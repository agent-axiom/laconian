"""Deterministic seed derivation for public benchmark sampling."""

from __future__ import annotations

import hashlib
import re

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def derive_seed128(
    domain: str,
    campaign_seed: str,
    input_tag_commit: str,
    judge_protocol_sha256: str,
) -> int:
    """Derive the first 128 SHA-256 bits from canonical NUL-separated material."""

    values = (domain, campaign_seed, input_tag_commit, judge_protocol_sha256)
    if any(type(value) is not str or not value for value in values):
        raise ValueError("seed material must be nonempty strings")
    if any("\0" in value for value in values):
        raise ValueError("seed material must not contain NUL")
    if _COMMIT.fullmatch(input_tag_commit) is None:
        raise ValueError("input tag commit must be lowercase SHA-1")
    if _SHA256.fullmatch(judge_protocol_sha256) is None:
        raise ValueError("judge protocol hash must be lowercase SHA-256")
    encoded = b"\0".join(value.encode("utf-8", errors="strict") for value in values)
    return int.from_bytes(hashlib.sha256(encoded).digest()[:16], "big", signed=False)
