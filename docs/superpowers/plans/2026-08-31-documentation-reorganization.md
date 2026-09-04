# Documentation Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the root README into a concise entry point, move synchronized localizations under `docs/i18n/`, and route detailed material into focused active documentation.

**Architecture:** Keep conventional repository files in the root, add `docs/README.md` as the documentation hub, use `docs/using-the-skill.md` and `benchmarks/README.md` as focused guides, and keep formal benchmark rules in `benchmarks/methodology.md`. Public-contract tests define the concise structure and resolve links relative to each Markdown source while excluding historical `docs/superpowers/` records.

**Tech Stack:** Markdown, Python 3.11, pytest, `pathlib`, `uv`

---

## File map

- `README.md`: concise English project entry point and navigation, kept between 40 and 70 lines.
- `docs/README.md`: active documentation index.
- `docs/using-the-skill.md`: behavior, boundaries, installation, and removal of the skill.
- `docs/philosophy.md`: editing philosophy plus the name's historical framing and sources.
- `benchmarks/README.md`: operational benchmark overview and exact quickstart.
- `benchmarks/methodology.md`: unchanged formal publication and reproducibility contract.
- `docs/i18n/README.{ru,zh-CN,el,it,grc-x-laconian}.md`: concise localized entry points.
- `tests/test_public_contract.py`: paths, content safeguards, and active-link contract.

### Task 1: Concise English entry point and focused documentation

**Files:**
- Modify: `tests/test_public_contract.py`
- Modify: `README.md`
- Create: `docs/README.md`
- Create: `docs/using-the-skill.md`
- Modify: `docs/philosophy.md`

- [ ] **Step 1: Replace the long-README tests with the concise entry-point contract**

Add `import os`, replace `README_FILES`, remove `MODERN_READMES`, and add the relative-link helper:

```python
import os
import re
from pathlib import Path

README_FILES = {
    "English": "README.md",
    "Русский": "docs/i18n/README.ru.md",
    "简体中文": "docs/i18n/README.zh-CN.md",
    "Ελληνικά": "docs/i18n/README.el.md",
    "Italiano": "docs/i18n/README.it.md",
    "Laconian Doric (reconstructed)": "docs/i18n/README.grc-x-laconian.md",
}


def _relative_link(source: str, target: str) -> str:
    source_dir = (ROOT / source).parent
    return Path(os.path.relpath(ROOT / target, start=source_dir)).as_posix()
```

Replace `test_each_readme_links_to_the_other_five` with:

```python
@pytest.mark.parametrize("filename", README_FILES.values())
def test_each_readme_links_to_the_other_five(filename: str) -> None:
    text = _read(filename)
    for language, target in README_FILES.items():
        if target != filename:
            href = _relative_link(filename, target)
            assert f"[{language}]({href})" in text
```

Replace the long English section-order test with:

```python
def test_english_readme_is_a_concise_entry_point() -> None:
    text = _read("README.md")
    assert "Laconian asks for the shortest complete answer—not the shortest answer." in text
    assert "No public benchmark result is available yet." in text
    assert "they do not show that `if` wins" in " ".join(text.split())
    assert 40 <= len(text.splitlines()) <= 70

    markers = (
        "# Laconian",
        "## Status",
        "## Start here",
        "## Documentation",
        "## Contributing and security",
        "## License",
    )
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)

    for removed_detail in (
        "## Why “if”?",
        "## What the skill does",
        "## Four-arm benchmark",
        "export OPENAI_API_KEY",
        "uv run laconian score",
    ):
        assert removed_detail not in text

    for target in (
        "skills/if/SKILL.md",
        "docs/using-the-skill.md",
        "benchmarks/README.md",
        "docs/README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "NOTICE",
    ):
        assert f"]({target})" in text
```

Change the anecdote test to read `docs/philosophy.md` and retain every existing required phrase,
unsupported-claim rejection, and `SOURCE_URLS` assertion:

```python
def test_philosophy_frames_the_anecdote_carefully() -> None:
    text = _read("docs/philosophy.md")
    required = (
        "Plutarch",
        "On Talkativeness",
        "Moralia 511A",
        "centuries later",
        "Philip II",
        "αἴκα",
        "The letter itself does not survive.",
    )
    for phrase in required:
        assert phrase in text
    for url in SOURCE_URLS:
        assert url in text

    lower = text.casefold()
    for unsupported in (
        "philip never entered",
        "never entered laconia",
        "kill every man",
        "enslave the women",
        "destroy sparta",
        "burn sparta to the ground",
    ):
        assert unsupported not in lower
```

Replace the full license-map README test and extend the core-document test:

```python
def test_english_readme_links_to_the_authoritative_license_map() -> None:
    text = _read("README.md")
    assert "[NOTICE](NOTICE)" in text


def test_core_public_document_files_exist() -> None:
    required = (
        "docs/README.md",
        "docs/using-the-skill.md",
        "evals/README.md",
        "benchmarks/README.md",
        "benchmarks/methodology.md",
        "benchmarks/results/.gitkeep",
        "docs/design.md",
        "docs/philosophy.md",
        "docs/contributing-cases.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
    )
    missing = [path for path in required if not (ROOT / path).is_file()]
    assert missing == []
```

Add focused contracts for the two new active documents:

```python
def test_documentation_index_routes_without_repeating_detail() -> None:
    text = _read("docs/README.md")
    for target in (
        "using-the-skill.md",
        "philosophy.md",
        "design.md",
        "../benchmarks/README.md",
        "../benchmarks/methodology.md",
        "../evals/README.md",
        "contributing-cases.md",
        "i18n/README.ru.md",
        "superpowers/specs/",
        "superpowers/plans/",
    ):
        assert target in text
    assert "uv run laconian run" not in text


def test_using_the_skill_owns_installation_and_boundaries() -> None:
    text = _read("docs/using-the-skill.md")
    for phrase in (
        "../skills/if/SKILL.md",
        "shortest complete answer",
        "does not turn prose into primitive speech",
        'mkdir -p "<agent-skills-directory>/if"',
        'cp skills/if/SKILL.md "<agent-skills-directory>/if/SKILL.md"',
        'rm "<agent-skills-directory>/if/SKILL.md"',
        "no scripts, dependencies, permissions, references, assets, network calls",
    ):
        assert phrase in text
```

- [ ] **Step 2: Run the focused tests and verify the new contract is red**

Run:

```bash
uv run pytest -q tests/test_public_contract.py -k "concise_entry_point or philosophy_frames or documentation_index or using_the_skill or core_public_document_files"
```

Expected: FAIL because `README.md` is still long, `docs/README.md` and
`docs/using-the-skill.md` do not exist, `benchmarks/README.md` does not exist, and the historical
material is still in the root README.

- [ ] **Step 3: Replace `README.md` with the concise English entry point**

Use this complete content:

```markdown
[Website](https://agent-axiom.github.io/laconian/) · [English](README.md) · [Русский](docs/i18n/README.ru.md) · [简体中文](docs/i18n/README.zh-CN.md) · [Ελληνικά](docs/i18n/README.el.md) · [Italiano](docs/i18n/README.it.md) · [Laconian Doric (reconstructed)](docs/i18n/README.grc-x-laconian.md)

![Laconian — The shortest complete answer.](assets/laconian-banner.png)

# Laconian

Laconian asks for the shortest complete answer—not the shortest answer.

Laconian is a public philosophy project built around one portable Markdown skill and an open
benchmark for testing whether brevity preserves a complete answer.

The entire installable artifact is [`skills/if/SKILL.md`](skills/if/SKILL.md).

## Status

Laconian is pre-release and under active development. It includes a credential-free evaluation
path and an optional live-provider adapter.

No public benchmark result is available yet. Smoke and replay fixtures verify the evaluation
pipeline; they do not show that `if` wins, saves cost, or outperforms another comparison arm.

## Start here

- [Read the skill](skills/if/SKILL.md)
- [Install and use it](docs/using-the-skill.md)
- [Run the benchmark](benchmarks/README.md)

## Documentation

- [Documentation index](docs/README.md)
- [Philosophy](docs/philosophy.md)
- [Design](docs/design.md)
- [Evaluation data](evals/README.md)
- [Benchmark methodology](benchmarks/methodology.md)

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute. Report suspected vulnerabilities through
the private process in [SECURITY.md](SECURITY.md).

## License

The repository uses a mixed license map. See [NOTICE](NOTICE) for the authoritative path-to-license
mapping.
```

- [ ] **Step 4: Create `docs/README.md` as the active documentation index**

Use this complete content:

```markdown
# Documentation

This index points to the active Laconian documentation. Development plans and specifications are
kept separately as historical records.

## Use the skill

- [Using the `if` skill](using-the-skill.md)
- [Portable skill file](../skills/if/SKILL.md)

## Concepts and design

- [The shortest complete answer](philosophy.md)
- [Evaluation architecture](design.md)

## Benchmark

- [Run the benchmark](../benchmarks/README.md)
- [Publication methodology](../benchmarks/methodology.md)
- [Evaluation data](../evals/README.md)
- [Contributing benchmark cases](contributing-cases.md)

## Project

- [Contributing](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Changelog](../CHANGELOG.md)
- [License map](../NOTICE)

## Languages

- [Русский](i18n/README.ru.md)
- [简体中文](i18n/README.zh-CN.md)
- [Ελληνικά](i18n/README.el.md)
- [Italiano](i18n/README.it.md)
- [Laconian Doric (experimental reconstruction)](i18n/README.grc-x-laconian.md)

## Development history

- [Approved specifications](superpowers/specs/)
- [Implementation plans](superpowers/plans/)

Documentation is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
```

- [ ] **Step 5: Create `docs/using-the-skill.md`**

Use this complete content:

````markdown
# Using the `if` skill

[`skills/if/SKILL.md`](../skills/if/SKILL.md) asks an agent to find the shortest complete answer,
not merely the shortest answer.

## What it does

The skill asks the agent to determine the complete answer first, then remove only what can be
removed without weakening correctness, safety, requirements, material facts, uncertainty,
practical sufficiency, clarity, tone, or natural language.

It removes greetings, restatement, unrequested process narration, repetition, and decoration
before it removes substance. It preserves requested detail and exact code, commands, errors,
numbers, versions, URLs, identifiers, quotations, and machine-readable structures when their
exact form matters.

## What it does not do

`if` does not turn prose into primitive speech, replace evidence with confidence, hide material
caveats, shorten tool calls, minify code, compress input context, or execute an action. It does
not override a request for a detailed tutorial, fixed structure, evidence, examples, or a
required length.

## Install

Copy the one skill file into the `if` directory of an agent host that supports Markdown skills:

```bash
mkdir -p "<agent-skills-directory>/if"
cp skills/if/SKILL.md "<agent-skills-directory>/if/SKILL.md"
```

The placeholder is host-specific. The project does not yet claim installation coverage across
named agent hosts.

## Uninstall

Remove the copied file and its empty directory:

```bash
rm "<agent-skills-directory>/if/SKILL.md"
rmdir "<agent-skills-directory>/if"
```

## Portability boundary

The skill is one Markdown-only file. It has no scripts, dependencies, permissions, references,
assets, network calls, or platform-specific tool instructions. Benchmark code, cases, examples,
and historical notes remain outside the installable artifact.

See the [project philosophy](philosophy.md) for the editing principles behind the skill.

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
````

- [ ] **Step 6: Move the historical framing into `docs/philosophy.md`**

Insert these sections immediately before `## Related fidelity method`:

```markdown
## Why “if”?

Plutarch, writing centuries later, preserves an anecdote about Philip II in *On Talkativeness*
17 (*Moralia* 511A). Philip writes a threat concerning entry into Laconia; the Laconians answer
in writing with one Doric word: `αἴκα`—“if.” The letter itself does not survive. What survives is
Plutarch's later literary account, not a contemporary document.

The story is an image for the project, not proof of its benchmark hypothesis. It is also not a
story about an unfulfilled entry: Polybius 9.33 has a speaker acknowledge that Philip entered
Laconia with an army.

## Historical and linguistic sources

- [Plutarch, *On Talkativeness* 17 (*Moralia* 511A)](https://www.perseus.tufts.edu/hopper/text?doc=Perseus%3Atext%3A2008.01.0287%3Asection%3D17), for the later literary account and `αἴκα`.
- [Eva A. Mitchell, *Laconian Dialect*, University of Edinburgh](https://era.ed.ac.uk/items/385e1ac5-539c-47f6-94b7-8ab83a94a139), for the fragmentary and heterogeneous evidence for ancient Laconian.
- [Polybius, *Histories* 9.33](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Polybius/9%2A.html), for ancient testimony that Philip entered Laconia with an army.
```

- [ ] **Step 7: Run the focused tests and verify the first slice is green except for the intentionally missing benchmark guide**

Run:

```bash
uv run pytest -q tests/test_public_contract.py -k "concise_entry_point or philosophy_frames or documentation_index or using_the_skill"
```

Expected: PASS.

Run:

```bash
uv run pytest -q tests/test_public_contract.py -k core_public_document_files
```

Expected: FAIL only because `benchmarks/README.md` is created in Task 2.

Do not commit this slice yet; Task 2 completes the active English-document contract.

### Task 2: Operational benchmark guide

**Files:**
- Modify: `tests/test_public_contract.py`
- Create: `benchmarks/README.md`

- [ ] **Step 1: Move quickstart and warning assertions to the benchmark guide**

Delete `test_every_readme_names_all_arms_without_percentage_claims` and
`test_modern_readmes_have_exact_live_run_block_and_warnings`, then replace
`test_english_quickstart_matches_the_current_cli` with:

```python
def test_benchmark_guide_names_all_arms_without_percentage_claims() -> None:
    text = _read("benchmarks/README.md")
    for arm in ARMS:
        assert f"`{arm}`" in text
    assert re.search(r"\b\d+(?:[.,]\d+)?\s*%(?![0-9A-Fa-f])", text) is None


def test_benchmark_guide_matches_the_current_cli() -> None:
    text = _read("benchmarks/README.md")
    commands = (
        "uv sync --all-extras",
        "uv run laconian validate evals/cases/response-smoke.yaml",
        "uv run laconian validate evals/cases/activation-smoke.yaml",
        "uv run laconian validate evals/manifests/replay-smoke.yaml",
        "uv run laconian run evals/manifests/replay-smoke.yaml --results-root benchmarks/results",
        (
            'uv run laconian score "$RUN_DIR/raw.jsonl" '
            '--cases evals/cases/response-smoke.yaml --output "$RUN_DIR/scored"'
        ),
        'uv run laconian report "$RUN_DIR/scored/scored.jsonl" --output "$RUN_DIR/report.md"',
    )
    for command in commands:
        assert command in text


def test_benchmark_guide_has_exact_live_run_block_and_warnings() -> None:
    text = _read("benchmarks/README.md")
    assert LIVE_RUN_BLOCK in text
    for warning in ("provider cost", "model availability", "API keys"):
        assert warning.casefold() in text.casefold()
    assert "sk-" not in text
```

- [ ] **Step 2: Run the benchmark-guide tests and verify they are red**

Run:

```bash
uv run pytest -q tests/test_public_contract.py -k "benchmark_guide or core_public_document_files"
```

Expected: FAIL because `benchmarks/README.md` does not exist.

- [ ] **Step 3: Create `benchmarks/README.md`**

Use this complete content:

````markdown
# Laconian benchmark

The benchmark tests whether the `if` skill produces shorter answers without weakening the answer
the user needs. The current smoke data verifies the evaluation pipeline; it is not a public model
result.

## Comparison arms

Every response case uses the same model, prompt, generation settings, tools, and instruction
location. Only the comparison instruction changes:

| Arm | Added instruction |
|---|---|
| `baseline` | None |
| `concise` | Exactly `Answer concisely.` |
| `caveman` | The pinned offline Caveman skill snapshot |
| `if` | The exact bytes of [`skills/if/SKILL.md`](../skills/if/SKILL.md) |

The primary comparison is `if` versus `concise`; the other arms provide context.

## Quality before brevity

Deterministic constraints are checked before brevity. Optional blind semantic judgment can then
check required facts and material warnings. A failed answer cannot win merely by being short,
and the project reports separate metrics rather than a composite score. See the full
[methodology](methodology.md).

## Offline quickstart

Run these commands from the repository root. They need no network access or provider credentials:

```bash
uv sync --all-extras
uv run laconian validate evals/cases/response-smoke.yaml
uv run laconian validate evals/cases/activation-smoke.yaml
uv run laconian validate evals/manifests/replay-smoke.yaml
uv run laconian run evals/manifests/replay-smoke.yaml --results-root benchmarks/results
```

The last command prints a unique run directory. Copy it into `RUN_DIR`, then score and render the
report:

```bash
RUN_DIR="benchmarks/results/PASTE_THE_PRINTED_DIRECTORY_NAME"
uv run laconian score "$RUN_DIR/raw.jsonl" --cases evals/cases/response-smoke.yaml --output "$RUN_DIR/scored"
uv run laconian report "$RUN_DIR/scored/scored.jsonl" --output "$RUN_DIR/report.md"
```

Replay outputs are local verification artifacts, not published benchmark evidence.

## Optional live run

```bash
export OPENAI_API_KEY="your key"
uv sync --extra openai
uv run laconian run evals/manifests/openai-example.yaml --results-root benchmarks/results
```

This command incurs provider cost. Model availability can vary by account and date. API keys
belong only in the configured environment variable; never place them in manifests or committed
results. A live run is not publication-ready until its model identifier, artifacts, method, and
limitations are reviewed.

## Further reading

- [Evaluation data and manifests](../evals/README.md)
- [Full publication methodology](methodology.md)
- [Contributing benchmark cases](../docs/contributing-cases.md)

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
````

- [ ] **Step 4: Run the active English-document tests**

Run:

```bash
uv run pytest -q tests/test_public_contract.py -k "concise_entry_point or philosophy_frames or documentation_index or using_the_skill or benchmark_guide or core_public_document_files"
```

Expected: PASS.

- [ ] **Step 5: Inspect the uncommitted English documentation slice**

```bash
git diff --check
git diff --stat
```

Expected: no whitespace errors; only the English documentation and public-contract files in
Tasks 1–2 are modified. Do not commit yet because the new language links become valid in Task 3.

### Task 3: Concise localized entry points and relative-link contract

**Files:**
- Modify: `tests/test_public_contract.py`
- Move: `README.ru.md` → `docs/i18n/README.ru.md`
- Move: `README.zh-CN.md` → `docs/i18n/README.zh-CN.md`
- Move: `README.el.md` → `docs/i18n/README.el.md`
- Move: `README.it.md` → `docs/i18n/README.it.md`
- Move: `README.grc-x-laconian.md` → `docs/i18n/README.grc-x-laconian.md`

- [ ] **Step 1: Add localized status, root-layout, and active-link tests**

Add these constants and tests:

```python
LOCALIZED_STATUS_MARKERS = {
    "docs/i18n/README.ru.md": "Публичных результатов бенчмарка пока нет",
    "docs/i18n/README.zh-CN.md": "目前还没有可用的公开基准结果",
    "docs/i18n/README.el.md": "Δεν υπάρχει ακόμη δημόσιο αποτέλεσμα benchmark",
    "docs/i18n/README.it.md": "Non sono ancora disponibili risultati pubblici del benchmark",
    "docs/i18n/README.grc-x-laconian.md": "Οὐδὲν δημόσιον ἀποτέλεσμα τοῦ `benchmark` ἔτι ἔστιν",
}

ACTIVE_MARKDOWN = (
    "README.md",
    "docs/README.md",
    "docs/using-the-skill.md",
    "docs/philosophy.md",
    "docs/design.md",
    "docs/contributing-cases.md",
    "benchmarks/README.md",
    "benchmarks/methodology.md",
    "evals/README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    *LOCALIZED_STATUS_MARKERS,
)


@pytest.mark.parametrize(("filename", "marker"), LOCALIZED_STATUS_MARKERS.items())
def test_localized_readmes_keep_the_no_result_caveat(filename: str, marker: str) -> None:
    text = _read(filename)
    assert marker in " ".join(text.split())
    assert re.search(r"\b\d+(?:[.,]\d+)?\s*%(?![0-9A-Fa-f])", text) is None
    assert len(text.splitlines()) < 90
    assert "uv run laconian" not in text
    for target in (
        "skills/if/SKILL.md",
        "docs/using-the-skill.md",
        "benchmarks/README.md",
        "docs/README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "NOTICE",
    ):
        assert f"]({_relative_link(filename, target)})" in text


def test_only_conventional_markdown_files_remain_in_the_root() -> None:
    assert {path.name for path in ROOT.glob("*.md")} == {
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
    }


@pytest.mark.parametrize("filename", ACTIVE_MARKDOWN)
def test_active_markdown_has_no_broken_local_links(filename: str) -> None:
    source = ROOT / filename
    text = _read(filename)
    targets = re.findall(r"!?\[[^]]*\]\(([^)]+)\)", text)
    for raw_target in targets:
        target = raw_target.split("#", 1)[0]
        if not target or target.startswith(("https://", "http://", "mailto:")):
            continue
        resolved = (source.parent / target).resolve()
        assert resolved.exists(), f"broken local link in {filename}: {raw_target}"
```

Update the reconstruction test to read the moved path:

```python
def test_reconstructed_readme_has_bilingual_warning_and_attested_word() -> None:
    text = _read("docs/i18n/README.grc-x-laconian.md")
    assert "Experimental reconstruction" in text
    assert "not an authentic ancient text" in text
    assert "Πειραματικὴ νεωτέρα ἀνάπλασις" in text
    assert "αἴκα" in text
```

- [ ] **Step 2: Run the localization contract and verify it is red**

Run:

```bash
uv run pytest -q tests/test_public_contract.py -k "readme_editions or links_to_the_other_five or localized_readmes or conventional_markdown or active_markdown or reconstructed_readme"
```

Expected: FAIL because the localized paths do not exist under `docs/i18n/` and five extra README
files remain in the root.

- [ ] **Step 3: Move all localized README files together**

```bash
mkdir -p docs/i18n
git mv README.ru.md docs/i18n/README.ru.md
git mv README.zh-CN.md docs/i18n/README.zh-CN.md
git mv README.el.md docs/i18n/README.el.md
git mv README.it.md docs/i18n/README.it.md
git mv README.grc-x-laconian.md docs/i18n/README.grc-x-laconian.md
```

- [ ] **Step 4: Replace the Russian and Italian files with concise entry points**

Use this complete content for `docs/i18n/README.ru.md`:

```markdown
[Website](https://agent-axiom.github.io/laconian/) · [English](../../README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

![Laconian — The shortest complete answer.](../../assets/laconian-banner.png)

# Laconian

Laconian просит дать самый короткий законченный ответ, а не просто самый короткий ответ.

Это публичный философский проект, объединяющий переносимый навык, целиком состоящий из одного
Markdown-файла, и открытый бенчмарк для проверки этой идеи при неизменных требованиях к
качеству.

## Статус

Laconian находится на предрелизной стадии. Публичных результатов бенчмарка пока нет. Фикстуры
smoke-тестов и офлайн-воспроизведения проверяют архитектуру, но не служат доказательством
производительности моделей или какого-либо преимущества `if`.

## С чего начать

- [Навык `if`](../../skills/if/SKILL.md) — весь переносимый артефакт в одном Markdown-файле.
- [Использование навыка](../using-the-skill.md) — поведение, установка, удаление и границы применения.
- [Руководство по бенчмарку](../../benchmarks/README.md) — варианты сравнения, порог качества и воспроизводимые запуски.

## Документация

Подробная документация пока доступна только на английском языке:

- [Содержание документации](../README.md)
- [Философия](../philosophy.md)
- [Дизайн](../design.md)
- [Данные для оценки](../../evals/README.md)
- [Методология бенчмарка](../../benchmarks/methodology.md)

## Участие в проекте и безопасность

Начните с [CONTRIBUTING.md](../../CONTRIBUTING.md). О предполагаемых уязвимостях сообщайте
приватно в порядке, описанном в [SECURITY.md](../../SECURITY.md), а не через публичную задачу.

## Лицензирование

Лицензирование следует карте в [NOTICE](../../NOTICE).
```

Use this complete content for `docs/i18n/README.it.md`:

```markdown
[Website](https://agent-axiom.github.io/laconian/) · [English](../../README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

![Laconian — The shortest complete answer.](../../assets/laconian-banner.png)

# Laconian

Laconian chiede la risposta completa più breve, non semplicemente la risposta più breve.

È un progetto filosofico pubblico che unisce una skill portabile costituita da un unico file
Markdown e un benchmark aperto per verificare questa idea mantenendo invariati i requisiti di
qualità.

## Stato

Laconian è ancora in fase di pre-release. Non sono ancora disponibili risultati pubblici del
benchmark. Le fixture smoke e di replay offline convalidano l'architettura, ma non costituiscono
prove delle prestazioni dei modelli né di alcun vantaggio di `if`.

## Da dove iniziare

- [La skill `if`](../../skills/if/SKILL.md) — l'intero artefatto portabile in un unico file Markdown.
- [Usare la skill](../using-the-skill.md) — comportamento, installazione, disinstallazione e limiti.
- [Guida al benchmark](../../benchmarks/README.md) — bracci di confronto, soglia di qualità ed esecuzioni riproducibili.

## Documentazione

La documentazione dettagliata è per ora disponibile solo in inglese:

- [Indice della documentazione](../README.md)
- [Filosofia](../philosophy.md)
- [Progettazione](../design.md)
- [Dati di valutazione](../../evals/README.md)
- [Metodologia del benchmark](../../benchmarks/methodology.md)

## Contributi e sicurezza

Per contribuire, iniziare da [CONTRIBUTING.md](../../CONTRIBUTING.md). Segnalare privatamente le
sospette vulnerabilità come descritto in [SECURITY.md](../../SECURITY.md), non tramite una issue
pubblica.

## Licenze

Le licenze seguono la mappa in [NOTICE](../../NOTICE).
```

- [ ] **Step 5: Replace the Simplified Chinese and Greek files with concise entry points**

Use this complete content for `docs/i18n/README.zh-CN.md`:

```markdown
[网站](https://agent-axiom.github.io/laconian/) · [English](../../README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

![Laconian — 最短的完整答案。](../../assets/laconian-banner.png)

# Laconian

Laconian 追求最短的完整答案，而不是最短的答案。

Laconian 是一个公共哲学项目，由一个可移植的单文件 Markdown 技能和一个开放基准组成。
该技能要求智能体先确定完整答案，然后只删除那些不会削弱正确性、安全性、必要事实、
清晰度或实际充分性的内容。

## 状态

本项目处于预发布阶段，仍在积极开发。目前还没有可用的公开基准结果。离线重放和测试夹具只用于
验证架构和评测流程；它们不是性能证据，也不能证明 `if` 获胜、节省了某个具体数值或优于
其他对照组。

## 从这里开始

- [完整的 `if` 技能](../../skills/if/SKILL.md) — 可移植的单文件 Markdown 技能。
- [技能使用指南](../using-the-skill.md) — 作用、边界、安装与卸载。
- [基准指南](../../benchmarks/README.md) — 对照组、质量门槛、离线重放与可选的真实运行。

## 文档

- [文档索引](../README.md)
- [理念与历史背景](../philosophy.md)
- [项目设计](../design.md)
- [评测数据](../../evals/README.md)
- [基准方法](../../benchmarks/methodology.md)

## 参与贡献

请先阅读 [CONTRIBUTING.md](../../CONTRIBUTING.md)。涉及安全的报告应遵循
[SECURITY.md](../../SECURITY.md)，不要提交公开议题。

## 许可

许可范围与第三方材料归属的权威映射见 [NOTICE](../../NOTICE)。
```

Use this complete content for `docs/i18n/README.el.md`:

```markdown
[Ιστότοπος](https://agent-axiom.github.io/laconian/) · [English](../../README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

![Laconian — Η συντομότερη ολοκληρωμένη απάντηση.](../../assets/laconian-banner.png)

# Laconian

Ο στόχος του Laconian είναι η συντομότερη ολοκληρωμένη απάντηση — όχι απλώς η συντομότερη απάντηση.

Το Laconian είναι ένα δημόσιο εγχείρημα φιλοσοφίας που συνδυάζει μία φορητή δεξιότητα Markdown
ενός μόνο αρχείου με ένα ανοικτό benchmark. Η δεξιότητα ζητά από έναν πράκτορα να προσδιορίσει
πρώτα την πλήρη απάντηση και έπειτα να αφαιρέσει μόνο ό,τι δεν αποδυναμώνει την ορθότητα,
την ασφάλεια, τα ουσιώδη γεγονότα, τη σαφήνεια ή την πρακτική επάρκεια.

## Κατάσταση

Το έργο βρίσκεται σε προκυκλοφοριακό στάδιο και αναπτύσσεται ενεργά. Δεν υπάρχει ακόμη δημόσιο
αποτέλεσμα benchmark. Η επανάληψη χωρίς σύνδεση και τα fixtures των δοκιμών επικυρώνουν μόνο την
αρχιτεκτονική και τη διαδικασία αξιολόγησης· δεν αποτελούν τεκμήρια επιδόσεων ούτε δείχνουν ότι
το `if` κερδίζει, εξοικονομεί κάποια συγκεκριμένη ποσότητα ή αποδίδει καλύτερα από άλλο σκέλος.

## Ξεκινήστε εδώ

- [Η πλήρης δεξιότητα `if`](../../skills/if/SKILL.md) — η φορητή δεξιότητα Markdown ενός αρχείου.
- [Οδηγός χρήσης της δεξιότητας](../using-the-skill.md) — λειτουργία, όρια, εγκατάσταση και απεγκατάσταση.
- [Οδηγός benchmark](../../benchmarks/README.md) — σκέλη σύγκρισης, πύλη ποιότητας, επανάληψη χωρίς σύνδεση και προαιρετική πραγματική εκτέλεση.

## Τεκμηρίωση

- [Ευρετήριο τεκμηρίωσης](../README.md)
- [Φιλοσοφία και ιστορικό πλαίσιο](../philosophy.md)
- [Σχεδιασμός έργου](../design.md)
- [Δεδομένα αξιολόγησης](../../evals/README.md)
- [Μεθοδολογία benchmark](../../benchmarks/methodology.md)

## Συνεισφορά

Ξεκινήστε από το [CONTRIBUTING.md](../../CONTRIBUTING.md). Οι αναφορές που αφορούν την ασφάλεια
ακολουθούν το [SECURITY.md](../../SECURITY.md) και όχι ένα δημόσιο issue.

## Άδειες χρήσης

Ο επίσημος χάρτης αδειών χρήσης και απόδοσης υλικού τρίτων βρίσκεται στο [NOTICE](../../NOTICE).
```

- [ ] **Step 6: Replace the reconstructed Laconian Doric file while preserving its warning**

Use this complete content for `docs/i18n/README.grc-x-laconian.md`:

```markdown
> **Experimental reconstruction.** This edition is a modern experiment in fragmentarily attested
> Laconian Doric; it is not an authentic ancient text. Identifiers and many unattested software
> terms remain in English and are code-formatted. Expert review and corrections are invited.
>
> **Πειραματικὴ νεωτέρα ἀνάπλασις.** Ἁ παλαιὰ Λακωνικὰ διάλεκτος κατὰ μέρος μόνον
> μαρτυρεῖται· τόδε νεώτερον κείμενον οὐ γνήσιον ἀρχαῖον ἐστί. Τὰ νεώτερα τεχνικὰ
> ὀνόματα Ἀγγλιστὶ καὶ ἐν σημείοις γράφεται· τοὺς δὲ εἰδήμονας ἐπισκοπεῖν καὶ
> διορθοῦν παρακαλέομες.

**Σημείωσις ἐκδοτικά.** Ἁ ἀνάπλασις συντηρητικῶς χρῆται ἐπιλελεγμένοις Δωρικοῖς καὶ
δυτικοῖς Ἑλληνικοῖς τύποις—τῷ μακρῷ α, τῷ μορίῳ κα, καὶ τῇ παρὰ Πλουτάρχῳ
μαρτυρουμένᾳ λέξει `αἴκα`. Οὐχ ὑπολαμβάνει ὡς ἕκαστος τύπος τοῦδε τοῦ νεωτέρου
κειμένου ἐν παλαιᾷ Λακωνικᾷ μαρτυρεῖται, οὐδὲ τὰς ἀμφισβητουμένας ἢ ὀψιτέρας
φωνητικὰς γραφὰς πανταχοῦ μιμεῖται. Τὰ ἀμαρτήματα καὶ αἱ διορθώσεις παρὰ τῶν
εἰδημόνων ἀσμένως δεχόμεθα.

[Website](https://agent-axiom.github.io/laconian/) · [English](../../README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

![Laconian — The shortest complete answer.](../../assets/laconian-banner.png)

# Laconian

Τὸ Laconian τὰν βραχυτάταν τελείαν ἀπόκρισιν αἰτεῖ—οὐ τὰν βραχυτάταν μόνον.

Τὸ Laconian δημόσιον φιλοσοφικὸν ἔργον ἐστίν, ἓν φορητὸν `Markdown skill`
καὶ ἀνεῳγμένον `benchmark` ἔχον, ὃ δοκιμάζει πότερον ἁ βραχύτας τὰν τελείαν
ἀπόκρισιν σώζει.

Τὸ [`skills/if/SKILL.md`](../../skills/if/SKILL.md) ὅλον τὸ `installable artifact` ἐστίν.

## Κατάστασις

Τὸ Laconian `pre-release` ἐστὶ καὶ ἔτι ποιεῖται. Ἔχει ὁδὸν `evaluation`
πιστευτηρίων μὴ δεομέναν καὶ προαιρετικὸν ζῶντα `provider adapter`.

Οὐδὲν δημόσιον ἀποτέλεσμα τοῦ `benchmark` ἔτι ἔστιν. Τὰ `smoke` καὶ
`replay fixtures` τὰν ὁδὸν τοῦ `evaluation` δοκιμάζει· οὐ δημόσια τεκμήρια τοῦ
`performance` ἐστίν, οὐδὲ δηλοῖ ὅτι τὸ `if` νικᾷ, δαπάναν σῴζει, ἢ ἄλλου
συγκριτικοῦ `arm` βέλτιον ἔργον ποιεῖ.

## Ἄρξαι ἐνθένδε

- [Ἀνάγνωθι τὸ `skill`](../../skills/if/SKILL.md)
- [Ἐγκατάστησον καὶ χρῆσαι αὐτῷ](../using-the-skill.md)
- [Τὸ `benchmark` τέλεσον](../../benchmarks/README.md)

## `Documentation`

- [Πίναξ τοῦ `documentation`](../README.md)
- [Φιλοσοφία](../philosophy.md)
- [`Design`](../design.md)
- [Δεδομένα τοῦ `evaluation`](../../evals/README.md)
- [Μέθοδος τοῦ `benchmark`](../../benchmarks/methodology.md)

## Συνεισφορά καὶ ἀσφάλεια

Ἄρξαι ἀπὸ τοῦ [CONTRIBUTING.md](../../CONTRIBUTING.md), εἰ συνεισφέρειν βούλει.
Τὰ περὶ ἀσφαλείας ἀγγέλματα κατὰ τὸ [SECURITY.md](../../SECURITY.md), οὐκ ἐν
δημοσίῳ `issue`, πέμπεται.

## Ἄδεια

Τὸ ἀποθετήριον μικτὸν πίνακα ἀδειῶν ἔχει. Ὅρα τὸ [NOTICE](../../NOTICE), ὅ
ἐστι κύριος πίναξ τῶν ὁδῶν καὶ ἀδειῶν.
```

- [ ] **Step 7: Run the localization and active-link tests**

Run:

```bash
uv run pytest -q tests/test_public_contract.py -k "readme_editions or links_to_the_other_five or localized_readmes or conventional_markdown or active_markdown or reconstructed_readme"
```

Expected: PASS.

- [ ] **Step 8: Run the complete public-document contract**

Run:

```bash
uv run pytest -q tests/test_public_contract.py
```

Expected: PASS.

- [ ] **Step 9: Commit the complete green documentation reorganization**

```bash
git add README.md benchmarks/README.md docs/README.md docs/using-the-skill.md docs/philosophy.md docs/i18n tests/test_public_contract.py
git commit -m "docs: reorganize project documentation"
```

### Task 4: Full verification and packaging check

**Files:**
- Verify: all changed documentation and `tests/test_public_contract.py`

- [ ] **Step 1: Run formatting and static checks**

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
```

Expected: all three commands exit 0 with no formatting, lint, or type errors.

- [ ] **Step 2: Run the full offline test suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Check the acceptance invariants directly**

Run:

```bash
test "$(find . -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')" = "4"
test "$(wc -l < README.md | tr -d ' ')" -ge 40
test "$(wc -l < README.md | tr -d ' ')" -le 70
test "$(find docs/i18n -maxdepth 1 -type f -name 'README.*.md' | wc -l | tr -d ' ')" = "5"
git diff --check da4bc05..HEAD
```

Expected: every command exits 0.

- [ ] **Step 4: Build package metadata from the concise root README**

Run:

```bash
docs_build_dir="$(mktemp -d /private/tmp/laconian-docs-build.XXXXXX)"
uv build --out-dir "$docs_build_dir"
unzip -p "$docs_build_dir"/laconian_eval-*.whl '*/METADATA' | rg -F "Laconian asks for the shortest complete answer"
```

Expected: wheel and source distribution build successfully, and the wheel metadata contains the
new README promise.

- [ ] **Step 5: Review the final tracked diff without touching unrelated files**

Run:

```bash
git status --short --branch
git diff --stat da4bc05..HEAD
git diff --name-status da4bc05..HEAD
```

Expected: tracked changes are limited to the documentation and public-contract files named in
this plan. Unrelated images and existing untracked `output/` and `.DS_Store` files remain
untouched.
