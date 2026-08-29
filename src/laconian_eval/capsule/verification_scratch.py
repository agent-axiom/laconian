"""Anonymous disk-backed state for exact, memory-bounded verification checks.

This module accepts no capsule path or descriptor. It receives only opaque filesystem identities
that scratch must avoid, chooses a fixed non-ambient host namespace, and unlinks its private file
before writing the first identity projection.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import hmac
import os
import stat
from collections.abc import Callable
from contextlib import suppress
from types import TracebackType
from typing import Literal, NoReturn
from uuid import UUID

IdentityKind = Literal["run", "operation", "session"]
NamespaceIdentity = tuple[int, int]

_GENERIC_SCRATCH_ERROR = "verification scratch failed"
_GENERIC_COLLISION_ERROR = "verification identity collision"
_SCRATCH_ROOTS = ("/var/tmp", "/private/tmp", "/tmp")
_NAME_PREFIX = b".laconian-verify-"
_CREATE_ATTEMPTS = 8
_EMPTY_TAG = 0
_TAGS: dict[IdentityKind, int] = {"run": 1, "operation": 2, "session": 3}
_SEAL_TAG = 4
_UUID_BYTES = 16
_ROW_BYTES = 8
_MAC_BYTES = 16
_RECORD_BYTES = 1 + _UUID_BYTES + _ROW_BYTES + _MAC_BYTES
_MIN_CAPACITY = 4
_MAX_ROW_INDEX = (1 << (_ROW_BYTES * 8)) - 1
_MAX_TABLE_VALUE = (1 << 64) - 1


class ScratchError(OSError):
    """A content-free operational failure in verifier-owned scratch."""

    def __init__(self) -> None:
        super().__init__(_GENERIC_SCRATCH_ERROR)


class IdentityCollision(ValueError):
    """An exact semantic identity collision at a physical event row."""

    def __init__(self, row_index: int) -> None:
        self.row_index = row_index
        super().__init__(_GENERIC_COLLISION_ERROR)


def _scratch_fail() -> NoReturn:
    raise ScratchError() from None


def _fd_flags(descriptor: int) -> int:
    try:
        return fcntl.fcntl(descriptor, fcntl.F_GETFD)
    except (OSError, OverflowError, ValueError):
        _scratch_fail()


def _fstat(descriptor: int) -> os.stat_result:
    try:
        return os.fstat(descriptor)
    except (OSError, OverflowError, ValueError):
        _scratch_fail()


def _close_once(descriptor: int) -> BaseException | None:
    try:
        os.close(descriptor)
    except BaseException as error:
        return error
    return None


def _validate_forbidden_identities(
    value: frozenset[NamespaceIdentity] | None,
) -> frozenset[NamespaceIdentity]:
    if value is None:
        return frozenset()
    if type(value) is not frozenset:
        _scratch_fail()
    checked: set[NamespaceIdentity] = set()
    for identity in value:
        if (
            type(identity) is not tuple
            or len(identity) != 2
            or any(type(part) is not int or part < 0 for part in identity)
        ):
            _scratch_fail()
        checked.add(identity)
    return frozenset(checked)


class _ScratchStorage:
    __slots__ = (
        "_closed",
        "_directory_fd",
        "_directory_identity",
        "_expected_size",
        "_file_fd",
        "_file_identity",
    )

    def __init__(self, forbidden: frozenset[NamespaceIdentity]) -> None:
        self._closed = False
        self._directory_fd = -1
        self._file_fd = -1
        self._expected_size = 0
        linked_name: bytes | None = None
        opened: os.stat_result | None = None
        primary: BaseException | None = None
        try:
            self._directory_fd, directory = self._open_directory(forbidden)
            self._directory_identity = (
                directory.st_dev,
                directory.st_ino,
                directory.st_mode,
            )
            self._file_fd, linked_name, opened = self._create_file()
            self._file_identity = (
                opened.st_dev,
                opened.st_ino,
                opened.st_mode,
                opened.st_uid,
            )
            try:
                os.unlink(linked_name, dir_fd=self._directory_fd)
            except OSError:
                self._best_effort_unlink(linked_name, opened)
                _scratch_fail()
            linked_name = None
            self._validate_file(expected_size=0)
        except BaseException as error:
            primary = error
        if linked_name is not None and opened is not None and self._file_fd >= 0:
            self._best_effort_unlink(linked_name, opened)
        if primary is not None:
            file_error = _close_once(self._file_fd) if self._file_fd >= 0 else None
            directory_error = _close_once(self._directory_fd) if self._directory_fd >= 0 else None
            self._file_fd = -1
            self._directory_fd = -1
            self._closed = True
            if isinstance(primary, (KeyboardInterrupt, SystemExit)):
                raise primary
            if isinstance(file_error, (KeyboardInterrupt, SystemExit)):
                raise file_error
            if isinstance(directory_error, (KeyboardInterrupt, SystemExit)):
                raise directory_error
            _scratch_fail()

    @staticmethod
    def _open_directory(
        forbidden: frozenset[NamespaceIdentity],
    ) -> tuple[int, os.stat_result]:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
        for root in _SCRATCH_ROOTS:
            try:
                descriptor = os.open(root, flags)
            except OSError:
                continue
            try:
                metadata = _fstat(descriptor)
                accepted = (
                    stat.S_ISDIR(metadata.st_mode)
                    and bool(_fd_flags(descriptor) & fcntl.FD_CLOEXEC)
                    and (metadata.st_dev, metadata.st_ino) not in forbidden
                )
            except BaseException as primary:
                close_error = _close_once(descriptor)
                if isinstance(primary, (KeyboardInterrupt, SystemExit)):
                    raise primary
                if isinstance(close_error, (KeyboardInterrupt, SystemExit)):
                    raise close_error from primary
                _scratch_fail()
            if not accepted:
                close_error = _close_once(descriptor)
                if close_error is not None:
                    _scratch_fail()
                continue
            return descriptor, metadata
        _scratch_fail()

    def _create_file(self) -> tuple[int, bytes, os.stat_result]:
        flags = os.O_RDWR | os.O_CLOEXEC | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        for _attempt in range(_CREATE_ATTEMPTS):
            try:
                name = _NAME_PREFIX + os.urandom(8).hex().encode("ascii")
                descriptor = os.open(name, flags, 0o600, dir_fd=self._directory_fd)
            except OSError as error:
                if error.errno == errno.EEXIST:
                    continue
                _scratch_fail()
            try:
                metadata = _fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.geteuid()
                    or metadata.st_nlink != 1
                    or metadata.st_size != 0
                    or stat.S_IMODE(metadata.st_mode) & ~0o600
                    or not _fd_flags(descriptor) & fcntl.FD_CLOEXEC
                ):
                    _scratch_fail()
                return descriptor, name, metadata
            except BaseException:
                close_error = _close_once(descriptor)
                with suppress(OSError):
                    os.unlink(name, dir_fd=self._directory_fd)
                if close_error is not None:
                    _scratch_fail()
                raise
        _scratch_fail()

    def _best_effort_unlink(self, name: bytes, opened: os.stat_result) -> None:
        try:
            visible = os.stat(name, dir_fd=self._directory_fd, follow_symlinks=False)
            if (visible.st_dev, visible.st_ino) == (opened.st_dev, opened.st_ino):
                os.unlink(name, dir_fd=self._directory_fd)
        except OSError:
            pass

    @property
    def descriptor(self) -> int:
        if self._closed or self._file_fd < 0:
            _scratch_fail()
        return self._file_fd

    @property
    def expected_size(self) -> int:
        return self._expected_size

    def _validate_directory(self) -> None:
        metadata = _fstat(self._directory_fd)
        if (
            (metadata.st_dev, metadata.st_ino, metadata.st_mode) != self._directory_identity
            or not stat.S_ISDIR(metadata.st_mode)
            or not _fd_flags(self._directory_fd) & fcntl.FD_CLOEXEC
        ):
            _scratch_fail()

    def _validate_file(self, *, expected_size: int) -> None:
        metadata = _fstat(self._file_fd)
        if (
            (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid)
            != self._file_identity
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 0
            or metadata.st_size != expected_size
            or stat.S_IMODE(metadata.st_mode) & ~0o600
            or not _fd_flags(self._file_fd) & fcntl.FD_CLOEXEC
        ):
            _scratch_fail()

    def validate(self) -> None:
        if self._closed:
            _scratch_fail()
        self._validate_directory()
        self._validate_file(expected_size=self._expected_size)

    def resize(self, size: int) -> None:
        if type(size) is not int or size < self._expected_size:
            _scratch_fail()
        self.validate()
        try:
            os.ftruncate(self._file_fd, size)
        except (OSError, OverflowError, ValueError):
            _scratch_fail()
        self._expected_size = size
        self.validate()

    def close(self, *, primary_active: bool, verify: Callable[[], None] | None = None) -> None:
        if self._closed:
            return
        pending: BaseException | None = None
        if not primary_active:
            try:
                self.validate()
                if verify is not None:
                    verify()
            except BaseException as error:
                pending = error
        self._closed = True
        file_error = _close_once(self._file_fd)
        directory_error = _close_once(self._directory_fd)
        self._file_fd = -1
        self._directory_fd = -1
        if primary_active:
            return
        if pending is not None:
            if isinstance(pending, (KeyboardInterrupt, SystemExit)):
                raise pending
            _scratch_fail()
        if file_error is not None or directory_error is not None:
            if isinstance(file_error, (KeyboardInterrupt, SystemExit)):
                raise file_error
            if isinstance(directory_error, (KeyboardInterrupt, SystemExit)):
                raise directory_error
            _scratch_fail()


def _checked_pread(descriptor: int, size: int, offset: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        try:
            chunk = os.pread(descriptor, size - len(chunks), offset + len(chunks))
        except InterruptedError:
            continue
        except (OSError, OverflowError, ValueError):
            _scratch_fail()
        if not chunk:
            _scratch_fail()
        chunks.extend(chunk)
    return bytes(chunks)


def _checked_pwrite(descriptor: int, data: bytes, offset: int) -> None:
    written = 0
    while written < len(data):
        try:
            progress = os.pwrite(descriptor, data[written:], offset + written)
        except InterruptedError:
            continue
        except (OSError, OverflowError, ValueError):
            _scratch_fail()
        if progress <= 0:
            _scratch_fail()
        written += progress


class ExactIdentityRegistry:
    """Exact external open-addressed registry with constant resident state."""

    __slots__ = ("_base", "_capacity", "_closed", "_count", "_key", "_storage")

    def __init__(
        self,
        *,
        initial_capacity: int = 1024,
        forbidden_namespace_identities: frozenset[NamespaceIdentity] | None = None,
    ) -> None:
        if type(initial_capacity) is not int or initial_capacity < _MIN_CAPACITY:
            _scratch_fail()
        capacity = 1
        while capacity < initial_capacity:
            capacity <<= 1
        self._capacity = capacity
        self._base = 0
        self._count = 0
        self._closed = False
        storage: _ScratchStorage | None = None
        try:
            forbidden = _validate_forbidden_identities(forbidden_namespace_identities)
            self._key = os.urandom(32)
            storage = _ScratchStorage(forbidden)
            self._storage = storage
            storage.resize(capacity * _RECORD_BYTES)
        except BaseException as error:
            self._closed = True
            if storage is not None:
                storage.close(primary_active=True)
            if isinstance(error, (ScratchError, KeyboardInterrupt, SystemExit)):
                raise
            _scratch_fail()

    def __enter__(self) -> ExactIdentityRegistry:
        if self._closed:
            _scratch_fail()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> Literal[False]:
        self.close(primary_active=exc_type is not None)
        return False

    def _slot(self, value: UUID, capacity: int | None = None) -> int:
        selected_capacity = self._capacity if capacity is None else capacity
        digest = hashlib.blake2b(value.bytes, key=self._key, digest_size=8).digest()
        return int.from_bytes(digest, "big") & (selected_capacity - 1)

    def _mac(self, payload: bytes, absolute_slot: int, capacity: int) -> bytes:
        if not 0 <= absolute_slot <= _MAX_TABLE_VALUE or not 0 < capacity <= _MAX_TABLE_VALUE:
            _scratch_fail()
        context = absolute_slot.to_bytes(8, "big") + capacity.to_bytes(8, "big")
        return hashlib.blake2b(payload + context, key=self._key, digest_size=_MAC_BYTES).digest()

    @staticmethod
    def _validate_declaration(value: UUID, row_index: int) -> None:
        if (
            type(value) is not UUID
            or type(row_index) is not int
            or not 0 <= row_index <= _MAX_ROW_INDEX
        ):
            _scratch_fail()

    def _encode(
        self,
        value: UUID,
        tag: int,
        row_index: int,
        absolute_slot: int,
        capacity: int,
    ) -> bytes:
        self._validate_declaration(value, row_index)
        payload = bytes((tag,)) + value.bytes + row_index.to_bytes(_ROW_BYTES, "big")
        return payload + self._mac(payload, absolute_slot, capacity)

    def _decode(
        self,
        record: bytes,
        absolute_slot: int,
        capacity: int,
    ) -> tuple[int, UUID | None, int]:
        if len(record) != _RECORD_BYTES:
            _scratch_fail()
        if not any(record):
            return _EMPTY_TAG, None, 0
        tag = record[0]
        if tag not in {*_TAGS.values(), _SEAL_TAG}:
            _scratch_fail()
        payload = record[:-_MAC_BYTES]
        if not hmac.compare_digest(
            record[-_MAC_BYTES:], self._mac(payload, absolute_slot, capacity)
        ):
            _scratch_fail()
        return (
            tag,
            UUID(bytes=record[1 : 1 + _UUID_BYTES]),
            int.from_bytes(record[1 + _UUID_BYTES : 1 + _UUID_BYTES + _ROW_BYTES], "big"),
        )

    def _record(self, base: int, slot: int, capacity: int) -> tuple[int, UUID | None, int]:
        offset = base + slot * _RECORD_BYTES
        record = _checked_pread(self._storage.descriptor, _RECORD_BYTES, offset)
        return self._decode(record, offset // _RECORD_BYTES, capacity)

    def _lookup_table(
        self,
        value: UUID,
        base: int,
        capacity: int,
    ) -> tuple[int, int, int]:
        start = self._slot(value, capacity)
        for probe in range(capacity):
            slot = (start + probe) & (capacity - 1)
            tag, stored, row_index = self._record(base, slot, capacity)
            if tag == _EMPTY_TAG or stored == value:
                return slot, tag, row_index
        _scratch_fail()

    def _write_record(
        self,
        value: UUID,
        tag: int,
        row_index: int,
        base: int,
        slot: int,
        capacity: int,
    ) -> None:
        offset = base + slot * _RECORD_BYTES
        _checked_pwrite(
            self._storage.descriptor,
            self._encode(value, tag, row_index, offset // _RECORD_BYTES, capacity),
            offset,
        )

    def _insert_without_resize(
        self,
        value: UUID,
        tag: int,
        row_index: int,
        base: int,
        capacity: int,
    ) -> None:
        slot, existing_tag, _existing_row = self._lookup_table(value, base, capacity)
        if existing_tag != _EMPTY_TAG:
            _scratch_fail()
        self._write_record(value, tag, row_index, base, slot, capacity)

    def _scan_table(self, base: int, capacity: int, expected_count: int) -> None:
        observed = 0
        for slot in range(capacity):
            tag, _value, _row_index = self._record(base, slot, capacity)
            if tag != _EMPTY_TAG:
                observed += 1
        if observed != expected_count:
            _scratch_fail()

    def _resize(self) -> None:
        self._storage.validate()
        self._scan_table(self._base, self._capacity, self._count)
        old_base = self._base
        old_capacity = self._capacity
        new_capacity = old_capacity << 1
        new_base = self._storage.expected_size
        self._storage.resize(new_base + new_capacity * _RECORD_BYTES)
        migrated = 0
        for slot in range(old_capacity):
            tag, value, row_index = self._record(old_base, slot, old_capacity)
            if tag != _EMPTY_TAG:
                assert value is not None
                self._insert_without_resize(
                    value,
                    tag,
                    row_index,
                    new_base,
                    new_capacity,
                )
                migrated += 1
        if migrated != self._count:
            _scratch_fail()
        self._scan_table(new_base, new_capacity, self._count)
        self._base = new_base
        self._capacity = new_capacity

    def _resize_for_new_value(self) -> None:
        if (self._count + 1) * 2 > self._capacity:
            self._resize()

    def declare_core(self, value: UUID, kind: IdentityKind | str, row_index: int) -> None:
        self._validate_declaration(value, row_index)
        if type(kind) is not str or kind not in _TAGS:
            _scratch_fail()
        _slot, existing_tag, _existing_row = self._lookup_table(value, self._base, self._capacity)
        if existing_tag != _EMPTY_TAG:
            raise IdentityCollision(row_index)
        self._resize_for_new_value()
        slot, existing_tag, _existing_row = self._lookup_table(value, self._base, self._capacity)
        if existing_tag != _EMPTY_TAG:
            _scratch_fail()
        self._write_record(value, _TAGS[kind], row_index, self._base, slot, self._capacity)
        self._count += 1

    def declare_seal(self, value: UUID, seal_operation: UUID, row_index: int) -> None:
        self._validate_declaration(value, row_index)
        self._validate_declaration(seal_operation, row_index)
        if value == seal_operation:
            raise IdentityCollision(row_index)
        _slot, existing_tag, _existing_row = self._lookup_table(value, self._base, self._capacity)
        if existing_tag in {_TAGS["run"], _TAGS["session"], _SEAL_TAG}:
            raise IdentityCollision(row_index)
        if existing_tag == _TAGS["operation"]:
            return
        self._resize_for_new_value()
        slot, existing_tag, _existing_row = self._lookup_table(value, self._base, self._capacity)
        if existing_tag != _EMPTY_TAG:
            _scratch_fail()
        self._write_record(value, _SEAL_TAG, row_index, self._base, slot, self._capacity)
        self._count += 1

    def _verify_current_table(self) -> None:
        self._scan_table(self._base, self._capacity, self._count)

    def close(self, *, primary_active: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        self._storage.close(
            primary_active=primary_active,
            verify=None if primary_active else self._verify_current_table,
        )


__all__ = ["ExactIdentityRegistry", "IdentityCollision", "NamespaceIdentity", "ScratchError"]
