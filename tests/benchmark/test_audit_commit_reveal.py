"""Source-backed Task 9 audit commit/reveal contract tests."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import laconian_eval.benchmark.audit_commit_reveal as audit_module
import laconian_eval.benchmark.protocol_review as protocol_module
from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.benchmark.audit_commit_reveal import (
    AuditAdjudicationCoreV1,
    AuditAdjudicationV1,
    AuditGitObjectArchiveV1,
    AuditPullRequestEvidenceSourceV1,
    CommitmentHeaderV1,
    ConsensusLabelV1,
    ExactGitHubPullRequestRecordV1,
    ExactGitHubReviewRecordV1,
    ExactGitHubReviewSignoffV1,
    ExactGitHubReviewSourceV1,
    GitHubAuditApiObservationReceiptV1,
    HumanAuditLabelV1,
    PullRequestProofV1,
    ReviewerChainV1,
    ReviewerCommitmentV1,
    ReviewerIdentityV1,
    ReviewerRevealV1,
    canonical_label_jsonl,
    compute_commitment,
    verify_audit_chain,
    verify_reviewer_chain,
)
from laconian_eval.benchmark.audit_sampling import (
    VerifiedAuditSampleRootV1,
    select_audit_sample,
    write_audit_sample_root,
)
from laconian_eval.benchmark.judge import RubricItemJudgmentV1, WarningJudgmentV1
from laconian_eval.benchmark.protocol_review import (
    GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
    ArchivedProtocolGitObjectV1,
    GitHubCommitVerificationProjectionV1,
    GitHubSignatureObservationReceiptV1,
    GitHubSignatureProjectionV1,
    GitHubVerifiedCommitEvidenceV1,
    LocalSignatureVerificationReceiptV1,
    ParsedProtocolGitObjectV1,
    ProtocolSignatureEvidenceSourceV1,
    ReviewerAccountBindingV1,
    SSHVerifiedCommitEvidenceV1,
    parse_protocol_git_object,
    protocol_review_digest,
    verify_commit_signature_evidence_source,
)
from laconian_eval.benchmark.provider_evidence import build_audit_population
from laconian_eval.capsule.canonical import stable_digest
from tests.benchmark.helpers import (
    CompleteProviderEvidenceFixture,
    audit_reviewer_ssh_key_material,
    get_cached_complete_provider_evidence_fixture,
)

SHA = "1" * 64
OID = "1" * 40
CAMPAIGN = "benchmark-0123456789abcdef0123456789abcdef"


class _DictSubclass(dict[str, Any]):
    pass


def _label(identifier: str = "0" * 64) -> HumanAuditLabelV1:
    return HumanAuditLabelV1(
        audit_record_id=identifier,
        rubric_items=(RubricItemJudgmentV1(item_index=0, passed=True, evidence="доказано"),),
        material_warning=None,
        material_contradiction=False,
        contradiction_evidence=None,
        semantic_pass=True,
    )


def _header() -> CommitmentHeaderV1:
    return CommitmentHeaderV1(
        schema_version="audit-commitment-v1",
        campaign_id=CAMPAIGN,
        campaign_registry_sha256="2" * 64,
        reviewer_id="audit-a",
        audit_reviewer_registry_sha256="3" * 64,
        sample_manifest_sha256="4" * 64,
        audit_commit_reveal_protocol_sha256="5" * 64,
    )


def _digest(domain: str, payload: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(payload)
    result[field] = stable_digest(domain, payload)
    return result


def _protocol_digest(domain: str, payload: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(payload)
    result[field] = protocol_review_digest(domain, payload)
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if type(value) is tuple:
        return tuple(_json_value(item) for item in value)
    if type(value) is list:
        return [_json_value(item) for item in value]
    return value


def _rehash(model: Any, domain: str, field: str, /, **updates: Any) -> Any:
    payload = model.model_dump(mode="json", exclude={field})
    payload.update({key: _json_value(value) for key, value in updates.items()})
    payload[field] = stable_digest(domain, payload)
    return type(model).model_validate_json(canonical_json_v1(payload))


def _protocol_rehash(model: Any, domain: str, field: str, /, **updates: Any) -> Any:
    payload = model.model_dump(mode="json", exclude={field})
    payload.update({key: _json_value(value) for key, value in updates.items()})
    payload[field] = protocol_review_digest(domain, payload)
    return type(model).model_validate_json(canonical_json_v1(payload))


_ED_P = 2**255 - 19
_ED_Q = 2**252 + 27742317777372353535851937790883648493
_ED_D = (-121665 * pow(121666, _ED_P - 2, _ED_P)) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)


def _ed_x(y: int, sign: int) -> int:
    y2 = y * y % _ED_P
    x2 = (y2 - 1) * pow(_ED_D * y2 + 1, _ED_P - 2, _ED_P) % _ED_P
    x = pow(x2, (_ED_P + 3) // 8, _ED_P)
    if (x * x - x2) % _ED_P:
        x = x * _ED_I % _ED_P
    assert (x * x - x2) % _ED_P == 0
    return _ED_P - x if (x & 1) != sign else x


_ED_BASE_Y = 4 * pow(5, _ED_P - 2, _ED_P) % _ED_P
_ED_BASE = (_ed_x(_ED_BASE_Y, 0), _ED_BASE_Y)


def _ed_add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    product = _ED_D * x1 * x2 * y1 * y2 % _ED_P
    return (
        (x1 * y2 + y1 * x2) * pow(1 + product, _ED_P - 2, _ED_P) % _ED_P,
        (y1 * y2 + x1 * x2) * pow(1 - product, _ED_P - 2, _ED_P) % _ED_P,
    )


def _ed_mult(scalar: int, point: tuple[int, int]) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _ed_add(result, addend)
        addend = _ed_add(addend, addend)
        scalar >>= 1
    return result


def _ed_encode(point: tuple[int, int]) -> bytes:
    x, y = point
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _ed_sign(seed: bytes, message: bytes) -> bytes:
    digest = hashlib.sha512(seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    public_key = _ed_encode(_ed_mult(scalar, _ED_BASE))
    nonce = int.from_bytes(hashlib.sha512(digest[32:] + message).digest(), "little") % _ED_Q
    encoded_r = _ed_encode(_ed_mult(nonce, _ED_BASE))
    challenge = (
        int.from_bytes(hashlib.sha512(encoded_r + public_key + message).digest(), "little") % _ED_Q
    )
    encoded_s = ((nonce + challenge * scalar) % _ED_Q).to_bytes(32, "little")
    return encoded_r + encoded_s


def _ssh_string(value: bytes) -> bytes:
    return len(value).to_bytes(4, "big") + value


def _armor(body: bytes, begin: bytes, end: bytes, width: int, *, pgp: bool) -> bytes:
    encoded = base64.b64encode(body)
    lines = [encoded[index : index + width] for index in range(0, len(encoded), width)]
    if pgp:
        crc = 0xB704CE
        for byte in body:
            crc ^= byte << 16
            for _ in range(8):
                crc <<= 1
                if crc & 0x1000000:
                    crc ^= 0x1864CFB
        crc_line = b"=" + base64.b64encode((crc & 0xFFFFFF).to_bytes(3, "big"))
        return b"\n".join((begin, b"", *lines, crc_line, end, b""))
    return b"\n".join((begin, *lines, end, b""))


def _openpgp_mpi(raw: bytes) -> bytes:
    value = int.from_bytes(raw, "big")
    encoded = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return value.bit_length().to_bytes(2, "big") + encoded


def _github_signature() -> bytes:
    body = (
        b"\x04\x00\x16\x08"
        + b"\x00\x00"
        + b"\x00\x00"
        + b"\x00\x00"
        + _openpgp_mpi(b"\x01")
        + _openpgp_mpi(b"\x01")
    )
    packet = bytes((0xC0 | 2, len(body))) + body
    return _armor(
        packet,
        b"-----BEGIN PGP SIGNATURE-----",
        b"-----END PGP SIGNATURE-----",
        64,
        pgp=True,
    )


def _ssh_signature(signed_payload: bytes) -> bytes:
    seed, wire_key, _ = audit_reviewer_ssh_key_material()
    preimage = (
        b"SSHSIG"
        + _ssh_string(b"git")
        + _ssh_string(b"")
        + _ssh_string(b"sha512")
        + _ssh_string(hashlib.sha512(signed_payload).digest())
    )
    signature_blob = _ssh_string(b"ssh-ed25519") + _ssh_string(_ed_sign(seed, preimage))
    body = (
        b"SSHSIG"
        + (1).to_bytes(4, "big")
        + _ssh_string(wire_key)
        + _ssh_string(b"git")
        + _ssh_string(b"")
        + _ssh_string(b"sha512")
        + _ssh_string(signature_blob)
    )
    return _armor(
        body,
        b"-----BEGIN SSH SIGNATURE-----",
        b"-----END SSH SIGNATURE-----",
        70,
        pgp=False,
    )


def _git_object(
    store: dict[str, ParsedProtocolGitObjectV1], object_type: str, raw_content: bytes
) -> ParsedProtocolGitObjectV1:
    wire = object_type.encode("ascii") + b" " + str(len(raw_content)).encode() + b"\0" + raw_content
    oid = hashlib.sha1(wire).hexdigest()
    parsed = parse_protocol_git_object(
        oid=oid,
        object_type=object_type,  # type: ignore[arg-type]
        raw_content=raw_content,
    )
    store.setdefault(parsed.oid, parsed)
    return parsed


def _unchecked_git_object(
    store: dict[str, ParsedProtocolGitObjectV1], object_type: str, raw_content: bytes
) -> ParsedProtocolGitObjectV1:
    wire = object_type.encode("ascii") + b" " + str(len(raw_content)).encode() + b"\0" + raw_content
    item = ParsedProtocolGitObjectV1(
        oid=hashlib.sha1(wire).hexdigest(),
        object_type=object_type,  # type: ignore[arg-type]
        size=len(raw_content),
        git_object_sha256=hashlib.sha256(wire).hexdigest(),
        raw_content=raw_content,
    )
    store[item.oid] = item
    return item


def _tree_for_files(
    store: dict[str, ParsedProtocolGitObjectV1], files: dict[str, bytes]
) -> ParsedProtocolGitObjectV1:
    root: dict[str, Any] = {}
    for path, content in files.items():
        node = root
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = content

    def build(node: dict[str, Any]) -> ParsedProtocolGitObjectV1:
        entries: list[tuple[str, bytes, str]] = []
        for name, value in sorted(
            node.items(),
            key=lambda item: item[0].encode() + (b"/" if isinstance(item[1], dict) else b""),
        ):
            if isinstance(value, dict):
                child = build(value)
                entries.append(("40000", name.encode(), child.oid))
            else:
                child = _git_object(store, "blob", value)
                entries.append(("100644", name.encode(), child.oid))
        raw = b"".join(
            mode.encode() + b" " + name + b"\0" + bytes.fromhex(oid) for mode, name, oid in entries
        )
        return _git_object(store, "tree", raw)

    return build(root)


def _tree_from_entries(
    store: dict[str, ParsedProtocolGitObjectV1],
    entries: tuple[tuple[str, bytes, str], ...],
) -> ParsedProtocolGitObjectV1:
    ordered = tuple(
        sorted(
            entries,
            key=lambda item: item[1] + (b"/" if item[0] == "40000" else b""),
        )
    )
    raw = b"".join(
        mode.encode("ascii") + b" " + name + b"\0" + bytes.fromhex(oid)
        for mode, name, oid in ordered
    )
    return _git_object(store, "tree", raw)


def _rewrite_tree_path(
    store: dict[str, ParsedProtocolGitObjectV1],
    root_oid: str,
    path: str,
    replacement: tuple[str, str] | None,
) -> str:
    parts = path.encode("utf-8").split(b"/")

    def rewrite(tree_oid: str, ordinal: int) -> str:
        tree = store[tree_oid]
        entries = list(audit_module._parse_tree_entries(tree.raw_content))
        name = parts[ordinal]
        selected = next((item for item in entries if item[1] == name), None)
        if ordinal + 1 == len(parts):
            entries = [item for item in entries if item[1] != name]
            if replacement is not None:
                entries.append((replacement[0], name, replacement[1]))
            return _tree_from_entries(store, tuple(entries)).oid
        if selected is None or selected[0] != "40000":
            empty = _tree_for_files(store, {})
            child_oid = empty.oid
        else:
            child_oid = selected[2]
        rewritten_child = rewrite(child_oid, ordinal + 1)
        entries = [item for item in entries if item[1] != name]
        entries.append(("40000", name, rewritten_child))
        return _tree_from_entries(store, tuple(entries)).oid

    return rewrite(root_oid, 0)


def _reachable_store(
    store: dict[str, ParsedProtocolGitObjectV1],
    *,
    roots: tuple[str, ...],
) -> dict[str, ParsedProtocolGitObjectV1]:
    selected: dict[str, ParsedProtocolGitObjectV1] = {}
    pending = list(roots)
    while pending:
        oid = pending.pop()
        if oid in selected:
            continue
        item = store[oid]
        selected[oid] = item
        if item.object_type == "commit":
            view = audit_module._parse_commit_view(item)
            pending.extend(view.parent_oids)
            pending.append(view.tree_oid)
        elif item.object_type == "tree":
            pending.extend(
                child_oid
                for _, _, child_oid in audit_module._parse_tree_entries(item.raw_content)
            )
    return selected


def _unsigned_commit(
    store: dict[str, ParsedProtocolGitObjectV1],
    *,
    tree_oid: str,
    parents: tuple[str, ...],
    message: str,
) -> ParsedProtocolGitObjectV1:
    headers = [b"tree " + tree_oid.encode()]
    headers.extend(b"parent " + parent.encode() for parent in parents)
    identity = b"Audit Merge Bot <audit-merge@users.noreply.github.com> 1788134400 +0000"
    headers.extend((b"author " + identity, b"committer " + identity))
    return _git_object(store, "commit", b"\n".join(headers) + b"\n\n" + message.encode() + b"\n")


@dataclass(frozen=True)
class _SignedHead:
    commit: ParsedProtocolGitObjectV1
    base_oid: str
    signed_payload: bytes
    signature: bytes
    signer_id: int
    signer_login: str
    mode: str
    fingerprint: str | None


def _signed_head(
    store: dict[str, ParsedProtocolGitObjectV1],
    *,
    tree_oid: str,
    base_oid: str,
    signer_id: int,
    signer_login: str,
    mode: str,
    fingerprint: str | None,
    git_identity: tuple[str, str, str, str] | None,
    message: str,
    parents: tuple[str, ...] | None = None,
) -> _SignedHead:
    if git_identity is None:
        author_name = committer_name = "Audit GitHub Signer"
        author_email = committer_email = "audit-github@users.noreply.github.com"
    else:
        author_name, author_email, committer_name, committer_email = git_identity
    parent_oids = (base_oid,) if parents is None else parents
    headers = b"tree " + tree_oid.encode() + b"\n"
    headers += b"".join(b"parent " + parent.encode() + b"\n" for parent in parent_oids)
    headers += f"author {author_name} <{author_email}> 1788134400 +0000\n".encode()
    headers += f"committer {committer_name} <{committer_email}> 1788134400 +0000".encode()
    signed_payload = headers + b"\n\n" + message.encode() + b"\n"
    signature = _ssh_signature(signed_payload) if mode == "ssh_sha256" else _github_signature()
    signature_header = b"\ngpgsig " + signature.replace(b"\n", b"\n ")
    commit = _git_object(
        store,
        "commit",
        headers + signature_header + b"\n\n" + message.encode() + b"\n",
    )
    return _SignedHead(
        commit=commit,
        base_oid=base_oid,
        signed_payload=signed_payload,
        signature=signature,
        signer_id=signer_id,
        signer_login=signer_login,
        mode=mode,
        fingerprint=fingerprint,
    )


def _signature_material(
    head: _SignedHead,
    *,
    statement_path: str,
    identity_bundle: Any,
    signing_key: Any | None,
    ordinal: int,
) -> SimpleNamespace:
    rest_payload: dict[str, Any] = {
        "schema_version": "GitHubCommitVerificationProjectionV1",
        "repository_id": 123,
        "commit_oid": head.commit.oid,
        "api_version": "2022-11-28",
        "endpoint": f"GET /repos/acme/laconian/git/commits/{head.commit.oid}",
        "verified": True,
        "reason": "valid",
        "payload": head.signed_payload.decode(),
        "signature": head.signature.decode(),
        "verified_at": "2026-08-31T00:00:00.000000Z",
    }
    rest = GitHubCommitVerificationProjectionV1.model_validate(
        _protocol_digest(
            "laconian-github-commit-verification-projection-v1",
            rest_payload,
            "rest_projection_sha256",
        )
    )
    graphql_payload: dict[str, Any] = {
        "schema_version": "GitHubSignatureProjectionV1",
        "repository_id": 123,
        "commit_oid": head.commit.oid,
        "query_sha256": GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
        "signer_database_id": head.signer_id,
        "signer_login": head.signer_login,
        "is_valid": True,
        "state": "VALID",
    }
    graphql = GitHubSignatureProjectionV1.model_validate(
        _protocol_digest(
            "laconian-github-signature-projection-v1",
            graphql_payload,
            "graphql_projection_sha256",
        )
    )
    raw_rest = canonical_json_v1(
        {
            "sha": head.commit.oid,
            "verification": {
                "verified": True,
                "reason": "valid",
                "payload": head.signed_payload.decode(),
                "signature": head.signature.decode(),
                "verified_at": "2026-08-31T03:00:00+03:00",
                "ignored": ordinal,
            },
        }
    )
    raw_graphql = canonical_json_v1(
        {
            "data": {
                "repository": {
                    "databaseId": 123,
                    "object": {
                        "oid": head.commit.oid,
                        "signature": {
                            "isValid": True,
                            "state": "VALID",
                            "signer": {
                                "databaseId": head.signer_id,
                                "login": head.signer_login,
                                "ignored": ordinal,
                            },
                        },
                    },
                }
            }
        }
    )
    canonical = (
        canonical_json_v1(rest.model_dump(mode="json")),
        canonical_json_v1(graphql.model_dump(mode="json")),
    )
    receipt_payload: dict[str, Any] = {
        "schema_version": "GitHubSignatureObservationReceiptV1",
        "repository_id": 123,
        "commit_oid": head.commit.oid,
        "rest_projection_sha256": rest.rest_projection_sha256,
        "graphql_projection_sha256": graphql.graphql_projection_sha256,
        "observed_at": "2026-08-31T00:00:00.000000Z",
        "request_ids": (f"audit-rest-{ordinal}", f"audit-graphql-{ordinal}"),
        "etags": (f'"audit-rest-{ordinal}"', f'"audit-graphql-{ordinal}"'),
        "raw_response_sha256s": (
            hashlib.sha256(raw_rest).hexdigest(),
            hashlib.sha256(raw_graphql).hexdigest(),
        ),
        "canonical_response_sha256s": tuple(hashlib.sha256(item).hexdigest() for item in canonical),
        "tls_endpoint_identity": "api.github.com:443",
    }
    receipt = GitHubSignatureObservationReceiptV1.model_validate(
        _protocol_digest(
            "laconian-github-signature-observation-receipt-v1",
            receipt_payload,
            "github_signature_observation_receipt_sha256",
        )
    )
    common: dict[str, Any] = {
        "commit_oid": head.commit.oid,
        "commit_object_sha256": head.commit.git_object_sha256,
        "parent_commit_oid": head.base_oid,
        "statement_path": statement_path,
        "github_rest_verification": rest.model_dump(mode="json"),
        "github_graphql_signature": graphql.model_dump(mode="json"),
    }
    if head.mode == "github_verified_commit":
        evidence: Any = GitHubVerifiedCommitEvidenceV1.model_validate(
            {
                "schema_version": "GitHubVerifiedCommitEvidenceV1",
                "verification_mode": "github_verified_commit",
                **common,
            }
        )
    else:
        assert signing_key is not None
        local_payload: dict[str, Any] = {
            "verified": True,
            "signed_payload_sha256": hashlib.sha256(head.signed_payload).hexdigest(),
            "signature_sha256": hashlib.sha256(head.signature).hexdigest(),
            "verifier_tool_sha256": identity_bundle.protocol_signature_verifier_tool_sha256,
        }
        local = LocalSignatureVerificationReceiptV1.model_validate(
            _protocol_digest(
                "laconian-local-signature-verification-receipt-v1",
                local_payload,
                "verification_receipt_sha256",
            )
        )
        evidence = SSHVerifiedCommitEvidenceV1.model_validate(
            {
                "schema_version": "SSHVerifiedCommitEvidenceV1",
                "verification_mode": "ssh_sha256",
                **common,
                "fingerprint": signing_key.fingerprint,
                "keyring_sha256": signing_key.public_key_sha256,
                "local_signature_verification": local.model_dump(mode="json"),
            }
        )
    return SimpleNamespace(
        evidence=evidence,
        receipt=receipt,
        raw=(raw_rest, raw_graphql),
        canonical=canonical,
    )


def _audit_receipt(
    *,
    kind: str,
    endpoint: str,
    raw: bytes,
    ordinal: int,
    observed_at: str,
) -> GitHubAuditApiObservationReceiptV1:
    payload: dict[str, Any] = {
        "schema_version": "audit-github-api-observation-receipt-v1",
        "source_kind": kind,
        "repository_id": 123,
        "endpoint": endpoint,
        "api_version": "2022-11-28",
        "observed_at_utc": observed_at,
        "request_id": f"audit-api-{ordinal}",
        "etag": f'"audit-api-{ordinal}"',
        "raw_response_byte_length": len(raw),
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "tls_endpoint_identity": "api.github.com:443",
    }
    return GitHubAuditApiObservationReceiptV1.model_validate(
        _digest(
            "laconian-audit-github-api-observation-receipt-v1",
            payload,
            "github_audit_api_observation_receipt_sha256",
        )
    )


def _pr_record(
    *,
    pr_number: int,
    actor_id: int,
    actor_login: str,
    head_oid: str,
    merge_oid: str,
    merged_at: str,
) -> tuple[ExactGitHubPullRequestRecordV1, bytes]:
    raw = canonical_json_v1(
        {
            "number": pr_number,
            "user": {"id": actor_id, "login": actor_login},
            "base": {
                "ref": "main",
                "repo": {"id": 123, "name": "laconian", "owner": {"login": "acme"}},
            },
            "head": {"sha": head_oid},
            "merge_commit_sha": merge_oid,
            "merged_by": {"id": 901, "login": "audit-merge-bot"},
            "state": "closed",
            "merged": True,
            "merged_at": merged_at,
            "ignored_provider_field": "not-authority",
        }
    )
    payload: dict[str, Any] = {
        "schema_version": "audit-github-pull-request-record-v1",
        "repository_id": 123,
        "pr_number": pr_number,
        "actor_account_id": actor_id,
        "actor": actor_login,
        "base_ref": "main",
        "head_sha": head_oid,
        "merge_commit_sha": merge_oid,
        "merge_actor_account_id": 901,
        "merge_actor": "audit-merge-bot",
        "state": "closed",
        "merged": True,
        "merged_at_utc": merged_at,
    }
    record = ExactGitHubPullRequestRecordV1.model_validate(
        _digest(
            "laconian-audit-github-pull-request-record-v1",
            payload,
            "exact_api_record_sha256",
        )
    )
    return record, raw


def _pull_request_source_and_proof(
    *,
    kind: str,
    reviewer_id: str | None,
    campaign_id: str,
    head: _SignedHead,
    merge: ParsedProtocolGitObjectV1,
    pr_number: int,
    merged_at: str,
    changed_paths: tuple[str, ...],
    identity_bundle: Any,
    signing_key: Any | None,
    ordinal: int,
) -> tuple[AuditPullRequestEvidenceSourceV1, PullRequestProofV1]:
    signature = _signature_material(
        head,
        statement_path=changed_paths[-1],
        identity_bundle=identity_bundle,
        signing_key=signing_key,
        ordinal=ordinal,
    )
    record, raw_pr = _pr_record(
        pr_number=pr_number,
        actor_id=head.signer_id,
        actor_login=head.signer_login,
        head_oid=head.commit.oid,
        merge_oid=merge.oid,
        merged_at=merged_at,
    )
    receipt = _audit_receipt(
        kind="pull_request",
        endpoint=f"GET /repos/acme/laconian/pulls/{pr_number}",
        raw=raw_pr,
        ordinal=ordinal,
        observed_at=merged_at,
    )
    source_payload: dict[str, Any] = {
        "schema_version": "audit-pull-request-source-v1",
        "proof_kind": kind,
        "campaign_id": campaign_id,
        "reviewer_id": reviewer_id,
        "pull_request_record": record.model_dump(mode="json"),
        "pull_request_observation_receipt": receipt.model_dump(mode="json"),
        "pull_request_raw_response_base64": base64.b64encode(raw_pr).decode(),
        "signature_observation_receipt": signature.receipt.model_dump(mode="json"),
        "signature_evidence": signature.evidence.model_dump(mode="json"),
        "signature_raw_response_byte_lengths": tuple(map(len, signature.raw)),
        "signature_raw_response_bytes_base64": tuple(
            base64.b64encode(item).decode() for item in signature.raw
        ),
        "signature_canonical_response_byte_lengths": tuple(map(len, signature.canonical)),
        "signature_canonical_response_bytes_base64": tuple(
            base64.b64encode(item).decode() for item in signature.canonical
        ),
    }
    source_payload = _digest(
        "laconian-audit-pull-request-source-v1",
        source_payload,
        "pull_request_source_sha256",
    )
    source = AuditPullRequestEvidenceSourceV1.model_validate_json(canonical_json_v1(source_payload))
    proof_payload: dict[str, Any] = {
        "schema_version": "audit-pull-request-proof-v1",
        "proof_kind": kind,
        "campaign_id": campaign_id,
        "reviewer_id": reviewer_id,
        "repository_id": 123,
        "pr_number": pr_number,
        "actor_account_id": head.signer_id,
        "actor": head.signer_login,
        "base_ref": "main",
        "base_sha": head.base_oid,
        "head_sha": head.commit.oid,
        "merge_commit_sha": merge.oid,
        "merge_actor_account_id": 901,
        "merge_actor": "audit-merge-bot",
        "merged_at_utc": merged_at,
        "verification_mode": head.mode,
        "head_signing_fingerprint": head.fingerprint,
        "signature_evidence": signature.evidence.model_dump(mode="json"),
        "changed_paths": changed_paths,
        "exact_pr_api_record_sha256": record.exact_api_record_sha256,
        "pull_request_source_sha256": source.pull_request_source_sha256,
    }
    proof = PullRequestProofV1.model_validate(
        _digest(
            "laconian-audit-pull-request-proof-v1",
            proof_payload,
            "pull_request_proof_sha256",
        )
    )
    return source, proof


def _review_source_and_signoff(
    *,
    reviewer: Any,
    core: AuditAdjudicationCoreV1,
    adjudication_pr: PullRequestProofV1,
    registry_sha256: str,
    review_id: int,
    submitted_at: str,
) -> tuple[ExactGitHubReviewSourceV1, ExactGitHubReviewSignoffV1]:
    body = f"laconian-audit-adjudication-core-v1\0{core.adjudication_core_sha256}\n"
    raw = canonical_json_v1(
        {
            "id": review_id,
            "user": {
                "id": reviewer.reviewer_numeric_account_id,
                "login": reviewer.reviewer_login,
            },
            "body": body,
            "state": "APPROVED",
            "commit_id": adjudication_pr.head_sha,
            "submitted_at": submitted_at,
            "ignored_provider_field": True,
        }
    )
    record_payload: dict[str, Any] = {
        "schema_version": "audit-github-review-record-v1",
        "repository_id": 123,
        "pr_number": adjudication_pr.pr_number,
        "review_id": review_id,
        "actor_account_id": reviewer.reviewer_numeric_account_id,
        "actor_login": reviewer.reviewer_login,
        "reviewed_head_sha": adjudication_pr.head_sha,
        "body": body,
        "state": "APPROVED",
        "submitted_at_utc": submitted_at,
    }
    record = ExactGitHubReviewRecordV1.model_validate(
        _digest(
            "laconian-audit-github-review-record-v1",
            record_payload,
            "exact_api_record_sha256",
        )
    )
    endpoint = f"GET /repos/acme/laconian/pulls/{adjudication_pr.pr_number}/reviews/{review_id}"
    receipt = _audit_receipt(
        kind="review",
        endpoint=endpoint,
        raw=raw,
        ordinal=100 + review_id,
        observed_at=submitted_at,
    )
    source_payload: dict[str, Any] = {
        "schema_version": "audit-github-review-source-v1",
        "reviewer_id": reviewer.reviewer_id,
        "record": record.model_dump(mode="json"),
        "observation_receipt": receipt.model_dump(mode="json"),
        "raw_response_base64": base64.b64encode(raw).decode(),
    }
    source = ExactGitHubReviewSourceV1.model_validate(
        _digest(
            "laconian-audit-github-review-source-v1",
            source_payload,
            "github_review_source_sha256",
        )
    )
    signoff_payload: dict[str, Any] = {
        "schema_version": "audit-adjudication-github-review-v1",
        "reviewer_id": reviewer.reviewer_id,
        "reviewer_numeric_account_id": reviewer.reviewer_numeric_account_id,
        "reviewer_login": reviewer.reviewer_login,
        "audit_reviewer_registry_sha256": registry_sha256,
        "adjudication_core_sha256": core.adjudication_core_sha256,
        "repository_id": 123,
        "pr_number": adjudication_pr.pr_number,
        "review_id": review_id,
        "state": "APPROVED",
        "reviewed_head_sha": adjudication_pr.head_sha,
        "submitted_at_utc": submitted_at,
        "fixed_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "exact_api_record_sha256": record.exact_api_record_sha256,
        "github_review_source_sha256": source.github_review_source_sha256,
    }
    signoff = ExactGitHubReviewSignoffV1.model_validate(
        _digest(
            "laconian-audit-adjudication-github-review-v1",
            signoff_payload,
            "signoff_proof_sha256",
        )
    )
    return source, signoff


def _archive(
    store: dict[str, ParsedProtocolGitObjectV1],
) -> AuditGitObjectArchiveV1:
    objects = tuple(
        ArchivedProtocolGitObjectV1(
            oid=item.oid,
            type=item.object_type,
            size=item.size,
            git_object_sha256=item.git_object_sha256,
            raw_content_base64=base64.b64encode(item.raw_content).decode(),
        )
        for item in sorted(store.values(), key=lambda candidate: candidate.oid)
    )
    closure = [
        {
            "oid": item.oid,
            "type": item.type,
            "size": item.size,
            "git_object_sha256": item.git_object_sha256,
        }
        for item in objects
    ]
    payload: dict[str, Any] = {
        "schema_version": "audit-git-object-archive-v1",
        "object_closure_root": stable_digest("laconian-audit-git-object-closure-v1", closure),
        "objects": tuple(item.model_dump(mode="json") for item in objects),
    }
    payload = _digest(
        "laconian-audit-git-object-archive-v1",
        payload,
        "audit_git_object_archive_sha256",
    )
    return AuditGitObjectArchiveV1.model_validate_json(canonical_json_v1(payload))


@dataclass(frozen=True)
class _AuditFixture:
    provider: Any
    sample: VerifiedAuditSampleRootV1
    registry: Any
    store: dict[str, ParsedProtocolGitObjectV1]
    archive: AuditGitObjectArchiveV1
    chains: tuple[ReviewerChainV1, ReviewerChainV1]
    adjudication: AuditAdjudicationV1
    pull_request_sources: tuple[
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
    ]
    github_review_sources: tuple[ExactGitHubReviewSourceV1, ExactGitHubReviewSourceV1]
    heads: tuple[_SignedHead, _SignedHead, _SignedHead, _SignedHead, _SignedHead]
    merges: tuple[
        ParsedProtocolGitObjectV1,
        ParsedProtocolGitObjectV1,
        ParsedProtocolGitObjectV1,
        ParsedProtocolGitObjectV1,
        ParsedProtocolGitObjectV1,
    ]


def _labels(
    sample: VerifiedAuditSampleRootV1, *, reviewer_ordinal: int
) -> tuple[HumanAuditLabelV1, ...]:
    labels: list[HumanAuditLabelV1] = []
    for record in sample.packet.records:
        rubric = tuple(
            RubricItemJudgmentV1(
                item_index=item.item_index,
                passed=True,
                evidence=f"reviewer {reviewer_ordinal}: доказано",
            )
            for item in record.rubric
        )
        warning = (
            None
            if record.material_warning_requirement is None
            else WarningJudgmentV1(passed=True, evidence="warning requirement satisfied")
        )
        labels.append(
            HumanAuditLabelV1(
                audit_record_id=record.audit_record_id,
                rubric_items=rubric,
                material_warning=warning,
                material_contradiction=False,
                contradiction_evidence=None,
                semantic_pass=True,
            )
        )
    return tuple(labels)


def _build_source_backed_audit(
    *, provider: Any, sample: VerifiedAuditSampleRootV1
) -> _AuditFixture:
    registry = provider.index.audit_reviewer_registry
    campaign_id = provider.index.campaign_id
    campaign_registry = provider.generation_context.index.campaign_registry_sha256
    commit_protocol = provider.index.audit_commit_reveal_protocol_sha256
    registry_sha = registry.audit_reviewer_registry_sha256
    sample_sha = sample.manifest.sample_manifest_sha256
    reviewers = registry.reviewers

    commitments: list[ReviewerCommitmentV1] = []
    reveals: list[ReviewerRevealV1] = []
    for ordinal, reviewer in enumerate(reviewers):
        header = CommitmentHeaderV1(
            schema_version="audit-commitment-v1",
            campaign_id=campaign_id,
            campaign_registry_sha256=campaign_registry,
            reviewer_id=reviewer.reviewer_id,
            audit_reviewer_registry_sha256=registry_sha,
            sample_manifest_sha256=sample_sha,
            audit_commit_reveal_protocol_sha256=commit_protocol,
        )
        labels = _labels(sample, reviewer_ordinal=ordinal)
        label_bytes = canonical_label_jsonl(labels)
        salt = bytes([41 + ordinal]) * 32
        commitment = ReviewerCommitmentV1(
            header=header,
            commitment_sha256=compute_commitment(
                header=header,
                salt=salt,
                exact_label_bytes=label_bytes,
            ),
        )
        reveal_payload: dict[str, Any] = {
            "schema_version": "audit-reveal-v1",
            "campaign_id": campaign_id,
            "campaign_registry_sha256": campaign_registry,
            "reviewer_id": reviewer.reviewer_id,
            "audit_reviewer_registry_sha256": registry_sha,
            "sample_manifest_sha256": sample_sha,
            "audit_commit_reveal_protocol_sha256": commit_protocol,
            "commitment_sha256": commitment.commitment_sha256,
            "salt_hex": salt.hex(),
            "labels_byte_length": len(label_bytes),
            "labels_sha256": hashlib.sha256(label_bytes).hexdigest(),
            "labels": tuple(item.model_dump(mode="json") for item in labels),
        }
        reveal_payload = _digest("laconian-audit-reveal-v1", reveal_payload, "reveal_sha256")
        reveal = ReviewerRevealV1.model_validate_json(canonical_json_v1(reveal_payload))
        commitments.append(commitment)
        reveals.append(reveal)

    consensus = tuple(
        ConsensusLabelV1(
            audit_record_id=record.audit_record_id,
            semantic_pass=True,
            resolution="reviewer-agreement",
            rationale=None,
        )
        for record in sample.packet.records
    )
    core_payload: dict[str, Any] = {
        "schema_version": "audit-adjudication-core-v1",
        "campaign_id": campaign_id,
        "campaign_registry_sha256": campaign_registry,
        "audit_reviewer_registry_sha256": registry_sha,
        "sample_manifest_sha256": sample_sha,
        "audit_commit_reveal_protocol_sha256": commit_protocol,
        "audit_adjudication_protocol_sha256": provider.index.audit_adjudication_protocol_sha256,
        "reveal_sha256s": tuple(item.reveal_sha256 for item in reveals),
        "consensus": tuple(item.model_dump(mode="json") for item in consensus),
        "judge_labels_were_available": False,
    }
    core_payload = _digest(
        "laconian-audit-adjudication-core-v1",
        core_payload,
        "adjudication_core_sha256",
    )
    core = AuditAdjudicationCoreV1.model_validate_json(canonical_json_v1(core_payload))

    root = f"benchmarks/audits/{campaign_id}"
    paths = (
        (f"{root}/commitments/{reviewers[0].reviewer_id}.json",),
        (f"{root}/commitments/{reviewers[1].reviewer_id}.json",),
        (
            f"{root}/reveals/{reviewers[0].reviewer_id}/labels.jsonl",
            f"{root}/reveals/{reviewers[0].reviewer_id}/reveal.json",
        ),
        (
            f"{root}/reveals/{reviewers[1].reviewer_id}/labels.jsonl",
            f"{root}/reveals/{reviewers[1].reviewer_id}/reveal.json",
        ),
        (f"{root}/adjudication-core.json",),
    )
    additions = (
        {paths[0][0]: canonical_json_v1(commitments[0].model_dump(mode="json")) + b"\n"},
        {paths[1][0]: canonical_json_v1(commitments[1].model_dump(mode="json")) + b"\n"},
        {
            paths[2][0]: canonical_label_jsonl(reveals[0].labels),
            paths[2][1]: canonical_json_v1(reveals[0].model_dump(mode="json")) + b"\n",
        },
        {
            paths[3][0]: canonical_label_jsonl(reveals[1].labels),
            paths[3][1]: canonical_json_v1(reveals[1].model_dump(mode="json")) + b"\n",
        },
        {paths[4][0]: canonical_json_v1(core.model_dump(mode="json")) + b"\n"},
    )
    store: dict[str, ParsedProtocolGitObjectV1] = {}
    empty_tree = _tree_for_files(store, {})
    base = _unsigned_commit(store, tree_oid=empty_tree.oid, parents=(), message="audit base")
    files: dict[str, bytes] = {}
    bases: list[ParsedProtocolGitObjectV1] = []
    heads: list[_SignedHead] = []
    merges: list[ParsedProtocolGitObjectV1] = []
    current = base
    signer_specs = (
        (reviewers[0], reviewers[0].signing_key),
        (reviewers[1], reviewers[1].signing_key),
        (reviewers[0], reviewers[0].signing_key),
        (reviewers[1], reviewers[1].signing_key),
        (None, None),
    )
    for ordinal, (added, signer_spec) in enumerate(zip(additions, signer_specs, strict=True)):
        files.update(added)
        tree = _tree_for_files(store, files)
        reviewer, signing_key = signer_spec
        if reviewer is None:
            signer_id, signer_login = 999, "audit-adjudicator"
            mode, fingerprint, identity = "github_verified_commit", None, None
        else:
            signer_id = reviewer.reviewer_numeric_account_id
            signer_login = reviewer.reviewer_login
            mode = reviewer.verification_mode
            fingerprint = reviewer.signing_fingerprint
            identity = (
                None
                if signing_key is None
                else (
                    signing_key.author_name_ascii,
                    signing_key.author_email_ascii,
                    signing_key.committer_name_ascii,
                    signing_key.committer_email_ascii,
                )
            )
        head = _signed_head(
            store,
            tree_oid=tree.oid,
            base_oid=current.oid,
            signer_id=signer_id,
            signer_login=signer_login,
            mode=mode,
            fingerprint=fingerprint,
            git_identity=identity,
            message=f"audit pull request {ordinal + 1}",
        )
        merge = _unsigned_commit(
            store,
            tree_oid=tree.oid,
            parents=(current.oid, head.commit.oid),
            message=f"merge audit pull request {ordinal + 1}",
        )
        bases.append(current)
        heads.append(head)
        merges.append(merge)
        current = merge

    kinds = ("commitment", "commitment", "reveal", "reveal", "adjudication")
    reviewer_ids = (
        reviewers[0].reviewer_id,
        reviewers[1].reviewer_id,
        reviewers[0].reviewer_id,
        reviewers[1].reviewer_id,
        None,
    )
    signing_keys = (
        reviewers[0].signing_key,
        reviewers[1].signing_key,
        reviewers[0].signing_key,
        reviewers[1].signing_key,
        None,
    )
    source_proofs = tuple(
        _pull_request_source_and_proof(
            kind=kind,
            reviewer_id=reviewer_id,
            campaign_id=campaign_id,
            head=head,
            merge=merge,
            pr_number=101 + ordinal,
            merged_at=f"2026-08-31T00:00:{10 * (ordinal + 1):02d}Z",
            changed_paths=path,
            identity_bundle=provider.identity_registry_bundle,
            signing_key=signing_key,
            ordinal=ordinal,
        )
        for ordinal, (kind, reviewer_id, head, merge, path, signing_key) in enumerate(
            zip(kinds, reviewer_ids, heads, merges, paths, signing_keys, strict=True)
        )
    )
    sources = tuple(item[0] for item in source_proofs)
    proofs = tuple(item[1] for item in source_proofs)
    identities = tuple(
        ReviewerIdentityV1(
            reviewer_id=reviewer.reviewer_id,
            reviewer_numeric_account_id=reviewer.reviewer_numeric_account_id,
            reviewer_login=reviewer.reviewer_login,
            verification_mode=reviewer.verification_mode,
            signing_fingerprint=reviewer.signing_fingerprint,
            audit_reviewer_registry_sha256=registry_sha,
        )
        for reviewer in reviewers
    )
    chains: list[ReviewerChainV1] = []
    for ordinal in range(2):
        chain_payload: dict[str, Any] = {
            "identity": identities[ordinal].model_dump(mode="json"),
            "commitment": commitments[ordinal].model_dump(mode="json"),
            "commitment_pr": proofs[ordinal].model_dump(mode="json"),
            "reveal": reveals[ordinal].model_dump(mode="json"),
            "reveal_pr": proofs[2 + ordinal].model_dump(mode="json"),
        }
        chain_payload = _digest(
            "laconian-audit-reviewer-chain-proof-v1",
            chain_payload,
            "reviewer_chain_proof_sha256",
        )
        chains.append(ReviewerChainV1.model_validate_json(canonical_json_v1(chain_payload)))

    review_pairs = tuple(
        _review_source_and_signoff(
            reviewer=reviewer,
            core=core,
            adjudication_pr=proofs[4],
            registry_sha256=registry_sha,
            review_id=701 + ordinal,
            submitted_at=f"2026-08-31T00:00:{45 + ordinal:02d}Z",
        )
        for ordinal, reviewer in enumerate(reviewers)
    )
    review_sources = tuple(item[0] for item in review_pairs)
    signoffs = tuple(item[1] for item in review_pairs)
    adjudication_payload: dict[str, Any] = {
        "schema_version": "audit-adjudication-v1",
        "core": core.model_dump(mode="json"),
        "signoffs": tuple(item.model_dump(mode="json") for item in signoffs),
        "adjudication_pr": proofs[4].model_dump(mode="json"),
    }
    adjudication_payload = _digest(
        "laconian-audit-adjudication-v1",
        adjudication_payload,
        "adjudication_sha256",
    )
    adjudication = AuditAdjudicationV1.model_validate_json(canonical_json_v1(adjudication_payload))
    return _AuditFixture(
        provider=provider,
        sample=sample,
        registry=registry,
        store=store,
        archive=_archive(store),
        chains=(chains[0], chains[1]),
        adjudication=adjudication,
        pull_request_sources=sources,  # type: ignore[arg-type]
        github_review_sources=review_sources,  # type: ignore[arg-type]
        heads=tuple(heads),  # type: ignore[arg-type]
        merges=tuple(merges),  # type: ignore[arg-type]
    )


@pytest.fixture(scope="module")
def provider_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> CompleteProviderEvidenceFixture:
    return get_cached_complete_provider_evidence_fixture(tmp_path_factory)


@pytest.fixture(scope="module")
def audit_fixture(
    provider_fixture: CompleteProviderEvidenceFixture,
    tmp_path_factory: pytest.TempPathFactory,
) -> _AuditFixture:
    provider = provider_fixture.provider_evidence
    assert provider is not None
    population = build_audit_population(provider_evidence=provider)
    manifest, packet = select_audit_sample(
        population=population,
        provider_evidence=provider,
    )
    sample = write_audit_sample_root(
        tmp_path_factory.mktemp("task9-audit-sample") / "sample-root",
        population=population,
        manifest=manifest,
        packet=packet,
        provider_evidence=provider,
    )
    return _build_source_backed_audit(provider=provider, sample=sample)


@pytest.fixture(autouse=True)
def verified_dependency_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = Path(__file__).resolve().parents[2]
    verified = (
        (project_root / "src/laconian_eval/benchmark/protocol_review.py").read_bytes(),
        (project_root / "uv.lock").read_bytes(),
    )
    monkeypatch.setattr(protocol_module, "_verify_active_verifier_runtime", lambda _: verified)


def _verify(
    fixture: _AuditFixture,
    *,
    chains: tuple[ReviewerChainV1, ReviewerChainV1] | None = None,
    adjudication: AuditAdjudicationV1 | None = None,
    archive: AuditGitObjectArchiveV1 | None = None,
    pull_request_sources: tuple[
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
    ]
    | None = None,
    github_review_sources: tuple[ExactGitHubReviewSourceV1, ExactGitHubReviewSourceV1]
    | None = None,
) -> None:
    verify_audit_chain(
        chains=fixture.chains if chains is None else chains,
        adjudication=fixture.adjudication if adjudication is None else adjudication,
        sample=fixture.sample,
        provider_evidence=fixture.provider,
        audit_git_object_archive=fixture.archive if archive is None else archive,
        pull_request_sources=(
            fixture.pull_request_sources if pull_request_sources is None else pull_request_sources
        ),
        github_review_sources=(
            fixture.github_review_sources
            if github_review_sources is None
            else github_review_sources
        ),
    )


def _chain_with(
    chain: ReviewerChainV1,
    **updates: Any,
) -> ReviewerChainV1:
    return _rehash(
        chain,
        "laconian-audit-reviewer-chain-proof-v1",
        "reviewer_chain_proof_sha256",
        **updates,
    )


def _adjudication_with(
    adjudication: AuditAdjudicationV1,
    **updates: Any,
) -> AuditAdjudicationV1:
    return _rehash(
        adjudication,
        "laconian-audit-adjudication-v1",
        "adjudication_sha256",
        **updates,
    )


def _source_with_pr_raw(
    source: AuditPullRequestEvidenceSourceV1,
    raw: bytes,
    *,
    endpoint: str | None = None,
) -> AuditPullRequestEvidenceSourceV1:
    receipt = _rehash(
        source.pull_request_observation_receipt,
        "laconian-audit-github-api-observation-receipt-v1",
        "github_audit_api_observation_receipt_sha256",
        endpoint=(
            source.pull_request_observation_receipt.endpoint if endpoint is None else endpoint
        ),
        raw_response_byte_length=len(raw),
        raw_response_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return _rehash(
        source,
        "laconian-audit-pull-request-source-v1",
        "pull_request_source_sha256",
        pull_request_observation_receipt=receipt,
        pull_request_raw_response_base64=base64.b64encode(raw).decode(),
    )


def _source_with_signature_raw(
    source: AuditPullRequestEvidenceSourceV1,
    raw_pair: tuple[bytes, bytes],
) -> AuditPullRequestEvidenceSourceV1:
    receipt_payload = source.signature_observation_receipt.model_dump(
        mode="json",
        exclude={"github_signature_observation_receipt_sha256"},
    )
    receipt_payload["raw_response_sha256s"] = tuple(
        hashlib.sha256(item).hexdigest() for item in raw_pair
    )
    receipt_payload["github_signature_observation_receipt_sha256"] = protocol_review_digest(
        "laconian-github-signature-observation-receipt-v1", receipt_payload
    )
    receipt = GitHubSignatureObservationReceiptV1.model_validate(receipt_payload)
    return _rehash(
        source,
        "laconian-audit-pull-request-source-v1",
        "pull_request_source_sha256",
        signature_observation_receipt=receipt,
        signature_raw_response_byte_lengths=tuple(map(len, raw_pair)),
        signature_raw_response_bytes_base64=tuple(
            base64.b64encode(item).decode() for item in raw_pair
        ),
    )


def _source_with_signature_canonical(
    source: AuditPullRequestEvidenceSourceV1,
    canonical_pair: tuple[bytes, bytes],
) -> AuditPullRequestEvidenceSourceV1:
    receipt_payload = source.signature_observation_receipt.model_dump(
        mode="json",
        exclude={"github_signature_observation_receipt_sha256"},
    )
    receipt_payload["canonical_response_sha256s"] = tuple(
        hashlib.sha256(item).hexdigest() for item in canonical_pair
    )
    receipt_payload["github_signature_observation_receipt_sha256"] = protocol_review_digest(
        "laconian-github-signature-observation-receipt-v1", receipt_payload
    )
    receipt = GitHubSignatureObservationReceiptV1.model_validate(receipt_payload)
    return _rehash(
        source,
        "laconian-audit-pull-request-source-v1",
        "pull_request_source_sha256",
        signature_observation_receipt=receipt,
        signature_canonical_response_byte_lengths=tuple(map(len, canonical_pair)),
        signature_canonical_response_bytes_base64=tuple(
            base64.b64encode(item).decode() for item in canonical_pair
        ),
    )


def _coherent_repository_id_substitution(
    source: AuditPullRequestEvidenceSourceV1,
    proof: PullRequestProofV1,
    *,
    repository_id: int,
) -> tuple[AuditPullRequestEvidenceSourceV1, PullRequestProofV1]:
    raw_pr_payload = _raw_json(source.pull_request_raw_response_base64)
    raw_pr_payload["base"]["repo"]["id"] = repository_id
    raw_pr = canonical_json_v1(raw_pr_payload)
    pr_record = _rehash(
        source.pull_request_record,
        "laconian-audit-github-pull-request-record-v1",
        "exact_api_record_sha256",
        repository_id=repository_id,
    )
    pr_receipt = _rehash(
        source.pull_request_observation_receipt,
        "laconian-audit-github-api-observation-receipt-v1",
        "github_audit_api_observation_receipt_sha256",
        repository_id=repository_id,
        raw_response_byte_length=len(raw_pr),
        raw_response_sha256=hashlib.sha256(raw_pr).hexdigest(),
    )

    raw_signature = tuple(
        base64.b64decode(value) for value in source.signature_raw_response_bytes_base64
    )
    raw_graphql_payload = _raw_json(source.signature_raw_response_bytes_base64[1])
    raw_graphql_payload["data"]["repository"]["databaseId"] = repository_id
    raw_signature = (raw_signature[0], canonical_json_v1(raw_graphql_payload))
    evidence = source.signature_evidence
    rest_projection = _protocol_rehash(
        evidence.github_rest_verification,
        "laconian-github-commit-verification-projection-v1",
        "rest_projection_sha256",
        repository_id=repository_id,
    )
    graphql_projection = _protocol_rehash(
        evidence.github_graphql_signature,
        "laconian-github-signature-projection-v1",
        "graphql_projection_sha256",
        repository_id=repository_id,
    )
    evidence_payload = evidence.model_dump(mode="json")
    evidence_payload.update(
        {
            "github_rest_verification": rest_projection.model_dump(mode="json"),
            "github_graphql_signature": graphql_projection.model_dump(mode="json"),
        }
    )
    substituted_evidence = type(evidence).model_validate_json(
        canonical_json_v1(evidence_payload)
    )
    canonical_signature = (
        canonical_json_v1(rest_projection.model_dump(mode="json")),
        canonical_json_v1(graphql_projection.model_dump(mode="json")),
    )
    signature_receipt = _protocol_rehash(
        source.signature_observation_receipt,
        "laconian-github-signature-observation-receipt-v1",
        "github_signature_observation_receipt_sha256",
        repository_id=repository_id,
        rest_projection_sha256=rest_projection.rest_projection_sha256,
        graphql_projection_sha256=graphql_projection.graphql_projection_sha256,
        raw_response_sha256s=tuple(
            hashlib.sha256(value).hexdigest() for value in raw_signature
        ),
        canonical_response_sha256s=tuple(
            hashlib.sha256(value).hexdigest() for value in canonical_signature
        ),
    )
    substituted_source = _rehash(
        source,
        "laconian-audit-pull-request-source-v1",
        "pull_request_source_sha256",
        pull_request_record=pr_record,
        pull_request_observation_receipt=pr_receipt,
        pull_request_raw_response_base64=base64.b64encode(raw_pr).decode(),
        signature_observation_receipt=signature_receipt,
        signature_evidence=substituted_evidence,
        signature_raw_response_byte_lengths=tuple(map(len, raw_signature)),
        signature_raw_response_bytes_base64=tuple(
            base64.b64encode(value).decode() for value in raw_signature
        ),
        signature_canonical_response_byte_lengths=tuple(
            map(len, canonical_signature)
        ),
        signature_canonical_response_bytes_base64=tuple(
            base64.b64encode(value).decode() for value in canonical_signature
        ),
    )
    substituted_proof = _rehash(
        proof,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        repository_id=repository_id,
        signature_evidence=substituted_evidence,
        exact_pr_api_record_sha256=pr_record.exact_api_record_sha256,
        pull_request_source_sha256=substituted_source.pull_request_source_sha256,
    )
    return substituted_source, substituted_proof


def _source_with_review_raw(
    source: ExactGitHubReviewSourceV1,
    raw: bytes,
    *,
    endpoint: str | None = None,
) -> ExactGitHubReviewSourceV1:
    receipt = _rehash(
        source.observation_receipt,
        "laconian-audit-github-api-observation-receipt-v1",
        "github_audit_api_observation_receipt_sha256",
        endpoint=source.observation_receipt.endpoint if endpoint is None else endpoint,
        raw_response_byte_length=len(raw),
        raw_response_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return _rehash(
        source,
        "laconian-audit-github-review-source-v1",
        "github_review_source_sha256",
        observation_receipt=receipt,
        raw_response_base64=base64.b64encode(raw).decode(),
    )


def _coherent_review_mutation(
    source: ExactGitHubReviewSourceV1,
    signoff: ExactGitHubReviewSignoffV1,
    *,
    body: str | None = None,
    reviewed_head_sha: str | None = None,
    review_id: int | None = None,
) -> tuple[ExactGitHubReviewSourceV1, ExactGitHubReviewSignoffV1]:
    selected_body = source.record.body if body is None else body
    selected_head = (
        source.record.reviewed_head_sha
        if reviewed_head_sha is None
        else reviewed_head_sha
    )
    selected_review_id = source.record.review_id if review_id is None else review_id
    raw_payload = _raw_json(source.raw_response_base64)
    raw_payload.update(
        {
            "id": selected_review_id,
            "body": selected_body,
            "commit_id": selected_head,
        }
    )
    raw = canonical_json_v1(raw_payload)
    record = _rehash(
        source.record,
        "laconian-audit-github-review-record-v1",
        "exact_api_record_sha256",
        review_id=selected_review_id,
        body=selected_body,
        reviewed_head_sha=selected_head,
    )
    endpoint = source.observation_receipt.endpoint.replace(
        f"/reviews/{source.record.review_id}",
        f"/reviews/{selected_review_id}",
    )
    receipt = _rehash(
        source.observation_receipt,
        "laconian-audit-github-api-observation-receipt-v1",
        "github_audit_api_observation_receipt_sha256",
        endpoint=endpoint,
        raw_response_byte_length=len(raw),
        raw_response_sha256=hashlib.sha256(raw).hexdigest(),
    )
    coherent_source = _rehash(
        source,
        "laconian-audit-github-review-source-v1",
        "github_review_source_sha256",
        record=record,
        observation_receipt=receipt,
        raw_response_base64=base64.b64encode(raw).decode(),
    )
    coherent_signoff = _rehash(
        signoff,
        "laconian-audit-adjudication-github-review-v1",
        "signoff_proof_sha256",
        review_id=selected_review_id,
        reviewed_head_sha=selected_head,
        fixed_body_sha256=hashlib.sha256(selected_body.encode("utf-8")).hexdigest(),
        exact_api_record_sha256=record.exact_api_record_sha256,
        github_review_source_sha256=coherent_source.github_review_source_sha256,
    )
    return coherent_source, coherent_signoff


def _raw_json(value: str) -> dict[str, Any]:
    import json

    parsed = json.loads(base64.b64decode(value).decode())
    assert isinstance(parsed, dict)
    return parsed


def _proof_tuple(fixture: _AuditFixture) -> tuple[PullRequestProofV1, ...]:
    return (
        fixture.chains[0].commitment_pr,
        fixture.chains[1].commitment_pr,
        fixture.chains[0].reveal_pr,
        fixture.chains[1].reveal_pr,
        fixture.adjudication.adjudication_pr,
    )


_UNSET = object()


def _replace_last_pr_graph(
    fixture: _AuditFixture,
    *,
    store: dict[str, ParsedProtocolGitObjectV1] | None = None,
    head_tree_oid: str | None = None,
    head_parents: tuple[str, ...] | None = None,
    merge_parents: tuple[str, ...] | object = _UNSET,
    merge_tree_oid: str | None = None,
) -> tuple[
    tuple[PullRequestProofV1, ...],
    AuditGitObjectArchiveV1,
    dict[str, ParsedProtocolGitObjectV1],
]:
    objects = dict(fixture.store) if store is None else store
    proofs = list(_proof_tuple(fixture))
    original = proofs[-1]
    original_head = objects[original.head_sha]
    selected_tree = (
        audit_module._parse_commit_view(original_head).tree_oid
        if head_tree_oid is None
        else head_tree_oid
    )
    replacement_head = _signed_head(
        objects,
        tree_oid=selected_tree,
        base_oid=original.base_sha,
        signer_id=fixture.heads[-1].signer_id,
        signer_login=fixture.heads[-1].signer_login,
        mode=fixture.heads[-1].mode,
        fingerprint=fixture.heads[-1].fingerprint,
        git_identity=None,
        message="replacement adjudication head",
        parents=head_parents,
    )
    selected_merge_parents = (
        (original.base_sha, replacement_head.commit.oid)
        if merge_parents is _UNSET
        else tuple(
            original.base_sha
            if parent == "{base}"
            else replacement_head.commit.oid
            if parent == "{head}"
            else parent
            for parent in merge_parents
        )
    )
    assert type(selected_merge_parents) is tuple
    replacement_merge = _unsigned_commit(
        objects,
        tree_oid=selected_tree if merge_tree_oid is None else merge_tree_oid,
        parents=selected_merge_parents,
        message="replacement adjudication merge",
    )
    proofs[-1] = _rehash(
        original,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        base_sha=original.base_sha,
        head_sha=replacement_head.commit.oid,
        merge_commit_sha=replacement_merge.oid,
    )
    result = tuple(proofs)
    roots = tuple(oid for proof in result for oid in (proof.head_sha, proof.merge_commit_sha))
    reachable = _reachable_store(objects, roots=roots)
    return result, _archive(reachable), reachable


def _audit_additions(fixture: _AuditFixture) -> tuple[dict[str, bytes], ...]:
    campaign_id = fixture.provider.index.campaign_id
    root = f"benchmarks/audits/{campaign_id}"
    left, right = fixture.chains
    return (
        {
            f"{root}/commitments/{left.identity.reviewer_id}.json": canonical_json_v1(
                left.commitment.model_dump(mode="json")
            )
            + b"\n"
        },
        {
            f"{root}/commitments/{right.identity.reviewer_id}.json": canonical_json_v1(
                right.commitment.model_dump(mode="json")
            )
            + b"\n"
        },
        {
            f"{root}/reveals/{left.identity.reviewer_id}/labels.jsonl": canonical_label_jsonl(
                left.reveal.labels
            ),
            f"{root}/reveals/{left.identity.reviewer_id}/reveal.json": canonical_json_v1(
                left.reveal.model_dump(mode="json")
            )
            + b"\n",
        },
        {
            f"{root}/reveals/{right.identity.reviewer_id}/labels.jsonl": canonical_label_jsonl(
                right.reveal.labels
            ),
            f"{root}/reveals/{right.identity.reviewer_id}/reveal.json": canonical_json_v1(
                right.reveal.model_dump(mode="json")
            )
            + b"\n",
        },
        {
            f"{root}/adjudication-core.json": canonical_json_v1(
                fixture.adjudication.core.model_dump(mode="json")
            )
            + b"\n"
        },
    )


def _rebuild_graph_in_merge_order(
    fixture: _AuditFixture,
    order: tuple[int, int, int, int, int],
) -> tuple[
    tuple[PullRequestProofV1, ...],
    AuditGitObjectArchiveV1,
    dict[str, ParsedProtocolGitObjectV1],
]:
    store: dict[str, ParsedProtocolGitObjectV1] = {}
    empty_tree = _tree_for_files(store, {})
    current = _unsigned_commit(store, tree_oid=empty_tree.oid, parents=(), message="audit base")
    files: dict[str, bytes] = {}
    proofs = list(_proof_tuple(fixture))
    additions = _audit_additions(fixture)
    for index in order:
        files.update(additions[index])
        tree = _tree_for_files(store, files)
        original_head = fixture.heads[index]
        signing_key = next(
            (
                reviewer.signing_key
                for reviewer in fixture.registry.reviewers
                if reviewer.reviewer_numeric_account_id == original_head.signer_id
            ),
            None,
        )
        git_identity = (
            None
            if signing_key is None
            else (
                signing_key.author_name_ascii,
                signing_key.author_email_ascii,
                signing_key.committer_name_ascii,
                signing_key.committer_email_ascii,
            )
        )
        head = _signed_head(
            store,
            tree_oid=tree.oid,
            base_oid=current.oid,
            signer_id=original_head.signer_id,
            signer_login=original_head.signer_login,
            mode=original_head.mode,
            fingerprint=original_head.fingerprint,
            git_identity=git_identity,
            message=f"reordered audit pull request {index + 1}",
        )
        merge = _unsigned_commit(
            store,
            tree_oid=tree.oid,
            parents=(current.oid, head.commit.oid),
            message=f"merge reordered audit pull request {index + 1}",
        )
        proofs[index] = _rehash(
            proofs[index],
            "laconian-audit-pull-request-proof-v1",
            "pull_request_proof_sha256",
            base_sha=current.oid,
            head_sha=head.commit.oid,
            merge_commit_sha=merge.oid,
        )
        current = merge
    result = tuple(proofs)
    roots = tuple(oid for proof in result for oid in (proof.head_sha, proof.merge_commit_sha))
    reachable = _reachable_store(store, roots=roots)
    return result, _archive(reachable), reachable


def _proof_for_source(
    proof: PullRequestProofV1,
    source: AuditPullRequestEvidenceSourceV1,
) -> PullRequestProofV1:
    return _rehash(
        proof,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        pull_request_source_sha256=source.pull_request_source_sha256,
    )


def _verify_one_pull_request_source(
    fixture: _AuditFixture,
    source: AuditPullRequestEvidenceSourceV1,
    proof: PullRequestProofV1,
) -> None:
    audit_module._verify_pull_request_source(
        source=source,
        proof=proof,
        expected_kind=proof.proof_kind,
        expected_reviewer_id=proof.reviewer_id,
        expected_primary_path=proof.changed_paths[-1],
        repository_id=123,
        repository_owner="acme",
        repository_name="laconian",
        registry=fixture.registry,
        evidence=fixture.provider,
        objects=fixture.store,
    )


def _verify_one_signoff_source(
    fixture: _AuditFixture,
    source: ExactGitHubReviewSourceV1,
    signoff: ExactGitHubReviewSignoffV1,
    *,
    reviewer_ordinal: int = 0,
) -> None:
    reveal_times = tuple(
        audit_module.datetime.strptime(
            chain.reveal_pr.merged_at_utc, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=audit_module.UTC)
        for chain in fixture.chains
    )
    audit_module._verify_signoff_source(
        source=source,
        signoff=signoff,
        reviewer=fixture.registry.reviewers[reviewer_ordinal],
        core=fixture.adjudication.core,
        adjudication_pr=fixture.adjudication.adjudication_pr,
        registry=fixture.registry,
        repository_id=123,
        repository_owner="acme",
        repository_name="laconian",
        reveal_merge_times=reveal_times,
    )


def test_commitment_matches_domain_header_salt_and_exact_canonical_jsonl_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = (_label("f" * 64), _label("0" * 64))
    exact = canonical_label_jsonl(labels)
    assert exact.endswith(b"\n")
    assert "доказано".encode() in exact
    salt = bytes(range(32))
    expected = hashlib.sha256(
        b"laconian-audit-commitment-v1\0"
        + canonical_json_v1(_header().model_dump(mode="json"))
        + b"\0"
        + salt
        + b"\0"
        + exact
    ).hexdigest()
    assert compute_commitment(header=_header(), salt=salt, exact_label_bytes=exact) == expected
    assert compute_commitment(header=_header(), salt=salt, exact_label_bytes=exact[:-1]) != expected

    cyclic_value: dict[str, object] = {}
    cyclic_value["self"] = cyclic_value
    with pytest.raises(ValidationError, match="cyclic Python container"):
        CommitmentHeaderV1.model_validate(
            _header().model_dump(mode="python", round_trip=True)
            | {"campaign_id": cyclic_value}
        )

    deep_value: object = "leaf"
    for _ in range(1_100):
        deep_value = [deep_value]
    with pytest.raises(ValidationError, match="nesting limit"):
        CommitmentHeaderV1.model_validate(
            _header().model_dump(mode="python", round_trip=True)
            | {"campaign_id": deep_value}
        )

    shared_value: object = {"leaf": "value"}
    for _ in range(24):
        shared_value = [shared_value, shared_value]
    with pytest.raises(ValidationError):
        CommitmentHeaderV1.model_validate(
            _header().model_dump(mode="python", round_trip=True)
            | {"campaign_id": shared_value}
        )

    shared_with_model: object = {"leaf": "value"}
    for _ in range(24):
        shared_with_model = [shared_with_model, shared_with_model]
    for node_limit, match in ((32, "node limit"), (64, "foreign.*owner")):
        with monkeypatch.context() as context:
            context.setattr(
                protocol_module,
                "_EXACT_MODEL_PREFLIGHT_NODE_LIMIT",
                node_limit,
            )
            with pytest.raises(TypeError, match=match):
                CommitmentHeaderV1.model_validate(
                    _header().model_dump(mode="python", round_trip=True)
                    | {"campaign_id": [shared_with_model, _header()]}
                )

    mutated_rubric = RubricItemJudgmentV1(
        item_index=0,
        passed=True,
        evidence="reviewed",
    )
    object.__setattr__(mutated_rubric, "passed", "yes")
    object.__setattr__(mutated_rubric, "evidence", "")
    with pytest.raises(ValidationError):
        HumanAuditLabelV1(
            audit_record_id="0" * 64,
            rubric_items=(mutated_rubric,),
            material_warning=None,
            material_contradiction=False,
            contradiction_evidence=None,
            semantic_pass=True,
        )

    missing_evidence = RubricItemJudgmentV1.model_construct(
        item_index=0,
        passed=True,
    )
    with pytest.raises((TypeError, ValidationError), match="missing field"):
        HumanAuditLabelV1(
            audit_record_id="0" * 64,
            rubric_items=(missing_evidence,),
            material_warning=None,
            material_contradiction=False,
            contradiction_evidence=None,
            semantic_pass=True,
        )

    mutated_warning = WarningJudgmentV1(passed=True, evidence="reviewed")
    object.__setattr__(mutated_warning, "passed", "yes")
    object.__setattr__(mutated_warning, "evidence", "")
    with pytest.raises(ValidationError):
        HumanAuditLabelV1(
            audit_record_id="0" * 64,
            rubric_items=(
                RubricItemJudgmentV1(
                    item_index=0,
                    passed=True,
                    evidence="reviewed",
                ),
            ),
            material_warning=mutated_warning,
            material_contradiction=False,
            contradiction_evidence=None,
            semantic_pass=True,
        )


def test_commitment_artifact_does_not_disclose_salt_or_labels() -> None:
    artifact = ReviewerCommitmentV1(
        header=_header(),
        commitment_sha256=compute_commitment(
            header=_header(), salt=b"s" * 32, exact_label_bytes=canonical_label_jsonl((_label(),))
        ),
    )
    assert tuple(ReviewerCommitmentV1.model_fields) == ("header", "commitment_sha256")
    encoded = canonical_json_v1(artifact.model_dump(mode="json"))
    assert (
        b"salt" not in encoded and b"labels" not in encoded and "доказано".encode() not in encoded
    )


def test_reveal_rejects_actor_mismatch_modified_commitment_duplicate_or_missing_label(
    audit_fixture: _AuditFixture,
) -> None:
    chain = audit_fixture.chains[0]
    wrong_actor = _rehash(
        chain.commitment_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        actor_account_id=chain.identity.reviewer_numeric_account_id + 1000,
    )
    with pytest.raises(ValueError):
        _verify(
            audit_fixture,
            chains=(_chain_with(chain, commitment_pr=wrong_actor), audit_fixture.chains[1]),
        )

    changed_commitment = chain.commitment.model_copy(update={"commitment_sha256": "f" * 64})
    with pytest.raises(ValueError, match=r"authority|open"):
        _verify(
            audit_fixture,
            chains=(
                _chain_with(chain, commitment=changed_commitment),
                audit_fixture.chains[1],
            ),
        )

    missing_labels = chain.reveal.labels[1:]
    missing_bytes = canonical_label_jsonl(missing_labels)
    missing_reveal = _rehash(
        chain.reveal,
        "laconian-audit-reveal-v1",
        "reveal_sha256",
        labels=missing_labels,
        labels_byte_length=len(missing_bytes),
        labels_sha256=hashlib.sha256(missing_bytes).hexdigest(),
    )
    with pytest.raises(ValueError, match="cover"):
        _verify(
            audit_fixture,
            chains=(
                _chain_with(chain, reveal=missing_reveal),
                audit_fixture.chains[1],
            ),
        )
    with pytest.raises(ValidationError):
        ReviewerRevealV1.model_validate_json(
            canonical_json_v1(
                chain.reveal.model_dump(mode="json")
                | {
                    "labels": [
                        *chain.reveal.model_dump(mode="json")["labels"],
                        chain.reveal.model_dump(mode="json")["labels"][0],
                    ]
                }
            )
        )


def test_reviewer_identity_binds_positive_account_id_login_and_reviewer_registry_digest(
    audit_fixture: _AuditFixture,
) -> None:
    chain = audit_fixture.chains[0]
    for field, replacement in (
        ("reviewer_numeric_account_id", chain.identity.reviewer_numeric_account_id + 1),
        ("reviewer_login", "renamed-reviewer"),
        ("audit_reviewer_registry_sha256", "f" * 64),
    ):
        identity = chain.identity.model_copy(update={field: replacement})
        with pytest.raises(ValueError, match="identity"):
            _verify(
                audit_fixture,
                chains=(_chain_with(chain, identity=identity), audit_fixture.chains[1]),
            )


def test_all_github_identity_and_proof_ids_reject_strings_booleans_and_zero(
    audit_fixture: _AuditFixture,
) -> None:
    identity = audit_fixture.chains[0].identity
    for replacement in (
        str(identity.reviewer_numeric_account_id),
        float(identity.reviewer_numeric_account_id),
        True,
        0,
        -1,
    ):
        with pytest.raises(ValidationError):
            ReviewerIdentityV1.model_validate(
                identity.model_dump(mode="python", round_trip=True)
                | {"reviewer_numeric_account_id": replacement}
            )

    source = audit_fixture.pull_request_sources[0]
    review_source = audit_fixture.github_review_sources[0]
    signoff = audit_fixture.adjudication.signoffs[0]
    owners = (
        (
            source.pull_request_observation_receipt,
            "laconian-audit-github-api-observation-receipt-v1",
            "github_audit_api_observation_receipt_sha256",
            ("repository_id",),
        ),
        (
            source.pull_request_record,
            "laconian-audit-github-pull-request-record-v1",
            "exact_api_record_sha256",
            ("repository_id", "pr_number", "actor_account_id", "merge_actor_account_id"),
        ),
        (
            audit_fixture.chains[0].commitment_pr,
            "laconian-audit-pull-request-proof-v1",
            "pull_request_proof_sha256",
            ("repository_id", "pr_number", "actor_account_id", "merge_actor_account_id"),
        ),
        (
            review_source.record,
            "laconian-audit-github-review-record-v1",
            "exact_api_record_sha256",
            ("repository_id", "pr_number", "review_id", "actor_account_id"),
        ),
        (
            signoff,
            "laconian-audit-adjudication-github-review-v1",
            "signoff_proof_sha256",
            ("reviewer_numeric_account_id", "repository_id", "pr_number", "review_id"),
        ),
    )
    for model, _domain, _digest_field, fields in owners:
        for field in fields:
            original = getattr(model, field)
            for replacement in (str(original), float(original), True, 0, -1):
                with pytest.raises(ValidationError) as exc_info:
                    type(model).model_validate(
                        model.model_dump(mode="python", round_trip=True)
                        | {field: replacement}
                    )
                assert any(error["loc"] == (field,) for error in exc_info.value.errors())

    signature_owners = (
        (
            source.signature_observation_receipt,
            "laconian-github-signature-observation-receipt-v1",
            "github_signature_observation_receipt_sha256",
            ("repository_id",),
        ),
        (
            source.signature_evidence.github_rest_verification,
            "laconian-github-commit-verification-projection-v1",
            "rest_projection_sha256",
            ("repository_id",),
        ),
        (
            source.signature_evidence.github_graphql_signature,
            "laconian-github-signature-projection-v1",
            "graphql_projection_sha256",
            ("repository_id", "signer_database_id"),
        ),
    )
    for model, _domain, _digest_field, fields in signature_owners:
        for field in fields:
            original = getattr(model, field)
            for replacement in (str(original), float(original), True, 0, -1):
                with pytest.raises(ValidationError) as exc_info:
                    type(model).model_validate(
                        model.model_dump(mode="python", round_trip=True)
                        | {field: replacement}
                    )
                assert any(error["loc"] == (field,) for error in exc_info.value.errors())

    binding = audit_fixture.registry.reviewers[0]
    for replacement in (
        str(binding.reviewer_numeric_account_id),
        float(binding.reviewer_numeric_account_id),
        True,
        0,
        -1,
    ):
        with pytest.raises(ValidationError):
            ReviewerAccountBindingV1.model_validate(
                binding.model_dump(mode="python", round_trip=True)
                | {"reviewer_numeric_account_id": replacement}
            )


def test_account_id_mismatch_or_login_rename_requires_a_new_reviewer_registry(
    audit_fixture: _AuditFixture,
) -> None:
    chain = audit_fixture.chains[1]
    for identity in (
        chain.identity.model_copy(
            update={"reviewer_numeric_account_id": chain.identity.reviewer_numeric_account_id + 1}
        ),
        chain.identity.model_copy(update={"reviewer_login": "audit-reviewer-b-renamed"}),
    ):
        with pytest.raises(ValueError, match="identity"):
            _verify(
                audit_fixture,
                chains=(audit_fixture.chains[0], _chain_with(chain, identity=identity)),
            )


def test_reviewer_chain_runs_required_git_commit_verification_mode_and_matches_fingerprint(
    audit_fixture: _AuditFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []
    verifier = audit_module.verify_commit_signature_evidence_source

    def recording_verifier(**kwargs: Any) -> Any:
        calls.append((kwargs["expected_verification_mode"], kwargs["expected_signing_fingerprint"]))
        return verifier(**kwargs)

    monkeypatch.setattr(
        audit_module,
        "verify_commit_signature_evidence_source",
        recording_verifier,
    )
    verify_reviewer_chain(
        audit_fixture.chains[1],
        sample=audit_fixture.sample,
        provider_evidence=audit_fixture.provider,
        audit_git_object_archive=audit_fixture.archive,
        commitment_sources=audit_fixture.pull_request_sources[:2],
        reveal_source=audit_fixture.pull_request_sources[3],
    )
    assert calls == [
        ("github_verified_commit", None),
        ("ssh_sha256", audit_fixture.registry.reviewers[1].signing_fingerprint),
        ("ssh_sha256", audit_fixture.registry.reviewers[1].signing_fingerprint),
    ]

    keyed_reviewer = audit_fixture.registry.reviewers[1]
    signing_key = keyed_reviewer.signing_key
    assert signing_key is not None
    expected_identity = (
        signing_key.author_name_ascii,
        signing_key.author_email_ascii,
        signing_key.committer_name_ascii,
        signing_key.committer_email_ascii,
    )
    original_proof = audit_fixture.chains[1].commitment_pr
    original_commit = audit_fixture.store[original_proof.head_sha]
    original_tree_oid = audit_module._parse_commit_view(original_commit).tree_oid
    for ordinal, field in enumerate(range(4), start=201):
        mutated_identity = list(expected_identity)
        mutated_identity[field] = (
            "Resigned Audit Reviewer"
            if field in (0, 2)
            else "resigned-audit-reviewer@users.noreply.github.com"
        )
        objects: dict[str, ParsedProtocolGitObjectV1] = {}
        resigned_head = _signed_head(
            objects,
            tree_oid=original_tree_oid,
            base_oid=original_proof.base_sha,
            signer_id=keyed_reviewer.reviewer_numeric_account_id,
            signer_login=keyed_reviewer.reviewer_login,
            mode=keyed_reviewer.verification_mode,
            fingerprint=keyed_reviewer.signing_fingerprint,
            git_identity=tuple(mutated_identity),  # type: ignore[arg-type]
            message=f"resigned identity mutation {field}",
        )
        material = _signature_material(
            resigned_head,
            statement_path=original_proof.changed_paths[0],
            identity_bundle=audit_fixture.provider.identity_registry_bundle,
            signing_key=signing_key,
            ordinal=ordinal,
        )
        source = ProtocolSignatureEvidenceSourceV1(
            observation_receipt=material.receipt,
            signature_evidence=material.evidence,
            raw_response_bytes=material.raw,
            canonical_response_bytes=material.canonical,
        )
        with pytest.raises(ValueError, match="Git identity mismatch"):
            verify_commit_signature_evidence_source(
                source=source,
                commit=resigned_head.commit,
                expected_parent_oid=original_proof.base_sha,
                expected_primary_path=original_proof.changed_paths[0],
                expected_repository_id=123,
                expected_repository_owner="acme",
                expected_repository_name="laconian",
                expected_signer_numeric_account_id=(
                    keyed_reviewer.reviewer_numeric_account_id
                ),
                expected_signer_login=keyed_reviewer.reviewer_login,
                expected_verification_mode=keyed_reviewer.verification_mode,
                expected_signing_fingerprint=keyed_reviewer.signing_fingerprint,
                signing_key=signing_key,
                expected_git_identity=expected_identity,
                identity_registry_bundle=audit_fixture.provider.identity_registry_bundle,
                audit_reviewer_registry=audit_fixture.registry,
            )


def test_audit_chain_recomputes_registry_hash_from_provider_bindings_not_hash_only(
    audit_fixture: _AuditFixture,
) -> None:
    rogue = object.__new__(type(audit_fixture.provider))
    for field in dataclasses.fields(audit_fixture.provider):
        if field.name != "_construction_authority":
            object.__setattr__(rogue, field.name, getattr(audit_fixture.provider, field.name))
    object.__setattr__(
        rogue,
        "index",
        audit_fixture.provider.index.model_copy(
            update={"audit_reviewer_registry_sha256": "f" * 64}
        ),
    )
    with pytest.raises((TypeError, ValueError), match=r"loader-minted|changed"):
        verify_audit_chain(
            chains=audit_fixture.chains,
            adjudication=audit_fixture.adjudication,
            sample=audit_fixture.sample,
            provider_evidence=rogue,
            audit_git_object_archive=audit_fixture.archive,
            pull_request_sources=audit_fixture.pull_request_sources,
            github_review_sources=audit_fixture.github_review_sources,
        )


def test_reveal_requires_both_commitment_merges_in_its_ancestry(
    audit_fixture: _AuditFixture,
) -> None:
    chain = audit_fixture.chains[0]
    other_chain = audit_fixture.chains[1]
    additions = _audit_additions(audit_fixture)
    objects = _reachable_store(
        dict(audit_fixture.store),
        roots=(chain.commitment_pr.head_sha, chain.commitment_pr.merge_commit_sha),
    )
    files = dict(additions[0])
    files.update(additions[2])
    tree = _tree_for_files(objects, files)
    base = audit_fixture.merges[0]
    head = _signed_head(
        objects,
        tree_oid=tree.oid,
        base_oid=base.oid,
        signer_id=chain.identity.reviewer_numeric_account_id,
        signer_login=chain.identity.reviewer_login,
        mode=chain.identity.verification_mode,
        fingerprint=chain.identity.signing_fingerprint,
        git_identity=None,
        message="premature reveal",
    )
    merge = _unsigned_commit(
        objects,
        tree_oid=tree.oid,
        parents=(base.oid, head.commit.oid),
        message="merge premature reveal",
    )
    premature_proof = _rehash(
        chain.reveal_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        base_sha=base.oid,
        head_sha=head.commit.oid,
        merge_commit_sha=merge.oid,
    )
    premature_chain = _chain_with(chain, reveal_pr=premature_proof)
    with pytest.raises(ValueError, match="both commitment"):
        audit_module._validate_one_chain_deltas_and_ancestry(
            premature_chain,
            commitment_merge_oids=(
                audit_fixture.merges[0].oid,
                audit_fixture.merges[1].oid,
            ),
            objects=objects,
        )

    other_reviewer = audit_fixture.registry.reviewers[1]
    other_key = other_reviewer.signing_key
    assert other_key is not None
    committed_files = dict(additions[0])
    committed_files.update(additions[1])
    other_tree = _tree_for_files(objects, committed_files)
    other_head = _signed_head(
        objects,
        tree_oid=other_tree.oid,
        base_oid=base.oid,
        signer_id=other_reviewer.reviewer_numeric_account_id,
        signer_login=other_reviewer.reviewer_login,
        mode=other_reviewer.verification_mode,
        fingerprint=other_reviewer.signing_fingerprint,
        git_identity=(
            other_key.author_name_ascii,
            other_key.author_email_ascii,
            other_key.committer_name_ascii,
            other_key.committer_email_ascii,
        ),
        message="add reviewer B commitment to the same graph",
    )
    other_merge = _unsigned_commit(
        objects,
        tree_oid=other_tree.oid,
        parents=(base.oid, other_head.commit.oid),
        message="merge reviewer B commitment into the same graph",
    )
    accepted_files = dict(committed_files)
    accepted_files.update(additions[2])
    accepted_tree = _tree_for_files(objects, accepted_files)
    accepted_head = _signed_head(
        objects,
        tree_oid=accepted_tree.oid,
        base_oid=other_merge.oid,
        signer_id=chain.identity.reviewer_numeric_account_id,
        signer_login=chain.identity.reviewer_login,
        mode=chain.identity.verification_mode,
        fingerprint=chain.identity.signing_fingerprint,
        git_identity=None,
        message="reviewer A reveal after both commitments",
    )
    accepted_merge = _unsigned_commit(
        objects,
        tree_oid=accepted_tree.oid,
        parents=(other_merge.oid, accepted_head.commit.oid),
        message="merge reviewer A reveal after both commitments",
    )
    accepted_proof = _rehash(
        chain.reveal_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        base_sha=other_merge.oid,
        head_sha=accepted_head.commit.oid,
        merge_commit_sha=accepted_merge.oid,
    )
    audit_module._validate_one_chain_deltas_and_ancestry(
        _chain_with(chain, reveal_pr=accepted_proof),
        commitment_merge_oids=(
            audit_fixture.merges[0].oid,
            other_merge.oid,
        ),
        objects=objects,
    )

    other_path = other_chain.commitment_pr.changed_paths[0]
    foreign_header = CommitmentHeaderV1(
        schema_version="audit-commitment-v1",
        campaign_id=audit_fixture.provider.index.campaign_id,
        campaign_registry_sha256=(
            audit_fixture.provider.generation_context.index.campaign_registry_sha256
        ),
        reviewer_id=other_reviewer.reviewer_id,
        audit_reviewer_registry_sha256=(
            audit_fixture.registry.audit_reviewer_registry_sha256
        ),
        sample_manifest_sha256="f" * 64,
        audit_commit_reveal_protocol_sha256=(
            audit_fixture.provider.index.audit_commit_reveal_protocol_sha256
        ),
    )
    foreign_commitment = ReviewerCommitmentV1(
        header=foreign_header,
        commitment_sha256=compute_commitment(
            header=foreign_header,
            salt=bytes.fromhex(other_chain.reveal.salt_hex),
            exact_label_bytes=canonical_label_jsonl(other_chain.reveal.labels),
        ),
    )
    hostile_objects = _reachable_store(
        dict(audit_fixture.store),
        roots=(chain.commitment_pr.head_sha, chain.commitment_pr.merge_commit_sha),
    )
    hostile_files = dict(additions[0])
    hostile_files[other_path] = (
        canonical_json_v1(foreign_commitment.model_dump(mode="json")) + b"\n"
    )
    hostile_tree = _tree_for_files(hostile_objects, hostile_files)
    hostile_head = _signed_head(
        hostile_objects,
        tree_oid=hostile_tree.oid,
        base_oid=base.oid,
        signer_id=other_reviewer.reviewer_numeric_account_id,
        signer_login=other_reviewer.reviewer_login,
        mode=other_reviewer.verification_mode,
        fingerprint=other_reviewer.signing_fingerprint,
        git_identity=(
            other_key.author_name_ascii,
            other_key.author_email_ascii,
            other_key.committer_name_ascii,
            other_key.committer_email_ascii,
        ),
        message="foreign-authority reviewer B commitment",
    )
    hostile_merge = _unsigned_commit(
        hostile_objects,
        tree_oid=hostile_tree.oid,
        parents=(base.oid, hostile_head.commit.oid),
        message="merge foreign-authority reviewer B commitment",
    )
    hostile_source, _ = _pull_request_source_and_proof(
        kind="commitment",
        reviewer_id=other_reviewer.reviewer_id,
        campaign_id=audit_fixture.provider.index.campaign_id,
        head=hostile_head,
        merge=hostile_merge,
        pr_number=other_chain.commitment_pr.pr_number,
        merged_at=other_chain.commitment_pr.merged_at_utc,
        changed_paths=(other_path,),
        identity_bundle=audit_fixture.provider.identity_registry_bundle,
        signing_key=other_key,
        ordinal=91,
    )
    with pytest.raises(ValueError, match="commitment authority mismatch"):
        audit_module._verify_unselected_commitment_source(
            source=hostile_source,
            reviewer_id=other_reviewer.reviewer_id,
            repository_id=123,
            repository_owner="acme",
            repository_name="laconian",
            registry=audit_fixture.registry,
            evidence=audit_fixture.provider,
            sample=audit_fixture.sample,
            objects=hostile_objects,
        )


def test_adjudication_core_digest_binds_reveals_consensus_without_a_signoff_cycle(
    audit_fixture: _AuditFixture,
) -> None:
    core = audit_fixture.adjudication.core
    assert b"signoff" not in canonical_json_v1(core.model_dump(mode="json"))
    forged_core = _rehash(
        core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        reveal_sha256s=(core.reveal_sha256s[0], "f" * 64),
    )
    with pytest.raises(ValueError, match=r"authority|reveal"):
        _verify(
            audit_fixture,
            adjudication=_adjudication_with(audit_fixture.adjudication, core=forged_core),
        )

    def consensus_with_first(**updates: Any) -> tuple[ConsensusLabelV1, ...]:
        first = ConsensusLabelV1.model_validate(
            core.consensus[0].model_dump(mode="python", round_trip=True) | updates
        )
        return (first, *core.consensus[1:])

    stale_consensus = consensus_with_first(semantic_pass=False)
    stale_consensus_core = core.model_copy(update={"consensus": stale_consensus})
    with pytest.raises(ValidationError, match="adjudication core digest mismatch"):
        AuditAdjudicationCoreV1.model_validate(stale_consensus_core)

    wrong_common_boolean_core = _rehash(
        core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        consensus=stale_consensus,
    )
    with pytest.raises(ValueError, match="agreement consensus differs"):
        audit_module._verify_consensus(
            chains=audit_fixture.chains,
            core=wrong_common_boolean_core,
            sample=audit_fixture.sample,
        )

    missing_consensus_core = _rehash(
        core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        consensus=core.consensus[1:],
    )
    with pytest.raises(ValueError, match="cover the blind packet exactly once"):
        audit_module._verify_consensus(
            chains=audit_fixture.chains,
            core=missing_consensus_core,
            sample=audit_fixture.sample,
        )

    right_chain = audit_fixture.chains[1]
    original_label = right_chain.reveal.labels[0]
    false_rubric = (
        RubricItemJudgmentV1.model_validate(
            original_label.rubric_items[0].model_dump(mode="python")
            | {"passed": False}
        ),
        *original_label.rubric_items[1:],
    )
    false_label = HumanAuditLabelV1.model_validate(
        original_label.model_dump(mode="python", round_trip=True)
        | {"rubric_items": false_rubric, "semantic_pass": False}
    )
    disagreeing_labels = (false_label, *right_chain.reveal.labels[1:])
    disagreeing_label_bytes = canonical_label_jsonl(disagreeing_labels)
    disagreeing_reveal = _rehash(
        right_chain.reveal,
        "laconian-audit-reveal-v1",
        "reveal_sha256",
        labels_byte_length=len(disagreeing_label_bytes),
        labels_sha256=hashlib.sha256(disagreeing_label_bytes).hexdigest(),
        labels=disagreeing_labels,
    )
    disagreeing_chain = _chain_with(right_chain, reveal=disagreeing_reveal)
    disagreeing_chains = (audit_fixture.chains[0], disagreeing_chain)
    disagreement_reveal_sha256s = (
        audit_fixture.chains[0].reveal.reveal_sha256,
        disagreeing_reveal.reveal_sha256,
    )

    illegal_agreement_core = _rehash(
        core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        reveal_sha256s=disagreement_reveal_sha256s,
    )
    with pytest.raises(ValueError, match="disagreement lacks adjudication"):
        audit_module._verify_consensus(
            chains=disagreeing_chains,
            core=illegal_agreement_core,
            sample=audit_fixture.sample,
        )

    adjudicated_consensus = consensus_with_first(
        semantic_pass=False,
        resolution="adjudicated",
        rationale="The reviewed evidence supports a failing decision.",
    )
    adjudicated_core = _rehash(
        core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        reveal_sha256s=disagreement_reveal_sha256s,
        consensus=adjudicated_consensus,
    )
    audit_module._verify_consensus(
        chains=disagreeing_chains,
        core=adjudicated_core,
        sample=audit_fixture.sample,
    )

    unresolved_consensus = consensus_with_first(
        semantic_pass=None,
        resolution="unresolved",
        rationale="The evidence remains genuinely inconclusive.",
    )
    unresolved_core = _rehash(
        core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        reveal_sha256s=disagreement_reveal_sha256s,
        consensus=unresolved_consensus,
    )
    audit_module._verify_consensus(
        chains=disagreeing_chains,
        core=unresolved_core,
        sample=audit_fixture.sample,
    )
    assert unresolved_core.consensus[0].resolution == "unresolved"
    assert unresolved_core.consensus[0].semantic_pass is None


def test_each_signoff_replays_exact_github_review_provenance_for_the_core_head(
    audit_fixture: _AuditFixture,
) -> None:
    _verify(audit_fixture)
    source = audit_fixture.github_review_sources[0]
    raw = _raw_json(source.raw_response_base64)
    raw["commit_id"] = audit_fixture.chains[0].reveal_pr.head_sha
    hostile = _source_with_review_raw(source, canonical_json_v1(raw))
    with pytest.raises(ValueError, match=r"reconstruct|stale|wrong-head"):
        _verify(
            audit_fixture,
            github_review_sources=(hostile, audit_fixture.github_review_sources[1]),
        )

    signoff = audit_fixture.adjudication.signoffs[0]
    for field, replacement in (
        ("repository_id", signoff.repository_id + 1),
        ("pr_number", signoff.pr_number + 1),
        ("review_id", signoff.review_id + 1),
        ("fixed_body_sha256", "f" * 64),
        ("exact_api_record_sha256", "e" * 64),
    ):
        candidate = _rehash(
            signoff,
            "laconian-audit-adjudication-github-review-v1",
            "signoff_proof_sha256",
            **{field: replacement},
        )
        with pytest.raises(ValueError, match=r"source|signoff|stale|unauthorized"):
            _verify_one_signoff_source(
                audit_fixture,
                audit_fixture.github_review_sources[0],
                candidate,
            )

    source = audit_fixture.github_review_sources[0]
    coherent_cases = (
        ("repository_id", source.record.repository_id + 1),
        ("pr_number", source.record.pr_number + 1),
    )
    for field, replacement in coherent_cases:
        record = _rehash(
            source.record,
            "laconian-audit-github-review-record-v1",
            "exact_api_record_sha256",
            **{field: replacement},
        )
        receipt_updates: dict[str, Any] = {}
        if field == "repository_id":
            receipt_updates["repository_id"] = replacement
        else:
            receipt_updates["endpoint"] = source.observation_receipt.endpoint.replace(
                f"/pulls/{source.record.pr_number}/",
                f"/pulls/{replacement}/",
            )
        receipt = _rehash(
            source.observation_receipt,
            "laconian-audit-github-api-observation-receipt-v1",
            "github_audit_api_observation_receipt_sha256",
            **receipt_updates,
        )
        coherent_source = _rehash(
            source,
            "laconian-audit-github-review-source-v1",
            "github_review_source_sha256",
            record=record,
            observation_receipt=receipt,
        )
        coherent_signoff = _rehash(
            signoff,
            "laconian-audit-adjudication-github-review-v1",
            "signoff_proof_sha256",
            **{field: replacement},
            exact_api_record_sha256=record.exact_api_record_sha256,
            github_review_source_sha256=coherent_source.github_review_source_sha256,
        )
        with pytest.raises(ValueError, match=r"source|stale|unauthorized|mismatch"):
            _verify_one_signoff_source(
                audit_fixture,
                coherent_source,
                coherent_signoff,
            )

    duplicate_source, duplicate_signoff = _coherent_review_mutation(
        audit_fixture.github_review_sources[1],
        audit_fixture.adjudication.signoffs[1],
        review_id=audit_fixture.adjudication.signoffs[0].review_id,
    )
    duplicate_adjudication = _adjudication_with(
        audit_fixture.adjudication,
        signoffs=(audit_fixture.adjudication.signoffs[0], duplicate_signoff),
    )
    with pytest.raises(ValueError, match="two distinct GitHub review IDs"):
        _verify(
            audit_fixture,
            adjudication=duplicate_adjudication,
            github_review_sources=(
                audit_fixture.github_review_sources[0],
                duplicate_source,
            ),
        )


def test_exact_github_review_record_digest_is_recomputed_offline_from_stable_api_fields(
    audit_fixture: _AuditFixture,
) -> None:
    source = audit_fixture.github_review_sources[0]
    raw = _raw_json(source.raw_response_base64)
    raw["ignored_provider_field"] = {"changed": True}
    changed_source = _source_with_review_raw(source, canonical_json_v1(raw))
    signoff = _rehash(
        audit_fixture.adjudication.signoffs[0],
        "laconian-audit-adjudication-github-review-v1",
        "signoff_proof_sha256",
        github_review_source_sha256=changed_source.github_review_source_sha256,
    )
    adjudication = _adjudication_with(
        audit_fixture.adjudication,
        signoffs=(signoff, audit_fixture.adjudication.signoffs[1]),
    )
    _verify(
        audit_fixture,
        adjudication=adjudication,
        github_review_sources=(changed_source, audit_fixture.github_review_sources[1]),
    )


def test_pr_or_review_numeric_actor_id_mismatch_rejects_even_when_login_matches(
    audit_fixture: _AuditFixture,
) -> None:
    chain = audit_fixture.chains[0]
    proof = _rehash(
        chain.commitment_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        actor_account_id=chain.identity.reviewer_numeric_account_id + 1,
    )
    with pytest.raises(ValueError):
        _verify(
            audit_fixture,
            chains=(_chain_with(chain, commitment_pr=proof), audit_fixture.chains[1]),
        )
    source = audit_fixture.github_review_sources[0]
    raw = _raw_json(source.raw_response_base64)
    raw["user"]["id"] += 1
    hostile = _source_with_review_raw(source, canonical_json_v1(raw))
    with pytest.raises(ValueError):
        _verify(
            audit_fixture,
            github_review_sources=(hostile, audit_fixture.github_review_sources[1]),
        )

    keyed_reviewer = audit_fixture.registry.reviewers[1]
    keyed_head = audit_fixture.heads[1]
    for ordinal, changes in enumerate(
        (
            {"signer_id": keyed_reviewer.reviewer_numeric_account_id + 1},
            {"signer_login": keyed_reviewer.reviewer_login + "-renamed"},
        ),
        start=301,
    ):
        coherent_head = dataclasses.replace(keyed_head, **changes)
        coherent_source, coherent_proof = _pull_request_source_and_proof(
            kind="commitment",
            reviewer_id=keyed_reviewer.reviewer_id,
            campaign_id=audit_fixture.provider.index.campaign_id,
            head=coherent_head,
            merge=audit_fixture.merges[1],
            pr_number=audit_fixture.chains[1].commitment_pr.pr_number,
            merged_at=audit_fixture.chains[1].commitment_pr.merged_at_utc,
            changed_paths=audit_fixture.chains[1].commitment_pr.changed_paths,
            identity_bundle=audit_fixture.provider.identity_registry_bundle,
            signing_key=keyed_reviewer.signing_key,
            ordinal=ordinal,
        )
        with pytest.raises(ValueError, match="selected audit reviewer"):
            _verify_one_pull_request_source(
                audit_fixture,
                coherent_source,
                coherent_proof,
            )

    reviewer = audit_fixture.registry.reviewers[0]
    for ordinal, (actor_id, actor_login) in enumerate(
        (
            (reviewer.reviewer_numeric_account_id + 1, reviewer.reviewer_login),
            (reviewer.reviewer_numeric_account_id, reviewer.reviewer_login + "-renamed"),
        ),
        start=801,
    ):
        coherent_reviewer = SimpleNamespace(
            reviewer_id=reviewer.reviewer_id,
            reviewer_numeric_account_id=actor_id,
            reviewer_login=actor_login,
        )
        coherent_source, coherent_signoff = _review_source_and_signoff(
            reviewer=coherent_reviewer,
            core=audit_fixture.adjudication.core,
            adjudication_pr=audit_fixture.adjudication.adjudication_pr,
            registry_sha256=audit_fixture.registry.audit_reviewer_registry_sha256,
            review_id=ordinal,
            submitted_at="2026-08-31T00:00:45Z",
        )
        with pytest.raises(ValueError, match="unauthorized"):
            _verify_one_signoff_source(
                audit_fixture,
                coherent_source,
                coherent_signoff,
            )


def test_reviewer_chain_digest_binds_identity_numeric_actors_and_both_pr_proofs(
    audit_fixture: _AuditFixture,
) -> None:
    chain = audit_fixture.chains[0]
    for field in ("commitment_pr", "reveal_pr"):
        proof = getattr(chain, field)
        forged = proof.model_copy(update={"pull_request_proof_sha256": "f" * 64})
        with pytest.raises(ValidationError, match="digest"):
            ReviewerChainV1.model_validate_json(
                canonical_json_v1(
                    chain.model_dump(mode="json") | {field: forged.model_dump(mode="json")}
                )
            )


def test_final_adjudication_envelope_hash_binds_core_signoffs_and_pr_proof(
    audit_fixture: _AuditFixture,
) -> None:
    adjudication = audit_fixture.adjudication
    for field, value in (
        ("core", adjudication.core.model_copy(update={"adjudication_core_sha256": "f" * 64})),
        (
            "signoffs",
            (
                adjudication.signoffs[0].model_copy(update={"signoff_proof_sha256": "f" * 64}),
                adjudication.signoffs[1],
            ),
        ),
        (
            "adjudication_pr",
            adjudication.adjudication_pr.model_copy(update={"pull_request_proof_sha256": "f" * 64}),
        ),
    ):
        with pytest.raises(ValidationError):
            AuditAdjudicationV1.model_validate_json(
                canonical_json_v1(
                    adjudication.model_dump(mode="json") | {field: _json_value(value)}
                )
            )

    direct_outer_mutation = adjudication.model_copy(
        update={"adjudication_sha256": "f" * 64}
    )
    with pytest.raises(ValueError, match="envelope digest"):
        _verify(audit_fixture, adjudication=direct_outer_mutation)

    valid_child = _rehash(
        adjudication.adjudication_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        pr_number=adjudication.adjudication_pr.pr_number + 1,
    )
    stale_outer = AuditAdjudicationV1.model_construct(
        schema_version=adjudication.schema_version,
        core=adjudication.core,
        signoffs=adjudication.signoffs,
        adjudication_pr=valid_child,
        adjudication_sha256=adjudication.adjudication_sha256,
    )
    with pytest.raises(ValueError, match="envelope digest"):
        _verify(audit_fixture, adjudication=stale_outer)


def test_missing_or_stale_signoff_rejects_final_envelope_and_blocks_audit_seal(
    audit_fixture: _AuditFixture,
) -> None:
    with pytest.raises(ValidationError):
        AuditAdjudicationV1.model_validate_json(
            canonical_json_v1(audit_fixture.adjudication.model_dump(mode="json") | {"signoffs": []})
        )
    stale = _rehash(
        audit_fixture.adjudication.signoffs[0],
        "laconian-audit-adjudication-github-review-v1",
        "signoff_proof_sha256",
        reviewed_head_sha=audit_fixture.chains[0].reveal_pr.head_sha,
    )
    with pytest.raises(ValueError, match=r"signoff|stale|wrong-head"):
        _verify(
            audit_fixture,
            adjudication=_adjudication_with(
                audit_fixture.adjudication,
                signoffs=(stale, audit_fixture.adjudication.signoffs[1]),
            ),
        )


def test_repository_authority_is_unanimously_derived_from_verified_protocol_attestations(
    audit_fixture: _AuditFixture,
) -> None:
    assert audit_module._repository_authority(audit_fixture.provider) == (123, "acme", "laconian")

    def projected_authority(
        *,
        endpoint_mutation: tuple[int, str, str] | None = None,
        repository_id_mutation: tuple[int, str] | None = None,
    ) -> SimpleNamespace:
        attestations: list[SimpleNamespace] = []
        for ordinal, attestation in enumerate(
            audit_fixture.provider.index.protocol_attestations
        ):
            signature = attestation.signature_evidence
            endpoint = signature.github_rest_verification.endpoint
            if endpoint_mutation is not None and ordinal == endpoint_mutation[0]:
                endpoint = endpoint.replace(endpoint_mutation[1], endpoint_mutation[2])
            rest_id = signature.github_rest_verification.repository_id
            graphql_id = signature.github_graphql_signature.repository_id
            if repository_id_mutation == (ordinal, "rest"):
                rest_id += 1
            if repository_id_mutation == (ordinal, "graphql"):
                graphql_id += 1
            attestations.append(
                SimpleNamespace(
                    signature_evidence=SimpleNamespace(
                        github_rest_verification=SimpleNamespace(
                            endpoint=endpoint,
                            repository_id=rest_id,
                        ),
                        github_graphql_signature=SimpleNamespace(
                            repository_id=graphql_id
                        ),
                        commit_oid=signature.commit_oid,
                    )
                )
            )
        return SimpleNamespace(
            index=SimpleNamespace(protocol_attestations=tuple(attestations))
        )

    for endpoint_mutation in (
        (0, "/acme/", "/evil/"),
        (1, "/laconian/", "/other-repository/"),
    ):
        with pytest.raises(ValueError, match="unanimously"):
            audit_module._repository_authority(
                projected_authority(endpoint_mutation=endpoint_mutation)
            )
    for ordinal in range(3):
        for projection in ("rest", "graphql"):
            with pytest.raises(ValueError, match="unanimously"):
                audit_module._repository_authority(
                    projected_authority(
                        repository_id_mutation=(ordinal, projection)
                    )
                )


def test_pull_request_source_reconstructs_raw_pr_and_raw_signature_responses(
    audit_fixture: _AuditFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _verify(audit_fixture)
    assert len(audit_fixture.pull_request_sources) == 5

    original = audit_fixture.pull_request_sources[0]
    original_proof = audit_fixture.chains[0].commitment_pr
    raw_pair = tuple(
        base64.b64decode(item) for item in original.signature_raw_response_bytes_base64
    )
    canonical_pair = tuple(
        base64.b64decode(item)
        for item in original.signature_canonical_response_bytes_base64
    )

    predecode_mismatches: tuple[tuple[str, int], ...] = (
        (
            "pull_request_raw_response_base64",
            original.pull_request_observation_receipt.raw_response_byte_length,
        ),
        (
            "signature_raw_response_bytes_base64",
            original.signature_raw_response_byte_lengths[0],
        ),
        (
            "signature_canonical_response_bytes_base64",
            original.signature_canonical_response_byte_lengths[0],
        ),
    )

    def fail_if_decoded(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("mismatched source bytes reached Base64 decoding")

    for field, declared_length in predecode_mismatches:
        payload = original.model_dump(mode="json")
        replacement = base64.b64encode(b"x" * (declared_length + 1)).decode("ascii")
        if field == "pull_request_raw_response_base64":
            payload[field] = replacement
        else:
            pair = list(payload[field])
            pair[0] = replacement
            payload[field] = pair
        with monkeypatch.context() as context:
            context.setattr(audit_module.base64, "b64decode", fail_if_decoded)
            with pytest.raises(ValidationError, match="encoded byte length"):
                AuditPullRequestEvidenceSourceV1.model_validate_json(
                    canonical_json_v1(payload)
                )

    with monkeypatch.context() as context:
        context.setattr(audit_module.base64, "b64decode", fail_if_decoded)
        with pytest.raises(ValidationError, match="exact plain dictionary"):
            AuditPullRequestEvidenceSourceV1.model_validate(
                _DictSubclass(original.model_dump(mode="python", round_trip=True))
            )

    reversed_raw = _source_with_signature_raw(
        original,
        (raw_pair[1], raw_pair[0]),
    )
    with pytest.raises(ValueError):
        _verify_one_pull_request_source(
            audit_fixture,
            reversed_raw,
            _proof_for_source(original_proof, reversed_raw),
        )
    reversed_canonical = _source_with_signature_canonical(
        original,
        (canonical_pair[1], canonical_pair[0]),
    )
    with pytest.raises(ValueError):
        _verify_one_pull_request_source(
            audit_fixture,
            reversed_canonical,
            _proof_for_source(original_proof, reversed_canonical),
        )

    for field, lengths in (
        (
            "signature_raw_response_byte_lengths",
            original.signature_raw_response_byte_lengths,
        ),
        (
            "signature_canonical_response_byte_lengths",
            original.signature_canonical_response_byte_lengths,
        ),
    ):
        wrong_lengths = original.model_copy(
            update={field: (lengths[0] + 1, lengths[1])}
        )
        with pytest.raises(ValueError, match="byte"):
            _verify_one_pull_request_source(
                audit_fixture,
                wrong_lengths,
                original_proof,
            )

    changed_canonical = _source_with_signature_canonical(
        original,
        (canonical_pair[0] + b" ", canonical_pair[1]),
    )
    with pytest.raises(ValueError, match=r"canonical|source"):
        _verify_one_pull_request_source(
            audit_fixture,
            changed_canonical,
            _proof_for_source(original_proof, changed_canonical),
        )

    raw_pr = base64.b64decode(original.pull_request_raw_response_base64)
    duplicate_key_pr = raw_pr[:-1] + b',"number":101}'
    duplicate_source = _source_with_pr_raw(original, duplicate_key_pr)
    with pytest.raises(ValueError, match="duplicate"):
        _verify_one_pull_request_source(
            audit_fixture,
            duplicate_source,
            _proof_for_source(original_proof, duplicate_source),
        )


def test_pull_request_source_rejects_forged_success_even_after_rehashing_outer_models(
    audit_fixture: _AuditFixture,
) -> None:
    source = audit_fixture.pull_request_sources[0]
    raw_pair = tuple(base64.b64decode(item) for item in source.signature_raw_response_bytes_base64)
    rest = _raw_json(source.signature_raw_response_bytes_base64[0])
    rest["verification"]["verified"] = False
    hostile = _source_with_signature_raw(
        source,
        (canonical_json_v1(rest), raw_pair[1]),
    )
    proof = _rehash(
        audit_fixture.chains[0].commitment_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        pull_request_source_sha256=hostile.pull_request_source_sha256,
    )
    chains = (
        _chain_with(audit_fixture.chains[0], commitment_pr=proof),
        audit_fixture.chains[1],
    )
    sources = (hostile, *audit_fixture.pull_request_sources[1:])
    with pytest.raises(ValueError, match=r"boolean true|must be true|valid"):
        _verify(
            audit_fixture,
            chains=chains,
            pull_request_sources=sources,  # type: ignore[arg-type]
        )


def test_pull_request_source_rejects_repository_endpoint_actor_or_signer_substitution(
    audit_fixture: _AuditFixture,
) -> None:
    original = audit_fixture.pull_request_sources[0]
    stale_receipt = _rehash(
        original.pull_request_observation_receipt,
        "laconian-audit-github-api-observation-receipt-v1",
        "github_audit_api_observation_receipt_sha256",
        observed_at_utc="2026-08-31T00:00:09Z",
    )
    with pytest.raises(ValidationError, match="observation predates"):
        _rehash(
            original,
            "laconian-audit-pull-request-source-v1",
            "pull_request_source_sha256",
            pull_request_observation_receipt=stale_receipt,
        )

    hostile_sources: list[AuditPullRequestEvidenceSourceV1] = [
        _source_with_pr_raw(
            original,
            base64.b64decode(original.pull_request_raw_response_base64),
            endpoint="GET /repos/evil/repo/pulls/101",
        )
    ]
    raw_pr = _raw_json(original.pull_request_raw_response_base64)
    raw_pr["user"]["id"] += 1
    hostile_sources.append(_source_with_pr_raw(original, canonical_json_v1(raw_pr)))
    for path, replacement in (
        (("base", "repo", "id"), 124),
        (("base", "repo", "name"), "other-repository"),
        (("user", "login"), "impostor"),
    ):
        raw_pr = _raw_json(original.pull_request_raw_response_base64)
        target: dict[str, Any] = raw_pr
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = replacement
        hostile_sources.append(_source_with_pr_raw(original, canonical_json_v1(raw_pr)))
    raw_pair = tuple(
        base64.b64decode(item) for item in original.signature_raw_response_bytes_base64
    )
    graphql = _raw_json(original.signature_raw_response_bytes_base64[1])
    graphql["data"]["repository"]["object"]["signature"]["signer"]["login"] = "impostor"
    hostile_sources.append(
        _source_with_signature_raw(original, (raw_pair[0], canonical_json_v1(graphql)))
    )
    for field, replacement in (
        ("databaseId", 124),
        ("signer.databaseId", original.pull_request_record.actor_account_id + 1),
    ):
        graphql = _raw_json(original.signature_raw_response_bytes_base64[1])
        if field == "databaseId":
            graphql["data"]["repository"][field] = replacement
        else:
            graphql["data"]["repository"]["object"]["signature"]["signer"][
                "databaseId"
            ] = replacement
        hostile_sources.append(
            _source_with_signature_raw(
                original,
                (raw_pair[0], canonical_json_v1(graphql)),
            )
        )

    evidence = original.signature_evidence
    hostile_rest_projection = _protocol_rehash(
        evidence.github_rest_verification,
        "laconian-github-commit-verification-projection-v1",
        "rest_projection_sha256",
        repository_id=124,
    )
    hostile_graphql_projection = _protocol_rehash(
        evidence.github_graphql_signature,
        "laconian-github-signature-projection-v1",
        "graphql_projection_sha256",
        repository_id=124,
    )
    for projection_name, projection in (
        ("github_rest_verification", hostile_rest_projection),
        ("github_graphql_signature", hostile_graphql_projection),
    ):
        with pytest.raises(ValidationError, match="projection repository identity mismatch"):
            type(evidence).model_validate_json(
                canonical_json_v1(
                    evidence.model_dump(mode="json")
                    | {projection_name: projection.model_dump(mode="json")}
                )
            )

    for hostile in hostile_sources:
        with pytest.raises(ValueError):
            _verify_one_pull_request_source(
                audit_fixture,
                hostile,
                _proof_for_source(audit_fixture.chains[0].commitment_pr, hostile),
            )

    substituted_source, substituted_proof = _coherent_repository_id_substitution(
        original,
        audit_fixture.chains[0].commitment_pr,
        repository_id=124,
    )
    with pytest.raises(ValueError, match="observation receipt byte binding mismatch"):
        _verify_one_pull_request_source(
            audit_fixture,
            substituted_source,
            substituted_proof,
        )


def _assert_archive_allows_git_objects_above_api_response_limit() -> None:
    raw = b"x" * (2_097_152 + 2)
    store: dict[str, ParsedProtocolGitObjectV1] = {}
    blob = _git_object(store, "blob", raw)
    archive = _archive(store)
    checked = AuditGitObjectArchiveV1.model_validate(
        archive.model_dump(mode="python", round_trip=True)
    )
    assert audit_module._archive_objects(checked)[blob.oid].raw_content == raw
    with pytest.raises(ValueError, match=r"audit source.*decoded-byte limit"):
        audit_module._decode_base64(base64.b64encode(raw).decode("ascii"))


def test_audit_git_archive_rejects_missing_extra_unsorted_oversized_or_tag_objects(
    audit_fixture: _AuditFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_archive_allows_git_objects_above_api_response_limit()

    missing_store = dict(audit_fixture.store)
    missing_store.pop(audit_fixture.heads[0].commit.oid)
    with pytest.raises(ValueError, match="missing"):
        _verify(audit_fixture, archive=_archive(missing_store))

    extra_store = dict(audit_fixture.store)
    _git_object(extra_store, "blob", b"unreachable extra\n")
    with pytest.raises(ValueError, match="extra"):
        _verify(audit_fixture, archive=_archive(extra_store))

    payload = audit_fixture.archive.model_dump(mode="json")
    payload["objects"] = list(reversed(payload["objects"]))
    with pytest.raises(ValidationError, match="ascending"):
        AuditGitObjectArchiveV1.model_validate_json(canonical_json_v1(payload))

    def fail_if_decoded(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("invalid audit archive reached Base64 decoding")

    aggregate_payload = audit_fixture.archive.model_dump(mode="json")
    aggregate_payload["objects"][0]["size"] = 67_108_864
    aggregate_payload["objects"][1]["size"] = 1
    with monkeypatch.context() as context:
        context.setattr(protocol_module, "_decode_canonical_base64", fail_if_decoded)
        context.setattr(audit_module, "_decode_base64", fail_if_decoded)
        with pytest.raises(ValidationError, match="decoded-byte limit"):
            AuditGitObjectArchiveV1.model_validate_json(
                canonical_json_v1(aggregate_payload)
            )

    encoded_length_payload = audit_fixture.archive.model_dump(mode="json")
    encoded_length_payload["objects"][0]["size"] += 1
    with monkeypatch.context() as context:
        context.setattr(protocol_module, "_decode_canonical_base64", fail_if_decoded)
        context.setattr(audit_module, "_decode_base64", fail_if_decoded)
        with pytest.raises(ValidationError, match="encoded byte length"):
            AuditGitObjectArchiveV1.model_validate_json(
                canonical_json_v1(encoded_length_payload)
            )

    with monkeypatch.context() as context:
        context.setattr(protocol_module, "_decode_canonical_base64", fail_if_decoded)
        context.setattr(audit_module, "_decode_base64", fail_if_decoded)
        with pytest.raises(ValidationError, match="exact plain dictionary"):
            AuditGitObjectArchiveV1.model_validate(
                _DictSubclass(
                    audit_fixture.archive.model_dump(mode="python", round_trip=True)
                )
            )

    tag_store = dict(audit_fixture.store)
    tag_target = audit_fixture.merges[0].oid.encode("ascii")
    _git_object(
        tag_store,
        "tag",
        b"object "
        + tag_target
        + b"\ntype commit\ntag forbidden-audit-tag\n"
        + b"tagger Audit Tagger <audit-tagger@example.com> 1788134400 +0000\n\n"
        + b"not an allowed audit object\n",
    )
    with pytest.raises(ValidationError, match="only commit, tree, and blob"):
        _archive(tag_store)

    class HugeLength(bytes):
        def __len__(self) -> int:
            return 67_108_865

    with monkeypatch.context() as context:
        context.setattr(audit_module, "_decode_base64", lambda _, **kwargs: HugeLength(b"x"))
        with pytest.raises(ValidationError, match="decoded-byte limit"):
            AuditGitObjectArchiveV1.model_validate_json(
                canonical_json_v1(audit_fixture.archive.model_dump(mode="json"))
            )

    empty_delta_store: dict[str, ParsedProtocolGitObjectV1] = {}
    empty_base = _tree_for_files(empty_delta_store, {})
    hidden_empty = _tree_from_entries(
        empty_delta_store,
        (("40000", b"unapproved-empty", empty_base.oid),),
    )
    closed_archive = _archive(empty_delta_store)
    closed_objects = audit_module._archive_objects(closed_archive)
    for before, after in (
        (empty_base.oid, hidden_empty.oid),
        (hidden_empty.oid, empty_base.oid),
    ):
        with pytest.raises(ValueError, match="one-sided tree must not be empty"):
            audit_module._simultaneous_tree_diff(
                before,
                after,
                prefix=b"",
                objects=closed_objects,
                selected=set(),
                changed={},
                expected_paths=("unapproved-empty/leaf",),
            )

    deep_store: dict[str, ParsedProtocolGitObjectV1] = {}
    deep_leaf = _git_object(deep_store, "blob", b"deep one-sided leaf\n")
    deep_tree = _tree_from_entries(
        deep_store,
        (("100644", b"leaf", deep_leaf.oid),),
    )
    deep_components: list[str] = []
    for ordinal in range(1_100):
        component = f"d{ordinal:04d}"
        deep_components.append(component)
        deep_tree = _tree_from_entries(
            deep_store,
            (("40000", component.encode("ascii"), deep_tree.oid),),
        )
    deep_archive = _archive(deep_store)
    deep_objects = audit_module._archive_objects(deep_archive)
    deep_path = "/".join((*reversed(deep_components), "leaf"))
    deep_entry = ("100644", deep_leaf.oid)
    for before, after, expected in (
        (None, deep_tree.oid, (None, deep_entry)),
        (deep_tree.oid, None, (deep_entry, None)),
    ):
        selected: set[str] = set()
        changed: dict[
            str,
            tuple[tuple[str, str] | None, tuple[str, str] | None],
        ] = {}
        audit_module._simultaneous_tree_diff(
            before,
            after,
            prefix=b"",
            objects=deep_objects,
            selected=selected,
            changed=changed,
            expected_paths=(deep_path,),
        )
        assert changed == {deep_path: expected}
        assert selected == set(deep_store)

    paired_store: dict[str, ParsedProtocolGitObjectV1] = {}
    paired_base_leaf = _git_object(paired_store, "blob", b"deep base leaf\n")
    paired_head_leaf = _git_object(paired_store, "blob", b"deep head leaf\n")
    paired_base_tree = _tree_from_entries(
        paired_store,
        (("100644", b"leaf", paired_base_leaf.oid),),
    )
    paired_head_tree = _tree_from_entries(
        paired_store,
        (("100644", b"leaf", paired_head_leaf.oid),),
    )
    paired_components: list[str] = []
    for ordinal in range(1_100):
        component = f"p{ordinal:04d}"
        paired_components.append(component)
        entry_name = component.encode("ascii")
        paired_base_tree = _tree_from_entries(
            paired_store,
            (("40000", entry_name, paired_base_tree.oid),),
        )
        paired_head_tree = _tree_from_entries(
            paired_store,
            (("40000", entry_name, paired_head_tree.oid),),
        )
    paired_archive = _archive(paired_store)
    paired_objects = audit_module._archive_objects(paired_archive)
    paired_path = "/".join((*reversed(paired_components), "leaf"))
    paired_selected: set[str] = set()
    paired_changed: dict[
        str,
        tuple[tuple[str, str] | None, tuple[str, str] | None],
    ] = {}
    audit_module._simultaneous_tree_diff(
        paired_base_tree.oid,
        paired_head_tree.oid,
        prefix=b"",
        objects=paired_objects,
        selected=paired_selected,
        changed=paired_changed,
        expected_paths=(paired_path,),
    )
    assert paired_changed == {
        paired_path: (
            ("100644", paired_base_leaf.oid),
            ("100644", paired_head_leaf.oid),
        )
    }
    assert paired_selected == set(paired_store)

    shared_store: dict[str, ParsedProtocolGitObjectV1] = {}
    shared_leaf = _git_object(shared_store, "blob", b"shared DAG leaf\n")
    shared_tree = _tree_from_entries(
        shared_store,
        (("100644", b"leaf", shared_leaf.oid),),
    )
    shared_depth = 24
    for _ in range(shared_depth):
        shared_tree = _tree_from_entries(
            shared_store,
            (
                ("40000", b"a", shared_tree.oid),
                ("40000", b"b", shared_tree.oid),
            ),
        )
    shared_objects = audit_module._archive_objects(_archive(shared_store))
    allowed_shared_path = "/".join((*(("a",) * shared_depth), "leaf"))
    tree_entry_calls = 0
    original_tree_entries = audit_module._tree_entries

    def counted_tree_entries(*args: Any, **kwargs: Any) -> Any:
        nonlocal tree_entry_calls
        tree_entry_calls += 1
        return original_tree_entries(*args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(audit_module, "_tree_entries", counted_tree_entries)
        with pytest.raises(ValueError, match="allowlist"):
            audit_module._simultaneous_tree_diff(
                None,
                shared_tree.oid,
                prefix=b"",
                objects=shared_objects,
                selected=set(),
                changed={},
                expected_paths=(allowed_shared_path,),
            )
    assert tree_entry_calls <= shared_depth + 2


def test_audit_git_topology_requires_single_parent_heads_two_parent_merges_and_group_order(
    audit_fixture: _AuditFixture,
) -> None:
    proofs = _proof_tuple(audit_fixture)

    def verify_graph(
        candidate_proofs: tuple[PullRequestProofV1, ...],
        archive: AuditGitObjectArchiveV1,
        objects: dict[str, ParsedProtocolGitObjectV1],
    ) -> None:
        audit_module._verify_topology_and_closure(
            chains=audit_fixture.chains,
            adjudication=audit_fixture.adjudication,
            proofs=candidate_proofs,
            archive=archive,
            objects=objects,
        )

    audit_module._verify_topology_and_closure(
        chains=audit_fixture.chains,
        adjudication=audit_fixture.adjudication,
        proofs=proofs,
        archive=audit_fixture.archive,
        objects=audit_fixture.store,
    )
    wrong_base = proofs[0].model_copy(update={"base_sha": audit_fixture.merges[1].oid})
    with pytest.raises(ValueError, match="head"):
        audit_module._verify_topology_and_closure(
            chains=audit_fixture.chains,
            adjudication=audit_fixture.adjudication,
            proofs=(wrong_base, *proofs[1:]),
            archive=audit_fixture.archive,
            objects=audit_fixture.store,
        )

    for parents in ((), (proofs[-1].base_sha, proofs[0].merge_commit_sha)):
        candidate, archive, objects = _replace_last_pr_graph(
            audit_fixture,
            head_parents=parents,
        )
        with pytest.raises(ValueError, match="signed and have exactly its base parent"):
            verify_graph(candidate, archive, objects)

    for parent_template in (
        ("{base}",),
        ("{base}", "{head}", proofs[0].merge_commit_sha),
        ("{head}", "{base}"),
    ):
        candidate, archive, objects = _replace_last_pr_graph(
            audit_fixture,
            merge_parents=parent_template,
        )
        with pytest.raises(ValueError, match="exact base/head parent order"):
            verify_graph(candidate, archive, objects)

    candidate, archive, objects = _replace_last_pr_graph(
        audit_fixture,
        merge_tree_oid=audit_module._parse_commit_view(
            audit_fixture.store[proofs[-1].base_sha]
        ).tree_oid,
    )
    with pytest.raises(ValueError, match="merge tree differs"):
        verify_graph(candidate, archive, objects)

    reordered, reordered_archive, reordered_objects = _rebuild_graph_in_merge_order(
        audit_fixture,
        (0, 2, 1, 3, 4),
    )
    with pytest.raises(ValueError, match="group order"):
        verify_graph(reordered, reordered_archive, reordered_objects)

    duplicate_pr = list(proofs)
    duplicate_pr[-1] = _rehash(
        duplicate_pr[-1],
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        pr_number=duplicate_pr[0].pr_number,
    )
    with pytest.raises(ValueError, match="numbers must be unique"):
        verify_graph(tuple(duplicate_pr), audit_fixture.archive, audit_fixture.store)

    for oid_field in ("head_sha", "merge_commit_sha"):
        duplicate_oid = list(proofs)
        duplicate_oid[-1] = _rehash(
            duplicate_oid[-1],
            "laconian-audit-pull-request-proof-v1",
            "pull_request_proof_sha256",
            **{oid_field: getattr(duplicate_oid[0], oid_field)},
        )
        with pytest.raises(ValueError, match="pairwise distinct"):
            verify_graph(tuple(duplicate_oid), audit_fixture.archive, audit_fixture.store)

    for merged_at in (
        proofs[-2].merged_at_utc,
        proofs[-3].merged_at_utc,
    ):
        nonincreasing = list(proofs)
        nonincreasing[-1] = _rehash(
            nonincreasing[-1],
            "laconian-audit-pull-request-proof-v1",
            "pull_request_proof_sha256",
            merged_at_utc=merged_at,
        )
        with pytest.raises(ValueError, match="timestamps must strictly increase"):
            verify_graph(tuple(nonincreasing), audit_fixture.archive, audit_fixture.store)
    with pytest.raises(ValueError, match="tuple order"):
        audit_module._verify_topology_and_closure(
            chains=audit_fixture.chains,
            adjudication=audit_fixture.adjudication,
            proofs=(proofs[1], proofs[0], *proofs[2:]),
            archive=audit_fixture.archive,
            objects=audit_fixture.store,
        )


def test_commitment_reveal_and_adjudication_deltas_use_the_exact_path_allowlists(
    audit_fixture: _AuditFixture,
) -> None:
    chain = audit_fixture.chains[0]
    commitment_proof = _rehash(
        chain.commitment_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        changed_paths=(
            f"benchmarks/audits/{audit_fixture.provider.index.campaign_id}/"
            "commitments/wrong-reviewer.json",
        ),
    )
    with pytest.raises(ValueError, match="allowlist"):
        _verify(
            audit_fixture,
            chains=(
                _chain_with(chain, commitment_pr=commitment_proof),
                audit_fixture.chains[1],
            ),
        )

    changed = tuple(sorted((*chain.reveal_pr.changed_paths, "extra.json"), key=str.encode))
    proof = _rehash(
        chain.reveal_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        changed_paths=changed,
    )
    with pytest.raises(ValueError, match="allowlist"):
        _verify(
            audit_fixture,
            chains=(_chain_with(chain, reveal_pr=proof), audit_fixture.chains[1]),
        )

    adjudication_proof = _rehash(
        audit_fixture.adjudication.adjudication_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        changed_paths=("extra.json",),
    )
    with pytest.raises(ValueError, match="allowlist"):
        _verify(
            audit_fixture,
            adjudication=_adjudication_with(
                audit_fixture.adjudication,
                adjudication_pr=adjudication_proof,
            ),
        )

    baseline_proofs = _proof_tuple(audit_fixture)
    baseline_tree_oid = audit_module._parse_commit_view(
        audit_fixture.store[baseline_proofs[-1].head_sha]
    ).tree_oid
    campaign_root = f"benchmarks/audits/{audit_fixture.provider.index.campaign_id}"

    def verify_mutated_tree(
        objects: dict[str, ParsedProtocolGitObjectV1],
        tree_oid: str,
        *,
        match: str = "allowlist|added regular blob",
    ) -> None:
        candidate, archive, reachable = _replace_last_pr_graph(
            audit_fixture,
            store=objects,
            head_tree_oid=tree_oid,
        )
        with pytest.raises(ValueError, match=match):
            audit_module._verify_topology_and_closure(
                chains=audit_fixture.chains,
                adjudication=audit_fixture.adjudication,
                proofs=candidate,
                archive=archive,
                objects=reachable,
            )

    objects = dict(audit_fixture.store)
    extra_blob = _git_object(objects, "blob", b"unapproved addition\n")
    verify_mutated_tree(
        objects,
        _rewrite_tree_path(
            objects,
            baseline_tree_oid,
            f"{campaign_root}/unapproved.txt",
            ("100644", extra_blob.oid),
        ),
    )

    governed_paths = (
        audit_fixture.chains[0].commitment_pr.changed_paths[0],
        audit_fixture.chains[1].commitment_pr.changed_paths[0],
        audit_fixture.chains[0].reveal_pr.changed_paths[1],
    )
    objects = dict(audit_fixture.store)
    verify_mutated_tree(
        objects,
        _rewrite_tree_path(objects, baseline_tree_oid, governed_paths[0], None),
    )

    objects = dict(audit_fixture.store)
    selected: set[str] = set()
    renamed_entry = audit_module._resolve_path(
        baseline_tree_oid,
        governed_paths[1],
        objects=objects,
        selected=selected,
    )
    assert renamed_entry is not None
    renamed_tree = _rewrite_tree_path(objects, baseline_tree_oid, governed_paths[1], None)
    renamed_tree = _rewrite_tree_path(
        objects,
        renamed_tree,
        governed_paths[1] + ".renamed",
        renamed_entry,
    )
    verify_mutated_tree(objects, renamed_tree)

    objects = dict(audit_fixture.store)
    modified_blob = _git_object(objects, "blob", b"modified governed bytes\n")
    verify_mutated_tree(
        objects,
        _rewrite_tree_path(
            objects,
            baseline_tree_oid,
            governed_paths[2],
            ("100644", modified_blob.oid),
        ),
    )

    objects = dict(audit_fixture.store)
    nested_blob = _git_object(objects, "blob", b"prefix alias child\n")
    nested_tree = _tree_from_entries(objects, (("100644", b"child", nested_blob.oid),))
    verify_mutated_tree(
        objects,
        _rewrite_tree_path(
            objects,
            baseline_tree_oid,
            baseline_proofs[-1].changed_paths[0],
            ("40000", nested_tree.oid),
        ),
    )

    objects = dict(audit_fixture.store)
    alias_blob = _git_object(objects, "blob", b"campaign prefix alias\n")
    verify_mutated_tree(
        objects,
        _rewrite_tree_path(
            objects,
            baseline_tree_oid,
            f"{campaign_root.upper()}/alias.txt",
            ("100644", alias_blob.oid),
        ),
    )

    objects = dict(audit_fixture.store)
    empty_tree = _tree_for_files(objects, {})
    empty_alias_tree = _rewrite_tree_path(
        objects,
        baseline_tree_oid,
        f"{campaign_root}/unapproved-empty",
        ("40000", empty_tree.oid),
    )
    verify_mutated_tree(objects, empty_alias_tree, match="allowlist")

    for forbidden_mode in ("100755", "120000", "160000"):
        invalid_store: dict[str, ParsedProtocolGitObjectV1] = {}
        target = _git_object(invalid_store, "blob", b"forbidden mode target\n")
        raw_tree = (
            forbidden_mode.encode("ascii")
            + b" forbidden\0"
            + bytes.fromhex(target.oid)
        )
        _unchecked_git_object(invalid_store, "tree", raw_tree)
        with pytest.raises(ValidationError, match="only directories and regular"):
            _archive(invalid_store)

    ambiguous_store: dict[str, ParsedProtocolGitObjectV1] = {}
    alias_blob = _git_object(ambiguous_store, "blob", b"alias\n")
    alias_tree = _tree_for_files(ambiguous_store, {})
    ambiguous_raw = (
        b"100644 alias\0"
        + bytes.fromhex(alias_blob.oid)
        + b"40000 alias\0"
        + bytes.fromhex(alias_tree.oid)
    )
    _unchecked_git_object(ambiguous_store, "tree", ambiguous_raw)
    with pytest.raises(ValidationError, match="canonical unique Git order"):
        _archive(ambiguous_store)


def test_governed_blobs_remain_immutable_across_intervening_first_parent_commits(
    audit_fixture: _AuditFixture,
) -> None:
    objects = dict(audit_fixture.store)
    root = f"benchmarks/audits/{audit_fixture.provider.index.campaign_id}"
    chains = audit_fixture.chains
    files = {
        f"{root}/commitments/{chains[0].identity.reviewer_id}.json": canonical_json_v1(
            chains[0].commitment.model_dump(mode="json")
        )
        + b"\n",
        f"{root}/commitments/{chains[1].identity.reviewer_id}.json": canonical_json_v1(
            chains[1].commitment.model_dump(mode="json")
        )
        + b"\n",
    }
    first_commitment_path = next(iter(files))
    files[first_commitment_path] = b'{"hostile":"mutation"}\n'
    hostile_tree = _tree_for_files(objects, files)
    intervening = _unsigned_commit(
        objects,
        tree_oid=hostile_tree.oid,
        parents=(audit_fixture.merges[1].oid,),
        message="hostile intervening audit mutation",
    )
    new_heads: list[_SignedHead] = []
    new_merges: list[ParsedProtocolGitObjectV1] = []
    current = intervening
    later_additions = (
        {
            f"{root}/reveals/{chains[0].identity.reviewer_id}/labels.jsonl": canonical_label_jsonl(
                chains[0].reveal.labels
            ),
            f"{root}/reveals/{chains[0].identity.reviewer_id}/reveal.json": canonical_json_v1(
                chains[0].reveal.model_dump(mode="json")
            )
            + b"\n",
        },
        {
            f"{root}/reveals/{chains[1].identity.reviewer_id}/labels.jsonl": canonical_label_jsonl(
                chains[1].reveal.labels
            ),
            f"{root}/reveals/{chains[1].identity.reviewer_id}/reveal.json": canonical_json_v1(
                chains[1].reveal.model_dump(mode="json")
            )
            + b"\n",
        },
        {
            f"{root}/adjudication-core.json": canonical_json_v1(
                audit_fixture.adjudication.core.model_dump(mode="json")
            )
            + b"\n"
        },
    )
    signer_specs = (
        (
            chains[0].identity.reviewer_numeric_account_id,
            chains[0].identity.reviewer_login,
        ),
        (
            chains[1].identity.reviewer_numeric_account_id,
            chains[1].identity.reviewer_login,
        ),
        (999, "audit-adjudicator"),
    )
    for ordinal, (added, signer) in enumerate(
        zip(later_additions, signer_specs, strict=True), start=3
    ):
        files.update(added)
        tree = _tree_for_files(objects, files)
        head = _signed_head(
            objects,
            tree_oid=tree.oid,
            base_oid=current.oid,
            signer_id=signer[0],
            signer_login=signer[1],
            mode="github_verified_commit",
            fingerprint=None,
            git_identity=None,
            message=f"replacement audit pull request {ordinal}",
        )
        merge = _unsigned_commit(
            objects,
            tree_oid=tree.oid,
            parents=(current.oid, head.commit.oid),
            message=f"merge replacement audit pull request {ordinal}",
        )
        new_heads.append(head)
        new_merges.append(merge)
        current = merge
    proofs = (
        chains[0].commitment_pr,
        chains[1].commitment_pr,
        chains[0].reveal_pr.model_copy(
            update={
                "base_sha": intervening.oid,
                "head_sha": new_heads[0].commit.oid,
                "merge_commit_sha": new_merges[0].oid,
            }
        ),
        chains[1].reveal_pr.model_copy(
            update={
                "base_sha": new_merges[0].oid,
                "head_sha": new_heads[1].commit.oid,
                "merge_commit_sha": new_merges[1].oid,
            }
        ),
        audit_fixture.adjudication.adjudication_pr.model_copy(
            update={
                "base_sha": new_merges[1].oid,
                "head_sha": new_heads[2].commit.oid,
                "merge_commit_sha": new_merges[2].oid,
            }
        ),
    )
    with pytest.raises(ValueError, match="intervening main commit changed"):
        audit_module._verify_topology_and_closure(
            chains=chains,
            adjudication=audit_fixture.adjudication,
            proofs=proofs,
            archive=audit_fixture.archive,
            objects=objects,
        )


def test_exact_github_review_source_reconstructs_raw_api_bytes(
    audit_fixture: _AuditFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for source in audit_fixture.github_review_sources:
        assert (
            audit_module._review_record_from_source(
                source,
                repository_id=123,
                repository_owner="acme",
                repository_name="laconian",
            )
            == source.record
        )

    source = audit_fixture.github_review_sources[0]
    payload = source.model_dump(mode="json")
    declared_length = source.observation_receipt.raw_response_byte_length
    payload["raw_response_base64"] = base64.b64encode(
        b"x" * (declared_length + 1)
    ).decode("ascii")

    def fail_if_decoded(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("mismatched review bytes reached Base64 decoding")

    with monkeypatch.context() as context:
        context.setattr(audit_module.base64, "b64decode", fail_if_decoded)
        with pytest.raises(ValidationError, match="encoded byte length"):
            ExactGitHubReviewSourceV1.model_validate_json(canonical_json_v1(payload))
    with monkeypatch.context() as context:
        context.setattr(audit_module.base64, "b64decode", fail_if_decoded)
        with pytest.raises(ValidationError, match="exact plain dictionary"):
            ExactGitHubReviewSourceV1.model_validate(
                _DictSubclass(source.model_dump(mode="python", round_trip=True))
            )


def test_review_source_rejects_wrong_endpoint_body_head_actor_state_or_timestamp(
    audit_fixture: _AuditFixture,
) -> None:
    source = audit_fixture.github_review_sources[0]
    stale_receipt = _rehash(
        source.observation_receipt,
        "laconian-audit-github-api-observation-receipt-v1",
        "github_audit_api_observation_receipt_sha256",
        observed_at_utc="2026-08-31T00:00:44Z",
    )
    with pytest.raises(ValidationError, match="observation predates"):
        _rehash(
            source,
            "laconian-audit-github-review-source-v1",
            "github_review_source_sha256",
            observation_receipt=stale_receipt,
        )

    hostile: list[ExactGitHubReviewSourceV1] = [
        _source_with_review_raw(
            source,
            base64.b64decode(source.raw_response_base64),
            endpoint=source.observation_receipt.endpoint + "/wrong",
        )
    ]
    mutations: tuple[tuple[str, Any], ...] = (
        ("body", "wrong review body"),
        ("commit_id", audit_fixture.chains[0].reveal_pr.head_sha),
        ("state", "CHANGES_REQUESTED"),
        ("submitted_at", "2026-08-31T00:00:45.000000Z"),
    )
    for field, value in mutations:
        raw = _raw_json(source.raw_response_base64)
        raw[field] = value
        hostile.append(_source_with_review_raw(source, canonical_json_v1(raw)))
    actor_raw = _raw_json(source.raw_response_base64)
    actor_raw["user"]["login"] = "impostor"
    hostile.append(_source_with_review_raw(source, canonical_json_v1(actor_raw)))
    exact_raw = base64.b64decode(source.raw_response_base64)
    hostile.append(
        _source_with_review_raw(
            source,
            exact_raw[:-1]
            + b',"id":'
            + str(source.record.review_id).encode("ascii")
            + b"}",
        )
    )
    for candidate in hostile:
        with pytest.raises((ValidationError, ValueError)):
            audit_module._review_record_from_source(
                candidate,
                repository_id=123,
                repository_owner="acme",
                repository_name="laconian",
            )

    coherent_semantic_mutations = (
        (
            "wrong-body",
            {
                "body": (
                    "laconian-audit-adjudication-core-v1\0" + "f" * 64 + "\n"
                )
            },
        ),
        (
            "wrong-head",
            {"reviewed_head_sha": audit_fixture.chains[0].reveal_pr.head_sha},
        ),
    )
    for expected_failure, changes in coherent_semantic_mutations:
        coherent_source, coherent_signoff = _coherent_review_mutation(
            source,
            audit_fixture.adjudication.signoffs[0],
            **changes,
        )
        with pytest.raises(ValueError, match=expected_failure):
            _verify_one_signoff_source(
                audit_fixture,
                coherent_source,
                coherent_signoff,
            )

    reviewer = audit_fixture.registry.reviewers[0]
    for ordinal, boundary_time in enumerate(
        (
            audit_fixture.chains[1].reveal_pr.merged_at_utc,
            audit_fixture.adjudication.adjudication_pr.merged_at_utc,
        ),
        start=901,
    ):
        boundary_source, boundary_signoff = _review_source_and_signoff(
            reviewer=reviewer,
            core=audit_fixture.adjudication.core,
            adjudication_pr=audit_fixture.adjudication.adjudication_pr,
            registry_sha256=audit_fixture.registry.audit_reviewer_registry_sha256,
            review_id=ordinal,
            submitted_at=boundary_time,
        )
        with pytest.raises(ValueError, match=r"stale|unauthorized"):
            _verify_one_signoff_source(
                audit_fixture,
                boundary_source,
                boundary_signoff,
            )


def test_adjudication_actor_is_distinct_from_both_reviewers_and_github_verified(
    audit_fixture: _AuditFixture,
) -> None:
    keyed_proof = _rehash(
        audit_fixture.adjudication.adjudication_pr,
        "laconian-audit-pull-request-proof-v1",
        "pull_request_proof_sha256",
        verification_mode="ssh_sha256",
        head_signing_fingerprint=audit_fixture.registry.reviewers[1].signing_fingerprint,
    )
    with pytest.raises(ValueError, match="GitHub verified"):
        _verify(
            audit_fixture,
            adjudication=_adjudication_with(
                audit_fixture.adjudication,
                adjudication_pr=keyed_proof,
            ),
        )

    partial_collisions: list[tuple[int, str]] = []
    for ordinal, reviewer in enumerate(audit_fixture.registry.reviewers):
        partial_collisions.extend(
            (
                (
                    reviewer.reviewer_numeric_account_id,
                    f"independent-adjudicator-{ordinal}",
                ),
                (9_900 + ordinal, reviewer.reviewer_login),
            )
        )
    for ordinal, (signer_id, signer_login) in enumerate(
        partial_collisions, start=440
    ):
        head = dataclasses.replace(
            audit_fixture.heads[4],
            signer_id=signer_id,
            signer_login=signer_login,
        )
        source, proof = _pull_request_source_and_proof(
            kind="adjudication",
            reviewer_id=None,
            campaign_id=audit_fixture.provider.index.campaign_id,
            head=head,
            merge=audit_fixture.merges[4],
            pr_number=audit_fixture.adjudication.adjudication_pr.pr_number,
            merged_at=audit_fixture.adjudication.adjudication_pr.merged_at_utc,
            changed_paths=audit_fixture.adjudication.adjudication_pr.changed_paths,
            identity_bundle=audit_fixture.provider.identity_registry_bundle,
            signing_key=None,
            ordinal=ordinal,
        )
        with pytest.raises(ValueError, match="distinct"):
            _verify(
                audit_fixture,
                adjudication=_adjudication_with(
                    audit_fixture.adjudication,
                    adjudication_pr=proof,
                ),
                pull_request_sources=(
                    *audit_fixture.pull_request_sources[:4],
                    source,
                ),  # type: ignore[arg-type]
            )


def test_every_audit_tuple_rejects_a_noncanonical_order(
    audit_fixture: _AuditFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github_source = audit_fixture.pull_request_sources[0]
    github_evidence = github_source.signature_evidence
    assert type(github_evidence) is GitHubVerifiedCommitEvidenceV1

    class ForeignGitHubEvidence(GitHubVerifiedCommitEvidenceV1):
        pass

    immediate_foreign_evidence = ForeignGitHubEvidence.model_construct(
        **{
            field: getattr(github_evidence, field)
            for field in GitHubVerifiedCommitEvidenceV1.model_fields
        }
    )
    source_payload = {
        field: getattr(github_source, field)
        for field in AuditPullRequestEvidenceSourceV1.model_fields
    }
    with pytest.raises(TypeError, match=r"foreign signature.?evidence"):
        AuditPullRequestEvidenceSourceV1.model_validate(
            source_payload | {"signature_evidence": immediate_foreign_evidence}
        )

    class ForeignGitHubProjection(GitHubCommitVerificationProjectionV1):
        pass

    foreign_projection = ForeignGitHubProjection.model_construct(
        **{
            field: getattr(github_evidence.github_rest_verification, field)
            for field in GitHubCommitVerificationProjectionV1.model_fields
        }
    )
    transitive_foreign_evidence = GitHubVerifiedCommitEvidenceV1.model_construct(
        **{
            **{
                field: getattr(github_evidence, field)
                for field in GitHubVerifiedCommitEvidenceV1.model_fields
            },
            "github_rest_verification": foreign_projection,
        }
    )
    with pytest.raises(TypeError, match="GitHubCommitVerificationProjectionV1"):
        AuditPullRequestEvidenceSourceV1.model_validate(
            source_payload | {"signature_evidence": transitive_foreign_evidence}
        )
    proof_payload = {
        field: getattr(audit_fixture.chains[0].commitment_pr, field)
        for field in PullRequestProofV1.model_fields
    }
    with pytest.raises(TypeError, match="GitHubCommitVerificationProjectionV1"):
        PullRequestProofV1.model_validate(
            proof_payload | {"signature_evidence": transitive_foreign_evidence}
        )

    class ForeignPullRequestProof(PullRequestProofV1):
        pass

    commitment_proof = audit_fixture.chains[0].commitment_pr
    foreign_proof = ForeignPullRequestProof.model_construct(
        **{field: getattr(commitment_proof, field) for field in PullRequestProofV1.model_fields}
    )
    chain_payload = {
        field: getattr(audit_fixture.chains[0], field) for field in ReviewerChainV1.model_fields
    }
    chain_payload["commitment_pr"] = foreign_proof
    with pytest.raises(TypeError, match="exact nested PullRequestProofV1 owner"):
        ReviewerChainV1.model_validate(chain_payload)
    model_constructed_chain = ReviewerChainV1.model_construct(**chain_payload)
    dictionary_payload = dict(chain_payload)
    dictionary_payload["commitment_pr"] = commitment_proof.model_dump(mode="json")
    dictionary_nested_chain = ReviewerChainV1.model_construct(**dictionary_payload)

    class ForeignAuditAdjudicationCore(AuditAdjudicationCoreV1):
        pass

    core = audit_fixture.adjudication.core
    foreign_core = ForeignAuditAdjudicationCore.model_construct(
        **{field: getattr(core, field) for field in AuditAdjudicationCoreV1.model_fields}
    )
    adjudication_payload = {
        field: getattr(audit_fixture.adjudication, field)
        for field in AuditAdjudicationV1.model_fields
    }
    adjudication_payload["core"] = foreign_core
    model_constructed_adjudication = AuditAdjudicationV1.model_construct(
        **adjudication_payload
    )

    events: list[str] = []

    def provider_first(value: object) -> object:
        events.append("provider")
        return value

    def sample_must_not_run(*args: object, **kwargs: object) -> None:
        events.append("sample")
        raise AssertionError("sample replay ran before hostile nested-owner rejection")

    with monkeypatch.context() as context:
        context.setattr(
            audit_module, "_revalidate_verified_provider_evidence_v1", provider_first
        )
        context.setattr(audit_module, "_checked_sample", sample_must_not_run)
        with pytest.raises(TypeError, match="exact nested PullRequestProofV1 owner"):
            verify_reviewer_chain(
                model_constructed_chain,
                sample=audit_fixture.sample,
                provider_evidence=audit_fixture.provider,
                audit_git_object_archive=audit_fixture.archive,
                commitment_sources=audit_fixture.pull_request_sources[:2],
                reveal_source=audit_fixture.pull_request_sources[2],
            )
        assert events == ["provider"]
        events.clear()
        with pytest.raises(TypeError, match="exact nested PullRequestProofV1 owner"):
            verify_reviewer_chain(
                dictionary_nested_chain,
                sample=audit_fixture.sample,
                provider_evidence=audit_fixture.provider,
                audit_git_object_archive=audit_fixture.archive,
                commitment_sources=audit_fixture.pull_request_sources[:2],
                reveal_source=audit_fixture.pull_request_sources[2],
            )
        assert events == ["provider"]
        events.clear()
        with pytest.raises(TypeError, match="exact nested AuditAdjudicationCoreV1 owner"):
            verify_audit_chain(
                chains=audit_fixture.chains,
                adjudication=model_constructed_adjudication,
                sample=audit_fixture.sample,
                provider_evidence=audit_fixture.provider,
                audit_git_object_archive=audit_fixture.archive,
                pull_request_sources=audit_fixture.pull_request_sources,
                github_review_sources=audit_fixture.github_review_sources,
            )
        assert events == ["provider"]

    with pytest.raises(ValueError, match="reviewer chains"):
        _verify(audit_fixture, chains=tuple(reversed(audit_fixture.chains)))
    sources = list(audit_fixture.pull_request_sources)
    sources[0], sources[1] = sources[1], sources[0]
    with pytest.raises(ValueError, match="pull-request sources"):
        _verify(audit_fixture, pull_request_sources=tuple(sources))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="review sources"):
        _verify(
            audit_fixture,
            github_review_sources=tuple(reversed(audit_fixture.github_review_sources)),  # type: ignore[arg-type]
        )
    reversed_reveals = _rehash(
        audit_fixture.adjudication.core,
        "laconian-audit-adjudication-core-v1",
        "adjudication_core_sha256",
        reveal_sha256s=tuple(reversed(audit_fixture.adjudication.core.reveal_sha256s)),
    )
    with pytest.raises(ValueError, match="authority"):
        _verify(
            audit_fixture,
            adjudication=_adjudication_with(
                audit_fixture.adjudication,
                core=reversed_reveals,
            ),
        )
    with pytest.raises(ValidationError, match="reviewer-ID byte order"):
        _adjudication_with(
            audit_fixture.adjudication,
            signoffs=tuple(reversed(audit_fixture.adjudication.signoffs)),
        )
    with pytest.raises(ValidationError, match="UTF-8 byte order"):
        _rehash(
            audit_fixture.chains[0].reveal_pr,
            "laconian-audit-pull-request-proof-v1",
            "pull_request_proof_sha256",
            changed_paths=tuple(reversed(audit_fixture.chains[0].reveal_pr.changed_paths)),
        )
    with pytest.raises(ValidationError, match="byte order"):
        _rehash(
            audit_fixture.chains[0].reveal,
            "laconian-audit-reveal-v1",
            "reveal_sha256",
            labels=tuple(reversed(audit_fixture.chains[0].reveal.labels)),
        )
    with pytest.raises(ValidationError, match="byte order"):
        _rehash(
            audit_fixture.adjudication.core,
            "laconian-audit-adjudication-core-v1",
            "adjudication_core_sha256",
            consensus=tuple(reversed(audit_fixture.adjudication.core.consensus)),
        )
