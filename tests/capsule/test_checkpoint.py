from __future__ import annotations

import errno
import multiprocessing
import os
import resource
import stat
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from capsule_helpers import UUID_B

import laconian_eval.capsule.checkpoint as checkpoint_module
import laconian_eval.capsule.execution as execution_module
import laconian_eval.capsule.prepare as prepare_module
import laconian_eval.capsule.verify as verify_module
from laconian_eval.capsule.canonical import sha256_bytes
from laconian_eval.capsule.checkpoint import (
    CheckpointError,
    CheckpointExpectedBindingsV1,
    CheckpointProtocolBindingV1,
    CheckpointProvenanceV1,
    checkpoint_archive_name,
    pack_checkpoint,
    restore_checkpoint,
)
from laconian_eval.capsule.execution import ProviderFactory
from laconian_eval.capsule.finalize import finalize_capsule
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.capsule.record_models import CapsuleV1
from laconian_eval.capsule.sharding import ShardPlanV1
from laconian_eval.capsule.verify import (
    VerificationMode,
    verified_checkpoint_source,
    verify_capsule,
)

from . import test_prepare as test_prepare_module
from .test_execution import (
    _benchmark_replay_outcome,
    _BenchmarkScriptedProvider,
    _install_fast_runtime,
    _seams_for_provider,
    _single_plan_capsule,
)
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


TreeSnapshot = tuple[tuple[str, str, int, bytes | None], ...]


def snapshot_tree(root: Path) -> TreeSnapshot:
    entries: list[tuple[str, str, int, bytes | None]] = []
    paths = (root, *root.rglob("*"))
    for path in sorted(
        paths,
        key=lambda candidate: (
            candidate != root,
            candidate.relative_to(root).as_posix().encode("utf-8"),
        ),
    ):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix() or "."
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
            payload = None
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
            payload = path.read_bytes()
        else:  # pragma: no cover - a valid capsule cannot reach this test helper branch
            raise AssertionError("unexpected capsule path kind")
        entries.append((relative, kind, stat.S_IMODE(metadata.st_mode), payload))
    return tuple(entries)


def _load_protocol_bound_shard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, ShardPlanV1]:
    protocol_files = (
        ("rubric-alpha", "protocols/rubric-alpha.bin", b"rubric-alpha\x00v1\n"),
        ("rubric-beta", "protocols/rubric-beta.bin", b"rubric-beta\xffv1\n"),
    )
    real_manifest_payload = test_prepare_module._manifest_payload
    real_load_source = prepare_module.load_source_manifest_capture

    def protocol_manifest_payload(**kwargs: object) -> dict[str, object]:
        payload = real_manifest_payload(**kwargs)  # type: ignore[arg-type]
        capsule = payload["capsule"]
        assert isinstance(capsule, dict)
        capsule["protocol_bindings"] = [
            {
                "binding_id": binding_id,
                "kind": "org.example.rubric",
                "schema_id": "org.example.rubric.v1",
                "media_type": "application/octet-stream",
                "path": relative_path,
                "scope": {
                    "dataset_ids": ["prepare-dataset"],
                    "comparison_ids": [],
                },
                "bound_at_stage": "pre_generation",
                "applies_at": ["scoring", "publication"],
                "declared_requirement": "optional",
            }
            for binding_id, relative_path, _payload in protocol_files
        ]
        return payload

    def load_source_with_protocols(
        path: object,
        *,
        input_root: object,
        invocation_cwd: object,
    ) -> object:
        source_root = Path(path).parent  # type: ignore[arg-type]
        for _binding_id, relative_path, payload in protocol_files:
            target = source_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        return real_load_source(
            path,  # type: ignore[arg-type]
            input_root=input_root,  # type: ignore[arg-type]
            invocation_cwd=invocation_cwd,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(test_prepare_module, "_manifest_payload", protocol_manifest_payload)
    monkeypatch.setattr(prepare_module, "load_source_manifest_capture", load_source_with_protocols)
    prepared, _harness, _manifest, _parent_plan, shard = _load_shard_success(
        tmp_path,
        monkeypatch,
    )
    assert isinstance(shard, ShardPlanV1)
    assert shard.row_count == 40
    planning = prepared.path / "inputs" / "planning"
    child = planning / "shard-plan.json"
    os.chmod(planning, 0o555)
    os.chmod(child, 0o640)
    return prepared.path, shard


def _complete_shard_capsule(
    capsule_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        capsule_path,
        provider_factory=ProviderFactory(),
        seams=_seams_for_provider(provider),
    )
    assert outcome.exit_code == 0
    assert outcome.result.state == "GENERATION_COMPLETE"
    assert len(provider.benchmark_calls) == 40
    assert finalize_capsule(capsule_path).state == "SEALED_COMPLETE"


def _expected_bindings(
    source: Path,
    shard: ShardPlanV1,
    *,
    archive_sha256: str,
    provenance: CheckpointProvenanceV1,
) -> CheckpointExpectedBindingsV1:
    capsule = CapsuleV1.model_validate_json((source / "capsule.json").read_bytes())
    manifest = ResolvedManifestV2.model_validate_json((source / "manifest.json").read_bytes())
    parent_plan_bytes = (source / "inputs/planning/parent-plan.jsonl").read_bytes()
    shard_plan_bytes = (source / "inputs/planning/shard-plan.json").read_bytes()
    captured_shard = ShardPlanV1.model_validate_json(shard_plan_bytes)
    assert captured_shard == shard
    assert shard.parent_plan_sha256 == sha256_bytes(parent_plan_bytes)
    return CheckpointExpectedBindingsV1(
        archive_sha256=archive_sha256,
        manifest_sha256=capsule.manifest_sha256,
        plan_sha256=capsule.plan_sha256,
        parent_plan_sha256=sha256_bytes(parent_plan_bytes),
        shard_plan_sha256=captured_shard.shard_plan_sha256,
        requested_model=captured_shard.model_id,
        scenario_uid=captured_shard.scenario_uid,
        protocol_bindings=tuple(
            CheckpointProtocolBindingV1(
                binding_id=binding.binding_id,
                sha256=binding.sha256,
            )
            for binding in manifest.capsule.protocol_bindings
        ),
        provenance=provenance,
    )


@dataclass(frozen=True, slots=True)
class _RawUstarMember:
    path: str | bytes
    typeflag: bytes = b"0"
    mode: int = 0o600
    payload: bytes = b""
    declared_size: int | None = None
    mode_field: bytes | None = None
    size_field: bytes | None = None
    magic: bytes = b"ustar\0"
    version: bytes = b"00"
    valid_checksum: bool = True


def _raw_octal(value: int, width: int) -> bytes:
    encoded = f"{value:0{width - 1}o}".encode("ascii")
    assert len(encoded) == width - 1
    return encoded + b"\0"


def _raw_ustar_path(path: bytes) -> tuple[bytes, bytes]:
    if len(path) <= 100:
        return b"", path
    for position in range(len(path) - 1, -1, -1):
        if path[position : position + 1] != b"/":
            continue
        prefix = path[:position]
        name = path[position + 1 :]
        if prefix and name and len(prefix) <= 155 and len(name) <= 100:
            return prefix, name
    raise AssertionError("test USTAR path does not fit prefix/name fields")


def _raw_ustar_header(member: _RawUstarMember) -> bytes:
    path = member.path.encode("utf-8") if isinstance(member.path, str) else member.path
    prefix, name = _raw_ustar_path(path)
    assert len(member.typeflag) == 1
    assert len(member.magic) == 6
    assert len(member.version) == 2
    size = len(member.payload) if member.declared_size is None else member.declared_size
    header = bytearray(_BLOCK_BYTES)
    header[: len(name)] = name
    header[100:108] = member.mode_field or _raw_octal(member.mode, 8)
    header[108:116] = _raw_octal(0, 8)
    header[116:124] = _raw_octal(0, 8)
    header[124:136] = member.size_field or _raw_octal(size, 12)
    header[136:148] = _raw_octal(0, 12)
    header[148:156] = b"        "
    header[156:157] = member.typeflag
    header[257:263] = member.magic
    header[263:265] = member.version
    header[345 : 345 + len(prefix)] = prefix
    checksum = sum(header)
    header[148:156] = f"{checksum:06o}".encode("ascii") + b"\0 "
    if not member.valid_checksum:
        header[148:156] = b"000000\0 "
    return bytes(header)


def _raw_ustar_archive(
    members: tuple[_RawUstarMember, ...],
    *,
    terminal_blocks: int = 2,
    trailer: bytes = b"",
    padding_byte: int = 0,
    short_final_member: bool = False,
) -> bytes:
    archive = bytearray()
    for ordinal, member in enumerate(members):
        archive.extend(_raw_ustar_header(member))
        archive.extend(member.payload)
        if short_final_member and ordinal == len(members) - 1:
            return bytes(archive)
        declared_size = (
            len(member.payload) if member.declared_size is None else member.declared_size
        )
        padding = (-declared_size) % _BLOCK_BYTES
        archive.extend(bytes([padding_byte]) * padding)
    archive.extend(bytes(terminal_blocks * _BLOCK_BYTES))
    archive.extend(trailer)
    return bytes(archive)


def _raw_members_from_tree(root: Path) -> tuple[_RawUstarMember, ...]:
    members: list[_RawUstarMember] = []
    for path in sorted(
        root.rglob("*"),
        key=lambda candidate: candidate.relative_to(root).as_posix().encode("utf-8"),
    ):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISDIR(metadata.st_mode):
            members.append(
                _RawUstarMember(
                    relative,
                    typeflag=b"5",
                    mode=stat.S_IMODE(metadata.st_mode),
                )
            )
        elif stat.S_ISREG(metadata.st_mode):
            members.append(
                _RawUstarMember(
                    relative,
                    mode=stat.S_IMODE(metadata.st_mode),
                    payload=path.read_bytes(),
                )
            )
        else:  # pragma: no cover - source construction guarantees a regular capsule tree
            raise AssertionError("unexpected source path kind")
    return tuple(members)


def _raw_members_from_archive(archive_bytes: bytes) -> tuple[_RawUstarMember, ...]:
    parsed, _terminal_offset = _parse_raw_ustar(archive_bytes)
    return tuple(
        _RawUstarMember(
            path,
            typeflag=typeflag.encode("ascii"),
            mode=mode,
            payload=payload,
        )
        for path, typeflag, mode, _size, payload in parsed
    )


@dataclass(frozen=True, slots=True)
class _RawRestoreCase:
    archive_path: Path
    sidecar_path: Path
    destination_parent: Path
    destination_name: str
    destination: Path
    sentinel: Path
    sentinel_bytes: bytes
    expected: CheckpointExpectedBindingsV1


@dataclass(frozen=True, slots=True)
class _PackedRestoreBaseline:
    archive_bytes: bytes
    expected: CheckpointExpectedBindingsV1


@pytest.fixture(scope="module")
def packed_restore_baseline(
    tmp_path_factory: pytest.TempPathFactory,
) -> _PackedRestoreBaseline:
    root = tmp_path_factory.mktemp("packed-restore-baseline")
    patcher = pytest.MonkeyPatch()
    try:
        source, shard = _load_protocol_bound_shard(root, patcher)
        provenance = _provenance(shard)
        transport = root / "transport"
        transport.mkdir()
        artifact = pack_checkpoint(
            source,
            transport / checkpoint_archive_name(provenance),
            provenance=provenance,
        )
        expected = _expected_bindings(
            source,
            shard,
            archive_sha256=artifact.sha256,
            provenance=provenance,
        )
        archive_bytes = artifact.archive_path.read_bytes()
        assert _raw_ustar_archive(_raw_members_from_archive(archive_bytes)) == archive_bytes
        return _PackedRestoreBaseline(archive_bytes=archive_bytes, expected=expected)
    finally:
        patcher.undo()


def _synthetic_expected_bindings(
    archive_sha256: str,
) -> CheckpointExpectedBindingsV1:
    scenario_uid = "a" * 64
    provenance = CheckpointProvenanceV1(
        campaign_id="hostile-restore-v1",
        model_id="gpt-5.6-sol",
        scenario_uid=scenario_uid,
        batch_attempt_id=UUID(UUID_B),
        run_attempt=1,
    )
    return CheckpointExpectedBindingsV1(
        archive_sha256=archive_sha256,
        manifest_sha256="b" * 64,
        plan_sha256="c" * 64,
        parent_plan_sha256="d" * 64,
        shard_plan_sha256="e" * 64,
        requested_model=provenance.model_id,
        scenario_uid=scenario_uid,
        protocol_bindings=(),
        provenance=provenance,
    )


def _write_raw_restore_case(
    tmp_path: Path,
    archive_bytes: bytes,
    *,
    expected_template: CheckpointExpectedBindingsV1 | None = None,
    authority_sha256: str | None = None,
    sidecar_sha256: str | None = None,
    sidecar_basename: str | None = None,
    archive_basename: str | None = None,
) -> _RawRestoreCase:
    actual_sha256 = sha256_bytes(archive_bytes)
    template = expected_template or _synthetic_expected_bindings(actual_sha256)
    expected = replace(
        template,
        archive_sha256=authority_sha256 or actual_sha256,
    )
    transport = tmp_path / "transport"
    transport.mkdir(parents=True)
    archive_path = transport / (archive_basename or checkpoint_archive_name(expected.provenance))
    archive_path.write_bytes(archive_bytes)
    sidecar_path = Path(f"{archive_path}.sha256")
    sidecar_path.write_bytes(
        (f"{sidecar_sha256 or actual_sha256}  {sidecar_basename or archive_path.name}\n").encode(
            "ascii"
        )
    )
    os.chmod(archive_path, 0o600)
    os.chmod(sidecar_path, 0o600)
    destination_parent = tmp_path / "restore-parent"
    destination_parent.mkdir(parents=True)
    sentinel_bytes = b"unrelated restore sentinel\x00\xff\n"
    sentinel = destination_parent / "unrelated.sentinel"
    sentinel.write_bytes(sentinel_bytes)
    destination_name = "restored-capsule"
    return _RawRestoreCase(
        archive_path=archive_path,
        sidecar_path=sidecar_path,
        destination_parent=destination_parent,
        destination_name=destination_name,
        destination=destination_parent / destination_name,
        sentinel=sentinel,
        sentinel_bytes=sentinel_bytes,
        expected=expected,
    )


def _public_restore(case: _RawRestoreCase) -> Path:
    return restore_checkpoint(
        case.archive_path,
        case.sidecar_path,
        destination_parent=case.destination_parent,
        destination_name=case.destination_name,
        expected=case.expected,
    )


def _seamed_restore(
    case: _RawRestoreCase,
    *,
    checkpoint: Callable[[str], None] = lambda _point: None,
    monotonic: Callable[[], float] | None = None,
    parse_read: Callable[[int, int], bytes] | None = None,
    fsync: Callable[[int], None] | None = None,
    rename_noreplace: Callable[[int, str, int, str], None] | None = None,
) -> Path:
    seam_values: dict[str, Any] = {"checkpoint": checkpoint}
    if monotonic is not None:
        seam_values["monotonic"] = monotonic
    if parse_read is not None:
        seam_values["parse_read"] = parse_read
    if fsync is not None:
        seam_values["fsync"] = fsync
    if rename_noreplace is not None:
        seam_values["rename_noreplace"] = rename_noreplace
    return checkpoint_module._restore_checkpoint(
        case.archive_path,
        case.sidecar_path,
        destination_parent=case.destination_parent,
        destination_name=case.destination_name,
        expected=case.expected,
        seams=checkpoint_module._RestoreSeams(**seam_values),
    )


def _assert_restore_rejected(
    case: _RawRestoreCase,
    *,
    invoke: Callable[[_RawRestoreCase], Path] = _public_restore,
) -> CheckpointError:
    with pytest.raises(CheckpointError) as caught:
        invoke(case)
    assert not case.destination.exists()
    assert case.sentinel.read_bytes() == case.sentinel_bytes
    return caught.value


class _VerifierBomb(BaseException):
    pass


def _assert_restore_rejected_at_phase(
    case: _RawRestoreCase,
    *,
    expected_code: str,
    required_points: tuple[str, ...] = (),
    forbidden_points: tuple[str, ...] = (),
    monotonic: Callable[[], float] | None = None,
    parse_read: Callable[[int, int], bytes] | None = None,
    verifier_bomb: bool = False,
    checkpoint_action: Callable[[str], None] | None = None,
) -> tuple[str, ...]:
    points: list[str] = []

    def record(point: str) -> None:
        points.append(point)
        if checkpoint_action is not None:
            checkpoint_action(point)
        if verifier_bomb and point == "before_capsule_verification":
            raise _VerifierBomb

    error = _assert_restore_rejected(
        case,
        invoke=lambda candidate: _seamed_restore(
            candidate,
            checkpoint=record,
            monotonic=monotonic,
            parse_read=parse_read,
        ),
    )
    assert error.code == expected_code
    for point in required_points:
        assert point in points
    for point in forbidden_points:
        assert point not in points
    return tuple(points)


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


@pytest.mark.parametrize("sealed", [False, True], ids=["prepared-partial", "sealed-complete"])
def test_checkpoint_round_trip_preserves_exact_capsule_tree_and_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sealed: bool,
) -> None:
    source, shard = _load_protocol_bound_shard(tmp_path, monkeypatch)
    if sealed:
        _complete_shard_capsule(source, monkeypatch)

    source_result = verify_capsule(source, mode=VerificationMode.PREPARED)
    assert source_result.status == "valid"
    assert source_result.state == ("SEALED_COMPLETE" if sealed else "PREPARED")
    assert (source / "seal.json").exists() is sealed

    provenance = _provenance(shard)
    archive_root = tmp_path / "checkpoint-output"
    archive_root.mkdir()
    archive_path = archive_root / checkpoint_archive_name(provenance)
    artifact = pack_checkpoint(source, archive_path, provenance=provenance)
    expected = _expected_bindings(
        source,
        shard,
        archive_sha256=artifact.sha256,
        provenance=provenance,
    )
    before = snapshot_tree(source)
    before_by_path = {path: (kind, mode, payload) for path, kind, mode, payload in before}
    assert before_by_path["inputs/planning"][0:2] == ("directory", 0o555)
    assert before_by_path["inputs/planning/shard-plan.json"][0:2] == ("file", 0o640)
    assert ".laconian.lock" in before_by_path
    assert ("seal.json" in before_by_path) is sealed

    restore_root = tmp_path / "restored"
    restore_root.mkdir()
    restored = restore_checkpoint(
        artifact.archive_path,
        artifact.sidecar_path,
        destination_parent=restore_root,
        destination_name=source.name,
        expected=expected,
    )

    assert restored == restore_root / source.name
    assert snapshot_tree(restored) == before
    assert verify_capsule(restored, mode=VerificationMode.PREPARED).status == "valid"


def test_restore_requires_exact_parent_shard_and_model_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, shard = _load_protocol_bound_shard(tmp_path, monkeypatch)
    provenance = _provenance(shard)
    archive_root = tmp_path / "checkpoint-output"
    archive_root.mkdir()
    archive_path = archive_root / checkpoint_archive_name(provenance)
    artifact = pack_checkpoint(source, archive_path, provenance=provenance)
    expected = _expected_bindings(
        source,
        shard,
        archive_sha256=artifact.sha256,
        provenance=provenance,
    )

    assert [field.name for field in fields(expected)] == [
        "archive_sha256",
        "manifest_sha256",
        "plan_sha256",
        "parent_plan_sha256",
        "shard_plan_sha256",
        "requested_model",
        "scenario_uid",
        "protocol_bindings",
        "provenance",
    ]
    assert not hasattr(expected, "__dict__")
    with pytest.raises(FrozenInstanceError):
        expected.scenario_uid = "f" * 64  # type: ignore[misc]
    assert tuple(binding.binding_id for binding in expected.protocol_bindings) == (
        "rubric-alpha",
        "rubric-beta",
    )
    assert tuple(binding.sha256 for binding in expected.protocol_bindings) == tuple(
        binding.sha256
        for binding in ResolvedManifestV2.model_validate_json(
            (source / "manifest.json").read_bytes()
        ).capsule.protocol_bindings
    )

    def different_digest(digest: str) -> str:
        return ("0" if digest[0] != "0" else "1") + digest[1:]

    assert len(expected.protocol_bindings) == 2
    reversed_protocols = tuple(reversed(expected.protocol_bindings))
    binding_id_mutation = (
        expected.protocol_bindings[0].model_copy(update={"binding_id": "rubric-other"}),
        expected.protocol_bindings[1],
    )
    binding_sha_mutation = (
        expected.protocol_bindings[0].model_copy(
            update={"sha256": different_digest(expected.protocol_bindings[0].sha256)}
        ),
        expected.protocol_bindings[1],
    )
    mutations = (
        (
            "archive-sha256",
            replace(expected, archive_sha256=different_digest(expected.archive_sha256)),
            "checkpoint_binding_mismatch",
        ),
        (
            "manifest-sha256",
            replace(expected, manifest_sha256=different_digest(expected.manifest_sha256)),
            "checkpoint_binding_mismatch",
        ),
        (
            "plan-sha256",
            replace(expected, plan_sha256=different_digest(expected.plan_sha256)),
            "checkpoint_binding_mismatch",
        ),
        (
            "parent-plan-sha256",
            replace(
                expected,
                parent_plan_sha256=different_digest(expected.parent_plan_sha256),
            ),
            "checkpoint_binding_mismatch",
        ),
        (
            "shard-plan-sha256",
            replace(
                expected,
                shard_plan_sha256=different_digest(expected.shard_plan_sha256),
            ),
            "checkpoint_binding_mismatch",
        ),
        (
            "requested-model",
            replace(expected, requested_model="gpt-5.6-terra"),
            "checkpoint_binding_mismatch",
        ),
        (
            "scenario-uid",
            replace(expected, scenario_uid=different_digest(expected.scenario_uid)),
            "checkpoint_binding_mismatch",
        ),
        (
            "protocol-binding-id",
            replace(expected, protocol_bindings=binding_id_mutation),
            "checkpoint_binding_mismatch",
        ),
        (
            "protocol-binding-sha",
            replace(expected, protocol_bindings=binding_sha_mutation),
            "checkpoint_binding_mismatch",
        ),
        (
            "protocol-bindings-order",
            replace(expected, protocol_bindings=reversed_protocols),
            "checkpoint_binding_mismatch",
        ),
    )

    for label, mutated, expected_code in mutations:
        destination_parent = tmp_path / f"rejected-{label}"
        destination_parent.mkdir()
        destination = destination_parent / source.name
        with pytest.raises(CheckpointError) as caught:
            restore_checkpoint(
                artifact.archive_path,
                artifact.sidecar_path,
                destination_parent=destination_parent,
                destination_name=source.name,
                expected=mutated,
            )
        assert caught.value.code == expected_code
        assert not destination.exists()


def _mutated_provenance(
    provenance: CheckpointProvenanceV1,
    field: str,
) -> CheckpointProvenanceV1:
    values: dict[str, object] = {
        "campaign_id": "different-campaign",
        "model_id": "gpt-5.6-terra",
        "scenario_uid": ("0" if provenance.scenario_uid[0] != "0" else "1")
        + provenance.scenario_uid[1:],
        "batch_attempt_id": UUID("323e4567-e89b-42d3-a456-426614174002"),
        "run_attempt": provenance.run_attempt + 1,
    }
    return provenance.model_copy(update={field: values[field]})


@pytest.mark.parametrize(
    "field",
    ["campaign_id", "model_id", "scenario_uid", "batch_attempt_id", "run_attempt"],
)
def test_restore_rejects_each_provenance_filename_binding_before_io(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    field: str,
) -> None:
    wrong_provenance = _mutated_provenance(packed_restore_baseline.expected.provenance, field)
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
        archive_basename=checkpoint_archive_name(wrong_provenance),
    )

    points = _assert_restore_rejected_at_phase(
        case,
        expected_code="checkpoint_binding_mismatch",
        forbidden_points=(
            "after_argument_validation",
            "after_destination_preflight",
            "before_sidecar_validation",
        ),
    )
    assert points == ()


@pytest.mark.parametrize("field", ["campaign_id", "model_id", "scenario_uid"])
def test_restore_rejects_deep_campaign_model_and_scenario_bindings(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    field: str,
) -> None:
    provenance = _mutated_provenance(packed_restore_baseline.expected.provenance, field)
    expected = replace(packed_restore_baseline.expected, provenance=provenance)
    if field == "model_id":
        expected = replace(expected, requested_model=provenance.model_id)
    elif field == "scenario_uid":
        expected = replace(expected, scenario_uid=provenance.scenario_uid)
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=expected,
    )

    _assert_restore_rejected_at_phase(
        case,
        expected_code="checkpoint_binding_mismatch",
        required_points=(
            "after_archive_identity_validation",
            "after_capsule_verification",
        ),
        forbidden_points=("after_binding_validation", "before_publish"),
    )


@pytest.mark.parametrize("field", ["binding_id", "sha256"])
def test_restore_rejects_independent_protocol_binding_id_and_sha_mutations(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    field: str,
) -> None:
    bindings = packed_restore_baseline.expected.protocol_bindings
    assert len(bindings) == 2
    update = (
        {"binding_id": "rubric-other"}
        if field == "binding_id"
        else {"sha256": ("0" if bindings[0].sha256[0] != "0" else "1") + bindings[0].sha256[1:]}
    )
    mutated_bindings = (bindings[0].model_copy(update=update), bindings[1])
    expected = replace(
        packed_restore_baseline.expected,
        protocol_bindings=mutated_bindings,
    )
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=expected,
    )

    _assert_restore_rejected_at_phase(
        case,
        expected_code="checkpoint_binding_mismatch",
        required_points=("after_capsule_verification",),
        forbidden_points=("after_binding_validation", "before_publish"),
    )


def _checkpoint_metrics(archive_bytes: bytes) -> dict[str, int]:
    members, _terminal_offset = _parse_raw_ustar(archive_bytes)
    regular = [member for member in members if member[1] == "0"]
    return {
        "checkpoint_archive_bytes": len(archive_bytes),
        "checkpoint_members": len(members),
        "checkpoint_directories": sum(member[1] == "5" for member in members),
        "checkpoint_file_bytes": max(member[3] for member in regular),
        "checkpoint_aggregate_file_bytes": sum(member[3] for member in regular),
        "checkpoint_path_depth": max(len(member[0].split("/")) for member in members),
    }


@pytest.mark.parametrize(
    "field",
    [
        "checkpoint_archive_bytes",
        "checkpoint_members",
        "checkpoint_directories",
        "checkpoint_file_bytes",
        "checkpoint_aggregate_file_bytes",
        "checkpoint_path_depth",
    ],
)
def test_restore_rejects_exact_minus_one_and_accepts_each_exact_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    packed_restore_baseline: _PackedRestoreBaseline,
    field: str,
) -> None:
    metric = _checkpoint_metrics(packed_restore_baseline.archive_bytes)[field]
    assert metric > 0
    exact_case = _write_raw_restore_case(
        tmp_path / "exact",
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    monkeypatch.setattr(
        checkpoint_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, **{field: metric}),
    )
    restored = _seamed_restore(exact_case)
    assert restored == exact_case.destination
    assert verify_capsule(restored, mode=VerificationMode.PREPARED).status == "valid"
    assert exact_case.sentinel.read_bytes() == exact_case.sentinel_bytes

    below_case = _write_raw_restore_case(
        tmp_path / "below",
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    monkeypatch.setattr(
        checkpoint_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, **{field: metric - 1}),
    )
    _assert_restore_rejected_at_phase(
        below_case,
        expected_code="resource_limit",
        forbidden_points=("after_binding_validation", "before_publish"),
    )


def test_restore_rejects_an_expired_deadline_and_accepts_exact_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    monkeypatch.setattr(
        checkpoint_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, checkpoint_restore_seconds=1),
    )
    exact_case = _write_raw_restore_case(
        tmp_path / "exact",
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    exact_ticks = iter((10.0, 11.0))
    restored = _seamed_restore(
        exact_case,
        monotonic=lambda: next(exact_ticks, 11.0),
    )
    assert restored == exact_case.destination
    assert verify_capsule(restored, mode=VerificationMode.PREPARED).status == "valid"

    expired_case = _write_raw_restore_case(
        tmp_path / "expired",
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    expired_ticks = iter((10.0, 11.000001))
    _assert_restore_rejected_at_phase(
        expired_case,
        expected_code="resource_limit",
        forbidden_points=("before_publish",),
        monotonic=lambda: next(expired_ticks, 11.000001),
    )


@pytest.mark.parametrize(
    ("vector", "member"),
    [
        (
            "invalid-header-checksum",
            _RawUstarMember(".laconian.lock", valid_checksum=False),
        ),
        ("non-ustar-magic", _RawUstarMember(".laconian.lock", magic=b"badar\0")),
        ("non-ustar-version", _RawUstarMember(".laconian.lock", version=b"01")),
        ("nul-regular-typeflag", _RawUstarMember(".laconian.lock", typeflag=b"\0")),
        ("pax-local-x", _RawUstarMember(".laconian.lock", typeflag=b"x")),
        ("pax-global-g", _RawUstarMember(".laconian.lock", typeflag=b"g")),
        ("gnu-long-name-L", _RawUstarMember(".laconian.lock", typeflag=b"L")),
        ("gnu-long-link-K", _RawUstarMember(".laconian.lock", typeflag=b"K")),
        ("gnu-sparse-S", _RawUstarMember(".laconian.lock", typeflag=b"S")),
        ("hard-link-1", _RawUstarMember(".laconian.lock", typeflag=b"1")),
        ("symbolic-link-2", _RawUstarMember(".laconian.lock", typeflag=b"2")),
        ("character-device-3", _RawUstarMember(".laconian.lock", typeflag=b"3")),
        ("block-device-4", _RawUstarMember(".laconian.lock", typeflag=b"4")),
        ("fifo-6", _RawUstarMember(".laconian.lock", typeflag=b"6")),
        ("contiguous-file-7", _RawUstarMember(".laconian.lock", typeflag=b"7")),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_restore_rejects_noncanonical_or_unsupported_ustar_headers(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    vector: str,
    member: _RawUstarMember,
) -> None:
    del vector
    members = list(_raw_members_from_archive(packed_restore_baseline.archive_bytes))
    ordinal = next(index for index, item in enumerate(members) if item.path == ".laconian.lock")
    members[ordinal] = member
    case = _write_raw_restore_case(
        tmp_path,
        _raw_ustar_archive(tuple(members)),
        expected_template=packed_restore_baseline.expected,
    )

    _assert_restore_rejected_at_phase(
        case,
        expected_code="source_rejected",
        required_points=("before_archive_parse",),
        forbidden_points=("after_archive_parse", "before_capsule_verification"),
        verifier_bomb=True,
    )


def _hostile_path_members(
    vector: str,
    baseline: tuple[_RawUstarMember, ...],
) -> tuple[_RawUstarMember, ...]:
    members = list(baseline)
    lock_ordinal = next(
        index for index, member in enumerate(members) if member.path == ".laconian.lock"
    )
    lock = members[lock_ordinal]
    if vector == "absolute-path":
        members[lock_ordinal] = replace(lock, path="/capsule.json")
    elif vector == "backslash":
        members[lock_ordinal] = replace(lock, path="inputs\\capsule.json")
    elif vector == "nul-in-decoded-name":
        members[lock_ordinal] = replace(lock, path=b"capsule.json\0hidden")
    elif vector == "non-utf8":
        members[lock_ordinal] = replace(lock, path=b"\xff")
    elif vector == "non-nfc":
        members[lock_ordinal] = replace(lock, path="inputs/cafe\u0301")
    elif vector == "empty-component":
        members[lock_ordinal] = replace(lock, path="inputs//planning")
    elif vector == "dot-component":
        members[lock_ordinal] = replace(lock, path="inputs/./planning")
    elif vector == "parent-component":
        members[lock_ordinal] = replace(lock, path="inputs/../capsule.json")
    if vector == "duplicate-normalized-path":
        members.insert(lock_ordinal + 1, lock)
    elif vector == "file-before-parent-directory":
        child_ordinal = next(
            index
            for index, member in enumerate(members)
            if member.path == "inputs/planning/parent-plan.jsonl"
        )
        child = members.pop(child_ordinal)
        parent_ordinal = next(
            index for index, member in enumerate(members) if member.path == "inputs"
        )
        members.insert(parent_ordinal, child)
    elif vector == "unexpected-capsule-member":
        members[lock_ordinal] = replace(lock, path="unexpected-private.bin")
    elif vector == "noncanonical-member-order":
        members[0], members[1] = members[1], members[0]
    elif vector not in {
        "absolute-path",
        "backslash",
        "nul-in-decoded-name",
        "non-utf8",
        "non-nfc",
        "empty-component",
        "dot-component",
        "parent-component",
    }:
        raise AssertionError("unknown hostile path vector")
    return tuple(members)


@pytest.mark.parametrize(
    "vector",
    [
        "absolute-path",
        "backslash",
        "nul-in-decoded-name",
        "non-utf8",
        "non-nfc",
        "empty-component",
        "dot-component",
        "parent-component",
        "duplicate-normalized-path",
        "file-before-parent-directory",
        "unexpected-capsule-member",
        "noncanonical-member-order",
    ],
)
def test_restore_rejects_hostile_noncanonical_or_unexpected_member_paths(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    vector: str,
) -> None:
    baseline_members = _raw_members_from_archive(packed_restore_baseline.archive_bytes)
    case = _write_raw_restore_case(
        tmp_path,
        _raw_ustar_archive(_hostile_path_members(vector, baseline_members)),
        expected_template=packed_restore_baseline.expected,
    )

    _assert_restore_rejected_at_phase(
        case,
        expected_code="source_rejected",
        required_points=("before_archive_parse",),
        forbidden_points=("after_archive_parse", "before_capsule_verification"),
        verifier_bomb=True,
    )


def _hostile_payload_archive(vector: str, baseline_bytes: bytes) -> bytes:
    members = list(_raw_members_from_archive(baseline_bytes))
    lock_ordinal = next(
        index for index, member in enumerate(members) if member.path == ".laconian.lock"
    )
    lock = members[lock_ordinal]
    if vector == "noncanonical-octal-field":
        members[lock_ordinal] = replace(lock, mode_field=b"0000600 ")
        return _raw_ustar_archive(tuple(members))
    if vector == "setuid-mode":
        members[lock_ordinal] = replace(lock, mode=lock.mode | stat.S_ISUID)
        return _raw_ustar_archive(tuple(members))
    if vector == "setgid-mode":
        members[lock_ordinal] = replace(lock, mode=lock.mode | stat.S_ISGID)
        return _raw_ustar_archive(tuple(members))
    if vector == "sticky-mode":
        members[lock_ordinal] = replace(lock, mode=lock.mode | stat.S_ISVTX)
        return _raw_ustar_archive(tuple(members))
    if vector == "declared-size-short-data":
        final = members[-1]
        assert final.typeflag == b"0"
        members[-1] = replace(final, payload=b"x", declared_size=4)
        return _raw_ustar_archive(
            tuple(members),
            short_final_member=True,
        )
    if vector == "nonzero-padding":
        return _raw_ustar_archive(
            tuple(members),
            padding_byte=1,
        )
    if vector == "missing-second-terminal-block":
        return _raw_ustar_archive(
            tuple(members),
            terminal_blocks=1,
        )
    if vector == "nonzero-trailer":
        return _raw_ustar_archive(
            tuple(members),
            trailer=b"x" + bytes(_BLOCK_BYTES - 1),
        )
    raise AssertionError("unknown hostile payload vector")


@pytest.mark.parametrize(
    "vector",
    [
        "noncanonical-octal-field",
        "setuid-mode",
        "setgid-mode",
        "sticky-mode",
        "declared-size-short-data",
        "nonzero-padding",
        "missing-second-terminal-block",
        "nonzero-trailer",
    ],
)
def test_restore_rejects_noncanonical_modes_sizes_padding_and_terminal_blocks(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    vector: str,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        _hostile_payload_archive(vector, packed_restore_baseline.archive_bytes),
        expected_template=packed_restore_baseline.expected,
    )

    _assert_restore_rejected_at_phase(
        case,
        expected_code="source_rejected",
        required_points=("before_archive_parse",),
        forbidden_points=("after_archive_parse", "before_capsule_verification"),
        verifier_bomb=True,
    )


def _mode_only_alternate_archive(archive_bytes: bytes) -> bytes:
    changed_members = list(_raw_members_from_archive(archive_bytes))
    changed_ordinal = next(
        index for index, member in enumerate(changed_members) if member.path == "manifest.json"
    )
    original_mode = changed_members[changed_ordinal].mode
    assert original_mode & 0o040 == 0
    changed_members[changed_ordinal] = replace(
        changed_members[changed_ordinal],
        mode=original_mode | 0o040,
    )
    return _raw_ustar_archive(tuple(changed_members))


def test_restore_accepts_semantically_valid_mode_only_transport_control(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    alternate = _mode_only_alternate_archive(packed_restore_baseline.archive_bytes)
    case = _write_raw_restore_case(
        tmp_path,
        alternate,
        expected_template=packed_restore_baseline.expected,
    )

    restored = _seamed_restore(case)

    result = verify_capsule(restored, mode=VerificationMode.PREPARED)
    assert result.status == "valid"
    assert "broader_permissions" in result.warnings
    assert case.sentinel.read_bytes() == case.sentinel_bytes


@pytest.mark.parametrize(
    "vector",
    [
        "trusted-hash-differs-from-sidecar",
        "trusted-hash-differs-from-preparse",
        "trusted-hash-differs-from-parse-pass",
        "substituted-valid-archive-and-sidecar",
        "sidecar-wrong-basename",
    ],
)
def test_restore_rejects_every_transport_hash_or_sidecar_substitution(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    vector: str,
) -> None:
    archive_a = packed_restore_baseline.archive_bytes
    archive_b = _mode_only_alternate_archive(archive_a)
    digest_a = sha256_bytes(archive_a)
    digest_b = sha256_bytes(archive_b)
    assert len(archive_a) == len(archive_b)
    assert digest_a != digest_b

    if vector == "trusted-hash-differs-from-sidecar":
        case = _write_raw_restore_case(
            tmp_path,
            archive_a,
            expected_template=packed_restore_baseline.expected,
            authority_sha256=digest_a,
            sidecar_sha256=digest_b,
        )
        _assert_restore_rejected_at_phase(
            case,
            expected_code="source_rejected",
            required_points=(
                "after_sidecar_validation",
                "before_archive_prehash",
                "after_archive_prehash",
            ),
            forbidden_points=("before_archive_parse",),
        )
        return
    if vector == "trusted-hash-differs-from-preparse":
        case = _write_raw_restore_case(
            tmp_path,
            archive_b,
            expected_template=packed_restore_baseline.expected,
            authority_sha256=digest_a,
            sidecar_sha256=digest_a,
        )
        _assert_restore_rejected_at_phase(
            case,
            expected_code="source_rejected",
            required_points=(
                "after_sidecar_validation",
                "before_archive_prehash",
                "after_archive_prehash",
            ),
            forbidden_points=("before_archive_parse",),
        )
        return
    if vector == "substituted-valid-archive-and-sidecar":
        case = _write_raw_restore_case(
            tmp_path,
            archive_b,
            expected_template=packed_restore_baseline.expected,
            authority_sha256=digest_a,
            sidecar_sha256=digest_b,
        )
        _assert_restore_rejected_at_phase(
            case,
            expected_code="checkpoint_binding_mismatch",
            required_points=(
                "after_sidecar_validation",
                "before_archive_prehash",
                "after_archive_prehash",
            ),
            forbidden_points=("before_archive_parse",),
        )
        return
    if vector == "sidecar-wrong-basename":
        case = _write_raw_restore_case(
            tmp_path,
            archive_a,
            expected_template=packed_restore_baseline.expected,
            sidecar_basename="different-checkpoint.tar",
        )
        _assert_restore_rejected_at_phase(
            case,
            expected_code="source_rejected",
            required_points=("before_sidecar_validation",),
            forbidden_points=("after_sidecar_validation", "before_archive_prehash"),
        )
        return

    case = _write_raw_restore_case(
        tmp_path,
        archive_a,
        expected_template=packed_restore_baseline.expected,
    )
    before_metadata = case.archive_path.stat()
    cursor = 0

    def parse_read(_descriptor: int, amount: int) -> bytes:
        nonlocal cursor
        chunk = archive_b[cursor : cursor + amount]
        cursor += len(chunk)
        return chunk

    _assert_restore_rejected_at_phase(
        case,
        expected_code="source_rejected",
        required_points=("after_archive_prehash", "before_archive_parse"),
        forbidden_points=("after_archive_parse", "before_capsule_verification"),
        parse_read=parse_read,
        verifier_bomb=True,
    )
    after_metadata = case.archive_path.stat()
    assert cursor == len(archive_b)
    assert case.archive_path.read_bytes() == archive_a
    assert (
        before_metadata.st_dev,
        before_metadata.st_ino,
        before_metadata.st_mode,
        before_metadata.st_size,
        before_metadata.st_mtime_ns,
        before_metadata.st_ctime_ns,
    ) == (
        after_metadata.st_dev,
        after_metadata.st_ino,
        after_metadata.st_mode,
        after_metadata.st_size,
        after_metadata.st_mtime_ns,
        after_metadata.st_ctime_ns,
    )


def test_restore_rejects_archive_identity_change_after_parse(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )

    def mutate_identity(point: str) -> None:
        if point == "after_archive_parse":
            metadata = case.archive_path.stat()
            os.utime(
                case.archive_path,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000_000),
            )

    _assert_restore_rejected_at_phase(
        case,
        expected_code="unstable_snapshot",
        required_points=("after_archive_parse",),
        forbidden_points=("after_archive_identity_validation", "before_capsule_verification"),
        checkpoint_action=mutate_identity,
    )


def test_restore_rejects_a_full_parent_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "full-parent-source"
    source_root.mkdir()
    source = _single_plan_capsule(source_root, monkeypatch)
    archive_bytes = _raw_ustar_archive(_raw_members_from_tree(source))
    case = _write_raw_restore_case(tmp_path / "full-parent-restore", archive_bytes)

    _assert_restore_rejected_at_phase(
        case,
        expected_code="source_rejected",
        required_points=(
            "after_archive_identity_validation",
            "before_capsule_verification",
            "after_capsule_verification",
        ),
        forbidden_points=("after_binding_validation", "before_publish"),
    )


@pytest.mark.parametrize(
    "field",
    ["parent_plan_sha256", "shard_plan_sha256", "scenario_uid"],
)
def test_restore_rejects_missing_mandatory_shard_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    packed_restore_baseline: _PackedRestoreBaseline,
    field: str,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    case = replace(case, expected=replace(case.expected, **{field: None}))
    real_open = os.open
    real_stat = os.stat
    accesses: list[str] = []
    points: list[str] = []

    def track_open(*args: Any, **kwargs: Any) -> int:
        accesses.append("open")
        return real_open(*args, **kwargs)

    def track_stat(*args: Any, **kwargs: Any) -> os.stat_result:
        accesses.append("stat")
        return real_stat(*args, **kwargs)

    monkeypatch.setattr(checkpoint_module.os, "open", track_open)
    monkeypatch.setattr(checkpoint_module.os, "stat", track_stat)
    try:
        with pytest.raises(CheckpointError) as caught:
            _seamed_restore(case, checkpoint=points.append)
    finally:
        monkeypatch.setattr(checkpoint_module.os, "open", real_open)
        monkeypatch.setattr(checkpoint_module.os, "stat", real_stat)

    assert caught.value.code == "invalid_argument"
    assert accesses == []
    assert points == []
    assert not case.destination.exists()
    assert case.sentinel.read_bytes() == case.sentinel_bytes


def _runner_directory_members(count: int) -> tuple[_RawUstarMember, ...]:
    parents = (
        "inputs",
        "inputs/software",
        "inputs/software/runner",
        "inputs/software/runner/laconian_eval",
    )
    siblings = tuple(
        f"inputs/software/runner/laconian_eval/d{ordinal:03d}" for ordinal in range(count)
    )
    return tuple(_RawUstarMember(path, typeflag=b"5", mode=0o700) for path in (*parents, *siblings))


def test_restore_rejects_sixty_fifth_retained_directory_under_reduced_nofile(
    tmp_path: Path,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        _raw_ustar_archive(_runner_directory_members(65)),
    )
    fork_context = multiprocessing.get_context("fork")
    receiver, sender = fork_context.Pipe(duplex=False)

    def restore_under_bound() -> None:
        try:
            _soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
            reduced = 128 if hard_limit == resource.RLIM_INFINITY else min(128, hard_limit)
            resource.setrlimit(resource.RLIMIT_NOFILE, (reduced, hard_limit))
            _public_restore(case)
        except BaseException as error:
            sender.send((type(error).__name__, getattr(error, "code", None)))
        else:
            sender.send(("unexpected-success", None))
        finally:
            sender.close()

    process = fork_context.Process(target=restore_under_bound)
    process.start()
    sender.close()
    try:
        assert receiver.poll(10.0)
        assert receiver.recv() == ("CheckpointError", "resource_limit")
        process.join(10.0)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(5.0)
        receiver.close()
    assert not case.destination.exists()
    assert case.sentinel.read_bytes() == case.sentinel_bytes


def test_restore_rejects_emfile_while_retaining_directory_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        _raw_ustar_archive(_runner_directory_members(1)),
    )
    real_open = os.open
    failed = False

    def fail_directory_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal failed
        if os.fspath(path).endswith("d000") and flags & os.O_DIRECTORY:
            failed = True
            raise OSError(errno.EMFILE, "private EMFILE canary")
        if dir_fd is None:
            return real_open(path, flags, mode)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(checkpoint_module.os, "open", fail_directory_open)

    _assert_restore_rejected_at_phase(
        case,
        expected_code="io_error",
        required_points=("before_archive_parse",),
        forbidden_points=("after_archive_parse", "before_capsule_verification"),
    )
    assert failed


def test_restore_rejects_existing_destination_without_touching_it(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    collision_bytes = b"preexisting destination must survive"
    case.destination.write_bytes(collision_bytes)
    points: list[str] = []

    with pytest.raises(CheckpointError) as caught:
        _seamed_restore(case, checkpoint=points.append)

    assert caught.value.code == "destination_collision"
    assert "after_argument_validation" in points
    assert "after_destination_preflight" not in points
    assert "before_sidecar_validation" not in points
    assert case.destination.read_bytes() == collision_bytes
    assert case.sentinel.read_bytes() == case.sentinel_bytes


def test_restore_rejects_destination_parent_identity_change_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "valid-shard-source"
    source_root.mkdir()
    source, shard = _load_protocol_bound_shard(source_root, monkeypatch)
    provenance = _provenance(shard)
    transport = tmp_path / "valid-transport"
    transport.mkdir()
    artifact = pack_checkpoint(
        source,
        transport / checkpoint_archive_name(provenance),
        provenance=provenance,
    )
    destination_parent = tmp_path / "moving-restore-parent"
    destination_parent.mkdir()
    sentinel_bytes = b"retained parent sentinel"
    sentinel = destination_parent / "unrelated.sentinel"
    sentinel.write_bytes(sentinel_bytes)
    expected = _expected_bindings(
        source,
        shard,
        archive_sha256=artifact.sha256,
        provenance=provenance,
    )
    case = _RawRestoreCase(
        archive_path=artifact.archive_path,
        sidecar_path=artifact.sidecar_path,
        destination_parent=destination_parent,
        destination_name="restored-capsule",
        destination=destination_parent / "restored-capsule",
        sentinel=sentinel,
        sentinel_bytes=sentinel_bytes,
        expected=expected,
    )
    displaced = tmp_path / "displaced-restore-parent"
    replacement_sentinel = b"replacement parent sentinel"
    points: list[str] = []

    def move_parent(point: str) -> None:
        points.append(point)
        if point == "before_publish":
            destination_parent.rename(displaced)
            destination_parent.mkdir()
            (destination_parent / "replacement.sentinel").write_bytes(replacement_sentinel)

    with pytest.raises(CheckpointError) as caught:
        _seamed_restore(case, checkpoint=move_parent)

    assert caught.value.code == "unstable_snapshot"
    assert "after_binding_validation" in points
    assert "before_publish" in points
    assert "after_publish" not in points
    assert not (destination_parent / case.destination_name).exists()
    assert not (displaced / case.destination_name).exists()
    assert (displaced / case.sentinel.name).read_bytes() == sentinel_bytes
    assert (destination_parent / "replacement.sentinel").read_bytes() == replacement_sentinel


@pytest.mark.parametrize("mutation_point", ["after_binding_validation", "before_publish"])
def test_restore_rechecks_verified_members_after_the_last_mutation_seams(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
    mutation_point: str,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    fired = False

    def mutate_verified_lock(point: str) -> None:
        nonlocal fired
        if point != mutation_point:
            return
        stages = tuple(case.destination_parent.glob(".laconian-stage.*"))
        assert len(stages) == 1
        (stages[0] / ".laconian.lock").write_bytes(b"mutated after verification")
        fired = True

    with pytest.raises(CheckpointError) as caught:
        _seamed_restore(case, checkpoint=mutate_verified_lock)

    assert caught.value.code == "source_rejected"
    assert fired
    assert not case.destination.exists()
    assert not tuple(case.destination_parent.glob(".laconian-stage.*"))
    assert case.sentinel.read_bytes() == case.sentinel_bytes


def test_restore_recovers_readonly_directories_and_uses_the_exact_cleanup_ceiling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    real_cleanup = checkpoint_module.cleanup_owned_staging
    cleanup_observations: list[tuple[int | None, int]] = []

    def inspect_cleanup(
        staging: Any,
        *,
        posix: Any,
        entry_ceiling: int | None = None,
    ) -> None:
        recovered = os.stat(
            "inputs/planning",
            dir_fd=staging.descriptor,
            follow_symlinks=False,
        )
        cleanup_observations.append((entry_ceiling, stat.S_IMODE(recovered.st_mode)))
        real_cleanup(staging, posix=posix, entry_ceiling=entry_ceiling)

    def fail_after_directory_modes(point: str) -> None:
        if point == "after_archive_parse":
            raise OSError("late restore failure canary")

    monkeypatch.setattr(checkpoint_module, "cleanup_owned_staging", inspect_cleanup)

    error = _assert_restore_rejected(
        case,
        invoke=lambda candidate: _seamed_restore(
            candidate,
            checkpoint=fail_after_directory_modes,
        ),
    )

    assert error.code == "io_error"
    assert cleanup_observations == [
        (RESOURCE_LIMITS_V1.checkpoint_members, 0o755),
    ]
    assert not tuple(case.destination_parent.glob(".laconian-stage.*"))


def test_restore_postpublication_parent_fsync_failure_keeps_the_verified_destination(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    published = False

    def record_publication(point: str) -> None:
        nonlocal published
        if point == "after_publish":
            published = True

    def fail_postpublication_fsync(descriptor: int) -> None:
        if published:
            raise OSError("postpublication fsync canary")
        os.fsync(descriptor)

    with pytest.raises(CheckpointError) as caught:
        _seamed_restore(
            case,
            checkpoint=record_publication,
            fsync=fail_postpublication_fsync,
        )

    assert caught.value.code == "checkpoint_restore_post_publish_fsync_failed"
    assert caught.value.publication_path == case.destination
    assert case.destination.is_dir()
    assert verify_capsule(case.destination, mode=VerificationMode.PREPARED).status == "valid"
    assert not tuple(case.destination_parent.glob(".laconian-stage.*"))
    assert case.sentinel.read_bytes() == case.sentinel_bytes


def test_restore_proves_an_effect_then_raise_rename_as_published(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )

    def rename_then_raise(
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        PosixOps().rename_noreplace(
            source_directory_fd,
            source_name,
            target_directory_fd,
            target_name,
        )
        raise OSError("ambiguous rename canary")

    with pytest.raises(CheckpointError) as caught:
        _seamed_restore(case, rename_noreplace=rename_then_raise)

    assert caught.value.code == "post_publish_integrity_error"
    assert caught.value.publication_path == case.destination
    assert case.destination.is_dir()
    assert verify_capsule(case.destination, mode=VerificationMode.PREPARED).status == "valid"
    assert not tuple(case.destination_parent.glob(".laconian-stage.*"))
    assert case.sentinel.read_bytes() == case.sentinel_bytes


def test_restore_rejects_a_false_successful_rename_and_removes_only_its_stage(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )

    def no_effect_rename(
        _source_directory_fd: int,
        _source_name: str,
        _target_directory_fd: int,
        _target_name: str,
    ) -> None:
        return

    error = _assert_restore_rejected(
        case,
        invoke=lambda candidate: _seamed_restore(
            candidate,
            rename_noreplace=no_effect_rename,
        ),
    )

    assert error.code == "post_publish_integrity_error"
    assert not tuple(case.destination_parent.glob(".laconian-stage.*"))


def test_restore_atomic_no_replace_preserves_a_racing_destination(
    tmp_path: Path,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    case = _write_raw_restore_case(
        tmp_path,
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )
    competitor = b"racing destination remains authoritative"

    def install_competitor_then_rename(
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        descriptor = os.open(
            target_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=target_directory_fd,
        )
        try:
            assert os.write(descriptor, competitor) == len(competitor)
        finally:
            os.close(descriptor)
        PosixOps().rename_noreplace(
            source_directory_fd,
            source_name,
            target_directory_fd,
            target_name,
        )

    with pytest.raises(CheckpointError) as caught:
        _seamed_restore(case, rename_noreplace=install_competitor_then_rename)

    assert caught.value.code == "destination_collision"
    assert caught.value.publication_path is None
    assert case.destination.read_bytes() == competitor
    assert not tuple(case.destination_parent.glob(".laconian-stage.*"))
    assert case.sentinel.read_bytes() == case.sentinel_bytes


def test_restore_does_not_leak_ambient_unread_or_private_exception_canaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    packed_restore_baseline: _PackedRestoreBaseline,
) -> None:
    canary = "RESTORE-PRIVATE-CREDENTIAL-CANARY"
    ambient_home = tmp_path / "ambient-home"
    ambient_tmp = tmp_path / "ambient-tmp"
    ambient_home.mkdir()
    ambient_tmp.mkdir()
    home_sentinel = ambient_home / "sentinel"
    tmp_sentinel = ambient_tmp / "sentinel"
    home_sentinel.write_bytes(b"home unchanged")
    tmp_sentinel.write_bytes(b"tmp unchanged")
    monkeypatch.setenv("HOME", str(ambient_home))
    monkeypatch.setenv("TMPDIR", str(ambient_tmp))
    monkeypatch.setenv("OPENAI_API_KEY", canary)

    hostile_archive = bytearray(packed_restore_baseline.archive_bytes)
    hostile_archive[257:263] = b"badbad"
    unread_offset = _BLOCK_BYTES
    hostile_archive[unread_offset : unread_offset + len(canary)] = canary.encode("ascii")
    hostile_case = _write_raw_restore_case(
        tmp_path / "hostile",
        bytes(hostile_archive),
        expected_template=packed_restore_baseline.expected,
    )
    hostile_sidecar = hostile_case.sidecar_path.read_bytes()

    hostile_error = _assert_restore_rejected(hostile_case)

    assert hostile_error.code == "source_rejected"
    assert canary not in "".join(traceback.format_exception(hostile_error))
    assert hostile_case.sidecar_path.read_bytes() == hostile_sidecar

    private_case = _write_raw_restore_case(
        tmp_path / "private-exception",
        packed_restore_baseline.archive_bytes,
        expected_template=packed_restore_baseline.expected,
    )

    class PrivateProviderRestoreError(Exception):
        pass

    def raise_private_provider_error(point: str) -> None:
        if point == "before_capsule_verification":
            raise PrivateProviderRestoreError(canary)

    seams = checkpoint_module._RestoreSeams(checkpoint=raise_private_provider_error)
    monkeypatch.setattr(checkpoint_module, "_RestoreSeams", lambda: seams)

    with pytest.raises(CheckpointError) as caught:
        _public_restore(private_case)

    private_error = caught.value
    assert private_error.code == "io_error"
    assert private_error.args == ("capsule checkpoint rejected",)
    assert private_error.__cause__ is None
    assert private_error.__context__ is None
    assert canary not in "".join(traceback.format_exception(private_error))
    assert not private_case.destination.exists()
    assert not tuple(private_case.destination_parent.glob(".laconian-stage.*"))
    assert home_sentinel.read_bytes() == b"home unchanged"
    assert tmp_sentinel.read_bytes() == b"tmp unchanged"
    assert tuple(ambient_home.iterdir()) == (home_sentinel,)
    assert tuple(ambient_tmp.iterdir()) == (tmp_sentinel,)


def test_restore_parent_probe_never_retries_an_ambiguously_closed_reused_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "restore-parent"
    parent.mkdir()
    canary = tmp_path / "reused-descriptor-canary"
    canary.write_bytes(b"still open")
    real_close = os.close
    fired = False
    retried = False
    reused_descriptor: int | None = None

    def open_parent(path: os.PathLike[str] | str) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        return os.open(path, flags)

    def ambiguous_close(descriptor: int) -> None:
        nonlocal fired, retried, reused_descriptor
        if not fired:
            fired = True
            real_close(descriptor)
            reused_descriptor = os.open(canary, os.O_RDONLY)
            assert reused_descriptor == descriptor
            raise OSError(errno.EIO, "ambiguous close canary")
        if descriptor == reused_descriptor:
            retried = True
            raise AssertionError("ambiguously closed descriptor was retried")
        real_close(descriptor)

    monkeypatch.setattr(checkpoint_module, "open_directory_no_follow", open_parent)
    monkeypatch.setattr(checkpoint_module.os, "close", ambiguous_close)

    with pytest.raises(CheckpointError) as caught:
        checkpoint_module._open_stable_parent(parent, classify=False)

    assert caught.value.code == "io_error"
    assert fired
    assert not retried
    assert reused_descriptor is not None
    assert os.fstat(reused_descriptor).st_size == len(b"still open")
    real_close(reused_descriptor)


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


@pytest.mark.parametrize(
    ("relative_path", "special_bit"),
    [
        ("manifest.json", stat.S_ISUID),
        ("manifest.json", stat.S_ISGID),
        ("inputs/planning", stat.S_ISVTX),
    ],
    ids=["setuid-file", "setgid-file", "sticky-directory"],
)
def test_pack_checkpoint_rejects_special_permission_bits(
    prepared_shard_capsule: tuple[Path, ShardPlanV1],
    tmp_path: Path,
    relative_path: str,
    special_bit: int,
) -> None:
    capsule_path, shard = prepared_shard_capsule
    target = capsule_path / relative_path
    os.chmod(target, stat.S_IMODE(target.lstat().st_mode) | special_bit)
    provenance = _provenance(shard)
    archive = tmp_path / checkpoint_archive_name(provenance)
    sentinel = tmp_path / "unrelated.sentinel"
    sentinel_bytes = b"pack special-mode sentinel"
    sentinel.write_bytes(sentinel_bytes)

    with pytest.raises(CheckpointError) as caught:
        pack_checkpoint(capsule_path, archive, provenance=provenance)

    assert caught.value.code == "source_rejected"
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()
    assert sentinel.read_bytes() == sentinel_bytes


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
