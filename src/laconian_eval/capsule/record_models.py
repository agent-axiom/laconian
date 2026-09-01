"""Strict static generated-record schemas for generation capsules."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Annotated, Literal, Self, TypeAlias
from uuid import UUID

from pydantic import BeforeValidator, Field, field_validator, model_validator

from laconian_eval.capsule.schema import (
    CONSOLE_LAUNCHER_TEMPLATE_SHA256,
    OPERATIONAL_BLOCKER_ORDER,
    UUID4,
    VERIFICATION_WARNING_ORDER,
    Arm,
    BoundedNonBlankString,
    CanonicalTimestamp,
    CapsuleModel,
    CaseCategory,
    CaseId,
    ClaimIntent,
    DatasetRole,
    DiagnosticString,
    FilesystemClass,
    GitObjectId,
    InputRole,
    LifecycleState,
    Locale,
    NormalizedDistributionName,
    OperationalBlocker,
    ProviderKind,
    RelativePosixPath,
    RunPurpose,
    ScenarioId,
    Sha256,
    StrictNonNegativeInt,
    StrictPositiveInt,
    StrictSigned64Int,
    TopLevelModuleName,
    VerificationErrorCode,
    VerificationWarning,
    VerifyStatus,
    require_fixed_order,
    require_unique,
    require_utf8_sorted_unique,
    validate_relative_posix_path,
)


def _exact_event_uuid(value: object) -> object:
    if type(value) not in (UUID, str):
        raise ValueError("event UUID must use an exact boundary type")
    return value


def _exact_event_datetime(value: object) -> object:
    if type(value) not in (datetime, str):
        raise ValueError("event timestamp must use an exact boundary type")
    return value


def _control_free_event_text(value: object) -> object:
    if type(value) is not str:
        raise ValueError("event text must be a string")
    if any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value):
        raise ValueError("event text must be control-free")
    return value


EventUUID4: TypeAlias = Annotated[UUID4, BeforeValidator(_exact_event_uuid)]
EventTimestamp: TypeAlias = Annotated[CanonicalTimestamp, BeforeValidator(_exact_event_datetime)]
EventText: TypeAlias = Annotated[BoundedNonBlankString, BeforeValidator(_control_free_event_text)]

_ARM_LOCATOR_PATTERN = re.compile(r"^arm\[(baseline|concise|caveman|if)\]/(.+)$")
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_CONCISE_SHA256 = "49f0aab807da85db802937558c8afa5617cfc9e05002327157b321b56b139cd1"


class CapsuleV1(CapsuleModel):
    capsule_schema_version: Literal["1"]
    attempt_schema_version: Literal["2"]
    event_schema_version: Literal["1"]
    resolved_manifest_schema_version: Literal["2"]
    resource_limits_version: Literal["1"]
    canonicalization_version: Literal["laconian-json-v1"]
    sanitizer_version: Literal["laconian-sanitizer-v1"]
    runner_version: BoundedNonBlankString
    run_id: UUID4
    created_at: CanonicalTimestamp
    run_purpose: RunPurpose
    claim_intent: ClaimIntent
    schedule_algorithm_version: Literal["laconian-schedule-v1"]
    arm_order_seed: StrictSigned64Int
    source_manifest_commitment_sha256: Sha256
    manifest_sha256: Sha256
    input_index_sha256: Sha256
    case_index_sha256: Sha256
    plan_sha256: Sha256
    environment_sha256: Sha256
    runner_source_sha256: Sha256


class InputFileRecordV1(CapsuleModel):
    role: InputRole
    role_ordinal: StrictNonNegativeInt
    logical_locator: BoundedNonBlankString
    capsule_path: RelativePosixPath
    byte_length: StrictNonNegativeInt
    sha256: Sha256
    dataset_id: BoundedNonBlankString | None
    binding_id: BoundedNonBlankString | None

    @model_validator(mode="after")
    def validate_role_contract(self) -> Self:
        if self.role == "case":
            if self.dataset_id is None or self.binding_id is not None:
                raise ValueError("case files require only dataset_id")
            expected_locator = f"case_files[{self.role_ordinal}]"
            if self.logical_locator != expected_locator:
                raise ValueError("case locator must match role ordinal")
            if self.capsule_path != f"inputs/cases/{self.role_ordinal:03d}.yaml":
                raise ValueError("case capsule path must match role ordinal")
        elif self.role == "protocol":
            if self.dataset_id is not None or self.binding_id is None:
                raise ValueError("protocol files require only binding_id")
            expected_locator = f"capsule.protocol_bindings[{self.role_ordinal}].path"
            if self.logical_locator != expected_locator:
                raise ValueError("protocol locator must match role ordinal")
            assert self.binding_id is not None
            binding_prefix = hashlib.sha256(self.binding_id.encode("utf-8")).hexdigest()[:16]
            expected_path = f"inputs/protocols/{self.role_ordinal:03d}-{binding_prefix}.bin"
            if self.capsule_path != expected_path:
                raise ValueError("protocol capsule path must match ordinal and binding")
        else:
            if self.dataset_id is not None or self.binding_id is not None:
                raise ValueError("only case/protocol files carry owning IDs")
            if self.role == "replay":
                if (
                    self.role_ordinal != 0
                    or self.logical_locator != "provider.replay_file"
                    or self.capsule_path != "inputs/provider/replay.yaml"
                ):
                    raise ValueError("replay locator, ordinal, and capsule path are fixed")
            elif self.role == "arm":
                match = _ARM_LOCATOR_PATTERN.fullmatch(self.logical_locator)
                if match is None:
                    raise ValueError("arm locator is invalid")
                arm, member = match.groups()
                validate_relative_posix_path(member)
                allowed_members = {
                    "baseline": ("baseline.txt",),
                    "concise": ("concise.txt",),
                    "caveman": ("SKILL.md", "SOURCE.md", "LICENSE.txt"),
                    "if": ("SKILL.md",),
                }
                if member not in allowed_members[arm]:
                    raise ValueError("arm locator member is invalid")
                expected_path = (
                    f"inputs/arms/{member}"
                    if arm in ("baseline", "concise")
                    else f"inputs/arms/{arm}/{member}"
                )
                if self.capsule_path != expected_path:
                    raise ValueError("arm capsule path must match its logical locator")
                if arm == "baseline" and (self.byte_length != 0 or self.sha256 != _EMPTY_SHA256):
                    raise ValueError("baseline arm metadata must bind the exact empty bytes")
                if arm == "concise" and (self.byte_length != 17 or self.sha256 != _CONCISE_SHA256):
                    raise ValueError("concise arm metadata must bind its exact instruction bytes")
            elif self.role == "runner_source":
                prefix = "package[laconian_eval]/"
                if not self.logical_locator.startswith(prefix):
                    raise ValueError("runner-source locator is invalid")
                member = self.logical_locator[len(prefix) :]
                validate_relative_posix_path(member)
                if member != "py.typed" and not member.endswith(".py"):
                    raise ValueError("runner-source locator must name Python source or py.typed")
                if self.capsule_path != f"inputs/software/runner/laconian_eval/{member}":
                    raise ValueError("runner-source path must match its logical locator")
        return self


class InputIndexV1(CapsuleModel):
    schema_version: Literal["1"]
    manifest_sha256: Sha256
    files: tuple[InputFileRecordV1, ...] = Field(min_length=1)

    @field_validator("files")
    @classmethod
    def validate_sorted_unique_paths(
        cls, value: tuple[InputFileRecordV1, ...]
    ) -> tuple[InputFileRecordV1, ...]:
        require_utf8_sorted_unique(
            value,
            key=lambda record: record.capsule_path,
            label="input-index capsule paths",
        )
        roles = {record.role for record in value}
        if not {"case", "arm", "runner_source"} <= roles:
            raise ValueError("input index requires case, arm, and runner-source members")
        if sum(record.role == "replay" for record in value) > 1:
            raise ValueError("input index may contain at most one replay fixture")
        for role in ("case", "protocol", "runner_source"):
            records = tuple(record for record in value if record.role == role)
            ordinals = tuple(record.role_ordinal for record in records)
            expected_ordinals = tuple(range(len(records)))
            if role == "runner_source":
                valid_ordinals = ordinals == expected_ordinals
            else:
                valid_ordinals = tuple(sorted(ordinals)) == expected_ordinals
            if not valid_ordinals:
                raise ValueError(f"{role} role ordinals must be consecutive and unique")

        arm_records = tuple(record for record in value if record.role == "arm")
        arm_ordinals: dict[str, int] = {}
        for record in arm_records:
            match = _ARM_LOCATOR_PATTERN.fullmatch(record.logical_locator)
            assert match is not None
            arm = match.group(1)
            prior = arm_ordinals.setdefault(arm, record.role_ordinal)
            if prior != record.role_ordinal:
                raise ValueError("all members of one arm must share its role ordinal")
        expected_arm_members = {
            "baseline": {"baseline.txt"},
            "concise": {"concise.txt"},
            "caveman": {"SKILL.md", "SOURCE.md", "LICENSE.txt"},
            "if": {"SKILL.md"},
        }
        for arm in arm_ordinals:
            actual_members = {
                match.group(2)
                for record in arm_records
                if (match := _ARM_LOCATOR_PATTERN.fullmatch(record.logical_locator)) is not None
                and match.group(1) == arm
            }
            if actual_members != expected_arm_members[arm]:
                raise ValueError("input index must include every fixed member of a selected arm")
        if sorted(arm_ordinals.values()) != list(range(len(arm_ordinals))):
            raise ValueError("arm role ordinals must identify distinct consecutive arms")
        return value


class CaseIndexRowV1(CapsuleModel):
    dataset_id: BoundedNonBlankString
    dataset_version: BoundedNonBlankString
    dataset_role: DatasetRole
    source_ordinal: StrictNonNegativeInt
    record_ordinal: StrictNonNegativeInt
    case_id: CaseId
    case_uid: Sha256
    scenario_id: ScenarioId
    scenario_uid: Sha256
    locale: Locale
    category: CaseCategory
    case_definition_sha256: Sha256
    prompt_sha256: Sha256
    prompt_utf8_bytes: StrictPositiveInt


class PlanRowV1(CapsuleModel):
    ordinal: StrictNonNegativeInt
    plan_item_id: Sha256
    pairing_unit_id: Sha256
    case_uid: Sha256
    scenario_uid: Sha256
    case_id: CaseId
    locale: Locale
    repetition: StrictNonNegativeInt
    arm: Arm
    block_id: Sha256
    arm_position: StrictNonNegativeInt
    prompt_sha256: Sha256
    case_definition_sha256: Sha256
    instruction_sha256: Sha256
    request_config_sha256: Sha256
    input_token_bound: StrictPositiveInt


class RunnerSourceFileV1(CapsuleModel):
    path: RelativePosixPath
    byte_length: StrictNonNegativeInt
    sha256: Sha256

    @field_validator("path")
    @classmethod
    def validate_runner_member(cls, value: str) -> str:
        if value != "py.typed" and not value.endswith(".py"):
            raise ValueError("runner source members must be Python source or py.typed")
        return value


class RunnerSourceIndexV1(CapsuleModel):
    schema_version: Literal["1"]
    package_name: Literal["laconian-eval"]
    files: tuple[RunnerSourceFileV1, ...] = Field(min_length=1)
    runner_source_sha256: Sha256

    @field_validator("files")
    @classmethod
    def validate_sorted_unique_files(
        cls, value: tuple[RunnerSourceFileV1, ...]
    ) -> tuple[RunnerSourceFileV1, ...]:
        return require_utf8_sorted_unique(
            value,
            key=lambda record: record.path,
            label="runner-source paths",
        )


class UvLockV1(CapsuleModel):
    availability: Literal["present", "unavailable"]
    sha256: Sha256 | None

    @model_validator(mode="after")
    def validate_availability(self) -> Self:
        if (self.availability == "present") != (self.sha256 is not None):
            raise ValueError("uv_lock.sha256 is present exactly when the lock is present")
        return self


class DependencyRecordV1(CapsuleModel):
    distribution: NormalizedDistributionName
    version: BoundedNonBlankString
    files_sha256: Sha256


class ImportRootV1(CapsuleModel):
    distribution: NormalizedDistributionName
    module: TopLevelModuleName
    origin_member: RelativePosixPath


class ImportEnvironmentV1(CapsuleModel):
    import_policy_version: Literal["laconian-import-policy-v1"]
    stdlib_origin_policy: Literal["interpreter-layout-v1"]
    stdlib_extension_policy: Literal["destshared-v1"]
    platstdlib_mode: Literal["same_as_stdlib", "omitted"]
    guard_source_sha256: Sha256
    audit_hook_source_sha256: Sha256
    runner_import_mode: Literal["wheel", "path"]
    launcher_mode: Literal["module", "console_script"]
    launcher_template_sha256: Sha256 | None
    virtualenv_bootstrap_sha256: Sha256 | None
    import_roots: tuple[ImportRootV1, ...] = Field(min_length=1)

    @field_validator("import_roots")
    @classmethod
    def validate_sorted_unique_roots(
        cls, value: tuple[ImportRootV1, ...]
    ) -> tuple[ImportRootV1, ...]:
        return require_utf8_sorted_unique(
            value,
            key=lambda record: f"{record.distribution}\0{record.module}\0{record.origin_member}",
            label="import roots",
        )

    @model_validator(mode="after")
    def validate_launcher(self) -> Self:
        if self.launcher_mode == "module":
            if self.launcher_template_sha256 is not None:
                raise ValueError("module launcher requires a null template digest")
        elif self.launcher_template_sha256 != CONSOLE_LAUNCHER_TEMPLATE_SHA256:
            raise ValueError("console launcher requires the fixed template digest")
        return self


class RuntimeEnvironmentV1(CapsuleModel):
    python_implementation: BoundedNonBlankString
    python_version: BoundedNonBlankString
    os_family: BoundedNonBlankString
    os_release: BoundedNonBlankString
    architecture: BoundedNonBlankString
    filesystem_class: FilesystemClass
    dependencies: tuple[DependencyRecordV1, ...] = Field(min_length=1)
    import_environment: ImportEnvironmentV1
    runtime_fingerprint_sha256: Sha256

    @field_validator("dependencies")
    @classmethod
    def validate_sorted_unique_dependencies(
        cls, value: tuple[DependencyRecordV1, ...]
    ) -> tuple[DependencyRecordV1, ...]:
        return require_utf8_sorted_unique(
            value,
            key=lambda record: record.distribution,
            label="dependency distributions",
        )

    @model_validator(mode="after")
    def validate_import_root_ownership(self) -> Self:
        distributions = {dependency.distribution for dependency in self.dependencies}
        if any(
            root.distribution not in distributions for root in self.import_environment.import_roots
        ):
            raise ValueError("every import root must name a selected dependency")
        modules = tuple(root.module for root in self.import_environment.import_roots)
        require_unique(modules, label="import-root modules")
        return self


class ProviderEnvironmentV1(CapsuleModel):
    kind: ProviderKind
    requested_model: BoundedNonBlankString
    adapter_source_sha256: Sha256
    transport_policy: Literal["offline", "openai-direct-v1"]
    sdk_distribution: Literal["openai"] | None
    sdk_version: BoundedNonBlankString | None

    @model_validator(mode="after")
    def validate_provider_runtime(self) -> Self:
        if self.kind == "openai":
            if (
                self.transport_policy != "openai-direct-v1"
                or self.sdk_distribution != "openai"
                or self.sdk_version is None
            ):
                raise ValueError("openai requires its direct transport and SDK identity")
        elif (
            self.transport_policy != "offline"
            or self.sdk_distribution is not None
            or self.sdk_version is not None
        ):
            raise ValueError("fake/replay require offline transport and null SDK identity")
        return self


class EnvironmentV1(CapsuleModel):
    schema_version: Literal["1"]
    canonical_repository_url: Literal["https://github.com/agent-axiom/laconian"]
    checkout_binding: Literal["bound", "unbound", "unavailable"]
    git_commit: GitObjectId | None
    git_state: Literal["clean", "dirty", "unavailable"]
    uv_lock: UvLockV1
    package_name: Literal["laconian-eval"]
    package_version: BoundedNonBlankString
    runner_source_sha256: Sha256
    runtime: RuntimeEnvironmentV1
    provider: ProviderEnvironmentV1
    container_image_digest: Sha256 | None

    @model_validator(mode="after")
    def validate_checkout_attribution(self) -> Self:
        if self.checkout_binding != "bound":
            if (
                self.git_state != "unavailable"
                or self.git_commit is not None
                or self.uv_lock.availability != "unavailable"
            ):
                raise ValueError("unbound checkout cannot carry Git or lock attribution")
        elif self.git_state == "unavailable":
            if self.git_commit is not None:
                raise ValueError("unavailable Git state requires a null commit")
        elif self.git_commit is None:
            raise ValueError("clean/dirty Git state requires a commit")

        dependency_versions = {
            dependency.distribution: dependency.version for dependency in self.runtime.dependencies
        }
        distributions = set(dependency_versions)
        required_distributions = {"packaging", "pydantic", "pydantic-core", "pyyaml"}
        if not required_distributions <= distributions:
            raise ValueError("runtime dependencies omit a required root distribution")
        if (self.provider.kind == "openai") != ("openai" in distributions):
            raise ValueError("OpenAI dependency presence must match the selected provider")
        if (
            self.provider.kind == "openai"
            and dependency_versions["openai"] != self.provider.sdk_version
        ):
            raise ValueError("OpenAI dependency and SDK versions must match")
        return self


class SessionEnvironmentV1(CapsuleModel):
    schema_version: Literal["1"]
    package_version: EventText
    runner_source_sha256: Sha256
    runtime_fingerprint_sha256: Sha256
    python_implementation: EventText
    python_version: EventText
    os_family: EventText
    os_release: EventText
    architecture: EventText
    filesystem_class: FilesystemClass
    adapter_source_sha256: Sha256
    sdk_distribution: Literal["openai"] | None
    sdk_version: EventText | None

    @model_validator(mode="after")
    def validate_sdk_pair(self) -> Self:
        if (self.sdk_distribution is None) != (self.sdk_version is None):
            raise ValueError("session SDK distribution and version must both be null or populated")
        return self


class PreparedPayloadV1(CapsuleModel):
    manifest_sha256: Sha256
    input_index_sha256: Sha256
    case_index_sha256: Sha256
    plan_sha256: Sha256
    environment_sha256: Sha256
    runner_source_sha256: Sha256


class PreparedEventV1(CapsuleModel):
    schema_version: Literal["1"]
    sequence: StrictNonNegativeInt
    event_id: Sha256
    run_id: EventUUID4
    occurred_at: EventTimestamp
    kind: Literal["prepared"]
    operation_id: EventUUID4
    execution_session_id: None
    payload: PreparedPayloadV1

    @field_validator("sequence")
    @classmethod
    def require_sequence_zero(cls, value: int) -> int:
        if value != 0:
            raise ValueError("prepared event sequence must be zero")
        return value


class VerifyErrorV1(CapsuleModel):
    code: VerificationErrorCode
    path: RelativePosixPath | None
    sequence: StrictNonNegativeInt | None
    explanation: DiagnosticString


class VerifyResultV1(CapsuleModel):
    schema_version: Literal["1"]
    status: VerifyStatus
    run_id: UUID4 | None
    state: LifecycleState | None
    capsule_sha256: Sha256 | None
    missing_plan_item_ids: tuple[Sha256, ...]
    operational_blocker_codes: tuple[OperationalBlocker, ...]
    warnings: tuple[VerificationWarning, ...]
    first_error: VerifyErrorV1 | None

    @field_validator("missing_plan_item_ids")
    @classmethod
    def validate_missing_ids(cls, value: tuple[Sha256, ...]) -> tuple[Sha256, ...]:
        return require_utf8_sorted_unique(
            value,
            key=lambda digest: digest,
            label="missing plan item IDs",
        )

    @field_validator("operational_blocker_codes")
    @classmethod
    def validate_blocker_order(
        cls, value: tuple[OperationalBlocker, ...]
    ) -> tuple[OperationalBlocker, ...]:
        return require_fixed_order(
            value,
            order=OPERATIONAL_BLOCKER_ORDER,
            label="operational blocker codes",
        )

    @field_validator("warnings")
    @classmethod
    def validate_warning_order(
        cls, value: tuple[VerificationWarning, ...]
    ) -> tuple[VerificationWarning, ...]:
        return require_fixed_order(
            value,
            order=VERIFICATION_WARNING_ORDER,
            label="verification warnings",
        )

    @model_validator(mode="after")
    def validate_status_projection(self) -> Self:
        if self.status == "valid":
            if self.run_id is None or self.state is None or self.first_error is not None:
                raise ValueError("valid result requires run/state and no error")
            sealed = self.state in ("SEALED_COMPLETE", "SEALED_BLOCKED")
            if sealed != (self.capsule_sha256 is not None):
                raise ValueError("capsule hash is present exactly for sealed states")
            state_blockers: dict[str, tuple[str, ...]] = {
                "PREPARED": ("never_started",),
                "INTERRUPTED": ("interrupted",),
                "AMBIGUOUS_INFLIGHT": ("ambiguous_inflight",),
                "AUTHENTICATION_STOPPED": ("authentication_stopped",),
            }
            if self.state in state_blockers:
                if self.operational_blocker_codes != state_blockers[self.state]:
                    raise ValueError("operational blockers must match the lifecycle state")
                if not self.missing_plan_item_ids:
                    raise ValueError("an incomplete lifecycle state requires missing plan items")
            elif self.state in ("GENERATION_COMPLETE", "SEALED_COMPLETE"):
                if self.operational_blocker_codes or self.missing_plan_item_ids:
                    raise ValueError("complete lifecycle states have no blockers or missing items")
            elif self.state == "SEALED_BLOCKED":
                if len(self.operational_blocker_codes) != 1 or not self.missing_plan_item_ids:
                    raise ValueError("sealed blocked state requires one blocker and missing items")
            elif (
                bool(self.operational_blocker_codes) != bool(self.missing_plan_item_ids)
                or len(self.operational_blocker_codes) > 1
            ):
                raise ValueError(
                    "interrupted sealing requires at most one blocker matching missing items"
                )
            return self

        if (
            self.run_id is not None
            or self.state is not None
            or self.capsule_sha256 is not None
            or self.missing_plan_item_ids
            or self.operational_blocker_codes
            or self.warnings
        ):
            raise ValueError("nonvalid results require null artifact fields and empty arrays")

        if self.status == "invalid":
            if self.first_error is None or self.first_error.code == "unsupported_filesystem":
                raise ValueError("invalid requires a non-filesystem first error")
        elif self.status == "busy":
            if self.first_error is not None:
                raise ValueError("busy requires a null first error")
        elif (
            self.first_error is None
            or self.first_error.code != "unsupported_filesystem"
            or self.first_error.path is not None
            or self.first_error.sequence is not None
        ):
            raise ValueError("unsupported requires the exact unsupported-filesystem error")
        return self
