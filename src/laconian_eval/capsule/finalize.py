"""Normalized, crash-safe publication of immutable generation-capsule seals."""

from __future__ import annotations

import errno
import os
import re
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NoReturn, TypeAlias, cast
from uuid import RFC_4122, UUID, uuid4

from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.bounded_io import BoundedIOError, open_directory_no_follow
from laconian_eval.capsule.canonical import canonical_timestamp
from laconian_eval.capsule.events import SealRequestedEventV1, make_event
from laconian_eval.capsule.filesystem import (
    FilesystemPosixOps,
    LockHandle,
    OwnedStagingError,
    UnsupportedFilesystemError,
    classify_filesystem,
    try_acquire_mutator_lock,
)
from laconian_eval.capsule.journal import JournalError, append_event
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.recovery import (
    RecoveryError,
    _apply_recovery_plan_v1,
    _bind_mutator_posix,
    _make_mutator_session_v1,
    _MutatorSessionV1,
    _plan_mutator_session_v1,
    _revalidate_mutator_session_v1,
    _run_mutator_filesystem_preflight,
)
from laconian_eval.capsule.seal_models import (
    SealModelError,
    capsule_sha256,
    derive_seal_v1,
    seal_bytes,
)
from laconian_eval.capsule.verify import (
    _check_finalization_namespace_descriptors,
    _check_lock_identity,
    _check_public_root_identity,
    _Failure,
    _Identity,
    _seal_transaction_candidate_available,
    _VerifiedFinalizationSnapshot,
    _verify_finalization_snapshot_descriptors,
    _verify_recoverable_capsule_descriptors,
)

FinalizationCode: TypeAlias = Literal[
    "invalid_argument",
    "target_callback_failed",
    "busy",
    "unsupported_filesystem",
    "incomplete_requires_flag",
    "integrity_error",
    "seal_mismatch",
    "destination_collision",
    "io_error",
    "post_publish_fsync_failed",
]
FinalState: TypeAlias = Literal["SEALED_COMPLETE", "SEALED_BLOCKED"]
CrashPoint: TypeAlias = Literal[
    "after_seal_requested_fsync",
    "after_temporary_exclusive_creation",
    "during_temporary_write",
    "after_temporary_file_fsync",
    "after_link_noreplace",
    "after_temporary_unlink",
    "during_capsule_directory_fsync",
]

_FINALIZATION_CODES = frozenset(
    {
        "invalid_argument",
        "target_callback_failed",
        "busy",
        "unsupported_filesystem",
        "incomplete_requires_flag",
        "integrity_error",
        "seal_mismatch",
        "destination_collision",
        "io_error",
        "post_publish_fsync_failed",
    }
)
_GENERIC_MESSAGE = "capsule finalization rejected"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TEMP_PREFIX = ".seal."
_SEAL_NAME = "seal.json"
_MAX_UUID_ATTEMPTS = 128


class FinalizationError(ContentFreeCapsuleError):
    """A stable content-free finalization failure."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code: FinalizationCode = cast(
            FinalizationCode,
            code if type(code) is str and code in _FINALIZATION_CODES else "invalid_argument",
        )
        super().__init__(_GENERIC_MESSAGE)


def _fail(code: FinalizationCode) -> NoReturn:
    raise FinalizationError(code)


@dataclass(frozen=True, slots=True)
class FinalizeResultV1:
    path: Path
    state: FinalState
    capsule_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, Path)
            or type(self.state) is not str
            or self.state not in {"SEALED_COMPLETE", "SEALED_BLOCKED"}
            or type(self.capsule_sha256) is not str
            or _SHA256.fullmatch(self.capsule_sha256) is None
        ):
            _fail("integrity_error")


def _default_now() -> datetime:
    return datetime.now(UTC)


def _no_crash(_point: CrashPoint) -> None:
    return None


def _link_noreplace(
    posix: FilesystemPosixOps,
    source_directory_fd: int,
    source_name: str,
    target_directory_fd: int,
    target_name: str,
) -> None:
    posix.link_noreplace(
        source_directory_fd,
        source_name,
        target_directory_fd,
        target_name,
    )


@dataclass(frozen=True, slots=True)
class _FinalizeSeams:
    new_uuid: Callable[[], UUID] = uuid4
    utc_now: Callable[[], datetime] = _default_now
    checkpoint: Callable[[CrashPoint], None] = _no_crash
    write: Callable[[int, bytes], int] = os.write
    link_noreplace: Callable[[FilesystemPosixOps, int, str, int, str], None] = _link_noreplace


@dataclass(slots=True)
class _OpenedArtifact:
    name: str
    descriptor: int
    identity: tuple[int, int, int, int, int, int]
    matches_expected: bool

    def close(self) -> None:
        descriptor = self.descriptor
        if descriptor < 0:
            return
        self.descriptor = -1
        os.close(descriptor)


@dataclass(slots=True)
class _PublicationState:
    published: bool = False


def _uuid4(value: object) -> UUID:
    if type(value) is not UUID or value.version != 4 or value.variant != RFC_4122:
        _fail("invalid_argument")
    return UUID(str(value))


def _timestamp(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _fail("invalid_argument")
    try:
        canonical_timestamp(value)
    except (TypeError, ValueError):
        _fail("invalid_argument")
    return datetime.fromisoformat(value.isoformat())


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _inventory_identity(identity: _Identity) -> tuple[int, int, int, int, int, int]:
    return (
        identity.device,
        identity.inode,
        identity.mode,
        identity.size,
        identity.mtime_ns,
        identity.ctime_ns,
    )


def _same_leaf(
    left: tuple[int, int, int, int, int, int],
    right: tuple[int, int, int, int, int, int],
) -> bool:
    return left[:3] == right[:3]


def _close_on_exec_flag() -> int:
    value = getattr(os, "O_CLOEXEC", 0)
    return value if type(value) is int else 0


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int:
        _fail("unsupported_filesystem")
    return value


def _read_flags() -> int:
    return (
        os.O_RDONLY
        | _required_open_flag("O_NOFOLLOW")
        | _required_open_flag("O_NONBLOCK")
        | _close_on_exec_flag()
    )


def _create_flags() -> int:
    return (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | _required_open_flag("O_NOFOLLOW")
        | _close_on_exec_flag()
    )


def _checkpoint(
    seams: _FinalizeSeams,
    point: CrashPoint,
    *,
    published: bool,
) -> None:
    try:
        seams.checkpoint(point)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        _fail("post_publish_fsync_failed" if published else "io_error")


def _stable_namespace(
    *,
    visible_path: Path,
    parent_fd: int,
    root_fd: int,
    lock: LockHandle,
    expected_parent: _Identity,
    expected_root_leaf: _Identity,
) -> None:
    _check_lock_identity(root_fd, lock.descriptor)
    _parent, root = _check_public_root_identity(
        visible_path,
        parent_fd,
        root_fd,
        expected_parent=expected_parent,
        recheck_visible_parent=True,
    )
    if (
        root.device,
        root.inode,
        root.mode,
    ) != (
        expected_root_leaf.device,
        expected_root_leaf.inode,
        expected_root_leaf.mode,
    ):
        raise _Failure("unstable_snapshot", None)


def _stable_finalization_namespace(
    *,
    visible_path: Path,
    parent_fd: int,
    root_fd: int,
    lock: LockHandle,
    snapshot: _VerifiedFinalizationSnapshot,
    seal: _OpenedArtifact | None,
    temporary: _OpenedArtifact | None,
) -> None:
    _stable_namespace(
        visible_path=visible_path,
        parent_fd=parent_fd,
        root_fd=root_fd,
        lock=lock,
        expected_parent=snapshot.parent_identity,
        expected_root_leaf=snapshot.root_identity,
    )
    _check_finalization_namespace_descriptors(
        root_fd,
        snapshot,
        seal_descriptor=None if seal is None else seal.descriptor,
        temporary_descriptor=None if temporary is None else temporary.descriptor,
    )
    _stable_namespace(
        visible_path=visible_path,
        parent_fd=parent_fd,
        root_fd=root_fd,
        lock=lock,
        expected_parent=snapshot.parent_identity,
        expected_root_leaf=snapshot.root_identity,
    )


def _close_failed_descriptor(descriptor: int) -> None:
    active = sys.exc_info()[1]
    try:
        os.close(descriptor)
    except BaseException as error:
        if not isinstance(error, Exception):
            if active is None or isinstance(active, Exception):
                raise
        elif active is None:
            _fail("io_error")


def _open_artifact(
    root_fd: int,
    name: str,
    expected_identity: _Identity,
    expected_bytes: bytes,
) -> _OpenedArtifact:
    descriptor = -1
    try:
        path_before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        descriptor = os.open(name, _read_flags(), dir_fd=root_fd)
        before_stat = os.fstat(descriptor)
        before = _identity(before_stat)
        if (
            not stat.S_ISREG(before_stat.st_mode)
            or before != _inventory_identity(expected_identity)
            or not _same_leaf(_identity(path_before), before)
        ):
            _fail("seal_mismatch")

        matches = before_stat.st_size == len(expected_bytes)
        offset = 0
        while matches and offset < len(expected_bytes):
            try:
                chunk = os.read(descriptor, min(64 * 1024, len(expected_bytes) - offset))
            except InterruptedError:
                continue
            if not chunk:
                _fail("seal_mismatch")
            if chunk != expected_bytes[offset : offset + len(chunk)]:
                matches = False
            offset += len(chunk)
        if matches:
            while True:
                try:
                    extra = os.read(descriptor, 1)
                    break
                except InterruptedError:
                    continue
            if extra:
                matches = False
        after = _identity(os.fstat(descriptor))
        path_after = _identity(os.stat(name, dir_fd=root_fd, follow_symlinks=False))
        if before != after or not _same_leaf(after, path_after):
            _fail("seal_mismatch")
        opened = _OpenedArtifact(name, descriptor, after, matches)
        return opened
    except FinalizationError:
        raise
    except OSError:
        _fail("seal_mismatch")
    finally:
        if descriptor >= 0 and sys.exc_info()[1] is not None:
            _close_failed_descriptor(descriptor)


def _refresh_opened(
    root_fd: int,
    opened: _OpenedArtifact,
    *,
    allow_metadata_change: bool = False,
) -> None:
    try:
        descriptor_identity = _identity(os.fstat(opened.descriptor))
        path_identity = _identity(os.stat(opened.name, dir_fd=root_fd, follow_symlinks=False))
    except OSError:
        _fail("seal_mismatch")
    if (
        not stat.S_ISREG(descriptor_identity[2])
        or not _same_leaf(descriptor_identity, path_identity)
        or descriptor_identity[3] != opened.identity[3]
        or (not allow_metadata_change and descriptor_identity != opened.identity)
    ):
        _fail("seal_mismatch")
    opened.identity = descriptor_identity


def _verify_opened_exact(
    root_fd: int,
    opened: _OpenedArtifact,
    expected_bytes: bytes,
    *,
    allow_metadata_change: bool = False,
    published: bool = False,
) -> None:
    probe = -1
    try:
        retained_before = _identity(os.fstat(opened.descriptor))
        path_before = _identity(os.stat(opened.name, dir_fd=root_fd, follow_symlinks=False))
        if (
            not stat.S_ISREG(retained_before[2])
            or not _same_leaf(retained_before, path_before)
            or retained_before[3] != len(expected_bytes)
            or (not allow_metadata_change and retained_before != opened.identity)
        ):
            _fail("seal_mismatch")
        probe = os.open(opened.name, _read_flags(), dir_fd=root_fd)
        probe_before = _identity(os.fstat(probe))
        if probe_before != retained_before:
            _fail("seal_mismatch")
        offset = 0
        while offset < len(expected_bytes):
            try:
                chunk = os.read(probe, min(64 * 1024, len(expected_bytes) - offset))
            except InterruptedError:
                continue
            if not chunk or chunk != expected_bytes[offset : offset + len(chunk)]:
                _fail("seal_mismatch")
            offset += len(chunk)
        while True:
            try:
                extra = os.read(probe, 1)
                break
            except InterruptedError:
                continue
        if extra:
            _fail("seal_mismatch")
        probe_after = _identity(os.fstat(probe))
        retained_after = _identity(os.fstat(opened.descriptor))
        path_after = _identity(os.stat(opened.name, dir_fd=root_fd, follow_symlinks=False))
        if (
            probe_before != probe_after
            or retained_before != retained_after
            or not _same_leaf(retained_after, path_after)
        ):
            _fail("seal_mismatch")
        opened.identity = retained_after
        opened.matches_expected = True
    except FinalizationError:
        raise
    except OSError:
        _fail("seal_mismatch")
    finally:
        if probe >= 0:
            active = sys.exc_info()[1]
            try:
                os.close(probe)
            except BaseException as error:
                if not isinstance(error, Exception):
                    if active is None or isinstance(active, Exception):
                        raise
                elif active is None:
                    _fail("post_publish_fsync_failed" if published else "io_error")


def _unlink_opened(
    root_fd: int,
    opened: _OpenedArtifact,
    *,
    published: bool,
    require_single_link: bool = False,
) -> None:
    _refresh_opened(root_fd, opened)
    if require_single_link:
        try:
            if os.fstat(opened.descriptor).st_nlink != 1:
                _fail("seal_mismatch")
        except OSError:
            _fail("seal_mismatch")
    try:
        os.unlink(opened.name, dir_fd=root_fd)
    except OSError:
        _fail("post_publish_fsync_failed" if published else "io_error")
    try:
        os.stat(opened.name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        _fail("post_publish_fsync_failed" if published else "io_error")
    _fail("seal_mismatch")


def _write_all(
    descriptor: int,
    data: bytes,
    seams: _FinalizeSeams,
) -> None:
    offset = 0
    first = True
    while offset < len(data):
        remaining = len(data) - offset
        request_length = min(64 * 1024, remaining)
        if first and remaining > 1:
            request_length = min(request_length, max(1, remaining // 2))
        try:
            written = seams.write(descriptor, data[offset : offset + request_length])
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            _fail("io_error")
        if type(written) is not int or not 0 < written <= request_length:
            _fail("io_error")
        offset += written
        if first:
            first = False
            _checkpoint(seams, "during_temporary_write", published=False)


def _create_temporary(
    root_fd: int,
    temporary_name: str,
    data: bytes,
    *,
    posix: FilesystemPosixOps,
    seams: _FinalizeSeams,
) -> _OpenedArtifact:
    descriptor = -1
    try:
        descriptor = os.open(temporary_name, _create_flags(), 0o600, dir_fd=root_fd)
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        path_metadata = os.stat(temporary_name, dir_fd=root_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not _same_leaf(_identity(metadata), _identity(path_metadata))
            or metadata.st_size != 0
        ):
            _fail("seal_mismatch")
        _checkpoint(seams, "after_temporary_exclusive_creation", published=False)
        _write_all(descriptor, data, seams)
        try:
            posix.fsync(descriptor)
        except (OSError, RuntimeError, ValueError):
            _fail("io_error")
        metadata = os.fstat(descriptor)
        path_metadata = os.stat(temporary_name, dir_fd=root_fd, follow_symlinks=False)
        if not _same_leaf(_identity(metadata), _identity(path_metadata)) or metadata.st_size != len(
            data
        ):
            _fail("seal_mismatch")
        _checkpoint(seams, "after_temporary_file_fsync", published=False)
        opened = _OpenedArtifact(
            temporary_name,
            descriptor,
            _identity(metadata),
            True,
        )
        return opened
    except FileExistsError:
        _fail("destination_collision")
    except FinalizationError:
        raise
    except OSError:
        _fail("io_error")
    finally:
        if descriptor >= 0 and sys.exc_info()[1] is not None:
            _close_failed_descriptor(descriptor)


def _sync_directory(
    root_fd: int,
    *,
    posix: FilesystemPosixOps,
    seams: _FinalizeSeams,
    published: bool,
) -> None:
    _checkpoint(seams, "during_capsule_directory_fsync", published=published)
    try:
        posix.fsync(root_fd)
    except (OSError, RuntimeError, ValueError):
        _fail("post_publish_fsync_failed" if published else "io_error")


def _link_temporary(
    root_fd: int,
    opened: _OpenedArtifact,
    data: bytes,
    *,
    posix: FilesystemPosixOps,
    seams: _FinalizeSeams,
    fsync_existing: bool,
    publication: _PublicationState,
) -> _OpenedArtifact:
    _verify_opened_exact(root_fd, opened, data)
    if fsync_existing:
        try:
            posix.fsync(opened.descriptor)
        except (OSError, RuntimeError, ValueError):
            _fail("io_error")
        _verify_opened_exact(root_fd, opened, data)
        _checkpoint(seams, "after_temporary_file_fsync", published=False)
        _verify_opened_exact(root_fd, opened, data)
    try:
        seams.link_noreplace(posix, root_fd, opened.name, root_fd, _SEAL_NAME)
    except FileExistsError:
        _fail("destination_collision")
    except (OSError, RuntimeError, ValueError):
        _fail("io_error")
    publication.published = True
    seal_descriptor = -1
    seal: _OpenedArtifact | None = None
    try:
        try:
            descriptor_identity = _identity(os.fstat(opened.descriptor))
            temporary_identity = _identity(
                os.stat(opened.name, dir_fd=root_fd, follow_symlinks=False)
            )
            seal_identity = _identity(os.stat(_SEAL_NAME, dir_fd=root_fd, follow_symlinks=False))
            seal_descriptor = os.open(_SEAL_NAME, _read_flags(), dir_fd=root_fd)
            retained_seal_identity = _identity(os.fstat(seal_descriptor))
        except OSError as error:
            if error.errno in {errno.ENOENT, errno.ELOOP, errno.ENOTDIR}:
                _fail("seal_mismatch")
            _fail("post_publish_fsync_failed")
        if (
            not stat.S_ISREG(descriptor_identity[2])
            or not _same_leaf(descriptor_identity, temporary_identity)
            or not _same_leaf(descriptor_identity, seal_identity)
            or not _same_leaf(descriptor_identity, retained_seal_identity)
            or descriptor_identity[3] != opened.identity[3]
        ):
            _fail("seal_mismatch")
        opened.identity = descriptor_identity
        seal = _OpenedArtifact(_SEAL_NAME, seal_descriptor, retained_seal_identity, True)
        seal_descriptor = -1
        _verify_opened_exact(
            root_fd,
            opened,
            data,
            allow_metadata_change=True,
            published=True,
        )
        _verify_opened_exact(root_fd, seal, data, published=True)
        _checkpoint(seams, "after_link_noreplace", published=True)
        _verify_opened_exact(root_fd, opened, data, published=True)
        _verify_opened_exact(root_fd, seal, data, published=True)
        retained = seal
        return retained
    finally:
        active = sys.exc_info()[1]
        active_error = active is not None
        active_fatal = active_error and not isinstance(active, Exception)
        cleanup_fatal: BaseException | None = None
        cleanup_failed = False
        if seal is not None and active_error:
            if seal_descriptor == seal.descriptor:
                seal_descriptor = -1
            try:
                seal.close()
            except BaseException as error:
                if isinstance(error, Exception):
                    cleanup_failed = not active_error
                elif not active_fatal:
                    cleanup_fatal = error
        if seal_descriptor >= 0:
            try:
                os.close(seal_descriptor)
            except BaseException as error:
                if isinstance(error, Exception):
                    cleanup_failed = cleanup_failed or not active_error
                elif not active_fatal and cleanup_fatal is None:
                    cleanup_fatal = error
        if cleanup_fatal is not None:
            raise cleanup_fatal
        if not active_error and cleanup_failed:
            _fail("post_publish_fsync_failed")


def _publish_or_reconcile(
    *,
    visible_path: Path,
    root_fd: int,
    parent_fd: int,
    lock: LockHandle,
    snapshot: _VerifiedFinalizationSnapshot,
    data: bytes,
    posix: FilesystemPosixOps,
    seams: _FinalizeSeams,
    publication: _PublicationState,
) -> None:
    request = snapshot.context.history.seal_requested
    if request is None:  # pragma: no cover - guarded by the verifier boundary
        _fail("integrity_error")
    temporary_name = f".seal.{request.payload.seal_transaction_id}.tmp"
    seal_identity = snapshot.inventory.files.get(_SEAL_NAME)
    temporary_identity = snapshot.inventory.files.get(temporary_name)
    seal: _OpenedArtifact | None = None
    temporary: _OpenedArtifact | None = None
    try:
        if seal_identity is not None:
            seal = _open_artifact(root_fd, _SEAL_NAME, seal_identity, data)
            if not seal.matches_expected:
                _fail("seal_mismatch")
            publication.published = True
            if temporary_identity is not None:
                temporary = _open_artifact(
                    root_fd,
                    temporary_name,
                    temporary_identity,
                    data,
                )
                if not temporary.matches_expected:
                    _fail("seal_mismatch")
                _verify_opened_exact(root_fd, seal, data, published=True)
                _verify_opened_exact(root_fd, temporary, data, published=True)
                _stable_finalization_namespace(
                    visible_path=visible_path,
                    parent_fd=parent_fd,
                    root_fd=root_fd,
                    lock=lock,
                    snapshot=snapshot,
                    seal=seal,
                    temporary=temporary,
                )
                _unlink_opened(root_fd, temporary, published=True)
                _verify_opened_exact(
                    root_fd,
                    seal,
                    data,
                    allow_metadata_change=True,
                    published=True,
                )
                _checkpoint(seams, "after_temporary_unlink", published=True)
                _verify_opened_exact(root_fd, seal, data, published=True)
                _stable_finalization_namespace(
                    visible_path=visible_path,
                    parent_fd=parent_fd,
                    root_fd=root_fd,
                    lock=lock,
                    snapshot=snapshot,
                    seal=seal,
                    temporary=None,
                )
            _sync_directory(root_fd, posix=posix, seams=seams, published=True)
            _verify_opened_exact(root_fd, seal, data, published=True)
            _stable_finalization_namespace(
                visible_path=visible_path,
                parent_fd=parent_fd,
                root_fd=root_fd,
                lock=lock,
                snapshot=snapshot,
                seal=seal,
                temporary=None,
            )
            return

        if temporary_identity is not None:
            temporary = _open_artifact(
                root_fd,
                temporary_name,
                temporary_identity,
                data,
            )
            _stable_finalization_namespace(
                visible_path=visible_path,
                parent_fd=parent_fd,
                root_fd=root_fd,
                lock=lock,
                snapshot=snapshot,
                seal=None,
                temporary=temporary,
            )
            if not temporary.matches_expected:
                _unlink_opened(
                    root_fd,
                    temporary,
                    published=False,
                    require_single_link=True,
                )
                _sync_directory(root_fd, posix=posix, seams=seams, published=False)
                temporary.close()
                temporary = None
                _stable_finalization_namespace(
                    visible_path=visible_path,
                    parent_fd=parent_fd,
                    root_fd=root_fd,
                    lock=lock,
                    snapshot=snapshot,
                    seal=None,
                    temporary=None,
                )

        if temporary is None:
            temporary = _create_temporary(
                root_fd,
                temporary_name,
                data,
                posix=posix,
                seams=seams,
            )
            _stable_finalization_namespace(
                visible_path=visible_path,
                parent_fd=parent_fd,
                root_fd=root_fd,
                lock=lock,
                snapshot=snapshot,
                seal=None,
                temporary=temporary,
            )
            fsync_existing = False
        else:
            fsync_existing = True
        _verify_opened_exact(root_fd, temporary, data)
        _stable_finalization_namespace(
            visible_path=visible_path,
            parent_fd=parent_fd,
            root_fd=root_fd,
            lock=lock,
            snapshot=snapshot,
            seal=None,
            temporary=temporary,
        )
        seal = _link_temporary(
            root_fd,
            temporary,
            data,
            posix=posix,
            seams=seams,
            fsync_existing=fsync_existing,
            publication=publication,
        )
        _stable_finalization_namespace(
            visible_path=visible_path,
            parent_fd=parent_fd,
            root_fd=root_fd,
            lock=lock,
            snapshot=snapshot,
            seal=seal,
            temporary=temporary,
        )
        _unlink_opened(root_fd, temporary, published=True)
        _verify_opened_exact(
            root_fd,
            seal,
            data,
            allow_metadata_change=True,
            published=True,
        )
        _checkpoint(seams, "after_temporary_unlink", published=True)
        _verify_opened_exact(root_fd, seal, data, published=True)
        _stable_finalization_namespace(
            visible_path=visible_path,
            parent_fd=parent_fd,
            root_fd=root_fd,
            lock=lock,
            snapshot=snapshot,
            seal=seal,
            temporary=None,
        )
        _sync_directory(root_fd, posix=posix, seams=seams, published=True)
        _verify_opened_exact(root_fd, seal, data, published=True)
        _stable_finalization_namespace(
            visible_path=visible_path,
            parent_fd=parent_fd,
            root_fd=root_fd,
            lock=lock,
            snapshot=snapshot,
            seal=seal,
            temporary=None,
        )
    finally:
        active = sys.exc_info()[1]
        active_error = active is not None
        active_fatal = active_error and not isinstance(active, Exception)
        cleanup_fatal: BaseException | None = None
        cleanup_failed = False
        for opened in (temporary, seal):
            if opened is None or opened.descriptor < 0:
                continue
            try:
                opened.close()
            except BaseException as error:
                if isinstance(error, Exception):
                    cleanup_failed = cleanup_failed or not active_error
                elif not active_fatal and cleanup_fatal is None:
                    cleanup_fatal = error
        if cleanup_fatal is not None:
            raise cleanup_fatal
        if not active_error and cleanup_failed:
            _fail("post_publish_fsync_failed" if publication.published else "io_error")


def _new_seal_transaction(
    root_fd: int,
    *,
    operation_id: UUID,
    seams: _FinalizeSeams,
) -> UUID:
    for _attempt in range(_MAX_UUID_ATTEMPTS):
        candidate = _uuid4(seams.new_uuid())
        if _seal_transaction_candidate_available(root_fd, candidate, operation_id):
            return candidate
    _fail("invalid_argument")


def _map_failure(error: BaseException) -> FinalizationError:
    if isinstance(error, FinalizationError):
        return error
    if isinstance(error, UnsupportedFilesystemError):
        return FinalizationError("unsupported_filesystem")
    if isinstance(error, _Failure):
        if error.code == "io_error":
            return FinalizationError("io_error")
        if error.path == _SEAL_NAME or (
            type(error.path) is str and error.path.startswith(_TEMP_PREFIX)
        ):
            return FinalizationError("seal_mismatch")
        return FinalizationError("integrity_error")
    if isinstance(error, SealModelError):
        return FinalizationError("seal_mismatch")
    if isinstance(error, RecoveryError):
        return FinalizationError("io_error" if error.code == "io_error" else "integrity_error")
    if isinstance(error, JournalError):
        return FinalizationError("io_error" if error.code == "io_error" else "integrity_error")
    if isinstance(error, BoundedIOError):
        return FinalizationError("io_error" if error.code == "io_error" else "integrity_error")
    if isinstance(error, OwnedStagingError):
        return FinalizationError("io_error" if error.code == "io_error" else "integrity_error")
    if isinstance(error, OSError):
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            return FinalizationError("integrity_error")
        return FinalizationError("io_error")
    return FinalizationError("integrity_error")


def _announce_target(
    visible_path: Path,
    callback: Callable[[Path], None] | None,
) -> None:
    if callback is None:
        return
    try:
        callback(visible_path)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        _fail("target_callback_failed")


def _finalize_locked(
    *,
    visible_path: Path,
    root_fd: int,
    parent_fd: int,
    lock: LockHandle,
    operation_id: UUID,
    operation_time: datetime,
    seal_incomplete: bool,
    filesystem_class: str,
    seams: _FinalizeSeams,
    on_target_known: Callable[[Path], None] | None,
    publication: _PublicationState,
) -> FinalizeResultV1:
    session: _MutatorSessionV1 | None = None
    try:
        _bind_mutator_posix(root_fd, lock)
        _run_mutator_filesystem_preflight(
            root_fd,
            parent_fd=parent_fd,
            destination_name=visible_path.name,
            operation_id=operation_id,
            lock_handle=lock,
        )
        initial = _verify_recoverable_capsule_descriptors(
            root_fd,
            parent_fd=parent_fd,
            destination_name=visible_path.name,
            reserved_operation_id=operation_id,
            allow_finalization_artifacts=True,
        )
        if initial.context.environment.runtime.filesystem_class != filesystem_class:
            _fail("unsupported_filesystem")

        request = initial.context.history.seal_requested
        snapshot: _VerifiedFinalizationSnapshot
        if request is not None:
            snapshot = _verify_finalization_snapshot_descriptors(
                root_fd,
                parent_fd=parent_fd,
                destination_name=visible_path.name,
            )
            if snapshot.context.history.seal_requested != request:
                _fail("integrity_error")
            _check_lock_identity(root_fd, lock.descriptor)
            _announce_target(visible_path, on_target_known)
        else:
            session = _make_mutator_session_v1(
                root_fd,
                parent_fd=parent_fd,
                destination_name=visible_path.name,
                operation_id=operation_id,
                occurred_at=operation_time,
                lock_handle=lock,
            )
            if session.history_context.environment.runtime.filesystem_class != filesystem_class:
                _fail("unsupported_filesystem")
            _announce_target(visible_path, on_target_known)
            recovery_plan = _plan_mutator_session_v1(session)
            _apply_recovery_plan_v1(session, recovery_plan)
            normalized = _revalidate_mutator_session_v1(
                session,
                tail_policy="reject",
                reserved_operation_id=None,
            )
            history = normalized.history
            if history.seal_requested is not None:
                _fail("integrity_error")
            incomplete = bool(history.missing_plan_item_ids)
            if incomplete and not seal_incomplete:
                _fail("incomplete_requires_flag")
            transaction_id = _new_seal_transaction(
                root_fd,
                operation_id=operation_id,
                seams=seams,
            )
            event = make_event(
                sequence=normalized.events.row_count,
                run_id=session.history_context.capsule.run_id,
                occurred_at=operation_time,
                kind="seal_requested",
                operation_id=operation_id,
                execution_session_id=None,
                payload={
                    "seal_transaction_id": transaction_id,
                    "expected_generation_status": "incomplete" if incomplete else "complete",
                    "prior_event_sequence": normalized.events.row_count - 1,
                },
            )
            if type(event) is not SealRequestedEventV1:
                _fail("integrity_error")
            append_event(session.transaction, event)
            _checkpoint(seams, "after_seal_requested_fsync", published=False)
            normalized = _revalidate_mutator_session_v1(
                session,
                tail_policy="reject",
                reserved_operation_id=None,
            )
            request = normalized.history.seal_requested
            if request != event:
                _fail("integrity_error")
            snapshot = _verify_finalization_snapshot_descriptors(
                root_fd,
                parent_fd=parent_fd,
                destination_name=visible_path.name,
            )
            if snapshot.context.history.seal_requested != request:
                _fail("integrity_error")

        _check_lock_identity(root_fd, lock.descriptor)
        seal = derive_seal_v1(
            capsule=snapshot.context.capsule,
            manifest=snapshot.context.manifest,
            environment=snapshot.context.environment,
            history=snapshot.context.history,
            lifecycle=snapshot.context.lifecycle,
            seal_requested=request,
            files=snapshot.files,
        )
        data = seal_bytes(seal)
        _check_public_root_identity(
            visible_path,
            parent_fd,
            root_fd,
            expected_parent=snapshot.parent_identity,
            expected_root=snapshot.root_identity,
            recheck_visible_parent=True,
        )
        _check_lock_identity(root_fd, lock.descriptor)
        _publish_or_reconcile(
            visible_path=visible_path,
            root_fd=root_fd,
            parent_fd=parent_fd,
            lock=lock,
            snapshot=snapshot,
            data=data,
            posix=lock._posix,
            seams=seams,
            publication=publication,
        )
        state: FinalState = (
            "SEALED_COMPLETE" if seal.generation_status == "complete" else "SEALED_BLOCKED"
        )
        return FinalizeResultV1(visible_path, state, capsule_sha256(seal))
    finally:
        if session is not None:
            active = sys.exc_info()[1]
            active_error = active is not None
            active_fatal = active_error and not isinstance(active, Exception)
            try:
                session.transaction.close()
            except BaseException as error:
                if not isinstance(error, Exception):
                    if not active_fatal:
                        raise
                elif not active_error:
                    _fail("post_publish_fsync_failed" if publication.published else "io_error")


def _finalize_capsule(
    path: Path,
    *,
    seal_incomplete: bool = False,
    on_target_known: Callable[[Path], None] | None = None,
    seams: _FinalizeSeams | None = None,
) -> FinalizeResultV1:
    """Private orchestration boundary exposing deterministic test seams and target announcement."""

    selected_seams = _FinalizeSeams() if seams is None else seams
    if (
        type(seal_incomplete) is not bool
        or type(selected_seams) is not _FinalizeSeams
        or not callable(selected_seams.new_uuid)
        or not callable(selected_seams.utc_now)
        or not callable(selected_seams.checkpoint)
        or not callable(selected_seams.write)
        or not callable(selected_seams.link_noreplace)
        or (on_target_known is not None and not callable(on_target_known))
    ):
        _fail("invalid_argument")
    try:
        raw_path = os.fspath(path)
        if type(raw_path) is not str or not raw_path:
            _fail("invalid_argument")
        visible_path = Path(os.path.abspath(raw_path))
        if not visible_path.name:
            _fail("invalid_argument")
        operation_id = _uuid4(selected_seams.new_uuid())
        operation_time = _timestamp(selected_seams.utc_now())
    except FinalizationError:
        raise
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        _fail("invalid_argument")

    root_fd: int | None = None
    parent_fd: int | None = None
    lock: LockHandle | None = None
    result: FinalizeResultV1 | None = None
    failure: FinalizationError | None = None
    fatal: BaseException | None = None
    publication = _PublicationState()
    try:
        root_fd = open_directory_no_follow(visible_path)
        parent_fd = open_directory_no_follow(visible_path.parent)
        _check_public_root_identity(visible_path, parent_fd, root_fd)
        initial_posix = cast(FilesystemPosixOps, PosixOps())
        filesystem_identity = classify_filesystem(root_fd, posix=initial_posix)
        lock = try_acquire_mutator_lock(root_fd, posix=initial_posix)
        if lock is None:
            _fail("busy")
        _check_lock_identity(root_fd, lock.descriptor)
        result = _finalize_locked(
            visible_path=visible_path,
            root_fd=root_fd,
            parent_fd=parent_fd,
            lock=lock,
            operation_id=operation_id,
            operation_time=operation_time,
            seal_incomplete=seal_incomplete,
            filesystem_class=filesystem_identity.filesystem_class,
            seams=selected_seams,
            on_target_known=on_target_known,
            publication=publication,
        )
    except BaseException as error:
        if isinstance(error, Exception):
            failure = _map_failure(error)
        else:
            fatal = error
    finally:
        cleanup_failed = False
        cleanup_fatal: BaseException | None = None
        if lock is not None:
            try:
                lock.close()
            except BaseException as error:
                if isinstance(error, Exception):
                    cleanup_failed = cleanup_failed or (fatal is None and failure is None)
                elif fatal is None:
                    cleanup_fatal = error
        for descriptor in (root_fd, parent_fd):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except BaseException as error:
                if isinstance(error, Exception):
                    cleanup_failed = cleanup_failed or (fatal is None and failure is None)
                elif fatal is None and cleanup_fatal is None:
                    cleanup_fatal = error
        if fatal is None and cleanup_fatal is not None:
            fatal = cleanup_fatal
        elif fatal is None and failure is None and cleanup_failed:
            failure = FinalizationError(
                "post_publish_fsync_failed" if publication.published else "io_error"
            )
    if fatal is not None:
        raise fatal
    if failure is not None:
        raise failure
    if result is None:  # pragma: no cover - defensive totality
        _fail("integrity_error")
    return result


def finalize_capsule(path: Path, *, seal_incomplete: bool = False) -> FinalizeResultV1:
    """Normalize recoverable history and atomically publish the deterministic seal."""

    return _finalize_capsule(path, seal_incomplete=seal_incomplete)


__all__ = ["FinalizationError", "FinalizeResultV1", "finalize_capsule"]
