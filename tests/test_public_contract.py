import hashlib
import os
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from laconian_eval.models import ActivationCaseFile, ResponseCaseFile, SemanticRubric
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
STANDALONE_SHA256 = "5c549c7c492c66a6b3ac5560499353b71615ffc6b93c4b1811f741a8f3d54006"
STANDALONE_INSTALL_BLOCK = f"""(
  set -eu
  skill_dir="$HOME/.agents/skills/if"
  skill_target="$skill_dir/SKILL.md"
  skill_expected_sha256="{STANDALONE_SHA256}"
  test ! -L "$skill_dir"
  mkdir -p "$skill_dir"
  test ! -L "$skill_dir"
  test ! -e "$skill_target"
  test ! -L "$skill_target"
  skill_tmp="$(mktemp "$skill_dir/.SKILL.md.XXXXXX")"
  trap 'rm -f "$skill_tmp"' EXIT
  curl -fsSL "{STANDALONE_URL}" -o "$skill_tmp"
  if command -v sha256sum >/dev/null 2>&1; then
    skill_actual_sha256="$(sha256sum "$skill_tmp")"
  else
    skill_actual_sha256="$(shasum -a 256 "$skill_tmp")"
  fi
  skill_actual_sha256="${{skill_actual_sha256%% *}}"
  test "$skill_actual_sha256" = "$skill_expected_sha256"
  chmod 0644 "$skill_tmp"
  ln "$skill_tmp" "$skill_target"
  if ! test "$skill_tmp" -ef "$skill_target"; then
    skill_misdirected="$skill_target/${{skill_tmp##*/}}"
    if test -f "$skill_misdirected" &&
      test ! -L "$skill_misdirected" &&
      test "$skill_tmp" -ef "$skill_misdirected"; then
      rm "$skill_misdirected"
    fi
    false
  fi
)"""
STANDALONE_UNINSTALL_BLOCK = f"""(
  set -eu
  skill_dir="$HOME/.agents/skills/if"
  skill_target="$skill_dir/SKILL.md"
  skill_expected_sha256="{STANDALONE_SHA256}"
  test ! -L "$skill_dir"
  test -d "$skill_dir"
  test -f "$skill_target"
  test ! -L "$skill_target"
  if command -v sha256sum >/dev/null 2>&1; then
    skill_actual_sha256="$(sha256sum "$skill_target")"
  else
    skill_actual_sha256="$(shasum -a 256 "$skill_target")"
  fi
  skill_actual_sha256="${{skill_actual_sha256%% *}}"
  test "$skill_actual_sha256" = "$skill_expected_sha256"
  rm "$skill_target"
  rmdir "$skill_dir" 2>/dev/null || true
)"""
UNSAFE_STANDALONE_REMOVE = 'rm "$HOME/.agents/skills/if/SKILL.md"'
SOCIAL_CARD_RENDER = (
    "magick -background none assets/social/laconian-alpha.svg -strip "
    "assets/social/laconian-alpha.png"
)
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


def _standalone_test_environment(tmp_path: Path, *, curl_mode: str) -> tuple[Path, dict[str, str]]:
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        """#!/bin/sh
set -eu
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    output="$2"
    shift 2
  else
    shift
  fi
done
test -n "$output"
if [ "$STUB_CURL_MODE" = "race-directory" ]; then
  mkdir "$HOME/.agents/skills/if/SKILL.md"
fi
cp "$STUB_SKILL_SOURCE" "$output"
""",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', os.defpath)}",
            "STUB_CURL_MODE": curl_mode,
            "STUB_SKILL_SOURCE": str(ROOT / "skills/if/SKILL.md"),
        }
    )
    return home, env


def _run_standalone_block(block: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", block],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


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
    assert text.count(STANDALONE_INSTALL_BLOCK) == 1
    assert text.count(STANDALONE_UNINSTALL_BLOCK) == 1
    assert UNSAFE_STANDALONE_REMOVE not in text
    assert '-o "$HOME/.agents/skills/if/SKILL.md"' not in text


def test_standalone_lifecycle_is_collision_safe_and_hash_pinned() -> None:
    assert hashlib.sha256((ROOT / "skills/if/SKILL.md").read_bytes()).hexdigest() == (
        STANDALONE_SHA256
    )

    install = STANDALONE_INSTALL_BLOCK
    directory_guards = [
        match.start()
        for match in re.finditer(r'^  test ! -L "\$skill_dir"$', install, re.MULTILINE)
    ]
    assert len(directory_guards) == 2
    mkdir_position = install.index('mkdir -p "$skill_dir"')
    assert directory_guards[0] < mkdir_position < directory_guards[1]
    for guard in ('test ! -e "$skill_target"', 'test ! -L "$skill_target"'):
        assert guard in install
    assert 'mktemp "$skill_dir/.SKILL.md.XXXXXX"' in install
    assert "trap 'rm -f \"$skill_tmp\"' EXIT" in install
    assert "EXIT HUP INT TERM" not in install
    assert f'curl -fsSL "{STANDALONE_URL}" -o "$skill_tmp"' in install
    assert '-o "$skill_target"' not in install
    link_and_verify = (
        'ln "$skill_tmp" "$skill_target"\n  if ! test "$skill_tmp" -ef "$skill_target"; then'
    )
    assert link_and_verify in install
    assert 'test -f "$skill_misdirected"' in install
    assert 'test ! -L "$skill_misdirected"' in install
    assert 'test "$skill_tmp" -ef "$skill_misdirected"' in install
    assert 'mv "$skill_tmp" "$skill_target"' not in install

    uninstall = STANDALONE_UNINSTALL_BLOCK
    directory_guard = 'test ! -L "$skill_dir"'
    directory_check = 'test -d "$skill_dir"'
    assert uninstall.index(directory_guard) < uninstall.index(directory_check)
    assert uninstall.index(directory_check) < uninstall.index('test -f "$skill_target"')
    assert 'test -f "$skill_target"' in uninstall
    assert 'test ! -L "$skill_target"' in uninstall
    hash_guard = 'test "$skill_actual_sha256" = "$skill_expected_sha256"'
    assert uninstall.index(hash_guard) < uninstall.index('rm "$skill_target"')
    assert 'rmdir "$skill_dir" 2>/dev/null || true' in uninstall
    for block in (install, uninstall):
        assert "command -v sha256sum" in block
        assert "shasum -a 256" in block

    plan = _read("docs/superpowers/plans/2026-08-29-alpha-launch-readiness.md")
    assert STANDALONE_INSTALL_BLOCK in plan
    assert STANDALONE_UNINSTALL_BLOCK in plan
    assert UNSAFE_STANDALONE_REMOVE not in plan
    assert '-o "$HOME/.agents/skills/if/SKILL.md"' not in plan
    assert "/Users/if/" not in plan
    assert "${CODEX_HOME:-$HOME/.codex}/skills/.system/" in plan


def test_standalone_install_refuses_an_existing_target(tmp_path: Path) -> None:
    home, env = _standalone_test_environment(tmp_path, curl_mode="copy")
    skill_dir = home / ".agents/skills/if"
    skill_dir.mkdir(parents=True)
    target = skill_dir / "SKILL.md"
    target.write_text("user content\n", encoding="utf-8")

    result = _run_standalone_block(STANDALONE_INSTALL_BLOCK, env)

    assert result.returncode != 0
    assert target.read_text(encoding="utf-8") == "user content\n"


def test_standalone_uninstall_refuses_a_symlinked_skill_directory(tmp_path: Path) -> None:
    home, env = _standalone_test_environment(tmp_path, curl_mode="copy")
    external = tmp_path / "external"
    external.mkdir()
    external_target = external / "SKILL.md"
    canonical = (ROOT / "skills/if/SKILL.md").read_bytes()
    external_target.write_bytes(canonical)
    skill_parent = home / ".agents/skills"
    skill_parent.mkdir(parents=True)
    (skill_parent / "if").symlink_to(external, target_is_directory=True)

    result = _run_standalone_block(STANDALONE_UNINSTALL_BLOCK, env)

    assert result.returncode != 0
    assert external_target.read_bytes() == canonical


def test_standalone_install_cleans_a_directory_race_hardlink(tmp_path: Path) -> None:
    home, env = _standalone_test_environment(tmp_path, curl_mode="race-directory")

    result = _run_standalone_block(STANDALONE_INSTALL_BLOCK, env)

    target = home / ".agents/skills/if/SKILL.md"
    assert result.returncode != 0
    assert target.is_dir()
    assert list(target.iterdir()) == []


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
        "material_warning_severity",
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


def test_semantic_rubric_has_only_the_frozen_public_fields() -> None:
    assert set(SemanticRubric.model_fields) == {
        "required_facts",
        "material_warning",
        "material_warning_severity",
    }


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


def test_social_card_has_exact_copy_and_dimensions() -> None:
    svg = _read("assets/social/laconian-alpha.svg")
    root = ET.fromstring(svg)
    visible_text = [
        "".join(node.itertext()) for node in root.findall("{http://www.w3.org/2000/svg}text")
    ]
    assert visible_text == [
        "if",
        "The shortest",
        "complete answer.",
        "Experimental alpha",
    ]
    assert " ".join(visible_text[1:3]) == "The shortest complete answer."
    assert f"Canonical PNG render: {SOCIAL_CARD_RENDER}" in svg
    png = (ROOT / "assets/social/laconian-alpha.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (1200, 630)
    assert hashlib.sha256(png).hexdigest() == (
        "53edc82ed51ce4dfd16280de39b0c6285dbbd0b7e1c7dfa94de817a0918b47f9"
    )


def test_benchmark_sdk_contract_has_one_public_owner() -> None:
    import ast
    import inspect

    import laconian_eval.benchmark as benchmark
    import laconian_eval.providers as providers
    from laconian_eval.benchmark import attachments
    from laconian_eval.providers import openai as provider_openai

    names = (
        "BENCHMARK_OPENAI_REQUEST_FIELDS_V1",
        "BENCHMARK_OPENAI_RESPONSE_CONTENT_PATHS_V1",
        "BENCHMARK_OPENAI_RESPONSE_PATHS_V1",
        "BENCHMARK_OPENAI_RETURNED_MODEL_PATH_V1",
        "BENCHMARK_OPENAI_SERIALIZER_PROJECTION_CANONICAL_JSON_V1",
        "BENCHMARK_OPENAI_SERIALIZER_PROJECTION_SHA256_V1",
        "BENCHMARK_OPENAI_LOCK_REGISTRY_V1",
        "BENCHMARK_OPENAI_LOCK_DEPENDENCIES_V1",
        "BENCHMARK_OPENAI_LOCK_SDIST_V1",
        "BENCHMARK_OPENAI_LOCK_WHEELS_V1",
        "BenchmarkSDKContractErrorCode",
        "BenchmarkSDKContractError",
        "VerifiedBenchmarkSDKContractV1",
        "require_benchmark_sdk_contract",
    )
    for name in names:
        assert getattr(providers, name) is getattr(provider_openai, name)
        assert providers.__all__.count(name) == 1
    for name in ("BenchmarkSDKContractError", "VerifiedBenchmarkSDKContractV1"):
        assert getattr(providers, name).__module__ == "laconian_eval.providers.openai"
    assert providers.require_benchmark_sdk_contract.__module__ == "laconian_eval.providers.openai"
    assert str(inspect.signature(providers.require_benchmark_sdk_contract)) == (
        "(*, c0_uv_lock_bytes: 'bytes', expected_c0_uv_lock_sha256: 'Sha256') -> 'None'"
    )
    assert str(inspect.signature(provider_openai._build_verified_benchmark_sdk_contract)) == (
        "(*, c0_uv_lock_bytes: 'bytes', expected_c0_uv_lock_sha256: 'Sha256') "
        "-> 'VerifiedBenchmarkSDKContractV1'"
    )

    assert benchmark.CanonicalJSONV1Error is attachments.CanonicalJSONV1Error
    assert benchmark.canonical_json_v1 is attachments.canonical_json_v1
    assert benchmark.parse_canonical_json_v1 is attachments.parse_canonical_json_v1
    assert provider_openai._canonical_json_v1 is attachments.canonical_json_v1
    canonical_names = {
        "CanonicalJSONV1Error",
        "canonical_json_v1",
        "parse_canonical_json_v1",
    }
    assert canonical_names.isdisjoint(providers.__all__)
    tree = ast.parse(inspect.getsource(provider_openai))
    locally_defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert canonical_names.isdisjoint(locally_defined)
    assert not {name for name in locally_defined if "canonical_json_v1" in name.lower()}
    source = inspect.getsource(provider_openai)
    assert "ProtocolSubjectKindV1" not in source
    assert "PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1" not in source


def test_benchmark_policy_status_exports_have_exact_public_owners() -> None:
    import laconian_eval.providers as providers
    from laconian_eval.capsule import attempts, schema
    from laconian_eval.providers import base

    exported = (
        "ServiceTier",
        "AppliedCacheControlStatus",
        "CacheReadStatus",
        "CacheWriteStatus",
        "ServiceTierStatus",
    )
    owners = {
        "ServiceTier": schema.ServiceTier,
        "AppliedCacheControlStatus": base.AppliedCacheControlStatus,
        "CacheReadStatus": base.CacheReadStatus,
        "CacheWriteStatus": base.CacheWriteStatus,
        "ServiceTierStatus": base.ServiceTierStatus,
    }
    for name in exported:
        assert getattr(providers, name) is owners[name]
        assert providers.__all__.count(name) == 1

    forbidden = {
        "OutputString",
        "PublicBenchmarkProvider",
        "PublicBenchmarkProviderOutcomeV1",
        "PublicBenchmarkProviderErrorEvidenceV1",
        "PublicBenchmarkResponseEvidenceV1",
        "ReasoningTokenAccounting",
    }
    assert forbidden.isdisjoint(providers.__all__)
    assert attempts.OutputString is not None
    assert attempts.PublicBenchmarkProvider is not None
    assert attempts.PublicBenchmarkProviderOutcomeV1 is not None


def test_benchmark_response_and_error_evidence_fields_are_exact() -> None:
    from laconian_eval.capsule.attempts import (
        PublicBenchmarkProviderErrorEvidenceV1,
        PublicBenchmarkResponseEvidenceV1,
    )

    shared_evidence = (
        "usage",
        "requested_model_id",
        "returned_model_id",
        "returned_model_source_sha256",
        "requested_service_tier",
        "returned_service_tier",
        "service_tier_status",
        "service_tier_source_sha256",
        "applied_prompt_cache_mode",
        "applied_prompt_cache_ttl",
        "applied_cache_control_status",
        "applied_cache_control_source_sha256",
        "cache_read_source_sha256",
        "cache_write_source_sha256",
        "usage_source_sha256",
        "reasoning_tokens_source_sha256",
    )
    response_fields = (
        "schema_version",
        "response_id",
        "raw_response_sha256",
        "output_text",
        "raw_response_source",
        *shared_evidence,
    )
    error_fields = (
        "schema_version",
        "delivery_certainty",
        "provider_request_id",
        "response_id",
        "raw_response_sha256",
        "raw_response_source",
        *shared_evidence,
        "structured_status",
        "error_source_sha256",
    )
    assert tuple(PublicBenchmarkResponseEvidenceV1.model_fields) == response_fields
    assert tuple(PublicBenchmarkProviderErrorEvidenceV1.model_fields) == error_fields


def test_benchmark_token_usage_fields_append_without_changing_legacy_results() -> None:
    from dataclasses import fields

    from laconian_eval.providers.base import GenerationResult, ProviderError, TokenUsage

    assert tuple(field.name for field in fields(TokenUsage)) == (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "reasoning_token_accounting",
    )
    assert tuple(field.name for field in fields(GenerationResult)) == (
        "output_text",
        "usage",
        "request_id",
        "finish_reason",
        "response_model",
        "delivery_certainty",
    )
    assert ProviderError.__slots__ == (
        "_delivery_certainty",
        "_finish_reason",
        "_kind",
        "_message",
        "_request_id",
        "_response_model",
        "_retryable",
        "_usage",
    )


def test_replay_legacy_callable_annotations_remain_eager_owner_objects() -> None:
    from collections.abc import Mapping

    import laconian_eval.providers.replay as replay
    from laconian_eval.providers.base import (
        GenerationRequest,
        GenerationResult,
        TokenUsage,
    )

    assert replay._entry_error.__annotations__ == {
        "source": Path | str,
        "key": str,
        "message": str,
        "return": ValueError,
    }
    assert replay._optional_string.__annotations__ == {
        "path": Path | str,
        "key": str,
        "entry": Mapping[object, object],
        "field": str,
        "return": str | None,
    }
    assert replay._parse_usage.__annotations__ == {
        "path": Path | str,
        "key": str,
        "entry": Mapping[object, object],
        "return": TokenUsage | None,
    }
    assert replay._parse_entry.__annotations__ == {
        "path": Path | str,
        "key": str,
        "raw_entry": object,
        "return": GenerationResult,
    }
    assert replay.ReplayProvider.__init__.__annotations__ == {
        "entries": Mapping[str, GenerationResult],
        "source": Path | None,
        "return": None,
    }
    assert replay.ReplayProvider._from_mapping.__annotations__ == {
        "raw": object,
        "error_source": Path | str,
        "source": Path | None,
        "return": "ReplayProvider",
    }
    assert replay.ReplayProvider.from_path.__annotations__ == {
        "path": Path,
        "return": "ReplayProvider",
    }
    assert replay.ReplayProvider.from_bytes.__annotations__ == {
        "data": bytes,
        "return": "ReplayProvider",
    }
    assert replay.ReplayProvider.generate.__annotations__ == {
        "request": GenerationRequest,
        "return": GenerationResult,
    }


def test_slice1_final_capsule_public_names_are_stable() -> None:
    from laconian_eval.capsule.finalize import FinalizeResultV1, finalize_capsule
    from laconian_eval.capsule.scorable import ScoredAttemptV2
    from laconian_eval.capsule.seal_models import SealV1, capsule_sha256
    from laconian_eval.capsule.sharding import ShardPlanV1
    from laconian_eval.capsule.sidecars import (
        VerifiedScoredCapsuleV2,
        load_verified_scored_capsule,
    )

    assert callable(capsule_sha256)
    assert callable(finalize_capsule)
    assert callable(load_verified_scored_capsule)
    assert all(
        isinstance(value, type)
        for value in (
            SealV1,
            FinalizeResultV1,
            ShardPlanV1,
            ScoredAttemptV2,
            VerifiedScoredCapsuleV2,
        )
    )
    assert {
        value.__name__: value.__module__
        for value in (
            SealV1,
            capsule_sha256,
            FinalizeResultV1,
            finalize_capsule,
            ShardPlanV1,
            ScoredAttemptV2,
            VerifiedScoredCapsuleV2,
            load_verified_scored_capsule,
        )
    } == {
        "SealV1": "laconian_eval.capsule.seal_models",
        "capsule_sha256": "laconian_eval.capsule.seal_models",
        "FinalizeResultV1": "laconian_eval.capsule.finalize",
        "finalize_capsule": "laconian_eval.capsule.finalize",
        "ShardPlanV1": "laconian_eval.capsule.sharding",
        "ScoredAttemptV2": "laconian_eval.capsule.scorable",
        "VerifiedScoredCapsuleV2": "laconian_eval.capsule.sidecars",
        "load_verified_scored_capsule": "laconian_eval.capsule.sidecars",
    }
