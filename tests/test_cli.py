from __future__ import annotations

import builtins
import errno
import io
import json
import os
import socket
from collections.abc import Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from capsule_helpers import source_manifest_v2_payload
from pydantic import TypeAdapter

import laconian_eval.capsule.capture as capture_module
import laconian_eval.cli as cli
from laconian_eval import __version__
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.manifest_models import SourceManifestV2
from laconian_eval.cli import main
from laconian_eval.models import RawAttempt, RunManifest, RunSummary, ScoredAttempt
from laconian_eval.providers import ProviderError
from laconian_eval.runner import manifest_sha256
from laconian_eval.yaml_io import bounded_yaml_discriminator

REPOSITORY_ROOT = Path(__file__).parents[1]


class _NoAmbientOs:
    @property
    def environ(self) -> object:
        raise AssertionError("validate read ambient environment")

    @property
    def environb(self) -> object:
        raise AssertionError("validate read ambient byte environment")

    @staticmethod
    def getenv(_key: str, _default: str | None = None) -> str | None:
        raise AssertionError("validate read ambient environment")

    @staticmethod
    def getenvb(_key: bytes, _default: bytes | None = None) -> bytes | None:
        raise AssertionError("validate read ambient byte environment")

    def __getattr__(self, name: str) -> object:
        return getattr(os, name)


class _NoAmbientEnvironment(Mapping[object, object]):
    def __getitem__(self, key: object) -> object:
        raise AssertionError(f"validate read ambient environment: {key!r}")

    def __iter__(self) -> Iterator[object]:
        raise AssertionError("validate iterated ambient environment")

    def __len__(self) -> int:
        raise AssertionError("validate inspected ambient environment size")

    def get(self, key: object, default: object = None) -> object:
        del default
        return self[key]


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
            ],
            program="laconian",
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

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("validate constructed a provider")

    monkeypatch.setattr(cli, "FakeProvider", forbidden)
    monkeypatch.setattr(cli, "ReplayProvider", forbidden)
    monkeypatch.setattr(cli, "OpenAIProvider", forbidden)
    monkeypatch.setattr(cli, "os", _NoAmbientOs())

    assert main(["validate", path], program="laconian") == 0
    assert path in capsys.readouterr().out


def test_validate_rejects_duplicate_keys_and_unknown_yaml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("kind: response\nkind: activation\n", encoding="utf-8")
    unknown = tmp_path / "unknown.yaml"
    unknown.write_text('schema_version: "1"\nmeaning: 42\n', encoding="utf-8")

    assert main(["validate", str(duplicate)], program="laconian") == 2
    assert "duplicate" in capsys.readouterr().err.lower()
    assert main(["validate", str(unknown)], program="laconian") == 2
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
    assert manifest.runner_version == __version__
    assert manifest.arms == ("baseline", "concise", "caveman", "if")
    attempts = tuple(
        RawAttempt.model_validate_json(line)
        for line in (run_directory / "raw.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(attempts) == 96
    assert all(attempt.terminal for attempt in attempts)
    assert {attempt.arm for attempt in attempts} == set(manifest.arms)
    assert {attempt.run_id for attempt in attempts} == {run_directory.name}
    assert {attempt.runner_version for attempt in attempts} == {__version__}
    assert {attempt.manifest_sha256 for attempt in attempts} == {manifest_sha256(manifest)}
    case_hashes = {
        case_id: {
            attempt.case_definition_sha256 for attempt in attempts if attempt.case_id == case_id
        }
        for case_id in {attempt.case_id for attempt in attempts}
    }
    assert len(case_hashes) == 24
    assert all(len(hashes) == 1 for hashes in case_hashes.values())
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
            ],
            program="laconian",
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
        "runner_version": "0.1.0a1",
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

    assert (
        main(["run", str(manifest_path), "--results-root", str(results_root)], program="laconian")
        == 2
    )
    assert not results_root.exists()
    assert empty_field in capsys.readouterr().err


def test_openai_run_rejects_whitespace_model_before_result_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    manifest_path = tmp_path / "blank-model.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "run_name": "blank-model",
                "provider": {
                    "kind": "openai",
                    "model": " \t",
                    "api_key_env": "OPENAI_API_KEY",
                },
                "case_files": ["evals/cases/response-smoke.yaml"],
                "arms": ["baseline"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    results_root = tmp_path / "results"

    assert (
        main(["run", str(manifest_path), "--results-root", str(results_root)], program="laconian")
        == 2
    )
    assert not results_root.exists()
    assert "model" in capsys.readouterr().err.lower()


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
    assert main(score_args, program="laconian") == 0
    scored_path = score_directory / "scored.jsonl"
    summary_path = score_directory / "summary.json"
    scored = TypeAdapter(tuple[ScoredAttempt, ...]).validate_python(
        tuple(json.loads(line) for line in scored_path.read_text(encoding="utf-8").splitlines())
    )
    summary = RunSummary.model_validate_json(summary_path.read_text(encoding="utf-8"))
    assert len(scored) == 96
    assert summary.terminal_records == 96
    assert summary.runner_versions == (__version__,)
    assert len(summary.case_definitions) == 24
    assert {item.case_id: item.sha256 for item in summary.case_definitions} == {
        attempt.raw.case_id: attempt.raw.case_definition_sha256 for attempt in scored
    }
    assert summary.providers == ("replay",)
    assert tuple(metrics.arm for metrics in summary.arms) == (
        "baseline",
        "concise",
        "caveman",
        "if",
    )

    scored_before = scored_path.read_bytes()
    summary_before = summary_path.read_bytes()
    assert main(score_args, program="laconian") == 2
    assert "overwrite" in capsys.readouterr().err.lower()
    assert scored_path.read_bytes() == scored_before
    assert summary_path.read_bytes() == summary_before

    report_path = tmp_path / "report.md"
    report_args = ["report", str(scored_path), "--output", str(report_path)]
    assert main(report_args, program="laconian") == 0
    report = report_path.read_text(encoding="utf-8")
    assert "# Laconian benchmark report" in report
    assert "Replay fixture" in report
    assert "not a public benchmark result" in report
    assert f"Runner versions: `{__version__}`" in report
    assert "Case definitions: 24" in report
    assert "Terminal records: 96" in report
    report_before = report_path.read_bytes()
    assert main(report_args, program="laconian") == 2
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
    assert main(args, program="laconian") == 2
    assert not (output / "scored.jsonl").exists()
    assert "overwrite" in capsys.readouterr().err.lower()

    output2 = tmp_path / "score-two"
    manifest_path = run_directory / "manifest.json"
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest["arm_order_seed"] += 1
    manifest_path.write_text(json.dumps(raw_manifest), encoding="utf-8")
    assert main([*args[:-1], str(output2)], program="laconian") == 2
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
        ],
        program="laconian",
    )

    assert code == 2
    assert tuple(output.iterdir()) == ()
    assert "overwrite" in capsys.readouterr().err.lower()


def test_score_concurrent_empty_directory_is_preserved_and_rerun_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_directory = _run_replay(tmp_path, monkeypatch)
    output = tmp_path / "concurrent-score"
    args = [
        "score",
        str(run_directory / "raw.jsonl"),
        "--cases",
        "evals/cases/response-smoke.yaml",
        "--output",
        str(output),
    ]
    original_preflight = cli._preflight_score_output
    preflights = 0

    def create_after_final_preflight(path: Path) -> None:
        nonlocal preflights
        original_preflight(path)
        preflights += 1
        if preflights == 3:
            path.mkdir()

    monkeypatch.setattr(cli, "_preflight_score_output", create_after_final_preflight)

    assert main(args, program="laconian") == 2
    assert preflights == 3
    assert output.is_dir()
    assert tuple(output.iterdir()) == ()
    assert "overwrite" in capsys.readouterr().err.lower()
    assert not tuple(tmp_path.glob(f".{output.name}.tmp-*"))

    output.rmdir()
    monkeypatch.setattr(cli, "_preflight_score_output", original_preflight)
    assert main(args, program="laconian") == 0
    assert {path.name for path in output.iterdir()} == {"scored.jsonl", "summary.json"}


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

    assert main(args, program="laconian") == 2
    assert not output.exists()
    assert staged_directories and staged_directories[0] != output
    assert not staged_directories[0].exists()
    assert set(tmp_path.iterdir()) == before
    assert "summary write failure" in capsys.readouterr().err

    monkeypatch.setattr(cli, "write_summary_json", original_write_summary)
    assert main(args, program="laconian") == 0
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

    assert main(args, program="laconian") == 2
    assert len(fsynced) == 3
    assert fsynced[0].parent == output.parent
    assert fsynced[0] != output
    assert fsynced[1] == output
    assert fsynced[2] == output.parent
    assert not output.exists()
    assert "parent fsync failure" in capsys.readouterr().err

    monkeypatch.setattr(cli, "_fsync_directory", original_fsync_directory)
    assert main(args, program="laconian") == 0


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
            ],
            program="laconian",
        )
        == 0
    )
    scored_path = score_directory / "scored.jsonl"
    summary_path = score_directory / "summary.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_data["case_definitions"][0]["sha256"] = "f" * 64
    summary_path.write_text(json.dumps(summary_data), encoding="utf-8")

    mismatched_report = tmp_path / "mismatched.md"
    assert (
        main(["report", str(scored_path), "--output", str(mismatched_report)], program="laconian")
        == 2
    )
    assert not mismatched_report.exists()
    assert "correspond" in capsys.readouterr().err.lower()

    fallback_directory = tmp_path / "fallback"
    fallback_directory.mkdir()
    fallback_scored = fallback_directory / "scored.jsonl"
    fallback_scored.write_bytes(scored_path.read_bytes())
    fallback_report = fallback_directory / "report.md"
    assert (
        main(["report", str(fallback_scored), "--output", str(fallback_report)], program="laconian")
        == 0
    )
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
            ],
            program="laconian",
        )
        == 2
    )
    assert not openai_results.exists()
    assert "OPENAI_API_KEY" in capsys.readouterr().err

    fake_manifest = tmp_path / "fake.yaml"
    fake_manifest.write_text(
        """schema_version: \"1\"
runner_version: 0.1.0a1
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
    assert (
        main(["run", str(fake_manifest), "--results-root", str(fake_results)], program="laconian")
        == 0
    )
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
        ],
        program="laconian",
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
        ],
        program="laconian",
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
runner_version: 0.1.0a1
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
    assert (
        main(["run", str(manifest_path), "--results-root", str(results_root)], program="laconian")
        == 0
    )
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
            ],
            program="laconian",
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
            ],
            program="laconian",
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
            ],
            program="laconian",
        )
        == 2
    )
    assert not output.exists()
    assert "case definitions" in capsys.readouterr().err.lower()


def test_argument_errors_return_two_and_version_behavior_is_preserved(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["run"], program="laconian") == 2
    assert "usage:" in capsys.readouterr().err.lower()
    assert main(["--version"], program="laconian") == 0
    assert "laconian " in capsys.readouterr().out


@pytest.mark.parametrize("schema_version", ["1", "2"])
def test_validate_source_manifests_checks_schema_without_resolving_referenced_files(
    schema_version: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / f"source-v{schema_version}.yaml"
    if schema_version == "1":
        document: dict[str, object] = {
            "schema_version": "1",
            "runner_version": __version__,
            "run_name": "validate-v1",
            "provider": {"kind": "fake", "model": "fixture-v1"},
            "case_files": [str(tmp_path / "absolute-and-missing-cases.yaml")],
            "arms": ["baseline"],
        }
    else:
        document = source_manifest_v2_payload()
        document["case_files"] = ["missing/cases.yaml"]
        capsule = document["capsule"]
        assert isinstance(capsule, dict)
        datasets = capsule["datasets"]
        assert isinstance(datasets, list)
        capsule["datasets"] = [datasets[0] | {"case_file_ordinals": [0]}]
        capsule["comparisons"] = []
        capsule["protocol_bindings"] = []
    manifest_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("validate resolved or captured a referenced file")

    for name in (
        "load_source_manifest_capture",
        "capture_authored_inputs",
        "prepare_capsule",
        "_provider",
    ):
        monkeypatch.setattr(cli, name, forbidden, raising=False)
    monkeypatch.setattr(cli, "FakeProvider", forbidden)
    monkeypatch.setattr(cli, "ReplayProvider", forbidden)
    monkeypatch.setattr(cli, "OpenAIProvider", forbidden)
    monkeypatch.setattr(cli, "os", _NoAmbientOs())

    assert main(["validate", str(manifest_path)], program="laconian") == 0
    captured = capsys.readouterr()
    assert captured.out == f"valid: {manifest_path}\n"
    assert captured.err == ""


def test_validate_openai_manifest_never_reads_the_declared_credential_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = source_manifest_v2_payload()
    document["provider"] = {
        "kind": "openai",
        "model": "fixture-v1",
        "api_key_env": "LIVE_OPENAI_API_KEY",
        "replay_file": None,
    }
    document["case_files"] = ["missing/cases.yaml"]
    capsule = document["capsule"]
    assert isinstance(capsule, dict)
    datasets = capsule["datasets"]
    assert isinstance(datasets, list)
    capsule["datasets"] = [datasets[0] | {"case_file_ordinals": [0]}]
    capsule["comparisons"] = []
    capsule["protocol_bindings"] = []
    SourceManifestV2.model_validate(document)
    manifest_path = tmp_path / "openai-source-v2.yaml"
    manifest_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("validate resolved inputs, credentials, or constructed a provider")

    for name in (
        "load_source_manifest_capture",
        "capture_authored_inputs",
        "prepare_capsule",
        "_provider",
    ):
        monkeypatch.setattr(cli, name, forbidden, raising=False)
    monkeypatch.setattr(cli, "FakeProvider", forbidden)
    monkeypatch.setattr(cli, "ReplayProvider", forbidden)
    monkeypatch.setattr(cli, "OpenAIProvider", forbidden)
    monkeypatch.setattr(cli, "os", _NoAmbientOs())
    namespace = SimpleNamespace(command="validate", path=manifest_path)
    parser = SimpleNamespace(parse_args=lambda _argv: namespace)
    monkeypatch.setattr(cli, "_parser", lambda: parser)
    with pytest.MonkeyPatch.context() as barrier:
        barrier.setattr(os, "environ", _NoAmbientEnvironment())
        barrier.setattr(os, "environb", _NoAmbientEnvironment())
        barrier.setattr(os, "getenv", forbidden)
        barrier.setattr(os, "getenvb", forbidden)
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "gethostbyaddr",
        ):
            barrier.setattr(socket, name, forbidden)
        assert main(["validate", str(manifest_path)], program="laconian") == 0
    captured = capsys.readouterr()
    assert captured.out == f"valid: {manifest_path}\n"
    assert captured.err == ""


def _assert_strict_source_manifest_rejection_before_capture_or_model(
    path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    forbid_unbounded_path_read: bool = False,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("strict source preflight reached capture, model, or unbounded read")

    for target in (cli, capture_module):
        monkeypatch.setattr(target, "load_source_manifest_capture", forbidden, raising=False)
        monkeypatch.setattr(target, "capture_authored_inputs", forbidden, raising=False)
    monkeypatch.setattr(capture_module, "project_v1_manifest", forbidden)
    monkeypatch.setattr(SourceManifestV2, "model_validate", forbidden)
    monkeypatch.setattr(RunManifest, "model_validate", forbidden)
    if forbid_unbounded_path_read:
        real_builtin_open = builtins.open
        real_io_open = io.open
        real_path_open = Path.open
        real_read_bytes = Path.read_bytes
        real_read_text = Path.read_text

        def is_target(candidate: object) -> bool:
            if isinstance(candidate, int):
                return False
            try:
                return os.fspath(candidate) == os.fspath(path)
            except TypeError:
                return False

        def bounded_builtin_open(*args: object, **kwargs: object) -> object:
            if args and is_target(args[0]):
                raise AssertionError("validate used unbounded builtins.open")
            return real_builtin_open(*args, **kwargs)

        def bounded_io_open(*args: object, **kwargs: object) -> object:
            if args and is_target(args[0]):
                raise AssertionError("validate used unbounded io.open")
            return real_io_open(*args, **kwargs)

        def bounded_path_open(
            candidate: Path,
            mode: str = "r",
            buffering: int = -1,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> object:
            if candidate == path:
                raise AssertionError("validate used unbounded Path.open")
            return real_path_open(
                candidate,
                mode=mode,
                buffering=buffering,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )

        def bounded_read_bytes(candidate: Path) -> bytes:
            if candidate == path:
                raise AssertionError("validate used unbounded Path.read_bytes")
            return real_read_bytes(candidate)

        def bounded_read_text(
            candidate: Path,
            encoding: str | None = None,
            errors: str | None = None,
        ) -> str:
            if candidate == path:
                raise AssertionError("validate used unbounded Path.read_text")
            return real_read_text(candidate, encoding=encoding, errors=errors)

        monkeypatch.setattr(builtins, "open", bounded_builtin_open)
        monkeypatch.setattr(io, "open", bounded_io_open)
        monkeypatch.setattr(Path, "open", bounded_path_open)
        monkeypatch.setattr(Path, "read_bytes", bounded_read_bytes)
        monkeypatch.setattr(Path, "read_text", bounded_read_text)

    assert main(["validate", str(path)], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert captured.err.endswith("\n")
    assert captured.err.count("\n") == 1
    assert len(captured.err.encode("utf-8")) <= RESOURCE_LIMITS_V1.diagnostic_bytes
    assert "TOP-SECRET" not in captured.err


@pytest.mark.parametrize("schema_version", ["1", "2"])
def test_validate_rejects_oversized_source_manifest_before_unbounded_read_or_model(
    schema_version: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if schema_version == "1":
        document: dict[str, object] = {
            "schema_version": "1",
            "runner_version": __version__,
            "run_name": "oversized-v1",
            "provider": {"kind": "fake", "model": "fixture-v1"},
            "case_files": ["missing/cases.yaml"],
            "arms": ["baseline"],
            "repetitions": 1,
            "arm_order_seed": 0,
            "generation": {"max_output_tokens": 128, "temperature": None},
            "retry": {"max_transient_retries": 0, "timeout_seconds": 5.0},
        }
    else:
        document = source_manifest_v2_payload()
        document["case_files"] = ["missing/cases.yaml"]
        capsule = document["capsule"]
        assert isinstance(capsule, dict)
        datasets = capsule["datasets"]
        assert isinstance(datasets, list)
        capsule["datasets"] = [datasets[0] | {"case_file_ordinals": [0]}]
        capsule["comparisons"] = []
        capsule["protocol_bindings"] = []
    prefix = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode("utf-8")
    padding = RESOURCE_LIMITS_V1.source_manifest_bytes + 1 - len(prefix)
    assert padding > 2
    path = tmp_path / f"oversized-source-v{schema_version}.yaml"
    path.write_bytes(prefix + b"#" + b"x" * (padding - 1))
    assert path.stat().st_size == RESOURCE_LIMITS_V1.source_manifest_bytes + 1

    _assert_strict_source_manifest_rejection_before_capture_or_model(
        path,
        monkeypatch,
        capsys,
        forbid_unbounded_path_read=True,
    )


def test_validate_source_manifest_read_remains_bounded_when_metadata_lies_and_file_grows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = source_manifest_v2_payload()
    document["case_files"] = ["missing/cases.yaml"]
    capsule = document["capsule"]
    assert isinstance(capsule, dict)
    datasets = capsule["datasets"]
    assert isinstance(datasets, list)
    capsule["datasets"] = [datasets[0] | {"case_file_ordinals": [0]}]
    capsule["comparisons"] = []
    capsule["protocol_bindings"] = []
    prefix = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode("utf-8")
    path = tmp_path / "growing-source-v2.yaml"
    path.write_bytes(prefix)
    original = path.stat()
    target_identity = (original.st_dev, original.st_ino)
    limit = RESOURCE_LIMITS_V1.source_manifest_bytes
    final_size = limit + 4096
    real_builtin_open = builtins.open
    real_io_open = io.open
    real_path_open = Path.open
    real_path_read_bytes = Path.read_bytes
    real_path_read_text = Path.read_text
    real_fstat = os.fstat
    real_lstat = os.lstat
    real_read = os.read
    real_stat = os.stat
    grew = False
    bytes_read = 0
    read_requests: list[int] = []

    def grow_once() -> None:
        nonlocal grew
        if grew:
            return
        padding = final_size - len(prefix)
        assert padding > 2
        with real_builtin_open(path, "ab") as output:
            output.write(b"\n#" + b"x" * (padding - 2))
        grew = True
        assert real_stat(path).st_size == final_size

    def lying_metadata(metadata: os.stat_result) -> os.stat_result:
        if (metadata.st_dev, metadata.st_ino) != target_identity:
            return metadata
        grow_once()
        fields = list(metadata)
        fields[6] = len(prefix)
        return os.stat_result(fields)

    def lying_fstat(descriptor: int) -> os.stat_result:
        return lying_metadata(real_fstat(descriptor))

    def lying_lstat(
        path_value: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
    ) -> os.stat_result:
        if dir_fd is None:
            metadata = real_lstat(path_value)
        else:
            metadata = real_lstat(path_value, dir_fd=dir_fd)
        return lying_metadata(metadata)

    def lying_stat(
        path_value: os.PathLike[str] | str | int,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        if dir_fd is None:
            metadata = real_stat(path_value, follow_symlinks=follow_symlinks)
        else:
            metadata = real_stat(
                path_value,
                dir_fd=dir_fd,
                follow_symlinks=follow_symlinks,
            )
        return lying_metadata(metadata)

    def is_target(candidate: object) -> bool:
        if isinstance(candidate, int):
            return False
        try:
            return os.fspath(candidate) == os.fspath(path)
        except TypeError:
            return False

    def forbid_builtin_open(*args: object, **kwargs: object) -> object:
        if args and is_target(args[0]):
            raise AssertionError("validate used unbounded builtins.open after a size precheck")
        return real_builtin_open(*args, **kwargs)

    def forbid_io_open(*args: object, **kwargs: object) -> object:
        if args and is_target(args[0]):
            raise AssertionError("validate used unbounded io.open after a size precheck")
        return real_io_open(*args, **kwargs)

    def forbid_path_open(candidate: Path, *args: object, **kwargs: object) -> object:
        if candidate == path:
            raise AssertionError("validate used unbounded Path.open after a size precheck")
        return real_path_open(candidate, *args, **kwargs)

    def forbid_path_read_bytes(candidate: Path) -> bytes:
        if candidate == path:
            raise AssertionError("validate used unbounded Path.read_bytes after a size precheck")
        return real_path_read_bytes(candidate)

    def forbid_path_read_text(
        candidate: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if candidate == path:
            raise AssertionError("validate used unbounded Path.read_text after a size precheck")
        return real_path_read_text(candidate, encoding=encoding, errors=errors)

    def bounded_read(descriptor: int, count: int) -> bytes:
        nonlocal bytes_read
        metadata = real_fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != target_identity:
            return real_read(descriptor, count)
        assert 0 < count <= limit + 1
        read_requests.append(count)
        chunk = real_read(descriptor, count)
        bytes_read += len(chunk)
        assert bytes_read <= limit + 1
        return chunk

    def forbidden_model_or_capture(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("growing source reached capture or model construction")

    for target in (cli, capture_module):
        monkeypatch.setattr(
            target,
            "load_source_manifest_capture",
            forbidden_model_or_capture,
            raising=False,
        )
        monkeypatch.setattr(
            target,
            "capture_authored_inputs",
            forbidden_model_or_capture,
            raising=False,
        )
    monkeypatch.setattr(SourceManifestV2, "model_validate", forbidden_model_or_capture)
    monkeypatch.setattr(RunManifest, "model_validate", forbidden_model_or_capture)
    monkeypatch.setattr(builtins, "open", forbid_builtin_open)
    monkeypatch.setattr(io, "open", forbid_io_open)
    monkeypatch.setattr(Path, "open", forbid_path_open)
    monkeypatch.setattr(Path, "read_bytes", forbid_path_read_bytes)
    monkeypatch.setattr(Path, "read_text", forbid_path_read_text)
    monkeypatch.setattr(os, "fstat", lying_fstat)
    monkeypatch.setattr(os, "lstat", lying_lstat)
    monkeypatch.setattr(os, "stat", lying_stat)
    monkeypatch.setattr(os, "read", bounded_read)

    assert main(["validate", str(path)], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert captured.err.count("\n") == 1
    assert grew is True
    assert real_stat(path).st_size == final_size
    assert read_requests
    assert bytes_read == limit + 1


def test_validate_streams_late_source_discriminants_without_full_yaml_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "late-source.yaml"
    padding = RESOURCE_LIMITS_V1.source_manifest_bytes + 1024
    path.write_bytes(
        b"#" + b"x" * padding + b"\nschema_version: '2'\nprovider: {}\ncase_files: []\n"
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("oversized late-discriminator source reached YAML construction")

    monkeypatch.setattr(cli, "_strict_validation_mapping", forbidden)
    monkeypatch.setattr(cli, "parse_source_manifest_bytes", forbidden)
    monkeypatch.setattr(SourceManifestV2, "model_validate", forbidden)
    monkeypatch.setattr(RunManifest, "model_validate", forbidden)

    assert main(["validate", str(path)], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: source manifest exceeds its resource limit\n"


def test_validate_accepts_large_response_case_with_late_kind_and_long_prompt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "large-response.yaml"
    prompt = b"x" * (RESOURCE_LIMITS_V1.source_manifest_bytes + 4096)
    path.write_bytes(
        b'schema_version: "1"\n'
        b"cases:\n"
        b"  - id: long-prompt-en\n"
        b"    scenario_id: long-prompt\n"
        b"    locale: en\n"
        b"    category: direct\n"
        b"    prompt: " + prompt + b"\n"
        b"  - id: long-prompt-ru\n"
        b"    scenario_id: long-prompt\n"
        b"    locale: ru\n"
        b"    category: direct\n"
        b"    prompt: korotkii\n"
        b"kind: response\n"
    )
    assert len(prompt) > RESOURCE_LIMITS_V1.bounded_string_bytes
    assert RESOURCE_LIMITS_V1.source_manifest_bytes < path.stat().st_size
    assert path.stat().st_size <= RESOURCE_LIMITS_V1.case_file_bytes

    assert main(["validate", str(path)], program="laconian") == 0
    captured = capsys.readouterr()
    assert captured.out == f"valid: {path}\n"
    assert captured.err == ""


def test_validate_streams_past_early_case_kind_to_late_source_discriminants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "early-case-late-source.yaml"
    path.write_bytes(
        b"kind: response\n#"
        + b"x" * (RESOURCE_LIMITS_V1.source_manifest_bytes + 1024)
        + b'\nschema_version: "2"\nprovider: {}\ncase_files: []\n'
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("oversized source reached the case loader")

    monkeypatch.setattr(cli, "load_response_cases", forbidden)

    assert main(["validate", str(path)], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: source manifest exceeds its resource limit\n"


@pytest.mark.parametrize(
    "leading_scalar",
    [
        b"padding: " + b"word " * 220_000 + b"\n",
        b"padding: '" + b"x" * (RESOURCE_LIMITS_V1.source_manifest_bytes + 1024) + b"'\n",
        b"padding: >\n" + b"  word word word word\n" * 60_000,
    ],
    ids=("spaced-plain", "single-quoted", "folded-block"),
)
def test_validate_discriminator_never_constructs_a_huge_preceding_scalar(
    leading_scalar: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "late-source.yaml"
    path.write_bytes(leading_scalar + b"schema_version: '2'\nprovider: {}\ncase_files: []\n")
    assert path.stat().st_size > RESOURCE_LIMITS_V1.source_manifest_bytes

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("oversized source scalar reached YAML/model construction")

    monkeypatch.setattr(cli, "_strict_validation_mapping", forbidden)
    monkeypatch.setattr(cli, "parse_source_manifest_bytes", forbidden)
    monkeypatch.setattr(SourceManifestV2, "model_validate", forbidden)
    monkeypatch.setattr(RunManifest, "model_validate", forbidden)

    assert main(["validate", str(path)], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: source manifest exceeds its resource limit\n"


@pytest.mark.parametrize(
    "document",
    [
        b"  schema_version: '1'\n  cases: []\n  kind: response\n",
        b'---\n{"schema_version":"1","cases":[],"kind":"response"}\n',
        b'%YAML 1.1\n---\n{"schema_version":"1","cases":[],"kind":"response"}\n',
        (b'{"schema_version":"1","cases":[],"\\u006b\\u0069\\u006e\\u0064":"response"}\n'),
        b'{prompt: foo#bar, schema_version: "1", cases: [], kind: response}\n',
    ],
    ids=("indented-root", "document-marker", "directive", "escaped-key", "plain-hash"),
)
def test_validate_discriminator_preserves_supported_yaml_grammar(document: bytes) -> None:
    assert bounded_yaml_discriminator(document) == "response"


@pytest.mark.parametrize(
    "document",
    [
        (
            b"padding: {\nkind: response\n, other: x\n}\n"
            b"schema_version: '2'\nprovider: {}\ncase_files: []\n"
        ),
        (
            b'padding: "foo\nkind: response\nbar"\n'
            b"schema_version: '2'\nprovider: {}\ncase_files: []\n"
        ),
    ],
    ids=("nested-flow", "quoted-content"),
)
def test_validate_discriminator_never_promotes_nested_kind(document: bytes) -> None:
    assert bounded_yaml_discriminator(document) == "source"


def test_validate_discriminator_streams_a_huge_scalar_with_bounded_reads() -> None:
    document = (
        b"padding: " + b"word " * 220_000 + b"\nschema_version: '2'\nprovider: {}\ncase_files: []\n"
    )

    class CountingStream(io.BytesIO):
        def __init__(self, data: bytes) -> None:
            super().__init__(data)
            self.bytes_read = 0
            self.max_requested = 0
            self.max_returned = 0

        def read(self, size: int = -1) -> bytes:
            assert 0 <= size <= 64 * 1024
            chunk = super().read(size)
            self.bytes_read += len(chunk)
            self.max_requested = max(self.max_requested, size)
            self.max_returned = max(self.max_returned, len(chunk))
            return chunk

    stream = CountingStream(document)
    assert bounded_yaml_discriminator(stream) == "source"
    assert stream.bytes_read == len(document)
    assert stream.max_requested <= 64 * 1024
    assert stream.max_returned <= 64 * 1024


def test_validate_discriminator_bounds_shorthand_tag_before_unbounded_read() -> None:
    document = b"padding: !" + b"x" * 100_000 + b" value\nkind: response\n"

    class CountingStream(io.BytesIO):
        def __init__(self, data: bytes) -> None:
            super().__init__(data)
            self.bytes_read = 0

        def read(self, size: int = -1) -> bytes:
            chunk = super().read(size)
            self.bytes_read += len(chunk)
            assert self.bytes_read <= 64 * 1024
            return chunk

    stream = CountingStream(document)
    with pytest.raises(ResourceLimitError, match="resource limit rejected"):
        bounded_yaml_discriminator(stream)
    assert stream.bytes_read <= 64 * 1024


@pytest.mark.parametrize(
    "document",
    [
        b"padding: !<tag:" + b"x" * 100_000 + b"> value\nkind: response\n",
        b"%" + b"X" * 100_000 + b"\n---\nkind: response\n",
    ],
    ids=("tag-uri", "directive-name"),
)
def test_validate_discriminator_bounds_non_scalar_token_lookahead(document: bytes) -> None:
    with pytest.raises(ResourceLimitError, match="resource limit rejected"):
        bounded_yaml_discriminator(document)


@pytest.mark.parametrize(
    "document",
    [
        b'{"padding":"'
        + b"\\U00000061" * RESOURCE_LIMITS_V1.bounded_string_bytes
        + b'","kind":"response"}',
        b'{"padding":"' + (b"\\\n" + b" " * 10_000) * 100 + b'a","kind":"response"}',
        b"padding: |\n" + b" " * 20_000 + b"a\nkind: response\n",
    ],
    ids=("unicode-escapes", "line-continuations", "block-indentation"),
)
def test_validate_discriminator_budgets_decoded_scalar_not_raw_form(document: bytes) -> None:
    assert bounded_yaml_discriminator(document) == "response"


def test_validate_discriminator_rejects_depth_before_growing_an_unbounded_stack() -> None:
    document = (
        b"[" * (RESOURCE_LIMITS_V1.nesting_depth + 1)
        + b"null"
        + b"]" * (RESOURCE_LIMITS_V1.nesting_depth + 1)
    )

    with pytest.raises(ResourceLimitError, match="resource limit rejected"):
        bounded_yaml_discriminator(document)


@pytest.mark.parametrize("read_fails", [False, True])
def test_validate_consumes_each_owned_descriptor_once_when_close_is_ambiguous(
    read_fails: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "source.yaml"
    path.write_text("schema_version: '2'\nprovider: {}\ncase_files: []\n", encoding="utf-8")
    target_fd: int | None = None
    close_calls: list[int] = []

    class CloseFailureOs(_NoAmbientOs):
        @staticmethod
        def open(
            path_value: os.PathLike[str] | str,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal target_fd
            descriptor = (
                os.open(path_value, flags, mode)
                if dir_fd is None
                else os.open(path_value, flags, mode, dir_fd=dir_fd)
            )
            target_fd = descriptor
            return descriptor

        @staticmethod
        def read(descriptor: int, count: int) -> bytes:
            if read_fails and descriptor == target_fd:
                raise OSError("TOP-SECRET primary read failure")
            return os.read(descriptor, count)

        @staticmethod
        def close(descriptor: int) -> None:
            close_calls.append(descriptor)
            os.close(descriptor)
            if descriptor == target_fd:
                raise OSError("TOP-SECRET ambiguous close failure")

    monkeypatch.setattr(cli, "os", CloseFailureOs())

    assert main(["validate", str(path)], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: unable to read YAML\n"
    assert target_fd is not None
    assert close_calls.count(target_fd) == 1
    assert len(close_calls) == 2
    with pytest.raises(OSError) as closed:
        os.fstat(target_fd)
    assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize(
    "fixture_path",
    ["evals/cases/response-smoke.yaml", "evals/cases/activation-smoke.yaml"],
)
def test_validate_keeps_the_eight_mib_case_limit_separate_from_source_manifests(
    fixture_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = (REPOSITORY_ROOT / fixture_path).read_bytes()
    target_size = RESOURCE_LIMITS_V1.source_manifest_bytes + 1024
    assert len(source) < target_size
    path = tmp_path / Path(fixture_path).name
    path.write_bytes(source + b"\n#" + b"x" * (target_size - len(source) - 2))
    assert RESOURCE_LIMITS_V1.source_manifest_bytes < path.stat().st_size
    assert path.stat().st_size < RESOURCE_LIMITS_V1.case_file_bytes

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("case-only validate captured inputs or constructed a provider")

    for name in (
        "load_source_manifest_capture",
        "capture_authored_inputs",
        "prepare_capsule",
        "_provider",
    ):
        monkeypatch.setattr(cli, name, forbidden, raising=False)
    monkeypatch.setattr(cli, "FakeProvider", forbidden)
    monkeypatch.setattr(cli, "ReplayProvider", forbidden)
    monkeypatch.setattr(cli, "OpenAIProvider", forbidden)
    monkeypatch.setattr(cli, "os", _NoAmbientOs())

    assert main(["validate", str(path)], program="laconian") == 0
    captured = capsys.readouterr()
    assert captured.out == f"valid: {path}\n"


@pytest.mark.parametrize(
    "fixture_path",
    ["evals/cases/response-smoke.yaml", "evals/cases/activation-smoke.yaml"],
)
def test_validate_accepts_large_case_when_kind_follows_the_source_manifest_limit(
    fixture_path: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = yaml.safe_load((REPOSITORY_ROOT / fixture_path).read_bytes())
    kind = document.pop("kind")
    prefix = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode("utf-8")
    padding = RESOURCE_LIMITS_V1.source_manifest_bytes + 1024 - len(prefix)
    assert padding > 2
    path = tmp_path / Path(fixture_path).name
    path.write_bytes(prefix + b"#" + b"x" * (padding - 1) + f"\nkind: {kind}\n".encode())

    assert main(["validate", str(path)], program="laconian") == 0
    captured = capsys.readouterr()
    assert captured.out == f"valid: {path}\n"
    assert captured.err == ""


@pytest.mark.parametrize(
    "fixture_path",
    ["evals/cases/response-smoke.yaml", "evals/cases/activation-smoke.yaml"],
)
def test_validate_accepts_large_single_line_flow_case_without_a_line_limit(
    fixture_path: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = yaml.safe_load((REPOSITORY_ROOT / fixture_path).read_bytes())
    compact = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert compact.startswith(b"{")
    path = tmp_path / Path(fixture_path).name
    path.write_bytes(b"{" + b" " * (RESOURCE_LIMITS_V1.source_manifest_bytes + 1024) + compact[1:])

    assert main(["validate", str(path)], program="laconian") == 0
    captured = capsys.readouterr()
    assert captured.out == f"valid: {path}\n"
    assert captured.err == ""


def test_validate_streams_single_line_flow_until_a_late_top_level_kind(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = yaml.safe_load((REPOSITORY_ROOT / "evals/cases/response-smoke.yaml").read_bytes())
    english, russian = fixture["cases"][:2]
    cases: list[dict[str, object]] = []
    for ordinal in range(2500):
        scenario_id = f"large-flow-{ordinal:04d}"
        cases.extend(
            (
                english | {"id": f"{scenario_id}-en", "scenario_id": scenario_id},
                russian | {"id": f"{scenario_id}-ru", "scenario_id": scenario_id},
            )
        )
    document = {
        "schema_version": fixture["schema_version"],
        "cases": cases,
        "kind": "response",
    }
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert encoded.index(b'"kind":"response"') > RESOURCE_LIMITS_V1.source_manifest_bytes
    assert len(encoded) < RESOURCE_LIMITS_V1.case_file_bytes
    path = tmp_path / "late-kind-flow.json"
    path.write_bytes(encoded)

    assert main(["validate", str(path)], program="laconian") == 0
    captured = capsys.readouterr()
    assert captured.out == f"valid: {path}\n"
    assert captured.err == ""


@pytest.mark.parametrize("schema_version", ["1", "2"])
@pytest.mark.parametrize("hostile_kind", ["anchor", "merge", "depth", "collection"])
def test_validate_rejects_strict_yaml_and_resource_violations_before_model_dispatch(
    hostile_kind: str,
    schema_version: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if schema_version == "1":
        document: dict[str, object] = {
            "schema_version": "1",
            "runner_version": __version__,
            "run_name": "hostile-v1",
            "provider": {
                "kind": "fake",
                "model": "fixture-v1",
                "api_key_env": None,
                "replay_file": None,
            },
            "case_files": ["missing/cases.yaml"],
            "arms": ["baseline"],
            "repetitions": 1,
            "arm_order_seed": 0,
            "generation": {"max_output_tokens": 128, "temperature": None},
            "retry": {"max_transient_retries": 0, "timeout_seconds": 5.0},
        }
    else:
        document = source_manifest_v2_payload()
        document["provider"] = {
            "kind": "fake",
            "model": "fixture-v1",
            "api_key_env": None,
            "replay_file": None,
        }
        document["case_files"] = ["missing/cases.yaml"]
        capsule = document["capsule"]
        assert isinstance(capsule, dict)
        datasets = capsule["datasets"]
        assert isinstance(datasets, list)
        capsule["datasets"] = [datasets[0] | {"case_file_ordinals": [0]}]
        capsule["comparisons"] = []
        capsule["protocol_bindings"] = []
    if hostile_kind == "depth":
        nested: object = "leaf"
        for _ in range(RESOURCE_LIMITS_V1.nesting_depth + 1):
            nested = [nested]
        document["unexpected_deep_value"] = nested
    elif hostile_kind == "collection":
        document["case_files"] = [
            f"cases/{ordinal:05d}.yaml" for ordinal in range(RESOURCE_LIMITS_V1.case_records + 1)
        ]
    source = yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
    if hostile_kind == "anchor":
        source = source.replace("provider:\n", "provider: &provider_defaults\n", 1)
    elif hostile_kind == "merge":
        original = (
            "provider:\n"
            "  kind: fake\n"
            "  model: fixture-v1\n"
            "  api_key_env: null\n"
            "  replay_file: null\n"
        )
        merged = (
            "provider:\n"
            "  <<: &provider_defaults\n"
            "    kind: fake\n"
            "    model: fixture-v1\n"
            "  api_key_env: null\n"
            "  replay_file: null\n"
        )
        assert original in source
        source = source.replace(original, merged, 1)
    path = tmp_path / f"hostile-{hostile_kind}-source-v{schema_version}.yaml"
    path.write_text(source, encoding="utf-8")

    _assert_strict_source_manifest_rejection_before_capture_or_model(
        path,
        monkeypatch,
        capsys,
    )


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--input-root", "inputs"),
        ("--source-root", "source"),
        ("--container-image-digest", f"sha256:{'9' * 64}"),
        ("--force", None),
    ],
)
def test_legacy_run_rejects_capsule_only_options_before_dispatch(
    option: str,
    value: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("capsule-only argument reached legacy run")

    monkeypatch.setattr(cli, "_run", forbidden)
    argv = ["run", "manifest.yaml", "--results-root", "results", option]
    if value is not None:
        argv.append(value)

    assert main(argv, program="laconian") == 2
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert "unrecognized arguments" in captured.err


@pytest.mark.parametrize(
    "invalid_path",
    ["/absolute/cases.yaml", "../escape.yaml", "cases\\windows.yaml", "cases//x.yaml"],
)
def test_validate_v2_enforces_path_grammar_without_opening_the_declared_path(
    invalid_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = source_manifest_v2_payload()
    document["case_files"] = [invalid_path]
    capsule = document["capsule"]
    assert isinstance(capsule, dict)
    datasets = capsule["datasets"]
    assert isinstance(datasets, list)
    capsule["datasets"] = [datasets[0] | {"case_file_ordinals": [0]}]
    capsule["comparisons"] = []
    capsule["protocol_bindings"] = []
    path = tmp_path / "invalid-v2.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid locator was opened")

    monkeypatch.setattr(cli, "load_source_manifest_capture", forbidden, raising=False)
    monkeypatch.setattr(cli, "prepare_capsule", forbidden, raising=False)
    monkeypatch.setattr(cli, "FakeProvider", forbidden)
    monkeypatch.setattr(cli, "ReplayProvider", forbidden)
    monkeypatch.setattr(cli, "OpenAIProvider", forbidden)
    monkeypatch.setattr(cli, "os", _NoAmbientOs())

    assert main(["validate", str(path)], program="laconian") == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")


def test_validate_rejects_capsule_only_options_as_usage_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls = 0

    def forbidden(_path: Path) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(cli, "_validate", forbidden)

    assert main(["validate", "manifest.yaml", "--input-root", "inputs"], program="laconian") == 2
    captured = capsys.readouterr()
    assert calls == 0
    assert captured.out == ""
    assert "unrecognized arguments" in captured.err
