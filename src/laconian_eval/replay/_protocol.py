"""Pure structural replay of archived protocol bytes, without live authority.

The raw Pydantic attestations below are serialized records, not verified DAG
capabilities. This module never validates the active runtime or invokes a keyed
signature verifier. It reconstructs their retained byte bindings and API
projections and joins them to the caller's raw generation context.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TypeVar

import yaml
from pydantic import BaseModel

from laconian_eval.benchmark import protocol_review as pr
from laconian_eval.benchmark.attachments import canonical_json_v1, parse_canonical_json_v1
from laconian_eval.benchmark.context import GenerationContextIndexV1

_Model = TypeVar("_Model", bound=BaseModel)
_Objects = Mapping[str, pr.ParsedProtocolGitObjectV1]
_Tree = Mapping[str, tuple[str, str]]
_ERROR = "invalid protocol archive"


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError(_ERROR)


def _canonical_model(raw: bytes, model_type: type[_Model]) -> _Model:
    model = model_type.model_validate(parse_canonical_json_v1(raw))
    _require(canonical_json_v1(model.model_dump(mode="json")) == raw)
    return model


def _c0_model(tree: _Tree, objects: _Objects, path: str, model_type: type[_Model]) -> _Model:
    return _canonical_model(pr._c0_blob(tree, objects, path), model_type)


def _hashed_model(
    payload: dict[str, object], model_type: type[_Model], field: str, domain: str
) -> _Model:
    payload[field] = pr.protocol_review_digest(domain, payload)
    return model_type.model_validate(payload)


def _identity_registry(
    tree: _Tree, objects: _Objects, reviewers: pr.ProtocolReviewerRegistryV1
) -> pr.ProtocolReviewIdentityRegistryBundleV1:
    identity = _c0_model(
        tree,
        objects,
        "benchmark/security/protocol-review-identity-registry.json",
        pr.ProtocolReviewIdentityRegistryBundleV1,
    )
    for path, digest in (
        (identity.verifier_source_path, identity.verifier_source_sha256),
        (identity.dependency_lock_path, identity.dependency_lock_sha256),
    ):
        _require(hashlib.sha256(pr._c0_blob(tree, objects, path)).hexdigest() == digest)
    keyed = tuple(
        item for item in reviewers.reviewers if item.verification_mode != "github_verified_commit"
    )
    _require(len(keyed) == len(identity.keys))
    for reviewer, key in zip(keyed, identity.keys, strict=True):
        _require(
            (
                key.role,
                key.reviewer_numeric_account_id,
                key.reviewer_login,
                key.verification_mode,
                key.fingerprint,
            )
            == (
                reviewer.role,
                reviewer.reviewer_numeric_account_id,
                reviewer.reviewer_login,
                reviewer.verification_mode,
                reviewer.signing_fingerprint,
            )
        )
        _require(
            pr._signing_key_fingerprint(
                key.verification_mode, pr._decode_canonical_base64(key.public_key_base64)
            )
            == key.fingerprint
        )
    return identity


def _signature_projection(
    binding: pr.ArchivedApiReceiptBindingV1,
    blobs: Mapping[str, pr.ArchivedApiBlobV1],
    commit: pr.ParsedProtocolGitObjectV1,
    parent: pr.ParsedProtocolGitObjectV1,
    attestation: pr.VerifiedProtocolAttestationV1,
    reviewer: pr.ProtocolReviewerBindingV1,
    identity: pr.ProtocolReviewIdentityRegistryBundleV1,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
) -> None:
    """Reconstruct stable provider projections and local receipt byte bindings."""
    receipt = binding.receipt
    _require(type(receipt) is pr.GitHubSignatureObservationReceiptV1)
    assert isinstance(receipt, pr.GitHubSignatureObservationReceiptV1)
    _require(receipt.repository_id == repository_id and receipt.commit_oid == commit.oid)
    _require(len(binding.raw_blob_paths) == len(binding.canonical_blob_paths) == 2)
    raw_rest, raw_graphql = (
        pr._decode_canonical_base64(blobs[path].raw_bytes_base64) for path in binding.raw_blob_paths
    )
    view, payload, signature = pr._validate_review_commit(
        commit,
        parent_oid=parent.oid,
        reviewer=reviewer,
        statement=attestation.statement,
        input_tag_ref=attestation.statement.input_tag_ref,
    )
    rest_raw = pr._parse_provider_json(raw_rest)
    verification = pr._selected_object(rest_raw["verification"], "verification")
    rest = _hashed_model(
        {
            "schema_version": "GitHubCommitVerificationProjectionV1",
            "repository_id": repository_id,
            "commit_oid": rest_raw["sha"],
            "api_version": "2022-11-28",
            "endpoint": f"GET /repos/{repository_owner}/{repository_name}/git/commits/{commit.oid}",
            "verified": verification["verified"],
            "reason": verification["reason"],
            "payload": verification["payload"],
            "signature": verification["signature"],
            "verified_at": pr._provider_verified_at(verification["verified_at"]).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
        },
        pr.GitHubCommitVerificationProjectionV1,
        "rest_projection_sha256",
        "laconian-github-commit-verification-projection-v1",
    )
    graphql_raw = pr._parse_provider_json(raw_graphql)
    _require("errors" not in graphql_raw)
    data = pr._selected_object(graphql_raw["data"], "data")
    repository = pr._selected_object(data["repository"], "repository")
    obj = pr._selected_object(repository["object"], "object")
    sig = pr._selected_object(obj["signature"], "signature")
    signer = pr._selected_object(sig["signer"], "signer")
    graphql = _hashed_model(
        {
            "schema_version": "GitHubSignatureProjectionV1",
            "repository_id": repository["databaseId"],
            "commit_oid": obj["oid"],
            "query_sha256": pr.GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
            "signer_database_id": signer["databaseId"],
            "signer_login": signer["login"],
            "is_valid": sig["isValid"],
            "state": sig["state"],
        },
        pr.GitHubSignatureProjectionV1,
        "graphql_projection_sha256",
        "laconian-github-signature-projection-v1",
    )
    evidence = attestation.signature_evidence
    _require(
        rest == evidence.github_rest_verification
        and graphql == evidence.github_graphql_signature
        and rest.commit_oid == commit.oid
        and graphql.repository_id == repository_id
        and graphql.signer_database_id == reviewer.reviewer_numeric_account_id
        and graphql.signer_login == reviewer.reviewer_login
        and rest.payload == payload.decode("utf-8", errors="strict")
        and rest.signature == signature.decode("utf-8", errors="strict")
        and evidence.commit_oid == commit.oid
        and evidence.commit_object_sha256 == commit.git_object_sha256
        and evidence.parent_commit_oid == parent.oid
        and evidence.verification_mode == reviewer.verification_mode
        and receipt.rest_projection_sha256 == rest.rest_projection_sha256
        and receipt.graphql_projection_sha256 == graphql.graphql_projection_sha256
    )
    for path, projection in zip(binding.canonical_blob_paths, (rest, graphql), strict=True):
        _require(
            pr._decode_canonical_base64(blobs[path].raw_bytes_base64)
            == canonical_json_v1(projection.model_dump(mode="json"))
        )
    if isinstance(evidence, pr.GitHubVerifiedCommitEvidenceV1):
        pr._validate_github_signature_armor(signature)
    else:
        keys = tuple(key for key in identity.keys if key.role == reviewer.role)
        _require(len(keys) == 1)
        key = keys[0]
        local = evidence.local_signature_verification
        _require(
            evidence.fingerprint == key.fingerprint
            and evidence.keyring_sha256 == key.public_key_sha256
            and local.signed_payload_sha256 == hashlib.sha256(view.signed_payload).hexdigest()
            and local.signature_sha256 == hashlib.sha256(signature).hexdigest()
            and local.verifier_tool_sha256 == identity.protocol_signature_verifier_tool_sha256
        )


def _validate_archive(
    archive: pr.ProtocolReviewObjectArchiveV1, context: GenerationContextIndexV1
) -> None:
    _require(
        archive.protocol_review_object_archive_sha256
        == context.protocol_review_object_archive_sha256
        and archive.object_closure_root == context.object_closure_root
    )
    for blob in archive.api_blobs:
        if blob.kind == "safe_raw_response":
            pr._validate_safe_raw_body(pr._decode_canonical_base64(blob.raw_bytes_base64))
    objects = pr._object_map(
        tuple(
            pr.parse_protocol_git_object(
                oid=item.oid,
                object_type=item.type,
                raw_content=pr._decode_canonical_base64(item.raw_content_base64),
            )
            for item in archive.objects
        )
    )
    input_ref = context.protocol_attestations[0].statement.input_tag_ref
    input_tag, input_view = pr._tag_object_for_ref(input_ref, objects)
    input_message = _canonical_model(input_view.message[:-1], pr.InputTagMessageV1)
    _require(input_view.message == canonical_json_v1(input_message.model_dump(mode="json")) + b"\n")
    c0 = objects[input_view.target_oid]
    _require(c0.oid == context.input_tag_commit == input_message.peeled_c0_oid)
    tree = pr._flatten_tree(pr._parse_commit_view(c0).tree_oid, objects)
    review_root = f"benchmarks/protocol-reviews/{input_view.tag_name}/"
    _require(not any(path.startswith(review_root) for path in tree))
    registry = pr._reconstruct_reviewer_registry(input_tag_ref=input_ref, c0=c0, objects=objects)
    _require(registry == context.protocol_reviewer_registry)
    operator = _c0_model(
        tree, objects, "benchmark/security/tag-operator-registry.json", pr.TagOperatorRegistryV1
    )
    policy = _c0_model(
        tree, objects, "benchmark/security/tag-ruleset-policy.json", pr.TagRulesetPolicyV1
    )
    pr._validate_c0_registry_members(
        flattened=tree,
        objects=objects,
        protocol_reviewer_registry=registry,
        tag_operator_registry=operator,
        tag_ruleset_policy=policy,
    )
    audit_raw = pr._c0_blob(
        tree, objects, "benchmarks/campaigns/public-three-model-v1/audit-reviewers.yaml"
    )
    audit = pr.AuditReviewerRegistryV1.model_validate(
        yaml.load(audit_raw.decode("utf-8", errors="strict"), Loader=pr._UniqueKeySafeLoader)
    )
    _require(audit == context.audit_reviewer_registry)
    identity = _identity_registry(tree, objects, registry)
    workflow_root = pr._workflow_root_from_c0(c0, objects)
    _require(
        input_message.input_tag_ref == input_ref
        and input_message.protocol_reviewer_registry_sha256
        == registry.protocol_reviewer_registry_sha256
        and input_message.tag_operator_registry_sha256 == operator.tag_operator_registry_sha256
        and input_message.tag_ruleset_policy_root == policy.tag_ruleset_policy_root
        and input_message.workflow_root == workflow_root == context.workflow_root
        and operator.repository_id == policy.repository_id
        and policy.rulesets[0].bypass_actors[0].actor_id
        == operator.operators[0].operator_account_id
    )
    pr._validate_tagger(input_view.tagger, operator.operators[0])
    chain = pr._commit_chain(c0.oid, objects, length=4)
    attestations, bundle = pr._parse_b0_payloads(chain[2], chain[3], objects, input_ref)
    _require(attestations == context.protocol_attestations)
    _require(
        bundle.protocol_attestation_bundle_sha256 == context.protocol_attestation_bundle_sha256
        and bundle.protocol_attestations_root == context.protocol_attestations_root
        and bundle.input_tag_oid == input_tag.oid
        and bundle.input_tag_object_sha256 == input_tag.git_object_sha256
        and bundle.peeled_c0_oid == c0.oid
        and bundle.peeled_c0_sha256 == c0.git_object_sha256
        and bundle.workflow_root == workflow_root
        and bundle.protocol_registry_sha256 == registry.protocol_reviewer_registry_sha256
    )
    github = tuple(item for item in archive.api_receipts if item.receipt_kind == "github_signature")
    by_commit = {
        item.receipt.commit_oid: item
        for item in github
        if isinstance(item.receipt, pr.GitHubSignatureObservationReceiptV1)
    }
    _require(len(by_commit) == 3 and set(by_commit) == {commit.oid for commit in chain[:3]})
    owner, name = pr._repository_slug_from_c0(c0, objects, policy.repository_id)
    blobs = {item.path: item for item in archive.api_blobs}
    parent = c0
    for commit, reviewer, attestation in zip(
        chain[:3], registry.reviewers, attestations, strict=True
    ):
        path = pr._statement_path(input_ref, reviewer.role)
        child_tree = pr._validate_only_tree_delta(parent, commit, objects, (path,))
        statement = _canonical_model(
            objects[child_tree[path][1]].raw_content, pr.ProtocolReviewStatementV1
        )
        _require(statement == attestation.statement)
        _signature_projection(
            by_commit[commit.oid],
            blobs,
            commit,
            parent,
            attestation,
            reviewer,
            identity,
            policy.repository_id,
            owner,
            name,
        )
        parent = commit
    security = {subject.kind: subject.sha256 for subject in attestations[2].statement.subjects}
    _require(
        security["identity_registry_bundle_sha256"] == identity.identity_registry_bundle_sha256
        and security["tag_operator_registry_sha256"] == operator.tag_operator_registry_sha256
        and security["tag_ruleset_policy_root"] == policy.tag_ruleset_policy_root
    )
    b0 = chain[3]
    builder = _c0_model(
        tree,
        objects,
        "benchmark/security/protocol-bundle-builder-git-identity.json",
        pr.ProtocolBundleBuilderGitIdentityV1,
    )
    pr._validate_b0_commit(
        b0,
        parent_oid=chain[2].oid,
        identity=builder,
        input_tag_ref=input_ref,
        bundle_sha256=bundle.protocol_attestation_bundle_sha256,
    )
    companion_ref = input_message.companion_tag_ref
    companion_tag, companion_view = pr._tag_object_for_ref(companion_ref, objects)
    pr._validate_tagger(companion_view.tagger, operator.operators[0])
    _require(companion_view.target_oid == b0.oid)
    companion_message = _canonical_model(
        companion_view.message[:-1], pr.ProtocolAttestationTagMessageV1
    )
    _require(
        companion_view.message
        == canonical_json_v1(companion_message.model_dump(mode="json")) + b"\n"
    )
    expected_message = {
        "schema_version": "ProtocolAttestationTagMessageV1",
        "input_tag_ref": input_ref,
        "input_tag_oid": input_tag.oid,
        "input_tag_object_sha256": input_tag.git_object_sha256,
        "companion_tag_ref": companion_ref,
        "bundle_commit_oid": b0.oid,
        "bundle_commit_object_sha256": b0.git_object_sha256,
        "protocol_attestation_bundle_sha256": bundle.protocol_attestation_bundle_sha256,
        "protocol_attestations_root": bundle.protocol_attestations_root,
        "tag_operator_registry_sha256": operator.tag_operator_registry_sha256,
        "tag_ruleset_policy_root": policy.tag_ruleset_policy_root,
    }
    _require(companion_message.model_dump(mode="json") == expected_message)
    suites = {
        item.receipt_kind: item.receipt
        for item in archive.api_receipts
        if item.receipt_kind in {"t0_creation_suite", "t1_creation_suite"}
    }
    t0, t1 = suites["t0_creation_suite"], suites["t1_creation_suite"]
    _require(
        isinstance(t0, pr.TagCreationRuleSuiteReceiptV1)
        and isinstance(t1, pr.TagCreationRuleSuiteReceiptV1)
    )
    assert isinstance(t0, pr.TagCreationRuleSuiteReceiptV1)
    assert isinstance(t1, pr.TagCreationRuleSuiteReceiptV1)
    _require(
        t0.rule_suite_id != t1.rule_suite_id
        and not set(t0.request_ids).intersection(t1.request_ids)
        and t0.raw_response_sha256 != t1.raw_response_sha256
        and t0.canonical_response_sha256 != t1.canonical_response_sha256
    )
    for suite, ref, tag in ((t0, input_ref, input_tag), (t1, companion_ref, companion_tag)):
        pr._validate_creation_suite(
            suite,
            expected_ref=ref,
            expected_after_oid=tag.oid,
            tag_operator_registry=operator,
            tag_ruleset_policy=policy,
        )
    pr._verify_archived_auxiliary_sources(
        archive=archive,
        tag_ruleset_policy=policy,
        t0_suite=t0,
        t1_suite=t1,
        repository_owner=owner,
        repository_name=name,
    )
    reached = {input_tag.oid, c0.oid, companion_tag.oid, *(item.oid for item in chain)}
    for commit in (c0, *chain):
        reached.update(pr._reachable_tree_objects(pr._parse_commit_view(commit).tree_oid, objects))
    _require(set(objects) == reached)
    binding = _hashed_model(
        {
            "schema_version": "ProtocolAttestationTagBindingV1",
            "input_tag_ref": input_ref,
            "input_tag_oid": input_tag.oid,
            "input_tag_object_sha256": input_tag.git_object_sha256,
            "peeled_c0_oid": c0.oid,
            "peeled_c0_sha256": c0.git_object_sha256,
            "reviewer_commits": [
                {
                    "role": reviewer.role,
                    "commit_oid": commit.oid,
                    "commit_object_sha256": commit.git_object_sha256,
                }
                for reviewer, commit in zip(registry.reviewers, chain[:3], strict=True)
            ],
            "bundle_commit_oid": b0.oid,
            "bundle_commit_object_sha256": b0.git_object_sha256,
            "companion_tag_ref": companion_ref,
            "companion_tag_oid": companion_tag.oid,
            "companion_tag_object_sha256": companion_tag.git_object_sha256,
            "protocol_registry_sha256": registry.protocol_reviewer_registry_sha256,
            "workflow_root": workflow_root,
            "protocol_attestations_root": bundle.protocol_attestations_root,
            "protocol_attestation_bundle_sha256": bundle.protocol_attestation_bundle_sha256,
            "object_closure_root": archive.object_closure_root,
            "tag_operator_registry_sha256": operator.tag_operator_registry_sha256,
            "tag_ruleset_policy_root": policy.tag_ruleset_policy_root,
        },
        pr.ProtocolAttestationTagBindingV1,
        "protocol_attestation_tag_binding_sha256",
        "laconian-protocol-attestation-tag-binding-v1",
    )
    _require(
        binding.protocol_attestation_tag_binding_sha256
        == context.protocol_attestation_tag_binding_sha256
    )


def validate_protocol_archive(raw_bytes: bytes, context: GenerationContextIndexV1) -> None:
    """Reject malformed or cross-context raw archives with a content-free error.

    File hashing/IO and campaign/provider/context-root joins belong to the caller.
    Successful structural validation returns no authority object.
    """
    try:
        _require(type(raw_bytes) is bytes and type(context) is GenerationContextIndexV1)
        checked_context = GenerationContextIndexV1.model_validate(context.model_dump(mode="json"))
        archive = _canonical_model(raw_bytes, pr.ProtocolReviewObjectArchiveV1)
        _validate_archive(archive, checked_context)
    except Exception:
        raise ValueError(_ERROR) from None
