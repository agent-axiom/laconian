from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Arm:
    name: str
    instruction: str | None
    sha256: str


_CONCISE_INSTRUCTION = "Answer concisely."
_FILE_ARMS = {
    "caveman": Path("evals/baselines/caveman/SKILL.md"),
    "if": Path("skills/if/SKILL.md"),
}


def _read_instruction(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{path}: unable to read arm instruction: {exc}") from exc


def load_arms(root: Path, names: Sequence[str]) -> tuple[Arm, ...]:
    arms: list[Arm] = []
    for name in names:
        if name == "baseline":
            instruction = None
            content = b""
        elif name == "concise":
            instruction = _CONCISE_INSTRUCTION
            content = instruction.encode("utf-8")
        elif name in _FILE_ARMS:
            instruction = _read_instruction(root / _FILE_ARMS[name])
            content = instruction.encode("utf-8")
        else:
            raise ValueError(f"unknown arm: {name!r}")

        arms.append(Arm(name=name, instruction=instruction, sha256=sha256(content).hexdigest()))
    return tuple(arms)
