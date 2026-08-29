"""Single-read capture of authored manifests and immutable capsule inputs."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias, cast

from pydantic import ValidationError

from laconian_eval.arms import (
    Arm,
    arm_from_captured_bytes,
    arm_member_specs,
    validate_caveman_snapshot,
)
from laconian_eval.capsule.bounded_io import (
    open_directory_no_follow,
    read_regular_file_once,
)
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes, stable_digest
from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_collection_count,
)
from laconian_eval.capsule.manifest_models import (
    ResolvedManifestV2,
    SourceManifestV2,
    V1UpgradeProjection,
    project_v1_manifest,
)
from laconian_eval.capsule.record_models import InputFileRecordV1
from laconian_eval.cases import parse_response_case_bytes
from laconian_eval.models import ResponseCase
from laconian_eval.yaml_io import StrictYamlError, safe_load_unique_bytes

_PathLike: TypeAlias = os.PathLike[str] | str
_SourceManifest: TypeAlias = SourceManifestV2 | V1UpgradeProjection
_CaptureKind: TypeAlias = Literal["case", "arm", "replay", "protocol"]


class CaptureError(ValueError):
    """Content-free capture failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str = "authored input capture failed") -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CapturedSourceManifest:
    """Exact source bytes, validated semantics, and private resolution context."""

    source_bytes: bytes
    source_manifest_commitment_sha256: str
    source_manifest: _SourceManifest
    _input_root: Path = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.source_bytes) is not bytes:
            raise TypeError("captured source manifest must be bytes")
        if sha256_bytes(self.source_bytes) != self.source_manifest_commitment_sha256:
            raise ValueError("source manifest commitment mismatch")
        if not self._input_root.is_absolute():
            raise ValueError("capture input root must be absolute")

    @property
    def source_manifest_schema_version(self) -> Literal["1", "2"]:
        if isinstance(self.source_manifest, V1UpgradeProjection):
            return "1"
        return "2"


@dataclass(frozen=True, slots=True)
class CapturedInputFile:
    """One exact authored byte buffer paired with its immutable input record."""

    record: InputFileRecordV1
    data: bytes

    def __post_init__(self) -> None:
        if type(self.data) is not bytes:
            raise TypeError("captured input must be bytes")
        if self.record.byte_length != len(self.data) or self.record.sha256 != sha256_bytes(
            self.data
        ):
            raise ValueError("captured input metadata mismatch")


@dataclass(frozen=True, slots=True)
class CapturedCaseFile:
    """One parsed case file whose records derive from the same exact byte buffer."""

    source_ordinal: int
    dataset_id: str
    input_file: CapturedInputFile
    cases: tuple[ResponseCase, ...]

    @property
    def data(self) -> bytes:
        return self.input_file.data

    @property
    def record(self) -> InputFileRecordV1:
        return self.input_file.record


@dataclass(frozen=True, slots=True)
class CapturedInputs:
    """Immutable authored inputs and the canonical resolved manifest they bind."""

    source_manifest_commitment_sha256: str
    resolved_manifest: ResolvedManifestV2
    resolved_manifest_bytes: bytes
    manifest_sha256: str
    files: tuple[CapturedInputFile, ...]
    case_files: tuple[CapturedCaseFile, ...]
    arms: tuple[Arm, ...]

    def __post_init__(self) -> None:
        expected_manifest = canonical_json(self.resolved_manifest.model_dump(mode="json"))
        if self.resolved_manifest_bytes != expected_manifest:
            raise ValueError("resolved manifest bytes are not canonical")
        if self.manifest_sha256 != sha256_bytes(self.resolved_manifest_bytes):
            raise ValueError("resolved manifest hash mismatch")
        paths = tuple(item.record.capsule_path for item in self.files)
        if paths != tuple(sorted(paths, key=lambda value: value.encode("utf-8"))):
            raise ValueError("captured files must be sorted by UTF-8 capsule path")
        if len(paths) != len(set(paths)):
            raise ValueError("captured capsule paths must be unique")
        expected_ordinals = tuple(range(len(self.case_files)))
        if tuple(item.source_ordinal for item in self.case_files) != expected_ordinals:
            raise ValueError("captured case files must remain in source order")

    @property
    def records(self) -> tuple[InputFileRecordV1, ...]:
        return tuple(item.record for item in self.files)


@dataclass(slots=True)
class _CaptureBudget:
    total_bytes: int = 0
    case_bytes: int = 0
    arm_bytes: int = 0
    protocol_bytes: int = 0

    def _candidates(self, kind: _CaptureKind) -> tuple[tuple[int, str], ...]:
        total = (
            RESOURCE_LIMITS_V1.captured_input_total_bytes - self.total_bytes,
            "captured_input_total_limit",
        )
        if kind == "case":
            return (
                (RESOURCE_LIMITS_V1.case_file_bytes, "case_file_limit"),
                (
                    RESOURCE_LIMITS_V1.all_case_files_bytes - self.case_bytes,
                    "all_case_files_limit",
                ),
                total,
            )
        if kind == "arm":
            return (
                (RESOURCE_LIMITS_V1.arm_member_bytes, "arm_member_limit"),
                (
                    RESOURCE_LIMITS_V1.all_arm_members_bytes - self.arm_bytes,
                    "all_arm_members_limit",
                ),
                total,
            )
        if kind == "protocol":
            return (
                (RESOURCE_LIMITS_V1.protocol_file_bytes, "protocol_file_limit"),
                (
                    RESOURCE_LIMITS_V1.all_protocol_files_bytes - self.protocol_bytes,
                    "all_protocol_files_limit",
                ),
                total,
            )
        return (
            (RESOURCE_LIMITS_V1.replay_fixture_bytes, "replay_fixture_limit"),
            total,
        )

    def read_limit(self, kind: _CaptureKind) -> tuple[int, str]:
        candidates = self._candidates(kind)
        limit, code = min(candidates, key=lambda item: item[0])
        check_collection_count(0, limit=max(limit, 0), code=code)
        return max(limit, 0), code

    def consume(self, kind: _CaptureKind, data: bytes) -> None:
        candidates = self._candidates(kind)
        for limit, code in candidates:
            check_collection_count(len(data), limit=max(limit, 0), code=code)
        byte_length = len(data)
        self.total_bytes += byte_length
        if kind == "case":
            self.case_bytes += byte_length
        elif kind == "arm":
            self.arm_bytes += byte_length
        elif kind == "protocol":
            self.protocol_bytes += byte_length


def _path_text(value: _PathLike) -> str:
    raw = os.fspath(value)
    if type(raw) is not str or not raw:
        raise CaptureError("invalid_host_path")
    if "\x00" in raw:
        raise CaptureError("invalid_host_path")
    return raw


def _lexical_absolute(value: _PathLike, *, base: Path | None = None) -> Path:
    raw = _path_text(value)
    if not os.path.isabs(raw) and base is not None:
        raw = os.path.join(os.fspath(base), raw)
    return Path(os.path.abspath(raw))


def _open_verified_directory(path: Path, *, code: str) -> int:
    try:
        return open_directory_no_follow(path)
    except (OSError, RuntimeError, ValueError):
        raise CaptureError(code) from None


def _read_absolute_once(path: Path, *, limit: int, code: str) -> bytes:
    name = path.name
    if not name or name in (".", ".."):
        raise CaptureError("invalid_source_path")
    directory_fd = _open_verified_directory(path.parent, code="source_parent_open_failed")
    try:
        try:
            return read_regular_file_once(directory_fd, name, limit=limit, code=code)
        except ResourceLimitError:
            raise
        except (OSError, RuntimeError, ValueError):
            raise CaptureError("source_read_failed") from None
    finally:
        os.close(directory_fd)


def _read_relative_once(
    directory_fd: int,
    path: str,
    *,
    limit: int,
    code: str,
) -> bytes:
    try:
        return read_regular_file_once(directory_fd, path, limit=limit, code=code)
    except ResourceLimitError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise CaptureError("source_read_failed") from None


def _verify_input_root(path: Path) -> None:
    descriptor = _open_verified_directory(path, code="invalid_input_root")
    os.close(descriptor)


def parse_source_manifest_bytes(data: bytes) -> _SourceManifest:
    """Strictly validate source-manifest bytes without resolving referenced inputs."""

    try:
        loaded = safe_load_unique_bytes(
            data,
            byte_limit=RESOURCE_LIMITS_V1.source_manifest_bytes,
            byte_code="source_manifest_limit",
            collection_limit=RESOURCE_LIMITS_V1.case_records,
            collection_code="source_manifest_collection_limit",
            top_level_sequence_limits={
                "case_files": (RESOURCE_LIMITS_V1.case_records, "case_records_limit"),
            },
        )
    except ResourceLimitError:
        raise
    except StrictYamlError as exc:
        raise CaptureError(exc.code, "source manifest is invalid") from None
    if not isinstance(loaded, Mapping) or any(type(key) is not str for key in loaded):
        raise CaptureError("invalid_source_manifest", "source manifest is invalid")
    payload = cast(Mapping[str, object], loaded)
    try:
        if payload.get("schema_version") == "1":
            return project_v1_manifest(payload)
        if payload.get("schema_version") == "2":
            return SourceManifestV2.model_validate(payload)
    except ValidationError:
        raise CaptureError("invalid_source_manifest", "source manifest is invalid") from None
    raise CaptureError("unsupported_source_manifest", "source manifest schema is unsupported")


def load_source_manifest_capture(
    path: _PathLike,
    *,
    input_root: _PathLike | None,
    invocation_cwd: _PathLike,
) -> CapturedSourceManifest:
    """Capture and validate one source manifest with exact v1/v2 path semantics."""

    invocation_root = _lexical_absolute(invocation_cwd)
    manifest_path = _lexical_absolute(path, base=invocation_root)
    source_bytes = _read_absolute_once(
        manifest_path,
        limit=RESOURCE_LIMITS_V1.source_manifest_bytes,
        code="source_manifest_limit",
    )
    source_manifest = parse_source_manifest_bytes(source_bytes)
    if isinstance(source_manifest, V1UpgradeProjection):
        if input_root is not None:
            raise CaptureError("v1_input_root_forbidden", "v1 forbids an input root")
        resolution_root = invocation_root
        _verify_input_root(resolution_root)
    else:
        resolution_root = (
            manifest_path.parent
            if input_root is None
            else _lexical_absolute(input_root, base=invocation_root)
        )
        _verify_input_root(resolution_root)
    return CapturedSourceManifest(
        source_bytes=source_bytes,
        source_manifest_commitment_sha256=sha256_bytes(source_bytes),
        source_manifest=source_manifest,
        _input_root=resolution_root,
    )


def _capture_locator(
    source: CapturedSourceManifest,
    input_root_fd: int | None,
    locator: str,
    *,
    budget: _CaptureBudget,
    kind: _CaptureKind,
    snapshots: dict[str, bytes],
) -> bytes:
    if isinstance(source.source_manifest, V1UpgradeProjection):
        absolute = _lexical_absolute(locator, base=source._input_root)
        snapshot_key = os.fspath(absolute)
    else:
        if input_root_fd is None:
            raise RuntimeError("v2 input-root descriptor is unavailable")
        snapshot_key = locator
    data = snapshots.get(snapshot_key)
    if data is None:
        limit, code = budget.read_limit(kind)
        if isinstance(source.source_manifest, V1UpgradeProjection):
            data = _read_absolute_once(absolute, limit=limit, code=code)
        else:
            assert input_root_fd is not None
            data = _read_relative_once(input_root_fd, locator, limit=limit, code=code)
        snapshots[snapshot_key] = data
    budget.consume(kind, data)
    return data


def _captured_file(
    *,
    role: Literal["case", "arm", "replay", "protocol"],
    role_ordinal: int,
    logical_locator: str,
    capsule_path: str,
    data: bytes,
    dataset_id: str | None = None,
    binding_id: str | None = None,
) -> CapturedInputFile:
    record = InputFileRecordV1.model_validate(
        {
            "role": role,
            "role_ordinal": role_ordinal,
            "logical_locator": logical_locator,
            "capsule_path": capsule_path,
            "byte_length": len(data),
            "sha256": sha256_bytes(data),
            "dataset_id": dataset_id,
            "binding_id": binding_id,
        }
    )
    return CapturedInputFile(record=record, data=data)


def _case_ownership(manifest: _SourceManifest) -> dict[int, str]:
    return {
        ordinal: dataset.dataset_id
        for dataset in manifest.capsule.datasets
        for ordinal in dataset.case_file_ordinals
    }


def _capture_cases(
    source: CapturedSourceManifest,
    input_root_fd: int | None,
    budget: _CaptureBudget,
    snapshots: dict[str, bytes],
) -> tuple[CapturedCaseFile, ...]:
    ownership = _case_ownership(source.source_manifest)
    case_files: list[CapturedCaseFile] = []
    case_count = 0
    for source_ordinal, locator in enumerate(source.source_manifest.case_files):
        data = _capture_locator(
            source,
            input_root_fd,
            locator,
            budget=budget,
            kind="case",
            snapshots=snapshots,
        )
        try:
            cases = parse_response_case_bytes(
                data,
                source=f"case_files[{source_ordinal}]",
                remaining_case_records=RESOURCE_LIMITS_V1.case_records - case_count,
            )
        except ResourceLimitError:
            raise
        except ValueError:
            raise CaptureError("invalid_case_file") from None
        case_count += len(cases)
        dataset_id = ownership[source_ordinal]
        input_file = _captured_file(
            role="case",
            role_ordinal=source_ordinal,
            logical_locator=f"case_files[{source_ordinal}]",
            capsule_path=f"inputs/cases/{source_ordinal:03d}.yaml",
            data=data,
            dataset_id=dataset_id,
        )
        case_files.append(
            CapturedCaseFile(
                source_ordinal=source_ordinal,
                dataset_id=dataset_id,
                input_file=input_file,
                cases=cases,
            )
        )
    _validate_case_ownership(case_files)
    return tuple(case_files)


def _validate_case_ownership(
    case_files: tuple[CapturedCaseFile, ...] | list[CapturedCaseFile],
) -> None:
    case_ids: set[str] = set()
    locales: dict[tuple[str, str], set[str]] = {}
    for case_file in case_files:
        for case in case_file.cases:
            if case.id in case_ids:
                raise CaptureError("duplicate_case_id")
            case_ids.add(case.id)
            key = (case_file.dataset_id, case.scenario_id)
            group = locales.setdefault(key, set())
            if case.locale in group:
                raise CaptureError("dataset_locale_ownership")
            group.add(case.locale)
    if any(group != {"en", "ru"} for group in locales.values()):
        raise CaptureError("dataset_locale_ownership")


def _arm_capsule_path(name: str, member: str) -> str:
    if name in ("baseline", "concise"):
        return f"inputs/arms/{member}"
    return f"inputs/arms/{name}/{member}"


def _capture_arms(
    manifest: _SourceManifest,
    *,
    source_root: _PathLike | None,
    budget: _CaptureBudget,
) -> tuple[tuple[Arm, ...], tuple[CapturedInputFile, ...]]:
    requires_source_root = any(
        spec.source_path is not None for name in manifest.arms for spec in arm_member_specs(name)
    )
    if requires_source_root and source_root is None:
        raise CaptureError("missing_source_root")
    root_fd: int | None = None
    if requires_source_root:
        assert source_root is not None
        root = _lexical_absolute(source_root)
        root_fd = _open_verified_directory(root, code="invalid_source_root")
    arms: list[Arm] = []
    captured_files: list[CapturedInputFile] = []
    try:
        for role_ordinal, name in enumerate(manifest.arms):
            member_bytes: dict[str, bytes] = {}
            for spec in arm_member_specs(name):
                if spec.inline_bytes is not None:
                    data = spec.inline_bytes
                    budget.consume("arm", data)
                else:
                    if spec.source_path is None:
                        raise RuntimeError("file-backed arm member has no source path")
                    if root_fd is None:
                        raise RuntimeError("file-backed arm capture has no source-root descriptor")
                    limit, code = budget.read_limit("arm")
                    data = _read_relative_once(
                        root_fd,
                        spec.source_path,
                        limit=limit,
                        code=code,
                    )
                    budget.consume("arm", data)
                member_bytes[spec.member] = data
            if name == "caveman":
                try:
                    validate_caveman_snapshot(
                        skill=member_bytes["SKILL.md"],
                        source=member_bytes["SOURCE.md"],
                        license_text=member_bytes["LICENSE.txt"],
                    )
                except (TypeError, ValueError):
                    raise CaptureError("caveman_pin_mismatch") from None
            instruction_member = {
                "baseline": "baseline.txt",
                "concise": "concise.txt",
                "caveman": "SKILL.md",
                "if": "SKILL.md",
            }[name]
            try:
                arm = arm_from_captured_bytes(name, member_bytes[instruction_member])
            except (TypeError, ValueError):
                raise CaptureError("invalid_arm_instruction") from None
            arms.append(arm)
            for spec in arm_member_specs(name):
                captured_files.append(
                    _captured_file(
                        role="arm",
                        role_ordinal=role_ordinal,
                        logical_locator=f"arm[{name}]/{spec.member}",
                        capsule_path=_arm_capsule_path(name, spec.member),
                        data=member_bytes[spec.member],
                    )
                )
    finally:
        if root_fd is not None:
            os.close(root_fd)
    return tuple(arms), tuple(captured_files)


def _capture_replay(
    source: CapturedSourceManifest,
    input_root_fd: int | None,
    budget: _CaptureBudget,
    snapshots: dict[str, bytes],
) -> CapturedInputFile | None:
    provider = source.source_manifest.provider
    if provider.kind != "replay":
        return None
    locator = provider.replay_file
    if locator is None:
        raise RuntimeError("validated replay provider has no source locator")
    data = _capture_locator(
        source,
        input_root_fd,
        locator,
        budget=budget,
        kind="replay",
        snapshots=snapshots,
    )
    return _captured_file(
        role="replay",
        role_ordinal=0,
        logical_locator="provider.replay_file",
        capsule_path="inputs/provider/replay.yaml",
        data=data,
    )


def _binding_sha_prefix(binding_id: str) -> str:
    return hashlib.sha256(binding_id.encode("utf-8")).hexdigest()[:16]


def _protocol_capsule_path(ordinal: int, binding_id: str) -> str:
    return f"inputs/protocols/{ordinal:03d}-{_binding_sha_prefix(binding_id)}.bin"


def _capture_protocols(
    source: CapturedSourceManifest,
    input_root_fd: int | None,
    budget: _CaptureBudget,
    snapshots: dict[str, bytes],
) -> tuple[CapturedInputFile, ...]:
    if isinstance(source.source_manifest, V1UpgradeProjection):
        return ()
    captured: list[CapturedInputFile] = []
    for ordinal, binding in enumerate(source.source_manifest.capsule.protocol_bindings):
        data = _capture_locator(
            source,
            input_root_fd,
            binding.path,
            budget=budget,
            kind="protocol",
            snapshots=snapshots,
        )
        captured.append(
            _captured_file(
                role="protocol",
                role_ordinal=ordinal,
                logical_locator=f"capsule.protocol_bindings[{ordinal}].path",
                capsule_path=_protocol_capsule_path(ordinal, binding.binding_id),
                data=data,
                binding_id=binding.binding_id,
            )
        )
    return tuple(captured)


def _dataset_content_digests(
    manifest: _SourceManifest,
    case_files: tuple[CapturedCaseFile, ...],
) -> dict[str, str]:
    records = {case_file.source_ordinal: case_file.record for case_file in case_files}
    digests: dict[str, str] = {}
    for dataset in manifest.capsule.datasets:
        members = []
        for source_ordinal in sorted(dataset.case_file_ordinals):
            record = records[source_ordinal]
            members.append(
                {
                    "source_ordinal": source_ordinal,
                    "capsule_path": record.capsule_path,
                    "byte_length": record.byte_length,
                    "sha256": record.sha256,
                }
            )
        digests[dataset.dataset_id] = stable_digest(
            "laconian-dataset-content-v1",
            {
                "dataset_id": dataset.dataset_id,
                "dataset_version": dataset.dataset_version,
                "members": members,
            },
        )
    return digests


def upgrade_v1_manifest(
    manifest: V1UpgradeProjection,
    *,
    dataset_content_sha256: str,
) -> ResolvedManifestV2:
    """Project the exact v1 compatibility defaults into a resolved v2 manifest."""

    dataset = manifest.capsule.datasets[0]
    provider_replay = "inputs/provider/replay.yaml" if manifest.provider.kind == "replay" else None
    return ResolvedManifestV2.model_validate(
        {
            "schema_version": "2",
            "source_manifest_schema_version": "1",
            "runner_version": manifest.runner_version,
            "run_name": manifest.run_name,
            "provider": {
                "kind": manifest.provider.kind,
                "model": manifest.provider.model,
                "api_key_env": manifest.provider.api_key_env,
                "replay_file": provider_replay,
            },
            "case_files": [
                f"inputs/cases/{ordinal:03d}.yaml" for ordinal in range(len(manifest.case_files))
            ],
            "arms": list(manifest.arms),
            "repetitions": manifest.repetitions,
            "arm_order_seed": manifest.arm_order_seed,
            "instruction_placement": manifest.instruction_placement,
            "schedule_algorithm_version": "laconian-schedule-v1",
            "generation": manifest.generation.model_dump(mode="json"),
            "retry": manifest.retry.model_dump(mode="json"),
            "price_snapshot": (
                None
                if manifest.price_snapshot is None
                else manifest.price_snapshot.model_dump(mode="json")
            ),
            "capsule": {
                "run_purpose": manifest.capsule.run_purpose,
                "claim_intent": manifest.capsule.claim_intent,
                "datasets": [
                    dataset.model_dump(mode="json")
                    | {"dataset_content_sha256": dataset_content_sha256}
                ],
                "comparisons": [
                    comparison.model_dump(mode="json")
                    for comparison in manifest.capsule.comparisons
                ],
                "protocol_bindings": [],
            },
        }
    )


def _resolve_v2_manifest(
    manifest: SourceManifestV2,
    *,
    dataset_digests: Mapping[str, str],
    protocols: tuple[CapturedInputFile, ...],
) -> ResolvedManifestV2:
    resolved_protocols = []
    for binding, captured in zip(
        manifest.capsule.protocol_bindings,
        protocols,
        strict=True,
    ):
        resolved_protocols.append(
            binding.model_dump(mode="json")
            | {
                "path": captured.record.capsule_path,
                "byte_length": captured.record.byte_length,
                "sha256": captured.record.sha256,
            }
        )
    provider_replay = "inputs/provider/replay.yaml" if manifest.provider.kind == "replay" else None
    return ResolvedManifestV2.model_validate(
        {
            "schema_version": "2",
            "source_manifest_schema_version": "2",
            "runner_version": manifest.runner_version,
            "run_name": manifest.run_name,
            "provider": {
                "kind": manifest.provider.kind,
                "model": manifest.provider.model,
                "api_key_env": manifest.provider.api_key_env,
                "replay_file": provider_replay,
            },
            "case_files": [
                f"inputs/cases/{ordinal:03d}.yaml" for ordinal in range(len(manifest.case_files))
            ],
            "arms": list(manifest.arms),
            "repetitions": manifest.repetitions,
            "arm_order_seed": manifest.arm_order_seed,
            "instruction_placement": manifest.instruction_placement,
            "schedule_algorithm_version": "laconian-schedule-v1",
            "generation": manifest.generation.model_dump(mode="json"),
            "retry": manifest.retry.model_dump(mode="json"),
            "price_snapshot": (
                None
                if manifest.price_snapshot is None
                else manifest.price_snapshot.model_dump(mode="json")
            ),
            "capsule": {
                "run_purpose": manifest.capsule.run_purpose,
                "claim_intent": manifest.capsule.claim_intent,
                "datasets": [
                    dataset.model_dump(mode="json")
                    | {"dataset_content_sha256": dataset_digests[dataset.dataset_id]}
                    for dataset in manifest.capsule.datasets
                ],
                "comparisons": [
                    comparison.model_dump(mode="json")
                    for comparison in manifest.capsule.comparisons
                ],
                "protocol_bindings": resolved_protocols,
            },
        }
    )


def capture_authored_inputs(
    source: CapturedSourceManifest,
    *,
    source_root: _PathLike | None,
) -> CapturedInputs:
    """Capture cases, selected arms, replay, and protocols without writing an index."""

    input_root_fd: int | None = None
    if isinstance(source.source_manifest, SourceManifestV2):
        input_root_fd = _open_verified_directory(source._input_root, code="invalid_input_root")
    budget = _CaptureBudget()
    snapshots: dict[str, bytes] = {}
    try:
        case_files = _capture_cases(source, input_root_fd, budget, snapshots)
        arms, arm_files = _capture_arms(
            source.source_manifest,
            source_root=source_root,
            budget=budget,
        )
        replay = _capture_replay(source, input_root_fd, budget, snapshots)
        protocols = _capture_protocols(source, input_root_fd, budget, snapshots)
    finally:
        if input_root_fd is not None:
            os.close(input_root_fd)

    dataset_digests = _dataset_content_digests(source.source_manifest, case_files)
    if isinstance(source.source_manifest, V1UpgradeProjection):
        dataset = source.source_manifest.capsule.datasets[0]
        resolved_manifest = upgrade_v1_manifest(
            source.source_manifest,
            dataset_content_sha256=dataset_digests[dataset.dataset_id],
        )
    else:
        resolved_manifest = _resolve_v2_manifest(
            source.source_manifest,
            dataset_digests=dataset_digests,
            protocols=protocols,
        )
    authored_files = [
        *(case_file.input_file for case_file in case_files),
        *arm_files,
        *protocols,
    ]
    if replay is not None:
        authored_files.append(replay)
    authored_files.sort(key=lambda item: item.record.capsule_path.encode("utf-8"))
    capsule_paths = tuple(item.record.capsule_path for item in authored_files)
    if len(capsule_paths) != len(set(capsule_paths)):
        raise CaptureError("authored_destination_collision")
    resolved_manifest_bytes = canonical_json(resolved_manifest.model_dump(mode="json"))
    return CapturedInputs(
        source_manifest_commitment_sha256=source.source_manifest_commitment_sha256,
        resolved_manifest=resolved_manifest,
        resolved_manifest_bytes=resolved_manifest_bytes,
        manifest_sha256=sha256_bytes(resolved_manifest_bytes),
        files=tuple(authored_files),
        case_files=case_files,
        arms=arms,
    )
