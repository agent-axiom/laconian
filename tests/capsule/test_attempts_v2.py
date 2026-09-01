from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any, cast, get_args
from uuid import UUID

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

import laconian_eval.capsule.attempts as attempts_module
import laconian_eval.providers.base as provider_base
from laconian_eval.capsule.attempts import (
    AttemptErrorV2,
    AttemptEvidenceError,
    AttemptUsageV2,
    NormalizedProviderEvidenceV2,
    RawAttemptV2,
    derive_attempt_id,
    derive_response_id,
    normalize_provider_outcome,
    raw_attempt_bytes,
    raw_attempt_jsonl,
    raw_record_sha256,
)
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.sanitizer import SanitizedOutput, SanitizerPatterns
from laconian_eval.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ReplayProvider,
    TokenUsage,
)

RUN_ID = UUID("12345678-1234-4abc-8def-1234567890ab")
ATTEMPT_ID = "fe416f7589b80d8488d4d3820cda93956d6770eee00ce179ef83ec3232d30ca3"
OUTPUT_SHA256 = "ed251864987c367e9641fbdc89c1d83e9bf0fa2e3eecef8f301c79f619bfac81"
RESPONSE_ID = "3f7e76a2e3e62156438f2296933a428f2ad04c4e1fa4c81264aee8882bc82ff3"
BOUNDARY_CANARY = "TOP-SECRET /private/build boundary canary"


class EvilUUID(UUID):
    def __str__(self) -> str:
        raise RuntimeError(BOUNDARY_CANARY)


class EvilDate(datetime):
    def utcoffset(self) -> timedelta | None:
        raise RuntimeError(BOUNDARY_CANARY)


class EvilTZ(tzinfo):
    def utcoffset(self, value: datetime | None) -> timedelta | None:
        raise RuntimeError(BOUNDARY_CANARY)

    def dst(self, value: datetime | None) -> timedelta | None:
        return timedelta(0)

    def tzname(self, value: datetime | None) -> str | None:
        return "evil"


class EvilInt(int):
    def __rshift__(self, other: object) -> int:
        raise RuntimeError(BOUNDARY_CANARY)

    def __format__(self, format_spec: str) -> str:
        raise RuntimeError(BOUNDARY_CANARY)


def valid_attempt_payload() -> dict[str, Any]:
    return {
        "schema_version": "2",
        "runner_version": "0.1.0a1",
        "run_id": str(RUN_ID),
        "manifest_sha256": "4" * 64,
        "plan_item_id": "1" * 64,
        "attempt_id": ATTEMPT_ID,
        "scenario_uid": "2" * 64,
        "case_uid": "3" * 64,
        "case_id": "direct-answer-en",
        "locale": "en",
        "case_definition_sha256": "5" * 64,
        "arm": "if",
        "repetition": 0,
        "attempt": 1,
        "terminal": True,
        "call_sequence": 0,
        "retry_of_attempt": None,
        "backoff_ms": None,
        "delivery_certainty": "response_received",
        "prompt_sha256": "6" * 64,
        "instruction_sha256": "7" * 64,
        "request_config_sha256": "8" * 64,
        "provider": "replay",
        "model": "fixture-v1",
        "response_model": "replay-v1",
        "started_at": "2026-08-29T12:34:56.123456Z",
        "elapsed_ms": 5,
        "output_text": "Done.",
        "output_sha256": OUTPUT_SHA256,
        "response_id": RESPONSE_ID,
        "output_was_redacted": False,
        "output_redaction_count": 0,
        "discarded_output_byte_length": None,
        "discarded_output_sha256": None,
        "usage": {
            "input_tokens": 4,
            "output_tokens": 1,
            "total_tokens": 5,
            "cached_input_tokens": 0,
            "availability": "complete",
            "source": "provider",
            "cache_accounting": "reported",
        },
        "request_id": "replay-request-1",
        "finish_reason": "stop",
        "error": None,
        "terminal_reason": "success",
    }


def valid_attempt() -> RawAttemptV2:
    return RawAttemptV2.model_validate(valid_attempt_payload())


def test_raw_attempt_v2_round_trips_complete_canonical_shape() -> None:
    payload = valid_attempt_payload()
    attempt = RawAttemptV2.model_validate(payload)

    assert attempt.model_dump(mode="json") == payload
    assert raw_attempt_bytes(attempt) == canonical_json(payload)


def test_attempt_id_uses_the_normative_domain_and_preimage() -> None:
    preimage = (
        b'{"attempt_number":1,"plan_item_id":"'
        + b"1" * 64
        + b'","run_id":"12345678-1234-4abc-8def-1234567890ab"}'
    )
    expected = hashlib.sha256(b"laconian-attempt-v1\0" + preimage).hexdigest()

    assert expected == ATTEMPT_ID
    assert derive_attempt_id(RUN_ID, "1" * 64, 1) == expected


def test_output_and_response_id_bind_persisted_redacted_output() -> None:
    attempt = valid_attempt()
    preimage = canonical_json(
        {
            "run_id": RUN_ID,
            "plan_item_id": "1" * 64,
            "attempt_id": ATTEMPT_ID,
            "case_uid": "3" * 64,
            "instruction_sha256": "7" * 64,
            "output_sha256": OUTPUT_SHA256,
        }
    )

    assert hashlib.sha256(b"Done.").hexdigest() == OUTPUT_SHA256
    assert hashlib.sha256(b"laconian-response-v1\0" + preimage).hexdigest() == RESPONSE_ID
    assert derive_response_id(attempt) == RESPONSE_ID


def test_raw_record_hash_covers_lf_free_canonical_row_and_is_not_embedded() -> None:
    attempt = valid_attempt()
    row = raw_attempt_bytes(attempt)

    assert not row.endswith(b"\n")
    assert b"raw_record_sha256" not in row
    assert raw_record_sha256(attempt) == hashlib.sha256(row).hexdigest()


def test_raw_jsonl_row_has_exactly_one_lf_and_respects_sixteen_mib_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempt = valid_attempt()
    row = raw_attempt_bytes(attempt)

    assert len(row) < RESOURCE_LIMITS_V1.raw_jsonl_row_bytes
    assert raw_attempt_jsonl(attempt) == row + b"\n"
    monkeypatch.setattr(
        attempts_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, raw_jsonl_row_bytes=len(row)),
    )
    assert raw_attempt_jsonl(attempt) == row + b"\n"
    monkeypatch.setattr(
        attempts_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, raw_jsonl_row_bytes=len(row) - 1),
    )
    with pytest.raises(AttemptEvidenceError) as caught:
        raw_attempt_jsonl(attempt)
    assert caught.value.code == "raw_jsonl_row_limit"


def test_attempt_models_are_frozen_strict_and_forbid_unknown_fields() -> None:
    attempt = valid_attempt()

    with pytest.raises(ValidationError):
        attempt.terminal = False
    with pytest.raises(ValidationError):
        RawAttemptV2.model_validate(valid_attempt_payload() | {"unknown": "forbidden"})
    with pytest.raises(ValidationError):
        AttemptUsageV2.model_validate(valid_attempt_payload()["usage"] | {"extra": 1})
    with pytest.raises(ValidationError):
        AttemptErrorV2.model_validate(
            {
                "kind": "temporary",
                "message": "Temporary failure.",
                "retryable": 1,
                "request_id": None,
            }
        )


_STRING_PATHS = (
    ("schema_version",),
    ("runner_version",),
    ("run_id",),
    ("manifest_sha256",),
    ("plan_item_id",),
    ("attempt_id",),
    ("scenario_uid",),
    ("case_uid",),
    ("case_id",),
    ("locale",),
    ("case_definition_sha256",),
    ("arm",),
    ("delivery_certainty",),
    ("prompt_sha256",),
    ("instruction_sha256",),
    ("request_config_sha256",),
    ("provider",),
    ("model",),
    ("response_model",),
    ("started_at",),
    ("output_text",),
    ("output_sha256",),
    ("response_id",),
    ("usage", "availability"),
    ("usage", "source"),
    ("usage", "cache_accounting"),
    ("request_id",),
    ("finish_reason",),
    ("terminal_reason",),
)


@pytest.mark.parametrize("path", _STRING_PATHS)
def test_every_persisted_string_rejects_unpaired_surrogates(path: tuple[str, ...]) -> None:
    payload = valid_attempt_payload()
    target = payload
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = "\ud800"

    with pytest.raises((ValidationError, ValueError, UnicodeError)):
        RawAttemptV2.model_validate(payload)


def _assert_content_free_error(call: Any) -> None:
    with pytest.raises(AttemptEvidenceError) as caught:
        call()
    assert caught.value.code == "invalid_attempt_evidence"
    assert str(caught.value) == "attempt evidence rejected"
    assert "TOP-SECRET" not in str(caught.value)
    assert "TOP-SECRET" not in repr(caught.value)


def test_public_helpers_reject_forged_top_level_state_content_free() -> None:
    values = dict(valid_attempt().__dict__)
    values["output_text"] = "TOP-SECRET /private/build"
    forged = RawAttemptV2.model_construct(**values)

    for helper in (raw_attempt_bytes, raw_record_sha256, raw_attempt_jsonl, derive_response_id):
        _assert_content_free_error(lambda helper=helper: helper(forged))


def test_public_helpers_reject_forged_nested_state_content_free() -> None:
    usage_values = dict(valid_attempt().usage.__dict__)
    usage_values["input_tokens"] = "TOP-SECRET /private/build"
    forged_usage = AttemptUsageV2.model_construct(**usage_values)
    values = dict(valid_attempt().__dict__)
    values["usage"] = forged_usage
    forged = RawAttemptV2.model_construct(**values)

    for helper in (raw_attempt_bytes, raw_record_sha256, raw_attempt_jsonl, derive_response_id):
        _assert_content_free_error(lambda helper=helper: helper(forged))


def test_public_helpers_reject_forged_nested_error_state_content_free() -> None:
    attempt = RawAttemptV2.model_validate(
        error_payload(
            certainty="response_received",
            retryable=False,
            terminal=True,
            terminal_reason="provider_rejected",
        )
    )
    assert attempt.error is not None
    error_values = dict(attempt.error.__dict__)
    error_values["retryable"] = BOUNDARY_CANARY
    forged_error = AttemptErrorV2.model_construct(**error_values)
    values = dict(attempt.__dict__)
    values["error"] = forged_error
    forged = RawAttemptV2.model_construct(**values)

    for helper in (raw_attempt_bytes, raw_record_sha256, raw_attempt_jsonl, derive_response_id):
        _assert_content_free_error(lambda helper=helper: helper(forged))


def test_public_helpers_ignore_shadowed_instance_model_dump() -> None:
    attempt = valid_attempt()
    forged = RawAttemptV2.model_construct(**dict(attempt.__dict__))

    def shadowed_model_dump(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError(BOUNDARY_CANARY)

    object.__setattr__(forged, "model_dump", shadowed_model_dump)

    assert raw_attempt_bytes(forged) == raw_attempt_bytes(attempt)
    assert raw_record_sha256(forged) == raw_record_sha256(attempt)
    assert raw_attempt_jsonl(forged) == raw_attempt_jsonl(attempt)
    assert derive_response_id(forged) == derive_response_id(attempt)


def test_public_helpers_catch_unexpected_datetime_projection_errors_content_free() -> None:
    values = dict(valid_attempt().__dict__)
    values["started_at"] = datetime(2026, 8, 29, 12, 34, 56, 123456, tzinfo=EvilTZ())
    forged = RawAttemptV2.model_construct(**values)

    for helper in (raw_attempt_bytes, raw_record_sha256, raw_attempt_jsonl, derive_response_id):
        _assert_content_free_error(lambda helper=helper: helper(forged))


def test_attempt_boundaries_reject_uuid_and_datetime_subclasses_before_projection() -> None:
    evil_uuid_payload = valid_attempt_payload()
    evil_uuid_payload["run_id"] = EvilUUID(str(RUN_ID))
    evil_date_payload = valid_attempt_payload()
    evil_date_payload["started_at"] = EvilDate(
        2026,
        8,
        29,
        12,
        34,
        56,
        123456,
        tzinfo=UTC,
    )

    for payload in (evil_uuid_payload, evil_date_payload):
        with pytest.raises(ValidationError):
            RawAttemptV2.model_validate(payload)


def test_attempt_boundaries_reject_evil_exact_uuid_int_and_datetime_timezone() -> None:
    evil_uuid = UUID("12345678-1234-4abc-8def-1234567890ab")
    object.__setattr__(evil_uuid, "int", EvilInt(evil_uuid.int))
    evil_uuid_payload = valid_attempt_payload()
    evil_uuid_payload["run_id"] = evil_uuid
    evil_timezone_payload = valid_attempt_payload()
    evil_timezone_payload["started_at"] = datetime(
        2026,
        8,
        29,
        12,
        34,
        56,
        123456,
        tzinfo=EvilTZ(),
    )

    for payload in (evil_uuid_payload, evil_timezone_payload):
        with pytest.raises(ValidationError):
            RawAttemptV2.model_validate(payload)


def test_exact_uuid_and_datetime_inputs_reparse_to_exact_base_objects() -> None:
    payload = valid_attempt_payload()
    payload["run_id"] = UUID(str(RUN_ID))
    payload["started_at"] = datetime(
        2026,
        8,
        29,
        12,
        34,
        56,
        123456,
        tzinfo=UTC,
    )

    attempt = RawAttemptV2.model_validate(payload)

    assert type(attempt.run_id) is UUID
    assert type(attempt.run_id.int) is int
    assert type(attempt.started_at) is datetime
    assert attempt.model_dump(mode="json")["run_id"] == str(RUN_ID)
    assert attempt.model_dump(mode="json")["started_at"] == "2026-08-29T12:34:56.123456Z"


def test_derive_attempt_id_rejects_evil_uuid_int_content_free() -> None:
    evil_uuid = UUID("12345678-1234-4abc-8def-1234567890ab")
    object.__setattr__(evil_uuid, "int", EvilInt(evil_uuid.int))

    with pytest.raises(AttemptEvidenceError) as caught:
        derive_attempt_id(evil_uuid, "1" * 64, 1)

    assert caught.value.code == "invalid_attempt_identity"
    assert str(caught.value) == "attempt evidence rejected"
    assert BOUNDARY_CANARY not in str(caught.value)
    assert BOUNDARY_CANARY not in repr(caught.value)


@pytest.mark.parametrize(
    ("run_id", "plan_item_id", "attempt_number"),
    [
        (UUID("12345678-1234-1abc-8def-1234567890ab"), "1" * 64, 1),
        (str(RUN_ID), "1" * 64, 1),
        (RUN_ID, "TOP-SECRET /private/build", 1),
        (RUN_ID, "1" * 64, True),
        (RUN_ID, "1" * 64, 0),
        (RUN_ID, "1" * 64, 7),
        (RUN_ID, "1" * 64, 10**10_000),
    ],
    ids=(
        "uuid1",
        "uuid-string",
        "invalid-plan-id",
        "boolean-attempt",
        "zero-attempt",
        "seventh-attempt",
        "enormous-attempt",
    ),
)
def test_identity_helpers_reject_invalid_inputs_content_free(
    run_id: object,
    plan_item_id: object,
    attempt_number: object,
) -> None:
    with pytest.raises(AttemptEvidenceError) as caught:
        derive_attempt_id(run_id, plan_item_id, attempt_number)  # type: ignore[arg-type]

    assert caught.value.code == "invalid_attempt_identity"
    assert str(caught.value) == "attempt evidence rejected"
    assert "TOP-SECRET" not in str(caught.value)
    assert "TOP-SECRET" not in repr(caught.value)


def usage_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "input_tokens": 4,
        "output_tokens": 1,
        "total_tokens": 5,
        "cached_input_tokens": 0,
        "availability": "complete",
        "source": "provider",
        "cache_accounting": "reported",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        usage_payload(),
        usage_payload(cached_input_tokens=None, cache_accounting="not_reported"),
        usage_payload(
            input_tokens=0,
            output_tokens=None,
            total_tokens=None,
            cached_input_tokens=0,
            availability="partial",
            source="adapter",
        ),
        usage_payload(
            input_tokens=None,
            output_tokens=0,
            total_tokens=0,
            cached_input_tokens=None,
            availability="partial",
            cache_accounting="not_applicable",
        ),
        usage_payload(
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cached_input_tokens=None,
            availability="unavailable",
            cache_accounting="not_reported",
        ),
        usage_payload(
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cached_input_tokens=None,
            availability="unavailable",
            source="adapter",
            cache_accounting="not_applicable",
        ),
    ],
)
def test_attempt_usage_accepts_exact_valid_states(payload: dict[str, object]) -> None:
    assert AttemptUsageV2.model_validate(payload).model_dump(mode="json") == payload


@pytest.mark.parametrize(
    "payload",
    [
        usage_payload(availability="unavailable"),
        usage_payload(
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cached_input_tokens=0,
            availability="unavailable",
        ),
        usage_payload(
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cached_input_tokens=None,
            availability="partial",
            cache_accounting="not_reported",
        ),
        usage_payload(availability="partial"),
        usage_payload(output_tokens=None, availability="complete"),
        usage_payload(total_tokens=6),
        usage_payload(cached_input_tokens=None, cache_accounting="reported"),
        usage_payload(cached_input_tokens=0, cache_accounting="not_reported"),
        usage_payload(cached_input_tokens=0, cache_accounting="not_applicable"),
        usage_payload(input_tokens=None, cached_input_tokens=0, availability="partial"),
        usage_payload(input_tokens=1, cached_input_tokens=2),
        usage_payload(input_tokens=True),
        usage_payload(cached_input_tokens=False),
    ],
)
def test_attempt_usage_rejects_every_invalid_cross_field_state(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AttemptUsageV2.model_validate(payload)


def _recompute_success_identities(payload: dict[str, Any]) -> None:
    run_id = UUID(payload["run_id"])
    attempt_id = derive_attempt_id(run_id, payload["plan_item_id"], payload["attempt"])
    payload["attempt_id"] = attempt_id
    output_text = payload["output_text"]
    assert isinstance(output_text, str)
    output_sha256 = hashlib.sha256(output_text.encode("utf-8")).hexdigest()
    payload["output_sha256"] = output_sha256
    payload["response_id"] = stable_digest(
        "laconian-response-v1",
        {
            "run_id": run_id,
            "plan_item_id": payload["plan_item_id"],
            "attempt_id": attempt_id,
            "case_uid": payload["case_uid"],
            "instruction_sha256": payload["instruction_sha256"],
            "output_sha256": output_sha256,
        },
    )


def success_payload(*, attempt: int = 1) -> dict[str, Any]:
    payload = valid_attempt_payload()
    payload["attempt"] = attempt
    payload["retry_of_attempt"] = None if attempt == 1 else attempt - 1
    _recompute_success_identities(payload)
    return payload


def error_payload(
    *,
    certainty: str,
    retryable: bool,
    terminal: bool,
    terminal_reason: str | None,
    attempt: int = 1,
    kind: str = "temporary",
    backoff_ms: int | None = None,
) -> dict[str, Any]:
    payload = valid_attempt_payload()
    payload.update(
        {
            "attempt": attempt,
            "attempt_id": derive_attempt_id(RUN_ID, "1" * 64, attempt),
            "terminal": terminal,
            "retry_of_attempt": None if attempt == 1 else attempt - 1,
            "backoff_ms": backoff_ms,
            "delivery_certainty": certainty,
            "response_model": "returned-model-v1",
            "output_text": None,
            "output_sha256": None,
            "response_id": None,
            "output_was_redacted": False,
            "output_redaction_count": 0,
            "error": {
                "kind": kind,
                "message": "Temporary failure.",
                "retryable": retryable,
                "request_id": "nested-request-id",
            },
            "terminal_reason": terminal_reason,
        }
    )
    return payload


@pytest.mark.parametrize("field", ["kind", "message", "request_id"])
@pytest.mark.parametrize("value", ["\ud800", 7, " \t"])
def test_nested_attempt_error_strings_reject_surrogates_nonstrings_and_blanks(
    field: str,
    value: object,
) -> None:
    payload = error_payload(
        certainty="response_received",
        retryable=False,
        terminal=True,
        terminal_reason="provider_rejected",
    )
    payload["error"][field] = value

    with pytest.raises(ValidationError):
        RawAttemptV2.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        success_payload(),
        error_payload(
            certainty="definitely_not_sent",
            retryable=True,
            terminal=False,
            terminal_reason=None,
            backoff_ms=100,
        ),
        error_payload(
            certainty="definitely_rejected",
            retryable=True,
            terminal=False,
            terminal_reason=None,
            attempt=2,
            backoff_ms=200,
        ),
        error_payload(
            certainty="definitely_rejected",
            retryable=True,
            terminal=True,
            terminal_reason="retry_exhausted",
        ),
        error_payload(
            certainty="definitely_not_sent",
            retryable=False,
            terminal=True,
            terminal_reason="provider_rejected",
        ),
        error_payload(
            certainty="response_received",
            retryable=True,
            terminal=True,
            terminal_reason="provider_rejected",
        ),
        error_payload(
            certainty="definitely_rejected",
            retryable=True,
            terminal=True,
            terminal_reason="authentication_stopped",
            kind="authentication",
        ),
        error_payload(
            certainty="response_received",
            retryable=False,
            terminal=True,
            terminal_reason="authentication_stopped",
            kind="authentication",
        ),
        error_payload(
            certainty="unknown",
            retryable=True,
            terminal=True,
            terminal_reason="ambiguous_delivery",
        ),
    ],
)
def test_raw_attempt_v2_accepts_every_normalized_truth_table_state(
    payload: dict[str, Any],
) -> None:
    assert RawAttemptV2.model_validate(payload).model_dump(mode="json") == payload


@pytest.mark.parametrize(
    "payload",
    [
        success_payload() | {"terminal": False},
        success_payload() | {"delivery_certainty": "definitely_rejected"},
        success_payload() | {"terminal_reason": "provider_rejected"},
        success_payload() | {"backoff_ms": 100},
        success_payload() | {"response_model": None},
        error_payload(
            certainty="definitely_not_sent",
            retryable=True,
            terminal=False,
            terminal_reason=None,
            backoff_ms=None,
        ),
        error_payload(
            certainty="definitely_not_sent",
            retryable=True,
            terminal=False,
            terminal_reason=None,
            backoff_ms=101,
        ),
        error_payload(
            certainty="response_received",
            retryable=True,
            terminal=False,
            terminal_reason=None,
            backoff_ms=100,
        ),
        error_payload(
            certainty="definitely_rejected",
            retryable=False,
            terminal=False,
            terminal_reason=None,
            backoff_ms=100,
        ),
        error_payload(
            certainty="definitely_rejected",
            retryable=True,
            terminal=False,
            terminal_reason=None,
            kind="authentication",
            backoff_ms=100,
        ),
        error_payload(
            certainty="definitely_rejected",
            retryable=True,
            terminal=True,
            terminal_reason="provider_rejected",
        ),
        error_payload(
            certainty="unknown",
            retryable=False,
            terminal=True,
            terminal_reason="provider_rejected",
        ),
        error_payload(
            certainty="unknown",
            retryable=False,
            terminal=False,
            terminal_reason=None,
            backoff_ms=100,
        ),
        error_payload(
            certainty="definitely_not_sent",
            retryable=False,
            terminal=True,
            terminal_reason="authentication_stopped",
            kind="authentication",
        ),
        error_payload(
            certainty="unknown",
            retryable=False,
            terminal=True,
            terminal_reason="ambiguous_delivery",
            kind="authentication",
        ),
    ],
)
def test_raw_attempt_v2_rejects_forbidden_truth_table_combinations(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        RawAttemptV2.model_validate(payload)


@pytest.mark.parametrize("attempt_number", range(1, 6))
def test_safe_retry_backoff_is_exact_after_attempt_bound(attempt_number: int) -> None:
    payload = error_payload(
        certainty="definitely_rejected",
        retryable=True,
        terminal=False,
        terminal_reason=None,
        attempt=attempt_number,
        backoff_ms=100 * 2 ** (attempt_number - 1),
    )

    assert RawAttemptV2.model_validate(payload).backoff_ms == 100 * 2 ** (attempt_number - 1)


def test_retry_lineage_and_global_attempt_cap_are_enforced_before_backoff() -> None:
    attempt_one = success_payload() | {"retry_of_attempt": 1}
    attempt_two = success_payload(attempt=2) | {"retry_of_attempt": None}
    attempt_six_nonterminal = error_payload(
        certainty="definitely_rejected",
        retryable=True,
        terminal=False,
        terminal_reason=None,
        attempt=6,
        backoff_ms=3200,
    )
    enormous = success_payload()
    enormous["attempt"] = 10**10_000

    for payload in (attempt_one, attempt_two, attempt_six_nonterminal, enormous):
        with pytest.raises(ValidationError):
            RawAttemptV2.model_validate(payload)


def test_error_state_and_usage_are_independent_and_request_ids_need_not_match() -> None:
    payload = error_payload(
        certainty="response_received",
        retryable=False,
        terminal=True,
        terminal_reason="provider_rejected",
    )
    payload["usage"] = usage_payload(
        input_tokens=0,
        output_tokens=None,
        total_tokens=None,
        cached_input_tokens=0,
        availability="partial",
        source="adapter",
    )
    payload["request_id"] = "top-level-request-id"

    attempt = RawAttemptV2.model_validate(payload)
    assert attempt.usage.availability == "partial"
    assert attempt.request_id != attempt.error.request_id  # type: ignore[union-attr]


def response_too_large_payload() -> dict[str, Any]:
    payload = error_payload(
        certainty="response_received",
        retryable=False,
        terminal=True,
        terminal_reason="provider_rejected",
        kind="response_too_large",
    )
    payload["error"]["message"] = "response_too_large"
    payload["output_was_redacted"] = True
    payload["output_redaction_count"] = 2
    payload["discarded_output_byte_length"] = RESOURCE_LIMITS_V1.output_utf8_bytes + 1
    payload["discarded_output_sha256"] = "9" * 64
    return payload


def test_response_too_large_is_the_only_discarded_output_state() -> None:
    payload = response_too_large_payload()
    attempt = RawAttemptV2.model_validate(payload)

    assert attempt.discarded_output_byte_length == RESOURCE_LIMITS_V1.output_utf8_bytes + 1
    assert attempt.discarded_output_sha256 == "9" * 64
    assert attempt.output_was_redacted is True
    assert attempt.output_redaction_count == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(discarded_output_byte_length=None),
        lambda payload: payload.update(discarded_output_sha256=None),
        lambda payload: payload.update(
            discarded_output_byte_length=RESOURCE_LIMITS_V1.output_utf8_bytes
        ),
        lambda payload: payload.update(delivery_certainty="definitely_rejected"),
        lambda payload: payload["error"].update(message="different"),
        lambda payload: payload["error"].update(retryable=True),
    ],
)
def test_response_too_large_rejects_forged_discard_evidence(mutate: Any) -> None:
    payload = response_too_large_payload()
    mutate(payload)

    with pytest.raises(ValidationError):
        RawAttemptV2.model_validate(payload)


def test_other_errors_cannot_disclose_output_redaction_or_discard_evidence() -> None:
    redacted = error_payload(
        certainty="response_received",
        retryable=False,
        terminal=True,
        terminal_reason="provider_rejected",
    )
    redacted.update(output_was_redacted=True, output_redaction_count=1)
    discarded = error_payload(
        certainty="response_received",
        retryable=False,
        terminal=True,
        terminal_reason="provider_rejected",
    )
    discarded.update(discarded_output_byte_length=2_100_000, discarded_output_sha256="9" * 64)

    for payload in (redacted, discarded):
        with pytest.raises(ValidationError):
            RawAttemptV2.model_validate(payload)


NORMALIZATION_PATTERNS = SanitizerPatterns(
    credential_values=("TOP-SECRET",),
    cwd_roots=("/private/build",),
)


def unavailable_provider_usage() -> dict[str, object]:
    return {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cached_input_tokens": None,
        "availability": "unavailable",
        "source": "provider",
        "cache_accounting": "not_reported",
    }


def assert_constant_normalized_error(
    evidence: NormalizedProviderEvidenceV2,
    *,
    kind: str,
    certainty: str,
) -> None:
    assert evidence.delivery_certainty == certainty
    assert evidence.output is None
    assert evidence.usage.model_dump(mode="json") == unavailable_provider_usage()
    assert evidence.error is not None
    assert evidence.error.kind == kind
    assert evidence.error.message == kind
    assert evidence.error.retryable is False


def test_normalized_provider_evidence_is_frozen_slotted_and_preserves_safe_success() -> None:
    result = GenerationResult(
        output_text="Answer TOP-SECRET.",
        usage=TokenUsage(
            input_tokens=4,
            output_tokens=2,
            total_tokens=6,
            cached_input_tokens=0,
        ),
        request_id="req-safe",
        finish_reason="stop",
        response_model="returned-model-v1",
    )

    evidence = normalize_provider_outcome(result, patterns=NORMALIZATION_PATTERNS)

    assert not hasattr(evidence, "__dict__")
    with pytest.raises(FrozenInstanceError):
        evidence.request_id = "forged"  # type: ignore[misc]
    assert evidence.delivery_certainty == "response_received"
    assert evidence.response_model == "returned-model-v1"
    assert evidence.request_id == "req-safe"
    assert evidence.finish_reason == "stop"
    assert evidence.error is None
    assert evidence.output is not None
    assert evidence.output.text == "Answer [REDACTED]."
    assert evidence.output.credential_replacement_count == 1
    assert evidence.output.sha256 == hashlib.sha256(b"Answer [REDACTED].").hexdigest()
    assert evidence.usage.model_dump(mode="json") == {
        "input_tokens": 4,
        "output_tokens": 2,
        "total_tokens": 6,
        "cached_input_tokens": 0,
        "availability": "complete",
        "source": "provider",
        "cache_accounting": "reported",
    }


def test_inline_replay_outcome_flows_through_pure_normalization() -> None:
    provider = ReplayProvider(
        {
            "case-001-en:concise:0": GenerationResult(
                output_text="Replay says TOP-SECRET.",
                response_model="replay-v1",
            )
        }
    )
    outcome = provider.generate(
        GenerationRequest(
            case_id="case-001-en",
            arm="concise",
            repetition=0,
            model="fixture-v1",
            instructions="Be concise.",
            prompt="Prompt",
            max_output_tokens=128,
            temperature=None,
            timeout_seconds=60.0,
        )
    )

    evidence = normalize_provider_outcome(outcome, patterns=NORMALIZATION_PATTERNS)

    assert evidence.output is not None
    assert evidence.output.text == "Replay says [REDACTED]."
    assert evidence.response_model == "replay-v1"
    assert evidence.usage.model_dump(mode="json") == unavailable_provider_usage()
    assert evidence.error is None


def test_safe_provider_error_preserves_metadata_usage_and_sanitizes_diagnostic() -> None:
    error = ProviderError(
        kind="rate_limit",
        message="TOP-SECRET failed at /private/build/job",
        retryable=True,
        request_id="req-safe",
        delivery_certainty="definitely_rejected",
        response_model="returned-model-v1",
        finish_reason="failed",
        usage=TokenUsage(4, 1, 5, None),
    )

    evidence = normalize_provider_outcome(error, patterns=NORMALIZATION_PATTERNS)

    assert evidence.delivery_certainty == "definitely_rejected"
    assert evidence.output is None
    assert evidence.response_model == "returned-model-v1"
    assert evidence.request_id == "req-safe"
    assert evidence.finish_reason == "failed"
    assert evidence.error == AttemptErrorV2(
        kind="rate_limit",
        message="[REDACTED] failed at [CWD]/job",
        retryable=True,
        request_id="req-safe",
    )
    assert evidence.usage.model_dump(mode="json") == {
        "input_tokens": 4,
        "output_tokens": 1,
        "total_tokens": 5,
        "cached_input_tokens": None,
        "availability": "complete",
        "source": "provider",
        "cache_accounting": "not_reported",
    }


@pytest.mark.parametrize("message", [" \t\n", "\ud800", object()])
def test_invalid_or_blank_provider_diagnostic_uses_constant_fallback(message: object) -> None:
    error = ProviderError(
        kind="server_error",
        message=message,  # type: ignore[arg-type]
        retryable=True,
        delivery_certainty="definitely_rejected",
    )

    evidence = normalize_provider_outcome(error, patterns=NORMALIZATION_PATTERNS)

    assert evidence.error is not None
    assert evidence.error.kind == "server_error"
    assert evidence.error.message == "diagnostic sanitization failed"
    assert evidence.error.retryable is True


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("response_model", "TOP-SECRET"),
        ("request_id", "/private/build/request"),
        ("finish_reason", "https://private.example/failure"),
        ("kind", "TOP-SECRET"),
    ],
)
def test_each_unsafe_provider_metadata_field_is_omitted_without_rewriting(
    field: str,
    unsafe_value: str,
) -> None:
    values: dict[str, object] = {
        "kind": "server_error",
        "message": "Public failure.",
        "retryable": True,
        "request_id": "req-safe",
        "delivery_certainty": "definitely_rejected",
        "response_model": "returned-model-v1",
        "finish_reason": "failed",
    }
    values[field] = unsafe_value
    error = ProviderError(**values)  # type: ignore[arg-type]

    evidence = normalize_provider_outcome(error, patterns=NORMALIZATION_PATTERNS)

    assert evidence.delivery_certainty == "definitely_rejected"
    assert evidence.output is None
    assert evidence.error is not None
    assert evidence.error.kind == "unsafe_provider_metadata"
    assert evidence.error.message == "unsafe_provider_metadata"
    assert evidence.error.retryable is False
    assert evidence.response_model == (None if field == "response_model" else "returned-model-v1")
    assert evidence.request_id == (None if field == "request_id" else "req-safe")
    assert evidence.finish_reason == (None if field == "finish_reason" else "failed")
    assert evidence.error.request_id == evidence.request_id
    assert unsafe_value not in repr(evidence)


def test_all_unsafe_success_metadata_is_omitted_and_output_is_not_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = GenerationResult(
        output_text="TOP-SECRET output must not be hashed",
        request_id="/private/build/request",
        finish_reason="https://private.example/done",
        response_model="TOP-SECRET",
    )

    def fail_if_called(value: str, *, patterns: SanitizerPatterns) -> SanitizedOutput:
        raise AssertionError("unsafe metadata must be rejected before output sanitization")

    monkeypatch.setattr(attempts_module, "sanitize_output", fail_if_called)
    evidence = normalize_provider_outcome(result, patterns=NORMALIZATION_PATTERNS)

    assert_constant_normalized_error(
        evidence,
        kind="unsafe_provider_metadata",
        certainty="response_received",
    )
    assert evidence.response_model is None
    assert evidence.request_id is None
    assert evidence.finish_reason is None
    assert "TOP-SECRET" not in repr(evidence)
    assert "/private/build" not in repr(evidence)


@pytest.mark.parametrize(
    "result",
    [
        GenerationResult(output_text="", response_model="returned-model-v1"),
        GenerationResult(output_text=" \t", response_model="returned-model-v1"),
        GenerationResult(output_text="\ud800", response_model="returned-model-v1"),
        GenerationResult(output_text="valid", response_model=None),
    ],
)
def test_invalid_success_output_or_missing_model_becomes_constant_malformed_response(
    result: GenerationResult,
) -> None:
    evidence = normalize_provider_outcome(result, patterns=NORMALIZATION_PATTERNS)

    assert_constant_normalized_error(
        evidence,
        kind="malformed_response",
        certainty="response_received",
    )


def test_invalid_evidence_is_rejected_before_output_sanitization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = (
        GenerationResult(output_text="TOP-SECRET", response_model=None),
        GenerationResult(
            output_text="TOP-SECRET",
            response_model="returned-model-v1",
            usage=TokenUsage(True, 1, 2),
        ),
    )

    def fail_if_called(value: str, *, patterns: SanitizerPatterns) -> SanitizedOutput:
        raise AssertionError("malformed evidence must be rejected before output sanitization")

    monkeypatch.setattr(attempts_module, "sanitize_output", fail_if_called)
    for outcome in outcomes:
        evidence = normalize_provider_outcome(outcome, patterns=NORMALIZATION_PATTERNS)
        assert_constant_normalized_error(
            evidence,
            kind="malformed_response",
            certainty="response_received",
        )


@pytest.mark.parametrize(
    "usage",
    [
        TokenUsage(True, 1, 2),
        TokenUsage(-1, 1, 0),
        TokenUsage(1, 1, 2, 2),
        TokenUsage(1, 1, 3),
    ],
)
@pytest.mark.parametrize("is_error", [False, True], ids=["result", "exception"])
def test_invalid_provider_usage_fails_closed_without_echoing_values(
    usage: TokenUsage,
    is_error: bool,
) -> None:
    if is_error:
        outcome: GenerationResult | ProviderError = ProviderError(
            kind="server_error",
            message="TOP-SECRET /private/build",
            retryable=True,
            delivery_certainty="definitely_rejected",
            response_model="returned-model-v1",
            request_id="req-safe",
            usage=usage,
        )
        expected_certainty = "definitely_rejected"
    else:
        outcome = GenerationResult(
            output_text="TOP-SECRET /private/build",
            response_model="returned-model-v1",
            request_id="req-safe",
            usage=usage,
        )
        expected_certainty = "response_received"

    evidence = normalize_provider_outcome(outcome, patterns=NORMALIZATION_PATTERNS)

    assert_constant_normalized_error(
        evidence,
        kind="malformed_response",
        certainty=expected_certainty,
    )
    assert evidence.response_model == "returned-model-v1"
    assert evidence.request_id == "req-safe"
    assert "TOP-SECRET" not in repr(evidence)
    assert "/private/build" not in repr(evidence)


def test_oversized_post_redaction_output_retains_only_discard_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized = SanitizedOutput(
        text=None,
        byte_length=RESOURCE_LIMITS_V1.output_utf8_bytes + 1,
        sha256="9" * 64,
        credential_replacement_count=2,
    )
    monkeypatch.setattr(
        attempts_module,
        "sanitize_output",
        lambda value, *, patterns: oversized,
    )
    result = GenerationResult(
        output_text="provider bytes",
        response_model="returned-model-v1",
        request_id="req-safe",
        finish_reason="length",
    )

    evidence = normalize_provider_outcome(result, patterns=NORMALIZATION_PATTERNS)

    assert evidence.delivery_certainty == "response_received"
    assert evidence.output == oversized
    assert evidence.error == AttemptErrorV2(
        kind="response_too_large",
        message="response_too_large",
        retryable=False,
        request_id="req-safe",
    )

    payload = error_payload(
        certainty="response_received",
        retryable=False,
        terminal=True,
        terminal_reason="provider_rejected",
        kind="response_too_large",
    )
    payload.update(
        response_model=evidence.response_model,
        request_id=evidence.request_id,
        finish_reason=evidence.finish_reason,
        usage=evidence.usage.model_dump(mode="json"),
        error=evidence.error.model_dump(mode="json"),
        output_was_redacted=evidence.output.was_redacted,
        output_redaction_count=evidence.output.credential_replacement_count,
        discarded_output_byte_length=evidence.output.byte_length,
        discarded_output_sha256=evidence.output.sha256,
    )
    assert RawAttemptV2.model_validate(payload).discarded_output_sha256 == "9" * 64


@pytest.mark.parametrize("certainty", ["unknown", "definitely_not_sent"])
def test_contradictory_authentication_evidence_becomes_constant_ambiguity(
    certainty: str,
) -> None:
    error = ProviderError(
        kind="authentication",
        message="TOP-SECRET auth diagnostic",
        retryable=True,
        request_id="req-safe",
        delivery_certainty=certainty,  # type: ignore[arg-type]
        response_model="returned-model-v1",
        finish_reason="failed",
        usage=TokenUsage(2, 1, 3),
    )

    evidence = normalize_provider_outcome(error, patterns=NORMALIZATION_PATTERNS)

    assert evidence.delivery_certainty == "unknown"
    assert evidence.output is None
    assert evidence.response_model == "returned-model-v1"
    assert evidence.request_id == "req-safe"
    assert evidence.finish_reason == "failed"
    assert evidence.usage.availability == "complete"
    assert evidence.error == AttemptErrorV2(
        kind="ambiguous_auth_delivery",
        message="ambiguous_auth_delivery",
        retryable=False,
        request_id="req-safe",
    )
    assert "TOP-SECRET" not in repr(evidence)


def test_valid_authentication_preserves_raw_retryable_flag() -> None:
    error = ProviderError(
        kind="authentication",
        message="Authentication rejected.",
        retryable=True,
        delivery_certainty="definitely_rejected",
    )

    evidence = normalize_provider_outcome(error, patterns=NORMALIZATION_PATTERNS)

    assert evidence.delivery_certainty == "definitely_rejected"
    assert evidence.error is not None
    assert evidence.error.kind == "authentication"
    assert evidence.error.retryable is True


@pytest.mark.parametrize(
    "certainty",
    [
        "definitely_not_sent",
        "definitely_rejected",
        "response_received",
        "unknown",
    ],
)
def test_provider_response_too_large_kind_collision_fails_closed(
    certainty: str,
) -> None:
    error = ProviderError(
        kind="response_too_large",
        message="TOP-SECRET forged discard evidence",
        retryable=True,
        request_id="req-safe",
        delivery_certainty=certainty,  # type: ignore[arg-type]
        response_model="returned-model-v1",
        finish_reason="failed",
        usage=TokenUsage(4, 1, 5, 0),
    )

    evidence = normalize_provider_outcome(error, patterns=NORMALIZATION_PATTERNS)

    assert evidence.delivery_certainty == certainty
    assert evidence.output is None
    assert evidence.response_model == "returned-model-v1"
    assert evidence.request_id == "req-safe"
    assert evidence.finish_reason == "failed"
    assert evidence.usage.model_dump(mode="json") == {
        "input_tokens": 4,
        "output_tokens": 1,
        "total_tokens": 5,
        "cached_input_tokens": 0,
        "availability": "complete",
        "source": "provider",
        "cache_accounting": "reported",
    }
    assert evidence.error == AttemptErrorV2(
        kind="malformed_response",
        message="malformed_response",
        retryable=False,
        request_id="req-safe",
    )
    assert "TOP-SECRET" not in repr(evidence)


def test_forged_outcome_type_invalid_retryable_and_invalid_certainty_never_raise_or_leak() -> None:
    invalid_retryable = ProviderError(
        kind="server_error",
        message="TOP-SECRET /private/build",
        retryable=True,
        delivery_certainty="definitely_rejected",
    )
    object.__setattr__(invalid_retryable, "_retryable", 1)
    invalid_exception_certainty = ProviderError(
        kind="server_error",
        message="TOP-SECRET /private/build",
        retryable=True,
        delivery_certainty="definitely_rejected",
    )
    object.__setattr__(invalid_exception_certainty, "_delivery_certainty", "forged")
    invalid_result_certainty = GenerationResult(
        output_text="TOP-SECRET /private/build",
        response_model="returned-model-v1",
    )
    object.__setattr__(invalid_result_certainty, "delivery_certainty", "forged")

    cases = (
        (object(), "unknown"),
        (invalid_retryable, "definitely_rejected"),
        (invalid_exception_certainty, "unknown"),
        (invalid_result_certainty, "response_received"),
    )
    for outcome, expected_certainty in cases:
        evidence = normalize_provider_outcome(
            cast(GenerationResult | ProviderError, outcome),
            patterns=NORMALIZATION_PATTERNS,
        )
        assert_constant_normalized_error(
            evidence,
            kind="malformed_response",
            certainty=expected_certainty,
        )
        assert "TOP-SECRET" not in repr(evidence)
        assert "/private/build" not in repr(evidence)


_RAW_RESPONSE_PATHS: tuple[attempts_module.PublicBenchmarkRawResponsePathV1, ...] = (
    "response.id",
    "response.status",
    "response.error",
    "response.output",
    "response.model",
    "response.service_tier",
    "response.prompt_cache_options.mode",
    "response.prompt_cache_options.ttl",
    "response.usage.input_tokens",
    "response.usage.input_tokens_details.cached_tokens",
    "response.usage.input_tokens_details.cache_write_tokens",
    "response.usage.output_tokens",
    "response.usage.output_tokens_details.reasoning_tokens",
    "response.usage.total_tokens",
)


def _benchmark_usage(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "input_tokens": 5,
        "output_tokens": 2,
        "total_tokens": 7,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "ordinary_uncached_input_tokens": 5,
        "reasoning_tokens": 1,
        "availability": "complete",
        "source": "provider",
        "cache_read_status": "reported_zero",
        "cache_write_status": "reported_zero",
        "reasoning_token_accounting": "reported",
    }
    payload.update(overrides)
    return payload


def _benchmark_raw_source(
    *,
    overrides: dict[str, tuple[bool, object]] | None = None,
) -> Any:
    values: tuple[object, ...] = (
        "resp_1",
        "completed",
        None,
        [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Answer TOP-SECRET."},
                ],
            }
        ],
        "gpt-5.6-sol-2026-08-01",
        "default",
        "explicit",
        "30m",
        5,
        0,
        0,
        2,
        1,
        7,
    )
    entry_type = attempts_module.PublicBenchmarkRawResponseSourceEntryV1
    source_type = attempts_module.PublicBenchmarkRawResponseSourceV1
    selected = overrides or {}
    return source_type(
        schema_version="PublicBenchmarkRawResponseSourceV1",
        entries=tuple(
            entry_type(
                path=path,
                present=selected.get(path, (True, value))[0],
                value=selected.get(path, (True, value))[1],
            )
            for path, value in zip(_RAW_RESPONSE_PATHS, values, strict=True)
        ),
    )


def _benchmark_response_payload() -> dict[str, object]:
    source = _benchmark_raw_source()
    digest = attempts_module.public_benchmark_raw_response_sha256(source)
    return {
        "schema_version": "public-benchmark-response-evidence-v1",
        "response_id": "resp_1",
        "raw_response_sha256": digest,
        "output_text": "Answer TOP-SECRET.",
        "raw_response_source": source,
        "usage": _benchmark_usage(),
        "requested_model_id": "gpt-5.6-sol",
        "returned_model_id": "gpt-5.6-sol-2026-08-01",
        "returned_model_source_sha256": digest,
        "requested_service_tier": "default",
        "returned_service_tier": "default",
        "service_tier_status": "reported_default",
        "service_tier_source_sha256": digest,
        "applied_prompt_cache_mode": "explicit",
        "applied_prompt_cache_ttl": "30m",
        "applied_cache_control_status": "reported_exact",
        "applied_cache_control_source_sha256": digest,
        "cache_read_source_sha256": digest,
        "cache_write_source_sha256": digest,
        "usage_source_sha256": digest,
        "reasoning_tokens_source_sha256": digest,
    }


def _benchmark_response_payload_for_source(
    source: Any,
    *,
    response_id: str = "resp_1",
    output_text: str = "Answer TOP-SECRET.",
    returned_model_id: str | None = "gpt-5.6-sol-2026-08-01",
    returned_service_tier: str | None = "default",
    service_tier_status: str = "reported_default",
    applied_prompt_cache_mode: str | None = "explicit",
    applied_prompt_cache_ttl: str | None = "30m",
    applied_cache_control_status: str = "reported_exact",
    usage: dict[str, object] | None = None,
) -> dict[str, object]:
    digest = attempts_module.public_benchmark_raw_response_sha256(source)
    payload = _benchmark_response_payload()
    payload.update(
        {
            "response_id": response_id,
            "raw_response_sha256": digest,
            "output_text": output_text,
            "raw_response_source": source,
            "usage": usage or _benchmark_usage(),
            "returned_model_id": returned_model_id,
            "returned_service_tier": returned_service_tier,
            "service_tier_status": service_tier_status,
            "applied_prompt_cache_mode": applied_prompt_cache_mode,
            "applied_prompt_cache_ttl": applied_prompt_cache_ttl,
            "applied_cache_control_status": applied_cache_control_status,
        }
    )
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        payload[field] = digest
    return payload


_EVIDENCE_SOURCE_DIGEST_FIELDS = (
    "returned_model_source_sha256",
    "service_tier_source_sha256",
    "applied_cache_control_source_sha256",
    "cache_read_source_sha256",
    "cache_write_source_sha256",
    "usage_source_sha256",
    "reasoning_tokens_source_sha256",
)


def _benchmark_error_payload(
    *,
    certainty: str = "definitely_rejected",
    structured_status: int | None = 429,
    with_source: bool = False,
) -> dict[str, object]:
    source = _benchmark_raw_source() if with_source else None
    if source is not None:
        source_payload = source.model_dump(mode="python")
        source_entries = list(source_payload["entries"])
        source_entries[1] = source_entries[1] | {"value": "failed"}
        source_entries[2] = source_entries[2] | {
            "value": {"code": "server_error", "message": "failed"}
        }
        source_entries[3] = source_entries[3] | {"value": []}
        source = attempts_module.PublicBenchmarkRawResponseSourceV1.model_validate(
            source_payload | {"entries": source_entries}
        )
    raw_digest = (
        attempts_module.public_benchmark_raw_response_sha256(source) if source is not None else None
    )
    if certainty == "definitely_not_sent":
        not_applicable = "not_applicable_definitely_not_sent"
    elif certainty == "definitely_rejected":
        not_applicable = "not_applicable_definitely_rejected"
    else:
        not_applicable = "missing"
    payload: dict[str, object] = {
        "schema_version": "public-benchmark-provider-error-evidence-v1",
        "delivery_certainty": certainty,
        "provider_request_id": "req_1" if certainty != "definitely_not_sent" else None,
        "response_id": "resp_1" if with_source else None,
        "raw_response_sha256": raw_digest,
        "raw_response_source": source,
        "usage": (
            _benchmark_usage()
            if with_source
            else _benchmark_usage(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cache_read_tokens=None,
                cache_write_tokens=None,
                ordinary_uncached_input_tokens=None,
                reasoning_tokens=None,
                availability="unavailable",
                cache_read_status=not_applicable,
                cache_write_status=not_applicable,
                reasoning_token_accounting="not_reported",
            )
        ),
        "requested_model_id": "gpt-5.6-sol",
        "returned_model_id": "gpt-5.6-sol-2026-08-01" if with_source else None,
        "returned_model_source_sha256": "0" * 64,
        "requested_service_tier": "default",
        "returned_service_tier": "default" if with_source else None,
        "service_tier_status": "reported_default" if with_source else not_applicable,
        "service_tier_source_sha256": "0" * 64,
        "applied_prompt_cache_mode": "explicit" if with_source else None,
        "applied_prompt_cache_ttl": "30m" if with_source else None,
        "applied_cache_control_status": "reported_exact" if with_source else not_applicable,
        "applied_cache_control_source_sha256": "0" * 64,
        "cache_read_source_sha256": "0" * 64,
        "cache_write_source_sha256": "0" * 64,
        "usage_source_sha256": "0" * 64,
        "reasoning_tokens_source_sha256": "0" * 64,
        "structured_status": structured_status,
        "error_source_sha256": "0" * 64,
    }
    error_digest = attempts_module.public_benchmark_provider_error_source_sha256(payload)
    payload["error_source_sha256"] = error_digest
    common_digest = raw_digest or error_digest
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        payload[field] = common_digest
    return payload


def _rebind_benchmark_error_payload_digests(
    payload: dict[str, object],
) -> dict[str, object]:
    payload["error_source_sha256"] = "0" * 64
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        payload[field] = "0" * 64
    error_digest = attempts_module.public_benchmark_provider_error_source_sha256(payload)
    payload["error_source_sha256"] = error_digest
    raw_digest = payload["raw_response_sha256"]
    common_digest = raw_digest if raw_digest is not None else error_digest
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        payload[field] = common_digest
    return payload


def _benchmark_projection_failure_payload() -> dict[str, object]:
    payload = _benchmark_error_payload(
        certainty="response_received",
        structured_status=None,
    )
    payload.update(
        {
            "usage": _benchmark_usage(
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                cache_read_tokens=None,
                cache_write_tokens=None,
                ordinary_uncached_input_tokens=None,
                reasoning_tokens=None,
                availability="unavailable",
                cache_read_status="invalid",
                cache_write_status="invalid",
                reasoning_token_accounting="invalid",
            ),
            "service_tier_status": "missing",
            "applied_cache_control_status": "invalid",
        }
    )
    return _rebind_benchmark_error_payload_digests(payload)


def _benchmark_received_error_payload_for_source(
    source: Any,
    *,
    response_id: str | None,
    returned_model_id: str | None,
    returned_service_tier: str | None,
    service_tier_status: str,
    applied_prompt_cache_mode: str | None,
    applied_prompt_cache_ttl: str | None,
    applied_cache_control_status: str,
    provider_request_id: str | None = "req_1",
    usage: dict[str, object] | None = None,
) -> dict[str, object]:
    digest = attempts_module.public_benchmark_raw_response_sha256(source)
    payload = _benchmark_error_payload(
        with_source=True,
        certainty="response_received",
        structured_status=None,
    )
    payload.update(
        {
            "provider_request_id": provider_request_id,
            "response_id": response_id,
            "raw_response_source": source,
            "raw_response_sha256": digest,
            "usage": usage or _benchmark_usage(),
            "returned_model_id": returned_model_id,
            "returned_service_tier": returned_service_tier,
            "service_tier_status": service_tier_status,
            "applied_prompt_cache_mode": applied_prompt_cache_mode,
            "applied_prompt_cache_ttl": applied_prompt_cache_ttl,
            "applied_cache_control_status": applied_cache_control_status,
        }
    )
    return _rebind_benchmark_error_payload_digests(payload)


def test_benchmark_status_aliases_and_token_usage_are_base_owned_and_exact() -> None:
    assert get_args(provider_base.ReasoningTokenAccounting) == (
        "reported",
        "not_reported",
        "invalid",
    )
    assert get_args(provider_base.ServiceTierStatus) == (
        "reported_default",
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
        "missing",
        "mismatch",
    )
    assert get_args(provider_base.AppliedCacheControlStatus) == (
        "reported_exact",
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
        "missing",
        "mismatch",
        "invalid",
    )
    cache_statuses = (
        "reported_zero",
        "reported_nonzero",
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
        "missing",
        "invalid",
    )
    assert get_args(provider_base.CacheReadStatus) == cache_statuses
    assert get_args(provider_base.CacheWriteStatus) == cache_statuses

    usage = provider_base.TokenUsage(
        5,
        2,
        7,
        cache_read_tokens=1,
        cache_write_tokens=2,
        reasoning_tokens=1,
        reasoning_token_accounting="reported",
    )
    assert usage.cache_read_tokens == 1
    assert usage.cache_write_tokens == 2
    assert usage.reasoning_tokens == 1
    assert usage.reasoning_token_accounting == "reported"


@pytest.mark.parametrize(
    ("reasoning_tokens", "accounting", "expected"),
    [
        (7, "reported", 13),
        (0, "reported", 20),
        (None, "not_reported", None),
        (None, "invalid", None),
    ],
)
def test_visible_output_tokens_require_valid_reasoning_breakdown(
    reasoning_tokens: int | None,
    accounting: provider_base.ReasoningTokenAccounting,
    expected: int | None,
) -> None:
    usage = attempts_module.AttemptUsageV2(
        input_tokens=5,
        output_tokens=20,
        total_tokens=25,
        cache_read_tokens=0,
        cache_write_tokens=0,
        ordinary_uncached_input_tokens=5,
        reasoning_tokens=reasoning_tokens,
        availability="complete",
        source="provider",
        cache_read_status="reported_zero",
        cache_write_status="reported_zero",
        reasoning_token_accounting=accounting,
    )
    assert attempts_module.visible_output_tokens(usage) == expected


def test_attempt_usage_tracks_cache_reads_and_writes_independently() -> None:
    accepted = (
        _benchmark_usage(),
        _benchmark_usage(
            cache_read_tokens=2,
            ordinary_uncached_input_tokens=3,
            cache_read_status="reported_nonzero",
        ),
        _benchmark_usage(
            cache_write_tokens=2,
            ordinary_uncached_input_tokens=3,
            cache_write_status="reported_nonzero",
        ),
        _benchmark_usage(
            cache_write_tokens=None,
            ordinary_uncached_input_tokens=5,
            cache_write_status="missing",
        ),
    )
    for payload in accepted:
        usage = attempts_module.AttemptUsageV2.model_validate(payload)
        assert usage.model_dump(mode="json") == payload

    invalid = (
        _benchmark_usage(cache_read_tokens=None, cache_read_status="reported_zero"),
        _benchmark_usage(cache_write_tokens=1, cache_write_status="missing"),
        _benchmark_usage(cache_read_tokens=6, ordinary_uncached_input_tokens=0),
        _benchmark_usage(cache_write_tokens=6, ordinary_uncached_input_tokens=0),
        _benchmark_usage(
            cache_read_tokens=3,
            cache_write_tokens=3,
            ordinary_uncached_input_tokens=0,
            cache_read_status="reported_nonzero",
            cache_write_status="reported_nonzero",
        ),
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            attempts_module.AttemptUsageV2.model_validate(payload)

    nonzero_write = attempts_module.AttemptUsageV2.model_validate(accepted[2])
    round_trip = attempts_module.AttemptUsageV2.model_validate_json(
        canonical_json(nonzero_write.model_dump(mode="json"))
    )
    assert round_trip.cache_write_tokens == 2
    assert canonical_json(round_trip.model_dump(mode="json")) == canonical_json(accepted[2])


def test_output_string_is_exact_bounded_ephemeral_text() -> None:
    adapter = TypeAdapter(attempts_module.OutputString)
    boundary = "x" * RESOURCE_LIMITS_V1.output_utf8_bytes
    control_and_non_nfc = "A\x00e\u0301"

    assert adapter.validate_python(boundary) is boundary
    assert adapter.validate_python(control_and_non_nfc) == control_and_non_nfc

    class TextSubclass(str):
        pass

    for rejected in (
        TextSubclass("text"),
        b"text",
        True,
        object(),
        " \t\n",
        "\ud800",
        boundary + "x",
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(rejected)


def test_raw_response_source_projection_is_exact_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SDKError(BaseModel):
        code: str
        message: str

    class SDKProjectionFailure(BaseModel):
        value: object

    sdk_error = SDKError(code="server_error", message="failed")
    output_tree = [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "Answer TOP-SECRET."}],
        }
    ]
    source = _benchmark_raw_source(
        overrides={
            "response.error": (True, sdk_error),
            "response.output": (True, output_tree),
        }
    )
    source_type = attempts_module.PublicBenchmarkRawResponseSourceV1
    assert type(source) is source_type
    assert tuple(entry.path for entry in source.entries) == _RAW_RESPONSE_PATHS
    assert source.entries[2].value == {"code": "server_error", "message": "failed"}
    assert source.entries[3].value == output_tree
    assert type(source.entries[2].value) is dict
    assert type(source.entries[3].value) is list
    exact_json_projection = source.model_dump(mode="json")
    assert attempts_module.public_benchmark_raw_response_sha256(source) == stable_digest(
        "laconian-public-benchmark-raw-response-source-v1",
        exact_json_projection,
    )
    with pytest.raises(ValueError):
        attempts_module.public_benchmark_raw_response_sha256(cast(Any, exact_json_projection))

    explicit_null = _benchmark_raw_source()
    missing = _benchmark_raw_source(overrides={"response.error": (False, None)})
    assert explicit_null.entries[2].present is True
    assert explicit_null.entries[2].value is None
    assert missing.entries[2].present is False
    assert missing.entries[2].value is None
    assert explicit_null.model_dump(mode="json") != missing.model_dump(mode="json")
    assert attempts_module.public_benchmark_raw_response_sha256(
        explicit_null
    ) != attempts_module.public_benchmark_raw_response_sha256(missing)

    dumped = source.model_dump(mode="python")
    entries = list(dumped["entries"])

    cyclic: list[object] = []
    cyclic.append(cyclic)
    too_deep: object = "leaf"
    for _ in range(RESOURCE_LIMITS_V1.nesting_depth + 2):
        too_deep = [too_deep]
    unsupported_values = (
        object(),
        b"not-json",
        {1: "non-string-key"},
        float("nan"),
        float("inf"),
        SDKProjectionFailure(value=object()),
        cyclic,
        too_deep,
    )
    for unsupported in unsupported_values:
        forged_entries = list(entries)
        forged_entries[5] = forged_entries[5] | {"value": unsupported}
        with pytest.raises(ValidationError):
            source_type.model_validate(dumped | {"entries": forged_entries})

    forged = source_type.model_construct(
        schema_version="PublicBenchmarkRawResponseSourceV1",
        entries=source.entries[:-1],
    )
    with pytest.raises(ValidationError):
        attempts_module.public_benchmark_raw_response_sha256(forged)

    encoded_size = len(canonical_json(exact_json_projection))
    monkeypatch.setattr(
        attempts_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, raw_jsonl_row_bytes=encoded_size - 1),
    )
    with pytest.raises(ValidationError):
        source_type.model_validate(exact_json_projection)


@pytest.mark.parametrize("ordinal", range(len(_RAW_RESPONSE_PATHS)))
@pytest.mark.parametrize(
    "mutation",
    ("remove", "duplicate", "rename", "reorder", "malformed_presence"),
)
def test_raw_response_source_rejects_each_structural_entry_mutation(
    ordinal: int,
    mutation: str,
) -> None:
    source_type = attempts_module.PublicBenchmarkRawResponseSourceV1
    dumped = _benchmark_raw_source().model_dump(mode="python")
    original_entries = list(dumped["entries"])
    mutated_entries = list(original_entries)

    if mutation == "remove":
        mutated_entries.pop(ordinal)
    elif mutation == "duplicate":
        mutated_entries.insert(ordinal, dict(mutated_entries[ordinal]))
    elif mutation == "rename":
        mutated_entries[ordinal] = mutated_entries[ordinal] | {"path": "response.output_text"}
    elif mutation == "reorder":
        moved = mutated_entries.pop(ordinal)
        destination = len(mutated_entries) if ordinal == 0 else 0
        mutated_entries.insert(destination, moved)
        assert mutated_entries != original_entries
    else:
        mutated_entries[ordinal] = mutated_entries[ordinal] | {
            "present": False,
            "value": f"malformed-presence-{ordinal}",
        }

    with pytest.raises(ValidationError):
        source_type.model_validate(dumped | {"entries": mutated_entries})


@pytest.mark.parametrize(
    ("status", "error"),
    (
        ("failed", {"code": "server_error", "message": "failed"}),
        ("incomplete", None),
        (True, None),
        ("completed", {"code": "server_error", "message": "failed"}),
    ),
)
def test_benchmark_response_evidence_rejects_provider_error_variant_sources(
    status: object,
    error: object,
) -> None:
    source = _benchmark_raw_source(
        overrides={
            "response.status": (True, status),
            "response.error": (True, error),
        }
    )

    with pytest.raises(ValidationError):
        attempts_module.PublicBenchmarkResponseEvidenceV1.model_validate(
            _benchmark_response_payload_for_source(source)
        )

    absent_error_source = _benchmark_raw_source(overrides={"response.error": (False, None)})
    accepted = attempts_module.PublicBenchmarkResponseEvidenceV1.model_validate(
        _benchmark_response_payload_for_source(absent_error_source)
    )
    assert accepted.output_text == "Answer TOP-SECRET."


def test_benchmark_provider_error_evidence_rejects_usable_success_source_only() -> None:
    error_type = attempts_module.PublicBenchmarkProviderErrorEvidenceV1
    for error_presence in (True, False):
        source = _benchmark_raw_source(overrides={"response.error": (error_presence, None)})
        with pytest.raises(ValidationError):
            error_type.model_validate(
                _benchmark_received_error_payload_for_source(
                    source,
                    response_id="resp_1",
                    returned_model_id="gpt-5.6-sol-2026-08-01",
                    returned_service_tier="default",
                    service_tier_status="reported_default",
                    applied_prompt_cache_mode="explicit",
                    applied_prompt_cache_ttl="30m",
                    applied_cache_control_status="reported_exact",
                )
            )

    accepted_sources = (
        _benchmark_raw_source(
            overrides={"response.output": (False, None)},
        ),
        _benchmark_raw_source(
            overrides={"response.output": (True, [])},
        ),
        _benchmark_raw_source(
            overrides={"response.status": (True, "failed")},
        ),
        _benchmark_raw_source(
            overrides={
                "response.error": (
                    True,
                    {"code": "server_error", "message": "failed"},
                )
            },
        ),
        _benchmark_raw_source(
            overrides={"response.status": (True, "incomplete")},
        ),
    )
    for source in accepted_sources:
        accepted = error_type.model_validate(
            _benchmark_received_error_payload_for_source(
                source,
                response_id="resp_1",
                returned_model_id="gpt-5.6-sol-2026-08-01",
                returned_service_tier="default",
                service_tier_status="reported_default",
                applied_prompt_cache_mode="explicit",
                applied_prompt_cache_ttl="30m",
                applied_cache_control_status="reported_exact",
            )
        )
        assert accepted.delivery_certainty == "response_received"

    missing_id_source = _benchmark_raw_source(
        overrides={"response.id": (False, None)},
    )
    missing_id = error_type.model_validate(
        _benchmark_received_error_payload_for_source(
            missing_id_source,
            response_id=None,
            returned_model_id="gpt-5.6-sol-2026-08-01",
            returned_service_tier="default",
            service_tier_status="reported_default",
            applied_prompt_cache_mode="explicit",
            applied_prompt_cache_ttl="30m",
            applied_cache_control_status="reported_exact",
        )
    )
    assert missing_id.raw_response_source is not None
    assert missing_id.usage.availability == "complete"


def test_benchmark_evidence_source_digests_are_one_envelope() -> None:
    response_type = attempts_module.PublicBenchmarkResponseEvidenceV1
    error_type = attempts_module.PublicBenchmarkProviderErrorEvidenceV1
    response_payload = _benchmark_response_payload()
    response = response_type.model_validate(response_payload)
    response_source_payload = response.raw_response_source.model_dump(mode="json")
    response_digest = stable_digest(
        "laconian-public-benchmark-raw-response-source-v1",
        response_source_payload,
    )
    assert response.raw_response_sha256 == response_digest
    assert response.raw_response_source.model_dump(mode="json") == response_source_payload
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        assert getattr(response, field) == response_digest
        with pytest.raises(ValidationError):
            response_type.model_validate(response_payload | {field: "f" * 64})

    error_payloads = {
        "received_response_error": _benchmark_error_payload(
            with_source=True,
            certainty="response_received",
            structured_status=None,
        ),
        "projection_failure": _benchmark_projection_failure_payload(),
        "definitely_not_sent": _benchmark_error_payload(
            certainty="definitely_not_sent",
            structured_status=None,
        ),
        "definitely_rejected": _benchmark_error_payload(),
    }
    assert len((response, *error_payloads.values())) == 5

    excluded_fields = {"error_source_sha256", *_EVIDENCE_SOURCE_DIGEST_FIELDS}

    def mutate_included_value(field: str, value: object) -> object:
        if field == "raw_response_source":
            return None if value is not None else {"mutated": True}
        if field == "structured_status":
            return 418 if value != 418 else 419
        if type(value) is dict:
            return {"mutated": True}
        if value is None:
            return "mutated"
        if type(value) is int:
            return value + 1
        return "mutated"

    for vector_name, error_payload in error_payloads.items():
        error = error_type.model_validate(error_payload)
        dumped = error.model_dump(mode="json")
        independently_computed_error_digest = stable_digest(
            "laconian-public-benchmark-provider-error-source-v1",
            {key: value for key, value in dumped.items() if key not in excluded_fields},
        )
        assert error.error_source_sha256 == independently_computed_error_digest

        if vector_name == "received_response_error":
            assert error.raw_response_source is not None
            source_payload = error.raw_response_source.model_dump(mode="json")
            independently_computed_raw_digest = stable_digest(
                "laconian-public-benchmark-raw-response-source-v1",
                source_payload,
            )
            assert error.raw_response_sha256 == independently_computed_raw_digest
            common_digest = independently_computed_raw_digest
        else:
            assert error.raw_response_source is None
            assert error.raw_response_sha256 is None
            common_digest = independently_computed_error_digest

        for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
            assert getattr(error, field) == common_digest
            with pytest.raises(ValidationError):
                error_type.model_validate(error_payload | {field: "f" * 64})

        included_fields = set(error_type.model_fields) - excluded_fields
        for field in included_fields:
            mutated = dict(dumped)
            mutated[field] = mutate_included_value(field, dumped[field])
            assert (
                attempts_module.public_benchmark_provider_error_source_sha256(mutated)
                != independently_computed_error_digest
            )
            with pytest.raises(ValidationError):
                error_type.model_validate(mutated)

        for field in excluded_fields:
            mutated = dict(dumped)
            mutated[field] = "f" * 64
            assert (
                attempts_module.public_benchmark_provider_error_source_sha256(mutated)
                == independently_computed_error_digest
            )
            with pytest.raises(ValidationError):
                error_type.model_validate(mutated)

        for raw_field in ("raw_response_source", "raw_response_sha256"):
            one_sided_pair = dict(dumped)
            one_sided_pair[raw_field] = (
                _benchmark_raw_source().model_dump(mode="json")
                if dumped[raw_field] is None and raw_field == "raw_response_source"
                else "f" * 64
                if dumped[raw_field] is None
                else None
            )
            with pytest.raises(ValidationError):
                error_type.model_validate(one_sided_pair)

    projection_failure = error_type.model_validate(error_payloads["projection_failure"])
    assert projection_failure.delivery_certainty == "response_received"
    assert projection_failure.provider_request_id == "req_1"
    assert projection_failure.response_id is None
    assert projection_failure.returned_model_id is None
    assert projection_failure.returned_service_tier is None
    assert projection_failure.usage.availability == "unavailable"
    assert projection_failure.usage.model_dump(mode="json") == _benchmark_usage(
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        cache_read_tokens=None,
        cache_write_tokens=None,
        ordinary_uncached_input_tokens=None,
        reasoning_tokens=None,
        availability="unavailable",
        cache_read_status="invalid",
        cache_write_status="invalid",
        reasoning_token_accounting="invalid",
    )
    assert projection_failure.service_tier_status == "missing"
    assert projection_failure.applied_cache_control_status == "invalid"
    assert not hasattr(projection_failure, "output_text")

    received_without_source = dict(error_payloads["received_response_error"])
    received_without_source.update(raw_response_source=None, raw_response_sha256=None)
    _rebind_benchmark_error_payload_digests(received_without_source)
    with pytest.raises(ValidationError):
        error_type.model_validate(received_without_source)

    cyclic: list[object] = []
    cyclic.append(cyclic)
    cyclic_payload = dict(error_payloads["projection_failure"])
    cyclic_payload["raw_response_source"] = cyclic
    with pytest.raises(ValueError):
        attempts_module.public_benchmark_provider_error_source_sha256(cyclic_payload)


def _benchmark_attempt_payload(
    *,
    returned_tier: str | None,
    status: str,
) -> dict[str, Any]:
    payload = success_payload()
    digest = "d" * 64
    payload["usage"] = _benchmark_usage()
    payload.update(
        {
            "model": "gpt-5.6-sol",
            "response_model": "gpt-5.6-sol-2026-08-01",
            "requested_model_id": "gpt-5.6-sol",
            "returned_model_id": "gpt-5.6-sol-2026-08-01",
            "returned_model_source_sha256": digest,
            "requested_service_tier": "default",
            "returned_service_tier": returned_tier,
            "service_tier_status": status,
            "service_tier_source_sha256": digest,
            "applied_prompt_cache_mode": "explicit",
            "applied_prompt_cache_ttl": "30m",
            "applied_cache_control_status": "reported_exact",
            "applied_cache_control_source_sha256": digest,
            "cache_read_source_sha256": digest,
            "cache_write_source_sha256": digest,
            "usage_source_sha256": digest,
            "reasoning_tokens_source_sha256": digest,
        }
    )
    return payload


def _benchmark_success_attempt_from_normalized(
    evidence: NormalizedProviderEvidenceV2,
) -> dict[str, Any]:
    assert evidence.output is not None
    assert evidence.output.text is not None
    payload = success_payload()
    payload.update(
        {
            "model": evidence.requested_model_id,
            "response_model": evidence.returned_model_id,
            "requested_model_id": evidence.requested_model_id,
            "returned_model_id": evidence.returned_model_id,
            "returned_model_source_sha256": evidence.returned_model_source_sha256,
            "requested_service_tier": evidence.requested_service_tier,
            "returned_service_tier": evidence.returned_service_tier,
            "service_tier_status": evidence.service_tier_status,
            "service_tier_source_sha256": evidence.service_tier_source_sha256,
            "applied_prompt_cache_mode": evidence.applied_prompt_cache_mode,
            "applied_prompt_cache_ttl": evidence.applied_prompt_cache_ttl,
            "applied_cache_control_status": evidence.applied_cache_control_status,
            "applied_cache_control_source_sha256": (evidence.applied_cache_control_source_sha256),
            "cache_read_source_sha256": evidence.cache_read_source_sha256,
            "cache_write_source_sha256": evidence.cache_write_source_sha256,
            "usage_source_sha256": evidence.usage_source_sha256,
            "reasoning_tokens_source_sha256": evidence.reasoning_tokens_source_sha256,
            "output_text": evidence.output.text,
            "output_was_redacted": evidence.output.was_redacted,
            "output_redaction_count": evidence.output.credential_replacement_count,
            "usage": evidence.usage.model_dump(mode="json"),
            "request_id": evidence.request_id,
            "finish_reason": evidence.finish_reason,
        }
    )
    _recompute_success_identities(payload)
    return payload


def _benchmark_error_attempt_from_normalized(
    evidence: NormalizedProviderEvidenceV2,
) -> dict[str, Any]:
    assert evidence.error is not None
    retryable_delivery = evidence.delivery_certainty in {
        "definitely_not_sent",
        "definitely_rejected",
    }
    if evidence.delivery_certainty == "unknown":
        terminal = True
        terminal_reason = "ambiguous_delivery"
        backoff_ms = None
    elif evidence.error.retryable and retryable_delivery:
        terminal = False
        terminal_reason = None
        backoff_ms = 100
    else:
        terminal = True
        terminal_reason = "provider_rejected"
        backoff_ms = None
    payload = error_payload(
        certainty=evidence.delivery_certainty,
        retryable=evidence.error.retryable,
        terminal=terminal,
        terminal_reason=terminal_reason,
        kind=evidence.error.kind,
        backoff_ms=backoff_ms,
    )
    payload.update(
        {
            "model": evidence.requested_model_id,
            "response_model": evidence.returned_model_id,
            "requested_model_id": evidence.requested_model_id,
            "returned_model_id": evidence.returned_model_id,
            "returned_model_source_sha256": evidence.returned_model_source_sha256,
            "requested_service_tier": evidence.requested_service_tier,
            "returned_service_tier": evidence.returned_service_tier,
            "service_tier_status": evidence.service_tier_status,
            "service_tier_source_sha256": evidence.service_tier_source_sha256,
            "applied_prompt_cache_mode": evidence.applied_prompt_cache_mode,
            "applied_prompt_cache_ttl": evidence.applied_prompt_cache_ttl,
            "applied_cache_control_status": evidence.applied_cache_control_status,
            "applied_cache_control_source_sha256": (evidence.applied_cache_control_source_sha256),
            "cache_read_source_sha256": evidence.cache_read_source_sha256,
            "cache_write_source_sha256": evidence.cache_write_source_sha256,
            "usage_source_sha256": evidence.usage_source_sha256,
            "reasoning_tokens_source_sha256": evidence.reasoning_tokens_source_sha256,
            "usage": evidence.usage.model_dump(mode="json"),
            "request_id": evidence.request_id,
            "finish_reason": evidence.finish_reason,
            "error": evidence.error.model_dump(mode="json"),
        }
    )
    return payload


def test_benchmark_normalization_requires_exact_caller_owned_service_tier() -> None:
    response = attempts_module.PublicBenchmarkResponseEvidenceV1.model_validate(
        _benchmark_response_payload()
    )
    caller_tier = ("default!")[:-1]
    assert type(caller_tier) is str
    assert caller_tier == "default"
    assert caller_tier is not response.requested_service_tier

    normalized = attempts_module.normalize_public_benchmark_outcome(
        response,
        requested_service_tier=caller_tier,
        patterns=NORMALIZATION_PATTERNS,
    )

    assert normalized.requested_service_tier is caller_tier

    class TierSubclass(str):
        pass

    for invalid_tier in ("priority", TierSubclass("default")):
        with pytest.raises(AttemptEvidenceError) as caught:
            attempts_module.normalize_public_benchmark_outcome(
                response,
                requested_service_tier=cast(Any, invalid_tier),
                patterns=NORMALIZATION_PATTERNS,
            )
        assert caught.value.code == "invalid_public_benchmark_evidence"


def test_benchmark_normalization_keeps_in_bound_missing_sanitized_text_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = attempts_module.PublicBenchmarkResponseEvidenceV1.model_validate(
        _benchmark_response_payload()
    )
    incomplete = SanitizedOutput(
        text=None,
        byte_length=RESOURCE_LIMITS_V1.output_utf8_bytes,
        sha256="9" * 64,
        credential_replacement_count=0,
    )
    monkeypatch.setattr(
        attempts_module,
        "sanitize_output",
        lambda value, *, patterns: incomplete,
    )

    normalized = attempts_module.normalize_public_benchmark_outcome(
        response,
        requested_service_tier="default",
        patterns=NORMALIZATION_PATTERNS,
    )

    assert normalized.output is incomplete
    assert normalized.error == AttemptErrorV2(
        kind="malformed_response",
        message="malformed_response",
        retryable=False,
        request_id="resp_1",
    )


def test_raw_attempt_service_tier_matrix_is_strict_and_preserves_billable_evidence() -> None:
    response_type = attempts_module.PublicBenchmarkResponseEvidenceV1
    error_type = attempts_module.PublicBenchmarkProviderErrorEvidenceV1
    valid_received = (
        ("default", "reported_default"),
        ("priority", "mismatch"),
        (None, "missing"),
    )
    normalized_received: dict[str, NormalizedProviderEvidenceV2] = {}
    for returned_tier, status in valid_received:
        source = _benchmark_raw_source(
            overrides={
                "response.service_tier": (
                    returned_tier is not None,
                    returned_tier,
                )
            }
        )
        response = response_type.model_validate(
            _benchmark_response_payload_for_source(
                source,
                returned_service_tier=returned_tier,
                service_tier_status=status,
            )
        )
        normalized = attempts_module.normalize_public_benchmark_outcome(
            response,
            requested_service_tier="default",
            patterns=NORMALIZATION_PATTERNS,
        )
        normalized_received[status] = normalized
        durable = RawAttemptV2.model_validate(
            _benchmark_success_attempt_from_normalized(normalized)
        )
        assert durable.requested_service_tier == "default"
        assert durable.returned_service_tier == returned_tier
        assert durable.service_tier_status == status
        assert durable.delivery_certainty == "response_received"
        assert durable.usage.cache_write_tokens == 0
        assert durable.output_text == "Answer [REDACTED]."
        assert durable.output_sha256 == hashlib.sha256(b"Answer [REDACTED].").hexdigest()
        assert durable.request_id == "resp_1"

        payload = _benchmark_attempt_payload(returned_tier=returned_tier, status=status)
        attempt = attempts_module.RawAttemptV2.model_validate(payload)
        assert attempt.requested_service_tier == "default"
        assert attempt.returned_service_tier == returned_tier
        assert attempt.service_tier_status == status
        assert attempt.usage.cache_write_tokens == 0
        assert attempt.model_dump(mode="json") == payload

    valid_pairs = set(valid_received)
    for returned_tier in ("default", "priority", None):
        for status in ("reported_default", "mismatch", "missing"):
            if (returned_tier, status) in valid_pairs:
                continue
            with pytest.raises(ValidationError):
                attempts_module.RawAttemptV2.model_validate(
                    _benchmark_attempt_payload(returned_tier=returned_tier, status=status)
                )

    response = response_type.model_validate(_benchmark_response_payload())
    forged_response_values = {
        field: getattr(response, field) for field in response_type.model_fields
    }
    forged_response_values["service_tier_status"] = "mismatch"
    adversarial_response = response_type.model_construct(**forged_response_values)
    normalized_adversarial_response = attempts_module.normalize_public_benchmark_outcome(
        adversarial_response,
        requested_service_tier="default",
        patterns=NORMALIZATION_PATTERNS,
    )
    assert normalized_adversarial_response.returned_service_tier == "default"
    assert normalized_adversarial_response.service_tier_status == "reported_default"

    received_error = error_type.model_validate(
        _benchmark_error_payload(
            with_source=True,
            certainty="response_received",
            structured_status=None,
        )
    )
    forged_error_values = {
        field: getattr(received_error, field) for field in error_type.model_fields
    }
    forged_error_values["service_tier_status"] = "mismatch"
    adversarial_error = error_type.model_construct(**forged_error_values)
    normalized_adversarial_error = attempts_module.normalize_public_benchmark_outcome(
        adversarial_error,
        requested_service_tier="default",
        patterns=NORMALIZATION_PATTERNS,
    )
    assert normalized_adversarial_error.returned_service_tier == "default"
    assert normalized_adversarial_error.service_tier_status == "reported_default"

    no_response_vectors = (
        (
            _benchmark_error_payload(
                certainty="definitely_not_sent",
                structured_status=None,
            ),
            "not_applicable_definitely_not_sent",
            None,
            "provider_error",
            False,
        ),
        (
            _benchmark_error_payload(),
            "not_applicable_definitely_rejected",
            "req_1",
            "rate_limit",
            True,
        ),
    )
    durable_no_response: dict[str, dict[str, Any]] = {}
    for (
        evidence_payload,
        expected_status,
        expected_request_id,
        expected_error_kind,
        expected_retryable,
    ) in no_response_vectors:
        evidence = error_type.model_validate(evidence_payload)
        forged_values = {field: getattr(evidence, field) for field in error_type.model_fields}
        forged_values["service_tier_status"] = "missing"
        adversarial = error_type.model_construct(**forged_values)
        normalized = attempts_module.normalize_public_benchmark_outcome(
            adversarial,
            requested_service_tier="default",
            patterns=NORMALIZATION_PATTERNS,
        )
        assert normalized.requested_service_tier == "default"
        assert normalized.returned_service_tier is None
        assert normalized.service_tier_status == expected_status
        assert normalized.usage.availability == "unavailable"
        assert normalized.request_id == expected_request_id
        assert normalized.error is not None
        assert normalized.error.kind == expected_error_kind
        assert normalized.error.retryable is expected_retryable
        assert normalized.error.request_id == expected_request_id

        raw_payload = _benchmark_error_attempt_from_normalized(normalized)
        durable = RawAttemptV2.model_validate(raw_payload)
        durable_no_response[expected_status] = raw_payload
        assert durable.service_tier_status == expected_status
        assert durable.returned_service_tier is None
        assert durable.usage.availability == "unavailable"
        assert durable.request_id == expected_request_id

    assert (
        durable_no_response["not_applicable_definitely_not_sent"]["service_tier_status"]
        != durable_no_response["not_applicable_definitely_rejected"]["service_tier_status"]
    )
    assert durable_no_response["not_applicable_definitely_not_sent"]["terminal"] is True
    assert durable_no_response["not_applicable_definitely_rejected"]["terminal"] is False
    assert durable_no_response["not_applicable_definitely_rejected"]["backoff_ms"] == 100

    unknown_evidence = error_type.model_validate(
        _benchmark_error_payload(certainty="unknown", structured_status=None)
    )
    unknown_normalized = attempts_module.normalize_public_benchmark_outcome(
        unknown_evidence,
        requested_service_tier="default",
        patterns=NORMALIZATION_PATTERNS,
    )
    unknown_payload = _benchmark_error_attempt_from_normalized(unknown_normalized)
    assert RawAttemptV2.model_validate(unknown_payload).service_tier_status == "missing"

    received_payload = _benchmark_attempt_payload(returned_tier=None, status="missing")
    for not_applicable in (
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
    ):
        with pytest.raises(ValidationError):
            RawAttemptV2.model_validate(received_payload | {"service_tier_status": not_applicable})
        with pytest.raises(ValidationError):
            RawAttemptV2.model_validate(unknown_payload | {"service_tier_status": not_applicable})

    invalid_no_response = (
        durable_no_response["not_applicable_definitely_not_sent"]
        | {"service_tier_status": "not_applicable_definitely_rejected"},
        durable_no_response["not_applicable_definitely_rejected"]
        | {"service_tier_status": "not_applicable_definitely_not_sent"},
        durable_no_response["not_applicable_definitely_not_sent"]
        | {"delivery_certainty": "definitely_rejected"},
        durable_no_response["not_applicable_definitely_rejected"]
        | {"delivery_certainty": "definitely_not_sent"},
        durable_no_response["not_applicable_definitely_not_sent"]
        | {"returned_service_tier": "priority"},
        durable_no_response["not_applicable_definitely_not_sent"]
        | {"returned_model_id": "gpt-5.6-sol-returned", "response_model": "gpt-5.6-sol-returned"},
        durable_no_response["not_applicable_definitely_not_sent"]
        | {
            "usage": _benchmark_usage(
                input_tokens=1,
                output_tokens=None,
                total_tokens=None,
                cache_read_tokens=None,
                cache_write_tokens=None,
                ordinary_uncached_input_tokens=1,
                reasoning_tokens=None,
                availability="partial",
                cache_read_status="not_applicable_definitely_not_sent",
                cache_write_status="not_applicable_definitely_not_sent",
                reasoning_token_accounting="not_reported",
            )
        },
    )
    for payload in invalid_no_response:
        with pytest.raises(ValidationError):
            RawAttemptV2.model_validate(payload)

    unknown_with_billable_evidence = dict(unknown_payload)
    unknown_with_billable_evidence.update(
        {
            "response_model": "gpt-5.6-sol-returned",
            "returned_model_id": "gpt-5.6-sol-returned",
            "usage": _benchmark_usage(
                cache_write_tokens=2,
                ordinary_uncached_input_tokens=3,
                cache_write_status="reported_nonzero",
            ),
            "applied_cache_control_status": "invalid",
        }
    )
    unknown_attempt = RawAttemptV2.model_validate(unknown_with_billable_evidence)
    assert unknown_attempt.delivery_certainty == "unknown"
    assert unknown_attempt.service_tier_status == "missing"
    assert unknown_attempt.usage.cache_write_tokens == 2
    assert unknown_attempt.request_id == "req_1"

    discard_payload = response_too_large_payload()
    digest = "d" * 64
    discard_payload.update(
        {
            "model": "gpt-5.6-sol",
            "response_model": "gpt-5.6-sol-returned",
            "requested_model_id": "gpt-5.6-sol",
            "returned_model_id": "gpt-5.6-sol-returned",
            "returned_model_source_sha256": digest,
            "requested_service_tier": "default",
            "returned_service_tier": "priority",
            "service_tier_status": "mismatch",
            "service_tier_source_sha256": digest,
            "applied_prompt_cache_mode": "explicit",
            "applied_prompt_cache_ttl": "30m",
            "applied_cache_control_status": "reported_exact",
            "applied_cache_control_source_sha256": digest,
            "cache_read_source_sha256": digest,
            "cache_write_source_sha256": digest,
            "usage_source_sha256": digest,
            "reasoning_tokens_source_sha256": digest,
            "usage": _benchmark_usage(
                cache_write_tokens=2,
                ordinary_uncached_input_tokens=3,
                cache_write_status="reported_nonzero",
            ),
        }
    )
    discarded = RawAttemptV2.model_validate(discard_payload)
    assert discarded.delivery_certainty == "response_received"
    assert discarded.service_tier_status == "mismatch"
    assert discarded.usage.cache_write_tokens == 2
    assert discarded.discarded_output_byte_length == RESOURCE_LIMITS_V1.output_utf8_bytes + 1
    assert discarded.discarded_output_sha256 == "9" * 64
    assert discarded.request_id == "replay-request-1"

    fail_closed_handoff_statuses = {
        normalized_received["mismatch"].service_tier_status,
        normalized_received["missing"].service_tier_status,
        *durable_no_response,
    }
    assert "reported_default" not in fail_closed_handoff_statuses
    assert fail_closed_handoff_statuses == {
        "mismatch",
        "missing",
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
    }


def test_benchmark_response_normalization_drops_unsafe_metadata_without_losing_evidence() -> None:
    unsafe_response_id = "resp-TOP-SECRET"
    unsafe_model = "model-TOP-SECRET"
    unsafe_tier = "tier-TOP-SECRET"
    unsafe_cache_mode = "/private/build/cache-mode"
    unsafe_cache_ttl = "ttl-TOP-SECRET"
    source = _benchmark_raw_source(
        overrides={
            "response.id": (True, unsafe_response_id),
            "response.model": (True, unsafe_model),
            "response.service_tier": (True, unsafe_tier),
            "response.prompt_cache_options.mode": (True, unsafe_cache_mode),
            "response.prompt_cache_options.ttl": (True, unsafe_cache_ttl),
        }
    )
    raw_digest = attempts_module.public_benchmark_raw_response_sha256(source)
    response = attempts_module.PublicBenchmarkResponseEvidenceV1.model_validate(
        _benchmark_response_payload_for_source(
            source,
            response_id=unsafe_response_id,
            returned_model_id=unsafe_model,
            returned_service_tier=unsafe_tier,
            service_tier_status="mismatch",
            applied_prompt_cache_mode=unsafe_cache_mode,
            applied_prompt_cache_ttl=unsafe_cache_ttl,
            applied_cache_control_status="mismatch",
        )
    )

    normalized = attempts_module.normalize_public_benchmark_outcome(
        response,
        requested_service_tier="default",
        patterns=NORMALIZATION_PATTERNS,
    )

    assert normalized.delivery_certainty == "response_received"
    assert normalized.output is not None
    assert normalized.output.text == "Answer [REDACTED]."
    assert normalized.output.sha256 == hashlib.sha256(b"Answer [REDACTED].").hexdigest()
    assert normalized.usage == response.usage
    assert normalized.request_id is None
    assert normalized.returned_model_id is None
    assert normalized.response_model is None
    assert normalized.returned_service_tier is None
    assert normalized.service_tier_status == "missing"
    assert normalized.applied_prompt_cache_mode is None
    assert normalized.applied_prompt_cache_ttl is None
    assert normalized.applied_cache_control_status == "invalid"
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        assert getattr(normalized, field) == raw_digest
    assert not hasattr(normalized, "raw_response_source")
    assert not hasattr(normalized, "raw_response_sha256")

    durable = RawAttemptV2.model_validate(_benchmark_success_attempt_from_normalized(normalized))
    durable_bytes = raw_attempt_bytes(durable)
    assert durable.output_text == "Answer [REDACTED]."
    assert durable.usage == response.usage
    assert durable.delivery_certainty == "response_received"
    assert durable.returned_model_id is None
    assert durable.returned_service_tier is None
    assert durable.service_tier_status == "missing"
    assert durable.applied_cache_control_status == "invalid"
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        assert getattr(durable, field) == raw_digest
    for unsafe in (
        unsafe_response_id,
        unsafe_model,
        unsafe_tier,
        unsafe_cache_mode,
        unsafe_cache_ttl,
    ):
        assert unsafe not in repr(normalized)
        assert unsafe.encode() not in durable_bytes
    assert b"raw_response_source" not in durable_bytes
    assert b"raw_response_sha256" not in durable_bytes


def test_benchmark_provider_error_normalization_drops_unsafe_metadata() -> None:
    unsafe_response_id = "resp-TOP-SECRET"
    unsafe_request_id = "request-TOP-SECRET-/private/build"
    unsafe_model = "model-TOP-SECRET"
    unsafe_tier = "tier-TOP-SECRET"
    unsafe_cache_mode = "/private/build/cache-mode"
    unsafe_cache_ttl = "ttl-TOP-SECRET"
    source = _benchmark_raw_source(
        overrides={
            "response.id": (True, unsafe_response_id),
            "response.status": (True, "failed"),
            "response.error": (
                True,
                {"code": "server_error", "message": "failed"},
            ),
            "response.output": (True, []),
            "response.model": (True, unsafe_model),
            "response.service_tier": (True, unsafe_tier),
            "response.prompt_cache_options.mode": (True, unsafe_cache_mode),
            "response.prompt_cache_options.ttl": (True, unsafe_cache_ttl),
        }
    )
    raw_digest = attempts_module.public_benchmark_raw_response_sha256(source)
    error = attempts_module.PublicBenchmarkProviderErrorEvidenceV1.model_validate(
        _benchmark_received_error_payload_for_source(
            source,
            response_id=unsafe_response_id,
            returned_model_id=unsafe_model,
            returned_service_tier=unsafe_tier,
            service_tier_status="mismatch",
            applied_prompt_cache_mode=unsafe_cache_mode,
            applied_prompt_cache_ttl=unsafe_cache_ttl,
            applied_cache_control_status="mismatch",
            provider_request_id=unsafe_request_id,
        )
    )

    normalized = attempts_module.normalize_public_benchmark_outcome(
        error,
        requested_service_tier="default",
        patterns=NORMALIZATION_PATTERNS,
    )

    assert normalized.delivery_certainty == "response_received"
    assert normalized.output is None
    assert normalized.usage == error.usage
    assert normalized.request_id is None
    assert normalized.error is not None
    assert normalized.error.request_id is None
    assert normalized.returned_model_id is None
    assert normalized.response_model is None
    assert normalized.returned_service_tier is None
    assert normalized.service_tier_status == "missing"
    assert normalized.applied_prompt_cache_mode is None
    assert normalized.applied_prompt_cache_ttl is None
    assert normalized.applied_cache_control_status == "invalid"
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        assert getattr(normalized, field) == raw_digest
    assert not hasattr(normalized, "raw_response_source")
    assert not hasattr(normalized, "raw_response_sha256")

    durable = RawAttemptV2.model_validate(_benchmark_error_attempt_from_normalized(normalized))
    durable_bytes = raw_attempt_bytes(durable)
    assert durable.delivery_certainty == "response_received"
    assert durable.usage == error.usage
    assert durable.request_id is None
    assert durable.error is not None
    assert durable.error.request_id is None
    assert durable.returned_model_id is None
    assert durable.returned_service_tier is None
    assert durable.service_tier_status == "missing"
    assert durable.applied_cache_control_status == "invalid"
    for field in _EVIDENCE_SOURCE_DIGEST_FIELDS:
        assert getattr(durable, field) == raw_digest
    for unsafe in (
        unsafe_response_id,
        unsafe_request_id,
        unsafe_model,
        unsafe_tier,
        unsafe_cache_mode,
        unsafe_cache_ttl,
    ):
        assert unsafe not in repr(normalized)
        assert unsafe.encode() not in durable_bytes
    assert b"raw_response_source" not in durable_bytes
    assert b"raw_response_sha256" not in durable_bytes


def test_benchmark_normalization_sanitizes_output_and_drops_ephemeral_source_trees() -> None:
    response = attempts_module.PublicBenchmarkResponseEvidenceV1.model_validate(
        _benchmark_response_payload()
    )
    normalized = attempts_module.normalize_public_benchmark_outcome(
        response,
        requested_service_tier="default",
        patterns=NORMALIZATION_PATTERNS,
    )

    assert normalized.output is not None
    assert normalized.output.text == "Answer [REDACTED]."
    assert normalized.requested_model_id == "gpt-5.6-sol"
    assert normalized.returned_model_id == "gpt-5.6-sol-2026-08-01"
    assert normalized.service_tier_status == "reported_default"
    assert not hasattr(normalized, "raw_response_source")
    assert not hasattr(normalized, "raw_response_sha256")
    assert not hasattr(normalized, "output_text")
    assert "TOP-SECRET" not in repr(normalized)
    assert "response.output" not in repr(normalized)

    payload = _benchmark_attempt_payload(
        returned_tier=normalized.returned_service_tier,
        status=normalized.service_tier_status,
    )
    payload.update(
        output_text=normalized.output.text,
        output_sha256=normalized.output.sha256,
        usage=normalized.usage.model_dump(mode="json"),
        requested_model_id=normalized.requested_model_id,
        returned_model_id=normalized.returned_model_id,
        returned_model_source_sha256=normalized.returned_model_source_sha256,
        service_tier_source_sha256=normalized.service_tier_source_sha256,
        applied_prompt_cache_mode=normalized.applied_prompt_cache_mode,
        applied_prompt_cache_ttl=normalized.applied_prompt_cache_ttl,
        applied_cache_control_status=normalized.applied_cache_control_status,
        applied_cache_control_source_sha256=normalized.applied_cache_control_source_sha256,
        cache_read_source_sha256=normalized.cache_read_source_sha256,
        cache_write_source_sha256=normalized.cache_write_source_sha256,
        usage_source_sha256=normalized.usage_source_sha256,
        reasoning_tokens_source_sha256=normalized.reasoning_tokens_source_sha256,
    )
    _recompute_success_identities(payload)
    durable_bytes = attempts_module.raw_attempt_bytes(
        attempts_module.RawAttemptV2.model_validate(payload)
    )
    assert b"TOP-SECRET" not in durable_bytes
    assert b"raw_response_source" not in durable_bytes
    assert b"raw_response_sha256" not in durable_bytes
    assert b"response.output" not in durable_bytes
