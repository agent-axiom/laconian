from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta, timezone
from enum import Enum
from pathlib import PurePosixPath
from uuid import UUID

import pytest

from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_jsonl,
    canonical_timestamp,
    sha256_bytes,
    stable_digest,
    stable_digest_bytes,
)


class SampleEnum(str, Enum):  # noqa: UP042 - contract covers classic string Enum.
    VALUE = "value"


class IntegerEnum(Enum):
    VALUE = 1


def test_canonical_json_projects_supported_values_exactly() -> None:
    value = {
        "z": -0.0,
        "text": "αἴκα",
        "date": date(2026, 8, 27),
        "timestamp": datetime(2026, 8, 27, 9, 34, 56, 123456, tzinfo=UTC),
        "uuid": UUID("12345678-1234-4abc-8def-1234567890ab"),
        "enum": SampleEnum.VALUE,
        "path": PurePosixPath("inputs/cases/000.yaml"),
    }
    expected = (
        '{"date":"2026-08-27","enum":"value","path":"inputs/cases/000.yaml",'
        '"text":"αἴκα","timestamp":"2026-08-27T09:34:56.123456Z",'
        '"uuid":"12345678-1234-4abc-8def-1234567890ab","z":0.0}'
    ).encode()
    assert canonical_json(value) == expected


def test_canonical_jsonl_adds_one_lf_per_row() -> None:
    assert canonical_jsonl(({"b": 2}, {"a": 1})) == b'{"b":2}\n{"a":1}\n'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_nonfinite_numbers(value: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"value": value})


def test_canonical_json_rejects_naive_datetime_lone_surrogate_and_nonstring_key() -> None:
    with pytest.raises(ValueError):
        canonical_json({"at": datetime(2026, 8, 27)})
    with pytest.raises(ValueError):
        canonical_json({"text": "\ud800"})
    with pytest.raises(TypeError):
        canonical_json({1: "value"})


def test_hash_and_stable_digest_use_exact_normative_preimages() -> None:
    payload = {"value": 1}
    encoded = b'{"value":1}'
    preimage = b"laconian-test-v1\x00" + encoded
    expected = hashlib.sha256(preimage).hexdigest()
    assert sha256_bytes(encoded) == hashlib.sha256(encoded).hexdigest()
    assert stable_digest("laconian-test-v1", payload) == expected
    assert stable_digest_bytes("laconian-test-v1", payload) == bytes.fromhex(expected)


def test_canonical_timestamp_converts_offset_to_utc() -> None:
    value = datetime.fromisoformat("2026-08-27T12:34:56.123456+03:00")
    assert canonical_timestamp(value) == "2026-08-27T09:34:56.123456Z"


def test_canonical_timestamp_zero_pads_four_digit_year() -> None:
    value = datetime(1, 1, 2, 3, 4, 5, 6, tzinfo=timezone.utc)  # noqa: UP017
    assert canonical_timestamp(value) == "0001-01-02T03:04:05.000006Z"


def test_canonical_timestamp_does_not_depend_on_platform_year_padding() -> None:
    class UnpaddedPlatformDatetime(datetime):
        def astimezone(self, tz: object = None) -> UnpaddedPlatformDatetime:
            return self

        def strftime(self, format_string: str) -> str:
            assert format_string == "%Y-%m-%dT%H:%M:%S.%fZ"
            return "1-01-02T03:04:05.000006Z"

    value = UnpaddedPlatformDatetime(1, 1, 2, 3, 4, 5, 6, tzinfo=UTC)
    assert canonical_timestamp(value) == "0001-01-02T03:04:05.000006Z"


def test_canonical_json_normalizes_nested_negative_zero() -> None:
    value = {"items": (-0.0, [-0.0, {"value": -0.0}])}
    assert canonical_json(value) == b'{"items":[0.0,[0.0,{"value":0.0}]]}'


def test_canonical_json_accepts_nested_json_containers() -> None:
    value = {"outer": ({"inner": [None, True, 7, 2.5, "text"]},)}
    assert canonical_json(value) == (b'{"outer":[{"inner":[null,true,7,2.5,"text"]}]}')


def test_canonical_timestamp_handles_date_boundary_when_converting_to_utc() -> None:
    value = datetime(
        2026,
        8,
        28,
        0,
        0,
        0,
        1,
        tzinfo=timezone(timedelta(hours=3)),
    )
    assert canonical_timestamp(value) == "2026-08-27T21:00:00.000001Z"


def test_empty_canonical_jsonl_is_empty_bytes() -> None:
    assert canonical_jsonl(()) == b""


@pytest.mark.parametrize(
    "path",
    [
        PurePosixPath("/absolute/path"),
        PurePosixPath("../traversal"),
        PurePosixPath("nested/../traversal"),
        PurePosixPath("."),
    ],
)
def test_canonical_json_rejects_invalid_relative_paths(path: PurePosixPath) -> None:
    with pytest.raises(ValueError):
        canonical_json({"path": path})


def test_canonical_json_preserves_unicode_without_normalization() -> None:
    composed = "é"
    decomposed = "e\u0301"
    assert canonical_json({"value": composed}) != canonical_json({"value": decomposed})


@pytest.mark.parametrize(
    "value",
    [b"bytes", {"set"}, IntegerEnum.VALUE, PurePosixPath("../escape")],
)
def test_canonical_json_rejects_unsupported_objects(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_json(value)


@pytest.mark.parametrize("domain", ["", "contains\x00nul", "contains\nnewline"])
def test_stable_digest_rejects_unsafe_domains(domain: str) -> None:
    with pytest.raises(ValueError):
        stable_digest(domain, {"value": 1})
