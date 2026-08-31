"""Strict canonical attachments for public benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn, Self, cast

from pydantic import model_validator

from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.schema import CapsuleModel


class CanonicalJSONV1Error(ValueError):
    """Raised when a value or byte string violates CanonicalJSONV1."""


def _canonical_json_v1_string(value: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise CanonicalJSONV1Error("strings must already be NFC")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise CanonicalJSONV1Error("strings must be encodable as strict UTF-8") from error
    return value


def _canonical_json_v1_tree(value: object) -> object:
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is str:
        return _canonical_json_v1_string(value)
    if type(value) is list:
        return [_canonical_json_v1_tree(item) for item in cast(list[object], value)]
    if type(value) is tuple:
        return [_canonical_json_v1_tree(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        raw_mapping = cast(dict[object, object], value)
        if not all(type(key) is str for key in raw_mapping):
            raise CanonicalJSONV1Error("object keys must be strings")
        mapping = cast(dict[str, object], raw_mapping)
        validated_items = [(_canonical_json_v1_string(key), item) for key, item in mapping.items()]
        items = sorted(validated_items, key=lambda item: item[0].encode("utf-8"))
        canonical_mapping: dict[str, object] = {}
        for key, item in items:
            canonical_mapping[key] = _canonical_json_v1_tree(item)
        return canonical_mapping
    raise CanonicalJSONV1Error("only null, strings, integer JSON, arrays, and objects are allowed")


def canonical_json_v1(value: object) -> bytes:
    """Encode strict UTF-8 CanonicalJSONV1 without a terminal newline."""

    return json.dumps(
        _canonical_json_v1_tree(value),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def parse_canonical_json_v1(data: bytes) -> object:
    """Parse bytes only when their spelling is already CanonicalJSONV1."""

    def reject_number(_: str) -> NoReturn:
        raise CanonicalJSONV1Error("only integer JSON numbers are allowed")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        if len({key for key, _ in pairs}) != len(pairs):
            raise CanonicalJSONV1Error("duplicate object key")
        return dict(pairs)

    try:
        text = data.decode("utf-8", errors="strict")
        parsed = json.loads(
            text,
            parse_float=reject_number,
            parse_constant=reject_number,
            object_pairs_hook=unique_object,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CanonicalJSONV1Error("invalid CanonicalJSONV1 bytes") from error
    canonical = canonical_json_v1(parsed)
    if canonical != data:
        raise CanonicalJSONV1Error("noncanonical CanonicalJSONV1 bytes")
    return parsed


def canonical_json_v1_digest(domain: str, value: object) -> str:
    """Hash one CanonicalJSONV1 value under an internal NUL-separated domain."""

    if unicodedata.normalize("NFC", domain) != domain or not domain:
        raise CanonicalJSONV1Error("digest domain must be nonempty NFC")
    return hashlib.sha256(domain.encode("utf-8") + b"\0" + canonical_json_v1(value)).hexdigest()


class RationalV1(CapsuleModel):
    """A reduced rational with a strictly positive denominator."""

    numerator: int
    denominator: int

    @model_validator(mode="before")
    @classmethod
    def require_exact_integer_inputs(cls, value: object) -> object:
        if isinstance(value, Mapping):
            for field_name in ("numerator", "denominator"):
                if field_name in value and type(value[field_name]) is not int:
                    raise ValueError("rational components must be exact integers")
        return value

    @model_validator(mode="after")
    def reduce_fraction(self) -> Self:
        if type(self.numerator) is not int or type(self.denominator) is not int:
            raise ValueError("rational components must be exact integers")
        if self.denominator <= 0:
            raise ValueError("rational denominator must be positive")
        divisor = math.gcd(self.numerator, self.denominator)
        normalized_numerator = self.numerator // divisor
        normalized_denominator = self.denominator // divisor
        if normalized_denominator != self.denominator:
            object.__setattr__(self, "numerator", normalized_numerator)
            object.__setattr__(self, "denominator", normalized_denominator)
        return self


def attachment_digest(domain: str, payload_without_id: Mapping[str, object]) -> str:
    """Return the existing capsule digest over an attachment payload without its ID."""

    return stable_digest(domain, dict(payload_without_id))


def write_attachment_json(path: Path, payload: Mapping[str, object]) -> None:
    """Create one canonical LF-terminated attachment without replacing an existing file."""

    encoded = canonical_json(dict(payload)) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short attachment write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
