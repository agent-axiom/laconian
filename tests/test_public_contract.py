import re
from pathlib import Path

import pytest

from laconian_eval.models import ActivationCaseFile, ResponseCaseFile
from laconian_eval.yaml_io import safe_load_unique

ROOT = Path(__file__).resolve().parents[1]

README_FILES = {
    "English": "README.md",
    "Русский": "README.ru.md",
    "简体中文": "README.zh-CN.md",
    "Ελληνικά": "README.el.md",
    "Italiano": "README.it.md",
    "Laconian Doric (reconstructed)": "README.grc-x-laconian.md",
}
MODERN_READMES = {
    "README.md": ("provider cost", "model availability", "API keys"),
    "README.ru.md": ("стоим", "доступност", "ключ"),
    "README.zh-CN.md": ("费用", "可用", "API 密钥"),
    "README.el.md": ("κόστος", "διαθεσιμότητα", "κλειδιά API"),
    "README.it.md": ("costo", "disponibilità", "chiavi API"),
}
ARMS = ("baseline", "concise", "caveman", "if")
LIVE_RUN_BLOCK = """export OPENAI_API_KEY="your key"
uv sync --extra openai
uv run laconian run evals/manifests/openai-example.yaml --results-root benchmarks/results"""
SOURCE_URLS = (
    "https://www.perseus.tufts.edu/hopper/text?doc=Perseus%3Atext%3A2008.01.0287%3Asection%3D17",
    "https://era.ed.ac.uk/items/385e1ac5-539c-47f6-94b7-8ab83a94a139",
    "https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Polybius/9%2A.html",
)
CAVEMAN_COMMIT = "781c384cafc28d7ca392014dbab569f985b5b2fd"
CAVEMAN_SHA256 = "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"
PLUGIN_ADD = "codex plugin marketplace add agent-axiom/laconian --ref v0.1.0-alpha.1 --json"
PLUGIN_INSTALL = "codex plugin add laconian@laconian --json"
PLUGIN_LIST = "codex plugin list --marketplace laconian --json"
PLUGIN_REMOVE = "codex plugin remove laconian@laconian --json"
MARKETPLACE_REMOVE = "codex plugin marketplace remove laconian --json"
STANDALONE_URL = (
    "https://raw.githubusercontent.com/agent-axiom/laconian/v0.1.0-alpha.1/skills/if/SKILL.md"
)
STANDALONE_REMOVE = 'rm "$HOME/.agents/skills/if/SKILL.md"'
STANDALONE_RMDIR = 'rmdir "$HOME/.agents/skills/if"'
APPROVED_NEGATED_SOCIAL_CLAIMS = (
    "not proven",
    "no numeric token savings",
    "does not claim numeric token savings",
    "not a benchmark winner",
    "not a universal-directory listing",
)


def _read(path: str) -> str:
    full_path = ROOT / path
    assert full_path.is_file(), f"missing public file: {path}"
    return full_path.read_text(encoding="utf-8")


def _social_claim_scan_text(text: str) -> str:
    folded = text.casefold()
    for approved in APPROVED_NEGATED_SOCIAL_CLAIMS:
        pattern = rf"(?<![\w-]){re.escape(approved)}(?![\w-])"
        folded = re.sub(pattern, "", folded)
    return folded


@pytest.mark.parametrize("filename", README_FILES.values())
def test_all_six_readme_editions_exist(filename: str) -> None:
    assert (ROOT / filename).is_file(), f"missing README edition: {filename}"


@pytest.mark.parametrize("filename", README_FILES.values())
def test_every_readme_has_pinned_install_paths(filename: str) -> None:
    text = _read(filename)
    assert PLUGIN_ADD in text
    assert PLUGIN_INSTALL in text
    assert PLUGIN_LIST in text
    assert PLUGIN_REMOVE in text
    assert MARKETPLACE_REMOVE in text
    assert STANDALONE_URL in text
    assert "$laconian:if" in text
    assert "$if" in text
    assert "<agent-skills-directory>" not in text

    rm_lines = [line for line in text.splitlines() if line.startswith("rm ")]
    rmdir_lines = [line for line in text.splitlines() if line.startswith("rmdir ")]
    assert rm_lines == [STANDALONE_REMOVE]
    assert rmdir_lines == [STANDALONE_RMDIR]


def test_greek_readme_describes_a_specific_pinned_version() -> None:
    text = _read("README.el.md")
    assert "με σταθερή έκδοση" not in text
    assert text.count("σε συγκεκριμένη έκδοση") == 2


@pytest.mark.parametrize("filename", README_FILES.values())
def test_each_readme_links_to_the_other_five(filename: str) -> None:
    text = _read(filename)
    for language, target in README_FILES.items():
        if target != filename:
            assert f"[{language}]({target})" in text


@pytest.mark.parametrize("filename", README_FILES.values())
def test_every_readme_names_all_arms_without_percentage_claims(filename: str) -> None:
    text = _read(filename)
    for arm in ARMS:
        assert f"`{arm}`" in text
    # Ignore percent-encoded source URLs such as ``%3A`` and reject written rates.
    assert re.search(r"\b\d+(?:[.,]\d+)?\s*%(?![0-9A-Fa-f])", text) is None


def test_english_readme_promise_and_section_order() -> None:
    text = _read("README.md")
    assert "Laconian asks for the shortest complete answer—not the shortest answer." in text
    markers = (
        "# Laconian",
        "## Status",
        "## Why “if”?",
        "## What the skill does",
        "## What the skill does not do",
        "## Install and uninstall",
        "## Four-arm benchmark",
        "## Quality gate and reported metrics",
        "## Quickstart",
        "## Repository map",
        "## Contributing",
        "## Licensing",
        "## Historical and linguistic sources",
    )
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_english_readme_frames_the_anecdote_carefully() -> None:
    text = _read("README.md")
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
    text = _read("README.grc-x-laconian.md")
    assert "Experimental reconstruction" in text
    assert "not an authentic ancient text" in text
    assert "Πειραματικὴ νεωτέρα ἀνάπλασις" in text
    assert "αἴκα" in text


@pytest.mark.parametrize(("filename", "warning_terms"), MODERN_READMES.items())
def test_modern_readmes_have_exact_live_run_block_and_warnings(
    filename: str, warning_terms: tuple[str, str, str]
) -> None:
    text = _read(filename)
    assert LIVE_RUN_BLOCK in text
    folded = text.casefold()
    for term in warning_terms:
        assert term.casefold() in folded
    assert "sk-" not in text


def test_english_quickstart_matches_the_current_cli() -> None:
    text = _read("README.md")
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
        ('uv run laconian report "$RUN_DIR/scored/scored.jsonl" --output "$RUN_DIR/report.md"'),
    )
    for command in commands:
        assert command in text


def test_english_readme_exposes_the_mixed_license_map() -> None:
    text = _read("README.md")
    for phrase in (
        "Apache-2.0",
        "CC BY 4.0",
        "MIT",
        "LICENSES/CC-BY-4.0.txt",
        "LICENSES/CAVEMAN-MIT.txt",
        "NOTICE",
    ):
        assert phrase in text


def test_notice_maps_new_public_documentation_to_cc_by() -> None:
    notice = _read("NOTICE")
    assert (
        "CHANGELOG.md, CONTRIBUTING.md, SECURITY.md, and evals/README.md: CC-BY-4.0."
        in notice.splitlines()
    )
    assert ".codex-plugin/, .agents/, and tools/: Apache-2.0." in notice.splitlines()
    assert "assets/social/ and docs/social/: CC-BY-4.0." in notice.splitlines()


def test_core_public_document_files_exist() -> None:
    required = (
        "evals/README.md",
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


def test_changelog_keeps_unreleased_and_records_the_alpha_boundary() -> None:
    text = _read("CHANGELOG.md")
    assert "## [Unreleased]" in text
    assert "## [0.1.0-alpha.1] - 2026-08-30" in text
    assert "walking skeleton" in text
    assert "No public benchmark result" in text


def test_alpha_release_notes_describe_only_the_experimental_release() -> None:
    text = _read("docs/releases/v0.1.0-alpha.1.md")
    for phrase in (
        "one-file skill",
        "repo plugin",
        "Python 3.11 and 3.14",
        "SHA-256",
        "experimental alpha",
        "No public benchmark result",
    ):
        assert phrase.casefold() in text.casefold()


@pytest.mark.parametrize(
    ("approved", "affirmative", "prohibited"),
    (
        ("Not proven.", "Proven.", "proven"),
        ("No numeric token savings.", "Numeric token savings.", "numeric token savings"),
        (
            "Does not claim numeric token savings.",
            "Claims numeric token savings.",
            "numeric token savings",
        ),
        ("Not a benchmark winner.", "Benchmark winner.", "benchmark winner"),
        (
            "Not a universal-directory listing.",
            "Universal-directory listing.",
            "universal-directory listing",
        ),
    ),
)
def test_social_claim_guard_allows_only_approved_negations(
    approved: str, affirmative: str, prohibited: str
) -> None:
    assert prohibited not in _social_claim_scan_text(approved)
    assert prohibited in _social_claim_scan_text(affirmative)


def test_social_launch_copy_is_explicitly_experimental() -> None:
    text = _read("docs/social/alpha-launch.md")
    publishable, separator, boundaries = text.partition("## Claim boundaries")
    assert separator == "## Claim boundaries"
    _, prohibited_heading, prohibited_block = boundaries.partition("Prohibited claims:")
    assert prohibited_heading == "Prohibited claims:"
    assert "Illustrative edit, not benchmark output." in publishable
    assert "Иллюстративное редактирование, не результат бенчмарка." in publishable
    assert "No public benchmark result" in text
    assert "one-file workflow" in text
    assert "experimental alpha" in text
    assert "open benchmark under development" in text
    publishable_claims = _social_claim_scan_text(publishable)
    for prohibited in (
        "proven",
        "numeric token savings",
        "benchmark winner",
        "universal-directory listing",
    ):
        assert f"- {prohibited}" in prohibited_block
        assert prohibited not in publishable_claims
    assert re.search(r"\b\d+(?:[.,]\d+)?\s*%", text) is None
