from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from yaml import YAMLError

from laconian_eval import __version__
from laconian_eval.arms import load_arms
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import canonical_json
from laconian_eval.capsule.capture import CaptureError, parse_source_manifest_bytes
from laconian_eval.capsule.execution import ProviderFactory, _resume_capsule
from laconian_eval.capsule.filesystem import (
    DestinationCollisionError,
    PostPublishSyncError,
    UnsupportedFilesystemError,
)
from laconian_eval.capsule.finalize import FinalizationError, _finalize_capsule
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.prepare import (
    PostPublishVerificationError,
    PreparationError,
    PreparedCapsule,
    PrepareRequest,
    prepare_capsule,
)
from laconian_eval.capsule.record_models import VerifyResultV1
from laconian_eval.capsule.verify import VerificationMode, verify_capsule
from laconian_eval.cases import (
    load_activation_cases,
    load_manifest,
    load_response_cases,
)
from laconian_eval.judging import attach_judgments, load_judgments
from laconian_eval.models import RunManifest, RunSummary, ScoredAttempt
from laconian_eval.providers import FakeProvider, Provider, ProviderError, ReplayProvider
from laconian_eval.providers.openai import OpenAIProvider
from laconian_eval.reporting import summarize, write_markdown_report, write_summary_json
from laconian_eval.runner import (
    load_raw_attempts,
    manifest_sha256,
    run_to_jsonl,
    validate_complete_run,
)
from laconian_eval.scoring import (
    load_scored_jsonl,
    score_terminal_attempts,
    write_scored_jsonl,
)
from laconian_eval.yaml_io import (
    StrictYamlError,
    bounded_yaml_discriminator,
    safe_load_unique,
    safe_load_unique_bytes,
)


class _RunFailure(RuntimeError):
    pass


_CONTAINER_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laconian", allow_abbrev=False)
    parser.add_argument("--version", action="version", version=f"laconian {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate", help="validate a manifest or case YAML", allow_abbrev=False
    )
    validate.add_argument("path", type=Path)

    plan = commands.add_parser(
        "plan", help="prepare a provider-free generation capsule", allow_abbrev=False
    )
    plan.add_argument("manifest", type=Path)
    plan.add_argument("--results-root", type=Path, required=True)
    plan.add_argument("--input-root", type=Path)
    plan.add_argument("--source-root", type=Path)
    plan.add_argument("--container-image-digest")

    verify = commands.add_parser(
        "verify", help="verify a prepared generation capsule", allow_abbrev=False
    )
    verify.add_argument("capsule", type=Path)
    verify.add_argument("--require", choices=("generation-complete", "sealed"))

    resume = commands.add_parser(
        "resume", help="resume a prepared generation capsule", allow_abbrev=False
    )
    resume.add_argument("capsule", type=Path)

    finalize = commands.add_parser("finalize", help="seal a generation capsule", allow_abbrev=False)
    finalize.add_argument("capsule", type=Path)
    finalize.add_argument("--seal-incomplete", action="store_true")

    run = commands.add_parser("run", help="execute a benchmark manifest", allow_abbrev=False)
    run.add_argument("manifest", type=Path)
    run.add_argument("--results-root", type=Path, required=True)

    score = commands.add_parser("score", help="score terminal raw attempts", allow_abbrev=False)
    score.add_argument("raw_jsonl", type=Path)
    score.add_argument("--cases", type=Path, required=True)
    score.add_argument("--judgments", type=Path)
    score.add_argument("--output", type=Path, required=True)

    report = commands.add_parser(
        "report", help="render a scored benchmark report", allow_abbrev=False
    )
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


def _read_validation_bytes(path: Path, *, limit: int) -> tuple[bytes, bool]:
    name = path.name
    if not name or name in {".", ".."}:
        raise ValueError("unable to read YAML")
    try:
        parent_fd = open_directory_no_follow(path.parent)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("unable to read YAML") from None
    descriptor: int | None = None
    result: tuple[bytes, bool] | None = None
    primary: BaseException | None = None
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("unable to read YAML")
        chunks: list[bytes] = []
        total = 0
        while total <= limit:
            requested = min(64 * 1024, limit + 1 - total)
            chunk = os.read(descriptor, requested)
            if not chunk:
                result = (b"".join(chunks), True)
                break
            chunks.append(chunk)
            total += len(chunk)
        if result is None:
            result = (b"".join(chunks), False)
    except BaseException as error:
        primary = error

    for owned_fd in (descriptor, parent_fd):
        if owned_fd is None:
            continue
        try:
            os.close(owned_fd)
        except BaseException as error:
            if primary is None:
                primary = error
    if primary is not None:
        if isinstance(primary, (OSError, RuntimeError, TypeError, ValueError)):
            raise ValueError("unable to read YAML") from None
        raise primary.with_traceback(primary.__traceback__)
    assert result is not None
    return result


def _strict_validation_mapping(
    data: bytes,
    *,
    byte_limit: int,
) -> Mapping[object, object]:
    try:
        loaded = safe_load_unique_bytes(
            data,
            byte_limit=byte_limit,
            collection_limit=RESOURCE_LIMITS_V1.case_records,
            collection_code="validation_collection_limit",
            top_level_sequence_limits={
                "case_files": (RESOURCE_LIMITS_V1.case_records, "case_records_limit")
            },
        )
    except ResourceLimitError:
        raise ValueError("invalid YAML") from None
    except StrictYamlError as error:
        raise ValueError(error.code.replace("_", " ")) from None
    if not isinstance(loaded, Mapping) or any(type(key) is not str for key in loaded):
        raise ValueError("YAML root must be a mapping")
    return loaded


def _yaml_document_kind(data: bytes) -> str | None:
    try:
        return bounded_yaml_discriminator(data)
    except (ResourceLimitError, StrictYamlError):
        return None


def _stream_validation_kind(path: Path) -> str | None:
    name = path.name
    if not name or name in {".", ".."}:
        raise ValueError("unable to read YAML")
    try:
        parent_fd = open_directory_no_follow(path.parent)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("unable to read YAML") from None
    descriptor: int | None = None
    primary: BaseException | None = None
    detected: str | None = None

    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("unable to read YAML")

        class DescriptorStream:
            def __init__(self, owned_descriptor: int) -> None:
                self.descriptor = owned_descriptor
                self.total = 0

            def read(self, size: int = -1) -> bytes:
                if size == 0:
                    return b""
                remaining = RESOURCE_LIMITS_V1.case_file_bytes + 1 - self.total
                if remaining <= 0:
                    raise ResourceLimitError("case_file_limit")
                requested = min(64 * 1024 if size < 0 else max(size, 1), remaining)
                while True:
                    try:
                        chunk = os.read(self.descriptor, requested)
                        break
                    except InterruptedError:
                        continue
                self.total += len(chunk)
                if self.total > RESOURCE_LIMITS_V1.case_file_bytes:
                    raise ResourceLimitError("case_file_limit")
                return chunk

        detected = bounded_yaml_discriminator(DescriptorStream(descriptor))
    except BaseException as error:
        primary = error

    for owned_fd in (descriptor, parent_fd):
        if owned_fd is None:
            continue
        try:
            os.close(owned_fd)
        except BaseException as error:
            if primary is None:
                primary = error
    if primary is not None:
        if isinstance(primary, (OSError, RuntimeError, TypeError, ValueError)):
            raise ValueError("unable to read YAML") from None
        raise primary.with_traceback(primary.__traceback__)
    return detected


def _validate(path: Path) -> None:
    source_limit = RESOURCE_LIMITS_V1.source_manifest_bytes
    prefix, complete = _read_validation_bytes(path, limit=source_limit)
    detected = _yaml_document_kind(prefix)
    loaded: Mapping[object, object]
    if not complete and detected == "source":
        raise ValueError("source manifest exceeds its resource limit")
    if not complete:
        detected = _stream_validation_kind(path)
        if detected == "source":
            raise ValueError("source manifest exceeds its resource limit")
        if detected is None:
            raise ValueError("invalid YAML")
        loaded = {"kind": detected}
    elif complete:
        loaded = _strict_validation_mapping(prefix, byte_limit=source_limit)
    else:
        assert detected is not None
        loaded = {"kind": detected}
    kind = loaded.get("kind")
    if kind == "response":
        load_response_cases((path,))
    elif kind == "activation":
        load_activation_cases((path,))
    elif (
        kind is None
        and loaded.get("schema_version") in {"1", "2"}
        and "provider" in loaded
        and "case_files" in loaded
    ):
        if not complete:
            raise ValueError("source manifest exceeds its resource limit")
        try:
            parse_source_manifest_bytes(prefix)
        except (CaptureError, ResourceLimitError):
            raise ValueError("invalid source manifest") from None
    else:
        raise ValueError(f"{path}: unsupported YAML kind")
    print(f"valid: {path}")


def _plan_summary(prepared: PreparedCapsule) -> dict[str, object]:
    capsule = prepared.capsule
    summary = prepared.summary
    return {
        "arms": summary.arm_count,
        "cases": summary.case_count,
        "claim_intent": capsule.claim_intent,
        "cost": "n/a",
        "hashes": {
            "case_index_sha256": capsule.case_index_sha256,
            "environment_sha256": capsule.environment_sha256,
            "input_index_sha256": capsule.input_index_sha256,
            "manifest_sha256": capsule.manifest_sha256,
            "plan_sha256": capsule.plan_sha256,
            "runner_source_sha256": capsule.runner_source_sha256,
            "source_manifest_commitment_sha256": (capsule.source_manifest_commitment_sha256),
        },
        "locales": dict(summary.locale_case_counts),
        "operational_disclosures": {
            "checkout_binding": summary.checkout_binding,
            "container_image_digest": summary.container_image_digest,
            "filesystem_class": summary.filesystem_class,
            "git_state": summary.git_state,
            "provider_kind": summary.provider_kind,
            "transport_policy": summary.transport_policy,
            "uv_lock_availability": summary.uv_lock_availability,
            "verification_warnings": list(summary.verification_warnings),
        },
        "planned_requests": summary.planned_request_count,
        "repetitions": summary.repetition_count,
        "run_purpose": capsule.run_purpose,
        "scenarios": summary.scenario_count,
    }


def _plan(
    manifest: Path,
    results_root: Path,
    *,
    input_root: Path | None,
    source_root: Path | None,
    container_image_digest: str | None,
) -> None:
    if (
        container_image_digest is not None
        and _CONTAINER_DIGEST.fullmatch(container_image_digest) is None
    ):
        raise ValueError("invalid container image digest")
    prepared = prepare_capsule(
        PrepareRequest(
            manifest_path=manifest,
            results_root=results_root,
            invocation_cwd=Path.cwd(),
            input_root=input_root,
            source_root=source_root,
            container_image_digest=container_image_digest,
        )
    )
    print(prepared.path)
    sys.stderr.write(canonical_json(_plan_summary(prepared)).decode("utf-8") + "\n")


def _requirement_met(result: VerifyResultV1, requirement: str | None) -> bool:
    if result.status != "valid":
        return False
    if requirement is None:
        return True
    if requirement == "sealed":
        return result.state in {"SEALED_COMPLETE", "SEALED_BLOCKED"}
    if requirement == "generation-complete":
        return result.state in {"GENERATION_COMPLETE", "SEALED_COMPLETE"} or (
            result.state == "SEALING_INTERRUPTED"
            and not result.missing_plan_item_ids
            and not result.operational_blocker_codes
        )
    raise AssertionError("unknown verification requirement")


def _verify(path: Path, *, requirement: str | None) -> int:
    result = verify_capsule(path, mode=VerificationMode.PREPARED)
    sys.stdout.write(canonical_json(result.model_dump(mode="json")).decode("utf-8") + "\n")
    return 0 if _requirement_met(result, requirement) else 2


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
        return FakeProvider({}), ()

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
        message = _redact(str(exc), secret_values)
        log = (
            f"run_id={run_directory.name}\n"
            f"manifest_sha256={manifest_sha256(manifest)}\n"
            "status=incomplete\n"
            "failure_kind=run_failure\n"
            f"failure_message={json.dumps(message, ensure_ascii=False)}\n"
        )
        _exclusive_text(run_directory / "run.log", log)
        raise _RunFailure(message) from exc

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


def _preflight_score_output(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"{output}: refuse to overwrite existing output")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as input_file:
        os.fsync(input_file.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_identity(path: Path) -> tuple[int, int]:
    metadata = path.lstat()
    return metadata.st_dev, metadata.st_ino


def _has_identity(path: Path, identity: tuple[int, int]) -> bool:
    try:
        return _path_identity(path) == identity
    except OSError:
        return False


def _cleanup_score_reservation(
    output: Path,
    reservation_identity: tuple[int, int],
    published_files: Sequence[tuple[Path, tuple[int, int]]],
) -> None:
    for path, identity in reversed(published_files):
        if _has_identity(path, identity):
            with suppress(OSError):
                path.unlink()
    if _has_identity(output, reservation_identity):
        with suppress(OSError):
            output.rmdir()


def _publish_score_output(
    scored: Sequence[ScoredAttempt],
    summary: RunSummary,
    output: Path,
) -> None:
    _preflight_score_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.tmp-",
            dir=output.parent,
        )
    )
    reservation_identity: tuple[int, int] | None = None
    published_files: list[tuple[Path, tuple[int, int]]] = []
    published = False
    try:
        scored_path = staging / "scored.jsonl"
        summary_path = staging / "summary.json"
        write_scored_jsonl(scored, scored_path)
        write_summary_json(summary, summary_path)
        _fsync_file(scored_path)
        _fsync_file(summary_path)
        _fsync_directory(staging)
        _preflight_score_output(output)
        try:
            output.mkdir()
        except FileExistsError as exc:
            raise FileExistsError(f"{output}: refuse to overwrite existing output") from exc
        reservation_identity = _path_identity(output)
        for staged_path in (scored_path, summary_path):
            destination = output / staged_path.name
            staged_identity = _path_identity(staged_path)
            staged_path.rename(destination)
            published_files.append((destination, staged_identity))
        _fsync_directory(output)
        _fsync_directory(output.parent)
        published = True
    finally:
        if not published and reservation_identity is not None:
            _cleanup_score_reservation(output, reservation_identity, published_files)
        if staging.exists():
            shutil.rmtree(staging)


def _score(
    raw_path: Path,
    cases_path: Path,
    judgments_path: Path | None,
    output: Path,
) -> None:
    _preflight_score_output(output)
    raw = load_raw_attempts(raw_path)
    manifest_path = raw_path.parent / "manifest.json"
    manifest = _load_manifest_json(manifest_path)
    manifest_cases = load_response_cases(
        tuple(_declared_path(value) for value in manifest.case_files)
    )
    selected_cases = load_response_cases((cases_path,))
    manifest_case_map = {case.id: case for case in manifest_cases}
    selected_case_map = {case.id: case for case in selected_cases}
    if selected_case_map != manifest_case_map:
        raise ValueError("--cases case definitions differ from manifest-declared cases")
    arms = load_arms(Path.cwd(), manifest.arms)
    validate_complete_run(
        manifest=manifest,
        cases=manifest_cases,
        arms=arms,
        attempts=raw,
        path=raw_path,
        run_id=raw_path.parent.name,
    )

    scored = score_terminal_attempts(selected_case_map, raw)
    require_semantic = judgments_path is not None
    if judgments_path is not None:
        scored = attach_judgments(scored, load_judgments(judgments_path))
    summary = summarize(
        scored,
        require_semantic=require_semantic,
        price_snapshot=manifest.price_snapshot,
    )
    _publish_score_output(scored, summary, output)
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


def _resume(path: Path) -> int:
    target = Path(os.path.abspath(os.fspath(path)))
    announced = False

    def announce(known: Path) -> None:
        nonlocal announced
        if announced:
            return
        announced = True
        print(known, flush=True)

    outcome = _resume_capsule(
        target,
        provider_factory=ProviderFactory(),
        on_target_known=announce,
        seams=None,
    )
    return outcome.exit_code


def _finalize(path: Path, *, seal_incomplete: bool) -> int:
    target = Path(os.path.abspath(os.fspath(path)))
    announced = False

    def announce(known: Path) -> None:
        nonlocal announced
        if announced:
            return
        announced = True
        print(known, flush=True)

    try:
        _finalize_capsule(
            target,
            seal_incomplete=seal_incomplete,
            on_target_known=announce,
            seams=None,
        )
    except FinalizationError as exc:
        if exc.code == "post_publish_fsync_failed":
            print(f"finalize failed: {exc}", file=sys.stderr)
            return 1
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def main(argv: Sequence[str] | None = None, *, program: str | None = None) -> int:
    effective_program = program or Path(sys.argv[0]).name
    if effective_program == "laconian-benchmark":
        from laconian_eval.replay.benchmark import run

        return run(argv)
    if effective_program != "laconian":
        sys.stderr.write(
            canonical_json({"code": "usage", "command": None, "status": "error"}).decode() + "\n"
        )
        return 2
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return cast(int, exc.code)

    command = cast(str, args.command)
    try:
        if command == "validate":
            _validate(cast(Path, args.path))
        elif command == "plan":
            _plan(
                cast(Path, args.manifest),
                cast(Path, args.results_root),
                input_root=cast(Path | None, args.input_root),
                source_root=cast(Path | None, args.source_root),
                container_image_digest=cast(str | None, args.container_image_digest),
            )
        elif command == "verify":
            return _verify(
                cast(Path, args.capsule),
                requirement=cast(str | None, args.require),
            )
        elif command == "resume":
            return _resume(cast(Path, args.capsule))
        elif command == "finalize":
            return _finalize(
                cast(Path, args.capsule),
                seal_incomplete=cast(bool, args.seal_incomplete),
            )
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
    except (PostPublishSyncError, PostPublishVerificationError) as exc:
        if exc.publication_path is not None:
            print(exc.publication_path)
        print(f"plan failed: {exc}", file=sys.stderr)
        return 1
    except _RunFailure as exc:
        print(f"run failed: {exc}", file=sys.stderr)
        return 1
    except (DestinationCollisionError, PreparationError, UnsupportedFilesystemError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
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
