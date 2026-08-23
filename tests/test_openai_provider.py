from __future__ import annotations

import builtins
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from laconian_eval.providers import GenerationRequest, ProviderError
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
        "usage": SimpleNamespace(
            input_tokens=15,
            output_tokens=4,
            total_tokens=19,
            input_tokens_details=SimpleNamespace(cached_tokens=6),
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def error_type(name: str) -> type[Exception]:
    return type(name, (Exception,), {})


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
    assert result.usage is not None
    assert result.usage.input_tokens == 15
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 19
    assert result.usage.cached_input_tokens == 6
    assert not hasattr(result, "response")


def test_nullable_fields_are_explicit_and_temperature_is_only_sent_when_present() -> None:
    client = StubClient(
        response(_request_id=None, status=None, usage=None, output_text="No metadata.")
    )
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
    assert result.finish_reason is None


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
        ({"timeout_seconds": 0}, "timeout_seconds"),
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
    assert client.responses.calls == []


@pytest.mark.parametrize(
    ("bad_response", "message"),
    [
        (response(output_text=None), "output_text"),
        (response(_request_id=123), "request ID"),
        (response(status=7), "status"),
        (response(usage=SimpleNamespace(input_tokens=1)), "usage"),
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
        ),
    ],
)
def test_malformed_responses_become_nonretryable_provider_errors(
    bad_response: object, message: str
) -> None:
    with pytest.raises(ProviderError, match=message) as caught:
        OpenAIProvider(client=StubClient(bad_response)).generate(request())

    assert caught.value.kind == "malformed_response"
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    ("exception_name", "status_code", "kind", "retryable"),
    [
        ("AuthenticationError", 401, "authentication", False),
        ("PermissionDeniedError", 403, "permission", False),
        ("BadRequestError", 400, "bad_request", False),
        ("RateLimitError", 429, "rate_limit", True),
        ("APITimeoutError", None, "timeout", True),
        ("APIConnectionError", None, "connection", True),
        ("InternalServerError", 500, "server_error", True),
        ("APIStatusError", 503, "server_error", True),
        ("APIStatusError", 409, "provider_status", False),
    ],
)
def test_recognized_sdk_errors_are_classified_and_preserve_request_ids(
    exception_name: str,
    status_code: int | None,
    kind: str,
    retryable: bool,
) -> None:
    exception = error_type(exception_name)("synthetic API failure")
    exception.request_id = "req_error"  # type: ignore[attr-defined]
    if status_code is not None:
        exception.status_code = status_code  # type: ignore[attr-defined]

    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=StubClient(exception)).generate(request())

    assert caught.value.kind == kind
    assert caught.value.retryable is retryable
    assert caught.value.request_id == "req_error"


def test_unrelated_exceptions_and_base_exceptions_are_not_reclassified() -> None:
    unrelated = RuntimeError("programming defect")
    with pytest.raises(RuntimeError, match="programming defect"):
        OpenAIProvider(client=StubClient(unrelated)).generate(request())

    with pytest.raises(KeyboardInterrupt):
        OpenAIProvider(client=StubClient(KeyboardInterrupt())).generate(request())


def test_live_client_is_configured_with_timeout_and_sdk_retries_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    client = StubClient(response())
    module = ModuleType("openai")

    def make_client(**kwargs: object) -> StubClient:
        calls.append(kwargs)
        return client

    module.OpenAI = make_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)

    provider = OpenAIProvider(api_key="test-key", timeout_seconds=120)
    provider.generate(request(timeout_seconds=120))

    assert calls == [{"api_key": "test-key", "timeout": 120.0, "max_retries": 0}]
    assert "timeout" not in client.responses.calls[0]


def test_live_client_requires_nonblank_key_and_the_optional_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ProviderError, match="API key") as blank:
        OpenAIProvider(api_key=" ")
    assert blank.value.kind == "configuration"
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
