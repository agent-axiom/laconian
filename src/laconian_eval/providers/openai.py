from __future__ import annotations

import math
import os
from typing import Protocol, cast

from laconian_eval.providers.base import (
    DeliveryCertainty,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    TokenUsage,
)


class _ResponsesResource(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesResource


def _provider_error(
    *,
    kind: str,
    message: str,
    retryable: bool,
    delivery_certainty: DeliveryCertainty,
    request_id: str | None = None,
    response_model: str | None = None,
    finish_reason: str | None = None,
    usage: TokenUsage | None = None,
) -> ProviderError:
    return ProviderError(
        kind=kind,
        message=message,
        retryable=retryable,
        request_id=request_id,
        delivery_certainty=delivery_certainty,
        response_model=response_model,
        finish_reason=finish_reason,
        usage=usage,
    )


def _configuration_error(message: str) -> ProviderError:
    return _provider_error(
        kind="configuration",
        message=message,
        retryable=False,
        delivery_certainty="definitely_not_sent",
    )


def _validate_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _configuration_error("timeout_seconds must be a finite positive number")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError):
        raise _configuration_error("timeout_seconds must be a finite positive number") from None
    if not math.isfinite(normalized) or normalized <= 0:
        raise _configuration_error("timeout_seconds must be a finite positive number")
    return normalized


def _openai_exception_names(error: Exception) -> frozenset[str]:
    return frozenset(base.__name__ for base in type(error).__mro__ if base.__module__ == "openai")


def _request_id(error: Exception) -> str | None:
    value = getattr(error, "request_id", None)
    return value if isinstance(value, str) else None


def _classify_api_error(error: Exception) -> ProviderError | None:
    names = _openai_exception_names(error)
    if "OpenAIError" not in names:
        return None
    raw_status = getattr(error, "status_code", None)
    status = raw_status if type(raw_status) is int else None
    kind = "provider_error"
    retryable = False
    if "APITimeoutError" in names:
        kind = "timeout"
        retryable = True
    elif "APIConnectionError" in names:
        kind = "connection"
        retryable = True
    elif "AuthenticationError" in names or status == 401:
        kind = "authentication"
    elif "PermissionDeniedError" in names or status == 403:
        kind = "permission"
    elif "BadRequestError" in names or status == 400:
        kind = "bad_request"
    elif "RateLimitError" in names or status == 429:
        kind = "rate_limit"
        retryable = True
    elif status in (408, 409):
        kind = "provider_status"
        retryable = True
    elif "InternalServerError" in names or (status is not None and status >= 500):
        kind = "server_error"
        retryable = True
    elif "APIStatusError" in names:
        kind = "provider_status"

    timeout_or_connection = bool(names & {"APITimeoutError", "APIConnectionError"})
    if timeout_or_connection or status == 408 or (status is not None and status >= 500):
        delivery_certainty: DeliveryCertainty = "unknown"
    elif (status is not None and 400 <= status < 500) or names & {
        "AuthenticationError",
        "PermissionDeniedError",
        "BadRequestError",
        "RateLimitError",
    }:
        delivery_certainty = "definitely_rejected"
    else:
        delivery_certainty = "unknown"

    return _provider_error(
        kind=kind,
        message=str(error),
        retryable=retryable,
        delivery_certainty=delivery_certainty,
        request_id=_request_id(error),
    )


def _malformed(
    message: str,
    request_id: str | None,
    *,
    response_model: str | None = None,
    finish_reason: str | None = None,
    usage: TokenUsage | None = None,
) -> ProviderError:
    return _provider_error(
        kind="malformed_response",
        message=message,
        retryable=False,
        delivery_certainty="response_received",
        request_id=request_id,
        response_model=response_model,
        finish_reason=finish_reason,
        usage=usage,
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
    if total_tokens != input_tokens + output_tokens:
        raise _malformed(
            "response usage total_tokens must equal input_tokens + output_tokens",
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
    metadata_error: str | None = None
    request_id: str | None = None
    try:
        request_id = _response_request_id(response)
    except ProviderError as error:
        metadata_error = error.message

    raw_response_model = getattr(response, "model", None)
    response_model: str | None = None
    if not isinstance(raw_response_model, str) or not raw_response_model.strip():
        metadata_error = metadata_error or "response model must be a nonblank string"
    else:
        response_model = raw_response_model

    raw_status = getattr(response, "status", None)
    status: str | None = None
    if not isinstance(raw_status, str):
        metadata_error = metadata_error or "response status must be a string"
    else:
        status = raw_status

    usage: TokenUsage | None = None
    try:
        usage = _parse_usage(getattr(response, "usage", None), request_id)
    except ProviderError as error:
        metadata_error = metadata_error or error.message

    if metadata_error is not None:
        raise _malformed(
            metadata_error,
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )

    assert response_model is not None
    assert status is not None
    response_error = getattr(response, "error", None)
    if status == "incomplete":
        raise _provider_error(
            kind="incomplete_response",
            message=f"OpenAI response is incomplete for model {response_model}",
            retryable=False,
            delivery_certainty="response_received",
            request_id=request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if status == "failed":
        if response_error is None:
            raise _provider_error(
                kind="failed_response",
                message=f"OpenAI response failed for model {response_model}",
                retryable=False,
                delivery_certainty="response_received",
                request_id=request_id,
                response_model=response_model,
                finish_reason=status,
                usage=usage,
            )
        try:
            code, message = _public_response_error(response_error, request_id)
        except ProviderError as error:
            raise _malformed(
                error.message,
                request_id,
                response_model=response_model,
                finish_reason=status,
                usage=usage,
            ) from None
        raise _provider_error(
            kind=code,
            message=message,
            retryable=code
            in {
                "rate_limit",
                "rate_limit_exceeded",
                "server_error",
                "vector_store_timeout",
            },
            delivery_certainty="response_received",
            request_id=request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if status == "cancelled":
        message = f"OpenAI response was cancelled for model {response_model}"
        if response_error is not None:
            try:
                _, message = _public_response_error(response_error, request_id)
            except ProviderError as error:
                raise _malformed(
                    error.message,
                    request_id,
                    response_model=response_model,
                    finish_reason=status,
                    usage=usage,
                ) from None
        raise _provider_error(
            kind="cancelled",
            message=message,
            retryable=False,
            delivery_certainty="response_received",
            request_id=request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if status != "completed":
        raise _malformed(
            f"response status {status!r} is not a completed terminal status",
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    if response_error is not None:
        raise _malformed(
            "completed response must not contain an error",
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        raise _malformed(
            "response output_text must be a nonblank string",
            request_id,
            response_model=response_model,
            finish_reason=status,
            usage=usage,
        )
    return GenerationResult(
        output_text=output_text,
        usage=usage,
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
            from openai import DefaultHttpxClient, OpenAI
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
                http_client=DefaultHttpxClient(trust_env=False),
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
            if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
                raise _configuration_error("temperature must be null or between 0 and 2")
            try:
                normalized_temperature = float(temperature)
            except (OverflowError, TypeError, ValueError):
                raise _configuration_error("temperature must be null or between 0 and 2") from None
            if not math.isfinite(normalized_temperature) or not 0 <= normalized_temperature <= 2:
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
