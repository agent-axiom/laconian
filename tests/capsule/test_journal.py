from __future__ import annotations

import hashlib
import os
import socket
import tempfile
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

import laconian_eval.capsule.journal as journal_module
from capsule.test_lifecycle import (
    EXECUTION_OPERATION,
    NOW,
    RUN_ID,
    SESSION_ID,
    _attempt,
    _context,
    _execution_started,
    _prepared,
    _session_payload,
    _start,
)
from laconian_eval.capsule.attempts import RawAttemptV2, raw_attempt_jsonl
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.events import EventV1, event_jsonl, make_event
from laconian_eval.capsule.filesystem import FilesystemPosixOps
from laconian_eval.capsule.history import HistoryContextV1, HistoryError
from laconian_eval.capsule.journal import (
    JournalError,
    append_event,
    append_raw_attempt,
    open_journal_transaction,
    snapshot_event_journal,
    snapshot_journal_pair,
    snapshot_raw_journal,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.record_models import CapsuleV1, EnvironmentV1, PlanRowV1


def _root(tmp_path: object) -> int:
    return os.open(os.fspath(tmp_path), os.O_RDONLY | os.O_DIRECTORY)


_OTHER_RUN_ID = UUID("12345678-1234-4abc-8def-1234567890c1")
_OTHER_OPERATION = UUID("12345678-1234-4abc-8def-1234567890c2")
_OTHER_SESSION = UUID("12345678-1234-4abc-8def-1234567890c3")


def _two_row_context() -> tuple[
    CapsuleV1,
    ResolvedManifestV2,
    EnvironmentV1,
    tuple[PlanRowV1, ...],
]:
    capsule, manifest, environment, plan = _context()
    second_payload = plan[0].model_dump(mode="python")
    second_payload.update(
        ordinal=1,
        plan_item_id="9" * 64,
        pairing_unit_id="a" * 64,
        case_uid="d" * 64,
        scenario_uid="e" * 64,
        case_id="second-case-en",
        block_id="f" * 64,
    )
    return capsule, manifest, environment, (plan[0], PlanRowV1.model_validate(second_payload))


def _event_stage_case(case: str) -> tuple[tuple[EventV1, ...], str, int]:
    capsule, _manifest, environment, plan = _context()
    prepared = _prepared(capsule)
    if case == "sequence_gap":
        return (prepared, _execution_started(environment, sequence=2)), "history_mismatch", 1
    if case == "missing_first_prepared":
        return (_execution_started(environment),), "history_mismatch", 0
    if case == "duplicate_prepared":
        return (prepared, prepared), "history_mismatch", 1
    if case == "wrong_run":
        wrong_run_start = make_event(
            sequence=1,
            run_id=_OTHER_RUN_ID,
            occurred_at=NOW,
            kind="execution_started",
            operation_id=_OTHER_OPERATION,
            execution_session_id=_OTHER_SESSION,
            payload={
                "resume_from_plan_ordinal": 0,
                "session_environment": _session_payload(environment),
            },
        )
        return (prepared, wrong_run_start), "identity_mismatch", 1
    if case == "resume_out_of_range":
        out_of_range = make_event(
            sequence=1,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="execution_started",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload={
                "resume_from_plan_ordinal": len(plan),
                "session_environment": _session_payload(environment),
            },
        )
        return (prepared, out_of_range), "identity_mismatch", 1
    if case == "epoch_operation_mismatch":
        wrong_epoch_block = make_event(
            sequence=2,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="execution_blocked",
            operation_id=_OTHER_OPERATION,
            execution_session_id=SESSION_ID,
            payload={"reason": "credential_unavailable"},
        )
        return (
            (
                prepared,
                _execution_started(environment),
                wrong_epoch_block,
            ),
            "history_mismatch",
            2,
        )
    if case == "epoch_session_mismatch":
        wrong_epoch_block = make_event(
            sequence=2,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="execution_blocked",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=_OTHER_SESSION,
            payload={"reason": "credential_unavailable"},
        )
        return (
            (
                prepared,
                _execution_started(environment),
                wrong_epoch_block,
            ),
            "history_mismatch",
            2,
        )
    if case == "terminal_seal_suffix":
        seal = make_event(
            sequence=1,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="seal_requested",
            operation_id=_OTHER_OPERATION,
            execution_session_id=None,
            payload={
                "seal_transaction_id": str(_OTHER_SESSION),
                "expected_generation_status": "incomplete",
                "prior_event_sequence": 0,
            },
        )
        return (
            (
                prepared,
                seal,
                _execution_started(environment, sequence=2),
            ),
            "lifecycle_mismatch",
            2,
        )
    if case in {"finish_link_mismatch", "normal_finish_wrong_epoch"}:
        start = _start(plan[0])
        finish = make_event(
            sequence=3,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="request_finished",
            operation_id=(
                _OTHER_OPERATION if case == "normal_finish_wrong_epoch" else EXECUTION_OPERATION
            ),
            execution_session_id=SESSION_ID,
            payload={
                "call_sequence": start.payload.call_sequence,
                "plan_item_id": start.payload.plan_item_id,
                "attempt_id": start.payload.attempt_id,
                "request_started_event_id": (
                    "a" * 64 if case == "finish_link_mismatch" else start.event_id
                ),
                "raw_record_sha256": "b" * 64,
                "recovered": False,
            },
        )
        return (
            (
                prepared,
                _execution_started(environment),
                start,
                finish,
            ),
            ("history_mismatch" if case == "normal_finish_wrong_epoch" else "identity_mismatch"),
            3,
        )
    if case == "attempt_identity_mismatch":
        payload = _start(plan[0]).payload.model_dump(mode="python")
        payload["attempt_id"] = "a" * 64
        forged = make_event(
            sequence=2,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="request_started",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload=payload,
        )
        return (
            (prepared, _execution_started(environment), forged),
            "identity_mismatch",
            2,
        )
    if case == "attempt_budget_exceeded":
        payload = _start(plan[0]).payload.model_dump(mode="python")
        payload.update(attempt_id="a" * 64, attempt=7, retry_of_attempt=6)
        over_budget = make_event(
            sequence=2,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="request_started",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload=payload,
        )
        return (
            (prepared, _execution_started(environment), over_budget),
            "retry_mismatch",
            2,
        )
    if case in {"auth_marker_link_mismatch", "completion_link_mismatch"}:
        start = _start(plan[0])
        finish = make_event(
            sequence=3,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="request_finished",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload={
                "call_sequence": 0,
                "plan_item_id": start.payload.plan_item_id,
                "attempt_id": start.payload.attempt_id,
                "request_started_event_id": start.event_id,
                "raw_record_sha256": "b" * 64,
                "recovered": False,
            },
        )
        if case == "auth_marker_link_mismatch":
            marker = make_event(
                sequence=4,
                run_id=RUN_ID,
                occurred_at=NOW,
                kind="authentication_stopped",
                operation_id=EXECUTION_OPERATION,
                execution_session_id=SESSION_ID,
                payload={
                    "plan_item_id": start.payload.plan_item_id,
                    "attempt_id": start.payload.attempt_id,
                    "origin_request_started_event_id": "a" * 64,
                    "recovered": False,
                },
            )
        else:
            marker = make_event(
                sequence=4,
                run_id=RUN_ID,
                occurred_at=NOW,
                kind="generation_completed",
                operation_id=EXECUTION_OPERATION,
                execution_session_id=SESSION_ID,
                payload={
                    "terminal_plan_item_count": len(plan),
                    "final_plan_ordinal": len(plan) - 1,
                    "origin_request_finished_event_id": "a" * 64,
                    "recovered": False,
                },
            )
        return (
            (prepared, _execution_started(environment), start, finish, marker),
            "identity_mismatch",
            4,
        )
    raise AssertionError("unknown event-stage fixture")


@pytest.mark.parametrize(
    "case",
    [
        "sequence_gap",
        "missing_first_prepared",
        "duplicate_prepared",
        "wrong_run",
        "resume_out_of_range",
        "epoch_operation_mismatch",
        "epoch_session_mismatch",
        "terminal_seal_suffix",
        "finish_link_mismatch",
        "normal_finish_wrong_epoch",
        "attempt_identity_mismatch",
        "attempt_budget_exceeded",
        "auth_marker_link_mismatch",
        "completion_link_mismatch",
    ],
)
def test_event_grammar_precedes_simultaneous_raw_corruption(case: str, tmp_path: object) -> None:
    capsule, manifest, environment, plan = _context()
    events, expected_code, expected_row = _event_stage_case(case)
    (tmp_path / "events.jsonl").write_bytes(b"".join(event_jsonl(event) for event in events))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"{\n")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises((HistoryError, JournalError)) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        os.close(descriptor)
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        expected_code,
        "events",
        expected_row,
    )


@pytest.mark.parametrize("event_kind", ["request_started", "execution_interrupted"])
def test_epoch_resume_target_mismatch_precedes_raw_corruption(
    event_kind: str,
    tmp_path: object,
) -> None:
    capsule, manifest, environment, plan = _two_row_context()
    if event_kind == "request_started":
        mismatched = _start(plan[1])
    else:
        mismatched = make_event(
            sequence=2,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="execution_interrupted",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload={
                "reason": "internal_error",
                "next_plan_item_id": plan[1].plan_item_id,
            },
        )
    events = (_prepared(capsule), _execution_started(environment), mismatched)
    (tmp_path / "events.jsonl").write_bytes(  # type: ignore[operator]
        b"".join(event_jsonl(event) for event in events)
    )
    (tmp_path / "raw.jsonl").write_bytes(b"{\n")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(HistoryError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "identity_mismatch",
        "events",
        2,
    )


def test_first_execution_resume_ordinal_mismatch_precedes_raw_corruption(
    tmp_path: object,
) -> None:
    capsule, manifest, environment, plan = _two_row_context()
    started = make_event(
        sequence=1,
        run_id=RUN_ID,
        occurred_at=NOW,
        kind="execution_started",
        operation_id=EXECUTION_OPERATION,
        execution_session_id=SESSION_ID,
        payload={
            "resume_from_plan_ordinal": 1,
            "session_environment": _session_payload(environment),
        },
    )
    events = (_prepared(capsule), started, _start(plan[1]))
    (tmp_path / "events.jsonl").write_bytes(  # type: ignore[operator]
        b"".join(event_jsonl(event) for event in events)
    )
    (tmp_path / "raw.jsonl").write_bytes(b"{\n")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(HistoryError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "identity_mismatch",
        "events",
        1,
    )


def test_prepared_journal_snapshot_is_compact_and_derives_lifecycle(tmp_path: object) -> None:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        snapshot = snapshot_journal_pair(
            descriptor,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="reject",
        )
    finally:
        os.close(descriptor)
    assert snapshot.events.row_count == 1
    assert snapshot.raw.row_count == 0
    assert snapshot.lifecycle.state == "PREPARED"
    assert not hasattr(snapshot.events, "rows")


def test_standalone_event_and_raw_snapshots_share_strict_reader(tmp_path: object) -> None:
    capsule, _manifest, _environment, _plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        events = snapshot_event_journal(descriptor, tail_policy="reject")
        raw = snapshot_raw_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)
    assert events.row_count == 1
    assert events.tail_byte_count == 0
    assert raw.row_count == 0
    assert raw.byte_length == 0


@pytest.mark.parametrize(
    ("ledger", "case", "expected_code"),
    [
        ("events", "blank", "noncanonical_json"),
        ("events", "malformed", "noncanonical_json"),
        ("events", "noncanonical", "noncanonical_json"),
        ("raw", "wrong_schema", "invalid_model"),
    ],
)
def test_committed_framing_and_schema_matrix(
    ledger: str,
    case: str,
    expected_code: str,
    tmp_path: Path,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    if case == "blank":
        encoded = b"\n"
    elif case == "malformed":
        encoded = b"{\n"
    elif case == "noncanonical":
        encoded = b" " + event_jsonl(_prepared(capsule))
    else:
        encoded = b'{"schema_version":"999"}\n'
    (tmp_path / "events.jsonl").write_bytes(encoded if ledger == "events" else b"")
    (tmp_path / "raw.jsonl").write_bytes(encoded if ledger == "raw" else b"")
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            if ledger == "events":
                snapshot_event_journal(descriptor, tail_policy="reject")
            else:
                snapshot_raw_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        expected_code,
        ledger,
        0,
    )


@pytest.mark.parametrize("terminated", [False, True], ids=("tail", "row"))
def test_oversized_row_or_tail_rejects_at_the_bounded_row_limit(
    terminated: bool,
    tmp_path: Path,
) -> None:
    oversized = b"x" * (RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 1)
    (tmp_path / "events.jsonl").write_bytes(oversized + (b"\n" if terminated else b""))
    (tmp_path / "raw.jsonl").write_bytes(b"")
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="report")
    finally:
        os.close(descriptor)
    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "resource_limit",
        "events",
        0,
    )


def test_exact_maximum_tail_is_reported_as_bounded_metadata(tmp_path: Path) -> None:
    tail = b"x" * RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes
    (tmp_path / "events.jsonl").write_bytes(tail)
    (tmp_path / "raw.jsonl").write_bytes(b"")
    descriptor = _root(tmp_path)
    try:
        snapshot = snapshot_event_journal(descriptor, tail_policy="report")
    finally:
        os.close(descriptor)
    assert snapshot.row_count == 0
    assert snapshot.tail_byte_count == len(tail)
    assert snapshot.tail_sha256 == hashlib.sha256(tail).hexdigest()


@pytest.mark.parametrize("path_type", ["symlink", "fifo", "socket", "directory"])
def test_snapshot_rejects_every_nonregular_ledger_path(
    path_type: str,
    tmp_path: Path,
) -> None:
    short_root: tempfile.TemporaryDirectory[str] | None = None
    root = tmp_path
    if path_type == "socket":
        short_root = tempfile.TemporaryDirectory(prefix="laconian-journal-", dir="/tmp")
        root = Path(short_root.name)
    event_path = root / "events.jsonl"
    socket_handle: socket.socket | None = None
    if path_type == "symlink":
        target = root / "target.jsonl"
        target.write_bytes(b"")
        event_path.symlink_to(target.name)
    elif path_type == "fifo":
        os.mkfifo(event_path)
    elif path_type == "socket":
        socket_handle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        socket_handle.bind(os.fspath(event_path))
    else:
        event_path.mkdir()
    (root / "raw.jsonl").write_bytes(b"")
    descriptor = _root(root)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)
        if socket_handle is not None:
            socket_handle.close()
        if short_root is not None:
            short_root.cleanup()
    assert caught.value.code == "unsafe_path_type"
    assert caught.value.ledger == "events"


def test_premature_eof_is_unstable_and_interrupted_short_reads_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    encoded = event_jsonl(_prepared(capsule))
    (tmp_path / "events.jsonl").write_bytes(encoded)
    (tmp_path / "raw.jsonl").write_bytes(b"")
    descriptor = _root(tmp_path)
    real_read = journal_module.os.read
    monkeypatch.setattr(journal_module.os, "read", lambda *_args: b"")
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)
    assert (caught.value.code, caught.value.row_index) == ("unstable_snapshot", 0)

    descriptor = _root(tmp_path)
    calls = 0

    def interrupted_then_short(descriptor_fd: int, count: int) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise InterruptedError
        return real_read(descriptor_fd, min(count, 7))

    monkeypatch.setattr(journal_module.os, "read", interrupted_then_short)
    try:
        snapshot = snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)
    assert snapshot.row_count == 1
    assert calls > 2


@pytest.mark.parametrize(
    ("reason", "field", "value", "expected_code"),
    [
        ("success", "attempt_id", "0" * 64, "identity_mismatch"),
        ("success", "retry_of_attempt", 1, "retry_mismatch"),
        ("success", "output_sha256", "0" * 64, "hash_mismatch"),
        ("success", "terminal", False, "lifecycle_mismatch"),
        ("success", "attempt", False, "invalid_model"),
        ("success", "attempt", 7, "retry_mismatch"),
        ("provider_rejected", "output_sha256", "0" * 64, "lifecycle_mismatch"),
    ],
)
def test_raw_model_failures_use_the_deterministic_verifier_taxonomy(
    reason: str,
    field: str,
    value: object,
    expected_code: str,
    tmp_path: object,
) -> None:
    _capsule, _manifest, _environment, plan = _context()
    payload = _attempt(plan[0], reason).model_dump(mode="json")
    payload[field] = value
    (tmp_path / "raw.jsonl").write_bytes(canonical_json(payload) + b"\n")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_raw_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        expected_code,
        "raw",
        0,
    )


@pytest.mark.parametrize(
    ("semantic_failure", "expected_code"),
    [
        ("retry_parent", "retry_mismatch"),
        ("recovered_session", "lifecycle_mismatch"),
    ],
)
def test_event_model_failures_use_the_deterministic_verifier_taxonomy(
    semantic_failure: str,
    expected_code: str,
    tmp_path: object,
) -> None:
    _capsule, _manifest, _environment, plan = _context()
    start = _start(plan[0])
    if semantic_failure == "retry_parent":
        payload = start.model_dump(mode="json")
        event_payload = payload["payload"]
        assert isinstance(event_payload, dict)
        event_payload["attempt"] = 2
    else:
        finish = make_event(
            sequence=3,
            run_id=RUN_ID,
            occurred_at=NOW,
            kind="request_finished",
            operation_id=EXECUTION_OPERATION,
            execution_session_id=SESSION_ID,
            payload={
                "call_sequence": start.payload.call_sequence,
                "plan_item_id": start.payload.plan_item_id,
                "attempt_id": start.payload.attempt_id,
                "request_started_event_id": start.event_id,
                "raw_record_sha256": "b" * 64,
                "recovered": False,
            },
        )
        payload = finish.model_dump(mode="json")
        event_payload = payload["payload"]
        assert isinstance(event_payload, dict)
        event_payload["recovered"] = True
    identity = dict(payload)
    identity.pop("event_id")
    payload["event_id"] = stable_digest("laconian-event-v1", identity)
    (tmp_path / "events.jsonl").write_bytes(canonical_json(payload) + b"\n")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        expected_code,
        "events",
        0,
    )


@pytest.mark.parametrize("name", ["events.jsonl", "raw.jsonl"])
def test_read_only_snapshot_rejects_torn_tail(name: str, tmp_path: object) -> None:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    (tmp_path / name).write_bytes(b"{}")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        os.close(descriptor)
    assert caught.value.code == "noncanonical_json"
    assert caught.value.ledger == ("events" if name.startswith("events") else "raw")
    assert str(caught.value) == "capsule journal rejected"


def test_nesting_limit_is_rejected_before_model_materialization(tmp_path: object) -> None:
    (tmp_path / "events.jsonl").write_bytes(b"[" * 65 + b"]" * 65 + b"\n")  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)
    assert caught.value.code == "resource_limit"
    assert caught.value.row_index == 0


def test_standalone_snapshot_rejects_oversized_metadata_before_streaming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "events.jsonl").write_bytes(b"")
    (tmp_path / "raw.jsonl").write_bytes(b"")
    os.truncate(
        tmp_path / "events.jsonl",
        RESOURCE_LIMITS_V1.mutable_capsule_bytes + 1,
    )
    descriptor = _root(tmp_path)
    monkeypatch.setattr(
        journal_module,
        "_rows",
        lambda *_args, **_kwargs: pytest.fail("oversized ledger was streamed"),
    )
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="report")
    finally:
        os.close(descriptor)
    assert caught.value.code == "resource_limit"
    assert caught.value.ledger == "events"


def test_transaction_rejects_aggregate_metadata_before_either_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "events.jsonl").write_bytes(b"")
    (tmp_path / "raw.jsonl").write_bytes(b"")
    half = RESOURCE_LIMITS_V1.mutable_capsule_bytes // 2 + 1
    os.truncate(tmp_path / "events.jsonl", half)
    os.truncate(tmp_path / "raw.jsonl", half)
    descriptor = _root(tmp_path)
    monkeypatch.setattr(
        journal_module,
        "snapshot_event_journal",
        lambda *_args, **_kwargs: pytest.fail("aggregate-oversized pair was streamed"),
    )
    try:
        with pytest.raises(JournalError) as caught:
            open_journal_transaction(
                descriptor,
                posix=cast(FilesystemPosixOps, _TransactionPosix()),
            )
    finally:
        os.close(descriptor)
    assert caught.value.code == "resource_limit"
    assert caught.value.ledger == "events"


@pytest.mark.parametrize("operation", ["read", "fstat", "close"])
def test_standalone_snapshot_normalizes_descriptor_failures(
    operation: str, tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    original = getattr(journal_module.os, operation)

    def fail(*args: object, **kwargs: object) -> object:
        raise OSError("TOP-SECRET-DESCRIPTOR-CANARY")

    monkeypatch.setattr(journal_module.os, operation, fail)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        monkeypatch.setattr(journal_module.os, operation, original)
        os.close(descriptor)
    assert caught.value.code == "io_error"
    assert "TOP-SECRET" not in repr(caught.value)


def test_standalone_snapshot_never_normalizes_process_death(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)

    class InjectedProcessDeath(SystemExit):
        pass

    def crash(*_args: object, **_kwargs: object) -> bytes:
        raise InjectedProcessDeath

    monkeypatch.setattr(journal_module.os, "read", crash)
    try:
        with pytest.raises(InjectedProcessDeath):
            snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)


def test_paired_snapshot_normalizes_seek_failure(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)

    def fail_seek(*args: object, **kwargs: object) -> int:
        raise OSError("TOP-SECRET-SEEK-CANARY")

    monkeypatch.setattr(journal_module.os, "lseek", fail_seek)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        os.close(descriptor)
    assert caught.value.code == "io_error"
    assert "TOP-SECRET" not in repr(caught.value)


@pytest.mark.parametrize(
    ("operation", "expected_code", "expected_row"),
    [
        ("read", "io_error", 0),
        ("lseek", "io_error", None),
        ("fstat", "io_error", None),
        ("stat", "unstable_snapshot", None),
        ("close", "io_error", None),
    ],
)
def test_paired_snapshot_attributes_raw_only_io_failures_to_raw_ledger(
    operation: str,
    expected_code: str,
    expected_row: int | None,
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    raw_path = tmp_path / "raw.jsonl"  # type: ignore[operator]
    raw_path.write_bytes(b"{}\n" if operation == "read" else b"")
    raw_identity = raw_path.stat().st_dev, raw_path.stat().st_ino
    descriptor = _root(tmp_path)

    original = getattr(journal_module.os, operation)
    real_fstat = journal_module.os.fstat
    raw_fstat_calls = 0
    raw_stat_calls = 0

    def is_raw_fd(fd: int) -> bool:
        metadata = real_fstat(fd)
        return (metadata.st_dev, metadata.st_ino) == raw_identity

    def fail_raw(*args: object, **kwargs: object) -> object:
        nonlocal raw_fstat_calls, raw_stat_calls
        if operation == "stat":
            if args and args[0] == "raw.jsonl":
                raw_stat_calls += 1
                if raw_stat_calls == 2:
                    raise OSError("TOP-SECRET-RAW-STAT-CANARY")
            return original(*args, **kwargs)
        fd = args[0]
        assert type(fd) is int
        if operation == "fstat":
            metadata = original(*args, **kwargs)
            if (metadata.st_dev, metadata.st_ino) == raw_identity:
                raw_fstat_calls += 1
                if raw_fstat_calls == 2:
                    raise OSError("TOP-SECRET-RAW-FSTAT-CANARY")
            return metadata
        if is_raw_fd(fd):
            if operation == "close":
                original(*args, **kwargs)
            raise OSError("TOP-SECRET-RAW-IO-CANARY")
        return original(*args, **kwargs)

    monkeypatch.setattr(journal_module.os, operation, fail_raw)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        monkeypatch.setattr(journal_module.os, operation, original)
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        expected_code,
        "raw",
        expected_row,
    )
    assert "TOP-SECRET" not in repr(caught.value)


def test_report_tail_returns_only_bounded_metadata(tmp_path: object) -> None:
    capsule, manifest, environment, plan = _context()
    tail = b'{"partial":"secret-canary"}'
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)) + tail)  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    try:
        snapshot = snapshot_journal_pair(
            descriptor,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="report",
        )
    finally:
        os.close(descriptor)
    assert snapshot.events.row_count == 1
    assert snapshot.events.tail_byte_count == len(tail)
    assert snapshot.events.tail_sha256 == __import__("hashlib").sha256(tail).hexdigest()
    assert "secret-canary" not in repr(snapshot)


def test_pass_three_fingerprint_detects_same_length_rewrite(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule, manifest, environment, plan = _context()
    path = tmp_path / "events.jsonl"  # type: ignore[operator]
    path.write_bytes(event_jsonl(_prepared(capsule)))
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    # Rebuild identity through the public factory while retaining byte length.
    from laconian_eval.capsule.events import make_prepared_event

    replacement = make_prepared_event(
        run_id=capsule.run_id,
        operation_id=UUID("12345678-1234-4abc-8def-1234567890b2"),
        occurred_at=capsule.created_at,
        manifest_sha256=capsule.manifest_sha256,
        input_index_sha256=capsule.input_index_sha256,
        case_index_sha256=capsule.case_index_sha256,
        plan_sha256=capsule.plan_sha256,
        environment_sha256=capsule.environment_sha256,
        runner_source_sha256=capsule.runner_source_sha256,
    )
    replacement_bytes = event_jsonl(replacement)
    assert len(replacement_bytes) == path.stat().st_size
    real_lseek = journal_module.os.lseek
    rewrote = False

    def rewrite_between_passes(fd: int, offset: int, whence: int) -> int:
        nonlocal rewrote
        result = real_lseek(fd, offset, whence)
        if not rewrote:
            rewrote = True
            path.write_bytes(replacement_bytes)
        return result

    monkeypatch.setattr(journal_module.os, "lseek", rewrite_between_passes)
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        os.close(descriptor)
    assert caught.value.code == "unstable_snapshot"
    assert caught.value.ledger == "events"


def test_pass_three_attributes_raw_only_rewrite_to_raw_ledger(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    path = tmp_path / "raw.jsonl"  # type: ignore[operator]
    path.write_bytes(b"")
    real_lseek = journal_module.os.lseek
    raw_identity = path.stat().st_dev, path.stat().st_ino
    rewrote = False

    def rewrite_raw_between_passes(fd: int, offset: int, whence: int) -> int:
        nonlocal rewrote
        result = real_lseek(fd, offset, whence)
        metadata = os.fstat(fd)
        if not rewrote and (metadata.st_dev, metadata.st_ino) == raw_identity:
            rewrote = True
            os.utime(
                path,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
            )
        return result

    monkeypatch.setattr(journal_module.os, "lseek", rewrite_raw_between_passes)
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_journal_pair(
                descriptor,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="reject",
            )
    finally:
        os.close(descriptor)

    assert caught.value.code == "unstable_snapshot"
    assert caught.value.ledger == "raw"


class _TransactionPosix:
    platform = "test"

    def __init__(self) -> None:
        self.synced: list[int] = []

    def fsync(self, descriptor: int) -> None:
        self.synced.append(descriptor)
        os.fsync(descriptor)


def _transaction_fixture(tmp_path: object) -> tuple[object, object, object, object]:
    capsule, manifest, environment, plan = _context()
    (tmp_path / "events.jsonl").write_bytes(event_jsonl(_prepared(capsule)))  # type: ignore[operator]
    (tmp_path / "raw.jsonl").write_bytes(b"")  # type: ignore[operator]
    return capsule, manifest, environment, plan


def test_transaction_retains_validated_descriptors_and_updates_cursors(tmp_path: object) -> None:
    _capsule, _manifest, environment, plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    try:
        with open_journal_transaction(
            descriptor,
            posix=cast(FilesystemPosixOps, posix),
        ) as transaction:
            initial_events = transaction.events
            initial_raw = transaction.raw
            assert initial_events.row_count == 1
            assert initial_events.last_lf_offset == initial_events.byte_length
            assert initial_raw.row_count == 0
            assert transaction.total_capsule_bytes == (
                initial_events.byte_length + initial_raw.byte_length
            )

            assert append_event(transaction, _execution_started(environment)) is None
            event_cursor = transaction.events
            assert append_event(transaction, _start(plan[0])) is None
            start_cursor = transaction.events
            assert append_raw_attempt(transaction, _attempt(plan[0], "success")) is None
            raw_cursor = transaction.raw

            assert event_cursor.row_count == 2
            assert start_cursor.row_count == 3
            assert raw_cursor.row_count == 1
            assert transaction.events == start_cursor
            assert transaction.raw == raw_cursor
            assert len(posix.synced) == 3
            event_identity = os.fstat(posix.synced[0]).st_ino
            raw_identity = os.fstat(posix.synced[-1]).st_ino
            assert event_identity == start_cursor.inode
            assert raw_identity == raw_cursor.inode
    finally:
        os.close(descriptor)

    assert (
        (tmp_path / "events.jsonl")
        .read_bytes()
        .endswith(  # type: ignore[operator]
            event_jsonl(_start(plan[0]))
        )
    )
    assert (tmp_path / "raw.jsonl").read_bytes() == raw_attempt_jsonl(  # type: ignore[operator]
        _attempt(plan[0], "success")
    )


def test_transaction_pair_snapshot_reuses_retained_descriptors(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule, manifest, environment, plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    try:
        with open_journal_transaction(
            descriptor,
            posix=cast(FilesystemPosixOps, posix),
        ) as transaction:
            monkeypatch.setattr(
                journal_module,
                "_open",
                lambda *_args, **_kwargs: pytest.fail("pair scan reopened a journal"),
            )
            monkeypatch.setattr(
                journal_module,
                "_open_update",
                lambda *_args, **_kwargs: pytest.fail("pair scan reopened a journal"),
            )
            snapshot = journal_module._snapshot_transaction_pair(
                transaction,
                history_context=HistoryContextV1(capsule, manifest, environment, plan),
                tail_policy="report",
                reserved_operation_id=_OTHER_OPERATION,
            )
    finally:
        os.close(descriptor)

    assert snapshot.events.inode == transaction.events.inode
    assert snapshot.raw.inode == transaction.raw.inode
    assert snapshot.reserved_operation_id == _OTHER_OPERATION


@pytest.mark.parametrize("tail_ledger", ["events", "raw"])
def test_transaction_refuses_append_while_either_ledger_has_a_tail(
    tail_ledger: str, tmp_path: object
) -> None:
    _capsule, _manifest, environment, _plan = _transaction_fixture(tmp_path)
    path = tmp_path / f"{tail_ledger}.jsonl"  # type: ignore[operator]
    with path.open("ab") as stream:
        stream.write(b'{"torn":"canary"}')
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    try:
        transaction = open_journal_transaction(
            descriptor,
            posix=cast(FilesystemPosixOps, posix),
        )
        try:
            with pytest.raises(JournalError) as caught:
                append_event(transaction, _execution_started(environment))
        finally:
            transaction.close()
    finally:
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger) == ("noncanonical_json", tail_ledger)
    assert posix.synced == []


@pytest.mark.parametrize("first_action", ["partial", "interrupted"])
def test_append_event_uses_a_full_write_loop_without_reopening(
    first_action: str, tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capsule, _manifest, environment, _plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, posix),
    )
    real_write = journal_module.os.write
    calls = 0

    def controlled_write(fd: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1 and first_action == "interrupted":
            raise InterruptedError
        if calls == 1:
            amount = max(1, len(data) // 2)
            return real_write(fd, data[:amount])
        return real_write(fd, data)

    monkeypatch.setattr(journal_module.os, "write", controlled_write)
    try:
        append_event(transaction, _execution_started(environment))
        cursor = transaction.events
    finally:
        transaction.close()
        os.close(descriptor)

    assert calls >= 2
    assert cursor.byte_length == len((tmp_path / "events.jsonl").read_bytes())  # type: ignore[operator]
    assert len(posix.synced) == 1


def test_zero_progress_write_poisoning_never_retries_the_row(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capsule, _manifest, environment, _plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, posix),
    )
    writes = 0

    def zero_write(_fd: int, _data: bytes) -> int:
        nonlocal writes
        writes += 1
        return 0

    monkeypatch.setattr(journal_module.os, "write", zero_write)
    try:
        with pytest.raises(JournalError) as first:
            append_event(transaction, _execution_started(environment))
        with pytest.raises(JournalError) as second:
            append_event(transaction, _execution_started(environment))
    finally:
        transaction.close()
        os.close(descriptor)

    assert writes == 1
    assert (first.value.code, first.value.ledger) == ("io_error", "events")
    assert (second.value.code, second.value.ledger) == ("io_error", "events")
    assert posix.synced == []


def _track_journal_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, int, int]]:
    real_open = journal_module.os.open
    calls: list[tuple[str, int, int]] = []

    def tracked_open(
        path: str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        calls.append((path, flags, descriptor))
        return descriptor

    monkeypatch.setattr(journal_module.os, "open", tracked_open)
    return calls


def test_transaction_adversarial_preflight_finishes_before_any_writable_open(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _transaction_fixture(tmp_path)
    (tmp_path / "raw.jsonl").write_bytes(b"{\n")  # type: ignore[operator]
    descriptor = _root(tmp_path)
    opens = _track_journal_opens(monkeypatch)
    try:
        with pytest.raises(JournalError) as caught:
            open_journal_transaction(
                descriptor,
                posix=cast(FilesystemPosixOps, _TransactionPosix()),
            )
    finally:
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger) == ("noncanonical_json", "raw")
    assert opens
    assert all(flags & os.O_ACCMODE != os.O_RDWR for _name, flags, _fd in opens)


def test_transaction_adversarial_retained_descriptors_use_exact_flags(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    opens = _track_journal_opens(monkeypatch)
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, _TransactionPosix()),
    )
    transaction.close()
    os.close(descriptor)

    retained = [(name, flags) for name, flags, _fd in opens if flags & os.O_ACCMODE == os.O_RDWR]
    expected_flags = os.O_RDWR | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    assert retained == [
        ("events.jsonl", expected_flags),
        ("raw.jsonl", expected_flags),
    ]


def test_transaction_adversarial_append_never_reopens_or_rereads_history(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capsule, _manifest, environment, _plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, _TransactionPosix()),
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("append reopened or reread a journal")

    monkeypatch.setattr(journal_module.os, "open", forbidden)
    monkeypatch.setattr(journal_module.os, "read", forbidden)
    try:
        append_event(transaction, _execution_started(environment))
        assert transaction.events.row_count == 2
    finally:
        transaction.close()
        os.close(descriptor)


def test_transaction_adversarial_path_replacement_preserves_both_inodes(
    tmp_path: object,
) -> None:
    _capsule, _manifest, environment, _plan = _transaction_fixture(tmp_path)
    event_path = tmp_path / "events.jsonl"  # type: ignore[operator]
    retained_path = tmp_path / "retained-events.jsonl"  # type: ignore[operator]
    initial = event_path.read_bytes()
    replacement = b"replacement-path-canary\n"
    descriptor = _root(tmp_path)
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, _TransactionPosix()),
    )
    event_path.rename(retained_path)
    event_path.write_bytes(replacement)
    try:
        with pytest.raises(JournalError) as caught:
            append_event(transaction, _execution_started(environment))
    finally:
        transaction.close()
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger) == ("unstable_snapshot", "events")
    assert retained_path.read_bytes() == initial
    assert event_path.read_bytes() == replacement


@pytest.mark.parametrize("ledger", ["events", "raw"])
def test_transaction_rejects_same_size_rewrite_before_append(
    ledger: str,
    tmp_path: object,
) -> None:
    _capsule, _manifest, environment, plan = _transaction_fixture(tmp_path)
    path = tmp_path / f"{ledger}.jsonl"  # type: ignore[operator]
    if ledger == "raw":
        path.write_bytes(raw_attempt_jsonl(_attempt(plan[0], "success")))
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, posix),
    )
    before = path.stat()
    rewritten = bytearray(path.read_bytes())
    rewritten[0] = ord("[") if rewritten[0] != ord("[") else ord("{")
    path.write_bytes(rewritten)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    try:
        with pytest.raises(JournalError) as caught:
            if ledger == "events":
                append_event(transaction, _execution_started(environment))
            else:
                payload = _attempt(plan[0], "success").model_dump(mode="python")
                payload["call_sequence"] = 1
                append_raw_attempt(transaction, RawAttemptV2.model_validate(payload))
    finally:
        transaction.close()
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger) == ("unstable_snapshot", ledger)
    assert path.read_bytes() == bytes(rewritten)
    assert posix.synced == []


@pytest.mark.parametrize("ledger", ["events", "raw"])
def test_transaction_adversarial_wrong_sequence_performs_no_write(
    ledger: str,
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capsule, _manifest, environment, plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, _TransactionPosix()),
    )
    before = transaction.events if ledger == "events" else transaction.raw
    writes = 0
    real_write = journal_module.os.write

    def tracked_write(fd: int, data: bytes) -> int:
        nonlocal writes
        writes += 1
        return real_write(fd, data)

    monkeypatch.setattr(journal_module.os, "write", tracked_write)
    try:
        with pytest.raises(JournalError) as caught:
            if ledger == "events":
                append_event(transaction, _execution_started(environment, sequence=2))
            else:
                attempt = _attempt(plan[0], "success")
                payload = attempt.model_dump(mode="python")
                payload["call_sequence"] = 1
                append_raw_attempt(transaction, RawAttemptV2.model_validate(payload))
    finally:
        transaction.close()
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger, caught.value.row_index) == (
        "history_mismatch",
        ledger,
        before.row_count,
    )
    assert writes == 0
    assert (transaction.events if ledger == "events" else transaction.raw) == before


@pytest.mark.parametrize("changed_ledger", ["events", "raw"])
def test_transaction_adversarial_growth_of_either_descriptor_poisons_before_write(
    changed_ledger: str,
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capsule, _manifest, environment, _plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, posix),
    )
    changed_path = tmp_path / f"{changed_ledger}.jsonl"  # type: ignore[operator]
    with changed_path.open("ab") as stream:
        stream.write(b"external-growth-canary")
    writes = 0

    def forbidden_write(_fd: int, _data: bytes) -> int:
        nonlocal writes
        writes += 1
        raise AssertionError("cursor mismatch reached write")

    monkeypatch.setattr(journal_module.os, "write", forbidden_write)
    try:
        with pytest.raises(JournalError) as first:
            append_event(transaction, _execution_started(environment))
        with pytest.raises(JournalError) as poisoned:
            append_event(transaction, _execution_started(environment))
    finally:
        transaction.close()
        os.close(descriptor)

    assert (first.value.code, first.value.ledger) == ("unstable_snapshot", changed_ledger)
    assert (poisoned.value.code, poisoned.value.ledger) == ("io_error", "events")
    assert writes == 0
    assert posix.synced == []


def test_transaction_adversarial_fsync_failure_is_single_and_cursor_stays_uncommitted(
    tmp_path: object,
) -> None:
    _capsule, _manifest, environment, _plan = _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    posix = _TransactionPosix()
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, posix),
    )
    initial = transaction.events
    calls: list[int] = []

    def failed_fsync(fd: int) -> None:
        calls.append(fd)
        raise OSError("TOP-SECRET-FSYNC-CANARY")

    posix.fsync = failed_fsync  # type: ignore[method-assign]
    try:
        with pytest.raises(JournalError) as caught:
            append_event(transaction, _execution_started(environment))
        with pytest.raises(JournalError):
            append_event(transaction, _execution_started(environment))
    finally:
        transaction.close()
        os.close(descriptor)

    assert (caught.value.code, caught.value.ledger) == ("io_error", "events")
    assert "TOP-SECRET" not in repr(caught.value)
    assert len(calls) == 1
    assert transaction.events == initial


def test_transaction_adversarial_close_is_idempotent_and_attempts_both_descriptors(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, _TransactionPosix()),
    )
    real_close = journal_module.os.close
    closes: list[int] = []

    def ambiguous_first_close(fd: int) -> None:
        closes.append(fd)
        real_close(fd)
        if len(closes) == 1:
            raise OSError("TOP-SECRET-CLOSE-CANARY")

    monkeypatch.setattr(journal_module.os, "close", ambiguous_first_close)
    with pytest.raises(JournalError) as caught:
        transaction.close()
    transaction.close()
    real_close(descriptor)

    assert (caught.value.code, caught.value.ledger) == ("io_error", "events")
    assert "TOP-SECRET" not in repr(caught.value)
    assert len(closes) == 2
    assert len(set(closes)) == 2


def test_transaction_adversarial_close_failure_does_not_mask_active_primary(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, _TransactionPosix()),
    )
    real_close = journal_module.os.close
    closes: list[int] = []
    primary = RuntimeError("PRIMARY-CANARY")

    def ambiguous_close(fd: int) -> None:
        closes.append(fd)
        real_close(fd)
        raise OSError("TOP-SECRET-CLOSE-CANARY")

    monkeypatch.setattr(journal_module.os, "close", ambiguous_close)
    with pytest.raises(RuntimeError) as caught, transaction:
        raise primary
    transaction.close()
    real_close(descriptor)

    assert caught.value is primary
    assert closes and len(closes) == 2
    assert len(set(closes)) == 2


def test_transaction_fatal_close_failure_overrides_active_ordinary_exception(
    tmp_path: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CloseCrash(BaseException):
        pass

    _transaction_fixture(tmp_path)
    descriptor = _root(tmp_path)
    transaction = open_journal_transaction(
        descriptor,
        posix=cast(FilesystemPosixOps, _TransactionPosix()),
    )
    real_close = journal_module.os.close
    closes: list[int] = []

    def fatal_close(fd: int) -> None:
        closes.append(fd)
        real_close(fd)
        raise CloseCrash

    monkeypatch.setattr(journal_module.os, "close", fatal_close)
    with pytest.raises(CloseCrash), transaction:
        raise RuntimeError("ordinary primary")
    transaction.close()
    real_close(descriptor)

    assert len(closes) == 2
    assert len(set(closes)) == 2


def test_reader_never_consumes_concurrent_growth_beyond_validated_size(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    path = tmp_path / "events.jsonl"  # type: ignore[operator]
    initial = event_jsonl(_prepared(capsule))
    path.write_bytes(initial)
    real_read = journal_module.os.read
    requested: list[int] = []
    returned = 0
    appended = False

    def append_during_read(descriptor: int, size: int) -> bytes:
        nonlocal appended, returned
        requested.append(size)
        data = real_read(descriptor, size)
        returned += len(data)
        if not appended:
            appended = True
            with path.open("ab") as stream:
                stream.write(b"x" * (2 * 64 * 1024))
        return data

    monkeypatch.setattr(journal_module.os, "read", append_during_read)
    descriptor = _root(tmp_path)
    try:
        with pytest.raises(JournalError) as caught:
            snapshot_event_journal(descriptor, tail_policy="reject")
    finally:
        os.close(descriptor)
    assert caught.value.code == "unstable_snapshot"
    assert requested == [len(initial)]
    assert returned == len(initial)
