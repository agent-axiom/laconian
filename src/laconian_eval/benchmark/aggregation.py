"""Fixed-population benchmark rows and aggregation denominators."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from laconian_eval.providers import (
    AppliedCacheControlStatus,
    CacheReadStatus,
    CacheWriteStatus,
    ServiceTierStatus,
)

TerminalZeroReason: TypeAlias = Literal[
    "provider_rejected",
    "retry_exhausted",
    "blank_response",
    "hard_fail",
]
ArmName: TypeAlias = Literal["baseline", "caveman", "if", "concise"]
GateName: TypeAlias = Literal["hard", "semantic"]
CachePolicyStatusV1: TypeAlias = Literal[
    "conformant_zero_write",
    "terminal_no_usage",
    "missing_write_detail",
    "forbidden_nonzero_write",
]
CostAvailabilityV1: TypeAlias = Literal[
    "trusted_usage",
    "definitely_rejected_zero",
    "retained_worst_case",
]
CacheIntegrityLimitationV1: TypeAlias = Literal[
    "cache_write_detail_missing",
    "forbidden_cache_write_observed",
]

_ARM_RANK: dict[ArmName, int] = {
    "baseline": 0,
    "caveman": 1,
    "if": 2,
    "concise": 3,
}
_REPORTED_CACHE_STATUSES = frozenset({"reported_zero", "reported_nonzero"})
_NOT_APPLICABLE_STATUSES = frozenset(
    {
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
    }
)


class InferenceIntegrityError(ValueError):
    """Evidence cannot be mapped bijectively to the frozen planned population."""


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class PlannedObservationV1(_StrictFrozenModel):
    """One validated row in the fixed benchmark population."""

    generation_model: str
    scenario_uid: str = Field(pattern="^[0-9a-f]{64}$")
    case_id: str
    locale: str
    repetition: int = Field(ge=0, lt=5)
    arm: ArmName
    response_id: str | None
    hard_pass: bool
    semantic_success: bool
    terminal_zero_reason: TerminalZeroReason | None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_write_tokens: int | None = Field(default=None, ge=0)
    ordinary_uncached_input_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    visible_output_tokens: int | None = Field(default=None, ge=0)
    applied_cache_control_status: AppliedCacheControlStatus
    cache_read_status: CacheReadStatus
    cache_write_status: CacheWriteStatus
    service_tier_status: ServiceTierStatus
    cache_policy_status: CachePolicyStatusV1
    analytical_cost_usd: Decimal = Field(ge=0)
    cost_availability: CostAvailabilityV1
    latency_ms: int | None = Field(default=None, ge=0)
    output_characters: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_terminal_projection(self) -> Self:
        provider_failure = self.terminal_zero_reason in {
            "provider_rejected",
            "retry_exhausted",
        }
        successful_zero = self.terminal_zero_reason in {
            "blank_response",
            "hard_fail",
        }
        if provider_failure:
            response_values = (
                self.input_tokens,
                self.output_tokens,
                self.reasoning_tokens,
                self.cache_read_tokens,
                self.cache_write_tokens,
                self.ordinary_uncached_input_tokens,
                self.total_tokens,
                self.visible_output_tokens,
                self.latency_ms,
                self.output_characters,
            )
            statuses = (
                self.applied_cache_control_status,
                self.cache_read_status,
                self.cache_write_status,
                self.service_tier_status,
            )
            if (
                self.response_id is not None
                or self.hard_pass
                or self.semantic_success
                or any(value is not None for value in response_values)
                or statuses[0] not in _NOT_APPLICABLE_STATUSES
                or any(status != statuses[0] for status in statuses[1:])
                or self.cache_policy_status != "terminal_no_usage"
                or self.analytical_cost_usd != Decimal(0)
                or self.cost_availability != "definitely_rejected_zero"
            ):
                raise ValueError("provider failure projection mismatch")
            return self

        if self.response_id is None:
            raise ValueError("provider success requires response_id")
        if self.output_characters is None:
            raise ValueError("provider response requires output characters")
        if successful_zero:
            if self.hard_pass or self.semantic_success:
                raise ValueError("successful zero projection mismatch")
            return self
        if not self.hard_pass:
            raise ValueError("hard failure requires terminal_zero_reason")
        return self

    @model_validator(mode="after")
    def validate_accounting_projection(self) -> Self:
        cache_fields = (
            (self.cache_read_status, self.cache_read_tokens),
            (self.cache_write_status, self.cache_write_tokens),
        )
        for status, value in cache_fields:
            if status == "reported_zero" and value != 0:
                raise ValueError("reported_zero requires zero")
            if status == "reported_nonzero" and (value is None or value <= 0):
                raise ValueError("reported_nonzero requires a positive count")
            if status not in _REPORTED_CACHE_STATUSES and value is not None:
                raise ValueError("unreported cache status forbids a count")

        complete_cache_detail = all(
            status in _REPORTED_CACHE_STATUSES for status, _ in cache_fields
        )
        if complete_cache_detail:
            if self.input_tokens is None:
                raise ValueError("reported cache components require input tokens")
            assert self.cache_read_tokens is not None
            assert self.cache_write_tokens is not None
            expected_uncached = (
                self.input_tokens - self.cache_read_tokens - self.cache_write_tokens
            )
            if (
                expected_uncached < 0
                or self.ordinary_uncached_input_tokens != expected_uncached
            ):
                raise ValueError("uncached input projection mismatch")
        elif self.ordinary_uncached_input_tokens is not None:
            raise ValueError("uncached input requires complete cache detail")

        if self.output_tokens is None or self.reasoning_tokens is None:
            if self.visible_output_tokens is not None:
                raise ValueError("visible output requires reasoning accounting")
        else:
            if self.reasoning_tokens > self.output_tokens:
                raise ValueError("reasoning tokens exceed output tokens")
            if self.visible_output_tokens != self.output_tokens - self.reasoning_tokens:
                raise ValueError("visible output projection mismatch")

        if self.total_tokens is not None and (
            self.input_tokens is None
            or self.output_tokens is None
            or self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total token projection mismatch")

        if self.response_id is not None and any(
            status in _NOT_APPLICABLE_STATUSES
            for status in (
                self.applied_cache_control_status,
                self.cache_read_status,
                self.cache_write_status,
                self.service_tier_status,
            )
        ):
            raise ValueError("response evidence cannot use a not-applicable source status")

        if self.response_id is not None and self.cache_write_status in {
            "missing",
            "invalid",
        }:
            if (
                self.cache_policy_status != "missing_write_detail"
                or self.cost_availability != "retained_worst_case"
            ):
                raise ValueError(
                    "missing cache-write detail must retain worst-case cost"
                )
        elif self.cache_write_status in _REPORTED_CACHE_STATUSES:
            expected_policy = (
                "conformant_zero_write"
                if self.cache_write_status == "reported_zero"
                else "forbidden_nonzero_write"
            )
            if self.cache_policy_status != expected_policy:
                raise ValueError("cache-write policy status mismatch")
        elif self.response_id is None and self.cache_policy_status != "terminal_no_usage":
            raise ValueError("response-free terminal row requires terminal_no_usage")

        trusted_cost_shape = (
            self.response_id is not None
            and all(
                value is not None
                for value in (
                    self.input_tokens,
                    self.output_tokens,
                    self.total_tokens,
                    self.ordinary_uncached_input_tokens,
                    self.cache_read_tokens,
                    self.cache_write_tokens,
                    self.visible_output_tokens,
                    self.reasoning_tokens,
                )
            )
            and self.applied_cache_control_status == "reported_exact"
            and self.service_tier_status == "reported_default"
            and complete_cache_detail
        )
        if self.response_id is not None:
            expected_cost_availability = (
                "trusted_usage" if trusted_cost_shape else "retained_worst_case"
            )
            if self.cost_availability != expected_cost_availability:
                raise ValueError(
                    "response cost availability does not match accounting shape"
                )
        elif self.cost_availability != "definitely_rejected_zero":
            raise ValueError("response-free row requires definitely rejected zero cost")

        if self.cost_availability == "definitely_rejected_zero" and (
            self.response_id is not None or self.analytical_cost_usd != Decimal(0)
        ):
            raise ValueError("definitely rejected zero-cost projection mismatch")
        return self


class PairDenominatorsV1(_StrictFrozenModel):
    """Matched-pair counts for one gate."""

    planned_pairs: Literal[120] = 120
    eligible_pairs: int = Field(ge=0, le=120)
    token_pairs: int = Field(ge=0, le=120)
    eligible_scenarios: int = Field(ge=0, le=12)

    @model_validator(mode="after")
    def validate_nested_counts(self) -> Self:
        if self.token_pairs > self.eligible_pairs:
            raise ValueError("token pairs must be a subset of eligible pairs")
        if self.eligible_pairs == 0:
            if self.eligible_scenarios != 0:
                raise ValueError("eligible scenarios require eligible pairs")
            return self
        minimum_scenarios = (self.eligible_pairs + 9) // 10
        maximum_scenarios = min(self.eligible_pairs, 12)
        if not minimum_scenarios <= self.eligible_scenarios <= maximum_scenarios:
            raise ValueError("eligible scenario count is impossible")
        return self


class GatePairDenominatorsV1(_StrictFrozenModel):
    """Closed hard and semantic denominator fields."""

    hard: PairDenominatorsV1
    semantic: PairDenominatorsV1


RowKey = tuple[str, str, str, int]


def _row_key(row: PlannedObservationV1) -> RowKey:
    return (row.scenario_uid, row.case_id, row.locale, row.repetition)


def _canonical_row_key(row: PlannedObservationV1) -> tuple[bytes, bytes, bytes, int, int]:
    return (
        bytes.fromhex(row.scenario_uid),
        row.case_id.encode("utf-8"),
        row.locale.encode("utf-8"),
        row.repetition,
        _ARM_RANK[row.arm],
    )


def _validated_exact_rows(rows: Iterable[PlannedObservationV1]) -> tuple[PlannedObservationV1, ...]:
    projected = tuple(rows)
    if any(type(row) is not PlannedObservationV1 for row in projected):
        raise InferenceIntegrityError("rows must be exact PlannedObservationV1 instances")
    return tuple(
        PlannedObservationV1.model_validate(row.model_dump()) for row in projected
    )


def _validate_key_shape(keys: set[RowKey]) -> None:
    scenario_case_ids: dict[str, set[str]] = {}
    scenario_keys: dict[str, set[tuple[str, int]]] = {}
    for scenario_uid, case_id, locale, repetition in keys:
        scenario_case_ids.setdefault(scenario_uid, set()).add(case_id)
        scenario_keys.setdefault(scenario_uid, set()).add((locale, repetition))
    if len(scenario_keys) != 12:
        raise InferenceIntegrityError("planned population must contain exactly 12 scenarios")
    for scenario_uid, locale_repetitions in scenario_keys.items():
        if len(scenario_case_ids[scenario_uid]) != 1:
            raise InferenceIntegrityError("scenario UID must identify exactly one case")
        locales = {locale for locale, _ in locale_repetitions}
        if len(locales) != 2 or any(
            {repetition for candidate, repetition in locale_repetitions if candidate == locale}
            != set(range(5))
            for locale in locales
        ):
            raise InferenceIntegrityError(
                "each scenario requires two locales and five repetitions"
            )


def _validate_population(rows: Sequence[PlannedObservationV1]) -> None:
    if len(rows) != 480:
        raise InferenceIntegrityError("aggregated model requires exactly 480 rows")
    keys_by_arm: dict[ArmName, set[RowKey]] = {}
    for arm in _ARM_RANK:
        arm_rows = [row for row in rows if row.arm == arm]
        if len(arm_rows) != 120:
            raise InferenceIntegrityError(f"arm {arm!r} requires exactly 120 rows")
        keys = {_row_key(row) for row in arm_rows}
        if len(keys) != len(arm_rows):
            raise InferenceIntegrityError(f"arm {arm!r} contains a duplicate key")
        keys_by_arm[arm] = keys
    shared_keys = keys_by_arm["baseline"]
    if any(keys != shared_keys for keys in keys_by_arm.values()):
        raise InferenceIntegrityError("all four arms must share an identical key population")
    _validate_key_shape(shared_keys)


def _require_gate(gate: object) -> GateName:
    if gate == "hard":
        return "hard"
    if gate == "semantic":
        return "semantic"
    raise InferenceIntegrityError("gate must be exactly 'hard' or 'semantic'")


def _gate_pass(row: PlannedObservationV1, gate: GateName) -> bool:
    return row.hard_pass if gate == "hard" else row.semantic_success


def arm_pass_rate(
    rows: Sequence[PlannedObservationV1], *, gate: GateName
) -> Fraction:
    """Return one arm's pass rate over the fixed 120 planned observations."""

    checked_gate = _require_gate(gate)
    checked_rows = _validated_exact_rows(rows)
    if len(checked_rows) != 120 or len({row.arm for row in checked_rows}) != 1:
        raise InferenceIntegrityError("arm pass rate requires exactly one 120-row arm")
    keys = {_row_key(row) for row in checked_rows}
    if len(keys) != 120:
        raise InferenceIntegrityError("arm pass rate requires 120 unique planned keys")
    _validate_key_shape(keys)
    return Fraction(sum(_gate_pass(row, checked_gate) for row in checked_rows), 120)


def pair_denominators_for_gate(
    rows: Sequence[PlannedObservationV1], *, gate: GateName
) -> PairDenominatorsV1:
    """Compute frozen if-versus-concise pair eligibility for one gate."""

    checked_gate = _require_gate(gate)
    checked_rows = _validated_exact_rows(rows)
    rows_by_arm: dict[ArmName, dict[RowKey, PlannedObservationV1]] = {
        "if": {},
        "concise": {},
        "baseline": {},
        "caveman": {},
    }
    for row in checked_rows:
        if _row_key(row) in rows_by_arm[row.arm]:
            raise InferenceIntegrityError(f"arm {row.arm!r} contains a duplicate key")
        rows_by_arm[row.arm][_row_key(row)] = row
    if (
        len(rows_by_arm["if"]) != 120
        or len(rows_by_arm["concise"]) != 120
        or rows_by_arm["if"].keys() != rows_by_arm["concise"].keys()
    ):
        raise InferenceIntegrityError(
            "pair denominators require shared 120-key if and concise populations"
        )
    eligible_keys = {
        key
        for key, if_row in rows_by_arm["if"].items()
        if _gate_pass(if_row, checked_gate)
        and _gate_pass(rows_by_arm["concise"][key], checked_gate)
    }
    token_pairs = sum(
        rows_by_arm["if"][key].visible_output_tokens is not None
        and rows_by_arm["concise"][key].visible_output_tokens is not None
        for key in eligible_keys
    )
    return PairDenominatorsV1(
        planned_pairs=120,
        eligible_pairs=len(eligible_keys),
        token_pairs=token_pairs,
        eligible_scenarios=len({key[0] for key in eligible_keys}),
    )


def cache_integrity_limitations(
    rows: Iterable[PlannedObservationV1],
) -> tuple[CacheIntegrityLimitationV1, ...]:
    """Return the exact ordered cache-integrity limitations present in rows."""

    policies = {row.cache_policy_status for row in _validated_exact_rows(rows)}
    limitations: list[CacheIntegrityLimitationV1] = []
    if "missing_write_detail" in policies:
        limitations.append("cache_write_detail_missing")
    if "forbidden_nonzero_write" in policies:
        limitations.append("forbidden_cache_write_observed")
    return tuple(limitations)


class AggregatedModelV1(_StrictFrozenModel):
    """One generation model's canonical 480-row aggregate."""

    generation_model: str
    rows: tuple[PlannedObservationV1, ...]
    denominators_by_gate: GatePairDenominatorsV1
    integrity_limitations: tuple[CacheIntegrityLimitationV1, ...]

    @model_validator(mode="before")
    @classmethod
    def require_exact_row_owner(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            rows = data.get("rows")
            if rows is not None and (
                not isinstance(rows, (tuple, list))
                or any(type(row) is not PlannedObservationV1 for row in rows)
            ):
                raise ValueError("rows must be exact PlannedObservationV1 instances")
        return data

    @model_validator(mode="after")
    def validate_aggregate(self) -> Self:
        checked_rows = _validated_exact_rows(self.rows)
        _validate_population(checked_rows)
        if any(row.generation_model != self.generation_model for row in checked_rows):
            raise ValueError("row generation model does not match aggregate")
        if checked_rows != tuple(sorted(checked_rows, key=_canonical_row_key)):
            raise ValueError("aggregate rows are not in canonical order")
        expected_denominators = GatePairDenominatorsV1(
            hard=pair_denominators_for_gate(checked_rows, gate="hard"),
            semantic=pair_denominators_for_gate(checked_rows, gate="semantic"),
        )
        if self.denominators_by_gate != expected_denominators:
            raise ValueError("gate denominators do not match rows")
        expected_limitations = cache_integrity_limitations(checked_rows)
        if self.integrity_limitations != expected_limitations:
            raise ValueError("cache integrity limitations do not match rows")
        return self


def _build_aggregated_model_from_rows(
    *, generation_model: str, rows: Iterable[PlannedObservationV1]
) -> AggregatedModelV1:
    """Canonicalize already-projected rows without making a provenance claim."""

    checked_rows = _validated_exact_rows(rows)
    _validate_population(checked_rows)
    if any(row.generation_model != generation_model for row in checked_rows):
        raise InferenceIntegrityError("row generation model does not match aggregate")
    canonical_rows = tuple(sorted(checked_rows, key=_canonical_row_key))
    return AggregatedModelV1(
        generation_model=generation_model,
        rows=canonical_rows,
        denominators_by_gate=GatePairDenominatorsV1(
            hard=pair_denominators_for_gate(canonical_rows, gate="hard"),
            semantic=pair_denominators_for_gate(canonical_rows, gate="semantic"),
        ),
        integrity_limitations=cache_integrity_limitations(canonical_rows),
    )


def _sealed_micro_usd_per_million(rate: object) -> int:
    """Seal one USD-per-million rate as integral micro-USD-per-million."""

    try:
        projected = Decimal(str(rate)) * Decimal(1_000_000)
    except (InvalidOperation, ValueError) as exc:
        raise InferenceIntegrityError("rate is not a finite decimal") from exc
    if (
        not projected.is_finite()
        or projected < 0
        or projected != projected.to_integral_value()
    ):
        raise InferenceIntegrityError(
            "rate must project to integral nonnegative micro-USD-per-million"
        )
    return int(projected)


def _checked_cost_components(
    component_tokens: Sequence[int], rates_micro_usd_per_million: Sequence[int]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    tokens = tuple(component_tokens)
    rates = tuple(rates_micro_usd_per_million)
    if (
        len(tokens) != 5
        or len(rates) != 5
        or any(type(value) is not int or value < 0 for value in tokens)
        or any(type(value) is not int or value < 0 for value in rates)
    ):
        raise InferenceIntegrityError(
            "analytical cost requires five nonnegative integer components and rates"
        )
    return tokens, rates


def _trusted_analytical_cost_usd(
    component_tokens: Sequence[int], rates_micro_usd_per_million: Sequence[int]
) -> Decimal:
    """Price five trusted components with five independent micro-USD ceilings."""

    tokens, rates = _checked_cost_components(
        component_tokens, rates_micro_usd_per_million
    )
    micro_usd = sum(
        (token_count * rate + 999_999) // 1_000_000
        for token_count, rate in zip(tokens, rates, strict=True)
    )
    return Decimal(micro_usd) / Decimal(1_000_000)


def _retained_worst_case_analytical_cost_usd(
    rates_micro_usd_per_million: Sequence[int],
) -> Decimal:
    """Price the frozen reservation envelope with one whole-envelope ceiling."""

    _, rates = _checked_cost_components((0, 0, 0, 0, 0), rates_micro_usd_per_million)
    input_rate = max(rates[:3])
    output_rate = max(rates[3:])
    micro_usd = (
        272_000 * input_rate + 1_024 * output_rate + 999_999
    ) // 1_000_000
    return Decimal(micro_usd) / Decimal(1_000_000)


__all__ = (
    "AggregatedModelV1",
    "ArmName",
    "CacheIntegrityLimitationV1",
    "CachePolicyStatusV1",
    "CostAvailabilityV1",
    "GateName",
    "GatePairDenominatorsV1",
    "InferenceIntegrityError",
    "PairDenominatorsV1",
    "PlannedObservationV1",
    "TerminalZeroReason",
    "arm_pass_rate",
    "cache_integrity_limitations",
    "pair_denominators_for_gate",
)
