"""Provider-free, descriptor-relative generation-capsule preparation."""

from __future__ import annotations

import os
import stat
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NoReturn, cast
from uuid import RFC_4122, UUID, uuid4

from laconian_eval.capsule.bounded_io import (
    BoundedIOError,
    open_directory_no_follow,
    read_regular_file_once,
)
from laconian_eval.capsule.canonical import canonical_json, canonical_jsonl, sha256_bytes
from laconian_eval.capsule.capture import (
    CapturedInputFile,
    CapturedInputs,
    capture_authored_inputs,
    load_source_manifest_capture,
)
from laconian_eval.capsule.events import event_jsonl, make_prepared_event
from laconian_eval.capsule.filesystem import (
    DestinationCollisionError,
    FilesystemPosixOps,
    PostPublishSyncError,
    PreparationFilesystem,
    UnsupportedFilesystemError,
    preparation_filesystem,
)
from laconian_eval.capsule.import_policy import (
    build_import_policy,
    capture_runtime_import_state,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.planning import materialize_case_index, materialize_parent_plan
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.provenance import (
    capture_installed_provenance,
    project_environment,
)
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    CaseIndexRowV1,
    EnvironmentV1,
    InputFileRecordV1,
    InputIndexV1,
    PlanRowV1,
    RunnerSourceIndexV1,
    VerifyResultV1,
)
from laconian_eval.capsule.schema import (
    FilesystemClass,
    Locale,
    ProviderKind,
    Sha256,
    VerificationWarning,
)
from laconian_eval.capsule.sharding import (
    ShardPlanError,
    materialize_shard_projection,
    parse_shard_plan_file_bytes,
)
from laconian_eval.capsule.verify import _verify_prepared_capsule_descriptors

_GENERIC_PREPARATION_MESSAGE = "capsule preparation failed"
_GENERIC_PUBLICATION_MESSAGE = "capsule publication failed"
_PERSISTENT_LOCK_NAME = ".laconian.lock"
_CAPSULE_MARKER_NAME = "capsule.json"
_RESERVED_API_KEY_ENVIRONMENTS = frozenset({"PYTHONHOME", "PYTHONPATH"})

_DirectoryIdentity = tuple[int, int, int]


class PreparationError(ValueError):
    """A content-free preparation failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_GENERIC_PREPARATION_MESSAGE)


class PostPublishVerificationError(RuntimeError):
    """A visible owned capsule could not cross the final verification boundary."""

    code = "post_publish_verification_failed"
    published = True

    def __init__(self, destination_name: str, *, publication_path: Path | None = None) -> None:
        self.destination_name = destination_name
        self.publication_path = publication_path
        super().__init__(_GENERIC_PUBLICATION_MESSAGE)


@dataclass(frozen=True, slots=True)
class PrepareRequest:
    manifest_path: Path
    results_root: Path
    invocation_cwd: Path
    input_root: Path | None
    source_root: Path | None
    container_image_digest: Sha256 | None


@dataclass(frozen=True, slots=True)
class PrepareShardRequest:
    prepare: PrepareRequest
    parent_plan_path: Path
    shard_plan_path: Path


@dataclass(frozen=True, slots=True)
class PreparedCapsule:
    path: Path
    run_id: UUID
    operation_id: UUID
    capsule: CapsuleV1
    summary: PreparedPlanSummary


@dataclass(frozen=True, slots=True)
class PreparedPlanSummary:
    case_count: int
    scenario_count: int
    locale_case_counts: tuple[tuple[Locale, int], ...]
    arm_count: int
    repetition_count: int
    planned_request_count: int
    checkout_binding: Literal["bound", "unbound", "unavailable"]
    git_state: Literal["clean", "dirty", "unavailable"]
    uv_lock_availability: Literal["present", "unavailable"]
    filesystem_class: FilesystemClass
    provider_kind: ProviderKind
    transport_policy: Literal["offline", "openai-direct-v1"]
    container_image_digest: str | None
    verification_warnings: tuple[VerificationWarning, ...]


def _make_prepared_plan_summary(
    manifest: ResolvedManifestV2,
    *,
    case_index: Sequence[CaseIndexRowV1],
    plan: Sequence[PlanRowV1],
    environment: EnvironmentV1,
    verification: VerifyResultV1,
) -> PreparedPlanSummary:
    locale_counts = {"en": 0, "ru": 0}
    for row in case_index:
        locale_counts[row.locale] += 1
    return PreparedPlanSummary(
        case_count=len(case_index),
        scenario_count=len({row.scenario_uid for row in case_index}),
        locale_case_counts=(("en", locale_counts["en"]), ("ru", locale_counts["ru"])),
        arm_count=len(manifest.arms),
        repetition_count=manifest.repetitions,
        planned_request_count=len(plan),
        checkout_binding=environment.checkout_binding,
        git_state=environment.git_state,
        uv_lock_availability=environment.uv_lock.availability,
        filesystem_class=environment.runtime.filesystem_class,
        provider_kind=environment.provider.kind,
        transport_policy=environment.provider.transport_policy,
        container_image_digest=environment.container_image_digest,
        verification_warnings=verification.warnings,
    )


def _post_publish_verify(
    capsule_directory_fd: int,
    *,
    results_root_fd: int,
    destination_name: str,
    persistent_lock_descriptor: int,
) -> VerifyResultV1:
    """Verify the durable visible capsule through descriptors already owned here."""

    result = _verify_prepared_capsule_descriptors(
        capsule_directory_fd,
        results_root_fd=results_root_fd,
        destination_name=destination_name,
        persistent_lock_descriptor=persistent_lock_descriptor,
    )
    if result.status != "valid" or result.state != "PREPARED":
        raise PostPublishVerificationError(destination_name)
    return result


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int:
        raise PreparationError("artifact_io_failed")
    return value


def _close_on_exec_flag() -> int:
    value = getattr(os, "O_CLOEXEC", 0)
    return value if type(value) is int else 0


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | _required_flag("O_DIRECTORY")
        | _required_flag("O_NOFOLLOW")
        | _close_on_exec_flag()
    )


def _file_flags() -> int:
    return (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _required_flag("O_NOFOLLOW") | _close_on_exec_flag()
    )


def _leaf_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode)


def _regular_path_matches(directory_fd: int, name: str, descriptor: int) -> bool:
    try:
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except (OSError, TypeError, ValueError):
        return False
    return (
        stat.S_ISREG(descriptor_metadata.st_mode)
        and stat.S_ISREG(path_metadata.st_mode)
        and _leaf_identity(descriptor_metadata) == _leaf_identity(path_metadata)
    )


def _absolute_path(value: os.PathLike[str] | str) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError:
        raise PreparationError("invalid_results_root") from None
    if type(raw) is not str or not raw or "\x00" in raw:
        raise PreparationError("invalid_results_root")
    return Path(os.path.abspath(raw))


def _directory_path_matches(path: Path, descriptor: int) -> bool:
    try:
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = os.stat(path, follow_symlinks=False)
    except (OSError, TypeError, ValueError):
        return False
    return (
        stat.S_ISDIR(descriptor_metadata.st_mode)
        and stat.S_ISDIR(path_metadata.st_mode)
        and (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
        == (path_metadata.st_dev, path_metadata.st_ino)
    )


def _published_directory_matches(
    capsule_directory_fd: int,
    results_root_fd: int,
    destination_name: str,
) -> bool:
    try:
        descriptor_metadata = os.fstat(capsule_directory_fd)
        path_metadata = os.stat(
            destination_name,
            dir_fd=results_root_fd,
            follow_symlinks=False,
        )
    except (OSError, TypeError, ValueError):
        return False
    return (
        stat.S_ISDIR(descriptor_metadata.st_mode)
        and stat.S_ISDIR(path_metadata.st_mode)
        and (descriptor_metadata.st_dev, descriptor_metadata.st_ino)
        == (path_metadata.st_dev, path_metadata.st_ino)
    )


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    offset = 0
    while offset < len(view):
        try:
            written = os.write(descriptor, view[offset:])
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError("owned artifact write made no progress")
        offset += written


def _open_owned_regular(directory_fd: int, name: str) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _file_flags(), 0o600, dir_fd=directory_fd)
        if not _regular_path_matches(directory_fd, name, descriptor):
            raise OSError("owned artifact is not a stable regular file")
        return descriptor
    except BaseException as error:
        if descriptor is not None:
            with suppress(BaseException):
                os.close(descriptor)
        if isinstance(error, (OSError, RuntimeError, TypeError, ValueError)):
            raise PreparationError("artifact_io_failed") from None
        raise


def _write_owned_regular(
    directory_fd: int,
    name: str,
    data: bytes,
    *,
    posix: FilesystemPosixOps,
) -> None:
    descriptor = _open_owned_regular(directory_fd, name)
    primary_error: BaseException | None = None
    try:
        _write_all(descriptor, data)
        posix.fsync(descriptor)
    except BaseException as caught:
        primary_error = caught
    close_error: BaseException | None = None
    try:
        os.close(descriptor)
    except BaseException as caught:
        close_error = caught
    error = primary_error if primary_error is not None else close_error
    if isinstance(error, (OSError, RuntimeError, TypeError, ValueError)):
        raise PreparationError("artifact_io_failed") from None
    if error is not None:
        raise error.with_traceback(error.__traceback__)


def _create_persistent_lock(
    staging_fd: int,
    *,
    posix: FilesystemPosixOps,
) -> int:
    descriptor = _open_owned_regular(staging_fd, _PERSISTENT_LOCK_NAME)
    acquired = False
    try:
        posix.acquire_lock(descriptor, exclusive=True, blocking=True)
        acquired = True
        if not _regular_path_matches(staging_fd, _PERSISTENT_LOCK_NAME, descriptor):
            raise OSError("persistent lock path changed during acquisition")
        posix.fsync(descriptor)
        return descriptor
    except BaseException as error:
        if acquired:
            with suppress(BaseException):
                posix.release_lock(descriptor)
        with suppress(BaseException):
            os.close(descriptor)
        if isinstance(error, (OSError, RuntimeError, TypeError, ValueError)):
            raise PreparationError("artifact_io_failed") from None
        raise


def _release_persistent_lock(
    descriptor: int,
    *,
    posix: FilesystemPosixOps,
) -> BaseException | None:
    error: BaseException | None = None
    try:
        posix.release_lock(descriptor)
    except BaseException as caught:
        error = caught
    try:
        os.close(descriptor)
    except BaseException as caught:
        if error is None:
            error = caught
    return error


def _artifact_directories(paths: tuple[str, ...]) -> tuple[str, ...]:
    directories: set[str] = set()
    for path in paths:
        parts = path.split("/")
        if any(not part or part in {".", ".."} for part in parts):
            raise PreparationError("artifact_io_failed")
        for end in range(1, len(parts)):
            directories.add("/".join(parts[:end]))
    return tuple(
        sorted(
            directories,
            key=lambda value: (value.count("/"), value.encode("utf-8")),
        )
    )


def _raise_artifact_failure(error: BaseException) -> NoReturn:
    if isinstance(error, PreparationError):
        raise error.with_traceback(error.__traceback__)
    if isinstance(error, (KeyError, OSError, RuntimeError, TypeError, ValueError)):
        raise PreparationError("artifact_io_failed") from None
    raise error.with_traceback(error.__traceback__)


def _close_artifact_descriptor(descriptor: int) -> BaseException | None:
    try:
        os.close(descriptor)
    except BaseException as error:
        return error
    return None


def _open_artifact_directory(
    staging_fd: int,
    path: str,
    identities: dict[str, _DirectoryIdentity],
) -> tuple[int, bool]:
    if path == "":
        return staging_fd, False

    current_fd = staging_fd
    current_owned = False
    prefix: list[str] = []
    for component in path.split("/"):
        candidate: int | None = None
        primary_error: BaseException | None = None
        try:
            prefix.append(component)
            relative = "/".join(prefix)
            expected = identities[relative]
            candidate = os.open(component, _directory_flags(), dir_fd=current_fd)
            descriptor_metadata = os.fstat(candidate)
            path_metadata = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(descriptor_metadata.st_mode)
                or not stat.S_ISDIR(path_metadata.st_mode)
                or _leaf_identity(descriptor_metadata) != _leaf_identity(path_metadata)
                or _leaf_identity(descriptor_metadata) != expected
            ):
                raise OSError("owned artifact directory identity changed")
        except BaseException as error:
            primary_error = error

        if primary_error is not None:
            if candidate is not None:
                _close_artifact_descriptor(candidate)
            if current_owned:
                _close_artifact_descriptor(current_fd)
            _raise_artifact_failure(primary_error)

        assert candidate is not None
        if current_owned:
            close_error = _close_artifact_descriptor(current_fd)
            if close_error is not None:
                _close_artifact_descriptor(candidate)
                _raise_artifact_failure(close_error)
        current_fd = candidate
        current_owned = True
    return current_fd, current_owned


def _create_directories(
    staging_fd: int,
    paths: tuple[str, ...],
) -> dict[str, _DirectoryIdentity]:
    identities: dict[str, _DirectoryIdentity] = {}
    for path in _artifact_directories(paths):
        parent, _, name = path.rpartition("/")
        parent_fd, parent_owned = _open_artifact_directory(staging_fd, parent, identities)
        candidate: int | None = None
        identity: _DirectoryIdentity | None = None
        primary_error: BaseException | None = None
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
            candidate = os.open(name, _directory_flags(), dir_fd=parent_fd)
            descriptor_metadata = os.fstat(candidate)
            path_metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(descriptor_metadata.st_mode)
                or not stat.S_ISDIR(path_metadata.st_mode)
                or _leaf_identity(descriptor_metadata) != _leaf_identity(path_metadata)
            ):
                raise OSError("owned artifact directory is unstable")
            identity = _leaf_identity(descriptor_metadata)
        except BaseException as error:
            primary_error = error

        candidate_close_error = None if candidate is None else _close_artifact_descriptor(candidate)
        parent_close_error = _close_artifact_descriptor(parent_fd) if parent_owned else None
        failure = primary_error or candidate_close_error or parent_close_error
        if failure is not None:
            _raise_artifact_failure(failure)
        assert identity is not None
        identities[path] = identity
    return identities


def _write_artifact(
    staging_fd: int,
    identities: dict[str, _DirectoryIdentity],
    path: str,
    data: bytes,
    *,
    posix: FilesystemPosixOps,
) -> None:
    parent, _, name = path.rpartition("/")
    parent_fd, parent_owned = _open_artifact_directory(staging_fd, parent, identities)
    primary_error: BaseException | None = None
    try:
        _write_owned_regular(parent_fd, name, data, posix=posix)
    except BaseException as error:
        primary_error = error
    close_error = _close_artifact_descriptor(parent_fd) if parent_owned else None
    failure = primary_error or close_error
    if failure is not None:
        _raise_artifact_failure(failure)


def _sync_directory_tree(
    staging_fd: int,
    identities: dict[str, _DirectoryIdentity],
    *,
    posix: FilesystemPosixOps,
) -> None:
    for path in sorted(
        identities,
        key=lambda value: (-value.count("/"), value.encode("utf-8")),
    ):
        descriptor, owned = _open_artifact_directory(staging_fd, path, identities)
        primary_error: BaseException | None = None
        try:
            posix.fsync(descriptor)
        except BaseException as error:
            primary_error = error
        close_error = _close_artifact_descriptor(descriptor) if owned else None
        failure = primary_error or close_error
        if failure is not None:
            _raise_artifact_failure(failure)
    try:
        posix.fsync(staging_fd)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise PreparationError("artifact_io_failed") from None


def _strict_model(model_type: type[Any], value: object, code: str) -> Any:
    try:
        payload = value.model_dump(mode="python", round_trip=True, warnings=False)  # type: ignore[attr-defined]
        return model_type.model_validate(payload)
    except (AttributeError, TypeError, ValueError):
        raise PreparationError(code) from None


@dataclass(frozen=True, slots=True)
class _PlanSelection:
    case_index: tuple[CaseIndexRowV1, ...]
    plan: tuple[PlanRowV1, ...]
    planning_inputs: tuple[CapturedInputFile, ...] = ()


def _read_planning_input(
    path: Path,
    *,
    invocation_cwd: Path,
    limit: int,
    limit_code: str,
) -> bytes:
    descriptor: int | None = None
    try:
        raw_path = os.fspath(path)
        if type(raw_path) is not str or not raw_path:
            raise BoundedIOError("unsafe_source_path", "unsafe source path")
        if path.is_absolute():
            root = Path(path.anchor)
            relative = "/".join(path.parts[1:])
        else:
            root = invocation_cwd
            relative = raw_path
        descriptor = open_directory_no_follow(root)
        return read_regular_file_once(
            descriptor,
            relative,
            limit=limit,
            code=limit_code,
        )
    except ResourceLimitError as error:
        if error.code == limit_code:
            raise PreparationError(limit_code) from None
        raise PreparationError("planning_input_read_failed") from None
    except (BoundedIOError, OSError, RuntimeError, TypeError, ValueError, UnicodeError):
        raise PreparationError("planning_input_read_failed") from None
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)


def _planning_input_file(
    *,
    role: Literal["parent_plan", "shard_plan"],
    data: bytes,
) -> CapturedInputFile:
    locator, capsule_path = {
        "parent_plan": ("preflight.parent_plan", "inputs/planning/parent-plan.jsonl"),
        "shard_plan": ("preflight.shard_plan", "inputs/planning/shard-plan.json"),
    }[role]
    try:
        record = InputFileRecordV1(
            role=role,
            role_ordinal=0,
            logical_locator=locator,
            capsule_path=capsule_path,
            byte_length=len(data),
            sha256=sha256_bytes(data),
            dataset_id=None,
            binding_id=None,
        )
    except (TypeError, ValueError):
        raise PreparationError("plan_mismatch") from None
    return CapturedInputFile(record=record, data=data)


def _materialize_shard_plan_selection(
    captured_inputs: CapturedInputs,
    request: PrepareShardRequest,
) -> _PlanSelection:
    manifest = captured_inputs.resolved_manifest
    case_index = materialize_case_index(captured_inputs, manifest)
    parent_plan = materialize_parent_plan(
        parent_manifest_sha256=captured_inputs.manifest_sha256,
        resolved_manifest=manifest,
        case_index=case_index,
        captured_arms=captured_inputs.arms,
    )
    expected_parent_bytes = canonical_jsonl(
        row.model_dump(mode="json", round_trip=True) for row in parent_plan
    )
    parent_bytes = _read_planning_input(
        request.parent_plan_path,
        invocation_cwd=request.prepare.invocation_cwd,
        limit=RESOURCE_LIMITS_V1.captured_input_total_bytes,
        limit_code="parent_plan_limit",
    )
    shard_bytes = _read_planning_input(
        request.shard_plan_path,
        invocation_cwd=request.prepare.invocation_cwd,
        limit=RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes,
        limit_code="shard_plan_limit",
    )
    if parent_bytes != expected_parent_bytes:
        raise PreparationError("plan_mismatch")
    try:
        shard = parse_shard_plan_file_bytes(shard_bytes)
        if (
            shard.model_id != manifest.provider.model
            or shard.parent_manifest_sha256 != captured_inputs.manifest_sha256
        ):
            raise ShardPlanError("plan_mismatch")
        plan = materialize_shard_projection(shard, parent_plan)
    except (ShardPlanError, TypeError, ValueError):
        raise PreparationError("plan_mismatch") from None
    return _PlanSelection(
        case_index=case_index,
        plan=plan,
        planning_inputs=(
            _planning_input_file(role="parent_plan", data=parent_bytes),
            _planning_input_file(role="shard_plan", data=shard_bytes),
        ),
    )


def _captured_artifacts(
    captured_inputs: CapturedInputs,
    runner_source: object,
    planning_inputs: Sequence[CapturedInputFile] = (),
) -> tuple[InputIndexV1, dict[str, bytes], RunnerSourceIndexV1, bytes]:
    try:
        runner_index = _strict_model(
            RunnerSourceIndexV1,
            runner_source.index,  # type: ignore[attr-defined]
            "invalid_runner_source",
        )
        runner_index_bytes = canonical_json(runner_index.model_dump(mode="json"))
        if runner_source.index_bytes != runner_index_bytes:  # type: ignore[attr-defined]
            raise PreparationError("invalid_runner_source")
        input_files = (
            tuple(captured_inputs.files)
            + tuple(planning_inputs)
            + tuple(
                runner_source.files  # type: ignore[attr-defined]
            )
        )
    except PreparationError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise PreparationError("invalid_runner_source") from None

    records: list[InputFileRecordV1] = []
    artifacts: dict[str, bytes] = {}
    for item in input_files:
        if type(item) is not CapturedInputFile:
            raise PreparationError("invalid_captured_input")
        record = _strict_model(
            InputFileRecordV1,
            item.record,
            "invalid_captured_input",
        )
        if (
            type(item.data) is not bytes
            or len(item.data) != record.byte_length
            or sha256_bytes(item.data) != record.sha256
            or record.capsule_path in artifacts
        ):
            raise PreparationError("invalid_captured_input")
        records.append(record)
        artifacts[record.capsule_path] = item.data
    records.sort(key=lambda item: item.capsule_path.encode("utf-8"))
    try:
        input_index = InputIndexV1(
            schema_version="1",
            manifest_sha256=captured_inputs.manifest_sha256,
            files=tuple(records),
        )
    except (TypeError, ValueError):
        raise PreparationError("invalid_input_index") from None
    return input_index, artifacts, runner_index, runner_index_bytes


def _build_artifacts(
    captured_inputs: CapturedInputs,
    provenance: object,
    environment: EnvironmentV1,
    run_id: UUID,
    operation_id: UUID,
    plan_selection: _PlanSelection | None = None,
) -> tuple[
    CapsuleV1,
    dict[str, bytes],
    ResolvedManifestV2,
    Sequence[CaseIndexRowV1],
    Sequence[PlanRowV1],
    EnvironmentV1,
]:
    manifest = captured_inputs.resolved_manifest
    runner_source = provenance.runner_source  # type: ignore[attr-defined]
    input_index, captured_artifacts, runner_index, runner_index_bytes = _captured_artifacts(
        captured_inputs,
        runner_source,
        () if plan_selection is None else plan_selection.planning_inputs,
    )
    manifest_sha256 = sha256_bytes(captured_inputs.resolved_manifest_bytes)
    if plan_selection is None:
        case_index = materialize_case_index(captured_inputs, manifest)
        plan = materialize_parent_plan(
            parent_manifest_sha256=manifest_sha256,
            resolved_manifest=manifest,
            case_index=case_index,
            captured_arms=captured_inputs.arms,
        )
    else:
        case_index = plan_selection.case_index
        plan = plan_selection.plan
    input_index_bytes = canonical_json(input_index.model_dump(mode="json"))
    case_index_bytes = canonical_jsonl(item.model_dump(mode="json") for item in case_index)
    plan_bytes = canonical_jsonl(item.model_dump(mode="json") for item in plan)
    checked_environment = _strict_model(
        EnvironmentV1,
        environment,
        "invalid_environment",
    )
    environment_bytes = canonical_json(checked_environment.model_dump(mode="json"))
    if (
        checked_environment.runner_source_sha256 != runner_index.runner_source_sha256
        or checked_environment.package_version != manifest.runner_version
    ):
        raise PreparationError("invalid_environment")

    created_at = datetime.now(UTC)
    input_index_sha256 = sha256_bytes(input_index_bytes)
    case_index_sha256 = sha256_bytes(case_index_bytes)
    plan_sha256 = sha256_bytes(plan_bytes)
    environment_sha256 = sha256_bytes(environment_bytes)
    event = make_prepared_event(
        run_id=run_id,
        operation_id=operation_id,
        occurred_at=created_at,
        manifest_sha256=manifest_sha256,
        input_index_sha256=input_index_sha256,
        case_index_sha256=case_index_sha256,
        plan_sha256=plan_sha256,
        environment_sha256=environment_sha256,
        runner_source_sha256=runner_index.runner_source_sha256,
    )
    try:
        capsule = CapsuleV1.model_validate(
            {
                "capsule_schema_version": "1",
                "attempt_schema_version": "2",
                "event_schema_version": "1",
                "resolved_manifest_schema_version": "2",
                "resource_limits_version": "1",
                "canonicalization_version": "laconian-json-v1",
                "sanitizer_version": "laconian-sanitizer-v1",
                "runner_version": manifest.runner_version,
                "run_id": run_id,
                "created_at": created_at,
                "run_purpose": manifest.capsule.run_purpose,
                "claim_intent": manifest.capsule.claim_intent,
                "schedule_algorithm_version": manifest.schedule_algorithm_version,
                "arm_order_seed": manifest.arm_order_seed,
                "source_manifest_commitment_sha256": (
                    captured_inputs.source_manifest_commitment_sha256
                ),
                "manifest_sha256": manifest_sha256,
                "input_index_sha256": input_index_sha256,
                "case_index_sha256": case_index_sha256,
                "plan_sha256": plan_sha256,
                "environment_sha256": environment_sha256,
                "runner_source_sha256": runner_index.runner_source_sha256,
            }
        )
    except (TypeError, ValueError):
        raise PreparationError("invalid_capsule") from None

    artifacts = dict(captured_artifacts)
    generated = {
        "case-index.jsonl": case_index_bytes,
        "environment.json": environment_bytes,
        "events.jsonl": event_jsonl(event),
        "inputs/index.json": input_index_bytes,
        "inputs/software/runner-source.json": runner_index_bytes,
        "manifest.json": captured_inputs.resolved_manifest_bytes,
        "plan.jsonl": plan_bytes,
        "raw.jsonl": b"",
    }
    if set(artifacts).intersection(generated):
        raise PreparationError("artifact_path_collision")
    artifacts.update(generated)
    return capsule, artifacts, manifest, case_index, plan, environment


def _write_and_publish(
    workspace: PreparationFilesystem,
    *,
    posix: FilesystemPosixOps,
    results_root_fd: int,
    results_root_path: Path,
    run_id: UUID,
    operation_id: UUID,
    capsule: CapsuleV1,
    artifacts: dict[str, bytes],
    manifest: ResolvedManifestV2,
    case_index: Sequence[CaseIndexRowV1],
    plan: Sequence[PlanRowV1],
    environment: EnvironmentV1,
) -> PreparedCapsule:
    staging_fd = workspace.staging.descriptor
    destination_name = str(run_id)
    persistent_lock_descriptor: int | None = None
    published = False
    result: PreparedCapsule | None = None
    primary_error: BaseException | None = None
    try:
        persistent_lock_descriptor = _create_persistent_lock(staging_fd, posix=posix)
        artifact_paths = tuple(artifacts)
        directory_identities = _create_directories(staging_fd, artifact_paths)
        for path in sorted(artifacts, key=lambda value: value.encode("utf-8")):
            _write_artifact(
                staging_fd,
                directory_identities,
                path,
                artifacts[path],
                posix=posix,
            )
        _sync_directory_tree(staging_fd, directory_identities, posix=posix)

        capsule_bytes = canonical_json(capsule.model_dump(mode="json"))
        _write_owned_regular(
            staging_fd,
            _CAPSULE_MARKER_NAME,
            capsule_bytes,
            posix=posix,
        )
        try:
            posix.fsync(staging_fd)
        except (OSError, RuntimeError, TypeError, ValueError):
            raise PreparationError("artifact_io_failed") from None

        workspace.publish(destination_name)
        published = True
        if not _published_directory_matches(staging_fd, results_root_fd, destination_name):
            raise PostPublishVerificationError(
                destination_name,
                publication_path=results_root_path / destination_name,
            )
        try:
            verification = _post_publish_verify(
                staging_fd,
                results_root_fd=results_root_fd,
                destination_name=destination_name,
                persistent_lock_descriptor=persistent_lock_descriptor,
            )
        except PostPublishVerificationError:
            raise
        except Exception:
            raise PostPublishVerificationError(
                destination_name,
                publication_path=results_root_path / destination_name,
            ) from None
        if (
            not _regular_path_matches(
                staging_fd,
                _PERSISTENT_LOCK_NAME,
                persistent_lock_descriptor,
            )
            or not _directory_path_matches(results_root_path, results_root_fd)
            or not _published_directory_matches(staging_fd, results_root_fd, destination_name)
        ):
            raise PostPublishVerificationError(
                destination_name,
                publication_path=results_root_path / destination_name,
            )
        try:
            summary = _make_prepared_plan_summary(
                manifest,
                case_index=case_index,
                plan=plan,
                environment=environment,
                verification=verification,
            )
            result = PreparedCapsule(
                path=results_root_path / destination_name,
                run_id=run_id,
                operation_id=operation_id,
                capsule=capsule,
                summary=summary,
            )
        except Exception:
            raise PostPublishVerificationError(
                destination_name,
                publication_path=results_root_path / destination_name,
            ) from None
    except BaseException as caught:
        primary_error = caught
        published = workspace.staging.state == "published"

    lock_error = (
        None
        if persistent_lock_descriptor is None
        else _release_persistent_lock(persistent_lock_descriptor, posix=posix)
    )
    if primary_error is None and lock_error is not None:
        if isinstance(lock_error, Exception):
            primary_error = (
                PostPublishVerificationError(
                    destination_name,
                    publication_path=results_root_path / destination_name,
                )
                if published
                else PreparationError("artifact_io_failed")
            )
        else:
            primary_error = lock_error
    if primary_error is not None:
        raise primary_error.with_traceback(primary_error.__traceback__)
    assert result is not None
    return result


def _generated_identities() -> tuple[UUID, UUID]:
    run_id = uuid4()
    operation_id = uuid4()
    if (
        type(run_id) is not UUID
        or type(operation_id) is not UUID
        or run_id.version != 4
        or operation_id.version != 4
        or run_id.variant != RFC_4122
        or operation_id.variant != RFC_4122
        or run_id == operation_id
    ):
        raise PreparationError("invalid_generated_identity")
    return run_id, operation_id


def _prepare_capsule_common(
    request: PrepareRequest,
    *,
    shard_request: PrepareShardRequest | None,
) -> PreparedCapsule:
    if type(request) is not PrepareRequest:
        raise PreparationError("invalid_request")
    captured_source = load_source_manifest_capture(
        request.manifest_path,
        input_root=request.input_root,
        invocation_cwd=request.invocation_cwd,
    )
    captured_inputs = capture_authored_inputs(
        captured_source,
        source_root=request.source_root,
    )
    if captured_inputs.resolved_manifest.provider.api_key_env in _RESERVED_API_KEY_ENVIRONMENTS:
        raise PreparationError("reserved_api_key_environment")
    plan_selection = (
        None
        if shard_request is None
        else _materialize_shard_plan_selection(captured_inputs, shard_request)
    )

    provenance = capture_installed_provenance(
        captured_inputs,
        source_root=request.source_root,
        container_image_digest=request.container_image_digest,
    )
    runtime_state = capture_runtime_import_state()
    import_policy = build_import_policy(provenance, runtime_state=runtime_state)
    run_id, operation_id = _generated_identities()
    results_root_path = _absolute_path(request.results_root)

    try:
        results_root_fd = open_directory_no_follow(request.results_root)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise PreparationError("invalid_results_root") from None
    try:
        if not _directory_path_matches(results_root_path, results_root_fd):
            raise PreparationError("results_root_identity_changed")
        posix = cast(FilesystemPosixOps, PosixOps())
        with preparation_filesystem(results_root_fd, operation_id, posix=posix) as workspace:
            environment = project_environment(
                provenance,
                import_environment=import_policy.import_environment,
                filesystem_class=workspace.filesystem_identity.filesystem_class,
            )
            capsule, artifacts, manifest, case_index, plan, environment = _build_artifacts(
                captured_inputs,
                provenance,
                environment,
                run_id,
                operation_id,
                plan_selection,
            )
            return _write_and_publish(
                workspace,
                posix=posix,
                results_root_fd=results_root_fd,
                results_root_path=results_root_path,
                run_id=run_id,
                operation_id=operation_id,
                capsule=capsule,
                artifacts=artifacts,
                manifest=manifest,
                case_index=case_index,
                plan=plan,
                environment=environment,
            )
    except PostPublishSyncError as error:
        if error.publication_path is None:
            raise PostPublishSyncError(
                error.destination_name,
                publication_path=results_root_path / error.destination_name,
            ) from error
        raise
    except PostPublishVerificationError as error:
        if error.publication_path is None:
            raise PostPublishVerificationError(
                error.destination_name,
                publication_path=results_root_path / error.destination_name,
            ) from error
        raise
    except (
        DestinationCollisionError,
        PreparationError,
        UnsupportedFilesystemError,
    ):
        raise
    finally:
        with suppress(OSError):
            os.close(results_root_fd)


def prepare_capsule(request: PrepareRequest) -> PreparedCapsule:
    """Prepare and durably publish one provider-free generation capsule."""

    return _prepare_capsule_common(request, shard_request=None)


def prepare_shard_capsule(request: PrepareShardRequest) -> PreparedCapsule:
    """Prepare one capsule only after recomputing and validating its captured parent projection."""

    if (
        type(request) is not PrepareShardRequest
        or type(request.prepare) is not PrepareRequest
        or not isinstance(request.parent_plan_path, Path)
        or not isinstance(request.shard_plan_path, Path)
    ):
        raise PreparationError("invalid_request")
    return _prepare_capsule_common(request.prepare, shard_request=request)
