"""Deterministic design-weighted audit calculations after source verification.

These functions are not evidence-admission APIs. The caller must independently run
``verify_audit_chain`` against the full immutable source-backed adjudication and pass
the verified sample's manifest and population records. The authoritative publication
workflow fresh-loads those parents, verifies the chain, and recomputes these metrics.
Structural reloads, bindings and joins here cannot authenticate absent raw sources.

All rational arithmetic is exact. Decimal output uses a fixed 80-digit, half-even
context, including conversions, Wilson endpoints and kappa. Stored endpoints retain
that precision; the reported two-sided false-fail upper endpoint is the sole U for
subsequent false-fail sensitivity calculations.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from typing import Literal, Self, TypeAlias, TypeVar

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from laconian_eval.benchmark.attachments import RationalV1, canonical_json_v1
from laconian_eval.benchmark.audit_commit_reveal import (
    AuditAdjudicationV1,
    ConsensusLabelV1,
    ReviewerChainV1,
    _AuditModel,
    canonical_label_jsonl,
    compute_commitment,
)
from laconian_eval.benchmark.audit_sampling import (
    AuditSampleManifestV1,
    _cell_id,
    _is_certainty,
)
from laconian_eval.benchmark.context import BenchmarkProtocolBindingsV1
from laconian_eval.benchmark.protocol_review import _preflight_exact_model_owners_v1
from laconian_eval.benchmark.provider_evidence import AuditPopulationRecordV1
from laconian_eval.capsule.canonical import stable_digest

_PrimaryArm: TypeAlias = Literal["if", "concise"]
_Authorization: TypeAlias = Literal["audit-gate", "false-fail-sensitivity", "reported-only"]
_UnavailableReason: TypeAlias = Literal[
    "zero_denominator",
    "empty_required_stratum",
    "effective_sample_size_below_one",
    "unresolved_sampled_consensus",
]
_REASONS: tuple[_UnavailableReason, ...] = (
    "zero_denominator",
    "empty_required_stratum",
    "effective_sample_size_below_one",
    "unresolved_sampled_consensus",
)
_PRIMARY_ARMS: tuple[_PrimaryArm, _PrimaryArm] = ("if", "concise")
_Z = Decimal("1.959963984540054")
_METRIC_DOMAIN = "laconian-model-audit-metric-v1"
_METRIC_DIGEST = "model_audit_metric_sha256"
_GATE_CONDITIONS = (
    ("agreement_interval_available", "agreement_interval_unavailable"),
    ("false_pass_interval_available", "false_pass_interval_unavailable"),
    ("agreement_at_least_90_percent", "agreement_below_90_percent"),
    ("false_pass_at_most_5_percent", "false_pass_above_5_percent"),
    ("no_unresolved_disagreement", "unresolved_disagreement"),
    ("critical_primary_coverage_complete", "critical_primary_coverage_incomplete"),
    ("no_critical_primary_false_pass", "critical_primary_false_pass"),
)
_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _reload(value: _ModelT, owner: type[_ModelT]) -> _ModelT:
    """Class-bound structural reload, including models whose instance validation is off."""

    if type(value) is not owner:
        raise TypeError(f"expected exact {owner.__name__} owner")
    _preflight_exact_model_owners_v1(value, owner)
    return owner.model_validate_json(canonical_json_v1(BaseModel.model_dump(value, mode="json")))


def _fraction(value: RationalV1) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _rational(value: Fraction) -> RationalV1:
    return RationalV1(numerator=value.numerator, denominator=value.denominator)


def _decimal(value: Fraction) -> Decimal:
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        return Decimal(value.numerator) / Decimal(value.denominator)


def _load_json_decimal(value: object, info: ValidationInfo) -> object:
    if info.mode == "json" and type(value) is str:
        try:
            with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
                return Decimal(value)
        except InvalidOperation as error:
            raise ValueError("audit Decimal text is invalid") from error
    return value


class WeightedConfusionV1(_AuditModel):
    """Exact weighted counts; first decision is judge/reviewer A, second consensus/B."""

    pass_pass: RationalV1
    pass_fail: RationalV1
    fail_pass: RationalV1
    fail_fail: RationalV1

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        for name in WeightedConfusionV1.model_fields:
            value = _reload(getattr(self, name), RationalV1)
            if _fraction(value) < 0:
                raise ValueError("weighted confusion counts must be nonnegative")
        return self


class WeightedProportionV1(_AuditModel):
    numerator: RationalV1
    denominator: RationalV1
    point: Decimal | None
    effective_n: Decimal | None
    lower: Decimal | None
    upper: Decimal | None
    available: bool
    confidence_level: Literal["two-sided-0.95"] = "two-sided-0.95"
    z: Decimal
    interval_method: Literal["design-weighted-wilson-score-v1"]
    authorization_use: _Authorization
    unavailable_reasons: tuple[_UnavailableReason, ...]

    @field_validator("point", "effective_n", "lower", "upper", "z", mode="before")
    @classmethod
    def load_json_decimals(cls, value: object, info: ValidationInfo) -> object:
        return _load_json_decimal(value, info)

    @field_validator("unavailable_reasons", mode="before")
    @classmethod
    def load_json_reasons(cls, value: object, info: ValidationInfo) -> object:
        return tuple(value) if info.mode == "json" and type(value) is list else value

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        numerator = _fraction(_reload(self.numerator, RationalV1))
        denominator = _fraction(_reload(self.denominator, RationalV1))
        if not 0 <= numerator <= denominator:
            raise ValueError("weighted proportion requires 0 <= numerator <= denominator")
        values = (self.point, self.effective_n, self.lower, self.upper)
        if any(value is not None and not value.is_finite() for value in (*values, self.z)):
            raise ValueError("weighted proportion Decimal values must be finite")
        if self.z != _Z:
            raise ValueError("weighted Wilson z differs from the frozen two-sided value")
        if self.unavailable_reasons != tuple(
            reason for reason in _REASONS if reason in self.unavailable_reasons
        ):
            raise ValueError("unavailable reasons must be unique and in frozen order")
        if self.available:
            if (
                self.point is None
                or self.effective_n is None
                or self.lower is None
                or self.upper is None
                or self.unavailable_reasons
                or denominator == 0
                or not 0 <= self.lower <= self.point <= self.upper <= 1
                or self.effective_n < 1
                or self.point != _decimal(numerator / denominator)
            ):
                raise ValueError(
                    "available Wilson interval requires valid values and effective n >= 1"
                )
        elif any(value is not None for value in values) or not self.unavailable_reasons:
            raise ValueError(
                "unavailable Wilson interval requires null values and nonempty reasons"
            )
        if (denominator == 0) != ("zero_denominator" in self.unavailable_reasons):
            raise ValueError("zero denominator must have its exact unavailable reason")
        return self


class ModelAuditMetricsV1(_AuditModel):
    generation_model: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    weights_by_record: Mapping[str, RationalV1]
    judge_consensus_confusion: WeightedConfusionV1
    reviewer_confusion: WeightedConfusionV1
    agreement: WeightedProportionV1
    false_pass: WeightedProportionV1
    false_fail_by_primary_arm: Mapping[_PrimaryArm, WeightedProportionV1]
    reviewer_agreement: WeightedProportionV1
    weighted_kappa: Decimal | None
    model_audit_metric_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @field_validator("weighted_kappa", mode="before")
    @classmethod
    def load_json_kappa(cls, value: object, info: ValidationInfo) -> object:
        return _load_json_decimal(value, info)

    @model_validator(mode="after")
    def validate_metrics(self) -> Self:
        _reload(self.protocol_bindings, BenchmarkProtocolBindingsV1)
        if not self.generation_model or set(self.false_fail_by_primary_arm) != set(_PRIMARY_ARMS):
            raise ValueError("model audit metrics require a model and both primary arms")
        if tuple(self.weights_by_record) != tuple(sorted(self.weights_by_record)):
            raise ValueError("record weights require canonical record-ID order")
        for identifier, weight in self.weights_by_record.items():
            if (
                len(identifier) != 64
                or any(char not in "0123456789abcdef" for char in identifier)
                or _fraction(_reload(weight, RationalV1)) <= 0
            ):
                raise ValueError("record weights require canonical IDs and positive rationals")
        for proportion, authorization in (
            (self.agreement, "audit-gate"),
            (self.false_pass, "audit-gate"),
            (self.reviewer_agreement, "reported-only"),
            *(
                (value, "false-fail-sensitivity")
                for value in self.false_fail_by_primary_arm.values()
            ),
        ):
            if _reload(proportion, WeightedProportionV1).authorization_use != authorization:
                raise ValueError("weighted proportion authorization differs from its metric role")
        for confusion in (self.judge_consensus_confusion, self.reviewer_confusion):
            _reload(confusion, WeightedConfusionV1)
        if self.weighted_kappa is not None and (
            not self.weighted_kappa.is_finite() or not -1 <= self.weighted_kappa <= 1
        ):
            raise ValueError("weighted kappa must be finite and within [-1, 1]")
        if self.model_audit_metric_sha256 != stable_digest(
            _METRIC_DOMAIN, self.model_dump(mode="json", exclude={_METRIC_DIGEST})
        ):
            raise ValueError("model audit metric self digest mismatch")
        return self


class ModelAuditGateV1(_AuditModel):
    generation_model: str
    agreement_interval_available: bool
    false_pass_interval_available: bool
    agreement_at_least_90_percent: bool
    false_pass_at_most_5_percent: bool
    no_unresolved_disagreement: bool
    critical_primary_coverage_complete: bool
    no_critical_primary_false_pass: bool
    passed: bool
    reasons: tuple[str, ...]

    @field_validator("reasons", mode="before")
    @classmethod
    def load_json_reasons(cls, value: object, info: ValidationInfo) -> object:
        return tuple(value) if info.mode == "json" and type(value) is list else value

    @model_validator(mode="after")
    def validate_gate(self) -> Self:
        reasons = tuple(reason for field, reason in _GATE_CONDITIONS if not getattr(self, field))
        if self.reasons != reasons or self.passed != (not reasons):
            raise ValueError("audit gate passed/reasons must retain every failed condition")
        return self


def _wilson_proportion(
    *,
    numerator: Fraction,
    denominator_weights: Sequence[Fraction],
    authorization: _Authorization,
    empty_stratum: bool = False,
    unresolved: bool = False,
) -> WeightedProportionV1:
    """The sole audit interval constructor; fixed two-sided design-weighted Wilson score."""

    if any(weight <= 0 for weight in denominator_weights):
        raise ValueError("Wilson denominator weights must be positive")
    sum_w = sum(denominator_weights, Fraction())
    sum_w_squared = sum((weight * weight for weight in denominator_weights), Fraction())
    effective_n = sum_w * sum_w / sum_w_squared if sum_w_squared else Fraction()
    reasons = tuple(
        reason
        for reason, failed in zip(
            _REASONS,
            (sum_w == 0, empty_stratum, sum_w > 0 and effective_n < 1, unresolved),
            strict=True,
        )
        if failed
    )
    point = n_eff = lower = upper = None
    if not reasons:
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            point = _decimal(numerator / sum_w)
            n_eff = _decimal(effective_n)
            z_squared = _Z * _Z
            scale = 1 + z_squared / n_eff
            center = (point + z_squared / (2 * n_eff)) / scale
            half = (
                _Z / scale * (point * (1 - point) / n_eff + z_squared / (4 * n_eff * n_eff)).sqrt()
            )
            lower = Decimal(0) if numerator == 0 else max(Decimal(0), center - half)
            upper = Decimal(1) if numerator == sum_w else min(Decimal(1), center + half)
    return WeightedProportionV1(
        numerator=_rational(numerator),
        denominator=_rational(sum_w),
        point=point,
        effective_n=n_eff,
        lower=lower,
        upper=upper,
        available=not reasons,
        z=_Z,
        interval_method="design-weighted-wilson-score-v1",
        authorization_use=authorization,
        unavailable_reasons=reasons,
    )


def _checked_design(
    manifest: AuditSampleManifestV1,
    population: Sequence[AuditPopulationRecordV1],
) -> tuple[AuditSampleManifestV1, tuple[AuditPopulationRecordV1, ...], dict[str, Fraction]]:
    manifest = _reload(manifest, AuditSampleManifestV1)
    records = tuple(_reload(record, AuditPopulationRecordV1) for record in population)
    by_id = {record.canonical_record_id: record for record in records}
    selected = set(manifest.ordered_selected_record_ids)
    if len(by_id) != len(records) or not selected <= set(by_id):
        raise ValueError("audit selected IDs require a unique, complete population join")
    expected_certainty = {identifier for identifier in selected if _is_certainty(by_id[identifier])}
    if set(manifest.certainty_record_ids) != expected_certainty:
        raise ValueError("audit selected certainty IDs disagree with the population")
    cells: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if not _is_certainty(record):
            cells[
                _cell_id(
                    record.generation_model,
                    record.locale,
                    record.arm,
                    record.blinded_judge_decision,
                )
            ].add(record.canonical_record_id)
    if not set(cells) <= {cell.cell_id for cell in manifest.cells}:
        raise ValueError("audit manifest lacks a population cell")
    weights = {identifier: Fraction(1) for identifier in expected_certainty}
    for cell in manifest.cells:
        population_ids = cells.get(cell.cell_id, set())
        sampled_ids = population_ids & selected
        if (
            set(cell.permutation) != population_ids
            or cell.noncertainty_population != len(population_ids)
            or cell.selected_noncertainty != len(sampled_ids)
            or set(cell.permutation[: cell.selected_noncertainty]) != sampled_ids
        ):
            raise ValueError("audit cell population/permutation/sample counts disagree")
        if sampled_ids:
            weight = Fraction(len(population_ids), len(sampled_ids))
            weights.update(dict.fromkeys(sampled_ids, weight))
    if set(weights) != selected:
        raise ValueError("audit design weights do not cover the selected population")
    return manifest, records, {identifier: weights[identifier] for identifier in sorted(weights)}


def _opaque_id(manifest: AuditSampleManifestV1, identifier: str) -> str:
    return stable_digest(
        "laconian-blind-audit-record-id-v1",
        {
            "campaign_id": manifest.campaign_id,
            "sample_manifest_sha256": manifest.sample_manifest_sha256,
            "canonical_record_id": identifier,
        },
    )


def _checked_adjudication(
    adjudication: AuditAdjudicationV1,
    manifest: AuditSampleManifestV1,
) -> tuple[AuditAdjudicationV1, dict[str, ConsensusLabelV1]]:
    adjudication = _reload(adjudication, AuditAdjudicationV1)
    core = adjudication.core
    bindings = manifest.protocol_bindings
    if (
        core.campaign_id != manifest.campaign_id
        or core.sample_manifest_sha256 != manifest.sample_manifest_sha256
    ):
        raise ValueError("adjudication core sample/campaign binding mismatch")
    for name in (
        "campaign_registry_sha256",
        "audit_reviewer_registry_sha256",
        "audit_commit_reveal_protocol_sha256",
        "audit_adjudication_protocol_sha256",
    ):
        if getattr(core, name) != getattr(bindings, name):
            raise ValueError(f"adjudication core protocol binding mismatch: {name}")
    proof = adjudication.adjudication_pr
    if proof.campaign_id != manifest.campaign_id or proof.proof_kind != "adjudication":
        raise ValueError("adjudication proof campaign/kind binding mismatch")
    for signoff in adjudication.signoffs:
        if (
            signoff.audit_reviewer_registry_sha256 != bindings.audit_reviewer_registry_sha256
            or signoff.adjudication_core_sha256 != core.adjudication_core_sha256
            or signoff.repository_id != proof.repository_id
            or signoff.pr_number != proof.pr_number
            or signoff.reviewed_head_sha != proof.head_sha
        ):
            raise ValueError("adjudication signoff core/protocol/proof binding mismatch")
    by_opaque_id = {label.audit_record_id: label for label in core.consensus}
    opaque_ids = {
        _opaque_id(manifest, identifier): identifier
        for identifier in manifest.ordered_selected_record_ids
    }
    if set(by_opaque_id) != set(opaque_ids):
        raise ValueError("adjudication consensus IDs do not exactly cover the sample")
    return adjudication, {
        identifier: by_opaque_id[opaque] for opaque, identifier in opaque_ids.items()
    }


def _checked_chains(
    chains: tuple[ReviewerChainV1, ReviewerChainV1],
    manifest: AuditSampleManifestV1,
    adjudication: AuditAdjudicationV1,
) -> tuple[ReviewerChainV1, ReviewerChainV1]:
    if type(chains) is not tuple or len(chains) != 2:
        raise TypeError("audit metrics require an exact reviewer-chain pair")
    checked = (_reload(chains[0], ReviewerChainV1), _reload(chains[1], ReviewerChainV1))
    reviewer_ids = tuple(chain.identity.reviewer_id for chain in checked)
    if (
        reviewer_ids != tuple(sorted(set(reviewer_ids)))
        or reviewer_ids != tuple(signoff.reviewer_id for signoff in adjudication.signoffs)
        or tuple(chain.reveal.reveal_sha256 for chain in checked)
        != adjudication.core.reveal_sha256s
        or checked[0].identity.reviewer_numeric_account_id
        == checked[1].identity.reviewer_numeric_account_id
    ):
        raise ValueError("audit reviewer identity/reveal bindings disagree")
    expected_ids = {
        _opaque_id(manifest, identifier) for identifier in manifest.ordered_selected_record_ids
    }
    for chain, signoff in zip(checked, adjudication.signoffs, strict=True):
        identity = chain.identity
        if (
            identity.audit_reviewer_registry_sha256
            != manifest.protocol_bindings.audit_reviewer_registry_sha256
            or signoff.reviewer_numeric_account_id != identity.reviewer_numeric_account_id
            or signoff.reviewer_login != identity.reviewer_login
        ):
            raise ValueError("reviewer identity registry/signoff binding mismatch")
        for parent in (chain.commitment.header, chain.reveal):
            if (
                parent.campaign_id != manifest.campaign_id
                or parent.sample_manifest_sha256 != manifest.sample_manifest_sha256
                or parent.reviewer_id != identity.reviewer_id
            ):
                raise ValueError("reviewer sample/campaign/identity binding mismatch")
            for name in (
                "campaign_registry_sha256",
                "audit_reviewer_registry_sha256",
                "audit_commit_reveal_protocol_sha256",
            ):
                if getattr(parent, name) != getattr(manifest.protocol_bindings, name):
                    raise ValueError(f"reviewer protocol binding mismatch: {name}")
        for proof, kind in ((chain.commitment_pr, "commitment"), (chain.reveal_pr, "reveal")):
            if (
                proof.campaign_id != manifest.campaign_id
                or proof.proof_kind != kind
                or proof.reviewer_id != identity.reviewer_id
            ):
                raise ValueError("reviewer proof campaign/identity/kind binding mismatch")
        if {label.audit_record_id for label in chain.reveal.labels} != expected_ids:
            raise ValueError("reviewer label IDs do not exactly cover the sample")
        if (
            chain.reveal.commitment_sha256 != chain.commitment.commitment_sha256
            or compute_commitment(
                header=chain.commitment.header,
                salt=bytes.fromhex(chain.reveal.salt_hex),
                exact_label_bytes=canonical_label_jsonl(chain.reveal.labels),
            )
            != chain.commitment.commitment_sha256
        ):
            raise ValueError("reviewer commitment/reveal binding mismatch")
    left = {label.audit_record_id: label.semantic_pass for label in checked[0].reveal.labels}
    right = {label.audit_record_id: label.semantic_pass for label in checked[1].reveal.labels}
    for consensus in adjudication.core.consensus:
        a, b = left[consensus.audit_record_id], right[consensus.audit_record_id]
        if (a == b) != (consensus.resolution == "reviewer-agreement") or (
            a == b and consensus.semantic_pass != a
        ):
            raise ValueError("consensus resolution disagrees with reviewer labels")
    return checked


def _confusion(rows: Sequence[tuple[Fraction, bool, bool | None]]) -> WeightedConfusionV1:
    counts = {
        (True, True): Fraction(),
        (True, False): Fraction(),
        (False, True): Fraction(),
        (False, False): Fraction(),
    }
    for weight, first, second in rows:
        if second is not None:
            counts[first, second] += weight
    return WeightedConfusionV1(
        pass_pass=_rational(counts[True, True]),
        pass_fail=_rational(counts[True, False]),
        fail_pass=_rational(counts[False, True]),
        fail_fail=_rational(counts[False, False]),
    )


def _kappa(confusion: WeightedConfusionV1) -> Decimal | None:
    pp, pf, fp, ff = (
        _fraction(getattr(confusion, name)) for name in WeightedConfusionV1.model_fields
    )
    total = pp + pf + fp + ff
    if not total:
        return None
    observed = (pp + ff) / total
    expected = ((pp + pf) * (pp + fp) + (fp + ff) * (pf + ff)) / (total * total)
    return _decimal((observed - expected) / (1 - expected)) if expected != 1 else None


def compute_model_audit_metrics(
    *,
    model: str,
    manifest: AuditSampleManifestV1,
    population: Sequence[AuditPopulationRecordV1],
    chains: tuple[ReviewerChainV1, ReviewerChainV1],
    adjudication: AuditAdjudicationV1,
) -> ModelAuditMetricsV1:
    """Compute after independent full ``verify_audit_chain``; this does not certify provenance.

    ``weights_by_record`` uses canonical population record IDs. Authorizing judge
    metrics use only this model's if/concise arms; reviewer metrics describe all its
    sampled arms. Both locales of each primary arm are required even if absent.
    """

    if type(model) is not str or not model:
        raise ValueError("audit metrics require a nonempty exact generation model")
    manifest, records, weights = _checked_design(manifest, population)
    adjudication, consensus = _checked_adjudication(adjudication, manifest)
    chains = _checked_chains(chains, manifest, adjudication)
    selected = tuple(
        record
        for record in records
        if record.generation_model == model and record.canonical_record_id in weights
    )
    primary = tuple(record for record in selected if record.arm in _PRIMARY_ARMS)
    sampled_strata = {(record.locale, record.arm) for record in selected}
    empty_primary = any(
        (locale, arm) not in sampled_strata for locale in ("en", "ru") for arm in _PRIMARY_ARMS
    )
    judge_rows = [
        (
            weights[record.canonical_record_id],
            record.blinded_judge_decision,
            consensus[record.canonical_record_id].semantic_pass,
        )
        for record in primary
    ]
    confusion = _confusion(judge_rows)
    agreement = _wilson_proportion(
        numerator=_fraction(confusion.pass_pass) + _fraction(confusion.fail_fail),
        denominator_weights=[weight for weight, _, _ in judge_rows],
        authorization="audit-gate",
        empty_stratum=empty_primary,
        unresolved=any(second is None for _, _, second in judge_rows),
    )
    false_pass = _wilson_proportion(
        numerator=_fraction(confusion.pass_fail),
        denominator_weights=[weight for weight, judge, _ in judge_rows if judge],
        authorization="audit-gate",
        empty_stratum=empty_primary,
        unresolved=any(second is None for _, judge, second in judge_rows if judge),
    )
    false_fails: dict[_PrimaryArm, WeightedProportionV1] = {}
    for arm in _PRIMARY_ARMS:
        failures = tuple(
            record for record in primary if record.arm == arm and not record.blinded_judge_decision
        )
        false_fails[arm] = _wilson_proportion(
            numerator=sum(
                (
                    weights[record.canonical_record_id]
                    for record in failures
                    if consensus[record.canonical_record_id].semantic_pass is True
                ),
                Fraction(),
            ),
            denominator_weights=[weights[record.canonical_record_id] for record in failures],
            authorization="false-fail-sensitivity",
            empty_stratum=any((locale, arm) not in sampled_strata for locale in ("en", "ru")),
            unresolved=any(
                consensus[record.canonical_record_id].semantic_pass is None for record in failures
            ),
        )
    reviewers = [
        {label.audit_record_id: label.semantic_pass for label in chain.reveal.labels}
        for chain in chains
    ]
    reviewer_rows = [
        (
            weights[record.canonical_record_id],
            reviewers[0][_opaque_id(manifest, record.canonical_record_id)],
            reviewers[1][_opaque_id(manifest, record.canonical_record_id)],
        )
        for record in selected
    ]
    reviewer_confusion = _confusion(reviewer_rows)
    reviewer_agreement = _wilson_proportion(
        numerator=_fraction(reviewer_confusion.pass_pass) + _fraction(reviewer_confusion.fail_fail),
        denominator_weights=[weight for weight, _, _ in reviewer_rows],
        authorization="reported-only",
        empty_stratum=any(
            (record.locale, record.arm) not in sampled_strata
            for record in records
            if record.generation_model == model
        ),
    )
    selected_ids = {record.canonical_record_id for record in selected}
    payload = {
        "generation_model": model,
        "protocol_bindings": manifest.protocol_bindings.model_dump(mode="json"),
        "weights_by_record": {
            identifier: _rational(weight).model_dump(mode="json")
            for identifier, weight in weights.items()
            if identifier in selected_ids
        },
        "judge_consensus_confusion": confusion.model_dump(mode="json"),
        "reviewer_confusion": reviewer_confusion.model_dump(mode="json"),
        "agreement": agreement.model_dump(mode="json"),
        "false_pass": false_pass.model_dump(mode="json"),
        "false_fail_by_primary_arm": {
            arm: value.model_dump(mode="json") for arm, value in false_fails.items()
        },
        "reviewer_agreement": reviewer_agreement.model_dump(mode="json"),
        "weighted_kappa": None if (kappa := _kappa(reviewer_confusion)) is None else str(kappa),
    }
    return ModelAuditMetricsV1.model_validate_json(
        canonical_json_v1(
            {
                **payload,
                _METRIC_DIGEST: stable_digest(_METRIC_DOMAIN, payload),
            }
        )
    )


def evaluate_model_audit_gate(
    *,
    metrics: ModelAuditMetricsV1,
    manifest: AuditSampleManifestV1,
    population: Sequence[AuditPopulationRecordV1],
    adjudication: AuditAdjudicationV1,
) -> ModelAuditGateV1:
    """Evaluate verified/recomputed metrics under the same source-verification precondition.

    Thresholds compare exact point fractions; interval availability is a separate
    requirement. Only this model's primary records and critical warnings participate.
    """

    metrics = _reload(metrics, ModelAuditMetricsV1)
    manifest, records, weights = _checked_design(manifest, population)
    _, consensus = _checked_adjudication(adjudication, manifest)
    if metrics.protocol_bindings != manifest.protocol_bindings:
        raise ValueError("audit metrics protocol bindings differ from the sample parent")
    model_records = tuple(
        record for record in records if record.generation_model == metrics.generation_model
    )
    expected_weights = {
        record.canonical_record_id: weights[record.canonical_record_id]
        for record in model_records
        if record.canonical_record_id in weights
    }
    if {
        identifier: _fraction(value) for identifier, value in metrics.weights_by_record.items()
    } != expected_weights:
        raise ValueError("audit metric record weights differ from the model sample")
    primary = tuple(record for record in model_records if record.arm in _PRIMARY_ARMS)
    sampled_primary = tuple(record for record in primary if record.canonical_record_id in weights)
    critical = tuple(record for record in primary if _is_certainty(record))
    agreement_denominator = _fraction(metrics.agreement.denominator)
    false_pass_denominator = _fraction(metrics.false_pass.denominator)
    flags = {
        "agreement_interval_available": metrics.agreement.available,
        "false_pass_interval_available": metrics.false_pass.available,
        "agreement_at_least_90_percent": agreement_denominator > 0
        and _fraction(metrics.agreement.numerator) / agreement_denominator >= Fraction(9, 10),
        "false_pass_at_most_5_percent": false_pass_denominator > 0
        and _fraction(metrics.false_pass.numerator) / false_pass_denominator <= Fraction(1, 20),
        "no_unresolved_disagreement": all(
            consensus[record.canonical_record_id].semantic_pass is not None
            for record in sampled_primary
        ),
        "critical_primary_coverage_complete": all(
            record.canonical_record_id in weights for record in critical
        ),
        "no_critical_primary_false_pass": all(
            consensus[record.canonical_record_id].semantic_pass is not False
            for record in critical
            if record.canonical_record_id in weights
        ),
    }
    reasons = tuple(reason for field, reason in _GATE_CONDITIONS if not flags[field])
    return ModelAuditGateV1(
        generation_model=metrics.generation_model,
        **flags,
        passed=not reasons,
        reasons=reasons,
    )


__all__ = (
    "ModelAuditGateV1",
    "ModelAuditMetricsV1",
    "WeightedConfusionV1",
    "WeightedProportionV1",
    "compute_model_audit_metrics",
    "evaluate_model_audit_gate",
)
