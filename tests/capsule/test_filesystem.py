from __future__ import annotations

import ast
import errno
import os
import signal
import stat
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import laconian_eval.capsule.filesystem as filesystem
from laconian_eval.capsule.filesystem import (
    BTRFS_SUPER_MAGIC,
    CREATOR_LOCK_NAME,
    EXT_SUPER_MAGIC,
    MNT_LOCAL,
    PERSISTENT_LOCK_NAME,
    XFS_SUPER_MAGIC,
    ZFS_SUPER_MAGIC,
    DestinationCollisionError,
    FilesystemIdentity,
    LockProbeEvidence,
    MountInfoEntry,
    OwnedStagingError,
    PostPublishSyncError,
    PreparationFilesystem,
    UnsupportedFilesystemError,
    acquire_creator_lock,
    classify_filesystem,
    cleanup_owned_staging,
    create_owned_staging,
    parse_linux_mountinfo,
    preparation_filesystem,
    probe_second_process_lock,
    publish_owned_staging,
    run_filesystem_probes,
    try_acquire_mutator_lock,
    try_acquire_shared_lock,
)
from laconian_eval.capsule.posix import (
    DEFAULT_MOUNTINFO_BYTE_LIMIT,
    FileSystemStat,
    MountIdentity,
    PosixOps,
)


class FakePosixOps:
    def __init__(
        self,
        *,
        platform: str,
        filesystem_stat: FileSystemStat,
        mount_identity: MountIdentity | None = None,
        mountinfo: bytes = b"",
    ) -> None:
        self.platform = platform
        self.filesystem_stat = filesystem_stat
        self.mount_identity = mount_identity
        self.mountinfo = mountinfo
        self.calls: list[tuple[Any, ...]] = []
        self.lock_error: OSError | None = None
        self.fsync_error_for: set[int] = set()

    def fstatfs(self, descriptor: int) -> FileSystemStat:
        self.calls.append(("fstatfs", descriptor))
        return self.filesystem_stat

    def statx_mount_identity(self, descriptor: int) -> MountIdentity:
        self.calls.append(("statx_mount_identity", descriptor))
        assert self.mount_identity is not None
        return self.mount_identity

    def read_mountinfo(self, byte_limit: int = DEFAULT_MOUNTINFO_BYTE_LIMIT) -> bytes:
        self.calls.append(("read_mountinfo", byte_limit))
        return self.mountinfo

    def rename_noreplace(
        self,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        self.calls.append(
            (
                "rename_noreplace",
                source_directory_fd,
                source_name,
                target_directory_fd,
                target_name,
            )
        )
        try:
            os.stat(target_name, dir_fd=target_directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            os.rename(
                source_name,
                target_name,
                src_dir_fd=source_directory_fd,
                dst_dir_fd=target_directory_fd,
            )
            return
        raise FileExistsError(errno.EEXIST, "private destination")

    def link_noreplace(
        self,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        self.calls.append(
            (
                "link_noreplace",
                source_directory_fd,
                source_name,
                target_directory_fd,
                target_name,
            )
        )
        os.link(
            source_name,
            target_name,
            src_dir_fd=source_directory_fd,
            dst_dir_fd=target_directory_fd,
            follow_symlinks=False,
        )

    def acquire_lock(self, descriptor: int, *, exclusive: bool, blocking: bool) -> None:
        self.calls.append(("acquire_lock", descriptor, exclusive, blocking))
        if self.lock_error is not None:
            raise self.lock_error

    def release_lock(self, descriptor: int) -> None:
        self.calls.append(("release_lock", descriptor))

    def fsync(self, descriptor: int) -> None:
        mode = os.fstat(descriptor).st_mode
        descriptor_type = "file" if stat.S_ISREG(mode) else "directory"
        self.calls.append(("fsync", descriptor, descriptor_type))
        if descriptor in self.fsync_error_for:
            raise OSError(errno.EIO, "private fsync failure")


def _directory_fd(path: Path) -> int:
    return os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))


def _device_parts(descriptor: int) -> tuple[int, int]:
    device = os.fstat(descriptor).st_dev
    return os.major(device), os.minor(device)


def _mountinfo_line(
    *,
    mount_id: int,
    major: int,
    minor: int,
    filesystem_type: str,
    mount_point: bytes = b"/work",
) -> bytes:
    return (
        str(mount_id).encode("ascii")
        + b" 1 "
        + str(major).encode("ascii")
        + b":"
        + str(minor).encode("ascii")
        + b" / "
        + mount_point
        + b" rw,nosuid shared:7 - "
        + filesystem_type.encode("ascii")
        + b" /dev/source rw\n"
    )


def _linux_fake(
    descriptor: int,
    *,
    magic: int = EXT_SUPER_MAGIC,
    filesystem_type: str = "ext4",
    mount_id: int = 42,
    mountinfo: bytes | None = None,
) -> FakePosixOps:
    major, minor = _device_parts(descriptor)
    return FakePosixOps(
        platform="linux",
        filesystem_stat=FileSystemStat(
            platform="linux",
            type_magic=magic,
            type_name=None,
            flags=0,
        ),
        mount_identity=MountIdentity(
            mount_id=mount_id,
            device_major=major,
            device_minor=minor,
        ),
        mountinfo=(
            _mountinfo_line(
                mount_id=mount_id,
                major=major,
                minor=minor,
                filesystem_type=filesystem_type,
            )
            if mountinfo is None
            else mountinfo
        ),
    )


def _darwin_fake(*, type_name: str = "apfs", flags: int = MNT_LOCAL) -> FakePosixOps:
    return FakePosixOps(
        platform="darwin",
        filesystem_stat=FileSystemStat(
            platform="darwin",
            type_magic=None,
            type_name=type_name,
            flags=flags,
        ),
    )


def test_parse_mountinfo_accepts_exact_kernel_frame_and_escaped_mount_point() -> None:
    raw = _mountinfo_line(
        mount_id=42,
        major=8,
        minor=1,
        filesystem_type="ext4",
        mount_point=b"/work\\040tree",
    )

    assert parse_linux_mountinfo(raw) == (
        MountInfoEntry(
            mount_id=42,
            device_major=8,
            device_minor=1,
            filesystem_type="ext4",
        ),
    )


def test_parse_mountinfo_accepts_exact_byte_limit_and_rejects_limit_plus_one() -> None:
    raw = _mountinfo_line(
        mount_id=42,
        major=8,
        minor=1,
        filesystem_type="ext4",
    )

    assert parse_linux_mountinfo(raw, byte_limit=len(raw))[0].mount_id == 42
    with pytest.raises(UnsupportedFilesystemError) as caught:
        parse_linux_mountinfo(raw + b"x", byte_limit=len(raw))
    assert caught.value.code == "unsupported_filesystem"
    assert caught.value.reason == "invalid_mountinfo"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"42 1 8:1 / / rw - ext4 /dev/source rw",
        b"42 1 8:1 / / rw ext4 /dev/source rw\n",
        b"42 1 8:1 / / rw - - ext4 /dev/source rw\n",
        b"0 1 8:1 / / rw - ext4 /dev/source rw\n",
        b"42 1 bad / / rw - ext4 /dev/source rw\n",
        b"42 1 8:1 / /bad\\041escape rw - ext4 /dev/source rw\n",
        b"42 1 8:1 / / rw - ext\xff /dev/source rw\n",
        b"42 1 4294967296:1 / / rw - ext4 /dev/source rw\n",
    ],
)
def test_parse_mountinfo_rejects_malformed_or_ambiguous_frames(raw: bytes) -> None:
    with pytest.raises(UnsupportedFilesystemError) as caught:
        parse_linux_mountinfo(raw)
    assert caught.value.code == "unsupported_filesystem"
    assert caught.value.reason == "invalid_mountinfo"
    assert str(caught.value) == "filesystem contract is unsupported"


@pytest.mark.parametrize(
    ("magic", "filesystem_type", "expected"),
    [
        (EXT_SUPER_MAGIC, "ext2", "ext-family"),
        (EXT_SUPER_MAGIC, "ext3", "ext-family"),
        (EXT_SUPER_MAGIC, "ext4", "ext-family"),
        (XFS_SUPER_MAGIC, "xfs", "xfs"),
        (BTRFS_SUPER_MAGIC, "btrfs", "btrfs"),
        (ZFS_SUPER_MAGIC, "zfs", "zfs"),
    ],
)
def test_linux_classification_requires_exact_magic_mount_id_device_and_type(
    tmp_path: Path,
    magic: int,
    filesystem_type: str,
    expected: str,
) -> None:
    descriptor = _directory_fd(tmp_path)
    try:
        fake = _linux_fake(
            descriptor,
            magic=magic,
            filesystem_type=filesystem_type,
        )

        identity = classify_filesystem(descriptor, posix=fake)

        assert identity == FilesystemIdentity(
            filesystem_class=expected,
            device=os.fstat(descriptor).st_dev,
            mount_id=42,
        )
        assert [call[0] for call in fake.calls] == [
            "fstatfs",
            "statx_mount_identity",
            "read_mountinfo",
        ]
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "magic",
    [
        0x6969,  # NFS
        0x517B,  # SMB
        0xFF534D42,  # CIFS
        0x65735546,  # FUSE
        0x794C7630,  # overlay
        0x01021994,  # tmpfs
        0xDEADBEEF,  # unknown
    ],
)
def test_linux_transport_or_unknown_magic_is_rejected_before_any_probe(
    tmp_path: Path, magic: int
) -> None:
    descriptor = _directory_fd(tmp_path)
    try:
        fake = _linux_fake(descriptor, magic=magic)

        with pytest.raises(UnsupportedFilesystemError) as caught:
            classify_filesystem(descriptor, posix=fake)

        assert caught.value.reason == "unclassified_filesystem"
        assert fake.calls == [("fstatfs", descriptor)]
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "filesystem_type",
    ["nfs", "nfs4", "cifs", "smbfs", "fuse", "overlay", "tmpfs", "ext5"],
)
def test_linux_mountinfo_transport_or_unknown_type_conflicts_with_allowed_magic(
    tmp_path: Path, filesystem_type: str
) -> None:
    descriptor = _directory_fd(tmp_path)
    try:
        fake = _linux_fake(descriptor, filesystem_type=filesystem_type)

        with pytest.raises(UnsupportedFilesystemError) as caught:
            classify_filesystem(descriptor, posix=fake)

        assert caught.value.reason == "mountinfo_conflict"
    finally:
        os.close(descriptor)


def test_linux_classification_rejects_absent_ambiguous_and_conflicting_mount_rows(
    tmp_path: Path,
) -> None:
    descriptor = _directory_fd(tmp_path)
    major, minor = _device_parts(descriptor)
    try:
        absent = _linux_fake(
            descriptor,
            mountinfo=_mountinfo_line(
                mount_id=41,
                major=major,
                minor=minor,
                filesystem_type="ext4",
            ),
        )
        with pytest.raises(UnsupportedFilesystemError) as absent_error:
            classify_filesystem(descriptor, posix=absent)
        assert absent_error.value.reason == "mountinfo_absent"

        matching = _mountinfo_line(
            mount_id=42,
            major=major,
            minor=minor,
            filesystem_type="ext4",
        )
        ambiguous = _linux_fake(descriptor, mountinfo=matching + matching)
        with pytest.raises(UnsupportedFilesystemError) as ambiguous_error:
            classify_filesystem(descriptor, posix=ambiguous)
        assert ambiguous_error.value.reason == "mountinfo_ambiguous"

        conflict = _linux_fake(
            descriptor,
            mountinfo=_mountinfo_line(
                mount_id=42,
                major=major,
                minor=minor + 1,
                filesystem_type="ext4",
            ),
        )
        with pytest.raises(UnsupportedFilesystemError) as conflict_error:
            classify_filesystem(descriptor, posix=conflict)
        assert conflict_error.value.reason == "mountinfo_conflict"
    finally:
        os.close(descriptor)


def test_linux_classification_rejects_fstat_and_statx_device_disagreement(
    tmp_path: Path,
) -> None:
    descriptor = _directory_fd(tmp_path)
    fake = _linux_fake(descriptor)
    assert fake.mount_identity is not None
    fake.mount_identity = MountIdentity(
        mount_id=fake.mount_identity.mount_id,
        device_major=fake.mount_identity.device_major,
        device_minor=fake.mount_identity.device_minor + 1,
    )
    try:
        with pytest.raises(UnsupportedFilesystemError) as caught:
            classify_filesystem(descriptor, posix=fake)
        assert caught.value.reason == "descriptor_identity_conflict"
        assert not any(call[0] == "read_mountinfo" for call in fake.calls)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    ("type_name", "expected"),
    [("apfs", "apfs"), ("hfs", "hfsplus")],
)
def test_darwin_classification_requires_mnt_local_and_exact_type(
    tmp_path: Path, type_name: str, expected: str
) -> None:
    descriptor = _directory_fd(tmp_path)
    try:
        fake = _darwin_fake(type_name=type_name)
        assert classify_filesystem(descriptor, posix=fake) == FilesystemIdentity(
            filesystem_class=expected,
            device=os.fstat(descriptor).st_dev,
            mount_id=None,
        )
        assert fake.calls == [("fstatfs", descriptor)]
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    ("type_name", "flags", "reason"),
    [
        ("apfs", 0, "nonlocal_filesystem"),
        ("hfs", MNT_LOCAL ^ MNT_LOCAL, "nonlocal_filesystem"),
        ("nfs", MNT_LOCAL, "unclassified_filesystem"),
        ("smbfs", MNT_LOCAL, "unclassified_filesystem"),
        ("fusefs", MNT_LOCAL, "unclassified_filesystem"),
        ("apfsx", MNT_LOCAL, "unclassified_filesystem"),
    ],
)
def test_darwin_nonlocal_transport_or_unknown_type_is_rejected(
    tmp_path: Path, type_name: str, flags: int, reason: str
) -> None:
    descriptor = _directory_fd(tmp_path)
    try:
        with pytest.raises(UnsupportedFilesystemError) as caught:
            classify_filesystem(descriptor, posix=_darwin_fake(type_name=type_name, flags=flags))
        assert caught.value.reason == reason
    finally:
        os.close(descriptor)


def test_classification_rejects_posix_platform_or_raw_stat_mismatch(tmp_path: Path) -> None:
    descriptor = _directory_fd(tmp_path)
    try:
        fake = FakePosixOps(
            platform="linux",
            filesystem_stat=FileSystemStat(
                platform="darwin",
                type_magic=None,
                type_name="apfs",
                flags=MNT_LOCAL,
            ),
        )
        with pytest.raises(UnsupportedFilesystemError) as caught:
            classify_filesystem(descriptor, posix=fake)
        assert caught.value.reason == "invalid_filesystem_stat"
    finally:
        os.close(descriptor)


def test_creator_lock_is_private_regular_no_follow_and_blocking_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    real_open = os.open
    open_calls: list[tuple[str, int, int, int | None]] = []

    def tracking_open(
        path: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        open_calls.append((path, flags, mode, dir_fd))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    try:
        monkeypatch.setattr(filesystem.os, "open", tracking_open)
        handle = acquire_creator_lock(directory_fd, posix=fake)
        lock_stat = os.fstat(handle.descriptor)

        assert stat.S_ISREG(lock_stat.st_mode)
        assert stat.S_IMODE(os.stat(tmp_path / CREATOR_LOCK_NAME).st_mode) == 0o600
        path, flags, mode, parent = open_calls[0]
        assert path == CREATOR_LOCK_NAME
        assert flags & os.O_CREAT
        assert flags & os.O_NONBLOCK
        assert flags & getattr(os, "O_NOFOLLOW", 0)
        assert mode == 0o600
        assert parent == directory_fd
        assert ("acquire_lock", handle.descriptor, True, True) in fake.calls

        handle.close()
        assert ("release_lock", handle.descriptor) in fake.calls
        handle.close()
        assert fake.calls.count(("release_lock", handle.descriptor)) == 1
    finally:
        os.close(directory_fd)


@pytest.mark.parametrize(
    ("acquire", "exclusive", "open_write"),
    [
        (try_acquire_mutator_lock, True, True),
        (try_acquire_shared_lock, False, False),
    ],
)
def test_capsule_locks_open_existing_regular_leaf_and_use_nonblocking_busy_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    acquire: Callable[..., object],
    exclusive: bool,
    open_write: bool,
) -> None:
    (tmp_path / PERSISTENT_LOCK_NAME).write_bytes(b"")
    os.chmod(tmp_path / PERSISTENT_LOCK_NAME, 0o600)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    real_open = os.open
    open_calls: list[tuple[str, int, int | None]] = []

    def tracking_open(path: str, flags: int, *args: Any, dir_fd: int | None = None) -> int:
        open_calls.append((path, flags, dir_fd))
        return real_open(path, flags, *args, dir_fd=dir_fd)

    try:
        monkeypatch.setattr(filesystem.os, "open", tracking_open)
        handle = acquire(directory_fd, posix=fake)
        assert handle is not None
        path, flags, parent = open_calls[0]
        assert path == PERSISTENT_LOCK_NAME
        assert not flags & os.O_CREAT
        assert flags & os.O_NONBLOCK
        assert flags & getattr(os, "O_NOFOLLOW", 0)
        assert bool(flags & os.O_RDWR) is open_write
        assert parent == directory_fd
        assert ("acquire_lock", handle.descriptor, exclusive, False) in fake.calls
        handle.close()
    finally:
        os.close(directory_fd)


@pytest.mark.parametrize("acquire", [try_acquire_mutator_lock, try_acquire_shared_lock])
def test_nonblocking_lock_contention_returns_busy_and_closes_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    acquire: Callable[..., object],
) -> None:
    (tmp_path / PERSISTENT_LOCK_NAME).write_bytes(b"")
    os.chmod(tmp_path / PERSISTENT_LOCK_NAME, 0o600)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    fake.lock_error = BlockingIOError(errno.EWOULDBLOCK, "private lock")
    real_close = os.close
    closed: list[int] = []

    def tracking_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    try:
        monkeypatch.setattr(filesystem.os, "close", tracking_close)
        assert acquire(directory_fd, posix=fake) is None
        assert len(closed) == 1
        assert not any(call[0] == "release_lock" for call in fake.calls)
    finally:
        os.close(directory_fd)


def test_lock_open_rejects_symlink_before_advisory_operation(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"")
    (tmp_path / PERSISTENT_LOCK_NAME).symlink_to(target)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    try:
        with pytest.raises(OSError):
            try_acquire_mutator_lock(directory_fd, posix=fake)
        assert not any(call[0] == "acquire_lock" for call in fake.calls)
    finally:
        os.close(directory_fd)


def test_lock_open_rejects_nonregular_leaf_before_advisory_operation(tmp_path: Path) -> None:
    (tmp_path / PERSISTENT_LOCK_NAME).mkdir()
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    try:
        with pytest.raises(OwnedStagingError) as caught:
            try_acquire_shared_lock(directory_fd, posix=fake)
        assert caught.value.code == "unsafe_lock_file"
        assert not any(call[0] == "acquire_lock" for call in fake.calls)
    finally:
        os.close(directory_fd)


def test_owned_staging_uses_exact_operation_name_private_mode_and_no_follow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    real_open = os.open
    real_mkdir = os.mkdir
    real_fchmod = os.fchmod
    opens: list[tuple[str, int, int | None]] = []
    mkdirs: list[tuple[str, int, int | None]] = []
    fchmods: list[tuple[int, int]] = []

    def tracking_open(path: str, flags: int, *args: Any, dir_fd: int | None = None) -> int:
        opens.append((path, flags, dir_fd))
        return real_open(path, flags, *args, dir_fd=dir_fd)

    def tracking_mkdir(path: str, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        mkdirs.append((path, mode, dir_fd))
        real_mkdir(path, mode, dir_fd=dir_fd)

    def tracking_fchmod(descriptor: int, mode: int) -> None:
        fchmods.append((descriptor, mode))
        real_fchmod(descriptor, mode)

    try:
        monkeypatch.setattr(filesystem.os, "open", tracking_open)
        monkeypatch.setattr(filesystem.os, "mkdir", tracking_mkdir)
        monkeypatch.setattr(filesystem.os, "fchmod", tracking_fchmod)
        previous_umask = os.umask(0o200)
        try:
            staging = create_owned_staging(parent_fd, operation_id)
        finally:
            os.umask(previous_umask)

        assert staging.name == ".laconian-stage.12345678-1234-4abc-9234-1234567890ab"
        assert staging.state == "owned"
        assert mkdirs == [(staging.name, 0o700, parent_fd)]
        assert fchmods == [(staging.descriptor, 0o700)]
        assert opens[0][0] == staging.name
        assert opens[0][1] & getattr(os, "O_DIRECTORY", 0)
        assert opens[0][1] & getattr(os, "O_NOFOLLOW", 0)
        assert opens[0][2] == parent_fd
        assert stat.S_IMODE(os.stat(tmp_path / staging.name).st_mode) == 0o700

        cleanup_owned_staging(staging, posix=_darwin_fake())
    finally:
        os.close(parent_fd)


def test_owned_staging_fchmod_failure_closes_once_and_removes_only_created_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    stage_name = f".laconian-stage.{operation_id}"
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"preserve")
    real_close = os.close
    stage_descriptor: int | None = None
    stage_close_calls = 0

    def fail_fchmod(descriptor: int, mode: int) -> None:
        nonlocal stage_descriptor
        stage_descriptor = descriptor
        assert mode == 0o700
        raise OSError(errno.EIO, "private fchmod failure")

    def tracking_close(descriptor: int) -> None:
        nonlocal stage_close_calls
        if descriptor == stage_descriptor:
            stage_close_calls += 1
        real_close(descriptor)

    try:
        monkeypatch.setattr(filesystem.os, "fchmod", fail_fchmod)
        monkeypatch.setattr(filesystem.os, "close", tracking_close)
        with pytest.raises(OSError, match="private fchmod failure"):
            create_owned_staging(parent_fd, operation_id)

        assert stage_descriptor is not None
        assert stage_close_calls == 1
        assert not (tmp_path / stage_name).exists()
        assert sentinel.read_bytes() == b"preserve"
    finally:
        real_close(parent_fd)


def test_owned_staging_rechecks_path_identity_and_mode_after_fchmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    stage_name = f".laconian-stage.{operation_id}"
    moved_name = "moved-created-stage"
    real_fchmod = os.fchmod

    def replace_path_after_fchmod(descriptor: int, mode: int) -> None:
        real_fchmod(descriptor, mode)
        os.rename(stage_name, moved_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.mkdir(stage_name, 0o700, dir_fd=parent_fd)
        (tmp_path / stage_name / "sentinel").write_bytes(b"replacement")

    try:
        monkeypatch.setattr(filesystem.os, "fchmod", replace_path_after_fchmod)
        with pytest.raises(OwnedStagingError) as caught:
            create_owned_staging(parent_fd, operation_id)

        assert caught.value.code == "staging_identity_mismatch"
        assert (tmp_path / stage_name / "sentinel").read_bytes() == b"replacement"
        assert (tmp_path / moved_name).is_dir()
    finally:
        os.close(parent_fd)


def test_owned_staging_rejects_a_nonexact_post_fchmod_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    stage_name = f".laconian-stage.{operation_id}"
    real_fchmod = os.fchmod

    def establish_wrong_mode(descriptor: int, _mode: int) -> None:
        real_fchmod(descriptor, 0o755)

    try:
        monkeypatch.setattr(filesystem.os, "fchmod", establish_wrong_mode)
        with pytest.raises(OwnedStagingError) as caught:
            create_owned_staging(parent_fd, operation_id)

        assert caught.value.code == "staging_identity_mismatch"
        assert not (tmp_path / stage_name).exists()
    finally:
        os.close(parent_fd)


@pytest.mark.parametrize(
    "operation_id",
    [
        "12345678-1234-4abc-9234-1234567890ab",
        UUID("12345678-1234-1abc-9234-1234567890ab"),
        UUID("12345678-1234-4abc-1234-1234567890ab"),
    ],
)
def test_owned_staging_requires_an_rfc4122_uuid4(operation_id: object, tmp_path: Path) -> None:
    parent_fd = _directory_fd(tmp_path)
    try:
        with pytest.raises(OwnedStagingError) as caught:
            create_owned_staging(parent_fd, operation_id)  # type: ignore[arg-type]
        assert caught.value.code == "invalid_operation_id"
        assert list(tmp_path.iterdir()) == []
    finally:
        os.close(parent_fd)


def test_owned_staging_cleanup_is_recursive_descriptor_relative_and_preserves_link_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"preserve")
    parent_fd = _directory_fd(root)
    fake = _darwin_fake()
    try:
        staging = create_owned_staging(
            parent_fd,
            UUID("12345678-1234-4abc-9234-1234567890ab"),
        )
        nested = root / staging.name / "nested"
        nested.mkdir()
        (nested / "data").write_bytes(b"evidence")
        (root / staging.name / "outside-link").symlink_to(outside)

        cleanup_owned_staging(staging, posix=fake)

        assert staging.state == "removed"
        assert not (root / staging.name).exists()
        assert outside.read_bytes() == b"preserve"
        fsynced = [call[1] for call in fake.calls if call[0] == "fsync"]
        assert parent_fd in fsynced
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
    finally:
        os.close(parent_fd)


def test_owned_staging_cleanup_rejects_replaced_path_and_removes_nothing(tmp_path: Path) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    fake = _darwin_fake()
    original_name = "original-preserved"
    try:
        staging = create_owned_staging(parent_fd, operation_id)
        os.rename(staging.name, original_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.mkdir(staging.name, 0o700, dir_fd=parent_fd)
        (tmp_path / staging.name / "replacement").write_bytes(b"do not remove")

        with pytest.raises(OwnedStagingError) as caught:
            cleanup_owned_staging(staging, posix=fake)

        assert caught.value.code == "staging_identity_mismatch"
        assert (tmp_path / staging.name / "replacement").read_bytes() == b"do not remove"
        assert (tmp_path / original_name).is_dir()
        assert not any(call[0] == "fsync" for call in fake.calls)
        assert staging.state == "abandoned"
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
    finally:
        os.close(parent_fd)


def test_capability_probes_are_fresh_same_mount_and_leave_staging_empty(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    try:
        staging = create_owned_staging(parent_fd, operation_id)
        fake = _linux_fake(parent_fd)
        contention_calls: list[tuple[int, str]] = []

        def contention_probe(directory_fd: int, name: str) -> None:
            contention_calls.append((directory_fd, name))

        first = run_filesystem_probes(
            parent_fd,
            staging,
            posix=fake,
            contention_probe=contention_probe,
        )
        second = run_filesystem_probes(
            parent_fd,
            staging,
            posix=fake,
            contention_probe=contention_probe,
        )

        assert first == second
        assert first.filesystem_class == "ext-family"
        assert len(contention_calls) == 2
        assert os.listdir(staging.descriptor) == []
        assert sum(call[0] == "fstatfs" for call in fake.calls) >= 6
        assert sum(call[0] == "rename_noreplace" for call in fake.calls) == 6
        assert sum(call[0] == "link_noreplace" for call in fake.calls) == 4
        assert sum(call[0] == "fsync" for call in fake.calls) >= 6

        cleanup_owned_staging(staging, posix=fake)
    finally:
        os.close(parent_fd)


def test_capability_probes_reject_staging_on_a_different_identity_before_operations(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    fake = _linux_fake(parent_fd)
    original = fake.statx_mount_identity
    call_count = 0

    def changing_mount(descriptor: int) -> MountIdentity:
        nonlocal call_count
        result = original(descriptor)
        call_count += 1
        if descriptor == staging.descriptor:
            return MountIdentity(
                mount_id=result.mount_id + 1,
                device_major=result.device_major,
                device_minor=result.device_minor,
            )
        return result

    fake.statx_mount_identity = changing_mount  # type: ignore[method-assign]
    try:
        with pytest.raises(UnsupportedFilesystemError) as caught:
            run_filesystem_probes(
                parent_fd,
                staging,
                posix=fake,
                contention_probe=lambda _directory_fd, _name: None,
            )
        assert caught.value.reason == "different_mount"
        assert call_count >= 2
        assert not any(call[0] == "rename_noreplace" for call in fake.calls)
        assert os.listdir(staging.descriptor) == []
    finally:
        cleanup_owned_staging(staging, posix=fake)
        os.close(parent_fd)


def test_capability_probe_collision_checks_preserve_both_file_and_directory_targets(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    fake = _linux_fake(parent_fd)
    try:
        run_filesystem_probes(
            parent_fd,
            staging,
            posix=fake,
            contention_probe=lambda _directory_fd, _name: None,
        )
        rename_calls = [call for call in fake.calls if call[0] == "rename_noreplace"]
        assert {call[2] for call in rename_calls} == {
            "rename-directory-success-source",
            "rename-file-source",
            "rename-directory-source",
        }
        assert {call[4] for call in rename_calls} == {
            "rename-directory-success-target",
            "rename-file-target",
            "rename-directory-target",
        }
        link_calls = [call for call in fake.calls if call[0] == "link_noreplace"]
        assert {call[4] for call in link_calls} == {"hard-link-copy", "hard-link-target"}
        assert os.listdir(staging.descriptor) == []
    finally:
        cleanup_owned_staging(staging, posix=fake)
        os.close(parent_fd)


@pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="POSIX-only acceptance")
def test_real_capability_probe_uses_second_process_contention_release_and_reacquire(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    posix = PosixOps()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    try:
        try:
            identity = classify_filesystem(parent_fd, posix=posix)
        except UnsupportedFilesystemError:
            pytest.skip("acceptance host filesystem is intentionally outside the allowlist")
        assert identity.filesystem_class in {"ext-family", "xfs", "btrfs", "zfs", "apfs", "hfsplus"}

        with acquire_creator_lock(parent_fd, posix=posix):
            assert run_filesystem_probes(parent_fd, staging, posix=posix) == identity

        assert os.listdir(staging.descriptor) == []
    finally:
        if staging.state == "owned":
            cleanup_owned_staging(staging, posix=posix)
        os.close(parent_fd)


def test_probe_implementation_has_no_sleep_or_thread_only_lock_shortcut() -> None:
    source = Path(filesystem.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "sleep" not in calls
    assert "threading" not in imports


def test_publication_collision_cleans_only_owned_stage_and_preserves_destination(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "sentinel").write_bytes(b"existing")
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    (tmp_path / staging.name / "candidate").write_bytes(b"new")
    try:
        with pytest.raises(DestinationCollisionError) as caught:
            publish_owned_staging(staging, "destination", posix=fake)

        assert caught.value.code == "destination_collision"
        assert caught.value.published is False
        assert staging.state == "removed"
        assert not (tmp_path / staging.name).exists()
        assert (destination / "sentinel").read_bytes() == b"existing"
        assert not (destination / "candidate").exists()
        assert parent_fd in [call[1] for call in fake.calls if call[0] == "fsync"]
    finally:
        os.close(parent_fd)


def test_post_publish_root_fsync_failure_preserves_visible_owned_destination(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    (tmp_path / staging.name / "capsule.json").write_bytes(b"{}")
    fake.fsync_error_for.add(parent_fd)
    try:
        with pytest.raises(PostPublishSyncError) as caught:
            publish_owned_staging(staging, "visible-capsule", posix=fake)

        assert caught.value.code == "post_publish_fsync_failed"
        assert caught.value.published is True
        assert caught.value.destination_name == "visible-capsule"
        assert staging.state == "published"
        assert not (tmp_path / staging.name).exists()
        assert (tmp_path / "visible-capsule" / "capsule.json").read_bytes() == b"{}"
        with pytest.raises(OwnedStagingError):
            cleanup_owned_staging(staging, posix=fake)
    finally:
        staging.close()
        os.close(parent_fd)


def test_successful_publication_fsyncs_root_after_state_becomes_published(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    observed_states: list[str] = []
    original_fsync = fake.fsync

    def observe_fsync(descriptor: int) -> None:
        if descriptor == parent_fd:
            observed_states.append(staging.state)
        original_fsync(descriptor)

    fake.fsync = observe_fsync  # type: ignore[method-assign]
    try:
        publish_owned_staging(staging, "visible-capsule", posix=fake)
        assert staging.state == "published"
        assert observed_states[-1] == "published"
        assert (tmp_path / "visible-capsule").is_dir()
    finally:
        staging.close()
        os.close(parent_fd)


def test_filesystem_module_forbids_path_rename_replace_and_check_then_publish_fallbacks() -> None:
    source = Path(filesystem.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr in {"rename", "replace"}
        ):
            forbidden_calls.append(node.func.attr)
    assert forbidden_calls == []


def test_publish_revalidates_stage_leaf_identity_and_preserves_replacement(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    try:
        os.rename(
            staging.name,
            "original-preserved",
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.mkdir(staging.name, 0o700, dir_fd=parent_fd)
        (tmp_path / staging.name / "replacement").write_bytes(b"preserve")

        with pytest.raises(OwnedStagingError) as caught:
            publish_owned_staging(staging, "destination", posix=fake)

        assert caught.value.code == "staging_identity_mismatch"
        assert (tmp_path / staging.name / "replacement").read_bytes() == b"preserve"
        assert (tmp_path / "original-preserved").is_dir()
        assert not any(call[0] in {"rename_noreplace", "fsync"} for call in fake.calls)
    finally:
        staging.close()
        os.close(parent_fd)


@pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="POSIX-only acceptance")
def test_second_process_probe_reports_independent_child_contention_and_death_release(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "probe-lock"
    lock_path.write_bytes(b"")
    os.chmod(lock_path, 0o600)
    directory_fd = _directory_fd(tmp_path)
    try:
        evidence = probe_second_process_lock(directory_fd, "probe-lock")
    finally:
        os.close(directory_fd)

    assert evidence == LockProbeEvidence(
        parent_pid=os.getpid(),
        child_pid=evidence.child_pid,
        child_observed_contention=True,
        child_acquired_after_release=True,
        parent_reacquired_after_child_death=True,
    )
    assert evidence.child_pid > 0
    assert evidence.child_pid != evidence.parent_pid


@pytest.mark.parametrize(
    ("failure", "expected_errno"),
    [
        ("rename_enosys", errno.ENOSYS),
        ("rename_unsupported", errno.EOPNOTSUPP),
        ("rename_always_exists", errno.EEXIST),
        ("rename_broken_overwrite", None),
        ("link_unsupported", errno.EOPNOTSUPP),
        ("file_fsync", errno.EIO),
    ],
)
def test_capability_probe_failures_are_unsupported_and_clean_probe_entries(
    tmp_path: Path,
    failure: str,
    expected_errno: int | None,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    fake = _linux_fake(parent_fd)
    original_rename = fake.rename_noreplace
    original_link = fake.link_noreplace
    original_fsync = fake.fsync

    def failing_rename(
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        if failure == "rename_enosys":
            raise OSError(errno.ENOSYS, "private")
        if failure == "rename_unsupported":
            raise OSError(errno.EOPNOTSUPP, "private")
        if failure == "rename_always_exists":
            raise FileExistsError(errno.EEXIST, "private")
        if failure == "rename_broken_overwrite" and target_name == "rename-file-target":
            os.unlink(target_name, dir_fd=target_directory_fd)
            os.rename(
                source_name,
                target_name,
                src_dir_fd=source_directory_fd,
                dst_dir_fd=target_directory_fd,
            )
            return
        original_rename(
            source_directory_fd,
            source_name,
            target_directory_fd,
            target_name,
        )

    def failing_link(
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        if failure == "link_unsupported":
            raise OSError(errno.EOPNOTSUPP, "private")
        original_link(
            source_directory_fd,
            source_name,
            target_directory_fd,
            target_name,
        )

    fsync_calls = 0

    def failing_fsync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if failure == "file_fsync" and fsync_calls == 1:
            raise OSError(errno.EIO, "private")
        original_fsync(descriptor)

    fake.rename_noreplace = failing_rename  # type: ignore[method-assign]
    fake.link_noreplace = failing_link  # type: ignore[method-assign]
    fake.fsync = failing_fsync  # type: ignore[method-assign]
    try:
        with pytest.raises(UnsupportedFilesystemError) as caught:
            run_filesystem_probes(
                parent_fd,
                staging,
                posix=fake,
                contention_probe=lambda _directory_fd, _name: None,
            )
        assert caught.value.code == "unsupported_filesystem"
        assert os.listdir(staging.descriptor) == []
        if expected_errno is not None:
            assert expected_errno in {
                errno.ENOSYS,
                errno.EOPNOTSUPP,
                errno.EEXIST,
                errno.EIO,
            }
    finally:
        cleanup_owned_staging(staging, posix=fake)
        os.close(parent_fd)


def test_capability_probes_fsync_a_regular_file_and_directories(tmp_path: Path) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    fake = _linux_fake(parent_fd)
    synced_types: list[str] = []
    original_fsync = fake.fsync

    def classify_sync_descriptor(descriptor: int) -> None:
        mode = os.fstat(descriptor).st_mode
        synced_types.append("file" if stat.S_ISREG(mode) else "directory")
        original_fsync(descriptor)

    fake.fsync = classify_sync_descriptor  # type: ignore[method-assign]
    try:
        run_filesystem_probes(
            parent_fd,
            staging,
            posix=fake,
            contention_probe=lambda _directory_fd, _name: None,
        )
        assert synced_types[0] == "file"
        assert "directory" in synced_types
        assert os.listdir(staging.descriptor) == []
    finally:
        cleanup_owned_staging(staging, posix=fake)
        os.close(parent_fd)


def test_lock_handle_release_failure_closes_once_and_consumes_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / PERSISTENT_LOCK_NAME).write_bytes(b"")
    os.chmod(tmp_path / PERSISTENT_LOCK_NAME, 0o600)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    handle = try_acquire_mutator_lock(directory_fd, posix=fake)
    assert handle is not None
    release_calls = 0
    real_close = os.close
    closed: list[int] = []

    def failing_release(_descriptor: int) -> None:
        nonlocal release_calls
        release_calls += 1
        raise OSError(errno.EIO, "private release")

    def tracking_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    fake.release_lock = failing_release  # type: ignore[method-assign]
    try:
        monkeypatch.setattr(filesystem.os, "close", tracking_close)
        with pytest.raises(OSError):
            handle.close()
        handle.close()
        assert release_calls == 1
        assert closed == [handle.descriptor]
    finally:
        os.close(directory_fd)


def test_lock_leaf_replacement_after_flock_releases_and_closes_original_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / PERSISTENT_LOCK_NAME
    lock_path.write_bytes(b"original")
    os.chmod(lock_path, 0o600)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    real_close = os.close
    closed: list[int] = []

    def replacing_acquire(descriptor: int, *, exclusive: bool, blocking: bool) -> None:
        fake.calls.append(("acquire_lock", descriptor, exclusive, blocking))
        lock_path.rename(tmp_path / "original-preserved")
        lock_path.write_bytes(b"replacement")
        os.chmod(lock_path, 0o600)

    def tracking_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    fake.acquire_lock = replacing_acquire  # type: ignore[method-assign]
    try:
        monkeypatch.setattr(filesystem.os, "close", tracking_close)
        with pytest.raises(OwnedStagingError) as caught:
            try_acquire_mutator_lock(directory_fd, posix=fake)
        assert caught.value.code == "unsafe_lock_file"
        assert lock_path.read_bytes() == b"replacement"
        assert (tmp_path / "original-preserved").read_bytes() == b"original"
        release_calls = [call for call in fake.calls if call[0] == "release_lock"]
        assert len(release_calls) == 1
        assert len(closed) == 1
    finally:
        os.close(directory_fd)


def test_lock_handle_never_retries_ambiguous_close_after_descriptor_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / PERSISTENT_LOCK_NAME).write_bytes(b"")
    os.chmod(tmp_path / PERSISTENT_LOCK_NAME, 0o600)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    handle = try_acquire_mutator_lock(directory_fd, posix=fake)
    assert handle is not None
    real_close = os.close
    real_open = os.open
    close_calls = 0
    replacement_fd: int | None = None

    def close_reuse_raise(descriptor: int) -> None:
        nonlocal close_calls, replacement_fd
        close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EIO, "ambiguous close")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(filesystem.os, "close", close_reuse_raise)
            with pytest.raises(OSError):
                handle.close()
            handle.close()
            assert close_calls == 1
            assert replacement_fd is not None
            os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        os.close(directory_fd)


def test_busy_lock_ambiguous_close_is_consumed_once_before_descriptor_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / PERSISTENT_LOCK_NAME
    lock_path.write_bytes(b"")
    os.chmod(lock_path, 0o600)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    fake.lock_error = BlockingIOError(errno.EWOULDBLOCK, "private lock")
    real_close = os.close
    real_open = os.open
    close_calls = 0
    replacement_fd: int | None = None

    def close_reuse_raise(descriptor: int) -> None:
        nonlocal close_calls, replacement_fd
        close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EIO, "ambiguous close")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(filesystem.os, "close", close_reuse_raise)
            with pytest.raises(OSError):
                try_acquire_mutator_lock(directory_fd, posix=fake)
            assert close_calls == 1
            assert replacement_fd is not None
            os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        os.close(directory_fd)


def test_preexisting_regular_lock_allows_broader_mode_for_later_verification_warning(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / PERSISTENT_LOCK_NAME
    lock_path.write_bytes(b"")
    os.chmod(lock_path, 0o640)
    directory_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    try:
        handle = try_acquire_shared_lock(directory_fd, posix=fake)
        assert handle is not None
        assert ("acquire_lock", handle.descriptor, False, False) in fake.calls
        assert stat.S_IMODE(os.stat(lock_path).st_mode) == 0o640
        handle.close()
    finally:
        os.close(directory_fd)


def test_preexisting_stage_is_never_opened_or_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    name = f".laconian-stage.{operation_id}"
    existing = tmp_path / name
    existing.mkdir()
    (existing / "sentinel").write_bytes(b"preserve")
    real_open = os.open
    opened_names: list[object] = []

    def tracking_open(path: object, *args: Any, **kwargs: Any) -> int:
        opened_names.append(path)
        return real_open(path, *args, **kwargs)

    try:
        monkeypatch.setattr(filesystem.os, "open", tracking_open)
        with pytest.raises(FileExistsError):
            create_owned_staging(parent_fd, operation_id)
        assert name not in opened_names
        assert (existing / "sentinel").read_bytes() == b"preserve"
    finally:
        os.close(parent_fd)


def test_post_mkdir_open_failure_rolls_back_only_the_just_created_empty_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    stage_name = f".laconian-stage.{operation_id}"
    real_open = os.open
    stage_open_attempts = 0

    def failing_stage_open(path: object, *args: Any, **kwargs: Any) -> int:
        nonlocal stage_open_attempts
        if path == stage_name:
            stage_open_attempts += 1
            raise OSError(errno.EIO, "injected open failure")
        return real_open(path, *args, **kwargs)

    try:
        monkeypatch.setattr(filesystem.os, "open", failing_stage_open)
        with pytest.raises(OSError):
            create_owned_staging(parent_fd, operation_id)
        assert stage_open_attempts == 1
        assert not (tmp_path / stage_name).exists()
        assert list(tmp_path.iterdir()) == []
    finally:
        os.close(parent_fd)


def test_cleanup_ambiguous_close_marks_removed_before_fd_reuse_and_never_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    fake = _darwin_fake()
    real_close = os.close
    real_open = os.open
    close_calls = 0
    replacement_fd: int | None = None

    def close_stage_reuse_raise(descriptor: int) -> None:
        nonlocal close_calls, replacement_fd
        assert descriptor == staging.descriptor
        close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EIO, "ambiguous close")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(filesystem.os, "close", close_stage_reuse_raise)
            with pytest.raises(OSError):
                cleanup_owned_staging(staging, posix=fake)
            assert staging.state == "removed"
            assert not (tmp_path / staging.name).exists()
            with pytest.raises(OwnedStagingError) as caught:
                cleanup_owned_staging(staging, posix=fake)
            assert caught.value.code == "staging_not_owned"
            assert close_calls == 1
            assert replacement_fd is not None
            os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        os.close(parent_fd)


def test_explicit_close_abandons_owned_stage_and_prevents_unsafe_cleanup_retry(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    try:
        staging.close()
        assert staging.state == "abandoned"
        with pytest.raises(OwnedStagingError) as caught:
            cleanup_owned_staging(staging, posix=_darwin_fake())
        assert caught.value.code == "staging_not_owned"
        assert (tmp_path / staging.name).is_dir()
        staging.close()
    finally:
        os.close(parent_fd)


@pytest.mark.parametrize(
    "raw",
    [
        _mountinfo_line(mount_id=1, major=8, minor=1, filesystem_type="ext4") + b"malformed\n",
        b"42 1 8:1 / / rw - ext4 /dev/source rw\r\n",
        b"42 1 8:1 / /nul\x00path rw - ext4 /dev/source rw\n",
        b"42 1 8:1 / / rw - ext4 /dev/source rw - extra\n",
    ],
)
def test_mountinfo_rejects_malformed_unrelated_rows_cr_nul_and_extra_separator(
    raw: bytes,
) -> None:
    with pytest.raises(UnsupportedFilesystemError) as caught:
        parse_linux_mountinfo(raw)
    assert caught.value.reason == "invalid_mountinfo"


def test_classification_rejects_but_does_not_close_a_regular_file_descriptor(
    tmp_path: Path,
) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"data")
    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(UnsupportedFilesystemError) as caught:
            classify_filesystem(descriptor, posix=_linux_fake(descriptor))
        assert caught.value.reason == "invalid_descriptor"
        os.fstat(descriptor)
    finally:
        os.close(descriptor)


@pytest.mark.parametrize(
    "destination",
    ["", ".", "..", "nested/name", "nul\x00name", "control\x1fname", "surrogate\ud800"],
)
def test_publication_rejects_invalid_destination_leaf_without_syscalls(
    tmp_path: Path,
    destination: str,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    try:
        with pytest.raises(OwnedStagingError) as caught:
            publish_owned_staging(staging, destination, posix=fake)
        assert caught.value.code == "invalid_leaf_name"
        assert staging.state == "owned"
        assert not any(call[0] in {"rename_noreplace", "fsync"} for call in fake.calls)
    finally:
        cleanup_owned_staging(staging, posix=fake)
        os.close(parent_fd)


def test_publication_does_not_preflight_a_valid_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    real_stat = os.stat

    def forbidden_destination_stat(path: object, *args: Any, **kwargs: Any) -> os.stat_result:
        if path == "destination":
            raise AssertionError("destination was preflighted")
        return real_stat(path, *args, **kwargs)

    def direct_fake_rename(
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        fake.calls.append(("rename_noreplace", source_name, target_name))
        os.rename(
            source_name,
            target_name,
            src_dir_fd=source_directory_fd,
            dst_dir_fd=target_directory_fd,
        )

    fake.rename_noreplace = direct_fake_rename  # type: ignore[method-assign]
    try:
        monkeypatch.setattr(filesystem.os, "stat", forbidden_destination_stat)
        publish_owned_staging(staging, "destination", posix=fake)
        assert staging.state == "published"
        assert (tmp_path / "destination").is_dir()
    finally:
        staging.close()
        os.close(parent_fd)


def test_cleanup_uses_bounded_descriptor_streaming_without_path_or_shutil_fallbacks() -> None:
    source = Path(filesystem.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    os_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    }
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "scandir" in os_calls
    assert "listdir" not in os_calls
    assert "shutil" not in imports
    assert "/proc/self/fd" not in source


def test_cleanup_entry_limit_stops_before_overrun_and_consumes_stage_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    (tmp_path / staging.name / "first").write_bytes(b"1")
    (tmp_path / staging.name / "second").write_bytes(b"2")
    monkeypatch.setattr(filesystem, "_MAX_CLEANUP_ENTRIES", 1)
    try:
        with pytest.raises(OwnedStagingError) as caught:
            cleanup_owned_staging(staging, posix=_darwin_fake(), entry_ceiling=None)
        assert caught.value.code == "staging_cleanup_limit"
        assert staging.state == "abandoned"
        assert len(list((tmp_path / staging.name).iterdir())) == 1
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
    finally:
        os.close(parent_fd)


def test_cleanup_explicit_entry_ceiling_accepts_exact_recursive_bound(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    nested = tmp_path / staging.name / "nested"
    nested.mkdir()
    (nested / "entry").write_bytes(b"data")
    try:
        cleanup_owned_staging(staging, posix=_darwin_fake(), entry_ceiling=2)

        assert staging.state == "removed"
        assert not (tmp_path / staging.name).exists()
    finally:
        os.close(parent_fd)


def test_cleanup_explicit_entry_ceiling_stops_at_recursive_bound_plus_one(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    nested = tmp_path / staging.name / "nested"
    nested.mkdir()
    (nested / "first").write_bytes(b"1")
    (nested / "second").write_bytes(b"2")
    try:
        with pytest.raises(OwnedStagingError) as caught:
            cleanup_owned_staging(staging, posix=_darwin_fake(), entry_ceiling=2)

        assert caught.value.code == "staging_cleanup_limit"
        assert staging.state == "abandoned"
        assert len(list(nested.iterdir())) == 1
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
    finally:
        os.close(parent_fd)


@pytest.mark.parametrize("invalid_ceiling", [True, False, 0, -1, 1.0, "1"])
def test_cleanup_rejects_invalid_explicit_entry_ceiling_before_validation_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_ceiling: object,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    sentinel = tmp_path / staging.name / "sentinel"
    sentinel.write_bytes(b"preserve")

    def forbidden_validation(_staging: object) -> None:
        raise AssertionError("invalid ceiling reached staging validation")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(filesystem, "_validate_owned_directory", forbidden_validation)
            with pytest.raises(OwnedStagingError) as caught:
                cleanup_owned_staging(
                    staging,
                    posix=_darwin_fake(),
                    entry_ceiling=invalid_ceiling,  # type: ignore[arg-type]
                )

        assert caught.value.code == "invalid_cleanup_entry_ceiling"
        assert staging.state == "owned"
        assert sentinel.read_bytes() == b"preserve"
        os.fstat(staging.descriptor)
        cleanup_owned_staging(staging, posix=_darwin_fake())
    finally:
        os.close(parent_fd)


def test_cleanup_depth_limit_stops_before_descending_and_consumes_stage_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    nested = tmp_path / staging.name / "level-one" / "level-two"
    nested.mkdir(parents=True)
    (nested / "sentinel").write_bytes(b"preserve")
    monkeypatch.setattr(filesystem, "_MAX_CLEANUP_DEPTH", 0)
    try:
        with pytest.raises(OwnedStagingError) as caught:
            cleanup_owned_staging(staging, posix=_darwin_fake())
        assert caught.value.code == "staging_cleanup_limit"
        assert staging.state == "abandoned"
        assert (nested / "sentinel").read_bytes() == b"preserve"
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
    finally:
        os.close(parent_fd)


def test_persistent_directory_fsync_failure_consumes_owned_stage_once(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    (tmp_path / staging.name / "entry").write_bytes(b"data")
    fake = _darwin_fake()

    def always_fail_fsync(descriptor: int) -> None:
        fake.calls.append(("fsync", descriptor, "failure"))
        raise OSError(errno.EIO, "persistent fsync failure")

    fake.fsync = always_fail_fsync  # type: ignore[method-assign]
    try:
        with pytest.raises(OSError):
            cleanup_owned_staging(staging, posix=fake)
        assert staging.state == "abandoned"
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
        with pytest.raises(OwnedStagingError) as retry:
            cleanup_owned_staging(staging, posix=fake)
        assert retry.value.code == "staging_not_owned"
        assert len([call for call in fake.calls if call[0] == "fsync"]) == 1
    finally:
        os.close(parent_fd)


def test_preparation_filesystem_classifies_before_lock_and_holds_lock_through_publish(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    operation_id = UUID("12345678-1234-4abc-9234-1234567890ab")
    staging_descriptor = -1
    try:
        with preparation_filesystem(
            parent_fd,
            operation_id,
            posix=fake,
            contention_probe=lambda _directory_fd, _name: None,
        ) as workspace:
            assert isinstance(workspace, PreparationFilesystem)
            assert workspace.filesystem_identity.filesystem_class == "apfs"
            acquire_index = next(
                index for index, call in enumerate(fake.calls) if call[0] == "acquire_lock"
            )
            assert fake.calls[0] == ("fstatfs", parent_fd)
            assert acquire_index > 0
            assert workspace.staging.state == "owned"
            staging_descriptor = workspace.staging.descriptor
            workspace.publish("destination")
            assert workspace.staging.state == "published"
            assert not any(call[0] == "release_lock" for call in fake.calls)

        release_index = next(
            index for index, call in enumerate(fake.calls) if call[0] == "release_lock"
        )
        publish_index = max(
            index for index, call in enumerate(fake.calls) if call[0] == "rename_noreplace"
        )
        root_fsync_index = max(
            index
            for index, call in enumerate(fake.calls)
            if call[0] == "fsync" and call[1] == parent_fd
        )
        assert publish_index < root_fsync_index < release_index
        assert (tmp_path / "destination").is_dir()
        with pytest.raises(OSError):
            os.fstat(staging_descriptor)
    finally:
        os.close(parent_fd)


def test_preparation_context_closes_post_publish_fsync_failure_but_preserves_destination(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging_descriptor = -1
    try:
        with (
            pytest.raises(PostPublishSyncError),
            preparation_filesystem(
                parent_fd,
                UUID("12345678-1234-4abc-9234-1234567890ab"),
                posix=fake,
                contention_probe=lambda _directory_fd, _name: None,
            ) as workspace,
        ):
            staging_descriptor = workspace.staging.descriptor
            fake.fsync_error_for.add(parent_fd)
            workspace.publish("visible-after-sync-failure")
        assert (tmp_path / "visible-after-sync-failure").is_dir()
        with pytest.raises(OSError):
            os.fstat(staging_descriptor)
        assert any(call[0] == "release_lock" for call in fake.calls)
    finally:
        os.close(parent_fd)


def test_post_publish_error_survives_ambiguous_stage_close_and_fd_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    real_close = os.close
    real_open = os.open
    staging_descriptor = -1
    stage_close_calls = 0
    replacement_fd: int | None = None

    def close_stage_reuse_raise(descriptor: int) -> None:
        nonlocal stage_close_calls, replacement_fd
        if descriptor != staging_descriptor:
            real_close(descriptor)
            return
        stage_close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EIO, "ambiguous stage close")

    try:
        with (
            pytest.raises(PostPublishSyncError) as caught,
            preparation_filesystem(
                parent_fd,
                UUID("12345678-1234-4abc-9234-1234567890ab"),
                posix=fake,
                contention_probe=lambda _directory_fd, _name: None,
            ) as workspace,
        ):
            staging_descriptor = workspace.staging.descriptor
            monkeypatch.setattr(filesystem.os, "close", close_stage_reuse_raise)
            fake.fsync_error_for.add(parent_fd)
            workspace.publish("visible-recovery")
        assert caught.value.published is True
        assert caught.value.destination_name == "visible-recovery"
        assert (tmp_path / "visible-recovery").is_dir()
        assert stage_close_calls == 1
        assert replacement_fd is not None
        os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        real_close(parent_fd)


def test_body_error_survives_persistent_cleanup_failure(tmp_path: Path) -> None:
    class BodyFailure(RuntimeError):
        pass

    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging_descriptor = -1
    try:
        with (
            pytest.raises(BodyFailure, match="primary") as caught,
            preparation_filesystem(
                parent_fd,
                UUID("12345678-1234-4abc-9234-1234567890ab"),
                posix=fake,
                contention_probe=lambda _directory_fd, _name: None,
            ) as workspace,
        ):
            staging_descriptor = workspace.staging.descriptor
            fake.fsync_error_for.add(staging_descriptor)
            raise BodyFailure("primary")
        assert caught.value.__notes__ == ["filesystem cleanup also failed"]
        with pytest.raises(OSError):
            os.fstat(staging_descriptor)
    finally:
        os.close(parent_fd)


def test_collision_survives_ambiguous_cleanup_close_and_preserves_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "sentinel").write_bytes(b"existing")
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    real_close = os.close
    real_open = os.open
    close_calls = 0
    replacement_fd: int | None = None

    def close_stage_reuse_raise(descriptor: int) -> None:
        nonlocal close_calls, replacement_fd
        assert descriptor == staging.descriptor
        close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EIO, "ambiguous cleanup close")

    try:
        monkeypatch.setattr(filesystem.os, "close", close_stage_reuse_raise)
        with pytest.raises(DestinationCollisionError) as caught:
            publish_owned_staging(staging, "destination", posix=fake)
        assert caught.value.published is False
        assert caught.value.__notes__ == ["filesystem cleanup also failed"]
        assert (destination / "sentinel").read_bytes() == b"existing"
        assert staging.state == "removed"
        assert close_calls == 1
        assert replacement_fd is not None
        os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        real_close(parent_fd)


def test_post_publish_error_survives_creator_release_and_ambiguous_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    real_close = os.close
    real_open = os.open
    creator_descriptor = -1
    creator_close_calls = 0
    replacement_fd: int | None = None

    def failing_release(descriptor: int) -> None:
        fake.calls.append(("release_lock", descriptor))
        raise OSError(errno.EIO, "ambiguous creator release")

    def close_creator_reuse_raise(descriptor: int) -> None:
        nonlocal creator_close_calls, replacement_fd
        if descriptor != creator_descriptor:
            real_close(descriptor)
            return
        creator_close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EBADF, "ambiguous creator close")

    try:
        with (
            pytest.raises(PostPublishSyncError) as caught,
            preparation_filesystem(
                parent_fd,
                UUID("12345678-1234-4abc-9234-1234567890ab"),
                posix=fake,
                contention_probe=lambda _directory_fd, _name: None,
            ) as workspace,
        ):
            creator_descriptor = next(call[1] for call in fake.calls if call[0] == "acquire_lock")
            fake.release_lock = failing_release  # type: ignore[method-assign]
            monkeypatch.setattr(filesystem.os, "close", close_creator_reuse_raise)
            fake.fsync_error_for.add(parent_fd)
            workspace.publish("visible-after-creator-failure")
        assert caught.value.published is True
        assert caught.value.destination_name == "visible-after-creator-failure"
        assert (tmp_path / "visible-after-creator-failure").is_dir()
        assert creator_close_calls == 1
        assert replacement_fd is not None
        os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        real_close(parent_fd)


def test_durable_publish_suppresses_ambiguous_stage_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    real_close = os.close
    real_open = os.open
    staging_descriptor = -1
    stage_close_calls = 0
    replacement_fd: int | None = None

    def close_stage_reuse_raise(descriptor: int) -> None:
        nonlocal stage_close_calls, replacement_fd
        if descriptor != staging_descriptor:
            real_close(descriptor)
            return
        stage_close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EIO, "ambiguous durable-stage close")

    try:
        with preparation_filesystem(
            parent_fd,
            UUID("12345678-1234-4abc-9234-1234567890ab"),
            posix=fake,
            contention_probe=lambda _directory_fd, _name: None,
        ) as workspace:
            staging_descriptor = workspace.staging.descriptor
            monkeypatch.setattr(filesystem.os, "close", close_stage_reuse_raise)
            workspace.publish("durable-destination")
        assert workspace.staging.state == "published"
        assert (tmp_path / "durable-destination").is_dir()
        assert stage_close_calls == 1
        assert replacement_fd is not None
        os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        real_close(parent_fd)


def test_durable_publish_suppresses_creator_release_and_ambiguous_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    real_close = os.close
    real_open = os.open
    creator_descriptor = -1
    creator_close_calls = 0
    replacement_fd: int | None = None

    def failing_release(descriptor: int) -> None:
        fake.calls.append(("release_lock", descriptor))
        raise OSError(errno.EIO, "durable creator release")

    def close_creator_reuse_raise(descriptor: int) -> None:
        nonlocal creator_close_calls, replacement_fd
        if descriptor != creator_descriptor:
            real_close(descriptor)
            return
        creator_close_calls += 1
        real_close(descriptor)
        replacement_fd = real_open("/dev/null", os.O_RDONLY)
        assert replacement_fd == descriptor
        raise OSError(errno.EBADF, "ambiguous durable-creator close")

    try:
        with preparation_filesystem(
            parent_fd,
            UUID("12345678-1234-4abc-9234-1234567890ab"),
            posix=fake,
            contention_probe=lambda _directory_fd, _name: None,
        ) as workspace:
            creator_descriptor = next(call[1] for call in fake.calls if call[0] == "acquire_lock")
            fake.release_lock = failing_release  # type: ignore[method-assign]
            monkeypatch.setattr(filesystem.os, "close", close_creator_reuse_raise)
            workspace.publish("durable-after-creator-teardown")
        assert workspace.staging.state == "published"
        assert (tmp_path / "durable-after-creator-teardown").is_dir()
        assert creator_close_calls == 1
        assert replacement_fd is not None
        os.fstat(replacement_fd)
    finally:
        if replacement_fd is not None:
            real_close(replacement_fd)
        real_close(parent_fd)


def test_unsupported_probe_error_survives_cleanup_and_creator_release_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging_descriptor = -1

    def unsupported_probe(
        _results_root_fd: int,
        staging: filesystem.OwnedStaging,
        *,
        posix: filesystem.FilesystemPosixOps,
        contention_probe: filesystem.ContentionProbe | None = None,
    ) -> FilesystemIdentity:
        del posix, contention_probe
        nonlocal staging_descriptor
        staging_descriptor = staging.descriptor
        fake.fsync_error_for.add(staging.descriptor)
        raise UnsupportedFilesystemError("capability_probe_failed")

    def failing_release(descriptor: int) -> None:
        fake.calls.append(("release_lock", descriptor))
        raise OSError(errno.EIO, "creator release failure")

    fake.release_lock = failing_release  # type: ignore[method-assign]
    monkeypatch.setattr(filesystem, "run_filesystem_probes", unsupported_probe)
    try:
        with (
            pytest.raises(UnsupportedFilesystemError) as caught,
            preparation_filesystem(
                parent_fd,
                UUID("12345678-1234-4abc-9234-1234567890ab"),
                posix=fake,
            ),
        ):
            pytest.fail("unsupported probe yielded a workspace")
        assert caught.value.code == "unsupported_filesystem"
        assert caught.value.reason == "capability_probe_failed"
        assert caught.value.__notes__ == [
            "filesystem cleanup also failed",
            "filesystem lock release also failed",
        ]
        with pytest.raises(OSError):
            os.fstat(staging_descriptor)
    finally:
        os.close(parent_fd)


def test_cleanup_parent_fsync_error_survives_ambiguous_stage_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    fake.fsync_error_for.add(parent_fd)
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )
    real_close = os.close
    close_calls = 0

    def close_stage_raise(descriptor: int) -> None:
        nonlocal close_calls
        assert descriptor == staging.descriptor
        close_calls += 1
        real_close(descriptor)
        raise OSError(errno.EBADF, "ambiguous stage close")

    try:
        monkeypatch.setattr(filesystem.os, "close", close_stage_raise)
        with pytest.raises(OSError) as caught:
            cleanup_owned_staging(staging, posix=fake)
        assert caught.value.errno == errno.EIO
        assert caught.value.__notes__ == ["filesystem descriptor close also failed"]
        assert staging.state == "removed"
        assert close_calls == 1
        assert not (tmp_path / staging.name).exists()
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
    finally:
        real_close(parent_fd)


def test_publication_error_survives_cleanup_failure(tmp_path: Path) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    staging = create_owned_staging(
        parent_fd,
        UUID("12345678-1234-4abc-9234-1234567890ab"),
    )

    def failing_rename(
        _source_directory_fd: int,
        _source_name: str,
        _target_directory_fd: int,
        _target_name: str,
    ) -> None:
        raise OSError(errno.EIO, "publication failure")

    fake.rename_noreplace = failing_rename  # type: ignore[method-assign]
    fake.fsync_error_for.add(staging.descriptor)
    try:
        with pytest.raises(OwnedStagingError) as caught:
            publish_owned_staging(staging, "destination", posix=fake)
        assert caught.value.code == "publication_failed"
        assert caught.value.__notes__ == ["filesystem cleanup also failed"]
        assert staging.state == "abandoned"
        assert not (tmp_path / "destination").exists()
        with pytest.raises(OSError):
            os.fstat(staging.descriptor)
    finally:
        os.close(parent_fd)


@pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="POSIX-only fork")
def test_lock_probe_kills_and_reaps_sigterm_ignoring_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "probe-lock"
    lock_path.write_bytes(b"")
    directory_fd = _directory_fd(tmp_path)
    real_fork = os.fork
    real_waitpid = os.waitpid
    spawned_pids: list[int] = []

    def tracking_fork() -> int:
        child_pid = real_fork()
        if child_pid > 0:
            spawned_pids.append(child_pid)
        return child_pid

    def unresponsive_child(
        _directory_fd: int,
        _name: str,
        _inherited_parent_lock_fd: int,
        opened: Any,
        attempt: Any,
        released: Any,
        _sender: Any,
    ) -> None:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        opened.set()
        attempt.wait()
        released.wait()

    monkeypatch.setattr(filesystem, "_PROCESS_HANDSHAKE_SECONDS", 0.05)
    monkeypatch.setattr(filesystem, "_probe_child", unresponsive_child)
    monkeypatch.setattr(filesystem.os, "fork", tracking_fork)
    try:
        with pytest.raises(UnsupportedFilesystemError) as caught:
            probe_second_process_lock(directory_fd, "probe-lock")
        assert caught.value.reason == "lock_probe_timeout"
        assert len(spawned_pids) == 1
        with pytest.raises(ProcessLookupError):
            os.kill(spawned_pids[0], 0)
        with pytest.raises(ChildProcessError):
            real_waitpid(spawned_pids[0], os.WNOHANG)
    finally:
        for child_pid in spawned_pids:
            with suppress(ProcessLookupError):
                os.kill(child_pid, signal.SIGKILL)
            with suppress(ChildProcessError):
                real_waitpid(child_pid, 0)
        os.close(directory_fd)


def test_lock_probe_uses_fork_and_reaps_child_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Endpoint:
        def __init__(self, connection: Any) -> None:
            self.connection = connection
            self.close_calls = 0

        def poll(self, timeout: float) -> bool:
            return self.connection.poll(timeout)

        def recv(self) -> tuple[str, int]:
            return self.connection.recv()

        def send(self, message: tuple[str, int]) -> None:
            self.connection.send(message)

        def close(self) -> None:
            self.close_calls += 1
            self.connection.close()

    real_context = filesystem.multiprocessing.get_context("fork")
    raw_receiver, raw_sender = real_context.Pipe(duplex=False)
    receiver = Endpoint(raw_receiver)
    sender = Endpoint(raw_sender)

    class Context:
        def Pipe(self, *, duplex: bool) -> tuple[Endpoint, Endpoint]:
            assert duplex is False
            return receiver, sender

        def Event(self) -> Any:
            return real_context.Event()

        def Process(self, *, target: Any, args: tuple[Any, ...]) -> Any:
            del target, args
            raise AssertionError("Process.start can lose an already-forked child PID")

    lock_path = tmp_path / "probe-lock"
    lock_path.write_bytes(b"")
    directory_fd = _directory_fd(tmp_path)
    monkeypatch.setattr(filesystem.multiprocessing, "get_context", lambda _kind: Context())
    try:
        evidence = probe_second_process_lock(directory_fd, "probe-lock")
        assert evidence.child_pid > 0
        assert receiver.close_calls == 1
        assert sender.close_calls == 1
        with pytest.raises(ChildProcessError):
            os.waitpid(evidence.child_pid, os.WNOHANG)
    finally:
        os.close(directory_fd)


def test_lock_probe_closes_pipe_endpoints_when_fork_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Endpoint:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class Event:
        pass

    receiver = Endpoint()
    sender = Endpoint()

    class Context:
        def Pipe(self, *, duplex: bool) -> tuple[Endpoint, Endpoint]:
            assert duplex is False
            return receiver, sender

        def Event(self) -> Event:
            return Event()

        def Process(self, *, target: Any, args: tuple[Any, ...]) -> Any:
            del target, args
            raise AssertionError("multiprocessing.Process must not be used")

    def failing_fork() -> int:
        raise OSError(errno.EAGAIN, "fork failed")

    lock_path = tmp_path / "probe-lock"
    lock_path.write_bytes(b"")
    directory_fd = _directory_fd(tmp_path)
    monkeypatch.setattr(filesystem.multiprocessing, "get_context", lambda _kind: Context())
    monkeypatch.setattr(filesystem.os, "fork", failing_fork)
    try:
        with pytest.raises(OSError, match="fork failed"):
            probe_second_process_lock(directory_fd, "probe-lock")
        assert receiver.close_calls == 1
        assert sender.close_calls == 1
    finally:
        os.close(directory_fd)


def test_lock_probe_reaps_authoritative_pid_when_parent_cleanup_raises_after_fork(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Endpoint:
        def __init__(self, connection: Any, *, fail_parent_close: bool = False) -> None:
            self.connection = connection
            self.fail_parent_close = fail_parent_close
            self.close_calls = 0

        def poll(self, timeout: float) -> bool:
            return self.connection.poll(timeout)

        def recv(self) -> tuple[str, int]:
            return self.connection.recv()

        def send(self, message: tuple[str, int]) -> None:
            self.connection.send(message)

        def close(self) -> None:
            self.close_calls += 1
            self.connection.close()
            if self.fail_parent_close and os.getpid() == parent_pid:
                raise OSError(errno.EIO, "ambiguous parent pipe close")

    parent_pid = os.getpid()
    real_context = filesystem.multiprocessing.get_context("fork")
    raw_receiver, raw_sender = real_context.Pipe(duplex=False)
    receiver = Endpoint(raw_receiver)
    sender = Endpoint(raw_sender, fail_parent_close=True)
    real_fork = os.fork
    real_waitpid = os.waitpid
    spawned_pids: list[int] = []

    def tracking_fork() -> int:
        child_pid = real_fork()
        if child_pid > 0:
            spawned_pids.append(child_pid)
        return child_pid

    class LostPidProcess:
        def __init__(self, target: Any, args: tuple[Any, ...]) -> None:
            del target, args

        def start(self) -> None:
            child_pid = real_fork()
            if child_pid == 0:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                while True:
                    signal.pause()
            spawned_pids.append(child_pid)
            raise OSError(errno.EIO, "ambiguous process start")

        def close(self) -> None:
            return None

    class Context:
        def Pipe(self, *, duplex: bool) -> tuple[Endpoint, Endpoint]:
            assert duplex is False
            return receiver, sender

        def Event(self) -> Any:
            return real_context.Event()

        def Process(self, *, target: Any, args: tuple[Any, ...]) -> LostPidProcess:
            return LostPidProcess(target, args)

    lock_path = tmp_path / "probe-lock"
    lock_path.write_bytes(b"")
    directory_fd = _directory_fd(tmp_path)
    monkeypatch.setattr(filesystem.multiprocessing, "get_context", lambda _kind: Context())
    monkeypatch.setattr(filesystem.os, "fork", tracking_fork)
    try:
        with pytest.raises(OSError):
            probe_second_process_lock(directory_fd, "probe-lock")
        assert len(spawned_pids) == 1
        with pytest.raises(ProcessLookupError):
            os.kill(spawned_pids[0], 0)
        with pytest.raises(ChildProcessError):
            real_waitpid(spawned_pids[0], os.WNOHANG)
        assert receiver.close_calls == 1
        assert sender.close_calls == 1
    finally:
        for child_pid in spawned_pids:
            with suppress(ProcessLookupError):
                os.kill(child_pid, signal.SIGKILL)
            with suppress(ChildProcessError):
                real_waitpid(child_pid, 0)
        os.close(directory_fd)


def test_probe_cleanup_never_signals_an_externally_reaped_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_pid = os.fork()
    if child_pid == 0:
        os._exit(0)
    os.waitpid(child_pid, 0)
    signals: list[tuple[int, int]] = []

    class Receiver:
        def poll(self, _timeout: float) -> bool:
            raise AssertionError("not-child status must stop before pipe polling")

    def recording_kill(process_id: int, signal_number: int) -> None:
        signals.append((process_id, signal_number))

    monkeypatch.setattr(filesystem.os, "kill", recording_kill)
    filesystem._terminate_probe_child(child_pid, Receiver())
    assert signals == []


def test_probe_cleanup_retries_blocking_waitpid_after_sigkill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_pid = 4242
    waitpid_calls: list[tuple[int, int]] = []
    signals: list[tuple[int, int]] = []
    blocking_attempts = 0

    class Receiver:
        def poll(self, _timeout: float) -> bool:
            return False

    def fake_waitpid(process_id: int, options: int) -> tuple[int, int]:
        nonlocal blocking_attempts
        waitpid_calls.append((process_id, options))
        assert process_id == child_pid
        if options == os.WNOHANG:
            return (0, 0)
        assert options == 0
        blocking_attempts += 1
        if blocking_attempts == 1:
            raise InterruptedError
        return (child_pid, signal.SIGKILL)

    def recording_kill(process_id: int, signal_number: int) -> None:
        signals.append((process_id, signal_number))

    monkeypatch.setattr(filesystem, "_PROCESS_HANDSHAKE_SECONDS", 0.0)
    monkeypatch.setattr(filesystem.os, "waitpid", fake_waitpid)
    monkeypatch.setattr(filesystem.os, "kill", recording_kill)
    filesystem._terminate_probe_child(child_pid, Receiver())

    assert signals == [
        (child_pid, signal.SIGTERM),
        (child_pid, signal.SIGKILL),
    ]
    assert waitpid_calls[-2:] == [(child_pid, 0), (child_pid, 0)]


def test_probe_cleanup_kills_owned_child_when_grace_channel_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_reader, ready_writer = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:
        os.close(ready_reader)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.write(ready_writer, b"1")
        os.close(ready_writer)
        while True:
            signal.pause()
    os.close(ready_writer)
    assert os.read(ready_reader, 1) == b"1"
    os.close(ready_reader)
    real_kill = os.kill
    real_waitpid = os.waitpid
    signals: list[tuple[int, int]] = []

    class BrokenReceiver:
        def poll(self, _timeout: float) -> bool:
            raise OSError(errno.EIO, "broken grace channel")

    def recording_kill(process_id: int, signal_number: int) -> None:
        signals.append((process_id, signal_number))
        real_kill(process_id, signal_number)

    monkeypatch.setattr(filesystem.os, "kill", recording_kill)
    try:
        outcome = filesystem._terminate_probe_child(child_pid, BrokenReceiver())
        assert outcome.state == "reaped"
        assert signals == [
            (child_pid, signal.SIGTERM),
            (child_pid, signal.SIGKILL),
        ]
        with pytest.raises(ProcessLookupError):
            real_kill(child_pid, 0)
        with pytest.raises(ChildProcessError):
            real_waitpid(child_pid, os.WNOHANG)
    finally:
        with suppress(ProcessLookupError):
            real_kill(child_pid, signal.SIGKILL)
        with suppress(ChildProcessError):
            real_waitpid(child_pid, 0)


@pytest.mark.parametrize("failure_phase", ["pipe", "event"])
def test_lock_probe_closes_constructed_resources_when_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    class Endpoint:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class Event:
        pass

    receiver = Endpoint()
    sender = Endpoint()

    class Context:
        def Pipe(self, *, duplex: bool) -> tuple[Endpoint, Endpoint]:
            assert duplex is False
            if failure_phase == "pipe":
                raise OSError(errno.EMFILE, "pipe construction failed")
            return receiver, sender

        def Event(self) -> Event:
            if failure_phase == "event":
                raise OSError(errno.ENOMEM, "event construction failed")
            return Event()

        def Process(self, *, target: Any, args: tuple[Any, ...]) -> Any:
            del target, args
            raise AssertionError("multiprocessing.Process must not be used")

    lock_path = tmp_path / "probe-lock"
    lock_path.write_bytes(b"")
    directory_fd = _directory_fd(tmp_path)
    real_open = os.open
    real_close = os.close
    probe_descriptor = -1

    def tracking_open(path: object, *args: Any, **kwargs: Any) -> int:
        nonlocal probe_descriptor
        descriptor = real_open(path, *args, **kwargs)
        if path == "probe-lock":
            probe_descriptor = descriptor
        return descriptor

    monkeypatch.setattr(filesystem.os, "open", tracking_open)
    monkeypatch.setattr(filesystem.multiprocessing, "get_context", lambda _kind: Context())
    try:
        with pytest.raises(OSError):
            probe_second_process_lock(directory_fd, "probe-lock")
        assert probe_descriptor >= 0
        with pytest.raises(OSError):
            os.fstat(probe_descriptor)
        expected_endpoint_closes = 0 if failure_phase == "pipe" else 1
        assert receiver.close_calls == expected_endpoint_closes
        assert sender.close_calls == expected_endpoint_closes
    finally:
        if probe_descriptor >= 0:
            with suppress(OSError):
                real_close(probe_descriptor)
        real_close(directory_fd)


def test_each_preparation_runs_fresh_probes_in_exact_creator_lock_window(
    tmp_path: Path,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _darwin_fake()
    operation_ids = (
        UUID("12345678-1234-4abc-9234-1234567890ab"),
        UUID("87654321-4321-4cba-a432-ba0987654321"),
    )
    destinations = ("first-destination", "second-destination")
    try:
        for operation_id, destination in zip(operation_ids, destinations, strict=True):
            start = len(fake.calls)

            def contention(directory_fd: int, name: str) -> None:
                fake.calls.append(("contention", directory_fd, name))

            with preparation_filesystem(
                parent_fd,
                operation_id,
                posix=fake,
                contention_probe=contention,
            ) as workspace:
                workspace.publish(destination)
            calls = fake.calls[start:]

            acquire_index = next(i for i, call in enumerate(calls) if call[0] == "acquire_lock")
            release_index = next(i for i, call in enumerate(calls) if call[0] == "release_lock")
            classification_indices = [i for i, call in enumerate(calls) if call[0] == "fstatfs"]
            contention_index = next(i for i, call in enumerate(calls) if call[0] == "contention")
            rename_indices = [i for i, call in enumerate(calls) if call[0] == "rename_noreplace"]
            link_indices = [i for i, call in enumerate(calls) if call[0] == "link_noreplace"]
            file_fsync_indices = [
                i for i, call in enumerate(calls) if call[0] == "fsync" and call[2] == "file"
            ]
            directory_fsync_indices = [
                i
                for i, call in enumerate(calls)
                if call[0] == "fsync" and call[2] == "directory" and call[1] != parent_fd
            ]
            root_fsync_index = max(
                i for i, call in enumerate(calls) if call[0] == "fsync" and call[1] == parent_fd
            )

            assert classification_indices[0] < acquire_index < classification_indices[1]
            assert len(classification_indices) >= 5
            assert len(rename_indices) == 4
            assert len(link_indices) == 2
            assert len(file_fsync_indices) == 1
            assert directory_fsync_indices
            assert acquire_index < contention_index
            assert contention_index < min(link_indices)
            assert max(link_indices) < rename_indices[-1]
            assert max(file_fsync_indices) < rename_indices[-1]
            assert max(directory_fsync_indices) < rename_indices[-1]
            assert rename_indices[-1] < root_fsync_index < release_index
            assert (tmp_path / destination).is_dir()
    finally:
        os.close(parent_fd)


def test_unsupported_preparation_root_performs_no_lock_or_staging_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_fd = _directory_fd(tmp_path)
    fake = _linux_fake(parent_fd, magic=0x794C7630, filesystem_type="overlay")
    mkdir_calls: list[tuple[object, ...]] = []
    real_mkdir = os.mkdir

    def tracking_mkdir(*args: Any, **kwargs: Any) -> None:
        mkdir_calls.append(args)
        real_mkdir(*args, **kwargs)

    try:
        monkeypatch.setattr(filesystem.os, "mkdir", tracking_mkdir)
        with (
            pytest.raises(UnsupportedFilesystemError),
            preparation_filesystem(
                parent_fd,
                UUID("12345678-1234-4abc-9234-1234567890ab"),
                posix=fake,
                contention_probe=lambda _directory_fd, _name: None,
            ),
        ):
            pytest.fail("unsupported root yielded a workspace")
        assert mkdir_calls == []
        assert not any(
            call[0] in {"acquire_lock", "rename_noreplace", "link_noreplace", "fsync"}
            for call in fake.calls
        )
        assert list(tmp_path.iterdir()) == []
    finally:
        os.close(parent_fd)
