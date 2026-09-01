"""Independent contract tests for atomic generation-capsule finalization."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.finalize as finalize_module
from laconian_eval.capsule.canonical import sha256_bytes
from laconian_eval.capsule.execution import ProviderFactory
from laconian_eval.capsule.finalize import FinalizationError, finalize_capsule
from laconian_eval.capsule.seal_models import SealV1
from laconian_eval.providers import GenerationResult

from .test_execution import (
    _install_fast_runtime,
    _ScriptedProvider,
    _seams_for_provider,
    _single_plan_capsule,
)

_FINALIZE_OPERATION = UUID("f23e4567-e89b-42d3-a456-426614174040")
_SEAL_TRANSACTION = UUID("e23e4567-e89b-42d3-a456-426614174041")
_COLLISION_TEST_OPERATION = UUID("d23e4567-e89b-42d3-a456-426614174042")
_FINALIZE_TIME = datetime(2026, 8, 30, 14, 15, 16, 123456, tzinfo=UTC)


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


def _event_rows(capsule: Path) -> list[dict[str, object]]:
    return [json.loads(row) for row in (capsule / "events.jsonl").read_bytes().splitlines()]


def _seal_requests(capsule: Path) -> list[dict[str, object]]:
    return [row for row in _event_rows(capsule) if row["kind"] == "seal_requested"]


def _crash_after(
    point: finalize_module.CrashPoint,
    *,
    operation_id: UUID = _FINALIZE_OPERATION,
    transaction_id: UUID = _SEAL_TRANSACTION,
) -> finalize_module._FinalizeSeams:
    identifiers = iter((operation_id, transaction_id))

    def checkpoint(observed: finalize_module.CrashPoint) -> None:
        if observed == point:
            raise OSError("diagnostic-CANARY")

    return finalize_module._FinalizeSeams(
        new_uuid=lambda: next(identifiers),
        utc_now=lambda: _FINALIZE_TIME,
        checkpoint=checkpoint,
    )


def test_committed_incomplete_request_retries_without_flag_and_reuses_request(
    prepared_capsule: Path,
) -> None:
    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            prepared_capsule,
            seal_incomplete=True,
            seams=_crash_after("after_seal_requested_fsync"),
        )

    assert caught.value.code == "io_error"
    committed = _seal_requests(prepared_capsule)
    assert len(committed) == 1
    committed_request = committed[0]
    assert committed_request["occurred_at"] == "2026-08-30T14:15:16.123456Z"
    assert committed_request["payload"] == {
        "seal_transaction_id": str(_SEAL_TRANSACTION),
        "expected_generation_status": "incomplete",
        "prior_event_sequence": committed_request["sequence"] - 1,
    }

    result = finalize_capsule(prepared_capsule)
    seal = SealV1.model_validate_json((prepared_capsule / "seal.json").read_bytes())

    assert result.state == "SEALED_BLOCKED"
    assert _seal_requests(prepared_capsule) == [committed_request]
    assert seal.seal_transaction_id == _SEAL_TRANSACTION
    assert seal.generation_status == "incomplete"
    assert seal.sealed_at == _FINALIZE_TIME


def test_seal_inventory_hashes_post_request_events_and_excludes_operational_files(
    complete_capsule: Path,
) -> None:
    with pytest.raises(FinalizationError) as caught:
        finalize_module._finalize_capsule(
            complete_capsule,
            seams=_crash_after("after_temporary_file_fsync"),
        )

    assert caught.value.code == "io_error"
    request = _seal_requests(complete_capsule)
    assert len(request) == 1
    payload = request[0]["payload"]
    assert isinstance(payload, dict)
    temporary_name = f".seal.{payload['seal_transaction_id']}.tmp"
    temporary = complete_capsule / temporary_name
    seal = SealV1.model_validate_json(temporary.read_bytes())

    all_regular_files = {
        path.relative_to(complete_capsule).as_posix()
        for path in complete_capsule.rglob("*")
        if path.is_file()
    }
    expected_paths = tuple(
        sorted(
            all_regular_files - {".laconian.lock", "seal.json", temporary_name},
            key=lambda path: path.encode("utf-8"),
        )
    )
    sealed_paths = tuple(record.path for record in seal.files)
    events_bytes = (complete_capsule / "events.jsonl").read_bytes()
    events_record = next(record for record in seal.files if record.path == "events.jsonl")

    assert sealed_paths == expected_paths
    assert events_record.byte_length == len(events_bytes)
    assert events_record.sha256 == sha256_bytes(events_bytes)
    assert seal.final_event_sequence == request[0]["sequence"]
    assert not ({".laconian.lock", "seal.json", temporary_name} & set(sealed_paths))


def test_transaction_uuid_retries_forbidden_collisions_and_allows_prior_operation(
    complete_capsule: Path,
) -> None:
    rows = _event_rows(complete_capsule)
    run_id = UUID(str(rows[0]["run_id"]))
    prior_operation_id = UUID(str(rows[0]["operation_id"]))
    execution_started = next(row for row in rows if row["kind"] == "execution_started")
    execution_session_id = UUID(str(execution_started["execution_session_id"]))
    candidates = (
        _COLLISION_TEST_OPERATION,
        run_id,
        _COLLISION_TEST_OPERATION,
        execution_session_id,
        prior_operation_id,
    )
    emitted: list[UUID] = []
    values = iter(candidates)

    def new_uuid() -> UUID:
        value = next(values)
        emitted.append(value)
        return value

    result = finalize_module._finalize_capsule(
        complete_capsule,
        seams=finalize_module._FinalizeSeams(
            new_uuid=new_uuid,
            utc_now=lambda: _FINALIZE_TIME,
        ),
    )
    seal = SealV1.model_validate_json((complete_capsule / "seal.json").read_bytes())

    assert result.state == "SEALED_COMPLETE"
    assert emitted == list(candidates)
    assert seal.seal_transaction_id == prior_operation_id
    assert seal.seal_transaction_id not in {
        run_id,
        _COLLISION_TEST_OPERATION,
        execution_session_id,
    }


@pytest.mark.parametrize("residue_kind", ["partial", "mismatch"])
def test_unsealed_retry_replaces_only_mismatching_same_transaction_temporary(
    prepared_capsule: Path,
    residue_kind: str,
) -> None:
    with pytest.raises(FinalizationError):
        finalize_module._finalize_capsule(
            prepared_capsule,
            seal_incomplete=True,
            seams=_crash_after("after_temporary_file_fsync"),
        )
    request = _seal_requests(prepared_capsule)
    assert len(request) == 1
    payload = request[0]["payload"]
    assert isinstance(payload, dict)
    temporary = prepared_capsule / f".seal.{payload['seal_transaction_id']}.tmp"
    exact_seal_bytes = temporary.read_bytes()
    if residue_kind == "partial":
        residue = exact_seal_bytes[: len(exact_seal_bytes) // 2]
    else:
        residue = bytes([exact_seal_bytes[0] ^ 1]) + exact_seal_bytes[1:]
    with temporary.open("r+b", buffering=0) as stream:
        stream.write(residue)
        stream.truncate()
        os.fsync(stream.fileno())

    result = finalize_capsule(prepared_capsule)

    assert result.state == "SEALED_BLOCKED"
    assert (prepared_capsule / "seal.json").read_bytes() == exact_seal_bytes
    assert not temporary.exists()
    assert len(_seal_requests(prepared_capsule)) == 1


def test_sealed_retry_preserves_mismatching_same_transaction_temporary_without_cleanup(
    complete_capsule: Path,
) -> None:
    finalize_capsule(complete_capsule)
    requests = _seal_requests(complete_capsule)
    assert len(requests) == 1
    payload = requests[0]["payload"]
    assert isinstance(payload, dict)
    temporary = complete_capsule / f".seal.{payload['seal_transaction_id']}.tmp"
    mismatch = b"mismatching-seal-residue\n"
    temporary.write_bytes(mismatch)
    temporary.chmod(0o600)
    seal = complete_capsule / "seal.json"
    seal_bytes_before = seal.read_bytes()
    seal_inode_before = seal.stat().st_ino
    temporary_inode_before = temporary.stat().st_ino
    events_before = (complete_capsule / "events.jsonl").read_bytes()
    paths_before = tuple(
        sorted(
            path.relative_to(complete_capsule).as_posix() for path in complete_capsule.rglob("*")
        )
    )

    with pytest.raises(FinalizationError) as caught:
        finalize_capsule(complete_capsule)

    paths_after = tuple(
        sorted(
            path.relative_to(complete_capsule).as_posix() for path in complete_capsule.rglob("*")
        )
    )
    assert caught.value.code == "seal_mismatch"
    assert paths_after == paths_before
    assert seal.read_bytes() == seal_bytes_before
    assert seal.stat().st_ino == seal_inode_before
    assert temporary.read_bytes() == mismatch
    assert temporary.stat().st_ino == temporary_inode_before
    assert (complete_capsule / "events.jsonl").read_bytes() == events_before
    assert _seal_requests(complete_capsule) == requests
