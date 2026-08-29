from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from capsule_helpers import (
    capsule_v1_payload,
    environment_v1_payload,
    plan_row_v1_payload,
    resolved_manifest_v2_payload,
)

from laconian_eval import __version__
from laconian_eval.capsule.attempts import (
    RawAttemptV2,
    derive_attempt_id,
    raw_record_sha256,
)
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.capsule.events import EventV1, make_event, make_prepared_event
from laconian_eval.capsule.history import (
    HistoryError,
    derive_lifecycle_v1,
    validate_history_v1,
)
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.record_models import CapsuleV1, EnvironmentV1, PlanRowV1

RUN_ID = UUID("12345678-1234-4abc-8def-1234567890ab")
PREPARE_OPERATION = UUID("12345678-1234-4abc-8def-1234567890ac")
EXECUTION_OPERATION = UUID("12345678-1234-4abc-8def-1234567890ad")
SESSION_ID = UUID("12345678-1234-4abc-8def-1234567890ae")
RECOVERY_OPERATION = UUID("12345678-1234-4abc-8def-1234567890af")
SEAL_OPERATION = UUID("12345678-1234-4abc-8def-1234567890b0")
SEAL_TRANSACTION = UUID("12345678-1234-4abc-8def-1234567890b1")
NOW = datetime(2026, 8, 29, 12, 34, 56, 123456, tzinfo=UTC)


def _context() -> tuple[CapsuleV1, ResolvedManifestV2, EnvironmentV1, tuple[PlanRowV1, ...]]:
    capsule_payload = capsule_v1_payload()
    capsule_payload.update(
        run_id=str(RUN_ID),
        runner_version=__version__,
        manifest_sha256="4" * 64,
        runner_source_sha256="b" * 64,
    )
    capsule = CapsuleV1.model_validate(capsule_payload)

    manifest_payload = resolved_manifest_v2_payload()
    manifest_payload["runner_version"] = __version__
    manifest_payload["provider"] = {
        "kind": "fake",
        "model": "fixture-v1",
        "api_key_env": None,
        "replay_file": None,
    }
    manifest_payload["arms"] = ["if"]
    manifest_capsule = manifest_payload["capsule"]
    assert isinstance(manifest_capsule, dict)
    manifest_capsule["comparisons"] = []
    manifest_capsule["protocol_bindings"] = []
    manifest_payload["repetitions"] = 1
    manifest_payload["retry"] = {"max_transient_retries": 2, "timeout_seconds": 60.0}
    manifest = ResolvedManifestV2.model_validate(manifest_payload)

    environment_payload = environment_v1_payload()
    environment_payload["package_version"] = __version__
    environment_payload["runner_source_sha256"] = capsule.runner_source_sha256
    environment_payload["provider"] = {
        "kind": "fake",
        "requested_model": "fixture-v1",
        "adapter_source_sha256": "c" * 64,
        "transport_policy": "offline",
        "sdk_distribution": None,
        "sdk_version": None,
    }
    environment = EnvironmentV1.model_validate(environment_payload)

    plan_payload = plan_row_v1_payload()
    plan_payload.update(
        plan_item_id="1" * 64,
        scenario_uid="2" * 64,
        case_uid="3" * 64,
        case_id="direct-answer-en",
        locale="en",
        case_definition_sha256="5" * 64,
        arm="if",
        repetition=0,
        prompt_sha256="6" * 64,
        instruction_sha256="7" * 64,
        request_config_sha256="8" * 64,
    )
    return capsule, manifest, environment, (PlanRowV1.model_validate(plan_payload),)


def _session_payload(environment: EnvironmentV1) -> dict[str, Any]:
    runtime = environment.runtime
    provider = environment.provider
    return {
        "schema_version": "1",
        "package_version": environment.package_version,
        "runner_source_sha256": environment.runner_source_sha256,
        "runtime_fingerprint_sha256": runtime.runtime_fingerprint_sha256,
        "python_implementation": runtime.python_implementation,
        "python_version": runtime.python_version,
        "os_family": runtime.os_family,
        "os_release": runtime.os_release,
        "architecture": runtime.architecture,
        "filesystem_class": runtime.filesystem_class,
        "adapter_source_sha256": provider.adapter_source_sha256,
        "sdk_distribution": provider.sdk_distribution,
        "sdk_version": provider.sdk_version,
    }


def _prepared(capsule: CapsuleV1) -> EventV1:
    return make_prepared_event(
        run_id=capsule.run_id,
        operation_id=PREPARE_OPERATION,
        occurred_at=capsule.created_at,
        manifest_sha256=capsule.manifest_sha256,
        input_index_sha256=capsule.input_index_sha256,
        case_index_sha256=capsule.case_index_sha256,
        plan_sha256=capsule.plan_sha256,
        environment_sha256=capsule.environment_sha256,
        runner_source_sha256=capsule.runner_source_sha256,
    )


def _execution_started(environment: EnvironmentV1, sequence: int = 1) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_started",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "resume_from_plan_ordinal": 0,
            "session_environment": _session_payload(environment),
        },
    )


def _attempt(plan: PlanRowV1, reason: str = "success") -> RawAttemptV2:
    attempt_id = derive_attempt_id(RUN_ID, plan.plan_item_id, 1)
    success = reason == "success"
    output = "Done." if success else None
    output_sha = hashlib.sha256(output.encode()).hexdigest() if output is not None else None
    payload: dict[str, Any] = {
        "schema_version": "2",
        "runner_version": __version__,
        "run_id": str(RUN_ID),
        "manifest_sha256": "4" * 64,
        "plan_item_id": plan.plan_item_id,
        "attempt_id": attempt_id,
        "scenario_uid": plan.scenario_uid,
        "case_uid": plan.case_uid,
        "case_id": plan.case_id,
        "locale": plan.locale,
        "case_definition_sha256": plan.case_definition_sha256,
        "arm": plan.arm,
        "repetition": plan.repetition,
        "attempt": 1,
        "terminal": reason != "safe_retry",
        "call_sequence": 0,
        "retry_of_attempt": None,
        "backoff_ms": 100 if reason == "safe_retry" else None,
        "delivery_certainty": (
            "response_received"
            if reason in {"success", "authentication", "provider_rejected"}
            else "unknown"
            if reason == "ambiguous_delivery"
            else "definitely_rejected"
        ),
        "prompt_sha256": plan.prompt_sha256,
        "instruction_sha256": plan.instruction_sha256,
        "request_config_sha256": plan.request_config_sha256,
        "provider": "fake",
        "model": "fixture-v1",
        "response_model": "returned-a" if success else None,
        "started_at": NOW,
        "elapsed_ms": 5,
        "output_text": output,
        "output_sha256": output_sha,
        "response_id": None,
        "output_was_redacted": False,
        "output_redaction_count": 0,
        "discarded_output_byte_length": None,
        "discarded_output_sha256": None,
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cached_input_tokens": None,
            "availability": "unavailable",
            "source": "provider",
            "cache_accounting": "not_reported",
        },
        "request_id": None,
        "finish_reason": "stop" if success else None,
        "error": None
        if success
        else {
            "kind": "authentication" if reason == "authentication" else "transport",
            "message": "authentication complete ambiguous",
            "retryable": reason in {"safe_retry", "ambiguous_delivery"},
            "request_id": None,
        },
        "terminal_reason": (
            None
            if reason == "safe_retry"
            else "authentication_stopped"
            if reason == "authentication"
            else reason
        ),
    }
    if success:
        payload["response_id"] = stable_digest(
            "laconian-response-v1",
            {
                "run_id": RUN_ID,
                "plan_item_id": plan.plan_item_id,
                "attempt_id": attempt_id,
                "case_uid": plan.case_uid,
                "instruction_sha256": plan.instruction_sha256,
                "output_sha256": output_sha,
            },
        )
    return RawAttemptV2.model_validate(payload)


def _start(plan: PlanRowV1, sequence: int = 2) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_started",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "call_sequence": 0,
            "plan_item_id": plan.plan_item_id,
            "attempt_id": derive_attempt_id(RUN_ID, plan.plan_item_id, 1),
            "attempt": 1,
            "retry_of_attempt": None,
            "request_config_sha256": plan.request_config_sha256,
            "prompt_sha256": plan.prompt_sha256,
            "case_definition_sha256": plan.case_definition_sha256,
            "instruction_sha256": plan.instruction_sha256,
            "provider": "fake",
            "model": "fixture-v1",
        },
    )


def _finish(start: EventV1, attempt: RawAttemptV2, sequence: int = 3) -> EventV1:
    return make_event(
        sequence=sequence,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_finished",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "call_sequence": 0,
            "plan_item_id": attempt.plan_item_id,
            "attempt_id": attempt.attempt_id,
            "request_started_event_id": start.event_id,
            "raw_record_sha256": raw_record_sha256(attempt),
            "recovered": False,
        },
    )


def _validate(events: tuple[EventV1, ...], raw: tuple[RawAttemptV2, ...] = ()):
    capsule, manifest, environment, plan = _context()
    return validate_history_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        events=events,
        raw_attempts=raw,
    )


def test_prepared_only_history_derives_exact_never_started_projection() -> None:
    capsule, _manifest, _environment, plan = _context()
    history = _validate((_prepared(capsule),))
    lifecycle = derive_lifecycle_v1(history)
    assert lifecycle.state == "PREPARED"
    assert lifecycle.missing_plan_item_ids == (plan[0].plan_item_id,)
    assert lifecycle.operational_blocker_codes == ("never_started",)
    assert history.next_unresolved_plan_ordinal == 0
    assert history.next_call_sequence == 0
    assert history.next_attempt_number == 1


def test_clean_safe_retry_retains_compact_next_attempt_cursor() -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "safe_retry")
    finish = _finish(start, attempt)

    history = _validate(
        (_prepared(capsule), _execution_started(environment), start, finish),
        (attempt,),
    )

    assert history.next_unresolved_plan_ordinal == 0
    assert history.next_call_sequence == 1
    assert history.next_attempt_number == 2
    assert history.open_attempt is None
    assert history.recovery_requirements == ()


def test_unmatched_request_start_is_markerless_ambiguity() -> None:
    capsule, _manifest, environment, plan = _context()
    history = _validate((_prepared(capsule), _execution_started(environment), _start(plan[0])))
    lifecycle = derive_lifecycle_v1(history)
    assert lifecycle.state == "AMBIGUOUS_INFLIGHT"
    assert lifecycle.operational_blocker_codes == ("ambiguous_inflight",)
    assert history.recovery_requirements == ()


@pytest.mark.parametrize(
    ("reason", "state", "requirement"),
    [
        ("success", "GENERATION_COMPLETE", ("request_finished", "generation_completed")),
        (
            "authentication",
            "AUTHENTICATION_STOPPED",
            ("request_finished", "authentication_stopped"),
        ),
        ("ambiguous_delivery", "AMBIGUOUS_INFLIGHT", ("request_finished", "delivery_ambiguous")),
        ("safe_retry", "INTERRUPTED", ("request_finished",)),
    ],
)
def test_raw_without_finish_derives_safety_and_causal_recovery_requirements(
    reason: str, state: str, requirement: tuple[str, ...]
) -> None:
    capsule, _manifest, environment, plan = _context()
    attempt = _attempt(plan[0], reason)
    history = _validate(
        (_prepared(capsule), _execution_started(environment), _start(plan[0])),
        (attempt,),
    )
    assert derive_lifecycle_v1(history).state == state
    assert tuple(item.kind for item in history.recovery_requirements) == requirement
    finish_requirement = history.recovery_requirements[0]
    assert finish_requirement.plan_item_id == plan[0].plan_item_id
    assert finish_requirement.attempt_id == attempt.attempt_id
    assert finish_requirement.origin_request_started_event_id == _start(plan[0]).event_id
    assert finish_requirement.raw_record_sha256 == raw_record_sha256(attempt)


def test_completion_marker_is_validated_against_final_finish() -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0])
    finish = _finish(start, attempt)
    completed = make_event(
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
    history = _validate(
        (_prepared(capsule), _execution_started(environment), start, finish, completed),
        (attempt,),
    )
    assert derive_lifecycle_v1(history).state == "GENERATION_COMPLETE"
    assert history.recovery_requirements == ()


@pytest.mark.parametrize("marker_kind", ["authentication_stopped", "generation_completed"])
def test_terminal_marker_link_mismatches_use_identity_taxonomy(marker_kind: str) -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(
        plan[0],
        "authentication" if marker_kind == "authentication_stopped" else "success",
    )
    finish = _finish(start, attempt)
    if marker_kind == "authentication_stopped":
        marker = make_event(
            sequence=4,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="authentication_stopped",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload={
                "plan_item_id": start.payload.plan_item_id,
                "attempt_id": start.payload.attempt_id,
                "origin_request_started_event_id": "a" * 64,
                "recovered": False,
            },
        )
    else:
        marker = make_event(
            sequence=4,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="generation_completed",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload={
                "terminal_plan_item_count": len(plan),
                "final_plan_ordinal": len(plan) - 1,
                "origin_request_finished_event_id": "a" * 64,
                "recovered": False,
            },
        )
    with pytest.raises(HistoryError) as caught:
        _validate(
            (_prepared(capsule), _execution_started(environment), start, finish, marker),
            (attempt,),
        )

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "identity_mismatch",
        "events",
        4,
    )


def test_normal_finish_allows_fresh_recovery_operation_for_missing_completion() -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0])
    finish = _finish(start, attempt)
    completed = make_event(
        sequence=4,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="generation_completed",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "terminal_plan_item_count": 1,
            "final_plan_ordinal": 0,
            "origin_request_finished_event_id": finish.event_id,
            "recovered": True,
        },
    )
    history = _validate(
        (_prepared(capsule), _execution_started(environment), start, finish, completed),
        (attempt,),
    )
    assert derive_lifecycle_v1(history).state == "GENERATION_COMPLETE"


def test_recovered_finish_and_completion_share_recovery_operation() -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0])
    finish = make_event(
        sequence=3,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_finished",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "call_sequence": 0,
            "plan_item_id": attempt.plan_item_id,
            "attempt_id": attempt.attempt_id,
            "request_started_event_id": start.event_id,
            "raw_record_sha256": raw_record_sha256(attempt),
            "recovered": True,
        },
    )
    completed = make_event(
        sequence=4,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="generation_completed",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "terminal_plan_item_count": 1,
            "final_plan_ordinal": 0,
            "origin_request_finished_event_id": finish.event_id,
            "recovered": True,
        },
    )
    history = _validate(
        (_prepared(capsule), _execution_started(environment), start, finish, completed),
        (attempt,),
    )
    assert history.recovery_requirements == ()


def test_provider_diagnostic_text_cannot_drive_auth_or_ambiguity_state() -> None:
    capsule, _manifest, environment, plan = _context()
    attempt = _attempt(plan[0], "provider_rejected")
    start = _start(plan[0])
    finish = _finish(start, attempt)
    history = _validate(
        (_prepared(capsule), _execution_started(environment), start, finish),
        (attempt,),
    )
    assert derive_lifecycle_v1(history).state == "GENERATION_COMPLETE"


def test_history_rejects_declared_sequence_gap_by_physical_index_content_free() -> None:
    capsule, _manifest, environment, _plan = _context()
    with pytest.raises(HistoryError) as caught:
        _validate((_prepared(capsule), _execution_started(environment, sequence=2)))
    assert caught.value.code == "history_mismatch"
    assert caught.value.ledger == "events"
    assert caught.value.row_index == 1
    assert str(caught.value) == "capsule history rejected"


def test_request_start_attempt_identity_is_checked_without_raw() -> None:
    capsule, _manifest, environment, plan = _context()
    forged = make_event(
        sequence=2,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="request_started",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={**_start(plan[0]).payload.model_dump(mode="python"), "attempt_id": "a" * 64},
    )
    with pytest.raises(HistoryError) as caught:
        _validate((_prepared(capsule), _execution_started(environment), forged))
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "identity_mismatch",
        "events",
        2,
    )


def test_tail_recovery_and_following_execution_share_one_operation() -> None:
    capsule, _manifest, environment, _plan = _context()
    tail = make_event(
        sequence=1,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="tail_recovered",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "ledger": "events",
            "removed_byte_count": 3,
            "removed_sha256": "a" * 64,
            "related_attempt_id": None,
        },
    )
    started = make_event(
        sequence=2,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_started",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "resume_from_plan_ordinal": 0,
            "session_environment": _session_payload(environment),
        },
    )
    history = _validate((_prepared(capsule), tail, started))
    assert derive_lifecycle_v1(history).state == "INTERRUPTED"


def test_tail_recovery_allows_fresh_following_execution_after_crash_boundary() -> None:
    capsule, _manifest, environment, _plan = _context()
    tail = make_event(
        sequence=1,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="tail_recovered",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "ledger": "events",
            "removed_byte_count": 3,
            "removed_sha256": "a" * 64,
            "related_attempt_id": None,
        },
    )
    history = _validate((_prepared(capsule), tail, _execution_started(environment, sequence=2)))
    assert derive_lifecycle_v1(history).state == "INTERRUPTED"


def test_tail_recovery_rejects_reuse_of_prior_operation() -> None:
    capsule, _manifest, environment, _plan = _context()
    tail = make_event(
        sequence=1,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="tail_recovered",
        operation_id=RECOVERY_OPERATION,
        execution_session_id=None,
        payload={
            "ledger": "events",
            "removed_byte_count": 3,
            "removed_sha256": "a" * 64,
            "related_attempt_id": None,
        },
    )
    started = make_event(
        sequence=2,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_started",
        operation_id=PREPARE_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "resume_from_plan_ordinal": 0,
            "session_environment": _session_payload(environment),
        },
    )
    with pytest.raises(HistoryError) as caught:
        _validate((_prepared(capsule), tail, started))
    assert caught.value.code == "identity_mismatch"


def test_terminal_completion_allows_only_optional_seal_suffix() -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0])
    finish = _finish(start, attempt)
    completed = make_event(
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
    forbidden = _execution_started(environment, sequence=5)
    with pytest.raises(HistoryError) as caught:
        _validate(
            (
                _prepared(capsule),
                _execution_started(environment),
                start,
                finish,
                completed,
                forbidden,
            ),
            (attempt,),
        )
    assert caught.value.code == "lifecycle_mismatch"
    assert caught.value.row_index == 5


def test_seal_request_has_precedence_and_retains_underlying_completion() -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0])
    finish = _finish(start, attempt)
    completed = make_event(
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
    seal = make_event(
        sequence=5,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="seal_requested",
        operation_id=SEAL_OPERATION,
        execution_session_id=None,
        payload={
            "seal_transaction_id": str(SEAL_TRANSACTION),
            "expected_generation_status": "complete",
            "prior_event_sequence": 4,
        },
    )
    history = _validate(
        (_prepared(capsule), _execution_started(environment), start, finish, completed, seal),
        (attempt,),
    )
    lifecycle = derive_lifecycle_v1(history)
    assert lifecycle.state == "SEALING_INTERRUPTED"
    assert lifecycle.missing_plan_item_ids == ()
    assert lifecycle.operational_blocker_codes == ()
