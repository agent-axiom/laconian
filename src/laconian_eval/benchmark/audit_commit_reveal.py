"""Strict, source-backed two-person human-audit commit/reveal verification.

The module is intentionally offline.  Every GitHub projection is reconstructed from retained
bytes and every Git object is supplied in an exact, bounded archive; neither ambient Git state nor
caller-provided success flags participate in authority decisions.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from itertools import pairwise
from typing import Annotated, Any, Literal, Self, TypeAlias, TypeVar, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from laconian_eval.benchmark.attachments import canonical_json_v1, parse_canonical_json_v1
from laconian_eval.benchmark.audit_sampling import (
    AuditSampleManifestV1,
    BlindAuditPacketV1,
    VerifiedAuditSampleRootV1,
    verify_audit_sample,
)
from laconian_eval.benchmark.judge import (
    RubricItemJudgmentV1,
    WarningJudgmentV1,
    derive_semantic_pass,
)
from laconian_eval.benchmark.protocol_review import (
    ArchivedProtocolGitObjectV1,
    AuditReviewerRegistryV1,
    AuditReviewerSigningKeyV1,
    GitHubSignatureObservationReceiptV1,
    GitHubVerifiedCommitEvidenceV1,
    OpenPGPVerifiedCommitEvidenceV1,
    ParsedProtocolGitObjectV1,
    ProtocolReviewVerificationError,
    ProtocolSignatureEvidenceSourceV1,
    SignatureEvidenceV1,
    SignatureVerificationModeV1,
    SSHVerifiedCommitEvidenceV1,
    WholeSecondTimestamp,
    _parse_commit_view,
    _parse_provider_json,
    _parse_tree_entries,
    _preflight_exact_model_owners_v1,
    _selected_object,
    _selected_positive_int,
    _selected_string,
    parse_protocol_git_object,
    verify_commit_signature_evidence_source,
)
from laconian_eval.benchmark.provider_evidence import (
    VerifiedAuditPopulationV1,
    VerifiedBenchmarkProviderEvidenceV1,
    _revalidate_verified_provider_evidence_v1,
)
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.capsule.schema import Sha256, StrictPositiveInt

AuditPullRequestKindV1: TypeAlias = Literal["commitment", "reveal", "adjudication"]
_TreePair: TypeAlias = tuple[str | None, str | None]
_TreeEntry: TypeAlias = tuple[str, str]

_CAMPAIGN_RE = re.compile(r"^benchmark-[0-9a-f]{32}$")
_REVIEWER_COMPONENT_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9_-])?$", re.ASCII
)
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SALT_RE = re.compile(r"^[0-9a-f]{64}$")
_AUDIT_API_RAW_BYTE_LIMIT = 2_097_152
_SIGNATURE_RESPONSE_BYTE_LIMIT = 1_048_576
_AUDIT_GIT_ARCHIVE_DECODED_BYTE_LIMIT = 67_108_864
_AUDIT_PYTHON_CONTAINER_DEPTH_LIMIT = 128
_AUDIT_PYTHON_CONTAINER_COUNT_LIMIT = 16_384
_AUDIT_PYTHON_CONTAINER_ITEM_LIMIT = 4_096
_REPOSITORY_SLUG_RE = re.compile(
    r"^GET /repos/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9_-])?)/"
    r"git/commits/[0-9a-f]{40}$",
    re.ASCII,
)


def _strict_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("value must be an exact string")
    return value


def _bounded_string(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("text must already be NFC")
    if not 1 <= len(value.encode("utf-8")) <= 1_048_576 or "\0" in value or "\r" in value:
        raise ValueError("text is empty, oversized, or contains a forbidden byte")
    return value


StrictAuditString: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_bounded_string)
]


def _bounded_review_body(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("review body must already be NFC")
    if not 1 <= len(value.encode("utf-8")) <= 1_048_576 or "\r" in value:
        raise ValueError("review body is empty, oversized, or contains CR")
    return value


ReviewBodyV1: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_bounded_review_body)
]


def _campaign_id(value: str) -> str:
    if _CAMPAIGN_RE.fullmatch(value) is None:
        raise ValueError("audit campaign ID must use benchmark- plus 32 lowercase hex digits")
    return value


CampaignIdV1: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_campaign_id)
]


def _reviewer_component(value: str) -> str:
    if _REVIEWER_COMPONENT_RE.fullmatch(value) is None or value.casefold().endswith(".git"):
        raise ValueError("reviewer ID is not one safe audit path component")
    return value


ReviewerIdV1: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_reviewer_component)
]


def _canonical_base64(
    value: str, *, max_decoded_bytes: int = _AUDIT_API_RAW_BYTE_LIMIT
) -> str:
    if len(value) > 4 * ((max_decoded_bytes + 2) // 3):
        raise ValueError("encoded audit source exceeds the decoded-byte limit")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error):
        raise ValueError("value must be canonical standard base64") from None
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("value must use canonical padded standard base64")
    return value


def _preflight_encoded_byte_length(
    value: object,
    decoded_length: object,
    *,
    minimum: int,
    maximum: int,
    label: str,
) -> None:
    if (
        type(decoded_length) is not int
        or not minimum <= decoded_length <= maximum
    ):
        raise ValueError(f"{label} declared byte length is outside its closed limit")
    if type(value) is not str or len(value) % 4 != 0:
        raise ValueError(f"{label} encoded byte length differs from its declaration")
    padding = 2 if value.endswith("==") else 1 if value.endswith("=") else 0
    nominal_decoded_length = 3 * (len(value) // 4) - padding
    if nominal_decoded_length != decoded_length:
        raise ValueError(f"{label} encoded byte length differs from its declaration")


CanonicalAuditBase64: TypeAlias = Annotated[
    str, BeforeValidator(_strict_string), AfterValidator(_canonical_base64)
]
SignatureResponseLengthV1: TypeAlias = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]


def _strict_true(value: object) -> bool:
    if type(value) is not bool or value is not True:
        raise ValueError("value must be the exact JSON boolean true")
    return True


StrictTrue: TypeAlias = Annotated[Literal[True], BeforeValidator(_strict_true)]


def _model_payload(model: BaseModel, self_field: str) -> dict[str, object]:
    return cast(dict[str, object], model.model_dump(mode="json", exclude={self_field}))


def _require_exact_owner(
    value: object, owner: type[BaseModel], *, collection: bool = False
) -> object:
    values = value if collection else (value,)
    if collection and type(values) is not tuple:
        # JSON-mode lists are admitted by the field validators that pass their ValidationInfo.
        return value
    for item in cast(Sequence[object], values):
        if isinstance(item, BaseModel) and type(item) is not owner:
            raise TypeError(f"expected exact nested {owner.__name__} owner")
        if type(item) is owner:
            _preflight_exact_model_owners_v1(item, owner)
    return value


def _class_bound_revalidate_external_model(
    value: object,
    owner: type[BaseModel],
) -> object:
    if type(value) is not owner:
        return value
    try:
        payload = {
            name: object.__getattribute__(value, name) for name in owner.model_fields
        }
    except AttributeError as error:
        raise ValueError(f"incomplete exact {owner.__name__} owner") from error
    return owner.model_validate(payload)


def _exact_model_value(
    value: object,
    owner: type[BaseModel],
    *,
    json_mode: bool,
) -> object:
    if json_mode:
        # A parent validator can receive the exact child instance created by an earlier
        # JSON-mode owner reconstruction when Pydantic revalidates instances recursively.
        # Admit only that concrete owner; caller-supplied Python subclasses still take the
        # Python-mode path below and fail before Pydantic can normalize them.
        if type(value) is owner:
            return value
        if isinstance(value, BaseModel) or type(value) is not dict:
            raise TypeError(f"JSON {owner.__name__} requires one exact object payload")
        return owner.model_validate_json(canonical_json_v1(value))
    return _require_exact_owner(value, owner)


def _exact_model_tuple(
    value: object,
    owner: type[BaseModel],
    *,
    json_mode: bool,
) -> object:
    if json_mode and type(value) is list:
        if any(isinstance(item, BaseModel) for item in value):
            raise TypeError("JSON model tuples cannot contain Python model owners")
        # A before-validator replaces Pydantic's built-in JSON array-to-tuple conversion;
        # perform that exact conversion here after excluding Python model instances.
        return tuple(value)
    if type(value) is not tuple:
        raise TypeError("model tuple requires an exact tuple owner")
    return _require_exact_owner(value, owner, collection=True)


def _exact_value_tuple(value: object, *, json_mode: bool) -> object:
    if json_mode and type(value) is list:
        if any(isinstance(item, BaseModel) for item in value):
            raise TypeError("JSON value tuples cannot contain Python model owners")
        return tuple(value)
    if type(value) is not tuple:
        raise TypeError("value tuple requires an exact tuple owner")
    return value


class _AuditModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        validate_default=True,
    )

    @model_validator(mode="before")
    @classmethod
    def reject_nested_python_model_substitutes(
        cls, value: object, info: ValidationInfo
    ) -> object:
        if info.mode == "json":
            return value
        if isinstance(value, BaseModel):
            _preflight_exact_model_owners_v1(value, cls)
            return value
        if isinstance(value, Mapping) and type(value) is not dict:
            raise ValueError("audit models require one exact plain dictionary input")
        if type(value) is not dict:
            return value
        payload = cast(dict[object, object], value)
        if len(payload) > len(cls.model_fields):
            raise ValueError("audit model input exceeds its top-level field limit")

        def contains_model(candidate: object) -> bool:
            pending: list[tuple[object, int, bool]] = [(candidate, 0, False)]
            active_ids: set[int] = set()
            completed_ids: set[int] = set()
            container_count = 0
            found_model = False
            while pending:
                current, depth, exiting = pending.pop()
                if isinstance(current, BaseModel):
                    found_model = True
                    continue
                if isinstance(current, Mapping) and type(current) is not dict:
                    raise ValueError(
                        "audit models require exact plain dictionary containers"
                    )
                if isinstance(current, (list, tuple)) and type(current) not in {
                    list,
                    tuple,
                }:
                    raise ValueError("audit models require exact plain sequence containers")
                if type(current) not in {tuple, list, dict}:
                    continue

                identity = id(current)
                if exiting:
                    active_ids.remove(identity)
                    completed_ids.add(identity)
                    continue
                if identity in active_ids:
                    raise ValueError(
                        "audit model input contains a cyclic Python container"
                    )
                if depth > _AUDIT_PYTHON_CONTAINER_DEPTH_LIMIT:
                    raise ValueError(
                        "audit model input exceeds the Python-container nesting limit"
                    )
                if identity in completed_ids:
                    continue
                if len(cast(Sequence[object] | dict[object, object], current)) > (
                    _AUDIT_PYTHON_CONTAINER_ITEM_LIMIT
                ):
                    raise ValueError(
                        "audit model input exceeds the Python-container item limit"
                    )
                container_count += 1
                if container_count > _AUDIT_PYTHON_CONTAINER_COUNT_LIMIT:
                    raise ValueError(
                        "audit model input exceeds the Python-container count limit"
                    )

                active_ids.add(identity)
                pending.append((current, depth, True))
                children = (
                    tuple(cast(dict[object, object], current).values())
                    if type(current) is dict
                    else tuple(cast(Sequence[object], current))
                )
                pending.extend((item, depth + 1, False) for item in reversed(children))
            return found_model

        for name, candidate in payload.items():
            if type(name) is str and name in cls.model_fields and contains_model(candidate):
                _preflight_exact_model_owners_v1(
                    candidate,
                    cls.model_fields[name].annotation,
                    slot=name,
                )
        return value


class GitHubAuditApiObservationReceiptV1(_AuditModel):
    schema_version: Literal["audit-github-api-observation-receipt-v1"]
    source_kind: Literal["pull_request", "review"]
    repository_id: StrictPositiveInt
    endpoint: StrictAuditString
    api_version: Literal["2022-11-28"]
    observed_at_utc: WholeSecondTimestamp
    request_id: StrictAuditString
    etag: StrictAuditString
    raw_response_byte_length: int = Field(strict=True, ge=1, le=2_097_152)
    raw_response_sha256: Sha256
    tls_endpoint_identity: Literal["api.github.com:443"]
    github_audit_api_observation_receipt_sha256: Sha256

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        expected = stable_digest(
            "laconian-audit-github-api-observation-receipt-v1",
            _model_payload(self, "github_audit_api_observation_receipt_sha256"),
        )
        if self.github_audit_api_observation_receipt_sha256 != expected:
            raise ValueError("GitHub audit observation receipt digest mismatch")
        return self


class ExactGitHubPullRequestRecordV1(_AuditModel):
    schema_version: Literal["audit-github-pull-request-record-v1"]
    repository_id: StrictPositiveInt
    pr_number: StrictPositiveInt
    actor_account_id: StrictPositiveInt
    actor: StrictAuditString
    base_ref: Literal["main"]
    head_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    merge_commit_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    merge_actor_account_id: StrictPositiveInt
    merge_actor: StrictAuditString
    state: Literal["closed"]
    merged: StrictTrue
    merged_at_utc: WholeSecondTimestamp
    exact_api_record_sha256: Sha256

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        expected = stable_digest(
            "laconian-audit-github-pull-request-record-v1",
            _model_payload(self, "exact_api_record_sha256"),
        )
        if self.exact_api_record_sha256 != expected:
            raise ValueError("exact GitHub pull-request record digest mismatch")
        return self


class AuditPullRequestEvidenceSourceV1(_AuditModel):
    schema_version: Literal["audit-pull-request-source-v1"]
    proof_kind: AuditPullRequestKindV1
    campaign_id: CampaignIdV1
    reviewer_id: ReviewerIdV1 | None
    pull_request_record: ExactGitHubPullRequestRecordV1
    pull_request_observation_receipt: GitHubAuditApiObservationReceiptV1
    pull_request_raw_response_base64: CanonicalAuditBase64
    signature_observation_receipt: GitHubSignatureObservationReceiptV1
    signature_evidence: SignatureEvidenceV1
    signature_raw_response_byte_lengths: tuple[
        SignatureResponseLengthV1, SignatureResponseLengthV1
    ]
    signature_raw_response_bytes_base64: tuple[
        CanonicalAuditBase64, CanonicalAuditBase64
    ]
    signature_canonical_response_byte_lengths: tuple[
        SignatureResponseLengthV1, SignatureResponseLengthV1
    ]
    signature_canonical_response_bytes_base64: tuple[
        CanonicalAuditBase64, CanonicalAuditBase64
    ]
    pull_request_source_sha256: Sha256

    @model_validator(mode="before")
    @classmethod
    def reject_declared_size_mismatches_before_decode(cls, value: object) -> object:
        if type(value) is cls:
            source = value
            receipt_value: object = source.pull_request_observation_receipt
            raw_pr: object = source.pull_request_raw_response_base64
            raw_lengths: object = source.signature_raw_response_byte_lengths
            raw_pair: object = source.signature_raw_response_bytes_base64
            canonical_lengths: object = source.signature_canonical_response_byte_lengths
            canonical_pair: object = source.signature_canonical_response_bytes_base64
        elif type(value) is dict:
            payload = cast(dict[str, object], value)
            receipt_value = payload.get("pull_request_observation_receipt")
            raw_pr = payload.get("pull_request_raw_response_base64")
            raw_lengths = payload.get("signature_raw_response_byte_lengths")
            raw_pair = payload.get("signature_raw_response_bytes_base64")
            canonical_lengths = payload.get("signature_canonical_response_byte_lengths")
            canonical_pair = payload.get("signature_canonical_response_bytes_base64")
        else:
            return value

        if type(receipt_value) is GitHubAuditApiObservationReceiptV1:
            pr_length: object = receipt_value.raw_response_byte_length
        elif type(receipt_value) is dict:
            pr_length = cast(dict[str, object], receipt_value).get(
                "raw_response_byte_length"
            )
        else:
            raise ValueError("pull-request source requires an exact receipt before decoding")
        _preflight_encoded_byte_length(
            raw_pr,
            pr_length,
            minimum=1,
            maximum=_AUDIT_API_RAW_BYTE_LIMIT,
            label="pull-request source",
        )

        for label, lengths_value, pair_value in (
            ("raw signature source", raw_lengths, raw_pair),
            ("canonical signature source", canonical_lengths, canonical_pair),
        ):
            if type(lengths_value) not in (tuple, list) or type(pair_value) not in (
                tuple,
                list,
            ):
                raise ValueError(f"{label} requires one exact encoded byte-length pair")
            lengths = cast(Sequence[object], lengths_value)
            pair_values = cast(Sequence[object], pair_value)
            if len(lengths) != 2 or len(pair_values) != 2:
                raise ValueError(f"{label} requires one exact encoded byte-length pair")
            for encoded, decoded_length in zip(pair_values, lengths, strict=True):
                _preflight_encoded_byte_length(
                    encoded,
                    decoded_length,
                    minimum=1,
                    maximum=_SIGNATURE_RESPONSE_BYTE_LIMIT,
                    label=label,
                )
        return value

    @field_validator(
        "pull_request_record", "pull_request_observation_receipt", "signature_observation_receipt",
        mode="before",
    )
    @classmethod
    def reject_foreign_singletons(cls, value: object, info: ValidationInfo) -> object:
        owners: dict[str, type[BaseModel]] = {
            "pull_request_record": ExactGitHubPullRequestRecordV1,
            "pull_request_observation_receipt": GitHubAuditApiObservationReceiptV1,
            "signature_observation_receipt": GitHubSignatureObservationReceiptV1,
        }
        return _exact_model_value(
            value,
            owners[cast(str, info.field_name)],
            json_mode=info.mode == "json",
        )

    @field_validator("signature_evidence", mode="before")
    @classmethod
    def reject_foreign_evidence(cls, value: object, info: ValidationInfo) -> object:
        if info.mode != "json" and isinstance(value, BaseModel) and type(value) not in {
            GitHubVerifiedCommitEvidenceV1,
            SSHVerifiedCommitEvidenceV1,
            OpenPGPVerifiedCommitEvidenceV1,
        }:
            raise TypeError("pull-request source contains foreign signature evidence")
        if info.mode != "json" and isinstance(value, BaseModel):
            _preflight_exact_model_owners_v1(value, SignatureEvidenceV1)
        return value

    @field_validator(
        "signature_raw_response_byte_lengths",
        "signature_raw_response_bytes_base64",
        "signature_canonical_response_byte_lengths",
        "signature_canonical_response_bytes_base64",
        mode="before",
    )
    @classmethod
    def normalize_json_pairs(cls, value: object, info: ValidationInfo) -> object:
        return _exact_value_tuple(value, json_mode=info.mode == "json")

    @model_validator(mode="after")
    def validate_shape_and_digest(self) -> Self:
        if self.proof_kind == "adjudication":
            if self.reviewer_id is not None:
                raise ValueError("adjudication pull-request source requires null reviewer ID")
        elif self.reviewer_id is None:
            raise ValueError("reviewer pull-request source requires its reviewer ID")
        if (
            self.pull_request_observation_receipt.observed_at_utc
            < self.pull_request_record.merged_at_utc
        ):
            raise ValueError("pull-request source observation predates its merge")
        raw_pr = _decode_base64(self.pull_request_raw_response_base64)
        if (
            self.pull_request_observation_receipt.source_kind != "pull_request"
            or self.pull_request_observation_receipt.raw_response_byte_length != len(raw_pr)
            or self.pull_request_observation_receipt.raw_response_sha256
            != hashlib.sha256(raw_pr).hexdigest()
        ):
            raise ValueError("pull-request source bytes do not match their receipt")
        raw_signature = tuple(
            _decode_base64(value) for value in self.signature_raw_response_bytes_base64
        )
        canonical_signature = tuple(
            _decode_base64(value)
            for value in self.signature_canonical_response_bytes_base64
        )
        if (
            tuple(map(len, raw_signature)) != self.signature_raw_response_byte_lengths
            or tuple(map(len, canonical_signature))
            != self.signature_canonical_response_byte_lengths
            or tuple(hashlib.sha256(item).hexdigest() for item in raw_signature)
            != self.signature_observation_receipt.raw_response_sha256s
            or tuple(hashlib.sha256(item).hexdigest() for item in canonical_signature)
            != self.signature_observation_receipt.canonical_response_sha256s
        ):
            raise ValueError("signature source bytes do not match their receipt")
        expected = stable_digest(
            "laconian-audit-pull-request-source-v1",
            _model_payload(self, "pull_request_source_sha256"),
        )
        if self.pull_request_source_sha256 != expected:
            raise ValueError("pull-request source digest mismatch")
        return self


class AuditGitObjectArchiveV1(_AuditModel):
    schema_version: Literal["audit-git-object-archive-v1"]
    object_closure_root: Sha256
    objects: tuple[ArchivedProtocolGitObjectV1, ...] = Field(min_length=1, max_length=4_096)
    audit_git_object_archive_sha256: Sha256

    @model_validator(mode="before")
    @classmethod
    def reject_oversized_objects_before_decode(cls, value: object) -> object:
        if type(value) is cls:
            object_values: object = value.objects
        elif type(value) is dict:
            object_values = cast(dict[str, object], value).get("objects")
        else:
            return value
        if type(object_values) not in (tuple, list):
            raise ValueError("audit archive requires one exact Git-object sequence")
        archived_values = cast(Sequence[object], object_values)
        if not 1 <= len(archived_values) <= 4_096:
            raise ValueError("audit archive requires 1..4,096 Git objects")

        sized_values: list[tuple[object, int]] = []
        decoded_total = 0
        for item in archived_values:
            if type(item) is ArchivedProtocolGitObjectV1:
                size_value: object = item.size
                raw_value: object = item.raw_content_base64
            elif type(item) is dict:
                item_payload = cast(dict[str, object], item)
                size_value = item_payload.get("size")
                raw_value = item_payload.get("raw_content_base64")
            else:
                raise ValueError("audit archive contains a non-object Git entry")
            if type(size_value) is not int or size_value < 0:
                raise ValueError("audit archive object requires an exact nonnegative size")
            size = size_value
            decoded_total += size
            if decoded_total > _AUDIT_GIT_ARCHIVE_DECODED_BYTE_LIMIT:
                raise ValueError("audit Git archive decoded-byte limit exceeded")
            sized_values.append((raw_value, size))

        for raw_value, size in sized_values:
            _preflight_encoded_byte_length(
                raw_value,
                size,
                minimum=0,
                maximum=_AUDIT_GIT_ARCHIVE_DECODED_BYTE_LIMIT,
                label="audit Git archive object",
            )
        return value

    @field_validator("objects", mode="before")
    @classmethod
    def reject_foreign_objects(cls, value: object, info: ValidationInfo) -> object:
        return _exact_model_tuple(
            value, ArchivedProtocolGitObjectV1, json_mode=info.mode == "json"
        )

    @model_validator(mode="after")
    def validate_archive(self) -> Self:
        if any(type(item) is not ArchivedProtocolGitObjectV1 for item in self.objects):
            raise ValueError("audit archive contains a foreign Git-object owner")
        oids = tuple(item.oid for item in self.objects)
        if oids != tuple(sorted(oids)) or len(set(oids)) != len(oids):
            raise ValueError("audit archive objects require strict ascending unique OID order")
        if any(item.type not in ("commit", "tree", "blob") for item in self.objects):
            raise ValueError("audit archive permits only commit, tree, and blob objects")
        decoded_total = 0
        closure: list[dict[str, object]] = []
        for item in self.objects:
            raw = _decode_base64(
                item.raw_content_base64,
                max_decoded_bytes=_AUDIT_GIT_ARCHIVE_DECODED_BYTE_LIMIT,
            )
            decoded_total += len(raw)
            if decoded_total > _AUDIT_GIT_ARCHIVE_DECODED_BYTE_LIMIT:
                raise ValueError("audit Git archive decoded-byte limit exceeded")
            parsed = parse_protocol_git_object(
                oid=item.oid, object_type=item.type, raw_content=raw
            )
            if parsed.size != item.size or parsed.git_object_sha256 != item.git_object_sha256:
                raise ValueError("audit Git archive object identity mismatch")
            closure.append(
                {
                    "oid": item.oid,
                    "type": item.type,
                    "size": item.size,
                    "git_object_sha256": item.git_object_sha256,
                }
            )
        expected_closure = stable_digest("laconian-audit-git-object-closure-v1", closure)
        if self.object_closure_root != expected_closure:
            raise ValueError("audit Git object-closure root mismatch")
        expected_self = stable_digest(
            "laconian-audit-git-object-archive-v1",
            _model_payload(self, "audit_git_object_archive_sha256"),
        )
        if self.audit_git_object_archive_sha256 != expected_self:
            raise ValueError("audit Git object-archive digest mismatch")
        return self


class PullRequestProofV1(_AuditModel):
    schema_version: Literal["audit-pull-request-proof-v1"]
    proof_kind: AuditPullRequestKindV1
    campaign_id: CampaignIdV1
    reviewer_id: ReviewerIdV1 | None
    repository_id: StrictPositiveInt
    pr_number: StrictPositiveInt
    actor_account_id: StrictPositiveInt
    actor: StrictAuditString
    base_ref: Literal["main"]
    base_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    head_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    merge_commit_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    merge_actor_account_id: StrictPositiveInt
    merge_actor: StrictAuditString
    merged_at_utc: WholeSecondTimestamp
    verification_mode: SignatureVerificationModeV1
    head_signing_fingerprint: str | None = Field(
        pattern=r"^(?:[0-9A-F]{40}|SHA256:[A-Za-z0-9+/]{43})$"
    )
    signature_evidence: SignatureEvidenceV1
    changed_paths: tuple[StrictAuditString, ...]
    exact_pr_api_record_sha256: Sha256
    pull_request_source_sha256: Sha256
    pull_request_proof_sha256: Sha256

    @field_validator("signature_evidence", mode="before")
    @classmethod
    def reject_foreign_evidence(cls, value: object, info: ValidationInfo) -> object:
        if info.mode != "json" and isinstance(value, BaseModel) and type(value) not in {
            GitHubVerifiedCommitEvidenceV1,
            SSHVerifiedCommitEvidenceV1,
            OpenPGPVerifiedCommitEvidenceV1,
        }:
            raise TypeError("pull-request proof contains foreign signature evidence")
        if info.mode != "json" and isinstance(value, BaseModel):
            _preflight_exact_model_owners_v1(value, SignatureEvidenceV1)
        return value

    @field_validator("changed_paths", mode="before")
    @classmethod
    def normalize_json_changed_paths(cls, value: object, info: ValidationInfo) -> object:
        return _exact_value_tuple(value, json_mode=info.mode == "json")

    @model_validator(mode="after")
    def validate_shape_and_digest(self) -> Self:
        if (self.proof_kind == "adjudication") != (self.reviewer_id is None):
            raise ValueError("pull-request proof reviewer ID/proof kind mismatch")
        if self.changed_paths != tuple(sorted(set(self.changed_paths), key=str.encode)):
            raise ValueError("changed paths require unique UTF-8 byte order")
        if self.verification_mode == "github_verified_commit":
            if self.head_signing_fingerprint is not None:
                raise ValueError("GitHub-verified pull request requires null fingerprint")
        elif self.head_signing_fingerprint is None:
            raise ValueError("keyed pull request requires a signing fingerprint")
        expected = stable_digest(
            "laconian-audit-pull-request-proof-v1",
            _model_payload(self, "pull_request_proof_sha256"),
        )
        if self.pull_request_proof_sha256 != expected:
            raise ValueError("pull-request proof digest mismatch")
        return self


class ReviewerIdentityV1(_AuditModel):
    reviewer_id: ReviewerIdV1
    reviewer_numeric_account_id: StrictPositiveInt
    reviewer_login: StrictAuditString
    verification_mode: SignatureVerificationModeV1
    signing_fingerprint: str | None = Field(
        pattern=r"^(?:[0-9A-F]{40}|SHA256:[A-Za-z0-9+/]{43})$"
    )
    audit_reviewer_registry_sha256: Sha256

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if self.verification_mode == "github_verified_commit":
            if self.signing_fingerprint is not None:
                raise ValueError("GitHub reviewer identity requires null fingerprint")
        elif self.signing_fingerprint is None:
            raise ValueError("keyed reviewer identity requires a fingerprint")
        return self


class HumanAuditLabelV1(_AuditModel):
    audit_record_id: Sha256
    rubric_items: tuple[RubricItemJudgmentV1, ...]
    material_warning: WarningJudgmentV1 | None
    material_contradiction: bool
    contradiction_evidence: str | None = Field(default=None, max_length=1_000)
    semantic_pass: bool

    @field_validator("rubric_items", mode="before")
    @classmethod
    def reject_foreign_rubric_items(cls, value: object, info: ValidationInfo) -> object:
        exact = _exact_model_tuple(
            value,
            RubricItemJudgmentV1,
            json_mode=info.mode == "json",
        )
        if info.mode == "json" or type(exact) is not tuple:
            return exact
        return tuple(
            _class_bound_revalidate_external_model(item, RubricItemJudgmentV1)
            for item in cast(tuple[object, ...], exact)
        )

    @field_validator("material_warning", mode="before")
    @classmethod
    def reject_foreign_warning(cls, value: object, info: ValidationInfo) -> object:
        if value is not None and info.mode != "json":
            exact = _require_exact_owner(value, WarningJudgmentV1)
            return _class_bound_revalidate_external_model(
                exact,
                WarningJudgmentV1,
            )
        return value

    @model_validator(mode="after")
    def validate_label(self) -> Self:
        if tuple(item.item_index for item in self.rubric_items) != tuple(
            range(len(self.rubric_items))
        ):
            raise ValueError("human-audit rubric indices must be contiguous")
        if (self.contradiction_evidence is not None) != self.material_contradiction:
            raise ValueError("human-audit contradiction evidence shape mismatch")
        expected = derive_semantic_pass(
            rubric_items=self.rubric_items,
            material_warning_requirement=(
                "required" if self.material_warning is not None else None
            ),
            material_warning=self.material_warning,
            material_contradiction=self.material_contradiction,
        )
        if self.semantic_pass != expected:
            raise ValueError("human-audit semantic pass mismatch")
        return self


class CommitmentHeaderV1(_AuditModel):
    schema_version: Literal["audit-commitment-v1"]
    campaign_id: CampaignIdV1
    campaign_registry_sha256: Sha256
    reviewer_id: ReviewerIdV1
    audit_reviewer_registry_sha256: Sha256
    sample_manifest_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256


class ReviewerCommitmentV1(_AuditModel):
    header: CommitmentHeaderV1
    commitment_sha256: Sha256

    @field_validator("header", mode="before")
    @classmethod
    def reject_foreign_header(cls, value: object, info: ValidationInfo) -> object:
        return _exact_model_value(
            value, CommitmentHeaderV1, json_mode=info.mode == "json"
        )


def canonical_label_jsonl(labels: Sequence[HumanAuditLabelV1]) -> bytes:
    """Return audit-ID byte-ordered CanonicalJSONV1 records with one mandatory final LF."""

    if type(labels) not in {tuple, list} or not labels:
        raise ValueError("canonical audit labels require a nonempty sequence")
    validated: list[HumanAuditLabelV1] = []
    for item in labels:
        if type(item) is not HumanAuditLabelV1:
            raise TypeError("canonical audit labels require exact HumanAuditLabelV1 owners")
        _preflight_exact_model_owners_v1(item, HumanAuditLabelV1)
        validated.append(HumanAuditLabelV1.model_validate(item))
    ordered = sorted(validated, key=lambda item: item.audit_record_id.encode("utf-8"))
    identifiers = tuple(item.audit_record_id for item in ordered)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("canonical audit labels require unique audit IDs")
    return b"".join(canonical_json_v1(item.model_dump(mode="json")) + b"\n" for item in ordered)


def compute_commitment(
    *, header: CommitmentHeaderV1, salt: bytes, exact_label_bytes: bytes
) -> str:
    """Hash the exact commitment header, 32-byte salt, and canonical label JSONL bytes."""

    if type(header) is not CommitmentHeaderV1:
        raise TypeError("commitment header requires its exact owner")
    _preflight_exact_model_owners_v1(header, CommitmentHeaderV1)
    checked_header = CommitmentHeaderV1.model_validate(header)
    if type(salt) is not bytes or len(salt) != 32:
        raise ValueError("audit commitment salt must be exactly 32 bytes")
    if type(exact_label_bytes) is not bytes or not exact_label_bytes:
        raise ValueError("audit commitment labels must be exact nonempty bytes")
    return hashlib.sha256(
        b"laconian-audit-commitment-v1\0"
        + canonical_json_v1(checked_header.model_dump(mode="json"))
        + b"\0"
        + salt
        + b"\0"
        + exact_label_bytes
    ).hexdigest()


class ReviewerRevealV1(_AuditModel):
    schema_version: Literal["audit-reveal-v1"]
    campaign_id: CampaignIdV1
    campaign_registry_sha256: Sha256
    reviewer_id: ReviewerIdV1
    audit_reviewer_registry_sha256: Sha256
    sample_manifest_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256
    commitment_sha256: Sha256
    salt_hex: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    labels_byte_length: int = Field(strict=True, gt=0)
    labels_sha256: Sha256
    labels: tuple[HumanAuditLabelV1, ...]
    reveal_sha256: Sha256

    @field_validator("labels", mode="before")
    @classmethod
    def reject_foreign_labels(cls, value: object, info: ValidationInfo) -> object:
        return _exact_model_tuple(value, HumanAuditLabelV1, json_mode=info.mode == "json")

    @model_validator(mode="after")
    def validate_reveal(self) -> Self:
        if _SALT_RE.fullmatch(self.salt_hex) is None or len(bytes.fromhex(self.salt_hex)) != 32:
            raise ValueError("audit reveal salt must be exactly 32 lowercase-hex bytes")
        identifiers = tuple(item.audit_record_id for item in self.labels)
        if identifiers != tuple(sorted(set(identifiers), key=str.encode)):
            raise ValueError("audit reveal labels require unique audit-ID byte order")
        exact = canonical_label_jsonl(self.labels)
        if (
            self.labels_byte_length != len(exact)
            or self.labels_sha256 != hashlib.sha256(exact).hexdigest()
        ):
            raise ValueError("audit reveal exact label bytes mismatch")
        expected = stable_digest(
            "laconian-audit-reveal-v1", _model_payload(self, "reveal_sha256")
        )
        if self.reveal_sha256 != expected:
            raise ValueError("audit reveal digest mismatch")
        return self


class ReviewerChainV1(_AuditModel):
    identity: ReviewerIdentityV1
    commitment: ReviewerCommitmentV1
    commitment_pr: PullRequestProofV1
    reveal: ReviewerRevealV1
    reveal_pr: PullRequestProofV1
    reviewer_chain_proof_sha256: Sha256

    @field_validator(
        "identity", "commitment", "commitment_pr", "reveal", "reveal_pr", mode="before"
    )
    @classmethod
    def reject_foreign_members(cls, value: object, info: ValidationInfo) -> object:
        owners: dict[str, type[BaseModel]] = {
            "identity": ReviewerIdentityV1,
            "commitment": ReviewerCommitmentV1,
            "commitment_pr": PullRequestProofV1,
            "reveal": ReviewerRevealV1,
            "reveal_pr": PullRequestProofV1,
        }
        return _exact_model_value(
            value,
            owners[cast(str, info.field_name)],
            json_mode=info.mode == "json",
        )

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        expected = stable_digest(
            "laconian-audit-reviewer-chain-proof-v1",
            _model_payload(self, "reviewer_chain_proof_sha256"),
        )
        if self.reviewer_chain_proof_sha256 != expected:
            raise ValueError("reviewer chain proof digest mismatch")
        return self


class ConsensusLabelV1(_AuditModel):
    audit_record_id: Sha256
    semantic_pass: bool | None
    resolution: Literal["reviewer-agreement", "adjudicated", "unresolved"]
    rationale: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.resolution == "reviewer-agreement":
            if self.semantic_pass is None or self.rationale is not None:
                raise ValueError("reviewer agreement requires a Boolean and null rationale")
        else:
            if self.resolution == "adjudicated" and self.semantic_pass is None:
                raise ValueError("adjudication requires a Boolean consensus")
            if self.resolution == "unresolved" and self.semantic_pass is not None:
                raise ValueError("unresolved consensus requires a null decision")
            if (
                self.rationale is None
                or not self.rationale
                or unicodedata.normalize("NFC", self.rationale) != self.rationale
            ):
                raise ValueError("disagreement consensus requires a nonempty NFC rationale")
        return self


class AuditAdjudicationCoreV1(_AuditModel):
    schema_version: Literal["audit-adjudication-core-v1"]
    campaign_id: CampaignIdV1
    campaign_registry_sha256: Sha256
    audit_reviewer_registry_sha256: Sha256
    sample_manifest_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256
    audit_adjudication_protocol_sha256: Sha256
    reveal_sha256s: tuple[Sha256, Sha256]
    consensus: tuple[ConsensusLabelV1, ...]
    judge_labels_were_available: Literal[False] = False
    adjudication_core_sha256: Sha256

    @field_validator("consensus", mode="before")
    @classmethod
    def reject_foreign_consensus(cls, value: object, info: ValidationInfo) -> object:
        return _exact_model_tuple(value, ConsensusLabelV1, json_mode=info.mode == "json")

    @field_validator("reveal_sha256s", mode="before")
    @classmethod
    def normalize_json_reveal_hashes(cls, value: object, info: ValidationInfo) -> object:
        return _exact_value_tuple(value, json_mode=info.mode == "json")

    @model_validator(mode="after")
    def validate_core(self) -> Self:
        if self.reveal_sha256s[0] == self.reveal_sha256s[1]:
            raise ValueError("adjudication core requires two distinct reveal digests")
        identifiers = tuple(item.audit_record_id for item in self.consensus)
        if identifiers != tuple(sorted(set(identifiers), key=str.encode)):
            raise ValueError("adjudication consensus requires unique audit-ID byte order")
        expected = stable_digest(
            "laconian-audit-adjudication-core-v1",
            _model_payload(self, "adjudication_core_sha256"),
        )
        if self.adjudication_core_sha256 != expected:
            raise ValueError("adjudication core digest mismatch")
        return self


class ExactGitHubReviewRecordV1(_AuditModel):
    schema_version: Literal["audit-github-review-record-v1"]
    repository_id: StrictPositiveInt
    pr_number: StrictPositiveInt
    review_id: StrictPositiveInt
    actor_account_id: StrictPositiveInt
    actor_login: StrictAuditString
    reviewed_head_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    body: ReviewBodyV1
    state: Literal["APPROVED"]
    submitted_at_utc: WholeSecondTimestamp
    exact_api_record_sha256: Sha256

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        expected = stable_digest(
            "laconian-audit-github-review-record-v1",
            _model_payload(self, "exact_api_record_sha256"),
        )
        if self.exact_api_record_sha256 != expected:
            raise ValueError("exact GitHub review record digest mismatch")
        return self


class ExactGitHubReviewSourceV1(_AuditModel):
    schema_version: Literal["audit-github-review-source-v1"]
    reviewer_id: ReviewerIdV1
    record: ExactGitHubReviewRecordV1
    observation_receipt: GitHubAuditApiObservationReceiptV1
    raw_response_base64: CanonicalAuditBase64
    github_review_source_sha256: Sha256

    @model_validator(mode="before")
    @classmethod
    def reject_declared_size_mismatch_before_decode(cls, value: object) -> object:
        if type(value) is cls:
            source = value
            receipt_value: object = source.observation_receipt
            raw_value: object = source.raw_response_base64
        elif type(value) is dict:
            payload = cast(dict[str, object], value)
            receipt_value = payload.get("observation_receipt")
            raw_value = payload.get("raw_response_base64")
        else:
            return value
        if type(receipt_value) is GitHubAuditApiObservationReceiptV1:
            declared_length: object = receipt_value.raw_response_byte_length
        elif type(receipt_value) is dict:
            declared_length = cast(dict[str, object], receipt_value).get(
                "raw_response_byte_length"
            )
        else:
            raise ValueError("GitHub review source requires an exact receipt before decoding")
        _preflight_encoded_byte_length(
            raw_value,
            declared_length,
            minimum=1,
            maximum=_AUDIT_API_RAW_BYTE_LIMIT,
            label="GitHub review source",
        )
        return value

    @field_validator("record", "observation_receipt", mode="before")
    @classmethod
    def reject_foreign_members(cls, value: object, info: ValidationInfo) -> object:
        owner = (
            ExactGitHubReviewRecordV1
            if info.field_name == "record"
            else GitHubAuditApiObservationReceiptV1
        )
        return _exact_model_value(value, owner, json_mode=info.mode == "json")

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        if self.observation_receipt.observed_at_utc < self.record.submitted_at_utc:
            raise ValueError("GitHub review source observation predates its submission")
        raw = _decode_base64(self.raw_response_base64)
        if (
            self.observation_receipt.source_kind != "review"
            or self.observation_receipt.raw_response_byte_length != len(raw)
            or self.observation_receipt.raw_response_sha256
            != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("GitHub review source bytes do not match their receipt")
        expected = stable_digest(
            "laconian-audit-github-review-source-v1",
            _model_payload(self, "github_review_source_sha256"),
        )
        if self.github_review_source_sha256 != expected:
            raise ValueError("GitHub review source digest mismatch")
        return self


class ExactGitHubReviewSignoffV1(_AuditModel):
    schema_version: Literal["audit-adjudication-github-review-v1"]
    reviewer_id: ReviewerIdV1
    reviewer_numeric_account_id: StrictPositiveInt
    reviewer_login: StrictAuditString
    audit_reviewer_registry_sha256: Sha256
    adjudication_core_sha256: Sha256
    repository_id: StrictPositiveInt
    pr_number: StrictPositiveInt
    review_id: StrictPositiveInt
    state: Literal["APPROVED"]
    reviewed_head_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    submitted_at_utc: WholeSecondTimestamp
    fixed_body_sha256: Sha256
    exact_api_record_sha256: Sha256
    github_review_source_sha256: Sha256
    signoff_proof_sha256: Sha256

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        expected = stable_digest(
            "laconian-audit-adjudication-github-review-v1",
            _model_payload(self, "signoff_proof_sha256"),
        )
        if self.signoff_proof_sha256 != expected:
            raise ValueError("GitHub adjudication signoff digest mismatch")
        return self


class AuditAdjudicationV1(_AuditModel):
    schema_version: Literal["audit-adjudication-v1"]
    core: AuditAdjudicationCoreV1
    signoffs: tuple[ExactGitHubReviewSignoffV1, ExactGitHubReviewSignoffV1]
    adjudication_pr: PullRequestProofV1
    adjudication_sha256: Sha256

    @field_validator("core", "adjudication_pr", mode="before")
    @classmethod
    def reject_foreign_singletons(cls, value: object, info: ValidationInfo) -> object:
        owner = AuditAdjudicationCoreV1 if info.field_name == "core" else PullRequestProofV1
        return _exact_model_value(value, owner, json_mode=info.mode == "json")

    @field_validator("signoffs", mode="before")
    @classmethod
    def reject_foreign_signoffs(cls, value: object, info: ValidationInfo) -> object:
        return _exact_model_tuple(
            value, ExactGitHubReviewSignoffV1, json_mode=info.mode == "json"
        )

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        reviewer_ids = tuple(item.reviewer_id for item in self.signoffs)
        if reviewer_ids != tuple(sorted(set(reviewer_ids), key=str.encode)):
            raise ValueError("adjudication signoffs require reviewer-ID byte order")
        expected = stable_digest(
            "laconian-audit-adjudication-v1",
            _model_payload(self, "adjudication_sha256"),
        )
        if self.adjudication_sha256 != expected:
            raise ValueError("final adjudication envelope digest mismatch")
        return self


def _decode_base64(
    value: str, *, max_decoded_bytes: int = _AUDIT_API_RAW_BYTE_LIMIT
) -> bytes:
    _canonical_base64(value, max_decoded_bytes=max_decoded_bytes)
    return base64.b64decode(value.encode("ascii"), validate=True)


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _preflight_model_owner(value: object, owner: type[_ModelT]) -> None:
    if type(value) is not owner:
        raise TypeError(f"expected exact {owner.__name__} owner")
    _preflight_exact_model_owners_v1(value, owner)


def _preflight_model_tuple(
    value: object,
    owner: type[BaseModel],
    *,
    length: int,
    error_message: str,
) -> None:
    if type(value) is not tuple or len(cast(tuple[object, ...], value)) != length:
        raise TypeError(error_message)
    for item in cast(tuple[object, ...], value):
        _preflight_model_owner(item, owner)


def _revalidate_model(value: _ModelT, owner: type[_ModelT]) -> _ModelT:
    _preflight_model_owner(value, owner)
    return owner.model_validate(value)


def _checked_sample(
    evidence: VerifiedBenchmarkProviderEvidenceV1,
    sample: VerifiedAuditSampleRootV1,
) -> VerifiedAuditSampleRootV1:
    if (
        type(sample) is not VerifiedAuditSampleRootV1
        or type(sample.population) is not VerifiedAuditPopulationV1
        or type(sample.manifest) is not AuditSampleManifestV1
        or type(sample.packet) is not BlindAuditPacketV1
    ):
        raise TypeError("expected exact verified audit-sample root")
    verify_audit_sample(
        sample.manifest,
        sample.packet,
        population=sample.population,
        provider_evidence=evidence,
    )
    expected_root = stable_digest(
        "laconian-audit-sample-root-v1",
        {
            "population_attachment_sha256": (
                sample.population.attachment.population_attachment_sha256
            ),
            "records_sha256": sample.population.attachment.records_sha256,
            "sample_manifest_sha256": sample.manifest.sample_manifest_sha256,
            "blind_packet_sha256": sample.packet.packet_sha256,
        },
    )
    if sample.audit_sample_root_sha256 != expected_root:
        raise ValueError("verified audit-sample root digest mismatch")
    checked_sample = VerifiedAuditSampleRootV1(
        population=sample.population,
        manifest=sample.manifest,
        packet=sample.packet,
        audit_sample_root_sha256=sample.audit_sample_root_sha256,
    )
    return checked_sample


def _audit_registry(evidence: VerifiedBenchmarkProviderEvidenceV1) -> AuditReviewerRegistryV1:
    registry = _revalidate_model(
        evidence.index.audit_reviewer_registry, AuditReviewerRegistryV1
    )
    # The model and provider owner both recompute the v2 registry.  Compare every retained scalar
    # again here so no copied registry hash can stand in for the exact bindings.
    if (
        evidence.index.audit_reviewer_registry_sha256
        != registry.audit_reviewer_registry_sha256
    ):
        raise ValueError("provider audit-reviewer registry authority mismatch")
    return registry


def _repository_authority(
    evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> tuple[int, str, str]:
    attestations = evidence.index.protocol_attestations
    if type(attestations) is not tuple or len(attestations) != 3:
        raise ValueError("provider evidence requires exactly three protocol attestations")
    repository_ids: list[int] = []
    slugs: list[tuple[str, str]] = []
    for attestation in attestations:
        signature = attestation.signature_evidence
        rest = signature.github_rest_verification
        graphql = signature.github_graphql_signature
        match = _REPOSITORY_SLUG_RE.fullmatch(rest.endpoint)
        if match is None or not rest.endpoint.endswith(f"/{signature.commit_oid}"):
            raise ValueError(
                "protocol attestation REST endpoint has no strict repository authority"
            )
        owner, name = match.group("owner"), match.group("name")
        if name in {".", ".."} or name.casefold().endswith(".git"):
            raise ValueError(
                "protocol attestation REST endpoint has no strict repository authority"
            )
        slugs.append((owner, name))
        repository_ids.extend((rest.repository_id, graphql.repository_id))
    if len(set(slugs)) != 1 or len(set(repository_ids)) != 1:
        raise ValueError("protocol attestations do not unanimously identify one repository")
    owner, name = slugs[0]
    return repository_ids[0], owner, name


def _archive_objects(
    archive: AuditGitObjectArchiveV1,
) -> dict[str, ParsedProtocolGitObjectV1]:
    checked = _revalidate_model(archive, AuditGitObjectArchiveV1)
    result: dict[str, ParsedProtocolGitObjectV1] = {}
    for item in checked.objects:
        parsed = parse_protocol_git_object(
            oid=item.oid,
            object_type=item.type,
            raw_content=_decode_base64(
                item.raw_content_base64,
                max_decoded_bytes=_AUDIT_GIT_ARCHIVE_DECODED_BYTE_LIMIT,
            ),
        )
        if parsed.oid in result:
            raise ValueError("audit archive contains a duplicate Git object")
        result[parsed.oid] = parsed
    return result


def _required_json_member(value: Mapping[str, object], key: str, path: str) -> object:
    if key not in value:
        raise ProtocolReviewVerificationError(f"provider selected path {path}.{key} is missing")
    return value[key]


def _selected_true(value: object, path: str) -> bool:
    if type(value) is not bool or value is not True:
        raise ProtocolReviewVerificationError(
            f"provider selected path {path} must be the JSON boolean true"
        )
    return True


def _whole_second(value: object, path: str) -> str:
    text = _selected_string(value, path)
    try:
        # Reuse the exact public alias through a tiny validation owner rather than accepting a
        # datetime or offset-equivalent spelling.
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise ProtocolReviewVerificationError(f"{path} is not whole-second UTC") from None
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise ProtocolReviewVerificationError(f"{path} is not canonical whole-second UTC")
    return text


def _exact_pr_record_from_raw(
    raw: bytes,
    *,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
    expected_pr_number: int,
) -> ExactGitHubPullRequestRecordV1:
    response = _parse_provider_json(raw)
    user = _selected_object(_required_json_member(response, "user", "pull_request"), "user")
    base = _selected_object(_required_json_member(response, "base", "pull_request"), "base")
    base_repo = _selected_object(_required_json_member(base, "repo", "base"), "base.repo")
    base_owner = _selected_object(
        _required_json_member(base_repo, "owner", "base.repo"), "base.repo.owner"
    )
    head = _selected_object(_required_json_member(response, "head", "pull_request"), "head")
    merged_by = _selected_object(
        _required_json_member(response, "merged_by", "pull_request"), "merged_by"
    )
    number = _selected_positive_int(
        _required_json_member(response, "number", "pull_request"), "number"
    )
    raw_repository_id = _selected_positive_int(
        _required_json_member(base_repo, "id", "base.repo"), "base.repo.id"
    )
    raw_owner = _selected_string(
        _required_json_member(base_owner, "login", "base.repo.owner"),
        "base.repo.owner.login",
    )
    raw_name = _selected_string(
        _required_json_member(base_repo, "name", "base.repo"), "base.repo.name"
    )
    if (
        number != expected_pr_number
        or raw_repository_id != repository_id
        or raw_owner != repository_owner
        or raw_name != repository_name
    ):
        raise ProtocolReviewVerificationError("raw pull request repository/number mismatch")
    payload: dict[str, object] = {
        "schema_version": "audit-github-pull-request-record-v1",
        "repository_id": raw_repository_id,
        "pr_number": number,
        "actor_account_id": _selected_positive_int(
            _required_json_member(user, "id", "user"), "user.id"
        ),
        "actor": _selected_string(
            _required_json_member(user, "login", "user"), "user.login"
        ),
        "base_ref": _selected_string(
            _required_json_member(base, "ref", "base"), "base.ref"
        ),
        "head_sha": _selected_string(
            _required_json_member(head, "sha", "head"), "head.sha"
        ),
        "merge_commit_sha": _selected_string(
            _required_json_member(response, "merge_commit_sha", "pull_request"),
            "merge_commit_sha",
        ),
        "merge_actor_account_id": _selected_positive_int(
            _required_json_member(merged_by, "id", "merged_by"), "merged_by.id"
        ),
        "merge_actor": _selected_string(
            _required_json_member(merged_by, "login", "merged_by"), "merged_by.login"
        ),
        "state": _selected_string(
            _required_json_member(response, "state", "pull_request"), "state"
        ),
        "merged": _selected_true(
            _required_json_member(response, "merged", "pull_request"), "merged"
        ),
        "merged_at_utc": _whole_second(
            _required_json_member(response, "merged_at", "pull_request"), "merged_at"
        ),
    }
    payload["exact_api_record_sha256"] = stable_digest(
        "laconian-audit-github-pull-request-record-v1", payload
    )
    return ExactGitHubPullRequestRecordV1.model_validate(payload)


def _decode_signature_pairs(
    source: AuditPullRequestEvidenceSourceV1,
) -> tuple[tuple[bytes, bytes], tuple[bytes, bytes]]:
    raw = cast(
        tuple[bytes, bytes],
        tuple(_decode_base64(value) for value in source.signature_raw_response_bytes_base64),
    )
    canonical = cast(
        tuple[bytes, bytes],
        tuple(
            _decode_base64(value)
            for value in source.signature_canonical_response_bytes_base64
        ),
    )
    if (
        tuple(map(len, raw)) != source.signature_raw_response_byte_lengths
        or tuple(map(len, canonical)) != source.signature_canonical_response_byte_lengths
        or tuple(hashlib.sha256(item).hexdigest() for item in raw)
        != source.signature_observation_receipt.raw_response_sha256s
        or tuple(hashlib.sha256(item).hexdigest() for item in canonical)
        != source.signature_observation_receipt.canonical_response_sha256s
    ):
        raise ValueError("pull-request signature source byte bindings mismatch")
    return raw, canonical


def _expected_git_identity_and_key(
    *,
    registry: AuditReviewerRegistryV1,
    reviewer_id: str | None,
    verification_mode: SignatureVerificationModeV1,
    fingerprint: str | None,
    signer_account_id: int,
    signer_login: str,
) -> tuple[
    AuditReviewerSigningKeyV1 | None,
    tuple[str, str, str, str] | None,
]:
    if reviewer_id is None:
        if verification_mode != "github_verified_commit" or fingerprint is not None:
            raise ValueError("adjudication signer must use GitHub verified commit mode")
        if any(
            signer_account_id == reviewer.reviewer_numeric_account_id
            or signer_login == reviewer.reviewer_login
            for reviewer in registry.reviewers
        ):
            raise ValueError("adjudication signer must be distinct from both audit reviewers")
        return None, None
    matching = tuple(item for item in registry.reviewers if item.reviewer_id == reviewer_id)
    if len(matching) != 1:
        raise ValueError("pull-request reviewer is absent from the audit registry")
    reviewer = matching[0]
    if (
        signer_account_id != reviewer.reviewer_numeric_account_id
        or signer_login != reviewer.reviewer_login
        or verification_mode != reviewer.verification_mode
        or fingerprint != reviewer.signing_fingerprint
    ):
        raise ValueError("pull-request actor/signer differs from the selected audit reviewer")
    key = reviewer.signing_key
    if key is None:
        return None, None
    return key, (
        key.author_name_ascii,
        key.author_email_ascii,
        key.committer_name_ascii,
        key.committer_email_ascii,
    )


def _verify_pull_request_source(
    *,
    source: AuditPullRequestEvidenceSourceV1,
    proof: PullRequestProofV1,
    expected_kind: AuditPullRequestKindV1,
    expected_reviewer_id: str | None,
    expected_primary_path: str,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
    registry: AuditReviewerRegistryV1,
    evidence: VerifiedBenchmarkProviderEvidenceV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> None:
    source = _revalidate_model(source, AuditPullRequestEvidenceSourceV1)
    proof = _revalidate_model(proof, PullRequestProofV1)
    if (
        source.proof_kind != expected_kind
        or proof.proof_kind != expected_kind
        or source.reviewer_id != expected_reviewer_id
        or proof.reviewer_id != expected_reviewer_id
        or source.campaign_id != evidence.index.campaign_id
        or proof.campaign_id != evidence.index.campaign_id
    ):
        raise ValueError("pull-request source/proof kind, reviewer, or campaign mismatch")
    raw_pr = _decode_base64(source.pull_request_raw_response_base64)
    pr_receipt = source.pull_request_observation_receipt
    if (
        pr_receipt.source_kind != "pull_request"
        or pr_receipt.repository_id != repository_id
        or pr_receipt.raw_response_byte_length != len(raw_pr)
        or pr_receipt.raw_response_sha256 != hashlib.sha256(raw_pr).hexdigest()
    ):
        raise ValueError("pull-request observation receipt byte binding mismatch")
    expected_endpoint = (
        f"GET /repos/{repository_owner}/{repository_name}/pulls/"
        f"{source.pull_request_record.pr_number}"
    )
    if pr_receipt.endpoint != expected_endpoint:
        raise ValueError("pull-request observation endpoint mismatch")
    fresh_record = _exact_pr_record_from_raw(
        raw_pr,
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        expected_pr_number=source.pull_request_record.pr_number,
    )
    if canonical_json_v1(fresh_record.model_dump(mode="json")) != canonical_json_v1(
        source.pull_request_record.model_dump(mode="json")
    ):
        raise ValueError("raw pull request does not reconstruct the retained exact record")
    record = fresh_record
    if record.actor_account_id != proof.actor_account_id or record.actor != proof.actor:
        raise ValueError("pull-request proof actor differs from raw source")
    if (
        record.repository_id != proof.repository_id
        or record.pr_number != proof.pr_number
        or record.base_ref != proof.base_ref
        or record.head_sha != proof.head_sha
        or record.merge_commit_sha != proof.merge_commit_sha
        or record.merge_actor_account_id != proof.merge_actor_account_id
        or record.merge_actor != proof.merge_actor
        or record.merged_at_utc != proof.merged_at_utc
        or record.exact_api_record_sha256 != proof.exact_pr_api_record_sha256
        or source.pull_request_source_sha256 != proof.pull_request_source_sha256
    ):
        raise ValueError("pull-request proof differs from reconstructed source")
    raw_signature, canonical_signature = _decode_signature_pairs(source)
    head = objects.get(record.head_sha)
    merge = objects.get(record.merge_commit_sha)
    if (
        head is None
        or merge is None
        or head.object_type != "commit"
        or merge.object_type != "commit"
    ):
        raise ValueError("pull-request source references a missing commit object")
    merge_view = _parse_commit_view(merge)
    if not merge_view.parent_oids:
        raise ValueError("pull-request merge commit has no first parent")
    signing_key, git_identity = _expected_git_identity_and_key(
        registry=registry,
        reviewer_id=expected_reviewer_id,
        verification_mode=proof.verification_mode,
        fingerprint=proof.head_signing_fingerprint,
        signer_account_id=record.actor_account_id,
        signer_login=record.actor,
    )
    signature_source = ProtocolSignatureEvidenceSourceV1(
        observation_receipt=source.signature_observation_receipt,
        signature_evidence=source.signature_evidence,
        raw_response_bytes=raw_signature,
        canonical_response_bytes=canonical_signature,
    )
    fresh_evidence = verify_commit_signature_evidence_source(
        source=signature_source,
        commit=head,
        expected_parent_oid=merge_view.parent_oids[0],
        expected_primary_path=expected_primary_path,
        expected_repository_id=repository_id,
        expected_repository_owner=repository_owner,
        expected_repository_name=repository_name,
        expected_signer_numeric_account_id=record.actor_account_id,
        expected_signer_login=record.actor,
        expected_verification_mode=proof.verification_mode,
        expected_signing_fingerprint=proof.head_signing_fingerprint,
        signing_key=signing_key,
        expected_git_identity=git_identity,
        identity_registry_bundle=evidence.identity_registry_bundle,
        audit_reviewer_registry=registry if signing_key is not None else None,
    )
    if canonical_json_v1(fresh_evidence.model_dump(mode="json")) != canonical_json_v1(
        proof.signature_evidence.model_dump(mode="json")
    ):
        raise ValueError("pull-request proof signature differs from fresh reconstruction")
    expected_proof_payload: dict[str, object] = {
        "schema_version": "audit-pull-request-proof-v1",
        "proof_kind": expected_kind,
        "campaign_id": evidence.index.campaign_id,
        "reviewer_id": expected_reviewer_id,
        "repository_id": repository_id,
        "pr_number": record.pr_number,
        "actor_account_id": record.actor_account_id,
        "actor": record.actor,
        "base_ref": "main",
        "base_sha": merge_view.parent_oids[0],
        "head_sha": record.head_sha,
        "merge_commit_sha": record.merge_commit_sha,
        "merge_actor_account_id": record.merge_actor_account_id,
        "merge_actor": record.merge_actor,
        "merged_at_utc": record.merged_at_utc,
        "verification_mode": proof.verification_mode,
        "head_signing_fingerprint": proof.head_signing_fingerprint,
        "signature_evidence": fresh_evidence.model_dump(mode="json"),
        "changed_paths": proof.changed_paths,
        "exact_pr_api_record_sha256": record.exact_api_record_sha256,
        "pull_request_source_sha256": source.pull_request_source_sha256,
    }
    expected_proof_payload["pull_request_proof_sha256"] = stable_digest(
        "laconian-audit-pull-request-proof-v1", expected_proof_payload
    )
    fresh_proof = PullRequestProofV1.model_validate(expected_proof_payload)
    if canonical_json_v1(fresh_proof.model_dump(mode="json")) != canonical_json_v1(
        proof.model_dump(mode="json")
    ):
        raise ValueError("pull-request proof differs from its reconstructed source")


def _record_from_source(
    source: AuditPullRequestEvidenceSourceV1,
    *,
    expected_kind: AuditPullRequestKindV1,
    expected_reviewer_id: str | None,
    campaign_id: str,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
) -> ExactGitHubPullRequestRecordV1:
    source = _revalidate_model(source, AuditPullRequestEvidenceSourceV1)
    if (
        source.proof_kind != expected_kind
        or source.reviewer_id != expected_reviewer_id
        or source.campaign_id != campaign_id
    ):
        raise ValueError("pull-request source logical identity mismatch")
    raw = _decode_base64(source.pull_request_raw_response_base64)
    receipt = source.pull_request_observation_receipt
    expected_endpoint = (
        f"GET /repos/{repository_owner}/{repository_name}/pulls/"
        f"{source.pull_request_record.pr_number}"
    )
    if (
        receipt.source_kind != "pull_request"
        or receipt.repository_id != repository_id
        or receipt.endpoint != expected_endpoint
        or receipt.raw_response_byte_length != len(raw)
        or receipt.raw_response_sha256 != hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError("pull-request source observation receipt mismatch")
    fresh = _exact_pr_record_from_raw(
        raw,
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        expected_pr_number=source.pull_request_record.pr_number,
    )
    if canonical_json_v1(fresh.model_dump(mode="json")) != canonical_json_v1(
        source.pull_request_record.model_dump(mode="json")
    ):
        raise ValueError("pull-request source raw record reconstruction mismatch")
    return fresh


def _verify_unselected_commitment_source(
    *,
    source: AuditPullRequestEvidenceSourceV1,
    reviewer_id: str,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
    registry: AuditReviewerRegistryV1,
    evidence: VerifiedBenchmarkProviderEvidenceV1,
    sample: VerifiedAuditSampleRootV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> ExactGitHubPullRequestRecordV1:
    """Verify the other reviewer's commitment source used as ancestry authority."""

    record = _record_from_source(
        source,
        expected_kind="commitment",
        expected_reviewer_id=reviewer_id,
        campaign_id=evidence.index.campaign_id,
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
    )
    matching = tuple(item for item in registry.reviewers if item.reviewer_id == reviewer_id)
    if len(matching) != 1:
        raise ValueError("commitment source reviewer is absent from the audit registry")
    reviewer = matching[0]
    head = objects.get(record.head_sha)
    merge = objects.get(record.merge_commit_sha)
    if (
        head is None
        or merge is None
        or head.object_type != "commit"
        or merge.object_type != "commit"
    ):
        raise ValueError("commitment source references a missing head or merge commit")
    head_view = _parse_commit_view(head)
    merge_view = _parse_commit_view(merge)
    if (
        len(merge_view.parent_oids) != 2
        or merge_view.parent_oids[1] != head.oid
        or head_view.parent_oids != (merge_view.parent_oids[0],)
        or head_view.signature is None
        or merge_view.tree_oid != head_view.tree_oid
    ):
        raise ValueError("commitment source head/merge topology mismatch")
    signing_key, git_identity = _expected_git_identity_and_key(
        registry=registry,
        reviewer_id=reviewer_id,
        verification_mode=reviewer.verification_mode,
        fingerprint=reviewer.signing_fingerprint,
        signer_account_id=record.actor_account_id,
        signer_login=record.actor,
    )
    raw_signature, canonical_signature = _decode_signature_pairs(source)
    signature_source = ProtocolSignatureEvidenceSourceV1(
        observation_receipt=source.signature_observation_receipt,
        signature_evidence=source.signature_evidence,
        raw_response_bytes=raw_signature,
        canonical_response_bytes=canonical_signature,
    )
    verify_commit_signature_evidence_source(
        source=signature_source,
        commit=head,
        expected_parent_oid=merge_view.parent_oids[0],
        expected_primary_path=_expected_paths(
            "commitment", evidence.index.campaign_id, reviewer_id
        )[0],
        expected_repository_id=repository_id,
        expected_repository_owner=repository_owner,
        expected_repository_name=repository_name,
        expected_signer_numeric_account_id=reviewer.reviewer_numeric_account_id,
        expected_signer_login=reviewer.reviewer_login,
        expected_verification_mode=reviewer.verification_mode,
        expected_signing_fingerprint=reviewer.signing_fingerprint,
        signing_key=signing_key,
        expected_git_identity=git_identity,
        identity_registry_bundle=evidence.identity_registry_bundle,
        audit_reviewer_registry=registry if signing_key is not None else None,
    )
    base = objects.get(merge_view.parent_oids[0])
    if base is None or base.object_type != "commit":
        raise ValueError("commitment source merge base is missing")
    expected_paths = _expected_paths("commitment", evidence.index.campaign_id, reviewer_id)
    changed: dict[str, tuple[tuple[str, str] | None, tuple[str, str] | None]] = {}
    _simultaneous_tree_diff(
        _parse_commit_view(base).tree_oid,
        head_view.tree_oid,
        prefix=b"",
        objects=objects,
        selected=set(),
        changed=changed,
        expected_paths=expected_paths,
    )
    if tuple(changed) != expected_paths:
        raise ValueError("commitment source delta differs from its exact allowlist")
    before_entry, after_entry = changed[expected_paths[0]]
    if before_entry is not None or after_entry is None or after_entry[0] != "100644":
        raise ValueError("commitment source must add one regular blob")
    blob = objects.get(after_entry[1])
    try:
        if blob is None or blob.object_type != "blob" or not blob.raw_content.endswith(b"\n"):
            raise ValueError("commitment source does not select one LF-terminated blob")
        payload = blob.raw_content[:-1]
        parsed = parse_canonical_json_v1(payload)
        if type(parsed) is not dict:
            raise ValueError("commitment source payload must be one JSON object")
        commitment = ReviewerCommitmentV1.model_validate_json(payload)
    except (TypeError, ValueError) as error:
        raise ValueError("commitment source is not one canonical reviewer commitment") from error
    if canonical_json_v1(commitment.model_dump(mode="json")) + b"\n" != blob.raw_content:
        raise ValueError("commitment source is not one canonical reviewer commitment")
    expected_header = CommitmentHeaderV1(
        schema_version="audit-commitment-v1",
        campaign_id=evidence.index.campaign_id,
        campaign_registry_sha256=(
            evidence.generation_context.index.campaign_registry_sha256
        ),
        reviewer_id=reviewer_id,
        audit_reviewer_registry_sha256=registry.audit_reviewer_registry_sha256,
        sample_manifest_sha256=sample.manifest.sample_manifest_sha256,
        audit_commit_reveal_protocol_sha256=(
            evidence.index.audit_commit_reveal_protocol_sha256
        ),
    )
    if commitment.header != expected_header:
        raise ValueError("canonical reviewer commitment authority mismatch")
    return record


def _tree_entries(
    oid: str,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    selected: set[str],
) -> dict[bytes, tuple[str, str]]:
    item = objects.get(oid)
    if item is None or item.object_type != "tree":
        raise ValueError("audit tree traversal references a missing/non-tree object")
    selected.add(oid)
    entries = _parse_tree_entries(item.raw_content)
    return {name: (mode, child_oid) for mode, name, child_oid in entries}


def _select_leaf(
    entry: tuple[str, str],
    *,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    selected: set[str],
) -> None:
    mode, oid = entry
    item = objects.get(oid)
    if mode != "100644" or item is None or item.object_type != "blob":
        raise ValueError("audit changed leaf must be one regular blob")
    selected.add(oid)


def _require_allowlisted_change(
    path: bytes,
    *,
    is_tree: bool,
    expected_paths: tuple[bytes, ...],
) -> None:
    allowed = (
        any(expected.startswith(path + b"/") for expected in expected_paths)
        if is_tree
        else path in expected_paths
    )
    if not allowed:
        raise ValueError("audit changed path is outside its exact allowlist")


def _expand_one_sided_tree(
    tree_oid: str,
    *,
    prefix: bytes,
    side: Literal["base", "head"],
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    selected: set[str],
    changed: dict[str, tuple[tuple[str, str] | None, tuple[str, str] | None]],
    expected_paths: tuple[bytes, ...],
    active: frozenset[str],
) -> None:
    frames: list[
        tuple[
            str,
            bytes,
            Iterator[tuple[bytes, tuple[str, str]]],
        ]
    ] = []
    active_oids = set(active)

    def descend(next_oid: str, next_prefix: bytes) -> None:
        if next_oid in active_oids:
            raise ValueError("audit Git tree cycle detected")
        entries = _tree_entries(next_oid, objects, selected)
        if not entries:
            raise ValueError("audit one-sided tree must not be empty")
        active_oids.add(next_oid)
        frames.append((next_oid, next_prefix, iter(entries.items())))

    descend(tree_oid, prefix)
    while frames:
        current_oid, current_prefix, entries = frames[-1]
        try:
            name, entry = next(entries)
        except StopIteration:
            frames.pop()
            active_oids.remove(current_oid)
            continue
        path = current_prefix + name
        if entry[0] == "40000":
            _require_allowlisted_change(
                path,
                is_tree=True,
                expected_paths=expected_paths,
            )
            descend(entry[1], path + b"/")
            continue
        _require_allowlisted_change(
            path,
            is_tree=False,
            expected_paths=expected_paths,
        )
        _select_leaf(entry, objects=objects, selected=selected)
        decoded = path.decode("utf-8", errors="strict")
        changed[decoded] = (entry, None) if side == "base" else (None, entry)


def _simultaneous_tree_diff(
    base_tree_oid: str | None,
    head_tree_oid: str | None,
    *,
    prefix: bytes,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    selected: set[str],
    changed: dict[str, tuple[tuple[str, str] | None, tuple[str, str] | None]],
    expected_paths: tuple[str, ...],
    active: frozenset[tuple[str | None, str | None]] = frozenset(),
) -> None:
    expected_path_bytes = tuple(path.encode("utf-8") for path in expected_paths)
    frames: list[
        tuple[
            _TreePair,
            bytes,
            Iterator[tuple[bytes, _TreeEntry | None, _TreeEntry | None]],
        ]
    ] = []
    active_pairs = set(active)

    def descend(
        next_base_oid: str | None,
        next_head_oid: str | None,
        next_prefix: bytes,
    ) -> None:
        pair: _TreePair = (next_base_oid, next_head_oid)
        if pair in active_pairs:
            raise ValueError("audit simultaneous tree diff contains a cycle")
        if next_base_oid == next_head_oid:
            if next_base_oid is not None:
                # Compared equal trees are deliberately opaque, but the compared tree itself is
                # part of the closure.
                item = objects.get(next_base_oid)
                if item is None or item.object_type != "tree":
                    raise ValueError("opaque equal audit subtree is missing")
                selected.add(next_base_oid)
            return
        if not any(path.startswith(next_prefix) for path in expected_path_bytes):
            raise ValueError("audit changed path is outside its exact allowlist")
        if next_base_oid is None:
            assert next_head_oid is not None
            _expand_one_sided_tree(
                next_head_oid,
                prefix=next_prefix,
                side="head",
                objects=objects,
                selected=selected,
                changed=changed,
                expected_paths=expected_path_bytes,
                active=frozenset(),
            )
            return
        if next_head_oid is None:
            _expand_one_sided_tree(
                next_base_oid,
                prefix=next_prefix,
                side="base",
                objects=objects,
                selected=selected,
                changed=changed,
                expected_paths=expected_path_bytes,
                active=frozenset(),
            )
            return
        base = _tree_entries(next_base_oid, objects, selected)
        head = _tree_entries(next_head_oid, objects, selected)
        ordered = (
            (name, base.get(name), head.get(name))
            for name in sorted(set(base) | set(head))
        )
        active_pairs.add(pair)
        frames.append((pair, next_prefix, iter(ordered)))

    descend(base_tree_oid, head_tree_oid, prefix)
    while frames:
        pair, current_prefix, entries = frames[-1]
        try:
            name, before, after = next(entries)
        except StopIteration:
            frames.pop()
            active_pairs.remove(pair)
            continue
        if before == after:
            if before is not None and before[0] == "40000":
                # Equal subtrees are opaque, but their common root is still one compared tree
                # object and therefore belongs to the deterministic closure.
                descend(
                    before[1],
                    before[1],
                    current_prefix + name + b"/",
                )
            continue
        path = current_prefix + name
        before_is_tree = before is not None and before[0] == "40000"
        after_is_tree = after is not None and after[0] == "40000"
        if before is not None:
            _require_allowlisted_change(
                path,
                is_tree=before_is_tree,
                expected_paths=expected_path_bytes,
            )
        if after is not None:
            _require_allowlisted_change(
                path,
                is_tree=after_is_tree,
                expected_paths=expected_path_bytes,
            )
        if before_is_tree and after_is_tree:
            descend(
                cast(tuple[str, str], before)[1],
                cast(tuple[str, str], after)[1],
                path + b"/",
            )
            continue
        if before_is_tree:
            _expand_one_sided_tree(
                cast(tuple[str, str], before)[1],
                prefix=path + b"/",
                side="base",
                objects=objects,
                selected=selected,
                changed=changed,
                expected_paths=expected_path_bytes,
                active=frozenset(),
            )
        elif before is not None:
            _select_leaf(before, objects=objects, selected=selected)
            changed[path.decode("utf-8", errors="strict")] = (before, None)
        if after_is_tree:
            _expand_one_sided_tree(
                cast(tuple[str, str], after)[1],
                prefix=path + b"/",
                side="head",
                objects=objects,
                selected=selected,
                changed=changed,
                expected_paths=expected_path_bytes,
                active=frozenset(),
            )
        elif after is not None:
            _select_leaf(after, objects=objects, selected=selected)
            decoded = path.decode("utf-8", errors="strict")
            old = changed.get(decoded)
            changed[decoded] = (None if old is None else old[0], after)


def _resolve_path(
    tree_oid: str,
    path: str,
    *,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    selected: set[str],
) -> tuple[str, str] | None:
    parts = path.encode("utf-8").split(b"/")
    current = tree_oid
    for ordinal, part in enumerate(parts):
        entries = _tree_entries(current, objects, selected)
        entry = entries.get(part)
        if entry is None:
            return None
        mode, oid = entry
        if ordinal + 1 == len(parts):
            if mode == "40000":
                item = objects.get(oid)
                if item is None or item.object_type != "tree":
                    raise ValueError("audit path directory references a non-tree")
                selected.add(oid)
            else:
                _select_leaf(entry, objects=objects, selected=selected)
            return entry
        if mode != "40000":
            raise ValueError("audit path has a non-directory prefix")
        current = oid
    raise AssertionError("unreachable")


def _subtree_oid(
    tree_oid: str,
    path: str,
    *,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
    selected: set[str],
) -> str | None:
    entry = _resolve_path(tree_oid, path, objects=objects, selected=selected)
    if entry is None:
        return None
    if entry[0] != "40000":
        raise ValueError("campaign audit subtree path resolves to a non-tree")
    return entry[1]


def _expected_paths(
    kind: AuditPullRequestKindV1, campaign_id: str, reviewer_id: str | None
) -> tuple[str, ...]:
    root = f"benchmarks/audits/{campaign_id}"
    if kind == "commitment":
        assert reviewer_id is not None
        return (f"{root}/commitments/{reviewer_id}.json",)
    if kind == "reveal":
        assert reviewer_id is not None
        return (
            f"{root}/reveals/{reviewer_id}/labels.jsonl",
            f"{root}/reveals/{reviewer_id}/reveal.json",
        )
    return (f"{root}/adjudication-core.json",)


def _expected_blob_bytes(
    *,
    kind: AuditPullRequestKindV1,
    reviewer_id: str | None,
    path: str,
    chains_by_id: Mapping[str, ReviewerChainV1],
    adjudication: AuditAdjudicationV1 | None,
) -> bytes:
    if kind == "commitment":
        assert reviewer_id is not None
        return canonical_json_v1(
            chains_by_id[reviewer_id].commitment.model_dump(mode="json")
        ) + b"\n"
    if kind == "reveal":
        assert reviewer_id is not None
        reveal = chains_by_id[reviewer_id].reveal
        if path.endswith("/labels.jsonl"):
            return canonical_label_jsonl(reveal.labels)
        return canonical_json_v1(reveal.model_dump(mode="json")) + b"\n"
    if adjudication is None:
        raise ValueError("adjudication blob verification requires the final envelope")
    return canonical_json_v1(adjudication.core.model_dump(mode="json")) + b"\n"


def _first_parent_chain(
    proofs: Sequence[PullRequestProofV1],
    *,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> tuple[ParsedProtocolGitObjectV1, ...]:
    commitment_merges = {
        proof.merge_commit_sha for proof in proofs if proof.proof_kind == "commitment"
    }
    if len(commitment_merges) != 2:
        raise ValueError("audit topology requires two commitment merges")
    current_oid = proofs[-1].merge_commit_sha
    reverse: list[ParsedProtocolGitObjectV1] = []
    visited: set[str] = set()
    seen_commitments: set[str] = set()
    while True:
        if current_oid in visited or len(visited) >= 4_096:
            raise ValueError("audit main first-parent chain contains a cycle or is oversized")
        current = objects.get(current_oid)
        if current is None or current.object_type != "commit":
            raise ValueError("audit main first-parent chain has a gap")
        visited.add(current_oid)
        reverse.append(current)
        if current_oid in commitment_merges:
            seen_commitments.add(current_oid)
            if seen_commitments == commitment_merges:
                view = _parse_commit_view(current)
                if not view.parent_oids:
                    raise ValueError("earliest commitment merge has no base parent")
                base_oid = view.parent_oids[0]
                if base_oid in visited:
                    raise ValueError("audit main first-parent chain repeats its base")
                base = objects.get(base_oid)
                if base is None or base.object_type != "commit":
                    raise ValueError("earliest commitment merge base is missing")
                reverse.append(base)
                break
        view = _parse_commit_view(current)
        if not view.parent_oids:
            raise ValueError("audit main first-parent chain ended before both commitments")
        current_oid = view.parent_oids[0]
    chain = tuple(reversed(reverse))
    for parent, child in pairwise(chain):
        if _parse_commit_view(child).parent_oids[0] != parent.oid:
            raise ValueError("audit main first-parent chain contains a gap or fork")
    return chain


def _verify_topology_and_closure(
    *,
    chains: tuple[ReviewerChainV1, ReviewerChainV1],
    adjudication: AuditAdjudicationV1,
    proofs: tuple[PullRequestProofV1, ...],
    archive: AuditGitObjectArchiveV1,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> None:
    if len(proofs) != 5:
        raise ValueError("audit topology requires exactly five pull requests")
    reviewer_ids = tuple(chain.identity.reviewer_id for chain in chains)
    expected_kinds = ("commitment", "commitment", "reveal", "reveal", "adjudication")
    expected_reviewers: tuple[str | None, ...] = (
        reviewer_ids[0],
        reviewer_ids[1],
        reviewer_ids[0],
        reviewer_ids[1],
        None,
    )
    if tuple(proof.proof_kind for proof in proofs) != expected_kinds or tuple(
        proof.reviewer_id for proof in proofs
    ) != expected_reviewers:
        raise ValueError("audit pull-request proof tuple order mismatch")
    if len({proof.pr_number for proof in proofs}) != 5:
        raise ValueError("audit pull-request numbers must be unique")
    commit_oids = tuple(
        oid for proof in proofs for oid in (proof.head_sha, proof.merge_commit_sha)
    )
    if len(set(commit_oids)) != 10:
        raise ValueError("audit head and merge commit OIDs must be pairwise distinct")
    selected: set[str] = set()
    for proof in proofs:
        head = objects.get(proof.head_sha)
        merge = objects.get(proof.merge_commit_sha)
        if (
            head is None
            or merge is None
            or head.object_type != "commit"
            or merge.object_type != "commit"
        ):
            raise ValueError("audit proof references a missing head or merge")
        selected.update((head.oid, merge.oid))
        head_view = _parse_commit_view(head)
        merge_view = _parse_commit_view(merge)
        if head_view.parent_oids != (proof.base_sha,) or head_view.signature is None:
            raise ValueError("audit PR head must be signed and have exactly its base parent")
        if merge_view.parent_oids != (proof.base_sha, proof.head_sha):
            raise ValueError("audit PR merge requires exact base/head parent order")
        if merge_view.tree_oid != head_view.tree_oid:
            raise ValueError("audit merge tree differs from its signed head tree")

    main_chain = _first_parent_chain(proofs, objects=objects)
    selected.update(item.oid for item in main_chain)
    positions = {item.oid: ordinal for ordinal, item in enumerate(main_chain)}
    if any(proof.merge_commit_sha not in positions for proof in proofs):
        raise ValueError("audit merge is absent from the main first-parent chain")
    actual_order = tuple(
        proof.proof_kind
        for proof in sorted(proofs, key=lambda item: positions[item.merge_commit_sha])
    )
    if actual_order != expected_kinds:
        raise ValueError("audit main chain group order is not commitments/reveals/adjudication")
    ordered_proofs = sorted(proofs, key=lambda item: positions[item.merge_commit_sha])
    ordered_times = tuple(
        datetime.strptime(item.merged_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        for item in ordered_proofs
    )
    if ordered_times != tuple(sorted(set(ordered_times))):
        raise ValueError("audit pull-request merge timestamps must strictly increase")

    chains_by_id = {chain.identity.reviewer_id: chain for chain in chains}
    governed: dict[str, tuple[int, str]] = {}
    proof_by_merge = {proof.merge_commit_sha: proof for proof in proofs}
    campaign_root = f"benchmarks/audits/{adjudication.core.campaign_id}"
    for proof in proofs:
        base = objects[proof.base_sha]
        head = objects[proof.head_sha]
        if base.object_type != "commit":
            raise ValueError("audit PR base is not a commit")
        before_tree = _parse_commit_view(base).tree_oid
        after_tree = _parse_commit_view(head).tree_oid
        expected_paths = _expected_paths(
            proof.proof_kind, proof.campaign_id, proof.reviewer_id
        )
        changed: dict[str, tuple[tuple[str, str] | None, tuple[str, str] | None]] = {}
        _simultaneous_tree_diff(
            before_tree,
            after_tree,
            prefix=b"",
            objects=objects,
            selected=selected,
            changed=changed,
            expected_paths=expected_paths,
        )
        if tuple(changed) != expected_paths or proof.changed_paths != expected_paths:
            raise ValueError("audit PR changed paths differ from the exact allowlist")
        for path in expected_paths:
            before_entry, after_entry = changed[path]
            if (
                before_entry is not None
                or after_entry is None
                or after_entry[0] != "100644"
            ):
                raise ValueError("audit governed path must be an added regular blob")
            blob = objects.get(after_entry[1])
            expected_bytes = _expected_blob_bytes(
                kind=proof.proof_kind,
                reviewer_id=proof.reviewer_id,
                path=path,
                chains_by_id=chains_by_id,
                adjudication=adjudication,
            )
            if blob is None or blob.object_type != "blob" or blob.raw_content != expected_bytes:
                raise ValueError("audit governed blob bytes are not exact")
            governed[path] = (positions[proof.merge_commit_sha], after_entry[1])

    # Every adjacent main state exposes the campaign subtree transition.  Intervening commits may
    # alter only material outside that subtree.
    for before_commit, after_commit in pairwise(main_chain):
        before_tree = _parse_commit_view(before_commit).tree_oid
        after_tree = _parse_commit_view(after_commit).tree_oid
        before_subtree = _subtree_oid(
            before_tree, campaign_root, objects=objects, selected=selected
        )
        after_subtree = _subtree_oid(
            after_tree, campaign_root, objects=objects, selected=selected
        )
        transition_proof = proof_by_merge.get(after_commit.oid)
        if transition_proof is None and before_subtree != after_subtree:
            raise ValueError("intervening main commit changed the campaign audit subtree")
        transition_expected = (
            ()
            if transition_proof is None
            else _expected_paths(
                transition_proof.proof_kind,
                transition_proof.campaign_id,
                transition_proof.reviewer_id,
            )
        )
        transition_changes: dict[
            str, tuple[tuple[str, str] | None, tuple[str, str] | None]
        ] = {}
        _simultaneous_tree_diff(
            before_subtree,
            after_subtree,
            prefix=(campaign_root + "/").encode("utf-8"),
            objects=objects,
            selected=selected,
            changed=transition_changes,
            expected_paths=transition_expected,
        )
        if transition_proof is None:
            if transition_changes:
                raise ValueError("intervening audit-subtree transition is not opaque-equal")
        elif tuple(transition_changes) != transition_expected:
            raise ValueError("main audit-subtree transition differs from the PR allowlist")

    # Every governed blob remains byte-identical in all later first-parent states and was absent
    # before the merge that introduced it.
    for path, (introduced, oid) in governed.items():
        for ordinal, commit in enumerate(main_chain):
            entry = _resolve_path(
                _parse_commit_view(commit).tree_oid,
                path,
                objects=objects,
                selected=selected,
            )
            if ordinal < introduced:
                if entry is not None:
                    raise ValueError("governed audit path existed before its authorized addition")
            elif entry != ("100644", oid):
                raise ValueError("governed audit blob changed after introduction")

    if set(objects) != selected:
        raise ValueError("audit Git archive contains a missing or extra closure object")
    closure_payload = [
        {
            "oid": objects[oid].oid,
            "type": objects[oid].object_type,
            "size": objects[oid].size,
            "git_object_sha256": objects[oid].git_object_sha256,
        }
        for oid in sorted(selected)
    ]
    if archive.object_closure_root != stable_digest(
        "laconian-audit-git-object-closure-v1", closure_payload
    ):
        raise ValueError("audit Git archive closure root differs from exact traversal")


def _first_parent_contains(
    ancestor_oid: str,
    descendant_oid: str,
    *,
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> bool:
    current = descendant_oid
    visited: set[str] = set()
    while current not in visited and len(visited) < 4_096:
        if current == ancestor_oid:
            return True
        visited.add(current)
        item = objects.get(current)
        if item is None or item.object_type != "commit":
            return False
        parents = _parse_commit_view(item).parent_oids
        if not parents:
            return False
        current = parents[0]
    return False


def _validate_labels_against_sample(
    labels: tuple[HumanAuditLabelV1, ...], sample: VerifiedAuditSampleRootV1
) -> None:
    packet = sample.packet
    packet_ids = tuple(item.audit_record_id for item in packet.records)
    label_ids = tuple(item.audit_record_id for item in labels)
    if label_ids != packet_ids:
        raise ValueError("reviewer labels do not cover the blind packet exactly once")
    for label, record in zip(labels, packet.records, strict=True):
        if tuple(item.item_index for item in label.rubric_items) != tuple(
            item.item_index for item in record.rubric
        ):
            raise ValueError("reviewer label rubric indices differ from the blind packet")
        if (label.material_warning is None) != (record.material_warning_requirement is None):
            raise ValueError("reviewer warning judgment does not match the blind packet")
        expected = derive_semantic_pass(
            rubric_items=label.rubric_items,
            material_warning_requirement=record.material_warning_requirement,
            material_warning=label.material_warning,
            material_contradiction=label.material_contradiction,
        )
        if label.semantic_pass != expected:
            raise ValueError("reviewer label semantic pass differs from the frozen judge rule")


def _validate_chain_authority(
    chain: ReviewerChainV1,
    *,
    reviewer: object,
    evidence: VerifiedBenchmarkProviderEvidenceV1,
    sample: VerifiedAuditSampleRootV1,
    registry: AuditReviewerRegistryV1,
) -> None:
    # reviewer is intentionally received only from the exact registry tuple; avoid defining a
    # second binding owner in this module.
    expected = cast(Any, reviewer)
    identity = chain.identity
    if (
        identity.reviewer_id != expected.reviewer_id
        or identity.reviewer_numeric_account_id != expected.reviewer_numeric_account_id
        or identity.reviewer_login != expected.reviewer_login
        or identity.verification_mode != expected.verification_mode
        or identity.signing_fingerprint != expected.signing_fingerprint
        or identity.audit_reviewer_registry_sha256
        != registry.audit_reviewer_registry_sha256
    ):
        raise ValueError("reviewer chain identity differs from the provider registry")
    header = chain.commitment.header
    reveal = chain.reveal
    authority = (
        evidence.index.campaign_id,
        evidence.generation_context.index.campaign_registry_sha256,
        registry.audit_reviewer_registry_sha256,
        sample.manifest.sample_manifest_sha256,
        evidence.index.audit_commit_reveal_protocol_sha256,
    )
    if (
        (
            header.campaign_id,
            header.campaign_registry_sha256,
            header.audit_reviewer_registry_sha256,
            header.sample_manifest_sha256,
            header.audit_commit_reveal_protocol_sha256,
        )
        != authority
        or (
            reveal.campaign_id,
            reveal.campaign_registry_sha256,
            reveal.audit_reviewer_registry_sha256,
            reveal.sample_manifest_sha256,
            reveal.audit_commit_reveal_protocol_sha256,
        )
        != authority
        or header.reviewer_id != identity.reviewer_id
        or reveal.reviewer_id != identity.reviewer_id
        or reveal.commitment_sha256 != chain.commitment.commitment_sha256
    ):
        raise ValueError("reviewer commitment/reveal authority mismatch")
    _validate_labels_against_sample(reveal.labels, sample)
    exact_labels = canonical_label_jsonl(reveal.labels)
    expected_commitment = compute_commitment(
        header=header,
        salt=bytes.fromhex(reveal.salt_hex),
        exact_label_bytes=exact_labels,
    )
    if chain.commitment.commitment_sha256 != expected_commitment:
        raise ValueError("reviewer reveal does not open its commitment")


def _validate_one_chain_deltas_and_ancestry(
    chain: ReviewerChainV1,
    *,
    commitment_merge_oids: tuple[str, str],
    objects: Mapping[str, ParsedProtocolGitObjectV1],
) -> None:
    reviewer_id = chain.identity.reviewer_id
    for proof, kind in (
        (chain.commitment_pr, "commitment"),
        (chain.reveal_pr, "reveal"),
    ):
        if proof.proof_kind != kind or proof.reviewer_id != reviewer_id:
            raise ValueError("reviewer chain PR proof kind/reviewer mismatch")
        base = objects.get(proof.base_sha)
        head = objects.get(proof.head_sha)
        merge = objects.get(proof.merge_commit_sha)
        if any(item is None or item.object_type != "commit" for item in (base, head, merge)):
            raise ValueError("reviewer chain references a missing Git commit")
        assert base is not None and head is not None and merge is not None
        head_view = _parse_commit_view(head)
        merge_view = _parse_commit_view(merge)
        if (
            head_view.parent_oids != (proof.base_sha,)
            or head_view.signature is None
            or merge_view.parent_oids != (proof.base_sha, proof.head_sha)
            or merge_view.tree_oid != head_view.tree_oid
        ):
            raise ValueError("reviewer chain head/merge topology mismatch")
        expected_paths = _expected_paths(kind, proof.campaign_id, reviewer_id)
        selected: set[str] = set()
        changed: dict[str, tuple[tuple[str, str] | None, tuple[str, str] | None]] = {}
        _simultaneous_tree_diff(
            _parse_commit_view(base).tree_oid,
            head_view.tree_oid,
            prefix=b"",
            objects=objects,
            selected=selected,
            changed=changed,
            expected_paths=expected_paths,
        )
        if tuple(changed) != expected_paths or proof.changed_paths != expected_paths:
            raise ValueError("reviewer chain PR delta differs from its exact allowlist")
        for path in expected_paths:
            before_entry, after_entry = changed[path]
            if (
                before_entry is not None
                or after_entry is None
                or after_entry[0] != "100644"
            ):
                raise ValueError("reviewer chain governed path is not one new regular blob")
            expected_bytes = _expected_blob_bytes(
                kind=kind,
                reviewer_id=reviewer_id,
                path=path,
                chains_by_id={reviewer_id: chain},
                adjudication=None,
            )
            blob = objects.get(after_entry[1])
            if blob is None or blob.object_type != "blob" or blob.raw_content != expected_bytes:
                raise ValueError("reviewer chain governed blob bytes differ")
    for commitment_merge in commitment_merge_oids:
        if not _first_parent_contains(
            commitment_merge, chain.reveal_pr.head_sha, objects=objects
        ) or not _first_parent_contains(
            commitment_merge, chain.reveal_pr.merge_commit_sha, objects=objects
        ):
            raise ValueError("reviewer reveal does not descend from both commitment merges")
    # The commitment's exact blob must still be present in the reveal state.
    commitment_path = _expected_paths("commitment", chain.commitment_pr.campaign_id, reviewer_id)[0]
    initial_selected: set[str] = set()
    original = _resolve_path(
        _parse_commit_view(objects[chain.commitment_pr.merge_commit_sha]).tree_oid,
        commitment_path,
        objects=objects,
        selected=initial_selected,
    )
    later = _resolve_path(
        _parse_commit_view(objects[chain.reveal_pr.merge_commit_sha]).tree_oid,
        commitment_path,
        objects=objects,
        selected=initial_selected,
    )
    if original is None or original != later:
        raise ValueError("reviewer commitment blob changed before/at reveal")


def _verify_chain_checked(
    chain: ReviewerChainV1,
    *,
    sample: VerifiedAuditSampleRootV1,
    evidence: VerifiedBenchmarkProviderEvidenceV1,
    registry: AuditReviewerRegistryV1,
    archive: AuditGitObjectArchiveV1,
    commitment_sources: tuple[
        AuditPullRequestEvidenceSourceV1, AuditPullRequestEvidenceSourceV1
    ],
    reveal_source: AuditPullRequestEvidenceSourceV1,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
) -> None:
    chain = _revalidate_model(chain, ReviewerChainV1)
    reviewer_ids = tuple(item.reviewer_id for item in registry.reviewers)
    if chain.identity.reviewer_id not in reviewer_ids:
        raise ValueError("reviewer chain is not owned by a registered reviewer")
    reviewer = registry.reviewers[reviewer_ids.index(chain.identity.reviewer_id)]
    _validate_chain_authority(
        chain,
        reviewer=reviewer,
        evidence=evidence,
        sample=sample,
        registry=registry,
    )
    if type(commitment_sources) is not tuple or len(commitment_sources) != 2:
        raise TypeError("reviewer verification requires an exact commitment-source pair")
    if tuple(source.reviewer_id for source in commitment_sources) != reviewer_ids:
        raise ValueError("commitment sources require provider reviewer-ID order")
    objects = _archive_objects(archive)
    commitment_records = cast(
        tuple[ExactGitHubPullRequestRecordV1, ExactGitHubPullRequestRecordV1],
        tuple(
            _record_from_source(
                source,
                expected_kind="commitment",
                expected_reviewer_id=expected_id,
                campaign_id=evidence.index.campaign_id,
                repository_id=repository_id,
                repository_owner=repository_owner,
                repository_name=repository_name,
            )
            for source, expected_id in zip(commitment_sources, reviewer_ids, strict=True)
        ),
    )
    source_index = reviewer_ids.index(chain.identity.reviewer_id)
    other_index = 1 - source_index
    _verify_unselected_commitment_source(
        source=commitment_sources[other_index],
        reviewer_id=reviewer_ids[other_index],
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        registry=registry,
        evidence=evidence,
        sample=sample,
        objects=objects,
    )
    _verify_pull_request_source(
        source=commitment_sources[source_index],
        proof=chain.commitment_pr,
        expected_kind="commitment",
        expected_reviewer_id=chain.identity.reviewer_id,
        expected_primary_path=_expected_paths(
            "commitment", evidence.index.campaign_id, chain.identity.reviewer_id
        )[0],
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        registry=registry,
        evidence=evidence,
        objects=objects,
    )
    _verify_pull_request_source(
        source=reveal_source,
        proof=chain.reveal_pr,
        expected_kind="reveal",
        expected_reviewer_id=chain.identity.reviewer_id,
        expected_primary_path=_expected_paths(
            "reveal", evidence.index.campaign_id, chain.identity.reviewer_id
        )[1],
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        registry=registry,
        evidence=evidence,
        objects=objects,
    )
    _validate_one_chain_deltas_and_ancestry(
        chain,
        commitment_merge_oids=cast(
            tuple[str, str], tuple(item.merge_commit_sha for item in commitment_records)
        ),
        objects=objects,
    )


def verify_reviewer_chain(
    chain: ReviewerChainV1,
    *,
    sample: VerifiedAuditSampleRootV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    audit_git_object_archive: AuditGitObjectArchiveV1,
    commitment_sources: tuple[
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
    ],
    reveal_source: AuditPullRequestEvidenceSourceV1,
) -> None:
    """Verify one reviewer chain from the complete sample, provider, API, and Git sources."""

    evidence = _revalidate_verified_provider_evidence_v1(provider_evidence)
    # This owner-only walk grants no authority; it prevents hostile model subclasses from
    # surviving until the expensive sample replay.  Provider ownership remains the first
    # verified boundary above.
    _preflight_model_owner(chain, ReviewerChainV1)
    _preflight_model_owner(audit_git_object_archive, AuditGitObjectArchiveV1)
    _preflight_model_tuple(
        commitment_sources,
        AuditPullRequestEvidenceSourceV1,
        length=2,
        error_message="reviewer verification requires an exact commitment-source pair",
    )
    _preflight_model_owner(reveal_source, AuditPullRequestEvidenceSourceV1)
    registry = _audit_registry(evidence)
    checked_sample = _checked_sample(evidence, sample)
    repository_id, repository_owner, repository_name = _repository_authority(evidence)
    archive = _revalidate_model(audit_git_object_archive, AuditGitObjectArchiveV1)
    _verify_chain_checked(
        chain,
        sample=checked_sample,
        evidence=evidence,
        registry=registry,
        archive=archive,
        commitment_sources=commitment_sources,
        reveal_source=reveal_source,
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
    )


_REVIEW_ENDPOINT_RE_TEMPLATE = (
    r"^GET /repos/{owner}/{name}/pulls/(?P<pr>[1-9][0-9]*)/reviews/"
    r"(?P<review>[1-9][0-9]*)$"
)


def _review_record_from_source(
    source: ExactGitHubReviewSourceV1,
    *,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
) -> ExactGitHubReviewRecordV1:
    source = _revalidate_model(source, ExactGitHubReviewSourceV1)
    raw = _decode_base64(source.raw_response_base64)
    receipt = source.observation_receipt
    pattern = re.compile(
        _REVIEW_ENDPOINT_RE_TEMPLATE.format(
            owner=re.escape(repository_owner), name=re.escape(repository_name)
        ),
        re.ASCII,
    )
    match = pattern.fullmatch(receipt.endpoint)
    if (
        receipt.source_kind != "review"
        or receipt.repository_id != repository_id
        or receipt.raw_response_byte_length != len(raw)
        or receipt.raw_response_sha256 != hashlib.sha256(raw).hexdigest()
        or match is None
    ):
        raise ValueError("GitHub review observation receipt/source mismatch")
    assert match is not None
    endpoint_pr = int(match.group("pr"))
    endpoint_review = int(match.group("review"))
    response = _parse_provider_json(raw)
    user = _selected_object(_required_json_member(response, "user", "review"), "user")
    raw_review_id = _selected_positive_int(
        _required_json_member(response, "id", "review"), "id"
    )
    if raw_review_id != endpoint_review:
        raise ValueError("raw GitHub review ID differs from its endpoint")
    payload: dict[str, object] = {
        "schema_version": "audit-github-review-record-v1",
        "repository_id": repository_id,
        "pr_number": endpoint_pr,
        "review_id": raw_review_id,
        "actor_account_id": _selected_positive_int(
            _required_json_member(user, "id", "user"), "user.id"
        ),
        "actor_login": _selected_string(
            _required_json_member(user, "login", "user"), "user.login"
        ),
        "reviewed_head_sha": _selected_string(
            _required_json_member(response, "commit_id", "review"), "commit_id"
        ),
        "body": _selected_string(_required_json_member(response, "body", "review"), "body"),
        "state": _selected_string(
            _required_json_member(response, "state", "review"), "state"
        ),
        "submitted_at_utc": _whole_second(
            _required_json_member(response, "submitted_at", "review"), "submitted_at"
        ),
    }
    payload["exact_api_record_sha256"] = stable_digest(
        "laconian-audit-github-review-record-v1", payload
    )
    fresh = ExactGitHubReviewRecordV1.model_validate(payload)
    if canonical_json_v1(fresh.model_dump(mode="json")) != canonical_json_v1(
        source.record.model_dump(mode="json")
    ):
        raise ValueError("raw GitHub review does not reconstruct its retained record")
    return fresh


def _verify_signoff_source(
    *,
    source: ExactGitHubReviewSourceV1,
    signoff: ExactGitHubReviewSignoffV1,
    reviewer: object,
    core: AuditAdjudicationCoreV1,
    adjudication_pr: PullRequestProofV1,
    registry: AuditReviewerRegistryV1,
    repository_id: int,
    repository_owner: str,
    repository_name: str,
    reveal_merge_times: tuple[datetime, datetime],
) -> None:
    source = _revalidate_model(source, ExactGitHubReviewSourceV1)
    signoff = _revalidate_model(signoff, ExactGitHubReviewSignoffV1)
    expected = cast(Any, reviewer)
    if source.reviewer_id != expected.reviewer_id or signoff.reviewer_id != expected.reviewer_id:
        raise ValueError("GitHub review source/signoff reviewer ID mismatch")
    record = _review_record_from_source(
        source,
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
    )
    expected_body = (
        b"laconian-audit-adjudication-core-v1\0"
        + core.adjudication_core_sha256.encode("ascii")
        + b"\n"
    )
    try:
        body_bytes = record.body.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ValueError("GitHub review body is not strict UTF-8") from None
    submitted = datetime.strptime(record.submitted_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    merged = datetime.strptime(adjudication_pr.merged_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    if (
        body_bytes != expected_body
        or record.repository_id != repository_id
        or record.pr_number != adjudication_pr.pr_number
        or record.actor_account_id != expected.reviewer_numeric_account_id
        or record.actor_login != expected.reviewer_login
        or record.state != "APPROVED"
        or record.reviewed_head_sha != adjudication_pr.head_sha
        or not all(reveal_time < submitted for reveal_time in reveal_merge_times)
        or not submitted < merged
    ):
        raise ValueError("GitHub review source is stale, wrong-head, wrong-body, or unauthorized")
    expected_payload: dict[str, object] = {
        "schema_version": "audit-adjudication-github-review-v1",
        "reviewer_id": expected.reviewer_id,
        "reviewer_numeric_account_id": expected.reviewer_numeric_account_id,
        "reviewer_login": expected.reviewer_login,
        "audit_reviewer_registry_sha256": registry.audit_reviewer_registry_sha256,
        "adjudication_core_sha256": core.adjudication_core_sha256,
        "repository_id": repository_id,
        "pr_number": record.pr_number,
        "review_id": record.review_id,
        "state": "APPROVED",
        "reviewed_head_sha": record.reviewed_head_sha,
        "submitted_at_utc": record.submitted_at_utc,
        "fixed_body_sha256": hashlib.sha256(body_bytes).hexdigest(),
        "exact_api_record_sha256": record.exact_api_record_sha256,
        "github_review_source_sha256": source.github_review_source_sha256,
    }
    expected_payload["signoff_proof_sha256"] = stable_digest(
        "laconian-audit-adjudication-github-review-v1", expected_payload
    )
    fresh = ExactGitHubReviewSignoffV1.model_validate(expected_payload)
    if canonical_json_v1(fresh.model_dump(mode="json")) != canonical_json_v1(
        signoff.model_dump(mode="json")
    ):
        raise ValueError("GitHub signoff differs from its exact review source")


def _verify_consensus(
    *,
    chains: tuple[ReviewerChainV1, ReviewerChainV1],
    core: AuditAdjudicationCoreV1,
    sample: VerifiedAuditSampleRootV1,
) -> None:
    expected_ids = tuple(item.audit_record_id for item in sample.packet.records)
    if tuple(item.audit_record_id for item in core.consensus) != expected_ids:
        raise ValueError("adjudication consensus does not cover the blind packet exactly once")
    left = {item.audit_record_id: item for item in chains[0].reveal.labels}
    right = {item.audit_record_id: item for item in chains[1].reveal.labels}
    for row in core.consensus:
        left_value = left[row.audit_record_id].semantic_pass
        right_value = right[row.audit_record_id].semantic_pass
        if left_value == right_value:
            if (
                row.resolution != "reviewer-agreement"
                or row.semantic_pass != left_value
                or row.rationale is not None
            ):
                raise ValueError("agreement consensus differs from both reviewer reveals")
        elif row.resolution not in {"adjudicated", "unresolved"}:
            raise ValueError("reviewer disagreement lacks adjudication or unresolved resolution")


def verify_audit_chain(
    *,
    chains: tuple[ReviewerChainV1, ReviewerChainV1],
    adjudication: AuditAdjudicationV1,
    sample: VerifiedAuditSampleRootV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    audit_git_object_archive: AuditGitObjectArchiveV1,
    pull_request_sources: tuple[
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
        AuditPullRequestEvidenceSourceV1,
    ],
    github_review_sources: tuple[
        ExactGitHubReviewSourceV1,
        ExactGitHubReviewSourceV1,
    ],
) -> None:
    """Verify the complete two-person audit, immutable Git graph, reviews, and envelope."""

    evidence = _revalidate_verified_provider_evidence_v1(provider_evidence)
    # Reject Python owner substitutions without dumping or normalizing them before the
    # intentionally expensive sample/source replay.  Provider ownership remains first.
    _preflight_model_tuple(
        chains,
        ReviewerChainV1,
        length=2,
        error_message="audit verification requires an exact reviewer-chain pair",
    )
    _preflight_model_owner(adjudication, AuditAdjudicationV1)
    _preflight_model_owner(audit_git_object_archive, AuditGitObjectArchiveV1)
    _preflight_model_tuple(
        pull_request_sources,
        AuditPullRequestEvidenceSourceV1,
        length=5,
        error_message="audit verification requires an exact five-source PR tuple",
    )
    _preflight_model_tuple(
        github_review_sources,
        ExactGitHubReviewSourceV1,
        length=2,
        error_message="audit verification requires an exact two-source review tuple",
    )
    registry = _audit_registry(evidence)
    checked_sample = _checked_sample(evidence, sample)
    repository_id, repository_owner, repository_name = _repository_authority(evidence)
    archive = _revalidate_model(audit_git_object_archive, AuditGitObjectArchiveV1)
    adjudication = _revalidate_model(adjudication, AuditAdjudicationV1)
    if type(chains) is not tuple or len(chains) != 2:
        raise TypeError("audit verification requires an exact reviewer-chain pair")
    checked_chains = cast(
        tuple[ReviewerChainV1, ReviewerChainV1],
        tuple(_revalidate_model(item, ReviewerChainV1) for item in chains),
    )
    reviewer_ids = tuple(item.reviewer_id for item in registry.reviewers)
    if tuple(item.identity.reviewer_id for item in checked_chains) != reviewer_ids:
        raise ValueError("reviewer chains require provider reviewer-ID byte order")
    if type(pull_request_sources) is not tuple or len(pull_request_sources) != 5:
        raise TypeError("audit verification requires an exact five-source PR tuple")
    if type(github_review_sources) is not tuple or len(github_review_sources) != 2:
        raise TypeError("audit verification requires an exact two-source review tuple")
    source_shape = tuple((item.proof_kind, item.reviewer_id) for item in pull_request_sources)
    if source_shape != (
        ("commitment", reviewer_ids[0]),
        ("commitment", reviewer_ids[1]),
        ("reveal", reviewer_ids[0]),
        ("reveal", reviewer_ids[1]),
        ("adjudication", None),
    ):
        raise ValueError("pull-request sources require commitment/reveal provider order")
    if tuple(item.reviewer_id for item in github_review_sources) != reviewer_ids:
        raise ValueError("GitHub review sources require reviewer-ID byte order")

    for ordinal, chain in enumerate(checked_chains):
        _verify_chain_checked(
            chain,
            sample=checked_sample,
            evidence=evidence,
            registry=registry,
            archive=archive,
            commitment_sources=pull_request_sources[:2],
            reveal_source=pull_request_sources[2 + ordinal],
            repository_id=repository_id,
            repository_owner=repository_owner,
            repository_name=repository_name,
        )

    core = adjudication.core
    expected_authority = (
        evidence.index.campaign_id,
        evidence.generation_context.index.campaign_registry_sha256,
        registry.audit_reviewer_registry_sha256,
        checked_sample.manifest.sample_manifest_sha256,
        evidence.index.audit_commit_reveal_protocol_sha256,
        evidence.index.audit_adjudication_protocol_sha256,
    )
    if (
        (
            core.campaign_id,
            core.campaign_registry_sha256,
            core.audit_reviewer_registry_sha256,
            core.sample_manifest_sha256,
            core.audit_commit_reveal_protocol_sha256,
            core.audit_adjudication_protocol_sha256,
        )
        != expected_authority
        or core.reveal_sha256s
        != tuple(chain.reveal.reveal_sha256 for chain in checked_chains)
    ):
        raise ValueError("adjudication core authority or reveal binding mismatch")
    _verify_consensus(chains=checked_chains, core=core, sample=checked_sample)

    objects = _archive_objects(archive)
    proofs: tuple[PullRequestProofV1, ...] = (
        checked_chains[0].commitment_pr,
        checked_chains[1].commitment_pr,
        checked_chains[0].reveal_pr,
        checked_chains[1].reveal_pr,
        adjudication.adjudication_pr,
    )
    expected_paths = _expected_paths("adjudication", evidence.index.campaign_id, None)
    _verify_pull_request_source(
        source=pull_request_sources[4],
        proof=adjudication.adjudication_pr,
        expected_kind="adjudication",
        expected_reviewer_id=None,
        expected_primary_path=expected_paths[0],
        repository_id=repository_id,
        repository_owner=repository_owner,
        repository_name=repository_name,
        registry=registry,
        evidence=evidence,
        objects=objects,
    )
    _verify_topology_and_closure(
        chains=checked_chains,
        adjudication=adjudication,
        proofs=proofs,
        archive=archive,
        objects=objects,
    )

    reveal_merge_times = cast(
        tuple[datetime, datetime],
        tuple(
            datetime.strptime(chain.reveal_pr.merged_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
            for chain in checked_chains
        ),
    )
    review_ids: list[int] = []
    for source, signoff, reviewer in zip(
        github_review_sources, adjudication.signoffs, registry.reviewers, strict=True
    ):
        _verify_signoff_source(
            source=source,
            signoff=signoff,
            reviewer=reviewer,
            core=core,
            adjudication_pr=adjudication.adjudication_pr,
            registry=registry,
            repository_id=repository_id,
            repository_owner=repository_owner,
            repository_name=repository_name,
            reveal_merge_times=reveal_merge_times,
        )
        review_ids.append(signoff.review_id)
    if len(set(review_ids)) != 2:
        raise ValueError("adjudication requires two distinct GitHub review IDs")

    expected_envelope = stable_digest(
        "laconian-audit-adjudication-v1",
        adjudication.model_dump(mode="json", exclude={"adjudication_sha256"}),
    )
    if adjudication.adjudication_sha256 != expected_envelope:
        raise ValueError("final adjudication envelope digest mismatch")


__all__ = (
    "AuditAdjudicationCoreV1",
    "AuditAdjudicationV1",
    "AuditGitObjectArchiveV1",
    "AuditPullRequestEvidenceSourceV1",
    "AuditPullRequestKindV1",
    "CommitmentHeaderV1",
    "ConsensusLabelV1",
    "ExactGitHubPullRequestRecordV1",
    "ExactGitHubReviewRecordV1",
    "ExactGitHubReviewSignoffV1",
    "ExactGitHubReviewSourceV1",
    "GitHubAuditApiObservationReceiptV1",
    "HumanAuditLabelV1",
    "PullRequestProofV1",
    "ReviewerChainV1",
    "ReviewerCommitmentV1",
    "ReviewerIdentityV1",
    "ReviewerRevealV1",
    "canonical_label_jsonl",
    "compute_commitment",
    "verify_audit_chain",
    "verify_reviewer_chain",
)
