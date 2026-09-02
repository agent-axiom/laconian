from __future__ import annotations

import copy
import hashlib
import inspect
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.capsule.canonical import stable_digest

from .helpers import (
    CompleteGenerationContextFixture,
    audit_reviewer_registry,
    build_complete_generation_context_fixture,
    generation_context_index_payload,
    generation_expectation_payload,
    generation_layer_index_payload,
    protocol_reviewer_registry,
)


def _write_synthetic_generation_layer(root: Path) -> object:
    from laconian_eval.benchmark.context import LayerRootIndexV1, write_layer_root_index

    index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    for member in index.members:
        capsule_path = root / member.capsule_relative_path
        capsule_path.mkdir(parents=True)
        sidecar_path = root / member.scored_sidecar_relative_path
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_bytes(b"fixture sidecar\n")
    write_layer_root_index(root, index)
    return index


def test_layer_root_index_binds_kind_campaign_ordered_paths_hashes_and_self_digest() -> None:
    from laconian_eval.benchmark.context import LayerRootIndexV1

    index = LayerRootIndexV1.model_validate(generation_layer_index_payload())

    assert tuple(LayerRootIndexV1.model_fields) == (
        "schema_version",
        "layer_kind",
        "campaign_id",
        "members",
        "layer_root_index_sha256",
    )
    assert tuple(member.ordinal for member in index.members) == tuple(range(36))
    assert index.layer_root_index_sha256 == stable_digest(
        "laconian-benchmark-layer-root-index-v1",
        index.model_dump(mode="json", exclude={"layer_root_index_sha256"}),
    )
    with pytest.raises(ValidationError):
        index.campaign_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize("mutation", ["order", "alias", "wrong_kind", "wrong_digest"])
def test_layer_root_index_rejects_noncanonical_path_order_alias_or_wrong_kind(
    mutation: str,
) -> None:
    from laconian_eval.benchmark.context import LayerRootIndexV1

    payload = generation_layer_index_payload()
    members = payload["members"]
    assert isinstance(members, list)
    if mutation == "order":
        members[0], members[1] = members[1], members[0]
    elif mutation == "alias":
        members[0]["capsule_relative_path"] = "generation/../generation/00/capsule"
    elif mutation == "wrong_kind":
        members[0]["member_kind"] = "hard-score"
    else:
        payload["layer_root_index_sha256"] = "f" * 64
    if mutation != "wrong_digest":
        payload["layer_root_index_sha256"] = stable_digest(
            "laconian-benchmark-layer-root-index-v1",
            {key: value for key, value in payload.items() if key != "layer_root_index_sha256"},
        )

    with pytest.raises(ValidationError):
        LayerRootIndexV1.model_validate(payload)


def test_generation_context_expectation_has_exact_fields_and_self_digest() -> None:
    from laconian_eval.benchmark.context import GenerationContextExpectationV1

    expectation = GenerationContextExpectationV1.model_validate(generation_expectation_payload())

    assert tuple(GenerationContextExpectationV1.model_fields) == (
        "schema_version",
        "campaign_id",
        "campaign_registry_sha256",
        "audit_reviewer_registry_sha256",
        "protocol_reviewer_registry_sha256",
        "protocol_attestations_root",
        "predecessor_authority_root_sha256",
        "generation_layer_root",
        "expected_context_index_sha256",
        "workflow_root",
        "generation_context_expectation_sha256",
    )
    assert expectation.generation_context_expectation_sha256 == stable_digest(
        "laconian-benchmark-generation-context-expectation-v1",
        expectation.model_dump(mode="json", exclude={"generation_context_expectation_sha256"}),
    )


def test_generation_context_index_binds_seed_commit_protocols_registries_and_36_parents() -> None:
    from laconian_eval.benchmark.context import GenerationContextIndexV1, LayerRootIndexV1

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    payload = generation_context_index_payload(root_index)
    context = GenerationContextIndexV1.model_validate(payload)

    assert tuple(GenerationContextIndexV1.model_fields) == (
        "schema_version",
        "campaign_id",
        "campaign_registry_sha256",
        "protocol_attestation_tag_binding_sha256",
        "protocol_attestation_bundle_sha256",
        "protocol_review_object_archive_sha256",
        "object_closure_root",
        "audit_reviewer_registry_sha256",
        "protocol_reviewer_registry_sha256",
        "protocol_attestations_root",
        "campaign_seed",
        "campaign_seed_sha256",
        "input_tag_commit",
        "hard_scorer_source_sha256",
        "hard_score_protocol_sha256",
        "judge_protocol_sha256",
        "judge_prompt_sha256",
        "judge_schema_sha256",
        "judge_requested_service_tier",
        "judge_service_tier_wire_field",
        "corpus_case_root",
        "statistical_protocol_sha256",
        "audit_protocol_sha256",
        "estimand_protocol_sha256",
        "bootstrap_protocol_sha256",
        "outcome_classification_protocol_sha256",
        "false_fail_sensitivity_protocol_sha256",
        "audit_sampling_protocol_sha256",
        "audit_commit_reveal_protocol_sha256",
        "audit_adjudication_protocol_sha256",
        "workflow_root",
        "audit_reviewer_registry",
        "protocol_reviewer_registry",
        "protocol_attestations",
        "generation_root_index_sha256",
        "provider_projection_root",
        "ordered_generation_capsule_sha256s",
        "generation_context_index_sha256",
    )
    assert context.campaign_seed_sha256 == stable_digest(
        "laconian-campaign-seed-v1",
        {
            "schema_version": "1",
            "algorithm": "public-hex-seed-v1",
            "campaign_seed": context.campaign_seed,
        },
    )
    assert context.input_tag_commit == context.protocol_attestations[0].statement.peeled_c0_oid
    assert len(context.ordered_generation_capsule_sha256s) == 36
    assert len(set(context.ordered_generation_capsule_sha256s)) == 36
    assert context.ordered_generation_capsule_sha256s == tuple(
        member.generation_capsule_sha256 for member in root_index.members
    )
    assert context.generation_context_index_sha256 == stable_digest(
        "laconian-benchmark-generation-context-index-v1",
        context.model_dump(mode="json", exclude={"generation_context_index_sha256"}),
    )


def test_generation_layer_member_binds_capsule_and_scored_sidecar_paths_and_hashes() -> None:
    from laconian_eval.benchmark.context import GenerationLayerRootMemberV1, LayerRootIndexV1

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    member = root_index.members[0]
    assert type(member) is GenerationLayerRootMemberV1
    assert tuple(GenerationLayerRootMemberV1.model_fields) == (
        "member_kind",
        "ordinal",
        "generation_model",
        "scenario_uid",
        "capsule_relative_path",
        "generation_capsule_sha256",
        "scored_sidecar_relative_path",
        "scored_sidecar_sha256",
    )
    assert member.capsule_relative_path.startswith("generation/")
    assert member.scored_sidecar_relative_path.startswith("generation/")
    assert member.capsule_relative_path != member.scored_sidecar_relative_path
    assert len(member.generation_capsule_sha256) == 64
    assert len(member.scored_sidecar_sha256) == 64


def test_generation_context_attestations_registries_and_protocols_are_one_coherent_authority() -> (
    None
):
    from laconian_eval.benchmark.context import GenerationContextIndexV1, LayerRootIndexV1
    from laconian_eval.benchmark.protocol_review import compute_protocol_attestations_root

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    context = GenerationContextIndexV1.model_validate(generation_context_index_payload(root_index))
    roles = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )

    assert context.judge_requested_service_tier == "default"
    assert context.judge_service_tier_wire_field == "service_tier"
    assert context.audit_reviewer_registry_sha256 == (
        context.audit_reviewer_registry.audit_reviewer_registry_sha256
    )
    assert context.protocol_reviewer_registry_sha256 == (
        context.protocol_reviewer_registry.protocol_reviewer_registry_sha256
    )
    assert context.protocol_attestations_root == compute_protocol_attestations_root(
        context.protocol_attestations
    )
    assert tuple(item.statement.role for item in context.protocol_attestations) == roles
    assert tuple(item.role for item in context.protocol_reviewer_registry.reviewers) == roles
    assert all(
        attestation.statement.protocol_registry_sha256 == context.protocol_reviewer_registry_sha256
        for attestation in context.protocol_attestations
    )
    assert all(
        attestation.statement.workflow_root == context.workflow_root
        and attestation.statement.peeled_c0_oid == context.input_tag_commit
        for attestation in context.protocol_attestations
    )
    assert all(
        attestation.statement.reviewer_numeric_account_id == reviewer.reviewer_numeric_account_id
        and attestation.statement.reviewer_login == reviewer.reviewer_login
        and attestation.signature_evidence.verification_mode == reviewer.verification_mode
        for attestation, reviewer in zip(
            context.protocol_attestations,
            context.protocol_reviewer_registry.reviewers,
            strict=True,
        )
    )


def test_reviewer_registry_hashes_recompute_from_distinct_exact_canonical_bytes() -> None:
    from laconian_eval.benchmark.protocol_review import (
        canonical_protocol_reviewer_registry_bytes,
        canonical_reviewer_registry_bytes,
        compute_audit_reviewer_registry_sha256,
        compute_protocol_reviewer_registry_sha256,
    )

    audit = audit_reviewer_registry()
    protocol = protocol_reviewer_registry()
    audit_bytes = canonical_reviewer_registry_bytes(audit.reviewers)
    protocol_bytes = canonical_protocol_reviewer_registry_bytes(protocol.reviewers)

    assert audit_bytes != protocol_bytes
    assert not audit_bytes.endswith(b"\n")
    assert not protocol_bytes.endswith(b"\n")
    assert hashlib.sha256(audit_bytes).hexdigest() == compute_audit_reviewer_registry_sha256(
        audit.reviewers
    )
    assert compute_audit_reviewer_registry_sha256(audit.reviewers) == (
        audit.audit_reviewer_registry_sha256
    )
    assert hashlib.sha256(protocol_bytes).hexdigest() == (
        compute_protocol_reviewer_registry_sha256(protocol.reviewers)
    )
    assert compute_protocol_reviewer_registry_sha256(protocol.reviewers) == (
        protocol.protocol_reviewer_registry_sha256
    )
    assert (
        canonical_json_v1(
            {
                "schema_version": audit.schema_version,
                "reviewers": [item.model_dump(mode="json") for item in audit.reviewers],
            }
        )
        == audit_bytes
    )


def test_protocol_reviewer_registry_freezes_role_order_modes_and_ascii_identities() -> None:
    from laconian_eval.benchmark.protocol_review import ProtocolReviewerRegistryV1

    registry = protocol_reviewer_registry()
    assert tuple(item.role for item in registry.reviewers) == (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    assert tuple(item.verification_mode for item in registry.reviewers) == (
        "github_verified_commit",
        "ssh_sha256",
        "openpgp_fingerprint",
    )
    assert registry.reviewers[0].signing_fingerprint is None
    assert registry.reviewers[2].signing_fingerprint is not None
    payload = registry.model_dump(mode="json")
    payload["reviewers"][0], payload["reviewers"][1] = (
        payload["reviewers"][1],
        payload["reviewers"][0],
    )
    with pytest.raises(ValidationError):
        ProtocolReviewerRegistryV1.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_tag_commit", b"a" * 40),
        ("input_tag_commit", bytes.fromhex("ab" * 20)),
        ("campaign_id", True),
        ("campaign_id", 7),
        ("campaign_seed", False),
    ],
)
def test_generation_context_rejects_bytes_bool_or_integer_scalar_coercion(
    field: str,
    value: object,
) -> None:
    from laconian_eval.benchmark.context import GenerationContextIndexV1, LayerRootIndexV1

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    payload = generation_context_index_payload(root_index)
    payload[field] = value
    payload["generation_context_index_sha256"] = "f" * 64
    with pytest.raises(ValidationError):
        GenerationContextIndexV1.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "hard_score_protocol_sha256",
        "judge_prompt_sha256",
        "judge_schema_sha256",
        "statistical_protocol_sha256",
        "workflow_root",
        "protocol_reviewer_registry_sha256",
        "audit_reviewer_registry_sha256",
    ],
)
def test_generation_context_rejects_rehashed_protocol_registry_or_workflow_substitution(
    field: str,
) -> None:
    from laconian_eval.benchmark.context import GenerationContextIndexV1, LayerRootIndexV1

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    payload = generation_context_index_payload(root_index)
    payload[field] = "f" * 64
    payload["generation_context_index_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-index-v1",
        {key: value for key, value in payload.items() if key != "generation_context_index_sha256"},
    )
    with pytest.raises(ValidationError):
        GenerationContextIndexV1.model_validate(payload)


def test_protocol_bindings_are_the_exact_context_projection_including_singular_audit() -> None:
    from laconian_eval.benchmark.context import (
        BenchmarkProtocolBindingsV1,
        GenerationContextIndexV1,
        LayerRootIndexV1,
        protocol_bindings_from_context,
    )

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    context = GenerationContextIndexV1.model_validate(generation_context_index_payload(root_index))
    projection = protocol_bindings_from_context(context)
    assert tuple(type(projection).model_fields) == tuple(BenchmarkProtocolBindingsV1.model_fields)
    assert projection.audit_protocol_sha256 == context.audit_protocol_sha256
    assert projection.model_dump(mode="json") == {
        name: getattr(context, name) for name in BenchmarkProtocolBindingsV1.model_fields
    }


def test_verified_expectation_requires_a_lowercase_bound_final_authority_root() -> None:
    from laconian_eval.benchmark.context import (
        GenerationContextExpectationV1,
        VerifiedGenerationContextExpectationV1,
    )

    expectation = GenerationContextExpectationV1.model_validate(generation_expectation_payload())
    verified = VerifiedGenerationContextExpectationV1(expectation, "a" * 64)
    assert verified.expectation == expectation
    with pytest.raises((TypeError, ValueError)):
        VerifiedGenerationContextExpectationV1(expectation, "A" * 64)


def test_context_public_loaders_have_no_raw_expected_digest_or_campaign_override() -> None:
    from laconian_eval.benchmark.context import (
        load_layer_root_index,
        load_verified_generation_context_index,
        write_generation_context_index,
        write_layer_root_index,
    )

    assert tuple(inspect.signature(write_layer_root_index).parameters) == ("root", "index")
    assert tuple(inspect.signature(load_layer_root_index).parameters) == ("root", "expected_kind")
    assert tuple(inspect.signature(write_generation_context_index).parameters) == (
        "generation_index_path",
        "index",
    )
    assert tuple(inspect.signature(load_verified_generation_context_index).parameters) == (
        "generation_index_path",
        "generation_root",
        "expectation",
    )


def test_context_module_has_no_campaign_or_downstream_imports() -> None:
    import laconian_eval.benchmark.context as context_module

    source = inspect.getsource(context_module)
    assert "laconian_eval.campaign" not in source
    assert "benchmark.hard_score" not in source
    assert "benchmark.judge" not in source
    assert "benchmark.provider_evidence" not in source


def test_layer_root_index_writer_loader_use_fixed_tree_and_never_replace(tmp_path: Path) -> None:
    from laconian_eval.benchmark.context import (
        load_layer_root_index,
        write_layer_root_index,
    )

    index = _write_synthetic_generation_layer(tmp_path)
    index_path = tmp_path / "generation/index.json"
    assert index_path.read_bytes().endswith(b"\n")
    assert not index_path.read_bytes().endswith(b"\n\n")
    assert load_layer_root_index(tmp_path, expected_kind="generation") == index
    before = index_path.read_bytes()
    with pytest.raises(FileExistsError):
        write_layer_root_index(tmp_path, index)
    assert index_path.read_bytes() == before


def test_layer_root_loader_rejects_generation_root_symlink_alias(tmp_path: Path) -> None:
    from laconian_eval.benchmark.context import load_layer_root_index

    real_root = tmp_path / "real-generation-root"
    real_root.mkdir()
    _write_synthetic_generation_layer(real_root)
    aliased_root = tmp_path / "aliased-generation-root"
    aliased_root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(ValueError):
        load_layer_root_index(aliased_root, expected_kind="generation")


def test_layer_root_loader_rejects_symlinked_ancestor_alias(tmp_path: Path) -> None:
    from laconian_eval.benchmark.context import load_layer_root_index

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    real_root = real_parent / "generation-root"
    real_root.mkdir()
    _write_synthetic_generation_layer(real_root)
    aliased_parent = tmp_path / "aliased-parent"
    aliased_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError):
        load_layer_root_index(
            aliased_parent / "generation-root",
            expected_kind="generation",
        )


def test_layer_root_writer_rejects_symlinked_layer_directory(tmp_path: Path) -> None:
    from laconian_eval.benchmark.context import LayerRootIndexV1, write_layer_root_index

    root = tmp_path / "generation-root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "generation").symlink_to(outside, target_is_directory=True)
    index = LayerRootIndexV1.model_validate(generation_layer_index_payload())

    with pytest.raises(ValueError):
        write_layer_root_index(root, index)

    assert not (outside / "index.json").exists()


def test_generation_context_writer_rejects_symlinked_parent_alias(tmp_path: Path) -> None:
    from laconian_eval.benchmark.context import (
        GenerationContextIndexV1,
        LayerRootIndexV1,
        write_generation_context_index,
    )

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    context = GenerationContextIndexV1.model_validate(generation_context_index_payload(root_index))
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    aliased_parent = tmp_path / "aliased-parent"
    aliased_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError):
        write_generation_context_index(aliased_parent / "generation-context.json", context)

    assert not (real_parent / "generation-context.json").exists()


def test_layer_root_loader_rejects_single_external_hardlink_alias(tmp_path: Path) -> None:
    from laconian_eval.benchmark.context import load_layer_root_index

    generation_root = tmp_path / "generation-root"
    generation_root.mkdir()
    index = _write_synthetic_generation_layer(generation_root)
    declared_sidecar = generation_root / index.members[0].scored_sidecar_relative_path
    external_alias = tmp_path / "external-sidecar-alias.json"
    os.link(declared_sidecar, external_alias)
    assert declared_sidecar.stat().st_nlink == 2

    with pytest.raises(ValueError):
        load_layer_root_index(generation_root, expected_kind="generation")


def test_layer_root_loader_rejects_lstat_to_read_inode_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.context as context_module

    generation_root = tmp_path / "generation-root"
    generation_root.mkdir()
    _write_synthetic_generation_layer(generation_root)
    index_path = generation_root / "generation/index.json"
    original_read_descriptor_bytes = context_module._read_descriptor_bytes
    swapped = False

    def swap_then_read(descriptor: int, *, limit: int) -> bytes:
        nonlocal swapped
        if not swapped:
            original_bytes = index_path.read_bytes()
            replacement = index_path.with_name("replacement-index.json")
            replacement.write_bytes(original_bytes)
            os.replace(replacement, index_path)
            swapped = True
        return original_read_descriptor_bytes(descriptor, limit=limit)

    monkeypatch.setattr(context_module, "_read_descriptor_bytes", swap_then_read)
    with pytest.raises(ValueError):
        context_module.load_layer_root_index(generation_root, expected_kind="generation")
    assert swapped


def test_layer_root_loader_rejects_index_swap_after_canonical_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.context as context_module

    generation_root = tmp_path / "generation-root"
    generation_root.mkdir()
    _write_synthetic_generation_layer(generation_root)
    index_path = generation_root / "generation/index.json"
    original_validate_layer_tree = context_module._validate_layer_tree
    swapped = False

    def swap_then_validate(root_descriptor: int, index: object) -> None:
        nonlocal swapped
        original_bytes = index_path.read_bytes()
        replacement = index_path.with_name("replacement-index.json")
        replacement.write_bytes(original_bytes)
        os.replace(replacement, index_path)
        swapped = True
        original_validate_layer_tree(root_descriptor, index)

    monkeypatch.setattr(context_module, "_validate_layer_tree", swap_then_validate)
    with pytest.raises(ValueError):
        context_module.load_layer_root_index(generation_root, expected_kind="generation")
    assert swapped


def test_layer_root_loader_rejects_oversize_index_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.context as context_module
    from laconian_eval.benchmark.context import load_layer_root_index
    from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

    generation_root = tmp_path / "generation-root"
    generation_root.mkdir()
    _write_synthetic_generation_layer(generation_root)
    index_path = generation_root / "generation/index.json"
    with index_path.open("r+b") as handle:
        handle.truncate(RESOURCE_LIMITS_V1.mutable_capsule_bytes + 1)

    def full_read_must_not_run(_descriptor: int, *, limit: int) -> bytes:
        assert limit == RESOURCE_LIMITS_V1.mutable_capsule_bytes
        raise AssertionError("oversize index was read")

    monkeypatch.setattr(context_module, "_read_descriptor_bytes", full_read_must_not_run)
    with pytest.raises(ValueError, match="resource limit"):
        load_layer_root_index(generation_root, expected_kind="generation")


def test_generation_context_loader_rejects_oversize_context_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.context as context_module
    from laconian_eval.benchmark.context import (
        GenerationContextExpectationV1,
        VerifiedGenerationContextExpectationV1,
        load_verified_generation_context_index,
    )
    from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

    generation_root = tmp_path / "GENERATION"
    generation_root.mkdir()
    context_path = generation_root / "generation-context.json"
    with context_path.open("w+b") as handle:
        handle.truncate(RESOURCE_LIMITS_V1.mutable_capsule_bytes + 1)
    expectation = GenerationContextExpectationV1.model_validate(generation_expectation_payload())
    verified = VerifiedGenerationContextExpectationV1(expectation, "a" * 64)

    def full_read_must_not_run(_descriptor: int, *, limit: int) -> bytes:
        assert limit == RESOURCE_LIMITS_V1.mutable_capsule_bytes
        raise AssertionError("oversize context was read")

    monkeypatch.setattr(context_module, "_read_descriptor_bytes", full_read_must_not_run)
    with pytest.raises(ValueError, match="resource limit"):
        load_verified_generation_context_index(
            generation_index_path=context_path,
            generation_root=generation_root,
            expectation=verified,
        )


def test_retained_snapshot_rejects_oversize_sidecar_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.context as context_module
    from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

    generation_root = tmp_path / "GENERATION"
    sidecar_path = generation_root / "generation/00/scored.json"
    sidecar_path.parent.mkdir(parents=True)
    with sidecar_path.open("w+b") as handle:
        handle.truncate(RESOURCE_LIMITS_V1.mutable_capsule_bytes + 1)
    descriptor, _identity = context_module._open_retained_directory(generation_root)
    try:
        def full_read_must_not_run(_descriptor: int, *, limit: int) -> bytes:
            assert limit == RESOURCE_LIMITS_V1.mutable_capsule_bytes
            raise AssertionError("oversize sidecar was read")

        monkeypatch.setattr(context_module, "_read_descriptor_bytes", full_read_must_not_run)
        with pytest.raises(ValueError, match="resource limit"):
            context_module._stable_regular_file_snapshot(descriptor, "generation/00/scored.json")
    finally:
        os.close(descriptor)


def test_sidecar_reconstruction_accepts_real_nonterminal_retry_raw_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sealed raw journal can contain retry rows absent from the terminal projection."""

    import laconian_eval.capsule.execution as execution_module
    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes
    from laconian_eval.capsule.execution import ProviderFactory
    from laconian_eval.capsule.finalize import finalize_capsule
    from laconian_eval.capsule.sidecars import (
        load_verified_scored_capsule,
        write_scored_sidecar,
    )
    from laconian_eval.providers import GenerationResult, ProviderError, TokenUsage
    from tests.capsule.test_execution import (
        _SECRET,
        _install_fast_runtime,
        _ScriptedProvider,
        _seams_for_provider,
        _single_plan_capsule,
    )

    capsule = _single_plan_capsule(tmp_path, monkeypatch, max_transient_retries=1)
    _install_fast_runtime(monkeypatch)
    provider = _ScriptedProvider(
        [
            ProviderError(
                "transient",
                f"retry safely {_SECRET}",
                True,
                delivery_certainty="definitely_not_sent",
                response_model="returned-retry-v1",
                request_id="request-retry",
                usage=TokenUsage(3, 0, 3),
            ),
            GenerationResult(
                output_text="retry succeeded",
                response_model="returned-success-v2",
                request_id="request-success",
                usage=TokenUsage(3, 2, 5, cached_input_tokens=1),
            ),
            ProviderError(
                "transient",
                f"retry safely {_SECRET}",
                True,
                delivery_certainty="definitely_not_sent",
                response_model="returned-retry-v1",
                request_id="request-retry",
                usage=TokenUsage(3, 0, 3),
            ),
            GenerationResult(
                output_text="retry succeeded",
                response_model="returned-success-v2",
                request_id="request-success",
                usage=TokenUsage(3, 2, 5, cached_input_tokens=1),
            ),
        ]
    )
    outcome = execution_module._resume_capsule(
        capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider, credential_values=(_SECRET,)),
    )
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len((capsule / "raw.jsonl").read_bytes().splitlines()) == 4
    assert finalize_capsule(capsule).state == "SEALED_COMPLETE"
    sidecar_path = tmp_path / "retry-sidecar.json"
    write_scored_sidecar(capsule, sidecar_path)
    evidence = load_verified_scored_capsule(capsule, sidecar_path)

    assert _reconstruct_scored_sidecar_bytes(evidence).sidecar_bytes == sidecar_path.read_bytes()


def _verified_expectation_for_context(context: object, root_index: object) -> object:
    from laconian_eval.benchmark.context import (
        GenerationContextExpectationV1,
        VerifiedGenerationContextExpectationV1,
    )

    payload = generation_expectation_payload(
        campaign_id=context.campaign_id,  # type: ignore[attr-defined]
        generation_layer_root=root_index.layer_root_index_sha256,  # type: ignore[attr-defined]
        expected_context_index_sha256=context.generation_context_index_sha256,  # type: ignore[attr-defined]
    )
    payload.update(
        campaign_registry_sha256=context.campaign_registry_sha256,  # type: ignore[attr-defined]
        audit_reviewer_registry_sha256=context.audit_reviewer_registry_sha256,  # type: ignore[attr-defined]
        protocol_reviewer_registry_sha256=context.protocol_reviewer_registry_sha256,  # type: ignore[attr-defined]
        protocol_attestations_root=context.protocol_attestations_root,  # type: ignore[attr-defined]
        workflow_root=context.workflow_root,  # type: ignore[attr-defined]
    )
    payload["generation_context_expectation_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-expectation-v1",
        {
            key: value
            for key, value in payload.items()
            if key != "generation_context_expectation_sha256"
        },
    )
    return VerifiedGenerationContextExpectationV1(
        expectation=GenerationContextExpectationV1.model_validate(payload),
        bound_generation_complete_authority_root_sha256="e" * 64,
    )


@pytest.fixture(scope="module")
def complete_generation_context_tree(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[CompleteGenerationContextFixture]:
    monkeypatch = pytest.MonkeyPatch()
    try:
        yield build_complete_generation_context_fixture(
            tmp_path_factory.mktemp("task3-complete-generation-context"),
            monkeypatch,
        )
    finally:
        monkeypatch.undo()


def test_context_loader_verifies_all_36_real_sealed_generation_parents(
    complete_generation_context_tree: CompleteGenerationContextFixture,
) -> None:
    from laconian_eval.benchmark.context import load_verified_generation_context_index
    from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2

    fixture = complete_generation_context_tree
    verified = load_verified_generation_context_index(
        generation_index_path=fixture.generation_index_path,
        generation_root=fixture.generation_root,
        expectation=fixture.expectation,
    )

    assert len(verified.generation_evidence) == 36
    assert all(type(item) is VerifiedScoredCapsuleV2 for item in verified.generation_evidence)
    assert all(item.seal.generation_status == "complete" for item in verified.generation_evidence)
    assert len({item.capsule_sha256 for item in verified.generation_evidence}) == 36
    assert {
        (item.manifest.provider.model, next(iter({row.scenario_uid for row in item.plan})))
        for item in verified.generation_evidence
    } == {(member.generation_model, member.scenario_uid) for member in verified.root_index.members}
    assert {item.manifest.provider.model for item in verified.generation_evidence} == {
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    }
    assert sorted(len(item.plan) for item in verified.generation_evidence) == [2] * 35 + [40]


@pytest.mark.parametrize("mutation", ("corrupt_sidecar", "remove_seal"))
def test_context_loader_rejects_invalid_nonselected_parent_at_ordinal_35(
    complete_generation_context_tree: CompleteGenerationContextFixture,
    mutation: str,
) -> None:
    from laconian_eval.benchmark.context import load_verified_generation_context_index

    fixture = complete_generation_context_tree
    member = fixture.root_index.members[35]
    assert member.ordinal != fixture.selected_ordinal
    target = (
        fixture.generation_root / member.scored_sidecar_relative_path
        if mutation == "corrupt_sidecar"
        else fixture.generation_root / member.capsule_relative_path / "seal.json"
    )
    original = target.read_bytes()
    try:
        if mutation == "corrupt_sidecar":
            target.write_bytes(original + b"corrupt")
        else:
            target.unlink()
        with pytest.raises(ValueError):
            load_verified_generation_context_index(
                generation_index_path=fixture.generation_index_path,
                generation_root=fixture.generation_root,
                expectation=fixture.expectation,
            )
    finally:
        target.write_bytes(original)


def test_context_loader_uses_external_expected_digest_before_parsing_parent_authority(
    tmp_path: Path,
) -> None:
    from laconian_eval.benchmark.context import (
        GenerationContextIndexV1,
        LayerRootIndexV1,
        VerifiedGenerationContextExpectationV1,
        load_verified_generation_context_index,
        write_generation_context_index,
    )

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    context = GenerationContextIndexV1.model_validate(generation_context_index_payload(root_index))
    verified = _verified_expectation_for_context(context, root_index)
    assert isinstance(verified, VerifiedGenerationContextExpectationV1)
    generation_root = tmp_path / "GENERATION"
    generation_root.mkdir()
    context_path = generation_root / "generation-context.json"
    write_generation_context_index(context_path, context)

    forged_payload = verified.expectation.model_dump(mode="json")
    forged_payload["expected_context_index_sha256"] = "f" * 64
    forged_payload["generation_context_expectation_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-expectation-v1",
        {
            key: value
            for key, value in forged_payload.items()
            if key != "generation_context_expectation_sha256"
        },
    )
    forged = VerifiedGenerationContextExpectationV1(
        expectation=type(verified.expectation).model_validate(forged_payload),
        bound_generation_complete_authority_root_sha256=(
            verified.bound_generation_complete_authority_root_sha256
        ),
    )
    with pytest.raises(ValueError, match="external expectation"):
        load_verified_generation_context_index(
            generation_index_path=context_path,
            generation_root=generation_root,
            expectation=forged,
        )


def test_context_loader_rejects_campaign_registry_substitution_against_retained_wrapper(
    tmp_path: Path,
) -> None:
    from laconian_eval.benchmark.attachments import write_attachment_json
    from laconian_eval.benchmark.context import (
        GenerationContextIndexV1,
        LayerRootIndexV1,
        load_verified_generation_context_index,
    )

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    context = GenerationContextIndexV1.model_validate(generation_context_index_payload(root_index))
    verified = _verified_expectation_for_context(context, root_index)
    forged_context = copy.deepcopy(context.model_dump(mode="json"))
    forged_context["campaign_registry_sha256"] = "f" * 64
    forged_context["generation_context_index_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-index-v1",
        {
            key: value
            for key, value in forged_context.items()
            if key != "generation_context_index_sha256"
        },
    )
    generation_root = tmp_path / "GENERATION"
    generation_root.mkdir()
    context_path = generation_root / "generation-context.json"
    write_attachment_json(context_path, forged_context)
    with pytest.raises(ValueError, match="external expectation"):
        load_verified_generation_context_index(
            generation_index_path=context_path,
            generation_root=generation_root,
            expectation=verified,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "campaign_seed",
        "input_tag_commit",
        "hard_scorer_source_sha256",
        "hard_score_protocol_sha256",
        "judge_protocol_sha256",
        "generation_member",
        "workflow_root",
    ),
)
def test_context_loader_rejects_rehashed_seed_commit_code_protocol_member_or_workflow_substitution(
    tmp_path: Path,
    mutation: str,
) -> None:
    from laconian_eval.benchmark.attachments import write_attachment_json
    from laconian_eval.benchmark.context import (
        GenerationContextIndexV1,
        LayerRootIndexV1,
        load_verified_generation_context_index,
    )

    root_index = LayerRootIndexV1.model_validate(generation_layer_index_payload())
    context = GenerationContextIndexV1.model_validate(generation_context_index_payload(root_index))
    verified = _verified_expectation_for_context(context, root_index)
    forged_payload = copy.deepcopy(context.model_dump(mode="json"))
    if mutation == "campaign_seed":
        forged_payload["campaign_seed"] = "f" * 64
        forged_payload["campaign_seed_sha256"] = stable_digest(
            "laconian-campaign-seed-v1",
            {
                "schema_version": "1",
                "algorithm": "public-hex-seed-v1",
                "campaign_seed": forged_payload["campaign_seed"],
            },
        )
    elif mutation == "input_tag_commit":
        forged_payload[mutation] = "f" * 40
    elif mutation == "generation_member":
        capsule_hashes = list(forged_payload["ordered_generation_capsule_sha256s"])
        capsule_hashes[-1] = "f" * 64
        forged_payload["ordered_generation_capsule_sha256s"] = capsule_hashes
    else:
        forged_payload[mutation] = "f" * 64
    forged_payload["generation_context_index_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-index-v1",
        {
            key: value
            for key, value in forged_payload.items()
            if key != "generation_context_index_sha256"
        },
    )
    assert forged_payload["generation_context_index_sha256"] != (
        verified.expectation.expected_context_index_sha256
    )
    generation_root = tmp_path / "GENERATION"
    generation_root.mkdir()
    context_path = generation_root / "generation-context.json"
    write_attachment_json(context_path, forged_payload)

    with pytest.raises(ValueError, match="external expectation"):
        load_verified_generation_context_index(
            generation_index_path=context_path,
            generation_root=generation_root,
            expectation=verified,
        )


def test_runtime_adapter_can_import_capsule_then_public_context_without_cycle() -> None:
    repository_root = Path(__file__).parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            ("import laconian_eval.capsule.attempts; import laconian_eval.benchmark.context"),
        ],
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
