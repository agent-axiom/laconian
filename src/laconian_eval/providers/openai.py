from __future__ import annotations

import math
import os
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
    elif status in (408, 409):
        kind = "provider_status"
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


def _malformed(message: str, request_id: str | None) -> ProviderError:
    return ProviderError(
        kind="malformed_response",
        message=message,
        retryable=False,
        request_id=request_id,
    )


def _required_count(usage: object, field: str, request_id: str | None) -> int:
    value = getattr(usage, field, None)
    if type(value) is not int or value < 0:
        raise _malformed(
            f"response usage {field} must be a nonnegative integer",
            request_id,
        )
    return value


def _optional_cached_count(usage: object, request_id: str | None) -> int | None:
    details = getattr(usage, "input_tokens_details", None)
    if details is None:
        return None
    missing = object()
    value = getattr(details, "cached_tokens", missing)
    if value is missing:
        raise _malformed(
            "response usage input_tokens_details must expose cached_tokens",
            request_id,
        )
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _malformed(
            "response usage cached_tokens must be a nonnegative integer or null",
            request_id,
        )
    return value


def _parse_usage(raw_usage: object | None, request_id: str | None) -> TokenUsage | None:
    if raw_usage is None:
        return None
    input_tokens = _required_count(raw_usage, "input_tokens", request_id)
    output_tokens = _required_count(raw_usage, "output_tokens", request_id)
    total_tokens = _required_count(raw_usage, "total_tokens", request_id)
    cached_tokens = _optional_cached_count(raw_usage, request_id)
    if total_tokens < input_tokens + output_tokens:
        raise _malformed(
            "response usage total_tokens must cover input_tokens + output_tokens",
            request_id,
        )
    if cached_tokens is not None and cached_tokens > input_tokens:
        raise _malformed(
            "response usage cached_tokens cannot exceed input_tokens",
            request_id,
        )
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_tokens,
    )


def _response_request_id(response: object) -> str | None:
    value = getattr(response, "_request_id", None)
    if value is not None and not isinstance(value, str):
        raise _malformed("response request ID must be a string or null", None)
    return value


def _public_response_error(error: object, request_id: str | None) -> tuple[str, str]:
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    if not isinstance(code, str) or not code.strip():
        raise _malformed("response error code must be a nonblank string", request_id)
    if not isinstance(message, str) or not message.strip():
        raise _malformed("response error message must be a nonblank string", request_id)
    return code, message


def _parse_response(response: object) -> GenerationResult:
    request_id = _response_request_id(response)
    status = getattr(response, "status", None)
    if not isinstance(status, str):
        raise _malformed("response status must be a string", request_id)
    response_model = getattr(response, "model", None)
    if not isinstance(response_model, str) or not response_model.strip():
        raise _malformed("response model must be a nonblank string", request_id)

    response_error = getattr(response, "error", None)
    if status == "incomplete":
        raise ProviderError(
            kind="incomplete_response",
            message=f"OpenAI response is incomplete for model {response_model}",
            retryable=False,
            request_id=request_id,
        )
    if status == "failed":
        if response_error is None:
            raise ProviderError(
                kind="failed_response",
                message=f"OpenAI response failed for model {response_model}",
                retryable=False,
                request_id=request_id,
            )
        code, message = _public_response_error(response_error, request_id)
        raise ProviderError(
            kind=code,
            message=message,
            retryable=code in {"rate_limit", "server_error", "vector_store_timeout"},
            request_id=request_id,
        )
    if status == "cancelled":
        message = f"OpenAI response was cancelled for model {response_model}"
        if response_error is not None:
            _, message = _public_response_error(response_error, request_id)
        raise ProviderError(
            kind="cancelled",
            message=message,
            retryable=False,
            request_id=request_id,
        )
    if status != "completed":
        raise _malformed(
            f"response status {status!r} is not a completed terminal status", request_id
        )
    if response_error is not None:
        raise _malformed("completed response must not contain an error", request_id)

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise _malformed("response output_text must be a nonblank string", request_id)
    return GenerationResult(
        output_text=output_text,
        usage=_parse_usage(getattr(response, "usage", None), request_id),
        request_id=request_id,
        finish_reason=status,
        response_model=response_model,
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
        if os.environ.get("OPENAI_CUSTOM_HEADERS", "").strip():
            raise _configuration_error(
                "OPENAI_CUSTOM_HEADERS must be unset or blank for reproducible runs"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise _configuration_error(
                "the openai extra is required; install with `uv sync --extra openai`"
            ) from exc
        self._client = cast(
            _OpenAIClient,
            OpenAI(
                api_key=api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
                base_url="https://api.openai.com/v1",
                organization="",
                project="",
                admin_api_key="",
                webhook_secret="",
            ),
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
