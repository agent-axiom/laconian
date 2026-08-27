"""Descriptor-relative, no-follow source reads and owned file writes."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager

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
    """Open one directory without following a symlink at the named component."""

    descriptor = os.open(path, _directory_open_flags())
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise BoundedIOError("not_directory", "source root is not a directory")
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
            os.close(current_fd)
            current_fd = next_fd
        yield current_fd, components[-1]
    finally:
        os.close(current_fd)


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
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


def read_regular_file_once(
    directory_fd: int,
    path: str,
    *,
    limit: int,
    code: str = "file_size_limit",
) -> bytes:
    """Return one bounded descriptor snapshot of a regular file below a directory."""

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
            return captured
        finally:
            os.close(descriptor)


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
