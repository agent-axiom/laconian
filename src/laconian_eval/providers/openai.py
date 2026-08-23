from __future__ import annotations

import math
from typing import Protocol, cast

from laconian_eval.providers.base import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    TokenUsage,
)


class _ResponsesResource(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesResource


def _configuration_error(message: str) -> ProviderError:
    return ProviderError(kind="configuration", message=message, retryable=False)


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _configuration_error("timeout_seconds must be a finite positive number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise _configuration_error("timeout_seconds must be a finite positive number")
    return normalized


def _exception_names(error: Exception) -> frozenset[str]:
    return frozenset(base.__name__ for base in type(error).__mro__)


def _request_id(error: Exception) -> str | None:
    value = getattr(error, "request_id", None)
    return value if isinstance(value, str) else None


def _classify_api_error(error: Exception) -> ProviderError | None:
    names = _exception_names(error)
    recognized = bool(
        names
        & {
            "OpenAIError",
            "APIError",
            "APIStatusError",
            "AuthenticationError",
            "PermissionDeniedError",
            "BadRequestError",
            "RateLimitError",
            "APITimeoutError",
            "APIConnectionError",
            "InternalServerError",
        }
    )
    if not recognized:
        return None

    raw_status = getattr(error, "status_code", None)
    status = raw_status if type(raw_status) is int else None
    kind = "provider_error"
    retryable = False
    if "AuthenticationError" in names or status == 401:
        kind = "authentication"
    elif "PermissionDeniedError" in names or status == 403:
        kind = "permission"
    elif "BadRequestError" in names or status == 400:
        kind = "bad_request"
    elif "RateLimitError" in names or status == 429:
        kind = "rate_limit"
        retryable = True
    elif "APITimeoutError" in names:
        kind = "timeout"
        retryable = True
    elif "APIConnectionError" in names:
        kind = "connection"
        retryable = True
    elif "InternalServerError" in names or (status is not None and status >= 500):
        kind = "server_error"
        retryable = True
    elif "APIStatusError" in names:
        kind = "provider_status"

    return ProviderError(
        kind=kind,
        message=str(error),
        retryable=retryable,
        request_id=_request_id(error),
    )


def _required_count(usage: object, field: str) -> int:
    value = getattr(usage, field, None)
    if type(value) is not int or value < 0:
        raise ProviderError(
            kind="malformed_response",
            message=f"response usage {field} must be a nonnegative integer",
            retryable=False,
        )
    return value


def _optional_cached_count(usage: object) -> int | None:
    details = getattr(usage, "input_tokens_details", None)
    if details is None:
        return None
    missing = object()
    value = getattr(details, "cached_tokens", missing)
    if value is missing:
        raise ProviderError(
            kind="malformed_response",
            message="response usage input_tokens_details must expose cached_tokens",
            retryable=False,
        )
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ProviderError(
            kind="malformed_response",
            message="response usage cached_tokens must be a nonnegative integer or null",
            retryable=False,
        )
    return value


def _parse_usage(raw_usage: object | None) -> TokenUsage | None:
    if raw_usage is None:
        return None
    input_tokens = _required_count(raw_usage, "input_tokens")
    output_tokens = _required_count(raw_usage, "output_tokens")
    total_tokens = _required_count(raw_usage, "total_tokens")
    cached_tokens = _optional_cached_count(raw_usage)
    if total_tokens < input_tokens + output_tokens:
        raise ProviderError(
            kind="malformed_response",
            message="response usage total_tokens must cover input_tokens + output_tokens",
            retryable=False,
        )
    if cached_tokens is not None and cached_tokens > input_tokens:
        raise ProviderError(
            kind="malformed_response",
            message="response usage cached_tokens cannot exceed input_tokens",
            retryable=False,
        )
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_tokens,
    )


def _optional_response_string(response: object, field: str, label: str) -> str | None:
    value = getattr(response, field, None)
    if value is not None and not isinstance(value, str):
        raise ProviderError(
            kind="malformed_response",
            message=f"response {label} must be a string or null",
            retryable=False,
        )
    return value


def _parse_response(response: object) -> GenerationResult:
    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str):
        raise ProviderError(
            kind="malformed_response",
            message="response output_text must be a string",
            retryable=False,
        )
    return GenerationResult(
        output_text=output_text,
        usage=_parse_usage(getattr(response, "usage", None)),
        request_id=_optional_response_string(response, "_request_id", "request ID"),
        finish_reason=_optional_response_string(response, "status", "status"),
    )


class OpenAIProvider:
    __slots__ = ("_client", "_timeout_seconds")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: object | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._timeout_seconds = _validate_timeout(timeout_seconds)
        if client is not None:
            self._client = cast(_OpenAIClient, client)
            return
        if not isinstance(api_key, str) or not api_key.strip():
            raise _configuration_error("a nonblank OpenAI API key is required")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise _configuration_error(
                "the openai extra is required; install with `uv sync --extra openai`"
            ) from exc
        self._client = cast(
            _OpenAIClient,
            OpenAI(api_key=api_key, timeout=self._timeout_seconds, max_retries=0),
        )

    def _validate_request(self, request: GenerationRequest) -> None:
        if not isinstance(request.model, str) or not request.model.strip():
            raise _configuration_error("model must not be blank")
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise _configuration_error("prompt must not be blank")
        if request.instructions is not None and (
            not isinstance(request.instructions, str) or not request.instructions.strip()
        ):
            raise _configuration_error("instructions must be null or nonblank")
        if type(request.max_output_tokens) is not int or request.max_output_tokens < 1:
            raise _configuration_error("max_output_tokens must be a positive integer")
        if request.temperature is not None:
            temperature = request.temperature
            if (
                isinstance(temperature, bool)
                or not isinstance(temperature, (int, float))
                or not math.isfinite(float(temperature))
                or not 0 <= float(temperature) <= 2
            ):
                raise _configuration_error("temperature must be null or between 0 and 2")
        request_timeout = _validate_timeout(request.timeout_seconds)
        if request_timeout != self._timeout_seconds:
            raise _configuration_error(
                "request timeout_seconds does not match the provider client timeout"
            )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self._validate_request(request)
        kwargs: dict[str, object] = {
            "model": request.model,
            "instructions": request.instructions,
            "input": request.prompt,
            "max_output_tokens": request.max_output_tokens,
            "store": False,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        try:
            response = self._client.responses.create(**kwargs)
        except Exception as exc:
            classified = _classify_api_error(exc)
            if classified is None:
                raise
            raise classified from exc
        return _parse_response(response)
