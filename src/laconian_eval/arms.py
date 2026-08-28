from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Arm:
    name: str
    instruction: str | None
    sha256: str

    @property
    def instruction_bytes(self) -> bytes:
        """Return the exact UTF-8 request-instruction bytes bound by ``sha256``."""

        return b"" if self.instruction is None else self.instruction.encode("utf-8")


@dataclass(frozen=True, slots=True)
class ArmMemberSpec:
    """One fixed authored arm member and its capsule destination name."""

    member: str
    source_path: str | None
    inline_bytes: bytes | None


_CONCISE_INSTRUCTION = "Answer concisely."
_CONCISE_BYTES = _CONCISE_INSTRUCTION.encode("utf-8")
_FILE_ARMS = {
    "caveman": Path("evals/baselines/caveman/SKILL.md"),
    "if": Path("skills/if/SKILL.md"),
}
_CAVEMAN_COMMIT = "781c384cafc28d7ca392014dbab569f985b5b2fd"
_CAVEMAN_SKILL_SHA256 = "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"
_CAVEMAN_SOURCE_SHA256 = "8aa76311ea6273848242b1fcdd3542c47683fdeb7118395afb5aafb4709d081d"
_CAVEMAN_LICENSE_SHA256 = "f0abc56b6f49ab2e285bb6e6723f028abb7ebd4fe0e242bbdc2b4dded0ace8b9"
_ARM_MEMBER_SPECS: dict[str, tuple[ArmMemberSpec, ...]] = {
    "baseline": (ArmMemberSpec("baseline.txt", None, b""),),
    "concise": (ArmMemberSpec("concise.txt", None, _CONCISE_BYTES),),
    "caveman": (
        ArmMemberSpec("SKILL.md", "evals/baselines/caveman/SKILL.md", None),
        ArmMemberSpec("SOURCE.md", "evals/baselines/caveman/SOURCE.md", None),
        ArmMemberSpec("LICENSE.txt", "LICENSES/CAVEMAN-MIT.txt", None),
    ),
    "if": (ArmMemberSpec("SKILL.md", "skills/if/SKILL.md", None),),
}


def arm_member_specs(name: str) -> tuple[ArmMemberSpec, ...]:
    """Return the fixed capture inventory for a selected arm."""

    try:
        return _ARM_MEMBER_SPECS[name]
    except KeyError:
        raise ValueError(f"unknown arm: {name!r}") from None


def arm_from_captured_bytes(name: str, content: bytes) -> Arm:
    """Build one request arm from its already captured exact instruction bytes."""

    if type(content) is not bytes:
        raise TypeError("arm instruction content must be bytes")
    if name == "baseline":
        if content != b"":
            raise ValueError("baseline instruction bytes must be empty")
        instruction = None
    elif name == "concise":
        if content != _CONCISE_BYTES:
            raise ValueError("concise instruction bytes must match the fixed baseline")
        instruction = _CONCISE_INSTRUCTION
    elif name in _FILE_ARMS:
        try:
            instruction = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise ValueError("arm instruction is not valid UTF-8") from None
    else:
        raise ValueError(f"unknown arm: {name!r}")
    return Arm(name=name, instruction=instruction, sha256=sha256(content).hexdigest())


def validate_caveman_snapshot(*, skill: bytes, source: bytes, license_text: bytes) -> None:
    """Fail closed unless all captured Caveman provenance matches the reviewed pin."""

    if not all(type(value) is bytes for value in (skill, source, license_text)):
        raise TypeError("Caveman snapshot members must be bytes")
    if sha256(skill).hexdigest() != _CAVEMAN_SKILL_SHA256:
        raise ValueError("Caveman snapshot pin mismatch")
    if sha256(source).hexdigest() != _CAVEMAN_SOURCE_SHA256:
        raise ValueError("Caveman snapshot pin mismatch")
    if sha256(license_text).hexdigest() != _CAVEMAN_LICENSE_SHA256:
        raise ValueError("Caveman snapshot pin mismatch")
    try:
        source_lines = tuple(line.strip() for line in source.decode("utf-8").splitlines())
        license_text.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Caveman snapshot pin mismatch") from None
    expected_lines = {
        "commit": f"- Commit: `{_CAVEMAN_COMMIT}`",
        "sha256": f"- SHA-256: `{_CAVEMAN_SKILL_SHA256}`",
        "license": "- License: MIT",
    }
    prefixes = {
        "commit": "- Commit:",
        "sha256": "- SHA-256:",
        "license": "- License:",
    }
    for label, prefix in prefixes.items():
        matching = tuple(line for line in source_lines if line.startswith(prefix))
        if matching != (expected_lines[label],):
            raise ValueError("Caveman snapshot pin mismatch")


def _read_instruction(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{path}: unable to read arm instruction: {exc}") from exc


def load_arms(root: Path, names: Sequence[str]) -> tuple[Arm, ...]:
    arms: list[Arm] = []
    for name in names:
        if name == "baseline":
            content = b""
        elif name == "concise":
            content = _CONCISE_BYTES
        elif name in _FILE_ARMS:
            instruction = _read_instruction(root / _FILE_ARMS[name])
            content = instruction.encode("utf-8")
        else:
            raise ValueError(f"unknown arm: {name!r}")

        arms.append(arm_from_captured_bytes(name, content))
    return tuple(arms)
