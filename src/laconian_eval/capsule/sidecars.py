"""Seal-bound deterministic scored-capsule sidecars."""

from __future__ import annotations

import errno
import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import InitVar, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, NoReturn, Self, TypeAlias, TypeVar, cast
from uuid import RFC_4122, UUID, uuid4

from pydantic import Field, ValidationError, field_validator, model_validator

from laconian_eval.capsule.boundary_errors import ContentFreeCapsuleError
from laconian_eval.capsule.bounded_io import BoundedIOError, open_directory_no_follow
from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_jsonl,
    sha256_bytes,
    stable_digest,
)
from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    check_nesting_depth,
)
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.schema import CapsuleModel, Sha256
from laconian_eval.capsule.scorable import (
    ScorableError,
    ScoredAttemptV2,
    project_scored_attempts,
)
from laconian_eval.capsule.seal_models import SealV1, seal_bytes
from laconian_eval.capsule.verify import (
    VerifiedSealedCapsuleSourceV1,
    verified_sealed_capsule_source,
)
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import ResponseCase

_SIDECAR_DIGEST_DOMAIN = "laconian-scored-capsule-sidecar-v2"
_SCORING_ALGORITHM_VERSION = "laconian-deterministic-hard-v2"
_SIDECAR_MESSAGE = "scored capsule sidecar rejected"
_SIDECAR_TEMP_PREFIX = ".laconian-scored."
_SIDECAR_TEMP_SUFFIX = ".tmp"
_CAPSULE_MARKER = "capsule.json"
_MAX_TEMPORARY_ATTEMPTS = 128
_READ_CHUNK_BYTES = 64 * 1024
# The sidecar embeds terminal raw evidence, so it inherits the existing aggregate capsule-evidence
# ceiling instead of inventing a second unapproved resource-limit field.
_SIDECAR_MAX_BYTES = RESOURCE_LIMITS_V1.mutable_capsule_bytes
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ModelT = TypeVar("_ModelT", bound=CapsuleModel)
_VERIFIED_SCORED_CONSTRUCTION_AUTHORITY = object()

SidecarErrorCode: TypeAlias = Literal[
    "invalid_argument",
    "source_rejected",
    "scoring_rejected",
    "resource_limit",
    "missing_path",
    "destination_collision",
    "unsupported_filesystem",
    "unsafe_path_type",
    "noncanonical_json",
    "sidecar_mismatch",
    "unstable_snapshot",
    "io_error",
    "post_publish_integrity_error",
    "post_publish_cleanup_failed",
    "post_publish_fsync_failed",
    "post_publish_close_failed",
]
_SIDECAR_ERROR_CODES: frozenset[str] = frozenset(
    {
        "invalid_argument",
        "source_rejected",
        "scoring_rejected",
        "resource_limit",
        "missing_path",
        "destination_collision",
        "unsupported_filesystem",
        "unsafe_path_type",
        "noncanonical_json",
        "sidecar_mismatch",
        "unstable_snapshot",
        "io_error",
        "post_publish_integrity_error",
        "post_publish_cleanup_failed",
        "post_publish_fsync_failed",
        "post_publish_close_failed",
    }
)


class SidecarError(ContentFreeCapsuleError):
    """Content-free sidecar failure with a closed machine-readable code."""

    __slots__ = ("code",)

    def __init__(self, code: SidecarErrorCode) -> None:
        checked = code if type(code) is str and code in _SIDECAR_ERROR_CODES else "invalid_argument"
        self.code = cast(SidecarErrorCode, checked)
        super().__init__(_SIDECAR_MESSAGE)


def _fail(code: SidecarErrorCode) -> NoReturn:
    raise SidecarError(code)


@dataclass(frozen=True, slots=True)
class _Identity:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    link_count: int


@dataclass(frozen=True, slots=True)
class _PublishedSidecar:
    parent_identity: _Identity
    output_identity: _Identity


_DirectoryLeaf = tuple[int, int, int]


@dataclass(slots=True)
class _JsonDepthState:
    depth: int = 0
    in_string: bool = False
    escaped: bool = False

    def feed(self, data: bytes) -> None:
        for byte in data:
            if self.in_string:
                if self.escaped:
                    self.escaped = False
                elif byte == 0x5C:
                    self.escaped = True
                elif byte == 0x22:
                    self.in_string = False
                continue
            if byte == 0x22:
                self.in_string = True
            elif byte in (0x5B, 0x7B):
                self.depth += 1
                if self.depth > RESOURCE_LIMITS_V1.nesting_depth:
                    _fail("resource_limit")
            elif byte in (0x5D, 0x7D):
                self.depth -= 1
                if self.depth < 0:
                    _fail("noncanonical_json")


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
    return _directory_leaf(left) == _directory_leaf(right)


def _directory_leaf(identity: _Identity) -> _DirectoryLeaf:
    return identity.device, identity.inode, stat.S_IFMT(identity.mode)


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


def _default_checkpoint(_point: str) -> None:
    return None


@dataclass(frozen=True, slots=True)
class _SidecarSeams:
    new_uuid: Callable[[], UUID] = uuid4
    write: Callable[[int, bytes], int] = os.write
    fsync: Callable[[int], None] = os.fsync
    link_noreplace: Callable[[int, str, int, str], None] = _default_link_noreplace
    close: Callable[[int], None] = os.close
    checkpoint: Callable[[str], None] = _default_checkpoint


def _sidecar_digest_payload(
    *,
    sidecar_schema_version: str,
    scoring_algorithm_version: str,
    capsule_sha256: str,
    manifest_sha256: str,
    case_index_sha256: str,
    plan_sha256: str,
    raw_sha256: str,
    ordered_plan_item_ids: tuple[str, ...],
    scored_attempts: tuple[ScoredAttemptV2, ...],
) -> dict[str, object]:
    return {
        "sidecar_schema_version": sidecar_schema_version,
        "scoring_algorithm_version": scoring_algorithm_version,
        "capsule_sha256": capsule_sha256,
        "manifest_sha256": manifest_sha256,
        "case_index_sha256": case_index_sha256,
        "plan_sha256": plan_sha256,
        "raw_sha256": raw_sha256,
        "ordered_plan_item_ids": ordered_plan_item_ids,
        "scored_attempts": [
            ScoredAttemptV2.model_dump(
                row,
                mode="json",
                round_trip=True,
                warnings=False,
            )
            for row in scored_attempts
        ],
    }


class ScoredCapsuleSidecarV2(CapsuleModel):
    sidecar_schema_version: Literal["2"]
    scoring_algorithm_version: Literal["laconian-deterministic-hard-v2"]
    capsule_sha256: Sha256
    manifest_sha256: Sha256
    case_index_sha256: Sha256
    plan_sha256: Sha256
    raw_sha256: Sha256
    ordered_plan_item_ids: tuple[Sha256, ...] = Field(min_length=1)
    scored_attempts: tuple[ScoredAttemptV2, ...] = Field(min_length=1)
    sidecar_sha256: Sha256

    @field_validator("scored_attempts", mode="before")
    @classmethod
    def reject_scored_subclasses(cls, value: object) -> object:
        if isinstance(value, (list, tuple)) and any(
            isinstance(row, ScoredAttemptV2) and type(row) is not ScoredAttemptV2 for row in value
        ):
            raise ValueError("scored-attempt subclass rejected")
        return value

    @model_validator(mode="after")
    def bind_order_and_self_hash(self) -> Self:
        if (
            len(self.ordered_plan_item_ids) != len(self.scored_attempts)
            or len(self.scored_attempts) > RESOURCE_LIMITS_V1.plan_rows
            or len(set(self.ordered_plan_item_ids)) != len(self.ordered_plan_item_ids)
        ):
            raise ValueError("scored-sidecar order mismatch")
        checked_rows: list[ScoredAttemptV2] = []
        try:
            for ordinal, (plan_item_id, row) in enumerate(
                zip(self.ordered_plan_item_ids, self.scored_attempts, strict=True)
            ):
                if type(row) is not ScoredAttemptV2:
                    raise ValueError
                payload = ScoredAttemptV2.model_dump(
                    row,
                    mode="python",
                    round_trip=True,
                    warnings=False,
                )
                checked = ScoredAttemptV2.model_validate(payload)
                if checked != row or row.ordinal != ordinal or row.plan_item_id != plan_item_id:
                    raise ValueError
                checked_rows.append(checked)
        except Exception:
            raise ValueError("invalid nested scored attempt") from None
        expected = stable_digest(
            _SIDECAR_DIGEST_DOMAIN,
            _sidecar_digest_payload(
                sidecar_schema_version=self.sidecar_schema_version,
                scoring_algorithm_version=self.scoring_algorithm_version,
                capsule_sha256=self.capsule_sha256,
                manifest_sha256=self.manifest_sha256,
                case_index_sha256=self.case_index_sha256,
                plan_sha256=self.plan_sha256,
                raw_sha256=self.raw_sha256,
                ordered_plan_item_ids=self.ordered_plan_item_ids,
                scored_attempts=tuple(checked_rows),
            ),
        )
        if self.sidecar_sha256 != expected:
            raise ValueError("scored-sidecar self-hash mismatch")
        return self


def _strict_model_copy(
    model_type: type[_ModelT],
    value: object,
) -> _ModelT:
    if type(value) is not model_type:
        raise TypeError
    payload = model_type.model_dump(
        value,
        mode="python",
        round_trip=True,
        warnings=False,
    )
    return model_type.model_validate(payload)


def _strict_response_case(value: object) -> ResponseCase:
    if type(value) is not ResponseCase:
        raise TypeError
    payload = ResponseCase.model_dump(
        value,
        mode="python",
        round_trip=True,
        warnings=False,
    )
    return ResponseCase.model_validate(payload)


@dataclass(frozen=True, slots=True)
class VerifiedScoredCapsuleV2:
    seal: SealV1
    capsule_sha256: str
    manifest: ResolvedManifestV2
    manifest_sha256: str
    plan_sha256: str
    plan: tuple[PlanRowV1, ...]
    scored_attempts: tuple[ScoredAttemptV2, ...]
    cases_by_uid: Mapping[str, ResponseCase]
    _construction_authority: InitVar[object] = None

    def __post_init__(self, _construction_authority: object) -> None:
        try:
            if _construction_authority is not _VERIFIED_SCORED_CONSTRUCTION_AUTHORITY:
                raise TypeError
            seal = _strict_model_copy(SealV1, self.seal)
            manifest = _strict_model_copy(ResolvedManifestV2, self.manifest)
            if (
                type(self.capsule_sha256) is not str
                or _SHA256_PATTERN.fullmatch(self.capsule_sha256) is None
                or type(self.manifest_sha256) is not str
                or _SHA256_PATTERN.fullmatch(self.manifest_sha256) is None
                or type(self.plan_sha256) is not str
                or _SHA256_PATTERN.fullmatch(self.plan_sha256) is None
                or type(self.plan) is not tuple
                or type(self.scored_attempts) is not tuple
                or type(self.cases_by_uid) is not type(MappingProxyType({}))
            ):
                raise TypeError
            plan = tuple(_strict_model_copy(PlanRowV1, row) for row in self.plan)
            scored = tuple(_strict_model_copy(ScoredAttemptV2, row) for row in self.scored_attempts)
            cases = {
                key: _strict_response_case(value)
                for key, value in cast(
                    Mapping[str, ResponseCase],
                    self.cases_by_uid,
                ).items()
            }
            ordered_case_uids = tuple(dict.fromkeys(row.case_uid for row in plan))
            seal_files = {item.path: item for item in seal.files}
            manifest_bytes = canonical_json(
                ResolvedManifestV2.model_dump(
                    manifest,
                    mode="json",
                    round_trip=True,
                    warnings=False,
                )
            )
            plan_bytes = canonical_jsonl(
                PlanRowV1.model_dump(
                    row,
                    mode="json",
                    round_trip=True,
                    warnings=False,
                )
                for row in plan
            )
            if (
                not plan
                or len(plan) != len(scored)
                or seal.generation_status != "complete"
                or seal.structural_integrity != "valid"
                or self.capsule_sha256 != sha256_bytes(seal_bytes(seal))
                or "manifest.json" not in seal_files
                or "plan.jsonl" not in seal_files
                or self.manifest_sha256 != seal_files["manifest.json"].sha256
                or self.plan_sha256 != seal_files["plan.jsonl"].sha256
                or self.manifest_sha256 != sha256_bytes(manifest_bytes)
                or self.plan_sha256 != sha256_bytes(plan_bytes)
                or tuple(row.ordinal for row in plan) != tuple(range(len(plan)))
                or tuple(row.plan_item_id for row in plan)
                != tuple(row.plan_item_id for row in scored)
                or tuple(cases) != ordered_case_uids
            ):
                raise TypeError
            for row in plan:
                case = cases[row.case_uid]
                if (
                    case.id != row.case_id
                    or case.locale != row.locale
                    or response_case_sha256(case) != row.case_definition_sha256
                    or sha256_bytes(case.prompt.encode("utf-8", errors="strict"))
                    != row.prompt_sha256
                ):
                    raise TypeError
            projected = project_scored_attempts(
                plan=plan,
                raw_attempts=tuple(row.raw for row in scored),
                cases_by_uid=cases,
            )
            if projected != scored:
                raise TypeError
            object.__setattr__(self, "seal", seal)
            object.__setattr__(self, "manifest", manifest)
            object.__setattr__(self, "plan", plan)
            object.__setattr__(self, "scored_attempts", scored)
            object.__setattr__(self, "cases_by_uid", MappingProxyType(cases))
        except Exception:
            pass
        else:
            return
        raise SidecarError("sidecar_mismatch") from None


def _sidecar_from_source(
    source: VerifiedSealedCapsuleSourceV1,
) -> ScoredCapsuleSidecarV2:
    if type(source) is not VerifiedSealedCapsuleSourceV1:
        _fail("source_rejected")
    try:
        scored_attempts = project_scored_attempts(
            plan=source.plan,
            raw_attempts=source.raw_attempts,
            cases_by_uid=source.cases_by_uid,
        )
    except ScorableError:
        _fail("scoring_rejected")
    try:
        capsule_sha256 = source.result.capsule_sha256
        if type(capsule_sha256) is not str:
            _fail("source_rejected")
        ordered_plan_item_ids = tuple(row.plan_item_id for row in source.plan)
        payload = _sidecar_digest_payload(
            sidecar_schema_version="2",
            scoring_algorithm_version=_SCORING_ALGORITHM_VERSION,
            capsule_sha256=capsule_sha256,
            manifest_sha256=sha256_bytes(source.manifest_bytes),
            case_index_sha256=sha256_bytes(source.case_index_bytes),
            plan_sha256=sha256_bytes(source.plan_bytes),
            raw_sha256=sha256_bytes(source.raw_bytes),
            ordered_plan_item_ids=ordered_plan_item_ids,
            scored_attempts=scored_attempts,
        )
        return ScoredCapsuleSidecarV2.model_validate(
            payload
            | {
                "sidecar_sha256": stable_digest(
                    _SIDECAR_DIGEST_DOMAIN,
                    payload,
                )
            }
        )
    except SidecarError:
        raise
    except MemoryError:
        _fail("resource_limit")
    except Exception:
        _fail("source_rejected")


def _sidecar_bytes(sidecar: ScoredCapsuleSidecarV2) -> bytes:
    try:
        checked = _strict_model_copy(ScoredCapsuleSidecarV2, sidecar)
        return canonical_json(
            ScoredCapsuleSidecarV2.model_dump(
                checked,
                mode="json",
                round_trip=True,
                warnings=False,
            )
        )
    except SidecarError:
        raise
    except MemoryError:
        _fail("resource_limit")
    except Exception:
        _fail("sidecar_mismatch")


def _artifact_path(value: Path) -> tuple[Path, Path, str]:
    try:
        raw = os.fspath(value)
        if type(raw) is not str or not raw or raw.endswith(os.sep):
            _fail("invalid_argument")
        visible = Path(os.path.abspath(raw))
        name = visible.name
        folded_name = name.casefold()
        encoded_name = name.encode("utf-8", errors="strict")
        if (
            not name
            or name in {".", ".."}
            or folded_name == _CAPSULE_MARKER
            or (
                folded_name.startswith(_SIDECAR_TEMP_PREFIX)
                and folded_name.endswith(_SIDECAR_TEMP_SUFFIX)
            )
            or len(encoded_name) > RESOURCE_LIMITS_V1.bounded_string_bytes
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in name)
        ):
            _fail("invalid_argument")
        return visible, visible.parent, name
    except SidecarError:
        raise
    except Exception:
        _fail("invalid_argument")


def _directory_flags() -> int:
    flags = os.O_RDONLY
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if type(value) is not int:
            _fail("unsupported_filesystem")
        flags |= value
    return flags


def _read_flags() -> int:
    flags = os.O_RDONLY
    for name in ("O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if type(value) is not int:
            _fail("unsupported_filesystem")
        flags |= value
    return flags


def _create_flags() -> int:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    for name in ("O_NOFOLLOW", "O_CLOEXEC"):
        value = getattr(os, name, None)
        if type(value) is not int:
            _fail("unsupported_filesystem")
        flags |= value
    return flags


def _prefer_failure(
    primary: BaseException | None,
    candidate: BaseException,
) -> BaseException:
    if primary is None or (isinstance(primary, Exception) and not isinstance(candidate, Exception)):
        return candidate
    return primary


def _close_os_descriptor(descriptor: int) -> BaseException | None:
    try:
        os.close(descriptor)
    except BaseException as error:
        return error if not isinstance(error, Exception) else SidecarError("io_error")
    return None


def _directory_is_capsule_contained(
    candidate_fd: int,
    retained_source_leaf: _DirectoryLeaf,
) -> bool:
    pending_fd = -1
    current_fd = -1
    result: bool | None = None
    primary: BaseException | None = None
    try:
        if (
            type(retained_source_leaf) is not tuple
            or len(retained_source_leaf) != 3
            or any(type(value) is not int for value in retained_source_leaf)
            or retained_source_leaf[0] < 0
            or retained_source_leaf[1] < 0
            or retained_source_leaf[2] != stat.S_IFDIR
        ):
            _fail("source_rejected")
        current_fd = os.dup(candidate_fd)
        for _ in range(1024):
            current = _identity(os.fstat(current_fd))
            if _directory_leaf(current) == retained_source_leaf:
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
            close_error = _close_os_descriptor(previous)
            if close_error is not None:
                primary = _prefer_failure(primary, close_error)
                break
        if result is None and primary is None:
            primary = SidecarError("unsafe_path_type")
    except BaseException as error:
        primary = _prefer_failure(
            primary,
            (
                error
                if not isinstance(error, Exception) or isinstance(error, SidecarError)
                else SidecarError("io_error")
            ),
        )
    finally:
        for descriptor in (pending_fd, current_fd):
            if descriptor < 0:
                continue
            close_error = _close_os_descriptor(descriptor)
            if close_error is not None:
                primary = _prefer_failure(primary, close_error)
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert result is not None
    return result


def _recheck_visible_directory(path: Path, descriptor: int, expected: _Identity) -> None:
    reopened = -1
    primary: BaseException | None = None
    try:
        if _identity(os.fstat(descriptor)) != expected:
            _fail("unstable_snapshot")
        reopened = open_directory_no_follow(path)
        if _identity(os.fstat(reopened)) != expected:
            _fail("unstable_snapshot")
    except BaseException as error:
        primary = (
            error
            if not isinstance(error, Exception)
            else (error if isinstance(error, SidecarError) else SidecarError("unstable_snapshot"))
        )
    finally:
        if reopened >= 0:
            close_error = _close_os_descriptor(reopened)
            if close_error is not None:
                primary = _prefer_failure(primary, close_error)
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)


def _recheck_visible_directory_leaf(path: Path, descriptor: int, expected: _Identity) -> _Identity:
    reopened = -1
    retained: _Identity | None = None
    primary: BaseException | None = None
    try:
        retained = _identity(os.fstat(descriptor))
        if not _same_leaf(retained, expected):
            _fail("unstable_snapshot")
        reopened = open_directory_no_follow(path)
        visible = _identity(os.fstat(reopened))
        if not _same_leaf(visible, expected) or visible != retained:
            _fail("unstable_snapshot")
    except BaseException as error:
        primary = (
            error
            if not isinstance(error, Exception)
            else (error if isinstance(error, SidecarError) else SidecarError("unstable_snapshot"))
        )
    finally:
        if reopened >= 0:
            close_error = _close_os_descriptor(reopened)
            if close_error is not None:
                primary = _prefer_failure(primary, close_error)
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert retained is not None
    return retained


def _open_external_parent(
    capsule_path: Path,
    parent_path: Path,
    retained_root_leaf: _DirectoryLeaf,
) -> tuple[int, _Identity]:
    parent_fd = -1
    parent_identity: _Identity | None = None
    primary: BaseException | None = None
    try:
        parent_fd = open_directory_no_follow(parent_path)
        parent_identity = _identity(os.fstat(parent_fd))
        if not stat.S_ISDIR(parent_identity.mode):
            _fail("unsafe_path_type")
        parent_identity = _recheck_external_parent(
            capsule_path=capsule_path,
            parent_path=parent_path,
            parent_fd=parent_fd,
            parent_identity=parent_identity,
            retained_root_leaf=retained_root_leaf,
        )
    except BaseException as error:
        if not isinstance(error, Exception) or isinstance(error, SidecarError):
            primary = error
        elif isinstance(error, BoundedIOError) or (
            isinstance(error, OSError) and error.errno in {errno.ELOOP, errno.ENOTDIR, errno.EISDIR}
        ):
            primary = SidecarError("unsafe_path_type")
        else:
            primary = SidecarError("io_error")
    finally:
        if parent_fd >= 0 and primary is not None:
            close_error = _close_os_descriptor(parent_fd)
            parent_fd = -1
            if close_error is not None:
                primary = _prefer_failure(primary, close_error)
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert parent_fd >= 0 and parent_identity is not None
    return parent_fd, parent_identity


def _recheck_external_parent(
    *,
    capsule_path: Path,
    parent_path: Path,
    parent_fd: int,
    parent_identity: _Identity,
    retained_root_leaf: _DirectoryLeaf,
) -> _Identity:
    capsule_fd = -1
    retained_parent: _Identity | None = None
    primary: BaseException | None = None
    try:
        capsule_fd = open_directory_no_follow(Path(os.path.abspath(os.fspath(capsule_path))))
        visible_capsule = _identity(os.fstat(capsule_fd))
        if (
            not stat.S_ISDIR(visible_capsule.mode)
            or _directory_leaf(visible_capsule) != retained_root_leaf
        ):
            _fail("unstable_snapshot")
        retained_parent = _recheck_visible_directory_leaf(
            parent_path,
            parent_fd,
            parent_identity,
        )
    except BaseException as error:
        if not isinstance(error, Exception) or isinstance(error, SidecarError):
            primary = error
        else:
            primary = SidecarError("unstable_snapshot")
    finally:
        if capsule_fd >= 0:
            close_error = _close_os_descriptor(capsule_fd)
            if close_error is not None:
                primary = _prefer_failure(primary, close_error)
    if primary is not None and not isinstance(primary, Exception):
        raise primary.with_traceback(primary.__traceback__)
    contained = False
    try:
        contained = _directory_is_capsule_contained(parent_fd, retained_root_leaf)
    except BaseException as error:
        candidate = (
            error
            if not isinstance(error, Exception) or isinstance(error, SidecarError)
            else SidecarError("unstable_snapshot")
        )
        primary = _prefer_failure(primary, candidate)
    if contained and (
        primary is None
        or (isinstance(primary, SidecarError) and primary.code == "unstable_snapshot")
    ):
        primary = SidecarError("invalid_argument")
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert retained_parent is not None
    return retained_parent


def _classify_existing_output_leaf(
    *,
    parent_fd: int,
    name: str,
    retained_root_leaf: _DirectoryLeaf,
) -> Literal["missing", "capsule", "other"]:
    leaf_fd = -1
    result: Literal["missing", "capsule", "other"] | None = None
    primary: BaseException | None = None
    try:
        try:
            visible = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
        except FileNotFoundError:
            result = "missing"
        except OSError:
            _fail("unsafe_path_type")
        else:
            result = "other"
            if stat.S_ISDIR(visible.mode):
                leaf_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
                retained = _identity(os.fstat(leaf_fd))
                if not _same_leaf(retained, visible):
                    _fail("unstable_snapshot")
                if _directory_is_capsule_contained(leaf_fd, retained_root_leaf):
                    result = "capsule"
    except BaseException as error:
        primary = (
            error
            if not isinstance(error, Exception) or isinstance(error, SidecarError)
            else SidecarError("unsafe_path_type")
        )
    finally:
        if leaf_fd >= 0:
            close_error = _close_os_descriptor(leaf_fd)
            if close_error is not None:
                primary = _prefer_failure(primary, close_error)
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert result is not None
    return result


def _read_descriptor_exact(
    descriptor: int,
    *,
    limit: int,
    expected: _Identity | None = None,
    scan_json: bool = False,
) -> tuple[bytes, _Identity]:
    try:
        before = _identity(os.fstat(descriptor))
        if not stat.S_ISREG(before.mode):
            _fail("unsafe_path_type")
        if before.size > limit:
            _fail("resource_limit")
        if expected is not None and before != expected:
            _fail("unstable_snapshot")
        os.lseek(descriptor, 0, os.SEEK_SET)
        remaining = before.size
        chunks: list[bytes] = []
        scanner = _JsonDepthState() if scan_json else None
        while remaining:
            chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, remaining))
            if not chunk:
                _fail("unstable_snapshot")
            if scanner is not None:
                scanner.feed(chunk)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail("unstable_snapshot")
        after = _identity(os.fstat(descriptor))
        if after != before:
            _fail("unstable_snapshot")
        return b"".join(chunks), after
    except SidecarError:
        raise
    except MemoryError:
        _fail("resource_limit")
    except OSError:
        _fail("io_error")


def _write_all(descriptor: int, data: bytes, seams: _SidecarSeams) -> None:
    offset = 0
    while offset < len(data):
        requested = min(_READ_CHUNK_BYTES, len(data) - offset)
        try:
            count = seams.write(descriptor, data[offset : offset + requested])
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("io_error")
        if type(count) is not int or not 0 < count <= requested:
            _fail("io_error")
        offset += count


def _checkpoint(seams: _SidecarSeams, point: str, *, published: bool) -> None:
    try:
        seams.checkpoint(point)
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("post_publish_integrity_error" if published else "io_error")


def _publication_error(error: BaseException, *, published: bool) -> BaseException:
    if isinstance(error, SidecarError):
        if published and not error.code.startswith("post_publish_"):
            return SidecarError("post_publish_integrity_error")
        return error
    if not isinstance(error, Exception):
        return error
    if isinstance(error, MemoryError):
        return SidecarError("post_publish_integrity_error" if published else "resource_limit")
    if isinstance(error, (BoundedIOError,)) or (
        isinstance(error, OSError)
        and error.errno in {errno.ELOOP, errno.ENOTDIR, errno.EISDIR, errno.ENXIO}
    ):
        return SidecarError("post_publish_integrity_error" if published else "unsafe_path_type")
    return SidecarError("post_publish_integrity_error" if published else "io_error")


def _publish_sidecar_bytes(
    *,
    capsule_path: Path,
    output_path: Path,
    data: bytes,
    retained_root_leaf: _DirectoryLeaf,
    seams: _SidecarSeams,
) -> _PublishedSidecar:
    if type(data) is not bytes or not data or len(data) > _SIDECAR_MAX_BYTES:
        _fail("resource_limit")
    visible_output, parent_path, output_name = _artifact_path(output_path)
    del visible_output
    parent_fd: int | None = None
    temporary_fd: int | None = None
    output_fd: int | None = None
    temporary_name: str | None = None
    temporary_identity: _Identity | None = None
    temporary_created = False
    temporary_removed = False
    published = False
    publication_proof: _PublishedSidecar | None = None
    primary: BaseException | None = None
    try:
        parent_fd, parent_identity = _open_external_parent(
            capsule_path,
            parent_path,
            retained_root_leaf,
        )
        _recheck_visible_directory(parent_path, parent_fd, parent_identity)
        existing_output = _classify_existing_output_leaf(
            parent_fd=parent_fd,
            name=output_name,
            retained_root_leaf=retained_root_leaf,
        )
        if existing_output == "capsule":
            _fail("invalid_argument")
        if existing_output == "other":
            _fail("destination_collision")

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
            candidate_name = f"{_SIDECAR_TEMP_PREFIX}{operation_id}{_SIDECAR_TEMP_SUFFIX}"
            try:
                temporary_fd = os.open(candidate_name, _create_flags(), 0o600, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temporary_name = candidate_name
            temporary_created = True
            _checkpoint(seams, "after_temporary_open", published=False)
            temporary_identity = _identity(os.fstat(temporary_fd))
            break
        else:
            _fail("destination_collision")

        assert temporary_fd is not None
        assert temporary_name is not None
        assert temporary_identity is not None
        os.fchmod(temporary_fd, 0o600)
        descriptor_identity = _identity(os.fstat(temporary_fd))
        path_identity = _identity(os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False))
        temporary_identity = descriptor_identity
        if (
            not stat.S_ISREG(descriptor_identity.mode)
            or stat.S_IMODE(descriptor_identity.mode) != 0o600
            or descriptor_identity.size != 0
            or descriptor_identity.link_count != 1
            or descriptor_identity != path_identity
        ):
            _fail("unsafe_path_type")
        _checkpoint(seams, "after_temporary_creation", published=False)
        _write_all(temporary_fd, data, seams)
        try:
            seams.fsync(temporary_fd)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("io_error")
        written, temporary_identity = _read_descriptor_exact(
            temporary_fd,
            limit=_SIDECAR_MAX_BYTES,
        )
        path_identity = _identity(os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False))
        if (
            written != data
            or temporary_identity != path_identity
            or not stat.S_ISREG(temporary_identity.mode)
            or stat.S_IMODE(temporary_identity.mode) != 0o600
            or temporary_identity.link_count != 1
        ):
            _fail("unstable_snapshot")
        parent_identity = _recheck_visible_directory_leaf(
            parent_path,
            parent_fd,
            parent_identity,
        )
        _checkpoint(seams, "after_temporary_fsync", published=False)
        _checkpoint(seams, "before_link_noreplace", published=False)
        prelink_bytes, prelink_identity = _read_descriptor_exact(
            temporary_fd,
            limit=_SIDECAR_MAX_BYTES,
            expected=temporary_identity,
        )
        prelink_path = _identity(os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False))
        if (
            prelink_bytes != data
            or prelink_identity != prelink_path
            or not stat.S_ISREG(prelink_identity.mode)
            or stat.S_IMODE(prelink_identity.mode) != 0o600
            or prelink_identity.link_count != 1
        ):
            _fail("unstable_snapshot")
        temporary_identity = prelink_identity
        immediate_descriptor = _identity(os.fstat(temporary_fd))
        immediate_path = _identity(os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False))
        if (
            immediate_descriptor != temporary_identity
            or immediate_path != temporary_identity
            or not stat.S_ISREG(immediate_descriptor.mode)
            or stat.S_IMODE(immediate_descriptor.mode) != 0o600
            or immediate_descriptor.link_count != 1
        ):
            _fail("unstable_snapshot")
        parent_identity = _recheck_external_parent(
            capsule_path=capsule_path,
            parent_path=parent_path,
            parent_fd=parent_fd,
            parent_identity=parent_identity,
            retained_root_leaf=retained_root_leaf,
        )
        try:
            seams.link_noreplace(parent_fd, temporary_name, parent_fd, output_name)
        except FileExistsError:
            try:
                collision_identity = _identity(
                    os.stat(output_name, dir_fd=parent_fd, follow_symlinks=False)
                )
            except OSError:
                _fail("destination_collision")
            if _same_leaf(collision_identity, temporary_identity):
                published = True
                _fail("post_publish_integrity_error")
            _fail("destination_collision")
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            try:
                visible_after_error = _identity(
                    os.stat(output_name, dir_fd=parent_fd, follow_symlinks=False)
                )
            except FileNotFoundError:
                _fail("io_error")
            except OSError:
                _fail("io_error")
            if not _same_leaf(visible_after_error, temporary_identity):
                _fail("io_error")
            published = True
            _fail("post_publish_integrity_error")
        published = True

        try:
            output_fd = os.open(output_name, _read_flags(), dir_fd=parent_fd)
            linked_temp = _identity(os.fstat(temporary_fd))
            linked_path = _identity(
                os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False)
            )
            linked_output_path = _identity(
                os.stat(output_name, dir_fd=parent_fd, follow_symlinks=False)
            )
            linked_output = _identity(os.fstat(output_fd))
        except OSError:
            _fail("post_publish_integrity_error")
        if (
            not stat.S_ISREG(linked_output.mode)
            or stat.S_IMODE(linked_output.mode) != 0o600
            or not all(
                linked_temp == item for item in (linked_path, linked_output_path, linked_output)
            )
            or linked_temp.size != len(data)
            or linked_temp.link_count != 2
            or linked_output.link_count != 2
        ):
            _fail("post_publish_integrity_error")
        retained, _ = _read_descriptor_exact(output_fd, limit=_SIDECAR_MAX_BYTES)
        if retained != data:
            _fail("post_publish_integrity_error")
        _checkpoint(seams, "after_link_noreplace", published=True)

        current_temp = _identity(os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False))
        if not _same_leaf(current_temp, linked_temp):
            _fail("post_publish_cleanup_failed")
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except OSError:
            _fail("post_publish_cleanup_failed")
        temporary_removed = True
        try:
            os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            _fail("post_publish_cleanup_failed")
        else:
            _fail("post_publish_cleanup_failed")
        _checkpoint(seams, "after_temporary_unlink", published=True)

        _recheck_visible_directory_leaf(parent_path, parent_fd, parent_identity)
        _checkpoint(seams, "before_parent_fsync", published=True)
        try:
            seams.fsync(parent_fd)
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("post_publish_fsync_failed")
        _checkpoint(seams, "after_parent_fsync", published=True)
        parent_identity = _identity(os.fstat(parent_fd))
        _recheck_visible_directory(parent_path, parent_fd, parent_identity)
        final_bytes, final_output = _read_descriptor_exact(
            output_fd,
            limit=_SIDECAR_MAX_BYTES,
        )
        _checkpoint(seams, "after_final_output_read", published=True)
        final_path = _identity(os.stat(output_name, dir_fd=parent_fd, follow_symlinks=False))
        if (
            final_bytes != data
            or final_output != final_path
            or not stat.S_ISREG(final_output.mode)
            or stat.S_IMODE(final_output.mode) != 0o600
            or final_output.link_count != 1
            or final_path.link_count != 1
        ):
            _fail("post_publish_integrity_error")
        _recheck_visible_directory(parent_path, parent_fd, parent_identity)
        publication_proof = _PublishedSidecar(
            parent_identity=parent_identity,
            output_identity=final_output,
        )
    except BaseException as error:
        primary = _publication_error(error, published=published)
    finally:
        if (
            parent_fd is not None
            and temporary_name is not None
            and temporary_created
            and not temporary_removed
        ):
            cleanup_identity = temporary_identity
            if cleanup_identity is None and temporary_fd is not None:
                try:
                    cleanup_identity = _identity(os.fstat(temporary_fd))
                except BaseException as error:
                    cleanup_error = (
                        error
                        if not isinstance(error, Exception)
                        else SidecarError(
                            "post_publish_cleanup_failed" if published else "io_error"
                        )
                    )
                    primary = _prefer_failure(primary, cleanup_error)
            try:
                current = _identity(
                    os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False)
                )
            except FileNotFoundError:
                pass
            except BaseException as error:
                cleanup_error = (
                    error
                    if not isinstance(error, Exception)
                    else SidecarError("post_publish_cleanup_failed" if published else "io_error")
                )
                primary = _prefer_failure(primary, cleanup_error)
            else:
                if cleanup_identity is not None and _same_leaf(current, cleanup_identity):
                    try:
                        os.unlink(temporary_name, dir_fd=parent_fd)
                        temporary_removed = True
                    except BaseException as error:
                        cleanup_error = (
                            error
                            if not isinstance(error, Exception)
                            else SidecarError(
                                "post_publish_cleanup_failed" if published else "io_error"
                            )
                        )
                        primary = _prefer_failure(primary, cleanup_error)
                elif primary is None:
                    primary = SidecarError(
                        "post_publish_cleanup_failed" if published else "unstable_snapshot"
                    )

        for label, descriptor in (
            ("output", output_fd),
            ("temporary", temporary_fd),
            ("parent", parent_fd),
        ):
            if descriptor is None:
                continue
            if label == "output":
                output_fd = None
            elif label == "temporary":
                temporary_fd = None
            else:
                parent_fd = None
            try:
                seams.close(descriptor)
            except BaseException as error:
                if primary is None or (
                    isinstance(primary, Exception) and not isinstance(error, Exception)
                ):
                    primary = (
                        error
                        if not isinstance(error, Exception)
                        else SidecarError("post_publish_close_failed" if published else "io_error")
                    )
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert publication_proof is not None
    return publication_proof


def _recheck_published_sidecar_after_source_exit(
    *,
    capsule_path: Path,
    output_path: Path,
    data: bytes,
    retained_root_leaf: _DirectoryLeaf,
    proof: _PublishedSidecar,
    seams: _SidecarSeams,
) -> None:
    _visible_output, parent_path, output_name = _artifact_path(output_path)
    parent_fd: int | None = None
    output_fd: int | None = None
    primary: BaseException | None = None
    try:
        parent_fd, parent_identity = _open_external_parent(
            capsule_path,
            parent_path,
            retained_root_leaf,
        )
        if parent_identity != proof.parent_identity:
            _fail("post_publish_integrity_error")
        output_fd = os.open(output_name, _read_flags(), dir_fd=parent_fd)
        retained_bytes, retained_output = _read_descriptor_exact(
            output_fd,
            limit=_SIDECAR_MAX_BYTES,
            expected=proof.output_identity,
        )
        visible_output = _identity(os.stat(output_name, dir_fd=parent_fd, follow_symlinks=False))
        if (
            retained_bytes != data
            or retained_output != proof.output_identity
            or visible_output != proof.output_identity
            or not stat.S_ISREG(retained_output.mode)
            or stat.S_IMODE(retained_output.mode) != 0o600
            or retained_output.link_count != 1
        ):
            _fail("post_publish_integrity_error")
        final_parent = _recheck_external_parent(
            capsule_path=capsule_path,
            parent_path=parent_path,
            parent_fd=parent_fd,
            parent_identity=parent_identity,
            retained_root_leaf=retained_root_leaf,
        )
        final_output = _identity(os.fstat(output_fd))
        final_visible_output = _identity(
            os.stat(output_name, dir_fd=parent_fd, follow_symlinks=False)
        )
        if (
            final_parent != proof.parent_identity
            or final_output != proof.output_identity
            or final_visible_output != proof.output_identity
            or not stat.S_ISREG(final_output.mode)
            or stat.S_IMODE(final_output.mode) != 0o600
            or final_output.link_count != 1
        ):
            _fail("post_publish_integrity_error")
    except BaseException as error:
        primary = (
            error
            if not isinstance(error, Exception)
            else SidecarError("post_publish_integrity_error")
        )
    finally:
        for descriptor in (output_fd, parent_fd):
            if descriptor is None:
                continue
            try:
                seams.close(descriptor)
            except BaseException as error:
                close_error = (
                    error
                    if not isinstance(error, Exception)
                    else SidecarError("post_publish_close_failed")
                )
                primary = _prefer_failure(primary, close_error)
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)


def _write_scored_sidecar(
    capsule_path: Path,
    output_path: Path,
    *,
    seams: _SidecarSeams | None = None,
) -> str:
    selected = _SidecarSeams() if seams is None else seams
    if type(selected) is not _SidecarSeams or any(
        not callable(value)
        for value in (
            selected.new_uuid,
            selected.write,
            selected.fsync,
            selected.link_noreplace,
            selected.close,
            selected.checkpoint,
        )
    ):
        _fail("invalid_argument")
    _artifact_path(output_path)
    sidecar: ScoredCapsuleSidecarV2 | None = None
    encoded: bytes | None = None
    retained_root_leaf: _DirectoryLeaf | None = None
    publication_proof: _PublishedSidecar | None = None
    published = False
    try:
        with verified_sealed_capsule_source(capsule_path) as source:
            sidecar = _sidecar_from_source(source)
            encoded = _sidecar_bytes(sidecar)
            retained_root_leaf = source._retained_root_leaf
            if len(encoded) > _SIDECAR_MAX_BYTES:
                _fail("resource_limit")
            publication_proof = _publish_sidecar_bytes(
                capsule_path=capsule_path,
                output_path=output_path,
                data=encoded,
                retained_root_leaf=retained_root_leaf,
                seams=selected,
            )
            published = True
        assert encoded is not None
        assert retained_root_leaf is not None
        assert publication_proof is not None
        _recheck_published_sidecar_after_source_exit(
            capsule_path=capsule_path,
            output_path=output_path,
            data=encoded,
            retained_root_leaf=retained_root_leaf,
            proof=publication_proof,
            seams=selected,
        )
    except SidecarError as error:
        if published and not error.code.startswith("post_publish_"):
            _fail("post_publish_integrity_error")
        raise
    except MemoryError:
        _fail("post_publish_integrity_error" if published else "resource_limit")
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        _fail("post_publish_integrity_error" if published else "source_rejected")
    assert sidecar is not None
    return sidecar.sidecar_sha256


def write_scored_sidecar(capsule_path: Path, output_path: Path) -> str:
    """Write one canonical no-replace sidecar for a verified SEALED_COMPLETE capsule."""

    failure_code: SidecarErrorCode | None = None
    try:
        return _write_scored_sidecar(capsule_path, output_path)
    except SidecarError as error:
        failure_code = error.code
    assert failure_code is not None
    raise SidecarError(failure_code) from None


def _check_json_depth_bytes(data: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in data:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > RESOURCE_LIMITS_V1.nesting_depth:
                _fail("resource_limit")
        elif byte in (0x5D, 0x7D):
            depth -= 1
            if depth < 0:
                _fail("noncanonical_json")


def _parse_sidecar_bytes(data: bytes) -> ScoredCapsuleSidecarV2:
    if type(data) is not bytes or not data or len(data) > _SIDECAR_MAX_BYTES:
        _fail("resource_limit" if len(data) > _SIDECAR_MAX_BYTES else "noncanonical_json")
    _check_json_depth_bytes(data)

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def reject_constant(_value: str) -> object:
        raise ValueError

    try:
        decoded = json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        check_nesting_depth(decoded, limit=RESOURCE_LIMITS_V1.nesting_depth)
        if type(decoded) is not dict or canonical_json(decoded) != data:
            _fail("noncanonical_json")
        sidecar = ScoredCapsuleSidecarV2.model_validate(decoded)
        if _sidecar_bytes(sidecar) != data:
            _fail("noncanonical_json")
        return sidecar
    except SidecarError:
        raise
    except MemoryError:
        _fail("resource_limit")
    except ResourceLimitError:
        _fail("resource_limit")
    except RecursionError:
        _fail("resource_limit")
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        TypeError,
        ValueError,
        OverflowError,
    ):
        _fail("noncanonical_json")


def _recheck_sidecar_file(
    *,
    parent_path: Path,
    parent_fd: int,
    parent_identity: _Identity,
    name: str,
    descriptor: int,
    expected_identity: _Identity,
    expected_bytes: bytes,
) -> None:
    _recheck_visible_directory(parent_path, parent_fd, parent_identity)
    data, retained = _read_descriptor_exact(
        descriptor,
        limit=_SIDECAR_MAX_BYTES,
        expected=expected_identity,
        scan_json=True,
    )
    try:
        visible = _identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
    except OSError:
        _fail("unstable_snapshot")
    if data != expected_bytes or retained != visible or visible.link_count != 1:
        _fail("unstable_snapshot")


def _load_verified_scored_capsule(
    capsule_path: Path,
    scored_sidecar_path: Path,
    *,
    seams: _SidecarSeams | None = None,
) -> VerifiedScoredCapsuleV2:
    selected = _SidecarSeams() if seams is None else seams
    if type(selected) is not _SidecarSeams or not callable(selected.close):
        _fail("invalid_argument")
    _visible, parent_path, name = _artifact_path(scored_sidecar_path)
    parent_fd: int | None = None
    sidecar_fd: int | None = None
    primary: BaseException | None = None
    evidence: VerifiedScoredCapsuleV2 | None = None
    parent_identity: _Identity | None = None
    sidecar_identity: _Identity | None = None
    sidecar_bytes: bytes | None = None
    retained_root_leaf: _DirectoryLeaf | None = None
    try:
        try:
            with verified_sealed_capsule_source(capsule_path) as retained_source:
                retained_root_leaf = retained_source._retained_root_leaf
                parent_fd, parent_identity = _open_external_parent(
                    capsule_path,
                    parent_path,
                    retained_root_leaf,
                )
                if (
                    _classify_existing_output_leaf(
                        parent_fd=parent_fd,
                        name=name,
                        retained_root_leaf=retained_root_leaf,
                    )
                    == "capsule"
                ):
                    _fail("invalid_argument")
                try:
                    sidecar_fd = os.open(name, _read_flags(), dir_fd=parent_fd)
                except FileNotFoundError:
                    _fail("missing_path")
                except OSError as error:
                    if error.errno in {errno.ELOOP, errno.ENOTDIR, errno.EISDIR, errno.ENXIO}:
                        _fail("unsafe_path_type")
                    _fail("io_error")
                sidecar_bytes, sidecar_identity = _read_descriptor_exact(
                    sidecar_fd,
                    limit=_SIDECAR_MAX_BYTES,
                    scan_json=True,
                )
                try:
                    path_identity = _identity(
                        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    )
                except OSError:
                    _fail("unstable_snapshot")
                if sidecar_identity != path_identity or sidecar_identity.link_count != 1:
                    _fail("unsafe_path_type")
                parsed = _parse_sidecar_bytes(sidecar_bytes)
                expected = _sidecar_from_source(retained_source)
                expected_bytes = _sidecar_bytes(expected)
                if expected != parsed or expected_bytes != sidecar_bytes:
                    _fail("sidecar_mismatch")
                _recheck_sidecar_file(
                    parent_path=parent_path,
                    parent_fd=parent_fd,
                    parent_identity=parent_identity,
                    name=name,
                    descriptor=sidecar_fd,
                    expected_identity=sidecar_identity,
                    expected_bytes=sidecar_bytes,
                )
                evidence = VerifiedScoredCapsuleV2(
                    seal=retained_source.seal,
                    capsule_sha256=parsed.capsule_sha256,
                    manifest=retained_source.manifest,
                    manifest_sha256=parsed.manifest_sha256,
                    plan_sha256=parsed.plan_sha256,
                    plan=retained_source.plan,
                    scored_attempts=parsed.scored_attempts,
                    cases_by_uid=retained_source.cases_by_uid,
                    _construction_authority=_VERIFIED_SCORED_CONSTRUCTION_AUTHORITY,
                )
                parent_identity = _recheck_external_parent(
                    capsule_path=capsule_path,
                    parent_path=parent_path,
                    parent_fd=parent_fd,
                    parent_identity=parent_identity,
                    retained_root_leaf=retained_root_leaf,
                )
        except SidecarError:
            raise
        except MemoryError:
            _fail("resource_limit")
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            _fail("source_rejected")
        assert (
            parent_fd is not None
            and parent_identity is not None
            and sidecar_fd is not None
            and sidecar_identity is not None
            and sidecar_bytes is not None
            and retained_root_leaf is not None
        )
        parent_identity = _recheck_external_parent(
            capsule_path=capsule_path,
            parent_path=parent_path,
            parent_fd=parent_fd,
            parent_identity=parent_identity,
            retained_root_leaf=retained_root_leaf,
        )
        _recheck_sidecar_file(
            parent_path=parent_path,
            parent_fd=parent_fd,
            parent_identity=parent_identity,
            name=name,
            descriptor=sidecar_fd,
            expected_identity=sidecar_identity,
            expected_bytes=sidecar_bytes,
        )
        parent_identity = _recheck_external_parent(
            capsule_path=capsule_path,
            parent_path=parent_path,
            parent_fd=parent_fd,
            parent_identity=parent_identity,
            retained_root_leaf=retained_root_leaf,
        )
        _recheck_sidecar_file(
            parent_path=parent_path,
            parent_fd=parent_fd,
            parent_identity=parent_identity,
            name=name,
            descriptor=sidecar_fd,
            expected_identity=sidecar_identity,
            expected_bytes=sidecar_bytes,
        )
    except BaseException as error:
        primary = (
            error
            if not isinstance(error, Exception)
            else (
                error
                if isinstance(error, SidecarError)
                else SidecarError(
                    "resource_limit" if isinstance(error, MemoryError) else "io_error"
                )
            )
        )
    finally:
        for label, descriptor in (("sidecar", sidecar_fd), ("parent", parent_fd)):
            if descriptor is None:
                continue
            if label == "sidecar":
                sidecar_fd = None
            else:
                parent_fd = None
            try:
                selected.close(descriptor)
            except BaseException as error:
                if primary is None or (
                    isinstance(primary, Exception) and not isinstance(error, Exception)
                ):
                    primary = (
                        error if not isinstance(error, Exception) else SidecarError("io_error")
                    )
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)
    assert evidence is not None
    return evidence


def load_verified_scored_capsule(
    capsule_path: Path,
    scored_sidecar_path: Path,
) -> VerifiedScoredCapsuleV2:
    """Verify the seal and every sidecar join before exposing scored evidence."""

    failure_code: SidecarErrorCode | None = None
    try:
        return _load_verified_scored_capsule(capsule_path, scored_sidecar_path)
    except SidecarError as error:
        failure_code = error.code
    assert failure_code is not None
    raise SidecarError(failure_code) from None
