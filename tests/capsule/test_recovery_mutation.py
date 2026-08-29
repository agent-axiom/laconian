from __future__ import annotations

import hashlib
import inspect
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

import laconian_eval.capsule.journal as journal_module
import laconian_eval.capsule.recovery as recovery_module
from capsule.test_lifecycle import _attempt, _context, _execution_started, _prepared, _start
from capsule.test_prepare import _load_success
from laconian_eval.capsule.attempts import RawAttemptV2, raw_attempt_jsonl
from laconian_eval.capsule.events import EventV1, event_jsonl
from laconian_eval.capsule.filesystem import (
    PERSISTENT_LOCK_NAME,
    LockHandle,
    try_acquire_mutator_lock,
    try_acquire_shared_lock,
)
from laconian_eval.capsule.history import HistoryContextV1
from laconian_eval.capsule.journal import (
    JournalError,
    JournalTransaction,
    Ledger,
    open_journal_transaction,
    snapshot_journal_pair,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    EnvironmentV1,
    PlanRowV1,
)
from laconian_eval.capsule.recovery import (
    RecoveryContextV1,
    RecoveryError,
    plan_recovery_v1,
)

RECOVERY_OPERATION = UUID("12345678-1234-4abc-8def-1234567890d1")
RECOVERY_TIME = datetime(2026, 8, 29, 12, 30, tzinfo=UTC)
REPLAY_OPERATION = UUID("22345678-1234-4abc-8def-1234567890d2")
REPLAY_TIME = datetime(2026, 8, 29, 12, 31, tzinfo=UTC)
IDEMPOTENCE_OPERATION = UUID("32345678-1234-4abc-8def-1234567890d3")
IDEMPOTENCE_TIME = datetime(2026, 8, 29, 12, 32, tzinfo=UTC)


def _root(path: Path) -> int:
    return os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )


def _write_capsule(
    root: Path,
    *,
    event_rows: tuple[EventV1, ...],
    raw_rows: tuple[RawAttemptV2, ...] = (),
    event_tail: bytes = b"",
    raw_tail: bytes = b"",
) -> None:
    (root / "events.jsonl").write_bytes(
        b"".join(event_jsonl(row) for row in event_rows) + event_tail
    )
    (root / "raw.jsonl").write_bytes(
        b"".join(raw_attempt_jsonl(row) for row in raw_rows) + raw_tail
    )
    lock_path = root / PERSISTENT_LOCK_NAME
    lock_path.write_bytes(b"")
    os.chmod(lock_path, 0o600)


def _fake_verified_proof(
    root_fd: int,
    *,
    parent_fd: int,
    destination_name: str,
    operation_id: UUID,
    history_context: HistoryContextV1,
    immutable_evidence_bytes: int,
) -> object:
    pair = snapshot_journal_pair(
        root_fd,
        history_context=history_context,
        tail_policy="report",
        reserved_operation_id=operation_id,
    )
    root = os.fstat(root_fd)
    parent = os.fstat(parent_fd)
    identity = recovery_module._stat_identity
    return recovery_module._VerifiedRecoveryProofV1(
        history_context,
        pair,
        immutable_evidence_bytes,
        identity(root),
        identity(parent),
        destination_name,
        "0" * 64,
        object(),
    )


class _OpenedRecovery:
    def __init__(
        self,
        *,
        root_fd: int,
        transaction: JournalTransaction,
        lock: LockHandle,
        session: object,
        sync_actions: list[int],
        capsule: CapsuleV1,
        manifest: ResolvedManifestV2,
        environment: EnvironmentV1,
        plan: tuple[PlanRowV1, ...],
    ) -> None:
        self.root_fd = root_fd
        self.transaction = transaction
        self.lock = lock
        self.session = session
        self.sync_actions = sync_actions
        self.capsule = capsule
        self.manifest = manifest
        self.environment = environment
        self.plan = plan

    @property
    def history_context(self) -> HistoryContextV1:
        return HistoryContextV1(
            self.capsule,
            self.manifest,
            self.environment,
            self.plan,
        )

    def ledger_for(self, descriptor: int) -> str:
        inode = os.fstat(descriptor).st_ino
        if inode == self.transaction.events.inode:
            return "events"
        if inode == self.transaction.raw.inode:
            return "raw"
        pytest.fail("recovery touched a descriptor outside the retained journal pair")


@contextmanager
def _opened_recovery(
    root: Path,
    *,
    immutable_evidence_bytes: int = 0,
    io_actions: list[tuple[str, str]] | None = None,
    after_io_action: Callable[[str, str], None] | None = None,
    operation_id: UUID = RECOVERY_OPERATION,
    occurred_at: datetime = RECOVERY_TIME,
) -> Iterator[_OpenedRecovery]:
    capsule, manifest, environment, plan = _context()
    root_fd = _root(root)
    parent_fd = _root(root.parent)
    sync_actions: list[int] = []
    transaction: JournalTransaction | None = None

    def fsync(descriptor: int) -> None:
        if transaction is None or descriptor not in {
            transaction._event_fd,
            transaction._raw_fd,
        }:
            os.fsync(descriptor)
            return
        sync_actions.append(descriptor)
        ledger: str | None = None
        if io_actions is not None:
            inode = os.fstat(descriptor).st_ino
            ledger = "events" if inode == transaction.events.inode else "raw"
            io_actions.append(("fsync", ledger))
        os.fsync(descriptor)
        if after_io_action is not None:
            if ledger is None:
                inode = os.fstat(descriptor).st_ino
                ledger = "events" if inode == transaction.events.inode else "raw"
            after_io_action("fsync", ledger)

    posix = PosixOps(fsync_fn=fsync)
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    try:
        history_context = HistoryContextV1(capsule, manifest, environment, plan)

        def load_verified(
            candidate_root_fd: int,
            *,
            parent_fd: int,
            destination_name: str,
            reserved_operation_id: UUID,
        ) -> object:
            assert candidate_root_fd == root_fd
            return _fake_verified_proof(
                root_fd,
                parent_fd=parent_fd,
                destination_name=destination_name,
                operation_id=reserved_operation_id,
                history_context=history_context,
                immutable_evidence_bytes=immutable_evidence_bytes,
            )

        make_session = recovery_module._make_mutator_session_v1
        with (
            patch.object(
                recovery_module,
                "_load_verified_recovery_context",
                load_verified,
            ),
            patch.object(recovery_module, "_new_mutator_posix", lambda: posix),
            patch.object(
                recovery_module,
                "_is_native_mutator_posix",
                lambda candidate: candidate is posix,
            ),
        ):
            session = make_session(
                root_fd,
                parent_fd=parent_fd,
                destination_name=root.name,
                operation_id=operation_id,
                occurred_at=occurred_at,
                lock_handle=lock,
            )
            sync_actions.clear()
            transaction = session.transaction
            yield _OpenedRecovery(
                root_fd=root_fd,
                transaction=transaction,
                lock=lock,
                session=session,
                sync_actions=sync_actions,
                capsule=capsule,
                manifest=manifest,
                environment=environment,
                plan=plan,
            )
    except BaseException as error:
        primary = error
        raise
    else:
        primary = None
    finally:
        cleanup_error: BaseException | None = None
        if transaction is not None:
            try:
                transaction.close()
            except BaseException as error:
                cleanup_error = error
        try:
            lock.close()
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
        try:
            os.close(root_fd)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
        try:
            os.close(parent_fd)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
        if primary is None and cleanup_error is not None:
            raise cleanup_error


def test_recovery_mutates_both_tails_and_appends_audits_then_required_markers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "success")
    event_tail = b'{"torn-event":"canary"}'
    raw_tail = b'{"torn-raw":"canary"}'
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
        event_tail=event_tail,
        raw_tail=raw_tail,
    )
    real_truncate = recovery_module._truncate_session_tail
    truncate_actions: list[tuple[str, int]] = []
    io_actions: list[tuple[str, str]] = []

    def truncate(session: object, truncation: object) -> None:
        assert type(truncation) is recovery_module.TailTruncationV1
        truncate_actions.append((truncation.ledger, truncation.truncate_to))
        io_actions.append(("ftruncate", truncation.ledger))
        real_truncate(session, truncation)  # type: ignore[arg-type]

    monkeypatch.setattr(recovery_module, "_truncate_session_tail", truncate)
    with _opened_recovery(tmp_path, io_actions=io_actions) as opened:
        applied = recovery_module._recover_journals_v1(opened.session)

        assert io_actions == [
            ("ftruncate", "events"),
            ("fsync", "events"),
            ("ftruncate", "raw"),
            ("fsync", "raw"),
            ("fsync", "events"),
            ("fsync", "events"),
            ("fsync", "events"),
            ("fsync", "events"),
        ]
        assert truncate_actions == [
            (
                "events",
                len(
                    event_jsonl(_prepared(capsule))
                    + event_jsonl(_execution_started(environment))
                    + event_jsonl(start)
                ),
            ),
            ("raw", len(raw_attempt_jsonl(attempt))),
        ]
        assert len(opened.sync_actions) == 6
        assert applied.disposition == "complete"
        assert applied.appended_event_count == 4

        post = snapshot_journal_pair(
            opened.root_fd,
            history_context=opened.history_context,
            tail_policy="report",
        )
        assert post.events.tail_byte_count == 0
        assert post.raw.tail_byte_count == 0
        assert post.history.recovery_requirements == ()
        assert post.lifecycle.state == "GENERATION_COMPLETE"

    kinds = tuple(
        json.loads(row)["kind"] for row in (tmp_path / "events.jsonl").read_bytes().splitlines()
    )
    assert kinds[-4:] == (
        "tail_recovered",
        "tail_recovered",
        "request_finished",
        "generation_completed",
    )
    assert (tmp_path / "raw.jsonl").read_bytes() == raw_attempt_jsonl(attempt)


def test_same_size_rewrite_after_session_scan_is_rejected_before_first_truncate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    original_tail = b'{"torn":"A"}'
    rewritten_tail = b'{"torn":"B"}'
    assert len(original_tail) == len(rewritten_tail)
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule),),
        event_tail=original_tail,
    )

    with _opened_recovery(tmp_path) as opened:
        event_path = tmp_path / "events.jsonl"
        before = event_path.stat()
        rewritten = event_path.read_bytes()[: -len(original_tail)] + rewritten_tail
        event_path.write_bytes(rewritten)
        os.utime(event_path, ns=(before.st_atime_ns, before.st_mtime_ns))

        monkeypatch.setattr(
            recovery_module,
            "_truncate_session_tail",
            lambda *_args, **_kwargs: pytest.fail(
                "recovery truncated after a changed joint snapshot"
            ),
        )
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(opened.session)

        assert caught.value.code == "unstable_snapshot"
        assert opened.sync_actions == []
        assert event_path.read_bytes() == rewritten


def test_same_size_rewrite_after_local_plan_is_caught_by_joint_hash_recheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    original_tail = b'{"torn":"A"}'
    rewritten_tail = b'{"torn":"B"}'
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule),),
        event_tail=original_tail,
    )

    with _opened_recovery(tmp_path) as opened:
        event_path = tmp_path / "events.jsonl"
        real_planner = recovery_module.plan_recovery_v1
        real_final_fstat = journal_module._final_fstat
        real_final_path_stat = journal_module._final_path_stat
        stable_metadata = os.fstat(opened.transaction._event_fd)
        rewritten = False

        def rewrite_after_plan(**kwargs: object) -> object:
            nonlocal rewritten
            local_plan = real_planner(**kwargs)  # type: ignore[arg-type]
            before = event_path.stat()
            changed = event_path.read_bytes()[: -len(original_tail)] + rewritten_tail
            event_path.write_bytes(changed)
            os.utime(event_path, ns=(before.st_atime_ns, before.st_mtime_ns))
            rewritten = True
            return local_plan

        def hide_changed_descriptor_metadata(descriptor: int, ledger: Ledger) -> os.stat_result:
            if rewritten and ledger == "events":
                return stable_metadata
            return real_final_fstat(descriptor, ledger)

        def hide_changed_path_metadata(capsule_fd: int, ledger: Ledger) -> os.stat_result:
            if rewritten and ledger == "events":
                return stable_metadata
            return real_final_path_stat(capsule_fd, ledger)

        monkeypatch.setattr(recovery_module, "plan_recovery_v1", rewrite_after_plan)
        monkeypatch.setattr(
            journal_module,
            "_final_fstat",
            hide_changed_descriptor_metadata,
        )
        monkeypatch.setattr(
            journal_module,
            "_final_path_stat",
            hide_changed_path_metadata,
        )
        monkeypatch.setattr(
            recovery_module,
            "_truncate_session_tail",
            lambda *_args, **_kwargs: pytest.fail(
                "recovery truncated after the post-plan whole-file rewrite"
            ),
        )
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(opened.session)

        assert caught.value.code == "unstable_snapshot"
        assert opened.sync_actions == []


def test_capacity_failure_is_atomic_before_any_tail_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    tail = b'{"torn":"capacity"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    original_events = (tmp_path / "events.jsonl").read_bytes()
    original_raw = (tmp_path / "raw.jsonl").read_bytes()
    immutable_bytes = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes - len(original_events) - len(original_raw)
    )

    with _opened_recovery(
        tmp_path,
        immutable_evidence_bytes=immutable_bytes,
    ) as opened:
        monkeypatch.setattr(
            recovery_module,
            "_truncate_session_tail",
            lambda *_args, **_kwargs: pytest.fail("capacity was checked after truncation"),
        )
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(opened.session)

        assert caught.value.code == "resource_limit"
        assert opened.sync_actions == []
        assert (tmp_path / "events.jsonl").read_bytes() == original_events
        assert (tmp_path / "raw.jsonl").read_bytes() == original_raw


def test_path_replacement_after_joint_recheck_never_redirects_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    tail = b'{"torn":"path-race"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    replacement = b"replacement-path-must-remain-untouched"
    retained_path = tmp_path / "retained-events.jsonl"
    event_path = tmp_path / "events.jsonl"
    original_events = event_path.read_bytes()

    with _opened_recovery(tmp_path) as opened:
        joint_recheck = recovery_module._joint_recheck_transaction_pair

        def replace_after_recheck(*args: object, **kwargs: object) -> object:
            proof = joint_recheck(*args, **kwargs)
            event_path.rename(retained_path)
            event_path.write_bytes(replacement)
            return proof

        monkeypatch.setattr(
            recovery_module,
            "_joint_recheck_transaction_pair",
            replace_after_recheck,
        )
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(opened.session)
        assert caught.value.code == "unstable_snapshot"

    assert event_path.read_bytes() == replacement
    assert retained_path.read_bytes() == original_events


def test_forged_public_plan_has_no_mutation_entrypoint_or_accepted_parameter(
    tmp_path: Path,
) -> None:
    capsule, manifest, environment, plan = _context()
    tail = b'{"torn":"forged-plan"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    original = (tmp_path / "events.jsonl").read_bytes()
    root_fd = _root(tmp_path)
    try:
        pair = snapshot_journal_pair(
            root_fd,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="report",
        )
    finally:
        os.close(root_fd)
    context = RecoveryContextV1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        immutable_evidence_bytes=0,
        history=pair.history,
        lifecycle=pair.lifecycle,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
    )
    local_plan = plan_recovery_v1(
        context=context,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
        operation_id=RECOVERY_OPERATION,
        occurred_at=RECOVERY_TIME,
    )
    with pytest.raises(RecoveryError):
        replace(
            local_plan,
            truncations=(replace(local_plan.truncations[0], truncate_to=0),),
        )

    make_session = recovery_module._make_mutator_session_v1
    recover = recovery_module._recover_journals_v1
    assert tuple(inspect.signature(make_session).parameters) == (
        "capsule_fd",
        "parent_fd",
        "destination_name",
        "operation_id",
        "occurred_at",
        "lock_handle",
    )
    assert tuple(inspect.signature(recover).parameters) == ("session",)
    assert "_recover_journals_v1" not in recovery_module.__all__
    assert not hasattr(recovery_module, "recover_journals_v1")
    assert not hasattr(recovery_module, "apply_recovery_v1")

    with _opened_recovery(tmp_path) as opened:
        with pytest.raises(TypeError):
            recover(opened.session, plan=local_plan)
        assert opened.sync_actions == []
        assert (tmp_path / "events.jsonl").read_bytes() == original


@pytest.mark.parametrize("lock_kind", ["shared", "closed_exclusive"])
def test_session_factory_rejects_wrong_or_closed_lock_capability(
    lock_kind: str,
    tmp_path: Path,
) -> None:
    capsule, manifest, environment, plan = _context()
    tail = b'{"torn":"lock-authority"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    original = (tmp_path / "events.jsonl").read_bytes()
    root_fd = _root(tmp_path)
    parent_fd = _root(tmp_path.parent)
    posix = PosixOps()
    if lock_kind == "shared":
        lock = try_acquire_shared_lock(root_fd, posix=posix)
    else:
        lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    if lock_kind == "closed_exclusive":
        lock.close()
    try:
        history_context = HistoryContextV1(capsule, manifest, environment, plan)

        def load_verified(
            candidate_root_fd: int,
            *,
            parent_fd: int,
            destination_name: str,
            reserved_operation_id: UUID,
        ) -> object:
            return _fake_verified_proof(
                candidate_root_fd,
                parent_fd=parent_fd,
                destination_name=destination_name,
                operation_id=reserved_operation_id,
                history_context=history_context,
                immutable_evidence_bytes=0,
            )

        with (
            patch.object(
                recovery_module,
                "_load_verified_recovery_context",
                load_verified,
            ),
            pytest.raises(RecoveryError) as caught,
        ):
            recovery_module._make_mutator_session_v1(
                root_fd,
                parent_fd=parent_fd,
                destination_name=tmp_path.name,
                operation_id=RECOVERY_OPERATION,
                occurred_at=RECOVERY_TIME,
                lock_handle=lock,
            )
        assert caught.value.code == "identity_mismatch"
        assert (tmp_path / "events.jsonl").read_bytes() == original
    finally:
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_session_factory_runs_fresh_probe_before_capsule_read_and_cleans_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),))
    original_events = (tmp_path / "events.jsonl").read_bytes()
    original_raw = (tmp_path / "raw.jsonl").read_bytes()
    root_fd = _root(tmp_path)
    parent_fd = _root(tmp_path.parent)
    posix = PosixOps()
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    probe_calls = 0

    def reject_probe(*_args: object, **_kwargs: object) -> object:
        nonlocal probe_calls
        probe_calls += 1
        raise RuntimeError("injected probe failure")

    def capsule_read_bomb(*_args: object, **_kwargs: object) -> object:
        pytest.fail("capsule evidence read after filesystem preflight failed")

    monkeypatch.setattr(recovery_module, "run_filesystem_probes", reject_probe)
    monkeypatch.setattr(
        recovery_module,
        "_load_verified_recovery_context",
        capsule_read_bomb,
    )
    try:
        with pytest.raises(RecoveryError) as caught:
            recovery_module._make_mutator_session_v1(
                root_fd,
                parent_fd=parent_fd,
                destination_name=tmp_path.name,
                operation_id=RECOVERY_OPERATION,
                occurred_at=RECOVERY_TIME,
                lock_handle=lock,
            )
        assert caught.value.code == "identity_mismatch"
        assert probe_calls == 1
        assert not (tmp_path.parent / f".laconian-stage.{RECOVERY_OPERATION}").exists()
        assert (tmp_path / "events.jsonl").read_bytes() == original_events
        assert (tmp_path / "raw.jsonl").read_bytes() == original_raw
    finally:
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_direct_session_construction_cannot_bypass_fresh_recovery_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, manifest, environment, plan = _context()
    tail = b'{"tail":"direct-session-forgery"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    original_events = (tmp_path / "events.jsonl").read_bytes()
    root_fd = _root(tmp_path)
    parent_fd = _root(tmp_path.parent)
    posix = PosixOps()
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    transaction: JournalTransaction | None = None
    try:
        history_context = HistoryContextV1(capsule, manifest, environment, plan)
        proof = _fake_verified_proof(
            root_fd,
            parent_fd=parent_fd,
            destination_name=tmp_path.name,
            operation_id=RECOVERY_OPERATION,
            history_context=history_context,
            immutable_evidence_bytes=0,
        )
        transaction = open_journal_transaction(
            root_fd,
            posix=posix,
            immutable_evidence_bytes=0,
        )
        pair = recovery_module._snapshot_transaction_pair(
            transaction,
            history_context=history_context,
            tail_policy="report",
            reserved_operation_id=RECOVERY_OPERATION,
        )
        forged = recovery_module._MutatorSessionV1(
            transaction,
            proof,
            RECOVERY_OPERATION,
            RECOVERY_TIME,
            lock,
            parent_fd,
            pair,
        )
        probe_calls = 0

        def reject_probe(*_args: object, **_kwargs: object) -> object:
            nonlocal probe_calls
            probe_calls += 1
            raise RuntimeError("forged session probe canary")

        monkeypatch.setattr(recovery_module, "run_filesystem_probes", reject_probe)
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(forged)
        assert caught.value.code == "identity_mismatch"
        assert probe_calls == 1
        assert (tmp_path / "events.jsonl").read_bytes() == original_events
    finally:
        if transaction is not None:
            transaction.close()
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_incomplete_capsule_is_rejected_before_any_writable_journal_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    tail = b'{"torn":"missing-static-preflight"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    original_events = (tmp_path / "events.jsonl").read_bytes()
    original_raw = (tmp_path / "raw.jsonl").read_bytes()
    root_fd = _root(tmp_path)
    parent_fd = _root(tmp_path.parent)
    posix = PosixOps()
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None

    def writable_open_bomb(*_args: object, **_kwargs: object) -> object:
        pytest.fail("writable journals opened before complete static verification")

    monkeypatch.setattr(
        recovery_module,
        "open_journal_transaction",
        writable_open_bomb,
    )
    try:
        with pytest.raises(RecoveryError) as caught:
            recovery_module._make_mutator_session_v1(
                root_fd,
                parent_fd=parent_fd,
                destination_name=tmp_path.name,
                operation_id=RECOVERY_OPERATION,
                occurred_at=RECOVERY_TIME,
                lock_handle=lock,
            )
        assert caught.value.code == "invalid_model"
        assert (tmp_path / "events.jsonl").read_bytes() == original_events
        assert (tmp_path / "raw.jsonl").read_bytes() == original_raw
    finally:
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_fake_factory_proof_cannot_bypass_fresh_production_preflight(
    tmp_path: Path,
) -> None:
    capsule, manifest, environment, plan = _context()
    tail = b'{"torn":"fresh-static-preflight"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    original_events = (tmp_path / "events.jsonl").read_bytes()
    root_fd = _root(tmp_path)
    parent_fd = _root(tmp_path.parent)
    posix = PosixOps()
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    history_context = HistoryContextV1(capsule, manifest, environment, plan)

    def load_fake(
        candidate_root_fd: int,
        *,
        parent_fd: int,
        destination_name: str,
        reserved_operation_id: UUID,
    ) -> object:
        return _fake_verified_proof(
            candidate_root_fd,
            parent_fd=parent_fd,
            destination_name=destination_name,
            operation_id=reserved_operation_id,
            history_context=history_context,
            immutable_evidence_bytes=0,
        )

    session: object | None = None
    try:
        with patch.object(
            recovery_module,
            "_load_verified_recovery_context",
            load_fake,
        ):
            session = recovery_module._make_mutator_session_v1(
                root_fd,
                parent_fd=parent_fd,
                destination_name=tmp_path.name,
                operation_id=RECOVERY_OPERATION,
                occurred_at=RECOVERY_TIME,
                lock_handle=lock,
            )
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(session)  # type: ignore[arg-type]
        assert caught.value.code == "unstable_snapshot"
        assert (tmp_path / "events.jsonl").read_bytes() == original_events
    finally:
        if session is not None:
            session.transaction.close()  # type: ignore[attr-defined]
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_real_prepared_capsule_uses_descriptor_verified_recovery_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_success(tmp_path, monkeypatch)
    capsule_path = prepared.path
    event_path = capsule_path / "events.jsonl"
    raw_path = capsule_path / "raw.jsonl"
    tail = b'{"real-prepared-tail":"canary"}'
    event_path.write_bytes(event_path.read_bytes() + tail)
    original_raw = raw_path.read_bytes()
    root_fd = _root(capsule_path)
    parent_fd = _root(capsule_path.parent)
    posix = PosixOps()
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    real_probe = recovery_module.run_filesystem_probes
    probe_calls: list[tuple[int, int]] = []

    def observed_probe(
        candidate_root_fd: int,
        staging: object,
        **kwargs: object,
    ) -> object:
        probe_calls.append((candidate_root_fd, staging.parent_directory_fd))  # type: ignore[attr-defined]
        return real_probe(candidate_root_fd, staging, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(recovery_module, "run_filesystem_probes", observed_probe)
    session: object | None = None
    try:
        session = recovery_module._make_mutator_session_v1(
            root_fd,
            parent_fd=parent_fd,
            destination_name=capsule_path.name,
            operation_id=RECOVERY_OPERATION,
            occurred_at=RECOVERY_TIME,
            lock_handle=lock,
        )
        applied = recovery_module._recover_journals_v1(session)  # type: ignore[arg-type]
        assert applied.disposition == "provider_ready"
        assert applied.appended_event_count == 1
        assert applied.events.tail_byte_count == 0
        assert applied.raw.tail_byte_count == 0
        assert raw_path.read_bytes() == original_raw
        assert probe_calls == [(root_fd, parent_fd), (root_fd, parent_fd)]
        rows = tuple(json.loads(row) for row in event_path.read_bytes().splitlines())
        assert rows[-1]["kind"] == "tail_recovered"
        assert rows[-1]["payload"]["removed_sha256"] == hashlib.sha256(tail).hexdigest()
    finally:
        if session is not None:
            session.transaction.close()  # type: ignore[attr-defined]
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_factory_rebinds_forged_posix_adapter_to_native_lock_and_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_success(tmp_path, monkeypatch)
    capsule_path = prepared.path
    root_fd = _root(capsule_path)
    parent_fd = _root(capsule_path.parent)
    fake_flock_calls = 0
    fake_fsync_calls = 0

    def fake_flock(_descriptor: int, _operation: int) -> None:
        nonlocal fake_flock_calls
        fake_flock_calls += 1

    def fake_fsync(_descriptor: int) -> None:
        nonlocal fake_fsync_calls
        fake_fsync_calls += 1

    forged_posix = PosixOps(flock_fn=fake_flock, fsync_fn=fake_fsync)
    lock = try_acquire_mutator_lock(root_fd, posix=forged_posix)
    assert lock is not None
    session: object | None = None
    try:
        session = recovery_module._make_mutator_session_v1(
            root_fd,
            parent_fd=parent_fd,
            destination_name=capsule_path.name,
            operation_id=RECOVERY_OPERATION,
            occurred_at=RECOVERY_TIME,
            lock_handle=lock,
        )
        assert lock._posix is session.transaction._posix  # type: ignore[attr-defined]
        assert lock._posix is not forged_posix
        assert recovery_module._is_native_mutator_posix(lock._posix)
        assert fake_flock_calls == 1
        assert fake_fsync_calls == 0
    finally:
        if session is not None:
            session.transaction.close()  # type: ignore[attr-defined]
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_nested_native_posix_tampering_is_rejected_before_recovery_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_success(tmp_path, monkeypatch)
    capsule_path = prepared.path
    event_path = capsule_path / "events.jsonl"
    event_path.write_bytes(event_path.read_bytes() + b'{"tail":"nested-posix-tamper"}')
    original_events = event_path.read_bytes()
    root_fd = _root(capsule_path)
    parent_fd = _root(capsule_path.parent)
    lock = try_acquire_mutator_lock(root_fd, posix=PosixOps())
    assert lock is not None
    session: object | None = None
    try:
        session = recovery_module._make_mutator_session_v1(
            root_fd,
            parent_fd=parent_fd,
            destination_name=capsule_path.name,
            operation_id=RECOVERY_OPERATION,
            occurred_at=RECOVERY_TIME,
            lock_handle=lock,
        )
        runtime = session.transaction._posix  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            runtime.fsync = lambda _descriptor: None
        object.__setattr__(runtime, "_fsync", lambda _descriptor: None)
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(session)  # type: ignore[arg-type]
        assert caught.value.code == "identity_mismatch"
        assert event_path.read_bytes() == original_events
    finally:
        if session is not None:
            session.transaction.close()  # type: ignore[attr-defined]
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_static_rewrite_after_local_plan_is_rejected_before_truncate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_success(tmp_path, monkeypatch)
    capsule_path = prepared.path
    event_path = capsule_path / "events.jsonl"
    event_path.write_bytes(event_path.read_bytes() + b'{"tail":"static-race"}')
    original_events = event_path.read_bytes()
    root_fd = _root(capsule_path)
    parent_fd = _root(capsule_path.parent)
    posix = PosixOps()
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    session: object | None = None
    try:
        session = recovery_module._make_mutator_session_v1(
            root_fd,
            parent_fd=parent_fd,
            destination_name=capsule_path.name,
            operation_id=RECOVERY_OPERATION,
            occurred_at=RECOVERY_TIME,
            lock_handle=lock,
        )
        manifest_path = capsule_path / "manifest.json"
        real_planner = recovery_module.plan_recovery_v1

        def rewrite_static_after_plan(**kwargs: object) -> object:
            local_plan = real_planner(**kwargs)  # type: ignore[arg-type]
            before = manifest_path.stat()
            changed = bytearray(manifest_path.read_bytes())
            changed[0] = ord("[")
            manifest_path.write_bytes(changed)
            os.utime(manifest_path, ns=(before.st_atime_ns, before.st_mtime_ns))
            return local_plan

        monkeypatch.setattr(
            recovery_module,
            "plan_recovery_v1",
            rewrite_static_after_plan,
        )
        monkeypatch.setattr(
            recovery_module,
            "_truncate_session_tail",
            lambda *_args, **_kwargs: pytest.fail(
                "recovery truncated after immutable static evidence changed"
            ),
        )
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(session)  # type: ignore[arg-type]
        assert caught.value.code in {
            "invalid_model",
            "noncanonical_json",
            "unstable_snapshot",
        }
        assert event_path.read_bytes() == original_events
    finally:
        if session is not None:
            session.transaction.close()  # type: ignore[attr-defined]
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


def test_static_rewrite_after_joint_recheck_is_rejected_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest = _load_success(tmp_path, monkeypatch)
    capsule_path = prepared.path
    event_path = capsule_path / "events.jsonl"
    event_path.write_bytes(event_path.read_bytes() + b'{"tail":"post-joint-static-race"}')
    original_events = event_path.read_bytes()
    root_fd = _root(capsule_path)
    parent_fd = _root(capsule_path.parent)
    posix = PosixOps()
    lock = try_acquire_mutator_lock(root_fd, posix=posix)
    assert lock is not None
    session: object | None = None
    try:
        session = recovery_module._make_mutator_session_v1(
            root_fd,
            parent_fd=parent_fd,
            destination_name=capsule_path.name,
            operation_id=RECOVERY_OPERATION,
            occurred_at=RECOVERY_TIME,
            lock_handle=lock,
        )
        manifest_path = capsule_path / "manifest.json"
        real_joint_recheck = recovery_module._joint_recheck_transaction_pair

        def rewrite_after_joint(*args: object, **kwargs: object) -> None:
            real_joint_recheck(*args, **kwargs)  # type: ignore[arg-type]
            before = manifest_path.stat()
            changed = bytearray(manifest_path.read_bytes())
            changed[0] = ord("[")
            manifest_path.write_bytes(changed)
            os.utime(manifest_path, ns=(before.st_atime_ns, before.st_mtime_ns))

        monkeypatch.setattr(
            recovery_module,
            "_joint_recheck_transaction_pair",
            rewrite_after_joint,
        )
        monkeypatch.setattr(
            recovery_module,
            "_truncate_session_tail",
            lambda *_args, **_kwargs: pytest.fail(
                "recovery truncated after post-joint static evidence changed"
            ),
        )
        with pytest.raises(RecoveryError) as caught:
            recovery_module._recover_journals_v1(session)  # type: ignore[arg-type]
        assert caught.value.code in {
            "invalid_model",
            "noncanonical_json",
            "unstable_snapshot",
        }
        assert event_path.read_bytes() == original_events
    finally:
        if session is not None:
            session.transaction.close()  # type: ignore[attr-defined]
        lock.close()
        os.close(root_fd)
        os.close(parent_fd)


class _InjectedCrash(SystemExit):
    """A process-death stand-in that production must never normalize or retry."""


class _CrashAfterAction:
    def __init__(self, target: tuple[str, str, int]) -> None:
        self.target = target
        self.counts: dict[tuple[str, str], int] = {}
        self.observed: list[tuple[str, str, int]] = []
        self.crashed = False

    def after(self, kind: str, ledger: str) -> None:
        key = (kind, ledger)
        occurrence = self.counts.get(key, 0) + 1
        self.counts[key] = occurrence
        action = (kind, ledger, occurrence)
        self.observed.append(action)
        if not self.crashed and action == self.target:
            self.crashed = True
            raise _InjectedCrash


def test_crash_before_first_mutation_recomputes_identical_local_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    tail = b'{"tail":"before-first-mutation"}'
    _write_capsule(tmp_path, event_rows=(_prepared(capsule),), event_tail=tail)
    original_events = (tmp_path / "events.jsonl").read_bytes()
    original_raw = (tmp_path / "raw.jsonl").read_bytes()
    real_planner = recovery_module.plan_recovery_v1
    real_joint_recheck = recovery_module._joint_recheck_transaction_pair
    plans: list[object] = []

    def capture_plan(**kwargs: object) -> object:
        plan = real_planner(**kwargs)  # type: ignore[arg-type]
        plans.append(plan)
        return plan

    def crash_after_joint_recheck(*args: object, **kwargs: object) -> None:
        real_joint_recheck(*args, **kwargs)  # type: ignore[arg-type]
        raise _InjectedCrash

    monkeypatch.setattr(recovery_module, "plan_recovery_v1", capture_plan)
    monkeypatch.setattr(
        recovery_module,
        "_joint_recheck_transaction_pair",
        crash_after_joint_recheck,
    )
    for _attempt_index in range(2):
        with pytest.raises(_InjectedCrash), _opened_recovery(tmp_path) as opened:
            recovery_module._recover_journals_v1(opened.session)
        assert (tmp_path / "events.jsonl").read_bytes() == original_events
        assert (tmp_path / "raw.jsonl").read_bytes() == original_raw

    assert len(plans) == 2
    assert plans[0] == plans[1]


def test_partial_write_then_oserror_is_recovered_after_reopen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, _environment, _plan = _context()
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule),),
        event_tail=b'{"initial-tail":"partial-write-error"}',
    )
    real_write = journal_module.os.write

    with _opened_recovery(tmp_path) as opened:
        write_calls = 0

        def partial_then_error(descriptor: int, data: bytes) -> int:
            nonlocal write_calls
            if descriptor not in {
                opened.transaction._event_fd,
                opened.transaction._raw_fd,
            }:
                return real_write(descriptor, data)
            write_calls += 1
            if write_calls == 1:
                prefix = data[: max(1, len(data) // 2)]
                return real_write(descriptor, prefix)
            raise OSError("sensitive-write-error-canary")

        with monkeypatch.context() as scoped:
            scoped.setattr(journal_module.os, "write", partial_then_error)
            with pytest.raises(RecoveryError) as caught:
                recovery_module._recover_journals_v1(opened.session)
            assert caught.value.code == "io_error"
            assert "sensitive-write-error-canary" not in repr(caught.value)

    with _opened_recovery(
        tmp_path,
        operation_id=REPLAY_OPERATION,
        occurred_at=REPLAY_TIME,
    ) as replay:
        applied = recovery_module._recover_journals_v1(replay.session)
        assert applied.disposition == "provider_ready"
        assert applied.appended_event_count == 1
        assert applied.events.tail_byte_count == 0

    kinds = tuple(
        json.loads(row)["kind"] for row in (tmp_path / "events.jsonl").read_bytes().splitlines()
    )
    assert kinds == ("prepared", "tail_recovered")


_CRASH_REPLAY_CASES = (
    pytest.param(
        ("ftruncate", "events", 1),
        ("raw",),
        3,
        id="after-events-ftruncate-before-fsync",
    ),
    pytest.param(
        ("fsync", "events", 1),
        ("raw",),
        3,
        id="after-events-truncate-fsync",
    ),
    pytest.param(
        ("ftruncate", "raw", 1),
        (),
        2,
        id="after-raw-ftruncate-before-fsync",
    ),
    pytest.param(
        ("fsync", "raw", 1),
        (),
        2,
        id="after-raw-truncate-fsync",
    ),
    pytest.param(
        ("write", "events", 1),
        ("events",),
        2,
        id="after-events-tail-audit-write-before-fsync",
    ),
    pytest.param(
        ("fsync", "events", 2),
        ("events",),
        2,
        id="after-events-tail-audit-fsync",
    ),
    pytest.param(
        ("write", "events", 2),
        ("events", "raw"),
        2,
        id="after-raw-tail-audit-write-before-fsync",
    ),
    pytest.param(
        ("fsync", "events", 3),
        ("events", "raw"),
        2,
        id="after-raw-tail-audit-fsync",
    ),
    pytest.param(
        ("write", "events", 3),
        ("events", "raw"),
        1,
        id="after-recovered-finish-write-before-fsync",
    ),
    pytest.param(
        ("fsync", "events", 4),
        ("events", "raw"),
        1,
        id="after-recovered-finish-fsync",
    ),
    pytest.param(
        ("write", "events", 4),
        ("events", "raw"),
        0,
        id="after-recovered-completion-write-before-fsync",
    ),
    pytest.param(
        ("fsync", "events", 5),
        ("events", "raw"),
        0,
        id="after-recovered-completion-fsync",
    ),
)


@pytest.mark.parametrize(
    ("crash_action", "expected_tail_audits", "expected_replay_appends"),
    _CRASH_REPLAY_CASES,
)
def test_crash_after_each_recovery_mutation_replays_from_visible_prefix(
    crash_action: tuple[str, str, int],
    expected_tail_audits: tuple[str, ...],
    expected_replay_appends: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "success")
    event_tail = b'{"torn-event":"crash-matrix-canary"}'
    raw_tail = b'{"torn-raw":"crash-matrix-canary"}'
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
        event_tail=event_tail,
        raw_tail=raw_tail,
    )
    crash = _CrashAfterAction(crash_action)

    with (
        monkeypatch.context() as scoped,
        pytest.raises(_InjectedCrash),
        _opened_recovery(tmp_path, after_io_action=crash.after) as opened,
    ):
        real_ftruncate = journal_module.os.ftruncate
        real_full_write = journal_module._full_write

        def crash_after_ftruncate(descriptor: int, length: int) -> None:
            real_ftruncate(descriptor, length)
            if descriptor == opened.transaction._event_fd:
                crash.after("ftruncate", "events")
            elif descriptor == opened.transaction._raw_fd:
                crash.after("ftruncate", "raw")

        def crash_after_full_write(
            transaction: JournalTransaction,
            ledger: Ledger,
            framed: bytes,
        ) -> None:
            real_full_write(transaction, ledger, framed)
            crash.after("write", ledger)

        scoped.setattr(journal_module.os, "ftruncate", crash_after_ftruncate)
        scoped.setattr(journal_module, "_full_write", crash_after_full_write)
        recovery_module._recover_journals_v1(opened.session)

    assert crash.crashed is True
    assert crash.observed[-1] == crash_action
    assert event_tail not in (tmp_path / "events.jsonl").read_bytes()

    with _opened_recovery(
        tmp_path,
        operation_id=REPLAY_OPERATION,
        occurred_at=REPLAY_TIME,
    ) as replay:
        applied = recovery_module._recover_journals_v1(replay.session)
        assert applied.disposition == "complete"
        assert applied.appended_event_count == expected_replay_appends
        post = snapshot_journal_pair(
            replay.root_fd,
            history_context=replay.history_context,
            tail_policy="report",
        )
        assert post.events.tail_byte_count == 0
        assert post.raw.tail_byte_count == 0
        assert post.raw.row_count == 1
        assert post.history.recovery_requirements == ()
        assert post.lifecycle.state == "GENERATION_COMPLETE"

    recovered_bytes = (tmp_path / "events.jsonl").read_bytes()
    recovered_raw = (tmp_path / "raw.jsonl").read_bytes()
    rows = tuple(json.loads(row) for row in recovered_bytes.splitlines())
    kinds = tuple(row["kind"] for row in rows)
    tail_audits = tuple(row["payload"]["ledger"] for row in rows if row["kind"] == "tail_recovered")
    assert tail_audits == expected_tail_audits
    assert kinds.count("request_started") == 1
    assert kinds.count("request_finished") == 1
    assert kinds.count("generation_completed") == 1
    assert recovered_raw == raw_attempt_jsonl(attempt)

    with _opened_recovery(
        tmp_path,
        operation_id=IDEMPOTENCE_OPERATION,
        occurred_at=IDEMPOTENCE_TIME,
    ) as idempotent:
        reapplied = recovery_module._recover_journals_v1(idempotent.session)
        assert reapplied.disposition == "complete"
        assert reapplied.appended_event_count == 0

    assert (tmp_path / "events.jsonl").read_bytes() == recovered_bytes
    assert (tmp_path / "raw.jsonl").read_bytes() == recovered_raw


def test_exact_capacity_partial_recovery_row_uses_reserved_replay_headroom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "success")
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
    )
    root_fd = _root(tmp_path)
    try:
        pair = snapshot_journal_pair(
            root_fd,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="report",
        )
    finally:
        os.close(root_fd)
    context = RecoveryContextV1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        immutable_evidence_bytes=0,
        history=pair.history,
        lifecycle=pair.lifecycle,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
    )
    baseline = plan_recovery_v1(
        context=context,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
        operation_id=RECOVERY_OPERATION,
        occurred_at=RECOVERY_TIME,
    )
    immutable = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
        - baseline.post_mutable_bytes
        - baseline.seal_reservation_bytes
        - baseline.crash_reservation_bytes
    )
    real_full_write = journal_module._full_write

    def partial_first_event(
        transaction: JournalTransaction,
        ledger: Ledger,
        framed: bytes,
    ) -> None:
        assert ledger == "events"
        descriptor = transaction._event_fd
        prefix = framed[: max(1, len(framed) // 2)]
        written = os.write(descriptor, prefix)
        assert written == len(prefix)
        raise _InjectedCrash

    with (
        monkeypatch.context() as scoped,
        pytest.raises(_InjectedCrash),
        _opened_recovery(tmp_path, immutable_evidence_bytes=immutable) as opened,
    ):
        scoped.setattr(journal_module, "_full_write", partial_first_event)
        recovery_module._recover_journals_v1(opened.session)

    assert journal_module._full_write is real_full_write
    with _opened_recovery(
        tmp_path,
        immutable_evidence_bytes=immutable,
        operation_id=REPLAY_OPERATION,
        occurred_at=REPLAY_TIME,
    ) as replay:
        applied = recovery_module._recover_journals_v1(replay.session)
        assert applied.disposition == "complete"
        assert applied.appended_event_count == 3
        assert (
            immutable + applied.events.byte_length + applied.raw.byte_length
            <= RESOURCE_LIMITS_V1.mutable_capsule_bytes
        )

    rows = tuple(json.loads(row) for row in (tmp_path / "events.jsonl").read_bytes().splitlines())
    assert tuple(row["kind"] for row in rows).count("tail_recovered") == 1
    assert tuple(row["kind"] for row in rows).count("request_finished") == 1
    assert tuple(row["kind"] for row in rows).count("generation_completed") == 1


def test_exact_capacity_initial_tail_survives_later_partial_recovery_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "success")
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
        event_tail=b'{"initial-torn-event":"capacity-canary"}',
    )
    root_fd = _root(tmp_path)
    try:
        pair = snapshot_journal_pair(
            root_fd,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="report",
        )
    finally:
        os.close(root_fd)
    context = RecoveryContextV1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        immutable_evidence_bytes=0,
        history=pair.history,
        lifecycle=pair.lifecycle,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
    )
    baseline = plan_recovery_v1(
        context=context,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
        operation_id=RECOVERY_OPERATION,
        occurred_at=RECOVERY_TIME,
    )
    immutable = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
        - baseline.post_mutable_bytes
        - baseline.seal_reservation_bytes
        - baseline.crash_reservation_bytes
    )
    real_full_write = journal_module._full_write
    event_write_count = 0

    def commit_audit_then_partially_write_finish(
        transaction: JournalTransaction,
        ledger: Ledger,
        framed: bytes,
    ) -> None:
        nonlocal event_write_count
        assert ledger == "events"
        event_write_count += 1
        if event_write_count == 1:
            real_full_write(transaction, ledger, framed)
            return
        prefix = framed[: max(1, len(framed) // 2)]
        assert os.write(transaction._event_fd, prefix) == len(prefix)
        raise _InjectedCrash

    with (
        monkeypatch.context() as scoped,
        pytest.raises(_InjectedCrash),
        _opened_recovery(tmp_path, immutable_evidence_bytes=immutable) as opened,
    ):
        scoped.setattr(
            journal_module,
            "_full_write",
            commit_audit_then_partially_write_finish,
        )
        recovery_module._recover_journals_v1(opened.session)

    with _opened_recovery(
        tmp_path,
        immutable_evidence_bytes=immutable,
        operation_id=REPLAY_OPERATION,
        occurred_at=REPLAY_TIME,
    ) as replay:
        applied = recovery_module._recover_journals_v1(replay.session)
        assert applied.disposition == "complete"
        assert applied.appended_event_count == 3
        assert (
            immutable + applied.events.byte_length + applied.raw.byte_length
            <= RESOURCE_LIMITS_V1.mutable_capsule_bytes
        )

    kinds = tuple(
        json.loads(row)["kind"] for row in (tmp_path / "events.jsonl").read_bytes().splitlines()
    )
    assert kinds.count("tail_recovered") == 2
    assert kinds.count("request_finished") == 1
    assert kinds.count("generation_completed") == 1


def test_exact_capacity_initial_tail_survives_partial_first_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "success")
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
        event_tail=b"x",
    )
    root_fd = _root(tmp_path)
    try:
        pair = snapshot_journal_pair(
            root_fd,
            history_context=HistoryContextV1(capsule, manifest, environment, plan),
            tail_policy="report",
        )
    finally:
        os.close(root_fd)
    context = RecoveryContextV1(
        capsule=capsule,
        manifest=manifest,
        environment=environment,
        plan=plan,
        immutable_evidence_bytes=0,
        history=pair.history,
        lifecycle=pair.lifecycle,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
    )
    baseline = plan_recovery_v1(
        context=context,
        event_snapshot=pair.events,
        raw_snapshot=pair.raw,
        operation_id=RECOVERY_OPERATION,
        occurred_at=RECOVERY_TIME,
    )
    immutable = (
        RESOURCE_LIMITS_V1.mutable_capsule_bytes
        - baseline.post_mutable_bytes
        - baseline.seal_reservation_bytes
        - baseline.crash_reservation_bytes
    )

    def partial_first_audit(
        transaction: JournalTransaction,
        ledger: Ledger,
        framed: bytes,
    ) -> None:
        assert ledger == "events"
        prefix = framed[: max(1, len(framed) // 2)]
        assert os.write(transaction._event_fd, prefix) == len(prefix)
        raise _InjectedCrash

    with (
        monkeypatch.context() as scoped,
        pytest.raises(_InjectedCrash),
        _opened_recovery(tmp_path, immutable_evidence_bytes=immutable) as opened,
    ):
        scoped.setattr(journal_module, "_full_write", partial_first_audit)
        recovery_module._recover_journals_v1(opened.session)

    with _opened_recovery(
        tmp_path,
        immutable_evidence_bytes=immutable,
        operation_id=REPLAY_OPERATION,
        occurred_at=REPLAY_TIME,
    ) as replay:
        applied = recovery_module._recover_journals_v1(replay.session)
        assert applied.disposition == "complete"
        assert applied.appended_event_count == 3
        assert (
            immutable + applied.events.byte_length + applied.raw.byte_length
            <= RESOURCE_LIMITS_V1.mutable_capsule_bytes
        )

    kinds = tuple(
        json.loads(row)["kind"] for row in (tmp_path / "events.jsonl").read_bytes().splitlines()
    )
    assert kinds.count("tail_recovered") == 1
    assert kinds.count("request_finished") == 1
    assert kinds.count("generation_completed") == 1


def test_close_failure_after_durable_recovery_is_idempotent_on_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule, _manifest, environment, plan = _context()
    start = _start(plan[0])
    attempt = _attempt(plan[0], "success")
    _write_capsule(
        tmp_path,
        event_rows=(_prepared(capsule), _execution_started(environment), start),
        raw_rows=(attempt,),
        event_tail=b'{"torn-event":"close-failure"}',
        raw_tail=b'{"torn-raw":"close-failure"}',
    )
    close_failed = False
    applied = None

    with (
        monkeypatch.context() as scoped,
        pytest.raises(JournalError) as caught,
        _opened_recovery(tmp_path) as opened,
    ):
        event_descriptor = opened.transaction._event_fd
        real_close = journal_module.os.close

        def close_with_one_failure(descriptor: int) -> None:
            nonlocal close_failed
            real_close(descriptor)
            if descriptor == event_descriptor and not close_failed:
                close_failed = True
                raise OSError

        scoped.setattr(journal_module.os, "close", close_with_one_failure)
        applied = recovery_module._recover_journals_v1(opened.session)
        assert applied.disposition == "complete"

    assert caught.value.code == "io_error"

    assert close_failed is True
    assert applied is not None
    recovered_events = (tmp_path / "events.jsonl").read_bytes()
    recovered_raw = (tmp_path / "raw.jsonl").read_bytes()

    with _opened_recovery(
        tmp_path,
        operation_id=REPLAY_OPERATION,
        occurred_at=REPLAY_TIME,
    ) as replay:
        reapplied = recovery_module._recover_journals_v1(replay.session)
        assert reapplied.disposition == "complete"
        assert reapplied.appended_event_count == 0

    assert (tmp_path / "events.jsonl").read_bytes() == recovered_events
    assert (tmp_path / "raw.jsonl").read_bytes() == recovered_raw
