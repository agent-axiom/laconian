from __future__ import annotations

import ast
import ctypes
import errno
import fcntl
import inspect
import os
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import laconian_eval.capsule.posix as posix
from laconian_eval.capsule.posix import (
    AT_EMPTY_PATH,
    DEFAULT_MOUNTINFO_BYTE_LIMIT,
    MAX_MOUNTINFO_INTERRUPTS,
    RENAME_EXCL,
    RENAME_NOREPLACE,
    STATX_MNT_ID,
    FileSystemStat,
    MountIdentity,
    PosixDataError,
    PosixOps,
    PosixUnsupportedError,
    UnsupportedPlatformError,
    _DarwinStatFs,
    _LinuxStatFs,
    _LinuxStatx,
)


class FakeCFunction:
    def __init__(self, implementation: Callable[..., int]) -> None:
        self.implementation = implementation
        self.calls: list[tuple[Any, ...]] = []
        self.argtypes: list[object] | None = None
        self.restype: object | None = None

    def __call__(self, *args: Any) -> int:
        self.calls.append(args)
        return self.implementation(*args)


def _succeed(*_args: object) -> int:
    return 0


def _linux_libc() -> SimpleNamespace:
    def fstatfs(_descriptor: int, output: object) -> int:
        value = _LinuxStatFs()
        value.f_type = 0xEF53
        ctypes.memmove(output, ctypes.byref(value), ctypes.sizeof(value))
        return 0

    def statx(
        _descriptor: int,
        _path: bytes,
        _flags: int,
        _mask: int,
        output: object,
    ) -> int:
        value = _LinuxStatx()
        value.stx_mask = STATX_MNT_ID
        value.stx_dev_major = 8
        value.stx_dev_minor = 1
        value.stx_mnt_id = 42
        ctypes.memmove(output, ctypes.byref(value), ctypes.sizeof(value))
        return 0

    return SimpleNamespace(
        fstatfs=FakeCFunction(fstatfs),
        statx=FakeCFunction(statx),
        renameat2=FakeCFunction(_succeed),
        linkat=FakeCFunction(_succeed),
    )


def _darwin_libc() -> SimpleNamespace:
    def fstatfs(_descriptor: int, output: object) -> int:
        value = _DarwinStatFs()
        value.f_flags = 0x1000
        value.f_fstypename = b"apfs"
        ctypes.memmove(output, ctypes.byref(value), ctypes.sizeof(value))
        return 0

    return SimpleNamespace(
        fstatfs=FakeCFunction(fstatfs),
        renameatx_np=FakeCFunction(_succeed),
        linkat=FakeCFunction(_succeed),
    )


def test_linux_fstatfs_uses_the_exact_64_bit_abi_and_returns_magic() -> None:
    libc = _linux_libc()
    ops = PosixOps(platform="linux", libc=libc)

    result = ops.fstatfs(17)

    assert result == FileSystemStat(
        platform="linux",
        type_magic=0xEF53,
        type_name=None,
        flags=0,
    )
    assert ctypes.sizeof(_LinuxStatFs) == 120
    assert _LinuxStatFs.f_type.offset == 0
    assert libc.fstatfs.calls[0][0] == 17
    assert libc.fstatfs.argtypes == [ctypes.c_int, ctypes.POINTER(_LinuxStatFs)]
    assert libc.fstatfs.restype is ctypes.c_int


def test_linux_statx_uses_empty_path_and_returns_descriptor_mount_identity() -> None:
    libc = _linux_libc()
    ops = PosixOps(platform="linux", libc=libc)

    result = ops.statx_mount_identity(29)

    assert result == MountIdentity(mount_id=42, device_major=8, device_minor=1)
    descriptor, path, flags, mask, _output = libc.statx.calls[0]
    assert descriptor == 29
    assert path == b""
    assert flags == AT_EMPTY_PATH
    assert mask == STATX_MNT_ID
    assert ctypes.sizeof(_LinuxStatx) == 256
    assert _LinuxStatx.stx_mnt_id.offset == 144
    assert libc.statx.argtypes == [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(_LinuxStatx),
    ]
    assert libc.statx.restype is ctypes.c_int


def test_linux_statx_fails_closed_when_kernel_omits_mount_id() -> None:
    libc = _linux_libc()

    def statx_without_mount_id(*args: object) -> int:
        value = _LinuxStatx()
        value.stx_mask = 0
        ctypes.memmove(args[-1], ctypes.byref(value), ctypes.sizeof(value))
        return 0

    libc.statx = FakeCFunction(statx_without_mount_id)
    ops = PosixOps(platform="linux", libc=libc)

    with pytest.raises(PosixUnsupportedError) as caught:
        ops.statx_mount_identity(29)
    assert caught.value.code == "statx_mount_id_unavailable"
    assert str(caught.value) == "POSIX operation is unsupported"


def test_linux_rename_is_descriptor_relative_and_exclusive() -> None:
    libc = _linux_libc()
    ops = PosixOps(platform="linux", libc=libc)

    ops.rename_noreplace(3, "source", 4, "destination")

    assert libc.renameat2.calls == [(3, b"source", 4, b"destination", RENAME_NOREPLACE)]
    assert libc.renameat2.argtypes == [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    assert libc.renameat2.restype is ctypes.c_int


def test_darwin_fstatfs_uses_the_exact_64_bit_abi_and_returns_type_and_flags() -> None:
    libc = _darwin_libc()
    inode64_calls: list[tuple[Any, ...]] = []
    setattr(
        libc,
        "fstatfs$INODE64",
        FakeCFunction(lambda *args: inode64_calls.append(args) or 0),
    )
    ops = PosixOps(platform="darwin", machine="arm64", libc=libc)

    result = ops.fstatfs(17)

    assert result == FileSystemStat(
        platform="darwin",
        type_magic=None,
        type_name="apfs",
        flags=0x1000,
    )
    assert ctypes.sizeof(_DarwinStatFs) == 2168
    assert _DarwinStatFs.f_flags.offset == 64
    assert _DarwinStatFs.f_fstypename.offset == 72
    assert libc.fstatfs.argtypes == [ctypes.c_int, ctypes.POINTER(_DarwinStatFs)]
    assert libc.fstatfs.restype is ctypes.c_int
    assert inode64_calls == []


def test_darwin_fstatfs_accepts_the_x86_64_inode64_abi_symbol() -> None:
    libc = _darwin_libc()
    plain_fstatfs = libc.fstatfs
    inode64_fstatfs = FakeCFunction(plain_fstatfs.implementation)
    setattr(libc, "fstatfs$INODE64", inode64_fstatfs)
    ops = PosixOps(platform="darwin", machine="x86_64", libc=libc)

    assert ops.fstatfs(17).type_name == "apfs"
    assert inode64_fstatfs.calls[0][0] == 17
    assert plain_fstatfs.calls == []


@pytest.mark.parametrize(
    ("machine", "libc"),
    [
        ("arm64", SimpleNamespace(**{"fstatfs$INODE64": FakeCFunction(_succeed)})),
        ("x86_64", _darwin_libc()),
    ],
)
def test_darwin_fstatfs_missing_exact_architecture_symbol_fails_closed(
    machine: str, libc: SimpleNamespace
) -> None:
    ops = PosixOps(platform="darwin", machine=machine, libc=libc)

    with pytest.raises(PosixUnsupportedError) as caught:
        ops.fstatfs(17)
    assert caught.value.code == "missing_fstatfs"


def test_darwin_rename_uses_only_descriptor_relative_renameatx_np() -> None:
    libc = _darwin_libc()
    path_based_calls: list[tuple[Any, ...]] = []
    libc.renamex_np = FakeCFunction(lambda *args: path_based_calls.append(args) or 0)
    ops = PosixOps(platform="darwin", machine="arm64", libc=libc)

    ops.rename_noreplace(5, "source", 6, "destination")

    assert libc.renameatx_np.calls == [(5, b"source", 6, b"destination", RENAME_EXCL)]
    assert libc.renameatx_np.argtypes == [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    assert libc.renameatx_np.restype is ctypes.c_int
    assert path_based_calls == []


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_hard_link_is_descriptor_relative_and_no_replace(platform: str) -> None:
    libc = _linux_libc() if platform == "linux" else _darwin_libc()
    ops = PosixOps(
        platform=platform,
        machine="arm64" if platform == "darwin" else None,
        libc=libc,
    )

    ops.link_noreplace(7, "temporary", 8, "seal.json")

    assert libc.linkat.calls == [(7, b"temporary", 8, b"seal.json", 0)]
    assert libc.linkat.argtypes == [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    assert libc.linkat.restype is ctypes.c_int


def test_advisory_locks_use_exact_shared_exclusive_nonblocking_and_unlock_flags() -> None:
    calls: list[tuple[int, int]] = []

    def flock_fn(descriptor: int, operation: int) -> None:
        calls.append((descriptor, operation))

    ops = PosixOps(platform="linux", libc=_linux_libc(), flock_fn=flock_fn)

    ops.acquire_lock(10, exclusive=True, blocking=True)
    ops.acquire_lock(11, exclusive=False, blocking=False)
    ops.release_lock(11)

    assert calls == [
        (10, fcntl.LOCK_EX),
        (11, fcntl.LOCK_SH | fcntl.LOCK_NB),
        (11, fcntl.LOCK_UN),
    ]


def test_fsync_uses_each_supplied_file_or_directory_descriptor() -> None:
    calls: list[int] = []
    ops = PosixOps(
        platform="linux",
        libc=_linux_libc(),
        fsync_fn=lambda descriptor: calls.append(descriptor),
    )

    ops.fsync(12)
    ops.fsync(13)

    assert calls == [12, 13]


def test_raw_operations_never_close_or_duplicate_caller_owned_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    duplicated: list[int] = []
    monkeypatch.setattr(posix.os, "close", lambda descriptor: closed.append(descriptor))
    monkeypatch.setattr(posix.os, "dup", lambda descriptor: duplicated.append(descriptor) or 99)
    ops = PosixOps(
        platform="linux",
        libc=_linux_libc(),
        flock_fn=lambda _descriptor, _operation: None,
        fsync_fn=lambda _descriptor: None,
    )

    ops.fstatfs(3)
    ops.statx_mount_identity(3)
    ops.rename_noreplace(3, "source", 4, "destination")
    ops.link_noreplace(3, "source", 4, "destination")
    ops.acquire_lock(3, exclusive=True, blocking=False)
    ops.release_lock(3)
    ops.fsync(3)

    assert closed == []
    assert duplicated == []


@pytest.mark.parametrize(
    ("errno_number", "error_type"),
    [
        (errno.EEXIST, FileExistsError),
        (errno.EAGAIN, BlockingIOError),
        (errno.EACCES, PermissionError),
        (errno.EXDEV, OSError),
        (errno.ENOSYS, OSError),
    ],
)
def test_ctypes_failures_preserve_errno_subclasses_without_content(
    errno_number: int, error_type: type[OSError]
) -> None:
    libc = _linux_libc()

    def fail(*_args: object) -> int:
        ctypes.set_errno(errno_number)
        return -1

    libc.renameat2 = FakeCFunction(fail)
    ops = PosixOps(platform="linux", libc=libc)

    with pytest.raises(error_type) as caught:
        ops.rename_noreplace(3, "private-source", 4, "private-destination")
    assert caught.value.errno == errno_number
    assert caught.value.filename is None
    assert caught.value.strerror == "POSIX operation failed"
    assert "private" not in repr(caught.value)


def test_ctypes_failure_without_fresh_errno_maps_to_io_error() -> None:
    libc = _linux_libc()
    libc.renameat2 = FakeCFunction(lambda *_args: -1)
    ctypes.set_errno(errno.EEXIST)
    ops = PosixOps(platform="linux", libc=libc)

    with pytest.raises(OSError) as caught:
        ops.rename_noreplace(3, "source", 4, "destination")
    assert caught.value.errno == errno.EIO
    assert caught.value.strerror == "POSIX operation failed"


def test_ctypes_errno_is_captured_before_return_value_comparison() -> None:
    class ErrnoClobberingFailure:
        def __ne__(self, other: object) -> bool:
            assert other == 0
            ctypes.set_errno(errno.EACCES)
            return True

    libc = _linux_libc()

    def fail(*_args: object) -> int:
        ctypes.set_errno(errno.EEXIST)
        return ErrnoClobberingFailure()  # type: ignore[return-value]

    libc.renameat2 = FakeCFunction(fail)
    ops = PosixOps(platform="linux", libc=libc)

    with pytest.raises(FileExistsError) as caught:
        ops.rename_noreplace(3, "source", 4, "destination")
    assert caught.value.errno == errno.EEXIST


def test_python_os_errors_are_remapped_without_leaking_the_original_message() -> None:
    def fsync_fn(_descriptor: int) -> None:
        raise OSError(errno.EIO, "private target failed")

    ops = PosixOps(
        platform="darwin",
        machine="arm64",
        libc=_darwin_libc(),
        fsync_fn=fsync_fn,
    )

    with pytest.raises(OSError) as caught:
        ops.fsync(12)
    assert caught.value.errno == errno.EIO
    assert caught.value.strerror == "POSIX operation failed"
    assert "private target" not in str(caught.value)


def test_nonblocking_lock_contention_remains_blocking_io_error() -> None:
    def flock_fn(_descriptor: int, _operation: int) -> None:
        raise BlockingIOError(errno.EWOULDBLOCK, "private lock")

    ops = PosixOps(platform="linux", libc=_linux_libc(), flock_fn=flock_fn)

    with pytest.raises(BlockingIOError) as caught:
        ops.acquire_lock(10, exclusive=True, blocking=False)
    assert caught.value.errno == errno.EWOULDBLOCK
    assert caught.value.strerror == "POSIX operation failed"


def test_mountinfo_returns_exact_bounded_bytes_from_one_owned_descriptor() -> None:
    raw = b"24 1 8:1 / / rw - ext4 /dev/root rw\n"
    opened: list[tuple[str, int]] = []
    reads: list[tuple[int, int]] = []
    closed: list[int] = []
    chunks = iter([raw, b""])

    def open_fn(path: str, flags: int) -> int:
        opened.append((path, flags))
        return 71

    def read_fn(descriptor: int, count: int) -> bytes:
        reads.append((descriptor, count))
        return next(chunks)

    ops = PosixOps(
        platform="linux",
        libc=_linux_libc(),
        mountinfo_open_fn=open_fn,
        mountinfo_read_fn=read_fn,
        mountinfo_close_fn=lambda descriptor: closed.append(descriptor),
    )

    assert ops.read_mountinfo(64) == raw
    assert opened == [("/proc/self/mountinfo", os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))]
    assert reads == [(71, 65), (71, 64 - len(raw) + 1)]
    assert closed == [71]


def test_mountinfo_default_limit_is_bounded_and_oversize_content_is_rejected() -> None:
    read_counts: list[int] = []
    chunks = iter([b"x" * 65, b""])

    def read_fn(_descriptor: int, count: int) -> bytes:
        read_counts.append(count)
        return next(chunks)

    ops = PosixOps(
        platform="linux",
        libc=_linux_libc(),
        mountinfo_open_fn=lambda _path, _flags: 72,
        mountinfo_read_fn=read_fn,
        mountinfo_close_fn=lambda _descriptor: None,
    )
    assert DEFAULT_MOUNTINFO_BYTE_LIMIT >= 64
    assert ops.read_mountinfo() == b"x" * 65
    assert 0 < read_counts[0] <= DEFAULT_MOUNTINFO_BYTE_LIMIT + 1

    chunks = iter([b"x" * 65])
    with pytest.raises(PosixDataError) as caught:
        ops.read_mountinfo(64)
    assert caught.value.code == "mountinfo_too_large"
    assert str(caught.value) == "POSIX data is invalid"
    assert read_counts[-1] == 65


def test_mountinfo_reader_bounds_interrupted_reads_and_closes_once() -> None:
    attempts = 0
    closes = 0

    def read_fn(_descriptor: int, _count: int) -> bytes:
        nonlocal attempts
        attempts += 1
        raise InterruptedError(errno.EINTR, "private")

    def close_fn(_descriptor: int) -> None:
        nonlocal closes
        closes += 1

    ops = PosixOps(
        platform="linux",
        libc=_linux_libc(),
        mountinfo_open_fn=lambda _path, _flags: 73,
        mountinfo_read_fn=read_fn,
        mountinfo_close_fn=close_fn,
    )

    with pytest.raises(InterruptedError) as caught:
        ops.read_mountinfo(64)
    assert attempts == MAX_MOUNTINFO_INTERRUPTS + 1
    assert closes == 1
    assert caught.value.errno == errno.EINTR
    assert caught.value.strerror == "POSIX operation failed"


def test_mountinfo_reader_never_retries_an_ambiguous_close() -> None:
    closes = 0

    def close_fn(_descriptor: int) -> None:
        nonlocal closes
        closes += 1
        raise OSError(errno.EIO, "private")

    ops = PosixOps(
        platform="linux",
        libc=_linux_libc(),
        mountinfo_open_fn=lambda _path, _flags: 74,
        mountinfo_read_fn=lambda _descriptor, _count: b"",
        mountinfo_close_fn=close_fn,
    )

    with pytest.raises(OSError) as caught:
        ops.read_mountinfo(64)
    assert closes == 1
    assert caught.value.errno == errno.EIO
    assert caught.value.strerror == "POSIX operation failed"


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        "nested/name",
        "nul\0name",
        "surrogate\ud800",
        *(f"control{chr(code)}name" for code in range(0x20)),
        *(f"control{chr(code)}name" for code in range(0x7F, 0xA0)),
    ],
)
def test_descriptor_relative_operations_reject_non_leaf_or_control_names(value: str) -> None:
    assert value in {"", ".", "..", "nested/name", "nul\0name", "surrogate\ud800"} or any(
        unicodedata.category(character) == "Cc" for character in value
    )
    ops = PosixOps(platform="linux", libc=_linux_libc())

    with pytest.raises(PosixDataError) as caught:
        ops.rename_noreplace(3, value, 4, "target")
    assert caught.value.code == "invalid_name"
    assert str(caught.value) == "POSIX data is invalid"
    if value:
        assert value not in str(caught.value)


@pytest.mark.parametrize("descriptor", [-1, True, 1.5, "3"])
def test_raw_operations_reject_invalid_descriptors(descriptor: object) -> None:
    ops = PosixOps(platform="linux", libc=_linux_libc())

    with pytest.raises(PosixDataError) as caught:
        ops.fstatfs(descriptor)  # type: ignore[arg-type]
    assert caught.value.code == "invalid_descriptor"


@pytest.mark.parametrize(
    ("exclusive", "blocking"),
    [(1, True), (True, 0), (None, False)],
)
def test_lock_modes_require_actual_booleans(exclusive: object, blocking: object) -> None:
    ops = PosixOps(platform="linux", libc=_linux_libc())

    with pytest.raises(PosixDataError) as caught:
        ops.acquire_lock(3, exclusive=exclusive, blocking=blocking)  # type: ignore[arg-type]
    assert caught.value.code == "invalid_lock_mode"


def test_platform_specific_operations_and_missing_symbols_fail_closed() -> None:
    with pytest.raises(UnsupportedPlatformError) as caught:
        PosixOps(platform="win32", libc=SimpleNamespace())
    assert caught.value.code == "unsupported_platform"
    assert str(caught.value) == "POSIX platform is unsupported"

    darwin = PosixOps(platform="darwin", machine="arm64", libc=_darwin_libc())
    with pytest.raises(PosixUnsupportedError) as statx_caught:
        darwin.statx_mount_identity(3)
    assert statx_caught.value.code == "statx_linux_only"
    with pytest.raises(PosixUnsupportedError) as mountinfo_caught:
        darwin.read_mountinfo()
    assert mountinfo_caught.value.code == "mountinfo_linux_only"

    linux = PosixOps(platform="linux", libc=SimpleNamespace())
    with pytest.raises(PosixUnsupportedError) as symbol_caught:
        linux.rename_noreplace(3, "source", 4, "destination")
    assert symbol_caught.value.code == "missing_renameat2"


def test_unsupported_linux_word_size_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_sizeof = ctypes.sizeof

    def short_long(value: object) -> int:
        if value is ctypes.c_long:
            return 4
        return real_sizeof(value)  # type: ignore[arg-type]

    monkeypatch.setattr(posix.ctypes, "sizeof", short_long)

    with pytest.raises(PosixUnsupportedError) as caught:
        PosixOps(platform="linux", libc=_linux_libc())
    assert caught.value.code == "unsupported_linux_abi"


def test_unsupported_darwin_word_size_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    real_sizeof = ctypes.sizeof

    def short_pointer(value: object) -> int:
        if value is ctypes.c_void_p:
            return 4
        return real_sizeof(value)  # type: ignore[arg-type]

    monkeypatch.setattr(posix.ctypes, "sizeof", short_pointer)

    with pytest.raises(PosixUnsupportedError) as caught:
        PosixOps(platform="darwin", machine="arm64", libc=_darwin_libc())
    assert caught.value.code == "unsupported_darwin_abi"


def test_unsupported_darwin_machine_fails_closed() -> None:
    with pytest.raises(PosixUnsupportedError) as caught:
        PosixOps(platform="darwin", machine="powerpc", libc=_darwin_libc())
    assert caught.value.code == "unsupported_darwin_abi"


def test_default_libc_is_loaded_with_thread_local_errno_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, bool]] = []
    assert sys.platform in {"linux", "darwin"}
    libc = _linux_libc() if sys.platform == "linux" else _darwin_libc()

    def cdll(name: object, *, use_errno: bool) -> object:
        calls.append((name, use_errno))
        return libc

    monkeypatch.setattr(posix.ctypes, "CDLL", cdll)

    PosixOps(platform=sys.platform)
    assert calls == [(None, True)]


def test_default_libc_rejects_foreign_platform_before_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sys.platform in {"linux", "darwin"}
    foreign_platform = "darwin" if sys.platform == "linux" else "linux"
    foreign_machine = "arm64" if foreign_platform == "darwin" else None
    calls: list[tuple[object, bool]] = []

    def cdll(name: object, *, use_errno: bool) -> object:
        calls.append((name, use_errno))
        return _darwin_libc() if foreign_platform == "darwin" else _linux_libc()

    monkeypatch.setattr(posix.ctypes, "CDLL", cdll)

    with pytest.raises(PosixUnsupportedError) as caught:
        PosixOps(platform=foreign_platform, machine=foreign_machine)
    assert caught.value.code == "foreign_platform_abi"
    assert str(caught.value) == "POSIX operation is unsupported"
    assert calls == []


def test_default_libc_rejects_foreign_darwin_machine_before_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, bool]] = []

    def cdll(name: object, *, use_errno: bool) -> object:
        calls.append((name, use_errno))
        return _darwin_libc()

    monkeypatch.setattr(posix.sys, "platform", "darwin")
    monkeypatch.setattr(posix.runtime_platform, "machine", lambda: "arm64")
    monkeypatch.setattr(posix.ctypes, "CDLL", cdll)

    with pytest.raises(PosixUnsupportedError) as caught:
        PosixOps(platform="darwin", machine="x86_64")
    assert caught.value.code == "foreign_darwin_machine_abi"
    assert str(caught.value) == "POSIX operation is unsupported"
    assert calls == []


def test_implementation_contains_no_ordinary_rename_or_path_based_macos_fallback() -> None:
    tree = ast.parse(inspect.getsource(posix))
    forbidden_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"rename", "replace"}
    }
    forbidden_symbols = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "renamex_np"
    }
    assert forbidden_attributes == set()
    assert forbidden_symbols == set()


@pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="supported POSIX host required")
def test_current_backend_executes_real_no_replace_link_lock_fsync_and_identity(
    tmp_path: Path,
) -> None:
    ops = PosixOps()
    source = tmp_path / "source"
    source.write_bytes(b"payload")
    source_fd = os.open(source, os.O_RDONLY)
    directory_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        ops.link_noreplace(directory_fd, "source", directory_fd, "linked")
        assert (tmp_path / "linked").read_bytes() == b"payload"
        with pytest.raises(FileExistsError):
            ops.link_noreplace(directory_fd, "source", directory_fd, "linked")

        (tmp_path / "staging").mkdir()
        ops.rename_noreplace(directory_fd, "staging", directory_fd, "published")
        assert (tmp_path / "published").is_dir()

        ops.acquire_lock(source_fd, exclusive=True, blocking=False)
        ops.release_lock(source_fd)
        ops.fsync(source_fd)
        ops.fsync(directory_fd)

        filesystem = ops.fstatfs(directory_fd)
        assert filesystem.platform == sys.platform
        if sys.platform == "linux":
            identity = ops.statx_mount_identity(directory_fd)
            assert identity.mount_id > 0
            assert ops.read_mountinfo()
        else:
            assert filesystem.type_name
    finally:
        os.close(source_fd)
        os.close(directory_fd)
