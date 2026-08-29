from __future__ import annotations

import fcntl
import os
import stat
from uuid import UUID

import pytest

from laconian_eval.capsule.verification_scratch import (
    ExactIdentityRegistry,
    IdentityCollision,
    ScratchError,
)

RUN_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
OPERATION_ID = UUID("223e4567-e89b-42d3-a456-426614174001")
SESSION_ID = UUID("323e4567-e89b-42d3-a456-426614174002")


@pytest.mark.parametrize(
    ("first_kind", "second_kind"),
    [
        ("run", "operation"),
        ("run", "session"),
        ("operation", "operation"),
        ("operation", "session"),
        ("session", "operation"),
        ("session", "session"),
    ],
)
def test_core_identity_declarations_are_exactly_pairwise_distinct(
    first_kind: str,
    second_kind: str,
) -> None:
    with ExactIdentityRegistry(initial_capacity=4) as registry:
        registry.declare_core(RUN_ID, first_kind, 1)
        with pytest.raises(IdentityCollision) as caught:
            registry.declare_core(RUN_ID, second_kind, 7)

    assert caught.value.row_index == 7
    assert str(caught.value) == "verification identity collision"


def test_seal_identity_has_the_narrow_approved_collision_matrix() -> None:
    old_operation = UUID("423e4567-e89b-42d3-a456-426614174003")
    seal_operation = UUID("523e4567-e89b-42d3-a456-426614174004")
    seal_transaction = UUID("623e4567-e89b-42d3-a456-426614174005")
    with ExactIdentityRegistry(initial_capacity=8) as registry:
        registry.declare_core(RUN_ID, "run", 0)
        registry.declare_core(old_operation, "operation", 1)
        registry.declare_core(SESSION_ID, "session", 2)
        registry.declare_core(seal_operation, "operation", 3)
        registry.declare_seal(old_operation, seal_operation, 4)
        registry.declare_seal(seal_transaction, seal_operation, 5)
        for forbidden in (RUN_ID, SESSION_ID, seal_operation):
            with pytest.raises(IdentityCollision) as caught:
                registry.declare_seal(forbidden, seal_operation, 6)
            assert caught.value.row_index == 6


def test_registry_resizes_on_disk_and_still_detects_an_early_identity() -> None:
    identities = tuple(UUID(int=(1 << 76) | (4 << 76) | index) for index in range(1, 80))
    with ExactIdentityRegistry(initial_capacity=4) as registry:
        for row_index, value in enumerate(identities):
            registry.declare_core(value, "operation", row_index)
        with pytest.raises(IdentityCollision) as caught:
            registry.declare_core(identities[3], "session", len(identities))
    assert caught.value.row_index == len(identities)


def test_scratch_is_unlinked_private_regular_and_cloexec_before_first_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_pwrite = os.pwrite
    observed: list[os.stat_result] = []

    def checked_pwrite(descriptor: int, data: bytes, offset: int) -> int:
        metadata = os.fstat(descriptor)
        observed.append(metadata)
        assert stat.S_ISREG(metadata.st_mode)
        assert metadata.st_nlink == 0
        assert metadata.st_uid == os.geteuid()
        assert stat.S_IMODE(metadata.st_mode) & ~0o600 == 0
        assert fcntl.fcntl(descriptor, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
        return real_pwrite(descriptor, data, offset)

    monkeypatch.setattr(os, "pwrite", checked_pwrite)
    with ExactIdentityRegistry(initial_capacity=4) as registry:
        registry.declare_core(RUN_ID, "run", 0)
    assert observed


def test_forbidden_capsule_namespace_identity_selects_a_different_fixed_root() -> None:
    first = os.stat("/var/tmp")
    second_root = "/private/tmp" if os.path.isdir("/private/tmp") else "/tmp"
    second = os.stat(second_root)
    if (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino):
        pytest.skip("host exposes only one fixed scratch namespace identity")
    forbidden = frozenset({(first.st_dev, first.st_ino)})
    with ExactIdentityRegistry(
        initial_capacity=4,
        forbidden_namespace_identities=forbidden,
    ) as registry:
        directory = os.fstat(registry._storage._directory_fd)
        assert (directory.st_dev, directory.st_ino) not in forbidden


def test_forbidden_namespace_ambiguous_close_is_attempted_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import verification_scratch as scratch_module

    root = "/var/tmp"
    metadata = os.stat(root)
    forbidden = frozenset({(metadata.st_dev, metadata.st_ino)})
    real_close = os.close
    close_calls: list[int] = []

    def ambiguous_close(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise OSError("credential=CANARY /private/scratch")

    with monkeypatch.context() as scoped:
        scoped.setattr(scratch_module, "_SCRATCH_ROOTS", (root,))
        scoped.setattr(scratch_module.os, "close", ambiguous_close)
        with pytest.raises(ScratchError) as caught:
            scratch_module._ScratchStorage._open_directory(forbidden)

    assert str(caught.value) == "verification scratch failed"
    assert len(close_calls) == 1


def test_directory_validation_failure_closes_the_owned_descriptor_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import verification_scratch as scratch_module

    root = "/var/tmp"
    real_open = os.open
    real_close = os.close
    opened: list[int] = []
    closed: list[int] = []

    def tracked_open(*args: object, **kwargs: object) -> int:
        descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
        opened.append(descriptor)
        return descriptor

    def tracked_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    def failed_flags(_descriptor: int) -> int:
        raise OSError("credential=CANARY /private/scratch-flags")

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(scratch_module, "_SCRATCH_ROOTS", (root,))
            scoped.setattr(scratch_module.os, "open", tracked_open)
            scoped.setattr(scratch_module.os, "close", tracked_close)
            scoped.setattr(scratch_module, "_fd_flags", failed_flags)
            with pytest.raises(ScratchError) as caught:
                scratch_module._ScratchStorage._open_directory(frozenset())
    finally:
        for descriptor in opened:
            if descriptor not in closed:
                real_close(descriptor)

    assert str(caught.value) == "verification scratch failed"
    assert closed == opened


def test_known_collision_precedes_a_resize_io_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from laconian_eval.capsule import verification_scratch as scratch_module

    registry = ExactIdentityRegistry(initial_capacity=4)
    registry.declare_core(RUN_ID, "run", 0)
    registry.declare_core(OPERATION_ID, "operation", 1)

    def failed_resize(_descriptor: int, _size: int) -> None:
        raise OSError("credential=CANARY /private/resize")

    with monkeypatch.context() as scoped:
        scoped.setattr(scratch_module.os, "ftruncate", failed_resize)
        with pytest.raises(IdentityCollision) as caught:
            registry.declare_core(RUN_ID, "session", 2)
    registry.close()
    assert caught.value.row_index == 2


@pytest.mark.parametrize("corruption", ["mac", "count"])
def test_successful_close_rejects_exact_record_or_count_corruption(corruption: str) -> None:
    from laconian_eval.capsule import verification_scratch as scratch_module

    registry = ExactIdentityRegistry(initial_capacity=4)
    registry.declare_core(RUN_ID, "run", 0)
    slot, _tag, _row = registry._lookup_table(RUN_ID, registry._base, registry._capacity)
    offset = registry._base + slot * scratch_module._RECORD_BYTES
    if corruption == "mac":
        original = os.pread(registry._storage.descriptor, scratch_module._RECORD_BYTES, offset)
        forged = original[:-1] + bytes((original[-1] ^ 1,))
    else:
        forged = b"\0" * scratch_module._RECORD_BYTES
    os.pwrite(registry._storage.descriptor, forged, offset)
    with pytest.raises(ScratchError) as caught:
        registry.close()
    assert str(caught.value) == "verification scratch failed"


def test_unlink_failure_writes_no_identity_and_best_effort_removes_the_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import verification_scratch as scratch_module

    real_unlink = os.unlink
    unlink_calls: list[bytes] = []
    first = True

    def flaky_unlink(name: bytes, *, dir_fd: int) -> None:
        nonlocal first
        unlink_calls.append(name)
        if first:
            first = False
            raise OSError("credential=CANARY /private/unlink")
        real_unlink(name, dir_fd=dir_fd)

    def forbidden_resize(_descriptor: int, _size: int) -> None:
        raise AssertionError("scratch records must not be allocated before unlink succeeds")

    with monkeypatch.context() as scoped:
        scoped.setattr(scratch_module.os, "unlink", flaky_unlink)
        scoped.setattr(scratch_module.os, "ftruncate", forbidden_resize)
        with pytest.raises(ScratchError) as caught:
            ExactIdentityRegistry(initial_capacity=4)
    assert str(caught.value) == "verification scratch failed"
    assert len(unlink_calls) >= 2


def test_close_failure_is_content_free_and_does_not_mask_a_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import verification_scratch as scratch_module

    real_close = os.close
    close_calls: list[int] = []

    registry = ExactIdentityRegistry(initial_capacity=4)
    owned = (registry._storage.descriptor, registry._storage._directory_fd)

    def ambiguous_close(descriptor: int) -> None:
        close_calls.append(descriptor)
        real_close(descriptor)
        raise OSError("credential=CANARY /private/scratch")

    with monkeypatch.context() as scoped:
        scoped.setattr(scratch_module.os, "close", ambiguous_close)
        with pytest.raises(ScratchError) as caught:
            registry.close()
    assert str(caught.value) == "verification scratch failed"
    assert close_calls == list(owned)

    primary = RuntimeError("earlier capsule failure")
    registry = ExactIdentityRegistry(initial_capacity=4)
    owned = (registry._storage.descriptor, registry._storage._directory_fd)
    close_calls.clear()
    with monkeypatch.context() as scoped:
        scoped.setattr(scratch_module.os, "close", ambiguous_close)
        with pytest.raises(RuntimeError) as preserved, registry:
            raise primary
    assert preserved.value is primary
    assert close_calls == list(owned)
