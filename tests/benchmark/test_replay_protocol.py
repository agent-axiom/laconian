"""Raw protocol replay: source reconstruction without a live authority capability."""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import importlib
import inspect
import json
from typing import Any

import pytest

from laconian_eval.benchmark import protocol_review
from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.benchmark.audit_commit_reveal import AuditGitObjectArchiveV1
from laconian_eval.benchmark.context import GenerationContextIndexV1, LayerRootIndexV1
from laconian_eval.benchmark.protocol_review import (
    ProtocolReviewObjectArchiveV1,
    protocol_review_digest,
)
from laconian_eval.capsule.canonical import stable_digest
from tests.benchmark import helpers
from tests.benchmark import test_protocol_review as protocol_data


def _validator() -> Any:
    try:
        module = importlib.import_module("laconian_eval.replay._protocol")
    except ModuleNotFoundError:
        pytest.fail("raw protocol archive validator is missing")
    return module.validate_protocol_archive


def _context(payload: dict[str, Any]) -> GenerationContextIndexV1:
    payload = copy.deepcopy(payload)
    payload.pop("generation_context_index_sha256", None)
    payload["generation_context_index_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-index-v1", payload
    )
    return GenerationContextIndexV1.model_validate(payload)


@pytest.fixture(scope="module")
def protocol_fixture() -> Any:
    return helpers._build_synthetic_protocol_review()


@pytest.fixture(scope="module")
def raw_protocol(protocol_fixture: Any) -> tuple[bytes, GenerationContextIndexV1]:
    fixture = protocol_fixture
    layer = LayerRootIndexV1.model_validate(helpers.generation_layer_index_payload())
    payload = helpers.generation_context_index_payload(layer)
    payload.update(
        protocol_attestation_tag_binding_sha256=(
            fixture.binding.protocol_attestation_tag_binding_sha256
        ),
        protocol_attestation_bundle_sha256=fixture.bundle.protocol_attestation_bundle_sha256,
        protocol_review_object_archive_sha256=fixture.archive.protocol_review_object_archive_sha256,
        object_closure_root=fixture.archive.object_closure_root,
        input_tag_commit=fixture.c0.oid,
        workflow_root=fixture.workflow_inventory.workflow_root,
        protocol_reviewer_registry=fixture.registry.model_dump(mode="json"),
        protocol_reviewer_registry_sha256=fixture.registry.protocol_reviewer_registry_sha256,
        audit_reviewer_registry=fixture.audit_registry.model_dump(mode="json"),
        audit_reviewer_registry_sha256=fixture.audit_registry.audit_reviewer_registry_sha256,
        protocol_attestations=[
            item.model_dump(mode="json") for item in fixture.bundle.attestations
        ],
        protocol_attestations_root=fixture.bundle.protocol_attestations_root,
    )
    for field in payload.keys() & fixture.subject_values.keys():
        payload[field] = fixture.subject_values[field]
    return canonical_json_v1(fixture.archive.model_dump(mode="json")), _context(payload)


def _rehashed_archive(payload: dict[str, Any]) -> bytes:
    payload["objects"].sort(key=lambda item: item["oid"])
    projection = [
        {name: item[name] for name in ("oid", "type", "size", "git_object_sha256")}
        for item in payload["objects"]
    ]
    payload["object_closure_root"] = protocol_review_digest(
        "laconian-protocol-review-object-closure-v1", projection
    )
    payload.pop("protocol_review_object_archive_sha256", None)
    payload["protocol_review_object_archive_sha256"] = protocol_review_digest(
        "laconian-protocol-review-object-archive-v1", payload
    )
    return canonical_json_v1(payload)


def test_accepts_real_raw_archive_without_returning_authority(raw_protocol: Any) -> None:
    raw, context = raw_protocol
    assert _validator()(raw, context) is None


@pytest.mark.parametrize("encoding", ["final-lf", "indent", "foreign-owner", "self", "closure"])
def test_rejects_noncanonical_or_invalid_archive(raw_protocol: Any, encoding: str) -> None:
    raw, context = raw_protocol
    payload = json.loads(raw)
    if encoding == "final-lf":
        raw += b"\n"
    elif encoding == "indent":
        raw = json.dumps(payload, indent=2).encode()
    else:
        field, value = {
            "foreign-owner": ("schema_version", "AuditGitObjectArchiveV1"),
            "self": ("protocol_review_object_archive_sha256", "0" * 64),
            "closure": ("object_closure_root", "0" * 64),
        }[encoding]
        payload[field] = value
        raw = canonical_json_v1(payload)
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(raw, context)


def test_rejects_valid_task9_archive_owner(raw_protocol: Any) -> None:
    raw, context = raw_protocol
    obj = next(item for item in json.loads(raw)["objects"] if item["type"] == "blob")
    projection = [{name: obj[name] for name in ("oid", "type", "size", "git_object_sha256")}]
    payload = {
        "schema_version": "audit-git-object-archive-v1",
        "objects": [obj],
        "object_closure_root": stable_digest("laconian-audit-git-object-closure-v1", projection),
    }
    payload["audit_git_object_archive_sha256"] = stable_digest(
        "laconian-audit-git-object-archive-v1", payload
    )
    foreign = AuditGitObjectArchiveV1.model_validate_json(canonical_json_v1(payload))
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(canonical_json_v1(foreign.model_dump(mode="json")), context)


@pytest.mark.parametrize("kind", ["git", "api"])
def test_rejects_changed_raw_source_bytes(raw_protocol: Any, kind: str) -> None:
    raw, context = raw_protocol
    payload = json.loads(raw)
    collection, field = (
        ("objects", "raw_content_base64") if kind == "git" else ("api_blobs", "raw_bytes_base64")
    )
    item = payload[collection][0]
    item[field] = base64.b64encode(base64.b64decode(item[field]) + b" ").decode()
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(canonical_json_v1(payload), context)


def test_rejects_rehashed_unrelated_git_object(raw_protocol: Any) -> None:
    raw, context = raw_protocol
    payload = json.loads(raw)
    content = b"unrelated campaign source"
    wire = b"blob " + str(len(content)).encode() + b"\0" + content
    payload["objects"].append(
        {
            "oid": hashlib.sha1(wire).hexdigest(),
            "type": "blob",
            "size": len(content),
            "git_object_sha256": hashlib.sha256(wire).hexdigest(),
            "raw_content_base64": base64.b64encode(content).decode(),
        }
    )
    mutated = _rehashed_archive(payload)
    archive = ProtocolReviewObjectArchiveV1.model_validate(json.loads(mutated))
    context_payload = context.model_dump(mode="json")
    context_payload.update(
        object_closure_root=archive.object_closure_root,
        protocol_review_object_archive_sha256=archive.protocol_review_object_archive_sha256,
    )
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(mutated, _context(context_payload))


@pytest.mark.parametrize(
    "field", ["protocol_attestation_tag_binding_sha256", "protocol_attestation_bundle_sha256"]
)
def test_reconstructs_context_bindings_instead_of_trusting_copied_digests(
    raw_protocol: Any, field: str
) -> None:
    raw, context = raw_protocol
    payload = context.model_dump(mode="json")
    payload[field] = "0" * 64
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(raw, _context(payload))


def _replace_response(
    payload: dict[str, Any], binding: dict[str, Any], ordinal: int, raw: bytes
) -> bytes:
    old_digest = binding["receipt_sha256"]
    receipt = binding["receipt"]
    blobs = {item["path"]: item for item in payload["api_blobs"]}
    blob = blobs[binding["raw_blob_paths"][ordinal]]
    digest = hashlib.sha256(raw).hexdigest()
    blob.update(
        byte_length=len(raw), sha256=digest, raw_bytes_base64=base64.b64encode(raw).decode()
    )
    if binding["receipt_kind"] in {"t0_creation_suite", "t1_creation_suite"}:
        receipt["raw_response_sha256"] = digest
        field = "tag_creation_rule_suite_receipt_sha256"
        domain = "laconian-tag-creation-rule-suite-receipt-v1"
    else:
        receipt["raw_response_sha256s"][ordinal] = digest
        field = "github_signature_observation_receipt_sha256"
        domain = "laconian-github-signature-observation-receipt-v1"
    receipt.pop(field)
    receipt[field] = protocol_review_digest(domain, receipt)
    binding["receipt_sha256"] = receipt[field]
    for paths in (binding["raw_blob_paths"], binding["canonical_blob_paths"]):
        for index, path in enumerate(paths):
            renamed = path.replace(old_digest, receipt[field])
            blobs[path]["path"] = renamed
            paths[index] = renamed
    payload["api_blobs"].sort(key=lambda item: item["path"].encode())
    kinds = (
        "github_signature",
        "tag_ruleset_observation",
        "t0_creation_suite",
        "t1_creation_suite",
    )
    payload["api_receipts"].sort(
        key=lambda item: (
            kinds.index(item["receipt_kind"]),
            item["receipt"].get("observed_at", ""),
            item["receipt_sha256"],
        )
    )
    return _rehashed_archive(payload)


@pytest.mark.parametrize("attack", ["rest-success", "graphql-signer", "creation-shape", "secret"])
def test_rejects_rehashed_api_bindings_that_do_not_reconstruct(
    raw_protocol: Any, attack: str
) -> None:
    raw, context = raw_protocol
    payload = json.loads(raw)
    kind = "t1_creation_suite" if attack == "creation-shape" else "github_signature"
    binding = next(item for item in payload["api_receipts"] if item["receipt_kind"] == kind)
    ordinal = 1 if attack == "graphql-signer" else 0
    blob = next(
        item for item in payload["api_blobs"] if item["path"] == binding["raw_blob_paths"][ordinal]
    )
    body = json.loads(base64.b64decode(blob["raw_bytes_base64"]))
    if attack == "rest-success":
        body["verification"]["verified"] = False
    elif attack == "graphql-signer":
        body["data"]["repository"]["object"]["signature"]["signer"]["login"] = "other-campaign"
    elif attack == "secret":
        body["headers"] = {"authorization": "forbidden-fixture-value"}
    else:
        canonical = next(
            item
            for item in payload["api_blobs"]
            if item["path"] == binding["canonical_blob_paths"][0]
        )
        body = json.loads(base64.b64decode(canonical["raw_bytes_base64"]))
    mutated = _replace_response(payload, binding, ordinal, canonical_json_v1(body))
    archive = ProtocolReviewObjectArchiveV1.model_validate(json.loads(mutated))
    context_payload = context.model_dump(mode="json")
    context_payload["protocol_review_object_archive_sha256"] = (
        archive.protocol_review_object_archive_sha256
    )
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(mutated, _context(context_payload))


def test_raw_helper_has_no_transitive_authority_or_io_calls() -> None:
    module = importlib.import_module("laconian_eval.replay._protocol")
    helper_tree = ast.parse(inspect.getsource(module))
    source_tree = ast.parse(inspect.getsource(protocol_review))
    definitions = {
        node.name: node
        for node in source_tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    pending = [
        node.attr
        for node in ast.walk(helper_tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "pr"
        and node.attr in definitions
    ]
    reached: set[str] = set()
    nodes = list(ast.walk(helper_tree))
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        children = list(ast.walk(definitions[name]))
        nodes.extend(children)
        pending.extend(
            node.id
            for node in children
            if isinstance(node, ast.Name) and node.id in definitions and node.id not in reached
        )
    names = {node.id for node in nodes if isinstance(node, ast.Name)}
    attributes = {node.attr for node in nodes if isinstance(node, ast.Attribute)}
    forbidden = {
        "_verify_active_verifier_runtime",
        "_verify_keyed_signature_v1",
        "verify_commit_signature_evidence_source",
        "_derive_source_evidence",
        "verify_protocol_review_dag",
        "_verify_protocol_review_dag",
        "_verify_protocol_review_prefix",
        "VerifiedProtocolReviewDagV1",
        "VerifiedProtocolReviewPrefixV1",
        "build_protocol_attestation_bundle",
        "build_protocol_attestation_tag_binding",
        "build_protocol_review_object_archive",
        "load_verified_protocol_review_object_archive",
        "_load_identity_registry_bundle",
        "open",
        "read_bytes",
        "write_bytes",
        "read_text",
        "write_text",
        "subprocess",
        "httpx",
        "requests",
        "socket",
        "Path",
        "os",
        "tempfile",
        "import_module",
    }
    assert not (names | attributes) & forbidden
    assert "_verify_archived_auxiliary_sources" in reached
    assert "_parse_b0_payloads" in reached
    assert not any(
        isinstance(node, ast.ImportFrom) and "campaign" in (node.module or "")
        for node in ast.walk(helper_tree)
    )


def _alternate_final_graph(
    fixture: Any, *, corrupt_local_receipt: bool
) -> tuple[bytes, dict[str, Any]]:
    """Rethread actual B0/T1 bytes and all raw hashes, without a verified wrapper."""
    objects = {item.oid: item for item in fixture.dag.objects}
    b0 = fixture.b0
    bundle = fixture.bundle
    if corrupt_local_receipt:
        envelopes = [item.model_dump(mode="json") for item in bundle.attestations]
        envelope = envelopes[2]
        local = envelope["signature_evidence"]["local_signature_verification"]
        local.pop("verification_receipt_sha256")
        local["signed_payload_sha256"] = "0" * 64
        local["verification_receipt_sha256"] = protocol_review_digest(
            "laconian-local-signature-verification-receipt-v1", local
        )
        envelope.pop("attestation_sha256")
        envelope["attestation_sha256"] = protocol_review_digest(
            "laconian-verified-protocol-attestation-v1", envelope
        )
        bundle_payload = bundle.model_dump(
            mode="json", exclude={"protocol_attestation_bundle_sha256"}
        )
        bundle_payload.update(
            attestations=envelopes,
            protocol_attestations_root=protocol_review_digest(
                "laconian-verified-protocol-attestations-root-v1", envelopes
            ),
        )
        bundle_payload["protocol_attestation_bundle_sha256"] = protocol_review_digest(
            "laconian-protocol-attestation-bundle-v1", bundle_payload
        )
        bundle = protocol_review.ProtocolAttestationBundleV1.model_validate(bundle_payload)
        tree = protocol_review._flatten_tree(
            protocol_review._parse_commit_view(b0).tree_oid, objects
        )
        files = {path: objects[entry[1]].raw_content for path, entry in tree.items()}
        prefix = "benchmarks/protocol-reviews/benchmark-input-20260831.1/"
        files[prefix + "attestations/03-security-evidence.json"] = canonical_json_v1(envelope)
        files[prefix + "bundle.json"] = canonical_json_v1(bundle_payload)
        new_tree = protocol_data._tree_for_files(objects, files)
        b0_raw = b0.raw_content.replace(
            b0.raw_content.splitlines()[0], b"tree " + new_tree.oid.encode(), 1
        ).replace(
            fixture.bundle.protocol_attestation_bundle_sha256.encode(),
            bundle.protocol_attestation_bundle_sha256.encode(),
        )
        b0 = protocol_data._git_object(objects, "commit", b0_raw)
    companion_raw = (
        fixture.companion_tag.raw_content.replace(fixture.b0.oid.encode(), b0.oid.encode())
        .replace(fixture.b0.git_object_sha256.encode(), b0.git_object_sha256.encode())
        .replace(
            fixture.bundle.protocol_attestation_bundle_sha256.encode(),
            bundle.protocol_attestation_bundle_sha256.encode(),
        )
        .replace(
            fixture.bundle.protocol_attestations_root.encode(),
            bundle.protocol_attestations_root.encode(),
        )
    )
    if not corrupt_local_receipt:
        companion_raw = companion_raw.replace(b"1788134400 +0000", b"1788134401 +0000")
    companion = protocol_data._git_object(objects, "tag", companion_raw)
    assert companion.oid != fixture.companion_tag.oid
    commits = (fixture.c0, *fixture.commits, b0)
    reached = {fixture.input_tag.oid, companion.oid, *(item.oid for item in commits)}
    for commit in commits:
        reached.update(
            protocol_review._reachable_tree_objects(
                protocol_review._parse_commit_view(commit).tree_oid, objects
            )
        )
    payload = fixture.archive.model_dump(mode="json")
    payload["objects"] = [
        {
            "oid": item.oid,
            "type": item.object_type,
            "size": item.size,
            "git_object_sha256": item.git_object_sha256,
            "raw_content_base64": base64.b64encode(item.raw_content).decode(),
        }
        for oid in sorted(reached)
        for item in (objects[oid],)
    ]
    old_suite = next(
        item for item in payload["api_receipts"] if item["receipt_kind"] == "t1_creation_suite"
    )
    paths = set(old_suite["raw_blob_paths"] + old_suite["canonical_blob_paths"])
    payload["api_blobs"] = [item for item in payload["api_blobs"] if item["path"] not in paths]
    payload["api_receipts"].remove(old_suite)
    suite = protocol_data._creation_suite(
        "refs/tags/benchmark-attestations-20260831.1", companion.oid, 1002
    )
    wrapper = protocol_data._archive_binding("t1_creation_suite", suite)
    payload["api_receipts"].append(wrapper.model_dump(mode="json"))
    payload["api_blobs"].extend(
        item.model_dump(mode="json") for item in protocol_data._archive_blobs(wrapper, suite)
    )
    payload["api_blobs"].sort(key=lambda item: item["path"].encode())
    raw = _rehashed_archive(payload)
    archive = ProtocolReviewObjectArchiveV1.model_validate(json.loads(raw))
    binding = fixture.binding.model_dump(
        mode="json", exclude={"protocol_attestation_tag_binding_sha256"}
    )
    binding.update(
        bundle_commit_oid=b0.oid,
        bundle_commit_object_sha256=b0.git_object_sha256,
        companion_tag_oid=companion.oid,
        companion_tag_object_sha256=companion.git_object_sha256,
        protocol_attestation_bundle_sha256=bundle.protocol_attestation_bundle_sha256,
        protocol_attestations_root=bundle.protocol_attestations_root,
        object_closure_root=archive.object_closure_root,
    )
    binding["protocol_attestation_tag_binding_sha256"] = protocol_review_digest(
        "laconian-protocol-attestation-tag-binding-v1", binding
    )
    checked_binding = protocol_review.ProtocolAttestationTagBindingV1.model_validate(binding)
    return raw, {
        "protocol_review_object_archive_sha256": archive.protocol_review_object_archive_sha256,
        "object_closure_root": archive.object_closure_root,
        "protocol_attestation_tag_binding_sha256": (
            checked_binding.protocol_attestation_tag_binding_sha256
        ),
        "protocol_attestation_bundle_sha256": bundle.protocol_attestation_bundle_sha256,
        "protocol_attestations_root": bundle.protocol_attestations_root,
        "protocol_attestations": [item.model_dump(mode="json") for item in bundle.attestations],
    }


def test_second_coherent_archive_cannot_replace_first_context(
    raw_protocol: Any, protocol_fixture: Any
) -> None:
    _, first_context = raw_protocol
    raw, bindings = _alternate_final_graph(protocol_fixture, corrupt_local_receipt=False)
    second_payload = first_context.model_dump(mode="json")
    second_payload.update(bindings, campaign_id="second-campaign")
    assert _validator()(raw, _context(second_payload)) is None
    copied_roots = first_context.model_dump(mode="json")
    for field in ("protocol_review_object_archive_sha256", "object_closure_root"):
        copied_roots[field] = bindings[field]
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(raw, _context(copied_roots))


def test_rehashed_local_receipt_must_match_raw_commit_even_with_all_supplied_bindings(
    raw_protocol: Any, protocol_fixture: Any
) -> None:
    _, context = raw_protocol
    raw, bindings = _alternate_final_graph(protocol_fixture, corrupt_local_receipt=True)
    payload = context.model_dump(mode="json")
    payload.update(bindings)
    with pytest.raises(ValueError, match=r"^invalid protocol archive$"):
        _validator()(raw, _context(payload))
