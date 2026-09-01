from __future__ import annotations

import os
import stat
import traceback
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from capsule_helpers import UUID_B

import laconian_eval.capsule.checkpoint as checkpoint_module
import laconian_eval.capsule.verify as verify_module
from laconian_eval.capsule.canonical import sha256_bytes
from laconian_eval.capsule.checkpoint import (
    CheckpointError,
    CheckpointProvenanceV1,
    checkpoint_archive_name,
    pack_checkpoint,
)
from laconian_eval.capsule.finalize import finalize_capsule
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.sharding import ShardPlanV1
from laconian_eval.capsule.verify import verified_checkpoint_source

from .test_execution import _single_plan_capsule
from .test_prepare import _load_shard_success

_BLOCK_BYTES = 512


@pytest.fixture
def prepared_shard_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, ShardPlanV1]:
    prepared, _harness, _manifest, _parent_plan, shard = _load_shard_success(
        tmp_path,
        monkeypatch,
    )
    assert isinstance(shard, ShardPlanV1)
    assert shard.row_count == 40
    nested = prepared.path / "inputs" / "planning"
    child = nested / "shard-plan.json"
    os.chmod(nested, 0o555)
    os.chmod(child, 0o640)
    return prepared.path, shard


def _provenance(shard: ShardPlanV1) -> CheckpointProvenanceV1:
    return CheckpointProvenanceV1(
        campaign_id=shard.campaign_id,
        model_id=shard.model_id,
        scenario_uid=shard.scenario_uid,
        batch_attempt_id=UUID(UUID_B),
        run_attempt=1,
    )


def _octal(field: bytes) -> int:
    return int(field.rstrip(b"\0 ") or b"0", 8)


def _parse_raw_ustar(
    data: bytes,
) -> tuple[list[tuple[str, str, int, int, bytes]], int]:
    members: list[tuple[str, str, int, int, bytes]] = []
    offset = 0
    while data[offset : offset + _BLOCK_BYTES] != bytes(_BLOCK_BYTES):
        header = data[offset : offset + _BLOCK_BYTES]
        assert len(header) == _BLOCK_BYTES
        assert header[257:263] == b"ustar\0"
        assert header[263:265] == b"00"
        assert header[108:116] == b"0000000\0"
        assert header[116:124] == b"0000000\0"
        assert header[136:148] == b"00000000000\0"
        assert len(header[100:107]) == 7 and header[107:108] == b"\0"
        assert len(header[124:135]) == 11 and header[135:136] == b"\0"
        assert len(header[148:154]) == 6 and header[154:156] == b"\0 "
        assert header[265:329] == bytes(64)
        assert header[329:345] == bytes(16)
        assert header[500:512] == bytes(12)
        checksum_header = bytearray(header)
        checksum_header[148:156] = b"        "
        checksum = sum(checksum_header)
        assert _octal(header[148:156]) == checksum

        name = header[:100].rstrip(b"\0")
        prefix = header[345:500].rstrip(b"\0")
        encoded_path = prefix + (b"/" if prefix else b"") + name
        path = encoded_path.decode("utf-8", errors="strict")
        mode = _octal(header[100:108])
        size = _octal(header[124:136])
        assert header[100:108] == f"{mode:07o}\0".encode("ascii")
        assert header[124:136] == f"{size:011o}\0".encode("ascii")
        assert header[148:156] == f"{checksum:06o}\0 ".encode("ascii")
        typeflag = header[156:157]
        assert typeflag in {b"0", b"5"}
        if typeflag == b"5":
            assert size == 0
        offset += _BLOCK_BYTES
        payload = data[offset : offset + size]
        assert len(payload) == size
        members.append((path, typeflag.decode("ascii"), mode, size, payload))
        padded_size = (size + _BLOCK_BYTES - 1) // _BLOCK_BYTES * _BLOCK_BYTES
        assert data[offset + size : offset + padded_size] == bytes(padded_size - size)
        offset += padded_size

    assert data[offset:] == bytes(2 * _BLOCK_BYTES)
    return members, offset


def test_verified_checkpoint_source_exposes_one_locked_sorted_shard_inventory(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
) -> None:
    capsule_path, shard = prepared_shard_capsule

    with verified_checkpoint_source(capsule_path) as source:
        borrowed_root = source.root_descriptor
        assert source.result.status == "valid"
        assert source.result.state == "PREPARED"
        assert source.shard == shard
        assert source.parent_plan_record.role == "parent_plan"
        assert source.shard_plan_record.role == "shard_plan"
        assert source.inventory == tuple(
            sorted(source.inventory, key=lambda item: item[0].encode("utf-8"))
        )
        assert (".laconian.lock", "file", 0o600, 0) in source.inventory
        assert stat.S_ISDIR(os.fstat(borrowed_root).st_mode)

    with pytest.raises(OSError):
        os.fstat(borrowed_root)


def test_pack_checkpoint_writes_deterministic_uncompressed_ustar_and_sidecar(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    output_a = tmp_path / "checkpoint-a"
    output_b = tmp_path / "checkpoint-b"
    output_a.mkdir()
    output_b.mkdir()
    archive_name = checkpoint_archive_name(provenance)
    archive_path = output_a / archive_name
    second_archive = output_b / archive_name

    artifact = pack_checkpoint(
        capsule_path,
        archive_path,
        provenance=provenance,
    )
    second = pack_checkpoint(
        capsule_path,
        second_archive,
        provenance=provenance,
    )

    archive_bytes = archive_path.read_bytes()
    assert archive_path.suffix == ".tar"
    assert artifact.archive_path == archive_path
    assert artifact.sidecar_path == Path(f"{archive_path}.sha256")
    assert artifact.sha256 == sha256_bytes(archive_bytes)
    assert artifact.byte_length == archive_path.stat().st_size
    assert artifact.member_count > 0
    assert artifact.sidecar_path.read_bytes() == (
        f"{artifact.sha256}  {archive_path.name}\n".encode("ascii")
    )
    assert second.sha256 == artifact.sha256
    assert second_archive.read_bytes() == archive_bytes

    members, _terminal_offset = _parse_raw_ustar(archive_bytes)
    paths = [member[0] for member in members]
    assert paths == sorted(paths, key=lambda value: value.encode("utf-8"))
    assert paths.index("inputs/planning") < paths.index("inputs/planning/shard-plan.json")
    assert ".laconian.lock" in paths
    assert artifact.member_count == len(members)
    with verified_checkpoint_source(capsule_path) as source:
        assert paths == [record[0] for record in source.inventory]
    by_path = {path: (kind, mode, size) for path, kind, mode, size, _payload in members}
    assert by_path["inputs/planning"] == ("5", 0o555, 0)
    assert by_path["inputs/planning/shard-plan.json"][0:2] == ("0", 0o640)
    for path, typeflag, mode, size, payload in members:
        source = capsule_path / path
        metadata = source.lstat()
        assert mode == stat.S_IMODE(metadata.st_mode)
        assert size == (metadata.st_size if typeflag == "0" else 0)
        assert payload == (source.read_bytes() if typeflag == "0" else b"")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("campaign_id", "wrong-campaign"),
        ("model_id", "gpt-5.6-terra"),
        ("scenario_uid", "f" * 64),
    ],
)
def test_pack_checkpoint_rejects_wrong_shard_provenance_before_output(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard).model_copy(update={field: value})
    archive = tmp_path / checkpoint_archive_name(provenance)

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "binding_mismatch"
    assert str(caught.value) == "capsule checkpoint rejected"
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


def test_pack_checkpoint_rejects_a_full_parent_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "full-parent-source"
    source_root.mkdir()
    capsule_path = _single_plan_capsule(source_root, monkeypatch)
    (tmp_path / "shard-authority").mkdir()
    _prepared, _harness, _manifest, _parent_plan, shard = _load_shard_success(
        tmp_path / "shard-authority",
        monkeypatch,
    )
    assert isinstance(shard, ShardPlanV1)
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "source_rejected"
    assert not archive.exists()


@pytest.mark.parametrize("mutation", ["append", "replace", "short_read", "lock_loss"])
def test_pack_checkpoint_rejects_source_mutation_after_member_header(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    mutation: str,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    target = capsule_path / "manifest.json"
    original = target.read_bytes()
    fired = False

    def mutate(point: str) -> None:
        nonlocal fired
        if fired or point != "after_header:manifest.json":
            return
        fired = True
        if mutation == "append":
            with target.open("ab") as stream:
                stream.write(b"x")
        elif mutation == "replace":
            target.rename(capsule_path / "displaced-manifest.json")
            target.write_bytes(original)
        elif mutation == "short_read":
            target.write_bytes(b"")
        else:
            (capsule_path / ".laconian.lock").unlink()

    seams = checkpoint_module._CheckpointSeams(checkpoint=mutate)
    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=seams,
        )

    assert fired
    assert caught.value.code == "unstable_snapshot"
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("checkpoint_archive_bytes", 1024),
        ("checkpoint_members", 1),
        ("checkpoint_directories", 1),
        ("checkpoint_file_bytes", 1),
        ("checkpoint_aggregate_file_bytes", 1),
        ("checkpoint_path_depth", 1),
    ],
)
def test_pack_checkpoint_preflights_every_restore_size_and_count_bound(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: int,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    limits = replace(RESOURCE_LIMITS_V1, **{field: value})
    monkeypatch.setattr(verify_module, "RESOURCE_LIMITS_V1", limits)
    monkeypatch.setattr(checkpoint_module, "RESOURCE_LIMITS_V1", limits)

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "resource_limit"
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


@pytest.mark.parametrize(
    "field",
    [
        "checkpoint_members",
        "checkpoint_directories",
        "checkpoint_file_bytes",
        "checkpoint_aggregate_file_bytes",
        "checkpoint_path_depth",
        "checkpoint_archive_bytes",
    ],
)
def test_checkpoint_bounds_accept_exact_metric_and_reject_one_less(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    with verified_checkpoint_source(capsule_path) as source:
        files = [record for record in source.inventory if record[1] == "file"]
        projected_archive = 2 * _BLOCK_BYTES + sum(
            _BLOCK_BYTES + ((record[3] + _BLOCK_BYTES - 1) // _BLOCK_BYTES) * _BLOCK_BYTES
            for record in source.inventory
        )
        exact_by_field = {
            "checkpoint_members": len(source.inventory),
            "checkpoint_directories": sum(record[1] == "directory" for record in source.inventory),
            "checkpoint_file_bytes": max(record[3] for record in files),
            "checkpoint_aggregate_file_bytes": sum(record[3] for record in files),
            "checkpoint_path_depth": max(len(record[0].split("/")) for record in source.inventory),
            "checkpoint_archive_bytes": projected_archive,
        }
    exact = exact_by_field[field]
    assert exact > 0

    exact_limits = replace(RESOURCE_LIMITS_V1, **{field: exact})
    monkeypatch.setattr(verify_module, "RESOURCE_LIMITS_V1", exact_limits)
    monkeypatch.setattr(checkpoint_module, "RESOURCE_LIMITS_V1", exact_limits)
    exact_parent = tmp_path / f"exact-{field}"
    exact_parent.mkdir()
    artifact = pack_checkpoint(
        capsule_path,
        exact_parent / checkpoint_archive_name(provenance),
        provenance=provenance,
    )
    assert artifact.archive_path.exists()

    below_limits = replace(RESOURCE_LIMITS_V1, **{field: exact - 1})
    monkeypatch.setattr(verify_module, "RESOURCE_LIMITS_V1", below_limits)
    monkeypatch.setattr(checkpoint_module, "RESOURCE_LIMITS_V1", below_limits)
    below_parent = tmp_path / f"below-{field}"
    below_parent.mkdir()
    below_archive = below_parent / checkpoint_archive_name(provenance)
    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, below_archive, provenance=provenance)
    assert caught.value.code == "resource_limit"
    assert not below_archive.exists()


def test_ustar_path_split_is_multibyte_safe_and_size_field_fails_closed() -> None:
    alpha = "\u03b1"
    beta = "\u03b2"
    path = f"{alpha * 70}/{beta * 45}"
    prefix, name = checkpoint_module._ustar_path(path)
    assert len(prefix) == 140
    assert len(name) == 90
    assert prefix + b"/" + name == path.encode("utf-8")

    with pytest.raises(CheckpointError) as path_error:
        checkpoint_module._ustar_path(f"{'a' * 156}/{'b' * 100}")
    assert path_error.value.code == "source_rejected"

    with pytest.raises(CheckpointError) as size_error:
        checkpoint_module._ustar_header("large.bin", "file", 0o600, 8 * 1024**3)
    assert size_error.value.code == "source_rejected"


@pytest.mark.parametrize("hostile_kind", ["symlink", "fifo", "hardlink"])
def test_pack_checkpoint_rejects_special_or_aliased_source_files(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    hostile_kind: str,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    target = capsule_path / "raw.jsonl"
    if hostile_kind == "hardlink":
        os.link(target, tmp_path / "outside-hardlink")
    else:
        target.unlink()
        if hostile_kind == "symlink":
            target.symlink_to("manifest.json")
        else:
            os.mkfifo(target)

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code in {"unsafe_path_type", "unstable_snapshot"}
    assert not archive.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


def test_pack_checkpoint_never_overwrites_archive_or_sidecar_collisions(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    sidecar = Path(f"{archive}.sha256")
    sidecar.write_bytes(b"keep-sidecar")
    os.chmod(sidecar, 0o600)
    opened_sidecar_descriptors: list[int] = []
    real_open = checkpoint_module.os.open

    def track_open(path: object, *args: object, **kwargs: object) -> int:
        descriptor = real_open(path, *args, **kwargs)  # type: ignore[arg-type]
        if path == sidecar.name and kwargs.get("dir_fd") is not None:
            opened_sidecar_descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(checkpoint_module.os, "open", track_open)
    with pytest.raises(CheckpointError) as sidecar_error:
        pack_checkpoint(capsule_path, archive, provenance=provenance)
    assert sidecar_error.value.code == "destination_collision"
    assert sidecar.read_bytes() == b"keep-sidecar"
    assert not archive.exists()
    assert opened_sidecar_descriptors
    for descriptor in opened_sidecar_descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)

    sidecar.unlink()
    archive.write_bytes(b"keep-archive")
    os.chmod(archive, 0o600)
    with pytest.raises(CheckpointError) as archive_error:
        pack_checkpoint(capsule_path, archive, provenance=provenance)
    assert archive_error.value.code == "destination_collision"
    assert archive.read_bytes() == b"keep-archive"
    assert not sidecar.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


def test_pack_checkpoint_retries_only_an_exact_archive_after_sidecar_failure(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def fail_sidecar_link(
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        if target_name.endswith(".sha256"):
            raise OSError("sidecar publish canary")
        PosixOps().link_noreplace(
            source_directory_fd,
            source_name,
            target_directory_fd,
            target_name,
        )

    with pytest.raises(CheckpointError) as first:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=fail_sidecar_link),
        )
    assert first.value.code == "checkpoint_sidecar_publish_failed"
    original_archive = archive.read_bytes()
    original_inode = archive.stat().st_ino
    assert not Path(f"{archive}.sha256").exists()

    artifact = pack_checkpoint(capsule_path, archive, provenance=provenance)
    assert archive.read_bytes() == original_archive
    assert archive.stat().st_ino == original_inode
    assert artifact.sha256 == sha256_bytes(original_archive)
    assert artifact.sidecar_path.exists()


def test_pack_checkpoint_rejects_changed_output_parent_before_publication(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    output_parent = tmp_path / "moving-output"
    output_parent.mkdir()
    archive = output_parent / checkpoint_archive_name(provenance)
    fired = False

    def replace_parent(point: str) -> None:
        nonlocal fired
        if fired or point != "before_archive_parent_proof":
            return
        fired = True
        output_parent.rename(tmp_path / "displaced-output")
        output_parent.mkdir()

    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(checkpoint=replace_parent),
        )
    assert fired
    assert caught.value.code == "unstable_snapshot"
    assert not archive.exists()
    assert not tuple((tmp_path / "displaced-output").glob(".laconian-checkpoint.*.tmp"))


def test_pack_checkpoint_rejects_output_inside_a_capsule(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = capsule_path / "inputs" / checkpoint_archive_name(provenance)

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "invalid_argument"
    assert not archive.exists()


def test_public_checkpoint_errors_drop_private_exception_chains_and_content(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    canary = "private-checkpoint-canary"
    invalid = tmp_path / f"{canary}.tar"

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, invalid, provenance=provenance)

    error = caught.value
    assert error.args == ("capsule checkpoint rejected",)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert canary not in str(error)
    assert canary not in "".join(traceback.format_exception_only(type(error), error))


@pytest.mark.parametrize(
    ("failure_call", "expected_code"),
    [
        (1, "io_error"),
        (2, "post_publish_integrity_error"),
        (3, "checkpoint_sidecar_publish_failed"),
        (4, "post_publish_integrity_error"),
    ],
)
def test_pack_checkpoint_classifies_each_fsync_publication_phase_and_cleans_temps(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    failure_call: int,
    expected_code: str,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    calls = 0

    def fail_selected_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("private fsync canary")
        os.fsync(descriptor)

    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(fsync=fail_selected_fsync),
        )

    assert caught.value.code == expected_code
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))
    sidecar = Path(f"{archive}.sha256")
    assert archive.exists() is (failure_call == 3)
    assert not sidecar.exists()


def test_pack_checkpoint_cleans_an_owned_temp_when_initialization_fails(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def fail_fchmod(_descriptor: int, _mode: int) -> None:
        raise OSError("private fchmod canary")

    monkeypatch.setattr(checkpoint_module.os, "fchmod", fail_fchmod)
    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "io_error"
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))
    assert caught.value.args == ("capsule checkpoint rejected",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_temp_initialization_never_unlinks_an_attacker_replacement(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    canary = b"attacker replacement canary"
    replaced: Path | None = None

    def replace_then_fail(_descriptor: int, _mode: int) -> None:
        nonlocal replaced
        temporary = next(tmp_path.glob(".laconian-checkpoint.*.tmp"))
        temporary.rename(tmp_path / "displaced-owned-temp")
        temporary.write_bytes(canary)
        replaced = temporary
        raise OSError("private fchmod canary")

    monkeypatch.setattr(checkpoint_module.os, "fchmod", replace_then_fail)
    with pytest.raises(CheckpointError):
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert replaced is not None
    assert replaced.read_bytes() == canary


def test_open_output_parent_closes_descriptor_on_post_open_failure(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, _shard = prepared_shard_capsule
    opened: list[int] = []
    real_open_parent = checkpoint_module.open_directory_no_follow

    def track_open(path: Path) -> int:
        descriptor = real_open_parent(path)
        opened.append(descriptor)
        return descriptor

    def fail_classification(_descriptor: int, **_kwargs: object) -> None:
        raise checkpoint_module.UnsupportedFilesystemError("private canary")

    monkeypatch.setattr(checkpoint_module, "open_directory_no_follow", track_open)
    monkeypatch.setattr(checkpoint_module, "classify_filesystem", fail_classification)
    with (
        verified_checkpoint_source(capsule_path) as source,
        pytest.raises(CheckpointError) as caught,
    ):
        checkpoint_module._open_output_parent(tmp_path, source)

    assert caught.value.code == "unsupported_filesystem"
    assert opened
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_pack_checkpoint_rechecks_outputs_after_the_source_boundary_exits(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    real_boundary = checkpoint_module.verified_checkpoint_source

    @contextmanager
    def mutate_after_source_exit(path: Path):
        with real_boundary(path) as source:
            yield source
        archive.write_bytes(b"post-source replacement")

    monkeypatch.setattr(
        checkpoint_module,
        "verified_checkpoint_source",
        mutate_after_source_exit,
    )
    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "post_publish_integrity_error"


def test_source_exit_failure_rolls_back_operation_owned_outputs(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    real_boundary = checkpoint_module.verified_checkpoint_source

    @contextmanager
    def fail_after_source_exit(path: Path):
        with real_boundary(path) as source:
            yield source
        raise verify_module._Failure("unstable_snapshot", None)

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", fail_after_source_exit)
    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "post_publish_integrity_error"
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


def test_pack_checkpoint_preserves_fatal_exit_and_cleans_owned_temp(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def fatal_write(_descriptor: int, _data: bytes) -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(write=fatal_write),
        )

    assert not archive.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


def test_pack_checkpoint_requires_the_local_lock_for_a_sealed_shard_source(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    assert finalize_capsule(capsule_path, seal_incomplete=True).state == "SEALED_BLOCKED"
    (capsule_path / ".laconian.lock").unlink()

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "source_rejected"
    assert not archive.exists()


def test_checkpoint_archive_name_sanitizes_constructed_invalid_provenance() -> None:
    invalid = CheckpointProvenanceV1.model_construct(
        campaign_id="canary campaign",
        model_id="private/model/canary",
        scenario_uid="bad",
        batch_attempt_id="bad",
        run_attempt=0,
    )

    with pytest.raises(CheckpointError) as caught:
        checkpoint_archive_name(invalid)

    assert caught.value.code == "invalid_argument"
    assert caught.value.args == ("capsule checkpoint rejected",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("scenario_uid", "bad"), ("run_attempt", 0), ("batch_attempt_id", "bad")],
)
def test_pack_revalidates_class_bound_corrupted_provenance_before_source_or_output(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    payload = _provenance(shard).model_dump(mode="python", round_trip=True)
    payload[field] = value
    invalid = CheckpointProvenanceV1.model_construct(**payload)
    entered = False

    @contextmanager
    def forbidden_source(_path: Path):
        nonlocal entered
        entered = True
        raise AssertionError("source boundary entered")
        yield  # pragma: no cover

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", forbidden_source)
    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, tmp_path / "invalid.tar", provenance=invalid)

    assert caught.value.code == "invalid_argument"
    assert not entered
    assert not (tmp_path / "invalid.tar").exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


def test_pack_checkpoint_retries_a_one_shot_interrupted_write(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    interrupted = False

    def write_once_interrupted(descriptor: int, data: bytes) -> int:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise InterruptedError
        return os.write(descriptor, data)

    artifact = checkpoint_module._pack_checkpoint(
        capsule_path,
        archive,
        provenance=provenance,
        seams=checkpoint_module._CheckpointSeams(write=write_once_interrupted),
    )

    assert interrupted
    assert artifact.sha256 == sha256_bytes(archive.read_bytes())


def test_pack_checkpoint_rolls_back_fresh_archive_if_parent_moves_inside_capsule(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    archive_name = checkpoint_archive_name(provenance)
    archive = output_parent / archive_name
    moved_parent = capsule_path / "moved-output"
    fired = False

    def move_before_link(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal fired
        if not fired:
            fired = True
            output_parent.rename(moved_parent)
            output_parent.mkdir()
        PosixOps().link_noreplace(source_fd, source, target_fd, target)

    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=move_before_link),
        )

    assert fired
    assert caught.value.code == "post_publish_integrity_error"
    assert not (moved_parent / archive_name).exists()
    assert not archive.exists()


def test_exact_retry_stops_before_sidecar_when_temp_close_is_fatal(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    test_pack_checkpoint_retries_only_an_exact_archive_after_sidecar_failure(
        prepared_shard_capsule,
        tmp_path,
    )
    Path(f"{archive}.sha256").unlink()
    inode = archive.stat().st_ino

    def fatal_close(_descriptor: int) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(close=fatal_close),
        )

    assert archive.stat().st_ino == inode
    assert not Path(f"{archive}.sha256").exists()


def test_source_exit_failure_preserves_a_preexisting_exact_retry_archive(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def fail_sidecar_link(source_fd: int, source: str, target_fd: int, target: str) -> None:
        if target.endswith(".sha256"):
            raise OSError("sidecar canary")
        PosixOps().link_noreplace(source_fd, source, target_fd, target)

    with pytest.raises(CheckpointError):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=fail_sidecar_link),
        )
    inode = archive.stat().st_ino
    payload = archive.read_bytes()
    real_boundary = checkpoint_module.verified_checkpoint_source

    @contextmanager
    def fail_after_source_exit(path: Path):
        with real_boundary(path) as source:
            yield source
        raise verify_module._Failure("unstable_snapshot", None)

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", fail_after_source_exit)
    with pytest.raises(CheckpointError):
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert archive.stat().st_ino == inode
    assert archive.read_bytes() == payload
    assert not Path(f"{archive}.sha256").exists()


def test_open_existing_regular_closes_descriptor_when_fstat_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaf = tmp_path / "existing.tar"
    leaf.write_bytes(b"x")
    os.chmod(leaf, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    tracked: list[int] = []
    real_open = checkpoint_module.os.open
    real_fstat = checkpoint_module.os.fstat

    def track_open(path: object, *args: object, **kwargs: object) -> int:
        descriptor = real_open(path, *args, **kwargs)  # type: ignore[arg-type]
        if path == leaf.name:
            tracked.append(descriptor)
        return descriptor

    def fail_tracked_fstat(descriptor: int) -> os.stat_result:
        if descriptor in tracked:
            raise OSError("private fstat canary")
        return real_fstat(descriptor)

    monkeypatch.setattr(checkpoint_module.os, "open", track_open)
    monkeypatch.setattr(checkpoint_module.os, "fstat", fail_tracked_fstat)
    try:
        with pytest.raises(CheckpointError):
            checkpoint_module._open_existing_regular(parent_fd, leaf.name)
    finally:
        os.close(parent_fd)

    assert tracked
    for descriptor in tracked:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_parent_moved_inside_capsule_during_archive_parent_fsync_rolls_back(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    output = tmp_path / "fsync-output"
    output.mkdir()
    moved = capsule_path / "moved-on-fsync"
    archive_name = checkpoint_archive_name(provenance)
    calls = 0

    def move_on_second_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            output.rename(moved)
            output.mkdir()
        os.fsync(descriptor)

    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            output / archive_name,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(fsync=move_on_second_fsync),
        )

    assert caught.value.code == "post_publish_integrity_error"
    assert not (moved / archive_name).exists()
    assert not (moved / f"{archive_name}.sha256").exists()


@pytest.mark.parametrize("fatal", [False, True])
def test_real_link_then_exception_is_adopted_and_rolled_back(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def link_then_raise(source_fd: int, source: str, target_fd: int, target: str) -> None:
        PosixOps().link_noreplace(source_fd, source, target_fd, target)
        if fatal:
            raise KeyboardInterrupt
        raise OSError("ambiguous link canary")

    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=link_then_raise),
        )

    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


def test_real_link_then_file_exists_is_adopted_and_rolled_back(
    prepared_shard_capsule: tuple[Path, ShardPlanV1], tmp_path: Path
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def link_then_file_exists(source_fd: int, source: str, target_fd: int, target: str) -> None:
        PosixOps().link_noreplace(source_fd, source, target_fd, target)
        raise FileExistsError("ambiguous link collision")

    with pytest.raises(CheckpointError):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=link_then_file_exists),
        )

    assert not archive.exists()


def test_initial_temp_fstat_one_shot_failure_cleans_owned_temp(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capsule_path, _shard = prepared_shard_capsule
    real_open = checkpoint_module.os.open
    real_fstat = checkpoint_module.os.fstat
    temp_fd: int | None = None
    failed = False

    def track_open(path: object, *args: object, **kwargs: object) -> int:
        nonlocal temp_fd
        descriptor = real_open(path, *args, **kwargs)  # type: ignore[arg-type]
        if isinstance(path, str) and path.startswith(".laconian-checkpoint.archive."):
            temp_fd = descriptor
        return descriptor

    def fail_once(descriptor: int) -> os.stat_result:
        nonlocal failed
        if descriptor == temp_fd and not failed:
            failed = True
            raise OSError("initial fstat canary")
        return real_fstat(descriptor)

    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(checkpoint_module.os, "open", track_open)
        monkeypatch.setattr(checkpoint_module.os, "fstat", fail_once)
        with pytest.raises(CheckpointError) as caught:
            checkpoint_module._create_temporary(
                parent_fd, role="archive", seams=checkpoint_module._CheckpointSeams()
            )
        assert caught.value.code == "io_error"
        assert failed
        assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))
    finally:
        os.close(parent_fd)


def test_first_post_open_temp_path_stat_failure_cleans_and_closes(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capsule_path, _shard = prepared_shard_capsule
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_stat = checkpoint_module.os.stat
    closed: list[int] = []
    failed = False

    def fail_first(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal failed
        if (
            not failed
            and isinstance(path, str)
            and path.startswith(".laconian-checkpoint.archive.")
        ):
            failed = True
            raise OSError("visible temp stat canary")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    def tracked_close(descriptor: int) -> None:
        closed.append(descriptor)
        os.close(descriptor)

    try:
        monkeypatch.setattr(checkpoint_module.os, "stat", fail_first)
        with pytest.raises(CheckpointError) as caught:
            checkpoint_module._create_temporary(
                parent_fd,
                role="archive",
                seams=checkpoint_module._CheckpointSeams(close=tracked_close),
            )
        assert caught.value.code == "io_error"
        assert failed and len(closed) == 1
        with pytest.raises(OSError):
            os.fstat(closed[0])
        assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))
    finally:
        os.close(parent_fd)


def test_ambiguous_temp_close_never_retries_a_reused_descriptor(
    prepared_shard_capsule: tuple[Path, ShardPlanV1], tmp_path: Path
) -> None:
    _capsule_path, _shard = prepared_shard_capsule
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    canary = tmp_path / "canary"
    canary.write_bytes(b"canary")
    reused: int | None = None
    close_calls = 0

    def close_reuse_then_raise(descriptor: int) -> None:
        nonlocal close_calls, reused
        close_calls += 1
        if close_calls != 1:
            raise AssertionError("ambiguous descriptor close was retried")
        os.close(descriptor)
        reused = os.open(canary, os.O_RDONLY)
        assert reused == descriptor
        raise OSError("ambiguous close canary")

    try:
        temporary = checkpoint_module._create_temporary(
            parent_fd, role="archive", seams=checkpoint_module._CheckpointSeams()
        )
        seams = checkpoint_module._CheckpointSeams(close=close_reuse_then_raise)
        primary = checkpoint_module._cleanup_temporary(temporary, seams, None)
        assert isinstance(primary, CheckpointError)
        checkpoint_module._cleanup_temporary(temporary, seams, primary)
        assert reused is not None
        assert os.fstat(reused).st_size == len(b"canary")
        assert close_calls == 1
    finally:
        if reused is not None:
            os.close(reused)
        os.close(parent_fd)


def test_close_owned_preserves_first_fatal_and_closes_later_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = os.open(tmp_path / "first", os.O_RDWR | os.O_CREAT, 0o600)
    second = os.open(tmp_path / "second", os.O_RDWR | os.O_CREAT, 0o600)
    real_close = verify_module.os.close
    calls = 0
    first_fatal = KeyboardInterrupt("first fatal")

    def fatal_after_close(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        real_close(descriptor)
        if calls == 1:
            raise first_fatal
        raise SystemExit("later fatal")

    monkeypatch.setattr(verify_module.os, "close", fatal_after_close)
    primary = verify_module._close_owned(first, path="first")
    primary = verify_module._close_owned(second, path="second", primary=primary)
    assert primary is first_fatal
    assert calls == 2
    with pytest.raises(OSError):
        os.fstat(first)
    with pytest.raises(OSError):
        os.fstat(second)


def test_fatal_source_exit_after_both_links_rolls_back_fresh_outputs(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    real_boundary = checkpoint_module.verified_checkpoint_source

    @contextmanager
    def fatal_after_exit(path: Path):
        with real_boundary(path) as source:
            yield source
        raise KeyboardInterrupt

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", fatal_after_exit)
    with pytest.raises(KeyboardInterrupt):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(),
        )

    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


def test_parent_move_after_clean_source_exit_rolls_back_through_retained_fd(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    output = tmp_path / "final-output"
    output.mkdir()
    moved = capsule_path / "moved-before-final"
    archive_name = checkpoint_archive_name(provenance)

    def move_before_final(point: str) -> None:
        if point == "before_final_output_proof":
            output.rename(moved)
            output.mkdir()

    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            output / archive_name,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(checkpoint=move_before_final),
        )

    assert caught.value.code == "post_publish_integrity_error"
    assert not (moved / archive_name).exists()
    assert not (moved / f"{archive_name}.sha256").exists()


def test_source_mutation_after_fresh_archive_link_rolls_back_archive(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    target = capsule_path / "manifest.json"

    def mutate(point: str) -> None:
        if point == "after_archive_link":
            target.write_bytes(b"mutated after archive link")

    with pytest.raises(CheckpointError):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(checkpoint=mutate),
        )

    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


@pytest.mark.parametrize("fatal", [False, True])
def test_failure_before_sidecar_creation_uses_initialized_state_and_rolls_back(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def fail(point: str) -> None:
        if point == "after_archive_link":
            if fatal:
                raise KeyboardInterrupt
            raise OSError("pre-sidecar canary")

    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(checkpoint=fail),
        )

    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


def test_fatal_source_exit_preserves_preexisting_exact_archive_and_removes_sidecar(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def fail_sidecar(source_fd: int, source: str, target_fd: int, target: str) -> None:
        if target.endswith(".sha256"):
            raise OSError("sidecar canary")
        PosixOps().link_noreplace(source_fd, source, target_fd, target)

    with pytest.raises(CheckpointError):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=fail_sidecar),
        )
    inode = archive.stat().st_ino
    payload = archive.read_bytes()
    real_boundary = checkpoint_module.verified_checkpoint_source

    @contextmanager
    def fatal_after_exit(path: Path):
        with real_boundary(path) as source:
            yield source
        raise KeyboardInterrupt

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", fatal_after_exit)
    with pytest.raises(KeyboardInterrupt):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(),
        )

    assert archive.stat().st_ino == inode
    assert archive.read_bytes() == payload
    assert not Path(f"{archive}.sha256").exists()


@pytest.mark.parametrize("fatal", [False, True])
def test_rollback_fsync_promotes_ordinary_but_never_fatal_primary(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    real_boundary = checkpoint_module.verified_checkpoint_source
    calls = 0
    rollback_fsync_fired = False

    @contextmanager
    def fail_after_exit(path: Path):
        with real_boundary(path) as source:
            yield source
        if fatal:
            raise KeyboardInterrupt
        raise verify_module._Failure("unstable_snapshot", None)

    def fail_rollback_fsync(descriptor: int) -> None:
        nonlocal calls, rollback_fsync_fired
        calls += 1
        if calls == 5:
            rollback_fsync_fired = True
            raise OSError("rollback fsync canary")
        os.fsync(descriptor)

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", fail_after_exit)
    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(fsync=fail_rollback_fsync),
        )
    if not fatal:
        assert isinstance(caught.value, CheckpointError)
        assert caught.value.code == "post_publish_integrity_error"
    assert rollback_fsync_fired
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


def test_rollback_quarantine_identity_mismatch_preserves_replacement_and_promotes(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    sidecar = Path(f"{archive}.sha256")
    canary = b"rollback attacker replacement"
    real_boundary = checkpoint_module.verified_checkpoint_source

    @contextmanager
    def fail_after_exit(path: Path):
        with real_boundary(path) as source:
            yield source
        raise verify_module._Failure("unstable_snapshot", None)

    def replace_quarantine(point: str) -> None:
        if point != f"before_quarantine_delete:{sidecar.name}":
            return
        quarantine = next(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
        quarantine.rename(tmp_path / "displaced-owned-sidecar")
        quarantine.write_bytes(canary)

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", fail_after_exit)
    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(checkpoint=replace_quarantine),
        )

    assert caught.value.code == "post_publish_integrity_error"
    assert sidecar.read_bytes() == canary


def test_sidecar_collision_descriptor_is_unified_and_closed_when_close_reports_error(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    sidecar = Path(f"{archive}.sha256")
    sidecar.write_bytes(b"collision")
    os.chmod(sidecar, 0o600)
    closed: list[int] = []

    def close_then_report(descriptor: int) -> None:
        os.close(descriptor)
        closed.append(descriptor)
        raise OSError("close canary")

    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(close=close_then_report),
        )

    assert caught.value.code == "destination_collision"
    assert len(closed) >= 2
    for descriptor in closed:
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.parametrize("preexisting", [False, True])
@pytest.mark.parametrize("fatal", [False, True])
def test_sidecar_real_link_then_exception_is_adopted_and_rolled_back(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    preexisting: bool,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    if preexisting:

        def fail_sidecar(source_fd: int, source: str, target_fd: int, target: str) -> None:
            if target.endswith(".sha256"):
                raise OSError("seed sidecar failure")
            PosixOps().link_noreplace(source_fd, source, target_fd, target)

        with pytest.raises(CheckpointError):
            checkpoint_module._pack_checkpoint(
                capsule_path,
                archive,
                provenance=provenance,
                seams=checkpoint_module._CheckpointSeams(link_noreplace=fail_sidecar),
            )
        inode = archive.stat().st_ino
        payload = archive.read_bytes()
    else:
        inode = None
        payload = None

    def sidecar_link_then_raise(source_fd: int, source: str, target_fd: int, target: str) -> None:
        PosixOps().link_noreplace(source_fd, source, target_fd, target)
        if target.endswith(".sha256"):
            if fatal:
                raise KeyboardInterrupt
            raise OSError("ambiguous sidecar link")

    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=sidecar_link_then_raise),
        )

    assert not Path(f"{archive}.sha256").exists()
    if preexisting:
        assert archive.stat().st_ino == inode
        assert archive.read_bytes() == payload
    else:
        assert not archive.exists()


@pytest.mark.parametrize("fatal", [False, True])
def test_published_quarantine_rename_then_exception_is_adopted_and_cleaned(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def mutate(point: str) -> None:
        if point == "after_archive_link":
            (capsule_path / "manifest.json").write_bytes(b"mutation")

    def rename_then_raise(source_fd: int, source: str, target_fd: int, target: str) -> None:
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)
        if source == archive.name:
            if fatal:
                raise KeyboardInterrupt
            raise OSError("ambiguous quarantine rename")

    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(
                checkpoint=mutate,
                rename_noreplace=rename_then_raise,
            ),
        )

    assert not archive.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))


def test_published_quarantine_rename_then_file_not_found_is_adopted_and_cleaned(
    prepared_shard_capsule: tuple[Path, ShardPlanV1], tmp_path: Path
) -> None:
    capsule_path, shard = prepared_shard_capsule
    archive = tmp_path / checkpoint_archive_name(_provenance(shard))

    def inject(point: str) -> None:
        if point == "after_archive_link":
            (capsule_path / "manifest.json").write_bytes(b"mutation")

    def rename_then_missing(source_fd: int, source: str, target_fd: int, target: str) -> None:
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)
        if source == archive.name:
            raise FileNotFoundError("ambiguous rename")

    with pytest.raises(CheckpointError):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=_provenance(shard),
            seams=checkpoint_module._CheckpointSeams(
                checkpoint=inject, rename_noreplace=rename_then_missing
            ),
        )

    assert not archive.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))


def test_first_quarantine_unlink_fatal_is_preserved_after_successful_retry(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capsule_path, _shard = prepared_shard_capsule
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned")
    os.chmod(leaf, 0o600)
    real_unlink = checkpoint_module.os.unlink
    failed = False

    def fatal_once(path: object, *args: object, **kwargs: object) -> None:
        nonlocal failed
        if not failed and isinstance(path, str) and "quarantine" in path:
            failed = True
            raise KeyboardInterrupt
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        expected = checkpoint_module._identity(os.stat(leaf, follow_symlinks=False))
        monkeypatch.setattr(checkpoint_module.os, "unlink", fatal_once)
        primary, removed = checkpoint_module._quarantine_remove(
            parent_fd,
            leaf.name,
            expected,
            checkpoint_module._CheckpointSeams(),
            None,
            published=False,
        )
        assert isinstance(primary, KeyboardInterrupt)
        assert removed
        assert failed
        assert not leaf.exists()
        assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    finally:
        os.close(parent_fd)


def test_two_quarantine_unlink_failures_never_report_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned")
    os.chmod(leaf, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    expected = checkpoint_module._identity(os.stat(leaf, follow_symlinks=False))

    def fail_unlink(_path: object, *args: object, **kwargs: object) -> None:
        raise OSError("unlink canary")

    try:
        monkeypatch.setattr(checkpoint_module.os, "unlink", fail_unlink)
        primary, removed = checkpoint_module._quarantine_remove(
            parent_fd,
            leaf.name,
            expected,
            checkpoint_module._CheckpointSeams(),
            None,
            published=False,
        )
        assert isinstance(primary, CheckpointError)
        assert not removed
        assert tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    finally:
        os.close(parent_fd)


def test_temporary_cleanup_retains_quarantine_location_for_later_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    temporary = checkpoint_module._create_temporary(
        parent_fd, role="archive", seams=checkpoint_module._CheckpointSeams()
    )
    real_unlink = checkpoint_module.os.unlink
    calls = 0

    def fail_twice(path: object, *args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise PermissionError("persistent unlink canary")
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(checkpoint_module.os, "unlink", fail_twice)
    first = checkpoint_module._cleanup_temporary(
        temporary, checkpoint_module._CheckpointSeams(), None
    )
    assert isinstance(first, CheckpointError)
    assert not temporary.removed
    assert "quarantine" in temporary.name
    second = checkpoint_module._cleanup_temporary(
        temporary, checkpoint_module._CheckpointSeams(), first
    )
    assert isinstance(second, CheckpointError)
    assert temporary.removed
    assert calls == 3
    assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    os.close(parent_fd)


def test_restored_identity_mismatch_tracks_original_across_cleanup_retry(
    tmp_path: Path,
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    temporary = checkpoint_module._create_temporary(
        parent_fd, role="archive", seams=checkpoint_module._CheckpointSeams()
    )

    def corrupt_quarantine(point: str) -> None:
        if point.startswith("before_quarantine_delete:"):
            quarantine = next(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
            os.chmod(quarantine, 0o640)

    seams = checkpoint_module._CheckpointSeams(checkpoint=corrupt_quarantine)
    first = checkpoint_module._cleanup_temporary(temporary, seams, None)
    assert isinstance(first, CheckpointError)
    assert not temporary.removed
    assert "quarantine" not in temporary.name
    assert (tmp_path / temporary.name).exists()
    second = checkpoint_module._cleanup_temporary(temporary, seams, first)
    assert isinstance(second, CheckpointError)
    assert not temporary.removed
    assert (tmp_path / temporary.name).exists()
    os.close(parent_fd)


def test_ambiguous_rename_with_unavailable_proofs_never_claims_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned")
    os.chmod(leaf, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    expected = checkpoint_module._identity(os.stat(leaf, follow_symlinks=False))
    real_stat = checkpoint_module.os.stat
    failures = 0
    moved = False

    def rename_then_missing(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal moved
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)
        moved = True
        raise FileNotFoundError("ambiguous rename")

    def unavailable_quarantine(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal failures
        if moved and isinstance(path, str) and "quarantine" in path and failures < 2:
            failures += 1
            raise OSError("proof unavailable")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(checkpoint_module.os, "stat", unavailable_quarantine)
    outcome = checkpoint_module._quarantine_remove(
        parent_fd,
        leaf.name,
        expected,
        checkpoint_module._CheckpointSeams(rename_noreplace=rename_then_missing),
        None,
        published=False,
    )
    assert not outcome.removed
    assert outcome.name == leaf.name
    assert leaf.name in outcome.candidates
    assert any("quarantine" in candidate for candidate in outcome.candidates)
    assert outcome.restore_pairs == ()
    assert not leaf.exists()
    quarantine = next(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    assert quarantine.stat().st_ino == expected.inode
    os.close(parent_fd)


def test_missing_rename_source_stat_fatal_dominates_and_source_stays_tracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned")
    os.chmod(leaf, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    expected = checkpoint_module._identity(os.stat(leaf, follow_symlinks=False))
    real_stat = checkpoint_module.os.stat

    def missing_without_move(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("rename canary")

    def fatal_source(path: object, *args: object, **kwargs: object) -> os.stat_result:
        if path == leaf.name:
            raise KeyboardInterrupt
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(checkpoint_module.os, "stat", fatal_source)
    primary, removed = checkpoint_module._quarantine_remove(
        parent_fd,
        leaf.name,
        expected,
        checkpoint_module._CheckpointSeams(rename_noreplace=missing_without_move),
        None,
        published=False,
    )
    assert isinstance(primary, KeyboardInterrupt)
    assert not removed
    assert leaf.exists()
    os.close(parent_fd)


def test_pack_persistent_unlink_failure_never_claims_success_or_loses_owned_leaf(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    archive = tmp_path / checkpoint_archive_name(_provenance(shard))
    real_unlink = checkpoint_module.os.unlink
    armed = False
    archive_inode: int | None = None
    archive_payload: bytes | None = None

    def mutate(point: str) -> None:
        nonlocal archive_inode, archive_payload, armed
        if point == "after_archive_link":
            archive_inode = archive.stat().st_ino
            archive_payload = archive.read_bytes()
            armed = True
            raise OSError("post-link rollback canary")

    def deny_quarantine(path: object, *args: object, **kwargs: object) -> None:
        if armed and isinstance(path, str) and "quarantine" in path:
            raise PermissionError("persistent unlink canary")
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(checkpoint_module.os, "unlink", deny_quarantine)
    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=_provenance(shard),
            seams=checkpoint_module._CheckpointSeams(checkpoint=mutate),
        )
    assert caught.value.code == "post_publish_integrity_error"
    assert archive_inode is not None and archive_payload is not None
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()
    residues = tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    assert residues
    for path in residues:
        residue = path.stat(follow_symlinks=False)
        assert stat.S_ISREG(residue.st_mode)
        assert stat.S_IMODE(residue.st_mode) == 0o600
        assert residue.st_ino == archive_inode
        assert path.read_bytes() == archive_payload
        assert residue.st_nlink == len(residues)
    assert set(tmp_path.glob(".laconian-checkpoint.*.tmp")) == set(residues)


@pytest.mark.parametrize("fatal", [False, True])
def test_ambiguous_missing_rename_retries_quarantine_proof_and_cleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fatal: bool
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned")
    os.chmod(leaf, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    expected = checkpoint_module._identity(os.stat(leaf, follow_symlinks=False))
    real_stat = checkpoint_module.os.stat
    failed = False
    moved = False

    def rename_then_missing(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal moved
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)
        moved = True
        raise FileNotFoundError("ambiguous rename")

    def fail_first_quarantine(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal failed
        if moved and not failed and isinstance(path, str) and "quarantine" in path:
            failed = True
            if fatal:
                raise KeyboardInterrupt
            raise OSError("quarantine stat canary")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    try:
        monkeypatch.setattr(checkpoint_module.os, "stat", fail_first_quarantine)
        primary, removed = checkpoint_module._quarantine_remove(
            parent_fd,
            leaf.name,
            expected,
            checkpoint_module._CheckpointSeams(rename_noreplace=rename_then_missing),
            None,
            published=False,
        )
        assert failed and removed
        if fatal:
            assert isinstance(primary, KeyboardInterrupt)
        else:
            assert isinstance(primary, CheckpointError)
        assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    finally:
        os.close(parent_fd)


def test_file_exists_collision_never_swallows_fatal_post_link_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "collision.tar"
    archive.write_bytes(b"collision")
    os.chmod(archive, 0o600)
    real_stat = checkpoint_module.os.stat
    armed = False
    failed = False

    def collide(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal armed
        armed = True
        PosixOps().link_noreplace(source_fd, source, target_fd, target)

    def fatal_once(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal failed
        if armed and not failed and path == archive.name:
            failed = True
            raise KeyboardInterrupt
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    temporary = checkpoint_module._create_temporary(
        parent_fd, role="archive", seams=checkpoint_module._CheckpointSeams()
    )
    os.write(temporary.descriptor, b"new archive")
    seams = checkpoint_module._CheckpointSeams(link_noreplace=collide)
    try:
        monkeypatch.setattr(checkpoint_module.os, "stat", fatal_once)
        with pytest.raises(KeyboardInterrupt):
            checkpoint_module._publish_temporary(
                temporary,
                output_name=archive.name,
                seams=seams,
                state=checkpoint_module._PublicationState(),
                sidecar=False,
            )
    finally:
        checkpoint_module._cleanup_temporary(temporary, seams, None)
        os.close(parent_fd)
    assert failed
    assert archive.read_bytes() == b"collision"


def test_real_link_then_file_exists_with_fatal_fstat_is_owned_and_rolled_back(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    real_fstat = checkpoint_module.os.fstat
    linked = False
    temp_fd: int | None = None
    failures = 0

    def link_then_collision(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal linked, temp_fd
        PosixOps().link_noreplace(source_fd, source, target_fd, target)
        linked = True
        temp_fd = os.open(source, os.O_RDONLY, dir_fd=source_fd)
        raise FileExistsError("ambiguous collision")

    def fatal_twice(descriptor: int) -> os.stat_result:
        nonlocal failures
        if linked and failures < 2 and descriptor != temp_fd:
            failures += 1
            raise KeyboardInterrupt
        return real_fstat(descriptor)

    monkeypatch.setattr(checkpoint_module.os, "fstat", fatal_twice)
    try:
        with pytest.raises(KeyboardInterrupt):
            checkpoint_module._pack_checkpoint(
                capsule_path,
                archive,
                provenance=provenance,
                seams=checkpoint_module._CheckpointSeams(link_noreplace=link_then_collision),
            )
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
    assert failures == 2
    assert not archive.exists()


@pytest.mark.parametrize("sidecar", [False, True])
@pytest.mark.parametrize("error_kind", ["file_exists", "generic"])
@pytest.mark.parametrize("fatal", [False, True])
def test_ambiguous_link_with_unavailable_target_proof_retains_rollback_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sidecar: bool,
    error_kind: str,
    fatal: bool,
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    role = "sidecar" if sidecar else "archive"
    output_name = f"artifact{'.sha256' if sidecar else '.tar'}"
    temporary = checkpoint_module._create_temporary(
        parent_fd, role=role, seams=checkpoint_module._CheckpointSeams()
    )
    os.write(temporary.descriptor, b"owned output")
    real_stat = checkpoint_module.os.stat
    linked = False
    proof_failures = 0

    def link_then_raise(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal linked
        PosixOps().link_noreplace(source_fd, source, target_fd, target)
        linked = True
        if error_kind == "file_exists":
            raise FileExistsError("ambiguous link")
        raise OSError("ambiguous link")

    def unavailable(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal proof_failures
        if linked and path == output_name and proof_failures < 2:
            proof_failures += 1
            if fatal:
                raise KeyboardInterrupt
            raise OSError("target proof unavailable")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    state = checkpoint_module._PublicationState(parent_descriptor=parent_fd)
    seams = checkpoint_module._CheckpointSeams(link_noreplace=link_then_raise)
    monkeypatch.setattr(checkpoint_module.os, "stat", unavailable)
    expected_error = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected_error) as caught:
        checkpoint_module._publish_temporary(
            temporary,
            output_name=output_name,
            seams=seams,
            state=state,
            sidecar=sidecar,
        )
    primary = checkpoint_module._rollback_state_retained(
        archive_name="artifact.tar",
        state=state,
        seams=seams,
        primary=caught.value,
    )
    assert isinstance(primary, expected_error)
    assert proof_failures == 2
    assert not (tmp_path / output_name).exists()
    checkpoint_module._cleanup_temporary(temporary, seams, primary)
    os.close(parent_fd)


@pytest.mark.parametrize("fatal", [False, True])
def test_quarantine_checkpoint_failure_still_deletes_proven_owned_leaf(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)

    def inject(point: str) -> None:
        if point == "after_archive_link":
            (capsule_path / "manifest.json").write_bytes(b"mutation")
        if point == f"before_quarantine_delete:{archive.name}":
            if fatal:
                raise KeyboardInterrupt
            raise OSError("quarantine checkpoint canary")

    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(checkpoint=inject),
        )

    assert not archive.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))


@pytest.mark.parametrize("proof", ["stat", "fstat"])
@pytest.mark.parametrize("fatal", [False, True])
@pytest.mark.parametrize("role", ["archive", "sidecar"])
def test_first_post_link_proof_failure_never_leaves_untracked_target(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    proof: str,
    fatal: bool,
    role: str,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    armed = False
    armed_name = archive.name if role == "archive" else f"{archive.name}.sha256"
    failed = False
    real_stat = checkpoint_module.os.stat
    real_fstat = checkpoint_module.os.fstat

    def arm_after_link(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal armed
        PosixOps().link_noreplace(source_fd, source, target_fd, target)
        if target == armed_name:
            armed = True

    def fail_stat_once(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal failed
        if proof == "stat" and armed and not failed and path == armed_name:
            failed = True
            if fatal:
                raise KeyboardInterrupt
            raise OSError("post-link stat canary")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    def fail_fstat_once(descriptor: int) -> os.stat_result:
        nonlocal failed
        if proof == "fstat" and armed and not failed:
            failed = True
            if fatal:
                raise KeyboardInterrupt
            raise OSError("post-link fstat canary")
        return real_fstat(descriptor)

    monkeypatch.setattr(checkpoint_module.os, "stat", fail_stat_once)
    monkeypatch.setattr(checkpoint_module.os, "fstat", fail_fstat_once)
    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(link_noreplace=arm_after_link),
        )

    assert failed
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()


@pytest.mark.parametrize("fatal", [False, True])
def test_source_boundary_exit_runs_once_after_post_enter_initialization_failure(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    real_boundary = checkpoint_module.verified_checkpoint_source
    real_fstat = checkpoint_module.os.fstat
    root_fd: int | None = None
    exits = 0

    @contextmanager
    def tracked_boundary(path: Path):
        nonlocal root_fd, exits
        with real_boundary(path) as source:
            root_fd = source.root_descriptor
            try:
                yield source
            finally:
                exits += 1

    def fail_root_fstat(descriptor: int) -> os.stat_result:
        if root_fd is not None and descriptor == root_fd:
            if fatal:
                raise KeyboardInterrupt
            raise OSError("root fstat canary")
        return real_fstat(descriptor)

    monkeypatch.setattr(checkpoint_module, "verified_checkpoint_source", tracked_boundary)
    monkeypatch.setattr(checkpoint_module.os, "fstat", fail_root_fstat)
    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(),
        )

    assert exits == 1
    assert root_fd is not None
    with pytest.raises(OSError):
        real_fstat(root_fd)


@pytest.mark.parametrize("fatal", [False, True])
def test_temp_link_cleanup_failure_uses_provisional_target_identity_for_rollback(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    fatal: bool,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    failed = False

    def fail_first_archive_temp_cleanup(
        source_fd: int, source: str, target_fd: int, target: str
    ) -> None:
        nonlocal failed
        if not failed and source.startswith(".laconian-checkpoint.archive."):
            failed = True
            if fatal:
                raise KeyboardInterrupt
            raise OSError("temp cleanup canary")
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)

    expected = KeyboardInterrupt if fatal else CheckpointError
    with pytest.raises(expected):
        checkpoint_module._pack_checkpoint(
            capsule_path,
            archive,
            provenance=provenance,
            seams=checkpoint_module._CheckpointSeams(
                rename_noreplace=fail_first_archive_temp_cleanup
            ),
        )

    assert failed
    assert not archive.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


def test_ambiguous_missing_rename_preserves_unproven_other_and_never_claims_removed(
    tmp_path: Path,
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned-a")
    os.chmod(leaf, 0o600)
    expected = checkpoint_module._identity(leaf.stat(follow_symlinks=False))
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    def swap_move_then_missing(
        source_fd: int,
        source: str,
        target_fd: int,
        target: str,
    ) -> None:
        os.unlink(source, dir_fd=source_fd)
        replacement_fd = os.open(
            source,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=source_fd,
        )
        try:
            os.write(replacement_fd, b"canary-b")
        finally:
            os.close(replacement_fd)
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)
        raise FileNotFoundError("ambiguous swapped rename")

    try:
        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            leaf.name,
            expected,
            checkpoint_module._CheckpointSeams(rename_noreplace=swap_move_then_missing),
            None,
            published=False,
        )
    finally:
        os.close(parent_fd)

    assert isinstance(outcome.primary, CheckpointError)
    assert not outcome.removed
    assert not leaf.exists()
    quarantine = next(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    assert quarantine.read_bytes() == b"canary-b"
    assert outcome.restore_pairs == ()


def test_retry_never_restores_other_from_a_rename_that_threw(
    tmp_path: Path,
) -> None:
    original = tmp_path / "owned"
    original.write_bytes(b"owned-a")
    os.chmod(original, 0o600)
    expected = checkpoint_module._identity(original.stat(follow_symlinks=False))
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    def move_other_but_deny_restore(
        source_fd: int,
        source: str,
        target_fd: int,
        target: str,
    ) -> None:
        if source == original.name:
            os.unlink(source, dir_fd=source_fd)
            replacement_fd = os.open(
                source,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=source_fd,
            )
            try:
                os.write(replacement_fd, b"canary-b")
            finally:
                os.close(replacement_fd)
            PosixOps().rename_noreplace(source_fd, source, target_fd, target)
            raise FileNotFoundError("ambiguous swapped rename")
        raise PermissionError("restore denied")

    try:
        first = checkpoint_module._quarantine_remove(
            parent_fd,
            original.name,
            expected,
            checkpoint_module._CheckpointSeams(rename_noreplace=move_other_but_deny_restore),
            None,
            published=False,
        )
        assert isinstance(first.primary, CheckpointError)
        assert not first.removed
        assert original.name in first.candidates
        assert any("quarantine" in candidate for candidate in first.candidates)
        quarantine = next(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
        assert first.restore_pairs == ()
        assert not original.exists()
        assert quarantine.read_bytes() == b"canary-b"

        second = checkpoint_module._quarantine_remove(
            parent_fd,
            first.candidates,
            expected,
            checkpoint_module._CheckpointSeams(),
            first.primary,
            published=False,
            restore_pairs=first.restore_pairs,
        )
        assert not second.removed
        assert not original.exists()
        assert quarantine.read_bytes() == b"canary-b"
        assert second.restore_pairs == ()
    finally:
        os.close(parent_fd)


def test_preexisting_generated_quarantine_collision_is_never_moved_or_deleted(
    tmp_path: Path,
) -> None:
    owned = tmp_path / "owned"
    owned.write_bytes(b"owned-a")
    os.chmod(owned, 0o600)
    expected = checkpoint_module._identity(owned.stat(follow_symlinks=False))
    operation_id = UUID(UUID_B)
    quarantine = tmp_path / f".laconian-checkpoint.quarantine.{operation_id}.tmp"
    quarantine.write_bytes(b"preexisting-canary")
    os.chmod(quarantine, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    callback_calls = 0

    def destructive_collision(
        source_fd: int,
        source: str,
        _target_fd: int,
        _target: str,
    ) -> None:
        nonlocal callback_calls
        callback_calls += 1
        os.unlink(source, dir_fd=source_fd)
        raise FileExistsError("preexisting quarantine collision")

    try:
        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            owned.name,
            expected,
            checkpoint_module._CheckpointSeams(
                new_uuid=lambda: operation_id,
                rename_noreplace=destructive_collision,
            ),
            None,
            published=False,
        )
    finally:
        os.close(parent_fd)

    assert isinstance(outcome.primary, CheckpointError)
    assert not outcome.removed
    assert callback_calls == 0
    assert owned.read_bytes() == b"owned-a"
    assert quarantine.read_bytes() == b"preexisting-canary"


def test_file_exists_race_canary_never_inherits_preproved_restore_authority(
    tmp_path: Path,
) -> None:
    owned = tmp_path / "owned"
    owned.write_bytes(b"owned-a")
    os.chmod(owned, 0o600)
    expected = checkpoint_module._identity(owned.stat(follow_symlinks=False))
    operation_id = UUID(UUID_B)
    quarantine = tmp_path / f".laconian-checkpoint.quarantine.{operation_id}.tmp"
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    callback_calls = 0

    def race_collision(
        source_fd: int,
        source: str,
        target_fd: int,
        target: str,
    ) -> None:
        nonlocal callback_calls
        callback_calls += 1
        if callback_calls == 1:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=target_fd)
            try:
                os.write(fd, b"race-canary")
            finally:
                os.close(fd)
            os.unlink(source, dir_fd=source_fd)
            raise FileExistsError("raced quarantine creation")
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)

    try:
        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            owned.name,
            expected,
            checkpoint_module._CheckpointSeams(
                new_uuid=lambda: operation_id,
                rename_noreplace=race_collision,
            ),
            None,
            published=False,
        )
    finally:
        os.close(parent_fd)

    assert isinstance(outcome.primary, CheckpointError)
    assert not outcome.removed
    assert callback_calls == 1
    assert not owned.exists()
    assert quarantine.read_bytes() == b"race-canary"
    assert outcome.restore_pairs == ()


@pytest.mark.parametrize(
    "raised",
    [OSError("ambiguous rename"), KeyboardInterrupt("fatal ambiguous rename")],
    ids=["ordinary", "fatal"],
)
def test_thrown_rename_never_grants_restore_authority_to_a_race_canary(
    tmp_path: Path,
    raised: BaseException,
) -> None:
    owned = tmp_path / "owned"
    owned.write_bytes(b"owned-a")
    os.chmod(owned, 0o600)
    expected = checkpoint_module._identity(owned.stat(follow_symlinks=False))
    operation_id = UUID(UUID_B)
    quarantine = tmp_path / f".laconian-checkpoint.quarantine.{operation_id}.tmp"
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    callback_calls = 0

    def race_then_throw(source_fd: int, source: str, target_fd: int, target: str) -> None:
        nonlocal callback_calls
        callback_calls += 1
        if callback_calls == 1:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=target_fd)
            try:
                os.write(fd, b"race-canary")
            finally:
                os.close(fd)
            os.unlink(source, dir_fd=source_fd)
            raise raised
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)

    try:
        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            owned.name,
            expected,
            checkpoint_module._CheckpointSeams(
                new_uuid=lambda: operation_id,
                rename_noreplace=race_then_throw,
            ),
            None,
            published=False,
        )
    finally:
        os.close(parent_fd)

    if isinstance(raised, KeyboardInterrupt):
        assert outcome.primary is raised
    else:
        assert isinstance(outcome.primary, CheckpointError)
    assert not outcome.removed
    assert callback_calls == 1
    assert not owned.exists()
    assert quarantine.read_bytes() == b"race-canary"
    assert outcome.restore_pairs == ()


def test_candidate_tuple_alone_never_authorizes_other_restoration(
    tmp_path: Path,
) -> None:
    expected_source = tmp_path / "expected-source"
    expected_source.write_bytes(b"owned-a")
    os.chmod(expected_source, 0o600)
    expected = checkpoint_module._identity(expected_source.stat(follow_symlinks=False))
    expected_source.unlink()
    restore_target = tmp_path / "restore-target"
    quarantine = tmp_path / ".laconian-checkpoint.quarantine.unproven.tmp"
    quarantine.write_bytes(b"preexisting-canary")
    os.chmod(quarantine, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    try:
        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            (restore_target.name, quarantine.name),
            expected,
            checkpoint_module._CheckpointSeams(),
            None,
            published=False,
        )
    finally:
        os.close(parent_fd)

    assert isinstance(outcome.primary, CheckpointError)
    assert not outcome.removed
    assert not restore_target.exists()
    assert quarantine.read_bytes() == b"preexisting-canary"


def test_proven_other_restoration_precedes_removal_of_a_separate_expected_name(
    tmp_path: Path,
) -> None:
    restore_target = tmp_path / "restore-target"
    owned = tmp_path / "owned-location"
    restore_target.write_bytes(b"owned-a")
    os.chmod(restore_target, 0o600)
    os.link(restore_target, owned)
    expected = checkpoint_module._identity(restore_target.stat(follow_symlinks=False))
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    restore_denied = False

    def displace_other_then_fail_first_restore(
        source_fd: int,
        source: str,
        target_fd: int,
        target: str,
    ) -> None:
        nonlocal restore_denied
        if source == restore_target.name:
            os.unlink(source, dir_fd=source_fd)
            replacement_fd = os.open(
                source,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=source_fd,
            )
            try:
                os.write(replacement_fd, b"canary-b")
            finally:
                os.close(replacement_fd)
            PosixOps().rename_noreplace(source_fd, source, target_fd, target)
            return
        if "quarantine" in source and not restore_denied:
            restore_denied = True
            raise PermissionError("first restore denied")
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)

    try:
        first = checkpoint_module._quarantine_remove(
            parent_fd,
            (restore_target.name, owned.name),
            expected,
            checkpoint_module._CheckpointSeams(
                rename_noreplace=displace_other_then_fail_first_restore
            ),
            None,
            published=False,
        )
        assert isinstance(first.primary, CheckpointError)
        assert not first.removed
        assert restore_denied
        assert owned.read_bytes() == b"owned-a"
        quarantine = next(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
        assert quarantine.read_bytes() == b"canary-b"
        assert (restore_target.name, quarantine.name) in first.restore_pairs

        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            first.candidates,
            expected,
            checkpoint_module._CheckpointSeams(),
            first.primary,
            published=False,
            restore_pairs=first.restore_pairs,
        )
    finally:
        os.close(parent_fd)

    assert isinstance(outcome.primary, CheckpointError)
    assert outcome.removed
    assert restore_target.read_bytes() == b"canary-b"
    assert not owned.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


def test_ambiguous_generic_rename_retains_both_names_until_retry_proves_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned")
    os.chmod(leaf, 0o600)
    expected = checkpoint_module._identity(leaf.stat(follow_symlinks=False))
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_stat = checkpoint_module.os.stat
    proof_failures = 0
    moved = False

    def move_then_raise(
        source_fd: int,
        source: str,
        target_fd: int,
        target: str,
    ) -> None:
        nonlocal moved
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)
        moved = True
        raise OSError("ambiguous rename")

    def unavailable_quarantine(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal proof_failures
        if moved and isinstance(path, str) and "quarantine" in path and proof_failures < 2:
            proof_failures += 1
            raise OSError("quarantine proof unavailable")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    try:
        monkeypatch.setattr(checkpoint_module.os, "stat", unavailable_quarantine)
        first = checkpoint_module._quarantine_remove(
            parent_fd,
            leaf.name,
            expected,
            checkpoint_module._CheckpointSeams(rename_noreplace=move_then_raise),
            None,
            published=False,
        )
        assert isinstance(first.primary, CheckpointError)
        assert not first.removed
        assert leaf.name in first.candidates
        assert any("quarantine" in candidate for candidate in first.candidates)
        assert not leaf.exists()
        assert tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))

        second = checkpoint_module._quarantine_remove(
            parent_fd,
            first.candidates,
            expected,
            checkpoint_module._CheckpointSeams(),
            first.primary,
            published=False,
        )
        assert second.removed
        assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    finally:
        os.close(parent_fd)


def test_ambiguous_restore_retains_original_and_quarantine_until_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned-a")
    os.chmod(leaf, 0o600)
    expected = checkpoint_module._identity(leaf.stat(follow_symlinks=False))
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_stat = checkpoint_module.os.stat
    restore_started = False
    proof_failures = 0

    def mutate_quarantine(point: str) -> None:
        if not point.startswith("before_quarantine_delete:"):
            return
        quarantine = next(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
        quarantine.unlink()
        quarantine.write_bytes(b"canary-b")
        os.chmod(quarantine, 0o600)

    def restore_then_raise(
        source_fd: int,
        source: str,
        target_fd: int,
        target: str,
    ) -> None:
        nonlocal restore_started
        PosixOps().rename_noreplace(source_fd, source, target_fd, target)
        if "quarantine" in source:
            restore_started = True
            raise OSError("ambiguous restore")

    def unavailable_restored_original(
        path: object, *args: object, **kwargs: object
    ) -> os.stat_result:
        nonlocal proof_failures
        if restore_started and path == leaf.name and proof_failures < 2:
            proof_failures += 1
            raise OSError("restored proof unavailable")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    seams = checkpoint_module._CheckpointSeams(
        checkpoint=mutate_quarantine,
        rename_noreplace=restore_then_raise,
    )
    try:
        monkeypatch.setattr(checkpoint_module.os, "stat", unavailable_restored_original)
        first = checkpoint_module._quarantine_remove(
            parent_fd,
            leaf.name,
            expected,
            seams,
            None,
            published=False,
        )
        assert isinstance(first.primary, CheckpointError)
        assert not first.removed
        assert leaf.name in first.candidates
        assert any("quarantine" in candidate for candidate in first.candidates)
        assert leaf.read_bytes() == b"canary-b"

        second = checkpoint_module._quarantine_remove(
            parent_fd,
            first.candidates,
            expected,
            checkpoint_module._CheckpointSeams(),
            first.primary,
            published=False,
        )
        assert isinstance(second.primary, CheckpointError)
        assert not second.removed
        assert leaf.read_bytes() == b"canary-b"
        assert not tuple(tmp_path.glob(".laconian-checkpoint.quarantine.*.tmp"))
    finally:
        os.close(parent_fd)


def test_original_and_tracked_quarantine_same_inode_removes_both(
    tmp_path: Path,
) -> None:
    leaf = tmp_path / "owned"
    leaf.write_bytes(b"owned")
    os.chmod(leaf, 0o600)
    expected = checkpoint_module._identity(leaf.stat(follow_symlinks=False))
    operation_id = UUID(UUID_B)
    quarantine = tmp_path / (f".laconian-checkpoint.quarantine.{operation_id}.tmp")
    os.link(leaf, quarantine)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    try:
        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            (leaf.name, quarantine.name),
            expected,
            checkpoint_module._CheckpointSeams(),
            None,
            published=False,
        )
    finally:
        os.close(parent_fd)

    assert outcome.primary is None
    assert outcome.removed
    assert not leaf.exists()
    assert not quarantine.exists()


def test_two_matching_names_do_not_claim_removed_while_one_proof_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = tmp_path / "owned"
    original.write_bytes(b"owned")
    os.chmod(original, 0o600)
    expected = checkpoint_module._identity(original.stat(follow_symlinks=False))
    quarantine = tmp_path / ".laconian-checkpoint.quarantine.retained.tmp"
    os.link(original, quarantine)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    real_stat = checkpoint_module.os.stat
    real_unlink = checkpoint_module.os.unlink
    quarantine_removed = False
    proof_failures = 0

    def track_unlink(path: object, *args: object, **kwargs: object) -> None:
        nonlocal quarantine_removed
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]
        if path == quarantine.name:
            quarantine_removed = True

    def unavailable_original(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal proof_failures
        if quarantine_removed and path == original.name and proof_failures < 2:
            proof_failures += 1
            raise OSError("remaining proof unavailable")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    try:
        monkeypatch.setattr(checkpoint_module.os, "unlink", track_unlink)
        monkeypatch.setattr(checkpoint_module.os, "stat", unavailable_original)
        first = checkpoint_module._quarantine_remove(
            parent_fd,
            (original.name, quarantine.name),
            expected,
            checkpoint_module._CheckpointSeams(),
            None,
            published=False,
        )
        assert isinstance(first.primary, CheckpointError)
        assert not first.removed
        assert original.name in first.candidates
        assert original.exists()
        assert not quarantine.exists()

        second = checkpoint_module._quarantine_remove(
            parent_fd,
            first.candidates,
            expected,
            checkpoint_module._CheckpointSeams(),
            first.primary,
            published=False,
        )
        assert second.removed
        assert not original.exists()
    finally:
        os.close(parent_fd)


def test_other_candidate_is_content_free_cleanup_error_and_is_never_deleted(
    tmp_path: Path,
) -> None:
    original = tmp_path / "owned"
    original.write_bytes(b"owned-a")
    os.chmod(original, 0o600)
    expected = checkpoint_module._identity(original.stat(follow_symlinks=False))
    quarantine = tmp_path / ".laconian-checkpoint.quarantine.retained.tmp"
    original.rename(quarantine)
    original.write_bytes(b"canary-b")
    os.chmod(original, 0o600)
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    try:
        outcome = checkpoint_module._quarantine_remove(
            parent_fd,
            (original.name, quarantine.name),
            expected,
            checkpoint_module._CheckpointSeams(),
            None,
            published=False,
        )
    finally:
        os.close(parent_fd)

    assert isinstance(outcome.primary, CheckpointError)
    assert outcome.primary.code == "io_error"
    assert outcome.removed
    assert original.read_bytes() == b"canary-b"
    assert not quarantine.exists()
    assert not tuple(tmp_path.glob(".laconian-checkpoint.*.tmp"))


@pytest.mark.parametrize("sidecar", [False, True])
@pytest.mark.parametrize("error_kind", ["file_exists", "generic"])
@pytest.mark.parametrize("fatal", [False, True])
def test_both_unknown_publication_proofs_remain_owned_until_outer_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sidecar: bool,
    error_kind: str,
    fatal: bool,
) -> None:
    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    role = "sidecar" if sidecar else "archive"
    output_name = f"artifact{'.sha256' if sidecar else '.tar'}"
    temporary = checkpoint_module._create_temporary(
        parent_fd, role=role, seams=checkpoint_module._CheckpointSeams()
    )
    os.write(temporary.descriptor, b"owned output")
    real_stat = checkpoint_module.os.stat
    real_fstat = checkpoint_module.os.fstat
    linked = False
    stat_failures = 0
    fstat_failures = 0

    def link_then_raise(
        source_fd: int,
        source: str,
        target_fd: int,
        target: str,
    ) -> None:
        nonlocal linked
        PosixOps().link_noreplace(source_fd, source, target_fd, target)
        linked = True
        if error_kind == "file_exists":
            raise FileExistsError("ambiguous link")
        raise OSError("ambiguous link")

    def unavailable_target(path: object, *args: object, **kwargs: object) -> os.stat_result:
        nonlocal stat_failures
        if linked and path == output_name and stat_failures < 2:
            stat_failures += 1
            if fatal:
                raise KeyboardInterrupt
            raise OSError("target proof unavailable")
        return real_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    def unavailable_retained(descriptor: int) -> os.stat_result:
        nonlocal fstat_failures
        if linked and descriptor == temporary.descriptor and fstat_failures < 2:
            fstat_failures += 1
            if fatal:
                raise KeyboardInterrupt
            raise OSError("retained proof unavailable")
        return real_fstat(descriptor)

    state = checkpoint_module._PublicationState(parent_descriptor=parent_fd)
    seams = checkpoint_module._CheckpointSeams(link_noreplace=link_then_raise)
    monkeypatch.setattr(checkpoint_module.os, "stat", unavailable_target)
    monkeypatch.setattr(checkpoint_module.os, "fstat", unavailable_retained)
    expected_error = KeyboardInterrupt if fatal else CheckpointError
    try:
        with pytest.raises(expected_error) as caught:
            checkpoint_module._publish_temporary(
                temporary,
                output_name=output_name,
                seams=seams,
                state=state,
                sidecar=sidecar,
            )
        ownership = state.sidecar_ownership if sidecar else state.archive_ownership
        assert ownership == "POSSIBLY_OWNED"
        primary = checkpoint_module._rollback_state_retained(
            archive_name="artifact.tar",
            state=state,
            seams=seams,
            primary=caught.value,
        )
        assert isinstance(primary, expected_error)
        assert stat_failures == 2
        assert fstat_failures == 2
        assert not (tmp_path / output_name).exists()
        checkpoint_module._cleanup_temporary(temporary, seams, primary)
    finally:
        os.close(parent_fd)
