"""Strict canonical lifecycle events for generation capsules."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias, cast
from uuid import UUID

from pydantic import Field, StrictBool, TypeAdapter, ValidationError, model_validator

from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.record_models import (
    EventText,
    EventTimestamp,
    EventUUID4,
    PreparedEventV1,
    SessionEnvironmentV1,
)
from laconian_eval.capsule.schema import (
    CapsuleModel,
    ProviderKind,
    Sha256,
    StrictNonNegativeInt,
    StrictPositiveInt,
)

_GENERIC_EVENT_ERROR = "capsule event rejected"
_EVENT_ID_DOMAIN = "laconian-event-v1"

EventKind: TypeAlias = Literal[
    "prepared",
    "execution_started",
    "execution_blocked",
    "request_started",
    "request_finished",
    "tail_recovered",
    "execution_interrupted",
    "authentication_stopped",
    "delivery_ambiguous",
    "generation_completed",
    "seal_requested",
]


class EventError(ValueError):
    """A content-free event failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_GENERIC_EVENT_ERROR)


class ExecutionStartedPayloadV1(CapsuleModel):
    resume_from_plan_ordinal: StrictNonNegativeInt
    session_environment: SessionEnvironmentV1


class ExecutionBlockedPayloadV1(CapsuleModel):
    reason: Literal["credential_unavailable", "provider_unavailable"]


class RequestStartedPayloadV1(CapsuleModel):
    call_sequence: StrictNonNegativeInt
    plan_item_id: Sha256
    attempt_id: Sha256
    attempt: StrictPositiveInt
    retry_of_attempt: StrictPositiveInt | None
    request_config_sha256: Sha256
    prompt_sha256: Sha256
    case_definition_sha256: Sha256
    instruction_sha256: Sha256
    provider: ProviderKind
    model: EventText

    @model_validator(mode="after")
    def validate_retry_parent(self) -> RequestStartedPayloadV1:
        expected = None if self.attempt == 1 else self.attempt - 1
        if self.retry_of_attempt != expected:
            raise ValueError("request retry parent mismatch")
        return self


class RequestFinishedPayloadV1(CapsuleModel):
    call_sequence: StrictNonNegativeInt
    plan_item_id: Sha256
    attempt_id: Sha256
    request_started_event_id: Sha256
    raw_record_sha256: Sha256
    recovered: StrictBool


class TailRecoveredPayloadV1(CapsuleModel):
    ledger: Literal["events", "raw"]
    removed_byte_count: StrictPositiveInt
    removed_sha256: Sha256
    related_attempt_id: Sha256 | None


class ExecutionInterruptedPayloadV1(CapsuleModel):
    next_plan_item_id: Sha256
    reason: Literal["signal", "operator", "internal_error"]


class AuthenticationStoppedPayloadV1(CapsuleModel):
    plan_item_id: Sha256
    attempt_id: Sha256
    origin_request_started_event_id: Sha256
    recovered: StrictBool


class DeliveryAmbiguousPayloadV1(CapsuleModel):
    plan_item_id: Sha256
    attempt_id: Sha256
    origin_request_started_event_id: Sha256
    recovered: StrictBool


class GenerationCompletedPayloadV1(CapsuleModel):
    terminal_plan_item_count: StrictPositiveInt
    final_plan_ordinal: StrictNonNegativeInt
    origin_request_finished_event_id: Sha256
    recovered: StrictBool


class SealRequestedPayloadV1(CapsuleModel):
    seal_transaction_id: EventUUID4
    expected_generation_status: Literal["complete", "incomplete"]
    prior_event_sequence: StrictNonNegativeInt


class _RuntimeEventV1(CapsuleModel):
    schema_version: Literal["1"]
    sequence: StrictPositiveInt
    event_id: Sha256
    run_id: EventUUID4
    occurred_at: EventTimestamp
    kind: EventKind
    operation_id: EventUUID4
    execution_session_id: EventUUID4 | None


class _SessionRequiredEventV1(_RuntimeEventV1):
    execution_session_id: EventUUID4


class _SessionNullEventV1(_RuntimeEventV1):
    execution_session_id: None


class ExecutionStartedEventV1(_SessionRequiredEventV1):
    kind: Literal["execution_started"]
    payload: ExecutionStartedPayloadV1


class ExecutionBlockedEventV1(_SessionRequiredEventV1):
    kind: Literal["execution_blocked"]
    payload: ExecutionBlockedPayloadV1


class RequestStartedEventV1(_SessionRequiredEventV1):
    kind: Literal["request_started"]
    payload: RequestStartedPayloadV1


class RequestFinishedEventV1(_RuntimeEventV1):
    kind: Literal["request_finished"]
    payload: RequestFinishedPayloadV1

    @model_validator(mode="after")
    def validate_recovery_session(self) -> RequestFinishedEventV1:
        if self.payload.recovered != (self.execution_session_id is None):
            raise ValueError("request-finish recovery session mismatch")
        return self


class TailRecoveredEventV1(_SessionNullEventV1):
    kind: Literal["tail_recovered"]
    payload: TailRecoveredPayloadV1


class ExecutionInterruptedEventV1(_SessionRequiredEventV1):
    kind: Literal["execution_interrupted"]
    payload: ExecutionInterruptedPayloadV1


class AuthenticationStoppedEventV1(_RuntimeEventV1):
    kind: Literal["authentication_stopped"]
    payload: AuthenticationStoppedPayloadV1

    @model_validator(mode="after")
    def validate_recovery_session(self) -> AuthenticationStoppedEventV1:
        if self.payload.recovered != (self.execution_session_id is None):
            raise ValueError("authentication recovery session mismatch")
        return self


class DeliveryAmbiguousEventV1(_RuntimeEventV1):
    kind: Literal["delivery_ambiguous"]
    payload: DeliveryAmbiguousPayloadV1

    @model_validator(mode="after")
    def validate_recovery_session(self) -> DeliveryAmbiguousEventV1:
        if self.payload.recovered != (self.execution_session_id is None):
            raise ValueError("ambiguity recovery session mismatch")
        return self


class GenerationCompletedEventV1(_RuntimeEventV1):
    kind: Literal["generation_completed"]
    payload: GenerationCompletedPayloadV1

    @model_validator(mode="after")
    def validate_recovery_session(self) -> GenerationCompletedEventV1:
        if self.payload.recovered != (self.execution_session_id is None):
            raise ValueError("completion recovery session mismatch")
        return self


class SealRequestedEventV1(_SessionNullEventV1):
    kind: Literal["seal_requested"]
    payload: SealRequestedPayloadV1

    @model_validator(mode="after")
    def validate_prior_sequence(self) -> SealRequestedEventV1:
        if self.payload.prior_event_sequence != self.sequence - 1:
            raise ValueError("seal prior sequence mismatch")
        return self


EventV1: TypeAlias = Annotated[
    PreparedEventV1
    | ExecutionStartedEventV1
    | ExecutionBlockedEventV1
    | RequestStartedEventV1
    | RequestFinishedEventV1
    | TailRecoveredEventV1
    | ExecutionInterruptedEventV1
    | AuthenticationStoppedEventV1
    | DeliveryAmbiguousEventV1
    | GenerationCompletedEventV1
    | SealRequestedEventV1,
    Field(discriminator="kind"),
]

_EVENT_ADAPTER: TypeAdapter[EventV1] = TypeAdapter(EventV1)
_EVENT_CLASSES = (
    PreparedEventV1,
    ExecutionStartedEventV1,
    ExecutionBlockedEventV1,
    RequestStartedEventV1,
    RequestFinishedEventV1,
    TailRecoveredEventV1,
    ExecutionInterruptedEventV1,
    AuthenticationStoppedEventV1,
    DeliveryAmbiguousEventV1,
    GenerationCompletedEventV1,
    SealRequestedEventV1,
)

_EVENT_VALIDATION_CODES = {
    "request retry parent mismatch": "retry_mismatch",
    "request-finish recovery session mismatch": "lifecycle_mismatch",
    "authentication recovery session mismatch": "lifecycle_mismatch",
    "ambiguity recovery session mismatch": "lifecycle_mismatch",
    "completion recovery session mismatch": "lifecycle_mismatch",
    "seal prior sequence mismatch": "history_mismatch",
}


def _event_validation_code(error: ValidationError) -> str:
    mapped: str | None = None
    for detail in error.errors(include_url=False, include_input=False):
        context = detail.get("ctx")
        if type(context) is not dict:
            return "invalid_event"
        cause = context.get("error")
        if (
            type(cause) is not ValueError
            or type(cause.args) is not tuple
            or len(cause.args) != 1
            or type(cause.args[0]) is not str
        ):
            return "invalid_event"
        candidate = _EVENT_VALIDATION_CODES.get(cause.args[0])
        if candidate is None or (mapped is not None and candidate != mapped):
            return "invalid_event"
        mapped = candidate
    return "invalid_event" if mapped is None else mapped


def _dump_event(event: EventV1, *, mode: Literal["python", "json"]) -> dict[str, object]:
    for event_class in _EVENT_CLASSES:
        if type(event) is event_class:
            dumped = event_class.model_dump(event, mode=mode, round_trip=True, warnings=False)
            if type(dumped) is not dict:
                raise TypeError
            return cast(dict[str, object], dumped)
    raise TypeError


def _strict_event(value: object) -> EventV1:
    try:
        if not any(type(value) is event_class for event_class in _EVENT_CLASSES):
            raise TypeError
        payload = _dump_event(cast(EventV1, value), mode="python")
        checked = _EVENT_ADAPTER.validate_python(payload)
        if type(checked) is not type(value):
            raise TypeError
        return checked
    except Exception:
        raise EventError("invalid_event") from None


def _identity_payload(event: EventV1) -> dict[str, object]:
    payload = _dump_event(event, mode="json")
    payload.pop("event_id")
    return payload


def _require_identity(event: EventV1) -> EventV1:
    try:
        expected = stable_digest(_EVENT_ID_DOMAIN, _identity_payload(event))
    except Exception:
        raise EventError("invalid_event") from None
    if event.event_id != expected:
        raise EventError("event_id_mismatch")
    return event


def parse_event(value: object) -> EventV1:
    """Parse and identity-check one strict event mapping without echoing rejected data."""

    try:
        event = _EVENT_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise EventError(_event_validation_code(error)) from None
    except Exception:
        raise EventError("invalid_event") from None
    return _require_identity(event)


def make_event(
    *,
    sequence: int,
    run_id: UUID,
    occurred_at: datetime,
    kind: EventKind,
    operation_id: UUID,
    execution_session_id: UUID | None,
    payload: object,
) -> EventV1:
    """Build one strict event and derive its canonical identity."""

    try:
        caller_payload = {
            "schema_version": "1",
            "sequence": sequence,
            "event_id": "0" * 64,
            "run_id": run_id,
            "occurred_at": occurred_at,
            "kind": kind,
            "operation_id": operation_id,
            "execution_session_id": execution_session_id,
            "payload": payload,
        }
        provisional = _EVENT_ADAPTER.validate_python(caller_payload)
        checked_payload = _dump_event(provisional, mode="python")
        checked_payload["event_id"] = stable_digest(
            _EVENT_ID_DOMAIN, _identity_payload(provisional)
        )
        return _require_identity(_EVENT_ADAPTER.validate_python(checked_payload))
    except Exception:
        raise EventError("invalid_event") from None


def make_prepared_event(
    *,
    run_id: UUID,
    operation_id: UUID,
    occurred_at: datetime,
    manifest_sha256: str,
    input_index_sha256: str,
    case_index_sha256: str,
    plan_sha256: str,
    environment_sha256: str,
    runner_source_sha256: str,
) -> PreparedEventV1:
    """Build the sequence-zero prepared event and its canonical identity."""

    event = make_event(
        sequence=0,
        run_id=run_id,
        operation_id=operation_id,
        occurred_at=occurred_at,
        kind="prepared",
        execution_session_id=None,
        payload={
            "manifest_sha256": manifest_sha256,
            "input_index_sha256": input_index_sha256,
            "case_index_sha256": case_index_sha256,
            "plan_sha256": plan_sha256,
            "environment_sha256": environment_sha256,
            "runner_source_sha256": runner_source_sha256,
        },
    )
    if type(event) is not PreparedEventV1:  # pragma: no cover
        raise EventError("invalid_event")
    return event


def event_bytes(event: EventV1) -> bytes:
    """Strictly revalidate and encode one bounded LF-free canonical event."""

    checked = _require_identity(_strict_event(event))
    try:
        encoded = canonical_json(_dump_event(checked, mode="json"))
    except (ResourceLimitError, TypeError, ValueError, UnicodeError):
        raise EventError("invalid_event") from None
    if len(encoded) > RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes:
        raise EventError("event_jsonl_row_limit")
    return encoded


def event_jsonl(event: EventV1) -> bytes:
    """Encode one strict canonical event with exactly one final LF."""

    return event_bytes(event) + b"\n"
