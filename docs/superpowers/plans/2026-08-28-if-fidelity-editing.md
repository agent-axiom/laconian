# `if` Fidelity Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the portable `if` deletion rule explicit and document its pinned methodological influence without adding workflow or benchmark scope.

**Architecture:** Extend the existing one-file skill by one sentence and lock the public contract with focused tests. Keep attribution in project philosophy so the portable artifact remains dependency-free and self-contained.

**Tech Stack:** Markdown, pytest, PyYAML, Agent Skills structural validator.

---

### Task 1: Lock the fidelity-editing contract

**Files:**
- Modify: `tests/test_skill_contract.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write the failing skill-contract test**

Add to `test_if_skill_states_the_complete_answer_boundary`:

```python
assert "Keep information. Remove only proven redundancy. Preserve uncertain content." in text
assert len(text.split()) <= 340
```

- [ ] **Step 2: Write the failing attribution test**

```python
def test_philosophy_credits_fidelity_method_without_a_lossless_claim() -> None:
    text = _read("docs/philosophy.md")
    assert "lossless-doc-compress" in text
    assert "8dd0d88852fe7445e9d2627c59124f0f161040c1" in text
    assert "does not claim that model editing is lossless" in " ".join(text.split())
```

- [ ] **Step 3: Run RED**

Run:

```bash
uv run pytest tests/test_skill_contract.py tests/test_public_contract.py -q
```

Expected: exactly the new skill sentence and philosophy-attribution assertions fail.

### Task 2: Add the minimal rule and attribution

**Files:**
- Modify: `skills/if/SKILL.md`
- Modify: `docs/philosophy.md`

- [ ] **Step 1: Add the skill rule**

Insert as the first bullet under `## Edit`:

```markdown
- Keep information. Remove only proven redundancy. Preserve uncertain content.
```

- [ ] **Step 2: Add the pinned methodological note**

Append before the license sentence in `docs/philosophy.md`:

```markdown
## Related fidelity method

The decision rule was informed by the `KEEP` / `REMOVE` / `FLAG` model in
[`lossless-doc-compress`](https://github.com/ML-SystemDesign/MLSystemDesign/tree/8dd0d88852fe7445e9d2627c59124f0f161040c1/skills/lossless-doc-compress),
by Valerii Babushkin and Arseny Kravchenko. Laconian adapts that model to answer editing: uncertain
content remains in the answer, no editorial log is emitted, and the project does not claim that
model editing is lossless.
```

- [ ] **Step 3: Run GREEN and structural validation**

```bash
uv run pytest tests/test_skill_contract.py tests/test_public_contract.py -q
python3 /Users/if/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/if
```

Expected: all focused tests pass and the validator reports `Skill is valid!`.

- [ ] **Step 4: Run repository gates**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 5: Commit exact files**

```bash
git add skills/if/SKILL.md docs/philosophy.md tests/test_skill_contract.py tests/test_public_contract.py docs/superpowers/specs/2026-08-28-if-fidelity-editing-design.md docs/superpowers/plans/2026-08-28-if-fidelity-editing.md
git commit -m "feat: make fidelity editing explicit"
```
