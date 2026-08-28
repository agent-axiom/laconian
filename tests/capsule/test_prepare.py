from __future__ import annotations

import ast
import copy
import errno
import fcntl
import importlib
import inspect
import multiprocessing
import os
import resource
import signal
import stat
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import FrozenInstanceError, dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from time import monotonic
from types import MappingProxyType, SimpleNamespace
from typing import Any
from uuid import RFC_4122, UUID

import pytest
import yaml
from capsule_helpers import environment_v1_payload

import laconian_eval.capsule.prepare as prepare_module
from laconian_eval import __version__
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_jsonl,
    sha256_bytes,
    stable_digest,
)
from laconian_eval.capsule.capture import CapturedInputFile, CapturedInputs
from laconian_eval.capsule.events import EventError, event_jsonl, make_prepared_event
from laconian_eval.capsule.filesystem import (
    DestinationCollisionError,
    FilesystemIdentity,
    PostPublishSyncError,
    PreparationFilesystem,
    UnsupportedFilesystemError,
    cleanup_owned_staging,
    create_owned_staging,
)
from laconian_eval.capsule.planning import materialize_case_index, materialize_plan
from laconian_eval.capsule.prepare import (
    PostPublishVerificationError,
    PreparationError,
    PreparedCapsule,
    PrepareRequest,
    prepare_capsule,
)
from laconian_eval.capsule.record_models import (
    CapsuleV1,
    EnvironmentV1,
    InputFileRecordV1,
    InputIndexV1,
    PreparedEventV1,
    PreparedPayloadV1,
    RunnerSourceFileV1,
    RunnerSourceIndexV1,
)

ROOT = Path(__file__).parents[2]
_EVENT_RUN_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
_EVENT_OPERATION_ID = UUID("223e4567-e89b-42d3-a456-426614174001")
_EVENT_TIME = datetime(2026, 8, 27, 12, 34, 56, 123456, tzinfo=UTC)
_DIGESTS = tuple(character * 64 for character in "abcdef")


def _case(case_id: str, scenario_id: str, locale: str, prompt: str) -> dict[str, object]:
    return {
        "id": case_id,
        "scenario_id": scenario_id,
        "locale": locale,
        "category": "direct",
        "prompt": prompt,
    }


def _write_case_file(path: Path) -> bytes:
    data = yaml.safe_dump(
        {
            "schema_version": "1",
            "kind": "response",
            "cases": [
                _case("prepare-001-en", "prepare-001", "en", "Answer in English."),
                _case("prepare-001-ru", "prepare-001", "ru", "Ответьте по-русски."),
            ],
        },
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _manifest_payload(
    *,
    provider_kind: str = "fake",
    api_key_env: str | None = None,
    replay_file: str | None = None,
    case_files: list[str] | None = None,
    arms: list[str] | None = None,
    datasets: list[dict[str, object]] | None = None,
    comparisons: list[dict[str, object]] | None = None,
    protocol_bindings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "2",
        "runner_version": __version__,
        "run_name": "prepare-smoke",
        "provider": {
            "kind": provider_kind,
            "model": "fixture-v1",
            "api_key_env": api_key_env,
            "replay_file": replay_file,
        },
        "case_files": case_files or ["cases/response.yaml"],
        "arms": arms or ["baseline", "concise"],
        "repetitions": 1,
        "arm_order_seed": 17,
        "instruction_placement": "system_suffix",
        "generation": {"max_output_tokens": 128, "temperature": None},
        "retry": {"max_transient_retries": 0, "timeout_seconds": 5.0},
        "price_snapshot": None,
        "capsule": {
            "run_purpose": "integration_smoke",
            "claim_intent": "none",
            "datasets": datasets
            or [
                {
                    "dataset_id": "prepare-dataset",
                    "dataset_version": "fixture-v1",
                    "role": "smoke",
                    "case_schema_version": "1",
                    "case_file_ordinals": [0],
                }
            ],
            "comparisons": comparisons or [],
            "protocol_bindings": protocol_bindings or [],
        },
    }


def _write_manifest(
    root: Path,
    *,
    provider_kind: str = "fake",
    api_key_env: str | None = None,
    replay_file: str | None = None,
    arms: list[str] | None = None,
) -> Path:
    _write_case_file(root / "cases/response.yaml")
    manifest = root / "manifest.yaml"
    manifest.write_bytes(
        yaml.safe_dump(
            _manifest_payload(
                provider_kind=provider_kind,
                api_key_env=api_key_env,
                replay_file=replay_file,
                arms=arms,
            ),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    return manifest


def _runner_source() -> SimpleNamespace:
    data = b'"""Captured fixture runner."""\n'
    source_record = RunnerSourceFileV1(
        path="__init__.py",
        byte_length=len(data),
        sha256=sha256_bytes(data),
    )
    root = stable_digest(
        "laconian-runner-source-v1",
        {
            "package_name": "laconian-eval",
            "files": [source_record.model_dump(mode="json")],
        },
    )
    index = RunnerSourceIndexV1(
        schema_version="1",
        package_name="laconian-eval",
        files=(source_record,),
        runner_source_sha256=root,
    )
    input_record = InputFileRecordV1(
        role="runner_source",
        role_ordinal=0,
        logical_locator="package[laconian_eval]/__init__.py",
        capsule_path="inputs/software/runner/laconian_eval/__init__.py",
        byte_length=len(data),
        sha256=sha256_bytes(data),
        dataset_id=None,
        binding_id=None,
    )
    captured = CapturedInputFile(record=input_record, data=data)
    index_bytes = canonical_json(index.model_dump(mode="json"))
    return SimpleNamespace(
        index=index,
        index_bytes=index_bytes,
        files=(captured,),
        file_bytes=MappingProxyType({"__init__.py": data}),
    )


def _environment(
    runner_source_sha256: str,
    *,
    filesystem_class: str,
    provider_kind: str,
) -> EnvironmentV1:
    payload = copy.deepcopy(environment_v1_payload())
    payload.update(
        {
            "checkout_binding": "unavailable",
            "git_commit": None,
            "git_state": "unavailable",
            "uv_lock": {"availability": "unavailable", "sha256": None},
            "runner_source_sha256": runner_source_sha256,
        }
    )
    runtime = payload["runtime"]
    assert isinstance(runtime, dict)
    runtime["filesystem_class"] = filesystem_class
    provider = payload["provider"]
    assert isinstance(provider, dict)
    if provider_kind == "replay":
        provider.update(
            {
                "kind": "replay",
                "transport_policy": "offline",
                "sdk_distribution": None,
                "sdk_version": None,
            }
        )
    elif provider_kind == "openai":
        dependencies = runtime["dependencies"]
        assert isinstance(dependencies, list)
        dependencies.insert(
            0,
            {"distribution": "openai", "version": "3.0.0", "files_sha256": "0" * 64},
        )
        import_environment = runtime["import_environment"]
        assert isinstance(import_environment, dict)
        import_roots = import_environment["import_roots"]
        assert isinstance(import_roots, list)
        import_roots.insert(
            0,
            {
                "distribution": "openai",
                "module": "openai",
                "origin_member": "openai/__init__.py",
            },
        )
        provider.update(
            {
                "kind": "openai",
                "transport_policy": "openai-direct-v1",
                "sdk_distribution": "openai",
                "sdk_version": "3.0.0",
            }
        )
    return EnvironmentV1.model_validate(payload)


def _descriptor_path(descriptor: int) -> Path | None:
    get_path = getattr(fcntl, "F_GETPATH", None)
    if type(get_path) is int:
        try:
            raw = fcntl.fcntl(descriptor, get_path, b"\x00" * 1024)
            if isinstance(raw, bytes):
                encoded = raw.split(b"\x00", 1)[0]
                if encoded:
                    return Path(os.fsdecode(encoded))
        except OSError:
            pass
    for candidate in (f"/proc/self/fd/{descriptor}", f"/dev/fd/{descriptor}"):
        try:
            return Path(os.readlink(candidate))
        except OSError:
            continue
    return None


@dataclass(slots=True)
class _HarnessPosix:
    results_root: Path
    real_fsync: Any
    real_flock: Any
    trace: list[tuple[str, str]]
    active_files: dict[int, _FileGeneration]
    fsync_counts: Counter[str]
    fail_fsync_at: tuple[str, int] | None = None
    fail_root_fsync_after_publish: bool = False
    platform: str = "darwin"
    published: bool = False
    rename_directory_fds: list[tuple[int, int]] = field(default_factory=list)
    fsync_descriptors: list[tuple[str, int]] = field(default_factory=list)

    def _label(self, descriptor: int) -> str:
        path = _descriptor_path(descriptor)
        if path is None:
            return f"fd:{descriptor}"
        try:
            relative = path.relative_to(self.results_root)
        except ValueError:
            return os.fspath(path)
        if relative == Path("."):
            return "<results-root>"
        parts = relative.parts
        if parts and (parts[0].startswith(".laconian-stage.") or len(parts[0]) == 36):
            parts = parts[1:]
        return "." if not parts else "/".join(parts)

    def rename_noreplace(
        self,
        source_directory_fd: int,
        source_name: str,
        target_directory_fd: int,
        target_name: str,
    ) -> None:
        self.trace.append(("rename", target_name))
        self.rename_directory_fds.append((source_directory_fd, target_directory_fd))
        try:
            os.stat(target_name, dir_fd=target_directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(errno.EEXIST, "capsule publication failed") from None
        os.rename(
            source_name,
            target_name,
            src_dir_fd=source_directory_fd,
            dst_dir_fd=target_directory_fd,
        )
        self.published = True

    def fsync(self, descriptor: int) -> None:
        label = self._label(descriptor)
        self.trace.append(("fsync", label))
        self.fsync_descriptors.append((label, descriptor))
        generation = self.active_files.get(descriptor)
        if generation is not None:
            generation.events.append("fsync")
        self.fsync_counts[label] += 1
        if self.fail_root_fsync_after_publish and self.published and label == "<results-root>":
            raise OSError(errno.EIO, "credential=TOP-SECRET host=/private/build")
        if self.fail_fsync_at == (label, self.fsync_counts[label]):
            raise OSError(errno.EIO, "credential=TOP-SECRET host=/private/build")
        self.real_fsync(descriptor)

    def acquire_lock(self, descriptor: int, *, exclusive: bool, blocking: bool) -> None:
        label = self._label(descriptor)
        self.trace.append(("lock-ex" if exclusive else "lock-sh", label))
        generation = self.active_files.get(descriptor)
        if generation is not None:
            generation.events.append("lock-ex" if exclusive else "lock-sh")
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if not blocking:
            operation |= fcntl.LOCK_NB
        self.real_flock(descriptor, operation)

    def release_lock(self, descriptor: int) -> None:
        label = self._label(descriptor)
        self.trace.append(("unlock", label))
        generation = self.active_files.get(descriptor)
        if generation is not None:
            generation.events.append("unlock")
        self.real_flock(descriptor, fcntl.LOCK_UN)

    def statx_mount_identity(self, _descriptor: int) -> object:
        raise AssertionError("Darwin cleanup must not inspect Linux mount identity")


@dataclass(slots=True)
class _FileGeneration:
    token: int
    path: str
    descriptor: int
    flags: int
    mode: int
    directory_fd: int | None
    events: list[str] = field(default_factory=lambda: ["open"])
    bytes_written: bytearray = field(default_factory=bytearray)
    write_attempts: int = 0
    regular_fstat_seen: bool = False


class _CredentialSpy(Mapping[str, str]):
    def __init__(self, forbidden: tuple[str, ...]) -> None:
        self.forbidden = frozenset(forbidden)
        self.lookups: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.lookups.append(key)
        if key in self.forbidden:
            raise AssertionError("credential value was read")
        raise AssertionError("ambient environment was read during preparation")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("ambient environment was iterated")

    def __len__(self) -> int:
        raise AssertionError("ambient environment size was inspected")

    def get(self, key: str, default: str | None = None) -> str | None:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass(slots=True)
class _PreparationHarness:
    results_root: Path
    runner_source: SimpleNamespace = field(default_factory=_runner_source)
    trace: list[tuple[str, str]] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)
    generations: list[_FileGeneration] = field(default_factory=list)
    active_files: dict[int, _FileGeneration] = field(default_factory=dict)
    mkdir_calls: list[tuple[str, str, int, int | None]] = field(default_factory=list)
    directory_opens: list[tuple[int, int, int, str, int | None]] = field(default_factory=list)
    fsync_counts: Counter[str] = field(default_factory=Counter)
    captured_inputs: CapturedInputs | None = None
    environment: EnvironmentV1 | None = None
    provenance_calls: int = 0
    import_policy_calls: int = 0
    runtime_state_calls: int = 0
    environment_calls: int = 0
    provider_constructions: int = 0
    source_manifest_calls: list[tuple[object, object, object]] = field(default_factory=list)
    authored_input_source_roots: list[object] = field(default_factory=list)
    provenance_arguments: list[tuple[object, object]] = field(default_factory=list)
    project_filesystem_classes: list[str] = field(default_factory=list)
    preparation_filesystem_calls: int = 0
    results_root_open_paths: list[object] = field(default_factory=list)
    results_root_fd: int | None = None
    results_root_identity: tuple[int, int] | None = None
    results_root_fd_closed: bool = False
    staging_directory_fd: int | None = None
    credentials: _CredentialSpy | None = None
    real_open: Any = None
    real_close: Any = None
    swapped_results_root: Path | None = None
    results_root_close_attempts: int = 0
    close_sentinel_path: Path | None = None
    close_sentinel_fd: int | None = None
    close_sentinel_identity: tuple[int, int] | None = None
    posix: _HarnessPosix | None = None


def _install_harness(
    monkeypatch: pytest.MonkeyPatch,
    results_root: Path,
    *,
    fail_root_fsync_after_publish: bool = False,
    filesystem_error: bool = False,
    fail_fsync_at: tuple[str, int] | None = None,
    fail_write_path: str | None = None,
    exercise_short_writes: bool = False,
    forbidden_credentials: tuple[str, ...] = ("LIVE_TEST_API_KEY",),
    swap_results_root_after_open: bool = False,
    forbid_preparation_filesystem: bool = False,
    inject_ambiguous_results_root_close: bool = False,
) -> _PreparationHarness:
    harness = _PreparationHarness(results_root=results_root)
    real_open = os.open
    real_close = os.close
    real_fstat = os.fstat
    real_write = os.write
    real_fsync = os.fsync
    real_mkdir = os.mkdir
    real_flock = fcntl.flock

    class PrepareOsProxy:
        def __getattr__(self, name: str) -> object:
            return getattr(os, name)

    monkeypatch.setattr(prepare_module, "os", PrepareOsProxy())
    harness.real_open = real_open
    harness.real_close = real_close
    if inject_ambiguous_results_root_close:
        sentinel_path = results_root.parent / f".{results_root.name}-close-sentinel"
        sentinel_path.write_bytes(b"sentinel-owned-by-test")
        harness.close_sentinel_path = sentinel_path
    posix = _HarnessPosix(
        results_root=results_root,
        real_fsync=real_fsync,
        real_flock=real_flock,
        trace=harness.trace,
        active_files=harness.active_files,
        fsync_counts=harness.fsync_counts,
        fail_fsync_at=fail_fsync_at,
        fail_root_fsync_after_publish=fail_root_fsync_after_publish,
    )
    harness.posix = posix

    def under_results_root(descriptor: int) -> bool:
        path = _descriptor_path(descriptor)
        if path is None:
            return False
        try:
            path.relative_to(results_root)
        except ValueError:
            return False
        return True

    def tracking_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if dir_fd is None:
            descriptor = real_open(path, flags, mode)
        else:
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        metadata = real_fstat(descriptor)
        if stat.S_ISDIR(metadata.st_mode):
            harness.directory_opens.append(
                (metadata.st_dev, metadata.st_ino, descriptor, os.fspath(path), dir_fd)
            )
        elif stat.S_ISREG(metadata.st_mode) and under_results_root(descriptor):
            label = posix._label(descriptor)
            generation = _FileGeneration(
                token=len(harness.generations),
                path=label,
                descriptor=descriptor,
                flags=flags,
                mode=mode,
                directory_fd=dir_fd,
            )
            harness.generations.append(generation)
            harness.active_files[descriptor] = generation
            harness.trace.append(("open", label))
            if flags & os.O_CREAT:
                harness.created_files.append(label)
        return descriptor

    def tracking_fstat(descriptor: int) -> os.stat_result:
        metadata = real_fstat(descriptor)
        generation = harness.active_files.get(descriptor)
        if generation is not None:
            generation.events.append("fstat")
            generation.regular_fstat_seen = stat.S_ISREG(metadata.st_mode)
            harness.trace.append(("fstat", generation.path))
        return metadata

    def tracking_write(descriptor: int, data: Any) -> int:
        generation = harness.active_files.get(descriptor)
        if generation is None:
            return real_write(descriptor, data)
        raw = bytes(data)
        generation.write_attempts += 1
        harness.trace.append(("write-attempt", generation.path))
        if fail_write_path == generation.path:
            raise OSError(errno.EIO, "credential=TOP-SECRET host=/private/build")
        if exercise_short_writes and generation.write_attempts == 1:
            raise InterruptedError(errno.EINTR, "interrupted system call")
        if exercise_short_writes and generation.write_attempts == 2 and len(raw) > 1:
            raw = raw[: max(1, len(raw) // 2)]
        written = real_write(descriptor, raw)
        generation.events.append("write")
        generation.bytes_written.extend(raw[:written])
        harness.trace.append(("write", generation.path))
        return written

    def tracking_fsync(descriptor: int) -> None:
        posix.fsync(descriptor)

    def tracking_close(descriptor: int) -> None:
        generation = harness.active_files.get(descriptor)
        if generation is not None:
            generation.events.append("close")
            harness.trace.append(("close", generation.path))
        if descriptor == harness.results_root_fd:
            harness.results_root_close_attempts += 1
            if inject_ambiguous_results_root_close:
                if harness.results_root_close_attempts > 1:
                    return
                real_close(descriptor)
                harness.active_files.pop(descriptor, None)
                harness.results_root_fd_closed = True
                harness.trace.append(("close", "<results-root>"))
                assert harness.close_sentinel_path is not None
                sentinel_fd = real_open(
                    harness.close_sentinel_path,
                    os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                )
                if sentinel_fd != descriptor:
                    os.dup2(sentinel_fd, descriptor, inheritable=False)
                    real_close(sentinel_fd)
                    sentinel_fd = descriptor
                sentinel_metadata = real_fstat(sentinel_fd)
                harness.close_sentinel_fd = sentinel_fd
                harness.close_sentinel_identity = (
                    sentinel_metadata.st_dev,
                    sentinel_metadata.st_ino,
                )
                raise OSError(
                    errno.EIO,
                    "credential=TOP-SECRET host=/private/close",
                )
            harness.results_root_fd_closed = True
            harness.trace.append(("close", "<results-root>"))
        try:
            real_close(descriptor)
        finally:
            harness.active_files.pop(descriptor, None)

    def tracking_mkdir(
        path: os.PathLike[str] | str,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        raw_path = os.fspath(path)
        parent = None if dir_fd is None else posix._label(dir_fd)
        if dir_fd is not None and under_results_root(dir_fd):
            label = raw_path if parent in (".", "<results-root>") else f"{parent}/{raw_path}"
            harness.mkdir_calls.append((label, raw_path, mode, dir_fd))
            harness.trace.append(("mkdir", label))
        if dir_fd is None:
            real_mkdir(path, mode)
        else:
            real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(prepare_module.os, "open", tracking_open)
    monkeypatch.setattr(prepare_module.os, "fstat", tracking_fstat)
    monkeypatch.setattr(prepare_module.os, "write", tracking_write)
    monkeypatch.setattr(prepare_module.os, "fsync", tracking_fsync)
    monkeypatch.setattr(prepare_module.os, "close", tracking_close)
    monkeypatch.setattr(prepare_module.os, "mkdir", tracking_mkdir)
    monkeypatch.setattr(prepare_module, "PosixOps", lambda: posix)

    def skip_task_1_11_verification(
        _capsule_directory_fd: int,
        *,
        results_root_fd: int,
        destination_name: str,
        persistent_lock_descriptor: int,
    ) -> None:
        del results_root_fd, destination_name, persistent_lock_descriptor

    monkeypatch.setattr(
        prepare_module,
        "_post_publish_verify",
        skip_task_1_11_verification,
    )

    credentials = _CredentialSpy(forbidden_credentials)
    harness.credentials = credentials
    for module_name, attribute in (
        ("laconian_eval.providers.fake", "FakeProvider"),
        ("laconian_eval.providers.replay", "ReplayProvider"),
        ("laconian_eval.providers.openai", "OpenAIProvider"),
    ):
        module = importlib.import_module(module_name)

        def provider_bomb(*_args: object, **_kwargs: object) -> object:
            harness.provider_constructions += 1
            raise AssertionError("provider was constructed during preparation")

        monkeypatch.setattr(module, attribute, provider_bomb)
        monkeypatch.setattr(prepare_module, attribute, provider_bomb, raising=False)
    for factory_name in ("_provider", "create_provider", "provider_from_manifest"):
        monkeypatch.setattr(prepare_module, factory_name, provider_bomb, raising=False)
    monkeypatch.setattr(prepare_module.os, "environ", credentials)

    real_root_open = open_directory_no_follow

    def tracked_root_open(path: os.PathLike[str] | str) -> int:
        harness.results_root_open_paths.append(path)
        descriptor = real_root_open(path)
        metadata = real_fstat(descriptor)
        harness.directory_opens.append(
            (metadata.st_dev, metadata.st_ino, descriptor, os.fspath(path), None)
        )
        harness.results_root_fd = descriptor
        harness.results_root_identity = (metadata.st_dev, metadata.st_ino)
        if swap_results_root_after_open:
            displaced = results_root.with_name(f"{results_root.name}.opened")
            os.rename(results_root, displaced)
            real_mkdir(results_root, 0o700)
            harness.swapped_results_root = displaced
        return descriptor

    monkeypatch.setattr(prepare_module, "open_directory_no_follow", tracked_root_open)

    @contextmanager
    def fake_preparation_filesystem(
        results_root_fd: int,
        operation_id: UUID,
        *,
        posix: _HarnessPosix,
        contention_probe: object | None = None,
    ) -> Iterator[PreparationFilesystem]:
        del contention_probe
        harness.preparation_filesystem_calls += 1
        if forbid_preparation_filesystem:
            raise AssertionError("filesystem preparation ran after results-root identity drift")
        assert results_root_fd == harness.results_root_fd
        if filesystem_error:
            raise UnsupportedFilesystemError("capability_probe_failed")
        staging = create_owned_staging(results_root_fd, operation_id)
        harness.staging_directory_fd = staging.descriptor
        workspace = PreparationFilesystem(
            filesystem_identity=FilesystemIdentity(
                filesystem_class="apfs",
                device=os.fstat(results_root_fd).st_dev,
                mount_id=None,
            ),
            staging=staging,
            _posix=posix,
        )
        try:
            yield workspace
        except BaseException:
            if staging.state == "owned":
                cleanup_owned_staging(staging, posix=posix)
            with suppress(OSError):
                staging.close()
            raise
        else:
            if staging.state == "owned":
                cleanup_owned_staging(staging, posix=posix)
            with suppress(OSError):
                staging.close()

    monkeypatch.setattr(prepare_module, "preparation_filesystem", fake_preparation_filesystem)

    real_load_source = prepare_module.load_source_manifest_capture
    real_capture_inputs = prepare_module.capture_authored_inputs

    def load_source(
        path: object,
        *,
        input_root: object,
        invocation_cwd: object,
    ) -> object:
        harness.source_manifest_calls.append((path, input_root, invocation_cwd))
        return real_load_source(
            path,
            input_root=input_root,
            invocation_cwd=invocation_cwd,
        )

    def capture_inputs(source: object, *, source_root: object) -> CapturedInputs:
        harness.authored_input_source_roots.append(source_root)
        return real_capture_inputs(source, source_root=source_root)

    monkeypatch.setattr(prepare_module, "load_source_manifest_capture", load_source)
    monkeypatch.setattr(prepare_module, "capture_authored_inputs", capture_inputs)

    def capture_provenance(
        captured_inputs: CapturedInputs,
        *,
        source_root: object,
        container_image_digest: str | None,
    ) -> SimpleNamespace:
        harness.provenance_calls += 1
        harness.provenance_arguments.append((source_root, container_image_digest))
        harness.captured_inputs = captured_inputs
        return SimpleNamespace(
            runner_source=harness.runner_source,
            container_image_digest=(
                None
                if container_image_digest is None
                else container_image_digest.removeprefix("sha256:")
            ),
        )

    runtime_state = object()

    def capture_runtime_state() -> object:
        harness.runtime_state_calls += 1
        return runtime_state

    def build_policy(
        provenance: object,
        *,
        runtime_state: object,
    ) -> SimpleNamespace:
        assert isinstance(provenance, SimpleNamespace)
        assert provenance.runner_source is harness.runner_source
        assert runtime_state is not None
        assert runtime_state is runtime_state_sentinel
        harness.import_policy_calls += 1
        payload = environment_v1_payload()["runtime"]
        assert isinstance(payload, dict)
        return SimpleNamespace(import_environment=payload["import_environment"])

    def project_environment(
        provenance: object,
        *,
        import_environment: object,
        filesystem_class: str,
    ) -> EnvironmentV1:
        del import_environment
        assert isinstance(provenance, SimpleNamespace)
        assert provenance.runner_source is harness.runner_source
        harness.environment_calls += 1
        harness.project_filesystem_classes.append(filesystem_class)
        assert harness.captured_inputs is not None
        provider_kind = harness.captured_inputs.resolved_manifest.provider.kind
        harness.environment = _environment(
            harness.runner_source.index.runner_source_sha256,
            filesystem_class=filesystem_class,
            provider_kind=provider_kind,
        )
        if provenance.container_image_digest is not None:
            environment_payload = harness.environment.model_dump(mode="python")
            environment_payload["container_image_digest"] = provenance.container_image_digest
            harness.environment = EnvironmentV1.model_validate(environment_payload)
        return harness.environment

    runtime_state_sentinel = runtime_state
    monkeypatch.setattr(prepare_module, "capture_installed_provenance", capture_provenance)
    monkeypatch.setattr(prepare_module, "capture_runtime_import_state", capture_runtime_state)
    monkeypatch.setattr(prepare_module, "build_import_policy", build_policy)
    monkeypatch.setattr(prepare_module, "project_environment", project_environment)
    return harness


def _request(
    manifest: Path,
    results_root: Path,
    *,
    invocation_cwd: Path | None = None,
    input_root: Path | None = None,
    source_root: Path | None = None,
    container_image_digest: str | None = None,
) -> PrepareRequest:
    return PrepareRequest(
        manifest_path=manifest,
        results_root=results_root,
        invocation_cwd=manifest.parent if invocation_cwd is None else invocation_cwd,
        input_root=input_root,
        source_root=source_root,
        container_image_digest=container_image_digest,
    )


def _generation(harness: _PreparationHarness, path: str) -> _FileGeneration:
    matches = [item for item in harness.generations if item.path == path]
    assert len(matches) == 1, f"expected one open generation for {path}: {matches!r}"
    return matches[0]


def _assert_safety_barrier_untouched(
    harness: _PreparationHarness,
    credential_name: str = "LIVE_TEST_API_KEY",
) -> None:
    assert harness.provider_constructions == 0
    assert harness.credentials is not None
    assert harness.credentials.lookups == []
    assert credential_name not in harness.credentials.lookups


def _assert_ambiguous_root_close_was_not_retried(
    harness: _PreparationHarness,
) -> None:
    assert harness.results_root_close_attempts == 1
    assert harness.close_sentinel_fd == harness.results_root_fd
    assert harness.close_sentinel_fd is not None
    assert harness.close_sentinel_identity is not None
    descriptor = harness.close_sentinel_fd
    try:
        metadata = os.fstat(descriptor)
        assert (metadata.st_dev, metadata.st_ino) == harness.close_sentinel_identity
        os.lseek(descriptor, 0, os.SEEK_SET)
        assert os.read(descriptor, 1024) == b"sentinel-owned-by-test"
    finally:
        harness.real_close(descriptor)
        harness.close_sentinel_fd = None


def _artifact_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for path in root.rglob("*"):
        suffix = "/" if path.is_dir() else ""
        paths.add(path.relative_to(root).as_posix() + suffix)
    return paths


def _load_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider_kind: str = "fake",
    api_key_env: str | None = None,
    harness_options: Mapping[str, Any] | None = None,
) -> tuple[PreparedCapsule, _PreparationHarness, Path]:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _write_manifest(
        source,
        provider_kind=provider_kind,
        api_key_env=api_key_env,
    )
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(
        monkeypatch,
        results_root,
        **({} if harness_options is None else dict(harness_options)),
    )
    prepared = prepare_capsule(_request(manifest, results_root))
    return prepared, harness, manifest


def test_make_prepared_event_has_exact_canonical_identity_and_bytes() -> None:
    event = make_prepared_event(
        run_id=_EVENT_RUN_ID,
        operation_id=_EVENT_OPERATION_ID,
        occurred_at=_EVENT_TIME,
        manifest_sha256=_DIGESTS[0],
        input_index_sha256=_DIGESTS[1],
        case_index_sha256=_DIGESTS[2],
        plan_sha256=_DIGESTS[3],
        environment_sha256=_DIGESTS[4],
        runner_source_sha256=_DIGESTS[5],
    )
    without_id = event.model_dump(mode="json")
    del without_id["event_id"]
    expected_id = stable_digest("laconian-event-v1", without_id)

    assert event == PreparedEventV1.model_validate(
        {
            "schema_version": "1",
            "sequence": 0,
            "event_id": expected_id,
            "run_id": str(_EVENT_RUN_ID),
            "occurred_at": "2026-08-27T12:34:56.123456Z",
            "kind": "prepared",
            "operation_id": str(_EVENT_OPERATION_ID),
            "execution_session_id": None,
            "payload": {
                "manifest_sha256": _DIGESTS[0],
                "input_index_sha256": _DIGESTS[1],
                "case_index_sha256": _DIGESTS[2],
                "plan_sha256": _DIGESTS[3],
                "environment_sha256": _DIGESTS[4],
                "runner_source_sha256": _DIGESTS[5],
            },
        }
    )
    assert event_jsonl(event) == canonical_json(event.model_dump(mode="json")) + b"\n"


def test_event_jsonl_rejects_a_noncanonical_event_id() -> None:
    event = PreparedEventV1.model_validate(
        {
            "schema_version": "1",
            "sequence": 0,
            "event_id": "0" * 64,
            "run_id": str(_EVENT_RUN_ID),
            "occurred_at": "2026-08-27T12:34:56.123456Z",
            "kind": "prepared",
            "operation_id": str(_EVENT_OPERATION_ID),
            "execution_session_id": None,
            "payload": {
                "manifest_sha256": _DIGESTS[0],
                "input_index_sha256": _DIGESTS[1],
                "case_index_sha256": _DIGESTS[2],
                "plan_sha256": _DIGESTS[3],
                "environment_sha256": _DIGESTS[4],
                "runner_source_sha256": _DIGESTS[5],
            },
        }
    )

    with pytest.raises(EventError) as caught:
        event_jsonl(event)

    assert caught.value.code == "event_id_mismatch"
    assert str(caught.value) == "capsule event rejected"


@pytest.mark.parametrize("corruption", ["top_level", "nested_payload"])
def test_event_jsonl_strictly_revalidates_forged_models_before_identity(
    corruption: str,
) -> None:
    payload_values = {
        "manifest_sha256": _DIGESTS[0],
        "input_index_sha256": _DIGESTS[1],
        "case_index_sha256": _DIGESTS[2],
        "plan_sha256": _DIGESTS[3],
        "environment_sha256": _DIGESTS[4],
        "runner_source_sha256": _DIGESTS[5],
    }
    sequence = 0
    if corruption == "top_level":
        sequence = 1
    else:
        payload_values["manifest_sha256"] = "TOP-SECRET /private/build"
    forged_payload = PreparedPayloadV1.model_construct(**payload_values)
    identity_payload = {
        "schema_version": "1",
        "sequence": sequence,
        "run_id": str(_EVENT_RUN_ID),
        "occurred_at": "2026-08-27T12:34:56.123456Z",
        "kind": "prepared",
        "operation_id": str(_EVENT_OPERATION_ID),
        "execution_session_id": None,
        "payload": forged_payload.model_dump(mode="json", warnings=False),
    }
    forged_values = dict(identity_payload)
    forged_values["event_id"] = stable_digest("laconian-event-v1", identity_payload)
    forged_values["payload"] = forged_payload
    forged = PreparedEventV1.model_construct(**forged_values)

    with pytest.raises(EventError) as caught:
        event_jsonl(forged)

    assert caught.value.code == "invalid_event"
    assert str(caught.value) == "capsule event rejected"
    assert "TOP-SECRET" not in str(caught.value)
    assert "TOP-SECRET" not in repr(caught.value)


def test_make_prepared_event_rejects_invalid_boundary_values_without_echo() -> None:
    with pytest.raises(EventError) as caught:
        make_prepared_event(
            run_id="TOP-SECRET /private/build",  # type: ignore[arg-type]
            operation_id=_EVENT_OPERATION_ID,
            occurred_at=_EVENT_TIME,
            manifest_sha256=_DIGESTS[0],
            input_index_sha256=_DIGESTS[1],
            case_index_sha256=_DIGESTS[2],
            plan_sha256=_DIGESTS[3],
            environment_sha256=_DIGESTS[4],
            runner_source_sha256=_DIGESTS[5],
        )

    assert caught.value.code == "invalid_event"
    assert str(caught.value) == "capsule event rejected"


def test_prepare_request_and_public_entrypoint_are_frozen_and_provider_free(
    tmp_path: Path,
) -> None:
    request = PrepareRequest(
        manifest_path=tmp_path / "manifest.yaml",
        results_root=tmp_path / "results",
        invocation_cwd=tmp_path,
        input_root=None,
        source_root=None,
        container_image_digest=None,
    )
    parameters = inspect.signature(prepare_capsule).parameters

    assert set(request.__dataclass_fields__) == {
        "manifest_path",
        "results_root",
        "invocation_cwd",
        "input_root",
        "source_root",
        "container_image_digest",
    }
    assert set(parameters) == {"request"}
    assert "provider_factory" not in parameters
    assert "credential" not in " ".join(parameters).lower()
    with pytest.raises(FrozenInstanceError):
        request.results_root = tmp_path / "elsewhere"  # type: ignore[misc]


def test_prepare_module_has_no_provider_import_factory_or_environment_read_surface() -> None:
    source_path = ROOT / "src/laconian_eval/capsule/prepare.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=os.fspath(source_path))
    forbidden_construction_names = {
        "AsyncOpenAI",
        "FakeProvider",
        "OpenAI",
        "OpenAIProvider",
        "ReplayProvider",
        "run_to_jsonl",
    }
    forbidden_modules = (
        "laconian_eval.cli",
        "laconian_eval.providers",
        "laconian_eval.runner",
        "openai",
    )

    def is_forbidden_module(name: str) -> bool:
        return any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden_modules)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not is_forbidden_module(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert not is_forbidden_module(node.module or "")
            if node.module == "os":
                assert not any(
                    alias.name in {"*", "environ", "environb", "getenv", "getenvb"}
                    for alias in node.names
                )
            if node.module == "laconian_eval":
                assert not any(
                    alias.name in {"providers", "runner", "run_to_jsonl"} for alias in node.names
                )
            assert not any(alias.name in forbidden_construction_names for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_construction_names
                assert node.func.id not in {
                    "create_provider",
                    "provider_from_manifest",
                    "_provider",
                }
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_construction_names
            if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                assert not any(
                    isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                    and is_forbidden_module(argument.value)
                    for argument in node.args
                )
        elif isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "environb", "getenv", "getenvb"}
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not is_forbidden_module(node.value)

    assert not forbidden_construction_names.intersection(prepare_module.__dict__)


def test_prepared_capsule_has_exact_frozen_provider_free_result_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, harness, _manifest = _load_success(tmp_path, monkeypatch)

    assert set(prepared.__dataclass_fields__) == {
        "path",
        "run_id",
        "operation_id",
        "capsule",
    }
    assert not any(
        "provider" in name or "credential" in name for name in prepared.__dataclass_fields__
    )
    with pytest.raises(FrozenInstanceError):
        prepared.path = tmp_path / "replacement"  # type: ignore[misc]
    assert harness.results_root_fd_closed is True
    assert not harness.active_files
    _assert_safety_barrier_untouched(harness)


def test_prepare_writes_the_exact_owned_tree_and_hash_commitments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, harness, manifest_path = _load_success(tmp_path, monkeypatch)
    capsule_root = prepared.path

    assert capsule_root.is_absolute()
    assert capsule_root == harness.results_root / str(prepared.run_id)
    assert prepared.run_id.version == 4 and prepared.run_id.variant == RFC_4122
    assert prepared.operation_id.version == 4 and prepared.operation_id.variant == RFC_4122
    assert prepared.run_id != prepared.operation_id
    assert prepared.capsule.run_id == prepared.run_id
    assert _artifact_paths(capsule_root) == {
        ".laconian.lock",
        "capsule.json",
        "case-index.jsonl",
        "environment.json",
        "events.jsonl",
        "inputs/",
        "inputs/arms/",
        "inputs/arms/baseline.txt",
        "inputs/arms/concise.txt",
        "inputs/cases/",
        "inputs/cases/000.yaml",
        "inputs/index.json",
        "inputs/software/",
        "inputs/software/runner-source.json",
        "inputs/software/runner/",
        "inputs/software/runner/laconian_eval/",
        "inputs/software/runner/laconian_eval/__init__.py",
        "manifest.json",
        "plan.jsonl",
        "raw.jsonl",
    }
    assert capsule_root.joinpath("raw.jsonl").read_bytes() == b""
    assert capsule_root.joinpath(".laconian.lock").read_bytes() == b""
    assert capsule_root.joinpath("inputs/arms/baseline.txt").read_bytes() == b""
    assert capsule_root.joinpath("inputs/arms/concise.txt").read_bytes() == b"Answer concisely."
    assert capsule_root.joinpath("inputs/software/runner-source.json").read_bytes() == (
        harness.runner_source.index_bytes
    )
    assert not any(
        path.name in {"judgments", "scored", "reports"} for path in capsule_root.rglob("*")
    )
    for path in capsule_root.rglob("*"):
        mode = path.lstat().st_mode
        assert not stat.S_ISLNK(mode)
        assert stat.S_ISDIR(mode) or stat.S_ISREG(mode)

    capsule_bytes = capsule_root.joinpath("capsule.json").read_bytes()
    capsule = CapsuleV1.model_validate_json(capsule_bytes)
    assert capsule_bytes == canonical_json(capsule.model_dump(mode="json"))
    assert not capsule_bytes.endswith(b"\n")
    assert capsule == prepared.capsule
    assert capsule.source_manifest_commitment_sha256 == sha256_bytes(manifest_path.read_bytes())
    assert capsule.manifest_sha256 == sha256_bytes(
        capsule_root.joinpath("manifest.json").read_bytes()
    )
    assert capsule.input_index_sha256 == sha256_bytes(
        capsule_root.joinpath("inputs/index.json").read_bytes()
    )
    assert capsule.case_index_sha256 == sha256_bytes(
        capsule_root.joinpath("case-index.jsonl").read_bytes()
    )
    assert capsule.plan_sha256 == sha256_bytes(capsule_root.joinpath("plan.jsonl").read_bytes())
    assert capsule.environment_sha256 == sha256_bytes(
        capsule_root.joinpath("environment.json").read_bytes()
    )
    assert capsule.runner_source_sha256 == harness.runner_source.index.runner_source_sha256
    assert capsule.run_purpose == "integration_smoke"
    assert capsule.claim_intent == "none"
    assert capsule.arm_order_seed == 17

    for path in (capsule_root, *(item for item in capsule_root.rglob("*") if item.is_dir())):
        assert stat.S_IMODE(path.stat().st_mode) & ~0o700 == 0
    for path in (item for item in capsule_root.rglob("*") if item.is_file()):
        assert stat.S_IMODE(path.stat().st_mode) & ~0o600 == 0


def test_prepare_assembles_the_complete_input_index_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, harness, _manifest_path = _load_success(tmp_path, monkeypatch)
    assert harness.captured_inputs is not None
    index_bytes = prepared.path.joinpath("inputs/index.json").read_bytes()
    index = InputIndexV1.model_validate_json(index_bytes)
    expected_records = tuple(
        sorted(
            (
                *harness.captured_inputs.records,
                *(item.record for item in harness.runner_source.files),
            ),
            key=lambda item: item.capsule_path.encode("utf-8"),
        )
    )

    assert index_bytes == canonical_json(index.model_dump(mode="json"))
    assert index.manifest_sha256 == harness.captured_inputs.manifest_sha256
    assert index.files == expected_records
    assert len(index.files) == len({item.capsule_path for item in index.files})
    assert [item.role_ordinal for item in index.files if item.role == "runner_source"] == [0]
    assert [item.capsule_path for item in index.files] == sorted(
        (item.capsule_path for item in index.files),
        key=lambda value: value.encode("utf-8"),
    )


def test_input_index_and_disk_bind_every_case_arm_replay_protocol_and_runner_byte_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = tmp_path / "authored"
    case_bytes = _write_case_file(input_root / "cases/response.yaml")
    replay_bytes = b"description: exact replay bytes\r\n"
    replay_path = input_root / "provider/replay.yaml"
    replay_path.parent.mkdir(parents=True)
    replay_path.write_bytes(replay_bytes)
    protocol_bytes = b"\x00protocol\xffexact\r\n"
    protocol_path = input_root / "protocols/rubric.bin"
    protocol_path.parent.mkdir(parents=True)
    protocol_path.write_bytes(protocol_bytes)
    binding_id = "rubric-v1"
    comparison = {
        "comparison_id": "if-vs-concise",
        "left_arm": "if",
        "right_arm": "concise",
        "role": "primary",
    }
    binding = {
        "binding_id": binding_id,
        "kind": "org.example.rubric",
        "schema_id": "org.example.rubric.v1",
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
    manifest = tmp_path / "manifests/complete.yaml"
    manifest.parent.mkdir()
    manifest.write_bytes(
        yaml.safe_dump(
            _manifest_payload(
                provider_kind="replay",
                replay_file="provider/replay.yaml",
                arms=["baseline", "concise", "caveman", "if"],
                comparisons=[comparison],
                protocol_bindings=[binding],
            ),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    invocation_cwd = tmp_path / "cwd"
    invocation_cwd.mkdir()
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(monkeypatch, results_root)

    prepared = prepare_capsule(
        _request(
            manifest,
            results_root,
            invocation_cwd=invocation_cwd,
            input_root=input_root,
            source_root=ROOT,
        )
    )

    assert harness.captured_inputs is not None
    captured_by_path = {item.record.capsule_path: item for item in harness.captured_inputs.files}
    runner_by_path = {item.record.capsule_path: item for item in harness.runner_source.files}
    all_captured = captured_by_path | runner_by_path
    index_bytes = prepared.path.joinpath("inputs/index.json").read_bytes()
    index = InputIndexV1.model_validate_json(index_bytes)
    indexed_paths = [record.capsule_path for record in index.files]
    creation_counts = Counter(harness.created_files)

    assert index_bytes == canonical_json(index.model_dump(mode="json"))
    assert Counter(indexed_paths) == Counter({path: 1 for path in all_captured})
    assert {record.role for record in index.files} == {
        "case",
        "arm",
        "replay",
        "protocol",
        "runner_source",
    }
    assert captured_by_path["inputs/cases/000.yaml"].data == case_bytes
    assert captured_by_path["inputs/provider/replay.yaml"].data == replay_bytes
    protocol_destination = (
        f"inputs/protocols/000-{sha256_bytes(binding_id.encode('utf-8'))[:16]}.bin"
    )
    assert captured_by_path[protocol_destination].data == protocol_bytes
    assert {arm.name for arm in harness.captured_inputs.arms} == {
        "baseline",
        "concise",
        "caveman",
        "if",
    }
    for record in index.files:
        captured = all_captured[record.capsule_path]
        on_disk = prepared.path.joinpath(record.capsule_path).read_bytes()
        assert on_disk == captured.data
        assert record.byte_length == len(on_disk)
        assert record.sha256 == sha256_bytes(on_disk)
        assert creation_counts[record.capsule_path] == 1
        assert bytes(_generation(harness, record.capsule_path).bytes_written) == captured.data
    assert creation_counts["inputs/index.json"] == 1
    _assert_safety_barrier_untouched(harness)


def test_prepare_materializes_exact_case_plan_environment_and_event_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, harness, _manifest_path = _load_success(tmp_path, monkeypatch)
    assert harness.captured_inputs is not None
    assert harness.environment is not None
    captured = harness.captured_inputs
    expected_cases = materialize_case_index(captured, captured.resolved_manifest)
    expected_plan = materialize_plan(
        prepared.run_id,
        captured.resolved_manifest,
        expected_cases,
        captured.arms,
    )

    assert prepared.path.joinpath("manifest.json").read_bytes() == captured.resolved_manifest_bytes
    assert prepared.path.joinpath("case-index.jsonl").read_bytes() == canonical_jsonl(
        item.model_dump(mode="json") for item in expected_cases
    )
    assert prepared.path.joinpath("plan.jsonl").read_bytes() == canonical_jsonl(
        item.model_dump(mode="json") for item in expected_plan
    )
    assert prepared.path.joinpath("environment.json").read_bytes() == canonical_json(
        harness.environment.model_dump(mode="json")
    )
    event_bytes = prepared.path.joinpath("events.jsonl").read_bytes()
    event = PreparedEventV1.model_validate_json(event_bytes.removesuffix(b"\n"))
    assert event_bytes == event_jsonl(event)
    assert event.sequence == 0
    assert event.run_id == prepared.run_id
    assert event.operation_id == prepared.operation_id
    assert event.execution_session_id is None
    assert event.occurred_at == prepared.capsule.created_at
    assert event.payload.manifest_sha256 == prepared.capsule.manifest_sha256
    assert event.payload.input_index_sha256 == prepared.capsule.input_index_sha256
    assert event.payload.case_index_sha256 == prepared.capsule.case_index_sha256
    assert event.payload.plan_sha256 == prepared.capsule.plan_sha256
    assert event.payload.environment_sha256 == prepared.capsule.environment_sha256
    assert event.payload.runner_source_sha256 == prepared.capsule.runner_source_sha256


def test_prepare_wires_every_optional_request_and_opened_filesystem_fact_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_root = tmp_path / "manifests"
    manifest_root.mkdir()
    manifest = manifest_root / "prepare.yaml"
    manifest.write_bytes(
        yaml.safe_dump(
            _manifest_payload(),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
    )
    input_root = tmp_path / "authored-inputs"
    _write_case_file(input_root / "cases/response.yaml")
    invocation_cwd = tmp_path / "invocation-cwd"
    invocation_cwd.mkdir()
    source_root = ROOT
    container_digest = f"sha256:{'9' * 64}"
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(monkeypatch, results_root)
    request = _request(
        manifest,
        results_root,
        invocation_cwd=invocation_cwd,
        input_root=input_root,
        source_root=source_root,
        container_image_digest=container_digest,
    )

    prepared = prepare_capsule(request)

    assert harness.source_manifest_calls == [(manifest, input_root, invocation_cwd)]
    assert harness.authored_input_source_roots == [source_root]
    assert harness.provenance_arguments == [(source_root, container_digest)]
    assert harness.runtime_state_calls == 1
    assert harness.import_policy_calls == 1
    assert harness.project_filesystem_classes == ["apfs"]
    assert harness.environment is not None
    assert harness.environment.container_image_digest == "9" * 64
    assert prepared.path.joinpath("environment.json").read_bytes() == canonical_json(
        harness.environment.model_dump(mode="json")
    )
    assert harness.results_root_open_paths == [results_root]
    assert harness.results_root_fd is not None
    assert harness.results_root_identity is not None
    assert [
        (device, inode)
        for device, inode, _descriptor, _path, _directory_fd in harness.directory_opens
        if (device, inode) == harness.results_root_identity
    ] == [harness.results_root_identity]
    assert harness.posix is not None
    assert harness.posix.rename_directory_fds == [
        (harness.results_root_fd, harness.results_root_fd)
    ]
    assert {
        descriptor
        for label, descriptor in harness.posix.fsync_descriptors
        if label == "<results-root>"
    } == {harness.results_root_fd}
    assert harness.results_root_fd_closed is True
    with pytest.raises(OSError) as caught:
        os.fstat(harness.results_root_fd)
    assert caught.value.errno == errno.EBADF
    _assert_safety_barrier_untouched(harness)


def test_prepare_creates_and_fsyncs_in_the_normative_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, harness, _manifest_path = _load_success(tmp_path, monkeypatch)
    expected_non_capsule_files = sorted(
        (
            ".laconian.lock",
            "case-index.jsonl",
            "environment.json",
            "events.jsonl",
            "inputs/arms/baseline.txt",
            "inputs/arms/concise.txt",
            "inputs/cases/000.yaml",
            "inputs/index.json",
            "inputs/software/runner-source.json",
            "inputs/software/runner/laconian_eval/__init__.py",
            "manifest.json",
            "plan.jsonl",
            "raw.jsonl",
        ),
        key=lambda value: value.encode("utf-8"),
    )
    created_owned = [
        name
        for name in harness.created_files
        if name not in {".laconian-create.lock"} and not name.startswith(".probe")
    ]

    assert created_owned == [*expected_non_capsule_files, "capsule.json"]
    fsync_labels = [label for operation, label in harness.trace if operation == "fsync"]
    first_stage_sync = fsync_labels.index(".")
    first_file_syncs = [fsync_labels.index(label) for label in expected_non_capsule_files]
    assert first_file_syncs == sorted(first_file_syncs)
    assert max(first_file_syncs) < first_stage_sync
    child_directories = {
        "inputs/arms",
        "inputs/cases",
        "inputs/software/runner/laconian_eval",
        "inputs/software/runner",
        "inputs/software",
        "inputs",
    }
    for child_directory in child_directories:
        child_syncs = [
            index for index, label in enumerate(fsync_labels) if label == child_directory
        ]
        assert child_syncs
        assert max(child_syncs) < first_stage_sync
    for child, parent in (
        ("inputs/arms", "inputs"),
        ("inputs/cases", "inputs"),
        ("inputs/software/runner/laconian_eval", "inputs/software/runner"),
        ("inputs/software/runner", "inputs/software"),
        ("inputs/software", "inputs"),
    ):
        child_syncs = [index for index, label in enumerate(fsync_labels) if label == child]
        parent_syncs = [index for index, label in enumerate(fsync_labels) if label == parent]
        assert child_syncs and parent_syncs
        assert max(child_syncs) < max(parent_syncs)
    capsule_syncs = [index for index, label in enumerate(fsync_labels) if label == "capsule.json"]
    stage_syncs = [index for index, label in enumerate(fsync_labels) if label == "."]
    assert capsule_syncs
    assert len(stage_syncs) >= 2
    assert first_stage_sync < min(capsule_syncs)
    assert max(capsule_syncs) < max(stage_syncs)
    rename_index = harness.trace.index(("rename", str(prepared.run_id)))
    second_stage_sync_index = max(
        index for index, item in enumerate(harness.trace[:rename_index]) if item == ("fsync", ".")
    )
    assert second_stage_sync_index < rename_index
    assert harness.trace[rename_index + 1] == ("fsync", "<results-root>")

    artifact_labels = set(expected_non_capsule_files) | {"capsule.json"}
    live_files: set[str] = set()
    maximum_live_files = 0
    for operation, label in harness.trace:
        if label not in artifact_labels:
            continue
        if operation == "open":
            assert label not in live_files
            live_files.add(label)
            maximum_live_files = max(maximum_live_files, len(live_files))
        elif operation == "close":
            assert label in live_files
            live_files.remove(label)
    assert live_files == set()
    assert maximum_live_files == 2

    sequential_files = [
        label for label in expected_non_capsule_files if label != ".laconian.lock"
    ] + ["capsule.json"]
    for current, following in pairwise(sequential_files):
        current_generation = _generation(harness, current)
        following_generation = _generation(harness, following)
        current_close = harness.trace.index(("close", current))
        following_open = harness.trace.index(("open", following))
        assert current_generation.events.index("fsync") < current_generation.events.index("close")
        assert current_close < following_open
        assert current_generation.token < following_generation.token

    def trace_positions(operation: str, label: str) -> list[int]:
        return [index for index, item in enumerate(harness.trace) if item == (operation, label)]

    for relative in sequential_files[:-1]:
        parent = relative.rsplit("/", 1)[0] if "/" in relative else "."
        write_positions = trace_positions("write", relative)
        file_sync_positions = trace_positions("fsync", relative)
        close_positions = trace_positions("close", relative)
        parent_sync_positions = trace_positions("fsync", parent)
        assert file_sync_positions and len(close_positions) == 1 and parent_sync_positions
        if write_positions:
            assert max(write_positions) < max(file_sync_positions)
        assert max(file_sync_positions) < close_positions[0] < max(parent_sync_positions)

    capsule_writes = trace_positions("write", "capsule.json")
    capsule_syncs = trace_positions("fsync", "capsule.json")
    capsule_closes = trace_positions("close", "capsule.json")
    stage_sync_positions = trace_positions("fsync", ".")
    assert capsule_syncs and len(capsule_closes) == 1 and len(stage_sync_positions) >= 2
    if capsule_writes:
        assert max(capsule_writes) < max(capsule_syncs)
    assert max(capsule_syncs) < capsule_closes[0] < max(stage_sync_positions)

    lock_syncs = trace_positions("fsync", ".laconian.lock")
    lock_close = trace_positions("close", ".laconian.lock")
    assert lock_syncs and len(lock_close) == 1
    assert max(lock_syncs) < min(stage_sync_positions) < lock_close[0]


def test_prepare_uses_one_exclusive_nofollow_generation_per_owned_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, harness, _manifest = _load_success(
        tmp_path,
        monkeypatch,
        harness_options={"exercise_short_writes": True},
    )
    required_flags = os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    artifact_files = sorted(
        path.relative_to(prepared.path).as_posix()
        for path in prepared.path.rglob("*")
        if path.is_file()
    )

    assert sorted(harness.created_files, key=lambda value: value.encode("utf-8")) == artifact_files
    for relative in artifact_files:
        generation = _generation(harness, relative)
        assert generation.flags & required_flags == required_flags
        assert generation.flags & os.O_ACCMODE in {os.O_WRONLY, os.O_RDWR}
        assert generation.mode == 0o600
        assert generation.directory_fd is not None
        assert generation.regular_fstat_seen is True
        assert generation.events[0] == "open"
        assert generation.events.count("fstat") >= 1
        assert generation.events.count("fsync") >= 1
        assert generation.events.count("close") == 1
        fsync_indices = [index for index, event in enumerate(generation.events) if event == "fsync"]
        write_indices = [index for index, event in enumerate(generation.events) if event == "write"]
        assert fsync_indices[-1] < generation.events.index("close")
        if write_indices:
            assert max(write_indices) < fsync_indices[-1]
        assert bytes(generation.bytes_written) == prepared.path.joinpath(relative).read_bytes()
        if generation.bytes_written:
            assert generation.write_attempts >= (3 if len(generation.bytes_written) > 1 else 2)

    owned_directories = {
        label
        for label, raw_name, mode, directory_fd in harness.mkdir_calls
        if not label.startswith(".laconian-stage.")
        and not label.startswith(".laconian-probe")
        and all(part not in {".", ".."} for part in Path(label).parts)
        and not raw_name.startswith(".laconian-")
        and mode == 0o700
        and directory_fd is not None
        and "/" not in raw_name
    }
    assert owned_directories == {
        "inputs",
        "inputs/arms",
        "inputs/cases",
        "inputs/software",
        "inputs/software/runner",
        "inputs/software/runner/laconian_eval",
    }


def test_capsule_marker_is_the_last_owned_file_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, harness, _manifest = _load_success(tmp_path, monkeypatch)
    marker_open = harness.trace.index(("open", "capsule.json"))
    publish = harness.trace.index(("rename", str(prepared.run_id)))
    first_stage_sync = harness.trace.index(("fsync", "."))

    assert first_stage_sync < marker_open < publish
    for operation, label in harness.trace[marker_open:publish]:
        if operation in {"open", "write-attempt", "write", "mkdir"}:
            assert label == "capsule.json"


def test_persistent_lock_is_exclusive_through_durable_publish_and_verification_seam(
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
    fork_context = multiprocessing.get_context("fork")
    harness = _install_harness(monkeypatch, results_root)
    contention_evidence: list[tuple[int, int, str]] = []

    def wait_for_child(child_pid: int, receiver: Any, timeout: float = 5.0) -> int | None:
        deadline = monotonic() + timeout
        while True:
            try:
                waited_pid, wait_status = os.waitpid(child_pid, os.WNOHANG)
            except InterruptedError:
                continue
            if waited_pid == child_pid:
                return wait_status
            remaining = deadline - monotonic()
            if remaining <= 0:
                return None
            try:
                if receiver.poll(min(remaining, 0.05)):
                    with suppress(EOFError, OSError):
                        receiver.recv()
            except InterruptedError:
                continue
            except (EOFError, OSError):
                pass

    def second_process_shared_lock_probe(
        capsule_directory_fd: int,
        persistent_lock_descriptor: int,
    ) -> tuple[int, int, str]:
        parent_pid = os.getpid()
        receiver, sender = fork_context.Pipe(duplex=False)
        opened = fork_context.Event()
        attempt = fork_context.Event()
        child_pid = os.fork()
        if child_pid == 0:
            child_descriptor: int | None = None
            exit_code = 1
            with suppress(BaseException):
                receiver.close()
            try:
                harness.real_close(persistent_lock_descriptor)
                child_descriptor = harness.real_open(
                    ".laconian.lock",
                    os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=capsule_directory_fd,
                )
                if not stat.S_ISREG(os.fstat(child_descriptor).st_mode):
                    sender.send((os.getpid(), "unsafe"))
                else:
                    opened.set()
                    if not attempt.wait(5.0):
                        sender.send((os.getpid(), "timeout"))
                    else:
                        try:
                            harness.posix.real_flock(
                                child_descriptor,
                                fcntl.LOCK_SH | fcntl.LOCK_NB,
                            )
                        except OSError as error:
                            outcome = (
                                "blocked"
                                if error.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}
                                else "error"
                            )
                            sender.send((os.getpid(), outcome))
                        else:
                            harness.posix.real_flock(child_descriptor, fcntl.LOCK_UN)
                            sender.send((os.getpid(), "acquired"))
                    exit_code = 0
            except BaseException:
                with suppress(BaseException):
                    sender.send((os.getpid(), "error"))
            finally:
                if child_descriptor is not None:
                    with suppress(OSError):
                        harness.real_close(child_descriptor)
                with suppress(BaseException):
                    sender.close()
                os._exit(exit_code)

        sender.close()
        wait_status: int | None = None
        message: tuple[int, str] | None = None
        try:
            opened_ready = opened.wait(5.0)
            attempt.set()
            if receiver.poll(5.0):
                received = receiver.recv()
                if (
                    type(received) is tuple
                    and len(received) == 2
                    and type(received[0]) is int
                    and type(received[1]) is str
                ):
                    message = received
            wait_status = wait_for_child(child_pid, receiver)
        finally:
            attempt.set()
            if wait_status is None:
                with suppress(ProcessLookupError):
                    os.kill(child_pid, signal.SIGKILL)
                wait_status = wait_for_child(child_pid, receiver)
            receiver.close()

        assert opened_ready is True
        assert message is not None
        assert wait_status is not None
        assert os.waitstatus_to_exitcode(wait_status) == 0
        reported_pid, outcome = message
        return parent_pid, reported_pid, outcome

    def observe_visible_capsule(
        capsule_directory_fd: int,
        *,
        results_root_fd: int,
        destination_name: str,
        persistent_lock_descriptor: int,
    ) -> None:
        harness.trace.append(("verify", destination_name))
        assert harness.results_root_fd == results_root_fd
        assert harness.results_root_identity is not None
        root_metadata = os.fstat(results_root_fd)
        assert (root_metadata.st_dev, root_metadata.st_ino) == harness.results_root_identity
        visible_path = results_root / destination_name
        assert capsule_directory_fd == harness.staging_directory_fd
        assert capsule_directory_fd != results_root_fd
        capsule_metadata = os.fstat(capsule_directory_fd)
        visible_metadata = visible_path.stat(follow_symlinks=False)
        assert stat.S_ISDIR(capsule_metadata.st_mode)
        assert (capsule_metadata.st_dev, capsule_metadata.st_ino) == (
            visible_metadata.st_dev,
            visible_metadata.st_ino,
        )
        assert harness.posix is not None
        assert harness.posix.rename_directory_fds == [(results_root_fd, results_root_fd)]
        lock = _generation(harness, ".laconian.lock")
        assert persistent_lock_descriptor == lock.descriptor
        assert persistent_lock_descriptor in harness.active_files
        lock_metadata = os.fstat(persistent_lock_descriptor)
        assert stat.S_ISREG(lock_metadata.st_mode)
        parent_lock_events = tuple(lock.events)
        evidence = second_process_shared_lock_probe(
            capsule_directory_fd,
            persistent_lock_descriptor,
        )
        contention_evidence.append(evidence)
        parent_pid, child_pid, outcome = evidence
        assert parent_pid == os.getpid()
        assert child_pid > 0
        assert child_pid != parent_pid
        assert outcome == "blocked"
        assert persistent_lock_descriptor in harness.active_files
        assert stat.S_ISREG(os.fstat(persistent_lock_descriptor).st_mode)
        assert tuple(lock.events) == parent_lock_events

    monkeypatch.setattr(prepare_module, "_post_publish_verify", observe_visible_capsule)
    prepared = prepare_capsule(_request(manifest, results_root))

    lock = _generation(harness, ".laconian.lock")
    first_other_open = next(
        index
        for index, item in enumerate(harness.trace)
        if item[0] == "open" and item[1] != ".laconian.lock"
    )
    lock_index = harness.trace.index(("lock-ex", ".laconian.lock"))
    rename_index = harness.trace.index(("rename", str(prepared.run_id)))
    root_sync_index = harness.trace.index(("fsync", "<results-root>"), rename_index)
    verify_index = harness.trace.index(("verify", str(prepared.run_id)))
    unlock_index = harness.trace.index(("unlock", ".laconian.lock"))
    close_index = harness.trace.index(("close", ".laconian.lock"))

    assert lock.events.count("lock-ex") == 1
    assert lock.events.index("fstat") < lock.events.index("lock-ex")
    assert "lock-sh" not in lock.events
    assert not any(operation == "lock-sh" for operation, _label in harness.trace)
    assert lock_index < first_other_open < rename_index < root_sync_index < verify_index
    assert verify_index < unlock_index < close_index
    assert len(contention_evidence) == 1
    assert contention_evidence[0][1] != contention_evidence[0][0]
    descriptor = harness.real_open(
        prepared.path / ".laconian.lock",
        os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        harness.real_close(descriptor)
    _assert_safety_barrier_untouched(harness)


def test_ordinary_verifier_failure_is_content_free_and_reports_published_capsule(
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
    harness = _install_harness(monkeypatch, results_root)
    observed_destination: str | None = None

    def failed_verifier(
        _capsule_directory_fd: int,
        *,
        results_root_fd: int,
        destination_name: str,
        persistent_lock_descriptor: int,
    ) -> None:
        nonlocal observed_destination
        del results_root_fd, persistent_lock_descriptor
        observed_destination = destination_name
        raise AssertionError("credential=TOP-SECRET host=/private/verifier")

    monkeypatch.setattr(prepare_module, "_post_publish_verify", failed_verifier)

    with pytest.raises(PostPublishVerificationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert observed_destination is not None
    assert caught.value.published is True
    assert caught.value.destination_name == observed_destination
    assert caught.value.code == "post_publish_verification_failed"
    assert str(caught.value) == "capsule publication failed"
    assert "TOP-SECRET" not in str(caught.value)
    assert "TOP-SECRET" not in " ".join(getattr(caught.value, "__notes__", ()))
    visible = results_root / observed_destination
    assert CapsuleV1.model_validate_json(visible.joinpath("capsule.json").read_bytes())
    assert _generation(harness, ".laconian.lock").events[-2:] == ["unlock", "close"]
    _assert_safety_barrier_untouched(harness)


def test_persistent_lock_path_replacement_at_verifier_is_reported_as_published_failure(
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
    harness = _install_harness(monkeypatch, results_root)
    replacement = b"replacement-lock-inode"
    observed_destination: str | None = None

    def replace_visible_lock(
        capsule_directory_fd: int,
        *,
        results_root_fd: int,
        destination_name: str,
        persistent_lock_descriptor: int,
    ) -> None:
        nonlocal observed_destination
        del results_root_fd
        assert persistent_lock_descriptor in harness.active_files
        os.unlink(".laconian.lock", dir_fd=capsule_directory_fd)
        descriptor = harness.real_open(
            ".laconian.lock",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=capsule_directory_fd,
        )
        try:
            assert os.write(descriptor, replacement) == len(replacement)
            os.fsync(descriptor)
        finally:
            harness.real_close(descriptor)
        observed_destination = destination_name

    monkeypatch.setattr(prepare_module, "_post_publish_verify", replace_visible_lock)

    with pytest.raises(PostPublishVerificationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert observed_destination is not None
    assert caught.value.published is True
    assert caught.value.destination_name == observed_destination
    visible = results_root / observed_destination
    assert CapsuleV1.model_validate_json(visible.joinpath("capsule.json").read_bytes())
    assert visible.joinpath(".laconian.lock").read_bytes() == replacement
    assert _generation(harness, ".laconian.lock").events[-2:] == ["unlock", "close"]
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize("failure_operation", ["fstat", "stat"])
def test_directory_candidate_validation_failure_consumes_descriptor_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_operation: str,
) -> None:
    staging = tmp_path / "stage"
    staging.mkdir()
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"sentinel-owned-by-test")
    staging_fd = os.open(
        staging,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    real_open = os.open
    real_close = os.close
    real_fstat = os.fstat
    real_stat = os.stat
    candidate_fd: int | None = None
    sentinel_fd: int | None = None
    close_attempts = 0

    class FaultOsProxy:
        def __getattr__(self, name: str) -> object:
            return getattr(os, name)

        def open(
            self,
            path: os.PathLike[str] | str,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal candidate_fd
            descriptor = (
                real_open(path, flags, mode)
                if dir_fd is None
                else real_open(path, flags, mode, dir_fd=dir_fd)
            )
            if os.fspath(path) == "broken":
                candidate_fd = descriptor
            return descriptor

        def fstat(self, descriptor: int) -> os.stat_result:
            if failure_operation == "fstat" and descriptor == candidate_fd:
                raise OSError(errno.EIO, "credential=TOP-SECRET host=/private/fstat")
            return real_fstat(descriptor)

        def stat(
            self,
            path: os.PathLike[str] | str,
            *,
            dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> os.stat_result:
            if failure_operation == "stat" and os.fspath(path) == "broken":
                raise OSError(errno.EIO, "credential=TOP-SECRET host=/private/stat")
            return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

        def close(self, descriptor: int) -> None:
            nonlocal close_attempts, sentinel_fd
            if descriptor != candidate_fd:
                real_close(descriptor)
                return
            close_attempts += 1
            if close_attempts > 1:
                real_close(descriptor)
                return
            real_close(descriptor)
            replacement_fd = real_open(
                sentinel,
                os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            )
            if replacement_fd != descriptor:
                os.dup2(replacement_fd, descriptor, inheritable=False)
                real_close(replacement_fd)
                replacement_fd = descriptor
            sentinel_fd = replacement_fd
            raise OSError(errno.EIO, "ambiguous descriptor close")

    monkeypatch.setattr(prepare_module, "os", FaultOsProxy())
    try:
        with pytest.raises(PreparationError) as caught:
            prepare_module._create_directories(staging_fd, ("broken/member.py",))

        assert caught.value.code == "artifact_io_failed"
        assert str(caught.value) == "capsule preparation failed"
        assert close_attempts == 1
        assert sentinel_fd == candidate_fd
        assert sentinel_fd is not None
        os.lseek(sentinel_fd, 0, os.SEEK_SET)
        assert os.read(sentinel_fd, 1024) == b"sentinel-owned-by-test"
    finally:
        if sentinel_fd is not None:
            real_close(sentinel_fd)
        real_close(staging_fd)


def test_directory_generation_remains_bounded_under_low_nofile_limit(tmp_path: Path) -> None:
    staging = tmp_path / "stage"
    staging.mkdir()
    paths = tuple(f"d{ordinal:03d}/member.py" for ordinal in range(40))
    fork_context = multiprocessing.get_context("fork")
    receiver, sender = fork_context.Pipe(duplex=False)

    def create_many_directories() -> None:
        descriptor: int | None = None
        try:
            _soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
            bounded_limit = 32 if hard_limit == resource.RLIM_INFINITY else min(32, hard_limit)
            resource.setrlimit(resource.RLIMIT_NOFILE, (bounded_limit, hard_limit))
            descriptor = os.open(
                staging,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            )
            identities = prepare_module._create_directories(descriptor, paths)
            sender.send(("ok", len(identities)))
        except BaseException as error:
            sender.send((type(error).__name__, getattr(error, "code", None)))
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)
            sender.close()

    process = fork_context.Process(target=create_many_directories)
    process.start()
    sender.close()
    try:
        assert receiver.poll(5.0)
        assert receiver.recv() == ("ok", 40)
        process.join(5.0)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join(5.0)
        receiver.close()
    assert sorted(path.name for path in staging.iterdir()) == [
        f"d{ordinal:03d}" for ordinal in range(40)
    ]


class _InjectedCancellation(BaseException):
    pass


@pytest.mark.parametrize("active_primary", [False, True])
def test_persistent_lock_teardown_consumes_descriptor_and_preserves_primary_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    active_primary: bool,
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
    harness = _install_harness(monkeypatch, results_root)
    assert harness.posix is not None

    def cancellation_during_release(self: _HarnessPosix, descriptor: int) -> None:
        self.real_flock(descriptor, fcntl.LOCK_UN)
        raise _InjectedCancellation

    monkeypatch.setattr(_HarnessPosix, "release_lock", cancellation_during_release)
    if active_primary:

        def failed_verifier(
            _capsule_directory_fd: int,
            *,
            results_root_fd: int,
            destination_name: str,
            persistent_lock_descriptor: int,
        ) -> None:
            del results_root_fd, destination_name, persistent_lock_descriptor
            raise RuntimeError("credential=TOP-SECRET host=/private/verifier")

        monkeypatch.setattr(prepare_module, "_post_publish_verify", failed_verifier)
        expected_error: type[BaseException] = PostPublishVerificationError
    else:
        expected_error = _InjectedCancellation

    with pytest.raises(expected_error) as caught:
        prepare_capsule(_request(manifest, results_root))

    if active_primary:
        assert isinstance(caught.value, PostPublishVerificationError)
        assert caught.value.published is True
        assert "TOP-SECRET" not in str(caught.value)
    lock = _generation(harness, ".laconian.lock")
    assert lock.events.count("close") == 1
    assert lock.descriptor not in harness.active_files
    assert harness.results_root_fd_closed is True
    _assert_safety_barrier_untouched(harness)


def test_ambiguous_results_root_close_after_durable_success_is_not_retried(
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
        inject_ambiguous_results_root_close=True,
    )

    prepared = prepare_capsule(_request(manifest, results_root))

    assert prepared.path == results_root / str(prepared.run_id)
    assert CapsuleV1.model_validate_json(prepared.path.joinpath("capsule.json").read_bytes())
    assert harness.results_root_fd_closed is True
    _assert_ambiguous_root_close_was_not_retried(harness)
    _assert_safety_barrier_untouched(harness)


def test_prepare_reads_no_credential_and_constructs_no_provider(
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
    harness = _install_harness(monkeypatch, results_root)

    prepared = prepare_capsule(_request(manifest, results_root))

    _assert_safety_barrier_untouched(harness)
    assert harness.provenance_calls == 1
    assert harness.runtime_state_calls == 1
    assert harness.import_policy_calls == 1
    assert harness.environment_calls == 1
    for relative in (
        "capsule.json",
        "environment.json",
        "inputs/index.json",
        "case-index.jsonl",
        "plan.jsonl",
        "events.jsonl",
    ):
        assert (
            b"credential-value-that-must-not-be-read"
            not in prepared.path.joinpath(relative).read_bytes()
        )


@pytest.mark.parametrize("reserved_name", ["PYTHONPATH", "PYTHONHOME"])
def test_reserved_api_key_environment_is_rejected_before_import_state_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reserved_name: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _write_manifest(
        source,
        provider_kind="openai",
        api_key_env=reserved_name,
    )
    results_root = tmp_path / "results"
    results_root.mkdir()
    harness = _install_harness(monkeypatch, results_root)

    def forbidden_runtime_capture() -> object:
        raise AssertionError("import state was captured before reserved-name rejection")

    monkeypatch.setattr(prepare_module, "capture_runtime_import_state", forbidden_runtime_capture)

    with pytest.raises(PreparationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert caught.value.code == "reserved_api_key_environment"
    assert str(caught.value) == "capsule preparation failed"
    assert harness.runtime_state_calls == 0
    assert harness.import_policy_calls == 0
    assert harness.credentials is not None
    assert harness.credentials.lookups == []
    assert harness.provider_constructions == 0
    assert not any(path.name.startswith(".laconian-stage.") for path in results_root.iterdir())


def test_collision_publishes_nothing_and_claims_no_existing_destination(
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
    generated_ids = (
        UUID("323e4567-e89b-42d3-a456-426614174002"),
        UUID("423e4567-e89b-42d3-a456-426614174003"),
    )
    markers: dict[str, Path] = {}
    for generated_id in generated_ids:
        target = results_root / str(generated_id)
        target.mkdir()
        marker = target / "owner.txt"
        marker.write_bytes(f"owner:{generated_id}".encode())
        markers[str(generated_id)] = marker
    generated = iter(generated_ids)

    def deterministic_uuid4() -> UUID:
        try:
            return next(generated)
        except StopIteration:
            raise AssertionError("preparation retried UUID generation after collision") from None

    monkeypatch.setattr(prepare_module, "uuid4", deterministic_uuid4)
    harness = _install_harness(monkeypatch, results_root)

    with pytest.raises(DestinationCollisionError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert caught.value.published is False
    assert not hasattr(caught.value, "destination_name")
    rename_targets = [label for operation, label in harness.trace if operation == "rename"]
    assert len(rename_targets) == 1
    assert rename_targets[0] in markers
    for target_name, marker in markers.items():
        assert marker.read_bytes() == f"owner:{target_name}".encode()
    assert {path.name for path in results_root.iterdir()} == set(markers)
    assert not any(path.name.startswith(".laconian-stage.") for path in results_root.iterdir())
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize("ambiguous_root_close", [False, True])
def test_post_rename_results_root_fsync_failure_preserves_and_reports_visible_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ambiguous_root_close: bool,
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
        fail_root_fsync_after_publish=True,
        inject_ambiguous_results_root_close=ambiguous_root_close,
    )

    with pytest.raises(PostPublishSyncError) as caught:
        prepare_capsule(_request(manifest, results_root))

    visible = results_root / caught.value.destination_name
    assert caught.value.published is True
    assert str(caught.value) == "capsule publication failed"
    assert "TOP-SECRET" not in str(caught.value)
    assert "TOP-SECRET" not in " ".join(getattr(caught.value, "__notes__", ()))
    assert visible.is_dir()
    assert CapsuleV1.model_validate_json(visible.joinpath("capsule.json").read_bytes())
    assert not any(path.name.startswith(".laconian-stage.") for path in results_root.iterdir())
    lock = _generation(harness, ".laconian.lock")
    assert lock.events[-2:] == ["unlock", "close"]
    assert harness.results_root_fd_closed is True
    if ambiguous_root_close:
        _assert_ambiguous_root_close_was_not_retried(harness)
    else:
        assert harness.results_root_close_attempts == 1
    _assert_safety_barrier_untouched(harness)


def test_capability_failure_creates_no_staging_or_visible_capsule(
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
    harness = _install_harness(monkeypatch, results_root, filesystem_error=True)

    with pytest.raises(UnsupportedFilesystemError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert str(caught.value) == "filesystem contract is unsupported"
    assert list(results_root.iterdir()) == []
    assert harness.results_root_fd_closed is True
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize("root_kind", ["intermediate_symlink", "regular_file"])
def test_results_root_is_opened_as_a_nofollow_regular_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_kind: str,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _write_manifest(
        source,
        provider_kind="openai",
        api_key_env="LIVE_TEST_API_KEY",
    )
    if root_kind == "intermediate_symlink":
        real_parent = tmp_path / "real-parent"
        real_parent.mkdir()
        real_results = real_parent / "results"
        real_results.mkdir()
        alias = tmp_path / "alias"
        alias.symlink_to(real_parent, target_is_directory=True)
        results_root = alias / "results"
    else:
        results_root = tmp_path / "results"
        results_root.write_bytes(b"not a directory")
        real_results = results_root
    harness = _install_harness(monkeypatch, results_root)

    with pytest.raises(PreparationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert caught.value.code == "invalid_results_root"
    assert str(caught.value) == "capsule preparation failed"
    if root_kind == "intermediate_symlink":
        assert list(real_results.iterdir()) == []
    else:
        assert real_results.read_bytes() == b"not a directory"
    _assert_safety_barrier_untouched(harness)


def test_results_root_identity_swap_after_open_fails_before_owned_mutation(
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
        swap_results_root_after_open=True,
        forbid_preparation_filesystem=True,
    )

    with pytest.raises(PreparationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert caught.value.code == "results_root_identity_changed"
    assert str(caught.value) == "capsule preparation failed"
    assert list(results_root.iterdir()) == []
    assert harness.swapped_results_root is not None
    assert list(harness.swapped_results_root.iterdir()) == []
    assert harness.preparation_filesystem_calls == 0
    assert harness.results_root_fd_closed is True
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize("ambiguous_root_close", [False, True])
def test_results_root_path_swap_at_verification_seam_cannot_return_wrong_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ambiguous_root_close: bool,
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
        inject_ambiguous_results_root_close=ambiguous_root_close,
    )
    displaced = tmp_path / "results-published"
    published_name: str | None = None
    published_capsule_bytes: bytes | None = None

    def swap_visible_root(
        capsule_directory_fd: int,
        *,
        results_root_fd: int,
        destination_name: str,
        persistent_lock_descriptor: int,
    ) -> None:
        nonlocal published_capsule_bytes, published_name
        published_name = destination_name
        harness.trace.append(("verify", destination_name))
        assert results_root_fd == harness.results_root_fd
        assert capsule_directory_fd == harness.staging_directory_fd
        assert stat.S_ISDIR(os.fstat(capsule_directory_fd).st_mode)
        assert (
            persistent_lock_descriptor
            == _generation(
                harness,
                ".laconian.lock",
            ).descriptor
        )
        snapshot_descriptor = harness.real_open(
            "capsule.json",
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=capsule_directory_fd,
        )
        try:
            published_capsule_bytes = os.read(snapshot_descriptor, 1024 * 1024)
        finally:
            harness.real_close(snapshot_descriptor)
        os.rename(results_root, displaced)
        results_root.mkdir(mode=0o700)

    monkeypatch.setattr(prepare_module, "_post_publish_verify", swap_visible_root)

    with pytest.raises(PostPublishVerificationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert caught.value.code == "post_publish_verification_failed"
    assert caught.value.published is True
    assert published_name is not None
    assert caught.value.destination_name == published_name
    assert str(caught.value) == "capsule publication failed"
    assert "TOP-SECRET" not in " ".join(getattr(caught.value, "__notes__", ()))
    assert list(results_root.iterdir()) == []
    visible = displaced / published_name
    assert visible.is_dir()
    visible_capsule_bytes = visible.joinpath("capsule.json").read_bytes()
    assert visible_capsule_bytes == published_capsule_bytes
    assert CapsuleV1.model_validate_json(visible_capsule_bytes)
    lock = _generation(harness, ".laconian.lock")
    assert lock.events[-2:] == ["unlock", "close"]
    assert harness.results_root_fd_closed is True
    if ambiguous_root_close:
        _assert_ambiguous_root_close_was_not_retried(harness)
    else:
        assert harness.results_root_close_attempts == 1
    _assert_safety_barrier_untouched(harness)


def test_owned_staging_is_cleaned_when_a_write_fails(
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
    orphan = results_root / ".laconian-stage.523e4567-e89b-42d3-a456-426614174004"
    orphan.mkdir()
    orphan_marker = orphan / "owner.txt"
    orphan_marker.write_bytes(b"different operation")
    harness = _install_harness(
        monkeypatch,
        results_root,
        fail_write_path="case-index.jsonl",
    )

    with pytest.raises(PreparationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert caught.value.code == "artifact_io_failed"
    assert str(caught.value) == "capsule preparation failed"
    assert "TOP-SECRET" not in str(caught.value)
    assert {path.name for path in results_root.iterdir()} == {orphan.name}
    assert orphan_marker.read_bytes() == b"different operation"
    assert not any(len(path.name) == 36 for path in results_root.iterdir())
    assert harness.results_root_fd_closed is True
    _assert_safety_barrier_untouched(harness)


@pytest.mark.parametrize(
    "failure_point",
    [
        ("plan.jsonl", 1),
        ("inputs/arms", 1),
        (".", 1),
        ("capsule.json", 1),
        (".", 2),
    ],
)
def test_every_prepublish_durability_failure_cleans_owned_stage_without_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: tuple[str, int],
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
        fail_fsync_at=failure_point,
    )

    with pytest.raises(PreparationError) as caught:
        prepare_capsule(_request(manifest, results_root))

    assert caught.value.code == "artifact_io_failed"
    assert str(caught.value) == "capsule preparation failed"
    assert "TOP-SECRET" not in str(caught.value)
    assert not any(operation == "rename" for operation, _label in harness.trace)
    assert list(results_root.iterdir()) == []
    assert harness.results_root_fd_closed is True
    _assert_safety_barrier_untouched(harness)


def test_generated_metadata_contains_no_host_source_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _harness, _manifest_path = _load_success(tmp_path, monkeypatch)
    forbidden = os.fspath(tmp_path).encode("utf-8")

    for relative in (
        "capsule.json",
        "manifest.json",
        "environment.json",
        "inputs/index.json",
        "inputs/software/runner-source.json",
        "case-index.jsonl",
        "plan.jsonl",
        "events.jsonl",
        "raw.jsonl",
    ):
        assert forbidden not in prepared.path.joinpath(relative).read_bytes()
