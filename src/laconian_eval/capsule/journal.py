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
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import ValidationError

from laconian_eval.capsule.attempts import RawAttemptV2, raw_attempt_bytes
from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.events import EventError, EventV1, event_bytes, parse_event
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


EventJournalSnapshotV1 = JournalSnapshotV1
RawJournalSnapshotV1 = JournalSnapshotV1


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
        descriptor = os.open(
            name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd
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
        if isinstance(error, JournalError):
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


def _snapshot_journal_pair(
    capsule_fd: int,
    *,
    history_context: HistoryContextV1,
    tail_policy: TailPolicy,
) -> JournalPairSnapshotV1:
    """Stream and reconcile stable event/raw descriptors without mutation."""

    if tail_policy not in ("reject", "report"):
        raise JournalError("invalid_model", "events")
    event_fd, event_before = _open(capsule_fd, "events.jsonl", "events")
    raw_fd = -1
    try:
        raw_fd, raw_before = _open(capsule_fd, "raw.jsonl", "raw")
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

        # Passes one and two establish deterministic event-before-raw validation.
        validate_event_ledger_v1(
            history_context=history_context,
            scratch_forbidden_namespace_identities=scratch_forbidden,
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
        return JournalPairSnapshotV1(
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
        )
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


def snapshot_journal_pair(
    capsule_fd: int,
    *,
    history_context: HistoryContextV1,
    tail_policy: TailPolicy,
) -> JournalPairSnapshotV1:
    """Return a stable three-pass snapshot or one content-free failure."""

    try:
        return _snapshot_journal_pair(
            capsule_fd,
            history_context=history_context,
            tail_policy=tail_policy,
        )
    except (JournalError, HistoryError):
        raise
    except (OSError, RecursionError, TypeError, ValueError):
        raise JournalError("io_error", "events") from None
