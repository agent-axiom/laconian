from __future__ import annotations

import multiprocessing
import os
import sys
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Literal

import pytest

from laconian_eval.capsule.filesystem import (
    PERSISTENT_LOCK_NAME,
    LockHandle,
    try_acquire_mutator_lock,
    try_acquire_shared_lock,
)
from laconian_eval.capsule.posix import PosixOps

_PROCESS_TIMEOUT_SECONDS = 15.0
_LockKind = Literal["exclusive", "shared"]

pytestmark = pytest.mark.skipif(
    sys.platform not in {"linux", "darwin"},
    reason="POSIX advisory locks required",
)


@dataclass(slots=True)
class _HeldProcess:
    process: Any
    receiver: Connection
    release: Any


def _open_directory(path: str) -> int:
    return os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )


def _try_lock(directory_fd: int, kind: _LockKind) -> LockHandle | None:
    posix = PosixOps()
    if kind == "exclusive":
        return try_acquire_mutator_lock(directory_fd, posix=posix)
    return try_acquire_shared_lock(directory_fd, posix=posix)


def _holder_process(
    directory: str,
    kind: _LockKind,
    sender: Connection,
    ready: Any,
    release: Any,
    exit_without_cleanup: bool,
) -> None:
    directory_fd: int | None = None
    handle: LockHandle | None = None
    try:
        directory_fd = _open_directory(directory)
        handle = _try_lock(directory_fd, kind)
        if handle is None:
            sender.send(("busy", os.getpid()))
            return
        sender.send(("acquired", os.getpid()))
        ready.set()
        release.wait()
        if exit_without_cleanup:
            os._exit(0)
        handle.close()
        handle = None
    except Exception as error:
        sender.send(
            (
                "error",
                type(error).__name__,
                getattr(error, "code", None),
                getattr(error, "errno", None),
            )
        )
    finally:
        if handle is not None:
            handle.close()
        if directory_fd is not None:
            os.close(directory_fd)
        sender.close()


def _attempt_once(directory: Path, kind: _LockKind) -> tuple[str, int]:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    ready = context.Event()
    release = context.Event()
    release.set()
    process = context.Process(
        target=_holder_process,
        args=(os.fspath(directory), kind, sender, ready, release, False),
    )
    process.start()
    sender.close()
    try:
        assert receiver.poll(_PROCESS_TIMEOUT_SECONDS), "lock contender produced no result"
        result = receiver.recv()
        process.join(_PROCESS_TIMEOUT_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(_PROCESS_TIMEOUT_SECONDS)
        assert process.exitcode == 0
        assert type(result) is tuple and len(result) == 2, result
        assert result[0] in {"acquired", "busy"}, result
        assert type(result[1]) is int and result[1] > 0, result
        return result
    finally:
        if process.is_alive():
            process.kill()
            process.join(_PROCESS_TIMEOUT_SECONDS)
        receiver.close()


def _start_holder(
    directory: Path,
    kind: _LockKind,
    *,
    exit_without_cleanup: bool = False,
) -> _HeldProcess:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_holder_process,
        args=(
            os.fspath(directory),
            kind,
            sender,
            ready,
            release,
            exit_without_cleanup,
        ),
    )
    process.start()
    sender.close()
    try:
        assert receiver.poll(_PROCESS_TIMEOUT_SECONDS), "lock holder produced no result"
        result = receiver.recv()
        assert result == ("acquired", process.pid), result
        assert ready.wait(_PROCESS_TIMEOUT_SECONDS), "lock holder did not publish readiness"
        assert process.is_alive()
    except BaseException:
        release.set()
        process.join(_PROCESS_TIMEOUT_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(_PROCESS_TIMEOUT_SECONDS)
        receiver.close()
        raise
    return _HeldProcess(process=process, receiver=receiver, release=release)


def _release_holder(holder: _HeldProcess) -> None:
    holder.release.set()
    holder.process.join(_PROCESS_TIMEOUT_SECONDS)
    if holder.process.is_alive():
        holder.process.kill()
        holder.process.join(_PROCESS_TIMEOUT_SECONDS)
    holder.receiver.close()
    assert holder.process.exitcode == 0


def _create_lock_leaf(directory: Path) -> None:
    lock_path = directory / PERSISTENT_LOCK_NAME
    lock_path.write_bytes(b"")
    os.chmod(lock_path, 0o600)


def test_second_exclusive_acquisition_is_busy_until_retained_owner_releases(
    tmp_path: Path,
) -> None:
    _create_lock_leaf(tmp_path)
    holder = _start_holder(tmp_path, "exclusive")
    try:
        assert _attempt_once(tmp_path, "exclusive")[0] == "busy"
        assert _attempt_once(tmp_path, "exclusive")[0] == "busy"
    finally:
        _release_holder(holder)

    assert _attempt_once(tmp_path, "exclusive")[0] == "acquired"


def test_exclusive_owner_blocks_shared_until_release(tmp_path: Path) -> None:
    _create_lock_leaf(tmp_path)
    holder = _start_holder(tmp_path, "exclusive")
    try:
        assert _attempt_once(tmp_path, "shared")[0] == "busy"
    finally:
        _release_holder(holder)

    assert _attempt_once(tmp_path, "shared")[0] == "acquired"


def test_concurrent_shared_owners_each_retain_exclusion_of_exclusive_owner(
    tmp_path: Path,
) -> None:
    _create_lock_leaf(tmp_path)
    first: _HeldProcess | None = _start_holder(tmp_path, "shared")
    second: _HeldProcess | None = None
    try:
        second = _start_holder(tmp_path, "shared")
        assert _attempt_once(tmp_path, "exclusive")[0] == "busy"

        _release_holder(first)
        first = None
        assert _attempt_once(tmp_path, "exclusive")[0] == "busy"
    finally:
        if first is not None:
            _release_holder(first)
        if second is not None:
            _release_holder(second)

    assert _attempt_once(tmp_path, "exclusive")[0] == "acquired"


def test_child_os_exit_releases_retained_exclusive_lock(tmp_path: Path) -> None:
    _create_lock_leaf(tmp_path)
    holder = _start_holder(tmp_path, "exclusive", exit_without_cleanup=True)

    _release_holder(holder)

    assert _attempt_once(tmp_path, "exclusive")[0] == "acquired"


def test_terminating_child_releases_retained_exclusive_lock(tmp_path: Path) -> None:
    _create_lock_leaf(tmp_path)
    holder = _start_holder(tmp_path, "exclusive")
    holder.process.terminate()
    holder.process.join(_PROCESS_TIMEOUT_SECONDS)
    if holder.process.is_alive():
        holder.process.kill()
        holder.process.join(_PROCESS_TIMEOUT_SECONDS)
    holder.receiver.close()

    assert holder.process.exitcode is not None
    assert holder.process.exitcode != 0
    assert _attempt_once(tmp_path, "exclusive")[0] == "acquired"
