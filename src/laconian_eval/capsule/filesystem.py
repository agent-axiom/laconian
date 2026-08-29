"""Fail-closed local-filesystem classification, locking, and staging ownership.

All caller paths enter this layer as already-open directory descriptors.  The module borrows those
descriptors, owns only the lock and staging descriptors it opens, and never falls back to a
path-based rename or a check-then-publish sequence.
"""

from __future__ import annotations

import errno
import multiprocessing
import os
import signal
import stat
import sys
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any, Literal, Protocol, Self
from uuid import RFC_4122, UUID

from laconian_eval.capsule.posix import (
    DEFAULT_MOUNTINFO_BYTE_LIMIT,
    FileSystemStat,
    MountIdentity,
    PosixOps,
)
from laconian_eval.capsule.schema import FilesystemClass

EXT_SUPER_MAGIC = 0x0000EF53
XFS_SUPER_MAGIC = 0x58465342
BTRFS_SUPER_MAGIC = 0x9123683E
ZFS_SUPER_MAGIC = 0x2FC12FC1
MNT_LOCAL = 0x00001000

CREATOR_LOCK_NAME = ".laconian-create.lock"
PERSISTENT_LOCK_NAME = ".laconian.lock"

_PROBE_DIRECTORY_NAME = ".laconian-probe"
_PROCESS_HANDSHAKE_SECONDS = 10.0
_MAX_CLEANUP_DEPTH = 64
_MAX_CLEANUP_ENTRIES = 100_000
_UINT32_MAX = (1 << 32) - 1
_INT32_MAX = (1 << 31) - 1
_GENERIC_UNSUPPORTED_MESSAGE = "filesystem contract is unsupported"
_GENERIC_OWNERSHIP_MESSAGE = "owned filesystem path is unsafe"
_GENERIC_PUBLICATION_MESSAGE = "capsule publication failed"
_CLEANUP_FAILURE_NOTE = "filesystem cleanup also failed"
_DESCRIPTOR_CLOSE_FAILURE_NOTE = "filesystem descriptor close also failed"
_LOCK_RELEASE_FAILURE_NOTE = "filesystem lock release also failed"
_CHILD_CLEANUP_FAILURE_NOTE = "filesystem child cleanup also failed"

_LINUX_MAGIC_CLASSES: dict[int, FilesystemClass] = {
    EXT_SUPER_MAGIC: "ext-family",
    XFS_SUPER_MAGIC: "xfs",
    BTRFS_SUPER_MAGIC: "btrfs",
    ZFS_SUPER_MAGIC: "zfs",
}
_LINUX_TYPE_CLASSES: dict[str, FilesystemClass] = {
    "ext2": "ext-family",
    "ext3": "ext-family",
    "ext4": "ext-family",
    "xfs": "xfs",
    "btrfs": "btrfs",
    "zfs": "zfs",
}
_DARWIN_TYPE_CLASSES: dict[str, FilesystemClass] = {
    "apfs": "apfs",
    "hfs": "hfsplus",
}

StagingState = Literal["owned", "published", "removed", "abandoned"]
ProbeChildWaitState = Literal[
    "reaped",
    "still_child_timeout",
    "not_child",
    "wait_error",
    "channel_error",
]
ContentionProbe = Callable[[int, str], None]


class FilesystemPosixOps(Protocol):
    """The raw operations consumed by this policy layer."""

    platform: str

    def fstatfs(self, descriptor: int) -> FileSystemStat: ...

    def statx_mount_identity(self, descriptor: int) -> MountIdentity: ...

    def read_mountinfo(self, byte_limit: int = DEFAULT_MOUNTINFO_BYTE_LIMIT) -> bytes: ...

    def rename_noreplace(
        self,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None: ...

    def link_noreplace(
        self,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None: ...

    def acquire_lock(self, descriptor: int, *, exclusive: bool, blocking: bool) -> None: ...

    def release_lock(self, descriptor: int) -> None: ...

    def fsync(self, descriptor: int) -> None: ...


class UnsupportedFilesystemError(RuntimeError):
    """A content-free failure to establish the required local-filesystem contract."""

    code = "unsupported_filesystem"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(_GENERIC_UNSUPPORTED_MESSAGE)


class OwnedStagingError(RuntimeError):
    """A content-free ownership, descriptor, or lock-leaf validation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_GENERIC_OWNERSHIP_MESSAGE)


class DestinationCollisionError(RuntimeError):
    """An atomic publication found an existing destination and published nothing."""

    code = "destination_collision"
    published = False

    def __init__(self) -> None:
        super().__init__(_GENERIC_PUBLICATION_MESSAGE)


class PostPublishSyncError(RuntimeError):
    """Publication succeeded but synchronizing the already-open parent directory failed."""

    code = "post_publish_fsync_failed"
    published = True

    def __init__(self, destination_name: str, *, publication_path: Path | None = None) -> None:
        self.destination_name = destination_name
        self.publication_path = publication_path
        super().__init__(_GENERIC_PUBLICATION_MESSAGE)


@dataclass(frozen=True, slots=True)
class MountInfoEntry:
    """The mount identity fields needed from one Linux mountinfo record."""

    mount_id: int
    device_major: int
    device_minor: int
    filesystem_type: str


@dataclass(frozen=True, slots=True)
class FilesystemIdentity:
    """An allowlisted class tied to the descriptor's current mount identity."""

    filesystem_class: FilesystemClass
    device: int
    mount_id: int | None


@dataclass(frozen=True, slots=True)
class LockProbeEvidence:
    """Observable facts established by the real second-process lock probe."""

    parent_pid: int
    child_pid: int
    child_observed_contention: bool
    child_acquired_after_release: bool
    parent_reacquired_after_child_death: bool


@dataclass(frozen=True, slots=True)
class _DirectoryIdentity:
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class _CleanupMountIdentity:
    device: int
    mount_id: int | None


@dataclass(frozen=True, slots=True)
class _ProbeChildWaitOutcome:
    state: ProbeChildWaitState
    wait_status: int | None = None


@dataclass(slots=True)
class OwnedStaging:
    """One freshly created operation-owned staging directory."""

    parent_directory_fd: int
    name: str
    descriptor: int
    identity: _DirectoryIdentity
    _state: StagingState = field(default="owned", repr=False)
    _descriptor_owned: bool = field(default=True, repr=False)

    @property
    def state(self) -> StagingState:
        return self._state

    def close(self) -> None:
        """Consume and close the module-opened descriptor at most once."""

        if not self._descriptor_owned:
            return
        self._descriptor_owned = False
        if self._state == "owned":
            self._state = "abandoned"
        os.close(self.descriptor)


@dataclass(slots=True)
class LockHandle:
    """One module-owned descriptor with a held advisory lock."""

    descriptor: int
    _posix: FilesystemPosixOps = field(repr=False)
    _exclusive: bool = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        release_error: BaseException | None = None
        try:
            self._posix.release_lock(self.descriptor)
        except BaseException as error:
            release_error = error
        try:
            os.close(self.descriptor)
        except BaseException:
            if release_error is None:
                raise
        if release_error is not None:
            raise release_error

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        exception: BaseException | None,
        _traceback: object | None,
    ) -> None:
        try:
            self.close()
        except BaseException:
            if exception is None:
                raise
            exception.add_note(_LOCK_RELEASE_FAILURE_NOTE)


@dataclass(slots=True)
class PreparationFilesystem:
    """A creator-locked, probed workspace for one preparation operation."""

    filesystem_identity: FilesystemIdentity
    staging: OwnedStaging
    _posix: FilesystemPosixOps = field(repr=False)

    def publish(self, destination_name: str) -> None:
        publish_owned_staging(self.staging, destination_name, posix=self._posix)


def _unsupported(reason: str) -> UnsupportedFilesystemError:
    return UnsupportedFilesystemError(reason)


def _bounded_uint(raw: bytes, *, maximum: int, positive: bool) -> int:
    if not raw or any(byte < ord("0") or byte > ord("9") for byte in raw):
        raise _unsupported("invalid_mountinfo")
    if len(raw) > len(str(maximum)):
        raise _unsupported("invalid_mountinfo")
    value = int(raw)
    if value > maximum or (positive and value == 0):
        raise _unsupported("invalid_mountinfo")
    return value


def _valid_mountinfo_token(raw: bytes, *, escaped: bool = False) -> bool:
    if not raw:
        return False
    offset = 0
    while offset < len(raw):
        byte = raw[offset]
        if byte == ord("\\"):
            if not escaped or raw[offset : offset + 4] not in {
                b"\\011",
                b"\\012",
                b"\\040",
                b"\\134",
            }:
                return False
            offset += 4
            continue
        if byte <= 0x20 or byte == 0x7F:
            return False
        offset += 1
    return True


def parse_linux_mountinfo(
    raw: bytes,
    *,
    byte_limit: int = DEFAULT_MOUNTINFO_BYTE_LIMIT,
) -> tuple[MountInfoEntry, ...]:
    """Parse one bounded, strictly LF-framed Linux mountinfo snapshot."""

    if (
        type(raw) is not bytes
        or type(byte_limit) is not int
        or byte_limit < 1
        or byte_limit > DEFAULT_MOUNTINFO_BYTE_LIMIT
        or not raw
        or len(raw) > byte_limit
        or not raw.endswith(b"\n")
    ):
        raise _unsupported("invalid_mountinfo")

    entries: list[MountInfoEntry] = []
    for line in raw[:-1].split(b"\n"):
        fields = line.split(b" ")
        if len(fields) < 10 or any(not item for item in fields):
            raise _unsupported("invalid_mountinfo")
        separator_indices = [index for index, item in enumerate(fields) if item == b"-"]
        if len(separator_indices) != 1:
            raise _unsupported("invalid_mountinfo")
        separator = separator_indices[0]
        if separator < 6 or len(fields) - separator != 4:
            raise _unsupported("invalid_mountinfo")

        mount_id = _bounded_uint(fields[0], maximum=_INT32_MAX, positive=True)
        _bounded_uint(fields[1], maximum=_INT32_MAX, positive=False)
        device_parts = fields[2].split(b":")
        if len(device_parts) != 2:
            raise _unsupported("invalid_mountinfo")
        device_major = _bounded_uint(device_parts[0], maximum=_UINT32_MAX, positive=False)
        device_minor = _bounded_uint(device_parts[1], maximum=_UINT32_MAX, positive=False)

        if not _valid_mountinfo_token(fields[3], escaped=True):
            raise _unsupported("invalid_mountinfo")
        if not _valid_mountinfo_token(fields[4], escaped=True):
            raise _unsupported("invalid_mountinfo")
        if not _valid_mountinfo_token(fields[5]):
            raise _unsupported("invalid_mountinfo")
        if any(not _valid_mountinfo_token(item) for item in fields[6:separator]):
            raise _unsupported("invalid_mountinfo")

        raw_type = fields[separator + 1]
        raw_source = fields[separator + 2]
        super_options = fields[separator + 3]
        if not _valid_mountinfo_token(raw_source, escaped=True) or not _valid_mountinfo_token(
            super_options
        ):
            raise _unsupported("invalid_mountinfo")
        try:
            filesystem_type = raw_type.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            raise _unsupported("invalid_mountinfo") from None
        if not filesystem_type or any(
            not (character.isalnum() or character in "._-") for character in filesystem_type
        ):
            raise _unsupported("invalid_mountinfo")
        entries.append(
            MountInfoEntry(
                mount_id=mount_id,
                device_major=device_major,
                device_minor=device_minor,
                filesystem_type=filesystem_type,
            )
        )
    return tuple(entries)


def _descriptor_device(descriptor: int) -> int:
    if type(descriptor) is not int or descriptor < 0:
        raise _unsupported("invalid_descriptor")
    try:
        metadata = os.fstat(descriptor)
    except OSError:
        raise _unsupported("filesystem_probe_failed") from None
    if not stat.S_ISDIR(metadata.st_mode):
        raise _unsupported("invalid_descriptor")
    return int(metadata.st_dev)


def classify_filesystem(
    descriptor: int,
    *,
    posix: FilesystemPosixOps,
    mountinfo_byte_limit: int = DEFAULT_MOUNTINFO_BYTE_LIMIT,
) -> FilesystemIdentity:
    """Classify the current descriptor filesystem using only exact platform allowlists."""

    device = _descriptor_device(descriptor)
    try:
        raw_stat = posix.fstatfs(descriptor)
    except (OSError, RuntimeError, ValueError):
        raise _unsupported("filesystem_probe_failed") from None
    if raw_stat.platform != posix.platform:
        raise _unsupported("invalid_filesystem_stat")

    if posix.platform == "darwin":
        if (
            raw_stat.type_magic is not None
            or type(raw_stat.type_name) is not str
            or type(raw_stat.flags) is not int
        ):
            raise _unsupported("invalid_filesystem_stat")
        if not raw_stat.flags & MNT_LOCAL:
            raise _unsupported("nonlocal_filesystem")
        filesystem_class = _DARWIN_TYPE_CLASSES.get(raw_stat.type_name)
        if filesystem_class is None:
            raise _unsupported("unclassified_filesystem")
        return FilesystemIdentity(
            filesystem_class=filesystem_class,
            device=device,
            mount_id=None,
        )

    if posix.platform != "linux":
        raise _unsupported("unsupported_platform")
    if (
        type(raw_stat.type_magic) is not int
        or raw_stat.type_name is not None
        or type(raw_stat.flags) is not int
    ):
        raise _unsupported("invalid_filesystem_stat")
    filesystem_class = _LINUX_MAGIC_CLASSES.get(raw_stat.type_magic)
    if filesystem_class is None:
        raise _unsupported("unclassified_filesystem")

    try:
        descriptor_mount = posix.statx_mount_identity(descriptor)
        descriptor_major = os.major(device)
        descriptor_minor = os.minor(device)
    except (OSError, RuntimeError, ValueError):
        raise _unsupported("filesystem_probe_failed") from None
    if (
        descriptor_mount.device_major != descriptor_major
        or descriptor_mount.device_minor != descriptor_minor
    ):
        raise _unsupported("descriptor_identity_conflict")

    try:
        raw_mountinfo = posix.read_mountinfo(mountinfo_byte_limit)
    except (OSError, RuntimeError, ValueError):
        raise _unsupported("filesystem_probe_failed") from None
    entries = parse_linux_mountinfo(raw_mountinfo, byte_limit=mountinfo_byte_limit)
    matches = tuple(entry for entry in entries if entry.mount_id == descriptor_mount.mount_id)
    if not matches:
        raise _unsupported("mountinfo_absent")
    if len(matches) != 1:
        raise _unsupported("mountinfo_ambiguous")
    selected = matches[0]
    if (
        selected.device_major != descriptor_major
        or selected.device_minor != descriptor_minor
        or _LINUX_TYPE_CLASSES.get(selected.filesystem_type) != filesystem_class
    ):
        raise _unsupported("mountinfo_conflict")
    return FilesystemIdentity(
        filesystem_class=filesystem_class,
        device=device,
        mount_id=descriptor_mount.mount_id,
    )


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int:
        raise OwnedStagingError("unsupported_open_flags")
    return value


def _close_on_exec_flag() -> int:
    value = getattr(os, "O_CLOEXEC", 0)
    return value if type(value) is int else 0


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | _required_open_flag("O_DIRECTORY")
        | _required_open_flag("O_NOFOLLOW")
        | _close_on_exec_flag()
    )


def _lock_open_flags(*, writable: bool, create: bool) -> int:
    flags = os.O_RDWR if writable else os.O_RDONLY
    flags |= _required_open_flag("O_NOFOLLOW")
    flags |= _required_open_flag("O_NONBLOCK")
    flags |= _close_on_exec_flag()
    if create:
        flags |= os.O_CREAT
    return flags


def _leaf_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode)


def _open_lock(
    directory_fd: int,
    name: str,
    *,
    posix: FilesystemPosixOps,
    writable: bool,
    create: bool,
    exclusive: bool,
    blocking: bool,
) -> LockHandle | None:
    _require_directory(directory_fd)
    flags = _lock_open_flags(writable=writable, create=create)
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    acquired = False
    descriptor_owned = True
    try:
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_stat.st_mode):
            raise OwnedStagingError("unsafe_lock_file")
        path_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(path_stat.st_mode) or _leaf_identity(path_stat) != _leaf_identity(
            descriptor_stat
        ):
            raise OwnedStagingError("unsafe_lock_file")
        try:
            posix.acquire_lock(descriptor, exclusive=exclusive, blocking=blocking)
        except BlockingIOError as error:
            if not blocking and error.errno in {errno.EAGAIN, errno.EWOULDBLOCK}:
                descriptor_owned = False
                os.close(descriptor)
                return None
            raise
        acquired = True
        path_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if _leaf_identity(path_after) != _leaf_identity(descriptor_stat):
            raise OwnedStagingError("unsafe_lock_file")
    except BaseException:
        if acquired:
            with suppress(OSError):
                posix.release_lock(descriptor)
        if descriptor_owned:
            descriptor_owned = False
            with suppress(OSError):
                os.close(descriptor)
        raise
    return LockHandle(descriptor=descriptor, _posix=posix, _exclusive=exclusive)


def acquire_creator_lock(
    results_root_fd: int,
    *,
    posix: FilesystemPosixOps,
) -> LockHandle:
    """Open and acquire the results-root creator lock exclusively and blocking."""

    handle = _open_lock(
        results_root_fd,
        CREATOR_LOCK_NAME,
        posix=posix,
        writable=True,
        create=True,
        exclusive=True,
        blocking=True,
    )
    assert handle is not None
    return handle


def try_acquire_mutator_lock(
    capsule_directory_fd: int,
    *,
    posix: FilesystemPosixOps,
) -> LockHandle | None:
    """Try the existing capsule lock exclusively, returning ``None`` when busy."""

    return _open_lock(
        capsule_directory_fd,
        PERSISTENT_LOCK_NAME,
        posix=posix,
        writable=True,
        create=False,
        exclusive=True,
        blocking=False,
    )


def try_acquire_shared_lock(
    capsule_directory_fd: int,
    *,
    posix: FilesystemPosixOps,
) -> LockHandle | None:
    """Try the existing capsule lock shared, returning ``None`` when busy."""

    return _open_lock(
        capsule_directory_fd,
        PERSISTENT_LOCK_NAME,
        posix=posix,
        writable=False,
        create=False,
        exclusive=False,
        blocking=False,
    )


def _require_directory(descriptor: int) -> os.stat_result:
    if type(descriptor) is not int or descriptor < 0:
        raise OwnedStagingError("invalid_directory_descriptor")
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise OwnedStagingError("invalid_directory_descriptor")
    return metadata


def _directory_identity(metadata: os.stat_result) -> _DirectoryIdentity:
    if not stat.S_ISDIR(metadata.st_mode):
        raise OwnedStagingError("staging_identity_mismatch")
    return _DirectoryIdentity(device=metadata.st_dev, inode=metadata.st_ino)


def _validate_leaf_name(name: str) -> str:
    if type(name) is not str or name in {"", ".", ".."} or "/" in name:
        raise OwnedStagingError("invalid_leaf_name")
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in name):
        raise OwnedStagingError("invalid_leaf_name")
    try:
        name.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise OwnedStagingError("invalid_leaf_name") from None
    return name


def _create_owned_directory(
    parent_directory_fd: int,
    name: str,
    *,
    mode: int,
) -> OwnedStaging:
    _require_directory(parent_directory_fd)
    checked_name = _validate_leaf_name(name)
    os.mkdir(checked_name, mode, dir_fd=parent_directory_fd)
    created_identity: _DirectoryIdentity | None = None
    try:
        path_metadata = os.stat(checked_name, dir_fd=parent_directory_fd, follow_symlinks=False)
        created_identity = _directory_identity(path_metadata)
        descriptor = os.open(checked_name, _directory_open_flags(), dir_fd=parent_directory_fd)
    except BaseException:
        _rollback_empty_created_directory(parent_directory_fd, checked_name, created_identity)
        raise
    try:
        descriptor_metadata = os.fstat(descriptor)
        descriptor_identity = _directory_identity(descriptor_metadata)
        if created_identity != descriptor_identity:
            raise OwnedStagingError("staging_identity_mismatch")
    except BaseException:
        try:
            os.close(descriptor)
        finally:
            _rollback_empty_created_directory(parent_directory_fd, checked_name, created_identity)
        raise
    return OwnedStaging(
        parent_directory_fd=parent_directory_fd,
        name=checked_name,
        descriptor=descriptor,
        identity=descriptor_identity,
    )


def _rollback_empty_created_directory(
    parent_directory_fd: int,
    name: str,
    identity: _DirectoryIdentity | None,
) -> None:
    if identity is None:
        return
    try:
        current = os.stat(name, dir_fd=parent_directory_fd, follow_symlinks=False)
        if _directory_identity(current) != identity:
            return
        os.rmdir(name, dir_fd=parent_directory_fd)
    except (OSError, OwnedStagingError):
        return


def create_owned_staging(parent_directory_fd: int, operation_id: UUID) -> OwnedStaging:
    """Create the exact private sibling staging directory for one UUID4 operation."""

    if (
        type(operation_id) is not UUID
        or operation_id.variant != RFC_4122
        or operation_id.version != 4
    ):
        raise OwnedStagingError("invalid_operation_id")
    return _create_owned_directory(
        parent_directory_fd,
        f".laconian-stage.{operation_id}",
        mode=0o700,
    )


def _validate_owned_directory(staging: OwnedStaging) -> None:
    if staging.state != "owned" or not staging._descriptor_owned:
        raise OwnedStagingError("staging_not_owned")
    descriptor_metadata = os.fstat(staging.descriptor)
    if _directory_identity(descriptor_metadata) != staging.identity:
        raise OwnedStagingError("staging_identity_mismatch")
    path_metadata = os.stat(
        staging.name,
        dir_fd=staging.parent_directory_fd,
        follow_symlinks=False,
    )
    if _directory_identity(path_metadata) != staging.identity:
        raise OwnedStagingError("staging_identity_mismatch")


def _same_cleanup_mount(
    root: _CleanupMountIdentity,
    descriptor: int,
    *,
    posix: FilesystemPosixOps,
) -> bool:
    metadata = os.fstat(descriptor)
    if metadata.st_dev != root.device:
        return False
    if root.mount_id is None:
        return True
    try:
        identity = posix.statx_mount_identity(descriptor)
    except (OSError, RuntimeError, ValueError):
        return False
    return (
        identity.mount_id == root.mount_id
        and identity.device_major == os.major(root.device)
        and identity.device_minor == os.minor(root.device)
    )


def _cleanup_identity(
    staging: OwnedStaging,
    posix: FilesystemPosixOps,
) -> _CleanupMountIdentity:
    descriptor_metadata = os.fstat(staging.descriptor)
    mount_id: int | None = None
    if posix.platform == "linux":
        try:
            raw_identity = posix.statx_mount_identity(staging.descriptor)
        except (OSError, RuntimeError, ValueError):
            raise OwnedStagingError("staging_identity_mismatch") from None
        if raw_identity.device_major != os.major(
            descriptor_metadata.st_dev
        ) or raw_identity.device_minor != os.minor(descriptor_metadata.st_dev):
            raise OwnedStagingError("staging_identity_mismatch")
        mount_id = raw_identity.mount_id
    return _CleanupMountIdentity(
        device=descriptor_metadata.st_dev,
        mount_id=mount_id,
    )


def _empty_owned_directory(
    descriptor: int,
    *,
    root_identity: _CleanupMountIdentity,
    posix: FilesystemPosixOps,
    depth: int,
    entry_count: list[int],
) -> None:
    if depth > _MAX_CLEANUP_DEPTH:
        raise OwnedStagingError("staging_cleanup_limit")
    with os.scandir(descriptor) as iterator:
        for entry in iterator:
            entry_count[0] += 1
            if entry_count[0] > _MAX_CLEANUP_ENTRIES:
                raise OwnedStagingError("staging_cleanup_limit")
            name = entry.name
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                child_fd = os.open(name, _directory_open_flags(), dir_fd=descriptor)
                try:
                    child_metadata = os.fstat(child_fd)
                    if _leaf_identity(child_metadata) != _leaf_identity(metadata):
                        raise OwnedStagingError("staging_identity_mismatch")
                    if not _same_cleanup_mount(root_identity, child_fd, posix=posix):
                        raise OwnedStagingError("staging_identity_mismatch")
                    _empty_owned_directory(
                        child_fd,
                        root_identity=root_identity,
                        posix=posix,
                        depth=depth + 1,
                        entry_count=entry_count,
                    )
                    posix.fsync(child_fd)
                finally:
                    os.close(child_fd)
                after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if _leaf_identity(after) != _leaf_identity(metadata):
                    raise OwnedStagingError("staging_identity_mismatch")
                os.rmdir(name, dir_fd=descriptor)
            else:
                os.unlink(name, dir_fd=descriptor)
    posix.fsync(descriptor)


def cleanup_owned_staging(
    staging: OwnedStaging,
    *,
    posix: FilesystemPosixOps,
) -> None:
    """Remove only an identity-validated, still-owned staging directory and sync its parent."""

    try:
        _validate_owned_directory(staging)
        root_identity = _cleanup_identity(staging, posix)
        _empty_owned_directory(
            staging.descriptor,
            root_identity=root_identity,
            posix=posix,
            depth=0,
            entry_count=[0],
        )
        _validate_owned_directory(staging)
        path_metadata = os.stat(
            staging.name,
            dir_fd=staging.parent_directory_fd,
            follow_symlinks=False,
        )
        if _directory_identity(path_metadata) != staging.identity:
            raise OwnedStagingError("staging_identity_mismatch")
        os.rmdir(staging.name, dir_fd=staging.parent_directory_fd)
    except BaseException:
        if staging.state == "owned":
            with suppress(BaseException):
                staging.close()
        raise
    staging._state = "removed"
    try:
        posix.fsync(staging.parent_directory_fd)
    except BaseException as primary_error:
        try:
            staging.close()
        except BaseException:
            primary_error.add_note(_DESCRIPTOR_CLOSE_FAILURE_NOTE)
        raise
    staging.close()


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        try:
            written = os.write(descriptor, data[offset:])
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError(errno.EIO, "probe write failed")
        offset += written


def _create_probe_file(directory_fd: int, name: str, data: bytes) -> int:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | _required_open_flag("O_NOFOLLOW")
        | _required_open_flag("O_NONBLOCK")
        | _close_on_exec_flag()
    )
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OwnedStagingError("unsafe_probe_path")
        _write_all(descriptor, data)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _assert_leaf_unchanged(
    directory_fd: int,
    name: str,
    expected: tuple[int, int, int],
) -> None:
    actual = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if _leaf_identity(actual) != expected:
        raise _unsupported("capability_probe_failed")


def _probe_child(
    directory_fd: int,
    name: str,
    inherited_parent_lock_fd: int,
    opened: Any,
    attempt: Any,
    released: Any,
    sender: Any,
) -> None:
    descriptor: int | None = None
    child_posix: PosixOps | None = None
    try:
        os.close(inherited_parent_lock_fd)
        descriptor = os.open(
            name,
            _lock_open_flags(writable=True, create=False),
            dir_fd=directory_fd,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            sender.send(("unsafe", os.getpid()))
            return
        child_posix = PosixOps()
        opened.set()
        if not attempt.wait(_PROCESS_HANDSHAKE_SECONDS):
            sender.send(("timeout", os.getpid()))
            return
        try:
            child_posix.acquire_lock(descriptor, exclusive=True, blocking=False)
        except BlockingIOError as error:
            if error.errno not in {errno.EAGAIN, errno.EWOULDBLOCK}:
                sender.send(("error", os.getpid()))
                return
            sender.send(("contended", os.getpid()))
        else:
            child_posix.release_lock(descriptor)
            sender.send(("not_contended", os.getpid()))
            return
        if not released.wait(_PROCESS_HANDSHAKE_SECONDS):
            sender.send(("timeout", os.getpid()))
            return
        child_posix.acquire_lock(descriptor, exclusive=True, blocking=False)
        sender.send(("reacquired", os.getpid()))
        os._exit(0)
    except BaseException:
        with suppress(BaseException):
            sender.send(("error", os.getpid()))
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        with suppress(BaseException):
            sender.close()


def _receive_probe_message(receiver: Any) -> tuple[str, int]:
    if not receiver.poll(_PROCESS_HANDSHAKE_SECONDS):
        raise _unsupported("lock_probe_timeout")
    message = receiver.recv()
    if (
        type(message) is not tuple
        or len(message) != 2
        or type(message[0]) is not str
        or type(message[1]) is not int
    ):
        raise _unsupported("capability_probe_failed")
    return (message[0], message[1])


def _wait_for_probe_child(
    child_pid: int,
    receiver: Any,
    *,
    timeout: float | None = None,
) -> _ProbeChildWaitOutcome:
    if timeout is None:
        timeout = _PROCESS_HANDSHAKE_SECONDS
    deadline = monotonic() + timeout
    while True:
        try:
            waited_pid, wait_status = os.waitpid(child_pid, os.WNOHANG)
        except InterruptedError:
            continue
        except ChildProcessError:
            return _ProbeChildWaitOutcome("not_child")
        except OSError:
            return _ProbeChildWaitOutcome("wait_error")
        if waited_pid == child_pid:
            return _ProbeChildWaitOutcome("reaped", wait_status)
        remaining = deadline - monotonic()
        if remaining <= 0:
            return _ProbeChildWaitOutcome("still_child_timeout")
        try:
            message_ready = receiver.poll(min(remaining, 0.05))
        except InterruptedError:
            continue
        except (EOFError, OSError):
            return _ProbeChildWaitOutcome("channel_error")
        if message_ready:
            with suppress(EOFError, OSError):
                receiver.recv()


def _blocking_reap_probe_child(child_pid: int) -> _ProbeChildWaitOutcome:
    while True:
        try:
            waited_pid, wait_status = os.waitpid(child_pid, 0)
        except InterruptedError:
            continue
        except ChildProcessError:
            return _ProbeChildWaitOutcome("not_child")
        except OSError:
            return _ProbeChildWaitOutcome("wait_error")
        if waited_pid != child_pid:
            return _ProbeChildWaitOutcome("wait_error")
        return _ProbeChildWaitOutcome("reaped", wait_status)


def _terminate_probe_child(child_pid: int, receiver: Any) -> _ProbeChildWaitOutcome:
    outcome = _wait_for_probe_child(child_pid, receiver, timeout=0.0)
    if outcome.state != "still_child_timeout":
        return outcome
    with suppress(OSError):
        os.kill(child_pid, signal.SIGTERM)
    outcome = _wait_for_probe_child(child_pid, receiver)
    if outcome.state in {"reaped", "not_child", "wait_error"}:
        return outcome
    outcome = _wait_for_probe_child(child_pid, receiver, timeout=0.0)
    if outcome.state != "still_child_timeout":
        return outcome
    with suppress(OSError):
        os.kill(child_pid, signal.SIGKILL)
    return _blocking_reap_probe_child(child_pid)


def probe_second_process_lock(directory_fd: int, name: str) -> LockProbeEvidence:
    """Prove contention, release, reacquisition, and process-death lock release."""

    _require_directory(directory_fd)
    checked_name = _validate_leaf_name(name)
    try:
        context = multiprocessing.get_context("fork")
    except ValueError:
        raise _unsupported("second_process_probe_unavailable") from None
    parent_descriptor = os.open(
        checked_name,
        _lock_open_flags(writable=True, create=False),
        dir_fd=directory_fd,
    )
    parent_descriptor_owned = True
    receiver: Any | None = None
    sender: Any | None = None
    receiver_owned = False
    sender_owned = False
    acquired = False
    child_pid: int | None = None
    child_reaped = False
    try:
        if not stat.S_ISREG(os.fstat(parent_descriptor).st_mode):
            raise OwnedStagingError("unsafe_lock_file")
        parent_posix = PosixOps()
        receiver, sender = context.Pipe(duplex=False)
        receiver_owned = True
        sender_owned = True
        opened = context.Event()
        attempt = context.Event()
        released = context.Event()
        parent_posix.acquire_lock(parent_descriptor, exclusive=True, blocking=True)
        acquired = True
        child_pid = os.fork()
        if child_pid == 0:
            with suppress(BaseException):
                receiver.close()
            try:
                _probe_child(
                    directory_fd,
                    checked_name,
                    parent_descriptor,
                    opened,
                    attempt,
                    released,
                    sender,
                )
            finally:
                os._exit(1)
        sender_owned = False
        sender.close()
        if not opened.wait(_PROCESS_HANDSHAKE_SECONDS):
            raise _unsupported("lock_probe_timeout")
        attempt.set()
        contention_message, reported_child_pid = _receive_probe_message(receiver)
        if contention_message != "contended" or reported_child_pid != child_pid:
            raise _unsupported("capability_probe_failed")
        parent_posix.release_lock(parent_descriptor)
        acquired = False
        released.set()
        reacquired_message, reacquired_pid = _receive_probe_message(receiver)
        if reacquired_message != "reacquired" or reacquired_pid != child_pid:
            raise _unsupported("capability_probe_failed")
        wait_outcome = _wait_for_probe_child(child_pid, receiver)
        if wait_outcome.state in {"reaped", "not_child"}:
            child_reaped = True
        if wait_outcome.state != "reaped" or wait_outcome.wait_status is None:
            raise _unsupported("capability_probe_failed")
        if os.waitstatus_to_exitcode(wait_outcome.wait_status) != 0:
            raise _unsupported("capability_probe_failed")
        parent_posix.acquire_lock(parent_descriptor, exclusive=True, blocking=False)
        acquired = True
        parent_posix.release_lock(parent_descriptor)
        acquired = False
        return LockProbeEvidence(
            parent_pid=os.getpid(),
            child_pid=child_pid,
            child_observed_contention=True,
            child_acquired_after_release=True,
            parent_reacquired_after_child_death=True,
        )
    finally:
        if acquired:
            with suppress(OSError):
                parent_posix.release_lock(parent_descriptor)
        if child_pid is not None and child_pid > 0 and not child_reaped:
            cleanup_outcome = _terminate_probe_child(child_pid, receiver)
            if cleanup_outcome.state in {"reaped", "not_child"}:
                child_reaped = True
            else:
                primary_error = sys.exc_info()[1]
                if primary_error is None:
                    raise _unsupported("capability_probe_failed")
                primary_error.add_note(_CHILD_CLEANUP_FAILURE_NOTE)
        if sender_owned:
            sender_owned = False
            with suppress(BaseException):
                assert sender is not None
                sender.close()
        if receiver_owned:
            receiver_owned = False
            with suppress(BaseException):
                assert receiver is not None
                receiver.close()
        if parent_descriptor_owned:
            parent_descriptor_owned = False
            with suppress(BaseException):
                os.close(parent_descriptor)


def _second_process_lock_probe(directory_fd: int, name: str) -> None:
    probe_second_process_lock(directory_fd, name)


def _probe_noreplace_and_durability(
    probe_fd: int,
    *,
    posix: FilesystemPosixOps,
    contention_probe: ContentionProbe,
) -> None:
    lock_fd = _create_probe_file(probe_fd, "advisory-lock", b"")
    os.close(lock_fd)
    contention_probe(probe_fd, "advisory-lock")

    sync_fd = _create_probe_file(probe_fd, "sync-file", b"sync")
    try:
        posix.fsync(sync_fd)
    finally:
        os.close(sync_fd)

    os.mkdir("rename-directory-success-source", 0o700, dir_fd=probe_fd)
    success_identity = _leaf_identity(
        os.stat(
            "rename-directory-success-source",
            dir_fd=probe_fd,
            follow_symlinks=False,
        )
    )
    posix.rename_noreplace(
        probe_fd,
        "rename-directory-success-source",
        probe_fd,
        "rename-directory-success-target",
    )
    try:
        os.stat(
            "rename-directory-success-source",
            dir_fd=probe_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        pass
    else:
        raise _unsupported("capability_probe_failed")
    _assert_leaf_unchanged(
        probe_fd,
        "rename-directory-success-target",
        success_identity,
    )

    source_fd = _create_probe_file(probe_fd, "rename-file-source", b"source")
    os.close(source_fd)
    target_fd = _create_probe_file(probe_fd, "rename-file-target", b"target")
    os.close(target_fd)
    source_identity = _leaf_identity(
        os.stat("rename-file-source", dir_fd=probe_fd, follow_symlinks=False)
    )
    target_identity = _leaf_identity(
        os.stat("rename-file-target", dir_fd=probe_fd, follow_symlinks=False)
    )
    try:
        posix.rename_noreplace(
            probe_fd,
            "rename-file-source",
            probe_fd,
            "rename-file-target",
        )
    except FileExistsError:
        pass
    else:
        raise _unsupported("capability_probe_failed")
    _assert_leaf_unchanged(probe_fd, "rename-file-source", source_identity)
    _assert_leaf_unchanged(probe_fd, "rename-file-target", target_identity)

    os.mkdir("rename-directory-source", 0o700, dir_fd=probe_fd)
    os.mkdir("rename-directory-target", 0o700, dir_fd=probe_fd)
    directory_source_identity = _leaf_identity(
        os.stat("rename-directory-source", dir_fd=probe_fd, follow_symlinks=False)
    )
    directory_target_identity = _leaf_identity(
        os.stat("rename-directory-target", dir_fd=probe_fd, follow_symlinks=False)
    )
    try:
        posix.rename_noreplace(
            probe_fd,
            "rename-directory-source",
            probe_fd,
            "rename-directory-target",
        )
    except FileExistsError:
        pass
    else:
        raise _unsupported("capability_probe_failed")
    _assert_leaf_unchanged(
        probe_fd,
        "rename-directory-source",
        directory_source_identity,
    )
    _assert_leaf_unchanged(
        probe_fd,
        "rename-directory-target",
        directory_target_identity,
    )

    hard_source_fd = _create_probe_file(probe_fd, "hard-link-source", b"link")
    os.close(hard_source_fd)
    hard_target_fd = _create_probe_file(probe_fd, "hard-link-target", b"target")
    os.close(hard_target_fd)
    posix.link_noreplace(probe_fd, "hard-link-source", probe_fd, "hard-link-copy")
    source_after_link = os.stat("hard-link-source", dir_fd=probe_fd, follow_symlinks=False)
    copy_after_link = os.stat("hard-link-copy", dir_fd=probe_fd, follow_symlinks=False)
    if (source_after_link.st_dev, source_after_link.st_ino) != (
        copy_after_link.st_dev,
        copy_after_link.st_ino,
    ):
        raise _unsupported("capability_probe_failed")
    hard_target_identity = _leaf_identity(
        os.stat("hard-link-target", dir_fd=probe_fd, follow_symlinks=False)
    )
    try:
        posix.link_noreplace(probe_fd, "hard-link-source", probe_fd, "hard-link-target")
    except FileExistsError:
        pass
    else:
        raise _unsupported("capability_probe_failed")
    _assert_leaf_unchanged(probe_fd, "hard-link-target", hard_target_identity)
    posix.fsync(probe_fd)


def run_filesystem_probes(
    results_root_fd: int,
    staging: OwnedStaging,
    *,
    posix: FilesystemPosixOps,
    contention_probe: ContentionProbe | None = None,
) -> FilesystemIdentity:
    """Run fresh, harmless mutation probes below one operation-owned staging path."""

    _validate_owned_directory(staging)
    root_identity = classify_filesystem(results_root_fd, posix=posix)
    try:
        staging_identity = classify_filesystem(staging.descriptor, posix=posix)
    except UnsupportedFilesystemError:
        raise _unsupported("different_mount") from None
    if staging_identity != root_identity:
        raise _unsupported("different_mount")

    probe = _create_owned_directory(staging.descriptor, _PROBE_DIRECTORY_NAME, mode=0o700)
    failure: BaseException | None = None
    try:
        try:
            probe_identity = classify_filesystem(probe.descriptor, posix=posix)
        except UnsupportedFilesystemError:
            raise _unsupported("different_mount") from None
        if probe_identity != root_identity:
            raise _unsupported("different_mount")
        selected_contention_probe = (
            _second_process_lock_probe if contention_probe is None else contention_probe
        )
        _probe_noreplace_and_durability(
            probe.descriptor,
            posix=posix,
            contention_probe=selected_contention_probe,
        )
    except BaseException as error:
        failure = error
    try:
        cleanup_owned_staging(probe, posix=posix)
    except BaseException as cleanup_error:
        if failure is None:
            failure = cleanup_error
    if failure is not None:
        if isinstance(failure, UnsupportedFilesystemError):
            raise failure
        raise _unsupported("capability_probe_failed") from None
    return root_identity


def publish_owned_staging(
    staging: OwnedStaging,
    destination_name: str,
    *,
    posix: FilesystemPosixOps,
) -> None:
    """Atomically publish owned staging without replacement, then sync the parent directory."""

    _validate_owned_directory(staging)
    checked_destination = _validate_leaf_name(destination_name)
    try:
        posix.rename_noreplace(
            staging.parent_directory_fd,
            staging.name,
            staging.parent_directory_fd,
            checked_destination,
        )
    except FileExistsError:
        collision = DestinationCollisionError()
        try:
            cleanup_owned_staging(staging, posix=posix)
        except BaseException:
            collision.add_note(_CLEANUP_FAILURE_NOTE)
        raise collision from None
    except (OSError, RuntimeError, ValueError):
        publication_error = OwnedStagingError("publication_failed")
        try:
            cleanup_owned_staging(staging, posix=posix)
        except BaseException:
            publication_error.add_note(_CLEANUP_FAILURE_NOTE)
        raise publication_error from None

    staging._state = "published"
    try:
        posix.fsync(staging.parent_directory_fd)
    except (OSError, RuntimeError, ValueError):
        raise PostPublishSyncError(checked_destination) from None


@contextmanager
def preparation_filesystem(
    results_root_fd: int,
    operation_id: UUID,
    *,
    posix: FilesystemPosixOps,
    contention_probe: ContentionProbe | None = None,
) -> Iterator[PreparationFilesystem]:
    """Establish and hold the complete preparation filesystem contract in the required order."""

    initial_identity = classify_filesystem(results_root_fd, posix=posix)
    durable_published = False
    try:
        with acquire_creator_lock(results_root_fd, posix=posix):
            current_identity = classify_filesystem(results_root_fd, posix=posix)
            if current_identity != initial_identity:
                raise _unsupported("filesystem_identity_changed")
            staging = create_owned_staging(results_root_fd, operation_id)
            try:
                probed_identity = run_filesystem_probes(
                    results_root_fd,
                    staging,
                    posix=posix,
                    contention_probe=contention_probe,
                )
                if probed_identity != current_identity:
                    raise _unsupported("filesystem_identity_changed")
                workspace = PreparationFilesystem(
                    filesystem_identity=current_identity,
                    staging=staging,
                    _posix=posix,
                )
                yield workspace
            except BaseException as primary_error:
                try:
                    if staging.state == "owned":
                        cleanup_owned_staging(staging, posix=posix)
                except BaseException:
                    primary_error.add_note(_CLEANUP_FAILURE_NOTE)
                try:
                    staging.close()
                except BaseException:
                    primary_error.add_note(_DESCRIPTOR_CLOSE_FAILURE_NOTE)
                raise
            else:
                if staging.state == "published":
                    with suppress(OSError):
                        staging.close()
                else:
                    try:
                        if staging.state == "owned":
                            cleanup_owned_staging(staging, posix=posix)
                    finally:
                        staging.close()
                durable_published = staging.state == "published"
    except (OSError, RuntimeError, ValueError):
        if not durable_published:
            raise
