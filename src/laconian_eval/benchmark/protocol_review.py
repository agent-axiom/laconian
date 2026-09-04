"""Strict, network-free protocol-review evidence contracts.

The protocol-review graph deliberately uses a different digest boundary from legacy capsule
attachments: every digest in this module is ``UTF8(domain) + LF + CanonicalJSONV1(value)``.
Transport metadata is kept in observation receipts and never enters the stable review objects.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.metadata as importlib_metadata
import importlib.util
import io
import json
import os
import platform
import re
import stat
import sys
import tempfile
import tomllib
import unicodedata
from abc import ABCMeta
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import (
    BuiltinFunctionType,
    FunctionType,
    MappingProxyType,
    MethodDescriptorType,
    ModuleType,
)
from typing import (
    Annotated,
    Any,
    Literal,
    Protocol,
    Self,
    TypeAlias,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from laconian_eval.benchmark.attachments import (
    CanonicalJSONV1Error,
    canonical_json_v1,
    parse_canonical_json_v1,
)
from laconian_eval.capsule.schema import (
    BoundedNonBlankString,
    CanonicalTimestamp,
    CapsuleModel,
    RelativePosixPath,
    Sha256,
    StrictPositiveInt,
)

GitObjectTypeV1 = Literal["blob", "tree", "commit", "tag"]
SignatureVerificationModeV1 = Literal["github_verified_commit", "ssh_sha256", "openpgp_fingerprint"]
ProtocolReviewRoleV1 = Literal[
    "statistical_method",
    "blind_judge_audit_protocol",
    "security_evidence",
]

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SSH_FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
_OPENPGP_FINGERPRINT_RE = re.compile(r"^[0-9A-F]{40}$")
_INPUT_TAG_REF_RE = re.compile(r"^refs/tags/benchmark-input-([0-9]{8})\.([1-9][0-9]*)$")
_COMPANION_TAG_REF_RE = re.compile(r"^refs/tags/benchmark-attestations-([0-9]{8})\.([1-9][0-9]*)$")
_WHOLE_SECOND_UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_GIT_EPOCH_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
_ARCHIVE_API_PATH_RE = re.compile(
    r"^api/(github_signature|tag_ruleset_observation|t0_creation_suite|t1_creation_suite)/"
    r"([0-9a-f]{64})/([0-9]{8})\.(response|canonical\.json)$"
)
_PROVIDER_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
_GITHUB_RULESET_LIST_TARGET_RE = re.compile(
    r"^/repos/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9_-])?)/rulesets\?"
    r"includes_parents=false&targets=tag&per_page=100&page=(?P<page>[1-9][0-9]*)$",
    flags=re.ASCII,
)
_GITHUB_RULESET_DETAIL_TARGET_RE = re.compile(
    r"^/repos/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9_-])?)/rulesets/"
    r"(?P<ruleset_id>[1-9][0-9]*)\?includes_parents=false$",
    flags=re.ASCII,
)


def protocol_review_digest(domain: str, value: object) -> str:
    """Hash one CanonicalJSONV1 value under the protocol-review LF boundary."""

    if (
        type(domain) is not str
        or unicodedata.normalize("NFC", domain) != domain
        or not domain
        or "\n" in domain
        or "\0" in domain
    ):
        raise CanonicalJSONV1Error(
            "protocol-review digest domain must be nonempty NFC without LF or NUL"
        )
    return hashlib.sha256(domain.encode("utf-8") + b"\n" + canonical_json_v1(value)).hexdigest()


def _strict_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("value must be a string")
    return value


def _git_sha1(value: str) -> str:
    if _SHA1_RE.fullmatch(value) is None:
        raise ValueError("Git object ID must be 40 lowercase hexadecimal characters")
    return value


GitObjectId: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_git_sha1),
]
GitObjectSHA256V1: TypeAlias = Sha256


def _canonical_git_ascii_name(value: str) -> str:
    encoded = value.encode("ascii", errors="strict")
    if not 1 <= len(encoded) <= 80:
        raise ValueError("Git identity name must contain 1..80 ASCII bytes")
    if any(
        byte < 0x21 or byte > 0x7E or byte in (ord("<"), ord(">"))
        for byte in encoded
        if byte != 0x20
    ):
        raise ValueError("Git identity name contains a forbidden byte")
    tokens = value.split(" ")
    if not tokens or any(not token for token in tokens):
        raise ValueError("Git identity name requires single-space-separated tokens")
    return value


def _canonical_git_ascii_email(value: str) -> str:
    encoded = value.encode("ascii", errors="strict")
    if not 3 <= len(encoded) <= 254:
        raise ValueError("Git identity email must contain 3..254 ASCII bytes")
    if any(byte < 0x21 or byte > 0x7E for byte in encoded) or "<" in value or ">" in value:
        raise ValueError("Git identity email contains a forbidden byte")
    if value.count("@") != 1:
        raise ValueError("Git identity email requires exactly one at-sign")
    local, domain = value.split("@")
    if (
        not local
        or not domain
        or local.startswith(".")
        or local.endswith(".")
        or domain.startswith(".")
        or domain.endswith(".")
        or ".." in local
        or ".." in domain
    ):
        raise ValueError("Git identity email has invalid dot placement")
    return value


CanonicalGitAsciiName: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_canonical_git_ascii_name),
]
CanonicalGitAsciiEmail: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_canonical_git_ascii_email),
]


def _bounded_canonical_text(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("canonical text must already be NFC")
    encoded = value.encode("utf-8", errors="strict")
    if not 1 <= len(encoded) <= 1_048_576:
        raise ValueError("canonical text must contain 1..1,048,576 UTF-8 bytes")
    if "\0" in value or "\r" in value:
        raise ValueError("canonical text must not contain NUL or CR")
    return value


BoundedCanonicalText: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_bounded_canonical_text),
]

StrictProtocolString: TypeAlias = Annotated[str, BeforeValidator(_strict_string)]


def _strict_canonical_base64(value: str) -> str:
    # 65,536 decoded bytes need at most 87,384 canonical padded Base64
    # characters.  Enforce that resource bound before asking binascii to
    # allocate the decoded buffer; the exact decoded-byte limit is checked
    # again below.
    if len(value) > 87_384:
        raise ValueError("encoded key material exceeds the 65,536-byte limit")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error):
        raise ValueError("value must be canonical standard base64") from None
    if not 1 <= len(decoded) <= 65_536:
        raise ValueError("decoded key material must contain 1..65,536 bytes")
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("value must be canonical padded standard base64")
    return value


StrictCanonicalBase64: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_strict_canonical_base64),
]


def _fingerprint(value: str) -> str:
    if (
        _SSH_FINGERPRINT_RE.fullmatch(value) is None
        and _OPENPGP_FINGERPRINT_RE.fullmatch(value) is None
    ):
        raise ValueError("invalid protocol signing fingerprint")
    return value


SigningFingerprintV1: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_fingerprint),
]


def _strict_true(value: object) -> bool:
    if type(value) is not bool or value is not True:
        raise ValueError("value must be the exact JSON boolean true")
    return True


StrictTrue: TypeAlias = Annotated[Literal[True], BeforeValidator(_strict_true)]


def _input_tag_ref(value: str) -> str:
    match = _INPUT_TAG_REF_RE.fullmatch(value)
    if match is None:
        raise ValueError("invalid benchmark input tag ref")
    _validate_tag_date(match.group(1))
    return value


def _companion_tag_ref(value: str) -> str:
    match = _COMPANION_TAG_REF_RE.fullmatch(value)
    if match is None:
        raise ValueError("invalid benchmark companion tag ref")
    _validate_tag_date(match.group(1))
    return value


def _validate_tag_date(value: str) -> None:
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        raise ValueError("tag ref contains an invalid calendar date") from None


InputTagRef: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_input_tag_ref),
]
CompanionTagRef: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_companion_tag_ref),
]


def _whole_second_timestamp(value: str) -> str:
    if _WHOLE_SECOND_UTC_RE.fullmatch(value) is None:
        raise ValueError("timestamp must use whole-second UTC RFC 3339 spelling")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError("timestamp is invalid") from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("timestamp is not canonically spelled")
    return value


WholeSecondTimestamp: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_whole_second_timestamp),
]


def _paired_refs(input_ref: str, companion_ref: str) -> bool:
    input_match = _INPUT_TAG_REF_RE.fullmatch(input_ref)
    companion_match = _COMPANION_TAG_REF_RE.fullmatch(companion_ref)
    return bool(
        input_match and companion_match and input_match.groups() == companion_match.groups()
    )


def _digest_payload(model: CapsuleModel, self_field: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        model.model_dump(mode="json", exclude={self_field}),
    )


class TagOperatorProjectionV1(CapsuleModel):
    operator_account_id: StrictPositiveInt
    operator_login: BoundedNonBlankString
    tagger_name: CanonicalGitAsciiName
    tagger_email: CanonicalGitAsciiEmail
    tag_operator_sha256: Sha256

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        expected = protocol_review_digest(
            "laconian-tag-operator-v1", _digest_payload(self, "tag_operator_sha256")
        )
        if self.tag_operator_sha256 != expected:
            raise ValueError("tag operator digest mismatch")
        return self


class TagOperatorRegistryV1(CapsuleModel):
    schema_version: Literal["TagOperatorRegistryV1"]
    repository_id: StrictPositiveInt
    operators: tuple[TagOperatorProjectionV1]
    tag_operator_registry_sha256: Sha256

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        if len(self.operators) != 1:
            raise ValueError("tag operator registry requires exactly one operator")
        expected = protocol_review_digest(
            "laconian-tag-operator-registry-v1",
            _digest_payload(self, "tag_operator_registry_sha256"),
        )
        if self.tag_operator_registry_sha256 != expected:
            raise ValueError("tag operator registry digest mismatch")
        return self


class TagRulesetRuleV1(CapsuleModel):
    type: Literal["creation", "update", "deletion"]
    parameters: None


class TagRulesetBypassActorV1(CapsuleModel):
    actor_id: StrictPositiveInt
    actor_type: Literal["User"]
    bypass_mode: Literal["always"]


class TagRulesetListEntryProjectionV1(CapsuleModel):
    ruleset_id: StrictPositiveInt


class TagRulesetListPageProjectionV1(CapsuleModel):
    schema_version: Literal["TagRulesetListPageProjectionV1"]
    repository_id: StrictPositiveInt
    page: StrictPositiveInt
    rulesets: tuple[TagRulesetListEntryProjectionV1, ...]
    tag_ruleset_list_page_projection_sha256: Sha256

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        expected = protocol_review_digest(
            "laconian-tag-ruleset-list-page-projection-v1",
            _digest_payload(self, "tag_ruleset_list_page_projection_sha256"),
        )
        if self.tag_ruleset_list_page_projection_sha256 != expected:
            raise ValueError("tag ruleset list-page projection digest mismatch")
        return self


class TagRulesetDetailProjectionV1(CapsuleModel):
    schema_version: Literal["TagRulesetDetailProjectionV1"]
    repository_id: StrictPositiveInt
    ruleset_id: StrictPositiveInt
    source_type: Literal["Repository"]
    source_id: StrictPositiveInt
    target: Literal["tag"]
    enforcement: Literal["active"]
    include_patterns: tuple[StrictProtocolString, ...]
    exclude_patterns: tuple[StrictProtocolString, ...]
    rules: tuple[TagRulesetRuleV1, ...]
    bypass_actors: tuple[TagRulesetBypassActorV1, ...]
    tag_ruleset_detail_projection_sha256: Sha256

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        if self.source_id != self.repository_id:
            raise ValueError("ruleset detail source ID must equal repository ID")
        expected = protocol_review_digest(
            "laconian-tag-ruleset-detail-projection-v1",
            _digest_payload(self, "tag_ruleset_detail_projection_sha256"),
        )
        if self.tag_ruleset_detail_projection_sha256 != expected:
            raise ValueError("tag ruleset detail projection digest mismatch")
        return self


class TagRulesetProjectionV1(CapsuleModel):
    semantic_role: Literal["creation_authorizer", "immutability"]
    ruleset_id: StrictPositiveInt
    source_type: Literal["Repository"]
    source_id: StrictPositiveInt
    target: Literal["tag"]
    enforcement: Literal["active"]
    include_patterns: tuple[StrictProtocolString, StrictProtocolString]
    exclude_patterns: tuple[()]
    rules: tuple[TagRulesetRuleV1, ...]
    bypass_actors: tuple[TagRulesetBypassActorV1, ...]


_TAG_INCLUDE_PATTERNS = (
    "refs/tags/benchmark-input-*",
    "refs/tags/benchmark-attestations-*",
)


class TagRulesetPolicyV1(CapsuleModel):
    schema_version: Literal["TagRulesetPolicyV1"]
    repository_id: StrictPositiveInt
    rulesets: tuple[TagRulesetProjectionV1, TagRulesetProjectionV1]
    tag_ruleset_policy_root: Sha256

    @model_validator(mode="after")
    def validate_closed_policy(self) -> Self:
        creation, immutability = self.rulesets
        if (creation.semantic_role, immutability.semantic_role) != (
            "creation_authorizer",
            "immutability",
        ):
            raise ValueError("tag rulesets require stable semantic order")
        if creation.ruleset_id == immutability.ruleset_id:
            raise ValueError("tag ruleset IDs must be distinct")
        if any(item.source_id != self.repository_id for item in self.rulesets):
            raise ValueError("ruleset source ID must equal repository ID")
        if any(
            item.include_patterns != _TAG_INCLUDE_PATTERNS or item.exclude_patterns != ()
            for item in self.rulesets
        ):
            raise ValueError("tag ruleset ref patterns mismatch")
        if (
            tuple((item.type, item.parameters) for item in creation.rules) != (("creation", None),)
            or len(creation.bypass_actors) != 1
        ):
            raise ValueError("creation ruleset must contain one creation rule and one bypass")
        if (
            tuple((item.type, item.parameters) for item in immutability.rules)
            != (("update", None), ("deletion", None))
            or immutability.bypass_actors != ()
        ):
            raise ValueError("immutability ruleset must forbid update/deletion bypass")
        expected = protocol_review_digest(
            "laconian-tag-ruleset-policy-v2",
            _digest_payload(self, "tag_ruleset_policy_root"),
        )
        if self.tag_ruleset_policy_root != expected:
            raise ValueError("tag ruleset policy root mismatch")
        return self


class InputTagMessageV1(CapsuleModel):
    schema_version: Literal["InputTagMessageV1"]
    input_tag_ref: InputTagRef
    companion_tag_ref: CompanionTagRef
    peeled_c0_oid: GitObjectId
    protocol_reviewer_registry_sha256: Sha256
    tag_operator_registry_sha256: Sha256
    tag_ruleset_policy_root: Sha256
    workflow_root: Sha256

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if not _paired_refs(self.input_tag_ref, self.companion_tag_ref):
            raise ValueError("input and companion tag refs require the same date/sequence")
        return self


class ProtocolAttestationTagMessageV1(CapsuleModel):
    schema_version: Literal["ProtocolAttestationTagMessageV1"]
    input_tag_ref: InputTagRef
    input_tag_oid: GitObjectId
    input_tag_object_sha256: Sha256
    companion_tag_ref: CompanionTagRef
    bundle_commit_oid: GitObjectId
    bundle_commit_object_sha256: Sha256
    protocol_attestation_bundle_sha256: Sha256
    protocol_attestations_root: Sha256
    tag_operator_registry_sha256: Sha256
    tag_ruleset_policy_root: Sha256

    @model_validator(mode="after")
    def validate_pair(self) -> Self:
        if not _paired_refs(self.input_tag_ref, self.companion_tag_ref):
            raise ValueError("input and companion tag refs require the same date/sequence")
        return self


class ProtocolBundleBuilderGitIdentityV1(CapsuleModel):
    schema_version: Literal["ProtocolBundleBuilderGitIdentityV1"]
    name_ascii: Literal["Laconian Protocol Bundle Builder"]
    email_ascii: Literal["laconian-protocol-bundle-builder@users.noreply.github.com"]
    protocol_bundle_builder_git_identity_sha256: Sha256

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        expected = protocol_review_digest(
            "laconian-protocol-bundle-builder-git-identity-v1",
            _digest_payload(self, "protocol_bundle_builder_git_identity_sha256"),
        )
        if self.protocol_bundle_builder_git_identity_sha256 != expected:
            raise ValueError("protocol bundle-builder identity digest mismatch")
        return self


class WorkflowInventoryMemberV1(CapsuleModel):
    path: RelativePosixPath
    sha256: Sha256


BENCHMARK_WORKFLOW_PATHS_V1: tuple[RelativePosixPath, ...] = (
    ".github/workflows/audit-pr-validate.yml",
    ".github/workflows/benchmark-analysis.yml",
    ".github/workflows/benchmark-audit.yml",
    ".github/workflows/benchmark-batch.yml",
    ".github/workflows/benchmark-collect-complete.yml",
    ".github/workflows/benchmark-dismiss-hold.yml",
    ".github/workflows/benchmark-docs-validate.yml",
    ".github/workflows/benchmark-evidence.yml",
    ".github/workflows/benchmark-finalize-invalid.yml",
    ".github/workflows/benchmark-hard-score.yml",
    ".github/workflows/benchmark-preflight.yml",
    ".github/workflows/benchmark-publication-state.yml",
    ".github/workflows/benchmark-publish.yml",
    ".github/workflows/benchmark-release.yml",
    ".github/workflows/publication-pr-validate.yml",
)


class WorkflowInventoryV1(CapsuleModel):
    schema_version: Literal["WorkflowInventoryV1"]
    members: tuple[
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
        WorkflowInventoryMemberV1,
    ]
    workflow_root: Sha256

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        if tuple(item.path for item in self.members) != BENCHMARK_WORKFLOW_PATHS_V1:
            raise ValueError("workflow member path inventory/order mismatch")
        expected = protocol_review_digest(
            "laconian-workflow-inventory-v1", _digest_payload(self, "workflow_root")
        )
        if self.workflow_root != expected:
            raise ValueError("workflow inventory root mismatch")
        return self


def build_workflow_inventory(
    *, c0_workflow_bytes: Mapping[RelativePosixPath, bytes]
) -> WorkflowInventoryV1:
    """Build the exact 15-member workflow inventory from verified C0 bytes."""

    if tuple(c0_workflow_bytes) != BENCHMARK_WORKFLOW_PATHS_V1:
        raise ValueError("C0 workflow mapping requires the exact literal path order")
    if any(type(value) is not bytes for value in c0_workflow_bytes.values()):
        raise ValueError("C0 workflow members must be exact bytes")
    payload: dict[str, object] = {
        "schema_version": "WorkflowInventoryV1",
        "members": [
            {"path": path, "sha256": hashlib.sha256(c0_workflow_bytes[path]).hexdigest()}
            for path in BENCHMARK_WORKFLOW_PATHS_V1
        ],
    }
    payload["workflow_root"] = protocol_review_digest("laconian-workflow-inventory-v1", payload)
    return WorkflowInventoryV1.model_validate(payload)


GITHUB_COMMIT_SIGNER_QUERY_V1 = """query ProtocolCommitSignature($owner: String!, $name: String!, \
$oid: GitObjectID!) {
  repository(owner: $owner, name: $name) {
    databaseId
    object(oid: $oid) {
      ... on Commit {
        oid
        signature {
          isValid
          state
          signer {
            databaseId
            login
          }
        }
      }
    }
  }
}
"""
GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1 = (
    "141ec2ce356c197073e0aeece28a804b56b8c31a615a3d36995c72ce2c9b3d7b"
)
assert hashlib.sha256(GITHUB_COMMIT_SIGNER_QUERY_V1.encode("utf-8")).hexdigest() == (
    GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1
)


class GitHubCommitVerificationProjectionV1(CapsuleModel):
    schema_version: Literal["GitHubCommitVerificationProjectionV1"]
    repository_id: StrictPositiveInt
    commit_oid: GitObjectId
    api_version: Literal["2022-11-28"]
    endpoint: BoundedNonBlankString
    verified: StrictTrue
    reason: Literal["valid"]
    payload: BoundedCanonicalText
    signature: BoundedCanonicalText
    verified_at: CanonicalTimestamp
    rest_projection_sha256: Sha256

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        endpoint_re = re.compile(
            r"^GET /repos/[^/\s]+/[^/\s]+/git/commits/" + re.escape(self.commit_oid) + r"$"
        )
        if endpoint_re.fullmatch(self.endpoint) is None:
            raise ValueError("GitHub REST commit endpoint mismatch")
        expected = protocol_review_digest(
            "laconian-github-commit-verification-projection-v1",
            _digest_payload(self, "rest_projection_sha256"),
        )
        if self.rest_projection_sha256 != expected:
            raise ValueError("GitHub REST projection digest mismatch")
        return self


class GitHubSignatureProjectionV1(CapsuleModel):
    schema_version: Literal["GitHubSignatureProjectionV1"]
    repository_id: StrictPositiveInt
    commit_oid: GitObjectId
    query_sha256: Sha256
    signer_database_id: StrictPositiveInt
    signer_login: BoundedNonBlankString
    is_valid: StrictTrue
    state: Literal["VALID"]
    graphql_projection_sha256: Sha256

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if self.query_sha256 != GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1:
            raise ValueError("GitHub GraphQL query digest mismatch")
        expected = protocol_review_digest(
            "laconian-github-signature-projection-v1",
            _digest_payload(self, "graphql_projection_sha256"),
        )
        if self.graphql_projection_sha256 != expected:
            raise ValueError("GitHub GraphQL projection digest mismatch")
        return self


class GitHubSignatureObservationReceiptV1(CapsuleModel):
    schema_version: Literal["GitHubSignatureObservationReceiptV1"]
    repository_id: StrictPositiveInt
    commit_oid: GitObjectId
    rest_projection_sha256: Sha256
    graphql_projection_sha256: Sha256
    observed_at: CanonicalTimestamp
    request_ids: tuple[BoundedNonBlankString, BoundedNonBlankString]
    etags: tuple[BoundedNonBlankString, BoundedNonBlankString]
    raw_response_sha256s: tuple[Sha256, Sha256]
    canonical_response_sha256s: tuple[Sha256, Sha256]
    tls_endpoint_identity: Literal["api.github.com:443"]
    github_signature_observation_receipt_sha256: Sha256

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        expected = protocol_review_digest(
            "laconian-github-signature-observation-receipt-v1",
            _digest_payload(self, "github_signature_observation_receipt_sha256"),
        )
        if self.github_signature_observation_receipt_sha256 != expected:
            raise ValueError("GitHub signature observation receipt digest mismatch")
        return self


class LocalSignatureVerificationReceiptV1(CapsuleModel):
    verified: StrictTrue
    signed_payload_sha256: Sha256
    signature_sha256: Sha256
    verifier_tool_sha256: Sha256
    verification_receipt_sha256: Sha256

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        expected = protocol_review_digest(
            "laconian-local-signature-verification-receipt-v1",
            _digest_payload(self, "verification_receipt_sha256"),
        )
        if self.verification_receipt_sha256 != expected:
            raise ValueError("local signature verification receipt digest mismatch")
        return self


class ProtocolReviewSigningKeyV1(CapsuleModel):
    role: ProtocolReviewRoleV1
    reviewer_numeric_account_id: StrictPositiveInt
    reviewer_login: BoundedNonBlankString
    verification_mode: Literal["ssh_sha256", "openpgp_fingerprint"]
    fingerprint: SigningFingerprintV1
    public_key_encoding: Literal[
        "openssh-ed25519-wire-v1",
        "openpgp-v4-ed25519-transferable-public-key-v1",
    ]
    public_key_base64: StrictCanonicalBase64
    public_key_sha256: Sha256

    @model_validator(mode="after")
    def validate_key(self) -> Self:
        validate_signature_mode_fingerprint(self.verification_mode, self.fingerprint)
        expected_encoding = (
            "openssh-ed25519-wire-v1"
            if self.verification_mode == "ssh_sha256"
            else "openpgp-v4-ed25519-transferable-public-key-v1"
        )
        if self.public_key_encoding != expected_encoding:
            raise ValueError("protocol signing-key mode/encoding mismatch")
        decoded = base64.b64decode(self.public_key_base64.encode("ascii"), validate=True)
        if hashlib.sha256(decoded).hexdigest() != self.public_key_sha256:
            raise ValueError("protocol signing-key byte digest mismatch")
        return self


class AuditReviewerSigningKeyV1(CapsuleModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        validate_default=True,
    )

    schema_version: Literal["AuditReviewerSigningKeyV1"]
    verification_mode: Literal["ssh_sha256", "openpgp_fingerprint"]
    fingerprint: SigningFingerprintV1
    author_name_ascii: CanonicalGitAsciiName
    author_email_ascii: CanonicalGitAsciiEmail
    committer_name_ascii: CanonicalGitAsciiName
    committer_email_ascii: CanonicalGitAsciiEmail
    public_key_encoding: Literal[
        "openssh-ed25519-wire-v1",
        "openpgp-v4-ed25519-transferable-public-key-v1",
    ]
    public_key_base64: StrictCanonicalBase64
    public_key_sha256: Sha256

    @model_validator(mode="after")
    def validate_key(self) -> Self:
        validate_signature_mode_fingerprint(self.verification_mode, self.fingerprint)
        expected_encoding = (
            "openssh-ed25519-wire-v1"
            if self.verification_mode == "ssh_sha256"
            else "openpgp-v4-ed25519-transferable-public-key-v1"
        )
        if self.public_key_encoding != expected_encoding:
            raise ValueError("audit signing-key mode/encoding mismatch")
        decoded = base64.b64decode(self.public_key_base64.encode("ascii"), validate=True)
        if hashlib.sha256(decoded).hexdigest() != self.public_key_sha256:
            raise ValueError("audit signing-key byte digest mismatch")
        actual_fingerprint = _signing_key_fingerprint(self.verification_mode, decoded)
        if actual_fingerprint != self.fingerprint:
            raise ValueError("audit signing-key fingerprint mismatch")
        return self


_PROTOCOL_SIGNATURE_ALGORITHM_PROFILE_V1 = (
    "ssh-ed25519-sshsig-git-sha512-or-openpgp-v4-ed25519-sha256-v1"
)
_PROTOCOL_SIGNATURE_VERIFIER_ENTRYPOINT_V1 = (
    "laconian_eval.benchmark.protocol_review:_verify_keyed_signature_v1"
)


class ProtocolReviewIdentityRegistryBundleV1(CapsuleModel):
    schema_version: Literal["ProtocolReviewIdentityRegistryBundleV1"]
    keys: tuple[ProtocolReviewSigningKeyV1, ...]
    verifier_source_path: Literal["src/laconian_eval/benchmark/protocol_review.py"]
    verifier_source_sha256: Sha256
    dependency_lock_path: Literal["uv.lock"]
    dependency_lock_sha256: Sha256
    verifier_dependency_inventory_root: Sha256
    protocol_signature_verifier_tool_sha256: Sha256
    identity_registry_bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        roles = tuple(item.role for item in self.keys)
        role_rank = {
            "statistical_method": 0,
            "blind_judge_audit_protocol": 1,
            "security_evidence": 2,
        }
        if roles != tuple(sorted(roles, key=role_rank.__getitem__)) or len(set(roles)) != len(
            roles
        ):
            raise ValueError("identity-registry keys require unique protocol-role order")
        if (
            len({item.reviewer_numeric_account_id for item in self.keys}) != len(self.keys)
            or len({item.reviewer_login for item in self.keys}) != len(self.keys)
            or len({item.fingerprint for item in self.keys}) != len(self.keys)
        ):
            raise ValueError("identity-registry key identities must be distinct")
        expected_tool = protocol_review_digest(
            "laconian-protocol-signature-verifier-tool-v1",
            {
                "algorithm_profile": _PROTOCOL_SIGNATURE_ALGORITHM_PROFILE_V1,
                "dependency_lock_path": self.dependency_lock_path,
                "dependency_lock_sha256": self.dependency_lock_sha256,
                "verifier_dependency_inventory_root": self.verifier_dependency_inventory_root,
                "entrypoint": _PROTOCOL_SIGNATURE_VERIFIER_ENTRYPOINT_V1,
                "verifier_source_path": self.verifier_source_path,
                "verifier_source_sha256": self.verifier_source_sha256,
            },
        )
        if self.protocol_signature_verifier_tool_sha256 != expected_tool:
            raise ValueError("protocol signature-verifier tool digest mismatch")
        expected_self = protocol_review_digest(
            "laconian-protocol-review-identity-registry-bundle-v1",
            _digest_payload(self, "identity_registry_bundle_sha256"),
        )
        if self.identity_registry_bundle_sha256 != expected_self:
            raise ValueError("protocol identity-registry bundle digest mismatch")
        return self


def validate_signature_mode_fingerprint(
    mode: SignatureVerificationModeV1,
    fingerprint: str | None,
    *,
    require_keyed: bool = False,
) -> None:
    if mode == "github_verified_commit":
        if fingerprint is not None or require_keyed:
            raise ValueError("GitHub verification requires null fingerprint")
    elif mode == "ssh_sha256":
        if fingerprint is None or _SSH_FINGERPRINT_RE.fullmatch(fingerprint) is None:
            raise ValueError("SSH verification requires an exact SHA256 fingerprint")
    elif fingerprint is None or _OPENPGP_FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise ValueError("OpenPGP verification requires an uppercase primary-key fingerprint")


class ReviewerAccountBindingV1(CapsuleModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        validate_default=True,
    )

    reviewer_id: BoundedNonBlankString
    reviewer_numeric_account_id: StrictPositiveInt
    reviewer_login: BoundedNonBlankString
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: SigningFingerprintV1 | None
    signing_key: AuditReviewerSigningKeyV1 | None
    role: Literal["audit_reviewer"]

    @model_validator(mode="before")
    @classmethod
    def reject_foreign_signing_key_owner(cls, value: object) -> object:
        if isinstance(value, Mapping):
            signing_key = value.get("signing_key")
            if isinstance(signing_key, BaseModel) and type(signing_key) is not (
                AuditReviewerSigningKeyV1
            ):
                raise ValueError("audit reviewer binding contains a foreign signing-key owner")
        return value

    @model_validator(mode="after")
    def validate_verification_mode(self) -> Self:
        validate_signature_mode_fingerprint(self.verification_mode, self.signing_fingerprint)
        if self.verification_mode == "github_verified_commit":
            if self.signing_key is not None:
                raise ValueError("GitHub audit verification requires a null signing key")
            return self
        if type(self.signing_key) is not AuditReviewerSigningKeyV1:
            raise ValueError("keyed audit verification requires an exact audit signing key")
        signing_key = _class_bound_revalidate(self.signing_key, AuditReviewerSigningKeyV1)
        if (
            signing_key.verification_mode != self.verification_mode
            or signing_key.fingerprint != self.signing_fingerprint
        ):
            raise ValueError("audit reviewer binding signing-key identity mismatch")
        return self


class AuditReviewerRegistryV1(CapsuleModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        validate_default=True,
    )

    schema_version: Literal["benchmark-reviewer-registry-v2"]
    reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1]
    audit_reviewer_registry_sha256: Sha256

    @field_serializer("reviewers")
    def serialize_reviewer_pair(
        self,
        reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
    ) -> list[dict[str, object]]:
        return [
            cast(dict[str, object], reviewer.model_dump(mode="json"))
            for reviewer in reviewers
        ]

    @field_validator("reviewers", mode="before")
    @classmethod
    def require_exact_reviewer_pair(cls, value: object, info: ValidationInfo) -> object:
        active: set[int] = set()
        completed: set[int] = set()
        remaining_nodes = _EXACT_MODEL_PREFLIGHT_NODE_LIMIT

        def require_plain_serialized_tree(candidate: object, depth: int = 0) -> None:
            nonlocal remaining_nodes
            if depth > _EXACT_MODEL_PREFLIGHT_DEPTH_LIMIT:
                raise TypeError("serialized audit reviewer graph exceeds its nesting limit")
            remaining_nodes -= 1
            if remaining_nodes < 0:
                raise TypeError("serialized audit reviewer graph exceeds its node limit")
            if isinstance(candidate, BaseModel):
                raise TypeError(
                    "serialized audit reviewer arrays reject nested model owners"
                )
            if candidate is None or type(candidate) in {str, int, bool}:
                return
            if type(candidate) not in {dict, list}:
                raise TypeError(
                    "serialized audit reviewer arrays require exact JSON value owners"
                )
            identity = id(candidate)
            if identity in active:
                raise TypeError("serialized audit reviewer graph contains an owner cycle")
            if identity in completed:
                return
            active.add(identity)
            try:
                if type(candidate) is dict:
                    for key, item in cast(dict[object, object], candidate).items():
                        if type(key) is not str:
                            raise TypeError(
                                "serialized audit reviewer objects require exact string keys"
                            )
                        require_plain_serialized_tree(item, depth + 1)
                else:
                    for item in cast(list[object], candidate):
                        require_plain_serialized_tree(item, depth + 1)
            finally:
                active.remove(identity)
            completed.add(identity)

        if type(value) is list:
            values = cast(list[object], value)
            if len(values) != 2:
                raise TypeError("serialized audit reviewers require exactly two object payloads")
            if any(isinstance(item, BaseModel) for item in values) or any(
                type(item) is not dict for item in values
            ):
                raise TypeError(
                    "serialized audit reviewer arrays require exact object payloads"
                )
            require_plain_serialized_tree(values)
            # Canonical JSON is duplicate-key checked before the surrounding durable owner calls
            # ``model_validate``.  Its array therefore arrives here as a list of plain mappings;
            # admit only that serialized shape, never a Python list of authority-bearing models.
            return tuple(values)
        if info.mode == "json":
            raise TypeError("JSON audit reviewers require one exact array payload")
        if type(value) is not tuple:
            raise TypeError("audit reviewers require an exact tuple owner")
        if len(cast(tuple[object, ...], value)) != 2:
            raise TypeError("audit reviewers require exactly two reviewer owners")
        for item in cast(tuple[object, ...], value):
            if type(item) is not ReviewerAccountBindingV1:
                raise TypeError("expected exact nested ReviewerAccountBindingV1 owner")
            _preflight_exact_model_owners_v1(item, ReviewerAccountBindingV1)
        return value

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        if any(type(item) is not ReviewerAccountBindingV1 for item in self.reviewers):
            raise ValueError("audit registry contains a foreign reviewer-binding owner")
        for reviewer in self.reviewers:
            _class_bound_revalidate(reviewer, ReviewerAccountBindingV1)
        keys = tuple(item.reviewer_id.encode("utf-8") for item in self.reviewers)
        if keys != tuple(sorted(keys)) or len(set(keys)) != 2:
            raise ValueError("audit reviewer IDs must be distinct and bytewise ordered")
        if (
            len({item.reviewer_numeric_account_id for item in self.reviewers}) != 2
            or len({item.reviewer_login for item in self.reviewers}) != 2
        ):
            raise ValueError("audit reviewer identities must be distinct")
        fingerprints = tuple(
            item.signing_fingerprint
            for item in self.reviewers
            if item.signing_fingerprint is not None
        )
        key_hashes = tuple(
            item.signing_key.public_key_sha256
            for item in self.reviewers
            if item.signing_key is not None
        )
        if len(set(fingerprints)) != len(fingerprints) or len(set(key_hashes)) != len(
            key_hashes
        ):
            raise ValueError("audit reviewer keyed identities must be distinct")
        if self.audit_reviewer_registry_sha256 != compute_audit_reviewer_registry_sha256(
            self.reviewers
        ):
            raise ValueError("audit reviewer registry digest mismatch")
        return self


class ProtocolReviewerBindingV1(CapsuleModel):
    role: ProtocolReviewRoleV1
    reviewer_numeric_account_id: StrictPositiveInt
    reviewer_login: BoundedNonBlankString
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: SigningFingerprintV1 | None
    author_name_ascii: CanonicalGitAsciiName
    author_email_ascii: CanonicalGitAsciiEmail
    committer_name_ascii: CanonicalGitAsciiName
    committer_email_ascii: CanonicalGitAsciiEmail

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        validate_signature_mode_fingerprint(
            self.verification_mode,
            self.signing_fingerprint,
            require_keyed=self.role == "security_evidence",
        )
        return self


class ProtocolReviewerRegistryV1(CapsuleModel):
    schema_version: Literal["benchmark-protocol-reviewer-registry-v1"]
    reviewers: tuple[
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
    ]
    protocol_reviewer_registry_sha256: Sha256

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        if tuple(item.role for item in self.reviewers) != expected_roles:
            raise ValueError("protocol reviewer role order mismatch")
        if (
            len({item.reviewer_numeric_account_id for item in self.reviewers}) != 3
            or len({item.reviewer_login for item in self.reviewers}) != 3
        ):
            raise ValueError("protocol reviewer identities must be distinct")
        if self.protocol_reviewer_registry_sha256 != compute_protocol_reviewer_registry_sha256(
            self.reviewers
        ):
            raise ValueError("protocol reviewer registry digest mismatch")
        return self


class ProtocolReviewVerificationError(ValueError):
    """Raised when raw protocol-review evidence does not reconstruct the closed DAG."""


_ProtocolModelT = TypeVar("_ProtocolModelT", bound=CapsuleModel)


def _annotation_model_owners(annotation: object) -> tuple[type[BaseModel], ...]:
    owners: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        owners.append(annotation)
    origin = get_origin(annotation)
    if origin in {tuple, list, dict, Mapping, Sequence}:
        return tuple(owners)
    for argument in get_args(annotation):
        for owner in _annotation_model_owners(argument):
            if owner not in owners:
                owners.append(owner)
    return tuple(owners)


def _annotation_allows_none(annotation: object) -> bool:
    return annotation is type(None) or any(
        _annotation_allows_none(argument) for argument in get_args(annotation)
    )


def _annotation_container_owners(annotation: object) -> tuple[type[object], ...]:
    origin = get_origin(annotation)
    if origin in {tuple, list, dict}:
        return (origin,)
    owners: list[type[object]] = []
    for argument in get_args(annotation):
        for owner in _annotation_container_owners(argument):
            if owner not in owners:
                owners.append(owner)
    return tuple(owners)


def _tuple_item_annotation(annotation: object, ordinal: int, length: int) -> object:
    if get_origin(annotation) is tuple:
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return arguments[0]
        if len(arguments) == length:
            return arguments[ordinal]
    return object


def _mapping_value_annotation(annotation: object) -> object:
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in {dict, Mapping} and len(arguments) == 2:
        return arguments[1]
    return object


_EXACT_MODEL_PREFLIGHT_DEPTH_LIMIT = 128
_EXACT_MODEL_PREFLIGHT_NODE_LIMIT = 262_144


def _preflight_exact_model_owners_v1(
    value: object,
    expected_annotation: object,
    *,
    slot: str = "model",
    active: set[int] | None = None,
    completed: set[tuple[int, int]] | None = None,
    depth: int = 0,
    remaining_nodes: list[int] | None = None,
) -> None:
    """Reject nested Pydantic substitutes before validation can normalize them."""

    if depth > _EXACT_MODEL_PREFLIGHT_DEPTH_LIMIT:
        raise TypeError("class-bound model graph exceeds its nesting limit")
    node_budget = (
        [_EXACT_MODEL_PREFLIGHT_NODE_LIMIT]
        if remaining_nodes is None
        else remaining_nodes
    )
    node_budget[0] -= 1
    if node_budget[0] < 0:
        raise TypeError("class-bound model graph exceeds its node limit")

    expected_containers = _annotation_container_owners(expected_annotation)
    if (
        expected_containers
        and type(value) not in expected_containers
        and not (value is None and _annotation_allows_none(expected_annotation))
    ):
        expected = " or ".join(owner.__name__ for owner in expected_containers)
        raise TypeError(
            f"foreign {slot.replace('_', '-')} container owner; "
            f"expected exact {expected} owner"
        )
    active_ids = set() if active is None else active
    completed_keys = set() if completed is None else completed
    tracked = isinstance(value, BaseModel) or type(value) in {tuple, list, dict}
    identity = id(value)
    completed_key = (identity, id(expected_annotation))
    if tracked:
        if identity in active_ids:
            raise TypeError("class-bound model graph contains an owner cycle")
        if completed_key in completed_keys:
            return
        active_ids.add(identity)
    try:
        expected_models = _annotation_model_owners(expected_annotation)
        if (
            expected_models
            and not isinstance(value, BaseModel)
            and not (value is None and _annotation_allows_none(expected_annotation))
        ):
            expected = " or ".join(owner.__name__ for owner in expected_models)
            raise TypeError(
                f"foreign {slot.replace('_', '-')} owner; "
                f"expected exact nested {expected} owner"
            )
        if isinstance(value, BaseModel):
            if type(value) not in expected_models:
                expected = (
                    " or ".join(owner.__name__ for owner in expected_models)
                    or "declared model"
                )
                raise TypeError(
                    f"foreign {slot.replace('_', '-')} owner; "
                    f"expected exact nested {expected} owner"
                )
            owner = type(value)
            for name, field in owner.model_fields.items():
                try:
                    child = object.__getattribute__(value, name)
                except AttributeError as error:
                    raise TypeError(
                        f"class-bound model graph is missing field {name}"
                    ) from error
                _preflight_exact_model_owners_v1(
                    child,
                    field.annotation,
                    slot=name,
                    active=active_ids,
                    completed=completed_keys,
                    depth=depth + 1,
                    remaining_nodes=node_budget,
                )
            return
        if type(value) in {tuple, list}:
            values = cast(tuple[object, ...] | list[object], value)
            for ordinal, item in enumerate(values):
                _preflight_exact_model_owners_v1(
                    item,
                    _tuple_item_annotation(expected_annotation, ordinal, len(values)),
                    slot=f"{slot} item",
                    active=active_ids,
                    completed=completed_keys,
                    depth=depth + 1,
                    remaining_nodes=node_budget,
                )
            return
        if type(value) is dict:
            mapping = cast(dict[object, object], value)
            child_annotation = _mapping_value_annotation(expected_annotation)
            for item in mapping.values():
                _preflight_exact_model_owners_v1(
                    item,
                    child_annotation,
                    slot=f"{slot} value",
                    active=active_ids,
                    completed=completed_keys,
                    depth=depth + 1,
                    remaining_nodes=node_budget,
                )
    finally:
        if tracked:
            active_ids.remove(identity)
            completed_keys.add(completed_key)


def _class_bound_revalidate(
    value: _ProtocolModelT, expected_type: type[_ProtocolModelT]
) -> _ProtocolModelT:
    if type(value) is not expected_type:
        raise ProtocolReviewVerificationError(
            f"expected exact {expected_type.__name__}, not a substitute instance"
        )
    _preflight_exact_model_owners_v1(value, expected_type)
    return expected_type.model_validate(value)


def _validated_audit_reviewers(
    reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
) -> tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1]:
    if type(reviewers) is not tuple or len(reviewers) != 2:
        raise ValueError("audit reviewer registry requires an exact two-entry tuple")
    validated = cast(
        tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
        tuple(_class_bound_revalidate(item, ReviewerAccountBindingV1) for item in reviewers),
    )
    reviewer_ids = tuple(item.reviewer_id for item in validated)
    if reviewer_ids != tuple(sorted(reviewer_ids, key=str.encode)) or len(set(reviewer_ids)) != 2:
        raise ValueError("audit reviewer IDs must be distinct and bytewise ordered")
    if (
        len({item.reviewer_numeric_account_id for item in validated}) != 2
        or len({item.reviewer_login for item in validated}) != 2
    ):
        raise ValueError("audit reviewer identities must be distinct")
    fingerprints = tuple(
        item.signing_fingerprint for item in validated if item.signing_fingerprint is not None
    )
    key_hashes = tuple(
        item.signing_key.public_key_sha256
        for item in validated
        if item.signing_key is not None
    )
    if len(set(fingerprints)) != len(fingerprints) or len(set(key_hashes)) != len(key_hashes):
        raise ValueError("audit reviewer keyed identities must be distinct")
    return validated


def _validated_protocol_reviewers(
    reviewers: tuple[
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
    ],
) -> tuple[
    ProtocolReviewerBindingV1,
    ProtocolReviewerBindingV1,
    ProtocolReviewerBindingV1,
]:
    if type(reviewers) is not tuple or len(reviewers) != 3:
        raise ValueError("protocol reviewer registry requires an exact three-entry tuple")
    validated = cast(
        tuple[
            ProtocolReviewerBindingV1,
            ProtocolReviewerBindingV1,
            ProtocolReviewerBindingV1,
        ],
        tuple(_class_bound_revalidate(item, ProtocolReviewerBindingV1) for item in reviewers),
    )
    expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    if tuple(item.role for item in validated) != expected_roles:
        raise ValueError("protocol reviewer role order mismatch")
    if (
        len({item.reviewer_numeric_account_id for item in validated}) != 3
        or len({item.reviewer_login for item in validated}) != 3
    ):
        raise ValueError("protocol reviewer identities must be distinct")
    return validated


def canonical_reviewer_registry_bytes(
    reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
) -> bytes:
    reviewers = _validated_audit_reviewers(reviewers)
    return canonical_json_v1(
        {
            "schema_version": "benchmark-reviewer-registry-v2",
            "reviewers": [item.model_dump(mode="json") for item in reviewers],
        }
    )


def compute_audit_reviewer_registry_sha256(
    reviewers: tuple[ReviewerAccountBindingV1, ReviewerAccountBindingV1],
) -> str:
    return hashlib.sha256(canonical_reviewer_registry_bytes(reviewers)).hexdigest()


def canonical_protocol_reviewer_registry_bytes(
    reviewers: tuple[
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
    ],
) -> bytes:
    reviewers = _validated_protocol_reviewers(reviewers)
    return canonical_json_v1(
        {
            "schema_version": "benchmark-protocol-reviewer-registry-v1",
            "reviewers": [item.model_dump(mode="json") for item in reviewers],
        }
    )


def compute_protocol_reviewer_registry_sha256(
    reviewers: tuple[
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
        ProtocolReviewerBindingV1,
    ],
) -> str:
    return hashlib.sha256(canonical_protocol_reviewer_registry_bytes(reviewers)).hexdigest()


ProtocolSubjectKindV1 = Literal[
    "corpus_case_root",
    "estimand_protocol_sha256",
    "statistical_protocol_sha256",
    "bootstrap_protocol_sha256",
    "outcome_classification_protocol_sha256",
    "false_fail_sensitivity_protocol_sha256",
    "hard_score_protocol_sha256",
    "judge_prompt_sha256",
    "judge_schema_sha256",
    "audit_sampling_protocol_sha256",
    "audit_commit_reveal_protocol_sha256",
    "audit_adjudication_protocol_sha256",
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
]

PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1: Mapping[
    ProtocolReviewRoleV1, tuple[ProtocolSubjectKindV1, ...]
] = MappingProxyType(
    {
        "statistical_method": (
            "corpus_case_root",
            "estimand_protocol_sha256",
            "statistical_protocol_sha256",
            "bootstrap_protocol_sha256",
            "outcome_classification_protocol_sha256",
            "false_fail_sensitivity_protocol_sha256",
        ),
        "blind_judge_audit_protocol": (
            "hard_score_protocol_sha256",
            "judge_prompt_sha256",
            "judge_schema_sha256",
            "audit_sampling_protocol_sha256",
            "audit_commit_reveal_protocol_sha256",
            "audit_adjudication_protocol_sha256",
        ),
        "security_evidence": (
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
        ),
    }
)


class ProtocolReviewSubjectV1(CapsuleModel):
    kind: ProtocolSubjectKindV1
    sha256: Sha256


class ProtocolReviewStatementV1(CapsuleModel):
    schema_version: Literal["ProtocolReviewStatementV1"]
    role: ProtocolReviewRoleV1
    protocol_registry_sha256: Sha256
    reviewer_numeric_account_id: StrictPositiveInt
    reviewer_login: BoundedNonBlankString
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: SigningFingerprintV1 | None
    input_tag_ref: InputTagRef
    input_tag_oid: GitObjectId
    input_tag_object_sha256: Sha256
    peeled_c0_oid: GitObjectId
    peeled_c0_sha256: Sha256
    workflow_root: Sha256
    subjects: tuple[ProtocolReviewSubjectV1, ...]
    subject_root: Sha256
    signed_at: WholeSecondTimestamp
    statement_sha256: Sha256

    @model_validator(mode="after")
    def validate_statement(self) -> Self:
        expected_subjects = PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1[self.role]
        if tuple(item.kind for item in self.subjects) != expected_subjects:
            raise ValueError("protocol statement subject inventory/order mismatch")
        validate_signature_mode_fingerprint(
            self.verification_mode,
            self.signing_fingerprint,
            require_keyed=self.role == "security_evidence",
        )
        expected_subject_root = protocol_review_digest(
            "laconian-protocol-review-subjects-root-v1",
            [item.model_dump(mode="json") for item in self.subjects],
        )
        if self.subject_root != expected_subject_root:
            raise ValueError("protocol statement subject root mismatch")
        expected = protocol_review_digest(
            "laconian-protocol-review-statement-v1",
            _digest_payload(self, "statement_sha256"),
        )
        if self.statement_sha256 != expected:
            raise ValueError("protocol statement digest mismatch")
        return self


class GitHubVerifiedCommitEvidenceV1(CapsuleModel):
    schema_version: Literal["GitHubVerifiedCommitEvidenceV1"]
    verification_mode: Literal["github_verified_commit"]
    commit_oid: GitObjectId
    commit_object_sha256: Sha256
    parent_commit_oid: GitObjectId
    statement_path: RelativePosixPath
    github_rest_verification: GitHubCommitVerificationProjectionV1
    github_graphql_signature: GitHubSignatureProjectionV1

    @model_validator(mode="after")
    def validate_projection_links(self) -> Self:
        _validate_signature_projection_links(self)
        return self


class SSHVerifiedCommitEvidenceV1(CapsuleModel):
    schema_version: Literal["SSHVerifiedCommitEvidenceV1"]
    verification_mode: Literal["ssh_sha256"]
    commit_oid: GitObjectId
    commit_object_sha256: Sha256
    parent_commit_oid: GitObjectId
    statement_path: RelativePosixPath
    github_rest_verification: GitHubCommitVerificationProjectionV1
    github_graphql_signature: GitHubSignatureProjectionV1
    fingerprint: Annotated[
        str, BeforeValidator(_strict_string), AfterValidator(_canonical_ssh_fingerprint)
    ]
    keyring_sha256: Sha256
    local_signature_verification: LocalSignatureVerificationReceiptV1

    @model_validator(mode="after")
    def validate_projection_links(self) -> Self:
        _validate_signature_projection_links(self)
        return self


def _canonical_ssh_fingerprint(value: str) -> str:
    if _SSH_FINGERPRINT_RE.fullmatch(value) is None:
        raise ValueError("invalid SSH SHA256 fingerprint")
    return value


def _canonical_openpgp_fingerprint(value: str) -> str:
    if _OPENPGP_FINGERPRINT_RE.fullmatch(value) is None:
        raise ValueError("invalid OpenPGP fingerprint")
    return value


class OpenPGPVerifiedCommitEvidenceV1(CapsuleModel):
    schema_version: Literal["OpenPGPVerifiedCommitEvidenceV1"]
    verification_mode: Literal["openpgp_fingerprint"]
    commit_oid: GitObjectId
    commit_object_sha256: Sha256
    parent_commit_oid: GitObjectId
    statement_path: RelativePosixPath
    github_rest_verification: GitHubCommitVerificationProjectionV1
    github_graphql_signature: GitHubSignatureProjectionV1
    fingerprint: Annotated[
        str,
        BeforeValidator(_strict_string),
        AfterValidator(_canonical_openpgp_fingerprint),
    ]
    keyring_sha256: Sha256
    local_signature_verification: LocalSignatureVerificationReceiptV1

    @model_validator(mode="after")
    def validate_projection_links(self) -> Self:
        _validate_signature_projection_links(self)
        return self


SignatureEvidenceV1 = Annotated[
    GitHubVerifiedCommitEvidenceV1 | SSHVerifiedCommitEvidenceV1 | OpenPGPVerifiedCommitEvidenceV1,
    Field(discriminator="verification_mode"),
]


@dataclass(frozen=True, slots=True)
class ProtocolSignatureEvidenceSourceV1:
    """Exact provider bytes plus the evidence they must freshly reconstruct."""

    observation_receipt: GitHubSignatureObservationReceiptV1
    signature_evidence: (
        GitHubVerifiedCommitEvidenceV1
        | SSHVerifiedCommitEvidenceV1
        | OpenPGPVerifiedCommitEvidenceV1
    )
    raw_response_bytes: tuple[bytes, bytes]
    canonical_response_bytes: tuple[bytes, bytes]

    def __post_init__(self) -> None:
        if type(self.observation_receipt) is not GitHubSignatureObservationReceiptV1:
            raise TypeError("signature source requires an exact observation receipt")
        if type(self.signature_evidence) not in {
            GitHubVerifiedCommitEvidenceV1,
            SSHVerifiedCommitEvidenceV1,
            OpenPGPVerifiedCommitEvidenceV1,
        }:
            raise TypeError("signature source requires exact mode-discriminated evidence")
        for label, values in (
            ("raw", self.raw_response_bytes),
            ("canonical", self.canonical_response_bytes),
        ):
            if type(values) is not tuple or len(values) != 2:
                raise TypeError(f"signature source {label} bytes require an exact two-tuple")
            if any(type(value) is not bytes for value in values):
                raise TypeError(f"signature source {label} members must be exact bytes")
            if any(not 1 <= len(value) <= 1_048_576 for value in values):
                raise ValueError(
                    f"signature source {label} members must contain 1..1,048,576 bytes"
                )


def _validate_signature_projection_links(
    evidence: GitHubVerifiedCommitEvidenceV1
    | SSHVerifiedCommitEvidenceV1
    | OpenPGPVerifiedCommitEvidenceV1,
) -> None:
    rest = evidence.github_rest_verification
    graphql = evidence.github_graphql_signature
    if rest.commit_oid != evidence.commit_oid or graphql.commit_oid != evidence.commit_oid:
        raise ValueError("signature projection commit identity mismatch")
    if rest.repository_id != graphql.repository_id:
        raise ValueError("signature projection repository identity mismatch")


class VerifiedProtocolAttestationV1(CapsuleModel):
    schema_version: Literal["VerifiedProtocolAttestationV1"]
    statement: ProtocolReviewStatementV1
    signature_evidence: SignatureEvidenceV1
    attestation_sha256: Sha256

    @model_validator(mode="after")
    def validate_attestation(self) -> Self:
        evidence = self.signature_evidence
        statement = self.statement
        if evidence.verification_mode != statement.verification_mode:
            raise ValueError("attestation verification mode mismatch")
        if (
            evidence.github_graphql_signature.signer_database_id
            != statement.reviewer_numeric_account_id
            or evidence.github_graphql_signature.signer_login != statement.reviewer_login
        ):
            raise ValueError("attestation signer identity mismatch")
        expected_path = _statement_path(statement.input_tag_ref, statement.role)
        if evidence.statement_path != expected_path:
            raise ValueError("attestation statement path mismatch")
        if isinstance(evidence, (SSHVerifiedCommitEvidenceV1, OpenPGPVerifiedCommitEvidenceV1)):
            if evidence.fingerprint != statement.signing_fingerprint:
                raise ValueError("attestation keyed fingerprint mismatch")
        elif statement.signing_fingerprint is not None:
            raise ValueError("GitHub-only attestation requires null fingerprint")
        expected = protocol_review_digest(
            "laconian-verified-protocol-attestation-v1",
            _digest_payload(self, "attestation_sha256"),
        )
        if self.attestation_sha256 != expected:
            raise ValueError("verified protocol attestation digest mismatch")
        return self


def compute_protocol_attestations_root(
    attestations: tuple[
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
    ],
) -> str:
    if type(attestations) is not tuple or len(attestations) != 3:
        raise ValueError("protocol attestation root requires an exact three-entry tuple")
    attestations = cast(
        tuple[
            VerifiedProtocolAttestationV1,
            VerifiedProtocolAttestationV1,
            VerifiedProtocolAttestationV1,
        ],
        tuple(
            _class_bound_revalidate(item, VerifiedProtocolAttestationV1) for item in attestations
        ),
    )
    expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    if tuple(item.statement.role for item in attestations) != expected_roles:
        raise ValueError("protocol attestation root role order mismatch")
    if (
        len({item.attestation_sha256 for item in attestations}) != 3
        or len({item.signature_evidence.commit_oid for item in attestations}) != 3
    ):
        raise ValueError("protocol attestations must bind three distinct envelopes and commits")
    campaign_bindings = {
        (
            item.statement.protocol_registry_sha256,
            item.statement.input_tag_ref,
            item.statement.input_tag_oid,
            item.statement.input_tag_object_sha256,
            item.statement.peeled_c0_oid,
            item.statement.peeled_c0_sha256,
            item.statement.workflow_root,
        )
        for item in attestations
    }
    if len(campaign_bindings) != 1:
        raise ValueError("protocol attestations must bind one common campaign prefix")
    return protocol_review_digest(
        "laconian-verified-protocol-attestations-root-v1",
        [item.model_dump(mode="json") for item in attestations],
    )


class ProtocolAttestationBundleV1(CapsuleModel):
    schema_version: Literal["ProtocolAttestationBundleV1"]
    protocol_registry_sha256: Sha256
    input_tag_ref: InputTagRef
    input_tag_oid: GitObjectId
    input_tag_object_sha256: Sha256
    peeled_c0_oid: GitObjectId
    peeled_c0_sha256: Sha256
    workflow_root: Sha256
    attestations: tuple[
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
    ]
    protocol_attestations_root: Sha256
    protocol_attestation_bundle_sha256: Sha256

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        root = compute_protocol_attestations_root(self.attestations)
        if self.protocol_attestations_root != root:
            raise ValueError("protocol bundle attestation root mismatch")
        for item in self.attestations:
            statement = item.statement
            if (
                statement.protocol_registry_sha256 != self.protocol_registry_sha256
                or statement.input_tag_ref != self.input_tag_ref
                or statement.input_tag_oid != self.input_tag_oid
                or statement.input_tag_object_sha256 != self.input_tag_object_sha256
                or statement.peeled_c0_oid != self.peeled_c0_oid
                or statement.peeled_c0_sha256 != self.peeled_c0_sha256
                or statement.workflow_root != self.workflow_root
            ):
                raise ValueError("protocol bundle statement authority mismatch")
        expected = protocol_review_digest(
            "laconian-protocol-attestation-bundle-v1",
            _digest_payload(self, "protocol_attestation_bundle_sha256"),
        )
        if self.protocol_attestation_bundle_sha256 != expected:
            raise ValueError("protocol attestation bundle digest mismatch")
        return self


class ProtocolReviewerCommitV1(CapsuleModel):
    role: ProtocolReviewRoleV1
    commit_oid: GitObjectId
    commit_object_sha256: Sha256


class ProtocolAttestationTagBindingV1(CapsuleModel):
    schema_version: Literal["ProtocolAttestationTagBindingV1"]
    input_tag_ref: InputTagRef
    input_tag_oid: GitObjectId
    input_tag_object_sha256: Sha256
    peeled_c0_oid: GitObjectId
    peeled_c0_sha256: Sha256
    reviewer_commits: tuple[
        ProtocolReviewerCommitV1,
        ProtocolReviewerCommitV1,
        ProtocolReviewerCommitV1,
    ]
    bundle_commit_oid: GitObjectId
    bundle_commit_object_sha256: Sha256
    companion_tag_ref: CompanionTagRef
    companion_tag_oid: GitObjectId
    companion_tag_object_sha256: Sha256
    protocol_registry_sha256: Sha256
    workflow_root: Sha256
    protocol_attestations_root: Sha256
    protocol_attestation_bundle_sha256: Sha256
    object_closure_root: Sha256
    tag_operator_registry_sha256: Sha256
    tag_ruleset_policy_root: Sha256
    protocol_attestation_tag_binding_sha256: Sha256

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        if tuple(item.role for item in self.reviewer_commits) != expected_roles:
            raise ValueError("reviewer commit role order mismatch")
        if len({item.commit_oid for item in self.reviewer_commits}) != 3:
            raise ValueError("reviewer commits must be distinct")
        if not _paired_refs(self.input_tag_ref, self.companion_tag_ref):
            raise ValueError("tag-binding refs require the same date/sequence")
        expected = protocol_review_digest(
            "laconian-protocol-attestation-tag-binding-v1",
            _digest_payload(self, "protocol_attestation_tag_binding_sha256"),
        )
        if self.protocol_attestation_tag_binding_sha256 != expected:
            raise ValueError("protocol attestation tag-binding digest mismatch")
        return self


class TagRulesetRequestTargetV1(CapsuleModel):
    method: Literal["GET"]
    path_and_query: BoundedNonBlankString
    accept_header: Literal["Accept: application/vnd.github+json"]
    api_version_header: Literal["X-GitHub-Api-Version: 2022-11-28"]

    @model_validator(mode="after")
    def validate_path_and_query(self) -> Self:
        list_match = _GITHUB_RULESET_LIST_TARGET_RE.fullmatch(self.path_and_query)
        detail_match = _GITHUB_RULESET_DETAIL_TARGET_RE.fullmatch(self.path_and_query)
        match = list_match or detail_match
        if match is None:
            raise ValueError("tag ruleset request target path/query mismatch")
        repo = match.group("repo")
        if repo in {".", ".."} or repo.casefold().endswith(".git"):
            raise ValueError("tag ruleset request target repository is invalid")
        return self


class TagRulesetObservationReceiptV1(CapsuleModel):
    schema_version: Literal["TagRulesetObservationReceiptV1"]
    repository_id: StrictPositiveInt
    ruleset_ids: tuple[StrictPositiveInt, StrictPositiveInt]
    tag_ruleset_policy_root: Sha256
    observed_at: CanonicalTimestamp
    request_targets: tuple[TagRulesetRequestTargetV1, ...]
    request_ids: tuple[BoundedNonBlankString, ...]
    etags: tuple[BoundedNonBlankString, ...]
    raw_response_sha256s: tuple[Sha256, ...]
    canonical_response_sha256s: tuple[Sha256, ...]
    pagination_root: Sha256
    tag_ruleset_observation_receipt_sha256: Sha256

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.ruleset_ids[0] == self.ruleset_ids[1]:
            raise ValueError("ruleset observation requires two distinct IDs")
        lengths = {
            len(self.request_targets),
            len(self.request_ids),
            len(self.etags),
            len(self.raw_response_sha256s),
            len(self.canonical_response_sha256s),
        }
        if lengths != {len(self.request_ids)} or len(self.request_ids) < 3:
            raise ValueError("ruleset observation arrays require equal K+2 cardinality")
        list_count = len(self.request_targets) - 2
        list_matches = tuple(
            _GITHUB_RULESET_LIST_TARGET_RE.fullmatch(item.path_and_query)
            for item in self.request_targets[:list_count]
        )
        detail_matches = tuple(
            _GITHUB_RULESET_DETAIL_TARGET_RE.fullmatch(item.path_and_query)
            for item in self.request_targets[list_count:]
        )
        if any(item is None for item in (*list_matches, *detail_matches)):
            raise ValueError("ruleset request targets require list-before-detail order")
        verified_matches = tuple(
            cast(re.Match[str], item) for item in (*list_matches, *detail_matches)
        )
        slugs = {
            (item.group("owner"), item.group("repo"))
            for item in verified_matches
        }
        pages = tuple(int(item.group("page")) for item in verified_matches[:list_count])
        detail_ids = tuple(
            int(item.group("ruleset_id")) for item in verified_matches[list_count:]
        )
        if (
            len(slugs) != 1
            or pages != tuple(range(1, list_count + 1))
            or detail_ids != tuple(sorted(detail_ids))
            or len(set(detail_ids)) != 2
            or set(detail_ids) != set(self.ruleset_ids)
        ):
            raise ValueError("ruleset request target identity/order mismatch")
        expected_pagination = protocol_review_digest(
            "laconian-tag-ruleset-pagination-root-v1",
            {
                "list_page_count": list_count,
                "list_page_raw_response_sha256s": self.raw_response_sha256s[:list_count],
                "list_page_canonical_response_sha256s": self.canonical_response_sha256s[
                    :list_count
                ],
            },
        )
        if self.pagination_root != expected_pagination:
            raise ValueError("tag ruleset pagination root mismatch")
        expected = protocol_review_digest(
            "laconian-tag-ruleset-observation-receipt-v1",
            _digest_payload(self, "tag_ruleset_observation_receipt_sha256"),
        )
        if self.tag_ruleset_observation_receipt_sha256 != expected:
            raise ValueError("tag ruleset observation receipt digest mismatch")
        return self


class TagCreationRuleEvaluationV1(CapsuleModel):
    rule_source_type: Literal["ruleset"]
    rule_source_id: StrictPositiveInt
    enforcement: Literal["active"]
    result: Literal["fail"]
    rule_type: Literal["creation"]


class TagCreationBypassGrantV1(CapsuleModel):
    actor_id: StrictPositiveInt
    actor_login: BoundedNonBlankString
    source_ruleset_id: StrictPositiveInt
    tag_ruleset_policy_root: Sha256


class TagCreationRuleSuiteReceiptV1(CapsuleModel):
    schema_version: Literal["TagCreationRuleSuiteReceiptV1"]
    repository_id: StrictPositiveInt
    rule_suite_id: StrictPositiveInt
    operation: Literal["create"]
    ref: InputTagRef | CompanionTagRef
    before_sha: Literal["0000000000000000000000000000000000000000"]
    after_sha: GitObjectId
    actor_account_id: StrictPositiveInt
    actor_login: BoundedNonBlankString
    pushed_at: CanonicalTimestamp
    overall_result: Literal["bypass"]
    evaluation_result: Literal["fail"]
    rule_evaluations: tuple[TagCreationRuleEvaluationV1]
    creation_authorizer_ruleset_id: StrictPositiveInt
    creation_bypass_grant: TagCreationBypassGrantV1
    tag_ruleset_policy_root: Sha256
    request_ids: tuple[BoundedNonBlankString, ...]
    api_version: Literal["2022-11-28"]
    raw_response_sha256: Sha256
    canonical_response_sha256: Sha256
    observed_at: CanonicalTimestamp
    tag_creation_rule_suite_receipt_sha256: Sha256

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if len(self.rule_evaluations) != 1:
            raise ValueError("tag creation suite requires exactly one creation-rule evaluation")
        evaluation = self.rule_evaluations[0]
        grant = self.creation_bypass_grant
        if (
            evaluation.rule_source_id != self.creation_authorizer_ruleset_id
            or grant.source_ruleset_id != self.creation_authorizer_ruleset_id
            or grant.actor_id != self.actor_account_id
            or grant.actor_login != self.actor_login
            or grant.tag_ruleset_policy_root != self.tag_ruleset_policy_root
        ):
            raise ValueError("tag creation suite identity/policy mismatch")
        if not self.request_ids or self.pushed_at > self.observed_at:
            raise ValueError("tag creation suite requires request evidence observed after its push")
        expected = protocol_review_digest(
            "laconian-tag-creation-rule-suite-receipt-v1",
            _digest_payload(self, "tag_creation_rule_suite_receipt_sha256"),
        )
        if self.tag_creation_rule_suite_receipt_sha256 != expected:
            raise ValueError("tag creation rule-suite receipt digest mismatch")
        return self


def _decode_canonical_base64(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error):
        raise ValueError("value must be canonical standard base64") from None
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("value must be canonical padded standard base64")
    return decoded


def _canonical_base64(value: str) -> str:
    _decode_canonical_base64(value)
    return value


CanonicalBase64: TypeAlias = Annotated[
    str,
    BeforeValidator(_strict_string),
    AfterValidator(_canonical_base64),
]


class ArchivedProtocolGitObjectV1(CapsuleModel):
    oid: GitObjectId
    type: GitObjectTypeV1
    size: int = Field(strict=True, ge=0)
    git_object_sha256: Sha256
    raw_content_base64: CanonicalBase64

    @model_validator(mode="after")
    def validate_raw_object(self) -> Self:
        parsed = parse_protocol_git_object(
            oid=self.oid,
            object_type=self.type,
            raw_content=_decode_canonical_base64(self.raw_content_base64),
        )
        if parsed.size != self.size or parsed.git_object_sha256 != self.git_object_sha256:
            raise ValueError("archived Git object size/digest mismatch")
        return self


class ArchivedApiBlobV1(CapsuleModel):
    path: RelativePosixPath
    kind: Literal["safe_raw_response", "canonical_projection"]
    byte_length: int = Field(strict=True, ge=0)
    sha256: Sha256
    raw_bytes_base64: CanonicalBase64

    @model_validator(mode="after")
    def validate_blob(self) -> Self:
        match = _ARCHIVE_API_PATH_RE.fullmatch(self.path)
        if match is None:
            raise ValueError("archived API blob path is outside the closed grammar")
        expected_suffix = "response" if self.kind == "safe_raw_response" else "canonical.json"
        if match.group(4) != expected_suffix:
            raise ValueError("archived API blob kind/path suffix mismatch")
        decoded = _decode_canonical_base64(self.raw_bytes_base64)
        if len(decoded) != self.byte_length:
            raise ValueError("archived API blob byte length mismatch")
        if hashlib.sha256(decoded).hexdigest() != self.sha256:
            raise ValueError("archived API blob digest mismatch")
        return self


ArchivedApiReceiptV1 = (
    GitHubSignatureObservationReceiptV1
    | TagRulesetObservationReceiptV1
    | TagCreationRuleSuiteReceiptV1
)
ArchivedApiReceiptKindV1 = Literal[
    "github_signature",
    "tag_ruleset_observation",
    "t0_creation_suite",
    "t1_creation_suite",
]


class ArchivedApiReceiptBindingV1(CapsuleModel):
    receipt_kind: ArchivedApiReceiptKindV1
    receipt_sha256: Sha256
    receipt: ArchivedApiReceiptV1
    raw_blob_paths: tuple[RelativePosixPath, ...]
    canonical_blob_paths: tuple[RelativePosixPath, ...]

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        expected_type: type[CapsuleModel]
        expected_digest: str
        raw_hashes: tuple[str, ...]
        canonical_hashes: tuple[str, ...]
        if self.receipt_kind == "github_signature":
            expected_type = GitHubSignatureObservationReceiptV1
            assert isinstance(self.receipt, GitHubSignatureObservationReceiptV1)
            expected_digest = self.receipt.github_signature_observation_receipt_sha256
            raw_hashes = self.receipt.raw_response_sha256s
            canonical_hashes = self.receipt.canonical_response_sha256s
        elif self.receipt_kind == "tag_ruleset_observation":
            expected_type = TagRulesetObservationReceiptV1
            assert isinstance(self.receipt, TagRulesetObservationReceiptV1)
            expected_digest = self.receipt.tag_ruleset_observation_receipt_sha256
            raw_hashes = self.receipt.raw_response_sha256s
            canonical_hashes = self.receipt.canonical_response_sha256s
        else:
            expected_type = TagCreationRuleSuiteReceiptV1
            assert isinstance(self.receipt, TagCreationRuleSuiteReceiptV1)
            expected_digest = self.receipt.tag_creation_rule_suite_receipt_sha256
            raw_hashes = (self.receipt.raw_response_sha256,)
            canonical_hashes = (self.receipt.canonical_response_sha256,)
            input_kind = self.receipt.ref.startswith("refs/tags/benchmark-input-")
            if input_kind != (self.receipt_kind == "t0_creation_suite"):
                raise ValueError("creation-suite wrapper kind/ref mismatch")
        if not isinstance(self.receipt, expected_type):
            raise ValueError("archived receipt kind/schema mismatch")
        if self.receipt_sha256 != expected_digest:
            raise ValueError("archived receipt digest mismatch")
        if not (
            len(self.raw_blob_paths)
            == len(self.canonical_blob_paths)
            == len(raw_hashes)
            == len(canonical_hashes)
        ):
            raise ValueError("archived receipt blob arrays require equal cardinality")
        for ordinal, (raw_path, canonical_path) in enumerate(
            zip(self.raw_blob_paths, self.canonical_blob_paths, strict=True)
        ):
            prefix = f"api/{self.receipt_kind}/{self.receipt_sha256}/{ordinal:08d}."
            if raw_path != prefix + "response" or canonical_path != prefix + "canonical.json":
                raise ValueError("archived receipt blob path mismatch")
        return self


class ProtocolReviewObjectArchiveV1(CapsuleModel):
    schema_version: Literal["ProtocolReviewObjectArchiveV1"]
    object_closure_root: Sha256
    objects: tuple[ArchivedProtocolGitObjectV1, ...]
    api_blobs: tuple[ArchivedApiBlobV1, ...]
    api_receipts: tuple[ArchivedApiReceiptBindingV1, ...]
    protocol_review_object_archive_sha256: Sha256

    @model_validator(mode="after")
    def validate_archive(self) -> Self:
        if not self.objects or len({item.oid for item in self.objects}) != len(self.objects):
            raise ValueError("archive Git objects must be nonempty and unique")
        if tuple(item.oid for item in self.objects) != tuple(
            sorted(item.oid for item in self.objects)
        ):
            raise ValueError("archive Git objects require strict ascending OID order")
        closure_projection = [
            {
                "oid": item.oid,
                "type": item.type,
                "size": item.size,
                "git_object_sha256": item.git_object_sha256,
            }
            for item in self.objects
        ]
        if self.object_closure_root != protocol_review_digest(
            "laconian-protocol-review-object-closure-v1", closure_projection
        ):
            raise ValueError("protocol-review object closure root mismatch")
        if tuple(item.path for item in self.api_blobs) != tuple(
            sorted((item.path for item in self.api_blobs), key=lambda value: value.encode("utf-8"))
        ):
            raise ValueError("archived API blobs require bytewise path order")
        if len({item.path for item in self.api_blobs}) != len(self.api_blobs):
            raise ValueError("archived API blob paths must be unique")
        kind_rank = {
            "github_signature": 0,
            "tag_ruleset_observation": 1,
            "t0_creation_suite": 2,
            "t1_creation_suite": 3,
        }
        receipt_keys = tuple(
            _archive_receipt_order_key(item, kind_rank) for item in self.api_receipts
        )
        if receipt_keys != tuple(sorted(receipt_keys)):
            raise ValueError("archived API receipt wrapper order mismatch")
        receipt_kinds = tuple(item.receipt_kind for item in self.api_receipts)
        if (
            receipt_kinds.count("github_signature") != 3
            or receipt_kinds.count("tag_ruleset_observation") < 1
            or receipt_kinds.count("t0_creation_suite") != 1
            or receipt_kinds.count("t1_creation_suite") != 1
        ):
            raise ValueError(
                "archive requires three signature receipts, current ruleset evidence, "
                "and both creation suites"
            )
        referenced = tuple(
            path
            for item in self.api_receipts
            for pair in zip(item.raw_blob_paths, item.canonical_blob_paths, strict=True)
            for path in pair
        )
        if len(referenced) != len(set(referenced)) or set(referenced) != {
            item.path for item in self.api_blobs
        }:
            raise ValueError("each archived API blob must be referenced exactly once")
        blobs = {item.path: item for item in self.api_blobs}
        for binding in self.api_receipts:
            raw_hashes, canonical_hashes = _receipt_hash_arrays(binding)
            for ordinal, (raw_path, canonical_path) in enumerate(
                zip(binding.raw_blob_paths, binding.canonical_blob_paths, strict=True)
            ):
                if (
                    blobs[raw_path].kind != "safe_raw_response"
                    or blobs[raw_path].sha256 != raw_hashes[ordinal]
                    or blobs[canonical_path].kind != "canonical_projection"
                    or blobs[canonical_path].sha256 != canonical_hashes[ordinal]
                ):
                    raise ValueError("archived API blob/receipt hash mismatch")
                parse_canonical_json_v1(
                    _decode_canonical_base64(blobs[canonical_path].raw_bytes_base64)
                )
        expected = protocol_review_digest(
            "laconian-protocol-review-object-archive-v1",
            _digest_payload(self, "protocol_review_object_archive_sha256"),
        )
        if self.protocol_review_object_archive_sha256 != expected:
            raise ValueError("protocol-review object archive digest mismatch")
        return self


def _archive_receipt_order_key(
    binding: ArchivedApiReceiptBindingV1, rank: Mapping[str, int]
) -> tuple[int, str, str]:
    observed = getattr(binding.receipt, "observed_at", None)
    observed_text = observed.isoformat() if isinstance(observed, datetime) else ""
    return rank[binding.receipt_kind], observed_text, binding.receipt_sha256


def _receipt_hash_arrays(
    binding: ArchivedApiReceiptBindingV1,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    receipt = binding.receipt
    if isinstance(receipt, (GitHubSignatureObservationReceiptV1, TagRulesetObservationReceiptV1)):
        return receipt.raw_response_sha256s, receipt.canonical_response_sha256s
    return (receipt.raw_response_sha256,), (receipt.canonical_response_sha256,)


@dataclass(frozen=True, slots=True)
class ParsedProtocolGitObjectV1:
    oid: str
    object_type: GitObjectTypeV1
    size: int
    git_object_sha256: str
    raw_content: bytes


def parse_protocol_git_object(
    *,
    oid: GitObjectId,
    object_type: GitObjectTypeV1,
    raw_content: bytes,
) -> ParsedProtocolGitObjectV1:
    """Validate and hash one exact raw Git object without invoking Git."""

    _git_sha1(oid)
    if object_type not in ("blob", "tree", "commit", "tag"):
        raise ValueError("unsupported Git object type")
    if type(raw_content) is not bytes:
        raise TypeError("raw Git object content must be exact bytes")
    header = object_type.encode("ascii") + b" " + str(len(raw_content)).encode("ascii") + b"\0"
    wire = header + raw_content
    actual_oid = hashlib.sha1(wire).hexdigest()
    if oid != actual_oid:
        raise ValueError("raw Git object SHA-1 mismatch")
    if object_type == "tree":
        _parse_tree_entries(raw_content)
    elif object_type in ("commit", "tag"):
        _validate_text_git_object(raw_content)
    return ParsedProtocolGitObjectV1(
        oid=oid,
        object_type=object_type,
        size=len(raw_content),
        git_object_sha256=hashlib.sha256(wire).hexdigest(),
        raw_content=raw_content,
    )


def _validate_text_git_object(raw_content: bytes) -> None:
    if b"\0" in raw_content or b"\r" in raw_content or not raw_content.endswith(b"\n"):
        raise ValueError("text Git object requires LF-only NUL-free terminal-LF bytes")
    try:
        text = raw_content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError("text Git object must be strict UTF-8") from None
    if unicodedata.normalize("NFC", text) != text:
        raise ValueError("text Git object must already be NFC")
    if "\n\n" not in text:
        raise ValueError("text Git object requires one header/message separator")


def _parse_tree_entries(raw_content: bytes) -> tuple[tuple[str, bytes, str], ...]:
    cursor = 0
    entries: list[tuple[str, bytes, str]] = []
    while cursor < len(raw_content):
        space = raw_content.find(b" ", cursor)
        nul = raw_content.find(b"\0", space + 1)
        if space <= cursor or nul < 0 or nul + 21 > len(raw_content):
            raise ValueError("malformed raw Git tree entry")
        mode = raw_content[cursor:space].decode("ascii", errors="strict")
        if mode not in {"100644", "40000"}:
            raise ValueError(
                "protocol Git trees allow only directories and regular non-executable blobs"
            )
        name = raw_content[space + 1 : nul]
        if not name or b"/" in name or name in {b".", b".."} or b"\0" in name:
            raise ValueError("invalid raw Git tree name")
        try:
            decoded_name = name.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise ValueError("raw Git tree names must be strict UTF-8") from None
        if unicodedata.normalize("NFC", decoded_name) != decoded_name:
            raise ValueError("raw Git tree names must already be NFC")
        child_oid = raw_content[nul + 1 : nul + 21].hex()
        entries.append((mode, name, child_oid))
        cursor = nul + 21
    sort_keys = tuple(name + (b"/" if mode == "40000" else b"") for mode, name, _ in entries)
    raw_names = tuple(name for _, name, _ in entries)
    if (
        sort_keys != tuple(sorted(sort_keys))
        or len(set(sort_keys)) != len(sort_keys)
        or len(set(raw_names)) != len(raw_names)
    ):
        raise ValueError("raw Git tree entries require canonical unique Git order")
    return tuple(entries)


def _statement_path(input_tag_ref: str, role: ProtocolReviewRoleV1) -> str:
    basename = input_tag_ref.removeprefix("refs/tags/")
    filename = {
        "statistical_method": "01-statistical-method.json",
        "blind_judge_audit_protocol": "02-blind-judge-audit-protocol.json",
        "security_evidence": "03-security-evidence.json",
    }[role]
    return f"benchmarks/protocol-reviews/{basename}/statements/{filename}"


@dataclass(frozen=True, slots=True)
class VerifiedProtocolReviewPrefixV1:
    input_tag_ref: str
    objects: tuple[ParsedProtocolGitObjectV1, ...]
    input_tag: ParsedProtocolGitObjectV1
    peeled_c0: ParsedProtocolGitObjectV1
    reviewer_commits: tuple[
        ParsedProtocolGitObjectV1,
        ParsedProtocolGitObjectV1,
        ParsedProtocolGitObjectV1,
    ]
    statements: tuple[
        ProtocolReviewStatementV1,
        ProtocolReviewStatementV1,
        ProtocolReviewStatementV1,
    ]
    attestations: tuple[
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
    ]
    protocol_reviewer_registry: ProtocolReviewerRegistryV1
    tag_operator_registry: TagOperatorRegistryV1
    tag_ruleset_policy: TagRulesetPolicyV1
    signature_evidence_sources: tuple[
        ProtocolSignatureEvidenceSourceV1,
        ProtocolSignatureEvidenceSourceV1,
        ProtocolSignatureEvidenceSourceV1,
    ]
    input_tag_creation_suite: TagCreationRuleSuiteReceiptV1


@dataclass(frozen=True, slots=True)
class VerifiedProtocolReviewDagV1:
    prefix: VerifiedProtocolReviewPrefixV1
    companion_tag_ref: str
    bundle: ProtocolAttestationBundleV1
    bundle_commit: ParsedProtocolGitObjectV1
    companion_tag: ParsedProtocolGitObjectV1
    objects: tuple[ParsedProtocolGitObjectV1, ...]
    tag_creation_suites: tuple[
        TagCreationRuleSuiteReceiptV1,
        TagCreationRuleSuiteReceiptV1,
    ]


def verify_protocol_review_prefix(
    *,
    input_tag_ref: InputTagRef,
    objects: tuple[ParsedProtocolGitObjectV1, ...],
    protocol_reviewer_registry: ProtocolReviewerRegistryV1,
    tag_operator_registry: TagOperatorRegistryV1,
    tag_ruleset_policy: TagRulesetPolicyV1,
    signature_evidence_sources: tuple[
        ProtocolSignatureEvidenceSourceV1,
        ProtocolSignatureEvidenceSourceV1,
        ProtocolSignatureEvidenceSourceV1,
    ],
    input_tag_creation_suite: TagCreationRuleSuiteReceiptV1,
) -> VerifiedProtocolReviewPrefixV1:
    """Verify the exact T0/C0/Rstat/Rjudge/Rsecurity prefix.

    Full raw DAG reconstruction is intentionally centralized here.  The implementation rejects
    incomplete evidence instead of accepting a caller-supplied trust Boolean.
    """

    if type(signature_evidence_sources) is not tuple or len(signature_evidence_sources) != 3:
        raise ProtocolReviewVerificationError(
            "protocol-review prefix requires an exact three-source tuple"
        )
    validated_reviewers = _class_bound_revalidate(
        protocol_reviewer_registry, ProtocolReviewerRegistryV1
    )
    validated_operator = _class_bound_revalidate(tag_operator_registry, TagOperatorRegistryV1)
    validated_policy = _class_bound_revalidate(tag_ruleset_policy, TagRulesetPolicyV1)
    validated_sources = cast(
        tuple[
            ProtocolSignatureEvidenceSourceV1,
            ProtocolSignatureEvidenceSourceV1,
            ProtocolSignatureEvidenceSourceV1,
        ],
        tuple(_revalidate_signature_source(item) for item in signature_evidence_sources),
    )
    validated_suite = _class_bound_revalidate(
        input_tag_creation_suite, TagCreationRuleSuiteReceiptV1
    )
    return _verify_protocol_review_prefix(
        input_tag_ref=input_tag_ref,
        objects=objects,
        protocol_reviewer_registry=validated_reviewers,
        tag_operator_registry=validated_operator,
        tag_ruleset_policy=validated_policy,
        signature_evidence_sources=validated_sources,
        input_tag_creation_suite=validated_suite,
    )


def verify_protocol_review_dag(
    *,
    input_tag_ref: InputTagRef,
    companion_tag_ref: CompanionTagRef,
    objects: tuple[ParsedProtocolGitObjectV1, ...],
    protocol_reviewer_registry: ProtocolReviewerRegistryV1,
    tag_operator_registry: TagOperatorRegistryV1,
    tag_ruleset_policy: TagRulesetPolicyV1,
    signature_evidence_sources: tuple[ProtocolSignatureEvidenceSourceV1, ...],
    tag_creation_suites: tuple[
        TagCreationRuleSuiteReceiptV1,
        TagCreationRuleSuiteReceiptV1,
    ],
) -> VerifiedProtocolReviewDagV1:
    """Verify the complete immutable T0/C0/R*/B0/T1 graph."""

    if type(signature_evidence_sources) is not tuple or len(signature_evidence_sources) != 3:
        raise ProtocolReviewVerificationError(
            "complete protocol DAG requires an exact three-source tuple"
        )
    if type(tag_creation_suites) is not tuple or len(tag_creation_suites) != 2:
        raise ProtocolReviewVerificationError(
            "complete protocol DAG requires an exact two-suite tuple"
        )
    validated_reviewers = _class_bound_revalidate(
        protocol_reviewer_registry, ProtocolReviewerRegistryV1
    )
    validated_operator = _class_bound_revalidate(tag_operator_registry, TagOperatorRegistryV1)
    validated_policy = _class_bound_revalidate(tag_ruleset_policy, TagRulesetPolicyV1)
    validated_sources = tuple(
        _revalidate_signature_source(item) for item in signature_evidence_sources
    )
    validated_suites = cast(
        tuple[TagCreationRuleSuiteReceiptV1, TagCreationRuleSuiteReceiptV1],
        tuple(
            _class_bound_revalidate(item, TagCreationRuleSuiteReceiptV1)
            for item in tag_creation_suites
        ),
    )
    return _verify_protocol_review_dag(
        input_tag_ref=input_tag_ref,
        companion_tag_ref=companion_tag_ref,
        objects=objects,
        protocol_reviewer_registry=validated_reviewers,
        tag_operator_registry=validated_operator,
        tag_ruleset_policy=validated_policy,
        signature_evidence_sources=validated_sources,
        tag_creation_suites=validated_suites,
    )


@dataclass(frozen=True, slots=True)
class _CommitView:
    tree_oid: str
    parent_oids: tuple[str, ...]
    author: bytes
    committer: bytes
    signature: bytes | None
    signed_payload: bytes
    message: bytes
    header_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TagView:
    target_oid: str
    tag_name: str
    tagger: bytes
    message: bytes
    header_names: tuple[str, ...]


def _header_groups(raw_content: bytes) -> tuple[list[tuple[bytes, list[bytes]]], bytes]:
    try:
        raw_headers, message = raw_content.split(b"\n\n", 1)
    except ValueError:
        raise ProtocolReviewVerificationError(
            "Git object lacks exactly one header separator"
        ) from None
    groups: list[tuple[bytes, list[bytes]]] = []
    for line in raw_headers.split(b"\n"):
        if line.startswith(b" "):
            if not groups:
                raise ProtocolReviewVerificationError("orphan Git header continuation")
            groups[-1][1].append(line[1:])
            continue
        if b" " not in line:
            raise ProtocolReviewVerificationError("malformed Git header")
        name, value = line.split(b" ", 1)
        if not name or not value:
            raise ProtocolReviewVerificationError("empty Git header name/value")
        groups.append((name, [value]))
    return groups, message


def _parse_commit_view(item: ParsedProtocolGitObjectV1) -> _CommitView:
    if item.object_type != "commit":
        raise ProtocolReviewVerificationError("expected a commit object")
    groups, message = _header_groups(item.raw_content)
    names = tuple(name.decode("ascii", errors="strict") for name, _ in groups)
    values: dict[str, list[bytes]] = {}
    for name, lines in groups:
        decoded = name.decode("ascii", errors="strict")
        if decoded in values and decoded not in {"parent"}:
            raise ProtocolReviewVerificationError("duplicate singleton commit header")
        values.setdefault(decoded, []).append(b"\n".join(lines))
    for required in ("tree", "author", "committer"):
        if required not in values or len(values[required]) != 1:
            raise ProtocolReviewVerificationError(f"commit requires one {required} header")
    tree_oid = values["tree"][0].decode("ascii", errors="strict")
    _git_sha1(tree_oid)
    parent_oids = tuple(
        value.decode("ascii", errors="strict") for value in values.get("parent", [])
    )
    for parent in parent_oids:
        _git_sha1(parent)
    signature_groups = [group for group in groups if group[0] == b"gpgsig"]
    if len(signature_groups) > 1:
        raise ProtocolReviewVerificationError("commit contains multiple signature headers")
    signature = None if not signature_groups else b"\n".join(signature_groups[0][1])
    retained_lines: list[bytes] = []
    for name, lines in groups:
        if name == b"gpgsig":
            continue
        retained_lines.append(name + b" " + lines[0])
        retained_lines.extend(b" " + line for line in lines[1:])
    signed_payload = b"\n".join(retained_lines) + b"\n\n" + message
    return _CommitView(
        tree_oid=tree_oid,
        parent_oids=parent_oids,
        author=values["author"][0],
        committer=values["committer"][0],
        signature=signature,
        signed_payload=signed_payload,
        message=message,
        header_names=names,
    )


def _parse_tag_view(item: ParsedProtocolGitObjectV1) -> _TagView:
    if item.object_type != "tag":
        raise ProtocolReviewVerificationError("expected an annotated tag object")
    groups, message = _header_groups(item.raw_content)
    names = tuple(name.decode("ascii", errors="strict") for name, _ in groups)
    if names != ("object", "type", "tag", "tagger") or any(len(lines) != 1 for _, lines in groups):
        raise ProtocolReviewVerificationError(
            "annotated tag requires the exact four-header grammar"
        )
    values = {name: lines[0] for name, lines in groups}
    target_oid = values[b"object"].decode("ascii", errors="strict")
    _git_sha1(target_oid)
    if values[b"type"] != b"commit":
        raise ProtocolReviewVerificationError("protocol tags must target commits directly")
    return _TagView(
        target_oid=target_oid,
        tag_name=values[b"tag"].decode("ascii", errors="strict"),
        tagger=values[b"tagger"],
        message=message,
        header_names=names,
    )


def _identity_parts(value: bytes) -> tuple[str, str, int, str]:
    try:
        text = value.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        raise ProtocolReviewVerificationError("Git identity must be ASCII") from None
    match = re.fullmatch(r"(.+) <([^<>]+)> ([^ ]+) ([^ ]+)", text)
    if match is None:
        raise ProtocolReviewVerificationError("malformed Git identity header")
    name, email, epoch_text, timezone = match.groups()
    _canonical_git_ascii_name(name)
    _canonical_git_ascii_email(email)
    if _GIT_EPOCH_RE.fullmatch(epoch_text) is None:
        raise ProtocolReviewVerificationError("Git identity epoch is not canonical")
    epoch = int(epoch_text)
    if not 0 <= epoch <= 253_402_300_799:
        raise ProtocolReviewVerificationError("Git identity epoch is out of range")
    if timezone != "+0000":
        raise ProtocolReviewVerificationError("protocol Git identity timezone must be +0000")
    return name, email, epoch, timezone


def _object_map(
    objects: tuple[ParsedProtocolGitObjectV1, ...],
) -> dict[str, ParsedProtocolGitObjectV1]:
    if type(objects) is not tuple or not objects:
        raise ProtocolReviewVerificationError("protocol-review object set is empty")
    if any(type(item) is not ParsedProtocolGitObjectV1 for item in objects):
        raise ProtocolReviewVerificationError(
            "protocol-review object set requires exact parsed object capabilities"
        )
    oids = tuple(item.oid for item in objects)
    if oids != tuple(sorted(oids)):
        raise ProtocolReviewVerificationError(
            "protocol-review objects require strict ascending decoded-OID order"
        )
    mapping = {item.oid: item for item in objects}
    if len(mapping) != len(objects):
        raise ProtocolReviewVerificationError("protocol-review object set contains duplicate OIDs")
    for item in objects:
        reparsed = parse_protocol_git_object(
            oid=item.oid, object_type=item.object_type, raw_content=item.raw_content
        )
        if reparsed != item:
            raise ProtocolReviewVerificationError(
                "parsed Git object was mutated after verification"
            )
    return mapping


def _flatten_tree(
    tree_oid: str,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    *,
    prefix: str = "",
    active: frozenset[str] = frozenset(),
) -> dict[str, tuple[str, str]]:
    if tree_oid in active:
        raise ProtocolReviewVerificationError("Git tree cycle detected")
    item = objects.get(tree_oid)
    if item is None or item.object_type != "tree":
        raise ProtocolReviewVerificationError("Git tree references a missing/non-tree object")
    flattened: dict[str, tuple[str, str]] = {}
    for mode, raw_name, child_oid in _parse_tree_entries(item.raw_content):
        name = raw_name.decode("utf-8", errors="strict")
        path = f"{prefix}{name}"
        child = objects.get(child_oid)
        if child is None:
            raise ProtocolReviewVerificationError(
                "Git tree references an unavailable closure object"
            )
        if mode == "40000":
            if child.object_type != "tree":
                raise ProtocolReviewVerificationError("directory entry does not reference a tree")
            nested = _flatten_tree(
                child_oid,
                objects,
                prefix=path + "/",
                active=active | {tree_oid},
            )
            if set(flattened).intersection(nested):
                raise ProtocolReviewVerificationError("duplicate flattened Git path")
            flattened.update(nested)
        else:
            if child.object_type != "blob":
                raise ProtocolReviewVerificationError(
                    "non-directory tree entry must reference a blob"
                )
            if path in flattened:
                raise ProtocolReviewVerificationError("duplicate flattened Git path")
            flattened[path] = mode, child_oid
    return flattened


def _tree_directory_topology(
    tree_oid: str,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    *,
    prefix: str = "",
    active: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Return every directory path and its exact tree object ID, including the root."""

    if tree_oid in active:
        raise ProtocolReviewVerificationError("Git tree cycle detected")
    item = objects.get(tree_oid)
    if item is None or item.object_type != "tree":
        raise ProtocolReviewVerificationError("Git tree references a missing/non-tree object")
    directories = {prefix: tree_oid}
    for mode, raw_name, child_oid in _parse_tree_entries(item.raw_content):
        if mode != "40000":
            continue
        child = objects.get(child_oid)
        if child is None or child.object_type != "tree":
            raise ProtocolReviewVerificationError("directory entry does not reference a tree")
        name = raw_name.decode("utf-8", errors="strict")
        path = f"{prefix}/{name}" if prefix else name
        nested = _tree_directory_topology(
            child_oid,
            objects,
            prefix=path,
            active=active | {tree_oid},
        )
        if set(directories).intersection(nested):
            raise ProtocolReviewVerificationError("duplicate Git directory path")
        directories.update(nested)
    return directories


def _reachable_tree_objects(
    tree_oid: str,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> set[str]:
    reached: set[str] = set()

    def visit(oid: str) -> None:
        if oid in reached:
            return
        item = objects.get(oid)
        if item is None:
            raise ProtocolReviewVerificationError("Git tree closure is incomplete")
        reached.add(oid)
        if item.object_type == "tree":
            for _, _, child_oid in _parse_tree_entries(item.raw_content):
                visit(child_oid)

    visit(tree_oid)
    return reached


def _tag_object_for_ref(
    ref: str,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> tuple[ParsedProtocolGitObjectV1, _TagView]:
    basename = ref.removeprefix("refs/tags/")
    matches: list[tuple[ParsedProtocolGitObjectV1, _TagView]] = []
    for item in objects.values():
        if item.object_type != "tag":
            continue
        view = _parse_tag_view(item)
        if view.tag_name == basename:
            matches.append((item, view))
    if len(matches) != 1:
        raise ProtocolReviewVerificationError(
            "protocol tag ref requires one exact annotated object"
        )
    return matches[0]


def _validate_tagger(
    value: bytes,
    operator: TagOperatorProjectionV1,
) -> int:
    name, email, epoch, _ = _identity_parts(value)
    if name != operator.tagger_name or email != operator.tagger_email:
        raise ProtocolReviewVerificationError(
            "raw tagger identity does not match operator registry"
        )
    return epoch


def _validate_creation_suite(
    receipt: TagCreationRuleSuiteReceiptV1,
    *,
    expected_ref: str,
    expected_after_oid: str,
    tag_operator_registry: TagOperatorRegistryV1,
    tag_ruleset_policy: TagRulesetPolicyV1,
) -> None:
    operator = tag_operator_registry.operators[0]
    creation = tag_ruleset_policy.rulesets[0]
    bypass = creation.bypass_actors[0]
    if (
        receipt.repository_id != tag_operator_registry.repository_id
        or receipt.repository_id != tag_ruleset_policy.repository_id
        or receipt.ref != expected_ref
        or receipt.after_sha != expected_after_oid
        or receipt.actor_account_id != operator.operator_account_id
        or receipt.actor_login != operator.operator_login
        or receipt.creation_authorizer_ruleset_id != creation.ruleset_id
        or receipt.tag_ruleset_policy_root != tag_ruleset_policy.tag_ruleset_policy_root
        or bypass.actor_id != operator.operator_account_id
    ):
        raise ProtocolReviewVerificationError(
            "tag creation suite does not bind operator/policy/tag"
        )


def _commit_chain(
    c0_oid: str,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    *,
    length: int,
) -> tuple[ParsedProtocolGitObjectV1, ...]:
    commits = {
        oid: (_parse_commit_view(item), item)
        for oid, item in objects.items()
        if item.object_type == "commit"
    }
    chain: list[ParsedProtocolGitObjectV1] = []
    parent = c0_oid
    for _ in range(length):
        children = [item for view, item in commits.values() if view.parent_oids == (parent,)]
        if len(children) != 1:
            raise ProtocolReviewVerificationError("protocol-review chain is missing or ambiguous")
        child = children[0]
        chain.append(child)
        parent = child.oid
    return tuple(chain)


def _validate_only_tree_delta(
    parent: ParsedProtocolGitObjectV1,
    child: ParsedProtocolGitObjectV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    expected_paths: tuple[str, ...],
) -> dict[str, tuple[str, str]]:
    parent_root = _parse_commit_view(parent).tree_oid
    child_root = _parse_commit_view(child).tree_oid
    parent_tree = _flatten_tree(parent_root, objects)
    child_tree = _flatten_tree(child_root, objects)
    if any(path not in child_tree for path in parent_tree):
        raise ProtocolReviewVerificationError("protocol-review commit deletes a parent path")
    if any(child_tree[path] != value for path, value in parent_tree.items()):
        raise ProtocolReviewVerificationError("protocol-review commit mutates a parent path")
    added = tuple(path for path in child_tree if path not in parent_tree)
    if added != expected_paths:
        raise ProtocolReviewVerificationError("protocol-review commit tree delta mismatch")
    if any(child_tree[path][0] != "100644" for path in added):
        raise ProtocolReviewVerificationError(
            "protocol-review additions must be regular non-executable blobs"
        )
    parent_directories = _tree_directory_topology(parent_root, objects)
    child_directories = _tree_directory_topology(child_root, objects)

    def is_ancestor(directory: str, path: str) -> bool:
        return not directory or path.startswith(directory + "/")

    for directory, oid in parent_directories.items():
        child_oid = child_directories.get(directory)
        if child_oid is None:
            raise ProtocolReviewVerificationError(
                "protocol-review commit deletes a parent directory"
            )
        if child_oid != oid and not any(is_ancestor(directory, path) for path in expected_paths):
            raise ProtocolReviewVerificationError("protocol-review commit tree delta mismatch")
    for directory in child_directories:
        if directory not in parent_directories and not any(
            path.startswith(directory + "/") for path in expected_paths
        ):
            raise ProtocolReviewVerificationError("protocol-review commit tree delta mismatch")
    return child_tree


def _workflow_root_from_c0(
    c0: ParsedProtocolGitObjectV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> str:
    flattened = _flatten_tree(_parse_commit_view(c0).tree_oid, objects)
    workflow_paths = tuple(path for path in flattened if path.startswith(".github/workflows/"))
    if set(workflow_paths) != set(BENCHMARK_WORKFLOW_PATHS_V1):
        raise ProtocolReviewVerificationError(
            "C0 workflow subtree must contain exactly the frozen fifteen members"
        )
    workflow_bytes: dict[RelativePosixPath, bytes] = {}
    for path in BENCHMARK_WORKFLOW_PATHS_V1:
        entry = flattened.get(path)
        if entry is None or entry[0] != "100644":
            raise ProtocolReviewVerificationError("C0 lacks an exact regular workflow member")
        workflow_bytes[path] = objects[entry[1]].raw_content
    return build_workflow_inventory(c0_workflow_bytes=workflow_bytes).workflow_root


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_yaml_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    pairs = loader.construct_pairs(node, deep=deep)
    result: dict[object, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolReviewVerificationError("duplicate key in C0 reviewer registry YAML")
        result[key] = value
    return result


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_yaml_mapping,
)


def _c0_blob(
    flattened: Mapping[str, tuple[str, str]],
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    path: str,
) -> bytes:
    entry = flattened.get(path)
    if entry is None or entry[0] != "100644":
        raise ProtocolReviewVerificationError(f"C0 lacks required regular member {path}")
    return objects[entry[1]].raw_content


def _validate_c0_registry_members(
    *,
    flattened: Mapping[str, tuple[str, str]],
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    protocol_reviewer_registry: ProtocolReviewerRegistryV1,
    tag_operator_registry: TagOperatorRegistryV1,
    tag_ruleset_policy: TagRulesetPolicyV1,
) -> None:
    operator_blob = _c0_blob(flattened, objects, "benchmark/security/tag-operator-registry.json")
    ruleset_blob = _c0_blob(flattened, objects, "benchmark/security/tag-ruleset-policy.json")
    operator_from_c0 = TagOperatorRegistryV1.model_validate(parse_canonical_json_v1(operator_blob))
    ruleset_from_c0 = TagRulesetPolicyV1.model_validate(parse_canonical_json_v1(ruleset_blob))
    reviewer_blob = _c0_blob(
        flattened,
        objects,
        "benchmarks/campaigns/public-three-model-v1/protocol-reviewers.yaml",
    )
    try:
        reviewer_payload = parse_canonical_json_v1(reviewer_blob)
    except CanonicalJSONV1Error:
        try:
            reviewer_payload = yaml.load(
                reviewer_blob.decode("utf-8", errors="strict"),
                Loader=_UniqueKeySafeLoader,
            )
        except (UnicodeDecodeError, yaml.YAMLError) as error:
            raise ProtocolReviewVerificationError(
                "invalid C0 protocol reviewer registry"
            ) from error
    reviewer_from_c0 = ProtocolReviewerRegistryV1.model_validate(reviewer_payload)
    for supplied, retained, label in (
        (tag_operator_registry, operator_from_c0, "tag operator"),
        (tag_ruleset_policy, ruleset_from_c0, "tag ruleset"),
        (protocol_reviewer_registry, reviewer_from_c0, "protocol reviewer"),
    ):
        if canonical_json_v1(supplied.model_dump(mode="json")) != canonical_json_v1(
            retained.model_dump(mode="json")
        ):
            raise ProtocolReviewVerificationError(f"supplied {label} registry differs from C0")


def _validate_review_commit(
    commit: ParsedProtocolGitObjectV1,
    *,
    parent_oid: str,
    reviewer: ProtocolReviewerBindingV1,
    statement: ProtocolReviewStatementV1,
    input_tag_ref: str,
) -> tuple[_CommitView, bytes, bytes]:
    view = _parse_commit_view(commit)
    if view.header_names != ("tree", "parent", "author", "committer", "gpgsig"):
        raise ProtocolReviewVerificationError("review commit header inventory/order mismatch")
    if view.parent_oids != (parent_oid,) or view.signature is None:
        raise ProtocolReviewVerificationError("review commit requires one parent and one signature")
    author_name, author_email, author_epoch, _ = _identity_parts(view.author)
    committer_name, committer_email, committer_epoch, _ = _identity_parts(view.committer)
    if (
        author_name != reviewer.author_name_ascii
        or author_email != reviewer.author_email_ascii
        or committer_name != reviewer.committer_name_ascii
        or committer_email != reviewer.committer_email_ascii
        or author_epoch != committer_epoch
    ):
        raise ProtocolReviewVerificationError("review commit Git identity mismatch")
    signed_at = datetime.fromtimestamp(author_epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if statement.signed_at != signed_at:
        raise ProtocolReviewVerificationError(
            "statement time does not match review commit identity"
        )
    expected_message = (
        f"laconian protocol review {input_tag_ref.removeprefix('refs/tags/')} "
        f"{reviewer.role}: {statement.statement_sha256}\n"
    ).encode("ascii")
    if view.message != expected_message:
        raise ProtocolReviewVerificationError("review commit message mismatch")
    if reviewer.verification_mode == "ssh_sha256":
        marker = b"-----BEGIN SSH SIGNATURE-----"
    else:
        marker = b"-----BEGIN PGP SIGNATURE-----"
    if marker not in view.signature:
        raise ProtocolReviewVerificationError("review commit signature mode/header mismatch")
    return view, view.signed_payload, view.signature


def _validated_repository_slug(owner: object, name: object) -> tuple[str, str]:
    if (
        type(owner) is not str
        or type(name) is not str
        or re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", owner, flags=re.ASCII
        )
        is None
        or re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9_-])?",
            name,
            flags=re.ASCII,
        )
        is None
        or name in {".", ".."}
        or name.casefold().endswith(".git")
    ):
        raise ProtocolReviewVerificationError("repository trust-boundary identity mismatch")
    return owner, name


def _repository_slug_from_c0(
    c0: ParsedProtocolGitObjectV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    repository_id: int,
) -> tuple[str, str]:
    flattened = _flatten_tree(_parse_commit_view(c0).tree_oid, objects)
    path = "benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json"
    entry = flattened.get(path)
    if entry is None or entry[0] != "100644":
        raise ProtocolReviewVerificationError("C0 lacks exact repository trust-boundary member")
    parsed = parse_canonical_json_v1(objects[entry[1]].raw_content)
    if not isinstance(parsed, dict):
        raise ProtocolReviewVerificationError("repository trust boundary must be an object")
    owner, name = _validated_repository_slug(
        parsed.get("repository_owner"), parsed.get("repository_name")
    )
    retained_repository_id = parsed.get("repository_id")
    if retained_repository_id != repository_id or type(retained_repository_id) is not int:
        raise ProtocolReviewVerificationError("repository trust-boundary identity mismatch")
    return owner, name


def _reject_json_constant(value: str) -> object:
    raise ProtocolReviewVerificationError(f"provider JSON contains forbidden constant {value!r}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolReviewVerificationError(f"provider JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _parse_provider_json_value(raw: bytes) -> object:
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolReviewVerificationError("provider response is not strict JSON") from error


def _parse_provider_json(raw: bytes) -> dict[str, object]:
    parsed = _parse_provider_json_value(raw)
    if type(parsed) is not dict:
        raise ProtocolReviewVerificationError("provider response must be a JSON object")
    return cast(dict[str, object], parsed)


def _parse_provider_json_array(raw: bytes) -> list[object]:
    parsed = _parse_provider_json_value(raw)
    if type(parsed) is not list:
        raise ProtocolReviewVerificationError("provider response must be a JSON array")
    return cast(list[object], parsed)


def _selected_object(value: object, path: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ProtocolReviewVerificationError(f"provider selected path {path} must be an object")
    return cast(dict[str, object], value)


def _selected_string(value: object, path: str) -> str:
    if type(value) is not str:
        raise ProtocolReviewVerificationError(f"provider selected path {path} must be a string")
    return value


def _selected_positive_int(value: object, path: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProtocolReviewVerificationError(
            f"provider selected path {path} must be a positive JSON integer"
        )
    return value


def _selected_true(value: object, path: str) -> bool:
    if type(value) is not bool or value is not True:
        raise ProtocolReviewVerificationError(f"provider selected path {path} must be true")
    return True


def _required_selected(mapping: Mapping[str, object], key: str, path: str) -> object:
    if key not in mapping or mapping[key] is None:
        raise ProtocolReviewVerificationError(f"provider selected path {path}.{key} is absent/null")
    return mapping[key]


def _provider_verified_at(value: object) -> datetime:
    text = _selected_string(value, "verification.verified_at")
    if _PROVIDER_TIMESTAMP_RE.fullmatch(text) is None:
        raise ProtocolReviewVerificationError("REST verified_at is not a strict RFC 3339 instant")
    try:
        parsed = datetime.fromisoformat(
            text.removesuffix("Z") + ("+00:00" if text.endswith("Z") else "")
        )
    except ValueError:
        raise ProtocolReviewVerificationError("REST verified_at is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProtocolReviewVerificationError("REST verified_at lacks an explicit UTC offset")
    return parsed.astimezone(UTC)


def _read_exact_active_file(relative_path: str, expected_sha256: str) -> bytes:
    project_root = Path(__file__).resolve().parents[3]
    candidate = project_root / relative_path
    if candidate != candidate.resolve() or not candidate.is_file():
        raise ProtocolReviewVerificationError(
            f"active verifier member {relative_path} is missing or symlinked"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(candidate, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProtocolReviewVerificationError("active verifier member is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ):
        raise ProtocolReviewVerificationError("active verifier member changed during hashing")
    raw = b"".join(chunks)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ProtocolReviewVerificationError(
            f"active verifier member {relative_path} differs from sealed C0 bytes"
        )
    return raw


_VERIFIER_DEPENDENCY_SELECTION_V1 = MappingProxyType(
    {
        "cryptography": (
            "50.0.1",
            (("cffi", "platform_python_implementation != 'PyPy'"),),
        ),
        "cffi": ("2.1.1", (("pycparser", "implementation_name != 'PyPy'"),)),
        "pycparser": ("3.0", ()),
    }
)
_VERIFIER_DEPENDENCY_SELECTION_PROJECTION_V1 = (
    {
        "distribution_name": "cryptography",
        "distribution_version": "50.0.1",
        "direct_dependencies": [
            {
                "distribution_name": "cffi",
                "marker": "platform_python_implementation != 'PyPy'",
            }
        ],
    },
    {
        "distribution_name": "cffi",
        "distribution_version": "2.1.1",
        "direct_dependencies": [
            {
                "distribution_name": "pycparser",
                "marker": "implementation_name != 'PyPy'",
            }
        ],
    },
    {
        "distribution_name": "pycparser",
        "distribution_version": "3.0",
        "direct_dependencies": [],
    },
)
_DISTRIBUTION_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*")


class VerifierDependencyInventoryEntryV1(CapsuleModel):
    distribution_name: Literal["cryptography", "cffi", "pycparser"]
    distribution_version: Literal["50.0.1", "2.1.1", "3.0"]
    environment_relative_path: RelativePosixPath
    byte_length: int = Field(strict=True, ge=0)
    sha256: Sha256


@dataclass(frozen=True, slots=True)
class _VerifiedDependencyInventoryV1:
    root: str
    entries: tuple[VerifierDependencyInventoryEntryV1, ...]
    paths_by_distribution: Mapping[str, frozenset[Path]]
    bytes_by_path: Mapping[Path, bytes]
    distributions: Mapping[str, importlib_metadata.Distribution]
    retained_anchors: tuple[tuple[int, Path, tuple[int, int, int, int, int, int, int]], ...]


def _normalized_distribution_name(value: str) -> str:
    if type(value) is not str or _DISTRIBUTION_NAME_RE.fullmatch(value) is None:
        raise ProtocolReviewVerificationError("invalid verifier distribution name")
    return re.sub(r"[-_.]+", "-", value).lower()


def _requirement_selected_without_extras(marker: str | None) -> bool:
    if marker is None:
        return True
    normalized = " ".join(marker.split())
    if re.fullmatch(r"extra\s*==\s*(['\"])[A-Za-z0-9._-]+\1", normalized):
        return False
    if normalized in {
        "platform_python_implementation != 'PyPy'",
        'platform_python_implementation != "PyPy"',
        "implementation_name != 'PyPy'",
        'implementation_name != "PyPy"',
    }:
        return sys.implementation.name.lower() != "pypy"
    if normalized in {
        "python_full_version < '3.11'",
        'python_full_version < "3.11"',
    }:
        return sys.version_info[:2] < (3, 11)
    raise ProtocolReviewVerificationError(
        "installed verifier dependency has an unsupported selection marker"
    )


def _selected_installed_requirements(requirements: list[str] | None) -> tuple[str, ...]:
    selected: list[str] = []
    for requirement in requirements or []:
        if type(requirement) is not str:
            raise ProtocolReviewVerificationError(
                "installed verifier dependency requirement is not text"
            )
        requirement_text, separator, marker = requirement.partition(";")
        match = _DISTRIBUTION_NAME_RE.match(requirement_text.strip())
        if match is None:
            raise ProtocolReviewVerificationError(
                "installed verifier dependency requirement is invalid"
            )
        if _requirement_selected_without_extras(marker.strip() if separator else None):
            selected.append(_normalized_distribution_name(match.group(0)))
    if len(set(selected)) != len(selected):
        raise ProtocolReviewVerificationError(
            "installed verifier dependency requirements are ambiguous"
        )
    return tuple(sorted(selected))


def _locked_verifier_dependency_selection(
    lock_bytes: bytes,
) -> dict[str, tuple[str, tuple[str, ...]]]:
    try:
        document = tomllib.loads(lock_bytes.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise ProtocolReviewVerificationError("C0 dependency lock is not strict TOML") from None
    packages = document.get("package")
    if type(packages) is not list:
        raise ProtocolReviewVerificationError("C0 dependency lock lacks its package inventory")
    selected: dict[str, tuple[str, tuple[str, ...]]] = {}
    for expected_name, (
        expected_version,
        expected_dependencies,
    ) in _VERIFIER_DEPENDENCY_SELECTION_V1.items():
        named = tuple(
            package
            for package in packages
            if type(package) is dict
            and package.get("name") == expected_name
        )
        if len(named) != 1 or named[0].get("version") != expected_version:
            raise ProtocolReviewVerificationError(
                f"C0 dependency lock requires one exact {expected_name}=={expected_version}"
            )
        package = named[0]
        if package.get("source") != {"registry": "https://pypi.org/simple"}:
            raise ProtocolReviewVerificationError(
                f"C0 verifier dependency {expected_name} is not registry-resolved"
            )
        dependency_entries = package.get("dependencies", [])
        if type(dependency_entries) is not list:
            raise ProtocolReviewVerificationError(
                f"C0 verifier dependency {expected_name} has invalid dependencies"
            )
        actual_dependencies: list[tuple[str, str | None]] = []
        for dependency in dependency_entries:
            if type(dependency) is not dict or type(dependency.get("name")) is not str:
                raise ProtocolReviewVerificationError(
                    f"C0 verifier dependency {expected_name} has an invalid direct dependency"
                )
            marker = dependency.get("marker")
            if marker is not None and type(marker) is not str:
                raise ProtocolReviewVerificationError(
                    f"C0 verifier dependency {expected_name} has an invalid marker"
                )
            actual_dependencies.append((dependency["name"], marker))
        if tuple(actual_dependencies) != expected_dependencies:
            raise ProtocolReviewVerificationError(
                f"C0 verifier dependency {expected_name} direct-dependency selection mismatch"
            )
        runtime_dependencies = tuple(
            sorted(
                dependency_name
                for dependency_name, marker in actual_dependencies
                if _requirement_selected_without_extras(marker)
            )
        )
        selected[expected_name] = (expected_version, runtime_dependencies)
    return selected


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_directory_no_follow(path: Path) -> tuple[int, Path]:
    if not path.is_absolute():
        raise ProtocolReviewVerificationError("verifier dependency path must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        before = os.fstat(descriptor)
        if not stat.S_ISDIR(before.st_mode):
            raise ProtocolReviewVerificationError("verifier dependency directory is not real")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            raise ProtocolReviewVerificationError(
                "verifier dependency directory cannot be resolved"
            ) from None
        current = os.stat(resolved, follow_symlinks=False)
        if _stat_identity(before) != _stat_identity(current):
            raise ProtocolReviewVerificationError(
                "verifier dependency directory descriptor identity mismatch"
            )
        return descriptor, resolved
    except Exception:
        os.close(descriptor)
        raise


def _read_inventory_member_no_follow(path: Path) -> tuple[bytes, os.stat_result]:
    parent_descriptor, _ = _open_directory_no_follow(path.parent)
    descriptor = -1
    try:
        path_before = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        descriptor = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _stat_identity(path_before) != _stat_identity(
            before
        ):
            raise ProtocolReviewVerificationError(
                "verifier dependency member path/descriptor identity mismatch"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1_048_576)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        path_after = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            _stat_identity(before) != _stat_identity(after)
            or _stat_identity(after) != _stat_identity(path_after)
        ):
            raise ProtocolReviewVerificationError(
                "verifier dependency member changed during hashing"
            )
        return b"".join(chunks), after
    except OSError as error:
        raise ProtocolReviewVerificationError(
            "verifier dependency member is missing, symlinked, or unreadable"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _environment_relative_record_path(site_relative: PurePosixPath, raw_path: str) -> str:
    parts = list(site_relative.parts)
    for part in PurePosixPath(raw_path).parts:
        if part == "..":
            if not parts:
                raise ProtocolReviewVerificationError(
                    "verifier dependency RECORD path escapes the environment root"
                )
            parts.pop()
        elif part not in {"", "."}:
            parts.append(part)
    if not parts:
        raise ProtocolReviewVerificationError(
            "verifier dependency RECORD path resolves to the environment root"
        )
    return PurePosixPath(*parts).as_posix()


def _read_inventory_member_at(
    environment_descriptor: int, environment_relative: str
) -> tuple[bytes, os.stat_result]:
    parts = PurePosixPath(environment_relative).parts
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor = os.dup(environment_descriptor)
    descriptor = -1
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=parent_descriptor)
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
        path_before = os.stat(parts[-1], dir_fd=parent_descriptor, follow_symlinks=False)
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _stat_identity(path_before) != _stat_identity(
            before
        ):
            raise ProtocolReviewVerificationError(
                "verifier dependency member path/descriptor identity mismatch"
            )
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1_048_576):
            chunks.append(chunk)
        after = os.fstat(descriptor)
        path_after = os.stat(parts[-1], dir_fd=parent_descriptor, follow_symlinks=False)
        if _stat_identity(before) != _stat_identity(after) or _stat_identity(
            after
        ) != _stat_identity(path_after):
            raise ProtocolReviewVerificationError(
                "verifier dependency member changed during hashing"
            )
        return b"".join(chunks), after
    except OSError as error:
        raise ProtocolReviewVerificationError(
            "verifier dependency member is missing, symlinked, or unreadable"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _open_inventory_member_fd(
    environment_descriptor: int, environment_relative: str
) -> tuple[int, bytes]:
    parts = PurePosixPath(environment_relative).parts
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor = os.dup(environment_descriptor)
    descriptor = -1
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=parent_descriptor)
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
        path_stat = os.stat(parts[-1], dir_fd=parent_descriptor, follow_symlinks=False)
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_stat.st_mode) or _stat_identity(
            path_stat
        ) != _stat_identity(descriptor_stat):
            raise ProtocolReviewVerificationError(
                "verifier dependency member path/descriptor identity mismatch"
            )
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1_048_576):
            chunks.append(chunk)
        if _stat_identity(descriptor_stat) != _stat_identity(os.fstat(descriptor)):
            raise ProtocolReviewVerificationError(
                "verifier dependency member changed during fd capture"
            )
        return descriptor, b"".join(chunks)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    finally:
        os.close(parent_descriptor)


def _strict_record_rows(raw: bytes) -> tuple[tuple[str, str, str], ...]:
    try:
        text = raw.decode("utf-8", errors="strict")
        parsed = tuple(csv.reader(io.StringIO(text, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error):
        raise ProtocolReviewVerificationError(
            "verifier dependency RECORD is not strict CSV"
        ) from None
    rows: list[tuple[str, str, str]] = []
    for row in parsed:
        if len(row) != 3 or any(type(item) is not str for item in row):
            raise ProtocolReviewVerificationError("verifier dependency RECORD row shape mismatch")
        path_text, hash_text, size_text = row
        if (
            not path_text
            or "\\" in path_text
            or any(value in path_text for value in ("\0", "\r", "\n"))
            or PurePosixPath(path_text).is_absolute()
            or PurePosixPath(path_text).as_posix() != path_text
            or any(part in {"", "."} for part in PurePosixPath(path_text).parts)
        ):
            raise ProtocolReviewVerificationError("verifier dependency RECORD path is invalid")
        rows.append((path_text, hash_text, size_text))
    if not rows or len({item[0] for item in rows}) != len(rows):
        raise ProtocolReviewVerificationError(
            "verifier dependency RECORD paths are empty/duplicate"
        )
    return tuple(rows)


def _record_sha256(value: str) -> bytes:
    if not value.startswith("sha256="):
        raise ProtocolReviewVerificationError("verifier dependency RECORD hash is not sha256")
    encoded = value.removeprefix("sha256=")
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", encoded, flags=re.ASCII) is None:
        raise ProtocolReviewVerificationError("verifier dependency RECORD hash is not canonical")
    try:
        decoded = base64.urlsafe_b64decode(encoded + "=")
    except (ValueError, binascii.Error):
        raise ProtocolReviewVerificationError(
            "verifier dependency RECORD hash is invalid"
        ) from None
    if len(decoded) != 32:
        raise ProtocolReviewVerificationError("verifier dependency RECORD hash length mismatch")
    return decoded


def _build_verifier_dependency_inventory(
    lock_bytes: bytes,
    *,
    retain_anchors: bool = False,
) -> _VerifiedDependencyInventoryV1:
    if (
        os.name != "posix"
        or sys.implementation.name != "cpython"
        or platform.python_implementation() != "CPython"
        or sys.prefix == sys.base_prefix
    ):
        raise ProtocolReviewVerificationError(
            "verifier dependency inventory requires a POSIX CPython virtual environment"
        )
    selected = _locked_verifier_dependency_selection(lock_bytes)
    environment_descriptor, environment_root = _open_directory_no_follow(Path(sys.prefix))
    environment_identity = _stat_identity(os.fstat(environment_descriptor))
    site_descriptors: list[int] = []
    site_descriptor_by_name: dict[str, int] = {}
    site_anchors: list[tuple[int, Path, tuple[int, int, int, int, int, int, int]]] = []
    completed = False
    try:
        installed = tuple(importlib_metadata.distributions())
        distributions: dict[str, importlib_metadata.Distribution] = {}
        site_root: Path | None = None
        for name, (version, expected_dependencies) in selected.items():
            matches = tuple(
                item
                for item in installed
                if _normalized_distribution_name(item.metadata["Name"]) == name
            )
            if len(matches) != 1:
                raise ProtocolReviewVerificationError(
                    f"installed verifier dependency {name} is missing or duplicated"
                )
            distribution = matches[0]
            if distribution.metadata["Name"] != name or distribution.version != version:
                raise ProtocolReviewVerificationError(
                    f"installed verifier dependency {name} identity/version mismatch"
                )
            if _selected_installed_requirements(distribution.requires) != expected_dependencies:
                raise ProtocolReviewVerificationError(
                    f"installed verifier dependency {name} direct-dependency selection mismatch"
                )
            original_site = Path(str(distribution.locate_file("")))
            site_descriptor, resolved_site = _open_directory_no_follow(original_site)
            site_descriptors.append(site_descriptor)
            site_descriptor_by_name[name] = site_descriptor
            site_anchors.append(
                (site_descriptor, resolved_site, _stat_identity(os.fstat(site_descriptor)))
            )
            if resolved_site == environment_root or environment_root not in resolved_site.parents:
                raise ProtocolReviewVerificationError(
                    "verifier dependency site root is outside the virtual environment"
                )
            if site_root is None:
                site_root = resolved_site
            elif resolved_site != site_root:
                raise ProtocolReviewVerificationError(
                    "verifier dependencies do not share one site-packages root"
                )
            distributions[name] = distribution

        entries: list[VerifierDependencyInventoryEntryV1] = []
        paths_by_distribution: dict[str, frozenset[Path]] = {}
        global_paths: set[Path] = set()
        global_inodes: set[tuple[int, int]] = set()
        inodes_by_path: dict[Path, tuple[int, int]] = {}
        bytes_by_path: dict[Path, bytes] = {}
        assert site_root is not None
        site_relative = PurePosixPath(site_root.relative_to(environment_root).as_posix())
        for name, (version, _) in selected.items():
            distribution = distributions[name]
            files = distribution.files
            if files is None:
                raise ProtocolReviewVerificationError(
                    "installed verifier dependency lacks a complete file inventory"
                )
            file_paths = tuple(str(item) for item in files)
            record_candidates = tuple(
                item for item in file_paths if item.endswith(".dist-info/RECORD")
            )
            if len(record_candidates) != 1:
                raise ProtocolReviewVerificationError(
                    "verifier dependency requires one exact RECORD PackagePath"
                )
            record_path = record_candidates[0]
            expected_record = f"{name}-{version}.dist-info/RECORD"
            if record_path != expected_record:
                raise ProtocolReviewVerificationError(
                    "verifier dependency RECORD dist-info identity mismatch"
                )
            record_environment_relative = _environment_relative_record_path(
                site_relative, record_path
            )
            literal_record_raw, literal_record_stat = _read_inventory_member_at(
                site_descriptor_by_name[name], record_path
            )
            record_raw, canonical_record_stat = _read_inventory_member_at(
                environment_descriptor, record_environment_relative
            )
            if literal_record_raw != record_raw or _stat_identity(
                literal_record_stat
            ) != _stat_identity(canonical_record_stat):
                raise ProtocolReviewVerificationError(
                    "verifier dependency literal/canonical RECORD route mismatch"
                )
            rows = _strict_record_rows(record_raw)
            if tuple(item[0] for item in rows) != file_paths:
                raise ProtocolReviewVerificationError(
                    "verifier dependency PackagePath/RECORD inventory mismatch"
                )
            owned_paths: set[Path] = set()
            self_rows = 0
            for raw_path, record_hash, record_size in rows:
                environment_relative = _environment_relative_record_path(site_relative, raw_path)
                literal_bytes, literal_stat = _read_inventory_member_at(
                    site_descriptor_by_name[name], raw_path
                )
                raw_bytes, member_stat = _read_inventory_member_at(
                    environment_descriptor, environment_relative
                )
                if literal_bytes != raw_bytes or _stat_identity(
                    literal_stat
                ) != _stat_identity(member_stat):
                    raise ProtocolReviewVerificationError(
                        "verifier dependency literal/canonical member route mismatch"
                    )
                resolved_target = environment_root / environment_relative
                if (
                    not environment_relative
                    or PurePosixPath(environment_relative).is_absolute()
                    or any(
                        part in {"", ".", ".."}
                        for part in PurePosixPath(environment_relative).parts
                    )
                    or "\\" in environment_relative
                ):
                    raise ProtocolReviewVerificationError(
                        "verifier dependency canonical environment path is invalid"
                    )
                inode = (member_stat.st_dev, member_stat.st_ino)
                if resolved_target in global_paths or inode in global_inodes:
                    raise ProtocolReviewVerificationError(
                        "verifier dependency member path/inode aliases another inventory member"
                    )
                global_paths.add(resolved_target)
                global_inodes.add(inode)
                inodes_by_path[resolved_target] = inode
                bytes_by_path[resolved_target] = raw_bytes
                owned_paths.add(resolved_target)
                if raw_path == record_path:
                    self_rows += 1
                    if record_hash or record_size:
                        raise ProtocolReviewVerificationError(
                            "verifier dependency RECORD self row must omit hash and size"
                        )
                else:
                    if re.fullmatch(r"(?:0|[1-9][0-9]*)", record_size, flags=re.ASCII) is None:
                        raise ProtocolReviewVerificationError(
                            "verifier dependency RECORD size is not canonical"
                        )
                    if int(record_size) != len(raw_bytes) or _record_sha256(
                        record_hash
                    ) != hashlib.sha256(raw_bytes).digest():
                        raise ProtocolReviewVerificationError(
                            "verifier dependency RECORD member hash/size mismatch"
                        )
                entries.append(
                    VerifierDependencyInventoryEntryV1(
                        distribution_name=cast(Any, name),
                        distribution_version=cast(Any, version),
                        environment_relative_path=environment_relative,
                        byte_length=len(raw_bytes),
                        sha256=hashlib.sha256(raw_bytes).hexdigest(),
                    )
                )
            if self_rows != 1:
                raise ProtocolReviewVerificationError(
                    "verifier dependency RECORD self row is missing or duplicated"
                )
            paths_by_distribution[name] = frozenset(owned_paths)
        expected_claimants = {
            path: name for name, paths in paths_by_distribution.items() for path in paths
        }
        claims: dict[Path, list[str]] = {path: [] for path in expected_claimants}
        selected_path_by_inode = {inode: path for path, inode in inodes_by_path.items()}
        for distribution in installed:
            files = distribution.files
            if files is None:
                continue
            claimant = distribution.metadata["Name"]
            for package_path in files:
                try:
                    claimed_path = Path(
                        str(distribution.locate_file(str(package_path)))
                    ).resolve(strict=True)
                except (OSError, RuntimeError):
                    raise ProtocolReviewVerificationError(
                        "ambient distribution RECORD claim is unresolvable"
                    ) from None
                claimed_target = claimed_path if claimed_path in claims else None
                if claimed_target is None:
                    try:
                        claimed_stat = os.stat(claimed_path, follow_symlinks=False)
                    except OSError:
                        raise ProtocolReviewVerificationError(
                            "ambient distribution RECORD claim cannot be stated"
                        ) from None
                    claimed_target = selected_path_by_inode.get(
                        (claimed_stat.st_dev, claimed_stat.st_ino)
                    )
                if claimed_target is not None:
                    claims[claimed_target].append(claimant)
        for path, expected_name in expected_claimants.items():
            if claims[path] != [expected_name]:
                raise ProtocolReviewVerificationError(
                    "verifier dependency member has ambiguous distribution RECORD claims"
                )
        entries.sort(
            key=lambda item: (
                item.distribution_name.encode("utf-8"),
                item.distribution_version.encode("utf-8"),
                item.environment_relative_path.encode("utf-8"),
            )
        )
        root = protocol_review_digest(
            "laconian-verifier-dependency-inventory-root-v1",
            {
                "os_name": "posix",
                "implementation_name": "cpython",
                "platform_python_implementation": "CPython",
                "environment_kind": "virtualenv",
                "selection": _VERIFIER_DEPENDENCY_SELECTION_PROJECTION_V1,
                "entries": [item.model_dump(mode="json") for item in entries],
            },
        )
        result = _VerifiedDependencyInventoryV1(
            root=root,
            entries=tuple(entries),
            paths_by_distribution=MappingProxyType(paths_by_distribution),
            bytes_by_path=MappingProxyType(bytes_by_path),
            distributions=MappingProxyType(distributions),
            retained_anchors=(
                (environment_descriptor, environment_root, environment_identity), *site_anchors
            ),
        )
        if not retain_anchors:
            _verify_inventory_anchors(result)
        completed = True
        return result
    finally:
        if not retain_anchors or not completed:
            for descriptor in site_descriptors:
                os.close(descriptor)
            os.close(environment_descriptor)


def compute_verifier_dependency_inventory_root(lock_bytes: bytes) -> str:
    if type(lock_bytes) is not bytes:
        raise ProtocolReviewVerificationError("verifier dependency lock must be exact bytes")
    return _build_verifier_dependency_inventory(lock_bytes).root


def _verify_inventory_anchors(inventory: _VerifiedDependencyInventoryV1) -> None:
    for descriptor, path, expected in inventory.retained_anchors:
        fresh_descriptor = -1
        try:
            descriptor_identity = _stat_identity(os.fstat(descriptor))
            fresh_descriptor, fresh_resolved = _open_directory_no_follow(path)
            fresh_identity = _stat_identity(os.fstat(fresh_descriptor))
            if (
                descriptor_identity != expected
                or fresh_identity != expected
                or fresh_resolved != path
            ):
                raise ProtocolReviewVerificationError(
                    "verifier dependency retained directory anchor changed"
                )
        except OSError as cause:
            raise ProtocolReviewVerificationError(
                "verifier dependency retained directory anchor is unavailable"
            ) from cause
        finally:
            if fresh_descriptor >= 0:
                os.close(fresh_descriptor)


def _verify_and_close_inventory_anchors(inventory: _VerifiedDependencyInventoryV1) -> None:
    error: Exception | None = None
    try:
        _verify_inventory_anchors(inventory)
    except Exception as cause:
        error = cause
    for descriptor, _, _ in reversed(inventory.retained_anchors):
        os.close(descriptor)
    if error is not None:
        raise error


class _VerifiedSourceLoader(importlib.abc.Loader):
    def __init__(self, filename: str, source: bytes) -> None:
        self.filename = filename
        self.source = source

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        module.__file__ = self.filename
        module.__dict__["__cached__"] = None
        exec(compile(self.source, self.filename, "exec", dont_inherit=True), module.__dict__)


class _VerifiedExtensionLoader(importlib.abc.Loader):
    def __init__(
        self,
        wrapped: importlib.machinery.ExtensionFileLoader,
        environment_descriptor: int,
        environment_relative: str,
        expected_bytes: bytes,
    ) -> None:
        self.wrapped = wrapped
        self.environment_descriptor = environment_descriptor
        self.environment_relative = environment_relative
        self.expected_bytes = expected_bytes
        self._descriptor = -1
        self._inner: importlib.machinery.ExtensionFileLoader | None = None
        self._inner_spec: importlib.machinery.ModuleSpec | None = None
        self._temporary_directory: str | None = None
        self._temporary_path: str | None = None

    def _capture(self, name: str) -> None:
        temporary_directory: str | None = None
        temporary_path: str | None = None
        directory_descriptor = -1
        writer = -1
        descriptor = -1
        basename = Path(self.wrapped.path).name
        try:
            temporary_directory = tempfile.mkdtemp(prefix="laconian-extension-")
            os.chmod(temporary_directory, 0o700)
            directory_descriptor = os.open(
                temporary_directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            temporary_path = str(Path(temporary_directory) / basename)
            writer = os.open(
                basename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o500,
                dir_fd=directory_descriptor,
            )
            view = memoryview(self.expected_bytes)
            while view:
                written = os.write(writer, view)
                if written <= 0:
                    raise ImportError("verified extension snapshot write failed")
                view = view[written:]
            os.fsync(writer)
            os.close(writer)
            writer = -1
            os.chmod(basename, 0o500, dir_fd=directory_descriptor, follow_symlinks=False)
            descriptor = os.open(
                basename,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_descriptor,
            )
            captured = b""
            while chunk := os.read(descriptor, 1_048_576):
                captured += chunk
            if captured != self.expected_bytes:
                raise ImportError("verified extension private snapshot mismatch")
            os.lseek(descriptor, 0, os.SEEK_SET)
            if _stat_identity(os.fstat(descriptor)) != _stat_identity(
                os.stat(basename, dir_fd=directory_descriptor, follow_symlinks=False)
            ):
                raise ImportError("verified extension private path/fd identity mismatch")
            os.close(directory_descriptor)
            directory_descriptor = -1
            self._descriptor = descriptor
            descriptor = -1
            self._temporary_directory = temporary_directory
            self._temporary_path = temporary_path
            aliases = (
                f"/dev/fd/{self._descriptor}",
                f"/proc/self/fd/{self._descriptor}",
            )
            alias = next((item for item in aliases if os.path.exists(item)), None)
            if alias is None:
                raise ImportError("verified extension fd alias is unavailable")
            alias_stat = os.stat(alias)
            descriptor_stat = os.fstat(self._descriptor)
            if (
                alias_stat.st_ino,
                alias_stat.st_size,
                alias_stat.st_mtime_ns,
                alias_stat.st_ctime_ns,
            ) != (
                descriptor_stat.st_ino,
                descriptor_stat.st_size,
                descriptor_stat.st_mtime_ns,
                descriptor_stat.st_ctime_ns,
            ):
                raise ImportError("verified extension fd alias identity mismatch")
            self._inner = importlib.machinery.ExtensionFileLoader(name, alias)
            self._inner_spec = importlib.util.spec_from_loader(
                name, self._inner, origin=alias
            )
            if self._inner_spec is None:
                raise ImportError("verified extension private spec construction failed")
        except BaseException:
            if writer >= 0:
                with suppress(OSError):
                    os.close(writer)
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
            if directory_descriptor >= 0:
                with suppress(OSError):
                    os.close(directory_descriptor)
            self._close()
            if temporary_path is not None:
                with suppress(OSError):
                    os.unlink(temporary_path)
            if temporary_directory is not None:
                with suppress(OSError):
                    os.rmdir(temporary_directory)
            raise

    def _close(self) -> None:
        if self._descriptor >= 0:
            with suppress(OSError):
                os.close(self._descriptor)
            self._descriptor = -1
        if self._temporary_path is not None:
            with suppress(OSError):
                os.unlink(self._temporary_path)
            self._temporary_path = None
        if self._temporary_directory is not None:
            with suppress(OSError):
                os.rmdir(self._temporary_directory)
            self._temporary_directory = None

    def _verify_private_identity(self) -> None:
        if self._descriptor < 0 or self._temporary_path is None or _stat_identity(
            os.fstat(self._descriptor)
        ) != _stat_identity(os.stat(self._temporary_path, follow_symlinks=False)):
            raise ImportError("verified extension private path/fd identity changed")

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType | None:
        self._capture(spec.name)
        assert self._inner is not None and self._inner_spec is not None
        try:
            module = self._inner.create_module(self._inner_spec)
            self._verify_private_identity()
            return module
        except Exception:
            self._close()
            raise

    def exec_module(self, module: ModuleType) -> None:
        assert self._inner is not None
        try:
            self._verify_private_identity()
            self._inner.exec_module(module)
            self._verify_private_identity()
            module.__file__ = self.wrapped.path
            if module.__spec__ is not None:
                module.__spec__.origin = self.wrapped.path
        finally:
            self._close()


_VERIFIER_GOVERNED_MODULE_ROOTS = ("cryptography", "cffi", "pycparser")


def _is_verifier_governed_module(name: str) -> bool:
    return name == "_cffi_backend" or any(
        name == root or name.startswith(f"{root}.")
        for root in _VERIFIER_GOVERNED_MODULE_ROOTS
    )


class _VerifiedSourceFinder(importlib.abc.MetaPathFinder):
    def __init__(
        self,
        sources: Mapping[Path, bytes],
        selected_paths: frozenset[Path],
        environment_descriptor: int | None = None,
        environment_root: Path | None = None,
    ) -> None:
        self.sources = sources
        self.selected_paths = selected_paths
        self.environment_descriptor = environment_descriptor
        self.environment_root = environment_root

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not _is_verifier_governed_module(fullname):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or type(spec.origin) is not str:
            raise ImportError(f"governed verifier module {fullname} lacks an exact file spec")
        try:
            origin = Path(spec.origin).resolve(strict=True)
        except (OSError, RuntimeError):
            raise ImportError(
                f"governed verifier module {fullname} origin is unavailable"
            ) from None
        if origin not in self.selected_paths:
            raise ImportError(f"governed verifier module {fullname} origin is outside inventory")
        source = self.sources.get(origin)
        if origin.suffix != ".py":
            if any(
                str(origin).endswith(suffix)
                for suffix in importlib.machinery.EXTENSION_SUFFIXES
            ):
                if (
                    type(spec.loader) is not importlib.machinery.ExtensionFileLoader
                    or self.environment_descriptor is None
                    or self.environment_root is None
                    or source is None
                ):
                    raise ImportError(
                        f"governed verifier extension {fullname} lacks a verified loader"
                    )
                try:
                    environment_relative = origin.relative_to(
                        self.environment_root
                    ).as_posix()
                except ValueError:
                    raise ImportError(
                        f"governed verifier extension {fullname} escapes environment"
                    ) from None
                spec.loader = _VerifiedExtensionLoader(
                    spec.loader,
                    self.environment_descriptor,
                    environment_relative,
                    source,
                )
                return spec
            raise ImportError(f"governed verifier module {fullname} has unsupported file type")
        if source is None:
            raise ImportError(f"governed verifier module {fullname} lacks verified source bytes")
        replacement = importlib.util.spec_from_loader(
            fullname,
            _VerifiedSourceLoader(str(origin), source),
            origin=str(origin),
            is_package=spec.submodule_search_locations is not None,
        )
        if replacement is not None and spec.submodule_search_locations is not None:
            replacement.submodule_search_locations = spec.submodule_search_locations
        return replacement


@dataclass(frozen=True, slots=True)
class _CommittedSelectedModuleTrust:
    inventory_root: str
    snapshot: dict[str, tuple[ModuleType, str]]


_POISONED_SELECTED_MODULE_TRUST = object()
_VERIFIED_SELECTED_MODULE_SNAPSHOT: _CommittedSelectedModuleTrust | object | None = None


@dataclass(frozen=True, slots=True)
class _PendingSelectedModuleTrust:
    snapshot: dict[str, tuple[ModuleType, str]]
    newly_added: tuple[tuple[str, object], ...]


def _selected_loaded_module_snapshot(
    selected_paths: frozenset[Path],
) -> dict[str, tuple[ModuleType, str]]:
    result: dict[str, tuple[ModuleType, str]] = {}
    for name, value in sys.modules.items():
        if not _is_verifier_governed_module(name):
            continue
        if type(value) is not ModuleType:
            raise ProtocolReviewVerificationError(
                "governed verifier dependency is not an exact module"
            )
        origin = getattr(getattr(value, "__spec__", None), "origin", None)
        module_file = getattr(value, "__file__", None)
        if type(origin) is not str or type(module_file) is not str:
            raise ProtocolReviewVerificationError(
                "governed verifier dependency lacks an exact origin"
            )
        try:
            resolved = Path(origin).resolve(strict=True)
        except (OSError, RuntimeError):
            raise ProtocolReviewVerificationError(
                "governed verifier dependency origin is unavailable"
            ) from None
        if Path(module_file).resolve() != resolved or resolved not in selected_paths:
            raise ProtocolReviewVerificationError(
                "governed verifier dependency origin is outside verified inventory"
            )
        result[name] = (value, str(resolved))
    return result


def _source_only_selected_imports(
    inventory: _VerifiedDependencyInventoryV1,
) -> _PendingSelectedModuleTrust:
    global _VERIFIED_SELECTED_MODULE_SNAPSHOT
    trust = _VERIFIED_SELECTED_MODULE_SNAPSHOT
    if trust is _POISONED_SELECTED_MODULE_TRUST:
        raise ProtocolReviewVerificationError(
            "verifier dependency import trust is poisoned; process restart required"
        )
    if isinstance(trust, _CommittedSelectedModuleTrust) and inventory.root != trust.inventory_root:
        raise ProtocolReviewVerificationError(
            "verified dependency root/module-object/origin trust changed"
        )
    selected_paths = frozenset().union(*inventory.paths_by_distribution.values())
    current = _selected_loaded_module_snapshot(selected_paths)
    if isinstance(trust, _CommittedSelectedModuleTrust):
        if current != trust.snapshot:
            raise ProtocolReviewVerificationError(
                "verified dependency root/module-object/origin trust changed"
            )
        _verify_loaded_cryptography_modules(
            inventory.distributions["cryptography"],
            verified_paths=inventory.paths_by_distribution["cryptography"],
        )
        return _PendingSelectedModuleTrust(snapshot=current, newly_added=())
    if current:
        raise ProtocolReviewVerificationError(
            "selected verifier dependency module was preloaded before source verification"
        )
    before_names = frozenset(sys.modules)
    environment_descriptor, environment_root, _ = inventory.retained_anchors[0]
    finder = _VerifiedSourceFinder(
        inventory.bytes_by_path,
        selected_paths,
        environment_descriptor,
        environment_root,
    )
    sys.meta_path.insert(0, finder)
    try:
        _load_verified_ed25519_primitives(
            inventory.distributions["cryptography"],
            verified_paths=inventory.paths_by_distribution["cryptography"],
        )
        current = _selected_loaded_module_snapshot(selected_paths)
        if not current:
            raise ProtocolReviewVerificationError(
                "source-only verifier import loaded no selected modules"
            )
        return _PendingSelectedModuleTrust(
            snapshot=current,
            newly_added=tuple(
                (name, value) for name, value in sys.modules.items() if name not in before_names
            ),
        )
    except Exception:
        _VERIFIED_SELECTED_MODULE_SNAPSHOT = _POISONED_SELECTED_MODULE_TRUST
        for name in tuple(sys.modules):
            if name not in before_names:
                sys.modules.pop(name, None)
        raise
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)


def _verify_loaded_cryptography_modules(
    distribution: importlib_metadata.Distribution,
    *,
    verified_paths: frozenset[Path] | None = None,
) -> tuple[Callable[[bytes], object], type[object]]:
    if verified_paths is None:
        files = distribution.files
        if files is None:
            raise ProtocolReviewVerificationError(
                "installed verifier dependency lacks a complete file inventory"
            )
        distribution_paths = frozenset(
            Path(str(distribution.locate_file(str(item)))).resolve() for item in files
        )
    else:
        distribution_paths = verified_paths
    required_modules = (
        "cryptography",
        "cryptography.exceptions",
        "cryptography.hazmat.bindings._rust",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
    )
    if any(name not in sys.modules for name in required_modules):
        raise ProtocolReviewVerificationError(
            "required cryptography verifier modules are not loaded"
        )
    module_origins: set[Path] = set()
    for name in required_modules:
        module = sys.modules[name]
        if type(module) is not ModuleType:
            raise ProtocolReviewVerificationError(
                "preloaded cryptography verifier module is not an exact module"
            )
        module_file = getattr(module, "__file__", None)
        if type(module_file) is not str:
            raise ProtocolReviewVerificationError(
                "preloaded cryptography verifier module lacks a file identity"
            )
        candidate = Path(module_file)
        resolved_candidate = candidate.resolve()
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or resolved_candidate not in distribution_paths
            or resolved_candidate in module_origins
        ):
            raise ProtocolReviewVerificationError(
                "preloaded cryptography verifier module identity mismatch"
            )
        module_origins.add(resolved_candidate)
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        if type(origin) is not str or Path(origin).resolve() != resolved_candidate:
            raise ProtocolReviewVerificationError(
                "preloaded cryptography verifier module origin mismatch"
            )
    rust_module = sys.modules["cryptography.hazmat.bindings._rust"]
    ed25519_module = sys.modules["cryptography.hazmat.primitives.asymmetric.ed25519"]
    openssl_module = getattr(rust_module, "openssl", None)
    rust_ed25519_module = getattr(openssl_module, "ed25519", None)
    rust_factory = getattr(rust_ed25519_module, "from_public_bytes", None)
    rust_public_type = getattr(rust_ed25519_module, "Ed25519PublicKey", None)
    rust_verify = (
        None
        if type(rust_public_type) is not type
        else rust_public_type.__dict__.get("verify")
    )
    if (
        type(openssl_module) is not ModuleType
        or getattr(openssl_module, "__name__", None) != "_rust.openssl"
        or type(rust_ed25519_module) is not ModuleType
        or getattr(rust_ed25519_module, "__name__", None) != "ed25519"
        or type(rust_factory) is not BuiltinFunctionType
        or getattr(rust_factory, "__name__", None) != "from_public_bytes"
        or type(rust_public_type) is not type
        or rust_public_type.__module__
        != "cryptography.hazmat.bindings._rust.openssl.ed25519"
        or rust_public_type.__name__ != "Ed25519PublicKey"
        or type(rust_verify) is not MethodDescriptorType
    ):
        raise ProtocolReviewVerificationError(
            "active cryptography Rust Ed25519 primitive identity mismatch"
        )
    public_type = getattr(ed25519_module, "Ed25519PublicKey", None)
    public_factory_descriptor = (
        None if type(public_type) is not ABCMeta else public_type.__dict__.get("from_public_bytes")
    )
    public_factory = (
        None
        if type(public_factory_descriptor) is not classmethod
        else public_factory_descriptor.__func__
    )
    module_file = cast(str, ed25519_module.__file__)
    if (
        type(public_type) is not ABCMeta
        or public_type.__module__ != "cryptography.hazmat.primitives.asymmetric.ed25519"
        or public_type.__name__ != "Ed25519PublicKey"
        or type(public_factory_descriptor) is not classmethod
        or type(public_factory) is not FunctionType
        or public_factory.__module__
        != "cryptography.hazmat.primitives.asymmetric.ed25519"
        or Path(public_factory.__code__.co_filename).resolve() != Path(module_file).resolve()
        or public_factory.__globals__.get("rust_openssl") is not openssl_module
    ):
        raise ProtocolReviewVerificationError(
            "active cryptography public Ed25519 primitive identity mismatch"
        )
    return cast(Callable[[bytes], object], rust_factory), cast(type[object], rust_public_type)


def _load_verified_ed25519_primitives(
    distribution: importlib_metadata.Distribution,
    *,
    verified_paths: frozenset[Path] | None = None,
) -> tuple[Callable[[bytes], object], type[object]]:
    for module_name in (
        "cryptography",
        "cryptography.exceptions",
        "cryptography.hazmat.bindings._rust",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
    ):
        try:
            importlib.import_module(module_name)
        except (ImportError, AttributeError, TypeError, ValueError) as error:
            raise ProtocolReviewVerificationError(
                "required cryptography verifier module could not be loaded"
            ) from error
    return _verify_loaded_cryptography_modules(distribution, verified_paths=verified_paths)


def _verify_installed_verifier_dependency_inventory(
    lock_bytes: bytes, expected_root: str
) -> None:
    global _VERIFIED_SELECTED_MODULE_SNAPSHOT
    before = _build_verifier_dependency_inventory(lock_bytes, retain_anchors=True)
    pending: _PendingSelectedModuleTrust | None = None
    try:
        if before.root != expected_root:
            raise ProtocolReviewVerificationError("verifier dependency inventory root mismatch")
        pending = _source_only_selected_imports(before)
        providers = importlib_metadata.packages_distributions().get("cryptography")
        if providers != ["cryptography"]:
            raise ProtocolReviewVerificationError(
                "cryptography package-to-distribution provider mapping mismatch"
            )
        after = _build_verifier_dependency_inventory(lock_bytes)
        if after.root != expected_root or after.entries != before.entries:
            raise ProtocolReviewVerificationError(
                "verifier dependency inventory changed during verified import"
            )
    except BaseException as primary:
        if pending is not None:
            _VERIFIED_SELECTED_MODULE_SNAPSHOT = _POISONED_SELECTED_MODULE_TRUST
            for name, value in pending.newly_added:
                if sys.modules.get(name) is value:
                    sys.modules.pop(name, None)
        try:
            _verify_and_close_inventory_anchors(before)
        except Exception as anchor_error:
            primary.add_note(f"retained-anchor cleanup also failed: {anchor_error}")
        raise
    else:
        try:
            _verify_and_close_inventory_anchors(before)
        except Exception:
            if pending is not None:
                _VERIFIED_SELECTED_MODULE_SNAPSHOT = _POISONED_SELECTED_MODULE_TRUST
                for name, value in pending.newly_added:
                    if sys.modules.get(name) is value:
                        sys.modules.pop(name, None)
            raise
        assert pending is not None
        if _VERIFIED_SELECTED_MODULE_SNAPSHOT is None:
            _VERIFIED_SELECTED_MODULE_SNAPSHOT = _CommittedSelectedModuleTrust(
                inventory_root=before.root,
                snapshot=pending.snapshot,
            )


def _verify_active_verifier_runtime(
    identity: ProtocolReviewIdentityRegistryBundleV1,
) -> tuple[bytes, bytes]:
    module = sys.modules.get(__name__)
    module_file = getattr(module, "__file__", None)
    expected_module_path = (
        Path(__file__).resolve().parents[3] / identity.verifier_source_path
    ).resolve()
    if (
        type(module) is not ModuleType
        or type(module_file) is not str
        or Path(module_file).resolve() != expected_module_path
    ):
        raise ProtocolReviewVerificationError(
            "preloaded protocol verifier module identity mismatch"
        )
    source = _read_exact_active_file(identity.verifier_source_path, identity.verifier_source_sha256)
    lock = _read_exact_active_file(identity.dependency_lock_path, identity.dependency_lock_sha256)
    _verify_installed_verifier_dependency_inventory(
        lock, identity.verifier_dependency_inventory_root
    )
    return source, lock


def _load_identity_registry_bundle(
    *,
    flattened: Mapping[str, tuple[str, str]],
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    protocol_reviewer_registry: ProtocolReviewerRegistryV1,
) -> ProtocolReviewIdentityRegistryBundleV1:
    identity_path = "benchmark/security/protocol-review-identity-registry.json"
    identity_blob = _c0_blob(flattened, objects, identity_path)
    identity = ProtocolReviewIdentityRegistryBundleV1.model_validate(
        parse_canonical_json_v1(identity_blob)
    )
    if canonical_json_v1(identity.model_dump(mode="json")) != identity_blob:
        raise ProtocolReviewVerificationError("C0 identity-registry bundle is not canonical JSON")
    source_blob = _c0_blob(flattened, objects, identity.verifier_source_path)
    lock_blob = _c0_blob(flattened, objects, identity.dependency_lock_path)
    if (
        hashlib.sha256(source_blob).hexdigest() != identity.verifier_source_sha256
        or hashlib.sha256(lock_blob).hexdigest() != identity.dependency_lock_sha256
    ):
        raise ProtocolReviewVerificationError("C0 identity-registry source/lock digest mismatch")
    expected_keys = tuple(
        reviewer
        for reviewer in protocol_reviewer_registry.reviewers
        if reviewer.verification_mode != "github_verified_commit"
    )
    if len(identity.keys) != len(expected_keys):
        raise ProtocolReviewVerificationError(
            "identity-registry keys do not exactly cover keyed reviewers"
        )
    for key, reviewer in zip(identity.keys, expected_keys, strict=True):
        if (
            key.role != reviewer.role
            or key.reviewer_numeric_account_id != reviewer.reviewer_numeric_account_id
            or key.reviewer_login != reviewer.reviewer_login
            or key.verification_mode != reviewer.verification_mode
            or key.fingerprint != reviewer.signing_fingerprint
        ):
            raise ProtocolReviewVerificationError(
                "identity-registry key does not match its protocol reviewer"
            )
    active_source, active_lock = _verify_active_verifier_runtime(identity)
    if active_source != source_blob:
        raise ProtocolReviewVerificationError("active verifier source differs from C0 member")
    if active_lock != lock_blob:
        raise ProtocolReviewVerificationError("active dependency lock differs from C0 member")
    return identity


def _ssh_string(value: bytes) -> bytes:
    return len(value).to_bytes(4, "big") + value


def _read_ssh_string(raw: bytes, cursor: int) -> tuple[bytes, int]:
    if cursor + 4 > len(raw):
        raise ProtocolReviewVerificationError("truncated SSH string length")
    length = int.from_bytes(raw[cursor : cursor + 4], "big")
    cursor += 4
    if cursor + length > len(raw):
        raise ProtocolReviewVerificationError("truncated SSH string body")
    return raw[cursor : cursor + length], cursor + length


def _decode_exact_armor(
    raw: bytes,
    *,
    begin: bytes,
    end: bytes,
    wrap: int,
    blank_after_begin: bool,
    require_crc24: bool,
) -> bytes:
    if b"\r" in raw or b"\0" in raw or not raw.endswith(b"\n"):
        raise ProtocolReviewVerificationError(
            "signature armor must be LF-only with one terminal LF"
        )
    lines = raw.split(b"\n")
    if lines[-1] != b"" or lines[0] != begin or lines[-2] != end:
        raise ProtocolReviewVerificationError("signature armor delimiters/terminal LF mismatch")
    cursor = 1
    if blank_after_begin:
        if cursor >= len(lines) or lines[cursor] != b"":
            raise ProtocolReviewVerificationError("OpenPGP armor requires one header separator")
        cursor += 1
    body_end = len(lines) - 2
    crc_line: bytes | None = None
    if require_crc24:
        if body_end <= cursor or not lines[body_end - 1].startswith(b"="):
            raise ProtocolReviewVerificationError("OpenPGP armor requires a CRC-24 line")
        crc_line = lines[body_end - 1]
        body_end -= 1
    body_lines = lines[cursor:body_end]
    if not body_lines or any(not line for line in body_lines):
        raise ProtocolReviewVerificationError("signature armor body is empty or contains blanks")
    if any(len(line) != wrap for line in body_lines[:-1]) or not 1 <= len(body_lines[-1]) <= wrap:
        raise ProtocolReviewVerificationError("signature armor has noncanonical base64 wrapping")
    encoded = b"".join(body_lines)
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except binascii.Error:
        raise ProtocolReviewVerificationError("signature armor base64 is invalid") from None
    if base64.b64encode(decoded) != encoded:
        raise ProtocolReviewVerificationError("signature armor base64 is not canonical")
    if crc_line is not None:
        if len(crc_line) != 5:
            raise ProtocolReviewVerificationError("OpenPGP armor CRC-24 spelling is invalid")
        try:
            supplied_crc = base64.b64decode(crc_line[1:], validate=True)
        except binascii.Error:
            raise ProtocolReviewVerificationError(
                "OpenPGP armor CRC-24 is invalid base64"
            ) from None
        if base64.b64encode(supplied_crc) != crc_line[1:] or supplied_crc != _openpgp_crc24(
            decoded
        ).to_bytes(3, "big"):
            raise ProtocolReviewVerificationError("OpenPGP armor CRC-24 mismatch")
    return decoded


def _openpgp_crc24(raw: bytes) -> int:
    crc = 0xB704CE
    for byte in raw:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


def _one_openpgp_packet(raw: bytes, expected_tag: int) -> bytes:
    if not raw or raw[0] & 0x80 == 0:
        raise ProtocolReviewVerificationError("OpenPGP body lacks a packet header")
    first = raw[0]
    cursor = 1
    if first & 0x40:
        tag = first & 0x3F
        if cursor >= len(raw):
            raise ProtocolReviewVerificationError("truncated OpenPGP packet length")
        first_length = raw[cursor]
        cursor += 1
        if first_length < 192:
            length = first_length
        elif first_length < 224:
            if cursor >= len(raw):
                raise ProtocolReviewVerificationError("truncated OpenPGP packet length")
            length = ((first_length - 192) << 8) + raw[cursor] + 192
            cursor += 1
        elif first_length == 255:
            if cursor + 4 > len(raw):
                raise ProtocolReviewVerificationError("truncated OpenPGP packet length")
            length = int.from_bytes(raw[cursor : cursor + 4], "big")
            cursor += 4
        else:
            raise ProtocolReviewVerificationError("partial OpenPGP packet lengths are forbidden")
    else:
        tag = (first >> 2) & 0x0F
        length_type = first & 0x03
        if length_type == 3:
            raise ProtocolReviewVerificationError("indeterminate OpenPGP lengths are forbidden")
        length_octets = (1, 2, 4)[length_type]
        if cursor + length_octets > len(raw):
            raise ProtocolReviewVerificationError("truncated OpenPGP packet length")
        length = int.from_bytes(raw[cursor : cursor + length_octets], "big")
        cursor += length_octets
    if tag != expected_tag or cursor + length != len(raw) or length == 0:
        raise ProtocolReviewVerificationError(
            "OpenPGP armor must contain exactly one expected packet"
        )
    return raw[cursor:]


def _validate_github_signature_armor(signature: bytes) -> None:
    packet = _decode_exact_armor(
        signature,
        begin=b"-----BEGIN PGP SIGNATURE-----",
        end=b"-----END PGP SIGNATURE-----",
        wrap=64,
        blank_after_begin=True,
        require_crc24=True,
    )
    body = _one_openpgp_packet(packet, 2)
    if not body or body[0] != 4:
        raise ProtocolReviewVerificationError("GitHub OpenPGP signature packet must be v4")
    # RFC 4880 v4 signature packets have a fixed five-field prefix followed by
    # hashed/unhashed subpacket areas, the digest prefix, and one or more MPIs.
    if len(body) < 10:
        raise ProtocolReviewVerificationError("truncated GitHub OpenPGP v4 Signature packet")
    public_key_algorithm = body[2]
    expected_mpi_count = {
        1: 1,  # RSA (encrypt or sign)
        2: 1,  # RSA (encrypt only)
        3: 1,  # RSA (sign only)
        17: 2,  # DSA
        19: 2,  # ECDSA
        22: 2,  # EdDSA
    }.get(public_key_algorithm)
    if expected_mpi_count is None:
        raise ProtocolReviewVerificationError(
            "GitHub OpenPGP v4 Signature packet uses an unsupported public-key algorithm"
        )
    cursor = 4  # version, signature type, public-key algorithm, hash algorithm
    hashed_length = int.from_bytes(body[cursor : cursor + 2], "big")
    cursor += 2
    if cursor + hashed_length + 2 + 2 > len(body):
        raise ProtocolReviewVerificationError("truncated GitHub OpenPGP v4 Signature packet")
    cursor += hashed_length
    unhashed_length = int.from_bytes(body[cursor : cursor + 2], "big")
    cursor += 2
    if cursor + unhashed_length + 2 >= len(body):
        raise ProtocolReviewVerificationError("truncated GitHub OpenPGP v4 Signature packet")
    cursor += unhashed_length + 2  # unhashed subpackets, left 16 digest bits
    mpi_count = 0
    while cursor < len(body):
        _, cursor = _read_openpgp_mpi(body, cursor)
        mpi_count += 1
    if mpi_count != expected_mpi_count:
        raise ProtocolReviewVerificationError(
            "GitHub OpenPGP v4 Signature packet public-key algorithm "
            f"{public_key_algorithm} requires exactly {expected_mpi_count} MPIs"
        )


class _Ed25519Verifier(Protocol):
    def verify(self, signature: bytes, message: bytes) -> None: ...


def _verify_ed25519(public_key: bytes, signature: bytes, message: bytes) -> None:
    if len(public_key) != 32 or len(signature) != 64 or type(message) is not bytes:
        raise ProtocolReviewVerificationError("Ed25519 verifier input length/type mismatch")
    try:
        distribution = importlib_metadata.distribution("cryptography")
    except importlib_metadata.PackageNotFoundError:
        raise ProtocolReviewVerificationError(
            "required verifier dependency cryptography is not installed"
        ) from None
    installed_name: object = distribution.metadata["Name"]
    if (
        type(installed_name) is not str
        or _normalized_distribution_name(installed_name) != "cryptography"
        or distribution.version != "50.0.1"
    ):
        raise ProtocolReviewVerificationError(
            "installed verifier dependency cryptography identity/version mismatch"
        )
    factory, rust_public_type = _load_verified_ed25519_primitives(distribution)
    try:
        verifier = factory(public_key)
        if type(verifier) is not rust_public_type:
            raise ProtocolReviewVerificationError(
                "cryptography Ed25519 factory did not return its exact Rust verifier type"
            )
        cast(_Ed25519Verifier, verifier).verify(signature, message)
    except ProtocolReviewVerificationError:
        raise
    except Exception:
        raise ProtocolReviewVerificationError("Ed25519 signature verification failed") from None


def _ssh_public_key_fingerprint(key_bytes: bytes) -> str:
    algorithm, cursor = _read_ssh_string(key_bytes, 0)
    public_key, cursor = _read_ssh_string(key_bytes, cursor)
    if algorithm != b"ssh-ed25519" or len(public_key) != 32 or cursor != len(key_bytes):
        raise ProtocolReviewVerificationError(
            "signing key is not one canonical ssh-ed25519 wire blob"
        )
    return "SHA256:" + base64.b64encode(hashlib.sha256(key_bytes).digest()).decode(
        "ascii"
    ).rstrip("=")


def _verify_ssh_signature(key_bytes: bytes, signature: bytes, signed_payload: bytes) -> str:
    fingerprint = _ssh_public_key_fingerprint(key_bytes)
    _, cursor = _read_ssh_string(key_bytes, 0)
    public_key, _ = _read_ssh_string(key_bytes, cursor)
    decoded = _decode_exact_armor(
        signature,
        begin=b"-----BEGIN SSH SIGNATURE-----",
        end=b"-----END SSH SIGNATURE-----",
        wrap=70,
        blank_after_begin=False,
        require_crc24=False,
    )
    if not decoded.startswith(b"SSHSIG") or len(decoded) < 10:
        raise ProtocolReviewVerificationError("decoded SSH signature lacks SSHSIG magic")
    if int.from_bytes(decoded[6:10], "big") != 1:
        raise ProtocolReviewVerificationError("decoded SSH signature version mismatch")
    cursor = 10
    embedded_key, cursor = _read_ssh_string(decoded, cursor)
    namespace, cursor = _read_ssh_string(decoded, cursor)
    reserved, cursor = _read_ssh_string(decoded, cursor)
    hash_algorithm, cursor = _read_ssh_string(decoded, cursor)
    signature_blob, cursor = _read_ssh_string(decoded, cursor)
    if (
        cursor != len(decoded)
        or embedded_key != key_bytes
        or namespace != b"git"
        or reserved != b""
        or hash_algorithm != b"sha512"
    ):
        raise ProtocolReviewVerificationError("decoded SSHSIG fields do not match frozen profile")
    signature_algorithm, signature_cursor = _read_ssh_string(signature_blob, 0)
    raw_signature, signature_cursor = _read_ssh_string(signature_blob, signature_cursor)
    if (
        signature_algorithm != b"ssh-ed25519"
        or signature_cursor != len(signature_blob)
        or len(raw_signature) != 64
    ):
        raise ProtocolReviewVerificationError("decoded SSHSIG signature blob is invalid")
    preimage = (
        b"SSHSIG"
        + _ssh_string(b"git")
        + _ssh_string(b"")
        + _ssh_string(b"sha512")
        + _ssh_string(hashlib.sha512(signed_payload).digest())
    )
    _verify_ed25519(public_key, raw_signature, preimage)
    return fingerprint


_OPENPGP_ED25519_LEGACY_OID = bytes.fromhex("2b06010401da470f01")
_OPENPGP_RECOGNIZED_SUBPACKETS = frozenset({2, 3, 9, 16, 27, 32, 33})


@dataclass(frozen=True, slots=True)
class _OpenPGPPacket:
    tag: int
    body: bytes


@dataclass(frozen=True, slots=True)
class _OpenPGPKeyMaterial:
    body: bytes
    public_key: bytes
    fingerprint: str
    created_at: int


@dataclass(frozen=True, slots=True)
class _OpenPGPSignature:
    signature_type: int
    issuer_fingerprint: str
    created_at: int
    signature_expiration: int | None
    key_expiration: int | None
    key_flags: int | None
    embedded_signatures: tuple[bytes, ...]
    signed_header: bytes
    hash_prefix: bytes
    raw_signature: bytes


@dataclass(frozen=True, slots=True)
class _OpenPGPSigningKey:
    public_key: bytes
    fingerprint: str
    created_at: int
    expires_at: int | None


def _read_openpgp_length(raw: bytes, cursor: int) -> tuple[int, int]:
    if cursor >= len(raw):
        raise ProtocolReviewVerificationError("truncated OpenPGP length")
    first = raw[cursor]
    cursor += 1
    if first < 192:
        return first, cursor
    if first < 224:
        if cursor >= len(raw):
            raise ProtocolReviewVerificationError("truncated OpenPGP length")
        length = ((first - 192) << 8) + raw[cursor] + 192
        return length, cursor + 1
    if first == 255:
        if cursor + 4 > len(raw):
            raise ProtocolReviewVerificationError("truncated OpenPGP length")
        length = int.from_bytes(raw[cursor : cursor + 4], "big")
        if length <= 8_383:
            raise ProtocolReviewVerificationError("noncanonical five-octet OpenPGP length")
        return length, cursor + 4
    raise ProtocolReviewVerificationError("partial OpenPGP lengths are forbidden")


def _parse_openpgp_packets(raw: bytes) -> tuple[_OpenPGPPacket, ...]:
    cursor = 0
    packets: list[_OpenPGPPacket] = []
    while cursor < len(raw):
        first = raw[cursor]
        cursor += 1
        if first & 0x80 == 0:
            raise ProtocolReviewVerificationError("OpenPGP packet lacks a packet-tag bit")
        if first & 0x40:
            tag = first & 0x3F
            length, cursor = _read_openpgp_length(raw, cursor)
        else:
            tag = (first >> 2) & 0x0F
            length_type = first & 0x03
            if length_type == 3:
                raise ProtocolReviewVerificationError(
                    "indeterminate OpenPGP packet lengths are forbidden"
                )
            length_octets = (1, 2, 4)[length_type]
            if cursor + length_octets > len(raw):
                raise ProtocolReviewVerificationError("truncated old-format OpenPGP length")
            length = int.from_bytes(raw[cursor : cursor + length_octets], "big")
            cursor += length_octets
        if length <= 0 or cursor + length > len(raw):
            raise ProtocolReviewVerificationError("truncated/empty OpenPGP packet")
        packets.append(_OpenPGPPacket(tag=tag, body=raw[cursor : cursor + length]))
        cursor += length
    if not packets:
        raise ProtocolReviewVerificationError("OpenPGP packet stream is empty")
    return tuple(packets)


def _read_openpgp_mpi(raw: bytes, cursor: int) -> tuple[bytes, int]:
    if cursor + 2 > len(raw):
        raise ProtocolReviewVerificationError("truncated OpenPGP MPI bit length")
    bit_length = int.from_bytes(raw[cursor : cursor + 2], "big")
    cursor += 2
    byte_length = (bit_length + 7) // 8
    if bit_length == 0 or cursor + byte_length > len(raw):
        raise ProtocolReviewVerificationError("truncated/zero OpenPGP MPI")
    encoded = raw[cursor : cursor + byte_length]
    if encoded[0] == 0 or int.from_bytes(encoded, "big").bit_length() != bit_length:
        raise ProtocolReviewVerificationError("OpenPGP MPI is not canonically encoded")
    return encoded, cursor + byte_length


def _parse_openpgp_key_material(body: bytes) -> _OpenPGPKeyMaterial:
    if len(body) < 16 or body[0] != 4 or body[5] != 22:
        raise ProtocolReviewVerificationError("OpenPGP signing key must be v4 Ed25519Legacy")
    created_at = int.from_bytes(body[1:5], "big")
    oid_length = body[6]
    oid_end = 7 + oid_length
    if oid_length != len(_OPENPGP_ED25519_LEGACY_OID) or body[7:oid_end] != (
        _OPENPGP_ED25519_LEGACY_OID
    ):
        raise ProtocolReviewVerificationError("OpenPGP signing key curve OID mismatch")
    point, cursor = _read_openpgp_mpi(body, oid_end)
    if cursor != len(body) or len(point) != 33 or point[0] != 0x40:
        raise ProtocolReviewVerificationError(
            "OpenPGP Ed25519 key requires one 0x40-prefixed 32-byte point"
        )
    if len(body) > 65_535:
        raise ProtocolReviewVerificationError("OpenPGP v4 key body is too long")
    fingerprint = hashlib.sha1(b"\x99" + len(body).to_bytes(2, "big") + body).hexdigest().upper()
    return _OpenPGPKeyMaterial(
        body=body,
        public_key=point[1:],
        fingerprint=fingerprint,
        created_at=created_at,
    )


def _openpgp_transferable_key_fingerprint(
    key_bytes: bytes,
) -> str:
    packets = _parse_openpgp_packets(key_bytes)
    if len(packets) < 3 or tuple(item.tag for item in packets[:3]) != (6, 13, 2):
        raise ProtocolReviewVerificationError(
            "OpenPGP key requires primary/User-ID/positive-certification packet order"
        )
    if (len(packets) - 3) % 2 or any(
        (packets[index].tag, packets[index + 1].tag) != (14, 2)
        for index in range(3, len(packets), 2)
    ):
        raise ProtocolReviewVerificationError(
            "OpenPGP key permits only ordered subkey/binding-signature pairs"
        )
    primary = _parse_openpgp_key_material(packets[0].body)
    certification = _parse_openpgp_signature(
        packets[2].body,
        expected_type=0x13,
        label="positive-certification 0x13",
        require_key_flags=True,
    )
    if (
        certification.issuer_fingerprint != primary.fingerprint
        or certification.key_flags is None
        or certification.key_flags & 0x03 != 0x03
    ):
        raise ProtocolReviewVerificationError("OpenPGP primary self-certification profile mismatch")
    key_bodies = {packets[0].body}
    key_fingerprints = {primary.fingerprint}
    key_public_material = {primary.public_key}
    subkey_fingerprints: list[str] = []
    for index in range(3, len(packets), 2):
        subkey = _parse_openpgp_key_material(packets[index].body)
        if (
            packets[index].body in key_bodies
            or subkey.fingerprint in key_fingerprints
            or subkey.public_key in key_public_material
        ):
            raise ProtocolReviewVerificationError(
                "OpenPGP primary/subkey key material must be globally unique"
            )
        key_bodies.add(packets[index].body)
        key_fingerprints.add(subkey.fingerprint)
        key_public_material.add(subkey.public_key)
        subkey_fingerprints.append(subkey.fingerprint)
        binding = _parse_openpgp_signature(
            packets[index + 1].body,
            expected_type=0x18,
            label="subkey-binding 0x18",
            require_key_flags=True,
        )
        if (
            binding.issuer_fingerprint != primary.fingerprint
            or binding.key_flags is None
            or binding.key_flags & 0x02 == 0
            or len(binding.embedded_signatures) != 1
        ):
            raise ProtocolReviewVerificationError("OpenPGP signing-subkey binding profile mismatch")
        embedded = _parse_openpgp_signature(
            binding.embedded_signatures[0],
            expected_type=0x19,
            label="embedded primary-binding 0x19",
            require_key_flags=False,
        )
        if embedded.issuer_fingerprint != subkey.fingerprint:
            raise ProtocolReviewVerificationError(
                "OpenPGP embedded primary-binding issuer mismatch"
            )
    if tuple(subkey_fingerprints) != tuple(sorted(subkey_fingerprints)) or len(
        set(subkey_fingerprints)
    ) != len(subkey_fingerprints):
        raise ProtocolReviewVerificationError(
            "OpenPGP subkeys require distinct ascending primary fingerprints"
        )
    return primary.fingerprint


def _signing_key_fingerprint(
    verification_mode: Literal["ssh_sha256", "openpgp_fingerprint"],
    key_bytes: bytes,
) -> str:
    if verification_mode == "ssh_sha256":
        return _ssh_public_key_fingerprint(key_bytes)
    return _openpgp_transferable_key_fingerprint(key_bytes)


def _openpgp_key_hash_bytes(key: _OpenPGPKeyMaterial) -> bytes:
    return b"\x99" + len(key.body).to_bytes(2, "big") + key.body


def _parse_openpgp_subpackets(raw: bytes) -> tuple[tuple[int, bool, bytes], ...]:
    cursor = 0
    result: list[tuple[int, bool, bytes]] = []
    while cursor < len(raw):
        length, cursor = _read_openpgp_length(raw, cursor)
        if length <= 0 or cursor + length > len(raw):
            raise ProtocolReviewVerificationError("truncated/empty OpenPGP signature subpacket")
        type_octet = raw[cursor]
        data = raw[cursor + 1 : cursor + length]
        cursor += length
        subpacket_type = type_octet & 0x7F
        critical = bool(type_octet & 0x80)
        if critical and subpacket_type not in _OPENPGP_RECOGNIZED_SUBPACKETS:
            raise ProtocolReviewVerificationError(
                "OpenPGP signature contains an unknown critical subpacket"
            )
        result.append((subpacket_type, critical, data))
    return tuple(result)


def _one_subpacket(
    subpackets: tuple[tuple[int, bool, bytes], ...],
    subpacket_type: int,
    *,
    required: bool,
    label: str,
) -> bytes | None:
    matches = tuple(data for item_type, _, data in subpackets if item_type == subpacket_type)
    if len(matches) > 1 or (required and len(matches) != 1):
        raise ProtocolReviewVerificationError(
            f"OpenPGP signature requires an unambiguous {label} subpacket"
        )
    return matches[0] if matches else None


def _parse_openpgp_signature(
    body: bytes,
    *,
    expected_type: int,
    label: str,
    require_key_flags: bool,
) -> _OpenPGPSignature:
    if len(body) < 12 or body[0] != 4:
        raise ProtocolReviewVerificationError(f"OpenPGP {label} signature must be v4")
    if body[1] != expected_type:
        raise ProtocolReviewVerificationError(
            f"OpenPGP {label} signature requires type 0x{expected_type:02x}"
        )
    if body[2:4] != b"\x16\x08":
        raise ProtocolReviewVerificationError(f"OpenPGP {label} signature requires EdDSA/SHA-256")
    hashed_length = int.from_bytes(body[4:6], "big")
    hashed_end = 6 + hashed_length
    if hashed_end + 2 > len(body):
        raise ProtocolReviewVerificationError("truncated OpenPGP hashed subpacket area")
    signed_header = body[:hashed_end]
    hashed = _parse_openpgp_subpackets(body[6:hashed_end])
    unhashed_length = int.from_bytes(body[hashed_end : hashed_end + 2], "big")
    unhashed_start = hashed_end + 2
    unhashed_end = unhashed_start + unhashed_length
    if unhashed_end + 2 > len(body):
        raise ProtocolReviewVerificationError("truncated OpenPGP unhashed subpacket area")
    unhashed = _parse_openpgp_subpackets(body[unhashed_start:unhashed_end])
    forbidden_unhashed = {2, 3, 9, 27, 32}
    if any(item_type in forbidden_unhashed for item_type, _, _ in unhashed):
        raise ProtocolReviewVerificationError(
            "OpenPGP security subpackets must occur only in the hashed area"
        )
    creation_raw = _one_subpacket(hashed, 2, required=True, label="hashed signature-creation-time")
    assert creation_raw is not None
    if len(creation_raw) != 4:
        raise ProtocolReviewVerificationError("OpenPGP signature creation time length mismatch")
    fingerprint_raw = _one_subpacket(hashed, 33, required=True, label="hashed issuer-fingerprint")
    assert fingerprint_raw is not None
    if len(fingerprint_raw) != 21 or fingerprint_raw[0] != 4:
        raise ProtocolReviewVerificationError("OpenPGP issuer fingerprint must be one v4 SHA-1 ID")
    issuer_fingerprint = fingerprint_raw[1:].hex().upper()
    unhashed_fingerprint = _one_subpacket(
        unhashed, 33, required=False, label="unhashed issuer-fingerprint"
    )
    if unhashed_fingerprint is not None and unhashed_fingerprint != fingerprint_raw:
        raise ProtocolReviewVerificationError(
            "OpenPGP hashed/unhashed issuer fingerprints are inconsistent"
        )
    issuer_ids = tuple(data for item_type, _, data in (*hashed, *unhashed) if item_type == 16)
    if len(issuer_ids) > 1 or any(
        len(item) != 8 or item != bytes.fromhex(issuer_fingerprint)[-8:] for item in issuer_ids
    ):
        raise ProtocolReviewVerificationError("OpenPGP issuer key IDs are ambiguous/inconsistent")
    signature_expiration_raw = _one_subpacket(
        hashed, 3, required=False, label="signature-expiration"
    )
    key_expiration_raw = _one_subpacket(hashed, 9, required=False, label="key-expiration")
    key_flags_raw = _one_subpacket(hashed, 27, required=require_key_flags, label="key-flags")
    if expected_type in {0x19, 0x00} and key_flags_raw is not None:
        raise ProtocolReviewVerificationError(
            "OpenPGP key-flags subpacket is forbidden for this signature role"
        )
    if expected_type not in {0x13, 0x18} and key_expiration_raw is not None:
        raise ProtocolReviewVerificationError(
            "OpenPGP key-expiration subpacket is forbidden for this signature role"
        )
    for name, value in (
        ("signature expiration", signature_expiration_raw),
        ("key expiration", key_expiration_raw),
    ):
        if value is not None and len(value) != 4:
            raise ProtocolReviewVerificationError(f"OpenPGP {name} length mismatch")
    if key_flags_raw is not None and len(key_flags_raw) != 1:
        raise ProtocolReviewVerificationError(
            "OpenPGP key-flags subpacket must contain exactly one octet"
        )
    embedded = tuple(data for item_type, _, data in hashed if item_type == 32)
    if any(item_type == 32 for item_type, _, _ in unhashed):
        raise ProtocolReviewVerificationError(
            "OpenPGP embedded signatures must occur only in the hashed area"
        )
    if (expected_type == 0x18 and len(embedded) != 1) or (
        expected_type != 0x18 and embedded
    ):
        raise ProtocolReviewVerificationError(
            "OpenPGP embedded primary-binding 0x19 signature cardinality/role mismatch"
        )
    hash_prefix = body[unhashed_end : unhashed_end + 2]
    cursor = unhashed_end + 2
    r_value, cursor = _read_openpgp_mpi(body, cursor)
    s_value, cursor = _read_openpgp_mpi(body, cursor)
    if cursor != len(body) or len(r_value) > 32 or len(s_value) > 32:
        raise ProtocolReviewVerificationError(
            "OpenPGP EdDSA signature requires exactly two <=32-byte MPIs"
        )
    return _OpenPGPSignature(
        signature_type=expected_type,
        issuer_fingerprint=issuer_fingerprint,
        created_at=int.from_bytes(creation_raw, "big"),
        signature_expiration=(
            None
            if signature_expiration_raw is None
            else int.from_bytes(signature_expiration_raw, "big")
        ),
        key_expiration=(
            None if key_expiration_raw is None else int.from_bytes(key_expiration_raw, "big")
        ),
        key_flags=(None if key_flags_raw is None else int.from_bytes(key_flags_raw, "big")),
        embedded_signatures=embedded,
        signed_header=signed_header,
        hash_prefix=hash_prefix,
        raw_signature=r_value.rjust(32, b"\0") + s_value.rjust(32, b"\0"),
    )


def _verify_openpgp_signature(
    signature: _OpenPGPSignature,
    *,
    public_key: bytes,
    signed_data: bytes,
) -> None:
    trailer = b"\x04\xff" + len(signature.signed_header).to_bytes(4, "big")
    digest = hashlib.sha256(signed_data + signature.signed_header + trailer).digest()
    if digest[:2] != signature.hash_prefix:
        raise ProtocolReviewVerificationError("OpenPGP signature hash prefix mismatch")
    _verify_ed25519(public_key, signature.raw_signature, digest)


def _openpgp_signed_at_epoch(value: str) -> int:
    _whole_second_timestamp(value)
    return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())


def _validate_openpgp_signature_time(
    signature: _OpenPGPSignature,
    *,
    key_created_at: int,
    signed_at: int,
    require_exact_creation: bool,
) -> None:
    if signature.created_at < key_created_at or signature.created_at > signed_at:
        raise ProtocolReviewVerificationError("OpenPGP signature time is outside key validity")
    if require_exact_creation and signature.created_at != signed_at:
        raise ProtocolReviewVerificationError(
            "OpenPGP detached signature time must equal statement signed_at"
        )
    if signature.signature_expiration not in (None, 0) and signed_at >= signature.created_at + cast(
        int, signature.signature_expiration
    ):
        raise ProtocolReviewVerificationError("OpenPGP signature is expired at statement signed_at")


def _openpgp_key_expiry(created_at: int, seconds: int | None) -> int | None:
    if seconds in (None, 0):
        return None
    return created_at + cast(int, seconds)


def _verify_openpgp_signature_profile(
    key_bytes: bytes,
    signature_armor: bytes,
    signed_payload: bytes,
    *,
    author_name_ascii: str,
    author_email_ascii: str,
    signed_at: str,
) -> str:
    signed_at_epoch = _openpgp_signed_at_epoch(signed_at)
    packets = _parse_openpgp_packets(key_bytes)
    if len(packets) < 3 or tuple(item.tag for item in packets[:3]) != (6, 13, 2):
        raise ProtocolReviewVerificationError(
            "OpenPGP key requires primary/User-ID/positive-certification packet order"
        )
    if (len(packets) - 3) % 2 or any(
        (packets[index].tag, packets[index + 1].tag) != (14, 2)
        for index in range(3, len(packets), 2)
    ):
        raise ProtocolReviewVerificationError(
            "OpenPGP key permits only ordered subkey/binding-signature pairs"
        )
    primary = _parse_openpgp_key_material(packets[0].body)
    key_bodies = {packets[0].body}
    key_fingerprints = {primary.fingerprint}
    key_public_material = {primary.public_key}
    expected_user_id = f"{author_name_ascii} <{author_email_ascii}>".encode("ascii")
    if packets[1].body != expected_user_id:
        raise ProtocolReviewVerificationError("OpenPGP User ID differs from review author identity")
    certification = _parse_openpgp_signature(
        packets[2].body,
        expected_type=0x13,
        label="positive-certification 0x13",
        require_key_flags=True,
    )
    if certification.issuer_fingerprint != primary.fingerprint:
        raise ProtocolReviewVerificationError("OpenPGP self-certification issuer mismatch")
    if certification.key_flags is None or certification.key_flags & 0x03 != 0x03:
        raise ProtocolReviewVerificationError(
            "OpenPGP primary self-certification requires certify+sign flags"
        )
    _validate_openpgp_signature_time(
        certification,
        key_created_at=primary.created_at,
        signed_at=signed_at_epoch,
        require_exact_creation=False,
    )
    certification_data = (
        _openpgp_key_hash_bytes(primary)
        + b"\xb4"
        + len(expected_user_id).to_bytes(4, "big")
        + expected_user_id
    )
    _verify_openpgp_signature(
        certification,
        public_key=primary.public_key,
        signed_data=certification_data,
    )
    primary_expiry = _openpgp_key_expiry(primary.created_at, certification.key_expiration)
    if primary_expiry is not None and signed_at_epoch >= primary_expiry:
        raise ProtocolReviewVerificationError("OpenPGP primary key is expired")
    signing_keys: dict[str, _OpenPGPSigningKey] = {
        primary.fingerprint: _OpenPGPSigningKey(
            public_key=primary.public_key,
            fingerprint=primary.fingerprint,
            created_at=primary.created_at,
            expires_at=primary_expiry,
        )
    }
    subkey_fingerprints: list[str] = []
    for index in range(3, len(packets), 2):
        subkey = _parse_openpgp_key_material(packets[index].body)
        if (
            packets[index].body in key_bodies
            or subkey.fingerprint in key_fingerprints
            or subkey.public_key in key_public_material
        ):
            raise ProtocolReviewVerificationError(
                "OpenPGP primary/subkey key material must be globally unique"
            )
        key_bodies.add(packets[index].body)
        key_fingerprints.add(subkey.fingerprint)
        key_public_material.add(subkey.public_key)
        subkey_fingerprints.append(subkey.fingerprint)
        signed_keys = _openpgp_key_hash_bytes(primary) + _openpgp_key_hash_bytes(subkey)
        binding = _parse_openpgp_signature(
            packets[index + 1].body,
            expected_type=0x18,
            label="subkey-binding 0x18",
            require_key_flags=True,
        )
        if binding.issuer_fingerprint != primary.fingerprint:
            raise ProtocolReviewVerificationError("OpenPGP subkey binding issuer mismatch")
        _validate_openpgp_signature_time(
            binding,
            key_created_at=max(primary.created_at, subkey.created_at),
            signed_at=signed_at_epoch,
            require_exact_creation=False,
        )
        _verify_openpgp_signature(
            binding,
            public_key=primary.public_key,
            signed_data=signed_keys,
        )
        if binding.key_flags is None or binding.key_flags & 0x02 == 0:
            raise ProtocolReviewVerificationError(
                "OpenPGP transferable key permits only signing-capable subkeys"
            )
        if len(binding.embedded_signatures) != 1:
            raise ProtocolReviewVerificationError(
                "OpenPGP signing subkey requires one embedded primary-binding 0x19 signature"
            )
        embedded = _parse_openpgp_signature(
            binding.embedded_signatures[0],
            expected_type=0x19,
            label="embedded primary-binding 0x19",
            require_key_flags=False,
        )
        if embedded.issuer_fingerprint != subkey.fingerprint:
            raise ProtocolReviewVerificationError(
                "OpenPGP embedded primary-binding issuer mismatch"
            )
        _validate_openpgp_signature_time(
            embedded,
            key_created_at=subkey.created_at,
            signed_at=signed_at_epoch,
            require_exact_creation=False,
        )
        _verify_openpgp_signature(
            embedded,
            public_key=subkey.public_key,
            signed_data=signed_keys,
        )
        subkey_expiry = _openpgp_key_expiry(subkey.created_at, binding.key_expiration)
        if subkey_expiry is None or signed_at_epoch < subkey_expiry:
            signing_keys[subkey.fingerprint] = _OpenPGPSigningKey(
                public_key=subkey.public_key,
                fingerprint=subkey.fingerprint,
                created_at=subkey.created_at,
                expires_at=subkey_expiry,
            )
    if tuple(subkey_fingerprints) != tuple(sorted(subkey_fingerprints)) or len(
        set(subkey_fingerprints)
    ) != len(subkey_fingerprints):
        raise ProtocolReviewVerificationError(
            "OpenPGP subkeys require distinct ascending primary fingerprints"
        )
    decoded_signature = _decode_exact_armor(
        signature_armor,
        begin=b"-----BEGIN PGP SIGNATURE-----",
        end=b"-----END PGP SIGNATURE-----",
        wrap=64,
        blank_after_begin=True,
        require_crc24=True,
    )
    signature_packet = _one_openpgp_packet(decoded_signature, 2)
    detached = _parse_openpgp_signature(
        signature_packet,
        expected_type=0x00,
        label="detached commit 0x00",
        require_key_flags=False,
    )
    selected = signing_keys.get(detached.issuer_fingerprint)
    if selected is None:
        raise ProtocolReviewVerificationError(
            "OpenPGP detached issuer is not the primary or one valid bound signing subkey"
        )
    if selected.expires_at is not None and signed_at_epoch >= selected.expires_at:
        raise ProtocolReviewVerificationError("OpenPGP selected signing key is expired")
    _validate_openpgp_signature_time(
        detached,
        key_created_at=selected.created_at,
        signed_at=signed_at_epoch,
        require_exact_creation=True,
    )
    _verify_openpgp_signature(
        detached,
        public_key=selected.public_key,
        signed_data=signed_payload,
    )
    return primary.fingerprint


def _verify_keyed_signature_v1(
    *,
    key: ProtocolReviewSigningKeyV1 | AuditReviewerSigningKeyV1,
    signed_payload: bytes,
    signature: bytes,
    verifier_tool_sha256: str,
    author_name_ascii: str,
    author_email_ascii: str,
    signed_at: str,
) -> LocalSignatureVerificationReceiptV1:
    """Hermetically verify one keyed commit signature from only sealed C0 inputs."""

    if type(key) is ProtocolReviewSigningKeyV1:
        key = _class_bound_revalidate(key, ProtocolReviewSigningKeyV1)
    elif type(key) is AuditReviewerSigningKeyV1:
        key = _class_bound_revalidate(key, AuditReviewerSigningKeyV1)
    else:
        raise ProtocolReviewVerificationError("expected an exact protocol or audit signing key")
    if type(signed_payload) is not bytes or type(signature) is not bytes:
        raise ProtocolReviewVerificationError("keyed verifier inputs must be exact bytes")
    author_name_ascii = _strict_string(author_name_ascii)
    author_email_ascii = _strict_string(author_email_ascii)
    signed_at = _whole_second_timestamp(_strict_string(signed_at))
    key_bytes = base64.b64decode(key.public_key_base64.encode("ascii"), validate=True)
    if key.verification_mode == "ssh_sha256":
        actual_fingerprint = _verify_ssh_signature(key_bytes, signature, signed_payload)
    else:
        actual_fingerprint = _verify_openpgp_signature_profile(
            key_bytes,
            signature,
            signed_payload,
            author_name_ascii=author_name_ascii,
            author_email_ascii=author_email_ascii,
            signed_at=signed_at,
        )
    if actual_fingerprint != key.fingerprint:
        raise ProtocolReviewVerificationError("C0 signing-key fingerprint mismatch")
    payload: dict[str, object] = {
        "verified": True,
        "signed_payload_sha256": hashlib.sha256(signed_payload).hexdigest(),
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
        "verifier_tool_sha256": verifier_tool_sha256,
    }
    payload["verification_receipt_sha256"] = protocol_review_digest(
        "laconian-local-signature-verification-receipt-v1", payload
    )
    return LocalSignatureVerificationReceiptV1.model_validate(payload)


def _revalidate_signature_source(
    source: ProtocolSignatureEvidenceSourceV1,
) -> ProtocolSignatureEvidenceSourceV1:
    if type(source) is not ProtocolSignatureEvidenceSourceV1:
        raise ProtocolReviewVerificationError("expected exact signature-evidence source")
    receipt = _class_bound_revalidate(
        source.observation_receipt, GitHubSignatureObservationReceiptV1
    )
    evidence_type = type(source.signature_evidence)
    if evidence_type not in {
        GitHubVerifiedCommitEvidenceV1,
        SSHVerifiedCommitEvidenceV1,
        OpenPGPVerifiedCommitEvidenceV1,
    }:
        raise ProtocolReviewVerificationError("signature source evidence type is not closed")
    evidence = _class_bound_revalidate(source.signature_evidence, evidence_type)
    return ProtocolSignatureEvidenceSourceV1(
        observation_receipt=receipt,
        signature_evidence=evidence,
        raw_response_bytes=source.raw_response_bytes,
        canonical_response_bytes=source.canonical_response_bytes,
    )


def verify_commit_signature_evidence_source(
    *,
    source: ProtocolSignatureEvidenceSourceV1,
    commit: ParsedProtocolGitObjectV1,
    expected_parent_oid: str,
    expected_primary_path: str,
    expected_repository_id: int,
    expected_repository_owner: str,
    expected_repository_name: str,
    expected_signer_numeric_account_id: int,
    expected_signer_login: str,
    expected_verification_mode: SignatureVerificationModeV1,
    expected_signing_fingerprint: str | None,
    signing_key: ProtocolReviewSigningKeyV1 | AuditReviewerSigningKeyV1 | None,
    expected_git_identity: tuple[str, str, str, str] | None,
    identity_registry_bundle: ProtocolReviewIdentityRegistryBundleV1,
    audit_reviewer_registry: AuditReviewerRegistryV1 | None,
) -> SignatureEvidenceV1:
    """Reconstruct one commit-signature evidence record from retained source bytes."""

    source = _revalidate_signature_source(source)
    if type(commit) is not ParsedProtocolGitObjectV1:
        raise ProtocolReviewVerificationError("expected one exact parsed commit object")
    reparsed_commit = parse_protocol_git_object(
        oid=commit.oid,
        object_type=commit.object_type,
        raw_content=commit.raw_content,
    )
    if reparsed_commit != commit:
        raise ProtocolReviewVerificationError("parsed commit was mutated after verification")
    commit_view = _parse_commit_view(reparsed_commit)
    expected_parent_oid = _git_sha1(_strict_string(expected_parent_oid))
    if (
        commit_view.header_names != ("tree", "parent", "author", "committer", "gpgsig")
        or commit_view.parent_oids != (expected_parent_oid,)
        or commit_view.signature is None
    ):
        raise ProtocolReviewVerificationError(
            "signed commit requires exact headers, one parent, and one signature"
        )
    expected_primary_path = _strict_string(expected_primary_path)
    expected_repository_id = _selected_positive_int(
        expected_repository_id, "expected repository ID"
    )
    expected_repository_owner, expected_repository_name = _validated_repository_slug(
        expected_repository_owner, expected_repository_name
    )
    expected_signer_numeric_account_id = _selected_positive_int(
        expected_signer_numeric_account_id, "expected signer account ID"
    )
    expected_signer_login = _strict_string(expected_signer_login)
    if expected_verification_mode not in (
        "github_verified_commit",
        "ssh_sha256",
        "openpgp_fingerprint",
    ):
        raise ProtocolReviewVerificationError("signature verification mode is not closed")
    validate_signature_mode_fingerprint(
        expected_verification_mode, expected_signing_fingerprint
    )
    identity_registry_bundle = _class_bound_revalidate(
        identity_registry_bundle, ProtocolReviewIdentityRegistryBundleV1
    )
    author_name, author_email, author_epoch, _ = _identity_parts(commit_view.author)
    committer_name, committer_email, _, _ = _identity_parts(commit_view.committer)
    signed_at = datetime.fromtimestamp(author_epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    validated_signing_key: ProtocolReviewSigningKeyV1 | AuditReviewerSigningKeyV1 | None
    if expected_verification_mode == "github_verified_commit":
        if signing_key is not None or expected_git_identity is not None:
            raise ProtocolReviewVerificationError(
                "GitHub verification requires null key and Git identity"
            )
        validated_signing_key = None
    else:
        if type(expected_git_identity) is not tuple or len(expected_git_identity) != 4:
            raise ProtocolReviewVerificationError(
                "keyed verification requires one exact four-field Git identity"
            )
        expected_author_name = _canonical_git_ascii_name(
            _strict_string(expected_git_identity[0])
        )
        expected_author_email = _canonical_git_ascii_email(
            _strict_string(expected_git_identity[1])
        )
        expected_committer_name = _canonical_git_ascii_name(
            _strict_string(expected_git_identity[2])
        )
        expected_committer_email = _canonical_git_ascii_email(
            _strict_string(expected_git_identity[3])
        )
        if (
            author_name,
            author_email,
            committer_name,
            committer_email,
        ) != (
            expected_author_name,
            expected_author_email,
            expected_committer_name,
            expected_committer_email,
        ):
            raise ProtocolReviewVerificationError("signed commit Git identity mismatch")
        if type(signing_key) is ProtocolReviewSigningKeyV1:
            validated_signing_key = _class_bound_revalidate(
                signing_key, ProtocolReviewSigningKeyV1
            )
            if validated_signing_key not in identity_registry_bundle.keys:
                raise ProtocolReviewVerificationError(
                    "protocol signing key is not an exact identity-registry member"
                )
        elif type(signing_key) is AuditReviewerSigningKeyV1:
            validated_signing_key = _class_bound_revalidate(
                signing_key, AuditReviewerSigningKeyV1
            )
            if audit_reviewer_registry is None:
                raise ProtocolReviewVerificationError(
                    "audit signing key requires its exact reviewer registry"
                )
            validated_audit_registry = _class_bound_revalidate(
                audit_reviewer_registry, AuditReviewerRegistryV1
            )
            matching_audit_reviewers = tuple(
                reviewer
                for reviewer in validated_audit_registry.reviewers
                if reviewer.reviewer_numeric_account_id
                == expected_signer_numeric_account_id
                and reviewer.reviewer_login == expected_signer_login
                and reviewer.verification_mode == expected_verification_mode
                and reviewer.signing_fingerprint == expected_signing_fingerprint
                and reviewer.signing_key == validated_signing_key
            )
            if len(matching_audit_reviewers) != 1:
                raise ProtocolReviewVerificationError(
                    "audit signing key is not the selected reviewer's exact nested key"
                )
            if expected_git_identity != (
                validated_signing_key.author_name_ascii,
                validated_signing_key.author_email_ascii,
                validated_signing_key.committer_name_ascii,
                validated_signing_key.committer_email_ascii,
            ):
                raise ProtocolReviewVerificationError(
                    "audit signing key Git identity differs from expected authority"
                )
        else:
            raise ProtocolReviewVerificationError(
                "keyed verification requires an exact protocol or audit signing key"
            )
        if (
            validated_signing_key.verification_mode != expected_verification_mode
            or validated_signing_key.fingerprint != expected_signing_fingerprint
        ):
            raise ProtocolReviewVerificationError("signing-key mode/fingerprint mismatch")

    receipt = source.observation_receipt
    if (
        receipt.repository_id != expected_repository_id
        or receipt.commit_oid != commit.oid
        or tuple(hashlib.sha256(item).hexdigest() for item in source.raw_response_bytes)
        != receipt.raw_response_sha256s
        or tuple(hashlib.sha256(item).hexdigest() for item in source.canonical_response_bytes)
        != receipt.canonical_response_sha256s
    ):
        raise ProtocolReviewVerificationError("signature source byte/receipt identity mismatch")
    rest_raw = _parse_provider_json(source.raw_response_bytes[0])
    raw_oid = _selected_string(_required_selected(rest_raw, "sha", "REST"), "sha")
    verification = _selected_object(
        _required_selected(rest_raw, "verification", "REST"), "verification"
    )
    verified = _selected_true(
        _required_selected(verification, "verified", "verification"),
        "verification.verified",
    )
    reason = _selected_string(
        _required_selected(verification, "reason", "verification"), "verification.reason"
    )
    payload_text = _selected_string(
        _required_selected(verification, "payload", "verification"), "verification.payload"
    )
    signature_text = _selected_string(
        _required_selected(verification, "signature", "verification"),
        "verification.signature",
    )
    verified_at = _provider_verified_at(
        _required_selected(verification, "verified_at", "verification")
    )
    if raw_oid != commit.oid or reason != "valid" or verified is not True:
        raise ProtocolReviewVerificationError("REST verification selected values are not valid")
    try:
        expected_payload_text = commit_view.signed_payload.decode("utf-8", errors="strict")
        expected_signature_text = commit_view.signature.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ProtocolReviewVerificationError(
            "raw Git signature evidence is not strict UTF-8"
        ) from None
    if payload_text != expected_payload_text or signature_text != expected_signature_text:
        raise ProtocolReviewVerificationError("REST payload/signature differ from raw Git commit")
    rest_payload: dict[str, object] = {
        "schema_version": "GitHubCommitVerificationProjectionV1",
        "repository_id": expected_repository_id,
        "commit_oid": commit.oid,
        "api_version": "2022-11-28",
        "endpoint": (
            f"GET /repos/{expected_repository_owner}/{expected_repository_name}"
            f"/git/commits/{commit.oid}"
        ),
        "verified": True,
        "reason": "valid",
        "payload": payload_text,
        "signature": signature_text,
        "verified_at": verified_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    rest_payload["rest_projection_sha256"] = protocol_review_digest(
        "laconian-github-commit-verification-projection-v1", rest_payload
    )
    rest = GitHubCommitVerificationProjectionV1.model_validate(rest_payload)

    graphql_raw = _parse_provider_json(source.raw_response_bytes[1])
    if "errors" in graphql_raw:
        raise ProtocolReviewVerificationError("GraphQL signature response contains errors")
    data = _selected_object(_required_selected(graphql_raw, "data", "GraphQL"), "data")
    repository = _selected_object(_required_selected(data, "repository", "data"), "data.repository")
    graphql_repository_id = _selected_positive_int(
        _required_selected(repository, "databaseId", "data.repository"),
        "data.repository.databaseId",
    )
    graphql_object = _selected_object(
        _required_selected(repository, "object", "data.repository"),
        "data.repository.object",
    )
    graphql_oid = _selected_string(
        _required_selected(graphql_object, "oid", "data.repository.object"),
        "data.repository.object.oid",
    )
    graphql_signature = _selected_object(
        _required_selected(graphql_object, "signature", "data.repository.object"),
        "data.repository.object.signature",
    )
    is_valid = _selected_true(
        _required_selected(graphql_signature, "isValid", "data.repository.object.signature"),
        "data.repository.object.signature.isValid",
    )
    state = _selected_string(
        _required_selected(graphql_signature, "state", "data.repository.object.signature"),
        "data.repository.object.signature.state",
    )
    signer = _selected_object(
        _required_selected(graphql_signature, "signer", "data.repository.object.signature"),
        "data.repository.object.signature.signer",
    )
    signer_id = _selected_positive_int(
        _required_selected(signer, "databaseId", "data.repository.object.signature.signer"),
        "data.repository.object.signature.signer.databaseId",
    )
    signer_login = _selected_string(
        _required_selected(signer, "login", "data.repository.object.signature.signer"),
        "data.repository.object.signature.signer.login",
    )
    if (
        graphql_repository_id != expected_repository_id
        or graphql_oid != commit.oid
        or is_valid is not True
        or state != "VALID"
        or signer_id != expected_signer_numeric_account_id
        or signer_login != expected_signer_login
    ):
        raise ProtocolReviewVerificationError("GraphQL selected signature identity mismatch")
    graphql_payload: dict[str, object] = {
        "schema_version": "GitHubSignatureProjectionV1",
        "repository_id": expected_repository_id,
        "commit_oid": commit.oid,
        "query_sha256": GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
        "signer_database_id": signer_id,
        "signer_login": signer_login,
        "is_valid": True,
        "state": "VALID",
    }
    graphql_payload["graphql_projection_sha256"] = protocol_review_digest(
        "laconian-github-signature-projection-v1", graphql_payload
    )
    graphql = GitHubSignatureProjectionV1.model_validate(graphql_payload)
    if (
        canonical_json_v1(rest.model_dump(mode="json")) != source.canonical_response_bytes[0]
        or canonical_json_v1(graphql.model_dump(mode="json")) != source.canonical_response_bytes[1]
        or rest.rest_projection_sha256 != receipt.rest_projection_sha256
        or graphql.graphql_projection_sha256 != receipt.graphql_projection_sha256
    ):
        raise ProtocolReviewVerificationError(
            "signature source canonical projections do not reconstruct receipt"
        )
    common: dict[str, object] = {
        "commit_oid": commit.oid,
        "commit_object_sha256": commit.git_object_sha256,
        "parent_commit_oid": expected_parent_oid,
        "statement_path": expected_primary_path,
        "github_rest_verification": rest.model_dump(mode="json"),
        "github_graphql_signature": graphql.model_dump(mode="json"),
    }
    if expected_verification_mode == "github_verified_commit":
        _validate_github_signature_armor(commit_view.signature)
        fresh: (
            GitHubVerifiedCommitEvidenceV1
            | SSHVerifiedCommitEvidenceV1
            | OpenPGPVerifiedCommitEvidenceV1
        ) = GitHubVerifiedCommitEvidenceV1.model_validate(
            {
                "schema_version": "GitHubVerifiedCommitEvidenceV1",
                "verification_mode": "github_verified_commit",
                **common,
            }
        )
    else:
        assert validated_signing_key is not None
        _verify_active_verifier_runtime(identity_registry_bundle)
        try:
            local = _verify_keyed_signature_v1(
                key=validated_signing_key,
                signed_payload=commit_view.signed_payload,
                signature=commit_view.signature,
                verifier_tool_sha256=(
                    identity_registry_bundle.protocol_signature_verifier_tool_sha256
                ),
                author_name_ascii=author_name,
                author_email_ascii=author_email,
                signed_at=signed_at,
            )
        finally:
            _verify_active_verifier_runtime(identity_registry_bundle)
        keyed = {
            **common,
            "fingerprint": validated_signing_key.fingerprint,
            "keyring_sha256": validated_signing_key.public_key_sha256,
            "local_signature_verification": local.model_dump(mode="json"),
        }
        if expected_verification_mode == "ssh_sha256":
            fresh = SSHVerifiedCommitEvidenceV1.model_validate(
                {
                    "schema_version": "SSHVerifiedCommitEvidenceV1",
                    "verification_mode": "ssh_sha256",
                    **keyed,
                }
            )
        else:
            fresh = OpenPGPVerifiedCommitEvidenceV1.model_validate(
                {
                    "schema_version": "OpenPGPVerifiedCommitEvidenceV1",
                    "verification_mode": "openpgp_fingerprint",
                    **keyed,
                }
            )
    if canonical_json_v1(fresh.model_dump(mode="json")) != canonical_json_v1(
        source.signature_evidence.model_dump(mode="json")
    ):
        raise ProtocolReviewVerificationError(
            "supplied signature evidence differs from fresh source reconstruction"
        )
    return fresh


def _derive_source_evidence(
    *,
    source: ProtocolSignatureEvidenceSourceV1,
    commit: ParsedProtocolGitObjectV1,
    expected_parent_oid: str,
    reviewer: ProtocolReviewerBindingV1,
    statement: ProtocolReviewStatementV1,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
    identity_registry: ProtocolReviewIdentityRegistryBundleV1,
) -> SignatureEvidenceV1:
    signing_key: ProtocolReviewSigningKeyV1 | None = None
    expected_git_identity: tuple[str, str, str, str] | None = None
    if reviewer.verification_mode != "github_verified_commit":
        matching = tuple(
            key
            for key in identity_registry.keys
            if key.role == reviewer.role
            and key.reviewer_numeric_account_id == reviewer.reviewer_numeric_account_id
            and key.reviewer_login == reviewer.reviewer_login
            and key.verification_mode == reviewer.verification_mode
            and key.fingerprint == reviewer.signing_fingerprint
        )
        if len(matching) != 1:
            raise ProtocolReviewVerificationError("C0 key selection is missing or ambiguous")
        signing_key = matching[0]
        expected_git_identity = (
            reviewer.author_name_ascii,
            reviewer.author_email_ascii,
            reviewer.committer_name_ascii,
            reviewer.committer_email_ascii,
        )
    return verify_commit_signature_evidence_source(
        source=source,
        commit=commit,
        expected_parent_oid=expected_parent_oid,
        expected_primary_path=_statement_path(statement.input_tag_ref, statement.role),
        expected_repository_id=repository_id,
        expected_repository_owner=repository_owner,
        expected_repository_name=repository_name,
        expected_signer_numeric_account_id=reviewer.reviewer_numeric_account_id,
        expected_signer_login=reviewer.reviewer_login,
        expected_verification_mode=reviewer.verification_mode,
        expected_signing_fingerprint=reviewer.signing_fingerprint,
        signing_key=signing_key,
        expected_git_identity=expected_git_identity,
        identity_registry_bundle=identity_registry,
        audit_reviewer_registry=None,
    )


def _verify_protocol_review_prefix(
    *,
    input_tag_ref: str,
    objects: tuple[ParsedProtocolGitObjectV1, ...],
    protocol_reviewer_registry: ProtocolReviewerRegistryV1,
    tag_operator_registry: TagOperatorRegistryV1,
    tag_ruleset_policy: TagRulesetPolicyV1,
    signature_evidence_sources: tuple[
        ProtocolSignatureEvidenceSourceV1,
        ProtocolSignatureEvidenceSourceV1,
        ProtocolSignatureEvidenceSourceV1,
    ],
    input_tag_creation_suite: TagCreationRuleSuiteReceiptV1,
    expected_attestations: tuple[
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
    ]
    | None = None,
) -> VerifiedProtocolReviewPrefixV1:
    _input_tag_ref(input_tag_ref)
    object_by_oid = _object_map(objects)
    if (
        protocol_reviewer_registry.protocol_reviewer_registry_sha256
        != compute_protocol_reviewer_registry_sha256(protocol_reviewer_registry.reviewers)
    ):
        raise ProtocolReviewVerificationError("protocol reviewer registry failed revalidation")
    if tag_operator_registry.repository_id != tag_ruleset_policy.repository_id:
        raise ProtocolReviewVerificationError("operator/ruleset repository mismatch")
    if (
        tag_ruleset_policy.rulesets[0].bypass_actors[0].actor_id
        != tag_operator_registry.operators[0].operator_account_id
    ):
        raise ProtocolReviewVerificationError(
            "creation bypass actor is not the registered operator"
        )
    input_tag, tag_view = _tag_object_for_ref(input_tag_ref, object_by_oid)
    _validate_tagger(tag_view.tagger, tag_operator_registry.operators[0])
    if not tag_view.message.endswith(b"\n") or tag_view.message.endswith(b"\n\n"):
        raise ProtocolReviewVerificationError("input tag message requires exactly one terminal LF")
    input_message = InputTagMessageV1.model_validate(parse_canonical_json_v1(tag_view.message[:-1]))
    if canonical_json_v1(input_message.model_dump(mode="json")) + b"\n" != tag_view.message:
        raise ProtocolReviewVerificationError(
            "input tag message bytes are not exact canonical JSON + LF"
        )
    if input_message.input_tag_ref != input_tag_ref:
        raise ProtocolReviewVerificationError("input tag message/ref mismatch")
    c0 = object_by_oid.get(tag_view.target_oid)
    if c0 is None or c0.object_type != "commit":
        raise ProtocolReviewVerificationError("input tag does not peel directly to C0")
    if input_message.peeled_c0_oid != c0.oid:
        raise ProtocolReviewVerificationError("input tag message C0 identity mismatch")
    flattened_c0 = _flatten_tree(_parse_commit_view(c0).tree_oid, object_by_oid)
    if any(
        path.startswith(f"benchmarks/protocol-reviews/{tag_view.tag_name}/")
        for path in flattened_c0
    ):
        raise ProtocolReviewVerificationError("C0 contains the forbidden future review subtree")
    _validate_c0_registry_members(
        flattened=flattened_c0,
        objects=object_by_oid,
        protocol_reviewer_registry=protocol_reviewer_registry,
        tag_operator_registry=tag_operator_registry,
        tag_ruleset_policy=tag_ruleset_policy,
    )
    identity_registry = _load_identity_registry_bundle(
        flattened=flattened_c0,
        objects=object_by_oid,
        protocol_reviewer_registry=protocol_reviewer_registry,
    )
    workflow_root = _workflow_root_from_c0(c0, object_by_oid)
    if (
        input_message.protocol_reviewer_registry_sha256
        != protocol_reviewer_registry.protocol_reviewer_registry_sha256
        or input_message.tag_operator_registry_sha256
        != tag_operator_registry.tag_operator_registry_sha256
        or input_message.tag_ruleset_policy_root != tag_ruleset_policy.tag_ruleset_policy_root
        or input_message.workflow_root != workflow_root
    ):
        raise ProtocolReviewVerificationError("input tag authority roots mismatch")
    _validate_creation_suite(
        input_tag_creation_suite,
        expected_ref=input_tag_ref,
        expected_after_oid=input_tag.oid,
        tag_operator_registry=tag_operator_registry,
        tag_ruleset_policy=tag_ruleset_policy,
    )
    chain = _commit_chain(c0.oid, object_by_oid, length=3)
    roles: tuple[ProtocolReviewRoleV1, ...] = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    statements: list[ProtocolReviewStatementV1] = []
    attestations: list[VerifiedProtocolAttestationV1] = []
    parent = c0
    repository_owner, repository_name = _repository_slug_from_c0(
        c0, object_by_oid, tag_ruleset_policy.repository_id
    )
    for role, commit, reviewer, source in zip(
        roles,
        chain,
        protocol_reviewer_registry.reviewers,
        signature_evidence_sources,
        strict=True,
    ):
        path = _statement_path(input_tag_ref, role)
        child_tree = _validate_only_tree_delta(parent, commit, object_by_oid, (path,))
        blob = object_by_oid[child_tree[path][1]]
        statement = ProtocolReviewStatementV1.model_validate(
            parse_canonical_json_v1(blob.raw_content)
        )
        if canonical_json_v1(statement.model_dump(mode="json")) != blob.raw_content:
            raise ProtocolReviewVerificationError(
                "statement blob is not byte-identical canonical JSON"
            )
        if (
            statement.role != role
            or statement.protocol_registry_sha256
            != protocol_reviewer_registry.protocol_reviewer_registry_sha256
            or statement.reviewer_numeric_account_id != reviewer.reviewer_numeric_account_id
            or statement.reviewer_login != reviewer.reviewer_login
            or statement.verification_mode != reviewer.verification_mode
            or statement.signing_fingerprint != reviewer.signing_fingerprint
            or statement.input_tag_ref != input_tag_ref
            or statement.input_tag_oid != input_tag.oid
            or statement.input_tag_object_sha256 != input_tag.git_object_sha256
            or statement.peeled_c0_oid != c0.oid
            or statement.peeled_c0_sha256 != c0.git_object_sha256
            or statement.workflow_root != workflow_root
        ):
            raise ProtocolReviewVerificationError("protocol statement authority/identity mismatch")
        if role == "security_evidence":
            security_subjects = {item.kind: item.sha256 for item in statement.subjects}
            if (
                security_subjects["tag_operator_registry_sha256"]
                != tag_operator_registry.tag_operator_registry_sha256
                or security_subjects["tag_ruleset_policy_root"]
                != tag_ruleset_policy.tag_ruleset_policy_root
                or security_subjects["identity_registry_bundle_sha256"]
                != identity_registry.identity_registry_bundle_sha256
            ):
                raise ProtocolReviewVerificationError(
                    "security statement operator/ruleset/identity subjects mismatch"
                )
        _validate_review_commit(
            commit,
            parent_oid=parent.oid,
            reviewer=reviewer,
            statement=statement,
            input_tag_ref=input_tag_ref,
        )
        evidence = _derive_source_evidence(
            source=source,
            commit=commit,
            expected_parent_oid=parent.oid,
            reviewer=reviewer,
            statement=statement,
            repository_id=tag_ruleset_policy.repository_id,
            repository_owner=repository_owner,
            repository_name=repository_name,
            identity_registry=identity_registry,
        )
        attestation_payload: dict[str, object] = {
            "schema_version": "VerifiedProtocolAttestationV1",
            "statement": statement.model_dump(mode="json"),
            "signature_evidence": evidence.model_dump(mode="json"),
        }
        attestation_payload["attestation_sha256"] = protocol_review_digest(
            "laconian-verified-protocol-attestation-v1", attestation_payload
        )
        attestation = VerifiedProtocolAttestationV1.model_validate(attestation_payload)
        statements.append(statement)
        attestations.append(attestation)
        parent = commit
    allowed = {input_tag.oid, c0.oid, *(item.oid for item in chain)}
    for commit in (c0, *chain):
        allowed.update(_reachable_tree_objects(_parse_commit_view(commit).tree_oid, object_by_oid))
    if set(object_by_oid) != allowed:
        raise ProtocolReviewVerificationError(
            "prefix contains a missing, extra, or future Git object"
        )
    exact_statements = cast(
        tuple[
            ProtocolReviewStatementV1,
            ProtocolReviewStatementV1,
            ProtocolReviewStatementV1,
        ],
        tuple(statements),
    )
    exact_attestations = cast(
        tuple[
            VerifiedProtocolAttestationV1,
            VerifiedProtocolAttestationV1,
            VerifiedProtocolAttestationV1,
        ],
        tuple(attestations),
    )
    if expected_attestations is not None and any(
        canonical_json_v1(actual.model_dump(mode="json"))
        != canonical_json_v1(expected.model_dump(mode="json"))
        for actual, expected in zip(exact_attestations, expected_attestations, strict=True)
    ):
        raise ProtocolReviewVerificationError(
            "B0 attestations differ from fresh source reconstruction"
        )
    return VerifiedProtocolReviewPrefixV1(
        input_tag_ref=input_tag_ref,
        objects=objects,
        input_tag=input_tag,
        peeled_c0=c0,
        reviewer_commits=cast(
            tuple[
                ParsedProtocolGitObjectV1,
                ParsedProtocolGitObjectV1,
                ParsedProtocolGitObjectV1,
            ],
            chain,
        ),
        statements=exact_statements,
        attestations=exact_attestations,
        protocol_reviewer_registry=protocol_reviewer_registry,
        tag_operator_registry=tag_operator_registry,
        tag_ruleset_policy=tag_ruleset_policy,
        signature_evidence_sources=signature_evidence_sources,
        input_tag_creation_suite=input_tag_creation_suite,
    )


def _attestation_path(input_tag_ref: str, role: ProtocolReviewRoleV1) -> str:
    basename = input_tag_ref.removeprefix("refs/tags/")
    filename = {
        "statistical_method": "01-statistical-method.json",
        "blind_judge_audit_protocol": "02-blind-judge-audit-protocol.json",
        "security_evidence": "03-security-evidence.json",
    }[role]
    return f"benchmarks/protocol-reviews/{basename}/attestations/{filename}"


def _parse_b0_payloads(
    rsecurity: ParsedProtocolGitObjectV1,
    b0: ParsedProtocolGitObjectV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    input_tag_ref: str,
) -> tuple[
    tuple[
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
    ],
    ProtocolAttestationBundleV1,
]:
    roles: tuple[ProtocolReviewRoleV1, ...] = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    paths = tuple(_attestation_path(input_tag_ref, role) for role in roles)
    bundle_path = (
        f"benchmarks/protocol-reviews/{input_tag_ref.removeprefix('refs/tags/')}/bundle.json"
    )
    tree = _validate_only_tree_delta(rsecurity, b0, objects, (*paths, bundle_path))
    attestations = tuple(
        VerifiedProtocolAttestationV1.model_validate(
            parse_canonical_json_v1(objects[tree[path][1]].raw_content)
        )
        for path in paths
    )
    bundle_blob = objects[tree[bundle_path][1]]
    bundle = ProtocolAttestationBundleV1.model_validate(
        parse_canonical_json_v1(bundle_blob.raw_content)
    )
    for path, envelope in zip(paths, attestations, strict=True):
        if objects[tree[path][1]].raw_content != canonical_json_v1(
            envelope.model_dump(mode="json")
        ):
            raise ProtocolReviewVerificationError("B0 envelope blob is not exact canonical JSON")
    if bundle_blob.raw_content != canonical_json_v1(bundle.model_dump(mode="json")):
        raise ProtocolReviewVerificationError("B0 bundle blob is not exact canonical JSON")
    if any(
        canonical_json_v1(left.model_dump(mode="json"))
        != canonical_json_v1(right.model_dump(mode="json"))
        for left, right in zip(bundle.attestations, attestations, strict=True)
    ):
        raise ProtocolReviewVerificationError(
            "B0 envelope blobs differ from embedded bundle values"
        )
    return cast(
        tuple[
            VerifiedProtocolAttestationV1,
            VerifiedProtocolAttestationV1,
            VerifiedProtocolAttestationV1,
        ],
        attestations,
    ), bundle


def _bundle_builder_identity(
    c0: ParsedProtocolGitObjectV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> ProtocolBundleBuilderGitIdentityV1:
    path = "benchmark/security/protocol-bundle-builder-git-identity.json"
    flattened = _flatten_tree(_parse_commit_view(c0).tree_oid, objects)
    entry = flattened.get(path)
    if entry is None or entry[0] != "100644":
        raise ProtocolReviewVerificationError(
            "C0 lacks the frozen protocol bundle-builder identity"
        )
    return ProtocolBundleBuilderGitIdentityV1.model_validate(
        parse_canonical_json_v1(objects[entry[1]].raw_content)
    )


def _validate_b0_commit(
    b0: ParsedProtocolGitObjectV1,
    *,
    parent_oid: str,
    identity: ProtocolBundleBuilderGitIdentityV1,
    input_tag_ref: str,
    bundle_sha256: str,
) -> None:
    view = _parse_commit_view(b0)
    if view.header_names != ("tree", "parent", "author", "committer"):
        raise ProtocolReviewVerificationError("B0 header inventory/order mismatch")
    if view.parent_oids != (parent_oid,) or view.signature is not None:
        raise ProtocolReviewVerificationError("B0 must be unsigned with one parent")
    author_name, author_email, author_epoch, _ = _identity_parts(view.author)
    committer_name, committer_email, committer_epoch, _ = _identity_parts(view.committer)
    if (
        author_name != identity.name_ascii
        or author_email != identity.email_ascii
        or committer_name != identity.name_ascii
        or committer_email != identity.email_ascii
        or author_epoch != committer_epoch
    ):
        raise ProtocolReviewVerificationError("B0 builder identity/timestamp mismatch")
    expected = (
        f"laconian protocol attestation bundle "
        f"{input_tag_ref.removeprefix('refs/tags/')}: {bundle_sha256}\n"
    ).encode("ascii")
    if view.message != expected:
        raise ProtocolReviewVerificationError("B0 commit message mismatch")


def _verify_protocol_review_dag(
    *,
    input_tag_ref: str,
    companion_tag_ref: str,
    objects: tuple[ParsedProtocolGitObjectV1, ...],
    protocol_reviewer_registry: ProtocolReviewerRegistryV1,
    tag_operator_registry: TagOperatorRegistryV1,
    tag_ruleset_policy: TagRulesetPolicyV1,
    signature_evidence_sources: tuple[ProtocolSignatureEvidenceSourceV1, ...],
    tag_creation_suites: tuple[
        TagCreationRuleSuiteReceiptV1,
        TagCreationRuleSuiteReceiptV1,
    ],
) -> VerifiedProtocolReviewDagV1:
    if not _paired_refs(input_tag_ref, companion_tag_ref):
        raise ProtocolReviewVerificationError("protocol tag refs are not the deterministic pair")
    if len(signature_evidence_sources) != 3:
        raise ProtocolReviewVerificationError("complete DAG requires exactly three sources")
    object_by_oid = _object_map(objects)
    input_tag, input_tag_view = _tag_object_for_ref(input_tag_ref, object_by_oid)
    c0 = object_by_oid.get(input_tag_view.target_oid)
    if c0 is None or c0.object_type != "commit":
        raise ProtocolReviewVerificationError("T0 does not peel directly to C0")
    chain = _commit_chain(c0.oid, object_by_oid, length=4)
    rstat, rjudge, rsecurity, b0 = chain
    expected_attestations, supplied_bundle = _parse_b0_payloads(
        rsecurity, b0, object_by_oid, input_tag_ref
    )
    prefix_oids = {input_tag.oid, c0.oid, rstat.oid, rjudge.oid, rsecurity.oid}
    for commit in (c0, rstat, rjudge, rsecurity):
        prefix_oids.update(
            _reachable_tree_objects(_parse_commit_view(commit).tree_oid, object_by_oid)
        )
    prefix_objects = tuple(item for item in objects if item.oid in prefix_oids)
    sources = signature_evidence_sources
    prefix = _verify_protocol_review_prefix(
        input_tag_ref=input_tag_ref,
        objects=prefix_objects,
        protocol_reviewer_registry=protocol_reviewer_registry,
        tag_operator_registry=tag_operator_registry,
        tag_ruleset_policy=tag_ruleset_policy,
        signature_evidence_sources=sources,
        input_tag_creation_suite=tag_creation_suites[0],
        expected_attestations=expected_attestations,
    )
    reconstructed_bundle = build_protocol_attestation_bundle(verified_prefix=prefix)
    if canonical_json_v1(reconstructed_bundle.model_dump(mode="json")) != canonical_json_v1(
        supplied_bundle.model_dump(mode="json")
    ):
        raise ProtocolReviewVerificationError("B0 bundle differs from prefix reconstruction")
    identity = _bundle_builder_identity(c0, object_by_oid)
    _validate_b0_commit(
        b0,
        parent_oid=rsecurity.oid,
        identity=identity,
        input_tag_ref=input_tag_ref,
        bundle_sha256=supplied_bundle.protocol_attestation_bundle_sha256,
    )
    companion_tag, companion_view = _tag_object_for_ref(companion_tag_ref, object_by_oid)
    _validate_tagger(companion_view.tagger, tag_operator_registry.operators[0])
    if companion_view.target_oid != b0.oid:
        raise ProtocolReviewVerificationError("T1 does not peel directly to B0")
    if not companion_view.message.endswith(b"\n") or companion_view.message.endswith(b"\n\n"):
        raise ProtocolReviewVerificationError("T1 message requires exactly one terminal LF")
    companion_message = ProtocolAttestationTagMessageV1.model_validate(
        parse_canonical_json_v1(companion_view.message[:-1])
    )
    if (
        canonical_json_v1(companion_message.model_dump(mode="json")) + b"\n"
        != companion_view.message
    ):
        raise ProtocolReviewVerificationError("T1 message bytes are not exact canonical JSON + LF")
    if (
        companion_message.input_tag_ref != input_tag_ref
        or companion_message.input_tag_oid != input_tag.oid
        or companion_message.input_tag_object_sha256 != input_tag.git_object_sha256
        or companion_message.companion_tag_ref != companion_tag_ref
        or companion_message.bundle_commit_oid != b0.oid
        or companion_message.bundle_commit_object_sha256 != b0.git_object_sha256
        or companion_message.protocol_attestation_bundle_sha256
        != supplied_bundle.protocol_attestation_bundle_sha256
        or companion_message.protocol_attestations_root
        != supplied_bundle.protocol_attestations_root
        or companion_message.tag_operator_registry_sha256
        != tag_operator_registry.tag_operator_registry_sha256
        or companion_message.tag_ruleset_policy_root != tag_ruleset_policy.tag_ruleset_policy_root
    ):
        raise ProtocolReviewVerificationError("T1 message authority mismatch")
    if tag_creation_suites[0].rule_suite_id == tag_creation_suites[1].rule_suite_id:
        raise ProtocolReviewVerificationError("T0 and T1 creation suites must be unique")
    if (
        set(tag_creation_suites[0].request_ids).intersection(tag_creation_suites[1].request_ids)
        or tag_creation_suites[0].raw_response_sha256 == tag_creation_suites[1].raw_response_sha256
        or tag_creation_suites[0].canonical_response_sha256
        == tag_creation_suites[1].canonical_response_sha256
    ):
        raise ProtocolReviewVerificationError(
            "T0 and T1 creation-suite transport evidence was replayed"
        )
    _validate_creation_suite(
        tag_creation_suites[1],
        expected_ref=companion_tag_ref,
        expected_after_oid=companion_tag.oid,
        tag_operator_registry=tag_operator_registry,
        tag_ruleset_policy=tag_ruleset_policy,
    )
    allowed = {
        input_tag.oid,
        c0.oid,
        rstat.oid,
        rjudge.oid,
        rsecurity.oid,
        b0.oid,
        companion_tag.oid,
    }
    for commit in (c0, rstat, rjudge, rsecurity, b0):
        allowed.update(_reachable_tree_objects(_parse_commit_view(commit).tree_oid, object_by_oid))
    if set(object_by_oid) != allowed:
        raise ProtocolReviewVerificationError("DAG contains a missing, extra, or pre-C0 Git object")
    return VerifiedProtocolReviewDagV1(
        prefix=prefix,
        companion_tag_ref=companion_tag_ref,
        bundle=supplied_bundle,
        bundle_commit=b0,
        companion_tag=companion_tag,
        objects=objects,
        tag_creation_suites=tag_creation_suites,
    )


def build_protocol_attestation_bundle(
    *, verified_prefix: VerifiedProtocolReviewPrefixV1
) -> ProtocolAttestationBundleV1:
    verified_prefix = _reverify_prefix_capability(verified_prefix)
    statements = verified_prefix.statements
    first = statements[0]
    payload: dict[str, object] = {
        "schema_version": "ProtocolAttestationBundleV1",
        "protocol_registry_sha256": first.protocol_registry_sha256,
        "input_tag_ref": first.input_tag_ref,
        "input_tag_oid": first.input_tag_oid,
        "input_tag_object_sha256": first.input_tag_object_sha256,
        "peeled_c0_oid": first.peeled_c0_oid,
        "peeled_c0_sha256": first.peeled_c0_sha256,
        "workflow_root": first.workflow_root,
        "attestations": [item.model_dump(mode="json") for item in verified_prefix.attestations],
        "protocol_attestations_root": compute_protocol_attestations_root(
            verified_prefix.attestations
        ),
    }
    payload["protocol_attestation_bundle_sha256"] = protocol_review_digest(
        "laconian-protocol-attestation-bundle-v1", payload
    )
    return ProtocolAttestationBundleV1.model_validate(payload)


def _reverify_prefix_capability(
    prefix: VerifiedProtocolReviewPrefixV1,
) -> VerifiedProtocolReviewPrefixV1:
    if type(prefix) is not VerifiedProtocolReviewPrefixV1:
        raise ProtocolReviewVerificationError("expected exact verified protocol prefix capability")
    reviewers = _class_bound_revalidate(
        prefix.protocol_reviewer_registry, ProtocolReviewerRegistryV1
    )
    operator = _class_bound_revalidate(prefix.tag_operator_registry, TagOperatorRegistryV1)
    policy = _class_bound_revalidate(prefix.tag_ruleset_policy, TagRulesetPolicyV1)
    sources = cast(
        tuple[
            ProtocolSignatureEvidenceSourceV1,
            ProtocolSignatureEvidenceSourceV1,
            ProtocolSignatureEvidenceSourceV1,
        ],
        tuple(_revalidate_signature_source(item) for item in prefix.signature_evidence_sources),
    )
    suite = _class_bound_revalidate(prefix.input_tag_creation_suite, TagCreationRuleSuiteReceiptV1)
    rebuilt = _verify_protocol_review_prefix(
        input_tag_ref=prefix.input_tag_ref,
        objects=prefix.objects,
        protocol_reviewer_registry=reviewers,
        tag_operator_registry=operator,
        tag_ruleset_policy=policy,
        signature_evidence_sources=sources,
        input_tag_creation_suite=suite,
        expected_attestations=prefix.attestations,
    )
    if rebuilt != prefix:
        raise ProtocolReviewVerificationError("forged or stale verified protocol prefix capability")
    return rebuilt


def _reverify_dag_capability(
    dag: VerifiedProtocolReviewDagV1,
) -> VerifiedProtocolReviewDagV1:
    if type(dag) is not VerifiedProtocolReviewDagV1:
        raise ProtocolReviewVerificationError("expected exact verified protocol DAG capability")
    rebuilt = verify_protocol_review_dag(
        input_tag_ref=dag.prefix.input_tag_ref,
        companion_tag_ref=dag.companion_tag_ref,
        objects=dag.objects,
        protocol_reviewer_registry=dag.prefix.protocol_reviewer_registry,
        tag_operator_registry=dag.prefix.tag_operator_registry,
        tag_ruleset_policy=dag.prefix.tag_ruleset_policy,
        signature_evidence_sources=dag.prefix.signature_evidence_sources,
        tag_creation_suites=dag.tag_creation_suites,
    )
    if rebuilt != dag:
        raise ProtocolReviewVerificationError("forged or stale verified protocol DAG capability")
    return rebuilt


def _object_closure_root(objects: tuple[ParsedProtocolGitObjectV1, ...]) -> str:
    return protocol_review_digest(
        "laconian-protocol-review-object-closure-v1",
        [
            {
                "oid": item.oid,
                "type": item.object_type,
                "size": item.size,
                "git_object_sha256": item.git_object_sha256,
            }
            for item in objects
        ],
    )


def build_protocol_attestation_tag_binding(
    *,
    verified_dag: VerifiedProtocolReviewDagV1,
    bundle: ProtocolAttestationBundleV1,
) -> ProtocolAttestationTagBindingV1:
    verified_dag = _reverify_dag_capability(verified_dag)
    bundle = _class_bound_revalidate(bundle, ProtocolAttestationBundleV1)
    if canonical_json_v1(bundle.model_dump(mode="json")) != canonical_json_v1(
        verified_dag.bundle.model_dump(mode="json")
    ):
        raise ProtocolReviewVerificationError(
            "supplied protocol bundle does not match verified DAG"
        )
    prefix = verified_dag.prefix
    message = _parse_tag_message(verified_dag.companion_tag.raw_content)
    tag_message = ProtocolAttestationTagMessageV1.model_validate(message)
    payload: dict[str, object] = {
        "schema_version": "ProtocolAttestationTagBindingV1",
        "input_tag_ref": prefix.input_tag_ref,
        "input_tag_oid": prefix.input_tag.oid,
        "input_tag_object_sha256": prefix.input_tag.git_object_sha256,
        "peeled_c0_oid": prefix.peeled_c0.oid,
        "peeled_c0_sha256": prefix.peeled_c0.git_object_sha256,
        "reviewer_commits": [
            {
                "role": role,
                "commit_oid": commit.oid,
                "commit_object_sha256": commit.git_object_sha256,
            }
            for role, commit in zip(
                cast(
                    tuple[ProtocolReviewRoleV1, ...], tuple(item.role for item in prefix.statements)
                ),
                prefix.reviewer_commits,
                strict=True,
            )
        ],
        "bundle_commit_oid": verified_dag.bundle_commit.oid,
        "bundle_commit_object_sha256": verified_dag.bundle_commit.git_object_sha256,
        "companion_tag_ref": verified_dag.companion_tag_ref,
        "companion_tag_oid": verified_dag.companion_tag.oid,
        "companion_tag_object_sha256": verified_dag.companion_tag.git_object_sha256,
        "protocol_registry_sha256": bundle.protocol_registry_sha256,
        "workflow_root": bundle.workflow_root,
        "protocol_attestations_root": bundle.protocol_attestations_root,
        "protocol_attestation_bundle_sha256": bundle.protocol_attestation_bundle_sha256,
        "object_closure_root": _object_closure_root(verified_dag.objects),
        "tag_operator_registry_sha256": prefix.tag_operator_registry.tag_operator_registry_sha256,
        "tag_ruleset_policy_root": prefix.tag_ruleset_policy.tag_ruleset_policy_root,
    }
    if (
        tag_message.input_tag_oid != prefix.input_tag.oid
        or tag_message.bundle_commit_oid != verified_dag.bundle_commit.oid
    ):
        raise ProtocolReviewVerificationError("companion tag message identity mismatch")
    payload["protocol_attestation_tag_binding_sha256"] = protocol_review_digest(
        "laconian-protocol-attestation-tag-binding-v1", payload
    )
    return ProtocolAttestationTagBindingV1.model_validate(payload)


def _parse_tag_message(raw_content: bytes) -> object:
    try:
        _, message = raw_content.split(b"\n\n", 1)
    except ValueError:
        raise ProtocolReviewVerificationError("raw tag lacks a message separator") from None
    if not message.endswith(b"\n") or message.endswith(b"\n\n"):
        raise ProtocolReviewVerificationError("raw tag message requires exactly one terminal LF")
    return parse_canonical_json_v1(message[:-1])


def build_protocol_review_object_archive(
    *,
    verified_dag: VerifiedProtocolReviewDagV1,
    api_blobs: tuple[ArchivedApiBlobV1, ...],
    api_receipts: tuple[ArchivedApiReceiptBindingV1, ...],
) -> ProtocolReviewObjectArchiveV1:
    verified_dag = _reverify_dag_capability(verified_dag)
    if type(api_blobs) is not tuple or type(api_receipts) is not tuple:
        raise ProtocolReviewVerificationError("archive API evidence requires exact tuples")
    api_blobs = tuple(_class_bound_revalidate(item, ArchivedApiBlobV1) for item in api_blobs)
    api_receipts = tuple(
        _class_bound_revalidate(item, ArchivedApiReceiptBindingV1) for item in api_receipts
    )
    _validate_archive_source_bijection(
        verified_dag=verified_dag,
        api_blobs=api_blobs,
        api_receipts=api_receipts,
    )
    objects = tuple(
        ArchivedProtocolGitObjectV1(
            oid=item.oid,
            type=item.object_type,
            size=item.size,
            git_object_sha256=item.git_object_sha256,
            raw_content_base64=base64.b64encode(item.raw_content).decode("ascii"),
        )
        for item in verified_dag.objects
    )
    payload: dict[str, object] = {
        "schema_version": "ProtocolReviewObjectArchiveV1",
        "object_closure_root": _object_closure_root(verified_dag.objects),
        "objects": [item.model_dump(mode="json") for item in objects],
        "api_blobs": [item.model_dump(mode="json") for item in api_blobs],
        "api_receipts": [item.model_dump(mode="json") for item in api_receipts],
    }
    payload["protocol_review_object_archive_sha256"] = protocol_review_digest(
        "laconian-protocol-review-object-archive-v1", payload
    )
    archive = ProtocolReviewObjectArchiveV1.model_validate(payload)
    repository_owner, repository_name = _repository_slug_from_c0(
        verified_dag.prefix.peeled_c0,
        _object_map(verified_dag.objects),
        verified_dag.prefix.tag_ruleset_policy.repository_id,
    )
    _verify_archived_auxiliary_sources(
        archive=archive,
        tag_ruleset_policy=verified_dag.prefix.tag_ruleset_policy,
        t0_suite=verified_dag.tag_creation_suites[0],
        t1_suite=verified_dag.tag_creation_suites[1],
        repository_owner=repository_owner,
        repository_name=repository_name,
    )
    return archive


def _validate_safe_raw_body(raw: bytes) -> None:
    parsed = _parse_provider_json_value(raw)
    forbidden = {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "access_token",
        "refresh_token",
        "client_secret",
        "headers",
        "request_headers",
        "query",
        "query_string",
    }

    def visit(value: object) -> None:
        if type(value) is dict:
            mapping = cast(dict[str, object], value)
            for key, item in mapping.items():
                if key.casefold() in forbidden:
                    raise ProtocolReviewVerificationError(
                        "archived raw API body contains forbidden secret-bearing metadata"
                    )
                visit(item)
        elif type(value) is list:
            for item in cast(list[object], value):
                visit(item)

    visit(parsed)


def _validate_archive_source_bijection(
    *,
    verified_dag: VerifiedProtocolReviewDagV1,
    api_blobs: tuple[ArchivedApiBlobV1, ...],
    api_receipts: tuple[ArchivedApiReceiptBindingV1, ...],
) -> None:
    blobs = {item.path: item for item in api_blobs}
    for blob in api_blobs:
        if blob.kind == "safe_raw_response":
            _validate_safe_raw_body(_decode_canonical_base64(blob.raw_bytes_base64))
    github_bindings = tuple(
        item for item in api_receipts if item.receipt_kind == "github_signature"
    )
    by_commit = {
        item.receipt.commit_oid: item
        for item in github_bindings
        if type(item.receipt) is GitHubSignatureObservationReceiptV1
    }
    sources = verified_dag.prefix.signature_evidence_sources
    if set(by_commit) != {item.observation_receipt.commit_oid for item in sources}:
        raise ProtocolReviewVerificationError(
            "archive GitHub receipt wrappers do not biject verified sources"
        )
    for source in sources:
        binding = by_commit[source.observation_receipt.commit_oid]
        if canonical_json_v1(binding.receipt.model_dump(mode="json")) != canonical_json_v1(
            source.observation_receipt.model_dump(mode="json")
        ):
            raise ProtocolReviewVerificationError(
                "archive GitHub receipt differs from verified source"
            )
        archived_raw = tuple(
            _decode_canonical_base64(blobs[path].raw_bytes_base64)
            for path in binding.raw_blob_paths
        )
        archived_canonical = tuple(
            _decode_canonical_base64(blobs[path].raw_bytes_base64)
            for path in binding.canonical_blob_paths
        )
        if archived_raw != source.raw_response_bytes or archived_canonical != (
            source.canonical_response_bytes
        ):
            raise ProtocolReviewVerificationError(
                "archive GitHub blobs differ from verified source bytes"
            )


def load_verified_protocol_review_object_archive(
    archive: ProtocolReviewObjectArchiveV1,
) -> VerifiedProtocolReviewDagV1:
    """Reparse an archive and repeat the complete DAG verifier without network access."""

    validated = _class_bound_revalidate(archive, ProtocolReviewObjectArchiveV1)
    for blob in validated.api_blobs:
        if blob.kind == "safe_raw_response":
            _validate_safe_raw_body(_decode_canonical_base64(blob.raw_bytes_base64))
    objects = tuple(
        parse_protocol_git_object(
            oid=item.oid,
            object_type=item.type,
            raw_content=_decode_canonical_base64(item.raw_content_base64),
        )
        for item in validated.objects
    )
    return _load_verified_protocol_review_object_archive(validated, objects)


def _load_verified_protocol_review_object_archive(
    archive: ProtocolReviewObjectArchiveV1,
    objects: tuple[ParsedProtocolGitObjectV1, ...],
) -> VerifiedProtocolReviewDagV1:
    object_by_oid = _object_map(objects)
    tag_names = sorted(
        _parse_tag_view(item).tag_name for item in objects if item.object_type == "tag"
    )
    input_names = [name for name in tag_names if name.startswith("benchmark-input-")]
    companion_names = [name for name in tag_names if name.startswith("benchmark-attestations-")]
    if len(input_names) != 1 or len(companion_names) != 1:
        raise ProtocolReviewVerificationError("archive requires exactly one T0/T1 tag pair")
    input_tag_ref = "refs/tags/" + input_names[0]
    companion_tag_ref = "refs/tags/" + companion_names[0]
    if not _paired_refs(input_tag_ref, companion_tag_ref):
        raise ProtocolReviewVerificationError("archived tag refs are not deterministically paired")
    _, input_view = _tag_object_for_ref(input_tag_ref, object_by_oid)
    c0 = object_by_oid.get(input_view.target_oid)
    if c0 is None or c0.object_type != "commit":
        raise ProtocolReviewVerificationError("archived T0 does not peel directly to C0")
    flattened_c0 = _flatten_tree(_parse_commit_view(c0).tree_oid, object_by_oid)
    operator_registry = _load_c0_protocol_model(
        flattened_c0,
        object_by_oid,
        "benchmark/security/tag-operator-registry.json",
        TagOperatorRegistryV1,
    )
    ruleset_policy = _load_c0_protocol_model(
        flattened_c0,
        object_by_oid,
        "benchmark/security/tag-ruleset-policy.json",
        TagRulesetPolicyV1,
    )
    assert isinstance(operator_registry, TagOperatorRegistryV1)
    assert isinstance(ruleset_policy, TagRulesetPolicyV1)
    reviewer_registry = _reconstruct_reviewer_registry(
        input_tag_ref=input_tag_ref,
        c0=c0,
        objects=object_by_oid,
    )
    chain = _commit_chain(c0.oid, object_by_oid, length=4)
    expected_attestations, _ = _parse_b0_payloads(chain[2], chain[3], object_by_oid, input_tag_ref)
    github_bindings = tuple(
        binding for binding in archive.api_receipts if binding.receipt_kind == "github_signature"
    )
    by_commit = {
        binding.receipt.commit_oid: binding
        for binding in github_bindings
        if type(binding.receipt) is GitHubSignatureObservationReceiptV1
    }
    if set(by_commit) != {item.oid for item in chain[:3]} or len(by_commit) != 3:
        raise ProtocolReviewVerificationError(
            "archive signature receipts do not biject reviewer commits"
        )
    blob_by_path = {item.path: item for item in archive.api_blobs}
    evidence_by_commit = {
        item.signature_evidence.commit_oid: item.signature_evidence
        for item in expected_attestations
    }
    sources = cast(
        tuple[
            ProtocolSignatureEvidenceSourceV1,
            ProtocolSignatureEvidenceSourceV1,
            ProtocolSignatureEvidenceSourceV1,
        ],
        tuple(
            _signature_source_from_archive(
                binding=by_commit[item.oid],
                blobs=blob_by_path,
                evidence=evidence_by_commit[item.oid],
            )
            for item in chain[:3]
        ),
    )
    creation_bindings = {
        binding.receipt_kind: binding.receipt
        for binding in archive.api_receipts
        if binding.receipt_kind in {"t0_creation_suite", "t1_creation_suite"}
    }
    t0_suite = creation_bindings.get("t0_creation_suite")
    t1_suite = creation_bindings.get("t1_creation_suite")
    if not isinstance(t0_suite, TagCreationRuleSuiteReceiptV1) or not isinstance(
        t1_suite, TagCreationRuleSuiteReceiptV1
    ):
        raise ProtocolReviewVerificationError("archive lacks the exact T0/T1 creation suites")
    for binding in archive.api_receipts:
        if binding.receipt_kind != "tag_ruleset_observation":
            continue
        receipt = binding.receipt
        if not isinstance(receipt, TagRulesetObservationReceiptV1):
            raise ProtocolReviewVerificationError("ruleset observation wrapper/schema mismatch")
        if (
            receipt.repository_id != ruleset_policy.repository_id
            or receipt.ruleset_ids != tuple(item.ruleset_id for item in ruleset_policy.rulesets)
            or receipt.tag_ruleset_policy_root != ruleset_policy.tag_ruleset_policy_root
        ):
            raise ProtocolReviewVerificationError(
                "ruleset observation does not reconstruct sealed policy"
            )
    repository_owner, repository_name = _repository_slug_from_c0(
        c0, object_by_oid, ruleset_policy.repository_id
    )
    _verify_archived_auxiliary_sources(
        archive=archive,
        tag_ruleset_policy=ruleset_policy,
        t0_suite=t0_suite,
        t1_suite=t1_suite,
        repository_owner=repository_owner,
        repository_name=repository_name,
    )
    verified = _verify_protocol_review_dag(
        input_tag_ref=input_tag_ref,
        companion_tag_ref=companion_tag_ref,
        objects=objects,
        protocol_reviewer_registry=reviewer_registry,
        tag_operator_registry=operator_registry,
        tag_ruleset_policy=ruleset_policy,
        signature_evidence_sources=sources,
        tag_creation_suites=(t0_suite, t1_suite),
    )
    if _object_closure_root(verified.objects) != archive.object_closure_root:
        raise ProtocolReviewVerificationError("archive closure root changed during replay")
    return verified


def _load_c0_protocol_model(
    flattened: Mapping[str, tuple[str, str]],
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    path: str,
    model_type: type[TagOperatorRegistryV1] | type[TagRulesetPolicyV1],
) -> TagOperatorRegistryV1 | TagRulesetPolicyV1:
    entry = flattened.get(path)
    if entry is None or entry[0] != "100644":
        raise ProtocolReviewVerificationError(f"C0 lacks required protocol member {path}")
    blob = objects[entry[1]].raw_content
    parsed = parse_canonical_json_v1(blob)
    model = model_type.model_validate(parsed)
    if canonical_json_v1(model.model_dump(mode="json")) != blob:
        raise ProtocolReviewVerificationError(f"C0 protocol member {path} is not canonical")
    return model


def _reconstruct_reviewer_registry(
    *,
    input_tag_ref: str,
    c0: ParsedProtocolGitObjectV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> ProtocolReviewerRegistryV1:
    chain = _commit_chain(c0.oid, objects, length=3)
    roles: tuple[ProtocolReviewRoleV1, ...] = (
        "statistical_method",
        "blind_judge_audit_protocol",
        "security_evidence",
    )
    reviewers: list[dict[str, object]] = []
    statements: list[ProtocolReviewStatementV1] = []
    parent = c0
    for role, commit in zip(roles, chain, strict=True):
        path = _statement_path(input_tag_ref, role)
        tree = _validate_only_tree_delta(parent, commit, objects, (path,))
        statement = ProtocolReviewStatementV1.model_validate(
            parse_canonical_json_v1(objects[tree[path][1]].raw_content)
        )
        view = _parse_commit_view(commit)
        author_name, author_email, _, _ = _identity_parts(view.author)
        committer_name, committer_email, _, _ = _identity_parts(view.committer)
        reviewers.append(
            {
                "role": role,
                "reviewer_numeric_account_id": statement.reviewer_numeric_account_id,
                "reviewer_login": statement.reviewer_login,
                "verification_mode": statement.verification_mode,
                "signing_fingerprint": statement.signing_fingerprint,
                "author_name_ascii": author_name,
                "author_email_ascii": author_email,
                "committer_name_ascii": committer_name,
                "committer_email_ascii": committer_email,
            }
        )
        statements.append(statement)
        parent = commit
    bindings = cast(
        tuple[
            ProtocolReviewerBindingV1,
            ProtocolReviewerBindingV1,
            ProtocolReviewerBindingV1,
        ],
        tuple(ProtocolReviewerBindingV1.model_validate(item) for item in reviewers),
    )
    digest = compute_protocol_reviewer_registry_sha256(bindings)
    if any(item.protocol_registry_sha256 != digest for item in statements):
        raise ProtocolReviewVerificationError(
            "statements do not bind reconstructed reviewer registry"
        )
    return ProtocolReviewerRegistryV1(
        schema_version="benchmark-protocol-reviewer-registry-v1",
        reviewers=bindings,
        protocol_reviewer_registry_sha256=digest,
    )


def _signature_source_from_archive(
    *,
    binding: ArchivedApiReceiptBindingV1,
    blobs: Mapping[str, ArchivedApiBlobV1],
    evidence: GitHubVerifiedCommitEvidenceV1
    | SSHVerifiedCommitEvidenceV1
    | OpenPGPVerifiedCommitEvidenceV1,
) -> ProtocolSignatureEvidenceSourceV1:
    if (
        binding.receipt_kind != "github_signature"
        or type(binding.receipt) is not GitHubSignatureObservationReceiptV1
        or len(binding.raw_blob_paths) != 2
        or len(binding.canonical_blob_paths) != 2
    ):
        raise ProtocolReviewVerificationError(
            "archived signature source requires exact REST/GraphQL bindings"
        )
    raw = tuple(
        _decode_canonical_base64(blobs[path].raw_bytes_base64) for path in binding.raw_blob_paths
    )
    canonical = tuple(
        _decode_canonical_base64(blobs[path].raw_bytes_base64)
        for path in binding.canonical_blob_paths
    )
    return ProtocolSignatureEvidenceSourceV1(
        observation_receipt=binding.receipt,
        signature_evidence=evidence,
        raw_response_bytes=cast(tuple[bytes, bytes], raw),
        canonical_response_bytes=cast(tuple[bytes, bytes], canonical),
    )


_CREATION_PROJECTION_FIELDS_V1 = (
    "repository_id",
    "rule_suite_id",
    "operation",
    "ref",
    "before_sha",
    "after_sha",
    "actor_account_id",
    "actor_login",
    "pushed_at",
    "overall_result",
    "evaluation_result",
    "rule_evaluations",
    "creation_authorizer_ruleset_id",
    "creation_bypass_grant",
    "tag_ruleset_policy_root",
)


def _creation_projection_from_raw(
    raw: bytes,
    *,
    kind: Literal["t0_creation_suite", "t1_creation_suite"],
    tag_ruleset_policy: TagRulesetPolicyV1,
) -> dict[str, object]:
    response = _parse_provider_json(raw)
    path = f"raw {kind}"
    stable_only_fields = {
        "rule_suite_id",
        "operation",
        "actor_account_id",
        "actor_login",
        "overall_result",
        "creation_authorizer_ruleset_id",
        "creation_bypass_grant",
        "tag_ruleset_policy_root",
    }
    if stable_only_fields.intersection(response):
        raise ProtocolReviewVerificationError(
            f"{path} contains a stable-only canonical projection field"
        )
    repository_id = _selected_positive_int(
        _required_selected(response, "repository_id", path), f"{path}.repository_id"
    )
    rule_suite_id = _selected_positive_int(
        _required_selected(response, "id", path), f"{path}.id"
    )
    ref = _selected_string(_required_selected(response, "ref", path), f"{path}.ref")
    before_sha = _selected_string(
        _required_selected(response, "before_sha", path), f"{path}.before_sha"
    )
    after_sha = _selected_string(
        _required_selected(response, "after_sha", path), f"{path}.after_sha"
    )
    actor_id = _selected_positive_int(
        _required_selected(response, "actor_id", path), f"{path}.actor_id"
    )
    actor_name = _selected_string(
        _required_selected(response, "actor_name", path), f"{path}.actor_name"
    )
    pushed_at_raw = _selected_string(
        _required_selected(response, "pushed_at", path), f"{path}.pushed_at"
    )
    try:
        pushed_at_raw = _whole_second_timestamp(pushed_at_raw)
    except ValueError as error:
        raise ProtocolReviewVerificationError(
            f"{path}.pushed_at must be a whole-second UTC instant"
        ) from error
    overall_result = _selected_string(
        _required_selected(response, "result", path), f"{path}.result"
    )
    evaluation_result = _selected_string(
        _required_selected(response, "evaluation_result", path),
        f"{path}.evaluation_result",
    )
    raw_evaluations = _required_selected(response, "rule_evaluations", path)
    if type(raw_evaluations) is not list or len(raw_evaluations) != 1:
        raise ProtocolReviewVerificationError(
            f"{path}.rule_evaluations must contain exactly one evaluation"
        )
    raw_evaluation = _selected_object(raw_evaluations[0], f"{path}.rule_evaluations[0]")
    if {"rule_source_type", "rule_source_id"}.intersection(raw_evaluation):
        raise ProtocolReviewVerificationError(
            f"{path}.rule_evaluations[0] contains a stable-only source field"
        )
    rule_source = _selected_object(
        _required_selected(raw_evaluation, "rule_source", f"{path}.rule_evaluations[0]"),
        f"{path}.rule_evaluations[0].rule_source",
    )
    rule_source_type = _selected_string(
        _required_selected(rule_source, "type", f"{path}.rule_evaluations[0].rule_source"),
        f"{path}.rule_evaluations[0].rule_source.type",
    )
    rule_source_id = _selected_positive_int(
        _required_selected(rule_source, "id", f"{path}.rule_evaluations[0].rule_source"),
        f"{path}.rule_evaluations[0].rule_source.id",
    )
    if "name" in rule_source and type(rule_source["name"]) is not str:
        raise ProtocolReviewVerificationError(
            f"{path}.rule_evaluations[0].rule_source.name must be text when present"
        )
    enforcement = _selected_string(
        _required_selected(raw_evaluation, "enforcement", f"{path}.rule_evaluations[0]"),
        f"{path}.rule_evaluations[0].enforcement",
    )
    evaluation_rule_result = _selected_string(
        _required_selected(raw_evaluation, "result", f"{path}.rule_evaluations[0]"),
        f"{path}.rule_evaluations[0].result",
    )
    rule_type = _selected_string(
        _required_selected(raw_evaluation, "rule_type", f"{path}.rule_evaluations[0]"),
        f"{path}.rule_evaluations[0].rule_type",
    )
    creation = tag_ruleset_policy.rulesets[0]
    bypass = creation.bypass_actors[0]
    if (
        repository_id != tag_ruleset_policy.repository_id
        or before_sha != "0" * 40
        or after_sha == "0" * 40
        or not ref.startswith("refs/tags/")
        or overall_result != "bypass"
        or evaluation_result != "fail"
        or rule_source_type != "ruleset"
        or rule_source_id != creation.ruleset_id
        or enforcement != "active"
        or evaluation_rule_result != "fail"
        or rule_type != "creation"
        or actor_id != bypass.actor_id
    ):
        raise ProtocolReviewVerificationError(
            f"{path} does not prove one authorized new-tag creation"
        )
    return {
        "repository_id": repository_id,
        "rule_suite_id": rule_suite_id,
        "operation": "create",
        "ref": ref,
        "before_sha": before_sha,
        "after_sha": after_sha,
        "actor_account_id": actor_id,
        "actor_login": actor_name,
        "pushed_at": pushed_at_raw[:-1] + ".000000Z",
        "overall_result": overall_result,
        "evaluation_result": evaluation_result,
        "rule_evaluations": [
            {
                "rule_source_type": rule_source_type,
                "rule_source_id": rule_source_id,
                "enforcement": enforcement,
                "result": evaluation_rule_result,
                "rule_type": rule_type,
            }
        ],
        "creation_authorizer_ruleset_id": creation.ruleset_id,
        "creation_bypass_grant": {
            "actor_id": actor_id,
            "actor_login": actor_name,
            "source_ruleset_id": creation.ruleset_id,
            "tag_ruleset_policy_root": tag_ruleset_policy.tag_ruleset_policy_root,
        },
        "tag_ruleset_policy_root": tag_ruleset_policy.tag_ruleset_policy_root,
    }


def _selected_string_tuple(value: object, path: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise ProtocolReviewVerificationError(f"provider selected path {path} must be an array")
    return tuple(_selected_string(item, f"{path}[{ordinal}]") for ordinal, item in enumerate(value))


def _tag_ruleset_list_page_projection_from_raw(
    raw: bytes,
    *,
    repository_id: int,
    page: int,
) -> TagRulesetListPageProjectionV1:
    response = _parse_provider_json_array(raw)
    rulesets: list[dict[str, object]] = []
    for ordinal, value in enumerate(response):
        item = _selected_object(value, f"ruleset list page {page}[{ordinal}]")
        rulesets.append(
            {
                "ruleset_id": _selected_positive_int(
                    _required_selected(item, "id", f"ruleset list page {page}[{ordinal}]"),
                    f"ruleset list page {page}[{ordinal}].id",
                )
            }
        )
    payload: dict[str, object] = {
        "schema_version": "TagRulesetListPageProjectionV1",
        "repository_id": repository_id,
        "page": page,
        "rulesets": rulesets,
    }
    payload["tag_ruleset_list_page_projection_sha256"] = protocol_review_digest(
        "laconian-tag-ruleset-list-page-projection-v1", payload
    )
    return TagRulesetListPageProjectionV1.model_validate(payload)


def _tag_ruleset_detail_projection_from_raw(
    raw: bytes,
    *,
    repository_id: int,
    expected_ruleset_id: int,
) -> TagRulesetDetailProjectionV1:
    response = _parse_provider_json(raw)
    path = f"ruleset detail {expected_ruleset_id}"
    ruleset_id = _selected_positive_int(
        _required_selected(response, "id", path), f"{path}.id"
    )
    source_type = _selected_string(
        _required_selected(response, "source_type", path), f"{path}.source_type"
    )
    target = _selected_string(_required_selected(response, "target", path), f"{path}.target")
    enforcement = _selected_string(
        _required_selected(response, "enforcement", path), f"{path}.enforcement"
    )
    conditions = _selected_object(
        _required_selected(response, "conditions", path), f"{path}.conditions"
    )
    ref_name = _selected_object(
        _required_selected(conditions, "ref_name", f"{path}.conditions"),
        f"{path}.conditions.ref_name",
    )
    include_patterns = _selected_string_tuple(
        _required_selected(ref_name, "include", f"{path}.conditions.ref_name"),
        f"{path}.conditions.ref_name.include",
    )
    exclude_patterns = _selected_string_tuple(
        _required_selected(ref_name, "exclude", f"{path}.conditions.ref_name"),
        f"{path}.conditions.ref_name.exclude",
    )
    raw_rules = _required_selected(response, "rules", path)
    if type(raw_rules) is not list:
        raise ProtocolReviewVerificationError(f"{path}.rules must be an array")
    rules: list[dict[str, object]] = []
    for ordinal, raw_rule in enumerate(raw_rules):
        rule = _selected_object(raw_rule, f"{path}.rules[{ordinal}]")
        rule_type = _selected_string(
            _required_selected(rule, "type", f"{path}.rules[{ordinal}]"),
            f"{path}.rules[{ordinal}].type",
        )
        parameters = rule.get("parameters")
        rules.append({"type": rule_type, "parameters": parameters})
    raw_bypass = _required_selected(response, "bypass_actors", path)
    if type(raw_bypass) is not list:
        raise ProtocolReviewVerificationError(f"{path}.bypass_actors must be an array")
    bypass_actors: list[dict[str, object]] = []
    for ordinal, raw_actor in enumerate(raw_bypass):
        actor = _selected_object(raw_actor, f"{path}.bypass_actors[{ordinal}]")
        actor_path = f"{path}.bypass_actors[{ordinal}]"
        bypass_actors.append(
            {
                "actor_id": _selected_positive_int(
                    _required_selected(actor, "actor_id", actor_path), f"{actor_path}.actor_id"
                ),
                "actor_type": _selected_string(
                    _required_selected(actor, "actor_type", actor_path),
                    f"{actor_path}.actor_type",
                ),
                "bypass_mode": _selected_string(
                    _required_selected(actor, "bypass_mode", actor_path),
                    f"{actor_path}.bypass_mode",
                ),
            }
        )
    if ruleset_id != expected_ruleset_id:
        raise ProtocolReviewVerificationError("ruleset detail ID differs from its request target")
    payload: dict[str, object] = {
        "schema_version": "TagRulesetDetailProjectionV1",
        "repository_id": repository_id,
        "ruleset_id": ruleset_id,
        "source_type": source_type,
        "source_id": repository_id,
        "target": target,
        "enforcement": enforcement,
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
        "rules": rules,
        "bypass_actors": bypass_actors,
    }
    payload["tag_ruleset_detail_projection_sha256"] = protocol_review_digest(
        "laconian-tag-ruleset-detail-projection-v1", payload
    )
    return TagRulesetDetailProjectionV1.model_validate(payload)


def _tag_ruleset_policy_from_details(
    repository_id: int,
    details: tuple[TagRulesetDetailProjectionV1, TagRulesetDetailProjectionV1],
) -> TagRulesetPolicyV1:
    by_role: dict[str, TagRulesetDetailProjectionV1] = {}
    for detail in details:
        rule_types = tuple(item.type for item in detail.rules)
        if rule_types == ("creation",) and len(detail.bypass_actors) == 1:
            role = "creation_authorizer"
        elif rule_types == ("update", "deletion") and detail.bypass_actors == ():
            role = "immutability"
        else:
            raise ProtocolReviewVerificationError("ruleset detail has no closed semantic role")
        if role in by_role:
            raise ProtocolReviewVerificationError("ruleset detail semantic role is ambiguous")
        by_role[role] = detail
    if set(by_role) != {"creation_authorizer", "immutability"}:
        raise ProtocolReviewVerificationError("ruleset details do not cover both semantic roles")
    projections: list[dict[str, object]] = []
    for role in ("creation_authorizer", "immutability"):
        detail = by_role[role]
        projections.append(
            {
                "semantic_role": role,
                "ruleset_id": detail.ruleset_id,
                "source_type": detail.source_type,
                "source_id": detail.source_id,
                "target": detail.target,
                "enforcement": detail.enforcement,
                "include_patterns": detail.include_patterns,
                "exclude_patterns": detail.exclude_patterns,
                "rules": [item.model_dump(mode="json") for item in detail.rules],
                "bypass_actors": [
                    item.model_dump(mode="json") for item in detail.bypass_actors
                ],
            }
        )
    payload: dict[str, object] = {
        "schema_version": "TagRulesetPolicyV1",
        "repository_id": repository_id,
        "rulesets": projections,
    }
    payload["tag_ruleset_policy_root"] = protocol_review_digest(
        "laconian-tag-ruleset-policy-v2", payload
    )
    return TagRulesetPolicyV1.model_validate(payload)


def _verify_one_ruleset_observation(
    *,
    binding: ArchivedApiReceiptBindingV1,
    blobs: Mapping[str, ArchivedApiBlobV1],
    tag_ruleset_policy: TagRulesetPolicyV1,
    repository_owner: str,
    repository_name: str,
) -> None:
    receipt = binding.receipt
    if type(receipt) is not TagRulesetObservationReceiptV1:
        raise ProtocolReviewVerificationError("ruleset observation wrapper/schema mismatch")
    list_count = len(receipt.request_targets) - 2
    if not (
        len(binding.raw_blob_paths)
        == len(binding.canonical_blob_paths)
        == len(receipt.request_targets)
    ):
        raise ProtocolReviewVerificationError("ruleset archive source shape mismatch")
    expected_prefix = f"/repos/{repository_owner}/{repository_name}/rulesets"
    if any(not item.path_and_query.startswith(expected_prefix) for item in receipt.request_targets):
        raise ProtocolReviewVerificationError("ruleset request target differs from C0 repository")
    list_projections: list[TagRulesetListPageProjectionV1] = []
    for ordinal in range(list_count):
        raw = _decode_canonical_base64(blobs[binding.raw_blob_paths[ordinal]].raw_bytes_base64)
        projection = _tag_ruleset_list_page_projection_from_raw(
            raw, repository_id=receipt.repository_id, page=ordinal + 1
        )
        count = len(projection.rulesets)
        if (ordinal + 1 < list_count and count != 100) or (
            ordinal + 1 == list_count and count >= 100
        ):
            raise ProtocolReviewVerificationError("ruleset list terminal-page cardinality mismatch")
        canonical = _decode_canonical_base64(
            blobs[binding.canonical_blob_paths[ordinal]].raw_bytes_base64
        )
        if canonical != canonical_json_v1(projection.model_dump(mode="json")):
            raise ProtocolReviewVerificationError("ruleset list canonical projection mismatch")
        list_projections.append(projection)
    list_ids = tuple(
        entry.ruleset_id for projection in list_projections for entry in projection.rulesets
    )
    if len(list_ids) != 2 or len(set(list_ids)) != 2:
        raise ProtocolReviewVerificationError("ruleset list requires exactly two unique IDs")
    ascending_ids = tuple(sorted(list_ids))
    details: list[TagRulesetDetailProjectionV1] = []
    for offset, ruleset_id in enumerate(ascending_ids):
        ordinal = list_count + offset
        raw = _decode_canonical_base64(blobs[binding.raw_blob_paths[ordinal]].raw_bytes_base64)
        detail = _tag_ruleset_detail_projection_from_raw(
            raw, repository_id=receipt.repository_id, expected_ruleset_id=ruleset_id
        )
        canonical = _decode_canonical_base64(
            blobs[binding.canonical_blob_paths[ordinal]].raw_bytes_base64
        )
        if canonical != canonical_json_v1(detail.model_dump(mode="json")):
            raise ProtocolReviewVerificationError("ruleset detail canonical projection mismatch")
        details.append(detail)
    reconstructed = _tag_ruleset_policy_from_details(
        receipt.repository_id,
        cast(tuple[TagRulesetDetailProjectionV1, TagRulesetDetailProjectionV1], tuple(details)),
    )
    if (
        reconstructed != tag_ruleset_policy
        or receipt.repository_id != reconstructed.repository_id
        or receipt.ruleset_ids != tuple(item.ruleset_id for item in reconstructed.rulesets)
        or receipt.tag_ruleset_policy_root != reconstructed.tag_ruleset_policy_root
    ):
        raise ProtocolReviewVerificationError(
            "archived raw ruleset responses do not reconstruct sealed policy"
        )


def _verify_archived_auxiliary_sources(
    *,
    archive: ProtocolReviewObjectArchiveV1,
    tag_ruleset_policy: TagRulesetPolicyV1,
    t0_suite: TagCreationRuleSuiteReceiptV1,
    t1_suite: TagCreationRuleSuiteReceiptV1,
    repository_owner: str,
    repository_name: str,
) -> None:
    blobs = {item.path: item for item in archive.api_blobs}
    ruleset_bindings = tuple(
        item for item in archive.api_receipts if item.receipt_kind == "tag_ruleset_observation"
    )
    if not ruleset_bindings:
        raise ProtocolReviewVerificationError(
            "archive replay requires ruleset observation evidence"
        )
    for ruleset_binding in ruleset_bindings:
        _verify_one_ruleset_observation(
            binding=ruleset_binding,
            blobs=blobs,
            tag_ruleset_policy=tag_ruleset_policy,
            repository_owner=repository_owner,
            repository_name=repository_name,
        )
    suites: tuple[
        tuple[Literal["t0_creation_suite", "t1_creation_suite"], TagCreationRuleSuiteReceiptV1],
        tuple[Literal["t0_creation_suite", "t1_creation_suite"], TagCreationRuleSuiteReceiptV1],
    ] = (("t0_creation_suite", t0_suite), ("t1_creation_suite", t1_suite))
    for kind, expected_receipt in suites:
        matches = tuple(item for item in archive.api_receipts if item.receipt_kind == kind)
        if len(matches) != 1:
            raise ProtocolReviewVerificationError(f"archive replay requires one {kind}")
        binding = matches[0]
        if (
            type(binding.receipt) is not TagCreationRuleSuiteReceiptV1
            or binding.receipt != expected_receipt
            or len(binding.raw_blob_paths) != 1
            or len(binding.canonical_blob_paths) != 1
        ):
            raise ProtocolReviewVerificationError(f"archived {kind} receipt/source mismatch")
        selected = _creation_projection_from_raw(
            _decode_canonical_base64(blobs[binding.raw_blob_paths[0]].raw_bytes_base64),
            kind=kind,
            tag_ruleset_policy=tag_ruleset_policy,
        )
        expected_projection = expected_receipt.model_dump(
            mode="json", include=set(_CREATION_PROJECTION_FIELDS_V1)
        )
        canonical_projection = _decode_canonical_base64(
            blobs[binding.canonical_blob_paths[0]].raw_bytes_base64
        )
        if canonical_json_v1(selected) != canonical_json_v1(
            expected_projection
        ) or canonical_projection != canonical_json_v1(selected):
            raise ProtocolReviewVerificationError(
                f"archived raw {kind} response does not reconstruct its canonical projection"
            )
