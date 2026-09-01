from __future__ import annotations

from typing import cast

import pytest

from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.tree_policy import capsule_path_kind


class _PathSubclass(str):
    pass


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        (".laconian.lock", "file"),
        ("capsule.json", "file"),
        ("inputs/planning", "directory"),
        ("inputs/planning/parent-plan.jsonl", "file"),
        ("inputs/planning/shard-plan.json", "file"),
        ("seal.json", "file"),
        (".seal.123e4567-e89b-42d3-a456-426614174000.tmp", "file"),
        ("inputs/cases/000.yaml", "file"),
        ("inputs/protocols/000-0123456789abcdef.bin", "file"),
        ("inputs/software/runner/laconian_eval/providers/openai.py", "file"),
    ],
)
def test_capsule_path_kind_accepts_exact_owned_grammar(path: str, kind: str) -> None:
    assert capsule_path_kind(path) == kind


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("case-index.jsonl", "file"),
        ("environment.json", "file"),
        ("events.jsonl", "file"),
        ("inputs/index.json", "file"),
        ("inputs/software/runner-source.json", "file"),
        ("manifest.json", "file"),
        ("plan.jsonl", "file"),
        ("raw.jsonl", "file"),
        ("inputs/arms/baseline.txt", "file"),
        ("inputs/arms/concise.txt", "file"),
        ("inputs/arms/caveman/SKILL.md", "file"),
        ("inputs/arms/caveman/SOURCE.md", "file"),
        ("inputs/arms/caveman/LICENSE.txt", "file"),
        ("inputs/arms/if/SKILL.md", "file"),
        ("inputs/provider/replay.yaml", "file"),
        ("inputs/cases/1000.yaml", "file"),
        ("inputs/protocols/1000-fedcba9876543210.bin", "file"),
        ("inputs/software/runner/laconian_eval/py.typed", "file"),
        ("inputs", "directory"),
        ("inputs/arms", "directory"),
        ("inputs/arms/caveman", "directory"),
        ("inputs/arms/if", "directory"),
        ("inputs/cases", "directory"),
        ("inputs/provider", "directory"),
        ("inputs/protocols", "directory"),
        ("inputs/software", "directory"),
        ("inputs/software/runner", "directory"),
        ("inputs/software/runner/laconian_eval", "directory"),
        ("inputs/software/runner/laconian_eval/providers", "directory"),
    ],
)
def test_capsule_path_kind_preserves_existing_tree_grammar(path: str, kind: str) -> None:
    assert capsule_path_kind(path) == kind


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "/",
        "/capsule.json",
        r"inputs\cases\000.yaml",
        "capsule.json\x00",
        "inputs/software/runner/laconian_eval/cafe\u0301",
        "inputs//cases",
        "inputs/./cases",
        "inputs/../cases",
        "inputs/cases/00.yaml",
        "inputs/cases/0000.yaml",
        "inputs/protocols/00-0123456789abcdef.bin",
        ".seal.123e4567-e89b-12d3-a456-426614174000.tmp",
        ".seal.123E4567-E89B-42D3-A456-426614174000.tmp",
        ".seal.123e4567-e89b-42d3-7456-426614174000.tmp",
        ".seal.123e4567e89b42d3a456426614174000.tmp",
        "unknown",
        "capsule.json/child",
        "seal.json/child",
        "inputs/software/runner/laconian_eval/__pycache__",
        "inputs/software/runner/laconian_eval/__pycache__/shadow.py",
    ],
)
def test_capsule_path_kind_rejects_nonmembers(path: str) -> None:
    assert capsule_path_kind(path) is None


def test_capsule_path_kind_preserves_nested_py_typed_directory_children() -> None:
    root = "inputs/software/runner/laconian_eval"

    assert capsule_path_kind(f"{root}/pkg/py.typed") == "directory"
    assert capsule_path_kind(f"{root}/pkg/py.typed/child.py") == "file"
    assert capsule_path_kind(f"{root}/py.typed/child.py") is None
    assert capsule_path_kind(f"{root}/openai.py/child.py") is None


@pytest.mark.parametrize("variant", ["8", "9", "a", "b"])
def test_capsule_path_kind_accepts_every_canonical_uuid4_variant(variant: str) -> None:
    path = f".seal.123e4567-e89b-42d3-{variant}456-426614174000.tmp"

    assert capsule_path_kind(path) == "file"


@pytest.mark.parametrize("path", [None, 1, b"capsule.json", _PathSubclass("capsule.json")])
def test_capsule_path_kind_rejects_non_exact_strings(path: object) -> None:
    assert capsule_path_kind(cast(str, path)) is None


def test_capsule_path_kind_rejects_hostile_utf8_and_boundaries() -> None:
    over_bound = "inputs/software/runner/laconian_eval/" + (
        "a" * (RESOURCE_LIMITS_V1.bounded_string_bytes + 1)
    )

    assert capsule_path_kind("inputs/software/runner/laconian_eval/hostile\ud800.py") is None
    assert capsule_path_kind(over_bound) is None
    assert capsule_path_kind("inputs/cases/0123.yaml") is None
