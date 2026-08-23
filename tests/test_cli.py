from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter

import laconian_eval.cli as cli
from laconian_eval.cli import main
from laconian_eval.models import RawAttempt, RunManifest, RunSummary, ScoredAttempt
from laconian_eval.providers import ProviderError
from laconian_eval.runner import manifest_sha256

REPOSITORY_ROOT = Path(__file__).parents[1]


def _only_run_directory(results_root: Path) -> Path:
    children = tuple(results_root.iterdir())
    assert len(children) == 1
    assert children[0].is_dir()
    return children[0]


def _run_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(REPOSITORY_ROOT)
    results_root = tmp_path / "results"
    assert (
        main(
            [
                "run",
                "evals/manifests/replay-smoke.yaml",
                "--results-root",
                str(results_root),
            ]
        )
        == 0
    )
    return _only_run_directory(results_root)


@pytest.mark.parametrize(
    "path",
    [
        "evals/cases/response-smoke.yaml",
        "evals/cases/activation-smoke.yaml",
        "evals/manifests/replay-smoke.yaml",
    ],
)
def test_validate_detects_each_supported_yaml_kind(
    path: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)

    assert main(["validate", path]) == 0
    assert path in capsys.readouterr().out


def test_validate_rejects_duplicate_keys_and_unknown_yaml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("kind: response\nkind: activation\n", encoding="utf-8")
    unknown = tmp_path / "unknown.yaml"
    unknown.write_text('schema_version: "1"\nmeaning: 42\n', encoding="utf-8")

    assert main(["validate", str(duplicate)]) == 2
    assert "duplicate" in capsys.readouterr().err.lower()
    assert main(["validate", str(unknown)]) == 2
    assert "unsupported" in capsys.readouterr().err.lower()


def test_replay_run_is_offline_complete_canonical_and_non_overwriting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)

    assert {path.name for path in run_directory.iterdir()} == {
        "manifest.json",
        "raw.jsonl",
        "run.log",
    }
    manifest = RunManifest.model_validate_json(
        (run_directory / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.provider.kind == "replay"
    assert manifest.arms == ("baseline", "concise", "caveman", "if")
    attempts = tuple(
        RawAttempt.model_validate_json(line)
        for line in (run_directory / "raw.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(attempts) == 96
    assert all(attempt.terminal for attempt in attempts)
    assert {attempt.arm for attempt in attempts} == set(manifest.arms)
    assert {attempt.run_id for attempt in attempts} == {run_directory.name}
    assert {attempt.manifest_sha256 for attempt in attempts} == {manifest_sha256(manifest)}
    assert run_directory.name in capsys.readouterr().out
    combined = "".join(path.read_text(encoding="utf-8") for path in run_directory.iterdir())
    assert "OPENAI_API_KEY" not in combined


def test_run_reserves_raw_jsonl_exclusively_before_calling_the_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)
    inspected: list[Path] = []

    def inspect_reserved_output(**kwargs: object) -> tuple[()]:
        output_path = kwargs["output_path"]
        assert isinstance(output_path, Path)
        assert output_path.exists()
        assert output_path.read_bytes() == b""
        inspected.append(output_path)
        return ()

    monkeypatch.setattr(cli, "run_to_jsonl", inspect_reserved_output)

    assert (
        main(
            [
                "run",
                "evals/manifests/replay-smoke.yaml",
                "--results-root",
                str(tmp_path / "results"),
            ]
        )
        == 0
    )
    assert len(inspected) == 1


@pytest.mark.parametrize("empty_field", ["case_files", "arms"])
def test_run_rejects_empty_plan_configuration_before_result_artifacts(
    empty_field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)
    document: dict[str, object] = {
        "schema_version": "1",
        "run_name": "empty-plan",
        "provider": {"kind": "fake", "model": "fake-v1"},
        "case_files": ["evals/cases/response-smoke.yaml"],
        "arms": ["baseline"],
        "repetitions": 1,
    }
    document[empty_field] = []
    manifest_path = tmp_path / f"empty-{empty_field}.yaml"
    manifest_path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )
    results_root = tmp_path / f"results-{empty_field}"

    assert main(["run", str(manifest_path), "--results-root", str(results_root)]) == 2
    assert not results_root.exists()
    assert empty_field in capsys.readouterr().err


def test_replay_score_and_report_end_to_end_with_overwrite_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    score_directory = tmp_path / "score"
    raw_path = run_directory / "raw.jsonl"

    score_args = [
        "score",
        str(raw_path),
        "--cases",
        "evals/cases/response-smoke.yaml",
        "--output",
        str(score_directory),
    ]
    assert main(score_args) == 0
    scored_path = score_directory / "scored.jsonl"
    summary_path = score_directory / "summary.json"
    scored = TypeAdapter(tuple[ScoredAttempt, ...]).validate_python(
        tuple(json.loads(line) for line in scored_path.read_text(encoding="utf-8").splitlines())
    )
    summary = RunSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    assert len(scored) == 96
    assert summary.terminal_records == 96
    assert tuple(metrics.arm for metrics in summary.arms) == (
        "baseline",
        "concise",
        "caveman",
        "if",
    )

    scored_before = scored_path.read_bytes()
    summary_before = summary_path.read_bytes()
    assert main(score_args) == 2
    assert "overwrite" in capsys.readouterr().err.lower()
    assert scored_path.read_bytes() == scored_before
    assert summary_path.read_bytes() == summary_before

    report_path = tmp_path / "report.md"
    report_args = ["report", str(scored_path), "--output", str(report_path)]
    assert main(report_args) == 0
    report = report_path.read_text(encoding="utf-8")
    assert "# Laconian benchmark report" in report
    assert "Terminal records: 96" in report
    report_before = report_path.read_bytes()
    assert main(report_args) == 2
    assert "overwrite" in capsys.readouterr().err.lower()
    assert report_path.read_bytes() == report_before


def test_score_preflights_both_outputs_and_validates_copied_manifest_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    output = tmp_path / "score"
    output.mkdir()
    (output / "summary.json").write_text("occupied\n", encoding="utf-8")

    args = [
        "score",
        str(run_directory / "raw.jsonl"),
        "--cases",
        "evals/cases/response-smoke.yaml",
        "--output",
        str(output),
    ]
    assert main(args) == 2
    assert not (output / "scored.jsonl").exists()
    assert "overwrite" in capsys.readouterr().err.lower()

    output2 = tmp_path / "score-two"
    manifest_path = run_directory / "manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest["arm_order_seed"] += 1
    manifest_path.write_text(json.dumps(raw_manifest), encoding="utf-8")
    assert main([*args[:-1], str(output2)]) == 2
    assert not output2.exists()
    assert "manifest" in capsys.readouterr().err.lower()


def test_score_refuses_an_existing_empty_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    output = tmp_path / "existing-score"
    output.mkdir()

    code = main(
        [
            "score",
            str(run_directory / "raw.jsonl"),
            "--cases",
            "evals/cases/response-smoke.yaml",
            "--output",
            str(output),
        ]
    )

    assert code == 2
    assert tuple(output.iterdir()) == ()
    assert "overwrite" in capsys.readouterr().err.lower()


def test_score_publish_is_failure_atomic_and_rerunnable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    output = tmp_path / "atomic-score"
    args = [
        "score",
        str(run_directory / "raw.jsonl"),
        "--cases",
        "evals/cases/response-smoke.yaml",
        "--output",
        str(output),
    ]
    original_write_summary = cli.write_summary_json
    staged_directories: list[Path] = []

    def fail_summary_write(summary: RunSummary, path: Path) -> None:
        assert (path.parent / "scored.jsonl").is_file()
        staged_directories.append(path.parent)
        raise OSError("synthetic summary write failure")

    monkeypatch.setattr(cli, "write_summary_json", fail_summary_write)
    before = set(tmp_path.iterdir())

    assert main(args) == 2
    assert not output.exists()
    assert staged_directories and staged_directories[0] != output
    assert not staged_directories[0].exists()
    assert set(tmp_path.iterdir()) == before
    assert "summary write failure" in capsys.readouterr().err

    monkeypatch.setattr(cli, "write_summary_json", original_write_summary)
    assert main(args) == 0
    assert {path.name for path in output.iterdir()} == {"scored.jsonl", "summary.json"}


def test_score_publish_fsyncs_parent_and_rolls_back_if_that_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    output = tmp_path / "parent-fsync-score"
    args = [
        "score",
        str(run_directory / "raw.jsonl"),
        "--cases",
        "evals/cases/response-smoke.yaml",
        "--output",
        str(output),
    ]
    original_fsync_directory = cli._fsync_directory
    fsynced: list[Path] = []

    def fail_parent_fsync(path: Path) -> None:
        fsynced.append(path)
        if path == output.parent:
            raise OSError("synthetic parent fsync failure")
        original_fsync_directory(path)

    monkeypatch.setattr(cli, "_fsync_directory", fail_parent_fsync)

    assert main(args) == 2
    assert len(fsynced) == 2
    assert fsynced[0].parent == output.parent
    assert fsynced[0] != output
    assert fsynced[1] == output.parent
    assert not output.exists()
    assert "parent fsync failure" in capsys.readouterr().err

    monkeypatch.setattr(cli, "_fsync_directory", original_fsync_directory)
    assert main(args) == 0


def test_report_strictly_validates_summary_correspondence_and_has_a_hard_gate_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    score_directory = tmp_path / "score"
    assert (
        main(
            [
                "score",
                str(run_directory / "raw.jsonl"),
                "--cases",
                "evals/cases/response-smoke.yaml",
                "--output",
                str(score_directory),
            ]
        )
        == 0
    )
    scored_path = score_directory / "scored.jsonl"
    summary_path = score_directory / "summary.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_data["terminal_records"] = 95
    summary_path.write_text(json.dumps(summary_data), encoding="utf-8")

    mismatched_report = tmp_path / "mismatched.md"
    assert main(["report", str(scored_path), "--output", str(mismatched_report)]) == 2
    assert not mismatched_report.exists()
    assert "correspond" in capsys.readouterr().err.lower()

    fallback_directory = tmp_path / "fallback"
    fallback_directory.mkdir()
    fallback_scored = fallback_directory / "scored.jsonl"
    fallback_scored.write_bytes(scored_path.read_bytes())
    fallback_report = fallback_directory / "report.md"
    assert main(["report", str(fallback_scored), "--output", str(fallback_report)]) == 0
    assert "Quality gate: `hard`" in fallback_report.read_text(encoding="utf-8")


def test_missing_openai_key_fails_before_results_and_fake_runs_as_offline_error_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    openai_results = tmp_path / "openai-results"

    assert (
        main(
            [
                "run",
                "evals/manifests/openai-example.yaml",
                "--results-root",
                str(openai_results),
            ]
        )
        == 2
    )
    assert not openai_results.exists()
    assert "OPENAI_API_KEY" in capsys.readouterr().err

    fake_manifest = tmp_path / "fake.yaml"
    fake_manifest.write_text(
        """schema_version: \"1\"
run_name: fake-example
provider:
  kind: fake
  model: fake-v1
case_files:
  - evals/cases/response-smoke.yaml
arms: [baseline]
repetitions: 1
""",
        encoding="utf-8",
    )
    fake_results = tmp_path / "fake-results"
    assert main(["run", str(fake_manifest), "--results-root", str(fake_results)]) == 0
    fake_run = _only_run_directory(fake_results)
    attempts = tuple(
        RawAttempt.model_validate_json(line)
        for line in (fake_run / "raw.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(attempts) == 24
    assert all(attempt.terminal for attempt in attempts)
    assert {attempt.error.kind for attempt in attempts if attempt.error is not None} == {
        "missing_fake_key"
    }
    assert {path.name for path in fake_run.iterdir()} == {"manifest.json", "raw.jsonl", "run.log"}
    assert "status=complete" in (fake_run / "run.log").read_text(encoding="utf-8")


def test_unexpected_run_failure_returns_one_without_printing_a_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)
    secret = "sk-secret-must-not-leak"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    class ExplodingProvider:
        def generate(self, request: object) -> object:
            raise RuntimeError(f"synthetic programming defect: {secret}")

    def make_exploding_provider(**kwargs: object) -> ExplodingProvider:
        assert kwargs["api_key"] == secret
        return ExplodingProvider()

    monkeypatch.setattr(cli, "OpenAIProvider", make_exploding_provider)
    results_root = tmp_path / "results"

    code = main(
        [
            "run",
            "evals/manifests/openai-example.yaml",
            "--results-root",
            str(results_root),
        ]
    )

    run_directory = _only_run_directory(results_root)
    assert {path.name for path in run_directory.iterdir()} == {
        "manifest.json",
        "raw.jsonl",
        "run.log",
    }
    log = (run_directory / "run.log").read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert code == 1
    assert "run failed" in captured.err.lower()
    assert "traceback" not in captured.err.lower()
    assert "status=incomplete" in log
    assert "failure_kind=run_failure" in log
    assert "[REDACTED]" in log
    assert secret not in log
    assert secret not in captured.err


def test_authentication_stopped_run_writes_an_incomplete_log_and_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)

    class AuthenticationFailure:
        def generate(self, request: object) -> object:
            raise ProviderError(
                kind="authentication",
                message="Synthetic authentication failure.",
                retryable=False,
                request_id="req_auth",
            )

    monkeypatch.setattr(
        cli.ReplayProvider,
        "from_path",
        classmethod(lambda cls, path: AuthenticationFailure()),
    )
    results_root = tmp_path / "results"

    code = main(
        [
            "run",
            "evals/manifests/replay-smoke.yaml",
            "--results-root",
            str(results_root),
        ]
    )

    run_directory = _only_run_directory(results_root)
    log = (run_directory / "run.log").read_text(encoding="utf-8")
    attempts = (run_directory / "raw.jsonl").read_text(encoding="utf-8").splitlines()
    captured = capsys.readouterr()
    assert code == 1
    assert len(attempts) == 1
    assert "status=incomplete" in log
    assert "failure_kind=authentication" in log
    assert "status=complete" not in log
    assert "authentication" in captured.err.lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "openai"),
        ("model", "other-model"),
        ("arm", "concise"),
        ("repetition", 1),
        ("run_id", "different-run"),
    ],
)
def test_score_rejects_raw_manifest_coherence_conflicts_before_outputs(
    field: str,
    value: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)
    manifest_path = tmp_path / "baseline-replay.yaml"
    manifest_path.write_text(
        """schema_version: \"1\"
run_name: integrity-replay
provider:
  kind: replay
  model: replay-v1
  replay_file: tests/fixtures/replay-responses.yaml
case_files:
  - evals/cases/response-smoke.yaml
arms: [baseline]
repetitions: 1
arm_order_seed: 7
generation:
  max_output_tokens: 128
  temperature: null
retry:
  max_transient_retries: 0
  timeout_seconds: 5
""",
        encoding="utf-8",
    )
    results_root = tmp_path / "results"
    assert main(["run", str(manifest_path), "--results-root", str(results_root)]) == 0
    run_directory = _only_run_directory(results_root)
    raw_path = run_directory / "raw.jsonl"
    rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    rows[0][field] = value
    raw_path.write_text(
        "".join(f"{json.dumps(row, sort_keys=True)}\n" for row in rows),
        encoding="utf-8",
    )
    capsys.readouterr()
    output = tmp_path / "score"

    assert (
        main(
            [
                "score",
                str(raw_path),
                "--cases",
                "evals/cases/response-smoke.yaml",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()
    assert field in capsys.readouterr().err


def test_score_rejects_a_subset_of_the_manifest_plan_before_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    raw_path = run_directory / "raw.jsonl"
    lines = raw_path.read_text(encoding="utf-8").splitlines()
    raw_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    output = tmp_path / "score"

    assert (
        main(
            [
                "score",
                str(raw_path),
                "--cases",
                "evals/cases/response-smoke.yaml",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()
    assert "complete" in capsys.readouterr().err.lower()


def test_score_rejects_cases_that_differ_from_manifest_declared_definitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    original_path = REPOSITORY_ROOT / "evals/cases/response-smoke.yaml"
    changed_document = yaml.safe_load(original_path.read_text(encoding="utf-8"))
    changed_document["cases"][0]["semantic_rubric"]["required_facts"][0] = (
        "A materially different rubric definition."
    )
    changed_cases = tmp_path / "changed-cases.yaml"
    changed_cases.write_text(
        yaml.safe_dump(changed_document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    output = tmp_path / "score"

    assert (
        main(
            [
                "score",
                str(run_directory / "raw.jsonl"),
                "--cases",
                str(changed_cases),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()
    assert "case definitions" in capsys.readouterr().err.lower()


def test_argument_errors_return_two_and_version_behavior_is_preserved(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["run"]) == 2
    assert "usage:" in capsys.readouterr().err.lower()
    assert main(["--version"]) == 0
    assert "laconian " in capsys.readouterr().out
