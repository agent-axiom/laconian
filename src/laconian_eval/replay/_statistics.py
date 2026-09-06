"""Offline statistical input identities and algebra, without running an analysis."""

from __future__ import annotations

import hashlib
import math
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from laconian_eval.benchmark.audit_metrics import WeightedProportionV1
from laconian_eval.benchmark.reporting import (
    AnalysisEvidenceAttachmentV1,
    BootstrapArtifactV1,
    CampaignAnalysisV1,
    ChecksumManifestV1,
)
from laconian_eval.benchmark.seeds import derive_seed128
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.replay._inputs import Tree
from laconian_eval.replay._structure import Graph, require

if TYPE_CHECKING:
    from laconian_eval.replay._audit import AuditData

_ANALYSIS_FILES = {
    "analysis/analysis-evidence.json",
    "analysis/analysis.json",
    "analysis/bootstrap.json",
    "analysis/checksums.json",
    "analysis/report.md",
}


def _wilson(value: WeightedProportionV1) -> None:
    # These are checks of supplied Wilson inputs/endpoints, never new metric artifacts.
    if not value.available:
        return
    require(value.effective_n is not None and value.point is not None)
    assert value.effective_n is not None and value.point is not None
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        p, n, z = value.point, value.effective_n, Decimal("1.959963984540054")
        z2 = z * z
        denominator = Decimal(1) + z2 / n
        center = (p + z2 / (Decimal(2) * n)) / denominator
        radius = z / denominator * (p * (1 - p) / n + z2 / (4 * n * n)).sqrt()
        require(
            value.lower
            == (Decimal(0) if value.numerator.numerator == 0 else max(Decimal(0), center - radius))
        )
        require(
            value.upper
            == (
                Decimal(1)
                if value.numerator == value.denominator
                else min(Decimal(1), center + radius)
            )
        )


def _false_fail_inputs(audit: AuditData, model: str, arm: str) -> dict[str, Any]:
    metric = next(item for item in audit.metrics if item.generation_model == model)
    consensus = {
        row.audit_record_id: row.semantic_pass for row in audit.adjudication.core.consensus
    }
    candidates = tuple(
        row
        for row in audit.population_records
        if row.generation_model == model and row.arm == arm and not row.blinded_judge_decision
    )
    known = sum(
        consensus.get(
            stable_digest(
                "laconian-blind-audit-record-id-v1",
                {
                    "campaign_id": audit.sample_manifest.campaign_id,
                    "sample_manifest_sha256": audit.sample_manifest.sample_manifest_sha256,
                    "canonical_record_id": row.canonical_record_id,
                },
            )
        )
        is True
        for row in candidates
    )
    proportions = (
        metric.agreement,
        metric.false_pass,
        metric.reviewer_agreement,
        *metric.false_fail_by_primary_arm.values(),
    )
    unresolved = any(
        "unresolved_sampled_consensus" in value.unavailable_reasons for value in proportions
    )
    proportion = metric.false_fail_by_primary_arm[arm]  # type: ignore[index]
    count = len(candidates)
    estimable = not unresolved and (count == 0 or proportion.available)
    upper = proportion.upper if estimable and count else None
    maximum = known
    if upper is not None:
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            maximum = min(
                count, max(known, int((upper * count).to_integral_value(rounding=ROUND_CEILING)))
            )
    return {
        "generation_model": model,
        "arm": arm,
        "m_all_judge_fail": count,
        "d_known_false_fail": known,
        "optional_candidates": count - known,
        "upper_false_fail": upper,
        "model_audit_metric_sha256": metric.model_audit_metric_sha256,
        "k_max_reclassified": maximum,
        "estimable": estimable,
    }


def validate_statistical_inputs(audit: AuditData, graph: Graph) -> None:
    require(audit.attachment is not None and len(audit.metrics) == 3)
    require(
        tuple(metric.generation_model for metric in audit.metrics)
        == tuple(sorted({member.generation_model for member in graph.generation_index.members}))
    )
    for metric in audit.metrics:
        require(metric.protocol_bindings == graph.bindings)
        for proportion in (
            metric.agreement,
            metric.false_pass,
            metric.reviewer_agreement,
            *metric.false_fail_by_primary_arm.values(),
        ):
            _wilson(proportion)
        for arm in ("if", "concise"):
            values = _false_fail_inputs(audit, metric.generation_model, arm)
            require(
                0
                <= values["d_known_false_fail"]
                <= values["k_max_reclassified"]
                <= values["m_all_judge_fail"]
                <= 120
            )


def _parents(model: BaseModel, graph: Graph) -> None:
    assert graph.provider is not None and graph.projection is not None
    for field in type(model).model_fields:
        for owner in (graph.context, graph.provider, graph.projection):
            if field != "schema_version" and field in type(owner).model_fields:
                require(getattr(model, field) == getattr(owner, field))
        if field == "protocol_bindings":
            require(getattr(model, field) == graph.bindings)


def validate_analysis(tree: Tree, audit: AuditData, graph: Graph) -> None:
    require(set(name for name in tree.members if name.startswith("analysis/")) == _ANALYSIS_FILES)
    require(audit.attachment is not None)
    assert audit.attachment is not None
    attachment = tree.model("analysis/analysis-evidence.json", AnalysisEvidenceAttachmentV1)
    analysis = tree.model("analysis/analysis.json", CampaignAnalysisV1)
    bootstrap = tree.model("analysis/bootstrap.json", BootstrapArtifactV1)
    checksums = tree.model("analysis/checksums.json", ChecksumManifestV1)
    _parents(attachment, graph)
    _parents(analysis, graph)
    require(
        attachment.audit_evidence_sha256
        == analysis.audit_evidence_sha256
        == audit.attachment.audit_evidence_sha256
    )
    require(attachment.campaign_analysis_sha256 == analysis.campaign_analysis_sha256)
    require(attachment.bootstrap_artifact_sha256 == bootstrap.bootstrap_artifact_sha256)
    require(attachment.checksums_sha256 == checksums.checksums_sha256)
    require(
        attachment.report_sha256 == hashlib.sha256(tree.members["analysis/report.md"]).hexdigest()
    )
    for entry in checksums.entries:
        raw = tree.members[entry.relative_path]
        require(len(raw) == entry.byte_length and hashlib.sha256(raw).hexdigest() == entry.sha256)
    require(analysis.audit_sample_manifest == audit.sample_manifest)
    require(analysis.bootstrap_vectors_sha256 == bootstrap.metadata.indices_sha256)
    require(
        bootstrap.metadata.scenario_uids
        == tuple(sorted({member.scenario_uid for member in graph.generation_index.members}))
    )
    require(
        bootstrap.metadata.seed
        == derive_seed128(
            "laconian-bootstrap-v1",
            graph.context.campaign_seed,
            graph.context.input_tag_commit,
            graph.context.judge_protocol_sha256,
        )
    )
    for model in analysis.models:
        metric = next(
            item for item in audit.metrics if item.generation_model == model.generation_model
        )
        require(model.audit_metrics == metric)
        expected_limits = tuple(
            _false_fail_inputs(audit, model.generation_model, arm) for arm in ("if", "concise")
        )
        for limit, expected in zip(model.false_fail_limits, expected_limits, strict=True):
            require(limit.model_dump(mode="python") == expected)
        if all(value["estimable"] for value in expected_limits):
            assignments = math.prod(
                sum(
                    math.comb(value["optional_candidates"], count)
                    for count in range(
                        value["k_max_reclassified"] - value["d_known_false_fail"] + 1
                    )
                )
                for value in expected_limits
            )
            require(model.sensitivity.assignment_count == assignments)
            require(model.sensitivity.evaluated_assignments <= assignments)
        for usage in model.usage_by_arm.values():
            # Public input contracts prohibit nonzero cache writes. The retained
            # descriptive write values must therefore be zero or unavailable.
            distribution = usage.cache_write_tokens
            for field in ("mean", "minimum", "maximum", "median", "p95"):
                if field in type(distribution).model_fields:
                    require(getattr(distribution, field) in {None, 0, Decimal(0)})
