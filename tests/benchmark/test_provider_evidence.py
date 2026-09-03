"""Behavioral tests for the verified benchmark provider-evidence boundary."""

from __future__ import annotations

import dataclasses
import gc
import importlib
import inspect
import json
import shutil
import subprocess
import sys
import threading
import weakref
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from pydantic import ValidationError

from laconian_eval.benchmark.aggregation import (
    InferenceIntegrityError,
    aggregate_verified_evidence,
)
from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.benchmark.protocol_review import protocol_review_digest
from laconian_eval.benchmark.provider_evidence import (
    _VERIFIED_PROVIDER_EVIDENCE_MINTS,
    BenchmarkProviderEvidenceProjectionV1,
    ProviderEvidenceIndexV1,
    RequestedReturnedModelEvidenceV1,
    VerifiedBenchmarkProviderEvidenceV1,
    _revalidate_verified_provider_evidence_v1,
    _verify_provider_chains_from_checked_context,
    build_audit_population,
    compute_requested_returned_model_source_sha256,
    load_verified_benchmark_provider_evidence,
    write_provider_evidence_index,
)
from laconian_eval.capsule.canonical import stable_digest
from tests.benchmark.helpers import (
    CompleteProviderEvidenceFixture,
    get_cached_complete_provider_evidence_fixture,
    protocol_identity_registry_bundle,
    sha256_marker,
)


@pytest.fixture(scope="module")
def provider_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> CompleteProviderEvidenceFixture:
    return get_cached_complete_provider_evidence_fixture(tmp_path_factory)


def _load(fixture: CompleteProviderEvidenceFixture) -> VerifiedBenchmarkProviderEvidenceV1:
    return load_verified_benchmark_provider_evidence(
        provider_index_path=fixture.provider_index_path,
        generation_root=fixture.generation_root,
        hard_score_root=fixture.hard_score_root,
        judge_request_root=fixture.judge_request_root,
        judge_attempt_root=fixture.judge_attempt_root,
        judge_root=fixture.judge_root,
        generation_expectation=fixture.expectation,
        identity_registry_bundle=fixture.identity_registry_bundle,
    )


def _cached(fixture: CompleteProviderEvidenceFixture) -> VerifiedBenchmarkProviderEvidenceV1:
    value = fixture.provider_evidence
    assert type(value) is VerifiedBenchmarkProviderEvidenceV1
    return value


def _clone(
    fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
    name: str,
) -> CompleteProviderEvidenceFixture:
    target = tmp_path / name
    shutil.copytree(fixture.workspace_root, target)
    return fixture.with_workspace_root(target)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(canonical_json_v1(payload) + b"\n")


def _rehash_provider_index(payload: dict[str, Any]) -> None:
    payload["provider_evidence_index_sha256"] = stable_digest(
        "laconian-benchmark-provider-evidence-index-v1",
        {key: value for key, value in payload.items() if key != "provider_evidence_index_sha256"},
    )


def _wrapper_kwargs(
    evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> dict[str, object]:
    return {
        field.name: getattr(evidence, field.name)
        for field in dataclasses.fields(VerifiedBenchmarkProviderEvidenceV1)
    }


def _assert_load_rejects(fixture: CompleteProviderEvidenceFixture) -> None:
    with pytest.raises((TypeError, ValueError, ValidationError)):
        _load(fixture)


def test_generation_context_and_provider_index_bind_default_judge_service_tier_and_wire_field(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    assert (
        evidence.generation_context.index.judge_requested_service_tier,
        evidence.generation_context.index.judge_service_tier_wire_field,
    ) == ("default", "service_tier")
    assert (
        evidence.index.judge_requested_service_tier,
        evidence.index.judge_service_tier_wire_field,
    ) == ("default", "service_tier")


def test_generation_and_provider_indexes_bind_two_ordered_numeric_reviewer_accounts(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    for registry in (
        evidence.generation_context.index.audit_reviewer_registry,
        evidence.index.audit_reviewer_registry,
    ):
        assert len(registry.reviewers) == 2
        assert tuple(row.reviewer_id for row in registry.reviewers) == tuple(
            sorted((row.reviewer_id for row in registry.reviewers), key=str.encode)
        )
        assert len({row.reviewer_numeric_account_id for row in registry.reviewers}) == 2


def test_protocol_attestations_bind_both_registry_digests_and_exact_role_identity(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    expected_roles = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    assert (
        tuple(row.statement.role for row in evidence.index.protocol_attestations) == expected_roles
    )
    for attestation, reviewer in zip(
        evidence.index.protocol_attestations,
        evidence.index.protocol_reviewer_registry.reviewers,
        strict=True,
    ):
        assert attestation.statement.protocol_registry_sha256 == (
            evidence.index.protocol_reviewer_registry_sha256
        )
        assert (
            attestation.statement.reviewer_numeric_account_id,
            attestation.statement.reviewer_login,
            attestation.statement.verification_mode,
            attestation.statement.signing_fingerprint,
        ) == (
            reviewer.reviewer_numeric_account_id,
            reviewer.reviewer_login,
            reviewer.verification_mode,
            reviewer.signing_fingerprint,
        )
    # The public owner helper binds the complete ordered source set, not one selected source.
    assert evidence.index.requested_returned_model_ids[0].returned_model_source_sha256 == (
        compute_requested_returned_model_source_sha256(
            purpose="generation",
            requested_model_id="gpt-5.6-sol",
            returned_model_id=evidence.index.requested_returned_model_ids[0].returned_model_id,
            ordered_source_sha256s=tuple(
                row.raw.returned_model_source_sha256
                for capsule in evidence.generation_evidence
                if capsule.manifest.provider.model == "gpt-5.6-sol"
                for row in capsule.scored_attempts
                if row.terminal_reason == "success"
            ),
        )
    )


def test_adapter_rejects_protocol_attestation_not_verified_against_role_fingerprint(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    payload = provider_fixture.provider_index.model_dump(mode="json")
    attestation = payload["protocol_attestations"][1]
    replacement = "SHA256:" + "G" * 43
    attestation["statement"]["signing_fingerprint"] = replacement
    attestation["statement"]["statement_sha256"] = protocol_review_digest(
        "laconian-protocol-review-statement-v1",
        {
            key: value
            for key, value in attestation["statement"].items()
            if key != "statement_sha256"
        },
    )
    attestation["signature_evidence"]["fingerprint"] = replacement
    attestation["attestation_sha256"] = protocol_review_digest(
        "laconian-verified-protocol-attestation-v1",
        {key: value for key, value in attestation.items() if key != "attestation_sha256"},
    )
    payload["protocol_attestations_root"] = protocol_review_digest(
        "laconian-verified-protocol-attestations-root-v1",
        payload["protocol_attestations"],
    )
    _rehash_provider_index(payload)
    with pytest.raises(ValidationError):
        ProviderEvidenceIndexV1.model_validate_json(canonical_json_v1(payload))


def test_provider_index_projection_and_loader_reject_workflow_root_substitution(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    clone = _clone(provider_fixture, tmp_path, "workflow")
    payload = _read_json(clone.provider_index_path)
    payload["workflow_root"] = sha256_marker(991_001)
    _rehash_provider_index(payload)
    _write_json(clone.provider_index_path, payload)
    _assert_load_rejects(clone)
    projection = provider_fixture.provider_evidence.projection.model_dump(mode="json")
    projection["workflow_root"] = sha256_marker(991_002)
    projection["benchmark_provider_evidence_sha256"] = stable_digest(
        "laconian-benchmark-provider-evidence-v1",
        {
            key: value
            for key, value in projection.items()
            if key != "benchmark_provider_evidence_sha256"
        },
    )
    projected = BenchmarkProviderEvidenceProjectionV1.model_validate_json(
        canonical_json_v1(projection)
    )
    assert projected.workflow_root != provider_fixture.provider_evidence.index.workflow_root
    with pytest.raises((TypeError, ValueError)):
        _revalidate_verified_provider_evidence_v1(
            dataclasses.replace(
                provider_fixture.provider_evidence,
                projection=projected,
            )
        )


def test_provider_index_projection_and_loader_bind_authority_checked_statistical_protocol(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    subject = {
        item.kind: item.sha256
        for attestation in evidence.index.protocol_attestations
        for item in attestation.statement.subjects
    }
    assert evidence.index.statistical_protocol_sha256 == subject["statistical_protocol_sha256"]
    assert evidence.projection.statistical_protocol_sha256 == (
        evidence.index.statistical_protocol_sha256
    )


def test_provider_index_projection_and_loader_bind_exact_registry_audit_protocol(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    assert (
        evidence.index.audit_protocol_sha256
        == evidence.generation_context.index.audit_protocol_sha256
    )
    assert evidence.projection.audit_protocol_sha256 == evidence.index.audit_protocol_sha256
    assert evidence.projection.protocol_bindings.audit_reviewer_registry_sha256 == (
        evidence.index.audit_reviewer_registry_sha256
    )


def test_benchmark_neutral_records_do_not_duplicate_runtime_workflow_inventory_type() -> None:
    module = importlib.import_module("laconian_eval.benchmark.provider_evidence")
    assert "WorkflowInventoryV1" not in vars(module)
    assert all(not name.startswith("laconian_eval.campaign") for name in vars(module))
    assert tuple(inspect.signature(_verify_provider_chains_from_checked_context).parameters) == (
        "checked_context",
        "expectation",
        "identity_registry_bundle",
        "hard_score_request_sets",
        "judge_request_attachments",
        "judge_attachments",
    )


def test_generation_and_provider_indexes_bind_exact_three_role_protocol_review_root(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    assert len(evidence.index.protocol_attestations) == 3
    assert (
        evidence.index.protocol_attestations
        == evidence.generation_context.index.protocol_attestations
    )
    assert evidence.index.protocol_attestations_root == (
        evidence.generation_context.index.protocol_attestations_root
    )


def test_prepare_judge_requires_generation_context_index_before_provider_index_exists(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    clone = _clone(provider_fixture, tmp_path, "prepare-before-provider")
    clone.provider_index_path.unlink()
    assert clone.generation_index_path.is_file()
    assert clone.judge_request_root.joinpath("judge-requests", "index.json").is_file()
    with pytest.raises(ValueError):
        _load(clone)


def test_provider_evidence_index_binds_plaintext_seed_commit_registry_and_four_layer_indexes(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    assert evidence.index.campaign_seed == evidence.generation_context.index.campaign_seed
    assert evidence.index.input_tag_commit == evidence.generation_context.index.input_tag_commit
    assert (
        evidence.index.audit_reviewer_registry
        == evidence.generation_context.index.audit_reviewer_registry
    )
    assert (
        evidence.index.generation_root_index_sha256,
        evidence.index.hard_score_root_index_sha256,
        evidence.index.judge_request_root_index_sha256,
        evidence.index.judge_root_index_sha256,
    ) == (
        evidence.generation_context.root_index.layer_root_index_sha256,
        evidence.hard_score_root_index.layer_root_index_sha256,
        evidence.judge_request_root_index.layer_root_index_sha256,
        evidence.judge_root_index.layer_root_index_sha256,
    )


def test_provider_index_copies_expectation_digest_and_bound_final_authority_root_without_serializing_capability(  # noqa: E501
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    payload = _read_json(provider_fixture.provider_index_path)
    assert payload["generation_context_expectation_sha256"] == (
        provider_fixture.expectation.expectation.generation_context_expectation_sha256
    )
    assert payload["bound_generation_complete_authority_root_sha256"] == (
        provider_fixture.expectation.bound_generation_complete_authority_root_sha256
    )
    serialized = canonical_json_v1(payload)
    assert b'"expectation"' not in serialized
    assert b'"identity_registry_bundle"' not in serialized


def test_provider_writer_requires_the_same_live_expectation_wrapper_and_final_root(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    from laconian_eval.benchmark.context import VerifiedGenerationContextExpectationV1

    wrong = VerifiedGenerationContextExpectationV1(
        expectation=provider_fixture.expectation.expectation,
        bound_generation_complete_authority_root_sha256=sha256_marker(991_003),
    )
    output = tmp_path / "provider-evidence-index.json"
    with pytest.raises(ValueError):
        write_provider_evidence_index(
            output, provider_fixture.provider_index, generation_expectation=wrong
        )
    assert not output.exists()
    write_provider_evidence_index(
        output,
        provider_fixture.provider_index,
        generation_expectation=provider_fixture.expectation,
    )
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        write_provider_evidence_index(
            output,
            provider_fixture.provider_index,
            generation_expectation=provider_fixture.expectation,
        )
    assert output.read_bytes() == before


def test_verified_provider_loader_requires_external_live_expectation_wrapper_and_never_mints_one(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    kwargs = dict(
        provider_index_path=provider_fixture.provider_index_path,
        generation_root=provider_fixture.generation_root,
        hard_score_root=provider_fixture.hard_score_root,
        judge_request_root=provider_fixture.judge_request_root,
        judge_attempt_root=provider_fixture.judge_attempt_root,
        judge_root=provider_fixture.judge_root,
        identity_registry_bundle=provider_fixture.identity_registry_bundle,
    )
    with pytest.raises(TypeError):
        load_verified_benchmark_provider_evidence(**kwargs)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        VerifiedBenchmarkProviderEvidenceV1(**_wrapper_kwargs(provider_fixture.provider_evidence))


def test_verified_provider_loader_rejects_expectation_predecessor_or_final_authority_mismatch(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    from laconian_eval.benchmark.context import (
        GenerationContextExpectationV1,
        VerifiedGenerationContextExpectationV1,
    )

    for field in (
        "predecessor_authority_root_sha256",
        "generation_context_expectation_sha256",
    ):
        payload = provider_fixture.expectation.expectation.model_dump(mode="json")
        payload[field] = sha256_marker(991_010)
        if field != "generation_context_expectation_sha256":
            payload["generation_context_expectation_sha256"] = stable_digest(
                "laconian-benchmark-generation-context-expectation-v1",
                {
                    key: value
                    for key, value in payload.items()
                    if key != "generation_context_expectation_sha256"
                },
            )
        with pytest.raises((ValidationError, ValueError)):
            forged = VerifiedGenerationContextExpectationV1(
                expectation=GenerationContextExpectationV1.model_validate_json(
                    canonical_json_v1(payload)
                ),
                bound_generation_complete_authority_root_sha256=(
                    provider_fixture.expectation.bound_generation_complete_authority_root_sha256
                ),
            )
            load_verified_benchmark_provider_evidence(
                provider_index_path=provider_fixture.provider_index_path,
                generation_root=provider_fixture.generation_root,
                hard_score_root=provider_fixture.hard_score_root,
                judge_request_root=provider_fixture.judge_request_root,
                judge_attempt_root=provider_fixture.judge_attempt_root,
                judge_root=provider_fixture.judge_root,
                generation_expectation=forged,
                identity_registry_bundle=provider_fixture.identity_registry_bundle,
            )


def test_provider_evidence_index_rejects_wrong_seed_hash_self_hash_or_parent_vector(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    base = provider_fixture.provider_index.model_dump(mode="json")
    variants: list[dict[str, Any]] = []
    for mutate in ("campaign_seed_sha256", "provider_evidence_index_sha256"):
        payload = dict(base)
        payload[mutate] = sha256_marker(991_020)
        variants.append(payload)
    payload = dict(base)
    payload["ordered_judge_attachment_sha256s"] = [
        *base["ordered_judge_attachment_sha256s"][:-1],
        base["ordered_judge_attachment_sha256s"][0],
    ]
    _rehash_provider_index(payload)
    variants.append(payload)
    for payload in variants:
        with pytest.raises(ValidationError):
            ProviderEvidenceIndexV1.model_validate_json(canonical_json_v1(payload))


def test_provider_loader_rejects_registry_binding_or_protocol_attestation_root_substitution(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    for field in ("audit_reviewer_registry_sha256", "protocol_attestations_root"):
        clone = _clone(provider_fixture, tmp_path, field)
        payload = _read_json(clone.provider_index_path)
        payload[field] = sha256_marker(991_030)
        _rehash_provider_index(payload)
        _write_json(clone.provider_index_path, payload)
        _assert_load_rejects(clone)


def test_provider_loader_requires_explicit_index_and_rejects_seed_commit_or_root_substitution(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    wrong_leaf = provider_fixture.judge_root / "renamed-index.json"
    shutil.copy2(provider_fixture.provider_index_path, wrong_leaf)
    with pytest.raises(ValueError):
        load_verified_benchmark_provider_evidence(
            provider_index_path=wrong_leaf,
            generation_root=provider_fixture.generation_root,
            hard_score_root=provider_fixture.hard_score_root,
            judge_request_root=provider_fixture.judge_request_root,
            judge_attempt_root=provider_fixture.judge_attempt_root,
            judge_root=provider_fixture.judge_root,
            generation_expectation=provider_fixture.expectation,
            identity_registry_bundle=provider_fixture.identity_registry_bundle,
        )
    wrong_leaf.unlink()
    for field in ("campaign_seed", "input_tag_commit", "hard_score_root_index_sha256"):
        clone = _clone(provider_fixture, tmp_path, f"sub-{field}")
        payload = _read_json(clone.provider_index_path)
        payload[field] = sha256_marker(991_040)[: 40 if field == "input_tag_commit" else 64]
        if field == "campaign_seed":
            payload["campaign_seed_sha256"] = stable_digest(
                "laconian-campaign-seed-v1",
                {
                    "schema_version": "1",
                    "algorithm": "public-hex-seed-v1",
                    "campaign_seed": payload[field],
                },
            )
        _rehash_provider_index(payload)
        _write_json(clone.provider_index_path, payload)
        _assert_load_rejects(clone)


def test_provider_loader_requires_authority_bound_context_expectation_and_rejects_rehashed_forgery(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    bundle_payload = provider_fixture.identity_registry_bundle.model_dump(mode="json")
    bundle_payload["verifier_source_sha256"] = sha256_marker(991_050)
    bundle_payload["protocol_signature_verifier_tool_sha256"] = protocol_review_digest(
        "laconian-protocol-signature-verifier-tool-v1",
        {
            "algorithm_profile": (
                "ssh-ed25519-sshsig-git-sha512-or-openpgp-v4-ed25519-sha256-v1"
            ),
            "dependency_lock_path": bundle_payload["dependency_lock_path"],
            "dependency_lock_sha256": bundle_payload["dependency_lock_sha256"],
            "verifier_dependency_inventory_root": bundle_payload[
                "verifier_dependency_inventory_root"
            ],
            "entrypoint": (
                "laconian_eval.benchmark.protocol_review:_verify_keyed_signature_v1"
            ),
            "verifier_source_path": bundle_payload["verifier_source_path"],
            "verifier_source_sha256": bundle_payload["verifier_source_sha256"],
        },
    )
    bundle_payload["identity_registry_bundle_sha256"] = protocol_review_digest(
        "laconian-protocol-review-identity-registry-bundle-v1",
        {
            key: value
            for key, value in bundle_payload.items()
            if key != "identity_registry_bundle_sha256"
        },
    )
    bundle_type = type(provider_fixture.identity_registry_bundle)
    foreign = bundle_type.model_validate_json(canonical_json_v1(bundle_payload))
    with pytest.raises(ValueError):
        load_verified_benchmark_provider_evidence(
            provider_index_path=provider_fixture.provider_index_path,
            generation_root=provider_fixture.generation_root,
            hard_score_root=provider_fixture.hard_score_root,
            judge_request_root=provider_fixture.judge_request_root,
            judge_attempt_root=provider_fixture.judge_attempt_root,
            judge_root=provider_fixture.judge_root,
            generation_expectation=provider_fixture.expectation,
            identity_registry_bundle=foreign,
        )
    mutated = bundle_type.model_validate_json(
        canonical_json_v1(provider_fixture.identity_registry_bundle.model_dump(mode="json"))
    )
    object.__setattr__(mutated, "verifier_source_sha256", sha256_marker(991_051))
    with pytest.raises(ValueError):
        load_verified_benchmark_provider_evidence(
            provider_index_path=provider_fixture.provider_index_path,
            generation_root=provider_fixture.generation_root,
            hard_score_root=provider_fixture.hard_score_root,
            judge_request_root=provider_fixture.judge_request_root,
            judge_attempt_root=provider_fixture.judge_attempt_root,
            judge_root=provider_fixture.judge_root,
            generation_expectation=provider_fixture.expectation,
            identity_registry_bundle=mutated,
        )


def test_slice4_adapter_can_construct_index_without_benchmark_importing_campaign() -> None:
    script = """
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith('laconian_eval.campaign'):
        raise AssertionError(name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from laconian_eval.benchmark.provider_evidence import ProviderEvidenceIndexV1
assert ProviderEvidenceIndexV1.__module__ == 'laconian_eval.benchmark.provider_evidence'
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)


def test_runtime_adapter_imports_context_and_provider_contracts_from_distinct_owner_modules() -> (
    None
):
    from laconian_eval.benchmark.context import GenerationContextIndexV1

    assert GenerationContextIndexV1.__module__ == "laconian_eval.benchmark.context"
    assert ProviderEvidenceIndexV1.__module__ == "laconian_eval.benchmark.provider_evidence"
    assert GenerationContextIndexV1 is not ProviderEvidenceIndexV1


def test_benchmark_provider_projection_loads_exact_four_layer_roots_and_attempt_root_vector(
    provider_fixture: CompleteProviderEvidenceFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.provider_evidence as provider_evidence

    evidence = _cached(provider_fixture)
    assert len(evidence.generation_evidence) == 36
    assert len(evidence.hard_score_request_sets) == 36
    assert len(evidence.judge_request_attachments) == 36
    assert len(evidence.judge_attempt_root.boundaries) == 36
    assert len(evidence.judge_attachments) == 36
    assert evidence.projection.ordered_judge_attempt_boundary_sha256s == tuple(
        row.judge_attempt_boundary_sha256 for row in evidence.judge_attempt_root.boundaries
    )
    caller_thread = threading.get_ident()
    calls: list[tuple[str, int, int]] = []

    def record(kind: str):
        def core(_attachment: object, *, member: object, **_parents: object) -> None:
            calls.append((kind, member.ordinal, threading.get_ident()))

        return core

    with monkeypatch.context() as scoped:
        scoped.setattr(
            provider_evidence,
            "_verify_hard_score_request_set_from_checked_authority",
            record("hard"),
        )
        scoped.setattr(
            provider_evidence,
            "_verify_judge_request_attachment_from_checked_authority",
            record("request"),
        )
        scoped.setattr(
            provider_evidence,
            "_verify_judge_attachment_from_checked_authority",
            record("judge"),
        )
        _verify_provider_chains_from_checked_context(
            checked_context=evidence.generation_context,
            expectation=evidence.generation_expectation,
            identity_registry_bundle=evidence.identity_registry_bundle,
            hard_score_request_sets=evidence.hard_score_request_sets,
            judge_request_attachments=evidence.judge_request_attachments,
            judge_attachments=evidence.judge_attachments,
        )
    assert calls == [
        (kind, ordinal, caller_thread)
        for ordinal in range(36)
        for kind in ("hard", "request", "judge")
    ]
    from laconian_eval.benchmark.context import VerifiedGenerationContextExpectationV1

    wrong_expectation = VerifiedGenerationContextExpectationV1(
        expectation=evidence.generation_expectation.expectation,
        bound_generation_complete_authority_root_sha256=sha256_marker(991_062),
    )
    calls.clear()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            provider_evidence,
            "_verify_hard_score_request_set_from_checked_authority",
            record("hard"),
        )
        scoped.setattr(
            provider_evidence,
            "_verify_judge_request_attachment_from_checked_authority",
            record("request"),
        )
        scoped.setattr(
            provider_evidence,
            "_verify_judge_attachment_from_checked_authority",
            record("judge"),
        )
        with pytest.raises(ValueError, match="different external expectation"):
            _verify_provider_chains_from_checked_context(
                checked_context=evidence.generation_context,
                expectation=wrong_expectation,
                identity_registry_bundle=evidence.identity_registry_bundle,
                hard_score_request_sets=evidence.hard_score_request_sets,
                judge_request_attachments=evidence.judge_request_attachments,
                judge_attachments=evidence.judge_attachments,
            )
    assert calls == []


def test_benchmark_provider_projection_rejects_missing_reordered_or_cross_parent_members(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    missing = _clone(provider_fixture, tmp_path, "missing-member")
    member = missing.provider_index.ordered_judge_attachment_sha256s[0]
    path = next(
        missing.judge_root / row.relative_path
        for row in missing.judge_root_index.members
        if row.attachment_sha256 == member
    )
    path.unlink()
    _assert_load_rejects(missing)

    reordered = _clone(provider_fixture, tmp_path, "reordered-members")
    index_path = reordered.judge_root / "judge/index.json"
    index_payload = _read_json(index_path)
    index_payload["members"][0], index_payload["members"][1] = (
        index_payload["members"][1],
        index_payload["members"][0],
    )
    index_payload["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1",
        {key: value for key, value in index_payload.items() if key != "layer_root_index_sha256"},
    )
    _write_json(index_path, index_payload)
    provider_payload = _read_json(reordered.provider_index_path)
    provider_payload["judge_root_index_sha256"] = index_payload["layer_root_index_sha256"]
    provider_payload["ordered_judge_attachment_sha256s"] = [
        row["attachment_sha256"] for row in index_payload["members"]
    ]
    _rehash_provider_index(provider_payload)
    _write_json(reordered.provider_index_path, provider_payload)
    _assert_load_rejects(reordered)

    crossed = _clone(provider_fixture, tmp_path, "crossed-members")
    provider_payload = _read_json(crossed.provider_index_path)
    provider_payload["ordered_judge_attachment_sha256s"][0] = provider_payload[
        "ordered_judge_attachment_sha256s"
    ][1]
    _rehash_provider_index(provider_payload)
    _write_json(crossed.provider_index_path, provider_payload)
    _assert_load_rejects(crossed)


def test_benchmark_provider_projection_is_campaign_package_independent_and_input_read_only(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    before = provider_fixture.file_sha256s()
    evidence = _load(provider_fixture)
    assert provider_fixture.file_sha256s() == before
    assert type(evidence).__module__ == "laconian_eval.benchmark.provider_evidence"


def test_benchmark_provider_projection_preserves_cache_write_evidence_and_accounting_status(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    evidence = _cached(provider_fixture)
    assert evidence.projection.generation_cache_evidence == evidence.index.generation_cache_evidence
    assert evidence.projection.judge_cache_evidence == evidence.index.judge_cache_evidence
    assert evidence.projection.generation_cache_evidence
    assert all(
        item.cache_write_source_sha256 for item in evidence.projection.generation_cache_evidence
    )
    # Rewrite one real attempt source and every digest that publicly commits to it.  The
    # provider index remains self-consistent, but the unchanged final judge record still
    # commits to the original terminal attempt and the durable loader must reject the graph.
    clone = _clone(provider_fixture, tmp_path, "returned-model-source")
    boundary_path = clone.judge_attempt_root / "judge-attempts/000.json"
    boundary_payload = _read_json(boundary_path)
    attempt_payload = boundary_payload["attempts"][0]
    attempt_payload["returned_judge_model_source_sha256"] = sha256_marker(991_060)
    attempt_payload["judge_attempt_evidence_sha256"] = stable_digest(
        "laconian-judge-attempt-evidence-v1",
        {
            key: value
            for key, value in attempt_payload.items()
            if key != "judge_attempt_evidence_sha256"
        },
    )
    boundary_payload["judge_attempt_boundary_sha256"] = stable_digest(
        "laconian-judge-attempt-boundary-v1",
        {
            key: value
            for key, value in boundary_payload.items()
            if key != "judge_attempt_boundary_sha256"
        },
    )
    _write_json(boundary_path, boundary_payload)

    attempt_index_path = clone.judge_attempt_root / "judge-attempts/index.json"
    attempt_index_payload = _read_json(attempt_index_path)
    attempt_index_payload["members"][0]["judge_attempt_boundary_sha256"] = boundary_payload[
        "judge_attempt_boundary_sha256"
    ]
    attempt_index_payload["judge_attempt_root_index_sha256"] = stable_digest(
        "laconian-judge-attempt-root-index-v1",
        {
            key: value
            for key, value in attempt_index_payload.items()
            if key != "judge_attempt_root_index_sha256"
        },
    )
    _write_json(attempt_index_path, attempt_index_payload)

    all_boundary_payloads = [
        _read_json(clone.judge_attempt_root / f"judge-attempts/{ordinal:03d}.json")
        for ordinal in range(36)
    ]
    ordered_sources = tuple(
        row["returned_judge_model_source_sha256"]
        for boundary in all_boundary_payloads
        for row in boundary["attempts"]
        if row["disposition"] == "success"
    )
    provider_payload = _read_json(clone.provider_index_path)
    provider_payload["judge_attempt_root_index_sha256"] = attempt_index_payload[
        "judge_attempt_root_index_sha256"
    ]
    provider_payload["ordered_judge_attempt_boundary_sha256s"][0] = boundary_payload[
        "judge_attempt_boundary_sha256"
    ]
    judge_model = next(
        row for row in provider_payload["requested_returned_model_ids"] if row["purpose"] == "judge"
    )
    judge_model["returned_model_source_sha256"] = compute_requested_returned_model_source_sha256(
        purpose="judge",
        requested_model_id="gpt-5.6-sol",
        returned_model_id=judge_model["returned_model_id"],
        ordered_source_sha256s=ordered_sources,
    )
    _rehash_provider_index(provider_payload)
    ProviderEvidenceIndexV1.model_validate_json(canonical_json_v1(provider_payload))
    _write_json(clone.provider_index_path, provider_payload)
    _assert_load_rejects(clone)


def test_benchmark_provider_projection_preserves_closed_judge_service_tier_status(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    assert evidence.projection.judge_cache_evidence
    assert {item.service_tier_status for item in evidence.projection.judge_cache_evidence} == {
        "reported_default"
    }
    assert {item.requested_service_tier for item in evidence.projection.judge_cache_evidence} == {
        "default"
    }


def test_verified_aggregate_requires_loader_minted_provider_evidence_wrapper(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    with pytest.raises(TypeError):
        VerifiedBenchmarkProviderEvidenceV1(**_wrapper_kwargs(provider_fixture.provider_evidence))
    shell = object.__new__(VerifiedBenchmarkProviderEvidenceV1)
    for name, value in _wrapper_kwargs(provider_fixture.provider_evidence).items():
        object.__setattr__(shell, name, value)
    with pytest.raises(InferenceIntegrityError):
        aggregate_verified_evidence(provider_evidence=shell)


def test_verified_provider_owner_revalidator_rejects_replace_nested_and_low_level_forgery(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    minted = _load(provider_fixture)
    with pytest.raises(TypeError):
        dataclasses.replace(minted)
    low = object.__new__(VerifiedBenchmarkProviderEvidenceV1)
    for name, value in _wrapper_kwargs(minted).items():
        object.__setattr__(low, name, value)
    with pytest.raises(TypeError):
        _revalidate_verified_provider_evidence_v1(low)
    original_judges = minted.judge_attachments
    object.__setattr__(minted, "judge_attachments", tuple(reversed(original_judges)))
    with pytest.raises(ValueError):
        _revalidate_verified_provider_evidence_v1(minted)
    object.__setattr__(minted, "judge_attachments", original_judges)
    foreign_bundle = protocol_identity_registry_bundle()
    object.__setattr__(foreign_bundle, "verifier_source_sha256", sha256_marker(991_061))
    original_bundle = minted.identity_registry_bundle
    object.__setattr__(minted, "identity_registry_bundle", foreign_bundle)
    with pytest.raises(ValueError):
        _revalidate_verified_provider_evidence_v1(minted)
    object.__setattr__(minted, "identity_registry_bundle", original_bundle)

    class SpoofedRequestedReturnedModelEvidenceV1(RequestedReturnedModelEvidenceV1):
        pass

    SpoofedRequestedReturnedModelEvidenceV1.__module__ = RequestedReturnedModelEvidenceV1.__module__
    SpoofedRequestedReturnedModelEvidenceV1.__qualname__ = (
        RequestedReturnedModelEvidenceV1.__qualname__
    )
    original_index = minted.index
    requested = original_index.requested_returned_model_ids
    spoofed = SpoofedRequestedReturnedModelEvidenceV1.model_validate(
        requested[0].model_dump(mode="python", round_trip=True)
    )
    index_payload = original_index.model_dump(mode="python", round_trip=True)
    index_payload["requested_returned_model_ids"] = (spoofed, *requested[1:])
    with pytest.raises((TypeError, ValueError)):
        ProviderEvidenceIndexV1.model_validate(index_payload)
    projection_payload = minted.projection.model_dump(mode="python", round_trip=True)
    projection_payload["requested_returned_model_ids"] = (
        spoofed,
        *minted.projection.requested_returned_model_ids[1:],
    )
    with pytest.raises((TypeError, ValueError)):
        BenchmarkProviderEvidenceProjectionV1.model_validate(projection_payload)
    poisoned_index = original_index.model_copy(
        update={"requested_returned_model_ids": (spoofed, *requested[1:])}
    )
    object.__setattr__(minted, "index", poisoned_index)
    with pytest.raises(TypeError):
        _revalidate_verified_provider_evidence_v1(minted)
    object.__setattr__(minted, "index", original_index)

    first_capsule = minted.generation_evidence[0]
    original_cases = first_capsule.cases_by_uid
    backing: dict[str, object] = {}
    cycle = MappingProxyType(backing)
    backing["cycle"] = cycle
    object.__setattr__(first_capsule, "cases_by_uid", cycle)
    with pytest.raises(ValueError, match="cycle"):
        _revalidate_verified_provider_evidence_v1(minted)
    object.__setattr__(first_capsule, "cases_by_uid", original_cases)

    raw = first_capsule.scored_attempts[0].raw
    original_run_id = raw.run_id
    object.__setattr__(raw, "run_id", str(original_run_id))
    with pytest.raises(TypeError, match="scalar owner"):
        _revalidate_verified_provider_evidence_v1(minted)
    object.__setattr__(raw, "run_id", original_run_id)


def test_provider_mint_registry_weak_cleanup_cannot_transfer_identity_authority(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    minted = _load(provider_fixture)
    identity = id(minted)
    fields = _wrapper_kwargs(minted)
    reference = weakref.ref(minted)
    assert identity in _VERIFIED_PROVIDER_EVIDENCE_MINTS
    del minted
    gc.collect()
    assert reference() is None
    assert identity not in _VERIFIED_PROVIDER_EVIDENCE_MINTS
    forged = object.__new__(VerifiedBenchmarkProviderEvidenceV1)
    for name, value in fields.items():
        object.__setattr__(forged, name, value)
    with pytest.raises(TypeError):
        _revalidate_verified_provider_evidence_v1(forged)


def test_all_provider_evidence_consumers_revalidate_before_reading_supplied_fields(
    provider_fixture: CompleteProviderEvidenceFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.context as context_module
    import laconian_eval.benchmark.provider_evidence as provider_evidence
    from laconian_eval.benchmark.context import VerifiedGenerationContextIndexV1

    source = _cached(provider_fixture)
    validations = 0
    checked_contexts: list[VerifiedGenerationContextIndexV1] = []

    def counted_validate(*_args: object, **_kwargs: object) -> None:
        nonlocal validations
        validations += 1

    def counted_batch(
        *, checked_context: VerifiedGenerationContextIndexV1, **_parents: object
    ) -> None:
        checked_contexts.append(checked_context)

    with monkeypatch.context() as scoped:
        scoped.setattr(context_module, "_validate_evidence_members", counted_validate)
        scoped.setattr(
            provider_evidence,
            "_verify_provider_chains_from_checked_context",
            counted_batch,
        )
        first = _revalidate_verified_provider_evidence_v1(source)
        assert validations == 1
        assert len(checked_contexts) == 1
        assert checked_contexts[0] is first.generation_context
        poisoned = _revalidate_verified_provider_evidence_v1(first)
    assert validations == 2
    assert len(checked_contexts) == 2
    assert checked_contexts[0] is not checked_contexts[1]
    assert checked_contexts[0].index is not checked_contexts[1].index
    original_index = poisoned.index
    for consumer in (
        lambda value: aggregate_verified_evidence(provider_evidence=value),
        lambda value: build_audit_population(provider_evidence=value),
    ):
        object.__setattr__(poisoned, "index", object())
        with pytest.raises((TypeError, ValueError, InferenceIntegrityError)):
            consumer(poisoned)
        object.__setattr__(poisoned, "index", original_index)


def test_verified_aggregate_emits_exact_36_chain_1440_row_bijection(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    aggregates = aggregate_verified_evidence(provider_evidence=_cached(provider_fixture))
    assert tuple(item.generation_model for item in aggregates) == tuple(
        sorted(("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"), key=str.encode)
    )
    assert tuple(len(item.rows) for item in aggregates) == (480, 480, 480)
    assert len({row.response_id for item in aggregates for row in item.rows}) == 1_440


def test_verified_aggregate_requires_same_canonical_120_keys_across_all_models_and_arms(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    aggregates = aggregate_verified_evidence(provider_evidence=_cached(provider_fixture))
    populations = []
    for aggregate in aggregates:
        by_arm = {
            arm: {
                (row.scenario_uid, row.case_id, row.locale, row.repetition)
                for row in aggregate.rows
                if row.arm == arm
            }
            for arm in ("baseline", "caveman", "if", "concise")
        }
        assert {len(keys) for keys in by_arm.values()} == {120}
        assert len({frozenset(keys) for keys in by_arm.values()}) == 1
        populations.append(next(iter(by_arm.values())))
    assert len({frozenset(keys) for keys in populations}) == 1


def test_verified_aggregate_rejects_rehashed_semantic_flip_against_judge_attempt_root(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path: Path,
) -> None:
    clone = _clone(provider_fixture, tmp_path, "semantic-flip")
    layer_index_path = clone.judge_root / "judge/index.json"
    layer_index = _read_json(layer_index_path)
    member = layer_index["members"][0]
    attachment_path = clone.judge_root / member["relative_path"]
    attachment = _read_json(attachment_path)
    judgment = attachment["records"][0]["judgment"]
    judgment["rubric_items"][0]["passed"] = not judgment["rubric_items"][0]["passed"]
    judgment["semantic_pass"] = not judgment["semantic_pass"]
    attachment["judge_attachment_sha256"] = stable_digest(
        "laconian-judge-attachment-v1",
        {key: value for key, value in attachment.items() if key != "judge_attachment_sha256"},
    )
    _write_json(attachment_path, attachment)
    member["attachment_sha256"] = attachment["judge_attachment_sha256"]
    layer_index["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1",
        {key: value for key, value in layer_index.items() if key != "layer_root_index_sha256"},
    )
    _write_json(layer_index_path, layer_index)
    provider = _read_json(clone.provider_index_path)
    provider["ordered_judge_attachment_sha256s"][0] = member["attachment_sha256"]
    provider["judge_root_index_sha256"] = layer_index["layer_root_index_sha256"]
    _rehash_provider_index(provider)
    _write_json(clone.provider_index_path, provider)
    _assert_load_rejects(clone)


def test_verified_aggregate_rejects_missing_duplicate_reordered_or_cross_parent_join(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    poisoned = _load(provider_fixture)
    for field, value in (
        (
            "hard_score_request_sets",
            provider_fixture.provider_evidence.hard_score_request_sets[:-1],
        ),
        (
            "judge_request_attachments",
            (
                provider_fixture.provider_evidence.judge_request_attachments[0],
                *provider_fixture.provider_evidence.judge_request_attachments,
            ),
        ),
        (
            "judge_attachments",
            tuple(reversed(provider_fixture.provider_evidence.judge_attachments)),
        ),
    ):
        original = getattr(poisoned, field)
        object.__setattr__(poisoned, field, value)
        with pytest.raises(InferenceIntegrityError):
            aggregate_verified_evidence(provider_evidence=poisoned)
        object.__setattr__(poisoned, field, original)


def test_verified_aggregate_rejects_unknown_delivery_authentication_or_response_received_error(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    poisoned = _load(provider_fixture)
    boundary = poisoned.judge_attempt_root.boundaries[0]
    terminal = boundary.attempts[-1]
    assert terminal.delivery_certainty == "response_received"
    object.__setattr__(terminal, "delivery_certainty", "unknown")
    with pytest.raises(InferenceIntegrityError):
        aggregate_verified_evidence(provider_evidence=poisoned)


def test_verified_aggregate_cost_is_analytical_and_never_claims_ledger_verification(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    aggregates = aggregate_verified_evidence(provider_evidence=_cached(provider_fixture))
    assert all(row.analytical_cost_usd > 0 for item in aggregates for row in item.rows)
    assert all(
        row.cost_availability in {"trusted_usage", "retained_worst_case"}
        for item in aggregates
        for row in item.rows
    )
    assert "ledger" not in type(aggregates[0]).model_fields


def test_verified_aggregate_output_characters_match_verified_response_text(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> None:
    evidence = _cached(provider_fixture)
    expected = {
        row.response_id: len(row.raw.output_text)
        for capsule in evidence.generation_evidence
        for row in capsule.scored_attempts
        if row.response_id is not None and row.raw.output_text is not None
    }
    aggregates = aggregate_verified_evidence(provider_evidence=evidence)
    assert all(
        row.output_characters == expected[row.response_id]
        for aggregate in aggregates
        for row in aggregate.rows
        if row.response_id is not None
    )
