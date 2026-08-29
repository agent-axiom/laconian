from __future__ import annotations

import builtins
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from laconian_eval.providers import GenerationRequest, ProviderError, TokenUsage
from laconian_eval.providers.openai import OpenAIProvider


class StubResponses:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class StubClient:
    def __init__(self, outcome: object) -> None:
        self.responses = StubResponses(outcome)


def request(**overrides: object) -> GenerationRequest:
    values: dict[str, object] = {
        "case_id": "case-001-en",
        "arm": "concise",
        "repetition": 0,
        "model": "test-model",
        "instructions": "Answer concisely.",
        "prompt": "Prompt",
        "max_output_tokens": 128,
        "temperature": None,
        "timeout_seconds": 60.0,
    }
    values.update(overrides)
    return GenerationRequest(**values)  # type: ignore[arg-type]


def response(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "output_text": "Complete answer.",
        "_request_id": "req_123",
        "status": "completed",
        "model": "gpt-5.5-2026-08-01",
        "error": None,
        "usage": SimpleNamespace(
            input_tokens=15,
            output_tokens=4,
            total_tokens=19,
            input_tokens_details=SimpleNamespace(cached_tokens=6),
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


_HUGE_INTEGER = 10**10_000


def sdk_error_type(name: str) -> type[Exception]:
    openai_error = type(
        "OpenAIError",
        (Exception,),
        {"__module__": "openai"},
    )
    api_error = type("APIError", (openai_error,), {"__module__": "openai"})
    api_status_error = type(
        "APIStatusError",
        (api_error,),
        {"__module__": "openai"},
    )
    api_connection_error = type(
        "APIConnectionError",
        (api_error,),
        {"__module__": "openai"},
    )
    if name == "OpenAIError":
        return openai_error
    if name == "APIError":
        return api_error
    if name == "APIStatusError":
        return api_status_error
    if name == "APIConnectionError":
        return api_connection_error
    if name == "APITimeoutError":
        return type(name, (api_connection_error,), {"__module__": "openai"})
    return type(name, (api_status_error,), {"__module__": "openai"})


def test_injected_client_uses_exact_responses_contract_and_maps_public_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def reject_openai_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "openai" or name.startswith("openai."):
            raise AssertionError("injected clients must not import the optional SDK")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_openai_import)
    client = StubClient(response())

    result = OpenAIProvider(client=client).generate(request())

    assert client.responses.calls == [
        {
            "model": "test-model",
            "instructions": "Answer concisely.",
            "input": "Prompt",
            "max_output_tokens": 128,
            "store": False,
        }
    ]
    assert result.output_text == "Complete answer."
    assert result.request_id == "req_123"
    assert result.finish_reason == "completed"
    assert result.response_model == "gpt-5.5-2026-08-01"
    assert result.delivery_certainty == "response_received"
    assert result.usage is not None
    assert result.usage.input_tokens == 15
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 19
    assert result.usage.cached_input_tokens == 6
    assert not hasattr(result, "response")


def test_nullable_fields_are_explicit_and_temperature_is_only_sent_when_present() -> None:
    client = StubClient(response(_request_id=None, usage=None, output_text="No metadata."))
    provider = OpenAIProvider(client=client)

    result = provider.generate(request(instructions=None, temperature=0.25, arm="baseline"))

    assert client.responses.calls == [
        {
            "model": "test-model",
            "instructions": None,
            "input": "Prompt",
            "max_output_tokens": 128,
            "store": False,
            "temperature": 0.25,
        }
    ]
    assert result.usage is None
    assert result.request_id is None
    assert result.finish_reason == "completed"
    assert result.delivery_certainty == "response_received"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"model": "  "}, "model"),
        ({"model": 7}, "model"),
        ({"prompt": "\t"}, "prompt"),
        ({"prompt": None}, "prompt"),
        ({"instructions": ""}, "instructions"),
        ({"instructions": 3}, "instructions"),
        ({"max_output_tokens": 0}, "max_output_tokens"),
        ({"max_output_tokens": True}, "max_output_tokens"),
        ({"temperature": -0.1}, "temperature"),
        ({"temperature": 2.1}, "temperature"),
        ({"temperature": _HUGE_INTEGER}, "temperature"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": _HUGE_INTEGER}, "timeout_seconds"),
        ({"timeout_seconds": 30}, "does not match"),
    ],
)
def test_invalid_local_requests_are_rejected_before_the_api_call(
    overrides: dict[str, object], message: str
) -> None:
    client = StubClient(response())

    with pytest.raises(ProviderError, match=message) as caught:
        OpenAIProvider(client=client).generate(request(**overrides))

    assert caught.value.kind == "configuration"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert client.responses.calls == []


@pytest.mark.parametrize(
    ("bad_response", "message", "invalid_field"),
    [
        (response(output_text=None), "output_text", "output"),
        (response(_request_id=123), "request ID", "request_id"),
        (response(status=7), "status", "status"),
        (response(model=None), "model", "model"),
        (response(usage=SimpleNamespace(input_tokens=1)), "usage", "usage"),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=True,
                    output_tokens=1,
                    total_tokens=2,
                    input_tokens_details=None,
                )
            ),
            "input_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=3,
                    total_tokens=4,
                    input_tokens_details=None,
                )
            ),
            "total_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=1,
                    total_tokens=4,
                    input_tokens_details=None,
                )
            ),
            "total_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=1,
                    total_tokens=3,
                    input_tokens_details=SimpleNamespace(cached_tokens=3),
                )
            ),
            "cached_tokens",
            "usage",
        ),
        (
            response(
                usage=SimpleNamespace(
                    input_tokens=2,
                    output_tokens=1,
                    total_tokens=3,
                    input_tokens_details=5,
                )
            ),
            "input_tokens_details",
            "usage",
        ),
    ],
)
def test_malformed_responses_become_nonretryable_provider_errors(
    bad_response: object,
    message: str,
    invalid_field: str,
) -> None:
    with pytest.raises(ProviderError, match=message) as caught:
        OpenAIProvider(client=StubClient(bad_response)).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == (None if invalid_field == "request_id" else "req_123")
    assert caught.value.response_model == (
        None if invalid_field == "model" else "gpt-5.5-2026-08-01"
    )
    assert caught.value.finish_reason == (None if invalid_field == "status" else "completed")
    assert caught.value.usage == (
        None
        if invalid_field == "usage"
        else TokenUsage(
            input_tokens=15,
            output_tokens=4,
            total_tokens=19,
            cached_input_tokens=6,
        )
    )


@pytest.mark.parametrize(
    (
        "exception_name",
        "status_code",
        "kind",
        "retryable",
        "delivery_certainty",
        "safe_retry_candidate",
    ),
    [
        (
            "AuthenticationError",
            401,
            "authentication",
            False,
            "definitely_rejected",
            False,
        ),
        ("PermissionDeniedError", 403, "permission", False, "definitely_rejected", False),
        ("BadRequestError", 400, "bad_request", False, "definitely_rejected", False),
        ("RateLimitError", 429, "rate_limit", True, "definitely_rejected", True),
        ("APITimeoutError", None, "timeout", True, "unknown", False),
        ("APIConnectionError", None, "connection", True, "unknown", False),
        ("InternalServerError", 500, "server_error", True, "unknown", False),
        ("APIStatusError", 408, "provider_status", True, "unknown", False),
        ("APIStatusError", 503, "server_error", True, "unknown", False),
        ("APIStatusError", 409, "provider_status", True, "definitely_rejected", True),
        ("APIStatusError", 422, "provider_status", False, "definitely_rejected", False),
        ("OpenAIError", None, "provider_error", False, "unknown", False),
    ],
)
def test_recognized_sdk_errors_are_classified_and_preserve_request_ids(
    exception_name: str,
    status_code: int | None,
    kind: str,
    retryable: bool,
    delivery_certainty: str,
    safe_retry_candidate: bool,
) -> None:
    exception = sdk_error_type(exception_name)("synthetic API failure")
    exception.request_id = "req_error"  # type: ignore[attr-defined]
    if status_code is not None:
        exception.status_code = status_code  # type: ignore[attr-defined]

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(exception)).generate(request())

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.delivery_certainty == delivery_certainty
    assert caught.value.request_id == "req_error"
    assert (
        caught.value.kind != "authentication"
        and caught.value.retryable
        and caught.value.delivery_certainty in {"definitely_not_sent", "definitely_rejected"}
    ) is safe_retry_candidate


@pytest.mark.parametrize(
    ("exception_name", "status_code", "kind", "retryable"),
    [
        ("AuthenticationError", 500, "authentication", False),
        ("RateLimitError", 500, "rate_limit", True),
        ("APITimeoutError", 400, "timeout", True),
    ],
)
def test_ambiguous_transport_evidence_precedes_rejection_classification(
    exception_name: str,
    status_code: int,
    kind: str,
    retryable: bool,
) -> None:
    exception = sdk_error_type(exception_name)("contradictory synthetic failure")
    exception.status_code = status_code  # type: ignore[attr-defined]

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(exception)).generate(request())

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.delivery_certainty == "unknown"


def test_unrelated_exceptions_and_base_exceptions_are_not_reclassified() -> None:
    unrelated = RuntimeError("programming defect")
    with pytest.raises(RuntimeError, match="programming defect"):
        OpenAIProvider(client=StubClient(unrelated)).generate(request())

    with pytest.raises(KeyboardInterrupt):
        OpenAIProvider(client=StubClient(KeyboardInterrupt())).generate(request())


@pytest.mark.parametrize("collision_name", ["AuthenticationError", "OpenAIError"])
def test_unrelated_exception_name_collisions_propagate_unchanged(
    collision_name: str,
) -> None:
    collision_type = type(collision_name, (RuntimeError,), {})
    collision = collision_type("application failure")
    collision.status_code = 401  # type: ignore[attr-defined]

    with pytest.raises(collision_type) as caught:
        OpenAIProvider(client=StubClient(collision)).generate(request())

    assert caught.value is collision


@pytest.mark.parametrize(
    "collision_name",
    [
        "AuthenticationError",
        "RateLimitError",
        "APITimeoutError",
        "APIConnectionError",
        "InternalServerError",
    ],
)
def test_non_sdk_subclass_name_collisions_on_openai_root_fail_closed(
    collision_name: str,
) -> None:
    collision_type = type(
        collision_name,
        (sdk_error_type("OpenAIError"),),
        {"__module__": __name__},
    )
    collision = collision_type("application-defined OpenAI failure")

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(collision)).generate(request())

    assert caught.value.kind == "provider_error"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "unknown"


def test_incomplete_response_is_a_nonretryable_provider_error() -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(status="incomplete"))).generate(request())

    assert caught.value.kind == "incomplete_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == "incomplete"
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )
    assert "gpt-5.5-2026-08-01" in caught.value.message


@pytest.mark.parametrize("output_text", ["", " \n\t"])
def test_completed_response_rejects_blank_output_with_request_id(output_text: str) -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(output_text=output_text))).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == "completed"
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )


@pytest.mark.parametrize(
    ("status", "public_error", "kind", "retryable", "message"),
    [
        (
            "failed",
            SimpleNamespace(
                code="server_error",
                message="Public server failure.",
                private_detail="must-not-leak",
            ),
            "server_error",
            True,
            "Public server failure.",
        ),
        (
            "failed",
            SimpleNamespace(
                code="rate_limit_exceeded",
                message="Public rate-limit failure.",
            ),
            "rate_limit_exceeded",
            True,
            "Public rate-limit failure.",
        ),
        (
            "failed",
            SimpleNamespace(
                code="authentication",
                message="Public authentication failure.",
            ),
            "authentication",
            False,
            "Public authentication failure.",
        ),
        ("cancelled", None, "cancelled", False, "cancelled"),
    ],
)
def test_failed_and_cancelled_responses_become_public_provider_errors(
    status: str,
    public_error: object | None,
    kind: str,
    retryable: bool,
    message: str,
) -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(status=status, error=public_error))).generate(
            request()
        )

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == status
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )
    assert message in caught.value.message
    assert "must-not-leak" not in caught.value.message


@pytest.mark.parametrize("status", ["queued", "in_progress", "unknown"])
def test_nonterminal_or_unknown_response_status_is_rejected_with_request_id(status: str) -> None:
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(response(status=status))).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == status
    assert caught.value.usage == TokenUsage(
        input_tokens=15,
        output_tokens=4,
        total_tokens=19,
        cached_input_tokens=6,
    )


def test_failed_response_with_invalid_usage_retains_other_valid_metadata() -> None:
    bad_usage = SimpleNamespace(
        input_tokens=2,
        output_tokens=1,
        total_tokens=4,
        input_tokens_details=None,
    )
    public_error = SimpleNamespace(code="server_error", message="Public failure.")

    with pytest.raises(ProviderError, match="total_tokens") as caught:
        OpenAIProvider(
            client=StubClient(response(status="failed", error=public_error, usage=bad_usage))
        ).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.delivery_certainty == "response_received"
    assert caught.value.request_id == "req_123"
    assert caught.value.response_model == "gpt-5.5-2026-08-01"
    assert caught.value.finish_reason == "failed"
    assert caught.value.usage is None


def test_live_client_is_configured_with_timeout_and_sdk_retries_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_client_calls: list[dict[str, object]] = []
    openai_calls: list[dict[str, object]] = []
    constructed_http_client = object()
    client = StubClient(response())
    module = ModuleType("openai")

    def make_http_client(**kwargs: object) -> object:
        http_client_calls.append(kwargs)
        return constructed_http_client

    def make_client(**kwargs: object) -> StubClient:
        openai_calls.append(kwargs)
        return client

    module.DefaultHttpxClient = make_http_client  # type: ignore[attr-defined]
    module.OpenAI = make_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://ambient.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "https://ambient.invalid:8443")
    monkeypatch.setenv("ALL_PROXY", "socks5://ambient.invalid:1080")
    monkeypatch.setenv("NO_PROXY", "api.openai.com")
    monkeypatch.setenv("SSL_CERT_FILE", "/ambient/cert.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/ambient/certs")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/ambient/requests.pem")
    monkeypatch.setenv("CURL_CA_BUNDLE", "/ambient/curl.pem")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ambient.invalid/v9")
    monkeypatch.setenv("OPENAI_ORG_ID", "ambient-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "ambient-project")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "ambient-admin")
    monkeypatch.setenv("OPENAI_WEBHOOK_SECRET", "ambient-webhook")

    provider = OpenAIProvider(api_key="test-key", timeout_seconds=120)
    provider.generate(request(timeout_seconds=120))

    assert http_client_calls == [{"trust_env": False}]
    assert openai_calls == [
        {
            "api_key": "test-key",
            "timeout": 120.0,
            "max_retries": 0,
            "base_url": "https://api.openai.com/v1",
            "organization": "",
            "project": "",
            "admin_api_key": "",
            "webhook_secret": "",
            "http_client": constructed_http_client,
        }
    ]
    assert client.responses.calls == [
        {
            "model": "test-model",
            "instructions": "Answer concisely.",
            "input": "Prompt",
            "max_output_tokens": 128,
            "store": False,
        }
    ]


def test_live_client_rejects_ambient_custom_headers_before_sdk_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    module = ModuleType("openai")

    def make_client(**kwargs: object) -> StubClient:
        calls.append(kwargs)
        return StubClient(response())

    module.OpenAI = make_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", '{"X-Ambient": "unsafe"}')

    with pytest.raises(ProviderError, match="OPENAI_CUSTOM_HEADERS") as caught:
        OpenAIProvider(api_key="configured-key")

    assert caught.value.kind == "configuration"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert calls == []


def test_live_client_requires_nonblank_key_and_the_optional_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ProviderError, match="API key") as blank:
        OpenAIProvider(api_key=" ")
    assert blank.value.kind == "configuration"
    assert blank.value.delivery_certainty == "definitely_not_sent"
    with pytest.raises(ProviderError, match="API key"):
        OpenAIProvider(api_key=3)  # type: ignore[arg-type]

    original_import = builtins.__import__

    def missing_openai(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "openai":
            raise ImportError("synthetic missing optional dependency")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "openai", raising=False)
    monkeypatch.setattr(builtins, "__import__", missing_openai)
    with pytest.raises(ProviderError, match="openai") as missing:
        OpenAIProvider(api_key="test-key")
    assert missing.value.kind == "configuration"
    assert missing.value.retryable is False
    assert missing.value.delivery_certainty == "definitely_not_sent"


def test_huge_provider_timeout_is_a_local_configuration_error() -> None:
    client = StubClient(response())

    with pytest.raises(ProviderError, match="timeout_seconds") as caught:
        OpenAIProvider(client=client, timeout_seconds=_HUGE_INTEGER)

    assert caught.value.kind == "configuration"
    assert caught.value.retryable is False
    assert caught.value.delivery_certainty == "definitely_not_sent"
    assert client.responses.calls == []
