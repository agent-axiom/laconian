"""Closed command boundary for offline non-evidentiary structural validation."""

from __future__ import annotations

import argparse
import errno
import os
import stat
import sys
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn, Self, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from laconian_eval.benchmark.context import (
    _open_retained_directory,
    _stable_regular_file_snapshot,
)
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.replay._inputs import Inputs, absolute, parse_model
from laconian_eval.replay._structure import (
    generation,
    hard_scores,
    judge_attempts,
    judge_requests,
    provider_graph,
)

COMMANDS = (
    "hard-score",
    "prepare-judge",
    "seal-judge",
    "sample-audit",
    "seal-audit",
    "analyze",
    "verify",
)
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VERIFICATION = 3
EXIT_OUTPUT_EXISTS = 4
EXIT_SOFTWARE = 70
NOTICE = (
    "OFFLINE NON-EVIDENTIARY VALIDATION ONLY; replay validates structure but cannot authorize "
    "live execution"
)
_GENERATION = ("generation-expectation", "generation-index", "generation-root")
_PROVIDER = (
    "generation-expectation",
    "provider-index",
    "generation-root",
    "hard-score-root",
    "judge-request-root",
    "judge-root",
)
OPTIONS = {
    "hard-score": (*_GENERATION, "output-root"),
    "prepare-judge": (*_GENERATION, "hard-score-root", "output-root"),
    "seal-judge": (
        *_GENERATION,
        "hard-score-root",
        "judge-request-root",
        "judge-attempt-root",
        "output-root",
    ),
    "sample-audit": (*_PROVIDER, "output-root"),
    "seal-audit": (*_PROVIDER, "review-root", "output-root"),
    "analyze": (*_PROVIDER, "audit-root", "output-root"),
    "verify": (*_PROVIDER, "result-root", "protocol-review-archive"),
}

_Command = Literal[
    "hard-score", "prepare-judge", "seal-judge", "sample-audit", "seal-audit", "analyze", "verify"
]
_Kind = Literal[
    "offline-hard-score-validation",
    "offline-prepare-judge-validation",
    "offline-seal-judge-validation",
    "offline-sample-audit-validation",
    "offline-seal-audit-validation",
    "offline-analyze-validation",
    "offline-verify-validation",
]
_Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class OfflineValidationReportV1(BaseModel):
    """Private ordinary report DATA, with no evidentiary or execution authority."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    schema_version: Literal["benchmark-offline-validation-report-v1"]
    command: _Command
    artifact_kind: _Kind
    generation_context_expectation_sha256: _Sha256
    ordered_input_sha256s: tuple[_Sha256, ...]
    status: Literal["structurally-valid-not-authorized"]
    offline_report_sha256: _Sha256

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.artifact_kind != f"offline-{self.command}-validation":
            raise ValueError("offline report kind rejected")
        if self.ordered_input_sha256s != tuple(sorted(self.ordered_input_sha256s)):
            raise ValueError("offline report inputs rejected")
        expected = stable_digest(
            "laconian-benchmark-offline-validation-report-v1",
            self.model_dump(mode="json", exclude={"offline_report_sha256"}),
        )
        if self.offline_report_sha256 != expected:
            raise ValueError("offline report digest rejected")
        return self


def _report(
    command: str, expectation_sha256: str, hashes: tuple[str, ...]
) -> OfflineValidationReportV1:
    payload = {
        "schema_version": "benchmark-offline-validation-report-v1",
        "command": command,
        "artifact_kind": f"offline-{command}-validation",
        "generation_context_expectation_sha256": expectation_sha256,
        "ordered_input_sha256s": hashes,
        "status": "structurally-valid-not-authorized",
    }
    payload["offline_report_sha256"] = stable_digest(
        "laconian-benchmark-offline-validation-report-v1", payload
    )
    return OfflineValidationReportV1.model_validate(payload)


def _absent_output(path: Path) -> None:
    target = absolute(path)
    descriptor, _ = _open_retained_directory(target.parent)
    try:
        try:
            os.stat(target.name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise FileExistsError
    finally:
        os.close(descriptor)


def _parent_recheck(path: Path, parent: int) -> None:
    probe, _ = _open_retained_directory(path)
    try:
        before, after = os.fstat(parent), os.fstat(probe)
        if (before.st_dev, before.st_ino, before.st_mode) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
        ):
            raise ValueError("offline output parent changed")
    finally:
        os.close(probe)


@contextmanager
def _publish_report(path: Path, report: OfflineValidationReportV1, inputs: Inputs) -> Iterator[str]:
    target = absolute(path)
    parent, _ = _open_retained_directory(target.parent)
    stage_name = f".offline-{uuid4().hex}.tmp"
    stage: int | None = None
    owned_name = stage_name
    stage_identity: tuple[int, int] | None = None
    file_identity: tuple[int, int] | None = None
    raw = canonical_json(report.model_dump(mode="json")) + b"\n"
    try:
        os.mkdir(stage_name, 0o700, dir_fd=parent)
        metadata = os.stat(stage_name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("offline stage identity rejected")
        stage_identity = (metadata.st_dev, metadata.st_ino)
        stage = os.open(stage_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        metadata = os.fstat(stage)
        if (metadata.st_dev, metadata.st_ino) != stage_identity:
            raise ValueError("offline stage identity changed")
        descriptor = os.open(
            "offline-non-evidentiary.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=stage,
        )
        try:
            file_metadata = os.fstat(descriptor)
            file_identity = (file_metadata.st_dev, file_metadata.st_ino)
            cursor = 0
            while cursor < len(raw):
                written = os.write(descriptor, raw[cursor:])
                if written <= 0:
                    raise OSError("offline report write failed")
                cursor += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        fresh_raw, _ = _stable_regular_file_snapshot(stage, "offline-non-evidentiary.json")
        fresh = parse_model(fresh_raw, OfflineValidationReportV1)
        if fresh_raw != raw or fresh != report:
            raise ValueError("offline report reload rejected")
        os.fsync(stage)
        inputs.recheck()
        _parent_recheck(target.parent, parent)
        PosixOps().rename_noreplace(parent, stage_name, parent, target.name)
        owned_name = target.name
        installed = os.stat(target.name, dir_fd=parent, follow_symlinks=False)
        if (installed.st_dev, installed.st_ino) != stage_identity:
            raise ValueError("offline report installation changed")
        fresh_raw, _ = _stable_regular_file_snapshot(stage, "offline-non-evidentiary.json")
        fresh = parse_model(fresh_raw, OfflineValidationReportV1)
        if fresh_raw != raw or fresh != report:
            raise ValueError("offline report reload rejected")
        inputs.recheck()
        os.fsync(parent)
        _parent_recheck(target.parent, parent)
        # Keep rollback ownership while the caller runs the final input witness
        # recheck and closes input descriptors. Any failure returns through here.
        yield fresh.offline_report_sha256
        _parent_recheck(target.parent, parent)
    except BaseException:
        if stage_identity is not None:
            visible = os.stat(owned_name, dir_fd=parent, follow_symlinks=False)
            if (visible.st_dev, visible.st_ino) == stage_identity and stat.S_ISDIR(visible.st_mode):
                if stage is None:
                    # mkdir succeeded but descriptor acquisition did not. Only
                    # remove this exact owned directory if it is still empty;
                    # never traverse or remove any unexpected contents.
                    try:
                        os.rmdir(owned_name, dir_fd=parent)
                    except OSError as cleanup_error:
                        if cleanup_error.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                            raise
                    raise
                names = os.listdir(stage)
                if names in ([], ["offline-non-evidentiary.json"]):
                    if names:
                        metadata = os.stat(names[0], dir_fd=stage, follow_symlinks=False)
                        if (
                            not stat.S_ISREG(metadata.st_mode)
                            or metadata.st_nlink != 1
                            or (metadata.st_dev, metadata.st_ino) != file_identity
                        ):
                            raise ValueError("offline owned cleanup rejected") from None
                        os.unlink(names[0], dir_fd=stage)
                    os.rmdir(owned_name, dir_fd=parent)
        raise
    finally:
        if stage is not None:
            os.close(stage)
        os.close(parent)


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _UsageError

    def parse_args(
        self,
        args: Sequence[str] | None = None,
        namespace: Any = None,
    ) -> Any:
        values = list(sys.argv[1:] if args is None else args)
        if self.prog == "laconian-benchmark":
            _closed_arguments(values)
        return super().parse_args(values, namespace)


def _closed_arguments(values: Sequence[str]) -> None:
    if values in (["--help"], ["-h"]):
        return
    if not values or values[0] not in COMMANDS or any(type(value) is not str for value in values):
        raise _UsageError
    allowed = {"--" + name for name in OPTIONS[values[0]]}
    seen: set[str] = set()
    cursor = 1
    while cursor < len(values):
        token = values[cursor]
        if token in {"-h", "--help"}:
            cursor += 1
            continue
        option, separator, _value = token.partition("=")
        if option not in allowed or option in seen:
            raise _UsageError
        seen.add(option)
        if not separator:
            cursor += 1
            if cursor >= len(values) or values[cursor].startswith("--"):
                raise _UsageError
        cursor += 1


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="laconian-benchmark", description=NOTICE, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparser = commands.add_parser(
            command, description=NOTICE, help=NOTICE, allow_abbrev=False
        )
        for option in OPTIONS[command]:
            help_text = (
                "offline report only; never later-stage input"
                if option == "output-root"
                else "explicit existing offline input"
            )
            subparser.add_argument("--" + option, type=Path, required=True, help=help_text)
    return parser


def _error(code: str, command: str | None, status: int) -> int:
    sys.stderr.write(
        canonical_json({"code": code, "command": command, "status": "error"}).decode() + "\n"
    )
    return status


def run(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    command = values[0] if values and values[0] in COMMANDS else None
    try:
        args = build_parser().parse_args(values)
    except _UsageError:
        return _error("usage", command, EXIT_USAGE)
    except SystemExit as error:
        return int(error.code or 0)
    try:
        if command != "verify":
            _absent_output(args.output_root)
        with ExitStack() as publication, Inputs() as inputs:
            graph = generation(
                inputs,
                args.generation_expectation,
                args.generation_index
                if command in COMMANDS[:3]
                else args.generation_root / "generation-context.json",
                args.generation_root,
            )
            if command != "hard-score":
                hard_scores(inputs, graph, args.hard_score_root)
            if command not in COMMANDS[:2]:
                judge_requests(inputs, graph, args.judge_request_root)
            if command == "seal-judge":
                judge_attempts(inputs, graph, args.judge_attempt_root)
            if command in COMMANDS[3:]:
                provider_graph(inputs, graph, args.provider_index, args.judge_root)
            if command in COMMANDS[4:]:
                from laconian_eval.replay._audit import validate_audit

                audit_root = (
                    args.review_root
                    if command == "seal-audit"
                    else args.audit_root
                    if command == "analyze"
                    else args.result_root
                )
                audit_tree = inputs.tree(audit_root)
                if command == "analyze" and any(
                    not name.startswith("audit/") for name in audit_tree.members
                ):
                    raise ValueError("offline audit root rejected")
                audit = validate_audit(audit_tree, graph, complete=command != "seal-audit")
                if command in {"analyze", "verify"}:
                    from laconian_eval.replay._statistics import validate_statistical_inputs

                    validate_statistical_inputs(audit, graph)
                if command == "verify":
                    from laconian_eval.replay._statistics import validate_analysis

                    validate_analysis(audit_tree, audit, graph)
            if command == "verify":
                from laconian_eval.replay._protocol import validate_protocol_archive

                protocol_review_archive = inputs.file(args.protocol_review_archive)
                validate_protocol_archive(protocol_review_archive, graph.context)
            report = _report(
                cast(str, command),
                graph.expectation.generation_context_expectation_sha256,
                inputs.ordered_hashes(),
            )
            if command != "verify":
                inputs.reject_output_overlap(args.output_root)
                digest = publication.enter_context(
                    _publish_report(args.output_root, report, inputs)
                )
            else:
                digest = report.offline_report_sha256
        sys.stdout.write(
            canonical_json(
                {
                    "artifact_count": 1,
                    "artifact_kind": report.artifact_kind,
                    "artifact_sha256": digest,
                    "command": command,
                    "status": "ok",
                }
            ).decode()
            + "\n"
        )
        return EXIT_OK
    except FileExistsError:
        return _error("output-exists", command, EXIT_OUTPUT_EXISTS)
    except (ValueError, OSError, LookupError):
        return _error("verification-failed", command, EXIT_VERIFICATION)
    except Exception:
        return _error("software-error", command, EXIT_SOFTWARE)
