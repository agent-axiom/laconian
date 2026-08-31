from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from laconian_eval.benchmark.attachments import (
    CanonicalJSONV1Error,
    RationalV1,
    attachment_digest,
    canonical_json_v1,
    canonical_json_v1_digest,
    parse_canonical_json_v1,
    write_attachment_json,
)
from laconian_eval.capsule.canonical import canonical_json


def test_rational_v1_normalizes_sign_and_reduces_exactly() -> None:
    assert RationalV1(numerator=6, denominator=8).model_dump(mode="json") == {
        "numerator": 3,
        "denominator": 4,
    }
    with pytest.raises(ValidationError):
        RationalV1(numerator=1, denominator=0)


@pytest.mark.parametrize(
    "payload",
    (
        {"numerator": "6", "denominator": 8},
        {"numerator": 6.0, "denominator": 8},
        {"numerator": True, "denominator": 8},
        {"numerator": 6, "denominator": "8"},
        {"numerator": 6, "denominator": 8.0},
        {"numerator": 6, "denominator": False},
    ),
)
def test_rational_v1_requires_exact_integer_inputs(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RationalV1.model_validate(payload)


def test_attachment_digest_is_domain_separated_and_excludes_only_its_id() -> None:
    payload = {
        "schema_version": "1",
        "parent_sha256": "a" * 64,
        "rows": [{"ordinal": 0, "value": 7}],
    }
    expected = hashlib.sha256(
        b"laconian-test-attachment-v1\0" + canonical_json(payload)
    ).hexdigest()
    assert attachment_digest("laconian-test-attachment-v1", payload) == expected
    assert attachment_digest("laconian-other-v1", payload) != expected


def test_canonical_json_v1_is_strict_and_has_no_terminal_newline() -> None:
    assert canonical_json_v1({"é": 1, "a": [2], "verified": True}) == (
        b'{"a":[2],"verified":true,"\xc3\xa9":1}'
    )
    for forbidden in ({"value": "e\u0301"}, {"e\u0301": 1}):
        with pytest.raises(CanonicalJSONV1Error):
            canonical_json_v1(forbidden)
    for forbidden in (1.0, float("nan")):
        with pytest.raises(CanonicalJSONV1Error):
            canonical_json_v1({"value": forbidden})
    for forbidden_bytes in (
        b'{"a":1}\n',
        b'{ "a":1}',
        b'{"a":1,"a":1}',
        b'{"value":"e\\u0301"}',
        b'{"e\\u0301":1}',
    ):
        with pytest.raises(CanonicalJSONV1Error):
            parse_canonical_json_v1(forbidden_bytes)


@pytest.mark.parametrize(
    "value",
    ("\ud800", {"x": "\ud800"}, {"\ud800": "x"}),
    ids=("scalar", "object-value", "object-key"),
)
def test_canonical_json_v1_rejects_lone_surrogates_as_contract_errors(value: object) -> None:
    with pytest.raises(CanonicalJSONV1Error):
        canonical_json_v1(value)


@pytest.mark.parametrize(
    "encoded",
    (b'{"x":"\\ud800"}', b'{"\\ud800":"x"}'),
    ids=("object-value", "object-key"),
)
def test_parse_canonical_json_v1_rejects_escaped_lone_surrogates(encoded: bytes) -> None:
    with pytest.raises(CanonicalJSONV1Error):
        parse_canonical_json_v1(encoded)


@pytest.mark.parametrize(
    ("encoded", "expected"),
    (
        (b"null", None),
        (b"true", True),
        (b"-7", -7),
        (b'"text"', "text"),
        (b'[null,true,2,"text"]', [None, True, 2, "text"]),
        (b'{"a":[2,false],"\xc3\xa9":{"x":"ok"}}', {"a": [2, False], "é": {"x": "ok"}}),
    ),
)
def test_parse_canonical_json_v1_accepts_exact_scalar_and_container_bytes(
    encoded: bytes,
    expected: object,
) -> None:
    decoded = parse_canonical_json_v1(encoded)

    assert decoded == expected
    assert type(decoded) is type(expected)
    assert canonical_json_v1(decoded) == encoded


def test_canonical_json_v1_digest_is_internal_and_domain_separated() -> None:
    payload = {"a": 1}
    assert (
        canonical_json_v1_digest("laconian-test-v1", payload)
        == hashlib.sha256(b"laconian-test-v1\0" + canonical_json_v1(payload)).hexdigest()
    )
    with pytest.raises(CanonicalJSONV1Error):
        canonical_json_v1_digest("", payload)
    with pytest.raises(CanonicalJSONV1Error):
        canonical_json_v1_digest("e\u0301", payload)


def test_canonical_json_v1_package_exports_are_owner_identical() -> None:
    import laconian_eval.benchmark as benchmark
    from laconian_eval.benchmark import attachments

    assert benchmark.CanonicalJSONV1Error is attachments.CanonicalJSONV1Error
    assert benchmark.canonical_json_v1 is attachments.canonical_json_v1
    assert benchmark.parse_canonical_json_v1 is attachments.parse_canonical_json_v1
    assert benchmark.attachment_digest is attachments.attachment_digest
    assert benchmark.write_attachment_json is attachments.write_attachment_json
    assert benchmark.RationalV1 is attachments.RationalV1
    assert not hasattr(benchmark, "canonical_json_v1_digest")


def test_write_attachment_is_canonical_fsynced_and_never_overwrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "attachment.json"
    real_open = os.open
    descriptor_purposes: dict[int, str] = {}
    fsync_calls: list[str] = []

    def tracked_open(path: Path, flags: int, mode: int = 0o777) -> int:
        purpose = {target: "file", target.parent: "parent"}[path]
        descriptor = real_open(path, flags, mode)
        descriptor_purposes[descriptor] = purpose
        return descriptor

    def tracked_fsync(descriptor: int) -> None:
        fsync_calls.append(descriptor_purposes[descriptor])

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "fsync", tracked_fsync)

    write_attachment_json(target, {"z": 1, "a": 2})

    assert target.read_bytes() == b'{"a":2,"z":1}\n'
    assert fsync_calls == ["file", "parent"]
    with pytest.raises(FileExistsError):
        write_attachment_json(target, {"a": 3})
    assert target.read_bytes() == b'{"a":2,"z":1}\n'
    assert fsync_calls == ["file", "parent"]
