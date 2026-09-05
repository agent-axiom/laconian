"""Source-replayed audit and analysis publication, with deterministic public prose.

The dataclass wrappers are containers, not authority. Every public consumer takes a
fresh provider snapshot and reconstructs all audit components before calculation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, ClassVar, Literal, Self, TypeVar, cast, get_args, get_origin
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from laconian_eval.benchmark.aggregation import (
    AggregatedModelV1,
    ArmName,
    CachePolicyStatusV1,
    CostAvailabilityV1,
    GateName,
    PairDenominatorsV1,
    PlannedObservationV1,
    aggregate_verified_evidence,
)
from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.benchmark.audit_commit_reveal import (
    AuditAdjudicationV1,
    AuditGitObjectArchiveV1,
    AuditPullRequestEvidenceSourceV1,
    ExactGitHubReviewRecordV1,
    ExactGitHubReviewSourceV1,
    ReviewerChainV1,
    _repository_authority,
    _review_record_from_source,
    canonical_label_jsonl,
    verify_audit_chain,
)
from laconian_eval.benchmark.audit_metrics import (
    ModelAuditGateV1,
    ModelAuditMetricsV1,
    _load_json_decimal,
    compute_model_audit_metrics,
    evaluate_model_audit_gate,
)
from laconian_eval.benchmark.audit_sampling import (
    AuditSampleManifestV1,
    BlindAuditPacketV1,
    VerifiedAuditSampleRootV1,
    _audit_sample_root_digest,
    _verify_audit_sample_from_checked,
    _write_sample_member,
    load_verified_audit_sample_root,
)
from laconian_eval.benchmark.bootstrap import (
    BootstrapIntervalV1,
    BootstrapVectorsV1,
    _verify_cluster_vectors,
    make_cluster_vectors,
    type7_quantile,
)
from laconian_eval.benchmark.context import (
    BenchmarkProtocolBindingsV1,
    protocol_bindings_from_context,
)
from laconian_eval.benchmark.outcomes import (
    ModelOutcomeV1,
    OutcomeEvidenceV1,
    classify_model_outcome,
)
from laconian_eval.benchmark.protocol_review import _preflight_exact_model_owners_v1
from laconian_eval.benchmark.provider_evidence import (
    VerifiedAuditPopulationV1,
    VerifiedBenchmarkProviderEvidenceV1,
    _canonical_population_jsonl,
    _load_verified_audit_population_from_bytes,
    _revalidate_verified_audit_population_v1,
    _revalidate_verified_provider_evidence_v1,
    _run_teardown,
)
from laconian_eval.benchmark.seeds import derive_seed128
from laconian_eval.benchmark.sensitivity import (
    FalseFailCandidateV1,
    FalseFailLimitV1,
    SensitivityResultV1,
    _reject_undeclared_model_fields,
    derive_false_fail_limit,
    enumerate_sensitivity_exact,
    search_sensitivity_exact,
)
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.filesystem import (
    DestinationCollisionError,
    FilesystemPosixOps,
    OwnedStaging,
    cleanup_owned_staging,
    create_owned_staging,
    publish_owned_staging,
)
from laconian_eval.capsule.posix import PosixOps

Sha256 = Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
Vector36 = Annotated[tuple[Sha256, ...], Field(min_length=36, max_length=36)]
PRSources = tuple[
    AuditPullRequestEvidenceSourceV1,
    AuditPullRequestEvidenceSourceV1,
    AuditPullRequestEvidenceSourceV1,
    AuditPullRequestEvidenceSourceV1,
    AuditPullRequestEvidenceSourceV1,
]
Chains = tuple[ReviewerChainV1, ReviewerChainV1]
ReviewSources = tuple[ExactGitHubReviewSourceV1, ExactGitHubReviewSourceV1]
ReviewRecords = tuple[ExactGitHubReviewRecordV1, ExactGitHubReviewRecordV1]
Metrics = tuple[ModelAuditMetricsV1, ModelAuditMetricsV1, ModelAuditMetricsV1]
_T = TypeVar("_T", bound=BaseModel)
_ARMS: tuple[ArmName, ...] = ("baseline", "caveman", "if", "concise")
_PRIMARY: tuple[Literal["if", "concise"], Literal["if", "concise"]] = ("if", "concise")
_COSTS: tuple[CostAvailabilityV1, ...] = (
    "trusted_usage",
    "definitely_rejected_zero",
    "retained_worst_case",
)
_CACHE: tuple[CachePolicyStatusV1, ...] = (
    "conformant_zero_write",
    "terminal_no_usage",
    "missing_write_detail",
    "forbidden_nonzero_write",
)
_VECTOR_FIELDS = (
    "ordered_generation_capsule_sha256s",
    "ordered_hard_score_request_set_sha256s",
    "ordered_judge_request_attachment_sha256s",
    "ordered_judge_attempt_boundary_sha256s",
    "ordered_judge_attachment_sha256s",
)


def _payload(value: BaseModel) -> dict[str, Any]:
    return cast(dict[str, Any], type(value).__pydantic_serializer__.to_python(value, mode="json"))


def _bytes(value: BaseModel) -> bytes:
    return canonical_json(_payload(value)) + b"\n"


def _checked(value: _T, owner: type[_T]) -> _T:
    if type(value) is not owner:
        raise TypeError(f"expected exact {owner.__name__} owner")
    _preflight_exact_model_owners_v1(value, owner)
    _reject_undeclared_model_fields(value)
    return owner.model_validate_json(canonical_json(_payload(value)), strict=True)


class _ReportModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        validate_default=True,
    )

    @model_validator(mode="before")
    @classmethod
    def reject_python_substitutions(cls, value: object, info: ValidationInfo) -> object:
        if info.mode == "json":
            return value
        if isinstance(value, BaseModel):
            _preflight_exact_model_owners_v1(value, cls)
            _reject_undeclared_model_fields(value)
        elif isinstance(value, Mapping) and type(value) is not dict:
            raise TypeError("reporting model input requires an exact dict")
        elif type(value) is dict:
            for name, candidate in value.items():
                if name in cls.model_fields:
                    _preflight_exact_model_owners_v1(candidate, cls.model_fields[name].annotation)
                    if isinstance(candidate, BaseModel):
                        _reject_undeclared_model_fields(candidate)
        return value

    @field_validator("*", mode="before")
    @classmethod
    def load_json_tuples(cls, value: object, info: ValidationInfo) -> object:
        def convert(candidate: object, annotation: object) -> object:
            if get_origin(annotation) is Annotated:
                annotation = get_args(annotation)[0]
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                if isinstance(candidate, BaseModel):
                    return _checked(candidate, annotation)
                if info.mode == "json" and type(candidate) is dict:
                    # Restore the nested owner's JSON mode, including strict tuples/enums.
                    return annotation.model_validate_json(canonical_json(candidate), strict=True)
            args = get_args(annotation)
            if get_origin(annotation) is Mapping and type(candidate) is dict:
                return {key: convert(item, args[1]) for key, item in candidate.items()}
            if get_origin(annotation) is tuple and (
                type(candidate) is tuple or (info.mode == "json" and type(candidate) is list)
            ):
                return tuple(
                    convert(
                        item,
                        args[0]
                        if len(args) == 2 and args[1] is Ellipsis
                        else args[index]
                        if index < len(args)
                        else Any,
                    )
                    for index, item in enumerate(candidate)
                )
            return candidate

        if info.field_name is not None:
            return convert(value, cls.model_fields[info.field_name].annotation)
        return value

    @model_validator(mode="after")
    def validate_exact_tree(self) -> Self:
        _preflight_exact_model_owners_v1(self, type(self))
        _reject_undeclared_model_fields(self)
        return self


class _SealedModel(_ReportModel):
    _domain: ClassVar[str]
    _digest_field: ClassVar[str]

    @model_validator(mode="after")
    def validate_seal(self) -> Self:
        payload = _payload(self)
        digest = payload.pop(self._digest_field)
        if digest != stable_digest(self._domain, payload):
            raise ValueError(f"{self._digest_field} self digest mismatch")
        return self


def _seal(owner: type[_T], payload: dict[str, Any]) -> _T:
    sealed = cast(type[_SealedModel], owner)
    return owner.model_validate_json(
        canonical_json(
            {
                **payload,
                sealed._digest_field: stable_digest(sealed._domain, payload),
            }
        ),
        strict=True,
    )


class DistributionSummaryV1(_ReportModel):
    unit: Literal["tokens", "usd", "milliseconds", "characters"]
    observed_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    minimum: Decimal | None
    median: Decimal | None
    maximum: Decimal | None

    @field_validator("minimum", "median", "maximum", mode="before")
    @classmethod
    def load_decimal(cls, value: object, info: ValidationInfo) -> object:
        return _load_json_decimal(value, info)

    @model_validator(mode="after")
    def validate_distribution(self) -> Self:
        values = (self.minimum, self.median, self.maximum)
        if not self.observed_count:
            if any(value is not None for value in values):
                raise ValueError("empty distribution requires null extrema")
        elif any(value is None or not value.is_finite() or value < 0 for value in values):
            raise ValueError("observed distribution requires finite nonnegative extrema")
        elif (
            not cast(Decimal, self.minimum)
            <= cast(Decimal, self.median)
            <= cast(Decimal, self.maximum)
        ):
            raise ValueError("distribution minimum/median/maximum order mismatch")
        if self.observed_count == 1 and len(set(values)) != 1:
            raise ValueError("one observation requires identical extrema")
        return self


class BootstrapArtifactV1(_ReportModel):
    schema_version: Literal["bootstrap-artifact-v1"]
    metadata: BootstrapVectorsV1
    indices: Annotated[
        tuple[
            Annotated[
                tuple[Annotated[int, Field(ge=0, lt=12)], ...], Field(min_length=12, max_length=12)
            ],
            ...,
        ],
        Field(min_length=10_000, max_length=10_000),
    ]
    bootstrap_artifact_sha256: Sha256

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        matrix = np.array(self.indices, dtype=np.uint8, order="C")
        _verify_cluster_vectors(self.metadata, matrix)
        if self.bootstrap_artifact_sha256 != _bootstrap_digest(self.metadata, matrix):
            raise ValueError("bootstrap artifact raw matrix digest mismatch")
        return self


def _bootstrap_digest(metadata: BootstrapVectorsV1, matrix: NDArray[np.uint8]) -> str:
    return hashlib.sha256(
        b"laconian-bootstrap-artifact-v1\0"
        + canonical_json(_payload(metadata))
        + b"\0"
        + matrix.tobytes(order="C")
    ).hexdigest()


def _bootstrap_from_checked(provider: VerifiedBenchmarkProviderEvidenceV1) -> BootstrapArtifactV1:
    index = provider.index
    uids = tuple(
        sorted(
            {row.scenario_uid for capsule in provider.generation_evidence for row in capsule.plan},
            key=str.encode,
        )
    )
    metadata, matrix = make_cluster_vectors(
        seed=derive_seed128(
            "laconian-bootstrap-v1",
            index.campaign_seed,
            index.input_tag_commit,
            index.judge_protocol_sha256,
        ),
        scenario_uids=uids,
    )
    return BootstrapArtifactV1(
        schema_version="bootstrap-artifact-v1",
        metadata=metadata,
        indices=tuple(tuple(int(value) for value in row) for row in matrix),
        bootstrap_artifact_sha256=_bootstrap_digest(metadata, matrix),
    )


def build_bootstrap_artifact(
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> BootstrapArtifactV1:
    return _bootstrap_from_checked(_revalidate_verified_provider_evidence_v1(provider_evidence))


def _relative_path(path: str) -> str:
    parsed = PurePosixPath(path)
    if (
        not path
        or parsed.is_absolute()
        or str(parsed) != path
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
    ):
        raise ValueError("noncanonical relative evidence path")
    path.encode("utf-8")
    return path


class ChecksumEntryV1(_ReportModel):
    relative_path: str
    byte_length: int = Field(ge=0)
    sha256: Sha256

    @field_validator("relative_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _relative_path(value)


class ChecksumManifestV1(_SealedModel):
    schema_version: Literal["analysis-checksums-v1"]
    entries: tuple[ChecksumEntryV1, ...]
    checksums_sha256: Sha256
    _domain = "laconian-analysis-checksums-v1"
    _digest_field = "checksums_sha256"

    @model_validator(mode="after")
    def validate_entries(self) -> Self:
        paths = tuple(row.relative_path for row in self.entries)
        if paths != ("analysis/analysis.json", "analysis/bootstrap.json", "analysis/report.md"):
            raise ValueError("analysis checksums require exact sorted noncyclic artifact paths")
        return self


class DescriptiveUsageV1(_ReportModel):
    input_tokens: DistributionSummaryV1
    visible_output_tokens: DistributionSummaryV1
    reasoning_tokens: DistributionSummaryV1
    billed_output_tokens: DistributionSummaryV1
    total_tokens: DistributionSummaryV1
    ordinary_uncached_input_tokens: DistributionSummaryV1
    cache_read_tokens: DistributionSummaryV1
    cache_write_tokens: DistributionSummaryV1
    trusted_usage_cost_usd: DistributionSummaryV1
    definitely_rejected_zero_cost_usd: DistributionSummaryV1
    retained_worst_case_exposure_usd: DistributionSummaryV1
    cost_availability_counts: Mapping[CostAvailabilityV1, int]
    cache_policy_status_counts: Mapping[CachePolicyStatusV1, int]
    latency_ms: DistributionSummaryV1
    output_characters: DistributionSummaryV1

    @model_validator(mode="after")
    def validate_usage(self) -> Self:
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, DistributionSummaryV1):
                unit = (
                    "usd"
                    if name.endswith("_usd")
                    else "milliseconds"
                    if name == "latency_ms"
                    else "characters"
                    if name == "output_characters"
                    else "tokens"
                )
                if value.unit != unit or value.observed_count + value.missing_count != 120:
                    raise ValueError("usage distributions require correct units and 120 rows")
        for counts, keys in (
            (self.cost_availability_counts, _COSTS),
            (self.cache_policy_status_counts, _CACHE),
        ):
            if (
                set(counts) != set(keys)
                or any(type(n) is not int or n < 0 for n in counts.values())
                or sum(counts.values()) != 120
            ):
                raise ValueError("usage status maps require all closed keys and 120 exact counts")
        for name, basis in (
            ("trusted_usage_cost_usd", "trusted_usage"),
            ("definitely_rejected_zero_cost_usd", "definitely_rejected_zero"),
            ("retained_worst_case_exposure_usd", "retained_worst_case"),
        ):
            if (
                getattr(self, name).observed_count
                != self.cost_availability_counts[cast(CostAvailabilityV1, basis)]
            ):
                raise ValueError("usage cost distribution basis differs from availability count")
        return self


def _assignment_count(limits: tuple[FalseFailLimitV1, FalseFailLimitV1]) -> int:
    return math.prod(
        sum(
            math.comb(limit.optional_candidates, j)
            for j in range(limit.k_max_reclassified - limit.d_known_false_fail + 1)
        )
        for limit in limits
    )


class ModelAnalysisV1(_ReportModel):
    generation_model: str
    hard_denominators: PairDenominatorsV1
    semantic_denominators: PairDenominatorsV1
    hard_pass_by_arm: Mapping[ArmName, BootstrapIntervalV1]
    semantic_pass_by_arm: Mapping[ArmName, BootstrapIntervalV1]
    hard_primary_difference: BootstrapIntervalV1
    semantic_primary_difference: BootstrapIntervalV1
    hard_visible_delta: BootstrapIntervalV1
    semantic_visible_delta: BootstrapIntervalV1
    usage_by_arm: Mapping[ArmName, DescriptiveUsageV1]
    audit_metrics: ModelAuditMetricsV1
    audit_gate: ModelAuditGateV1
    false_fail_limits: tuple[FalseFailLimitV1, FalseFailLimitV1]
    sensitivity: SensitivityResultV1
    outcome: ModelOutcomeV1

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        for mapping in (self.hard_pass_by_arm, self.semantic_pass_by_arm, self.usage_by_arm):
            if set(mapping) != set(_ARMS):
                raise ValueError("model analysis requires all four arms")
        if (
            not self.generation_model
            or any(
                item.generation_model != self.generation_model
                for item in (
                    self.audit_metrics,
                    self.audit_gate,
                    self.sensitivity,
                    *self.false_fail_limits,
                )
            )
            or tuple(limit.arm for limit in self.false_fail_limits) != _PRIMARY
        ):
            raise ValueError("analysis model and ordered primary arms differ")
        digest = self.audit_metrics.model_audit_metric_sha256
        if any(
            item.model_audit_metric_sha256 != digest
            for item in (*self.false_fail_limits, self.sensitivity)
        ):
            raise ValueError("analysis requires one shared model audit metric digest")
        sensitivity = self.sensitivity
        if all(limit.estimable for limit in self.false_fail_limits):
            if sensitivity.assignment_count != _assignment_count(self.false_fail_limits):
                raise ValueError("sensitivity assignment count differs from exact A formula")
        elif any(
            (
                sensitivity.assignment_count,
                sensitivity.visited_nodes,
                sensitivity.evaluated_assignments,
                sensitivity.search_exhausted,
            )
        ) or any(
            getattr(sensitivity, field) is not None
            for field in (
                "semantic_min_lower",
                "semantic_max_upper",
                "token_min_lower",
                "token_max_upper",
                "certificate_sha256",
                "exhaustion_reason",
            )
        ):
            raise ValueError("unestimable sensitivity requires zero counters and null results")
        return self


class _BoundSeal(_SealedModel):
    @model_validator(mode="after")
    def validate_repeated_bindings(self) -> Self:
        bindings = cast(BenchmarkProtocolBindingsV1, self.__dict__["protocol_bindings"])
        for field in BenchmarkProtocolBindingsV1.model_fields:
            if field in type(self).model_fields and getattr(self, field) != getattr(
                bindings, field
            ):
                raise ValueError(f"repeated protocol binding differs: {field}")
        for field in _VECTOR_FIELDS:
            if field in type(self).model_fields and len(set(getattr(self, field))) != 36:
                raise ValueError("exact 36 unique source parents required")
        return self


class CampaignAnalysisV1(_BoundSeal):
    schema_version: Literal["campaign-analysis-v1"]
    campaign_id: str
    input_tag_commit: Annotated[str, Field(pattern="^[0-9a-f]{40}$")]
    audit_reviewer_registry_sha256: Sha256
    protocol_reviewer_registry_sha256: Sha256
    protocol_attestations_root: Sha256
    workflow_root: Sha256
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: Sha256
    generation_context_index_sha256: Sha256
    provider_projection_root: Sha256
    hard_score_protocol_sha256: Sha256
    judge_prompt_sha256: Sha256
    judge_schema_sha256: Sha256
    audit_sampling_protocol_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256
    audit_adjudication_protocol_sha256: Sha256
    benchmark_provider_evidence_sha256: Sha256
    ordered_generation_capsule_sha256s: Vector36
    ordered_hard_score_request_set_sha256s: Vector36
    ordered_judge_request_attachment_sha256s: Vector36
    judge_attempt_root_index_sha256: Sha256
    ordered_judge_attempt_boundary_sha256s: Vector36
    ordered_judge_attachment_sha256s: Vector36
    audit_evidence_sha256: Sha256
    bootstrap_vectors_sha256: Sha256
    statistical_protocol_sha256: Sha256
    audit_protocol_sha256: Sha256
    audit_sample_manifest: AuditSampleManifestV1
    models: tuple[ModelAnalysisV1, ModelAnalysisV1, ModelAnalysisV1]
    limitations: tuple[str, ...]
    campaign_analysis_sha256: Sha256
    _domain = "laconian-campaign-analysis-v1"
    _digest_field = "campaign_analysis_sha256"

    @model_validator(mode="after")
    def validate_campaign(self) -> Self:
        names = tuple(model.generation_model for model in self.models)
        if names != tuple(sorted(set(names), key=str.encode)) or len(names) != 3:
            raise ValueError("campaign requires three distinct UTF-8 ordered models")
        if (
            self.audit_sample_manifest.campaign_id != self.campaign_id
            or self.audit_sample_manifest.protocol_bindings != self.protocol_bindings
            or any(
                model.audit_metrics.protocol_bindings != self.protocol_bindings
                for model in self.models
            )
        ):
            raise ValueError("campaign audit manifest/metrics protocol binding differs")
        if self.limitations != _LIMITATIONS:
            raise ValueError("campaign limitations must be fixed publication prose")
        return self


class AuditEvidenceAttachmentV1(_BoundSeal):
    schema_version: Literal["verified-audit-evidence-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: Sha256
    protocol_reviewer_registry_sha256: Sha256
    protocol_attestations_root: Sha256
    workflow_root: Sha256
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: Sha256
    generation_context_index_sha256: Sha256
    provider_projection_root: Sha256
    hard_score_protocol_sha256: Sha256
    judge_prompt_sha256: Sha256
    judge_schema_sha256: Sha256
    statistical_protocol_sha256: Sha256
    audit_protocol_sha256: Sha256
    audit_sampling_protocol_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256
    audit_adjudication_protocol_sha256: Sha256
    provider_evidence_index_sha256: Sha256
    benchmark_provider_evidence_sha256: Sha256
    judge_attempt_root_index_sha256: Sha256
    ordered_generation_capsule_sha256s: Vector36
    ordered_hard_score_request_set_sha256s: Vector36
    ordered_judge_request_attachment_sha256s: Vector36
    ordered_judge_attempt_boundary_sha256s: Vector36
    ordered_judge_attachment_sha256s: Vector36
    population_attachment_sha256: Sha256
    sample_manifest_sha256: Sha256
    blind_packet_sha256: Sha256
    audit_git_object_archive_sha256: Sha256
    pull_request_source_sha256s: tuple[Sha256, Sha256, Sha256, Sha256, Sha256]
    github_review_source_sha256s: tuple[Sha256, Sha256]
    commitment_sha256s: tuple[Sha256, Sha256]
    reveal_sha256s: tuple[Sha256, Sha256]
    reviewer_chain_proof_sha256s: tuple[Sha256, Sha256]
    adjudication_core_sha256: Sha256
    signoff_proof_sha256s: tuple[Sha256, Sha256]
    exact_github_review_record_sha256s: tuple[Sha256, Sha256]
    adjudication_sha256: Sha256
    model_audit_metric_sha256s: tuple[Sha256, Sha256, Sha256]
    audit_evidence_sha256: Sha256
    _domain = "laconian-verified-audit-evidence-v1"
    _digest_field = "audit_evidence_sha256"


class AnalysisEvidenceAttachmentV1(_BoundSeal):
    schema_version: Literal["verified-analysis-evidence-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: Sha256
    protocol_reviewer_registry_sha256: Sha256
    protocol_attestations_root: Sha256
    workflow_root: Sha256
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: Sha256
    generation_context_index_sha256: Sha256
    provider_projection_root: Sha256
    provider_evidence_index_sha256: Sha256
    benchmark_provider_evidence_sha256: Sha256
    hard_score_protocol_sha256: Sha256
    judge_prompt_sha256: Sha256
    judge_schema_sha256: Sha256
    statistical_protocol_sha256: Sha256
    audit_protocol_sha256: Sha256
    audit_sampling_protocol_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256
    audit_adjudication_protocol_sha256: Sha256
    audit_evidence_sha256: Sha256
    campaign_analysis_sha256: Sha256
    bootstrap_artifact_sha256: Sha256
    report_sha256: Sha256
    checksums_sha256: Sha256
    analysis_evidence_sha256: Sha256
    _domain = "laconian-verified-analysis-evidence-v1"
    _digest_field = "analysis_evidence_sha256"


@dataclass(frozen=True, slots=True)
class VerifiedAuditEvidenceV1:
    attachment: AuditEvidenceAttachmentV1
    population: VerifiedAuditPopulationV1
    manifest: AuditSampleManifestV1
    packet: BlindAuditPacketV1
    audit_git_object_archive: AuditGitObjectArchiveV1
    pull_request_sources: PRSources
    reviewer_chains: Chains
    github_review_sources: ReviewSources
    github_review_records: ReviewRecords
    adjudication: AuditAdjudicationV1
    metrics: Metrics


@dataclass(frozen=True, slots=True)
class VerifiedAnalysisEvidenceV1:
    attachment: AnalysisEvidenceAttachmentV1
    audit: VerifiedAuditEvidenceV1
    analysis: CampaignAnalysisV1
    bootstrap: BootstrapArtifactV1
    report_bytes: bytes
    checksums: ChecksumManifestV1


_LIMITATIONS = (
    "Bootstrap describes scenario-superpopulation variation conditional on this fixed campaign.",
    "Nominal 95 percent percentile coverage is approximate with 12 clusters.",
    "Results do not generalize to new models, provider versions, prompts, domains, "
    "or time periods.",
    "Visible tokens describe visible responses; billed output, total tokens and costs "
    "have separate bases.",
    "Baseline and Caveman are exploratory only. The three generation models are assessed "
    "independently.",
    "Cardinality pruning v1 only; semantic and token dominance are disabled. Spaces above "
    "4096 reach either the 1000000 visited-node cap or the 4096 bootstrap-evaluation cap "
    "and are inconclusive until a separately versioned witness is available.",
)


def _provider_fields(
    owner: type[BaseModel], provider: VerifiedBenchmarkProviderEvidenceV1
) -> dict[str, Any]:
    """Select repeated fields exclusively from the fixed, checked provider parents."""
    index = _payload(provider.index)
    index["benchmark_provider_evidence_sha256"] = (
        provider.projection.benchmark_provider_evidence_sha256
    )
    index["protocol_bindings"] = _payload(
        protocol_bindings_from_context(provider.generation_context.index)
    )
    return {
        name: index[name]
        for name in owner.model_fields
        if name in index and name != "schema_version"
    }


def _check_provider_fields(value: BaseModel, provider: VerifiedBenchmarkProviderEvidenceV1) -> None:
    payload = _payload(value)
    for field, expected in _provider_fields(type(value), provider).items():
        if canonical_json(payload[field]) != canonical_json(expected):
            raise ValueError(f"evidence differs from fixed provider parent: {field}")


def _sample(
    population: VerifiedAuditPopulationV1,
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
) -> VerifiedAuditSampleRootV1:
    return VerifiedAuditSampleRootV1(
        population, manifest, packet, _audit_sample_root_digest(population, manifest, packet)
    )


def _checked_tuple(values: tuple[_T, ...], owner: type[_T], length: int) -> tuple[_T, ...]:
    if type(values) is not tuple or len(values) != length:
        raise TypeError(f"expected exact {length}-member {owner.__name__} tuple")
    return tuple(_checked(value, owner) for value in values)


def _derive_audit(
    *,
    provider: VerifiedBenchmarkProviderEvidenceV1,
    sample: VerifiedAuditSampleRootV1,
    archive: AuditGitObjectArchiveV1,
    sources: PRSources,
    chains: Chains,
    review_sources: ReviewSources,
    adjudication: AuditAdjudicationV1,
    metrics: Metrics,
) -> VerifiedAuditEvidenceV1:
    if type(sample) is not VerifiedAuditSampleRootV1:
        raise TypeError("expected exact verified audit sample")
    population = _revalidate_verified_audit_population_v1(sample.population)
    manifest = _checked(sample.manifest, AuditSampleManifestV1)
    packet = _checked(sample.packet, BlindAuditPacketV1)
    fresh_sample = _sample(population, manifest, packet)
    if sample.audit_sample_root_sha256 != fresh_sample.audit_sample_root_sha256:
        raise ValueError("sample root binding differs")
    _verify_audit_sample_from_checked(
        manifest, packet, population=population, provider_evidence=provider
    )
    archive = _checked(archive, AuditGitObjectArchiveV1)
    sources = cast(PRSources, _checked_tuple(sources, AuditPullRequestEvidenceSourceV1, 5))
    chains = cast(Chains, _checked_tuple(chains, ReviewerChainV1, 2))
    review_sources = cast(
        ReviewSources, _checked_tuple(review_sources, ExactGitHubReviewSourceV1, 2)
    )
    adjudication = _checked(adjudication, AuditAdjudicationV1)
    metrics = cast(Metrics, _checked_tuple(metrics, ModelAuditMetricsV1, 3))
    verify_audit_chain(
        chains=chains,
        adjudication=adjudication,
        sample=fresh_sample,
        provider_evidence=provider,
        audit_git_object_archive=archive,
        pull_request_sources=sources,
        github_review_sources=review_sources,
    )
    repository_id, owner, name = _repository_authority(provider)
    records = cast(
        ReviewRecords,
        tuple(
            _review_record_from_source(
                source,
                repository_id=repository_id,
                repository_owner=owner,
                repository_name=name,
            )
            for source in review_sources
        ),
    )
    if len({record.review_id for record in records}) != 2:
        raise ValueError("audit requires two distinct exact review IDs")
    models = sorted(
        {member.generation_model for member in provider.generation_context.root_index.members},
        key=str.encode,
    )
    fresh_metrics = cast(
        Metrics,
        tuple(
            compute_model_audit_metrics(
                model=model,
                manifest=manifest,
                population=population.records,
                chains=chains,
                adjudication=adjudication,
            )
            for model in models
        ),
    )
    if tuple(map(_bytes, metrics)) != tuple(map(_bytes, fresh_metrics)):
        raise ValueError("supplied metrics differ from source-recomputed audit metrics")
    payload = {
        **_provider_fields(AuditEvidenceAttachmentV1, provider),
        "schema_version": "verified-audit-evidence-v1",
        "population_attachment_sha256": population.attachment.population_attachment_sha256,
        "sample_manifest_sha256": manifest.sample_manifest_sha256,
        "blind_packet_sha256": packet.packet_sha256,
        "audit_git_object_archive_sha256": archive.audit_git_object_archive_sha256,
        "pull_request_source_sha256s": tuple(
            source.pull_request_source_sha256 for source in sources
        ),
        "github_review_source_sha256s": tuple(
            source.github_review_source_sha256 for source in review_sources
        ),
        "commitment_sha256s": tuple(chain.commitment.commitment_sha256 for chain in chains),
        "reveal_sha256s": tuple(chain.reveal.reveal_sha256 for chain in chains),
        "reviewer_chain_proof_sha256s": tuple(
            chain.reviewer_chain_proof_sha256 for chain in chains
        ),
        "adjudication_core_sha256": adjudication.core.adjudication_core_sha256,
        "signoff_proof_sha256s": tuple(item.signoff_proof_sha256 for item in adjudication.signoffs),
        "exact_github_review_record_sha256s": tuple(
            item.exact_api_record_sha256 for item in records
        ),
        "adjudication_sha256": adjudication.adjudication_sha256,
        "model_audit_metric_sha256s": tuple(
            item.model_audit_metric_sha256 for item in fresh_metrics
        ),
    }
    attachment = _seal(AuditEvidenceAttachmentV1, payload)
    return VerifiedAuditEvidenceV1(
        attachment,
        population,
        manifest,
        packet,
        archive,
        sources,
        chains,
        review_sources,
        records,
        adjudication,
        fresh_metrics,
    )


def _audit_members(audit: VerifiedAuditEvidenceV1) -> dict[str, bytes]:
    members = {
        "audit/audit-evidence.json": _bytes(audit.attachment),
        "audit/population-attachment.json": _bytes(audit.population.attachment),
        "audit/population.jsonl": _canonical_population_jsonl(audit.population.records),
        "audit/sample-manifest.json": _bytes(audit.manifest),
        "audit/blind-packet.json": _bytes(audit.packet),
        "audit/git-object-archive.json": _bytes(audit.audit_git_object_archive),
        "audit/pull-request-sources/adjudication.json": _bytes(audit.pull_request_sources[4]),
        "audit/adjudication-core.json": _bytes(audit.adjudication.core),
        "audit/adjudication.json": _bytes(audit.adjudication),
        "audit/metrics.json": canonical_json([_payload(metric) for metric in audit.metrics])
        + b"\n",
    }
    for ordinal, chain in enumerate(audit.reviewer_chains):
        reviewer = chain.identity.reviewer_id
        members.update(
            {
                f"audit/pull-request-sources/commitment/{reviewer}.json": _bytes(
                    audit.pull_request_sources[ordinal]
                ),
                f"audit/pull-request-sources/reveal/{reviewer}.json": _bytes(
                    audit.pull_request_sources[ordinal + 2]
                ),
                f"audit/commitments/{reviewer}.json": _bytes(chain.commitment),
                f"audit/reveals/{reviewer}/reveal.json": _bytes(chain.reveal),
                f"audit/reveals/{reviewer}/labels.jsonl": canonical_label_jsonl(
                    chain.reveal.labels
                ),
                f"audit/reviewer-chains/{reviewer}.json": _bytes(chain),
                f"audit/signoffs/{reviewer}.json": _bytes(audit.adjudication.signoffs[ordinal]),
            }
        )
        record = audit.github_review_records[ordinal]
        members[f"audit/github-review-sources/{record.review_id}.json"] = _bytes(
            audit.github_review_sources[ordinal]
        )
        members[f"audit/github-review-records/{record.review_id}.json"] = _bytes(record)
    return members


def _revalidate_audit(
    audit: VerifiedAuditEvidenceV1, provider: VerifiedBenchmarkProviderEvidenceV1
) -> VerifiedAuditEvidenceV1:
    if type(audit) is not VerifiedAuditEvidenceV1:
        raise TypeError("expected exact VerifiedAuditEvidenceV1")
    attachment = _checked(audit.attachment, AuditEvidenceAttachmentV1)
    _check_provider_fields(attachment, provider)
    records = _checked_tuple(audit.github_review_records, ExactGitHubReviewRecordV1, 2)
    population = _revalidate_verified_audit_population_v1(audit.population)
    manifest = _checked(audit.manifest, AuditSampleManifestV1)
    packet = _checked(audit.packet, BlindAuditPacketV1)
    fresh = _derive_audit(
        provider=provider,
        sample=_sample(population, manifest, packet),
        archive=audit.audit_git_object_archive,
        sources=audit.pull_request_sources,
        chains=audit.reviewer_chains,
        review_sources=audit.github_review_sources,
        adjudication=audit.adjudication,
        metrics=audit.metrics,
    )
    if _bytes(attachment) != _bytes(fresh.attachment) or tuple(map(_bytes, records)) != tuple(
        map(_bytes, fresh.github_review_records)
    ):
        raise ValueError("audit attachment or dedicated review records differ from replay")
    return fresh


def _json_value(raw: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError(f"nonfinite JSON constant: {value}")

    value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
    if raw != canonical_json(value) + b"\n":
        raise ValueError("evidence JSON requires canonical bytes and exactly one LF")
    return value


def _parse(raw: bytes, owner: type[_T]) -> _T:
    _json_value(raw)
    checked = owner.model_validate_json(raw, strict=True)
    if _bytes(checked) != raw:
        raise ValueError("evidence JSON differs after exact owner serialization")
    return checked


_ANALYSIS_PATHS = frozenset(
    f"analysis/{name}"
    for name in (
        "analysis-evidence.json",
        "analysis.json",
        "bootstrap.json",
        "report.md",
        "checksums.json",
    )
)
_FILE_LIMITS = {
    "audit/git-object-archive.json": 100_663_296,
    "audit/population.jsonl": 128 * 1024 * 1024,
    "audit/blind-packet.json": 64 * 1024 * 1024,
}
_Identity = tuple[int, int, int, int, int, int, int]


def _identity(metadata: os.stat_result) -> _Identity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


@dataclass(frozen=True)
class _Tree:
    members: dict[str, bytes]
    identities: dict[str, _Identity]


@contextmanager
def _descriptor_scope() -> Iterator[Callable[[int], None]]:
    """Close each registered descriptor once, preserving an active operation error."""
    descriptors: list[int] = []
    primary: BaseException | None = None
    try:
        yield descriptors.append
    except BaseException as error:
        primary = error
    _run_teardown(tuple(partial(os.close, fd) for fd in reversed(descriptors)), primary)


def _capture_tree(root_fd: int) -> _Tree:
    """Read one bounded stable descriptor tree, rejecting aliases and unsafe file kinds."""
    members: dict[str, bytes] = {}
    identities: dict[str, _Identity] = {"": _identity(os.fstat(root_fd))}
    seen = {identities[""][:2]}
    with _descriptor_scope() as own_descriptor:
        descriptors = {"": root_fd}
        names_by_directory: dict[str, tuple[str, ...]] = {}
        pending = [""]
        while pending:
            prefix = pending.pop()
            descriptor = descriptors[prefix]
            collected: list[str] = []
            with os.scandir(descriptor) as iterator:
                for entry in iterator:
                    if len(collected) >= 32 or len(identities) + len(collected) >= 96:
                        raise ValueError("evidence tree exceeds exact bounded member count")
                    collected.append(entry.name)
            names = tuple(sorted(collected, key=str.encode))
            names_by_directory[prefix] = names
            if len(names) > 32 or len(identities) + len(names) > 96:
                raise ValueError("evidence tree exceeds exact bounded member count")
            for name in names:
                relative = _relative_path(f"{prefix}/{name}" if prefix else name)
                if len(relative.encode()) > 1024 or len(PurePosixPath(relative).parts) > 5:
                    raise ValueError("evidence tree path exceeds bound")
                visible = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if not (stat.S_ISREG(visible.st_mode) or stat.S_ISDIR(visible.st_mode)):
                    raise ValueError("evidence tree rejects symlinks and special files")
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
                if stat.S_ISDIR(visible.st_mode):
                    flags |= os.O_DIRECTORY
                child = os.open(name, flags, dir_fd=descriptor)
                own_descriptor(child)
                identity = _identity(os.fstat(child))
                if identity != _identity(visible) or identity[:2] in seen:
                    raise ValueError("evidence tree identity changed or aliases another member")
                seen.add(identity[:2])
                identities[relative] = identity
                descriptors[relative] = child
                if stat.S_ISDIR(visible.st_mode):
                    pending.append(relative)
                    continue
                limit = _FILE_LIMITS.get(relative, 16 * 1024 * 1024)
                if visible.st_nlink != 1 or visible.st_size > limit:
                    raise ValueError("evidence member is aliased or exceeds byte bound")
                chunks = []
                remaining = visible.st_size + 1
                while remaining:
                    chunk = os.read(child, min(remaining, 1024 * 1024))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw = b"".join(chunks)
                if len(raw) != visible.st_size:
                    raise ValueError("evidence member size changed while reading")
                members[relative] = raw
        for relative, descriptor in descriptors.items():
            if _identity(os.fstat(descriptor)) != identities[relative]:
                raise ValueError("evidence tree changed while reading")
            if relative:
                path = PurePosixPath(relative)
                parent = "" if str(path.parent) == "." else str(path.parent)
                if (
                    _identity(os.stat(path.name, dir_fd=descriptors[parent], follow_symlinks=False))
                    != identities[relative]
                ):
                    raise ValueError("evidence member name changed while reading")
        for relative, names in names_by_directory.items():
            with os.scandir(descriptors[relative]) as iterator:
                actual: set[str] = set()
                for entry in iterator:
                    if entry.name not in names or entry.name in actual:
                        raise ValueError("evidence allowlist changed while reading")
                    actual.add(entry.name)
            if actual != set(names):
                raise ValueError("evidence allowlist changed while reading")
    return _Tree(members, identities)


def _snapshot(root: Path) -> _Tree:
    if root.name in {"", ".", ".."} or root.parent / root.name != root:
        raise ValueError("evidence root requires one safe parent child")
    with _descriptor_scope() as own_descriptor:
        parent = open_directory_no_follow(root.parent)
        own_descriptor(parent)
        visible = os.stat(root.name, dir_fd=parent, follow_symlinks=False)
        descriptor = os.open(
            root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
        own_descriptor(descriptor)
        identity = _identity(os.fstat(descriptor))
        if identity != _identity(visible):
            raise ValueError("evidence root changed while opening")
        tree = _capture_tree(descriptor)
        if (
            _identity(os.fstat(descriptor)) != identity
            or _identity(os.stat(root.name, dir_fd=parent, follow_symlinks=False)) != identity
        ):
            raise ValueError("evidence root changed while loading")
        return tree


def _require_exact_tree(tree: _Tree, paths: set[str]) -> None:
    directories = {""}
    for path in paths:
        directories.update(
            str(parent) for parent in PurePosixPath(path).parents if str(parent) != "."
        )
    if set(tree.members) != paths or set(tree.identities) != paths | directories:
        raise ValueError("evidence root exact tree allowlist mismatch")


def _audit_from_tree(
    tree: _Tree, provider: VerifiedBenchmarkProviderEvidenceV1
) -> VerifiedAuditEvidenceV1:
    members = tree.members
    reviewers = tuple(item.reviewer_id for item in provider.index.audit_reviewer_registry.reviewers)
    try:
        attachment = _parse(members["audit/audit-evidence.json"], AuditEvidenceAttachmentV1)
        _check_provider_fields(attachment, provider)
        adjudication = _parse(members["audit/adjudication.json"], AuditAdjudicationV1)
        paths = {
            f"audit/{name}"
            for name in (
                "audit-evidence.json",
                "population-attachment.json",
                "population.jsonl",
                "sample-manifest.json",
                "blind-packet.json",
                "git-object-archive.json",
                "pull-request-sources/adjudication.json",
                "adjudication-core.json",
                "adjudication.json",
                "metrics.json",
            )
        }
        for reviewer in reviewers:
            paths.update(
                {
                    f"audit/{name}"
                    for name in (
                        f"pull-request-sources/commitment/{reviewer}.json",
                        f"pull-request-sources/reveal/{reviewer}.json",
                        f"commitments/{reviewer}.json",
                        f"reveals/{reviewer}/reveal.json",
                        f"reveals/{reviewer}/labels.jsonl",
                        f"reviewer-chains/{reviewer}.json",
                        f"signoffs/{reviewer}.json",
                    )
                }
            )
        review_ids = tuple(signoff.review_id for signoff in adjudication.signoffs)
        if len(set(review_ids)) != 2:
            raise ValueError("audit requires two distinct canonical review filenames")
        paths.update(
            f"audit/{kind}/{review_id}.json"
            for kind in ("github-review-sources", "github-review-records")
            for review_id in review_ids
        )
        analysis_paths = set(members) & _ANALYSIS_PATHS
        if analysis_paths and analysis_paths != _ANALYSIS_PATHS:
            raise ValueError("combined analysis root is partial")
        _require_exact_tree(tree, paths | analysis_paths)
        manifest = _parse(members["audit/sample-manifest.json"], AuditSampleManifestV1)
        packet = _parse(members["audit/blind-packet.json"], BlindAuditPacketV1)
        archive = _parse(members["audit/git-object-archive.json"], AuditGitObjectArchiveV1)
        chains = cast(
            Chains,
            tuple(
                _parse(members[f"audit/reviewer-chains/{reviewer}.json"], ReviewerChainV1)
                for reviewer in reviewers
            ),
        )
        sources = cast(
            PRSources,
            tuple(
                _parse(members[path], AuditPullRequestEvidenceSourceV1)
                for path in (
                    *[
                        f"audit/pull-request-sources/{kind}/{reviewer}.json"
                        for kind in ("commitment", "reveal")
                        for reviewer in reviewers
                    ],
                    "audit/pull-request-sources/adjudication.json",
                )
            ),
        )
        review_sources = cast(
            ReviewSources,
            tuple(
                _parse(
                    members[f"audit/github-review-sources/{signoff.review_id}.json"],
                    ExactGitHubReviewSourceV1,
                )
                for signoff in adjudication.signoffs
            ),
        )
        raw_metrics = _json_value(members["audit/metrics.json"])
        if type(raw_metrics) is not list or len(raw_metrics) != 3:
            raise ValueError("audit requires exactly three model metrics")
        metrics = cast(
            Metrics,
            tuple(
                ModelAuditMetricsV1.model_validate_json(canonical_json(value), strict=True)
                for value in raw_metrics
            ),
        )
        # The expanded audit owner enforces its own tree; the population owner receives
        # the captured bytes rather than a path with a broadened standalone allowlist.
        population = _load_verified_audit_population_from_bytes(
            attachment_raw=members["audit/population-attachment.json"],
            records_raw=members["audit/population.jsonl"],
            provider_evidence=provider,
        )
        fresh = _derive_audit(
            provider=provider,
            sample=_sample(population, manifest, packet),
            archive=archive,
            sources=sources,
            chains=chains,
            review_sources=review_sources,
            adjudication=adjudication,
            metrics=metrics,
        )
        expected = _audit_members(fresh)
        _require_exact_tree(tree, set(expected) | analysis_paths)
        if _bytes(attachment) != _bytes(fresh.attachment) or any(
            members[path] != raw for path, raw in expected.items()
        ):
            raise ValueError("dedicated audit component or root digest differs from source replay")
        return fresh
    except KeyError as error:
        raise ValueError("audit evidence is missing a required component") from error


def load_verified_audit_evidence(
    root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditEvidenceV1:
    provider = _revalidate_verified_provider_evidence_v1(provider_evidence)
    tree = _snapshot(root)
    audit = _audit_from_tree(tree, provider)
    if _snapshot(root) != tree:
        raise ValueError("audit evidence root changed during verification")
    return audit


def _rollback(
    parent: int, name: str, descriptor: int, witness: _Tree, posix: FilesystemPosixOps
) -> None:
    def same_named_directory(
        parent_fd: int, child_name: str, retained_fd: int, expected: tuple[int, int]
    ) -> None:
        visible = os.stat(child_name, dir_fd=parent_fd, follow_symlinks=False)
        retained = os.fstat(retained_fd)
        if (
            not stat.S_ISDIR(visible.st_mode)
            or _identity(visible)[:2] != expected
            or _identity(retained)[:2] != expected
        ):
            raise ValueError("owned rollback directory name was substituted")

    def same_tree() -> None:
        current = _capture_tree(descriptor)
        if (
            current.members != witness.members
            or any(
                (
                    identity[:2] != witness.identities[path][:2]
                    if path == ""
                    else identity != witness.identities[path]
                )
                for path, identity in current.identities.items()
            )
            or set(current.identities) != set(witness.identities)
        ):
            raise ValueError("owned publication tree changed before rollback")

    identity = witness.identities[""][:2]
    if _identity(os.stat(name, dir_fd=parent, follow_symlinks=False))[:2] != identity:
        raise ValueError("published destination was substituted; rollback refused")
    same_tree()
    quarantine = f".laconian-rollback.{uuid4()}"
    posix.rename_noreplace(parent, name, parent, quarantine)
    try:
        if _identity(os.stat(quarantine, dir_fd=parent, follow_symlinks=False))[:2] != identity:
            raise ValueError("published destination changed during rollback quarantine")
        same_tree()
        with _descriptor_scope() as own_descriptor:
            descriptors = {"": descriptor}
            directories = sorted(
                (
                    path
                    for path, meta in witness.identities.items()
                    if path and stat.S_ISDIR(meta[2])
                ),
                key=lambda path: (path.count("/"), path),
            )
            for path in directories:
                part = PurePosixPath(path)
                parent_path = "" if str(part.parent) == "." else str(part.parent)
                child = os.open(
                    part.name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=descriptors[parent_path],
                )
                own_descriptor(child)
                if _identity(os.fstat(child)) != witness.identities[path]:
                    raise ValueError("owned rollback directory substituted")
                descriptors[path] = child
            for path in witness.members:
                part = PurePosixPath(path)
                parent_path = str(part.parent)
                if (
                    _identity(
                        os.stat(part.name, dir_fd=descriptors[parent_path], follow_symlinks=False)
                    )
                    != witness.identities[path]
                ):
                    raise ValueError("owned rollback file substituted")
                os.unlink(part.name, dir_fd=descriptors[parent_path])
            for path in reversed(directories):
                os.fsync(descriptors[path])
                part = PurePosixPath(path)
                parent_path = "" if str(part.parent) == "." else str(part.parent)
                same_named_directory(
                    descriptors[parent_path],
                    part.name,
                    descriptors[path],
                    witness.identities[path][:2],
                )
                os.rmdir(part.name, dir_fd=descriptors[parent_path])
        os.fsync(descriptor)
        same_named_directory(parent, quarantine, descriptor, identity)
        os.rmdir(quarantine, dir_fd=parent)
        os.fsync(parent)
    except BaseException:
        with suppress(BaseException):
            same_named_directory(parent, quarantine, descriptor, identity)
            posix.rename_noreplace(parent, quarantine, parent, name)
        raise


def _publish(output: Path, members: dict[str, bytes], verify: Callable[[], _T]) -> _T:
    if output.name in {"", ".", ".."} or output.parent / output.name != output:
        raise ValueError("evidence output requires one safe parent child")
    parent = open_directory_no_follow(output.parent)
    staging: OwnedStaging | None = None
    posix: FilesystemPosixOps | None = None
    witness: _Tree | None = None
    primary: BaseException | None = None
    result: _T | None = None
    try:
        posix = cast(FilesystemPosixOps, PosixOps())
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("evidence destination already exists")
        staging = create_owned_staging(parent, uuid4())
        with _descriptor_scope() as own_descriptor:
            descriptors = {"": staging.descriptor}
            for path, raw in sorted(members.items()):
                _relative_path(path)
                parts = PurePosixPath(path).parts
                prefix = ""
                for name in parts[:-1]:
                    next_prefix = f"{prefix}/{name}" if prefix else name
                    if next_prefix not in descriptors:
                        os.mkdir(name, 0o700, dir_fd=descriptors[prefix])
                        child = os.open(
                            name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptors[prefix],
                        )
                        own_descriptor(child)
                        descriptors[next_prefix] = child
                    prefix = next_prefix
                _write_sample_member(descriptors[prefix], parts[-1], raw)
            for descriptor in reversed(tuple(descriptors.values())):
                os.fsync(descriptor)
        witness = _capture_tree(staging.descriptor)
        _require_exact_tree(witness, set(members))
        if witness.members != members:
            raise ValueError("staged evidence differs from checked source bytes")
        try:
            publish_owned_staging(staging, output.name, posix=posix)
        except DestinationCollisionError:
            raise FileExistsError("evidence destination already exists") from None
        result = verify()
    except BaseException as error:
        primary = error
        if staging is not None and staging.state == "published" and witness is not None:
            assert posix is not None
            try:
                _rollback(parent, output.name, staging.descriptor, witness, posix)
            except BaseException as rollback_error:
                error.add_note(
                    f"identity-bound publication rollback refused or failed: {rollback_error}"
                )
    closers: list[Callable[[], None]] = []
    if staging is not None:
        if staging.state == "owned":
            assert posix is not None
            closers.append(partial(cleanup_owned_staging, staging, posix=posix))
        else:
            closers.append(staging.close)
    closers.append(partial(os.close, parent))
    _run_teardown(closers, primary)
    if result is None:
        raise AssertionError("publication completed without a verified attachment")
    return result


def write_audit_evidence_root(
    output_root: Path,
    *,
    source_sample_root: Path,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    sample: VerifiedAuditSampleRootV1,
    audit_git_object_archive: AuditGitObjectArchiveV1,
    pull_request_sources: PRSources,
    reviewer_chains: Chains,
    github_review_sources: ReviewSources,
    adjudication: AuditAdjudicationV1,
    metrics: Metrics,
) -> AuditEvidenceAttachmentV1:
    provider = _revalidate_verified_provider_evidence_v1(provider_evidence)
    fresh_sample = load_verified_audit_sample_root(source_sample_root, provider_evidence=provider)
    if type(sample) is not VerifiedAuditSampleRootV1:
        raise TypeError("expected exact verified sample")
    supplied_population = _revalidate_verified_audit_population_v1(sample.population)
    if (
        sample.audit_sample_root_sha256 != fresh_sample.audit_sample_root_sha256
        or _bytes(_checked(sample.manifest, AuditSampleManifestV1)) != _bytes(fresh_sample.manifest)
        or _bytes(_checked(sample.packet, BlindAuditPacketV1)) != _bytes(fresh_sample.packet)
        or _bytes(supplied_population.attachment) != _bytes(fresh_sample.population.attachment)
        or _canonical_population_jsonl(supplied_population.records)
        != _canonical_population_jsonl(fresh_sample.population.records)
    ):
        raise ValueError("supplied sample differs from fresh source sample root")
    audit = _derive_audit(
        provider=provider,
        sample=fresh_sample,
        archive=audit_git_object_archive,
        sources=pull_request_sources,
        chains=reviewer_chains,
        review_sources=github_review_sources,
        adjudication=adjudication,
        metrics=metrics,
    )
    source = _snapshot(source_sample_root)
    members = _audit_members(audit)
    _require_exact_tree(
        source,
        {
            f"audit/{name}"
            for name in (
                "population-attachment.json",
                "population.jsonl",
                "sample-manifest.json",
                "blind-packet.json",
            )
        },
    )
    if any(members[path] != raw for path, raw in source.members.items()):
        raise ValueError("source sample changed after fresh verification")
    members.update(source.members)

    def verify() -> AuditEvidenceAttachmentV1:
        fresh = load_verified_audit_evidence(output_root, provider_evidence=provider)
        if _audit_members(fresh) != members:
            raise ValueError("installed audit differs from writer inputs")
        return fresh.attachment

    return _publish(output_root, members, verify)


def _distribution(
    values: Sequence[int | Decimal | None],
    unit: Literal["tokens", "usd", "milliseconds", "characters"],
) -> DistributionSummaryV1:
    observed = sorted(Decimal(value) for value in values if value is not None)
    middle = None
    if observed:
        lo, hi = observed[(len(observed) - 1) // 2], observed[len(observed) // 2]
        # Sufficient precision for an exact midpoint, independent of ambient Decimal context.
        precision = max(
            80,
            *(
                len(value.as_tuple().digits)
                + abs(cast(int, value.as_tuple().exponent))
                + abs(value.adjusted())
                + 4
                for value in (lo, hi)
            ),
        )
        with localcontext(Context(prec=precision)):
            middle = (lo + hi) / 2
    return DistributionSummaryV1(
        unit=unit,
        observed_count=len(observed),
        missing_count=len(values) - len(observed),
        minimum=observed[0] if observed else None,
        median=middle,
        maximum=observed[-1] if observed else None,
    )


def _usage(rows: tuple[PlannedObservationV1, ...]) -> DescriptiveUsageV1:
    fields: dict[str, Any] = {}
    for name in DescriptiveUsageV1.model_fields:
        if name.endswith("_counts") or name.endswith("_usd"):
            continue
        source = "output_tokens" if name == "billed_output_tokens" else name
        unit: Literal["tokens", "usd", "milliseconds", "characters"] = (
            "milliseconds"
            if name == "latency_ms"
            else "characters"
            if name == "output_characters"
            else "tokens"
        )
        fields[name] = _distribution(tuple(getattr(row, source) for row in rows), unit)
    for name, basis in (
        ("trusted_usage_cost_usd", "trusted_usage"),
        ("definitely_rejected_zero_cost_usd", "definitely_rejected_zero"),
        ("retained_worst_case_exposure_usd", "retained_worst_case"),
    ):
        fields[name] = _distribution(
            tuple(
                row.analytical_cost_usd if row.cost_availability == basis else None for row in rows
            ),
            "usd",
        )
    fields["cost_availability_counts"] = {
        key: sum(row.cost_availability == key for row in rows) for key in _COSTS
    }
    fields["cache_policy_status_counts"] = {
        key: sum(row.cache_policy_status == key for row in rows) for key in _CACHE
    }
    return DescriptiveUsageV1(**fields)


def _interval(point: float | None, estimates: NDArray[np.float64]) -> BootstrapIntervalV1:
    valid = estimates[np.isfinite(estimates)]
    available = len(valid) >= 9990
    return BootstrapIntervalV1(
        point=point,
        lower=type7_quantile(valid, 0.025) if available else None,
        upper=type7_quantile(valid, 0.975) if available else None,
        valid_replicates=len(valid),
        available=available,
    )


def _quality_intervals(
    rows: tuple[PlannedObservationV1, ...], vectors: BootstrapArtifactV1, gate: GateName
) -> tuple[dict[ArmName, BootstrapIntervalV1], BootstrapIntervalV1, BootstrapIntervalV1]:
    """Exact scenario block resampling, evaluating all stored vectors in C order."""
    indices = np.array(vectors.indices, dtype=np.uint8, order="C")
    uids = vectors.metadata.scenario_uids
    passed = {id(row): row.hard_pass if gate == "hard" else row.semantic_success for row in rows}
    counts = {
        arm: np.array(
            [
                sum(passed[id(row)] for row in rows if row.arm == arm and row.scenario_uid == uid)
                for uid in uids
            ],
            dtype=np.float64,
        )
        for arm in _ARMS
    }
    by_arm = {
        arm: _interval(float(counts[arm].sum() / 120), counts[arm][indices].sum(axis=1) / 120)
        for arm in _ARMS
    }
    differences = counts["if"] - counts["concise"]
    quality = _interval(float(differences.sum() / 120), differences[indices].sum(axis=1) / 120)
    by_key = {
        (row.scenario_uid, row.case_id, row.locale, row.repetition, row.arm): row for row in rows
    }
    deltas: list[tuple[int, int]] = []
    for row in rows:
        if row.arm != "if":
            continue
        other = by_key[(row.scenario_uid, row.case_id, row.locale, row.repetition, "concise")]
        if (
            passed[id(row)]
            and passed[id(other)]
            and row.visible_output_tokens is not None
            and other.visible_output_tokens is not None
        ):
            deltas.append(
                (
                    other.visible_output_tokens - row.visible_output_tokens,
                    uids.index(row.scenario_uid),
                )
            )
    estimates = np.full(10000, np.nan, dtype=np.float64)
    point = None
    if deltas:
        deltas.sort()
        # Preserve Python integer sums before conversion so large opposite endpoints
        # cannot erase a small, exact median through premature float rounding.
        values = np.array([delta for delta, _ in deltas], dtype=object)
        scenario_counts = np.stack(
            [(indices == ordinal).sum(axis=1) for ordinal in range(12)], axis=1
        )
        weights = scenario_counts[:, [ordinal for _, ordinal in deltas]]
        cumulative = weights.cumsum(axis=1)
        totals = cumulative[:, -1]
        present = totals > 0
        lower_rank = (totals - 1) // 2
        upper_rank = totals // 2
        lo = (cumulative > lower_rank[:, None]).argmax(axis=1)
        hi = (cumulative > upper_rank[:, None]).argmax(axis=1)
        estimates[present] = (values[lo[present]] + values[hi[present]]) / 2
        point = float((values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2)
    return by_arm, quality, _interval(point, estimates)


def _candidates(
    aggregate: AggregatedModelV1, audit: VerifiedAuditEvidenceV1
) -> tuple[FalseFailCandidateV1, ...]:
    consensus = {
        row.audit_record_id: row.semantic_pass for row in audit.adjudication.core.consensus
    }
    known: set[str] = set()
    for record in audit.population.records:
        blind_id = stable_digest(
            "laconian-blind-audit-record-id-v1",
            {
                "campaign_id": audit.manifest.campaign_id,
                "sample_manifest_sha256": audit.manifest.sample_manifest_sha256,
                "canonical_record_id": record.canonical_record_id,
            },
        )
        if consensus.get(blind_id) is True:
            known.add(record.response_id)
    return tuple(
        FalseFailCandidateV1(
            response_id=cast(str, row.response_id),
            generation_model=row.generation_model,
            arm=row.arm,
            scenario_uid=row.scenario_uid,
            planned_key=canonical_json_v1(
                {
                    "scenario_uid": row.scenario_uid,
                    "case_id": row.case_id,
                    "locale": row.locale,
                    "repetition": row.repetition,
                }
            ).decode("utf-8"),
            known_false_fail=row.response_id in known,
        )
        for row in aggregate.rows
        if row.arm in _PRIMARY and row.hard_pass and not row.semantic_success
    )


def _confirmatory_coverage(
    semantic: PairDenominatorsV1,
    hard_quality: BootstrapIntervalV1,
    semantic_quality: BootstrapIntervalV1,
    semantic_visible: BootstrapIntervalV1,
) -> bool:
    return (
        semantic.eligible_pairs >= 96
        and semantic.eligible_scenarios >= 10
        and semantic.token_pairs == semantic.eligible_pairs
        and all(value.available for value in (hard_quality, semantic_quality, semantic_visible))
    )


def _model_analysis(
    aggregate: AggregatedModelV1, audit: VerifiedAuditEvidenceV1, vectors: BootstrapArtifactV1
) -> ModelAnalysisV1:
    # Aggregation validates nested snapshots but retains original rows. Rebuild them
    # class-bound here before any arithmetic or serializer can consume supplied state.
    rows = tuple(_checked(row, PlannedObservationV1) for row in aggregate.rows)
    aggregate = AggregatedModelV1.model_validate(
        {**dict(aggregate.__dict__), "rows": rows}, strict=True
    )
    model = aggregate.generation_model
    metrics = next(metric for metric in audit.metrics if metric.generation_model == model)
    gate = evaluate_model_audit_gate(
        metrics=metrics,
        manifest=audit.manifest,
        population=audit.population.records,
        adjudication=audit.adjudication,
    )
    candidates = _candidates(aggregate, audit)
    limits = cast(
        tuple[FalseFailLimitV1, FalseFailLimitV1],
        tuple(
            derive_false_fail_limit(model=model, arm=arm, candidates=candidates, metrics=metrics)
            for arm in _PRIMARY
        ),
    )
    matrix = np.array(vectors.indices, dtype=np.uint8, order="C")
    if not all(limit.estimable for limit in limits) or _assignment_count(limits) <= 4096:
        sensitivity = enumerate_sensitivity_exact(
            aggregate=aggregate, limits=limits, candidates=candidates, vectors=matrix
        )
    else:
        sensitivity, _ = search_sensitivity_exact(
            aggregate=aggregate, limits=limits, candidates=candidates, vectors=matrix
        )
    hard, hard_difference, hard_visible = _quality_intervals(rows, vectors, "hard")
    semantic, semantic_difference, semantic_visible = _quality_intervals(rows, vectors, "semantic")
    denominators = aggregate.denominators_by_gate
    coverage = _confirmatory_coverage(
        denominators.semantic, hard_difference, semantic_difference, semantic_visible
    )
    extrema = {
        name: None if (value := getattr(sensitivity, field)) is None else value.value
        for name, field in (
            ("semantic_sensitivity_min_lower", "semantic_min_lower"),
            ("semantic_sensitivity_max_upper", "semantic_max_upper"),
            ("token_sensitivity_min_lower", "token_min_lower"),
            ("token_sensitivity_max_upper", "token_max_upper"),
        )
    }
    complete = (
        all(limit.estimable for limit in limits)
        and not sensitivity.search_exhausted
        and sensitivity.evaluated_assignments == sensitivity.assignment_count
        and sensitivity.assignment_count > 0
        and all(value is not None for value in extrema.values())
    )
    outcome = classify_model_outcome(
        OutcomeEvidenceV1(
            integrity_valid=not aggregate.integrity_limitations,
            integrity_reasons=tuple(aggregate.integrity_limitations),
            coverage_valid=coverage,
            hard_quality=hard_difference,
            audit_gate_passed=gate.passed,
            sensitivity_complete=complete,
            **extrema,
        )
    )
    return ModelAnalysisV1(
        generation_model=model,
        hard_denominators=denominators.hard,
        semantic_denominators=denominators.semantic,
        hard_pass_by_arm=hard,
        semantic_pass_by_arm=semantic,
        hard_primary_difference=hard_difference,
        semantic_primary_difference=semantic_difference,
        hard_visible_delta=hard_visible,
        semantic_visible_delta=semantic_visible,
        usage_by_arm={arm: _usage(tuple(row for row in rows if row.arm == arm)) for arm in _ARMS},
        audit_metrics=metrics,
        audit_gate=gate,
        false_fail_limits=limits,
        sensitivity=sensitivity,
        outcome=outcome,
    )


def analyze_campaign(
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    audit: VerifiedAuditEvidenceV1,
    vectors: BootstrapArtifactV1,
) -> CampaignAnalysisV1:
    provider = _revalidate_verified_provider_evidence_v1(provider_evidence)
    audit = _revalidate_audit(audit, provider)
    vectors = _checked(vectors, BootstrapArtifactV1)
    if _bytes(vectors) != _bytes(_bootstrap_from_checked(provider)):
        raise ValueError("bootstrap seed, scenario UIDs or stored vectors differ from provider")
    aggregates = aggregate_verified_evidence(provider_evidence=provider)
    models = tuple(
        _model_analysis(aggregate, audit, vectors)
        for aggregate in sorted(aggregates, key=lambda row: row.generation_model.encode())
    )
    return _seal(
        CampaignAnalysisV1,
        {
            **_provider_fields(CampaignAnalysisV1, provider),
            "schema_version": "campaign-analysis-v1",
            "audit_evidence_sha256": audit.attachment.audit_evidence_sha256,
            "bootstrap_vectors_sha256": vectors.metadata.indices_sha256,
            "audit_sample_manifest": _payload(audit.manifest),
            "models": [_payload(model) for model in models],
            "limitations": _LIMITATIONS,
        },
    )


def _display(value: object) -> str:
    """Encode all punctuation/control characters, neutralizing Markdown, HTML and mentions."""
    text = str(value)
    return "".join(char if char.isalnum() or char == " " else f"&#{ord(char)};" for char in text)


def _number(value: object) -> str:
    return "null" if value is None else str(value)


def _limit_unavailability(
    metrics: ModelAuditMetricsV1, arm: Literal["if", "concise"]
) -> tuple[str, ...]:
    reasons = metrics.false_fail_by_primary_arm[arm].unavailable_reasons
    # Task 11 applies this veto model-wide, including an otherwise estimable arm.
    unresolved = any(
        "unresolved_sampled_consensus" in value.unavailable_reasons
        for value in (
            metrics.agreement,
            metrics.false_pass,
            metrics.reviewer_agreement,
            *metrics.false_fail_by_primary_arm.values(),
        )
    )
    if unresolved and "unresolved_sampled_consensus" not in reasons:
        return (*reasons, "unresolved_sampled_consensus")
    return reasons


def _model_limitations(model: ModelAnalysisV1) -> tuple[str, ...]:
    missing = any(
        usage.cache_policy_status_counts["missing_write_detail"]
        for usage in model.usage_by_arm.values()
    )
    forbidden = any(
        usage.cache_policy_status_counts["forbidden_nonzero_write"]
        for usage in model.usage_by_arm.values()
    )
    return tuple(
        reason
        for present, reason in (
            (missing, "cache_write_detail_missing"),
            (forbidden, "forbidden_cache_write_observed"),
        )
        if present
    )


def _bootstrap_row(
    label: str, interval: BootstrapIntervalV1, denominator: PairDenominatorsV1
) -> str:
    return (
        f"| {label} | bootstrap point={_number(interval.point)}; two-sided 95 percent interval="
        f"[{_number(interval.lower)}, {_number(interval.upper)}]; planned denominator=120; "
        f"scenario coverage={denominator.eligible_scenarios}/12; "
        f"eligible pairs={denominator.eligible_pairs}; token pairs={denominator.token_pairs}; "
        f"missingness={denominator.eligible_pairs - denominator.token_pairs} "
        f"eligible token pairs, {120 - denominator.eligible_pairs} ineligible planned pairs; "
        f"valid replicates={interval.valid_replicates}/10000; scenario-superpopulation variation "
        "conditional on the fixed campaign; "
        "nominal 95 percent percentile coverage is approximate with 12 clusters. |"
    )


def render_public_report(analysis: CampaignAnalysisV1) -> bytes:
    analysis = _checked(analysis, CampaignAnalysisV1)
    lines = [
        "# Public benchmark analysis",
        "",
        f"Campaign: {_display(analysis.campaign_id)}",
        "",
        f"Analysis digest: {analysis.campaign_analysis_sha256}",
        "",
        *analysis.limitations,
        "",
        f"Audit sample manifest: {analysis.audit_sample_manifest.sample_manifest_sha256}",
        f"Audit target={analysis.audit_sample_manifest.target}; "
        f"certainty records={analysis.audit_sample_manifest.total_certainty_count}.",
        "",
    ]
    for cell in analysis.audit_sample_manifest.cells:
        probability = cell.inclusion_probability
        lines.append(
            f"Audit cell {_display(cell.cell_id)}: N={cell.noncertainty_population}; "
            f"selected={cell.selected_noncertainty}; "
            f"exact inclusion probability={probability.numerator}/{probability.denominator}; "
            f"local minimum={cell.local_minimum}; floor seats={cell.floor_seats}; "
            f"residual rank={_number(cell.residual_rank)}."
        )
    for model in analysis.models:
        limitation = ", ".join(_model_limitations(model)) or "none"
        lines.extend(
            [
                "",
                f"## {_display(model.generation_model)}",
                "",
                f"Outcome: {_display(model.outcome.outcome.value)}; "
                f"reasons: {_display(', '.join(model.outcome.reasons) or 'none')}; "
                f"operational integrity limitations: {limitation}.",
                "",
                "| Estimate | Result and interpretation |",
                "| --- | --- |",
            ]
        )
        for gate_name in ("hard", "semantic"):
            denominator = getattr(model, f"{gate_name}_denominators")
            for arm, interval in getattr(model, f"{gate_name}_pass_by_arm").items():
                label = f"{gate_name} pass {_display(arm)}" + (
                    " (exploratory only)" if arm in {"baseline", "caveman"} else ""
                )
                lines.append(_bootstrap_row(label, interval, denominator))
            lines.append(
                _bootstrap_row(
                    f"{gate_name} quality if - concise",
                    getattr(model, f"{gate_name}_primary_difference"),
                    denominator,
                )
            )
            lines.append(
                _bootstrap_row(
                    f"{gate_name} visible tokens(concise) - visible tokens(if), "
                    "among jointly successful matched responses",
                    getattr(model, f"{gate_name}_visible_delta"),
                    denominator,
                )
            )
        for arm, usage in model.usage_by_arm.items():
            availability = _display(
                json.dumps(dict(usage.cost_availability_counts), sort_keys=True)
            )
            policies = _display(json.dumps(dict(usage.cache_policy_status_counts), sort_keys=True))
            lines.extend(
                [
                    "",
                    f"### {_display(arm)} descriptive usage",
                    "",
                    f"Cost availability counts: {availability}; "
                    f"cache policy status counts: {policies}; "
                    f"operational integrity limitations: {limitation}; "
                    f"outcome: {_display(model.outcome.outcome.value)}.",
                    "",
                    "| Measure and separate availability basis | Distribution |",
                    "| --- | --- |",
                ]
            )
            for name in DescriptiveUsageV1.model_fields:
                distribution = getattr(usage, name)
                if isinstance(distribution, DistributionSummaryV1):
                    lines.append(
                        f"| {name.replace('_', ' ')} | unit={distribution.unit}; "
                        f"observed={distribution.observed_count}; "
                        f"missing={distribution.missing_count}; "
                        f"planned denominator=120; minimum={_number(distribution.minimum)}; "
                        f"median={_number(distribution.median)}; "
                        f"maximum={_number(distribution.maximum)} |"
                    )
        metrics = model.audit_metrics
        lines.extend(
            [
                "",
                f"Shared audit metric digest: {metrics.model_audit_metric_sha256}",
                "",
                "Exact record weights (inverse inclusion probability):",
            ]
        )
        for identifier, weight in metrics.weights_by_record.items():
            lines.append(f"- {identifier}: {weight.numerator}/{weight.denominator}")
        for name, confusion in (
            ("judge-consensus", metrics.judge_consensus_confusion),
            ("reviewer", metrics.reviewer_confusion),
        ):
            counts = "; ".join(
                f"{field}={getattr(confusion, field).numerator}/"
                f"{getattr(confusion, field).denominator}"
                for field in type(confusion).model_fields
            )
            lines.append(f"{name} weighted confusion: {counts}.")
        for name, proportion in (
            ("agreement", metrics.agreement),
            ("false pass", metrics.false_pass),
            ("reviewer agreement", metrics.reviewer_agreement),
            *(
                (f"false fail {arm}", value)
                for arm, value in metrics.false_fail_by_primary_arm.items()
            ),
        ):
            lines.append(
                f"Wilson {name}: point={_number(proportion.point)}; "
                f"interval=[{_number(proportion.lower)}, {_number(proportion.upper)}]; "
                f"n_eff={_number(proportion.effective_n)}; design-weighted-wilson-score-v1; "
                "two-sided-0.95; z=1.959963984540054; "
                f"authorization={proportion.authorization_use}; unavailable reasons="
                f"{_display(', '.join(proportion.unavailable_reasons) or 'none')}."
            )
        lines.append(f"Weighted kappa={_number(metrics.weighted_kappa)} (no interval).")
        critical = (
            "complete" if model.audit_gate.critical_primary_coverage_complete else "incomplete"
        )
        lines.append(
            "Critical primary coverage="
            f"{critical}; "
            f"audit gate={model.audit_gate.passed}; "
            f"reasons={_display(', '.join(model.audit_gate.reasons) or 'none')}."
        )
        for field in type(model.audit_gate).model_fields:
            if field not in {"generation_model", "reasons"}:
                lines.append(f"Audit gate {field}={getattr(model.audit_gate, field)}.")
        for limit in model.false_fail_limits:
            proportion = metrics.false_fail_by_primary_arm[limit.arm]
            lines.append(
                f"False-fail {_display(limit.arm)}: M={limit.m_all_judge_fail}; "
                f"D={limit.d_known_false_fail}; U={_number(limit.upper_false_fail)}; "
                "upper endpoint of two-sided-0.95 design-weighted-wilson-score-v1; "
                f"z=1.959963984540054; n_eff={_number(proportion.effective_n)}; "
                f"exact Decimal-derived K={limit.k_max_reclassified}; "
                f"estimable={limit.estimable}; optional={limit.optional_candidates}; "
                f"shared metric digest={limit.model_audit_metric_sha256}; "
                "unavailable reasons="
                f"{_display(', '.join(_limit_unavailability(metrics, limit.arm)) or 'none')}. "
                "When unestimable, K=D is a nonauthorizing placeholder and A=0."
            )
        sensitivity = model.sensitivity
        lines.append(
            f"Sensitivity A={sensitivity.assignment_count}; "
            f"visited_nodes={sensitivity.visited_nodes}; "
            f"evaluated_assignments={sensitivity.evaluated_assignments}; "
            f"search_exhausted={sensitivity.search_exhausted}; "
            f"exhaustion_reason={_number(sensitivity.exhaustion_reason)}; "
            f"certificate_sha256={_number(sensitivity.certificate_sha256)}; "
            "caps: 1000000 visited nodes, 4096 bootstrap evaluations; cardinality pruning v1 only; "
            "semantic and token dominance are disabled."
        )
        for field in (
            "semantic_min_lower",
            "semantic_max_upper",
            "token_min_lower",
            "token_max_upper",
        ):
            extremum = getattr(sensitivity, field)
            lines.append(
                f"Sensitivity {field}={_number(None if extremum is None else extremum.value)}; "
                "assignment_sha256="
                f"{_number(None if extremum is None else extremum.assignment_sha256)}."
            )
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _checksums(members: Mapping[str, bytes]) -> ChecksumManifestV1:
    return _seal(
        ChecksumManifestV1,
        {
            "schema_version": "analysis-checksums-v1",
            "entries": [
                {
                    "relative_path": path,
                    "byte_length": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                for path, raw in sorted(members.items())
            ],
        },
    )


def _analysis_attachment(
    provider: VerifiedBenchmarkProviderEvidenceV1,
    audit: VerifiedAuditEvidenceV1,
    analysis: CampaignAnalysisV1,
    bootstrap: BootstrapArtifactV1,
    report: bytes,
    checksums: ChecksumManifestV1,
) -> AnalysisEvidenceAttachmentV1:
    return _seal(
        AnalysisEvidenceAttachmentV1,
        {
            **_provider_fields(AnalysisEvidenceAttachmentV1, provider),
            "schema_version": "verified-analysis-evidence-v1",
            "audit_evidence_sha256": audit.attachment.audit_evidence_sha256,
            "campaign_analysis_sha256": analysis.campaign_analysis_sha256,
            "bootstrap_artifact_sha256": bootstrap.bootstrap_artifact_sha256,
            "report_sha256": hashlib.sha256(report).hexdigest(),
            "checksums_sha256": checksums.checksums_sha256,
        },
    )


def _check_audit_copy_tree(source: _Tree, audit_members: dict[str, bytes]) -> None:
    analysis_paths = set(source.members) & _ANALYSIS_PATHS
    if analysis_paths and analysis_paths != _ANALYSIS_PATHS:
        raise ValueError("source audit has a partial analysis tree")
    _require_exact_tree(source, set(audit_members) | analysis_paths)
    if any(source.members[path] != raw for path, raw in audit_members.items()):
        raise ValueError("source audit changed after fresh verification")


def write_analysis_evidence_root(
    output_root: Path,
    *,
    source_audit_root: Path,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    audit: VerifiedAuditEvidenceV1,
    bootstrap: BootstrapArtifactV1,
) -> AnalysisEvidenceAttachmentV1:
    provider = _revalidate_verified_provider_evidence_v1(provider_evidence)
    fresh_audit = load_verified_audit_evidence(source_audit_root, provider_evidence=provider)
    if _audit_members(_revalidate_audit(audit, provider)) != _audit_members(fresh_audit):
        raise ValueError("supplied audit differs from fresh source audit root")
    expected_bootstrap = build_bootstrap_artifact(provider_evidence=provider)
    if _bytes(_checked(bootstrap, BootstrapArtifactV1)) != _bytes(expected_bootstrap):
        raise ValueError("supplied bootstrap differs from provider-derived artifact")
    analysis = analyze_campaign(
        provider_evidence=provider, audit=fresh_audit, vectors=expected_bootstrap
    )
    report = render_public_report(analysis)
    analysis_members = {
        "analysis/analysis.json": _bytes(analysis),
        "analysis/bootstrap.json": _bytes(expected_bootstrap),
        "analysis/report.md": report,
    }
    checksums = _checksums(analysis_members)
    attachment = _analysis_attachment(
        provider, fresh_audit, analysis, expected_bootstrap, report, checksums
    )
    source = _snapshot(source_audit_root)
    audit_members = _audit_members(fresh_audit)
    _check_audit_copy_tree(source, audit_members)
    members = {
        **audit_members,
        **analysis_members,
        "analysis/checksums.json": _bytes(checksums),
        "analysis/analysis-evidence.json": _bytes(attachment),
    }

    def verify() -> AnalysisEvidenceAttachmentV1:
        fresh = load_verified_analysis_evidence(output_root, provider_evidence=provider)
        if (
            _bytes(fresh.attachment) != _bytes(attachment)
            or _bytes(fresh.analysis) != _bytes(analysis)
            or _bytes(fresh.bootstrap) != _bytes(expected_bootstrap)
            or fresh.report_bytes != report
            or _bytes(fresh.checksums) != _bytes(checksums)
            or _audit_members(fresh.audit) != audit_members
        ):
            raise ValueError("installed analysis differs from derived writer inputs")
        return fresh.attachment

    return _publish(output_root, members, verify)


def load_verified_analysis_evidence(
    root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAnalysisEvidenceV1:
    provider = _revalidate_verified_provider_evidence_v1(provider_evidence)
    tree = _snapshot(root)
    audit = _audit_from_tree(tree, provider)
    _require_exact_tree(tree, set(_audit_members(audit)) | set(_ANALYSIS_PATHS))
    members = tree.members
    attachment = _parse(members["analysis/analysis-evidence.json"], AnalysisEvidenceAttachmentV1)
    analysis = _parse(members["analysis/analysis.json"], CampaignAnalysisV1)
    bootstrap = _parse(members["analysis/bootstrap.json"], BootstrapArtifactV1)
    checksums = _parse(members["analysis/checksums.json"], ChecksumManifestV1)
    report = members["analysis/report.md"]
    if _bytes(checksums) != _bytes(
        _checksums(
            {
                path: members[path]
                for path in (
                    "analysis/analysis.json",
                    "analysis/bootstrap.json",
                    "analysis/report.md",
                )
            }
        )
    ):
        raise ValueError("analysis artifact checksums differ")
    expected_attachment = _analysis_attachment(
        provider, audit, analysis, bootstrap, report, checksums
    )
    if _bytes(expected_attachment) != _bytes(attachment):
        raise ValueError("analysis attachment differs from fixed provider/artifact parents")
    expected = analyze_campaign(provider_evidence=provider, audit=audit, vectors=bootstrap)
    if _bytes(expected) != _bytes(analysis):
        raise ValueError("stored analysis differs from provider/audit rederivation")
    if render_public_report(expected) != report:
        raise ValueError("public report differs from sealed numeric analysis")
    if _snapshot(root) != tree:
        raise ValueError("analysis evidence root changed during verification")
    return VerifiedAnalysisEvidenceV1(attachment, audit, analysis, bootstrap, report, checksums)
