from __future__ import annotations

import os
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
from laconian_eval.capsule.canonical import canonical_json, stable_digest
from laconian_eval.capsule.events import EventV1, event_jsonl, make_event
from laconian_eval.capsule.history import HistoryContextV1, HistoryError
from laconian_eval.capsule.journal import (
    JournalError,
    snapshot_event_journal,
    snapshot_journal_pair,
    snapshot_raw_journal,
)
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
