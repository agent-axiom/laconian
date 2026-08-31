from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from itertools import product
from types import SimpleNamespace
from typing import get_args

import pytest

import laconian_eval.providers as providers_module
import laconian_eval.providers.base as provider_base_module
import laconian_eval.runner as runner_module
from laconian_eval import __version__
from laconian_eval.arms import Arm, arm_from_captured_bytes
from laconian_eval.models import (
    GenerationSettings,
    ProviderConfig,
    ResponseCase,
    RetryPolicy,
    RunManifest,
)
from laconian_eval.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    TokenUsage,
)
from laconian_eval.runner import run_to_jsonl


class _CharacterizationProvider:
    def __init__(self, outcomes: tuple[GenerationResult | ProviderError, ...]) -> None:
        self._outcomes = outcomes
        self._calls = 0

    def generate(self, request: GenerationRequest) -> GenerationResult:
        del request
        outcome = self._outcomes[self._calls]
        self._calls += 1
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


def _manifest() -> RunManifest:
    return RunManifest(
        schema_version="1",
        runner_version=__version__,
        run_name="delivery-characterization",
        provider=ProviderConfig(kind="fake", model="requested-model-v1"),
        case_files=("cases.yaml",),
        arms=("baseline", "concise"),
        repetitions=1,
        arm_order_seed=0,
        generation=GenerationSettings(max_output_tokens=128, temperature=None),
        retry=RetryPolicy(max_transient_retries=0, timeout_seconds=5),
    )


def _case() -> ResponseCase:
    return ResponseCase(
        id="direct-answer-en",
        scenario_id="direct-answer",
        locale="en",
        category="direct",
        prompt="Explain idempotency.",
    )


def _arms() -> tuple[Arm, Arm]:
    return (
        arm_from_captured_bytes("baseline", b""),
        arm_from_captured_bytes("concise", b"Answer concisely."),
    )


def test_v1_provider_serialization_characterization(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FrozenDateTime:
        @classmethod
        def now(cls, timezone) -> datetime:
            assert timezone is UTC
            return datetime(2026, 8, 29, 12, 34, 56, 123456, tzinfo=UTC)

    monotonic_values = iter((10.0, 10.125, 20.0, 20.25))
    monkeypatch.setattr(runner_module, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        runner_module,
        "time",
        SimpleNamespace(monotonic=lambda: next(monotonic_values)),
    )
    provider = _CharacterizationProvider(
        (
            GenerationResult(
                output_text="Done.",
                usage=TokenUsage(
                    input_tokens=4,
                    output_tokens=1,
                    total_tokens=5,
                    cached_input_tokens=0,
                ),
                request_id="request-success",
                finish_reason="stop",
                response_model="returned-model-v1",
            ),
            ProviderError(
                kind="rate_limit",
                message="Try again later.",
                retryable=True,
                request_id="request-error",
            ),
        )
    )
    output_path = tmp_path / "raw.jsonl"

    run_to_jsonl(
        manifest=_manifest(),
        cases=(_case(),),
        arms=_arms(),
        provider=provider,
        output_path=output_path,
        run_id="run-1",
        sleep=lambda _: None,
    )

    expected = (
        b'{"schema_version":"1","runner_version":"0.1.0a1","run_id":"run-1",'
        b'"manifest_sha256":"5b3dfb1e8524dea8056c6cbe9c9a87c6f12cf8a071bfcd434c40003bc2f12dad",'
        b'"case_id":"direct-answer-en","case_definition_sha256":"f44c40a8d927e21fb515e81ed85b478abfaedad0bc8a9decc611ba74c535595d",'
        b'"arm":"baseline","repetition":0,"attempt":1,"terminal":true,'
        b'"retry_of_attempt":null,"backoff_ms":null,'
        b'"prompt_sha256":"816fc4ad159e0afcee464e117f604e018871b558e24f2c224ca2c3d76a96591f",'
        b'"instruction_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",'
        b'"provider":"fake","model":"requested-model-v1",'
        b'"response_model":"returned-model-v1",'
        b'"started_at":"2026-08-29T12:34:56.123456Z","elapsed_ms":125,'
        b'"output_text":"Done.","usage":{"input_tokens":4,"output_tokens":1,'
        b'"total_tokens":5,"cached_input_tokens":0},"request_id":"request-success",'
        b'"finish_reason":"stop","error":null}\n'
        b'{"schema_version":"1","runner_version":"0.1.0a1","run_id":"run-1",'
        b'"manifest_sha256":"5b3dfb1e8524dea8056c6cbe9c9a87c6f12cf8a071bfcd434c40003bc2f12dad",'
        b'"case_id":"direct-answer-en","case_definition_sha256":"f44c40a8d927e21fb515e81ed85b478abfaedad0bc8a9decc611ba74c535595d",'
        b'"arm":"concise","repetition":0,"attempt":1,"terminal":true,'
        b'"retry_of_attempt":null,"backoff_ms":null,'
        b'"prompt_sha256":"816fc4ad159e0afcee464e117f604e018871b558e24f2c224ca2c3d76a96591f",'
        b'"instruction_sha256":"49f0aab807da85db802937558c8afa5617cfc9e05002327157b321b56b139cd1",'
        b'"provider":"fake","model":"requested-model-v1","response_model":null,'
        b'"started_at":"2026-08-29T12:34:56.123456Z","elapsed_ms":250,'
        b'"output_text":null,"usage":null,"request_id":null,"finish_reason":null,'
        b'"error":{"kind":"rate_limit","message":"Try again later.",'
        b'"retryable":true,"request_id":"request-error"}}\n'
    )
    assert output_path.read_bytes() == expected


def test_generation_result_has_fixed_response_received_certainty() -> None:
    result = GenerationResult(output_text="Done.")

    assert result.delivery_certainty == "response_received"
    with pytest.raises(TypeError):
        GenerationResult(  # type: ignore[call-arg]
            output_text="Done.",
            delivery_certainty="unknown",
        )


def test_provider_error_defaults_to_unknown_fail_closed() -> None:
    error = ProviderError(
        kind="temporary",
        message="Try again.",
        retryable=True,
    )

    assert error.delivery_certainty == "unknown"
    assert error.response_model is None
    assert error.finish_reason is None
    assert error.usage is None
    assert error.retryable is True


def test_provider_error_exposes_exact_optional_response_metadata() -> None:
    usage = TokenUsage(
        input_tokens=7,
        output_tokens=2,
        total_tokens=9,
        cached_input_tokens=3,
    )
    error = ProviderError(
        kind="failed_response",
        message="The response failed.",
        retryable=False,
        request_id="request-123",
        delivery_certainty="response_received",
        response_model="returned-model-v1",
        finish_reason="failed",
        usage=usage,
    )

    assert error.delivery_certainty == "response_received"
    assert error.response_model == "returned-model-v1"
    assert error.finish_reason == "failed"
    assert error.usage is usage
    assert error.request_id == "request-123"
    assert error.args == ("The response failed.",)


@pytest.mark.parametrize(
    ("delivery_certainty", "retryable", "kind"),
    product(
        (
            "definitely_not_sent",
            "definitely_rejected",
            "response_received",
            "unknown",
        ),
        (False, True),
        ("authentication", "rate_limit"),
    ),
)
def test_safe_retry_candidate_requires_transience_safe_delivery_and_non_authentication(
    delivery_certainty: str,
    retryable: bool,
    kind: str,
) -> None:
    error = ProviderError(
        kind=kind,
        message="Synthetic failure.",
        retryable=retryable,
        delivery_certainty=delivery_certainty,  # type: ignore[arg-type]
    )

    safe_retry_candidate = (
        error.kind != "authentication"
        and error.retryable
        and error.delivery_certainty in {"definitely_not_sent", "definitely_rejected"}
    )
    assert safe_retry_candidate is (
        kind == "rate_limit"
        and retryable
        and delivery_certainty in {"definitely_not_sent", "definitely_rejected"}
    )
    if delivery_certainty == "unknown" and retryable:
        assert error.retryable is True
        assert safe_retry_candidate is False


def test_provider_records_remain_frozen_slotted_and_v1_compatible() -> None:
    result = GenerationResult(output_text="Done.")
    error = ProviderError(
        kind="temporary",
        message="Try again.",
        retryable=True,
        request_id="request-123",
    )

    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.delivery_certainty = "response_received"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        error.delivery_certainty = "unknown"  # type: ignore[misc]
    assert error.args == ("Try again.",)
    assert str(error) == "Try again."


def test_delivery_certainty_has_one_public_canonical_alias() -> None:
    base_alias = getattr(provider_base_module, "DeliveryCertainty", None)
    public_alias = getattr(providers_module, "DeliveryCertainty", None)

    assert public_alias is base_alias
    assert get_args(base_alias) == (
        "definitely_not_sent",
        "definitely_rejected",
        "response_received",
        "unknown",
    )
