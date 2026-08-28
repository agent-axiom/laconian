"""Installed producer, dependency, and checkout provenance for capsules."""

from __future__ import annotations

import configparser
import csv
import importlib.metadata as metadata
import io
import json
import os
import platform
import posixpath
import re
import stat
import sys
import sysconfig
import tomllib
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from email.parser import BytesParser
from pathlib import Path
from types import MappingProxyType
from typing import Literal, TypeAlias, cast
from urllib.parse import urlsplit

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from pydantic import ValidationError

import laconian_eval
from laconian_eval.capsule.bounded_io import (
    open_directory_no_follow,
    read_regular_file_once,
    read_regular_file_snapshot,
)
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes, stable_digest
from laconian_eval.capsule.capture import CapturedInputFile, CapturedInputs
from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_collection_count,
    check_nesting_depth,
)
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.record_models import (
    DependencyRecordV1,
    EnvironmentV1,
    ImportEnvironmentV1,
    InputFileRecordV1,
    ProviderEnvironmentV1,
    RunnerSourceFileV1,
    RunnerSourceIndexV1,
    RuntimeEnvironmentV1,
    UvLockV1,
)

_PathLike: TypeAlias = os.PathLike[str] | str
_ProviderKind: TypeAlias = Literal["fake", "replay", "openai"]
_CONTAINER_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
_REQUIRES_DIST_HEADER = re.compile(rb"(?im)^requires-dist[ \t]*:")
_VOLATILE_METADATA = frozenset({"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"})
_CANONICAL_REPOSITORY_URL = "https://github.com/agent-axiom/laconian"
_PACKAGE_NAME = "laconian-eval"
_REQUIREMENT_NAME_PREFIX = re.compile(r"^[ \t]*[A-Za-z0-9][A-Za-z0-9._-]*[ \t]*")


class ProvenanceError(ValueError):
    """Content-free producer-provenance failure with a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("producer provenance failed")


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """Private descriptor identity retained for later import-policy checks."""

    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True, slots=True)
class LocalFileOrigin:
    """Private absolute origin and exact capture-time identity."""

    path: Path
    identity: FileIdentity


@dataclass(frozen=True, slots=True)
class _RunnerInventory:
    members: tuple[str, ...]
    identities: Mapping[str, FileIdentity]


@dataclass(frozen=True, slots=True)
class CapturedRunnerSource:
    """Exact installed runner snapshot and copy-ready input-index members."""

    index: RunnerSourceIndexV1
    index_bytes: bytes
    files: tuple[CapturedInputFile, ...] = field(repr=False)
    file_bytes: Mapping[str, bytes] = field(repr=False)
    origins: Mapping[str, LocalFileOrigin] = field(repr=False)
    _package_root: Path = field(repr=False, compare=False)
    _package_parent: Path = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class DistributionFile:
    """One exact retained installed-distribution member."""

    path: str
    byte_length: int
    sha256: str
    data: bytes = field(repr=False, compare=False)
    _origin: Path = field(repr=False, compare=False)
    _identity: FileIdentity = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class DistributionInventory:
    """One installed distribution's stable retained-file commitment."""

    record: DependencyRecordV1
    files: tuple[DistributionFile, ...]
    metadata_bytes: bytes = field(repr=False, compare=False)
    _site_packages_root: Path = field(repr=False, compare=False)
    _captured_byte_length: int = field(repr=False, compare=False)
    _captured_member_count: int = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RunnerDistribution:
    """Private installed runner metadata retained for launcher/import checks."""

    package_version: str
    metadata_bytes: bytes = field(repr=False)
    entry_points_bytes: bytes = field(repr=False)
    direct_url_bytes: bytes | None = field(repr=False)
    files: tuple[str, ...]
    in_root_files: Mapping[str, bytes] = field(repr=False, compare=False)
    origins: Mapping[str, LocalFileOrigin] = field(repr=False, compare=False)
    _site_packages_root: Path = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _DistributionCandidate:
    raw_members: tuple[str, ...]
    root: Path
    dist_info: str
    metadata_path: str
    metadata_bytes: bytes
    metadata_origin: LocalFileOrigin
    record_bytes: bytes
    record_origin: LocalFileOrigin
    name: str
    version: str
    requirements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstalledProvenance:
    """Captured producer commitments awaiting import/filesystem classification."""

    runner_source: CapturedRunnerSource
    runner_distribution: RunnerDistribution
    dependencies: tuple[DistributionInventory, ...]
    package_version: str
    checkout_binding: Literal["bound", "unbound", "unavailable"]
    git_commit: str | None
    git_state: Literal["clean", "dirty", "unavailable"]
    uv_lock: UvLockV1
    provider_kind: _ProviderKind
    requested_model: str
    adapter_source_sha256: str
    transport_policy: Literal["offline", "openai-direct-v1"]
    sdk_distribution: Literal["openai"] | None
    sdk_version: str | None
    container_image_digest: str | None
    python_implementation: str
    python_version: str
    os_family: str
    os_release: str
    architecture: str


def _utf8_sort_key(value: str, *, code: str) -> bytes:
    try:
        return value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ProvenanceError(code) from None


def _absolute_path(value: _PathLike, *, base: Path | None = None) -> Path:
    raw = os.fspath(value)
    if type(raw) is not str or not raw or "\x00" in raw:
        raise ProvenanceError("invalid_source_root")
    if not os.path.isabs(raw) and base is not None:
        raw = os.path.join(os.fspath(base), raw)
    return Path(os.path.abspath(raw))


def _directory_flags() -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if type(no_follow) is not int or type(directory) is not int:
        raise ProvenanceError("unsupported_descriptor_platform")
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    return (
        os.O_RDONLY | no_follow | directory | (close_on_exec if type(close_on_exec) is int else 0)
    )


def _scan_runner_members(root_fd: int) -> _RunnerInventory:
    members: list[str] = []
    identities: dict[str, FileIdentity] = {}
    scanned_entries = 0

    def visit(directory_fd: int, prefix: str) -> None:
        nonlocal scanned_entries
        try:
            directory_before = _file_identity(os.fstat(directory_fd))
        except OSError:
            raise ProvenanceError("runner_inventory_failed") from None
        if not stat.S_ISDIR(directory_before.mode):
            raise ProvenanceError("runner_inventory_failed")
        try:
            entries: list[os.DirEntry[str]] = []
            with os.scandir(directory_fd) as scanner:
                for entry in scanner:
                    check_collection_count(
                        scanned_entries + 1,
                        limit=RESOURCE_LIMITS_V1.dependency_files,
                        code="runner_member_count_limit",
                    )
                    scanned_entries += 1
                    entries.append(entry)
        except OSError:
            raise ProvenanceError("runner_inventory_failed") from None
        for entry in sorted(
            entries,
            key=lambda item: _utf8_sort_key(item.name, code="runner_inventory_failed"),
        ):
            name = entry.name
            if name in (".", "..") or "/" in name or "\x00" in name:
                raise ProvenanceError("unsafe_runner_member")
            path = f"{prefix}/{name}" if prefix else name
            try:
                metadata_record = entry.stat(follow_symlinks=False)
            except OSError:
                raise ProvenanceError("runner_inventory_failed") from None
            member_identity = _file_identity(metadata_record)
            if stat.S_ISLNK(metadata_record.st_mode):
                raise ProvenanceError("unsafe_runner_member")
            if stat.S_ISDIR(metadata_record.st_mode):
                identities[path] = member_identity
                if name == "__pycache__":
                    continue
                try:
                    nested_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
                except OSError:
                    raise ProvenanceError("unsafe_runner_member") from None
                try:
                    if _file_identity(os.fstat(nested_fd)) != member_identity:
                        raise ProvenanceError("unstable_runner_inventory")
                    visit(nested_fd, path)
                finally:
                    os.close(nested_fd)
                continue
            if not stat.S_ISREG(metadata_record.st_mode):
                raise ProvenanceError("unsafe_runner_member")
            identities[path] = member_identity
            if path.endswith(".pyc"):
                continue
            if not path.endswith(".py") and path != "py.typed":
                raise ProvenanceError("unexpected_runner_member")
            members.append(path)
        try:
            directory_after = _file_identity(os.fstat(directory_fd))
        except OSError:
            raise ProvenanceError("runner_inventory_failed") from None
        if directory_before != directory_after:
            raise ProvenanceError("unstable_runner_inventory")
        identities[prefix] = directory_after

    visit(root_fd, "")
    members.sort(key=lambda value: _utf8_sort_key(value, code="runner_inventory_failed"))
    if not members or len(members) != len(set(members)):
        raise ProvenanceError("invalid_runner_inventory")
    return _RunnerInventory(
        members=tuple(members),
        identities=MappingProxyType(identities),
    )


def _file_identity(value: os.stat_result) -> FileIdentity:
    return FileIdentity(
        device=value.st_dev,
        inode=value.st_ino,
        mode=value.st_mode,
        size=value.st_size,
        mtime_ns=value.st_mtime_ns,
        ctime_ns=value.st_ctime_ns,
    )


def _stat_beneath_no_follow(root_fd: int, path: str) -> os.stat_result:
    components = path.split("/")
    if not components or any(part in ("", ".", "..") for part in components):
        raise ProvenanceError("unsafe_regular_file")
    current_fd = os.dup(root_fd)
    try:
        for component in components[:-1]:
            next_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
            previous_fd = current_fd
            current_fd = next_fd
            os.close(previous_fd)
        return os.stat(components[-1], dir_fd=current_fd, follow_symlinks=False)
    finally:
        os.close(current_fd)


def _read_with_identity(
    root_fd: int,
    root: Path,
    path: str,
    *,
    limit: int,
    code: str,
) -> tuple[bytes, LocalFileOrigin]:
    try:
        before = _stat_beneath_no_follow(root_fd, path)
        if not stat.S_ISREG(before.st_mode):
            raise ProvenanceError("unsafe_regular_file")
        snapshot = read_regular_file_snapshot(root_fd, path, limit=limit, code=code)
        after = _stat_beneath_no_follow(root_fd, path)
    except ResourceLimitError:
        raise
    except ProvenanceError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise ProvenanceError("unstable_file_snapshot") from None
    before_identity = _file_identity(before)
    after_identity = _file_identity(after)
    snapshot_identity = FileIdentity(
        device=snapshot.identity.device,
        inode=snapshot.identity.inode,
        mode=snapshot.identity.mode,
        size=snapshot.identity.size,
        mtime_ns=snapshot.identity.mtime_ns,
        ctime_ns=snapshot.identity.ctime_ns,
    )
    if (
        before_identity != snapshot_identity
        or snapshot_identity != after_identity
        or snapshot_identity.size != len(snapshot.data)
    ):
        raise ProvenanceError("unstable_file_snapshot")
    origin = Path(os.path.abspath(os.path.join(os.fspath(root), *path.split("/"))))
    return snapshot.data, LocalFileOrigin(path=origin, identity=snapshot_identity)


def capture_runner_source(
    *,
    package_root: _PathLike | None = None,
    authored_input_bytes: int = 0,
) -> CapturedRunnerSource:
    """Capture the exact installed runner inventory once, ready for capsule copying."""

    if type(authored_input_bytes) is not int or authored_input_bytes < 0:
        raise ResourceLimitError("invalid_count")
    package_path = (
        Path(laconian_eval.__file__).parent
        if package_root is None
        else _absolute_path(package_root)
    )
    try:
        root_fd = open_directory_no_follow(package_path)
    except (OSError, RuntimeError, ValueError):
        raise ProvenanceError("runner_package_unavailable") from None
    try:
        initial_inventory = _scan_runner_members(root_fd)
        members = initial_inventory.members
        source_files: list[RunnerSourceFileV1] = []
        copied_files: list[CapturedInputFile] = []
        buffers: dict[str, bytes] = {}
        origins: dict[str, LocalFileOrigin] = {}
        total = 0
        for ordinal, path in enumerate(members):
            candidates = (
                (RESOURCE_LIMITS_V1.runner_source_file_bytes, "runner_source_file_limit"),
                (
                    max(RESOURCE_LIMITS_V1.all_runner_source_files_bytes - total, 0),
                    "all_runner_source_files_limit",
                ),
                (
                    max(
                        RESOURCE_LIMITS_V1.captured_input_total_bytes
                        - authored_input_bytes
                        - total,
                        0,
                    ),
                    "captured_input_total_limit",
                ),
            )
            limit, code = min(candidates, key=lambda item: item[0])
            data, origin = _read_with_identity(
                root_fd,
                package_path,
                path,
                limit=limit,
                code=code,
            )
            total += len(data)
            check_collection_count(
                total,
                limit=RESOURCE_LIMITS_V1.all_runner_source_files_bytes,
                code="all_runner_source_files_limit",
            )
            check_collection_count(
                authored_input_bytes + total,
                limit=RESOURCE_LIMITS_V1.captured_input_total_bytes,
                code="captured_input_total_limit",
            )
            digest = sha256_bytes(data)
            source_file = RunnerSourceFileV1.model_validate(
                {"path": path, "byte_length": len(data), "sha256": digest}
            )
            record = InputFileRecordV1.model_validate(
                {
                    "role": "runner_source",
                    "role_ordinal": ordinal,
                    "logical_locator": f"package[laconian_eval]/{path}",
                    "capsule_path": f"inputs/software/runner/laconian_eval/{path}",
                    "byte_length": len(data),
                    "sha256": digest,
                    "dataset_id": None,
                    "binding_id": None,
                }
            )
            source_files.append(source_file)
            copied_files.append(CapturedInputFile(record=record, data=data))
            buffers[path] = data
            origins[path] = origin
        try:
            final_inventory = _scan_runner_members(root_fd)
        except ProvenanceError:
            raise ProvenanceError("unstable_runner_inventory") from None
        if (
            final_inventory.members != initial_inventory.members
            or final_inventory.identities != initial_inventory.identities
            or any(
                origins[path].identity != initial_inventory.identities.get(path) for path in members
            )
        ):
            raise ProvenanceError("unstable_runner_inventory")
    except (ResourceLimitError, ProvenanceError):
        raise
    except (OSError, RuntimeError, ValueError, ValidationError):
        raise ProvenanceError("runner_source_capture_failed") from None
    finally:
        os.close(root_fd)

    file_payloads = [item.model_dump(mode="json") for item in source_files]
    root_digest = stable_digest(
        "laconian-runner-source-v1",
        {"package_name": _PACKAGE_NAME, "files": file_payloads},
    )
    try:
        index = RunnerSourceIndexV1.model_validate(
            {
                "schema_version": "1",
                "package_name": _PACKAGE_NAME,
                "files": file_payloads,
                "runner_source_sha256": root_digest,
            }
        )
    except ValidationError:
        raise ProvenanceError("runner_source_index_invalid") from None
    index_bytes = canonical_json(index.model_dump(mode="json"))
    return CapturedRunnerSource(
        index=index,
        index_bytes=index_bytes,
        files=tuple(copied_files),
        file_bytes=MappingProxyType(buffers),
        origins=MappingProxyType(origins),
        _package_root=package_path,
        _package_parent=package_path.parent,
    )


def _distribution_root(distribution: metadata.Distribution) -> Path:
    try:
        root = Path(str(distribution.locate_file("")))
    except (OSError, TypeError, ValueError):
        raise ProvenanceError("distribution_root_unavailable") from None
    return root if root.is_absolute() else Path(os.path.abspath(root))


def _distribution_relative_path(root: Path, raw: str) -> str | None:
    if not raw or raw.startswith(("/", "\\")) or "\\" in raw or "\x00" in raw:
        raise ProvenanceError("invalid_distribution_member")
    normalized = posixpath.normpath(raw)
    absolute = os.path.abspath(os.path.join(os.fspath(root), *normalized.split("/")))
    try:
        common = os.path.commonpath((os.fspath(root), absolute))
    except ValueError:
        raise ProvenanceError("distribution_member_escape") from None
    if common != os.fspath(root):
        return None
    relative = os.path.relpath(absolute, root).replace(os.sep, "/")
    if relative in ("", ".") or relative.startswith("../"):
        raise ProvenanceError("invalid_distribution_member")
    return relative


def _is_cache_member(path: str) -> bool:
    parts = path.split("/")
    return path.endswith(".pyc") or "__pycache__" in parts


def _is_volatile_metadata(path: str, *, dist_info: str) -> bool:
    parent, separator, name = path.rpartition("/")
    return separator == "/" and parent == dist_info and name in _VOLATILE_METADATA


def _is_volatile_metadata_case_variant(path: str, *, dist_info: str) -> bool:
    parent, separator, name = path.rpartition("/")
    return (
        separator == "/"
        and parent == dist_info
        and name not in _VOLATILE_METADATA
        and name.casefold() in {item.casefold() for item in _VOLATILE_METADATA}
    )


def _read_distribution_member(
    root_fd: int,
    root: Path,
    path: str,
    *,
    limit: int | None = None,
    code: str = "distribution_file_limit",
) -> tuple[bytes, LocalFileOrigin]:
    try:
        return _read_with_identity(
            root_fd,
            root,
            path,
            limit=(RESOURCE_LIMITS_V1.dependency_file_bytes if limit is None else limit),
            code=code,
        )
    except ResourceLimitError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise ProvenanceError("distribution_member_read_failed") from None


def _remaining_dependency_file_limit(byte_budget: int, captured_bytes: int) -> int:
    return min(
        RESOURCE_LIMITS_V1.dependency_file_bytes,
        max(byte_budget - captured_bytes, 0),
    )


def _verify_origin(root_fd: int, path: str, origin: LocalFileOrigin) -> None:
    try:
        current = _file_identity(_stat_beneath_no_follow(root_fd, path))
    except OSError:
        raise ProvenanceError("unstable_file_snapshot") from None
    if current != origin.identity:
        raise ProvenanceError("unstable_file_snapshot")


def _open_stable_directory(root_fd: int, path: str) -> tuple[int, FileIdentity]:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, _directory_flags(), dir_fd=root_fd)
        identity = _file_identity(os.fstat(descriptor))
        reachable = _file_identity(_stat_beneath_no_follow(root_fd, path))
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        raise ProvenanceError("unstable_file_snapshot") from None
    assert descriptor is not None
    if identity != reachable or not stat.S_ISDIR(identity.mode):
        os.close(descriptor)
        raise ProvenanceError("unstable_file_snapshot")
    return descriptor, identity


def _verify_stable_directory(
    root_fd: int,
    path: str,
    descriptor: int,
    identity: FileIdentity,
) -> None:
    try:
        descriptor_identity = _file_identity(os.fstat(descriptor))
        reachable_identity = _file_identity(_stat_beneath_no_follow(root_fd, path))
    except OSError:
        raise ProvenanceError("unstable_file_snapshot") from None
    if descriptor_identity != identity or reachable_identity != identity:
        raise ProvenanceError("unstable_file_snapshot")


def _console_scripts(entry_points_bytes: bytes | None) -> Mapping[str, str]:
    if entry_points_bytes is None:
        return MappingProxyType({})
    try:
        text = entry_points_bytes.decode("utf-8", errors="strict")
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str  # type: ignore[method-assign,assignment]
        parser.read_string(text)
        if parser.defaults():
            raise ProvenanceError("invalid_distribution_entry_points")
    except (UnicodeDecodeError, configparser.Error):
        raise ProvenanceError("invalid_distribution_entry_points") from None
    if not parser.has_section("console_scripts"):
        return MappingProxyType({})
    return MappingProxyType(dict(parser.items("console_scripts")))


def _scripts_root(value: _PathLike | None) -> Path:
    raw = sysconfig.get_path("scripts") if value is None else os.fspath(value)
    if type(raw) is not str or not raw or "\x00" in raw or not os.path.isabs(raw):
        raise ProvenanceError("invalid_scripts_root")
    return Path(os.path.abspath(raw))


def _validate_external_members(
    raw_members: Iterable[str],
    scripts: Mapping[str, str],
    *,
    site_packages_root: Path,
    scripts_root: Path,
) -> None:
    for raw in raw_members:
        match = re.fullmatch(r"\.\./\.\./\.\./bin/([^/]+)", raw)
        if match is None:
            raise ProvenanceError("distribution_member_escape")
        script = match.group(1)
        destination = Path(
            os.path.abspath(os.path.join(os.fspath(site_packages_root), *raw.split("/")))
        )
        if script not in scripts or destination != scripts_root / script:
            raise ProvenanceError("distribution_member_escape")


def _check_json_depth_before_parse(data: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in data:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            check_collection_count(
                depth,
                limit=RESOURCE_LIMITS_V1.nesting_depth,
                code="nesting_depth_limit",
            )
        elif byte in (0x5D, 0x7D):
            depth = max(depth - 1, 0)


def _validate_dependency_direct_url(data: bytes | None) -> None:
    if data is None:
        return
    _check_json_depth_before_parse(data)

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    def reject_constant(_value: str) -> object:
        raise ValueError

    try:
        value = json.loads(
            data,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except RecursionError:
        raise ResourceLimitError("nesting_depth_limit") from None
    except (UnicodeDecodeError, ValueError):
        raise ProvenanceError("invalid_dependency_direct_url") from None
    check_nesting_depth(value)
    if not isinstance(value, dict):
        raise ProvenanceError("invalid_dependency_direct_url")
    directory_info = value.get("dir_info", {})
    if directory_info is not None and not isinstance(directory_info, dict):
        raise ProvenanceError("invalid_dependency_direct_url")
    if isinstance(directory_info, dict) and "editable" in directory_info:
        editable = directory_info["editable"]
        if type(editable) is not bool:
            raise ProvenanceError("invalid_dependency_direct_url")
        if editable:
            raise ProvenanceError("editable_dependency")
    url = value.get("url")
    if not isinstance(url, str):
        raise ProvenanceError("invalid_dependency_direct_url")
    try:
        scheme = urlsplit(url).scheme.lower()
    except ValueError:
        raise ProvenanceError("invalid_dependency_direct_url") from None
    if scheme == "file" or scheme.endswith("+file") or not scheme:
        raise ProvenanceError("local_dependency")


def _parse_exact_metadata(
    data: bytes,
    *,
    requirement_limit: int | None = None,
) -> tuple[str, str, tuple[str, ...]]:
    limit = (
        RESOURCE_LIMITS_V1.dependency_requirements
        if requirement_limit is None
        else requirement_limit
    )
    header_boundaries = tuple(
        boundary for separator in (b"\n\n", b"\r\n\r\n") if (boundary := data.find(separator)) >= 0
    )
    header_end = min(header_boundaries, default=len(data))
    requirement_headers = 0
    for _match in _REQUIRES_DIST_HEADER.finditer(data, 0, header_end):
        requirement_headers += 1
        check_collection_count(
            requirement_headers,
            limit=limit,
            code="distribution_requirement_count_limit",
        )
    try:
        message = BytesParser().parsebytes(data)
        names = tuple(message.get_all("Name", ()))
        versions = tuple(message.get_all("Version", ()))
        requirements = tuple(message.get_all("Requires-Dist", ()))
    except (TypeError, ValueError):
        raise ProvenanceError("invalid_distribution_metadata") from None
    if len(names) != 1 or len(versions) != 1:
        raise ProvenanceError("invalid_distribution_metadata")
    name = names[0]
    version = versions[0]
    if not isinstance(name, str) or not isinstance(version, str) or not name or not version:
        raise ProvenanceError("invalid_distribution_metadata")
    if any(not isinstance(item, str) for item in requirements):
        raise ProvenanceError("invalid_distribution_metadata")
    if len(requirements) != requirement_headers:
        raise ProvenanceError("invalid_distribution_metadata")
    return str(canonicalize_name(name)), version, requirements


def _preflight_requirement_extras(data: str) -> None:
    match = _REQUIREMENT_NAME_PREFIX.match(data)
    if match is None or match.end() >= len(data) or data[match.end()] != "[":
        return
    count = 0
    has_item_content = False
    for index in range(match.end() + 1, len(data)):
        character = data[index]
        if character == "]":
            if has_item_content:
                count += 1
                check_collection_count(
                    count,
                    limit=RESOURCE_LIMITS_V1.dependency_marker_contexts,
                    code="distribution_marker_context_limit",
                )
            return
        if character == ",":
            count += 1
            check_collection_count(
                count,
                limit=RESOURCE_LIMITS_V1.dependency_marker_contexts,
                code="distribution_marker_context_limit",
            )
            has_item_content = False
        elif not character.isspace():
            has_item_content = True


def _parse_record(
    data: bytes,
    *,
    member_limit: int | None = None,
) -> tuple[str, ...]:
    try:
        text = data.decode("utf-8", errors="strict")
    except (UnicodeDecodeError, csv.Error):
        raise ProvenanceError("invalid_distribution_record") from None
    limit = RESOURCE_LIMITS_V1.dependency_files if member_limit is None else member_limit
    members: list[str] = []
    try:
        for row in csv.reader(io.StringIO(text, newline=""), strict=True):
            check_collection_count(
                len(members) + 1,
                limit=limit,
                code="distribution_member_count_limit",
            )
            if len(row) != 3 or not row[0]:
                raise ProvenanceError("invalid_distribution_record")
            members.append(row[0])
    except csv.Error:
        raise ProvenanceError("invalid_distribution_record") from None
    if not members:
        raise ProvenanceError("invalid_distribution_record")
    return tuple(members)


def _dist_info_matches(entry_name: str, expected_name: str | None) -> bool:
    if not entry_name.lower().endswith(".dist-info"):
        return False
    stem = entry_name[: -len(".dist-info")]
    if "-" not in stem:
        return False
    raw_name, _ = stem.rsplit("-", 1)
    return expected_name is None or str(canonicalize_name(raw_name)) == expected_name


def _snapshot_candidates_in_root(
    root: Path,
    *,
    expected_name: str | None,
    byte_limit: int | None = None,
    member_limit: int | None = None,
    requirement_limit: int | None = None,
    distribution_limit: int | None = None,
) -> tuple[_DistributionCandidate, ...]:
    bytes_budget = (
        RESOURCE_LIMITS_V1.all_dependency_files_bytes if byte_limit is None else byte_limit
    )
    members_budget = RESOURCE_LIMITS_V1.dependency_files if member_limit is None else member_limit
    requirements_budget = (
        RESOURCE_LIMITS_V1.dependency_requirements
        if requirement_limit is None
        else requirement_limit
    )
    distributions_budget = (
        RESOURCE_LIMITS_V1.dependency_distributions
        if distribution_limit is None
        else distribution_limit
    )
    check_collection_count(0, limit=bytes_budget, code="distribution_bytes_limit")
    check_collection_count(0, limit=members_budget, code="distribution_member_count_limit")
    check_collection_count(
        0,
        limit=requirements_budget,
        code="distribution_requirement_count_limit",
    )
    check_collection_count(
        0,
        limit=distributions_budget,
        code="distribution_candidate_count_limit",
    )
    try:
        root_fd = open_directory_no_follow(root)
    except (OSError, RuntimeError, ValueError):
        raise ProvenanceError("distribution_root_unavailable") from None
    candidates: list[_DistributionCandidate] = []
    captured_bytes = 0
    captured_members = 0
    captured_requirements = 0
    try:
        try:
            entries: list[os.DirEntry[str]] = []
            with os.scandir(root_fd) as scanner:
                for entry in scanner:
                    if not _dist_info_matches(entry.name, expected_name):
                        continue
                    check_collection_count(
                        len(entries) + 1,
                        limit=distributions_budget,
                        code="distribution_candidate_count_limit",
                    )
                    entries.append(entry)
        except OSError:
            raise ProvenanceError("dependency_discovery_failed") from None
        for entry in sorted(
            entries,
            key=lambda item: _utf8_sort_key(item.name, code="dependency_discovery_failed"),
        ):
            try:
                member_stat = entry.stat(follow_symlinks=False)
            except OSError:
                raise ProvenanceError("dependency_discovery_failed") from None
            if stat.S_ISLNK(member_stat.st_mode) or not stat.S_ISDIR(member_stat.st_mode):
                raise ProvenanceError("unsafe_distribution_metadata")
            metadata_path = f"{entry.name}/METADATA"
            record_path = f"{entry.name}/RECORD"
            metadata_bytes, metadata_origin = _read_distribution_member(
                root_fd,
                root,
                metadata_path,
                limit=_remaining_dependency_file_limit(bytes_budget, captured_bytes),
                code="distribution_bytes_limit",
            )
            captured_bytes += len(metadata_bytes)
            record_bytes, record_origin = _read_distribution_member(
                root_fd,
                root,
                record_path,
                limit=_remaining_dependency_file_limit(bytes_budget, captured_bytes),
                code="distribution_bytes_limit",
            )
            captured_bytes += len(record_bytes)
            name, version, requirements = _parse_exact_metadata(
                metadata_bytes,
                requirement_limit=max(requirements_budget - captured_requirements, 0),
            )
            captured_requirements += len(requirements)
            if expected_name is not None and name != expected_name:
                raise ProvenanceError("distribution_identity_mismatch")
            raw_members = _parse_record(
                record_bytes,
                member_limit=max(members_budget - captured_members, 0),
            )
            captured_members += len(raw_members)
            if metadata_path not in raw_members or record_path not in raw_members:
                raise ProvenanceError("invalid_distribution_record")
            candidates.append(
                _DistributionCandidate(
                    raw_members=raw_members,
                    root=root,
                    dist_info=entry.name,
                    metadata_path=metadata_path,
                    metadata_bytes=metadata_bytes,
                    metadata_origin=metadata_origin,
                    record_bytes=record_bytes,
                    record_origin=record_origin,
                    name=name,
                    version=version,
                    requirements=requirements,
                )
            )
    finally:
        os.close(root_fd)
    return tuple(candidates)


def _discover_distribution_candidates(
    name: str,
    *,
    byte_limit: int | None = None,
    member_limit: int | None = None,
    requirement_limit: int | None = None,
    distribution_limit: int | None = None,
) -> tuple[_DistributionCandidate, ...]:
    bytes_budget = (
        RESOURCE_LIMITS_V1.all_dependency_files_bytes if byte_limit is None else byte_limit
    )
    members_budget = RESOURCE_LIMITS_V1.dependency_files if member_limit is None else member_limit
    requirements_budget = (
        RESOURCE_LIMITS_V1.dependency_requirements
        if requirement_limit is None
        else requirement_limit
    )
    distributions_budget = (
        RESOURCE_LIMITS_V1.dependency_distributions
        if distribution_limit is None
        else distribution_limit
    )
    try:
        distributions = metadata.distributions(name=name)
    except (OSError, TypeError, ValueError):
        raise ProvenanceError("dependency_discovery_failed") from None
    roots: dict[str, Path] = {}
    try:
        for distribution_index, distribution in enumerate(distributions, start=1):
            check_collection_count(
                distribution_index,
                limit=distributions_budget,
                code="distribution_candidate_count_limit",
            )
            root = _distribution_root(distribution)
            roots.setdefault(os.fspath(root), root)
    except ResourceLimitError:
        raise
    except ProvenanceError:
        raise
    except (OSError, TypeError, ValueError):
        raise ProvenanceError("dependency_discovery_failed") from None
    candidates: list[_DistributionCandidate] = []
    captured_bytes = 0
    captured_members = 0
    captured_requirements = 0
    captured_distributions = 0
    for root in roots.values():
        root_candidates = _snapshot_candidates_in_root(
            root,
            expected_name=name,
            byte_limit=max(bytes_budget - captured_bytes, 0),
            member_limit=max(members_budget - captured_members, 0),
            requirement_limit=max(requirements_budget - captured_requirements, 0),
            distribution_limit=max(
                distributions_budget - captured_distributions,
                0,
            ),
        )
        candidates.extend(root_candidates)
        captured_bytes += sum(
            len(candidate.metadata_bytes) + len(candidate.record_bytes)
            for candidate in root_candidates
        )
        captured_members += sum(len(candidate.raw_members) for candidate in root_candidates)
        captured_requirements += sum(len(candidate.requirements) for candidate in root_candidates)
        captured_distributions += len(root_candidates)
    return tuple(candidates)


def _optional_unlisted_direct_url(
    root_fd: int,
    root: Path,
    candidate: _DistributionCandidate,
    listed_paths: set[str],
    *,
    limit: int | None = None,
    code: str = "distribution_file_limit",
    member_count: int,
    member_limit: int,
) -> tuple[bytes, LocalFileOrigin] | None:
    direct_url_path = f"{candidate.dist_info}/direct_url.json"
    if direct_url_path in listed_paths:
        return None
    try:
        file_metadata = _stat_beneath_no_follow(root_fd, direct_url_path)
    except FileNotFoundError:
        return None
    except OSError:
        raise ProvenanceError("invalid_dependency_direct_url") from None
    if not stat.S_ISREG(file_metadata.st_mode):
        raise ProvenanceError("invalid_dependency_direct_url")
    check_collection_count(
        member_count + 1,
        limit=member_limit,
        code="distribution_member_count_limit",
    )
    return _read_distribution_member(
        root_fd,
        root,
        direct_url_path,
        limit=limit,
        code=code,
    )


def _capture_distribution_candidate(
    candidate: _DistributionCandidate,
    *,
    scripts_root: _PathLike | None = None,
    byte_limit: int | None = None,
    member_limit: int | None = None,
) -> DistributionInventory:
    bytes_budget = (
        RESOURCE_LIMITS_V1.all_dependency_files_bytes if byte_limit is None else byte_limit
    )
    members_budget = RESOURCE_LIMITS_V1.dependency_files if member_limit is None else member_limit
    captured_bytes = len(candidate.metadata_bytes) + len(candidate.record_bytes)
    check_collection_count(
        captured_bytes,
        limit=bytes_budget,
        code="distribution_bytes_limit",
    )
    check_collection_count(
        len(candidate.raw_members),
        limit=members_budget,
        code="distribution_member_count_limit",
    )
    try:
        root_fd = open_directory_no_follow(candidate.root)
    except (OSError, RuntimeError, ValueError):
        raise ProvenanceError("distribution_root_unavailable") from None
    retained: list[DistributionFile] = []
    exact_buffers: dict[str, bytes] = {}
    external: list[str] = []
    external_seen: set[str] = set()
    normalized_seen: set[str] = set()
    direct_url_bytes: bytes | None = None
    semantic_origins: dict[str, LocalFileOrigin] = {}
    dist_info_fd: int | None = None
    try:
        dist_info_fd, dist_info_identity = _open_stable_directory(root_fd, candidate.dist_info)
        try:
            current_record = _file_identity(
                _stat_beneath_no_follow(root_fd, f"{candidate.dist_info}/RECORD")
            )
        except OSError:
            raise ProvenanceError("unstable_file_snapshot") from None
        if current_record != candidate.record_origin.identity:
            raise ProvenanceError("unstable_file_snapshot")
        for raw in candidate.raw_members:
            relative = _distribution_relative_path(candidate.root, raw)
            if relative is None:
                if raw in external_seen:
                    raise ProvenanceError("duplicate_distribution_member")
                external_seen.add(raw)
                external.append(raw)
                continue
            if relative in normalized_seen:
                raise ProvenanceError("duplicate_distribution_member")
            normalized_seen.add(relative)
            if _is_cache_member(relative):
                continue
            if _is_volatile_metadata_case_variant(relative, dist_info=candidate.dist_info):
                raise ProvenanceError("unsafe_distribution_metadata")
            if _is_volatile_metadata(relative, dist_info=candidate.dist_info):
                if relative == f"{candidate.dist_info}/direct_url.json":
                    direct_url_bytes, direct_url_origin = _read_distribution_member(
                        root_fd,
                        candidate.root,
                        relative,
                        limit=_remaining_dependency_file_limit(
                            bytes_budget,
                            captured_bytes,
                        ),
                        code="distribution_bytes_limit",
                    )
                    captured_bytes += len(direct_url_bytes)
                    semantic_origins[relative] = direct_url_origin
                continue
            if relative == candidate.metadata_path:
                try:
                    current_metadata = _file_identity(_stat_beneath_no_follow(root_fd, relative))
                except OSError:
                    raise ProvenanceError("unstable_file_snapshot") from None
                if current_metadata != candidate.metadata_origin.identity:
                    raise ProvenanceError("unstable_file_snapshot")
                data = candidate.metadata_bytes
                origin = candidate.metadata_origin
            else:
                data, origin = _read_distribution_member(
                    root_fd,
                    candidate.root,
                    relative,
                    limit=_remaining_dependency_file_limit(
                        bytes_budget,
                        captured_bytes,
                    ),
                    code="distribution_bytes_limit",
                )
                captured_bytes += len(data)
            exact_buffers[relative] = data
            retained.append(
                DistributionFile(
                    path=relative,
                    byte_length=len(data),
                    sha256=sha256_bytes(data),
                    data=data,
                    _origin=origin.path,
                    _identity=origin.identity,
                )
            )
        unlisted = _optional_unlisted_direct_url(
            root_fd,
            candidate.root,
            candidate,
            normalized_seen,
            limit=_remaining_dependency_file_limit(bytes_budget, captured_bytes),
            code="distribution_bytes_limit",
            member_count=len(candidate.raw_members),
            member_limit=members_budget,
        )
        if unlisted is not None:
            direct_url_bytes, direct_url_origin = unlisted
            captured_bytes += len(direct_url_bytes)
            semantic_origins[f"{candidate.dist_info}/direct_url.json"] = direct_url_origin
        _verify_origin(
            root_fd,
            f"{candidate.dist_info}/RECORD",
            candidate.record_origin,
        )
        for item in retained:
            _verify_origin(
                root_fd,
                item.path,
                LocalFileOrigin(path=item._origin, identity=item._identity),
            )
        for path, origin in semantic_origins.items():
            _verify_origin(root_fd, path, origin)
        _verify_stable_directory(
            root_fd,
            candidate.dist_info,
            dist_info_fd,
            dist_info_identity,
        )
    finally:
        if dist_info_fd is not None:
            os.close(dist_info_fd)
        os.close(root_fd)
    retained.sort(key=lambda item: item.path.encode("utf-8"))
    metadata_members = [item for item in retained if item.path == candidate.metadata_path]
    if len(metadata_members) != 1 or metadata_members[0].data is not candidate.metadata_bytes:
        raise ProvenanceError("invalid_distribution_metadata")
    entry_points_bytes = exact_buffers.get(f"{candidate.dist_info}/entry_points.txt")
    _validate_external_members(
        external,
        _console_scripts(entry_points_bytes),
        site_packages_root=candidate.root,
        scripts_root=_scripts_root(scripts_root),
    )
    _validate_dependency_direct_url(direct_url_bytes)
    members_payload = [
        {"path": item.path, "byte_length": item.byte_length, "sha256": item.sha256}
        for item in retained
    ]
    root_digest = stable_digest(
        "laconian-distribution-files-v1",
        {"distribution": candidate.name, "files": members_payload},
    )
    try:
        record = DependencyRecordV1.model_validate(
            {
                "distribution": candidate.name,
                "version": candidate.version,
                "files_sha256": root_digest,
            }
        )
    except ValidationError:
        raise ProvenanceError("invalid_distribution_metadata") from None
    return DistributionInventory(
        record=record,
        files=tuple(retained),
        metadata_bytes=candidate.metadata_bytes,
        _site_packages_root=candidate.root,
        _captured_byte_length=captured_bytes,
        _captured_member_count=len(candidate.raw_members) + int(unlisted is not None),
    )


def capture_distribution_inventory(
    distribution: metadata.Distribution,
    *,
    expected_name: str,
    scripts_root: _PathLike | None = None,
) -> DistributionInventory:
    """Hash one installed distribution using its descriptor-read RECORD inventory."""

    if (
        type(expected_name) is not str
        or not expected_name
        or str(canonicalize_name(expected_name)) != expected_name
    ):
        raise ProvenanceError("invalid_dependency_name")
    root = _distribution_root(distribution)
    candidates = _snapshot_candidates_in_root(root, expected_name=expected_name)
    if not candidates:
        raise ProvenanceError("distribution_identity_mismatch")
    if len(candidates) != 1:
        raise ProvenanceError("duplicate_dependency")
    return _capture_distribution_candidate(candidates[0], scripts_root=scripts_root)


def capture_dependency_closure(
    *,
    provider_kind: _ProviderKind = "fake",
    root_distributions: Iterable[str] | None = None,
) -> tuple[DistributionInventory, ...]:
    """Capture the marker-selected PEP 503 installed dependency closure."""

    if provider_kind not in ("fake", "replay", "openai"):
        raise ProvenanceError("invalid_provider_kind")
    roots = (
        root_distributions
        if root_distributions is not None
        else (
            ("pydantic", "pyyaml", "packaging", "openai")
            if provider_kind == "openai"
            else ("pydantic", "pyyaml", "packaging")
        )
    )
    queue: deque[str] = deque()
    queued: set[str] = set()
    requested_extras: dict[str, set[str]] = {}

    def enqueue(name: str) -> None:
        if name in queued:
            return
        check_collection_count(
            len(queued) + 1,
            limit=RESOURCE_LIMITS_V1.dependency_distributions,
            code="distribution_queue_limit",
        )
        queue.append(name)
        queued.add(name)

    for root_count, root in enumerate(roots, start=1):
        check_collection_count(
            root_count,
            limit=RESOURCE_LIMITS_V1.dependency_distributions,
            code="distribution_candidate_count_limit",
        )
        if not isinstance(root, str) or not root:
            raise ProvenanceError("invalid_dependency_name")
        name = str(canonicalize_name(root))
        if name not in requested_extras:
            requested_extras[name] = set()
            enqueue(name)
    candidates_by_name: dict[str, tuple[_DistributionCandidate, ...]] = {}
    evidence_bytes = 0
    evidence_members = 0
    evidence_requirements = 0
    evidence_distributions = 0

    def candidates_for(name: str) -> tuple[_DistributionCandidate, ...]:
        nonlocal evidence_bytes, evidence_distributions
        nonlocal evidence_members, evidence_requirements
        if name not in candidates_by_name:
            candidates = _discover_distribution_candidates(
                name,
                byte_limit=max(
                    RESOURCE_LIMITS_V1.all_dependency_files_bytes - evidence_bytes,
                    0,
                ),
                member_limit=max(
                    RESOURCE_LIMITS_V1.dependency_files - evidence_members,
                    0,
                ),
                requirement_limit=max(
                    RESOURCE_LIMITS_V1.dependency_requirements - evidence_requirements,
                    0,
                ),
                distribution_limit=max(
                    RESOURCE_LIMITS_V1.dependency_distributions - evidence_distributions,
                    0,
                ),
            )
            evidence_bytes += sum(
                len(candidate.metadata_bytes) + len(candidate.record_bytes)
                for candidate in candidates
            )
            evidence_members += sum(len(candidate.raw_members) for candidate in candidates)
            evidence_requirements += sum(len(candidate.requirements) for candidate in candidates)
            evidence_distributions += len(candidates)
            check_collection_count(
                evidence_bytes,
                limit=RESOURCE_LIMITS_V1.all_dependency_files_bytes,
                code="distribution_bytes_limit",
            )
            check_collection_count(
                evidence_members,
                limit=RESOURCE_LIMITS_V1.dependency_files,
                code="distribution_member_count_limit",
            )
            check_collection_count(
                evidence_requirements,
                limit=RESOURCE_LIMITS_V1.dependency_requirements,
                code="distribution_requirement_count_limit",
            )
            check_collection_count(
                evidence_distributions,
                limit=RESOURCE_LIMITS_V1.dependency_distributions,
                code="distribution_candidate_count_limit",
            )
            candidates_by_name[name] = candidates
        return candidates_by_name[name]

    captured: dict[str, DistributionInventory] = {}
    processed_contexts: dict[str, set[str]] = {}
    base_marker_environment = cast(dict[str, str], dict(default_environment()))
    requested_marker_contexts = 0
    requirement_evaluations = 0

    def marker_matches(requirement: Requirement, contexts: set[str]) -> bool:
        nonlocal requirement_evaluations
        if requirement.marker is None:
            return True
        for extra in sorted(contexts, key=lambda value: value.encode("utf-8")):
            check_collection_count(
                requirement_evaluations + 1,
                limit=RESOURCE_LIMITS_V1.dependency_requirement_evaluations,
                code="distribution_requirement_evaluation_limit",
            )
            requirement_evaluations += 1
            if requirement.marker.evaluate(environment={**base_marker_environment, "extra": extra}):
                return True
        return False

    while queue:
        name = queue.popleft()
        queued.remove(name)
        contexts = {"", *requested_extras.get(name, set())}
        new_contexts = contexts - processed_contexts.get(name, set())
        if not new_contexts and name in captured:
            continue
        candidates = candidates_for(name)
        if not candidates:
            raise ProvenanceError("missing_dependency")
        if len(candidates) != 1:
            raise ProvenanceError("duplicate_dependency")
        candidate = candidates[0]
        if name not in captured:
            candidate_base_bytes = len(candidate.metadata_bytes) + len(candidate.record_bytes)
            inventory = _capture_distribution_candidate(
                candidate,
                byte_limit=candidate_base_bytes
                + max(
                    RESOURCE_LIMITS_V1.all_dependency_files_bytes - evidence_bytes,
                    0,
                ),
                member_limit=len(candidate.raw_members)
                + max(RESOURCE_LIMITS_V1.dependency_files - evidence_members, 0),
            )
            captured[name] = inventory
            evidence_bytes += inventory._captured_byte_length - candidate_base_bytes
            evidence_members += inventory._captured_member_count - len(candidate.raw_members)
            check_collection_count(
                evidence_bytes,
                limit=RESOURCE_LIMITS_V1.all_dependency_files_bytes,
                code="distribution_bytes_limit",
            )
            check_collection_count(
                evidence_members,
                limit=RESOURCE_LIMITS_V1.dependency_files,
                code="distribution_member_count_limit",
            )
        for requirement_text in candidate.requirements:
            try:
                check_collection_count(
                    requirement_evaluations + 1,
                    limit=RESOURCE_LIMITS_V1.dependency_requirement_evaluations,
                    code="distribution_requirement_evaluation_limit",
                )
                requirement_evaluations += 1
                _preflight_requirement_extras(requirement_text)
                requirement = Requirement(requirement_text)
                selected = marker_matches(requirement, new_contexts)
            except ResourceLimitError:
                raise
            except (InvalidRequirement, ValueError, KeyError):
                raise ProvenanceError("invalid_dependency_requirement") from None
            if not selected:
                continue
            dependency_name = str(canonicalize_name(requirement.name))
            dependency_candidates = candidates_for(dependency_name)
            if not dependency_candidates:
                raise ProvenanceError("missing_dependency")
            if len(dependency_candidates) != 1:
                raise ProvenanceError("duplicate_dependency")
            installed_version = dependency_candidates[0].version
            if requirement.specifier and not requirement.specifier.contains(
                installed_version, prereleases=True
            ):
                raise ProvenanceError("unsatisfied_dependency")
            if dependency_name not in requested_extras:
                check_collection_count(
                    len(requested_extras) + 1,
                    limit=RESOURCE_LIMITS_V1.dependency_distributions,
                    code="distribution_candidate_count_limit",
                )
                requested_extras[dependency_name] = set()
            known_extras = requested_extras[dependency_name]
            extras_changed = False
            for raw_extra in requirement.extras:
                extra = str(canonicalize_name(raw_extra))
                if extra in known_extras:
                    continue
                check_collection_count(
                    requested_marker_contexts + 1,
                    limit=RESOURCE_LIMITS_V1.dependency_marker_contexts,
                    code="distribution_marker_context_limit",
                )
                known_extras.add(extra)
                requested_marker_contexts += 1
                extras_changed = True
            if dependency_name not in captured or extras_changed:
                enqueue(dependency_name)
        processed_contexts.setdefault(name, set()).update(new_contexts)
    return tuple(
        captured[name] for name in sorted(captured, key=lambda value: value.encode("utf-8"))
    )


def parse_container_image_digest(value: str | None) -> str | None:
    """Validate an explicit container commitment and return its bare digest."""

    if value is None:
        return None
    if type(value) is not str:
        raise ProvenanceError("invalid_container_image_digest")
    match = _CONTAINER_DIGEST.fullmatch(value)
    if match is None:
        raise ProvenanceError("invalid_container_image_digest")
    return match.group(1)


def resolve_source_root(
    explicit_source_root: _PathLike | None,
    *,
    invocation_cwd: _PathLike,
) -> Path | None:
    """Resolve explicit source root, or default only from a matching project CWD."""

    cwd = _absolute_path(invocation_cwd)
    candidate = (
        _absolute_path(explicit_source_root, base=cwd) if explicit_source_root is not None else cwd
    )
    try:
        directory_fd = open_directory_no_follow(candidate)
    except (OSError, RuntimeError, ValueError):
        if explicit_source_root is not None:
            raise ProvenanceError("invalid_source_root") from None
        return None
    if explicit_source_root is not None:
        os.close(directory_fd)
        return candidate
    try:
        try:
            pyproject = read_regular_file_once(
                directory_fd,
                "pyproject.toml",
                limit=RESOURCE_LIMITS_V1.source_manifest_bytes,
                code="source_project_limit",
            )
        except (OSError, RuntimeError, ValueError, ResourceLimitError):
            return None
    finally:
        os.close(directory_fd)
    try:
        payload = tomllib.loads(pyproject.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    project = payload.get("project")
    if not isinstance(project, dict) or project.get("name") != _PACKAGE_NAME:
        return None
    return candidate


def _authored_byte_count(captured_inputs: CapturedInputs) -> int:
    total = 0
    for item in captured_inputs.files:
        if type(item.data) is not bytes:
            raise ProvenanceError("invalid_captured_input")
        total += len(item.data)
        check_collection_count(
            total,
            limit=RESOURCE_LIMITS_V1.captured_input_total_bytes,
            code="captured_input_total_limit",
        )
    return total


def _adapter_digest(runner: CapturedRunnerSource, provider_kind: _ProviderKind) -> str:
    required = ("providers/__init__.py", f"providers/{provider_kind}.py")
    by_path = {item.path: item for item in runner.index.files}
    if any(path not in by_path for path in required):
        raise ProvenanceError("adapter_source_missing")
    members = [by_path[path].model_dump(mode="json") for path in required]
    return stable_digest(
        "laconian-adapter-source-v1",
        {"provider_kind": provider_kind, "files": members},
    )


def _source_binding(
    source_root: Path | None,
    runner: CapturedRunnerSource,
) -> tuple[
    Literal["bound", "unbound", "unavailable"],
    Literal["clean", "dirty", "unavailable"],
    str | None,
    UvLockV1,
]:
    unavailable_lock = UvLockV1.model_validate({"availability": "unavailable", "sha256": None})
    if source_root is None:
        return "unavailable", "unavailable", None, unavailable_lock
    source_package = source_root / "src/laconian_eval"
    try:
        source_inventory = capture_runner_source(package_root=source_package)
    except (OSError, ProvenanceError, ResourceLimitError):
        return "unbound", "unavailable", None, unavailable_lock
    if source_inventory.index.files != runner.index.files:
        return "unbound", "unavailable", None, unavailable_lock

    lock = unavailable_lock
    lock_bytes: bytes | None = None
    try:
        source_fd = open_directory_no_follow(source_root)
        try:
            source_identity = _file_identity(os.fstat(source_fd))
            try:
                _stat_beneath_no_follow(source_fd, "uv.lock")
            except FileNotFoundError:
                lock_bytes = None
            else:
                lock_bytes, _ = _read_with_identity(
                    source_fd,
                    source_root,
                    "uv.lock",
                    limit=RESOURCE_LIMITS_V1.captured_input_total_bytes,
                    code="uv_lock_limit",
                )
            if _file_identity(os.fstat(source_fd)) != source_identity:
                raise ProvenanceError("unsafe_uv_lock")
        finally:
            os.close(source_fd)
    except (OSError, RuntimeError, ValueError, ResourceLimitError):
        raise ProvenanceError("unsafe_uv_lock") from None
    if lock_bytes is not None:
        lock = UvLockV1.model_validate(
            {"availability": "present", "sha256": sha256_bytes(lock_bytes)}
        )
    git_state, commit = _git_attribution(source_root)
    return "bound", git_state, commit, lock


def _git_attribution(
    source_root: Path,
) -> tuple[Literal["clean", "dirty", "unavailable"], str | None]:
    """Fail closed without executing repository-controlled Git configuration."""

    # Worktree-aware Git commands may execute repository-selected fsmonitor hooks or
    # clean filters. A passive preparation boundary therefore records no Git claim.
    del source_root
    return "unavailable", None


def _capture_runner_distribution(*, scripts_root: _PathLike | None = None) -> RunnerDistribution:
    candidates = _discover_distribution_candidates(_PACKAGE_NAME)
    if not candidates:
        raise ProvenanceError("runner_distribution_missing")
    if len(candidates) != 1:
        raise ProvenanceError("runner_distribution_duplicate")
    candidate = candidates[0]
    root = candidate.root
    raw_members = candidate.raw_members
    bytes_budget = RESOURCE_LIMITS_V1.all_dependency_files_bytes
    captured_bytes = len(candidate.metadata_bytes) + len(candidate.record_bytes)
    check_collection_count(
        captured_bytes,
        limit=bytes_budget,
        code="distribution_bytes_limit",
    )
    check_collection_count(
        len(raw_members),
        limit=RESOURCE_LIMITS_V1.dependency_files,
        code="distribution_member_count_limit",
    )
    try:
        root_fd = open_directory_no_follow(root)
    except (OSError, RuntimeError, ValueError):
        raise ProvenanceError("runner_distribution_root_unavailable") from None
    buffers: dict[str, bytes] = {}
    origins: dict[str, LocalFileOrigin] = {}
    external: list[str] = []
    external_seen: set[str] = set()
    seen: set[str] = set()
    unlisted_direct_url_bytes: bytes | None = None
    unlisted_direct_url_origin: LocalFileOrigin | None = None
    dist_info_fd: int | None = None
    try:
        dist_info_fd, dist_info_identity = _open_stable_directory(root_fd, candidate.dist_info)
        try:
            current_record = _file_identity(
                _stat_beneath_no_follow(root_fd, f"{candidate.dist_info}/RECORD")
            )
        except OSError:
            raise ProvenanceError("unstable_file_snapshot") from None
        if current_record != candidate.record_origin.identity:
            raise ProvenanceError("unstable_file_snapshot")
        for raw in raw_members:
            relative = _distribution_relative_path(root, raw)
            if relative is None:
                if raw in external_seen:
                    raise ProvenanceError("runner_distribution_duplicate_member")
                external_seen.add(raw)
                external.append(raw)
                continue
            if relative in seen:
                raise ProvenanceError("runner_distribution_duplicate_member")
            seen.add(relative)
            if _is_cache_member(relative):
                continue
            if _is_volatile_metadata_case_variant(relative, dist_info=candidate.dist_info):
                raise ProvenanceError("invalid_runner_distribution_metadata")
            if relative == candidate.metadata_path:
                try:
                    current_metadata = _file_identity(_stat_beneath_no_follow(root_fd, relative))
                except OSError:
                    raise ProvenanceError("unstable_file_snapshot") from None
                if current_metadata != candidate.metadata_origin.identity:
                    raise ProvenanceError("unstable_file_snapshot")
                data = candidate.metadata_bytes
                origin = candidate.metadata_origin
            elif relative == f"{candidate.dist_info}/RECORD":
                data = candidate.record_bytes
                origin = candidate.record_origin
            else:
                data, origin = _read_distribution_member(
                    root_fd,
                    root,
                    relative,
                    limit=_remaining_dependency_file_limit(
                        bytes_budget,
                        captured_bytes,
                    ),
                    code="distribution_bytes_limit",
                )
                captured_bytes += len(data)
            buffers[relative] = data
            origins[relative] = origin
        unlisted_direct_url = _optional_unlisted_direct_url(
            root_fd,
            root,
            candidate,
            seen,
            limit=_remaining_dependency_file_limit(bytes_budget, captured_bytes),
            code="distribution_bytes_limit",
            member_count=len(raw_members),
            member_limit=RESOURCE_LIMITS_V1.dependency_files,
        )
        if unlisted_direct_url is not None:
            unlisted_direct_url_bytes, unlisted_direct_url_origin = unlisted_direct_url
        for path, origin in origins.items():
            _verify_origin(root_fd, path, origin)
        if unlisted_direct_url_origin is not None:
            _verify_origin(
                root_fd,
                f"{candidate.dist_info}/direct_url.json",
                unlisted_direct_url_origin,
            )
        _verify_stable_directory(
            root_fd,
            candidate.dist_info,
            dist_info_fd,
            dist_info_identity,
        )
    finally:
        if dist_info_fd is not None:
            os.close(dist_info_fd)
        os.close(root_fd)
    entry_point_path = f"{candidate.dist_info}/entry_points.txt"
    direct_url_path = f"{candidate.dist_info}/direct_url.json"
    if candidate.metadata_path not in buffers or entry_point_path not in buffers:
        raise ProvenanceError("invalid_runner_distribution_metadata")
    metadata_bytes = buffers[candidate.metadata_path]
    if (
        metadata_bytes is not candidate.metadata_bytes
        or candidate.name != _PACKAGE_NAME
        or candidate.version != laconian_eval.__version__
    ):
        raise ProvenanceError("runner_version_mismatch")
    entry_points_bytes = buffers[entry_point_path]
    scripts = _console_scripts(entry_points_bytes)
    if scripts != {"laconian": "laconian_eval.cli:entrypoint"}:
        raise ProvenanceError("invalid_runner_console_entry_point")
    _validate_external_members(
        external,
        scripts,
        site_packages_root=root,
        scripts_root=_scripts_root(scripts_root),
    )
    return RunnerDistribution(
        package_version=candidate.version,
        metadata_bytes=metadata_bytes,
        entry_points_bytes=entry_points_bytes,
        direct_url_bytes=buffers.get(direct_url_path, unlisted_direct_url_bytes),
        files=raw_members,
        in_root_files=MappingProxyType(buffers),
        origins=MappingProxyType(origins),
        _site_packages_root=root,
    )


def capture_installed_provenance(
    captured_inputs: CapturedInputs,
    *,
    source_root: _PathLike | None,
    container_image_digest: str | None,
) -> InstalledProvenance:
    """Capture all installed producer commitments without importing a provider SDK."""

    try:
        manifest_payload = captured_inputs.resolved_manifest.model_dump(
            mode="python",
            round_trip=True,
            warnings=False,
        )
        manifest = ResolvedManifestV2.model_validate(manifest_payload)
    except (AttributeError, TypeError, ValueError):
        raise ProvenanceError("invalid_resolved_manifest") from None
    try:
        manifest_bytes = canonical_json(
            manifest.model_dump(mode="json", round_trip=True, warnings=False)
        )
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ProvenanceError("invalid_resolved_manifest") from None
    if (
        type(captured_inputs.resolved_manifest_bytes) is not bytes
        or captured_inputs.resolved_manifest_bytes != manifest_bytes
        or type(captured_inputs.manifest_sha256) is not str
        or captured_inputs.manifest_sha256 != sha256_bytes(manifest_bytes)
    ):
        raise ProvenanceError("manifest_capture_mismatch")
    runner_distribution = _capture_runner_distribution()
    package_version = runner_distribution.package_version
    if manifest.runner_version != package_version:
        raise ProvenanceError("runner_version_mismatch")
    provider_kind = manifest.provider.kind
    authored_bytes = _authored_byte_count(captured_inputs)
    runner = capture_runner_source(authored_input_bytes=authored_bytes)
    dependencies = capture_dependency_closure(provider_kind=provider_kind)
    adapter_digest = _adapter_digest(runner, provider_kind)
    normalized_source_root = None if source_root is None else _absolute_path(source_root)
    checkout_binding, git_state, git_commit, uv_lock = _source_binding(
        normalized_source_root, runner
    )
    if provider_kind == "openai":
        sdk_distribution: Literal["openai"] | None = "openai"
        sdk_inventory = next(
            (item for item in dependencies if item.record.distribution == "openai"), None
        )
        if sdk_inventory is None:
            raise ProvenanceError("missing_provider_sdk")
        sdk_version: str | None = sdk_inventory.record.version
        transport_policy: Literal["offline", "openai-direct-v1"] = "openai-direct-v1"
    else:
        sdk_distribution = None
        sdk_version = None
        transport_policy = "offline"
    return InstalledProvenance(
        runner_source=runner,
        runner_distribution=runner_distribution,
        dependencies=dependencies,
        package_version=package_version,
        checkout_binding=checkout_binding,
        git_commit=git_commit,
        git_state=git_state,
        uv_lock=uv_lock,
        provider_kind=provider_kind,
        requested_model=manifest.provider.model,
        adapter_source_sha256=adapter_digest,
        transport_policy=transport_policy,
        sdk_distribution=sdk_distribution,
        sdk_version=sdk_version,
        container_image_digest=parse_container_image_digest(container_image_digest),
        python_implementation=platform.python_implementation(),
        python_version=sys.version,
        os_family=platform.system(),
        os_release=platform.release(),
        architecture=platform.machine(),
    )


def project_environment(
    provenance: InstalledProvenance,
    *,
    import_environment: ImportEnvironmentV1,
    filesystem_class: str,
) -> EnvironmentV1:
    """Project a complete strict environment once later policy probes are available."""

    try:
        checked_import_environment = ImportEnvironmentV1.model_validate(
            import_environment.model_dump(
                mode="python",
                round_trip=True,
                warnings=False,
            )
        )
    except (AttributeError, TypeError, ValueError):
        raise ProvenanceError("invalid_import_environment") from None
    dependencies = tuple(item.record for item in provenance.dependencies)
    dependency_payloads = [item.model_dump(mode="json") for item in dependencies]
    import_payload = checked_import_environment.model_dump(
        mode="json",
        round_trip=True,
        warnings=False,
    )
    runtime_fingerprint = stable_digest(
        "laconian-runtime-v1",
        {
            "package_version": provenance.package_version,
            "runner_source_sha256": provenance.runner_source.index.runner_source_sha256,
            "dependencies": dependency_payloads,
            "import_environment": import_payload,
            "adapter_source_sha256": provenance.adapter_source_sha256,
        },
    )
    try:
        provider = ProviderEnvironmentV1.model_validate(
            {
                "kind": provenance.provider_kind,
                "requested_model": provenance.requested_model,
                "adapter_source_sha256": provenance.adapter_source_sha256,
                "transport_policy": provenance.transport_policy,
                "sdk_distribution": provenance.sdk_distribution,
                "sdk_version": provenance.sdk_version,
            }
        )
        runtime = RuntimeEnvironmentV1.model_validate(
            {
                "python_implementation": provenance.python_implementation,
                "python_version": provenance.python_version,
                "os_family": provenance.os_family,
                "os_release": provenance.os_release,
                "architecture": provenance.architecture,
                "filesystem_class": filesystem_class,
                "dependencies": dependency_payloads,
                "import_environment": import_payload,
                "runtime_fingerprint_sha256": runtime_fingerprint,
            }
        )
        return EnvironmentV1.model_validate(
            {
                "schema_version": "1",
                "canonical_repository_url": _CANONICAL_REPOSITORY_URL,
                "checkout_binding": provenance.checkout_binding,
                "git_commit": provenance.git_commit,
                "git_state": provenance.git_state,
                "uv_lock": provenance.uv_lock.model_dump(mode="json"),
                "package_name": _PACKAGE_NAME,
                "package_version": provenance.package_version,
                "runner_source_sha256": provenance.runner_source.index.runner_source_sha256,
                "runtime": runtime.model_dump(mode="json"),
                "provider": provider.model_dump(mode="json"),
                "container_image_digest": provenance.container_image_digest,
            }
        )
    except ValidationError:
        raise ProvenanceError("invalid_environment_projection") from None
