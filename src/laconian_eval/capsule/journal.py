"""Descriptor-relative, read-only snapshots of mutable capsule journals."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Literal, Protocol, Self, cast
from uuid import UUID

from pydantic import ValidationError

from laconian_eval.capsule.attempts import RawAttemptV2, raw_attempt_bytes, raw_attempt_jsonl
from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.events import EventError, EventV1, event_bytes, event_jsonl, parse_event
from laconian_eval.capsule.filesystem import FilesystemPosixOps
from laconian_eval.capsule.history import (
    HistoryContextV1,
    HistoryError,
    LifecycleProjectionV1,
    ValidatedHistoryV1,
    derive_lifecycle_v1,
    validate_event_ledger_v1,
    validate_history_v1,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1

JournalCode = Literal[
    "io_error",
    "unsafe_path_type",
    "resource_limit",
    "noncanonical_json",
    "invalid_model",
    "hash_mismatch",
    "identity_mismatch",
    "history_mismatch",
    "retry_mismatch",
    "lifecycle_mismatch",
    "unstable_snapshot",
]
Ledger = Literal["events", "raw"]
TailPolicy = Literal["reject", "report"]


class JournalError(ContentFreeCapsuleError):
    def __init__(self, code: JournalCode, ledger: Ledger, row_index: int | None = None) -> None:
        self.code = code
        self.ledger = ledger
        self.row_index = row_index
        super().__init__("capsule journal rejected")


@dataclass(frozen=True, slots=True)
class JournalSnapshotV1:
    device: int
    inode: int
    mode: int
    byte_length: int
    mtime_ns: int
    ctime_ns: int
    row_count: int
    sha256: str
    tail_byte_count: int
    tail_sha256: str | None


@dataclass(slots=True)
class _PassState:
    row_count: int = 0
    byte_length: int = 0
    sha256: str = ""
    tail_byte_count: int = 0
    tail_sha256: str | None = None
    committed_byte_length: int = 0
    whole_hash_state: _HashState | None = field(default=None, repr=False, compare=False)
    committed_hash_state: _HashState | None = field(default=None, repr=False, compare=False)


class _HashState(Protocol):
    def update(self, data: bytes) -> None: ...

    def hexdigest(self) -> str: ...

    def copy(self) -> Self: ...


_RAW_VALIDATION_CODES: dict[str, JournalCode] = {
    "attempt identity mismatch": "identity_mismatch",
    "retry lineage mismatch": "retry_mismatch",
    "retry limit exceeded": "retry_mismatch",
    "output identity mismatch": "hash_mismatch",
    "response identity mismatch": "hash_mismatch",
    "output redaction disclosure mismatch": "lifecycle_mismatch",
    "invalid success attempt": "lifecycle_mismatch",
    "contradictory authentication delivery evidence": "lifecycle_mismatch",
    "attempt truth-table mismatch": "lifecycle_mismatch",
    "invalid discarded-output evidence": "lifecycle_mismatch",
    "error attempt discloses output evidence": "lifecycle_mismatch",
    "error attempts cannot contain output identity": "lifecycle_mismatch",
}


def _raw_validation_code(error: ValidationError) -> JournalCode:
    mapped: JournalCode | None = None
    for detail in error.errors(include_url=False, include_input=False):
        context = detail.get("ctx")
        candidate: JournalCode | None = None
        if (
            detail.get("type") == "less_than_equal"
            and detail.get("loc") == ("attempt",)
            and type(context) is dict
            and type(context.get("le")) is int
            and context.get("le") == 6
        ):
            candidate = "retry_mismatch"
        elif type(context) is dict:
            cause = context.get("error")
            if (
                type(cause) is ValueError
                and type(cause.args) is tuple
                and len(cause.args) == 1
                and type(cause.args[0]) is str
            ):
                candidate = _RAW_VALIDATION_CODES.get(cause.args[0])
        if candidate is None or (mapped is not None and candidate != mapped):
            return "invalid_model"
        mapped = candidate
    return "invalid_model" if mapped is None else mapped


@dataclass(frozen=True, slots=True)
class JournalPairSnapshotV1:
    events: JournalSnapshotV1
    raw: JournalSnapshotV1
    history: ValidatedHistoryV1
    lifecycle: LifecycleProjectionV1
    reserved_operation_id: UUID | None = None


EventJournalSnapshotV1 = JournalSnapshotV1
RawJournalSnapshotV1 = JournalSnapshotV1


@dataclass(frozen=True, slots=True)
class JournalCursorV1:
    ledger: Ledger
    device: int
    inode: int
    mode: int
    byte_length: int
    mtime_ns: int
    ctime_ns: int
    row_count: int
    whole_sha256: str
    last_lf_offset: int
    tail_byte_count: int
    tail_sha256: str | None


EventJournalCursorV1 = JournalCursorV1
RawJournalCursorV1 = JournalCursorV1
EventJournalCursor = EventJournalCursorV1
RawJournalCursor = RawJournalCursorV1


class JournalTransaction:
    """One validated pair of retained writable journal descriptors."""

    __slots__ = (
        "_capsule_fd",
        "_closed",
        "_committed_hashes",
        "_event_fd",
        "_events",
        "_immutable_evidence_bytes",
        "_poisoned",
        "_posix",
        "_raw",
        "_raw_fd",
        "_whole_hashes",
    )

    def __init__(
        self,
        *,
        capsule_fd: int,
        event_fd: int,
        raw_fd: int,
        events: EventJournalCursorV1,
        raw: RawJournalCursorV1,
        event_whole_hash: _HashState,
        raw_whole_hash: _HashState,
        event_committed_hash: _HashState,
        raw_committed_hash: _HashState,
        posix: FilesystemPosixOps,
        immutable_evidence_bytes: int,
    ) -> None:
        self._capsule_fd = capsule_fd
        self._event_fd = event_fd
        self._raw_fd = raw_fd
        self._events = events
        self._raw = raw
        self._whole_hashes = {
            "events": event_whole_hash.copy(),
            "raw": raw_whole_hash.copy(),
        }
        self._committed_hashes = {
            "events": event_committed_hash.copy(),
            "raw": raw_committed_hash.copy(),
        }
        self._posix = posix
        self._immutable_evidence_bytes = immutable_evidence_bytes
        self._closed = False
        self._poisoned = False

    @property
    def events(self) -> EventJournalCursorV1:
        return self._events

    @property
    def raw(self) -> RawJournalCursorV1:
        return self._raw

    @property
    def total_capsule_bytes(self) -> int:
        return self._immutable_evidence_bytes + self.total_journal_bytes

    @property
    def total_journal_bytes(self) -> int:
        return self._events.byte_length + self._raw.byte_length

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        failure: tuple[Ledger, BaseException] | None = None
        fatal: BaseException | None = None
        owned_descriptors: tuple[tuple[Ledger, int], ...] = (
            ("events", self._event_fd),
            ("raw", self._raw_fd),
        )
        for ledger, descriptor in owned_descriptors:
            try:
                os.close(descriptor)
            except BaseException as error:
                if not isinstance(error, Exception):
                    if fatal is None:
                        fatal = error
                elif failure is None:
                    failure = ledger, error
        if fatal is not None:
            raise fatal
        if failure is not None:
            raise JournalError("io_error", failure[0]) from None

    def __enter__(self) -> JournalTransaction:
        if self._closed:
            raise JournalError("io_error", "events")
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        exception: BaseException | None,
        _traceback: object | None,
    ) -> None:
        try:
            self.close()
        except BaseException as close_error:
            if exception is None or (
                isinstance(exception, Exception) and not isinstance(close_error, Exception)
            ):
                raise


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open(root_fd: int, name: str, ledger: Ledger) -> tuple[int, os.stat_result]:
    descriptor = -1
    try:
        path_before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if not stat.S_ISREG(path_before.st_mode):
            raise JournalError("unsafe_path_type", ledger)
        descriptor = os.open(
            name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd
        )
        before = os.fstat(descriptor)
    except JournalError:
        raise
    except OSError as error:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        code: JournalCode = (
            "unsafe_path_type" if error.errno in {errno.ELOOP, errno.ENOTDIR} else "io_error"
        )
        raise JournalError(code, ledger) from None
    if not stat.S_ISREG(before.st_mode):
        with suppress(OSError):
            os.close(descriptor)
        raise JournalError("unsafe_path_type", ledger)
    if _identity(path_before) != _identity(before):
        with suppress(OSError):
            os.close(descriptor)
        raise JournalError("unstable_snapshot", ledger)
    return descriptor, before


def _rows(
    descriptor: int,
    ledger: Ledger,
    row_limit: int,
    count_limit: int | None,
    exact_size: int,
    *,
    tail_policy: TailPolicy,
    state: _PassState,
) -> Iterator[object]:
    pending = bytearray()
    row_index = 0
    whole_hash = hashlib.sha256()
    committed_hash = hashlib.sha256()
    while state.byte_length < exact_size:
        remaining = exact_size - state.byte_length
        try:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
        except InterruptedError:
            continue
        except (OSError, OverflowError, TypeError, ValueError):
            raise JournalError("io_error", ledger, row_index) from None
        if not chunk:
            break
        whole_hash.update(chunk)
        state.byte_length += len(chunk)
        for byte in chunk:
            if byte != 10:
                pending.append(byte)
                if len(pending) > row_limit:
                    raise JournalError("resource_limit", ledger, row_index)
                continue
            if not pending:
                raise JournalError("noncanonical_json", ledger, row_index)
            if count_limit is not None and row_index >= count_limit:
                raise JournalError("resource_limit", ledger, row_index)
            encoded = bytes(pending)
            pending.clear()
            try:
                _check_json_nesting(encoded, ledger, row_index)
                try:
                    decoded = json.loads(encoded)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise JournalError("noncanonical_json", ledger, row_index) from None
                if ledger == "events":
                    if (
                        isinstance(decoded, dict)
                        and decoded.get("kind") == "prepared"
                        and (row_index > 0 or decoded.get("sequence") != 0)
                    ):
                        raise JournalError("history_mismatch", ledger, row_index)
                    event_model = parse_event(decoded)
                    if event_bytes(event_model) != encoded:
                        raise JournalError("noncanonical_json", ledger, row_index)
                    yield event_model
                else:
                    raw_model = RawAttemptV2.model_validate(decoded, strict=True)
                    if raw_attempt_bytes(raw_model) != encoded:
                        raise JournalError("noncanonical_json", ledger, row_index)
                    yield raw_model
            except JournalError:
                raise
            except EventError as error:
                event_codes: dict[str, JournalCode] = {
                    "event_id_mismatch": "hash_mismatch",
                    "retry_mismatch": "retry_mismatch",
                    "lifecycle_mismatch": "lifecycle_mismatch",
                    "history_mismatch": "history_mismatch",
                }
                code = event_codes.get(error.code, "invalid_model")
                raise JournalError(code, ledger, row_index) from None
            except ValidationError as error:
                raise JournalError(_raw_validation_code(error), ledger, row_index) from None
            except (ValueError, TypeError):
                raise JournalError("invalid_model", ledger, row_index) from None
            committed_row = encoded + b"\n"
            committed_hash.update(committed_row)
            state.committed_byte_length += len(committed_row)
            row_index += 1
            state.row_count = row_index
    if pending:
        if tail_policy == "reject":
            raise JournalError("noncanonical_json", ledger, row_index)
        state.tail_byte_count = len(pending)
        state.tail_sha256 = hashlib.sha256(pending).hexdigest()
    if state.byte_length != exact_size:
        raise JournalError("unstable_snapshot", ledger, row_index)
    state.sha256 = whole_hash.hexdigest()
    state.whole_hash_state = whole_hash
    state.committed_hash_state = committed_hash


def _check_json_nesting(encoded: bytes, ledger: Ledger, row_index: int) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in encoded:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                in_string = False
            continue
        if byte == 34:
            in_string = True
        elif byte in (91, 123):
            depth += 1
            if depth > RESOURCE_LIMITS_V1.nesting_depth:
                raise JournalError("resource_limit", ledger, row_index)
        elif byte in (93, 125):
            depth -= 1


def _snapshot_one(capsule_fd: int, ledger: Ledger, *, tail_policy: TailPolicy) -> JournalSnapshotV1:
    name = f"{ledger}.jsonl"
    descriptor, before = _open(capsule_fd, name, ledger)
    primary: BaseException | None = None
    try:
        if before.st_size > RESOURCE_LIMITS_V1.mutable_capsule_bytes:
            raise JournalError("resource_limit", ledger)
        state = _PassState()
        row_limit = (
            RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes
            if ledger == "events"
            else RESOURCE_LIMITS_V1.raw_jsonl_row_bytes
        )
        count_limit = None if ledger == "events" else RESOURCE_LIMITS_V1.raw_rows
        for _model in _rows(
            descriptor,
            ledger,
            row_limit,
            count_limit,
            before.st_size,
            tail_policy=tail_policy,
            state=state,
        ):
            pass
        after = os.fstat(descriptor)
        path_after = os.stat(name, dir_fd=capsule_fd, follow_symlinks=False)
        if _identity(before) != _identity(after) or _identity(after) != _identity(path_after):
            raise JournalError("unstable_snapshot", ledger)
        return JournalSnapshotV1(
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            state.row_count,
            state.sha256,
            state.tail_byte_count,
            state.tail_sha256,
        )
    except BaseException as error:
        primary = error
        if isinstance(error, JournalError) or not isinstance(error, Exception):
            raise
        raise JournalError("io_error", ledger) from None
    finally:
        try:
            os.close(descriptor)
        except OSError:
            if primary is None:
                raise JournalError("io_error", ledger) from None


def snapshot_event_journal(capsule_fd: int, *, tail_policy: TailPolicy) -> EventJournalSnapshotV1:
    return _snapshot_one(capsule_fd, "events", tail_policy=tail_policy)


def snapshot_raw_journal(capsule_fd: int, *, tail_policy: TailPolicy) -> RawJournalSnapshotV1:
    return _snapshot_one(capsule_fd, "raw", tail_policy=tail_policy)


def _rewind(descriptor: int, ledger: Ledger) -> None:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
    except (OSError, OverflowError, TypeError, ValueError):
        raise JournalError("io_error", ledger) from None


def _final_fstat(descriptor: int, ledger: Ledger) -> os.stat_result:
    try:
        return os.fstat(descriptor)
    except (OSError, OverflowError, TypeError, ValueError):
        raise JournalError("io_error", ledger) from None


def _final_path_stat(capsule_fd: int, ledger: Ledger) -> os.stat_result:
    try:
        return os.stat(f"{ledger}.jsonl", dir_fd=capsule_fd, follow_symlinks=False)
    except OSError:
        raise JournalError("unstable_snapshot", ledger) from None
    except (OverflowError, TypeError, ValueError):
        raise JournalError("io_error", ledger) from None


def _append_identity_from_cursor(
    cursor: JournalCursorV1,
) -> tuple[int, int, int, int, int, int]:
    return (
        cursor.device,
        cursor.inode,
        cursor.mode,
        cursor.byte_length,
        cursor.mtime_ns,
        cursor.ctime_ns,
    )


def _append_identity_from_stat(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _cursor_from_scan(
    ledger: Ledger,
    snapshot: JournalSnapshotV1,
    state: _PassState,
) -> JournalCursorV1:
    if (
        state.whole_hash_state is None
        or state.committed_hash_state is None
        or state.committed_byte_length != snapshot.byte_length - snapshot.tail_byte_count
    ):
        raise JournalError("io_error", ledger)
    return JournalCursorV1(
        ledger=ledger,
        device=snapshot.device,
        inode=snapshot.inode,
        mode=snapshot.mode,
        byte_length=snapshot.byte_length,
        mtime_ns=snapshot.mtime_ns,
        ctime_ns=snapshot.ctime_ns,
        row_count=snapshot.row_count,
        whole_sha256=snapshot.sha256,
        last_lf_offset=state.committed_byte_length,
        tail_byte_count=snapshot.tail_byte_count,
        tail_sha256=snapshot.tail_sha256,
    )


def _open_update(
    capsule_fd: int,
    ledger: Ledger,
    expected: JournalSnapshotV1,
) -> tuple[int, os.stat_result]:
    name = f"{ledger}.jsonl"
    descriptor = -1
    try:
        path_before = os.stat(name, dir_fd=capsule_fd, follow_symlinks=False)
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=capsule_fd,
        )
        before = os.fstat(descriptor)
    except OSError as error:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        code: JournalCode = (
            "unsafe_path_type" if error.errno in {errno.ELOOP, errno.ENOTDIR} else "io_error"
        )
        raise JournalError(code, ledger) from None
    if not stat.S_ISREG(before.st_mode):
        with suppress(OSError):
            os.close(descriptor)
        raise JournalError("unsafe_path_type", ledger)
    if _identity(path_before) != _identity(before) or _identity(before) != (
        expected.device,
        expected.inode,
        expected.mode,
        expected.byte_length,
        expected.mtime_ns,
        expected.ctime_ns,
    ):
        with suppress(OSError):
            os.close(descriptor)
        raise JournalError("unstable_snapshot", ledger)
    return descriptor, before


def _scan_update_descriptor(
    capsule_fd: int,
    descriptor: int,
    ledger: Ledger,
    before: os.stat_result,
) -> tuple[JournalSnapshotV1, _PassState]:
    _rewind(descriptor, ledger)
    state = _PassState()
    row_limit = (
        RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes
        if ledger == "events"
        else RESOURCE_LIMITS_V1.raw_jsonl_row_bytes
    )
    count_limit = None if ledger == "events" else RESOURCE_LIMITS_V1.raw_rows
    for _model in _rows(
        descriptor,
        ledger,
        row_limit,
        count_limit,
        before.st_size,
        tail_policy="report",
        state=state,
    ):
        pass
    after = _final_fstat(descriptor, ledger)
    path_after = _final_path_stat(capsule_fd, ledger)
    if _identity(before) != _identity(after) or _identity(after) != _identity(path_after):
        raise JournalError("unstable_snapshot", ledger)
    return (
        JournalSnapshotV1(
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            state.row_count,
            state.sha256,
            state.tail_byte_count,
            state.tail_sha256,
        ),
        state,
    )


def _precheck_transaction_pair_size(
    capsule_fd: int,
    immutable_evidence_bytes: int,
) -> None:
    """Reject an oversized pair from metadata before either ledger is streamed."""

    event_fd, event_before = _open(capsule_fd, "events.jsonl", "events")
    raw_fd = -1
    primary: BaseException | None = None
    try:
        raw_fd, raw_before = _open(capsule_fd, "raw.jsonl", "raw")
        if (
            immutable_evidence_bytes + event_before.st_size + raw_before.st_size
            > RESOURCE_LIMITS_V1.mutable_capsule_bytes
        ):
            raise JournalError("resource_limit", "events")
    except BaseException as error:
        primary = error
        raise
    finally:
        close_failure: Ledger | None = None
        try:
            os.close(event_fd)
        except OSError:
            close_failure = "events"
        if raw_fd >= 0:
            try:
                os.close(raw_fd)
            except OSError:
                if close_failure is None:
                    close_failure = "raw"
        if close_failure is not None and primary is None:
            raise JournalError("io_error", close_failure) from None


def open_journal_transaction(
    capsule_fd: int,
    *,
    posix: FilesystemPosixOps,
    immutable_evidence_bytes: int = 0,
) -> JournalTransaction:
    """Open, bind, and retain the exact canonically validated writable journal pair."""

    if type(immutable_evidence_bytes) is not int or immutable_evidence_bytes < 0:
        raise JournalError("invalid_model", "events")
    _precheck_transaction_pair_size(capsule_fd, immutable_evidence_bytes)
    event_validated = snapshot_event_journal(capsule_fd, tail_policy="report")
    raw_validated = snapshot_raw_journal(capsule_fd, tail_policy="report")
    if (
        immutable_evidence_bytes + event_validated.byte_length + raw_validated.byte_length
        > RESOURCE_LIMITS_V1.mutable_capsule_bytes
    ):
        raise JournalError("resource_limit", "events")

    event_fd = -1
    raw_fd = -1
    primary: BaseException | None = None
    try:
        event_fd, event_before = _open_update(capsule_fd, "events", event_validated)
        raw_fd, raw_before = _open_update(capsule_fd, "raw", raw_validated)
        event_snapshot, event_state = _scan_update_descriptor(
            capsule_fd, event_fd, "events", event_before
        )
        if event_snapshot != event_validated:
            raise JournalError("unstable_snapshot", "events")
        raw_snapshot, raw_state = _scan_update_descriptor(capsule_fd, raw_fd, "raw", raw_before)
        if raw_snapshot != raw_validated:
            raise JournalError("unstable_snapshot", "raw")
        events = _cursor_from_scan("events", event_snapshot, event_state)
        raw = _cursor_from_scan("raw", raw_snapshot, raw_state)
        assert event_state.whole_hash_state is not None
        assert raw_state.whole_hash_state is not None
        assert event_state.committed_hash_state is not None
        assert raw_state.committed_hash_state is not None
        transaction = JournalTransaction(
            capsule_fd=capsule_fd,
            event_fd=event_fd,
            raw_fd=raw_fd,
            events=events,
            raw=raw,
            event_whole_hash=event_state.whole_hash_state,
            raw_whole_hash=raw_state.whole_hash_state,
            event_committed_hash=event_state.committed_hash_state,
            raw_committed_hash=raw_state.committed_hash_state,
            posix=posix,
            immutable_evidence_bytes=immutable_evidence_bytes,
        )
        event_fd = -1
        raw_fd = -1
        return transaction
    except BaseException as error:
        primary = error
        raise
    finally:
        close_failure: Ledger | None = None
        opened_descriptors: tuple[tuple[Ledger, int], ...] = (
            ("events", event_fd),
            ("raw", raw_fd),
        )
        for ledger, descriptor in opened_descriptors:
            if descriptor < 0:
                continue
            try:
                os.close(descriptor)
            except OSError:
                if close_failure is None:
                    close_failure = ledger
        if primary is None and close_failure is not None:
            raise JournalError("io_error", close_failure) from None


def _checked_transaction(
    transaction: JournalTransaction,
    ledger: Ledger,
) -> JournalTransaction:
    if type(transaction) is not JournalTransaction or transaction._closed or transaction._poisoned:
        raise JournalError("io_error", ledger)
    if transaction.events.tail_byte_count:
        raise JournalError("noncanonical_json", "events", transaction.events.row_count)
    if transaction.raw.tail_byte_count:
        raise JournalError("noncanonical_json", "raw", transaction.raw.row_count)
    return transaction


def _recheck_transaction_descriptors(transaction: JournalTransaction) -> None:
    retained: tuple[tuple[Ledger, int, JournalCursorV1], ...] = (
        ("events", transaction._event_fd, transaction.events),
        ("raw", transaction._raw_fd, transaction.raw),
    )
    for ledger, descriptor, cursor in retained:
        try:
            metadata = _final_fstat(descriptor, ledger)
            path_metadata = _final_path_stat(transaction._capsule_fd, ledger)
        except JournalError:
            transaction._poisoned = True
            raise
        expected = _append_identity_from_cursor(cursor)
        if (
            _append_identity_from_stat(metadata) != expected
            or _append_identity_from_stat(path_metadata) != expected
        ):
            transaction._poisoned = True
            raise JournalError("unstable_snapshot", ledger)


def _cursor_identity(cursor: JournalCursorV1) -> tuple[int, int, int, int, int, int]:
    return (
        cursor.device,
        cursor.inode,
        cursor.mode,
        cursor.byte_length,
        cursor.mtime_ns,
        cursor.ctime_ns,
    )


def _rehash_transaction_pair(transaction: JournalTransaction) -> None:
    """Bind both retained descriptors and paths to their current cursor hashes."""

    if type(transaction) is not JournalTransaction or transaction._closed or transaction._poisoned:
        raise JournalError("io_error", "events")
    try:
        retained: tuple[tuple[Ledger, int, JournalCursorV1], ...] = (
            ("events", transaction._event_fd, transaction.events),
            ("raw", transaction._raw_fd, transaction.raw),
        )
        for ledger, descriptor, cursor in retained:
            before = _final_fstat(descriptor, ledger)
            path_before = _final_path_stat(transaction._capsule_fd, ledger)
            expected_identity = _cursor_identity(cursor)
            if (
                _identity(before) != expected_identity
                or _identity(path_before) != expected_identity
            ):
                raise JournalError("unstable_snapshot", ledger)
            digest = hashlib.sha256()
            offset = 0
            while offset < cursor.byte_length:
                try:
                    chunk = os.pread(
                        descriptor,
                        min(64 * 1024, cursor.byte_length - offset),
                        offset,
                    )
                except InterruptedError:
                    continue
                except (OSError, OverflowError, TypeError, ValueError):
                    raise JournalError("io_error", ledger) from None
                if not chunk:
                    raise JournalError("unstable_snapshot", ledger)
                digest.update(chunk)
                offset += len(chunk)
            after = _final_fstat(descriptor, ledger)
            path_after = _final_path_stat(transaction._capsule_fd, ledger)
            if (
                _identity(after) != expected_identity
                or _identity(path_after) != expected_identity
                or digest.hexdigest() != cursor.whole_sha256
            ):
                raise JournalError("unstable_snapshot", ledger)

        # A change to events while raw was being hashed must not escape the joint
        # binding merely because events was checked first.
        for ledger, descriptor, cursor in retained:
            if _identity(_final_fstat(descriptor, ledger)) != _cursor_identity(cursor) or _identity(
                _final_path_stat(transaction._capsule_fd, ledger)
            ) != _cursor_identity(cursor):
                raise JournalError("unstable_snapshot", ledger)
    except BaseException:
        transaction._poisoned = True
        raise


def _joint_recheck_transaction_pair(
    transaction: JournalTransaction,
    pair: JournalPairSnapshotV1,
) -> None:
    """Bind both live descriptors and both current paths to one just-scanned pair."""

    if type(pair) is not JournalPairSnapshotV1:
        raise JournalError("invalid_model", "events")
    if type(transaction) is not JournalTransaction or transaction._closed or transaction._poisoned:
        raise JournalError("io_error", "events")
    try:
        _rehash_transaction_pair(transaction)
        retained: tuple[tuple[Ledger, int, JournalCursorV1, JournalSnapshotV1], ...] = (
            ("events", transaction._event_fd, transaction.events, pair.events),
            ("raw", transaction._raw_fd, transaction.raw, pair.raw),
        )
        for ledger, descriptor, cursor, snapshot in retained:
            metadata = _final_fstat(descriptor, ledger)
            path_metadata = _final_path_stat(transaction._capsule_fd, ledger)
            expected_identity = (
                snapshot.device,
                snapshot.inode,
                snapshot.mode,
                snapshot.byte_length,
                snapshot.mtime_ns,
                snapshot.ctime_ns,
            )
            if (
                _identity(metadata) != expected_identity
                or _identity(path_metadata) != expected_identity
                or (
                    cursor.device,
                    cursor.inode,
                    cursor.mode,
                    cursor.byte_length,
                    cursor.mtime_ns,
                    cursor.ctime_ns,
                    cursor.row_count,
                    cursor.whole_sha256,
                    cursor.tail_byte_count,
                    cursor.tail_sha256,
                )
                != (
                    snapshot.device,
                    snapshot.inode,
                    snapshot.mode,
                    snapshot.byte_length,
                    snapshot.mtime_ns,
                    snapshot.ctime_ns,
                    snapshot.row_count,
                    snapshot.sha256,
                    snapshot.tail_byte_count,
                    snapshot.tail_sha256,
                )
            ):
                raise JournalError("unstable_snapshot", ledger)
    except BaseException:
        transaction._poisoned = True
        raise


def _full_write(transaction: JournalTransaction, ledger: Ledger, framed: bytes) -> None:
    descriptor = transaction._event_fd if ledger == "events" else transaction._raw_fd
    offset = 0
    while offset < len(framed):
        try:
            written = os.write(descriptor, framed[offset:])
        except InterruptedError:
            continue
        except (KeyboardInterrupt, SystemExit):
            transaction._poisoned = True
            raise
        except (OSError, OverflowError, TypeError, ValueError):
            transaction._poisoned = True
            raise JournalError("io_error", ledger) from None
        if type(written) is not int or not 0 < written <= len(framed) - offset:
            transaction._poisoned = True
            raise JournalError("io_error", ledger)
        offset += written


def _append_framed(
    transaction: JournalTransaction,
    ledger: Ledger,
    framed: bytes,
) -> JournalCursorV1:
    transaction = _checked_transaction(transaction, ledger)
    _recheck_transaction_descriptors(transaction)
    if transaction.total_capsule_bytes + len(framed) > RESOURCE_LIMITS_V1.mutable_capsule_bytes:
        raise JournalError("resource_limit", ledger)
    cursor = transaction.events if ledger == "events" else transaction.raw
    if ledger == "raw" and cursor.row_count >= RESOURCE_LIMITS_V1.raw_rows:
        raise JournalError("resource_limit", ledger, cursor.row_count)
    _full_write(transaction, ledger, framed)
    descriptor = transaction._event_fd if ledger == "events" else transaction._raw_fd
    try:
        transaction._posix.fsync(descriptor)
    except BaseException as error:
        transaction._poisoned = True
        if not isinstance(error, Exception):
            raise
        raise JournalError("io_error", ledger) from None
    try:
        after = _final_fstat(descriptor, ledger)
    except JournalError:
        transaction._poisoned = True
        raise
    if (after.st_dev, after.st_ino, after.st_mode) != (
        cursor.device,
        cursor.inode,
        cursor.mode,
    ) or after.st_size != cursor.byte_length + len(framed):
        transaction._poisoned = True
        raise JournalError("unstable_snapshot", ledger)
    whole_hash = transaction._whole_hashes[ledger]
    committed_hash = transaction._committed_hashes[ledger]
    whole_hash.update(framed)
    committed_hash.update(framed)
    updated = JournalCursorV1(
        ledger=ledger,
        device=after.st_dev,
        inode=after.st_ino,
        mode=after.st_mode,
        byte_length=after.st_size,
        mtime_ns=after.st_mtime_ns,
        ctime_ns=after.st_ctime_ns,
        row_count=cursor.row_count + 1,
        whole_sha256=whole_hash.hexdigest(),
        last_lf_offset=after.st_size,
        tail_byte_count=0,
        tail_sha256=None,
    )
    if ledger == "events":
        transaction._events = updated
    else:
        transaction._raw = updated
    return updated


def append_event(transaction: JournalTransaction, event: EventV1) -> None:
    """Append and fsync one canonical event on the retained event descriptor."""

    transaction = _checked_transaction(transaction, "events")
    try:
        framed = event_jsonl(event)
    except Exception:
        raise JournalError("invalid_model", "events") from None
    if event.sequence != transaction.events.row_count:
        raise JournalError("history_mismatch", "events", transaction.events.row_count)
    _append_framed(transaction, "events", framed)


def append_raw_attempt(
    transaction: JournalTransaction,
    attempt: RawAttemptV2,
) -> None:
    """Append and fsync one canonical raw attempt on the retained raw descriptor."""

    transaction = _checked_transaction(transaction, "raw")
    try:
        framed = raw_attempt_jsonl(attempt)
    except Exception:
        raise JournalError("invalid_model", "raw") from None
    if attempt.call_sequence != transaction.raw.row_count:
        raise JournalError("history_mismatch", "raw", transaction.raw.row_count)
    _append_framed(transaction, "raw", framed)


def _scan_journal_pair_descriptors(
    capsule_fd: int,
    event_fd: int,
    raw_fd: int,
    event_before: os.stat_result,
    raw_before: os.stat_result,
    *,
    history_context: HistoryContextV1,
    tail_policy: TailPolicy,
    reserved_operation_id: UUID | None,
) -> tuple[JournalPairSnapshotV1, _PassState, _PassState]:
    """Run the exact three-pass reconciliation on an already retained descriptor pair."""

    if tail_policy not in ("reject", "report"):
        raise JournalError("invalid_model", "events")
    try:
        capsule_identity = os.fstat(capsule_fd)
        parent_identity = os.stat("..", dir_fd=capsule_fd, follow_symlinks=False)
    except OSError:
        raise HistoryError("io_error", "events", None) from None
    scratch_forbidden = frozenset(
        {
            (capsule_identity.st_dev, capsule_identity.st_ino),
            (parent_identity.st_dev, parent_identity.st_ino),
        }
    )
    if event_before.st_size + raw_before.st_size > RESOURCE_LIMITS_V1.mutable_capsule_bytes:
        raise JournalError("resource_limit", "events")
    event_pass1 = _PassState()
    raw_pass2 = _PassState()

    _rewind(event_fd, "events")
    _rewind(raw_fd, "raw")
    validate_event_ledger_v1(
        history_context=history_context,
        scratch_forbidden_namespace_identities=scratch_forbidden,
        reserved_operation_id=reserved_operation_id,
        events=cast(
            Iterator[EventV1],
            _rows(
                event_fd,
                "events",
                RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes,
                None,
                event_before.st_size,
                tail_policy=tail_policy,
                state=event_pass1,
            ),
        ),
    )
    _rewind(event_fd, "events")
    for _scanned in _rows(
        raw_fd,
        "raw",
        RESOURCE_LIMITS_V1.raw_jsonl_row_bytes,
        RESOURCE_LIMITS_V1.raw_rows,
        raw_before.st_size,
        tail_policy=tail_policy,
        state=raw_pass2,
    ):
        pass
    _rewind(raw_fd, "raw")

    event_pass3 = _PassState()
    raw_pass3 = _PassState()

    def events() -> Iterator[EventV1]:
        yield from cast(
            Iterator[EventV1],
            _rows(
                event_fd,
                "events",
                RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes,
                None,
                event_before.st_size,
                tail_policy=tail_policy,
                state=event_pass3,
            ),
        )

    def attempts() -> Iterator[RawAttemptV2]:
        yield from cast(
            Iterator[RawAttemptV2],
            _rows(
                raw_fd,
                "raw",
                RESOURCE_LIMITS_V1.raw_jsonl_row_bytes,
                RESOURCE_LIMITS_V1.raw_rows,
                raw_before.st_size,
                tail_policy=tail_policy,
                state=raw_pass3,
            ),
        )

    history = validate_history_v1(
        capsule=history_context.capsule,
        manifest=history_context.manifest,
        environment=history_context.environment,
        plan=history_context.plan,
        events=events(),
        raw_attempts=attempts(),
        scratch_forbidden_namespace_identities=scratch_forbidden,
        reserved_operation_id=reserved_operation_id,
    )
    event_after = _final_fstat(event_fd, "events")
    raw_after = _final_fstat(raw_fd, "raw")
    event_path_after = _final_path_stat(capsule_fd, "events")
    raw_path_after = _final_path_stat(capsule_fd, "raw")
    if _identity(event_before) != _identity(event_after) or _identity(event_after) != _identity(
        event_path_after
    ):
        raise JournalError("unstable_snapshot", "events") from None
    if _identity(raw_before) != _identity(raw_after) or _identity(raw_after) != _identity(
        raw_path_after
    ):
        raise JournalError("unstable_snapshot", "raw") from None
    if event_pass1 != event_pass3:
        raise JournalError("unstable_snapshot", "events") from None
    if raw_pass2 != raw_pass3:
        raise JournalError("unstable_snapshot", "raw") from None
    pair = JournalPairSnapshotV1(
        JournalSnapshotV1(
            event_before.st_dev,
            event_before.st_ino,
            event_before.st_mode,
            event_before.st_size,
            event_before.st_mtime_ns,
            event_before.st_ctime_ns,
            event_pass3.row_count,
            event_pass3.sha256,
            event_pass3.tail_byte_count,
            event_pass3.tail_sha256,
        ),
        JournalSnapshotV1(
            raw_before.st_dev,
            raw_before.st_ino,
            raw_before.st_mode,
            raw_before.st_size,
            raw_before.st_mtime_ns,
            raw_before.st_ctime_ns,
            raw_pass3.row_count,
            raw_pass3.sha256,
            raw_pass3.tail_byte_count,
            raw_pass3.tail_sha256,
        ),
        history,
        derive_lifecycle_v1(history),
        reserved_operation_id,
    )
    return pair, event_pass3, raw_pass3


def _snapshot_journal_pair(
    capsule_fd: int,
    *,
    history_context: HistoryContextV1,
    tail_policy: TailPolicy,
    reserved_operation_id: UUID | None,
) -> JournalPairSnapshotV1:
    """Stream and reconcile stable event/raw descriptors without mutation."""

    event_fd, event_before = _open(capsule_fd, "events.jsonl", "events")
    raw_fd = -1
    try:
        raw_fd, raw_before = _open(capsule_fd, "raw.jsonl", "raw")
        pair, _event_state, _raw_state = _scan_journal_pair_descriptors(
            capsule_fd,
            event_fd,
            raw_fd,
            event_before,
            raw_before,
            history_context=history_context,
            tail_policy=tail_policy,
            reserved_operation_id=reserved_operation_id,
        )
        return pair
    finally:
        primary_active = sys.exc_info()[0] is not None
        close_failed_ledger: Ledger | None = None
        try:
            os.close(event_fd)
        except OSError:
            close_failed_ledger = "events"
        if raw_fd >= 0:
            try:
                os.close(raw_fd)
            except OSError:
                if close_failed_ledger is None:
                    close_failed_ledger = "raw"
        if close_failed_ledger is not None and not primary_active:
            raise JournalError("io_error", close_failed_ledger) from None


def _snapshot_transaction_pair(
    transaction: JournalTransaction,
    *,
    history_context: HistoryContextV1,
    tail_policy: TailPolicy,
    reserved_operation_id: UUID | None,
) -> JournalPairSnapshotV1:
    """Reconcile history on the exact writable descriptors retained by a transaction."""

    if type(transaction) is not JournalTransaction or transaction._closed or transaction._poisoned:
        raise JournalError("io_error", "events")
    try:
        event_before = _final_fstat(transaction._event_fd, "events")
        raw_before = _final_fstat(transaction._raw_fd, "raw")
        current: tuple[tuple[Ledger, os.stat_result, JournalCursorV1], ...] = (
            ("events", event_before, transaction.events),
            ("raw", raw_before, transaction.raw),
        )
        for ledger, metadata, cursor in current:
            if _append_identity_from_stat(metadata) != _append_identity_from_cursor(cursor):
                raise JournalError("unstable_snapshot", ledger)
        if (
            transaction._immutable_evidence_bytes + event_before.st_size + raw_before.st_size
            > RESOURCE_LIMITS_V1.mutable_capsule_bytes
        ):
            raise JournalError("resource_limit", "events")
        pair, event_state, raw_state = _scan_journal_pair_descriptors(
            transaction._capsule_fd,
            transaction._event_fd,
            transaction._raw_fd,
            event_before,
            raw_before,
            history_context=history_context,
            tail_policy=tail_policy,
            reserved_operation_id=reserved_operation_id,
        )
        scanned: tuple[tuple[Ledger, JournalSnapshotV1, JournalCursorV1], ...] = (
            ("events", pair.events, transaction.events),
            ("raw", pair.raw, transaction.raw),
        )
        for ledger, snapshot, cursor in scanned:
            if (
                snapshot.device,
                snapshot.inode,
                snapshot.mode,
                snapshot.byte_length,
                snapshot.mtime_ns,
                snapshot.row_count,
                snapshot.sha256,
                snapshot.tail_byte_count,
                snapshot.tail_sha256,
            ) != (
                cursor.device,
                cursor.inode,
                cursor.mode,
                cursor.byte_length,
                cursor.mtime_ns,
                cursor.row_count,
                cursor.whole_sha256,
                cursor.tail_byte_count,
                cursor.tail_sha256,
            ):
                raise JournalError("unstable_snapshot", ledger)
        transaction._events = _cursor_from_scan("events", pair.events, event_state)
        transaction._raw = _cursor_from_scan("raw", pair.raw, raw_state)
        assert event_state.whole_hash_state is not None
        assert raw_state.whole_hash_state is not None
        assert event_state.committed_hash_state is not None
        assert raw_state.committed_hash_state is not None
        transaction._whole_hashes = {
            "events": event_state.whole_hash_state.copy(),
            "raw": raw_state.whole_hash_state.copy(),
        }
        transaction._committed_hashes = {
            "events": event_state.committed_hash_state.copy(),
            "raw": raw_state.committed_hash_state.copy(),
        }
        return pair
    except BaseException:
        transaction._poisoned = True
        raise


def snapshot_journal_pair(
    capsule_fd: int,
    *,
    history_context: HistoryContextV1,
    tail_policy: TailPolicy,
    reserved_operation_id: UUID | None = None,
) -> JournalPairSnapshotV1:
    """Return a stable three-pass snapshot or one content-free failure."""

    try:
        return _snapshot_journal_pair(
            capsule_fd,
            history_context=history_context,
            tail_policy=tail_policy,
            reserved_operation_id=reserved_operation_id,
        )
    except (JournalError, HistoryError):
        raise
    except (OSError, RecursionError, TypeError, ValueError):
        raise JournalError("io_error", "events") from None
