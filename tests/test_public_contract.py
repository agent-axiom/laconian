import hashlib
import os
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from laconian_eval.models import ActivationCaseFile, ResponseCaseFile, SemanticRubric
from laconian_eval.yaml_io import safe_load_unique

ROOT = Path(__file__).resolve().parents[1]

# Literal cumulative contract from approved Evaluation Task 15, Step 6.
EXPECTED_BENCHMARK_SLICE2_EXPORTS = (
    "CanonicalJSONV1Error",
    "canonical_json_v1",
    "parse_canonical_json_v1",
    "RationalV1",
    "attachment_digest",
    "write_attachment_json",
    "derive_seed128",
    "HardScoreRequestSetV1",
    "build_hard_score_request_set",
    "verify_hard_score_request_set",
    "JUDGE_REQUESTED_SERVICE_TIER",
    "JUDGE_SERVICE_TIER_WIRE_FIELD",
    "BlindJudgeRequestV1",
    "JudgeProviderRequestV1",
    "JudgeRequestAttachmentV1",
    "JudgeAttemptUsageV1",
    "JudgeAttemptEvidenceV1",
    "JudgeAttemptBoundaryV1",
    "JudgeAttemptRootMemberV1",
    "JudgeAttemptRootIndexV1",
    "VerifiedJudgeAttemptRootV1",
    "write_judge_attempt_root",
    "load_verified_judge_attempt_root",
    "JudgeAttachmentV1",
    "build_judge_request_attachment",
    "verify_judge_request_attachment",
    "build_judge_attachment",
    "verify_judge_attachment",
    "AggregatedModelV1",
    "aggregate_verified_evidence",
    "BootstrapVectorsV1",
    "BootstrapIntervalV1",
    "make_cluster_vectors",
    "BootstrapArtifactV1",
    "build_bootstrap_artifact",
    "LayerKindV1",
    "GenerationLayerRootMemberV1",
    "AttachmentLayerRootMemberV1",
    "LayerRootMemberV1",
    "LayerRootIndexV1",
    "write_layer_root_index",
    "load_layer_root_index",
    "SignatureVerificationModeV1",
    "GitHubVerifiedCommitEvidenceV1",
    "SSHVerifiedCommitEvidenceV1",
    "OpenPGPVerifiedCommitEvidenceV1",
    "SignatureEvidenceV1",
    "ProtocolSignatureEvidenceSourceV1",
    "AuditReviewerSigningKeyV1",
    "verify_commit_signature_evidence_source",
    "ProtocolReviewRoleV1",
    "ProtocolSubjectKindV1",
    "PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1",
    "ReviewerAccountBindingV1",
    "AuditReviewerRegistryV1",
    "ProtocolReviewerBindingV1",
    "ProtocolReviewerRegistryV1",
    "TagOperatorProjectionV1",
    "TagOperatorRegistryV1",
    "TagRulesetPolicyV1",
    "GITHUB_COMMIT_SIGNER_QUERY_V1",
    "GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1",
    "InputTagMessageV1",
    "ProtocolAttestationTagMessageV1",
    "ProtocolBundleBuilderGitIdentityV1",
    "TagRulesetObservationReceiptV1",
    "TagCreationRuleSuiteReceiptV1",
    "ArchivedApiReceiptBindingV1",
    "WorkflowInventoryV1",
    "BENCHMARK_WORKFLOW_PATHS_V1",
    "build_workflow_inventory",
    "GitObjectSHA256V1",
    "ParsedProtocolGitObjectV1",
    "VerifiedProtocolReviewPrefixV1",
    "VerifiedProtocolReviewDagV1",
    "ArchivedApiBlobV1",
    "parse_protocol_git_object",
    "verify_protocol_review_prefix",
    "verify_protocol_review_dag",
    "build_protocol_attestation_bundle",
    "build_protocol_attestation_tag_binding",
    "build_protocol_review_object_archive",
    "load_verified_protocol_review_object_archive",
    "ProtocolReviewSubjectV1",
    "ProtocolReviewStatementV1",
    "VerifiedProtocolAttestationV1",
    "GitHubCommitVerificationProjectionV1",
    "GitHubSignatureProjectionV1",
    "GitHubSignatureObservationReceiptV1",
    "LocalSignatureVerificationReceiptV1",
    "ProtocolReviewSigningKeyV1",
    "ProtocolReviewIdentityRegistryBundleV1",
    "ProtocolAttestationBundleV1",
    "ProtocolAttestationTagBindingV1",
    "ProtocolReviewObjectArchiveV1",
    "canonical_reviewer_registry_bytes",
    "compute_audit_reviewer_registry_sha256",
    "canonical_protocol_reviewer_registry_bytes",
    "compute_protocol_reviewer_registry_sha256",
    "protocol_review_digest",
    "compute_protocol_attestations_root",
    "BenchmarkProtocolBindingsV1",
    "protocol_bindings_from_context",
    "GenerationContextExpectationV1",
    "VerifiedGenerationContextExpectationV1",
    "GenerationContextIndexV1",
    "VerifiedGenerationContextIndexV1",
    "write_generation_context_index",
    "load_verified_generation_context_index",
    "ProviderEvidenceIndexV1",
    "compute_requested_returned_model_source_sha256",
    "write_provider_evidence_index",
    "load_provider_evidence_index",
    "BenchmarkProviderEvidenceProjectionV1",
    "VerifiedBenchmarkProviderEvidenceV1",
    "load_verified_benchmark_provider_evidence",
    "AuditPopulationAttachmentV1",
    "VerifiedAuditPopulationV1",
    "VerifiedAuditSampleRootV1",
    "build_audit_population",
    "write_audit_population",
    "load_verified_audit_population",
    "AuditSampleManifestV1",
    "BlindAuditPacketV1",
    "select_audit_sample",
    "verify_audit_sample",
    "write_audit_sample_root",
    "load_verified_audit_sample_root",
    "ReviewerIdentityV1",
    "PullRequestProofV1",
    "ReviewerCommitmentV1",
    "ReviewerRevealV1",
    "GitHubAuditApiObservationReceiptV1",
    "ExactGitHubPullRequestRecordV1",
    "AuditPullRequestEvidenceSourceV1",
    "AuditGitObjectArchiveV1",
    "ExactGitHubReviewSourceV1",
    "ReviewerChainV1",
    "verify_reviewer_chain",
    "AuditAdjudicationCoreV1",
    "ExactGitHubReviewRecordV1",
    "ExactGitHubReviewSignoffV1",
    "AuditAdjudicationV1",
    "verify_audit_chain",
    "WeightedConfusionV1",
    "WeightedProportionV1",
    "ModelAuditMetricsV1",
    "ModelAuditGateV1",
    "compute_model_audit_metrics",
    "evaluate_model_audit_gate",
    "SensitivityResultV1",
    "SensitivityCertificateV1",
    "verify_sensitivity_certificate",
    "CampaignAnalysisV1",
    "AuditEvidenceAttachmentV1",
    "AnalysisEvidenceAttachmentV1",
    "VerifiedAuditEvidenceV1",
    "VerifiedAnalysisEvidenceV1",
    "write_audit_evidence_root",
    "load_verified_audit_evidence",
    "load_verified_analysis_evidence",
    "write_analysis_evidence_root",
)
EXPECTED_BENCHMARK_COMMANDS = (
    "hard-score",
    "prepare-judge",
    "seal-judge",
    "sample-audit",
    "seal-audit",
    "analyze",
    "verify",
)
EXPECTED_LIVE_METHODS = (
    "laconian_eval.campaign.runtime.Runtime.hard_score",
    "laconian_eval.campaign.runtime.Runtime.prepare_judge",
    "laconian_eval.campaign.runtime.Runtime.seal_judge",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.sample_audit",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.seal_audit",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.analyze",
    "laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.verify",
)
EXPECTED_PRIVATE_CONSTRUCTORS = (
    "_reconstruct_verified_runtime",
    "_reconstruct_verified_publication",
)


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
    "docs/releases/v0.1.0-alpha.1.md",
    "docs/social/alpha-launch.md",
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


def _relative_link(source: str, target: str) -> str:
    source_dir = (ROOT / source).parent
    return Path(os.path.relpath(ROOT / target, start=source_dir)).as_posix()


def _canonical_repository_url(target: str) -> str:
    return f"{GITHUB_BLOB_ROOT}{target}"


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


def test_using_the_skill_has_pinned_install_paths() -> None:
    text = _read("docs/using-the-skill.md")
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


@pytest.mark.parametrize("filename", LOCALIZED_STATUS_MARKERS)
def test_localized_readmes_route_installation_without_duplicating_lifecycle(
    filename: str,
) -> None:
    text = _read(filename)
    usage_href = _relative_link(filename, "docs/using-the-skill.md")
    assert f"]({usage_href})" in text
    for duplicated_detail in (
        PLUGIN_ADD,
        STANDALONE_URL,
        STANDALONE_INSTALL_BLOCK,
        STANDALONE_UNINSTALL_BLOCK,
    ):
        assert duplicated_detail not in text


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
    assert ".codex-plugin/, .agents/, and tools/: Apache-2.0." in notice.splitlines()
    assert "assets/social/ and docs/social/: CC-BY-4.0." in notice.splitlines()


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
        "releases/v0.1.0-alpha.1.md",
        "social/alpha-launch.md",
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
        "The skill artifact is one Markdown-only file.",
        "no scripts, dependencies, permissions, references, assets, network calls",
    ):
        assert phrase in normalized
    for command in (
        PLUGIN_ADD,
        PLUGIN_INSTALL,
        PLUGIN_LIST,
        PLUGIN_REMOVE,
        MARKETPLACE_REMOVE,
    ):
        assert command in text
    assert "$laconian:if" in text
    assert "$if" in text
    assert STANDALONE_URL in text
    assert text.count(STANDALONE_INSTALL_BLOCK) == 1
    assert text.count(STANDALONE_UNINSTALL_BLOCK) == 1


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


def test_methodology_freezes_public_cluster_bootstrap_and_audit_contract() -> None:
    methodology = _read("benchmarks/methodology.md")
    required = (
        "visible_output_tokens = output_tokens - reasoning_tokens",
        "cache_write_tokens",
        "retained_worst_case",
        "sum(H) / 120",
        "sum(S) / 120",
        '"service_tier": "default"',
        "service_tier_status",
        "not_applicable_definitely_not_sent",
        "not_applicable_definitely_rejected",
        "missing",
        "mismatch",
        "reported_default",
        "statistical_protocol_sha256",
        "audit_protocol_sha256",
        "10,000",
        "Generator(PCG64)",
        "type-7",
        "9,990",
        "scenario-superpopulation-conditional-on-fixed-campaign",
        "nominal 95% approximate",
        "144",
        "Hamilton",
        "commit-reveal",
        "n_eff = sum(w)^2 / sum(w^2)",
        "z = 1.959963984540054",
        "design-weighted-wilson-score-v1",
        "K = min(M, max(D, ceil(U * M)))",
        "A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})",
        "1,000,000",
        "4,096",
        "among jointly successful matched responses",
        "offline and non-evidentiary",
        "in-memory verified generation-context expectation",
        "Runtime.hard_score",
        "Runtime.prepare_judge",
        "Runtime.seal_judge",
        "Publication.campaign.evaluation_stage.sample_audit",
        "Publication.campaign.evaluation_stage.seal_audit",
        "Publication.campaign.evaluation_stage.analyze",
        "Publication.campaign.evaluation_stage.verify",
        "_reconstruct_verified_runtime",
        "_reconstruct_verified_publication",
    )
    for phrase in required:
        assert phrase in methodology

    eval_readme = _read("evals/README.md")
    for phrase in (
        "LayerRootIndexV1",
        "GenerationContextExpectationV1",
        "GenerationContextIndexV1",
        "workflow_root",
        "statistical_protocol_sha256",
        "audit_protocol_sha256",
        "JudgeAttemptEvidenceV1",
        "JudgeAttemptRootIndexV1",
        "ProviderEvidenceIndexV1",
        "write_audit_sample_root",
        "write_audit_evidence_root",
        "BootstrapArtifactV1",
        "build_bootstrap_artifact",
        "ProtocolReviewerRegistryV1",
        "reviewers.yaml",
        "benchmark-reviewer-registry-v2",
        "protocol-reviewers.yaml",
        "HardScoreRequestSetV1",
        "JudgeAttachmentV1",
        "audit-evidence.json",
        "git-object-archive.json",
        "pull-request-sources",
        "adjudication-core.json",
        "github-review-sources",
        "github-review-records",
        "analysis-evidence.json",
        "bootstrap.json",
        "checksums.json",
    ):
        assert phrase in eval_readme


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


def test_structured_output_provider_contract_has_one_foundation_owner() -> None:
    import inspect

    import laconian_eval.providers as providers
    from laconian_eval.providers import base

    assert providers.StructuredOutputProviderRequestV1 is base.StructuredOutputProviderRequestV1
    assert providers.StructuredOutputProvider is base.StructuredOutputProvider
    assert providers.__all__.count("StructuredOutputProviderRequestV1") == 1
    assert providers.__all__.count("StructuredOutputProvider") == 1
    signature = inspect.signature(base.StructuredOutputProvider.generate_structured_output)
    assert signature.parameters["request"].annotation is base.StructuredOutputProviderRequestV1
    assert signature.return_annotation == "PublicBenchmarkProviderOutcomeV1"


def test_public_benchmark_slice2_exports_and_exact_seven_commands_are_owned() -> None:
    import argparse
    import ast
    import importlib
    import inspect
    import tomllib
    from dataclasses import is_dataclass
    from types import MappingProxyType

    import laconian_eval.benchmark as benchmark
    import laconian_eval.providers as providers

    assert benchmark.__all__ == EXPECTED_BENCHMARK_SLICE2_EXPORTS
    assert len(benchmark.__all__) == len(set(benchmark.__all__)) == 162
    assert {"cli", "main", "ServiceTierStatus", "OfflineValidationReportV1"}.isdisjoint(
        benchmark.__all__
    )
    assert set(EXPECTED_PRIVATE_CONSTRUCTORS).isdisjoint(benchmark.__all__)
    assert all(not hasattr(benchmark, name) for name in EXPECTED_PRIVATE_CONSTRUCTORS)
    assert tuple(name.rsplit(".", 1)[-1].replace("_", "-") for name in EXPECTED_LIVE_METHODS) == (
        EXPECTED_BENCHMARK_COMMANDS
    )

    cold_import = subprocess.run(
        (
            sys.executable,
            "-c",
            "import sys; import laconian_eval.benchmark; "
            "assert 'laconian_eval.cli' not in sys.modules; "
            "assert not any(name.startswith('laconian_eval.campaign') for name in sys.modules)",
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cold_import.returncode == 0, cold_import.stderr

    # Literal sole-owner inventories; aliases/constants are checked by identity too.
    owner_names = {
        "attachments": (
            "CanonicalJSONV1Error",
            "canonical_json_v1",
            "parse_canonical_json_v1",
            "RationalV1",
            "attachment_digest",
            "write_attachment_json",
        ),
        "seeds": ("derive_seed128",),
        "hard_score": (
            "HardScoreRequestSetV1",
            "build_hard_score_request_set",
            "verify_hard_score_request_set",
        ),
        "judge": (
            "JUDGE_REQUESTED_SERVICE_TIER",
            "JUDGE_SERVICE_TIER_WIRE_FIELD",
            "BlindJudgeRequestV1",
            "JudgeProviderRequestV1",
            "JudgeRequestAttachmentV1",
            "JudgeAttemptUsageV1",
            "JudgeAttemptEvidenceV1",
            "JudgeAttemptBoundaryV1",
            "JudgeAttemptRootMemberV1",
            "JudgeAttemptRootIndexV1",
            "VerifiedJudgeAttemptRootV1",
            "write_judge_attempt_root",
            "load_verified_judge_attempt_root",
            "JudgeAttachmentV1",
            "build_judge_request_attachment",
            "verify_judge_request_attachment",
            "build_judge_attachment",
            "verify_judge_attachment",
        ),
        "aggregation": (
            "AggregatedModelV1",
            "aggregate_verified_evidence",
        ),
        "bootstrap": (
            "BootstrapVectorsV1",
            "BootstrapIntervalV1",
            "make_cluster_vectors",
        ),
        "reporting": (
            "BootstrapArtifactV1",
            "build_bootstrap_artifact",
            "CampaignAnalysisV1",
            "AuditEvidenceAttachmentV1",
            "AnalysisEvidenceAttachmentV1",
            "VerifiedAuditEvidenceV1",
            "VerifiedAnalysisEvidenceV1",
            "write_audit_evidence_root",
            "load_verified_audit_evidence",
            "load_verified_analysis_evidence",
            "write_analysis_evidence_root",
        ),
        "context": (
            "LayerKindV1",
            "GenerationLayerRootMemberV1",
            "AttachmentLayerRootMemberV1",
            "LayerRootMemberV1",
            "LayerRootIndexV1",
            "write_layer_root_index",
            "load_layer_root_index",
            "BenchmarkProtocolBindingsV1",
            "protocol_bindings_from_context",
            "GenerationContextExpectationV1",
            "VerifiedGenerationContextExpectationV1",
            "GenerationContextIndexV1",
            "VerifiedGenerationContextIndexV1",
            "write_generation_context_index",
            "load_verified_generation_context_index",
        ),
        "protocol_review": (
            "SignatureVerificationModeV1",
            "GitHubVerifiedCommitEvidenceV1",
            "SSHVerifiedCommitEvidenceV1",
            "OpenPGPVerifiedCommitEvidenceV1",
            "SignatureEvidenceV1",
            "ProtocolSignatureEvidenceSourceV1",
            "AuditReviewerSigningKeyV1",
            "verify_commit_signature_evidence_source",
            "ProtocolReviewRoleV1",
            "ProtocolSubjectKindV1",
            "PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1",
            "ReviewerAccountBindingV1",
            "AuditReviewerRegistryV1",
            "ProtocolReviewerBindingV1",
            "ProtocolReviewerRegistryV1",
            "TagOperatorProjectionV1",
            "TagOperatorRegistryV1",
            "TagRulesetPolicyV1",
            "GITHUB_COMMIT_SIGNER_QUERY_V1",
            "GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1",
            "InputTagMessageV1",
            "ProtocolAttestationTagMessageV1",
            "ProtocolBundleBuilderGitIdentityV1",
            "TagRulesetObservationReceiptV1",
            "TagCreationRuleSuiteReceiptV1",
            "ArchivedApiReceiptBindingV1",
            "WorkflowInventoryV1",
            "BENCHMARK_WORKFLOW_PATHS_V1",
            "build_workflow_inventory",
            "GitObjectSHA256V1",
            "ParsedProtocolGitObjectV1",
            "VerifiedProtocolReviewPrefixV1",
            "VerifiedProtocolReviewDagV1",
            "ArchivedApiBlobV1",
            "parse_protocol_git_object",
            "verify_protocol_review_prefix",
            "verify_protocol_review_dag",
            "build_protocol_attestation_bundle",
            "build_protocol_attestation_tag_binding",
            "build_protocol_review_object_archive",
            "load_verified_protocol_review_object_archive",
            "ProtocolReviewSubjectV1",
            "ProtocolReviewStatementV1",
            "VerifiedProtocolAttestationV1",
            "GitHubCommitVerificationProjectionV1",
            "GitHubSignatureProjectionV1",
            "GitHubSignatureObservationReceiptV1",
            "LocalSignatureVerificationReceiptV1",
            "ProtocolReviewSigningKeyV1",
            "ProtocolReviewIdentityRegistryBundleV1",
            "ProtocolAttestationBundleV1",
            "ProtocolAttestationTagBindingV1",
            "ProtocolReviewObjectArchiveV1",
            "canonical_reviewer_registry_bytes",
            "compute_audit_reviewer_registry_sha256",
            "canonical_protocol_reviewer_registry_bytes",
            "compute_protocol_reviewer_registry_sha256",
            "protocol_review_digest",
            "compute_protocol_attestations_root",
        ),
        "provider_evidence": (
            "ProviderEvidenceIndexV1",
            "compute_requested_returned_model_source_sha256",
            "write_provider_evidence_index",
            "load_provider_evidence_index",
            "BenchmarkProviderEvidenceProjectionV1",
            "VerifiedBenchmarkProviderEvidenceV1",
            "load_verified_benchmark_provider_evidence",
            "AuditPopulationAttachmentV1",
            "VerifiedAuditPopulationV1",
            "build_audit_population",
            "write_audit_population",
            "load_verified_audit_population",
        ),
        "audit_sampling": (
            "VerifiedAuditSampleRootV1",
            "AuditSampleManifestV1",
            "BlindAuditPacketV1",
            "select_audit_sample",
            "verify_audit_sample",
            "write_audit_sample_root",
            "load_verified_audit_sample_root",
        ),
        "audit_commit_reveal": (
            "ReviewerIdentityV1",
            "PullRequestProofV1",
            "ReviewerCommitmentV1",
            "ReviewerRevealV1",
            "GitHubAuditApiObservationReceiptV1",
            "ExactGitHubPullRequestRecordV1",
            "AuditPullRequestEvidenceSourceV1",
            "AuditGitObjectArchiveV1",
            "ExactGitHubReviewSourceV1",
            "ReviewerChainV1",
            "verify_reviewer_chain",
            "AuditAdjudicationCoreV1",
            "ExactGitHubReviewRecordV1",
            "ExactGitHubReviewSignoffV1",
            "AuditAdjudicationV1",
            "verify_audit_chain",
        ),
        "audit_metrics": (
            "WeightedConfusionV1",
            "WeightedProportionV1",
            "ModelAuditMetricsV1",
            "ModelAuditGateV1",
            "compute_model_audit_metrics",
            "evaluate_model_audit_gate",
        ),
        "sensitivity": (
            "SensitivityResultV1",
            "SensitivityCertificateV1",
            "verify_sensitivity_certificate",
        ),
    }
    assert set(benchmark.__all__) == {name for names in owner_names.values() for name in names}
    for suffix, names in owner_names.items():
        owner = importlib.import_module("laconian_eval.benchmark." + suffix)
        for name in names:
            value = getattr(benchmark, name)
            assert value is getattr(owner, name), (suffix, name)
            if inspect.isclass(value) or inspect.isfunction(value):
                assert value.__module__ == owner.__name__, name

    protocol_review = importlib.import_module("laconian_eval.benchmark.protocol_review")
    subjects = benchmark.PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1
    assert subjects is protocol_review.PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1
    assert isinstance(subjects, MappingProxyType)
    assert subjects["security_evidence"] == (
        "provider_request_contract_sha256",
        "retry_spend_protocol_sha256",
        "campaign_state_schema_sha256",
        "workflow_endpoint_policy_sha256",
        "artifact_security_protocol_sha256",
        "publication_correction_protocol_sha256",
        "publication_branch_ruleset_policy_sha256",
        "identity_registry_bundle_sha256",
        "state_writer_git_identity_sha256",
        "broker_token_delivery_isolation_policy_sha256",
        "broker_signing_keys_root_sha256",
        "tag_operator_registry_sha256",
        "tag_ruleset_policy_root",
        "invalid_event_dismissal_policy_sha256",
    )
    provider_base = importlib.import_module("laconian_eval.providers.base")
    assert providers.ServiceTierStatus is provider_base.ServiceTierStatus

    from laconian_eval.replay.benchmark import build_parser

    parser = build_parser()
    subparsers = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers) == 1
    assert tuple(subparsers[0].choices) == EXPECTED_BENCHMARK_COMMANDS
    assert parser.allow_abbrev is False
    assert all(child.allow_abbrev is False for child in subparsers[0].choices.values())
    scripts = tomllib.loads(_read("pyproject.toml"))["project"]["scripts"]
    assert scripts["laconian-benchmark"] == "laconian_eval.cli:main"
    assert scripts["laconian"] == "laconian_eval.cli:entrypoint"
    replay_files = sorted((ROOT / "src/laconian_eval/replay").rglob("*.py"))
    assert replay_files
    replay_modules = []
    for path in replay_files:
        parts = path.relative_to(ROOT / "src").with_suffix("").parts
        module_name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        module = importlib.import_module(module_name)
        replay_modules.append(module)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    not alias.name.startswith("laconian_eval.campaign") for alias in node.names
                ), path
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("laconian_eval.campaign"), path
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not node.value.startswith("laconian_eval.campaign"), path

    for module in (benchmark, *replay_modules):
        assert all(not hasattr(module, name) for name in EXPECTED_PRIVATE_CONSTRUCTORS)
        public_names = getattr(
            module, "__all__", tuple(name for name in vars(module) if not name.startswith("_"))
        )
        for name in public_names:
            value = getattr(module, name)
            if not callable(value):
                continue
            owner = getattr(value, "__module__", "")
            callable_name = getattr(value, "__name__", "")
            qualified_name = owner + "." + getattr(value, "__qualname__", callable_name)
            assert not owner.startswith("laconian_eval.campaign"), (module.__name__, name)
            assert qualified_name not in EXPECTED_LIVE_METHODS, (module.__name__, name)
            assert callable_name not in EXPECTED_PRIVATE_CONSTRUCTORS, (module.__name__, name)
            if module is not benchmark:
                # Raw Pydantic records (including VerifiedProtocolAttestationV1) are data;
                # verified dataclass capabilities and their loaders are not replay exports.
                assert not callable_name.startswith("load_verified_"), (module.__name__, name)
                assert not (is_dataclass(value) and callable_name.startswith("Verified")), (
                    module.__name__,
                    name,
                )


def test_benchmark_package_uses_pep562_lazy_owner_identical_judge_exports() -> None:
    import importlib

    import laconian_eval.benchmark as benchmark

    expected = (
        "JUDGE_REQUESTED_SERVICE_TIER",
        "JUDGE_SERVICE_TIER_WIRE_FIELD",
        "BlindJudgeRequestV1",
        "JudgeProviderRequestV1",
        "JudgeRequestAttachmentV1",
        "JudgeAttemptUsageV1",
        "JudgeAttemptEvidenceV1",
        "JudgeAttemptBoundaryV1",
        "JudgeAttemptRootMemberV1",
        "JudgeAttemptRootIndexV1",
        "VerifiedJudgeAttemptRootV1",
        "write_judge_attempt_root",
        "load_verified_judge_attempt_root",
        "JudgeAttachmentV1",
        "build_judge_request_attachment",
        "verify_judge_request_attachment",
        "build_judge_attachment",
        "verify_judge_attachment",
    )
    assert expected == benchmark.JUDGE_LAZY_EXPORTS_V1
    assert all(name in benchmark.__all__ and name in dir(benchmark) for name in expected)

    judge = importlib.import_module("laconian_eval.benchmark.judge")
    for name in expected:
        assert getattr(benchmark, name) is getattr(judge, name)
        assert benchmark.__dict__[name] is getattr(judge, name)
    with pytest.raises(AttributeError):
        benchmark.__getattr__("unregistered_judge_export")


def test_cold_provider_import_and_each_cold_judge_export_are_cycle_free() -> None:
    import laconian_eval.benchmark as benchmark

    provider_probe = subprocess.run(
        (
            sys.executable,
            "-c",
            "import sys; import laconian_eval.providers.openai; "
            "assert 'laconian_eval.benchmark.judge' not in sys.modules",
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert provider_probe.returncode == 0, provider_probe.stderr

    for name in benchmark.JUDGE_LAZY_EXPORTS_V1:
        export_probe = subprocess.run(
            (
                sys.executable,
                "-c",
                "import importlib, laconian_eval.benchmark as benchmark; "
                f"value = getattr(benchmark, {name!r}); "
                "judge = importlib.import_module('laconian_eval.benchmark.judge'); "
                f"assert value is getattr(judge, {name!r}); "
                f"assert benchmark.__dict__[{name!r}] is value",
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert export_probe.returncode == 0, f"{name}: {export_probe.stderr}"
