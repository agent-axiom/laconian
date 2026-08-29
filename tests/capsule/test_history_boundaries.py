from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID

import pytest

from capsule.test_lifecycle import (
    EXECUTION_OPERATION,
    NOW,
    PREPARE_OPERATION,
    RECOVERY_OPERATION,
    RUN_ID,
    SESSION_ID,
    _attempt,
    _context,
    _execution_started,
    _prepared,
    _session_payload,
    _start,
    _validate,
)
from laconian_eval.capsule.attempts import raw_record_sha256
from laconian_eval.capsule.events import EventV1, make_event
from laconian_eval.capsule.history import HistoryError, validate_history_v1

FRESH_OPERATION = UUID("72345678-1234-4abc-8def-1234567890b2")
FRESH_SESSION = UUID("82345678-1234-4abc-8def-1234567890b3")


def _blocked(sequence: int = 2) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_blocked",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={"reason": "provider_unavailable"},
    )


def _started_with(
    *, sequence: int, operation_id: UUID, session_id: UUID, environment: object
) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_started",
        operation_id=operation_id,
        execution_session_id=session_id,
        payload={
            "resume_from_plan_ordinal": 0,
            "session_environment": _session_payload(environment),
        },
    )


@pytest.mark.parametrize("mutation", ["run", "timestamp", "operation-equals-run"])
def test_prepared_capsule_identity_mismatches_use_identity_taxonomy(mutation: str) -> None:
    capsule, manifest, environment, plan = _context()
    prepared = _prepared(capsule)
    forged = make_event(
        sequence=0,
        run_id=(UUID("92345678-1234-4abc-8def-1234567890b4") if mutation == "run" else RUN_ID),
        occurred_at=NOW + timedelta(microseconds=1) if mutation == "timestamp" else NOW,
        kind="prepared",
        operation_id=RUN_ID if mutation == "operation-equals-run" else PREPARE_OPERATION,
        execution_session_id=None,
        payload=prepared.payload.model_dump(mode="python"),
    )
    with pytest.raises(HistoryError) as caught:
        validate_history_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            plan=plan,
            events=(forged,),
            raw_attempts=(),
        )
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "identity_mismatch",
        "events",
        0,
    )


def test_orphan_raw_row_is_a_cross_ledger_history_mismatch() -> None:
    capsule, _manifest, _environment, plan = _context()
    with pytest.raises(HistoryError) as caught:
        _validate((_prepared(capsule),), (_attempt(plan[0]),))
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "history_mismatch",
        "raw",
        0,
    )


@pytest.mark.parametrize(
    ("operation_id", "session_id"),
    [
        (FRESH_OPERATION, PREPARE_OPERATION),
        (SESSION_ID, FRESH_SESSION),
        (FRESH_OPERATION, EXECUTION_OPERATION),
    ],
)
def test_cross_class_uuid_reuse_is_rejected_exactly(
    operation_id: UUID,
    session_id: UUID,
) -> None:
    capsule, _manifest, environment, _plan = _context()
    events = (
        _prepared(capsule),
        _execution_started(environment),
        _blocked(),
        _started_with(
            sequence=3,
            operation_id=operation_id,
            session_id=session_id,
            environment=environment,
        ),
    )
    with pytest.raises(HistoryError) as caught:
        _validate(events)
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "identity_mismatch",
        "events",
        3,
    )


def test_bad_session_python_version_preserves_the_physical_event_row() -> None:
    capsule, _manifest, environment, _plan = _context()
    payload = _session_payload(environment)
    payload["python_version"] = "not-a-version"
    event = make_event(
        sequence=1,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_started",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={"resume_from_plan_ordinal": 0, "session_environment": payload},
    )
    with pytest.raises(HistoryError) as caught:
        _validate((_prepared(capsule), event))
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "identity_mismatch",
        "events",
        1,
    )


class _HostileIterable:
    def __iter__(self) -> Iterator[object]:
        raise RuntimeError("credential=CANARY /private/history")


@pytest.mark.parametrize("hostile_ledger", ["events", "raw"])
def test_hostile_iterable_failures_are_content_free(hostile_ledger: str) -> None:
    capsule, manifest, environment, plan = _context()
    events: object = _HostileIterable() if hostile_ledger == "events" else (_prepared(capsule),)
    raw: object = _HostileIterable() if hostile_ledger == "raw" else ()
    with pytest.raises(HistoryError) as caught:
        validate_history_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            plan=plan,
            events=events,  # type: ignore[arg-type]
            raw_attempts=raw,  # type: ignore[arg-type]
        )
    assert caught.value.ledger == hostile_ledger
    assert "CANARY" not in str(caught.value)
    assert "/private" not in str(caught.value)


def _tail_recovered(sequence: int, ledger: str) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="tail_recovered",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "ledger": ledger,
            "removed_byte_count": 1,
            "removed_sha256": "a" * 64,
            "related_attempt_id": None,
        },
    )


@pytest.mark.parametrize(
    "tail_ledgers",
    [
        ("raw", "events"),
        ("events", "events"),
        ("raw", "raw"),
    ],
)
def test_tail_recovery_audits_are_unique_and_events_before_raw_per_operation(
    tail_ledgers: tuple[str, str],
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    events = (
        _prepared(capsule),
        _tail_recovered(1, tail_ledgers[0]),
        _tail_recovered(2, tail_ledgers[1]),
    )

    with pytest.raises(HistoryError) as caught:
        _validate(events)

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "history_mismatch",
        "events",
        2,
    )


def test_tail_recovery_cannot_follow_a_recovered_finish_in_the_same_operation() -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "success")
    recovered_finish = make_event(
        sequence=3,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_finished",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "call_sequence": start.payload.call_sequence,
            "plan_item_id": start.payload.plan_item_id,
            "attempt_id": start.payload.attempt_id,
            "request_started_event_id": start.event_id,
            "raw_record_sha256": raw_record_sha256(attempt),
            "recovered": True,
        },
    )
    late_tail = _tail_recovered(4, "events")

    with pytest.raises(HistoryError) as caught:
        _validate(
            (
                _prepared(capsule),
                _execution_started(environment),
                start,
                recovered_finish,
                late_tail,
            ),
            (attempt,),
        )

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "history_mismatch",
        "events",
        4,
    )
