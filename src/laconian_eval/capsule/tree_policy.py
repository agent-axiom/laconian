"""Pure classification for every path that may belong to a generation capsule."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, TypeAlias

from laconian_eval.capsule.schema import validate_relative_posix_path

MemberKind: TypeAlias = Literal["file", "directory"]

_FIXED_FILES = frozenset(
    {
        ".laconian.lock",
        "capsule.json",
        "case-index.jsonl",
        "environment.json",
        "events.jsonl",
        "inputs/arms/baseline.txt",
        "inputs/arms/caveman/LICENSE.txt",
        "inputs/arms/caveman/SKILL.md",
        "inputs/arms/caveman/SOURCE.md",
        "inputs/arms/concise.txt",
        "inputs/arms/if/SKILL.md",
        "inputs/index.json",
        "inputs/planning/parent-plan.jsonl",
        "inputs/planning/shard-plan.json",
        "inputs/provider/replay.yaml",
        "inputs/software/runner-source.json",
        "manifest.json",
        "plan.jsonl",
        "raw.jsonl",
        "seal.json",
    }
)
_FIXED_DIRECTORIES = frozenset(
    {
        "inputs",
        "inputs/arms",
        "inputs/arms/caveman",
        "inputs/arms/if",
        "inputs/cases",
        "inputs/planning",
        "inputs/protocols",
        "inputs/provider",
        "inputs/software",
        "inputs/software/runner",
        "inputs/software/runner/laconian_eval",
    }
)
_ORDINAL = r"(?:[0-9]{3}|[1-9][0-9]{3,})"
_CASE_PATH = re.compile(rf"inputs/cases/{_ORDINAL}\.yaml\Z")
_PROTOCOL_PATH = re.compile(rf"inputs/protocols/{_ORDINAL}-[0-9a-f]{{16}}\.bin\Z")
_RUNNER_SOURCE_PATH = re.compile(r"inputs/software/runner/laconian_eval/(?P<member>.+)\Z")
_SEAL_TEMP_PATH = re.compile(
    r"\.seal\.[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\.tmp\Z"
)


def capsule_path_kind(path: str) -> MemberKind | None:
    """Classify one normalized possible capsule member without reading the filesystem."""

    if type(path) is not str:
        return None
    try:
        validate_relative_posix_path(path)
    except ValueError:
        return None
    if unicodedata.normalize("NFC", path) != path:
        return None
    if path in _FIXED_FILES or _SEAL_TEMP_PATH.fullmatch(path) is not None:
        return "file"
    if path in _FIXED_DIRECTORIES:
        return "directory"
    if _CASE_PATH.fullmatch(path) is not None or _PROTOCOL_PATH.fullmatch(path) is not None:
        return "file"

    runner_match = _RUNNER_SOURCE_PATH.fullmatch(path)
    if runner_match is None:
        return None
    components = runner_match.group("member").split("/")
    if "__pycache__" in components:
        return None
    if any(component.endswith(".py") for component in components[:-1]) or (
        len(components) > 1 and components[0] == "py.typed"
    ):
        return None
    leaf = components[-1]
    if leaf.endswith(".py") or (len(components) == 1 and leaf == "py.typed"):
        return "file"
    return "directory"
