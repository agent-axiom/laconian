"""Descriptor-relative, no-follow source reads and owned file writes."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    bounded_utf8_length,
    check_collection_count,
)

_WINDOWS_PREFIX = re.compile(r"^[A-Za-z]:")
_READ_CHUNK_BYTES = 64 * 1024


class BoundedIOError(ValueError):
    """A content-free bounded-I/O failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RegularFileIdentity:
    """Identity captured from the same descriptor as a file's exact bytes."""

    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True, slots=True)
class RegularFileSnapshot:
    """Bounded bytes and their same-descriptor identity."""

    data: bytes
    identity: RegularFileIdentity


@dataclass(frozen=True, slots=True)
class _DescriptorDirectoryIdentity:
    device: int
    inode: int
    mode: int
    link_count: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True, slots=True)
class _DescriptorBoundPath(os.PathLike[str]):
    _directory_fd: int
    _directory_identity: _DescriptorDirectoryIdentity
    _relative_components: tuple[str, ...]

    def __fspath__(self) -> str:
        base = f"/dev/fd/{self._directory_fd}"
        return "/".join((base, *self._relative_components))

    def __truediv__(self, operand: object) -> _DescriptorBoundPath:
        normalized = normalize_source_path(operand)  # type: ignore[arg-type]
        return _DescriptorBoundPath(
            self._directory_fd,
            self._directory_identity,
            (*self._relative_components, *normalized.split("/")),
        )

    @property
    def parent(self) -> _DescriptorBoundPath:
        if not self._relative_components:
            return self
        return _DescriptorBoundPath(
            self._directory_fd,
            self._directory_identity,
            self._relative_components[:-1],
        )

    @property
    def name(self) -> str:
        return self._relative_components[-1] if self._relative_components else ""

    @property
    def parts(self) -> tuple[str, ...]:
        return self._relative_components


def _descriptor_directory_identity(metadata: os.stat_result) -> _DescriptorDirectoryIdentity:
    return _DescriptorDirectoryIdentity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=metadata.st_mode,
        link_count=metadata.st_nlink,
        size=metadata.st_size,
        mtime_ns=metadata.st_mtime_ns,
        ctime_ns=metadata.st_ctime_ns,
    )


def _descriptor_bound_path(directory_fd: int) -> _DescriptorBoundPath:
    if type(directory_fd) is not int or directory_fd < 0:
        raise BoundedIOError("invalid_directory_descriptor", "invalid directory descriptor")
    try:
        metadata = os.fstat(directory_fd)
    except OSError as error:
        raise BoundedIOError(
            "invalid_directory_descriptor", "invalid directory descriptor"
        ) from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise BoundedIOError("not_directory", "source root is not a directory")
    return _DescriptorBoundPath(directory_fd, _descriptor_directory_identity(metadata), ())


def _is_descriptor_bound_path(value: object) -> bool:
    return type(value) is _DescriptorBoundPath


def normalize_source_path(value: str) -> str:
    """Validate and return an unchanged normalized relative POSIX path."""

    if type(value) is not str:
        raise BoundedIOError("unsafe_source_path", "unsafe source path")
    bounded_utf8_length(
        value,
        limit=RESOURCE_LIMITS_V1.bounded_string_bytes,
        code="source_path_limit",
    )
    if (
        not value
        or value == "."
        or value.startswith(("/", "\\"))
        or _WINDOWS_PREFIX.match(value) is not None
        or "\\" in value
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise BoundedIOError("unsafe_source_path", "unsafe source path")
    components = value.split("/")
    if any(component in ("", ".", "..") for component in components):
        raise BoundedIOError("unsafe_source_path", "unsafe source path")
    return value


def _required_flag(name: str, description: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int:
        raise RuntimeError(f"required {description} primitive is unavailable")
    return value


def _close_on_exec_flag() -> int:
    value = getattr(os, "O_CLOEXEC", 0)
    return value if type(value) is int else 0


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | _required_flag("O_DIRECTORY", "directory-open")
        | _required_flag("O_NOFOLLOW", "no-follow")
        | _close_on_exec_flag()
    )


def _source_open_flags() -> int:
    return (
        os.O_RDONLY
        | _required_flag("O_NOFOLLOW", "no-follow")
        | _required_flag("O_NONBLOCK", "nonblocking-open")
        | _close_on_exec_flag()
    )


def open_directory_no_follow(path: os.PathLike[str] | str) -> int:
    """Open a directory without following a symlink at any path component."""

    if _is_descriptor_bound_path(path):
        capability = path
        assert type(capability) is _DescriptorBoundPath
        if type(capability._relative_components) is not tuple or any(
            type(component) is not str for component in capability._relative_components
        ):
            raise BoundedIOError("unsafe_source_path", "unsafe source path")
        if capability._relative_components:
            normalized_tail = normalize_source_path("/".join(capability._relative_components))
            if tuple(normalized_tail.split("/")) != capability._relative_components:
                raise BoundedIOError("unsafe_source_path", "unsafe source path")
        try:
            descriptor = os.dup(capability._directory_fd)
        except OSError as error:
            raise BoundedIOError(
                "invalid_directory_descriptor", "invalid directory descriptor"
            ) from error
        try:
            if (
                _descriptor_directory_identity(os.fstat(descriptor))
                != capability._directory_identity
            ):
                raise BoundedIOError(
                    "invalid_directory_descriptor", "invalid directory descriptor"
                )
            for component in capability._relative_components:
                next_descriptor = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
                previous = descriptor
                descriptor = next_descriptor
                os.close(previous)
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise BoundedIOError("not_directory", "source root is not a directory")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    raw_path = os.fspath(path)
    if type(raw_path) is not str or not raw_path:
        raise BoundedIOError("not_directory", "source root is not a directory")
    absolute = raw_path.startswith("/")
    components = raw_path.split("/")
    descriptor = os.open("/" if absolute else ".", _directory_open_flags())
    try:
        for component in components:
            if component in ("", "."):
                continue
            next_descriptor = os.open(
                component,
                _directory_open_flags(),
                dir_fd=descriptor,
            )
            try:
                if not stat.S_ISDIR(os.fstat(next_descriptor).st_mode):
                    raise BoundedIOError("not_directory", "source root is not a directory")
            except BaseException:
                os.close(next_descriptor)
                raise
            previous_descriptor = descriptor
            descriptor = next_descriptor
            os.close(previous_descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


@contextmanager
def _parent_directory(
    directory_fd: int,
    normalized_path: str,
) -> Iterator[tuple[int, str]]:
    if type(directory_fd) is not int or directory_fd < 0:
        raise BoundedIOError("invalid_directory_descriptor", "invalid directory descriptor")

    components = normalized_path.split("/")
    current_fd = os.dup(directory_fd)
    try:
        if not stat.S_ISDIR(os.fstat(current_fd).st_mode):
            raise BoundedIOError("not_directory", "source root is not a directory")
        for component in components[:-1]:
            next_fd = os.open(
                component,
                _directory_open_flags(),
                dir_fd=current_fd,
            )
            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise BoundedIOError("not_directory", "path component is not a directory")
            except BaseException:
                os.close(next_fd)
                raise
            previous_fd = current_fd
            current_fd = next_fd
            os.close(previous_fd)
        yield current_fd, components[-1]
    finally:
        os.close(current_fd)


def _identity(metadata: os.stat_result) -> RegularFileIdentity:
    return RegularFileIdentity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=metadata.st_mode,
        size=metadata.st_size,
        mtime_ns=metadata.st_mtime_ns,
        ctime_ns=metadata.st_ctime_ns,
    )


def _read_to_eof_bounded(descriptor: int, *, limit: int, code: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        requested = min(_READ_CHUNK_BYTES, limit + 1 - total)
        try:
            chunk = os.read(descriptor, requested)
        except InterruptedError:
            continue
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ResourceLimitError(code)
    raise ResourceLimitError(code)


def read_regular_file_snapshot(
    directory_fd: int,
    path: str,
    *,
    limit: int,
    code: str = "file_size_limit",
) -> RegularFileSnapshot:
    """Return bounded bytes and identity from one regular-file descriptor."""

    normalized = normalize_source_path(path)
    check_collection_count(0, limit=limit, code=code)
    with _parent_directory(directory_fd, normalized) as (parent_fd, name):
        descriptor = os.open(name, _source_open_flags(), dir_fd=parent_fd)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise BoundedIOError("not_regular_file", "source is not a regular file")
            check_collection_count(before.st_size, limit=limit, code=code)
            captured = _read_to_eof_bounded(descriptor, limit=limit, code=code)
            after = os.fstat(descriptor)
            if not stat.S_ISREG(after.st_mode):
                raise BoundedIOError("source_mutated", "source mutated during capture")
            if _identity(before) != _identity(after) or len(captured) != before.st_size:
                raise BoundedIOError("source_mutated", "source mutated during capture")
            return RegularFileSnapshot(data=captured, identity=_identity(after))
        finally:
            os.close(descriptor)


def read_regular_file_once(
    directory_fd: int,
    path: str,
    *,
    limit: int,
    code: str = "file_size_limit",
) -> bytes:
    """Return one bounded descriptor snapshot of a regular file below a directory."""

    return read_regular_file_snapshot(
        directory_fd,
        path,
        limit=limit,
        code=code,
    ).data


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        try:
            count = os.write(descriptor, view[written:])
        except InterruptedError:
            continue
        if count <= 0:
            raise OSError("owned file write made no progress")
        written += count


def write_owned_file(directory_fd: int, path: str, data: bytes) -> None:
    """Create one private regular file below an owned directory without overwrite."""

    if type(data) is not bytes:
        raise TypeError("owned file data must be bytes")
    normalized = normalize_source_path(path)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | _required_flag("O_NOFOLLOW", "no-follow")
        | _close_on_exec_flag()
    )
    with _parent_directory(directory_fd, normalized) as (parent_fd, name):
        descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
        try:
            _write_all(descriptor, data)
        finally:
            os.close(descriptor)
