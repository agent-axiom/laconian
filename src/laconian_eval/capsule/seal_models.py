"""Strict immutable capsule-seal schema and deterministic encoding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, NoReturn, Self, TypeVar

from pydantic import Field, TypeAdapter, field_validator, model_validator

from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes
from laconian_eval.capsule.events import (
    EventError,
    RequestStartedEventV1,
    SealRequestedEventV1,
    event_bytes,
)
from laconian_eval.capsule.history import (
    AttemptCommitV1,
    LifecycleProjectionV1,
    RawHistorySummaryV1,
    ValidatedHistoryV1,
)
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.record_models import CapsuleV1, EnvironmentV1
from laconian_eval.capsule.schema import (
    OPERATIONAL_BLOCKER_ORDER,
    UUID4,
    BoundedNonBlankString,
    CanonicalTimestamp,
    CapsuleModel,
    OperationalBlocker,
    RelativePosixPath,
    Sha256,
    StrictNonNegativeInt,
    require_fixed_order,
    require_utf8_sorted_unique,
)
from laconian_eval.capsule.tree_policy import capsule_path_kind

_SEAL_TEMP_PATTERN = re.compile(
    r"^\.seal\.[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\.tmp$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TSealModel = TypeVar("_TSealModel", bound=CapsuleModel)
_BOUNDED_STRING_ADAPTER = TypeAdapter(BoundedNonBlankString)


class SealModelError(ContentFreeCapsuleError):
    """Content-free seal failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("capsule seal rejected")


def _fail(code: str = "seal_mismatch") -> NoReturn:
    raise SealModelError(code)


def _revalidate_model(model_type: type[_TSealModel], value: object) -> _TSealModel:
    if type(value) is not model_type:
        _fail()
    try:
        payload = model_type.model_dump(
            value,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return model_type.model_validate(payload)
    except SealModelError:
        raise
    except Exception:
        _fail()


def _strict_nonnegative(value: object) -> int:
    if type(value) is not int or value < 0:
        _fail()
    return value


def _strict_sha256_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        _fail()
    try:
        values = tuple(value)
        for item in values:
            if type(item) is not str or _SHA256_PATTERN.fullmatch(item) is None:
                _fail()
        return require_utf8_sorted_unique(
            values,
            key=lambda item: item,
            label=label,
        )
    except SealModelError:
        raise
    except (TypeError, ValueError, UnicodeError):
        _fail()


def _strict_sha256_sequence(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        _fail()
    try:
        values = tuple(value)
        if any(
            type(item) is not str or _SHA256_PATTERN.fullmatch(item) is None for item in values
        ) or len(values) != len(set(values)):
            _fail()
        return values
    except SealModelError:
        raise
    except (TypeError, ValueError, UnicodeError):
        _fail()


def _strict_bounded_string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if type(value) is not tuple:
        _fail()
    try:
        checked = tuple(_BOUNDED_STRING_ADAPTER.validate_python(item) for item in value)
        if any(type(item) is not str for item in checked):
            _fail()
        return require_utf8_sorted_unique(
            checked,
            key=lambda item: item,
            label=label,
        )
    except SealModelError:
        raise
    except (TypeError, ValueError, UnicodeError):
        _fail()


def _strict_raw_summary(value: object) -> RawHistorySummaryV1:
    if type(value) is not RawHistorySummaryV1:
        _fail()
    checked = RawHistorySummaryV1(
        raw_attempt_count=_strict_nonnegative(value.raw_attempt_count),
        usage_complete_count=_strict_nonnegative(value.usage_complete_count),
        usage_partial_count=_strict_nonnegative(value.usage_partial_count),
        usage_unavailable_count=_strict_nonnegative(value.usage_unavailable_count),
        redacted_output_attempt_count=_strict_nonnegative(value.redacted_output_attempt_count),
        redacted_output_replacement_count=_strict_nonnegative(
            value.redacted_output_replacement_count
        ),
    )
    usage_total = (
        checked.usage_complete_count + checked.usage_partial_count + checked.usage_unavailable_count
    )
    if (
        usage_total != checked.raw_attempt_count
        or checked.redacted_output_attempt_count > checked.raw_attempt_count
        or (checked.redacted_output_attempt_count == 0)
        != (checked.redacted_output_replacement_count == 0)
        or checked.redacted_output_replacement_count < checked.redacted_output_attempt_count
    ):
        _fail()
    return checked


@dataclass(frozen=True, slots=True)
class _SealHistoryProjection:
    missing_plan_item_ids: tuple[str, ...]
    operational_blocker_codes: tuple[OperationalBlocker, ...]
    returned_models: tuple[str, ...]
    raw_summary: RawHistorySummaryV1
    latest_no_call_blocked_reason: Literal["credential_unavailable", "provider_unavailable"] | None
    seal_requested: SealRequestedEventV1
    open_start: RequestStartedEventV1 | None


def _revalidate_history(value: object) -> _SealHistoryProjection:
    if type(value) is not ValidatedHistoryV1:
        _fail()
    resolved = _strict_sha256_sequence(value.resolved_plan_item_ids)
    missing = _strict_sha256_tuple(
        value.missing_plan_item_ids,
        label="missing plan item IDs",
    )
    returned = _strict_bounded_string_tuple(
        value.returned_models,
        label="returned models",
    )
    summary = _strict_raw_summary(value.raw_summary)
    if (
        (not resolved and not missing)
        or set(resolved) & set(missing)
        or len(returned) > len(resolved)
        or len(resolved) > summary.raw_attempt_count
    ):
        _fail()
    next_call = _strict_nonnegative(value.next_call_sequence)
    next_ordinal = value.next_unresolved_plan_ordinal
    next_attempt = value.next_attempt_number
    if (
        next_ordinal != (None if not missing else len(resolved))
        or (next_ordinal is not None and type(next_ordinal) is not int)
        or (next_attempt is None) != (not missing)
        or (
            next_attempt is not None
            and (type(next_attempt) is not int or not 1 <= next_attempt <= 6)
        )
    ):
        _fail()
    if type(value.recovery_requirements) is not tuple or value.recovery_requirements:
        _fail()
    open_attempt = value.open_attempt
    open_start: RequestStartedEventV1 | None = None
    if open_attempt is not None:
        if (
            type(open_attempt) is not AttemptCommitV1
            or open_attempt.finish is not None
            or open_attempt.raw is not None
        ):
            _fail()
        open_start = _revalidate_model(RequestStartedEventV1, open_attempt.start)
        try:
            event_bytes(open_start)
        except EventError:
            _fail()
    rawless_open = open_attempt is not None and open_attempt.raw is None
    if summary.raw_attempt_count != next_call - int(rawless_open):
        _fail()

    request_history_present = value.request_history_present
    execution_history_present = value.execution_history_present
    blocked = value.latest_no_call_blocked
    reason = value.latest_no_call_blocked_reason
    has_ambiguity = value.has_ambiguous_delivery
    has_authentication_stop = value.has_authentication_stop
    latest_event_recovered = value.latest_event_recovered
    if any(
        type(item) is not bool
        for item in (
            request_history_present,
            execution_history_present,
            blocked,
            has_ambiguity,
            has_authentication_stop,
            latest_event_recovered,
        )
    ) or reason not in (
        None,
        "credential_unavailable",
        "provider_unavailable",
    ):
        _fail()
    if reason is not None and type(reason) is not str:
        _fail()
    if (
        request_history_present != (next_call > 0)
        or (request_history_present and not execution_history_present)
        or (request_history_present and blocked)
        or blocked != (reason is not None)
        or (reason is not None and not execution_history_present)
        or (
            (has_ambiguity or has_authentication_stop)
            and (not request_history_present or not execution_history_present)
        )
        or (has_ambiguity and has_authentication_stop)
        or (not missing and (has_ambiguity or has_authentication_stop))
        or (rawless_open and not has_ambiguity)
        or latest_event_recovered
    ):
        _fail()
    if has_ambiguity:
        blockers: tuple[OperationalBlocker, ...] = ("ambiguous_inflight",)
    elif has_authentication_stop:
        blockers = ("authentication_stopped",)
    elif not missing:
        blockers = ()
    elif not request_history_present and blocked:
        blockers = ("never_started",)
    elif execution_history_present or request_history_present:
        blockers = ("interrupted",)
    else:
        blockers = ("never_started",)
    if value.seal_requested is None:
        _fail()
    request = _revalidate_model(SealRequestedEventV1, value.seal_requested)
    try:
        event_bytes(request)
    except EventError:
        _fail()
    if open_start is not None and (
        open_start.run_id != request.run_id
        or open_start.operation_id == open_start.run_id
        or open_start.execution_session_id
        in (
            open_start.run_id,
            open_start.operation_id,
        )
        or open_start.sequence >= request.sequence
        or open_start.payload.call_sequence != next_call - 1
        or open_start.payload.plan_item_id not in missing
        or open_start.payload.attempt != next_attempt
    ):
        _fail()
    return _SealHistoryProjection(
        missing,
        blockers,
        returned,
        summary,
        reason,
        request,
        open_start,
    )


@dataclass(frozen=True, slots=True)
class _SealLifecycleProjection:
    missing_plan_item_ids: tuple[str, ...]
    operational_blocker_codes: tuple[OperationalBlocker, ...]


def _revalidate_lifecycle(value: object) -> _SealLifecycleProjection:
    if type(value) is not LifecycleProjectionV1 or type(value.state) is not str:
        _fail()
    if value.state != "SEALING_INTERRUPTED":
        _fail()
    missing = _strict_sha256_tuple(
        value.missing_plan_item_ids,
        label="lifecycle missing plan item IDs",
    )
    blockers = value.operational_blocker_codes
    if type(blockers) is not tuple or any(
        type(blocker) is not str or blocker not in OPERATIONAL_BLOCKER_ORDER for blocker in blockers
    ):
        _fail()
    try:
        checked_blockers = require_fixed_order(
            blockers,
            order=OPERATIONAL_BLOCKER_ORDER,
            label="lifecycle operational blockers",
        )
    except (TypeError, ValueError):
        _fail()
    return _SealLifecycleProjection(missing, checked_blockers)


class SealFileV1(CapsuleModel):
    path: RelativePosixPath
    byte_length: StrictNonNegativeInt
    sha256: Sha256


class SealUsageAvailabilityCountsV1(CapsuleModel):
    complete: StrictNonNegativeInt
    partial: StrictNonNegativeInt
    unavailable: StrictNonNegativeInt


class SealDisclosuresV1(CapsuleModel):
    source_state: Literal["clean", "dirty", "unbound", "unavailable"]
    returned_models: tuple[BoundedNonBlankString, ...]
    usage_availability_counts: SealUsageAvailabilityCountsV1
    redacted_output_attempt_count: StrictNonNegativeInt
    redacted_output_replacement_count: StrictNonNegativeInt
    dataset_ids: tuple[BoundedNonBlankString, ...]
    protocol_binding_ids: tuple[BoundedNonBlankString, ...]

    @field_validator("returned_models", "dataset_ids", "protocol_binding_ids")
    @classmethod
    def require_utf8_order(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return require_utf8_sorted_unique(
            value,
            key=lambda item: item,
            label="seal disclosure values",
        )

    @model_validator(mode="after")
    def validate_redaction_counts(self) -> Self:
        if (self.redacted_output_attempt_count == 0) != (
            self.redacted_output_replacement_count == 0
        ) or self.redacted_output_replacement_count < self.redacted_output_attempt_count:
            raise ValueError("redaction replacements cannot be fewer than redacted attempts")
        return self


class SealV1(CapsuleModel):
    seal_schema_version: Literal["1"]
    run_id: UUID4
    seal_transaction_id: UUID4
    generation_status: Literal["complete", "incomplete"]
    structural_integrity: Literal["valid"]
    missing_plan_item_ids: tuple[Sha256, ...]
    operational_blocker_codes: tuple[OperationalBlocker, ...]
    never_started_detail: (
        Literal[
            "credential_unavailable",
            "provider_unavailable",
            "operator_abandoned",
        ]
        | None
    )
    disclosures: SealDisclosuresV1
    final_event_sequence: StrictNonNegativeInt
    raw_attempt_count: StrictNonNegativeInt
    sealed_at: CanonicalTimestamp
    files: tuple[SealFileV1, ...] = Field(min_length=1)

    @field_validator("missing_plan_item_ids")
    @classmethod
    def validate_missing_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return require_utf8_sorted_unique(
            value,
            key=lambda digest: digest,
            label="missing plan item IDs",
        )

    @field_validator("operational_blocker_codes")
    @classmethod
    def validate_blocker_order(
        cls,
        value: tuple[OperationalBlocker, ...],
    ) -> tuple[OperationalBlocker, ...]:
        return require_fixed_order(
            value,
            order=OPERATIONAL_BLOCKER_ORDER,
            label="operational blocker codes",
        )

    @field_validator("files")
    @classmethod
    def validate_inventory(cls, value: tuple[SealFileV1, ...]) -> tuple[SealFileV1, ...]:
        checked = require_utf8_sorted_unique(
            value,
            key=lambda item: item.path,
            label="seal inventory paths",
        )
        if any(
            capsule_path_kind(item.path) != "file"
            or item.path in (".laconian.lock", "seal.json")
            or _SEAL_TEMP_PATTERN.fullmatch(item.path) is not None
            for item in checked
        ):
            raise ValueError("seal inventory contains an excluded path")
        return checked

    @model_validator(mode="after")
    def validate_relations(self) -> Self:
        if self.run_id == self.seal_transaction_id:
            raise ValueError("seal transaction must be distinct from the run")

        missing = self.missing_plan_item_ids
        blockers = self.operational_blocker_codes
        detail = self.never_started_detail
        if self.generation_status == "complete":
            if missing or blockers or detail is not None:
                raise ValueError("complete seal cannot carry incomplete state")
        else:
            if not missing or len(blockers) != 1:
                raise ValueError("incomplete seal requires missing IDs and one blocker")
            if blockers == ("never_started",):
                if detail is None:
                    raise ValueError("never-started seal requires detail")
            elif detail is not None:
                raise ValueError("only never-started seal may carry detail")

        usage = self.disclosures.usage_availability_counts
        if usage.complete + usage.partial + usage.unavailable != self.raw_attempt_count:
            raise ValueError("usage availability must cover every raw attempt")
        if self.disclosures.redacted_output_attempt_count > self.raw_attempt_count:
            raise ValueError("redacted attempts cannot exceed raw attempts")
        if len(self.disclosures.returned_models) > self.raw_attempt_count:
            raise ValueError("returned models cannot exceed raw attempts")
        return self


def _revalidate_files(value: object) -> tuple[SealFileV1, ...]:
    if type(value) is not tuple:
        _fail()
    try:
        checked = tuple(_revalidate_model(SealFileV1, item) for item in value)
        return tuple(sorted(checked, key=lambda item: item.path.encode("utf-8")))
    except SealModelError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeError):
        _fail()


def _source_state(
    environment: EnvironmentV1,
) -> Literal["clean", "dirty", "unbound", "unavailable"]:
    if environment.checkout_binding == "unbound":
        return "unbound"
    if environment.checkout_binding == "bound" and environment.git_state in {
        "clean",
        "dirty",
    }:
        return environment.git_state
    return "unavailable"


def derive_seal_v1(
    *,
    capsule: CapsuleV1,
    manifest: ResolvedManifestV2,
    environment: EnvironmentV1,
    history: ValidatedHistoryV1,
    lifecycle: LifecycleProjectionV1,
    seal_requested: SealRequestedEventV1,
    files: tuple[SealFileV1, ...],
) -> SealV1:
    """Derive the sole valid seal from a frozen, normalized pre-seal snapshot."""

    try:
        checked_capsule = _revalidate_model(CapsuleV1, capsule)
        checked_manifest = _revalidate_model(ResolvedManifestV2, manifest)
        checked_environment = _revalidate_model(EnvironmentV1, environment)
        checked_history = _revalidate_history(history)
        checked_lifecycle = _revalidate_lifecycle(lifecycle)
        checked_request = _revalidate_model(SealRequestedEventV1, seal_requested)
        event_bytes(checked_request)
        checked_files = _revalidate_files(files)
    except SealModelError:
        raise
    except Exception:
        _fail()

    if checked_request != checked_history.seal_requested:
        _fail()
    if checked_request.run_id != checked_capsule.run_id:
        _fail()
    transaction_id = checked_request.payload.seal_transaction_id
    if (
        checked_request.operation_id == checked_capsule.run_id
        or transaction_id == checked_capsule.run_id
        or transaction_id == checked_request.operation_id
    ):
        _fail()
    open_start = checked_history.open_start
    if open_start is not None and (
        checked_request.operation_id in (open_start.operation_id, open_start.execution_session_id)
        or transaction_id == open_start.execution_session_id
    ):
        _fail()
    if checked_lifecycle.missing_plan_item_ids != checked_history.missing_plan_item_ids:
        _fail()
    if checked_lifecycle.operational_blocker_codes != checked_history.operational_blocker_codes:
        _fail()

    missing = checked_lifecycle.missing_plan_item_ids
    blockers = checked_lifecycle.operational_blocker_codes
    if not missing:
        if blockers:
            _fail()
        generation_status: Literal["complete", "incomplete"] = "complete"
    else:
        if len(blockers) != 1:
            _fail()
        generation_status = "incomplete"
    if checked_request.payload.expected_generation_status != generation_status:
        _fail()

    blocked_reason = checked_history.latest_no_call_blocked_reason
    if blockers == ("never_started",):
        never_started_detail: (
            Literal[
                "credential_unavailable",
                "provider_unavailable",
                "operator_abandoned",
            ]
            | None
        ) = blocked_reason or "operator_abandoned"
    else:
        if blocked_reason is not None:
            _fail()
        never_started_detail = None

    summary = checked_history.raw_summary
    dataset_ids = tuple(
        sorted(
            (dataset.dataset_id for dataset in checked_manifest.capsule.datasets),
            key=lambda item: item.encode("utf-8"),
        )
    )
    protocol_binding_ids = tuple(
        sorted(
            (binding.binding_id for binding in checked_manifest.capsule.protocol_bindings),
            key=lambda item: item.encode("utf-8"),
        )
    )
    try:
        return SealV1(
            seal_schema_version="1",
            run_id=checked_capsule.run_id,
            seal_transaction_id=transaction_id,
            generation_status=generation_status,
            structural_integrity="valid",
            missing_plan_item_ids=missing,
            operational_blocker_codes=blockers,
            never_started_detail=never_started_detail,
            disclosures=SealDisclosuresV1(
                source_state=_source_state(checked_environment),
                returned_models=checked_history.returned_models,
                usage_availability_counts=SealUsageAvailabilityCountsV1(
                    complete=summary.usage_complete_count,
                    partial=summary.usage_partial_count,
                    unavailable=summary.usage_unavailable_count,
                ),
                redacted_output_attempt_count=summary.redacted_output_attempt_count,
                redacted_output_replacement_count=summary.redacted_output_replacement_count,
                dataset_ids=dataset_ids,
                protocol_binding_ids=protocol_binding_ids,
            ),
            final_event_sequence=checked_request.sequence,
            raw_attempt_count=summary.raw_attempt_count,
            sealed_at=checked_request.occurred_at,
            files=checked_files,
        )
    except SealModelError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeError):
        _fail()


def seal_bytes(seal: SealV1) -> bytes:
    """Return exact canonical bytes for one class-bound seal."""

    checked = _revalidate_model(SealV1, seal)
    try:
        return canonical_json(
            SealV1.model_dump(
                checked,
                mode="json",
                round_trip=True,
                warnings=False,
            )
        )
    except SealModelError:
        raise
    except (AttributeError, TypeError, ValueError, UnicodeError):
        _fail()


def capsule_sha256(seal: SealV1) -> str:
    """Return the digest of exact canonical seal bytes."""

    return sha256_bytes(seal_bytes(seal))
