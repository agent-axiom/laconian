import os
import re
from pathlib import Path

import pytest

from laconian_eval.models import ActivationCaseFile, ResponseCaseFile
from laconian_eval.yaml_io import safe_load_unique

ROOT = Path(__file__).resolve().parents[1]

README_FILES = {
    "English": "README.md",
    "Русский": "docs/i18n/README.ru.md",
    "简体中文": "docs/i18n/README.zh-CN.md",
    "Ελληνικά": "docs/i18n/README.el.md",
    "Italiano": "docs/i18n/README.it.md",
    "Laconian Doric (reconstructed)": "docs/i18n/README.grc-x-laconian.md",
}
LIVE_RUN_BLOCK = """export OPENAI_API_KEY="your key"
uv sync --extra openai
uv run laconian run evals/manifests/openai-example.yaml --results-root benchmarks/results"""
SOURCE_URLS = (
    "https://www.perseus.tufts.edu/hopper/text?doc=Perseus%3Atext%3A2008.01.0287%3Asection%3D17",
    "https://era.ed.ac.uk/items/385e1ac5-539c-47f6-94b7-8ab83a94a139",
    "https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Polybius/9%2A.html",
)
LOCALIZED_STATUS_MARKERS = {
    "docs/i18n/README.ru.md": "Публичных результатов бенчмарка пока нет",
    "docs/i18n/README.zh-CN.md": "目前还没有可用的公开基准结果",
    "docs/i18n/README.el.md": "Δεν υπάρχει ακόμη δημόσιο αποτέλεσμα benchmark",
    "docs/i18n/README.it.md": "Non sono ancora disponibili risultati pubblici del benchmark",
    "docs/i18n/README.grc-x-laconian.md": ("Οὐδὲν δημόσιον ἀποτέλεσμα τοῦ `benchmark` ἔτι ἔστιν"),
}
LOCALIZED_HEADING_MARKERS = {
    "docs/i18n/README.ru.md": (
        "# Laconian",
        "## Статус",
        "## С чего начать",  # noqa: RUF001
        "## Документация",
        "## Участие в проекте и безопасность",
        "## Лицензирование",
    ),
    "docs/i18n/README.zh-CN.md": (
        "# Laconian",
        "## 状态",
        "## 从这里开始",
        "## 文档",
        "## 参与贡献",
        "## 许可",
    ),
    "docs/i18n/README.el.md": (
        "# Laconian",
        "## Κατάσταση",
        "## Ξεκινήστε εδώ",
        "## Τεκμηρίωση",
        "## Συνεισφορά",
        "## Άδειες χρήσης",
    ),
    "docs/i18n/README.it.md": (
        "# Laconian",
        "## Stato",
        "## Da dove iniziare",
        "## Documentazione",
        "## Contributi e sicurezza",
        "## Licenze",
    ),
    "docs/i18n/README.grc-x-laconian.md": (
        "# Laconian",
        "## Κατάστασις",
        "## Ἄρξαι ἐνθένδε",
        "## `Documentation`",
        "## Συνεισφορά καὶ ἀσφάλεια",
        "## Ἄδεια",
    ),
}
LOCALIZED_CORE_MARKERS = {
    "docs/i18n/README.ru.md": (
        "Laconian просит дать самый короткий законченный ответ, а не просто самый короткий ответ.",  # noqa: RUF001
        "Это публичный философский проект",
    ),
    "docs/i18n/README.zh-CN.md": (
        "Laconian 追求最短的完整答案，而不是最短的答案。",  # noqa: RUF001
        "Laconian 是一个公共哲学项目",
    ),
    "docs/i18n/README.el.md": (
        "Ο στόχος του Laconian είναι η συντομότερη ολοκληρωμένη απάντηση — όχι απλώς η συντομότερη απάντηση.",  # noqa: E501, RUF001
        "Το Laconian είναι ένα δημόσιο εγχείρημα φιλοσοφίας",  # noqa: RUF001
    ),
    "docs/i18n/README.it.md": (
        "Laconian chiede la risposta completa più breve, non semplicemente la risposta più breve.",
        "È un progetto filosofico pubblico",
    ),
    "docs/i18n/README.grc-x-laconian.md": (
        "Τὸ Laconian τὰν βραχυτάταν τελείαν ἀπόκρισιν αἰτεῖ—οὐ τὰν βραχυτάταν μόνον.",
        "Τὸ Laconian δημόσιον φιλοσοφικὸν ἔργον ἐστίν",
    ),
}
LOCALIZED_ENGLISH_ONLY_NOTICES = {
    "docs/i18n/README.ru.md": ("Подробная документация пока доступна только на английском языке:"),
    "docs/i18n/README.zh-CN.md": "详细文档目前仅提供英文版本：",  # noqa: RUF001
    "docs/i18n/README.el.md": (
        "Η αναλυτική τεκμηρίωση είναι προς το παρόν διαθέσιμη μόνο στα αγγλικά:"  # noqa: RUF001
    ),
    "docs/i18n/README.it.md": (
        "La documentazione dettagliata è per ora disponibile solo in inglese:"
    ),
    "docs/i18n/README.grc-x-laconian.md": (
        "Τὸ λεπτομερὲς `documentation` Ἀγγλιστὶ μόνον νῦν γέγραπται:"
    ),
}
GITHUB_BLOB_ROOT = "https://github.com/agent-axiom/laconian/blob/main/"
GITHUB_RAW_ROOT = "https://raw.githubusercontent.com/agent-axiom/laconian/main/"
ROOT_README_TARGETS = (
    "README.md",
    "docs/i18n/README.ru.md",
    "docs/i18n/README.zh-CN.md",
    "docs/i18n/README.el.md",
    "docs/i18n/README.it.md",
    "docs/i18n/README.grc-x-laconian.md",
    "skills/if/SKILL.md",
    "docs/using-the-skill.md",
    "benchmarks/README.md",
    "docs/README.md",
    "docs/philosophy.md",
    "docs/design.md",
    "evals/README.md",
    "benchmarks/methodology.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "NOTICE",
)
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
CAVEMAN_COMMIT = "781c384cafc28d7ca392014dbab569f985b5b2fd"
CAVEMAN_SHA256 = "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"


def _relative_link(source: str, target: str) -> str:
    source_dir = (ROOT / source).parent
    return Path(os.path.relpath(ROOT / target, start=source_dir)).as_posix()


def _canonical_repository_url(target: str) -> str:
    return f"{GITHUB_BLOB_ROOT}{target}"


def _read(path: str) -> str:
    full_path = ROOT / path
    assert full_path.is_file(), f"missing public file: {path}"
    return full_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("filename", README_FILES.values())
def test_all_six_readme_editions_exist(filename: str) -> None:
    assert (ROOT / filename).is_file(), f"missing README edition: {filename}"


@pytest.mark.parametrize("filename", README_FILES.values())
def test_each_readme_links_to_the_other_five(filename: str) -> None:
    text = _read(filename)
    for language, target in README_FILES.items():
        if target != filename:
            href = (
                _canonical_repository_url(target)
                if filename == "README.md"
                else _relative_link(filename, target)
            )
            assert f"[{language}]({href})" in text


def test_english_readme_is_a_concise_entry_point() -> None:
    text = _read("README.md")
    lines = text.splitlines()
    assert "Laconian asks for the shortest complete answer—not the shortest answer." in text
    assert "No public benchmark result is available yet." in text
    assert "they do not show that `if` wins" in " ".join(text.split())
    assert 40 <= len(lines) <= 70

    markers = (
        "# Laconian",
        "## Status",
        "## Start here",
        "## Documentation",
        "## Contributing and security",
        "## License",
    )
    positions = [lines.index(marker) for marker in markers]
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
        assert f"]({_canonical_repository_url(target)})" in text


def test_english_readme_uses_canonical_repository_urls() -> None:
    text = _read("README.md")
    link_targets = set(re.findall(r"!?\[[^]]*\]\(([^)]+)\)", text))
    expected_targets = {
        "https://agent-axiom.github.io/laconian/",
        f"{GITHUB_RAW_ROOT}assets/laconian-banner.png",
        *(_canonical_repository_url(target) for target in ROOT_README_TARGETS),
    }
    assert link_targets == expected_targets
    for target in ROOT_README_TARGETS:
        assert (ROOT / target).is_file(), f"canonical README target is missing: {target}"


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


def test_reconstructed_readme_has_bilingual_warning_and_attested_word() -> None:
    text = _read("docs/i18n/README.grc-x-laconian.md")
    assert "Experimental reconstruction" in text
    assert "not an authentic ancient text" in text
    assert "Πειραματικὴ νεωτέρα ἀνάπλασις" in text
    assert "αἴκα" in text


@pytest.mark.parametrize(("filename", "headings"), LOCALIZED_HEADING_MARKERS.items())
def test_localized_readmes_have_ordered_structure(filename: str, headings: tuple[str, ...]) -> None:
    text = _read(filename)
    lines = text.splitlines()
    positions = [lines.index(heading) for heading in headings]
    assert positions == sorted(positions)
    normalized = " ".join(text.split())
    for marker in LOCALIZED_CORE_MARKERS[filename]:
        assert marker in normalized


@pytest.mark.parametrize(("filename", "notice"), LOCALIZED_ENGLISH_ONLY_NOTICES.items())
def test_localized_readmes_disclose_english_only_detailed_docs(filename: str, notice: str) -> None:
    assert notice in " ".join(_read(filename).split())


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


def test_benchmark_guide_defines_all_comparison_arms_without_percentage_claims() -> None:
    text = _read("benchmarks/README.md")
    expected_rows = (
        "| `baseline` | None |",
        "| `concise` | Exactly `Answer concisely.` |",
        "| `caveman` | The pinned offline Caveman skill snapshot |",
        "| `if` | The exact bytes of [`skills/if/SKILL.md`](../skills/if/SKILL.md) |",
    )
    comparison_heading = "## Comparison arms"
    next_heading = "## Quality before brevity"
    assert comparison_heading in text
    assert next_heading in text
    comparison_section = text.split(comparison_heading, maxsplit=1)[1]
    comparison_section = comparison_section.split(next_heading, maxsplit=1)[0]

    lines = comparison_section.splitlines()
    table_header = "| Arm | Added instruction |"
    assert table_header in lines
    header_index = lines.index(table_header)
    assert lines[header_index + 1] == "|---|---|"

    actual_rows = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        actual_rows.append(line)
    assert tuple(actual_rows) == expected_rows
    assert "The primary comparison is `if` versus `concise`" in text
    assert re.search(r"\b\d+(?:[.,]\d+)?\s*%(?![0-9A-Fa-f])", text) is None


def test_benchmark_guide_puts_quality_before_brevity() -> None:
    text = _read("benchmarks/README.md")
    assert "## Quality before brevity" in text
    assert "A failed answer cannot win merely by being short" in " ".join(text.split())


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


def test_benchmark_guide_warns_dependency_sync_may_use_network() -> None:
    text = _read("benchmarks/README.md")
    install_heading = "## Install dependencies"
    replay_heading = "## Offline replay"
    assert install_heading in text
    assert replay_heading in text
    install_section = text.split(install_heading, maxsplit=1)[1]
    install_section = install_section.split(replay_heading, maxsplit=1)[0]
    folded = install_section.casefold()
    assert "uv sync --all-extras" in install_section
    assert "may require" in folded
    assert "package index" in folded
    assert "network access" in folded


def test_benchmark_guide_scopes_offline_claim_to_replay_commands() -> None:
    text = _read("benchmarks/README.md")
    replay_heading = "## Offline replay"
    live_heading = "## Optional live run"
    assert replay_heading in text
    assert live_heading in text
    replay_section = text.split(replay_heading, maxsplit=1)[1]
    replay_section = replay_section.split(live_heading, maxsplit=1)[0]
    folded = replay_section.casefold()
    assert "after dependencies are installed" in folded
    assert "no network access or provider credentials" in folded
    assert "uv sync --all-extras" not in replay_section
    for operation in ("validate", "run", "score", "report"):
        assert f"uv run laconian {operation}" in replay_section


def test_benchmark_guide_has_exact_live_run_block_and_warnings() -> None:
    text = _read("benchmarks/README.md")
    assert LIVE_RUN_BLOCK in text
    for warning in ("provider cost", "model availability", "API keys"):
        assert warning.casefold() in text.casefold()
    assert "sk-" not in text


def test_english_readme_links_to_the_authoritative_license_map() -> None:
    text = _read("README.md")
    assert f"[NOTICE]({_canonical_repository_url('NOTICE')})" in text


def test_notice_maps_new_public_documentation_to_cc_by() -> None:
    notice = _read("NOTICE")
    assert (
        "CHANGELOG.md, CONTRIBUTING.md, SECURITY.md, and evals/README.md: CC-BY-4.0."
        in notice.splitlines()
    )


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
        assert f"]({target})" in text
    assert "uv run laconian run" not in text


def test_using_the_skill_owns_installation_and_boundaries() -> None:
    text = _read("docs/using-the-skill.md")
    normalized = " ".join(text.split())
    for phrase in (
        "../skills/if/SKILL.md",
        "shortest complete answer",
        "does not turn prose into primitive speech",
        "It makes no promise that every agent or model will respond identically.",
        "From the repository root",
        'mkdir -p "<agent-skills-directory>/if"',
        'cp skills/if/SKILL.md "<agent-skills-directory>/if/SKILL.md"',
        'rm "<agent-skills-directory>/if/SKILL.md"',
        "no scripts, dependencies, permissions, references, assets, network calls",
    ):
        assert phrase in normalized


def test_philosophy_credits_fidelity_method_without_a_lossless_claim() -> None:
    text = _read("docs/philosophy.md")
    assert "lossless-doc-compress" in text
    assert "8dd0d88852fe7445e9d2627c59124f0f161040c1" in text
    assert "does not claim that model editing is lossless" in " ".join(text.split())


def test_methodology_defines_reproducibility_and_quality_contracts() -> None:
    text = _read("benchmarks/methodology.md")
    required = (
        "A failed answer cannot win",
        "activation suite",
        "response suite",
        "system_suffix",
        "Answer concisely.",
        CAVEMAN_COMMIT,
        CAVEMAN_SHA256,
        "arm-order seed",
        "repetition",
        "authentication",
        "hard gate",
        "semantic gate",
        "concise - if",
        "matched case/repetition",
        "raw.jsonl",
        "manifest.json",
        "scored.jsonl",
        "summary.json",
        "report.md",
        "dated price snapshot",
        "cached-input",
        "confidence interval",
        "negative",
        "inconclusive",
        "The walking-skeleton CLI does not calculate confidence intervals.",
    )
    folded = text.casefold()
    for phrase in required:
        assert phrase.casefold() in folded


def test_evals_readme_separates_inputs_fixtures_and_evidence() -> None:
    text = _read("evals/README.md")
    for phrase in (
        "evals/cases/",
        "evals/manifests/",
        "tests/fixtures/",
        "benchmarks/results/",
        "synthetic",
        "not benchmark results",
        "activation",
        "response",
    ):
        assert phrase in text


@pytest.mark.parametrize(
    "filename",
    ("docs/design.md", "benchmarks/methodology.md", "evals/README.md"),
)
def test_provenance_docs_name_the_artifact_schema_fields(filename: str) -> None:
    text = _read(filename)
    assert "runner_version" in text
    assert "case_definition_sha256" in text


def test_case_contribution_guide_documents_valid_exact_schemas() -> None:
    text = _read("docs/contributing-cases.md")
    blocks = re.findall(r"```yaml\n(.*?)\n```", text, flags=re.DOTALL)
    parsed = [safe_load_unique(block) for block in blocks]
    response_files = [
        value for value in parsed if isinstance(value, dict) and value.get("kind") == "response"
    ]
    activation_files = [
        value for value in parsed if isinstance(value, dict) and value.get("kind") == "activation"
    ]
    assert len(response_files) == 1
    assert len(activation_files) == 1
    response = ResponseCaseFile.model_validate(response_files[0])
    activation = ActivationCaseFile.model_validate(activation_files[0])
    assert {case.locale for case in response.cases} == {"en", "ru"}
    assert {case.locale for case in activation.cases} == {"en", "ru"}

    required_schema_terms = (
        "scenario_id",
        "required_literals",
        "forbidden_literals",
        "required_json_keys",
        "required_yaml_keys",
        "min_sentences",
        "max_sentences",
        "required_facts",
        "material_warning",
        "expected_activation",
        "rationale",
        "evidence-backed",
        "exactly one `en` and one `ru`",
        "designed only to favor `if`",
        "unknown fields",
        "duplicate",
    )
    for phrase in required_schema_terms:
        assert phrase in text


def test_design_and_philosophy_preserve_the_project_boundary() -> None:
    design = _read("docs/design.md")
    philosophy = _read("docs/philosophy.md")
    for phrase in (
        "skills/if/SKILL.md",
        "Markdown-only",
        "provider-neutral",
        "activation",
        "response",
        "raw JSONL",
        "Generated model text is never executed",
    ):
        assert phrase.casefold() in design.casefold()
    for phrase in (
        "shortest complete answer",
        "Brevity never overrides",
        "primitive speech",
        "failed answer",
        "negative result",
        "uncertainty",
    ):
        assert phrase.casefold() in philosophy.casefold()


def test_contributing_documents_quality_and_evidence_rules() -> None:
    text = _read("CONTRIBUTING.md")
    for phrase in (
        "uv sync --all-extras",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run mypy src",
        "uv run pytest -q",
        "test-driven development",
        "exactly one English and one Russian",
        "raw artifacts",
    ):
        assert phrase.casefold() in text.casefold()


def test_security_uses_private_reporting_and_names_scope() -> None:
    text = _read("SECURITY.md")
    for phrase in (
        "https://github.com/agent-axiom/laconian/security/advisories/new",
        "secret exposure",
        "unsafe execution of model output",
        "benchmark artifact path traversal",
        "Do not open a public issue",
    ):
        assert phrase.casefold() in text.casefold()


def test_changelog_starts_unreleased_without_a_release_date() -> None:
    text = _read("CHANGELOG.md")
    assert "## [Unreleased]" in text
    assert "walking skeleton" in text
    assert "No public benchmark result" in text
    assert re.search(r"^## \[v?\d[^]]*\]", text, flags=re.MULTILINE) is None
