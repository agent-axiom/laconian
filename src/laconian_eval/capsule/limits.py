"""Versioned resource bounds for generation capsules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

_KIB = 1024
_MIB = 1024 * _KIB
_GIB = 1024 * _MIB
_UTF8_CHUNK_CHARACTERS = 4096


class ResourceLimitError(ValueError):
    """A fail-closed resource check with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("resource limit rejected")


@dataclass(frozen=True, slots=True)
class ResourceLimitsV1:
    """The complete binary-unit resource table for capsule schema v1."""

    version: str = "1"
    source_manifest_bytes: int = 1 * _MIB
    case_file_bytes: int = 8 * _MIB
    all_case_files_bytes: int = 64 * _MIB
    arm_member_bytes: int = 2 * _MIB
    all_arm_members_bytes: int = 8 * _MIB
    replay_fixture_bytes: int = 256 * _MIB
    protocol_file_bytes: int = 16 * _MIB
    all_protocol_files_bytes: int = 64 * _MIB
    runner_source_file_bytes: int = 2 * _MIB
    all_runner_source_files_bytes: int = 32 * _MIB
    captured_input_total_bytes: int = 512 * _MIB
    case_records: int = 10_000
    plan_rows: int = 100_000
    raw_rows: int = 600_000
    plan_event_jsonl_row_bytes: int = 1 * _MIB
    raw_jsonl_row_bytes: int = 16 * _MIB
    output_utf8_bytes: int = 2 * _MIB
    output_tokens_per_request: int = 65_536
    output_tokens_plan: int = 10_000_000
    mutable_capsule_bytes: int = 8 * _GIB
    diagnostic_bytes: int = 4 * _KIB
    bounded_string_bytes: int = 1 * _KIB
    nesting_depth: int = 64

    def __post_init__(self) -> None:
        for definition in fields(self):
            value = object.__getattribute__(self, definition.name)
            if definition.name == "version":
                if type(value) is not str or value != "1":
                    raise ResourceLimitError("invalid_resource_limits")
            elif type(value) is not int or value <= 0:
                raise ResourceLimitError("invalid_resource_limits")


RESOURCE_LIMITS_V1 = ResourceLimitsV1()


def _nonnegative_integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ResourceLimitError("invalid_count")
    return value


def bounded_utf8_length(value: str, *, limit: int, code: str) -> int:
    """Return strict UTF-8 length after enforcing a caller-named byte bound."""

    if not isinstance(value, str):
        raise ResourceLimitError("invalid_string")
    checked_limit = _nonnegative_integer(limit)
    character_length = str.__len__(value)
    if character_length > checked_limit:
        raise ResourceLimitError(code)
    byte_length = 0
    for start in range(0, character_length, _UTF8_CHUNK_CHARACTERS):
        chunk = str.__getitem__(value, slice(start, start + _UTF8_CHUNK_CHARACTERS))
        try:
            byte_length += len(chunk.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            raise ResourceLimitError("invalid_utf8") from None
        if byte_length > checked_limit:
            raise ResourceLimitError(code)
    return byte_length


def check_collection_count(count: int, *, limit: int, code: str) -> None:
    """Reject a count above a named item, aggregate, or record bound."""

    checked_count = _nonnegative_integer(count)
    checked_limit = _nonnegative_integer(limit)
    if checked_count > checked_limit:
        raise ResourceLimitError(code)


def check_nesting_depth(
    value: object,
    *,
    limit: int = RESOURCE_LIMITS_V1.nesting_depth,
) -> None:
    """Reject JSON/YAML-like collection nesting deeper than the configured limit."""

    checked_limit = _nonnegative_integer(limit)
    active_containers: set[int] = set()

    def visit(item: object, depth: int) -> None:
        if not isinstance(item, (Mapping, list, tuple)):
            return
        if depth > checked_limit:
            raise ResourceLimitError("nesting_depth_limit")
        identity = id(item)
        if identity in active_containers:
            raise ResourceLimitError("cyclic_structure")
        active_containers.add(identity)
        children = item.values() if isinstance(item, Mapping) else item
        try:
            for child in children:
                visit(child, depth + 1)
        finally:
            active_containers.remove(identity)

    visit(value, 1)


def check_plan_token_exposure(
    max_output_tokens: int,
    plan_rows: int,
    *,
    limits: ResourceLimitsV1 = RESOURCE_LIMITS_V1,
) -> int:
    """Return total output-token exposure after enforcing both token bounds."""

    checked_tokens = _nonnegative_integer(max_output_tokens)
    checked_rows = _nonnegative_integer(plan_rows)
    if checked_tokens > limits.output_tokens_per_request:
        raise ResourceLimitError("output_tokens_per_request_limit")
    exposure = checked_tokens * checked_rows
    if exposure > limits.output_tokens_plan:
        raise ResourceLimitError("output_tokens_plan_limit")
    return exposure


def reserve_attempt_transaction(
    current_capsule_bytes: int,
    *,
    reserved_bytes: int = 0,
    include_epoch_events: bool = False,
    limits: ResourceLimitsV1 = RESOURCE_LIMITS_V1,
) -> int:
    """Return the target reservation for one complete worst-case attempt transaction."""

    checked_current = _nonnegative_integer(current_capsule_bytes)
    checked_reserved = _nonnegative_integer(reserved_bytes)
    if type(include_epoch_events) is not bool:
        raise ResourceLimitError("invalid_flag")

    event_rows = 4 + (2 if include_epoch_events else 0)
    event_bytes = event_rows * (limits.plan_event_jsonl_row_bytes + 1)
    raw_bytes = limits.raw_jsonl_row_bytes + 1
    required_reservation = event_bytes + raw_bytes
    target_reservation = max(checked_reserved, required_reservation)
    if checked_current + target_reservation > limits.mutable_capsule_bytes:
        raise ResourceLimitError("mutable_capsule_limit")
    return target_reservation
