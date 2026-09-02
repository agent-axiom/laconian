"""Deterministic payload helpers shared by benchmark Task 3 tests."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from laconian_eval.capsule.canonical import stable_digest

if TYPE_CHECKING:
    import pytest

    from laconian_eval.benchmark.context import (
        LayerRootIndexV1,
        VerifiedGenerationContextExpectationV1,
        VerifiedGenerationContextIndexV1,
    )
    from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2


def sha256_marker(ordinal: int) -> str:
    """Return one deterministic lowercase SHA-256-shaped test value."""

    return f"{ordinal:064x}"


def git_oid_marker(ordinal: int) -> str:
    """Return one deterministic lowercase Git-SHA-1-shaped test value."""

    return f"{ordinal:040x}"


def generation_layer_index_payload(*, campaign_id: str = "campaign-2026-08-31") -> dict[str, Any]:
    """Return a complete canonical 36-member generation-layer payload."""

    members = [
        {
            "member_kind": "generation",
            "ordinal": ordinal,
            "generation_model": f"model-{ordinal // 12:02d}",
            "scenario_uid": sha256_marker(1_000 + ordinal),
            "capsule_relative_path": f"generation/{ordinal:02d}/capsule",
            "generation_capsule_sha256": sha256_marker(2_000 + ordinal),
            "scored_sidecar_relative_path": f"generation/{ordinal:02d}/scored.json",
            "scored_sidecar_sha256": sha256_marker(3_000 + ordinal),
        }
        for ordinal in range(36)
    ]
    payload: dict[str, Any] = {
        "schema_version": "benchmark-layer-root-index-v1",
        "layer_kind": "generation",
        "campaign_id": campaign_id,
        "members": members,
    }
    payload["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1", payload
    )
    return payload


def generation_expectation_payload(
    *,
    campaign_id: str = "campaign-2026-08-31",
    generation_layer_root: str | None = None,
    expected_context_index_sha256: str | None = None,
) -> dict[str, Any]:
    """Return one self-hashed generation-context expectation payload."""

    payload: dict[str, Any] = {
        "schema_version": "benchmark-generation-context-expectation-v1",
        "campaign_id": campaign_id,
        "campaign_registry_sha256": sha256_marker(10),
        "audit_reviewer_registry_sha256": sha256_marker(11),
        "protocol_reviewer_registry_sha256": sha256_marker(12),
        "protocol_attestations_root": sha256_marker(13),
        "predecessor_authority_root_sha256": sha256_marker(14),
        "generation_layer_root": generation_layer_root or sha256_marker(15),
        "expected_context_index_sha256": expected_context_index_sha256 or sha256_marker(16),
        "workflow_root": sha256_marker(17),
    }
    payload["generation_context_expectation_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-expectation-v1", payload
    )
    return payload


def hard_score_record_payload(
    ordinal: int,
    *,
    hard_pass: bool = True,
    terminal_reason: str = "success",
) -> dict[str, Any]:
    """Return one structurally valid hard-score record payload."""

    response_id = sha256_marker(20_000 + ordinal) if terminal_reason == "success" else None
    if hard_pass:
        reason_codes = ["hard_pass"]
        judge_request_id = sha256_marker(30_000 + ordinal)
    elif terminal_reason in {"provider_rejected", "retry_exhausted"}:
        reason_codes = [terminal_reason]
        judge_request_id = None
    else:
        reason_codes = ["required_literal"]
        judge_request_id = None
    return {
        "ordinal": ordinal,
        "plan_item_id": sha256_marker(40_000 + ordinal),
        "attempt_id": sha256_marker(50_000 + ordinal),
        "response_id": response_id,
        "terminal_reason": terminal_reason,
        "hard_pass": hard_pass,
        "reason_codes": reason_codes,
        "judge_request_id": judge_request_id,
    }


def protocol_bindings_payload() -> dict[str, Any]:
    """Return all frozen downstream protocol-binding fields in schema order."""

    names = (
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
    )
    return {name: sha256_marker(60_000 + ordinal) for ordinal, name in enumerate(names)}


def audit_reviewer_registry() -> Any:
    """Build the exact two-reviewer audit registry with freshly recomputed bytes."""

    from laconian_eval.benchmark.protocol_review import (
        AuditReviewerRegistryV1,
        ReviewerAccountBindingV1,
        compute_audit_reviewer_registry_sha256,
    )

    reviewers = (
        ReviewerAccountBindingV1(
            reviewer_id="audit-a",
            reviewer_numeric_account_id=201,
            reviewer_login="audit-reviewer-a",
            verification_mode="github_verified_commit",
            signing_fingerprint=None,
            role="audit_reviewer",
        ),
        ReviewerAccountBindingV1(
            reviewer_id="audit-b",
            reviewer_numeric_account_id=202,
            reviewer_login="audit-reviewer-b",
            verification_mode="ssh_sha256",
            signing_fingerprint="SHA256:" + "D" * 43,
            role="audit_reviewer",
        ),
    )
    return AuditReviewerRegistryV1(
        schema_version="benchmark-reviewer-registry-v1",
        reviewers=reviewers,
        audit_reviewer_registry_sha256=compute_audit_reviewer_registry_sha256(reviewers),
    )


def protocol_reviewer_registry() -> Any:
    """Build the exact ordered three-role protocol reviewer registry."""

    from laconian_eval.benchmark.protocol_review import (
        ProtocolReviewerBindingV1,
        ProtocolReviewerRegistryV1,
        compute_protocol_reviewer_registry_sha256,
    )

    reviewers = (
        ProtocolReviewerBindingV1(
            role="statistical_method",
            reviewer_numeric_account_id=301,
            reviewer_login="statistics-reviewer",
            verification_mode="github_verified_commit",
            signing_fingerprint=None,
            author_name_ascii="Statistics Reviewer",
            author_email_ascii="statistics-reviewer@users.noreply.github.com",
            committer_name_ascii="Statistics Reviewer",
            committer_email_ascii="statistics-reviewer@users.noreply.github.com",
        ),
        ProtocolReviewerBindingV1(
            role="blind_judge_audit_protocol",
            reviewer_numeric_account_id=302,
            reviewer_login="judge-reviewer",
            verification_mode="ssh_sha256",
            signing_fingerprint="SHA256:" + "E" * 43,
            author_name_ascii="Judge Reviewer",
            author_email_ascii="judge-reviewer@users.noreply.github.com",
            committer_name_ascii="Judge Reviewer",
            committer_email_ascii="judge-reviewer@users.noreply.github.com",
        ),
        ProtocolReviewerBindingV1(
            role="security_evidence",
            reviewer_numeric_account_id=303,
            reviewer_login="security-reviewer",
            verification_mode="openpgp_fingerprint",
            signing_fingerprint="F" * 40,
            author_name_ascii="Security Reviewer",
            author_email_ascii="security-reviewer@users.noreply.github.com",
            committer_name_ascii="Security Reviewer",
            committer_email_ascii="security-reviewer@users.noreply.github.com",
        ),
    )
    return ProtocolReviewerRegistryV1(
        schema_version="benchmark-protocol-reviewer-registry-v1",
        reviewers=reviewers,
        protocol_reviewer_registry_sha256=compute_protocol_reviewer_registry_sha256(reviewers),
    )


def protocol_subject_values() -> dict[str, str]:
    """Return one distinct digest for every owner-ordered protocol subject."""

    from laconian_eval.benchmark.protocol_review import (
        PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1,
    )

    kinds = tuple(
        kind
        for role in (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        for kind in PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1[role]
    )
    values = {kind: sha256_marker(80_000 + ordinal) for ordinal, kind in enumerate(kinds)}
    values.update(
        judge_prompt_sha256="6e5e97ef532bf45f3df7e6b8accc24557259e5527290793354de00ee50fd68db",
        judge_schema_sha256="37418892e29c9af0a6f8a57348de07b26d8a83f9fd163fbb4b1a487a0120e95c",
        identity_registry_bundle_sha256=(
            protocol_identity_registry_bundle().identity_registry_bundle_sha256
        ),
    )
    return values


def protocol_identity_registry_bundle() -> Any:
    """Build one deterministic self-bound identity bundle for judge request fixtures."""

    from laconian_eval.benchmark.protocol_review import (
        ProtocolReviewIdentityRegistryBundleV1,
        protocol_review_digest,
    )

    dependency_lock_sha256 = hashlib.sha256(
        (Path(__file__).parents[2] / "uv.lock").read_bytes()
    ).hexdigest()
    tool_sha256 = protocol_review_digest(
        "laconian-protocol-signature-verifier-tool-v1",
        {
            "algorithm_profile": (
                "ssh-ed25519-sshsig-git-sha512-or-openpgp-v4-ed25519-sha256-v1"
            ),
            "dependency_lock_path": "uv.lock",
            "dependency_lock_sha256": dependency_lock_sha256,
            "verifier_dependency_inventory_root": sha256_marker(80_100),
            "entrypoint": (
                "laconian_eval.benchmark.protocol_review:_verify_keyed_signature_v1"
            ),
            "verifier_source_path": "src/laconian_eval/benchmark/protocol_review.py",
            "verifier_source_sha256": sha256_marker(80_101),
        },
    )
    payload: dict[str, Any] = {
        "schema_version": "ProtocolReviewIdentityRegistryBundleV1",
        "keys": (),
        "verifier_source_path": "src/laconian_eval/benchmark/protocol_review.py",
        "verifier_source_sha256": sha256_marker(80_101),
        "dependency_lock_path": "uv.lock",
        "dependency_lock_sha256": dependency_lock_sha256,
        "verifier_dependency_inventory_root": sha256_marker(80_100),
        "protocol_signature_verifier_tool_sha256": tool_sha256,
    }
    payload["identity_registry_bundle_sha256"] = protocol_review_digest(
        "laconian-protocol-review-identity-registry-bundle-v1",
        payload,
    )
    return ProtocolReviewIdentityRegistryBundleV1.model_validate(payload)


def verified_protocol_attestations(
    *,
    registry: Any,
    workflow_root: str,
    subject_values: dict[str, str],
) -> tuple[Any, Any, Any]:
    """Build three mode-discriminated envelopes coherent with one reviewer registry."""

    from laconian_eval.benchmark.protocol_review import (
        GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
        PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1,
        GitHubCommitVerificationProjectionV1,
        GitHubSignatureProjectionV1,
        GitHubVerifiedCommitEvidenceV1,
        LocalSignatureVerificationReceiptV1,
        OpenPGPVerifiedCommitEvidenceV1,
        ProtocolReviewStatementV1,
        SSHVerifiedCommitEvidenceV1,
        VerifiedProtocolAttestationV1,
        protocol_review_digest,
    )

    input_tag_ref = "refs/tags/benchmark-input-20260831.1"
    statement_names = (
        "01-statistical-method.json",
        "02-blind-judge-audit-protocol.json",
        "03-security-evidence.json",
    )
    attestations: list[Any] = []
    for ordinal, (reviewer, statement_name) in enumerate(
        zip(registry.reviewers, statement_names, strict=True),
        start=1,
    ):
        subjects = [
            {"kind": kind, "sha256": subject_values[kind]}
            for kind in PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1[reviewer.role]
        ]
        statement_payload: dict[str, Any] = {
            "schema_version": "ProtocolReviewStatementV1",
            "role": reviewer.role,
            "protocol_registry_sha256": registry.protocol_reviewer_registry_sha256,
            "reviewer_numeric_account_id": reviewer.reviewer_numeric_account_id,
            "reviewer_login": reviewer.reviewer_login,
            "verification_mode": reviewer.verification_mode,
            "signing_fingerprint": reviewer.signing_fingerprint,
            "input_tag_ref": input_tag_ref,
            "input_tag_oid": git_oid_marker(100),
            "input_tag_object_sha256": sha256_marker(101),
            "peeled_c0_oid": git_oid_marker(102),
            "peeled_c0_sha256": sha256_marker(103),
            "workflow_root": workflow_root,
            "subjects": subjects,
            "subject_root": protocol_review_digest(
                "laconian-protocol-review-subjects-root-v1", subjects
            ),
            "signed_at": f"2026-08-31T00:00:0{ordinal}Z",
        }
        statement_payload["statement_sha256"] = protocol_review_digest(
            "laconian-protocol-review-statement-v1", statement_payload
        )
        statement = ProtocolReviewStatementV1.model_validate(statement_payload)

        commit_oid = git_oid_marker(110 + ordinal)
        rest_payload: dict[str, Any] = {
            "schema_version": "GitHubCommitVerificationProjectionV1",
            "repository_id": 123,
            "commit_oid": commit_oid,
            "api_version": "2022-11-28",
            "endpoint": f"GET /repos/acme/laconian/git/commits/{commit_oid}",
            "verified": True,
            "reason": "valid",
            "payload": f"signed payload {ordinal}\n",
            "signature": f"signature {ordinal}\n",
            "verified_at": f"2026-08-31T00:01:0{ordinal}.000000Z",
        }
        rest_payload["rest_projection_sha256"] = protocol_review_digest(
            "laconian-github-commit-verification-projection-v1", rest_payload
        )
        rest = GitHubCommitVerificationProjectionV1.model_validate(rest_payload)

        graphql_payload: dict[str, Any] = {
            "schema_version": "GitHubSignatureProjectionV1",
            "repository_id": 123,
            "commit_oid": commit_oid,
            "query_sha256": GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
            "signer_database_id": reviewer.reviewer_numeric_account_id,
            "signer_login": reviewer.reviewer_login,
            "is_valid": True,
            "state": "VALID",
        }
        graphql_payload["graphql_projection_sha256"] = protocol_review_digest(
            "laconian-github-signature-projection-v1", graphql_payload
        )
        graphql = GitHubSignatureProjectionV1.model_validate(graphql_payload)
        evidence_payload: dict[str, Any] = {
            "schema_version": {
                "github_verified_commit": "GitHubVerifiedCommitEvidenceV1",
                "ssh_sha256": "SSHVerifiedCommitEvidenceV1",
                "openpgp_fingerprint": "OpenPGPVerifiedCommitEvidenceV1",
            }[reviewer.verification_mode],
            "verification_mode": reviewer.verification_mode,
            "commit_oid": commit_oid,
            "commit_object_sha256": sha256_marker(120 + ordinal),
            "parent_commit_oid": git_oid_marker(120 + ordinal),
            "statement_path": (
                "benchmarks/protocol-reviews/benchmark-input-20260831.1/statements/"
                + statement_name
            ),
            "github_rest_verification": rest.model_dump(mode="json"),
            "github_graphql_signature": graphql.model_dump(mode="json"),
        }
        if reviewer.verification_mode != "github_verified_commit":
            local_payload: dict[str, Any] = {
                "verified": True,
                "signed_payload_sha256": sha256_marker(130 + ordinal),
                "signature_sha256": sha256_marker(140 + ordinal),
                "verifier_tool_sha256": sha256_marker(150 + ordinal),
            }
            local_payload["verification_receipt_sha256"] = protocol_review_digest(
                "laconian-local-signature-verification-receipt-v1", local_payload
            )
            local = LocalSignatureVerificationReceiptV1.model_validate(local_payload)
            evidence_payload.update(
                fingerprint=reviewer.signing_fingerprint,
                keyring_sha256=sha256_marker(160 + ordinal),
                local_signature_verification=local.model_dump(mode="json"),
            )
        evidence_type = {
            "github_verified_commit": GitHubVerifiedCommitEvidenceV1,
            "ssh_sha256": SSHVerifiedCommitEvidenceV1,
            "openpgp_fingerprint": OpenPGPVerifiedCommitEvidenceV1,
        }[reviewer.verification_mode]
        evidence = evidence_type.model_validate(evidence_payload)
        attestation_payload: dict[str, Any] = {
            "schema_version": "VerifiedProtocolAttestationV1",
            "statement": statement.model_dump(mode="json"),
            "signature_evidence": evidence.model_dump(mode="json"),
        }
        attestation_payload["attestation_sha256"] = protocol_review_digest(
            "laconian-verified-protocol-attestation-v1", attestation_payload
        )
        attestations.append(VerifiedProtocolAttestationV1.model_validate(attestation_payload))
    return tuple(attestations)  # type: ignore[return-value]


def generation_context_index_payload(
    root_index: Any,
    *,
    campaign_id: str | None = None,
    workflow_root: str | None = None,
) -> dict[str, Any]:
    """Return a full self-hashed context coherent with both registries and attestations."""

    from laconian_eval.benchmark.protocol_review import compute_protocol_attestations_root

    root_campaign_id = root_index.campaign_id if campaign_id is None else campaign_id
    bound_workflow_root = sha256_marker(90_000) if workflow_root is None else workflow_root
    audit_registry = audit_reviewer_registry()
    protocol_registry = protocol_reviewer_registry()
    subjects = protocol_subject_values()
    attestations = verified_protocol_attestations(
        registry=protocol_registry,
        workflow_root=bound_workflow_root,
        subject_values=subjects,
    )
    campaign_seed = sha256_marker(90_001)
    generation_members = root_index.members
    payload: dict[str, Any] = {
        "schema_version": "benchmark-generation-context-index-v1",
        "campaign_id": root_campaign_id,
        "campaign_registry_sha256": sha256_marker(90_002),
        "protocol_attestation_tag_binding_sha256": sha256_marker(90_003),
        "protocol_attestation_bundle_sha256": sha256_marker(90_004),
        "protocol_review_object_archive_sha256": sha256_marker(90_005),
        "object_closure_root": sha256_marker(90_006),
        "audit_reviewer_registry_sha256": audit_registry.audit_reviewer_registry_sha256,
        "protocol_reviewer_registry_sha256": (protocol_registry.protocol_reviewer_registry_sha256),
        "protocol_attestations_root": compute_protocol_attestations_root(attestations),
        "campaign_seed": campaign_seed,
        "campaign_seed_sha256": stable_digest(
            "laconian-campaign-seed-v1",
            {
                "schema_version": "1",
                "algorithm": "public-hex-seed-v1",
                "campaign_seed": campaign_seed,
            },
        ),
        "input_tag_commit": git_oid_marker(102),
        "hard_scorer_source_sha256": sha256_marker(90_008),
        "hard_score_protocol_sha256": subjects["hard_score_protocol_sha256"],
        "judge_protocol_sha256": (
            "2aee6c1afaa8fb59958113566a73a547ae2b70c93b454fcd6afef2889c7563e8"
        ),
        "judge_prompt_sha256": subjects["judge_prompt_sha256"],
        "judge_schema_sha256": subjects["judge_schema_sha256"],
        "judge_requested_service_tier": "default",
        "judge_service_tier_wire_field": "service_tier",
        "corpus_case_root": subjects["corpus_case_root"],
        "statistical_protocol_sha256": subjects["statistical_protocol_sha256"],
        "audit_protocol_sha256": sha256_marker(90_010),
        "estimand_protocol_sha256": subjects["estimand_protocol_sha256"],
        "bootstrap_protocol_sha256": subjects["bootstrap_protocol_sha256"],
        "outcome_classification_protocol_sha256": subjects[
            "outcome_classification_protocol_sha256"
        ],
        "false_fail_sensitivity_protocol_sha256": subjects[
            "false_fail_sensitivity_protocol_sha256"
        ],
        "audit_sampling_protocol_sha256": subjects["audit_sampling_protocol_sha256"],
        "audit_commit_reveal_protocol_sha256": subjects["audit_commit_reveal_protocol_sha256"],
        "audit_adjudication_protocol_sha256": subjects["audit_adjudication_protocol_sha256"],
        "workflow_root": bound_workflow_root,
        "audit_reviewer_registry": audit_registry.model_dump(mode="json"),
        "protocol_reviewer_registry": protocol_registry.model_dump(mode="json"),
        "protocol_attestations": [item.model_dump(mode="json") for item in attestations],
        "generation_root_index_sha256": root_index.layer_root_index_sha256,
        "provider_projection_root": sha256_marker(90_011),
        "ordered_generation_capsule_sha256s": [
            item.generation_capsule_sha256 for item in generation_members
        ],
    }
    payload["generation_context_index_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-index-v1", payload
    )
    return payload


def _load_task3_shard_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any]:
    """Prepare one 2-locale x 4-arm x 5-repetition scenario shard."""

    import yaml

    from laconian_eval.capsule.canonical import canonical_jsonl
    from laconian_eval.capsule.planning import materialize_case_index, materialize_parent_plan
    from laconian_eval.capsule.sharding import project_shard_plans, shard_plan_file_bytes
    from tests.capsule import test_prepare as prepare_test_module

    repository_root = Path(__file__).parents[2]
    source = tmp_path / "task3-shard-source"
    source.mkdir()
    cases: list[dict[str, object]] = []
    for scenario in range(12):
        for locale in ("en", "ru"):
            case = prepare_test_module._case(
                f"task3-{scenario:03d}-{locale}",
                f"task3-{scenario:03d}",
                locale,
                f"Answer scenario {scenario} in {locale}.",
            )
            case["hard_constraints"] = {"required_literals": ["Done."]}
            cases.append(case)
    case_path = source / "cases/response.yaml"
    case_path.parent.mkdir(parents=True)
    case_path.write_bytes(
        yaml.safe_dump(
            {"schema_version": "1", "kind": "response", "cases": cases},
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    manifest_payload = prepare_test_module._manifest_payload(
        provider_kind="openai",
        api_key_env="LIVE_TEST_API_KEY",
        repetitions=5,
        arms=["baseline", "concise", "caveman", "if"],
    )
    provider_payload = manifest_payload["provider"]
    assert isinstance(provider_payload, dict)
    provider_payload["model"] = "gpt-5.6-sol"
    manifest = source / "manifest.yaml"
    manifest.write_bytes(
        yaml.safe_dump(manifest_payload, allow_unicode=True, sort_keys=False).encode("utf-8")
    )
    captured_source = prepare_test_module.prepare_module.load_source_manifest_capture(
        manifest,
        input_root=None,
        invocation_cwd=source,
    )
    captured = prepare_test_module.prepare_module.capture_authored_inputs(
        captured_source,
        source_root=repository_root,
    )
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    parent_plan = materialize_parent_plan(
        parent_manifest_sha256=captured.manifest_sha256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )
    shards = project_shard_plans(
        campaign_id="public-foundations-v1",
        resolved_manifest=captured.resolved_manifest,
        parent_manifest_sha256=captured.manifest_sha256,
        parent_plan=parent_plan,
        case_index=case_index,
        captured_arms=captured.arms,
    )
    assert len(parent_plan) == 480
    assert len(shards) == 12
    shard = shards[0]
    assert shard.row_count == 40
    planning = tmp_path / "planning"
    planning.mkdir()
    (planning / "parent-plan.jsonl").write_bytes(
        canonical_jsonl(row.model_dump(mode="json") for row in parent_plan)
    )
    (planning / "shard-plan.json").write_bytes(shard_plan_file_bytes(shard))
    results_root = tmp_path / "task3-shard-results"
    results_root.mkdir()
    prepare_test_module._install_harness(monkeypatch, results_root)
    request_type = prepare_test_module.prepare_module.PrepareShardRequest
    prepared = prepare_test_module.prepare_module.prepare_shard_capsule(
        request_type(
            prepare=prepare_test_module._request(
                manifest,
                results_root,
                invocation_cwd=tmp_path,
                source_root=repository_root,
            ),
            parent_plan_path=Path("planning/parent-plan.jsonl"),
            shard_plan_path=Path("planning/shard-plan.json"),
        )
    )
    return prepared, shard


def load_real_sealed_40_row_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    all_hard_fail: bool = False,
) -> tuple[Path, Path, VerifiedScoredCapsuleV2]:
    """Exercise the real Slice 1 pipeline and return one verified mixed-outcome shard."""

    import laconian_eval.capsule.execution as execution_module
    from laconian_eval.capsule.attempts import AttemptUsageV2
    from laconian_eval.capsule.execution import ProviderFactory
    from laconian_eval.capsule.finalize import finalize_capsule
    from laconian_eval.capsule.sidecars import (
        load_verified_scored_capsule,
        write_scored_sidecar,
    )
    from laconian_eval.providers.replay import _benchmark_error_evidence
    from tests.capsule.test_execution import (
        _benchmark_replay_outcome,
        _benchmark_replay_response_with_output,
        _BenchmarkScriptedProvider,
        _install_fast_runtime,
        _seams_for_provider,
    )

    prepared, shard = _load_task3_shard_success(
        tmp_path,
        monkeypatch,
    )
    assert shard.row_count == 40
    monkeypatch.setattr(
        execution_module._fake_provider_module,
        "FakeProvider",
        execution_module._FAKE_PROVIDER_TYPE,
    )
    monkeypatch.setattr(
        execution_module._replay_provider_module,
        "ReplayProvider",
        execution_module._REPLAY_PROVIDER_TYPE,
    )
    monkeypatch.setattr(
        execution_module._openai_provider_module,
        "OpenAIProvider",
        execution_module._OPENAI_PROVIDER_TYPE,
    )
    _install_fast_runtime(monkeypatch)
    passing = _benchmark_replay_outcome(returned_service_tier="default")
    deterministic_failure = _benchmark_replay_response_with_output("Not this time.")
    provider_failure = _benchmark_error_evidence(
        requested_model_id="gpt-5.6-sol",
        delivery_certainty="definitely_rejected",
        provider_request_id="fixture-rejected-request-v1",
        response_id=None,
        raw_source=None,
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
            cache_read_status="not_applicable_definitely_rejected",
            cache_write_status="not_applicable_definitely_rejected",
            reasoning_token_accounting="not_reported",
        ),
        returned_model_id=None,
        returned_service_tier=None,
        service_tier_status="not_applicable_definitely_rejected",
        applied_prompt_cache_mode=None,
        applied_prompt_cache_ttl=None,
        applied_cache_control_status="not_applicable_definitely_rejected",
        structured_status=400,
    )
    outcomes = (
        [deterministic_failure] * 40
        if all_hard_fail
        else [provider_failure, deterministic_failure, *([passing] * 38)]
    )
    provider = _BenchmarkScriptedProvider(outcomes)
    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )
    assert outcome.exit_code == 0, (outcome, len(provider.benchmark_calls))
    assert outcome.result.state == "GENERATION_COMPLETE", outcome
    assert len(provider.benchmark_calls) == 40, outcome
    assert finalize_capsule(prepared.path).state == "SEALED_COMPLETE"
    sidecar_path = tmp_path / "scored-sidecar.json"
    write_scored_sidecar(prepared.path, sidecar_path)
    evidence = load_verified_scored_capsule(prepared.path, sidecar_path)
    assert evidence.capsule_sha256
    assert evidence.seal.generation_status == "complete"
    assert evidence.seal.structural_integrity == "valid"
    assert len(evidence.plan) == len(evidence.scored_attempts) == 40
    if all_hard_fail:
        assert not any(row.hard_pass for row in evidence.scored_attempts)
        assert all(
            row.terminal_reason == "success" and row.response_id is not None
            for row in evidence.scored_attempts
        )
    else:
        assert sum(row.hard_pass for row in evidence.scored_attempts) == 38
        assert (
            sum(row.terminal_reason == "provider_rejected" for row in evidence.scored_attempts) == 1
        )
        deterministic_failures = tuple(
            row
            for row in evidence.scored_attempts
            if row.terminal_reason == "success" and not row.hard_pass
        )
        assert len(deterministic_failures) == 1
        assert deterministic_failures[0].response_id is not None
    return prepared.path, sidecar_path, evidence


def _load_minimal_real_sealed_evidence(
    build_root: Path,
    results_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    generation_model: str,
    scenario_ordinal: int,
) -> tuple[Path, Path, VerifiedScoredCapsuleV2]:
    """Build one minimum-size genuine scored capsule for a public model/scenario."""

    import yaml

    import laconian_eval.capsule.execution as execution_module
    from laconian_eval.capsule.execution import ProviderFactory
    from laconian_eval.capsule.finalize import finalize_capsule
    from laconian_eval.capsule.sidecars import (
        load_verified_scored_capsule,
        write_scored_sidecar,
    )
    from tests.capsule import test_prepare as prepare_test_module
    from tests.capsule.test_execution import (
        _benchmark_replay_outcome,
        _BenchmarkScriptedProvider,
        _install_fast_runtime,
        _seams_for_provider,
    )

    scenario_id = f"task3-{scenario_ordinal:03d}"
    source = build_root / "source"
    case_path = source / "cases/response.yaml"
    case_path.parent.mkdir(parents=True)
    cases = [
        prepare_test_module._case(
            f"{scenario_id}-{locale}",
            scenario_id,
            locale,
            f"Answer scenario {scenario_ordinal} in {locale}.",
        )
        for locale in ("en", "ru")
    ]
    for case in cases:
        case["hard_constraints"] = {"required_literals": ["Done."]}
    case_path.write_bytes(
        yaml.safe_dump(
            {"schema_version": "1", "kind": "response", "cases": cases},
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    manifest_payload = prepare_test_module._manifest_payload(
        provider_kind="fake",
        repetitions=1,
        arms=["baseline"],
    )
    provider_payload = manifest_payload["provider"]
    assert isinstance(provider_payload, dict)
    provider_payload["model"] = generation_model
    manifest = source / "manifest.yaml"
    manifest.write_bytes(
        yaml.safe_dump(manifest_payload, allow_unicode=True, sort_keys=False).encode("utf-8")
    )
    results_root.mkdir(parents=True)

    with monkeypatch.context() as capsule_patch:
        prepare_test_module._install_harness(capsule_patch, results_root)
        prepared = prepare_test_module.prepare_module.prepare_capsule(
            prepare_test_module._request(manifest, results_root)
        )
        capsule_patch.setattr(
            execution_module._fake_provider_module,
            "FakeProvider",
            execution_module._FAKE_PROVIDER_TYPE,
        )
        capsule_patch.setattr(
            execution_module._replay_provider_module,
            "ReplayProvider",
            execution_module._REPLAY_PROVIDER_TYPE,
        )
        capsule_patch.setattr(
            execution_module._openai_provider_module,
            "OpenAIProvider",
            execution_module._OPENAI_PROVIDER_TYPE,
        )
        _install_fast_runtime(capsule_patch)
        response = _benchmark_replay_outcome(returned_service_tier="default")
        response_payload = type(response).model_dump(response, mode="python", round_trip=True)
        response_payload["requested_model_id"] = generation_model
        response = type(response).model_validate(response_payload)
        provider = _BenchmarkScriptedProvider([response, response])
        outcome = execution_module._resume_capsule(
            prepared.path,
            provider_factory=ProviderFactory(),
            seams=_seams_for_provider(provider),
        )
        assert outcome.exit_code == 0, outcome
        assert outcome.result.state == "GENERATION_COMPLETE", outcome
        assert len(provider.benchmark_calls) == 2
        assert provider.legacy_calls == []
        assert finalize_capsule(prepared.path).state == "SEALED_COMPLETE"
        sidecar_path = results_root / "scored.json"
        write_scored_sidecar(prepared.path, sidecar_path)
        evidence = load_verified_scored_capsule(prepared.path, sidecar_path)

    assert evidence.capsule_sha256
    assert evidence.seal.generation_status == "complete"
    assert evidence.seal.structural_integrity == "valid"
    assert len(evidence.plan) == len(evidence.scored_attempts) == 2
    assert all(row.hard_pass for row in evidence.scored_attempts)
    return prepared.path, sidecar_path, evidence


def _verified_expectation_for_index(
    index: Any,
    root_index: Any,
) -> VerifiedGenerationContextExpectationV1:
    """Construct the Runtime-style verified expectation bound to one context index."""

    from laconian_eval.benchmark.context import (
        GenerationContextExpectationV1,
        VerifiedGenerationContextExpectationV1,
    )

    expectation_payload = generation_expectation_payload(
        campaign_id=index.campaign_id,
        generation_layer_root=root_index.layer_root_index_sha256,
        expected_context_index_sha256=index.generation_context_index_sha256,
    )
    expectation_payload.update(
        campaign_registry_sha256=index.campaign_registry_sha256,
        audit_reviewer_registry_sha256=index.audit_reviewer_registry_sha256,
        protocol_reviewer_registry_sha256=index.protocol_reviewer_registry_sha256,
        protocol_attestations_root=index.protocol_attestations_root,
        workflow_root=index.workflow_root,
    )
    expectation_payload["generation_context_expectation_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-expectation-v1",
        {
            key: value
            for key, value in expectation_payload.items()
            if key != "generation_context_expectation_sha256"
        },
    )
    return VerifiedGenerationContextExpectationV1(
        expectation=GenerationContextExpectationV1.model_validate(expectation_payload),
        bound_generation_complete_authority_root_sha256=sha256_marker(105_000),
    )


@dataclass(frozen=True, slots=True)
class CompleteGenerationContextFixture:
    """A complete on-disk generation root backed by 36 genuine scored capsules."""

    generation_root: Path
    generation_index_path: Path
    root_index: LayerRootIndexV1
    expectation: VerifiedGenerationContextExpectationV1
    selected_ordinal: int
    selected_evidence: VerifiedScoredCapsuleV2


def build_complete_generation_context_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    all_hard_fail: bool = False,
) -> CompleteGenerationContextFixture:
    """Build the real 3-model x 12-scenario generation loader boundary."""

    from laconian_eval.benchmark.context import (
        GenerationContextIndexV1,
        LayerRootIndexV1,
        write_generation_context_index,
        write_layer_root_index,
    )
    from laconian_eval.capsule.planning import scenario_uid
    from laconian_eval.capsule.sidecars import load_verified_scored_capsule

    generation_root = tmp_path / "GENERATION"
    layer_root = generation_root / "generation"
    layer_root.mkdir(parents=True)
    selected_build_root = tmp_path / "selected-build"
    selected_build_root.mkdir()
    with monkeypatch.context() as selected_patch:
        selected_capsule, selected_sidecar, selected_evidence = load_real_sealed_40_row_evidence(
            selected_build_root,
            selected_patch,
            all_hard_fail=all_hard_fail,
        )
    selected_destination = layer_root / "parent-selected"
    selected_capsule_destination = selected_destination / "capsule"
    selected_sidecar_destination = selected_destination / "scored.json"
    selected_destination.mkdir()
    shutil.copytree(selected_capsule, selected_capsule_destination)
    shutil.copy2(selected_sidecar, selected_sidecar_destination)
    selected_evidence = load_verified_scored_capsule(
        selected_capsule_destination,
        selected_sidecar_destination,
    )

    public_models = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
    expected_keys = {
        (model, scenario_uid("prepare-dataset", "fixture-v1", f"task3-{ordinal:03d}"))
        for model in public_models
        for ordinal in range(12)
    }
    selected_scenarios = {row.scenario_uid for row in selected_evidence.plan}
    assert selected_evidence.manifest.provider.model == "gpt-5.6-sol"
    assert selected_scenarios == {scenario_uid("prepare-dataset", "fixture-v1", "task3-000")}

    parents: list[tuple[Path, Path, VerifiedScoredCapsuleV2]] = [
        (selected_capsule_destination, selected_sidecar_destination, selected_evidence)
    ]
    candidate_ordinal = 0
    for model in public_models:
        for scenario_ordinal in range(12):
            if model == "gpt-5.6-sol" and scenario_ordinal == 0:
                continue
            build_root = tmp_path / f"minimal-build-{candidate_ordinal:02d}"
            results_root = layer_root / f"parent-{candidate_ordinal:02d}"
            build_root.mkdir()
            parents.append(
                _load_minimal_real_sealed_evidence(
                    build_root,
                    results_root,
                    monkeypatch,
                    generation_model=model,
                    scenario_ordinal=scenario_ordinal,
                )
            )
            candidate_ordinal += 1

    raw_members: list[dict[str, Any]] = []
    observed_keys: set[tuple[str, str]] = set()
    for capsule_path, sidecar_path, evidence in parents:
        scenarios = {row.scenario_uid for row in evidence.plan}
        assert len(scenarios) == 1
        scenario = next(iter(scenarios))
        key = (evidence.manifest.provider.model, scenario)
        assert key not in observed_keys
        observed_keys.add(key)
        raw_members.append(
            {
                "member_kind": "generation",
                "generation_model": key[0],
                "scenario_uid": key[1],
                "capsule_relative_path": capsule_path.relative_to(generation_root).as_posix(),
                "generation_capsule_sha256": evidence.capsule_sha256,
                "scored_sidecar_relative_path": sidecar_path.relative_to(
                    generation_root
                ).as_posix(),
                "scored_sidecar_sha256": hashlib.sha256(sidecar_path.read_bytes()).hexdigest(),
            }
        )
    assert observed_keys == expected_keys
    assert len({member["generation_capsule_sha256"] for member in raw_members}) == 36
    raw_members.sort(
        key=lambda member: (
            str(member["generation_model"]).encode("utf-8"),
            bytes.fromhex(str(member["scenario_uid"])),
        )
    )
    members = [dict(member, ordinal=ordinal) for ordinal, member in enumerate(raw_members)]
    root_payload: dict[str, Any] = {
        "schema_version": "benchmark-layer-root-index-v1",
        "layer_kind": "generation",
        "campaign_id": "public-foundations-v1",
        "members": members,
    }
    root_payload["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1", root_payload
    )
    root_index = LayerRootIndexV1.model_validate(root_payload)
    write_layer_root_index(generation_root, root_index)
    index = GenerationContextIndexV1.model_validate(generation_context_index_payload(root_index))
    generation_index_path = generation_root / "generation-context.json"
    write_generation_context_index(generation_index_path, index)
    expectation = _verified_expectation_for_index(index, root_index)
    selected_ordinal = next(
        member.ordinal
        for member in root_index.members
        if member.generation_capsule_sha256 == selected_evidence.capsule_sha256
    )
    assert selected_ordinal != 35
    return CompleteGenerationContextFixture(
        generation_root=generation_root,
        generation_index_path=generation_index_path,
        root_index=root_index,
        expectation=expectation,
        selected_ordinal=selected_ordinal,
        selected_evidence=selected_evidence,
    )


def generation_layer_index_for_evidence(
    evidence: VerifiedScoredCapsuleV2,
    *,
    sidecar_path: Path,
    campaign_id: str = "public-foundations-v1",
) -> tuple[Any, int]:
    """Bind one real scored parent and 35 nonselected synthetic identities."""

    from laconian_eval.benchmark.context import LayerRootIndexV1

    selected_scenarios = {row.scenario_uid for row in evidence.plan}
    assert len(selected_scenarios) == 1
    selected_scenario = next(iter(selected_scenarios))
    raw_members: list[dict[str, Any]] = [
        {
            "member_kind": "generation",
            "generation_model": evidence.manifest.provider.model,
            "scenario_uid": selected_scenario,
            "capsule_relative_path": "generation/real/capsule",
            "generation_capsule_sha256": evidence.capsule_sha256,
            "scored_sidecar_relative_path": "generation/real/scored.json",
            "scored_sidecar_sha256": hashlib.sha256(sidecar_path.read_bytes()).hexdigest(),
        }
    ]
    raw_members.extend(
        {
            "member_kind": "generation",
            "generation_model": f"zz-synthetic-model-{ordinal:02d}",
            "scenario_uid": sha256_marker(100_000 + ordinal),
            "capsule_relative_path": f"generation/synthetic-{ordinal:02d}/capsule",
            "generation_capsule_sha256": sha256_marker(101_000 + ordinal),
            "scored_sidecar_relative_path": f"generation/synthetic-{ordinal:02d}/scored.json",
            "scored_sidecar_sha256": sha256_marker(102_000 + ordinal),
        }
        for ordinal in range(35)
    )
    raw_members.sort(
        key=lambda member: (
            str(member["generation_model"]).encode("utf-8"),
            bytes.fromhex(str(member["scenario_uid"])),
        )
    )
    members = [dict(member, ordinal=ordinal) for ordinal, member in enumerate(raw_members)]
    payload: dict[str, Any] = {
        "schema_version": "benchmark-layer-root-index-v1",
        "layer_kind": "generation",
        "campaign_id": campaign_id,
        "members": members,
    }
    payload["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1", payload
    )
    root_index = LayerRootIndexV1.model_validate(payload)
    boundary_ordinal = next(
        member.ordinal
        for member in root_index.members
        if member.generation_capsule_sha256 == evidence.capsule_sha256
    )
    return root_index, boundary_ordinal


def _nonselected_verified_evidence_shell(member: Any) -> VerifiedScoredCapsuleV2:
    """Supply only nonselected identities; hard-score tests never consume these rows."""

    from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2

    shell = object.__new__(VerifiedScoredCapsuleV2)
    object.__setattr__(shell, "seal", None)
    object.__setattr__(shell, "capsule_sha256", member.generation_capsule_sha256)
    object.__setattr__(
        shell,
        "manifest",
        SimpleNamespace(provider=SimpleNamespace(model=member.generation_model)),
    )
    object.__setattr__(shell, "manifest_sha256", sha256_marker(103_000 + member.ordinal))
    object.__setattr__(shell, "plan_sha256", sha256_marker(104_000 + member.ordinal))
    object.__setattr__(shell, "plan", (SimpleNamespace(scenario_uid=member.scenario_uid),))
    object.__setattr__(shell, "scored_attempts", ())
    object.__setattr__(shell, "cases_by_uid", {})
    return shell


@dataclass(frozen=True, slots=True)
class SealedScoredScenario:
    """One real selected scored shard inside a fully bound 36-member context."""

    context: VerifiedGenerationContextIndexV1
    expectation: VerifiedGenerationContextExpectationV1
    boundary_ordinal: int
    evidence: VerifiedScoredCapsuleV2
    capsule_path: Path
    sidecar_path: Path


def sealed_scored_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    all_hard_fail: bool = False,
) -> SealedScoredScenario:
    """Build the Task 3 real sealed parent plus its Runtime-style context wrappers."""

    from laconian_eval.benchmark.context import load_verified_generation_context_index

    fixture = build_complete_generation_context_fixture(
        tmp_path,
        monkeypatch,
        all_hard_fail=all_hard_fail,
    )
    verified_context = load_verified_generation_context_index(
        generation_index_path=fixture.generation_index_path,
        generation_root=fixture.generation_root,
        expectation=fixture.expectation,
    )
    boundary_ordinal = fixture.selected_ordinal
    member = verified_context.root_index.members[boundary_ordinal]
    evidence = verified_context.generation_evidence[boundary_ordinal]
    return SealedScoredScenario(
        context=verified_context,
        expectation=fixture.expectation,
        boundary_ordinal=boundary_ordinal,
        evidence=evidence,
        capsule_path=fixture.generation_root / member.capsule_relative_path,
        sidecar_path=fixture.generation_root / member.scored_sidecar_relative_path,
    )


def hard_score_request_set_payload() -> dict[str, Any]:
    """Return one exact 40-row, self-hashed request-set payload."""

    bindings = protocol_bindings_payload()
    records = [hard_score_record_payload(ordinal) for ordinal in range(40)]
    payload: dict[str, Any] = {
        "schema_version": "1",
        "campaign_id": "campaign-2026-08-31",
        "generation_model": "gpt-5.6-sol",
        "scenario_uid": sha256_marker(70_000),
        "generation_capsule_sha256": sha256_marker(70_001),
        "manifest_sha256": sha256_marker(70_002),
        "plan_sha256": sha256_marker(70_003),
        "hard_scorer_source_sha256": bindings["hard_scorer_source_sha256"],
        "hard_score_protocol_sha256": bindings["hard_score_protocol_sha256"],
        "judge_protocol_sha256": bindings["judge_protocol_sha256"],
        "protocol_bindings": bindings,
        "records": records,
        "ordered_judge_request_ids": [row["judge_request_id"] for row in records],
    }
    payload["hard_score_request_set_sha256"] = stable_digest(
        "laconian-hard-score-request-set-v1", payload
    )
    return payload
