"""Exact bounded false-fail calculations after external source verification.

Like audit_metrics, this module is a pure calculation boundary, not an evidence
admission API. Callers must verify immutable audit sources first, construct known
false-fails only from audited consensus-pass records, and preserve every other
H=1 judge-fail as optional, including audited consensus-fail records. The aggregate
join here enforces the complete candidate universe but cannot authenticate audits.

Direct enumeration visits one assignment node per evaluated assignment. Certified
search visits the optional-candidate binary tree and prunes only cardinality
violations. An unavailable U defines no authorizing assignment space: inconclusive
results report zero counts and null extrema; K=D is a non-authorizing placeholder.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Context, Decimal, localcontext
from itertools import combinations, pairwise
from typing import Literal, Self, TypeAlias, TypeVar

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from laconian_eval.benchmark.aggregation import (
    AggregatedModelV1,
    PlannedObservationV1,
    _row_key,
)
from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.benchmark.audit_commit_reveal import (
    _AuditModel,
    _exact_model_tuple,
    _exact_value_tuple,
)
from laconian_eval.benchmark.audit_metrics import (
    ModelAuditMetricsV1,
    _load_json_decimal,
    _reload,
)
from laconian_eval.benchmark.bootstrap import (
    BOOTSTRAP_MIN_VALID,
    BootstrapIntervalV1,
    _validate_index_matrix,
    type7_quantile,
)
from laconian_eval.benchmark.protocol_review import _preflight_exact_model_owners_v1
from laconian_eval.capsule.canonical import canonical_json, stable_digest

_PrimaryArm: TypeAlias = Literal["if", "concise"]
_ARMS: tuple[_PrimaryArm, _PrimaryArm] = ("if", "concise")
SensitivityExhaustionReason: TypeAlias = Literal["visited_node_cap", "bootstrap_evaluation_cap"]
MAX_VISITED_NODES = 1_000_000
MAX_BOOTSTRAP_LEAVES = 4_096


def _ceil_product(upper: Decimal, count: int) -> int:
    # Directed rounding retains the exact integer ceiling even when the fixed
    # 80-digit product lies infinitesimally above an integer. Half-even could
    # erase that excess. With n=ceil(U*M), upward rounding gives U*M <= r <= n,
    # since every integer n in [0,120] is exactly representable. Thus ceil(r)=n.
    # This does not change the stored Wilson upper bound.
    with localcontext(Context(prec=80, rounding=ROUND_CEILING)):
        return int((upper * count).to_integral_value(rounding=ROUND_CEILING))


class FalseFailCandidateV1(_AuditModel):
    response_id: str
    generation_model: str
    arm: Literal["if", "concise"]
    scenario_uid: str
    planned_key: str
    known_false_fail: bool

    @field_validator("response_id", "generation_model", "scenario_uid", "planned_key")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value:
            raise ValueError("candidate identifiers must be nonempty")
        value.encode("utf-8")
        return value


class FalseFailLimitV1(_AuditModel):
    generation_model: str
    arm: Literal["if", "concise"]
    m_all_judge_fail: int = Field(ge=0, le=120)
    d_known_false_fail: int = Field(ge=0, le=120)
    optional_candidates: int = Field(ge=0, le=120)
    upper_false_fail: Decimal | None
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    k_max_reclassified: int = Field(ge=0, le=120)
    estimable: bool

    @field_validator("upper_false_fail", mode="before")
    @classmethod
    def load_json_upper(cls, value: object, info: ValidationInfo) -> object:
        return _load_json_decimal(value, info)

    @model_validator(mode="after")
    def validate_bound(self) -> Self:
        m, d, k = self.m_all_judge_fail, self.d_known_false_fail, self.k_max_reclassified
        if not self.generation_model or not 0 <= d <= k <= m or self.optional_candidates != m - d:
            raise ValueError("false-fail limits require D <= K <= M and optional = M - D")
        upper = self.upper_false_fail
        if upper is not None and (not upper.is_finite() or not 0 <= upper <= 1):
            raise ValueError("false-fail upper must be finite and within [0, 1]")
        if not self.estimable:
            if upper is not None or k != d:
                raise ValueError("unestimable limit requires null U and placeholder K=D")
        elif m:
            if upper is None or k != min(m, max(d, _ceil_product(upper, m))):
                raise ValueError("estimable limit must use the closed ceil(U*M) formula")
        elif upper is not None:
            raise ValueError("zero judge-fail rows require no false-fail interval")
        return self


_FalseFailInputT = TypeVar("_FalseFailInputT", FalseFailCandidateV1, FalseFailLimitV1)


def _reject_undeclared_model_fields(value: BaseModel) -> None:
    """Inspect actual supplied fields after owner preflight, before serializers can omit extras."""

    pending: list[object] = [value]
    completed: set[int] = set()
    remaining = 16 * MAX_VISITED_NODES
    while pending:
        remaining -= 1
        if remaining < 0:
            raise TypeError("sensitivity model graph exceeds its field-inspection node limit")
        current = pending.pop()
        if not isinstance(current, (BaseModel, tuple, list, dict)):
            continue
        if id(current) in completed:
            continue
        completed.add(id(current))
        if isinstance(current, BaseModel):
            fields: dict[str, object] = object.__getattribute__(current, "__dict__")
            extra: object = object.__getattribute__(current, "__pydantic_extra__")
            if (
                type(fields) is not dict
                or set(fields) - set(type(current).model_fields)
                or (extra is not None and (type(extra) is not dict or extra))
            ):
                raise ValueError("sensitivity models forbid undeclared supplied fields")
            pending.extend(fields.values())
        elif isinstance(current, dict):
            pending.extend(current.values())
        else:
            pending.extend(current)


def _reload_false_fail_input(
    value: _FalseFailInputT,
    owner: type[_FalseFailInputT],
) -> _FalseFailInputT:
    """Reload our own inputs through the schema's serializer, never an instance substitute."""

    if type(value) is not owner:
        raise TypeError(f"expected exact {owner.__name__} owner")
    _preflight_exact_model_owners_v1(value, owner)
    _reject_undeclared_model_fields(value)
    return owner.model_validate_json(
        canonical_json_v1(
            owner.__pydantic_serializer__.to_python(value, mode="json"),
        )
    )


def _checked_candidates(
    candidates: Sequence[FalseFailCandidateV1],
) -> tuple[FalseFailCandidateV1, ...]:
    checked = tuple(
        _reload_false_fail_input(candidate, FalseFailCandidateV1) for candidate in candidates
    )
    if len({candidate.response_id for candidate in checked}) != len(checked):
        raise ValueError("duplicate candidate response ID")
    if len(
        {
            (candidate.generation_model, candidate.arm, candidate.planned_key)
            for candidate in checked
        }
    ) != len(checked):
        raise ValueError("duplicate candidate model/arm/planned key")
    return checked


def derive_false_fail_limit(
    *,
    model: str,
    arm: Literal["if", "concise"],
    candidates: Sequence[FalseFailCandidateV1],
    metrics: ModelAuditMetricsV1,
) -> FalseFailLimitV1:
    """Use only the authorizing model/arm two-sided design-weighted Wilson U."""

    checked_metrics = _reload(metrics, ModelAuditMetricsV1)
    if model != checked_metrics.generation_model or arm not in _ARMS:
        raise ValueError("false-fail model/primary arm differs from audit metrics")
    checked = _checked_candidates(candidates)
    selected = tuple(
        candidate
        for candidate in checked
        if candidate.generation_model == model and candidate.arm == arm
    )
    m = len(selected)
    d = sum(candidate.known_false_fail for candidate in selected)
    proportion = checked_metrics.false_fail_by_primary_arm[arm]
    # This model-level veto takes precedence even when the requested arm has M=0.
    unresolved = any(
        "unresolved_sampled_consensus" in value.unavailable_reasons
        for value in (
            checked_metrics.agreement,
            checked_metrics.false_pass,
            checked_metrics.reviewer_agreement,
            *checked_metrics.false_fail_by_primary_arm.values(),
        )
    )
    estimable = not unresolved and (m == 0 or proportion.available)
    upper = proportion.upper if estimable and m else None
    k = min(m, max(d, _ceil_product(upper, m))) if upper is not None else d
    return FalseFailLimitV1(
        generation_model=model,
        arm=arm,
        m_all_judge_fail=m,
        d_known_false_fail=d,
        optional_candidates=m - d,
        upper_false_fail=upper,
        model_audit_metric_sha256=checked_metrics.model_audit_metric_sha256,
        k_max_reclassified=k,
        estimable=estimable,
    )


class SensitivityExtremumV1(_AuditModel):
    value: float = Field(allow_inf_nan=False)
    assignment_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class SensitivityResultV1(_AuditModel):
    generation_model: str
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    assignment_count: int = Field(ge=0)
    visited_nodes: int = Field(ge=0)
    evaluated_assignments: int = Field(ge=0)
    semantic_min_lower: SensitivityExtremumV1 | None
    semantic_max_upper: SensitivityExtremumV1 | None
    token_min_lower: SensitivityExtremumV1 | None
    token_max_upper: SensitivityExtremumV1 | None
    search_exhausted: bool
    exhaustion_reason: SensitivityExhaustionReason | None
    certificate_sha256: str | None = Field(pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_exhaustion(self) -> Self:
        if not self.generation_model:
            raise ValueError("sensitivity result requires a generation model")
        if not self.search_exhausted:
            if self.exhaustion_reason is not None:
                raise ValueError("nonexhausted sensitivity forbids an exhaustion reason")
            return self
        if self.exhaustion_reason is None or any(
            value is not None
            for value in (
                self.semantic_min_lower,
                self.semantic_max_upper,
                self.token_min_lower,
                self.token_max_upper,
                self.certificate_sha256,
            )
        ):
            raise ValueError(
                "exhausted sensitivity requires a reason and no extrema or certificate"
            )
        if self.exhaustion_reason == "visited_node_cap":
            if (
                self.visited_nodes != MAX_VISITED_NODES
                or self.evaluated_assignments > MAX_BOOTSTRAP_LEAVES
            ):
                raise ValueError("visited_node_cap requires 1000000 nodes and at most 4096 leaves")
        elif (
            self.evaluated_assignments != MAX_BOOTSTRAP_LEAVES
            or self.visited_nodes >= MAX_VISITED_NODES
        ):
            raise ValueError(
                "bootstrap_evaluation_cap requires 4096 evaluations below the node cap"
            )
        return self


class PrunedSubtreeV1(_AuditModel):
    prefix_bits: str = Field(pattern="^[01]*$")
    selected_by_arm: Mapping[_PrimaryArm, int]
    remaining_by_arm: Mapping[_PrimaryArm, int]
    assignment_count: int = Field(gt=0)
    reason: Literal["cardinality-infeasible"]

    @field_validator("selected_by_arm", "remaining_by_arm")
    @classmethod
    def validate_arm_counts(cls, value: Mapping[_PrimaryArm, int]) -> Mapping[_PrimaryArm, int]:
        if set(value) != set(_ARMS) or any(count < 0 for count in value.values()):
            raise ValueError("subtree counts require both primary arms and nonnegative counts")
        return value


class EvaluatedLeafV1(_AuditModel):
    assignment_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    selected_response_ids: tuple[str, ...]
    semantic_lower: float | None = Field(allow_inf_nan=False)
    semantic_upper: float | None = Field(allow_inf_nan=False)
    token_lower: float | None = Field(allow_inf_nan=False)
    token_upper: float | None = Field(allow_inf_nan=False)

    @field_validator("selected_response_ids", mode="before")
    @classmethod
    def load_selected_ids(cls, value: object, info: ValidationInfo) -> object:
        return _exact_value_tuple(value, json_mode=info.mode == "json")


class SensitivityCertificateV1(_AuditModel):
    schema_version: Literal["sensitivity-certificate-v1"]
    generation_model: str
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    candidate_order: tuple[str, ...]
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1]
    bootstrap_vectors_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    visited_nodes: int = Field(ge=0, le=MAX_VISITED_NODES)
    evaluated_leaves: tuple[EvaluatedLeafV1, ...]
    pruned_subtrees: tuple[PrunedSubtreeV1, ...]
    semantic_min_lower: SensitivityExtremumV1 | None
    semantic_max_upper: SensitivityExtremumV1 | None
    token_min_lower: SensitivityExtremumV1 | None
    token_max_upper: SensitivityExtremumV1 | None
    certificate_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @field_validator("candidate_order", mode="before")
    @classmethod
    def load_candidate_order(cls, value: object, info: ValidationInfo) -> object:
        return _exact_value_tuple(value, json_mode=info.mode == "json")

    @field_validator("limits", "evaluated_leaves", "pruned_subtrees", mode="before")
    @classmethod
    def load_model_tuples(cls, value: object, info: ValidationInfo) -> object:
        owners: dict[str, type[BaseModel]] = {
            "limits": FalseFailLimitV1,
            "evaluated_leaves": EvaluatedLeafV1,
            "pruned_subtrees": PrunedSubtreeV1,
        }
        return _exact_model_tuple(
            value, owners[str(info.field_name)], json_mode=info.mode == "json"
        )


def _assignment_count(limits: tuple[FalseFailLimitV1, FalseFailLimitV1]) -> int:
    return math.prod(
        sum(
            math.comb(limit.optional_candidates, total - limit.d_known_false_fail)
            for total in range(limit.d_known_false_fail, limit.k_max_reclassified + 1)
        )
        for limit in limits
    )


def _partition(
    arm: _PrimaryArm,
    candidates: Sequence[FalseFailCandidateV1],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return tuple(
        sorted(
            (
                candidate.response_id
                for candidate in candidates
                if candidate.arm == arm and candidate.known_false_fail
            ),
            key=str.encode,
        )
    ), tuple(
        sorted(
            (
                candidate.response_id
                for candidate in candidates
                if candidate.arm == arm and not candidate.known_false_fail
            ),
            key=str.encode,
        )
    )


def _assignment_choices(
    limit: FalseFailLimitV1,
    candidates: Sequence[FalseFailCandidateV1],
) -> Iterator[tuple[str, ...]]:
    forced, optional = _partition(limit.arm, candidates)
    for total in range(limit.d_known_false_fail, limit.k_max_reclassified + 1):
        for selected in combinations(optional, total - limit.d_known_false_fail):
            yield forced + selected


def _assignment_digest(
    model: str,
    selected: Sequence[str],
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: Sequence[FalseFailCandidateV1],
) -> str:
    partitions = {arm: _partition(arm, candidates) for arm in _ARMS}
    selected_ids = sorted(selected, key=lambda value: value.encode("utf-8"))
    return stable_digest(
        "laconian-false-fail-assignment-v1",
        {
            "generation_model": model,
            "reclassified_response_ids": selected_ids,
            "forced_response_ids": {arm: list(partitions[arm][0]) for arm in _ARMS},
            "optional_response_ids": {arm: list(partitions[arm][1]) for arm in _ARMS},
            "limits": [limit.model_dump(mode="json") for limit in limits],
        },
    )


def _planned_key(row: PlannedObservationV1) -> str:
    """Canonical JSON spelling of the four-field planned key; arm is joined separately."""

    return canonical_json_v1(
        {
            "scenario_uid": row.scenario_uid,
            "case_id": row.case_id,
            "locale": row.locale,
            "repetition": row.repetition,
        }
    ).decode("utf-8")


def _validate_candidate_universe(
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: tuple[FalseFailCandidateV1, ...],
) -> None:
    response_ids = [row.response_id for row in aggregate.rows if row.response_id is not None]
    if len(set(response_ids)) != len(response_ids):
        raise ValueError("duplicate aggregate response ID")
    universe = {
        row.response_id: row
        for row in aggregate.rows
        if row.arm in _ARMS and row.hard_pass and not row.semantic_success
    }
    if set(universe) != {candidate.response_id for candidate in candidates}:
        raise ValueError("candidates must bijectively cover every primary-arm H=1 judge-fail row")
    for candidate in candidates:
        row = universe[candidate.response_id]
        if (
            candidate.generation_model != aggregate.generation_model
            or candidate.arm != row.arm
            or candidate.scenario_uid != row.scenario_uid
            or candidate.planned_key != _planned_key(row)
        ):
            raise ValueError(
                "candidate model, arm, scenario or planned key differs from aggregate row"
            )
    for limit in limits:
        forced, optional = _partition(limit.arm, candidates)
        if (limit.m_all_judge_fail, limit.d_known_false_fail, limit.optional_candidates) != (
            len(forced) + len(optional),
            len(forced),
            len(optional),
        ):
            raise ValueError(
                "limit counts differ from the complete forced/optional candidate partition"
            )


@dataclass(frozen=True)
class _PreparedAssignment:
    semantic_counts: tuple[int, ...]
    token_deltas_by_cluster: tuple[tuple[int, ...], ...]
    eligible_pairs: int
    token_pairs: int


def _prepare_assignment(
    rows: Sequence[PlannedObservationV1],
    reclassified: frozenset[str],
) -> _PreparedAssignment:
    """Project S=1 only on selected rows; all H and token accounting remain untouched.

    Private callers must supply the canonical, validated 480-row snapshot. Complete
    blocks contain ten paired keys, so summed integer success differences divided
    by 120 equal the public estimator for every cluster multiset.
    """

    uids = sorted({row.scenario_uid for row in rows}, key=str.encode)
    ranks = {uid: index for index, uid in enumerate(uids)}
    if_rows = {_row_key(row): row for row in rows if row.arm == "if"}
    concise_rows = {_row_key(row): row for row in rows if row.arm == "concise"}
    counts = [0] * 12
    deltas: list[list[int]] = [[] for _ in range(12)]
    eligible = 0
    for key, if_row in if_rows.items():
        concise_row = concise_rows[key]
        left = if_row.semantic_success or if_row.response_id in reclassified
        right = concise_row.semantic_success or concise_row.response_id in reclassified
        rank = ranks[if_row.scenario_uid]
        counts[rank] += int(left) - int(right)
        if left and right:
            eligible += 1
            if (
                if_row.visible_output_tokens is not None
                and concise_row.visible_output_tokens is not None
            ):
                deltas[rank].append(
                    concise_row.visible_output_tokens - if_row.visible_output_tokens
                )
    return _PreparedAssignment(
        tuple(counts), tuple(tuple(values) for values in deltas), eligible, sum(map(len, deltas))
    )


def _estimate_prepared(
    prepared: _PreparedAssignment,
    indices: NDArray[np.uint8],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Exact multiset estimates, retaining cluster multiplicity and integer token deltas."""

    semantic = np.asarray(prepared.semantic_counts, dtype=np.int64)[indices].sum(axis=1) / 120
    token = np.full(len(indices), np.nan, dtype=np.float64)
    ordered = sorted(
        (delta, cluster)
        for cluster, deltas in enumerate(prepared.token_deltas_by_cluster)
        for delta in deltas
    )
    if not ordered:
        return semantic, token
    multiplicities = np.stack([(indices == cluster).sum(axis=1) for cluster in range(12)], axis=1)
    cumulative = multiplicities[:, [cluster for _, cluster in ordered]].cumsum(axis=1)
    totals = cumulative[:, -1]
    lower = (cumulative > ((totals - 1) // 2)[:, None]).argmax(axis=1)
    upper = (cumulative > (totals // 2)[:, None]).argmax(axis=1)
    for index in np.flatnonzero(totals):
        a, b = ordered[int(lower[index])][0], ordered[int(upper[index])][0]
        # Match statistics.median: retain arbitrary-size integers until the final
        # division/conversion; float arrays of input deltas would lose precision.
        token[index] = float(a) if totals[index] % 2 else float((a + b) / 2)
    return semantic, token


def _intervals_for_assignment(
    prepared: _PreparedAssignment,
    vectors: NDArray[np.uint8],
) -> tuple[BootstrapIntervalV1, BootstrapIntervalV1]:
    # Repeated vectors are evaluated once, then expanded before percentile ranks.
    unique, inverse = np.unique(vectors, axis=0, return_inverse=True)
    return _intervals_for_unique_vectors(prepared, unique, inverse)


def _intervals_for_unique_vectors(
    prepared: _PreparedAssignment,
    unique: NDArray[np.uint8],
    inverse: NDArray[np.intp],
) -> tuple[BootstrapIntervalV1, BootstrapIntervalV1]:
    """Reuse a call's immutable vector compression, preserving all 10000 replicate ranks."""

    estimates = _estimate_prepared(prepared, unique)
    points = _estimate_prepared(prepared, np.arange(12, dtype=np.uint8)[None, :])

    def interval(values: NDArray[np.float64], point: float) -> BootstrapIntervalV1:
        expanded = values[inverse]
        finite = expanded[np.isfinite(expanded)]
        available = len(finite) >= BOOTSTRAP_MIN_VALID
        return BootstrapIntervalV1(
            point=point if math.isfinite(point) else None,
            lower=type7_quantile(finite, 0.025) if available else None,
            upper=type7_quantile(finite, 0.975) if available else None,
            valid_replicates=len(finite),
            available=available,
        )

    return interval(estimates[0], float(points[0][0])), interval(estimates[1], float(points[1][0]))


def _checked_sensitivity_inputs(
    *,
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: Sequence[FalseFailCandidateV1],
    vectors: NDArray[np.uint8],
) -> tuple[
    AggregatedModelV1,
    tuple[FalseFailLimitV1, FalseFailLimitV1],
    tuple[FalseFailCandidateV1, ...],
    NDArray[np.uint8],
]:
    """Snapshot class-bound normalized rows and vectors before either exact calculation."""

    if type(aggregate) is not AggregatedModelV1:
        raise TypeError("expected exact AggregatedModelV1 owner")
    _preflight_exact_model_owners_v1(aggregate, AggregatedModelV1)
    aggregate_payload = dict(aggregate.__dict__)
    # Aggregate validation checks normalized copies but retains its nested row
    # instances. Snapshot those rows explicitly so overloaded scalar subclasses
    # cannot supply arithmetic to the prepared calculator after validation.
    aggregate_payload["rows"] = tuple(
        PlannedObservationV1.model_validate(dict(row.__dict__)) for row in aggregate.rows
    )
    checked_aggregate = AggregatedModelV1.model_validate(aggregate_payload)
    if type(limits) is not tuple or len(limits) != 2:
        raise ValueError("limits must be an exact (if, concise) tuple")
    checked_limits = (
        _reload_false_fail_input(limits[0], FalseFailLimitV1),
        _reload_false_fail_input(limits[1], FalseFailLimitV1),
    )
    if (
        tuple(limit.arm for limit in checked_limits) != _ARMS
        or any(
            limit.generation_model != checked_aggregate.generation_model for limit in checked_limits
        )
        or checked_limits[0].model_audit_metric_sha256
        != checked_limits[1].model_audit_metric_sha256
    ):
        raise ValueError(
            "if/concise limits must share the aggregate model and one audit metric digest"
        )
    checked_candidates = _checked_candidates(candidates)
    _validate_candidate_universe(checked_aggregate, checked_limits, checked_candidates)
    index_snapshot = _validate_index_matrix(vectors).copy(order="C")
    index_snapshot.flags.writeable = False
    return checked_aggregate, checked_limits, checked_candidates, index_snapshot


def enumerate_sensitivity_exact(
    *,
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: Sequence[FalseFailCandidateV1],
    vectors: NDArray[np.uint8],
) -> SensitivityResultV1:
    """Enumerate at most 4096 assignments using the same frozen 10000 cluster vectors."""

    checked_aggregate, checked_limits, checked_candidates, index_snapshot = (
        _checked_sensitivity_inputs(
            aggregate=aggregate,
            limits=limits,
            candidates=candidates,
            vectors=vectors,
        )
    )
    estimable = all(limit.estimable for limit in checked_limits)
    count = _assignment_count(checked_limits) if estimable else 0
    if count > 4096:
        raise ValueError("direct sensitivity enumeration refuses assignment spaces above 4096")
    extrema: list[SensitivityExtremumV1 | None] = [None] * 4
    available = [True] * 4
    evaluated = 0
    if estimable:
        for if_selected in _assignment_choices(checked_limits[0], checked_candidates):
            for concise_selected in _assignment_choices(checked_limits[1], checked_candidates):
                selected = if_selected + concise_selected
                prepared = _prepare_assignment(checked_aggregate.rows, frozenset(selected))
                semantic, token = _intervals_for_assignment(prepared, index_snapshot)
                digest = _assignment_digest(
                    checked_aggregate.generation_model, selected, checked_limits, checked_candidates
                )
                for index, endpoint in enumerate(
                    (semantic.lower, semantic.upper, token.lower, token.upper)
                ):
                    current = extrema[index]
                    if endpoint is None:
                        available[index] = False
                        extrema[index] = None
                    elif available[index] and (
                        current is None
                        or (
                            endpoint < current.value if index % 2 == 0 else endpoint > current.value
                        )
                    ):
                        extrema[index] = SensitivityExtremumV1(
                            value=endpoint, assignment_sha256=digest
                        )
                evaluated += 1
    return SensitivityResultV1(
        generation_model=checked_aggregate.generation_model,
        model_audit_metric_sha256=checked_limits[0].model_audit_metric_sha256,
        assignment_count=count,
        visited_nodes=evaluated,
        evaluated_assignments=evaluated,
        semantic_min_lower=extrema[0],
        semantic_max_upper=extrema[1],
        token_min_lower=extrema[2],
        token_max_upper=extrema[3],
        search_exhausted=False,
        exhaustion_reason=None,
        certificate_sha256=None,
    )


def _evaluate_leaf(
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: tuple[FalseFailCandidateV1, ...],
    selected: tuple[str, ...],
    unique: NDArray[np.uint8],
    inverse: NDArray[np.intp],
) -> EvaluatedLeafV1:
    prepared = _prepare_assignment(aggregate.rows, frozenset(selected))
    semantic, token = _intervals_for_unique_vectors(prepared, unique, inverse)
    return EvaluatedLeafV1(
        assignment_sha256=_assignment_digest(
            aggregate.generation_model, selected, limits, candidates
        ),
        selected_response_ids=tuple(sorted(selected, key=str.encode)),
        semantic_lower=semantic.lower,
        semantic_upper=semantic.upper,
        token_lower=token.lower,
        token_upper=token.upper,
    )


_TieRank: TypeAlias = tuple[int, tuple[bytes, ...], int, tuple[bytes, ...]]
_Extrema: TypeAlias = tuple[
    SensitivityExtremumV1 | None,
    SensitivityExtremumV1 | None,
    SensitivityExtremumV1 | None,
    SensitivityExtremumV1 | None,
]


def _leaf_extrema(
    leaves: Sequence[EvaluatedLeafV1],
    candidates: tuple[FalseFailCandidateV1, ...],
) -> _Extrema:
    """Task 11 tie order: if cardinality/combinations outside concise cardinality/combinations."""

    optional = {arm: frozenset(_partition(arm, candidates)[1]) for arm in _ARMS}
    ranks: list[_TieRank] = []
    for leaf in leaves:
        by_arm = [
            tuple(
                value.encode("utf-8")
                for value in leaf.selected_response_ids
                if value in optional[arm]
            )
            for arm in _ARMS
        ]
        ranks.append((len(by_arm[0]), by_arm[0], len(by_arm[1]), by_arm[1]))
    extrema: list[SensitivityExtremumV1 | None] = []
    for index, name in enumerate(
        ("semantic_lower", "semantic_upper", "token_lower", "token_upper")
    ):
        endpoints: list[float | None] = [getattr(leaf, name) for leaf in leaves]
        if not endpoints or any(value is None for value in endpoints):
            extrema.append(None)
            continue
        available = [
            (value, rank, leaf.assignment_sha256)
            for value, rank, leaf in zip(endpoints, ranks, leaves, strict=True)
            if value is not None
        ]
        value, _, digest = min(
            available,
            key=lambda item: (
                item[0] if index % 2 == 0 else -item[0],
                item[1],
            ),
        )
        extrema.append(SensitivityExtremumV1(value=value, assignment_sha256=digest))
    return extrema[0], extrema[1], extrema[2], extrema[3]


def _search_result(
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    *,
    count: int,
    visited: int,
    evaluated: int,
    extrema: _Extrema = (None, None, None, None),
    reason: SensitivityExhaustionReason | None = None,
    certificate_sha256: str | None = None,
) -> SensitivityResultV1:
    return SensitivityResultV1(
        generation_model=aggregate.generation_model,
        model_audit_metric_sha256=limits[0].model_audit_metric_sha256,
        assignment_count=count,
        visited_nodes=visited,
        evaluated_assignments=evaluated,
        semantic_min_lower=extrema[0],
        semantic_max_upper=extrema[1],
        token_min_lower=extrema[2],
        token_max_upper=extrema[3],
        search_exhausted=reason is not None,
        exhaustion_reason=reason,
        certificate_sha256=certificate_sha256,
    )


def search_sensitivity_exact(
    *,
    aggregate: AggregatedModelV1,
    limits: tuple[FalseFailLimitV1, FalseFailLimitV1],
    candidates: Sequence[FalseFailCandidateV1],
    vectors: NDArray[np.uint8],
) -> tuple[SensitivityResultV1, SensitivityCertificateV1 | None]:
    """Certify exhaustive cardinality-only DFS, or discard all partial extrema at either cap.

    The vector commitment is SHA-256 of the validated C-order uint8 snapshot,
    distinct from BootstrapVectorsV1's seeded metadata digest. Source verification
    and binding that metadata to the raw matrix remain external preconditions.
    """

    aggregate, limits, checked, snapshot = _checked_sensitivity_inputs(
        aggregate=aggregate,
        limits=limits,
        candidates=candidates,
        vectors=vectors,
    )
    if not all(limit.estimable for limit in limits):
        return _search_result(aggregate, limits, count=0, visited=0, evaluated=0), None
    count = _assignment_count(limits)
    optional = tuple(
        sorted(
            (candidate for candidate in checked if not candidate.known_false_fail),
            key=lambda candidate: candidate.response_id.encode("utf-8"),
        )
    )
    order = tuple(candidate.response_id for candidate in optional)
    arm_indices = tuple(_ARMS.index(candidate.arm) for candidate in optional)
    forced = tuple(candidate.response_id for candidate in checked if candidate.known_false_fail)
    capacity = tuple(limit.k_max_reclassified - limit.d_known_false_fail for limit in limits)
    unique, inverse = np.unique(snapshot, axis=0, return_inverse=True)
    unique.flags.writeable = inverse.flags.writeable = False
    # A space larger than the leaf cap cannot yield a certificate. Its traversal
    # and every permitted leaf evaluation still run; avoid retaining a doomed proof.
    retain_proof = count <= MAX_BOOTSTRAP_LEAVES
    leaves: list[EvaluatedLeafV1] = []
    prunes: list[PrunedSubtreeV1] = []
    pending = [("", (0, 0), (limits[0].optional_candidates, limits[1].optional_candidates))]
    visited = evaluated = 0
    reason: SensitivityExhaustionReason | None = None
    while pending:
        if visited == MAX_VISITED_NODES:
            reason = "visited_node_cap"
            break
        prefix, selected_counts, remaining = pending.pop()
        visited += 1
        if any(selected_counts[index] > capacity[index] for index in range(2)):
            if retain_proof:
                prunes.append(
                    PrunedSubtreeV1(
                        prefix_bits=prefix,
                        selected_by_arm=dict(zip(_ARMS, selected_counts, strict=True)),
                        remaining_by_arm=dict(zip(_ARMS, remaining, strict=True)),
                        assignment_count=2 ** sum(remaining),
                        reason="cardinality-infeasible",
                    )
                )
            continue
        depth = len(prefix)
        if depth == len(order):
            if evaluated == MAX_BOOTSTRAP_LEAVES:
                reason = (
                    "visited_node_cap"
                    if visited == MAX_VISITED_NODES
                    else "bootstrap_evaluation_cap"
                )
                break
            selected = forced + tuple(
                value for value, bit in zip(order, prefix, strict=True) if bit == "1"
            )
            evaluated += 1
            leaf = _evaluate_leaf(aggregate, limits, checked, selected, unique, inverse)
            if retain_proof:
                leaves.append(leaf)
            continue
        arm = arm_indices[depth]
        next_remaining = (remaining[0] - (arm == 0), remaining[1] - (arm == 1))
        included = (selected_counts[0] + (arm == 0), selected_counts[1] + (arm == 1))
        # Stack reversal makes the exclude child the next entered prefix.
        pending.append((prefix + "1", included, next_remaining))
        pending.append((prefix + "0", selected_counts, next_remaining))
    if reason is not None:
        return _search_result(
            aggregate, limits, count=count, visited=visited, evaluated=evaluated, reason=reason
        ), None
    extrema = _leaf_extrema(leaves, checked)
    payload = {
        "schema_version": "sensitivity-certificate-v1",
        "generation_model": aggregate.generation_model,
        "model_audit_metric_sha256": limits[0].model_audit_metric_sha256,
        "candidate_order": order,
        "limits": [limit.model_dump(mode="json") for limit in limits],
        "bootstrap_vectors_sha256": hashlib.sha256(snapshot.tobytes(order="C")).hexdigest(),
        "visited_nodes": visited,
        "evaluated_leaves": [leaf.model_dump(mode="json") for leaf in leaves],
        "pruned_subtrees": [prune.model_dump(mode="json") for prune in prunes],
        **{
            name: value.model_dump(mode="json") if value is not None else None
            for name, value in zip(
                ("semantic_min_lower", "semantic_max_upper", "token_min_lower", "token_max_upper"),
                extrema,
                strict=True,
            )
        },
    }
    # The certificate commits its complete payload before a result refers to it.
    digest = stable_digest("laconian-sensitivity-certificate-v1", payload)
    certificate = SensitivityCertificateV1.model_validate_json(
        canonical_json(
            {
                **payload,
                "certificate_sha256": digest,
            }
        )
    )
    return _search_result(
        aggregate,
        limits,
        count=count,
        visited=visited,
        evaluated=evaluated,
        extrema=extrema,
        certificate_sha256=digest,
    ), certificate


def verify_sensitivity_certificate(
    certificate: SensitivityCertificateV1,
    *,
    aggregate: AggregatedModelV1,
    candidates: Sequence[FalseFailCandidateV1],
    vectors: NDArray[np.uint8],
) -> SensitivityResultV1:
    """Independently prove coverage and recompute every leaf; never invoke the producer."""

    if type(certificate) is not SensitivityCertificateV1:
        raise TypeError("expected exact SensitivityCertificateV1 owner")
    # A legal large partition can exceed the audit preflight's generic graph
    # budget. This bound covers every field of at most one million tree records.
    _preflight_exact_model_owners_v1(
        certificate,
        SensitivityCertificateV1,
        remaining_nodes=[16 * MAX_VISITED_NODES],
    )
    _reject_undeclared_model_fields(certificate)
    certificate = SensitivityCertificateV1.model_validate_json(
        canonical_json(
            SensitivityCertificateV1.__pydantic_serializer__.to_python(certificate, mode="json"),
        )
    )
    payload = certificate.model_dump(mode="json", exclude={"certificate_sha256"})
    if (
        stable_digest("laconian-sensitivity-certificate-v1", payload)
        != certificate.certificate_sha256
    ):
        raise ValueError("certificate digest differs from its canonical payload")
    aggregate, limits, checked, snapshot = _checked_sensitivity_inputs(
        aggregate=aggregate,
        limits=certificate.limits,
        candidates=candidates,
        vectors=vectors,
    )
    if not all(limit.estimable for limit in limits):
        raise ValueError("unestimable limits cannot authorize a sensitivity certificate")
    if (
        certificate.generation_model != aggregate.generation_model
        or certificate.model_audit_metric_sha256 != limits[0].model_audit_metric_sha256
    ):
        raise ValueError("certificate model or audit metric differs from the ordered limits")
    if (
        certificate.bootstrap_vectors_sha256
        != hashlib.sha256(snapshot.tobytes(order="C")).hexdigest()
    ):
        raise ValueError("certificate bootstrap vector digest mismatch")
    optional = tuple(
        sorted(
            (candidate for candidate in checked if not candidate.known_false_fail),
            key=lambda candidate: candidate.response_id.encode("utf-8"),
        )
    )
    order = tuple(candidate.response_id for candidate in optional)
    if certificate.candidate_order != order:
        raise ValueError("certificate candidate order differs from the exact optional pool")
    count = _assignment_count(limits)
    if len(certificate.evaluated_leaves) != count or count > MAX_BOOTSTRAP_LEAVES:
        raise ValueError("certificate must evaluate every feasible assignment within the leaf cap")
    forced = {candidate.response_id for candidate in checked if candidate.known_false_fail}
    pool = forced | set(order)
    capacity = {limit.arm: limit.k_max_reclassified - limit.d_known_false_fail for limit in limits}
    optional_counts = {limit.arm: limit.optional_candidates for limit in limits}
    prune_prefixes: list[str] = []
    excluded = 0
    for prune in certificate.pruned_subtrees:
        prefix = prune.prefix_bits
        if not prefix or len(prefix) > len(order):
            raise ValueError("pruned prefix must name an optional-candidate subtree")
        selected = {
            arm: sum(
                candidate.arm == arm and bit == "1"
                for candidate, bit in zip(optional, prefix, strict=False)
            )
            for arm in _ARMS
        }
        remaining = {
            arm: optional_counts[arm]
            - sum(candidate.arm == arm for candidate in optional[: len(prefix)])
            for arm in _ARMS
        }
        residual = math.prod(
            sum(
                math.comb(remaining[arm], q)
                for q in range(remaining[arm] + 1)
                if selected[arm] + q <= capacity[arm]
            )
            for arm in _ARMS
        )
        parent = dict(selected)
        parent[optional[len(prefix) - 1].arm] -= prefix[-1] == "1"
        if (
            dict(prune.selected_by_arm) != selected
            or dict(prune.remaining_by_arm) != remaining
            or residual != 0
            or any(parent[arm] > capacity[arm] for arm in _ARMS)
            or prune.assignment_count != 2 ** sum(remaining.values())
        ):
            raise ValueError("pruned subtree has wrong cardinality, residual, or completion count")
        prune_prefixes.append(prefix)
        excluded += prune.assignment_count
    leaf_prefixes: list[str] = []
    for leaf in certificate.evaluated_leaves:
        selected_ids = set(leaf.selected_response_ids)
        if (
            leaf.selected_response_ids != tuple(sorted(selected_ids, key=str.encode))
            or not forced <= selected_ids <= pool
        ):
            raise ValueError("leaf must select every forced row and only exact candidate IDs")
        if any(
            sum(
                candidate.arm == arm and candidate.response_id in selected_ids
                for candidate in optional
            )
            > capacity[arm]
            for arm in _ARMS
        ):
            raise ValueError("evaluated leaf violates cardinality")
        leaf_prefixes.append("".join("1" if value in selected_ids else "0" for value in order))
    if prune_prefixes != sorted(prune_prefixes) or leaf_prefixes != sorted(leaf_prefixes):
        raise ValueError("certificate records must follow exclude-before-include DFS order")
    terminals = sorted(prune_prefixes + leaf_prefixes)
    if any(right.startswith(left) for left, right in pairwise(terminals)):
        raise ValueError("certificate subtrees overlap or duplicate an evaluated leaf")
    # Reconstruct the tree bottom-up. Every internal prefix must have both
    # children; totals alone cannot substitute for this exhaustive partition proof.
    frontier: list[str] = []
    reconstructed_nodes = len(terminals)
    for prefix in terminals:
        frontier.append(prefix)
        while (
            len(frontier) >= 2
            and frontier[-2].endswith("0")
            and frontier[-1] == frontier[-2][:-1] + "1"
        ):
            frontier.pop()
            frontier[-1] = frontier[-1][:-1]
            reconstructed_nodes += 1
    if (
        frontier != [""]
        or len(certificate.evaluated_leaves) + excluded != 2 ** len(order)
        or reconstructed_nodes != certificate.visited_nodes
    ):
        raise ValueError("certificate does not prove the complete prefix tree or visited count")
    unique, inverse = np.unique(snapshot, axis=0, return_inverse=True)
    unique.flags.writeable = inverse.flags.writeable = False
    verified: list[EvaluatedLeafV1] = []
    for leaf in certificate.evaluated_leaves:
        recomputed = _evaluate_leaf(
            aggregate, limits, checked, leaf.selected_response_ids, unique, inverse
        )
        if canonical_json(recomputed.model_dump(mode="json")) != canonical_json(
            leaf.model_dump(mode="json")
        ):
            raise ValueError(
                "certificate leaf digest or bootstrap endpoints differ from recomputation"
            )
        verified.append(recomputed)
    extrema = _leaf_extrema(verified, checked)
    expected = [value.model_dump(mode="json") if value is not None else None for value in extrema]
    actual = [
        payload[name]
        for name in (
            "semantic_min_lower",
            "semantic_max_upper",
            "token_min_lower",
            "token_max_upper",
        )
    ]
    if canonical_json(expected) != canonical_json(actual):
        raise ValueError("certificate extrema differ from the verified leaves")
    return _search_result(
        aggregate,
        limits,
        count=count,
        visited=reconstructed_nodes,
        evaluated=len(verified),
        extrema=extrema,
        certificate_sha256=certificate.certificate_sha256,
    )


__all__ = (
    "MAX_BOOTSTRAP_LEAVES",
    "MAX_VISITED_NODES",
    "EvaluatedLeafV1",
    "FalseFailCandidateV1",
    "FalseFailLimitV1",
    "PrunedSubtreeV1",
    "SensitivityCertificateV1",
    "SensitivityExhaustionReason",
    "SensitivityExtremumV1",
    "SensitivityResultV1",
    "derive_false_fail_limit",
    "enumerate_sensitivity_exact",
    "search_sensitivity_exact",
    "verify_sensitivity_certificate",
)
