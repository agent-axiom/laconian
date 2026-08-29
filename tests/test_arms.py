from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path

import pytest

from laconian_eval.arms import Arm, load_arms

ROOT = Path(__file__).parents[1]


def test_load_arms_returns_exact_order_and_instructions(tmp_path) -> None:
    arms = load_arms(ROOT, ("baseline", "concise", "caveman", "if"))
    assert [arm.name for arm in arms] == ["baseline", "concise", "caveman", "if"]
    assert arms[0].instruction is None
    assert arms[1].instruction == "Answer concisely."
    assert arms[2].instruction == (ROOT / "evals/baselines/caveman/SKILL.md").read_text()
    assert arms[3].instruction == (ROOT / "skills/if/SKILL.md").read_text()


def test_load_arms_hashes_exact_utf8_bytes_and_preserves_requested_order() -> None:
    arms = load_arms(ROOT, ("if", "baseline", "caveman", "concise"))

    assert [arm.name for arm in arms] == ["if", "baseline", "caveman", "concise"]
    assert [arm.sha256 for arm in arms] == [
        sha256((ROOT / "skills/if/SKILL.md").read_bytes()).hexdigest(),
        sha256(b"").hexdigest(),
        sha256((ROOT / "evals/baselines/caveman/SKILL.md").read_bytes()).hexdigest(),
        sha256(b"Answer concisely.").hexdigest(),
    ]
    assert [arm.instruction_bytes for arm in arms] == [
        (ROOT / "skills/if/SKILL.md").read_bytes(),
        b"",
        (ROOT / "evals/baselines/caveman/SKILL.md").read_bytes(),
        b"Answer concisely.",
    ]


def test_file_arm_hash_preserves_exact_utf8_line_endings(tmp_path: Path) -> None:
    skill_path = tmp_path / "skills/if/SKILL.md"
    skill_path.parent.mkdir(parents=True)
    content = b"line one\r\nline two\r\n"
    skill_path.write_bytes(content)

    (arm,) = load_arms(tmp_path, ("if",))

    assert arm.instruction == content.decode("utf-8")
    assert arm.sha256 == sha256(content).hexdigest()


def test_arm_is_frozen_and_slotted() -> None:
    arm = Arm(name="baseline", instruction=None, sha256=sha256(b"").hexdigest())

    assert not hasattr(arm, "__dict__")
    with pytest.raises(FrozenInstanceError):
        arm.name = "if"  # type: ignore[misc]


def test_load_arms_rejects_unknown_arm() -> None:
    with pytest.raises(ValueError, match="unknown arm"):
        load_arms(ROOT, ("baseline", "unknown"))


def test_load_arms_reports_missing_instruction_path(tmp_path: Path) -> None:
    expected_path = tmp_path / "skills/if/SKILL.md"

    with pytest.raises(ValueError) as error:
        load_arms(tmp_path, ("if",))

    assert str(expected_path) in str(error.value)


def test_load_arms_reports_invalid_utf8_instruction_path(tmp_path: Path) -> None:
    skill_path = tmp_path / "evals/baselines/caveman/SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_bytes(b"valid prefix\xffinvalid suffix")

    with pytest.raises(ValueError) as error:
        load_arms(tmp_path, ("caveman",))

    assert str(skill_path) in str(error.value)
