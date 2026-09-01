from __future__ import annotations

import hashlib

import pytest

from laconian_eval.benchmark import derive_seed128


def test_seed128_matches_first_128_sha256_bits() -> None:
    material = (
        b"laconian-bootstrap-v1"
        + b"\0"
        + b"campaign-seed-2026"
        + b"\0"
        + b"a" * 40
        + b"\0"
        + b"b" * 64
    )
    expected = int.from_bytes(hashlib.sha256(material).digest()[:16], "big")
    assert (
        derive_seed128(
            "laconian-bootstrap-v1",
            "campaign-seed-2026",
            "a" * 40,
            "b" * 64,
        )
        == expected
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ("", "seed", "a" * 40, "b" * 64),
        ("domain", "", "a" * 40, "b" * 64),
        ("domain", "seed", "A" * 40, "b" * 64),
        ("domain", "seed", "a" * 40, "B" * 64),
        ("bad\0domain", "seed", "a" * 40, "b" * 64),
    ],
)
def test_seed128_rejects_noncanonical_material(arguments: tuple[str, str, str, str]) -> None:
    with pytest.raises(ValueError):
        derive_seed128(*arguments)
