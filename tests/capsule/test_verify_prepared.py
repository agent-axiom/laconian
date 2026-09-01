from __future__ import annotations

import ast
import errno
import fcntl
import inspect
import json
import multiprocessing
import os
import platform
import shutil
import socket
import stat
from collections.abc import Iterator, Mapping
from contextlib import suppress
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
import yaml

import laconian_eval.capsule.history as history_module
import laconian_eval.capsule.prepare as prepare_module
import laconian_eval.capsule.verify as verify_module
from laconian_eval import __version__
from laconian_eval.capsule.attempts import (
    RawAttemptV2,
    derive_attempt_id,
    raw_attempt_jsonl,
    raw_record_sha256,
)
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_jsonl,
    sha256_bytes,
    stable_digest,
)
from laconian_eval.capsule.events import event_jsonl, make_event, make_prepared_event
from laconian_eval.capsule.filesystem import (
    UnsupportedFilesystemError,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    CaseIndexRowV1,
    EnvironmentV1,
    PlanRowV1,
    PreparedEventV1,
    VerifyResultV1,
)
from laconian_eval.capsule.verify import (
    VerificationMode,
    verify_capsule,
)

from .test_prepare import (
    ROOT,
    _assert_safety_barrier_untouched,
    _descriptor_path,
    _generation,
    _HarnessPosix,
    _install_harness,
    _load_success,
    _manifest_payload,
    _request,
    _write_case_file,
    _write_manifest,
)

_OTHER_DIGEST = "f" * 64

_FILE_BACKED_ARM_SOURCES = (
    "evals/baselines/caveman/SKILL.md",
    "evals/baselines/caveman/SOURCE.md",
    "LICENSES/CAVEMAN-MIT.txt",
    "skills/if/SKILL.md",
)


def _prepared_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider_kind: str = "fake",
    api_key_env: str | None = None,
) -> tuple[Path, SimpleNamespace, Path]:
    prepared, harness, source_manifest = _load_success(
        tmp_path,
        monkeypatch,
        provider_kind=provider_kind,
        api_key_env=api_key_env,
    )
    return prepared.path, SimpleNamespace(prepared=prepared, harness=harness), source_manifest


def _copy_file_backed_arm_source(tmp_path: Path) -> Path:
    source_root = tmp_path / "file-backed-arm-source"
    for relative in _FILE_BACKED_ARM_SOURCES:
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return source_root


def _prepare_all_input_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Any]:
    input_root = tmp_path / "all-role-inputs"
    _write_case_file(input_root / "cases/response.yaml")
    replay = input_root / "provider/replay.yaml"
    replay.parent.mkdir(parents=True)
    replay.write_bytes(b"schema_version: '1'\nresponses: {}\n")
    protocol = input_root / "protocols/rubric.bin"
    protocol.parent.mkdir(parents=True)
    protocol.write_bytes(b"exact protocol bytes\x00")
    manifest_root = tmp_path / "all-role-manifest"
    manifest_root.mkdir()
    manifest = manifest_root / "manifest.yaml"
    manifest.write_bytes(
        yaml.safe_dump(
            _manifest_payload(
                provider_kind="replay",
                replay_file="provider/replay.yaml",
                arms=["baseline", "concise", "caveman", "if"],
                comparisons=[
                    {
                        "comparison_id": "if-vs-concise",
                        "left_arm": "if",
                        "right_arm": "concise",
                        "role": "primary",
                    }
                ],
                protocol_bindings=[
                    {
                        "binding_id": "fixture/rubric-v1",
                        "kind": "org.example/rubric",
                        "schema_id": "org.example/rubric/v1",
                        "media_type": "application/octet-stream",
                        "path": "protocols/rubric.bin",
                        "scope": {
                            "dataset_ids": ["prepare-dataset"],
                            "comparison_ids": ["if-vs-concise"],
                        },
                        "bound_at_stage": "pre_generation",
                        "applies_at": ["scoring", "publication"],
                        "declared_requirement": "required_for_declared_claim",
                    }
                ],
            ),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    results_root = tmp_path / "all-role-results"
    results_root.mkdir()
    harness = _install_harness(monkeypatch, results_root)
    source_root = _copy_file_backed_arm_source(tmp_path)
    prepared = prepare_module.prepare_capsule(
        _request(
            manifest,
            results_root,
            input_root=input_root,
            source_root=source_root,
        )
    )
    source_root.rename(source_root.with_name("file-backed-arm-source-removed"))
    return prepared.path, harness


def _json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def _jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_bytes().splitlines():
        loaded = json.loads(raw)
        assert isinstance(loaded, dict)
        rows.append(loaded)
    return rows


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_bytes(canonical_json(dict(payload)))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_bytes(canonical_jsonl(rows))


def _runtime_fingerprint(environment: dict[str, Any]) -> str:
    runtime = environment["runtime"]
    provider = environment["provider"]
    assert isinstance(runtime, dict)
    assert isinstance(provider, dict)
    return stable_digest(
        "laconian-runtime-v1",
        {
            "package_version": environment["package_version"],
            "runner_source_sha256": environment["runner_source_sha256"],
            "dependencies": runtime["dependencies"],
            "import_environment": runtime["import_environment"],
            "adapter_source_sha256": provider["adapter_source_sha256"],
        },
    )


def _runner_source_root(index: dict[str, Any]) -> str:
    return stable_digest(
        "laconian-runner-source-v1",
        {"package_name": "laconian-eval", "files": index["files"]},
    )


def _adapter_root(index: dict[str, Any], provider_kind: str) -> str:
    files = index["files"]
    assert isinstance(files, list)
    by_path = {item["path"]: item for item in files}
    return stable_digest(
        "laconian-adapter-source-v1",
        {
            "provider_kind": provider_kind,
            "files": [
                by_path["providers/__init__.py"],
                by_path[f"providers/{provider_kind}.py"],
            ],
        },
    )


def _refresh_index_manifest(root: Path) -> None:
    index_path = root / "inputs/index.json"
    index = _json_object(index_path)
    index["manifest_sha256"] = sha256_bytes((root / "manifest.json").read_bytes())
    _write_json(index_path, index)


def _recommit_case_bytes(root: Path, *, relative: str, data: bytes) -> None:
    (root / relative).write_bytes(data)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    changed_record = next(record for record in records if record["capsule_path"] == relative)
    changed_record["byte_length"] = len(data)
    changed_record["sha256"] = sha256_bytes(data)
    _write_json(root / "inputs/index.json", index)

    manifest = _json_object(root / "manifest.json")
    declarations = manifest["capsule"]
    assert isinstance(declarations, dict)
    datasets = declarations["datasets"]
    assert isinstance(datasets, list)
    for dataset in datasets:
        assert isinstance(dataset, dict)
        source_ordinals = dataset["case_file_ordinals"]
        assert isinstance(source_ordinals, list)
        members = []
        for source_ordinal in sorted(source_ordinals):
            record = next(
                item
                for item in records
                if item["role"] == "case"
                and item["dataset_id"] == dataset["dataset_id"]
                and item["role_ordinal"] == source_ordinal
            )
            members.append(
                {
                    "source_ordinal": source_ordinal,
                    "capsule_path": record["capsule_path"],
                    "byte_length": record["byte_length"],
                    "sha256": record["sha256"],
                }
            )
        dataset["dataset_content_sha256"] = stable_digest(
            "laconian-dataset-content-v1",
            {
                "dataset_id": dataset["dataset_id"],
                "dataset_version": dataset["dataset_version"],
                "members": members,
            },
        )
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)
    _refresh_capsule_and_event(root)


def _refresh_capsule_and_event(root: Path, *, sync_manifest_identity: bool = True) -> None:
    capsule_path = root / "capsule.json"
    capsule = _json_object(capsule_path)
    manifest = _json_object(root / "manifest.json")
    runner_index = _json_object(root / "inputs/software/runner-source.json")
    if sync_manifest_identity:
        capsule.update(
            {
                "runner_version": manifest["runner_version"],
                "run_purpose": manifest["capsule"]["run_purpose"],
                "claim_intent": manifest["capsule"]["claim_intent"],
                "schedule_algorithm_version": manifest["schedule_algorithm_version"],
                "arm_order_seed": manifest["arm_order_seed"],
            }
        )
    capsule.update(
        {
            "manifest_sha256": sha256_bytes((root / "manifest.json").read_bytes()),
            "input_index_sha256": sha256_bytes((root / "inputs/index.json").read_bytes()),
            "case_index_sha256": sha256_bytes((root / "case-index.jsonl").read_bytes()),
            "plan_sha256": sha256_bytes((root / "plan.jsonl").read_bytes()),
            "environment_sha256": sha256_bytes((root / "environment.json").read_bytes()),
            "runner_source_sha256": runner_index["runner_source_sha256"],
        }
    )
    _write_json(capsule_path, capsule)

    checked = CapsuleV1.model_validate_json(capsule_path.read_bytes())
    old_event = PreparedEventV1.model_validate_json(
        (root / "events.jsonl").read_bytes().removesuffix(b"\n")
    )
    event = make_prepared_event(
        run_id=checked.run_id,
        operation_id=old_event.operation_id,
        occurred_at=checked.created_at,
        manifest_sha256=checked.manifest_sha256,
        input_index_sha256=checked.input_index_sha256,
        case_index_sha256=checked.case_index_sha256,
        plan_sha256=checked.plan_sha256,
        environment_sha256=checked.environment_sha256,
        runner_source_sha256=checked.runner_source_sha256,
    )
    (root / "events.jsonl").write_bytes(event_jsonl(event))


def _snapshot(root: Path) -> dict[str, tuple[int, int, int, int, int, bytes | None]]:
    root_metadata = root.lstat()
    snapshot: dict[str, tuple[int, int, int, int, int, bytes | None]] = {
        ".": (
            root_metadata.st_ino,
            root_metadata.st_mode,
            root_metadata.st_size,
            root_metadata.st_mtime_ns,
            root_metadata.st_ctime_ns,
            None,
        )
    }
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            data = path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None
            snapshot[relative] = (
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
                data,
            )
    return snapshot


def _assert_invalid(
    result: VerifyResultV1,
    *,
    code: str | None = None,
    path: str | object | None = ...,
    sequence: int | object | None = ...,
) -> None:
    assert result.status == "invalid"
    assert result.run_id is None
    assert result.state is None
    assert result.capsule_sha256 is None
    assert result.missing_plan_item_ids == ()
    assert result.operational_blocker_codes == ()
    assert result.warnings == ()
    assert result.first_error is not None
    if code is not None:
        assert result.first_error.code == code
    if path is not ...:
        assert result.first_error.path == path
    if sequence is not ...:
        assert result.first_error.sequence == sequence
    assert result.first_error.explanation.strip()
    assert len(result.first_error.explanation.encode("utf-8")) <= 4096


def _hold_exclusive_lock(lock_path: str, ready: Any, release: Any) -> None:
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        ready.set()
        if not release.wait(10.0):
            os._exit(2)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _install_artifact_inspection_bombs(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
) -> list[int]:
    real_open = os.open
    lock_descriptors: list[int] = []

    def inspection_bomb(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("busy/unsupported verifier inspected capsule artifacts")

    def guarded_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        raw = os.fspath(path)
        if raw == ".laconian.lock":
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            lock_descriptors.append(descriptor)
            return descriptor
        if dir_fd is not None:
            parent = _descriptor_path(dir_fd)
            if parent is not None:
                with suppress(ValueError):
                    parent.relative_to(root)
                    raise AssertionError("busy/unsupported verifier opened a capsule artifact")
        if type(raw) is str and raw != os.fspath(root) and raw.startswith(f"{root}{os.sep}"):
            raise AssertionError("busy/unsupported verifier used an absolute artifact path")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(verify_module.os, "open", guarded_open)
    monkeypatch.setattr(verify_module.os, "scandir", inspection_bomb)
    return lock_descriptors


class _TrackedSharedLock:
    def __init__(self, wrapped: Any, held: list[bool], close_calls: list[int]) -> None:
        self.descriptor = wrapped.descriptor
        self._wrapped = wrapped
        self._held = held
        self._close_calls = close_calls

    def close(self) -> None:
        self._close_calls.append(self.descriptor)
        assert self._held == [True]
        self._wrapped.close()
        self._held[0] = False

    def __enter__(self) -> _TrackedSharedLock:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object | None,
    ) -> None:
        self.close()


class _AmbiguousCloseLock:
    def __init__(self, wrapped: Any, close_calls: list[int], secret: str) -> None:
        self.descriptor = wrapped.descriptor
        self._wrapped = wrapped
        self._close_calls = close_calls
        self._secret = secret

    def close(self) -> None:
        self._close_calls.append(self.descriptor)
        self._wrapped.close()
        raise OSError(errno.EIO, self._secret)

    def __enter__(self) -> _AmbiguousCloseLock:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object | None,
    ) -> None:
        self.close()


def test_verification_mode_and_public_signature_are_exact() -> None:
    assert list(VerificationMode) == [VerificationMode.PREPARED]
    assert VerificationMode.PREPARED.value == "prepared"
    assert (
        str(inspect.signature(verify_capsule))
        == "(path: 'Path', *, mode: 'VerificationMode') -> 'VerifyResultV1'"
    )


def test_valid_prepared_capsule_returns_the_exact_canonical_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    before = _snapshot(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    plan_ids = tuple(
        sorted(
            (row["plan_item_id"] for row in _jsonl_objects(root / "plan.jsonl")),
            key=lambda value: value.encode("utf-8"),
        )
    )
    assert result == VerifyResultV1.model_validate(
        {
            "schema_version": "1",
            "status": "valid",
            "run_id": fixture.prepared.run_id,
            "state": "PREPARED",
            "capsule_sha256": None,
            "missing_plan_item_ids": plan_ids,
            "operational_blocker_codes": ["never_started"],
            "warnings": [],
            "first_error": None,
        }
    )
    encoded = canonical_json(result.model_dump(mode="json"))
    assert VerifyResultV1.model_validate_json(encoded) == result
    assert not encoded.endswith(b"\n")
    assert _snapshot(root) == before
    _assert_safety_barrier_untouched(fixture.harness)


def test_prepared_verification_is_independent_of_directory_name_source_checkout_and_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, fixture, source_manifest = _prepared_fixture(tmp_path, monkeypatch)
    renamed = root.with_name("transport-copy-without-run-id")
    root.rename(renamed)
    removed_source = source_manifest.parent.with_name("source-removed-from-verifier")
    source_manifest.parent.rename(removed_source)
    unrelated = tmp_path / "unrelated-cwd"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    result = verify_capsule(renamed, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert result.run_id == fixture.prepared.run_id
    assert result.state == "PREPARED"
    assert result.first_error is None
    _assert_safety_barrier_untouched(fixture.harness)


@pytest.mark.parametrize(
    ("producer_version", "expected_warnings"),
    [
        (__version__, ()),
        ("999.0.0-compatible-producer", ("producer_runtime_differs",)),
    ],
)
def test_coherent_same_or_future_version_runner_source_drift_remains_read_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    producer_version: str,
    expected_warnings: tuple[str, ...],
) -> None:
    root, fixture, source_manifest = _prepared_fixture(tmp_path, monkeypatch)
    manifest = _json_object(root / "manifest.json")
    manifest["runner_version"] = producer_version
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)

    runner_path = root / "inputs/software/runner/laconian_eval/providers/fake.py"
    runner_bytes = b'"""Future compatible captured fake adapter."""\n'
    runner_path.write_bytes(runner_bytes)
    input_index = _json_object(root / "inputs/index.json")
    input_records = input_index["files"]
    assert isinstance(input_records, list)
    indexed_runner = next(
        item for item in input_records if item["capsule_path"].endswith("providers/fake.py")
    )
    indexed_runner["byte_length"] = len(runner_bytes)
    indexed_runner["sha256"] = sha256_bytes(runner_bytes)
    _write_json(root / "inputs/index.json", input_index)

    runner_index = _json_object(root / "inputs/software/runner-source.json")
    runner_records = runner_index["files"]
    assert isinstance(runner_records, list)
    runner_record = next(item for item in runner_records if item["path"] == "providers/fake.py")
    runner_record["byte_length"] = len(runner_bytes)
    runner_record["sha256"] = sha256_bytes(runner_bytes)
    runner_index["runner_source_sha256"] = _runner_source_root(runner_index)
    _write_json(root / "inputs/software/runner-source.json", runner_index)

    environment = _json_object(root / "environment.json")
    environment["package_version"] = producer_version
    environment["runner_source_sha256"] = runner_index["runner_source_sha256"]
    provider = environment["provider"]
    runtime = environment["runtime"]
    assert isinstance(provider, dict)
    assert isinstance(runtime, dict)
    provider["adapter_source_sha256"] = _adapter_root(runner_index, "fake")
    runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
    _write_json(root / "environment.json", environment)
    assert fixture.harness.captured_inputs is not None
    case_index = tuple(
        CaseIndexRowV1.model_validate(row) for row in _jsonl_objects(root / "case-index.jsonl")
    )
    parent_plan = prepare_module.materialize_parent_plan(
        parent_manifest_sha256=sha256_bytes((root / "manifest.json").read_bytes()),
        resolved_manifest=ResolvedManifestV2.model_validate(manifest),
        case_index=case_index,
        captured_arms=fixture.harness.captured_inputs.arms,
    )
    _write_jsonl(
        root / "plan.jsonl",
        [row.model_dump(mode="json") for row in parent_plan],
    )
    _refresh_capsule_and_event(root)

    removed_source = source_manifest.parent.with_name("producer-checkout-removed")
    source_manifest.parent.rename(removed_source)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert result.run_id == fixture.prepared.run_id
    assert result.warnings == expected_warnings
    assert result.first_error is None
    _assert_safety_barrier_untouched(fixture.harness)


def test_broader_owned_permissions_are_a_warning_not_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    os.chmod(root, 0o755)
    os.chmod(root / "manifest.json", 0o644)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert result.warnings == ("broader_permissions",)
    assert result.first_error is None


def test_cross_os_permission_representation_warning_uses_fixed_display_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    environment = _json_object(root / "environment.json")
    runtime = environment["runtime"]
    assert isinstance(runtime, dict)
    runtime["os_family"] = "Linux" if platform.system() != "Linux" else "Darwin"
    runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
    _write_json(root / "environment.json", environment)
    _refresh_capsule_and_event(root)
    os.chmod(root, 0o755)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert result.warnings == ("broader_permissions", "permission_representation_differs")
    assert result.first_error is None


@pytest.mark.parametrize("omitted_role", ["arm", "case", "replay", "protocol"])
def test_full_dynamic_tree_survives_source_removal_and_rejects_declared_omission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    omitted_role: str,
) -> None:
    input_root = tmp_path / "input-root"
    _write_case_file(input_root / "cases/response.yaml")
    second_case_path = input_root / "cases/response-two.yaml"
    second_case_path.write_bytes(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "kind": "response",
                "cases": [
                    {
                        "id": "prepare-002-en",
                        "scenario_id": "prepare-002",
                        "locale": "en",
                        "category": "direct",
                        "prompt": "Second English prompt.",
                    },
                    {
                        "id": "prepare-002-ru",
                        "scenario_id": "prepare-002",
                        "locale": "ru",
                        "category": "direct",
                        "prompt": "Второй русский запрос.",
                    },
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    replay_path = input_root / "provider/replay.yaml"
    replay_path.parent.mkdir(parents=True)
    replay_path.write_bytes(b"schema_version: '1'\nresponses: {}\n")
    protocol_path = input_root / "protocols/rubric.bin"
    protocol_path.parent.mkdir(parents=True)
    protocol_path.write_bytes(b"exact protocol bytes\x00")
    manifest_root = tmp_path / "manifest-root"
    manifest_root.mkdir()
    manifest = manifest_root / "manifest.yaml"
    manifest.write_bytes(
        yaml.safe_dump(
            _manifest_payload(
                provider_kind="replay",
                replay_file="provider/replay.yaml",
                case_files=["cases/response.yaml", "cases/response-two.yaml"],
                arms=["baseline", "concise", "caveman", "if"],
                datasets=[
                    {
                        "dataset_id": "prepare-dataset",
                        "dataset_version": "fixture-v1",
                        "role": "smoke",
                        "case_schema_version": "1",
                        "case_file_ordinals": [0, 1],
                    }
                ],
                comparisons=[
                    {
                        "comparison_id": "if-vs-concise",
                        "left_arm": "if",
                        "right_arm": "concise",
                        "role": "primary",
                    }
                ],
                protocol_bindings=[
                    {
                        "binding_id": "fixture/rubric-v1",
                        "kind": "org.example/rubric",
                        "schema_id": "org.example/rubric/v1",
                        "media_type": "application/octet-stream",
                        "path": "protocols/rubric.bin",
                        "scope": {
                            "dataset_ids": ["prepare-dataset"],
                            "comparison_ids": ["if-vs-concise"],
                        },
                        "bound_at_stage": "pre_generation",
                        "applies_at": ["scoring", "publication"],
                        "declared_requirement": "required_for_declared_claim",
                    }
                ],
            ),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(monkeypatch, results_root)
    source_root = _copy_file_backed_arm_source(tmp_path)
    prepared = prepare_module.prepare_capsule(
        _request(
            manifest,
            results_root,
            input_root=input_root,
            source_root=source_root,
        )
    )
    removed_source = source_root.with_name("file-backed-arm-source-removed")
    source_root.rename(removed_source)

    result = verify_capsule(prepared.path, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    index = _json_object(prepared.path / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    assert {record["role"] for record in records} == {
        "case",
        "arm",
        "replay",
        "protocol",
        "runner_source",
    }
    if omitted_role == "arm":
        omitted_records = [
            record
            for record in records
            if record["role"] == "arm" and record["logical_locator"] == "arm[if]/SKILL.md"
        ]
    elif omitted_role == "case":
        omitted_records = [
            record for record in records if record["role"] == "case" and record["role_ordinal"] == 1
        ]
    else:
        omitted_records = [record for record in records if record["role"] == omitted_role]
    assert len(omitted_records) == 1
    omitted_relative = omitted_records[0]["capsule_path"]
    assert isinstance(omitted_relative, str)
    (prepared.path / omitted_relative).rename(tmp_path / f"removed-{omitted_role}.bin")
    index["files"] = [record for record in records if record not in omitted_records]
    _write_json(prepared.path / "inputs/index.json", index)
    _refresh_capsule_and_event(prepared.path)
    invalid = verify_capsule(prepared.path, mode=VerificationMode.PREPARED)
    _assert_invalid(invalid, code="missing_path", path=omitted_relative)
    _assert_safety_barrier_untouched(harness)


def test_arm_role_ordinals_are_bound_to_resolved_manifest_arm_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    arm_records = [record for record in records if record["role"] == "arm"]
    assert {record["role_ordinal"] for record in arm_records} == {0, 1}
    for record in arm_records:
        record["role_ordinal"] = 1 - record["role_ordinal"]
    _write_json(root / "inputs/index.json", index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="inputs/index.json")


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("byte_length", 999),
        ("sha256", _OTHER_DIGEST),
    ],
)
def test_protocol_binding_metadata_is_bound_manifest_to_index_and_captured_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: str | int,
) -> None:
    root, harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    manifest = _json_object(root / "manifest.json")
    capsule_declarations = manifest["capsule"]
    assert isinstance(capsule_declarations, dict)
    bindings = capsule_declarations["protocol_bindings"]
    assert isinstance(bindings, list) and len(bindings) == 1
    bindings[0][field] = replacement
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="manifest.json")
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize("role", ["case", "arm", "replay", "protocol", "runner_source"])
def test_every_indexed_input_role_recomputes_exact_same_length_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    root, harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)

    def selected(record: dict[str, Any]) -> bool:
        if record["role"] != role:
            return False
        if role == "arm":
            return record["logical_locator"] == "arm[if]/SKILL.md"
        if role == "runner_source":
            return record["capsule_path"].endswith("providers/replay.py")
        return True

    record = next(item for item in records if selected(item))
    relative = record["capsule_path"]
    assert isinstance(relative, str)
    path = root / relative
    original = path.read_bytes()
    assert original
    changed = bytes([original[0] ^ 1]) + original[1:]
    assert len(changed) == record["byte_length"]
    path.write_bytes(changed)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="hash_mismatch", path=relative)
    _assert_safety_barrier_untouched(harness)


def test_input_index_declared_byte_length_is_checked_independently_of_its_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    record = next(item for item in records if item["capsule_path"] == "inputs/cases/000.yaml")
    record["byte_length"] += 1
    _write_json(root / "inputs/index.json", index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="hash_mismatch", path="inputs/cases/000.yaml")


def test_complete_input_index_rejects_a_coherent_arm_not_selected_by_the_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    relative = "inputs/arms/if/SKILL.md"
    content = (ROOT / "skills/if/SKILL.md").read_bytes()
    path = root / relative
    path.parent.mkdir()
    path.write_bytes(content)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    records.append(
        {
            "role": "arm",
            "role_ordinal": 2,
            "logical_locator": "arm[if]/SKILL.md",
            "capsule_path": relative,
            "byte_length": len(content),
            "sha256": sha256_bytes(content),
            "dataset_id": None,
            "binding_id": None,
        }
    )
    index["files"] = sorted(records, key=lambda item: item["capsule_path"].encode("utf-8"))
    _write_json(root / "inputs/index.json", index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="inputs/index.json")


@pytest.mark.parametrize(
    ("mutation", "expected_code", "expected_path"),
    [
        ("unexpected", "unexpected_path", "aaa-unexpected"),
        ("nested-unexpected", "unexpected_path", "inputs/aaa-unexpected"),
        ("empty-directory", "unexpected_path", "inputs/aaa-empty"),
        ("missing", "missing_path", "manifest.json"),
        ("symlink", "unsafe_path_type", "manifest.json"),
        ("intermediate-symlink", "unsafe_path_type", "inputs/cases"),
        ("directory", "unsafe_path_type", "manifest.json"),
        ("socket", "unsafe_path_type", "raw.jsonl"),
    ],
)
def test_structure_requires_the_exact_dynamic_regular_nofollow_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
    expected_path: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    unsafe_socket: socket.socket | None = None
    if mutation == "unexpected":
        (root / "zzz-unexpected").write_bytes(b"later")
        (root / "aaa-unexpected").write_bytes(b"first")
    elif mutation == "nested-unexpected":
        (root / "inputs/zzz-unexpected").write_bytes(b"later")
        (root / "inputs/aaa-unexpected").write_bytes(b"first")
    elif mutation == "empty-directory":
        (root / "inputs/aaa-empty").mkdir()
    elif mutation == "missing":
        (root / "manifest.json").rename(tmp_path / "saved-manifest.json")
    elif mutation == "symlink":
        target = tmp_path / "saved-manifest.json"
        (root / "manifest.json").rename(target)
        (root / "manifest.json").symlink_to(target)
    elif mutation == "intermediate-symlink":
        target = tmp_path / "saved-cases"
        (root / "inputs/cases").rename(target)
        (root / "inputs/cases").symlink_to(target, target_is_directory=True)
    elif mutation == "directory":
        (root / "manifest.json").rename(tmp_path / "saved-manifest.json")
        (root / "manifest.json").mkdir()
    else:
        (root / "raw.jsonl").unlink()
        unsafe_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        prior_cwd = Path.cwd()
        try:
            os.chdir(root)
            unsafe_socket.bind("raw.jsonl")
        finally:
            os.chdir(prior_cwd)
    before = _snapshot(root)

    try:
        result = verify_capsule(root, mode=VerificationMode.PREPARED)
    finally:
        if unsafe_socket is not None:
            unsafe_socket.close()

    _assert_invalid(result, code=expected_code, path=expected_path)
    if unsafe_socket is None:
        assert _snapshot(root) == before


def test_artifact_traversal_is_descriptor_relative_and_scandir_receives_only_descriptors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    real_scandir = os.scandir
    real_open = os.open
    real_fstat = os.fstat
    real_close = os.close
    scandir_arguments: list[int] = []
    expected_snapshot = _snapshot(root)
    expected_regular_paths = {
        path
        for path, metadata in expected_snapshot.items()
        if metadata[-1] is not None and path != ".laconian.lock"
    }
    expected_descendant_paths = set(expected_snapshot) - {"."}
    resolved_root = root.resolve(strict=True)
    root_target_opens: list[int] = []
    descendant_opens: list[str] = []
    active_regular: dict[int, tuple[str, int, list[int]]] = {}
    completed_regular: list[tuple[str, int, list[int]]] = []

    def descriptor_scandir(path: int) -> Any:
        assert type(path) is int
        scandir_arguments.append(path)
        return real_scandir(path)

    def descriptor_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        raw = os.fspath(path)
        if type(raw) is bytes:
            assert raw.startswith(b".laconian-verify-")
            assert dir_fd is not None
            return real_open(path, flags, mode, dir_fd=dir_fd)
        assert type(raw) is str
        if dir_fd is None:
            if raw not in {"/", ".", "/var/tmp", "/private/tmp", "/tmp"}:
                absolute = Path(raw)
                assert absolute.is_absolute()
                with pytest.raises(ValueError):
                    absolute.relative_to(resolved_root)
        else:
            assert type(dir_fd) is int
            assert raw not in {"", ".", ".."}
            assert "/" not in raw and "\\" not in raw
            parent = _descriptor_path(dir_fd)
            assert parent is not None
            target = parent / raw
            if target == resolved_root:
                root_target_opens.append(dir_fd)
            else:
                try:
                    relative = target.relative_to(resolved_root).as_posix()
                except ValueError:
                    assert target in resolved_root.parents
                else:
                    assert relative in expected_descendant_paths
                    descendant_opens.append(relative)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        metadata = real_fstat(descriptor)
        if stat.S_ISREG(metadata.st_mode) and raw != ".laconian.lock":
            descriptor_path = _descriptor_path(descriptor)
            assert descriptor_path is not None
            try:
                relative = descriptor_path.relative_to(root).as_posix()
            except ValueError:
                pass
            else:
                assert flags & os.O_NOFOLLOW
                assert flags & os.O_NONBLOCK
                assert flags & os.O_ACCMODE == os.O_RDONLY
                if getattr(os, "O_CLOEXEC", 0):
                    assert flags & os.O_CLOEXEC
                active_regular[descriptor] = (relative, flags, [])
        return descriptor

    def descriptor_fstat(descriptor: int) -> os.stat_result:
        if descriptor in active_regular:
            active_regular[descriptor][2].append(descriptor)
        return real_fstat(descriptor)

    def descriptor_close(descriptor: int) -> None:
        generation = active_regular.pop(descriptor, None)
        if generation is not None:
            completed_regular.append(generation)
        real_close(descriptor)

    def path_bomb(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("path-based artifact traversal or read")

    monkeypatch.setattr(verify_module.os, "scandir", descriptor_scandir)
    monkeypatch.setattr(verify_module.os, "open", descriptor_open)
    monkeypatch.setattr(verify_module.os, "fstat", descriptor_fstat)
    monkeypatch.setattr(verify_module.os, "close", descriptor_close)
    monkeypatch.setattr(Path, "read_bytes", path_bomb)
    monkeypatch.setattr(Path, "rglob", path_bomb)
    monkeypatch.setattr(Path, "iterdir", path_bomb)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert scandir_arguments
    assert len(root_target_opens) == 1
    assert set(descendant_opens) == expected_descendant_paths
    assert not active_regular
    assert {path for path, _flags, _fstats in completed_regular} == expected_regular_paths
    assert all(len(fstats) >= 2 for _path, _flags, fstats in completed_regular)


def test_same_descriptor_metadata_change_during_read_is_an_unstable_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    manifest_path = root / "manifest.json"
    original = manifest_path.read_bytes()
    replacement = bytes([original[0] ^ 1]) + original[1:]
    assert len(replacement) == len(original)
    real_read = os.read
    mutated: list[int] = []

    def mutate_after_manifest_read(descriptor: int, size: int) -> bytes:
        data = real_read(descriptor, size)
        descriptor_path = _descriptor_path(descriptor)
        if data and not mutated and descriptor_path == manifest_path:
            manifest_path.write_bytes(replacement)
            mutated.append(descriptor)
        return data

    monkeypatch.setattr(verify_module.os, "read", mutate_after_manifest_read)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert len(mutated) == 1
    _assert_invalid(result, code="unstable_snapshot", path="manifest.json")
    assert manifest_path.read_bytes() == replacement


def test_root_symlink_is_never_followed_or_reported_as_a_host_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    alias = tmp_path / "capsule-alias"
    alias.symlink_to(root, target_is_directory=True)

    result = verify_capsule(alias, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="unsafe_path_type", path=None)
    assert os.fspath(root) not in result.first_error.explanation  # type: ignore[union-attr]


def test_hostile_artifact_oserror_is_sanitized_to_one_relative_io_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    before = _snapshot(root)
    real_open = os.open
    resolved_root = root.resolve(strict=True)
    secret = "credential=TOP-SECRET host=/private/producer/source"

    def hostile_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if os.fspath(path) == "manifest.json" and dir_fd is not None:
            parent = _descriptor_path(dir_fd)
            if parent == resolved_root:
                raise OSError(errno.EIO, secret)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(verify_module.os, "open", hostile_open)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="io_error", path="manifest.json")
    rendered = canonical_json(result.model_dump(mode="json"))
    assert b"TOP-SECRET" not in rendered
    assert b"/private/producer/source" not in rendered
    assert _snapshot(root) == before


def test_non_utf8_capsule_member_is_content_free_and_never_exposes_a_host_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(
                b"\xff-TOP-SECRET",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=root_fd,
            )
        except OSError as error:
            if error.errno in {errno.EILSEQ, errno.EINVAL, errno.ENOTSUP}:
                pytest.skip("filesystem cannot create a non-UTF-8 test filename")
            raise
        assert descriptor is not None
        assert os.write(descriptor, b"private bytes") == len(b"private bytes")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(root_fd)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="unexpected_path", path=None)
    rendered = canonical_json(result.model_dump(mode="json"))
    assert b"TOP-SECRET" not in rendered


@pytest.mark.parametrize(
    ("relative", "mutate"),
    [
        ("capsule.json", "unsorted"),
        ("manifest.json", "trailing-lf"),
        ("environment.json", "unsorted"),
        ("inputs/index.json", "unsorted"),
        ("inputs/software/runner-source.json", "unsorted"),
        ("case-index.jsonl", "missing-lf"),
        ("plan.jsonl", "blank-line"),
        ("events.jsonl", "missing-lf"),
    ],
)
def test_every_json_and_jsonl_artifact_requires_exact_canonical_bytes_and_framing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    mutate: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    path = root / relative
    original = path.read_bytes()
    if mutate == "trailing-lf":
        path.write_bytes(original + b"\n")
    elif mutate == "missing-lf":
        path.write_bytes(original.removesuffix(b"\n"))
    elif mutate == "blank-line":
        path.write_bytes(b"\n" + original)
    else:
        payload = _json_object(path)
        path.write_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="noncanonical_json", path=relative)


def test_strict_models_reject_unknown_fields_and_future_schema_is_classified_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    capsule = _json_object(root / "capsule.json")
    secret = "TOP-SECRET credential at /private/producer/source"
    capsule["unknown"] = secret
    _write_json(root / "capsule.json", capsule)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)
    _assert_invalid(result, code="invalid_model", path="capsule.json")
    rendered = canonical_json(result.model_dump(mode="json"))
    assert secret.encode("utf-8") not in rendered
    assert b"/private/producer/source" not in rendered

    capsule.pop("unknown")
    capsule["capsule_schema_version"] = "999"
    _write_json(root / "capsule.json", capsule)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)
    _assert_invalid(result, code="unsupported_schema", path="capsule.json")


def test_same_model_failures_follow_displayed_field_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    capsule = _json_object(root / "capsule.json")
    capsule["capsule_schema_version"] = "999"
    capsule["runner_version"] = ""
    capsule["manifest_sha256"] = "not-a-digest"
    _write_json(root / "capsule.json", capsule)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="unsupported_schema", path="capsule.json")


@pytest.mark.parametrize(
    "relative",
    [
        "manifest.json",
        "environment.json",
        "inputs/index.json",
        "inputs/software/runner-source.json",
        "case-index.jsonl",
        "plan.jsonl",
        "events.jsonl",
    ],
)
def test_every_strict_artifact_model_rejects_an_unknown_field_without_echo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    secret = "TOP-SECRET credential at /private/producer/source"
    path = root / relative
    if relative.endswith(".jsonl"):
        rows = _jsonl_objects(path)
        rows[0]["unknown"] = secret
        if relative == "events.jsonl":
            identity = dict(rows[0])
            identity.pop("event_id")
            rows[0]["event_id"] = stable_digest("laconian-event-v1", identity)
        _write_jsonl(path, rows)
    else:
        payload = _json_object(path)
        payload["unknown"] = secret
        _write_json(path, payload)

    if relative == "manifest.json":
        _refresh_index_manifest(root)
        _refresh_capsule_and_event(root)
    elif relative in {
        "environment.json",
        "inputs/index.json",
        "case-index.jsonl",
        "plan.jsonl",
    }:
        _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="invalid_model", path=relative)
    rendered = canonical_json(result.model_dump(mode="json"))
    assert secret.encode("utf-8") not in rendered
    assert b"/private/producer/source" not in rendered


@pytest.mark.parametrize("relative", ["events.jsonl", "plan.jsonl"])
def test_jsonl_row_bound_is_checked_before_parsing_or_echoing_oversized_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    secret = b"TOP-SECRET-OVERSIZED-CONTENT"
    limit = RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes
    payload = b'{"secret":"' + secret + b"x" * limit + b'"}\n'
    (root / relative).write_bytes(payload)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path=relative)
    rendered = canonical_json(result.model_dump(mode="json"))
    assert secret not in rendered


@pytest.mark.parametrize(
    ("relative", "count"),
    [
        ("case-index.jsonl", RESOURCE_LIMITS_V1.case_records + 1),
        ("plan.jsonl", RESOURCE_LIMITS_V1.plan_rows + 1),
    ],
)
def test_jsonl_row_count_is_bounded_before_model_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    count: int,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / relative).write_bytes(b"{}\n" * count)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path=relative)


def test_json_nesting_depth_is_bounded_before_strict_model_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    nested: dict[str, Any] = {"leaf": "TOP-SECRET-DEEP"}
    for _ in range(RESOURCE_LIMITS_V1.nesting_depth):
        nested = {"nested": nested}
    (root / "environment.json").write_bytes(
        json.dumps(nested, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path="environment.json")
    assert b"TOP-SECRET-DEEP" not in canonical_json(result.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("relative", "limit"),
    [
        ("inputs/arms/concise.txt", RESOURCE_LIMITS_V1.arm_member_bytes),
        ("inputs/cases/000.yaml", RESOURCE_LIMITS_V1.case_file_bytes),
        (
            "inputs/software/runner/laconian_eval/providers/fake.py",
            RESOURCE_LIMITS_V1.runner_source_file_bytes,
        ),
    ],
)
def test_indexed_role_file_bounds_precede_hash_or_model_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    limit: int,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    with (root / relative).open("wb") as stream:
        stream.truncate(limit + 1)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path=relative)


def test_runner_aggregate_bound_is_enforced_from_metadata_before_sparse_member_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    runner_index = _json_object(root / "inputs/software/runner-source.json")
    runner_records = runner_index["files"]
    assert isinstance(runner_records, list)
    input_index = _json_object(root / "inputs/index.json")
    input_records = input_index["files"]
    assert isinstance(input_records, list)
    sparse_relatives: set[str] = set()
    member_bytes = RESOURCE_LIMITS_V1.runner_source_file_bytes
    member_count = RESOURCE_LIMITS_V1.all_runner_source_files_bytes // member_bytes + 1
    for ordinal in range(member_count):
        member = f"aggregate_{ordinal:02d}.py"
        relative = f"inputs/software/runner/laconian_eval/{member}"
        sparse_relatives.add(relative)
        with (root / relative).open("wb") as stream:
            stream.truncate(member_bytes)
        runner_records.append(
            {
                "path": member,
                "byte_length": member_bytes,
                "sha256": _OTHER_DIGEST,
            }
        )
        input_records.append(
            {
                "role": "runner_source",
                "role_ordinal": 0,
                "logical_locator": f"package[laconian_eval]/{member}",
                "capsule_path": relative,
                "byte_length": member_bytes,
                "sha256": _OTHER_DIGEST,
                "dataset_id": None,
                "binding_id": None,
            }
        )
    runner_records.sort(key=lambda item: item["path"].encode("utf-8"))
    runner_ordinal_by_path = {
        f"inputs/software/runner/laconian_eval/{record['path']}": ordinal
        for ordinal, record in enumerate(runner_records)
    }
    for record in input_records:
        if record["role"] == "runner_source":
            record["role_ordinal"] = runner_ordinal_by_path[record["capsule_path"]]
    input_records.sort(key=lambda item: item["capsule_path"].encode("utf-8"))
    runner_index["runner_source_sha256"] = _runner_source_root(runner_index)
    _write_json(root / "inputs/software/runner-source.json", runner_index)
    _write_json(root / "inputs/index.json", input_index)

    environment = _json_object(root / "environment.json")
    environment["runner_source_sha256"] = runner_index["runner_source_sha256"]
    provider = environment["provider"]
    runtime = environment["runtime"]
    assert isinstance(provider, dict)
    assert isinstance(runtime, dict)
    provider["adapter_source_sha256"] = _adapter_root(runner_index, "fake")
    runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
    _write_json(root / "environment.json", environment)
    _refresh_capsule_and_event(root)

    real_read = os.read

    def sparse_read_bomb(descriptor: int, size: int) -> bytes:
        descriptor_path = _descriptor_path(descriptor)
        if descriptor_path is not None:
            with suppress(ValueError):
                relative = descriptor_path.relative_to(root).as_posix()
                if relative in sparse_relatives:
                    raise AssertionError("aggregate limit was checked after reading sparse bytes")
        return real_read(descriptor, size)

    monkeypatch.setattr(verify_module.os, "read", sparse_read_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit")


@pytest.mark.parametrize(
    ("role", "limit"),
    [
        ("replay", RESOURCE_LIMITS_V1.replay_fixture_bytes),
        ("protocol", RESOURCE_LIMITS_V1.protocol_file_bytes),
    ],
)
def test_opaque_replay_and_protocol_per_file_bounds_precede_sparse_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    limit: int,
) -> None:
    root, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    record = next(item for item in records if item["role"] == role)
    relative = record["capsule_path"]
    assert isinstance(relative, str)
    with (root / relative).open("wb") as stream:
        stream.truncate(limit + 1)
    real_read = os.read

    def sparse_read_bomb(descriptor: int, size: int) -> bytes:
        if _descriptor_path(descriptor) == (root / relative).resolve():
            raise AssertionError("per-file bound was checked after reading sparse bytes")
        return real_read(descriptor, size)

    monkeypatch.setattr(verify_module.os, "read", sparse_read_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path=relative)


@pytest.mark.parametrize(
    ("limit_field", "roles"),
    [
        ("all_case_files_bytes", {"case"}),
        ("all_arm_members_bytes", {"arm"}),
        ("all_protocol_files_bytes", {"protocol"}),
        ("all_runner_source_files_bytes", {"runner_source"}),
        ("captured_input_total_bytes", {"case", "arm", "replay", "protocol", "runner_source"}),
    ],
)
def test_each_captured_input_aggregate_bucket_is_enforced_before_member_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_field: str,
    roles: set[str],
) -> None:
    root, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    selected = [record for record in records if record["role"] in roles]
    assert selected
    aggregate_bytes = sum(record["byte_length"] for record in selected)
    assert aggregate_bytes > 0
    monkeypatch.setattr(
        verify_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, **{limit_field: aggregate_bytes - 1}),
    )
    selected_paths = {record["capsule_path"] for record in selected}
    real_read = os.read

    def aggregate_read_bomb(descriptor: int, size: int) -> bytes:
        descriptor_path = _descriptor_path(descriptor)
        if descriptor_path is not None:
            with suppress(ValueError):
                relative = descriptor_path.relative_to(root).as_posix()
                if relative in selected_paths:
                    raise AssertionError("aggregate bound was checked after reading input bytes")
        return real_read(descriptor, size)

    monkeypatch.setattr(verify_module.os, "read", aggregate_read_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit")


def test_mutable_capsule_total_bound_precedes_reading_an_oversized_sparse_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    plan = root / "plan.jsonl"
    with plan.open("wb") as stream:
        stream.truncate(RESOURCE_LIMITS_V1.mutable_capsule_bytes + 1)
    real_read = os.read

    def plan_read_bomb(descriptor: int, size: int) -> bytes:
        if _descriptor_path(descriptor) == plan.resolve():
            raise AssertionError("mutable capsule bound was checked after reading sparse bytes")
        return real_read(descriptor, size)

    monkeypatch.setattr(verify_module.os, "read", plan_read_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path="plan.jsonl")


@pytest.mark.parametrize(
    "relative",
    [
        "capsule.json",
        "environment.json",
        "inputs/index.json",
        "inputs/software/runner-source.json",
        "manifest.json",
    ],
)
def test_static_json_schema_ceiling_precedes_reading_an_oversized_sparse_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    target = root / relative
    with target.open("wb") as stream:
        stream.truncate(4 * 1024 * 1024 * 1024)
    real_read = os.read

    def static_read_bomb(descriptor: int, size: int) -> bytes:
        if _descriptor_path(descriptor) == target.resolve():
            raise AssertionError("static JSON schema ceiling was checked after reading bytes")
        return real_read(descriptor, size)

    monkeypatch.setattr(verify_module.os, "read", static_read_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path=relative)


def test_static_json_collection_count_is_rejected_before_model_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    environment = _json_object(root / "environment.json")
    runtime = environment["runtime"]
    assert isinstance(runtime, dict)
    dependencies = runtime["dependencies"]
    assert isinstance(dependencies, list)
    while len(dependencies) <= RESOURCE_LIMITS_V1.dependency_distributions:
        ordinal = len(dependencies)
        dependencies.append(
            {
                "distribution": f"zz-overflow-{ordinal:04d}",
                "version": "1",
                "files_sha256": _OTHER_DIGEST,
            }
        )
    dependencies.sort(key=lambda item: item["distribution"].encode("utf-8"))
    runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
    _write_json(root / "environment.json", environment)
    _refresh_capsule_and_event(root)
    real_model_from_value = verify_module._model_from_value

    def model_construction_bomb(model_type: type[Any], value: object, path: str) -> object:
        if model_type is verify_module.EnvironmentV1:
            assert isinstance(value, dict)
            checked_runtime = value.get("runtime")
            if isinstance(checked_runtime, dict):
                checked_dependencies = checked_runtime.get("dependencies")
                if (
                    isinstance(checked_dependencies, list)
                    and len(checked_dependencies) > RESOURCE_LIMITS_V1.dependency_distributions
                ):
                    raise AssertionError("dependency count reached model construction")
        return real_model_from_value(model_type, value, path)

    monkeypatch.setattr(verify_module, "_model_from_value", model_construction_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path="environment.json")


def test_static_json_decoded_string_limit_precedes_whole_document_decoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    input_index = _json_object(root / "inputs/index.json")
    records = input_index["files"]
    assert isinstance(records, list)
    records[0]["logical_locator"] = "x" * (RESOURCE_LIMITS_V1.bounded_string_bytes + 1)
    _write_json(root / "inputs/index.json", input_index)
    _refresh_capsule_and_event(root)
    real_decode = verify_module._decode_json

    def whole_document_decode_bomb(data: bytes, path: str) -> object:
        if path == "inputs/index.json":
            raise AssertionError("oversized decoded string reached whole-document decoding")
        return real_decode(data, path)

    monkeypatch.setattr(verify_module, "_decode_json", whole_document_decode_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path="inputs/index.json")


def test_static_json_prescan_allows_maximum_decoded_string_with_worst_case_escaping() -> None:
    scanner = verify_module._StaticJsonScanner(
        "capsule.json",
        verify_module._static_json_policy("capsule.json"),
    )
    encoded = b'{"value":"' + b"\\u0001" * RESOURCE_LIMITS_V1.bounded_string_bytes + b'"}'

    for start in range(0, len(encoded), 97):
        scanner.feed(encoded[start : start + 97])
    scanner.finish()


def test_static_json_requires_the_producer_canonical_model_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    manifest = _json_object(root / "manifest.json")
    retry = manifest["retry"]
    assert isinstance(retry, dict)
    timeout = retry["timeout_seconds"]
    assert isinstance(timeout, float)
    assert timeout.is_integer()
    retry["timeout_seconds"] = int(timeout)
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="noncanonical_json", path="manifest.json")


@pytest.mark.parametrize(
    ("relative", "field"),
    [
        ("manifest.json", "runner_version"),
        ("environment.json", "container_image_digest"),
        ("inputs/index.json", "manifest_sha256"),
        ("case-index.jsonl", "category"),
        ("plan.jsonl", "arm_position"),
    ],
)
def test_capsule_hash_commitments_cover_every_static_generated_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    field: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    path = root / relative
    if relative.endswith(".jsonl"):
        rows = _jsonl_objects(path)
        rows[0][field] = "coding" if field == "category" else 99
        _write_jsonl(path, rows)
    else:
        payload = _json_object(path)
        payload[field] = "other-compatible-version" if field == "runner_version" else _OTHER_DIGEST
        _write_json(path, payload)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="hash_mismatch", path=relative)


def test_input_index_recomputes_every_indexed_byte_length_hash_and_disk_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    case_path = root / "inputs/cases/000.yaml"
    changed = case_path.read_bytes() + b"# coherent index rewrite must still bind exact bytes\n"
    case_path.write_bytes(changed)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    case_record = next(item for item in records if item["capsule_path"] == "inputs/cases/000.yaml")
    case_record["byte_length"] = len(changed)
    case_record["sha256"] = _OTHER_DIGEST
    _write_json(root / "inputs/index.json", index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="hash_mismatch", path="inputs/cases/000.yaml")


def test_input_index_manifest_commitment_must_equal_the_resolved_manifest_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    index = _json_object(root / "inputs/index.json")
    index["manifest_sha256"] = _OTHER_DIGEST
    _write_json(root / "inputs/index.json", index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="inputs/index.json")


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("runner_version", "999.0.0-compatible-producer"),
        ("run_purpose", "development"),
        ("claim_intent", "exploratory"),
        ("arm_order_seed", 99),
    ],
)
def test_capsule_identity_projection_must_equal_the_resolved_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: str | int,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    manifest = _json_object(root / "manifest.json")
    if field in {"run_purpose", "claim_intent"}:
        capsule_declarations = manifest["capsule"]
        assert isinstance(capsule_declarations, dict)
        capsule_declarations[field] = replacement
    else:
        manifest[field] = replacement
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)
    _refresh_capsule_and_event(root, sync_manifest_identity=False)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="capsule.json")


def test_runner_index_must_mirror_the_input_index_and_same_captured_runner_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    relative = "inputs/software/runner/laconian_eval/providers/fake.py"
    member = root / relative
    changed = member.read_bytes() + b"# coherent only in the complete input index\n"
    member.write_bytes(changed)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    input_record = next(record for record in records if record["capsule_path"] == relative)
    input_record["byte_length"] = len(changed)
    input_record["sha256"] = sha256_bytes(changed)
    _write_json(root / "inputs/index.json", index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="hash_mismatch", path=relative)


def test_case_index_is_recomputed_from_coherently_recommitted_captured_case_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    case_path = root / "inputs/cases/000.yaml"
    case_payload = yaml.safe_load(case_path.read_bytes())
    assert isinstance(case_payload, dict)
    cases = case_payload["cases"]
    assert isinstance(cases, list)
    assert isinstance(cases[0], dict)
    cases[0]["prompt"] = "A coherent new prompt that leaves generated rows stale."
    changed = yaml.safe_dump(
        case_payload,
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    case_path.write_bytes(changed)

    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    case_record = next(
        record for record in records if record["capsule_path"] == "inputs/cases/000.yaml"
    )
    case_record["byte_length"] = len(changed)
    case_record["sha256"] = sha256_bytes(changed)
    _write_json(root / "inputs/index.json", index)

    manifest = _json_object(root / "manifest.json")
    declarations = manifest["capsule"]
    assert isinstance(declarations, dict)
    datasets = declarations["datasets"]
    assert isinstance(datasets, list) and len(datasets) == 1
    dataset = datasets[0]
    assert isinstance(dataset, dict)
    dataset["dataset_content_sha256"] = stable_digest(
        "laconian-dataset-content-v1",
        {
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["dataset_version"],
            "members": [
                {
                    "source_ordinal": case_record["role_ordinal"],
                    "capsule_path": case_record["capsule_path"],
                    "byte_length": case_record["byte_length"],
                    "sha256": case_record["sha256"],
                }
            ],
        },
    )
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="case-index.jsonl")


def test_captured_case_yaml_rejects_anchors_and_aliases_even_when_semantics_are_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    relative = "inputs/cases/000.yaml"
    source = (root / relative).read_text(encoding="utf-8")
    assert source.count("category: direct") == 2
    anchored = source.replace("category: direct", "category: &shared direct", 1)
    anchored = anchored.replace("category: direct", "category: *shared", 1)
    _recommit_case_bytes(root, relative=relative, data=anchored.encode("utf-8"))

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="invalid_model", path=relative)


@pytest.mark.parametrize("member", ["SKILL.md", "SOURCE.md", "LICENSE.txt"])
def test_fixed_caveman_snapshot_pins_are_recomputed_after_coherent_input_recommit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    member: str,
) -> None:
    authored = tmp_path / "authored"
    authored.mkdir()
    manifest = _write_manifest(authored, arms=["baseline", "caveman"])
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(monkeypatch, results_root)
    source_root = _copy_file_backed_arm_source(tmp_path)
    prepared = prepare_module.prepare_capsule(
        _request(manifest, results_root, source_root=source_root)
    )
    source_root.rename(source_root.with_name("file-backed-arm-source-removed"))

    relative = f"inputs/arms/caveman/{member}"
    path = prepared.path / relative
    changed = path.read_bytes() + b"\ncoherently recommitted but not the fixed snapshot\n"
    path.write_bytes(changed)
    index = _json_object(prepared.path / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    record = next(item for item in records if item["capsule_path"] == relative)
    record["byte_length"] = len(changed)
    record["sha256"] = sha256_bytes(changed)
    _write_json(prepared.path / "inputs/index.json", index)
    _refresh_capsule_and_event(prepared.path)

    result = verify_capsule(prepared.path, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path=relative)
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize(
    "target",
    ["guard", "audit-hook", "adapter", "runtime", "runner-root"],
)
def test_static_verification_recomputes_runner_guard_audit_adapter_and_runtime_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    environment_path = root / "environment.json"
    environment = _json_object(environment_path)
    runtime = environment["runtime"]
    provider = environment["provider"]
    assert isinstance(runtime, dict)
    assert isinstance(provider, dict)
    if target in {"guard", "audit-hook"}:
        imports = runtime["import_environment"]
        assert isinstance(imports, dict)
        field = "guard_source_sha256" if target == "guard" else "audit_hook_source_sha256"
        imports[field] = _OTHER_DIGEST
        runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
        expected_path = "environment.json"
    elif target == "adapter":
        provider["adapter_source_sha256"] = _OTHER_DIGEST
        runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
        expected_path = "environment.json"
    elif target == "runtime":
        runtime["runtime_fingerprint_sha256"] = _OTHER_DIGEST
        expected_path = "environment.json"
    else:
        runner_path = root / "inputs/software/runner-source.json"
        runner = _json_object(runner_path)
        runner["runner_source_sha256"] = _OTHER_DIGEST
        _write_json(runner_path, runner)
        environment["runner_source_sha256"] = _OTHER_DIGEST
        runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
        expected_path = "inputs/software/runner-source.json"
    _write_json(environment_path, environment)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path=expected_path)


@pytest.mark.parametrize(
    "target",
    ["package-version", "runner-source", "provider-kind", "requested-model"],
)
def test_environment_projection_must_match_capsule_and_resolved_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    environment = _json_object(root / "environment.json")
    runtime = environment["runtime"]
    provider = environment["provider"]
    assert isinstance(runtime, dict)
    assert isinstance(provider, dict)
    if target == "package-version":
        environment["package_version"] = "999.0.0-compatible-producer"
    elif target == "runner-source":
        environment["runner_source_sha256"] = _OTHER_DIGEST
    elif target == "provider-kind":
        provider["kind"] = "replay"
        runner_index = _json_object(root / "inputs/software/runner-source.json")
        provider["adapter_source_sha256"] = _adapter_root(runner_index, "replay")
    else:
        provider["requested_model"] = "different-fixture-model"
    runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
    _write_json(root / "environment.json", environment)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="environment.json")


def test_dataset_content_commitment_is_recomputed_from_exact_case_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    manifest = _json_object(root / "manifest.json")
    capsule_section = manifest["capsule"]
    assert isinstance(capsule_section, dict)
    datasets = capsule_section["datasets"]
    assert isinstance(datasets, list)
    datasets[0]["dataset_content_sha256"] = _OTHER_DIGEST
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="manifest.json")


@pytest.mark.parametrize(
    "target",
    [
        "prompt",
        "prompt-utf8-bytes",
        "category",
        "source-ordinal",
        "case-uid",
        "coverage",
    ],
)
def test_case_index_recomputes_every_semantic_field_and_exact_row_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    rows = _jsonl_objects(root / "case-index.jsonl")
    if target == "prompt":
        rows[0]["prompt_sha256"] = _OTHER_DIGEST
    elif target == "prompt-utf8-bytes":
        rows[0]["prompt_utf8_bytes"] += 1
    elif target == "category":
        rows[0]["category"] = "coding"
    elif target == "source-ordinal":
        rows[0]["source_ordinal"] = 1
    elif target == "case-uid":
        rows[0]["case_uid"] = _OTHER_DIGEST
    else:
        rows.pop()
    _write_jsonl(root / "case-index.jsonl", rows)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="case-index.jsonl")


@pytest.mark.parametrize(
    "target",
    ["arm-position", "pairing-unit", "request-config", "input-token-bound", "coverage"],
)
def test_plan_is_recomputed_for_order_pairing_request_and_exact_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    rows = _jsonl_objects(root / "plan.jsonl")
    if target == "arm-position":
        rows[0]["arm_position"] = 99
    elif target == "pairing-unit":
        rows[0]["pairing_unit_id"] = _OTHER_DIGEST
    elif target == "request-config":
        rows[0]["request_config_sha256"] = _OTHER_DIGEST
    elif target == "input-token-bound":
        rows[0]["input_token_bound"] += 1
    else:
        rows.pop()
    _write_jsonl(root / "plan.jsonl", rows)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="plan_mismatch", path="plan.jsonl")


def test_plan_is_recomputed_from_coherently_recommitted_captured_arm_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    relative = "inputs/arms/if/SKILL.md"
    path = root / relative
    changed = path.read_bytes() + b"\nA coherent changed instruction.\n"
    path.write_bytes(changed)
    index = _json_object(root / "inputs/index.json")
    records = index["files"]
    assert isinstance(records, list)
    record = next(item for item in records if item["capsule_path"] == relative)
    record["byte_length"] = len(changed)
    record["sha256"] = sha256_bytes(changed)
    _write_json(root / "inputs/index.json", index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="plan_mismatch", path="plan.jsonl")
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize(
    "mutation",
    ["second-event", "event-id", "timestamp", "same-operation", "payload"],
)
def test_prepared_history_is_exactly_one_bound_sequence_zero_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root, fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    path = root / "events.jsonl"
    event = PreparedEventV1.model_validate_json(path.read_bytes().removesuffix(b"\n"))
    expected_code = "history_mismatch"
    if mutation == "second-event":
        payload = event.model_dump(mode="json")
        payload["sequence"] = 1
        identity_payload = dict(payload)
        identity_payload.pop("event_id")
        payload["event_id"] = stable_digest("laconian-event-v1", identity_payload)
        path.write_bytes(path.read_bytes() + canonical_json(payload) + b"\n")
        expected_sequence = 1
    elif mutation == "event-id":
        payload = event.model_dump(mode="json")
        payload["event_id"] = _OTHER_DIGEST
        path.write_bytes(canonical_json(payload) + b"\n")
        expected_sequence = 0
        expected_code = "hash_mismatch"
    else:
        changed = make_prepared_event(
            run_id=event.run_id,
            operation_id=(
                fixture.prepared.run_id if mutation == "same-operation" else event.operation_id
            ),
            occurred_at=(
                event.occurred_at + timedelta(seconds=1)
                if mutation == "timestamp"
                else event.occurred_at
            ),
            manifest_sha256=(
                _OTHER_DIGEST if mutation == "payload" else event.payload.manifest_sha256
            ),
            input_index_sha256=event.payload.input_index_sha256,
            case_index_sha256=event.payload.case_index_sha256,
            plan_sha256=event.payload.plan_sha256,
            environment_sha256=event.payload.environment_sha256,
            runner_source_sha256=event.payload.runner_source_sha256,
        )
        path.write_bytes(event_jsonl(changed))
        expected_sequence = 0
        if mutation == "payload":
            expected_code = "hash_mismatch"
        elif mutation in {"timestamp", "same-operation"}:
            expected_code = "identity_mismatch"

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(
        result,
        code=expected_code,
        path="events.jsonl",
        sequence=expected_sequence,
    )


def test_event_errors_use_physical_row_order_not_an_untrusted_declared_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    event = PreparedEventV1.model_validate_json(
        (root / "events.jsonl").read_bytes().removesuffix(b"\n")
    )
    first = event.model_dump(mode="json")
    first["sequence"] = 7
    first_identity = dict(first)
    first_identity.pop("event_id")
    first["event_id"] = stable_digest("laconian-event-v1", first_identity)
    second = event.model_dump(mode="json")
    second["event_id"] = _OTHER_DIGEST
    _write_jsonl(root / "events.jsonl", [first, second])

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="history_mismatch", path="events.jsonl", sequence=0)


def test_prepared_raw_ledger_must_be_exactly_empty_and_is_never_repaired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    raw = b'{"secret":"TOP-SECRET-RAW"}\nunterminated-tail'
    (root / "raw.jsonl").write_bytes(raw)
    before = _snapshot(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="invalid_model", path="raw.jsonl", sequence=0)
    assert _snapshot(root) == before
    assert b"TOP-SECRET-RAW" not in canonical_json(result.model_dump(mode="json"))


def test_first_failure_is_stage_then_utf8_path_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / "zzz-unexpected").write_bytes(b"z")
    (root / "aaa-unexpected").write_bytes(b"a")
    (root / "environment.json").write_bytes(b"not json")
    (root / "manifest.json").write_bytes(b"not json")

    first = verify_capsule(root, mode=VerificationMode.PREPARED)
    second = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(first, code="unexpected_path", path="aaa-unexpected")
    assert second == first


def test_static_stage_errors_sort_by_utf8_relative_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / "manifest.json").write_bytes((root / "manifest.json").read_bytes() + b"\n")
    (root / "environment.json").write_bytes((root / "environment.json").read_bytes() + b"\n")

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="noncanonical_json", path="environment.json")


def test_captured_arm_and_case_static_errors_sort_by_utf8_relative_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    case_relative = "inputs/cases/000.yaml"
    _recommit_case_bytes(root, relative=case_relative, data=b"not: [valid\n")

    arm_relative = "inputs/arms/caveman/LICENSE.txt"
    changed_arm = (root / arm_relative).read_bytes() + b"\n"
    (root / arm_relative).write_bytes(changed_arm)
    input_index = _json_object(root / "inputs/index.json")
    input_records = input_index["files"]
    assert isinstance(input_records, list)
    arm_record = next(record for record in input_records if record["capsule_path"] == arm_relative)
    arm_record["byte_length"] = len(changed_arm)
    arm_record["sha256"] = sha256_bytes(changed_arm)
    _write_json(root / "inputs/index.json", input_index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path=arm_relative)


def test_captured_arm_error_precedes_a_later_runner_cross_link_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    arm_relative = "inputs/arms/caveman/LICENSE.txt"
    changed_arm = (root / arm_relative).read_bytes() + b"\n"
    (root / arm_relative).write_bytes(changed_arm)
    input_index = _json_object(root / "inputs/index.json")
    input_records = input_index["files"]
    assert isinstance(input_records, list)
    arm_record = next(record for record in input_records if record["capsule_path"] == arm_relative)
    arm_record["byte_length"] = len(changed_arm)
    arm_record["sha256"] = sha256_bytes(changed_arm)
    _write_json(root / "inputs/index.json", input_index)

    runner_index = _json_object(root / "inputs/software/runner-source.json")
    runner_records = runner_index["files"]
    assert isinstance(runner_records, list)
    runner_record = next(
        record
        for record in runner_records
        if record["path"]
        not in {"providers/__init__.py", "providers/fake.py", "capsule/import_policy.py"}
    )
    runner_record["byte_length"] += 1
    _write_json(root / "inputs/software/runner-source.json", runner_index)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path=arm_relative)


def test_captured_arm_error_precedes_a_later_runner_member_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    arm_relative = "inputs/arms/caveman/LICENSE.txt"
    changed_arm = (root / arm_relative).read_bytes() + b"\n"
    (root / arm_relative).write_bytes(changed_arm)
    input_index = _json_object(root / "inputs/index.json")
    input_records = input_index["files"]
    assert isinstance(input_records, list)
    arm_record = next(record for record in input_records if record["capsule_path"] == arm_relative)
    arm_record["byte_length"] = len(changed_arm)
    arm_record["sha256"] = sha256_bytes(changed_arm)
    _write_json(root / "inputs/index.json", input_index)
    _refresh_capsule_and_event(root)

    later_runner = "inputs/software/runner/laconian_eval/providers/fake.py"
    real_read_file = verify_module._read_file

    def fail_later_runner(*args: Any, **kwargs: Any) -> bytes:
        path = args[1]
        if path == later_runner:
            raise verify_module._Failure("io_error", later_runner)
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_read_file", fail_later_runner)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path=arm_relative)


@pytest.mark.parametrize("member", ["SKILL.md", "SOURCE.md"])
@pytest.mark.parametrize(
    ("failure_kind", "expected_code"),
    [("read", "io_error"), ("hash", "hash_mismatch")],
)
def test_caveman_dependent_validation_preserves_a_direct_member_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    member: str,
    failure_kind: str,
    expected_code: str,
) -> None:
    root, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    relative = f"inputs/arms/caveman/{member}"
    if failure_kind == "hash":
        target = root / relative
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        real_read_file = verify_module._read_file

        def fail_member(*args: Any, **kwargs: Any) -> bytes:
            if args[1] == relative:
                raise verify_module._Failure("io_error", relative)
            return real_read_file(*args, **kwargs)

        monkeypatch.setattr(verify_module, "_read_file", fail_member)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code=expected_code, path=relative)


@pytest.mark.parametrize("trusted_member", ["LICENSE.txt", "SKILL.md"])
def test_each_trusted_caveman_pin_is_checked_despite_a_later_untrusted_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trusted_member: str,
) -> None:
    root, _harness = _prepare_all_input_roles(tmp_path, monkeypatch)
    trusted_relative = f"inputs/arms/caveman/{trusted_member}"
    changed = (root / trusted_relative).read_bytes() + b"\n"
    (root / trusted_relative).write_bytes(changed)
    input_index = _json_object(root / "inputs/index.json")
    input_records = input_index["files"]
    assert isinstance(input_records, list)
    trusted_record = next(
        record for record in input_records if record["capsule_path"] == trusted_relative
    )
    trusted_record["byte_length"] = len(changed)
    trusted_record["sha256"] = sha256_bytes(changed)
    _write_json(root / "inputs/index.json", input_index)
    _refresh_capsule_and_event(root)

    untrusted_relative = "inputs/arms/caveman/SOURCE.md"
    real_read_file = verify_module._read_file

    def fail_source(*args: Any, **kwargs: Any) -> bytes:
        if args[1] == untrusted_relative:
            raise verify_module._Failure("io_error", untrusted_relative)
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(verify_module, "_read_file", fail_source)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path=trusted_relative)


def test_captured_case_error_precedes_a_later_dataset_commitment_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    case_relative = "inputs/cases/000.yaml"
    _recommit_case_bytes(root, relative=case_relative, data=b"not: [valid\n")
    manifest = _json_object(root / "manifest.json")
    declarations = manifest["capsule"]
    assert isinstance(declarations, dict)
    datasets = declarations["datasets"]
    assert isinstance(datasets, list)
    datasets[0]["dataset_content_sha256"] = _OTHER_DIGEST
    _write_json(root / "manifest.json", manifest)
    _refresh_index_manifest(root)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="invalid_model", path=case_relative)


def test_runner_capture_rejects_producer_ignored_pycache_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    runner_member = "__pycache__/shadow.py"
    relative = f"inputs/software/runner/laconian_eval/{runner_member}"
    payload = b"captured = False\n"
    target = root / relative
    target.parent.mkdir()
    target.write_bytes(payload)

    runner_index = _json_object(root / "inputs/software/runner-source.json")
    runner_records = runner_index["files"]
    assert isinstance(runner_records, list)
    runner_records.append(
        {
            "path": runner_member,
            "byte_length": len(payload),
            "sha256": sha256_bytes(payload),
        }
    )
    runner_records.sort(key=lambda item: item["path"].encode("utf-8"))
    runner_index["runner_source_sha256"] = _runner_source_root(runner_index)
    _write_json(root / "inputs/software/runner-source.json", runner_index)

    input_index = _json_object(root / "inputs/index.json")
    input_records = input_index["files"]
    assert isinstance(input_records, list)
    input_records.append(
        {
            "role": "runner_source",
            "role_ordinal": 0,
            "logical_locator": f"package[laconian_eval]/{runner_member}",
            "capsule_path": relative,
            "byte_length": len(payload),
            "sha256": sha256_bytes(payload),
            "dataset_id": None,
            "binding_id": None,
        }
    )
    runner_ordinal_by_path = {
        f"inputs/software/runner/laconian_eval/{record['path']}": ordinal
        for ordinal, record in enumerate(runner_records)
    }
    for record in input_records:
        if record["role"] == "runner_source":
            record["role_ordinal"] = runner_ordinal_by_path[record["capsule_path"]]
    input_records.sort(key=lambda item: item["capsule_path"].encode("utf-8"))
    _write_json(root / "inputs/index.json", input_index)

    environment = _json_object(root / "environment.json")
    environment["runner_source_sha256"] = runner_index["runner_source_sha256"]
    runtime = environment["runtime"]
    assert isinstance(runtime, dict)
    runtime["runtime_fingerprint_sha256"] = _runtime_fingerprint(environment)
    _write_json(root / "environment.json", environment)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(
        result,
        code="unexpected_path",
        path="inputs/software/runner/laconian_eval/__pycache__",
    )


def test_runner_tree_rejects_an_overlong_relative_path_before_recursive_descent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    runner_root = root / "inputs/software/runner/laconian_eval"
    descriptor = os.open(runner_root, os.O_RDONLY | os.O_DIRECTORY)
    relative = "inputs/software/runner/laconian_eval"
    try:
        while len(relative.encode("utf-8")) <= RESOURCE_LIMITS_V1.bounded_string_bytes:
            os.mkdir("d", dir_fd=descriptor)
            next_descriptor = os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
            relative += "/d"
    finally:
        os.close(descriptor)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path=None)


def test_case_index_stage_failure_precedes_a_simultaneous_plan_stage_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    case_rows = _jsonl_objects(root / "case-index.jsonl")
    case_rows[0]["case_uid"] = _OTHER_DIGEST
    _write_jsonl(root / "case-index.jsonl", case_rows)
    plan_rows = _jsonl_objects(root / "plan.jsonl")
    plan_rows[0]["arm_position"] = 99
    _write_jsonl(root / "plan.jsonl", plan_rows)
    _refresh_capsule_and_event(root)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="identity_mismatch", path="case-index.jsonl")


def test_static_utf8_order_precedes_later_static_and_case_stage_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    environment = _json_object(root / "environment.json")
    environment["container_image_digest"] = _OTHER_DIGEST
    _write_json(root / "environment.json", environment)
    (root / "inputs/index.json").write_bytes(b"not canonical json")
    (root / "case-index.jsonl").write_bytes(b"not canonical jsonl")

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="hash_mismatch", path="environment.json")


def test_exact_tree_precedes_role_resource_checks_for_unindexed_sparse_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    unexpected = "inputs/software/runner/laconian_eval/zzz-unindexed.py"
    with (root / unexpected).open("wb") as stream:
        stream.truncate(RESOURCE_LIMITS_V1.runner_source_file_bytes + 1)
    real_read = os.read

    def unexpected_read_bomb(descriptor: int, size: int) -> bytes:
        if _descriptor_path(descriptor) == (root / unexpected).resolve():
            raise AssertionError("unexpected sparse member was read before exact-tree rejection")
        return real_read(descriptor, size)

    monkeypatch.setattr(verify_module.os, "read", unexpected_read_bomb)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="unexpected_path", path=unexpected)


@pytest.mark.parametrize("relative", ["plan.jsonl", "events.jsonl"])
def test_oversized_jsonl_row_is_rejected_without_reading_the_sparse_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    sparse_size = 64 * 1024 * 1024
    with (root / relative).open("wb") as stream:
        stream.truncate(sparse_size)
    real_read = os.read
    read_bytes = [0]
    allowed = RESOURCE_LIMITS_V1.plan_event_jsonl_row_bytes + 2 * 64 * 1024

    def bounded_sparse_read(descriptor: int, size: int) -> bytes:
        data = real_read(descriptor, size)
        if _descriptor_path(descriptor) == (root / relative).resolve():
            read_bytes[0] += len(data)
            if read_bytes[0] > allowed:
                raise AssertionError("verifier read the oversized JSONL sparse tail")
        return data

    monkeypatch.setattr(verify_module.os, "read", bounded_sparse_read)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="resource_limit", path=relative)
    assert read_bytes[0] <= allowed


def test_jsonl_second_pass_rechecks_snapshot_size_before_allocating_growth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    relative = "plan.jsonl"
    plan = root / relative
    original_size = plan.stat().st_size
    sparse_size = 64 * 1024 * 1024
    real_lseek = os.lseek
    real_read = os.read
    grew = [False]
    second_pass_bytes = [0]

    def grow_at_second_pass(descriptor: int, offset: int, whence: int) -> int:
        if (
            not grew[0]
            and offset == 0
            and whence == os.SEEK_SET
            and _descriptor_path(descriptor) == plan.resolve()
        ):
            with plan.open("r+b") as stream:
                stream.truncate(sparse_size)
            grew[0] = True
        return real_lseek(descriptor, offset, whence)

    def bounded_second_pass_read(descriptor: int, size: int) -> bytes:
        data = real_read(descriptor, size)
        if grew[0] and _descriptor_path(descriptor) == plan.resolve():
            second_pass_bytes[0] += len(data)
            if second_pass_bytes[0] > original_size + 2 * 64 * 1024:
                raise AssertionError("second JSONL pass consumed unstable sparse growth")
        return data

    monkeypatch.setattr(verify_module.os, "lseek", grow_at_second_pass)
    monkeypatch.setattr(verify_module.os, "read", bounded_second_pass_read)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert grew == [True]
    _assert_invalid(result, code="unstable_snapshot", path=relative)
    assert second_pass_bytes[0] <= original_size + 2 * 64 * 1024


def test_nonempty_prepared_raw_is_read_and_rejected_by_framing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / "raw.jsonl").write_bytes(b"TOP-SECRET-RAW")
    before = _snapshot(root)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="noncanonical_json", path="raw.jsonl", sequence=0)
    assert _snapshot(root) == before


def test_descriptor_context_entry_never_acquires_shared_lock_and_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    try:
        inventory = verify_module._scan_inventory(root_fd)

        def shared_lock_bomb(*args: object, **kwargs: object) -> object:
            raise AssertionError("descriptor context attempted recursive shared locking")

        monkeypatch.setattr(verify_module, "try_acquire_shared_lock", shared_lock_bomb)
        context = verify_module._verify_capsule_context_descriptors(root_fd, inventory)
    finally:
        os.close(root_fd)

    assert context.capsule.run_id == fixture.prepared.run_id
    assert context.manifest.runner_version == context.capsule.runner_version
    assert context.environment.runner_source_sha256 == context.capsule.runner_source_sha256
    assert tuple(item.record for item in context.captured.files) == context.input_index.files
    assert context.case_index
    assert all(row.source_ordinal < len(context.captured.case_files) for row in context.case_index)
    assert context.plan
    assert context.history.next_call_sequence == 0
    assert context.lifecycle.state == "PREPARED"
    with pytest.raises(FrozenInstanceError):
        context.lifecycle = context.lifecycle  # type: ignore[misc]


def test_verifier_threads_capsule_manifest_digest_into_parent_plan_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    expected_plan = tuple(
        PlanRowV1.model_validate_json(line)
        for line in (root / "plan.jsonl").read_bytes().splitlines()
    )
    calls: list[tuple[Any, str, Any, Any, Any]] = []
    validator = verify_module.validate_parent_plan

    def validate_parent_plan_spy(
        rows: Any,
        *,
        parent_manifest_sha256: str,
        resolved_manifest: Any,
        case_index: Any,
        captured_arms: Any,
    ) -> None:
        calls.append(
            (
                rows,
                parent_manifest_sha256,
                resolved_manifest,
                case_index,
                captured_arms,
            )
        )
        validator(
            rows,
            parent_manifest_sha256=parent_manifest_sha256,
            resolved_manifest=resolved_manifest,
            case_index=case_index,
            captured_arms=captured_arms,
        )

    monkeypatch.setattr(verify_module, "validate_parent_plan", validate_parent_plan_spy)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert len(calls) == 2
    assert all(call[0] == expected_plan for call in calls)
    assert all(call[1] == fixture.prepared.capsule.manifest_sha256 for call in calls)


def test_descriptor_context_rejects_hostile_inventory_before_artifact_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    try:
        inventory = verify_module._scan_inventory(root_fd)
        forged_root = verify_module._Identity(
            True,
            inventory.root_identity.inode,
            inventory.root_identity.mode,
            inventory.root_identity.size,
            inventory.root_identity.mtime_ns,
            inventory.root_identity.ctime_ns,
        )
        forged = verify_module._Inventory(forged_root, inventory.directories, inventory.files)
        with pytest.raises(verify_module._Failure) as caught:
            verify_module._verify_capsule_context_descriptors(root_fd, forged)
    finally:
        os.close(root_fd)
    assert caught.value.code == "invalid_model"
    assert caught.value.path is None


def test_descriptor_context_revalidates_model_construct_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    inventory = verify_module._scan_inventory(root_fd)
    real_json_model = verify_module._json_model

    def forge_capsule(data: bytes, path: str, model_type: type[Any]) -> Any:
        value = real_json_model(data, path, model_type)
        if path != "capsule.json":
            return value
        payload = value.model_dump(mode="python")
        payload["runner_version"] = object()
        return type(value).model_construct(**payload)

    monkeypatch.setattr(verify_module, "_json_model", forge_capsule)
    try:
        with pytest.raises(verify_module._Failure) as caught:
            verify_module._verify_capsule_context_descriptors(root_fd, inventory)
    finally:
        os.close(root_fd)
    assert caught.value.code in {"invalid_model", "identity_mismatch"}
    assert "TOP-SECRET" not in repr(caught.value)


def test_descriptor_context_rejects_a_contradictory_lifecycle_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    try:
        context = verify_module._verify_capsule_context_descriptors(
            root_fd,
            verify_module._scan_inventory(root_fd),
        )
    finally:
        os.close(root_fd)
    forged = history_module.LifecycleProjectionV1("GENERATION_COMPLETE", (), ())

    with pytest.raises(verify_module._Failure) as caught:
        replace(context, lifecycle=forged)

    assert (caught.value.code, caught.value.path) == ("invalid_model", None)


def test_descriptor_context_rejects_a_coherently_forged_history_and_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    try:
        context = verify_module._verify_capsule_context_descriptors(
            root_fd,
            verify_module._scan_inventory(root_fd),
        )
    finally:
        os.close(root_fd)
    forged_history = replace(
        context.history,
        resolved_plan_item_ids=tuple(row.plan_item_id for row in context.plan),
        missing_plan_item_ids=(),
        next_unresolved_plan_ordinal=None,
    )
    forged_lifecycle = history_module.LifecycleProjectionV1("GENERATION_COMPLETE", (), ())

    with pytest.raises(verify_module._Failure) as caught:
        replace(
            context,
            history=forged_history,
            lifecycle=forged_lifecycle,
        )

    assert (caught.value.code, caught.value.path) == ("invalid_model", None)


@pytest.mark.parametrize("forgery", ["record", "bytes"])
def test_descriptor_context_rejects_forged_nested_captured_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    forgery: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    try:
        context = verify_module._verify_capsule_context_descriptors(
            root_fd,
            verify_module._scan_inventory(root_fd),
        )
    finally:
        os.close(root_fd)
    original = context.captured.files[0]
    if forgery == "record":
        payload = original.record.model_dump(mode="python")
        payload["sha256"] = "0" * 64
        forged_input = replace(
            original,
            record=type(original.record).model_construct(**payload),
        )
    else:
        forged_input = replace(original, data=b"TOP-SECRET-CAPTURED-CANARY")
    forged_captured = replace(
        context.captured,
        files=(forged_input, *context.captured.files[1:]),
    )

    with pytest.raises(verify_module._Failure) as caught:
        replace(context, captured=forged_captured)

    assert (caught.value.code, caught.value.path) == ("invalid_model", None)
    assert "TOP-SECRET" not in repr(caught.value)


_DYNAMIC_OPERATION = UUID("72345678-1234-4abc-8def-1234567890ab")
_DYNAMIC_SESSION = UUID("82345678-1234-4abc-8def-1234567890ab")
_DYNAMIC_RUN_ID = UUID("62345678-1234-4abc-8def-1234567890ab")
_DYNAMIC_SEAL_OPERATION = UUID("92345678-1234-4abc-8def-1234567890ab")
_DYNAMIC_SEAL_TRANSACTION = UUID("a2345678-1234-4abc-8def-1234567890ab")
_DYNAMIC_AT = datetime(2026, 8, 29, 15, 0, 0, tzinfo=UTC)


def _dynamic_models(root: Path) -> tuple[CapsuleV1, EnvironmentV1, tuple[PlanRowV1, ...]]:
    capsule = CapsuleV1.model_validate_json((root / "capsule.json").read_bytes())
    environment = EnvironmentV1.model_validate_json((root / "environment.json").read_bytes())
    plan = tuple(
        PlanRowV1.model_validate_json(line)
        for line in (root / "plan.jsonl").read_bytes().splitlines()
    )
    return capsule, environment, plan


def _dynamic_started(environment: EnvironmentV1, *, sequence: int = 1) -> Any:
    runtime = environment.runtime
    provider = environment.provider
    return make_event(
        sequence=sequence,
        run_id=_DYNAMIC_RUN_ID,
        occurred_at=_DYNAMIC_AT,
        kind="execution_started",
        operation_id=_DYNAMIC_OPERATION,
        execution_session_id=_DYNAMIC_SESSION,
        payload={
            "resume_from_plan_ordinal": 0,
            "session_environment": {
                "schema_version": "1",
                "package_version": environment.package_version,
                "runner_source_sha256": environment.runner_source_sha256,
                "runtime_fingerprint_sha256": runtime.runtime_fingerprint_sha256,
                "python_implementation": runtime.python_implementation,
                "python_version": runtime.python_version,
                "os_family": runtime.os_family,
                "os_release": runtime.os_release,
                "architecture": runtime.architecture,
                "filesystem_class": runtime.filesystem_class,
                "adapter_source_sha256": provider.adapter_source_sha256,
                "sdk_distribution": provider.sdk_distribution,
                "sdk_version": provider.sdk_version,
            },
        },
    )


def _dynamic_attempt(
    capsule: CapsuleV1, plan: PlanRowV1, call_sequence: int, *, authentication: bool = False
) -> RawAttemptV2:
    attempt_id = derive_attempt_id(capsule.run_id, plan.plan_item_id, 1)
    output = None if authentication else "Done."
    output_sha = None if output is None else sha256_bytes(output.encode())
    response_id = (
        None
        if output_sha is None
        else stable_digest(
            "laconian-response-v1",
            {
                "run_id": capsule.run_id,
                "plan_item_id": plan.plan_item_id,
                "attempt_id": attempt_id,
                "case_uid": plan.case_uid,
                "instruction_sha256": plan.instruction_sha256,
                "output_sha256": output_sha,
            },
        )
    )
    return RawAttemptV2.model_validate(
        {
            "schema_version": "2",
            "runner_version": capsule.runner_version,
            "run_id": capsule.run_id,
            "manifest_sha256": capsule.manifest_sha256,
            "plan_item_id": plan.plan_item_id,
            "attempt_id": attempt_id,
            "scenario_uid": plan.scenario_uid,
            "case_uid": plan.case_uid,
            "case_id": plan.case_id,
            "locale": plan.locale,
            "case_definition_sha256": plan.case_definition_sha256,
            "arm": plan.arm,
            "repetition": plan.repetition,
            "attempt": 1,
            "terminal": True,
            "call_sequence": call_sequence,
            "retry_of_attempt": None,
            "backoff_ms": None,
            "delivery_certainty": "response_received",
            "prompt_sha256": plan.prompt_sha256,
            "instruction_sha256": plan.instruction_sha256,
            "request_config_sha256": plan.request_config_sha256,
            "provider": "fake",
            "model": "fixture-v1",
            "response_model": None if authentication else "fixture-v1",
            "started_at": _DYNAMIC_AT,
            "elapsed_ms": 1,
            "output_text": output,
            "output_sha256": output_sha,
            "response_id": response_id,
            "output_was_redacted": False,
            "output_redaction_count": 0,
            "discarded_output_byte_length": None,
            "discarded_output_sha256": None,
            "usage": {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "cached_input_tokens": None,
                "availability": "unavailable",
                "source": "provider",
                "cache_accounting": "not_reported",
            },
            "request_id": None,
            "finish_reason": None if authentication else "stop",
            "error": (
                {
                    "kind": "authentication",
                    "message": "authentication stopped",
                    "retryable": False,
                    "request_id": None,
                }
                if authentication
                else None
            ),
            "terminal_reason": "authentication_stopped" if authentication else "success",
        }
    )


def _dynamic_start(capsule: CapsuleV1, plan: PlanRowV1, sequence: int, call: int) -> Any:
    return make_event(
        sequence=sequence,
        run_id=capsule.run_id,
        occurred_at=_DYNAMIC_AT,
        kind="request_started",
        operation_id=_DYNAMIC_OPERATION,
        execution_session_id=_DYNAMIC_SESSION,
        payload={
            "call_sequence": call,
            "plan_item_id": plan.plan_item_id,
            "attempt_id": derive_attempt_id(capsule.run_id, plan.plan_item_id, 1),
            "attempt": 1,
            "retry_of_attempt": None,
            "request_config_sha256": plan.request_config_sha256,
            "prompt_sha256": plan.prompt_sha256,
            "case_definition_sha256": plan.case_definition_sha256,
            "instruction_sha256": plan.instruction_sha256,
            "provider": "fake",
            "model": "fixture-v1",
        },
    )


def _dynamic_finish(capsule: CapsuleV1, start: Any, raw: RawAttemptV2, sequence: int) -> Any:
    return make_event(
        sequence=sequence,
        run_id=capsule.run_id,
        occurred_at=_DYNAMIC_AT,
        kind="request_finished",
        operation_id=_DYNAMIC_OPERATION,
        execution_session_id=_DYNAMIC_SESSION,
        payload={
            "call_sequence": raw.call_sequence,
            "plan_item_id": raw.plan_item_id,
            "attempt_id": raw.attempt_id,
            "request_started_event_id": start.event_id,
            "raw_record_sha256": raw_record_sha256(raw),
            "recovered": False,
        },
    )


@pytest.mark.parametrize(
    "target_state",
    [
        "PREPARED",
        "INTERRUPTED",
        "AMBIGUOUS_INFLIGHT",
        "AUTHENTICATION_STOPPED",
        "GENERATION_COMPLETE",
        "SEALING_INTERRUPTED",
    ],
)
def test_dynamic_capsule_verify_results_are_exact_and_read_only(
    target_state: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    capsule, environment, plan = _dynamic_models(root)
    global _DYNAMIC_RUN_ID
    _DYNAMIC_RUN_ID = capsule.run_id
    prepared_bytes = (root / "events.jsonl").read_bytes()
    events: list[Any] = []
    raw_rows: list[RawAttemptV2] = []
    if target_state in {
        "INTERRUPTED",
        "AMBIGUOUS_INFLIGHT",
        "AUTHENTICATION_STOPPED",
        "GENERATION_COMPLETE",
    }:
        events.append(_dynamic_started(environment))
    if target_state == "AMBIGUOUS_INFLIGHT":
        events.append(_dynamic_start(capsule, plan[0], 2, 0))
    elif target_state == "AUTHENTICATION_STOPPED":
        start = _dynamic_start(capsule, plan[0], 2, 0)
        raw = _dynamic_attempt(capsule, plan[0], 0, authentication=True)
        finish = _dynamic_finish(capsule, start, raw, 3)
        events.extend(
            [
                start,
                finish,
                make_event(
                    sequence=4,
                    run_id=capsule.run_id,
                    occurred_at=_DYNAMIC_AT,
                    kind="authentication_stopped",
                    operation_id=_DYNAMIC_OPERATION,
                    execution_session_id=_DYNAMIC_SESSION,
                    payload={
                        "plan_item_id": raw.plan_item_id,
                        "attempt_id": raw.attempt_id,
                        "origin_request_started_event_id": start.event_id,
                        "recovered": False,
                    },
                ),
            ]
        )
        raw_rows.append(raw)
    elif target_state == "GENERATION_COMPLETE":
        sequence = 2
        last_finish = None
        for call, row in enumerate(plan):
            start = _dynamic_start(capsule, row, sequence, call)
            raw = _dynamic_attempt(capsule, row, call)
            finish = _dynamic_finish(capsule, start, raw, sequence + 1)
            events.extend((start, finish))
            raw_rows.append(raw)
            last_finish = finish
            sequence += 2
        assert last_finish is not None
        events.append(
            make_event(
                sequence=sequence,
                run_id=capsule.run_id,
                occurred_at=_DYNAMIC_AT,
                kind="generation_completed",
                operation_id=_DYNAMIC_OPERATION,
                execution_session_id=_DYNAMIC_SESSION,
                payload={
                    "terminal_plan_item_count": len(plan),
                    "final_plan_ordinal": len(plan) - 1,
                    "origin_request_finished_event_id": last_finish.event_id,
                    "recovered": False,
                },
            )
        )
    elif target_state == "SEALING_INTERRUPTED":
        events.append(
            make_event(
                sequence=1,
                run_id=capsule.run_id,
                occurred_at=_DYNAMIC_AT,
                kind="seal_requested",
                operation_id=_DYNAMIC_SEAL_OPERATION,
                execution_session_id=None,
                payload={
                    "seal_transaction_id": _DYNAMIC_SEAL_TRANSACTION,
                    "expected_generation_status": "incomplete",
                    "prior_event_sequence": 0,
                },
            )
        )
    (root / "events.jsonl").write_bytes(prepared_bytes + b"".join(event_jsonl(e) for e in events))
    (root / "raw.jsonl").write_bytes(b"".join(raw_attempt_jsonl(row) for row in raw_rows))
    before = _snapshot(root)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)
    missing = (
        ()
        if target_state == "GENERATION_COMPLETE"
        else tuple(sorted((row.plan_item_id for row in plan), key=lambda value: value.encode()))
    )
    blocker = {
        "PREPARED": ("never_started",),
        "INTERRUPTED": ("interrupted",),
        "AMBIGUOUS_INFLIGHT": ("ambiguous_inflight",),
        "AUTHENTICATION_STOPPED": ("authentication_stopped",),
        "GENERATION_COMPLETE": (),
        "SEALING_INTERRUPTED": ("never_started",),
    }[target_state]
    assert result.status == "valid"
    assert result.run_id == capsule.run_id
    assert result.state == target_state
    assert result.missing_plan_item_ids == missing
    assert result.operational_blocker_codes == blocker
    assert result.first_error is None
    assert _snapshot(root) == before


def test_verification_scratch_failure_has_null_public_path_and_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)

    class FailedScratch:
        def __init__(self, **_kwargs: object) -> None:
            raise history_module.ScratchError()

    monkeypatch.setattr(history_module, "ExactIdentityRegistry", FailedScratch)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="io_error", path=None, sequence=None)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("missing", "missing_path"),
        ("symlink", "unsafe_path_type"),
        ("directory", "unsafe_path_type"),
    ],
)
def test_unsealed_verification_requires_one_safe_existing_regular_lock_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    code: str,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    lock_path = root / ".laconian.lock"
    lock_path.unlink()
    if mutation == "symlink":
        target = tmp_path / "external-lock"
        target.write_bytes(b"must-not-be-followed")
        lock_path.symlink_to(target)
    elif mutation == "directory":
        lock_path.mkdir()

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code=code, path=".laconian.lock")


def test_lock_path_to_descriptor_replacement_is_unstable_and_original_handle_closes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    real_try_shared = verify_module.try_acquire_shared_lock
    original_descriptors: list[int] = []
    replacement = b"replacement-operational-lock"

    def replace_after_acquire(*args: object, **kwargs: object) -> Any:
        handle = real_try_shared(*args, **kwargs)
        assert handle is not None
        original_descriptors.append(handle.descriptor)
        os.unlink(".laconian.lock", dir_fd=args[0])
        descriptor = os.open(
            ".laconian.lock",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=args[0],
        )
        try:
            assert os.write(descriptor, replacement) == len(replacement)
        finally:
            os.close(descriptor)
        return handle

    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", replace_after_acquire)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="unstable_snapshot", path=".laconian.lock")
    assert len(original_descriptors) == 1
    with pytest.raises(OSError) as caught:
        os.fstat(original_descriptors[0])
    assert caught.value.errno == errno.EBADF
    assert (root / ".laconian.lock").read_bytes() == replacement


def test_public_visible_capsule_path_is_bound_to_the_verified_root_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    displaced = tmp_path / "displaced-verified-capsule"
    real_core = verify_module._verify_core
    core_calls: list[int] = []

    def verify_then_replace_visible_path(descriptor: int) -> VerifyResultV1:
        core_calls.append(descriptor)
        result = real_core(descriptor)
        root.rename(displaced)
        root.mkdir()
        return result

    monkeypatch.setattr(verify_module, "_verify_core", verify_then_replace_visible_path)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert len(core_calls) == 1
    _assert_invalid(result, code="unstable_snapshot", path=None)
    assert displaced.joinpath("capsule.json").is_file()
    assert not root.joinpath("capsule.json").exists()


def test_unrelated_parent_sibling_churn_does_not_invalidate_the_bound_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    sibling = root.parent / "unrelated-sibling"
    real_core = verify_module._verify_core

    def verify_with_sibling_churn(descriptor: int) -> VerifyResultV1:
        result = real_core(descriptor)
        sibling.mkdir()
        return result

    monkeypatch.setattr(verify_module, "_verify_core", verify_with_sibling_churn)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert sibling.is_dir()


@pytest.mark.parametrize("preexisting_invalid", [False, True])
def test_fresh_public_parent_rewalk_close_failure_is_sanitized_once_and_preserves_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preexisting_invalid: bool,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    expected_primary: VerifyResultV1 | None = None
    if preexisting_invalid:
        (root / "manifest.json").write_bytes(b"invalid")
        expected_primary = verify_capsule(root, mode=VerificationMode.PREPARED)
        _assert_invalid(expected_primary, code="noncanonical_json", path="manifest.json")

    real_open_root = verify_module.open_directory_no_follow
    real_close = os.close
    parent_descriptors: list[int] = []
    close_calls: list[int] = []
    secret = "credential=TOP-SECRET host=/private/fresh-parent"

    def tracked_open(path: os.PathLike[str] | str) -> int:
        descriptor = real_open_root(path)
        if Path(path) == root.parent:
            parent_descriptors.append(descriptor)
        return descriptor

    def ambiguous_fresh_close(descriptor: int) -> None:
        if len(parent_descriptors) >= 2 and descriptor == parent_descriptors[1]:
            close_calls.append(descriptor)
            real_close(descriptor)
            raise OSError(errno.EIO, secret)
        real_close(descriptor)

    monkeypatch.setattr(verify_module, "open_directory_no_follow", tracked_open)
    monkeypatch.setattr(verify_module.os, "close", ambiguous_fresh_close)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert len(parent_descriptors) == 2
    assert close_calls == parent_descriptors[1:]
    for descriptor in parent_descriptors:
        with pytest.raises(OSError) as caught:
            os.fstat(descriptor)
        assert caught.value.errno == errno.EBADF
    if expected_primary is None:
        _assert_invalid(result, code="io_error", path=None)
    else:
        assert result == expected_primary
    rendered = canonical_json(result.model_dump(mode="json"))
    assert b"TOP-SECRET" not in rendered
    assert b"/private/fresh-parent" not in rendered


def test_public_lock_postcondition_overrides_a_simultaneous_semantic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    saved = root / ".laconian.lock.saved"
    core_calls: list[int] = []

    def replace_lock_then_fail(descriptor: int) -> VerifyResultV1:
        core_calls.append(descriptor)
        (root / ".laconian.lock").rename(saved)
        (root / ".laconian.lock").write_bytes(b"replacement lock")
        raise verify_module._Failure("noncanonical_json", "manifest.json")

    monkeypatch.setattr(verify_module, "_verify_core", replace_lock_then_fail)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert len(core_calls) == 1
    _assert_invalid(result, code="unstable_snapshot", path=".laconian.lock")
    assert saved.is_file()


def test_operational_lock_bytes_are_excluded_from_prepared_evidence_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / ".laconian.lock").write_bytes(b"opaque operational residue")

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    assert result.first_error is None


@pytest.mark.parametrize("corrupt", [False, True])
def test_public_shared_lock_is_held_across_all_artifact_opens_then_released_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt: bool,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    if corrupt:
        (root / "manifest.json").write_bytes(b"invalid")
    real_try_shared = verify_module.try_acquire_shared_lock
    real_open = os.open
    real_read = os.read
    held = [False]
    close_calls: list[int] = []
    artifact_opens: list[str] = []
    artifact_reads: list[str] = []

    def tracked_try_shared(*args: object, **kwargs: object) -> _TrackedSharedLock | None:
        wrapped = real_try_shared(*args, **kwargs)
        if wrapped is None:
            return None
        assert held == [False]
        held[0] = True
        return _TrackedSharedLock(wrapped, held, close_calls)

    def lock_guarded_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        raw = os.fspath(path)
        if dir_fd is not None and raw != ".laconian.lock":
            parent = _descriptor_path(dir_fd)
            if parent is not None:
                try:
                    parent.relative_to(root)
                except ValueError:
                    pass
                else:
                    assert held == [True]
                    artifact_opens.append(raw)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def lock_guarded_read(descriptor: int, size: int) -> bytes:
        descriptor_path = _descriptor_path(descriptor)
        if descriptor_path is not None:
            try:
                relative = descriptor_path.relative_to(root).as_posix()
            except ValueError:
                pass
            else:
                if relative != ".laconian.lock":
                    assert held == [True]
                    artifact_reads.append(relative)
        return real_read(descriptor, size)

    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", tracked_try_shared)
    monkeypatch.setattr(verify_module.os, "open", lock_guarded_open)
    monkeypatch.setattr(verify_module.os, "read", lock_guarded_read)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == ("invalid" if corrupt else "valid")
    assert artifact_opens
    assert artifact_reads
    assert held == [False]
    assert len(close_calls) == 1
    with pytest.raises(OSError) as caught:
        os.fstat(close_calls[0])
    assert caught.value.errno == errno.EBADF
    descriptor = real_open(
        root / ".laconian.lock",
        os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def test_true_second_process_exclusive_lock_returns_busy_before_artifact_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / "capsule.json").write_bytes(b"corrupt bytes that must not be inspected while busy")
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    child = context.Process(
        target=_hold_exclusive_lock,
        args=(os.fspath(root / ".laconian.lock"), ready, release),
    )
    child.start()
    opened_roots: list[int] = []
    lock_descriptors: list[int] = []
    real_open_root = open_directory_no_follow

    def tracked_root_open(path: os.PathLike[str] | str) -> int:
        descriptor = real_open_root(path)
        opened_roots.append(descriptor)
        return descriptor

    try:
        assert ready.wait(10.0)
        lock_descriptors = _install_artifact_inspection_bombs(monkeypatch, root)
        monkeypatch.setattr(verify_module, "open_directory_no_follow", tracked_root_open)
        result = verify_capsule(root, mode=VerificationMode.PREPARED)
    finally:
        release.set()
        child.join(10.0)
        if child.is_alive():
            child.kill()
            child.join(10.0)

    assert child.exitcode == 0
    assert len(opened_roots) == 3
    for owned_descriptor in opened_roots:
        with pytest.raises(OSError) as root_close:
            os.fstat(owned_descriptor)
        assert root_close.value.errno == errno.EBADF
    assert len(lock_descriptors) == 1
    with pytest.raises(OSError) as lock_close:
        os.fstat(lock_descriptors[0])
    assert lock_close.value.errno == errno.EBADF
    assert result == VerifyResultV1.model_validate(
        {
            "schema_version": "1",
            "status": "busy",
            "run_id": None,
            "state": None,
            "capsule_sha256": None,
            "missing_plan_item_ids": [],
            "operational_blocker_codes": [],
            "warnings": [],
            "first_error": None,
        }
    )


def test_unsupported_unsealed_filesystem_short_circuits_with_exact_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / "capsule.json").write_bytes(b"must not be inspected")
    opened_roots: list[int] = []
    real_open_root = open_directory_no_follow

    def tracked_root_open(path: os.PathLike[str] | str) -> int:
        descriptor = real_open_root(path)
        opened_roots.append(descriptor)
        return descriptor

    def unsupported(*_args: object, **_kwargs: object) -> object:
        raise UnsupportedFilesystemError("unclassified_filesystem")

    lock_descriptors = _install_artifact_inspection_bombs(monkeypatch, root)
    monkeypatch.setattr(verify_module, "open_directory_no_follow", tracked_root_open)
    monkeypatch.setattr(verify_module, "classify_filesystem", unsupported)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert len(opened_roots) == 3
    for owned_descriptor in opened_roots:
        with pytest.raises(OSError) as root_close:
            os.fstat(owned_descriptor)
        assert root_close.value.errno == errno.EBADF
    assert lock_descriptors == []
    assert result.status == "unsupported"
    assert result.run_id is None
    assert result.state is None
    assert result.capsule_sha256 is None
    assert result.missing_plan_item_ids == ()
    assert result.operational_blocker_codes == ()
    assert result.warnings == ()
    assert result.first_error is not None
    assert result.first_error.code == "unsupported_filesystem"
    assert result.first_error.path is None
    assert result.first_error.sequence is None
    assert "unclassified_filesystem" not in result.first_error.explanation


@pytest.mark.parametrize("corrupt", [False, True])
def test_public_verifier_owns_and_closes_root_and_parent_descriptors_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt: bool,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    if corrupt:
        (root / "manifest.json").write_bytes(b"invalid")
    opened: list[int] = []
    real_open_root = open_directory_no_follow

    def tracked_open(path: os.PathLike[str] | str) -> int:
        descriptor = real_open_root(path)
        opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(verify_module, "open_directory_no_follow", tracked_open)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == ("invalid" if corrupt else "valid")
    assert len(opened) == 3
    for owned_descriptor in opened:
        with pytest.raises(OSError) as caught:
            os.fstat(owned_descriptor)
        assert caught.value.errno == errno.EBADF


def test_partial_public_descriptor_acquisition_closes_the_owned_root_before_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)

    class OpenCancelled(BaseException):
        pass

    cancelled = OpenCancelled("credential=TOP-SECRET")
    real_open_root = open_directory_no_follow
    real_close = os.close
    opened: list[int] = []
    close_calls: list[int] = []

    def fail_second_open(path: os.PathLike[str] | str) -> int:
        if opened:
            raise cancelled
        descriptor = real_open_root(path)
        opened.append(descriptor)
        return descriptor

    def tracked_close(descriptor: int) -> None:
        if opened and descriptor == opened[0]:
            close_calls.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(verify_module, "open_directory_no_follow", fail_second_open)
    monkeypatch.setattr(verify_module.os, "close", tracked_close)

    with pytest.raises(OpenCancelled) as caught:
        verify_capsule(root, mode=VerificationMode.PREPARED)

    assert caught.value is cancelled
    assert len(opened) == 1
    assert close_calls == opened
    with pytest.raises(OSError) as closed:
        os.fstat(opened[0])
    assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize("owner", ["lock", "root", "parent"])
@pytest.mark.parametrize("preexisting_invalid", [False, True])
def test_ambiguous_owned_descriptor_close_failure_is_sanitized_once_and_preserves_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: str,
    preexisting_invalid: bool,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    expected_primary: VerifyResultV1 | None = None
    if preexisting_invalid:
        manifest = root / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        expected_primary = verify_capsule(root, mode=VerificationMode.PREPARED)
        _assert_invalid(expected_primary, code="noncanonical_json", path="manifest.json")

    secret = "credential=TOP-SECRET host=/private/teardown"
    close_calls: list[int] = []
    owned_descriptor: list[int] = []
    if owner == "lock":
        real_try_shared = verify_module.try_acquire_shared_lock

        def ambiguous_lock(*args: object, **kwargs: object) -> _AmbiguousCloseLock | None:
            wrapped = real_try_shared(*args, **kwargs)
            if wrapped is None:
                return None
            owned_descriptor.append(wrapped.descriptor)
            return _AmbiguousCloseLock(wrapped, close_calls, secret)

        monkeypatch.setattr(verify_module, "try_acquire_shared_lock", ambiguous_lock)
    else:
        real_open_root = verify_module.open_directory_no_follow
        real_close = os.close
        owned_path = root if owner == "root" else root.parent

        def tracked_root(path: os.PathLike[str] | str) -> int:
            descriptor = real_open_root(path)
            if Path(path) == owned_path:
                owned_descriptor.append(descriptor)
            return descriptor

        def ambiguous_root_close(descriptor: int) -> None:
            if owned_descriptor and descriptor == owned_descriptor[0]:
                close_calls.append(descriptor)
                real_close(descriptor)
                raise OSError(errno.EIO, secret)
            real_close(descriptor)

        monkeypatch.setattr(verify_module, "open_directory_no_follow", tracked_root)
        monkeypatch.setattr(verify_module.os, "close", ambiguous_root_close)

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    expected_owned_count = 2 if owner == "parent" else 1
    assert len(owned_descriptor) == expected_owned_count
    assert close_calls == owned_descriptor[:1]
    for descriptor in owned_descriptor:
        with pytest.raises(OSError) as caught:
            os.fstat(descriptor)
        assert caught.value.errno == errno.EBADF
    if expected_primary is not None:
        assert result == expected_primary
    else:
        _assert_invalid(
            result,
            code="io_error",
            path=".laconian.lock" if owner == "lock" else None,
        )
    rendered = canonical_json(result.model_dump(mode="json"))
    assert b"TOP-SECRET" not in rendered
    assert b"/private/teardown" not in rendered


def test_borrowed_exclusive_lock_descriptor_is_bound_to_the_visible_lock_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    results_fd = open_directory_no_follow(root.parent)
    root_fd = open_directory_no_follow(root)
    lock_fd = os.open(
        ".laconian.lock",
        os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        dir_fd=root_fd,
    )
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    saved = root / ".laconian.lock.saved"
    (root / ".laconian.lock").rename(saved)
    (root / ".laconian.lock").write_bytes(b"replacement")
    plan_id = _jsonl_objects(root / "plan.jsonl")[0]["plan_item_id"]
    valid = VerifyResultV1.model_validate(
        {
            "schema_version": "1",
            "status": "valid",
            "run_id": fixture.prepared.run_id,
            "state": "PREPARED",
            "capsule_sha256": None,
            "missing_plan_item_ids": [plan_id],
            "operational_blocker_codes": ["never_started"],
            "warnings": [],
            "first_error": None,
        }
    )
    core_calls: list[int] = []

    def isolated_core(descriptor: int) -> VerifyResultV1:
        core_calls.append(descriptor)
        return valid

    monkeypatch.setattr(verify_module, "_verify_core", isolated_core)
    try:
        result = verify_module._verify_prepared_capsule_descriptors(
            root_fd,
            results_root_fd=results_fd,
            destination_name=root.name,
            persistent_lock_descriptor=lock_fd,
        )
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(root_fd)
        os.close(results_fd)

    _assert_invalid(result, code="unstable_snapshot", path=".laconian.lock")
    assert core_calls == []


def test_borrowed_destination_postcondition_runs_even_when_semantic_core_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    results_fd = open_directory_no_follow(root.parent)
    root_fd = open_directory_no_follow(root)
    lock_fd = os.open(
        ".laconian.lock",
        os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        dir_fd=root_fd,
    )
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    displaced = tmp_path / "displaced-owned-capsule"
    core_calls: list[int] = []

    def swap_then_fail(descriptor: int) -> VerifyResultV1:
        core_calls.append(descriptor)
        root.rename(displaced)
        root.mkdir()
        raise verify_module._Failure("noncanonical_json", "manifest.json")

    monkeypatch.setattr(verify_module, "_verify_core", swap_then_fail)
    try:
        result = verify_module._verify_prepared_capsule_descriptors(
            root_fd,
            results_root_fd=results_fd,
            destination_name=root.name,
            persistent_lock_descriptor=lock_fd,
        )
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(root_fd)
        os.close(results_fd)

    assert core_calls == [root_fd]
    _assert_invalid(result, code="unstable_snapshot", path=None)


def test_tree_walker_streams_entries_without_inventing_json_or_false_tree_limits() -> None:
    source = inspect.getsource(verify_module._scan_inventory)

    assert "list(iterator)" not in source
    assert "RESOURCE_LIMITS_V1.nesting_depth" not in source


def test_tree_entry_ceiling_is_checked_before_stat_or_retention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    observed = [0]
    stat_calls: list[int] = []

    class FakeEntry:
        def __init__(self, ordinal: int) -> None:
            self.name = f"zzz-{ordinal:03d}"
            self._ordinal = ordinal

        def stat(self, *, follow_symlinks: bool) -> os.stat_result:
            assert follow_symlinks is False
            stat_calls.append(self._ordinal)
            return (root / "capsule.json").stat()

    class FakeScandir:
        def __enter__(self) -> FakeScandir:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> FakeScandir:
            return self

        def __next__(self) -> FakeEntry:
            observed[0] += 1
            if observed[0] > 4:
                raise AssertionError("walker requested an entry after the bounded rejection")
            return FakeEntry(observed[0])

    monkeypatch.setattr(verify_module, "_TREE_ENTRY_CEILING", 3, raising=False)
    monkeypatch.setattr(verify_module.os, "scandir", lambda _descriptor: FakeScandir())
    try:
        with pytest.raises(verify_module._Failure) as caught:
            verify_module._scan_inventory(root_fd)
    finally:
        os.close(root_fd)

    assert caught.value.code == "resource_limit"
    assert observed == [4]
    assert stat_calls == []


def test_tree_walker_sorts_bounded_names_before_stat_and_error_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    root_fd = open_directory_no_follow(root)
    regular = (root / "capsule.json").stat()
    real_scandir = os.scandir

    class FakeEntry:
        def __init__(
            self,
            name: str,
            *,
            stat_error: bool = False,
            metadata: os.stat_result = regular,
        ) -> None:
            self.name = name
            self.stat_error = stat_error
            self.metadata = metadata

        def stat(self, *, follow_symlinks: bool) -> os.stat_result:
            assert follow_symlinks is False
            if self.stat_error:
                raise OSError(errno.EIO, "credential=TOP-SECRET")
            return self.metadata

    class FakeScandir:
        def __enter__(self) -> FakeScandir:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> Iterator[FakeEntry]:
            existing = [FakeEntry(path.name, metadata=path.lstat()) for path in root.iterdir()]
            return iter(
                [
                    FakeEntry("zzz-stat-error", stat_error=True),
                    FakeEntry(
                        "yyy-" + "x" * RESOURCE_LIMITS_V1.bounded_string_bytes,
                        stat_error=False,
                    ),
                    FakeEntry("aaa-unexpected", stat_error=False),
                    *existing,
                ]
            )

    def ordered_scandir(
        descriptor: int | str | bytes | os.PathLike[str],
    ) -> Any:
        if type(descriptor) is int and _descriptor_path(descriptor) == root.resolve():
            return FakeScandir()
        return real_scandir(descriptor)

    monkeypatch.setattr(verify_module.os, "scandir", ordered_scandir)
    try:
        with pytest.raises(verify_module._Failure) as caught:
            verify_module._scan_inventory(root_fd)
    finally:
        os.close(root_fd)

    assert caught.value.code == "unexpected_path"
    assert caught.value.path == "aaa-unexpected"


def test_dynamic_ordinal_paths_accept_width_beyond_three_digits() -> None:
    assert verify_module._file_allowed("inputs/cases/1000.yaml")
    assert verify_module._file_allowed("inputs/protocols/1000-0123456789abcdef.bin")


def test_structure_error_selection_compares_missing_and_unexpected_paths_globally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    (root / "capsule.json").rename(tmp_path / "saved-capsule.json")
    (root / "zzz-unexpected").write_bytes(b"later")

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="missing_path", path="capsule.json")


def test_dynamic_tree_compares_missing_and_unexpected_paths_globally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    missing = "inputs/software/runner/laconian_eval/providers/replay.py"
    unexpected = "inputs/software/runner/laconian_eval/providers/zzz.py"
    (root / missing).rename(tmp_path / "saved-replay.py")
    (root / unexpected).write_bytes(b"unexpected but grammar-compatible")

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="missing_path", path=missing)


def test_declared_dynamic_regular_file_replaced_by_directory_is_unsafe_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    relative = "inputs/software/runner/laconian_eval/providers/fake.py"
    (root / relative).rename(tmp_path / "saved-fake.py")
    (root / relative).mkdir()

    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    _assert_invalid(result, code="unsafe_path_type", path=relative)


def test_reopened_intermediate_directory_must_match_its_inventoried_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    replacement = tmp_path / "replacement-inputs"
    shutil.copytree(root / "inputs", replacement, copy_function=os.link)
    original = tmp_path / "original-inputs"
    real_inventory = verify_module._scan_inventory
    swapped: list[bool] = []

    def swap_after_inventory(descriptor: int) -> Any:
        inventory = real_inventory(descriptor)
        (root / "inputs").rename(original)
        replacement.rename(root / "inputs")
        swapped.append(True)
        return inventory

    monkeypatch.setattr(verify_module, "_scan_inventory", swap_after_inventory)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert swapped == [True]
    _assert_invalid(result, code="unstable_snapshot", path="inputs")


@pytest.mark.parametrize("preexisting_invalid", [False, True])
def test_ambiguous_artifact_descriptor_close_is_sanitized_and_preserves_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preexisting_invalid: bool,
) -> None:
    root, _fixture, _source = _prepared_fixture(tmp_path, monkeypatch)
    expected_primary: VerifyResultV1 | None = None
    if preexisting_invalid:
        manifest = root / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        expected_primary = verify_capsule(root, mode=VerificationMode.PREPARED)
        _assert_invalid(expected_primary, code="noncanonical_json", path="manifest.json")
    real_close = os.close
    close_calls: list[int] = []
    secret = "credential=TOP-SECRET host=/private/artifact-close"

    def ambiguous_close(descriptor: int) -> None:
        descriptor_path = _descriptor_path(descriptor)
        if not close_calls and descriptor_path == (root / "manifest.json").resolve():
            close_calls.append(descriptor)
            real_close(descriptor)
            raise OSError(errno.EIO, secret)
        real_close(descriptor)

    monkeypatch.setattr(verify_module.os, "close", ambiguous_close)
    result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert len(close_calls) == 1
    with pytest.raises(OSError) as caught:
        os.fstat(close_calls[0])
    assert caught.value.errno == errno.EBADF
    if expected_primary is not None:
        assert result == expected_primary
    else:
        _assert_invalid(result, code="io_error", path="manifest.json")
    rendered = canonical_json(result.model_dump(mode="json"))
    assert b"TOP-SECRET" not in rendered
    assert b"/private/artifact-close" not in rendered


def test_verify_module_has_no_provider_credential_source_or_mutation_surface() -> None:
    source = inspect.getsource(verify_module)
    tree = ast.parse(source)
    forbidden_import_fragments = (
        "capture_installed_provenance",
        "load_source_manifest_capture",
        "capture_authored_inputs",
        "importlib.metadata",
    )
    forbidden_modules = (
        "laconian_eval.cli",
        "laconian_eval.capsule.capture",
        "laconian_eval.capsule.provenance",
        "laconian_eval.providers",
        "laconian_eval.runner",
        "openai",
    )
    forbidden_relative_heads = {"capture", "provenance", "providers", "runner"}
    forbidden_construction_names = {
        "AsyncOpenAI",
        "FakeProvider",
        "OpenAI",
        "OpenAIProvider",
        "ReplayProvider",
        "build_import_policy",
        "capture_authored_inputs",
        "capture_installed_provenance",
        "capture_runner_source",
        "capture_runtime_import_state",
        "create_provider",
        "load_source_manifest_capture",
        "provider_from_manifest",
        "run_to_jsonl",
    }
    forbidden_calls = {
        "chmod",
        "chown",
        "fdatasync",
        "fchmod",
        "fchown",
        "fsync",
        "ftruncate",
        "hardlink_to",
        "lchown",
        "link",
        "mkfifo",
        "mknod",
        "mkdir",
        "pwrite",
        "remove",
        "removexattr",
        "rename",
        "replace",
        "rmdir",
        "setxattr",
        "symlink",
        "symlink_to",
        "touch",
        "truncate",
        "unlink",
        "utime",
        "write",
        "write_bytes",
        "write_text",
    }

    def is_forbidden_module(name: str) -> bool:
        return any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden_modules)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not is_forbidden_module(alias.name) for alias in node.names)
            assert not any(
                fragment in alias.name
                for fragment in forbidden_import_fragments
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            aliases = {alias.name for alias in node.names}
            qualified = {f"{module}.{name}" if module else name for name in aliases}
            assert not is_forbidden_module(module)
            if node.level:
                module_head = module.split(".", maxsplit=1)[0]
                assert module_head not in forbidden_relative_heads
                assert not aliases.intersection(forbidden_relative_heads)
            assert not any(
                fragment in name
                for fragment in forbidden_import_fragments
                for name in {module, *qualified}
            )
            if module == "os":
                assert not aliases.intersection(
                    {
                        "*",
                        "environ",
                        "environb",
                        "getenv",
                        "getenvb",
                        "O_APPEND",
                        "O_CREAT",
                        "O_RDWR",
                        "O_EXCL",
                        "O_TRUNC",
                        "O_WRONLY",
                        *forbidden_calls,
                    }
                )
            if module == "laconian_eval" or node.level:
                assert not aliases.intersection({"providers", "runner", "run_to_jsonl"})
            assert not aliases.intersection(forbidden_construction_names)
        elif isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "environb", "getenv", "getenvb"}
            assert node.attr not in {
                "O_APPEND",
                "O_CREAT",
                "O_EXCL",
                "O_RDWR",
                "O_TRUNC",
                "O_WRONLY",
            }
            assert node.attr not in forbidden_calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
                assert node.func.id not in forbidden_construction_names
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls
                assert node.func.attr not in forbidden_construction_names
                if node.func.attr == "import_module":
                    assert not any(
                        isinstance(argument, ast.Constant)
                        and isinstance(argument.value, str)
                        and is_forbidden_module(argument.value)
                        for argument in node.args
                    )

    assert not forbidden_construction_names.intersection(verify_module.__dict__)


class _EnvironmentBomb(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"environment lookup: {key}")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("environment iteration")

    def __len__(self) -> int:
        raise AssertionError("environment length")

    def get(self, key: str, default: str | None = None) -> str | None:
        del default
        return self[key]


def test_runtime_verification_never_reads_environment_or_constructs_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, fixture, _source = _prepared_fixture(
        tmp_path,
        monkeypatch,
        provider_kind="openai",
        api_key_env="LIVE_TEST_API_KEY",
    )
    environment_bomb = _EnvironmentBomb()

    class OsProxy:
        environ = environment_bomb

        def __getattr__(self, name: str) -> object:
            if name in {
                "getenv",
                "getenvb",
                "environb",
                "chmod",
                "chown",
                "fdatasync",
                "fchmod",
                "fchown",
                "fsync",
                "ftruncate",
                "lchown",
                "link",
                "mkfifo",
                "mknod",
                "mkdir",
                "pwrite",
                "remove",
                "removexattr",
                "rename",
                "replace",
                "rmdir",
                "setxattr",
                "symlink",
                "truncate",
                "unlink",
                "utime",
                "write",
                "O_APPEND",
                "O_CREAT",
                "O_RDWR",
                "O_EXCL",
                "O_TRUNC",
                "O_WRONLY",
            }:
                raise AssertionError(f"forbidden runtime surface: {name}")
            return getattr(os, name)

    monkeypatch.setattr(verify_module, "os", OsProxy())

    def lookup_bomb(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("transitive environment lookup")

    with monkeypatch.context() as transitive:
        transitive.setattr(os, "environ", environment_bomb)
        transitive.setattr(os, "environb", environment_bomb, raising=False)
        transitive.setattr(os, "getenv", lookup_bomb)
        transitive.setattr(os, "getenvb", lookup_bomb, raising=False)
        result = verify_capsule(root, mode=VerificationMode.PREPARED)

    assert result.status == "valid"
    _assert_safety_barrier_untouched(fixture.harness)


def test_prepare_real_verifier_uses_borrowed_descriptors_without_reopen_relock_or_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _write_manifest(source)
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(
        monkeypatch,
        results_root,
        skip_post_publish_verification=False,
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("published verification reopened, relocked, or probed")

    monkeypatch.setattr(verify_module, "open_directory_no_follow", forbidden)
    monkeypatch.setattr(verify_module, "try_acquire_shared_lock", forbidden)
    monkeypatch.setattr(verify_module, "classify_filesystem", forbidden)
    real_descriptor_verifier = prepare_module._verify_prepared_capsule_descriptors
    calls: list[tuple[int, int, str, int, VerifyResultV1]] = []

    def descriptor_verifier(
        capsule_directory_fd: int,
        *,
        results_root_fd: int,
        destination_name: str,
        persistent_lock_descriptor: int,
    ) -> VerifyResultV1:
        assert capsule_directory_fd == harness.staging_directory_fd
        assert results_root_fd == harness.results_root_fd
        assert _descriptor_path(capsule_directory_fd) == (results_root / destination_name).resolve()
        lock = _generation(harness, ".laconian.lock")
        assert persistent_lock_descriptor == lock.descriptor
        assert persistent_lock_descriptor in harness.active_files
        assert "lock-ex" in lock.events
        assert "unlock" not in lock.events
        assert "close" not in lock.events
        rename_index = harness.trace.index(("rename", destination_name))
        root_sync_index = harness.trace.index(("fsync", "<results-root>"), rename_index)
        assert rename_index < root_sync_index < len(harness.trace)
        result = real_descriptor_verifier(
            capsule_directory_fd,
            results_root_fd=results_root_fd,
            destination_name=destination_name,
            persistent_lock_descriptor=persistent_lock_descriptor,
        )
        assert result.status == "valid"
        assert result.state == "PREPARED"
        calls.append(
            (
                capsule_directory_fd,
                results_root_fd,
                destination_name,
                persistent_lock_descriptor,
                result,
            )
        )
        return result

    monkeypatch.setattr(
        prepare_module,
        "_verify_prepared_capsule_descriptors",
        descriptor_verifier,
    )

    prepared = prepare_module.prepare_capsule(_request(manifest, results_root))

    assert len(calls) == 1
    assert calls[0][2] == str(prepared.run_id)
    assert calls[0][4].status == "valid"
    assert prepared.path.exists()
    lock = _generation(harness, ".laconian.lock")
    assert lock.events.count("lock-ex") == 1
    assert "lock-sh" not in lock.events
    assert lock.events[-2:] == ["unlock", "close"]
    _assert_safety_barrier_untouched(harness)


def test_prepare_full_verification_failure_after_durable_publication_preserves_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _write_manifest(
        source,
        provider_kind="openai",
        api_key_env="LIVE_TEST_API_KEY",
    )
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(
        monkeypatch,
        results_root,
        skip_post_publish_verification=False,
    )
    original_fsync = _HarnessPosix.fsync
    mutated: list[Path] = []

    def fsync_then_corrupt(self: _HarnessPosix, descriptor: int) -> None:
        original_fsync(self, descriptor)
        if self.published and self._label(descriptor) == "<results-root>" and not mutated:
            visible = next(
                path
                for path in results_root.iterdir()
                if path.is_dir() and not path.name.startswith(".laconian-stage.")
            )
            artifact = visible / "manifest.json"
            artifact.write_bytes(artifact.read_bytes() + b"\n")
            mutated.append(visible)

    monkeypatch.setattr(_HarnessPosix, "fsync", fsync_then_corrupt)

    with pytest.raises(prepare_module.PostPublishVerificationError) as caught:
        prepare_module.prepare_capsule(_request(manifest, results_root))

    assert len(mutated) == 1
    visible = mutated[0]
    assert caught.value.published is True
    assert caught.value.destination_name == visible.name
    assert caught.value.code == "post_publish_verification_failed"
    assert str(caught.value) == "capsule publication failed"
    assert visible.exists()
    assert (visible / "manifest.json").read_bytes().endswith(b"\n")
    assert _generation(harness, ".laconian.lock").events[-2:] == ["unlock", "close"]
    _assert_safety_barrier_untouched(harness)
