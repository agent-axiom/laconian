from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "skills/if"
SKILL = SKILL_DIR / "SKILL.md"
EXPECTED_DESCRIPTION = (
    "Use when the user explicitly invokes the `if` skill or asks for a concise, "
    "laconic, no-fluff, or to-the-point answer. Do not trigger on the ordinary word or "
    "programming keyword `if`. Detailed, step-by-step, exhaustive, educational, or "
    "fixed-length requests activate only when they also include an explicit invocation "
    "or brevity request."
)


def _frontmatter(text: str) -> dict[str, str]:
    opening = "---\n"
    closing = "\n---\n"
    assert text.startswith(opening)
    closing_index = text.find(closing, len(opening))
    assert closing_index != -1
    raw = text[len(opening) : closing_index]
    value = yaml.safe_load(raw)
    assert isinstance(value, dict)
    return value


def test_if_skill_is_the_only_portable_artifact() -> None:
    files = sorted(path.relative_to(SKILL_DIR).as_posix() for path in SKILL_DIR.rglob("*"))
    assert files == ["SKILL.md"]


def test_if_skill_has_discriminating_metadata() -> None:
    metadata = _frontmatter(SKILL.read_text(encoding="utf-8"))
    assert metadata == {"name": "if", "description": EXPECTED_DESCRIPTION}


def test_if_skill_states_the_complete_answer_boundary() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "shortest complete answer" in text.lower()
    correctness_index = text.find("1. Correctness and safety.")
    brevity_index = text.find("6. Brevity.")
    assert 0 <= correctness_index < brevity_index
    assert "Brevity never overrides a higher priority." in text
    assert "normal grammar" in text
    assert (
        "Do not alter code, commands, errors, numbers, versions, URLs, identifiers, "
        "quotations, schemas, machine-readable formats, or other exact values when their "
        "exact form is required." in text
    )
    assert (
        "Preserve every required key, item, order, and format. Direct requests to "
        "transform exact content take precedence." in text
    )
    assert (
        "- Choose a shorter operation that can discard, overwrite, or broaden changes "
        "when a safer targeted or reversible option is available." in text
    )
    assert (
        "Stop editing when the next deletion would reduce correctness, safety, "
        "requirement coverage, clarity, completeness, usefulness, tone, or force." in text
    )
