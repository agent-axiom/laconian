from __future__ import annotations

import json
import os
import shutil
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from capsule_helpers import plan_row_v1_payload, raw_attempt_v2_payload
from pydantic import ValidationError

import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.sidecars as sidecar_module
from laconian_eval.capsule.attempts import RawAttemptV2, raw_attempt_bytes
from laconian_eval.capsule.bounded_io import _descriptor_bound_path, open_directory_no_follow
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes, stable_digest
from laconian_eval.capsule.execution import ProviderFactory
from laconian_eval.capsule.finalize import finalize_capsule
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.scorable import HardCheckV2, ScoredAttemptV2
from laconian_eval.capsule.sidecars import (
    ScoredCapsuleSidecarV2,
    SidecarError,
    VerifiedScoredCapsuleV2,
    load_verified_scored_capsule,
    write_scored_sidecar,
)
from laconian_eval.providers import GenerationResult

from .test_execution import (
    _benchmark_replay_outcome,
    _BenchmarkScriptedProvider,
    _install_fast_runtime,
    _ScriptedProvider,
    _seams_for_provider,
    _single_plan_capsule,
)
from .test_prepare import _load_shard_success


def _scored_attempt(*, ordinal: int = 0, marker: str = "first") -> ScoredAttemptV2:
    plan_payload = plan_row_v1_payload()
    plan_payload.update(
        ordinal=ordinal,
        plan_item_id=sha256_bytes(f"plan:{marker}".encode()),
        pairing_unit_id=sha256_bytes(f"pair:{marker}".encode()),
        case_uid=sha256_bytes(f"case:{marker}".encode()),
        scenario_uid=sha256_bytes(f"scenario:{marker}".encode()),
        block_id=sha256_bytes(f"block:{marker}".encode()),
    )
    plan = PlanRowV1.model_validate(plan_payload)
    raw = RawAttemptV2.model_validate(raw_attempt_v2_payload(plan.model_dump(mode="json")))
    return ScoredAttemptV2(
        schema_version="2",
        ordinal=plan.ordinal,
        plan_item_id=plan.plan_item_id,
        attempt_id=raw.attempt_id,
        raw_attempt_sha256=sha256_bytes(raw_attempt_bytes(raw)),
        case_uid=raw.case_uid,
        case_definition_sha256=raw.case_definition_sha256,
        response_id=raw.response_id,
        terminal_reason="success",
        raw=raw,
        checks=(HardCheckV2(name="content.nonblank", passed=True),),
        hard_pass=True,
    )


def _sidecar_payload(
    scored_attempts: tuple[ScoredAttemptV2, ...] | None = None,
) -> dict[str, Any]:
    rows = (_scored_attempt(),) if scored_attempts is None else scored_attempts
    payload: dict[str, Any] = {
        "sidecar_schema_version": "2",
        "scoring_algorithm_version": "laconian-deterministic-hard-v2",
        "capsule_sha256": "1" * 64,
        "manifest_sha256": "2" * 64,
        "case_index_sha256": "3" * 64,
        "plan_sha256": "4" * 64,
        "raw_sha256": "5" * 64,
        "ordered_plan_item_ids": tuple(row.plan_item_id for row in rows),
        "scored_attempts": rows,
    }
    payload["sidecar_sha256"] = stable_digest(
        "laconian-scored-capsule-sidecar-v2",
        {
            **{key: value for key, value in payload.items() if key != "scored_attempts"},
            "scored_attempts": [row.model_dump(mode="json") for row in rows],
        },
    )
    return payload


def _rehash(payload: dict[str, Any]) -> dict[str, Any]:
    updated = dict(payload)
    preimage = {key: value for key, value in updated.items() if key != "sidecar_sha256"}
    preimage["scored_attempts"] = [
        row.model_dump(mode="json") if isinstance(row, ScoredAttemptV2) else row
        for row in preimage["scored_attempts"]
    ]
    updated["sidecar_sha256"] = stable_digest(
        "laconian-scored-capsule-sidecar-v2",
        preimage,
    )
    return updated


def test_scored_sidecar_round_trips_and_self_hashes_exactly() -> None:
    payload = _sidecar_payload()
    sidecar = ScoredCapsuleSidecarV2.model_validate(payload)

    expected = stable_digest(
        "laconian-scored-capsule-sidecar-v2",
        {
            "sidecar_schema_version": "2",
            "scoring_algorithm_version": "laconian-deterministic-hard-v2",
            "capsule_sha256": payload["capsule_sha256"],
            "manifest_sha256": payload["manifest_sha256"],
            "case_index_sha256": payload["case_index_sha256"],
            "plan_sha256": payload["plan_sha256"],
            "raw_sha256": payload["raw_sha256"],
            "ordered_plan_item_ids": payload["ordered_plan_item_ids"],
            "scored_attempts": [row.model_dump(mode="json") for row in sidecar.scored_attempts],
        },
    )
    assert sidecar.sidecar_sha256 == expected
    assert tuple(ScoredCapsuleSidecarV2.model_fields) == (
        "sidecar_schema_version",
        "scoring_algorithm_version",
        "capsule_sha256",
        "manifest_sha256",
        "case_index_sha256",
        "plan_sha256",
        "raw_sha256",
        "ordered_plan_item_ids",
        "scored_attempts",
        "sidecar_sha256",
    )
    encoded = canonical_json(sidecar.model_dump(mode="json"))
    assert ScoredCapsuleSidecarV2.model_validate_json(encoded) == sidecar


def test_scored_sidecar_rejects_invalid_versions_hashes_order_and_judgments() -> None:
    first = _scored_attempt(ordinal=0, marker="first")
    second = _scored_attempt(ordinal=1, marker="second")
    valid = _sidecar_payload((first, second))

    mutations: tuple[dict[str, Any], ...] = (
        valid | {"scoring_algorithm_version": "future-scoring"},
        valid | {"sidecar_sha256": "0" * 64},
        _rehash(valid | {"ordered_plan_item_ids": ()}),
        _rehash(valid | {"ordered_plan_item_ids": (first.plan_item_id,) * 2}),
        _rehash(
            valid
            | {
                "ordered_plan_item_ids": (
                    second.plan_item_id,
                    first.plan_item_id,
                )
            }
        ),
        _rehash(valid | {"scored_attempts": (second, first)}),
        valid | {"capsule_sha256": "x" * 64},
        valid | {"manifest_sha256": "2" * 63},
        valid | {"case_index_sha256": "A" * 64},
        valid | {"plan_sha256": "-" * 64},
        valid | {"raw_sha256": "5" * 65},
        valid | {"unknown": "forbidden"},
        valid | {"semantic_pass": True},
        valid | {"detail": "later-stage judgment"},
    )
    for payload in mutations:
        with pytest.raises(ValidationError):
            ScoredCapsuleSidecarV2.model_validate(payload)


def test_scored_sidecar_rejects_forged_nested_scored_model() -> None:
    scored = _scored_attempt()
    forged = ScoredAttemptV2.model_construct(**(scored.__dict__ | {"ordinal": 7}))
    payload = _rehash(_sidecar_payload() | {"scored_attempts": (forged,)})

    with pytest.raises(ValidationError):
        ScoredCapsuleSidecarV2.model_validate(payload)


@pytest.fixture
def sealed_shard_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    prepared, _harness, _manifest, _parent_plan, shard = _load_shard_success(
        tmp_path,
        monkeypatch,
    )
    assert shard.row_count == 40  # type: ignore[union-attr]
    monkeypatch.setattr(
        execution_module._fake_provider_module,
        "FakeProvider",
        execution_module._FAKE_PROVIDER_TYPE,
    )
    monkeypatch.setattr(
        execution_module._replay_provider_module,
        "ReplayProvider",
        execution_module._REPLAY_PROVIDER_TYPE,
    )
    monkeypatch.setattr(
        execution_module._openai_provider_module,
        "OpenAIProvider",
        execution_module._OPENAI_PROVIDER_TYPE,
    )
    _install_fast_runtime(monkeypatch)
    evidence = _benchmark_replay_outcome(returned_service_tier="default")
    provider = _BenchmarkScriptedProvider([evidence] * 40)
    outcome = execution_module._resume_capsule(
        prepared.path,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(provider.benchmark_calls) == 40
    assert finalize_capsule(prepared.path).state == "SEALED_COMPLETE"
    return prepared.path


@pytest.fixture
def sealed_small_capsules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    complete_root = tmp_path / "complete-root"
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

    blocked_root = tmp_path / "blocked-root"
    blocked_root.mkdir()
    blocked = _single_plan_capsule(blocked_root, monkeypatch)
    assert finalize_capsule(blocked, seal_incomplete=True).state == "SEALED_BLOCKED"

    unsealed_root = tmp_path / "unsealed-root"
    unsealed_root.mkdir()
    unsealed = _single_plan_capsule(unsealed_root, monkeypatch)
    return complete, blocked, unsealed


def _tree_snapshot(root: Path) -> dict[str, tuple[int, int, int, int, bytes | None]]:
    snapshot: dict[str, tuple[int, int, int, int, bytes | None]] = {}
    for path in (root, *sorted(root.rglob("*"))):
        metadata = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        snapshot[relative] = (
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
            path.read_bytes() if path.is_file() and not path.is_symlink() else None,
        )
    return snapshot


def test_write_and_load_verified_scored_sidecar_for_complete_40_row_shard(
    sealed_shard_capsule: Path,
) -> None:
    capsule_path = sealed_shard_capsule
    sidecar_path = capsule_path.parent / "scored-sidecar.json"

    sidecar_hash = write_scored_sidecar(capsule_path, sidecar_path)
    before_capsule = _tree_snapshot(capsule_path)
    before_parent = _tree_snapshot(capsule_path.parent)
    evidence = load_verified_scored_capsule(capsule_path, sidecar_path)

    assert type(evidence) is VerifiedScoredCapsuleV2
    assert evidence.capsule_sha256 == sha256_bytes((capsule_path / "seal.json").read_bytes())
    seal_files = {item.path: item for item in evidence.seal.files}
    assert evidence.manifest_sha256 == seal_files["manifest.json"].sha256
    assert evidence.plan_sha256 == seal_files["plan.jsonl"].sha256
    assert tuple(row.plan_item_id for row in evidence.plan) == tuple(
        row.plan_item_id for row in evidence.scored_attempts
    )
    assert len(evidence.plan) == len(evidence.scored_attempts) == 40
    assert set(evidence.cases_by_uid) == {row.case_uid for row in evidence.plan}
    assert type(evidence.cases_by_uid) is type(MappingProxyType({}))
    assert (
        sidecar_hash
        == ScoredCapsuleSidecarV2.model_validate_json(sidecar_path.read_bytes()).sidecar_sha256
    )
    assert sidecar_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(TypeError):
        evidence.cases_by_uid[next(iter(evidence.cases_by_uid))] = next(  # type: ignore[index]
            iter(evidence.cases_by_uid.values())
        )
    with pytest.raises(FrozenInstanceError):
        evidence.capsule_sha256 = "0" * 64  # type: ignore[misc]
    assert _tree_snapshot(capsule_path) == before_capsule
    assert _tree_snapshot(capsule_path.parent) == before_parent


def test_write_scored_sidecar_never_replaces_an_existing_output(
    sealed_shard_capsule: Path,
) -> None:
    sidecar_path = sealed_shard_capsule.parent / "collision.json"
    sentinel = b"user-owned-sidecar\n"
    sidecar_path.write_bytes(sentinel)

    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(sealed_shard_capsule, sidecar_path)

    assert caught.value.code == "destination_collision"
    assert str(caught.value) == "scored capsule sidecar rejected"
    assert sidecar_path.read_bytes() == sentinel
    assert not tuple(sidecar_path.parent.glob(".laconian-scored.*.tmp"))


def test_writer_and_loader_reject_capsule_internal_or_reserved_sidecar_paths(
    sealed_small_capsules: tuple[Path, Path, Path],
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    before = _tree_snapshot(complete)
    internal = complete / "scored.json"
    reserved = complete.parent / ".laconian-scored.123e4567-e89b-42d3-a456-426614174000.tmp"
    reserved_case_alias = (
        complete.parent / ".LACONIAN-SCORED.123e4567-e89b-42d3-a456-426614174000.TMP"
    )
    capsule_marker = complete.parent / "capsule.json"
    capsule_marker_case_alias = complete.parent / "Capsule.JSON"
    aliased_parent = complete.parent / "capsule-parent-alias"
    aliased_parent.symlink_to(complete, target_is_directory=True)
    aliased = aliased_parent / "scored.json"

    for call in (
        lambda: write_scored_sidecar(complete, internal),
        lambda: load_verified_scored_capsule(complete, internal),
        lambda: write_scored_sidecar(complete, reserved),
        lambda: write_scored_sidecar(complete, reserved_case_alias),
        lambda: write_scored_sidecar(complete, capsule_marker),
        lambda: write_scored_sidecar(complete, capsule_marker_case_alias),
        lambda: write_scored_sidecar(complete, aliased),
    ):
        with pytest.raises(SidecarError) as caught:
            call()
        assert caught.value.code in {"invalid_argument", "missing_path", "unsafe_path_type"}
        assert str(caught.value) == "scored capsule sidecar rejected"

    assert _tree_snapshot(complete) == before
    assert not internal.exists()
    assert not reserved.exists()
    assert not reserved_case_alias.exists()
    assert not capsule_marker.exists()
    assert not capsule_marker_case_alias.exists()
    assert not aliased.exists()
    assert not tuple(complete.parent.glob(".laconian-scored.*.tmp"))


def test_writer_and_loader_reject_untrusted_sources_and_sidecar_forms(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    complete, blocked, unsealed = sealed_small_capsules
    for index, source in enumerate((blocked, unsealed)):
        output = tmp_path / f"rejected-source-{index}.json"
        with pytest.raises(SidecarError) as caught:
            write_scored_sidecar(source, output)
        assert caught.value.code == "source_rejected"
        assert not output.exists()

    valid_sidecar = tmp_path / "valid-sidecar.json"
    write_scored_sidecar(complete, valid_sidecar)
    canonical = valid_sidecar.read_bytes()

    symlink = tmp_path / "sidecar-link.json"
    symlink.symlink_to(valid_sidecar)
    fifo = tmp_path / "sidecar-fifo.json"
    os.mkfifo(fifo)
    noncanonical = tmp_path / "sidecar-noncanonical.json"
    noncanonical.write_bytes(b" " + canonical)
    mutated = tmp_path / "sidecar-mutated.json"
    mutated.write_bytes(bytes([canonical[0] ^ 1]) + canonical[1:])

    for existing in (symlink, fifo):
        with pytest.raises(SidecarError) as caught:
            write_scored_sidecar(complete, existing)
        assert caught.value.code == "destination_collision"
        assert existing.is_symlink() if existing == symlink else existing.exists()

    for path, expected_code in (
        (symlink, "unsafe_path_type"),
        (fifo, "unsafe_path_type"),
        (noncanonical, "noncanonical_json"),
        (mutated, "noncanonical_json"),
    ):
        with pytest.raises(SidecarError) as caught:
            load_verified_scored_capsule(complete, path)
        assert caught.value.code == expected_code

    payload = json.loads(canonical)
    for index, field in enumerate(
        (
            "capsule_sha256",
            "manifest_sha256",
            "case_index_sha256",
            "plan_sha256",
            "raw_sha256",
        )
    ):
        forged = dict(payload)
        forged[field] = "0" * 64
        forged["sidecar_sha256"] = stable_digest(
            "laconian-scored-capsule-sidecar-v2",
            {key: value for key, value in forged.items() if key != "sidecar_sha256"},
        )
        path = tmp_path / f"wrong-digest-{index}.json"
        path.write_bytes(canonical_json(forged))
        with pytest.raises(SidecarError) as caught:
            load_verified_scored_capsule(complete, path)
        assert caught.value.code == "sidecar_mismatch"


def test_loader_rejects_each_changed_sealed_source_byte(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    sidecar = tmp_path / "source-bound-sidecar.json"
    write_scored_sidecar(complete, sidecar)
    seal_payload = json.loads((complete / "seal.json").read_bytes())
    case_input = next(
        item["path"] for item in seal_payload["files"] if item["path"].startswith("inputs/cases/")
    )
    members = (
        "seal.json",
        "manifest.json",
        case_input,
        "case-index.jsonl",
        "plan.jsonl",
        "raw.jsonl",
    )

    for index, member in enumerate(members):
        mutated = tmp_path / f"mutated-capsule-{index}"
        shutil.copytree(complete, mutated)
        target = mutated / member
        target.write_bytes(target.read_bytes() + b" ")
        with pytest.raises(SidecarError) as caught:
            load_verified_scored_capsule(mutated, sidecar)
        assert caught.value.code == "source_rejected"


def test_writer_fails_closed_across_temporary_link_fsync_and_identity_seams(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules

    temp_failure_output = tmp_path / "temp-failure.json"

    def fail_after_temporary_open(point: str) -> None:
        if point == "after_temporary_open":
            raise OSError("TEMP-CANARY")

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            temp_failure_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=fail_after_temporary_open
            ),
        )
    assert caught.value.code == "io_error"
    assert not temp_failure_output.exists()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))

    link_failure_output = tmp_path / "link-side-effect.json"

    def link_then_raise(source_fd: int, source: str, target_fd: int, target: str) -> None:
        sidecar_module._default_link_noreplace(  # type: ignore[attr-defined]
            source_fd,
            source,
            target_fd,
            target,
        )
        raise OSError("LINK-CANARY")

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            link_failure_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                link_noreplace=link_then_raise
            ),
        )
    assert caught.value.code == "post_publish_integrity_error"
    assert link_failure_output.is_file()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))

    file_fsync_output = tmp_path / "file-fsync.json"

    def fail_file_fsync(_descriptor: int) -> None:
        raise OSError("FSYNC-CANARY")

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            file_fsync_output,
            seams=sidecar_module._SidecarSeams(fsync=fail_file_fsync),  # type: ignore[attr-defined]
        )
    assert caught.value.code == "io_error"
    assert not file_fsync_output.exists()

    prelink_output = tmp_path / "prelink-mode-race.json"

    def mutate_temporary_before_link(point: str) -> None:
        if point != "before_link_noreplace":
            return
        temporary = tuple(tmp_path.glob(".laconian-scored.*.tmp"))
        assert len(temporary) == 1
        temporary[0].chmod(0o644)

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            prelink_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=mutate_temporary_before_link
            ),
        )
    assert caught.value.code == "unstable_snapshot"
    assert not prelink_output.exists()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))

    parent_fsync_output = tmp_path / "parent-fsync.json"
    fsync_calls = 0

    def fail_parent_fsync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("FSYNC-CANARY")
        os.fsync(descriptor)

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            parent_fsync_output,
            seams=sidecar_module._SidecarSeams(fsync=fail_parent_fsync),  # type: ignore[attr-defined]
        )
    assert caught.value.code == "post_publish_fsync_failed"
    assert parent_fsync_output.is_file()

    postlink_mode_output = tmp_path / "postlink-mode-race.json"

    def broaden_output_after_link(point: str) -> None:
        if point == "after_link_noreplace":
            postlink_mode_output.chmod(0o644)

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            postlink_mode_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=broaden_output_after_link
            ),
        )
    assert caught.value.code == "post_publish_integrity_error"
    assert postlink_mode_output.is_file()

    final_identity_output = tmp_path / "final-identity.json"

    def mutate_after_final_read(point: str) -> None:
        if point != "after_final_output_read":
            return
        data = bytearray(final_identity_output.read_bytes())
        data[-1] ^= 1
        with final_identity_output.open("r+b") as stream:
            stream.write(data)
            stream.flush()

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            final_identity_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=mutate_after_final_read
            ),
        )
    assert caught.value.code == "post_publish_integrity_error"
    assert final_identity_output.is_file()


def test_writer_retains_source_authority_through_publication_and_exit_recheck(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    in_place = tmp_path / "in-place-capsule"
    shutil.copytree(complete, in_place)
    in_place_output = tmp_path / "in-place-sidecar.json"

    def mutate_source_after_publish(point: str) -> None:
        if point == "after_parent_fsync":
            raw = in_place / "raw.jsonl"
            raw.write_bytes(raw.read_bytes() + b" ")

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            in_place,
            in_place_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=mutate_source_after_publish
            ),
        )
    assert caught.value.code == "post_publish_integrity_error"
    assert in_place_output.is_file()

    replaced = tmp_path / "replaced-capsule"
    shutil.copytree(complete, replaced)
    displaced = tmp_path / "displaced-capsule"
    replacement_output = tmp_path / "replacement-sidecar.json"

    def replace_visible_source_before_link(point: str) -> None:
        if point != "before_link_noreplace":
            return
        os.rename(replaced, displaced)
        shutil.copytree(displaced, replaced)

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            replaced,
            replacement_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=replace_visible_source_before_link
            ),
        )
    assert caught.value.code == "unstable_snapshot"
    assert not replacement_output.exists()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))


def test_writer_never_mistakes_displaced_retained_source_for_external_parent(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    displaced = tmp_path / "retained-source-now-output-parent"
    output = displaced / "must-not-publish.json"
    real_sidecar_from_source = sidecar_module._sidecar_from_source  # type: ignore[attr-defined]
    displaced_snapshot: dict[str, tuple[int, int, int, int, bytes | None]] | None = None

    def displace_after_derivation(source: object) -> ScoredCapsuleSidecarV2:
        nonlocal displaced_snapshot
        result = real_sidecar_from_source(source)
        os.rename(complete, displaced)
        shutil.copytree(displaced, complete)
        displaced_snapshot = _tree_snapshot(displaced)
        return result

    monkeypatch.setattr(sidecar_module, "_sidecar_from_source", displace_after_derivation)
    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(complete, output)

    assert caught.value.code == "invalid_argument"
    assert not output.exists()
    assert not tuple(displaced.glob(".laconian-scored.*.tmp"))
    assert displaced_snapshot is not None
    assert _tree_snapshot(displaced) == displaced_snapshot


@pytest.mark.parametrize("target_index", [1, 2])
def test_writer_and_loader_reject_sidecars_inside_any_other_capsule(
    sealed_small_capsules: tuple[Path, Path, Path],
    target_index: int,
) -> None:
    source = sealed_small_capsules[0]
    target = sealed_small_capsules[target_index]
    output = target / "must-remain-external.json"
    before = _tree_snapshot(target)

    for operation in (
        lambda: write_scored_sidecar(source, output),
        lambda: load_verified_scored_capsule(source, output),
    ):
        with pytest.raises(SidecarError) as caught:
            operation()
        assert caught.value.code == "invalid_argument"

    assert not output.exists()
    assert not tuple(target.glob(".laconian-scored.*.tmp"))
    assert _tree_snapshot(target) == before


@pytest.mark.parametrize("marker_kind", ["symlink", "fifo"])
def test_any_capsule_marker_type_makes_an_output_parent_internal(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    marker_kind: str,
) -> None:
    source = sealed_small_capsules[0]
    target = tmp_path / f"marker-{marker_kind}"
    target.mkdir()
    marker = target / "capsule.json"
    if marker_kind == "symlink":
        marker.symlink_to("missing-marker-target")
    else:
        os.mkfifo(marker, 0o600)
    output = target / "must-remain-external.json"
    before = _tree_snapshot(target)

    for operation in (
        lambda: write_scored_sidecar(source, output),
        lambda: load_verified_scored_capsule(source, output),
    ):
        with pytest.raises(SidecarError) as caught:
            operation()
        assert caught.value.code == "invalid_argument"

    assert not output.exists()
    assert not tuple(target.glob(".laconian-scored.*.tmp"))
    assert _tree_snapshot(target) == before


@pytest.mark.parametrize("target_index", [0, 1, 2])
def test_writer_and_loader_reject_a_capsule_directory_as_the_sidecar_leaf(
    sealed_small_capsules: tuple[Path, Path, Path],
    target_index: int,
) -> None:
    source = sealed_small_capsules[0]
    target = sealed_small_capsules[target_index]
    before_target = _tree_snapshot(target)
    before_parent = _tree_snapshot(target.parent)

    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(source, target)
    assert caught.value.code == "invalid_argument"

    with pytest.raises(SidecarError) as caught:
        load_verified_scored_capsule(source, target)
    assert caught.value.code in {"invalid_argument", "unsafe_path_type"}

    assert not tuple(target.parent.glob(".laconian-scored.*.tmp"))
    assert _tree_snapshot(target) == before_target
    assert _tree_snapshot(target.parent) == before_parent


def test_writer_rechecks_external_parent_ancestry_immediately_before_link(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    external_parent = tmp_path / "external-before-link"
    external_parent.mkdir()
    output = external_parent / "must-not-publish.json"
    moved_parent = complete / "adversarial-output-parent"

    def move_parent_inside_retained_source(point: str) -> None:
        if point == "before_link_noreplace":
            os.rename(external_parent, moved_parent)

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=move_parent_inside_retained_source
            ),
        )

    assert caught.value.code == "invalid_argument"
    assert not (moved_parent / output.name).exists()
    assert not tuple(moved_parent.glob(".laconian-scored.*.tmp"))


def test_external_parent_proof_is_the_last_filesystem_operation_before_link(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    external_parent = tmp_path / "late-external-parent"
    external_parent.mkdir()
    moved_parent = complete / "late-internal-parent"
    output = external_parent / "must-not-publish.json"
    real_stat = os.stat
    temporary_stats = 0

    def move_during_final_temporary_stat(
        path: os.PathLike[str] | str | int,
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        nonlocal temporary_stats
        if type(path) is str and path.startswith(".laconian-scored.") and path.endswith(".tmp"):
            temporary_stats += 1
            if temporary_stats == 4:
                os.rename(external_parent, moved_parent)
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sidecar_module.os, "stat", move_during_final_temporary_stat)
    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(complete, output)

    assert temporary_stats >= 4
    assert caught.value.code == "invalid_argument"
    assert not (moved_parent / output.name).exists()
    assert not tuple(moved_parent.glob(".laconian-scored.*.tmp"))


def test_ancestor_walk_is_the_last_operation_inside_the_prelink_parent_proof(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    external_parent = tmp_path / "parent-moved-during-proof"
    external_parent.mkdir()
    moved_parent = complete / "parent-moved-after-visible-recheck"
    output = external_parent / "must-not-publish.json"
    real_recheck = sidecar_module._recheck_visible_directory_leaf  # type: ignore[attr-defined]
    rechecks = 0

    def move_after_final_visible_recheck(*args: object, **kwargs: object) -> object:
        nonlocal rechecks
        result = real_recheck(*args, **kwargs)
        rechecks += 1
        if rechecks == 3:
            os.rename(external_parent, moved_parent)
        return result

    monkeypatch.setattr(
        sidecar_module,
        "_recheck_visible_directory_leaf",
        move_after_final_visible_recheck,
    )
    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(complete, output)

    assert rechecks >= 3
    assert caught.value.code == "invalid_argument"
    assert not (moved_parent / output.name).exists()
    assert not tuple(moved_parent.glob(".laconian-scored.*.tmp"))


def test_writer_maps_memory_exhaustion_after_link_to_published_failure(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    output = tmp_path / "published-before-memory-error.json"
    real_read = sidecar_module._read_descriptor_exact  # type: ignore[attr-defined]
    reads = 0

    def fail_first_output_read(*args: object, **kwargs: object) -> object:
        nonlocal reads
        reads += 1
        if reads == 3:
            raise MemoryError
        return real_read(*args, **kwargs)

    monkeypatch.setattr(sidecar_module, "_read_descriptor_exact", fail_first_output_read)
    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(complete, output)

    assert caught.value.code == "post_publish_integrity_error"
    assert output.is_file()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))


@pytest.mark.parametrize("attack", ["mutate", "replace-identical"])
def test_writer_rechecks_exact_published_output_after_clean_source_exit(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    output = tmp_path / f"post-source-exit-{attack}.json"
    real_source = sidecar_module.verified_sealed_capsule_source

    @contextmanager
    def attack_after_writer_body(path: Path) -> Iterator[object]:
        with real_source(path) as source:
            yield source
            original = output.read_bytes()
            if attack == "mutate":
                changed = bytearray(original)
                changed[-1] ^= 1
                output.write_bytes(changed)
            else:
                replacement = output.with_suffix(".replacement")
                replacement.write_bytes(original)
                replacement.chmod(0o600)
                os.replace(replacement, output)

    monkeypatch.setattr(
        sidecar_module,
        "verified_sealed_capsule_source",
        attack_after_writer_body,
    )
    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(complete, output)

    assert caught.value.code == "post_publish_integrity_error"
    assert output.is_file()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))


def test_writer_and_loader_attempt_each_owned_close_once(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    writer_output = tmp_path / "writer-close.json"
    writer_closed: list[int] = []

    def writer_close(descriptor: int) -> None:
        writer_closed.append(descriptor)
        os.close(descriptor)
        if len(writer_closed) == 1:
            raise OSError("CLOSE-CANARY")

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            writer_output,
            seams=sidecar_module._SidecarSeams(close=writer_close),  # type: ignore[attr-defined]
        )
    assert caught.value.code == "post_publish_close_failed"
    assert len(writer_closed) == len(set(writer_closed)) == 3
    assert writer_output.is_file()

    postguard_output = tmp_path / "postguard-close.json"
    postguard_closed: list[int] = []

    def fail_first_postguard_close(descriptor: int) -> None:
        postguard_closed.append(descriptor)
        os.close(descriptor)
        if len(postguard_closed) == 4:
            raise OSError("POSTGUARD-CLOSE-CANARY")

    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            postguard_output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                close=fail_first_postguard_close
            ),
        )
    assert caught.value.code == "post_publish_close_failed"
    assert len(postguard_closed) == 5
    assert len(set(postguard_closed[:3])) == 3
    assert len(set(postguard_closed[3:])) == 2
    assert postguard_output.is_file()

    loader_closed: list[int] = []

    def loader_close(descriptor: int) -> None:
        loader_closed.append(descriptor)
        os.close(descriptor)
        if len(loader_closed) == 1:
            raise OSError("CLOSE-CANARY")

    with pytest.raises(SidecarError) as caught:
        sidecar_module._load_verified_scored_capsule(  # type: ignore[attr-defined]
            complete,
            writer_output,
            seams=sidecar_module._SidecarSeams(close=loader_close),  # type: ignore[attr-defined]
        )
    assert caught.value.code == "io_error"
    assert len(loader_closed) == len(set(loader_closed)) == 2


def test_writer_cleans_owned_temp_when_its_first_fstat_fails(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    output = tmp_path / "first-temp-fstat.json"
    real_fstat = os.fstat
    armed = False
    failed = False
    closed: list[int] = []

    def arm_after_open(point: str) -> None:
        nonlocal armed
        if point == "after_temporary_open":
            armed = True

    def fail_once(descriptor: int) -> os.stat_result:
        nonlocal failed
        if armed and not failed:
            failed = True
            raise OSError("FIRST-FSTAT-CANARY")
        return real_fstat(descriptor)

    def track_close(descriptor: int) -> None:
        closed.append(descriptor)
        os.close(descriptor)

    monkeypatch.setattr(sidecar_module.os, "fstat", fail_once)
    with pytest.raises(SidecarError) as caught:
        sidecar_module._write_scored_sidecar(  # type: ignore[attr-defined]
            complete,
            output,
            seams=sidecar_module._SidecarSeams(  # type: ignore[attr-defined]
                checkpoint=arm_after_open,
                close=track_close,
            ),
        )

    assert failed
    assert caught.value.code == "io_error"
    assert not output.exists()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))
    assert len(closed) == len(set(closed)) == 2


def test_public_sidecar_errors_drop_private_exception_chains_and_content(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    invalid = tmp_path / "invalid-secret-sidecar.json"
    invalid.write_bytes(b'{"SECRET-CANARY-FIELD":"SECRET-CANARY-VALUE"}')

    with pytest.raises(SidecarError) as caught:
        load_verified_scored_capsule(complete, invalid)
    assert caught.value.code == "noncanonical_json"
    assert caught.value.args == ("scored capsule sidecar rejected",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "SECRET-CANARY" not in "".join(traceback.format_exception(caught.value))

    output = tmp_path / "writer-secret-error.json"

    def fail_fchmod(_descriptor: int, _mode: int) -> None:
        raise OSError("WRITER-SECRET-CANARY")

    monkeypatch.setattr(sidecar_module.os, "fchmod", fail_fchmod)
    with pytest.raises(SidecarError) as caught:
        write_scored_sidecar(complete, output)
    assert caught.value.code == "io_error"
    assert caught.value.args == ("scored capsule sidecar rejected",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "WRITER-SECRET-CANARY" not in "".join(traceback.format_exception(caught.value))
    assert not output.exists()
    assert not tuple(tmp_path.glob(".laconian-scored.*.tmp"))


@pytest.mark.parametrize("attack", ["mutate", "replace-identical"])
def test_loader_rechecks_exact_sidecar_after_its_final_external_proof(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    sidecar = tmp_path / f"loader-final-{attack}.json"
    write_scored_sidecar(complete, sidecar)
    capsule_parent_fd = open_directory_no_follow(complete.parent)
    sidecar_parent_fd = open_directory_no_follow(sidecar.parent)
    try:
        capsule_capability = _descriptor_bound_path(capsule_parent_fd) / complete.name
        sidecar_capability = _descriptor_bound_path(sidecar_parent_fd) / sidecar.name
        capability_rechecks: list[tuple[object, object]] = []
        capability_real_recheck = sidecar_module._recheck_external_parent

        def record_capability_recheck(*args: object, **kwargs: object) -> object:
            capability_rechecks.append((kwargs["capsule_path"], kwargs["parent_path"]))
            return capability_real_recheck(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(sidecar_module, "_recheck_external_parent", record_capability_recheck)
            loaded = load_verified_scored_capsule(
                capsule_capability,  # type: ignore[arg-type]
                sidecar_capability,  # type: ignore[arg-type]
            )
        assert loaded.capsule_sha256
        assert len(capability_rechecks) >= 4
        assert all(type(capsule) is type(capsule_capability) for capsule, _ in capability_rechecks)
        assert all(type(parent) is type(sidecar_capability) for _, parent in capability_rechecks)
    finally:
        os.close(sidecar_parent_fd)
        os.close(capsule_parent_fd)
    real_recheck = sidecar_module._recheck_external_parent  # type: ignore[attr-defined]
    rechecks = 0

    def attack_after_final_external_proof(*args: object, **kwargs: object) -> object:
        nonlocal rechecks
        result = real_recheck(*args, **kwargs)
        rechecks += 1
        if rechecks == 4:
            original = sidecar.read_bytes()
            if attack == "mutate":
                changed = bytearray(original)
                changed[-1] ^= 1
                sidecar.write_bytes(changed)
            else:
                replacement = sidecar.with_suffix(".replacement")
                replacement.write_bytes(original)
                replacement.chmod(0o600)
                os.replace(replacement, sidecar)
        return result

    monkeypatch.setattr(
        sidecar_module,
        "_recheck_external_parent",
        attack_after_final_external_proof,
    )
    with pytest.raises(SidecarError) as caught:
        load_verified_scored_capsule(complete, sidecar)

    assert rechecks >= 4
    assert caught.value.code == "unstable_snapshot"

def test_loader_constructs_authority_inside_source_and_scans_depth_incrementally(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    sidecar = tmp_path / "authority-sidecar.json"
    write_scored_sidecar(complete, sidecar)
    depth_source = tmp_path / "depth-source"
    shutil.copytree(complete, depth_source)
    real_verified_type = sidecar_module.VerifiedScoredCapsuleV2

    def mutate_during_construction(**kwargs: object) -> VerifiedScoredCapsuleV2:
        raw = complete / "raw.jsonl"
        raw.write_bytes(raw.read_bytes() + b" ")
        return real_verified_type(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        sidecar_module,
        "VerifiedScoredCapsuleV2",
        mutate_during_construction,
    )
    with pytest.raises(SidecarError) as caught:
        load_verified_scored_capsule(complete, sidecar)
    assert caught.value.code == "source_rejected"

    deep = tmp_path / "too-deep.json"
    deep.write_bytes(b"[" * 65 + b"]" * 65)
    with pytest.raises(SidecarError) as caught:
        load_verified_scored_capsule(depth_source, deep)
    assert caught.value.code == "resource_limit"


def test_verified_scored_capsule_cannot_be_minted_by_callers(
    sealed_small_capsules: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    complete, _blocked, _unsealed = sealed_small_capsules
    sidecar = tmp_path / "verified-authority.json"
    write_scored_sidecar(complete, sidecar)
    evidence = load_verified_scored_capsule(complete, sidecar)
    payload = {field.name: getattr(evidence, field.name) for field in fields(evidence)}

    with pytest.raises(SidecarError) as caught:
        VerifiedScoredCapsuleV2(**payload)
    assert caught.value.code == "sidecar_mismatch"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None

    scored = evidence.scored_attempts[0]
    forged = ScoredAttemptV2.model_construct(**(scored.__dict__ | {"ordinal": 99}))
    with pytest.raises(SidecarError) as caught:
        VerifiedScoredCapsuleV2(
            **(payload | {"scored_attempts": (forged, *evidence.scored_attempts[1:])}),
            _construction_authority=sidecar_module._VERIFIED_SCORED_CONSTRUCTION_AUTHORITY,  # type: ignore[attr-defined]
        )
    assert caught.value.code == "sidecar_mismatch"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
