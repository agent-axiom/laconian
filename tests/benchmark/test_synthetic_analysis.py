"""Offline, source-backed proof of the complete synthetic public campaign.

The frozen model identifiers label synthetic observations, never model evidence.
The campaign builder is deliberately looked up inside test bodies: the initial RED
must report missing campaign construction, not an import or collection error.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import shutil
from collections import Counter
from copy import deepcopy
from decimal import ROUND_CEILING, Context, Decimal, localcontext
from pathlib import Path

import pytest

from laconian_eval.benchmark import reporting
from laconian_eval.benchmark.attachments import canonical_json_v1, parse_canonical_json_v1
from laconian_eval.benchmark.audit_commit_reveal import verify_audit_chain
from laconian_eval.benchmark.audit_sampling import (
    load_verified_audit_sample_root,
    write_audit_sample_root,
)
from laconian_eval.benchmark.context import BenchmarkProtocolBindingsV1, GenerationContextIndexV1
from laconian_eval.benchmark.judge import (
    JudgeAttemptBoundaryV1,
    JudgeAttemptRootIndexV1,
    build_judge_attachment,
    load_verified_judge_attempt_root,
    write_judge_attempt_root,
)
from laconian_eval.benchmark.protocol_review import (
    ProtocolReviewerBindingV1,
    ProtocolReviewStatementV1,
    VerifiedProtocolAttestationV1,
    compute_audit_reviewer_registry_sha256,
    load_verified_protocol_review_object_archive,
    parse_protocol_git_object,
    protocol_review_digest,
    verify_protocol_review_dag,
)
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.scorable import ScoredAttemptV2
from laconian_eval.capsule.seal_models import SealV1
from tests.benchmark import helpers

MODELS = (
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
)
ROLES = ("statistical_method", "blind_judge_audit_protocol", "security_evidence")
STATISTICAL_PROTOCOL = "1111111111111111111111111111111111111111111111111111111111111111"
AUDIT_PROTOCOL = "2222222222222222222222222222222222222222222222222222222222222222"
CAMPAIGN_SEED = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SECURITY_SUBJECTS = (
    "provider_request_contract_sha256",
    "retry_spend_protocol_sha256",
    "campaign_state_schema_sha256",
    "workflow_endpoint_policy_sha256",
    "artifact_security_protocol_sha256",
    "publication_correction_protocol_sha256",
    "publication_branch_ruleset_policy_sha256",
    "identity_registry_bundle_sha256",
    "state_writer_git_identity_sha256",
    "broker_token_delivery_isolation_policy_sha256",
    "broker_signing_keys_root_sha256",
    "tag_operator_registry_sha256",
    "tag_ruleset_policy_root",
    "invalid_event_dismissal_policy_sha256",
)


@pytest.fixture(scope="module")
def campaign_source(tmp_path_factory):
    # Reuse source DATA only. Tests invoke public verification for each admission.
    data = []

    def source():
        builder = getattr(helpers, "build_synthetic_public_campaign", None)
        assert callable(builder), "complete synthetic campaign builder is not implemented"
        if not data:
            data.append(builder(tmp_path_factory.mktemp("synthetic-public-campaign")))
        return data[0]

    return source


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _rehash(payload, domain, field):
    payload.pop(field)
    payload[field] = stable_digest(domain, payload)
    return payload


def _rehash_attestation(payload):
    statement = payload["statement"]
    statement["subject_root"] = protocol_review_digest(
        "laconian-protocol-review-subjects-root-v1", statement["subjects"]
    )
    statement.pop("statement_sha256")
    statement["statement_sha256"] = protocol_review_digest(
        "laconian-protocol-review-statement-v1", statement
    )
    payload.pop("attestation_sha256")
    payload["attestation_sha256"] = protocol_review_digest(
        "laconian-verified-protocol-attestation-v1", payload
    )
    return payload


def _verify_dag(fixture, **updates):
    inputs = {
        "input_tag_ref": "refs/tags/benchmark-input-20260831.1",
        "companion_tag_ref": "refs/tags/benchmark-attestations-20260831.1",
        "objects": fixture.dag.objects,
        "protocol_reviewer_registry": fixture.registry,
        "tag_operator_registry": fixture.operator_registry,
        "tag_ruleset_policy": fixture.ruleset_policy,
        "signature_evidence_sources": tuple(item.source for item in fixture.observations),
        "tag_creation_suites": (fixture.t0_suite.receipt, fixture.t1_suite.receipt),
    }
    return verify_protocol_review_dag(**(inputs | updates))


def _golden_broker_package():
    """Literal wire DATA frozen independently with stdlib JSON and SHA-256."""
    roles = ("publisher", "release_finalizer", "security_attestor")
    spkis = (
        "MCowBQYDK2VwAyEA11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
        "MCowBQYDK2VwAyEAPUAXw-hDiVqStwqnTRt-vJyYLM8uxJaMwM1V8Sr0Zgw",
        "MCowBQYDK2VwAyEA_FHNjmIYoaONpH7QAjDwWAgW7RO6MwOsXeuRFUiQgCU",
    )
    key_ids = (
        "synthetic-publisher-2026",
        "synthetic-release-finalizer-2026",
        "synthetic-security-attestor-2026",
    )
    digests = (
        "7bd16c3cc9c4e03a24a7e5e4da61f18ddd722565cfafe5b5081f8c76c32c67b4",
        "a3956441a82fb6dccf4ee9f4bcfa3a061f6e1ff7a5d9f8968b1f60a312af6302",
        "cf7e0926cfed49fdcf5ab2ff704346e30dc9ee4d7da9ab9ace6878e88903b96b",
    )
    keys = [
        {
            "schema_version": "BrokerSigningKeyV1",
            "broker_role": role,
            "key_id": key_id,
            "algorithm": "Ed25519",
            "public_key_spki_der_base64url": spki,
            "not_before": "2026-08-01T00:00:00Z",
            "not_after": "2026-10-01T00:00:00Z",
            "broker_signing_key_sha256": digest,
        }
        for role, key_id, spki, digest in zip(roles, key_ids, spkis, digests, strict=True)
    ]
    return {
        "broker_signing_keys": keys,
        "broker_signing_keys_root_sha256": (
            "2b3c6d15f0bcb48a2e564766f7365a4f6ad8672e9dd18b64bb4194c39ec5210d"
        ),
        "broker_token_delivery_isolation_policy": {
            "schema_version": "BrokerTokenDeliveryIsolationPolicyV1",
            "api_origin": "https://api.github.com",
            "api_version": "2022-11-28",
            "installation_token_endpoint": (
                "POST /app/installations/{installation_id}/access_tokens"
            ),
            "broker_roles": list(roles),
            "vault_implementation_measurements": [
                {"broker_role": role, "vault_measurement_sha256": marker * 64}
                for role, marker in zip(roles, ("a", "b", "c"), strict=True)
            ],
            "github_tls_terminates_inside_token_vault": True,
            "complete_response_validation_precedes_token_commit": True,
            "token_commit_precedes_executor_visibility": True,
            "failed_token_commit_zeroizes_response_bytes": True,
            "executor_accepts_only_committed_token_handles": True,
            "raw_token_bytes_leave_token_vault": False,
            "raw_token_bytes_enter_actions": False,
            "unknown_delivery_allows_operation_dispatch": False,
            "broker_token_delivery_isolation_policy_sha256": (
                "d2ed58a783a98d9dd60664768758b7331adb3cd34dc971aaa65ffc3124da2474"
            ),
        },
        "statistical_protocol_sha256": STATISTICAL_PROTOCOL,
        "audit_protocol_sha256": AUDIT_PROTOCOL,
    }


def _raw_c0_file(protocol, path):
    """Independently walk the raw C0 Git tree to its actual input blob."""
    objects = {item.oid: item for item in protocol.dag.objects}
    oid = protocol.c0.raw_content.splitlines()[0].removeprefix(b"tree ").decode()
    for component in path.split("/"):
        raw = objects[oid].raw_content
        entries = {}
        cursor = 0
        while cursor < len(raw):
            space = raw.index(b" ", cursor)
            nul = raw.index(b"\0", space)
            entries[raw[space + 1 : nul].decode()] = raw[nul + 1 : nul + 21].hex()
            cursor = nul + 21
        oid = entries[component]
    return objects[oid].raw_content


def test_synthetic_campaign_reconstructs_analysis_from_36_bound_attachments(
    campaign_source, tmp_path
):
    campaign = campaign_source()
    provider = campaign.provider_fixture.load()
    result = reporting.load_verified_analysis_evidence(
        campaign.result_root, provider_evidence=provider
    )
    context = provider.generation_context.index
    assert context.campaign_seed == provider.index.campaign_seed == CAMPAIGN_SEED
    # C0's tree binds the genuine installed verifier inventory and can differ
    # across hosts. Its authored identity, time and message are fixed before
    # downstream analysis; compute the Git identity independently from raw bytes.
    raw_c0 = campaign.protocol.c0.raw_content
    fixed_input_commit = hashlib.sha1(
        b"commit " + str(len(raw_c0)).encode() + b"\0" + raw_c0
    ).hexdigest()
    assert context.input_tag_commit == provider.index.input_tag_commit == fixed_input_commit
    assert campaign.protocol.c0.oid == fixed_input_commit
    assert raw_c0.splitlines()[1:] == [
        b"author Campaign Input <campaign@example.com> 1788134400 +0000",
        b"committer Campaign Input <campaign@example.com> 1788134400 +0000",
        b"",
        b"benchmark input",
    ]
    assert campaign.protocol.input_tag.raw_content.splitlines()[0] == (
        b"object " + fixed_input_commit.encode()
    )
    assert len(provider.generation_evidence) == 36
    assert sum(len(item.plan) for item in provider.generation_evidence) == 1440
    assert sum(len(item.scored_attempts) for item in provider.generation_evidence) == 1440
    assert Counter(item.manifest.provider.model for item in provider.generation_evidence) == {
        "gpt-5.6-luna": 12,
        "gpt-5.6-sol": 12,
        "gpt-5.6-terra": 12,
    }
    assert Counter(
        item.manifest.provider.model
        for item in provider.generation_evidence
        for row in item.scored_attempts
        if row.hard_pass
    ) == {"gpt-5.6-luna": 440, "gpt-5.6-sol": 456, "gpt-5.6-terra": 480}
    for item in provider.generation_evidence:
        assert type(item.seal) is SealV1
        assert item.capsule_sha256 is not None and len(item.capsule_sha256) == 64
        assert len(item.plan) == len(item.scored_attempts) == 40
        assert all(type(row) is ScoredAttemptV2 for row in item.scored_attempts)
        assert Counter(row.locale for row in item.plan) == {"en": 20, "ru": 20}
        assert Counter(row.arm for row in item.plan) == {
            "baseline": 10,
            "caveman": 10,
            "if": 10,
            "concise": 10,
        }
        assert Counter(row.repetition for row in item.plan) == {0: 8, 1: 8, 2: 8, 3: 8, 4: 8}
    assert tuple(
        len(layer)
        for layer in (
            provider.hard_score_request_sets,
            provider.judge_request_attachments,
            provider.judge_attempt_root.boundaries,
            provider.judge_attachments,
        )
    ) == (36, 36, 36, 36)
    empty = [item for item in provider.judge_attempt_root.boundaries if not item.attempts]
    assert len(empty) == 1
    assert empty[0].ordered_judge_request_ids == ()
    assert provider.judge_attachments[empty[0].boundary_ordinal].records == ()
    assert len(provider.judge_attachments[empty[0].boundary_ordinal].judge_attachment_sha256) == 64
    for owner in (
        context,
        provider.index,
        provider.projection.protocol_bindings,
        result.audit.attachment,
        result.analysis,
        result.attachment,
    ):
        assert owner.statistical_protocol_sha256 == STATISTICAL_PROTOCOL
        assert owner.audit_protocol_sha256 == AUDIT_PROTOCOL
    for owner in (
        provider.projection,
        *provider.hard_score_request_sets,
        *provider.judge_request_attachments,
        *provider.judge_attachments,
        result.audit.population.attachment,
        result.audit.manifest,
        result.audit.attachment,
        result.analysis,
        result.attachment,
        *result.audit.metrics,
    ):
        assert owner.protocol_bindings.statistical_protocol_sha256 == STATISTICAL_PROTOCOL
        assert owner.protocol_bindings.audit_protocol_sha256 == AUDIT_PROTOCOL
    for field in (
        "ordered_generation_capsule_sha256s",
        "ordered_hard_score_request_set_sha256s",
        "ordered_judge_request_attachment_sha256s",
        "ordered_judge_attempt_boundary_sha256s",
        "ordered_judge_attachment_sha256s",
    ):
        values = getattr(provider.index, field)
        assert len(values) == len(set(values)) == 36
        assert getattr(result.audit.attachment, field) == getattr(result.analysis, field) == values
    assert len(result.analysis.models) == 3
    assert tuple(item.generation_model for item in result.analysis.models) == MODELS
    assert result.bootstrap.metadata.replicates == 10000
    assert len(result.bootstrap.indices) == 10000
    assert {len(vector) for vector in result.bootstrap.indices} == {12}
    expected_counters = {
        "gpt-5.6-luna": (1, 1, 1),
        "gpt-5.6-sol": (2, 2, 2),
        "gpt-5.6-terra": (1, 1, 1),
    }
    for model in result.analysis.models:
        assert (
            model.sensitivity.assignment_count,
            model.sensitivity.visited_nodes,
            model.sensitivity.evaluated_assignments,
        ) == expected_counters[model.generation_model]
        assert model.sensitivity.search_exhausted is False
        assert model.sensitivity.exhaustion_reason is None
        assert model.sensitivity.certificate_sha256 is None
        assert (
            model.hard_denominators.planned_pairs
            == model.semantic_denominators.planned_pairs
            == 120
        )
        metric = model.audit_metrics.model_audit_metric_sha256
        assert tuple(limit.model_audit_metric_sha256 for limit in model.false_fail_limits) == (
            metric,
            metric,
        )
        assert model.sensitivity.model_audit_metric_sha256 == metric
        # A_m = product_a sum_{j=D}^{K} C(M-D, j-D), independently of the solver.
        expected_assignments = math.prod(
            sum(
                math.comb(
                    limit.m_all_judge_fail - limit.d_known_false_fail, j - limit.d_known_false_fail
                )
                for j in range(limit.d_known_false_fail, limit.k_max_reclassified + 1)
            )
            for limit in model.false_fail_limits
        )
        if not all(limit.estimable for limit in model.false_fail_limits):
            assert model.sensitivity.assignment_count == 0
            assert model.sensitivity.visited_nodes == model.sensitivity.evaluated_assignments == 0
            assert model.sensitivity.search_exhausted is False
            assert (
                model.sensitivity.exhaustion_reason is model.sensitivity.certificate_sha256 is None
            )
            assert all(
                getattr(model.sensitivity, field) is None
                for field in (
                    "semantic_min_lower",
                    "semantic_max_upper",
                    "token_min_lower",
                    "token_max_upper",
                )
            )
            continue
        assert model.sensitivity.assignment_count == expected_assignments
        extrema = tuple(
            getattr(model.sensitivity, field)
            for field in (
                "semantic_min_lower",
                "semantic_max_upper",
                "token_min_lower",
                "token_max_upper",
            )
        )
        if model.sensitivity.search_exhausted:
            assert model.sensitivity.exhaustion_reason in {
                "visited_node_cap",
                "bootstrap_evaluation_cap",
            }
        else:
            assert all(item is not None for item in extrema)
            assert model.sensitivity.exhaustion_reason is None
            assert model.sensitivity.evaluated_assignments == expected_assignments
    retries = [
        row
        for row in provider.index.judge_cache_evidence
        if row.service_tier_status == "not_applicable_definitely_rejected"
    ]
    assert len(retries) == 1
    assert {row.requested_service_tier for row in provider.index.generation_cache_evidence} == {
        "default"
    }
    assert campaign.rejected_nondefault_attempt.service_tier_status == "mismatch"
    assert campaign.rejected_nondefault_attempt.cost_availability == "retained_worst_case"
    assert len(provider.index.generation_cache_evidence) == 1440
    assert len(provider.index.judge_cache_evidence) == 1377
    assert sum(len(item.requests) for item in provider.judge_request_attachments) == 1376
    assert sum(len(item.records) for item in provider.judge_attachments) == 1376
    assert result.audit.population.attachment.record_count == 1376
    assert result.audit.manifest.target == len(result.audit.packet.records) == 144
    assert result.audit.manifest.total_certainty_count == 58
    retry = provider.judge_attempt_root.boundaries[0].attempts[0]
    successor = provider.judge_attempt_root.boundaries[0].attempts[1]
    assert (retry.structured_retry_status, retry.delivery_certainty, retry.disposition) == (
        429,
        "definitely_rejected",
        "retry_scheduled",
    )
    assert retry.cost_availability == "definitely_rejected_zero"
    assert successor.attempt_number == 2
    assert successor.retry_of_judge_attempt_sha256 == retry.judge_attempt_evidence_sha256
    # The nondefault response is durable incident DATA. Fresh public admission
    # accepts its history, but it cannot produce an accepted judge attachment.
    boundaries = list(provider.judge_attempt_root.boundaries)
    payload = boundaries[0].model_dump(mode="json")
    payload["attempts"] = [
        campaign.rejected_nondefault_attempt.model_dump(mode="json"),
        *payload["attempts"][2:],
    ]
    _rehash(payload, "laconian-judge-attempt-boundary-v1", "judge_attempt_boundary_sha256")
    boundaries[0] = JudgeAttemptBoundaryV1.model_validate_json(canonical_json_v1(payload))
    root_payload = provider.judge_attempt_root.index.model_dump(mode="json")
    root_payload["members"][0].update(
        judge_attempt_boundary_sha256=boundaries[0].judge_attempt_boundary_sha256,
        attempt_count=40,
    )
    _rehash(root_payload, "laconian-judge-attempt-root-index-v1", "judge_attempt_root_index_sha256")
    incident_root = tmp_path / "incident-attempts"
    incident_root.mkdir()
    write_judge_attempt_root(
        incident_root,
        index=JudgeAttemptRootIndexV1.model_validate_json(canonical_json_v1(root_payload)),
        boundaries=tuple(boundaries),
    )
    incident = load_verified_judge_attempt_root(
        incident_root,
        expected_request_root_index_sha256=provider.index.judge_request_root_index_sha256,
        request_attachments=provider.judge_request_attachments,
    )
    with pytest.raises(ValueError):
        build_judge_attachment(
            context=provider.generation_context,
            expectation=provider.generation_expectation,
            boundary_ordinal=0,
            request_set=provider.hard_score_request_sets[0],
            request_attachment=provider.judge_request_attachments[0],
            attempt_root=incident,
        )


def test_synthetic_negative_inconclusive_and_supported_models_remain_separate(campaign_source):
    campaign = campaign_source()
    models = campaign.analysis.models
    assert {item.generation_model: item.outcome.outcome.value for item in models} == {
        "gpt-5.6-sol": "negative-quality",
        "gpt-5.6-luna": "inconclusive",
        "gpt-5.6-terra": "supported",
    }
    negative, inconclusive, supported = (
        next(item for item in models if item.generation_model == name)
        for name in (
            "gpt-5.6-sol",
            "gpt-5.6-luna",
            "gpt-5.6-terra",
        )
    )
    assert negative.hard_primary_difference.upper < -0.05
    # Authored if failures: preserve-config has three; the other five constrained
    # non-post scenarios have four each. The shifted baseline failure is not primary.
    # One medical paired cell has two judge failures, leaving 96 semantic pairs.
    assert negative.hard_primary_difference.point == pytest.approx(-23 / 120)
    assert negative.hard_denominators.eligible_pairs == 97
    assert negative.hard_denominators.eligible_scenarios == 12
    assert negative.semantic_denominators.eligible_pairs == 96
    assert negative.semantic_denominators.token_pairs == 96
    assert negative.semantic_denominators.eligible_scenarios == 12
    assert "hard-quality-upper-below-minus-0.05" in negative.outcome.reasons
    assert inconclusive.audit_gate.passed is False
    assert inconclusive.sensitivity.search_exhausted is False
    assert inconclusive.hard_denominators.eligible_pairs == 110
    assert inconclusive.semantic_denominators.eligible_pairs == 110
    assert inconclusive.hard_denominators.eligible_scenarios == 11
    assert inconclusive.semantic_denominators.eligible_scenarios == 11
    for model in (inconclusive, supported):
        assert model.sensitivity.assignment_count == 1
        assert [
            (limit.m_all_judge_fail, limit.d_known_false_fail, limit.k_max_reclassified)
            for limit in model.false_fail_limits
        ] == [(0, 0, 0), (0, 0, 0)]
    assert supported.audit_gate.passed
    assert supported.hard_primary_difference.lower == 0.0
    assert supported.sensitivity.semantic_min_lower.value == 0.0
    assert supported.sensitivity.semantic_max_upper.value == 0.0
    assert supported.sensitivity.token_min_lower.value == 10.0
    assert supported.sensitivity.token_max_upper.value == 10.0
    assert supported.sensitivity.assignment_count == 1
    assert supported.hard_denominators.eligible_pairs == 120
    assert supported.semantic_denominators.token_pairs == 120
    assert supported.semantic_denominators.eligible_scenarios == 12


def test_synthetic_artifacts_are_byte_identical_across_two_fresh_roots(campaign_source, tmp_path):
    first = campaign_source()
    second = helpers.build_synthetic_public_campaign(tmp_path / "fresh-campaign")
    assert first.workspace_root != second.workspace_root
    assert _files(first.workspace_root) == _files(second.workspace_root)
    for campaign in (first, second):
        provider = campaign.provider_fixture.load()
        loaded = reporting.load_verified_analysis_evidence(
            campaign.result_root, provider_evidence=provider
        )
        assert loaded.analysis == first.analysis
        assert loaded.attachment == first.analysis_attachment
        assert (
            load_verified_protocol_review_object_archive(campaign.protocol.archive).objects
            == campaign.protocol.dag.objects
        )


def test_synthetic_analysis_loaders_fail_closed_on_each_parent_hash_substitution(
    campaign_source, tmp_path
):
    campaign = campaign_source()
    parents = (
        "campaign_registry_sha256",
        "protocol_attestation_tag_binding_sha256",
        "protocol_attestation_bundle_sha256",
        "protocol_review_object_archive_sha256",
        "object_closure_root",
        "audit_reviewer_registry_sha256",
        "protocol_reviewer_registry_sha256",
        "protocol_attestations_root",
        "hard_scorer_source_sha256",
        "hard_score_protocol_sha256",
        "judge_protocol_sha256",
        "judge_prompt_sha256",
        "judge_schema_sha256",
        "corpus_case_root",
        "estimand_protocol_sha256",
        "statistical_protocol_sha256",
        "audit_protocol_sha256",
        "bootstrap_protocol_sha256",
        "outcome_classification_protocol_sha256",
        "false_fail_sensitivity_protocol_sha256",
        "audit_sampling_protocol_sha256",
        "audit_commit_reveal_protocol_sha256",
        "audit_adjudication_protocol_sha256",
        "workflow_root",
        "generation_context_expectation_sha256",
        "generation_context_index_sha256",
        "provider_projection_root",
        "provider_evidence_index_sha256",
        "benchmark_provider_evidence_sha256",
        "audit_evidence_sha256",
        "campaign_analysis_sha256",
        "bootstrap_artifact_sha256",
        "report_sha256",
        "checksums_sha256",
    )
    assert len(parents) == len(set(parents)) == 34
    assert set(parents[:24]) == set(BenchmarkProtocolBindingsV1.model_fields)
    for ordinal, field in enumerate(parents):
        root = tmp_path / f"substitution-{ordinal}"
        shutil.copytree(campaign.result_root, root)
        path = root / "analysis/analysis-evidence.json"
        payload = json.loads(path.read_bytes())
        target = (
            payload["protocol_bindings"]
            if field in BenchmarkProtocolBindingsV1.model_fields
            else payload
        )
        target[field] = "f" * 64
        if field in payload:
            payload[field] = "f" * 64
        _rehash(payload, "laconian-verified-analysis-evidence-v1", "analysis_evidence_sha256")
        path.write_bytes(canonical_json(payload) + b"\n")
        with pytest.raises(ValueError):
            reporting.load_verified_analysis_evidence(root, provider_evidence=campaign.provider)


def test_synthetic_audit_reload_reconstructs_archive_pr_review_sources_records_signoffs_and_final_envelope(  # noqa: E501
    campaign_source,
):
    campaign = campaign_source()
    provider = campaign.provider_fixture.load()
    audit = reporting.load_verified_audit_evidence(campaign.audit_root, provider_evidence=provider)
    assert len(audit.pull_request_sources) == 5
    assert len(audit.github_review_sources) == len(audit.github_review_records) == 2
    authority = provider.index.protocol_attestations[0].signature_evidence
    assert authority.github_rest_verification.endpoint.startswith("GET /repos/acme/repo/")
    for source in audit.pull_request_sources:
        number = source.pull_request_record.pr_number
        assert source.pull_request_observation_receipt.endpoint == (
            f"GET /repos/acme/repo/pulls/{number}"
        )
        assert source.signature_evidence.github_rest_verification.endpoint == (
            "GET /repos/acme/repo/git/commits/" + source.signature_evidence.commit_oid
        )
        raw = json.loads(base64.b64decode(source.pull_request_raw_response_base64))
        assert raw["base"]["repo"] == {
            "id": 123,
            "name": "repo",
            "owner": {"login": "acme"},
        }
    for source in audit.github_review_sources:
        assert source.observation_receipt.endpoint == (
            f"GET /repos/acme/repo/pulls/{source.record.pr_number}"
            f"/reviews/{source.record.review_id}"
        )
    assert tuple(row.review_id for row in audit.github_review_records) == (701, 702)
    assert tuple(row.actor_account_id for row in audit.github_review_records) == (201, 202)
    assert tuple(row.identity.reviewer_id for row in audit.reviewer_chains) == (
        "audit-a",
        "audit-b",
    )
    assert len(audit.adjudication.signoffs) == 2
    assert audit.github_review_records == tuple(
        source.record for source in audit.github_review_sources
    )
    core = audit.adjudication.core.model_dump(mode="json")
    digest = core.pop("adjudication_core_sha256")
    assert digest == stable_digest("laconian-audit-adjudication-core-v1", core)
    verify_audit_chain(
        chains=audit.reviewer_chains,
        adjudication=audit.adjudication,
        sample=campaign.sample,
        provider_evidence=provider,
        audit_git_object_archive=audit.audit_git_object_archive,
        pull_request_sources=audit.pull_request_sources,
        github_review_sources=audit.github_review_sources,
    )
    assert (
        audit.attachment.audit_git_object_archive_sha256
        == audit.audit_git_object_archive.audit_git_object_archive_sha256
    )
    assert audit.attachment.adjudication_core_sha256 == digest
    assert audit.attachment.adjudication_sha256 == audit.adjudication.adjudication_sha256
    assert audit.attachment.model_audit_metric_sha256s == tuple(
        item.model_audit_metric_sha256 for item in audit.metrics
    )


def test_synthetic_sample_and_audit_atomic_writers_fresh_reload_exact_roots(
    campaign_source, tmp_path
):
    campaign = campaign_source()
    provider = campaign.provider_fixture.load()
    sample_root = tmp_path / "fresh-sample"
    sample = write_audit_sample_root(
        sample_root,
        population=campaign.sample.population,
        manifest=campaign.sample.manifest,
        packet=campaign.sample.packet,
        provider_evidence=provider,
    )
    assert _files(sample_root) == _files(campaign.sample_root)
    assert load_verified_audit_sample_root(sample_root, provider_evidence=provider) == sample
    audit_root = tmp_path / "fresh-audit"
    attachment = reporting.write_audit_evidence_root(
        audit_root,
        source_sample_root=sample_root,
        provider_evidence=provider,
        sample=sample,
        audit_git_object_archive=campaign.audit.audit_git_object_archive,
        pull_request_sources=campaign.audit.pull_request_sources,
        reviewer_chains=campaign.audit.reviewer_chains,
        github_review_sources=campaign.audit.github_review_sources,
        adjudication=campaign.audit.adjudication,
        metrics=campaign.audit.metrics,
    )
    assert _files(audit_root) == _files(campaign.audit_root)
    assert (
        reporting.load_verified_audit_evidence(audit_root, provider_evidence=provider).attachment
        == attachment
    )
    before = _files(audit_root)
    with pytest.raises(FileExistsError):
        reporting.write_audit_evidence_root(
            audit_root,
            source_sample_root=sample_root,
            provider_evidence=provider,
            sample=sample,
            audit_git_object_archive=campaign.audit.audit_git_object_archive,
            pull_request_sources=campaign.audit.pull_request_sources,
            reviewer_chains=campaign.audit.reviewer_chains,
            github_review_sources=campaign.audit.github_review_sources,
            adjudication=campaign.audit.adjudication,
            metrics=campaign.audit.metrics,
        )
    assert _files(audit_root) == before
    assert {path.name for path in tmp_path.iterdir()} == {"fresh-sample", "fresh-audit"}


def test_synthetic_two_sided_wilson_false_fail_upper_sets_k_and_keeps_zero_error_uncertainty_positive(  # noqa: E501
    campaign_source,
):
    campaign = campaign_source()
    for model in campaign.analysis.models:
        metrics = model.audit_metrics
        for limit in model.false_fail_limits:
            interval = metrics.false_fail_by_primary_arm[limit.arm]
            assert interval.confidence_level == "two-sided-0.95"
            assert interval.z == Decimal("1.959963984540054")
            assert interval.interval_method == "design-weighted-wilson-score-v1"
            assert interval.authorization_use == "false-fail-sensitivity"
            if limit.m_all_judge_fail:
                assert limit.upper_false_fail == interval.upper
                with localcontext(Context(prec=80, rounding=ROUND_CEILING)):
                    ceiling = int(
                        (interval.upper * limit.m_all_judge_fail).to_integral_value(
                            rounding=ROUND_CEILING
                        )
                    )
                assert limit.k_max_reclassified == min(
                    limit.m_all_judge_fail, max(limit.d_known_false_fail, ceiling)
                )
            else:
                assert (
                    limit.upper_false_fail,
                    limit.d_known_false_fail,
                    limit.k_max_reclassified,
                ) == (None, 0, 0)
    supported = next(
        item for item in campaign.analysis.models if item.generation_model == "gpt-5.6-terra"
    )
    assert (
        supported.audit_metrics.agreement.point
        == supported.audit_metrics.agreement.upper
        == Decimal(1)
    )
    assert Decimal(0) < supported.audit_metrics.agreement.lower < Decimal(1)
    assert (
        supported.audit_metrics.false_pass.point
        == supported.audit_metrics.false_pass.lower
        == Decimal(0)
    )
    assert supported.audit_metrics.false_pass.upper > Decimal(0)
    negative = next(
        item for item in campaign.analysis.models if item.generation_model == "gpt-5.6-sol"
    )
    assert [
        (limit.m_all_judge_fail, limit.d_known_false_fail, limit.k_max_reclassified)
        for limit in negative.false_fail_limits
    ] == [(1, 1, 1), (1, 0, 1)]
    assert negative.sensitivity.assignment_count == 2
    zero_error = negative.audit_metrics.false_fail_by_primary_arm["concise"]
    assert (zero_error.denominator.numerator, zero_error.denominator.denominator) == (1, 1)
    assert zero_error.effective_n == Decimal(1)
    assert zero_error.point == zero_error.lower == Decimal(0)
    with localcontext(Context(prec=80)):
        squared_z = Decimal("1.959963984540054") ** 2
        expected_upper = squared_z / (1 + squared_z)
        assert abs(zero_error.upper - expected_upper) < Decimal("1e-78")
    assert Decimal(0) < zero_error.upper < Decimal(1)


def test_synthetic_attestations_accept_null_github_and_keyed_fingerprints_by_mode(campaign_source):
    campaign = campaign_source()
    replayed = load_verified_protocol_review_object_archive(campaign.protocol.archive)
    assert tuple(item.statement.role for item in replayed.prefix.attestations) == ROLES
    for envelope in replayed.prefix.attestations:
        assert (
            VerifiedProtocolAttestationV1.model_validate_json(envelope.model_dump_json())
            == envelope
        )
        statement, evidence = envelope.statement, envelope.signature_evidence
        if statement.verification_mode == "github_verified_commit":
            assert statement.signing_fingerprint is None
            assert "fingerprint" not in type(evidence).model_fields
        else:
            assert statement.verification_mode in {"ssh_sha256", "openpgp_fingerprint"}
            assert statement.signing_fingerprint == evidence.fingerprint
    registry = campaign.provider.index.audit_reviewer_registry
    assert len(registry.reviewers) == 2
    assert registry.audit_reviewer_registry_sha256 == compute_audit_reviewer_registry_sha256(
        registry.reviewers
    )
    assert registry.reviewers[0].signing_fingerprint is registry.reviewers[0].signing_key is None
    assert (
        registry.reviewers[1].signing_fingerprint == registry.reviewers[1].signing_key.fingerprint
    )
    assert base64.b64decode(registry.reviewers[1].signing_key.public_key_base64, validate=True)


def test_synthetic_security_attestation_requires_nonnull_keyed_fingerprint(campaign_source):
    campaign = campaign_source()
    security = campaign.protocol.prefix.attestations[2]
    assert security.statement.role == "security_evidence"
    assert security.statement.verification_mode in {"ssh_sha256", "openpgp_fingerprint"}
    assert security.statement.signing_fingerprint is not None
    for mode in ("github_verified_commit", "ssh_sha256", "openpgp_fingerprint"):
        payload = security.statement.model_dump(mode="json")
        payload.update(verification_mode=mode, signing_fingerprint=None)
        payload.pop("statement_sha256")
        payload["statement_sha256"] = protocol_review_digest(
            "laconian-protocol-review-statement-v1", payload
        )
        with pytest.raises(ValueError):
            ProtocolReviewStatementV1.model_validate_json(canonical_json_v1(payload))
        binding = campaign.protocol.registry.reviewers[2].model_dump(mode="json")
        binding.update(verification_mode=mode, signing_fingerprint=None)
        with pytest.raises(ValueError):
            ProtocolReviewerBindingV1.model_validate_json(canonical_json_v1(binding))


def test_synthetic_attestations_reject_cross_role_reorder_extra_missing_or_duplicate_subject(
    campaign_source,
):
    campaign = campaign_source()
    envelopes = campaign.protocol.prefix.attestations
    assert tuple(item.kind for item in envelopes[2].statement.subjects) == SECURITY_SUBJECTS
    for ordinal, envelope in enumerate(envelopes):
        original = envelope.model_dump(mode="json")
        subjects = original["statement"]["subjects"]
        attacks = (
            list(reversed(subjects)),
            subjects[1:],
            [*subjects, {"kind": "unknown", "sha256": "f" * 64}],
            [subjects[0], *subjects],
            envelopes[(ordinal + 1) % 3].statement.model_dump(mode="json")["subjects"],
        )
        if ordinal == 2:
            attacks += (
                [
                    item
                    for item in subjects
                    if item["kind"]
                    not in {
                        "publication_branch_ruleset_policy_sha256",
                        "broker_token_delivery_isolation_policy_sha256",
                        "broker_signing_keys_root_sha256",
                    }
                ],
            )
        for changed in attacks:
            payload = deepcopy(original)
            payload["statement"]["subjects"] = changed
            with pytest.raises(ValueError):
                VerifiedProtocolAttestationV1.model_validate_json(
                    canonical_json_v1(_rehash_attestation(payload))
                )
    payload = campaign.provider.generation_context.index.model_dump(mode="json")
    payload["protocol_attestations"] = list(reversed(payload["protocol_attestations"]))
    _rehash(
        payload, "laconian-benchmark-generation-context-index-v1", "generation_context_index_sha256"
    )
    with pytest.raises(ValueError):
        GenerationContextIndexV1.model_validate_json(canonical_json_v1(payload))


def test_synthetic_attestations_reject_extra_top_level_field_or_signature_mode_mismatch(
    campaign_source,
):
    campaign = campaign_source()
    for envelope in campaign.protocol.prefix.attestations:
        payload = envelope.model_dump(mode="json")
        payload["undeclared_verified"] = True
        with pytest.raises(ValueError):
            VerifiedProtocolAttestationV1.model_validate_json(
                canonical_json_v1(_rehash_attestation(payload))
            )
        payload = envelope.model_dump(mode="json")
        payload["statement"]["undeclared_verified"] = True
        with pytest.raises(ValueError):
            VerifiedProtocolAttestationV1.model_validate_json(
                canonical_json_v1(_rehash_attestation(payload))
            )
        for mode in {"github_verified_commit", "ssh_sha256", "openpgp_fingerprint"} - {
            envelope.statement.verification_mode
        }:
            payload = envelope.model_dump(mode="json")
            payload["signature_evidence"]["verification_mode"] = mode
            with pytest.raises(ValueError):
                VerifiedProtocolAttestationV1.model_validate_json(
                    canonical_json_v1(_rehash_attestation(payload))
                )


def test_synthetic_protocol_review_constructs_exact_t0_c0_rstat_rjudge_rsecurity_b0_t1_dag(
    campaign_source,
):
    campaign = campaign_source()
    protocol = campaign.protocol
    dag = _verify_dag(protocol)
    golden = _golden_broker_package()
    expected_raw = json.dumps(
        golden, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert len(expected_raw) == 2744
    assert (
        hashlib.sha256(expected_raw).hexdigest()
        == "0dccc2693a148f88c2cc09ea386a7cc0cbb3652b06b75e2eb47158d04a808d5e"
    )
    assert _raw_c0_file(protocol, protocol.input_package_path) == expected_raw
    assert protocol.input_package_bytes == expected_raw
    security = {item.kind: item.sha256 for item in dag.prefix.statements[2].subjects}
    assert (
        security["broker_signing_keys_root_sha256"]
        == "2b3c6d15f0bcb48a2e564766f7365a4f6ad8672e9dd18b64bb4194c39ec5210d"
    )
    assert (
        security["broker_token_delivery_isolation_policy_sha256"]
        == "d2ed58a783a98d9dd60664768758b7331adb3cd34dc971aaa65ffc3124da2474"
    )
    assert tuple(item.kind for item in dag.prefix.statements[2].subjects) == SECURITY_SUBJECTS
    assert tuple(item.statement.role for item in dag.prefix.attestations) == ROLES
    ordered = (
        protocol.input_tag,
        protocol.c0,
        *protocol.commits,
        protocol.b0,
        protocol.companion_tag,
    )
    assert tuple(item.object_type for item in ordered) == (
        "tag",
        "commit",
        "commit",
        "commit",
        "commit",
        "commit",
        "tag",
    )
    assert len({item.oid for item in ordered}) == 7
    assert b"object " + protocol.c0.oid.encode() + b"\n" in protocol.input_tag.raw_content
    previous = protocol.c0
    for commit in (*protocol.commits, protocol.b0):
        assert [
            line for line in commit.raw_content.splitlines() if line.startswith(b"parent ")
        ] == [b"parent " + previous.oid.encode()]
        previous = commit
    assert b"object " + protocol.b0.oid.encode() + b"\n" in protocol.companion_tag.raw_content
    assert protocol.bundle.attestations == dag.prefix.attestations
    assert len(protocol.operator_registry.operators) == 1
    assert len(protocol.ruleset_policy.rulesets) == 2
    assert len(protocol.workflow_inventory.members) == 15
    assert protocol.t0_suite.receipt.rule_suite_id == 1001
    assert protocol.t1_suite.receipt.rule_suite_id == 1002
    assert protocol.t0_suite.receipt.before_sha == protocol.t1_suite.receipt.before_sha == "0" * 40
    assert protocol.t0_suite.receipt.after_sha == protocol.input_tag.oid
    assert protocol.t1_suite.receipt.after_sha == protocol.companion_tag.oid
    assert not set(protocol.t0_suite.receipt.request_ids) & set(
        protocol.t1_suite.receipt.request_ids
    )
    assert protocol.binding.peeled_c0_oid == protocol.c0.oid
    assert protocol.binding.bundle_commit_oid == protocol.b0.oid
    assert protocol.binding.companion_tag_oid == protocol.companion_tag.oid


def test_synthetic_protocol_review_reconstructs_all_raw_objects_and_receipts_without_network(
    campaign_source,
):
    campaign = campaign_source()
    protocol = campaign.protocol
    replayed = load_verified_protocol_review_object_archive(protocol.archive)
    assert replayed.objects == protocol.dag.objects
    assert replayed.prefix.attestations == protocol.prefix.attestations
    assert replayed.bundle == protocol.bundle
    assert replayed.tag_creation_suites == (protocol.t0_suite.receipt, protocol.t1_suite.receipt)
    assert protocol.binding.object_closure_root == protocol.archive.object_closure_root
    assert tuple(item.receipt_kind for item in protocol.archive.api_receipts) == (
        "github_signature",
        "github_signature",
        "github_signature",
        "tag_ruleset_observation",
        "t0_creation_suite",
        "t1_creation_suite",
    )
    archived = {item.oid: item for item in protocol.archive.objects}
    for item in replayed.objects:
        raw = base64.b64decode(archived[item.oid].raw_content_base64, validate=True)
        assert raw == item.raw_content
        header = f"{item.object_type} {len(raw)}\0".encode()
        assert hashlib.sha1(header + raw).hexdigest() == item.oid
        assert hashlib.sha256(header + raw).hexdigest() == item.git_object_sha256
    for blob in protocol.archive.api_blobs:
        raw = base64.b64decode(blob.raw_bytes_base64, validate=True)
        assert len(raw) == blob.byte_length
        assert hashlib.sha256(raw).hexdigest() == blob.sha256
    assert canonical_json_v1(replayed.bundle.model_dump(mode="json")) == canonical_json_v1(
        protocol.bundle.model_dump(mode="json")
    )


def test_synthetic_protocol_review_rejects_every_canonical_json_git_header_tree_delta_signature_ruleset_creation_suite_and_cross_campaign_negative(  # noqa: E501
    campaign_source,
):
    campaign = campaign_source()
    protocol = campaign.protocol
    for raw in (b'{"a":1,"a":1}', b'{ "a":1}', b'{"a":1.0}', b'{"a":"e\\u0301"}', b'{"a":1}\n'):
        with pytest.raises(ValueError):
            parse_canonical_json_v1(raw)
    for object_type in ("unknown", "tree\x00commit", "commit\n"):
        with pytest.raises(ValueError):
            parse_protocol_git_object(
                oid=protocol.c0.oid, object_type=object_type, raw_content=protocol.c0.raw_content
            )
    with pytest.raises(ValueError):
        _verify_dag(protocol, objects=protocol.dag.objects[:-1])
    with pytest.raises(ValueError):
        _verify_dag(
            protocol,
            signature_evidence_sources=tuple(
                item.source for item in reversed(protocol.observations)
            ),
        )
    with pytest.raises(ValueError):
        _verify_dag(
            protocol, tag_creation_suites=(protocol.t0_suite.receipt, protocol.t0_suite.receipt)
        )
    with pytest.raises(ValueError):
        _verify_dag(protocol, input_tag_ref="refs/tags/benchmark-input-20260831.2")
    # Each input is raw malformed DATA; public verification is always called here.
    # These attacks are separate from simple outer-digest corruption above.
    assert set(protocol.negative_dag_inputs) == {
        "duplicate-git-header",
        "wrong-tree-delta",
        "extra-empty-subtree",
        "bad-keyed-signature",
        "ruleset-extra-bypass",
        "t0-creation-wrong-after",
        "t1-creation-replayed-request",
        "cross-campaign-statement",
    }
    for altered in protocol.negative_dag_inputs.values():
        with pytest.raises(ValueError):
            _verify_dag(protocol, **altered)


def test_synthetic_every_downstream_attachment_binds_campaign_registry_tag_binding_attestation_workflow_and_archive_closure_roots(  # noqa: E501
    campaign_source,
):
    campaign = campaign_source()
    provider = campaign.provider_fixture.load()
    index = provider.generation_context.index
    protocol = campaign.protocol
    expected = {
        "campaign_registry_sha256": index.campaign_registry_sha256,
        "protocol_attestation_tag_binding_sha256": (
            protocol.binding.protocol_attestation_tag_binding_sha256
        ),
        "protocol_attestation_bundle_sha256": protocol.bundle.protocol_attestation_bundle_sha256,
        "protocol_review_object_archive_sha256": (
            protocol.archive.protocol_review_object_archive_sha256
        ),
        "object_closure_root": protocol.archive.object_closure_root,
        "audit_reviewer_registry_sha256": (
            provider.index.audit_reviewer_registry.audit_reviewer_registry_sha256
        ),
        "protocol_reviewer_registry_sha256": protocol.registry.protocol_reviewer_registry_sha256,
        "protocol_attestations_root": protocol.bundle.protocol_attestations_root,
        "workflow_root": protocol.workflow_inventory.workflow_root,
        "statistical_protocol_sha256": STATISTICAL_PROTOCOL,
        "audit_protocol_sha256": AUDIT_PROTOCOL,
    }
    owners = (
        provider.projection,
        *provider.hard_score_request_sets,
        *provider.judge_request_attachments,
        *provider.judge_attachments,
        campaign.sample.population.attachment,
        campaign.sample.manifest,
        campaign.audit.attachment,
        *campaign.audit.metrics,
        campaign.analysis,
        campaign.analysis_attachment,
    )
    assert len(owners) == 117
    assert campaign.sample.packet.campaign_registry_sha256 == expected["campaign_registry_sha256"]
    for owner in owners:
        for field, value in expected.items():
            assert getattr(owner.protocol_bindings, field) == value
            if field in type(owner).model_fields:
                assert getattr(owner, field) == value
    for field, value in expected.items():
        assert getattr(index, field) == value
    assert (
        provider.index.generation_context_expectation_sha256
        == provider.generation_expectation.expectation.generation_context_expectation_sha256
    )
    assert provider.index.generation_context_index_sha256 == index.generation_context_index_sha256
    assert (
        provider.index.judge_attempt_root_index_sha256
        == provider.judge_attempt_root.index.judge_attempt_root_index_sha256
    )
    assert (
        tuple(item.statement for item in index.protocol_attestations) == protocol.prefix.statements
    )
