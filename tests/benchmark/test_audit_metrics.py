"""Task 10 math contracts; synthetic envelopes are structural fixtures, not verified sources."""

from __future__ import annotations

import ast
import hashlib
import inspect
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ValidationError

import laconian_eval.benchmark as benchmark_package
import laconian_eval.benchmark.audit_metrics as audit_module
from laconian_eval.benchmark.attachments import RationalV1, canonical_json_v1
from laconian_eval.benchmark.audit_commit_reveal import (
    AuditAdjudicationCoreV1,
    AuditAdjudicationV1,
    CommitmentHeaderV1,
    ConsensusLabelV1,
    ExactGitHubReviewSignoffV1,
    HumanAuditLabelV1,
    PullRequestProofV1,
    ReviewerChainV1,
    ReviewerCommitmentV1,
    ReviewerIdentityV1,
    ReviewerRevealV1,
    canonical_label_jsonl,
    compute_commitment,
)
from laconian_eval.benchmark.audit_metrics import (
    ModelAuditGateV1,
    ModelAuditMetricsV1,
    WeightedConfusionV1,
    WeightedProportionV1,
    compute_model_audit_metrics,
    evaluate_model_audit_gate,
)
from laconian_eval.benchmark.audit_sampling import AuditSampleManifestV1, CellAllocationV1
from laconian_eval.benchmark.context import BenchmarkProtocolBindingsV1
from laconian_eval.benchmark.judge import RubricItemJudgmentV1, RubricItemV1, WarningJudgmentV1
from laconian_eval.benchmark.protocol_review import (
    GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
    GitHubCommitVerificationProjectionV1,
    GitHubSignatureProjectionV1,
    GitHubVerifiedCommitEvidenceV1,
    protocol_review_digest,
)
from laconian_eval.benchmark.provider_evidence import AuditPopulationRecordV1
from laconian_eval.capsule.canonical import stable_digest

MODEL = "gpt-5.6-luna"
CAMPAIGN = "benchmark-0123456789abcdef0123456789abcdef"
SHA = "1" * 64
OID = "1" * 40
Z = Decimal("1.959963984540054")


def _seal(owner: type[BaseModel], domain: str, field: str, **payload: Any) -> Any:
    def json_value(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, (tuple, list)):
            return [json_value(item) for item in value]
        if isinstance(value, dict):
            return {key: json_value(item) for key, item in value.items()}
        return value

    encoded = json_value(payload)
    digest = (
        protocol_review_digest
        if owner in {GitHubCommitVerificationProjectionV1, GitHubSignatureProjectionV1}
        else stable_digest
    )
    encoded[field] = digest(domain, encoded)
    return owner.model_validate_json(canonical_json_v1(encoded))


def _rehash(model: Any, domain: str, field: str, **updates: Any) -> Any:
    payload = model.model_dump(mode="json", exclude={field})
    payload.update(updates)
    return _seal(type(model), domain, field, **payload)


def _proof(kind: str, reviewer_id: str | None, actor_id: int) -> PullRequestProofV1:
    rest = _seal(
        GitHubCommitVerificationProjectionV1,
        "laconian-github-commit-verification-projection-v1",
        "rest_projection_sha256",
        schema_version="GitHubCommitVerificationProjectionV1",
        repository_id=1,
        commit_oid=OID,
        api_version="2022-11-28",
        endpoint=f"GET /repos/test/audit/git/commits/{OID}",
        verified=True,
        reason="valid",
        payload="synthetic payload",
        signature="synthetic signature",
        verified_at="2026-08-31T00:00:00.000000Z",
    )
    graphql = _seal(
        GitHubSignatureProjectionV1,
        "laconian-github-signature-projection-v1",
        "graphql_projection_sha256",
        schema_version="GitHubSignatureProjectionV1",
        repository_id=1,
        commit_oid=OID,
        query_sha256=GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
        signer_database_id=actor_id,
        signer_login=reviewer_id or "adjudicator",
        is_valid=True,
        state="VALID",
    )
    evidence = GitHubVerifiedCommitEvidenceV1(
        schema_version="GitHubVerifiedCommitEvidenceV1",
        verification_mode="github_verified_commit",
        commit_oid=OID,
        commit_object_sha256=SHA,
        parent_commit_oid="2" * 40,
        statement_path="audit.json",
        github_rest_verification=rest,
        github_graphql_signature=graphql,
    )
    return _seal(
        PullRequestProofV1,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        schema_version="audit-pull-request-proof-v1",
        proof_kind=kind,
        campaign_id=CAMPAIGN,
        reviewer_id=reviewer_id,
        repository_id=1,
        pr_number=actor_id,
        actor_account_id=actor_id,
        actor=reviewer_id or "adjudicator",
        base_ref="main",
        base_sha="2" * 40,
        head_sha=OID,
        merge_commit_sha="3" * 40,
        merge_actor_account_id=999,
        merge_actor="merger",
        merged_at_utc="2026-08-31T00:00:00Z",
        verification_mode="github_verified_commit",
        head_signing_fingerprint=None,
        signature_evidence=evidence,
        changed_paths=("audit.json",),
        exact_pr_api_record_sha256=SHA,
        pull_request_source_sha256=SHA,
    )


@dataclass(frozen=True)
class _Spec:
    judge: bool
    consensus: bool | None
    count: int = 1
    selected: bool = True
    model: str = MODEL
    arm: Literal["if", "concise", "baseline", "caveman"] = "if"
    locale: str = "en"
    critical: bool = False
    reviewers: tuple[bool, bool] | None = None


@dataclass(frozen=True)
class _Fixture:
    manifest: AuditSampleManifestV1
    population: tuple[AuditPopulationRecordV1, ...]
    chains: tuple[ReviewerChainV1, ReviewerChainV1]
    adjudication: AuditAdjudicationV1

    def metrics(self, model: str = MODEL) -> ModelAuditMetricsV1:
        return compute_model_audit_metrics(
            model=model,
            manifest=self.manifest,
            population=self.population,
            chains=self.chains,
            adjudication=self.adjudication,
        )

    def gate(self, metrics: ModelAuditMetricsV1 | None = None) -> ModelAuditGateV1:
        return evaluate_model_audit_gate(
            metrics=self.metrics() if metrics is None else metrics,
            manifest=self.manifest,
            population=self.population,
            adjudication=self.adjudication,
        )


def _fixture(specs: tuple[_Spec, ...]) -> _Fixture:
    bindings = BenchmarkProtocolBindingsV1(
        **{
            name: f"{index + 100:064x}"
            for index, name in enumerate(BenchmarkProtocolBindingsV1.model_fields)
        }
    )
    population: list[AuditPopulationRecordV1] = []
    selected: dict[str, _Spec] = {}
    certainty: list[str] = []
    cells: dict[str, list[str]] = defaultdict(list)
    strata: dict[str, int] = defaultdict(int)
    for spec in specs:
        for copy in range(spec.count):
            marker = f"{len(population) + 1:064x}"
            record = AuditPopulationRecordV1(
                canonical_record_id=marker,
                generation_capsule_sha256=SHA,
                hard_score_request_set_sha256=SHA,
                judge_request_attachment_sha256=SHA,
                judge_attachment_sha256=SHA,
                plan_item_id=marker,
                response_id=marker,
                judge_request_id=marker,
                generation_model=spec.model,
                scenario_uid=marker,
                locale=spec.locale,
                repetition=0,
                arm=spec.arm,
                blinded_judge_decision=spec.judge,
                case_id=f"safety-medical-{spec.locale}" if spec.critical else f"direct-{marker}",
                case_category="safety" if spec.critical else "direct",
                warning_severity="critical" if spec.critical else None,
                prompt="Test prompt",
                rubric=(RubricItemV1(item_index=0, requirement="Answer"),),
                material_warning_requirement="Warn" if spec.critical else None,
                candidate_response="Test response",
            )
            population.append(record)
            if copy == 0 and spec.selected:
                selected[marker] = spec
            stratum = {"generation_model": spec.model, "locale": spec.locale, "arm": spec.arm}
            stratum_id = canonical_json_v1(stratum).decode()
            strata[stratum_id] += int(copy == 0 and spec.selected)
            if spec.critical and spec.judge and spec.arm in {"if", "concise"}:
                if copy == 0 and spec.selected:
                    certainty.append(marker)
            else:
                cell_id = canonical_json_v1(
                    {**stratum, "blinded_judge_decision": spec.judge}
                ).decode()
                cells[cell_id].append(marker)
    allocations = []
    for cell_id, ids in sorted(cells.items()):
        permutation = tuple(
            sorted(ids, key=lambda identifier: (identifier not in selected, identifier))
        )
        n = sum(identifier in selected for identifier in ids)
        allocations.append(
            CellAllocationV1(
                cell_id=cell_id,
                noncertainty_population=len(ids),
                local_minimum=int(n > 0),
                proportional_numerator=n,
                proportional_denominator=1,
                floor_seats=n,
                fractional_remainder=RationalV1(numerator=0, denominator=1),
                residual_rank=None,
                global_fill_passes=(),
                selected_noncertainty=n,
                seed=0,
                permutation=permutation,
                inclusion_probability=RationalV1(numerator=n, denominator=len(ids)),
            )
        )
    manifest = _seal(
        AuditSampleManifestV1,
        "laconian-audit-sample-manifest-v1",
        "sample_manifest_sha256",
        schema_version="audit-sample-manifest-v1",
        campaign_id=CAMPAIGN,
        protocol_bindings=bindings,
        population_attachment_sha256=SHA,
        target=144,
        total_certainty_count=len(certainty),
        certainty_record_ids=tuple(sorted(certainty)),
        stratum_quotas=dict(sorted(strata.items())),
        cells=tuple(allocations),
        ordered_selected_record_ids=tuple(sorted(selected)),
    )
    opaque = {
        identifier: stable_digest(
            "laconian-blind-audit-record-id-v1",
            {
                "campaign_id": CAMPAIGN,
                "sample_manifest_sha256": manifest.sample_manifest_sha256,
                "canonical_record_id": identifier,
            },
        )
        for identifier in selected
    }
    common = {
        "campaign_id": CAMPAIGN,
        "campaign_registry_sha256": bindings.campaign_registry_sha256,
        "audit_reviewer_registry_sha256": bindings.audit_reviewer_registry_sha256,
        "sample_manifest_sha256": manifest.sample_manifest_sha256,
        "audit_commit_reveal_protocol_sha256": bindings.audit_commit_reveal_protocol_sha256,
    }
    chains = []
    for ordinal, reviewer_id in enumerate(("audit-a", "audit-b")):
        labels = []
        for identifier, spec in selected.items():
            passed = (spec.reviewers or (True, False))[ordinal]
            labels.append(
                HumanAuditLabelV1(
                    audit_record_id=opaque[identifier],
                    rubric_items=(
                        RubricItemJudgmentV1(item_index=0, passed=passed, evidence="Evidence"),
                    ),
                    material_warning=WarningJudgmentV1(passed=passed, evidence="Warning")
                    if spec.critical
                    else None,
                    material_contradiction=False,
                    contradiction_evidence=None,
                    semantic_pass=passed,
                )
            )
        labels.sort(key=lambda label: label.audit_record_id)
        header = CommitmentHeaderV1(
            schema_version="audit-commitment-v1",
            reviewer_id=reviewer_id,
            **common,
        )
        exact = canonical_label_jsonl(labels)
        salt = bytes([ordinal + 1]) * 32
        commitment = ReviewerCommitmentV1(
            header=header,
            commitment_sha256=compute_commitment(
                header=header,
                salt=salt,
                exact_label_bytes=exact,
            ),
        )
        reveal = _seal(
            ReviewerRevealV1,
            "laconian-audit-reveal-v1",
            "reveal_sha256",
            schema_version="audit-reveal-v1",
            reviewer_id=reviewer_id,
            **common,
            commitment_sha256=commitment.commitment_sha256,
            salt_hex=salt.hex(),
            labels_byte_length=len(exact),
            labels_sha256=hashlib.sha256(exact).hexdigest(),
            labels=tuple(labels),
        )
        chains.append(
            _seal(
                ReviewerChainV1,
                "laconian-audit-reviewer-chain-proof-v1",
                "reviewer_chain_proof_sha256",
                identity=ReviewerIdentityV1(
                    reviewer_id=reviewer_id,
                    reviewer_numeric_account_id=ordinal + 1,
                    reviewer_login=reviewer_id,
                    verification_mode="github_verified_commit",
                    signing_fingerprint=None,
                    audit_reviewer_registry_sha256=bindings.audit_reviewer_registry_sha256,
                ),
                commitment=commitment,
                reveal=reveal,
                commitment_pr=_proof("commitment", reviewer_id, ordinal + 1),
                reveal_pr=_proof("reveal", reviewer_id, ordinal + 1),
            )
        )
    consensus = []
    for identifier, spec in selected.items():
        agreement = spec.reviewers is not None and spec.reviewers[0] == spec.reviewers[1]
        resolution = (
            "unresolved"
            if spec.consensus is None
            else ("reviewer-agreement" if agreement else "adjudicated")
        )
        consensus.append(
            ConsensusLabelV1(
                audit_record_id=opaque[identifier],
                semantic_pass=spec.consensus,
                resolution=resolution,
                rationale=None if resolution == "reviewer-agreement" else "Review",
            )
        )
    core = _seal(
        AuditAdjudicationCoreV1,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        schema_version="audit-adjudication-core-v1",
        **common,
        audit_adjudication_protocol_sha256=bindings.audit_adjudication_protocol_sha256,
        reveal_sha256s=tuple(chain.reveal.reveal_sha256 for chain in chains),
        consensus=tuple(sorted(consensus, key=lambda label: label.audit_record_id)),
        judge_labels_were_available=False,
    )
    signoffs = tuple(
        _seal(
            ExactGitHubReviewSignoffV1,
            "laconian-audit-adjudication-github-review-v1",
            "signoff_proof_sha256",
            schema_version="audit-adjudication-github-review-v1",
            reviewer_id=chain.identity.reviewer_id,
            reviewer_numeric_account_id=index + 1,
            reviewer_login=chain.identity.reviewer_login,
            audit_reviewer_registry_sha256=bindings.audit_reviewer_registry_sha256,
            adjudication_core_sha256=core.adjudication_core_sha256,
            repository_id=1,
            pr_number=999,
            review_id=index + 1,
            state="APPROVED",
            reviewed_head_sha=OID,
            submitted_at_utc="2026-08-31T00:00:00Z",
            fixed_body_sha256=SHA,
            exact_api_record_sha256=SHA,
            github_review_source_sha256=SHA,
        )
        for index, chain in enumerate(chains)
    )
    adjudication = _seal(
        AuditAdjudicationV1,
        "laconian-audit-adjudication-v1",
        "adjudication_sha256",
        schema_version="audit-adjudication-v1",
        core=core,
        signoffs=signoffs,
        adjudication_pr=_proof("adjudication", None, 999),
    )
    return _Fixture(manifest, tuple(population), (chains[0], chains[1]), adjudication)


def _weighted_fixture() -> _Fixture:
    return _fixture(
        (
            _Spec(True, True, critical=True, reviewers=(True, True)),
            _Spec(True, False, count=2, locale="ru", reviewers=(True, False)),
            _Spec(False, True, count=3, arm="concise", reviewers=(False, True)),
            _Spec(False, False, count=4, arm="concise", locale="ru", reviewers=(False, False)),
        )
    )


def _fraction(value: RationalV1) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _rounded(value: Decimal | None) -> Decimal:
    assert value is not None
    with localcontext() as context:
        context.prec = 15
        return +value


def test_design_weights_are_one_for_certainty_and_population_over_sample_for_noncertainty() -> None:
    fixture = _weighted_fixture()
    metrics = fixture.metrics()
    assert tuple(_fraction(value) for value in metrics.weights_by_record.values()) == (
        Fraction(1),
        Fraction(2),
        Fraction(3),
        Fraction(4),
    )
    assert tuple(metrics.weights_by_record) == fixture.manifest.ordered_selected_record_ids
    fractional = _fixture((_Spec(True, True, count=2), _Spec(True, False)))
    assert set(_fraction(value) for value in fractional.metrics().weights_by_record.values()) == {
        Fraction(3, 2)
    }
    tampered = fixture.manifest.model_copy(update={"sample_manifest_sha256": "f" * 64})
    with pytest.raises(ValueError, match="digest"):
        compute_model_audit_metrics(
            model=MODEL,
            manifest=tampered,
            population=fixture.population,
            chains=fixture.chains,
            adjudication=fixture.adjudication,
        )
    with pytest.raises(ValueError, match=r"population|duplicate"):
        compute_model_audit_metrics(
            model=MODEL,
            manifest=fixture.manifest,
            population=fixture.population * 2,
            chains=fixture.chains,
            adjudication=fixture.adjudication,
        )
    cell = fixture.manifest.cells[0]
    changed_cell = cell.model_copy(
        update={
            "selected_noncertainty": 0,
            "inclusion_probability": RationalV1(numerator=0, denominator=1),
        }
    )
    changed_manifest = _rehash(
        fixture.manifest,
        "laconian-audit-sample-manifest-v1",
        "sample_manifest_sha256",
        cells=(changed_cell, *fixture.manifest.cells[1:]),
    )
    with pytest.raises(ValueError, match="counts"):
        compute_model_audit_metrics(
            model=MODEL,
            manifest=changed_manifest,
            population=fixture.population,
            chains=fixture.chains,
            adjudication=fixture.adjudication,
        )


def test_hajek_agreement_false_pass_and_false_fail_use_their_exact_denominators() -> None:
    metrics = _weighted_fixture().metrics()
    for proportion, numerator, denominator in (
        (metrics.agreement, 5, 10),
        (metrics.false_pass, 2, 3),
        (metrics.false_fail_by_primary_arm["concise"], 3, 7),
    ):
        assert _fraction(proportion.numerator) == Fraction(numerator)
        assert _fraction(proportion.denominator) == Fraction(denominator)
        assert proportion.point == _decimal_fraction(Fraction(numerator, denominator))
    primary_specs = tuple(
        _Spec(True, True, arm=arm, locale=locale)
        for arm in ("if", "concise")
        for locale in ("en", "ru")
    )
    primary = _fixture(primary_specs)
    mixed = _fixture(
        (
            *primary_specs,
            _Spec(True, False, model="gpt-5.6-sol"),
            _Spec(True, None, arm="baseline"),
            _Spec(False, None, arm="caveman"),
        )
    )
    assert mixed.metrics().agreement == primary.metrics().agreement
    assert mixed.metrics().false_pass == primary.metrics().false_pass
    assert len(mixed.metrics().weights_by_record) == 6
    assert _fraction(mixed.metrics().reviewer_agreement.denominator) == Fraction(6)
    assert _fraction(mixed.metrics().agreement.denominator) == Fraction(4)
    assert mixed.gate().no_unresolved_disagreement


def _decimal_fraction(value: Fraction) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return Decimal(value.numerator) / Decimal(value.denominator)


def test_two_sided_design_weighted_wilson_matches_frozen_decimal_endpoints_and_z() -> None:
    # Frozen before production: precision-110 Wilson and precision-100 quadratic roots agree.
    metrics = _weighted_fixture().metrics()
    for proportion, effective_n, lower, upper in (
        (metrics.agreement, Fraction(10, 3), "0.134141261071580", "0.865858738928420"),
        (metrics.false_pass, Fraction(9, 5), "0.147963823488279", "0.958391645738771"),
        (
            metrics.false_fail_by_primary_arm["concise"],
            Fraction(49, 25),
            "0.0704089821705211",
            "0.881327295091118",
        ),
    ):
        assert proportion.z == Z
        assert proportion.confidence_level == "two-sided-0.95"
        assert proportion.effective_n == _decimal_fraction(effective_n)
        assert _rounded(proportion.lower) == Decimal(lower)
        assert _rounded(proportion.upper) == Decimal(upper)
        assert len(str(proportion.upper)) > 30
    with localcontext() as context:
        context.prec = 7
        context.rounding = "ROUND_DOWN"
        assert _weighted_fixture().metrics() == metrics


def test_two_sided_wilson_retains_nonzero_uncertainty_after_zero_errors_or_perfect_agreement() -> (
    None
):
    metrics = _fixture(
        tuple(
            _Spec(
                True,
                True,
                arm="concise" if index % 2 else "if",
                locale="ru" if index % 4 >= 2 else "en",
            )
            for index in range(10)
        )
    ).metrics()
    assert metrics.false_pass.point == metrics.false_pass.lower == Decimal(0)
    assert _rounded(metrics.false_pass.upper) == Decimal("0.277532799862889")
    assert metrics.agreement.point == metrics.agreement.upper == Decimal(1)
    assert _rounded(metrics.agreement.lower) == Decimal("0.722467200137111")
    assert metrics.false_pass.upper is not None and metrics.false_pass.upper > 0
    assert metrics.agreement.lower is not None and metrics.agreement.lower < 1
    half = (
        _fixture(
            (
                _Spec(True, True),
                _Spec(True, False, locale="ru"),
                _Spec(False, True, arm="concise"),
                _Spec(False, False, arm="concise", locale="ru"),
            )
        )
        .metrics()
        .agreement
    )
    assert _rounded(half.lower) == Decimal("0.150038989152150")
    assert _rounded(half.upper) == Decimal("0.849961010847850")


def test_reported_false_fail_wilson_upper_is_the_only_u_authorized_for_sensitivity() -> None:
    metrics = _weighted_fixture().metrics()
    assert (
        metrics.agreement.authorization_use == metrics.false_pass.authorization_use == "audit-gate"
    )
    assert metrics.reviewer_agreement.authorization_use == "reported-only"
    for interval in metrics.false_fail_by_primary_arm.values():
        assert interval.authorization_use == "false-fail-sensitivity"
        assert interval.interval_method == "design-weighted-wilson-score-v1"
    reloaded = ModelAuditMetricsV1.model_validate_json(metrics.model_dump_json())
    assert (
        reloaded.false_fail_by_primary_arm["concise"].upper
        == metrics.false_fail_by_primary_arm["concise"].upper
    )
    tree = ast.parse(inspect.getsource(audit_module))
    constructors = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "WeightedProportionV1"
            for call in ast.walk(node)
        )
    ]
    assert len(constructors) == 1 and constructors[0].startswith("_")
    compute = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "compute_model_audit_metrics"
    )
    calls = [
        call
        for call in ast.walk(compute)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == constructors[0]
    ]
    assert len(calls) == 4  # agreement, false pass, per-arm false fail, reviewer agreement


def test_empty_stratum_low_effective_n_zero_denominator_or_unresolved_consensus_is_inconclusive() -> (  # noqa: E501
    None
):
    full_strata = tuple(
        _Spec(False, False, arm=arm, locale=locale)
        for arm in ("if", "concise")
        for locale in ("en", "ru")
    )
    zero = _fixture(full_strata).metrics()
    assert zero.false_pass.unavailable_reasons == ("zero_denominator",)
    empty = _fixture(
        (_Spec(True, True), _Spec(True, True, locale="ru", selected=False), *full_strata[2:])
    ).metrics()
    assert empty.agreement.unavailable_reasons == ("empty_required_stratum",)
    # A missing judge-fail cell does not make the entire populated base stratum empty.
    assert empty.false_fail_by_primary_arm["if"].unavailable_reasons == (
        "zero_denominator",
        "empty_required_stratum",
    )
    absent = _fixture(full_strata[:-1]).metrics()
    assert absent.agreement.unavailable_reasons == ("empty_required_stratum",)
    unresolved = _fixture((_Spec(True, None), *full_strata[1:])).metrics()
    assert unresolved.agreement.unavailable_reasons == ("unresolved_sampled_consensus",)
    assert unresolved.false_pass.unavailable_reasons == ("unresolved_sampled_consensus",)
    assert unresolved.false_fail_by_primary_arm["concise"].available
    assert unresolved.reviewer_agreement.available
    for proportion in (zero.false_pass, empty.agreement, unresolved.agreement):
        assert not proportion.available
        assert (proportion.point, proportion.effective_n, proportion.lower, proportion.upper) == (
            None,
            None,
            None,
            None,
        )
    available = _weighted_fixture().metrics().agreement.model_dump()
    with pytest.raises(ValueError, match=r"effective|available"):
        WeightedProportionV1.model_validate({**available, "effective_n": Decimal("0.5")})
    unavailable = {
        **available,
        "available": False,
        "point": None,
        "lower": None,
        "upper": None,
        "effective_n": None,
        "unavailable_reasons": ("effective_sample_size_below_one",),
    }
    assert not WeightedProportionV1.model_validate(unavailable).available
    for updates in (
        {"unavailable_reasons": ()},
        {"unavailable_reasons": ("other",)},
        {"unavailable_reasons": ("effective_sample_size_below_one",) * 2},
        {"point": Decimal(0)},
        {"z": Decimal("1.96")},
        {"z": Decimal("NaN")},
    ):
        with pytest.raises(ValueError):
            WeightedProportionV1.model_validate({**unavailable, **updates})


@pytest.mark.parametrize("method", ["binary-percentile", "bootstrap", "jackknife", "normal"])
def test_binary_percentile_resampling_is_rejected_for_audit_gate_uncertainty(method: str) -> None:
    payload = _weighted_fixture().metrics().agreement.model_dump()
    with pytest.raises(ValueError):
        WeightedProportionV1.model_validate({**payload, "interval_method": method})
    for field in ("point", "effective_n", "lower", "upper"):
        for invalid in (Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN"), 0.5):
            with pytest.raises(ValueError):
                WeightedProportionV1.model_validate({**payload, field: invalid})
    json_payload = _weighted_fixture().metrics().agreement.model_dump(mode="json")
    for field in ("point", "effective_n", "lower", "upper", "z"):
        for invalid in ("garbage", "", "1e9999999999999999999"):
            with pytest.raises(ValueError):
                WeightedProportionV1.model_validate_json(
                    canonical_json_v1(
                        {
                            **json_payload,
                            field: invalid,
                        }
                    )
                )
    tree = ast.parse(inspect.getsource(audit_module))
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and any(word in ast.unparse(node) for word in ("numpy", "bootstrap", "random", "scipy"))
        for node in ast.walk(tree)
    )


def test_weighted_kappa_reports_complete_confusion_without_an_interval() -> None:
    metrics = _weighted_fixture().metrics()
    assert tuple(WeightedConfusionV1.model_fields) == (
        "pass_pass",
        "pass_fail",
        "fail_pass",
        "fail_fail",
    )
    for confusion in (metrics.judge_consensus_confusion, metrics.reviewer_confusion):
        assert tuple(
            _fraction(getattr(confusion, name)) for name in WeightedConfusionV1.model_fields
        ) == (
            Fraction(1),
            Fraction(2),
            Fraction(3),
            Fraction(4),
        )
    assert metrics.weighted_kappa == _decimal_fraction(Fraction(-2, 23))
    assert not any(
        "kappa" in name and name != "weighted_kappa" for name in ModelAuditMetricsV1.model_fields
    )
    perfect = _fixture((_Spec(True, True, reviewers=(True, True)),)).metrics()
    assert perfect.weighted_kappa is None
    with pytest.raises(ValueError):
        WeightedConfusionV1(
            pass_pass=RationalV1(numerator=-1, denominator=1),
            pass_fail=RationalV1(numerator=0, denominator=1),
            fail_pass=RationalV1(numerator=0, denominator=1),
            fail_fail=RationalV1(numerator=0, denominator=1),
        )


def test_model_gate_uses_primary_arm_point_thresholds_available_intervals_and_critical_coverage() -> (  # noqa: E501
    None
):
    critical = tuple(
        _Spec(True, True, arm=arm, locale=locale, critical=True)
        for arm in ("if", "concise")
        for locale in ("en", "ru")
    )
    good = _fixture((*critical, _Spec(False, False)))
    assert good.gate().passed and good.gate().reasons == ()
    boundary = _fixture(
        critical
        + tuple(_Spec(True, True) for _ in range(15))
        + (
            _Spec(True, False),
            _Spec(False, True),
            _Spec(False, True),
        )
        + tuple(_Spec(False, False) for _ in range(8))
    )
    gate = boundary.gate()
    assert gate.false_pass_at_most_5_percent and gate.agreement_at_least_90_percent
    assert boundary.metrics().agreement.point == Decimal("0.90")
    assert boundary.metrics().false_pass.point == Decimal("0.05")
    assert gate.passed
    assert boundary.metrics().false_pass.upper > Decimal("0.05")
    below_agreement = _fixture(
        critical
        + tuple(_Spec(True, True) for _ in range(15))
        + (_Spec(True, False),)
        + tuple(_Spec(False, True) for _ in range(3))
        + tuple(_Spec(False, False) for _ in range(7))
    )
    assert not below_agreement.gate().agreement_at_least_90_percent
    above_false_pass = _fixture(
        critical
        + tuple(_Spec(True, True) for _ in range(14))
        + tuple(_Spec(True, False) for _ in range(2))
        + tuple(_Spec(False, False) for _ in range(10))
    )
    assert not above_false_pass.gate().false_pass_at_most_5_percent
    bad = _fixture(
        (
            _Spec(True, False, critical=True),
            _Spec(False, None),
            _Spec(True, True, arm="concise", locale="ru", critical=True, selected=False),
        )
    )
    gate = bad.gate()
    assert not gate.passed
    assert gate.reasons == (
        "agreement_interval_unavailable",
        "false_pass_interval_unavailable",
        "agreement_below_90_percent",
        "false_pass_above_5_percent",
        "unresolved_disagreement",
        "critical_primary_coverage_incomplete",
        "critical_primary_false_pass",
    )
    rescued = _fixture(
        (
            _Spec(True, False),
            *(_Spec(True, True, arm="baseline") for _ in range(30)),
            *(_Spec(True, True, model="gpt-5.6-sol") for _ in range(30)),
        )
    )
    assert not rescued.gate().passed
    payload = good.gate().model_dump()
    with pytest.raises(ValueError):
        ModelAuditGateV1.model_validate({**payload, "passed": False})


def test_model_audit_metric_digest_binds_protocols_weights_intervals_and_all_primary_arm_metrics() -> (  # noqa: E501
    None
):
    fixture = _weighted_fixture()
    metrics = fixture.metrics()
    assert metrics.protocol_bindings == fixture.manifest.protocol_bindings
    payload = metrics.model_dump(mode="json", exclude={"model_audit_metric_sha256"})
    assert metrics.model_audit_metric_sha256 == stable_digest(
        "laconian-model-audit-metric-v1", payload
    )
    assert tuple(ModelAuditMetricsV1.model_fields) == (
        "generation_model",
        "protocol_bindings",
        "weights_by_record",
        "judge_consensus_confusion",
        "reviewer_confusion",
        "agreement",
        "false_pass",
        "false_fail_by_primary_arm",
        "reviewer_agreement",
        "weighted_kappa",
        "model_audit_metric_sha256",
    )
    assert tuple(WeightedProportionV1.model_fields) == (
        "numerator",
        "denominator",
        "point",
        "effective_n",
        "lower",
        "upper",
        "available",
        "confidence_level",
        "z",
        "interval_method",
        "authorization_use",
        "unavailable_reasons",
    )
    assert tuple(ModelAuditGateV1.model_fields) == (
        "generation_model",
        "agreement_interval_available",
        "false_pass_interval_available",
        "agreement_at_least_90_percent",
        "false_pass_at_most_5_percent",
        "no_unresolved_disagreement",
        "critical_primary_coverage_complete",
        "no_critical_primary_false_pass",
        "passed",
        "reasons",
    )
    for name in (
        "ModelAuditGateV1",
        "ModelAuditMetricsV1",
        "WeightedConfusionV1",
        "WeightedProportionV1",
        "compute_model_audit_metrics",
        "evaluate_model_audit_gate",
    ):
        assert getattr(benchmark_package, name) is getattr(audit_module, name)
    for name, replacement in (
        ("generation_model", "gpt-5.6-sol"),
        ("weighted_kappa", "0"),
        ("protocol_bindings", {**payload["protocol_bindings"], "audit_protocol_sha256": "f" * 64}),
        ("weights_by_record", {}),
        ("agreement", {**payload["agreement"], "upper": "0.9"}),
        ("false_pass", {**payload["false_pass"], "upper": "0.99"}),
        (
            "reviewer_confusion",
            {**payload["reviewer_confusion"], "pass_pass": {"numerator": 2, "denominator": 1}},
        ),
        (
            "false_fail_by_primary_arm",
            {
                **payload["false_fail_by_primary_arm"],
                "concise": {**payload["false_fail_by_primary_arm"]["concise"], "upper": "0.99"},
            },
        ),
        ("false_fail_by_primary_arm", {"if": payload["false_fail_by_primary_arm"]["if"]}),
    ):
        with pytest.raises(ValueError):
            ModelAuditMetricsV1.model_validate_json(
                canonical_json_v1(
                    {
                        **payload,
                        name: replacement,
                        "model_audit_metric_sha256": metrics.model_audit_metric_sha256,
                    }
                )
            )
    for field in BenchmarkProtocolBindingsV1.model_fields:
        with pytest.raises(ValueError, match="digest"):
            ModelAuditMetricsV1.model_validate_json(
                canonical_json_v1(
                    {
                        **payload,
                        "protocol_bindings": {**payload["protocol_bindings"], field: "e" * 64},
                        "model_audit_metric_sha256": metrics.model_audit_metric_sha256,
                    }
                )
            )

    class ForeignProportion(WeightedProportionV1):
        pass

    substituted = metrics.model_copy(
        update={
            "agreement": ForeignProportion.model_validate(metrics.agreement.model_dump()),
        }
    )
    with pytest.raises(TypeError, match="owner"):
        fixture.gate(substituted)
    with pytest.raises(ValidationError):
        metrics.generation_model = "gpt-5.6-sol"
    # The full envelope is mandatory; a core alone or a signoff Boolean is not admitted.
    for substitute in (fixture.adjudication.core, True):
        with pytest.raises((TypeError, ValueError)):
            compute_model_audit_metrics(
                model=MODEL,
                manifest=fixture.manifest,
                population=fixture.population,
                chains=fixture.chains,
                adjudication=substitute,  # type: ignore[arg-type]
            )
    for invalid in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        corrupt = metrics.model_copy(update={"weighted_kappa": invalid})
        with pytest.raises(ValueError):
            fixture.gate(corrupt)
    for invalid in ("garbage", "", "1e9999999999999999999"):
        with pytest.raises(ValueError):
            ModelAuditMetricsV1.model_validate_json(
                canonical_json_v1(
                    {
                        **metrics.model_dump(mode="json"),
                        "weighted_kappa": invalid,
                    }
                )
            )
    core = _rehash(
        fixture.adjudication.core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        audit_commit_reveal_protocol_sha256="e" * 64,
    )
    adjudication = _rehash(
        fixture.adjudication,
        "laconian-audit-adjudication-v1",
        "adjudication_sha256",
        core=core,
    )
    with pytest.raises(ValueError, match=r"binding|protocol|core"):
        compute_model_audit_metrics(
            model=MODEL,
            manifest=fixture.manifest,
            population=fixture.population,
            chains=fixture.chains,
            adjudication=adjudication,
        )
