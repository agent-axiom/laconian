"""End-to-end acceptance coverage for history-derived capsule seals."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import pytest

from capsule.test_lifecycle import (
    EXECUTION_OPERATION,
    NOW,
    RUN_ID,
    SEAL_OPERATION,
    SEAL_TRANSACTION,
    SESSION_ID,
    _attempt,
    _context,
    _execution_started,
    _prepared,
    _start,
)
from laconian_eval.capsule.attempts import (
    RawAttemptV2,
    derive_attempt_id,
    raw_record_sha256,
)
from laconian_eval.capsule.events import EventV1, SealRequestedEventV1, make_event
from laconian_eval.capsule.history import (
    HistoryError,
    RawHistorySummaryV1,
    derive_lifecycle_v1,
    validate_history_v1,
)
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.seal_models import (
    SealFileV1,
    derive_seal_v1,
)

Scenario = Literal[
    "complete",
    "never_started",
    "interrupted",
    "ambiguous",
    "rawless_ambiguous",
    "auth",
]
UsageAvailability = Literal["complete", "partial", "unavailable"]


def _plan_rows(count: int) -> tuple[PlanRowV1, ...]:
    _capsule, _manifest, _environment, base = _context()
    return tuple(
        base[0].model_copy(
            update={
                "ordinal": ordinal,
                "plan_item_id": f"{ordinal + 16:064x}",
            }
        )
        for ordinal in range(count)
    )


def _numbered_start(
    plan: PlanRowV1,
    *,
    attempt_number: int,
    call_sequence: int,
    sequence: int,
) -> EventV1:
    payload = _start(plan).payload.model_dump(
        mode="python",
        round_trip=True,
        warnings=False,
    )
    payload.update(
        attempt=attempt_number,
        attempt_id=derive_attempt_id(RUN_ID, plan.plan_item_id, attempt_number),
        call_sequence=call_sequence,
        retry_of_attempt=None if attempt_number == 1 else attempt_number - 1,
    )
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_started",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload=payload,
    )


def _numbered_attempt(
    plan: PlanRowV1,
    *,
    reason: Literal["safe_retry", "provider_rejected", "success"],
    attempt_number: int,
    call_sequence: int,
    response_model: str,
    usage_availability: UsageAvailability,
    redaction_count: int = 0,
) -> RawAttemptV2:
    payload: dict[str, Any] = _attempt(plan, reason).model_dump(
        mode="python",
        round_trip=True,
        warnings=False,
    )
    payload.update(
        attempt=attempt_number,
        attempt_id=derive_attempt_id(RUN_ID, plan.plan_item_id, attempt_number),
        call_sequence=call_sequence,
        retry_of_attempt=None if attempt_number == 1 else attempt_number - 1,
        response_model=response_model,
        output_was_redacted=redaction_count > 0,
        output_redaction_count=redaction_count,
    )
    if reason == "safe_retry":
        payload["backoff_ms"] = 100 * 2 ** (attempt_number - 1)
    usage = payload["usage"]
    assert isinstance(usage, dict)
    usage.update(
        input_tokens=11 if usage_availability != "unavailable" else None,
        output_tokens=7 if usage_availability == "complete" else None,
        total_tokens=18 if usage_availability == "complete" else None,
        availability=usage_availability,
    )
    return RawAttemptV2.model_validate(payload)


def _numbered_finish(start: EventV1, raw: RawAttemptV2, *, sequence: int) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_finished",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "call_sequence": raw.call_sequence,
            "plan_item_id": raw.plan_item_id,
            "attempt_id": raw.attempt_id,
            "request_started_event_id": start.event_id,
            "raw_record_sha256": raw_record_sha256(raw),
            "recovered": False,
        },
    )


def _seal_request(
    *,
    sequence: int,
    status: Literal["complete", "incomplete"],
    seal_transaction_id: UUID = SEAL_TRANSACTION,
) -> SealRequestedEventV1:
    event = make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="seal_requested",
        operation_id=SEAL_OPERATION,
        execution_session_id=None,
        payload={
            "seal_transaction_id": seal_transaction_id,
            "expected_generation_status": status,
            "prior_event_sequence": sequence - 1,
        },
    )
    assert type(event) is SealRequestedEventV1
    return event


def test_history_aggregates_every_retry_error_and_success_raw_row() -> None:
    capsule, manifest, environment, _base_plan = _context()
    plan = _plan_rows(2)
    events: list[EventV1] = [_prepared(capsule), _execution_started(environment)]
    raw_rows: list[RawAttemptV2] = []
    attempts = (
        (plan[0], "safe_retry", 1, "retry-returned-model", "partial", 0),
        (plan[0], "provider_rejected", 2, "error-returned-model", "unavailable", 0),
        (plan[1], "success", 1, "successful-returned-model", "complete", 2),
    )
    for call_sequence, (
        row,
        reason,
        attempt_number,
        response_model,
        usage_availability,
        redaction_count,
    ) in enumerate(attempts):
        start = _numbered_start(
            row,
            attempt_number=attempt_number,
            call_sequence=call_sequence,
            sequence=len(events),
        )
        raw = _numbered_attempt(
            row,
            reason=reason,  # type: ignore[arg-type]
            attempt_number=attempt_number,
            call_sequence=call_sequence,
            response_model=response_model,
            usage_availability=usage_availability,  # type: ignore[arg-type]
            redaction_count=redaction_count,
        )
        events.append(start)
        events.append(_numbered_finish(start, raw, sequence=len(events)))
        raw_rows.append(raw)

    history = validate_history_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        events=tuple(events),
        raw_attempts=tuple(raw_rows),
    )

    assert history.raw_summary == RawHistorySummaryV1(
        raw_attempt_count=3,
        usage_complete_count=1,
        usage_partial_count=1,
        usage_unavailable_count=1,
        redacted_output_attempt_count=1,
        redacted_output_replacement_count=2,
    )
    assert history.returned_models == ("successful-returned-model",)


def _actual_ledger_scenario(
    scenario: Scenario,
) -> tuple[tuple[EventV1, ...], tuple[RawAttemptV2, ...]]:
    capsule, _manifest, environment, plan = _context()
    events: list[EventV1] = [_prepared(capsule)]
    raw_rows: tuple[RawAttemptV2, ...] = ()

    if scenario == "never_started":
        events.extend(
            (
                _execution_started(environment),
                make_event(
                    sequence=2,
                    run_id=RUN_ID,
                    occurred_at=NOW,
                    kind="execution_blocked",
                    operation_id=EXECUTION_OPERATION,
                    execution_session_id=SESSION_ID,
                    payload={"reason": "provider_unavailable"},
                ),
            )
        )
    elif scenario == "interrupted":
        events.extend(
            (
                _execution_started(environment),
                make_event(
                    sequence=2,
                    run_id=RUN_ID,
                    occurred_at=NOW,
                    kind="execution_interrupted",
                    operation_id=EXECUTION_OPERATION,
                    execution_session_id=SESSION_ID,
                    payload={
                        "next_plan_item_id": plan[0].plan_item_id,
                        "reason": "operator",
                    },
                ),
            )
        )
    elif scenario == "rawless_ambiguous":
        events.extend((_execution_started(environment), _start(plan[0])))
    else:
        reason = (
            "success"
            if scenario == "complete"
            else "ambiguous_delivery"
            if scenario == "ambiguous"
            else "authentication"
        )
        start = _start(plan[0])
        raw = _attempt(plan[0], reason)
        finish = _numbered_finish(start, raw, sequence=3)
        events.extend((_execution_started(environment), start, finish))
        raw_rows = (raw,)
        if scenario == "complete":
            events.append(
                make_event(
                    sequence=4,
                    run_id=RUN_ID,
                    occurred_at=NOW,
                    kind="generation_completed",
                    operation_id=EXECUTION_OPERATION,
                    execution_session_id=SESSION_ID,
                    payload={
                        "terminal_plan_item_count": 1,
                        "final_plan_ordinal": 0,
                        "origin_request_finished_event_id": finish.event_id,
                        "recovered": False,
                    },
                )
            )
        else:
            marker_kind = (
                "delivery_ambiguous" if scenario == "ambiguous" else "authentication_stopped"
            )
            events.append(
                make_event(
                    sequence=4,
                    run_id=RUN_ID,
                    occurred_at=NOW,
                    kind=marker_kind,
                    operation_id=EXECUTION_OPERATION,
                    execution_session_id=SESSION_ID,
                    payload={
                        "plan_item_id": plan[0].plan_item_id,
                        "attempt_id": raw.attempt_id,
                        "origin_request_started_event_id": start.event_id,
                        "recovered": False,
                    },
                )
            )

    status: Literal["complete", "incomplete"] = (
        "complete" if scenario == "complete" else "incomplete"
    )
    events.append(_seal_request(sequence=len(events), status=status))
    return tuple(events), raw_rows


@pytest.mark.parametrize(
    (
        "scenario",
        "expected_status",
        "expected_blockers",
        "expected_detail",
        "expected_raw_count",
        "expected_models",
    ),
    [
        ("complete", "complete", (), None, 1, ("returned-a",)),
        (
            "never_started",
            "incomplete",
            ("never_started",),
            "provider_unavailable",
            0,
            (),
        ),
        ("interrupted", "incomplete", ("interrupted",), None, 0, ()),
        ("ambiguous", "incomplete", ("ambiguous_inflight",), None, 1, ()),
        ("rawless_ambiguous", "incomplete", ("ambiguous_inflight",), None, 0, ()),
        ("auth", "incomplete", ("authentication_stopped",), None, 1, ()),
    ],
)
def test_actual_ledgers_derive_the_complete_seal_status_matrix(
    scenario: Scenario,
    expected_status: str,
    expected_blockers: tuple[str, ...],
    expected_detail: str | None,
    expected_raw_count: int,
    expected_models: tuple[str, ...],
) -> None:
    capsule, manifest, environment, plan = _context()
    events, raw_rows = _actual_ledger_scenario(scenario)
    request = events[-1]
    assert type(request) is SealRequestedEventV1

    history = validate_history_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        events=events,
        raw_attempts=raw_rows,
    )
    lifecycle = derive_lifecycle_v1(history)
    seal = derive_seal_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        history=history,
        lifecycle=lifecycle,
        seal_requested=request,
        files=(SealFileV1(path="capsule.json", byte_length=1, sha256="a" * 64),),
    )

    expected_missing = () if scenario == "complete" else (plan[0].plan_item_id,)
    assert history.recovery_requirements == ()
    assert lifecycle.state == "SEALING_INTERRUPTED"
    assert lifecycle.missing_plan_item_ids == expected_missing
    assert lifecycle.operational_blocker_codes == expected_blockers
    assert seal.generation_status == expected_status
    assert seal.missing_plan_item_ids == expected_missing
    assert seal.operational_blocker_codes == expected_blockers
    assert seal.never_started_detail == expected_detail
    assert seal.raw_attempt_count == expected_raw_count
    assert seal.disclosures.returned_models == expected_models
    assert (
        seal.disclosures.usage_availability_counts.complete
        + seal.disclosures.usage_availability_counts.partial
        + seal.disclosures.usage_availability_counts.unavailable
        == expected_raw_count
    )
    assert seal.final_event_sequence == request.sequence


def _rawless_open_events(seal_transaction_id: UUID) -> tuple[EventV1, ...]:
    capsule, _manifest, environment, plan = _context()
    return (
        _prepared(capsule),
        _execution_started(environment),
        _start(plan[0]),
        _seal_request(
            sequence=3,
            status="incomplete",
            seal_transaction_id=seal_transaction_id,
        ),
    )


def test_rawless_open_request_allows_prior_operation_as_seal_transaction() -> None:
    capsule, manifest, environment, plan = _context()
    events = _rawless_open_events(EXECUTION_OPERATION)
    request = events[-1]
    assert type(request) is SealRequestedEventV1
    history = validate_history_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        events=events,
        raw_attempts=(),
    )
    lifecycle = derive_lifecycle_v1(history)

    seal = derive_seal_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        history=history,
        lifecycle=lifecycle,
        seal_requested=request,
        files=(SealFileV1(path="capsule.json", byte_length=1, sha256="a" * 64),),
    )

    assert seal.seal_transaction_id == EXECUTION_OPERATION


def test_rawless_open_request_rejects_session_colliding_transaction_at_history_boundary() -> None:
    capsule, manifest, environment, plan = _context()

    with pytest.raises(HistoryError) as caught:
        validate_history_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            plan=plan,
            events=_rawless_open_events(SESSION_ID),
            raw_attempts=(),
        )

    assert caught.value.code == "identity_mismatch"
    assert str(caught.value) == "capsule history rejected"
