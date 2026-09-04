"""Frozen protocol-review contracts for the public benchmark."""

from __future__ import annotations

import base64
import hashlib
import importlib
import inspect
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import warnings
from collections.abc import MutableMapping
from dataclasses import replace
from functools import cache
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast, get_args
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import laconian_eval.benchmark.protocol_review as protocol_review
from laconian_eval.benchmark.attachments import CanonicalJSONV1Error, canonical_json_v1
from laconian_eval.benchmark.protocol_review import (
    BENCHMARK_WORKFLOW_PATHS_V1,
    GITHUB_COMMIT_SIGNER_QUERY_V1,
    GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
    PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1,
    ArchivedApiBlobV1,
    ArchivedApiReceiptBindingV1,
    AuditReviewerSigningKeyV1,
    GitHubCommitVerificationProjectionV1,
    GitHubSignatureObservationReceiptV1,
    GitHubSignatureProjectionV1,
    GitHubVerifiedCommitEvidenceV1,
    InputTagMessageV1,
    LocalSignatureVerificationReceiptV1,
    OpenPGPVerifiedCommitEvidenceV1,
    ProtocolAttestationBundleV1,
    ProtocolBundleBuilderGitIdentityV1,
    ProtocolReviewerBindingV1,
    ProtocolReviewerRegistryV1,
    ProtocolReviewIdentityRegistryBundleV1,
    ProtocolReviewObjectArchiveV1,
    ProtocolReviewRoleV1,
    ProtocolReviewSigningKeyV1,
    ProtocolReviewStatementV1,
    ProtocolSignatureEvidenceSourceV1,
    ProtocolSubjectKindV1,
    ReviewerAccountBindingV1,
    SSHVerifiedCommitEvidenceV1,
    TagCreationRuleSuiteReceiptV1,
    TagOperatorProjectionV1,
    TagOperatorRegistryV1,
    TagRulesetBypassActorV1,
    TagRulesetObservationReceiptV1,
    TagRulesetPolicyV1,
    TagRulesetProjectionV1,
    TagRulesetRequestTargetV1,
    TagRulesetRuleV1,
    WorkflowInventoryV1,
    _read_exact_active_file,
    _validate_github_signature_armor,
    _validate_only_tree_delta,
    _validate_safe_raw_body,
    _verify_active_verifier_runtime,
    _verify_ed25519,
    _verify_installed_verifier_dependency_inventory,
    _verify_keyed_signature_v1,
    build_protocol_attestation_bundle,
    build_protocol_attestation_tag_binding,
    build_protocol_review_object_archive,
    build_workflow_inventory,
    canonical_reviewer_registry_bytes,
    compute_audit_reviewer_registry_sha256,
    compute_protocol_reviewer_registry_sha256,
    load_verified_protocol_review_object_archive,
    parse_protocol_git_object,
    protocol_review_digest,
    verify_commit_signature_evidence_source,
    verify_protocol_review_dag,
    verify_protocol_review_prefix,
)
from tests.benchmark.helpers import (
    audit_reviewer_registry,
    audit_reviewer_signing_key,
    audit_reviewer_ssh_key_material,
)

SECURITY_SUBJECT_KINDS_V1: tuple[ProtocolSubjectKindV1, ...] = (
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


def _digest(domain: str, value: object) -> str:
    return hashlib.sha256(domain.encode() + b"\n" + canonical_json_v1(value)).hexdigest()


_TEST_ED_P = 2**255 - 19
_TEST_ED_Q = 2**252 + 27742317777372353535851937790883648493
_TEST_ED_D = (-121665 * pow(121666, _TEST_ED_P - 2, _TEST_ED_P)) % _TEST_ED_P
_TEST_ED_I = pow(2, (_TEST_ED_P - 1) // 4, _TEST_ED_P)


def _test_ed_x(y: int, sign: int) -> int:
    y2 = y * y % _TEST_ED_P
    x2 = (y2 - 1) * pow(_TEST_ED_D * y2 + 1, _TEST_ED_P - 2, _TEST_ED_P) % _TEST_ED_P
    x = pow(x2, (_TEST_ED_P + 3) // 8, _TEST_ED_P)
    if (x * x - x2) % _TEST_ED_P:
        x = x * _TEST_ED_I % _TEST_ED_P
    assert (x * x - x2) % _TEST_ED_P == 0
    return _TEST_ED_P - x if (x & 1) != sign else x


_TEST_ED_BASE_Y = 4 * pow(5, _TEST_ED_P - 2, _TEST_ED_P) % _TEST_ED_P
_TEST_ED_BASE = (_test_ed_x(_TEST_ED_BASE_Y, 0), _TEST_ED_BASE_Y)


def _test_ed_add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    product = _TEST_ED_D * x1 * x2 * y1 * y2 % _TEST_ED_P
    return (
        (x1 * y2 + y1 * x2) * pow(1 + product, _TEST_ED_P - 2, _TEST_ED_P) % _TEST_ED_P,
        (y1 * y2 + x1 * x2) * pow(1 - product, _TEST_ED_P - 2, _TEST_ED_P) % _TEST_ED_P,
    )


def _test_ed_mult(scalar: int, point: tuple[int, int]) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _test_ed_add(result, addend)
        addend = _test_ed_add(addend, addend)
        scalar >>= 1
    return result


def _test_ed_encode(point: tuple[int, int]) -> bytes:
    x, y = point
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _test_ed_key(seed: bytes) -> tuple[bytes, bytes]:
    digest = hashlib.sha512(seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    return _test_ed_encode(_test_ed_mult(scalar, _TEST_ED_BASE)), digest[32:]


def _test_ed_sign(seed: bytes, message: bytes) -> tuple[bytes, bytes]:
    public_key, prefix = _test_ed_key(seed)
    digest = hashlib.sha512(seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _TEST_ED_Q
    encoded_r = _test_ed_encode(_test_ed_mult(nonce, _TEST_ED_BASE))
    challenge = (
        int.from_bytes(hashlib.sha512(encoded_r + public_key + message).digest(), "little")
        % _TEST_ED_Q
    )
    encoded_s = ((nonce + challenge * scalar) % _TEST_ED_Q).to_bytes(32, "little")
    return public_key, encoded_r + encoded_s


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


def _github_signature() -> bytes:
    signature_body = (
        b"\x04\x00\x16\x08"  # v4, binary document, EdDSA, SHA-256
        + b"\x00\x00"  # empty hashed subpackets
        + b"\x00\x00"  # empty unhashed subpackets
        + b"\x00\x00"  # left 16 bits of the digest
        + _openpgp_mpi(b"\x01")
        + _openpgp_mpi(b"\x01")
    )
    packet = _openpgp_packet(2, signature_body)
    return _armor(
        packet,
        b"-----BEGIN PGP SIGNATURE-----",
        b"-----END PGP SIGNATURE-----",
        64,
        pgp=True,
    )


def _ssh_signature(seed: bytes, key_blob: bytes, signed_payload: bytes) -> bytes:
    preimage = (
        b"SSHSIG"
        + _ssh_string(b"git")
        + _ssh_string(b"")
        + _ssh_string(b"sha512")
        + _ssh_string(hashlib.sha512(signed_payload).digest())
    )
    _, raw_signature = _test_ed_sign(seed, preimage)
    signature_blob = _ssh_string(b"ssh-ed25519") + _ssh_string(raw_signature)
    decoded = (
        b"SSHSIG"
        + (1).to_bytes(4, "big")
        + _ssh_string(key_blob)
        + _ssh_string(b"git")
        + _ssh_string(b"")
        + _ssh_string(b"sha512")
        + _ssh_string(signature_blob)
    )
    return _armor(
        decoded,
        b"-----BEGIN SSH SIGNATURE-----",
        b"-----END SSH SIGNATURE-----",
        70,
        pgp=False,
    )


_TEST_OPENPGP_ED25519_OID = bytes.fromhex("2b06010401da470f01")


def _openpgp_packet(tag: int, body: bytes) -> bytes:
    length = len(body)
    if length < 192:
        encoded_length = bytes((length,))
    elif length <= 8_383:
        adjusted = length - 192
        encoded_length = bytes(((adjusted >> 8) + 192, adjusted & 0xFF))
    else:
        encoded_length = b"\xff" + length.to_bytes(4, "big")
    return bytes((0xC0 | tag,)) + encoded_length + body


def _openpgp_mpi(raw: bytes) -> bytes:
    value = int.from_bytes(raw, "big")
    assert value > 0
    encoded = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return value.bit_length().to_bytes(2, "big") + encoded


def _openpgp_subpacket(subpacket_type: int, data: bytes, *, critical: bool = False) -> bytes:
    body = bytes((subpacket_type | (0x80 if critical else 0),)) + data
    length = len(body)
    if length < 192:
        return bytes((length,)) + body
    adjusted = length - 192
    return bytes(((adjusted >> 8) + 192, adjusted & 0xFF)) + body


def _openpgp_key_body(seed: bytes, created_at: int) -> tuple[bytes, bytes, str]:
    public_key, _ = _test_ed_key(seed)
    body = (
        b"\x04"
        + created_at.to_bytes(4, "big")
        + b"\x16"
        + bytes((len(_TEST_OPENPGP_ED25519_OID),))
        + _TEST_OPENPGP_ED25519_OID
        + _openpgp_mpi(b"\x40" + public_key)
    )
    fingerprint = hashlib.sha1(b"\x99" + len(body).to_bytes(2, "big") + body).hexdigest().upper()
    return body, public_key, fingerprint


def _openpgp_signed_key(key_body: bytes) -> bytes:
    return b"\x99" + len(key_body).to_bytes(2, "big") + key_body


def _openpgp_signature_body(
    *,
    signature_type: int,
    seed: bytes,
    issuer_fingerprint: str,
    signed_data: bytes,
    created_at: int,
    key_flags: int | None = None,
    signature_expiration: int | None = None,
    key_expiration: int | None = None,
    embedded_signature: bytes | None = None,
    unknown_critical: bool = False,
    issuer_fingerprint_subpacket: bool = True,
) -> bytes:
    hashed = _openpgp_subpacket(2, created_at.to_bytes(4, "big"))
    if issuer_fingerprint_subpacket:
        hashed += _openpgp_subpacket(33, b"\x04" + bytes.fromhex(issuer_fingerprint))
    else:
        hashed += _openpgp_subpacket(16, bytes.fromhex(issuer_fingerprint)[-8:])
    if signature_expiration is not None:
        hashed += _openpgp_subpacket(3, signature_expiration.to_bytes(4, "big"))
    if key_expiration is not None:
        hashed += _openpgp_subpacket(9, key_expiration.to_bytes(4, "big"))
    if key_flags is not None:
        hashed += _openpgp_subpacket(27, bytes((key_flags,)))
    if embedded_signature is not None:
        hashed += _openpgp_subpacket(32, embedded_signature)
    if unknown_critical:
        hashed += _openpgp_subpacket(100, b"hostile", critical=True)
    signed_header = (
        b"\x04" + bytes((signature_type, 22, 8)) + len(hashed).to_bytes(2, "big") + hashed
    )
    trailer = b"\x04\xff" + len(signed_header).to_bytes(4, "big")
    digest = hashlib.sha256(signed_data + signed_header + trailer).digest()
    _, signature = _test_ed_sign(seed, digest)
    return (
        signed_header
        + b"\x00\x00"
        + digest[:2]
        + _openpgp_mpi(signature[:32])
        + _openpgp_mpi(signature[32:])
    )


def _openpgp_fixture(
    *,
    use_subkey: bool,
    include_embedded: bool = True,
    detached_type: int = 0x00,
    detached_unknown_critical: bool = False,
    detached_key_id_only: bool = False,
    primary_key_expiration: int | None = None,
):
    created_at = 1_788_048_000
    signed_at = 1_788_134_400
    primary_seed = hashlib.sha256(b"openpgp-primary-seed").digest()
    primary_body, _, primary_fingerprint = _openpgp_key_body(primary_seed, created_at)
    user_id = b"OpenPGP Review Author <openpgp-review@example.com>"
    certification = _openpgp_signature_body(
        signature_type=0x13,
        seed=primary_seed,
        issuer_fingerprint=primary_fingerprint,
        signed_data=(
            _openpgp_signed_key(primary_body) + b"\xb4" + len(user_id).to_bytes(4, "big") + user_id
        ),
        created_at=created_at,
        key_flags=0x03,
        key_expiration=primary_key_expiration,
    )
    key_bytes = (
        _openpgp_packet(6, primary_body)
        + _openpgp_packet(13, user_id)
        + _openpgp_packet(2, certification)
    )
    signing_seed = primary_seed
    signing_fingerprint = primary_fingerprint
    if use_subkey:
        subkey_seed = hashlib.sha256(b"openpgp-signing-subkey-seed").digest()
        subkey_body, _, subkey_fingerprint = _openpgp_key_body(subkey_seed, created_at + 1)
        signed_keys = _openpgp_signed_key(primary_body) + _openpgp_signed_key(subkey_body)
        embedded = _openpgp_signature_body(
            signature_type=0x19,
            seed=subkey_seed,
            issuer_fingerprint=subkey_fingerprint,
            signed_data=signed_keys,
            created_at=created_at + 1,
        )
        binding = _openpgp_signature_body(
            signature_type=0x18,
            seed=primary_seed,
            issuer_fingerprint=primary_fingerprint,
            signed_data=signed_keys,
            created_at=created_at + 1,
            key_flags=0x02,
            embedded_signature=embedded if include_embedded else None,
        )
        key_bytes += _openpgp_packet(14, subkey_body) + _openpgp_packet(2, binding)
        signing_seed = subkey_seed
        signing_fingerprint = subkey_fingerprint
    payload = b"tree " + b"1" * 40 + b"\n\nopenpgp review\n"
    detached = _openpgp_signature_body(
        signature_type=detached_type,
        seed=signing_seed,
        issuer_fingerprint=signing_fingerprint,
        signed_data=payload,
        created_at=signed_at,
        unknown_critical=detached_unknown_critical,
        issuer_fingerprint_subpacket=not detached_key_id_only,
    )
    armor = _armor(
        _openpgp_packet(2, detached),
        b"-----BEGIN PGP SIGNATURE-----",
        b"-----END PGP SIGNATURE-----",
        64,
        pgp=True,
    )
    return SimpleNamespace(
        key_bytes=key_bytes,
        primary_fingerprint=primary_fingerprint,
        signing_seed=signing_seed,
        signing_fingerprint=signing_fingerprint,
        payload=payload,
        signature=armor,
        signed_at="2026-08-31T00:00:00Z",
    )


def _openpgp_signature_for_payload(
    fixture: SimpleNamespace,
    payload: bytes,
    *,
    signing_seed: bytes | None = None,
) -> bytes:
    detached = _openpgp_signature_body(
        signature_type=0x00,
        seed=fixture.signing_seed if signing_seed is None else signing_seed,
        issuer_fingerprint=fixture.signing_fingerprint,
        signed_data=payload,
        created_at=1_788_134_400,
    )
    return _armor(
        _openpgp_packet(2, detached),
        b"-----BEGIN PGP SIGNATURE-----",
        b"-----END PGP SIGNATURE-----",
        64,
        pgp=True,
    )


def _operator() -> TagOperatorProjectionV1:
    payload: dict[str, object] = {
        "operator_account_id": 101,
        "operator_login": "tag-operator",
        "tagger_name": "Laconian Tag Operator",
        "tagger_email": "tag-operator@users.noreply.github.com",
    }
    payload["tag_operator_sha256"] = _digest("laconian-tag-operator-v1", payload)
    return TagOperatorProjectionV1.model_validate(payload)


def _operator_registry() -> TagOperatorRegistryV1:
    operator = _operator()
    payload: dict[str, object] = {
        "schema_version": "TagOperatorRegistryV1",
        "repository_id": 123,
        "operators": [operator.model_dump(mode="json")],
    }
    payload["tag_operator_registry_sha256"] = _digest("laconian-tag-operator-registry-v1", payload)
    return TagOperatorRegistryV1.model_validate(payload)


def _ruleset_policy() -> TagRulesetPolicyV1:
    includes = (
        "refs/tags/benchmark-input-*",
        "refs/tags/benchmark-attestations-*",
    )
    rulesets = (
        TagRulesetProjectionV1(
            semantic_role="creation_authorizer",
            ruleset_id=11,
            source_type="Repository",
            source_id=123,
            target="tag",
            enforcement="active",
            include_patterns=includes,
            exclude_patterns=(),
            rules=(TagRulesetRuleV1(type="creation", parameters=None),),
            bypass_actors=(
                TagRulesetBypassActorV1(actor_id=101, actor_type="User", bypass_mode="always"),
            ),
        ),
        TagRulesetProjectionV1(
            semantic_role="immutability",
            ruleset_id=12,
            source_type="Repository",
            source_id=123,
            target="tag",
            enforcement="active",
            include_patterns=includes,
            exclude_patterns=(),
            rules=(
                TagRulesetRuleV1(type="update", parameters=None),
                TagRulesetRuleV1(type="deletion", parameters=None),
            ),
            bypass_actors=(),
        ),
    )
    payload: dict[str, object] = {
        "schema_version": "TagRulesetPolicyV1",
        "repository_id": 123,
        "rulesets": [item.model_dump(mode="json") for item in rulesets],
    }
    payload["tag_ruleset_policy_root"] = _digest("laconian-tag-ruleset-policy-v2", payload)
    return TagRulesetPolicyV1.model_validate(payload)


def _security_statement_payload(
    subject_kinds: tuple[ProtocolSubjectKindV1, ...],
) -> dict[str, object]:
    subjects = [
        {"kind": kind, "sha256": f"{ordinal:064x}"}
        for ordinal, kind in enumerate(subject_kinds, start=1)
    ]
    payload: dict[str, object] = {
        "schema_version": "ProtocolReviewStatementV1",
        "role": "security_evidence",
        "protocol_registry_sha256": "a" * 64,
        "reviewer_numeric_account_id": 101,
        "reviewer_login": "security-reviewer",
        "verification_mode": "ssh_sha256",
        "signing_fingerprint": "SHA256:" + "A" * 43,
        "input_tag_ref": "refs/tags/benchmark-input-20260831.1",
        "input_tag_oid": "b" * 40,
        "input_tag_object_sha256": "c" * 64,
        "peeled_c0_oid": "d" * 40,
        "peeled_c0_sha256": "e" * 64,
        "workflow_root": "f" * 64,
        "subjects": subjects,
        "subject_root": protocol_review_digest(
            "laconian-protocol-review-subjects-root-v1", subjects
        ),
        "signed_at": "2026-08-31T00:00:00Z",
    }
    payload["statement_sha256"] = protocol_review_digest(
        "laconian-protocol-review-statement-v1", payload
    )
    return payload


def test_protocol_review_digest_uses_exact_lf_separator_and_rejects_alternates() -> None:
    payload = {"schema_version": "1", "value": 7}
    expected = _digest("laconian-test-v1", payload)
    assert protocol_review_digest("laconian-test-v1", payload) == expected
    assert (
        expected != hashlib.sha256(b"laconian-test-v1\0" + canonical_json_v1(payload)).hexdigest()
    )
    assert expected != hashlib.sha256(b"laconian-test-v1" + canonical_json_v1(payload)).hexdigest()
    assert (
        expected != hashlib.sha256(b"laconian-test-v1\n\n" + canonical_json_v1(payload)).hexdigest()
    )
    for bad_domain in ("", "e\u0301", "domain\n", "domain\0value"):
        with pytest.raises(CanonicalJSONV1Error):
            protocol_review_digest(bad_domain, payload)


def test_graphql_query_has_exact_golden_bytes_and_digest() -> None:
    encoded = GITHUB_COMMIT_SIGNER_QUERY_V1.encode("utf-8")
    assert len(encoded) == 357
    assert encoded.endswith(b"}\n")
    assert hashlib.sha256(encoded).hexdigest() == (
        "141ec2ce356c197073e0aeece28a804b56b8c31a615a3d36995c72ce2c9b3d7b"
    )
    assert hashlib.sha256(encoded).hexdigest() == GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1


def test_operator_registry_has_one_exact_user_and_ascii_tagger_identity() -> None:
    registry = _operator_registry()
    assert len(registry.operators) == 1
    assert tuple(TagOperatorRegistryV1.model_fields) == (
        "schema_version",
        "repository_id",
        "operators",
        "tag_operator_registry_sha256",
    )
    for mutation in (
        {"tagger_name": " leading"},
        {"tagger_name": "two  spaces"},
        {"tagger_name": "Unicode é"},
        {"tagger_email": "bad..dots@example.com"},
        {"tagger_email": "a b@example.com"},
    ):
        payload = _operator().model_dump(mode="json") | mutation
        payload["tag_operator_sha256"] = _digest(
            "laconian-tag-operator-v1",
            {key: value for key, value in payload.items() if key != "tag_operator_sha256"},
        )
        with pytest.raises(ValidationError):
            TagOperatorProjectionV1.model_validate(payload)


def test_two_stable_rulesets_allow_only_operator_creation_bypass() -> None:
    policy = _ruleset_policy()
    assert tuple(item.semantic_role for item in policy.rulesets) == (
        "creation_authorizer",
        "immutability",
    )
    assert tuple(rule.type for rule in policy.rulesets[1].rules) == ("update", "deletion")
    payload = policy.model_dump(mode="json")
    payload["rulesets"][1]["bypass_actors"] = [
        {"actor_id": 101, "actor_type": "User", "bypass_mode": "always"}
    ]
    payload["tag_ruleset_policy_root"] = _digest(
        "laconian-tag-ruleset-policy-v2",
        {key: value for key, value in payload.items() if key != "tag_ruleset_policy_root"},
    )
    with pytest.raises(ValidationError):
        TagRulesetPolicyV1.model_validate(payload)


def test_input_tag_message_has_exact_fields_and_no_future_value() -> None:
    message = InputTagMessageV1(
        schema_version="InputTagMessageV1",
        input_tag_ref="refs/tags/benchmark-input-20260831.1",
        companion_tag_ref="refs/tags/benchmark-attestations-20260831.1",
        peeled_c0_oid="a" * 40,
        protocol_reviewer_registry_sha256="b" * 64,
        tag_operator_registry_sha256="c" * 64,
        tag_ruleset_policy_root="d" * 64,
        workflow_root="e" * 64,
    )
    assert tuple(InputTagMessageV1.model_fields) == (
        "schema_version",
        "input_tag_ref",
        "companion_tag_ref",
        "peeled_c0_oid",
        "protocol_reviewer_registry_sha256",
        "tag_operator_registry_sha256",
        "tag_ruleset_policy_root",
        "workflow_root",
    )
    assert canonical_json_v1(message.model_dump(mode="json"))[-1:] != b"\n"
    with pytest.raises(ValidationError):
        InputTagMessageV1.model_validate(
            message.model_dump(mode="json") | {"bundle_commit_oid": "f" * 40}
        )


def test_bundle_builder_identity_has_exact_literals_and_lf_self_digest() -> None:
    payload: dict[str, object] = {
        "schema_version": "ProtocolBundleBuilderGitIdentityV1",
        "name_ascii": "Laconian Protocol Bundle Builder",
        "email_ascii": "laconian-protocol-bundle-builder@users.noreply.github.com",
    }
    payload["protocol_bundle_builder_git_identity_sha256"] = _digest(
        "laconian-protocol-bundle-builder-git-identity-v1", payload
    )
    identity = ProtocolBundleBuilderGitIdentityV1.model_validate(payload)
    assert (
        identity.protocol_bundle_builder_git_identity_sha256
        == payload["protocol_bundle_builder_git_identity_sha256"]
    )
    assert tuple(ProtocolBundleBuilderGitIdentityV1.model_fields) == (
        "schema_version",
        "name_ascii",
        "email_ascii",
        "protocol_bundle_builder_git_identity_sha256",
    )
    with pytest.raises(ValidationError):
        ProtocolBundleBuilderGitIdentityV1.model_validate(payload | {"name_ascii": "Another"})


def test_workflow_inventory_has_exact_three_fields_and_fifteen_ordered_members() -> None:
    files = {
        path: f"workflow:{ordinal}\n".encode()
        for ordinal, path in enumerate(BENCHMARK_WORKFLOW_PATHS_V1)
    }
    inventory = build_workflow_inventory(c0_workflow_bytes=files)
    assert tuple(WorkflowInventoryV1.model_fields) == (
        "schema_version",
        "members",
        "workflow_root",
    )
    assert len(inventory.members) == 15
    assert tuple(item.path for item in inventory.members) == BENCHMARK_WORKFLOW_PATHS_V1
    assert inventory.workflow_root == _digest(
        "laconian-workflow-inventory-v1",
        inventory.model_dump(mode="json", exclude={"workflow_root"}),
    )
    with pytest.raises((ValidationError, ValueError)):
        build_workflow_inventory(c0_workflow_bytes=dict(reversed(tuple(files.items()))))
    with pytest.raises((ValidationError, ValueError)):
        WorkflowInventoryV1.model_validate(
            inventory.model_dump(mode="json")
            | {"members": inventory.model_dump(mode="json")["members"][:-1]}
        )


def test_security_statement_has_exact_approved_fourteen_subjects() -> None:
    statement = ProtocolReviewStatementV1.model_validate(
        _security_statement_payload(SECURITY_SUBJECT_KINDS_V1)
    )
    assert tuple(item.kind for item in statement.subjects) == SECURITY_SUBJECT_KINDS_V1
    assert (
        PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1["security_evidence"] == SECURITY_SUBJECT_KINDS_V1
    )
    former_eleven = tuple(
        kind
        for kind in SECURITY_SUBJECT_KINDS_V1
        if kind
        not in {
            "publication_branch_ruleset_policy_sha256",
            "broker_token_delivery_isolation_policy_sha256",
            "broker_signing_keys_root_sha256",
        }
    )
    mutations = (
        former_eleven,
        SECURITY_SUBJECT_KINDS_V1[:-1],
        (*SECURITY_SUBJECT_KINDS_V1, "invalid_event_dismissal_policy_sha256"),
        (
            *SECURITY_SUBJECT_KINDS_V1[:6],
            SECURITY_SUBJECT_KINDS_V1[7],
            SECURITY_SUBJECT_KINDS_V1[6],
            *SECURITY_SUBJECT_KINDS_V1[8:],
        ),
    )
    for mutated in mutations:
        with pytest.raises(ValidationError):
            ProtocolReviewStatementV1.model_validate(_security_statement_payload(mutated))


def test_protocol_subject_mapping_is_immutable_and_literal_order_is_role_flattening() -> None:
    role_order: tuple[ProtocolReviewRoleV1, ...] = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    assert get_args(ProtocolSubjectKindV1) == tuple(
        kind for role in role_order for kind in PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1[role]
    )
    mutable = cast(
        MutableMapping[ProtocolReviewRoleV1, tuple[ProtocolSubjectKindV1, ...]],
        PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1,
    )
    with pytest.raises(TypeError):
        mutable["security_evidence"] = ()


def test_signature_evidence_variants_have_exact_mode_discriminated_fields() -> None:
    common = (
        "schema_version",
        "verification_mode",
        "commit_oid",
        "commit_object_sha256",
        "parent_commit_oid",
        "statement_path",
        "github_rest_verification",
        "github_graphql_signature",
    )
    assert tuple(GitHubVerifiedCommitEvidenceV1.model_fields) == common
    assert tuple(SSHVerifiedCommitEvidenceV1.model_fields) == (
        *common,
        "fingerprint",
        "keyring_sha256",
        "local_signature_verification",
    )
    assert tuple(OpenPGPVerifiedCommitEvidenceV1.model_fields) == (
        *common,
        "fingerprint",
        "keyring_sha256",
        "local_signature_verification",
    )


def test_stable_rest_and_graphql_projections_exclude_transport_metadata() -> None:
    rest_payload: dict[str, object] = {
        "schema_version": "GitHubCommitVerificationProjectionV1",
        "repository_id": 123,
        "commit_oid": "a" * 40,
        "api_version": "2022-11-28",
        "endpoint": "GET /repos/acme/repo/git/commits/" + "a" * 40,
        "verified": True,
        "reason": "valid",
        "payload": "tree " + "b" * 40 + "\n",
        "signature": "-----BEGIN SSH SIGNATURE-----\nx\n-----END SSH SIGNATURE-----",
        "verified_at": "2026-08-31T00:00:00.000000Z",
    }
    rest_payload["rest_projection_sha256"] = _digest(
        "laconian-github-commit-verification-projection-v1", rest_payload
    )
    rest = GitHubCommitVerificationProjectionV1.model_validate(rest_payload)
    graphql_payload: dict[str, object] = {
        "schema_version": "GitHubSignatureProjectionV1",
        "repository_id": 123,
        "commit_oid": "a" * 40,
        "query_sha256": GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
        "signer_database_id": 101,
        "signer_login": "reviewer",
        "is_valid": True,
        "state": "VALID",
    }
    graphql_payload["graphql_projection_sha256"] = _digest(
        "laconian-github-signature-projection-v1", graphql_payload
    )
    graphql = GitHubSignatureProjectionV1.model_validate(graphql_payload)
    assert "etag" not in GitHubCommitVerificationProjectionV1.model_fields
    assert "request_id" not in GitHubSignatureProjectionV1.model_fields
    for model, extra in ((rest, {"etag": "x"}), (graphql, {"verified_at": "x"})):
        with pytest.raises(ValidationError):
            type(model).model_validate(model.model_dump(mode="json") | extra)


def test_raw_git_object_parser_pins_sha1_and_sha256_over_header_plus_content() -> None:
    raw = b"hello protocol\n"
    wire = b"blob " + str(len(raw)).encode() + b"\0" + raw
    oid = hashlib.sha1(wire).hexdigest()
    parsed = parse_protocol_git_object(oid=oid, object_type="blob", raw_content=raw)
    assert parsed.oid == oid
    assert parsed.size == len(raw)
    assert parsed.git_object_sha256 == hashlib.sha256(wire).hexdigest()
    with pytest.raises(ValueError):
        parse_protocol_git_object(oid="0" * 40, object_type="blob", raw_content=raw)


def test_raw_protocol_trees_reject_executable_symlink_submodule_and_duplicate_names() -> None:
    child_oid = "1" * 40
    for mode in ("100755", "120000", "160000"):
        raw = mode.encode() + b" member\0" + bytes.fromhex(child_oid)
        wire = b"tree " + str(len(raw)).encode() + b"\0" + raw
        with pytest.raises(ValueError, match="regular non-executable"):
            parse_protocol_git_object(
                oid=hashlib.sha1(wire).hexdigest(),
                object_type="tree",
                raw_content=raw,
            )

    duplicate_name = (
        b"100644 same\0" + bytes.fromhex("1" * 40) + b"40000 same\0" + bytes.fromhex("2" * 40)
    )
    wire = b"tree " + str(len(duplicate_name)).encode() + b"\0" + duplicate_name
    with pytest.raises(ValueError, match="canonical unique"):
        parse_protocol_git_object(
            oid=hashlib.sha1(wire).hexdigest(),
            object_type="tree",
            raw_content=duplicate_name,
        )


def test_tree_delta_rejects_an_added_empty_subtree() -> None:
    store: dict[str, object] = {}
    parent_tree = _git_object(store, "tree", b"")
    empty_tree = _git_object(store, "tree", b"")
    child_tree = _git_object(
        store,
        "tree",
        b"40000 empty\0" + bytes.fromhex(empty_tree.oid),
    )

    def commit(tree_oid: str) -> object:
        return _git_object(
            store,
            "commit",
            (
                b"tree "
                + tree_oid.encode()
                + b"\nauthor Test Author <author@example.com> 0 +0000"
                + b"\ncommitter Test Committer <committer@example.com> 0 +0000"
                + b"\n\ntest\n"
            ),
        )

    parent = commit(parent_tree.oid)
    child = commit(child_tree.oid)
    with pytest.raises(ValueError, match="tree delta mismatch"):
        _validate_only_tree_delta(parent, child, cast(dict, store), ())


def test_registry_digest_helpers_revalidate_exact_bindings_and_reject_duplicates() -> None:
    first, second = audit_reviewer_registry().reviewers
    assert (
        compute_audit_reviewer_registry_sha256((first, second))
        == hashlib.sha256(canonical_reviewer_registry_bytes((first, second))).hexdigest()
    )
    with pytest.raises(ValueError, match="distinct"):
        compute_audit_reviewer_registry_sha256((first, first))

    forged = ReviewerAccountBindingV1.model_construct(
        reviewer_id="audit-c",
        reviewer_numeric_account_id=True,
        reviewer_login="audit-c",
        verification_mode="github_verified_commit",
        signing_fingerprint=None,
        signing_key=None,
        role="audit_reviewer",
    )
    with pytest.raises(ValidationError):
        canonical_reviewer_registry_bytes((first, forged))

    protocol = _protocol_reviewer_registry().reviewers
    with pytest.raises(ValueError, match="role order"):
        compute_protocol_reviewer_registry_sha256((protocol[1], protocol[0], protocol[2]))
    duplicate_identity = ProtocolReviewerBindingV1.model_validate(
        protocol[2].model_dump(mode="json")
        | {
            "reviewer_numeric_account_id": protocol[1].reviewer_numeric_account_id,
            "reviewer_login": protocol[1].reviewer_login,
        }
    )
    with pytest.raises(ValueError, match="distinct"):
        compute_protocol_reviewer_registry_sha256((protocol[0], protocol[1], duplicate_identity))


def test_audit_registry_directly_binds_exact_key_bytes_and_git_identities() -> None:
    from laconian_eval.benchmark.context import GenerationContextIndexV1
    from laconian_eval.benchmark.provider_evidence import ProviderEvidenceIndexV1

    registry = audit_reviewer_registry()
    github_reviewer, keyed_reviewer = registry.reviewers
    key = keyed_reviewer.signing_key
    assert type(key) is AuditReviewerSigningKeyV1
    assert tuple(AuditReviewerSigningKeyV1.model_fields) == (
        "schema_version",
        "verification_mode",
        "fingerprint",
        "author_name_ascii",
        "author_email_ascii",
        "committer_name_ascii",
        "committer_email_ascii",
        "public_key_encoding",
        "public_key_base64",
        "public_key_sha256",
    )
    assert tuple(ReviewerAccountBindingV1.model_fields) == (
        "reviewer_id",
        "reviewer_numeric_account_id",
        "reviewer_login",
        "verification_mode",
        "signing_fingerprint",
        "signing_key",
        "role",
    )
    assert registry.schema_version == "benchmark-reviewer-registry-v2"
    assert github_reviewer.signing_key is None
    assert key is not None
    _, expected_key_bytes, expected_fingerprint = audit_reviewer_ssh_key_material()
    assert base64.b64decode(key.public_key_base64, validate=True) == expected_key_bytes
    assert key.fingerprint == expected_fingerprint == keyed_reviewer.signing_fingerprint
    assert (
        key.author_name_ascii,
        key.author_email_ascii,
        key.committer_name_ascii,
        key.committer_email_ascii,
    ) == (
        "Audit Reviewer B",
        "audit-reviewer-b@users.noreply.github.com",
        "Audit Reviewer B",
        "audit-reviewer-b@users.noreply.github.com",
    )
    expected_bytes = canonical_json_v1(
        {
            "schema_version": "benchmark-reviewer-registry-v2",
            "reviewers": [item.model_dump(mode="json") for item in registry.reviewers],
        }
    )
    assert canonical_reviewer_registry_bytes(registry.reviewers) == expected_bytes
    assert registry.audit_reviewer_registry_sha256 == hashlib.sha256(expected_bytes).hexdigest()

    with warnings.catch_warnings(record=True) as serialization_warnings:
        warnings.simplefilter("always")
        binding_python = keyed_reviewer.model_dump(
            mode="python", round_trip=True, warnings=True
        )
        registry_python = registry.model_dump(
            mode="python", round_trip=True, warnings=True
        )
        registry_json = registry.model_dump(mode="json", warnings=True)
        registry_json_text = registry.model_dump_json(warnings=True)
        for parent_type in (GenerationContextIndexV1, ProviderEvidenceIndexV1):
            parent = parent_type.model_construct(audit_reviewer_registry=registry)
            parent_python = parent.model_dump(
                mode="python",
                round_trip=True,
                warnings=True,
                include={"audit_reviewer_registry"},
            )
            parent_json = parent.model_dump(
                mode="json", warnings=True, include={"audit_reviewer_registry"}
            )
            parent_json_text = parent.model_dump_json(
                warnings=True, include={"audit_reviewer_registry"}
            )
            parent_registry = parent_python["audit_reviewer_registry"]
            assert type(parent_registry["reviewers"]) is list
            assert all(
                type(item) is dict
                for item in parent_registry["reviewers"]
            )
            assert (
                protocol_review.AuditReviewerRegistryV1.model_validate(parent_registry)
                == registry
            )
            assert type(parent_json["audit_reviewer_registry"]["reviewers"]) is list
            assert all(
                type(item) is dict
                for item in parent_json["audit_reviewer_registry"]["reviewers"]
            )
            parsed_parent = json.loads(parent_json_text)
            assert type(parsed_parent["audit_reviewer_registry"]["reviewers"]) is list
            assert all(
                type(item) is dict
                for item in parsed_parent["audit_reviewer_registry"]["reviewers"]
            )
    assert serialization_warnings == []
    assert type(binding_python) is dict
    assert type(registry_python["reviewers"]) is list
    assert all(type(item) is dict for item in registry_python["reviewers"])
    assert (
        protocol_review.AuditReviewerRegistryV1.model_validate(registry_python)
        == registry
    )
    assert type(registry_json["reviewers"]) is list
    assert all(type(item) is dict for item in registry_json["reviewers"])
    parsed_registry = json.loads(registry_json_text)
    assert type(parsed_registry["reviewers"]) is list
    assert all(type(item) is dict for item in parsed_registry["reviewers"])
    assert protocol_review._class_bound_revalidate(
        registry, protocol_review.AuditReviewerRegistryV1
    ) == registry

    # Python callers must already carry the exact immutable pair owner.  In particular,
    # Pydantic's otherwise convenient sequence coercion cannot turn a mutable or executable
    # caller-owned container into registry authority.  Canonical JSON arrays remain the one
    # transport representation admitted for the tuple field.
    class ReviewerIterable:
        def __iter__(self):  # type: ignore[no-untyped-def]
            raise AssertionError("registry validation executed an arbitrary iterable")

    python_payload = registry.model_dump(mode="python", round_trip=True)
    for foreign_reviewers in (
        list(registry.reviewers),
        set(registry.reviewers),
        frozenset(registry.reviewers),
        ReviewerIterable(),
    ):
        with pytest.raises((TypeError, ValidationError)):
            protocol_review.AuditReviewerRegistryV1.model_validate(
                python_payload | {"reviewers": foreign_reviewers}
            )
    assert (
        protocol_review.AuditReviewerRegistryV1.model_validate_json(
            canonical_json_v1(registry.model_dump(mode="json"))
        )
        == registry
    )
    assert (
        protocol_review.AuditReviewerRegistryV1.model_validate(
            registry.model_dump(mode="json")
        )
        == registry
    )

    class ForeignDict(dict[str, object]):
        pass

    serialized_payload = registry.model_dump(mode="json")
    with (
        patch.object(
            protocol_review,
            "_preflight_exact_model_owners_v1",
            side_effect=AssertionError("wrong-length reviewer pair reached owner traversal"),
        ),
        pytest.raises(TypeError, match="exactly two"),
    ):
        protocol_review.AuditReviewerRegistryV1.model_validate(
            serialized_payload
            | {"reviewers": (*registry.reviewers, github_reviewer)}
        )
    with pytest.raises((TypeError, ValidationError), match="ReviewerAccountBindingV1"):
        protocol_review.AuditReviewerRegistryV1.model_validate(
            serialized_payload
            | {"reviewers": tuple(serialized_payload["reviewers"])}
        )
    with pytest.raises((TypeError, ValidationError)):
        protocol_review.AuditReviewerRegistryV1.model_validate(
            serialized_payload
            | {
                "reviewers": [
                    ForeignDict(serialized_payload["reviewers"][0]),
                    serialized_payload["reviewers"][1],
                ]
            }
        )

    nested_model_payload = registry.model_dump(mode="json")
    nested_model_payload["reviewers"][1]["signing_key"] = key
    with pytest.raises((TypeError, ValidationError), match=r"serialized|model owner"):
        protocol_review.AuditReviewerRegistryV1.model_validate(nested_model_payload)

    cyclic_list: list[object] = []
    cyclic_list.append(cyclic_list)
    cyclic_dict: dict[str, object] = {}
    cyclic_dict["self"] = cyclic_dict
    for cyclic_value in (cyclic_list, cyclic_dict):
        cyclic_payload = registry.model_dump(mode="json")
        cyclic_payload["reviewers"][0]["reviewer_login"] = cyclic_value
        with pytest.raises(TypeError, match="cycle"):
            protocol_review.AuditReviewerRegistryV1.model_validate(cyclic_payload)

    deep_value: object = "leaf"
    for _ in range(1_100):
        deep_value = [deep_value]
    deep_payload = registry.model_dump(mode="json")
    deep_payload["reviewers"][0]["reviewer_login"] = deep_value
    with pytest.raises(TypeError, match="nesting limit"):
        protocol_review.AuditReviewerRegistryV1.model_validate(deep_payload)

    wide_payload = registry.model_dump(mode="json")
    wide_payload["reviewers"][0]["reviewer_login"] = [None] * 262_144
    with pytest.raises(TypeError, match="node limit"):
        protocol_review.AuditReviewerRegistryV1.model_validate(wide_payload)

    shared_value: object = "leaf"
    for _ in range(18):
        shared_value = [shared_value, shared_value]
    shared_payload = registry.model_dump(mode="json")
    shared_payload["reviewers"][0]["reviewer_login"] = [shared_value, key]
    # This tiny graph needs memoization to reach the forbidden model within the budget.
    for node_limit, match in ((32, "node limit"), (64, "nested model owners")):
        with (
            patch.object(protocol_review, "_EXACT_MODEL_PREFLIGHT_NODE_LIMIT", node_limit),
            pytest.raises(TypeError, match=match),
        ):
            protocol_review.AuditReviewerRegistryV1.model_validate(shared_payload)

    legacy_payload = registry.model_dump(mode="json")
    legacy_payload["schema_version"] = "benchmark-reviewer-registry-v1"
    with pytest.raises(ValidationError):
        protocol_review.AuditReviewerRegistryV1.model_validate_json(
            canonical_json_v1(legacy_payload)
        )

    missing_key_field = github_reviewer.model_dump(mode="json")
    del missing_key_field["signing_key"]
    with pytest.raises(ValidationError):
        ReviewerAccountBindingV1.model_validate(missing_key_field)

    class ForeignAuditReviewerSigningKey(AuditReviewerSigningKeyV1):
        pass

    foreign_key = ForeignAuditReviewerSigningKey.model_construct(
        **{
            field: getattr(keyed_reviewer.signing_key, field)
            for field in AuditReviewerSigningKeyV1.model_fields
        }
    )
    foreign_binding = ReviewerAccountBindingV1.model_construct(
        **{
            **{
                field: getattr(keyed_reviewer, field)
                for field in ReviewerAccountBindingV1.model_fields
            },
            "signing_key": foreign_key,
        }
    )
    with pytest.raises((TypeError, ValueError), match="foreign signing-key owner"):
        canonical_reviewer_registry_bytes((github_reviewer, foreign_binding))
    registry_owner_payload = {
        field: getattr(registry, field)
        for field in protocol_review.AuditReviewerRegistryV1.model_fields
    }
    with pytest.raises((TypeError, ValidationError), match="signing-key owner"):
        protocol_review.AuditReviewerRegistryV1.model_validate(
            registry_owner_payload
            | {"reviewers": (github_reviewer, foreign_binding)}
        )

    dict_key_binding = ReviewerAccountBindingV1.model_construct(
        **{
            **{
                field: getattr(keyed_reviewer, field)
                for field in ReviewerAccountBindingV1.model_fields
            },
            "signing_key": key.model_dump(mode="python", round_trip=True),
        }
    )
    with pytest.raises((TypeError, ValidationError), match="signing-key owner"):
        protocol_review.AuditReviewerRegistryV1.model_validate(
            registry_owner_payload
            | {"reviewers": (github_reviewer, dict_key_binding)}
        )

    class ForeignReviewerAccountBinding(ReviewerAccountBindingV1):
        pass

    foreign_reviewer = ForeignReviewerAccountBinding.model_construct(
        **{
            field: getattr(keyed_reviewer, field)
            for field in ReviewerAccountBindingV1.model_fields
        }
    )
    with pytest.raises((TypeError, ValidationError), match="ReviewerAccountBindingV1"):
        protocol_review.AuditReviewerRegistryV1.model_validate(
            {
                **{
                    field: getattr(registry, field)
                    for field in protocol_review.AuditReviewerRegistryV1.model_fields
                },
                "reviewers": (github_reviewer, foreign_reviewer),
            }
        )
    for foreign_collection in (set, frozenset):
        foreign_registry = protocol_review.AuditReviewerRegistryV1.model_construct(
            schema_version="benchmark-reviewer-registry-v2",
            reviewers=foreign_collection((github_reviewer, foreign_reviewer)),
            audit_reviewer_registry_sha256=registry.audit_reviewer_registry_sha256,
        )
        with pytest.raises(TypeError, match="exact tuple owner"):
            protocol_review._class_bound_revalidate(
                foreign_registry, protocol_review.AuditReviewerRegistryV1
            )

    duplicate_key = ReviewerAccountBindingV1.model_validate(
        github_reviewer.model_dump(mode="json")
        | {
            "verification_mode": keyed_reviewer.verification_mode,
            "signing_fingerprint": keyed_reviewer.signing_fingerprint,
            "signing_key": key.model_dump(mode="json"),
        }
    )
    with pytest.raises(ValueError, match="distinct"):
        compute_audit_reviewer_registry_sha256((duplicate_key, keyed_reviewer))


def test_github_mode_rejects_an_audit_key_and_keyed_modes_require_one() -> None:
    registry = audit_reviewer_registry()
    github_reviewer, keyed_reviewer = registry.reviewers
    audit_key = audit_reviewer_signing_key()

    with pytest.raises(ValidationError):
        ReviewerAccountBindingV1.model_validate(
            github_reviewer.model_dump(mode="json")
            | {
                "signing_key": audit_key.model_dump(mode="json"),
            }
        )
    with pytest.raises(ValidationError):
        ReviewerAccountBindingV1.model_validate(
            keyed_reviewer.model_dump(mode="json") | {"signing_key": None}
        )
    with pytest.raises(ValidationError):
        ReviewerAccountBindingV1.model_validate(
            keyed_reviewer.model_dump(mode="json")
            | {"signing_fingerprint": "SHA256:" + "A" * 43}
        )

    protocol_key = ProtocolReviewSigningKeyV1(
        role="security_evidence",
        reviewer_numeric_account_id=keyed_reviewer.reviewer_numeric_account_id,
        reviewer_login=keyed_reviewer.reviewer_login,
        verification_mode=audit_key.verification_mode,
        fingerprint=audit_key.fingerprint,
        public_key_encoding=audit_key.public_key_encoding,
        public_key_base64=audit_key.public_key_base64,
        public_key_sha256=audit_key.public_key_sha256,
    )
    with pytest.raises(ValidationError):
        ReviewerAccountBindingV1.model_validate(
            keyed_reviewer.model_dump(mode="json") | {"signing_key": protocol_key}
        )


@pytest.mark.parametrize(
    "mutation",
    ("encoding", "bytes", "hash", "fingerprint", "algorithm"),
)
def test_audit_key_profile_rejects_wrong_encoding_bytes_hash_fingerprint_or_algorithm(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = audit_reviewer_signing_key()
    payload = key.model_dump(mode="json")
    if mutation == "encoding":
        payload["public_key_encoding"] = "openpgp-v4-ed25519-transferable-public-key-v1"
    elif mutation == "bytes":
        decoded = bytearray(base64.b64decode(key.public_key_base64, validate=True))
        decoded[-1] ^= 1
        payload["public_key_base64"] = base64.b64encode(decoded).decode("ascii")
    elif mutation == "hash":
        payload["public_key_sha256"] = "0" * 64
    elif mutation == "fingerprint":
        payload["fingerprint"] = "SHA256:" + "A" * 43
    else:
        _, valid_wire, _ = audit_reviewer_ssh_key_material()
        invalid_algorithm = b"ssh-rsa"
        algorithm_wire = (
            len(invalid_algorithm).to_bytes(4, "big")
            + invalid_algorithm
            + valid_wire[-36:]
        )
        payload["public_key_base64"] = base64.b64encode(algorithm_wire).decode("ascii")
        payload["public_key_sha256"] = hashlib.sha256(algorithm_wire).hexdigest()
        payload["fingerprint"] = "SHA256:" + base64.b64encode(
            hashlib.sha256(algorithm_wire).digest()
        ).decode("ascii").rstrip("=")
    with pytest.raises(ValidationError):
        AuditReviewerSigningKeyV1.model_validate(payload)

    oversized_payload = key.model_dump(mode="json")
    oversized_payload["public_key_base64"] = "A" * 87_388

    def fail_if_decoded(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("oversized audit key reached Base64 decoding")

    with monkeypatch.context() as context:
        context.setattr(protocol_review.base64, "b64decode", fail_if_decoded)
        with pytest.raises(ValidationError, match="encoded key material"):
            AuditReviewerSigningKeyV1.model_validate(oversized_payload)

    if mutation == "encoding":
        openpgp = _openpgp_fixture(use_subkey=True)
        openpgp_key = AuditReviewerSigningKeyV1(
            schema_version="AuditReviewerSigningKeyV1",
            verification_mode="openpgp_fingerprint",
            fingerprint=openpgp.primary_fingerprint,
            author_name_ascii="Audit OpenPGP Reviewer",
            author_email_ascii="audit-openpgp@users.noreply.github.com",
            committer_name_ascii="Audit OpenPGP Reviewer",
            committer_email_ascii="audit-openpgp@users.noreply.github.com",
            public_key_encoding="openpgp-v4-ed25519-transferable-public-key-v1",
            public_key_base64=base64.b64encode(openpgp.key_bytes).decode("ascii"),
            public_key_sha256=hashlib.sha256(openpgp.key_bytes).hexdigest(),
        )
        assert openpgp_key.fingerprint == openpgp.primary_fingerprint


def test_public_builder_and_parser_signatures_have_no_raw_trust_boolean() -> None:
    signature = inspect.signature(parse_protocol_git_object)
    assert tuple(signature.parameters) == ("oid", "object_type", "raw_content")
    assert "verified" not in signature.parameters


def test_protocol_models_reject_bool_numeric_and_bytes_string_coercion() -> None:
    operator = _operator().model_dump(mode="json")
    operator["operator_account_id"] = True
    operator["tag_operator_sha256"] = _digest(
        "laconian-tag-operator-v1",
        {key: value for key, value in operator.items() if key != "tag_operator_sha256"},
    )
    with pytest.raises(ValidationError):
        TagOperatorProjectionV1.model_validate(operator)

    statement = _security_statement_payload(SECURITY_SUBJECT_KINDS_V1)
    statement["signing_fingerprint"] = b"SHA256:" + b"A" * 43
    with pytest.raises(ValidationError):
        ProtocolReviewStatementV1.model_validate(statement)


def test_archived_api_blob_binds_exact_byte_length_hash_and_canonical_base64() -> None:
    raw = b'{"ok":true}'
    blob = ArchivedApiBlobV1(
        path="api/github_signature/" + "a" * 64 + "/00000000.response",
        kind="safe_raw_response",
        byte_length=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        raw_bytes_base64=base64.b64encode(raw).decode("ascii"),
    )
    assert tuple(ArchivedApiBlobV1.model_fields) == (
        "path",
        "kind",
        "byte_length",
        "sha256",
        "raw_bytes_base64",
    )
    with pytest.raises(ValidationError):
        ArchivedApiBlobV1.model_validate(
            blob.model_dump(mode="json") | {"byte_length": len(raw) + 1}
        )
    with pytest.raises(ValidationError):
        ArchivedApiBlobV1.model_validate(blob.model_dump(mode="json") | {"raw_bytes_base64": "e30"})


def test_protocol_signing_key_and_identity_bundle_are_strict_and_self_hashing() -> None:
    key_bytes = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + b"K" * 32
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key_bytes).digest()).decode().rstrip(
        "="
    )
    key = ProtocolReviewSigningKeyV1(
        role="security_evidence",
        reviewer_numeric_account_id=203,
        reviewer_login="reviewer-3",
        verification_mode="ssh_sha256",
        fingerprint=fingerprint,
        public_key_encoding="openssh-ed25519-wire-v1",
        public_key_base64=base64.b64encode(key_bytes).decode(),
        public_key_sha256=hashlib.sha256(key_bytes).hexdigest(),
    )
    source_sha256 = hashlib.sha256(b"source").hexdigest()
    lock_sha256 = hashlib.sha256(b"lock").hexdigest()
    inventory_root = "9" * 64
    tool = _digest(
        "laconian-protocol-signature-verifier-tool-v1",
        {
            "algorithm_profile": ("ssh-ed25519-sshsig-git-sha512-or-openpgp-v4-ed25519-sha256-v1"),
            "dependency_lock_path": "uv.lock",
            "dependency_lock_sha256": lock_sha256,
            "verifier_dependency_inventory_root": inventory_root,
            "entrypoint": "laconian_eval.benchmark.protocol_review:_verify_keyed_signature_v1",
            "verifier_source_path": "src/laconian_eval/benchmark/protocol_review.py",
            "verifier_source_sha256": source_sha256,
        },
    )
    payload: dict[str, object] = {
        "schema_version": "ProtocolReviewIdentityRegistryBundleV1",
        "keys": [key.model_dump(mode="json")],
        "verifier_source_path": "src/laconian_eval/benchmark/protocol_review.py",
        "verifier_source_sha256": source_sha256,
        "dependency_lock_path": "uv.lock",
        "dependency_lock_sha256": lock_sha256,
        "verifier_dependency_inventory_root": inventory_root,
        "protocol_signature_verifier_tool_sha256": tool,
    }
    payload["identity_registry_bundle_sha256"] = _digest(
        "laconian-protocol-review-identity-registry-bundle-v1", payload
    )
    bundle = ProtocolReviewIdentityRegistryBundleV1.model_validate(payload)
    assert bundle.keys == (key,)

    for invalid in ("", "eA", "eA===", "eA==\n", "-_=="):
        with pytest.raises(ValidationError):
            ProtocolReviewSigningKeyV1.model_validate(
                key.model_dump(mode="json") | {"public_key_base64": invalid}
            )
    with pytest.raises(ValidationError):
        ProtocolReviewSigningKeyV1.model_validate(
            key.model_dump(mode="json") | {"reviewer_numeric_account_id": True}
        )

    lock = (Path(__file__).resolve().parents[2] / "uv.lock").read_bytes()
    assert _read_exact_active_file("uv.lock", hashlib.sha256(lock).hexdigest()) == lock
    with pytest.raises(ValueError, match="differs from sealed C0"):
        _read_exact_active_file("uv.lock", "0" * 64)


def test_c0_lock_installed_crypto_inventory_and_loaded_module_identity_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    lock = (root / "uv.lock").read_bytes()
    assert hashlib.sha256(lock).hexdigest() == (
        "c49ecbb436fc583e877a1db9f7a7be35467c5743b2fe15936495c2834ff9a9d6"
    )
    inventory_root = protocol_review.compute_verifier_dependency_inventory_root(lock)
    _verify_installed_verifier_dependency_inventory(lock, inventory_root)
    identity = _identity_registry_bundle(_protocol_reviewer_registry())
    assert _verify_active_verifier_runtime(identity) == (
        (root / identity.verifier_source_path).read_bytes(),
        lock,
    )

    mutated = lock.replace(
        b'name = "cryptography"\nversion = "50.0.1"',
        b'name = "cryptography"\nversion = "50.0.0"',
        1,
    )
    assert mutated != lock
    with pytest.raises(ValueError, match=r"cryptography==50\.0\.1"):
        _verify_installed_verifier_dependency_inventory(mutated, inventory_root)
    mutated_dependency = lock.replace(
        b'{ name = "cffi", marker = "platform_python_implementation != \'PyPy\'" }',
        b'{ name = "pycparser", marker = "platform_python_implementation != \'PyPy\'" }',
        1,
    )
    assert mutated_dependency != lock
    with pytest.raises(ValueError, match="direct-dependency selection mismatch"):
        _verify_installed_verifier_dependency_inventory(mutated_dependency, inventory_root)

    real_distributions = protocol_review.importlib_metadata.distributions

    def wrong_distributions():
        return tuple(
            SimpleNamespace(
                metadata=distribution.metadata,
                version="50.0.0",
                requires=distribution.requires,
                files=distribution.files,
                locate_file=distribution.locate_file,
            )
            if distribution.metadata.get("Name") == "cryptography"
            else distribution
            for distribution in real_distributions()
        )

    with monkeypatch.context() as scoped:
        scoped.setattr(
            protocol_review.importlib_metadata,
            "distributions",
            wrong_distributions,
        )
        with pytest.raises(ValueError, match="identity/version mismatch"):
            _verify_installed_verifier_dependency_inventory(lock, inventory_root)

    module_name = "cryptography.hazmat.primitives.asymmetric.ed25519"
    with monkeypatch.context() as scoped:
        scoped.setitem(sys.modules, module_name, SimpleNamespace(__file__="/tmp/alternate.py"))
        with pytest.raises(ValueError, match="not an exact module"):
            _verify_installed_verifier_dependency_inventory(lock, inventory_root)


def test_installed_crypto_inventory_rejects_bogus_packagepath_hash_and_changed_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    lock = (root / "uv.lock").read_bytes()
    inventory_root = protocol_review.compute_verifier_dependency_inventory_root(lock)
    distribution = protocol_review.importlib_metadata.distribution("cryptography")
    target = next(
        Path(distribution.locate_file(str(item))).resolve()
        for item in distribution.files or ()
        if str(item).endswith("hazmat/primitives/asymmetric/ed25519.py")
    )
    target_relative = target.relative_to(Path(sys.prefix).resolve()).as_posix()
    original_reader = protocol_review._read_inventory_member_at

    def changed_installed_file(environment_descriptor: int, environment_relative: str):
        raw, member_stat = original_reader(environment_descriptor, environment_relative)
        if environment_relative == target_relative:
            raw = b"changed installed cryptography module"
        return raw, member_stat

    monkeypatch.setattr(protocol_review, "_read_inventory_member_at", changed_installed_file)
    with pytest.raises(ValueError, match="literal/canonical member route mismatch"):
        _verify_installed_verifier_dependency_inventory(lock, inventory_root)


def test_verified_source_finder_never_executes_timestamp_valid_malicious_pyc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_name = "pycparser"
    source_path = tmp_path / f"{module_name}.py"
    malicious = b"VALUE = 'malicious'\n"
    verified = b"VALUE = 'verified!'\n"
    assert len(malicious) == len(verified)
    source_path.write_bytes(malicious)
    source_stat = source_path.stat()
    py_compile.compile(str(source_path), doraise=True)
    source_path.write_bytes(verified)
    source_path.touch()
    os.utime(source_path, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
    finder = protocol_review._VerifiedSourceFinder(
        {source_path.resolve(): verified}, frozenset({source_path.resolve()})
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.meta_path.insert(0, finder)
    try:
        module = importlib.import_module(module_name)
        assert module.VALUE == "verified!"
        assert module.__cached__ is None
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop(module_name, None)


def test_source_only_import_restores_finder_and_new_modules_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_name = "cffi"
    source_path = tmp_path / f"{module_name}.py"
    source = b"VALUE = 'loaded'\n"
    source_path.write_bytes(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    environment_descriptor = os.open(
        tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    inventory = SimpleNamespace(
        root="probe-root",
        paths_by_distribution={
            "cryptography": frozenset({source_path.resolve()}),
            "cffi": frozenset(),
            "pycparser": frozenset(),
        },
        bytes_by_path={source_path.resolve(): source},
        distributions={"cryptography": object()},
        retained_anchors=((environment_descriptor, tmp_path, ()),),
    )

    def fail_after_import(*args: object, **kwargs: object) -> None:
        importlib.import_module(module_name)
        raise RuntimeError("probe failure")

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(protocol_review, "_VERIFIED_SELECTED_MODULE_SNAPSHOT", None)
            scoped.setattr(
                protocol_review, "_load_verified_ed25519_primitives", fail_after_import
            )
            for loaded_name in tuple(sys.modules):
                if protocol_review._is_verifier_governed_module(loaded_name):
                    scoped.delitem(sys.modules, loaded_name)
            before_finders = tuple(sys.meta_path)
            with pytest.raises(RuntimeError, match="probe failure"):
                protocol_review._source_only_selected_imports(inventory)
            assert tuple(sys.meta_path) == before_finders
            assert module_name not in sys.modules
    finally:
        os.close(environment_descriptor)


def test_inventory_rejects_hidden_unselected_distribution_record_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    lock = (root / "uv.lock").read_bytes()
    real_distributions = tuple(protocol_review.importlib_metadata.distributions())
    cryptography = next(
        item for item in real_distributions if item.metadata["Name"] == "cryptography"
    )
    claimed = next(
        str(item)
        for item in cryptography.files or ()
        if str(item).endswith("hazmat/primitives/asymmetric/ed25519.py")
    )
    hidden = SimpleNamespace(
        metadata={"Name": "hidden-record-claim"},
        files=(claimed,),
        locate_file=cryptography.locate_file,
    )
    monkeypatch.setattr(
        protocol_review.importlib_metadata,
        "distributions",
        lambda: (*real_distributions, hidden),
    )
    with pytest.raises(ValueError, match="ambiguous distribution RECORD claims"):
        protocol_review.compute_verifier_dependency_inventory_root(lock)


def test_inventory_claim_scan_matches_selected_member_by_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[2]
    lock = (root / "uv.lock").read_bytes()
    real_distributions = tuple(protocol_review.importlib_metadata.distributions())
    cryptography = next(
        item for item in real_distributions if item.metadata["Name"] == "cryptography"
    )
    selected = next(
        Path(str(cryptography.locate_file(str(item)))).resolve()
        for item in cryptography.files or ()
        if str(item).endswith("hazmat/primitives/asymmetric/ed25519.py")
    )
    alias = tmp_path / "case-variant-alias.py"
    alias.write_bytes(b"unrelated spelling")
    hidden = SimpleNamespace(
        metadata={"Name": "hidden-inode-claim"},
        files=("case-variant-alias.py",),
        locate_file=lambda value: alias,
    )
    real_stat = protocol_review.os.stat

    def same_inode_stat(path: object, *args: object, **kwargs: object):
        if isinstance(path, (str, Path)) and Path(path) == alias:
            return real_stat(selected, *args, **kwargs)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(
        protocol_review.importlib_metadata,
        "distributions",
        lambda: (*real_distributions, hidden),
    )
    monkeypatch.setattr(protocol_review.os, "stat", same_inode_stat)
    with pytest.raises(ValueError, match="ambiguous distribution RECORD claims"):
        protocol_review.compute_verifier_dependency_inventory_root(lock)


def test_inventory_fd_relative_walk_rejects_symlinked_intermediate_directory(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "member.py").write_bytes(b"verified")
    (tmp_path / "linked").symlink_to(real, target_is_directory=True)
    descriptor = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with pytest.raises(ValueError, match="missing, symlinked, or unreadable"):
            protocol_review._read_inventory_member_at(descriptor, "linked/member.py")
        with pytest.raises(ValueError, match="missing, symlinked, or unreadable"):
            protocol_review._read_inventory_member_at(
                descriptor, "linked/../real/member.py"
            )
    finally:
        os.close(descriptor)


def test_post_import_failure_never_publishes_trust_and_removes_only_exact_new_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact = ModuleType("cryptography.probe")
    replacement = ModuleType("cryptography.replacement")
    pending = protocol_review._PendingSelectedModuleTrust(
        snapshot={"cryptography.probe": (exact, "/verified/probe.py")},
        newly_added=(("cryptography.probe", exact), ("cryptography.keep", exact)),
    )
    before = SimpleNamespace(root="a" * 64, entries=(1,), retained_anchors=())
    after = SimpleNamespace(root="b" * 64, entries=(1,))
    builds = iter((before, after))
    monkeypatch.setattr(protocol_review, "_VERIFIED_SELECTED_MODULE_SNAPSHOT", None)
    monkeypatch.setattr(
        protocol_review,
        "_build_verifier_dependency_inventory",
        lambda *a, **k: next(builds),
    )
    monkeypatch.setattr(protocol_review, "_source_only_selected_imports", lambda inventory: pending)
    monkeypatch.setattr(
        protocol_review.importlib_metadata,
        "packages_distributions",
        lambda: {"cryptography": ["cryptography"]},
    )
    monkeypatch.setitem(sys.modules, "cryptography.probe", exact)
    monkeypatch.setitem(sys.modules, "cryptography.keep", replacement)
    with pytest.raises(ValueError, match="changed during verified import"):
        _verify_installed_verifier_dependency_inventory(b"lock", "a" * 64)
    assert (
        protocol_review._VERIFIED_SELECTED_MODULE_SNAPSHOT
        is protocol_review._POISONED_SELECTED_MODULE_TRUST
    )
    assert "cryptography.probe" not in sys.modules
    assert sys.modules["cryptography.keep"] is replacement


def test_anchor_failure_never_publishes_pending_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    original_source_imports = protocol_review._source_only_selected_imports
    pending = protocol_review._PendingSelectedModuleTrust(snapshot={}, newly_added=())
    inventory = SimpleNamespace(root="a" * 64, entries=(), retained_anchors=())
    monkeypatch.setattr(protocol_review, "_VERIFIED_SELECTED_MODULE_SNAPSHOT", None)
    monkeypatch.setattr(
        protocol_review,
        "_build_verifier_dependency_inventory",
        lambda *a, **k: inventory,
    )
    monkeypatch.setattr(protocol_review, "_source_only_selected_imports", lambda value: pending)
    monkeypatch.setattr(
        protocol_review.importlib_metadata,
        "packages_distributions",
        lambda: {"cryptography": ["cryptography"]},
    )
    monkeypatch.setattr(
        protocol_review,
        "_verify_and_close_inventory_anchors",
        lambda value: (_ for _ in ()).throw(ValueError("anchor replaced")),
    )
    with pytest.raises(ValueError, match="anchor replaced"):
        _verify_installed_verifier_dependency_inventory(b"lock", "a" * 64)
    assert (
        protocol_review._VERIFIED_SELECTED_MODULE_SNAPSHOT
        is protocol_review._POISONED_SELECTED_MODULE_TRUST
    )
    monkeypatch.setattr(
        protocol_review, "_source_only_selected_imports", original_source_imports
    )
    with pytest.raises(ValueError, match=r"poisoned.*restart required"):
        protocol_review._source_only_selected_imports(inventory)


@pytest.mark.parametrize("value", (object(), ModuleType("cryptography.utils")))
def test_governed_module_preload_outside_inventory_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    if isinstance(value, ModuleType):
        outside = tmp_path / "utils.py"
        outside.write_bytes(b"hostile")
        value.__file__ = str(outside)
        value.__spec__ = importlib.util.spec_from_file_location(value.__name__, outside)
    monkeypatch.setitem(sys.modules, "cryptography.utils", value)
    with pytest.raises(ValueError, match=r"not an exact module|outside verified inventory"):
        protocol_review._selected_loaded_module_snapshot(frozenset())


def test_verified_finder_is_terminal_for_selected_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension = tmp_path / f"_cffi_backend{importlib.machinery.EXTENSION_SUFFIXES[0]}"
    extension.write_bytes(b"verified extension fixture")
    expected = importlib.machinery.ModuleSpec(
        "_cffi_backend",
        loader=importlib.machinery.ExtensionFileLoader("_cffi_backend", str(extension)),
        origin=str(extension),
    )
    monkeypatch.setattr(
        importlib.machinery.PathFinder,
        "find_spec",
        lambda fullname, path=None, target=None: expected,
    )
    descriptor = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    verified_finder = protocol_review._VerifiedSourceFinder(
        {extension.resolve(): extension.read_bytes()},
        frozenset({extension.resolve()}),
        descriptor,
        tmp_path,
    )
    malicious_called = False

    class MaliciousFinder:
        def find_spec(self, *args: object, **kwargs: object) -> None:
            nonlocal malicious_called
            malicious_called = True
            return None

    try:
        selected = None
        for finder in (verified_finder, MaliciousFinder()):
            selected = finder.find_spec("_cffi_backend", None, None)
            if selected is not None:
                break
        assert selected is expected
        assert isinstance(selected.loader, protocol_review._VerifiedExtensionLoader)
        assert not malicious_called
    finally:
        os.close(descriptor)


def test_committed_module_trust_is_bound_to_inventory_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = tmp_path / "cryptography.py"
    origin.write_bytes(b"verified")
    module = ModuleType("cryptography")
    module.__file__ = str(origin)
    module.__spec__ = importlib.util.spec_from_file_location("cryptography", origin)
    snapshot = {"cryptography": (module, str(origin.resolve()))}
    monkeypatch.setitem(sys.modules, "cryptography", module)
    monkeypatch.setattr(
        protocol_review,
        "_VERIFIED_SELECTED_MODULE_SNAPSHOT",
        protocol_review._CommittedSelectedModuleTrust("a" * 64, snapshot),
    )
    inventory = SimpleNamespace(
        root="b" * 64,
        paths_by_distribution={"cryptography": frozenset({origin.resolve()})},
    )
    with pytest.raises(ValueError, match="root/module-object/origin trust changed"):
        protocol_review._source_only_selected_imports(inventory)


def test_verified_extension_loader_uses_unlinked_private_expected_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension = tmp_path / "extension.so"
    extension.write_bytes(b"verified")
    descriptor = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    native_bytes = b""
    native_path = ""

    class FakeNativeLoader:
        def __init__(self, name: str, path: str) -> None:
            nonlocal native_path
            self.path = path
            native_path = path

        def create_module(self, spec: object) -> None:
            nonlocal native_bytes
            native_bytes = Path(self.path).read_bytes()
            return None

        def exec_module(self, module: object) -> None:
            return None

    loader = protocol_review._VerifiedExtensionLoader(
        SimpleNamespace(path=str(extension)), descriptor, "extension.so", b"verified"
    )
    extension.write_bytes(b"tampered")
    try:
        monkeypatch.setattr(importlib.machinery, "ExtensionFileLoader", FakeNativeLoader)
        module = ModuleType("extension")
        module.__spec__ = importlib.machinery.ModuleSpec("extension", loader)
        loader.create_module(module.__spec__)
        assert native_bytes == b"verified"
        assert not Path(native_path).exists() or native_path.startswith(("/dev/fd/", "/proc/"))
        loader.exec_module(module)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("phase", ("write", "loader", "spec"))
def test_verified_extension_capture_failure_cleans_private_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    environment_descriptor = os.open(
        tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    original_mkdtemp = tempfile.mkdtemp
    monkeypatch.setattr(
        protocol_review.tempfile,
        "mkdtemp",
        lambda **kwargs: original_mkdtemp(dir=tmp_path, prefix="capture-"),
    )
    loader = protocol_review._VerifiedExtensionLoader(
        SimpleNamespace(path="verified-extension.so"),
        environment_descriptor,
        "unused.so",
        b"verified",
    )
    if phase == "write":
        monkeypatch.setattr(
            protocol_review.os,
            "write",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("write failed")),
        )
    elif phase == "loader":
        monkeypatch.setattr(
            importlib.machinery,
            "ExtensionFileLoader",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("loader failed")),
        )
    else:
        monkeypatch.setattr(importlib.util, "spec_from_loader", lambda *a, **k: None)
    try:
        with pytest.raises((OSError, ImportError)):
            loader._capture("verified_extension")
        assert not tuple(tmp_path.iterdir())
        assert loader._descriptor == -1
    finally:
        os.close(environment_descriptor)


def test_retained_anchor_rejects_path_replacement(tmp_path: Path) -> None:
    anchor = tmp_path / "anchor"
    anchor.mkdir()
    descriptor = os.open(anchor, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    identity = protocol_review._stat_identity(os.fstat(descriptor))
    anchor.rename(tmp_path / "old-anchor")
    anchor.mkdir()
    inventory = SimpleNamespace(retained_anchors=((descriptor, anchor, identity),))
    with pytest.raises(ValueError, match="retained directory anchor changed"):
        protocol_review._verify_and_close_inventory_anchors(inventory)


def test_retained_anchor_rejects_accepted_intermediate_symlink(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    anchor = parent / "anchor"
    anchor.mkdir(parents=True)
    descriptor = os.open(anchor, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    identity = protocol_review._stat_identity(os.fstat(descriptor))
    retained_path = anchor.resolve()
    relocated = tmp_path / "relocated-parent"
    parent.rename(relocated)
    parent.symlink_to(relocated, target_is_directory=True)
    inventory = SimpleNamespace(
        retained_anchors=((descriptor, retained_path, identity),)
    )
    with pytest.raises(ValueError, match=r"directory|anchor"):
        protocol_review._verify_and_close_inventory_anchors(inventory)


def test_standalone_inventory_root_requires_final_anchor_recheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    lock = (root / "uv.lock").read_bytes()
    monkeypatch.setattr(
        protocol_review,
        "_verify_inventory_anchors",
        lambda value: (_ for _ in ()).throw(ValueError("standalone anchor replaced")),
    )
    with pytest.raises(ValueError, match="standalone anchor replaced"):
        protocol_review.compute_verifier_dependency_inventory_root(lock)


def test_ambient_distribution_unresolvable_record_claim_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[2]
    lock = (root / "uv.lock").read_bytes()
    real_distributions = tuple(protocol_review.importlib_metadata.distributions())
    missing = tmp_path / "missing-claim.py"
    hidden = SimpleNamespace(
        metadata={"Name": "hidden-missing-claim"},
        files=("missing-claim.py",),
        locate_file=lambda value: missing,
    )
    monkeypatch.setattr(
        protocol_review.importlib_metadata,
        "distributions",
        lambda: (*real_distributions, hidden),
    )
    with pytest.raises(ValueError, match="ambient distribution RECORD claim is unresolvable"):
        protocol_review.compute_verifier_dependency_inventory_root(lock)


def test_provider_mapping_rejects_nonoverlapping_top_level_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    lock = (root / "uv.lock").read_bytes()
    inventory_root = protocol_review.compute_verifier_dependency_inventory_root(lock)
    monkeypatch.setattr(
        protocol_review,
        "_VERIFIED_SELECTED_MODULE_SNAPSHOT",
        protocol_review._VERIFIED_SELECTED_MODULE_SNAPSHOT,
    )
    monkeypatch.setattr(
        protocol_review.importlib_metadata,
        "packages_distributions",
        lambda: {"cryptography": ["cryptography", "hidden-provider"]},
    )
    with pytest.raises(ValueError, match="provider mapping mismatch"):
        _verify_installed_verifier_dependency_inventory(lock, inventory_root)


def test_protocol_review_import_does_not_eagerly_load_cryptography() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "assert not any(n == 'cryptography' or n.startswith('cryptography.') "
                "for n in sys.modules); "
                "import laconian_eval.benchmark.protocol_review; "
                "assert not any(n == 'cryptography' or n.startswith('cryptography.') "
                "for n in sys.modules)"
            ),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_preimported_python_ed25519_lookalike_cannot_verify() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib
import sys
from types import ModuleType

module_name = "cryptography.hazmat.primitives.asymmetric.ed25519"
real_module = importlib.import_module(module_name)

class AcceptingVerifier:
    def verify(self, signature, message):
        return None

class Ed25519PublicKey:
    @classmethod
    def from_public_bytes(cls, public_key):
        return AcceptingVerifier()

Ed25519PublicKey.__module__ = module_name
fake_module = ModuleType(module_name)
fake_module.__file__ = real_module.__file__
fake_module.__spec__ = real_module.__spec__
fake_module.Ed25519PublicKey = Ed25519PublicKey
sys.modules[module_name] = fake_module

from laconian_eval.benchmark.protocol_review import _verify_ed25519

try:
    _verify_ed25519(
        bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"),
        bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
        ),
        b"",
    )
except ValueError:
    raise SystemExit(0)
raise SystemExit("preimported Python Ed25519 lookalike was accepted")
""",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_signature_evidence_source_requires_exact_bounded_two_byte_tuples() -> None:
    with pytest.raises((TypeError, ValueError)):
        ProtocolSignatureEvidenceSourceV1(
            observation_receipt=cast(object, object()),
            signature_evidence=cast(object, object()),
            raw_response_bytes=(b"{}", b"{}"),
            canonical_response_bytes=(b"{}", b"{}"),
        )


def test_ssh_keyed_verifier_pins_exact_sshsig_profile_and_cryptography() -> None:
    _verify_ed25519(
        bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"),
        bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
        ),
        b"",
    )
    registry = _protocol_reviewer_registry()
    identity = _identity_registry_bundle(registry)
    seed, key_blob, _ = _security_key_material()
    payload = b"tree " + b"0" * 40 + b"\n\nreview\n"
    signature = _ssh_signature(seed, key_blob, payload)
    receipt = _verify_keyed_signature_v1(
        key=identity.keys[0],
        signed_payload=payload,
        signature=signature,
        verifier_tool_sha256=identity.protocol_signature_verifier_tool_sha256,
        author_name_ascii="Security Reviewer",
        author_email_ascii="security-reviewer@example.com",
        signed_at="2026-08-31T00:00:00Z",
    )
    assert receipt.signed_payload_sha256 == hashlib.sha256(payload).hexdigest()
    assert receipt.signature_sha256 == hashlib.sha256(signature).hexdigest()

    audit_seed, audit_key_blob, _ = audit_reviewer_ssh_key_material()
    audit_signature = _ssh_signature(audit_seed, audit_key_blob, payload)
    audit_key = audit_reviewer_signing_key()
    audit_receipt = _verify_keyed_signature_v1(
        key=audit_key,
        signed_payload=payload,
        signature=audit_signature,
        verifier_tool_sha256=identity.protocol_signature_verifier_tool_sha256,
        author_name_ascii=audit_key.author_name_ascii,
        author_email_ascii=audit_key.author_email_ascii,
        signed_at="2026-08-31T00:00:00Z",
    )
    assert audit_receipt.signed_payload_sha256 == hashlib.sha256(payload).hexdigest()
    assert audit_receipt.signature_sha256 == hashlib.sha256(audit_signature).hexdigest()

    with pytest.raises(ValueError, match="verification failed"):
        _verify_keyed_signature_v1(
            key=identity.keys[0],
            signed_payload=payload + b"tampered",
            signature=signature,
            verifier_tool_sha256=identity.protocol_signature_verifier_tool_sha256,
            author_name_ascii="Security Reviewer",
            author_email_ascii="security-reviewer@example.com",
            signed_at="2026-08-31T00:00:00Z",
        )
    with pytest.raises(ValueError, match="terminal LF"):
        _verify_keyed_signature_v1(
            key=identity.keys[0],
            signed_payload=payload,
            signature=signature.rstrip(b"\n"),
            verifier_tool_sha256=identity.protocol_signature_verifier_tool_sha256,
            author_name_ascii="Security Reviewer",
            author_email_ascii="security-reviewer@example.com",
            signed_at="2026-08-31T00:00:00Z",
        )


@pytest.mark.parametrize("use_subkey", [False, True])
def test_openpgp_keyed_verifier_accepts_exact_certification_binding_and_detached_types(
    use_subkey: bool,
) -> None:
    fixture = _openpgp_fixture(use_subkey=use_subkey)
    key = ProtocolReviewSigningKeyV1(
        role="security_evidence",
        reviewer_numeric_account_id=303,
        reviewer_login="openpgp-reviewer",
        verification_mode="openpgp_fingerprint",
        fingerprint=fixture.primary_fingerprint,
        public_key_encoding="openpgp-v4-ed25519-transferable-public-key-v1",
        public_key_base64=base64.b64encode(fixture.key_bytes).decode("ascii"),
        public_key_sha256=hashlib.sha256(fixture.key_bytes).hexdigest(),
    )
    receipt = _verify_keyed_signature_v1(
        key=key,
        signed_payload=fixture.payload,
        signature=fixture.signature,
        verifier_tool_sha256="a" * 64,
        author_name_ascii="OpenPGP Review Author",
        author_email_ascii="openpgp-review@example.com",
        signed_at=fixture.signed_at,
    )
    assert receipt.verified is True
    assert receipt.signature_sha256 == hashlib.sha256(fixture.signature).hexdigest()
    with pytest.raises(ValueError, match="verification failed"):
        _verify_keyed_signature_v1(
            key=key,
            signed_payload=fixture.payload,
            signature=_openpgp_signature_for_payload(
                fixture,
                fixture.payload,
                signing_seed=hashlib.sha256(b"wrong-openpgp-signing-seed").digest(),
            ),
            verifier_tool_sha256="a" * 64,
            author_name_ascii="OpenPGP Review Author",
            author_email_ascii="openpgp-review@example.com",
            signed_at=fixture.signed_at,
        )


@pytest.mark.parametrize(
    ("fixture", "match"),
    (
        (_openpgp_fixture(use_subkey=True, include_embedded=False), "embedded.*0x19"),
        (_openpgp_fixture(use_subkey=False, detached_type=0x13), "detached.*0x00"),
        (
            _openpgp_fixture(use_subkey=False, detached_unknown_critical=True),
            "unknown critical",
        ),
        (_openpgp_fixture(use_subkey=False, detached_key_id_only=True), "issuer-fingerprint"),
        (_openpgp_fixture(use_subkey=False, primary_key_expiration=1), "primary key is expired"),
    ),
)
def test_openpgp_keyed_verifier_rejects_wrong_packet_roles_and_unknown_critical_subpacket(
    fixture: SimpleNamespace,
    match: str,
) -> None:
    key = ProtocolReviewSigningKeyV1(
        role="security_evidence",
        reviewer_numeric_account_id=303,
        reviewer_login="openpgp-reviewer",
        verification_mode="openpgp_fingerprint",
        fingerprint=fixture.primary_fingerprint,
        public_key_encoding="openpgp-v4-ed25519-transferable-public-key-v1",
        public_key_base64=base64.b64encode(fixture.key_bytes).decode("ascii"),
        public_key_sha256=hashlib.sha256(fixture.key_bytes).hexdigest(),
    )
    with pytest.raises(ValueError, match=match):
        _verify_keyed_signature_v1(
            key=key,
            signed_payload=fixture.payload,
            signature=fixture.signature,
            verifier_tool_sha256="a" * 64,
            author_name_ascii="OpenPGP Review Author",
            author_email_ascii="openpgp-review@example.com",
            signed_at=fixture.signed_at,
        )


@pytest.mark.parametrize(
    ("signature_type", "kwargs", "match"),
    (
        (0x00, {"key_flags": 0x02}, "key-flags.*forbidden"),
        (0x00, {"key_expiration": 1}, "key-expiration.*forbidden"),
        (0x00, {"embedded_signature": b"x"}, "embedded.*role mismatch"),
        (0x19, {"key_flags": 0x02}, "key-flags.*forbidden"),
        (0x19, {"key_expiration": 1}, "key-expiration.*forbidden"),
        (0x13, {"key_flags": 0x03, "embedded_signature": b"x"}, "embedded.*role mismatch"),
    ),
)
def test_openpgp_signature_security_subpackets_are_role_specific(
    signature_type: int, kwargs: dict[str, object], match: str
) -> None:
    seed = hashlib.sha256(b"openpgp-role-policy").digest()
    _, _, fingerprint = _openpgp_key_body(seed, 1_788_048_000)
    body = _openpgp_signature_body(
        signature_type=signature_type,
        seed=seed,
        issuer_fingerprint=fingerprint,
        signed_data=b"role policy",
        created_at=1_788_048_000,
        **kwargs,
    )
    with pytest.raises(ValueError, match=match):
        protocol_review._parse_openpgp_signature(
            body,
            expected_type=signature_type,
            label="role-policy",
            require_key_flags=signature_type in {0x13, 0x18},
        )


def test_openpgp_rejects_primary_subkey_body_collision() -> None:
    fixture = _openpgp_fixture(use_subkey=True)
    packets = protocol_review._parse_openpgp_packets(fixture.key_bytes)
    collided = b"".join(
        _openpgp_packet(packet.tag, packets[0].body if index == 3 else packet.body)
        for index, packet in enumerate(packets)
    )
    with pytest.raises(ValueError, match="key material must be globally unique"):
        protocol_review._verify_openpgp_signature_profile(
            collided,
            fixture.signature,
            fixture.payload,
            author_name_ascii="OpenPGP Review Author",
            author_email_ascii="openpgp-review@example.com",
            signed_at=fixture.signed_at,
        )


def test_github_only_signature_requires_exact_single_openpgp_armor_packet() -> None:
    valid = _github_signature()
    _validate_github_signature_armor(valid)
    incomplete_v4_signature = _armor(
        b"\xc2\x02\x04\x00",
        b"-----BEGIN PGP SIGNATURE-----",
        b"-----END PGP SIGNATURE-----",
        64,
        pgp=True,
    )
    with pytest.raises(ValueError, match="truncated"):
        _validate_github_signature_armor(incomplete_v4_signature)
    eddsa_with_one_mpi = _armor(
        bytes.fromhex("c20d04001608000000000000000101"),
        b"-----BEGIN PGP SIGNATURE-----",
        b"-----END PGP SIGNATURE-----",
        64,
        pgp=True,
    )
    with pytest.raises(ValueError, match="requires exactly 2 MPIs"):
        _validate_github_signature_armor(eddsa_with_one_mpi)
    crc_line = next(line for line in valid.splitlines() if line.startswith(b"="))
    bad_first_character = b"A" if crc_line[1:2] != b"A" else b"B"
    bad_crc = valid.replace(crc_line, b"=" + bad_first_character + crc_line[2:], 1)
    with pytest.raises(ValueError, match="CRC-24 mismatch"):
        _validate_github_signature_armor(bad_crc)
    with pytest.raises(ValueError, match="terminal LF"):
        _validate_github_signature_armor(valid.rstrip(b"\n"))
    two_packets = _armor(
        b"\xc2\x02\x04\x00\xc2\x02\x04\x00",
        b"-----BEGIN PGP SIGNATURE-----",
        b"-----END PGP SIGNATURE-----",
        64,
        pgp=True,
    )
    with pytest.raises(ValueError, match="exactly one"):
        _validate_github_signature_armor(two_packets)


def test_archived_raw_api_bodies_reject_secret_bearing_metadata() -> None:
    _validate_safe_raw_body(b'{"data":{"ok":true}}')
    _validate_safe_raw_body(
        b'{"data":{"ignored_decimal":1.5,"ignored_exponent":6.02e23}}'
    )
    for raw in (
        b'{"headers":{"authorization":"Bearer secret"}}',
        b'{"cookie":"session=secret"}',
        b'{"query_string":"access_token=secret"}',
    ):
        with pytest.raises(ValueError, match="secret-bearing"):
            _validate_safe_raw_body(raw)


def test_object_archive_rejects_missing_required_receipt_composition() -> None:
    raw = b"archive object\n"
    wire = b"blob " + str(len(raw)).encode() + b"\0" + raw
    oid = hashlib.sha1(wire).hexdigest()
    git_sha256 = hashlib.sha256(wire).hexdigest()
    objects = [
        {
            "oid": oid,
            "type": "blob",
            "size": len(raw),
            "git_object_sha256": git_sha256,
            "raw_content_base64": base64.b64encode(raw).decode("ascii"),
        }
    ]
    closure = _digest(
        "laconian-protocol-review-object-closure-v1",
        [{"oid": oid, "type": "blob", "size": len(raw), "git_object_sha256": git_sha256}],
    )
    payload: dict[str, object] = {
        "schema_version": "ProtocolReviewObjectArchiveV1",
        "object_closure_root": closure,
        "objects": objects,
        "api_blobs": [],
        "api_receipts": [],
    }
    payload["protocol_review_object_archive_sha256"] = _digest(
        "laconian-protocol-review-object-archive-v1", payload
    )
    with pytest.raises(ValidationError):
        ProtocolReviewObjectArchiveV1.model_validate(payload)


def _git_object(store: dict[str, object], object_type: str, raw_content: bytes):
    wire = object_type.encode("ascii") + b" " + str(len(raw_content)).encode() + b"\0" + raw_content
    oid = hashlib.sha1(wire).hexdigest()
    parsed = parse_protocol_git_object(
        oid=oid,
        object_type=cast(object, object_type),
        raw_content=raw_content,
    )
    store.setdefault(parsed.oid, parsed)
    return parsed


def _tree_for_files(store: dict[str, object], files: dict[str, bytes]):
    root: dict[str, object] = {}
    for path, content in files.items():
        node = root
        parts = path.split("/")
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            assert isinstance(child, dict)
            node = child
        node[parts[-1]] = content

    def build(node: dict[str, object]):
        entries: list[tuple[str, bytes, str]] = []
        items = sorted(
            node.items(),
            key=lambda item: item[0].encode() + (b"/" if isinstance(item[1], dict) else b""),
        )
        for name, value in items:
            if isinstance(value, dict):
                child = build(value)
                entries.append(("40000", name.encode(), child.oid))
            else:
                assert isinstance(value, bytes)
                child = _git_object(store, "blob", value)
                entries.append(("100644", name.encode(), child.oid))
        raw = b"".join(
            mode.encode() + b" " + name + b"\0" + bytes.fromhex(oid) for mode, name, oid in entries
        )
        return _git_object(store, "tree", raw)

    return build(root)


def _builder_identity() -> ProtocolBundleBuilderGitIdentityV1:
    payload: dict[str, object] = {
        "schema_version": "ProtocolBundleBuilderGitIdentityV1",
        "name_ascii": "Laconian Protocol Bundle Builder",
        "email_ascii": "laconian-protocol-bundle-builder@users.noreply.github.com",
    }
    payload["protocol_bundle_builder_git_identity_sha256"] = _digest(
        "laconian-protocol-bundle-builder-git-identity-v1", payload
    )
    return ProtocolBundleBuilderGitIdentityV1.model_validate(payload)


def _security_key_material() -> tuple[bytes, bytes, str]:
    seed = hashlib.sha256(b"laconian-test-security-reviewer-ed25519").digest()
    public_key, _ = _test_ed_key(seed)
    key_blob = _ssh_string(b"ssh-ed25519") + _ssh_string(public_key)
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key_blob).digest()).decode(
        "ascii"
    ).rstrip("=")
    return seed, key_blob, fingerprint


def _protocol_reviewer_registry(
    security_mode: str = "ssh_sha256",
) -> ProtocolReviewerRegistryV1:
    if security_mode == "ssh_sha256":
        _, _, security_fingerprint = _security_key_material()
    else:
        assert security_mode == "openpgp_fingerprint"
        security_fingerprint = _openpgp_fixture(use_subkey=True).primary_fingerprint
    reviewers = tuple(
        ProtocolReviewerBindingV1(
            role=role,
            reviewer_numeric_account_id=201 + ordinal,
            reviewer_login=f"reviewer-{ordinal + 1}",
            verification_mode=(
                security_mode if role == "security_evidence" else "github_verified_commit"
            ),
            signing_fingerprint=(security_fingerprint if role == "security_evidence" else None),
            author_name_ascii=(
                "OpenPGP Review Author"
                if role == "security_evidence" and security_mode == "openpgp_fingerprint"
                else f"Review Author {ordinal + 1}"
            ),
            author_email_ascii=(
                "openpgp-review@example.com"
                if role == "security_evidence" and security_mode == "openpgp_fingerprint"
                else f"review-author-{ordinal + 1}@example.com"
            ),
            committer_name_ascii=f"Review Committer {ordinal + 1}",
            committer_email_ascii=f"review-committer-{ordinal + 1}@example.com",
        )
        for ordinal, role in enumerate(
            cast(
                tuple[ProtocolReviewRoleV1, ...],
                (
                    "statistical_method",
                    "blind_judge_audit_protocol",
                    "security_evidence",
                ),
            )
        )
    )
    exact = cast(
        tuple[ProtocolReviewerBindingV1, ProtocolReviewerBindingV1, ProtocolReviewerBindingV1],
        reviewers,
    )
    return ProtocolReviewerRegistryV1(
        schema_version="benchmark-protocol-reviewer-registry-v1",
        reviewers=exact,
        protocol_reviewer_registry_sha256=compute_protocol_reviewer_registry_sha256(exact),
    )


def _identity_registry_bundle(
    registry: ProtocolReviewerRegistryV1,
    *,
    inventory_root: str | None = None,
) -> ProtocolReviewIdentityRegistryBundleV1:
    reviewer = registry.reviewers[2]
    if reviewer.verification_mode == "ssh_sha256":
        _, key_blob, fingerprint = _security_key_material()
        public_key_encoding = "openssh-ed25519-wire-v1"
    else:
        openpgp = _openpgp_fixture(use_subkey=True)
        key_blob = openpgp.key_bytes
        fingerprint = openpgp.primary_fingerprint
        public_key_encoding = "openpgp-v4-ed25519-transferable-public-key-v1"
    root = Path(__file__).resolve().parents[2]
    source_path = "src/laconian_eval/benchmark/protocol_review.py"
    lock_path = "uv.lock"
    source_sha256 = hashlib.sha256((root / source_path).read_bytes()).hexdigest()
    lock_sha256 = hashlib.sha256((root / lock_path).read_bytes()).hexdigest()
    if inventory_root is None:
        inventory_root = protocol_review.compute_verifier_dependency_inventory_root(
            (root / lock_path).read_bytes()
        )
    key = ProtocolReviewSigningKeyV1(
        role=reviewer.role,
        reviewer_numeric_account_id=reviewer.reviewer_numeric_account_id,
        reviewer_login=reviewer.reviewer_login,
        verification_mode=reviewer.verification_mode,
        fingerprint=fingerprint,
        public_key_encoding=public_key_encoding,
        public_key_base64=base64.b64encode(key_blob).decode("ascii"),
        public_key_sha256=hashlib.sha256(key_blob).hexdigest(),
    )
    tool = _digest(
        "laconian-protocol-signature-verifier-tool-v1",
        {
            "algorithm_profile": ("ssh-ed25519-sshsig-git-sha512-or-openpgp-v4-ed25519-sha256-v1"),
            "dependency_lock_path": lock_path,
            "dependency_lock_sha256": lock_sha256,
            "verifier_dependency_inventory_root": inventory_root,
            "entrypoint": "laconian_eval.benchmark.protocol_review:_verify_keyed_signature_v1",
            "verifier_source_path": source_path,
            "verifier_source_sha256": source_sha256,
        },
    )
    payload: dict[str, object] = {
        "schema_version": "ProtocolReviewIdentityRegistryBundleV1",
        "keys": [key.model_dump(mode="json")],
        "verifier_source_path": source_path,
        "verifier_source_sha256": source_sha256,
        "dependency_lock_path": lock_path,
        "dependency_lock_sha256": lock_sha256,
        "verifier_dependency_inventory_root": inventory_root,
        "protocol_signature_verifier_tool_sha256": tool,
    }
    payload["identity_registry_bundle_sha256"] = _digest(
        "laconian-protocol-review-identity-registry-bundle-v1", payload
    )
    return ProtocolReviewIdentityRegistryBundleV1.model_validate(payload)


def _review_statement(
    *,
    reviewer: ProtocolReviewerBindingV1,
    registry: ProtocolReviewerRegistryV1,
    input_tag,
    c0,
    workflow_root: str,
    identity_registry_sha256: str,
) -> ProtocolReviewStatementV1:
    subjects = [
        {
            "kind": kind,
            "sha256": (
                _operator_registry().tag_operator_registry_sha256
                if kind == "tag_operator_registry_sha256"
                else _ruleset_policy().tag_ruleset_policy_root
                if kind == "tag_ruleset_policy_root"
                else identity_registry_sha256
                if kind == "identity_registry_bundle_sha256"
                else hashlib.sha256(f"{reviewer.role}:{kind}".encode()).hexdigest()
            ),
        }
        for kind in PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1[reviewer.role]
    ]
    payload: dict[str, object] = {
        "schema_version": "ProtocolReviewStatementV1",
        "role": reviewer.role,
        "protocol_registry_sha256": registry.protocol_reviewer_registry_sha256,
        "reviewer_numeric_account_id": reviewer.reviewer_numeric_account_id,
        "reviewer_login": reviewer.reviewer_login,
        "verification_mode": reviewer.verification_mode,
        "signing_fingerprint": reviewer.signing_fingerprint,
        "input_tag_ref": "refs/tags/benchmark-input-20260831.1",
        "input_tag_oid": input_tag.oid,
        "input_tag_object_sha256": input_tag.git_object_sha256,
        "peeled_c0_oid": c0.oid,
        "peeled_c0_sha256": c0.git_object_sha256,
        "workflow_root": workflow_root,
        "subjects": subjects,
        "subject_root": _digest("laconian-protocol-review-subjects-root-v1", subjects),
        "signed_at": "2026-08-31T00:00:00Z",
    }
    payload["statement_sha256"] = _digest("laconian-protocol-review-statement-v1", payload)
    return ProtocolReviewStatementV1.model_validate(payload)


def _review_commit(
    store: dict[str, object],
    *,
    tree_oid: str,
    parent_oid: str,
    reviewer: ProtocolReviewerBindingV1,
    statement: ProtocolReviewStatementV1,
):
    author = (
        f"{reviewer.author_name_ascii} <{reviewer.author_email_ascii}> 1788134400 +0000"
    ).encode()
    committer = (
        f"{reviewer.committer_name_ascii} <{reviewer.committer_email_ascii}> 1788134400 +0000"
    ).encode()
    core_headers = (
        b"tree " + tree_oid.encode() + b"\n"
        b"parent " + parent_oid.encode() + b"\n"
        b"author " + author + b"\n"
        b"committer " + committer
    )
    message = (
        f"laconian protocol review benchmark-input-20260831.1 {reviewer.role}: "
        f"{statement.statement_sha256}\n"
    ).encode()
    signed_payload = core_headers + b"\n\n" + message
    if reviewer.verification_mode == "ssh_sha256":
        seed, key_blob, _ = _security_key_material()
        signature = _ssh_signature(seed, key_blob, signed_payload)
    elif reviewer.verification_mode == "openpgp_fingerprint":
        signature = _openpgp_signature_for_payload(
            _openpgp_fixture(use_subkey=True), signed_payload
        )
    else:
        signature = _github_signature()
    signature_header = b"\ngpgsig " + signature.replace(b"\n", b"\n ")
    raw = core_headers + signature_header + b"\n\n" + message
    commit = _git_object(store, "commit", raw)
    return commit, signed_payload, signature


def _signature_observation(
    *,
    commit,
    reviewer: ProtocolReviewerBindingV1,
    signed_payload: bytes,
    signature: bytes,
    ordinal: int,
    identity_registry: ProtocolReviewIdentityRegistryBundleV1,
):
    rest_payload: dict[str, object] = {
        "schema_version": "GitHubCommitVerificationProjectionV1",
        "repository_id": 123,
        "commit_oid": commit.oid,
        "api_version": "2022-11-28",
        "endpoint": f"GET /repos/acme/repo/git/commits/{commit.oid}",
        "verified": True,
        "reason": "valid",
        "payload": signed_payload.decode(),
        "signature": signature.decode(),
        "verified_at": "2026-08-31T00:00:00.000000Z",
    }
    rest_payload["rest_projection_sha256"] = _digest(
        "laconian-github-commit-verification-projection-v1", rest_payload
    )
    rest = GitHubCommitVerificationProjectionV1.model_validate(rest_payload)
    graphql_payload: dict[str, object] = {
        "schema_version": "GitHubSignatureProjectionV1",
        "repository_id": 123,
        "commit_oid": commit.oid,
        "query_sha256": GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
        "signer_database_id": reviewer.reviewer_numeric_account_id,
        "signer_login": reviewer.reviewer_login,
        "is_valid": True,
        "state": "VALID",
    }
    graphql_payload["graphql_projection_sha256"] = _digest(
        "laconian-github-signature-projection-v1", graphql_payload
    )
    graphql = GitHubSignatureProjectionV1.model_validate(graphql_payload)
    raw_rest = canonical_json_v1(
        {
            "sha": commit.oid,
            "verification": {
                "verified": True,
                "reason": "valid",
                "payload": signed_payload.decode(),
                "signature": signature.decode(),
                "verified_at": "2026-08-31T03:00:00+03:00",
                "ignored_provider_field": ordinal,
            },
            "ignored_top_level": "not-stable",
        }
    )
    raw_graphql = canonical_json_v1(
        {
            "data": {
                "repository": {
                    "databaseId": 123,
                    "object": {
                        "oid": commit.oid,
                        "signature": {
                            "isValid": True,
                            "state": "VALID",
                            "signer": {
                                "databaseId": reviewer.reviewer_numeric_account_id,
                                "login": reviewer.reviewer_login,
                                "ignored": ordinal,
                            },
                        },
                    },
                }
            },
            "extensions": {"ignored": True},
        }
    )
    canonical_rest = canonical_json_v1(rest.model_dump(mode="json"))
    canonical_graphql = canonical_json_v1(graphql.model_dump(mode="json"))
    payload: dict[str, object] = {
        "schema_version": "GitHubSignatureObservationReceiptV1",
        "repository_id": 123,
        "commit_oid": commit.oid,
        "rest_projection_sha256": rest.rest_projection_sha256,
        "graphql_projection_sha256": graphql.graphql_projection_sha256,
        "observed_at": "2026-08-31T00:00:00.000000Z",
        "request_ids": (f"rest-{ordinal}", f"graphql-{ordinal}"),
        "etags": (f'"rest-{ordinal}"', f'"graphql-{ordinal}"'),
        "raw_response_sha256s": (
            hashlib.sha256(raw_rest).hexdigest(),
            hashlib.sha256(raw_graphql).hexdigest(),
        ),
        "canonical_response_sha256s": (
            hashlib.sha256(canonical_rest).hexdigest(),
            hashlib.sha256(canonical_graphql).hexdigest(),
        ),
        "tls_endpoint_identity": "api.github.com:443",
    }
    payload["github_signature_observation_receipt_sha256"] = _digest(
        "laconian-github-signature-observation-receipt-v1", payload
    )
    receipt = GitHubSignatureObservationReceiptV1.model_validate(payload)
    common: dict[str, object] = {
        "commit_oid": commit.oid,
        "commit_object_sha256": commit.git_object_sha256,
        "parent_commit_oid": cast(
            str, signed_payload.split(b"\nparent ", 1)[1].split(b"\n", 1)[0].decode()
        ),
        "statement_path": (
            "benchmarks/protocol-reviews/benchmark-input-20260831.1/statements/"
            + {
                "statistical_method": "01-statistical-method.json",
                "blind_judge_audit_protocol": "02-blind-judge-audit-protocol.json",
                "security_evidence": "03-security-evidence.json",
            }[reviewer.role]
        ),
        "github_rest_verification": rest.model_dump(mode="json"),
        "github_graphql_signature": graphql.model_dump(mode="json"),
    }
    if reviewer.verification_mode == "github_verified_commit":
        evidence = GitHubVerifiedCommitEvidenceV1.model_validate(
            {
                "schema_version": "GitHubVerifiedCommitEvidenceV1",
                "verification_mode": "github_verified_commit",
                **common,
            }
        )
    else:
        key = identity_registry.keys[0]
        local_payload: dict[str, object] = {
            "verified": True,
            "signed_payload_sha256": hashlib.sha256(signed_payload).hexdigest(),
            "signature_sha256": hashlib.sha256(signature).hexdigest(),
            "verifier_tool_sha256": identity_registry.protocol_signature_verifier_tool_sha256,
        }
        local_payload["verification_receipt_sha256"] = _digest(
            "laconian-local-signature-verification-receipt-v1", local_payload
        )
        local = LocalSignatureVerificationReceiptV1.model_validate(local_payload)
        keyed = {
            **common,
            "fingerprint": key.fingerprint,
            "keyring_sha256": key.public_key_sha256,
            "local_signature_verification": local.model_dump(mode="json"),
        }
        if reviewer.verification_mode == "ssh_sha256":
            evidence = SSHVerifiedCommitEvidenceV1.model_validate(
                {
                    "schema_version": "SSHVerifiedCommitEvidenceV1",
                    "verification_mode": "ssh_sha256",
                    **keyed,
                }
            )
        else:
            evidence = OpenPGPVerifiedCommitEvidenceV1.model_validate(
                {
                    "schema_version": "OpenPGPVerifiedCommitEvidenceV1",
                    "verification_mode": "openpgp_fingerprint",
                    **keyed,
                }
            )
    source = ProtocolSignatureEvidenceSourceV1(
        observation_receipt=receipt,
        signature_evidence=evidence,
        raw_response_bytes=(raw_rest, raw_graphql),
        canonical_response_bytes=(canonical_rest, canonical_graphql),
    )
    return SimpleNamespace(
        receipt=receipt,
        source=source,
        evidence=evidence,
        raw=(raw_rest, raw_graphql),
        canonical=(canonical_rest, canonical_graphql),
    )


def _creation_suite(ref: str, after_oid: str, suite_id: int):
    projection: dict[str, object] = {
        "repository_id": 123,
        "rule_suite_id": suite_id,
        "operation": "create",
        "ref": ref,
        "before_sha": "0" * 40,
        "after_sha": after_oid,
        "actor_account_id": 101,
        "actor_login": "tag-operator",
        "pushed_at": "2026-08-31T00:00:01.000000Z",
        "overall_result": "bypass",
        "evaluation_result": "fail",
        "rule_evaluations": [
            {
                "rule_source_type": "ruleset",
                "rule_source_id": 11,
                "enforcement": "active",
                "result": "fail",
                "rule_type": "creation",
            }
        ],
        "creation_authorizer_ruleset_id": 11,
        "creation_bypass_grant": {
            "actor_id": 101,
            "actor_login": "tag-operator",
            "source_ruleset_id": 11,
            "tag_ruleset_policy_root": _ruleset_policy().tag_ruleset_policy_root,
        },
        "tag_ruleset_policy_root": _ruleset_policy().tag_ruleset_policy_root,
    }
    raw = canonical_json_v1(
        {
            "id": suite_id,
            "repository_id": 123,
            "ref": ref,
            "before_sha": "0" * 40,
            "after_sha": after_oid,
            "actor_id": 101,
            "actor_name": "tag-operator",
            "pushed_at": "2026-08-31T00:00:01Z",
            "result": "bypass",
            "evaluation_result": "fail",
            "rule_evaluations": [
                {
                    "rule_source": {
                        "type": "ruleset",
                        "id": 11,
                        "name": "benchmark-tag-creation-authorizer",
                    },
                    "enforcement": "active",
                    "result": "fail",
                    "rule_type": "creation",
                    "details": {"ignored": f"suite-{suite_id}"},
                }
            ],
            "ignored_transport_field": f"suite-{suite_id}",
        }
    )
    canonical = canonical_json_v1(projection)
    payload: dict[str, object] = {
        "schema_version": "TagCreationRuleSuiteReceiptV1",
        "repository_id": 123,
        "rule_suite_id": suite_id,
        "operation": "create",
        "ref": ref,
        "before_sha": "0" * 40,
        "after_sha": after_oid,
        "actor_account_id": 101,
        "actor_login": "tag-operator",
        "pushed_at": "2026-08-31T00:00:01.000000Z",
        "overall_result": "bypass",
        "evaluation_result": "fail",
        "rule_evaluations": (
            {
                "rule_source_type": "ruleset",
                "rule_source_id": 11,
                "enforcement": "active",
                "result": "fail",
                "rule_type": "creation",
            },
        ),
        "creation_authorizer_ruleset_id": 11,
        "creation_bypass_grant": {
            "actor_id": 101,
            "actor_login": "tag-operator",
            "source_ruleset_id": 11,
            "tag_ruleset_policy_root": _ruleset_policy().tag_ruleset_policy_root,
        },
        "tag_ruleset_policy_root": _ruleset_policy().tag_ruleset_policy_root,
        "request_ids": (f"suite-{suite_id}",),
        "api_version": "2022-11-28",
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_response_sha256": hashlib.sha256(canonical).hexdigest(),
        "observed_at": "2026-08-31T00:00:02.000000Z",
    }
    payload["tag_creation_rule_suite_receipt_sha256"] = _digest(
        "laconian-tag-creation-rule-suite-receipt-v1", payload
    )
    return SimpleNamespace(
        receipt=TagCreationRuleSuiteReceiptV1.model_validate(payload),
        raw=(raw,),
        canonical=(canonical,),
    )


def _ruleset_observation():
    policy = _ruleset_policy()
    list_raw = canonical_json_v1(
        [
            {"id": 12, "name": "ignored immutability"},
            {"id": 11, "name": "ignored creation"},
        ]
    )
    by_id = {item.ruleset_id: item for item in policy.rulesets}
    detail_raw = tuple(
        canonical_json_v1(
            {
                "id": ruleset_id,
                "name": "ignored",
                "source_type": "Repository",
                "source": "acme/repo",
                "target": "tag",
                "enforcement": projection.enforcement,
                "conditions": {
                    "ref_name": {
                        "include": list(projection.include_patterns),
                        "exclude": list(projection.exclude_patterns),
                    }
                },
                "rules": [item.model_dump(mode="json") for item in projection.rules],
                "bypass_actors": [
                    item.model_dump(mode="json") for item in projection.bypass_actors
                ],
            }
        )
        for ruleset_id in (11, 12)
        for projection in (by_id[ruleset_id],)
    )
    raw = (list_raw, *detail_raw)
    list_projection = protocol_review._tag_ruleset_list_page_projection_from_raw(
        list_raw, repository_id=policy.repository_id, page=1
    )
    detail_projections = tuple(
        protocol_review._tag_ruleset_detail_projection_from_raw(
            item, repository_id=policy.repository_id, expected_ruleset_id=ruleset_id
        )
        for item, ruleset_id in zip(detail_raw, (11, 12), strict=True)
    )
    canonical = tuple(
        canonical_json_v1(item.model_dump(mode="json"))
        for item in (list_projection, *detail_projections)
    )
    raw_hashes = tuple(hashlib.sha256(item).hexdigest() for item in raw)
    canonical_hashes = tuple(hashlib.sha256(item).hexdigest() for item in canonical)
    payload: dict[str, object] = {
        "schema_version": "TagRulesetObservationReceiptV1",
        "repository_id": 123,
        "ruleset_ids": (11, 12),
        "tag_ruleset_policy_root": _ruleset_policy().tag_ruleset_policy_root,
        "observed_at": "2026-08-31T00:00:00.000000Z",
        "request_targets": (
            {
                "method": "GET",
                "path_and_query": (
                    "/repos/acme/repo/rulesets?includes_parents=false&targets=tag&"
                    "per_page=100&page=1"
                ),
                "accept_header": "Accept: application/vnd.github+json",
                "api_version_header": "X-GitHub-Api-Version: 2022-11-28",
            },
            {
                "method": "GET",
                "path_and_query": "/repos/acme/repo/rulesets/11?includes_parents=false",
                "accept_header": "Accept: application/vnd.github+json",
                "api_version_header": "X-GitHub-Api-Version: 2022-11-28",
            },
            {
                "method": "GET",
                "path_and_query": "/repos/acme/repo/rulesets/12?includes_parents=false",
                "accept_header": "Accept: application/vnd.github+json",
                "api_version_header": "X-GitHub-Api-Version: 2022-11-28",
            },
        ),
        "request_ids": ("rulesets-1", "ruleset-11", "ruleset-12"),
        "etags": ('"rulesets-1"', '"ruleset-11"', '"ruleset-12"'),
        "raw_response_sha256s": raw_hashes,
        "canonical_response_sha256s": canonical_hashes,
        "pagination_root": _digest(
            "laconian-tag-ruleset-pagination-root-v1",
            {
                "list_page_count": 1,
                "list_page_raw_response_sha256s": raw_hashes[:1],
                "list_page_canonical_response_sha256s": canonical_hashes[:1],
            },
        ),
    }
    payload["tag_ruleset_observation_receipt_sha256"] = _digest(
        "laconian-tag-ruleset-observation-receipt-v1", payload
    )
    return SimpleNamespace(
        receipt=TagRulesetObservationReceiptV1.model_validate(payload),
        raw=raw,
        canonical=canonical,
    )


def _archive_binding(kind: str, evidence) -> ArchivedApiReceiptBindingV1:
    receipt = evidence.receipt
    digest_field = {
        "github_signature": "github_signature_observation_receipt_sha256",
        "tag_ruleset_observation": "tag_ruleset_observation_receipt_sha256",
        "t0_creation_suite": "tag_creation_rule_suite_receipt_sha256",
        "t1_creation_suite": "tag_creation_rule_suite_receipt_sha256",
    }[kind]
    receipt_sha256 = getattr(receipt, digest_field)
    raw_paths = tuple(
        f"api/{kind}/{receipt_sha256}/{ordinal:08d}.response"
        for ordinal in range(len(evidence.raw))
    )
    canonical_paths = tuple(
        f"api/{kind}/{receipt_sha256}/{ordinal:08d}.canonical.json"
        for ordinal in range(len(evidence.canonical))
    )
    return ArchivedApiReceiptBindingV1(
        receipt_kind=kind,
        receipt_sha256=receipt_sha256,
        receipt=receipt,
        raw_blob_paths=raw_paths,
        canonical_blob_paths=canonical_paths,
    )


def _archive_blobs(binding: ArchivedApiReceiptBindingV1, evidence) -> list[ArchivedApiBlobV1]:
    blobs: list[ArchivedApiBlobV1] = []
    for path, raw in zip(binding.raw_blob_paths, evidence.raw, strict=True):
        blobs.append(
            ArchivedApiBlobV1(
                path=path,
                kind="safe_raw_response",
                byte_length=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                raw_bytes_base64=base64.b64encode(raw).decode(),
            )
        )
    for path, raw in zip(binding.canonical_blob_paths, evidence.canonical, strict=True):
        blobs.append(
            ArchivedApiBlobV1(
                path=path,
                kind="canonical_projection",
                byte_length=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                raw_bytes_base64=base64.b64encode(raw).decode(),
            )
        )
    return blobs


def _synthetic_protocol_review_impl(
    security_mode: str, inventory_root: str | None
):
    store: dict[str, object] = {}
    workflows = {
        path: f"name: workflow-{ordinal}\n".encode()
        for ordinal, path in enumerate(BENCHMARK_WORKFLOW_PATHS_V1)
    }
    workflow = build_workflow_inventory(c0_workflow_bytes=workflows)
    operator_registry = _operator_registry()
    ruleset_policy = _ruleset_policy()
    builder_identity = _builder_identity()
    registry = _protocol_reviewer_registry(security_mode)
    identity_registry = _identity_registry_bundle(registry, inventory_root=inventory_root)
    project_root = Path(__file__).resolve().parents[2]
    files = dict(workflows)
    files.update(
        {
            "benchmark/security/tag-operator-registry.json": canonical_json_v1(
                operator_registry.model_dump(mode="json")
            ),
            "benchmark/security/tag-ruleset-policy.json": canonical_json_v1(
                ruleset_policy.model_dump(mode="json")
            ),
            "benchmark/security/protocol-bundle-builder-git-identity.json": canonical_json_v1(
                builder_identity.model_dump(mode="json")
            ),
            "benchmark/security/protocol-review-identity-registry.json": canonical_json_v1(
                identity_registry.model_dump(mode="json")
            ),
            "src/laconian_eval/benchmark/protocol_review.py": (
                project_root / identity_registry.verifier_source_path
            ).read_bytes(),
            "uv.lock": (project_root / identity_registry.dependency_lock_path).read_bytes(),
            "benchmarks/campaigns/public-three-model-v1/protocol-reviewers.yaml": canonical_json_v1(
                registry.model_dump(mode="json")
            ),
            "benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json": (
                canonical_json_v1(
                    {
                        "repository_id": 123,
                        "repository_name": "repo",
                        "repository_owner": "acme",
                    }
                )
            ),
        }
    )
    c0_tree = _tree_for_files(store, files)
    c0_raw = (
        b"tree "
        + c0_tree.oid.encode()
        + b"\nauthor Campaign Input <campaign@example.com> 1788134400 +0000"
        + b"\ncommitter Campaign Input <campaign@example.com> 1788134400 +0000"
        + b"\n\nbenchmark input\n"
    )
    c0 = _git_object(store, "commit", c0_raw)
    input_message = InputTagMessageV1(
        schema_version="InputTagMessageV1",
        input_tag_ref="refs/tags/benchmark-input-20260831.1",
        companion_tag_ref="refs/tags/benchmark-attestations-20260831.1",
        peeled_c0_oid=c0.oid,
        protocol_reviewer_registry_sha256=registry.protocol_reviewer_registry_sha256,
        tag_operator_registry_sha256=operator_registry.tag_operator_registry_sha256,
        tag_ruleset_policy_root=ruleset_policy.tag_ruleset_policy_root,
        workflow_root=workflow.workflow_root,
    )
    input_tag_raw = (
        b"object "
        + c0.oid.encode()
        + b"\ntype commit\ntag benchmark-input-20260831.1"
        + b"\ntagger Laconian Tag Operator <tag-operator@users.noreply.github.com> "
        + b"1788134400 +0000\n\n"
        + canonical_json_v1(input_message.model_dump(mode="json"))
        + b"\n"
    )
    input_tag = _git_object(store, "tag", input_tag_raw)
    role_files = {
        "statistical_method": "01-statistical-method.json",
        "blind_judge_audit_protocol": "02-blind-judge-audit-protocol.json",
        "security_evidence": "03-security-evidence.json",
    }
    commits = []
    observations = []
    parent = c0
    for ordinal, reviewer in enumerate(registry.reviewers):
        statement = _review_statement(
            reviewer=reviewer,
            registry=registry,
            input_tag=input_tag,
            c0=c0,
            workflow_root=workflow.workflow_root,
            identity_registry_sha256=identity_registry.identity_registry_bundle_sha256,
        )
        statement_path = (
            "benchmarks/protocol-reviews/benchmark-input-20260831.1/statements/"
            + role_files[reviewer.role]
        )
        files[statement_path] = canonical_json_v1(statement.model_dump(mode="json"))
        review_tree = _tree_for_files(store, files)
        commit, signed_payload, signature = _review_commit(
            store,
            tree_oid=review_tree.oid,
            parent_oid=parent.oid,
            reviewer=reviewer,
            statement=statement,
        )
        observation = _signature_observation(
            commit=commit,
            reviewer=reviewer,
            signed_payload=signed_payload,
            signature=signature,
            ordinal=ordinal,
            identity_registry=identity_registry,
        )
        commits.append(commit)
        observations.append(observation)
        parent = commit
    t0_suite = _creation_suite("refs/tags/benchmark-input-20260831.1", input_tag.oid, 1001)
    prefix_objects = tuple(store[oid] for oid in sorted(store))
    prefix = verify_protocol_review_prefix(
        input_tag_ref="refs/tags/benchmark-input-20260831.1",
        objects=cast(tuple, prefix_objects),
        protocol_reviewer_registry=registry,
        tag_operator_registry=operator_registry,
        tag_ruleset_policy=ruleset_policy,
        signature_evidence_sources=cast(tuple, tuple(item.source for item in observations)),
        input_tag_creation_suite=t0_suite.receipt,
    )
    bundle = build_protocol_attestation_bundle(verified_prefix=prefix)
    attestation_names = (
        "01-statistical-method.json",
        "02-blind-judge-audit-protocol.json",
        "03-security-evidence.json",
    )
    for name, attestation in zip(attestation_names, prefix.attestations, strict=True):
        files["benchmarks/protocol-reviews/benchmark-input-20260831.1/attestations/" + name] = (
            canonical_json_v1(attestation.model_dump(mode="json"))
        )
    files["benchmarks/protocol-reviews/benchmark-input-20260831.1/bundle.json"] = canonical_json_v1(
        bundle.model_dump(mode="json")
    )
    b0_tree = _tree_for_files(store, files)
    b0_raw = (
        b"tree "
        + b0_tree.oid.encode()
        + b"\nparent "
        + commits[-1].oid.encode()
        + b"\nauthor Laconian Protocol Bundle Builder "
        + b"<laconian-protocol-bundle-builder@users.noreply.github.com> 1788134400 +0000"
        + b"\ncommitter Laconian Protocol Bundle Builder "
        + b"<laconian-protocol-bundle-builder@users.noreply.github.com> 1788134400 +0000"
        + b"\n\nlaconian protocol attestation bundle benchmark-input-20260831.1: "
        + bundle.protocol_attestation_bundle_sha256.encode()
        + b"\n"
    )
    b0 = _git_object(store, "commit", b0_raw)
    companion_message = {
        "schema_version": "ProtocolAttestationTagMessageV1",
        "input_tag_ref": "refs/tags/benchmark-input-20260831.1",
        "input_tag_oid": input_tag.oid,
        "input_tag_object_sha256": input_tag.git_object_sha256,
        "companion_tag_ref": "refs/tags/benchmark-attestations-20260831.1",
        "bundle_commit_oid": b0.oid,
        "bundle_commit_object_sha256": b0.git_object_sha256,
        "protocol_attestation_bundle_sha256": bundle.protocol_attestation_bundle_sha256,
        "protocol_attestations_root": bundle.protocol_attestations_root,
        "tag_operator_registry_sha256": operator_registry.tag_operator_registry_sha256,
        "tag_ruleset_policy_root": ruleset_policy.tag_ruleset_policy_root,
    }
    companion_raw = (
        b"object "
        + b0.oid.encode()
        + b"\ntype commit\ntag benchmark-attestations-20260831.1"
        + b"\ntagger Laconian Tag Operator <tag-operator@users.noreply.github.com> "
        + b"1788134400 +0000\n\n"
        + canonical_json_v1(companion_message)
        + b"\n"
    )
    companion_tag = _git_object(store, "tag", companion_raw)
    t1_suite = _creation_suite(
        "refs/tags/benchmark-attestations-20260831.1", companion_tag.oid, 1002
    )
    objects = cast(tuple, tuple(store[oid] for oid in sorted(store)))
    dag = verify_protocol_review_dag(
        input_tag_ref="refs/tags/benchmark-input-20260831.1",
        companion_tag_ref="refs/tags/benchmark-attestations-20260831.1",
        objects=objects,
        protocol_reviewer_registry=registry,
        tag_operator_registry=operator_registry,
        tag_ruleset_policy=ruleset_policy,
        signature_evidence_sources=tuple(item.source for item in observations),
        tag_creation_suites=(t0_suite.receipt, t1_suite.receipt),
    )
    binding = build_protocol_attestation_tag_binding(verified_dag=dag, bundle=bundle)
    ruleset_observation = _ruleset_observation()
    evidence_by_kind = [
        *(("github_signature", item) for item in observations),
        ("tag_ruleset_observation", ruleset_observation),
        ("t0_creation_suite", t0_suite),
        ("t1_creation_suite", t1_suite),
    ]
    wrapper_pairs = [
        (kind, evidence, _archive_binding(kind, evidence)) for kind, evidence in evidence_by_kind
    ]
    rank = {
        "github_signature": 0,
        "tag_ruleset_observation": 1,
        "t0_creation_suite": 2,
        "t1_creation_suite": 3,
    }
    wrapper_pairs.sort(key=lambda item: (rank[item[0]], item[2].receipt_sha256))
    wrappers = tuple(item[2] for item in wrapper_pairs)
    blobs = tuple(
        sorted(
            (
                blob
                for _, evidence, wrapper in wrapper_pairs
                for blob in _archive_blobs(wrapper, evidence)
            ),
            key=lambda item: item.path.encode(),
        )
    )
    archive = build_protocol_review_object_archive(
        verified_dag=dag,
        api_blobs=blobs,
        api_receipts=wrappers,
    )
    return SimpleNamespace(
        prefix=prefix,
        dag=dag,
        bundle=bundle,
        binding=binding,
        archive=archive,
        input_tag=input_tag,
        c0=c0,
        commits=tuple(commits),
        b0=b0,
        companion_tag=companion_tag,
        observations=tuple(observations),
        registry=registry,
        operator_registry=operator_registry,
        ruleset_policy=ruleset_policy,
        identity_registry=identity_registry,
        t0_suite=t0_suite,
        t1_suite=t1_suite,
    )


@cache
def _synthetic_protocol_review(
    security_mode: str = "ssh_sha256", inventory_root: str | None = None
):
    if inventory_root is None:
        return _synthetic_protocol_review_impl(security_mode, inventory_root)
    project_root = Path(__file__).resolve().parents[2]
    verified_runtime = (
        (project_root / "src/laconian_eval/benchmark/protocol_review.py").read_bytes(),
        (project_root / "uv.lock").read_bytes(),
    )
    with patch.object(
        protocol_review,
        "_verify_active_verifier_runtime",
        return_value=verified_runtime,
    ):
        return _synthetic_protocol_review_impl(security_mode, inventory_root)


def test_serial_git_prefix_golden_bytes_oids_raw_sha256_and_sizes() -> None:
    fixture = _synthetic_protocol_review(inventory_root="9" * 64)
    assert tuple(
        (item.oid, item.git_object_sha256, len(item.raw_content))
        for item in (
            fixture.input_tag,
            fixture.c0,
            *fixture.commits,
            fixture.b0,
            fixture.companion_tag,
        )
    ) == (
        (
            "ce664b80e759ed987b2a1e424454d1da9910b27d",
            "bb514975acb47675f394d23b1abb540e0b9c0015d0fbbaac08ea701d0c9811c9",
            774,
        ),
        (
            "557214a1052d9dc378aaeb71228da06ee48f4fa5",
            "1ce0b4f496fba490d0e267eb6eecabc34b7cf5d6bffa487144540c0f066ac751",
            190,
        ),
        (
            "4cb017d52988409d8c824a07e0fd633717f3647d",
            "ca5f6cf85b0a02a8aa38d8dd053c0770f51c46b60227f24ee0ad2aa6b31513b7",
            484,
        ),
        (
            "9be0652f440db7da477a5f80fb96f03a5453dac1",
            "32b0c1a72b2e5e0a0e5c816111e625c25477e38e730465c2560b9419c46d31bd",
            492,
        ),
        (
            "1c298825e5ff5a7dea8181f8e7da9da9a326556c",
            "3fba954690fa3d5af95ec2511e8fb9773b206eb64f883838c5399e5c76a28e7e",
            688,
        ),
        (
            "0841d092005415447b3f7ff3fb9501783c131752",
            "c489dcba9c78001cbd65af4c2ab99d1bde6f71f17634ff8415e2749542ecd50c",
            462,
        ),
        (
            "9931185546afea7658d495b5c236cd3c27948371",
            "acc8d2b23009e4a901e41f337d27a70b96c72b29e01a9a4db215c348291cbffd",
            1062,
        ),
    )
    assert fixture.bundle.protocol_attestation_bundle_sha256 == (
        "12a588a15ab02a74dd1e37b21a0a87a12d567957fd09dc69aec855e9ab37f28d"
    )
    assert fixture.binding.object_closure_root == (
        "2aecf4f16440b747fa0ac44a27473e6d148e61ac2fa2654bafb819cac8fab20a"
    )
    assert fixture.archive.protocol_review_object_archive_sha256 == (
        "4ab9b134ec28b4a9a68dae4a37515951551fde570070dc89bdc9dcbb2aca8b0a"
    )


def test_prefix_verification_reconstructs_source_backed_signature_evidence() -> None:
    fixture = _synthetic_protocol_review()
    assert tuple(item.statement.role for item in fixture.prefix.attestations) == (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    assert tuple(
        item.signature_evidence.github_rest_verification.verified_at
        for item in fixture.prefix.attestations
    ) == tuple(item.evidence.github_rest_verification.verified_at for item in fixture.observations)
    assert fixture.prefix.attestations[2].signature_evidence.verification_mode == "ssh_sha256"

    reviewer = fixture.registry.reviewers[2]
    direct = verify_commit_signature_evidence_source(
        source=fixture.observations[2].source,
        commit=fixture.commits[2],
        expected_parent_oid=fixture.commits[1].oid,
        expected_primary_path=fixture.observations[2].evidence.statement_path,
        expected_repository_id=fixture.ruleset_policy.repository_id,
        expected_repository_owner="acme",
        expected_repository_name="repo",
        expected_signer_numeric_account_id=reviewer.reviewer_numeric_account_id,
        expected_signer_login=reviewer.reviewer_login,
        expected_verification_mode=reviewer.verification_mode,
        expected_signing_fingerprint=reviewer.signing_fingerprint,
        signing_key=fixture.identity_registry.keys[0],
        expected_git_identity=(
            reviewer.author_name_ascii,
            reviewer.author_email_ascii,
            reviewer.committer_name_ascii,
            reviewer.committer_email_ascii,
        ),
        identity_registry_bundle=fixture.identity_registry,
        audit_reviewer_registry=None,
    )
    assert direct == fixture.observations[2].evidence


def test_complete_dag_bundle_binding_and_archive_replay_are_source_backed() -> None:
    fixture = _synthetic_protocol_review()
    replayed = load_verified_protocol_review_object_archive(fixture.archive)
    assert replayed.bundle == fixture.bundle
    assert replayed.companion_tag == fixture.companion_tag
    assert fixture.binding.object_closure_root == fixture.archive.object_closure_root
    assert fixture.t0_suite.receipt.pushed_at.isoformat() != "2026-08-31T00:00:00+00:00"
    assert fixture.t0_suite.receipt.pushed_at <= fixture.t0_suite.receipt.observed_at
    assert fixture.b0.oid not in {item.oid for item in fixture.prefix.objects}
    assert fixture.companion_tag.oid not in {item.oid for item in fixture.prefix.objects}
    archived_by_oid = {item.oid: item for item in fixture.archive.objects}
    assert set(archived_by_oid) == {item.oid for item in fixture.dag.objects}
    for item in fixture.dag.objects:
        assert base64.b64decode(archived_by_oid[item.oid].raw_content_base64) == item.raw_content


def test_github_creation_raw_shape_derives_the_exact_canonical_projection() -> None:
    suite = _creation_suite("refs/tags/benchmark-input-20260831.1", "a" * 40, 1001)
    assert b'"id":1001' in suite.raw[0]
    assert b'"actor_id":101' in suite.raw[0]
    assert b'"actor_name":"tag-operator"' in suite.raw[0]
    assert b'"operation"' not in suite.raw[0]
    assert b'"creation_bypass_grant"' not in suite.raw[0]
    projection = protocol_review._creation_projection_from_raw(
        suite.raw[0],
        kind="t0_creation_suite",
        tag_ruleset_policy=_ruleset_policy(),
    )
    assert projection["pushed_at"] == "2026-08-31T00:00:01.000000Z"
    assert canonical_json_v1(projection) == suite.canonical[0]


@pytest.mark.parametrize(
    ("old", "new", "match"),
    (
        (b'"id":1001', b'"id":true', "positive JSON integer"),
        (b'"result":"bypass"', b'"result":"pass"', "authorized new-tag"),
        (b'"actor_id":101', b'"actor_id":102', "authorized new-tag"),
        (b'"type":"ruleset"', b'"type":"branch"', "authorized new-tag"),
        (b'"id":11,"name"', b'"id":12,"name"', "authorized new-tag"),
        (
            b'"pushed_at":"2026-08-31T00:00:01Z"',
            b'"pushed_at":"2026-08-31T00:00:01.000000Z"',
            "whole-second UTC",
        ),
    ),
)
def test_github_creation_raw_shape_rejects_hostile_selected_values(
    old: bytes, new: bytes, match: str
) -> None:
    suite = _creation_suite("refs/tags/benchmark-input-20260831.1", "a" * 40, 1001)
    mutated = suite.raw[0].replace(old, new, 1)
    assert mutated != suite.raw[0]
    with pytest.raises(ValueError, match=match):
        protocol_review._creation_projection_from_raw(
            mutated,
            kind="t0_creation_suite",
            tag_ruleset_policy=_ruleset_policy(),
        )


def test_archive_creation_replay_rejects_pseudo_raw_canonical_projection() -> None:
    fixture = _synthetic_protocol_review()
    payload = fixture.archive.model_dump(mode="json")
    receipts = cast(list[dict[str, object]], payload["api_receipts"])
    target = next(item for item in receipts if item["receipt_kind"] == "t0_creation_suite")
    old_digest = cast(str, target["receipt_sha256"])
    receipt = cast(dict[str, object], target["receipt"])
    raw_paths = cast(list[str], target["raw_blob_paths"])
    canonical_paths = cast(list[str], target["canonical_blob_paths"])
    blobs = cast(list[dict[str, object]], payload["api_blobs"])
    raw_blob = next(item for item in blobs if item["path"] == raw_paths[0])
    canonical_blob = next(item for item in blobs if item["path"] == canonical_paths[0])
    pseudo_raw = base64.b64decode(cast(str, canonical_blob["raw_bytes_base64"]))
    pseudo_raw_sha256 = hashlib.sha256(pseudo_raw).hexdigest()
    receipt["raw_response_sha256"] = pseudo_raw_sha256
    receipt["tag_creation_rule_suite_receipt_sha256"] = _digest(
        "laconian-tag-creation-rule-suite-receipt-v1",
        {
            key: value
            for key, value in receipt.items()
            if key != "tag_creation_rule_suite_receipt_sha256"
        },
    )
    new_digest = cast(str, receipt["tag_creation_rule_suite_receipt_sha256"])
    target["receipt_sha256"] = new_digest
    for paths in (raw_paths, canonical_paths):
        for ordinal, old_path in enumerate(paths):
            new_path = old_path.replace(old_digest, new_digest)
            next(item for item in blobs if item["path"] == old_path)["path"] = new_path
            paths[ordinal] = new_path
    raw_blob["byte_length"] = len(pseudo_raw)
    raw_blob["sha256"] = pseudo_raw_sha256
    raw_blob["raw_bytes_base64"] = base64.b64encode(pseudo_raw).decode("ascii")
    blobs.sort(key=lambda item: cast(str, item["path"]).encode())
    payload["protocol_review_object_archive_sha256"] = _digest(
        "laconian-protocol-review-object-archive-v1",
        {
            key: value
            for key, value in payload.items()
            if key != "protocol_review_object_archive_sha256"
        },
    )
    mutated_archive = ProtocolReviewObjectArchiveV1.model_validate(payload)
    with pytest.raises(ValueError, match="raw t0_creation_suite"):
        load_verified_protocol_review_object_archive(mutated_archive)


def test_openpgp_source_backed_prefix_dag_bundle_and_archive_replay() -> None:
    fixture = _synthetic_protocol_review("openpgp_fingerprint")
    security = fixture.prefix.attestations[2].signature_evidence
    assert isinstance(security, OpenPGPVerifiedCommitEvidenceV1)
    assert security.fingerprint == fixture.registry.reviewers[2].signing_fingerprint
    assert security.keyring_sha256 == fixture.identity_registry.keys[0].public_key_sha256
    assert fixture.dag.prefix.attestations[2] == fixture.prefix.attestations[2]
    replayed = load_verified_protocol_review_object_archive(fixture.archive)
    assert replayed.bundle == fixture.bundle
    assert replayed.prefix.attestations[2].signature_evidence == security


def test_verified_protocol_attestation_embeds_byte_identical_statement_and_mode_discriminated_evidence() -> (  # noqa: E501
    None
):
    fixture = _synthetic_protocol_review()
    for statement, attestation, source in zip(
        fixture.prefix.statements,
        fixture.prefix.attestations,
        fixture.prefix.signature_evidence_sources,
        strict=True,
    ):
        assert canonical_json_v1(
            attestation.statement.model_dump(mode="json")
        ) == canonical_json_v1(statement.model_dump(mode="json"))
        assert canonical_json_v1(
            attestation.signature_evidence.model_dump(mode="json")
        ) == canonical_json_v1(source.signature_evidence.model_dump(mode="json"))


def test_protocol_bundle_embeds_three_ordered_envelopes_and_no_b0_or_t1_identity() -> None:
    fixture = _synthetic_protocol_review()
    assert fixture.bundle.attestations == fixture.prefix.attestations
    assert tuple(item.statement.role for item in fixture.bundle.attestations) == (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    assert not {
        "bundle_commit_oid",
        "companion_tag_oid",
        "companion_tag_ref",
    }.intersection(ProtocolAttestationBundleV1.model_fields)


def test_tag_binding_binds_t0_c0_three_reviewers_b0_t1_bundle_closure_operator_and_policy() -> None:
    fixture = _synthetic_protocol_review()
    binding = fixture.binding
    assert binding.input_tag_oid == fixture.input_tag.oid
    assert binding.peeled_c0_oid == fixture.c0.oid
    assert tuple(item.commit_oid for item in binding.reviewer_commits) == tuple(
        item.oid for item in fixture.commits
    )
    assert binding.bundle_commit_oid == fixture.b0.oid
    assert binding.companion_tag_oid == fixture.companion_tag.oid
    assert binding.protocol_attestation_bundle_sha256 == (
        fixture.bundle.protocol_attestation_bundle_sha256
    )
    assert binding.object_closure_root == fixture.archive.object_closure_root
    assert binding.tag_operator_registry_sha256 == (
        fixture.operator_registry.tag_operator_registry_sha256
    )
    assert binding.tag_ruleset_policy_root == fixture.ruleset_policy.tag_ruleset_policy_root


def test_t0_and_t1_creation_suites_are_unique_nonreplayable_and_bind_all_zero_before_exact_after() -> (  # noqa: E501
    None
):
    fixture = _synthetic_protocol_review()
    t0 = fixture.t0_suite.receipt
    t1 = fixture.t1_suite.receipt
    assert t0.rule_suite_id != t1.rule_suite_id
    assert not set(t0.request_ids).intersection(t1.request_ids)
    assert t0.before_sha == t1.before_sha == "0" * 40
    assert t0.after_sha == fixture.input_tag.oid
    assert t1.after_sha == fixture.companion_tag.oid
    assert t0.pushed_at <= t0.observed_at and t1.pushed_at <= t1.observed_at


def test_ruleset_observation_receipt_has_exact_ordered_fields_lf_digest_and_no_creation_claim() -> (
    None
):
    observation = _ruleset_observation().receipt
    assert tuple(TagRulesetObservationReceiptV1.model_fields) == (
        "schema_version",
        "repository_id",
        "ruleset_ids",
        "tag_ruleset_policy_root",
        "observed_at",
        "request_targets",
        "request_ids",
        "etags",
        "raw_response_sha256s",
        "canonical_response_sha256s",
        "pagination_root",
        "tag_ruleset_observation_receipt_sha256",
    )
    assert observation.ruleset_ids == (11, 12)
    assert observation.tag_ruleset_observation_receipt_sha256 == _digest(
        "laconian-tag-ruleset-observation-receipt-v1",
        observation.model_dump(mode="json", exclude={"tag_ruleset_observation_receipt_sha256"}),
    )
    assert not {
        "actor_account_id",
        "creation_bypass_grant",
        "rule_suite_id",
    }.intersection(TagRulesetObservationReceiptV1.model_fields)


def test_ruleset_request_targets_are_exact_and_selected_ids_are_strict_integers() -> None:
    target = TagRulesetRequestTargetV1(
        method="GET",
        path_and_query=(
            "/repos/acme/repo/rulesets?includes_parents=false&targets=tag&per_page=100&page=1"
        ),
        accept_header="Accept: application/vnd.github+json",
        api_version_header="X-GitHub-Api-Version: 2022-11-28",
    )
    payload = target.model_dump(mode="json")
    for mutation in (
        {"method": "POST"},
        {"accept_header": "Accept: application/json"},
        {"api_version_header": "X-GitHub-Api-Version: 2022-11-29"},
        {
            "path_and_query": (
                "/repos/acme/repo/rulesets?targets=tag&includes_parents=false&per_page=100&page=1"
            )
        },
    ):
        with pytest.raises(ValidationError):
            TagRulesetRequestTargetV1.model_validate(payload | mutation)

    for raw in (b'[{"id":true}]', b'[{"id":11.0}]', b'[{"id":1e1}]'):
        with pytest.raises(protocol_review.ProtocolReviewVerificationError):
            protocol_review._tag_ruleset_list_page_projection_from_raw(
                raw, repository_id=123, page=1
            )


def test_archive_receipt_wrapper_has_exact_kind_order_paths_hash_binding_and_no_self_digest() -> (
    None
):
    fixture = _synthetic_protocol_review()
    assert tuple(ArchivedApiReceiptBindingV1.model_fields) == (
        "receipt_kind",
        "receipt_sha256",
        "receipt",
        "raw_blob_paths",
        "canonical_blob_paths",
    )
    kinds = tuple(item.receipt_kind for item in fixture.archive.api_receipts)
    assert kinds[:3] == ("github_signature",) * 3
    assert kinds[3:] == (
        "tag_ruleset_observation",
        "t0_creation_suite",
        "t1_creation_suite",
    )
    paths = {item.path: item for item in fixture.archive.api_blobs}
    for wrapper in fixture.archive.api_receipts:
        for raw_path, canonical_path in zip(
            wrapper.raw_blob_paths, wrapper.canonical_blob_paths, strict=True
        ):
            assert paths[raw_path].kind == "safe_raw_response"
            assert paths[canonical_path].kind == "canonical_projection"


def test_forged_verified_wrappers_and_model_constructed_bundle_are_reverified() -> None:
    fixture = _synthetic_protocol_review()
    forged_prefix = replace(
        fixture.prefix,
        attestations=(
            fixture.prefix.attestations[1],
            fixture.prefix.attestations[0],
            fixture.prefix.attestations[2],
        ),
    )
    with pytest.raises(ValueError, match=r"B0 attestations|role order"):
        build_protocol_attestation_bundle(verified_prefix=forged_prefix)
    forged_bundle = ProtocolAttestationBundleV1.model_construct(
        **{
            name: (
                "0" * 64
                if name == "protocol_attestation_bundle_sha256"
                else getattr(fixture.bundle, name)
            )
            for name in ProtocolAttestationBundleV1.model_fields
        }
    )
    with pytest.raises(ValidationError):
        build_protocol_attestation_tag_binding(
            verified_dag=fixture.dag,
            bundle=forged_bundle,
        )


def test_protocol_review_rejects_future_objects_and_creation_suite_replay() -> None:
    fixture = _synthetic_protocol_review()
    extra = parse_protocol_git_object(
        oid=hashlib.sha1(b"blob 5\0extra").hexdigest(),
        object_type="blob",
        raw_content=b"extra",
    )
    extra_objects = tuple(sorted((*fixture.prefix.objects, extra), key=lambda item: item.oid))
    with pytest.raises(ValueError, match="extra, or future"):
        verify_protocol_review_prefix(
            input_tag_ref="refs/tags/benchmark-input-20260831.1",
            objects=extra_objects,
            protocol_reviewer_registry=fixture.registry,
            tag_operator_registry=fixture.operator_registry,
            tag_ruleset_policy=fixture.ruleset_policy,
            signature_evidence_sources=cast(
                tuple, tuple(item.source for item in fixture.observations)
            ),
            input_tag_creation_suite=fixture.t0_suite.receipt,
        )
    replayed_t0 = _creation_suite("refs/tags/benchmark-input-20260831.1", "f" * 40, 1001)
    with pytest.raises(ValueError, match="does not bind operator/policy/tag"):
        verify_protocol_review_prefix(
            input_tag_ref="refs/tags/benchmark-input-20260831.1",
            objects=fixture.prefix.objects,
            protocol_reviewer_registry=fixture.registry,
            tag_operator_registry=fixture.operator_registry,
            tag_ruleset_policy=fixture.ruleset_policy,
            signature_evidence_sources=cast(
                tuple, tuple(item.source for item in fixture.observations)
            ),
            input_tag_creation_suite=replayed_t0.receipt,
        )


def test_transport_metadata_does_not_change_stable_verified_evidence() -> None:
    fixture = _synthetic_protocol_review()
    mutated_sources = []
    for ordinal, evidence in enumerate(fixture.observations):
        payload = evidence.receipt.model_dump(mode="json")
        payload["observed_at"] = "2026-08-31T00:10:00.000000Z"
        payload["request_ids"] = [f"new-rest-{ordinal}", f"new-graphql-{ordinal}"]
        payload["etags"] = [f'"new-rest-{ordinal}"', f'"new-graphql-{ordinal}"']
        payload["github_signature_observation_receipt_sha256"] = _digest(
            "laconian-github-signature-observation-receipt-v1",
            {
                key: value
                for key, value in payload.items()
                if key != "github_signature_observation_receipt_sha256"
            },
        )
        mutated_receipt = GitHubSignatureObservationReceiptV1.model_validate(payload)
        mutated_sources.append(
            ProtocolSignatureEvidenceSourceV1(
                observation_receipt=mutated_receipt,
                signature_evidence=evidence.evidence,
                raw_response_bytes=evidence.raw,
                canonical_response_bytes=evidence.canonical,
            )
        )
    rebuilt = verify_protocol_review_prefix(
        input_tag_ref="refs/tags/benchmark-input-20260831.1",
        objects=fixture.prefix.objects,
        protocol_reviewer_registry=fixture.registry,
        tag_operator_registry=fixture.operator_registry,
        tag_ruleset_policy=fixture.ruleset_policy,
        signature_evidence_sources=cast(tuple, tuple(mutated_sources)),
        input_tag_creation_suite=fixture.t0_suite.receipt,
    )
    assert tuple(item.attestation_sha256 for item in rebuilt.attestations) == tuple(
        item.attestation_sha256 for item in fixture.prefix.attestations
    )


def _source_with_raw_rest(
    source: ProtocolSignatureEvidenceSourceV1, raw_rest: bytes
) -> ProtocolSignatureEvidenceSourceV1:
    receipt_payload = source.observation_receipt.model_dump(mode="json")
    raw_hashes = list(receipt_payload["raw_response_sha256s"])
    raw_hashes[0] = hashlib.sha256(raw_rest).hexdigest()
    receipt_payload["raw_response_sha256s"] = raw_hashes
    receipt_payload["github_signature_observation_receipt_sha256"] = _digest(
        "laconian-github-signature-observation-receipt-v1",
        {
            key: value
            for key, value in receipt_payload.items()
            if key != "github_signature_observation_receipt_sha256"
        },
    )
    return ProtocolSignatureEvidenceSourceV1(
        observation_receipt=GitHubSignatureObservationReceiptV1.model_validate(receipt_payload),
        signature_evidence=source.signature_evidence,
        raw_response_bytes=(raw_rest, source.raw_response_bytes[1]),
        canonical_response_bytes=source.canonical_response_bytes,
    )


def _source_with_raw_graphql(
    source: ProtocolSignatureEvidenceSourceV1, raw_graphql: bytes
) -> ProtocolSignatureEvidenceSourceV1:
    receipt_payload = source.observation_receipt.model_dump(mode="json")
    raw_hashes = list(receipt_payload["raw_response_sha256s"])
    raw_hashes[1] = hashlib.sha256(raw_graphql).hexdigest()
    receipt_payload["raw_response_sha256s"] = raw_hashes
    receipt_payload["github_signature_observation_receipt_sha256"] = _digest(
        "laconian-github-signature-observation-receipt-v1",
        {
            key: value
            for key, value in receipt_payload.items()
            if key != "github_signature_observation_receipt_sha256"
        },
    )
    return ProtocolSignatureEvidenceSourceV1(
        observation_receipt=GitHubSignatureObservationReceiptV1.model_validate(receipt_payload),
        signature_evidence=source.signature_evidence,
        raw_response_bytes=(source.raw_response_bytes[0], raw_graphql),
        canonical_response_bytes=source.canonical_response_bytes,
    )


@pytest.mark.parametrize("mutation", ["false-success", "duplicate-key", "verified-at"])
def test_source_derivation_rejects_synthetic_or_ambiguous_rest_values(mutation: str) -> None:
    fixture = _synthetic_protocol_review()
    original = fixture.observations[0].source
    if mutation == "false-success":
        raw = original.raw_response_bytes[0].replace(b'"verified":true', b'"verified":false')
        match = "must be true"
    elif mutation == "duplicate-key":
        raw = (
            original.raw_response_bytes[0][:-1]
            + b',"sha":"'
            + fixture.commits[0].oid.encode()
            + b'"}'
        )
        match = "duplicate key"
    else:
        raw = original.raw_response_bytes[0].replace(
            b"2026-08-31T03:00:00+03:00", b"2026-08-31T03:00:01+03:00"
        )
        match = "canonical projections"
    mutated = _source_with_raw_rest(original, raw)
    sources = (mutated, fixture.observations[1].source, fixture.observations[2].source)
    with pytest.raises(ValueError, match=match):
        verify_protocol_review_prefix(
            input_tag_ref="refs/tags/benchmark-input-20260831.1",
            objects=fixture.prefix.objects,
            protocol_reviewer_registry=fixture.registry,
            tag_operator_registry=fixture.operator_registry,
            tag_ruleset_policy=fixture.ruleset_policy,
            signature_evidence_sources=sources,
            input_tag_creation_suite=fixture.t0_suite.receipt,
        )


@pytest.mark.parametrize(
    ("replacement", "match"),
    (
        (b'"databaseId":true', "positive JSON integer"),
        (b'"databaseId":123.0', "positive JSON integer"),
    ),
)
def test_source_derivation_rejects_bool_or_float_selected_graphql_id(
    replacement: bytes, match: str
) -> None:
    fixture = _synthetic_protocol_review()
    original = fixture.observations[0].source
    raw = original.raw_response_bytes[1].replace(b'"databaseId":123', replacement, 1)
    mutated = _source_with_raw_graphql(original, raw)
    with pytest.raises(ValueError, match=match):
        verify_protocol_review_prefix(
            input_tag_ref="refs/tags/benchmark-input-20260831.1",
            objects=fixture.prefix.objects,
            protocol_reviewer_registry=fixture.registry,
            tag_operator_registry=fixture.operator_registry,
            tag_ruleset_policy=fixture.ruleset_policy,
            signature_evidence_sources=(
                mutated,
                fixture.observations[1].source,
                fixture.observations[2].source,
            ),
            input_tag_creation_suite=fixture.t0_suite.receipt,
        )


def test_protocol_object_tuple_rejects_non_oid_order() -> None:
    fixture = _synthetic_protocol_review()
    with pytest.raises(ValueError, match="strict ascending decoded-OID order"):
        verify_protocol_review_prefix(
            input_tag_ref="refs/tags/benchmark-input-20260831.1",
            objects=tuple(reversed(fixture.prefix.objects)),
            protocol_reviewer_registry=fixture.registry,
            tag_operator_registry=fixture.operator_registry,
            tag_ruleset_policy=fixture.ruleset_policy,
            signature_evidence_sources=tuple(item.source for item in fixture.observations),
            input_tag_creation_suite=fixture.t0_suite.receipt,
        )


def test_archive_replay_rejects_hash_consistent_raw_rest_success_mutation() -> None:
    fixture = _synthetic_protocol_review()
    payload = fixture.archive.model_dump(mode="json")
    receipts = cast(list[dict[str, object]], payload["api_receipts"])
    target = next(item for item in receipts if item["receipt_kind"] == "github_signature")
    old_digest = cast(str, target["receipt_sha256"])
    receipt = cast(dict[str, object], target["receipt"])
    raw_paths = cast(list[str], target["raw_blob_paths"])
    canonical_paths = cast(list[str], target["canonical_blob_paths"])
    blobs = cast(list[dict[str, object]], payload["api_blobs"])
    raw_blob = next(item for item in blobs if item["path"] == raw_paths[0])
    raw = base64.b64decode(cast(str, raw_blob["raw_bytes_base64"]))
    mutated_raw = raw.replace(b'"verified":true', b'"verified":false')
    mutated_hash = hashlib.sha256(mutated_raw).hexdigest()
    raw_hashes = cast(list[str], receipt["raw_response_sha256s"])
    raw_hashes[0] = mutated_hash
    receipt["github_signature_observation_receipt_sha256"] = _digest(
        "laconian-github-signature-observation-receipt-v1",
        {
            key: value
            for key, value in receipt.items()
            if key != "github_signature_observation_receipt_sha256"
        },
    )
    new_digest = cast(str, receipt["github_signature_observation_receipt_sha256"])
    target["receipt_sha256"] = new_digest
    for paths in (raw_paths, canonical_paths):
        for ordinal, old_path in enumerate(paths):
            new_path = old_path.replace(old_digest, new_digest)
            next(item for item in blobs if item["path"] == old_path)["path"] = new_path
            paths[ordinal] = new_path
    raw_blob["byte_length"] = len(mutated_raw)
    raw_blob["sha256"] = mutated_hash
    raw_blob["raw_bytes_base64"] = base64.b64encode(mutated_raw).decode("ascii")
    cast(list[dict[str, object]], payload["api_blobs"]).sort(
        key=lambda item: cast(str, item["path"]).encode()
    )
    rank = {
        "github_signature": 0,
        "tag_ruleset_observation": 1,
        "t0_creation_suite": 2,
        "t1_creation_suite": 3,
    }
    receipts.sort(
        key=lambda item: (
            rank[cast(str, item["receipt_kind"])],
            cast(dict[str, object], item["receipt"]).get("observed_at", ""),
            cast(str, item["receipt_sha256"]),
        )
    )
    payload["protocol_review_object_archive_sha256"] = _digest(
        "laconian-protocol-review-object-archive-v1",
        {
            key: value
            for key, value in payload.items()
            if key != "protocol_review_object_archive_sha256"
        },
    )
    mutated_archive = ProtocolReviewObjectArchiveV1.model_validate(payload)
    with pytest.raises(ValueError, match="must be true"):
        load_verified_protocol_review_object_archive(mutated_archive)


def test_supplied_local_receipt_cannot_skip_fresh_ssh_verification() -> None:
    fixture = _synthetic_protocol_review()
    source = fixture.observations[2].source
    evidence_payload = source.signature_evidence.model_dump(mode="json")
    local = cast(dict[str, object], evidence_payload["local_signature_verification"])
    local["signature_sha256"] = "0" * 64
    local["verification_receipt_sha256"] = _digest(
        "laconian-local-signature-verification-receipt-v1",
        {key: value for key, value in local.items() if key != "verification_receipt_sha256"},
    )
    altered_evidence = SSHVerifiedCommitEvidenceV1.model_validate(evidence_payload)
    altered_source = ProtocolSignatureEvidenceSourceV1(
        observation_receipt=source.observation_receipt,
        signature_evidence=altered_evidence,
        raw_response_bytes=source.raw_response_bytes,
        canonical_response_bytes=source.canonical_response_bytes,
    )
    with pytest.raises(ValueError, match="differs from fresh source reconstruction"):
        verify_protocol_review_prefix(
            input_tag_ref="refs/tags/benchmark-input-20260831.1",
            objects=fixture.prefix.objects,
            protocol_reviewer_registry=fixture.registry,
            tag_operator_registry=fixture.operator_registry,
            tag_ruleset_policy=fixture.ruleset_policy,
            signature_evidence_sources=(
                fixture.observations[0].source,
                fixture.observations[1].source,
                altered_source,
            ),
            input_tag_creation_suite=fixture.t0_suite.receipt,
        )
