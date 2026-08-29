"""Read-only staged verification for prepared generation capsules.

The verifier deliberately owns only descriptors opened by the public entry point.  The
post-publication entry point borrows the descriptors and persistent exclusive lock already held by
``prepare``.  Every capsule descendant is inventoried and read relative to an open directory
descriptor, without following symlinks.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import platform
import re
import stat
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

from laconian_eval import __version__
from laconian_eval.arms import (
    Arm,
    arm_from_captured_bytes,
    arm_member_specs,
    validate_caveman_snapshot,
)
from laconian_eval.capsule.bounded_io import BoundedIOError, open_directory_no_follow
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes, stable_digest
from laconian_eval.capsule.events import (
    RequestStartedEventV1,
    SealRequestedEventV1,
)
from laconian_eval.capsule.filesystem import (
    FilesystemPosixOps,
    LockHandle,
    OwnedStagingError,
    UnsupportedFilesystemError,
    classify_filesystem,
    try_acquire_shared_lock,
)
from laconian_eval.capsule.history import (
    AttemptCommitV1,
    HistoryContextV1,
    HistoryError,
    LifecycleProjectionV1,
    RawCommitProjectionV1,
    RecoveryRequirementV1,
    ValidatedHistoryV1,
    derive_lifecycle_v1,
)
from laconian_eval.capsule.journal import JournalError, snapshot_journal_pair
from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_nesting_depth,
)
from laconian_eval.capsule.manifest_models import ResolvedDatasetV2, ResolvedManifestV2
from laconian_eval.capsule.planning import (
    PlanningError,
    recompute_dataset_content_sha256,
    validate_case_index,
    validate_plan,
)
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    CaseIndexRowV1,
    EnvironmentV1,
    InputFileRecordV1,
    InputIndexV1,
    PlanRowV1,
    PreparedEventV1,
    RunnerSourceIndexV1,
    VerifyResultV1,
)
from laconian_eval.cases import parse_response_case_bytes
from laconian_eval.models import ResponseCase


class VerificationMode(StrEnum):
    """Supported verification boundaries."""

    PREPARED = "prepared"


@dataclass(frozen=True, slots=True)
class _Failure(Exception):
    code: str
    path: str | None
    sequence: int | None = None


@dataclass(frozen=True, slots=True)
class _Identity:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True, slots=True)
class _Inventory:
    root_identity: _Identity
    directories: dict[str, _Identity]
    files: dict[str, _Identity]


def _strict_inventory(value: object) -> _Inventory:
    if type(value) is not _Inventory:
        raise _Failure("invalid_model", None)

    def strict_identity(identity: object) -> _Identity:
        if type(identity) is not _Identity:
            raise _Failure("invalid_model", None)
        fields = (
            identity.device,
            identity.inode,
            identity.mode,
            identity.size,
            identity.mtime_ns,
            identity.ctime_ns,
        )
        if any(type(item) is not int or item < 0 for item in fields):
            raise _Failure("invalid_model", None)
        return _Identity(*fields)

    def strict_entries(entries: object) -> dict[str, _Identity]:
        if type(entries) is not dict:
            raise _Failure("invalid_model", None)
        checked: dict[str, _Identity] = {}
        for path, identity in dict.items(entries):
            if type(path) is not str:
                raise _Failure("invalid_model", None)
            checked[path] = strict_identity(identity)
        return checked

    return _Inventory(
        strict_identity(value.root_identity),
        strict_entries(value.directories),
        strict_entries(value.files),
    )


@dataclass(frozen=True, slots=True)
class _CapturedInput:
    record: InputFileRecordV1
    data: bytes


@dataclass(frozen=True, slots=True)
class _CapturedCase:
    source_ordinal: int
    dataset_id: str
    input_file: _CapturedInput
    cases: tuple[object, ...]

    @property
    def data(self) -> bytes:
        return self.input_file.data

    @property
    def record(self) -> InputFileRecordV1:
        return self.input_file.record


@dataclass(frozen=True, slots=True)
class _CapturedProjection:
    source_manifest_commitment_sha256: str
    resolved_manifest: ResolvedManifestV2
    resolved_manifest_bytes: bytes
    manifest_sha256: str
    files: tuple[_CapturedInput, ...]
    case_files: tuple[_CapturedCase, ...]
    arms: tuple[Arm, ...]

    @property
    def records(self) -> tuple[InputFileRecordV1, ...]:
        return tuple(item.record for item in self.files)


_ModelT = TypeVar("_ModelT", bound=BaseModel)
_SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_REASONS = frozenset(
    {
        "success",
        "retry_exhausted",
        "provider_rejected",
        "authentication_stopped",
        "ambiguous_delivery",
    }
)
_RECOVERY_KINDS = (
    "request_finished",
    "authentication_stopped",
    "delivery_ambiguous",
    "generation_completed",
)
_LIFECYCLE_STATES = frozenset(
    {
        "PREPARED",
        "INTERRUPTED",
        "AMBIGUOUS_INFLIGHT",
        "AUTHENTICATION_STOPPED",
        "GENERATION_COMPLETE",
        "SEALING_INTERRUPTED",
        "SEALED_COMPLETE",
        "SEALED_BLOCKED",
    }
)
_OPERATIONAL_BLOCKERS = frozenset(
    {"never_started", "interrupted", "ambiguous_inflight", "authentication_stopped"}
)


def _strict_model_copy(model_type: type[_ModelT], value: object) -> _ModelT:
    if type(value) is not model_type:
        raise TypeError
    payload = model_type.model_dump(value, mode="python", round_trip=True, warnings=False)
    return model_type.model_validate(payload)


def _strict_sha256(value: object) -> str:
    if type(value) is not str or _SHA256_TEXT.fullmatch(value) is None:
        raise TypeError
    return value


def _strict_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise TypeError
    return value


def _strict_provider_text(value: object) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8", errors="strict")) > RESOURCE_LIMITS_V1.bounded_string_bytes
        or any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value)
    ):
        raise TypeError
    return value


def _strict_captured_projection(
    value: object,
    *,
    capsule: CapsuleV1,
    manifest: ResolvedManifestV2,
    input_index: InputIndexV1,
) -> tuple[_CapturedProjection, tuple[Arm, ...]]:
    if type(value) is not _CapturedProjection:
        raise TypeError
    if (
        type(value.resolved_manifest_bytes) is not bytes
        or type(value.files) is not tuple
        or type(value.case_files) is not tuple
        or type(value.arms) is not tuple
    ):
        raise TypeError
    source_commitment = _strict_sha256(value.source_manifest_commitment_sha256)
    manifest_sha256 = _strict_sha256(value.manifest_sha256)
    resolved_manifest = _strict_model_copy(ResolvedManifestV2, value.resolved_manifest)
    resolved_manifest_bytes = bytes(value.resolved_manifest_bytes)
    if (
        source_commitment != capsule.source_manifest_commitment_sha256
        or resolved_manifest != manifest
        or manifest_sha256 != capsule.manifest_sha256
        or sha256_bytes(resolved_manifest_bytes) != manifest_sha256
        or canonical_json(resolved_manifest.model_dump(mode="json", round_trip=True))
        != resolved_manifest_bytes
    ):
        raise TypeError

    files: list[_CapturedInput] = []
    for item in value.files:
        if type(item) is not _CapturedInput or type(item.data) is not bytes:
            raise TypeError
        record = _strict_model_copy(InputFileRecordV1, item.record)
        data = bytes(item.data)
        if record.byte_length != len(data) or record.sha256 != sha256_bytes(data):
            raise TypeError
        files.append(_CapturedInput(record, data))
    checked_files = tuple(files)
    if tuple(item.record for item in checked_files) != input_index.files:
        raise TypeError

    case_files: list[_CapturedCase] = []
    for captured_case in value.case_files:
        if (
            type(captured_case) is not _CapturedCase
            or type(captured_case.source_ordinal) is not int
            or captured_case.source_ordinal < 0
            or type(captured_case.dataset_id) is not str
            or not captured_case.dataset_id
            or type(captured_case.cases) is not tuple
        ):
            raise TypeError
        if (
            type(captured_case.input_file) is not _CapturedInput
            or type(captured_case.input_file.data) is not bytes
        ):
            raise TypeError
        input_record = _strict_model_copy(InputFileRecordV1, captured_case.input_file.record)
        input_data = bytes(captured_case.input_file.data)
        cases = tuple(_strict_model_copy(ResponseCase, case) for case in captured_case.cases)
        case_files.append(
            _CapturedCase(
                captured_case.source_ordinal,
                captured_case.dataset_id,
                _CapturedInput(input_record, input_data),
                cases,
            )
        )

    arms: list[Arm] = []
    for arm in value.arms:
        if (
            type(arm) is not Arm
            or type(arm.name) is not str
            or (arm.instruction is not None and type(arm.instruction) is not str)
        ):
            raise TypeError
        arms.append(Arm(arm.name, arm.instruction, _strict_sha256(arm.sha256)))
    supplied = _CapturedProjection(
        source_commitment,
        resolved_manifest,
        resolved_manifest_bytes,
        manifest_sha256,
        checked_files,
        tuple(case_files),
        tuple(arms),
    )
    artifacts = {item.record.capsule_path: item.data for item in checked_files}
    rebuilt, rebuilt_arms = _build_captured_projection(
        capsule,
        manifest,
        resolved_manifest_bytes,
        input_index,
        artifacts,
        frozenset(artifacts),
    )
    if supplied != rebuilt:
        raise TypeError
    return rebuilt, rebuilt_arms


def _strict_raw_projection(value: object) -> RawCommitProjectionV1:
    if type(value) is not RawCommitProjectionV1:
        raise TypeError
    call_sequence = _strict_nonnegative_int(value.call_sequence)
    plan_item_id = _strict_sha256(value.plan_item_id)
    attempt_id = _strict_sha256(value.attempt_id)
    attempt = _strict_nonnegative_int(value.attempt)
    if not 1 <= attempt <= 6 or type(value.terminal) is not bool:
        raise TypeError
    terminal_reason = value.terminal_reason
    if terminal_reason is not None and (
        type(terminal_reason) is not str or terminal_reason not in _TERMINAL_REASONS
    ):
        raise TypeError
    backoff_ms = value.backoff_ms
    if backoff_ms is not None:
        backoff_ms = _strict_nonnegative_int(backoff_ms)
    if value.terminal:
        if terminal_reason is None or backoff_ms is not None:
            raise TypeError
    elif terminal_reason is not None or backoff_ms != 100 * 2 ** (attempt - 1):
        raise TypeError
    raw_hash = _strict_sha256(value.raw_record_sha256)
    response_model = (
        None if value.response_model is None else _strict_provider_text(value.response_model)
    )
    if (terminal_reason == "success") != (response_model is not None):
        raise TypeError
    return RawCommitProjectionV1(
        call_sequence,
        plan_item_id,
        attempt_id,
        attempt,
        value.terminal,
        terminal_reason,
        backoff_ms,
        raw_hash,
        response_model,
    )


def _strict_open_attempt(value: object) -> AttemptCommitV1:
    if type(value) is not AttemptCommitV1 or value.finish is not None:
        raise TypeError
    start = _strict_model_copy(RequestStartedEventV1, value.start)
    raw = None if value.raw is None else _strict_raw_projection(value.raw)
    if raw is not None and (
        raw.call_sequence != start.payload.call_sequence
        or raw.plan_item_id != start.payload.plan_item_id
        or raw.attempt_id != start.payload.attempt_id
        or raw.attempt != start.payload.attempt
    ):
        raise TypeError
    return AttemptCommitV1(start, raw, None)


def _strict_recovery_requirement(value: object) -> RecoveryRequirementV1:
    if type(value) is not RecoveryRequirementV1 or type(value.kind) is not str:
        raise TypeError
    kind = value.kind
    if kind not in _RECOVERY_KINDS:
        raise TypeError
    call_sequence = _strict_nonnegative_int(value.call_sequence)

    def optional_sha(candidate: object) -> str | None:
        return None if candidate is None else _strict_sha256(candidate)

    plan_item_id = optional_sha(value.plan_item_id)
    attempt_id = optional_sha(value.attempt_id)
    origin_start = optional_sha(value.origin_request_started_event_id)
    raw_hash = optional_sha(value.raw_record_sha256)
    origin_finish = optional_sha(value.origin_request_finished_event_id)
    if kind == "request_finished":
        if None in (plan_item_id, attempt_id, origin_start, raw_hash) or origin_finish is not None:
            raise TypeError
    elif kind in {"authentication_stopped", "delivery_ambiguous"}:
        if (
            None in (plan_item_id, attempt_id, origin_start)
            or raw_hash is not None
            or origin_finish is not None
        ):
            raise TypeError
    elif any(item is not None for item in (plan_item_id, attempt_id, origin_start, raw_hash)):
        raise TypeError
    return RecoveryRequirementV1(
        kind,
        call_sequence,
        plan_item_id,
        attempt_id,
        origin_start,
        raw_hash,
        origin_finish,
    )


def _strict_string_tuple(value: object, *, sha256: bool) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise TypeError
    checked = tuple(
        _strict_sha256(item) if sha256 else _strict_provider_text(item) for item in value
    )
    if len(checked) != len(set(checked)):
        raise TypeError
    return checked


def _strict_history_copy(value: object, plan: tuple[PlanRowV1, ...]) -> ValidatedHistoryV1:
    if type(value) is not ValidatedHistoryV1 or type(value.recovery_requirements) is not tuple:
        raise TypeError
    resolved = _strict_string_tuple(value.resolved_plan_item_ids, sha256=True)
    missing = _strict_string_tuple(value.missing_plan_item_ids, sha256=True)
    returned = _strict_string_tuple(value.returned_models, sha256=False)
    plan_ids = tuple(row.plan_item_id for row in plan)
    if (
        resolved != plan_ids[: len(resolved)]
        or missing
        != tuple(sorted(plan_ids[len(resolved) :], key=lambda item: item.encode("utf-8")))
        or returned != tuple(sorted(returned, key=lambda item: item.encode("utf-8")))
        or len(returned) > 2
    ):
        raise TypeError
    next_ordinal = value.next_unresolved_plan_ordinal
    expected_ordinal = None if not missing else len(resolved)
    if next_ordinal != expected_ordinal or (
        next_ordinal is not None and type(next_ordinal) is not int
    ):
        raise TypeError
    next_call = _strict_nonnegative_int(value.next_call_sequence)
    open_attempt = None if value.open_attempt is None else _strict_open_attempt(value.open_attempt)
    requirements = tuple(
        _strict_recovery_requirement(requirement) for requirement in value.recovery_requirements
    )
    if len(requirements) > 3:
        raise TypeError
    order = tuple(_RECOVERY_KINDS.index(requirement.kind) for requirement in requirements)
    if order != tuple(sorted(order)) or len(order) != len(set(order)):
        raise TypeError
    bool_values = (
        value.request_history_present,
        value.execution_history_present,
        value.latest_no_call_blocked,
        value.has_ambiguous_delivery,
        value.has_authentication_stop,
    )
    if any(type(item) is not bool for item in bool_values):
        raise TypeError
    if (
        value.request_history_present != (next_call > 0)
        or (value.request_history_present and not value.execution_history_present)
        or (value.request_history_present and value.latest_no_call_blocked)
        or (value.has_ambiguous_delivery and value.has_authentication_stop)
        or (not missing and (value.has_ambiguous_delivery or value.has_authentication_stop))
        or len(resolved) > next_call
    ):
        raise TypeError
    if open_attempt is not None:
        if next_call == 0 or open_attempt.start.payload.call_sequence != next_call - 1:
            raise TypeError
        raw = open_attempt.raw
        target_id = open_attempt.start.payload.plan_item_id
        if raw is None:
            if not missing or target_id != plan[expected_ordinal].plan_item_id:  # type: ignore[index]
                raise TypeError
            if not value.has_ambiguous_delivery or requirements:
                raise TypeError
        else:
            if not requirements or requirements[0].kind != "request_finished":
                raise TypeError
            first = requirements[0]
            if (
                first.call_sequence != raw.call_sequence
                or first.plan_item_id != raw.plan_item_id
                or first.attempt_id != raw.attempt_id
                or first.origin_request_started_event_id != open_attempt.start.event_id
                or first.raw_record_sha256 != raw.raw_record_sha256
            ):
                raise TypeError
            if raw.terminal_reason in {"success", "retry_exhausted", "provider_rejected"}:
                if not resolved or target_id != resolved[-1]:
                    raise TypeError
            elif not missing or target_id != plan[expected_ordinal].plan_item_id:  # type: ignore[index]
                raise TypeError
            if (
                raw.terminal_reason == "authentication_stopped"
                and not value.has_authentication_stop
            ):
                raise TypeError
            if raw.terminal_reason == "ambiguous_delivery" and not value.has_ambiguous_delivery:
                raise TypeError
    seal = None
    if value.seal_requested is not None:
        seal = _strict_model_copy(SealRequestedEventV1, value.seal_requested)
        if requirements:
            raise TypeError
    return ValidatedHistoryV1(
        resolved,
        missing,
        returned,
        expected_ordinal,
        next_call,
        open_attempt,
        requirements,
        *bool_values,
        seal,
    )


def _history_commitment(history: ValidatedHistoryV1) -> str:
    open_attempt: dict[str, object] | None = None
    if history.open_attempt is not None:
        raw = history.open_attempt.raw
        open_attempt = {
            "start": history.open_attempt.start.model_dump(mode="json", round_trip=True),
            "raw": None
            if raw is None
            else {
                "call_sequence": raw.call_sequence,
                "plan_item_id": raw.plan_item_id,
                "attempt_id": raw.attempt_id,
                "attempt": raw.attempt,
                "terminal": raw.terminal,
                "terminal_reason": raw.terminal_reason,
                "backoff_ms": raw.backoff_ms,
                "raw_record_sha256": raw.raw_record_sha256,
                "response_model": raw.response_model,
            },
        }
    return stable_digest(
        "laconian-validated-history-context-v1",
        {
            "resolved_plan_item_ids": history.resolved_plan_item_ids,
            "missing_plan_item_ids": history.missing_plan_item_ids,
            "returned_models": history.returned_models,
            "next_unresolved_plan_ordinal": history.next_unresolved_plan_ordinal,
            "next_call_sequence": history.next_call_sequence,
            "open_attempt": open_attempt,
            "recovery_requirements": [
                {
                    "kind": item.kind,
                    "call_sequence": item.call_sequence,
                    "plan_item_id": item.plan_item_id,
                    "attempt_id": item.attempt_id,
                    "origin_request_started_event_id": item.origin_request_started_event_id,
                    "raw_record_sha256": item.raw_record_sha256,
                    "origin_request_finished_event_id": item.origin_request_finished_event_id,
                }
                for item in history.recovery_requirements
            ],
            "request_history_present": history.request_history_present,
            "execution_history_present": history.execution_history_present,
            "latest_no_call_blocked": history.latest_no_call_blocked,
            "has_ambiguous_delivery": history.has_ambiguous_delivery,
            "has_authentication_stop": history.has_authentication_stop,
            "seal_requested": None
            if history.seal_requested is None
            else history.seal_requested.model_dump(mode="json", round_trip=True),
        },
    )


def _strict_lifecycle_copy(value: object) -> LifecycleProjectionV1:
    if (
        type(value) is not LifecycleProjectionV1
        or type(value.state) is not str
        or value.state not in _LIFECYCLE_STATES
        or type(value.missing_plan_item_ids) is not tuple
        or type(value.operational_blocker_codes) is not tuple
    ):
        raise TypeError
    missing = tuple(_strict_sha256(item) for item in value.missing_plan_item_ids)
    blockers = tuple(value.operational_blocker_codes)
    if any(type(item) is not str or item not in _OPERATIONAL_BLOCKERS for item in blockers):
        raise TypeError
    return LifecycleProjectionV1(value.state, missing, blockers)


@dataclass(frozen=True, slots=True)
class _VerifiedCapsuleContext:
    capsule: CapsuleV1
    manifest: ResolvedManifestV2
    environment: EnvironmentV1
    input_index: InputIndexV1
    captured: _CapturedProjection
    case_index: tuple[CaseIndexRowV1, ...]
    plan: tuple[PlanRowV1, ...]
    history: ValidatedHistoryV1
    lifecycle: LifecycleProjectionV1
    _history_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        try:
            capsule = _strict_model_copy(CapsuleV1, self.capsule)
            manifest = _strict_model_copy(ResolvedManifestV2, self.manifest)
            environment = _strict_model_copy(EnvironmentV1, self.environment)
            input_index = _strict_model_copy(InputIndexV1, self.input_index)
            if type(self.case_index) is not tuple or type(self.plan) is not tuple:
                raise TypeError
            case_index = tuple(_strict_model_copy(CaseIndexRowV1, row) for row in self.case_index)
            plan = tuple(_strict_model_copy(PlanRowV1, row) for row in self.plan)
            captured, arms = _strict_captured_projection(
                self.captured,
                capsule=capsule,
                manifest=manifest,
                input_index=input_index,
            )
            validate_case_index(case_index, captured, manifest)  # type: ignore[arg-type]
            validate_plan(plan, capsule.run_id, manifest, case_index, arms)
            history = _strict_history_copy(self.history, plan)
            if _strict_sha256(self._history_sha256) != _history_commitment(history):
                raise TypeError
            lifecycle = _strict_lifecycle_copy(self.lifecycle)
            derived_lifecycle = derive_lifecycle_v1(history)
            if lifecycle != derived_lifecycle:
                raise TypeError
            object.__setattr__(self, "capsule", capsule)
            object.__setattr__(self, "manifest", manifest)
            object.__setattr__(self, "environment", environment)
            object.__setattr__(self, "input_index", input_index)
            object.__setattr__(self, "captured", captured)
            object.__setattr__(self, "case_index", case_index)
            object.__setattr__(self, "plan", plan)
            object.__setattr__(self, "history", history)
            object.__setattr__(self, "lifecycle", derived_lifecycle)
        except Exception:
            raise _Failure("invalid_model", None) from None


_FIXED_FILES = frozenset(
    {
        ".laconian.lock",
        "capsule.json",
        "case-index.jsonl",
        "environment.json",
        "events.jsonl",
        "inputs/index.json",
        "inputs/software/runner-source.json",
        "manifest.json",
        "plan.jsonl",
        "raw.jsonl",
    }
)
_FIXED_DIRECTORIES = frozenset(
    {
        "inputs",
        "inputs/arms",
        "inputs/cases",
        "inputs/software",
        "inputs/software/runner",
        "inputs/software/runner/laconian_eval",
    }
)
_STATIC_JSON_FILES = frozenset(
    {
        "capsule.json",
        "environment.json",
        "inputs/index.json",
        "inputs/software/runner-source.json",
        "manifest.json",
    }
)
_FIXED_ARM_FILES = frozenset(
    {
        "inputs/arms/baseline.txt",
        "inputs/arms/concise.txt",
        "inputs/arms/caveman/SKILL.md",
        "inputs/arms/caveman/SOURCE.md",
        "inputs/arms/caveman/LICENSE.txt",
        "inputs/arms/if/SKILL.md",
    }
)
_FIXED_ARM_DIRECTORIES = frozenset({"inputs/arms/caveman", "inputs/arms/if"})
_ORDINAL = r"(?:[0-9]{3}|[1-9][0-9]{3,})"
_CASE_PATH = re.compile(rf"inputs/cases/{_ORDINAL}\.yaml\Z")
_PROTOCOL_PATH = re.compile(rf"inputs/protocols/{_ORDINAL}-[0-9a-f]{{16}}\.bin\Z")
_READ_CHUNK = 64 * 1024
# Producer provenance counts every runner-subtree entry against ``dependency_files``; the source
# YAML collection bound independently caps case files and protocol bindings at ``case_records``.
# Fixed files, directories, arm members, and the optional replay pair consume fewer than 64 entries.
_TREE_ENTRY_CEILING = RESOURCE_LIMITS_V1.dependency_files + 2 * RESOURCE_LIMITS_V1.case_records + 64
# A semantically valid case-index row has only the displayed fixed fields, every string is bounded
# by ``bounded_string_bytes``, and both ordinals are below ``case_records``.  Six times the UTF-8
# bound covers worst-case JSON escaping; the fixed allowance covers keys, punctuation, and numbers.
# This derived framing ceiling prevents an invalid unterminated row from consuming the 8-GiB
# mutable-capsule allowance before its model can be rejected.
_CASE_INDEX_ROW_CEILING = (
    6 * RESOURCE_LIMITS_V1.bounded_string_bytes * len(CaseIndexRowV1.model_fields) + 4096
)
_CAVEMAN_PINS = {
    "inputs/arms/caveman/SKILL.md": (
        "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"
    ),
    "inputs/arms/caveman/SOURCE.md": (
        "8aa76311ea6273848242b1fcdd3542c47683fdeb7118395afb5aafb4709d081d"
    ),
    "inputs/arms/caveman/LICENSE.txt": (
        "f0abc56b6f49ab2e285bb6e6723f028abb7ebd4fe0e242bbdc2b4dded0ace8b9"
    ),
}


@dataclass(frozen=True, slots=True)
class _StaticJsonPolicy:
    byte_ceiling: int
    array_limits: dict[str, int]


@dataclass(slots=True)
class _JsonFrame:
    kind: str
    key: str | None = None
    count: int = 0
    expect_value: bool = True
    expect_key: bool = True
    pending_key: str | None = None


def _static_json_policy(path: str) -> _StaticJsonPolicy:
    """Return schema-derived encoded ceilings for a generated static JSON document."""

    bounded = RESOURCE_LIMITS_V1.bounded_string_bytes
    json_string = 6 * bounded + 2
    relative_path = 2 * bounded + 2
    ascii_string = bounded + 2
    cases = RESOURCE_LIMITS_V1.case_records
    dependency_files = RESOURCE_LIMITS_V1.dependency_files
    input_files = dependency_files + 2 * cases + 7
    if path == "capsule.json":
        ceiling = (2 * len(CapsuleV1.model_fields) + 16) * json_string
        arrays: dict[str, int] = {}
    elif path == "environment.json":
        ceiling = (
            256 * json_string
            + RESOURCE_LIMITS_V1.dependency_distributions * (3 * json_string + 256)
            + dependency_files * (2 * ascii_string + relative_path + 256)
        )
        arrays = {
            "dependencies": RESOURCE_LIMITS_V1.dependency_distributions,
            "import_roots": dependency_files,
        }
    elif path == "inputs/index.json":
        ceiling = 64 * json_string + input_files * (
            3 * json_string + relative_path + ascii_string + 512
        )
        arrays = {"files": input_files}
    elif path == "inputs/software/runner-source.json":
        ceiling = 32 * json_string + dependency_files * (relative_path + 256)
        arrays = {"files": dependency_files}
    elif path == "manifest.json":
        # Resolution can legitimately expand beyond the authored 1-MiB source.  Six escaped
        # source copies plus the bounded generated paths, digests, ordinals, and declarations are
        # a conservative schema maximum without reapplying the authored-source byte limit.
        ceiling = (
            6 * RESOURCE_LIMITS_V1.source_manifest_bytes
            + cases * (8 * json_string + 6 * relative_path + 4096)
            + 256 * json_string
        )
        arrays = {
            "case_files": cases,
            "arms": 4,
            "datasets": cases,
            "comparisons": 6,
            "protocol_bindings": cases,
            "case_file_ordinals": cases,
            "dataset_ids": cases,
            "comparison_ids": cases,
            "applies_at": 4,
        }
    else:  # pragma: no cover - private callers use the fixed table above
        raise AssertionError("unknown static JSON artifact")
    return _StaticJsonPolicy(min(ceiling, RESOURCE_LIMITS_V1.mutable_capsule_bytes), arrays)


class _StaticJsonScanner:
    """Bound JSON tokens and schema collections without materializing the document."""

    def __init__(self, path: str, policy: _StaticJsonPolicy) -> None:
        self.path = path
        self.policy = policy
        self.frames: list[_JsonFrame] = []
        self.in_string = False
        self.string_is_key = False
        self.string_value_key: str | None = None
        self.escaped = False
        self.string_bytes = bytearray()
        self.string_length = 0
        self.scalar_bytes = 0
        self.case_ordinal_count = 0
        self.input_role_counts = {
            "case": 0,
            "protocol": 0,
            "runner_source": 0,
            "replay": 0,
            "arm": 0,
        }

    def _begin_value(self) -> str | None:
        if not self.frames:
            return None
        parent = self.frames[-1]
        if parent.kind == "array":
            if parent.expect_value:
                parent.count += 1
                limit = self.policy.array_limits.get(parent.key or "", _TREE_ENTRY_CEILING)
                if parent.count > limit:
                    raise _Failure("resource_limit", self.path)
                if parent.key == "case_file_ordinals":
                    self.case_ordinal_count += 1
                    if self.case_ordinal_count > RESOURCE_LIMITS_V1.case_records:
                        raise _Failure("resource_limit", self.path)
                parent.expect_value = False
            return None
        key = parent.pending_key
        parent.pending_key = None
        return key

    def _open_container(self, kind: str) -> None:
        key = self._begin_value()
        if len(self.frames) + 1 > RESOURCE_LIMITS_V1.nesting_depth:
            raise _Failure("resource_limit", self.path)
        self.frames.append(_JsonFrame(kind=kind, key=key))

    def feed(self, chunk: bytes) -> None:
        string_limit = 6 * RESOURCE_LIMITS_V1.bounded_string_bytes
        scalar_limit = RESOURCE_LIMITS_V1.bounded_string_bytes
        for byte in chunk:
            if self.in_string:
                if self.escaped:
                    self.escaped = False
                elif byte == 0x5C:
                    self.escaped = True
                elif byte == 0x22:
                    self.in_string = False
                    try:
                        decoded = json.loads(b'"' + bytes(self.string_bytes) + b'"')
                        if type(decoded) is not str:
                            raise ValueError
                        if (
                            len(decoded.encode("utf-8", errors="strict"))
                            > RESOURCE_LIMITS_V1.bounded_string_bytes
                        ):
                            raise _Failure("resource_limit", self.path)
                    except _Failure:
                        raise
                    except (
                        UnicodeDecodeError,
                        UnicodeEncodeError,
                        json.JSONDecodeError,
                        ValueError,
                    ):
                        raise _Failure("noncanonical_json", self.path) from None
                    if self.frames:
                        if self.string_is_key:
                            self.frames[-1].pending_key = decoded
                        elif (
                            self.path == "inputs/index.json"
                            and decoded in self.input_role_counts
                            and self.string_value_key == "role"
                        ):
                            self.input_role_counts[decoded] += 1
                            role_limits = {
                                "case": RESOURCE_LIMITS_V1.case_records,
                                "protocol": RESOURCE_LIMITS_V1.case_records,
                                "runner_source": RESOURCE_LIMITS_V1.dependency_files,
                                "replay": 1,
                                "arm": 6,
                            }
                            if self.input_role_counts[decoded] > role_limits[decoded]:
                                raise _Failure("resource_limit", self.path)
                    self.string_bytes.clear()
                    self.string_value_key = None
                    continue
                self.string_bytes.append(byte)
                self.string_length += 1
                if self.string_length > string_limit:
                    raise _Failure("resource_limit", self.path)
                continue

            if self.scalar_bytes:
                if byte not in b",]}":
                    self.scalar_bytes += 1
                    if self.scalar_bytes > scalar_limit:
                        raise _Failure("resource_limit", self.path)
                    continue
                self.scalar_bytes = 0

            if byte in b" \t\r\n":
                raise _Failure("noncanonical_json", self.path)
            if byte == 0x22:
                self.string_is_key = bool(
                    self.frames and self.frames[-1].kind == "object" and self.frames[-1].expect_key
                )
                if self.string_is_key:
                    self.frames[-1].expect_key = False
                    self.string_value_key = None
                else:
                    self.string_value_key = self._begin_value()
                self.in_string = True
                self.escaped = False
                self.string_bytes.clear()
                self.string_length = 0
            elif byte == 0x7B:
                self._open_container("object")
            elif byte == 0x5B:
                self._open_container("array")
            elif byte in {0x7D, 0x5D}:
                if self.frames:
                    self.frames.pop()
            elif byte == 0x2C:
                if self.frames:
                    frame = self.frames[-1]
                    if frame.kind == "array":
                        frame.expect_value = True
                    else:
                        frame.expect_key = True
                        frame.pending_key = None
            elif byte == 0x3A:
                continue
            else:
                self._begin_value()
                self.scalar_bytes = 1

    def finish(self) -> None:
        if self.in_string and self.string_length > 6 * RESOURCE_LIMITS_V1.bounded_string_bytes:
            raise _Failure("resource_limit", self.path)


def _identity(metadata: os.stat_result) -> _Identity:
    return _Identity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=metadata.st_mode,
        size=metadata.st_size,
        mtime_ns=metadata.st_mtime_ns,
        ctime_ns=metadata.st_ctime_ns,
    )


def _result(
    status: str,
    *,
    code: str | None = None,
    path: str | None = None,
    sequence: int | None = None,
) -> VerifyResultV1:
    explanation = None
    if code is not None:
        explanation = {
            "code": code,
            "path": path,
            "sequence": sequence,
            "explanation": "capsule verification failed",
        }
    return VerifyResultV1.model_validate(
        {
            "schema_version": "1",
            "status": status,
            "run_id": None,
            "state": None,
            "capsule_sha256": None,
            "missing_plan_item_ids": [],
            "operational_blocker_codes": [],
            "warnings": [],
            "first_error": explanation,
        }
    )


def _invalid_result(
    code: str = "io_error",
    path: str | None = None,
    sequence: int | None = None,
) -> VerifyResultV1:
    return _result("invalid", code=code, path=path, sequence=sequence)


def _busy_result() -> VerifyResultV1:
    return _result("busy")


def _unsupported_result() -> VerifyResultV1:
    return _result("unsupported", code="unsupported_filesystem")


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int:
        raise _Failure("io_error", None)
    return value


def _directory_flags() -> int:
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    if type(close_on_exec) is not int:
        close_on_exec = 0
    return (
        os.O_RDONLY | _required_flag("O_DIRECTORY") | _required_flag("O_NOFOLLOW") | close_on_exec
    )


def _file_flags() -> int:
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    if type(close_on_exec) is not int:
        close_on_exec = 0
    return os.O_RDONLY | _required_flag("O_NOFOLLOW") | _required_flag("O_NONBLOCK") | close_on_exec


def _safe_name(value: object) -> str:
    if type(value) is not str or value in {"", ".", ".."} or "/" in value or "\\" in value:
        raise _Failure("unexpected_path", None)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise _Failure("unexpected_path", None) from None
    return value


def _directory_allowed(path: str) -> bool:
    if path in _FIXED_DIRECTORIES or path in _FIXED_ARM_DIRECTORIES:
        return True
    if path in {"inputs/provider", "inputs/protocols"}:
        return True
    prefix = "inputs/software/runner/laconian_eval/"
    if not path.startswith(prefix):
        return False
    return "__pycache__" not in path[len(prefix) :].split("/")


def _file_allowed(path: str) -> bool:
    if path in _FIXED_FILES or path in _FIXED_ARM_FILES:
        return True
    if _CASE_PATH.fullmatch(path) is not None or _PROTOCOL_PATH.fullmatch(path) is not None:
        return True
    if path == "inputs/provider/replay.yaml":
        return True
    prefix = "inputs/software/runner/laconian_eval/"
    if not path.startswith(prefix):
        return False
    member = path[len(prefix) :]
    return (
        bool(member)
        and "__pycache__" not in member.split("/")
        and (member == "py.typed" or member.endswith(".py"))
    )


def _same_leaf(left: _Identity, right: _Identity) -> bool:
    return (left.device, left.inode, left.mode) == (right.device, right.inode, right.mode)


def _close_owned(
    descriptor: int,
    *,
    path: str | None,
    primary: BaseException | None = None,
) -> BaseException | None:
    try:
        os.close(descriptor)
    except OSError:
        if primary is None:
            return _Failure("io_error", path)
    return primary


def _scan_inventory(root_fd: int) -> _Inventory:
    try:
        root_before = _identity(os.fstat(root_fd))
    except OSError:
        raise _Failure("io_error", None) from None
    if not stat.S_ISDIR(root_before.mode):
        raise _Failure("unsafe_path_type", None)
    directories: dict[str, _Identity] = {}
    files: dict[str, _Identity] = {}
    structural: tuple[bytes, _Failure] | None = None
    teardown: BaseException | None = None
    entry_count = 0

    def note_structure(failure: _Failure, *, sort_path: str | None = None) -> None:
        nonlocal structural
        selected_path = sort_path if sort_path is not None else failure.path
        key = selected_path.encode("utf-8") if selected_path is not None else b"\xff"
        if structural is None or key < structural[0]:
            structural = (key, failure)

    def walk(directory_fd: int, prefix: str) -> None:
        nonlocal entry_count, teardown
        normalized: list[tuple[bytes, str, Any]] = []
        try:
            with os.scandir(directory_fd) as iterator:
                for entry in iterator:
                    entry_count += 1
                    if entry_count > _TREE_ENTRY_CEILING:
                        raise _Failure("resource_limit", None)
                    raw_name = getattr(entry, "name", None)
                    if type(raw_name) is not str:
                        note_structure(_Failure("unexpected_path", None))
                        continue
                    try:
                        encoded_name = raw_name.encode("utf-8", errors="strict")
                    except UnicodeEncodeError:
                        note_structure(_Failure("unexpected_path", None))
                        continue
                    normalized.append((encoded_name, raw_name, entry))
        except _Failure:
            raise
        except OSError:
            raise _Failure("io_error", prefix or None) from None
        for _encoded, raw_name, entry in sorted(normalized, key=lambda item: item[0]):
            try:
                name = _safe_name(raw_name)
            except _Failure as failure:
                note_structure(failure, sort_path=raw_name)
                continue
            relative = f"{prefix}/{name}" if prefix else name
            if len(relative.encode("utf-8")) > RESOURCE_LIMITS_V1.bounded_string_bytes:
                note_structure(_Failure("resource_limit", None), sort_path=relative)
                continue
            try:
                current = _identity(entry.stat(follow_symlinks=False))
            except OSError:
                note_structure(_Failure("io_error", relative))
                continue
            if stat.S_ISLNK(current.mode):
                note_structure(_Failure("unsafe_path_type", relative))
                continue
            if stat.S_ISDIR(current.mode):
                if _file_allowed(relative) and not _directory_allowed(relative):
                    note_structure(_Failure("unsafe_path_type", relative))
                    continue
                if not _directory_allowed(relative):
                    note_structure(_Failure("unexpected_path", relative))
                    continue
                child_fd: int | None = None
                operation_error: BaseException | None = None
                try:
                    child_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
                    opened = _identity(os.fstat(child_fd))
                    if not stat.S_ISDIR(opened.mode) or not _same_leaf(current, opened):
                        raise _Failure("unstable_snapshot", relative)
                    directories[relative] = opened
                    walk(child_fd, relative)
                    after = _identity(os.fstat(child_fd))
                    path_after = _identity(
                        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    )
                    if opened != after or not _same_leaf(opened, path_after):
                        raise _Failure("unstable_snapshot", relative)
                except BaseException as error:
                    operation_error = error
                close_error: BaseException | None = None
                if child_fd is not None:
                    close_error = _close_owned(child_fd, path=relative)
                if operation_error is not None:
                    if isinstance(operation_error, OSError):
                        code = (
                            "unsafe_path_type"
                            if operation_error.errno in {errno.ELOOP, errno.ENOTDIR}
                            else "io_error"
                        )
                        raise _Failure(code, relative) from None
                    if isinstance(operation_error, _Failure):
                        raise operation_error
                    raise operation_error
                if teardown is None and close_error is not None:
                    teardown = close_error
            elif stat.S_ISREG(current.mode):
                if not _file_allowed(relative):
                    code = "unsafe_path_type" if _directory_allowed(relative) else "unexpected_path"
                    note_structure(_Failure(code, relative))
                    continue
                files[relative] = current
            else:
                note_structure(_Failure("unsafe_path_type", relative))

    walk(root_fd, "")
    for path in _FIXED_FILES - files.keys():
        note_structure(_Failure("missing_path", path))
    for path in _FIXED_DIRECTORIES - set(directories):
        note_structure(_Failure("missing_path", path))
    if structural is not None:
        raise structural[1]
    if teardown is not None:
        raise teardown
    try:
        root_after = _identity(os.fstat(root_fd))
    except OSError:
        raise _Failure("io_error", None) from None
    if root_before != root_after:
        raise _Failure("unstable_snapshot", None)
    return _Inventory(root_before, directories, files)


def _open_parent(
    root_fd: int,
    path: str,
    inventory: _Inventory,
    teardown_errors: list[_Failure],
) -> tuple[int, str]:
    components = path.split("/")
    current = os.dup(root_fd)
    current_path: str | None = None
    try:
        for position, component in enumerate(components[:-1], start=1):
            relative = "/".join(components[:position])
            next_fd = os.open(component, _directory_flags(), dir_fd=current)
            try:
                opened = _identity(os.fstat(next_fd))
                path_identity = _identity(os.stat(component, dir_fd=current, follow_symlinks=False))
                expected = inventory.directories.get(relative)
                if (
                    expected is None
                    or not stat.S_ISDIR(opened.mode)
                    or not _same_leaf(expected, opened)
                    or not _same_leaf(opened, path_identity)
                ):
                    raise _Failure("unstable_snapshot", relative)
            except BaseException as error:
                primary = _close_owned(next_fd, path=relative, primary=error)
                assert primary is not None
                raise primary from None
            previous = current
            current = next_fd
            close_error = _close_owned(previous, path=current_path)
            if isinstance(close_error, _Failure):
                teardown_errors.append(close_error)
            current_path = relative
        return current, components[-1]
    except BaseException as error:
        primary = _close_owned(current, path=current_path, primary=error)
        assert primary is not None
        raise primary from None


def _read_file(
    root_fd: int,
    path: str,
    expected: _Identity,
    inventory: _Inventory,
    teardown_errors: list[_Failure],
    *,
    limit: int,
    static_policy: _StaticJsonPolicy | None = None,
) -> bytes:
    parent_fd: int | None = None
    descriptor: int | None = None
    captured: bytes | None = None
    primary: BaseException | None = None
    try:
        parent_fd, name = _open_parent(root_fd, path, inventory, teardown_errors)
        path_before = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        descriptor = os.open(name, _file_flags(), dir_fd=parent_fd)
        before = _identity(os.fstat(descriptor))
        if not stat.S_ISREG(before.mode):
            raise _Failure("unsafe_path_type", path)
        if not _same_leaf(expected, before) or not _same_leaf(path_before, before):
            raise _Failure("unstable_snapshot", path)
        effective_limit = min(
            limit,
            static_policy.byte_ceiling if static_policy is not None else limit,
        )
        if before.size > effective_limit:
            raise _Failure("resource_limit", path)
        if static_policy is not None:
            scanner = _StaticJsonScanner(path, static_policy)
            scanned = 0
            while True:
                try:
                    chunk = os.read(descriptor, _READ_CHUNK)
                except InterruptedError:
                    continue
                if not chunk:
                    break
                scanned += len(chunk)
                if scanned > effective_limit:
                    raise _Failure("resource_limit", path)
                scanner.feed(chunk)
            scanner.finish()
            if scanned != before.size:
                raise _Failure("unstable_snapshot", path)
            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
            except OSError:
                raise _Failure("io_error", path) from None
        chunks: list[bytes] = []
        total = 0
        second_scanner = (
            _StaticJsonScanner(path, static_policy) if static_policy is not None else None
        )
        while total <= effective_limit:
            try:
                chunk = os.read(descriptor, min(_READ_CHUNK, effective_limit + 1 - total))
            except InterruptedError:
                continue
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > effective_limit:
                raise _Failure("resource_limit", path)
            if second_scanner is not None:
                second_scanner.feed(chunk)
        if second_scanner is not None:
            second_scanner.finish()
        after = _identity(os.fstat(descriptor))
        path_after = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        captured = b"".join(chunks)
        if before != after or len(captured) != before.size or not _same_leaf(after, path_after):
            raise _Failure("unstable_snapshot", path)
    except BaseException as error:
        primary = error
    if descriptor is not None:
        close_error = _close_owned(descriptor, path=path, primary=primary)
        if primary is None and isinstance(close_error, _Failure):
            teardown_errors.append(close_error)
    if parent_fd is not None:
        close_error = _close_owned(parent_fd, path=path, primary=primary)
        if primary is None and isinstance(close_error, _Failure):
            teardown_errors.append(close_error)
    if primary is not None:
        if isinstance(primary, _Failure):
            raise primary
        if isinstance(primary, OSError):
            code = (
                "unsafe_path_type" if primary.errno in {errno.ELOOP, errno.ENOTDIR} else "io_error"
            )
            raise _Failure(code, path) from None
        raise primary
    assert captured is not None
    return captured


def _read_jsonl_models_file(
    root_fd: int,
    path: str,
    expected: _Identity,
    inventory: _Inventory,
    teardown_errors: list[_Failure],
    model_type: type[BaseModel],
    *,
    count_limit: int,
    row_limit: int,
) -> tuple[tuple[Any, ...], str]:
    """Frame/hash JSONL before allocating rows, then parse it in a bounded second pass."""

    parent_fd: int | None = None
    descriptor: int | None = None
    primary: BaseException | None = None
    parsed: tuple[Any, ...] | None = None
    digest_hex: str | None = None
    try:
        parent_fd, name = _open_parent(root_fd, path, inventory, teardown_errors)
        path_before = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        descriptor = os.open(name, _file_flags(), dir_fd=parent_fd)
        before = _identity(os.fstat(descriptor))
        if not stat.S_ISREG(before.mode):
            raise _Failure("unsafe_path_type", path)
        if not _same_leaf(expected, before) or not _same_leaf(path_before, before):
            raise _Failure("unstable_snapshot", path)
        if before.size > RESOURCE_LIMITS_V1.mutable_capsule_bytes:
            raise _Failure("resource_limit", path)

        digest = hashlib.sha256()
        row_count = 0
        row_length = 0
        consumed = 0
        while True:
            try:
                chunk = os.read(descriptor, _READ_CHUNK)
            except InterruptedError:
                continue
            if not chunk:
                break
            consumed += len(chunk)
            digest.update(chunk)
            start = 0
            while start < len(chunk):
                newline = chunk.find(b"\n", start)
                end = len(chunk) if newline < 0 else newline
                row_length += end - start
                if row_length > row_limit:
                    raise _Failure("resource_limit", path)
                if newline < 0:
                    break
                if row_length == 0:
                    raise _Failure("noncanonical_json", path)
                row_count += 1
                if row_count > count_limit:
                    raise _Failure("resource_limit", path)
                row_length = 0
                start = newline + 1
        if consumed != before.size:
            raise _Failure("unstable_snapshot", path)
        if row_count == 0 or row_length != 0:
            raise _Failure("noncanonical_json", path)
        digest_hex = digest.hexdigest()

        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
        except OSError:
            raise _Failure("io_error", path) from None
        rows: list[Any] = []
        pending = bytearray()
        second_pass_bytes = 0
        second_pass_rows = 0
        second_digest = hashlib.sha256()
        parse_failure: _Failure | None = None
        while True:
            try:
                chunk = os.read(descriptor, _READ_CHUNK)
            except InterruptedError:
                continue
            if not chunk:
                break
            second_pass_bytes += len(chunk)
            if second_pass_bytes > before.size:
                raise _Failure("unstable_snapshot", path)
            second_digest.update(chunk)
            start = 0
            while start < len(chunk):
                newline = chunk.find(b"\n", start)
                end = len(chunk) if newline < 0 else newline
                segment = chunk[start:end]
                if len(pending) + len(segment) > row_limit:
                    raise _Failure("resource_limit", path)
                pending.extend(segment)
                if newline < 0:
                    break
                if not pending:
                    raise _Failure("noncanonical_json", path)
                second_pass_rows += 1
                if second_pass_rows > count_limit:
                    raise _Failure("resource_limit", path)
                if parse_failure is None:
                    try:
                        value = _decode_json(bytes(pending), path)
                        model = _model_from_value(model_type, value, path)
                        if canonical_json(model.model_dump(mode="json", round_trip=True)) != bytes(
                            pending
                        ):
                            raise _Failure("noncanonical_json", path)
                        rows.append(model)
                    except _Failure as failure:
                        parse_failure = failure
                pending.clear()
                start = newline + 1
        if second_pass_bytes != before.size:
            raise _Failure("unstable_snapshot", path)

        after = _identity(os.fstat(descriptor))
        path_after = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        if (
            before != after
            or not _same_leaf(after, path_after)
            or second_digest.hexdigest() != digest_hex
            or second_pass_rows != row_count
        ):
            raise _Failure("unstable_snapshot", path)
        if pending:
            raise _Failure("noncanonical_json", path)
        if parse_failure is not None:
            raise parse_failure
        if len(rows) != row_count:
            raise _Failure("unstable_snapshot", path)
        parsed = tuple(rows)
    except BaseException as error:
        primary = error
    if descriptor is not None:
        close_error = _close_owned(descriptor, path=path, primary=primary)
        if primary is None and isinstance(close_error, _Failure):
            teardown_errors.append(close_error)
    if parent_fd is not None:
        close_error = _close_owned(parent_fd, path=path, primary=primary)
        if primary is None and isinstance(close_error, _Failure):
            teardown_errors.append(close_error)
    if primary is not None:
        if isinstance(primary, _Failure):
            raise primary
        if isinstance(primary, OSError):
            code = (
                "unsafe_path_type" if primary.errno in {errno.ELOOP, errno.ENOTDIR} else "io_error"
            )
            raise _Failure(code, path) from None
        raise primary
    assert parsed is not None and digest_hex is not None
    return parsed, digest_hex


def _resource_checks(inventory: _Inventory) -> None:
    evidence = {path: item for path, item in inventory.files.items() if path != ".laconian.lock"}
    total = sum(item.size for item in evidence.values())
    if total > RESOURCE_LIMITS_V1.mutable_capsule_bytes:
        oversized = next(
            (
                path
                for path, item in sorted(evidence.items(), key=lambda pair: pair[0].encode("utf-8"))
                if item.size > RESOURCE_LIMITS_V1.mutable_capsule_bytes
            ),
            None,
        )
        raise _Failure("resource_limit", oversized)

    role_paths: dict[str, list[str]] = {
        "case": [],
        "arm": [],
        "replay": [],
        "protocol": [],
        "runner_source": [],
    }
    for path in evidence:
        if _CASE_PATH.fullmatch(path) is not None:
            role_paths["case"].append(path)
        elif path.startswith("inputs/arms/"):
            role_paths["arm"].append(path)
        elif path == "inputs/provider/replay.yaml":
            role_paths["replay"].append(path)
        elif _PROTOCOL_PATH.fullmatch(path) is not None:
            role_paths["protocol"].append(path)
        elif path.startswith("inputs/software/runner/laconian_eval/"):
            role_paths["runner_source"].append(path)

    per_file_limits = {
        "case": RESOURCE_LIMITS_V1.case_file_bytes,
        "arm": RESOURCE_LIMITS_V1.arm_member_bytes,
        "replay": RESOURCE_LIMITS_V1.replay_fixture_bytes,
        "protocol": RESOURCE_LIMITS_V1.protocol_file_bytes,
        "runner_source": RESOURCE_LIMITS_V1.runner_source_file_bytes,
    }
    aggregate_limits = {
        "case": RESOURCE_LIMITS_V1.all_case_files_bytes,
        "arm": RESOURCE_LIMITS_V1.all_arm_members_bytes,
        "protocol": RESOURCE_LIMITS_V1.all_protocol_files_bytes,
        "runner_source": RESOURCE_LIMITS_V1.all_runner_source_files_bytes,
    }
    for role, paths in role_paths.items():
        for path in sorted(paths, key=lambda item: item.encode("utf-8")):
            if evidence[path].size > per_file_limits[role]:
                raise _Failure("resource_limit", path)
        if (
            role in aggregate_limits
            and sum(evidence[path].size for path in paths) > aggregate_limits[role]
        ):
            raise _Failure("resource_limit", None)
    captured_total = sum(evidence[path].size for paths in role_paths.values() for path in paths)
    if captured_total > RESOURCE_LIMITS_V1.captured_input_total_bytes:
        raise _Failure("resource_limit", None)


def _load_artifacts(
    root_fd: int,
    inventory: _Inventory,
) -> tuple[dict[str, bytes], list[_Failure]]:
    loaded: dict[str, bytes] = {}
    teardown_errors: list[_Failure] = []
    for path in sorted(inventory.files, key=lambda item: item.encode("utf-8")):
        if path == ".laconian.lock":
            continue
        loaded[path] = _read_file(
            root_fd,
            path,
            inventory.files[path],
            inventory,
            teardown_errors,
            limit=RESOURCE_LIMITS_V1.mutable_capsule_bytes,
        )
    return loaded, teardown_errors


def _decode_json(data: bytes, path: str) -> object:
    try:
        text = data.decode("utf-8", errors="strict")
        value = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _Failure("noncanonical_json", path) from None
    try:
        check_nesting_depth(value, limit=RESOURCE_LIMITS_V1.nesting_depth)
    except ResourceLimitError:
        raise _Failure("resource_limit", path) from None
    try:
        if canonical_json(value) != data:
            raise _Failure("noncanonical_json", path)
    except ResourceLimitError:
        raise _Failure("resource_limit", path) from None
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _Failure("noncanonical_json", path) from None
    return value


def _schema_field(model_type: type[BaseModel]) -> tuple[str, str] | None:
    if model_type is CapsuleV1:
        return ("capsule_schema_version", "1")
    if model_type is ResolvedManifestV2:
        return ("schema_version", "2")
    if "schema_version" in model_type.model_fields:
        return ("schema_version", "1")
    return None


def _model_from_value(model_type: type[BaseModel], value: object, path: str) -> Any:
    if not isinstance(value, dict):
        raise _Failure("invalid_model", path)
    schema = _schema_field(model_type)
    if schema is not None and value.get(schema[0]) != schema[1]:
        raise _Failure("unsupported_schema", path)
    try:
        return model_type.model_validate(value)
    except ResourceLimitError:
        raise _Failure("resource_limit", path) from None
    except ValidationError:
        raise _Failure("invalid_model", path) from None
    except (TypeError, ValueError):
        raise _Failure("invalid_model", path) from None


def _static_value_limits(value: object, path: str) -> None:
    """Reapply exact generated-document collection caps before Pydantic construction."""

    if not isinstance(value, dict):
        return

    def limited(candidate: object, maximum: int) -> list[object] | None:
        if not isinstance(candidate, list):
            return None
        if len(candidate) > maximum:
            raise _Failure("resource_limit", path)
        return candidate

    cases = RESOURCE_LIMITS_V1.case_records
    if path == "environment.json":
        runtime = value.get("runtime")
        if isinstance(runtime, dict):
            limited(runtime.get("dependencies"), RESOURCE_LIMITS_V1.dependency_distributions)
            imports = runtime.get("import_environment")
            if isinstance(imports, dict):
                limited(imports.get("import_roots"), RESOURCE_LIMITS_V1.dependency_files)
    elif path == "inputs/index.json":
        maximum = RESOURCE_LIMITS_V1.dependency_files + 2 * cases + 7
        records = limited(value.get("files"), maximum)
        if records is not None:
            role_limits = {
                "case": cases,
                "protocol": cases,
                "runner_source": RESOURCE_LIMITS_V1.dependency_files,
                "replay": 1,
                "arm": 6,
            }
            counts = {role: 0 for role in role_limits}
            for record in records:
                if isinstance(record, dict) and record.get("role") in counts:
                    role = cast(str, record["role"])
                    counts[role] += 1
                    if counts[role] > role_limits[role]:
                        raise _Failure("resource_limit", path)
    elif path == "inputs/software/runner-source.json":
        limited(value.get("files"), RESOURCE_LIMITS_V1.dependency_files)
    elif path == "manifest.json":
        limited(value.get("case_files"), cases)
        limited(value.get("arms"), 4)
        capsule = value.get("capsule")
        if not isinstance(capsule, dict):
            return
        datasets = limited(capsule.get("datasets"), cases)
        limited(capsule.get("comparisons"), 6)
        protocols = limited(capsule.get("protocol_bindings"), cases)
        ordinal_total = 0
        for dataset in datasets or ():
            if isinstance(dataset, dict):
                ordinals = limited(dataset.get("case_file_ordinals"), cases)
                ordinal_total += len(ordinals or ())
                if ordinal_total > cases:
                    raise _Failure("resource_limit", path)
        for binding in protocols or ():
            if not isinstance(binding, dict):
                continue
            scope = binding.get("scope")
            if isinstance(scope, dict):
                limited(scope.get("dataset_ids"), cases)
                limited(scope.get("comparison_ids"), cases)
            limited(binding.get("applies_at"), 4)


def _json_model(data: bytes, path: str, model_type: type[BaseModel]) -> Any:
    value = _decode_json(data, path)
    _static_value_limits(value, path)
    model = _model_from_value(model_type, value, path)
    try:
        projected = canonical_json(model.model_dump(mode="json", round_trip=True))
    except ResourceLimitError:
        raise _Failure("resource_limit", path) from None
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _Failure("invalid_model", path) from None
    if projected != data:
        raise _Failure("noncanonical_json", path)
    return model


def _jsonl_values(
    data: bytes,
    path: str,
    *,
    count_limit: int,
    row_limit: int | None = None,
) -> list[object]:
    if not data or not data.endswith(b"\n") or b"\n\n" in data:
        raise _Failure("noncanonical_json", path)
    row_count = data.count(b"\n")
    if row_count > count_limit:
        raise _Failure("resource_limit", path)
    raw_rows = data[:-1].split(b"\n")
    values: list[object] = []
    for raw in raw_rows:
        if row_limit is not None and len(raw) > row_limit:
            raise _Failure("resource_limit", path)
        value = _decode_json(raw, path)
        values.append(value)
    return values


def _jsonl_models(
    data: bytes,
    path: str,
    model_type: type[BaseModel],
    *,
    count_limit: int,
    row_limit: int | None = None,
) -> tuple[Any, ...]:
    values = _jsonl_values(data, path, count_limit=count_limit, row_limit=row_limit)
    models: list[Any] = []
    raw_rows = data[:-1].split(b"\n")
    for raw, value in zip(raw_rows, values, strict=True):
        model = _model_from_value(model_type, value, path)
        if canonical_json(model.model_dump(mode="json", round_trip=True)) != raw:
            raise _Failure("noncanonical_json", path)
        models.append(model)
    return tuple(models)


def _parents(path: str) -> set[str]:
    components = path.split("/")
    return {"/".join(components[:end]) for end in range(1, len(components))}


def _exact_tree(
    inventory: _Inventory,
    index: InputIndexV1,
    manifest: ResolvedManifestV2 | None = None,
) -> None:
    expected_files = set(_FIXED_FILES)
    expected_files.update(record.capsule_path for record in index.files)
    if manifest is not None:
        expected_files.update(manifest.case_files)
        expected_files.update(_declared_arm_paths(manifest))
        if manifest.provider.replay_file is not None:
            expected_files.add(manifest.provider.replay_file)
        expected_files.update(binding.path for binding in manifest.capsule.protocol_bindings)
    expected_directories = set(_FIXED_DIRECTORIES)
    for path in expected_files:
        expected_directories.update(_parents(path))
    actual_files = set(inventory.files)
    actual_directories = set(inventory.directories)
    candidates: list[tuple[bytes, int, _Failure]] = []
    wrong_type = (expected_files & actual_directories) | (expected_directories & actual_files)
    candidates.extend(
        (path.encode("utf-8"), 0, _Failure("unsafe_path_type", path)) for path in wrong_type
    )
    unexpected = (actual_files - expected_files) | (actual_directories - expected_directories)
    candidates.extend(
        (path.encode("utf-8"), 1, _Failure("unexpected_path", path)) for path in unexpected
    )
    missing = (expected_files - actual_files) | (expected_directories - actual_directories)
    candidates.extend((path.encode("utf-8"), 2, _Failure("missing_path", path)) for path in missing)
    if candidates:
        raise min(candidates, key=lambda item: (item[0], item[1]))[2]


def _declared_arm_paths(manifest: ResolvedManifestV2) -> set[str]:
    paths: set[str] = set()
    for arm_name in manifest.arms:
        for member in arm_member_specs(arm_name):
            if arm_name in {"baseline", "concise"}:
                paths.add(f"inputs/arms/{member.member}")
            else:
                paths.add(f"inputs/arms/{arm_name}/{member.member}")
    return paths


def _check_manifest_input_coverage(
    manifest: ResolvedManifestV2,
    index: InputIndexV1,
) -> None:
    actual: dict[str, set[str]] = {
        role: {record.capsule_path for record in index.files if record.role == role}
        for role in ("case", "arm", "replay", "protocol")
    }
    declared: dict[str, set[str]] = {
        "case": set(manifest.case_files),
        "arm": _declared_arm_paths(manifest),
        "replay": {manifest.provider.replay_file}
        if manifest.provider.replay_file is not None
        else set(),
        "protocol": {binding.path for binding in manifest.capsule.protocol_bindings},
    }
    for role in ("case", "arm", "replay", "protocol"):
        missing = sorted(declared[role] - actual[role], key=lambda item: item.encode("utf-8"))
        if missing:
            raise _Failure("missing_path", missing[0])
        if actual[role] != declared[role]:
            raise _Failure("identity_mismatch", "inputs/index.json")

    arm_records = tuple(record for record in index.files if record.role == "arm")
    for ordinal, arm_name in enumerate(manifest.arms):
        prefix = f"arm[{arm_name}]/"
        if any(
            record.logical_locator.startswith(prefix) and record.role_ordinal != ordinal
            for record in arm_records
        ):
            raise _Failure("identity_mismatch", "inputs/index.json")

    protocol_by_path = {
        record.capsule_path: record for record in index.files if record.role == "protocol"
    }
    for ordinal, binding in enumerate(manifest.capsule.protocol_bindings):
        record = protocol_by_path.get(binding.path)
        if record is None:
            raise _Failure("missing_path", binding.path)
        if (
            record.role_ordinal != ordinal
            or record.binding_id != binding.binding_id
            or record.logical_locator != f"capsule.protocol_bindings[{ordinal}].path"
            or record.byte_length != binding.byte_length
            or record.sha256 != binding.sha256
        ):
            raise _Failure("identity_mismatch", "manifest.json")


def _check_input_bytes(index: InputIndexV1, artifacts: dict[str, bytes]) -> None:
    for record in index.files:
        data = artifacts.get(record.capsule_path)
        if data is None:
            raise _Failure("missing_path", record.capsule_path)
        if record.byte_length != len(data) or record.sha256 != sha256_bytes(data):
            raise _Failure("hash_mismatch", record.capsule_path)


def _runner_file_payload(record: BaseModel) -> dict[str, object]:
    return cast(dict[str, object], record.model_dump(mode="json"))


def _check_runner_index(
    runner_index: RunnerSourceIndexV1,
    input_index: InputIndexV1,
) -> None:
    input_records = {
        record.capsule_path: record
        for record in input_index.files
        if record.role == "runner_source"
    }
    expected_paths: set[str] = set()
    for ordinal, member in enumerate(runner_index.files):
        path = f"inputs/software/runner/laconian_eval/{member.path}"
        expected_paths.add(path)
        indexed = input_records.get(path)
        if indexed is None:
            raise _Failure("missing_path", path)
        if (
            indexed.role_ordinal != ordinal
            or indexed.logical_locator != f"package[laconian_eval]/{member.path}"
            or indexed.byte_length != member.byte_length
            or indexed.sha256 != member.sha256
            or indexed.dataset_id is not None
            or indexed.binding_id is not None
        ):
            raise _Failure("hash_mismatch", path)
    if set(input_records) != expected_paths:
        raise _Failure("identity_mismatch", "inputs/software/runner-source.json")
    expected_root = stable_digest(
        "laconian-runner-source-v1",
        {
            "package_name": runner_index.package_name,
            "files": [_runner_file_payload(record) for record in runner_index.files],
        },
    )
    if runner_index.runner_source_sha256 != expected_root:
        raise _Failure("identity_mismatch", "inputs/software/runner-source.json")


def _check_capsule_projection(capsule: CapsuleV1, manifest: ResolvedManifestV2) -> None:
    if (
        capsule.runner_version != manifest.runner_version
        or capsule.run_purpose != manifest.capsule.run_purpose
        or capsule.claim_intent != manifest.capsule.claim_intent
        or capsule.schedule_algorithm_version != manifest.schedule_algorithm_version
        or capsule.arm_order_seed != manifest.arm_order_seed
    ):
        raise _Failure("identity_mismatch", "capsule.json")


def _check_environment(
    environment: EnvironmentV1,
    capsule: CapsuleV1,
    manifest: ResolvedManifestV2,
    runner_index: RunnerSourceIndexV1,
) -> None:
    if (
        environment.package_version != capsule.runner_version
        or environment.runner_source_sha256 != capsule.runner_source_sha256
        or environment.provider.kind != manifest.provider.kind
        or environment.provider.requested_model != manifest.provider.model
    ):
        raise _Failure("identity_mismatch", "environment.json")
    runner_by_path = {record.path: record for record in runner_index.files}
    adapter_paths = ("providers/__init__.py", f"providers/{environment.provider.kind}.py")
    try:
        adapter_files = [_runner_file_payload(runner_by_path[path]) for path in adapter_paths]
        guard = runner_by_path["capsule/import_policy.py"].sha256
    except KeyError:
        raise _Failure("identity_mismatch", "environment.json") from None
    adapter_root = stable_digest(
        "laconian-adapter-source-v1",
        {"provider_kind": environment.provider.kind, "files": adapter_files},
    )
    imports = environment.runtime.import_environment
    if (
        environment.provider.adapter_source_sha256 != adapter_root
        or imports.guard_source_sha256 != guard
        or imports.audit_hook_source_sha256 != guard
    ):
        raise _Failure("identity_mismatch", "environment.json")
    runtime_root = stable_digest(
        "laconian-runtime-v1",
        {
            "package_version": environment.package_version,
            "runner_source_sha256": environment.runner_source_sha256,
            "dependencies": [
                dependency.model_dump(mode="json")
                for dependency in environment.runtime.dependencies
            ],
            "import_environment": imports.model_dump(mode="json"),
            "adapter_source_sha256": environment.provider.adapter_source_sha256,
        },
    )
    if environment.runtime.runtime_fingerprint_sha256 != runtime_root:
        raise _Failure("identity_mismatch", "environment.json")


def _build_captured_projection(
    capsule: CapsuleV1,
    manifest: ResolvedManifestV2,
    manifest_bytes: bytes,
    index: InputIndexV1,
    artifacts: dict[str, bytes],
    trusted_paths: frozenset[str],
) -> tuple[_CapturedProjection, tuple[Arm, ...]]:
    captured_files = tuple(
        _CapturedInput(record=record, data=artifacts[record.capsule_path])
        for record in index.files
        if record.capsule_path in trusted_paths
    )
    by_path = {item.record.capsule_path: item for item in captured_files}
    ownership: dict[int, ResolvedDatasetV2] = {}
    projection_failure: _Failure | None = None

    def note_projection_failure(failure: _Failure) -> None:
        nonlocal projection_failure
        key = (failure.path is None, (failure.path or "").encode("utf-8"))
        if projection_failure is None or key < (
            projection_failure.path is None,
            (projection_failure.path or "").encode("utf-8"),
        ):
            projection_failure = failure

    for dataset in manifest.capsule.datasets:
        records = tuple(
            record
            for record in index.files
            if record.role == "case" and record.role_ordinal in dataset.case_file_ordinals
        )
        try:
            recomputed = recompute_dataset_content_sha256(dataset, records)
        except (PlanningError, ResourceLimitError):
            note_projection_failure(_Failure("identity_mismatch", "manifest.json"))
        else:
            if recomputed != dataset.dataset_content_sha256:
                note_projection_failure(_Failure("identity_mismatch", "manifest.json"))
        for ordinal in dataset.case_file_ordinals:
            ownership[ordinal] = dataset

    arm_by_name: dict[str, Arm] = {}
    arm_failure: _Failure | None = None

    def note_arm_failure(failure: _Failure) -> None:
        nonlocal arm_failure
        if arm_failure is None or (failure.path or "").encode("utf-8") < (
            arm_failure.path or ""
        ).encode("utf-8"):
            arm_failure = failure

    instruction_paths: list[tuple[str, str]] = []
    for arm_name in manifest.arms:
        if arm_name in {"baseline", "concise"}:
            instruction_path = f"inputs/arms/{arm_name}.txt"
        else:
            instruction_path = f"inputs/arms/{arm_name}/SKILL.md"
        instruction_paths.append((instruction_path, arm_name))
    for instruction_path, selected_name in sorted(
        instruction_paths, key=lambda item: item[0].encode("utf-8")
    ):
        if instruction_path not in trusted_paths:
            continue
        try:
            arm_by_name[selected_name] = arm_from_captured_bytes(
                selected_name, artifacts[instruction_path]
            )
        except KeyError:
            note_arm_failure(_Failure("missing_path", instruction_path))
        except (TypeError, ValueError):
            note_arm_failure(_Failure("identity_mismatch", instruction_path))
    caveman_members = frozenset(_CAVEMAN_PINS)
    if "caveman" in manifest.arms:
        pin_mismatch = False
        for relative in sorted(_CAVEMAN_PINS, key=lambda item: item.encode("utf-8")):
            if relative not in trusted_paths:
                continue
            if sha256_bytes(artifacts[relative]) != _CAVEMAN_PINS[relative]:
                pin_mismatch = True
                note_arm_failure(_Failure("identity_mismatch", relative))
        if caveman_members <= trusted_paths:
            try:
                validate_caveman_snapshot(
                    skill=artifacts["inputs/arms/caveman/SKILL.md"],
                    source=artifacts["inputs/arms/caveman/SOURCE.md"],
                    license_text=artifacts["inputs/arms/caveman/LICENSE.txt"],
                )
            except (KeyError, TypeError, ValueError):
                if not pin_mismatch:
                    note_arm_failure(
                        _Failure("identity_mismatch", "inputs/arms/caveman/LICENSE.txt")
                    )
    if arm_failure is not None:
        note_projection_failure(arm_failure)
    arms = [arm_by_name[arm_name] for arm_name in manifest.arms if arm_name in arm_by_name]

    case_files: list[_CapturedCase] = []
    remaining = RESOURCE_LIMITS_V1.case_records
    for ordinal, path in enumerate(manifest.case_files):
        if path not in trusted_paths:
            break
        item = by_path.get(path)
        owned_dataset = ownership.get(ordinal)
        if item is None or owned_dataset is None:
            note_projection_failure(_Failure("missing_path", path))
            break
        try:
            cases = parse_response_case_bytes(
                item.data,
                source=item.record.logical_locator,
                remaining_case_records=remaining,
            )
        except ResourceLimitError:
            note_projection_failure(_Failure("resource_limit", path))
            break
        except (TypeError, ValueError):
            note_projection_failure(_Failure("invalid_model", path))
            break
        remaining -= len(cases)
        case_files.append(
            _CapturedCase(
                source_ordinal=ordinal,
                dataset_id=owned_dataset.dataset_id,
                input_file=item,
                cases=tuple(cases),
            )
        )

    if projection_failure is not None:
        raise projection_failure

    projection = _CapturedProjection(
        source_manifest_commitment_sha256=capsule.source_manifest_commitment_sha256,
        resolved_manifest=manifest,
        resolved_manifest_bytes=manifest_bytes,
        manifest_sha256=sha256_bytes(manifest_bytes),
        files=captured_files,
        case_files=tuple(case_files),
        arms=tuple(arms),
    )
    return projection, tuple(arms)


def _check_prepared_event_row(data: bytes, capsule: CapsuleV1) -> None:
    first_value = _decode_json(data, "events.jsonl")
    if not isinstance(first_value, dict):
        raise _Failure("invalid_model", "events.jsonl")
    if set(first_value) != set(PreparedEventV1.model_fields):
        raise _Failure("invalid_model", "events.jsonl")
    if first_value.get("schema_version") != "1":
        raise _Failure("unsupported_schema", "events.jsonl")
    try:
        event = PreparedEventV1.model_validate(first_value)
    except ValidationError:
        raise _Failure("history_mismatch", "events.jsonl", 0) from None
    if canonical_json(event.model_dump(mode="json", round_trip=True)) != data:
        raise _Failure("noncanonical_json", "events.jsonl")
    identity = event.model_dump(mode="json")
    identity.pop("event_id")
    expected_payload = {
        "manifest_sha256": capsule.manifest_sha256,
        "input_index_sha256": capsule.input_index_sha256,
        "case_index_sha256": capsule.case_index_sha256,
        "plan_sha256": capsule.plan_sha256,
        "environment_sha256": capsule.environment_sha256,
        "runner_source_sha256": capsule.runner_source_sha256,
    }
    if (
        event.event_id != stable_digest("laconian-event-v1", identity)
        or event.run_id != capsule.run_id
        or event.occurred_at != capsule.created_at
        or event.operation_id == capsule.run_id
        or event.payload.model_dump(mode="json") != expected_payload
    ):
        raise _Failure("history_mismatch", "events.jsonl", 0)


def _verify_prepared_event_file(
    root_fd: int,
    expected: _Identity,
    inventory: _Inventory,
    teardown_errors: list[_Failure],
    capsule: CapsuleV1,
) -> None:
    """Validate the sole prepared row without buffering an attacker-sized ledger."""

    path = "events.jsonl"
    parent_fd: int | None = None
    descriptor: int | None = None
    primary: BaseException | None = None
    try:
        parent_fd, name = _open_parent(root_fd, path, inventory, teardown_errors)
        path_before = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        descriptor = os.open(name, _file_flags(), dir_fd=parent_fd)
        before = _identity(os.fstat(descriptor))
        if not stat.S_ISREG(before.mode):
            raise _Failure("unsafe_path_type", path)
        if not _same_leaf(expected, before) or not _same_leaf(path_before, before):
            raise _Failure("unstable_snapshot", path)

        pending = bytearray()
        first_complete = False
        consumed = 0
        while True:
            try:
                chunk = os.read(descriptor, _READ_CHUNK)
            except InterruptedError:
                continue
            if not chunk:
                break
            consumed += len(chunk)
            start = 0
            while start < len(chunk):
                newline = chunk.find(b"\n", start)
                end = len(chunk) if newline < 0 else newline
                pending.extend(chunk[start:end])
                if len(pending) > RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes:
                    raise _Failure("resource_limit", path)
                if newline < 0:
                    break
                if not pending:
                    raise _Failure("noncanonical_json", path)
                if not first_complete:
                    _check_prepared_event_row(bytes(pending), capsule)
                    first_complete = True
                else:
                    raise _Failure("history_mismatch", path, 1)
                pending.clear()
                start = newline + 1
        if consumed != before.size:
            raise _Failure("unstable_snapshot", path)
        if pending or not first_complete:
            raise _Failure("noncanonical_json", path)

        after = _identity(os.fstat(descriptor))
        path_after = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        if before != after or not _same_leaf(after, path_after):
            raise _Failure("unstable_snapshot", path)
    except BaseException as error:
        primary = error
    if descriptor is not None:
        close_error = _close_owned(descriptor, path=path, primary=primary)
        if primary is None and isinstance(close_error, _Failure):
            teardown_errors.append(close_error)
    if parent_fd is not None:
        close_error = _close_owned(parent_fd, path=path, primary=primary)
        if primary is None and isinstance(close_error, _Failure):
            teardown_errors.append(close_error)
    if primary is not None:
        if isinstance(primary, _Failure):
            raise primary
        if isinstance(primary, OSError):
            code = (
                "unsafe_path_type" if primary.errno in {errno.ELOOP, errno.ENOTDIR} else "io_error"
            )
            raise _Failure(code, path) from None
        raise primary


def _valid_result(
    context: _VerifiedCapsuleContext,
    inventory: _Inventory,
) -> VerifyResultV1:
    capsule = context.capsule
    environment = context.environment
    lifecycle = context.lifecycle
    warnings: list[str] = []
    if (
        stat.S_IMODE(inventory.root_identity.mode) & ~0o700
        or any(stat.S_IMODE(metadata.mode) & ~0o600 for metadata in inventory.files.values())
        or any(stat.S_IMODE(metadata.mode) & ~0o700 for metadata in inventory.directories.values())
    ):
        warnings.append("broader_permissions")
    if environment.runtime.os_family != platform.system():
        warnings.append("permission_representation_differs")
    if capsule.runner_version != __version__:
        warnings.append("producer_runtime_differs")
    return VerifyResultV1.model_validate(
        {
            "schema_version": "1",
            "status": "valid",
            "run_id": capsule.run_id,
            "state": lifecycle.state,
            "capsule_sha256": None,
            "missing_plan_item_ids": lifecycle.missing_plan_item_ids,
            "operational_blocker_codes": lifecycle.operational_blocker_codes,
            "warnings": warnings,
            "first_error": None,
        }
    )


def _verify_capsule_context_descriptors(
    root_fd: int, inventory: _Inventory
) -> _VerifiedCapsuleContext:
    """Validate one already-owned descriptor snapshot without acquiring any lock."""

    inventory = _strict_inventory(inventory)
    teardown_errors: list[_Failure] = []
    artifacts: dict[str, bytes] = {}

    def load(path: str) -> bytes:
        cached = artifacts.get(path)
        if cached is not None:
            return cached
        data = _read_file(
            root_fd,
            path,
            inventory.files[path],
            inventory,
            teardown_errors,
            limit=RESOURCE_LIMITS_V1.mutable_capsule_bytes,
            static_policy=_static_json_policy(path) if path in _STATIC_JSON_FILES else None,
        )
        artifacts[path] = data
        return data

    # The capsule marker is the first schema/run-identity trust root.  Nothing dynamic can be
    # interpreted safely if it is absent or malformed.
    capsule_bytes = load("capsule.json")
    capsule = _json_model(capsule_bytes, "capsule.json", CapsuleV1)

    static_failure: _Failure | None = None

    def failure_key(failure: _Failure) -> tuple[int, bytes]:
        if failure.path is None:
            return (1, b"")
        return (0, failure.path.encode("utf-8"))

    def note_static(failure: _Failure) -> None:
        nonlocal static_failure
        if static_failure is None or failure_key(failure) < failure_key(static_failure):
            static_failure = failure

    environment: EnvironmentV1 | None = None
    input_index: InputIndexV1 | None = None
    runner_index: RunnerSourceIndexV1 | None = None
    manifest: ResolvedManifestV2 | None = None

    static_models: tuple[tuple[str, type[BaseModel], str | None], ...] = (
        ("environment.json", EnvironmentV1, capsule.environment_sha256),
        ("inputs/index.json", InputIndexV1, capsule.input_index_sha256),
        ("inputs/software/runner-source.json", RunnerSourceIndexV1, None),
        ("manifest.json", ResolvedManifestV2, capsule.manifest_sha256),
    )
    parsed_models: dict[str, BaseModel] = {}
    for path, model_type, expected_digest in static_models:
        try:
            data = load(path)
            parsed = _json_model(data, path, model_type)
            if expected_digest is not None and sha256_bytes(data) != expected_digest:
                raise _Failure("hash_mismatch", path)
            parsed_models[path] = parsed
        except _Failure as failure:
            note_static(failure)

    parsed_environment = parsed_models.get("environment.json")
    if isinstance(parsed_environment, EnvironmentV1):
        environment = parsed_environment
    parsed_input_index = parsed_models.get("inputs/index.json")
    if isinstance(parsed_input_index, InputIndexV1):
        input_index = parsed_input_index
    parsed_runner_index = parsed_models.get("inputs/software/runner-source.json")
    if isinstance(parsed_runner_index, RunnerSourceIndexV1):
        runner_index = parsed_runner_index
    parsed_manifest = parsed_models.get("manifest.json")
    if isinstance(parsed_manifest, ResolvedManifestV2):
        manifest = parsed_manifest

    if input_index is not None:
        # Exact structure is stage 1 even though its dynamic allowlist is supplied by the safely
        # parsed index.  It therefore overrides every accumulated static-input failure.
        _exact_tree(inventory, input_index, manifest)
    if manifest is not None and input_index is not None:
        try:
            _check_manifest_input_coverage(manifest, input_index)
        except _Failure as failure:
            note_static(failure)

    resource_failure = False
    try:
        _resource_checks(inventory)
    except _Failure as failure:
        resource_failure = True
        note_static(failure)

    if (
        manifest is not None
        and input_index is not None
        and input_index.manifest_sha256 != sha256_bytes(artifacts["manifest.json"])
    ):
        note_static(_Failure("identity_mismatch", "inputs/index.json"))
    if runner_index is not None and input_index is not None:
        try:
            _check_runner_index(runner_index, input_index)
        except _Failure as failure:
            note_static(failure)
    if (
        runner_index is not None
        and capsule.runner_source_sha256 != runner_index.runner_source_sha256
    ):
        note_static(_Failure("identity_mismatch", "capsule.json"))
    if manifest is not None:
        try:
            _check_capsule_projection(capsule, manifest)
        except _Failure as failure:
            note_static(failure)
    if environment is not None and manifest is not None and runner_index is not None:
        try:
            _check_environment(environment, capsule, manifest, runner_index)
        except _Failure as failure:
            note_static(failure)

    # Metadata-only resource failures must stop before any sparse captured member is opened.
    if resource_failure:
        assert static_failure is not None
        raise static_failure
    if input_index is None:
        assert static_failure is not None
        raise static_failure

    # An earlier static file cannot be displaced by any captured-input path (all begin `inputs/`).
    if static_failure is not None and failure_key(static_failure) < (0, b"inputs/"):
        raise static_failure

    trusted_input_paths: set[str] = set()
    for record in input_index.files:
        path = record.capsule_path
        try:
            data = load(path)
            if record.byte_length != len(data) or record.sha256 != sha256_bytes(data):
                raise _Failure("hash_mismatch", path)
            trusted_input_paths.add(path)
        except _Failure as failure:
            note_static(failure)

    # Parsing captured cases and arms is still static-input verification; generated case-index
    # bytes are not touched until every independently checkable stage-2 failure has participated
    # in the same global UTF-8 path ordering.
    captured: _CapturedProjection | None = None
    arms: tuple[Arm, ...] | None = None
    if manifest is not None:
        try:
            captured, arms = _build_captured_projection(
                capsule,
                manifest,
                artifacts["manifest.json"],
                input_index,
                artifacts,
                frozenset(trusted_input_paths),
            )
        except _Failure as failure:
            note_static(failure)
    if static_failure is not None:
        raise static_failure
    assert environment is not None
    assert runner_index is not None
    assert manifest is not None
    assert captured is not None
    assert arms is not None
    assert len(captured.files) == len(input_index.files)
    assert len(arms) == len(manifest.arms)

    case_index, case_index_sha256 = _read_jsonl_models_file(
        root_fd,
        "case-index.jsonl",
        inventory.files["case-index.jsonl"],
        inventory,
        teardown_errors,
        CaseIndexRowV1,
        count_limit=RESOURCE_LIMITS_V1.case_records,
        row_limit=_CASE_INDEX_ROW_CEILING,
    )
    if case_index_sha256 != capsule.case_index_sha256:
        raise _Failure("hash_mismatch", "case-index.jsonl")
    try:
        validate_case_index(case_index, captured, manifest)  # type: ignore[arg-type]
    except ResourceLimitError:
        raise _Failure("resource_limit", "case-index.jsonl") from None
    except (PlanningError, TypeError, ValueError):
        raise _Failure("identity_mismatch", "case-index.jsonl") from None

    plan, plan_sha256 = _read_jsonl_models_file(
        root_fd,
        "plan.jsonl",
        inventory.files["plan.jsonl"],
        inventory,
        teardown_errors,
        PlanRowV1,
        count_limit=RESOURCE_LIMITS_V1.plan_rows,
        row_limit=RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes,
    )
    if plan_sha256 != capsule.plan_sha256:
        raise _Failure("hash_mismatch", "plan.jsonl")
    try:
        validate_plan(plan, capsule.run_id, manifest, case_index, arms)
    except ResourceLimitError:
        raise _Failure("resource_limit", "plan.jsonl") from None
    except (PlanningError, TypeError, ValueError):
        raise _Failure("plan_mismatch", "plan.jsonl") from None

    try:
        journals = snapshot_journal_pair(
            root_fd,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="reject",
        )
    except JournalError as error:
        raise _Failure(
            error.code,
            f"{error.ledger}.jsonl",
            error.row_index,
        ) from None
    except HistoryError as error:
        raise _Failure(
            error.code,
            None if error.code == "io_error" else f"{error.ledger}.jsonl",
            None if error.code == "io_error" else error.row_index,
        ) from None
    event_expected = inventory.files["events.jsonl"]
    raw_expected = inventory.files["raw.jsonl"]
    if (
        journals.events.device,
        journals.events.inode,
        journals.events.mode,
        journals.events.byte_length,
        journals.events.mtime_ns,
        journals.events.ctime_ns,
    ) != (
        event_expected.device,
        event_expected.inode,
        event_expected.mode,
        event_expected.size,
        event_expected.mtime_ns,
        event_expected.ctime_ns,
    ) or (
        journals.raw.device,
        journals.raw.inode,
        journals.raw.mode,
        journals.raw.byte_length,
        journals.raw.mtime_ns,
        journals.raw.ctime_ns,
    ) != (
        raw_expected.device,
        raw_expected.inode,
        raw_expected.mode,
        raw_expected.size,
        raw_expected.mtime_ns,
        raw_expected.ctime_ns,
    ):
        raise _Failure("unstable_snapshot", "events.jsonl")
    if teardown_errors:
        raise teardown_errors[0]
    return _VerifiedCapsuleContext(
        capsule,
        manifest,
        environment,
        input_index,
        captured,
        case_index,
        plan,
        journals.history,
        journals.lifecycle,
        _history_commitment(journals.history),
    )


def _check_lock_identity(root_fd: int, descriptor: int) -> None:
    try:
        opened = _identity(os.fstat(descriptor))
        current = _identity(os.stat(".laconian.lock", dir_fd=root_fd, follow_symlinks=False))
    except OSError:
        raise _Failure("unstable_snapshot", ".laconian.lock") from None
    if not stat.S_ISREG(opened.mode) or not _same_leaf(opened, current):
        raise _Failure("unstable_snapshot", ".laconian.lock")


def _check_public_root_identity(
    path: Path,
    parent_fd: int,
    root_fd: int,
    *,
    expected_parent: _Identity | None = None,
    expected_root: _Identity | None = None,
    recheck_visible_parent: bool = False,
) -> tuple[_Identity, _Identity]:
    fresh_parent_fd: int | None = None
    fresh_parent: _Identity | None = None
    fresh_leaf: _Identity | None = None
    primary: BaseException | None = None
    try:
        parent = _identity(os.fstat(parent_fd))
        root = _identity(os.fstat(root_fd))
        visible_leaf = _identity(os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False))
        if recheck_visible_parent:
            fresh_parent_fd = open_directory_no_follow(path.parent)
            fresh_parent = _identity(os.fstat(fresh_parent_fd))
            fresh_leaf = _identity(
                os.stat(path.name, dir_fd=fresh_parent_fd, follow_symlinks=False)
            )
    except BaseException as error:
        primary = error
    if fresh_parent_fd is not None:
        primary = _close_owned(fresh_parent_fd, path=None, primary=primary)
    if primary is not None:
        if isinstance(primary, AssertionError):
            raise primary
        if isinstance(primary, _Failure):
            raise primary
        raise _Failure("unstable_snapshot", None) from None
    if (
        not stat.S_ISDIR(parent.mode)
        or not stat.S_ISDIR(root.mode)
        or not _same_leaf(root, visible_leaf)
        or (expected_parent is not None and not _same_leaf(parent, expected_parent))
        or (expected_root is not None and root != expected_root)
        or (fresh_parent is not None and not _same_leaf(parent, fresh_parent))
        or (fresh_leaf is not None and not _same_leaf(root, fresh_leaf))
    ):
        raise _Failure("unstable_snapshot", None)
    return parent, root


def _verify_core(root_fd: int) -> VerifyResultV1:
    """Verify one complete descriptor-bound prepared snapshot."""

    inventory = _scan_inventory(root_fd)
    context = _verify_capsule_context_descriptors(root_fd, inventory)
    return _valid_result(context, inventory)


def _verify_prepared_capsule_descriptors(
    capsule_directory_fd: int,
    *,
    results_root_fd: int,
    destination_name: str,
    persistent_lock_descriptor: int,
) -> VerifyResultV1:
    try:
        before = _identity(os.fstat(capsule_directory_fd))
        visible_before = _identity(
            os.stat(destination_name, dir_fd=results_root_fd, follow_symlinks=False)
        )
        if not stat.S_ISDIR(before.mode) or not _same_leaf(before, visible_before):
            raise _Failure("unstable_snapshot", None)
        _check_lock_identity(capsule_directory_fd, persistent_lock_descriptor)
    except _Failure as failure:
        return _invalid_result(failure.code, failure.path, failure.sequence)
    except (OSError, TypeError, ValueError):
        return _invalid_result()

    semantic_failure: _Failure | None = None
    result: VerifyResultV1 | None = None
    try:
        result = _verify_core(capsule_directory_fd)
    except _Failure as failure:
        semantic_failure = failure
    except (OSError, TypeError, ValueError):
        semantic_failure = _Failure("io_error", None)

    try:
        _check_lock_identity(capsule_directory_fd, persistent_lock_descriptor)
        after = _identity(os.fstat(capsule_directory_fd))
        visible_after = _identity(
            os.stat(destination_name, dir_fd=results_root_fd, follow_symlinks=False)
        )
        if before != after or not _same_leaf(after, visible_after):
            raise _Failure("unstable_snapshot", None)
    except _Failure as postcondition_failure:
        return _invalid_result(
            postcondition_failure.code,
            postcondition_failure.path,
            postcondition_failure.sequence,
        )
    except (OSError, TypeError, ValueError):
        return _invalid_result()
    if semantic_failure is not None:
        return _invalid_result(
            semantic_failure.code,
            semantic_failure.path,
            semantic_failure.sequence,
        )
    assert result is not None
    return result


def verify_capsule(path: Path, *, mode: VerificationMode) -> VerifyResultV1:
    """Verify one capsule without mutating it."""

    del mode
    parent_fd: int | None = None
    root_fd: int | None = None
    lock: LockHandle | None = None
    result: VerifyResultV1 | None = None
    visible_path: Path | None = None
    parent_before: _Identity | None = None
    root_before: _Identity | None = None
    try:
        raw_path = os.fspath(path)
        if type(raw_path) is not str or not raw_path:
            raise BoundedIOError("not_directory", "source root is not a directory")
        visible_path = Path(os.path.abspath(raw_path))
        if not visible_path.name:
            raise BoundedIOError("not_directory", "source root is not a directory")
        root_fd = open_directory_no_follow(visible_path)
        parent_fd = open_directory_no_follow(visible_path.parent)
        parent_before, root_before = _check_public_root_identity(
            visible_path,
            parent_fd,
            root_fd,
        )
    except _Failure as failure:
        result = _invalid_result(failure.code, failure.path, failure.sequence)
    except BoundedIOError:
        result = _invalid_result("unsafe_path_type")
    except OSError as error:
        code = "unsafe_path_type" if error.errno in {errno.ELOOP, errno.ENOTDIR} else "io_error"
        result = _invalid_result(code)
    except (RuntimeError, TypeError, ValueError):
        result = _invalid_result()
    except BaseException:
        # Cancellation or an injected host failure must not strand descriptors acquired before a
        # later open failed.  Every owned descriptor gets one ambiguous close attempt; teardown
        # failures never mask the active exception and are never retried.
        for descriptor in (parent_fd, root_fd):
            if descriptor is None:
                continue
            with suppress(BaseException):
                os.close(descriptor)
        parent_fd = None
        root_fd = None
        raise

    try:
        if result is not None:
            raise StopIteration
        assert root_fd is not None
        posix = cast(FilesystemPosixOps, PosixOps())
        try:
            classify_filesystem(root_fd, posix=posix)
        except UnsupportedFilesystemError:
            result = _unsupported_result()
        else:
            try:
                lock = try_acquire_shared_lock(root_fd, posix=posix)
            except FileNotFoundError:
                result = _invalid_result("missing_path", ".laconian.lock")
            except OwnedStagingError:
                result = _invalid_result("unsafe_path_type", ".laconian.lock")
            except OSError as error:
                code = (
                    "unsafe_path_type"
                    if error.errno in {errno.ELOOP, errno.ENOTDIR}
                    else "io_error"
                )
                result = _invalid_result(code, ".laconian.lock")
            if lock is None and result is None:
                result = _busy_result()
            elif lock is not None:
                try:
                    _check_lock_identity(root_fd, lock.descriptor)
                    result = _verify_core(root_fd)
                except _Failure as failure:
                    result = _invalid_result(failure.code, failure.path, failure.sequence)
                except (OSError, TypeError, ValueError):
                    result = _invalid_result()
    except StopIteration:
        pass
    except AssertionError:
        raise
    except BaseException:
        result = _invalid_result()

    if result is None:
        result = _invalid_result()
    if root_before is not None and parent_before is not None:
        try:
            assert visible_path is not None and parent_fd is not None and root_fd is not None
            if lock is not None:
                _check_lock_identity(root_fd, lock.descriptor)
            _check_public_root_identity(
                visible_path,
                parent_fd,
                root_fd,
                expected_parent=parent_before,
                expected_root=root_before,
                recheck_visible_parent=True,
            )
        except _Failure as failure:
            existing = result.first_error
            more_specific_snapshot = (
                failure.code == "unstable_snapshot"
                and failure.path is None
                and existing is not None
                and existing.code == "unstable_snapshot"
                and existing.path is not None
            )
            if not more_specific_snapshot and (
                failure.code != "io_error" or result.status == "valid"
            ):
                result = _invalid_result(failure.code, failure.path, failure.sequence)
        except (OSError, TypeError, ValueError):
            result = _invalid_result()
    if lock is not None:
        try:
            lock.close()
        except BaseException:
            if result.status == "valid":
                result = _invalid_result("io_error", ".laconian.lock")
    if root_fd is not None:
        try:
            os.close(root_fd)
        except BaseException:
            if result.status == "valid":
                result = _invalid_result()
    if parent_fd is not None:
        try:
            os.close(parent_fd)
        except BaseException:
            if result.status == "valid":
                result = _invalid_result()
    return result
