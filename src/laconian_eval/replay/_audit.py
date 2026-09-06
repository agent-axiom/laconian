"""Raw audit graph checks only; no sampling, metric builder, or live authority."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from fractions import Fraction
from typing import cast

from pydantic import BaseModel

from laconian_eval.benchmark import audit_commit_reveal as ac
from laconian_eval.benchmark import protocol_review as pr
from laconian_eval.benchmark.attachments import RationalV1
from laconian_eval.benchmark.audit_metrics import (
    ModelAuditMetricsV1,
    WeightedConfusionV1,
    WeightedProportionV1,
    _checked_design,
)
from laconian_eval.benchmark.audit_sampling import (
    AuditSampleManifestV1,
    BlindAuditPacketV1,
    _is_certainty,
)
from laconian_eval.benchmark.judge import derive_semantic_pass
from laconian_eval.benchmark.provider_evidence import (
    AuditPopulationAttachmentV1,
    AuditPopulationRecordV1,
    _validate_population_content,
)
from laconian_eval.benchmark.reporting import AuditEvidenceAttachmentV1
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.replay._inputs import Tree, parse_model, parse_rows
from laconian_eval.replay._structure import Graph, require

_Chains = tuple[ac.ReviewerChainV1, ac.ReviewerChainV1]
_ANALYSIS = {
    "analysis/analysis-evidence.json",
    "analysis/analysis.json",
    "analysis/bootstrap.json",
    "analysis/checksums.json",
    "analysis/report.md",
}


@dataclass(frozen=True)
class AuditData:
    population_attachment: AuditPopulationAttachmentV1
    population_records: tuple[AuditPopulationRecordV1, ...]
    sample_manifest: AuditSampleManifestV1
    blind_packet: BlindAuditPacketV1
    git_archive: ac.AuditGitObjectArchiveV1
    reviewer_chains: _Chains
    adjudication: ac.AuditAdjudicationV1
    attachment: AuditEvidenceAttachmentV1 | None
    metrics: tuple[ModelAuditMetricsV1, ...]


def _provider_copies(value: BaseModel, graph: Graph) -> None:
    assert graph.provider is not None and graph.projection is not None
    expected = graph.provider.model_dump(mode="json")
    expected["benchmark_provider_evidence_sha256"] = (
        graph.projection.benchmark_provider_evidence_sha256
    )
    expected["protocol_bindings"] = graph.bindings.model_dump(mode="json")
    actual = value.model_dump(mode="json")
    for name in type(value).model_fields:
        if name != "schema_version" and name in expected:
            require(actual[name] == expected[name])


def _population(
    tree: Tree, graph: Graph
) -> tuple[
    AuditPopulationAttachmentV1,
    tuple[AuditPopulationRecordV1, ...],
    AuditSampleManifestV1,
    BlindAuditPacketV1,
]:
    attachment = tree.model("audit/population-attachment.json", AuditPopulationAttachmentV1)
    records = parse_rows(tree.members["audit/population.jsonl"], AuditPopulationRecordV1)
    _validate_population_content(attachment, records)
    _provider_copies(attachment, graph)
    by_request = {record.judge_request_id: record for record in records}
    expected_requests: set[str] = set()
    for capsule, hard, request, judge in zip(
        graph.capsules, graph.hard, graph.requests, graph.judgments, strict=True
    ):
        plans = {row.plan_item_id: row for row in capsule.plan}
        passed = {row.judge_request_id: row for row in hard.records if row.hard_pass}
        judgments = {row.judge_request_id: row for row in judge.records}
        for wrapper in request.requests:
            blind = wrapper.blind_request
            expected_requests.add(blind.judge_request_id)
            row = by_request[blind.judge_request_id]
            parent = passed[blind.judge_request_id]
            plan = plans[parent.plan_item_id]
            case = capsule.cases_by_uid[plan.case_uid]
            require(
                row.generation_capsule_sha256 == hard.generation_capsule_sha256
                and row.hard_score_request_set_sha256 == hard.hard_score_request_set_sha256
                and row.judge_request_attachment_sha256 == request.judge_request_attachment_sha256
                and row.judge_attachment_sha256 == judge.judge_attachment_sha256
                and row.plan_item_id == parent.plan_item_id
                and row.response_id == parent.response_id
                and row.generation_model == capsule.manifest.provider.model
                and row.scenario_uid == plan.scenario_uid
                and row.locale == plan.locale
                and row.repetition == plan.repetition
                and row.arm == plan.arm
                and row.case_id == plan.case_id
                and row.case_category == case.category
                and row.warning_severity == case.semantic_rubric.material_warning_severity
                and row.blinded_judge_decision
                == judgments[blind.judge_request_id].judgment.semantic_pass
                and row.prompt == blind.prompt
                and row.rubric == blind.rubric
                and row.material_warning_requirement == blind.material_warning_requirement
                and row.candidate_response == blind.candidate_response
            )
    require(set(by_request) == expected_requests and len(by_request) == len(records))
    manifest = tree.model("audit/sample-manifest.json", AuditSampleManifestV1)
    packet = tree.model("audit/blind-packet.json", BlindAuditPacketV1)
    require(
        manifest.campaign_id == graph.context.campaign_id
        and manifest.protocol_bindings == graph.bindings
        and manifest.population_attachment_sha256 == attachment.population_attachment_sha256
        and packet.campaign_registry_sha256 == graph.context.campaign_registry_sha256
        and packet.sample_manifest_sha256 == manifest.sample_manifest_sha256
    )
    by_id = {record.canonical_record_id: record for record in records}
    require(set(manifest.ordered_selected_record_ids) <= set(by_id))
    selected = {
        stable_digest(
            "laconian-blind-audit-record-id-v1",
            {
                "campaign_id": manifest.campaign_id,
                "sample_manifest_sha256": manifest.sample_manifest_sha256,
                "canonical_record_id": identifier,
            },
        ): by_id[identifier]
        for identifier in manifest.ordered_selected_record_ids
    }
    require(tuple(row.audit_record_id for row in packet.records) == tuple(sorted(selected)))
    for packet_row in packet.records:
        source = selected[packet_row.audit_record_id]
        require(
            all(
                getattr(packet_row, name) == getattr(source, name)
                for name in (
                    "prompt",
                    "rubric",
                    "material_warning_requirement",
                    "warning_severity",
                    "locale",
                    "candidate_response",
                )
            )
        )
    # Retain and check the supplied design without deriving or selecting a new sample.
    certainty = {row.canonical_record_id for row in records if _is_certainty(row)}
    require(set(manifest.certainty_record_ids) == certainty)
    require(manifest.target == max(144, len(certainty)))
    _checked_design(manifest, records)
    return attachment, records, manifest, packet


def _repository(graph: Graph) -> tuple[int, str, str]:
    authorities: set[tuple[int, str, str]] = set()
    for attestation in graph.context.protocol_attestations:
        evidence = attestation.signature_evidence
        rest = evidence.github_rest_verification
        match = re.fullmatch(
            r"GET /repos/([^/\s]+)/([^/\s]+)/git/commits/([0-9a-f]{40})", rest.endpoint
        )
        require(match is not None)
        assert match is not None
        require(match[3] == evidence.commit_oid)
        require(match[2] not in {".", ".."} and not match[2].casefold().endswith(".git"))
        require(rest.repository_id == evidence.github_graphql_signature.repository_id)
        authorities.add((rest.repository_id, match[1], match[2]))
    require(len(authorities) == 1)
    return next(iter(authorities))


def _signature(
    source: ac.AuditPullRequestEvidenceSourceV1,
    proof: ac.PullRequestProofV1,
    graph: Graph,
    objects: Mapping[str, pr.ParsedProtocolGitObjectV1],
    repository: tuple[int, str, str],
) -> None:
    repository_id, owner, name = repository
    raw, canonical = ac._decode_signature_pairs(source)
    evidence, receipt = source.signature_evidence, source.signature_observation_receipt
    head = objects[proof.head_sha]
    view = pr._parse_commit_view(head)
    require(
        view.header_names == ("tree", "parent", "author", "committer", "gpgsig")
        and view.signature is not None
        and view.parent_oids == (proof.base_sha,)
    )
    assert view.signature is not None
    # The raw identity grammar and whole-second UTC signing time apply to every
    # signature mode; only comparison with registered Git names is keyed-only.
    author = pr._identity_parts(view.author)
    committer = pr._identity_parts(view.committer)
    _signed_at = datetime.fromtimestamp(author[2], tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    key, identity = ac._expected_git_identity_and_key(
        registry=graph.context.audit_reviewer_registry,
        reviewer_id=proof.reviewer_id,
        verification_mode=proof.verification_mode,
        fingerprint=proof.head_signing_fingerprint,
        signer_account_id=proof.actor_account_id,
        signer_login=proof.actor,
    )
    rest_raw = pr._parse_provider_json(raw[0])
    verification = pr._selected_object(rest_raw["verification"], "verification")
    payload = {
        "schema_version": "GitHubCommitVerificationProjectionV1",
        "repository_id": repository_id,
        "commit_oid": rest_raw["sha"],
        "api_version": "2022-11-28",
        "endpoint": f"GET /repos/{owner}/{name}/git/commits/{head.oid}",
        "verified": verification["verified"],
        "reason": verification["reason"],
        "payload": verification["payload"],
        "signature": verification["signature"],
        "verified_at": pr._provider_verified_at(verification["verified_at"]).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
    }
    payload["rest_projection_sha256"] = pr.protocol_review_digest(
        "laconian-github-commit-verification-projection-v1", payload
    )
    rest = pr.GitHubCommitVerificationProjectionV1.model_validate(payload)
    graphql_raw = pr._parse_provider_json(raw[1])
    require("errors" not in graphql_raw)
    data = pr._selected_object(graphql_raw["data"], "data")
    repo = pr._selected_object(data["repository"], "repository")
    obj = pr._selected_object(repo["object"], "object")
    sig = pr._selected_object(obj["signature"], "signature")
    signer = pr._selected_object(sig["signer"], "signer")
    payload = {
        "schema_version": "GitHubSignatureProjectionV1",
        "repository_id": repo["databaseId"],
        "commit_oid": obj["oid"],
        "query_sha256": pr.GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
        "signer_database_id": signer["databaseId"],
        "signer_login": signer["login"],
        "is_valid": sig["isValid"],
        "state": sig["state"],
    }
    payload["graphql_projection_sha256"] = pr.protocol_review_digest(
        "laconian-github-signature-projection-v1", payload
    )
    graphql = pr.GitHubSignatureProjectionV1.model_validate(payload)
    require(
        rest == evidence.github_rest_verification
        and graphql == evidence.github_graphql_signature
        and canonical
        == (
            canonical_json(rest.model_dump(mode="json")),
            canonical_json(graphql.model_dump(mode="json")),
        )
        and receipt.repository_id == repository_id
        and receipt.commit_oid == head.oid
        and receipt.rest_projection_sha256 == rest.rest_projection_sha256
        and receipt.graphql_projection_sha256 == graphql.graphql_projection_sha256
        and rest.commit_oid == head.oid
        and graphql.commit_oid == head.oid
        and graphql.repository_id == repository_id
        and graphql.signer_database_id == proof.actor_account_id
        and graphql.signer_login == proof.actor
        and rest.payload == view.signed_payload.decode("utf-8")
        and rest.signature == view.signature.decode("utf-8")
        and evidence.commit_oid == head.oid
        and evidence.commit_object_sha256 == head.git_object_sha256
        and evidence.parent_commit_oid == proof.base_sha
        and evidence.statement_path == proof.changed_paths[1 if proof.proof_kind == "reveal" else 0]
        and evidence.verification_mode == proof.verification_mode
        and evidence == proof.signature_evidence
    )
    if isinstance(evidence, pr.GitHubVerifiedCommitEvidenceV1):
        require(key is None)
        pr._validate_github_signature_armor(view.signature)
    else:
        require(key is not None and identity is not None)
        assert key is not None
        require((author[0], author[1], committer[0], committer[1]) == identity)
        local = evidence.local_signature_verification
        tool_digests = {
            item.signature_evidence.local_signature_verification.verifier_tool_sha256
            for item in graph.context.protocol_attestations
            if not isinstance(item.signature_evidence, pr.GitHubVerifiedCommitEvidenceV1)
        }
        require(len(tool_digests) == 1)
        require(
            evidence.fingerprint == key.fingerprint
            and evidence.keyring_sha256 == key.public_key_sha256
            and pr._signing_key_fingerprint(
                key.verification_mode, pr._decode_canonical_base64(key.public_key_base64)
            )
            == key.fingerprint
            and local.signed_payload_sha256 == hashlib.sha256(view.signed_payload).hexdigest()
            and local.signature_sha256 == hashlib.sha256(view.signature).hexdigest()
            and local.verifier_tool_sha256 in tool_digests
        )


def _reviewer_bindings(
    chain: ac.ReviewerChainV1,
    reviewer: pr.ReviewerAccountBindingV1,
    graph: Graph,
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
) -> None:
    identity = chain.identity
    require(
        all(
            getattr(identity, name) == getattr(reviewer, name)
            for name in (
                "reviewer_id",
                "reviewer_numeric_account_id",
                "reviewer_login",
                "verification_mode",
                "signing_fingerprint",
            )
        )
    )
    require(identity.audit_reviewer_registry_sha256 == graph.context.audit_reviewer_registry_sha256)
    common = {
        "campaign_id": graph.context.campaign_id,
        "campaign_registry_sha256": graph.context.campaign_registry_sha256,
        "audit_reviewer_registry_sha256": graph.context.audit_reviewer_registry_sha256,
        "sample_manifest_sha256": manifest.sample_manifest_sha256,
        "audit_commit_reveal_protocol_sha256": graph.context.audit_commit_reveal_protocol_sha256,
        "reviewer_id": reviewer.reviewer_id,
    }
    for item in (chain.commitment.header, chain.reveal):
        require(all(getattr(item, name) == value for name, value in common.items()))
    require(chain.reveal.commitment_sha256 == chain.commitment.commitment_sha256)
    require(
        tuple(label.audit_record_id for label in chain.reveal.labels)
        == tuple(row.audit_record_id for row in packet.records)
    )
    for label, row in zip(chain.reveal.labels, packet.records, strict=True):
        require(
            tuple(item.item_index for item in label.rubric_items)
            == tuple(item.item_index for item in row.rubric)
        )
        require((label.material_warning is None) == (row.material_warning_requirement is None))
        require(
            label.semantic_pass
            == derive_semantic_pass(
                rubric_items=label.rubric_items,
                material_warning_requirement=row.material_warning_requirement,
                material_warning=label.material_warning,
                material_contradiction=label.material_contradiction,
            )
        )
    require(
        chain.commitment.commitment_sha256
        == ac.compute_commitment(
            header=chain.commitment.header,
            salt=bytes.fromhex(chain.reveal.salt_hex),
            exact_label_bytes=ac.canonical_label_jsonl(chain.reveal.labels),
        )
    )


def _fraction(value: RationalV1) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _decimal(value: Fraction) -> Decimal:
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        return Decimal(value.numerator) / Decimal(value.denominator)


def _confusion_inputs(
    value: WeightedConfusionV1,
    rows: Sequence[tuple[Fraction, bool, bool | None]],
) -> None:
    for field, first, second in (
        ("pass_pass", True, True),
        ("pass_fail", True, False),
        ("fail_pass", False, True),
        ("fail_fail", False, False),
    ):
        require(
            _fraction(getattr(value, field))
            == sum(
                (weight for weight, left, right in rows if left is first and right is second),
                Fraction(),
            )
        )


def _proportion_inputs(
    value: WeightedProportionV1,
    numerator: Fraction,
    weights: list[Fraction],
    *,
    empty: bool,
    unresolved: bool = False,
) -> None:
    denominator = sum(weights, Fraction())
    sum_squares = sum((weight * weight for weight in weights), Fraction())
    n_eff = denominator * denominator / sum_squares if sum_squares else Fraction()
    reasons = tuple(
        reason
        for reason, failed in (
            ("zero_denominator", denominator == 0),
            ("empty_required_stratum", empty),
            ("effective_sample_size_below_one", denominator > 0 and n_eff < 1),
            ("unresolved_sampled_consensus", unresolved),
        )
        if failed
    )
    require(_fraction(value.numerator) == numerator and _fraction(value.denominator) == denominator)
    require(value.unavailable_reasons == reasons and value.available == (not reasons))
    if not reasons:
        require(value.point == _decimal(numerator / denominator))
        require(value.effective_n == _decimal(n_eff))


def _metric_inputs(
    metrics: tuple[ModelAuditMetricsV1, ...],
    manifest: AuditSampleManifestV1,
    records: tuple[AuditPopulationRecordV1, ...],
    chains: _Chains,
    adjudication: ac.AuditAdjudicationV1,
) -> None:
    """Check retained sufficient statistics; never construct a metric artifact."""
    _, _, design = _checked_design(manifest, records)
    opaque = {
        identifier: stable_digest(
            "laconian-blind-audit-record-id-v1",
            {
                "campaign_id": manifest.campaign_id,
                "sample_manifest_sha256": manifest.sample_manifest_sha256,
                "canonical_record_id": identifier,
            },
        )
        for identifier in design
    }
    consensus = {row.audit_record_id: row.semantic_pass for row in adjudication.core.consensus}
    reviewers = [
        {row.audit_record_id: row.semantic_pass for row in chain.reveal.labels} for chain in chains
    ]
    for metric in metrics:
        selected = tuple(
            row
            for row in records
            if row.generation_model == metric.generation_model and row.canonical_record_id in design
        )
        expected_weights = {
            row.canonical_record_id: design[row.canonical_record_id] for row in selected
        }
        require(
            {identifier: _fraction(value) for identifier, value in metric.weights_by_record.items()}
            == expected_weights
        )
        primary = tuple(row for row in selected if row.arm in {"if", "concise"})
        strata = {(row.locale, row.arm) for row in selected}
        empty = any(
            (locale, arm) not in strata for locale in ("en", "ru") for arm in ("if", "concise")
        )
        judge_rows = [
            (
                design[row.canonical_record_id],
                row.blinded_judge_decision,
                consensus[opaque[row.canonical_record_id]],
            )
            for row in primary
        ]
        _confusion_inputs(metric.judge_consensus_confusion, judge_rows)
        _proportion_inputs(
            metric.agreement,
            sum((weight for weight, left, right in judge_rows if left is right), Fraction()),
            [weight for weight, _, _ in judge_rows],
            empty=empty,
            unresolved=any(right is None for _, _, right in judge_rows),
        )
        _proportion_inputs(
            metric.false_pass,
            sum(
                (weight for weight, left, right in judge_rows if left and right is False),
                Fraction(),
            ),
            [weight for weight, left, _ in judge_rows if left],
            empty=empty,
            unresolved=any(right is None for _, left, right in judge_rows if left),
        )
        for arm in ("if", "concise"):
            failures = tuple(
                row for row in primary if row.arm == arm and not row.blinded_judge_decision
            )
            _proportion_inputs(
                metric.false_fail_by_primary_arm[arm],
                sum(
                    (
                        design[row.canonical_record_id]
                        for row in failures
                        if consensus[opaque[row.canonical_record_id]] is True
                    ),
                    Fraction(),
                ),
                [design[row.canonical_record_id] for row in failures],
                empty=any((locale, arm) not in strata for locale in ("en", "ru")),
                unresolved=any(
                    consensus[opaque[row.canonical_record_id]] is None for row in failures
                ),
            )
        reviewer_rows = [
            (
                design[row.canonical_record_id],
                reviewers[0][opaque[row.canonical_record_id]],
                reviewers[1][opaque[row.canonical_record_id]],
            )
            for row in selected
        ]
        _confusion_inputs(metric.reviewer_confusion, reviewer_rows)
        _proportion_inputs(
            metric.reviewer_agreement,
            sum((weight for weight, left, right in reviewer_rows if left is right), Fraction()),
            [weight for weight, _, _ in reviewer_rows],
            empty=any(
                (row.locale, row.arm) not in strata
                for row in records
                if row.generation_model == metric.generation_model
            ),
        )
        pp, pf, fp, ff = (
            _fraction(getattr(metric.reviewer_confusion, name))
            for name in (
                "pass_pass",
                "pass_fail",
                "fail_pass",
                "fail_fail",
            )
        )
        total = pp + pf + fp + ff
        expected_kappa = None
        if total:
            chance = ((pp + pf) * (pp + fp) + (fp + ff) * (pf + ff)) / (total * total)
            if chance != 1:
                expected_kappa = _decimal(((pp + ff) / total - chance) / (1 - chance))
        require(metric.weighted_kappa == expected_kappa)


def _raw_audit(tree: Tree, graph: Graph, *, complete: bool) -> AuditData:
    require(graph.provider is not None and graph.projection is not None)
    registry = graph.context.audit_reviewer_registry
    reviewer_ids = tuple(row.reviewer_id for row in registry.reviewers)
    adjudication = tree.model("audit/adjudication.json", ac.AuditAdjudicationV1)
    review_ids = tuple(signoff.review_id for signoff in adjudication.signoffs)
    require(len(set(review_ids)) == 2)
    paths = {
        f"audit/{name}"
        for name in (
            "population-attachment.json",
            "population.jsonl",
            "sample-manifest.json",
            "blind-packet.json",
            "git-object-archive.json",
            "pull-request-sources/adjudication.json",
            "adjudication-core.json",
            "adjudication.json",
        )
    }
    for reviewer_component in reviewer_ids:
        paths.update(
            f"audit/{name}"
            for name in (
                f"pull-request-sources/commitment/{reviewer_component}.json",
                f"pull-request-sources/reveal/{reviewer_component}.json",
                f"commitments/{reviewer_component}.json",
                f"reveals/{reviewer_component}/reveal.json",
                f"reveals/{reviewer_component}/labels.jsonl",
                f"reviewer-chains/{reviewer_component}.json",
                f"signoffs/{reviewer_component}.json",
            )
        )
    paths.update(
        f"audit/{kind}/{identifier}.json"
        for kind in (
            "github-review-sources",
            "github-review-records",
        )
        for identifier in review_ids
    )
    if complete:
        paths.update({"audit/audit-evidence.json", "audit/metrics.json"})
        if set(tree.members) & _ANALYSIS:
            paths.update(_ANALYSIS)
    tree.exact(paths)
    population, records, manifest, packet = _population(tree, graph)
    archive = tree.model("audit/git-object-archive.json", ac.AuditGitObjectArchiveV1)
    chains = cast(
        _Chains,
        tuple(
            tree.model(f"audit/reviewer-chains/{reviewer}.json", ac.ReviewerChainV1)
            for reviewer in reviewer_ids
        ),
    )
    require(tuple(chain.identity.reviewer_id for chain in chains) == reviewer_ids)
    sources = tuple(
        tree.model(
            f"audit/pull-request-sources/{kind}/{reviewer}.json",
            ac.AuditPullRequestEvidenceSourceV1,
        )
        for kind in ("commitment", "reveal")
        for reviewer in reviewer_ids
    )
    sources += (
        tree.model(
            "audit/pull-request-sources/adjudication.json", ac.AuditPullRequestEvidenceSourceV1
        ),
    )
    review_sources = tuple(
        tree.model(f"audit/github-review-sources/{identifier}.json", ac.ExactGitHubReviewSourceV1)
        for identifier in review_ids
    )
    objects = ac._archive_objects(archive)
    repository_id, owner, name = repository = _repository(graph)
    proofs = (
        chains[0].commitment_pr,
        chains[1].commitment_pr,
        chains[0].reveal_pr,
        chains[1].reveal_pr,
        adjudication.adjudication_pr,
    )
    for source, proof, kind, expected_reviewer_id in zip(
        sources,
        proofs,
        ("commitment", "commitment", "reveal", "reveal", "adjudication"),
        (*reviewer_ids, *reviewer_ids, None),
        strict=True,
    ):
        require(
            proof.proof_kind == kind
            and proof.reviewer_id == expected_reviewer_id
            and proof.campaign_id == graph.context.campaign_id
        )
        record = ac._record_from_source(
            source,
            expected_kind=cast(ac.AuditPullRequestKindV1, kind),
            expected_reviewer_id=expected_reviewer_id,
            campaign_id=graph.context.campaign_id,
            repository_id=repository_id,
            repository_owner=owner,
            repository_name=name,
        )
        for field in (
            "repository_id",
            "pr_number",
            "actor_account_id",
            "actor",
            "base_ref",
            "head_sha",
            "merge_commit_sha",
            "merge_actor_account_id",
            "merge_actor",
            "merged_at_utc",
        ):
            require(getattr(proof, field) == getattr(record, field))
        require(
            proof.exact_pr_api_record_sha256 == record.exact_api_record_sha256
            and proof.pull_request_source_sha256 == source.pull_request_source_sha256
        )
        _signature(source, proof, graph, objects, repository)
    for chain, reviewer in zip(chains, registry.reviewers, strict=True):
        _reviewer_bindings(chain, reviewer, graph, manifest, packet)
        ac._validate_one_chain_deltas_and_ancestry(
            chain,
            commitment_merge_oids=(proofs[0].merge_commit_sha, proofs[1].merge_commit_sha),
            objects=objects,
        )
    core = adjudication.core
    for field, value in (
        ("campaign_id", graph.context.campaign_id),
        ("campaign_registry_sha256", graph.context.campaign_registry_sha256),
        ("audit_reviewer_registry_sha256", graph.context.audit_reviewer_registry_sha256),
        ("sample_manifest_sha256", manifest.sample_manifest_sha256),
        ("audit_commit_reveal_protocol_sha256", graph.context.audit_commit_reveal_protocol_sha256),
        ("audit_adjudication_protocol_sha256", graph.context.audit_adjudication_protocol_sha256),
        ("reveal_sha256s", tuple(chain.reveal.reveal_sha256 for chain in chains)),
    ):
        require(getattr(core, field) == value)
    require(
        tuple(row.audit_record_id for row in core.consensus)
        == tuple(row.audit_record_id for row in packet.records)
    )
    for row, left, right in zip(
        core.consensus, chains[0].reveal.labels, chains[1].reveal.labels, strict=True
    ):
        if left.semantic_pass == right.semantic_pass:
            require(
                row.resolution == "reviewer-agreement"
                and row.semantic_pass == left.semantic_pass
                and row.rationale is None
            )
        else:
            require(row.resolution in {"adjudicated", "unresolved"})
    ac._verify_topology_and_closure(
        chains=chains, adjudication=adjudication, proofs=proofs, archive=archive, objects=objects
    )
    reveal_times = cast(
        tuple[datetime, datetime],
        tuple(
            datetime.strptime(chain.reveal_pr.merged_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
            for chain in chains
        ),
    )
    review_records = []
    for review_source, signoff, reviewer in zip(
        review_sources, adjudication.signoffs, registry.reviewers, strict=True
    ):
        ac._verify_signoff_source(
            source=review_source,
            signoff=signoff,
            reviewer=reviewer,
            core=core,
            adjudication_pr=adjudication.adjudication_pr,
            registry=registry,
            repository_id=repository_id,
            repository_owner=owner,
            repository_name=name,
            reveal_merge_times=reveal_times,
        )
        review_record = ac._review_record_from_source(
            review_source, repository_id=repository_id, repository_owner=owner, repository_name=name
        )
        require(
            tree.model(
                f"audit/github-review-records/{review_record.review_id}.json",
                ac.ExactGitHubReviewRecordV1,
            )
            == review_record
        )
        review_records.append(review_record)
    require(tree.model("audit/adjudication-core.json", ac.AuditAdjudicationCoreV1) == core)
    for chain, signoff in zip(chains, adjudication.signoffs, strict=True):
        reviewer_id = chain.identity.reviewer_id
        require(
            tree.model(f"audit/commitments/{reviewer_id}.json", ac.ReviewerCommitmentV1)
            == chain.commitment
        )
        require(
            tree.model(f"audit/reveals/{reviewer_id}/reveal.json", ac.ReviewerRevealV1)
            == chain.reveal
        )
        require(
            tree.members[f"audit/reveals/{reviewer_id}/labels.jsonl"]
            == ac.canonical_label_jsonl(chain.reveal.labels)
        )
        require(
            tree.model(f"audit/signoffs/{reviewer_id}.json", ac.ExactGitHubReviewSignoffV1)
            == signoff
        )
    attachment = None
    metrics: tuple[ModelAuditMetricsV1, ...] = ()
    if complete:
        raw = tree.members["audit/metrics.json"]
        value = json.loads(raw)
        require(type(value) is list and len(value) == 3 and canonical_json(value) + b"\n" == raw)
        metrics = tuple(
            parse_model(canonical_json(item), ModelAuditMetricsV1, final_lf=False) for item in value
        )
        require(
            tuple(metric.generation_model for metric in metrics)
            == tuple(sorted({member.generation_model for member in graph.generation_index.members}))
        )
        require(all(metric.protocol_bindings == graph.bindings for metric in metrics))
        _metric_inputs(metrics, manifest, records, chains, adjudication)
        attachment = tree.model("audit/audit-evidence.json", AuditEvidenceAttachmentV1)
        _provider_copies(attachment, graph)
        expected = {
            "population_attachment_sha256": population.population_attachment_sha256,
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
            "adjudication_core_sha256": core.adjudication_core_sha256,
            "signoff_proof_sha256s": tuple(
                signoff.signoff_proof_sha256 for signoff in adjudication.signoffs
            ),
            "exact_github_review_record_sha256s": tuple(
                record.exact_api_record_sha256 for record in review_records
            ),
            "adjudication_sha256": adjudication.adjudication_sha256,
            "model_audit_metric_sha256s": tuple(
                metric.model_audit_metric_sha256 for metric in metrics
            ),
        }
        require(all(getattr(attachment, field) == value for field, value in expected.items()))
    return AuditData(
        population, records, manifest, packet, archive, chains, adjudication, attachment, metrics
    )


def validate_audit(tree: Tree, graph: Graph, *, complete: bool) -> AuditData:
    """Check already-captured bytes and return ordinary raw, non-authorizing data."""
    try:
        return _raw_audit(tree, graph, complete=complete)
    except (KeyError, TypeError, ValueError, IndexError, UnicodeError):
        raise ValueError("offline audit structure rejected") from None
