"""Fail-closed descriptor-relative POSIX syscall primitives.

This module deliberately stops below filesystem classification and capability probes.  Callers own
every descriptor they pass to :class:`PosixOps`; the only descriptor opened and closed here is the
module-owned, bounded ``/proc/self/mountinfo`` snapshot descriptor on Linux.
"""

from __future__ import annotations

import ctypes
import errno
import importlib
import os
import platform as runtime_platform
import sys
import unicodedata
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal, NoReturn, Protocol, cast

RENAME_NOREPLACE = 1
RENAME_EXCL = 0x00000004
AT_EMPTY_PATH = 0x00001000
STATX_MNT_ID = 0x00001000

DEFAULT_MOUNTINFO_BYTE_LIMIT = 1024 * 1024
MAX_MOUNTINFO_INTERRUPTS = 16
_MOUNTINFO_READ_CHUNK = 64 * 1024
_MOUNTINFO_PATH = "/proc/self/mountinfo"
_POSIX_ERROR_MESSAGE = "POSIX operation failed"
_C_INT_MAX = (1 << 31) - 1

_LOCK_SH = 1
_LOCK_EX = 2
_LOCK_NB = 4
_LOCK_UN = 8

Platform = Literal["linux", "darwin"]
DarwinMachine = Literal["arm64", "x86_64"]
FlockFunction = Callable[[int, int], object]
FsyncFunction = Callable[[int], object]
MountinfoOpenFunction = Callable[[str, int], int]
MountinfoReadFunction = Callable[[int, int], bytes]
MountinfoCloseFunction = Callable[[int], object]


class _LinuxFsid(ctypes.Structure):
    _fields_ = [("value", ctypes.c_int32 * 2)]


class _LinuxStatFs(ctypes.Structure):
    _fields_ = [
        ("f_type", ctypes.c_long),
        ("f_bsize", ctypes.c_long),
        ("f_blocks", ctypes.c_ulong),
        ("f_bfree", ctypes.c_ulong),
        ("f_bavail", ctypes.c_ulong),
        ("f_files", ctypes.c_ulong),
        ("f_ffree", ctypes.c_ulong),
        ("f_fsid", _LinuxFsid),
        ("f_namelen", ctypes.c_long),
        ("f_frsize", ctypes.c_long),
        ("f_flags", ctypes.c_long),
        ("f_spare", ctypes.c_long * 4),
    ]


class _LinuxStatxTimestamp(ctypes.Structure):
    _fields_ = [
        ("tv_sec", ctypes.c_int64),
        ("tv_nsec", ctypes.c_uint32),
        ("reserved", ctypes.c_int32),
    ]


class _LinuxStatx(ctypes.Structure):
    _fields_ = [
        ("stx_mask", ctypes.c_uint32),
        ("stx_blksize", ctypes.c_uint32),
        ("stx_attributes", ctypes.c_uint64),
        ("stx_nlink", ctypes.c_uint32),
        ("stx_uid", ctypes.c_uint32),
        ("stx_gid", ctypes.c_uint32),
        ("stx_mode", ctypes.c_uint16),
        ("spare0", ctypes.c_uint16 * 1),
        ("stx_ino", ctypes.c_uint64),
        ("stx_size", ctypes.c_uint64),
        ("stx_blocks", ctypes.c_uint64),
        ("stx_attributes_mask", ctypes.c_uint64),
        ("stx_atime", _LinuxStatxTimestamp),
        ("stx_btime", _LinuxStatxTimestamp),
        ("stx_ctime", _LinuxStatxTimestamp),
        ("stx_mtime", _LinuxStatxTimestamp),
        ("stx_rdev_major", ctypes.c_uint32),
        ("stx_rdev_minor", ctypes.c_uint32),
        ("stx_dev_major", ctypes.c_uint32),
        ("stx_dev_minor", ctypes.c_uint32),
        ("stx_mnt_id", ctypes.c_uint64),
        ("stx_dio_mem_align", ctypes.c_uint32),
        ("stx_dio_offset_align", ctypes.c_uint32),
        ("stx_subvol", ctypes.c_uint64),
        ("stx_atomic_write_unit_min", ctypes.c_uint32),
        ("stx_atomic_write_unit_max", ctypes.c_uint32),
        ("stx_atomic_write_segments_max", ctypes.c_uint32),
        ("stx_dio_read_offset_align", ctypes.c_uint32),
        ("spare3", ctypes.c_uint64 * 9),
    ]


class _DarwinFsid(ctypes.Structure):
    _fields_ = [("value", ctypes.c_int32 * 2)]


class _DarwinStatFs(ctypes.Structure):
    _fields_ = [
        ("f_bsize", ctypes.c_uint32),
        ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64),
        ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64),
        ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64),
        ("f_fsid", _DarwinFsid),
        ("f_owner", ctypes.c_uint32),
        ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32),
        ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * 16),
        ("f_mntonname", ctypes.c_char * 1024),
        ("f_mntfromname", ctypes.c_char * 1024),
        ("f_flags_ext", ctypes.c_uint32),
        ("f_reserved", ctypes.c_uint32 * 7),
    ]


class _CFunction(Protocol):
    argtypes: list[object] | None
    restype: object | None

    def __call__(self, *args: object) -> int: ...


class PosixDataError(ValueError):
    """A content-free validation failure with a stable machine code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("POSIX data is invalid")


class PosixUnsupportedError(RuntimeError):
    """A content-free unavailable-primitive failure with a stable machine code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("POSIX operation is unsupported")


class UnsupportedPlatformError(RuntimeError):
    """Raised when the actual or explicitly selected platform is unsupported."""

    def __init__(self) -> None:
        self.code = "unsupported_platform"
        super().__init__("POSIX platform is unsupported")


@dataclass(frozen=True, slots=True)
class FileSystemStat:
    """Raw platform filesystem identity returned for an open descriptor."""

    platform: Platform
    type_magic: int | None
    type_name: str | None
    flags: int


@dataclass(frozen=True, slots=True)
class MountIdentity:
    """Linux descriptor mount identity returned by ``statx``."""

    mount_id: int
    device_major: int
    device_minor: int


def _raise_sanitized_os_error(errno_number: int | None) -> NoReturn:
    saved_errno = errno.EIO if errno_number is None or errno_number <= 0 else errno_number
    raise OSError(saved_errno, _POSIX_ERROR_MESSAGE) from None


def _validate_descriptor(descriptor: int) -> int:
    if type(descriptor) is not int or not 0 <= descriptor <= _C_INT_MAX:
        raise PosixDataError("invalid_descriptor")
    return descriptor


def _validate_limit(limit: int) -> int:
    if type(limit) is not int or limit < 1 or limit > DEFAULT_MOUNTINFO_BYTE_LIMIT:
        raise PosixDataError("invalid_mountinfo_limit")
    return limit


def _encode_leaf(name: str) -> bytes:
    if type(name) is not str or name in {"", ".", ".."} or "/" in name:
        raise PosixDataError("invalid_name")
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in name):
        raise PosixDataError("invalid_name")
    try:
        return name.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise PosixDataError("invalid_name") from None


def _validate_platform_abi(platform: Platform) -> None:
    if platform == "linux":
        valid = (
            ctypes.sizeof(ctypes.c_long) == 8
            and ctypes.sizeof(ctypes.c_void_p) == 8
            and ctypes.sizeof(_LinuxStatFs) == 120
            and _LinuxStatFs.f_type.offset == 0
            and ctypes.sizeof(_LinuxStatx) == 256
            and _LinuxStatx.stx_mnt_id.offset == 144
        )
        if not valid:
            raise PosixUnsupportedError("unsupported_linux_abi")
        return
    valid = (
        ctypes.sizeof(ctypes.c_void_p) == 8
        and ctypes.sizeof(_DarwinStatFs) == 2168
        and _DarwinStatFs.f_flags.offset == 64
        and _DarwinStatFs.f_fstypename.offset == 72
    )
    if not valid:
        raise PosixUnsupportedError("unsupported_darwin_abi")


class PosixOps:
    """Injectable raw POSIX operations for Linux and macOS."""

    __slots__ = (
        "_flock",
        "_fsync",
        "_functions",
        "_libc",
        "_mountinfo_close",
        "_mountinfo_open",
        "_mountinfo_read",
        "_sealed",
        "machine",
        "platform",
    )

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("PosixOps is sealed")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        platform: str | None = None,
        *,
        machine: str | None = None,
        libc: object | None = None,
        flock_fn: FlockFunction | None = None,
        fsync_fn: FsyncFunction | None = None,
        mountinfo_open_fn: MountinfoOpenFunction | None = None,
        mountinfo_read_fn: MountinfoReadFunction | None = None,
        mountinfo_close_fn: MountinfoCloseFunction | None = None,
    ) -> None:
        selected = sys.platform if platform is None else platform
        if selected not in {"linux", "darwin"}:
            raise UnsupportedPlatformError
        self.platform = cast(Platform, selected)
        self.machine: DarwinMachine | None = None
        if self.platform == "darwin":
            selected_machine = runtime_platform.machine() if machine is None else machine
            if selected_machine not in {"arm64", "x86_64"}:
                raise PosixUnsupportedError("unsupported_darwin_abi")
            self.machine = cast(DarwinMachine, selected_machine)
        _validate_platform_abi(self.platform)

        if libc is None:
            if self.platform != sys.platform:
                raise PosixUnsupportedError("foreign_platform_abi")
            if self.platform == "darwin" and self.machine != runtime_platform.machine():
                raise PosixUnsupportedError("foreign_darwin_machine_abi")
            try:
                libc = ctypes.CDLL(None, use_errno=True)
            except OSError:
                raise PosixUnsupportedError("libc_unavailable") from None
        self._libc = libc
        self._functions: dict[str, _CFunction] = {}

        if flock_fn is None:
            try:
                flock_module = importlib.import_module("fcntl")
            except ImportError:
                raise PosixUnsupportedError("flock_unavailable") from None
            candidate = flock_module.__dict__.get("flock")
            if candidate is None or not callable(candidate):
                raise PosixUnsupportedError("flock_unavailable")
            flock_fn = cast(FlockFunction, candidate)
        self._flock = flock_fn
        self._fsync = os.fsync if fsync_fn is None else fsync_fn
        self._mountinfo_open = os.open if mountinfo_open_fn is None else mountinfo_open_fn
        self._mountinfo_read = os.read if mountinfo_read_fn is None else mountinfo_read_fn
        self._mountinfo_close = os.close if mountinfo_close_fn is None else mountinfo_close_fn
        object.__setattr__(self, "_sealed", True)

    def _bind(
        self,
        key: str,
        symbols: tuple[str, ...],
        argtypes: list[object],
        restype: object,
        *,
        missing_code: str,
    ) -> _CFunction:
        cached = self._functions.get(key)
        if cached is not None:
            return cached
        function: _CFunction | None = None
        for symbol in symbols:
            candidate = getattr(self._libc, symbol, None)
            if candidate is not None and callable(candidate):
                function = cast(_CFunction, candidate)
                break
        if function is None:
            raise PosixUnsupportedError(missing_code)
        try:
            function.argtypes = argtypes
            function.restype = restype
        except (AttributeError, TypeError):
            raise PosixUnsupportedError(missing_code) from None
        self._functions[key] = function
        return function

    @staticmethod
    def _call(function: _CFunction, *args: object) -> None:
        ctypes.set_errno(0)
        try:
            result = function(*args)
            saved_errno = ctypes.get_errno()
        except OSError as error:
            _raise_sanitized_os_error(error.errno)
        if result != 0:
            _raise_sanitized_os_error(saved_errno)

    def fstatfs(self, descriptor: int) -> FileSystemStat:
        """Return raw filesystem type data for ``descriptor`` without taking ownership."""

        checked_descriptor = _validate_descriptor(descriptor)
        if self.platform == "linux":
            linux_output = _LinuxStatFs()
            function = self._bind(
                "fstatfs",
                ("fstatfs",),
                [ctypes.c_int, ctypes.POINTER(_LinuxStatFs)],
                ctypes.c_int,
                missing_code="missing_fstatfs",
            )
            self._call(function, checked_descriptor, ctypes.byref(linux_output))
            return FileSystemStat(
                platform="linux",
                type_magic=int(linux_output.f_type),
                type_name=None,
                flags=0,
            )

        darwin_output = _DarwinStatFs()
        fstatfs_symbol = "fstatfs" if self.machine == "arm64" else "fstatfs$INODE64"
        function = self._bind(
            "fstatfs",
            (fstatfs_symbol,),
            [ctypes.c_int, ctypes.POINTER(_DarwinStatFs)],
            ctypes.c_int,
            missing_code="missing_fstatfs",
        )
        self._call(function, checked_descriptor, ctypes.byref(darwin_output))
        raw_type_name = ctypes.string_at(
            ctypes.addressof(darwin_output) + _DarwinStatFs.f_fstypename.offset,
            16,
        )
        terminator = raw_type_name.find(b"\0")
        if terminator <= 0:
            raise PosixDataError("invalid_filesystem_type")
        try:
            type_name = raw_type_name[:terminator].decode("ascii", errors="strict")
        except UnicodeDecodeError:
            raise PosixDataError("invalid_filesystem_type") from None
        return FileSystemStat(
            platform="darwin",
            type_magic=None,
            type_name=type_name,
            flags=int(darwin_output.f_flags),
        )

    def statx_mount_identity(self, descriptor: int) -> MountIdentity:
        """Return the Linux mount ID and device numbers for an open descriptor."""

        if self.platform != "linux":
            raise PosixUnsupportedError("statx_linux_only")
        checked_descriptor = _validate_descriptor(descriptor)
        output = _LinuxStatx()
        function = self._bind(
            "statx",
            ("statx",),
            [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_uint,
                ctypes.POINTER(_LinuxStatx),
            ],
            ctypes.c_int,
            missing_code="missing_statx",
        )
        self._call(
            function,
            checked_descriptor,
            b"",
            AT_EMPTY_PATH,
            STATX_MNT_ID,
            ctypes.byref(output),
        )
        if not output.stx_mask & STATX_MNT_ID:
            raise PosixUnsupportedError("statx_mount_id_unavailable")
        if output.stx_mnt_id <= 0:
            raise PosixDataError("invalid_mount_identity")
        return MountIdentity(
            mount_id=int(output.stx_mnt_id),
            device_major=int(output.stx_dev_major),
            device_minor=int(output.stx_dev_minor),
        )

    def rename_noreplace(
        self,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        """Atomically rename one leaf without replacing an existing target."""

        source_fd = _validate_descriptor(source_directory_fd)
        target_fd = _validate_descriptor(target_directory_fd)
        encoded_source = _encode_leaf(source_name)
        encoded_target = _encode_leaf(target_name)
        if self.platform == "linux":
            function = self._bind(
                "rename_noreplace",
                ("renameat2",),
                [
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                ],
                ctypes.c_int,
                missing_code="missing_renameat2",
            )
            self._call(
                function,
                source_fd,
                encoded_source,
                target_fd,
                encoded_target,
                RENAME_NOREPLACE,
            )
            return
        function = self._bind(
            "rename_noreplace",
            ("renameatx_np",),
            [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ],
            ctypes.c_int,
            missing_code="missing_renameatx_np",
        )
        self._call(
            function,
            source_fd,
            encoded_source,
            target_fd,
            encoded_target,
            RENAME_EXCL,
        )

    def link_noreplace(
        self,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        """Create a descriptor-relative hard link without replacing the target."""

        source_fd = _validate_descriptor(source_directory_fd)
        target_fd = _validate_descriptor(target_directory_fd)
        encoded_source = _encode_leaf(source_name)
        encoded_target = _encode_leaf(target_name)
        function = self._bind(
            "link_noreplace",
            ("linkat",),
            [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
            ],
            ctypes.c_int,
            missing_code="missing_linkat",
        )
        self._call(function, source_fd, encoded_source, target_fd, encoded_target, 0)

    def acquire_lock(self, descriptor: int, *, exclusive: bool, blocking: bool) -> None:
        """Acquire a shared or exclusive advisory lock for a caller-owned descriptor."""

        checked_descriptor = _validate_descriptor(descriptor)
        if type(exclusive) is not bool or type(blocking) is not bool:
            raise PosixDataError("invalid_lock_mode")
        operation = _LOCK_EX if exclusive else _LOCK_SH
        if not blocking:
            operation |= _LOCK_NB
        try:
            self._flock(checked_descriptor, operation)
        except OSError as error:
            _raise_sanitized_os_error(error.errno)

    def release_lock(self, descriptor: int) -> None:
        """Release an advisory lock for a caller-owned descriptor."""

        checked_descriptor = _validate_descriptor(descriptor)
        try:
            self._flock(checked_descriptor, _LOCK_UN)
        except OSError as error:
            _raise_sanitized_os_error(error.errno)

    def fsync(self, descriptor: int) -> None:
        """Synchronize a caller-owned regular-file or directory descriptor."""

        checked_descriptor = _validate_descriptor(descriptor)
        try:
            self._fsync(checked_descriptor)
        except OSError as error:
            _raise_sanitized_os_error(error.errno)

    def read_mountinfo(self, byte_limit: int = DEFAULT_MOUNTINFO_BYTE_LIMIT) -> bytes:
        """Read one bounded raw Linux ``/proc/self/mountinfo`` snapshot."""

        if self.platform != "linux":
            raise PosixUnsupportedError("mountinfo_linux_only")
        checked_limit = _validate_limit(byte_limit)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        open_interrupts = 0
        while True:
            try:
                descriptor = self._mountinfo_open(_MOUNTINFO_PATH, flags)
                break
            except InterruptedError as error:
                open_interrupts += 1
                if open_interrupts > MAX_MOUNTINFO_INTERRUPTS:
                    _raise_sanitized_os_error(error.errno)
            except OSError as error:
                _raise_sanitized_os_error(error.errno)
        checked_descriptor = _validate_descriptor(descriptor)
        try:
            captured = self._read_mountinfo_descriptor(checked_descriptor, checked_limit)
        except BaseException:
            with suppress(OSError):
                self._mountinfo_close(checked_descriptor)
            raise
        try:
            self._mountinfo_close(checked_descriptor)
        except OSError as error:
            _raise_sanitized_os_error(error.errno)
        return captured

    def _read_mountinfo_descriptor(self, descriptor: int, byte_limit: int) -> bytes:
        captured = bytearray()
        interrupts = 0
        while True:
            read_size = min(_MOUNTINFO_READ_CHUNK, byte_limit - len(captured) + 1)
            try:
                chunk = self._mountinfo_read(descriptor, read_size)
            except InterruptedError as error:
                interrupts += 1
                if interrupts > MAX_MOUNTINFO_INTERRUPTS:
                    _raise_sanitized_os_error(error.errno)
                continue
            except OSError as error:
                _raise_sanitized_os_error(error.errno)
            if type(chunk) is not bytes or len(chunk) > read_size:
                raise PosixDataError("invalid_mountinfo_read")
            if not chunk:
                return bytes(captured)
            captured.extend(chunk)
            if len(captured) > byte_limit:
                raise PosixDataError("mountinfo_too_large")
