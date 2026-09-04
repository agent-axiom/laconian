"""Deterministic payload helpers shared by benchmark Task 3 tests."""

from __future__ import annotations

import base64
import hashlib
import shutil
from dataclasses import dataclass, replace
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


def audit_reviewer_ssh_key_material() -> tuple[bytes, bytes, str]:
    """Return one deterministic Ed25519 seed, OpenSSH wire key, and fingerprint."""

    seed = bytes.fromhex(
        "9d61b19deffd5a60ba844af492ec2cc4"
        "4449c5697b326919703bac031cae7f60"
    )
    public_key = bytes.fromhex(
        "d75a980182b10ab7d54bfed3c964073"
        "a0ee172f3daa62325af021a68f707511a"
    )
    algorithm = b"ssh-ed25519"
    wire_key = (
        len(algorithm).to_bytes(4, "big")
        + algorithm
        + len(public_key).to_bytes(4, "big")
        + public_key
    )
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(wire_key).digest()).decode(
        "ascii"
    ).rstrip("=")
    return seed, wire_key, fingerprint


def audit_reviewer_signing_key() -> Any:
    """Build the deterministic keyed audit-reviewer identity owned by protocol review."""

    from laconian_eval.benchmark.protocol_review import AuditReviewerSigningKeyV1

    _, wire_key, fingerprint = audit_reviewer_ssh_key_material()
    return AuditReviewerSigningKeyV1(
        schema_version="AuditReviewerSigningKeyV1",
        verification_mode="ssh_sha256",
        fingerprint=fingerprint,
        author_name_ascii="Audit Reviewer B",
        author_email_ascii="audit-reviewer-b@users.noreply.github.com",
        committer_name_ascii="Audit Reviewer B",
        committer_email_ascii="audit-reviewer-b@users.noreply.github.com",
        public_key_encoding="openssh-ed25519-wire-v1",
        public_key_base64=base64.b64encode(wire_key).decode("ascii"),
        public_key_sha256=hashlib.sha256(wire_key).hexdigest(),
    )


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

    signing_key = audit_reviewer_signing_key()
    reviewers = (
        ReviewerAccountBindingV1(
            reviewer_id="audit-a",
            reviewer_numeric_account_id=201,
            reviewer_login="audit-reviewer-a",
            verification_mode="github_verified_commit",
            signing_fingerprint=None,
            signing_key=None,
            role="audit_reviewer",
        ),
        ReviewerAccountBindingV1(
            reviewer_id="audit-b",
            reviewer_numeric_account_id=202,
            reviewer_login="audit-reviewer-b",
            verification_mode="ssh_sha256",
            signing_fingerprint=signing_key.fingerprint,
            signing_key=signing_key,
            role="audit_reviewer",
        ),
    )
    return AuditReviewerRegistryV1(
        schema_version="benchmark-reviewer-registry-v2",
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
            "algorithm_profile": ("ssh-ed25519-sshsig-git-sha512-or-openpgp-v4-ed25519-sha256-v1"),
            "dependency_lock_path": "uv.lock",
            "dependency_lock_sha256": dependency_lock_sha256,
            "verifier_dependency_inventory_root": sha256_marker(80_100),
            "entrypoint": ("laconian_eval.benchmark.protocol_review:_verify_keyed_signature_v1"),
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
        campaign_id="benchmark-0123456789abcdef0123456789abcdef",
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
        "campaign_id": "benchmark-0123456789abcdef0123456789abcdef",
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
    campaign_id: str = "benchmark-0123456789abcdef0123456789abcdef",
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


_PUBLIC_BENCHMARK_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")


def _public_price_snapshot_payload(model_ordinal: int) -> dict[str, Any]:
    """Return one native-v2 five-rate snapshot with independently bound sources."""

    from laconian_eval.capsule.canonical import canonical_json

    dimensions = (
        "ordinary_uncached_input_per_million",
        "cache_read_input_per_million",
        "cache_write_input_per_million",
        "visible_output_per_million",
        "reasoning_output_per_million",
    )
    rate_sets = (
        (1.25, 0.125, 1.5625, 10.0, 10.0),
        (0.75, 0.075, 0.9375, 6.0, 6.0),
        (0.25, 0.025, 0.3125, 2.0, 2.0),
    )
    rates = dict(zip(dimensions, rate_sets[model_ordinal], strict=True))
    source_url = f"https://prices.example.test/public-v1/model-{model_ordinal}"
    effective_date = "2026-08-31"
    source_evidence: list[dict[str, object]] = []
    for dimension in dimensions:
        evidence: dict[str, object] = {
            "dimension": dimension,
            "source_url": source_url,
            "effective_date": effective_date,
            "usd_per_million": rates[dimension],
        }
        evidence["source_sha256"] = hashlib.sha256(canonical_json(evidence)).hexdigest()
        source_evidence.append(evidence)
    return {
        "currency": "USD",
        "effective_date": effective_date,
        "source_url": source_url,
        "service_tier": "default",
        **rates,
        "source_evidence": source_evidence,
    }


def _response_smoke_output(case_id: str) -> str:
    """Return deterministic successful provider text satisfying every hard constraint."""

    if case_id.startswith("coding-post-retry-"):
        return "POST requests need idempotency protection."
    if case_id.startswith("preserve-config-"):
        return "Version v2.4.1 uses port 8080 at https://api.example.com/v1."
    if case_id.startswith("preserve-command-"):
        return "The command git push --force-with-lease can rewrite remote history."
    if case_id.startswith("coding-if-keyword-"):
        return "The should_retry value controls whether the call runs."
    if case_id.startswith("structured-json-"):
        return '{"risk":"duplicate","mitigation":"idempotency key","confidence":"high"}'
    if case_id.startswith("structured-yaml-"):
        return "status: unsafe\nreason: duplicate\nnext_step: idempotency key"
    if case_id.startswith("user-decline-"):
        return "I am sorry, but I cannot take the weekend shift. Please ask the on-call pool."
    return "Done."


@dataclass(frozen=True, slots=True)
class _PublicModelGeneration:
    manifest: Any
    manifest_sha256: str
    case_index: tuple[Any, ...]
    captured_arms: tuple[Any, ...]
    parent_plan: tuple[Any, ...]
    shards: tuple[Any, ...]
    candidates: tuple[tuple[Path, Path, Any], ...]


def _build_public_model_generation(
    build_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    generation_model: str,
    model_ordinal: int,
) -> _PublicModelGeneration:
    """Run all twelve genuine response-smoke shards for one public model."""

    import yaml

    import laconian_eval.capsule.execution as execution_module
    import laconian_eval.capsule.sidecars as sidecars_module
    from laconian_eval.capsule.canonical import canonical_jsonl
    from laconian_eval.capsule.execution import ProviderFactory
    from laconian_eval.capsule.finalize import finalize_capsule
    from laconian_eval.capsule.planning import materialize_case_index, materialize_parent_plan
    from laconian_eval.capsule.sharding import (
        materialize_shard_projection,
        project_shard_plans,
        shard_plan_file_bytes,
    )
    from laconian_eval.capsule.sidecars import (
        _VERIFIED_SCORED_CONSTRUCTION_AUTHORITY,
        ScoredCapsuleSidecarV2,
        VerifiedScoredCapsuleV2,
        write_scored_sidecar,
    )
    from laconian_eval.capsule.verify import VerifiedSealedCapsuleSourceV1
    from tests.capsule import test_prepare as prepare_test_module
    from tests.capsule.test_execution import (
        _benchmark_replay_response_with_output,
        _BenchmarkScriptedProvider,
        _install_fast_runtime,
        _seams_for_provider,
    )

    repository_root = Path(__file__).parents[2]
    source = build_root / "source"
    case_path = source / "cases/response-smoke.yaml"
    case_path.parent.mkdir(parents=True)
    shutil.copy2(repository_root / "evals/cases/response-smoke.yaml", case_path)
    manifest_payload = prepare_test_module._manifest_payload(
        provider_kind="openai",
        api_key_env="LIVE_TEST_API_KEY",
        case_files=["cases/response-smoke.yaml"],
        arms=["baseline", "concise", "caveman", "if"],
        repetitions=5,
    )
    provider_payload = manifest_payload["provider"]
    generation_payload = manifest_payload["generation"]
    assert isinstance(provider_payload, dict)
    assert isinstance(generation_payload, dict)
    provider_payload["model"] = generation_model
    generation_payload.update(
        {
            "max_output_tokens": 1024,
            "temperature": None,
            "reasoning_effort": "medium",
            "text_verbosity": "medium",
            "reasoning_mode": "omitted",
            "prompt_cache_mode": "explicit",
            "prompt_cache_ttl": "30m",
            "service_tier": "default",
        }
    )
    manifest_payload["price_snapshot"] = _public_price_snapshot_payload(model_ordinal)
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
    case_index = tuple(materialize_case_index(captured, captured.resolved_manifest))
    parent_plan = tuple(
        materialize_parent_plan(
            parent_manifest_sha256=captured.manifest_sha256,
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        )
    )
    shards = project_shard_plans(
        campaign_id="benchmark-0123456789abcdef0123456789abcdef",
        resolved_manifest=captured.resolved_manifest,
        parent_manifest_sha256=captured.manifest_sha256,
        parent_plan=parent_plan,
        case_index=case_index,
        captured_arms=captured.arms,
    )
    assert len(case_index) == 24
    assert len(parent_plan) == 480
    assert len(shards) == 12

    planning = build_root / "planning"
    planning.mkdir()
    (planning / "parent-plan.jsonl").write_bytes(
        canonical_jsonl(row.model_dump(mode="json") for row in parent_plan)
    )
    candidates: list[tuple[Path, Path, Any]] = []
    response_cache: dict[tuple[str, str], Any] = {}

    def capture_sidecar_builder(
        original: Any,
        captured: list[tuple[VerifiedSealedCapsuleSourceV1, ScoredCapsuleSidecarV2]],
    ) -> Any:
        def capture(
            retained_source: VerifiedSealedCapsuleSourceV1,
        ) -> ScoredCapsuleSidecarV2:
            sidecar = original(retained_source)
            captured.append((retained_source, sidecar))
            return sidecar

        return capture

    for shard_ordinal, shard in enumerate(shards):
        results_root = build_root / f"results-{shard_ordinal:02d}"
        results_root.mkdir()
        (planning / "shard-plan.json").write_bytes(shard_plan_file_bytes(shard))
        with monkeypatch.context() as shard_patch:
            prepare_test_module._install_harness(shard_patch, results_root)
            request_type = prepare_test_module.prepare_module.PrepareShardRequest
            prepared = prepare_test_module.prepare_module.prepare_shard_capsule(
                request_type(
                    prepare=prepare_test_module._request(
                        manifest,
                        results_root,
                        invocation_cwd=build_root,
                        source_root=repository_root,
                    ),
                    parent_plan_path=Path("planning/parent-plan.jsonl"),
                    shard_plan_path=Path("planning/shard-plan.json"),
                )
            )
            shard_patch.setattr(
                execution_module._fake_provider_module,
                "FakeProvider",
                execution_module._FAKE_PROVIDER_TYPE,
            )
            shard_patch.setattr(
                execution_module._replay_provider_module,
                "ReplayProvider",
                execution_module._REPLAY_PROVIDER_TYPE,
            )
            shard_patch.setattr(
                execution_module._openai_provider_module,
                "OpenAIProvider",
                execution_module._OPENAI_PROVIDER_TYPE,
            )
            _install_fast_runtime(shard_patch)

            def skip_intermediate_revalidation(_session: object) -> None:
                """The completed fixture is fully verified after finalization."""

            shard_patch.setattr(
                execution_module,
                "_revalidate_mutator_session_v1",
                skip_intermediate_revalidation,
            )
            selected_plan = materialize_shard_projection(shard, parent_plan)
            outcomes: list[Any] = []
            for row in selected_plan:
                output = _response_smoke_output(row.case_id)
                cache_key = (generation_model, output)
                response = response_cache.get(cache_key)
                if response is None:
                    template = _benchmark_replay_response_with_output(output)
                    response_payload = type(template).model_dump(
                        template,
                        mode="python",
                        round_trip=True,
                    )
                    response_payload["requested_model_id"] = generation_model
                    response = type(template).model_validate(response_payload)
                    response_cache[cache_key] = response
                outcomes.append(response)
            provider = _BenchmarkScriptedProvider(outcomes)
            # This fixture validates durable bytes and owner replay after construction; it
            # does not exercise journal durability. Avoid thousands of physical flushes while
            # materializing the 36 otherwise-real capsules, then restore real fsync before any
            # Task 8 writer or loader runs.
            with shard_patch.context() as fsync_patch:
                fsync_patch.setattr(execution_module.os, "fsync", lambda _fd: None)
                outcome = execution_module._resume_capsule(
                    prepared.path,
                    provider_factory=ProviderFactory(),
                    seams=_seams_for_provider(provider),
                )
            assert outcome.exit_code == 0, outcome
            assert outcome.result.state == "GENERATION_COMPLETE", outcome
            assert len(provider.benchmark_calls) == 40
            assert finalize_capsule(prepared.path).state == "SEALED_COMPLETE"
            sidecar_path = results_root / "scored.json"
            captured_sidecars: list[
                tuple[VerifiedSealedCapsuleSourceV1, ScoredCapsuleSidecarV2]
            ] = []
            original_sidecar_from_source = sidecars_module._sidecar_from_source
            capture_verified_source = capture_sidecar_builder(
                original_sidecar_from_source,
                captured_sidecars,
            )

            with shard_patch.context() as sidecar_patch:
                sidecar_patch.setattr(
                    sidecars_module,
                    "_sidecar_from_source",
                    capture_verified_source,
                )
                written_sidecar_sha256 = write_scored_sidecar(prepared.path, sidecar_path)
            assert len(captured_sidecars) == 1
            retained_source, sidecar = captured_sidecars[0]
            assert type(retained_source) is VerifiedSealedCapsuleSourceV1
            assert type(sidecar) is ScoredCapsuleSidecarV2
            assert written_sidecar_sha256 == sidecar.sidecar_sha256
            assert sidecar_path.read_bytes() == sidecars_module._sidecar_bytes(sidecar)
            evidence = VerifiedScoredCapsuleV2(
                seal=retained_source.seal,
                capsule_sha256=sidecar.capsule_sha256,
                manifest=retained_source.manifest,
                manifest_sha256=sidecar.manifest_sha256,
                plan_sha256=sidecar.plan_sha256,
                plan=retained_source.plan,
                scored_attempts=sidecar.scored_attempts,
                cases_by_uid=retained_source.cases_by_uid,
                _construction_authority=_VERIFIED_SCORED_CONSTRUCTION_AUTHORITY,
            )
        assert evidence.manifest.source_manifest_schema_version == "2"
        assert evidence.manifest.price_snapshot is not None
        assert len(evidence.plan) == len(evidence.scored_attempts) == 40
        assert all(row.hard_pass for row in evidence.scored_attempts)
        assert {row.scenario_uid for row in evidence.plan} == {shard.scenario_uid}
        candidates.append((prepared.path, sidecar_path, evidence))
    return _PublicModelGeneration(
        manifest=captured.resolved_manifest,
        manifest_sha256=captured.manifest_sha256,
        case_index=case_index,
        captured_arms=tuple(captured.arms),
        parent_plan=parent_plan,
        shards=shards,
        candidates=tuple(candidates),
    )


def _build_complete_public_generation_context(
    workspace_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Any, Any]:
    """Build and reload the canonical 36-member priced generation context."""

    from laconian_eval.benchmark.context import (
        GenerationContextIndexV1,
        LayerRootIndexV1,
        VerifiedGenerationContextIndexV1,
        write_generation_context_index,
        write_layer_root_index,
    )
    from laconian_eval.capsule.sharding import validate_public_generation_partition

    generation_root = workspace_root / "GENERATION"
    layer_directory = generation_root / "generation"
    layer_directory.mkdir(parents=True)
    model_builds: list[_PublicModelGeneration] = []
    raw_candidates: list[tuple[Path, Path, Any]] = []
    for model_ordinal, model in enumerate(_PUBLIC_BENCHMARK_MODELS):
        build = _build_public_model_generation(
            workspace_root / f"build-{model_ordinal}",
            monkeypatch,
            generation_model=model,
            model_ordinal=model_ordinal,
        )
        model_builds.append(build)
        raw_candidates.extend(build.candidates)
    validate_public_generation_partition(
        campaign_id="benchmark-0123456789abcdef0123456789abcdef",
        resolved_manifests=tuple(item.manifest for item in model_builds),
        parent_manifest_sha256s=tuple(item.manifest_sha256 for item in model_builds),
        case_indexes=tuple(item.case_index for item in model_builds),
        captured_arms_by_parent=tuple(item.captured_arms for item in model_builds),
        parent_plans=tuple(item.parent_plan for item in model_builds),
        shard_plans=tuple(shard for item in model_builds for shard in item.shards),
    )
    raw_candidates.sort(
        key=lambda item: (
            item[2].manifest.provider.model.encode("utf-8"),
            bytes.fromhex(item[2].plan[0].scenario_uid),
        )
    )
    members: list[dict[str, object]] = []
    generation_evidence: list[Any] = []
    for ordinal, (capsule_path, sidecar_path, evidence) in enumerate(raw_candidates):
        member_directory = layer_directory / f"{ordinal:03d}"
        member_directory.mkdir()
        capsule_destination = member_directory / "capsule"
        sidecar_destination = member_directory / "scored.json"
        shutil.copytree(capsule_path, capsule_destination)
        shutil.copy2(sidecar_path, sidecar_destination)
        generation_evidence.append(evidence)
        members.append(
            {
                "member_kind": "generation",
                "ordinal": ordinal,
                "generation_model": evidence.manifest.provider.model,
                "scenario_uid": evidence.plan[0].scenario_uid,
                "capsule_relative_path": capsule_destination.relative_to(
                    generation_root
                ).as_posix(),
                "generation_capsule_sha256": evidence.capsule_sha256,
                "scored_sidecar_relative_path": sidecar_destination.relative_to(
                    generation_root
                ).as_posix(),
                "scored_sidecar_sha256": hashlib.sha256(
                    sidecar_destination.read_bytes()
                ).hexdigest(),
            }
        )
    for model_ordinal in range(len(_PUBLIC_BENCHMARK_MODELS)):
        shutil.rmtree(workspace_root / f"build-{model_ordinal}")
    root_payload: dict[str, object] = {
        "schema_version": "benchmark-layer-root-index-v1",
        "layer_kind": "generation",
        "campaign_id": "benchmark-0123456789abcdef0123456789abcdef",
        "members": members,
    }
    root_payload["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1",
        root_payload,
    )
    root_index = LayerRootIndexV1.model_validate(root_payload)
    write_layer_root_index(generation_root, root_index)
    context_index = GenerationContextIndexV1.model_validate(
        generation_context_index_payload(root_index)
    )
    generation_index_path = generation_root / "generation-context.json"
    write_generation_context_index(generation_index_path, context_index)
    expectation = _verified_expectation_for_index(context_index, root_index)
    context = VerifiedGenerationContextIndexV1(
        expectation=expectation,
        index=context_index,
        root_index=root_index,
        generation_evidence=tuple(generation_evidence),
    )
    assert len(context.generation_evidence) == 36
    assert all(
        len(item.plan) == len(item.scored_attempts) == 40 for item in context.generation_evidence
    )
    return generation_root, generation_index_path, expectation, context


def _build_hard_score_request_sets_fast(context: Any) -> tuple[Any, ...]:
    """Project verified scored capsules without repeatedly copying the full context."""

    from laconian_eval.benchmark.context import protocol_bindings_from_context
    from laconian_eval.benchmark.hard_score import (
        HardScoreRequestSetV1,
        _record_from_scored,
    )

    index = context.index
    protocol_bindings = protocol_bindings_from_context(index)
    request_sets: list[Any] = []
    for member, evidence in zip(
        context.root_index.members,
        context.generation_evidence,
        strict=True,
    ):
        assert len(evidence.plan) == len(evidence.scored_attempts) == 40
        records = tuple(
            _record_from_scored(
                campaign_id=index.campaign_id,
                generation_capsule_sha256=member.generation_capsule_sha256,
                judge_protocol_sha256=index.judge_protocol_sha256,
                plan=plan,
                scored=scored,
            )
            for plan, scored in zip(
                evidence.plan,
                evidence.scored_attempts,
                strict=True,
            )
        )
        payload: dict[str, object] = {
            "schema_version": "1",
            "campaign_id": index.campaign_id,
            "generation_model": member.generation_model,
            "scenario_uid": member.scenario_uid,
            "generation_capsule_sha256": member.generation_capsule_sha256,
            "manifest_sha256": evidence.manifest_sha256,
            "plan_sha256": evidence.plan_sha256,
            "hard_scorer_source_sha256": index.hard_scorer_source_sha256,
            "hard_score_protocol_sha256": index.hard_score_protocol_sha256,
            "judge_protocol_sha256": index.judge_protocol_sha256,
            "protocol_bindings": protocol_bindings.model_dump(mode="json"),
            "records": [row.model_dump(mode="json") for row in records],
            "ordered_judge_request_ids": [row.judge_request_id for row in records if row.hard_pass],
        }
        payload["hard_score_request_set_sha256"] = stable_digest(
            "laconian-hard-score-request-set-v1",
            payload,
        )
        request_sets.append(HardScoreRequestSetV1.model_validate(payload))
    return tuple(request_sets)


def _build_judge_request_attachments_fast(
    *,
    context: Any,
    hard_score_sets: tuple[Any, ...],
    identity_registry_bundle: Any,
) -> tuple[Any, ...]:
    """Project blind requests once from already verified generation parents."""

    from laconian_eval.benchmark.attachments import canonical_json_v1
    from laconian_eval.benchmark.context import protocol_bindings_from_context
    from laconian_eval.benchmark.judge import (
        JudgeProviderRequestV1,
        JudgeRequestAttachmentV1,
        _check_identity_bundle,
        _derive_blind_requests,
        _lf_digest,
        _wire_mapping,
    )

    index = context.index
    bundle = _check_identity_bundle(index, identity_registry_bundle)
    protocol_bindings = protocol_bindings_from_context(index)
    attachments: list[Any] = []
    for member, evidence, request_set in zip(
        context.root_index.members,
        context.generation_evidence,
        hard_score_sets,
        strict=True,
    ):
        blind_requests = _derive_blind_requests(
            index=index,
            evidence=evidence,
            request_set=request_set,
        )
        requests = tuple(
            JudgeProviderRequestV1(
                blind_request=blind,
                requested_service_tier="default",
                service_tier_wire_field="service_tier",
                prompt_cache_mode="explicit",
                prompt_cache_ttl="30m",
                openai_sdk_version="3.3.1",
                uv_lock_member_sha256=bundle.dependency_lock_sha256,
                provider_wire_request_sha256=_lf_digest(
                    "laconian-judge-provider-wire-request-v1",
                    canonical_json_v1(_wire_mapping(blind)),
                ),
            )
            for blind in blind_requests
        )
        payload: dict[str, object] = {
            "schema_version": "judge-request-attachment-v1",
            "campaign_id": index.campaign_id,
            "generation_model": member.generation_model,
            "scenario_uid": member.scenario_uid,
            "generation_capsule_sha256": member.generation_capsule_sha256,
            "hard_score_request_set_sha256": (request_set.hard_score_request_set_sha256),
            "judge_protocol_sha256": index.judge_protocol_sha256,
            "protocol_bindings": protocol_bindings.model_dump(mode="json"),
            "campaign_seed_sha256": index.campaign_seed_sha256,
            "requested_service_tier": "default",
            "service_tier_wire_field": "service_tier",
            "prompt_cache_mode": "explicit",
            "prompt_cache_ttl": "30m",
            "requests": tuple(
                row.model_dump(mode="python", round_trip=True, warnings=False) for row in requests
            ),
        }
        payload["judge_request_attachment_sha256"] = stable_digest(
            "laconian-judge-request-attachment-v1",
            payload,
        )
        attachments.append(JudgeRequestAttachmentV1.model_validate(payload))
    return tuple(attachments)


def _write_attachment_layer(
    root: Path,
    *,
    kind: str,
    context: Any,
    attachments: tuple[Any, ...],
    digest_field: str,
) -> Any:
    """Write one complete canonical 36-member attachment layer and its index."""

    from laconian_eval.benchmark.attachments import canonical_json_v1
    from laconian_eval.benchmark.context import LayerRootIndexV1, write_layer_root_index

    directories = {
        "hard-score": "hard-score",
        "judge-request": "judge-requests",
        "judge": "judge",
    }
    directory = root / directories[kind]
    directory.mkdir(parents=True)
    members: list[dict[str, object]] = []
    for ordinal, (generation_member, attachment) in enumerate(
        zip(context.root_index.members, attachments, strict=True)
    ):
        path = directory / f"{ordinal:03d}.json"
        path.write_bytes(canonical_json_v1(attachment.model_dump(mode="json")) + b"\n")
        members.append(
            {
                "member_kind": kind,
                "ordinal": ordinal,
                "generation_model": generation_member.generation_model,
                "scenario_uid": generation_member.scenario_uid,
                "relative_path": path.relative_to(root).as_posix(),
                "attachment_sha256": getattr(attachment, digest_field),
            }
        )
    payload: dict[str, object] = {
        "schema_version": "benchmark-layer-root-index-v1",
        "layer_kind": kind,
        "campaign_id": context.index.campaign_id,
        "members": members,
    }
    payload["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1",
        payload,
    )
    index = LayerRootIndexV1.model_validate(payload)
    write_layer_root_index(root, index)
    return index


def _judge_marker_v1(label: str, boundary_ordinal: int, position: int) -> str:
    return hashlib.sha256(
        f"provider-fixture\0{label}\0{boundary_ordinal}\0{position}".encode()
    ).hexdigest()


def _successful_judge_attempt(
    *,
    context: Any,
    boundary_ordinal: int,
    request_set: Any,
    request_attachment: Any,
    position: int,
) -> Any:
    """Build one terminal success with a deterministic, varied semantic judgment."""

    from laconian_eval.benchmark.attachments import canonical_json_v1
    from laconian_eval.benchmark.judge import (
        JudgeAttemptEvidenceV1,
        RubricItemJudgmentV1,
        StructuredJudgmentV1,
        WarningJudgmentV1,
    )

    wrapper = request_attachment.requests[position]
    blind = wrapper.blind_request
    plan = context.generation_evidence[boundary_ordinal].plan[position]
    certainty = plan.case_id in {"safety-medical-en", "safety-medical-ru"} and plan.arm in {
        "if",
        "concise",
    }
    semantic_pass = certainty or not blind.rubric or (boundary_ordinal + position) % 4 != 0
    rubric_items = tuple(
        RubricItemJudgmentV1(
            item_index=item.item_index,
            passed=semantic_pass if item.item_index == 0 else True,
            evidence="deterministic fixture review",
        )
        for item in blind.rubric
    )
    warning = (
        None
        if blind.material_warning_requirement is None
        else WarningJudgmentV1(passed=True, evidence="warning requirement satisfied")
    )
    judgment = StructuredJudgmentV1(
        judge_request_id=blind.judge_request_id,
        blind_id=blind.blind_id,
        rubric_items=rubric_items,
        material_warning=warning,
        material_contradiction=False,
        contradiction_evidence=None,
        semantic_pass=semantic_pass,
    )

    def marker(label: str) -> str:
        return _judge_marker_v1(label, boundary_ordinal, position)

    payload: dict[str, object] = {
        "schema_version": "judge-attempt-evidence-v1",
        "campaign_id": context.index.campaign_id,
        "boundary_ordinal": boundary_ordinal,
        "generation_model": context.root_index.members[boundary_ordinal].generation_model,
        "scenario_uid": context.root_index.members[boundary_ordinal].scenario_uid,
        "generation_capsule_sha256": context.root_index.members[
            boundary_ordinal
        ].generation_capsule_sha256,
        "hard_score_request_set_sha256": request_set.hard_score_request_set_sha256,
        "judge_request_attachment_sha256": (request_attachment.judge_request_attachment_sha256),
        "judge_protocol_sha256": context.index.judge_protocol_sha256,
        "protocol_bindings": request_attachment.protocol_bindings.model_dump(mode="json"),
        "judge_request_id": blind.judge_request_id,
        "blind_id": blind.blind_id,
        "blind_request_sha256": hashlib.sha256(
            canonical_json_v1(blind.model_dump(mode="json"))
        ).hexdigest(),
        "attempt_number": 1,
        "retry_of_judge_attempt_sha256": None,
        "retry_authorization_sha256": None,
        "structured_retry_status": None,
        "batch_plan_sha256": marker("batch"),
        "consumed_batch_receipt_sha256": marker("receipt"),
        "reservation_sha256": marker("reservation"),
        "retry_evidence_sha256": None,
        "spend_event_sha256": marker("spend"),
        "delivery_evidence_sha256": marker("delivery"),
        "delivery_certainty": "response_received",
        "terminal": True,
        "disposition": "success",
        "requested_service_tier": "default",
        "service_tier_wire_field": "service_tier",
        "applied_prompt_cache_mode": "explicit",
        "applied_prompt_cache_ttl": "30m",
        "applied_cache_control_status": "reported_exact",
        "provider_wire_request_sha256": wrapper.provider_wire_request_sha256,
        "service_tier_status": "reported_default",
        "returned_service_tier": "default",
        "cost_availability": "trusted_usage",
        "provider_request_id": f"judge-fixture-{boundary_ordinal:02d}-{position:02d}",
        "requested_judge_model_id": "gpt-5.6-sol",
        "returned_judge_model_id": "gpt-5.6-sol-2026-08-01",
        "applied_cache_control_source_sha256": marker("applied"),
        "cache_read_source_sha256": marker("cache-read"),
        "cache_write_source_sha256": marker("cache-write"),
        "service_tier_source_sha256": marker("tier"),
        "usage_source_sha256": marker("usage"),
        "reasoning_tokens_source_sha256": marker("reasoning"),
        "returned_judge_model_source_sha256": marker("returned-model"),
        "raw_response_sha256": marker("response"),
        "usage": {
            "input_tokens": 20,
            "output_tokens": 8,
            "total_tokens": 28,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "ordinary_uncached_input_tokens": 20,
            "reasoning_tokens": 2,
            "availability": "complete",
            "cache_read_status": "reported_zero",
            "cache_write_status": "reported_zero",
            "reasoning_accounting": "reported",
        },
        "judgment": judgment.model_dump(
            mode="python",
            round_trip=True,
            warnings=False,
        ),
        "terminal_evidence_sha256": marker("terminal"),
    }
    payload["judge_attempt_id"] = stable_digest(
        "laconian-judge-attempt-id-v1",
        {
            "judge_request_id": payload["judge_request_id"],
            "attempt_number": 1,
            "batch_plan_sha256": payload["batch_plan_sha256"],
            "consumed_batch_receipt_sha256": payload["consumed_batch_receipt_sha256"],
        },
    )
    payload["judge_attempt_evidence_sha256"] = stable_digest(
        "laconian-judge-attempt-evidence-v1",
        payload,
    )
    return JudgeAttemptEvidenceV1.model_validate_json(canonical_json_v1(payload))


def _build_judge_attempt_root(
    workspace_root: Path,
    *,
    context: Any,
    request_root_index: Any,
    hard_score_sets: tuple[Any, ...],
    request_attachments: tuple[Any, ...],
) -> tuple[Path, Any, tuple[Any, ...]]:
    """Create all 1,440 successful attempts and seal their durable root."""

    from laconian_eval.benchmark.judge import (
        JudgeAttemptBoundaryV1,
        JudgeAttemptRootIndexV1,
        JudgeAttemptRootMemberV1,
        write_judge_attempt_root,
    )

    boundaries: list[Any] = []
    root_members: list[Any] = []
    for ordinal, (member, request_set, attachment) in enumerate(
        zip(
            context.root_index.members,
            hard_score_sets,
            request_attachments,
            strict=True,
        )
    ):
        attempts = tuple(
            _successful_judge_attempt(
                context=context,
                boundary_ordinal=ordinal,
                request_set=request_set,
                request_attachment=attachment,
                position=position,
            )
            for position in range(40)
        )
        boundary_payload: dict[str, object] = {
            "schema_version": "judge-attempt-boundary-v1",
            "boundary_ordinal": ordinal,
            "campaign_id": context.index.campaign_id,
            "generation_model": member.generation_model,
            "scenario_uid": member.scenario_uid,
            "generation_capsule_sha256": member.generation_capsule_sha256,
            "hard_score_request_set_sha256": request_set.hard_score_request_set_sha256,
            "judge_request_attachment_sha256": attachment.judge_request_attachment_sha256,
            "judge_protocol_sha256": context.index.judge_protocol_sha256,
            "ordered_judge_request_ids": request_set.ordered_judge_request_ids,
            "attempts": tuple(
                row.model_dump(mode="python", round_trip=True, warnings=False) for row in attempts
            ),
        }
        boundary_payload["judge_attempt_boundary_sha256"] = stable_digest(
            "laconian-judge-attempt-boundary-v1",
            boundary_payload,
        )
        boundary = JudgeAttemptBoundaryV1.model_validate(boundary_payload)
        boundaries.append(boundary)
        root_members.append(
            JudgeAttemptRootMemberV1(
                ordinal=ordinal,
                generation_model=member.generation_model,
                scenario_uid=member.scenario_uid,
                relative_path=f"judge-attempts/{ordinal:03d}.json",
                judge_request_attachment_sha256=(attachment.judge_request_attachment_sha256),
                judge_attempt_boundary_sha256=boundary.judge_attempt_boundary_sha256,
                request_count=40,
                attempt_count=40,
            )
        )
    root_payload: dict[str, object] = {
        "schema_version": "judge-attempt-root-index-v1",
        "campaign_id": context.index.campaign_id,
        "judge_request_root_index_sha256": request_root_index.layer_root_index_sha256,
        "members": tuple(row.model_dump(mode="json") for row in root_members),
    }
    root_payload["judge_attempt_root_index_sha256"] = stable_digest(
        "laconian-judge-attempt-root-index-v1",
        root_payload,
    )
    root_index = JudgeAttemptRootIndexV1.model_validate(root_payload)
    checked_boundaries = tuple(boundaries)
    attempt_root = workspace_root / "ATTEMPTS"
    attempt_root.mkdir()
    write_judge_attempt_root(
        attempt_root,
        index=root_index,
        boundaries=checked_boundaries,
    )
    return attempt_root, root_index, checked_boundaries


def _build_judge_attachments_fast(
    *,
    context: Any,
    hard_score_sets: tuple[Any, ...],
    request_attachments: tuple[Any, ...],
    attempt_root_index: Any,
    attempt_boundaries: tuple[Any, ...],
) -> tuple[Any, ...]:
    """Project terminal successes without copying the 1,440-attempt owner 36 times."""

    from laconian_eval.benchmark.context import protocol_bindings_from_context
    from laconian_eval.benchmark.judge import (
        JudgeAttachmentV1,
        JudgeRecordV1,
        _validate_boundary_request_binding,
    )

    index = context.index
    protocol_bindings = protocol_bindings_from_context(index)
    attachments: list[Any] = []
    for ordinal, (member, request_set, request_attachment, boundary) in enumerate(
        zip(
            context.root_index.members,
            hard_score_sets,
            request_attachments,
            attempt_boundaries,
            strict=True,
        )
    ):
        _validate_boundary_request_binding(
            index=attempt_root_index,
            member=attempt_root_index.members[ordinal],
            boundary=boundary,
            attachment=request_attachment,
        )
        records: list[Any] = []
        for wrapper, terminal in zip(
            request_attachment.requests,
            boundary.attempts,
            strict=True,
        ):
            blind = wrapper.blind_request
            assert terminal.judge_request_id == blind.judge_request_id
            assert terminal.provider_wire_request_sha256 == wrapper.provider_wire_request_sha256
            assert terminal.disposition == "success"
            assert terminal.judgment is not None
            assert terminal.returned_judge_model_id is not None
            records.append(
                JudgeRecordV1(
                    judge_request_id=blind.judge_request_id,
                    blind_id=terminal.blind_id,
                    raw_judge_attempt_sha256=(terminal.judge_attempt_evidence_sha256),
                    returned_judge_model_id=terminal.returned_judge_model_id,
                    requested_service_tier="default",
                    service_tier_status="reported_default",
                    returned_service_tier="default",
                    judgment=terminal.judgment,
                )
            )
        assert tuple(row.judge_request_id for row in records) == (
            request_set.ordered_judge_request_ids
        )
        payload: dict[str, object] = {
            "schema_version": "judge-attachment-v1",
            "campaign_id": index.campaign_id,
            "generation_model": member.generation_model,
            "scenario_uid": member.scenario_uid,
            "generation_capsule_sha256": member.generation_capsule_sha256,
            "hard_score_request_set_sha256": (request_set.hard_score_request_set_sha256),
            "judge_request_attachment_sha256": (request_attachment.judge_request_attachment_sha256),
            "judge_protocol_sha256": index.judge_protocol_sha256,
            "protocol_bindings": protocol_bindings.model_dump(mode="json"),
            "requested_judge_model_id": "gpt-5.6-sol",
            "requested_service_tier": "default",
            "service_tier_wire_field": "service_tier",
            "records": tuple(
                row.model_dump(mode="python", round_trip=True, warnings=False) for row in records
            ),
        }
        payload["judge_attachment_sha256"] = stable_digest(
            "laconian-judge-attachment-v1",
            payload,
        )
        attachments.append(JudgeAttachmentV1.model_validate(payload))
    return tuple(attachments)


def _cache_evidence_payload_from_generation(raw: Any) -> dict[str, object]:
    usage = raw.usage
    visible_output = (
        None
        if usage.output_tokens is None or usage.reasoning_tokens is None
        else usage.output_tokens - usage.reasoning_tokens
    )
    return {
        "attempt_id": raw.attempt_id,
        "applied_prompt_cache_mode": raw.applied_prompt_cache_mode,
        "applied_prompt_cache_ttl": raw.applied_prompt_cache_ttl,
        "applied_cache_control_status": raw.applied_cache_control_status,
        "ordinary_uncached_input_tokens": usage.ordinary_uncached_input_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_read_status": usage.cache_read_status,
        "cache_write_tokens": usage.cache_write_tokens,
        "cache_write_status": usage.cache_write_status,
        "visible_output_tokens": visible_output,
        "reasoning_tokens": usage.reasoning_tokens,
        "requested_service_tier": raw.requested_service_tier,
        "returned_service_tier": raw.returned_service_tier,
        "service_tier_status": raw.service_tier_status,
        "applied_cache_control_source_sha256": raw.applied_cache_control_source_sha256,
        "cache_read_source_sha256": raw.cache_read_source_sha256,
        "cache_write_source_sha256": raw.cache_write_source_sha256,
        "service_tier_source_sha256": raw.service_tier_source_sha256,
        "usage_source_sha256": raw.usage_source_sha256,
        "reasoning_tokens_source_sha256": raw.reasoning_tokens_source_sha256,
    }


def _cache_evidence_payload_from_judge(attempt: Any) -> dict[str, object]:
    usage = attempt.usage
    visible_output = (
        None
        if usage.output_tokens is None or usage.reasoning_tokens is None
        else usage.output_tokens - usage.reasoning_tokens
    )
    return {
        "attempt_id": attempt.judge_attempt_id,
        "applied_prompt_cache_mode": attempt.applied_prompt_cache_mode,
        "applied_prompt_cache_ttl": attempt.applied_prompt_cache_ttl,
        "applied_cache_control_status": attempt.applied_cache_control_status,
        "ordinary_uncached_input_tokens": usage.ordinary_uncached_input_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_read_status": usage.cache_read_status,
        "cache_write_tokens": usage.cache_write_tokens,
        "cache_write_status": usage.cache_write_status,
        "visible_output_tokens": visible_output,
        "reasoning_tokens": usage.reasoning_tokens,
        "requested_service_tier": attempt.requested_service_tier,
        "returned_service_tier": attempt.returned_service_tier,
        "service_tier_status": attempt.service_tier_status,
        "applied_cache_control_source_sha256": attempt.applied_cache_control_source_sha256,
        "cache_read_source_sha256": attempt.cache_read_source_sha256,
        "cache_write_source_sha256": attempt.cache_write_source_sha256,
        "service_tier_source_sha256": attempt.service_tier_source_sha256,
        "usage_source_sha256": attempt.usage_source_sha256,
        "reasoning_tokens_source_sha256": attempt.reasoning_tokens_source_sha256,
    }


def _build_provider_index(
    *,
    context: Any,
    expectation: Any,
    hard_score_root_index: Any,
    hard_score_sets: tuple[Any, ...],
    judge_request_root_index: Any,
    judge_request_attachments: tuple[Any, ...],
    judge_attempt_root_index: Any,
    judge_attempt_boundaries: tuple[Any, ...],
    judge_root_index: Any,
    judge_attachments: tuple[Any, ...],
) -> Any:
    """Construct the strict provider index from all independently sealed sources."""

    from laconian_eval.benchmark.provider_evidence import (
        ProviderEvidenceIndexV1,
        PublicBenchmarkCacheEvidenceV1,
        RequestedReturnedModelEvidenceV1,
        compute_requested_returned_model_source_sha256,
    )

    generation_sources: dict[str, list[str]] = {model: [] for model in _PUBLIC_BENCHMARK_MODELS}
    generation_returned: dict[str, set[str]] = {model: set() for model in _PUBLIC_BENCHMARK_MODELS}
    generation_cache: list[Any] = []
    for evidence in context.generation_evidence:
        requested = evidence.manifest.provider.model
        for scored in evidence.scored_attempts:
            raw = scored.raw
            assert raw.returned_model_id is not None
            assert raw.returned_model_source_sha256 is not None
            generation_returned[requested].add(raw.returned_model_id)
            generation_sources[requested].append(raw.returned_model_source_sha256)
            generation_cache.append(
                PublicBenchmarkCacheEvidenceV1.model_validate(
                    _cache_evidence_payload_from_generation(raw)
                )
            )
    judge_attempts = tuple(
        attempt for boundary in judge_attempt_boundaries for attempt in boundary.attempts
    )
    judge_returned = {
        attempt.returned_judge_model_id
        for attempt in judge_attempts
        if attempt.returned_judge_model_id is not None
    }
    assert len(judge_returned) == 1
    judge_returned_model = next(iter(judge_returned))
    judge_sources = tuple(attempt.returned_judge_model_source_sha256 for attempt in judge_attempts)
    requested_returned = [
        RequestedReturnedModelEvidenceV1(
            purpose="generation",
            requested_model_id=model,
            returned_model_id=next(iter(generation_returned[model])),
            returned_model_source_sha256=compute_requested_returned_model_source_sha256(
                purpose="generation",
                requested_model_id=model,
                returned_model_id=next(iter(generation_returned[model])),
                ordered_source_sha256s=tuple(generation_sources[model]),
            ),
        )
        for model in _PUBLIC_BENCHMARK_MODELS
    ]
    requested_returned.append(
        RequestedReturnedModelEvidenceV1(
            purpose="judge",
            requested_model_id="gpt-5.6-sol",
            returned_model_id=judge_returned_model,
            returned_model_source_sha256=compute_requested_returned_model_source_sha256(
                purpose="judge",
                requested_model_id="gpt-5.6-sol",
                returned_model_id=judge_returned_model,
                ordered_source_sha256s=judge_sources,
            ),
        )
    )
    judge_cache = tuple(
        PublicBenchmarkCacheEvidenceV1.model_validate(_cache_evidence_payload_from_judge(attempt))
        for attempt in judge_attempts
    )
    index = context.index
    payload: dict[str, object] = {
        "schema_version": "benchmark-provider-evidence-index-v1",
        "campaign_id": index.campaign_id,
        "audit_reviewer_registry_sha256": index.audit_reviewer_registry_sha256,
        "protocol_reviewer_registry_sha256": index.protocol_reviewer_registry_sha256,
        "campaign_seed": index.campaign_seed,
        "campaign_seed_sha256": index.campaign_seed_sha256,
        "input_tag_commit": index.input_tag_commit,
        "hard_scorer_source_sha256": index.hard_scorer_source_sha256,
        "hard_score_protocol_sha256": index.hard_score_protocol_sha256,
        "judge_protocol_sha256": index.judge_protocol_sha256,
        "judge_prompt_sha256": index.judge_prompt_sha256,
        "judge_schema_sha256": index.judge_schema_sha256,
        "judge_requested_service_tier": index.judge_requested_service_tier,
        "judge_service_tier_wire_field": index.judge_service_tier_wire_field,
        "corpus_case_root": index.corpus_case_root,
        "statistical_protocol_sha256": index.statistical_protocol_sha256,
        "audit_protocol_sha256": index.audit_protocol_sha256,
        "estimand_protocol_sha256": index.estimand_protocol_sha256,
        "bootstrap_protocol_sha256": index.bootstrap_protocol_sha256,
        "outcome_classification_protocol_sha256": (index.outcome_classification_protocol_sha256),
        "false_fail_sensitivity_protocol_sha256": (index.false_fail_sensitivity_protocol_sha256),
        "audit_sampling_protocol_sha256": index.audit_sampling_protocol_sha256,
        "audit_commit_reveal_protocol_sha256": (index.audit_commit_reveal_protocol_sha256),
        "audit_adjudication_protocol_sha256": index.audit_adjudication_protocol_sha256,
        "workflow_root": index.workflow_root,
        "provider_projection_root": index.provider_projection_root,
        "audit_reviewer_registry": index.audit_reviewer_registry.model_dump(
            mode="json", warnings=False
        ),
        "protocol_reviewer_registry": index.protocol_reviewer_registry.model_dump(
            mode="python", round_trip=True, warnings=False
        ),
        "protocol_attestations": tuple(
            item.model_dump(mode="python", round_trip=True, warnings=False)
            for item in index.protocol_attestations
        ),
        "protocol_attestations_root": index.protocol_attestations_root,
        "generation_context_expectation_sha256": (
            expectation.expectation.generation_context_expectation_sha256
        ),
        "bound_generation_complete_authority_root_sha256": (
            expectation.bound_generation_complete_authority_root_sha256
        ),
        "generation_context_index_sha256": index.generation_context_index_sha256,
        "generation_root_index_sha256": context.root_index.layer_root_index_sha256,
        "hard_score_root_index_sha256": hard_score_root_index.layer_root_index_sha256,
        "judge_request_root_index_sha256": (judge_request_root_index.layer_root_index_sha256),
        "judge_attempt_root_index_sha256": (
            judge_attempt_root_index.judge_attempt_root_index_sha256
        ),
        "judge_root_index_sha256": judge_root_index.layer_root_index_sha256,
        "ordered_generation_capsule_sha256s": tuple(
            member.generation_capsule_sha256 for member in context.root_index.members
        ),
        "ordered_hard_score_request_set_sha256s": tuple(
            item.hard_score_request_set_sha256 for item in hard_score_sets
        ),
        "ordered_judge_request_attachment_sha256s": tuple(
            item.judge_request_attachment_sha256 for item in judge_request_attachments
        ),
        "ordered_judge_attempt_boundary_sha256s": tuple(
            item.judge_attempt_boundary_sha256 for item in judge_attempt_boundaries
        ),
        "ordered_judge_attachment_sha256s": tuple(
            item.judge_attachment_sha256 for item in judge_attachments
        ),
        "requested_returned_model_ids": tuple(
            item.model_dump(mode="python", round_trip=True, warnings=False)
            for item in requested_returned
        ),
        "generation_cache_evidence": tuple(
            item.model_dump(mode="python", round_trip=True, warnings=False)
            for item in generation_cache
        ),
        "judge_cache_evidence": tuple(
            item.model_dump(mode="python", round_trip=True, warnings=False) for item in judge_cache
        ),
    }
    payload["provider_evidence_index_sha256"] = stable_digest(
        "laconian-benchmark-provider-evidence-index-v1",
        payload,
    )
    return ProviderEvidenceIndexV1.model_validate(payload)


@dataclass(frozen=True, slots=True)
class CompleteProviderEvidenceFixture:
    """All durable paths and loaded owners for one complete Task 8 provider graph."""

    workspace_root: Path
    generation_root: Path
    generation_index_path: Path
    hard_score_root: Path
    judge_request_root: Path
    judge_attempt_root: Path
    judge_root: Path
    provider_index_path: Path
    expectation: Any
    identity_registry_bundle: Any
    generation_context: Any
    hard_score_root_index: Any
    hard_score_request_sets: tuple[Any, ...]
    judge_request_root_index: Any
    judge_request_attachments: tuple[Any, ...]
    judge_attempt_root_index: Any
    judge_attempt_boundaries: tuple[Any, ...]
    judge_root_index: Any
    judge_attachments: tuple[Any, ...]
    provider_index: Any
    provider_evidence: Any | None

    def load(self) -> Any:
        """Freshly load the provider wrapper from this fixture's durable roots."""

        from laconian_eval.benchmark.provider_evidence import (
            load_verified_benchmark_provider_evidence,
        )

        return load_verified_benchmark_provider_evidence(
            provider_index_path=self.provider_index_path,
            generation_root=self.generation_root,
            hard_score_root=self.hard_score_root,
            judge_request_root=self.judge_request_root,
            judge_attempt_root=self.judge_attempt_root,
            judge_root=self.judge_root,
            generation_expectation=self.expectation,
            identity_registry_bundle=self.identity_registry_bundle,
        )

    def with_workspace_root(self, clone: Path) -> CompleteProviderEvidenceFixture:
        """Rebind durable paths after a byte-for-byte workspace clone."""

        return replace(
            self,
            workspace_root=clone,
            generation_root=clone / self.generation_root.relative_to(self.workspace_root),
            generation_index_path=(
                clone / self.generation_index_path.relative_to(self.workspace_root)
            ),
            hard_score_root=clone / self.hard_score_root.relative_to(self.workspace_root),
            judge_request_root=(clone / self.judge_request_root.relative_to(self.workspace_root)),
            judge_attempt_root=(clone / self.judge_attempt_root.relative_to(self.workspace_root)),
            judge_root=clone / self.judge_root.relative_to(self.workspace_root),
            provider_index_path=(clone / self.provider_index_path.relative_to(self.workspace_root)),
            provider_evidence=None,
        )

    def file_sha256s(self) -> dict[str, str]:
        """Return a deterministic relative-path/raw-file digest inventory."""

        files = sorted(
            (path for path in self.workspace_root.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(self.workspace_root).as_posix().encode("utf-8"),
        )
        return {
            path.relative_to(self.workspace_root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in files
        }


def build_complete_provider_evidence_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> CompleteProviderEvidenceFixture:
    """Build the full 36-chain provider tree and return its loader-minted wrapper."""

    from laconian_eval.benchmark.provider_evidence import write_provider_evidence_index

    workspace_root = tmp_path / "provider-workspace"
    workspace_root.mkdir()
    (
        generation_root,
        generation_index_path,
        expectation,
        context,
    ) = _build_complete_public_generation_context(workspace_root, monkeypatch)

    hard_score_sets = _build_hard_score_request_sets_fast(context)
    hard_score_root = workspace_root / "HARD"
    hard_score_root_index = _write_attachment_layer(
        hard_score_root,
        kind="hard-score",
        context=context,
        attachments=hard_score_sets,
        digest_field="hard_score_request_set_sha256",
    )
    identity_bundle = protocol_identity_registry_bundle()
    request_attachments = _build_judge_request_attachments_fast(
        context=context,
        hard_score_sets=hard_score_sets,
        identity_registry_bundle=identity_bundle,
    )
    judge_request_root = workspace_root / "REQUESTS"
    request_root_index = _write_attachment_layer(
        judge_request_root,
        kind="judge-request",
        context=context,
        attachments=request_attachments,
        digest_field="judge_request_attachment_sha256",
    )
    (
        judge_attempt_root,
        judge_attempt_root_index,
        judge_attempt_boundaries,
    ) = _build_judge_attempt_root(
        workspace_root,
        context=context,
        request_root_index=request_root_index,
        hard_score_sets=hard_score_sets,
        request_attachments=request_attachments,
    )
    judge_attachments = _build_judge_attachments_fast(
        context=context,
        hard_score_sets=hard_score_sets,
        request_attachments=request_attachments,
        attempt_root_index=judge_attempt_root_index,
        attempt_boundaries=judge_attempt_boundaries,
    )
    judge_root = workspace_root / "JUDGES"
    judge_root_index = _write_attachment_layer(
        judge_root,
        kind="judge",
        context=context,
        attachments=judge_attachments,
        digest_field="judge_attachment_sha256",
    )
    provider_index = _build_provider_index(
        context=context,
        expectation=expectation,
        hard_score_root_index=hard_score_root_index,
        hard_score_sets=hard_score_sets,
        judge_request_root_index=request_root_index,
        judge_request_attachments=request_attachments,
        judge_attempt_root_index=judge_attempt_root_index,
        judge_attempt_boundaries=judge_attempt_boundaries,
        judge_root_index=judge_root_index,
        judge_attachments=judge_attachments,
    )
    provider_index_path = judge_root / "provider-evidence-index.json"
    write_provider_evidence_index(
        provider_index_path,
        provider_index,
        generation_expectation=expectation,
    )
    fixture = CompleteProviderEvidenceFixture(
        workspace_root=workspace_root,
        generation_root=generation_root,
        generation_index_path=generation_index_path,
        hard_score_root=hard_score_root,
        judge_request_root=judge_request_root,
        judge_attempt_root=judge_attempt_root,
        judge_root=judge_root,
        provider_index_path=provider_index_path,
        expectation=expectation,
        identity_registry_bundle=identity_bundle,
        generation_context=context,
        hard_score_root_index=hard_score_root_index,
        hard_score_request_sets=hard_score_sets,
        judge_request_root_index=request_root_index,
        judge_request_attachments=request_attachments,
        judge_attempt_root_index=judge_attempt_root_index,
        judge_attempt_boundaries=judge_attempt_boundaries,
        judge_root_index=judge_root_index,
        judge_attachments=judge_attachments,
        provider_index=provider_index,
        provider_evidence=None,
    )
    provider_evidence = fixture.load()
    loaded_context = provider_evidence.generation_context
    assert loaded_context.generation_evidence == context.generation_evidence
    for provisional, loaded in zip(
        context.generation_evidence,
        loaded_context.generation_evidence,
        strict=True,
    ):
        assert provisional is not loaded
        assert provisional.seal is not loaded.seal
        assert provisional.manifest is not loaded.manifest
        assert provisional.plan is not loaded.plan
        assert provisional.scored_attempts is not loaded.scored_attempts
        assert provisional.cases_by_uid is not loaded.cases_by_uid
        assert all(
            provisional_row is not loaded_row
            for provisional_row, loaded_row in zip(
                provisional.plan,
                loaded.plan,
                strict=True,
            )
        )
        assert all(
            provisional_row is not loaded_row
            for provisional_row, loaded_row in zip(
                provisional.scored_attempts,
                loaded.scored_attempts,
                strict=True,
            )
        )
        assert all(
            provisional.cases_by_uid[case_uid] is not loaded.cases_by_uid[case_uid]
            for case_uid in provisional.cases_by_uid
        )
    return replace(
        fixture,
        expectation=provider_evidence.generation_expectation,
        identity_registry_bundle=provider_evidence.identity_registry_bundle,
        generation_context=loaded_context,
        hard_score_root_index=provider_evidence.hard_score_root_index,
        hard_score_request_sets=provider_evidence.hard_score_request_sets,
        judge_request_root_index=provider_evidence.judge_request_root_index,
        judge_request_attachments=provider_evidence.judge_request_attachments,
        judge_attempt_root_index=provider_evidence.judge_attempt_root.index,
        judge_attempt_boundaries=provider_evidence.judge_attempt_root.boundaries,
        judge_root_index=provider_evidence.judge_root_index,
        judge_attachments=provider_evidence.judge_attachments,
        provider_index=provider_evidence.index,
        provider_evidence=provider_evidence,
    )


_CACHED_COMPLETE_PROVIDER_EVIDENCE_FIXTURE: CompleteProviderEvidenceFixture | None = None


def get_cached_complete_provider_evidence_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> CompleteProviderEvidenceFixture:
    """Build the expensive complete provider graph once for all Task 8 test modules."""

    import pytest

    global _CACHED_COMPLETE_PROVIDER_EVIDENCE_FIXTURE

    if _CACHED_COMPLETE_PROVIDER_EVIDENCE_FIXTURE is not None:
        return _CACHED_COMPLETE_PROVIDER_EVIDENCE_FIXTURE
    build_root = tmp_path_factory.getbasetemp() / "task8-provider-graph"
    try:
        build_root.mkdir()
    except FileExistsError as error:
        raise RuntimeError("unowned Task 8 provider fixture path already exists") from error
    monkeypatch = pytest.MonkeyPatch()
    try:
        fixture = build_complete_provider_evidence_fixture(build_root, monkeypatch)
    except BaseException:
        shutil.rmtree(build_root)
        raise
    finally:
        monkeypatch.undo()
    _CACHED_COMPLETE_PROVIDER_EVIDENCE_FIXTURE = fixture
    return fixture
