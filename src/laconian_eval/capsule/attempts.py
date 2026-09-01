"""Strict canonical provider-attempt evidence for generation capsules."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Protocol, Self, TypeAlias, cast
from uuid import RFC_4122, UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StrictBool,
    field_validator,
    model_serializer,
    model_validator,
)

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
    PublicBenchmarkModelId,
    ServiceTier,
    Sha256,
    StrictNonNegativeInt,
    StrictPositiveInt,
)
from laconian_eval.providers.base import (
    AppliedCacheControlStatus,
    CacheReadStatus,
    CacheWriteStatus,
    DeliveryCertainty,
    GenerationResult,
    ProviderError,
    PublicBenchmarkRequestV1,
    ReasoningTokenAccounting,
    ServiceTierStatus,
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
    cached_input_tokens: StrictNonNegativeInt | None = None
    availability: UsageAvailability
    source: UsageSource
    cache_accounting: CacheAccounting | None = None
    cache_read_tokens: StrictNonNegativeInt | None = None
    cache_write_tokens: StrictNonNegativeInt | None = None
    ordinary_uncached_input_tokens: StrictNonNegativeInt | None = None
    reasoning_tokens: StrictNonNegativeInt | None = None
    cache_read_status: CacheReadStatus | None = None
    cache_write_status: CacheWriteStatus | None = None
    reasoning_token_accounting: ReasoningTokenAccounting | None = None

    @model_validator(mode="after")
    def validate_accounting_state(self) -> Self:
        core_counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        available_core_counts = sum(value is not None for value in core_counts)

        legacy = self.cache_accounting is not None
        benchmark = self.cache_read_status is not None
        if legacy == benchmark:
            raise ValueError("usage shape must be exactly legacy or benchmark")

        if legacy:
            if any(
                value is not None
                for value in (
                    self.cache_read_tokens,
                    self.cache_write_tokens,
                    self.ordinary_uncached_input_tokens,
                    self.reasoning_tokens,
                    self.cache_read_status,
                    self.cache_write_status,
                    self.reasoning_token_accounting,
                )
            ):
                raise ValueError("legacy usage cannot contain benchmark accounting")
            self._validate_core_counts(available_core_counts)
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

        if self.cached_input_tokens is not None or self.cache_accounting is not None:
            raise ValueError("benchmark usage cannot contain legacy accounting")
        if self.cache_write_status is None or self.reasoning_token_accounting is None:
            raise ValueError("benchmark accounting statuses are required")
        self._validate_core_counts(available_core_counts)

        reported = {"reported_zero", "reported_nonzero"}
        for status, count in (
            (self.cache_read_status, self.cache_read_tokens),
            (self.cache_write_status, self.cache_write_tokens),
        ):
            if (status in reported) != (count is not None):
                raise ValueError("cache status/value mismatch")
            if status == "reported_zero" and count != 0:
                raise ValueError("reported_zero requires exact zero")
            if status == "reported_nonzero" and (count is None or count <= 0):
                raise ValueError("reported_nonzero requires a positive count")

        if self.input_tokens is None:
            if (
                self.cache_read_tokens is not None
                or self.cache_write_tokens is not None
                or self.ordinary_uncached_input_tokens is not None
            ):
                raise ValueError("input accounting requires provider input tokens")
        else:
            expected = (
                self.input_tokens - (self.cache_read_tokens or 0) - (self.cache_write_tokens or 0)
            )
            if expected < 0 or self.ordinary_uncached_input_tokens != expected:
                raise ValueError("ordinary uncached input is inconsistent")

        if self.reasoning_token_accounting == "reported":
            if (
                self.reasoning_tokens is None
                or self.output_tokens is None
                or self.reasoning_tokens > self.output_tokens
            ):
                raise ValueError("reported reasoning accounting requires a consistent count")
        elif self.reasoning_tokens is not None:
            raise ValueError("unreported or invalid reasoning accounting forbids a count")
        return self

    def _validate_core_counts(self, available_core_counts: int) -> None:
        if self.availability == "unavailable":
            if available_core_counts != 0:
                raise ValueError("unavailable usage must not contain counts")
        elif self.availability == "partial":
            if available_core_counts not in (1, 2):
                raise ValueError("partial usage requires one or two core counts")
        elif (
            available_core_counts != 3
            or self.total_tokens != self.input_tokens + self.output_tokens  # type: ignore[operator]
        ):
            raise ValueError("complete usage requires consistent core counts")

    @model_serializer(mode="wrap")
    def serialize_accounting_shape(self, handler: object) -> object:
        payload = handler(self)  # type: ignore[operator]
        if not isinstance(payload, dict):  # pragma: no cover - Pydantic contract
            return payload
        if self.cache_accounting is not None:
            for field_name in (
                "cache_read_tokens",
                "cache_write_tokens",
                "ordinary_uncached_input_tokens",
                "reasoning_tokens",
                "cache_read_status",
                "cache_write_status",
                "reasoning_token_accounting",
            ):
                payload.pop(field_name, None)
        else:
            payload.pop("cached_input_tokens", None)
            payload.pop("cache_accounting", None)
        return payload


PublicBenchmarkRawResponsePathV1: TypeAlias = Literal[
    "response.id",
    "response.status",
    "response.error",
    "response.output",
    "response.model",
    "response.service_tier",
    "response.prompt_cache_options.mode",
    "response.prompt_cache_options.ttl",
    "response.usage.input_tokens",
    "response.usage.input_tokens_details.cached_tokens",
    "response.usage.input_tokens_details.cache_write_tokens",
    "response.usage.output_tokens",
    "response.usage.output_tokens_details.reasoning_tokens",
    "response.usage.total_tokens",
]
_PUBLIC_BENCHMARK_RAW_RESPONSE_PATHS: tuple[str, ...] = (
    "response.id",
    "response.status",
    "response.error",
    "response.output",
    "response.model",
    "response.service_tier",
    "response.prompt_cache_options.mode",
    "response.prompt_cache_options.ttl",
    "response.usage.input_tokens",
    "response.usage.input_tokens_details.cached_tokens",
    "response.usage.input_tokens_details.cache_write_tokens",
    "response.usage.output_tokens",
    "response.usage.output_tokens_details.reasoning_tokens",
    "response.usage.total_tokens",
)
_PUBLIC_BENCHMARK_SOURCE_DIGEST_FIELDS: tuple[str, ...] = (
    "returned_model_source_sha256",
    "service_tier_source_sha256",
    "applied_cache_control_source_sha256",
    "cache_read_source_sha256",
    "cache_write_source_sha256",
    "usage_source_sha256",
    "reasoning_tokens_source_sha256",
)
_PUBLIC_BENCHMARK_ERROR_DIGEST_EXCLUDES = frozenset(
    {"error_source_sha256", *_PUBLIC_BENCHMARK_SOURCE_DIGEST_FIELDS}
)


def _project_public_benchmark_source_value(
    value: object,
    *,
    depth: int = 0,
    active: set[int] | None = None,
) -> object:
    """Project one SDK value into the exact bounded JSON-tree surface."""

    if active is None:
        active = set()
    if depth > RESOURCE_LIMITS_V1.nesting_depth:
        raise ValueError("raw response source is too deeply nested")
    if isinstance(value, BaseModel):
        try:
            value = BaseModel.model_dump(
                value,
                mode="json",
                round_trip=False,
                warnings=False,
            )
        except Exception:
            raise ValueError("raw response model projection failed") from None
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("raw response source contains a nonfinite number")
        return value
    if type(value) is str:
        bounded_utf8_length(
            value,
            limit=RESOURCE_LIMITS_V1.raw_jsonl_row_bytes,
            code="raw_jsonl_row_limit",
        )
        return value
    if type(value) not in (dict, list, tuple):
        raise ValueError("unsupported raw response source value")
    identity = id(value)
    if identity in active:
        raise ValueError("cyclic raw response source")
    active.add(identity)
    try:
        if type(value) is dict:
            projected: dict[str, object] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("raw response source keys must be exact strings")
                projected[key] = _project_public_benchmark_source_value(
                    item,
                    depth=depth + 1,
                    active=active,
                )
            return projected
        sequence = cast(list[object] | tuple[object, ...], value)
        return [
            _project_public_benchmark_source_value(
                item,
                depth=depth + 1,
                active=active,
            )
            for item in sequence
        ]
    finally:
        active.remove(identity)


class PublicBenchmarkRawResponseSourceEntryV1(CapsuleModel):
    path: PublicBenchmarkRawResponsePathV1
    present: StrictBool
    value: object

    @field_validator("value", mode="before")
    @classmethod
    def validate_source_value(cls, value: object) -> object:
        return _project_public_benchmark_source_value(value)

    @model_validator(mode="after")
    def validate_presence_relation(self) -> Self:
        if not self.present and self.value is not None:
            raise ValueError("missing raw response paths require null values")
        return self


class PublicBenchmarkRawResponseSourceV1(CapsuleModel):
    schema_version: Literal["PublicBenchmarkRawResponseSourceV1"]
    entries: tuple[PublicBenchmarkRawResponseSourceEntryV1, ...]

    @model_validator(mode="after")
    def validate_exact_projection(self) -> Self:
        if tuple(entry.path for entry in self.entries) != _PUBLIC_BENCHMARK_RAW_RESPONSE_PATHS:
            raise ValueError("raw response paths are not exact and ordered")
        payload = PublicBenchmarkRawResponseSourceV1.model_dump(
            self,
            mode="json",
            round_trip=True,
            warnings=False,
        )
        if len(canonical_json(payload)) > RESOURCE_LIMITS_V1.raw_jsonl_row_bytes:
            raise ValueError("raw response source exceeds its byte bound")
        return self


def public_benchmark_raw_response_sha256(
    source: PublicBenchmarkRawResponseSourceV1,
) -> str:
    """Digest one strictly revalidated typed SDK projection."""

    if type(source) is not PublicBenchmarkRawResponseSourceV1:
        raise ValueError("raw response source type mismatch")
    payload = PublicBenchmarkRawResponseSourceV1.model_dump(
        source,
        mode="python",
        round_trip=True,
        warnings=False,
    )
    checked = PublicBenchmarkRawResponseSourceV1.model_validate(payload)
    return stable_digest(
        "laconian-public-benchmark-raw-response-source-v1",
        PublicBenchmarkRawResponseSourceV1.model_dump(
            checked,
            mode="json",
            round_trip=True,
            warnings=False,
        ),
    )


def _raw_source_entries(
    source: PublicBenchmarkRawResponseSourceV1,
) -> dict[str, PublicBenchmarkRawResponseSourceEntryV1]:
    return {entry.path: entry for entry in source.entries}


def _bounded_source_metadata(
    entry: PublicBenchmarkRawResponseSourceEntryV1,
) -> str | None:
    if not entry.present or entry.value is None:
        return None
    try:
        return _provider_metadata(entry.value)
    except Exception:
        return None


def _source_count(entry: PublicBenchmarkRawResponseSourceEntryV1) -> int | None:
    value = entry.value
    if not entry.present or value is None or type(value) is not int or value < 0:
        return None
    return value


def _derive_received_service_tier_status(
    returned_service_tier: str | None,
) -> ServiceTierStatus:
    if returned_service_tier == "default":
        return "reported_default"
    if returned_service_tier is not None:
        return "mismatch"
    return "missing"


def _derive_applied_cache_evidence(
    source: PublicBenchmarkRawResponseSourceV1,
) -> tuple[str | None, str | None, AppliedCacheControlStatus]:
    entries = _raw_source_entries(source)
    mode_entry = entries["response.prompt_cache_options.mode"]
    ttl_entry = entries["response.prompt_cache_options.ttl"]
    mode = _bounded_source_metadata(mode_entry)
    ttl = _bounded_source_metadata(ttl_entry)
    invalid = (mode_entry.present and mode_entry.value is not None and mode is None) or (
        ttl_entry.present and ttl_entry.value is not None and ttl is None
    )
    if invalid:
        status: AppliedCacheControlStatus = "invalid"
    elif (
        not mode_entry.present
        or mode_entry.value is None
        or not ttl_entry.present
        or ttl_entry.value is None
    ):
        status = "missing"
    elif mode == "explicit" and ttl == "30m":
        status = "reported_exact"
    else:
        status = "mismatch"
    return mode, ttl, status


def _usage_from_raw_source(source: PublicBenchmarkRawResponseSourceV1) -> AttemptUsageV2:
    entries = _raw_source_entries(source)
    input_tokens = _source_count(entries["response.usage.input_tokens"])
    output_tokens = _source_count(entries["response.usage.output_tokens"])
    total_tokens = _source_count(entries["response.usage.total_tokens"])
    if (
        input_tokens is not None
        and output_tokens is not None
        and total_tokens is not None
        and total_tokens != input_tokens + output_tokens
    ):
        total_tokens = None

    cache_values: list[int | None] = []
    cache_statuses: list[CacheReadStatus | CacheWriteStatus] = []
    for path in (
        "response.usage.input_tokens_details.cached_tokens",
        "response.usage.input_tokens_details.cache_write_tokens",
    ):
        entry = entries[path]
        count = _source_count(entry)
        if not entry.present or entry.value is None:
            status: CacheReadStatus | CacheWriteStatus = "missing"
        elif count is None or input_tokens is None or count > input_tokens:
            status = "invalid"
            count = None
        elif count == 0:
            status = "reported_zero"
        else:
            status = "reported_nonzero"
        cache_values.append(count)
        cache_statuses.append(status)
    if (
        input_tokens is not None
        and cache_values[0] is not None
        and cache_values[1] is not None
        and cache_values[0] + cache_values[1] > input_tokens
    ):
        cache_values = [None, None]
        cache_statuses = ["invalid", "invalid"]

    reasoning_entry = entries["response.usage.output_tokens_details.reasoning_tokens"]
    reasoning_tokens = _source_count(reasoning_entry)
    if not reasoning_entry.present or reasoning_entry.value is None:
        reasoning_accounting: ReasoningTokenAccounting = "not_reported"
    elif reasoning_tokens is None or output_tokens is None or reasoning_tokens > output_tokens:
        reasoning_tokens = None
        reasoning_accounting = "invalid"
    else:
        reasoning_accounting = "reported"

    available_core_counts = sum(
        value is not None for value in (input_tokens, output_tokens, total_tokens)
    )
    if available_core_counts == 3:
        availability: UsageAvailability = "complete"
    elif available_core_counts:
        availability = "partial"
    else:
        availability = "unavailable"
    ordinary_uncached_input_tokens = (
        None
        if input_tokens is None
        else input_tokens - (cache_values[0] or 0) - (cache_values[1] or 0)
    )
    return AttemptUsageV2(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cache_read_tokens=cache_values[0],
        cache_write_tokens=cache_values[1],
        ordinary_uncached_input_tokens=ordinary_uncached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        availability=availability,
        source="provider",
        cache_read_status=cache_statuses[0],
        cache_write_status=cache_statuses[1],
        reasoning_token_accounting=reasoning_accounting,
    )


def _output_text_from_raw_source(source: PublicBenchmarkRawResponseSourceV1) -> str:
    entry = _raw_source_entries(source)["response.output"]
    if not entry.present or type(entry.value) is not list:
        raise ValueError("response output is missing or malformed")
    pieces: list[str] = []
    for item in entry.value:
        if type(item) is not dict or type(item.get("type")) is not str:
            raise ValueError("response output item is malformed")
        if item["type"] != "message":
            continue
        content = item.get("content")
        if type(content) is not list:
            raise ValueError("response message content is malformed")
        for part in content:
            if type(part) is not dict or type(part.get("type")) is not str:
                raise ValueError("response content item is malformed")
            if part["type"] != "output_text":
                continue
            text = part.get("text")
            if type(text) is not str:
                raise ValueError("response output text is malformed")
            pieces.append(text)
    return _output_string("".join(pieces))


def _raw_source_has_usable_completed_output(
    source: PublicBenchmarkRawResponseSourceV1,
) -> bool:
    entries = _raw_source_entries(source)
    response_id = _bounded_source_metadata(entries["response.id"])
    status = entries["response.status"]
    error = entries["response.error"]
    if (
        response_id is None
        or not status.present
        or type(status.value) is not str
        or status.value != "completed"
        or (error.present and error.value is not None)
    ):
        return False
    try:
        _output_text_from_raw_source(source)
    except (TypeError, ValueError, UnicodeError):
        return False
    return True


def _validate_received_evidence_against_source(
    *,
    source: PublicBenchmarkRawResponseSourceV1,
    response_id: str | None,
    usage: AttemptUsageV2,
    returned_model_id: str | None,
    returned_service_tier: str | None,
    service_tier_status: ServiceTierStatus,
    applied_prompt_cache_mode: str | None,
    applied_prompt_cache_ttl: str | None,
    applied_cache_control_status: AppliedCacheControlStatus,
) -> None:
    entries = _raw_source_entries(source)
    expected_response_id = _bounded_source_metadata(entries["response.id"])
    expected_model_id = _bounded_source_metadata(entries["response.model"])
    expected_tier = _bounded_source_metadata(entries["response.service_tier"])
    expected_mode, expected_ttl, expected_applied_status = _derive_applied_cache_evidence(source)
    if response_id != expected_response_id:
        raise ValueError("response identifier does not match its source")
    if returned_model_id != expected_model_id:
        raise ValueError("returned model does not match its source")
    if returned_service_tier != expected_tier:
        raise ValueError("returned service tier does not match its source")
    if service_tier_status != _derive_received_service_tier_status(expected_tier):
        raise ValueError("service tier status does not match its source")
    if (
        applied_prompt_cache_mode != expected_mode
        or applied_prompt_cache_ttl != expected_ttl
        or applied_cache_control_status != expected_applied_status
    ):
        raise ValueError("applied cache control does not match its source")
    expected_usage = _usage_from_raw_source(source)
    if usage.model_dump(mode="json") != expected_usage.model_dump(mode="json"):
        raise ValueError("provider usage does not match its source")


class PublicBenchmarkResponseEvidenceV1(CapsuleModel):
    schema_version: Literal["public-benchmark-response-evidence-v1"]
    response_id: ProviderMetadataString
    raw_response_sha256: Sha256
    output_text: OutputString
    raw_response_source: PublicBenchmarkRawResponseSourceV1
    usage: AttemptUsageV2
    requested_model_id: PublicBenchmarkModelId
    returned_model_id: ProviderMetadataString | None
    returned_model_source_sha256: Sha256
    requested_service_tier: ServiceTier
    returned_service_tier: ProviderMetadataString | None
    service_tier_status: ServiceTierStatus
    service_tier_source_sha256: Sha256
    applied_prompt_cache_mode: ProviderMetadataString | None
    applied_prompt_cache_ttl: ProviderMetadataString | None
    applied_cache_control_status: AppliedCacheControlStatus
    applied_cache_control_source_sha256: Sha256
    cache_read_source_sha256: Sha256
    cache_write_source_sha256: Sha256
    usage_source_sha256: Sha256
    reasoning_tokens_source_sha256: Sha256

    @model_validator(mode="after")
    def validate_response_envelope(self) -> Self:
        raw_digest = public_benchmark_raw_response_sha256(self.raw_response_source)
        if self.raw_response_sha256 != raw_digest:
            raise ValueError("raw response source digest mismatch")
        for field_name in _PUBLIC_BENCHMARK_SOURCE_DIGEST_FIELDS:
            if getattr(self, field_name) != raw_digest:
                raise ValueError("response evidence must use one source envelope")
        _validate_received_evidence_against_source(
            source=self.raw_response_source,
            response_id=self.response_id,
            usage=self.usage,
            returned_model_id=self.returned_model_id,
            returned_service_tier=self.returned_service_tier,
            service_tier_status=self.service_tier_status,
            applied_prompt_cache_mode=self.applied_prompt_cache_mode,
            applied_prompt_cache_ttl=self.applied_prompt_cache_ttl,
            applied_cache_control_status=self.applied_cache_control_status,
        )
        entries = _raw_source_entries(self.raw_response_source)
        status = entries["response.status"]
        error = entries["response.error"]
        if not status.present or type(status.value) is not str or status.value != "completed":
            raise ValueError("response evidence requires a completed response source")
        if error.present and error.value is not None:
            raise ValueError("response evidence forbids a response error")
        if self.output_text != _output_text_from_raw_source(self.raw_response_source):
            raise ValueError("output text does not match the response output tree")
        return self


class PublicBenchmarkProviderErrorEvidenceV1(CapsuleModel):
    schema_version: Literal["public-benchmark-provider-error-evidence-v1"]
    delivery_certainty: DeliveryCertainty
    provider_request_id: ProviderMetadataString | None
    response_id: ProviderMetadataString | None
    raw_response_sha256: Sha256 | None
    raw_response_source: PublicBenchmarkRawResponseSourceV1 | None
    usage: AttemptUsageV2
    requested_model_id: PublicBenchmarkModelId
    returned_model_id: ProviderMetadataString | None
    returned_model_source_sha256: Sha256
    requested_service_tier: ServiceTier
    returned_service_tier: ProviderMetadataString | None
    service_tier_status: ServiceTierStatus
    service_tier_source_sha256: Sha256
    applied_prompt_cache_mode: ProviderMetadataString | None
    applied_prompt_cache_ttl: ProviderMetadataString | None
    applied_cache_control_status: AppliedCacheControlStatus
    applied_cache_control_source_sha256: Sha256
    cache_read_source_sha256: Sha256
    cache_write_source_sha256: Sha256
    usage_source_sha256: Sha256
    reasoning_tokens_source_sha256: Sha256
    structured_status: Annotated[int, Field(strict=True, ge=100, le=599)] | None
    error_source_sha256: Sha256

    @model_validator(mode="after")
    def validate_error_envelope(self) -> Self:
        if (self.raw_response_source is None) != (self.raw_response_sha256 is None):
            raise ValueError("raw response source and digest must form one pair")
        raw_digest: str | None = None
        if self.raw_response_source is not None:
            raw_digest = public_benchmark_raw_response_sha256(self.raw_response_source)
            if self.raw_response_sha256 != raw_digest:
                raise ValueError("raw response source digest mismatch")
        error_digest = public_benchmark_provider_error_source_sha256(self)
        if self.error_source_sha256 != error_digest:
            raise ValueError("provider error source digest mismatch")
        common_digest = raw_digest or error_digest
        for field_name in _PUBLIC_BENCHMARK_SOURCE_DIGEST_FIELDS:
            if getattr(self, field_name) != common_digest:
                raise ValueError("provider error must use one source envelope")

        if self.raw_response_source is not None:
            if self.delivery_certainty != "response_received":
                raise ValueError("a response source proves response receipt")
            _validate_received_evidence_against_source(
                source=self.raw_response_source,
                response_id=self.response_id,
                usage=self.usage,
                returned_model_id=self.returned_model_id,
                returned_service_tier=self.returned_service_tier,
                service_tier_status=self.service_tier_status,
                applied_prompt_cache_mode=self.applied_prompt_cache_mode,
                applied_prompt_cache_ttl=self.applied_prompt_cache_ttl,
                applied_cache_control_status=self.applied_cache_control_status,
            )
            if _raw_source_has_usable_completed_output(self.raw_response_source):
                raise ValueError("provider error evidence hides a usable response")
            return self

        if any(
            value is not None
            for value in (
                self.response_id,
                self.returned_model_id,
                self.returned_service_tier,
                self.applied_prompt_cache_mode,
                self.applied_prompt_cache_ttl,
            )
        ):
            raise ValueError("no-response evidence contains response-derived values")
        if self.usage.availability != "unavailable" or any(
            value is not None
            for value in (
                self.usage.input_tokens,
                self.usage.output_tokens,
                self.usage.total_tokens,
                self.usage.cache_read_tokens,
                self.usage.cache_write_tokens,
                self.usage.ordinary_uncached_input_tokens,
                self.usage.reasoning_tokens,
            )
        ):
            raise ValueError("no-response evidence must have unavailable usage")

        if self.delivery_certainty == "definitely_not_sent":
            expected_status = "not_applicable_definitely_not_sent"
            if self.structured_status is not None:
                raise ValueError("definitely-not-sent evidence forbids a status code")
        elif self.delivery_certainty == "definitely_rejected":
            expected_status = "not_applicable_definitely_rejected"
            if self.structured_status is None:
                raise ValueError("definite rejection requires a structured status")
        elif self.delivery_certainty == "response_received":
            if (
                self.service_tier_status != "missing"
                or self.applied_cache_control_status != "invalid"
                or self.usage.cache_read_status != "invalid"
                or self.usage.cache_write_status != "invalid"
                or self.usage.reasoning_token_accounting != "invalid"
            ):
                raise ValueError("invalid projection-failure evidence")
            return self
        else:
            if (
                self.service_tier_status != "missing"
                or self.applied_cache_control_status != "missing"
                or self.usage.cache_read_status != "missing"
                or self.usage.cache_write_status != "missing"
                or self.usage.reasoning_token_accounting != "not_reported"
            ):
                raise ValueError("invalid unknown-delivery evidence")
            return self

        if (
            self.service_tier_status != expected_status
            or self.applied_cache_control_status != expected_status
            or self.usage.cache_read_status != expected_status
            or self.usage.cache_write_status != expected_status
            or self.usage.reasoning_token_accounting != "not_reported"
        ):
            raise ValueError("not-applicable evidence status mismatch")
        return self


def public_benchmark_provider_error_source_sha256(
    evidence: PublicBenchmarkProviderErrorEvidenceV1 | Mapping[str, object],
) -> str:
    """Digest the exact acyclic provider-error evidence preimage."""

    if type(evidence) is PublicBenchmarkProviderErrorEvidenceV1:
        payload: dict[str, object] = PublicBenchmarkProviderErrorEvidenceV1.model_dump(
            evidence,
            mode="json",
            round_trip=True,
            warnings=False,
        )
    elif type(evidence) is dict:
        payload = dict(evidence)
    else:
        raise ValueError("provider error evidence type mismatch")
    expected_fields = set(PublicBenchmarkProviderErrorEvidenceV1.model_fields)
    if set(payload) != expected_fields:
        raise ValueError("provider error evidence shape mismatch")
    preimage = {
        key: _project_public_benchmark_source_value(value)
        for key, value in payload.items()
        if key not in _PUBLIC_BENCHMARK_ERROR_DIGEST_EXCLUDES
    }
    return stable_digest(
        "laconian-public-benchmark-provider-error-source-v1",
        preimage,
    )


PublicBenchmarkProviderOutcomeV1: TypeAlias = (
    PublicBenchmarkResponseEvidenceV1 | PublicBenchmarkProviderErrorEvidenceV1
)


class PublicBenchmarkProvider(Protocol):
    def generate_benchmark(
        self,
        request: PublicBenchmarkRequestV1,
    ) -> PublicBenchmarkProviderOutcomeV1: ...


def visible_output_tokens(usage: AttemptUsageV2) -> int | None:
    if usage.output_tokens is None or usage.reasoning_token_accounting != "reported":
        return None
    if usage.reasoning_tokens is None:
        return None
    return usage.output_tokens - usage.reasoning_tokens


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
    requested_model_id: PublicBenchmarkModelId | None
    returned_model_id: str | None
    returned_model_source_sha256: str | None
    requested_service_tier: ServiceTier | None
    returned_service_tier: str | None
    service_tier_status: ServiceTierStatus | None
    service_tier_source_sha256: str | None
    applied_prompt_cache_mode: str | None
    applied_prompt_cache_ttl: str | None
    applied_cache_control_status: AppliedCacheControlStatus | None
    applied_cache_control_source_sha256: str | None
    cache_read_source_sha256: str | None
    cache_write_source_sha256: str | None
    usage_source_sha256: str | None
    reasoning_tokens_source_sha256: str | None
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
        requested_model_id=None,
        returned_model_id=None,
        returned_model_source_sha256=None,
        requested_service_tier=None,
        returned_service_tier=None,
        service_tier_status=None,
        service_tier_source_sha256=None,
        applied_prompt_cache_mode=None,
        applied_prompt_cache_ttl=None,
        applied_cache_control_status=None,
        applied_cache_control_source_sha256=None,
        cache_read_source_sha256=None,
        cache_write_source_sha256=None,
        usage_source_sha256=None,
        reasoning_tokens_source_sha256=None,
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
            requested_model_id=None,
            returned_model_id=None,
            returned_model_source_sha256=None,
            requested_service_tier=None,
            returned_service_tier=None,
            service_tier_status=None,
            service_tier_source_sha256=None,
            applied_prompt_cache_mode=None,
            applied_prompt_cache_ttl=None,
            applied_cache_control_status=None,
            applied_cache_control_source_sha256=None,
            cache_read_source_sha256=None,
            cache_write_source_sha256=None,
            usage_source_sha256=None,
            reasoning_tokens_source_sha256=None,
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
        requested_model_id=None,
        returned_model_id=None,
        returned_model_source_sha256=None,
        requested_service_tier=None,
        returned_service_tier=None,
        service_tier_status=None,
        service_tier_source_sha256=None,
        applied_prompt_cache_mode=None,
        applied_prompt_cache_ttl=None,
        applied_cache_control_status=None,
        applied_cache_control_source_sha256=None,
        cache_read_source_sha256=None,
        cache_write_source_sha256=None,
        usage_source_sha256=None,
        reasoning_tokens_source_sha256=None,
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
        requested_model_id=None,
        returned_model_id=None,
        returned_model_source_sha256=None,
        requested_service_tier=None,
        returned_service_tier=None,
        service_tier_status=None,
        service_tier_source_sha256=None,
        applied_prompt_cache_mode=None,
        applied_prompt_cache_ttl=None,
        applied_cache_control_status=None,
        applied_cache_control_source_sha256=None,
        cache_read_source_sha256=None,
        cache_write_source_sha256=None,
        usage_source_sha256=None,
        reasoning_tokens_source_sha256=None,
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


def _strict_public_benchmark_outcome(
    outcome: PublicBenchmarkProviderOutcomeV1,
) -> PublicBenchmarkProviderOutcomeV1:
    if type(outcome) is PublicBenchmarkResponseEvidenceV1:
        payload = PublicBenchmarkResponseEvidenceV1.model_dump(
            outcome,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        source = PublicBenchmarkRawResponseSourceV1.model_validate(payload["raw_response_source"])
        entries = _raw_source_entries(source)
        mode, ttl, applied_status = _derive_applied_cache_evidence(source)
        payload.update(
            response_id=_bounded_source_metadata(entries["response.id"]),
            output_text=_output_text_from_raw_source(source),
            usage=_usage_from_raw_source(source).model_dump(mode="python"),
            returned_model_id=_bounded_source_metadata(entries["response.model"]),
            returned_service_tier=_bounded_source_metadata(entries["response.service_tier"]),
            applied_prompt_cache_mode=mode,
            applied_prompt_cache_ttl=ttl,
            applied_cache_control_status=applied_status,
        )
        payload["service_tier_status"] = _derive_received_service_tier_status(
            payload["returned_service_tier"]
        )
        return PublicBenchmarkResponseEvidenceV1.model_validate(payload)
    if type(outcome) is PublicBenchmarkProviderErrorEvidenceV1:
        payload = PublicBenchmarkProviderErrorEvidenceV1.model_dump(
            outcome,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        source_payload = payload["raw_response_source"]
        if source_payload is not None:
            source = PublicBenchmarkRawResponseSourceV1.model_validate(source_payload)
            entries = _raw_source_entries(source)
            mode, ttl, applied_status = _derive_applied_cache_evidence(source)
            payload.update(
                response_id=_bounded_source_metadata(entries["response.id"]),
                usage=_usage_from_raw_source(source).model_dump(mode="python"),
                returned_model_id=_bounded_source_metadata(entries["response.model"]),
                returned_service_tier=_bounded_source_metadata(entries["response.service_tier"]),
                applied_prompt_cache_mode=mode,
                applied_prompt_cache_ttl=ttl,
                applied_cache_control_status=applied_status,
            )
            payload["service_tier_status"] = _derive_received_service_tier_status(
                payload["returned_service_tier"]
            )
        else:
            certainty = payload["delivery_certainty"]
            no_source_cache_status: CacheReadStatus
            no_source_service_status: ServiceTierStatus
            no_source_applied_status: AppliedCacheControlStatus
            no_source_reasoning_status: ReasoningTokenAccounting
            if certainty == "definitely_not_sent":
                no_source_cache_status = "not_applicable_definitely_not_sent"
                no_source_service_status = "not_applicable_definitely_not_sent"
                no_source_applied_status = "not_applicable_definitely_not_sent"
                no_source_reasoning_status = "not_reported"
            elif certainty == "definitely_rejected":
                no_source_cache_status = "not_applicable_definitely_rejected"
                no_source_service_status = "not_applicable_definitely_rejected"
                no_source_applied_status = "not_applicable_definitely_rejected"
                no_source_reasoning_status = "not_reported"
            elif certainty == "response_received":
                no_source_cache_status = "invalid"
                no_source_service_status = "missing"
                no_source_applied_status = "invalid"
                no_source_reasoning_status = "invalid"
            else:
                no_source_cache_status = "missing"
                no_source_service_status = "missing"
                no_source_applied_status = "missing"
                no_source_reasoning_status = "not_reported"
            payload.update(
                response_id=None,
                returned_model_id=None,
                returned_service_tier=None,
                service_tier_status=no_source_service_status,
                applied_prompt_cache_mode=None,
                applied_prompt_cache_ttl=None,
                applied_cache_control_status=no_source_applied_status,
                usage=AttemptUsageV2(
                    input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    cache_read_tokens=None,
                    cache_write_tokens=None,
                    ordinary_uncached_input_tokens=None,
                    reasoning_tokens=None,
                    availability="unavailable",
                    source="provider",
                    cache_read_status=no_source_cache_status,
                    cache_write_status=no_source_cache_status,
                    reasoning_token_accounting=no_source_reasoning_status,
                ).model_dump(mode="python"),
            )
        return PublicBenchmarkProviderErrorEvidenceV1.model_validate(payload)
    raise AttemptEvidenceError("invalid_public_benchmark_evidence")


def _benchmark_error_kind_and_retryable(
    evidence: PublicBenchmarkProviderErrorEvidenceV1,
) -> tuple[str, bool]:
    status = evidence.structured_status
    if status in (401, 403):
        return "authentication", False
    if status == 429:
        return "rate_limit", True
    if status in (408, 409, 425) or (status is not None and status >= 500):
        return "provider_error", True
    if evidence.delivery_certainty == "response_received":
        return "malformed_response", False
    return "provider_error", False


def _normalized_benchmark_common(
    checked: PublicBenchmarkResponseEvidenceV1 | PublicBenchmarkProviderErrorEvidenceV1,
    *,
    requested_service_tier: ServiceTier,
    patterns: SanitizerPatterns,
) -> dict[str, object]:
    """Drop unsafe provider metadata and re-derive every affected public status."""

    returned_model_id, _returned_model_is_safe = _normalize_provider_metadata(
        checked.returned_model_id,
        patterns=patterns,
    )
    returned_service_tier, returned_tier_is_safe = _normalize_provider_metadata(
        checked.returned_service_tier,
        patterns=patterns,
    )
    applied_mode, applied_mode_is_safe = _normalize_provider_metadata(
        checked.applied_prompt_cache_mode,
        patterns=patterns,
    )
    applied_ttl, applied_ttl_is_safe = _normalize_provider_metadata(
        checked.applied_prompt_cache_ttl,
        patterns=patterns,
    )

    delivery_certainty: DeliveryCertainty = (
        "response_received"
        if type(checked) is PublicBenchmarkResponseEvidenceV1
        else cast(
            PublicBenchmarkProviderErrorEvidenceV1,
            checked,
        ).delivery_certainty
    )
    if delivery_certainty == "definitely_not_sent":
        service_tier_status: ServiceTierStatus = "not_applicable_definitely_not_sent"
        applied_status: AppliedCacheControlStatus = "not_applicable_definitely_not_sent"
    elif delivery_certainty == "definitely_rejected":
        service_tier_status = "not_applicable_definitely_rejected"
        applied_status = "not_applicable_definitely_rejected"
    else:
        if not returned_tier_is_safe or returned_service_tier is None:
            service_tier_status = "missing"
        elif returned_service_tier == "default":
            service_tier_status = "reported_default"
        else:
            service_tier_status = "mismatch"

        projection_failed = (
            type(checked) is PublicBenchmarkProviderErrorEvidenceV1
            and delivery_certainty == "response_received"
            and checked.raw_response_source is None
        )
        if not applied_mode_is_safe or not applied_ttl_is_safe or projection_failed:
            applied_status = "invalid"
        elif applied_mode is None or applied_ttl is None:
            applied_status = "missing"
        elif applied_mode == "explicit" and applied_ttl == "30m":
            applied_status = "reported_exact"
        else:
            applied_status = "mismatch"

    return {
        "requested_model_id": checked.requested_model_id,
        "returned_model_id": returned_model_id,
        "returned_model_source_sha256": checked.returned_model_source_sha256,
        "requested_service_tier": requested_service_tier,
        "returned_service_tier": returned_service_tier,
        "service_tier_status": service_tier_status,
        "service_tier_source_sha256": checked.service_tier_source_sha256,
        "applied_prompt_cache_mode": applied_mode,
        "applied_prompt_cache_ttl": applied_ttl,
        "applied_cache_control_status": applied_status,
        "applied_cache_control_source_sha256": checked.applied_cache_control_source_sha256,
        "cache_read_source_sha256": checked.cache_read_source_sha256,
        "cache_write_source_sha256": checked.cache_write_source_sha256,
        "usage_source_sha256": checked.usage_source_sha256,
        "reasoning_tokens_source_sha256": checked.reasoning_tokens_source_sha256,
    }


def normalize_public_benchmark_outcome(
    outcome: PublicBenchmarkProviderOutcomeV1,
    *,
    requested_service_tier: ServiceTier,
    patterns: SanitizerPatterns,
) -> NormalizedProviderEvidenceV2:
    """Validate, sanitize, and drop every ephemeral benchmark source tree."""

    if type(requested_service_tier) is not str or requested_service_tier != "default":
        raise AttemptEvidenceError("invalid_public_benchmark_evidence")
    checked = _strict_public_benchmark_outcome(outcome)
    if (
        type(checked.requested_service_tier) is not str
        or checked.requested_service_tier != requested_service_tier
    ):
        raise AttemptEvidenceError("invalid_public_benchmark_evidence")
    common = _normalized_benchmark_common(
        checked,
        requested_service_tier=requested_service_tier,
        patterns=patterns,
    )
    if type(checked) is PublicBenchmarkResponseEvidenceV1:
        request_id, _request_id_is_safe = _normalize_provider_metadata(
            checked.response_id,
            patterns=patterns,
        )
        returned_model_id = cast(str | None, common["returned_model_id"])
        try:
            output = sanitize_output(checked.output_text, patterns=patterns)
        except (SanitizerError, TypeError, ValueError, UnicodeError):
            output = None
        if (
            type(output) is SanitizedOutput
            and output.text is not None
            and output.byte_length <= RESOURCE_LIMITS_V1.output_utf8_bytes
        ):
            return NormalizedProviderEvidenceV2(
                delivery_certainty="response_received",
                output=output,
                **common,  # type: ignore[arg-type]
                response_model=returned_model_id,
                request_id=request_id,
                finish_reason=None,
                usage=checked.usage,
                error=None,
            )
        if (
            type(output) is SanitizedOutput
            and output.text is None
            and output.byte_length > RESOURCE_LIMITS_V1.output_utf8_bytes
        ):
            return NormalizedProviderEvidenceV2(
                delivery_certainty="response_received",
                output=output,
                **common,  # type: ignore[arg-type]
                response_model=returned_model_id,
                request_id=request_id,
                finish_reason=None,
                usage=checked.usage,
                error=AttemptErrorV2(
                    kind="response_too_large",
                    message="response_too_large",
                    retryable=False,
                    request_id=request_id,
                ),
            )
        return NormalizedProviderEvidenceV2(
            delivery_certainty="response_received",
            output=output if type(output) is SanitizedOutput else None,
            **common,  # type: ignore[arg-type]
            response_model=returned_model_id,
            request_id=request_id,
            finish_reason=None,
            usage=checked.usage,
            error=AttemptErrorV2(
                kind="malformed_response",
                message="malformed_response",
                retryable=False,
                request_id=request_id,
            ),
        )

    if type(checked) is not PublicBenchmarkProviderErrorEvidenceV1:
        raise AttemptEvidenceError("invalid_public_benchmark_evidence")
    error_checked = checked
    request_id, _request_id_is_safe = _normalize_provider_metadata(
        error_checked.provider_request_id,
        patterns=patterns,
    )
    returned_model_id = cast(str | None, common["returned_model_id"])
    kind, retryable = _benchmark_error_kind_and_retryable(error_checked)
    return NormalizedProviderEvidenceV2(
        delivery_certainty=error_checked.delivery_certainty,
        output=None,
        **common,  # type: ignore[arg-type]
        response_model=returned_model_id,
        request_id=request_id,
        finish_reason=None,
        usage=error_checked.usage,
        error=AttemptErrorV2(
            kind=kind,
            message=kind,
            retryable=retryable,
            request_id=request_id,
        ),
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
    requested_model_id: PublicBenchmarkModelId | None = None
    returned_model_id: ProviderMetadataString | None = None
    returned_model_source_sha256: Sha256 | None = None
    requested_service_tier: ServiceTier | None = None
    returned_service_tier: ProviderMetadataString | None = None
    service_tier_status: ServiceTierStatus | None = None
    service_tier_source_sha256: Sha256 | None = None
    applied_prompt_cache_mode: ProviderMetadataString | None = None
    applied_prompt_cache_ttl: ProviderMetadataString | None = None
    applied_cache_control_status: AppliedCacheControlStatus | None = None
    applied_cache_control_source_sha256: Sha256 | None = None
    cache_read_source_sha256: Sha256 | None = None
    cache_write_source_sha256: Sha256 | None = None
    usage_source_sha256: Sha256 | None = None
    reasoning_tokens_source_sha256: Sha256 | None = None
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

        self._validate_benchmark_evidence()

        if self.error is None:
            self._validate_success()
        else:
            self._validate_error()
        return self

    def _validate_benchmark_evidence(self) -> None:
        benchmark_values = (
            self.requested_model_id,
            self.returned_model_id,
            self.returned_model_source_sha256,
            self.requested_service_tier,
            self.returned_service_tier,
            self.service_tier_status,
            self.service_tier_source_sha256,
            self.applied_prompt_cache_mode,
            self.applied_prompt_cache_ttl,
            self.applied_cache_control_status,
            self.applied_cache_control_source_sha256,
            self.cache_read_source_sha256,
            self.cache_write_source_sha256,
            self.usage_source_sha256,
            self.reasoning_tokens_source_sha256,
        )
        if self.requested_model_id is None:
            if any(value is not None for value in benchmark_values):
                raise ValueError("legacy attempt contains partial benchmark evidence")
            if self.usage.cache_accounting is None:
                raise ValueError("legacy attempt requires legacy usage evidence")
            return

        required_values = (
            self.returned_model_source_sha256,
            self.requested_service_tier,
            self.service_tier_status,
            self.service_tier_source_sha256,
            self.applied_cache_control_status,
            self.applied_cache_control_source_sha256,
            self.cache_read_source_sha256,
            self.cache_write_source_sha256,
            self.usage_source_sha256,
            self.reasoning_tokens_source_sha256,
        )
        if any(value is None for value in required_values):
            raise ValueError("benchmark attempt evidence is incomplete")
        if self.usage.cache_accounting is not None:
            raise ValueError("benchmark attempt requires benchmark usage evidence")
        if self.model != self.requested_model_id:
            raise ValueError("requested model evidence mismatch")
        if self.response_model != self.returned_model_id:
            raise ValueError("returned model evidence mismatch")
        source_digests = (
            self.returned_model_source_sha256,
            self.service_tier_source_sha256,
            self.applied_cache_control_source_sha256,
            self.cache_read_source_sha256,
            self.cache_write_source_sha256,
            self.usage_source_sha256,
            self.reasoning_tokens_source_sha256,
        )
        if len(set(source_digests)) != 1:
            raise ValueError("benchmark evidence must use one source envelope")

        tier_status = self.service_tier_status
        if tier_status == "reported_default":
            if (
                self.delivery_certainty != "response_received"
                or self.returned_service_tier != "default"
            ):
                raise ValueError("reported default tier evidence mismatch")
        elif tier_status == "mismatch":
            if (
                self.delivery_certainty != "response_received"
                or self.returned_service_tier is None
                or self.returned_service_tier == "default"
            ):
                raise ValueError("mismatched tier evidence mismatch")
        elif tier_status == "missing":
            if (
                self.delivery_certainty not in ("response_received", "unknown")
                or self.returned_service_tier is not None
            ):
                raise ValueError("missing tier evidence mismatch")
        elif tier_status in (
            "not_applicable_definitely_not_sent",
            "not_applicable_definitely_rejected",
        ):
            expected_certainty = (
                "definitely_not_sent"
                if tier_status == "not_applicable_definitely_not_sent"
                else "definitely_rejected"
            )
            if (
                self.delivery_certainty != expected_certainty
                or self.returned_service_tier is not None
                or self.returned_model_id is not None
                or self.usage.availability != "unavailable"
            ):
                raise ValueError("not-applicable tier evidence mismatch")
        else:  # pragma: no cover - Literal narrows every valid status
            raise ValueError("unknown service tier status")

        applied_status = self.applied_cache_control_status
        if applied_status == "reported_exact":
            if (
                self.applied_prompt_cache_mode != "explicit"
                or self.applied_prompt_cache_ttl != "30m"
            ):
                raise ValueError("reported cache control evidence mismatch")
        elif applied_status == "mismatch":
            if (
                self.applied_prompt_cache_mode is None
                or self.applied_prompt_cache_ttl is None
                or (
                    self.applied_prompt_cache_mode == "explicit"
                    and self.applied_prompt_cache_ttl == "30m"
                )
            ):
                raise ValueError("mismatched cache control evidence mismatch")
        elif applied_status == "missing":
            if (
                self.applied_prompt_cache_mode is not None
                and self.applied_prompt_cache_ttl is not None
            ):
                raise ValueError("missing cache control evidence mismatch")
        elif applied_status == "invalid":
            if self.delivery_certainty not in ("response_received", "unknown"):
                raise ValueError("invalid cache control delivery mismatch")
        elif applied_status in (
            "not_applicable_definitely_not_sent",
            "not_applicable_definitely_rejected",
        ):
            expected_certainty = (
                "definitely_not_sent"
                if applied_status == "not_applicable_definitely_not_sent"
                else "definitely_rejected"
            )
            if (
                self.delivery_certainty != expected_certainty
                or self.applied_prompt_cache_mode is not None
                or self.applied_prompt_cache_ttl is not None
                or self.usage.availability != "unavailable"
            ):
                raise ValueError("not-applicable cache control mismatch")

        for status in (self.usage.cache_read_status, self.usage.cache_write_status):
            if status in (
                "not_applicable_definitely_not_sent",
                "not_applicable_definitely_rejected",
            ):
                expected_certainty = (
                    "definitely_not_sent"
                    if status == "not_applicable_definitely_not_sent"
                    else "definitely_rejected"
                )
                if (
                    self.delivery_certainty != expected_certainty
                    or self.usage.availability != "unavailable"
                ):
                    raise ValueError("not-applicable cache usage mismatch")

    @model_serializer(mode="wrap")
    def serialize_attempt_shape(self, handler: object) -> object:
        payload = handler(self)  # type: ignore[operator]
        if not isinstance(payload, dict):  # pragma: no cover - Pydantic contract
            return payload
        if self.requested_model_id is None:
            for field_name in (
                "requested_model_id",
                "returned_model_id",
                "returned_model_source_sha256",
                "requested_service_tier",
                "returned_service_tier",
                "service_tier_status",
                "service_tier_source_sha256",
                "applied_prompt_cache_mode",
                "applied_prompt_cache_ttl",
                "applied_cache_control_status",
                "applied_cache_control_source_sha256",
                "cache_read_source_sha256",
                "cache_write_source_sha256",
                "usage_source_sha256",
                "reasoning_tokens_source_sha256",
            ):
                payload.pop(field_name, None)
        return payload

    def _validate_success(self) -> None:
        if (
            not self.terminal
            or self.backoff_ms is not None
            or self.delivery_certainty != "response_received"
            or self.output_text is None
            or self.output_sha256 is None
            or self.response_id is None
            or (self.requested_model_id is None and self.response_model is None)
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
