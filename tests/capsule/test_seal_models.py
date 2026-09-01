"""Strict immutable seal schema and deterministic byte tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from capsule.test_lifecycle import _context as lifecycle_context
from capsule.test_lifecycle import _start as lifecycle_start
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes
from laconian_eval.capsule.events import (
    RequestStartedEventV1,
    SealRequestedEventV1,
    make_event,
)
from laconian_eval.capsule.history import (
    AttemptCommitV1,
    LifecycleProjectionV1,
    RawCommitProjectionV1,
    RawHistorySummaryV1,
    RecoveryRequirementV1,
    ValidatedHistoryV1,
)
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.record_models import CapsuleV1, EnvironmentV1
from laconian_eval.capsule.seal_models import (
    SealDisclosuresV1,
    SealFileV1,
    SealModelError,
    SealUsageAvailabilityCountsV1,
    SealV1,
    capsule_sha256,
    derive_seal_v1,
    seal_bytes,
)
from tests.capsule_helpers import (
    SHA_A,
    SHA_B,
    SHA_C,
    SHA_D,
    UUID_A,
    UUID_B,
    capsule_v1_payload,
    environment_v1_payload,
    resolved_manifest_v2_payload,
    seal_v1_payload,
)

_SEAL_OPERATION = UUID("323e4567-e89b-42d3-a456-426614174002")
_OPEN_OPERATION = UUID("423e4567-e89b-42d3-a456-426614174003")
_OPEN_SESSION = UUID("523e4567-e89b-42d3-a456-426614174004")
_FOREIGN_RUN = UUID("623e4567-e89b-42d3-a456-426614174005")
_CAPSULE_RUN_ID = UUID(UUID_A)
_SEALED_AT = datetime(2026, 8, 30, 12, 34, 56, 123456, tzinfo=UTC)


def _invalid(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SealV1.model_validate(payload)


def test_seal_v1_round_trips_exact_shape() -> None:
    payload = seal_v1_payload()

    seal = SealV1.model_validate(payload)

    assert seal.model_dump(mode="json") == payload
    assert list(seal.model_dump().keys()) == [
        "seal_schema_version",
        "run_id",
        "seal_transaction_id",
        "generation_status",
        "structural_integrity",
        "missing_plan_item_ids",
        "operational_blocker_codes",
        "never_started_detail",
        "disclosures",
        "final_event_sequence",
        "raw_attempt_count",
        "sealed_at",
        "files",
    ]
    assert list(seal.disclosures.model_dump().keys()) == [
        "source_state",
        "returned_models",
        "usage_availability_counts",
        "redacted_output_attempt_count",
        "redacted_output_replacement_count",
        "dataset_ids",
        "protocol_binding_ids",
    ]
    assert list(seal.disclosures.usage_availability_counts.model_dump().keys()) == [
        "complete",
        "partial",
        "unavailable",
    ]
    assert list(seal.files[0].model_dump().keys()) == ["path", "byte_length", "sha256"]


def test_seal_models_are_frozen_strict_and_extra_forbid() -> None:
    seal = SealV1.model_validate(seal_v1_payload())
    with pytest.raises(ValidationError):
        seal.raw_attempt_count = 41  # type: ignore[misc]

    for path, value in (
        (("raw_attempt_count",), True),
        (("files", 0, "byte_length"), 321.0),
        (("disclosures", "usage_availability_counts", "complete"), "40"),
    ):
        payload = seal_v1_payload()
        target: Any = payload
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = value
        _invalid(payload)

    for path in ((), ("disclosures",), ("files", 0)):
        payload = seal_v1_payload()
        target = payload
        for component in path:
            target = target[component]
        target["unknown"] = "forbidden"
        _invalid(payload)


@pytest.mark.parametrize(
    "field",
    ["returned_models", "dataset_ids", "protocol_binding_ids"],
)
def test_seal_disclosure_arrays_require_exact_utf8_sort_and_uniqueness(field: str) -> None:
    payload = seal_v1_payload()
    disclosures = payload["disclosures"]
    assert isinstance(disclosures, dict)
    disclosures[field] = ["z", "é", "a"]
    _invalid(payload)

    disclosures[field] = ["a", "a"]
    _invalid(payload)


def test_seal_missing_ids_files_and_blockers_require_exact_order() -> None:
    payload = seal_v1_payload()
    payload.update(
        generation_status="incomplete",
        missing_plan_item_ids=[SHA_B, SHA_A],
        operational_blocker_codes=["interrupted"],
    )
    _invalid(payload)

    payload["missing_plan_item_ids"] = [SHA_A, SHA_A]
    _invalid(payload)

    payload["missing_plan_item_ids"] = [SHA_A]
    payload["operational_blocker_codes"] = ["interrupted", "never_started"]
    _invalid(payload)

    payload = seal_v1_payload()
    payload["files"] = list(reversed(payload["files"]))
    _invalid(payload)

    payload["files"] = [payload["files"][0], payload["files"][0]]
    _invalid(payload)


@pytest.mark.parametrize(
    ("blocker", "detail"),
    [
        ("never_started", "credential_unavailable"),
        ("never_started", "provider_unavailable"),
        ("never_started", "operator_abandoned"),
        ("interrupted", None),
        ("ambiguous_inflight", None),
        ("authentication_stopped", None),
    ],
)
def test_seal_v1_accepts_exact_incomplete_matrix(blocker: str, detail: str | None) -> None:
    payload = seal_v1_payload()
    payload.update(
        generation_status="incomplete",
        missing_plan_item_ids=[SHA_A],
        operational_blocker_codes=[blocker],
        never_started_detail=detail,
    )
    assert SealV1.model_validate(payload).model_dump(mode="json") == payload


@pytest.mark.parametrize(
    ("status", "missing", "blockers", "detail"),
    [
        ("complete", [SHA_A], [], None),
        ("complete", [], ["interrupted"], None),
        ("complete", [], [], "operator_abandoned"),
        ("incomplete", [], ["interrupted"], None),
        ("incomplete", [SHA_A], [], None),
        ("incomplete", [SHA_A], ["interrupted", "ambiguous_inflight"], None),
        ("incomplete", [SHA_A], ["never_started"], None),
        ("incomplete", [SHA_A], ["interrupted"], "operator_abandoned"),
    ],
)
def test_seal_v1_rejects_every_other_status_matrix(
    status: str,
    missing: list[str],
    blockers: list[str],
    detail: str | None,
) -> None:
    payload = seal_v1_payload()
    payload.update(
        generation_status=status,
        missing_plan_item_ids=missing,
        operational_blocker_codes=blockers,
        never_started_detail=detail,
    )
    _invalid(payload)


def test_seal_v1_requires_usage_count_sum_and_consistent_redaction_counts() -> None:
    payload = seal_v1_payload()
    counts = payload["disclosures"]["usage_availability_counts"]
    counts["partial"] = 1
    _invalid(payload)

    payload = seal_v1_payload()
    payload["disclosures"]["redacted_output_attempt_count"] = 2
    payload["disclosures"]["redacted_output_replacement_count"] = 1
    _invalid(payload)

    payload = seal_v1_payload()
    payload["disclosures"]["redacted_output_replacement_count"] = 1
    _invalid(payload)

    payload = seal_v1_payload()
    payload["raw_attempt_count"] = 0
    payload["disclosures"]["usage_availability_counts"]["complete"] = 0
    _invalid(payload)


@pytest.mark.parametrize(
    "path",
    [
        ".laconian.lock",
        "seal.json",
        f".seal.{UUID_B}.tmp",
        "inputs",
        "unknown.txt",
    ],
)
def test_seal_v1_rejects_inventory_exclusions(path: str) -> None:
    payload = seal_v1_payload()
    payload["files"][0]["path"] = path
    payload["files"] = sorted(payload["files"], key=lambda item: item["path"].encode("utf-8"))
    _invalid(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", "123e4567-e89b-12d3-a456-426614174000"),
        ("run_id", "123E4567-E89B-42D3-A456-426614174000"),
        ("seal_transaction_id", UUID_A),
        ("sealed_at", "2026-08-30T12:34:56Z"),
        ("sealed_at", "2026-08-30T15:34:56.123456+03:00"),
    ],
)
def test_seal_v1_rejects_noncanonical_uuid_and_timestamp_boundaries(field: str, value: str) -> None:
    payload = seal_v1_payload()
    payload[field] = value
    _invalid(payload)


def test_seal_v1_accepts_aware_datetime_and_serializes_canonically() -> None:
    payload = seal_v1_payload()
    payload["sealed_at"] = datetime(2026, 8, 30, 12, 34, 56, 123456, tzinfo=UTC)
    seal = SealV1.model_validate(payload)
    assert seal.model_dump(mode="json")["sealed_at"] == "2026-08-30T12:34:56.123456Z"


@pytest.mark.parametrize(
    ("nested_type", "field", "bad_value"),
    [
        (SealFileV1, "byte_length", True),
        (SealUsageAvailabilityCountsV1, "complete", True),
        (SealDisclosuresV1, "returned_models", ("z", "a")),
    ],
)
def test_seal_v1_class_bound_revalidates_model_construct_nested_models(
    nested_type: type[Any], field: str, bad_value: Any
) -> None:
    payload = seal_v1_payload()
    if nested_type is SealFileV1:
        nested_payload = deepcopy(payload["files"][0])
        nested_payload[field] = bad_value
        payload["files"][0] = nested_type.model_construct(**nested_payload)
    elif nested_type is SealUsageAvailabilityCountsV1:
        nested_payload = deepcopy(payload["disclosures"]["usage_availability_counts"])
        nested_payload[field] = bad_value
        payload["disclosures"]["usage_availability_counts"] = nested_type.model_construct(
            **nested_payload
        )
    else:
        nested_payload = deepcopy(payload["disclosures"])
        nested_payload[field] = bad_value
        nested_payload["usage_availability_counts"] = SealUsageAvailabilityCountsV1.model_validate(
            nested_payload["usage_availability_counts"]
        )
        payload["disclosures"] = nested_type.model_construct(**nested_payload)
    _invalid(payload)


def test_seal_bytes_and_hash_are_exact_canonical_projection() -> None:
    seal = SealV1.model_validate(seal_v1_payload())
    expected = canonical_json(seal.model_dump(mode="json"))

    assert seal_bytes(seal) == expected
    assert capsule_sha256(seal) == sha256_bytes(expected)


def _seal_request(status: str, *, sequence: int = 83) -> SealRequestedEventV1:
    event = make_event(
        sequence=sequence,
        run_id=UUID(UUID_A),
        occurred_at=_SEALED_AT,
        kind="seal_requested",
        operation_id=_SEAL_OPERATION,
        execution_session_id=None,
        payload={
            "seal_transaction_id": UUID_B,
            "expected_generation_status": status,
            "prior_event_sequence": sequence - 1,
        },
    )
    assert type(event) is SealRequestedEventV1
    return event


def _history(
    *,
    status: str,
    missing: tuple[str, ...],
    blocker: str | None,
    seal_requested: SealRequestedEventV1,
    latest_no_call_blocked_reason: str | None = None,
    raw_counts: tuple[int, int, int, int, int, int] = (4, 2, 1, 1, 2, 3),
) -> ValidatedHistoryV1:
    raw_summary = RawHistorySummaryV1(
        raw_attempt_count=raw_counts[0],
        usage_complete_count=raw_counts[1],
        usage_partial_count=raw_counts[2],
        usage_unavailable_count=raw_counts[3],
        redacted_output_attempt_count=raw_counts[4],
        redacted_output_replacement_count=raw_counts[5],
    )
    complete = status == "complete"
    returned_models = (
        ("gpt-5.6-sol-2026-08-30", "gpt-5.6-sol-2026-08-31") if raw_counts[0] >= 2 else ()
    )
    return ValidatedHistoryV1(
        resolved_plan_item_ids=(SHA_A, SHA_B, SHA_C, SHA_D) if complete else (),
        missing_plan_item_ids=missing,
        returned_models=returned_models,
        raw_summary=raw_summary,
        next_unresolved_plan_ordinal=None if complete else 0,
        next_call_sequence=raw_counts[0],
        next_attempt_number=None if complete else 1,
        open_attempt=None,
        recovery_requirements=(),
        request_history_present=raw_counts[0] > 0,
        execution_history_present=(
            raw_counts[0] > 0
            or blocker == "interrupted"
            or latest_no_call_blocked_reason is not None
        ),
        latest_no_call_blocked=latest_no_call_blocked_reason is not None,
        latest_no_call_blocked_reason=latest_no_call_blocked_reason,
        latest_event_recovered=False,
        has_ambiguous_delivery=blocker == "ambiguous_inflight",
        has_authentication_stop=blocker == "authentication_stopped",
        seal_requested=seal_requested,
    )


def _inputs() -> tuple[CapsuleV1, ResolvedManifestV2, EnvironmentV1]:
    return (
        CapsuleV1.model_validate(capsule_v1_payload()),
        ResolvedManifestV2.model_validate(resolved_manifest_v2_payload()),
        EnvironmentV1.model_validate(environment_v1_payload()),
    )


def _files() -> tuple[SealFileV1, ...]:
    return (
        SealFileV1(path="events.jsonl", byte_length=654, sha256=SHA_B),
        SealFileV1(path="capsule.json", byte_length=321, sha256=SHA_A),
    )


def test_derive_seal_v1_is_a_total_projection_of_validated_history() -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("complete")
    history = _history(status="complete", missing=(), blocker=None, seal_requested=request)
    lifecycle = LifecycleProjectionV1("SEALING_INTERRUPTED", (), ())

    first = derive_seal_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        history=history,
        lifecycle=lifecycle,
        seal_requested=request,
        files=_files(),
    )
    second = derive_seal_v1(
        capsule=CapsuleV1.model_validate(capsule.model_dump(mode="python")),
        manifest=ResolvedManifestV2.model_validate(manifest.model_dump(mode="python")),
        environment=EnvironmentV1.model_validate(environment.model_dump(mode="python")),
        history=history,
        lifecycle=lifecycle,
        seal_requested=SealRequestedEventV1.model_validate(request.model_dump(mode="python")),
        files=tuple(reversed(_files())),
    )

    assert first.seal_schema_version == "1"
    assert first.run_id == capsule.run_id
    assert first.seal_transaction_id == request.payload.seal_transaction_id
    assert first.generation_status == request.payload.expected_generation_status
    assert first.structural_integrity == "valid"
    assert first.missing_plan_item_ids == ()
    assert first.operational_blocker_codes == ()
    assert first.never_started_detail is None
    assert first.disclosures.source_state == "clean"
    assert first.disclosures.returned_models == history.returned_models
    assert first.disclosures.usage_availability_counts.model_dump() == {
        "complete": 2,
        "partial": 1,
        "unavailable": 1,
    }
    assert first.disclosures.redacted_output_attempt_count == 2
    assert first.disclosures.redacted_output_replacement_count == 3
    assert first.disclosures.dataset_ids == ("dataset-alpha", "dataset-beta")
    assert first.disclosures.protocol_binding_ids == ("rubric-v1",)
    assert first.final_event_sequence == request.sequence
    assert first.raw_attempt_count == 4
    assert first.sealed_at == request.occurred_at
    assert tuple(item.path for item in first.files) == ("capsule.json", "events.jsonl")
    assert seal_bytes(first) == seal_bytes(second)
    assert capsule_sha256(first) == capsule_sha256(second)


@pytest.mark.parametrize(
    ("blocker", "reason", "detail", "raw_counts"),
    [
        ("never_started", "credential_unavailable", "credential_unavailable", (0, 0, 0, 0, 0, 0)),
        ("never_started", "provider_unavailable", "provider_unavailable", (0, 0, 0, 0, 0, 0)),
        ("never_started", None, "operator_abandoned", (0, 0, 0, 0, 0, 0)),
        ("interrupted", None, None, (0, 0, 0, 0, 0, 0)),
        ("ambiguous_inflight", None, None, (1, 0, 0, 1, 0, 0)),
        ("authentication_stopped", None, None, (1, 0, 0, 1, 0, 0)),
    ],
)
def test_derive_seal_v1_projects_exact_incomplete_matrix(
    blocker: str,
    reason: str | None,
    detail: str | None,
    raw_counts: tuple[int, int, int, int, int, int],
) -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("incomplete")
    history = _history(
        status="incomplete",
        missing=(SHA_A,),
        blocker=blocker,
        seal_requested=request,
        latest_no_call_blocked_reason=reason,
        raw_counts=raw_counts,
    )
    lifecycle = LifecycleProjectionV1("SEALING_INTERRUPTED", (SHA_A,), (blocker,))

    seal = derive_seal_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        history=history,
        lifecycle=lifecycle,
        seal_requested=request,
        files=tuple(reversed(_files())),
    )

    assert seal.generation_status == "incomplete"
    assert seal.missing_plan_item_ids == (SHA_A,)
    assert seal.operational_blocker_codes == (blocker,)
    assert seal.never_started_detail == detail


@pytest.mark.parametrize(
    ("checkout_binding", "git_state", "source_state"),
    [
        ("bound", "clean", "clean"),
        ("bound", "dirty", "dirty"),
        ("bound", "unavailable", "unavailable"),
        ("unbound", "unavailable", "unbound"),
        ("unavailable", "unavailable", "unavailable"),
    ],
)
def test_derive_seal_v1_uses_exhaustive_source_state_table(
    checkout_binding: str,
    git_state: str,
    source_state: str,
) -> None:
    capsule, manifest, _environment = _inputs()
    environment_payload = environment_v1_payload()
    environment_payload["checkout_binding"] = checkout_binding
    environment_payload["git_state"] = git_state
    if checkout_binding != "bound" or git_state == "unavailable":
        environment_payload["git_commit"] = None
    if checkout_binding != "bound":
        environment_payload["uv_lock"] = {"availability": "unavailable", "sha256": None}
    environment = EnvironmentV1.model_validate(environment_payload)
    request = _seal_request("complete")
    history = _history(status="complete", missing=(), blocker=None, seal_requested=request)

    seal = derive_seal_v1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        history=history,
        lifecycle=LifecycleProjectionV1("SEALING_INTERRUPTED", (), ()),
        seal_requested=request,
        files=_files(),
    )
    assert seal.disclosures.source_state == source_state


def test_derive_seal_v1_rejects_mismatched_boundaries_content_free() -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("complete")
    history = _history(status="complete", missing=(), blocker=None, seal_requested=request)
    other_request = _seal_request("complete", sequence=84)

    mutations = (
        {"seal_requested": other_request},
        {"lifecycle": LifecycleProjectionV1("SEALING_INTERRUPTED", (SHA_A,), ("interrupted",))},
        {"capsule": CapsuleV1.model_construct(**(capsule.model_dump() | {"run_id": "bad"}))},
    )
    base: dict[str, Any] = {
        "capsule": capsule,
        "manifest": manifest,
        "environment": environment,
        "history": history,
        "lifecycle": LifecycleProjectionV1("SEALING_INTERRUPTED", (), ()),
        "seal_requested": request,
        "files": _files(),
    }
    for mutation in mutations:
        with pytest.raises(SealModelError) as caught:
            derive_seal_v1(**(base | mutation))
        assert caught.value.code == "seal_mismatch"
        assert str(caught.value) == "capsule seal rejected"


def test_derive_seal_v1_recomputes_lifecycle_blocker_precedence() -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("incomplete")
    history = _history(
        status="incomplete",
        missing=(SHA_A,),
        blocker="ambiguous_inflight",
        seal_requested=request,
        raw_counts=(1, 0, 0, 1, 0, 0),
    )

    with pytest.raises(SealModelError) as caught:
        derive_seal_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            history=history,
            lifecycle=LifecycleProjectionV1(
                "SEALING_INTERRUPTED",
                (SHA_A,),
                ("interrupted",),
            ),
            seal_requested=request,
            files=_files(),
        )
    assert caught.value.code == "seal_mismatch"
    assert str(caught.value) == "capsule seal rejected"


def test_derive_seal_v1_rejects_raw_summary_cursor_mismatch() -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("complete")
    history = _history(status="complete", missing=(), blocker=None, seal_requested=request)
    forged = replace(
        history,
        returned_models=(),
        raw_summary=RawHistorySummaryV1(0, 0, 0, 0, 0, 0),
    )

    with pytest.raises(SealModelError) as caught:
        derive_seal_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            history=forged,
            lifecycle=LifecycleProjectionV1("SEALING_INTERRUPTED", (), ()),
            seal_requested=request,
            files=_files(),
        )
    assert caught.value.code == "seal_mismatch"
    assert str(caught.value) == "capsule seal rejected"


def test_derive_seal_v1_maps_forged_history_boundaries_content_free() -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("complete")
    history = _history(status="complete", missing=(), blocker=None, seal_requested=request)
    forged_summary = RawHistorySummaryV1(
        raw_attempt_count=True,  # type: ignore[arg-type]
        usage_complete_count=2,
        usage_partial_count=1,
        usage_unavailable_count=1,
        redacted_output_attempt_count=2,
        redacted_output_replacement_count=3,
    )
    malformed_history = object.__new__(ValidatedHistoryV1)
    malformed_lifecycle = object.__new__(LifecycleProjectionV1)

    base: dict[str, Any] = {
        "capsule": capsule,
        "manifest": manifest,
        "environment": environment,
        "history": history,
        "lifecycle": LifecycleProjectionV1("SEALING_INTERRUPTED", (), ()),
        "seal_requested": request,
        "files": _files(),
    }
    for mutation in (
        {"history": replace(history, raw_summary=forged_summary)},
        {"history": malformed_history},
        {"lifecycle": malformed_lifecycle},
    ):
        with pytest.raises(SealModelError) as caught:
            derive_seal_v1(**(base | mutation))
        assert caught.value.code == "seal_mismatch"
        assert str(caught.value) == "capsule seal rejected"


@pytest.mark.parametrize(
    "field",
    ["has_ambiguous_delivery", "has_authentication_stop"],
)
def test_derive_seal_v1_rejects_terminal_call_state_without_request_history(
    field: str,
) -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("incomplete")
    history = _history(
        status="incomplete",
        missing=(SHA_A,),
        blocker=None,
        seal_requested=request,
        raw_counts=(0, 0, 0, 0, 0, 0),
    )
    forged_history = replace(history, **{field: True})
    blocker = (
        "ambiguous_inflight" if field == "has_ambiguous_delivery" else "authentication_stopped"
    )

    with pytest.raises(SealModelError) as caught:
        derive_seal_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            history=forged_history,
            lifecycle=LifecycleProjectionV1("SEALING_INTERRUPTED", (SHA_A,), (blocker,)),
            seal_requested=request,
            files=_files(),
        )

    assert caught.value.code == "seal_mismatch"
    assert str(caught.value) == "capsule seal rejected"


def test_derive_seal_v1_rejects_returned_model_without_resolved_success() -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("incomplete")
    history = _history(
        status="incomplete",
        missing=(SHA_A,),
        blocker="interrupted",
        seal_requested=request,
        raw_counts=(1, 0, 0, 1, 0, 0),
    )
    forged_history = replace(history, returned_models=("forged-returned",))

    with pytest.raises(SealModelError) as caught:
        derive_seal_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            history=forged_history,
            lifecycle=LifecycleProjectionV1("SEALING_INTERRUPTED", (SHA_A,), ("interrupted",)),
            seal_requested=request,
            files=_files(),
        )

    assert caught.value.code == "seal_mismatch"
    assert str(caught.value) == "capsule seal rejected"


def _open_attempt(*, with_raw: bool) -> AttemptCommitV1:
    _capsule, _manifest, _environment, plan = lifecycle_context()
    raw = (
        RawCommitProjectionV1(
            call_sequence=0,
            plan_item_id=plan[0].plan_item_id,
            attempt_id=SHA_B,
            attempt=1,
            terminal=False,
            terminal_reason=None,
            backoff_ms=100,
            raw_record_sha256=SHA_C,
            response_model=None,
        )
        if with_raw
        else None
    )
    return AttemptCommitV1(lifecycle_start(plan[0]), raw, None)


def _bound_open_attempt(
    *,
    run_id: UUID = _CAPSULE_RUN_ID,
    call_sequence: int = 0,
) -> AttemptCommitV1:
    start = make_event(
        sequence=2,
        run_id=run_id,
        occurred_at=_SEALED_AT,
        kind="request_started",
        operation_id=_OPEN_OPERATION,
        execution_session_id=_OPEN_SESSION,
        payload={
            "call_sequence": call_sequence,
            "plan_item_id": SHA_A,
            "attempt_id": SHA_B,
            "attempt": 1,
            "retry_of_attempt": None,
            "request_config_sha256": SHA_A,
            "prompt_sha256": SHA_B,
            "case_definition_sha256": SHA_C,
            "instruction_sha256": SHA_D,
            "provider": "openai",
            "model": "gpt-5.6-sol",
        },
    )
    assert type(start) is RequestStartedEventV1
    return AttemptCommitV1(start, None, None)


@pytest.mark.parametrize(
    "mutation",
    [
        {"recovery_requirements": (RecoveryRequirementV1("generation_completed", 0),)},
        {"latest_event_recovered": 1},
        {"latest_event_recovered": True},
        {"next_unresolved_plan_ordinal": 1},
    ],
    ids=(
        "pending-recovery",
        "non-bool-recovered",
        "recovered-seal-request",
        "forged-cursor",
    ),
)
def test_derive_seal_v1_rejects_nonquiescent_or_forged_history(
    mutation: dict[str, object],
) -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("incomplete")
    history = _history(
        status="incomplete",
        missing=(SHA_A,),
        blocker="interrupted",
        seal_requested=request,
        raw_counts=(1, 0, 0, 1, 0, 0),
    )

    with pytest.raises(SealModelError):
        derive_seal_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            history=replace(history, **mutation),
            lifecycle=LifecycleProjectionV1("SEALING_INTERRUPTED", (SHA_A,), ("interrupted",)),
            seal_requested=request,
            files=_files(),
        )


@pytest.mark.parametrize("with_raw", [False, True], ids=("rawless", "with-raw"))
def test_derive_seal_v1_rejects_impossible_open_attempt_state(with_raw: bool) -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("incomplete")
    raw_counts = (1, 0, 0, 1, 0, 0) if with_raw else (0, 0, 0, 0, 0, 0)
    history = _history(
        status="incomplete",
        missing=(SHA_A,),
        blocker="interrupted",
        seal_requested=request,
        raw_counts=raw_counts,
    )
    forged_history = replace(
        history,
        next_call_sequence=1,
        request_history_present=True,
        execution_history_present=True,
        open_attempt=_open_attempt(with_raw=with_raw),
    )

    with pytest.raises(SealModelError):
        derive_seal_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            history=forged_history,
            lifecycle=LifecycleProjectionV1("SEALING_INTERRUPTED", (SHA_A,), ("interrupted",)),
            seal_requested=request,
            files=_files(),
        )


@pytest.mark.parametrize(
    "open_attempt",
    [
        _bound_open_attempt(run_id=_FOREIGN_RUN),
        _bound_open_attempt(call_sequence=1),
    ],
    ids=("foreign-run", "call-sequence"),
)
def test_derive_seal_v1_rejects_forged_open_start_binding(
    open_attempt: AttemptCommitV1,
) -> None:
    capsule, manifest, environment = _inputs()
    request = _seal_request("incomplete")
    history = _history(
        status="incomplete",
        missing=(SHA_A,),
        blocker="ambiguous_inflight",
        seal_requested=request,
        raw_counts=(0, 0, 0, 0, 0, 0),
    )
    forged_history = replace(
        history,
        next_call_sequence=1,
        request_history_present=True,
        open_attempt=open_attempt,
    )

    with pytest.raises(SealModelError) as caught:
        derive_seal_v1(
            capsule=capsule,
            manifest=manifest,
            environment=environment,
            history=forged_history,
            lifecycle=LifecycleProjectionV1(
                "SEALING_INTERRUPTED",
                (SHA_A,),
                ("ambiguous_inflight",),
            ),
            seal_requested=request,
            files=_files(),
        )

    assert caught.value.code == "seal_mismatch"
    assert str(caught.value) == "capsule seal rejected"


def test_seal_bytes_class_bound_revalidates_forged_seal() -> None:
    seal = SealV1.model_validate(seal_v1_payload())
    forged = SealV1.model_construct(**(seal.model_dump() | {"raw_attempt_count": True}))

    with pytest.raises(SealModelError) as caught:
        seal_bytes(forged)
    assert caught.value.code == "seal_mismatch"
    assert str(caught.value) == "capsule seal rejected"


class _RuntimeBomb:
    def __getattribute__(self, name: str) -> object:
        raise RuntimeError("HOSTILE_CANARY")


def test_seal_hash_helpers_map_hostile_nested_exceptions_content_free() -> None:
    seal = SealV1.model_validate(seal_v1_payload())
    forged = SealV1.model_construct(**(seal.model_dump() | {"files": (_RuntimeBomb(),)}))

    for operation in (seal_bytes, capsule_sha256):
        with pytest.raises(SealModelError) as caught:
            operation(forged)
        assert caught.value.code == "seal_mismatch"
        assert str(caught.value) == "capsule seal rejected"
        assert "HOSTILE_CANARY" not in str(caught.value)
