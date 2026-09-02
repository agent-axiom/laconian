"""Campaign-neutral sealed generation context and evidence-layer indexes."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal, Self, TypeAlias, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from laconian_eval.benchmark.attachments import (
    CanonicalJSONV1Error,
    canonical_json_v1,
    parse_canonical_json_v1,
)
from laconian_eval.benchmark.protocol_review import (
    AuditReviewerRegistryV1,
    GitObjectId,
    ProtocolReviewerRegistryV1,
    ProtocolReviewRoleV1,
    VerifiedProtocolAttestationV1,
    compute_audit_reviewer_registry_sha256,
    compute_protocol_attestations_root,
    compute_protocol_reviewer_registry_sha256,
)
from laconian_eval.capsule.attempts import AttemptErrorV2, AttemptUsageV2, RawAttemptV2
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_jsonl,
    sha256_bytes,
    stable_digest,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.manifest_models import (
    ComparisonV2,
    PriceSourceEvidenceV1,
    ProtocolScopeV2,
    ResolvedCapsuleDeclarationsV2,
    ResolvedDatasetV2,
    ResolvedManifestV2,
    ResolvedPriceSnapshotV1,
    ResolvedProtocolBindingV2,
)
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.schema import (
    BoundedNonBlankString,
    CapsuleModel,
    RelativePosixPath,
    Sha256,
)
from laconian_eval.capsule.scorable import HardCheckV2, ScoredAttemptV2, project_scored_attempts
from laconian_eval.capsule.seal_models import (
    SealDisclosuresV1,
    SealFileV1,
    SealV1,
    seal_bytes,
)
from laconian_eval.capsule.sidecars import (
    ScoredCapsuleSidecarV2,
    VerifiedScoredCapsuleV2,
    load_verified_scored_capsule,
)
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import HardConstraints, ResponseCase, SemanticRubric

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_LAYER_DIRECTORY = {
    "generation": "generation",
    "hard-score": "hard-score",
    "judge-request": "judge-requests",
    "judge": "judge",
}
_LAYER_PREFIX = {kind: f"{directory}/" for kind, directory in _LAYER_DIRECTORY.items()}
_RETAINED_ATTACHMENT_MAX_BYTES = RESOURCE_LIMITS_V1.mutable_capsule_bytes
_SCORED_SIDECAR_DIGEST_DOMAIN = "laconian-scored-capsule-sidecar-v2"
_MAPPING_PROXY_TYPE: type[object] = type(MappingProxyType({}))
_OWNER_TREE_ENTRY_CEILING = (
    RESOURCE_LIMITS_V1.dependency_files + 2 * RESOURCE_LIMITS_V1.case_records + 64
)

LayerKindV1: TypeAlias = Literal["generation", "hard-score", "judge-request", "judge"]
LayerOrdinal: TypeAlias = Annotated[int, Field(strict=True, ge=0, lt=36)]
_ModelT = TypeVar("_ModelT", bound=BaseModel)


class _StrictFrozenModel(CapsuleModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        validate_default=True,
    )


@dataclass(frozen=True, slots=True)
class _FilesystemIdentity:
    device: int
    inode: int
    mode: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True, slots=True)
class _ReconstructedScoredSidecar:
    sidecar_bytes: bytes
    capsule_sha256: str
    generation_model: str
    scenarios: frozenset[str]


def _filesystem_identity(metadata: os.stat_result) -> _FilesystemIdentity:
    return _FilesystemIdentity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=metadata.st_mode,
        links=metadata.st_nlink,
        size=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
        changed_ns=metadata.st_ctime_ns,
    )


def _required_open_flags(*names: str) -> int:
    flags = 0
    for name in names:
        value = getattr(os, name, None)
        if type(value) is not int:
            raise ValueError(f"filesystem lacks required {name} support")
        flags |= value
    return flags


def _open_retained_directory(path: Path) -> tuple[int, _FilesystemIdentity]:
    descriptor: int | None = None
    try:
        if ".." in path.parts:
            raise ValueError("retained root path must not contain an alias component")
        descriptor = open_directory_no_follow(path)
        opened = _filesystem_identity(os.fstat(descriptor))
        if not stat.S_ISDIR(opened.mode):
            raise ValueError("retained root must be one non-symlink directory")
        return descriptor, opened
    except ValueError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("retained root must not contain a filesystem alias") from error


def _recheck_retained_path(
    path: Path,
    descriptor: int,
    expected: _FilesystemIdentity,
) -> None:
    probe: int | None = None
    try:
        probe = open_directory_no_follow(path)
        if (
            _filesystem_identity(os.fstat(descriptor)) != expected
            or _filesystem_identity(os.fstat(probe)) != expected
        ):
            raise ValueError("retained filesystem identity changed")
    except ValueError:
        raise
    except OSError as error:
        raise ValueError("retained filesystem identity changed") from error
    finally:
        if probe is not None:
            os.close(probe)


def _read_descriptor_bytes(descriptor: int, *, limit: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            raise ValueError("canonical attachment exceeds resource limit")
        chunks.append(chunk)


def _relative_components(path: str) -> tuple[str, ...]:
    if type(path) is not str or not path or path.startswith(("/", "\\")) or "\\" in path:
        raise ValueError("retained child path must be canonical relative POSIX")
    components = tuple(path.split("/"))
    if any(component in ("", ".", "..") for component in components):
        raise ValueError("retained child path must be canonical relative POSIX")
    return components


def _directory_open_flags() -> int:
    return os.O_RDONLY | _required_open_flags("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")


@contextmanager
def _open_relative_parent(
    root_descriptor: int,
    relative_path: str,
) -> Iterator[tuple[int, str]]:
    components = _relative_components(relative_path)
    current = os.dup(root_descriptor)
    try:
        for component in components[:-1]:
            try:
                child = os.open(component, _directory_open_flags(), dir_fd=current)
            except OSError as error:
                raise ValueError("retained child path contains an unsafe directory") from error
            previous = current
            current = child
            os.close(previous)
        yield current, components[-1]
    finally:
        os.close(current)


@contextmanager
def _open_relative_directory(root_descriptor: int, relative_path: str) -> Iterator[int]:
    with _open_relative_parent(root_descriptor, relative_path) as (parent, name):
        try:
            descriptor = os.open(name, _directory_open_flags(), dir_fd=parent)
        except OSError as error:
            raise ValueError("retained child directory is missing or unsafe") from error
        try:
            yield descriptor
        finally:
            os.close(descriptor)


def _stable_regular_file_snapshot(
    root_descriptor: int,
    relative_path: str,
) -> tuple[bytes, _FilesystemIdentity]:
    with _open_relative_parent(root_descriptor, relative_path) as (parent, name):
        try:
            visible = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except OSError as error:
            raise ValueError("canonical attachment path is missing or unsafe") from error
        if (
            stat.S_ISLNK(visible.st_mode)
            or not stat.S_ISREG(visible.st_mode)
            or visible.st_nlink != 1
        ):
            raise ValueError("canonical attachment path must be one regular file")
        if visible.st_size > _RETAINED_ATTACHMENT_MAX_BYTES:
            raise ValueError("canonical attachment exceeds resource limit")
        flags = os.O_RDONLY | _required_open_flags("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
        try:
            descriptor = os.open(name, flags, dir_fd=parent)
        except OSError as error:
            raise ValueError("canonical attachment path is missing or unsafe") from error
        expected = _filesystem_identity(visible)
        try:
            if _filesystem_identity(os.fstat(descriptor)) != expected:
                raise ValueError("canonical attachment identity changed while opening")
            data = _read_descriptor_bytes(
                descriptor,
                limit=_RETAINED_ATTACHMENT_MAX_BYTES,
            )
            try:
                visible_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except OSError as error:
                raise ValueError("canonical attachment identity changed while reading") from error
            if (
                _filesystem_identity(os.fstat(descriptor)) != expected
                or _filesystem_identity(visible_after) != expected
            ):
                raise ValueError("canonical attachment identity changed while reading")
            return data, expected
        finally:
            os.close(descriptor)


def _stable_directory_identity(root_descriptor: int, relative_path: str) -> _FilesystemIdentity:
    with _open_relative_directory(root_descriptor, relative_path) as descriptor:
        identity = _filesystem_identity(os.fstat(descriptor))
        if not stat.S_ISDIR(identity.mode):
            raise ValueError("canonical attachment directory is unsafe")
        return identity


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(descriptor, view)
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError("short attachment write")
        view = view[written:]


def _write_attachment_at(
    root_descriptor: int,
    relative_path: str,
    payload: Mapping[str, object],
) -> None:
    encoded = canonical_json_v1(dict(payload)) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _required_open_flags("O_NOFOLLOW", "O_CLOEXEC")
    with _open_relative_parent(root_descriptor, relative_path) as (parent, name):
        descriptor = os.open(name, flags, 0o600, dir_fd=parent)
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(parent)


def _ensure_layer_directory(root_descriptor: int, layer_directory: str) -> None:
    try:
        os.mkdir(layer_directory, 0o700, dir_fd=root_descriptor)
    except FileExistsError:
        pass
    except OSError as error:
        raise ValueError("layer directory could not be created safely") from error
    with _open_relative_directory(root_descriptor, layer_directory):
        return


class GenerationLayerRootMemberV1(_StrictFrozenModel):
    member_kind: Literal["generation"]
    ordinal: LayerOrdinal
    generation_model: BoundedNonBlankString
    scenario_uid: Sha256
    capsule_relative_path: RelativePosixPath
    generation_capsule_sha256: Sha256
    scored_sidecar_relative_path: RelativePosixPath
    scored_sidecar_sha256: Sha256


class AttachmentLayerRootMemberV1(_StrictFrozenModel):
    member_kind: Literal["hard-score", "judge-request", "judge"]
    ordinal: LayerOrdinal
    generation_model: BoundedNonBlankString
    scenario_uid: Sha256
    relative_path: RelativePosixPath
    attachment_sha256: Sha256


LayerRootMemberV1: TypeAlias = Annotated[
    GenerationLayerRootMemberV1 | AttachmentLayerRootMemberV1,
    Field(discriminator="member_kind"),
]


class LayerRootIndexV1(_StrictFrozenModel):
    schema_version: Literal["benchmark-layer-root-index-v1"]
    layer_kind: LayerKindV1
    campaign_id: BoundedNonBlankString
    members: tuple[LayerRootMemberV1, ...] = Field(min_length=36, max_length=36)
    layer_root_index_sha256: Sha256

    @model_validator(mode="after")
    def validate_closed_layer_index(self) -> Self:
        if tuple(member.ordinal for member in self.members) != tuple(range(36)):
            raise ValueError("layer members require ordinals 0..35")
        keys = tuple(
            (member.generation_model.encode("utf-8"), bytes.fromhex(member.scenario_uid))
            for member in self.members
        )
        if keys != tuple(sorted(keys)) or len(set(keys)) != 36:
            raise ValueError("layer members require unique canonical model/scenario order")
        if any(member.member_kind != self.layer_kind for member in self.members):
            raise ValueError("layer member kind mismatch")
        paths = tuple(
            path
            for member in self.members
            for path in (
                (member.capsule_relative_path, member.scored_sidecar_relative_path)
                if isinstance(member, GenerationLayerRootMemberV1)
                else (member.relative_path,)
            )
        )
        if len(set(paths)) != len(paths):
            raise ValueError("layer paths must be unique")
        expected_prefix = _LAYER_PREFIX[self.layer_kind]
        if any(not path.startswith(expected_prefix) for path in paths):
            raise ValueError("layer member path is outside its fixed subtree")
        expected = stable_digest(
            "laconian-benchmark-layer-root-index-v1",
            self.model_dump(mode="json", exclude={"layer_root_index_sha256"}),
        )
        if self.layer_root_index_sha256 != expected:
            raise ValueError("layer root index self digest mismatch")
        return self


class BenchmarkProtocolBindingsV1(_StrictFrozenModel):
    """The single immutable protocol projection repeated by downstream attachments."""

    campaign_registry_sha256: Sha256
    protocol_attestation_tag_binding_sha256: Sha256
    protocol_attestation_bundle_sha256: Sha256
    protocol_review_object_archive_sha256: Sha256
    object_closure_root: Sha256
    audit_reviewer_registry_sha256: Sha256
    protocol_reviewer_registry_sha256: Sha256
    protocol_attestations_root: Sha256
    hard_scorer_source_sha256: Sha256
    hard_score_protocol_sha256: Sha256
    judge_protocol_sha256: Sha256
    judge_prompt_sha256: Sha256
    judge_schema_sha256: Sha256
    corpus_case_root: Sha256
    estimand_protocol_sha256: Sha256
    statistical_protocol_sha256: Sha256
    audit_protocol_sha256: Sha256
    bootstrap_protocol_sha256: Sha256
    outcome_classification_protocol_sha256: Sha256
    false_fail_sensitivity_protocol_sha256: Sha256
    audit_sampling_protocol_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256
    audit_adjudication_protocol_sha256: Sha256
    workflow_root: Sha256


class GenerationContextIndexV1(_StrictFrozenModel):
    schema_version: Literal["benchmark-generation-context-index-v1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    protocol_attestation_tag_binding_sha256: Sha256
    protocol_attestation_bundle_sha256: Sha256
    protocol_review_object_archive_sha256: Sha256
    object_closure_root: Sha256
    audit_reviewer_registry_sha256: Sha256
    protocol_reviewer_registry_sha256: Sha256
    protocol_attestations_root: Sha256
    campaign_seed: Sha256
    campaign_seed_sha256: Sha256
    input_tag_commit: GitObjectId
    hard_scorer_source_sha256: Sha256
    hard_score_protocol_sha256: Sha256
    judge_protocol_sha256: Sha256
    judge_prompt_sha256: Sha256
    judge_schema_sha256: Sha256
    judge_requested_service_tier: Literal["default"]
    judge_service_tier_wire_field: Literal["service_tier"]
    corpus_case_root: Sha256
    statistical_protocol_sha256: Sha256
    audit_protocol_sha256: Sha256
    estimand_protocol_sha256: Sha256
    bootstrap_protocol_sha256: Sha256
    outcome_classification_protocol_sha256: Sha256
    false_fail_sensitivity_protocol_sha256: Sha256
    audit_sampling_protocol_sha256: Sha256
    audit_commit_reveal_protocol_sha256: Sha256
    audit_adjudication_protocol_sha256: Sha256
    workflow_root: Sha256
    audit_reviewer_registry: AuditReviewerRegistryV1
    protocol_reviewer_registry: ProtocolReviewerRegistryV1
    protocol_attestations: tuple[
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
        VerifiedProtocolAttestationV1,
    ]
    generation_root_index_sha256: Sha256
    provider_projection_root: Sha256
    ordered_generation_capsule_sha256s: tuple[Sha256, ...] = Field(
        min_length=36,
        max_length=36,
    )
    generation_context_index_sha256: Sha256

    @model_validator(mode="after")
    def validate_closed_generation_context(self) -> Self:
        expected_seed_sha256 = stable_digest(
            "laconian-campaign-seed-v1",
            {
                "schema_version": "1",
                "algorithm": "public-hex-seed-v1",
                "campaign_seed": self.campaign_seed,
            },
        )
        if self.campaign_seed_sha256 != expected_seed_sha256:
            raise ValueError("generation context campaign seed digest mismatch")
        if len(set(self.ordered_generation_capsule_sha256s)) != 36:
            raise ValueError("generation context requires 36 unique capsule parents")

        audit_reviewers = self.audit_reviewer_registry.reviewers
        audit_keys = tuple(reviewer.reviewer_id.encode("utf-8") for reviewer in audit_reviewers)
        if (
            audit_keys != tuple(sorted(audit_keys))
            or len(set(audit_keys)) != 2
            or len({reviewer.reviewer_numeric_account_id for reviewer in audit_reviewers}) != 2
            or len({reviewer.reviewer_login for reviewer in audit_reviewers}) != 2
        ):
            raise ValueError("generation context requires two ordered distinct reviewers")
        recomputed_audit_registry = compute_audit_reviewer_registry_sha256(audit_reviewers)
        if (
            self.audit_reviewer_registry.audit_reviewer_registry_sha256 != recomputed_audit_registry
            or self.audit_reviewer_registry_sha256 != recomputed_audit_registry
        ):
            raise ValueError("generation context reviewer registry digest mismatch")

        expected_roles: tuple[ProtocolReviewRoleV1, ...] = (
            "statistical_method",
            "blind_judge_audit_protocol",
            "security_evidence",
        )
        protocol_reviewers = self.protocol_reviewer_registry.reviewers
        if tuple(item.statement.role for item in self.protocol_attestations) != expected_roles:
            raise ValueError("generation context requires the ordered protocol review roles")
        if tuple(reviewer.role for reviewer in protocol_reviewers) != expected_roles:
            raise ValueError("generation context protocol reviewer role order mismatch")
        if (
            len({item.attestation_sha256 for item in self.protocol_attestations}) != 3
            or len({reviewer.reviewer_numeric_account_id for reviewer in protocol_reviewers}) != 3
            or len({reviewer.reviewer_login for reviewer in protocol_reviewers}) != 3
        ):
            raise ValueError("generation context requires three distinct protocol reviewers")
        recomputed_protocol_registry = compute_protocol_reviewer_registry_sha256(protocol_reviewers)
        if (
            self.protocol_reviewer_registry.protocol_reviewer_registry_sha256
            != recomputed_protocol_registry
            or self.protocol_reviewer_registry_sha256 != recomputed_protocol_registry
        ):
            raise ValueError("generation context protocol reviewer registry digest mismatch")

        shared_statement_authority: tuple[str, str, str, str, str] | None = None
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
                or statement.protocol_registry_sha256 != recomputed_protocol_registry
                or statement.workflow_root != self.workflow_root
                or statement.peeled_c0_oid != self.input_tag_commit
            ):
                raise ValueError("generation context protocol attestation identity mismatch")
            statement_authority = (
                statement.input_tag_ref,
                statement.input_tag_oid,
                statement.input_tag_object_sha256,
                statement.peeled_c0_oid,
                statement.peeled_c0_sha256,
            )
            if shared_statement_authority is None:
                shared_statement_authority = statement_authority
            elif statement_authority != shared_statement_authority:
                raise ValueError("generation context protocol attestation authority mismatch")
            signature_fingerprint = getattr(signature, "fingerprint", None)
            if reviewer.verification_mode != "github_verified_commit" and (
                signature_fingerprint != reviewer.signing_fingerprint
            ):
                raise ValueError("generation context protocol signature fingerprint mismatch")

        if self.protocol_attestations_root != compute_protocol_attestations_root(
            self.protocol_attestations
        ):
            raise ValueError("generation context protocol review root mismatch")
        self._validate_attested_protocol_values()
        expected = stable_digest(
            "laconian-benchmark-generation-context-index-v1",
            self.model_dump(mode="json", exclude={"generation_context_index_sha256"}),
        )
        if self.generation_context_index_sha256 != expected:
            raise ValueError("generation context self digest mismatch")
        return self

    def _validate_attested_protocol_values(self) -> None:
        context_values = {
            "corpus_case_root": self.corpus_case_root,
            "estimand_protocol_sha256": self.estimand_protocol_sha256,
            "statistical_protocol_sha256": self.statistical_protocol_sha256,
            "bootstrap_protocol_sha256": self.bootstrap_protocol_sha256,
            "outcome_classification_protocol_sha256": self.outcome_classification_protocol_sha256,
            "false_fail_sensitivity_protocol_sha256": (self.false_fail_sensitivity_protocol_sha256),
            "hard_score_protocol_sha256": self.hard_score_protocol_sha256,
            "judge_prompt_sha256": self.judge_prompt_sha256,
            "judge_schema_sha256": self.judge_schema_sha256,
            "audit_sampling_protocol_sha256": self.audit_sampling_protocol_sha256,
            "audit_commit_reveal_protocol_sha256": self.audit_commit_reveal_protocol_sha256,
            "audit_adjudication_protocol_sha256": self.audit_adjudication_protocol_sha256,
        }
        subjects: dict[str, str] = {
            subject.kind: subject.sha256
            for attestation in self.protocol_attestations
            for subject in attestation.statement.subjects
        }
        if any(subjects.get(kind) != value for kind, value in context_values.items()):
            raise ValueError("generation context attested protocol digest mismatch")


def protocol_bindings_from_context(
    context: GenerationContextIndexV1,
) -> BenchmarkProtocolBindingsV1:
    checked = _revalidate_model(GenerationContextIndexV1, context)
    return BenchmarkProtocolBindingsV1.model_validate(
        {name: getattr(checked, name) for name in BenchmarkProtocolBindingsV1.model_fields}
    )


class GenerationContextExpectationV1(_StrictFrozenModel):
    schema_version: Literal["benchmark-generation-context-expectation-v1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    audit_reviewer_registry_sha256: Sha256
    protocol_reviewer_registry_sha256: Sha256
    protocol_attestations_root: Sha256
    predecessor_authority_root_sha256: Sha256
    generation_layer_root: Sha256
    expected_context_index_sha256: Sha256
    workflow_root: Sha256
    generation_context_expectation_sha256: Sha256

    @model_validator(mode="after")
    def validate_self_digest(self) -> Self:
        expected = stable_digest(
            "laconian-benchmark-generation-context-expectation-v1",
            self.model_dump(
                mode="json",
                exclude={"generation_context_expectation_sha256"},
            ),
        )
        if self.generation_context_expectation_sha256 != expected:
            raise ValueError("generation context expectation self digest mismatch")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedGenerationContextExpectationV1:
    expectation: GenerationContextExpectationV1
    bound_generation_complete_authority_root_sha256: str

    def __post_init__(self) -> None:
        expectation = _revalidate_model(GenerationContextExpectationV1, self.expectation)
        if (
            type(self.bound_generation_complete_authority_root_sha256) is not str
            or _SHA256_PATTERN.fullmatch(self.bound_generation_complete_authority_root_sha256)
            is None
        ):
            raise ValueError("bound generation-complete authority root must be lowercase SHA-256")
        object.__setattr__(self, "expectation", expectation)


@dataclass(frozen=True, slots=True)
class VerifiedGenerationContextIndexV1:
    expectation: VerifiedGenerationContextExpectationV1
    index: GenerationContextIndexV1
    root_index: LayerRootIndexV1
    generation_evidence: tuple[VerifiedScoredCapsuleV2, ...]

    def __post_init__(self) -> None:
        expectation = _revalidate_verified_expectation(self.expectation)
        index = _revalidate_model(GenerationContextIndexV1, self.index)
        root_index = _revalidate_model(LayerRootIndexV1, self.root_index)
        if type(self.generation_evidence) is not tuple or len(self.generation_evidence) != 36:
            raise ValueError("verified generation context requires 36 scored capsules")
        if any(type(item) is not VerifiedScoredCapsuleV2 for item in self.generation_evidence):
            raise ValueError("verified generation context contains unverified scored evidence")
        _validate_expectation_index(expectation, index, root_index)
        _validate_evidence_members(root_index, self.generation_evidence)
        object.__setattr__(self, "expectation", expectation)
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "root_index", root_index)


def _revalidate_model(model_type: type[_ModelT], value: object) -> _ModelT:
    if type(value) is not model_type:
        raise TypeError(f"expected exact {model_type.__name__}")
    payload = model_type.model_dump(value, mode="python", round_trip=True, warnings=False)
    return model_type.model_validate(payload)


def _revalidate_verified_expectation(
    value: VerifiedGenerationContextExpectationV1,
) -> VerifiedGenerationContextExpectationV1:
    if type(value) is not VerifiedGenerationContextExpectationV1:
        raise TypeError("expected verified generation context expectation")
    return VerifiedGenerationContextExpectationV1(
        expectation=value.expectation,
        bound_generation_complete_authority_root_sha256=(
            value.bound_generation_complete_authority_root_sha256
        ),
    )


def _validate_expectation_index(
    verified: VerifiedGenerationContextExpectationV1,
    index: GenerationContextIndexV1,
    root_index: LayerRootIndexV1,
) -> None:
    expectation = verified.expectation
    if (
        index.generation_context_index_sha256 != expectation.expected_context_index_sha256
        or index.campaign_id != expectation.campaign_id
        or index.campaign_registry_sha256 != expectation.campaign_registry_sha256
        or index.audit_reviewer_registry_sha256 != expectation.audit_reviewer_registry_sha256
        or index.protocol_reviewer_registry_sha256 != expectation.protocol_reviewer_registry_sha256
        or index.protocol_attestations_root != expectation.protocol_attestations_root
        or index.workflow_root != expectation.workflow_root
        or index.generation_root_index_sha256 != expectation.generation_layer_root
        or root_index.layer_root_index_sha256 != expectation.generation_layer_root
        or root_index.layer_kind != "generation"
        or root_index.campaign_id != expectation.campaign_id
    ):
        raise ValueError("generation context does not match verified expectation")
    generation_members = cast(tuple[GenerationLayerRootMemberV1, ...], root_index.members)
    if tuple(member.generation_capsule_sha256 for member in generation_members) != (
        index.ordered_generation_capsule_sha256s
    ):
        raise ValueError("generation context capsule vector mismatch")


def _preflight_tuple(value: object, *, maximum: int) -> tuple[object, ...]:
    if type(value) is not tuple or len(value) > maximum:
        raise TypeError
    return cast(tuple[object, ...], value)


def _preflight_seal_shell(value: object) -> SealV1:
    if type(value) is not SealV1:
        raise TypeError
    files = _preflight_tuple(value.files, maximum=_OWNER_TREE_ENTRY_CEILING)
    missing_ids = _preflight_tuple(
        value.missing_plan_item_ids,
        maximum=RESOURCE_LIMITS_V1.plan_rows,
    )
    blockers = _preflight_tuple(
        value.operational_blocker_codes,
        maximum=RESOURCE_LIMITS_V1.plan_rows,
    )
    disclosures = value.disclosures
    if type(disclosures) is not SealDisclosuresV1 or any(
        type(item) is not SealFileV1 for item in files
    ):
        raise TypeError
    _preflight_tuple(disclosures.returned_models, maximum=RESOURCE_LIMITS_V1.raw_rows)
    for vector in (disclosures.dataset_ids, disclosures.protocol_binding_ids):
        _preflight_tuple(vector, maximum=RESOURCE_LIMITS_V1.case_records)
    # Retain these local values so the shape checks happen before a model dump.
    del missing_ids, blockers
    return value


def _preflight_manifest_shell(value: object) -> ResolvedManifestV2:
    if type(value) is not ResolvedManifestV2:
        raise TypeError
    _preflight_tuple(value.case_files, maximum=RESOURCE_LIMITS_V1.case_records)
    _preflight_tuple(value.arms, maximum=4)
    capsule = value.capsule
    if type(capsule) is not ResolvedCapsuleDeclarationsV2:
        raise TypeError
    datasets = _preflight_tuple(capsule.datasets, maximum=RESOURCE_LIMITS_V1.case_records)
    comparisons = _preflight_tuple(capsule.comparisons, maximum=6)
    bindings = _preflight_tuple(
        capsule.protocol_bindings,
        maximum=RESOURCE_LIMITS_V1.case_records,
    )
    if any(type(item) is not ResolvedDatasetV2 for item in datasets) or any(
        type(item) is not ComparisonV2 for item in comparisons
    ) or any(type(item) is not ResolvedProtocolBindingV2 for item in bindings):
        raise TypeError
    ordinal_total = 0
    for dataset in datasets:
        assert type(dataset) is ResolvedDatasetV2
        ordinals = _preflight_tuple(
            dataset.case_file_ordinals,
            maximum=RESOURCE_LIMITS_V1.case_records,
        )
        ordinal_total += len(ordinals)
        if ordinal_total > RESOURCE_LIMITS_V1.case_records:
            raise TypeError
    for binding in bindings:
        assert type(binding) is ResolvedProtocolBindingV2
        scope = binding.scope
        if type(scope) is not ProtocolScopeV2:
            raise TypeError
        _preflight_tuple(scope.dataset_ids, maximum=RESOURCE_LIMITS_V1.case_records)
        _preflight_tuple(scope.comparison_ids, maximum=RESOURCE_LIMITS_V1.case_records)
        _preflight_tuple(binding.applies_at, maximum=4)
    price = value.price_snapshot
    if price is not None:
        if type(price) is not ResolvedPriceSnapshotV1:
            raise TypeError
        evidence = _preflight_tuple(price.source_evidence, maximum=5)
        if any(type(item) is not PriceSourceEvidenceV1 for item in evidence):
            raise TypeError
    return value


def _preflight_raw_attempt_shell(value: object) -> RawAttemptV2:
    if (
        type(value) is not RawAttemptV2
        or type(value.usage) is not AttemptUsageV2
        or (value.error is not None and type(value.error) is not AttemptErrorV2)
    ):
        raise TypeError
    return value


def _preflight_scored_attempt_shell(value: object) -> ScoredAttemptV2:
    if type(value) is not ScoredAttemptV2:
        raise TypeError
    checks = _preflight_tuple(value.checks, maximum=RESOURCE_LIMITS_V1.case_file_bytes)
    if any(type(check) is not HardCheckV2 for check in checks):
        raise TypeError
    _preflight_raw_attempt_shell(value.raw)
    return value


def _preflight_response_case_shell(value: object) -> ResponseCase:
    if type(value) is not ResponseCase:
        raise TypeError
    constraints = value.hard_constraints
    rubric = value.semantic_rubric
    if type(constraints) is not HardConstraints or type(rubric) is not SemanticRubric:
        raise TypeError
    for vector in (
        constraints.required_literals,
        constraints.forbidden_literals,
        constraints.required_json_keys,
        constraints.required_yaml_keys,
        rubric.required_facts,
    ):
        _preflight_tuple(vector, maximum=RESOURCE_LIMITS_V1.case_file_bytes)
    return value


def _reconstruct_scored_sidecar_bytes(evidence: object) -> _ReconstructedScoredSidecar:
    """Rebuild the canonical scored-sidecar bytes from independently revalidated evidence."""

    if type(evidence) is not VerifiedScoredCapsuleV2:
        raise ValueError("generation evidence must have the exact verified type")
    try:
        # Do not iterate or materialize attacker-forged exact-type fields until
        # their closed container types and owner bounds are established.
        if (
            type(evidence.plan) is not tuple
            or type(evidence.scored_attempts) is not tuple
            or type(evidence.cases_by_uid) is not _MAPPING_PROXY_TYPE
            or not evidence.plan
            or len(evidence.plan) > RESOURCE_LIMITS_V1.plan_rows
            or len(evidence.scored_attempts) > RESOURCE_LIMITS_V1.plan_rows
            or len(evidence.cases_by_uid) > RESOURCE_LIMITS_V1.case_records
        ):
            raise TypeError
        seal = _revalidate_model(SealV1, _preflight_seal_shell(evidence.seal))
        manifest = _revalidate_model(
            ResolvedManifestV2,
            _preflight_manifest_shell(evidence.manifest),
        )
        plan = tuple(_revalidate_model(PlanRowV1, row) for row in evidence.plan)
        scored_attempts = tuple(
            _revalidate_model(ScoredAttemptV2, _preflight_scored_attempt_shell(row))
            for row in evidence.scored_attempts
        )
        cases: dict[str, ResponseCase] = {}
        raw_cases = cast(Mapping[object, object], evidence.cases_by_uid)
        expected_case_count = len(raw_cases)
        case_items = iter(raw_cases.items())
        for _ in range(expected_case_count):
            try:
                raw_key, raw_case = next(case_items)
            except StopIteration:
                raise TypeError from None
            if type(raw_key) is not str:
                raise TypeError
            cases[raw_key] = _revalidate_model(
                ResponseCase,
                _preflight_response_case_shell(raw_case),
            )
        if len(cases) != expected_case_count:
            raise TypeError
        try:
            next(case_items)
        except StopIteration:
            pass
        else:
            raise TypeError
        manifest_bytes = canonical_json(
            ResolvedManifestV2.model_dump(
                manifest,
                mode="json",
                round_trip=True,
                warnings=False,
            )
        )
        plan_bytes = canonical_jsonl(
            PlanRowV1.model_dump(
                row,
                mode="json",
                round_trip=True,
                warnings=False,
            )
            for row in plan
        )
        seal_files = {item.path: item for item in seal.files}
        required_file_bytes = {
            "manifest.json": manifest_bytes,
            "plan.jsonl": plan_bytes,
        }
        raw_file = seal_files.get("raw.jsonl")
        if (
            not plan
            or len(plan) != len(scored_attempts)
            or seal.generation_status != "complete"
            or seal.structural_integrity != "valid"
            or evidence.capsule_sha256 != sha256_bytes(seal_bytes(seal))
            or any(
                path not in seal_files
                or seal_files[path].sha256 != sha256_bytes(data)
                or seal_files[path].byte_length != len(data)
                for path, data in required_file_bytes.items()
            )
            # `scored_attempts` contains only terminal projection rows.  The
            # sealed raw journal can additionally contain nonterminal retries,
            # so its hash/size are authority from the seal rather than a value
            # we can reproduce from that projection.
            or raw_file is None
            or raw_file.byte_length < 0
            or "case-index.jsonl" not in seal_files
            or evidence.manifest_sha256 != seal_files["manifest.json"].sha256
            or evidence.plan_sha256 != seal_files["plan.jsonl"].sha256
            or evidence.manifest_sha256 != sha256_bytes(manifest_bytes)
            or evidence.plan_sha256 != sha256_bytes(plan_bytes)
            or tuple(row.ordinal for row in plan) != tuple(range(len(plan)))
            or tuple(row.plan_item_id for row in plan)
            != tuple(row.plan_item_id for row in scored_attempts)
        ):
            raise TypeError
        ordered_case_uids = tuple(dict.fromkeys(row.case_uid for row in plan))
        if tuple(cases) != ordered_case_uids:
            raise TypeError
        for row in plan:
            case = cases[row.case_uid]
            if (
                case.id != row.case_id
                or case.locale != row.locale
                or response_case_sha256(case) != row.case_definition_sha256
                or sha256_bytes(case.prompt.encode("utf-8", errors="strict"))
                != row.prompt_sha256
            ):
                raise TypeError
        if project_scored_attempts(
            plan=plan,
            raw_attempts=tuple(row.raw for row in scored_attempts),
            cases_by_uid=cases,
        ) != scored_attempts:
            raise TypeError
        payload: dict[str, object] = {
            "sidecar_schema_version": "2",
            "scoring_algorithm_version": "laconian-deterministic-hard-v2",
            "capsule_sha256": evidence.capsule_sha256,
            "manifest_sha256": evidence.manifest_sha256,
            "case_index_sha256": seal_files["case-index.jsonl"].sha256,
            "plan_sha256": evidence.plan_sha256,
            "raw_sha256": seal_files["raw.jsonl"].sha256,
            "ordered_plan_item_ids": tuple(row.plan_item_id for row in plan),
            "scored_attempts": [
                ScoredAttemptV2.model_dump(
                    row,
                    mode="json",
                    round_trip=True,
                    warnings=False,
                )
                for row in scored_attempts
            ],
        }
        payload["sidecar_sha256"] = stable_digest(_SCORED_SIDECAR_DIGEST_DOMAIN, payload)
        sidecar = ScoredCapsuleSidecarV2.model_validate(payload)
        return _ReconstructedScoredSidecar(
            sidecar_bytes=canonical_json(
                ScoredCapsuleSidecarV2.model_dump(
                    sidecar,
                    mode="json",
                    round_trip=True,
                    warnings=False,
                )
            ),
            capsule_sha256=evidence.capsule_sha256,
            generation_model=manifest.provider.model,
            scenarios=frozenset(row.scenario_uid for row in plan),
        )
    except Exception as error:
        raise ValueError("generation evidence failed independent sidecar reconstruction") from error


def _validate_evidence_members(
    root_index: LayerRootIndexV1,
    evidence: tuple[VerifiedScoredCapsuleV2, ...],
) -> None:
    for member, scored in zip(root_index.members, evidence, strict=True):
        if type(member) is not GenerationLayerRootMemberV1:
            raise ValueError("generation root contains a non-generation member")
        reconstructed = _reconstruct_scored_sidecar_bytes(scored)
        if (
            reconstructed.capsule_sha256 != member.generation_capsule_sha256
            or reconstructed.generation_model != member.generation_model
            or reconstructed.scenarios != {member.scenario_uid}
        ):
            raise ValueError("generation evidence identity mismatch")
        if (
            hashlib.sha256(reconstructed.sidecar_bytes).hexdigest()
            != member.scored_sidecar_sha256
        ):
            raise ValueError("generation evidence sidecar binding mismatch")


def _canonical_payload_from_bytes(data: bytes) -> object:
    if not data.endswith(b"\n") or data.endswith(b"\n\n"):
        raise CanonicalJSONV1Error("canonical attachment requires exactly one terminal LF")
    return parse_canonical_json_v1(data[:-1])


def _canonical_payload_from_file(root_descriptor: int, relative_path: str) -> object:
    data, _ = _stable_regular_file_snapshot(root_descriptor, relative_path)
    return _canonical_payload_from_bytes(data)


def _layer_index_path(root: Path, kind: LayerKindV1) -> Path:
    return root / _LAYER_DIRECTORY[kind] / "index.json"


def _member_paths(index: LayerRootIndexV1) -> tuple[str, ...]:
    return tuple(
        path
        for member in index.members
        for path in (
            (member.capsule_relative_path, member.scored_sidecar_relative_path)
            if isinstance(member, GenerationLayerRootMemberV1)
            else (member.relative_path,)
        )
    )


def _validate_layer_tree(root_descriptor: int, index: LayerRootIndexV1) -> None:
    layer_directory = _LAYER_DIRECTORY[index.layer_kind]
    expected_paths = set(_member_paths(index))
    index_relative = f"{layer_directory}/index.json"
    expected_paths.add(index_relative)
    capsule_roots = {
        member.capsule_relative_path
        for member in index.members
        if isinstance(member, GenerationLayerRootMemberV1)
    }
    seen_inodes: set[tuple[int, int]] = set()
    retained_modes: dict[str, int] = {}

    def walk(descriptor: int, relative_directory: str) -> None:
        directory_identity = _filesystem_identity(os.fstat(descriptor))
        try:
            iterator = os.scandir(descriptor)
        except OSError as error:
            raise ValueError("layer tree could not be inspected safely") from error
        with iterator as entries:
            for entry in entries:
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as error:
                    raise ValueError("layer tree identity changed during validation") from error
                relative = f"{relative_directory}/{entry.name}"
                identity = _filesystem_identity(metadata)
                retained_modes[relative] = identity.mode
                if (
                    relative not in expected_paths
                    and not any(path.startswith(f"{relative}/") for path in expected_paths)
                    and not any(
                        relative == capsule or relative.startswith(f"{capsule}/")
                        for capsule in capsule_roots
                    )
                ):
                    raise ValueError("layer tree contains an unexpected path")
                inode = (metadata.st_dev, metadata.st_ino)
                if inode in seen_inodes:
                    raise ValueError("layer tree contains an inode alias")
                seen_inodes.add(inode)

                if stat.S_ISLNK(metadata.st_mode):
                    raise ValueError("layer tree contains a symbolic link")
                if stat.S_ISREG(metadata.st_mode):
                    if metadata.st_nlink != 1:
                        raise ValueError("layer tree contains an external inode alias")
                elif stat.S_ISDIR(metadata.st_mode):
                    try:
                        child = os.open(entry.name, _directory_open_flags(), dir_fd=descriptor)
                    except OSError as error:
                        raise ValueError("layer tree contains an unsafe directory") from error
                    try:
                        if _filesystem_identity(os.fstat(child)) != identity:
                            raise ValueError("layer tree identity changed while opening")
                        walk(child, relative)
                        try:
                            visible_after = os.stat(
                                entry.name,
                                dir_fd=descriptor,
                                follow_symlinks=False,
                            )
                        except OSError as error:
                            raise ValueError(
                                "layer tree identity changed during validation"
                            ) from error
                        if (
                            _filesystem_identity(os.fstat(child)) != identity
                            or _filesystem_identity(visible_after) != identity
                        ):
                            raise ValueError("layer tree identity changed during validation")
                    finally:
                        os.close(child)
                else:
                    raise ValueError("layer tree contains a non-regular member")

                try:
                    visible_after = os.stat(
                        entry.name,
                        dir_fd=descriptor,
                        follow_symlinks=False,
                    )
                except OSError as error:
                    raise ValueError("layer tree identity changed during validation") from error
                if _filesystem_identity(visible_after) != identity:
                    raise ValueError("layer tree identity changed during validation")
        if _filesystem_identity(os.fstat(descriptor)) != directory_identity:
            raise ValueError("layer tree identity changed during validation")

    with _open_relative_directory(root_descriptor, layer_directory) as layer_descriptor:
        layer_identity = _filesystem_identity(os.fstat(layer_descriptor))
        walk(layer_descriptor, layer_directory)
    with _open_relative_directory(root_descriptor, layer_directory) as layer_descriptor:
        if _filesystem_identity(os.fstat(layer_descriptor)) != layer_identity:
            raise ValueError("layer tree identity changed during validation")

    if expected_paths - retained_modes.keys():
        raise ValueError("layer tree is missing a declared path")
    for member in index.members:
        if isinstance(member, GenerationLayerRootMemberV1):
            if not stat.S_ISDIR(retained_modes[member.capsule_relative_path]) or not stat.S_ISREG(
                retained_modes[member.scored_sidecar_relative_path]
            ):
                raise ValueError("generation layer member path type mismatch")
        elif not stat.S_ISREG(retained_modes[member.relative_path]):
            raise ValueError("attachment layer member must be one regular file")


def _load_layer_root_index_at(
    root_descriptor: int,
    *,
    expected_kind: LayerKindV1,
) -> LayerRootIndexV1:
    index_path = f"{_LAYER_DIRECTORY[expected_kind]}/index.json"
    index_bytes, index_identity = _stable_regular_file_snapshot(
        root_descriptor,
        index_path,
    )
    parsed = _canonical_payload_from_bytes(index_bytes)
    index = LayerRootIndexV1.model_validate(parsed)
    if index.layer_kind != expected_kind:
        raise ValueError("layer index kind mismatch")
    _validate_layer_tree(root_descriptor, index)
    reloaded_bytes, reloaded_identity = _stable_regular_file_snapshot(root_descriptor, index_path)
    if reloaded_identity != index_identity or reloaded_bytes != index_bytes:
        raise ValueError("layer index identity changed during validation")
    return index


def write_layer_root_index(root: Path, index: LayerRootIndexV1) -> None:
    """Write the kind-specific fixed index.json canonically without replacement."""

    checked = _revalidate_model(LayerRootIndexV1, index)
    root_descriptor, _ = _open_retained_directory(root)
    try:
        layer_directory = _LAYER_DIRECTORY[checked.layer_kind]
        _ensure_layer_directory(root_descriptor, layer_directory)
        _write_attachment_at(
            root_descriptor,
            f"{layer_directory}/index.json",
            checked.model_dump(mode="json"),
        )
        _recheck_retained_path(
            root,
            root_descriptor,
            _filesystem_identity(os.fstat(root_descriptor)),
        )
    finally:
        os.close(root_descriptor)


def load_layer_root_index(root: Path, *, expected_kind: LayerKindV1) -> LayerRootIndexV1:
    """Load a fixed layer subtree, rejecting aliases, extras, and digest mismatches."""

    if expected_kind not in _LAYER_DIRECTORY:
        raise ValueError("unknown layer kind")
    root_descriptor, root_identity = _open_retained_directory(root)
    try:
        index = _load_layer_root_index_at(root_descriptor, expected_kind=expected_kind)
        _recheck_retained_path(root, root_descriptor, root_identity)
        return index
    finally:
        os.close(root_descriptor)


def write_generation_context_index(
    generation_index_path: Path,
    index: GenerationContextIndexV1,
) -> None:
    """No-replace write the canonical pre-judge generation context."""

    checked = _revalidate_model(GenerationContextIndexV1, index)
    if generation_index_path.name != "generation-context.json":
        raise ValueError("generation context path must use the fixed leaf name")
    parent = generation_index_path.parent
    parent_descriptor, _ = _open_retained_directory(parent)
    try:
        _write_attachment_at(
            parent_descriptor,
            "generation-context.json",
            checked.model_dump(mode="json"),
        )
        _recheck_retained_path(
            parent,
            parent_descriptor,
            _filesystem_identity(os.fstat(parent_descriptor)),
        )
    finally:
        os.close(parent_descriptor)


def load_verified_generation_context_index(
    *,
    generation_index_path: Path,
    generation_root: Path,
    expectation: VerifiedGenerationContextExpectationV1,
) -> VerifiedGenerationContextIndexV1:
    """Verify context against external authority and every retained capsule parent."""

    verified_expectation = _revalidate_verified_expectation(expectation)
    if generation_index_path != generation_root / "generation-context.json":
        raise ValueError("generation context path is not the fixed root child")
    root_descriptor, root_identity = _open_retained_directory(generation_root)
    try:
        parsed = _canonical_payload_from_file(root_descriptor, "generation-context.json")
        if not isinstance(parsed, dict):
            raise ValueError("generation context must be a canonical object")
        asserted_digest = parsed.get("generation_context_index_sha256")
        if asserted_digest != verified_expectation.expectation.expected_context_index_sha256:
            raise ValueError("generation context is not bound by the external expectation")
        index = GenerationContextIndexV1.model_validate(parsed)
        root_index = _load_layer_root_index_at(root_descriptor, expected_kind="generation")
        _validate_expectation_index(verified_expectation, index, root_index)

        with os.scandir(root_descriptor) as entries:
            root_children = {entry.name for entry in entries}
        if root_children != {"generation", "generation-context.json"}:
            raise ValueError("generation root contains an unexpected child")
        evidence: list[VerifiedScoredCapsuleV2] = []
        for member in root_index.members:
            if type(member) is not GenerationLayerRootMemberV1:
                raise ValueError("generation root contains a non-generation member")
            capsule_path = generation_root / member.capsule_relative_path
            sidecar_path = generation_root / member.scored_sidecar_relative_path
            capsule_identity = _stable_directory_identity(
                root_descriptor,
                member.capsule_relative_path,
            )
            sidecar_bytes, sidecar_identity = _stable_regular_file_snapshot(
                root_descriptor,
                member.scored_sidecar_relative_path,
            )
            if hashlib.sha256(sidecar_bytes).hexdigest() != member.scored_sidecar_sha256:
                raise ValueError("scored sidecar file hash mismatch")
            scored = load_verified_scored_capsule(capsule_path, sidecar_path)
            reloaded_sidecar_bytes, reloaded_sidecar_identity = _stable_regular_file_snapshot(
                root_descriptor,
                member.scored_sidecar_relative_path,
            )
            if (
                _stable_directory_identity(root_descriptor, member.capsule_relative_path)
                != capsule_identity
                or reloaded_sidecar_identity != sidecar_identity
                or reloaded_sidecar_bytes != sidecar_bytes
            ):
                raise ValueError("generation evidence identity changed while loading")
            evidence.append(scored)
        checked_evidence = tuple(evidence)
        _validate_evidence_members(root_index, checked_evidence)
        _recheck_retained_path(generation_root, root_descriptor, root_identity)
        return VerifiedGenerationContextIndexV1(
            expectation=verified_expectation,
            index=index,
            root_index=root_index,
            generation_evidence=checked_evidence,
        )
    finally:
        os.close(root_descriptor)


__all__ = (
    "AttachmentLayerRootMemberV1",
    "BenchmarkProtocolBindingsV1",
    "GenerationContextExpectationV1",
    "GenerationContextIndexV1",
    "GenerationLayerRootMemberV1",
    "LayerKindV1",
    "LayerRootIndexV1",
    "LayerRootMemberV1",
    "VerifiedGenerationContextExpectationV1",
    "VerifiedGenerationContextIndexV1",
    "load_layer_root_index",
    "load_verified_generation_context_index",
    "protocol_bindings_from_context",
    "write_generation_context_index",
    "write_layer_root_index",
)
