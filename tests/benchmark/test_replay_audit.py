"""Raw review replay tests, with genuine retained source-backed audit data."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import textwrap
from dataclasses import is_dataclass, replace
from types import ModuleType

import pytest

from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.replay._inputs import Inputs
from laconian_eval.replay._structure import generation, hard_scores, judge_requests, provider_graph


@pytest.fixture(scope="module")
def audit_data(replay_campaign):
    root = replay_campaign.workspace_root
    with Inputs() as inputs:
        graph = generation(
            inputs,
            root / "GENERATION_COMPLETE/generation-context-expectation.json",
            root / "GENERATION/generation-context.json",
            root / "GENERATION",
        )
        hard_scores(inputs, graph, root / "HARD")
        judge_requests(inputs, graph, root / "REQUESTS")
        provider_graph(inputs, graph, root / "JUDGES/provider-evidence-index.json", root / "JUDGES")
        reviews = inputs.tree(root / "REVIEWS")
        complete = inputs.tree(replay_campaign.audit_root)
    return graph, reviews, complete


def test_raw_audit_replay_has_ordinary_data_boundary() -> None:
    assert importlib.util.find_spec("laconian_eval.replay._audit") is not None, (
        "raw review structural validator is not implemented"
    )


def test_real_review_and_complete_roots_keep_only_raw_data(audit_data):
    assert importlib.util.find_spec("laconian_eval.replay._audit") is not None
    from laconian_eval.replay._audit import validate_audit

    graph, review, complete = audit_data
    result = validate_audit(review, graph, complete=False)
    assert is_dataclass(result)
    assert result.__dataclass_params__.frozen
    assert result.attachment is None and result.metrics == ()
    full = validate_audit(complete, graph, complete=True)
    assert full.population_attachment == result.population_attachment
    assert full.reviewer_chains == result.reviewer_chains
    assert full.attachment is not None and len(full.metrics) == 3


@pytest.mark.parametrize("member", range(26))
def test_raw_review_requires_every_member(audit_data, member):
    from laconian_eval.replay._audit import validate_audit

    graph, review, _ = audit_data
    members = dict(review.members)
    del members[sorted(members)[member]]
    with pytest.raises(ValueError):
        validate_audit(replace(review, members=members), graph, complete=False)


@pytest.mark.parametrize(
    "extra", ["audit/audit-evidence.json", "audit/metrics.json", "audit/extra", "empty/"]
)
def test_raw_review_forbids_derived_files_extras_and_empty_directories(audit_data, extra):
    from laconian_eval.replay._audit import validate_audit

    graph, review, _ = audit_data
    members = dict(review.members)
    directories = review.directories
    if extra.endswith("/"):
        directories = directories | {extra[:-1]}
    else:
        members[extra] = b"{}\n"
    with pytest.raises(ValueError):
        validate_audit(
            replace(review, members=members, directories=directories), graph, complete=False
        )


def test_raw_audit_rejects_rehashed_population_attempt_parent(audit_data):
    import json

    from laconian_eval.replay._audit import validate_audit

    graph, review, _ = audit_data
    members = dict(review.members)
    payload = json.loads(members["audit/population-attachment.json"])
    payload.pop("population_attachment_sha256")
    payload["judge_attempt_root_index_sha256"] = "f" * 64
    payload["population_attachment_sha256"] = stable_digest(
        "laconian-audit-population-attachment-v1", payload
    )
    members["audit/population-attachment.json"] = canonical_json(payload) + b"\n"
    with pytest.raises(ValueError):
        validate_audit(replace(review, members=members), graph, complete=False)


def test_metric_source_inputs_reject_rehashed_weight_substitution(audit_data):
    import json

    from laconian_eval.replay._audit import validate_audit

    graph, _, complete = audit_data
    members = dict(complete.members)
    metrics = json.loads(members["audit/metrics.json"])
    first = metrics[0]
    identifier = next(iter(first["weights_by_record"]))
    first["weights_by_record"][identifier] = {"numerator": 123, "denominator": 1}
    first.pop("model_audit_metric_sha256")
    first["model_audit_metric_sha256"] = stable_digest("laconian-model-audit-metric-v1", first)
    members["audit/metrics.json"] = canonical_json(metrics) + b"\n"
    attachment = json.loads(members["audit/audit-evidence.json"])
    attachment["model_audit_metric_sha256s"][0] = first["model_audit_metric_sha256"]
    attachment.pop("audit_evidence_sha256")
    attachment["audit_evidence_sha256"] = stable_digest(
        "laconian-verified-audit-evidence-v1", attachment
    )
    members["audit/audit-evidence.json"] = canonical_json(attachment) + b"\n"
    with pytest.raises(ValueError):
        validate_audit(replace(complete, members=members), graph, complete=True)


@pytest.mark.parametrize("attack", ["rest-false", "graphql-actor", "raw-payload"])
def test_signature_raw_projection_rejects_fully_rehashed_source(audit_data, attack):
    import json

    from laconian_eval.benchmark import audit_commit_reveal as ac
    from laconian_eval.replay._audit import _repository, _signature
    from tests.benchmark.test_audit_commit_reveal import _source_with_signature_raw

    graph, review, _ = audit_data
    reviewer = graph.context.audit_reviewer_registry.reviewers[0].reviewer_id
    source = review.model(
        f"audit/pull-request-sources/commitment/{reviewer}.json",
        ac.AuditPullRequestEvidenceSourceV1,
    )
    chain = review.model(f"audit/reviewer-chains/{reviewer}.json", ac.ReviewerChainV1)
    objects = ac._archive_objects(
        review.model("audit/git-object-archive.json", ac.AuditGitObjectArchiveV1)
    )
    raw, _ = ac._decode_signature_pairs(source)
    payloads = [json.loads(item) for item in raw]
    if attack == "rest-false":
        payloads[0]["verification"]["verified"] = False
    elif attack == "graphql-actor":
        payloads[1]["data"]["repository"]["object"]["signature"]["signer"]["databaseId"] += 1
    else:
        payloads[0]["verification"]["payload"] += "candidate-canary"
    mutated = _source_with_signature_raw(source, tuple(canonical_json(item) for item in payloads))
    # This is a valid raw source with recomputed byte lengths, receipt and source hashes.
    assert mutated.pull_request_source_sha256 != source.pull_request_source_sha256
    with pytest.raises(ValueError):
        _signature(mutated, chain.commitment_pr, graph, objects, _repository(graph))


@pytest.mark.parametrize(
    "field", ["signed_payload_sha256", "signature_sha256", "verifier_tool_sha256"]
)
def test_local_signature_receipt_rejects_rehashed_binding_substitution(audit_data, field):
    from laconian_eval.benchmark import audit_commit_reveal as ac
    from laconian_eval.benchmark import protocol_review as pr
    from laconian_eval.replay._audit import _repository, _signature

    graph, review, _ = audit_data
    reviewer = next(
        row.reviewer_id
        for row in graph.context.audit_reviewer_registry.reviewers
        if row.verification_mode != "github_verified_commit"
    )
    source = review.model(
        f"audit/pull-request-sources/commitment/{reviewer}.json",
        ac.AuditPullRequestEvidenceSourceV1,
    )
    chain = review.model(f"audit/reviewer-chains/{reviewer}.json", ac.ReviewerChainV1)
    objects = ac._archive_objects(
        review.model("audit/git-object-archive.json", ac.AuditGitObjectArchiveV1)
    )
    payload = source.model_dump(mode="json")
    receipt = payload["signature_evidence"]["local_signature_verification"]
    receipt.pop("verification_receipt_sha256")
    receipt[field] = "0" * 64
    receipt["verification_receipt_sha256"] = pr.protocol_review_digest(
        "laconian-local-signature-verification-receipt-v1", receipt
    )
    payload.pop("pull_request_source_sha256")
    payload["pull_request_source_sha256"] = stable_digest(
        "laconian-audit-pull-request-source-v1", payload
    )
    mutated = ac.AuditPullRequestEvidenceSourceV1.model_validate_json(canonical_json(payload))
    proof = chain.commitment_pr.model_dump(mode="json")
    proof["signature_evidence"] = payload["signature_evidence"]
    proof["pull_request_source_sha256"] = mutated.pull_request_source_sha256
    proof.pop("pull_request_proof_sha256")
    proof["pull_request_proof_sha256"] = stable_digest(
        "laconian-audit-pull-request-proof-v1", proof
    )
    mutated_proof = ac.PullRequestProofV1.model_validate_json(canonical_json(proof))
    with pytest.raises(ValueError):
        _signature(mutated, mutated_proof, graph, objects, _repository(graph))


def _rehashed_signed_head(source, proof, original, raw_head):
    """Change actual Git bytes and every retained raw signature/source binding."""
    import base64
    import hashlib
    import json

    from laconian_eval.benchmark import audit_commit_reveal as ac
    from laconian_eval.benchmark import protocol_review as pr

    def rehash(payload, field, domain, *, protocol=False):
        payload.pop(field)
        payload[field] = (pr.protocol_review_digest if protocol else stable_digest)(domain, payload)

    head = pr.parse_protocol_git_object(
        oid=hashlib.sha1(b"commit " + str(len(raw_head)).encode() + b"\0" + raw_head).hexdigest(),
        object_type="commit",
        raw_content=raw_head,
    )
    view = pr._parse_commit_view(head)
    assert head.oid != original.oid
    payload = source.model_dump(mode="json")
    evidence = payload["signature_evidence"]
    evidence["commit_oid"] = head.oid
    evidence["commit_object_sha256"] = head.git_object_sha256
    rest, graphql = evidence["github_rest_verification"], evidence["github_graphql_signature"]
    rest["commit_oid"] = head.oid
    rest["endpoint"] = rest["endpoint"].replace(original.oid, head.oid)
    rest["payload"] = view.signed_payload.decode()
    rehash(
        rest,
        "rest_projection_sha256",
        "laconian-github-commit-verification-projection-v1",
        protocol=True,
    )
    graphql["commit_oid"] = head.oid
    rehash(
        graphql,
        "graphql_projection_sha256",
        "laconian-github-signature-projection-v1",
        protocol=True,
    )
    raw_pair, _ = ac._decode_signature_pairs(source)
    raw_rest, raw_graphql = map(json.loads, raw_pair)
    raw_rest["sha"] = head.oid
    raw_rest["verification"]["payload"] = view.signed_payload.decode()
    raw_graphql["data"]["repository"]["object"]["oid"] = head.oid
    raw_pair = (canonical_json(raw_rest), canonical_json(raw_graphql))
    canonical_pair = (canonical_json(rest), canonical_json(graphql))
    receipt = payload["signature_observation_receipt"]
    receipt["commit_oid"] = head.oid
    receipt["rest_projection_sha256"] = rest["rest_projection_sha256"]
    receipt["graphql_projection_sha256"] = graphql["graphql_projection_sha256"]
    receipt["raw_response_sha256s"] = [hashlib.sha256(raw).hexdigest() for raw in raw_pair]
    receipt["canonical_response_sha256s"] = [
        hashlib.sha256(raw).hexdigest() for raw in canonical_pair
    ]
    rehash(
        receipt,
        "github_signature_observation_receipt_sha256",
        "laconian-github-signature-observation-receipt-v1",
        protocol=True,
    )
    for kind, pair in (("raw", raw_pair), ("canonical", canonical_pair)):
        payload[f"signature_{kind}_response_bytes_base64"] = [
            base64.b64encode(raw).decode() for raw in pair
        ]
        payload[f"signature_{kind}_response_byte_lengths"] = list(map(len, pair))
    # Keep the source PR projection/raw bytes and its own receipt consistent too.
    record = payload["pull_request_record"]
    record["head_sha"] = head.oid
    rehash(record, "exact_api_record_sha256", "laconian-audit-github-pull-request-record-v1")
    raw_pr = json.loads(base64.b64decode(payload["pull_request_raw_response_base64"]))
    raw_pr["head"]["sha"] = head.oid
    raw_pr_bytes = canonical_json(raw_pr)
    payload["pull_request_raw_response_base64"] = base64.b64encode(raw_pr_bytes).decode()
    pr_receipt = payload["pull_request_observation_receipt"]
    pr_receipt["raw_response_byte_length"] = len(raw_pr_bytes)
    pr_receipt["raw_response_sha256"] = hashlib.sha256(raw_pr_bytes).hexdigest()
    rehash(
        pr_receipt,
        "github_audit_api_observation_receipt_sha256",
        "laconian-audit-github-api-observation-receipt-v1",
    )
    rehash(payload, "pull_request_source_sha256", "laconian-audit-pull-request-source-v1")
    mutated_source = ac.AuditPullRequestEvidenceSourceV1.model_validate_json(
        canonical_json(payload)
    )
    proof_payload = proof.model_dump(mode="json")
    proof_payload.update(
        head_sha=head.oid,
        signature_evidence=evidence,
        exact_pr_api_record_sha256=record["exact_api_record_sha256"],
        pull_request_source_sha256=mutated_source.pull_request_source_sha256,
    )
    rehash(proof_payload, "pull_request_proof_sha256", "laconian-audit-pull-request-proof-v1")
    mutated_proof = ac.PullRequestProofV1.model_validate_json(canonical_json(proof_payload))
    return mutated_source, mutated_proof, head


@pytest.mark.parametrize(
    "attack",
    [
        "extra-header",
        "header-order",
        "author-invalid",
        "committer-invalid",
        "author-epoch-leading-zero",
        "author-epoch-out-of-range",
        "committer-epoch-negative",
        "author-timezone",
        "committer-timezone",
    ],
)
def test_github_signature_checks_exact_commit_grammar_and_identities(audit_data, attack):
    from laconian_eval.benchmark import audit_commit_reveal as ac
    from laconian_eval.benchmark import protocol_review as pr
    from laconian_eval.replay._audit import _repository, _signature

    graph, review, _ = audit_data
    reviewer = next(
        row.reviewer_id
        for row in graph.context.audit_reviewer_registry.reviewers
        if row.verification_mode == "github_verified_commit"
    )
    source = review.model(
        f"audit/pull-request-sources/commitment/{reviewer}.json",
        ac.AuditPullRequestEvidenceSourceV1,
    )
    chain = review.model(f"audit/reviewer-chains/{reviewer}.json", ac.ReviewerChainV1)
    objects = ac._archive_objects(
        review.model("audit/git-object-archive.json", ac.AuditGitObjectArchiveV1)
    )
    head = objects[chain.commitment_pr.head_sha]
    view = pr._parse_commit_view(head)
    raw = head.raw_content
    if attack == "extra-header":
        raw = raw.replace(b"\ngpgsig ", b"\nencoding UTF-8\ngpgsig ", 1)
    elif attack == "header-order":
        raw = raw.replace(
            b"author " + view.author + b"\ncommitter " + view.committer,
            b"committer " + view.committer + b"\nauthor " + view.author,
            1,
        )
    else:
        kind = "author" if attack.startswith("author") else "committer"
        original = getattr(view, kind)
        if attack.endswith("invalid"):
            changed = b"invalid"
        elif attack.endswith("leading-zero"):
            identity, epoch, timezone = original.rsplit(b" ", 2)
            changed = b" ".join((identity, b"0" + epoch, timezone))
        elif attack.endswith("out-of-range"):
            identity, _, timezone = original.rsplit(b" ", 2)
            changed = b" ".join((identity, b"253402300800", timezone))
        elif attack.endswith("negative"):
            identity, _, timezone = original.rsplit(b" ", 2)
            changed = b" ".join((identity, b"-1", timezone))
        else:
            changed = original.rsplit(b" ", 1)[0] + b" +0100"
        raw = raw.replace(kind.encode() + b" " + original, kind.encode() + b" " + changed, 1)
    mutated_source, mutated_proof, mutated_head = _rehashed_signed_head(
        source, chain.commitment_pr, head, raw
    )
    objects[mutated_head.oid] = mutated_head
    with pytest.raises(ValueError):
        _signature(mutated_source, mutated_proof, graph, objects, _repository(graph))


def test_raw_audit_transitive_call_graph_has_no_authority_or_io():
    from laconian_eval.replay import _audit
    from laconian_eval.replay._inputs import Tree

    pending = [_audit.validate_audit, Tree.model]
    reached = set()
    forbidden = {
        "_verify_active_verifier_runtime",
        "_verify_keyed_signature_v1",
        "verify_commit_signature_evidence_source",
        "verify_audit_chain",
        "verify_reviewer_chain",
        "_verify_pull_request_source",
        "_verify_chain_checked",
        "_derive_audit",
        "build_audit_population",
        "select_audit_sample",
        "verify_audit_sample",
        "_verify_audit_sample_from_checked",
        "compute_model_audit_metrics",
        "_wilson_proportion",
        "_compute_sampling_design",
        "_confusion",
        "analyze_campaign",
        "_mint_population",
        "open",
        "read_bytes",
        "write_bytes",
        "read_text",
        "write_text",
        "Popen",
        "_verify_ed25519",
        "_verify_ssh_signature",
        "_verify_openpgp_signature",
    }
    while pending:
        function = pending.pop()
        if function in reached:
            continue
        reached.add(function)
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = node.func
            name = (
                call.id
                if isinstance(call, ast.Name)
                else call.attr
                if isinstance(call, ast.Attribute)
                else ""
            )
            assert name not in forbidden and not name.startswith(("load_verified_", "write_")), name
            target = function.__globals__.get(name) if isinstance(call, ast.Name) else None
            if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name):
                module = function.__globals__.get(call.value.id)
                if isinstance(module, ModuleType):
                    target = getattr(module, name, None)
            if inspect.isfunction(target) and target.__module__.startswith("laconian_eval."):
                pending.append(target)
    assert {
        "_verify_topology_and_closure",
        "_record_from_source",
        "_verify_signoff_source",
        "_checked_design",
    } <= {function.__name__ for function in reached}
