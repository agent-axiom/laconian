"""Crash-safe generation-capsule finalization tests."""

from __future__ import annotations

import fcntl
import inspect
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Any, cast
from uuid import UUID

import pytest

import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.finalize as finalize_module
import laconian_eval.capsule.verify as verify_module
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import sha256_bytes
from laconian_eval.capsule.execution import ProviderFactory
from laconian_eval.capsule.finalize import FinalizationError, finalize_capsule
from laconian_eval.capsule.seal_models import SealV1
from laconian_eval.providers import GenerationResult, ProviderError

from .test_execution import (
    _install_fast_runtime,
    _ScriptedProvider,
    _seams_for_provider,
    _single_plan_capsule,
)

_FINALIZE_OPERATION = UUID("b23e4567-e89b-42d3-a456-426614174030")
_SEAL_TRANSACTION = UUID("c23e4567-e89b-42d3-a456-426614174031")
_RETRY_OPERATION = UUID("d23e4567-e89b-42d3-a456-426614174032")
_FINALIZE_TIME = datetime(2026, 8, 30, 13, 0, tzinfo=UTC)


@pytest.fixture
def prepared_capsule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _single_plan_capsule(tmp_path, monkeypatch)


@pytest.fixture
def complete_capsule(prepared_capsule: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _install_fast_runtime(monkeypatch)
    result = GenerationResult(output_text="complete", response_model="returned-v1")
    outcome = execution_module._resume_capsule(
        prepared_capsule,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(_ScriptedProvider([result, result])),
    )
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    return prepared_capsule


def test_finalize_complete_capsule_publishes_one_deterministic_seal(
    complete_capsule: Path,
) -> None:
    result = finalize_capsule(complete_capsule)
    seal_data = (complete_capsule / "seal.json").read_bytes()
    seal = SealV1.model_validate_json(seal_data)

    assert result.state == "SEALED_COMPLETE"
    assert result.capsule_sha256 == sha256_bytes(seal_data)
    assert seal.generation_status == "complete"
    assert seal.missing_plan_item_ids == ()
    assert seal.operational_blocker_codes == ()


def test_finalize_incomplete_requires_explicit_flag(prepared_capsule: Path) -> None:
    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(prepared_capsule)

    assert caught.value.code == "incomplete_requires_flag"
    assert not (prepared_capsule / "seal.json").exists()

    result = finalize_capsule(prepared_capsule, seal_incomplete=True)

    assert result.state == "SEALED_BLOCKED"


def _event_rows(capsule: Path) -> list[dict[str, object]]:
    return [json.loads(row) for row in (capsule / "events.jsonl").read_bytes().splitlines()]


def _seal_request(capsule: Path) -> dict[str, object]:
    requests = [row for row in _event_rows(capsule) if row["kind"] == "seal_requested"]
    assert len(requests) == 1
    return requests[0]


def _crash_seams(point: finalize_module.CrashPoint) -> finalize_module._FinalizeSeams:
    identifiers = iter((_FINALIZE_OPERATION, _SEAL_TRANSACTION))

    def checkpoint(observed: finalize_module.CrashPoint) -> None:
        if observed == point:
            raise OSError("diagnostic-CANARY")

    return finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
        checkpoint=checkpoint,
    )


@pytest.mark.parametrize(
    ("point", "expected_code", "expected_seal", "expected_temporary"),
    [
        ("after_seal_requested_fsync", "io_error", False, False),
        ("after_temporary_exclusive_creation", "io_error", False, True),
        ("during_temporary_write", "io_error", False, True),
        ("after_temporary_file_fsync", "io_error", False, True),
        ("after_link_noreplace", "post_publish_fsync_failed", True, True),
        ("after_temporary_unlink", "post_publish_fsync_failed", True, False),
        ("during_capsule_directory_fsync", "post_publish_fsync_failed", True, False),
    ],
)
def test_finalize_crash_boundaries_retry_one_committed_request_and_exact_seal(
    complete_capsule: Path,
    point: finalize_module.CrashPoint,
    expected_code: str,
    expected_seal: bool,
    expected_temporary: bool,
) -> None:
    sentinel = complete_capsule.parent / "unrelated-sentinel"
    sentinel.write_bytes(b"sentinel-evidence")

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            complete_capsule,
            seams=_crash_seams(point),
        )

    assert caught.value.code == expected_code
    assert str(caught.value) == "capsule finalization rejected"
    request = _seal_request(complete_capsule)
    payload = request["payload"]
    assert isinstance(payload, dict)
    temporary_name = f".seal.{payload['seal_transaction_id']}.tmp"
    residues = sorted(path.name for path in complete_capsule.glob(".seal.*.tmp"))
    assert (complete_capsule / "seal.json").exists() is expected_seal
    assert residues == ([temporary_name] if expected_temporary else [])
    if expected_seal and expected_temporary:
        assert (complete_capsule / "seal.json").stat().st_ino == (
            complete_capsule / temporary_name
        ).stat().st_ino
    seal_before_retry = (
        (complete_capsule / "seal.json").read_bytes()
        if (complete_capsule / "seal.json").is_file()
        else None
    )
    temporary_before_retry = (
        (complete_capsule / temporary_name).read_bytes()
        if (complete_capsule / temporary_name).is_file()
        else None
    )

    result = finalize_capsule(complete_capsule)
    final_bytes = (complete_capsule / "seal.json").read_bytes()

    assert result.state == "SEALED_COMPLETE"
    assert result.capsule_sha256 == sha256_bytes(final_bytes)
    assert (
        len([row for row in _event_rows(complete_capsule) if row["kind"] == "seal_requested"]) == 1
    )
    assert not list(complete_capsule.glob(".seal.*.tmp"))
    assert sentinel.read_bytes() == b"sentinel-evidence"
    if seal_before_retry is not None:
        assert seal_before_retry == final_bytes
    if point == "after_temporary_file_fsync":
        assert temporary_before_retry == final_bytes
    if point == "during_temporary_write":
        assert temporary_before_retry is not None
        assert 0 < len(temporary_before_retry) < len(final_bytes)


def test_ordinary_recovery_verifier_does_not_accept_finalization_artifacts(
    prepared_capsule: Path,
) -> None:
    temporary = prepared_capsule / ".seal.c23e4567-e89b-42d3-a456-426614174031.tmp"
    temporary.write_bytes(b"not-authorized-without-a-request")
    root_fd = open_directory_no_follow(prepared_capsule)
    parent_fd = open_directory_no_follow(prepared_capsule.parent)
    try:
        with pytest.raises(verify_module._Failure) as caught:
            verify_module._verify_recoverable_capsule_descriptors(
                root_fd,
                parent_fd=parent_fd,
                destination_name=prepared_capsule.name,
                reserved_operation_id=_RETRY_OPERATION,
            )
    finally:
        os.close(root_fd)
        os.close(parent_fd)

    assert caught.value.code == "unexpected_path"


def test_target_callback_waits_for_descriptor_verified_capsule(tmp_path: Path) -> None:
    announced: list[Path] = []

    with pytest.raises(FinalizationError):
        finalize_module._finalize_capsule(
            tmp_path,
            on_target_known=announced.append,
        )

    assert announced == []


def test_same_name_seal_replacement_after_link_is_rejected_without_temp_cleanup(
    complete_capsule: Path,
) -> None:
    temporary = complete_capsule / f".seal.{_SEAL_TRANSACTION}.tmp"
    replacement_bytes: bytes | None = None

    def checkpoint(point: finalize_module.CrashPoint) -> None:
        nonlocal replacement_bytes
        if point == "after_link_noreplace":
            seal = complete_capsule / "seal.json"
            replacement_bytes = seal.read_bytes()
            seal.unlink()
            seal.write_bytes(replacement_bytes)

    identifiers = iter((_FINALIZE_OPERATION, _SEAL_TRANSACTION))
    seams = finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
        checkpoint=checkpoint,
    )

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(complete_capsule, seams=seams)

    assert caught.value.code == "seal_mismatch"
    assert replacement_bytes is not None
    assert (complete_capsule / "seal.json").read_bytes() == replacement_bytes
    assert temporary.read_bytes() == replacement_bytes


def test_same_inode_temporary_rewrite_before_link_is_rejected_and_preserved(
    complete_capsule: Path,
) -> None:
    with pytest.raises(FinalizationError):
        finalize_module._finalize_capsule(
            complete_capsule,
            seams=_crash_seams("after_temporary_file_fsync"),
        )
    request = _seal_request(complete_capsule)
    payload = request["payload"]
    assert isinstance(payload, dict)
    temporary = complete_capsule / f".seal.{payload['seal_transaction_id']}.tmp"
    original = temporary.read_bytes()
    replacement = bytes([original[0] ^ 1]) + original[1:]

    def checkpoint(point: finalize_module.CrashPoint) -> None:
        if point == "after_temporary_file_fsync":
            with temporary.open("r+b", buffering=0) as stream:
                stream.write(replacement)
                stream.flush()
                os.fsync(stream.fileno())

    seams = finalize_module._FinalizeSeams(
        new_uuid=lambda: _RETRY_OPERATION,
        utc_now=lambda: _FINALIZE_TIME,
        checkpoint=checkpoint,
    )

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(complete_capsule, seams=seams)

    assert caught.value.code == "seal_mismatch"
    assert not (complete_capsule / "seal.json").exists()
    assert temporary.read_bytes() == replacement


def test_same_name_seal_replacement_during_directory_fsync_is_rejected(
    complete_capsule: Path,
) -> None:
    replacement_inode: int | None = None

    def checkpoint(point: finalize_module.CrashPoint) -> None:
        nonlocal replacement_inode
        if point == "during_capsule_directory_fsync":
            seal = complete_capsule / "seal.json"
            data = seal.read_bytes()
            seal.unlink()
            seal.write_bytes(data)
            replacement_inode = seal.stat().st_ino

    identifiers = iter((_FINALIZE_OPERATION, _SEAL_TRANSACTION))
    seams = finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
        checkpoint=checkpoint,
    )

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(complete_capsule, seams=seams)

    assert caught.value.code == "seal_mismatch"
    assert replacement_inode is not None
    assert (complete_capsule / "seal.json").stat().st_ino == replacement_inode


@pytest.mark.parametrize(
    ("history_kind", "expected_blocker"),
    [
        ("never-started", "never_started"),
        ("interrupted", "interrupted"),
        ("ambiguous", "ambiguous_inflight"),
        ("authentication", "authentication_stopped"),
    ],
)
def test_finalize_incomplete_lifecycle_matrix_adds_no_attempt_or_outcome(
    prepared_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
    history_kind: str,
    expected_blocker: str,
) -> None:
    provider = _ScriptedProvider([])
    if history_kind != "never-started":
        _install_fast_runtime(monkeypatch)
        if history_kind == "interrupted":
            seams = _seams_for_provider(
                provider,
                stop_before_attempt=lambda _row: "operator",
            )
        else:
            error = ProviderError(
                "authentication" if history_kind == "authentication" else "timeout",
                "content-free test failure",
                history_kind == "ambiguous",
                delivery_certainty=(
                    "definitely_rejected" if history_kind == "authentication" else "unknown"
                ),
                response_model="returned-v1",
            )
            provider = _ScriptedProvider([error])
            seams = _seams_for_provider(provider)
        outcome = execution_module._resume_capsule(
            prepared_capsule,
            provider_factory=ProviderFactory(),
            seams=seams,
        )
        assert outcome.exit_code == 1

    events_before = _event_rows(prepared_capsule)
    raw_before = (prepared_capsule / "raw.jsonl").read_bytes()
    request_count_before = sum(row["kind"] == "request_started" for row in events_before)
    finish_count_before = sum(row["kind"] == "request_finished" for row in events_before)
    plan_ids = tuple(
        sorted(
            (
                json.loads(row)["plan_item_id"]
                for row in (prepared_capsule / "plan.jsonl").read_bytes().splitlines()
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )

    result = finalize_capsule(prepared_capsule, seal_incomplete=True)
    seal = SealV1.model_validate_json((prepared_capsule / "seal.json").read_bytes())
    events_after = _event_rows(prepared_capsule)

    assert result.state == "SEALED_BLOCKED"
    assert seal.generation_status == "incomplete"
    assert seal.missing_plan_item_ids == plan_ids
    assert seal.operational_blocker_codes == (expected_blocker,)
    assert seal.never_started_detail == (
        "operator_abandoned" if history_kind == "never-started" else None
    )
    assert (prepared_capsule / "raw.jsonl").read_bytes() == raw_before
    assert events_after[:-1] == events_before
    assert events_after[-1]["kind"] == "seal_requested"
    assert sum(row["kind"] == "request_started" for row in events_after) == request_count_before
    assert sum(row["kind"] == "request_finished" for row in events_after) == finish_count_before
    if history_kind == "interrupted":
        assert provider.calls == []


def _interrupt_after_complete_temporary(capsule: Path) -> tuple[Path, bytes]:
    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            capsule,
            seams=_crash_seams("after_temporary_file_fsync"),
        )
    assert caught.value.code == "io_error"
    request = _seal_request(capsule)
    payload = request["payload"]
    assert isinstance(payload, dict)
    temporary = capsule / f".seal.{payload['seal_transaction_id']}.tmp"
    return temporary, temporary.read_bytes()


def _interrupt_after_seal_request(capsule: Path) -> Path:
    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            capsule,
            seams=_crash_seams("after_seal_requested_fsync"),
        )
    assert caught.value.code == "io_error"
    request = _seal_request(capsule)
    payload = request["payload"]
    assert isinstance(payload, dict)
    temporary = capsule / f".seal.{payload['seal_transaction_id']}.tmp"
    assert not temporary.exists()
    assert not (capsule / "seal.json").exists()
    return temporary


def test_committed_retry_preflight_precedes_descriptor_verification_and_callback(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _interrupt_after_seal_request(complete_capsule)
    trace: list[str] = []
    real_preflight = finalize_module._run_mutator_filesystem_preflight
    real_verify = finalize_module._verify_recoverable_capsule_descriptors

    def traced_preflight(
        capsule_fd: int,
        *,
        parent_fd: int,
        destination_name: str,
        operation_id: UUID,
        lock_handle: finalize_module.LockHandle,
    ) -> None:
        trace.append("preflight")
        real_preflight(
            capsule_fd,
            parent_fd=parent_fd,
            destination_name=destination_name,
            operation_id=operation_id,
            lock_handle=lock_handle,
        )

    def traced_verify(
        root_fd: int,
        *,
        parent_fd: int,
        destination_name: str,
        reserved_operation_id: UUID,
        allow_finalization_artifacts: bool = False,
    ) -> verify_module._VerifiedRecoveryContext:
        trace.append("verify")
        return real_verify(
            root_fd,
            parent_fd=parent_fd,
            destination_name=destination_name,
            reserved_operation_id=reserved_operation_id,
            allow_finalization_artifacts=allow_finalization_artifacts,
        )

    monkeypatch.setattr(
        finalize_module,
        "_run_mutator_filesystem_preflight",
        traced_preflight,
    )
    monkeypatch.setattr(
        finalize_module,
        "_verify_recoverable_capsule_descriptors",
        traced_verify,
    )

    result = finalize_module._finalize_capsule(
        complete_capsule,
        on_target_known=lambda _path: trace.append("callback"),
    )

    assert result.state == "SEALED_COMPLETE"
    assert trace[:3] == ["preflight", "verify", "callback"]


def test_committed_retry_rejects_tail_without_callback_or_recovery(
    complete_capsule: Path,
) -> None:
    _interrupt_after_seal_request(complete_capsule)
    events = complete_capsule / "events.jsonl"
    damaged = events.read_bytes() + b'{"torn":'
    with events.open("ab") as stream:
        stream.write(b'{"torn":')
    announced: list[Path] = []

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            complete_capsule,
            on_target_known=announced.append,
        )

    assert caught.value.code == "integrity_error"
    assert announced == []
    assert events.read_bytes() == damaged
    assert not (complete_capsule / "seal.json").exists()
    assert not list(complete_capsule.glob(".seal.*.tmp"))


def test_finalize_retry_links_exact_existing_temporary_inode(
    complete_capsule: Path,
) -> None:
    temporary, expected = _interrupt_after_complete_temporary(complete_capsule)
    temporary_inode = temporary.stat().st_ino

    result = finalize_capsule(complete_capsule)

    assert result.state == "SEALED_COMPLETE"
    assert not temporary.exists()
    seal = complete_capsule / "seal.json"
    assert seal.read_bytes() == expected
    assert seal.stat().st_ino == temporary_inode


def test_finalize_retry_replaces_only_mismatching_owned_temporary(
    complete_capsule: Path,
) -> None:
    temporary, expected = _interrupt_after_complete_temporary(complete_capsule)
    corrupted = bytes([expected[0] ^ 1]) + expected[1:]
    temporary.write_bytes(corrupted)
    old_inode = temporary.stat().st_ino

    result = finalize_capsule(complete_capsule)

    seal = complete_capsule / "seal.json"
    assert result.state == "SEALED_COMPLETE"
    assert seal.read_bytes() == expected
    assert seal.stat().st_ino != old_inode
    assert not temporary.exists()


def test_finalize_retry_cleans_exact_same_inode_seal_temporary(
    complete_capsule: Path,
) -> None:
    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            complete_capsule,
            seams=_crash_seams("after_link_noreplace"),
        )
    assert caught.value.code == "post_publish_fsync_failed"
    request = _seal_request(complete_capsule)
    payload = request["payload"]
    assert isinstance(payload, dict)
    temporary = complete_capsule / f".seal.{payload['seal_transaction_id']}.tmp"
    seal = complete_capsule / "seal.json"
    original_inode = seal.stat().st_ino
    assert temporary.stat().st_ino == original_inode

    result = finalize_capsule(complete_capsule)

    assert result.state == "SEALED_COMPLETE"
    assert seal.stat().st_ino == original_inode
    assert not temporary.exists()


def test_finalize_retry_cleans_exact_separate_inode_seal_temporary(
    complete_capsule: Path,
) -> None:
    with pytest.raises(FinalizationError):
        finalize_module._finalize_capsule(
            complete_capsule,
            seams=_crash_seams("after_link_noreplace"),
        )
    request = _seal_request(complete_capsule)
    payload = request["payload"]
    assert isinstance(payload, dict)
    temporary = complete_capsule / f".seal.{payload['seal_transaction_id']}.tmp"
    seal = complete_capsule / "seal.json"
    expected = seal.read_bytes()
    seal_inode = seal.stat().st_ino
    temporary.unlink()
    temporary.write_bytes(expected)
    assert temporary.stat().st_ino != seal_inode

    result = finalize_capsule(complete_capsule)

    assert result.state == "SEALED_COMPLETE"
    assert seal.stat().st_ino == seal_inode
    assert seal.read_bytes() == expected
    assert not temporary.exists()


def test_finalize_wrong_transaction_temporary_is_rejected_and_preserved(
    complete_capsule: Path,
) -> None:
    expected_temporary = _interrupt_after_seal_request(complete_capsule)
    wrong = complete_capsule / ".seal.e23e4567-e89b-42d3-a456-426614174033.tmp"
    wrong.write_bytes(b"wrong-transaction-evidence")
    identity = os.lstat(wrong)

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    assert caught.value.code == "seal_mismatch"
    assert os.lstat(wrong) == identity
    assert wrong.read_bytes() == b"wrong-transaction-evidence"
    assert not expected_temporary.exists()
    assert not (complete_capsule / "seal.json").exists()


def test_finalize_second_temporary_is_rejected_without_cleanup(
    complete_capsule: Path,
) -> None:
    expected = _interrupt_after_seal_request(complete_capsule)
    wrong = complete_capsule / ".seal.e23e4567-e89b-42d3-a456-426614174033.tmp"
    expected.write_bytes(b"expected-name-evidence")
    wrong.write_bytes(b"second-name-evidence")
    before = {path.name: (os.lstat(path), path.read_bytes()) for path in (expected, wrong)}

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    assert caught.value.code == "seal_mismatch"
    assert {path.name: (os.lstat(path), path.read_bytes()) for path in (expected, wrong)} == before
    assert not (complete_capsule / "seal.json").exists()


def test_finalize_existing_different_seal_is_rejected_without_overwrite(
    complete_capsule: Path,
) -> None:
    temporary = _interrupt_after_seal_request(complete_capsule)
    seal = complete_capsule / "seal.json"
    seal.write_bytes(b"different-seal-evidence")
    identity = os.lstat(seal)
    events_before = (complete_capsule / "events.jsonl").read_bytes()

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    assert caught.value.code == "seal_mismatch"
    assert os.lstat(seal) == identity
    assert seal.read_bytes() == b"different-seal-evidence"
    assert (complete_capsule / "events.jsonl").read_bytes() == events_before
    assert not temporary.exists()


def test_finalize_mismatching_temporary_aliased_to_preseal_file_is_preserved(
    complete_capsule: Path,
) -> None:
    temporary = _interrupt_after_seal_request(complete_capsule)
    events = complete_capsule / "events.jsonl"
    os.link(events, temporary)
    before_events = os.lstat(events)
    before_temporary = os.lstat(temporary)
    before_bytes = events.read_bytes()

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    assert caught.value.code == "seal_mismatch"
    assert os.lstat(events) == before_events
    assert os.lstat(temporary) == before_temporary
    assert events.read_bytes() == before_bytes
    assert temporary.read_bytes() == before_bytes


@pytest.mark.parametrize("artifact_kind", ["seal-directory", "temporary-symlink"])
def test_finalize_nonregular_publication_artifact_is_rejected_and_preserved(
    complete_capsule: Path,
    artifact_kind: str,
) -> None:
    temporary = _interrupt_after_seal_request(complete_capsule)
    sentinel = complete_capsule.parent / "sentinel-target"
    sentinel.write_bytes(b"sentinel-evidence")
    artifact = complete_capsule / "seal.json" if artifact_kind == "seal-directory" else temporary
    if artifact_kind == "seal-directory":
        artifact.mkdir()
    else:
        artifact.symlink_to(sentinel)
    identity = os.lstat(artifact)

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    assert caught.value.code == "seal_mismatch"
    assert os.lstat(artifact) == identity
    assert sentinel.read_bytes() == b"sentinel-evidence"


def test_finalize_link_race_preserves_existing_destination_and_temporary(
    complete_capsule: Path,
) -> None:
    collision = b"concurrent-destination-evidence"

    def collide_at_publication(
        posix: finalize_module.FilesystemPosixOps,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        assert target_name == "seal.json"
        (complete_capsule / target_name).write_bytes(collision)
        posix.link_noreplace(
            source_directory_fd,
            source_name,
            target_directory_fd,
            target_name,
        )

    identifiers = iter((_FINALIZE_OPERATION, _SEAL_TRANSACTION))
    seams = finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
        link_noreplace=collide_at_publication,
    )

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(complete_capsule, seams=seams)

    temporary = complete_capsule / f".seal.{_SEAL_TRANSACTION}.tmp"
    assert caught.value.code == "destination_collision"
    assert (complete_capsule / "seal.json").read_bytes() == collision
    assert temporary.is_file()
    assert temporary.read_bytes() != collision


class _ExplodingPath:
    def __fspath__(self) -> str:
        raise RuntimeError("path-CANARY")


class _InjectedFatal(BaseException):
    pass


@pytest.mark.parametrize("boundary", ["path", "uuid", "clock"])
def test_finalize_argument_boundary_maps_ordinary_exceptions_content_free(
    prepared_capsule: Path,
    boundary: str,
) -> None:
    def explode() -> object:
        raise RuntimeError("argument-CANARY")

    path = cast(Path, _ExplodingPath()) if boundary == "path" else prepared_capsule
    seams = finalize_module._FinalizeSeams(
        new_uuid=(
            (lambda: cast(UUID, explode())) if boundary == "uuid" else lambda: _FINALIZE_OPERATION
        ),
        utc_now=(
            (lambda: cast(datetime, explode())) if boundary == "clock" else lambda: _FINALIZE_TIME
        ),
    )

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(path, seams=seams)

    assert caught.value.code == "invalid_argument"
    assert str(caught.value) == "capsule finalization rejected"
    assert "CANARY" not in str(caught.value)


def test_finalize_callback_failure_is_content_free_and_precedes_mutation(
    prepared_capsule: Path,
) -> None:
    events_before = (prepared_capsule / "events.jsonl").read_bytes()
    raw_before = (prepared_capsule / "raw.jsonl").read_bytes()
    calls = 0

    def fail_callback(_path: Path) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("callback-CANARY")

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            prepared_capsule,
            on_target_known=fail_callback,
        )

    assert caught.value.code == "target_callback_failed"
    assert str(caught.value) == "capsule finalization rejected"
    assert calls == 1
    assert (prepared_capsule / "events.jsonl").read_bytes() == events_before
    assert (prepared_capsule / "raw.jsonl").read_bytes() == raw_before
    assert not (prepared_capsule / "seal.json").exists()


def test_finalize_busy_is_unannounced_and_byte_preserving(complete_capsule: Path) -> None:
    events_before = (complete_capsule / "events.jsonl").read_bytes()
    raw_before = (complete_capsule / "raw.jsonl").read_bytes()
    names_before = tuple(sorted(path.name for path in complete_capsule.iterdir()))
    announced: list[Path] = []
    lock_fd = os.open(complete_capsule / ".laconian.lock", os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(FinalizationError) as caught:
            finalize_module._finalize_capsule(
                complete_capsule,
                on_target_known=announced.append,
            )
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)

    assert caught.value.code == "busy"
    assert announced == []
    assert (complete_capsule / "events.jsonl").read_bytes() == events_before
    assert (complete_capsule / "raw.jsonl").read_bytes() == raw_before
    assert tuple(sorted(path.name for path in complete_capsule.iterdir())) == names_before


def test_finalize_preserves_non_exception_checkpoint_fatal(complete_capsule: Path) -> None:
    fatal = _InjectedFatal("fatal-CANARY")

    def checkpoint(point: finalize_module.CrashPoint) -> None:
        if point == "after_seal_requested_fsync":
            raise fatal

    identifiers = iter((_FINALIZE_OPERATION, _SEAL_TRANSACTION))
    seams = finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
        checkpoint=checkpoint,
    )

    with pytest.raises(_InjectedFatal) as caught:
        finalize_module._finalize_capsule(complete_capsule, seams=seams)

    assert caught.value is fatal


def test_finalize_propagates_fatal_artifact_close_after_publication(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fatal = _InjectedFatal("close-CANARY")
    original_close = finalize_module._OpenedArtifact.close
    injected = False

    def close_then_fail(opened: finalize_module._OpenedArtifact) -> None:
        nonlocal injected
        original_close(opened)
        if not injected:
            injected = True
            raise fatal

    monkeypatch.setattr(finalize_module._OpenedArtifact, "close", close_then_fail)

    with pytest.raises(_InjectedFatal) as caught:
        finalize_capsule(complete_capsule)

    assert caught.value is fatal
    assert (complete_capsule / "seal.json").is_file()


@pytest.mark.parametrize("primary_kind", ["ordinary", "fatal"])
def test_finalize_cleanup_fatal_precedence_matches_mutator_contract(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
    primary_kind: str,
) -> None:
    primary_fatal = _InjectedFatal("primary-fatal-CANARY")
    cleanup_fatal = _InjectedFatal("cleanup-fatal-CANARY")
    original_close = finalize_module._OpenedArtifact.close
    injected = False

    def close_then_fail(opened: finalize_module._OpenedArtifact) -> None:
        nonlocal injected
        original_close(opened)
        if not injected:
            injected = True
            raise cleanup_fatal

    def checkpoint(point: finalize_module.CrashPoint) -> None:
        if point != "after_link_noreplace":
            return
        if primary_kind == "fatal":
            raise primary_fatal
        raise RuntimeError("primary-ordinary-CANARY")

    monkeypatch.setattr(finalize_module._OpenedArtifact, "close", close_then_fail)
    identifiers = iter((_FINALIZE_OPERATION, _SEAL_TRANSACTION))
    seams = finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
        checkpoint=checkpoint,
    )

    with pytest.raises(_InjectedFatal) as caught:
        finalize_module._finalize_capsule(complete_capsule, seams=seams)

    assert caught.value is (primary_fatal if primary_kind == "fatal" else cleanup_fatal)


def test_finalize_postpublication_probe_close_failure_is_operational(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_close = os.close
    injected = False

    def fail_first_published_artifact_close(descriptor: int) -> None:
        nonlocal injected
        seal = complete_capsule / "seal.json"
        if not injected and seal.exists():
            try:
                descriptor_stat = os.fstat(descriptor)
                seal_stat = os.lstat(seal)
            except OSError:
                pass
            else:
                if (descriptor_stat.st_dev, descriptor_stat.st_ino) == (
                    seal_stat.st_dev,
                    seal_stat.st_ino,
                ):
                    injected = True
                    real_close(descriptor)
                    raise OSError("probe-close-CANARY")
        real_close(descriptor)

    monkeypatch.setattr(finalize_module.os, "close", fail_first_published_artifact_close)

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    assert injected is True
    assert caught.value.code == "post_publish_fsync_failed"
    assert str(caught.value) == "capsule finalization rejected"
    assert (complete_capsule / "seal.json").is_file()


def test_finalize_prepublication_probe_close_failure_is_operational(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_close = os.close
    injected = False

    def fail_first_temporary_probe_close(descriptor: int) -> None:
        nonlocal injected
        temporary = complete_capsule / f".seal.{_SEAL_TRANSACTION}.tmp"
        if not injected and temporary.exists() and not (complete_capsule / "seal.json").exists():
            try:
                descriptor_stat = os.fstat(descriptor)
                temporary_stat = os.lstat(temporary)
            except OSError:
                pass
            else:
                if (descriptor_stat.st_dev, descriptor_stat.st_ino) == (
                    temporary_stat.st_dev,
                    temporary_stat.st_ino,
                ):
                    injected = True
                    real_close(descriptor)
                    raise OSError("probe-close-CANARY")
        real_close(descriptor)

    monkeypatch.setattr(finalize_module.os, "close", fail_first_temporary_probe_close)
    identifiers = iter((_FINALIZE_OPERATION, _SEAL_TRANSACTION))
    seams = finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
    )

    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(complete_capsule, seams=seams)

    assert injected is True
    assert caught.value.code == "io_error"
    assert str(caught.value) == "capsule finalization rejected"
    assert not (complete_capsule / "seal.json").exists()
    assert (complete_capsule / f".seal.{_SEAL_TRANSACTION}.tmp").is_file()


def test_finalize_maps_identity_scanner_scratch_failure_to_io_error(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_registry(*_args: object, **_kwargs: object) -> object:
        raise verify_module.ScratchError()

    monkeypatch.setattr(verify_module, "ExactIdentityRegistry", fail_registry)

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    assert caught.value.code == "io_error"
    assert str(caught.value) == "capsule finalization rejected"
    assert not (complete_capsule / "seal.json").exists()
    assert not list(complete_capsule.glob(".seal.*.tmp"))
    assert not any(row["kind"] == "seal_requested" for row in _event_rows(complete_capsule))


@pytest.mark.parametrize(
    "error",
    [
        finalize_module.RecoveryError("io_error"),
        finalize_module.JournalError("io_error", "events"),
        finalize_module.BoundedIOError("io_error", "bounded-io-CANARY"),
        finalize_module.OwnedStagingError("io_error"),
    ],
)
def test_finalize_error_mapping_preserves_operational_io_code(error: Exception) -> None:
    mapped = finalize_module._map_failure(error)

    assert mapped.code == "io_error"
    assert str(mapped) == "capsule finalization rejected"


@pytest.mark.parametrize(
    ("failure_kind", "expected_code"),
    [
        ("operational", "post_publish_fsync_failed"),
        ("identity", "seal_mismatch"),
    ],
)
def test_finalize_closes_raw_seal_descriptor_when_post_link_validation_fails(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
    expected_code: str,
) -> None:
    real_open = os.open
    real_fstat = os.fstat
    real_close = os.close
    seal_descriptor: int | None = None
    injected = False
    seal_closed = False

    def tracked_open(
        path: Any,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal seal_descriptor
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == "seal.json":
            seal_descriptor = descriptor
        return descriptor

    def fail_first_seal_fstat(descriptor: int) -> os.stat_result:
        nonlocal injected
        if descriptor == seal_descriptor and not injected:
            injected = True
            if failure_kind == "operational":
                raise OSError("seal-fstat-CANARY")
            return os.lstat(complete_capsule / ".laconian.lock")
        return real_fstat(descriptor)

    def tracked_close(descriptor: int) -> None:
        nonlocal seal_closed
        if seal_descriptor is not None and descriptor == seal_descriptor:
            seal_closed = True
        real_close(descriptor)

    monkeypatch.setattr(finalize_module.os, "open", tracked_open)
    monkeypatch.setattr(finalize_module.os, "fstat", fail_first_seal_fstat)
    monkeypatch.setattr(finalize_module.os, "close", tracked_close)

    try:
        with pytest.raises(FinalizationError) as caught:
            finalize_capsule(complete_capsule)

        assert injected is True
        assert caught.value.code == expected_code
        assert seal_descriptor is not None
        assert seal_closed is True
        assert (complete_capsule / "seal.json").is_file()
        assert list(complete_capsule.glob(".seal.*.tmp"))
    finally:
        if seal_descriptor is not None and not seal_closed:
            real_close(seal_descriptor)


@pytest.mark.parametrize("handoff", ["raw_to_artifact", "return_to_caller"])
def test_finalize_async_fatal_during_seal_descriptor_handoff_closes_once(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
    handoff: str,
) -> None:
    fatal = _InjectedFatal("handoff-fatal-CANARY")
    real_open = os.open
    real_close = os.close
    seal_descriptor: int | None = None
    seal_close_attempts = 0

    def tracked_open(
        path: Any,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal seal_descriptor, seal_close_attempts
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == "seal.json":
            seal_descriptor = descriptor
            seal_close_attempts = 0
        return descriptor

    def tracked_close(descriptor: int) -> None:
        nonlocal seal_close_attempts
        if seal_descriptor is not None and descriptor == seal_descriptor:
            seal_close_attempts += 1
        real_close(descriptor)

    link_code = finalize_module._link_temporary.__code__
    source, start_line = inspect.getsourcelines(finalize_module._link_temporary)
    return_line = start_line + next(
        index for index, line in enumerate(source) if line.strip() == "return retained"
    )

    def interrupt_double_ownership(
        frame: FrameType,
        event: str,
        _argument: object,
    ) -> Any:
        if event == "line" and frame.f_code is link_code:
            seal = frame.f_locals.get("seal")
            raw_descriptor = frame.f_locals.get("seal_descriptor")
            duplicate_ownership = (
                type(seal) is finalize_module._OpenedArtifact
                and type(raw_descriptor) is int
                and raw_descriptor >= 0
                and raw_descriptor == seal.descriptor
            )
            returning = frame.f_lineno == return_line
            if (handoff == "raw_to_artifact" and duplicate_ownership) or (
                handoff == "return_to_caller" and returning
            ):
                sys.settrace(None)
                raise fatal
        return interrupt_double_ownership

    monkeypatch.setattr(finalize_module.os, "open", tracked_open)
    monkeypatch.setattr(finalize_module.os, "close", tracked_close)
    previous_trace = sys.gettrace()
    try:
        sys.settrace(interrupt_double_ownership)
        with pytest.raises(_InjectedFatal) as caught:
            finalize_capsule(complete_capsule)
    finally:
        sys.settrace(previous_trace)
        if seal_descriptor is not None and seal_close_attempts == 0:
            real_close(seal_descriptor)

    assert caught.value is fatal
    assert seal_descriptor is not None
    assert seal_close_attempts == 1
    assert (complete_capsule / "seal.json").is_file()
    assert list(complete_capsule.glob(".seal.*.tmp"))


@pytest.mark.parametrize("handoff", ["open_existing", "create_new"])
def test_finalize_async_fatal_during_artifact_return_handoff_closes_once(
    complete_capsule: Path,
    monkeypatch: pytest.MonkeyPatch,
    handoff: str,
) -> None:
    if handoff == "open_existing":
        _interrupt_after_complete_temporary(complete_capsule)
        function = finalize_module._open_artifact
    else:
        function = finalize_module._create_temporary
    source, start_line = inspect.getsourcelines(function)
    return_line = start_line + next(
        index for index, line in enumerate(source) if line.strip() == "return opened"
    )
    fatal = _InjectedFatal("return-handoff-fatal-CANARY")
    real_close = os.close
    artifact_descriptor: int | None = None
    artifact_close_attempts = 0

    def tracked_close(descriptor: int) -> None:
        nonlocal artifact_close_attempts
        if artifact_descriptor is not None and descriptor == artifact_descriptor:
            artifact_close_attempts += 1
        real_close(descriptor)

    def interrupt_return_handoff(
        frame: FrameType,
        event: str,
        _argument: object,
    ) -> Any:
        nonlocal artifact_descriptor, artifact_close_attempts
        if event == "line" and frame.f_code is function.__code__ and frame.f_lineno == return_line:
            opened = frame.f_locals.get("opened")
            assert type(opened) is finalize_module._OpenedArtifact
            artifact_descriptor = opened.descriptor
            artifact_close_attempts = 0
            sys.settrace(None)
            raise fatal
        return interrupt_return_handoff

    monkeypatch.setattr(finalize_module.os, "close", tracked_close)
    previous_trace = sys.gettrace()
    try:
        sys.settrace(interrupt_return_handoff)
        with pytest.raises(_InjectedFatal) as caught:
            finalize_capsule(complete_capsule)
    finally:
        sys.settrace(previous_trace)
        if artifact_descriptor is not None and artifact_close_attempts == 0:
            real_close(artifact_descriptor)

    assert caught.value is fatal
    assert artifact_descriptor is not None
    assert artifact_close_attempts == 1
