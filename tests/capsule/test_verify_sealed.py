"""Read-only verification tests for sealed generation-capsule transports."""

from __future__ import annotations

import errno
import json
import os
import shutil
import stat
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.verify as verify_module
from laconian_eval.capsule.bounded_io import (
    _descriptor_bound_path,
    _is_descriptor_bound_path,
    open_directory_no_follow,
)
from laconian_eval.capsule.canonical import canonical_json, canonical_jsonl, sha256_bytes
from laconian_eval.capsule.execution import ProviderFactory
from laconian_eval.capsule.filesystem import UnsupportedFilesystemError
from laconian_eval.capsule.finalize import finalize_capsule
from laconian_eval.capsule.seal_models import SealV1, seal_bytes
from laconian_eval.capsule.verify import (
    VerificationMode,
    VerifiedSealedCapsuleSourceV1,
    verified_sealed_capsule_source,
    verify_capsule,
)
from laconian_eval.providers import GenerationResult

from .test_execution import (
    _install_fast_runtime,
    _ScriptedProvider,
    _seams_for_provider,
    _single_plan_capsule,
)


@pytest.fixture
def sealed_capsules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    complete_root = tmp_path / "complete"
    complete_root.mkdir()
    complete = _single_plan_capsule(complete_root, monkeypatch)
    _install_fast_runtime(monkeypatch)
    result = GenerationResult(output_text="complete", response_model="returned-v1")
    outcome = execution_module._resume_capsule(
        complete,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(_ScriptedProvider([result, result])),
    )
    assert outcome.exit_code == 0
    assert finalize_capsule(complete).state == "SEALED_COMPLETE"

    blocked_root = tmp_path / "blocked"
    blocked_root.mkdir()
    blocked = _single_plan_capsule(blocked_root, monkeypatch)
    assert finalize_capsule(blocked, seal_incomplete=True).state == "SEALED_BLOCKED"
    return complete, blocked


def test_seal_presence_selects_sealed_verification(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete_path, blocked_path = sealed_capsules

    complete = verify_capsule(complete_path, mode=VerificationMode.PREPARED)
    blocked = verify_capsule(blocked_path, mode=VerificationMode.PREPARED)

    assert complete.status == "valid"
    assert complete.state == "SEALED_COMPLETE"
    assert complete.capsule_sha256 == sha256_bytes((complete_path / "seal.json").read_bytes())
    assert blocked.status == "valid"
    assert blocked.state == "SEALED_BLOCKED"
    assert blocked.capsule_sha256 == sha256_bytes((blocked_path / "seal.json").read_bytes())


def test_verified_sealed_capsule_source_exposes_exact_frozen_evidence(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    before = _tree_snapshot(complete.parent)

    with verified_sealed_capsule_source(complete) as source:
        assert type(source) is VerifiedSealedCapsuleSourceV1
        assert source.result.status == "valid"
        assert source.result.state == "SEALED_COMPLETE"
        assert source.result.capsule_sha256 == sha256_bytes((complete / "seal.json").read_bytes())
        assert source.capsule.run_id == source.result.run_id
        assert source.manifest_bytes == (complete / "manifest.json").read_bytes()
        assert source.case_index_bytes == (complete / "case-index.jsonl").read_bytes()
        assert source.plan_bytes == (complete / "plan.jsonl").read_bytes()
        assert source.raw_bytes == (complete / "raw.jsonl").read_bytes()
        root_metadata = complete.stat()
        assert source._retained_root_leaf == (  # type: ignore[attr-defined]
            root_metadata.st_dev,
            root_metadata.st_ino,
            stat.S_IFMT(root_metadata.st_mode),
        )
        assert tuple(row.plan_item_id for row in source.plan) == tuple(
            row.plan_item_id for row in source.raw_attempts if row.terminal
        )
        expected_case_uids = tuple(dict.fromkeys(row.case_uid for row in source.plan))
        assert tuple(source.cases_by_uid) == expected_case_uids
        assert all(source.cases_by_uid[row.case_uid].id == row.case_id for row in source.plan)
        with pytest.raises(TypeError):
            source.cases_by_uid[expected_case_uids[0]] = source.cases_by_uid[  # type: ignore[index]
                expected_case_uids[0]
            ]
        with pytest.raises(FrozenInstanceError):
            source.raw_bytes = b"forged"  # type: ignore[misc]

    assert _tree_snapshot(complete.parent) == before


def test_verified_sealed_capsule_source_rejects_caller_construction(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    with verified_sealed_capsule_source(complete) as source:
        forged_payload = {item.name: getattr(source, item.name) for item in fields(source)}

    with pytest.raises(verify_module._Failure) as caught:  # type: ignore[attr-defined]
        VerifiedSealedCapsuleSourceV1(**forged_payload)

    assert caught.value.code == "invalid_model"
    assert caught.value.path is None


def test_verified_sealed_capsule_source_revalidates_plan_case_joins(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    with verified_sealed_capsule_source(complete) as source:
        forged_plan = (
            source.plan[0].model_copy(update={"scenario_uid": "f" * 64}),
            *source.plan[1:],
        )
        forged_plan_bytes = canonical_jsonl(
            row.model_dump(mode="json", round_trip=True) for row in forged_plan
        )
        forged_plan_sha256 = sha256_bytes(forged_plan_bytes)
        forged_capsule = source.capsule.model_copy(update={"plan_sha256": forged_plan_sha256})
        forged_files = tuple(
            item.model_copy(
                update={
                    "byte_length": len(forged_plan_bytes),
                    "sha256": forged_plan_sha256,
                }
            )
            if item.path == "plan.jsonl"
            else item
            for item in source.seal.files
        )
        forged_seal = source.seal.model_copy(update={"files": forged_files})
        forged_result = source.result.model_copy(
            update={"capsule_sha256": sha256_bytes(seal_bytes(forged_seal))}
        )
        forged_payload = {item.name: getattr(source, item.name) for item in fields(source)}
        forged_payload.update(
            {
                "result": forged_result,
                "seal": forged_seal,
                "capsule": forged_capsule,
                "plan_bytes": forged_plan_bytes,
                "plan": forged_plan,
            }
        )

    with pytest.raises(verify_module._Failure) as caught:  # type: ignore[attr-defined]
        VerifiedSealedCapsuleSourceV1(
            **forged_payload,
            _construction_authority=verify_module._SEALED_SOURCE_CONSTRUCTION_AUTHORITY,  # type: ignore[attr-defined]
        )

    assert caught.value.code == "invalid_model"


def test_verified_sealed_capsule_source_rejects_blocked_capsules(
    sealed_capsules: tuple[Path, Path],
) -> None:
    _complete, blocked = sealed_capsules

    with (
        pytest.raises(verify_module._Failure) as caught,  # type: ignore[attr-defined]
        verified_sealed_capsule_source(blocked),
    ):
        pytest.fail("blocked capsule must not expose scored-source evidence")

    assert caught.value.code == "seal_mismatch"
    assert caught.value.path == "seal.json"


def test_verified_sealed_capsule_source_supports_lockless_transport_without_posix(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    transported = tmp_path / "source-lockless"
    shutil.copytree(complete, transported)
    (transported / ".laconian.lock").unlink()

    def posix_bomb() -> object:
        raise AssertionError("lockless sealed source must not construct POSIX lock ops")

    monkeypatch.setattr(verify_module, "PosixOps", posix_bomb)
    with verified_sealed_capsule_source(transported) as source:
        assert source.result.state == "SEALED_COMPLETE"
        assert source.result.warnings[-1] == "lock_file_omitted_for_sealed_transport"


def test_verified_sealed_capsule_source_rechecks_exposed_bytes_on_exit(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules

    with (
        pytest.raises(verify_module._Failure) as caught,  # type: ignore[attr-defined]
        verified_sealed_capsule_source(complete) as source,
    ):
        assert source.manifest_bytes == (complete / "manifest.json").read_bytes()
        (complete / "manifest.json").write_bytes(b"{}")

    assert caught.value.code == "unstable_snapshot"
    assert caught.value.path == "manifest.json"


def test_verified_sealed_capsule_source_retains_and_rechecks_shared_lock(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    lock_path = complete / ".laconian.lock"

    with (
        pytest.raises(verify_module._Failure) as caught,  # type: ignore[attr-defined]
        verified_sealed_capsule_source(complete),
    ):
        lock_path.unlink()
        lock_path.write_bytes(b"")

    assert caught.value.code == "unstable_snapshot"
    assert caught.value.path == ".laconian.lock"


@pytest.mark.parametrize("mutation", ["delete", "type-swap"])
def test_verified_sealed_capsule_source_normalizes_proven_source_read_races(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    complete, _blocked = sealed_capsules
    manifest_path = complete / "manifest.json"
    real_snapshot = verify_module._verify_sealed_snapshot
    real_read_file = verify_module._read_file
    snapshot_complete = False
    mutated = False

    def tracked_snapshot(*args: Any, **kwargs: Any) -> object:
        nonlocal snapshot_complete
        snapshot = real_snapshot(*args, **kwargs)
        snapshot_complete = True
        return snapshot

    def mutate_before_source_read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal mutated
        if snapshot_complete and args[1] == "manifest.json" and not mutated:
            manifest_path.unlink()
            if mutation == "type-swap":
                manifest_path.mkdir()
            mutated = True
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_verify_sealed_snapshot", tracked_snapshot)
    monkeypatch.setattr(verify_module, "_read_file", mutate_before_source_read)
    with (
        pytest.raises(verify_module._Failure) as caught,  # type: ignore[attr-defined]
        verified_sealed_capsule_source(complete),
    ):
        pytest.fail("raced evidence must not be exposed")

    assert mutated
    assert caught.value.code == "unstable_snapshot"
    assert caught.value.path == "manifest.json"


def test_verified_sealed_capsule_source_preserves_stable_source_read_eio(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    real_snapshot = verify_module._verify_sealed_snapshot
    real_read_file = verify_module._read_file
    snapshot_complete = False
    injected = False

    def tracked_snapshot(*args: Any, **kwargs: Any) -> object:
        nonlocal snapshot_complete
        snapshot = real_snapshot(*args, **kwargs)
        snapshot_complete = True
        return snapshot

    def fail_source_read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal injected
        if snapshot_complete and args[1] == "manifest.json" and not injected:
            injected = True
            raise verify_module._Failure("io_error", "manifest.json")  # type: ignore[attr-defined]
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_verify_sealed_snapshot", tracked_snapshot)
    monkeypatch.setattr(verify_module, "_read_file", fail_source_read)
    with (
        pytest.raises(verify_module._Failure) as caught,  # type: ignore[attr-defined]
        verified_sealed_capsule_source(complete),
    ):
        pytest.fail("stable EIO must not expose evidence")

    assert injected
    assert caught.value.code == "io_error"
    assert caught.value.path == "manifest.json"


def test_verified_sealed_capsule_source_never_reopens_capsule_public_path(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    real_open_directory = verify_module.open_directory_no_follow
    opened: list[object] = []

    def track_directory_open(path: Path) -> int:
        opened.append(path)
        return real_open_directory(path)

    monkeypatch.setattr(verify_module, "open_directory_no_follow", track_directory_open)
    with verified_sealed_capsule_source(complete) as source:
        assert source.result.state == "SEALED_COMPLETE"

    assert opened.count(complete) == 1
    assert opened and all(path in {complete, complete.parent} for path in opened)

    parent_fd = open_directory_no_follow(complete.parent)
    try:
        capability = _descriptor_bound_path(parent_fd) / complete.name
        capability_start = len(opened)
        with verified_sealed_capsule_source(capability) as source:  # type: ignore[arg-type]
            assert source.result.state == "SEALED_COMPLETE"
        capability_opens = opened[capability_start:]
        assert len(capability_opens) >= 4
        assert all(_is_descriptor_bound_path(path) for path in capability_opens)
    finally:
        os.close(parent_fd)


def test_verified_sealed_capsule_source_rechecks_visible_root_on_exit(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    moved = complete.with_name(f"{complete.name}-moved")

    with (
        pytest.raises(verify_module._Failure) as caught,  # type: ignore[attr-defined]
        verified_sealed_capsule_source(complete),
    ):
        complete.rename(moved)
        shutil.copytree(moved, complete)

    assert caught.value.code == "unstable_snapshot"
    assert caught.value.path is None


def test_verified_sealed_capsule_source_preserves_body_failure_over_exit_race(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules

    class BodyFailure(Exception):
        pass

    with pytest.raises(BodyFailure), verified_sealed_capsule_source(complete):
        (complete / "manifest.json").write_bytes(b"{}")
        raise BodyFailure


def test_lockless_sealed_transport_bypasses_local_filesystem_requirement(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    expected = verify_capsule(complete, mode=VerificationMode.PREPARED)
    transport = tmp_path / "transport"
    shutil.copytree(complete, transport)
    (transport / ".laconian.lock").unlink()
    classifier_calls = 0

    def unsupported(*_args: object, **_kwargs: object) -> object:
        nonlocal classifier_calls
        classifier_calls += 1
        raise UnsupportedFilesystemError("unclassified_filesystem")

    monkeypatch.setattr(verify_module, "classify_filesystem", unsupported)
    actual = verify_capsule(transport, mode=VerificationMode.PREPARED)

    assert classifier_calls == 0
    assert actual.status == "valid"
    assert actual.state == expected.state == "SEALED_COMPLETE"
    assert actual.capsule_sha256 == expected.capsule_sha256
    assert actual.warnings == (
        *expected.warnings,
        "lock_file_omitted_for_sealed_transport",
    )


def test_invalid_seal_never_falls_back_to_unsealed_verification(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    corrupt = tmp_path / "corrupt"
    shutil.copytree(complete, corrupt)
    (corrupt / "seal.json").write_bytes(b"{}")
    classifier_calls = 0

    def unsupported(*_args: object, **_kwargs: object) -> object:
        nonlocal classifier_calls
        classifier_calls += 1
        raise UnsupportedFilesystemError("unclassified_filesystem")

    monkeypatch.setattr(verify_module, "classify_filesystem", unsupported)
    result = verify_capsule(corrupt, mode=VerificationMode.PREPARED)

    assert classifier_calls == 1
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    assert result.first_error.path == "seal.json"


@pytest.mark.parametrize(
    ("residue", "expected_status"),
    [
        ("none", "valid"),
        ("matching", "valid"),
        ("matching-hardlink", "valid"),
        ("mismatching", "invalid"),
        ("wrong-transaction", "invalid"),
        ("second", "invalid"),
    ],
)
def test_sealed_temporary_rule_is_exact_and_read_only(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    residue: str,
    expected_status: str,
) -> None:
    complete, _blocked = sealed_capsules
    transported = tmp_path / residue
    shutil.copytree(complete, transported)
    seal_bytes = (transported / "seal.json").read_bytes()
    seal = SealV1.model_validate_json(seal_bytes)
    expected_name = f".seal.{seal.seal_transaction_id}.tmp"
    expected_temporary = transported / expected_name
    wrong_name = f".seal.{UUID('d23e4567-e89b-42d3-a456-426614174099')}.tmp"

    if residue == "matching":
        expected_temporary.write_bytes(seal_bytes)
    elif residue == "matching-hardlink":
        expected_temporary.hardlink_to(transported / "seal.json")
    elif residue == "mismatching":
        expected_temporary.write_bytes(b"not-the-seal")
    elif residue == "wrong-transaction":
        (transported / wrong_name).write_bytes(seal_bytes)
    elif residue == "second":
        expected_temporary.write_bytes(seal_bytes)
        (transported / wrong_name).write_bytes(seal_bytes)

    before = _tree_snapshot(transported.parent)
    result = verify_capsule(transported, mode=VerificationMode.PREPARED)
    after = _tree_snapshot(transported.parent)

    assert result.status == expected_status
    if expected_status == "invalid":
        assert result.first_error is not None
        assert result.first_error.code == "seal_mismatch"
    assert after == before


@pytest.mark.parametrize(
    "wrong_transaction",
    [
        "00000000-0000-4000-8000-000000000000",
        "ffffffff-ffff-4fff-bfff-ffffffffffff",
    ],
)
def test_duplicate_temporary_reports_the_wrong_member_on_either_lexical_side(
    sealed_capsules: tuple[Path, Path],
    wrong_transaction: str,
) -> None:
    complete, _blocked = sealed_capsules
    seal_bytes = (complete / "seal.json").read_bytes()
    seal = SealV1.model_validate_json(seal_bytes)
    expected_name = f".seal.{seal.seal_transaction_id}.tmp"
    wrong_name = f".seal.{wrong_transaction}.tmp"
    assert wrong_name != expected_name
    (complete / expected_name).write_bytes(seal_bytes)
    (complete / wrong_name).write_bytes(seal_bytes)

    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    assert result.first_error.path == wrong_name


@pytest.mark.parametrize(
    ("wrong_transaction", "first_failure"),
    [
        ("00000000-0000-4000-8000-000000000000", "wrong"),
        ("ffffffff-ffff-4fff-bfff-ffffffffffff", "matching"),
    ],
)
def test_mixed_temp_name_and_byte_failures_use_utf8_path_order(
    sealed_capsules: tuple[Path, Path],
    wrong_transaction: str,
    first_failure: str,
) -> None:
    complete, _blocked = sealed_capsules
    seal_bytes = (complete / "seal.json").read_bytes()
    seal = SealV1.model_validate_json(seal_bytes)
    expected_name = f".seal.{seal.seal_transaction_id}.tmp"
    wrong_name = f".seal.{wrong_transaction}.tmp"
    (complete / expected_name).write_bytes(b"bad-matching-temp")
    (complete / wrong_name).write_bytes(seal_bytes)

    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    expected_failure = expected_name if first_failure == "matching" else wrong_name
    assert result.first_error.path == expected_failure


def test_request_absence_with_artifacts_reports_first_utf8_artifact(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    seal_bytes = (complete / "seal.json").read_bytes()
    seal = SealV1.model_validate_json(seal_bytes)
    temporary_name = f".seal.{seal.seal_transaction_id}.tmp"
    (complete / temporary_name).write_bytes(seal_bytes)
    events_path = complete / "events.jsonl"
    rows = [json.loads(line) for line in events_path.read_bytes().splitlines()]
    assert rows[-1]["kind"] == "seal_requested"
    events_path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in rows[:-1]))

    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    assert result.first_error.path == temporary_name


def test_earlier_matching_temp_alias_precedes_later_wrong_temp(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    seal_bytes = (complete / "seal.json").read_bytes()
    seal = SealV1.model_validate_json(seal_bytes)
    temporary_name = f".seal.{seal.seal_transaction_id}.tmp"
    (complete / temporary_name).hardlink_to(complete / ".laconian.lock")
    wrong_name = ".seal.ffffffff-ffff-4fff-bfff-ffffffffffff.tmp"
    assert temporary_name < wrong_name
    (complete / wrong_name).write_bytes(seal_bytes)

    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    assert result.first_error.path == temporary_name


def test_dual_retained_artifact_mismatch_uses_utf8_path_order(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    exact_seal = seal_path.read_bytes()
    seal = SealV1.model_validate_json(exact_seal)
    temporary_name = f".seal.{seal.seal_transaction_id}.tmp"
    corrupt = b"x" + exact_seal[1:]
    (complete / temporary_name).write_bytes(corrupt)
    seal_path.write_bytes(corrupt)

    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    assert result.first_error.path == temporary_name


def test_earlier_temporary_byte_mismatch_precedes_later_seal_alias(
    sealed_capsules: tuple[Path, Path],
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    seal = SealV1.model_validate_json(seal_path.read_bytes())
    temporary_name = f".seal.{seal.seal_transaction_id}.tmp"
    (complete / temporary_name).write_bytes(b"bad-temp")
    seal_path.unlink()
    seal_path.hardlink_to(complete / ".laconian.lock")

    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    assert result.first_error.path == temporary_name


def test_seal_is_reread_after_final_recursive_inventory(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    original = seal_path.read_bytes()
    real_scan = verify_module._scan_inventory
    scans = 0

    def mutate_after_final_inventory(*args: Any, **kwargs: Any) -> object:
        nonlocal scans
        inventory = real_scan(*args, **kwargs)
        scans += 1
        if scans == 2:
            seal_path.write_bytes(b"x" + original[1:])
        return inventory

    monkeypatch.setattr(verify_module, "_scan_inventory", mutate_after_final_inventory)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert scans == 2
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "seal.json"


def test_seal_type_swap_after_final_inventory_is_path_specific_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    real_scan = verify_module._scan_inventory
    scans = 0

    def type_swap_after_final_inventory(*args: Any, **kwargs: Any) -> object:
        nonlocal scans
        inventory = real_scan(*args, **kwargs)
        scans += 1
        if scans == 2:
            seal_path.unlink()
            seal_path.mkdir()
        return inventory

    monkeypatch.setattr(verify_module, "_scan_inventory", type_swap_after_final_inventory)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert scans == 2
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "seal.json"


def test_raced_seal_content_mismatch_is_unstable_not_a_stable_seal_mismatch(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    seal_inode = seal_path.stat().st_ino
    real_read = verify_module.os.read
    raced = False

    def mutate_during_exact_read(descriptor: int, length: int) -> bytes:
        nonlocal raced
        chunk = real_read(descriptor, length)
        if chunk and not raced and verify_module.os.fstat(descriptor).st_ino == seal_inode:
            raced = True
            mutated = b"x" + seal_path.read_bytes()[1:]
            seal_path.write_bytes(mutated)
            return b"x" + chunk[1:]
        return chunk

    monkeypatch.setattr(verify_module.os, "read", mutate_during_exact_read)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert raced
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "seal.json"


def test_raced_seal_size_mismatch_is_unstable_not_a_stable_seal_mismatch(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    exact_seal = seal_path.read_bytes()
    seal_path.write_bytes(exact_seal + b"x")
    seal_inode = seal_path.stat().st_ino
    real_fstat = verify_module.os.fstat
    raced = False

    def mutate_after_before_stat(descriptor: int) -> Any:
        nonlocal raced
        observed = real_fstat(descriptor)
        if not raced and observed.st_ino == seal_inode and observed.st_size == len(exact_seal) + 1:
            raced = True
            seal_path.write_bytes(exact_seal)
        return observed

    monkeypatch.setattr(verify_module.os, "fstat", mutate_after_before_stat)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert raced
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "seal.json"


def test_preseal_deletion_before_stable_seal_mismatch_is_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    exact_seal = seal_path.read_bytes()
    seal_path.write_bytes(b"x" + exact_seal[1:])
    baseline_path = complete / "inputs/arms/baseline.txt"
    real_verify_exact = verify_module._verify_file_exact
    mutated = False

    def delete_before_first_exact(*args: Any, **kwargs: Any) -> None:
        nonlocal mutated
        if not mutated:
            baseline_path.unlink()
            mutated = True
        real_verify_exact(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_verify_file_exact", delete_before_first_exact)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert mutated
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "inputs/arms/baseline.txt"


def test_unsupported_transport_ignores_only_a_regular_lock_file(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    transport = tmp_path / "transport-invalid-lock"
    shutil.copytree(complete, transport)
    (transport / ".laconian.lock").unlink()
    (transport / ".laconian.lock").mkdir()

    def unsupported(*_args: object, **_kwargs: object) -> object:
        raise UnsupportedFilesystemError("unclassified_filesystem")

    monkeypatch.setattr(verify_module, "classify_filesystem", unsupported)
    result = verify_capsule(transport, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unsafe_path_type"
    assert result.first_error.path == ".laconian.lock"


def test_lock_omission_warning_uses_the_stable_verified_inventory(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    transport = tmp_path / "transport-lock-race"
    shutil.copytree(complete, transport)
    real_probe = verify_module._top_level_entry_present

    def stale_absent_probe(root_fd: int, name: str) -> bool:
        if name == ".laconian.lock":
            return False
        return real_probe(root_fd, name)

    monkeypatch.setattr(verify_module, "_top_level_entry_present", stale_absent_probe)
    result = verify_capsule(transport, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert "lock_file_omitted_for_sealed_transport" not in result.warnings


def test_stale_lock_presence_probe_cannot_suppress_omission_warning(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    transport = tmp_path / "transport-stale-present-lock"
    shutil.copytree(complete, transport)
    (transport / ".laconian.lock").unlink()
    real_probe = verify_module._top_level_entry_present

    def stale_present_probe(root_fd: int, name: str) -> bool:
        if name == ".laconian.lock":
            return True
        return real_probe(root_fd, name)

    monkeypatch.setattr(verify_module, "_top_level_entry_present", stale_present_probe)
    result = verify_capsule(transport, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert result.warnings[-1] == "lock_file_omitted_for_sealed_transport"


def test_supported_sealed_capsule_observes_busy_shared_lock(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", lambda *_args, **_kwargs: None)

    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "busy"


def test_unsupported_sealed_transport_does_not_acquire_existing_lock(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules

    def unsupported(*_args: object, **_kwargs: object) -> object:
        raise UnsupportedFilesystemError("unclassified_filesystem")

    def lock_bomb(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unsupported sealed transport must remain lockless")

    monkeypatch.setattr(verify_module, "classify_filesystem", unsupported)
    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", lock_bomb)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert "lock_file_omitted_for_sealed_transport" not in result.warnings


def test_ignored_lock_becoming_a_seal_alias_during_final_scan_is_unstable(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    transport = tmp_path / "ignored-lock-alias-race"
    shutil.copytree(complete, transport)
    real_scan = verify_module._scan_inventory
    scans = 0

    def unsupported(*_args: object, **_kwargs: object) -> object:
        raise UnsupportedFilesystemError("unclassified_filesystem")

    def alias_before_final_scan(*args: Any, **kwargs: Any) -> object:
        nonlocal scans
        scans += 1
        if scans == 2:
            lock_path = transport / ".laconian.lock"
            lock_path.unlink()
            lock_path.hardlink_to(transport / "seal.json")
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(verify_module, "classify_filesystem", unsupported)
    monkeypatch.setattr(verify_module, "_scan_inventory", alias_before_final_scan)
    result = verify_capsule(transport, mode=VerificationMode.PREPARED)

    assert scans == 2
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path in {None, "seal.json"}


def test_lockless_unsealed_transport_still_requires_persistent_lock(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked = sealed_capsules
    unsealed = tmp_path / "unsealed-no-lock"
    shutil.copytree(complete, unsealed)
    (unsealed / "seal.json").unlink()
    (unsealed / ".laconian.lock").unlink()

    result = verify_capsule(unsealed, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "missing_path"
    assert result.first_error.path == ".laconian.lock"


def test_lockless_sealed_verification_does_not_construct_posix_ops(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    transport = tmp_path / "transport-no-posix"
    shutil.copytree(complete, transport)
    (transport / ".laconian.lock").unlink()

    def posix_bomb() -> object:
        raise AssertionError("lockless sealed verification must not construct POSIX lock ops")

    monkeypatch.setattr(verify_module, "PosixOps", posix_bomb)
    result = verify_capsule(transport, mode=VerificationMode.PREPARED)

    assert result.status == "valid"


def test_sticky_seal_disappearance_before_first_inventory_is_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    real_probe = verify_module._top_level_entry_identity
    removed = False

    def remove_after_probe(root_fd: int, name: str) -> object:
        nonlocal removed
        identity = real_probe(root_fd, name)
        if name == "seal.json" and identity is not None and not removed:
            (complete / name).unlink()
            removed = True
        return identity

    monkeypatch.setattr(verify_module, "_top_level_entry_identity", remove_after_probe)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "seal.json"


def test_initial_sealed_inventory_eio_is_not_remapped_to_instability(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    real_scan = verify_module._scan_inventory
    injected = False

    def fail_initial_scan(*args: Any, **kwargs: Any) -> object:
        nonlocal injected
        if not injected and kwargs.get("expected_inventory") is None:
            injected = True
            raise verify_module._Failure("io_error", "seal.json")  # type: ignore[attr-defined]
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_scan_inventory", fail_initial_scan)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert injected
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "io_error"
    assert result.first_error.path == "seal.json"


@pytest.mark.parametrize("mutation", ["delete", "add", "type-swap"])
def test_final_recursive_inventory_namespace_races_are_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    complete, _blocked = sealed_capsules
    real_scan = verify_module._scan_inventory
    scans = 0

    def mutate_before_final_scan(*args: Any, **kwargs: Any) -> object:
        nonlocal scans
        scans += 1
        if scans == 2:
            if mutation == "delete":
                (complete / "manifest.json").unlink()
            elif mutation == "add":
                (complete / "unexpected").write_bytes(b"race")
            else:
                (complete / "manifest.json").unlink()
                (complete / "manifest.json").mkdir()
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_scan_inventory", mutate_before_final_scan)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path in {"manifest.json", "unexpected"}


def test_seal_published_before_shared_lock_is_verified_under_refreshed_root(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    exact_seal = seal_path.read_bytes()
    seal_path.unlink()
    real_acquire = verify_module.try_acquire_shared_lock

    def publish_then_acquire(*args: Any, **kwargs: Any) -> object:
        seal_path.write_bytes(exact_seal)
        return real_acquire(*args, **kwargs)

    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", publish_then_acquire)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert result.state == "SEALED_COMPLETE"
    assert result.capsule_sha256 == sha256_bytes(exact_seal)


def test_initially_published_seal_replaced_before_shared_lock_is_unstable(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    replacement = tmp_path / "replacement-seal.json"
    replacement.write_bytes(seal_path.read_bytes())
    original_inode = seal_path.stat().st_ino
    replacement_inode = replacement.stat().st_ino
    assert replacement_inode != original_inode
    real_acquire = verify_module.try_acquire_shared_lock

    def replace_then_acquire(*args: Any, **kwargs: Any) -> object:
        replacement.replace(seal_path)
        return real_acquire(*args, **kwargs)

    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", replace_then_acquire)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert seal_path.stat().st_ino == replacement_inode
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "seal.json"


def test_hardlinked_temporary_cleanup_before_shared_lock_remains_valid(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    seal_path = complete / "seal.json"
    seal = SealV1.model_validate_json(seal_path.read_bytes())
    temporary_path = complete / f".seal.{seal.seal_transaction_id}.tmp"
    temporary_path.hardlink_to(seal_path)
    pre_cleanup_identity = seal_path.stat()
    real_acquire = verify_module.try_acquire_shared_lock
    cleaned = False

    def cleanup_then_acquire(*args: Any, **kwargs: Any) -> object:
        nonlocal cleaned
        temporary_path.unlink()
        cleaned = True
        return real_acquire(*args, **kwargs)

    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", cleanup_then_acquire)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    post_cleanup_identity = seal_path.stat()
    assert cleaned
    assert post_cleanup_identity.st_ino == pre_cleanup_identity.st_ino
    assert result.status == "valid"
    assert result.state == "SEALED_COMPLETE"


@pytest.mark.parametrize("mutation", ["delete", "type-swap"])
def test_context_read_namespace_race_is_path_specific_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    complete, _blocked = sealed_capsules
    capsule_path = complete / "capsule.json"
    real_read_file = verify_module._read_file
    mutated = False

    def mutate_before_context_read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal mutated
        path = args[1]
        if path == "capsule.json" and not mutated:
            capsule_path.unlink()
            if mutation == "type-swap":
                capsule_path.mkdir()
            mutated = True
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_read_file", mutate_before_context_read)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert mutated
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "capsule.json"


def test_changed_nested_directory_identity_preempts_later_traversal_eacces(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    arms_directory = complete / "inputs/arms"
    original_mode = stat.S_IMODE(arms_directory.stat().st_mode)
    real_read_file = verify_module._read_file
    mutated = False

    def chmod_before_nested_read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal mutated
        if args[1] == "inputs/arms/baseline.txt" and not mutated:
            arms_directory.chmod(0)
            mutated = True
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_read_file", chmod_before_nested_read)
    try:
        result = verify_capsule(complete, mode=VerificationMode.PREPARED)
    finally:
        arms_directory.chmod(original_mode)

    assert mutated
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "inputs/arms"


def test_directory_change_between_expected_stat_and_open_preempts_eacces(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    arms_directory = complete / "inputs/arms"
    original_mode = stat.S_IMODE(arms_directory.stat().st_mode)
    real_read_file = verify_module._read_file
    real_open = verify_module.os.open
    diagnostic_scan = False
    mutated = False

    def fail_context_read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal diagnostic_scan
        if args[1] == "capsule.json" and not diagnostic_scan:
            diagnostic_scan = True
            raise verify_module._Failure("io_error", "capsule.json")  # type: ignore[attr-defined]
        return real_read_file(*args, **kwargs)

    def chmod_immediately_before_open(*args: Any, **kwargs: Any) -> int:
        nonlocal mutated
        if diagnostic_scan and args[0] == "arms" and not mutated:
            arms_directory.chmod(0)
            mutated = True
        return real_open(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_read_file", fail_context_read)
    monkeypatch.setattr(verify_module.os, "open", chmod_immediately_before_open)
    try:
        result = verify_capsule(complete, mode=VerificationMode.PREPARED)
    finally:
        arms_directory.chmod(original_mode)

    assert diagnostic_scan
    assert mutated
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "inputs/arms"


def test_expected_scan_eio_with_unchanged_directory_identity_remains_io_error(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    real_read_file = verify_module._read_file
    real_open = verify_module.os.open
    diagnostic_scan = False
    injected = False

    def fail_context_read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal diagnostic_scan
        if args[1] == "capsule.json" and not diagnostic_scan:
            diagnostic_scan = True
            raise verify_module._Failure("io_error", "capsule.json")  # type: ignore[attr-defined]
        return real_read_file(*args, **kwargs)

    def fail_unchanged_directory_open(*args: Any, **kwargs: Any) -> int:
        nonlocal injected
        if diagnostic_scan and args[0] == "arms" and not injected:
            injected = True
            raise OSError(errno.EIO, "injected stable EIO")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_read_file", fail_context_read)
    monkeypatch.setattr(verify_module.os, "open", fail_unchanged_directory_open)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert diagnostic_scan
    assert injected
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "io_error"
    assert result.first_error.path == "capsule.json"


def test_root_identity_delta_preempts_expected_scan_scandir_eacces(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    original_mode = stat.S_IMODE(complete.stat().st_mode)
    root_fd = verify_module.os.open(complete, verify_module._directory_flags())
    selected_seal_identity = verify_module._top_level_entry_identity(root_fd, "seal.json")
    real_read_file = verify_module._read_file
    real_scandir = verify_module.os.scandir
    diagnostic_scan = False
    injected = False

    def fail_context_after_root_chmod(*args: Any, **kwargs: Any) -> bytes:
        nonlocal diagnostic_scan
        if args[1] == "capsule.json" and not diagnostic_scan:
            complete.chmod(0)
            diagnostic_scan = True
            raise verify_module._Failure("io_error", "capsule.json")  # type: ignore[attr-defined]
        return real_read_file(*args, **kwargs)

    def fail_changed_root_scandir(directory_fd: int) -> Any:
        nonlocal injected
        if diagnostic_scan and directory_fd == root_fd and not injected:
            injected = True
            raise PermissionError(errno.EACCES, "injected changed-root EACCES")
        return real_scandir(directory_fd)

    monkeypatch.setattr(verify_module, "_read_file", fail_context_after_root_chmod)
    monkeypatch.setattr(verify_module.os, "scandir", fail_changed_root_scandir)
    try:
        with pytest.raises(verify_module._Failure) as caught:  # type: ignore[attr-defined]
            verify_module._verify_sealed_core(
                root_fd,
                selected_seal_identity=selected_seal_identity,
            )
    finally:
        complete.chmod(original_mode)
        verify_module.os.close(root_fd)

    assert diagnostic_scan
    assert injected
    assert caught.value.code == "unstable_snapshot"
    assert caught.value.path is None


@pytest.mark.parametrize("mutation", ["delete", "type-swap"])
def test_hash_phase_namespace_race_is_path_specific_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    complete, _blocked = sealed_capsules
    manifest_path = complete / "manifest.json"
    real_hash = verify_module._hash_inventory_file
    mutated = False

    def mutate_before_hash(*args: Any, **kwargs: Any) -> object:
        nonlocal mutated
        path = args[1]
        if path == "manifest.json" and not mutated:
            manifest_path.unlink()
            if mutation == "type-swap":
                manifest_path.mkdir()
            mutated = True
        return real_hash(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_hash_inventory_file", mutate_before_hash)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert mutated
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "manifest.json"


def test_journal_mutation_after_inventory_preempts_semantic_failure_as_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    events_path = complete / "events.jsonl"
    real_snapshot = verify_module.snapshot_journal_pair
    mutated = False

    def mutate_before_journal_snapshot(*args: Any, **kwargs: Any) -> object:
        nonlocal mutated
        if not mutated:
            events_path.write_bytes(b"{}\n")
            mutated = True
        return real_snapshot(*args, **kwargs)

    monkeypatch.setattr(verify_module, "snapshot_journal_pair", mutate_before_journal_snapshot)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert mutated
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unstable_snapshot"
    assert result.first_error.path == "events.jsonl"


def test_stable_context_io_error_is_not_remapped_to_unstable(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    real_read_file = verify_module._read_file
    injected = False

    def fail_capsule_read(*args: Any, **kwargs: Any) -> bytes:
        nonlocal injected
        if args[1] == "capsule.json" and not injected:
            injected = True
            raise verify_module._Failure("io_error", "capsule.json")  # type: ignore[attr-defined]
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_read_file", fail_capsule_read)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert injected
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "io_error"
    assert result.first_error.path == "capsule.json"


def test_static_failure_precedes_a_simultaneously_corrupt_seal(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked = sealed_capsules
    corrupt = tmp_path / "dual-corrupt"
    shutil.copytree(complete, corrupt)
    (corrupt / "capsule.json").write_bytes(b"{}")
    (corrupt / "seal.json").write_bytes(b"{}")

    result = verify_capsule(corrupt, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "unsupported_schema"
    assert result.first_error.path == "capsule.json"


@pytest.mark.parametrize(
    ("mutation", "expected_code", "expected_path"),
    [
        ("missing-member", "missing_path", "manifest.json"),
        ("renamed-member", "missing_path", "manifest.json"),
        ("changed-preseal-bytes", "hash_mismatch", "inputs/arms/baseline.txt"),
        ("forged-seal-field", "seal_mismatch", "seal.json"),
        ("forged-seal-inventory", "seal_mismatch", "seal.json"),
    ],
)
def test_sealed_tamper_matrix_rejects_missing_renamed_bytes_and_forged_seal(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    expected_path: str,
) -> None:
    complete, _blocked = sealed_capsules
    tampered = tmp_path / mutation
    shutil.copytree(complete, tampered)
    if mutation == "missing-member":
        (tampered / "manifest.json").unlink()
    elif mutation == "renamed-member":
        (tampered / "manifest.json").rename(tampered / "unexpected")
    elif mutation == "changed-preseal-bytes":
        (tampered / "inputs/arms/baseline.txt").write_bytes(b"tampered")
    else:
        payload = json.loads((tampered / "seal.json").read_bytes())
        if mutation == "forged-seal-field":
            payload["final_event_sequence"] += 1
        else:
            payload["files"][0]["sha256"] = "f" * 64
        (tampered / "seal.json").write_bytes(canonical_json(payload))

    result = verify_capsule(tampered, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == expected_code
    assert result.first_error.path == expected_path


def test_second_inventory_child_close_failure_remains_io_error(
    sealed_capsules: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked = sealed_capsules
    real_scan = verify_module._scan_inventory
    real_close_owned = verify_module._close_owned
    scans = 0
    injected = False
    injected_descriptors: list[int] = []

    def tracked_scan(*args: Any, **kwargs: Any) -> object:
        nonlocal scans
        scans += 1
        return real_scan(*args, **kwargs)

    def fail_one_child_close(
        descriptor: int,
        *,
        path: str | None,
        primary: BaseException | None = None,
    ) -> BaseException | None:
        nonlocal injected
        result = real_close_owned(descriptor, path=path, primary=primary)
        if scans == 2 and path == "inputs/arms" and primary is None and not injected:
            injected = True
            injected_descriptors.append(descriptor)
            return verify_module._Failure("io_error", path)  # type: ignore[attr-defined]
        return result

    monkeypatch.setattr(verify_module, "_scan_inventory", tracked_scan)
    monkeypatch.setattr(verify_module, "_close_owned", fail_one_child_close)
    result = verify_capsule(complete, mode=VerificationMode.PREPARED)

    assert scans == 3
    assert len(injected_descriptors) == 1
    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "io_error"
    assert result.first_error.path == "inputs/arms"


@pytest.mark.parametrize("unsupported", [False, True])
def test_seal_may_not_alias_the_operational_lock(
    sealed_capsules: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsupported: bool,
) -> None:
    complete, _blocked = sealed_capsules
    transported = tmp_path / f"seal-lock-alias-{unsupported}"
    shutil.copytree(complete, transported)
    lock_path = transported / ".laconian.lock"
    lock_path.unlink()
    lock_path.hardlink_to(transported / "seal.json")
    if unsupported:
        monkeypatch.setattr(
            verify_module,
            "classify_filesystem",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                UnsupportedFilesystemError("unclassified_filesystem")
            ),
        )

    result = verify_capsule(transported, mode=VerificationMode.PREPARED)

    assert result.status == "invalid"
    assert result.first_error is not None
    assert result.first_error.code == "seal_mismatch"
    assert result.first_error.path == "seal.json"


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int, int, int, int, int, bytes | None]]:
    snapshot: dict[str, tuple[int, int, int, int, int, int, bytes | None]] = {}
    members = (root, *sorted(root.rglob("*"), key=lambda path: path.as_posix().encode("utf-8")))
    for member in members:
        metadata = member.lstat()
        relative = "." if member == root else member.relative_to(root).as_posix()
        payload = member.read_bytes() if stat.S_ISREG(metadata.st_mode) else None
        snapshot[relative] = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
            payload,
        )
    return snapshot
