"""Verified post-judge provider evidence and the complete audit population."""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import stat
import threading
import weakref
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import InitVar, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Self, TypeAlias, cast, get_args, get_type_hints
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from laconian_eval.benchmark.attachments import canonical_json_v1, parse_canonical_json_v1
from laconian_eval.benchmark.context import (
    AttachmentLayerRootMemberV1,
    BenchmarkProtocolBindingsV1,
    GenerationLayerRootMemberV1,
    LayerRootIndexV1,
    VerifiedGenerationContextExpectationV1,
    VerifiedGenerationContextIndexV1,
    _filesystem_identity,
    _FilesystemIdentity,
    _load_layer_root_index_at,
    _open_retained_directory,
    _recheck_retained_path,
    _stable_regular_file_snapshot,
    _validate_layer_tree,
    _write_attachment_at,
    load_verified_generation_context_index,
    protocol_bindings_from_context,
)
from laconian_eval.benchmark.hard_score import (
    HardScoreRequestSetV1,
    _verify_hard_score_request_set_from_checked_authority,
)
from laconian_eval.benchmark.judge import (
    JudgeAttachmentV1,
    JudgeAttemptBoundaryV1,
    JudgeAttemptEvidenceV1,
    JudgeRequestAttachmentV1,
    RubricItemV1,
    VerifiedJudgeAttemptRootV1,
    _validate_boundary_request_binding,
    _verify_judge_attachment_from_checked_authority,
    _verify_judge_request_attachment_from_checked_authority,
    load_verified_judge_attempt_root,
)
from laconian_eval.benchmark.protocol_review import (
    AuditReviewerRegistryV1,
    ProtocolReviewerRegistryV1,
    ProtocolReviewIdentityRegistryBundleV1,
    ProtocolReviewRoleV1,
    VerifiedProtocolAttestationV1,
    _class_bound_revalidate,
    compute_audit_reviewer_registry_sha256,
    compute_protocol_attestations_root,
    compute_protocol_reviewer_registry_sha256,
)
from laconian_eval.capsule.attempts import ProviderMetadataString
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2
from laconian_eval.models import WarningSeverity
from laconian_eval.providers import (
    AppliedCacheControlStatus,
    CacheReadStatus,
    CacheWriteStatus,
    ServiceTierStatus,
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GIT_OID_RE = re.compile(r"[0-9a-f]{40}")
_PUBLIC_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
_CANONICAL_MODELS = tuple(sorted(_PUBLIC_MODELS, key=str.encode))
_AUDIT_POPULATION_ATTACHMENT_MAX_BYTES = 4 * 1024 * 1024
_AUDIT_POPULATION_JSONL_MAX_BYTES = 128 * 1024 * 1024
RequestedModelIdV1: TypeAlias = Literal["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def _validate_nested_model_owner(
    value: object,
    expected_owner: type[BaseModel],
    *,
    collection: bool = False,
    json_mode: bool = False,
) -> object:
    """Reject Python-supplied model subclasses before Pydantic can normalize them."""

    values = value if collection and isinstance(value, (list, tuple)) else (value,)
    if any(isinstance(item, BaseModel) and type(item) is not expected_owner for item in values):
        raise ValueError(f"field must contain exact {expected_owner.__name__} owners")
    if collection and json_mode and type(value) is list:
        return tuple(value)
    return value


def _revalidate_model(model_type: type[BaseModel], value: object) -> BaseModel:
    if type(value) is not model_type:
        raise TypeError(f"expected exact {model_type.__name__}")
    payload = model_type.model_dump(value, mode="python", round_trip=True, warnings=False)
    return model_type.model_validate(payload)


class RequestedReturnedModelEvidenceV1(_StrictFrozenModel):
    purpose: Literal["generation", "judge"]
    requested_model_id: RequestedModelIdV1
    returned_model_id: ProviderMetadataString
    returned_model_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")


def compute_requested_returned_model_source_sha256(
    *,
    purpose: Literal["generation", "judge"],
    requested_model_id: RequestedModelIdV1,
    returned_model_id: ProviderMetadataString,
    ordered_source_sha256s: tuple[str, ...],
) -> str:
    """Hash one nonempty canonical ordered set of independently verified model sources."""

    if type(purpose) is not str or purpose not in {"generation", "judge"}:
        raise ValueError("model-source purpose is outside the closed vocabulary")
    if type(requested_model_id) is not str or requested_model_id not in _PUBLIC_MODELS:
        raise ValueError("requested model is outside the public benchmark")
    if type(returned_model_id) is not str or not returned_model_id.strip():
        raise ValueError("returned model ID must be nonblank provider metadata")
    if (
        type(ordered_source_sha256s) is not tuple
        or not ordered_source_sha256s
        or any(
            type(item) is not str or _SHA256_RE.fullmatch(item) is None
            for item in ordered_source_sha256s
        )
    ):
        raise ValueError("model-source aggregate requires a nonempty ordered SHA-256 tuple")
    return stable_digest(
        "laconian-requested-returned-model-sources-v1",
        {
            "purpose": purpose,
            "requested_model_id": requested_model_id,
            "returned_model_id": returned_model_id,
            "ordered_returned_model_source_sha256s": ordered_source_sha256s,
        },
    )


class PublicBenchmarkCacheEvidenceV1(_StrictFrozenModel):
    attempt_id: str = Field(pattern="^[0-9a-f]{64}$")
    applied_prompt_cache_mode: ProviderMetadataString | None
    applied_prompt_cache_ttl: ProviderMetadataString | None
    applied_cache_control_status: AppliedCacheControlStatus
    ordinary_uncached_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    cache_read_status: CacheReadStatus
    cache_write_tokens: int | None = Field(default=None, ge=0)
    cache_write_status: CacheWriteStatus
    visible_output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    requested_service_tier: Literal["default"]
    returned_service_tier: ProviderMetadataString | None
    service_tier_status: ServiceTierStatus
    applied_cache_control_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    cache_read_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    cache_write_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    service_tier_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    usage_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    reasoning_tokens_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class ProviderEvidenceIndexV1(_StrictFrozenModel):
    schema_version: Literal["benchmark-provider-evidence-index-v1"]
    campaign_id: str
    audit_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_reviewer_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    campaign_seed: str = Field(pattern="^[0-9a-f]{64}$")
    campaign_seed_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    input_tag_commit: str = Field(pattern="^[0-9a-f]{40}$")
    hard_scorer_source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_prompt_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_schema_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_requested_service_tier: Literal["default"]
    judge_service_tier_wire_field: Literal["service_tier"]
    corpus_case_root: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    estimand_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bootstrap_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    outcome_classification_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    false_fail_sensitivity_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_sampling_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_commit_reveal_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_adjudication_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    provider_projection_root: str = Field(pattern="^[0-9a-f]{64}$")
    audit_reviewer_registry: AuditReviewerRegistryV1
    protocol_reviewer_registry: ProtocolReviewerRegistryV1
    protocol_attestations: tuple[
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
    ]
    protocol_attestations_root: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bound_generation_complete_authority_root_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_attempt_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    requested_returned_model_ids: tuple[RequestedReturnedModelEvidenceV1, ...]
    generation_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    judge_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    provider_evidence_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @field_validator("audit_reviewer_registry", "protocol_reviewer_registry", mode="before")
    @classmethod
    def reject_foreign_registry_owner(cls, value: object, info: ValidationInfo) -> object:
        owner = (
            AuditReviewerRegistryV1
            if info.field_name == "audit_reviewer_registry"
            else ProtocolReviewerRegistryV1
        )
        return _validate_nested_model_owner(value, owner)

    @field_validator(
        "protocol_attestations",
        "requested_returned_model_ids",
        "generation_cache_evidence",
        "judge_cache_evidence",
        mode="before",
    )
    @classmethod
    def reject_foreign_collection_owners(cls, value: object, info: ValidationInfo) -> object:
        owners: dict[str, type[BaseModel]] = {
            "protocol_attestations": VerifiedProtocolAttestationV1,
            "requested_returned_model_ids": RequestedReturnedModelEvidenceV1,
            "generation_cache_evidence": PublicBenchmarkCacheEvidenceV1,
            "judge_cache_evidence": PublicBenchmarkCacheEvidenceV1,
        }
        field_name = info.field_name
        if field_name is None:
            raise ValueError("provider index nested owner field is unknown")
        return _validate_nested_model_owner(
            value,
            owners[field_name],
            collection=True,
            json_mode=info.mode == "json",
        )

    @model_validator(mode="after")
    def validate_closed_index(self) -> Self:
        if (
            type(self.audit_reviewer_registry) is not AuditReviewerRegistryV1
            or type(self.protocol_reviewer_registry) is not ProtocolReviewerRegistryV1
            or any(
                type(row) is not VerifiedProtocolAttestationV1 for row in self.protocol_attestations
            )
            or any(
                type(row) is not RequestedReturnedModelEvidenceV1
                for row in self.requested_returned_model_ids
            )
            or any(
                type(row) is not PublicBenchmarkCacheEvidenceV1
                for row in (*self.generation_cache_evidence, *self.judge_cache_evidence)
            )
        ):
            raise ValueError("provider index contains a foreign nested owner")
        expected_projection = (
            ("generation", "gpt-5.6-sol"),
            ("generation", "gpt-5.6-terra"),
            ("generation", "gpt-5.6-luna"),
            ("judge", "gpt-5.6-sol"),
        )
        if (
            tuple(
                (row.purpose, row.requested_model_id) for row in self.requested_returned_model_ids
            )
            != expected_projection
        ):
            raise ValueError("provider index requested/returned model projection mismatch")
        vectors = (
            self.ordered_generation_capsule_sha256s,
            self.ordered_hard_score_request_set_sha256s,
            self.ordered_judge_request_attachment_sha256s,
            self.ordered_judge_attempt_boundary_sha256s,
            self.ordered_judge_attachment_sha256s,
        )
        if any(len(set(vector)) != 36 for vector in vectors):
            raise ValueError("provider index requires 36 unique parents per bound source")
        reviewers = self.audit_reviewer_registry.reviewers
        reviewer_keys = tuple(row.reviewer_id.encode("utf-8") for row in reviewers)
        if (
            reviewer_keys != tuple(sorted(reviewer_keys))
            or len(set(reviewer_keys)) != 2
            or len({row.reviewer_numeric_account_id for row in reviewers}) != 2
            or len({row.reviewer_login for row in reviewers}) != 2
            or self.audit_reviewer_registry.audit_reviewer_registry_sha256
            != compute_audit_reviewer_registry_sha256(reviewers)
            or self.audit_reviewer_registry_sha256
            != compute_audit_reviewer_registry_sha256(reviewers)
        ):
            raise ValueError("provider index audit reviewer registry mismatch")
        expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        protocol_reviewers = self.protocol_reviewer_registry.reviewers
        recomputed_registry = compute_protocol_reviewer_registry_sha256(protocol_reviewers)
        if (
            tuple(row.role for row in protocol_reviewers) != expected_roles
            or tuple(row.statement.role for row in self.protocol_attestations) != expected_roles
            or len({row.reviewer_numeric_account_id for row in protocol_reviewers}) != 3
            or len({row.reviewer_login for row in protocol_reviewers}) != 3
            or len({row.attestation_sha256 for row in self.protocol_attestations}) != 3
            or self.protocol_reviewer_registry.protocol_reviewer_registry_sha256
            != recomputed_registry
            or self.protocol_reviewer_registry_sha256 != recomputed_registry
        ):
            raise ValueError("provider index protocol reviewer registry mismatch")
        shared_authority: tuple[str, str, str, str, str] | None = None
        for attestation, reviewer in zip(
            self.protocol_attestations,
            protocol_reviewers,
            strict=True,
        ):
            statement = attestation.statement
            signature = attestation.signature_evidence
            if (
                statement.role != reviewer.role
                or statement.reviewer_numeric_account_id != reviewer.reviewer_numeric_account_id
                or statement.reviewer_login != reviewer.reviewer_login
                or statement.verification_mode != reviewer.verification_mode
                or statement.signing_fingerprint != reviewer.signing_fingerprint
                or signature.verification_mode != reviewer.verification_mode
                or statement.protocol_registry_sha256 != recomputed_registry
                or statement.workflow_root != self.workflow_root
                or statement.peeled_c0_oid != self.input_tag_commit
            ):
                raise ValueError("provider index protocol attestation identity mismatch")
            fingerprint = getattr(signature, "fingerprint", None)
            if (
                reviewer.verification_mode != "github_verified_commit"
                and fingerprint != reviewer.signing_fingerprint
            ):
                raise ValueError("provider index protocol signature fingerprint mismatch")
            authority = (
                statement.input_tag_ref,
                statement.input_tag_oid,
                statement.input_tag_object_sha256,
                statement.peeled_c0_oid,
                statement.peeled_c0_sha256,
            )
            if shared_authority is None:
                shared_authority = authority
            elif shared_authority != authority:
                raise ValueError("provider index protocol attestation authority mismatch")
        if self.protocol_attestations_root != compute_protocol_attestations_root(
            self.protocol_attestations
        ):
            raise ValueError("provider index protocol review root mismatch")
        expected_seed = stable_digest(
            "laconian-campaign-seed-v1",
            {
                "schema_version": "1",
                "algorithm": "public-hex-seed-v1",
                "campaign_seed": self.campaign_seed,
            },
        )
        if self.campaign_seed_sha256 != expected_seed:
            raise ValueError("provider index campaign seed digest mismatch")
        expected_self = stable_digest(
            "laconian-benchmark-provider-evidence-index-v1",
            self.model_dump(mode="json", exclude={"provider_evidence_index_sha256"}),
        )
        if self.provider_evidence_index_sha256 != expected_self:
            raise ValueError("provider index self digest mismatch")
        return self


class BenchmarkProviderEvidenceProjectionV1(_StrictFrozenModel):
    schema_version: Literal["benchmark-provider-evidence-v1"]
    campaign_id: str
    provider_evidence_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    bound_generation_complete_authority_root_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    protocol_bindings: BenchmarkProtocolBindingsV1
    workflow_root: str = Field(pattern="^[0-9a-f]{64}$")
    statistical_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    audit_protocol_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_attempt_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    requested_returned_model_ids: tuple[RequestedReturnedModelEvidenceV1, ...]
    generation_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    judge_cache_evidence: tuple[PublicBenchmarkCacheEvidenceV1, ...]
    benchmark_provider_evidence_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @field_validator("protocol_bindings", mode="before")
    @classmethod
    def reject_foreign_protocol_owner(cls, value: object) -> object:
        return _validate_nested_model_owner(value, BenchmarkProtocolBindingsV1)

    @field_validator(
        "requested_returned_model_ids",
        "generation_cache_evidence",
        "judge_cache_evidence",
        mode="before",
    )
    @classmethod
    def reject_foreign_collection_owners(cls, value: object, info: ValidationInfo) -> object:
        owners: dict[str, type[BaseModel]] = {
            "requested_returned_model_ids": RequestedReturnedModelEvidenceV1,
            "generation_cache_evidence": PublicBenchmarkCacheEvidenceV1,
            "judge_cache_evidence": PublicBenchmarkCacheEvidenceV1,
        }
        field_name = info.field_name
        if field_name is None:
            raise ValueError("provider projection nested owner field is unknown")
        return _validate_nested_model_owner(
            value,
            owners[field_name],
            collection=True,
            json_mode=info.mode == "json",
        )

    @model_validator(mode="after")
    def validate_projection(self) -> Self:
        if (
            type(self.protocol_bindings) is not BenchmarkProtocolBindingsV1
            or any(
                type(row) is not RequestedReturnedModelEvidenceV1
                for row in self.requested_returned_model_ids
            )
            or any(
                type(row) is not PublicBenchmarkCacheEvidenceV1
                for row in (*self.generation_cache_evidence, *self.judge_cache_evidence)
            )
        ):
            raise ValueError("provider projection contains a foreign nested owner")
        vectors = (
            self.ordered_generation_capsule_sha256s,
            self.ordered_hard_score_request_set_sha256s,
            self.ordered_judge_request_attachment_sha256s,
            self.ordered_judge_attempt_boundary_sha256s,
            self.ordered_judge_attachment_sha256s,
        )
        if any(len(set(vector)) != 36 for vector in vectors):
            raise ValueError("provider projection requires 36 unique parents per bound source")
        expected = stable_digest(
            "laconian-benchmark-provider-evidence-v1",
            self.model_dump(mode="json", exclude={"benchmark_provider_evidence_sha256"}),
        )
        if self.benchmark_provider_evidence_sha256 != expected:
            raise ValueError("provider projection self digest mismatch")
        return self


_PROVIDER_CONSTRUCTION_AUTHORITY = object()


@dataclass(frozen=True, slots=True, weakref_slot=True)
class VerifiedBenchmarkProviderEvidenceV1:
    generation_expectation: VerifiedGenerationContextExpectationV1
    generation_context: VerifiedGenerationContextIndexV1
    identity_registry_bundle: ProtocolReviewIdentityRegistryBundleV1
    index: ProviderEvidenceIndexV1
    projection: BenchmarkProviderEvidenceProjectionV1
    generation_evidence: tuple[VerifiedScoredCapsuleV2, ...]
    hard_score_root_index: LayerRootIndexV1
    hard_score_request_sets: tuple[HardScoreRequestSetV1, ...]
    judge_request_root_index: LayerRootIndexV1
    judge_request_attachments: tuple[JudgeRequestAttachmentV1, ...]
    judge_attempt_root: VerifiedJudgeAttemptRootV1
    judge_root_index: LayerRootIndexV1
    judge_attachments: tuple[JudgeAttachmentV1, ...]
    _construction_authority: InitVar[object] = None

    def __post_init__(self, _construction_authority: object) -> None:
        if _construction_authority is not _PROVIDER_CONSTRUCTION_AUTHORITY:
            raise TypeError("verified provider evidence is loader-owned")


@dataclass(frozen=True, slots=True)
class _ProviderMintEntry:
    reference: weakref.ReferenceType[VerifiedBenchmarkProviderEvidenceV1]
    fingerprint: str


_VERIFIED_PROVIDER_EVIDENCE_MINTS: dict[int, _ProviderMintEntry] = {}
_VERIFIED_PROVIDER_EVIDENCE_MINTS_LOCK = threading.RLock()


def _annotation_owners(
    annotation: object,
    registered: Mapping[type[Any], str],
) -> frozenset[type[object]]:
    owners: set[type[object]] = set()
    if isinstance(annotation, type) and annotation in registered:
        owners.add(annotation)
    for argument in get_args(annotation):
        owners.update(_annotation_owners(argument, registered))
    return frozenset(owners)


def _annotation_scalar_owners(annotation: object) -> frozenset[type[object]]:
    owners: set[type[object]] = set()
    if isinstance(annotation, type) and annotation in _FINGERPRINT_SCALAR_OWNERS:
        owners.add(annotation)
    for argument in get_args(annotation):
        if type(argument) in _FINGERPRINT_SCALAR_OWNERS:
            owners.add(type(argument))
        else:
            owners.update(_annotation_scalar_owners(argument))
    return frozenset(owners)


def _annotation_container_owners(annotation: object) -> frozenset[type[object]]:
    owners: set[type[object]] = set()
    origin = getattr(annotation, "__origin__", None)
    if origin is tuple or annotation is tuple:
        owners.add(tuple)
    if origin in {dict, Mapping} or annotation in {dict, Mapping}:
        owners.update({dict, MappingProxyType})
    for argument in get_args(annotation):
        owners.update(_annotation_container_owners(argument))
    return frozenset(owners)


def _tuple_item_annotation(annotation: object, ordinal: int, length: int) -> object:
    arguments = get_args(annotation)
    if len(arguments) == 2 and arguments[1] is Ellipsis:
        return arguments[0]
    if len(arguments) == length:
        return arguments[ordinal]
    return object


def _mapping_value_annotation(annotation: object) -> object:
    arguments = get_args(annotation)
    return arguments[1] if len(arguments) == 2 else object


def _canonical_fingerprint_value(
    value: object,
    expected_annotation: object = object,
    *,
    _preflighted: bool = False,
) -> object:
    if not _preflighted:
        _preflight_exact_owners(value, expected_annotation)
    owner = type(value)
    model_type = cast(type[BaseModel], owner)
    model_owner = _FINGERPRINT_MODEL_OWNER_NAMES.get(model_type)
    if model_owner is not None:
        roundtrip_json = model_type.model_dump_json(
            cast(BaseModel, value),
            round_trip=True,
            warnings=False,
        ).encode("utf-8")
        checked = model_type.model_validate_json(roundtrip_json)
        return {
            "owner": model_owner,
            "value": checked.model_dump(mode="json", round_trip=True, warnings=False),
        }
    dataclass_owner = _FINGERPRINT_DATACLASS_OWNER_NAMES.get(owner)
    if dataclass_owner is not None:
        allowed = _annotation_owners(
            expected_annotation,
            _FINGERPRINT_DATACLASS_OWNER_NAMES,
        )
        if expected_annotation is not object and owner not in allowed:
            raise TypeError("retained dataclass owner differs from its declared slot")
        hints = _FINGERPRINT_DATACLASS_FIELD_HINTS[owner]
        return {
            "owner": dataclass_owner,
            "fields": [
                [
                    field.name,
                    _canonical_fingerprint_value(
                        object.__getattribute__(value, field.name),
                        hints[field.name],
                        _preflighted=True,
                    ),
                ]
                for field in dataclasses.fields(cast(Any, value))
            ],
        }
    if owner is tuple:
        allowed = _annotation_container_owners(expected_annotation)
        if expected_annotation is not object and tuple not in allowed:
            raise TypeError("tuple owner differs from its declared slot")
        values = cast(tuple[object, ...], value)
        return [
            _canonical_fingerprint_value(
                item,
                _tuple_item_annotation(expected_annotation, ordinal, len(values)),
                _preflighted=True,
            )
            for ordinal, item in enumerate(values)
        ]
    if owner in {dict, MappingProxyType}:
        allowed = _annotation_container_owners(expected_annotation)
        if expected_annotation is not object and owner not in allowed:
            raise TypeError("mapping owner differs from its declared slot")
        mapping = cast(Mapping[object, object], value)
        if not all(type(key) is str for key in mapping):
            raise TypeError("fingerprinted mappings require exact string keys")
        return [
            [
                key,
                _canonical_fingerprint_value(
                    mapping[key],
                    _mapping_value_annotation(expected_annotation),
                    _preflighted=True,
                ),
            ]
            for key in sorted(
                cast(Mapping[str, object], value), key=lambda item: item.encode("utf-8")
            )
        ]
    if value is None:
        return None
    if owner in _FINGERPRINT_SCALAR_OWNERS:
        if expected_annotation is not object:
            allowed = _annotation_scalar_owners(expected_annotation)
            if owner not in allowed:
                raise TypeError("scalar owner differs from its declared slot")
        return value
    raise TypeError(f"unsupported verified-provider fingerprint owner: {owner!r}")


@dataclass(slots=True)
class _OwnerWalkState:
    active: set[int]
    nodes: int = 0


_FINGERPRINT_MAX_DEPTH = 128
_FINGERPRINT_MAX_NODES = 1_000_000


def _preflight_exact_owners(
    value: object,
    expected_annotation: object = object,
    *,
    _state: _OwnerWalkState | None = None,
    _depth: int = 0,
) -> None:
    """Reject every unregistered nested owner before invoking serialization methods."""

    state = _OwnerWalkState(active=set()) if _state is None else _state
    if _depth > _FINGERPRINT_MAX_DEPTH:
        raise ValueError("verified-provider fingerprint exceeds nesting limit")
    state.nodes += 1
    if state.nodes > _FINGERPRINT_MAX_NODES:
        raise ValueError("verified-provider fingerprint exceeds owner-count limit")
    owner = type(value)
    tracked = (
        owner in _FINGERPRINT_MODEL_OWNER_NAMES
        or owner in _FINGERPRINT_DATACLASS_OWNER_NAMES
        or owner in {tuple, dict, MappingProxyType}
    )
    identity = id(value)
    if tracked:
        if identity in state.active:
            raise ValueError("verified-provider fingerprint contains an owner cycle")
        state.active.add(identity)
    try:
        _preflight_exact_owner_body(
            value,
            expected_annotation,
            state=state,
            depth=_depth,
        )
    finally:
        if tracked:
            state.active.remove(identity)


def _preflight_exact_owner_body(
    value: object,
    expected_annotation: object,
    *,
    state: _OwnerWalkState,
    depth: int,
) -> None:
    owner = type(value)
    if owner in _FINGERPRINT_MODEL_OWNER_NAMES:
        allowed = _annotation_owners(expected_annotation, _FINGERPRINT_MODEL_OWNER_NAMES)
        if expected_annotation is not object and owner not in allowed:
            raise TypeError("retained Pydantic owner differs from its declared slot")
        hints = _FINGERPRINT_MODEL_FIELD_HINTS[owner]
        for name in owner.model_fields:
            _preflight_exact_owners(
                object.__getattribute__(value, name),
                hints[name],
                _state=state,
                _depth=depth + 1,
            )
        return
    if owner in _FINGERPRINT_DATACLASS_OWNER_NAMES:
        allowed = _annotation_owners(
            expected_annotation,
            _FINGERPRINT_DATACLASS_OWNER_NAMES,
        )
        if expected_annotation is not object and owner not in allowed:
            raise TypeError("retained dataclass owner differs from its declared slot")
        hints = _FINGERPRINT_DATACLASS_FIELD_HINTS[owner]
        for field in dataclasses.fields(cast(Any, owner)):
            _preflight_exact_owners(
                object.__getattribute__(value, field.name),
                hints[field.name],
                _state=state,
                _depth=depth + 1,
            )
        return
    if owner is tuple:
        allowed = _annotation_container_owners(expected_annotation)
        if expected_annotation is not object and tuple not in allowed:
            raise TypeError("tuple owner differs from its declared slot")
        values = cast(tuple[object, ...], value)
        for ordinal, item in enumerate(values):
            _preflight_exact_owners(
                item,
                _tuple_item_annotation(expected_annotation, ordinal, len(values)),
                _state=state,
                _depth=depth + 1,
            )
        return
    if owner in {dict, MappingProxyType}:
        allowed = _annotation_container_owners(expected_annotation)
        if expected_annotation is not object and owner not in allowed:
            raise TypeError("mapping owner differs from its declared slot")
        mapping = cast(Mapping[object, object], value)
        if not all(type(key) is str for key in mapping):
            raise TypeError("fingerprinted mappings require exact string keys")
        for key in sorted(cast(Mapping[str, object], mapping), key=str.encode):
            _preflight_exact_owners(
                mapping[key],
                _mapping_value_annotation(expected_annotation),
                _state=state,
                _depth=depth + 1,
            )
        return
    if value is None:
        if expected_annotation is not object:
            nullable = expected_annotation is type(None) or any(
                argument is type(None) for argument in get_args(expected_annotation)
            )
            if not nullable:
                raise TypeError("null differs from its declared slot")
        return
    if owner in _FINGERPRINT_SCALAR_OWNERS:
        if expected_annotation is not object:
            allowed = _annotation_scalar_owners(expected_annotation)
            if owner not in allowed:
                raise TypeError("scalar owner differs from its declared slot")
        return
    raise TypeError(f"unsupported nested owner in provider fingerprint: {owner!r}")


def _provider_snapshot(value: VerifiedBenchmarkProviderEvidenceV1) -> tuple[object, ...]:
    return tuple(object.__getattribute__(value, field.name) for field in dataclasses.fields(value))


def _provider_fingerprint(snapshot: tuple[object, ...]) -> str:
    names = tuple(field.name for field in dataclasses.fields(VerifiedBenchmarkProviderEvidenceV1))
    hints = _FINGERPRINT_DATACLASS_FIELD_HINTS[VerifiedBenchmarkProviderEvidenceV1]
    return stable_digest(
        "laconian-verified-benchmark-provider-evidence-full-content-v1",
        [
            [name, _canonical_fingerprint_value(value, hints[name])]
            for name, value in zip(names, snapshot, strict=True)
        ],
    )


def _register_provider(
    value: VerifiedBenchmarkProviderEvidenceV1,
    fingerprint: str,
) -> None:
    identity = id(value)

    def cleanup(dead_ref: weakref.ReferenceType[VerifiedBenchmarkProviderEvidenceV1]) -> None:
        with _VERIFIED_PROVIDER_EVIDENCE_MINTS_LOCK:
            current = _VERIFIED_PROVIDER_EVIDENCE_MINTS.get(identity)
            if current is not None and current.reference is dead_ref:
                _VERIFIED_PROVIDER_EVIDENCE_MINTS.pop(identity, None)

    reference = weakref.ref(value, cleanup)
    with _VERIFIED_PROVIDER_EVIDENCE_MINTS_LOCK:
        _VERIFIED_PROVIDER_EVIDENCE_MINTS[identity] = _ProviderMintEntry(reference, fingerprint)


def _mint_provider(
    snapshot: tuple[object, ...],
    *,
    fingerprint: str,
) -> VerifiedBenchmarkProviderEvidenceV1:
    value = VerifiedBenchmarkProviderEvidenceV1(
        generation_expectation=cast(
            VerifiedGenerationContextExpectationV1,
            snapshot[0],
        ),
        generation_context=cast(VerifiedGenerationContextIndexV1, snapshot[1]),
        identity_registry_bundle=cast(
            ProtocolReviewIdentityRegistryBundleV1,
            snapshot[2],
        ),
        index=cast(ProviderEvidenceIndexV1, snapshot[3]),
        projection=cast(BenchmarkProviderEvidenceProjectionV1, snapshot[4]),
        generation_evidence=cast(tuple[VerifiedScoredCapsuleV2, ...], snapshot[5]),
        hard_score_root_index=cast(LayerRootIndexV1, snapshot[6]),
        hard_score_request_sets=cast(tuple[HardScoreRequestSetV1, ...], snapshot[7]),
        judge_request_root_index=cast(LayerRootIndexV1, snapshot[8]),
        judge_request_attachments=cast(
            tuple[JudgeRequestAttachmentV1, ...],
            snapshot[9],
        ),
        judge_attempt_root=cast(VerifiedJudgeAttemptRootV1, snapshot[10]),
        judge_root_index=cast(LayerRootIndexV1, snapshot[11]),
        judge_attachments=cast(tuple[JudgeAttachmentV1, ...], snapshot[12]),
        _construction_authority=_PROVIDER_CONSTRUCTION_AUTHORITY,
    )
    _register_provider(value, fingerprint)
    return value


def _verified_expectation_copy(
    value: object,
) -> VerifiedGenerationContextExpectationV1:
    if type(value) is not VerifiedGenerationContextExpectationV1:
        raise TypeError("expected verified generation expectation")
    return VerifiedGenerationContextExpectationV1(
        expectation=value.expectation,
        bound_generation_complete_authority_root_sha256=(
            value.bound_generation_complete_authority_root_sha256
        ),
    )


def _bundle_copy(value: object) -> ProtocolReviewIdentityRegistryBundleV1:
    _preflight_exact_owners(value, ProtocolReviewIdentityRegistryBundleV1)
    checked_value = cast(ProtocolReviewIdentityRegistryBundleV1, value)
    return _class_bound_revalidate(
        checked_value,
        ProtocolReviewIdentityRegistryBundleV1,
    )


def _security_bundle_subject(index: ProviderEvidenceIndexV1) -> str:
    security = tuple(
        row for row in index.protocol_attestations if row.statement.role == "security_evidence"
    )
    if len(security) != 1:
        raise ValueError("provider evidence requires one security attestation")
    values = {subject.kind: subject.sha256 for subject in security[0].statement.subjects}
    digest = values.get("identity_registry_bundle_sha256")
    if digest is None:
        raise ValueError("security attestation omits identity registry bundle")
    return digest


def _validate_context_index_binding(
    *,
    expectation: VerifiedGenerationContextExpectationV1,
    context: VerifiedGenerationContextIndexV1,
    index: ProviderEvidenceIndexV1,
) -> None:
    context_index = context.index
    copied_names = (
        "campaign_id",
        "audit_reviewer_registry_sha256",
        "protocol_reviewer_registry_sha256",
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
        "provider_projection_root",
        "audit_reviewer_registry",
        "protocol_reviewer_registry",
        "protocol_attestations",
        "protocol_attestations_root",
        "generation_context_index_sha256",
        "generation_root_index_sha256",
        "ordered_generation_capsule_sha256s",
    )
    if any(getattr(index, name) != getattr(context_index, name) for name in copied_names):
        raise ValueError("provider index does not copy the verified generation context")
    if (
        index.generation_context_expectation_sha256
        != expectation.expectation.generation_context_expectation_sha256
        or index.bound_generation_complete_authority_root_sha256
        != expectation.bound_generation_complete_authority_root_sha256
    ):
        raise ValueError("provider index expectation authority mismatch")


def _member_vector(index: LayerRootIndexV1) -> tuple[str, ...]:
    return tuple(
        member.generation_capsule_sha256
        if type(member) is GenerationLayerRootMemberV1
        else cast(AttachmentLayerRootMemberV1, member).attachment_sha256
        for member in index.members
    )


def _validate_terminal_judge_attempts(
    boundaries: tuple[JudgeAttemptBoundaryV1, ...],
    request_attachments: tuple[JudgeRequestAttachmentV1, ...],
    judge_attachments: tuple[JudgeAttachmentV1, ...],
) -> None:
    for boundary, requests, attachment in zip(
        boundaries,
        request_attachments,
        judge_attachments,
        strict=True,
    ):
        records = {row.judge_request_id: row for row in attachment.records}
        wrappers = {row.blind_request.judge_request_id: row for row in requests.requests}
        if records.keys() != wrappers.keys():
            raise ValueError("judge final-record coverage mismatch")
        attempts_by_request: dict[str, list[JudgeAttemptEvidenceV1]] = {
            request_id: [] for request_id in boundary.ordered_judge_request_ids
        }
        for attempt in boundary.attempts:
            try:
                attempts_by_request[attempt.judge_request_id].append(attempt)
            except KeyError:
                raise ValueError("judge attempt has an unknown request parent") from None
        for request_id in boundary.ordered_judge_request_ids:
            history = attempts_by_request[request_id]
            if not history or history[-1].disposition != "success" or not history[-1].terminal:
                raise ValueError("judge final record lacks one terminal-success attempt")
            terminal = history[-1]
            record = records.get(request_id)
            if record is None or terminal.judgment is None:
                raise ValueError("judge final record is missing")
            if (
                record.raw_judge_attempt_sha256 != terminal.judge_attempt_evidence_sha256
                or record.returned_judge_model_id != terminal.returned_judge_model_id
                or canonical_json_v1(record.judgment.model_dump(mode="json"))
                != canonical_json_v1(terminal.judgment.model_dump(mode="json"))
            ):
                raise ValueError("judge final record differs from terminal-success attempt")


def _verify_provider_chains_from_checked_context(
    *,
    checked_context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    identity_registry_bundle: ProtocolReviewIdentityRegistryBundleV1,
    hard_score_request_sets: tuple[HardScoreRequestSetV1, ...],
    judge_request_attachments: tuple[JudgeRequestAttachmentV1, ...],
    judge_attachments: tuple[JudgeAttachmentV1, ...],
) -> None:
    """Sequentially replay all chains from one call-local checked context."""

    if (
        type(checked_context) is not VerifiedGenerationContextIndexV1
        or type(expectation) is not VerifiedGenerationContextExpectationV1
        or checked_context.expectation != expectation
    ):
        raise ValueError("provider context is bound to a different external expectation")
    vectors = (
        (hard_score_request_sets, HardScoreRequestSetV1),
        (judge_request_attachments, JudgeRequestAttachmentV1),
        (judge_attachments, JudgeAttachmentV1),
    )
    if any(
        type(values) is not tuple
        or len(values) != 36
        or any(type(value) is not owner for value in values)
        for values, owner in vectors
    ):
        raise ValueError("provider checked-chain vector mismatch")
    for ordinal in range(36):
        member = checked_context.root_index.members[ordinal]
        evidence = checked_context.generation_evidence[ordinal]
        hard = hard_score_request_sets[ordinal]
        request = judge_request_attachments[ordinal]
        judge = judge_attachments[ordinal]
        if (
            type(member) is not GenerationLayerRootMemberV1
            or type(evidence) is not VerifiedScoredCapsuleV2
        ):
            raise ValueError("provider checked context contains a foreign member")
        _verify_hard_score_request_set_from_checked_authority(
            hard,
            index=checked_context.index,
            member=member,
            evidence=evidence,
        )
        _verify_judge_request_attachment_from_checked_authority(
            request,
            index=checked_context.index,
            member=member,
            evidence=evidence,
            request_set=hard,
            identity_registry_bundle=identity_registry_bundle,
        )
        _verify_judge_attachment_from_checked_authority(
            judge,
            index=checked_context.index,
            member=member,
            evidence=evidence,
            request_set=hard,
            request_attachment=request,
        )


def _cache_from_generation(row: Any) -> PublicBenchmarkCacheEvidenceV1:
    raw = row.raw
    usage = raw.usage
    required = (
        raw.applied_cache_control_status,
        usage.cache_read_status,
        usage.cache_write_status,
        raw.service_tier_status,
        raw.applied_cache_control_source_sha256,
        raw.cache_read_source_sha256,
        raw.cache_write_source_sha256,
        raw.service_tier_source_sha256,
        raw.usage_source_sha256,
        raw.reasoning_tokens_source_sha256,
    )
    if any(value is None for value in required) or raw.requested_service_tier != "default":
        raise ValueError("generation attempt lacks complete public benchmark evidence")
    visible = None
    if usage.output_tokens is not None and usage.reasoning_tokens is not None:
        if usage.reasoning_tokens > usage.output_tokens:
            raise ValueError("reasoning tokens exceed output tokens")
        visible = usage.output_tokens - usage.reasoning_tokens
    return PublicBenchmarkCacheEvidenceV1(
        attempt_id=row.attempt_id,
        applied_prompt_cache_mode=raw.applied_prompt_cache_mode,
        applied_prompt_cache_ttl=raw.applied_prompt_cache_ttl,
        applied_cache_control_status=raw.applied_cache_control_status,
        ordinary_uncached_input_tokens=usage.ordinary_uncached_input_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_read_status=usage.cache_read_status,
        cache_write_tokens=usage.cache_write_tokens,
        cache_write_status=usage.cache_write_status,
        visible_output_tokens=visible,
        reasoning_tokens=usage.reasoning_tokens,
        requested_service_tier="default",
        returned_service_tier=raw.returned_service_tier,
        service_tier_status=raw.service_tier_status,
        applied_cache_control_source_sha256=raw.applied_cache_control_source_sha256,
        cache_read_source_sha256=raw.cache_read_source_sha256,
        cache_write_source_sha256=raw.cache_write_source_sha256,
        service_tier_source_sha256=raw.service_tier_source_sha256,
        usage_source_sha256=raw.usage_source_sha256,
        reasoning_tokens_source_sha256=raw.reasoning_tokens_source_sha256,
    )


def _cache_from_judge(row: Any) -> PublicBenchmarkCacheEvidenceV1:
    usage = row.usage
    visible = None
    if usage.output_tokens is not None and usage.reasoning_tokens is not None:
        if usage.reasoning_tokens > usage.output_tokens:
            raise ValueError("judge reasoning tokens exceed output tokens")
        visible = usage.output_tokens - usage.reasoning_tokens
    return PublicBenchmarkCacheEvidenceV1(
        attempt_id=row.judge_attempt_id,
        applied_prompt_cache_mode=row.applied_prompt_cache_mode,
        applied_prompt_cache_ttl=row.applied_prompt_cache_ttl,
        applied_cache_control_status=row.applied_cache_control_status,
        ordinary_uncached_input_tokens=usage.ordinary_uncached_input_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_read_status=usage.cache_read_status,
        cache_write_tokens=usage.cache_write_tokens,
        cache_write_status=usage.cache_write_status,
        visible_output_tokens=visible,
        reasoning_tokens=usage.reasoning_tokens,
        requested_service_tier="default",
        returned_service_tier=row.returned_service_tier,
        service_tier_status=row.service_tier_status,
        applied_cache_control_source_sha256=row.applied_cache_control_source_sha256,
        cache_read_source_sha256=row.cache_read_source_sha256,
        cache_write_source_sha256=row.cache_write_source_sha256,
        service_tier_source_sha256=row.service_tier_source_sha256,
        usage_source_sha256=row.usage_source_sha256,
        reasoning_tokens_source_sha256=row.reasoning_tokens_source_sha256,
    )


def _derive_provider_model_and_cache_evidence(
    generation_evidence: tuple[VerifiedScoredCapsuleV2, ...],
    judge_attempt_root: VerifiedJudgeAttemptRootV1,
) -> tuple[
    tuple[RequestedReturnedModelEvidenceV1, ...],
    tuple[PublicBenchmarkCacheEvidenceV1, ...],
    tuple[PublicBenchmarkCacheEvidenceV1, ...],
]:
    generation_projection: list[RequestedReturnedModelEvidenceV1] = []
    for requested in _PUBLIC_MODELS:
        successful = tuple(
            row.raw
            for capsule in generation_evidence
            if capsule.manifest.provider.model == requested
            for row in capsule.scored_attempts
            if row.terminal_reason == "success"
        )
        returned_ids = {row.returned_model_id for row in successful}
        sources = tuple(row.returned_model_source_sha256 for row in successful)
        if (
            not successful
            or len(returned_ids) != 1
            or None in returned_ids
            or any(source is None for source in sources)
        ):
            raise ValueError("generation requested/returned model evidence is inconsistent")
        returned = cast(str, next(iter(returned_ids)))
        generation_projection.append(
            RequestedReturnedModelEvidenceV1(
                purpose="generation",
                requested_model_id=cast(RequestedModelIdV1, requested),
                returned_model_id=returned,
                returned_model_source_sha256=compute_requested_returned_model_source_sha256(
                    purpose="generation",
                    requested_model_id=cast(RequestedModelIdV1, requested),
                    returned_model_id=returned,
                    ordered_source_sha256s=cast(tuple[str, ...], sources),
                ),
            )
        )
    successful_judge = tuple(
        row
        for boundary in judge_attempt_root.boundaries
        for row in boundary.attempts
        if row.disposition == "success"
    )
    judge_ids = {row.returned_judge_model_id for row in successful_judge}
    judge_sources = tuple(row.returned_judge_model_source_sha256 for row in successful_judge)
    if not successful_judge or len(judge_ids) != 1 or None in judge_ids:
        raise ValueError("judge requested/returned model evidence is inconsistent")
    returned_judge = cast(str, next(iter(judge_ids)))
    generation_projection.append(
        RequestedReturnedModelEvidenceV1(
            purpose="judge",
            requested_model_id="gpt-5.6-sol",
            returned_model_id=returned_judge,
            returned_model_source_sha256=compute_requested_returned_model_source_sha256(
                purpose="judge",
                requested_model_id="gpt-5.6-sol",
                returned_model_id=returned_judge,
                ordered_source_sha256s=judge_sources,
            ),
        )
    )
    generation_cache = tuple(
        _cache_from_generation(row)
        for capsule in generation_evidence
        for row in capsule.scored_attempts
    )
    judge_cache = tuple(
        _cache_from_judge(row)
        for boundary in judge_attempt_root.boundaries
        for row in boundary.attempts
    )
    return tuple(generation_projection), generation_cache, judge_cache


def _projection_from_index(
    index: ProviderEvidenceIndexV1,
    context: VerifiedGenerationContextIndexV1,
) -> BenchmarkProviderEvidenceProjectionV1:
    payload: dict[str, object] = {
        "schema_version": "benchmark-provider-evidence-v1",
        "campaign_id": index.campaign_id,
        "provider_evidence_index_sha256": index.provider_evidence_index_sha256,
        "generation_context_expectation_sha256": index.generation_context_expectation_sha256,
        "bound_generation_complete_authority_root_sha256": (
            index.bound_generation_complete_authority_root_sha256
        ),
        "generation_context_index_sha256": index.generation_context_index_sha256,
        "protocol_bindings": protocol_bindings_from_context(context.index).model_dump(mode="json"),
        "workflow_root": index.workflow_root,
        "statistical_protocol_sha256": index.statistical_protocol_sha256,
        "audit_protocol_sha256": index.audit_protocol_sha256,
        "generation_root_index_sha256": index.generation_root_index_sha256,
        "hard_score_root_index_sha256": index.hard_score_root_index_sha256,
        "judge_request_root_index_sha256": index.judge_request_root_index_sha256,
        "judge_attempt_root_index_sha256": index.judge_attempt_root_index_sha256,
        "judge_root_index_sha256": index.judge_root_index_sha256,
        "ordered_generation_capsule_sha256s": index.ordered_generation_capsule_sha256s,
        "ordered_hard_score_request_set_sha256s": index.ordered_hard_score_request_set_sha256s,
        "ordered_judge_request_attachment_sha256s": index.ordered_judge_request_attachment_sha256s,
        "ordered_judge_attempt_boundary_sha256s": index.ordered_judge_attempt_boundary_sha256s,
        "ordered_judge_attachment_sha256s": index.ordered_judge_attachment_sha256s,
        "requested_returned_model_ids": tuple(
            row.model_dump(mode="json") for row in index.requested_returned_model_ids
        ),
        "generation_cache_evidence": tuple(
            row.model_dump(mode="json") for row in index.generation_cache_evidence
        ),
        "judge_cache_evidence": tuple(
            row.model_dump(mode="json") for row in index.judge_cache_evidence
        ),
    }
    payload["benchmark_provider_evidence_sha256"] = stable_digest(
        "laconian-benchmark-provider-evidence-v1", payload
    )
    return BenchmarkProviderEvidenceProjectionV1.model_validate(payload)


def _validate_complete_provider_graph(snapshot: tuple[object, ...]) -> tuple[object, ...]:
    (
        raw_expectation,
        raw_context,
        raw_bundle,
        raw_index,
        raw_projection,
        raw_generation,
        raw_hard_index,
        raw_hard,
        raw_request_index,
        raw_requests,
        raw_attempt_root,
        raw_judge_index,
        raw_judges,
    ) = snapshot
    expectation = _verified_expectation_copy(raw_expectation)
    if type(raw_context) is not VerifiedGenerationContextIndexV1:
        raise TypeError("provider evidence requires the exact verified context owner")
    context = VerifiedGenerationContextIndexV1(
        expectation=raw_context.expectation,
        index=raw_context.index,
        root_index=raw_context.root_index,
        generation_evidence=raw_context.generation_evidence,
    )
    if context.expectation != expectation:
        raise ValueError("provider context is bound to a different external expectation")
    bundle = _bundle_copy(raw_bundle)
    index = cast(ProviderEvidenceIndexV1, _revalidate_model(ProviderEvidenceIndexV1, raw_index))
    projection = cast(
        BenchmarkProviderEvidenceProjectionV1,
        _revalidate_model(BenchmarkProviderEvidenceProjectionV1, raw_projection),
    )
    if type(raw_generation) is not tuple or raw_generation != context.generation_evidence:
        raise ValueError("provider generation evidence differs from verified context")
    generation = context.generation_evidence
    hard_index = cast(LayerRootIndexV1, _revalidate_model(LayerRootIndexV1, raw_hard_index))
    request_index = cast(LayerRootIndexV1, _revalidate_model(LayerRootIndexV1, raw_request_index))
    judge_index = cast(LayerRootIndexV1, _revalidate_model(LayerRootIndexV1, raw_judge_index))
    if type(raw_hard) is not tuple or len(raw_hard) != 36:
        raise ValueError("provider hard-score evidence requires 36 members")
    if type(raw_requests) is not tuple or len(raw_requests) != 36:
        raise ValueError("provider judge-request evidence requires 36 members")
    if type(raw_judges) is not tuple or len(raw_judges) != 36:
        raise ValueError("provider judge evidence requires 36 members")
    hard = tuple(
        cast(HardScoreRequestSetV1, _revalidate_model(HardScoreRequestSetV1, row))
        for row in raw_hard
    )
    requests = tuple(
        cast(JudgeRequestAttachmentV1, _revalidate_model(JudgeRequestAttachmentV1, row))
        for row in raw_requests
    )
    judges = tuple(
        cast(JudgeAttachmentV1, _revalidate_model(JudgeAttachmentV1, row)) for row in raw_judges
    )
    if type(raw_attempt_root) is not VerifiedJudgeAttemptRootV1:
        raise TypeError("provider evidence requires the exact judge-attempt root owner")
    attempt_root = VerifiedJudgeAttemptRootV1(
        index=raw_attempt_root.index,
        boundaries=raw_attempt_root.boundaries,
    )
    _validate_context_index_binding(expectation=expectation, context=context, index=index)
    if _security_bundle_subject(index) != bundle.identity_registry_bundle_sha256:
        raise ValueError("identity registry bundle is not bound by the C0 security attestation")
    layer_specs = (
        (
            context.root_index,
            "generation",
            index.generation_root_index_sha256,
            index.ordered_generation_capsule_sha256s,
        ),
        (
            hard_index,
            "hard-score",
            index.hard_score_root_index_sha256,
            index.ordered_hard_score_request_set_sha256s,
        ),
        (
            request_index,
            "judge-request",
            index.judge_request_root_index_sha256,
            index.ordered_judge_request_attachment_sha256s,
        ),
        (
            judge_index,
            "judge",
            index.judge_root_index_sha256,
            index.ordered_judge_attachment_sha256s,
        ),
    )
    for layer, kind, digest, vector in layer_specs:
        if (
            layer.layer_kind != kind
            or layer.layer_root_index_sha256 != digest
            or _member_vector(layer) != vector
        ):
            raise ValueError("provider layer root/index/vector mismatch")
    if (
        attempt_root.index.judge_attempt_root_index_sha256 != index.judge_attempt_root_index_sha256
        or attempt_root.index.judge_request_root_index_sha256
        != index.judge_request_root_index_sha256
        or tuple(row.judge_attempt_boundary_sha256 for row in attempt_root.boundaries)
        != index.ordered_judge_attempt_boundary_sha256s
    ):
        raise ValueError("provider judge-attempt root mismatch")
    for attempt_member, boundary, request_attachment in zip(
        attempt_root.index.members,
        attempt_root.boundaries,
        requests,
        strict=True,
    ):
        _validate_boundary_request_binding(
            index=attempt_root.index,
            member=attempt_member,
            boundary=boundary,
            attachment=request_attachment,
        )
    for (
        generation_member,
        scored,
        hard_member,
        hard_row,
        request_member,
        request_row,
        judge_member,
        judge_row,
    ) in zip(
        context.root_index.members,
        generation,
        hard_index.members,
        hard,
        request_index.members,
        requests,
        judge_index.members,
        judges,
        strict=True,
    ):
        if (
            type(generation_member) is not GenerationLayerRootMemberV1
            or type(hard_member) is not AttachmentLayerRootMemberV1
            or type(request_member) is not AttachmentLayerRootMemberV1
            or type(judge_member) is not AttachmentLayerRootMemberV1
            or generation_member.generation_capsule_sha256 != scored.capsule_sha256
            or hard_member.attachment_sha256 != hard_row.hard_score_request_set_sha256
            or request_member.attachment_sha256 != request_row.judge_request_attachment_sha256
            or judge_member.attachment_sha256 != judge_row.judge_attachment_sha256
            or any(
                member.generation_model != generation_member.generation_model
                or member.scenario_uid != generation_member.scenario_uid
                for member in (hard_member, request_member, judge_member)
            )
        ):
            raise ValueError("provider chain member mismatch")
    _verify_provider_chains_from_checked_context(
        checked_context=context,
        expectation=expectation,
        identity_registry_bundle=bundle,
        hard_score_request_sets=hard,
        judge_request_attachments=requests,
        judge_attachments=judges,
    )
    _validate_terminal_judge_attempts(attempt_root.boundaries, requests, judges)
    models, generation_cache, judge_cache = _derive_provider_model_and_cache_evidence(
        generation, attempt_root
    )
    if (
        index.requested_returned_model_ids != models
        or index.generation_cache_evidence != generation_cache
        or index.judge_cache_evidence != judge_cache
        or projection != _projection_from_index(index, context)
    ):
        raise ValueError("provider evidence projection differs from verified sources")
    return (
        expectation,
        context,
        bundle,
        index,
        projection,
        generation,
        hard_index,
        hard,
        request_index,
        requests,
        attempt_root,
        judge_index,
        judges,
    )


def _revalidate_verified_provider_evidence_v1(
    value: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedBenchmarkProviderEvidenceV1:
    if type(value) is not VerifiedBenchmarkProviderEvidenceV1:
        raise TypeError("expected loader-minted provider evidence")
    identity = id(value)
    with _VERIFIED_PROVIDER_EVIDENCE_MINTS_LOCK:
        entry = _VERIFIED_PROVIDER_EVIDENCE_MINTS.get(identity)
        if entry is None or entry.reference() is not value:
            raise TypeError("provider evidence identity was not loader-minted")
        expected_fingerprint = entry.fingerprint
    snapshot = _provider_snapshot(value)
    if _provider_fingerprint(snapshot) != expected_fingerprint:
        raise ValueError("provider evidence changed after verification")
    checked_snapshot = _validate_complete_provider_graph(snapshot)
    checked_fingerprint = _provider_fingerprint(checked_snapshot)
    if checked_fingerprint != expected_fingerprint:
        raise ValueError("provider evidence changed during owner revalidation")
    return _mint_provider(checked_snapshot, fingerprint=checked_fingerprint)


def write_provider_evidence_index(
    provider_index_path: Path,
    index: ProviderEvidenceIndexV1,
    *,
    generation_expectation: VerifiedGenerationContextExpectationV1,
) -> None:
    """Match live expectation, revalidate, and no-replace write one canonical provider index."""

    checked = cast(ProviderEvidenceIndexV1, _revalidate_model(ProviderEvidenceIndexV1, index))
    expectation = _verified_expectation_copy(generation_expectation)
    if provider_index_path.name != "provider-evidence-index.json":
        raise ValueError("provider evidence index path must use the fixed leaf name")
    if (
        checked.generation_context_expectation_sha256
        != expectation.expectation.generation_context_expectation_sha256
        or checked.bound_generation_complete_authority_root_sha256
        != expectation.bound_generation_complete_authority_root_sha256
    ):
        raise ValueError("provider index does not match the live generation expectation")
    parent = provider_index_path.parent
    descriptor, _ = _open_retained_directory(parent)
    try:
        _write_attachment_at(
            descriptor, "provider-evidence-index.json", checked.model_dump(mode="json")
        )
        _recheck_retained_path(
            parent,
            descriptor,
            _filesystem_identity(os.fstat(descriptor)),
        )
    finally:
        os.close(descriptor)


def _load_provider_evidence_index_at(
    descriptor: int,
) -> tuple[ProviderEvidenceIndexV1, bytes, _FilesystemIdentity]:
    raw, identity = _stable_regular_file_snapshot(
        descriptor,
        "provider-evidence-index.json",
    )
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ValueError("provider evidence index requires exactly one final LF")
    parsed = parse_canonical_json_v1(raw[:-1])
    if not isinstance(parsed, dict):
        raise ValueError("provider evidence index must be a canonical object")
    index = ProviderEvidenceIndexV1.model_validate_json(raw[:-1])
    reloaded, reloaded_identity = _stable_regular_file_snapshot(
        descriptor,
        "provider-evidence-index.json",
    )
    if reloaded != raw or reloaded_identity != identity:
        raise ValueError("provider evidence index changed while loading")
    return index, raw, identity


def load_provider_evidence_index(provider_index_path: Path) -> ProviderEvidenceIndexV1:
    """Load the canonical index and recompute seed, registries, roots, and self digest."""

    if provider_index_path.name != "provider-evidence-index.json":
        raise ValueError("provider evidence index path must use the fixed leaf name")
    parent = provider_index_path.parent
    descriptor, identity = _open_retained_directory(parent)
    try:
        index, raw, file_identity = _load_provider_evidence_index_at(descriptor)
        reloaded, reloaded_identity = _stable_regular_file_snapshot(
            descriptor,
            "provider-evidence-index.json",
        )
        if reloaded != raw or reloaded_identity != file_identity:
            raise ValueError("provider evidence index changed while loading")
        _recheck_retained_path(parent, descriptor, identity)
        return index
    finally:
        os.close(descriptor)


@dataclass(slots=True)
class _LoadedAttachmentLayer:
    root: Path
    descriptor: int
    root_identity: _FilesystemIdentity
    root_names: frozenset[str]
    index_path: str
    index_raw: bytes
    index_identity: _FilesystemIdentity
    member_snapshots: tuple[tuple[str, bytes, _FilesystemIdentity], ...]
    index: LayerRootIndexV1
    rows: tuple[BaseModel, ...]

    def recheck(self) -> None:
        with os.scandir(self.descriptor) as entries:
            if frozenset(entry.name for entry in entries) != self.root_names:
                raise ValueError("provider layer root allowlist changed while loading")
        _validate_layer_tree(self.descriptor, self.index)
        index_raw, index_identity = _stable_regular_file_snapshot(
            self.descriptor,
            self.index_path,
        )
        if index_raw != self.index_raw or index_identity != self.index_identity:
            raise ValueError("provider layer index changed while loading")
        for path, expected_raw, expected_identity in self.member_snapshots:
            raw, identity = _stable_regular_file_snapshot(self.descriptor, path)
            if raw != expected_raw or identity != expected_identity:
                raise ValueError("provider layer member changed while loading")
        _recheck_retained_path(self.root, self.descriptor, self.root_identity)

    def close(self) -> None:
        os.close(self.descriptor)


def _retained_tree_snapshot(
    descriptor: int,
) -> tuple[tuple[str, _FilesystemIdentity], ...]:
    rows: list[tuple[str, _FilesystemIdentity]] = []

    def walk(current: int, prefix: str, depth: int) -> None:
        if depth > 128 or len(rows) > 100_000:
            raise ValueError("retained evidence tree exceeds resource limits")
        before = _filesystem_identity(os.fstat(current))
        with os.scandir(current) as entries:
            names = sorted((entry.name for entry in entries), key=str.encode)
        for name in names:
            try:
                visible = os.stat(name, dir_fd=current, follow_symlinks=False)
            except OSError as error:
                raise ValueError("retained evidence tree changed while scanning") from error
            identity = _filesystem_identity(visible)
            relative = f"{prefix}/{name}" if prefix else name
            if stat.S_ISLNK(visible.st_mode):
                raise ValueError("retained evidence tree contains a symbolic link")
            if stat.S_ISREG(visible.st_mode):
                if visible.st_nlink != 1:
                    raise ValueError("retained evidence tree contains an inode alias")
            elif stat.S_ISDIR(visible.st_mode):
                child = os.open(
                    name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=current,
                )
                try:
                    if _filesystem_identity(os.fstat(child)) != identity:
                        raise ValueError("retained evidence directory changed while opening")
                    walk(child, relative, depth + 1)
                    if _filesystem_identity(os.fstat(child)) != identity:
                        raise ValueError("retained evidence directory changed while scanning")
                finally:
                    os.close(child)
            else:
                raise ValueError("retained evidence tree contains a special file")
            if (
                _filesystem_identity(os.stat(name, dir_fd=current, follow_symlinks=False))
                != identity
            ):
                raise ValueError("retained evidence member changed while scanning")
            rows.append((relative, identity))
        if _filesystem_identity(os.fstat(current)) != before:
            raise ValueError("retained evidence directory changed while scanning")

    walk(descriptor, "", 0)
    return tuple(sorted(rows, key=lambda row: row[0].encode("utf-8")))


@dataclass(slots=True)
class _RetainedTreeWitness:
    root: Path
    descriptor: int
    root_identity: _FilesystemIdentity
    tree: tuple[tuple[str, _FilesystemIdentity], ...]

    @classmethod
    def open(cls, root: Path) -> _RetainedTreeWitness:
        descriptor, identity = _open_retained_directory(root)
        try:
            return cls(
                root=root,
                descriptor=descriptor,
                root_identity=identity,
                tree=_retained_tree_snapshot(descriptor),
            )
        except BaseException:
            os.close(descriptor)
            raise

    def recheck(self) -> None:
        if _retained_tree_snapshot(self.descriptor) != self.tree:
            raise ValueError("retained evidence tree changed while loading")
        _recheck_retained_path(self.root, self.descriptor, self.root_identity)

    def close(self) -> None:
        os.close(self.descriptor)


def _load_attachment_layer(
    root: Path,
    *,
    kind: Literal["hard-score", "judge-request", "judge"],
    attachment_type: type[BaseModel],
    extra_root_children: frozenset[str] = frozenset(),
) -> _LoadedAttachmentLayer:
    descriptor, identity = _open_retained_directory(root)
    try:
        with os.scandir(descriptor) as entries:
            names = {entry.name for entry in entries}
        directory = {
            "hard-score": "hard-score",
            "judge-request": "judge-requests",
            "judge": "judge",
        }[kind]
        if names != {directory, *extra_root_children}:
            raise ValueError("provider layer root allowlist mismatch")
        index = _load_layer_root_index_at(descriptor, expected_kind=kind)
        index_path = f"{directory}/index.json"
        index_raw, index_identity = _stable_regular_file_snapshot(
            descriptor,
            index_path,
        )
        expected_index_raw = canonical_json_v1(index.model_dump(mode="json")) + b"\n"
        if index_raw != expected_index_raw:
            raise ValueError("provider layer index bytes differ from verified index")
        rows: list[BaseModel] = []
        member_snapshots: list[tuple[str, bytes, _FilesystemIdentity]] = []
        for member in index.members:
            if type(member) is not AttachmentLayerRootMemberV1:
                raise ValueError("attachment layer contains a foreign member")
            raw, member_identity = _stable_regular_file_snapshot(
                descriptor,
                member.relative_path,
            )
            if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
                raise ValueError("attachment member requires exactly one final LF")
            parsed = parse_canonical_json_v1(raw[:-1])
            if not isinstance(parsed, dict):
                raise ValueError("attachment layer member must be a canonical object")
            row = attachment_type.model_validate_json(raw[:-1])
            typed_row = cast(Any, row)
            digest_name = {
                "hard-score": "hard_score_request_set_sha256",
                "judge-request": "judge_request_attachment_sha256",
                "judge": "judge_attachment_sha256",
            }[kind]
            if (
                getattr(row, digest_name) != member.attachment_sha256
                or typed_row.generation_model != member.generation_model
                or typed_row.scenario_uid != member.scenario_uid
                or typed_row.campaign_id != index.campaign_id
            ):
                raise ValueError("attachment layer member binding mismatch")
            rows.append(row)
            member_snapshots.append((member.relative_path, raw, member_identity))
        loaded = _LoadedAttachmentLayer(
            root=root,
            descriptor=descriptor,
            root_identity=identity,
            root_names=frozenset(names),
            index_path=index_path,
            index_raw=index_raw,
            index_identity=index_identity,
            member_snapshots=tuple(member_snapshots),
            index=index,
            rows=tuple(rows),
        )
        loaded.recheck()
        return loaded
    except BaseException:
        os.close(descriptor)
        raise


def load_verified_benchmark_provider_evidence(
    *,
    provider_index_path: Path,
    generation_root: Path,
    hard_score_root: Path,
    judge_request_root: Path,
    judge_attempt_root: Path,
    judge_root: Path,
    generation_expectation: VerifiedGenerationContextExpectationV1,
    identity_registry_bundle: ProtocolReviewIdentityRegistryBundleV1,
) -> VerifiedBenchmarkProviderEvidenceV1:
    """Verify the live capabilities, four layer roots, and separate attempt root."""

    expectation = _verified_expectation_copy(generation_expectation)
    bundle = _bundle_copy(identity_registry_bundle)
    if provider_index_path != judge_root / "provider-evidence-index.json":
        raise ValueError("provider index is not the fixed judge-root child")
    retained_layers: list[_LoadedAttachmentLayer] = []
    retained_trees: list[_RetainedTreeWitness] = []
    try:
        generation_witness = _RetainedTreeWitness.open(generation_root)
        retained_trees.append(generation_witness)
        attempt_witness = _RetainedTreeWitness.open(judge_attempt_root)
        retained_trees.append(attempt_witness)
        judge_layer = _load_attachment_layer(
            judge_root,
            kind="judge",
            attachment_type=JudgeAttachmentV1,
            extra_root_children=frozenset({"provider-evidence-index.json"}),
        )
        retained_layers.append(judge_layer)
        index, index_raw, index_identity = _load_provider_evidence_index_at(judge_layer.descriptor)
        context = load_verified_generation_context_index(
            generation_index_path=generation_root / "generation-context.json",
            generation_root=generation_root,
            expectation=expectation,
        )
        generation_witness.recheck()
        _validate_context_index_binding(
            expectation=expectation,
            context=context,
            index=index,
        )
        if _security_bundle_subject(index) != bundle.identity_registry_bundle_sha256:
            raise ValueError("identity registry bundle is not bound by the C0 security attestation")
        hard_layer = _load_attachment_layer(
            hard_score_root,
            kind="hard-score",
            attachment_type=HardScoreRequestSetV1,
        )
        retained_layers.append(hard_layer)
        request_layer = _load_attachment_layer(
            judge_request_root,
            kind="judge-request",
            attachment_type=JudgeRequestAttachmentV1,
        )
        retained_layers.append(request_layer)
        hard = cast(tuple[HardScoreRequestSetV1, ...], hard_layer.rows)
        requests = cast(tuple[JudgeRequestAttachmentV1, ...], request_layer.rows)
        judges = cast(tuple[JudgeAttachmentV1, ...], judge_layer.rows)
        attempt_root = load_verified_judge_attempt_root(
            judge_attempt_root,
            expected_request_root_index_sha256=index.judge_request_root_index_sha256,
            request_attachments=requests,
        )
        attempt_witness.recheck()
        projection = _projection_from_index(index, context)
        snapshot: tuple[object, ...] = (
            expectation,
            context,
            bundle,
            index,
            projection,
            context.generation_evidence,
            hard_layer.index,
            hard,
            request_layer.index,
            requests,
            attempt_root,
            judge_layer.index,
            judges,
        )
        checked_snapshot = _validate_complete_provider_graph(snapshot)
        for retained_layer in retained_layers:
            retained_layer.recheck()
        for retained_tree in retained_trees:
            retained_tree.recheck()
        reloaded_index, reloaded_identity = _stable_regular_file_snapshot(
            judge_layer.descriptor,
            "provider-evidence-index.json",
        )
        if reloaded_index != index_raw or reloaded_identity != index_identity:
            raise ValueError("provider evidence index changed before mint")
        return _mint_provider(
            checked_snapshot,
            fingerprint=_provider_fingerprint(checked_snapshot),
        )
    finally:
        for retained_layer in reversed(retained_layers):
            retained_layer.close()
        for retained_tree in reversed(retained_trees):
            retained_tree.close()


class AuditPopulationAttachmentV1(_StrictFrozenModel):
    schema_version: Literal["audit-population-attachment-v1"]
    campaign_id: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    generation_context_expectation_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    generation_context_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    provider_evidence_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    benchmark_provider_evidence_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_attempt_root_index_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    ordered_generation_capsule_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_hard_score_request_set_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_request_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_attempt_boundary_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    ordered_judge_attachment_sha256s: tuple[str, ...] = Field(min_length=36, max_length=36)
    record_count: int = Field(ge=0, le=1_440)
    records_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    population_attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @field_validator("protocol_bindings", mode="before")
    @classmethod
    def reject_foreign_protocol_owner(cls, value: object) -> object:
        return _validate_nested_model_owner(value, BenchmarkProtocolBindingsV1)

    @model_validator(mode="after")
    def validate_attachment(self) -> Self:
        if type(self.protocol_bindings) is not BenchmarkProtocolBindingsV1:
            raise ValueError("audit population contains a foreign protocol owner")
        vectors = (
            self.ordered_generation_capsule_sha256s,
            self.ordered_hard_score_request_set_sha256s,
            self.ordered_judge_request_attachment_sha256s,
            self.ordered_judge_attempt_boundary_sha256s,
            self.ordered_judge_attachment_sha256s,
        )
        if any(len(set(vector)) != 36 for vector in vectors):
            raise ValueError("audit population requires 36 unique parents per bound source")
        expected = stable_digest(
            "laconian-audit-population-attachment-v1",
            self.model_dump(mode="json", exclude={"population_attachment_sha256"}),
        )
        if self.population_attachment_sha256 != expected:
            raise ValueError("audit population attachment self digest mismatch")
        return self


class AuditPopulationRecordV1(_StrictFrozenModel):
    canonical_record_id: str = Field(pattern="^[0-9a-f]{64}$")
    generation_capsule_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    hard_score_request_set_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    judge_attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    plan_item_id: str = Field(pattern="^[0-9a-f]{64}$")
    response_id: str = Field(pattern="^[0-9a-f]{64}$")
    judge_request_id: str = Field(pattern="^[0-9a-f]{64}$")
    generation_model: str
    scenario_uid: str = Field(pattern="^[0-9a-f]{64}$")
    locale: str
    repetition: int = Field(ge=0, lt=5)
    arm: Literal["baseline", "caveman", "if", "concise"]
    blinded_judge_decision: bool
    case_id: str
    case_category: str
    warning_severity: WarningSeverity | None
    prompt: str
    rubric: tuple[RubricItemV1, ...]
    material_warning_requirement: str | None
    candidate_response: str

    @field_validator("rubric", mode="before")
    @classmethod
    def reject_foreign_rubric_owners(cls, value: object, info: ValidationInfo) -> object:
        return _validate_nested_model_owner(
            value,
            RubricItemV1,
            collection=True,
            json_mode=info.mode == "json",
        )

    @model_validator(mode="after")
    def validate_exact_rubric_owners(self) -> Self:
        if any(type(row) is not RubricItemV1 for row in self.rubric):
            raise ValueError("audit population record contains a foreign rubric owner")
        return self


_AUDIT_POPULATION_CONSTRUCTION_AUTHORITY = object()


@dataclass(frozen=True, slots=True, weakref_slot=True)
class VerifiedAuditPopulationV1:
    attachment: AuditPopulationAttachmentV1
    records: tuple[AuditPopulationRecordV1, ...]
    _construction_authority: InitVar[object] = None

    def __post_init__(self, _construction_authority: object) -> None:
        if _construction_authority is not _AUDIT_POPULATION_CONSTRUCTION_AUTHORITY:
            raise TypeError("verified audit population is owner-minted")


_FINGERPRINT_DATACLASS_OWNERS = frozenset(
    {
        VerifiedGenerationContextExpectationV1,
        VerifiedGenerationContextIndexV1,
        VerifiedScoredCapsuleV2,
        VerifiedJudgeAttemptRootV1,
        VerifiedBenchmarkProviderEvidenceV1,
        VerifiedAuditPopulationV1,
    }
)
_FINGERPRINT_DATACLASS_OWNER_NAMES = {
    owner: f"{owner.__module__}.{owner.__qualname__}" for owner in _FINGERPRINT_DATACLASS_OWNERS
}


def _build_fingerprint_owner_registries() -> tuple[
    dict[type[BaseModel], str],
    frozenset[type[object]],
]:
    """Build a closed exact-class registry from the six admitted owner roots."""

    models: set[type[BaseModel]] = set()
    scalars: set[type[object]] = {
        str,
        int,
        bool,
        float,
        date,
        datetime,
        UUID,
    }

    def visit_annotation(annotation: object) -> None:
        if isinstance(annotation, type):
            if issubclass(annotation, BaseModel):
                visit_model(annotation)
                return
            if issubclass(annotation, Enum) or annotation.__module__.startswith(
                ("pydantic", "pydantic_core")
            ):
                scalars.add(annotation)
                return
            if annotation in _FINGERPRINT_DATACLASS_OWNERS:
                visit_dataclass(annotation)
                return
        for argument in get_args(annotation):
            visit_annotation(argument)

    def visit_model(owner: type[BaseModel]) -> None:
        if owner in models:
            return
        models.add(owner)
        for field in owner.model_fields.values():
            visit_annotation(field.annotation)

    visited_dataclasses: set[type[object]] = set()

    def visit_dataclass(owner: type[object]) -> None:
        if owner in visited_dataclasses:
            return
        visited_dataclasses.add(owner)
        hints = get_type_hints(owner)
        for field in dataclasses.fields(cast(Any, owner)):
            visit_annotation(hints.get(field.name, field.type))

    for root in _FINGERPRINT_DATACLASS_OWNERS:
        visit_dataclass(root)
    return (
        {owner: f"{owner.__module__}.{owner.__qualname__}" for owner in models},
        frozenset(scalars),
    )


_FINGERPRINT_MODEL_OWNER_NAMES, _FINGERPRINT_SCALAR_OWNERS = _build_fingerprint_owner_registries()
_FINGERPRINT_DATACLASS_FIELD_HINTS = {
    owner: get_type_hints(owner, include_extras=True) for owner in _FINGERPRINT_DATACLASS_OWNERS
}
_FINGERPRINT_MODEL_FIELD_HINTS = {
    owner: get_type_hints(owner, include_extras=True) for owner in _FINGERPRINT_MODEL_OWNER_NAMES
}


@dataclass(frozen=True, slots=True)
class _PopulationMintEntry:
    reference: weakref.ReferenceType[VerifiedAuditPopulationV1]
    fingerprint: str


_VERIFIED_AUDIT_POPULATION_MINTS: dict[int, _PopulationMintEntry] = {}
_VERIFIED_AUDIT_POPULATION_MINTS_LOCK = threading.RLock()


def _population_fingerprint(
    attachment: AuditPopulationAttachmentV1,
    records: tuple[AuditPopulationRecordV1, ...],
) -> str:
    return stable_digest(
        "laconian-verified-audit-population-full-content-v1",
        {
            "attachment": _canonical_fingerprint_value(
                attachment,
                AuditPopulationAttachmentV1,
            ),
            "records": _canonical_fingerprint_value(
                records,
                tuple[AuditPopulationRecordV1, ...],
            ),
        },
    )


def _register_population(value: VerifiedAuditPopulationV1, fingerprint: str) -> None:
    identity = id(value)

    def cleanup(dead_ref: weakref.ReferenceType[VerifiedAuditPopulationV1]) -> None:
        with _VERIFIED_AUDIT_POPULATION_MINTS_LOCK:
            current = _VERIFIED_AUDIT_POPULATION_MINTS.get(identity)
            if current is not None and current.reference is dead_ref:
                _VERIFIED_AUDIT_POPULATION_MINTS.pop(identity, None)

    reference = weakref.ref(value, cleanup)
    with _VERIFIED_AUDIT_POPULATION_MINTS_LOCK:
        _VERIFIED_AUDIT_POPULATION_MINTS[identity] = _PopulationMintEntry(reference, fingerprint)


def _mint_population(
    attachment: AuditPopulationAttachmentV1,
    records: tuple[AuditPopulationRecordV1, ...],
    *,
    fingerprint: str,
) -> VerifiedAuditPopulationV1:
    value = VerifiedAuditPopulationV1(
        attachment=attachment,
        records=records,
        _construction_authority=_AUDIT_POPULATION_CONSTRUCTION_AUTHORITY,
    )
    _register_population(value, fingerprint)
    return value


def _canonical_population_jsonl(records: Sequence[AuditPopulationRecordV1]) -> bytes:
    rows = sorted(canonical_json_v1(record.model_dump(mode="json")) for record in records)
    return b"".join(row + b"\n" for row in rows)


def _canonical_record_id(
    *,
    campaign_id: str,
    generation_capsule_sha256: str,
    hard_score_request_set_sha256: str,
    judge_request_attachment_sha256: str,
    judge_attachment_sha256: str,
    plan_item_id: str,
    response_id: str,
    judge_request_id: str,
) -> str:
    return stable_digest(
        "laconian-audit-population-record-id-v1",
        {
            "campaign_id": campaign_id,
            "generation_capsule_sha256": generation_capsule_sha256,
            "hard_score_request_set_sha256": hard_score_request_set_sha256,
            "judge_request_attachment_sha256": judge_request_attachment_sha256,
            "judge_attachment_sha256": judge_attachment_sha256,
            "plan_item_id": plan_item_id,
            "response_id": response_id,
            "judge_request_id": judge_request_id,
        },
    )


def _validate_population_content(
    attachment: AuditPopulationAttachmentV1,
    records: tuple[AuditPopulationRecordV1, ...],
) -> tuple[AuditPopulationAttachmentV1, tuple[AuditPopulationRecordV1, ...]]:
    checked_attachment = cast(
        AuditPopulationAttachmentV1,
        _revalidate_model(AuditPopulationAttachmentV1, attachment),
    )
    if type(records) is not tuple:
        raise TypeError("audit population records require an exact tuple")
    checked_records = tuple(
        cast(AuditPopulationRecordV1, _revalidate_model(AuditPopulationRecordV1, row))
        for row in records
    )
    canonical = tuple(
        sorted(
            checked_records,
            key=lambda row: canonical_json_v1(row.model_dump(mode="json")),
        )
    )
    if (
        canonical != checked_records
        or len({row.canonical_record_id for row in checked_records}) != len(checked_records)
        or checked_attachment.record_count != len(checked_records)
        or checked_attachment.records_sha256
        != hashlib.sha256(_canonical_population_jsonl(checked_records)).hexdigest()
        or any(
            row.canonical_record_id
            != _canonical_record_id(
                campaign_id=checked_attachment.campaign_id,
                generation_capsule_sha256=row.generation_capsule_sha256,
                hard_score_request_set_sha256=row.hard_score_request_set_sha256,
                judge_request_attachment_sha256=row.judge_request_attachment_sha256,
                judge_attachment_sha256=row.judge_attachment_sha256,
                plan_item_id=row.plan_item_id,
                response_id=row.response_id,
                judge_request_id=row.judge_request_id,
            )
            for row in checked_records
        )
    ):
        raise ValueError("audit population content is not canonical and bijective")
    return checked_attachment, checked_records


def _revalidate_verified_audit_population_v1(
    value: VerifiedAuditPopulationV1,
) -> VerifiedAuditPopulationV1:
    if type(value) is not VerifiedAuditPopulationV1:
        raise TypeError("expected owner-minted audit population")
    identity = id(value)
    with _VERIFIED_AUDIT_POPULATION_MINTS_LOCK:
        entry = _VERIFIED_AUDIT_POPULATION_MINTS.get(identity)
        if entry is None or entry.reference() is not value:
            raise TypeError("audit population identity was not owner-minted")
        expected = entry.fingerprint
    attachment = value.attachment
    records = value.records
    if _population_fingerprint(attachment, records) != expected:
        raise ValueError("audit population changed after verification")
    checked_attachment, checked_records = _validate_population_content(attachment, records)
    checked_fingerprint = _population_fingerprint(checked_attachment, checked_records)
    if checked_fingerprint != expected:
        raise ValueError("audit population changed during owner revalidation")
    return _mint_population(
        checked_attachment,
        checked_records,
        fingerprint=checked_fingerprint,
    )


def _build_audit_population_from_checked(
    evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditPopulationV1:
    records: list[AuditPopulationRecordV1] = []
    for capsule, hard_set, request_attachment, judge_attachment in zip(
        evidence.generation_evidence,
        evidence.hard_score_request_sets,
        evidence.judge_request_attachments,
        evidence.judge_attachments,
        strict=True,
    ):
        wrappers = {
            row.blind_request.judge_request_id: row.blind_request
            for row in request_attachment.requests
        }
        judgments = {row.judge_request_id: row for row in judge_attachment.records}
        plan_by_id = {row.plan_item_id: row for row in capsule.plan}
        scored_by_id = {row.plan_item_id: row for row in capsule.scored_attempts}
        for hard in hard_set.records:
            if not hard.hard_pass:
                continue
            plan = plan_by_id.get(hard.plan_item_id)
            scored = scored_by_id.get(hard.plan_item_id)
            request_id = hard.judge_request_id
            blind = None if request_id is None else wrappers.get(request_id)
            judgment = None if request_id is None else judgments.get(request_id)
            if (
                plan is None
                or scored is None
                or request_id is None
                or hard.response_id is None
                or scored.response_id != hard.response_id
                or blind is None
                or judgment is None
                or blind.judge_request_id != judgment.judge_request_id
            ):
                raise ValueError("audit population hard-pass join mismatch")
            case = capsule.cases_by_uid.get(plan.case_uid)
            if (
                case is None
                or case.id != plan.case_id
                or blind.candidate_response != scored.raw.output_text
            ):
                raise ValueError("audit population case/candidate join mismatch")
            records.append(
                AuditPopulationRecordV1(
                    canonical_record_id=_canonical_record_id(
                        campaign_id=evidence.index.campaign_id,
                        generation_capsule_sha256=capsule.capsule_sha256,
                        hard_score_request_set_sha256=hard_set.hard_score_request_set_sha256,
                        judge_request_attachment_sha256=(
                            request_attachment.judge_request_attachment_sha256
                        ),
                        judge_attachment_sha256=judge_attachment.judge_attachment_sha256,
                        plan_item_id=plan.plan_item_id,
                        response_id=hard.response_id,
                        judge_request_id=request_id,
                    ),
                    generation_capsule_sha256=capsule.capsule_sha256,
                    hard_score_request_set_sha256=hard_set.hard_score_request_set_sha256,
                    judge_request_attachment_sha256=(
                        request_attachment.judge_request_attachment_sha256
                    ),
                    judge_attachment_sha256=judge_attachment.judge_attachment_sha256,
                    plan_item_id=plan.plan_item_id,
                    response_id=hard.response_id,
                    judge_request_id=request_id,
                    generation_model=capsule.manifest.provider.model,
                    scenario_uid=plan.scenario_uid,
                    locale=plan.locale,
                    repetition=plan.repetition,
                    arm=plan.arm,
                    blinded_judge_decision=judgment.judgment.semantic_pass,
                    case_id=case.id,
                    case_category=case.category,
                    warning_severity=case.semantic_rubric.material_warning_severity,
                    prompt=blind.prompt,
                    rubric=blind.rubric,
                    material_warning_requirement=blind.material_warning_requirement,
                    candidate_response=blind.candidate_response,
                )
            )
    ordered_records = tuple(
        sorted(records, key=lambda row: canonical_json_v1(row.model_dump(mode="json")))
    )
    if len({row.canonical_record_id for row in ordered_records}) != len(ordered_records):
        raise ValueError("audit population contains duplicate records")
    records_bytes = _canonical_population_jsonl(ordered_records)
    index = evidence.index
    projection = evidence.projection
    attachment_payload: dict[str, object] = {
        "schema_version": "audit-population-attachment-v1",
        "campaign_id": index.campaign_id,
        "protocol_bindings": protocol_bindings_from_context(evidence.generation_context.index),
        "generation_context_expectation_sha256": index.generation_context_expectation_sha256,
        "generation_context_index_sha256": index.generation_context_index_sha256,
        "provider_evidence_index_sha256": index.provider_evidence_index_sha256,
        "benchmark_provider_evidence_sha256": projection.benchmark_provider_evidence_sha256,
        "judge_attempt_root_index_sha256": index.judge_attempt_root_index_sha256,
        "ordered_generation_capsule_sha256s": index.ordered_generation_capsule_sha256s,
        "ordered_hard_score_request_set_sha256s": index.ordered_hard_score_request_set_sha256s,
        "ordered_judge_request_attachment_sha256s": index.ordered_judge_request_attachment_sha256s,
        "ordered_judge_attempt_boundary_sha256s": index.ordered_judge_attempt_boundary_sha256s,
        "ordered_judge_attachment_sha256s": index.ordered_judge_attachment_sha256s,
        "record_count": len(ordered_records),
        "records_sha256": hashlib.sha256(records_bytes).hexdigest(),
    }
    attachment_digest_payload = {
        **attachment_payload,
        "protocol_bindings": cast(
            BenchmarkProtocolBindingsV1,
            attachment_payload["protocol_bindings"],
        ).model_dump(mode="json"),
    }
    attachment_payload["population_attachment_sha256"] = stable_digest(
        "laconian-audit-population-attachment-v1", attachment_digest_payload
    )
    attachment = AuditPopulationAttachmentV1.model_validate(attachment_payload)
    checked_attachment, checked_records = _validate_population_content(attachment, ordered_records)
    return _mint_population(
        checked_attachment,
        checked_records,
        fingerprint=_population_fingerprint(checked_attachment, checked_records),
    )


def build_audit_population(
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditPopulationV1:
    """Derive the complete judged-record population from one verified 36-chain projection."""

    evidence = _revalidate_verified_provider_evidence_v1(provider_evidence)
    return _build_audit_population_from_checked(evidence)


def write_audit_population(
    audit_root: Path,
    population: VerifiedAuditPopulationV1,
) -> None:
    """Write only population-attachment.json and population.jsonl beneath audit_root."""

    checked = _revalidate_verified_audit_population_v1(population)
    with suppress(FileExistsError):
        audit_root.mkdir(mode=0o700)
    descriptor, _ = _open_retained_directory(audit_root)
    try:
        with os.scandir(descriptor) as entries:
            if {entry.name for entry in entries} & {
                "population-attachment.json",
                "population.jsonl",
            }:
                raise FileExistsError("audit population already exists")
        _write_attachment_at(
            descriptor,
            "population-attachment.json",
            checked.attachment.model_dump(mode="json"),
        )
        records = _canonical_population_jsonl(checked.records)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        output = os.open("population.jsonl", flags, 0o600, dir_fd=descriptor)
        try:
            view = memoryview(records)
            while view:
                written = os.write(output, view)
                if written <= 0:
                    raise OSError("short audit population write")
                view = view[written:]
            os.fsync(output)
        finally:
            os.close(output)
        os.fsync(descriptor)
        _recheck_retained_path(
            audit_root,
            descriptor,
            _filesystem_identity(os.fstat(descriptor)),
        )
    finally:
        os.close(descriptor)


def _bounded_population_member_snapshot(
    descriptor: int,
    name: str,
    *,
    limit: int,
) -> tuple[bytes, _FilesystemIdentity]:
    try:
        visible = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    except OSError as error:
        raise ValueError("audit population member is missing or unsafe") from error
    if not stat.S_ISREG(visible.st_mode) or visible.st_nlink != 1 or visible.st_size > limit:
        raise ValueError("audit population member is not one bounded regular file")
    return _stable_regular_file_snapshot(descriptor, name)


def _population_identity_key(identity: _FilesystemIdentity) -> tuple[int, int]:
    return identity.device, identity.inode


def _load_verified_audit_population_from_bytes(
    *,
    attachment_raw: bytes,
    records_raw: bytes,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditPopulationV1:
    """Validate an already stable two-member snapshot against provider authority."""

    if not attachment_raw.endswith(b"\n") or attachment_raw.endswith(b"\n\n"):
        raise ValueError("audit population attachment requires exactly one final LF")
    attachment_payload = parse_canonical_json_v1(attachment_raw[:-1])
    if not isinstance(attachment_payload, dict):
        raise ValueError("audit population attachment must be a canonical object")
    attachment = AuditPopulationAttachmentV1.model_validate_json(attachment_raw[:-1])
    if records_raw and not records_raw.endswith(b"\n"):
        raise ValueError("audit population JSONL requires a final LF")
    records: list[AuditPopulationRecordV1] = []
    for line in records_raw.splitlines():
        parsed = parse_canonical_json_v1(line)
        if not isinstance(parsed, dict):
            raise ValueError("audit population row must be a canonical object")
        records.append(AuditPopulationRecordV1.model_validate_json(line))
    checked_attachment, checked_records = _validate_population_content(
        attachment,
        tuple(records),
    )
    expected = _build_audit_population_from_checked(provider_evidence)
    if (
        attachment_raw != canonical_json_v1(expected.attachment.model_dump(mode="json")) + b"\n"
        or records_raw != _canonical_population_jsonl(expected.records)
        or checked_attachment != expected.attachment
        or checked_records != expected.records
    ):
        raise ValueError("audit population differs from verified provider evidence")
    return _mint_population(
        checked_attachment,
        checked_records,
        fingerprint=_population_fingerprint(checked_attachment, checked_records),
    )


def load_verified_audit_population(
    audit_root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditPopulationV1:
    """Reload two fixed files and rederive them from the expected provider parents."""

    evidence = _revalidate_verified_provider_evidence_v1(provider_evidence)
    descriptor, identity = _open_retained_directory(audit_root)
    try:
        with os.scandir(descriptor) as entries:
            names = {entry.name for entry in entries}
        required = {"population-attachment.json", "population.jsonl"}
        allowed = {*required, "sample-manifest.json", "blind-packet.json"}
        if not required <= names or names - allowed:
            raise ValueError("audit population root allowlist mismatch")
        attachment_raw, attachment_identity = _bounded_population_member_snapshot(
            descriptor,
            "population-attachment.json",
            limit=_AUDIT_POPULATION_ATTACHMENT_MAX_BYTES,
        )
        raw_records, records_identity = _bounded_population_member_snapshot(
            descriptor,
            "population.jsonl",
            limit=_AUDIT_POPULATION_JSONL_MAX_BYTES,
        )
        if _population_identity_key(attachment_identity) == _population_identity_key(
            records_identity
        ):
            raise ValueError("audit population members alias one another")
        population = _load_verified_audit_population_from_bytes(
            attachment_raw=attachment_raw,
            records_raw=raw_records,
            provider_evidence=evidence,
        )
        reloaded_attachment, reloaded_attachment_identity = _bounded_population_member_snapshot(
            descriptor,
            "population-attachment.json",
            limit=_AUDIT_POPULATION_ATTACHMENT_MAX_BYTES,
        )
        reloaded_records, reloaded_records_identity = _bounded_population_member_snapshot(
            descriptor,
            "population.jsonl",
            limit=_AUDIT_POPULATION_JSONL_MAX_BYTES,
        )
        with os.scandir(descriptor) as entries:
            final_names = {entry.name for entry in entries}
        if (
            reloaded_attachment != attachment_raw
            or reloaded_attachment_identity != attachment_identity
            or reloaded_records != raw_records
            or reloaded_records_identity != records_identity
            or final_names != names
        ):
            raise ValueError("audit population changed while loading")
        _recheck_retained_path(audit_root, descriptor, identity)
        return population
    finally:
        os.close(descriptor)


__all__ = (
    "AuditPopulationAttachmentV1",
    "AuditPopulationRecordV1",
    "BenchmarkProviderEvidenceProjectionV1",
    "ProviderEvidenceIndexV1",
    "PublicBenchmarkCacheEvidenceV1",
    "RequestedReturnedModelEvidenceV1",
    "VerifiedAuditPopulationV1",
    "VerifiedBenchmarkProviderEvidenceV1",
    "build_audit_population",
    "compute_requested_returned_model_source_sha256",
    "load_provider_evidence_index",
    "load_verified_audit_population",
    "load_verified_benchmark_provider_evidence",
    "write_audit_population",
    "write_provider_evidence_index",
)
