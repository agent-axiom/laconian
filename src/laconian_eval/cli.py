from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from yaml import YAMLError

from laconian_eval import __version__
from laconian_eval.arms import load_arms
from laconian_eval.cases import (
    load_activation_cases,
    load_manifest,
    load_response_cases,
)
from laconian_eval.judging import attach_judgments, load_judgments
from laconian_eval.models import RawAttempt, RunManifest, RunSummary
from laconian_eval.providers import Provider, ProviderError, ReplayProvider
from laconian_eval.providers.openai import OpenAIProvider
from laconian_eval.reporting import summarize, write_markdown_report, write_summary_json
from laconian_eval.runner import load_raw_attempts, manifest_sha256, run_to_jsonl
from laconian_eval.scoring import (
    load_scored_jsonl,
    score_terminal_attempts,
    write_scored_jsonl,
)
from laconian_eval.yaml_io import safe_load_unique


class _RunFailure(RuntimeError):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laconian")
    parser.add_argument("--version", action="version", version=f"laconian {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a manifest or case YAML")
    validate.add_argument("path", type=Path)

    run = commands.add_parser("run", help="execute a benchmark manifest")
    run.add_argument("manifest", type=Path)
    run.add_argument("--results-root", type=Path, required=True)

    score = commands.add_parser("score", help="score terminal raw attempts")
    score.add_argument("raw_jsonl", type=Path)
    score.add_argument("--cases", type=Path, required=True)
    score.add_argument("--judgments", type=Path)
    score.add_argument("--output", type=Path, required=True)

    report = commands.add_parser("report", help="render a scored benchmark report")
    report.add_argument("scored_jsonl", type=Path)
    report.add_argument("--output", type=Path, required=True)
    return parser


def _strict_mapping(path: Path, *, label: str) -> Mapping[object, object]:
    try:
        loaded = safe_load_unique(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, YAMLError) as exc:
        raise ValueError(f"{path}: unable to read {label}: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError(f"{path}: {label} root must be a mapping")
    return loaded


def _validate(path: Path) -> None:
    loaded = _strict_mapping(path, label="YAML")
    kind = loaded.get("kind")
    if kind == "response":
        load_response_cases((path,))
    elif kind == "activation":
        load_activation_cases((path,))
    elif kind is None and "provider" in loaded and "case_files" in loaded:
        load_manifest(path)
    else:
        raise ValueError(f"{path}: unsupported YAML kind")
    print(f"valid: {path}")


def _declared_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def _redact(message: str, secrets: Sequence[str]) -> str:
    redacted = message
    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _provider(manifest: RunManifest) -> tuple[Provider, tuple[str, ...]]:
    config = manifest.provider
    if config.kind == "replay":
        assert config.replay_file is not None
        return ReplayProvider.from_path(_declared_path(config.replay_file)), ()
    if config.kind == "fake":
        raise ValueError(
            "fake provider has no manifest script source; use the replay provider for CLI runs"
        )

    assert config.kind == "openai"
    assert config.api_key_env is not None
    api_key = os.environ.get(config.api_key_env)
    if api_key is None or not api_key.strip():
        raise ValueError(f"environment variable {config.api_key_env} must contain an API key")
    try:
        provider = OpenAIProvider(
            api_key=api_key,
            timeout_seconds=manifest.retry.timeout_seconds,
        )
    except ProviderError as exc:
        raise ValueError(_redact(exc.message, (api_key,))) from exc
    except Exception as exc:
        raise _RunFailure(_redact(str(exc), (api_key,))) from exc
    return provider, (api_key,)


def _exclusive_text(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"{path}: refuse to overwrite existing path")
    try:
        with path.open("x", encoding="utf-8") as output:
            output.write(content)
    except FileExistsError as exc:
        raise FileExistsError(f"{path}: refuse to overwrite existing path") from exc


def _canonical_manifest(manifest: RunManifest) -> str:
    return (
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _new_run_directory(results_root: Path, manifest: RunManifest) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    name = f"{timestamp}-{manifest.run_name}-{manifest_sha256(manifest)[:12]}"
    directory = results_root / name
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise FileExistsError(f"{directory}: refuse to overwrite existing run") from exc
    return directory


def _run(manifest_path: Path, results_root: Path) -> None:
    manifest = load_manifest(manifest_path)
    cases = load_response_cases(tuple(_declared_path(value) for value in manifest.case_files))
    arms = load_arms(Path.cwd(), manifest.arms)
    provider, secret_values = _provider(manifest)

    run_directory = _new_run_directory(results_root, manifest)
    _exclusive_text(run_directory / "manifest.json", _canonical_manifest(manifest))
    raw_path = run_directory / "raw.jsonl"
    _exclusive_text(raw_path, "")
    try:
        attempts = run_to_jsonl(
            manifest=manifest,
            cases=cases,
            arms=arms,
            provider=provider,
            output_path=raw_path,
            run_id=run_directory.name,
            secret_values=secret_values,
        )
    except Exception as exc:
        raise _RunFailure(_redact(str(exc), secret_values)) from exc

    terminal = sum(attempt.terminal for attempt in attempts)
    authentication_failure = next(
        (
            attempt
            for attempt in attempts
            if attempt.terminal
            and attempt.error is not None
            and attempt.error.kind == "authentication"
        ),
        None,
    )
    if authentication_failure is not None:
        log = (
            f"run_id={run_directory.name}\n"
            f"manifest_sha256={manifest_sha256(manifest)}\n"
            f"attempts={len(attempts)}\n"
            f"terminal_records={terminal}\n"
            "status=incomplete\n"
            "failure_kind=authentication\n"
        )
        _exclusive_text(run_directory / "run.log", log)
        raise _RunFailure(
            f"authentication error stopped run; inspect {run_directory / 'raw.jsonl'}"
        )
    log = (
        f"run_id={run_directory.name}\n"
        f"manifest_sha256={manifest_sha256(manifest)}\n"
        f"attempts={len(attempts)}\n"
        f"terminal_records={terminal}\n"
        "status=complete\n"
    )
    _exclusive_text(run_directory / "run.log", log)
    print(run_directory)


def _load_manifest_json(path: Path) -> RunManifest:
    loaded = _strict_mapping(path, label="manifest JSON")
    try:
        return RunManifest.model_validate(loaded)
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid manifest JSON: {exc}") from exc


def _load_summary_json(path: Path) -> RunSummary:
    loaded = _strict_mapping(path, label="summary JSON")
    try:
        return RunSummary.model_validate(loaded)
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid summary JSON: {exc}") from exc


def _preflight_score_outputs(output: Path) -> tuple[Path, Path]:
    scored_path = output / "scored.jsonl"
    summary_path = output / "summary.json"
    existing = [path for path in (scored_path, summary_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"refuse to overwrite existing output(s): {joined}")
    if output.exists() and not output.is_dir():
        raise ValueError(f"{output}: output must be a directory")
    return scored_path, summary_path


def _validate_raw_manifest_coherence(
    raw_path: Path,
    manifest: RunManifest,
    raw: Sequence[RawAttempt],
) -> None:
    for attempt in raw:
        if attempt.provider != manifest.provider.kind:
            raise ValueError(
                f"{raw_path}: raw provider {attempt.provider!r} conflicts with manifest"
            )
        if attempt.model != manifest.provider.model:
            raise ValueError(f"{raw_path}: raw model {attempt.model!r} conflicts with manifest")
        if attempt.arm not in manifest.arms:
            raise ValueError(f"{raw_path}: raw arm {attempt.arm!r} conflicts with manifest")
        if attempt.repetition >= manifest.repetitions:
            raise ValueError(
                f"{raw_path}: raw repetition {attempt.repetition} conflicts with manifest"
            )
    run_ids = {attempt.run_id for attempt in raw}
    if len(run_ids) > 1 or any(not run_id.strip() for run_id in run_ids):
        raise ValueError(f"{raw_path}: raw run_id values are not coherent")


def _score(
    raw_path: Path,
    cases_path: Path,
    judgments_path: Path | None,
    output: Path,
) -> None:
    scored_path, summary_path = _preflight_score_outputs(output)
    raw = load_raw_attempts(raw_path)
    manifest_path = raw_path.parent / "manifest.json"
    manifest = _load_manifest_json(manifest_path)
    expected_manifest_hash = manifest_sha256(manifest)
    if any(attempt.manifest_sha256 != expected_manifest_hash for attempt in raw):
        raise ValueError(f"{raw_path}: raw records do not match copied manifest.json")
    _validate_raw_manifest_coherence(raw_path, manifest, raw)

    cases = load_response_cases((cases_path,))
    scored = score_terminal_attempts({case.id: case for case in cases}, raw)
    require_semantic = judgments_path is not None
    if judgments_path is not None:
        scored = attach_judgments(scored, load_judgments(judgments_path))
    summary = summarize(
        scored,
        require_semantic=require_semantic,
        price_snapshot=manifest.price_snapshot,
    )
    write_scored_jsonl(scored, scored_path)
    write_summary_json(summary, summary_path)
    print(output)


def _report(scored_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"{output}: refuse to overwrite existing path")
    scored = load_scored_jsonl(scored_path)
    summary_path = scored_path.parent / "summary.json"
    if summary_path.exists():
        recorded = _load_summary_json(summary_path)
        recomputed = summarize(
            scored,
            require_semantic=recorded.quality_gate == "semantic",
            price_snapshot=recorded.price_snapshot,
        )
        if recorded != recomputed:
            raise ValueError(f"{summary_path}: summary does not correspond to scored data")
        summary = recorded
    else:
        summary = summarize(scored, require_semantic=False, price_snapshot=None)
    write_markdown_report(summary, output)
    print(output)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return cast(int, exc.code)

    command = cast(str, args.command)
    try:
        if command == "validate":
            _validate(cast(Path, args.path))
        elif command == "run":
            _run(cast(Path, args.manifest), cast(Path, args.results_root))
        elif command == "score":
            _score(
                cast(Path, args.raw_jsonl),
                cast(Path, args.cases),
                cast(Path | None, args.judgments),
                cast(Path, args.output),
            )
        elif command == "report":
            _report(cast(Path, args.scored_jsonl), cast(Path, args.output))
        else:
            raise AssertionError(f"unhandled command: {command}")
    except _RunFailure as exc:
        print(f"run failed: {exc}", file=sys.stderr)
        return 1
    except (FileExistsError, OSError, ProviderError, ValueError) as exc:
        message = exc.message if isinstance(exc, ProviderError) else str(exc)
        print(f"error: {message}", file=sys.stderr)
        return 2
    except Exception as exc:
        label = "run failed" if command == "run" else "command failed"
        print(f"{label}: {exc}", file=sys.stderr)
        return 1
    return 0


def entrypoint() -> None:
    raise SystemExit(main())
