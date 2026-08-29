"""Streaming cross-ledger grammar and lifecycle derivation."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Literal, NoReturn
from uuid import RFC_4122, UUID

from laconian_eval.capsule.attempts import (
    RawAttemptV2,
    derive_attempt_id,
    raw_attempt_bytes,
    raw_record_sha256,
)
from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.events import (
    AuthenticationStoppedEventV1,
    DeliveryAmbiguousEventV1,
    EventError,
    EventV1,
    ExecutionBlockedEventV1,
    ExecutionInterruptedEventV1,
    ExecutionStartedEventV1,
    GenerationCompletedEventV1,
    RequestFinishedEventV1,
    RequestStartedEventV1,
    SealRequestedEventV1,
    TailRecoveredEventV1,
    event_bytes,
)
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    EnvironmentV1,
    PlanRowV1,
    PreparedEventV1,
)
from laconian_eval.capsule.schema import LifecycleState, OperationalBlocker
from laconian_eval.capsule.verification_scratch import (
    ExactIdentityRegistry,
    IdentityCollision,
    NamespaceIdentity,
    ScratchError,
)

HistoryCode = Literal[
    "io_error",
    "hash_mismatch",
    "identity_mismatch",
    "history_mismatch",
    "retry_mismatch",
    "lifecycle_mismatch",
]
Ledger = Literal["events", "raw"]
RecoveryKind = Literal[
    "request_finished",
    "authentication_stopped",
    "delivery_ambiguous",
    "generation_completed",
]
RecoveryStep = Literal["tail_events", "tail_raw", "finish", "marker", "completion"]
IdentityKind = Literal["run", "operation", "session"]
CoreIdentityDeclaration = Callable[[UUID, IdentityKind, int], None]
SealIdentityDeclaration = Callable[[UUID, UUID, int], None]

_GENERIC_HISTORY_ERROR = "capsule history rejected"
_RESOLVED_REASONS = frozenset({"success", "retry_exhausted", "provider_rejected"})


class HistoryError(ContentFreeCapsuleError):
    """A content-free history failure with stable location metadata."""

    def __init__(self, code: HistoryCode, ledger: Ledger, row_index: int | None) -> None:
        self.code = code
        self.ledger = ledger
        self.row_index = row_index
        super().__init__(_GENERIC_HISTORY_ERROR)


@dataclass(frozen=True, slots=True)
class HistoryContextV1:
    capsule: CapsuleV1
    manifest: ResolvedManifestV2
    environment: EnvironmentV1
    plan: tuple[PlanRowV1, ...]

    def __post_init__(self) -> None:
        try:
            capsule = CapsuleV1.model_validate(
                CapsuleV1.model_dump(self.capsule, mode="python", round_trip=True, warnings=False)
            )
            manifest = ResolvedManifestV2.model_validate(
                ResolvedManifestV2.model_dump(
                    self.manifest, mode="python", round_trip=True, warnings=False
                )
            )
            environment = EnvironmentV1.model_validate(
                EnvironmentV1.model_dump(
                    self.environment, mode="python", round_trip=True, warnings=False
                )
            )
            plan = tuple(
                PlanRowV1.model_validate(
                    PlanRowV1.model_dump(row, mode="python", round_trip=True, warnings=False)
                )
                for row in self.plan
            )
        except Exception:
            raise HistoryError("identity_mismatch", "events", None) from None
        object.__setattr__(self, "capsule", capsule)
        object.__setattr__(self, "manifest", manifest)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "plan", plan)


@dataclass(frozen=True, slots=True)
class RawCommitProjectionV1:
    call_sequence: int
    plan_item_id: str
    attempt_id: str
    attempt: int
    terminal: bool
    terminal_reason: str | None
    backoff_ms: int | None
    raw_record_sha256: str
    response_model: str | None


@dataclass(frozen=True, slots=True)
class AttemptCommitV1:
    start: RequestStartedEventV1
    raw: RawCommitProjectionV1 | None
    finish: RequestFinishedEventV1 | None


@dataclass(frozen=True, slots=True)
class RecoveryRequirementV1:
    kind: RecoveryKind
    call_sequence: int
    plan_item_id: str | None = None
    attempt_id: str | None = None
    origin_request_started_event_id: str | None = None
    raw_record_sha256: str | None = None
    origin_request_finished_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidatedHistoryV1:
    resolved_plan_item_ids: tuple[str, ...]
    missing_plan_item_ids: tuple[str, ...]
    returned_models: tuple[str, ...]
    next_unresolved_plan_ordinal: int | None
    next_call_sequence: int
    next_attempt_number: int | None
    open_attempt: AttemptCommitV1 | None
    recovery_requirements: tuple[RecoveryRequirementV1, ...]
    request_history_present: bool
    execution_history_present: bool
    latest_no_call_blocked: bool
    latest_event_recovered: bool
    has_ambiguous_delivery: bool
    has_authentication_stop: bool
    seal_requested: SealRequestedEventV1 | None


@dataclass(frozen=True, slots=True)
class LifecycleProjectionV1:
    state: LifecycleState
    missing_plan_item_ids: tuple[str, ...]
    operational_blocker_codes: tuple[OperationalBlocker, ...]


def _fail(
    code: HistoryCode = "history_mismatch",
    ledger: Ledger = "events",
    row_index: int | None = None,
) -> NoReturn:
    raise HistoryError(code, ledger, row_index)


def _advance_recovery_phase(current: int, step: RecoveryStep, row_index: int) -> int:
    if step == "tail_events":
        if current != 0:
            _fail("history_mismatch", "events", row_index)
        return 1
    if step == "tail_raw":
        if current not in (0, 1):
            _fail("history_mismatch", "events", row_index)
        return 2
    if step == "finish":
        if current > 2:
            _fail("history_mismatch", "events", row_index)
        return 3
    if step == "marker":
        if current > 3:
            _fail("history_mismatch", "events", row_index)
        return 4
    if current > 3:
        _fail("history_mismatch", "events", row_index)
    return 5


def _python_major_minor(value: str, row_index: int) -> tuple[int, int]:
    try:
        head = value.split(maxsplit=1)[0]
        major, minor, *_rest = head.split(".")
        return int(major), int(minor)
    except Exception:
        _fail("identity_mismatch", "events", row_index)


def _validate_session(
    event: ExecutionStartedEventV1,
    environment: EnvironmentV1,
    row_index: int,
) -> None:
    session = event.payload.session_environment
    runtime = environment.runtime
    provider = environment.provider
    if (
        session.package_version != environment.package_version
        or session.runner_source_sha256 != environment.runner_source_sha256
        or session.runtime_fingerprint_sha256 != runtime.runtime_fingerprint_sha256
        or session.python_implementation != runtime.python_implementation
        or _python_major_minor(session.python_version, row_index)
        != _python_major_minor(runtime.python_version, row_index)
        or session.adapter_source_sha256 != provider.adapter_source_sha256
        or session.sdk_distribution != provider.sdk_distribution
        or session.sdk_version != provider.sdk_version
    ):
        _fail("identity_mismatch", "events", row_index)


def _validate_prepared(event: PreparedEventV1, context: HistoryContextV1) -> None:
    capsule = context.capsule
    expected = (
        capsule.manifest_sha256,
        capsule.input_index_sha256,
        capsule.case_index_sha256,
        capsule.plan_sha256,
        capsule.environment_sha256,
        capsule.runner_source_sha256,
    )
    actual = (
        event.payload.manifest_sha256,
        event.payload.input_index_sha256,
        event.payload.case_index_sha256,
        event.payload.plan_sha256,
        event.payload.environment_sha256,
        event.payload.runner_source_sha256,
    )
    if actual != expected:
        _fail("hash_mismatch", "events", 0)
    if event.sequence != 0:
        _fail("history_mismatch", "events", 0)
    if (
        event.run_id != capsule.run_id
        or event.occurred_at != capsule.created_at
        or event.operation_id == capsule.run_id
    ):
        _fail("identity_mismatch", "events", 0)


def _validate_event_ledger_v1(
    *,
    history_context: HistoryContextV1,
    events: Iterable[EventV1],
    declare_core_identity: CoreIdentityDeclaration | None = None,
    declare_seal_identity: SealIdentityDeclaration | None = None,
) -> None:
    """Validate the event-only grammar in one bounded-memory streaming pass.

    Cross-ledger facts remain the responsibility of :func:`validate_history_v1`.  The optional
    declaration callbacks are the integration boundary for an exact external UUID registry;
    this validator deliberately retains no history-sized identity set of its own.
    """

    context = history_context
    plan = context.plan
    plan_by_id = {row.plan_item_id: row for row in plan}
    if not plan:
        _fail("identity_mismatch", "events", None)

    try:
        event_iterator = iter(events)
    except ContentFreeCapsuleError:
        raise
    except Exception:
        _fail("history_mismatch", "events", 0)
    try:
        first = next(event_iterator)
    except StopIteration:
        _fail("history_mismatch", "events", 0)
    except ContentFreeCapsuleError:
        raise
    except Exception:
        _fail("history_mismatch", "events", 0)
    try:
        event_bytes(first)
    except EventError:
        _fail("history_mismatch", "events", 0)
    if type(first) is not PreparedEventV1:
        _fail("history_mismatch", "events", 0)
    _validate_prepared(first, context)
    if declare_core_identity is not None:
        declare_core_identity(first.run_id, "run", 0)
        declare_core_identity(first.operation_id, "operation", 0)

    active_epoch: tuple[UUID, UUID] | None = None
    active_resume_ordinal: int | None = None
    epoch_had_call = False
    open_start: RequestStartedEventV1 | None = None
    last_start: RequestStartedEventV1 | None = None
    last_finish: RequestFinishedEventV1 | None = None
    recovery_operation: UUID | None = None
    recovery_phase = 0
    terminal_suffix = False
    seal_seen = False
    expected_call = 0

    def declare_new_operation(operation_id: UUID, row_index: int) -> None:
        if declare_core_identity is not None:
            declare_core_identity(operation_id, "operation", row_index)

    def declare_new_session(session_id: UUID, row_index: int) -> None:
        if declare_core_identity is not None:
            declare_core_identity(session_id, "session", row_index)

    def accept_recovery_operation(
        operation_id: UUID,
        row_index: int,
        step: RecoveryStep,
    ) -> None:
        nonlocal recovery_operation, recovery_phase
        if operation_id != recovery_operation:
            declare_new_operation(operation_id, row_index)
            recovery_operation = operation_id
            recovery_phase = 0
        recovery_phase = _advance_recovery_phase(recovery_phase, step, row_index)

    def plan_row(plan_item_id: str) -> PlanRowV1 | None:
        return plan_by_id.get(plan_item_id)

    def event_rows() -> Iterator[tuple[int, EventV1]]:
        row_index = 1
        while True:
            try:
                event = next(event_iterator)
            except StopIteration:
                return
            except ContentFreeCapsuleError:
                raise
            except Exception:
                _fail("history_mismatch", "events", row_index)
            yield row_index, event
            row_index += 1

    for row_index, event in event_rows():
        try:
            event_bytes(event)
        except EventError:
            _fail("history_mismatch", "events", row_index)
        if event.sequence != row_index:
            _fail("history_mismatch", "events", row_index)
        if event.run_id != context.capsule.run_id or event.operation_id == event.run_id:
            _fail("identity_mismatch", "events", row_index)
        if event.execution_session_id is not None and (
            event.execution_session_id == event.run_id
            or event.execution_session_id == event.operation_id
        ):
            _fail("identity_mismatch", "events", row_index)
        if seal_seen:
            _fail("lifecycle_mismatch", "events", row_index)
        if terminal_suffix and not isinstance(event, SealRequestedEventV1):
            _fail("lifecycle_mismatch", "events", row_index)
        if type(event) is PreparedEventV1:
            _fail("history_mismatch", "events", row_index)

        if isinstance(event, ExecutionStartedEventV1):
            if open_start is not None:
                _fail("lifecycle_mismatch", "events", row_index)
            if event.payload.resume_from_plan_ordinal >= len(plan):
                _fail("identity_mismatch", "events", row_index)
            if expected_call == 0 and event.payload.resume_from_plan_ordinal != 0:
                _fail("identity_mismatch", "events", row_index)
            if event.operation_id != recovery_operation:
                declare_new_operation(event.operation_id, row_index)
            declare_new_session(event.execution_session_id, row_index)
            recovery_operation = None
            recovery_phase = 0
            _validate_session(event, context.environment, row_index)
            active_epoch = (event.operation_id, event.execution_session_id)
            active_resume_ordinal = event.payload.resume_from_plan_ordinal
            epoch_had_call = False
            last_start = None
            last_finish = None
            continue

        if isinstance(event, TailRecoveredEventV1):
            allowed_related = (
                {None, open_start.payload.attempt_id}
                if event.payload.ledger == "raw" and open_start is not None
                else {None}
            )
            if event.payload.related_attempt_id not in allowed_related:
                _fail("identity_mismatch", "events", row_index)
            accept_recovery_operation(
                event.operation_id,
                row_index,
                "tail_events" if event.payload.ledger == "events" else "tail_raw",
            )
            active_epoch = None
            active_resume_ordinal = None
            continue

        if isinstance(event, SealRequestedEventV1):
            if event.operation_id != recovery_operation:
                declare_new_operation(event.operation_id, row_index)
            if declare_seal_identity is not None:
                declare_seal_identity(
                    event.payload.seal_transaction_id,
                    event.operation_id,
                    row_index,
                )
            recovery_operation = None
            recovery_phase = 0
            active_epoch = None
            active_resume_ordinal = None
            seal_seen = True
            continue

        normal_session = event.execution_session_id is not None
        if not normal_session:
            active_epoch = None
            active_resume_ordinal = None
        if normal_session and (
            active_epoch is None or (event.operation_id, event.execution_session_id) != active_epoch
        ):
            _fail("history_mismatch", "events", row_index)

        if isinstance(event, ExecutionBlockedEventV1):
            if epoch_had_call or open_start is not None:
                _fail("history_mismatch", "events", row_index)
            active_epoch = None
            active_resume_ordinal = None
            last_start = None
            last_finish = None
            continue

        if isinstance(event, ExecutionInterruptedEventV1):
            if open_start is not None:
                _fail("lifecycle_mismatch", "events", row_index)
            if (
                not epoch_had_call
                and (
                    active_resume_ordinal is None
                    or event.payload.next_plan_item_id != plan[active_resume_ordinal].plan_item_id
                )
            ) or plan_row(event.payload.next_plan_item_id) is None:
                _fail("identity_mismatch", "events", row_index)
            active_epoch = None
            active_resume_ordinal = None
            last_start = None
            last_finish = None
            continue

        if isinstance(event, RequestStartedEventV1):
            if active_epoch is None or open_start is not None:
                _fail("history_mismatch", "events", row_index)
            payload = event.payload
            if payload.call_sequence != expected_call:
                _fail("history_mismatch", "events", row_index)
            if payload.attempt > min(6, 1 + context.manifest.retry.max_transient_retries):
                _fail("retry_mismatch", "events", row_index)
            if payload.attempt_id != derive_attempt_id(
                context.capsule.run_id,
                payload.plan_item_id,
                payload.attempt,
            ):
                _fail("identity_mismatch", "events", row_index)
            target = plan_row(payload.plan_item_id)
            if not epoch_had_call and (
                active_resume_ordinal is None
                or payload.plan_item_id != plan[active_resume_ordinal].plan_item_id
            ):
                _fail("identity_mismatch", "events", row_index)
            if target is None or (
                payload.provider != context.manifest.provider.kind
                or payload.model != context.manifest.provider.model
                or payload.request_config_sha256 != target.request_config_sha256
                or payload.prompt_sha256 != target.prompt_sha256
                or payload.case_definition_sha256 != target.case_definition_sha256
                or payload.instruction_sha256 != target.instruction_sha256
            ):
                _fail("identity_mismatch", "events", row_index)
            epoch_had_call = True
            open_start = event
            last_start = event
            last_finish = None
            expected_call += 1
            continue

        if isinstance(event, RequestFinishedEventV1):
            if open_start is None:
                _fail("history_mismatch", "events", row_index)
            finish_payload = event.payload
            start_payload = open_start.payload
            if (
                finish_payload.call_sequence != start_payload.call_sequence
                or finish_payload.plan_item_id != start_payload.plan_item_id
                or finish_payload.attempt_id != start_payload.attempt_id
                or finish_payload.request_started_event_id != open_start.event_id
            ):
                _fail("identity_mismatch", "events", row_index)
            if not finish_payload.recovered and (
                event.operation_id != open_start.operation_id
                or event.execution_session_id != open_start.execution_session_id
            ):
                _fail("history_mismatch", "events", row_index)
            if finish_payload.recovered:
                accept_recovery_operation(event.operation_id, row_index, "finish")
            last_start = open_start
            last_finish = event
            open_start = None
            continue

        if isinstance(event, (AuthenticationStoppedEventV1, DeliveryAmbiguousEventV1)):
            if open_start is not None or last_start is None or last_finish is None:
                _fail("lifecycle_mismatch", "events", row_index)
            if (
                event.payload.plan_item_id != last_start.payload.plan_item_id
                or event.payload.attempt_id != last_start.payload.attempt_id
                or event.payload.origin_request_started_event_id != last_start.event_id
            ):
                _fail("identity_mismatch", "events", row_index)
            if not event.payload.recovered and (
                event.operation_id != last_finish.operation_id
                or event.execution_session_id != last_finish.execution_session_id
            ):
                _fail("history_mismatch", "events", row_index)
            if event.payload.recovered:
                accept_recovery_operation(event.operation_id, row_index, "marker")
            terminal_suffix = True
            active_epoch = None
            active_resume_ordinal = None
            continue

        if isinstance(event, GenerationCompletedEventV1):
            if (
                open_start is not None
                or last_finish is None
                or event.payload.terminal_plan_item_count != len(plan)
                or event.payload.final_plan_ordinal != len(plan) - 1
            ):
                _fail("lifecycle_mismatch", "events", row_index)
            if event.payload.origin_request_finished_event_id != last_finish.event_id:
                _fail("identity_mismatch", "events", row_index)
            if not event.payload.recovered and (
                event.operation_id != last_finish.operation_id
                or event.execution_session_id != last_finish.execution_session_id
            ):
                _fail("history_mismatch", "events", row_index)
            if event.payload.recovered:
                accept_recovery_operation(event.operation_id, row_index, "completion")
            terminal_suffix = True
            active_epoch = None
            active_resume_ordinal = None
            continue

        _fail("history_mismatch", "events", row_index)


def validate_event_ledger_v1(
    *,
    history_context: HistoryContextV1,
    events: Iterable[EventV1],
    declare_core_identity: CoreIdentityDeclaration | None = None,
    declare_seal_identity: SealIdentityDeclaration | None = None,
    scratch_forbidden_namespace_identities: frozenset[NamespaceIdentity] | None = None,
    reserved_operation_id: UUID | None = None,
) -> None:
    """Validate event-only grammar and exact identities with bounded resident memory."""

    if (declare_core_identity is None) != (declare_seal_identity is None):
        _fail("io_error", "events", None)
    if reserved_operation_id is not None and (
        type(reserved_operation_id) is not UUID
        or reserved_operation_id.version != 4
        or reserved_operation_id.variant != RFC_4122
    ):
        _fail("identity_mismatch", "events", None)
    if declare_core_identity is None:
        try:
            with ExactIdentityRegistry(
                forbidden_namespace_identities=scratch_forbidden_namespace_identities
            ) as identities:
                _validate_event_ledger_v1(
                    history_context=history_context,
                    events=events,
                    declare_core_identity=identities.declare_core,
                    declare_seal_identity=identities.declare_seal,
                )
                if reserved_operation_id is not None:
                    identities.declare_core(reserved_operation_id, "operation", 0)
            return
        except IdentityCollision as error:
            _fail("identity_mismatch", "events", error.row_index)
        except ScratchError:
            _fail("io_error", "events", None)
    try:
        _validate_event_ledger_v1(
            history_context=history_context,
            events=events,
            declare_core_identity=declare_core_identity,
            declare_seal_identity=declare_seal_identity,
        )
        if reserved_operation_id is not None:
            assert declare_core_identity is not None
            declare_core_identity(reserved_operation_id, "operation", 0)
    except IdentityCollision as error:
        _fail("identity_mismatch", "events", error.row_index)
    except ScratchError:
        _fail("io_error", "events", None)


def _strict_raw(value: object, row_index: int) -> RawAttemptV2:
    try:
        raw_attempt_bytes(value)  # type: ignore[arg-type]
        payload = RawAttemptV2.model_dump(
            value,  # type: ignore[arg-type]
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return RawAttemptV2.model_validate(payload)
    except Exception:
        _fail("identity_mismatch", "raw", row_index)


def _validate_raw_binding(
    raw: RawAttemptV2,
    start: RequestStartedEventV1,
    plan: PlanRowV1,
    context: HistoryContextV1,
    row_index: int,
) -> RawCommitProjectionV1:
    manifest = context.manifest
    capsule = context.capsule
    start_payload = start.payload
    if (
        raw.run_id != capsule.run_id
        or raw.runner_version != capsule.runner_version
        or raw.manifest_sha256 != capsule.manifest_sha256
    ):
        _fail("identity_mismatch", "raw", row_index)
    plan_values = (
        raw.plan_item_id,
        raw.scenario_uid,
        raw.case_uid,
        raw.case_id,
        raw.locale,
        raw.case_definition_sha256,
        raw.arm,
        raw.repetition,
        raw.prompt_sha256,
        raw.instruction_sha256,
        raw.request_config_sha256,
    )
    expected_plan_values = (
        plan.plan_item_id,
        plan.scenario_uid,
        plan.case_uid,
        plan.case_id,
        plan.locale,
        plan.case_definition_sha256,
        plan.arm,
        plan.repetition,
        plan.prompt_sha256,
        plan.instruction_sha256,
        plan.request_config_sha256,
    )
    if plan_values != expected_plan_values:
        _fail("identity_mismatch", "raw", row_index)
    if raw.call_sequence != start_payload.call_sequence:
        _fail("history_mismatch", "raw", row_index)
    if (
        raw.attempt_id != start_payload.attempt_id
        or raw.attempt != start_payload.attempt
        or raw.retry_of_attempt != start_payload.retry_of_attempt
    ):
        _fail("retry_mismatch", "raw", row_index)
    if (
        raw.plan_item_id != start_payload.plan_item_id
        or raw.request_config_sha256 != start_payload.request_config_sha256
        or raw.prompt_sha256 != start_payload.prompt_sha256
        or raw.case_definition_sha256 != start_payload.case_definition_sha256
        or raw.instruction_sha256 != start_payload.instruction_sha256
        or raw.provider != start_payload.provider
        or raw.model != start_payload.model
    ):
        _fail("identity_mismatch", "raw", row_index)
    if raw.provider != manifest.provider.kind or raw.model != manifest.provider.model:
        _fail("identity_mismatch", "raw", row_index)
    return RawCommitProjectionV1(
        call_sequence=raw.call_sequence,
        plan_item_id=raw.plan_item_id,
        attempt_id=raw.attempt_id,
        attempt=raw.attempt,
        terminal=raw.terminal,
        terminal_reason=raw.terminal_reason,
        backoff_ms=raw.backoff_ms,
        raw_record_sha256=raw_record_sha256(raw),
        response_model=raw.response_model if raw.terminal_reason == "success" else None,
    )


def _validate_history_v1(
    *,
    capsule: CapsuleV1,
    manifest: ResolvedManifestV2,
    environment: EnvironmentV1,
    plan: tuple[PlanRowV1, ...],
    events: Iterable[EventV1],
    raw_attempts: Iterable[RawAttemptV2],
    identity_registry: ExactIdentityRegistry,
) -> ValidatedHistoryV1:
    """Validate committed event/raw iterators and retain only compact lifecycle facts."""

    context = HistoryContextV1(capsule, manifest, environment, plan)
    if not context.plan:
        _fail("identity_mismatch", "events", None)

    try:
        event_iterator = iter(events)
    except ContentFreeCapsuleError:
        raise
    except Exception:
        _fail("history_mismatch", "events", 0)
    try:
        raw_iterator = iter(raw_attempts)
    except ContentFreeCapsuleError:
        raise
    except Exception:
        _fail("history_mismatch", "raw", 0)
    try:
        first = next(event_iterator)
    except StopIteration:
        _fail("history_mismatch", "events", 0)
    except ContentFreeCapsuleError:
        raise
    except Exception:
        _fail("history_mismatch", "events", 0)
    try:
        event_bytes(first)
    except EventError:
        _fail("history_mismatch", "events", 0)
    if type(first) is not PreparedEventV1:
        _fail("history_mismatch", "events", 0)
    _validate_prepared(first, context)
    identity_registry.declare_core(first.run_id, "run", 0)
    identity_registry.declare_core(first.operation_id, "operation", 0)

    active_epoch: tuple[UUID, UUID] | None = None
    epoch_had_call = False
    open_commit: AttemptCommitV1 | None = None
    last_projection: RawCommitProjectionV1 | None = None
    last_finish: RequestFinishedEventV1 | None = None
    pending_marker: Literal["authentication_stopped", "delivery_ambiguous"] | None = None
    marker_seen = False
    completion_seen = False
    terminal_suffix = False
    recovery_operation: UUID | None = None
    recovery_phase = 0
    seal_requested: SealRequestedEventV1 | None = None
    execution_history = False
    request_history = False
    latest_no_call_blocked = False
    latest_event_recovered = False
    has_ambiguity = False
    has_auth = False
    current_ordinal = 0
    expected_attempt = 1
    expected_call = 0
    resolved: list[str] = []
    returned_models: list[str] = []
    raw_lookahead: RawAttemptV2 | None = None
    raw_index = 0

    def peek_raw() -> RawAttemptV2 | None:
        nonlocal raw_lookahead, raw_index
        if raw_lookahead is None:
            try:
                candidate = next(raw_iterator)
            except StopIteration:
                return None
            except ContentFreeCapsuleError:
                raise
            except Exception:
                _fail("history_mismatch", "raw", raw_index)
            raw_lookahead = _strict_raw(candidate, raw_index)
        return raw_lookahead

    def take_raw() -> RawAttemptV2 | None:
        nonlocal raw_lookahead, raw_index
        value = peek_raw()
        if value is not None:
            raw_lookahead = None
            raw_index += 1
        return value

    def accept_recovery_operation(
        operation_id: UUID,
        row_index: int,
        step: RecoveryStep,
    ) -> None:
        nonlocal recovery_operation, recovery_phase
        if operation_id != recovery_operation:
            identity_registry.declare_core(operation_id, "operation", row_index)
            recovery_operation = operation_id
            recovery_phase = 0
        recovery_phase = _advance_recovery_phase(recovery_phase, step, row_index)

    def event_rows() -> Iterator[tuple[int, EventV1]]:
        row_index = 1
        while True:
            try:
                event = next(event_iterator)
            except StopIteration:
                return
            except ContentFreeCapsuleError:
                raise
            except Exception:
                _fail("history_mismatch", "events", row_index)
            yield row_index, event
            row_index += 1

    for row_index, event in event_rows():
        try:
            event_bytes(event)
        except EventError:
            _fail("history_mismatch", "events", row_index)
        if event.sequence != row_index:
            _fail("history_mismatch", "events", row_index)
        if event.run_id != context.capsule.run_id or event.operation_id == event.run_id:
            _fail("identity_mismatch", "events", row_index)
        if event.execution_session_id is not None and (
            event.execution_session_id == event.run_id
            or event.execution_session_id == event.operation_id
        ):
            _fail("identity_mismatch", "events", row_index)
        if seal_requested is not None:
            _fail("lifecycle_mismatch", "events", row_index)
        if terminal_suffix and not isinstance(event, SealRequestedEventV1):
            _fail("lifecycle_mismatch", "events", row_index)
        if type(event) is PreparedEventV1:
            _fail("history_mismatch", "events", row_index)

        latest_event_recovered = isinstance(event, TailRecoveredEventV1) or (
            isinstance(
                event,
                (
                    RequestFinishedEventV1,
                    AuthenticationStoppedEventV1,
                    DeliveryAmbiguousEventV1,
                    GenerationCompletedEventV1,
                ),
            )
            and event.payload.recovered
        )

        if isinstance(event, ExecutionStartedEventV1):
            execution_history = True
            latest_no_call_blocked = False
            if open_commit is not None or pending_marker is not None or completion_seen:
                _fail("lifecycle_mismatch", "events", row_index)
            if current_ordinal == len(plan):
                _fail("lifecycle_mismatch", "events", row_index)
            if active_epoch is not None:
                active_epoch = None
            session_id = event.execution_session_id
            if event.operation_id != recovery_operation:
                identity_registry.declare_core(event.operation_id, "operation", row_index)
            identity_registry.declare_core(session_id, "session", row_index)
            recovery_operation = None
            recovery_phase = 0
            _validate_session(event, context.environment, row_index)
            if event.payload.resume_from_plan_ordinal != current_ordinal:
                _fail("identity_mismatch", "events", row_index)
            active_epoch = (event.operation_id, session_id)
            epoch_had_call = False
            continue

        if isinstance(event, TailRecoveredEventV1):
            expected_related = (
                open_commit.start.payload.attempt_id
                if (
                    event.payload.ledger == "raw"
                    and open_commit is not None
                    and open_commit.raw is None
                )
                else None
            )
            if event.payload.related_attempt_id != expected_related:
                _fail("identity_mismatch", "events", row_index)
            accept_recovery_operation(
                event.operation_id,
                row_index,
                "tail_events" if event.payload.ledger == "events" else "tail_raw",
            )
            active_epoch = None
            continue

        if isinstance(event, SealRequestedEventV1):
            if active_epoch is not None:
                active_epoch = None
            if event.operation_id != recovery_operation:
                identity_registry.declare_core(event.operation_id, "operation", row_index)
            identity_registry.declare_seal(
                event.payload.seal_transaction_id,
                event.operation_id,
                row_index,
            )
            recovery_operation = None
            recovery_phase = 0
            seal_requested = event
            continue

        normal_session = event.execution_session_id is not None
        if not normal_session:
            active_epoch = None
        if normal_session and (
            active_epoch is None
            or (
                event.operation_id,
                event.execution_session_id,
            )
            != active_epoch
        ):
            _fail("history_mismatch", "events", row_index)

        if isinstance(event, ExecutionBlockedEventV1):
            if epoch_had_call or open_commit is not None:
                _fail("history_mismatch", "events", row_index)
            latest_no_call_blocked = not request_history
            active_epoch = None
            continue

        if isinstance(event, ExecutionInterruptedEventV1):
            if (
                open_commit is not None
                or pending_marker is not None
                or current_ordinal >= len(plan)
            ):
                _fail("lifecycle_mismatch", "events", row_index)
            if event.payload.next_plan_item_id != plan[current_ordinal].plan_item_id:
                _fail("identity_mismatch", "events", row_index)
            active_epoch = None
            continue

        if isinstance(event, RequestStartedEventV1):
            request_history = True
            epoch_had_call = True
            latest_no_call_blocked = False
            if active_epoch is None or open_commit is not None or pending_marker is not None:
                _fail("history_mismatch", "events", row_index)
            if current_ordinal >= len(plan):
                _fail("identity_mismatch", "events", row_index)
            target = plan[current_ordinal]
            payload = event.payload
            if payload.call_sequence != expected_call:
                _fail("history_mismatch", "events", row_index)
            if payload.attempt != expected_attempt:
                _fail("retry_mismatch", "events", row_index)
            if payload.attempt_id != derive_attempt_id(
                context.capsule.run_id, target.plan_item_id, payload.attempt
            ):
                _fail("identity_mismatch", "events", row_index)
            if (
                payload.plan_item_id != target.plan_item_id
                or payload.provider != manifest.provider.kind
                or payload.model != manifest.provider.model
                or payload.request_config_sha256 != target.request_config_sha256
                or payload.prompt_sha256 != target.prompt_sha256
                or payload.case_definition_sha256 != target.case_definition_sha256
                or payload.instruction_sha256 != target.instruction_sha256
            ):
                _fail("identity_mismatch", "events", row_index)
            if payload.attempt > 1 + manifest.retry.max_transient_retries:
                _fail("retry_mismatch", "events", row_index)
            candidate = peek_raw()
            projection = None
            if candidate is not None:
                if candidate.call_sequence < expected_call:
                    _fail("history_mismatch", "raw", raw_index)
                if candidate.call_sequence == expected_call:
                    projection = _validate_raw_binding(
                        take_raw(),  # type: ignore[arg-type]
                        event,
                        target,
                        context,
                        raw_index - 1,
                    )
                    if not projection.terminal:
                        if projection.attempt == 1 + manifest.retry.max_transient_retries:
                            _fail("retry_mismatch", "raw", raw_index - 1)
                        expected_attempt += 1
                    elif projection.terminal_reason in _RESOLVED_REASONS:
                        if (
                            projection.terminal_reason == "retry_exhausted"
                            and projection.attempt != 1 + manifest.retry.max_transient_retries
                        ):
                            _fail("retry_mismatch", "raw", raw_index - 1)
                        resolved.append(projection.plan_item_id)
                        current_ordinal += 1
                        expected_attempt = 1
                    elif projection.terminal_reason == "authentication_stopped":
                        has_auth = True
                        pending_marker = "authentication_stopped"
                    elif projection.terminal_reason == "ambiguous_delivery":
                        has_ambiguity = True
                        pending_marker = "delivery_ambiguous"
                    if (
                        projection.response_model is not None
                        and projection.response_model not in returned_models
                        and len(returned_models) < 2
                    ):
                        returned_models.append(projection.response_model)
            open_commit = AttemptCommitV1(event, projection, None)
            expected_call += 1
            continue

        if isinstance(event, RequestFinishedEventV1):
            if open_commit is None or open_commit.raw is None:
                _fail("history_mismatch", "events", row_index)
            start = open_commit.start
            projection = open_commit.raw
            finish_payload = event.payload
            if (
                finish_payload.call_sequence != projection.call_sequence
                or finish_payload.plan_item_id != projection.plan_item_id
                or finish_payload.attempt_id != projection.attempt_id
                or finish_payload.request_started_event_id != start.event_id
            ):
                _fail("identity_mismatch", "events", row_index)
            if finish_payload.raw_record_sha256 != projection.raw_record_sha256:
                _fail("hash_mismatch", "events", row_index)
            if not finish_payload.recovered and (
                event.operation_id != start.operation_id
                or event.execution_session_id != start.execution_session_id
            ):
                _fail("history_mismatch", "events", row_index)
            if finish_payload.recovered:
                accept_recovery_operation(event.operation_id, row_index, "finish")
            open_commit = None
            last_projection = projection
            last_finish = event
            continue

        if isinstance(event, (AuthenticationStoppedEventV1, DeliveryAmbiguousEventV1)):
            expected_kind = (
                "authentication_stopped"
                if isinstance(event, AuthenticationStoppedEventV1)
                else "delivery_ambiguous"
            )
            if (
                open_commit is not None
                or pending_marker != expected_kind
                or last_projection is None
                or last_finish is None
            ):
                _fail("lifecycle_mismatch", "events", row_index)
            if (
                event.payload.plan_item_id != last_projection.plan_item_id
                or event.payload.attempt_id != last_projection.attempt_id
                or event.payload.origin_request_started_event_id
                != last_finish.payload.request_started_event_id
            ):
                _fail("identity_mismatch", "events", row_index)
            if not event.payload.recovered and (
                event.operation_id != last_finish.operation_id
                or event.execution_session_id != last_finish.execution_session_id
            ):
                _fail("history_mismatch", "events", row_index)
            if event.payload.recovered:
                accept_recovery_operation(event.operation_id, row_index, "marker")
            pending_marker = None
            marker_seen = True
            terminal_suffix = True
            active_epoch = None
            continue

        if isinstance(event, GenerationCompletedEventV1):
            if (
                open_commit is not None
                or pending_marker is not None
                or current_ordinal != len(plan)
                or last_finish is None
                or event.payload.terminal_plan_item_count != len(plan)
                or event.payload.final_plan_ordinal != len(plan) - 1
            ):
                _fail("lifecycle_mismatch", "events", row_index)
            if event.payload.origin_request_finished_event_id != last_finish.event_id:
                _fail("identity_mismatch", "events", row_index)
            if not event.payload.recovered and (
                event.operation_id != last_finish.operation_id
                or event.execution_session_id != last_finish.execution_session_id
            ):
                _fail("history_mismatch", "events", row_index)
            if event.payload.recovered:
                accept_recovery_operation(event.operation_id, row_index, "completion")
            completion_seen = True
            terminal_suffix = True
            active_epoch = None
            continue

        _fail("history_mismatch", "events", row_index)

    if peek_raw() is not None:
        _fail("history_mismatch", "raw", raw_index)

    requirements: list[RecoveryRequirementV1] = []
    if open_commit is not None and open_commit.raw is not None:
        requirements.append(
            RecoveryRequirementV1(
                "request_finished",
                open_commit.raw.call_sequence,
                open_commit.raw.plan_item_id,
                open_commit.raw.attempt_id,
                open_commit.start.event_id,
                open_commit.raw.raw_record_sha256,
            )
        )
        last_projection = open_commit.raw
    if pending_marker is not None and not marker_seen and last_projection is not None:
        requirements.append(
            RecoveryRequirementV1(
                pending_marker,
                last_projection.call_sequence,
                last_projection.plan_item_id,
                last_projection.attempt_id,
                (
                    open_commit.start.event_id
                    if open_commit is not None
                    else last_finish.payload.request_started_event_id
                    if last_finish is not None
                    else None
                ),
            )
        )
    if current_ordinal == len(plan) and not completion_seen:
        final_sequence = (
            last_projection.call_sequence if last_projection is not None else expected_call - 1
        )
        requirements.append(
            RecoveryRequirementV1(
                "generation_completed",
                final_sequence,
                origin_request_finished_event_id=(
                    last_finish.event_id
                    if last_finish is not None and open_commit is None
                    else None
                ),
            )
        )

    missing = tuple(
        sorted(
            (row.plan_item_id for row in plan[current_ordinal:]),
            key=lambda value: value.encode("utf-8"),
        )
    )
    if seal_requested is not None:
        complete = not missing
        if complete != (seal_requested.payload.expected_generation_status == "complete"):
            _fail("lifecycle_mismatch", "events", seal_requested.sequence)
        if requirements:
            _fail("lifecycle_mismatch", "events", seal_requested.sequence)

    return ValidatedHistoryV1(
        resolved_plan_item_ids=tuple(resolved),
        missing_plan_item_ids=missing,
        returned_models=tuple(sorted(returned_models, key=lambda value: value.encode("utf-8"))),
        next_unresolved_plan_ordinal=None if not missing else current_ordinal,
        next_call_sequence=expected_call,
        next_attempt_number=None if not missing else expected_attempt,
        open_attempt=open_commit,
        recovery_requirements=tuple(requirements),
        request_history_present=request_history,
        execution_history_present=execution_history,
        latest_no_call_blocked=latest_no_call_blocked,
        latest_event_recovered=latest_event_recovered,
        has_ambiguous_delivery=has_ambiguity
        or (open_commit is not None and open_commit.raw is None),
        has_authentication_stop=has_auth,
        seal_requested=seal_requested,
    )


def validate_history_v1(
    *,
    capsule: CapsuleV1,
    manifest: ResolvedManifestV2,
    environment: EnvironmentV1,
    plan: tuple[PlanRowV1, ...],
    events: Iterable[EventV1],
    raw_attempts: Iterable[RawAttemptV2],
    scratch_forbidden_namespace_identities: frozenset[NamespaceIdentity] | None = None,
    reserved_operation_id: UUID | None = None,
) -> ValidatedHistoryV1:
    """Validate both ledgers with exact external identity state and bounded resident memory."""

    if reserved_operation_id is not None and (
        type(reserved_operation_id) is not UUID
        or reserved_operation_id.version != 4
        or reserved_operation_id.variant != RFC_4122
    ):
        _fail("identity_mismatch", "events", None)
    try:
        with ExactIdentityRegistry(
            forbidden_namespace_identities=scratch_forbidden_namespace_identities
        ) as identities:
            history = _validate_history_v1(
                capsule=capsule,
                manifest=manifest,
                environment=environment,
                plan=plan,
                events=events,
                raw_attempts=raw_attempts,
                identity_registry=identities,
            )
            if reserved_operation_id is not None:
                identities.declare_core(reserved_operation_id, "operation", 0)
            return history
    except IdentityCollision as error:
        _fail("identity_mismatch", "events", error.row_index)
    except ScratchError:
        _fail("io_error", "events", None)


def derive_lifecycle_v1(
    history: ValidatedHistoryV1,
    *,
    validated_seal_state: Literal["SEALED_COMPLETE", "SEALED_BLOCKED"] | None = None,
) -> LifecycleProjectionV1:
    """Derive the exact quiescent lifecycle projection from validated facts."""

    missing = history.missing_plan_item_ids
    if history.has_ambiguous_delivery:
        underlying_state: LifecycleState = "AMBIGUOUS_INFLIGHT"
        blocker: tuple[OperationalBlocker, ...] = ("ambiguous_inflight",)
    elif history.has_authentication_stop:
        underlying_state = "AUTHENTICATION_STOPPED"
        blocker = ("authentication_stopped",)
    elif not missing:
        underlying_state = "GENERATION_COMPLETE"
        blocker = ()
    elif not history.request_history_present and history.latest_no_call_blocked:
        underlying_state = "PREPARED"
        blocker = ("never_started",)
    elif history.execution_history_present or history.request_history_present:
        underlying_state = "INTERRUPTED"
        blocker = ("interrupted",)
    else:
        underlying_state = "PREPARED"
        blocker = ("never_started",)

    state: LifecycleState
    if validated_seal_state is not None:
        state = validated_seal_state
    elif history.seal_requested is not None:
        state = "SEALING_INTERRUPTED"
    else:
        state = underlying_state
    return LifecycleProjectionV1(state, missing, blocker)
