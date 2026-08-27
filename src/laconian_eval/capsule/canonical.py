"""Normative byte encoding and digest primitives for generation capsules."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import TypeAlias
from uuid import UUID

JsonScalar: TypeAlias = bool | int | float | str | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def canonical_timestamp(value: datetime) -> str:
    """Project an aware datetime to the capsule's single UTC spelling."""

    if not isinstance(value, datetime):
        raise TypeError("canonical timestamp requires a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("canonical timestamp requires an aware datetime")
    utc_value = value.astimezone(UTC)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _project_path(value: PurePosixPath) -> str:
    if value.is_absolute() or not value.parts or value == PurePosixPath("."):
        raise ValueError("canonical paths must be nonempty and relative")
    if any(part == ".." for part in value.parts):
        raise ValueError("canonical paths must not traverse parent directories")
    return value.as_posix()


def _project(value: object) -> JsonValue:
    if isinstance(value, Enum):
        if not isinstance(value.value, str):
            raise TypeError("canonical JSON supports only string enums")
        return value.value
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, PurePosixPath):
        return _project_path(value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON requires finite floats")
        if value == 0.0:
            return 0.0
        return value
    if isinstance(value, Mapping):
        projected: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON requires string mapping keys")
            projected[key] = _project(item)
        return projected
    if isinstance(value, (list, tuple)):
        return [_project(item) for item in value]
    raise TypeError("unsupported canonical JSON value")


def canonical_json(value: object) -> bytes:
    """Encode a supported value using the normative capsule JSON contract."""

    projected = _project(value)
    encoded = json.dumps(
        projected,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return encoded.encode("utf-8", errors="strict")


def canonical_jsonl(values: Iterable[object]) -> bytes:
    """Encode values as canonical JSON rows, each terminated by one LF."""

    return b"".join(canonical_json(value) + b"\n" for value in values)


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase hexadecimal SHA-256 of exact bytes."""

    if not isinstance(value, bytes):
        raise TypeError("sha256_bytes requires bytes")
    return hashlib.sha256(value).hexdigest()


def _stable_digest(domain: str, payload: object) -> bytes:
    if not isinstance(domain, str):
        raise TypeError("stable digest domain must be a string")
    if not domain or any(ord(character) < 0x20 or ord(character) == 0x7F for character in domain):
        raise ValueError("stable digest domain must be nonempty and contain no controls")
    domain_bytes = domain.encode("utf-8", errors="strict")
    return hashlib.sha256(domain_bytes + b"\x00" + canonical_json(payload)).digest()


def stable_digest(domain: str, payload: object) -> str:
    """Return a lowercase domain-separated SHA-256 digest."""

    return _stable_digest(domain, payload).hex()


def stable_digest_bytes(domain: str, payload: object) -> bytes:
    """Return the raw bytes of a domain-separated SHA-256 digest."""

    return _stable_digest(domain, payload)
