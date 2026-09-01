"""Deterministic uncompressed checkpoints for verified shard capsules."""

from __future__ import annotations

import errno
import hashlib
import os
import re
import stat
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn, TypeAlias, cast
from uuid import RFC_4122, UUID, uuid4

from pydantic import field_validator

from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.bounded_io import BoundedIOError, open_directory_no_follow
from laconian_eval.capsule.filesystem import (
    FilesystemPosixOps,
    UnsupportedFilesystemError,
    classify_filesystem,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.schema import (
    UUID4,
    CapsuleModel,
    PublicBenchmarkModelId,
    RunName,
    Sha256,
    StrictPositiveInt,
)
from laconian_eval.capsule.verify import (
    VerifiedCheckpointSourceV1,
    _checkpoint_source_member,
    _recheck_checkpoint_source,
    verified_checkpoint_source,
)
from laconian_eval.capsule.verify import (
    _Failure as VerificationFailure,
)

_CHECKPOINT_MESSAGE = "capsule checkpoint rejected"
_SAFE_MODEL_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9.-]{0,127}$")
_BLOCK_BYTES = 512
_READ_CHUNK_BYTES = 64 * 1024
_MAX_TEMPORARY_ATTEMPTS = 128
_TEMP_PREFIX = ".laconian-checkpoint."
_TEMP_SUFFIX = ".tmp"
_CAPSULE_MARKER = "capsule.json"

CheckpointErrorCode: TypeAlias = Literal[
    "invalid_argument",
    "source_rejected",
    "binding_mismatch",
    "resource_limit",
    "unsupported_filesystem",
    "unsafe_path_type",
    "unstable_snapshot",
    "destination_collision",
    "io_error",
    "checkpoint_sidecar_publish_failed",
    "post_publish_integrity_error",
]
_CHECKPOINT_ERROR_CODES = frozenset(
    {
        "invalid_argument",
        "source_rejected",
        "binding_mismatch",
        "resource_limit",
        "unsupported_filesystem",
        "unsafe_path_type",
        "unstable_snapshot",
        "destination_collision",
        "io_error",
        "checkpoint_sidecar_publish_failed",
        "post_publish_integrity_error",
    }
)


class CheckpointError(ContentFreeCapsuleError):
    """Content-free checkpoint failure with a closed machine-readable code."""

    __slots__ = ("code",)

    def __init__(self, code: CheckpointErrorCode) -> None:
        checked = (
            code if type(code) is str and code in _CHECKPOINT_ERROR_CODES else "invalid_argument"
        )
        self.code = cast(CheckpointErrorCode, checked)
        super().__init__(_CHECKPOINT_MESSAGE)


def _fail(code: CheckpointErrorCode) -> NoReturn:
    raise CheckpointError(code)


class CheckpointProvenanceV1(CapsuleModel):
    campaign_id: RunName
    model_id: PublicBenchmarkModelId
    scenario_uid: Sha256
    batch_attempt_id: UUID4
    run_attempt: StrictPositiveInt

    @field_validator("model_id")
    @classmethod
    def require_safe_model_component(cls, value: str) -> str:
        if _SAFE_MODEL_COMPONENT.fullmatch(value) is None:
            raise ValueError("invalid checkpoint model component")
        return value


@dataclass(frozen=True, slots=True)
class CheckpointArtifactV1:
    archive_path: Path
    sidecar_path: Path
    sha256: str
    byte_length: int
    member_count: int


@dataclass(frozen=True, slots=True)
class _Identity:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    link_count: int


@dataclass(slots=True)
class _OwnedTemporary:
    parent_descriptor: int
    name: str
    descriptor: int
    identity: _Identity
    removed: bool = False
    closed: bool = False
    candidate_names: tuple[str, ...] = ()
    restore_pairs: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _RemovalOutcome:
    primary: BaseException | None
    removed: bool
    name: str
    candidates: tuple[str, ...] = ()
    restore_pairs: tuple[tuple[str, str], ...] = ()

    def __iter__(self) -> Iterator[BaseException | bool | None]:
        yield self.primary
        yield self.removed


_CandidateStatus: TypeAlias = Literal["MISSING", "MATCH_EXPECTED", "OTHER", "UNKNOWN"]
_PublicationOwnership: TypeAlias = Literal[
    "NONE",
    "PREEXISTING",
    "POSSIBLY_OWNED",
    "PROVEN_OWNED",
]


@dataclass(frozen=True, slots=True)
class _CandidateObservation:
    name: str
    status: _CandidateStatus
    identity: _Identity | None = None


@dataclass(frozen=True, slots=True)
class _PublishedProof:
    parent_identity: _Identity
    archive_identity: _Identity
    sidecar_identity: _Identity


@dataclass(slots=True)
class _PublicationState:
    archive_ready: bool = False
    archive_ownership: _PublicationOwnership = "NONE"
    sidecar_ownership: _PublicationOwnership = "NONE"
    proof: _PublishedProof | None = None
    archive_identity: _Identity | None = None
    sidecar_identity: _Identity | None = None
    archive_location: tuple[str, ...] = ()
    sidecar_location: tuple[str, ...] = ()
    archive_restore_pairs: tuple[tuple[str, str], ...] = ()
    sidecar_restore_pairs: tuple[tuple[str, str], ...] = ()
    parent_descriptor: int | None = None
    parent_identity: _Identity | None = None
    source_root_identity: _Identity | None = None
    archive_digest: str | None = None
    archive_bytes: int | None = None
    sidecar_started: bool = False
    member_count: int | None = None
    fatal_error: BaseException | None = None


def _default_link_noreplace(
    source_directory_fd: int,
    source_name: str,
    target_directory_fd: int,
    target_name: str,
) -> None:
    PosixOps().link_noreplace(
        source_directory_fd,
        source_name,
        target_directory_fd,
        target_name,
    )


def _default_rename_noreplace(
    source_directory_fd: int,
    source_name: str,
    target_directory_fd: int,
    target_name: str,
) -> None:
    PosixOps().rename_noreplace(
        source_directory_fd,
        source_name,
        target_directory_fd,
        target_name,
    )


def _default_checkpoint(_point: str) -> None:
    return None


@dataclass(frozen=True, slots=True)
class _CheckpointSeams:
    new_uuid: Callable[[], UUID] = uuid4
    write: Callable[[int, bytes], int] = os.write
    fsync: Callable[[int], None] = os.fsync
    link_noreplace: Callable[[int, str, int, str], None] = _default_link_noreplace
    rename_noreplace: Callable[[int, str, int, str], None] = _default_rename_noreplace
    close: Callable[[int], None] = os.close
    checkpoint: Callable[[str], None] = _default_checkpoint


def _identity(metadata: os.stat_result) -> _Identity:
    return _Identity(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_nlink,
    )


def _same_leaf(left: _Identity, right: _Identity) -> bool:
    return (
        left.device,
        left.inode,
        stat.S_IFMT(left.mode),
    ) == (
        right.device,
        right.inode,
        stat.S_IFMT(right.mode),
    )


def _same_quarantined(left: _Identity, right: _Identity) -> bool:
    return (
        left.device,
        left.inode,
        left.mode,
        left.size,
        left.mtime_ns,
        left.link_count,
    ) == (
        right.device,
        right.inode,
        right.mode,
        right.size,
        right.mtime_ns,
        right.link_count,
    )


def _same_published_quarantine(left: _Identity, right: _Identity) -> bool:
    if not _same_leaf(left, right):
        return False
    if (
        left.mode,
        left.size,
        left.mtime_ns,
    ) != (
        right.mode,
        right.size,
        right.mtime_ns,
    ):
        return False
    return left.link_count == right.link_count or (right.link_count == 2 and left.link_count == 1)


def _prefer_failure(
    primary: BaseException | None,
    candidate: BaseException,
) -> BaseException:
    if primary is None or (isinstance(primary, Exception) and not isinstance(candidate, Exception)):
        return candidate
    return primary


def _promote_rollback_failure(
    primary: BaseException | None,
    candidate: BaseException,
) -> BaseException:
    if primary is not None and not isinstance(primary, Exception):
        return primary
    if not isinstance(candidate, Exception):
        return candidate
    return CheckpointError("post_publish_integrity_error")


def _checkpoint(seams: _CheckpointSeams, point: str, *, published: bool) -> None:
    try:
        seams.checkpoint(point)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("post_publish_integrity_error" if published else "io_error")


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int:
        _fail("unsupported_filesystem")
    return value


def _read_flags() -> int:
    return (
        os.O_RDONLY
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_NONBLOCK")
        | _required_flag("O_CLOEXEC")
    )


def _create_flags() -> int:
    return (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_CLOEXEC")
    )


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | _required_flag("O_DIRECTORY")
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_CLOEXEC")
    )


def _strict_provenance(value: object) -> CheckpointProvenanceV1:
    if type(value) is not CheckpointProvenanceV1:
        _fail("invalid_argument")
    failed = False
    try:
        checked = CheckpointProvenanceV1.model_validate(
            CheckpointProvenanceV1.model_dump(
                value,
                mode="python",
                round_trip=True,
                warnings=False,
            )
        )
    except Exception:
        failed = True
    if failed:
        _fail("invalid_argument")
    return checked


def checkpoint_archive_name(provenance: CheckpointProvenanceV1) -> str:
    checked = _strict_provenance(provenance)
    return (
        f"checkpoint-{checked.campaign_id}-{checked.model_id}-"
        f"{checked.scenario_uid}-{checked.batch_attempt_id}-{checked.run_attempt}.tar"
    )


def _artifact_path(value: Path, provenance: CheckpointProvenanceV1) -> tuple[Path, Path, str]:
    try:
        raw = os.fspath(value)
        if type(raw) is not str or not raw or raw.endswith(os.sep):
            _fail("invalid_argument")
        visible = Path(os.path.abspath(raw))
        name = visible.name
        if (
            name != checkpoint_archive_name(provenance)
            or len(name.encode("utf-8", errors="strict")) > RESOURCE_LIMITS_V1.bounded_string_bytes
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in name)
        ):
            _fail("invalid_argument")
        return visible, visible.parent, name
    except CheckpointError:
        raise
    except Exception:
        _fail("invalid_argument")


def _ustar_path(path: str) -> tuple[bytes, bytes]:
    try:
        encoded = path.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _fail("source_rejected")
    if len(encoded) <= 100:
        return b"", encoded
    for position in range(len(encoded) - 1, -1, -1):
        if encoded[position] != 0x2F:
            continue
        prefix = encoded[:position]
        name = encoded[position + 1 :]
        if prefix and name and len(prefix) <= 155 and len(name) <= 100:
            return prefix, name
    _fail("source_rejected")


def _octal(value: int, width: int) -> bytes:
    if type(value) is not int or value < 0:
        _fail("source_rejected")
    encoded = f"{value:0{width - 1}o}".encode("ascii")
    if len(encoded) != width - 1:
        _fail("source_rejected")
    return encoded + b"\0"


def _ustar_header(path: str, kind: str, mode: int, byte_length: int) -> bytes:
    prefix, name = _ustar_path(path)
    if kind not in {"directory", "file"}:
        _fail("source_rejected")
    header = bytearray(_BLOCK_BYTES)
    header[: len(name)] = name
    header[100:108] = _octal(mode, 8)
    header[108:116] = _octal(0, 8)
    header[116:124] = _octal(0, 8)
    header[124:136] = _octal(byte_length if kind == "file" else 0, 12)
    header[136:148] = _octal(0, 12)
    header[148:156] = b"        "
    header[156:157] = b"0" if kind == "file" else b"5"
    header[257:263] = b"ustar\0"
    header[263:265] = b"00"
    header[345 : 345 + len(prefix)] = prefix
    checksum = sum(header)
    encoded_checksum = f"{checksum:06o}".encode("ascii")
    if len(encoded_checksum) != 6:
        _fail("source_rejected")
    header[148:156] = encoded_checksum + b"\0 "
    return bytes(header)


def _write_all(descriptor: int, data: bytes, seams: _CheckpointSeams) -> None:
    offset = 0
    while offset < len(data):
        requested = min(_READ_CHUNK_BYTES, len(data) - offset)
        try:
            written = seams.write(descriptor, data[offset : offset + requested])
        except InterruptedError:
            continue
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("io_error")
        if type(written) is not int or not 0 < written <= requested:
            _fail("io_error")
        offset += written


def _read_retry(descriptor: int, amount: int) -> bytes:
    while True:
        try:
            return os.read(descriptor, amount)
        except InterruptedError:
            continue


def _write_archive(
    source: VerifiedCheckpointSourceV1,
    temporary: _OwnedTemporary,
    seams: _CheckpointSeams,
) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_length = 0

    def emit(data: bytes) -> None:
        nonlocal byte_length
        byte_length += len(data)
        if byte_length > RESOURCE_LIMITS_V1.checkpoint_archive_bytes:
            _fail("resource_limit")
        _write_all(temporary.descriptor, data, seams)
        digest.update(data)

    for record in source.inventory:
        path, kind, mode, member_bytes = record
        with _checkpoint_source_member(source, record) as descriptor:
            emit(_ustar_header(path, kind, mode, member_bytes))
            _checkpoint(seams, f"after_header:{path}", published=False)
            if kind == "file":
                remaining = member_bytes
                while remaining:
                    try:
                        chunk = _read_retry(descriptor, min(_READ_CHUNK_BYTES, remaining))
                    except OSError:
                        _fail("io_error")
                    if not chunk:
                        _fail("unstable_snapshot")
                    emit(chunk)
                    remaining -= len(chunk)
                try:
                    extra = _read_retry(descriptor, 1)
                except OSError:
                    _fail("io_error")
                if extra:
                    _fail("unstable_snapshot")
                padding = (-member_bytes) % _BLOCK_BYTES
                if padding:
                    emit(bytes(padding))
    emit(bytes(2 * _BLOCK_BYTES))
    return digest.hexdigest(), byte_length


def _directory_is_capsule_contained(candidate_fd: int, source_root: _Identity) -> bool:
    current_fd = -1
    pending_fd = -1
    primary: BaseException | None = None
    result: bool | None = None
    try:
        current_fd = os.dup(candidate_fd)
        for _ in range(1024):
            current = _identity(os.fstat(current_fd))
            if _same_leaf(current, source_root):
                result = True
                break
            try:
                os.stat(_CAPSULE_MARKER, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            except OSError:
                _fail("unsafe_path_type")
            else:
                result = True
                break
            pending_fd = os.open("..", _directory_flags(), dir_fd=current_fd)
            parent = _identity(os.fstat(pending_fd))
            if _same_leaf(current, parent):
                result = False
                break
            previous = current_fd
            current_fd = pending_fd
            pending_fd = -1
            os.close(previous)
        if result is None:
            _fail("unsafe_path_type")
    except BaseException as error:
        primary = error
    for descriptor in (pending_fd, current_fd):
        if descriptor < 0:
            continue
        try:
            os.close(descriptor)
        except BaseException as error:
            primary = _prefer_failure(
                primary,
                error if not isinstance(error, Exception) else CheckpointError("io_error"),
            )
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert result is not None
    return result


def _open_output_parent(
    path: Path,
    source: VerifiedCheckpointSourceV1,
) -> tuple[int, _Identity]:
    descriptor: int | None = None
    try:
        descriptor = open_directory_no_follow(path)
        identity = _identity(os.fstat(descriptor))
        if not stat.S_ISDIR(identity.mode):
            _fail("unsafe_path_type")
        classify_filesystem(descriptor, posix=cast(FilesystemPosixOps, PosixOps()))
        source_root = _identity(os.fstat(source.root_descriptor))
        if _directory_is_capsule_contained(descriptor, source_root):
            _fail("invalid_argument")
        reopened = open_directory_no_follow(path)
        try:
            if _identity(os.fstat(reopened)) != identity:
                _fail("unstable_snapshot")
        finally:
            os.close(reopened)
        return descriptor, identity
    except BaseException as error:
        primary = error
    if descriptor is not None:
        try:
            os.close(descriptor)
        except BaseException as error:
            primary = _prefer_failure(primary, error)
    if not isinstance(primary, Exception):
        raise primary.with_traceback(primary.__traceback__)
    if isinstance(primary, CheckpointError):
        raise CheckpointError(primary.code) from None
    if isinstance(primary, BoundedIOError):
        _fail("unsafe_path_type")
    if isinstance(primary, UnsupportedFilesystemError):
        _fail("unsupported_filesystem")
    if isinstance(primary, OSError) and primary.errno in {
        errno.ELOOP,
        errno.ENOTDIR,
        errno.EISDIR,
        errno.ENXIO,
    }:
        _fail("unsafe_path_type")
    _fail("io_error")


def _recheck_output_parent(
    path: Path,
    descriptor: int,
    expected: _Identity,
    source: VerifiedCheckpointSourceV1,
) -> _Identity:
    reopened = -1
    try:
        retained = _identity(os.fstat(descriptor))
        reopened = open_directory_no_follow(path)
        visible = _identity(os.fstat(reopened))
        if not _same_leaf(retained, expected) or retained != visible:
            _fail("unstable_snapshot")
        if _directory_is_capsule_contained(
            descriptor,
            _identity(os.fstat(source.root_descriptor)),
        ):
            _fail("invalid_argument")
        return retained
    except CheckpointError:
        raise
    except (BoundedIOError, OSError):
        _fail("unstable_snapshot")
    finally:
        if reopened >= 0:
            os.close(reopened)


def _create_temporary(
    parent_fd: int,
    *,
    role: str,
    seams: _CheckpointSeams,
) -> _OwnedTemporary:
    for _ in range(_MAX_TEMPORARY_ATTEMPTS):
        try:
            operation_id = seams.new_uuid()
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("invalid_argument")
        if (
            type(operation_id) is not UUID
            or operation_id.version != 4
            or operation_id.variant != RFC_4122
        ):
            _fail("invalid_argument")
        name = f"{_TEMP_PREFIX}{role}.{operation_id}{_TEMP_SUFFIX}"
        try:
            descriptor = os.open(name, _create_flags(), 0o600, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError:
            _fail("io_error")
        opened: _Identity | None = None
        open_error: BaseException | None = None
        for _ in range(2):
            try:
                opened = _identity(os.fstat(descriptor))
                break
            except BaseException as error:
                open_error = _prefer_failure(open_error, error)
        if opened is None:
            try:
                seams.close(descriptor)
            except BaseException as close_error:
                open_error = _prefer_failure(open_error, close_error)
            assert open_error is not None
            if not isinstance(open_error, Exception):
                raise open_error.with_traceback(open_error.__traceback__) from None
            _fail("io_error")
        temporary = _OwnedTemporary(parent_fd, name, descriptor, opened)
        if open_error is not None:
            cleanup_primary = _cleanup_temporary(
                temporary,
                seams,
                open_error
                if not isinstance(open_error, Exception)
                else CheckpointError("io_error"),
            )
            assert cleanup_primary is not None
            raise cleanup_primary.with_traceback(cleanup_primary.__traceback__) from None
        primary: BaseException | None = None
        try:
            visible = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
            if opened != visible or not stat.S_ISREG(opened.mode) or opened.link_count != 1:
                _fail("unsafe_path_type")
            os.fchmod(descriptor, 0o600)
            opened = _identity(os.fstat(descriptor))
            visible = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
            if (
                opened != visible
                or not stat.S_ISREG(opened.mode)
                or stat.S_IMODE(opened.mode) != 0o600
                or opened.size != 0
                or opened.link_count != 1
            ):
                _fail("unsafe_path_type")
            temporary.identity = opened
            return temporary
        except BaseException as error:
            primary = error
        primary = _cleanup_temporary(temporary, seams, primary)
        assert primary is not None
        if isinstance(primary, Exception) and not isinstance(primary, CheckpointError):
            primary = CheckpointError("io_error")
        raise primary.with_traceback(primary.__traceback__)
    _fail("destination_collision")


def _cleanup_temporary(
    temporary: _OwnedTemporary,
    seams: _CheckpointSeams,
    primary: BaseException | None,
) -> BaseException | None:
    if not temporary.removed:
        if not temporary.closed:
            try:
                retained = _identity(os.fstat(temporary.descriptor))
                if not _same_leaf(retained, temporary.identity):
                    raise CheckpointError("unstable_snapshot")
                temporary.identity = retained
            except BaseException as error:
                primary = _prefer_failure(
                    primary,
                    error if not isinstance(error, Exception) else CheckpointError("io_error"),
                )
        outcome = _quarantine_remove(
            temporary.parent_descriptor,
            temporary.candidate_names or temporary.name,
            temporary.identity,
            seams,
            primary,
            published=False,
            restore_pairs=temporary.restore_pairs,
        )
        primary = outcome.primary
        temporary.removed = outcome.removed
        temporary.name = outcome.name
        temporary.candidate_names = outcome.candidates
        temporary.restore_pairs = outcome.restore_pairs
    if not temporary.closed:
        temporary.closed = True
        try:
            seams.close(temporary.descriptor)
        except BaseException as error:
            primary = _prefer_failure(
                primary,
                error if not isinstance(error, Exception) else CheckpointError("io_error"),
            )
    return primary


def _unique_candidate_names(name: str | tuple[str, ...]) -> tuple[str, ...]:
    candidates = (name,) if isinstance(name, str) else name
    return tuple(dict.fromkeys(candidates))


def _is_quarantine_name(name: str) -> bool:
    return name.startswith(f"{_TEMP_PREFIX}quarantine.") and name.endswith(_TEMP_SUFFIX)


def _matches_removal_identity(
    observed: _Identity,
    expected: _Identity,
    *,
    published: bool,
) -> bool:
    if published:
        return _same_published_quarantine(observed, expected)
    if _same_quarantined(observed, expected):
        return True
    return (
        _same_leaf(observed, expected)
        and (observed.mode, observed.size, observed.mtime_ns)
        == (expected.mode, expected.size, expected.mtime_ns)
        and observed.link_count in {1, 2}
        and expected.link_count in {1, 2}
    )


def _cleanup_combiner(
    published: bool,
) -> Callable[[BaseException | None, BaseException], BaseException]:
    return _promote_rollback_failure if published else _prefer_failure


def _observe_removal_candidate(
    parent_fd: int,
    name: str,
    expected: _Identity,
    primary: BaseException | None,
    *,
    published: bool,
) -> tuple[_CandidateObservation, BaseException | None]:
    failure_code: CheckpointErrorCode = "post_publish_integrity_error" if published else "io_error"
    combine = _cleanup_combiner(published)
    saw_missing = False
    saw_unknown = False
    for _ in range(2):
        try:
            observed = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        except FileNotFoundError:
            saw_missing = True
            continue
        except BaseException as error:
            saw_unknown = True
            primary = combine(
                primary,
                error if not isinstance(error, Exception) else CheckpointError(failure_code),
            )
            continue
        status: _CandidateStatus = (
            "MATCH_EXPECTED"
            if _matches_removal_identity(observed, expected, published=published)
            else "OTHER"
        )
        if status == "OTHER":
            primary = combine(primary, CheckpointError(failure_code))
        return _CandidateObservation(name, status, observed), primary
    if saw_unknown:
        return _CandidateObservation(name, "UNKNOWN"), primary
    if saw_missing:
        return _CandidateObservation(name, "MISSING"), primary
    primary = combine(primary, CheckpointError(failure_code))
    return _CandidateObservation(name, "UNKNOWN"), primary


def _observe_removal_candidates(
    parent_fd: int,
    candidates: tuple[str, ...],
    expected: _Identity,
    primary: BaseException | None,
    *,
    published: bool,
) -> tuple[tuple[_CandidateObservation, ...], BaseException | None]:
    observations: list[_CandidateObservation] = []
    for candidate in candidates:
        observation, primary = _observe_removal_candidate(
            parent_fd,
            candidate,
            expected,
            primary,
            published=published,
        )
        observations.append(observation)
    return tuple(observations), primary


def _new_quarantine_name(
    parent_fd: int,
    seams: _CheckpointSeams,
    failure_code: CheckpointErrorCode,
) -> str:
    for _ in range(_MAX_TEMPORARY_ATTEMPTS):
        operation_id = seams.new_uuid()
        if (
            type(operation_id) is not UUID
            or operation_id.version != 4
            or operation_id.variant != RFC_4122
        ):
            raise CheckpointError(failure_code)
        quarantine = f"{_TEMP_PREFIX}quarantine.{operation_id}{_TEMP_SUFFIX}"
        missing_proofs = 0
        for _ in range(2):
            try:
                os.stat(quarantine, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                missing_proofs += 1
                continue
            except BaseException:
                raise
            break
        if missing_proofs == 2:
            return quarantine
    raise CheckpointError(failure_code)


def _quarantine_remove(
    parent_fd: int,
    name: str | tuple[str, ...],
    expected: _Identity,
    seams: _CheckpointSeams,
    primary: BaseException | None,
    *,
    published: bool,
    restore_pairs: tuple[tuple[str, str], ...] = (),
) -> _RemovalOutcome:
    failure_code: CheckpointErrorCode = "post_publish_integrity_error" if published else "io_error"
    combine = _cleanup_combiner(published)
    candidates = _unique_candidate_names(name)
    pending_pairs = tuple(
        dict.fromkeys(
            pair
            for pair in restore_pairs
            if (
                len(pair) == 2 and not _is_quarantine_name(pair[0]) and _is_quarantine_name(pair[1])
            )
        )
    )
    for restore_name, quarantine in pending_pairs:
        candidates = _unique_candidate_names((*candidates, restore_name, quarantine))
    fallback = candidates[0] if candidates else ""
    if not candidates:
        return _RemovalOutcome(primary, True, fallback, ())
    unlinked_expected = False

    for _ in range(_MAX_TEMPORARY_ATTEMPTS):
        observations, primary = _observe_removal_candidates(
            parent_fd,
            candidates,
            expected,
            primary,
            published=published,
        )
        by_name = {item.name: item for item in observations}
        if pending_pairs:
            restore_target_name, quarantine_name = pending_pairs[0]
            restore_target = by_name[restore_target_name]
            pending_other = by_name[quarantine_name]
            pair = (restore_target_name, quarantine_name)
            if restore_target.status == "OTHER" and pending_other.status == "MISSING":
                pending_pairs = tuple(candidate for candidate in pending_pairs if candidate != pair)
                restored_expected_leaf = restore_target.identity is not None and _same_leaf(
                    restore_target.identity, expected
                )
                candidates = tuple(
                    candidate
                    for candidate in candidates
                    if candidate != quarantine_name
                    and (candidate != restore_target_name or restored_expected_leaf)
                )
                continue
            if restore_target.status == "MISSING" and pending_other.status == "OTHER":
                try:
                    seams.rename_noreplace(
                        parent_fd,
                        quarantine_name,
                        parent_fd,
                        restore_target_name,
                    )
                except BaseException as error:
                    primary = combine(
                        primary,
                        error
                        if not isinstance(error, Exception)
                        else CheckpointError(failure_code),
                    )
                    return _RemovalOutcome(
                        primary,
                        False,
                        restore_target_name,
                        candidates,
                        pending_pairs,
                    )
                restored, primary = _observe_removal_candidate(
                    parent_fd,
                    restore_target_name,
                    expected,
                    primary,
                    published=published,
                )
                relocated, primary = _observe_removal_candidate(
                    parent_fd,
                    quarantine_name,
                    expected,
                    primary,
                    published=published,
                )
                if restored.status != "OTHER" or relocated.status != "MISSING":
                    return _RemovalOutcome(
                        primary,
                        False,
                        restore_target_name,
                        candidates,
                        pending_pairs,
                    )
                pending_pairs = tuple(candidate for candidate in pending_pairs if candidate != pair)
                restored_expected_leaf = restored.identity is not None and _same_leaf(
                    restored.identity, expected
                )
                candidates = tuple(
                    candidate
                    for candidate in candidates
                    if candidate != quarantine_name
                    and (candidate != restore_target_name or restored_expected_leaf)
                )
                continue
            if pending_other.status == "MISSING" and restore_target.status in {
                "MATCH_EXPECTED",
                "MISSING",
            }:
                pending_pairs = tuple(candidate for candidate in pending_pairs if candidate != pair)
            elif pending_other.status != "MATCH_EXPECTED":
                return _RemovalOutcome(
                    primary,
                    False,
                    restore_target_name,
                    candidates,
                    pending_pairs,
                )
        matches = [item for item in observations if item.status == "MATCH_EXPECTED"]
        if not matches:
            all_missing = all(item.status == "MISSING" for item in observations)
            has_unknown = any(item.status == "UNKNOWN" for item in observations)
            removed = all_missing or (unlinked_expected and not has_unknown)
            unresolved = tuple(item.name for item in observations if item.status != "MISSING")
            if removed:
                unresolved = ()
            return _RemovalOutcome(
                primary,
                removed,
                unresolved[0] if unresolved else fallback,
                unresolved,
                pending_pairs,
            )

        chosen = next(
            (item for item in matches if _is_quarantine_name(item.name)),
            matches[0],
        )
        if _is_quarantine_name(chosen.name):
            original = next(
                (item for item in observations if not _is_quarantine_name(item.name)),
                None,
            )
            checkpoint_name = original.name if original is not None else chosen.name
            try:
                seams.checkpoint(f"before_quarantine_delete:{checkpoint_name}")
            except BaseException as error:
                primary = combine(
                    primary,
                    error if not isinstance(error, Exception) else CheckpointError(failure_code),
                )
            current, primary = _observe_removal_candidate(
                parent_fd,
                chosen.name,
                expected,
                primary,
                published=published,
            )
            if current.status == "MISSING":
                continue
            if current.status == "UNKNOWN":
                return _RemovalOutcome(primary, False, chosen.name, candidates, pending_pairs)
            if current.status == "OTHER":
                if (
                    original is None
                    or original.status != "MISSING"
                    or (original.name, chosen.name) not in pending_pairs
                ):
                    return _RemovalOutcome(primary, False, chosen.name, candidates, pending_pairs)
                try:
                    seams.rename_noreplace(
                        parent_fd,
                        chosen.name,
                        parent_fd,
                        original.name,
                    )
                except BaseException as error:
                    primary = combine(
                        primary,
                        error
                        if not isinstance(error, Exception)
                        else CheckpointError(failure_code),
                    )
                    retained = _unique_candidate_names((*candidates, original.name, chosen.name))
                    return _RemovalOutcome(primary, False, original.name, retained, pending_pairs)
                continue

            unlink_error: BaseException | None = None
            unlinked = False
            for _ in range(2):
                try:
                    os.unlink(chosen.name, dir_fd=parent_fd)
                    unlinked = True
                    break
                except BaseException as error:
                    unlink_error = _prefer_failure(unlink_error, error)
            if unlink_error is not None:
                primary = combine(
                    primary,
                    unlink_error
                    if not isinstance(unlink_error, Exception)
                    else CheckpointError(failure_code),
                )
            if not unlinked:
                return _RemovalOutcome(primary, False, chosen.name, candidates, pending_pairs)
            unlinked_expected = True
            pending_pairs = tuple(pair for pair in pending_pairs if pair[1] != chosen.name)
            continue

        try:
            quarantine = _new_quarantine_name(parent_fd, seams, failure_code)
        except BaseException as error:
            primary = combine(
                primary,
                error if not isinstance(error, Exception) else CheckpointError(failure_code),
            )
            return _RemovalOutcome(primary, False, chosen.name, candidates, pending_pairs)
        candidates = _unique_candidate_names((*candidates, quarantine))
        pending_pairs = tuple(dict.fromkeys((*pending_pairs, (chosen.name, quarantine))))
        rename_threw = False
        try:
            seams.rename_noreplace(
                parent_fd,
                chosen.name,
                parent_fd,
                quarantine,
            )
        except BaseException as error:
            rename_threw = True
            pending_pairs = tuple(
                pair for pair in pending_pairs if pair != (chosen.name, quarantine)
            )
            primary = combine(
                primary,
                error if not isinstance(error, Exception) else CheckpointError(failure_code),
            )

        after_move, primary = _observe_removal_candidates(
            parent_fd,
            candidates,
            expected,
            primary,
            published=published,
        )
        by_name = {item.name: item for item in after_move}
        moved = by_name[quarantine]
        original = by_name[chosen.name]
        if rename_threw and moved.status != "MATCH_EXPECTED":
            return _RemovalOutcome(primary, False, chosen.name, candidates, pending_pairs)
        if moved.status == "OTHER":
            if original.status != "MISSING":
                return _RemovalOutcome(primary, False, chosen.name, candidates, pending_pairs)
            continue
        if moved.status == "UNKNOWN":
            return _RemovalOutcome(primary, False, quarantine, candidates, pending_pairs)
        if moved.status == "MISSING" and original.status != "MISSING":
            return _RemovalOutcome(primary, False, chosen.name, candidates, pending_pairs)

    primary = combine(primary, CheckpointError(failure_code))
    return _RemovalOutcome(primary, False, fallback, candidates, pending_pairs)


def _hash_descriptor(
    descriptor: int,
    *,
    limit: int,
    expected: _Identity | None = None,
) -> tuple[str, int, _Identity]:
    try:
        before = _identity(os.fstat(descriptor))
        if (
            not stat.S_ISREG(before.mode)
            or before.link_count != 1
            or before.size > limit
            or (expected is not None and before != expected)
        ):
            _fail("unstable_snapshot")
        os.lseek(descriptor, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        remaining = before.size
        while remaining:
            chunk = _read_retry(descriptor, min(_READ_CHUNK_BYTES, remaining))
            if not chunk:
                _fail("unstable_snapshot")
            digest.update(chunk)
            remaining -= len(chunk)
        if _read_retry(descriptor, 1):
            _fail("unstable_snapshot")
        after = _identity(os.fstat(descriptor))
        if after != before:
            _fail("unstable_snapshot")
        return digest.hexdigest(), before.size, after
    except CheckpointError:
        raise
    except OSError:
        _fail("io_error")


def _descriptors_equal(left: int, right: int, byte_length: int) -> bool:
    try:
        os.lseek(left, 0, os.SEEK_SET)
        os.lseek(right, 0, os.SEEK_SET)
        remaining = byte_length
        while remaining:
            amount = min(_READ_CHUNK_BYTES, remaining)
            left_chunk = _read_retry(left, amount)
            right_chunk = _read_retry(right, amount)
            if not left_chunk or left_chunk != right_chunk:
                return False
            remaining -= len(left_chunk)
        return not _read_retry(left, 1) and not _read_retry(right, 1)
    except OSError:
        _fail("io_error")


def _open_existing_regular(parent_fd: int, name: str) -> tuple[int, _Identity] | None:
    try:
        visible = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
    except FileNotFoundError:
        return None
    except OSError:
        _fail("unsafe_path_type")
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _read_flags(), dir_fd=parent_fd)
        opened = _identity(os.fstat(descriptor))
        if (
            opened != visible
            or not stat.S_ISREG(opened.mode)
            or stat.S_IMODE(opened.mode) != 0o600
            or opened.link_count != 1
        ):
            _fail("unsafe_path_type")
    except BaseException as error:
        primary = error
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException as close_error:
                primary = _prefer_failure(primary, close_error)
        if not isinstance(primary, Exception):
            raise primary.with_traceback(primary.__traceback__) from None
        _fail("unsafe_path_type")
    assert descriptor is not None
    return descriptor, opened


def _set_publication_ownership(
    state: _PublicationState,
    *,
    sidecar: bool,
    ownership: _PublicationOwnership,
    output_name: str,
    expected: _Identity,
) -> None:
    tracked = ownership in {"POSSIBLY_OWNED", "PROVEN_OWNED"}
    if sidecar:
        state.sidecar_ownership = ownership
        state.sidecar_identity = expected if tracked else None
        state.sidecar_location = (output_name,) if tracked else ()
        state.sidecar_restore_pairs = ()
        return
    state.archive_ownership = ownership
    state.archive_ready = tracked
    state.archive_identity = expected if tracked else None
    state.archive_location = (output_name,) if tracked else ()
    state.archive_restore_pairs = ()


def _probe_publication_target(
    parent_fd: int,
    output_name: str,
    expected: _Identity,
) -> tuple[_CandidateObservation, BaseException | None, bool]:
    proof_error: BaseException | None = None
    proof_failed = False
    saw_missing = False
    for _ in range(2):
        try:
            observed = _identity(os.stat(output_name, dir_fd=parent_fd, follow_symlinks=False))
        except FileNotFoundError:
            saw_missing = True
            continue
        except BaseException as error:
            proof_error = _prefer_failure(proof_error, error)
            proof_failed = True
            continue
        status: _CandidateStatus = (
            "MATCH_EXPECTED"
            if _same_published_quarantine(observed, expected) and observed.link_count == 2
            else "OTHER"
        )
        return _CandidateObservation(output_name, status, observed), proof_error, proof_failed
    if proof_failed:
        return _CandidateObservation(output_name, "UNKNOWN"), proof_error, True
    if saw_missing:
        return _CandidateObservation(output_name, "MISSING"), proof_error, False
    return _CandidateObservation(output_name, "UNKNOWN"), proof_error, True


def _probe_publication_source(
    descriptor: int,
) -> tuple[_Identity | None, BaseException | None, bool]:
    proof_error: BaseException | None = None
    for _ in range(2):
        try:
            return _identity(os.fstat(descriptor)), proof_error, proof_error is not None
        except BaseException as error:
            proof_error = _prefer_failure(proof_error, error)
    return None, proof_error, True


def _publish_temporary(
    temporary: _OwnedTemporary,
    *,
    output_name: str,
    seams: _CheckpointSeams,
    state: _PublicationState,
    sidecar: bool,
) -> _Identity:
    temporary.identity = _identity(os.fstat(temporary.descriptor))
    visible_temp = _identity(
        os.stat(temporary.name, dir_fd=temporary.parent_descriptor, follow_symlinks=False)
    )
    if (
        temporary.identity != visible_temp
        or not stat.S_ISREG(temporary.identity.mode)
        or stat.S_IMODE(temporary.identity.mode) != 0o600
        or temporary.identity.link_count != 1
    ):
        _fail("unstable_snapshot")
    provisional = _Identity(
        temporary.identity.device,
        temporary.identity.inode,
        temporary.identity.mode,
        temporary.identity.size,
        temporary.identity.mtime_ns,
        temporary.identity.ctime_ns,
        2,
    )
    link_error: BaseException | None = None
    link_returned = False
    try:
        seams.link_noreplace(
            temporary.parent_descriptor,
            temporary.name,
            temporary.parent_descriptor,
            output_name,
        )
        link_returned = True
        _set_publication_ownership(
            state,
            sidecar=sidecar,
            ownership="PROVEN_OWNED",
            output_name=output_name,
            expected=provisional,
        )
    except BaseException as error:
        link_error = error
        _set_publication_ownership(
            state,
            sidecar=sidecar,
            ownership="POSSIBLY_OWNED",
            output_name=output_name,
            expected=provisional,
        )

    target, target_error, target_failed = _probe_publication_target(
        temporary.parent_descriptor,
        output_name,
        provisional,
    )
    retained, retained_error, retained_failed = _probe_publication_source(temporary.descriptor)
    proof_error = target_error
    if retained_error is not None:
        proof_error = _prefer_failure(proof_error, retained_error)
    proof_failed = target_failed or retained_failed
    retained_unlinked = (
        retained is not None
        and _same_quarantined(retained, temporary.identity)
        and retained.link_count == 1
    )
    full_link_proof = (
        target.status == "MATCH_EXPECTED"
        and target.identity is not None
        and retained is not None
        and target.identity == retained
        and retained.link_count == 2
        and stat.S_IMODE(retained.mode) == 0o600
    )
    if link_returned or target.status == "MATCH_EXPECTED":
        ownership: _PublicationOwnership = "PROVEN_OWNED"
    elif target.status == "OTHER" and retained_unlinked:
        ownership = "PREEXISTING"
    elif target.status == "MISSING" and retained_unlinked:
        ownership = "NONE"
    else:
        ownership = "POSSIBLY_OWNED"
    _set_publication_ownership(
        state,
        sidecar=sidecar,
        ownership=ownership,
        output_name=output_name,
        expected=provisional,
    )
    if retained is not None and _same_leaf(retained, temporary.identity):
        temporary.identity = retained

    post_error: BaseException | None = None
    if link_error is not None:
        if not isinstance(link_error, Exception):
            post_error = link_error
        elif ownership == "PREEXISTING":
            post_error = CheckpointError(
                "checkpoint_sidecar_publish_failed" if sidecar else "destination_collision"
            )
        else:
            post_error = CheckpointError(
                "checkpoint_sidecar_publish_failed" if sidecar else "io_error"
            )
    if proof_error is not None:
        post_error = _prefer_failure(post_error, proof_error)
    if proof_failed or (link_returned and not full_link_proof):
        post_error = _prefer_failure(
            post_error,
            CheckpointError("post_publish_integrity_error"),
        )
    if not link_returned and link_error is None:
        post_error = _prefer_failure(post_error, CheckpointError("io_error"))

    cleanup_error = _cleanup_temporary(temporary, seams, post_error)
    if cleanup_error is not None and not temporary.removed:
        cleanup_error = _cleanup_temporary(temporary, seams, cleanup_error)

    final: _Identity | None = None
    final_error: BaseException | None = None
    if ownership in {"POSSIBLY_OWNED", "PROVEN_OWNED"}:
        for _ in range(2):
            try:
                final = _identity(
                    os.stat(
                        output_name,
                        dir_fd=temporary.parent_descriptor,
                        follow_symlinks=False,
                    )
                )
                break
            except BaseException as error:
                final_error = _prefer_failure(final_error, error)
        if final_error is not None:
            cleanup_error = _prefer_failure(cleanup_error, final_error)
        if (
            final is None
            or not _same_published_quarantine(final, provisional)
            or not stat.S_ISREG(final.mode)
            or stat.S_IMODE(final.mode) != 0o600
            or final.link_count != 1
        ):
            cleanup_error = _prefer_failure(
                cleanup_error,
                CheckpointError("post_publish_integrity_error"),
            )
        elif temporary.removed:
            if sidecar:
                state.sidecar_identity = final
            else:
                state.archive_identity = final

    if cleanup_error is not None:
        if not isinstance(cleanup_error, Exception):
            state.fatal_error = cleanup_error
        raise cleanup_error.with_traceback(cleanup_error.__traceback__) from None
    if ownership not in {"POSSIBLY_OWNED", "PROVEN_OWNED"}:
        _fail("checkpoint_sidecar_publish_failed" if sidecar else "destination_collision")
    assert final is not None
    _set_publication_ownership(
        state,
        sidecar=sidecar,
        ownership="PROVEN_OWNED",
        output_name=output_name,
        expected=final,
    )
    return final


def _rollback_published_leaf(
    parent_fd: int,
    name: str | tuple[str, ...],
    expected: _Identity | None,
    primary: BaseException,
    seams: _CheckpointSeams,
    restore_pairs: tuple[tuple[str, str], ...] = (),
) -> _RemovalOutcome:
    if expected is None:
        return _RemovalOutcome(
            _promote_rollback_failure(primary, CheckpointError("post_publish_integrity_error")),
            False,
            name[0] if isinstance(name, tuple) else name,
            name if isinstance(name, tuple) else (name,),
        )
    outcome = _quarantine_remove(
        parent_fd,
        name,
        expected,
        seams,
        primary,
        published=True,
        restore_pairs=restore_pairs,
    )
    assert outcome.primary is not None
    return outcome


def _sync_after_rollback(
    parent_fd: int,
    seams: _CheckpointSeams,
    primary: BaseException,
) -> BaseException:
    try:
        seams.fsync(parent_fd)
    except BaseException as error:
        primary = _promote_rollback_failure(
            primary,
            error
            if not isinstance(error, Exception)
            else CheckpointError("post_publish_integrity_error"),
        )
    return primary


def _read_small_exact(descriptor: int, expected: bytes) -> _Identity:
    digest, length, identity = _hash_descriptor(
        descriptor,
        limit=RESOURCE_LIMITS_V1.bounded_string_bytes * 2,
    )
    if length != len(expected) or digest != hashlib.sha256(expected).hexdigest():
        _fail("post_publish_integrity_error")
    os.lseek(descriptor, 0, os.SEEK_SET)
    if _read_retry(descriptor, len(expected) + 1) != expected:
        _fail("post_publish_integrity_error")
    return identity


def _pack_under_source(
    source: VerifiedCheckpointSourceV1,
    *,
    parent_path: Path,
    archive_name: str,
    provenance: CheckpointProvenanceV1,
    seams: _CheckpointSeams,
    state: _PublicationState,
) -> tuple[str, int, int]:
    if (
        provenance.campaign_id != source.shard.campaign_id
        or provenance.model_id != source.shard.model_id
        or provenance.model_id != source.manifest.provider.model
        or provenance.scenario_uid != source.shard.scenario_uid
    ):
        _fail("binding_mismatch")
    for path, _kind, _mode, _size in source.inventory:
        _ustar_path(path)

    parent_fd: int | None = None
    archive_temp: _OwnedTemporary | None = None
    sidecar_temp: _OwnedTemporary | None = None
    existing_archive_fd: int | None = None
    existing_sidecar_fd: int | None = None
    archive_fd: int | None = None
    sidecar_fd: int | None = None
    primary: BaseException | None = None
    output_archive_identity: _Identity | None = None
    output_sidecar_identity: _Identity | None = None
    archive_digest: str | None = None
    archive_bytes: int | None = None
    try:
        parent_fd, parent_identity = _open_output_parent(parent_path, source)
        state.parent_descriptor = parent_fd
        state.parent_identity = parent_identity
        existing_sidecar = _open_existing_regular(parent_fd, f"{archive_name}.sha256")
        if existing_sidecar is not None:
            existing_sidecar_fd = existing_sidecar[0]
            _fail("destination_collision")
        existing_archive = _open_existing_regular(parent_fd, archive_name)
        if existing_archive is not None:
            existing_archive_fd, _existing_identity = existing_archive

        archive_temp = _create_temporary(parent_fd, role="archive", seams=seams)
        archive_digest, archive_bytes = _write_archive(source, archive_temp, seams)
        state.archive_digest = archive_digest
        state.archive_bytes = archive_bytes
        state.member_count = len(source.inventory)
        seams.fsync(archive_temp.descriptor)
        generated_digest, generated_bytes, generated_identity = _hash_descriptor(
            archive_temp.descriptor,
            limit=RESOURCE_LIMITS_V1.checkpoint_archive_bytes,
        )
        archive_temp.identity = generated_identity
        if generated_digest != archive_digest or generated_bytes != archive_bytes:
            _fail("unstable_snapshot")

        _checkpoint(seams, "before_archive_parent_proof", published=False)
        _recheck_checkpoint_source(source, full=True)
        parent_identity = _recheck_output_parent(parent_path, parent_fd, parent_identity, source)
        if existing_archive_fd is None:
            output_archive_identity = _publish_temporary(
                archive_temp,
                output_name=archive_name,
                seams=seams,
                state=state,
                sidecar=False,
            )
            _checkpoint(seams, "after_archive_link", published=True)
            try:
                parent_identity = _recheck_output_parent(
                    parent_path,
                    parent_fd,
                    parent_identity,
                    source,
                )
            except BaseException as error:
                raise error.with_traceback(error.__traceback__) from None
            try:
                seams.fsync(parent_fd)
            except BaseException as error:
                if not isinstance(error, Exception):
                    raise
                _fail("post_publish_integrity_error")
        else:
            existing_digest, existing_bytes, existing_identity = _hash_descriptor(
                existing_archive_fd,
                limit=RESOURCE_LIMITS_V1.checkpoint_archive_bytes,
            )
            if (
                existing_digest != archive_digest
                or existing_bytes != archive_bytes
                or not _descriptors_equal(
                    archive_temp.descriptor,
                    existing_archive_fd,
                    archive_bytes,
                )
                or _identity(os.stat(archive_name, dir_fd=parent_fd, follow_symlinks=False))
                != existing_identity
            ):
                _fail("destination_collision")
            state.archive_ready = True
            state.archive_ownership = "PREEXISTING"
            state.archive_identity = existing_identity
            output_archive_identity = existing_identity
            primary = _cleanup_temporary(archive_temp, seams, primary)
            archive_temp = None
            if primary is not None:
                raise primary.with_traceback(primary.__traceback__)

        sidecar_bytes = f"{archive_digest}  {archive_name}\n".encode("ascii")
        state.sidecar_started = True
        sidecar_temp = _create_temporary(parent_fd, role="sidecar", seams=seams)
        _write_all(sidecar_temp.descriptor, sidecar_bytes, seams)
        try:
            seams.fsync(sidecar_temp.descriptor)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("checkpoint_sidecar_publish_failed")
        if _read_small_exact(sidecar_temp.descriptor, sidecar_bytes).link_count != 1:
            _fail("checkpoint_sidecar_publish_failed")
        sidecar_temp.identity = _identity(os.fstat(sidecar_temp.descriptor))
        _recheck_checkpoint_source(source, full=True)
        parent_identity = _recheck_output_parent(parent_path, parent_fd, parent_identity, source)
        output_sidecar_identity = _publish_temporary(
            sidecar_temp,
            output_name=f"{archive_name}.sha256",
            seams=seams,
            state=state,
            sidecar=True,
        )
        try:
            parent_identity = _recheck_output_parent(
                parent_path,
                parent_fd,
                parent_identity,
                source,
            )
        except BaseException as error:
            raise error.with_traceback(error.__traceback__) from None
        try:
            seams.fsync(parent_fd)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("post_publish_integrity_error")

        archive_fd = os.open(archive_name, _read_flags(), dir_fd=parent_fd)
        sidecar_fd = os.open(f"{archive_name}.sha256", _read_flags(), dir_fd=parent_fd)
        final_digest, final_bytes, final_archive = _hash_descriptor(
            archive_fd,
            limit=RESOURCE_LIMITS_V1.checkpoint_archive_bytes,
        )
        final_sidecar = _read_small_exact(sidecar_fd, sidecar_bytes)
        if (
            final_digest != archive_digest
            or final_bytes != archive_bytes
            or final_archive != output_archive_identity
            or final_sidecar != output_sidecar_identity
        ):
            _fail("post_publish_integrity_error")
        parent_identity = _recheck_output_parent(parent_path, parent_fd, parent_identity, source)
        state.proof = _PublishedProof(parent_identity, final_archive, final_sidecar)
    except BaseException as error:
        if (
            state.archive_ready
            and state.sidecar_ownership == "NONE"
            and state.sidecar_started
            and isinstance(error, CheckpointError)
            and error.code == "io_error"
        ):
            primary = CheckpointError("checkpoint_sidecar_publish_failed")
        else:
            primary = error
    for temporary in (sidecar_temp, archive_temp):
        if temporary is not None:
            primary = _cleanup_temporary(temporary, seams, primary)
    for descriptor in (sidecar_fd, archive_fd, existing_archive_fd, existing_sidecar_fd):
        if descriptor is None:
            continue
        try:
            seams.close(descriptor)
        except BaseException as error:
            primary = _prefer_failure(
                primary,
                error
                if not isinstance(error, Exception)
                else CheckpointError(
                    "post_publish_integrity_error" if state.archive_ready else "io_error"
                ),
            )
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert archive_digest is not None and archive_bytes is not None
    return archive_digest, archive_bytes, len(source.inventory)


def _map_boundary_error(error: BaseException, state: _PublicationState) -> CheckpointErrorCode:
    if isinstance(error, CheckpointError):
        return error.code
    if isinstance(error, MemoryError):
        return "post_publish_integrity_error" if state.archive_ready else "resource_limit"
    if isinstance(error, VerificationFailure):
        if error.code == "resource_limit":
            return "resource_limit"
        if error.code == "unsupported_filesystem":
            return "unsupported_filesystem"
        if error.code in {"unsafe_path_type", "unexpected_path"}:
            return "unsafe_path_type"
        if error.code == "unstable_snapshot":
            return "post_publish_integrity_error" if state.archive_ready else "unstable_snapshot"
        return "source_rejected"
    if isinstance(error, UnsupportedFilesystemError):
        return "unsupported_filesystem"
    if isinstance(error, BoundedIOError):
        return "unsafe_path_type"
    if isinstance(error, OSError) and error.errno in {
        errno.ELOOP,
        errno.ENOTDIR,
        errno.EISDIR,
        errno.ENXIO,
    }:
        return "unsafe_path_type"
    return "post_publish_integrity_error" if state.archive_ready else "io_error"


def _rollback_state_retained(
    *,
    archive_name: str,
    state: _PublicationState,
    seams: _CheckpointSeams,
    primary: BaseException,
) -> BaseException:
    parent_fd = state.parent_descriptor
    if parent_fd is None:
        return _promote_rollback_failure(primary, CheckpointError("post_publish_integrity_error"))
    if state.sidecar_ownership in {"POSSIBLY_OWNED", "PROVEN_OWNED"}:
        outcome = _rollback_published_leaf(
            parent_fd,
            state.sidecar_location or (f"{archive_name}.sha256",),
            state.sidecar_identity,
            primary,
            seams,
            state.sidecar_restore_pairs,
        )
        combined = outcome.primary
        assert combined is not None
        primary = combined
        state.sidecar_location = outcome.candidates
        state.sidecar_restore_pairs = outcome.restore_pairs
        if outcome.removed:
            state.sidecar_ownership = "NONE"
    if state.archive_ownership in {"POSSIBLY_OWNED", "PROVEN_OWNED"}:
        outcome = _rollback_published_leaf(
            parent_fd,
            state.archive_location or (archive_name,),
            state.archive_identity,
            primary,
            seams,
            state.archive_restore_pairs,
        )
        combined = outcome.primary
        assert combined is not None
        primary = combined
        state.archive_location = outcome.candidates
        state.archive_restore_pairs = outcome.restore_pairs
        if outcome.removed:
            state.archive_ownership = "NONE"
    return _sync_after_rollback(parent_fd, seams, primary)


def _final_proof_retained(
    *,
    parent_path: Path,
    archive_name: str,
    archive_digest: str,
    archive_bytes: int,
    state: _PublicationState,
) -> None:
    parent_fd = state.parent_descriptor
    proof = state.proof
    source_root = state.source_root_identity
    if parent_fd is None or proof is None or source_root is None:
        _fail("post_publish_integrity_error")
    reopened: int | None = None
    archive_fd: int | None = None
    sidecar_fd: int | None = None
    primary: BaseException | None = None
    try:
        retained = _identity(os.fstat(parent_fd))
        reopened = open_directory_no_follow(parent_path)
        visible = _identity(os.fstat(reopened))
        if retained != visible or not _same_leaf(retained, proof.parent_identity):
            _fail("post_publish_integrity_error")
        if _directory_is_capsule_contained(parent_fd, source_root):
            _fail("post_publish_integrity_error")
        archive_fd = os.open(archive_name, _read_flags(), dir_fd=parent_fd)
        sidecar_fd = os.open(f"{archive_name}.sha256", _read_flags(), dir_fd=parent_fd)
        final_digest, final_bytes, final_archive = _hash_descriptor(
            archive_fd,
            limit=RESOURCE_LIMITS_V1.checkpoint_archive_bytes,
        )
        sidecar_bytes = f"{archive_digest}  {archive_name}\n".encode("ascii")
        final_sidecar = _read_small_exact(sidecar_fd, sidecar_bytes)
        if (
            final_digest != archive_digest
            or final_bytes != archive_bytes
            or final_archive != proof.archive_identity
            or final_sidecar != proof.sidecar_identity
            or final_archive
            != _identity(os.stat(archive_name, dir_fd=parent_fd, follow_symlinks=False))
            or final_sidecar
            != _identity(
                os.stat(
                    f"{archive_name}.sha256",
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            )
        ):
            _fail("post_publish_integrity_error")
    except BaseException as error:
        primary = error
    for descriptor in (sidecar_fd, archive_fd, reopened):
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except BaseException as error:
            primary = _prefer_failure(
                primary,
                error
                if not isinstance(error, Exception)
                else CheckpointError("post_publish_integrity_error"),
            )
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)


def _prove_archive_only_retained(
    *,
    parent_path: Path,
    archive_name: str,
    archive_digest: str | None,
    archive_bytes: int | None,
    state: _PublicationState,
) -> bool:
    parent_fd = state.parent_descriptor
    expected = state.archive_identity
    source_root = state.source_root_identity
    if (
        parent_fd is None
        or expected is None
        or source_root is None
        or archive_digest is None
        or archive_bytes is None
    ):
        return False
    reopened: int | None = None
    archive_fd: int | None = None
    result = False
    primary: BaseException | None = None
    try:
        retained = _identity(os.fstat(parent_fd))
        reopened = open_directory_no_follow(parent_path)
        if retained != _identity(os.fstat(reopened)) or _directory_is_capsule_contained(
            parent_fd, source_root
        ):
            result = False
        else:
            archive_fd = os.open(archive_name, _read_flags(), dir_fd=parent_fd)
            digest, length, identity = _hash_descriptor(
                archive_fd,
                limit=RESOURCE_LIMITS_V1.checkpoint_archive_bytes,
            )
            result = (
                digest == archive_digest
                and length == archive_bytes
                and _same_quarantined(identity, expected)
                and identity
                == _identity(os.stat(archive_name, dir_fd=parent_fd, follow_symlinks=False))
            )
    except BaseException as error:
        primary = error
    for descriptor in (archive_fd, reopened):
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException as error:
                primary = _prefer_failure(
                    primary,
                    error
                    if not isinstance(error, Exception)
                    else CheckpointError("post_publish_integrity_error"),
                )
    if primary is not None and not isinstance(primary, Exception):
        raise primary.with_traceback(primary.__traceback__) from None
    return result and primary is None


def _pack_checkpoint(
    capsule_path: Path,
    archive_path: Path,
    *,
    provenance: CheckpointProvenanceV1,
    seams: _CheckpointSeams,
) -> CheckpointArtifactV1:
    checked = _strict_provenance(provenance)
    visible_archive, parent_path, archive_name = _artifact_path(archive_path, checked)
    state = _PublicationState()
    archive_digest: str | None = None
    archive_bytes: int | None = None
    member_count: int | None = None
    primary: BaseException | None = None
    body_error: BaseException | None = None
    exit_error: BaseException | None = None
    boundary = verified_checkpoint_source(capsule_path)
    try:
        source = boundary.__enter__()
        try:
            state.source_root_identity = _identity(os.fstat(source.root_descriptor))
            try:
                archive_digest, archive_bytes, member_count = _pack_under_source(
                    source,
                    parent_path=parent_path,
                    archive_name=archive_name,
                    provenance=checked,
                    seams=seams,
                    state=state,
                )
            except BaseException as error:
                body_error = error
        except BaseException as error:
            body_error = error
        finally:
            archive_digest = state.archive_digest
            archive_bytes = state.archive_bytes
            member_count = state.member_count
            try:
                boundary.__exit__(None, None, None)
            except BaseException as error:
                exit_error = error
    except BaseException as error:
        primary = error
    if primary is None:
        if state.fatal_error is not None:
            primary = state.fatal_error
        elif body_error is not None and not isinstance(body_error, Exception):
            primary = body_error
        elif exit_error is not None:
            primary = exit_error
        else:
            primary = body_error
    if primary is None:
        if (
            archive_digest is None
            or archive_bytes is None
            or member_count is None
            or state.proof is None
        ):
            primary = CheckpointError("post_publish_integrity_error")
        else:
            try:
                _checkpoint(seams, "before_final_output_proof", published=True)
                _final_proof_retained(
                    parent_path=parent_path,
                    archive_name=archive_name,
                    archive_digest=archive_digest,
                    archive_bytes=archive_bytes,
                    state=state,
                )
            except BaseException as error:
                primary = error
    if primary is not None:
        preserve_archive_only = (
            exit_error is None
            and isinstance(body_error, CheckpointError)
            and body_error.code == "checkpoint_sidecar_publish_failed"
            and state.sidecar_ownership == "NONE"
            and state.archive_identity is not None
        )
        if preserve_archive_only:
            try:
                preserve_archive_only = _prove_archive_only_retained(
                    parent_path=parent_path,
                    archive_name=archive_name,
                    archive_digest=archive_digest,
                    archive_bytes=archive_bytes,
                    state=state,
                )
            except BaseException as error:
                primary = _prefer_failure(primary, error)
                preserve_archive_only = False
        if not preserve_archive_only and (
            state.sidecar_ownership in {"POSSIBLY_OWNED", "PROVEN_OWNED"}
            or state.archive_ownership in {"POSSIBLY_OWNED", "PROVEN_OWNED"}
        ):
            primary = _rollback_state_retained(
                archive_name=archive_name,
                state=state,
                seams=seams,
                primary=primary,
            )
    if state.parent_descriptor is not None:
        try:
            seams.close(state.parent_descriptor)
        except BaseException as error:
            primary = _prefer_failure(
                primary,
                error
                if not isinstance(error, Exception)
                else CheckpointError("post_publish_integrity_error"),
            )
        state.parent_descriptor = None
    if primary is not None:
        if not isinstance(primary, Exception):
            raise primary.with_traceback(primary.__traceback__)
        raise CheckpointError(_map_boundary_error(primary, state)) from None
    assert archive_digest is not None and archive_bytes is not None and member_count is not None
    return CheckpointArtifactV1(
        archive_path=visible_archive,
        sidecar_path=Path(f"{visible_archive}.sha256"),
        sha256=archive_digest,
        byte_length=archive_bytes,
        member_count=member_count,
    )


def pack_checkpoint(
    capsule_path: Path,
    archive_path: Path,
    *,
    provenance: CheckpointProvenanceV1,
) -> CheckpointArtifactV1:
    """Write one deterministic uncompressed USTAR archive and SHA-256 sidecar."""

    failure_code: CheckpointErrorCode | None = None
    try:
        return _pack_checkpoint(
            capsule_path,
            archive_path,
            provenance=provenance,
            seams=_CheckpointSeams(),
        )
    except CheckpointError as error:
        failure_code = error.code
    except BaseException:
        raise
    assert failure_code is not None
    raise CheckpointError(failure_code)
