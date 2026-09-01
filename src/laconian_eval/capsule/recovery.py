"""Pure recovery planning for validated generation-capsule journals."""

from __future__ import annotations

import fcntl
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from types import FunctionType
from typing import Literal, NoReturn, cast
from uuid import RFC_4122, UUID

from laconian_eval.capsule.attempts import derive_attempt_id
from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.canonical import canonical_timestamp
from laconian_eval.capsule.events import (
    EventV1,
    RequestStartedEventV1,
    SealRequestedEventV1,
    event_jsonl,
    make_event,
)
from laconian_eval.capsule.filesystem import (
    PERSISTENT_LOCK_NAME,
    FilesystemPosixOps,
    LockHandle,
    OwnedStaging,
    UnsupportedFilesystemError,
    classify_filesystem,
    cleanup_owned_staging,
    create_owned_staging,
    run_filesystem_probes,
)
from laconian_eval.capsule.history import (
    AttemptCommitV1,
    HistoryContextV1,
    HistoryError,
    LifecycleProjectionV1,
    RawCommitProjectionV1,
    RawHistorySummaryV1,
    RecoveryRequirementV1,
    ValidatedHistoryV1,
    derive_lifecycle_v1,
)
from laconian_eval.capsule.journal import (
    JournalCursorV1,
    JournalError,
    JournalPairSnapshotV1,
    JournalSnapshotV1,
    JournalTransaction,
    Ledger,
    TailPolicy,
    _final_fstat,
    _joint_recheck_transaction_pair,
    _rehash_transaction_pair,
    _snapshot_transaction_pair,
    append_event,
    open_journal_transaction,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    EnvironmentV1,
    PlanRowV1,
)

RecoveryCode = Literal[
    "io_error",
    "unsafe_path_type",
    "noncanonical_json",
    "invalid_model",
    "resource_limit",
    "hash_mismatch",
    "identity_mismatch",
    "history_mismatch",
    "retry_mismatch",
    "lifecycle_mismatch",
    "unstable_snapshot",
]
RecoveryDisposition = Literal[
    "provider_ready",
    "ambiguous",
    "authentication_stopped",
    "complete",
    "sealing_interrupted",
]

_GENERIC_RECOVERY_ERROR = "capsule recovery rejected"
_MUTATOR_SESSION_AUTHORITY = object()
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NATIVE_POSIX_MRO = PosixOps.__mro__
_NATIVE_POSIX_NAMESPACE = tuple(
    sorted(vars(PosixOps).items(), key=lambda item: item[0].encode("utf-8"))
)
_NATIVE_POSIX_FUNCTION_SEALS = tuple(
    (
        name,
        function,
        function.__code__,
        None
        if function.__defaults__ is None
        else (id(function.__defaults__), tuple(id(item) for item in function.__defaults__)),
        None
        if function.__kwdefaults__ is None
        else (
            id(function.__kwdefaults__),
            tuple(
                (key, id(function.__kwdefaults__[key])) for key in sorted(function.__kwdefaults__)
            ),
        ),
    )
    for name, function in _NATIVE_POSIX_NAMESPACE
    if type(function) is FunctionType
)
_RECOVERY_KINDS = (
    "request_finished",
    "authentication_stopped",
    "delivery_ambiguous",
    "generation_completed",
)
_TERMINAL_REASONS = frozenset(
    {
        "success",
        "retry_exhausted",
        "provider_rejected",
        "authentication_stopped",
        "ambiguous_delivery",
    }
)


class RecoveryError(ContentFreeCapsuleError):
    """One content-free recovery-planning failure."""

    def __init__(self, code: RecoveryCode) -> None:
        self.code = code
        super().__init__(_GENERIC_RECOVERY_ERROR)


def _fail(code: RecoveryCode) -> NoReturn:
    raise RecoveryError(code)


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise TypeError
    return value


def _nonnegative(value: object) -> int:
    if type(value) is not int or value < 0:
        raise TypeError
    return value


def _provider_text(value: object) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8", errors="strict")) > RESOURCE_LIMITS_V1.bounded_string_bytes
        or any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value)
    ):
        raise TypeError
    return value


def _strict_start(value: object) -> RequestStartedEventV1:
    if type(value) is not RequestStartedEventV1:
        raise TypeError
    payload = RequestStartedEventV1.model_dump(
        value,
        mode="python",
        round_trip=True,
        warnings=False,
    )
    return RequestStartedEventV1.model_validate(payload)


def _strict_raw_projection(value: object) -> RawCommitProjectionV1:
    if type(value) is not RawCommitProjectionV1:
        raise TypeError
    terminal_reason = value.terminal_reason
    if terminal_reason is not None and (
        type(terminal_reason) is not str or terminal_reason not in _TERMINAL_REASONS
    ):
        raise TypeError
    backoff_ms = None if value.backoff_ms is None else _nonnegative(value.backoff_ms)
    response_model = None if value.response_model is None else _provider_text(value.response_model)
    projection = RawCommitProjectionV1(
        _nonnegative(value.call_sequence),
        _sha256(value.plan_item_id),
        _sha256(value.attempt_id),
        _nonnegative(value.attempt),
        value.terminal,
        terminal_reason,
        backoff_ms,
        _sha256(value.raw_record_sha256),
        response_model,
    )
    if (
        type(projection.terminal) is not bool
        or not 1 <= projection.attempt <= 6
        or (
            projection.terminal
            and (projection.terminal_reason is None or projection.backoff_ms is not None)
        )
        or (
            not projection.terminal
            and (
                projection.terminal_reason is not None
                or projection.backoff_ms != 100 * 2 ** (projection.attempt - 1)
            )
        )
        or (projection.terminal_reason == "success") != (projection.response_model is not None)
    ):
        raise TypeError
    return projection


def _strict_requirement(value: object) -> RecoveryRequirementV1:
    if type(value) is not RecoveryRequirementV1 or value.kind not in _RECOVERY_KINDS:
        raise TypeError

    def optional_sha(candidate: object) -> str | None:
        return None if candidate is None else _sha256(candidate)

    requirement = RecoveryRequirementV1(
        value.kind,
        _nonnegative(value.call_sequence),
        optional_sha(value.plan_item_id),
        optional_sha(value.attempt_id),
        optional_sha(value.origin_request_started_event_id),
        optional_sha(value.raw_record_sha256),
        optional_sha(value.origin_request_finished_event_id),
    )
    values = (
        requirement.plan_item_id,
        requirement.attempt_id,
        requirement.origin_request_started_event_id,
        requirement.raw_record_sha256,
    )
    if requirement.kind == "request_finished":
        if None in values or requirement.origin_request_finished_event_id is not None:
            raise TypeError
    elif requirement.kind in {"authentication_stopped", "delivery_ambiguous"}:
        if None in values[:3] or values[3] is not None:
            raise TypeError
    elif any(item is not None for item in values):
        raise TypeError
    return requirement


def _strict_history(value: object, context: HistoryContextV1) -> ValidatedHistoryV1:
    if type(value) is not ValidatedHistoryV1:
        raise TypeError
    plan = context.plan
    tuple_fields = (
        value.resolved_plan_item_ids,
        value.missing_plan_item_ids,
        value.returned_models,
        value.recovery_requirements,
    )
    if any(type(item) is not tuple for item in tuple_fields):
        raise TypeError
    resolved = tuple(_sha256(item) for item in value.resolved_plan_item_ids)
    missing = tuple(_sha256(item) for item in value.missing_plan_item_ids)
    returned = tuple(_provider_text(item) for item in value.returned_models)
    summary_value = value.raw_summary
    if type(summary_value) is not RawHistorySummaryV1:
        raise TypeError
    raw_summary = RawHistorySummaryV1(
        raw_attempt_count=_nonnegative(summary_value.raw_attempt_count),
        usage_complete_count=_nonnegative(summary_value.usage_complete_count),
        usage_partial_count=_nonnegative(summary_value.usage_partial_count),
        usage_unavailable_count=_nonnegative(summary_value.usage_unavailable_count),
        redacted_output_attempt_count=_nonnegative(summary_value.redacted_output_attempt_count),
        redacted_output_replacement_count=_nonnegative(
            summary_value.redacted_output_replacement_count
        ),
    )
    plan_ids = tuple(row.plan_item_id for row in plan)
    if (
        resolved != plan_ids[: len(resolved)]
        or missing
        != tuple(sorted(plan_ids[len(resolved) :], key=lambda item: item.encode("utf-8")))
        or returned != tuple(sorted(set(returned), key=lambda item: item.encode("utf-8")))
        or len(returned) > len(resolved)
        or len(resolved) > raw_summary.raw_attempt_count
    ):
        raise TypeError
    expected_ordinal = None if not missing else len(resolved)
    if value.next_unresolved_plan_ordinal != expected_ordinal or (
        value.next_unresolved_plan_ordinal is not None
        and type(value.next_unresolved_plan_ordinal) is not int
    ):
        raise TypeError
    next_call = _nonnegative(value.next_call_sequence)
    next_attempt = value.next_attempt_number
    if (next_attempt is None) != (expected_ordinal is None) or (
        next_attempt is not None and (type(next_attempt) is not int or not 1 <= next_attempt <= 6)
    ):
        raise TypeError
    open_attempt: AttemptCommitV1 | None = None
    if value.open_attempt is not None:
        if type(value.open_attempt) is not AttemptCommitV1 or value.open_attempt.finish is not None:
            raise TypeError
        start = _strict_start(value.open_attempt.start)
        target = next(
            (row for row in plan if row.plan_item_id == start.payload.plan_item_id),
            None,
        )
        if (
            target is None
            or start.run_id != context.capsule.run_id
            or start.operation_id == start.run_id
            or start.execution_session_id is None
            or start.payload.provider != context.manifest.provider.kind
            or start.payload.model != context.manifest.provider.model
            or start.payload.prompt_sha256 != target.prompt_sha256
            or start.payload.case_definition_sha256 != target.case_definition_sha256
            or start.payload.instruction_sha256 != target.instruction_sha256
            or start.payload.request_config_sha256 != target.request_config_sha256
            or start.payload.attempt > 1 + context.manifest.retry.max_transient_retries
            or start.payload.attempt_id
            != derive_attempt_id(
                context.capsule.run_id,
                target.plan_item_id,
                start.payload.attempt,
            )
        ):
            raise TypeError
        raw = (
            None
            if value.open_attempt.raw is None
            else _strict_raw_projection(value.open_attempt.raw)
        )
        if raw is not None and (
            raw.call_sequence != start.payload.call_sequence
            or raw.plan_item_id != start.payload.plan_item_id
            or raw.attempt_id != start.payload.attempt_id
            or raw.attempt != start.payload.attempt
        ):
            raise TypeError
        open_attempt = AttemptCommitV1(start, raw, None)
    requirements = tuple(_strict_requirement(item) for item in value.recovery_requirements)
    order = tuple(_RECOVERY_KINDS.index(item.kind) for item in requirements)
    if len(requirements) > 3 or order != tuple(sorted(set(order))):
        raise TypeError
    booleans = (
        value.request_history_present,
        value.execution_history_present,
        value.latest_no_call_blocked,
        value.latest_event_recovered,
        value.has_ambiguous_delivery,
        value.has_authentication_stop,
    )
    if any(type(item) is not bool for item in booleans):
        raise TypeError
    blocked_reason = value.latest_no_call_blocked_reason
    if blocked_reason not in (None, "credential_unavailable", "provider_unavailable") or (
        blocked_reason is not None and type(blocked_reason) is not str
    ):
        raise TypeError
    if (
        value.request_history_present != (next_call > 0)
        or (value.request_history_present and not value.execution_history_present)
        or (value.request_history_present and value.latest_no_call_blocked)
        or value.latest_no_call_blocked != (blocked_reason is not None)
        or (blocked_reason is not None and not value.execution_history_present)
        or (
            (value.has_ambiguous_delivery or value.has_authentication_stop)
            and (not value.request_history_present or not value.execution_history_present)
        )
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
            if (
                not missing
                or expected_ordinal is None
                or target_id != plan[expected_ordinal].plan_item_id
                or not value.has_ambiguous_delivery
                or requirements
            ):
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
            elif (
                not missing
                or expected_ordinal is None
                or target_id != plan[expected_ordinal].plan_item_id
            ):
                raise TypeError
            if (
                raw.terminal_reason == "authentication_stopped"
                and not value.has_authentication_stop
            ):
                raise TypeError
            if raw.terminal_reason == "ambiguous_delivery" and not value.has_ambiguous_delivery:
                raise TypeError
    rawless_open = open_attempt is not None and open_attempt.raw is None
    usage_count = (
        raw_summary.usage_complete_count
        + raw_summary.usage_partial_count
        + raw_summary.usage_unavailable_count
    )
    if (
        raw_summary.raw_attempt_count != next_call - int(rawless_open)
        or usage_count != raw_summary.raw_attempt_count
        or raw_summary.redacted_output_attempt_count > raw_summary.raw_attempt_count
        or (raw_summary.redacted_output_attempt_count == 0)
        != (raw_summary.redacted_output_replacement_count == 0)
        or raw_summary.redacted_output_replacement_count < raw_summary.redacted_output_attempt_count
    ):
        raise TypeError
    requirement_kinds = tuple(item.kind for item in requirements)
    if open_attempt is None and "request_finished" in requirement_kinds:
        raise TypeError
    if ("authentication_stopped" in requirement_kinds and not value.has_authentication_stop) or (
        "delivery_ambiguous" in requirement_kinds and not value.has_ambiguous_delivery
    ):
        raise TypeError
    completion = next(
        (item for item in requirements if item.kind == "generation_completed"),
        None,
    )
    if completion is not None:
        if missing or not value.request_history_present:
            raise TypeError
        if open_attempt is None and completion.origin_request_finished_event_id is None:
            raise TypeError
        if open_attempt is not None and completion.origin_request_finished_event_id is not None:
            raise TypeError
    seal = None
    if value.seal_requested is not None:
        if type(value.seal_requested) is not SealRequestedEventV1:
            raise TypeError
        payload = SealRequestedEventV1.model_dump(
            value.seal_requested,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        seal = SealRequestedEventV1.model_validate(payload)
        if requirements:
            raise TypeError
    return ValidatedHistoryV1(
        resolved_plan_item_ids=resolved,
        missing_plan_item_ids=missing,
        returned_models=returned,
        raw_summary=raw_summary,
        next_unresolved_plan_ordinal=expected_ordinal,
        next_call_sequence=next_call,
        next_attempt_number=next_attempt,
        open_attempt=open_attempt,
        recovery_requirements=requirements,
        request_history_present=booleans[0],
        execution_history_present=booleans[1],
        latest_no_call_blocked=booleans[2],
        latest_no_call_blocked_reason=blocked_reason,
        latest_event_recovered=booleans[3],
        has_ambiguous_delivery=booleans[4],
        has_authentication_stop=booleans[5],
        seal_requested=seal,
    )


@dataclass(frozen=True, slots=True)
class RecoveryContextV1:
    capsule: CapsuleV1
    manifest: ResolvedManifestV2
    environment: EnvironmentV1
    plan: tuple[PlanRowV1, ...]
    immutable_evidence_bytes: int
    history: ValidatedHistoryV1
    lifecycle: LifecycleProjectionV1
    event_snapshot: JournalSnapshotV1
    raw_snapshot: JournalSnapshotV1

    def __post_init__(self) -> None:
        try:
            base = HistoryContextV1(self.capsule, self.manifest, self.environment, self.plan)
            immutable_evidence_bytes = _nonnegative(self.immutable_evidence_bytes)
            if not base.plan:
                raise TypeError
            history = _strict_history(self.history, base)
            lifecycle = derive_lifecycle_v1(history)
            if type(self.lifecycle) is not LifecycleProjectionV1 or self.lifecycle != lifecycle:
                raise TypeError
            event_snapshot = _strict_snapshot(self.event_snapshot, "events")
            raw_snapshot = _strict_snapshot(self.raw_snapshot, "raw")
            rawless_open = history.open_attempt is not None and history.open_attempt.raw is None
            if raw_snapshot.row_count != history.next_call_sequence - int(rawless_open):
                raise TypeError
            if (
                history.open_attempt is not None
                and history.open_attempt.start.sequence >= event_snapshot.row_count
            ):
                raise TypeError
            object.__setattr__(self, "capsule", base.capsule)
            object.__setattr__(self, "manifest", base.manifest)
            object.__setattr__(self, "environment", base.environment)
            object.__setattr__(self, "plan", base.plan)
            object.__setattr__(self, "immutable_evidence_bytes", immutable_evidence_bytes)
            object.__setattr__(self, "history", history)
            object.__setattr__(self, "lifecycle", lifecycle)
            object.__setattr__(self, "event_snapshot", event_snapshot)
            object.__setattr__(self, "raw_snapshot", raw_snapshot)
        except Exception:
            _fail("invalid_model")


@dataclass(frozen=True, slots=True)
class TailTruncationV1:
    ledger: Ledger
    original_byte_length: int
    truncate_to: int
    removed_byte_count: int
    removed_sha256: str
    related_attempt_id: str | None

    def __post_init__(self) -> None:
        try:
            if (
                self.ledger not in ("events", "raw")
                or type(self.original_byte_length) is not int
                or type(self.truncate_to) is not int
                or type(self.removed_byte_count) is not int
                or self.original_byte_length < 1
                or self.truncate_to < 0
                or self.removed_byte_count < 1
                or self.truncate_to + self.removed_byte_count != self.original_byte_length
                or _sha256(self.removed_sha256) != self.removed_sha256
                or (
                    self.related_attempt_id is not None
                    and _sha256(self.related_attempt_id) != self.related_attempt_id
                )
                or (self.ledger == "events" and self.related_attempt_id is not None)
            ):
                raise TypeError
        except Exception:
            _fail("invalid_model")


@dataclass(frozen=True, slots=True)
class RecoveryPlanV1:
    truncations: tuple[TailTruncationV1, ...]
    append_events: tuple[EventV1, ...]
    disposition: RecoveryDisposition
    post_mutable_bytes: int
    seal_reservation_bytes: int
    crash_reservation_bytes: int

    def __post_init__(self) -> None:
        try:
            if (
                type(self.truncations) is not tuple
                or type(self.append_events) is not tuple
                or self.disposition
                not in {
                    "provider_ready",
                    "ambiguous",
                    "authentication_stopped",
                    "complete",
                    "sealing_interrupted",
                }
            ):
                raise TypeError
            truncations = tuple(
                TailTruncationV1(
                    item.ledger,
                    item.original_byte_length,
                    item.truncate_to,
                    item.removed_byte_count,
                    item.removed_sha256,
                    item.related_attempt_id,
                )
                for item in self.truncations
                if type(item) is TailTruncationV1
            )
            if len(truncations) != len(self.truncations):
                raise TypeError
            append_events = tuple(self.append_events)
            for index, event in enumerate(append_events):
                event_jsonl(event)
                if index and event.sequence != append_events[index - 1].sequence + 1:
                    raise TypeError
            integers = (
                self.post_mutable_bytes,
                self.seal_reservation_bytes,
                self.crash_reservation_bytes,
            )
            if any(type(item) is not int or item < 0 for item in integers):
                raise TypeError
            object.__setattr__(self, "truncations", truncations)
            object.__setattr__(self, "append_events", append_events)
        except RecoveryError:
            raise
        except Exception:
            _fail("invalid_model")


@dataclass(frozen=True, slots=True)
class AppliedRecoveryV1:
    disposition: RecoveryDisposition
    appended_event_count: int
    events: JournalSnapshotV1
    raw: JournalSnapshotV1

    def __post_init__(self) -> None:
        try:
            if (
                self.disposition
                not in {
                    "provider_ready",
                    "ambiguous",
                    "authentication_stopped",
                    "complete",
                    "sealing_interrupted",
                }
                or type(self.appended_event_count) is not int
                or self.appended_event_count < 0
            ):
                raise TypeError
            object.__setattr__(self, "events", _strict_snapshot(self.events, "events"))
            object.__setattr__(self, "raw", _strict_snapshot(self.raw, "raw"))
        except RecoveryError:
            raise
        except Exception:
            _fail("invalid_model")


@dataclass(frozen=True, slots=True)
class _VerifiedRecoveryProofV1:
    history_context: HistoryContextV1
    journal_pair: JournalPairSnapshotV1
    immutable_evidence_bytes: int
    root_identity: tuple[int, int, int, int, int, int]
    parent_identity: tuple[int, int, int, int, int, int]
    destination_name: str
    immutable_tree_sha256: str
    _source: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            base = HistoryContextV1(
                self.history_context.capsule,
                self.history_context.manifest,
                self.history_context.environment,
                self.history_context.plan,
            )
            if type(self.journal_pair) is not JournalPairSnapshotV1:
                raise TypeError
            events = _strict_snapshot(self.journal_pair.events, "events")
            raw = _strict_snapshot(self.journal_pair.raw, "raw")
            history = _strict_history(self.journal_pair.history, base)
            lifecycle = derive_lifecycle_v1(history)
            if lifecycle != self.journal_pair.lifecycle:
                raise TypeError
            immutable_evidence_bytes = _nonnegative(self.immutable_evidence_bytes)
            identities: list[tuple[int, int, int, int, int, int]] = []
            for identity in (self.root_identity, self.parent_identity):
                if (
                    type(identity) is not tuple
                    or len(identity) != 6
                    or any(type(item) is not int or item < 0 for item in identity)
                    or not stat.S_ISDIR(identity[2])
                ):
                    raise TypeError
                identities.append(tuple(identity))  # type: ignore[arg-type]
            if (
                type(self.destination_name) is not str
                or not self.destination_name
                or self.destination_name in {".", ".."}
                or "/" in self.destination_name
                or "\x00" in self.destination_name
            ):
                raise TypeError
            immutable_tree_sha256 = _sha256(self.immutable_tree_sha256)
            journal_pair = JournalPairSnapshotV1(
                events,
                raw,
                history,
                lifecycle,
                self.journal_pair.reserved_operation_id,
            )
            object.__setattr__(self, "history_context", base)
            object.__setattr__(self, "journal_pair", journal_pair)
            object.__setattr__(self, "immutable_evidence_bytes", immutable_evidence_bytes)
            object.__setattr__(self, "root_identity", identities[0])
            object.__setattr__(self, "parent_identity", identities[1])
            object.__setattr__(self, "immutable_tree_sha256", immutable_tree_sha256)
        except Exception:
            _fail("invalid_model")


@dataclass(frozen=True, slots=True)
class _MutatorSessionV1:
    transaction: JournalTransaction
    verified: _VerifiedRecoveryProofV1
    operation_id: UUID
    occurred_at: datetime
    lock_handle: LockHandle
    parent_fd: int
    _initial_pair: JournalPairSnapshotV1
    _authority: object = field(repr=False, compare=False)

    @property
    def history_context(self) -> HistoryContextV1:
        return self.verified.history_context

    def __post_init__(self) -> None:
        try:
            if type(self.verified) is not _VerifiedRecoveryProofV1:
                raise TypeError
            if self._authority is not _MUTATOR_SESSION_AUTHORITY:
                _fail("identity_mismatch")
            verified = _VerifiedRecoveryProofV1(
                self.verified.history_context,
                self.verified.journal_pair,
                self.verified.immutable_evidence_bytes,
                self.verified.root_identity,
                self.verified.parent_identity,
                self.verified.destination_name,
                self.verified.immutable_tree_sha256,
                self.verified._source,
            )
            operation_id = _strict_operation_id(
                self.operation_id,
                verified.history_context.capsule.run_id,
            )
            occurred_at = _strict_occurred_at(self.occurred_at)
            if (
                type(self._initial_pair) is not JournalPairSnapshotV1
                or self._initial_pair.reserved_operation_id != operation_id
                or self._initial_pair != verified.journal_pair
                or self.transaction._immutable_evidence_bytes != verified.immutable_evidence_bytes
                or type(self.parent_fd) is not int
                or self.parent_fd < 0
            ):
                raise TypeError
            _validate_mutator_authority(
                self.transaction,
                self.lock_handle,
            )
            _validate_verified_root_binding(
                self.transaction._capsule_fd,
                self.parent_fd,
                verified,
            )
            object.__setattr__(self, "verified", verified)
            object.__setattr__(self, "operation_id", operation_id)
            object.__setattr__(self, "occurred_at", occurred_at)
        except RecoveryError:
            raise
        except Exception:
            _fail("invalid_model")


def _strict_snapshot(value: object, ledger: Ledger) -> JournalSnapshotV1:
    if type(value) is not JournalSnapshotV1:
        raise TypeError
    integers = (
        value.device,
        value.inode,
        value.mode,
        value.byte_length,
        value.mtime_ns,
        value.ctime_ns,
        value.row_count,
        value.tail_byte_count,
    )
    if any(type(item) is not int or item < 0 for item in integers):
        raise TypeError
    if (
        not stat.S_ISREG(value.mode)
        or value.tail_byte_count > value.byte_length
        or (value.tail_byte_count == 0) != (value.tail_sha256 is None)
        or (value.tail_sha256 is not None and _sha256(value.tail_sha256) != value.tail_sha256)
        or _sha256(value.sha256) != value.sha256
        or (ledger == "events" and value.row_count < 1)
        or (ledger == "raw" and value.row_count > RESOURCE_LIMITS_V1.raw_rows)
    ):
        raise TypeError
    return JournalSnapshotV1(
        *integers[:6],
        value.row_count,
        value.sha256,
        value.tail_byte_count,
        value.tail_sha256,
    )


def _strict_operation_id(value: object, run_id: UUID) -> UUID:
    if (
        type(value) is not UUID
        or type(value.int) is not int
        or value.version != 4
        or value.variant != RFC_4122
        or value == run_id
    ):
        raise TypeError
    return UUID(str(value))


def _strict_occurred_at(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise TypeError
    canonical_timestamp(value)
    return datetime.fromisoformat(value.isoformat())


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _validate_verified_root_binding(
    root_fd: int,
    parent_fd: int,
    verified: _VerifiedRecoveryProofV1,
) -> None:
    try:
        root = os.fstat(root_fd)
        parent = os.fstat(parent_fd)
        visible = os.stat(
            verified.destination_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except OSError:
        _fail("unstable_snapshot")
    if (
        _stat_identity(root) != verified.root_identity
        or _stat_identity(parent) != verified.parent_identity
        or (visible.st_dev, visible.st_ino, visible.st_mode)
        != (root.st_dev, root.st_ino, root.st_mode)
    ):
        _fail("unstable_snapshot")


def _load_verified_recovery_context(
    root_fd: int,
    *,
    parent_fd: int,
    destination_name: str,
    reserved_operation_id: UUID | None,
) -> _VerifiedRecoveryProofV1:
    """Run the read-only verifier and compact its descriptor-bound result."""

    from laconian_eval.capsule.verify import (
        _Failure,
        _VerifiedRecoveryContext,
        _verify_recoverable_capsule_descriptors,
    )

    try:
        verified = _verify_recoverable_capsule_descriptors(
            root_fd,
            parent_fd=parent_fd,
            destination_name=destination_name,
            # The verifier core already accepts ``None`` and forwards it to the
            # optional history reservation; its private annotation remains
            # narrower for the initial session-construction caller.
            reserved_operation_id=cast(UUID, reserved_operation_id),
        )
    except _Failure as error:
        _fail(_recovery_code(error.code))
    if type(verified) is not _VerifiedRecoveryContext:
        _fail("invalid_model")
    context = verified.context
    root = verified.root_identity
    parent = verified.parent_identity
    return _VerifiedRecoveryProofV1(
        HistoryContextV1(
            context.capsule,
            context.manifest,
            context.environment,
            context.plan,
        ),
        context._journal_pair,
        verified.immutable_evidence_bytes,
        (root.device, root.inode, root.mode, root.size, root.mtime_ns, root.ctime_ns),
        (
            parent.device,
            parent.inode,
            parent.mode,
            parent.size,
            parent.mtime_ns,
            parent.ctime_ns,
        ),
        verified.destination_name,
        verified.immutable_tree_sha256,
        verified,
    )


def _validate_lock_authority(
    capsule_fd: object,
    lock_handle: object,
) -> None:
    if (
        type(capsule_fd) is not int
        or capsule_fd < 0
        or type(lock_handle) is not LockHandle
        or lock_handle._closed
        or lock_handle._exclusive is not True
        or not _is_native_mutator_posix(lock_handle._posix)
    ):
        _fail("identity_mismatch")
    try:
        root = os.fstat(capsule_fd)
        lock = os.fstat(lock_handle.descriptor)
        lock_flags = fcntl.fcntl(lock_handle.descriptor, fcntl.F_GETFL)
        lock_path = os.stat(
            PERSISTENT_LOCK_NAME,
            dir_fd=capsule_fd,
            follow_symlinks=False,
        )
    except OSError:
        _fail("unstable_snapshot")
    if (
        not stat.S_ISDIR(root.st_mode)
        or not stat.S_ISREG(lock.st_mode)
        or lock_flags & os.O_ACCMODE != os.O_RDWR
        or (lock.st_dev, lock.st_ino, lock.st_mode)
        != (lock_path.st_dev, lock_path.st_ino, lock_path.st_mode)
        or lock_handle.descriptor == capsule_fd
    ):
        _fail("identity_mismatch")
    try:
        lock_handle._posix.acquire_lock(
            lock_handle.descriptor,
            exclusive=True,
            blocking=False,
        )
    except BlockingIOError:
        _fail("identity_mismatch")
    except OSError:
        _fail("io_error")


def _new_mutator_posix() -> PosixOps:
    """Construct the production syscall capability; tests replace this private seam."""

    return PosixOps()


def _is_native_mutator_posix(value: object) -> bool:
    namespace = vars(PosixOps)
    return (
        type(value) is PosixOps
        and PosixOps.__mro__ == _NATIVE_POSIX_MRO
        and len(namespace) == len(_NATIVE_POSIX_NAMESPACE)
        and all(
            name in namespace and namespace[name] is expected
            for name, expected in _NATIVE_POSIX_NAMESPACE
        )
        and all(
            namespace.get(name) is function
            and function.__code__ is code
            and (
                None
                if function.__defaults__ is None
                else (
                    id(function.__defaults__),
                    tuple(id(item) for item in function.__defaults__),
                )
            )
            == defaults
            and (
                None
                if function.__kwdefaults__ is None
                else (
                    id(function.__kwdefaults__),
                    tuple(
                        (key, id(function.__kwdefaults__[key]))
                        for key in sorted(function.__kwdefaults__)
                    ),
                )
            )
            == kwdefaults
            for name, function, code, defaults, kwdefaults in _NATIVE_POSIX_FUNCTION_SEALS
        )
        and value._flock is fcntl.flock
        and value._fsync is os.fsync
        and value._mountinfo_open is os.open
        and value._mountinfo_read is os.read
        and value._mountinfo_close is os.close
    )


def _bind_mutator_posix(capsule_fd: int, lock_handle: object) -> LockHandle:
    """Replace caller-supplied syscall adapters and establish the real exclusive lock."""

    if (
        type(lock_handle) is not LockHandle
        or lock_handle._closed
        or lock_handle._exclusive is not True
    ):
        _fail("identity_mismatch")
    try:
        root = os.fstat(capsule_fd)
        lock = os.fstat(lock_handle.descriptor)
        lock_path = os.stat(
            PERSISTENT_LOCK_NAME,
            dir_fd=capsule_fd,
            follow_symlinks=False,
        )
        lock_flags = fcntl.fcntl(lock_handle.descriptor, fcntl.F_GETFL)
    except OSError:
        _fail("unstable_snapshot")
    if (
        not stat.S_ISDIR(root.st_mode)
        or not stat.S_ISREG(lock.st_mode)
        or lock_flags & os.O_ACCMODE != os.O_RDWR
        or (lock.st_dev, lock.st_ino, lock.st_mode)
        != (lock_path.st_dev, lock_path.st_ino, lock_path.st_mode)
        or lock_handle.descriptor == capsule_fd
    ):
        _fail("identity_mismatch")
    try:
        runtime = _new_mutator_posix()
        if not _is_native_mutator_posix(runtime):
            _fail("identity_mismatch")
        runtime.acquire_lock(
            lock_handle.descriptor,
            exclusive=True,
            blocking=False,
        )
    except RecoveryError:
        raise
    except BlockingIOError:
        _fail("identity_mismatch")
    except (OSError, RuntimeError, ValueError):
        _fail("io_error")
    lock_handle._posix = cast(FilesystemPosixOps, runtime)
    return lock_handle


def _validate_mutator_authority(
    transaction: object,
    lock_handle: object,
) -> None:
    if (
        type(transaction) is not JournalTransaction
        or transaction._closed
        or transaction._poisoned
        or type(lock_handle) is not LockHandle
        or lock_handle._posix is not transaction._posix
    ):
        _fail("identity_mismatch")
    _validate_lock_authority(transaction._capsule_fd, lock_handle)
    if lock_handle.descriptor in {
        transaction._event_fd,
        transaction._raw_fd,
    }:
        _fail("identity_mismatch")


def _preflight_identity(
    capsule_fd: int,
    parent_fd: int,
    destination_name: str,
    lock_handle: LockHandle,
) -> tuple[tuple[int, int, int], ...]:
    try:
        root = os.fstat(capsule_fd)
        parent = os.fstat(parent_fd)
        visible = os.stat(
            destination_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        lock = os.fstat(lock_handle.descriptor)
        lock_path = os.stat(
            PERSISTENT_LOCK_NAME,
            dir_fd=capsule_fd,
            follow_symlinks=False,
        )
    except OSError:
        _fail("unstable_snapshot")
    identities = tuple(
        (item.st_dev, item.st_ino, item.st_mode)
        for item in (root, parent, visible, lock, lock_path)
    )
    if identities[0] != identities[2] or identities[3] != identities[4]:
        _fail("identity_mismatch")
    return identities


def _run_mutator_filesystem_preflight(
    capsule_fd: int,
    *,
    parent_fd: int,
    destination_name: str,
    operation_id: UUID,
    lock_handle: LockHandle,
) -> None:
    """Prove the live mount contract while the exact capsule lock remains held."""

    _validate_lock_authority(capsule_fd, lock_handle)
    before = _preflight_identity(
        capsule_fd,
        parent_fd,
        destination_name,
        lock_handle,
    )
    staging: OwnedStaging | None = None
    failure: BaseException | None = None
    fatal: BaseException | None = None
    unsupported: UnsupportedFilesystemError | None = None
    try:
        capsule_identity = classify_filesystem(capsule_fd, posix=lock_handle._posix)
        staging = create_owned_staging(parent_fd, operation_id)
        probed_identity = run_filesystem_probes(
            capsule_fd,
            staging,
            posix=lock_handle._posix,
        )
        if probed_identity != capsule_identity:
            raise ValueError
    except BaseException as error:
        if not isinstance(error, Exception):
            fatal = error
        elif isinstance(error, UnsupportedFilesystemError):
            unsupported = error
        else:
            failure = error
    if staging is not None and staging.state == "owned":
        try:
            cleanup_owned_staging(staging, posix=lock_handle._posix)
        except BaseException as error:
            if not isinstance(error, Exception):
                if fatal is None:
                    fatal = error
            elif failure is None:
                failure = error
    if fatal is not None:
        raise fatal
    if failure is not None:
        _fail("identity_mismatch")
    if unsupported is not None:
        raise unsupported
    _validate_lock_authority(capsule_fd, lock_handle)
    after = _preflight_identity(
        capsule_fd,
        parent_fd,
        destination_name,
        lock_handle,
    )
    if after != before:
        _fail("unstable_snapshot")


def _make_mutator_session_v1(
    capsule_fd: int,
    *,
    parent_fd: int,
    destination_name: str,
    operation_id: UUID,
    occurred_at: datetime,
    lock_handle: LockHandle,
) -> _MutatorSessionV1:
    """Verify static evidence, then open and bind the only writable journal pair."""

    transaction: JournalTransaction | None = None
    try:
        if (
            type(operation_id) is not UUID
            or operation_id.version != 4
            or operation_id.variant != RFC_4122
        ):
            raise TypeError
        timestamp = _strict_occurred_at(occurred_at)
        lock_handle = _bind_mutator_posix(capsule_fd, lock_handle)
        _run_mutator_filesystem_preflight(
            capsule_fd,
            parent_fd=parent_fd,
            destination_name=destination_name,
            operation_id=operation_id,
            lock_handle=lock_handle,
        )
        verified = _load_verified_recovery_context(
            capsule_fd,
            parent_fd=parent_fd,
            destination_name=destination_name,
            reserved_operation_id=operation_id,
        )
        operation = _strict_operation_id(
            operation_id,
            verified.history_context.capsule.run_id,
        )
        if type(lock_handle) is not LockHandle or lock_handle._closed:
            _fail("identity_mismatch")
        transaction = open_journal_transaction(
            capsule_fd,
            posix=lock_handle._posix,
            immutable_evidence_bytes=verified.immutable_evidence_bytes,
        )
        _validate_mutator_authority(transaction, lock_handle)
        _validate_verified_root_binding(capsule_fd, parent_fd, verified)
        initial_pair = _snapshot_transaction_pair(
            transaction,
            history_context=verified.history_context,
            tail_policy="report",
            reserved_operation_id=operation,
        )
        if initial_pair != verified.journal_pair:
            _fail("unstable_snapshot")
        session = _MutatorSessionV1(
            transaction,
            verified,
            operation,
            timestamp,
            lock_handle,
            parent_fd,
            initial_pair,
            _MUTATOR_SESSION_AUTHORITY,
        )
        transaction = None
        return session
    except RecoveryError:
        raise
    except UnsupportedFilesystemError:
        raise
    except (JournalError, HistoryError) as error:
        _fail(_recovery_code(error.code))
    except Exception:
        _fail("invalid_model")
    finally:
        if transaction is not None:
            with suppress(JournalError, OSError):
                transaction.close()


def _recovery_context_from_pair(
    session: _MutatorSessionV1,
    pair: JournalPairSnapshotV1,
) -> RecoveryContextV1:
    base = session.history_context
    return RecoveryContextV1(
        base.capsule,
        base.manifest,
        base.environment,
        base.plan,
        session.transaction._immutable_evidence_bytes,
        pair.history,
        pair.lifecycle,
        pair.events,
        pair.raw,
    )


def _truncate_session_tail(
    session: _MutatorSessionV1,
    truncation: TailTruncationV1,
) -> None:
    """Durably apply one locally derived suffix removal under verified authority."""

    if type(session) is not _MutatorSessionV1 or type(truncation) is not TailTruncationV1:
        _fail("identity_mismatch")
    _validate_mutator_authority(
        session.transaction,
        session.lock_handle,
    )
    _validate_verified_root_binding(
        session.transaction._capsule_fd,
        session.parent_fd,
        session.verified,
    )
    transaction = session.transaction
    ledger = truncation.ledger
    if ledger not in ("events", "raw"):
        raise JournalError("invalid_model", "events")
    cursor = transaction.events if ledger == "events" else transaction.raw
    if (
        type(truncation.original_byte_length) is not int
        or type(truncation.truncate_to) is not int
        or type(truncation.removed_byte_count) is not int
        or type(truncation.removed_sha256) is not str
        or truncation.original_byte_length != cursor.byte_length
        or truncation.truncate_to != cursor.last_lf_offset
        or truncation.removed_byte_count != cursor.tail_byte_count
        or truncation.removed_byte_count != truncation.original_byte_length - truncation.truncate_to
        or truncation.removed_byte_count <= 0
        or truncation.removed_sha256 != cursor.tail_sha256
    ):
        raise JournalError("identity_mismatch", ledger, cursor.row_count)
    descriptor = transaction._event_fd if ledger == "events" else transaction._raw_fd
    _rehash_transaction_pair(transaction)
    try:
        os.ftruncate(descriptor, truncation.truncate_to)
    except BaseException as error:
        transaction._poisoned = True
        if not isinstance(error, Exception):
            raise
        raise JournalError("io_error", ledger) from None
    try:
        transaction._posix.fsync(descriptor)
    except BaseException as error:
        transaction._poisoned = True
        if not isinstance(error, Exception):
            raise
        raise JournalError("io_error", ledger) from None
    try:
        after = _final_fstat(descriptor, ledger)
    except JournalError:
        transaction._poisoned = True
        raise
    if (after.st_dev, after.st_ino, after.st_mode) != (
        cursor.device,
        cursor.inode,
        cursor.mode,
    ) or after.st_size != truncation.truncate_to:
        transaction._poisoned = True
        raise JournalError("unstable_snapshot", ledger)
    whole_hash = transaction._committed_hashes[ledger].copy()
    transaction._whole_hashes[ledger] = whole_hash
    updated = JournalCursorV1(
        ledger=ledger,
        device=after.st_dev,
        inode=after.st_ino,
        mode=after.st_mode,
        byte_length=after.st_size,
        mtime_ns=after.st_mtime_ns,
        ctime_ns=after.st_ctime_ns,
        row_count=cursor.row_count,
        whole_sha256=whole_hash.hexdigest(),
        last_lf_offset=after.st_size,
        tail_byte_count=0,
        tail_sha256=None,
    )
    if ledger == "events":
        transaction._events = updated
    else:
        transaction._raw = updated


def _recovery_code(value: object) -> RecoveryCode:
    allowed: frozenset[str] = frozenset(
        {
            "io_error",
            "unsafe_path_type",
            "noncanonical_json",
            "invalid_model",
            "resource_limit",
            "hash_mismatch",
            "identity_mismatch",
            "history_mismatch",
            "retry_mismatch",
            "lifecycle_mismatch",
            "unstable_snapshot",
        }
    )
    return cast(RecoveryCode, value) if type(value) is str and value in allowed else "invalid_model"


def _disposition(context: RecoveryContextV1) -> RecoveryDisposition:
    state = context.lifecycle.state
    if state == "SEALING_INTERRUPTED":
        return "sealing_interrupted"
    if state == "AMBIGUOUS_INFLIGHT":
        return "ambiguous"
    if state == "AUTHENTICATION_STOPPED":
        return "authentication_stopped"
    if state == "GENERATION_COMPLETE":
        return "complete"
    if state in {"PREPARED", "INTERRUPTED"}:
        return "provider_ready"
    _fail("lifecycle_mismatch")


def plan_recovery_v1(
    *,
    context: RecoveryContextV1,
    event_snapshot: JournalSnapshotV1,
    raw_snapshot: JournalSnapshotV1,
    operation_id: UUID,
    occurred_at: datetime,
) -> RecoveryPlanV1:
    """Return the complete deterministic repair plan without mutating either ledger."""

    try:
        if type(context) is not RecoveryContextV1:
            raise TypeError
        context = RecoveryContextV1(
            context.capsule,
            context.manifest,
            context.environment,
            context.plan,
            context.immutable_evidence_bytes,
            context.history,
            context.lifecycle,
            context.event_snapshot,
            context.raw_snapshot,
        )
        events = _strict_snapshot(event_snapshot, "events")
        raw = _strict_snapshot(raw_snapshot, "raw")
        operation = _strict_operation_id(operation_id, context.capsule.run_id)
        timestamp = _strict_occurred_at(occurred_at)
    except RecoveryError:
        raise
    except Exception:
        _fail("invalid_model")

    if events != context.event_snapshot or raw != context.raw_snapshot:
        _fail("identity_mismatch")

    if (
        context.immutable_evidence_bytes + events.byte_length + raw.byte_length
        > RESOURCE_LIMITS_V1.mutable_capsule_bytes
    ):
        _fail("resource_limit")

    history = context.history
    terminal_marker_committed = (
        not history.recovery_requirements
        and history.open_attempt is None
        and context.lifecycle.state
        in {"AMBIGUOUS_INFLIGHT", "AUTHENTICATION_STOPPED", "GENERATION_COMPLETE"}
    )
    if (events.tail_byte_count or raw.tail_byte_count) and (
        history.seal_requested is not None or terminal_marker_committed
    ):
        _fail("lifecycle_mismatch")

    truncations: list[TailTruncationV1] = []
    open_start = history.open_attempt.start if history.open_attempt is not None else None
    snapshots: tuple[tuple[Ledger, JournalSnapshotV1], ...] = (
        ("events", events),
        ("raw", raw),
    )
    for ledger, snapshot in snapshots:
        if not snapshot.tail_byte_count:
            continue
        assert snapshot.tail_sha256 is not None
        related = (
            open_start.payload.attempt_id
            if (
                ledger == "raw"
                and open_start is not None
                and history.open_attempt is not None
                and history.open_attempt.raw is None
            )
            else None
        )
        truncations.append(
            TailTruncationV1(
                ledger,
                snapshot.byte_length,
                snapshot.byte_length - snapshot.tail_byte_count,
                snapshot.tail_byte_count,
                snapshot.tail_sha256,
                related,
            )
        )

    appended: list[EventV1] = []
    sequence = events.row_count
    for truncation in truncations:
        appended.append(
            make_event(
                sequence=sequence,
                run_id=context.capsule.run_id,
                occurred_at=timestamp,
                kind="tail_recovered",
                operation_id=operation,
                execution_session_id=None,
                payload={
                    "ledger": truncation.ledger,
                    "removed_byte_count": truncation.removed_byte_count,
                    "removed_sha256": truncation.removed_sha256,
                    "related_attempt_id": truncation.related_attempt_id,
                },
            )
        )
        sequence += 1

    synthesized_finish_id: str | None = None
    for requirement in history.recovery_requirements:
        if requirement.kind == "request_finished":
            event = make_event(
                sequence=sequence,
                run_id=context.capsule.run_id,
                occurred_at=timestamp,
                kind="request_finished",
                operation_id=operation,
                execution_session_id=None,
                payload={
                    "call_sequence": requirement.call_sequence,
                    "plan_item_id": requirement.plan_item_id,
                    "attempt_id": requirement.attempt_id,
                    "request_started_event_id": requirement.origin_request_started_event_id,
                    "raw_record_sha256": requirement.raw_record_sha256,
                    "recovered": True,
                },
            )
            synthesized_finish_id = event.event_id
        elif requirement.kind in {"authentication_stopped", "delivery_ambiguous"}:
            event = make_event(
                sequence=sequence,
                run_id=context.capsule.run_id,
                occurred_at=timestamp,
                kind=requirement.kind,
                operation_id=operation,
                execution_session_id=None,
                payload={
                    "plan_item_id": requirement.plan_item_id,
                    "attempt_id": requirement.attempt_id,
                    "origin_request_started_event_id": requirement.origin_request_started_event_id,
                    "recovered": True,
                },
            )
        else:
            origin_finish = requirement.origin_request_finished_event_id or synthesized_finish_id
            if origin_finish is None:
                _fail("history_mismatch")
            event = make_event(
                sequence=sequence,
                run_id=context.capsule.run_id,
                occurred_at=timestamp,
                kind="generation_completed",
                operation_id=operation,
                execution_session_id=None,
                payload={
                    "terminal_plan_item_count": len(context.plan),
                    "final_plan_ordinal": len(context.plan) - 1,
                    "origin_request_finished_event_id": origin_finish,
                    "recovered": True,
                },
            )
        appended.append(event)
        sequence += 1

    seal_reservation = (
        0
        if history.seal_requested is not None
        else RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1
    )
    # Budget each planned tail audit as one full row, regardless of the exact
    # suffix length it describes.  A crash during that audit can therefore replace
    # it with a differently sized audit without changing the capacity proof.  A
    # clean recovery additionally needs room for both a partial row and its replay
    # audit; each durable fact consumes one stage of that allowance.
    crash_row_bytes = RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1
    tail_audit_padding = sum(
        crash_row_bytes - len(event_jsonl(event))
        for event in appended
        if event.kind == "tail_recovered"
    )
    crash_stages = (
        max(
            0,
            2 - int(events.tail_byte_count > 0) - int(history.latest_event_recovered),
        )
        if appended
        else 0
    )
    crash_reservation = tail_audit_padding + crash_stages * crash_row_bytes
    post_bytes = (
        context.immutable_evidence_bytes
        + events.byte_length
        + raw.byte_length
        - sum(item.removed_byte_count for item in truncations)
        + sum(len(event_jsonl(event)) for event in appended)
    )
    if post_bytes + seal_reservation + crash_reservation > RESOURCE_LIMITS_V1.mutable_capsule_bytes:
        _fail("resource_limit")
    return RecoveryPlanV1(
        tuple(truncations),
        tuple(appended),
        _disposition(context),
        post_bytes,
        seal_reservation,
        crash_reservation,
    )


_PLAN_RECOVERY_V1_EXACT = plan_recovery_v1


def _local_session_pair_v1(session: object) -> JournalPairSnapshotV1:
    """Validate private in-memory authority without consulting the filesystem."""

    try:
        if type(session) is not _MutatorSessionV1:
            _fail("identity_mismatch")
        transaction = session.transaction
        lock_handle = session.lock_handle
        verified = session.verified
        pair = session._initial_pair
        if (
            session._authority is not _MUTATOR_SESSION_AUTHORITY
            or type(transaction) is not JournalTransaction
            or transaction._closed
            or transaction._poisoned
            or type(lock_handle) is not LockHandle
            or lock_handle._closed
            or lock_handle._exclusive is not True
            or lock_handle._posix is not transaction._posix
            or not _is_native_mutator_posix(lock_handle._posix)
            or type(verified) is not _VerifiedRecoveryProofV1
            or type(pair) is not JournalPairSnapshotV1
            or type(session.parent_fd) is not int
            or session.parent_fd < 0
            or transaction._immutable_evidence_bytes != verified.immutable_evidence_bytes
        ):
            _fail("identity_mismatch")
        rebound = _VerifiedRecoveryProofV1(
            verified.history_context,
            verified.journal_pair,
            verified.immutable_evidence_bytes,
            verified.root_identity,
            verified.parent_identity,
            verified.destination_name,
            verified.immutable_tree_sha256,
            verified._source,
        )
        operation_id = _strict_operation_id(
            session.operation_id,
            rebound.history_context.capsule.run_id,
        )
        _strict_occurred_at(session.occurred_at)
        if pair.reserved_operation_id != operation_id or pair != rebound.journal_pair:
            _fail("identity_mismatch")
        return pair
    except RecoveryError:
        raise
    except Exception:
        _fail("identity_mismatch")


def _plan_mutator_session_v1(session: _MutatorSessionV1) -> RecoveryPlanV1:
    """Purely derive one exact plan from the factory-retained initial pair."""

    try:
        pair = _local_session_pair_v1(session)
        context = _recovery_context_from_pair(session, pair)
        return plan_recovery_v1(
            context=context,
            event_snapshot=pair.events,
            raw_snapshot=pair.raw,
            operation_id=session.operation_id,
            occurred_at=session.occurred_at,
        )
    except RecoveryError:
        raise
    except (JournalError, HistoryError) as error:
        _fail(_recovery_code(error.code))
    except (OSError, RecursionError, TypeError, ValueError):
        _fail("io_error")


def _authorized_recovery_plan_v1(
    session: _MutatorSessionV1,
    pair: JournalPairSnapshotV1,
    plan: object,
) -> RecoveryPlanV1:
    if type(plan) is not RecoveryPlanV1:
        _fail("identity_mismatch")
    context = _recovery_context_from_pair(session, pair)
    expected = _PLAN_RECOVERY_V1_EXACT(
        context=context,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
        operation_id=session.operation_id,
        occurred_at=session.occurred_at,
    )
    if plan != expected:
        _fail("identity_mismatch")
    return plan


def _same_immutable_recovery_proof_v1(
    before: _VerifiedRecoveryProofV1,
    after: _VerifiedRecoveryProofV1,
) -> bool:
    return (
        after.history_context == before.history_context
        and after.immutable_evidence_bytes == before.immutable_evidence_bytes
        and after.root_identity == before.root_identity
        and after.parent_identity == before.parent_identity
        and after.destination_name == before.destination_name
        and after.immutable_tree_sha256 == before.immutable_tree_sha256
    )


def _revalidate_mutator_session_v1(
    session: _MutatorSessionV1,
    *,
    tail_policy: TailPolicy = "reject",
    reserved_operation_id: UUID | None = None,
) -> JournalPairSnapshotV1:
    """Revalidate immutable evidence and the current retained journals without mutation."""

    try:
        _local_session_pair_v1(session)
        if tail_policy not in ("report", "reject"):
            _fail("invalid_model")
        operation_id = (
            None
            if reserved_operation_id is None
            else _strict_operation_id(
                reserved_operation_id,
                session.history_context.capsule.run_id,
            )
        )
        _validate_mutator_authority(session.transaction, session.lock_handle)
        _validate_verified_root_binding(
            session.transaction._capsule_fd,
            session.parent_fd,
            session.verified,
        )
        fresh_verified = _load_verified_recovery_context(
            session.transaction._capsule_fd,
            parent_fd=session.parent_fd,
            destination_name=session.verified.destination_name,
            reserved_operation_id=operation_id,
        )
        if not _same_immutable_recovery_proof_v1(session.verified, fresh_verified):
            _fail("unstable_snapshot")
        pair = _snapshot_transaction_pair(
            session.transaction,
            history_context=session.history_context,
            tail_policy=tail_policy,
            reserved_operation_id=operation_id,
        )
        if pair != fresh_verified.journal_pair:
            _fail("unstable_snapshot")
        _validate_mutator_authority(session.transaction, session.lock_handle)
        _validate_verified_root_binding(
            session.transaction._capsule_fd,
            session.parent_fd,
            session.verified,
        )
        _joint_recheck_transaction_pair(session.transaction, pair)
        return pair
    except RecoveryError:
        raise
    except (JournalError, HistoryError) as error:
        _fail(_recovery_code(error.code))
    except (OSError, RecursionError, TypeError, ValueError):
        _fail("io_error")


def _apply_recovery_plan_v1(
    session: _MutatorSessionV1,
    plan: RecoveryPlanV1,
) -> AppliedRecoveryV1:
    """Recheck the factory snapshot, then durably apply exactly its authorized plan."""

    try:
        pair = _local_session_pair_v1(session)
        plan = _authorized_recovery_plan_v1(session, pair, plan)
        refreshed_pair = _revalidate_mutator_session_v1(
            session,
            tail_policy="report",
            reserved_operation_id=session.operation_id,
        )
        if refreshed_pair != pair:
            _fail("unstable_snapshot")
        _validate_mutator_authority(session.transaction, session.lock_handle)
        _validate_verified_root_binding(
            session.transaction._capsule_fd,
            session.parent_fd,
            session.verified,
        )
        _joint_recheck_transaction_pair(session.transaction, pair)
        _validate_mutator_authority(session.transaction, session.lock_handle)
        _validate_verified_root_binding(
            session.transaction._capsule_fd,
            session.parent_fd,
            session.verified,
        )
        _rehash_transaction_pair(session.transaction)
        for truncation in plan.truncations:
            _truncate_session_tail(session, truncation)
        if plan.append_events:
            _validate_mutator_authority(session.transaction, session.lock_handle)
            _validate_verified_root_binding(
                session.transaction._capsule_fd,
                session.parent_fd,
                session.verified,
            )
            _rehash_transaction_pair(session.transaction)
        for event in plan.append_events:
            _validate_mutator_authority(session.transaction, session.lock_handle)
            _validate_verified_root_binding(
                session.transaction._capsule_fd,
                session.parent_fd,
                session.verified,
            )
            append_event(session.transaction, event)
        post_pair = _snapshot_transaction_pair(
            session.transaction,
            history_context=session.history_context,
            tail_policy="reject",
            reserved_operation_id=None,
        )
        post_context = _recovery_context_from_pair(session, post_pair)
        disposition = _disposition(post_context)
        if (
            post_pair.events.tail_byte_count != 0
            or post_pair.raw.tail_byte_count != 0
            or post_context.history.recovery_requirements
            or disposition != plan.disposition
            or post_pair.events.row_count != pair.events.row_count + len(plan.append_events)
            or post_pair.raw.row_count != pair.raw.row_count
        ):
            _fail("lifecycle_mismatch")
        return AppliedRecoveryV1(
            disposition,
            len(plan.append_events),
            post_pair.events,
            post_pair.raw,
        )
    except RecoveryError:
        raise
    except (JournalError, HistoryError) as error:
        _fail(_recovery_code(error.code))
    except (OSError, RecursionError, TypeError, ValueError):
        _fail("io_error")


def _recover_journals_v1(session: _MutatorSessionV1) -> AppliedRecoveryV1:
    """Compose pure planning and exact application for private recovery callers."""

    return _apply_recovery_plan_v1(session, _plan_mutator_session_v1(session))


__all__ = [
    "AppliedRecoveryV1",
    "RecoveryContextV1",
    "RecoveryError",
    "RecoveryPlanV1",
    "TailTruncationV1",
    "plan_recovery_v1",
]
