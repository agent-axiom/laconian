"""Descriptor-bound import construction and irreversible runtime guard primitives.

These checks are a fail-closed detector for sequential Python-level mutation of the enumerated import surfaces, not a same-process sandbox; native memory access, frame/closure or audit-hook discovery, tracing, and concurrent mutation between audit and loader dispatch require process isolation."""  # noqa: E501

from __future__ import annotations

import _imp
import errno
import fcntl
import importlib.machinery
import importlib.metadata as metadata
import os
import site
import stat
import sys
import sysconfig
import zipimport
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from pathlib import Path
from types import CodeType, MappingProxyType, ModuleType
from typing import Any, Literal, Protocol, cast

from packaging.utils import canonicalize_name

from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import sha256_bytes, stable_digest
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.provenance import (
    CapturedRunnerSource,
    DistributionFile,
    DistributionInventory,
    FileIdentity,
    InstalledProvenance,
    LocalFileOrigin,
)
from laconian_eval.capsule.record_models import (
    DependencyRecordV1,
    ImportEnvironmentV1,
    ImportRootV1,
    RunnerSourceIndexV1,
)
from laconian_eval.capsule.schema import (
    CONSOLE_LAUNCHER_TEMPLATE_SHA256 as _SCHEMA_CONSOLE_LAUNCHER_TEMPLATE_SHA256,
)

CONSOLE_LAUNCHER_TEMPLATE = (
    b"#!<CURRENT_INTERPRETER>\n"
    b"# -*- coding: utf-8 -*-\n"
    b"import sys\n"
    b"from laconian_eval.cli import entrypoint\n"
    b'if __name__ == "__main__":\n'
    b'    if sys.argv[0].endswith("-script.pyw"):\n'
    b"        sys.argv[0] = sys.argv[0][:-11]\n"
    b'    elif sys.argv[0].endswith(".exe"):\n'
    b"        sys.argv[0] = sys.argv[0][:-4]\n"
    b"    sys.exit(entrypoint())\n"
)
CONSOLE_LAUNCHER_TEMPLATE_SHA256 = _SCHEMA_CONSOLE_LAUNCHER_TEMPLATE_SHA256
_VIRTUALENV_PTH = b"import _virtualenv"
_RUNNER_PATH_PTH = "_editable_impl_laconian_eval.pth"
_GUARD_MEMBER = "capsule/import_policy.py"
_FIXED_MODULE_ALIASES = {
    "os.path": "posixpath" if os.name == "posix" else "ntpath",
    "importlib._bootstrap": "_frozen_importlib",
    "importlib._bootstrap_external": "_frozen_importlib_external",
}
_IDENTITY_MODULE_ALIASES = {"__mp_main__": "__main__"}
_MODULE_ALIAS_TARGETS = {**_FIXED_MODULE_ALIASES, **_IDENTITY_MODULE_ALIASES}
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
_REGULAR_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_BUILTIN_FIND_SPEC_DESCRIPTOR = importlib.machinery.BuiltinImporter.__dict__["find_spec"]
_FROZEN_FIND_SPEC_DESCRIPTOR = importlib.machinery.FrozenImporter.__dict__["find_spec"]
_PATH_FIND_SPEC_DESCRIPTOR = importlib.machinery.PathFinder.__dict__["find_spec"]
_FILE_FINDER_FIND_SPEC_DESCRIPTOR = importlib.machinery.FileFinder.__dict__["find_spec"]
_BUILTIN_FIND_SPEC_FUNCTION = _BUILTIN_FIND_SPEC_DESCRIPTOR.__func__
_FROZEN_FIND_SPEC_FUNCTION = _FROZEN_FIND_SPEC_DESCRIPTOR.__func__
_PATH_FIND_SPEC_FUNCTION = _PATH_FIND_SPEC_DESCRIPTOR.__func__
_FILE_FINDER_FIND_SPEC_FUNCTION = _FILE_FINDER_FIND_SPEC_DESCRIPTOR
_BUILTIN_FIND_SPEC_CODE = _BUILTIN_FIND_SPEC_FUNCTION.__code__
_FROZEN_FIND_SPEC_CODE = _FROZEN_FIND_SPEC_FUNCTION.__code__
_PATH_FIND_SPEC_CODE = _PATH_FIND_SPEC_FUNCTION.__code__
_FILE_FINDER_FIND_SPEC_CODE = _FILE_FINDER_FIND_SPEC_FUNCTION.__code__
_MAPPING_PROXY_TYPE: type[object] = type(MappingProxyType({}))


class ImportPolicyError(ValueError):
    """A content-free import-policy failure with a stable machine code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("import policy failed")


@dataclass(frozen=True, slots=True)
class DirectoryIdentity:
    device: int
    inode: int
    mode: int
    canonical_path: Path = field(repr=False, compare=True)


@dataclass(frozen=True, slots=True)
class VerifiedDirectory:
    identity: DirectoryIdentity
    role: str

    @property
    def canonical_path(self) -> Path:
        return self.identity.canonical_path


@dataclass(frozen=True, slots=True)
class InterpreterLayout:
    stdlib_root: VerifiedDirectory
    destshared_root: VerifiedDirectory
    platstdlib_mode: Literal["same_as_stdlib", "omitted"]
    zip_placeholder: Path = field(repr=False)


@dataclass(frozen=True, slots=True)
class SiteBootstrap:
    runner_import_mode: Literal["wheel", "path"]
    virtualenv_bootstrap_sha256: str | None
    virtualenv_finder: object | None = field(repr=False)
    virtualenv_module: Path | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class RuntimeImportState:
    sys_path: tuple[str, ...] = field(repr=False)
    meta_path: tuple[object, ...] = field(repr=False)
    path_hooks: tuple[object, ...] = field(repr=False)
    importer_cache: Mapping[str, object | None] = field(repr=False)
    modules: Mapping[str, object] = field(repr=False)
    environ: Mapping[str, str] = field(repr=False)
    executable: str = field(repr=False)
    argv0: str = field(repr=False)
    cwd: Path = field(repr=False)
    user_site_enabled: bool | None
    user_site: Path | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class _RegularSnapshot:
    data: bytes = field(repr=False)
    metadata: os.stat_result = field(repr=False)
    canonical_path: Path = field(repr=False)


@dataclass(frozen=True, slots=True)
class _OwnedOrigin:
    module_name: str
    distribution: str
    member: str
    canonical_path: Path = field(repr=False)
    identity: FileIdentity = field(repr=False)
    captured_source: bytes | None = field(repr=False)
    root: VerifiedDirectory = field(repr=False)


@dataclass(frozen=True, slots=True)
class _FileFinderBinding:
    key: str = field(repr=False)
    finder: object = field(repr=False)
    path: str = field(repr=False)
    loaders: tuple[tuple[str, object], ...] = field(repr=False)


class _FindSpec(Protocol):
    def __call__(self, fullname: str) -> importlib.machinery.ModuleSpec | None: ...


def _descriptor_path(descriptor: int, fallback: str) -> Path:
    raw: str | None = None
    if sys.platform == "darwin":
        try:
            result = fcntl.fcntl(descriptor, 50, b"\0" * 1024)
            if isinstance(result, bytes):
                raw = os.fsdecode(result.split(b"\0", 1)[0])
        except (OSError, TypeError, ValueError):
            raw = None
    elif os.path.exists("/proc/self/fd"):
        try:
            raw = os.readlink(f"/proc/self/fd/{descriptor}")
        except OSError:
            raw = None
    if raw is None:
        raw = os.path.realpath(fallback)
    if not raw or not os.path.isabs(raw) or "\x00" in raw:
        raise ImportPolicyError("invalid_descriptor_path")
    return Path(os.path.normpath(raw))


def _directory_stat(path: os.PathLike[str] | str) -> tuple[DirectoryIdentity, int]:
    raw = os.fspath(path)
    if type(raw) is not str or not raw or "\x00" in raw:
        raise ImportPolicyError("invalid_import_directory")
    descriptor = -1
    canonical_descriptor = -1
    try:
        descriptor = os.open(raw, _DIRECTORY_FLAGS)
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ImportPolicyError("invalid_import_directory")
        canonical = _descriptor_path(descriptor, raw)
        canonical_descriptor = open_directory_no_follow(canonical)
        canonical_metadata = os.fstat(canonical_descriptor)
        if not stat.S_ISDIR(canonical_metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != (
            canonical_metadata.st_dev,
            canonical_metadata.st_ino,
        ):
            raise ImportPolicyError("invalid_import_directory")
        return (
            DirectoryIdentity(
                device=metadata.st_dev,
                inode=metadata.st_ino,
                mode=metadata.st_mode,
                canonical_path=canonical,
            ),
            descriptor,
        )
    except ImportPolicyError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except (OSError, TypeError, ValueError):
        if descriptor >= 0:
            os.close(descriptor)
        raise ImportPolicyError("invalid_import_directory") from None
    finally:
        if canonical_descriptor >= 0:
            os.close(canonical_descriptor)


def directory_identity(path: os.PathLike[str] | str) -> DirectoryIdentity:
    """Resolve a directory spelling through an opened descriptor and return physical identity."""

    identity, descriptor = _directory_stat(path)
    os.close(descriptor)
    return identity


def _same_directory(left: DirectoryIdentity, right: DirectoryIdentity) -> bool:
    return (left.device, left.inode) == (right.device, right.inode)


def _is_beneath(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.fspath(path), os.fspath(root))) == os.fspath(root)
    except ValueError:
        return False


def _read_bounded(descriptor: int, limit: int, code: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        try:
            chunk = os.read(descriptor, min(64 * 1024, limit + 1 - total))
        except InterruptedError:
            continue
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ImportPolicyError(code)
    raise ImportPolicyError(code)


def _regular_snapshot(
    path: os.PathLike[str] | str,
    *,
    code: str,
    follow_leaf: bool = False,
    read: bool = True,
) -> _RegularSnapshot:
    raw_path = Path(os.fspath(path))
    if not raw_path.is_absolute() or not raw_path.name:
        raise ImportPolicyError(code)
    parent = directory_identity(raw_path.parent)
    parent_fd = -1
    descriptor = -1
    try:
        parent_fd = open_directory_no_follow(parent.canonical_path)
        flags = (
            _REGULAR_FLAGS if not follow_leaf else (_REGULAR_FLAGS & ~getattr(os, "O_NOFOLLOW", 0))
        )
        descriptor = os.open(raw_path.name, flags, dir_fd=parent_fd)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ImportPolicyError(code)
        data = (
            _read_bounded(descriptor, RESOURCE_LIMITS_V1.runner_source_file_bytes, code)
            if read
            else b""
        )
        after = os.fstat(descriptor)
        if (
            not stat.S_ISREG(after.st_mode)
            or _stat_identity_tuple(before) != _stat_identity_tuple(after)
            or (read and len(data) != before.st_size)
        ):
            raise ImportPolicyError(code)
        canonical = _descriptor_path(descriptor, os.fspath(raw_path))
        return _RegularSnapshot(data=data, metadata=after, canonical_path=canonical)
    except ImportPolicyError:
        raise
    except (OSError, TypeError, ValueError):
        raise ImportPolicyError(code) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_fd >= 0:
            os.close(parent_fd)


def _stat_identity_tuple(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _captured_identity_tuple(value: FileIdentity) -> tuple[int, int, int, int, int, int]:
    return (value.device, value.inode, value.mode, value.size, value.mtime_ns, value.ctime_ns)


def _project_import_environment(value: object, *, code: str) -> Mapping[str, str]:
    try:
        python_path = cast(Any, value)["PYTHONPATH"]
    except KeyError:
        python_path = ""
    except (AttributeError, OSError, TypeError, ValueError):
        raise ImportPolicyError(code) from None
    try:
        python_home = cast(Any, value)["PYTHONHOME"]
    except KeyError:
        python_home = ""
    except (AttributeError, OSError, TypeError, ValueError):
        raise ImportPolicyError(code) from None
    if type(python_path) is not str or type(python_home) is not str:
        raise ImportPolicyError(code)
    return MappingProxyType({"PYTHONPATH": python_path, "PYTHONHOME": python_home})


def capture_runtime_import_state() -> RuntimeImportState:
    """Capture import-relevant process state without changing it."""

    try:
        environ = _project_import_environment(os.environ, code="runtime_state_capture_failed")
        raw_user_site = site.USER_SITE
        if raw_user_site is None or (type(raw_user_site) is str and not raw_user_site):
            user_site = None
        elif type(raw_user_site) is str:
            user_site = Path(raw_user_site)
        else:
            raise ImportPolicyError("runtime_state_capture_failed")
        return RuntimeImportState(
            sys_path=tuple(sys.path),
            meta_path=tuple(sys.meta_path),
            path_hooks=tuple(sys.path_hooks),
            importer_cache=MappingProxyType(dict(sys.path_importer_cache)),
            modules=MappingProxyType(dict(sys.modules)),
            environ=environ,
            executable=sys.executable,
            argv0=sys.argv[0],
            cwd=Path(os.getcwd()),
            user_site_enabled=site.ENABLE_USER_SITE,
            user_site=user_site,
        )
    except (OSError, TypeError, ValueError):
        raise ImportPolicyError("runtime_state_capture_failed") from None


def validate_interpreter_layout(
    *,
    stdlib: os.PathLike[str] | str,
    destshared: os.PathLike[str] | str | None,
    platstdlib: os.PathLike[str] | str | None,
    base_prefix: os.PathLike[str] | str,
    version: tuple[int, int],
) -> InterpreterLayout:
    """Verify CPython library roots and the one removable zip placeholder."""

    if destshared is None:
        raise ImportPolicyError("missing_destshared")
    if (
        type(version) is not tuple
        or len(version) != 2
        or any(type(component) is not int or component < 0 for component in version)
    ):
        raise ImportPolicyError("invalid_interpreter_version")
    base = directory_identity(base_prefix)
    stdlib_identity = directory_identity(stdlib)
    destshared_identity = directory_identity(destshared)
    if not _is_beneath(stdlib_identity.canonical_path, base.canonical_path):
        raise ImportPolicyError("stdlib_outside_base_prefix")
    if not _is_beneath(destshared_identity.canonical_path, base.canonical_path):
        raise ImportPolicyError("destshared_outside_base_prefix")
    platstdlib_mode: Literal["same_as_stdlib", "omitted"] = "omitted"
    if platstdlib is not None:
        platstdlib_identity = directory_identity(platstdlib)
        if _same_directory(platstdlib_identity, stdlib_identity):
            platstdlib_mode = "same_as_stdlib"
    zip_placeholder = stdlib_identity.canonical_path.parent / f"python{version[0]}{version[1]}.zip"
    try:
        os.lstat(zip_placeholder)
    except FileNotFoundError:
        pass
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise ImportPolicyError("stdlib_zip_probe_failed") from None
    else:
        raise ImportPolicyError("existing_stdlib_zip")
    return InterpreterLayout(
        stdlib_root=VerifiedDirectory(stdlib_identity, "stdlib"),
        destshared_root=VerifiedDirectory(destshared_identity, "destshared"),
        platstdlib_mode=platstdlib_mode,
        zip_placeholder=zip_placeholder,
    )


def _discover_interpreter_layout() -> InterpreterLayout:
    stdlib = sysconfig.get_path("stdlib")
    platstdlib = sysconfig.get_path("platstdlib")
    destshared = sysconfig.get_config_var("DESTSHARED")
    if type(stdlib) is not str or type(platstdlib) is not str:
        raise ImportPolicyError("invalid_interpreter_layout")
    if destshared is not None and type(destshared) is not str:
        raise ImportPolicyError("invalid_interpreter_layout")
    return validate_interpreter_layout(
        stdlib=stdlib,
        destshared=destshared,
        platstdlib=platstdlib,
        base_prefix=sys.base_prefix,
        version=(sys.version_info.major, sys.version_info.minor),
    )


def verify_console_launcher(
    launcher: os.PathLike[str] | str,
    *,
    executable: os.PathLike[str] | str,
) -> str:
    """Verify and normalize the exact generated ``laconian`` console wrapper."""

    snapshot = _regular_snapshot(launcher, code="launcher_not_regular")
    try:
        shebang, remainder = snapshot.data.split(b"\n", 1)
    except ValueError:
        raise ImportPolicyError("invalid_launcher_shebang") from None
    if not shebang.startswith(b"#!"):
        raise ImportPolicyError("invalid_launcher_shebang")
    if shebang.endswith(b"\r"):
        raise ImportPolicyError("launcher_template_mismatch")
    try:
        interpreter = os.fsdecode(shebang[2:])
    except (TypeError, UnicodeError):
        raise ImportPolicyError("invalid_launcher_shebang") from None
    if (
        not interpreter
        or not os.path.isabs(interpreter)
        or any(character in interpreter for character in ("\x00", "\r", "\n"))
    ):
        raise ImportPolicyError("invalid_launcher_shebang")
    expected_executable = os.fspath(executable)
    if type(expected_executable) is not str or not os.path.isabs(expected_executable):
        raise ImportPolicyError("launcher_interpreter_mismatch")
    shebang_identity = _regular_snapshot(
        interpreter,
        code="launcher_interpreter_mismatch",
        follow_leaf=True,
        read=False,
    ).metadata
    executable_identity = _regular_snapshot(
        expected_executable,
        code="launcher_interpreter_mismatch",
        follow_leaf=True,
        read=False,
    ).metadata
    if (shebang_identity.st_dev, shebang_identity.st_ino) != (
        executable_identity.st_dev,
        executable_identity.st_ino,
    ):
        raise ImportPolicyError("launcher_interpreter_mismatch")
    normalized = b"#!<CURRENT_INTERPRETER>\n" + remainder
    if normalized != CONSOLE_LAUNCHER_TEMPLATE:
        raise ImportPolicyError("launcher_template_mismatch")
    if sha256_bytes(normalized) != CONSOLE_LAUNCHER_TEMPLATE_SHA256:
        raise ImportPolicyError("launcher_template_mismatch")
    return CONSOLE_LAUNCHER_TEMPLATE_SHA256


def classify_pth_file(
    name: str,
    data: bytes,
    *,
    runner_parent: os.PathLike[str] | str,
) -> Literal["virtualenv", "runner_path"]:
    """Classify one narrowly supported site bootstrap file."""

    if type(name) is not str or type(data) is not bytes:
        raise ImportPolicyError("invalid_path_pth")
    if name.endswith(".egg-link"):
        raise ImportPolicyError("egg_link_unsupported")
    if name == "_virtualenv.pth" and data == _VIRTUALENV_PTH:
        return "virtualenv"
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError:
        raise ImportPolicyError("invalid_path_pth") from None
    lines = text.splitlines()
    if any(line.startswith(("import ", "import\t")) for line in lines):
        raise ImportPolicyError("unknown_executable_pth")
    if name != _RUNNER_PATH_PTH or "\x00" in text or "\r" in text or len(lines) != 1:
        raise ImportPolicyError("invalid_path_pth")
    target = lines[0]
    if not target or not os.path.isabs(target):
        raise ImportPolicyError("invalid_path_pth")
    if not _same_directory(directory_identity(target), directory_identity(runner_parent)):
        raise ImportPolicyError("unknown_pth_target")
    return "runner_path"


def _virtualenv_candidate(value: object) -> bool:
    return (
        getattr(value, "__module__", None) == "_virtualenv"
        and getattr(value, "__qualname__", None) == "_Finder"
    ) or (type(value).__module__ == "_virtualenv" and type(value).__qualname__ == "_Finder")


def _bootstrap_entry_bytes(root: Path, name: str) -> bytes:
    return _regular_snapshot(root / name, code="invalid_site_bootstrap").data


def _sorted_directory_entries(
    scanner: Iterable[os.DirEntry[str]],
    *,
    already_seen: int,
    reverse: bool = False,
) -> tuple[list[os.DirEntry[str]], int]:
    entries: list[os.DirEntry[str]] = []
    seen = already_seen
    for entry in scanner:
        seen += 1
        if seen > RESOURCE_LIMITS_V1.dependency_files:
            raise ResourceLimitError("import_directory_entry_count_limit")
        entries.append(entry)
    entries.sort(key=lambda item: os.fsencode(item.name), reverse=reverse)
    return entries, seen


def inspect_site_bootstrap(
    site_roots: tuple[Path, ...],
    *,
    runner_parent: Path,
    meta_path: tuple[object, ...],
) -> SiteBootstrap:
    """Enumerate every active site-root bootstrap file and bind supported exceptions."""

    verified_roots: list[DirectoryIdentity] = []
    seen: set[tuple[int, int]] = set()
    for site_root in site_roots:
        identity = directory_identity(site_root)
        key = (identity.device, identity.inode)
        if key not in seen:
            verified_roots.append(identity)
            seen.add(key)
    runner_identity = directory_identity(runner_parent)
    path_entries = 0
    virtualenv: tuple[DirectoryIdentity, bytes] | None = None
    virtualenv_modules: list[tuple[DirectoryIdentity, bytes]] = []
    scanned_entries = 0
    for verified_root in verified_roots:
        root_fd = -1
        try:
            root_fd = open_directory_no_follow(verified_root.canonical_path)
            before = os.fstat(root_fd)
            with os.scandir(root_fd) as scanner:
                entries, scanned_entries = _sorted_directory_entries(
                    scanner,
                    already_seen=scanned_entries,
                )
        except ResourceLimitError:
            if root_fd >= 0:
                os.close(root_fd)
            raise
        except OSError:
            if root_fd >= 0:
                os.close(root_fd)
            raise ImportPolicyError("site_bootstrap_scan_failed") from None
        try:
            for entry in entries:
                if entry.name.endswith((".pth", ".egg-link")):
                    data = _bootstrap_entry_bytes(verified_root.canonical_path, entry.name)
                    kind = classify_pth_file(entry.name, data, runner_parent=runner_parent)
                    if kind == "runner_path":
                        path_entries += 1
                    elif virtualenv is not None:
                        raise ImportPolicyError("duplicate_virtualenv_bootstrap")
                    else:
                        virtualenv = (verified_root, data)
                elif entry.name == "_virtualenv.py":
                    virtualenv_modules.append(
                        (
                            verified_root,
                            _bootstrap_entry_bytes(verified_root.canonical_path, entry.name),
                        )
                    )
            after = os.fstat(root_fd)
            if _stat_identity_tuple(before) != _stat_identity_tuple(after):
                raise ImportPolicyError("site_bootstrap_changed")
        except OSError:
            raise ImportPolicyError("site_bootstrap_changed") from None
        finally:
            if root_fd >= 0:
                os.close(root_fd)
    runner_in_site = any(_same_directory(runner_identity, root) for root in verified_roots)
    if runner_in_site:
        if path_entries:
            raise ImportPolicyError("unexpected_runner_path_pth")
        runner_mode: Literal["wheel", "path"] = "wheel"
    else:
        if path_entries != 1:
            raise ImportPolicyError("missing_runner_path_pth")
        runner_mode = "path"
    finder_candidates = tuple(item for item in meta_path if _virtualenv_candidate(item))
    if virtualenv is None:
        if finder_candidates or virtualenv_modules:
            raise ImportPolicyError("unexpected_virtualenv_bootstrap")
        return SiteBootstrap(runner_mode, None, None, None)
    if len(finder_candidates) != 1:
        raise ImportPolicyError("missing_virtualenv_finder")
    if len(virtualenv_modules) != 1 or not _same_directory(virtualenv[0], virtualenv_modules[0][0]):
        raise ImportPolicyError("missing_virtualenv_module")
    module_path = virtualenv_modules[0][0].canonical_path / "_virtualenv.py"
    loaded_virtualenv = sys.modules.get("_virtualenv")
    loaded_path = getattr(loaded_virtualenv, "__file__", None)
    if type(loaded_path) is not str:
        raise ImportPolicyError("virtualenv_module_origin_mismatch")
    loaded_snapshot = _regular_snapshot(
        loaded_path,
        code="virtualenv_module_origin_mismatch",
        read=False,
    )
    expected_snapshot = _regular_snapshot(
        module_path,
        code="virtualenv_module_origin_mismatch",
        read=False,
    )
    if (loaded_snapshot.metadata.st_dev, loaded_snapshot.metadata.st_ino) != (
        expected_snapshot.metadata.st_dev,
        expected_snapshot.metadata.st_ino,
    ):
        raise ImportPolicyError("virtualenv_module_origin_mismatch")
    finder_type = getattr(loaded_virtualenv, "_Finder", None)
    if finder_type is None or type(finder_candidates[0]) is not finder_type:
        raise ImportPolicyError("virtualenv_finder_identity_mismatch")
    digest = stable_digest(
        "laconian-import-bootstrap-v1",
        {
            "pth_sha256": sha256_bytes(virtualenv[1]),
            "module_sha256": sha256_bytes(virtualenv_modules[0][1]),
        },
    )
    return SiteBootstrap(runner_mode, digest, finder_candidates[0], module_path)


@dataclass(frozen=True, slots=True)
class ImportPolicy:
    """Private fixed runtime policy plus its path-free serialized projection."""

    import_environment: ImportEnvironmentV1
    initial_state: RuntimeImportState = field(repr=False)
    runtime_state: RuntimeImportState = field(repr=False)
    allowed_roots: tuple[VerifiedDirectory, ...] = field(repr=False)
    stdlib_root: VerifiedDirectory
    destshared_root: VerifiedDirectory
    site_roots: tuple[VerifiedDirectory, ...] = field(repr=False)
    runner_parent_root: VerifiedDirectory = field(repr=False)
    runner_package_root: VerifiedDirectory = field(repr=False)
    zip_placeholder: Path = field(repr=False)
    bootstrap: SiteBootstrap
    file_finder_hook: object = field(repr=False)
    cache_bindings: tuple[_FileFinderBinding, ...] = field(repr=False)
    owned_origins: Mapping[str, _OwnedOrigin] = field(repr=False)
    originless_modules: Mapping[str, object] = field(repr=False)
    fixed_alias_modules: Mapping[str, object] = field(repr=False)
    launcher_mode: Literal["module", "console_script"]
    launcher_path: Path | None = field(repr=False)
    launcher_identity: FileIdentity | None = field(repr=False)
    virtualenv_module: Path | None = field(repr=False)
    enforcement_token: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _EnforcementSnapshot:
    token: object = field(repr=False)
    runtime_state: RuntimeImportState = field(repr=False)
    cache_bindings: tuple[_FileFinderBinding, ...] = field(repr=False)
    allowed_roots: tuple[VerifiedDirectory, ...] = field(repr=False)
    stdlib_root: VerifiedDirectory
    destshared_root: VerifiedDirectory
    site_roots: tuple[VerifiedDirectory, ...] = field(repr=False)
    runner_parent_root: VerifiedDirectory = field(repr=False)
    owned_origins: Mapping[str, _OwnedOrigin] = field(repr=False)
    virtualenv_finder: object | None = field(repr=False)
    virtualenv_find_spec: object | None = field(repr=False)
    virtualenv_find_spec_code: object | None = field(repr=False)
    path_find_spec: Callable[[str, object, object], object] = field(repr=False)
    builtin_find_spec_code: object = field(repr=False)
    frozen_find_spec_code: object = field(repr=False)
    path_find_spec_code: object = field(repr=False)
    file_finder_find_spec_code: object = field(repr=False)
    file_finder_hook_code: object = field(repr=False)
    enforce_fixed_finders: bool


def _copy_runtime_state(value: RuntimeImportState) -> RuntimeImportState:
    if type(value) is not RuntimeImportState:
        raise ImportPolicyError("invalid_runtime_state")
    if (
        any(type(item) is not str or "\x00" in item for item in value.sys_path)
        or type(value.executable) is not str
        or not value.executable
        or type(value.argv0) is not str
        or not isinstance(value.cwd, Path)
        or value.user_site_enabled not in (True, False, None)
    ):
        raise ImportPolicyError("invalid_runtime_state")
    environ = _project_import_environment(value.environ, code="invalid_runtime_state")
    if any(type(key) is not str for key in value.importer_cache):
        raise ImportPolicyError("invalid_runtime_state")
    if any(type(key) is not str for key in value.modules):
        raise ImportPolicyError("invalid_runtime_state")
    return RuntimeImportState(
        sys_path=tuple(value.sys_path),
        meta_path=tuple(value.meta_path),
        path_hooks=tuple(value.path_hooks),
        importer_cache=MappingProxyType(dict(value.importer_cache)),
        modules=MappingProxyType(dict(value.modules)),
        environ=environ,
        executable=value.executable,
        argv0=value.argv0,
        cwd=value.cwd,
        user_site_enabled=value.user_site_enabled,
        user_site=value.user_site,
    )


def _fixed_path_find_spec(fullname: str, path: object, target: object) -> object:
    return _PATH_FIND_SPEC_FUNCTION(importlib.machinery.PathFinder, fullname, path, target)


def _build_enforcement_snapshot(
    policy: ImportPolicy,
    *,
    path_find_spec: Callable[[str, object, object], object] | None = None,
) -> _EnforcementSnapshot:
    virtualenv_finder = policy.bootstrap.virtualenv_finder
    virtualenv_find_spec: object | None = None
    virtualenv_find_spec_code: object | None = None
    if virtualenv_finder is not None:
        virtualenv_find_spec = type(virtualenv_finder).__dict__.get("find_spec")
        if not callable(virtualenv_find_spec):
            raise ImportPolicyError("unknown_meta_path_finder")
        virtualenv_find_spec_code = getattr(virtualenv_find_spec, "__code__", None)
        if virtualenv_find_spec_code is None:
            raise ImportPolicyError("unknown_meta_path_finder")
    file_finder_hook_code = getattr(policy.file_finder_hook, "__code__", None)
    if file_finder_hook_code is None:
        raise ImportPolicyError("unknown_path_hook")
    snapshot = _EnforcementSnapshot(
        token=policy.enforcement_token,
        runtime_state=policy.runtime_state,
        cache_bindings=policy.cache_bindings,
        allowed_roots=policy.allowed_roots,
        stdlib_root=policy.stdlib_root,
        destshared_root=policy.destshared_root,
        site_roots=policy.site_roots,
        runner_parent_root=policy.runner_parent_root,
        owned_origins=policy.owned_origins,
        virtualenv_finder=virtualenv_finder,
        virtualenv_find_spec=virtualenv_find_spec,
        virtualenv_find_spec_code=virtualenv_find_spec_code,
        path_find_spec=_fixed_path_find_spec if path_find_spec is None else path_find_spec,
        builtin_find_spec_code=_BUILTIN_FIND_SPEC_CODE,
        frozen_find_spec_code=_FROZEN_FIND_SPEC_CODE,
        path_find_spec_code=_PATH_FIND_SPEC_CODE,
        file_finder_find_spec_code=_FILE_FINDER_FIND_SPEC_CODE,
        file_finder_hook_code=file_finder_hook_code,
        enforce_fixed_finders=path_find_spec is None,
    )
    if snapshot.enforce_fixed_finders:
        _revalidate_fixed_finder_descriptors(snapshot)
    return snapshot


def _revalidate_fixed_finder_descriptors(snapshot: _EnforcementSnapshot) -> None:
    if (
        importlib.machinery.BuiltinImporter.__dict__.get("find_spec")
        is not _BUILTIN_FIND_SPEC_DESCRIPTOR
        or importlib.machinery.FrozenImporter.__dict__.get("find_spec")
        is not _FROZEN_FIND_SPEC_DESCRIPTOR
        or importlib.machinery.PathFinder.__dict__.get("find_spec")
        is not _PATH_FIND_SPEC_DESCRIPTOR
        or importlib.machinery.FileFinder.__dict__.get("find_spec")
        is not _FILE_FINDER_FIND_SPEC_DESCRIPTOR
        or _BUILTIN_FIND_SPEC_FUNCTION.__code__ is not snapshot.builtin_find_spec_code
        or _FROZEN_FIND_SPEC_FUNCTION.__code__ is not snapshot.frozen_find_spec_code
        or _PATH_FIND_SPEC_FUNCTION.__code__ is not snapshot.path_find_spec_code
        or _FILE_FINDER_FIND_SPEC_FUNCTION.__code__ is not snapshot.file_finder_find_spec_code
    ):
        raise ImportPolicyError("meta_path_finder_drift")
    finder = snapshot.virtualenv_finder
    if finder is not None and type(finder).__dict__.get("find_spec") is not (
        snapshot.virtualenv_find_spec
    ):
        raise ImportPolicyError("meta_path_finder_drift")
    if finder is not None and getattr(snapshot.virtualenv_find_spec, "__code__", None) is not (
        snapshot.virtualenv_find_spec_code
    ):
        raise ImportPolicyError("meta_path_finder_drift")
    hook = snapshot.runtime_state.path_hooks[1]
    if getattr(hook, "__code__", None) is not snapshot.file_finder_hook_code:
        raise ImportPolicyError("path_hooks_drift")


def _validated_file_finder_hook(path_hooks: tuple[object, ...]) -> object:
    if len(path_hooks) != 2 or path_hooks[0] is not zipimport.zipimporter:
        raise ImportPolicyError("unknown_path_hook")
    candidate = path_hooks[1]
    trusted = importlib.machinery.FileFinder.path_hook(
        (importlib.machinery.ExtensionFileLoader, importlib.machinery.EXTENSION_SUFFIXES),
        (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES),
        (importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES),
    )
    if not callable(candidate):
        raise ImportPolicyError("unknown_path_hook")
    candidate_code = getattr(candidate, "__code__", None)
    trusted_code = getattr(trusted, "__code__", None)
    if candidate_code is not trusted_code:
        raise ImportPolicyError("unknown_path_hook")
    candidate_closure = getattr(candidate, "__closure__", None)
    trusted_closure = getattr(trusted, "__closure__", None)
    if candidate_closure is None or trusted_closure is None:
        raise ImportPolicyError("unknown_path_hook")
    try:
        candidate_values = tuple(cell.cell_contents for cell in candidate_closure)
        trusted_values = tuple(cell.cell_contents for cell in trusted_closure)
    except (AttributeError, TypeError, ValueError):
        raise ImportPolicyError("unknown_path_hook") from None
    if len(candidate_values) != 2 or len(trusted_values) != 2:
        raise ImportPolicyError("unknown_path_hook")
    if candidate_values[0] is not trusted_values[0]:
        raise ImportPolicyError("unknown_path_hook")
    candidate_loaders = candidate_values[1]
    trusted_loaders = trusted_values[1]
    if not isinstance(candidate_loaders, tuple) or not isinstance(trusted_loaders, tuple):
        raise ImportPolicyError("unknown_path_hook")
    normalized_candidate = tuple(
        (loader, tuple(suffixes)) for loader, suffixes in candidate_loaders
    )
    normalized_trusted = tuple((loader, tuple(suffixes)) for loader, suffixes in trusted_loaders)
    if normalized_candidate != normalized_trusted:
        raise ImportPolicyError("unknown_path_hook")
    return candidate


def _validated_meta_path(
    meta_path: tuple[object, ...], bootstrap: SiteBootstrap
) -> tuple[object, ...]:
    expected = (
        *((bootstrap.virtualenv_finder,) if bootstrap.virtualenv_finder is not None else ()),
        importlib.machinery.BuiltinImporter,
        importlib.machinery.FrozenImporter,
        importlib.machinery.PathFinder,
    )
    if len(meta_path) != len(expected) or any(
        actual is not required for actual, required in zip(meta_path, expected, strict=True)
    ):
        raise ImportPolicyError("unknown_meta_path_finder")
    return expected


def _validate_captured_origin(
    origin: LocalFileOrigin,
    *,
    expected: Path,
    code: str,
) -> Path:
    if type(origin) is not LocalFileOrigin or type(origin.identity) is not FileIdentity:
        raise ImportPolicyError(code)
    snapshot = _regular_snapshot(origin.path, code=code, read=False)
    if snapshot.canonical_path != expected or _stat_identity_tuple(
        snapshot.metadata
    ) != _captured_identity_tuple(origin.identity):
        raise ImportPolicyError(code)
    return snapshot.canonical_path


def _safe_member(value: str) -> str:
    if (
        type(value) is not str
        or not value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or "\x00" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ImportPolicyError("invalid_inventory_member")
    return value


def _extension_module_stem(filename: str) -> str | None:
    for suffix in sorted(importlib.machinery.EXTENSION_SUFFIXES, key=len, reverse=True):
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
    return None


def _member_module_name(prefix: str, member: str) -> str | None:
    parts = member.split("/")
    leaf = parts[-1]
    if leaf.endswith(".py"):
        leaf = leaf[:-3]
    else:
        extension_stem = _extension_module_stem(leaf)
        if extension_stem is None:
            return None
        leaf = extension_stem
    parts[-1] = leaf
    if parts[-1] == "__init__":
        parts.pop()
    if not parts:
        return prefix or None
    if any(not part.isidentifier() for part in parts):
        return None
    return ".".join((prefix, *parts)) if prefix else ".".join(parts)


def _validate_runner_capture(
    runner: CapturedRunnerSource,
) -> tuple[VerifiedDirectory, VerifiedDirectory, dict[str, _OwnedOrigin]]:
    if type(runner) is not CapturedRunnerSource:
        raise ImportPolicyError("runner_capture_mismatch")
    try:
        checked_index = RunnerSourceIndexV1.model_validate(
            runner.index.model_dump(mode="python", round_trip=True, warnings=False)
        )
    except (AttributeError, TypeError, ValueError):
        raise ImportPolicyError("runner_capture_mismatch") from None
    if checked_index != runner.index:
        raise ImportPolicyError("runner_capture_mismatch")
    records = tuple(checked_index.files)
    members = tuple(record.path for record in records)
    if set(members) != set(runner.file_bytes) or set(members) != set(runner.origins):
        raise ImportPolicyError("runner_capture_mismatch")
    expected_digest = stable_digest(
        "laconian-runner-source-v1",
        {
            "package_name": "laconian-eval",
            "files": [record.model_dump(mode="json") for record in records],
        },
    )
    if checked_index.runner_source_sha256 != expected_digest:
        raise ImportPolicyError("runner_capture_mismatch")
    package_root = VerifiedDirectory(directory_identity(runner._package_root), "runner_package")
    package_parent = VerifiedDirectory(directory_identity(runner._package_parent), "runner_parent")
    if package_root.canonical_path.parent != package_parent.canonical_path:
        raise ImportPolicyError("runner_capture_mismatch")
    owned: dict[str, _OwnedOrigin] = {}
    for record in records:
        member = _safe_member(record.path)
        data = runner.file_bytes[member]
        if (
            type(data) is not bytes
            or len(data) != record.byte_length
            or sha256_bytes(data) != record.sha256
        ):
            raise ImportPolicyError("runner_capture_mismatch")
        expected = package_root.canonical_path / member
        canonical = _validate_captured_origin(
            runner.origins[member], expected=expected, code="captured_origin_changed"
        )
        module_name = _member_module_name("laconian_eval", member)
        if module_name is None:
            continue
        owned[os.fspath(canonical)] = _OwnedOrigin(
            module_name=module_name,
            distribution="laconian-eval",
            member=member,
            canonical_path=canonical,
            identity=runner.origins[member].identity,
            captured_source=data if member.endswith(".py") else None,
            root=package_root,
        )
    return package_root, package_parent, owned


def _validate_distribution_capture(
    inventory: DistributionInventory,
) -> tuple[VerifiedDirectory, dict[str, _OwnedOrigin]]:
    if type(inventory) is not DistributionInventory:
        raise ImportPolicyError("dependency_capture_mismatch")
    try:
        checked_record = DependencyRecordV1.model_validate(
            inventory.record.model_dump(mode="python", round_trip=True, warnings=False)
        )
    except (AttributeError, TypeError, ValueError):
        raise ImportPolicyError("dependency_capture_mismatch") from None
    if checked_record != inventory.record:
        raise ImportPolicyError("dependency_capture_mismatch")
    root = VerifiedDirectory(
        directory_identity(inventory._site_packages_root),
        f"site:{checked_record.distribution}",
    )
    member_payloads: list[dict[str, object]] = []
    owned: dict[str, _OwnedOrigin] = {}
    seen: set[str] = set()
    for item in inventory.files:
        if type(item) is not DistributionFile:
            raise ImportPolicyError("dependency_capture_mismatch")
        member = _safe_member(item.path)
        if member in seen:
            raise ImportPolicyError("dependency_capture_mismatch")
        seen.add(member)
        if (
            type(item.data) is not bytes
            or len(item.data) != item.byte_length
            or sha256_bytes(item.data) != item.sha256
        ):
            raise ImportPolicyError("dependency_capture_mismatch")
        member_payloads.append(
            {"path": member, "byte_length": item.byte_length, "sha256": item.sha256}
        )
        expected = root.canonical_path / member
        origin = LocalFileOrigin(path=item._origin, identity=item._identity)
        canonical = _validate_captured_origin(
            origin, expected=expected, code="captured_origin_changed"
        )
        module_name = _member_module_name("", member)
        if module_name is None:
            continue
        owned[os.fspath(canonical)] = _OwnedOrigin(
            module_name=module_name,
            distribution=checked_record.distribution,
            member=member,
            canonical_path=canonical,
            identity=item._identity,
            captured_source=item.data if member.endswith(".py") else None,
            root=root,
        )
    expected_digest = stable_digest(
        "laconian-distribution-files-v1",
        {"distribution": checked_record.distribution, "files": member_payloads},
    )
    if expected_digest != checked_record.files_sha256:
        raise ImportPolicyError("dependency_capture_mismatch")
    return root, owned


def derive_import_roots_from_members(
    distribution_members: Mapping[str, tuple[str, ...]],
    *,
    package_owners: Mapping[str, tuple[str, ...]],
) -> tuple[ImportRootV1, ...]:
    """Derive selected top-level records from package ownership and retained member names."""

    normalized_members: dict[str, tuple[str, ...]] = {}
    executable: dict[str, bool] = {}
    for raw_distribution, raw_members in distribution_members.items():
        distribution = canonicalize_name(raw_distribution)
        members = tuple(_safe_member(item) for item in raw_members)
        normalized_members[distribution] = members
        executable[distribution] = any(
            _member_module_name("", member) is not None for member in members
        )
    roots: list[ImportRootV1] = []
    covered: set[str] = set()
    seen_modules: set[str] = set()
    for module in sorted(package_owners, key=lambda item: item.encode("utf-8")):
        owners = tuple(
            sorted(
                {
                    canonicalize_name(owner)
                    for owner in package_owners[module]
                    if canonicalize_name(owner) in normalized_members
                },
                key=lambda item: item.encode("utf-8"),
            )
        )
        if not owners:
            continue
        if len(owners) != 1:
            raise ImportPolicyError("duplicate_import_ownership")
        distribution = owners[0]
        candidates: list[str] = []
        for member in normalized_members[distribution]:
            if _member_module_name("", member) == module:
                candidates.append(member)
        if not candidates:
            if any(
                member.startswith(f"{module}/") and _member_module_name("", member) is not None
                for member in normalized_members[distribution]
            ):
                raise ImportPolicyError("namespace_import_unsupported")
            raise ImportPolicyError("missing_import_root")
        preferred = tuple(
            member
            for member in candidates
            if member == f"{module}/__init__.py"
            or member == f"{module}.py"
            or _extension_module_stem(member) == module
        )
        if len(preferred) != 1 or module in seen_modules:
            raise ImportPolicyError("duplicate_import_ownership")
        seen_modules.add(module)
        covered.add(distribution)
        try:
            roots.append(
                ImportRootV1.model_validate(
                    {
                        "distribution": distribution,
                        "module": module,
                        "origin_member": preferred[0],
                    }
                )
            )
        except (TypeError, ValueError):
            raise ImportPolicyError("invalid_import_root") from None
    if any(
        has_code and distribution not in covered for distribution, has_code in executable.items()
    ):
        raise ImportPolicyError("missing_import_root")
    return tuple(
        sorted(
            roots,
            key=lambda root: (
                root.distribution.encode("utf-8"),
                root.module.encode("utf-8"),
                root.origin_member.encode("utf-8"),
            ),
        )
    )


def _spec_origin_snapshot(spec: importlib.machinery.ModuleSpec) -> _RegularSnapshot:
    if spec.origin is None:
        portions = spec.submodule_search_locations
        if portions is not None and len(tuple(portions)) > 1:
            raise ImportPolicyError("multiple_import_portions")
        raise ImportPolicyError("namespace_import_unsupported")
    if type(spec.origin) is not str or not os.path.isabs(spec.origin):
        raise ImportPolicyError("import_origin_not_allowed")
    if isinstance(spec.loader, zipimport.zipimporter) or ".zip/" in spec.origin:
        raise ImportPolicyError("zip_import_unsupported")
    return _regular_snapshot(spec.origin, code="import_origin_not_regular", read=False)


def validate_mapped_import_spec(
    module: str,
    distribution: str,
    dependencies: tuple[DistributionInventory, ...],
    *,
    find_spec: _FindSpec,
) -> ImportRootV1:
    """Bind a mapped top-level spec to exactly one retained distribution member."""

    normalized_distribution = canonicalize_name(distribution)
    inventory = next(
        (item for item in dependencies if item.record.distribution == normalized_distribution),
        None,
    )
    if inventory is None:
        raise ImportPolicyError("import_origin_wrong_distribution")
    try:
        spec = find_spec(module)
    except (ImportError, AttributeError, TypeError, ValueError):
        raise ImportPolicyError("missing_import_spec") from None
    if spec is None:
        raise ImportPolicyError("missing_import_spec")
    if not isinstance(spec, importlib.machinery.ModuleSpec):
        raise ImportPolicyError("missing_import_spec")
    snapshot = _spec_origin_snapshot(spec)
    matching_member: DistributionFile | None = None
    for item in inventory.files:
        origin = LocalFileOrigin(path=item._origin, identity=item._identity)
        canonical = _validate_captured_origin(
            origin,
            expected=directory_identity(inventory._site_packages_root).canonical_path / item.path,
            code="captured_origin_changed",
        )
        if canonical == snapshot.canonical_path:
            matching_member = item
            break
    if matching_member is None:
        for other in dependencies:
            for item in other.files:
                if item._origin == snapshot.canonical_path:
                    raise ImportPolicyError("import_origin_wrong_distribution")
        selected_roots = tuple(
            directory_identity(item._site_packages_root) for item in dependencies
        )
        if any(
            _is_beneath(snapshot.canonical_path, root.canonical_path) for root in selected_roots
        ):
            raise ImportPolicyError("unowned_import_origin")
        raise ImportPolicyError("import_origin_not_allowed")
    if _stat_identity_tuple(snapshot.metadata) != _captured_identity_tuple(
        matching_member._identity
    ):
        raise ImportPolicyError("captured_origin_changed")
    expected_module = _member_module_name("", matching_member.path)
    if expected_module != module:
        raise ImportPolicyError("import_origin_wrong_distribution")
    try:
        return ImportRootV1.model_validate(
            {
                "distribution": normalized_distribution,
                "module": module,
                "origin_member": matching_member.path,
            }
        )
    except (TypeError, ValueError):
        raise ImportPolicyError("invalid_import_root") from None


def _validate_console_entry_point(provenance: InstalledProvenance) -> None:
    data = provenance.runner_distribution.entry_points_bytes
    if type(data) is not bytes:
        raise ImportPolicyError("invalid_console_entry_point")
    try:
        lines = data.decode("utf-8", errors="strict").splitlines()
    except UnicodeError:
        raise ImportPolicyError("invalid_console_entry_point") from None
    section: str | None = None
    scripts: list[tuple[str, str]] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section == "console_scripts" and "=" in line:
            name, target = line.split("=", 1)
            scripts.append((name.strip(), target.strip()))
    if scripts != [("laconian", "laconian_eval.cli:entrypoint")]:
        raise ImportPolicyError("invalid_console_entry_point")


def _detect_launcher(
    provenance: InstalledProvenance,
    state: RuntimeImportState,
    owned: Mapping[str, _OwnedOrigin],
) -> tuple[
    Literal["module", "console_script"],
    str | None,
    Path | None,
    DirectoryIdentity | None,
    FileIdentity | None,
]:
    main = state.modules.get("__main__")
    main_file = getattr(main, "__file__", None)
    if type(main_file) is not str or not os.path.isabs(main_file):
        raise ImportPolicyError("invalid_module_main")
    try:
        main_snapshot = _regular_snapshot(main_file, code="launcher_not_regular", read=False)
    except ImportPolicyError as exc:
        if exc.code == "launcher_not_regular":
            raise
        raise ImportPolicyError("invalid_module_main") from None
    owned_main = owned.get(os.fspath(main_snapshot.canonical_path))
    if owned_main is not None and owned_main.distribution == "laconian-eval":
        if _stat_identity_tuple(main_snapshot.metadata) != _captured_identity_tuple(
            owned_main.identity
        ):
            raise ImportPolicyError("captured_origin_changed")
        spec_origin = getattr(getattr(main, "__spec__", None), "origin", None)
        if type(spec_origin) is str:
            spec_snapshot = _regular_snapshot(spec_origin, code="invalid_module_main", read=False)
            if (spec_snapshot.metadata.st_dev, spec_snapshot.metadata.st_ino) != (
                main_snapshot.metadata.st_dev,
                main_snapshot.metadata.st_ino,
            ):
                raise ImportPolicyError("invalid_module_main")
        return "module", None, None, None, None
    try:
        launcher_digest = verify_console_launcher(main_file, executable=state.executable)
    except ImportPolicyError as exc:
        if exc.code == "launcher_not_regular":
            raise
        raise ImportPolicyError("invalid_module_main") from None
    argv_snapshot = _regular_snapshot(state.argv0, code="launcher_identity_mismatch", read=False)
    if (main_snapshot.metadata.st_dev, main_snapshot.metadata.st_ino) != (
        argv_snapshot.metadata.st_dev,
        argv_snapshot.metadata.st_ino,
    ):
        raise ImportPolicyError("launcher_identity_mismatch")
    return (
        "console_script",
        launcher_digest,
        main_snapshot.canonical_path,
        directory_identity(Path(state.argv0).parent),
        FileIdentity(
            device=main_snapshot.metadata.st_dev,
            inode=main_snapshot.metadata.st_ino,
            mode=main_snapshot.metadata.st_mode,
            size=main_snapshot.metadata.st_size,
            mtime_ns=main_snapshot.metadata.st_mtime_ns,
            ctime_ns=main_snapshot.metadata.st_ctime_ns,
        ),
    )


def _path_spells_zip(path: str, placeholder: Path) -> bool:
    if not path:
        return False
    absolute = os.path.abspath(path)
    return os.path.normpath(os.path.realpath(absolute)) == os.fspath(placeholder)


def _ordered_unique_roots(
    layout: InterpreterLayout,
    bootstrap: SiteBootstrap,
    runner_parent: VerifiedDirectory,
    site_roots: tuple[VerifiedDirectory, ...],
) -> tuple[VerifiedDirectory, ...]:
    candidates = [layout.stdlib_root]
    if not _same_directory(layout.stdlib_root.identity, layout.destshared_root.identity):
        candidates.append(layout.destshared_root)
    if bootstrap.runner_import_mode == "path":
        candidates.append(runner_parent)
    candidates.extend(site_roots)
    result: list[VerifiedDirectory] = []
    seen: set[tuple[int, int]] = set()
    for root in candidates:
        key = (root.identity.device, root.identity.inode)
        if key not in seen:
            result.append(root)
            seen.add(key)
    return tuple(result)


def _normalize_sys_path(
    state: RuntimeImportState,
    *,
    layout: InterpreterLayout,
    roots: tuple[VerifiedDirectory, ...],
    launcher_mode: Literal["module", "console_script"],
    launcher_parent: DirectoryIdentity | None,
) -> tuple[str, ...]:
    cwd_identity = directory_identity(state.cwd)
    launcher_matches: list[int] = []
    zip_matches: list[int] = []
    active: dict[tuple[int, int], int] = {}
    allowed = {(root.identity.device, root.identity.inode): root for root in roots}
    platstdlib_raw = sysconfig.get_path("platstdlib")
    platstdlib_identity = (
        directory_identity(platstdlib_raw) if type(platstdlib_raw) is str else None
    )
    for index, item in enumerate(state.sys_path):
        if launcher_mode == "module" and item == "":
            launcher_matches.append(index)
            continue
        try:
            identity = directory_identity(os.path.abspath(item) if item else state.cwd)
        except ImportPolicyError:
            if _path_spells_zip(item, layout.zip_placeholder):
                zip_matches.append(index)
                continue
            if item.lower().endswith((".zip", ".egg")) and os.path.exists(item):
                raise ImportPolicyError("active_zip_import") from None
            raise ImportPolicyError("unknown_import_root") from None
        if launcher_mode == "module" and _same_directory(identity, cwd_identity):
            launcher_matches.append(index)
            continue
        if (
            launcher_mode == "console_script"
            and launcher_parent is not None
            and _same_directory(identity, launcher_parent)
        ):
            launcher_matches.append(index)
            continue
        key = (identity.device, identity.inode)
        if (
            platstdlib_identity is not None
            and not _same_directory(platstdlib_identity, layout.stdlib_root.identity)
            and _same_directory(identity, platstdlib_identity)
        ):
            raise ImportPolicyError("active_distinct_platstdlib")
        if key not in allowed:
            raise ImportPolicyError("unknown_import_root")
        active.setdefault(key, index)
    if len(launcher_matches) != 1:
        raise ImportPolicyError(
            "ambiguous_launcher_path" if launcher_matches else "launcher_entry_missing"
        )
    if len(zip_matches) != 1:
        raise ImportPolicyError("stdlib_zip_placeholder_mismatch")
    if set(active) != set(allowed):
        raise ImportPolicyError("missing_import_root")
    return tuple(os.fspath(root.canonical_path) for root in roots)


def _shadow_names(package_owners: Mapping[str, object]) -> frozenset[str]:
    return frozenset((*sys.stdlib_module_names, *package_owners, "laconian_eval"))


def _scan_shadow_directory(path: Path, names: frozenset[str]) -> None:
    try:
        identity = directory_identity(path)
    except ImportPolicyError:
        if not path.exists():
            return
        raise ImportPolicyError("shadow_scan_failed") from None
    try:
        entries = os.scandir(identity.canonical_path)
        with entries as scanner:
            for scanned_entries, entry in enumerate(scanner, start=1):
                if scanned_entries > RESOURCE_LIMITS_V1.dependency_files:
                    raise ResourceLimitError("import_directory_entry_count_limit")
                name = entry.name
                if name.endswith(".py"):
                    candidate = name[:-3]
                elif name.endswith(".pyc"):
                    candidate = name[:-4]
                else:
                    candidate = name
                extension = _extension_module_stem(name)
                if extension is not None:
                    candidate = extension
                if candidate in names:
                    raise ImportPolicyError("shadowing_import")
    except ImportPolicyError:
        raise
    except OSError:
        raise ImportPolicyError("shadow_scan_failed") from None


def _validate_cached_file_finder(key: str, finder: object) -> None:
    if type(finder) is not importlib.machinery.FileFinder:
        raise ImportPolicyError("unknown_importer_cache_finder")
    finder_path = getattr(finder, "path", None)
    if type(finder_path) is not str:
        raise ImportPolicyError("importer_cache_finder_mismatch")
    instance_namespace = getattr(finder, "__dict__", None)
    if type(instance_namespace) is not dict or "find_spec" in instance_namespace:
        raise ImportPolicyError("importer_cache_finder_mismatch")
    try:
        key_identity = directory_identity(key)
        finder_identity = directory_identity(finder_path)
    except ImportPolicyError:
        raise ImportPolicyError("importer_cache_finder_mismatch") from None
    if not _same_directory(key_identity, finder_identity):
        raise ImportPolicyError("importer_cache_finder_mismatch")
    expected_loaders = [
        *(
            (suffix, importlib.machinery.ExtensionFileLoader)
            for suffix in importlib.machinery.EXTENSION_SUFFIXES
        ),
        *(
            (suffix, importlib.machinery.SourceFileLoader)
            for suffix in importlib.machinery.SOURCE_SUFFIXES
        ),
        *(
            (suffix, importlib.machinery.SourcelessFileLoader)
            for suffix in importlib.machinery.BYTECODE_SUFFIXES
        ),
    ]
    actual_loaders = getattr(finder, "_loaders", None)
    if type(actual_loaders) is not list or len(actual_loaders) != len(expected_loaders):
        raise ImportPolicyError("importer_cache_finder_mismatch")
    if any(
        type(actual) is not tuple
        or len(actual) != 2
        or type(actual[0]) is not str
        or actual[0] != expected[0]
        or actual[1] is not expected[1]
        for actual, expected in zip(actual_loaders, expected_loaders, strict=True)
    ):
        raise ImportPolicyError("importer_cache_finder_mismatch")


def _snapshot_cache_bindings(
    importer_cache: Mapping[str, object | None],
) -> tuple[_FileFinderBinding, ...]:
    result: list[_FileFinderBinding] = []
    for key, finder in importer_cache.items():
        if finder is None:
            continue
        _validate_cached_file_finder(key, finder)
        typed_finder = cast(Any, finder)
        path = cast(str, typed_finder.path)
        raw_loaders = cast(list[tuple[str, object]], typed_finder._loaders)
        result.append(
            _FileFinderBinding(
                key=key,
                finder=finder,
                path=path,
                loaders=tuple(raw_loaders),
            )
        )
    return tuple(result)


def _revalidate_cache_bindings(
    bindings: tuple[_FileFinderBinding, ...],
    importer_cache: Mapping[str, object | None],
    *,
    code: str,
) -> None:
    for binding in bindings:
        if importer_cache.get(binding.key) is not binding.finder:
            raise ImportPolicyError(code)
        if getattr(binding.finder, "path", None) != binding.path:
            raise ImportPolicyError(code)
        instance_namespace = getattr(binding.finder, "__dict__", None)
        if type(instance_namespace) is not dict or "find_spec" in instance_namespace:
            raise ImportPolicyError(code)
        loaders = getattr(binding.finder, "_loaders", None)
        if type(loaders) is not list or len(loaders) != len(binding.loaders):
            raise ImportPolicyError(code)
        if any(
            type(actual) is not tuple
            or len(actual) != 2
            or actual[0] != expected[0]
            or actual[1] is not expected[1]
            for actual, expected in zip(loaders, binding.loaders, strict=True)
        ):
            raise ImportPolicyError(code)


def _validate_initial_cache(
    state: RuntimeImportState,
    *,
    roots: tuple[VerifiedDirectory, ...],
    layout: InterpreterLayout,
    launcher_mode: Literal["module", "console_script"],
    launcher_parent: DirectoryIdentity | None,
) -> None:
    cwd = directory_identity(state.cwd)
    launcher_cache_key = (
        Path(os.path.realpath(os.path.abspath(state.argv0)))
        if launcher_mode == "console_script"
        else None
    )
    for key, finder in state.importer_cache.items():
        if isinstance(finder, zipimport.zipimporter):
            raise ImportPolicyError("zip_importer_unsupported")
        if finder is not None:
            _validate_cached_file_finder(key, finder)
        if _path_spells_zip(key, layout.zip_placeholder):
            continue
        try:
            identity = directory_identity(key)
        except ImportPolicyError:
            canonical = Path(os.path.realpath(os.path.abspath(key)))
            if finder is None and canonical == launcher_cache_key:
                continue
            if finder is None and any(
                _is_beneath(canonical, root.canonical_path) for root in roots
            ):
                continue
            raise ImportPolicyError("unknown_importer_cache_root") from None
        if launcher_mode == "module" and _same_directory(identity, cwd):
            continue
        if (
            launcher_mode == "console_script"
            and launcher_parent is not None
            and _same_directory(identity, launcher_parent)
        ):
            continue
        if not any(_is_beneath(identity.canonical_path, root.canonical_path) for root in roots):
            raise ImportPolicyError("unknown_importer_cache_root")


def _scan_directory_tree(root: VerifiedDirectory) -> tuple[Path, ...]:
    result: list[Path] = []
    pending = [root.canonical_path]
    seen: set[tuple[int, int]] = set()
    scanned_entries = 0
    while pending:
        path = pending.pop()
        identity = directory_identity(path)
        key = (identity.device, identity.inode)
        if key in seen:
            continue
        seen.add(key)
        if len(seen) > RESOURCE_LIMITS_V1.dependency_files:
            raise ImportPolicyError("import_directory_count_limit")
        result.append(identity.canonical_path)
        try:
            with os.scandir(identity.canonical_path) as scanner:
                entries, scanned_entries = _sorted_directory_entries(
                    scanner,
                    already_seen=scanned_entries,
                    reverse=True,
                )
            for entry in entries:
                try:
                    metadata_record = entry.stat(follow_symlinks=False)
                except OSError:
                    raise ImportPolicyError("import_directory_scan_failed") from None
                if stat.S_ISDIR(metadata_record.st_mode):
                    pending.append(identity.canonical_path / entry.name)
        except ImportPolicyError:
            raise
        except OSError:
            raise ImportPolicyError("import_directory_scan_failed") from None
    return tuple(result)


def _preseed_importer_cache(
    roots: tuple[VerifiedDirectory, ...],
    *,
    stdlib: VerifiedDirectory,
    destshared: VerifiedDirectory,
    owned: Mapping[str, _OwnedOrigin],
    file_hook: object,
) -> Mapping[str, object | None]:
    directories: set[Path] = set(_scan_directory_tree(stdlib))
    if not _same_directory(stdlib.identity, destshared.identity):
        directories.update(_scan_directory_tree(destshared))
    directories.update(root.canonical_path for root in roots)
    for origin in owned.values():
        parent = origin.canonical_path.parent
        while _is_beneath(parent, origin.root.canonical_path):
            directories.add(parent)
            if parent == origin.root.canonical_path:
                break
            parent = parent.parent
    cache: dict[str, object | None] = {}
    hook = cast(Callable[[str], object], file_hook)
    for path in sorted(directories, key=lambda item: os.fsencode(item)):
        try:
            finder = hook(os.fspath(path))
        except ImportError:
            raise ImportPolicyError("file_finder_preseed_failed") from None
        if type(finder) is not importlib.machinery.FileFinder:
            raise ImportPolicyError("file_finder_preseed_failed")
        cache[os.fspath(path)] = finder
    return MappingProxyType(cache)


def _strict_import_environment(value: object) -> ImportEnvironmentV1:
    try:
        payload = cast(Any, value).model_dump(mode="python", round_trip=True, warnings=False)
        return ImportEnvironmentV1.model_validate(payload)
    except (AttributeError, TypeError, ValueError):
        raise ImportPolicyError("invalid_import_environment") from None


def _find_spec_in_verified_roots(
    fullname: str,
    roots: tuple[Path, ...],
    file_hook: object,
) -> importlib.machinery.ModuleSpec | None:
    """Resolve from fresh standard FileFinders without ambient importer-cache delegation."""

    hook = cast(Callable[[str], object], file_hook)
    for root in roots:
        try:
            finder = hook(os.fspath(root))
        except ImportError:
            raise ImportPolicyError("file_finder_resolution_failed") from None
        if type(finder) is not importlib.machinery.FileFinder:
            raise ImportPolicyError("file_finder_resolution_failed")
        spec = finder.find_spec(fullname)
        if spec is not None:
            return spec
    return None


def _find_mapped_import_spec(
    fullname: str,
    roots: tuple[Path, ...],
    file_hook: object,
    *,
    virtualenv_finder: object | None,
) -> importlib.machinery.ModuleSpec | None:
    fixed_finders: list[tuple[Callable[..., object], object]] = [
        (_BUILTIN_FIND_SPEC_FUNCTION, importlib.machinery.BuiltinImporter),
        (_FROZEN_FIND_SPEC_FUNCTION, importlib.machinery.FrozenImporter),
    ]
    if virtualenv_finder is not None:
        virtualenv_find_spec = type(virtualenv_finder).__dict__.get("find_spec")
        if not callable(virtualenv_find_spec):
            raise ImportPolicyError("unknown_meta_path_finder")
        fixed_finders.append((virtualenv_find_spec, virtualenv_finder))
    for find_spec, owner in fixed_finders:
        spec = find_spec(owner, fullname, None, None)
        if spec is None:
            continue
        if not isinstance(spec, importlib.machinery.ModuleSpec):
            raise ImportPolicyError("missing_import_spec")
        return spec
    return _find_spec_in_verified_roots(fullname, roots, file_hook)


def build_import_policy(
    provenance: InstalledProvenance,
    *,
    runtime_state: RuntimeImportState | None = None,
) -> ImportPolicy:
    """Construct and fully validate a policy without mutating interpreter state."""

    if type(provenance) is not InstalledProvenance:
        raise ImportPolicyError("invalid_installed_provenance")
    state = _copy_runtime_state(
        capture_runtime_import_state() if runtime_state is None else runtime_state
    )
    if state.environ["PYTHONPATH"]:
        raise ImportPolicyError("nonempty_pythonpath")
    if state.environ["PYTHONHOME"]:
        raise ImportPolicyError("nonempty_pythonhome")
    if state.user_site_enabled is True:
        raise ImportPolicyError("user_site_enabled")
    layout = _discover_interpreter_layout()
    runner_package, runner_parent, owned = _validate_runner_capture(provenance.runner_source)
    site_roots_list: list[VerifiedDirectory] = []
    site_seen: set[tuple[int, int]] = set()
    distribution_members: dict[str, tuple[str, ...]] = {}
    for inventory in provenance.dependencies:
        root, dependency_owned = _validate_distribution_capture(inventory)
        key = (root.identity.device, root.identity.inode)
        if key not in site_seen:
            site_roots_list.append(root)
            site_seen.add(key)
        if set(owned).intersection(dependency_owned):
            raise ImportPolicyError("duplicate_import_ownership")
        owned.update(dependency_owned)
        distribution_members[inventory.record.distribution] = tuple(
            item.path for item in inventory.files
        )
    site_roots = tuple(site_roots_list)
    bootstrap = inspect_site_bootstrap(
        tuple(root.canonical_path for root in site_roots),
        runner_parent=runner_parent.canonical_path,
        meta_path=state.meta_path,
    )
    expected_meta = _validated_meta_path(state.meta_path, bootstrap)
    file_hook = _validated_file_finder_hook(state.path_hooks)
    _validate_console_entry_point(provenance)
    (
        launcher_mode,
        launcher_digest,
        launcher_path,
        launcher_parent,
        launcher_identity,
    ) = _detect_launcher(provenance, state, owned)
    roots = _ordered_unique_roots(layout, bootstrap, runner_parent, site_roots)
    normalized_path = _normalize_sys_path(
        state,
        layout=layout,
        roots=roots,
        launcher_mode=launcher_mode,
        launcher_parent=launcher_parent,
    )
    _validate_initial_cache(
        state,
        roots=roots,
        layout=layout,
        launcher_mode=launcher_mode,
        launcher_parent=launcher_parent,
    )
    package_owners_raw = metadata.packages_distributions()
    package_owners = {
        module: tuple(owners)
        for module, owners in package_owners_raw.items()
        if type(module) is str and isinstance(owners, list)
    }
    projected_roots = derive_import_roots_from_members(
        distribution_members,
        package_owners=package_owners,
    )
    spec_roots = tuple(root.canonical_path for root in roots)
    validated_roots: list[ImportRootV1] = []
    for projected_root in projected_roots:
        checked = validate_mapped_import_spec(
            projected_root.module,
            projected_root.distribution,
            provenance.dependencies,
            find_spec=lambda name: _find_mapped_import_spec(
                name,
                spec_roots,
                file_hook,
                virtualenv_finder=bootstrap.virtualenv_finder,
            ),
        )
        if checked != projected_root:
            raise ImportPolicyError("import_root_mismatch")
        validated_roots.append(checked)
    names = _shadow_names(package_owners)
    _scan_shadow_directory(state.cwd, names)
    if state.user_site is not None:
        _scan_shadow_directory(state.user_site, names)
    preseeded_cache = _preseed_importer_cache(
        roots,
        stdlib=layout.stdlib_root,
        destshared=layout.destshared_root,
        owned=owned,
        file_hook=file_hook,
    )
    cache_bindings = _snapshot_cache_bindings(preseeded_cache)
    guard_bytes = provenance.runner_source.file_bytes.get(_GUARD_MEMBER)
    guard_record = next(
        (item for item in provenance.runner_source.index.files if item.path == _GUARD_MEMBER),
        None,
    )
    if (
        type(guard_bytes) is not bytes
        or guard_record is None
        or len(guard_bytes) != guard_record.byte_length
        or sha256_bytes(guard_bytes) != guard_record.sha256
    ):
        raise ImportPolicyError("runner_capture_mismatch")
    environment = _strict_import_environment(
        ImportEnvironmentV1.model_validate(
            {
                "import_policy_version": "laconian-import-policy-v1",
                "stdlib_origin_policy": "interpreter-layout-v1",
                "stdlib_extension_policy": "destshared-v1",
                "platstdlib_mode": layout.platstdlib_mode,
                "guard_source_sha256": sha256_bytes(guard_bytes),
                "audit_hook_source_sha256": sha256_bytes(guard_bytes),
                "runner_import_mode": bootstrap.runner_import_mode,
                "launcher_mode": launcher_mode,
                "launcher_template_sha256": launcher_digest,
                "virtualenv_bootstrap_sha256": bootstrap.virtualenv_bootstrap_sha256,
                "import_roots": [item.model_dump(mode="json") for item in validated_roots],
            }
        )
    )
    projected_state = RuntimeImportState(
        sys_path=normalized_path,
        meta_path=expected_meta,
        path_hooks=state.path_hooks,
        importer_cache=preseeded_cache,
        modules=state.modules,
        environ=state.environ,
        executable=state.executable,
        argv0=state.argv0,
        cwd=state.cwd,
        user_site_enabled=state.user_site_enabled,
        user_site=state.user_site,
    )
    policy = ImportPolicy(
        import_environment=environment,
        initial_state=state,
        runtime_state=projected_state,
        allowed_roots=roots,
        stdlib_root=layout.stdlib_root,
        destshared_root=layout.destshared_root,
        site_roots=site_roots,
        runner_parent_root=runner_parent,
        runner_package_root=runner_package,
        zip_placeholder=layout.zip_placeholder,
        bootstrap=bootstrap,
        file_finder_hook=file_hook,
        cache_bindings=cache_bindings,
        owned_origins=MappingProxyType(owned),
        originless_modules=MappingProxyType({}),
        fixed_alias_modules=MappingProxyType({}),
        launcher_mode=launcher_mode,
        launcher_path=launcher_path,
        launcher_identity=launcher_identity,
        virtualenv_module=bootstrap.virtualenv_module,
        enforcement_token=object(),
    )
    originless_modules = _capture_originless_runtime_modules(policy, state.modules)
    fixed_alias_modules = _capture_fixed_alias_modules(policy, state.modules)
    policy = dataclass_replace(
        policy,
        originless_modules=originless_modules,
        fixed_alias_modules=fixed_alias_modules,
    )
    revalidate_loaded_modules(policy, modules=state.modules)
    return policy


def revalidate_import_environment(
    policy: ImportPolicy,
    environment: ImportEnvironmentV1,
) -> None:
    checked = _strict_import_environment(environment)
    if checked != policy.import_environment:
        raise ImportPolicyError("import_environment_drift")


class _OriginContext(Protocol):
    @property
    def stdlib_root(self) -> VerifiedDirectory: ...

    @property
    def destshared_root(self) -> VerifiedDirectory: ...

    @property
    def site_roots(self) -> tuple[VerifiedDirectory, ...]: ...

    @property
    def runner_parent_root(self) -> VerifiedDirectory: ...

    @property
    def owned_origins(self) -> Mapping[str, _OwnedOrigin]: ...


def _revalidate_root_identities(roots: tuple[VerifiedDirectory, ...]) -> None:
    seen: set[tuple[int, int]] = set()
    for root in roots:
        key = (root.identity.device, root.identity.inode)
        if key in seen:
            continue
        seen.add(key)
        try:
            current = directory_identity(root.canonical_path)
        except ImportPolicyError:
            raise ImportPolicyError("import_root_identity_drift") from None
        if not _same_directory(current, root.identity):
            raise ImportPolicyError("import_root_identity_drift")


def _validated_origin(
    policy: _OriginContext,
    origin: str,
    *,
    loader: object | None = None,
) -> _OwnedOrigin | None:
    _revalidate_root_identities(
        (
            policy.stdlib_root,
            policy.destshared_root,
            policy.runner_parent_root,
            *policy.site_roots,
        )
    )
    if type(origin) is not str or not os.path.isabs(origin):
        raise ImportPolicyError("import_origin_not_allowed")
    if ".zip/" in origin or isinstance(loader, zipimport.zipimporter):
        raise ImportPolicyError("zip_import_unsupported")
    snapshot = _regular_snapshot(origin, code="import_origin_not_regular", read=False)
    canonical = snapshot.canonical_path
    if canonical.suffix == ".pyc" and (
        _is_beneath(canonical, policy.runner_parent_root.canonical_path)
        or any(_is_beneath(canonical, root.canonical_path) for root in policy.site_roots)
    ):
        raise ImportPolicyError("captured_bytecode_unsupported")
    owned = policy.owned_origins.get(os.fspath(canonical))
    if owned is not None:
        if _stat_identity_tuple(snapshot.metadata) != _captured_identity_tuple(owned.identity):
            raise ImportPolicyError("captured_origin_changed")
        return owned
    if _is_beneath(canonical, policy.stdlib_root.canonical_path) or _is_beneath(
        canonical, policy.destshared_root.canonical_path
    ):
        return None
    if _is_beneath(canonical, policy.runner_parent_root.canonical_path) or any(
        _is_beneath(canonical, root.canonical_path) for root in policy.site_roots
    ):
        raise ImportPolicyError("unowned_import_origin")
    raise ImportPolicyError("import_origin_not_allowed")


def _same_regular_file(left: str, right: str, *, code: str) -> bool:
    left_snapshot = _regular_snapshot(left, code=code, read=False)
    right_snapshot = _regular_snapshot(right, code=code, read=False)
    return (left_snapshot.metadata.st_dev, left_snapshot.metadata.st_ino) == (
        right_snapshot.metadata.st_dev,
        right_snapshot.metadata.st_ino,
    )


def _capture_originless_runtime_modules(
    policy: ImportPolicy,
    modules: Mapping[str, object],
) -> Mapping[str, object]:
    captured: dict[str, object] = {}
    typing_names = {"typing.io": "io", "typing.re": "re"}
    present_typing = typing_names.keys() & modules.keys()
    if present_typing:
        if present_typing != typing_names.keys():
            raise ImportPolicyError("originless_module_changed")
        typing_module = modules.get("typing")
        if typing_module is None:
            raise ImportPolicyError("originless_module_changed")
        _validate_loaded_module(policy, "typing", typing_module)
        for name, attribute in typing_names.items():
            value = modules[name]
            if (
                value is not getattr(typing_module, attribute, None)
                or getattr(value, "__file__", None) is not None
                or getattr(value, "__spec__", None) is not None
            ):
                raise ImportPolicyError("originless_module_changed")
            captured[name] = value

    cython_names = {"cython_runtime", "_cython_3_1_4"}
    present_cython = cython_names & modules.keys()
    if present_cython:
        if present_cython != cython_names:
            raise ImportPolicyError("originless_module_changed")
        native_anchor = modules.get("pydantic_core._pydantic_core")
        if native_anchor is None:
            raise ImportPolicyError("originless_module_changed")
        _validate_loaded_module(policy, "pydantic_core._pydantic_core", native_anchor)
        for name in cython_names:
            value = modules[name]
            if (
                type(value) is not ModuleType
                or getattr(value, "__name__", None) != name
                or getattr(value, "__file__", None) is not None
                or getattr(value, "__spec__", None) is not None
            ):
                raise ImportPolicyError("originless_module_changed")
            captured[name] = value
    return MappingProxyType(captured)


def _revalidate_originless_modules(
    policy: ImportPolicy,
    modules: Mapping[str, object],
) -> None:
    for name, expected in policy.originless_modules.items():
        if modules.get(name) is not expected:
            raise ImportPolicyError("originless_module_changed")
        if (
            getattr(expected, "__file__", None) is not None
            or getattr(expected, "__spec__", None) is not None
        ):
            raise ImportPolicyError("originless_module_changed")
    typing_module = modules.get("typing")
    for name, attribute in (("typing.io", "io"), ("typing.re", "re")):
        expected = policy.originless_modules.get(name)
        if expected is not None and (
            typing_module is None or getattr(typing_module, attribute, None) is not expected
        ):
            raise ImportPolicyError("originless_module_changed")


def _validate_fixed_loaded_module(
    policy: ImportPolicy,
    name: str,
    module: object,
    *,
    allow_uncaptured_alias: bool = False,
) -> bool:
    spec = getattr(module, "__spec__", None)
    if not isinstance(spec, importlib.machinery.ModuleSpec):
        raise ImportPolicyError("builtin_frozen_mismatch")
    origin = spec.origin
    loader: object = spec.loader
    if type(origin) is not str:
        raise ImportPolicyError("builtin_frozen_mismatch")
    expected_loader: object | None = {
        "built-in": importlib.machinery.BuiltinImporter,
        "frozen": importlib.machinery.FrozenImporter,
    }.get(origin)
    if expected_loader is None or loader is not expected_loader:
        raise ImportPolicyError("builtin_frozen_mismatch")
    module_file = getattr(module, "__file__", None)
    if origin == "built-in":
        if module_file is not None:
            raise ImportPolicyError("builtin_frozen_mismatch")
        resolved = _BUILTIN_FIND_SPEC_FUNCTION(
            importlib.machinery.BuiltinImporter, name, None, None
        )
    else:
        if module_file is not None:
            if type(module_file) is not str:
                raise ImportPolicyError("builtin_frozen_mismatch")
            owned = _validated_origin(policy, module_file, loader=loader)
            if owned is not None:
                raise ImportPolicyError("builtin_frozen_mismatch")
        resolved = _FROZEN_FIND_SPEC_FUNCTION(importlib.machinery.FrozenImporter, name, None, None)
    alias_target = _FIXED_MODULE_ALIASES.get(name)
    if alias_target is not None and spec.name == alias_target:
        if not allow_uncaptured_alias and policy.fixed_alias_modules.get(name) is not module:
            raise ImportPolicyError("fixed_module_alias_changed")
        return True
    if (
        not isinstance(resolved, importlib.machinery.ModuleSpec)
        or resolved.origin != origin
        or resolved.loader is not loader
        or resolved.name != spec.name
    ):
        raise ImportPolicyError("builtin_frozen_mismatch")
    return True


def _capture_fixed_alias_modules(
    policy: ImportPolicy,
    modules: Mapping[str, object],
) -> Mapping[str, object]:
    captured: dict[str, object] = {}
    for alias, target in _IDENTITY_MODULE_ALIASES.items():
        if alias not in modules:
            continue
        module = modules[alias]
        if module is None or modules.get(target) is not module:
            raise ImportPolicyError("fixed_module_alias_changed")
        captured[alias] = module
    for alias, target in _FIXED_MODULE_ALIASES.items():
        if alias not in modules:
            continue
        module = modules[alias]
        if modules.get(target) is not module:
            raise ImportPolicyError("fixed_module_alias_changed")
        _validate_fixed_loaded_module(
            policy,
            alias,
            module,
            allow_uncaptured_alias=True,
        )
        captured[alias] = module
    return MappingProxyType(captured)


def _revalidate_fixed_alias_modules(
    policy: ImportPolicy,
    modules: Mapping[str, object],
) -> None:
    for alias, expected in policy.fixed_alias_modules.items():
        target = _MODULE_ALIAS_TARGETS[alias]
        if modules.get(alias) is not expected or modules.get(target) is not expected:
            raise ImportPolicyError("fixed_module_alias_changed")


def _validate_loaded_module(policy: ImportPolicy, name: str, module: object) -> None:
    originless = policy.originless_modules.get(name)
    if originless is not None:
        if module is not originless:
            raise ImportPolicyError("originless_module_changed")
        return
    if name in _IDENTITY_MODULE_ALIASES:
        if policy.fixed_alias_modules.get(name) is not module:
            raise ImportPolicyError("fixed_module_alias_changed")
        return
    spec = getattr(module, "__spec__", None)
    spec_origin = getattr(spec, "origin", None)
    loader = getattr(spec, "loader", None)
    module_file = getattr(module, "__file__", None)
    if name == "__main__":
        if type(module_file) is not str:
            raise ImportPolicyError("invalid_module_main")
        if policy.launcher_mode == "console_script":
            if policy.launcher_path is None or not _same_regular_file(
                module_file, os.fspath(policy.launcher_path), code="invalid_module_main"
            ):
                raise ImportPolicyError("invalid_module_main")
            digest = verify_console_launcher(
                module_file, executable=policy.runtime_state.executable
            )
            if digest != policy.import_environment.launcher_template_sha256:
                raise ImportPolicyError("launcher_template_mismatch")
            if policy.launcher_identity is None:
                raise ImportPolicyError("launcher_identity_mismatch")
            snapshot = _regular_snapshot(
                module_file,
                code="launcher_identity_mismatch",
                read=False,
            )
            if _stat_identity_tuple(snapshot.metadata) != _captured_identity_tuple(
                policy.launcher_identity
            ):
                raise ImportPolicyError("launcher_identity_mismatch")
            return
        owned = _validated_origin(policy, module_file, loader=loader)
        if owned is None or owned.distribution != "laconian-eval":
            raise ImportPolicyError("invalid_module_main")
        return
    claims_fixed = spec_origin in ("built-in", "frozen") or loader in (
        importlib.machinery.BuiltinImporter,
        importlib.machinery.FrozenImporter,
    )
    if claims_fixed:
        _validate_fixed_loaded_module(policy, name, module)
        return
    if name == "_virtualenv":
        if policy.virtualenv_module is None or type(module_file) is not str:
            raise ImportPolicyError("virtualenv_module_origin_mismatch")
        if not _same_regular_file(
            module_file,
            os.fspath(policy.virtualenv_module),
            code="virtualenv_module_origin_mismatch",
        ):
            raise ImportPolicyError("virtualenv_module_origin_mismatch")
        return
    portions = getattr(spec, "submodule_search_locations", None)
    if spec_origin is None and portions is not None:
        if len(tuple(portions)) > 1:
            raise ImportPolicyError("multiple_import_portions")
        raise ImportPolicyError("namespace_import_unsupported")
    origins = tuple(
        value for value in (spec_origin, module_file) if type(value) is str and value not in ("",)
    )
    if not origins:
        raise ImportPolicyError("import_origin_not_allowed")
    if len(origins) == 2 and not _same_regular_file(
        origins[0], origins[1], code="module_origin_mismatch"
    ):
        raise ImportPolicyError("module_origin_mismatch")
    owned = _validated_origin(policy, origins[0], loader=loader)
    spec_name = getattr(spec, "name", None)
    if owned is not None and (
        not isinstance(spec, importlib.machinery.ModuleSpec)
        or type(spec_name) is not str
        or spec_name != owned.module_name
        or name != owned.module_name
    ):
        raise ImportPolicyError("import_origin_wrong_distribution")


def revalidate_loaded_modules(
    policy: ImportPolicy,
    *,
    modules: Mapping[str, object] | None = None,
) -> None:
    """Revalidate every loaded non-builtin/non-frozen module against fixed ownership."""

    selected = dict(sys.modules) if modules is None else dict(modules)
    _revalidate_originless_modules(policy, selected)
    _revalidate_fixed_alias_modules(policy, selected)
    for name in sorted(selected, key=lambda item: item.encode("utf-8")):
        module = selected[name]
        if module is None:
            continue
        _validate_loaded_module(policy, name, module)


def _same_identity_sequence(actual: tuple[object, ...], expected: tuple[object, ...]) -> bool:
    return len(actual) == len(expected) and all(
        left is right for left, right in zip(actual, expected, strict=True)
    )


def _same_cache(
    actual: Mapping[str, object | None],
    expected: Mapping[str, object | None],
) -> bool:
    actual_items = tuple(actual.items())
    expected_items = tuple(expected.items())
    return len(actual_items) == len(expected_items) and all(
        actual_key == expected_key and actual_value is expected_value
        for (actual_key, actual_value), (expected_key, expected_value) in zip(
            actual_items, expected_items, strict=True
        )
    )


def revalidate_import_state(
    policy: ImportPolicy,
    *,
    runtime_state: RuntimeImportState | None = None,
    require_guard: bool = True,
) -> None:
    """Revalidate exact ordered paths, finders, hooks, and importer-cache identities."""

    preinstall_live_state = not require_guard and runtime_state is None
    state = _copy_runtime_state(
        capture_runtime_import_state() if runtime_state is None else runtime_state
    )
    expected = policy.initial_state if preinstall_live_state else policy.runtime_state
    if state.sys_path != expected.sys_path:
        raise ImportPolicyError("sys_path_drift")
    expected_meta = expected.meta_path
    if require_guard:
        if not state.meta_path:
            raise ImportPolicyError("guard_order_drift")
        guard = state.meta_path[0]
        if (
            type(guard) is not _LaconianImportGuard
            or not guard._installed_for(policy.enforcement_token)
            or not _same_identity_sequence(state.meta_path[1:], expected_meta)
        ):
            raise ImportPolicyError("guard_order_drift")
    elif not _same_identity_sequence(state.meta_path, expected_meta):
        raise ImportPolicyError("meta_path_drift")
    if not _same_identity_sequence(state.path_hooks, expected.path_hooks):
        raise ImportPolicyError("path_hooks_drift")
    if not _same_cache(state.importer_cache, expected.importer_cache):
        raise ImportPolicyError("importer_cache_drift")
    if not preinstall_live_state:
        _revalidate_cache_bindings(
            policy.cache_bindings,
            state.importer_cache,
            code="importer_cache_drift",
        )
    _revalidate_fixed_finder_descriptors(_build_enforcement_snapshot(policy))


def _revalidate_owned_origins(policy: ImportPolicy) -> None:
    for owned in policy.owned_origins.values():
        snapshot = _regular_snapshot(
            owned.canonical_path,
            code="captured_origin_changed",
            read=False,
        )
        if _stat_identity_tuple(snapshot.metadata) != _captured_identity_tuple(owned.identity):
            raise ImportPolicyError("captured_origin_changed")


def revalidate_import_policy(
    policy: ImportPolicy,
    *,
    environment: ImportEnvironmentV1 | None = None,
) -> None:
    """Repeat complete fixed-state, inventory, environment, and loaded-module validation."""

    revalidate_import_environment(
        policy,
        policy.import_environment if environment is None else environment,
    )
    _revalidate_owned_origins(policy)
    revalidate_import_state(policy)
    revalidate_loaded_modules(policy)


@dataclass(frozen=True, slots=True)
class _LoaderDispatch:
    loader_type: type[object]
    creator_owner: type[object]
    creator_function: Callable[..., object]
    creator_code: CodeType
    creator: Callable[[importlib.machinery.ModuleSpec], object | None]
    executor_owner: type[object]
    executor_function: Callable[..., object]
    executor_code: CodeType
    executor: Callable[[object], None]


def _capture_loader_dispatch(loader: object) -> _LoaderDispatch:
    loader_type = type(loader)

    def capture(name: str) -> tuple[type[object], Callable[..., object], CodeType, object]:
        for owner in loader_type.__mro__:
            descriptor = owner.__dict__.get(name)
            if descriptor is None:
                continue
            if type(descriptor) is not type(_FILE_FINDER_FIND_SPEC_FUNCTION):
                raise ImportPolicyError("invalid_import_loader")
            code = descriptor.__code__
            if type(code) is not CodeType:
                raise ImportPolicyError("invalid_import_loader")
            bound = descriptor.__get__(loader, loader_type)
            if not callable(bound):
                raise ImportPolicyError("invalid_import_loader")
            return owner, descriptor, code, bound
        raise ImportPolicyError("invalid_import_loader")

    creator_owner, creator_function, creator_code, creator = capture("create_module")
    executor_owner, executor_function, executor_code, executor = capture("exec_module")
    return _LoaderDispatch(
        loader_type=loader_type,
        creator_owner=creator_owner,
        creator_function=creator_function,
        creator_code=creator_code,
        creator=cast(Callable[[importlib.machinery.ModuleSpec], object | None], creator),
        executor_owner=executor_owner,
        executor_function=executor_function,
        executor_code=executor_code,
        executor=cast(Callable[[object], None], executor),
    )


class _OriginValidatingLoader:
    """Loader proxy enforcing origin identity around every ambient loader action."""

    __slots__ = (
        "__ambient_loader",
        "__captured_source",
        "__dispatch",
        "__display_origin",
        "__post_validate",
        "__validate",
    )
    __ambient_loader: object
    __captured_source: bytes | None
    __dispatch: _LoaderDispatch
    __display_origin: str
    __post_validate: Callable[[], None]
    __validate: Callable[[], None]

    def __init__(
        self,
        ambient_loader: object,
        *,
        dispatch: _LoaderDispatch | None = None,
        validate: Callable[[], None],
        captured_source: bytes | None,
        display_origin: str,
        post_validate: Callable[[], None],
    ) -> None:
        object.__setattr__(self, "_OriginValidatingLoader__ambient_loader", ambient_loader)
        object.__setattr__(
            self,
            "_OriginValidatingLoader__dispatch",
            _capture_loader_dispatch(ambient_loader) if dispatch is None else dispatch,
        )
        object.__setattr__(self, "_OriginValidatingLoader__validate", validate)
        object.__setattr__(self, "_OriginValidatingLoader__captured_source", captured_source)
        object.__setattr__(self, "_OriginValidatingLoader__display_origin", display_origin)
        object.__setattr__(self, "_OriginValidatingLoader__post_validate", post_validate)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("sealed loader")

    @property
    def ambient_loader(self) -> object:
        return self.__ambient_loader

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> object | None:
        self.__validate()
        if self.__captured_source is not None:
            self.__post_validate()
            return None
        dispatch = self.__dispatch
        if (
            type(self.__ambient_loader) is not dispatch.loader_type
            or dispatch.creator_owner.__dict__.get("create_module") is not dispatch.creator_function
            or dispatch.creator_function.__code__ is not dispatch.creator_code
        ):
            raise ImportPolicyError("invalid_import_loader")
        try:
            return dispatch.creator(spec)
        finally:
            self.__post_validate()

    def exec_module(self, module: object) -> None:
        self.__validate()
        try:
            if self.__captured_source is not None:
                namespace = getattr(module, "__dict__", None)
                if type(namespace) is not dict:
                    raise ImportPolicyError("invalid_module_namespace")
                code = compile(
                    self.__captured_source, self.__display_origin, "exec", dont_inherit=True
                )
                exec(code, namespace, namespace)
                return
            dispatch = self.__dispatch
            if (
                type(self.__ambient_loader) is not dispatch.loader_type
                or dispatch.executor_owner.__dict__.get("exec_module")
                is not dispatch.executor_function
                or dispatch.executor_function.__code__ is not dispatch.executor_code
            ):
                raise ImportPolicyError("invalid_import_loader")
            dispatch.executor(module)
        finally:
            self.__post_validate()


class _LaconianImportGuard:
    """First meta-path finder resolving only through fixed verified finder identities."""

    __slots__ = ("__installed", "__sentinel_blocks", "__sentinel_name", "__snapshot")
    __installed: bool
    __sentinel_blocks: int
    __sentinel_name: str
    __snapshot: _EnforcementSnapshot

    def __init__(
        self,
        policy: ImportPolicy,
        *,
        path_find_spec: Callable[[str, object, object], object] | None = None,
    ) -> None:
        snapshot = _build_enforcement_snapshot(policy, path_find_spec=path_find_spec)
        object.__setattr__(self, "_LaconianImportGuard__snapshot", snapshot)
        object.__setattr__(
            self,
            "_LaconianImportGuard__sentinel_name",
            f"_laconian_guard_sentinel_{policy.import_environment.guard_source_sha256[:16]}",
        )
        object.__setattr__(self, "_LaconianImportGuard__sentinel_blocks", 0)
        object.__setattr__(self, "_LaconianImportGuard__installed", False)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("sealed guard")

    @property
    def sentinel_name(self) -> str:
        return self.__sentinel_name

    @property
    def sentinel_blocks(self) -> int:
        return self.__sentinel_blocks

    def _snapshot_for_install(self, token: object) -> _EnforcementSnapshot:
        if token is not self.__snapshot.token or self.__installed:
            raise ImportPolicyError("guard_already_installed")
        return self.__snapshot

    def _arm_installed(self, token: object) -> None:
        if token is not self.__snapshot.token or self.__installed:
            raise ImportPolicyError("guard_already_installed")
        object.__setattr__(self, "_LaconianImportGuard__installed", True)

    def _installed_for(self, token: object) -> bool:
        return self.__installed and token is self.__snapshot.token

    def _resolve_spec(
        self,
        fullname: str,
        path: object,
        target: object,
    ) -> importlib.machinery.ModuleSpec | None:
        snapshot = self.__snapshot
        fixed_finders: list[tuple[Callable[..., object], object]] = [
            (_BUILTIN_FIND_SPEC_FUNCTION, importlib.machinery.BuiltinImporter),
            (_FROZEN_FIND_SPEC_FUNCTION, importlib.machinery.FrozenImporter),
        ]
        if snapshot.virtualenv_finder is not None:
            virtualenv_function = snapshot.virtualenv_find_spec
            if not callable(virtualenv_function):
                raise ImportPolicyError("unknown_meta_path_finder")
            fixed_finders.append((virtualenv_function, snapshot.virtualenv_finder))
        for function, owner in fixed_finders:
            spec = function(owner, fullname, path, target)
            if spec is not None:
                if not isinstance(spec, importlib.machinery.ModuleSpec):
                    raise ImportPolicyError("invalid_import_spec")
                return spec
        spec = snapshot.path_find_spec(fullname, path, target)
        if spec is not None:
            if not isinstance(spec, importlib.machinery.ModuleSpec):
                raise ImportPolicyError("invalid_import_spec")
            return spec
        return None

    def _validate_search_path(self, path: object) -> None:
        if path is None:
            return
        if type(path) not in (list, tuple):
            raise ImportPolicyError("import_path_not_allowed")
        expected_cache = self.__snapshot.runtime_state.importer_cache
        bound = {binding.key: binding.finder for binding in self.__snapshot.cache_bindings}
        search_path = cast(list[object] | tuple[object, ...], path)
        for entry in search_path:
            if type(entry) is not str:
                raise ImportPolicyError("import_path_not_allowed")
            finder = expected_cache.get(entry)
            if finder is None or bound.get(entry) is not finder:
                raise ImportPolicyError("import_path_not_allowed")

    def _validate_standard_loader(
        self,
        fullname: str,
        origin: str,
        loader: object,
    ) -> _LoaderDispatch:
        expected_type: type[object]
        if any(origin.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES):
            expected_type = importlib.machinery.ExtensionFileLoader
        elif origin.endswith(tuple(importlib.machinery.SOURCE_SUFFIXES)):
            expected_type = importlib.machinery.SourceFileLoader
        elif origin.endswith(tuple(importlib.machinery.BYTECODE_SUFFIXES)):
            expected_type = importlib.machinery.SourcelessFileLoader
        else:
            raise ImportPolicyError("invalid_import_loader")
        namespace = getattr(loader, "__dict__", None)
        loader_path = getattr(loader, "path", None)
        if (
            type(loader) is not expected_type
            or type(namespace) is not dict
            or "create_module" in namespace
            or "exec_module" in namespace
            or getattr(loader, "name", None) != fullname
            or type(loader_path) is not str
            or not _same_regular_file(
                origin,
                loader_path,
                code="invalid_import_loader",
            )
        ):
            raise ImportPolicyError("invalid_import_loader")
        return _capture_loader_dispatch(loader)

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if self.__installed:
            _check_live_fixed_state(self.__snapshot, self)
        self._validate_search_path(path)
        if fullname == self.__sentinel_name:
            object.__setattr__(
                self,
                "_LaconianImportGuard__sentinel_blocks",
                self.__sentinel_blocks + 1,
            )
            raise ImportPolicyError("import_origin_not_allowed")
        spec = self._resolve_spec(fullname, path, target)
        if spec is None:
            return None
        spec_loader: object = spec.loader
        claims_fixed = spec.origin in ("built-in", "frozen") or spec_loader in (
            importlib.machinery.BuiltinImporter,
            importlib.machinery.FrozenImporter,
        )
        if claims_fixed:
            if type(spec.origin) is not str:
                raise ImportPolicyError("builtin_frozen_mismatch")
            expected_loader: object | None = {
                "built-in": importlib.machinery.BuiltinImporter,
                "frozen": importlib.machinery.FrozenImporter,
            }.get(spec.origin)
            if expected_loader is None or spec_loader is not expected_loader:
                raise ImportPolicyError("builtin_frozen_mismatch")
            return spec
        if spec.loader is None:
            if spec.submodule_search_locations is not None:
                raise ImportPolicyError("namespace_import_unsupported")
            raise ImportPolicyError("invalid_import_loader")
        origin = spec.origin
        if type(origin) is not str:
            raise ImportPolicyError("namespace_import_unsupported")

        def validate() -> None:
            owned = _validated_origin(self.__snapshot, origin, loader=spec.loader)
            if owned is not None and owned.module_name != fullname:
                raise ImportPolicyError("import_origin_wrong_distribution")

        owned = _validated_origin(self.__snapshot, origin, loader=spec.loader)
        if (
            owned is not None
            and owned.captured_source is not None
            and not self.__snapshot.enforce_fixed_finders
        ):
            dispatch = _capture_loader_dispatch(spec.loader)
        else:
            dispatch = self._validate_standard_loader(fullname, origin, spec.loader)

        def post_validate() -> None:
            validate()
            if self.__installed:
                _check_live_fixed_state(self.__snapshot, self)

        cast(Any, spec).loader = _OriginValidatingLoader(
            spec.loader,
            dispatch=dispatch,
            validate=validate,
            captured_source=None if owned is None else owned.captured_source,
            display_origin="<captured-source>",
            post_validate=post_validate,
        )
        return spec


def _clone_directory_identity(identity: DirectoryIdentity) -> DirectoryIdentity:
    return DirectoryIdentity(
        device=identity.device,
        inode=identity.inode,
        mode=identity.mode,
        canonical_path=identity.canonical_path,
    )


def _clone_verified_directory(root: VerifiedDirectory) -> VerifiedDirectory:
    return VerifiedDirectory(_clone_directory_identity(root.identity), root.role)


def _clone_enforcement_snapshot(snapshot: _EnforcementSnapshot) -> _EnforcementSnapshot:
    state = snapshot.runtime_state
    copied_state = RuntimeImportState(
        sys_path=tuple(state.sys_path),
        meta_path=tuple(state.meta_path),
        path_hooks=tuple(state.path_hooks),
        importer_cache=MappingProxyType(dict(state.importer_cache)),
        modules=MappingProxyType({}),
        environ=MappingProxyType({}),
        executable=state.executable,
        argv0=state.argv0,
        cwd=state.cwd,
        user_site_enabled=state.user_site_enabled,
        user_site=state.user_site,
    )
    copied_bindings = tuple(
        _FileFinderBinding(
            key=binding.key,
            finder=binding.finder,
            path=binding.path,
            loaders=tuple(binding.loaders),
        )
        for binding in snapshot.cache_bindings
    )
    copied_owned: dict[str, _OwnedOrigin] = {}
    for key, owned in snapshot.owned_origins.items():
        identity = owned.identity
        copied_owned[key] = _OwnedOrigin(
            module_name=owned.module_name,
            distribution=owned.distribution,
            member=owned.member,
            canonical_path=owned.canonical_path,
            identity=FileIdentity(
                device=identity.device,
                inode=identity.inode,
                mode=identity.mode,
                size=identity.size,
                mtime_ns=identity.mtime_ns,
                ctime_ns=identity.ctime_ns,
            ),
            captured_source=owned.captured_source,
            root=_clone_verified_directory(owned.root),
        )
    return _EnforcementSnapshot(
        token=snapshot.token,
        runtime_state=copied_state,
        cache_bindings=copied_bindings,
        allowed_roots=tuple(_clone_verified_directory(root) for root in snapshot.allowed_roots),
        stdlib_root=_clone_verified_directory(snapshot.stdlib_root),
        destshared_root=_clone_verified_directory(snapshot.destshared_root),
        site_roots=tuple(_clone_verified_directory(root) for root in snapshot.site_roots),
        runner_parent_root=_clone_verified_directory(snapshot.runner_parent_root),
        owned_origins=MappingProxyType(copied_owned),
        virtualenv_finder=snapshot.virtualenv_finder,
        virtualenv_find_spec=snapshot.virtualenv_find_spec,
        virtualenv_find_spec_code=snapshot.virtualenv_find_spec_code,
        path_find_spec=snapshot.path_find_spec,
        builtin_find_spec_code=snapshot.builtin_find_spec_code,
        frozen_find_spec_code=snapshot.frozen_find_spec_code,
        path_find_spec_code=snapshot.path_find_spec_code,
        file_finder_find_spec_code=snapshot.file_finder_find_spec_code,
        file_finder_hook_code=snapshot.file_finder_hook_code,
        enforce_fixed_finders=snapshot.enforce_fixed_finders,
    )


def _make_application_audit_hook(
    source_snapshot: _EnforcementSnapshot,
    guard: _LaconianImportGuard,
) -> tuple[Callable[[str, tuple[object, ...]], None], list[object]]:
    audit_snapshot = _clone_enforcement_snapshot(source_snapshot)
    type_ = type
    id_ = id
    len_ = len
    tuple_ = tuple
    sorted_ = sorted
    any_ = any
    all_ = all
    zip_ = zip
    getattr_ = getattr
    object_getattribute = object.__getattribute__
    type_getattribute = type.__getattribute__
    dict_items = dict.items
    dict_get = dict.get
    os_open = os.open
    os_close = os.close
    os_fstat = os.fstat
    os_fspath = os.fspath
    handled_os_errors = (OSError, TypeError, ValueError)
    attribute_error = AttributeError
    value_error = ValueError
    sys_module = sys
    error_type = ImportPolicyError
    snapshot_type = _EnforcementSnapshot
    state_type = RuntimeImportState
    binding_type = _FileFinderBinding
    owned_type = _OwnedOrigin
    file_identity_type = FileIdentity
    verified_directory_type = VerifiedDirectory
    directory_identity_type = DirectoryIdentity
    mapping_proxy_type = _MAPPING_PROXY_TYPE
    guard_type = _LaconianImportGuard
    type_type = type
    str_type = str
    tuple_type = tuple
    list_type = list
    list_getitem = list.__getitem__
    list_setitem = list.__setitem__
    dict_type = dict
    bool_type = bool
    int_type = int
    machinery = importlib.machinery
    builtin_finder = machinery.BuiltinImporter
    frozen_finder = machinery.FrozenImporter
    path_finder = machinery.PathFinder
    file_finder = machinery.FileFinder
    builtin_descriptor = _BUILTIN_FIND_SPEC_DESCRIPTOR
    frozen_descriptor = _FROZEN_FIND_SPEC_DESCRIPTOR
    path_descriptor = _PATH_FIND_SPEC_DESCRIPTOR
    file_descriptor = _FILE_FINDER_FIND_SPEC_DESCRIPTOR
    classmethod_type = type(builtin_descriptor)
    staticmethod_type = staticmethod
    property_type = property
    function_type = type(file_descriptor)
    code_type = CodeType
    proxy_loader_type = _OriginValidatingLoader
    dispatch_type = _LoaderDispatch
    module_spec_type = machinery.ModuleSpec
    source_loader_type = machinery.SourceFileLoader
    sourceless_loader_type = machinery.SourcelessFileLoader
    extension_loader_type = machinery.ExtensionFileLoader
    importlib_module = importlib
    zipimport_module = zipimport
    zipimporter_type = zipimport.zipimporter
    imp_module = _imp
    virtualenv_finder = audit_snapshot.virtualenv_finder
    virtualenv_type = type_(virtualenv_finder) if virtualenv_finder is not None else None
    virtualenv_descriptor = audit_snapshot.virtualenv_find_spec
    virtualenv_code = audit_snapshot.virtualenv_find_spec_code
    missing_binding = object()
    directory_flags = (
        os.O_RDONLY
        | getattr_(os, "O_DIRECTORY", 0)
        | getattr_(os, "O_NOFOLLOW", 0)
        | getattr_(os, "O_CLOEXEC", 0)
    )

    def private_directory_seal(root: object) -> tuple[object, ...] | None:
        if type_(root) is not verified_directory_type:
            return None
        identity = object_getattribute(root, "identity")
        if type_(identity) is not directory_identity_type:
            return None
        canonical_path = object_getattribute(identity, "canonical_path")
        return (
            object_getattribute(root, "role"),
            object_getattribute(identity, "device"),
            object_getattribute(identity, "inode"),
            object_getattribute(identity, "mode"),
            type_(canonical_path),
            id_(canonical_path),
        )

    def private_snapshot_seal(snapshot: object) -> tuple[object, ...] | None:
        if type_(snapshot) is not snapshot_type:
            return None
        state_value = object_getattribute(snapshot, "runtime_state")
        if type_(state_value) is not state_type:
            return None
        sys_path_value = object_getattribute(state_value, "sys_path")
        meta_path_value = object_getattribute(state_value, "meta_path")
        path_hooks_value = object_getattribute(state_value, "path_hooks")
        cache_value = object_getattribute(state_value, "importer_cache")
        bindings_value = object_getattribute(snapshot, "cache_bindings")
        roots_value = object_getattribute(snapshot, "allowed_roots")
        site_roots_value = object_getattribute(snapshot, "site_roots")
        owned_value = object_getattribute(snapshot, "owned_origins")
        enforce_fixed = object_getattribute(snapshot, "enforce_fixed_finders")
        if (
            type_(sys_path_value) is not tuple_type
            or any_(type_(item) is not str_type for item in sys_path_value)
            or type_(meta_path_value) is not tuple_type
            or type_(path_hooks_value) is not tuple_type
            or type_(cache_value) is not mapping_proxy_type
            or any_(type_(key) is not str_type for key in cache_value)
            or type_(bindings_value) is not tuple_type
            or type_(roots_value) is not tuple_type
            or type_(site_roots_value) is not tuple_type
            or type_(owned_value) is not mapping_proxy_type
            or any_(type_(key) is not str_type for key in owned_value)
            or type_(enforce_fixed) is not bool_type
        ):
            return None
        binding_seals: list[tuple[object, ...]] = []
        for binding in bindings_value:
            if type_(binding) is not binding_type:
                return None
            key = object_getattribute(binding, "key")
            path = object_getattribute(binding, "path")
            loaders = object_getattribute(binding, "loaders")
            if (
                type_(key) is not str_type
                or type_(path) is not str_type
                or type_(loaders) is not tuple_type
            ):
                return None
            loader_seal: list[tuple[str, int]] = []
            for item in loaders:
                if (
                    type_(item) is not tuple_type
                    or len_(item) != 2
                    or type_(item[0]) is not str_type
                ):
                    return None
                loader_seal.append((item[0], id_(item[1])))
            binding_seals.append(
                (key, id_(object_getattribute(binding, "finder")), path, tuple_(loader_seal))
            )
        root_seals = tuple_(private_directory_seal(root) for root in roots_value)
        if any_(item is None for item in root_seals):
            return None
        owned_seals: list[tuple[object, ...]] = []
        for key in sorted_(owned_value):
            owned = owned_value[key]
            if type_(owned) is not owned_type:
                return None
            identity = object_getattribute(owned, "identity")
            if type_(identity) is not file_identity_type:
                return None
            owned_root_seal = private_directory_seal(object_getattribute(owned, "root"))
            if owned_root_seal is None:
                return None
            canonical_path = object_getattribute(owned, "canonical_path")
            owned_seals.append(
                (
                    key,
                    object_getattribute(owned, "module_name"),
                    object_getattribute(owned, "distribution"),
                    object_getattribute(owned, "member"),
                    type_(canonical_path),
                    id_(canonical_path),
                    object_getattribute(identity, "device"),
                    object_getattribute(identity, "inode"),
                    object_getattribute(identity, "mode"),
                    object_getattribute(identity, "size"),
                    object_getattribute(identity, "mtime_ns"),
                    object_getattribute(identity, "ctime_ns"),
                    id_(object_getattribute(owned, "captured_source")),
                    owned_root_seal,
                )
            )
        return (
            id_(object_getattribute(snapshot, "token")),
            sys_path_value,
            tuple_(id_(item) for item in meta_path_value),
            tuple_(id_(item) for item in path_hooks_value),
            tuple_((key, id_(value)) for key, value in cache_value.items()),
            tuple_(binding_seals),
            root_seals,
            private_directory_seal(object_getattribute(snapshot, "stdlib_root")),
            private_directory_seal(object_getattribute(snapshot, "destshared_root")),
            tuple_(private_directory_seal(root) for root in site_roots_value),
            private_directory_seal(object_getattribute(snapshot, "runner_parent_root")),
            tuple_(owned_seals),
            id_(object_getattribute(snapshot, "virtualenv_finder")),
            id_(object_getattribute(snapshot, "virtualenv_find_spec")),
            id_(object_getattribute(snapshot, "virtualenv_find_spec_code")),
            id_(object_getattribute(snapshot, "path_find_spec")),
            id_(object_getattribute(snapshot, "builtin_find_spec_code")),
            id_(object_getattribute(snapshot, "frozen_find_spec_code")),
            id_(object_getattribute(snapshot, "path_find_spec_code")),
            id_(object_getattribute(snapshot, "file_finder_find_spec_code")),
            id_(object_getattribute(snapshot, "file_finder_hook_code")),
            enforce_fixed,
        )

    def private_function_seal(function: object) -> tuple[object, ...] | None:
        if type_(function) is not function_type:
            return None
        code = object_getattribute(function, "__code__")
        defaults = object_getattribute(function, "__defaults__")
        kwdefaults = object_getattribute(function, "__kwdefaults__")
        closure = object_getattribute(function, "__closure__")
        function_globals = object_getattribute(function, "__globals__")
        function_builtins = object_getattribute(function, "__builtins__")
        if type_(code) is not code_type:
            return None
        if defaults is None:
            defaults_seal: object = None
        elif type_(defaults) is tuple_type:
            defaults_seal = (id_(defaults), tuple_(id_(item) for item in defaults))
        else:
            return None
        if kwdefaults is None:
            kwdefaults_seal: object = None
        elif type_(kwdefaults) is dict_type and all_(type_(key) is str_type for key in kwdefaults):
            kwdefaults_seal = (
                id_(kwdefaults),
                tuple_((key, id_(value)) for key, value in sorted_(dict_items(kwdefaults))),
            )
        else:
            return None
        if closure is None:
            closure_seal: object = None
        elif type_(closure) is tuple_type:
            try:
                closure_seal = (
                    id_(closure),
                    tuple_(
                        (id_(cell), id_(object_getattribute(cell, "cell_contents")))
                        for cell in closure
                    ),
                )
            except value_error:
                return None
        else:
            return None
        return (
            id_(code),
            defaults_seal,
            kwdefaults_seal,
            closure_seal,
            id_(function_globals),
            id_(function_builtins),
        )

    def private_descriptor_seal(descriptor: object) -> tuple[object, ...]:
        if type_(descriptor) is function_type:
            return ("function", private_function_seal(descriptor))
        if type_(descriptor) in (classmethod_type, staticmethod_type):
            function = object_getattribute(descriptor, "__func__")
            return (type_(descriptor).__name__, id_(function), private_function_seal(function))
        if type_(descriptor) is property_type:
            accessors: list[tuple[int, tuple[object, ...] | None] | None] = []
            for name in ("fget", "fset", "fdel"):
                function = object_getattribute(descriptor, name)
                accessors.append(
                    None if function is None else (id_(function), private_function_seal(function))
                )
            return (
                "property",
                tuple_(accessors),
                id_(object_getattribute(descriptor, "__doc__")),
            )
        return ("identity", type_(descriptor), id_(descriptor))

    def private_class_seal(owner: object) -> tuple[object, ...] | None:
        if type_(owner) is not type_type:
            return None
        owner_mro = type_getattribute(owner, "__mro__")
        owner_namespace = type_getattribute(owner, "__dict__")
        if type_(owner_mro) is not tuple_type or type_(owner_namespace) is not mapping_proxy_type:
            return None
        entries: list[tuple[str, int, tuple[object, ...]]] = []
        for name, descriptor in owner_namespace.items():
            if type_(name) is not str_type:
                return None
            entries.append((name, id_(descriptor), private_descriptor_seal(descriptor)))
        return (id_(owner), tuple_(id_(base) for base in owner_mro), tuple_(entries))

    sealed_classes: list[type[object]] = []
    seen_classes: set[int] = set()
    class_leaves: tuple[type[object], ...] = (
        guard_type,
        proxy_loader_type,
        dispatch_type,
        error_type,
        module_spec_type,
        builtin_finder,
        frozen_finder,
        path_finder,
        file_finder,
        source_loader_type,
        sourceless_loader_type,
        extension_loader_type,
        *((virtualenv_type,) if virtualenv_type is not None else ()),
    )
    for leaf in class_leaves:
        for owner in leaf.__mro__:
            if owner is object or owner.__module__ == "builtins" or id_(owner) in seen_classes:
                continue
            seen_classes.add(id_(owner))
            sealed_classes.append(owner)
    expected_class_surface: list[tuple[type[object], tuple[object, ...]]] = []
    for owner in sealed_classes:
        class_seal = private_class_seal(owner)
        if class_seal is None:
            raise ImportPolicyError("audit_hook_installation_failed")
        expected_class_surface.append((owner, class_seal))

    surface_functions: list[object] = []
    for owner, names in (
        (
            guard_type,
            ("find_spec", "_resolve_spec", "_validate_search_path", "_validate_standard_loader"),
        ),
        (proxy_loader_type, ("__init__", "create_module", "exec_module")),
        (dispatch_type, ("__init__",)),
        (error_type, ("__init__",)),
    ):
        owner_namespace = owner.__dict__
        for name in names:
            descriptor = owner_namespace.get(name)
            function_seal = private_function_seal(descriptor)
            if descriptor is None or function_seal is None:
                raise ImportPolicyError("audit_hook_installation_failed")
            surface_functions.append(descriptor)

    global_surface: list[tuple[dict[str, object], str, object, tuple[object, ...] | None]] = []
    seen_global_bindings: set[tuple[int, str]] = set()
    visited_functions: set[int] = set()

    def capture_global_binding(namespace: dict[str, object], name: str) -> object:
        key = (id_(namespace), name)
        expected = dict_get(namespace, name, missing_binding)
        if expected is missing_binding:
            return missing_binding
        if key not in seen_global_bindings:
            seen_global_bindings.add(key)
            global_surface.append((namespace, name, expected, private_function_seal(expected)))
        return expected

    def capture_code_bindings(
        code: CodeType,
        function_globals: dict[str, object],
        function_builtins: dict[str, object],
    ) -> None:
        for name in code.co_names:
            expected = capture_global_binding(function_globals, name)
            if expected is missing_binding:
                expected = capture_global_binding(function_builtins, name)
            if type_(expected) is function_type and getattr_(expected, "__module__", "").startswith(
                "laconian_eval."
            ):
                surface_functions.append(expected)
        for constant in code.co_consts:
            if type_(constant) is code_type:
                capture_code_bindings(constant, function_globals, function_builtins)

    while surface_functions:
        function = surface_functions.pop()
        if type_(function) is not function_type or id_(function) in visited_functions:
            continue
        visited_functions.add(id_(function))
        function_globals = object_getattribute(function, "__globals__")
        function_builtins = object_getattribute(function, "__builtins__")
        if type_(function_globals) is not dict_type or type_(function_builtins) is not dict_type:
            raise ImportPolicyError("audit_hook_installation_failed")
        capture_code_bindings(
            object_getattribute(function, "__code__"),
            function_globals,
            function_builtins,
        )

    expected_class_seals = tuple_(expected_class_surface)
    expected_global_surface = tuple_(global_surface)
    expected_machinery_classes = tuple_(
        (
            name,
            getattr_(machinery, name),
        )
        for name in (
            "BuiltinImporter",
            "FrozenImporter",
            "PathFinder",
            "FileFinder",
            "ModuleSpec",
            "SourceFileLoader",
            "SourcelessFileLoader",
            "ExtensionFileLoader",
        )
    )
    expected_suffixes = tuple_(
        (name, getattr_(machinery, name), tuple_(getattr_(machinery, name)))
        for name in ("SOURCE_SUFFIXES", "BYTECODE_SUFFIXES", "EXTENSION_SUFFIXES")
    )
    expected_create_dynamic = imp_module.create_dynamic
    expected_exec_dynamic = imp_module.exec_dynamic
    extension_create = extension_loader_type.__dict__.get("create_module")
    extension_exec = extension_loader_type.__dict__.get("exec_module")
    if type_(extension_create) is not function_type or type_(extension_exec) is not function_type:
        raise ImportPolicyError("audit_hook_installation_failed")
    extension_create_globals = object_getattribute(extension_create, "__globals__")
    extension_exec_globals = object_getattribute(extension_exec, "__globals__")

    expected_seal = private_snapshot_seal(audit_snapshot)
    if expected_seal is None:
        raise ImportPolicyError("audit_hook_installation_failed")
    expected_sentinel = guard.sentinel_name
    expected_state = audit_snapshot.runtime_state
    expected_sys_path = expected_state.sys_path
    expected_meta_path = expected_state.meta_path
    expected_path_hooks = expected_state.path_hooks
    expected_cache_items = tuple_(expected_state.importer_cache.items())
    expected_bindings = tuple_(
        (binding.key, binding.finder, binding.path, binding.loaders)
        for binding in audit_snapshot.cache_bindings
    )
    expected_roots: list[tuple[str, int, int]] = []
    seen_roots: set[tuple[int, int]] = set()
    for root in audit_snapshot.allowed_roots:
        root_key = (root.identity.device, root.identity.inode)
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        root_path = os_fspath(root.canonical_path)
        if type_(root_path) is not str_type or not root_path.startswith("/"):
            raise ImportPolicyError("audit_hook_installation_failed")
        expected_roots.append((root_path, root_key[0], root_key[1]))
    expected_root_entries = tuple_(expected_roots)
    expected_hook_code = audit_snapshot.file_finder_hook_code
    expected_path_resolver = audit_snapshot.path_find_spec
    expected_path_resolver_code = getattr_(expected_path_resolver, "__code__", None)
    probe_state: list[object] = [0, False, False]

    def root_identity_is_current(path: str, device: int, inode: int) -> bool:
        descriptor = -1
        try:
            descriptor = os_open("/", directory_flags)
            for component in path.split("/"):
                if component in ("", "."):
                    continue
                next_descriptor = os_open(component, directory_flags, dir_fd=descriptor)
                os_close(descriptor)
                descriptor = next_descriptor
            metadata = os_fstat(descriptor)
            return (
                metadata.st_mode & 0o170000 == 0o040000
                and metadata.st_dev == device
                and metadata.st_ino == inode
            )
        except handled_os_errors:
            return False
        finally:
            if descriptor >= 0:
                try:
                    os_close(descriptor)
                except handled_os_errors:
                    return False

    def fixed_finders_are_current() -> bool:
        if (
            machinery.BuiltinImporter is not builtin_finder
            or machinery.FrozenImporter is not frozen_finder
            or machinery.PathFinder is not path_finder
            or machinery.FileFinder is not file_finder
        ):
            return False
        current_builtin = builtin_finder.__dict__.get("find_spec")
        current_frozen = frozen_finder.__dict__.get("find_spec")
        current_path = path_finder.__dict__.get("find_spec")
        current_file = file_finder.__dict__.get("find_spec")
        if (
            current_builtin is not builtin_descriptor
            or current_frozen is not frozen_descriptor
            or current_path is not path_descriptor
            or current_file is not file_descriptor
            or type_(current_builtin) is not classmethod_type
            or type_(current_frozen) is not classmethod_type
            or type_(current_path) is not classmethod_type
            or type_(current_file) is not function_type
            or object_getattribute(object_getattribute(current_builtin, "__func__"), "__code__")
            is not audit_snapshot.builtin_find_spec_code
            or object_getattribute(object_getattribute(current_frozen, "__func__"), "__code__")
            is not audit_snapshot.frozen_find_spec_code
            or object_getattribute(object_getattribute(current_path, "__func__"), "__code__")
            is not audit_snapshot.path_find_spec_code
            or object_getattribute(current_file, "__code__")
            is not audit_snapshot.file_finder_find_spec_code
            or getattr_(expected_path_resolver, "__code__", None) is not expected_path_resolver_code
        ):
            return False
        if virtualenv_finder is not None:
            if virtualenv_type is None:
                return False
            current_virtualenv = virtualenv_type.__dict__.get("find_spec")
            if (
                current_virtualenv is not virtualenv_descriptor
                or getattr_(current_virtualenv, "__code__", None) is not virtualenv_code
            ):
                return False
        return True

    def post_audit_surface_is_current() -> bool:
        for owner, expected_class_seal in expected_class_seals:
            if private_class_seal(owner) != expected_class_seal:
                return False
        for namespace, name, expected, expected_global_function_seal in expected_global_surface:
            current = dict_get(namespace, name, missing_binding)
            if current is not expected:
                return False
            if expected_global_function_seal is not None and (
                private_function_seal(current) != expected_global_function_seal
            ):
                return False
        return True

    def module_manifest_is_current() -> bool:
        if importlib_module.machinery is not machinery:
            return False
        if any_(
            getattr_(machinery, name, missing_binding) is not expected
            for name, expected in expected_machinery_classes
        ):
            return False
        for name, expected_list, expected_values in expected_suffixes:
            current = getattr_(machinery, name, missing_binding)
            if (
                current is not expected_list
                or type_(current) is not list_type
                or tuple_(current) != expected_values
                or any_(type_(value) is not str_type for value in current)
            ):
                return False
        return (
            zipimport_module.zipimporter is zipimporter_type
            and imp_module.create_dynamic is expected_create_dynamic
            and imp_module.exec_dynamic is expected_exec_dynamic
            and dict_get(extension_create_globals, "_imp", missing_binding) is imp_module
            and dict_get(extension_exec_globals, "_imp", missing_binding) is imp_module
        )

    def hidden_validate() -> None:
        if type_(guard) is not guard_type:
            raise error_type("guard_integrity_drift")
        try:
            installed = object_getattribute(guard, "_LaconianImportGuard__installed")
            sentinel = object_getattribute(guard, "_LaconianImportGuard__sentinel_name")
            guard_snapshot = object_getattribute(guard, "_LaconianImportGuard__snapshot")
        except attribute_error:
            raise error_type("guard_integrity_drift") from None
        if (
            installed is not True
            or type_(sentinel) is not str_type
            or sentinel != expected_sentinel
            or private_snapshot_seal(guard_snapshot) != expected_seal
        ):
            raise error_type("guard_integrity_drift")
        if any_(
            not root_identity_is_current(path, device, inode)
            for path, device, inode in expected_root_entries
        ):
            raise error_type("import_root_identity_drift")
        live_path = sys_module.path
        if type_(live_path) is not list_type or any_(
            type_(item) is not str_type for item in live_path
        ):
            raise error_type("sys_path_drift")
        if tuple_(live_path) != expected_sys_path:
            raise error_type("sys_path_drift")
        live_meta = sys_module.meta_path
        if type_(live_meta) is not list_type:
            raise error_type("guard_order_drift")
        if len_(live_meta) != len_(expected_meta_path) + 1 or any_(
            actual is not expected
            for actual, expected in zip_(live_meta, (guard, *expected_meta_path), strict=True)
        ):
            raise error_type("guard_order_drift")
        live_hooks = sys_module.path_hooks
        if type_(live_hooks) is not list_type:
            raise error_type("path_hooks_drift")
        if len_(live_hooks) != len_(expected_path_hooks) or any_(
            actual is not expected
            for actual, expected in zip_(live_hooks, expected_path_hooks, strict=True)
        ):
            raise error_type("path_hooks_drift")
        if getattr_(live_hooks[1], "__code__", None) is not expected_hook_code:
            raise error_type("path_hooks_drift")
        live_cache = sys_module.path_importer_cache
        if type_(live_cache) is not dict_type or any_(
            type_(key) is not str_type for key in live_cache
        ):
            raise error_type("importer_cache_drift")
        live_cache_items = tuple_(dict_items(live_cache))
        if len_(live_cache_items) != len_(expected_cache_items) or any_(
            actual_key != expected_key or actual_value is not expected_value
            for (actual_key, actual_value), (expected_key, expected_value) in zip_(
                live_cache_items, expected_cache_items, strict=True
            )
        ):
            raise error_type("importer_cache_drift")
        for key, finder, expected_path, expected_loaders in expected_bindings:
            if dict_get(live_cache, key) is not finder:
                raise error_type("importer_cache_drift")
            finder_path = getattr_(finder, "path", None)
            namespace = getattr_(finder, "__dict__", None)
            loaders = getattr_(finder, "_loaders", None)
            if type_(finder_path) is not str_type or finder_path != expected_path:
                raise error_type("importer_cache_drift")
            if type_(namespace) is not dict_type:
                raise error_type("importer_cache_drift")
            namespace_dict: dict[object, object] = namespace  # type: ignore[assignment]
            if "find_spec" in namespace_dict:
                raise error_type("importer_cache_drift")
            if type_(loaders) is not list_type:
                raise error_type("importer_cache_drift")
            loader_entries: list[object] = loaders  # type: ignore[assignment]
            if len_(loader_entries) != len_(expected_loaders) or any_(
                type_(actual) is not tuple_type
                or len_(actual) != 2  # type: ignore[arg-type]
                or type_(actual[0]) is not str_type  # type: ignore[index]
                or actual[0] != expected[0]  # type: ignore[index]
                or actual[1] is not expected[1]  # type: ignore[index]
                for actual, expected in zip_(loader_entries, expected_loaders, strict=True)
            ):
                raise error_type("importer_cache_drift")
        if audit_snapshot.enforce_fixed_finders and not fixed_finders_are_current():
            raise error_type("meta_path_finder_drift")
        if not module_manifest_is_current() or not post_audit_surface_is_current():
            raise error_type("guard_callable_drift")

    def audit_hook(event: str, arguments: tuple[object, ...]) -> None:
        if event == "sys.addaudithook":
            # CPython suppresses this exception but aborts the later hook registration.
            raise error_type("audit_hook_registration_drift")
        if event == "laconian.import_policy.audit_probe":
            list_setitem(probe_state, 1, True)
            return
        if event != "import":
            return
        import_events = list_getitem(probe_state, 0)
        if type_(import_events) is not int_type:
            raise error_type("audit_hook_installation_failed")
        import_event_count: int = import_events  # type: ignore[assignment]
        list_setitem(probe_state, 0, import_event_count + 1)
        if arguments and arguments[0] == expected_sentinel:
            list_setitem(probe_state, 2, True)
        hidden_validate()

    return audit_hook, probe_state


def _check_live_fixed_state(
    snapshot: _EnforcementSnapshot,
    guard: _LaconianImportGuard,
) -> None:
    _revalidate_root_identities(snapshot.allowed_roots)
    expected = snapshot.runtime_state
    if type(sys.path) is not list or any(type(item) is not str for item in sys.path):
        raise ImportPolicyError("sys_path_drift")
    if type(sys.meta_path) is not list:
        raise ImportPolicyError("guard_order_drift")
    if type(sys.path_hooks) is not list:
        raise ImportPolicyError("path_hooks_drift")
    if type(sys.path_importer_cache) is not dict or any(
        type(key) is not str for key in sys.path_importer_cache
    ):
        raise ImportPolicyError("importer_cache_drift")
    if tuple(sys.path) != expected.sys_path:
        raise ImportPolicyError("sys_path_drift")
    meta = tuple(sys.meta_path)
    expected_meta = (guard, *expected.meta_path)
    if not _same_identity_sequence(meta, expected_meta):
        raise ImportPolicyError("guard_order_drift")
    if not _same_identity_sequence(tuple(sys.path_hooks), expected.path_hooks):
        raise ImportPolicyError("path_hooks_drift")
    if not _same_cache(sys.path_importer_cache, expected.importer_cache):
        raise ImportPolicyError("importer_cache_drift")
    _revalidate_cache_bindings(
        snapshot.cache_bindings,
        sys.path_importer_cache,
        code="importer_cache_drift",
    )
    if snapshot.enforce_fixed_finders:
        _revalidate_fixed_finder_descriptors(snapshot)


@dataclass(frozen=True, slots=True)
class _AuditHookStatus:
    import_events: int


@dataclass(frozen=True, slots=True)
class GuardInstallation:
    guard: _LaconianImportGuard = field(repr=False)
    audit_hook: _AuditHookStatus = field(repr=False)
    sentinel_name: str
    sentinel_audit_observed: bool
    sentinel_guard_blocked: bool


def _initial_state_unchanged(policy: ImportPolicy) -> bool:
    state = policy.initial_state
    return (
        tuple(sys.path) == state.sys_path
        and _same_identity_sequence(tuple(sys.meta_path), state.meta_path)
        and _same_identity_sequence(tuple(sys.path_hooks), state.path_hooks)
        and _same_cache(sys.path_importer_cache, state.importer_cache)
    )


def install_import_guard(policy: ImportPolicy) -> GuardInstallation:
    """Install the irreversible audit hook and first finder; call only in owned processes."""

    if not _initial_state_unchanged(policy):
        raise ImportPolicyError("runtime_state_changed_before_guard")
    _revalidate_owned_origins(policy)
    revalidate_loaded_modules(policy)
    current_bootstrap = inspect_site_bootstrap(
        tuple(root.canonical_path for root in policy.site_roots),
        runner_parent=policy.runner_parent_root.canonical_path,
        meta_path=policy.initial_state.meta_path,
    )
    if current_bootstrap != policy.bootstrap:
        raise ImportPolicyError("site_bootstrap_changed")
    guard = _LaconianImportGuard(policy)
    snapshot = guard._snapshot_for_install(policy.enforcement_token)
    audit_hook, audit_state = _make_application_audit_hook(snapshot, guard)
    try:
        sys.addaudithook(audit_hook)
        sys.audit("laconian.import_policy.audit_probe")
    except BaseException:
        raise ImportPolicyError("audit_hook_installation_failed") from None
    if audit_state[1] is not True:
        raise ImportPolicyError("audit_hook_installation_failed")
    sys.path[:] = policy.runtime_state.sys_path
    sys.path_importer_cache.clear()
    sys.path_importer_cache.update(cast(Any, policy.runtime_state.importer_cache))
    sys.meta_path.insert(0, guard)
    guard._arm_installed(policy.enforcement_token)
    blocked = False
    try:
        __import__(guard.sentinel_name)
    except ImportPolicyError as exc:
        if exc.code != "import_origin_not_allowed":
            raise
        blocked = True
    if not blocked or audit_state[2] is not True or guard.sentinel_blocks != 1:
        raise ImportPolicyError("guard_self_test_failed")
    _check_live_fixed_state(snapshot, guard)
    return GuardInstallation(
        guard=guard,
        audit_hook=_AuditHookStatus(import_events=cast(int, audit_state[0])),
        sentinel_name=guard.sentinel_name,
        sentinel_audit_observed=cast(bool, audit_state[2]),
        sentinel_guard_blocked=blocked,
    )
