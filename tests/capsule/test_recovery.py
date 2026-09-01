from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from capsule.test_lifecycle import (
    EXECUTION_OPERATION,
    NOW,
    PREPARE_OPERATION,
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
    raw_attempt_jsonl,
    raw_record_sha256,
)
from laconian_eval.capsule.events import EventV1, event_jsonl, make_event
from laconian_eval.capsule.history import (
    HistoryContextV1,
    HistoryError,
    RawHistorySummaryV1,
    RecoveryRequirementV1,
    derive_lifecycle_v1,
)
from laconian_eval.capsule.journal import snapshot_journal_pair
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.recovery import (
    RecoveryContextV1,
    RecoveryError,
    plan_recovery_v1,
)

RECOVERY_OPERATION = UUID("12345678-1234-4abc-8def-1234567890d1")
RECOVERY_TIME = datetime(2026, 8, 29, 12, 30, tzinfo=UTC)


def _root(tmp_path: object) -> int:
    return os.open(os.fspath(tmp_path), os.O_RDONLY | os.O_DIRECTORY)


def _snapshot(
    tmp_path: object,
    *,
    event_rows: tuple[object, ...],
    raw_rows: tuple[object, ...] = (),
    event_tail: bytes = b"",
    raw_tail: bytes = b"",
) -> tuple[RecoveryContextV1, object]:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(  # type: ignore[operator]
        b"".join(event_jsonl(row) for row in event_rows) + event_tail
    )
    (tmp_path / "raw.jsonl").write_bytes(  # type: ignore[operator]
        b"".join(raw_attempt_jsonl(row) for row in raw_rows) + raw_tail
    )
    descriptor = _root(tmp_path)
    try:
        journals = snapshot_journal_pair(
            descriptor,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="report",
        )
    finally:
        os.close(descriptor)
    context = RecoveryContextV1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        immutable_evidence_bytes=0,
        history=journals.history,
        lifecycle=journals.lifecycle,
        event_snapshot=journals.events,
        raw_snapshot=journals.raw,
    )
    return context, journals


def _plan(context: RecoveryContextV1, journals: object) -> object:
    return plan_recovery_v1(
        context=context,
        event_snapshot=journals.events,  # type: ignore[attr-defined]
        raw_snapshot=journals.raw,  # type: ignore[attr-defined]
        operation_id=RECOVERY_OPERATION,
        occurred_at=RECOVERY_TIME,
    )


def _numbered_attempt(
    plan: PlanRowV1,
    reason: str,
    *,
    attempt_number: int,
) -> RawAttemptV2:
    base_reason = "safe_retry" if reason == "retry_exhausted" else reason
    payload: dict[str, Any] = _attempt(plan, base_reason).model_dump(
        mode="python",
        round_trip=True,
        warnings=False,
    )
    payload.update(
        attempt=attempt_number,
        attempt_id=derive_attempt_id(RUN_ID, plan.plan_item_id, attempt_number),
        call_sequence=attempt_number - 1,
        retry_of_attempt=None if attempt_number == 1 else attempt_number - 1,
    )
    if reason == "retry_exhausted":
        payload.update(
            terminal=True,
            terminal_reason="retry_exhausted",
            backoff_ms=None,
        )
    elif reason == "safe_retry":
        payload["backoff_ms"] = 100 * 2 ** (attempt_number - 1)
    return RawAttemptV2.model_validate(payload)


def _numbered_start(
    plan: PlanRowV1,
    *,
    attempt_number: int,
    sequence: int,
) -> EventV1:
    payload = _start(plan).payload.model_dump(
        mode="python",
        round_trip=True,
        warnings=False,
    )
    payload.update(
        call_sequence=attempt_number - 1,
        attempt_id=derive_attempt_id(RUN_ID, plan.plan_item_id, attempt_number),
        attempt=attempt_number,
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


def _numbered_finish(start: EventV1, attempt: RawAttemptV2, *, sequence: int) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_finished",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "call_sequence": attempt.call_sequence,
            "plan_item_id": attempt.plan_item_id,
            "attempt_id": attempt.attempt_id,
            "request_started_event_id": start.event_id,
            "raw_record_sha256": raw_record_sha256(attempt),
            "recovered": False,
        },
    )


def _truth_state_rows(
    reason: str,
    *,
    finish_committed: bool,
) -> tuple[tuple[EventV1, ...], tuple[RawAttemptV2, ...]]:
    capsule, _manifest, environment, plan = _context()
    events = [_prepared(capsule), _execution_started(environment)]
    attempts: list[RawAttemptV2] = []
    final_attempt = 3 if reason == "retry_exhausted" else 1
    for attempt_number in range(1, final_attempt + 1):
        current_reason = "safe_retry" if attempt_number < final_attempt else reason
        start = _numbered_start(
            plan[0],
            attempt_number=attempt_number,
            sequence=len(events),
        )
        attempt = _numbered_attempt(
            plan[0],
            current_reason,
            attempt_number=attempt_number,
        )
        events.append(start)
        attempts.append(attempt)
        if attempt_number < final_attempt or finish_committed:
            events.append(_numbered_finish(start, attempt, sequence=len(events)))
    return tuple(events), tuple(attempts)


def _assert_content_free(error: RecoveryError, *, canary: str | None = None) -> None:
    assert str(error) == "capsule recovery rejected"
    assert error.args == ("capsule recovery rejected",)
    if canary is not None:
        assert canary not in str(error)
        assert canary not in repr(error)
        assert canary not in repr(error.args)
        assert canary not in repr(vars(error))


def test_prepared_history_is_provider_ready_without_recovery_rows(tmp_path: object) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))

    plan = _plan(context, journals)

    assert plan.disposition == "provider_ready"
    assert plan.truncations == ()
    assert plan.append_events == ()
    assert plan.post_mutable_bytes == (journals.events.byte_length + journals.raw.byte_length)
    assert plan.seal_reservation_bytes == RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1


def test_unmatched_start_stays_markerless_ambiguous(tmp_path: object) -> None:
    capsule, _manifest, environment, plan_rows = _context()
    context, journals = _snapshot(
        tmp_path,
        event_rows=(
            _prepared(capsule),
            _execution_started(environment),
            _start(plan_rows[0]),
        ),
    )

    plan = _plan(context, journals)

    assert plan.disposition == "ambiguous"
    assert plan.truncations == ()
    assert plan.append_events == ()


def test_raw_without_finish_synthesizes_finish_then_completion(tmp_path: object) -> None:
    capsule, _manifest, environment, plan_rows = _context()
    start = _start(plan_rows[0])
    attempt = _attempt(plan_rows[0], "success")
    context, journals = _snapshot(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
    )

    plan = _plan(context, journals)

    assert plan.disposition == "complete"
    assert tuple(event.kind for event in plan.append_events) == (
        "request_finished",
        "generation_completed",
    )
    recovered_finish, completion = plan.append_events
    assert recovered_finish.sequence == journals.events.row_count
    assert recovered_finish.payload.recovered is True
    assert recovered_finish.payload.request_started_event_id == start.event_id
    assert completion.payload.recovered is True
    assert completion.payload.origin_request_finished_event_id == recovered_finish.event_id


@pytest.mark.parametrize(
    ("reason", "disposition", "normalized_suffix"),
    [
        ("success", "complete", ("generation_completed",)),
        ("safe_retry", "provider_ready", ()),
        ("retry_exhausted", "complete", ("generation_completed",)),
        ("provider_rejected", "complete", ("generation_completed",)),
        ("authentication", "authentication_stopped", ("authentication_stopped",)),
        ("ambiguous_delivery", "ambiguous", ("delivery_ambiguous",)),
    ],
)
@pytest.mark.parametrize(
    "finish_committed",
    [False, True],
    ids=("raw-without-finish", "start-raw-finish"),
)
def test_all_six_raw_truth_states_have_exact_normalized_recovery(
    reason: str,
    disposition: str,
    normalized_suffix: tuple[str, ...],
    finish_committed: bool,
    tmp_path: Path,
) -> None:
    events, raw = _truth_state_rows(reason, finish_committed=finish_committed)
    context, journals = _snapshot(tmp_path, event_rows=events, raw_rows=raw)

    plan = _plan(context, journals)

    expected = (() if finish_committed else ("request_finished",)) + normalized_suffix
    assert plan.disposition == disposition
    assert tuple(event.kind for event in plan.append_events) == expected
    assert all(event.payload.recovered is True for event in plan.append_events)
    assert all(event.operation_id == RECOVERY_OPERATION for event in plan.append_events)
    assert all(event.execution_session_id is None for event in plan.append_events)
    if not finish_committed:
        recovered_finish = plan.append_events[0]
        assert recovered_finish.payload.raw_record_sha256 == raw_record_sha256(raw[-1])
        assert recovered_finish.payload.request_started_event_id == events[-1].event_id
    if normalized_suffix == ("generation_completed",):
        completion = plan.append_events[-1]
        assert completion.payload.origin_request_finished_event_id == (
            events[-1].event_id if finish_committed else plan.append_events[0].event_id
        )


@pytest.mark.parametrize(
    ("reason", "marker_kind"),
    [
        ("authentication", "authentication_stopped"),
        ("ambiguous_delivery", "delivery_ambiguous"),
    ],
)
def test_terminal_retry_recovery_marker_links_to_current_open_start(
    reason: str,
    marker_kind: str,
    tmp_path: Path,
) -> None:
    capsule, _manifest, environment, plan_rows = _context()
    first_start = _numbered_start(plan_rows[0], attempt_number=1, sequence=2)
    first_raw = _numbered_attempt(plan_rows[0], "safe_retry", attempt_number=1)
    first_finish = _numbered_finish(first_start, first_raw, sequence=3)
    second_start = _numbered_start(plan_rows[0], attempt_number=2, sequence=4)
    second_raw = _numbered_attempt(plan_rows[0], reason, attempt_number=2)
    context, journals = _snapshot(
        tmp_path,
        event_rows=(
            _prepared(capsule),
            _execution_started(environment),
            first_start,
            first_finish,
            second_start,
        ),
        raw_rows=(first_raw, second_raw),
    )

    recovery = _plan(context, journals)

    assert tuple(event.kind for event in recovery.append_events) == (
        "request_finished",
        marker_kind,
    )
    recovered_finish, marker = recovery.append_events
    assert recovered_finish.payload.request_started_event_id == second_start.event_id
    assert marker.payload.origin_request_started_event_id == second_start.event_id


def test_raw_terminal_reason_not_diagnostic_words_drives_normalization(
    tmp_path: Path,
) -> None:
    events, raw = _truth_state_rows("provider_rejected", finish_committed=False)
    assert raw[-1].error is not None
    assert "authentication" in raw[-1].error.message
    assert "ambiguous" in raw[-1].error.message
    context, journals = _snapshot(tmp_path, event_rows=events, raw_rows=raw)

    plan = _plan(context, journals)

    assert plan.disposition == "complete"
    assert tuple(event.kind for event in plan.append_events) == (
        "request_finished",
        "generation_completed",
    )


def test_simultaneous_tails_have_exact_fixed_order_audits(tmp_path: object) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    event_tail = b'{"partial-event":"secret-canary"}'
    raw_tail = b'{"partial-raw":"secret-canary"}'
    context, journals = _snapshot(
        tmp_path,
        event_rows=(_prepared(capsule),),
        event_tail=event_tail,
        raw_tail=raw_tail,
    )

    plan = _plan(context, journals)

    assert tuple(item.ledger for item in plan.truncations) == ("events", "raw")
    assert tuple(item.removed_byte_count for item in plan.truncations) == (
        len(event_tail),
        len(raw_tail),
    )
    assert tuple(item.removed_sha256 for item in plan.truncations) == (
        hashlib.sha256(event_tail).hexdigest(),
        hashlib.sha256(raw_tail).hexdigest(),
    )
    assert tuple(event.kind for event in plan.append_events) == (
        "tail_recovered",
        "tail_recovered",
    )
    assert tuple(event.payload.ledger for event in plan.append_events) == ("events", "raw")
    assert all("secret-canary" not in repr(item) for item in plan.truncations)


def test_raw_tail_for_durable_open_start_records_only_related_attempt(tmp_path: object) -> None:
    capsule, _manifest, environment, plan_rows = _context()
    start = _start(plan_rows[0])
    raw_tail = b'{"schema_version":"2"}'
    context, journals = _snapshot(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_tail=raw_tail,
    )

    plan = _plan(context, journals)

    assert plan.disposition == "ambiguous"
    assert len(plan.truncations) == 1
    assert plan.truncations[0].ledger == "raw"
    assert plan.truncations[0].related_attempt_id == start.payload.attempt_id
    assert tuple(event.kind for event in plan.append_events) == ("tail_recovered",)
    assert plan.append_events[0].payload.related_attempt_id == start.payload.attempt_id


def test_raw_tail_after_committed_raw_is_not_related_to_the_resolved_attempt(
    tmp_path: Path,
) -> None:
    capsule, _manifest, environment, plan_rows = _context()
    start = _start(plan_rows[0])
    attempt = _attempt(plan_rows[0], "success")
    context, journals = _snapshot(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
        raw_tail=b'{"uncommitted-next-raw":"canary"}',
    )

    recovery = _plan(context, journals)

    assert recovery.disposition == "complete"
    assert tuple(event.kind for event in recovery.append_events) == (
        "tail_recovered",
        "request_finished",
        "generation_completed",
    )
    assert recovery.append_events[0].payload.related_attempt_id is None


def test_committed_raw_cannot_depend_on_start_present_only_in_event_tail(
    tmp_path: Path,
) -> None:
    capsule, manifest, environment, plan_rows = _context()
    start_tail = event_jsonl(_start(plan_rows[0]))[:-1]
    attempt = _attempt(plan_rows[0], "success")
    event_path = tmp_path / "events.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    event_path.write_bytes(
        event_jsonl(_prepared(capsule)) + event_jsonl(_execution_started(environment)) + start_tail
    )
    raw_path.write_bytes(raw_attempt_jsonl(attempt))
    original_events = event_path.read_bytes()
    original_raw = raw_path.read_bytes()
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(HistoryError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan_rows),
                tail_policy="report",
            )
    finally:
        os.close(descriptor)

    assert caught.value.code == "history_mismatch"
    assert event_path.read_bytes() == original_events
    assert raw_path.read_bytes() == original_raw


def test_full_evidence_capacity_accepts_exact_limit_and_rejects_plus_one(
    tmp_path: object,
) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    seal_reservation = RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1
    exact_immutable = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
        - journals.events.byte_length
        - journals.raw.byte_length
        - seal_reservation
    )

    exact = _plan(replace(context, immutable_evidence_bytes=exact_immutable), journals)
    assert exact.post_mutable_bytes + exact.seal_reservation_bytes == (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
    )

    with pytest.raises(RecoveryError) as caught:
        _plan(replace(context, immutable_evidence_bytes=exact_immutable + 1), journals)
    assert caught.value.code == "resource_limit"


def test_recovery_event_appends_reserve_partial_row_and_replay_audit(tmp_path: Path) -> None:
    capsule, _manifest, environment, plan_rows = _context()
    start = _start(plan_rows[0])
    attempt = _attempt(plan_rows[0], "success")
    context, journals = _snapshot(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
    )
    baseline = _plan(context, journals)
    replay_reservation = 2 * (RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1)
    exact_immutable = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
        - baseline.post_mutable_bytes
        - baseline.seal_reservation_bytes
        - replay_reservation
    )

    exact = _plan(replace(context, immutable_evidence_bytes=exact_immutable), journals)

    assert exact.crash_reservation_bytes == replay_reservation
    assert (
        exact.post_mutable_bytes + exact.seal_reservation_bytes + exact.crash_reservation_bytes
        == RESOURCE_LIMITS_V1.mutable_capsule_bytes
    )
    with pytest.raises(RecoveryError) as caught:
        _plan(replace(context, immutable_evidence_bytes=exact_immutable + 1), journals)
    assert caught.value.code == "resource_limit"


def test_existing_event_tail_reserves_fixed_audit_slot_and_partial_replay(
    tmp_path: Path,
) -> None:
    capsule, _manifest, environment, plan_rows = _context()
    start = _start(plan_rows[0])
    attempt = _attempt(plan_rows[0], "success")
    context, journals = _snapshot(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
        event_tail=b'{"initial-torn-event":"canary"}',
    )
    baseline = _plan(context, journals)
    row_reservation = RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1
    audit_bytes = len(event_jsonl(baseline.append_events[0]))
    replay_reservation = 2 * row_reservation - audit_bytes
    exact_immutable = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
        - baseline.post_mutable_bytes
        - baseline.seal_reservation_bytes
        - replay_reservation
    )

    exact = _plan(replace(context, immutable_evidence_bytes=exact_immutable), journals)

    assert exact.crash_reservation_bytes == replay_reservation
    assert (
        exact.post_mutable_bytes + exact.seal_reservation_bytes + exact.crash_reservation_bytes
        == RESOURCE_LIMITS_V1.mutable_capsule_bytes
    )
    with pytest.raises(RecoveryError) as caught:
        _plan(replace(context, immutable_evidence_bytes=exact_immutable + 1), journals)
    assert caught.value.code == "resource_limit"


@pytest.mark.parametrize(
    ("ledger", "changes"),
    [
        ("events", {"byte_length": -1}),
        ("events", {"mode": stat.S_IFDIR | 0o755}),
        ("events", {"row_count": 0}),
        ("raw", {"tail_byte_count": 1, "tail_sha256": None}),
        ("raw", {"sha256": "snapshot-secret-canary"}),
        ("raw", {"row_count": RESOURCE_LIMITS_V1.raw_rows + 1}),
    ],
)
def test_dataclasses_replace_cannot_forge_nested_journal_snapshots(
    ledger: str,
    changes: dict[str, object],
    tmp_path: Path,
) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    events = journals.events
    raw = journals.raw
    if ledger == "events":
        events = replace(events, **changes)
    else:
        raw = replace(raw, **changes)

    with pytest.raises(RecoveryError) as caught:
        plan_recovery_v1(
            context=context,
            event_snapshot=events,
            raw_snapshot=raw,
            operation_id=RECOVERY_OPERATION,
            occurred_at=RECOVERY_TIME,
        )

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value, canary="snapshot-secret-canary")


def test_dataclasses_replace_cannot_inject_nested_recovery_requirement(
    tmp_path: Path,
) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    forged_history = replace(
        context.history,
        recovery_requirements=(
            RecoveryRequirementV1(
                "generation_completed",
                0,
                origin_request_finished_event_id="a" * 64,
            ),
        ),
    )

    with pytest.raises(RecoveryError) as caught:
        forged_context = replace(
            context,
            history=forged_history,
            lifecycle=derive_lifecycle_v1(forged_history),
        )
        _plan(forged_context, journals)

    assert caught.value.code in {"invalid_model", "identity_mismatch"}
    _assert_content_free(caught.value)


def test_dataclasses_replace_cannot_change_open_raw_terminal_reason(
    tmp_path: Path,
) -> None:
    events, raw = _truth_state_rows("success", finish_committed=False)
    context, journals = _snapshot(tmp_path, event_rows=events, raw_rows=raw)
    assert context.history.open_attempt is not None
    assert context.history.open_attempt.raw is not None
    forged_raw = replace(
        context.history.open_attempt.raw,
        terminal_reason="authentication_stopped",
    )
    forged_history = replace(
        context.history,
        open_attempt=replace(context.history.open_attempt, raw=forged_raw),
    )

    with pytest.raises(RecoveryError) as caught:
        forged_context = replace(
            context,
            history=forged_history,
            lifecycle=derive_lifecycle_v1(forged_history),
        )
        _plan(forged_context, journals)

    assert caught.value.code in {"invalid_model", "identity_mismatch"}
    _assert_content_free(caught.value)


@pytest.mark.parametrize(
    "raw_summary",
    [
        object(),
        RawHistorySummaryV1(True, 0, 0, 0, 0, 0),  # type: ignore[arg-type]
        RawHistorySummaryV1(-1, 0, 0, 0, 0, 0),
        RawHistorySummaryV1(0, 1, 0, 0, 0, 0),
        RawHistorySummaryV1(1, 0, 0, 1, 0, 0),
        RawHistorySummaryV1(0, 0, 0, 0, 1, 1),
        RawHistorySummaryV1(0, 0, 0, 0, 0, 1),
    ],
    ids=(
        "wrong-class",
        "boolean-count",
        "negative-count",
        "usage-sum",
        "cursor-count",
        "redacted-attempt",
        "replacement-without-attempt",
    ),
)
def test_recovery_rejects_forged_raw_history_summary(
    raw_summary: object,
    tmp_path: Path,
) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, _journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    forged_history = replace(context.history, raw_summary=raw_summary)

    with pytest.raises(RecoveryError) as caught:
        replace(context, history=forged_history)

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value)


def test_recovery_rejects_block_reason_without_latest_no_call_block(
    tmp_path: Path,
) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, _journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    forged_history = replace(
        context.history,
        latest_no_call_blocked_reason="provider_unavailable",
    )

    with pytest.raises(RecoveryError) as caught:
        replace(context, history=forged_history)

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value)


@pytest.mark.parametrize(
    "field",
    ["has_ambiguous_delivery", "has_authentication_stop"],
)
def test_recovery_rejects_terminal_call_state_without_request_history(
    field: str,
    tmp_path: Path,
) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, _journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    forged_history = replace(context.history, **{field: True})
    forged_lifecycle = derive_lifecycle_v1(forged_history)

    with pytest.raises(RecoveryError) as caught:
        replace(
            context,
            history=forged_history,
            lifecycle=forged_lifecycle,
        )

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value)


def test_recovery_rejects_returned_model_without_resolved_success(
    tmp_path: Path,
) -> None:
    events, raw_rows = _truth_state_rows("safe_retry", finish_committed=True)
    context, _journals = _snapshot(tmp_path, event_rows=events, raw_rows=raw_rows)
    assert context.history.resolved_plan_item_ids == ()
    forged_history = replace(context.history, returned_models=("forged-returned",))

    with pytest.raises(RecoveryError) as caught:
        replace(context, history=forged_history)

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value)


def test_public_context_rejects_foreign_run_open_attempt(
    tmp_path: Path,
) -> None:
    events, raw = _truth_state_rows("success", finish_committed=False)
    context, journals = _snapshot(tmp_path, event_rows=events, raw_rows=raw)
    assert context.history.open_attempt is not None
    start = context.history.open_attempt.start
    foreign_start = make_event(
        sequence=start.sequence,
        run_id=UUID("42345678-1234-4abc-8def-1234567890d4"),
        occurred_at=start.occurred_at,
        kind="request_started",
        operation_id=start.operation_id,
        execution_session_id=start.execution_session_id,
        payload=start.payload.model_dump(mode="python", round_trip=True),
    )
    requirements = list(context.history.recovery_requirements)
    requirements[0] = replace(
        requirements[0],
        origin_request_started_event_id=foreign_start.event_id,
    )
    forged_history = replace(
        context.history,
        open_attempt=replace(context.history.open_attempt, start=foreign_start),
        recovery_requirements=tuple(requirements),
    )

    with pytest.raises(RecoveryError) as caught:
        forged_context = replace(
            context,
            history=forged_history,
            lifecycle=derive_lifecycle_v1(forged_history),
        )
        _plan(forged_context, journals)

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value)


def test_forged_nested_plan_row_is_revalidated_before_planning(tmp_path: Path) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    forged_payload = context.plan[0].model_dump(
        mode="python",
        round_trip=True,
        warnings=False,
    )
    forged_payload["plan_item_id"] = "plan-secret-canary"
    forged_row = PlanRowV1.model_construct(**forged_payload)

    with pytest.raises(RecoveryError) as caught:
        forged_context = replace(context, plan=(forged_row,))
        _plan(forged_context, journals)

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value, canary="plan-secret-canary")


def test_context_and_snapshots_from_different_verified_pairs_are_rejected(
    tmp_path: Path,
) -> None:
    prepared_path = tmp_path / "prepared"
    active_path = tmp_path / "active"
    prepared_path.mkdir()
    active_path.mkdir()
    capsule, _manifest, _environment, _plan_rows = _context()
    prepared_context, _prepared_journals = _snapshot(
        prepared_path,
        event_rows=(_prepared(capsule),),
    )
    active_events, active_raw = _truth_state_rows("success", finish_committed=False)
    _active_context, active_journals = _snapshot(
        active_path,
        event_rows=active_events,
        raw_rows=active_raw,
    )

    with pytest.raises(RecoveryError) as caught:
        _plan(prepared_context, active_journals)

    assert caught.value.code in {"hash_mismatch", "identity_mismatch", "unstable_snapshot"}
    _assert_content_free(caught.value)


@pytest.mark.parametrize("conflict", ["terminal", "seal"])
def test_terminal_or_seal_tail_conflict_rejects_atomically_and_content_free(
    conflict: str,
    tmp_path: Path,
) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    if conflict == "terminal":
        events, raw = _truth_state_rows("success", finish_committed=True)
        finish = events[-1]
        marker = make_event(
            sequence=len(events),
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
        events = (*events, marker)
    else:
        raw = ()
        seal = make_event(
            sequence=1,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="seal_requested",
            operation_id=SEAL_OPERATION,
            execution_session_id=None,
            payload={
                "seal_transaction_id": str(SEAL_TRANSACTION),
                "expected_generation_status": "incomplete",
                "prior_event_sequence": 0,
            },
        )
        events = (_prepared(capsule), seal)
    canary = "tail-secret-canary"
    event_tail = f'{{"{canary}":"events"}}'.encode()
    raw_tail = f'{{"{canary}":"raw"}}'.encode()
    context, journals = _snapshot(
        tmp_path,
        event_rows=events,
        raw_rows=raw,
        event_tail=event_tail,
        raw_tail=raw_tail,
    )
    original_events = (tmp_path / "events.jsonl").read_bytes()
    original_raw = (tmp_path / "raw.jsonl").read_bytes()

    with pytest.raises(RecoveryError) as caught:
        _plan(context, journals)

    assert caught.value.code == "lifecycle_mismatch"
    _assert_content_free(caught.value, canary=canary)
    assert (tmp_path / "events.jsonl").read_bytes() == original_events
    assert (tmp_path / "raw.jsonl").read_bytes() == original_raw


def test_committed_seal_at_capacity_needs_no_second_seal_reservation(tmp_path: Path) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    seal = make_event(
        sequence=1,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="seal_requested",
        operation_id=SEAL_OPERATION,
        execution_session_id=None,
        payload={
            "seal_transaction_id": str(SEAL_TRANSACTION),
            "expected_generation_status": "incomplete",
            "prior_event_sequence": 0,
        },
    )
    context, journals = _snapshot(
        tmp_path,
        event_rows=(_prepared(capsule), seal),
    )
    immutable = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
        - journals.events.byte_length
        - journals.raw.byte_length
    )

    recovery = _plan(replace(context, immutable_evidence_bytes=immutable), journals)

    assert recovery.disposition == "sealing_interrupted"
    assert recovery.append_events == ()
    assert recovery.seal_reservation_bytes == 0
    assert recovery.post_mutable_bytes == RESOURCE_LIMITS_V1.mutable_capsule_bytes


def test_invalid_operation_identity_error_never_retains_hostile_input(tmp_path: Path) -> None:
    capsule, _manifest, _environment, _plan_rows = _context()
    context, journals = _snapshot(tmp_path, event_rows=(_prepared(capsule),))
    canary = "operation-secret-canary"

    with pytest.raises(RecoveryError) as caught:
        plan_recovery_v1(
            context=context,
            event_snapshot=journals.events,
            raw_snapshot=journals.raw,
            operation_id=canary,  # type: ignore[arg-type]
            occurred_at=RECOVERY_TIME,
        )

    assert caught.value.code == "invalid_model"
    _assert_content_free(caught.value, canary=canary)


def test_snapshot_reserves_new_operation_id_in_exact_identity_pass(tmp_path: object) -> None:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(HistoryError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="report",
                reserved_operation_id=PREPARE_OPERATION,
            )
        assert caught.value.code == "identity_mismatch"

        journals = snapshot_journal_pair(
            descriptor,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="report",
            reserved_operation_id=RECOVERY_OPERATION,
        )
    finally:
        os.close(descriptor)

    assert journals.reserved_operation_id == RECOVERY_OPERATION


def test_reserved_operation_id_cannot_reuse_historical_seal_transaction(
    tmp_path: Path,
) -> None:
    capsule, manifest, environment, plan = _context()
    seal = make_event(
        sequence=1,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="seal_requested",
        operation_id=SEAL_OPERATION,
        execution_session_id=None,
        payload={
            "seal_transaction_id": str(SEAL_TRANSACTION),
            "expected_generation_status": "incomplete",
            "prior_event_sequence": 0,
        },
    )
    (tmp_path / "events.jsonl").write_bytes(  # type: ignore[operator]
        event_jsonl(_prepared(capsule)) + event_jsonl(seal)
    )
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(HistoryError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="report",
                reserved_operation_id=SEAL_TRANSACTION,
            )
    finally:
        os.close(descriptor)

    assert caught.value.code == "identity_mismatch"
