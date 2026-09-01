from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

import pytest

from capsule.test_lifecycle import (
    EXECUTION_OPERATION,
    NOW,
    RUN_ID,
    SESSION_ID,
    _attempt,
    _context,
    _execution_started,
    _prepared,
    _start,
)
from laconian_eval.capsule import history as history_module
from laconian_eval.capsule.attempts import RawAttemptV2, raw_record_sha256
from laconian_eval.capsule.events import EventV1, make_event
from laconian_eval.capsule.history import RawHistorySummaryV1, validate_history_v1
from laconian_eval.capsule.record_models import PlanRowV1


def _three_plan_rows() -> tuple[PlanRowV1, ...]:
    _capsule, _manifest, _environment, plan = _context()
    return tuple(
        plan[0].model_copy(
            update={
                "ordinal": ordinal,
                "plan_item_id": f"{ordinal + 16:064x}",
            }
        )
        for ordinal in range(3)
    )


def _numbered_start(plan: PlanRowV1, call_sequence: int, sequence: int) -> EventV1:
    payload = _start(plan).payload.model_dump(
        mode="python",
        round_trip=True,
        warnings=False,
    )
    payload["call_sequence"] = call_sequence
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_started",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload=payload,
    )


def _numbered_success(
    plan: PlanRowV1,
    call_sequence: int,
    *,
    response_model: str,
    availability: Literal["complete", "partial", "unavailable"],
    redaction_count: int,
) -> RawAttemptV2:
    payload: dict[str, Any] = _attempt(plan).model_dump(
        mode="python",
        round_trip=True,
        warnings=False,
    )
    payload.update(
        call_sequence=call_sequence,
        response_model=response_model,
        output_was_redacted=redaction_count > 0,
        output_redaction_count=redaction_count,
    )
    usage = payload["usage"]
    assert isinstance(usage, dict)
    usage.update(
        input_tokens=1 if availability != "unavailable" else None,
        output_tokens=2 if availability == "complete" else None,
        total_tokens=3 if availability == "complete" else None,
        availability=availability,
    )
    return RawAttemptV2.model_validate(payload)


def _finish(start: EventV1, raw: RawAttemptV2, sequence: int) -> EventV1:
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


def test_validated_history_retains_exact_compact_raw_summary_and_all_returned_models() -> None:
    capsule, manifest, environment, _plan = _context()
    plan = _three_plan_rows()
    events: list[EventV1] = [_prepared(capsule), _execution_started(environment)]
    raw_rows: list[RawAttemptV2] = []
    cases = (
        ("returned-c", "complete", 0),
        ("returned-a", "partial", 1),
        ("returned-b", "unavailable", 3),
    )
    for call_sequence, (response_model, availability, redactions) in enumerate(cases):
        start = _numbered_start(plan[call_sequence], call_sequence, len(events))
        raw = _numbered_success(
            plan[call_sequence],
            call_sequence,
            response_model=response_model,
            availability=availability,  # type: ignore[arg-type]
            redaction_count=redactions,
        )
        events.extend((start, _finish(start, raw, len(events) + 1)))
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
        redacted_output_attempt_count=2,
        redacted_output_replacement_count=4,
    )
    assert history.returned_models == ("returned-a", "returned-b", "returned-c")


def test_validated_history_retains_latest_never_started_block_reason() -> None:
    capsule, manifest, environment, plan = _context()
    blocked = make_event(
        sequence=2,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_blocked",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={"reason": "provider_unavailable"},
    )

    history = validate_history_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        events=(_prepared(capsule), _execution_started(environment), blocked),
        raw_attempts=(),
    )

    assert history.latest_no_call_blocked is True
    assert history.latest_no_call_blocked_reason == "provider_unavailable"


class _ComparisonCountingString(str):
    comparisons = 0

    def __eq__(self, other: object) -> bool:
        type(self).comparisons += 1
        return super().__eq__(other)

    __hash__ = str.__hash__


def test_returned_model_deduplication_is_not_quadratic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, manifest, environment, base_plan = _context()
    item_count = 64
    plan = tuple(
        base_plan[0].model_copy(
            update={
                "ordinal": ordinal,
                "plan_item_id": f"{ordinal + 16:064x}",
            }
        )
        for ordinal in range(item_count)
    )
    events: list[EventV1] = [_prepared(capsule), _execution_started(environment)]
    raw_rows: list[RawAttemptV2] = []
    for call_sequence, row in enumerate(plan):
        start = _numbered_start(row, call_sequence, len(events))
        raw = _numbered_success(
            row,
            call_sequence,
            response_model=f"returned-{call_sequence:03d}",
            availability="complete",
            redaction_count=0,
        )
        events.extend((start, _finish(start, raw, len(events) + 1)))
        raw_rows.append(raw)

    original = history_module._validate_raw_binding

    def counted_binding(*args: Any, **kwargs: Any) -> history_module.RawCommitProjectionV1:
        projection = original(*args, **kwargs)
        assert projection.response_model is not None
        return replace(
            projection,
            response_model=_ComparisonCountingString(projection.response_model),
        )

    monkeypatch.setattr(history_module, "_validate_raw_binding", counted_binding)
    _ComparisonCountingString.comparisons = 0

    history = validate_history_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        events=tuple(events),
        raw_attempts=tuple(raw_rows),
    )

    assert len(history.returned_models) == item_count
    assert _ComparisonCountingString.comparisons < item_count * 4
