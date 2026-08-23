from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "skills/if"
SKILL = SKILL_DIR / "SKILL.md"


def _frontmatter(text: str) -> dict[str, str]:
    _, raw, _ = text.split("---", 2)
    value = yaml.safe_load(raw)
    assert isinstance(value, dict)
    return value


def test_if_skill_is_the_only_portable_artifact() -> None:
    files = sorted(path.relative_to(SKILL_DIR).as_posix() for path in SKILL_DIR.rglob("*"))
    assert files == ["SKILL.md"]


def test_if_skill_has_discriminating_metadata() -> None:
    metadata = _frontmatter(SKILL.read_text(encoding="utf-8"))
    assert metadata["name"] == "if"
    description = metadata["description"].lower()
    assert "concise" in description
    assert "programming" in description
    assert "detailed" in description


def test_if_skill_states_the_complete_answer_boundary() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "shortest complete answer" in text.lower()
    assert "Correctness and safety" in text
    assert "normal grammar" in text
    assert "Direct requests to transform exact content take precedence" in text
