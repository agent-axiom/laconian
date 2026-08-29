"""Strict canonical provider-attempt evidence for generation capsules."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Self, TypeAlias
from uuid import RFC_4122, UUID

from pydantic import BeforeValidator, Field, StrictBool, model_validator

from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_timestamp,
    sha256_bytes,
    stable_digest,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, bounded_utf8_length
from laconian_eval.capsule.sanitizer import (
    SanitizedOutput,
    SanitizerError,
    SanitizerPatterns,
    provider_metadata_is_safe,
    require_safe_provider_metadata,
    sanitize_diagnostic_or_constant,
    sanitize_output,
)
from laconian_eval.capsule.schema import (
    UUID4,
    Arm,
    BoundedNonBlankString,
    CanonicalTimestamp,
    CapsuleModel,
    CaseId,
    DiagnosticString,
    Locale,
    Sha256,
    StrictNonNegativeInt,
    StrictPositiveInt,
)
from laconian_eval.providers.base import (
    DeliveryCertainty,
    GenerationResult,
    ProviderError,
    TokenUsage,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GENERIC_ATTEMPT_ERROR = "attempt evidence rejected"

UsageAvailability: TypeAlias = Literal["complete", "partial", "unavailable"]
UsageSource: TypeAlias = Literal["provider", "adapter"]
CacheAccounting: TypeAlias = Literal["reported", "not_reported", "not_applicable"]
TerminalReason: TypeAlias = Literal[
    "success",
    "retry_exhausted",
    "provider_rejected",
    "authentication_stopped",
    "ambiguous_delivery",
]
AttemptNumber: TypeAlias = Annotated[int, Field(strict=True, ge=1, le=6)]
_DELIVERY_CERTAINTIES = frozenset(
    {
        "definitely_not_sent",
        "definitely_rejected",
        "response_received",
        "unknown",
    }
)


class AttemptEvidenceError(ValueError):
    """A content-free attempt-evidence failure with a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_GENERIC_ATTEMPT_ERROR)


def _provider_metadata(value: object) -> str:
    if type(value) is not str:
        raise ValueError("provider metadata must be a string")
    bounded_utf8_length(
        value,
        limit=RESOURCE_LIMITS_V1.bounded_string_bytes,
        code="bounded_string_limit",
    )
    if not value.strip():
        raise ValueError("provider metadata must not be blank")
    if any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value):
        raise ValueError("provider metadata must not contain controls")
    return value


def _output_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("output must be a string")
    bounded_utf8_length(
        value,
        limit=RESOURCE_LIMITS_V1.output_utf8_bytes,
        code="output_utf8_limit",
    )
    if not value.strip():
        raise ValueError("output must not be blank")
    return value


ProviderMetadataString: TypeAlias = Annotated[str, BeforeValidator(_provider_metadata)]
OutputString: TypeAlias = Annotated[str, BeforeValidator(_output_string)]


def _attempt_run_id_boundary(value: object) -> object:
    try:
        if type(value) is str:
            return value
        if type(value) is not UUID or type(value.int) is not int:
            raise ValueError
        projected = UUID.__str__(value)
        if type(projected) is not str:
            raise ValueError
        return projected
    except Exception:
        raise ValueError("attempt run ID boundary rejected") from None


def _attempt_timestamp_boundary(value: object) -> object:
    try:
        if type(value) is str:
            return value
        if type(value) is not datetime:
            raise ValueError
        projected = canonical_timestamp(value)
        if type(projected) is not str:
            raise ValueError
        return projected
    except Exception:
        raise ValueError("attempt timestamp boundary rejected") from None


AttemptRunId: TypeAlias = Annotated[UUID4, BeforeValidator(_attempt_run_id_boundary)]
AttemptTimestamp: TypeAlias = Annotated[
    CanonicalTimestamp,
    BeforeValidator(_attempt_timestamp_boundary),
]


class AttemptUsageV2(CapsuleModel):
    input_tokens: StrictNonNegativeInt | None
    output_tokens: StrictNonNegativeInt | None
    total_tokens: StrictNonNegativeInt | None
    cached_input_tokens: StrictNonNegativeInt | None
    availability: UsageAvailability
    source: UsageSource
    cache_accounting: CacheAccounting

    @model_validator(mode="after")
    def validate_accounting_state(self) -> Self:
        core_counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        available_core_counts = sum(value is not None for value in core_counts)

        if self.availability == "unavailable":
            if available_core_counts != 0 or self.cached_input_tokens is not None:
                raise ValueError("unavailable usage must not contain counts")
        elif self.availability == "partial":
            if available_core_counts not in (1, 2):
                raise ValueError("partial usage requires one or two core counts")
        elif (
            available_core_counts != 3
            or self.total_tokens != self.input_tokens + self.output_tokens  # type: ignore[operator]
        ):
            raise ValueError("complete usage requires consistent core counts")

        if self.cache_accounting == "reported":
            if self.cached_input_tokens is None:
                raise ValueError("reported cache accounting requires a count")
        elif self.cached_input_tokens is not None:
            raise ValueError("unreported cache accounting must not contain a count")

        if self.cached_input_tokens is not None and (
            self.input_tokens is None or self.cached_input_tokens > self.input_tokens
        ):
            raise ValueError("cached input tokens exceed input tokens")
        return self


class AttemptErrorV2(CapsuleModel):
    kind: ProviderMetadataString
    message: DiagnosticString
    retryable: StrictBool
    request_id: ProviderMetadataString | None


@dataclass(frozen=True, slots=True)
class NormalizedProviderEvidenceV2:
    """Pure, sanitized evidence returned by one provider call."""

    delivery_certainty: DeliveryCertainty
    output: SanitizedOutput | None
    response_model: str | None
    request_id: str | None
    finish_reason: str | None
    usage: AttemptUsageV2
    error: AttemptErrorV2 | None


def _unavailable_provider_usage() -> AttemptUsageV2:
    return AttemptUsageV2(
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        cached_input_tokens=None,
        availability="unavailable",
        source="provider",
        cache_accounting="not_reported",
    )


def _normalize_provider_usage(value: object) -> tuple[AttemptUsageV2, bool]:
    unavailable = _unavailable_provider_usage()
    if value is None:
        return unavailable, True
    if type(value) is not TokenUsage:
        return unavailable, False
    try:
        cached_input_tokens = value.cached_input_tokens
        return (
            AttemptUsageV2(
                input_tokens=value.input_tokens,
                output_tokens=value.output_tokens,
                total_tokens=value.total_tokens,
                cached_input_tokens=cached_input_tokens,
                availability="complete",
                source="provider",
                cache_accounting=(
                    "reported" if cached_input_tokens is not None else "not_reported"
                ),
            ),
            True,
        )
    except (AttributeError, TypeError, ValueError, UnicodeError):
        return unavailable, False


def _normalize_provider_metadata(
    value: object,
    *,
    patterns: SanitizerPatterns,
) -> tuple[str | None, bool]:
    if not provider_metadata_is_safe(value, patterns=patterns):
        return None, False
    return require_safe_provider_metadata(value, patterns=patterns), True


def _constant_normalized_error(
    kind: Literal[
        "malformed_response",
        "unsafe_provider_metadata",
        "ambiguous_auth_delivery",
    ],
    *,
    delivery_certainty: DeliveryCertainty,
    response_model: str | None = None,
    request_id: str | None = None,
    finish_reason: str | None = None,
    usage: AttemptUsageV2 | None = None,
) -> NormalizedProviderEvidenceV2:
    return NormalizedProviderEvidenceV2(
        delivery_certainty=delivery_certainty,
        output=None,
        response_model=response_model,
        request_id=request_id,
        finish_reason=finish_reason,
        usage=usage if usage is not None else _unavailable_provider_usage(),
        error=AttemptErrorV2(
            kind=kind,
            message=kind,
            retryable=False,
            request_id=request_id,
        ),
    )


def _normalize_result(
    outcome: GenerationResult,
    *,
    patterns: SanitizerPatterns,
) -> NormalizedProviderEvidenceV2:
    try:
        raw_certainty = outcome.delivery_certainty
        raw_response_model = outcome.response_model
        raw_request_id = outcome.request_id
        raw_finish_reason = outcome.finish_reason
        raw_usage = outcome.usage
        raw_output = outcome.output_text
    except (AttributeError, TypeError, ValueError):
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty="response_received",
        )

    response_model, response_model_is_safe = _normalize_provider_metadata(
        raw_response_model,
        patterns=patterns,
    )
    request_id, request_id_is_safe = _normalize_provider_metadata(
        raw_request_id,
        patterns=patterns,
    )
    finish_reason, finish_reason_is_safe = _normalize_provider_metadata(
        raw_finish_reason,
        patterns=patterns,
    )
    usage, usage_is_valid = _normalize_provider_usage(raw_usage)

    if not all((response_model_is_safe, request_id_is_safe, finish_reason_is_safe)):
        return _constant_normalized_error(
            "unsafe_provider_metadata",
            delivery_certainty="response_received",
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )
    if (
        type(raw_certainty) is not str
        or raw_certainty != "response_received"
        or not usage_is_valid
        or response_model is None
    ):
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty="response_received",
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )

    try:
        output = sanitize_output(raw_output, patterns=patterns)
    except (SanitizerError, TypeError, ValueError, UnicodeError):
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty="response_received",
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )

    if type(output) is not SanitizedOutput:
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty="response_received",
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )
    if output.text is None:
        if output.byte_length <= RESOURCE_LIMITS_V1.output_utf8_bytes:
            return _constant_normalized_error(
                "malformed_response",
                delivery_certainty="response_received",
                response_model=response_model,
                request_id=request_id,
                finish_reason=finish_reason,
                usage=usage,
            )
        return NormalizedProviderEvidenceV2(
            delivery_certainty="response_received",
            output=output,
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
            error=AttemptErrorV2(
                kind="response_too_large",
                message="response_too_large",
                retryable=False,
                request_id=request_id,
            ),
        )
    if output.byte_length > RESOURCE_LIMITS_V1.output_utf8_bytes:
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty="response_received",
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )
    return NormalizedProviderEvidenceV2(
        delivery_certainty="response_received",
        output=output,
        response_model=response_model,
        request_id=request_id,
        finish_reason=finish_reason,
        usage=usage,
        error=None,
    )


def _normalize_error(
    outcome: ProviderError,
    *,
    patterns: SanitizerPatterns,
) -> NormalizedProviderEvidenceV2:
    try:
        raw_certainty = outcome.delivery_certainty
        raw_retryable = outcome.retryable
        raw_kind = outcome.kind
        raw_message = outcome.message
        raw_response_model = outcome.response_model
        raw_request_id = outcome.request_id
        raw_finish_reason = outcome.finish_reason
        raw_usage = outcome.usage
    except (AttributeError, TypeError, ValueError):
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty="unknown",
        )

    certainty_is_valid = type(raw_certainty) is str and raw_certainty in _DELIVERY_CERTAINTIES
    certainty: DeliveryCertainty = raw_certainty if certainty_is_valid else "unknown"
    response_model, response_model_is_safe = _normalize_provider_metadata(
        raw_response_model,
        patterns=patterns,
    )
    request_id, request_id_is_safe = _normalize_provider_metadata(
        raw_request_id,
        patterns=patterns,
    )
    finish_reason, finish_reason_is_safe = _normalize_provider_metadata(
        raw_finish_reason,
        patterns=patterns,
    )
    kind, kind_is_safe = _normalize_provider_metadata(raw_kind, patterns=patterns)
    usage, usage_is_valid = _normalize_provider_usage(raw_usage)

    if not certainty_is_valid or type(raw_retryable) is not bool:
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty=certainty,
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )
    if not all(
        (
            response_model_is_safe,
            request_id_is_safe,
            finish_reason_is_safe,
            kind_is_safe,
        )
    ):
        return _constant_normalized_error(
            "unsafe_provider_metadata",
            delivery_certainty=certainty,
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )
    if not usage_is_valid or kind is None or kind == "response_too_large":
        return _constant_normalized_error(
            "malformed_response",
            delivery_certainty=certainty,
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )
    if kind == "authentication" and certainty in ("unknown", "definitely_not_sent"):
        return _constant_normalized_error(
            "ambiguous_auth_delivery",
            delivery_certainty="unknown",
            response_model=response_model,
            request_id=request_id,
            finish_reason=finish_reason,
            usage=usage,
        )

    diagnostic = sanitize_diagnostic_or_constant(raw_message, patterns=patterns)
    return NormalizedProviderEvidenceV2(
        delivery_certainty=certainty,
        output=None,
        response_model=response_model,
        request_id=request_id,
        finish_reason=finish_reason,
        usage=usage,
        error=AttemptErrorV2(
            kind=kind,
            message=diagnostic.text,
            retryable=raw_retryable,
            request_id=request_id,
        ),
    )


def normalize_provider_outcome(
    outcome: GenerationResult | ProviderError,
    *,
    patterns: SanitizerPatterns,
) -> NormalizedProviderEvidenceV2:
    """Normalize provider-controlled evidence without choosing execution state."""

    if type(outcome) is GenerationResult:
        return _normalize_result(outcome, patterns=patterns)
    if type(outcome) is ProviderError:
        return _normalize_error(outcome, patterns=patterns)
    return _constant_normalized_error(
        "malformed_response",
        delivery_certainty="unknown",
    )


def _derive_attempt_id_fields(run_id: UUID, plan_item_id: str, attempt_number: int) -> str:
    return stable_digest(
        "laconian-attempt-v1",
        {
            "run_id": run_id,
            "plan_item_id": plan_item_id,
            "attempt_number": attempt_number,
        },
    )


def _derive_response_id_fields(
    *,
    run_id: UUID,
    plan_item_id: str,
    attempt_id: str,
    case_uid: str,
    instruction_sha256: str,
    output_sha256: str,
) -> str:
    return stable_digest(
        "laconian-response-v1",
        {
            "run_id": run_id,
            "plan_item_id": plan_item_id,
            "attempt_id": attempt_id,
            "case_uid": case_uid,
            "instruction_sha256": instruction_sha256,
            "output_sha256": output_sha256,
        },
    )


class RawAttemptV2(CapsuleModel):
    schema_version: Literal["2"]
    runner_version: BoundedNonBlankString
    run_id: AttemptRunId
    manifest_sha256: Sha256
    plan_item_id: Sha256
    attempt_id: Sha256
    scenario_uid: Sha256
    case_uid: Sha256
    case_id: CaseId
    locale: Locale
    case_definition_sha256: Sha256
    arm: Arm
    repetition: StrictNonNegativeInt
    attempt: AttemptNumber
    terminal: StrictBool
    call_sequence: StrictNonNegativeInt
    retry_of_attempt: StrictPositiveInt | None
    backoff_ms: StrictNonNegativeInt | None
    delivery_certainty: DeliveryCertainty
    prompt_sha256: Sha256
    instruction_sha256: Sha256
    request_config_sha256: Sha256
    provider: BoundedNonBlankString
    model: BoundedNonBlankString
    response_model: ProviderMetadataString | None
    started_at: AttemptTimestamp
    elapsed_ms: StrictNonNegativeInt
    output_text: OutputString | None
    output_sha256: Sha256 | None
    response_id: Sha256 | None
    output_was_redacted: StrictBool
    output_redaction_count: StrictNonNegativeInt
    discarded_output_byte_length: StrictNonNegativeInt | None
    discarded_output_sha256: Sha256 | None
    usage: AttemptUsageV2
    request_id: ProviderMetadataString | None
    finish_reason: ProviderMetadataString | None
    error: AttemptErrorV2 | None
    terminal_reason: TerminalReason | None

    @model_validator(mode="after")
    def validate_attempt_contract(self) -> Self:
        if (
            type(self.run_id) is not UUID
            or type(self.run_id.int) is not int
            or type(self.started_at) is not datetime
        ):
            raise ValueError("attempt scalar boundary mismatch")
        expected_attempt_id = _derive_attempt_id_fields(
            self.run_id,
            self.plan_item_id,
            self.attempt,
        )
        if self.attempt_id != expected_attempt_id:
            raise ValueError("attempt identity mismatch")
        expected_retry_parent = None if self.attempt == 1 else self.attempt - 1
        if self.retry_of_attempt != expected_retry_parent:
            raise ValueError("retry lineage mismatch")
        if self.output_was_redacted != (self.output_redaction_count > 0):
            raise ValueError("output redaction disclosure mismatch")

        if self.error is None:
            self._validate_success()
        else:
            self._validate_error()
        return self

    def _validate_success(self) -> None:
        if (
            not self.terminal
            or self.backoff_ms is not None
            or self.delivery_certainty != "response_received"
            or self.output_text is None
            or self.output_sha256 is None
            or self.response_id is None
            or self.response_model is None
            or self.terminal_reason != "success"
            or self.discarded_output_byte_length is not None
            or self.discarded_output_sha256 is not None
        ):
            raise ValueError("invalid success attempt")

        expected_output_sha256 = hashlib.sha256(
            self.output_text.encode("utf-8", errors="strict")
        ).hexdigest()
        if self.output_sha256 != expected_output_sha256:
            raise ValueError("output identity mismatch")
        expected_response_id = _derive_response_id_fields(
            run_id=self.run_id,
            plan_item_id=self.plan_item_id,
            attempt_id=self.attempt_id,
            case_uid=self.case_uid,
            instruction_sha256=self.instruction_sha256,
            output_sha256=self.output_sha256,
        )
        if self.response_id != expected_response_id:
            raise ValueError("response identity mismatch")

    def _validate_error(self) -> None:
        error = self.error
        if error is None:  # pragma: no cover - narrowed by the caller
            raise ValueError("missing error")
        if (
            self.output_text is not None
            or self.output_sha256 is not None
            or self.response_id is not None
        ):
            raise ValueError("error attempts cannot contain output identity")

        if error.kind == "authentication" and self.delivery_certainty in (
            "unknown",
            "definitely_not_sent",
        ):
            raise ValueError("contradictory authentication delivery evidence")

        if self.delivery_certainty == "unknown":
            expected_terminal = True
            expected_reason: TerminalReason | None = "ambiguous_delivery"
            expected_backoff = None
        elif error.kind == "authentication":
            expected_terminal = True
            expected_reason = "authentication_stopped"
            expected_backoff = None
        elif error.retryable and self.delivery_certainty in (
            "definitely_not_sent",
            "definitely_rejected",
        ):
            if self.terminal:
                expected_terminal = True
                expected_reason = "retry_exhausted"
                expected_backoff = None
            else:
                if self.attempt == 6:
                    raise ValueError("retry limit exceeded")
                expected_terminal = False
                expected_reason = None
                expected_backoff = 100 * 2 ** (self.attempt - 1)
        else:
            expected_terminal = True
            expected_reason = "provider_rejected"
            expected_backoff = None

        if (
            self.terminal is not expected_terminal
            or self.terminal_reason != expected_reason
            or self.backoff_ms != expected_backoff
        ):
            raise ValueError("attempt truth-table mismatch")

        if error.kind == "response_too_large":
            if (
                self.delivery_certainty != "response_received"
                or error.message != "response_too_large"
                or error.retryable
                or self.discarded_output_byte_length is None
                or self.discarded_output_byte_length <= RESOURCE_LIMITS_V1.output_utf8_bytes
                or self.discarded_output_sha256 is None
            ):
                raise ValueError("invalid discarded-output evidence")
        elif (
            self.output_was_redacted
            or self.output_redaction_count != 0
            or self.discarded_output_byte_length is not None
            or self.discarded_output_sha256 is not None
        ):
            raise ValueError("error attempt discloses output evidence")


def derive_attempt_id(run_id: UUID, plan_item_id: str, attempt_number: int) -> str:
    """Derive an attempt identity after an exact content-free boundary check."""

    try:
        if (
            type(run_id) is not UUID
            or type(run_id.int) is not int
            or type(plan_item_id) is not str
            or _SHA256_PATTERN.fullmatch(plan_item_id) is None
            or type(attempt_number) is not int
            or not 1 <= attempt_number <= 6
        ):
            raise ValueError
        projected_run_id = UUID.__str__(run_id)
        if type(projected_run_id) is not str:
            raise ValueError
        safe_run_id = UUID(projected_run_id)
        if safe_run_id.version != 4 or safe_run_id.variant != RFC_4122:
            raise ValueError
        return _derive_attempt_id_fields(safe_run_id, plan_item_id, attempt_number)
    except Exception:
        raise AttemptEvidenceError("invalid_attempt_identity") from None


def _strict_attempt(value: object) -> RawAttemptV2:
    try:
        if type(value) is not RawAttemptV2:
            raise TypeError
        payload = RawAttemptV2.model_dump(
            value,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return RawAttemptV2.model_validate(payload)
    except Exception:
        raise AttemptEvidenceError("invalid_attempt_evidence") from None


def derive_response_id(attempt: RawAttemptV2) -> str:
    """Return the response identity for one strictly valid success attempt."""

    checked = _strict_attempt(attempt)
    if checked.error is not None or checked.output_sha256 is None:
        raise AttemptEvidenceError("invalid_attempt_evidence")
    return _derive_response_id_fields(
        run_id=checked.run_id,
        plan_item_id=checked.plan_item_id,
        attempt_id=checked.attempt_id,
        case_uid=checked.case_uid,
        instruction_sha256=checked.instruction_sha256,
        output_sha256=checked.output_sha256,
    )


def raw_attempt_bytes(attempt: RawAttemptV2) -> bytes:
    """Return the exact LF-free canonical bytes of a strictly valid attempt."""

    checked = _strict_attempt(attempt)
    try:
        payload = RawAttemptV2.model_dump(
            checked,
            mode="json",
            round_trip=True,
            warnings=False,
        )
        return canonical_json(payload)
    except Exception:
        raise AttemptEvidenceError("invalid_attempt_evidence") from None


def raw_record_sha256(attempt: RawAttemptV2) -> str:
    """Hash the exact LF-free canonical raw-attempt row."""

    return sha256_bytes(raw_attempt_bytes(attempt))


def raw_attempt_jsonl(attempt: RawAttemptV2) -> bytes:
    """Return one bounded canonical raw-attempt row with exactly one final LF."""

    row = raw_attempt_bytes(attempt)
    if len(row) > RESOURCE_LIMITS_V1.raw_jsonl_row_bytes:
        raise AttemptEvidenceError("raw_jsonl_row_limit")
    return row + b"\n"
