from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from capsule_helpers import session_environment_v1_payload
from pydantic import ValidationError

import laconian_eval.capsule.events as events_module
from laconian_eval.capsule.events import (
    AuthenticationStoppedEventV1,
    DeliveryAmbiguousEventV1,
    EventError,
    ExecutionBlockedEventV1,
    ExecutionInterruptedEventV1,
    ExecutionStartedEventV1,
    GenerationCompletedEventV1,
    RequestFinishedEventV1,
    RequestStartedEventV1,
    SealRequestedEventV1,
    TailRecoveredEventV1,
    event_bytes,
    event_jsonl,
    make_event,
    parse_event,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.record_models import PreparedEventV1

RUN_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
OPERATION_ID = UUID("223e4567-e89b-42d3-a456-426614174001")
SESSION_ID = UUID("323e4567-e89b-42d3-a456-426614174002")
SEAL_ID = UUID("423e4567-e89b-42d3-a456-426614174003")
OCCURRED_AT = datetime(2026, 8, 27, 12, 34, 56, 123456, tzinfo=UTC)
SHA = tuple(character * 64 for character in "abcdef012345")

EVENT_MODELS = {
    "prepared": PreparedEventV1,
    "execution_started": ExecutionStartedEventV1,
    "execution_blocked": ExecutionBlockedEventV1,
    "request_started": RequestStartedEventV1,
    "request_finished": RequestFinishedEventV1,
    "tail_recovered": TailRecoveredEventV1,
    "execution_interrupted": ExecutionInterruptedEventV1,
    "authentication_stopped": AuthenticationStoppedEventV1,
    "delivery_ambiguous": DeliveryAmbiguousEventV1,
    "generation_completed": GenerationCompletedEventV1,
    "seal_requested": SealRequestedEventV1,
}


def _payload(kind: str, *, recovered: bool = False) -> dict[str, Any]:
    payloads: dict[str, dict[str, Any]] = {
        "prepared": {
            "manifest_sha256": SHA[0],
            "input_index_sha256": SHA[1],
            "case_index_sha256": SHA[2],
            "plan_sha256": SHA[3],
            "environment_sha256": SHA[4],
            "runner_source_sha256": SHA[5],
        },
        "execution_started": {
            "resume_from_plan_ordinal": 0,
            "session_environment": session_environment_v1_payload(),
        },
        "execution_blocked": {"reason": "credential_unavailable"},
        "request_started": {
            "call_sequence": 0,
            "plan_item_id": SHA[0],
            "attempt_id": SHA[1],
            "attempt": 1,
            "retry_of_attempt": None,
            "request_config_sha256": SHA[2],
            "prompt_sha256": SHA[3],
            "case_definition_sha256": SHA[4],
            "instruction_sha256": SHA[5],
            "provider": "fake",
            "model": "fixture-v1",
        },
        "request_finished": {
            "call_sequence": 0,
            "plan_item_id": SHA[0],
            "attempt_id": SHA[1],
            "request_started_event_id": SHA[2],
            "raw_record_sha256": SHA[3],
            "recovered": recovered,
        },
        "tail_recovered": {
            "ledger": "events",
            "removed_byte_count": 7,
            "removed_sha256": SHA[0],
            "related_attempt_id": None,
        },
        "execution_interrupted": {
            "next_plan_item_id": SHA[0],
            "reason": "signal",
        },
        "authentication_stopped": {
            "plan_item_id": SHA[0],
            "attempt_id": SHA[1],
            "origin_request_started_event_id": SHA[2],
            "recovered": recovered,
        },
        "delivery_ambiguous": {
            "plan_item_id": SHA[0],
            "attempt_id": SHA[1],
            "origin_request_started_event_id": SHA[2],
            "recovered": recovered,
        },
        "generation_completed": {
            "terminal_plan_item_count": 1,
            "final_plan_ordinal": 0,
            "origin_request_finished_event_id": SHA[0],
            "recovered": recovered,
        },
        "seal_requested": {
            "seal_transaction_id": str(SEAL_ID),
            "expected_generation_status": "complete",
            "prior_event_sequence": 9,
        },
    }
    return payloads[kind]


def _event(
    kind: str,
    *,
    sequence: int | None = None,
    recovered: bool = False,
    session: UUID | object | None = ...,  # type: ignore[assignment]
) -> object:
    if sequence is None:
        sequence = 0 if kind == "prepared" else 1
    if session is ...:
        if kind in {"prepared", "tail_recovered", "seal_requested"} or recovered:
            session = None
        else:
            session = SESSION_ID
    payload = _payload(kind, recovered=recovered)
    if kind == "seal_requested":
        payload["prior_event_sequence"] = sequence - 1
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=OCCURRED_AT,
        kind=kind,  # type: ignore[arg-type]
        operation_id=OPERATION_ID,
        execution_session_id=session,  # type: ignore[arg-type]
        payload=payload,
    )


@pytest.mark.parametrize("kind", EVENT_MODELS)
def test_exact_event_union_round_trips_every_kind(kind: str) -> None:
    event = _event(kind)
    assert type(event) is EVENT_MODELS[kind]
    dumped = event.model_dump(mode="json")  # type: ignore[union-attr]
    assert set(dumped) == {
        "schema_version",
        "sequence",
        "event_id",
        "run_id",
        "occurred_at",
        "kind",
        "operation_id",
        "execution_session_id",
        "payload",
    }
    assert set(dumped["payload"]) == set(_payload(kind))
    assert parse_event(dumped) == event


@pytest.mark.parametrize("kind", EVENT_MODELS)
def test_event_models_are_frozen_strict_and_extra_forbid(kind: str) -> None:
    event = _event(kind)
    with pytest.raises((FrozenInstanceError, ValidationError)):
        event.sequence = 99  # type: ignore[union-attr,misc]

    payload = event.model_dump(mode="json")  # type: ignore[union-attr]
    payload["unknown"] = True
    with pytest.raises(EventError) as caught:
        parse_event(payload)
    assert caught.value.code == "invalid_event"


@pytest.mark.parametrize(
    ("kind", "recovered", "session"),
    [
        ("execution_started", False, None),
        ("execution_blocked", False, None),
        ("request_started", False, None),
        ("execution_interrupted", False, None),
        ("prepared", False, SESSION_ID),
        ("tail_recovered", False, SESSION_ID),
        ("seal_requested", False, SESSION_ID),
        ("request_finished", False, None),
        ("request_finished", True, SESSION_ID),
        ("authentication_stopped", False, None),
        ("authentication_stopped", True, SESSION_ID),
        ("delivery_ambiguous", False, None),
        ("delivery_ambiguous", True, SESSION_ID),
        ("generation_completed", False, None),
        ("generation_completed", True, SESSION_ID),
    ],
)
def test_event_session_matrix_is_exact(kind: str, recovered: bool, session: UUID | None) -> None:
    with pytest.raises(EventError) as caught:
        _event(kind, recovered=recovered, session=session)
    assert caught.value.code == "invalid_event"


@pytest.mark.parametrize(
    ("attempt", "retry_of_attempt"),
    [(1, 1), (2, None), (3, 1), (3, 3)],
)
def test_request_start_requires_immediate_retry_parent(
    attempt: int, retry_of_attempt: int | None
) -> None:
    payload = _payload("request_started")
    payload.update(attempt=attempt, retry_of_attempt=retry_of_attempt)
    with pytest.raises(EventError):
        make_event(
            sequence=1,
            run_id=RUN_ID,
            occurred_at=OCCURRED_AT,
            kind="request_started",
            operation_id=OPERATION_ID,
            execution_session_id=SESSION_ID,
            payload=payload,
        )


def test_seal_request_prior_sequence_matches_envelope() -> None:
    payload = _payload("seal_requested")
    payload["prior_event_sequence"] = 8
    with pytest.raises(EventError):
        make_event(
            sequence=10,
            run_id=RUN_ID,
            occurred_at=OCCURRED_AT,
            kind="seal_requested",
            operation_id=OPERATION_ID,
            execution_session_id=None,
            payload=payload,
        )


def test_execution_started_has_hard_coded_event_identity() -> None:
    event = _event("execution_started")
    assert event.event_id == "d9d06660301ee78f4f0e27b3c6b9a39abed0fd5c1845af2aec734bf27e88d8a8"

    logical = event.model_dump(mode="json")
    del logical["event_id"]
    encoded = json.dumps(
        logical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    assert hashlib.sha256(b"laconian-event-v1\0" + encoded).hexdigest() == event.event_id


def test_event_bytes_are_canonical_lf_free_and_jsonl_adds_one_lf() -> None:
    event = _event("execution_started")
    encoded = event_bytes(event)
    assert not encoded.endswith(b"\n")
    assert event_jsonl(event) == encoded + b"\n"
    assert parse_event(json.loads(encoded)) == event


def test_event_serializer_enforces_injected_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event("execution_started")
    encoded = event_bytes(event)
    monkeypatch.setattr(
        events_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, plan_event_jsonl_row_bytes=len(encoded) - 1),
    )
    with pytest.raises(EventError) as caught:
        event_bytes(event)
    assert caught.value.code == "event_jsonl_row_limit"


def test_public_event_helpers_reject_forged_secret_state_content_free() -> None:
    event = _event("execution_started")
    values = event.model_dump(mode="python")
    nested = event.payload.model_dump(mode="python")
    nested["resume_from_plan_ordinal"] = "TOP-SECRET /private/build"
    values["payload"] = type(event.payload).model_construct(**nested)
    forged = type(event).model_construct(**values)

    for helper in (event_bytes, event_jsonl):
        with pytest.raises(EventError) as caught:
            helper(forged)
        assert caught.value.code == "invalid_event"
        assert str(caught.value) == "capsule event rejected"
        assert "TOP-SECRET" not in repr(caught.value)


def test_make_event_rejects_uuid_and_datetime_subclasses_before_hashing() -> None:
    class EvilUUID(UUID):
        def __str__(self) -> str:
            return "TOP-SECRET-UUID-CANARY"

    class EvilDatetime(datetime):
        def isoformat(self, *args: object, **kwargs: object) -> str:
            return "TOP-SECRET-DATETIME-CANARY"

    evil_uuid = EvilUUID(str(RUN_ID))
    evil_datetime = EvilDatetime(
        OCCURRED_AT.year,
        OCCURRED_AT.month,
        OCCURRED_AT.day,
        OCCURRED_AT.hour,
        OCCURRED_AT.minute,
        OCCURRED_AT.second,
        OCCURRED_AT.microsecond,
        tzinfo=UTC,
    )
    for field, value in (("run_id", evil_uuid), ("occurred_at", evil_datetime)):
        arguments: dict[str, object] = {
            "sequence": 1,
            "run_id": RUN_ID,
            "occurred_at": OCCURRED_AT,
            "kind": "execution_started",
            "operation_id": OPERATION_ID,
            "execution_session_id": SESSION_ID,
            "payload": _payload("execution_started"),
        }
        arguments[field] = value
        with pytest.raises(EventError) as caught:
            make_event(**arguments)  # type: ignore[arg-type]
        assert caught.value.code == "invalid_event"
        assert "TOP-SECRET" not in repr(caught.value)


def test_make_event_normalizes_hostile_mapping_event_error() -> None:
    class HostileMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise EventError("TOP-SECRET-MAPPING-CANARY")

        def __iter__(self) -> Iterator[str]:
            raise EventError("TOP-SECRET-MAPPING-CANARY")

        def __len__(self) -> int:
            raise EventError("TOP-SECRET-MAPPING-CANARY")

    with pytest.raises(EventError) as caught:
        make_event(
            sequence=1,
            run_id=RUN_ID,
            occurred_at=OCCURRED_AT,
            kind="execution_started",
            operation_id=OPERATION_ID,
            execution_session_id=SESSION_ID,
            payload=HostileMapping(),
        )
    assert caught.value.code == "invalid_event"
    assert str(caught.value) == "capsule event rejected"
    assert "TOP-SECRET" not in repr(caught.value)


@pytest.mark.parametrize("hostile", ["model\x00name", "model\x85name", "model\ud800name"])
def test_event_and_session_text_reject_controls_and_surrogates(hostile: str) -> None:
    request = _payload("request_started")
    request["model"] = hostile
    with pytest.raises(EventError):
        make_event(
            sequence=1,
            run_id=RUN_ID,
            occurred_at=OCCURRED_AT,
            kind="request_started",
            operation_id=OPERATION_ID,
            execution_session_id=SESSION_ID,
            payload=request,
        )

    started = _payload("execution_started")
    started["session_environment"]["python_version"] = hostile
    with pytest.raises(EventError):
        make_event(
            sequence=1,
            run_id=RUN_ID,
            occurred_at=OCCURRED_AT,
            kind="execution_started",
            operation_id=OPERATION_ID,
            execution_session_id=SESSION_ID,
            payload=started,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sequence", True),
        ("run_id", "123e4567-e89b-12d3-a456-426614174000"),
        ("occurred_at", "2026-08-27T12:34:56Z"),
        ("event_id", "A" * 64),
    ],
)
def test_parse_event_rejects_strict_common_field_boundaries(field: str, value: object) -> None:
    event = _event("execution_started")
    payload = event.model_dump(mode="json")
    payload[field] = value
    with pytest.raises(EventError) as caught:
        parse_event(payload)
    assert caught.value.code == "invalid_event"
