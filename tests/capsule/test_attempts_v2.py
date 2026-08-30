from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

import laconian_eval.capsule.attempts as attempts_module
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
        attempt.terminal = False  # type: ignore[misc]
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
            usage=TokenUsage(True, 1, 2),  # type: ignore[arg-type]
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
        TokenUsage(True, 1, 2),  # type: ignore[arg-type]
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
        evidence = normalize_provider_outcome(  # type: ignore[arg-type]
            outcome,
            patterns=NORMALIZATION_PATTERNS,
        )
        assert_constant_normalized_error(
            evidence,
            kind="malformed_response",
            certainty=expected_certainty,
        )
        assert "TOP-SECRET" not in repr(evidence)
        assert "/private/build" not in repr(evidence)
