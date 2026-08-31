from __future__ import annotations

import os
import shutil
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from laconian_eval import __version__
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes, stable_digest
from laconian_eval.capsule.capture import (
    CapturedInputs,
    CapturedSourceManifest,
    CaptureError,
    capture_authored_inputs,
    load_source_manifest_capture,
    upgrade_v1_manifest,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.manifest_models import V1UpgradeProjection, project_v1_manifest
from laconian_eval.models import RunManifest

ROOT = Path(__file__).parents[2]
_CAVEMAN_SKILL_SHA256 = "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"
_CAVEMAN_SOURCE_SHA256 = "8aa76311ea6273848242b1fcdd3542c47683fdeb7118395afb5aafb4709d081d"
_CAVEMAN_COMMIT = "781c384cafc28d7ca392014dbab569f985b5b2fd"


def _case(case_id: str, scenario_id: str, locale: str, *, prompt: str) -> dict[str, object]:
    return {
        "id": case_id,
        "scenario_id": scenario_id,
        "locale": locale,
        "category": "direct",
        "prompt": prompt,
    }


def _write_case(path: Path, *cases: dict[str, object]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_dump(
        {"schema_version": "1", "kind": "response", "cases": list(cases)},
        allow_unicode=True,
        sort_keys=False,
    ).encode("utf-8")
    path.write_bytes(data)
    return data


def _dataset(
    dataset_id: str,
    ordinals: list[int],
    *,
    dataset_version: str = "fixture-v1",
) -> dict[str, object]:
    return {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "role": "smoke",
        "case_schema_version": "1",
        "case_file_ordinals": ordinals,
    }


def _source_v2(
    *,
    case_files: list[str],
    datasets: list[dict[str, object]],
    arms: list[str] | None = None,
    provider: dict[str, object] | None = None,
    comparisons: list[dict[str, object]] | None = None,
    protocol_bindings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "2",
        "runner_version": __version__,
        "run_name": "capture-smoke",
        "provider": provider
        or {
            "kind": "fake",
            "model": "fixture-v1",
            "api_key_env": None,
            "replay_file": None,
        },
        "case_files": case_files,
        "arms": arms or ["baseline"],
        "repetitions": 1,
        "arm_order_seed": 17,
        "instruction_placement": "system_suffix",
        "generation": {
            "max_output_tokens": 1024,
            "temperature": None,
            "reasoning_effort": None,
            "text_verbosity": None,
            "reasoning_mode": "omitted",
            "prompt_cache_mode": "explicit",
            "prompt_cache_ttl": "30m",
            "service_tier": "default",
        },
        "retry": {"max_transient_retries": 0, "timeout_seconds": 5},
        "price_snapshot": None,
        "capsule": {
            "run_purpose": "integration_smoke",
            "claim_intent": "none",
            "datasets": datasets,
            "comparisons": comparisons or [],
            "protocol_bindings": protocol_bindings or [],
        },
    }


def _write_manifest(path: Path, payload: dict[str, object]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")
    path.write_bytes(data)
    return data


def _capture_v2(
    manifest_path: Path,
    *,
    invocation_cwd: Path,
    input_root: Path | None = None,
    source_root: Path = ROOT,
) -> tuple[CapturedSourceManifest, CapturedInputs]:
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=invocation_cwd,
    )
    return source, capture_authored_inputs(source, source_root=source_root)


def _record_payloads(captured: CapturedInputs) -> list[dict[str, object]]:
    return [record.model_dump(mode="json") for record in captured.records]


def _copy_arm_sources(destination: Path) -> None:
    members = {
        ROOT / "evals/baselines/caveman/SKILL.md": destination / "evals/baselines/caveman/SKILL.md",
        ROOT / "evals/baselines/caveman/SOURCE.md": destination
        / "evals/baselines/caveman/SOURCE.md",
        ROOT / "LICENSES/CAVEMAN-MIT.txt": destination / "LICENSES/CAVEMAN-MIT.txt",
    }
    for source, target in members.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_v1_capture_uses_invocation_cwd_and_explicit_absolute_paths(tmp_path: Path) -> None:
    invocation_cwd = tmp_path / "invocation"
    invocation_cwd.mkdir()
    relative_case = invocation_cwd / "cases/en.yaml"
    absolute_case = tmp_path / "absolute/ru.yaml"
    relative_bytes = _write_case(
        relative_case,
        _case("legacy-en", "legacy", "en", prompt="relative source"),
    )
    absolute_bytes = _write_case(
        absolute_case,
        _case("legacy-ru", "legacy", "ru", prompt="absolute source"),
    )
    ignored_replay = str(tmp_path / "must-not-be-read.yaml")
    payload: dict[str, object] = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-capture",
        "provider": {
            "kind": "fake",
            "model": "fixture-v1",
            "api_key_env": "IGNORED_API_KEY",
            "replay_file": ignored_replay,
        },
        "case_files": ["cases/en.yaml", str(absolute_case)],
        "arms": ["if", "concise"],
        "repetitions": 2,
        "arm_order_seed": -9,
        "instruction_placement": "system_suffix",
        "generation": {"max_output_tokens": 2048, "temperature": 0},
        "retry": {"max_transient_retries": 1, "timeout_seconds": 3},
        "price_snapshot": None,
    }
    source_bytes = _write_manifest(invocation_cwd / "manifest.yaml", payload)

    source = load_source_manifest_capture(
        "manifest.yaml",
        input_root=None,
        invocation_cwd=invocation_cwd,
    )
    captured = capture_authored_inputs(source, source_root=ROOT)

    assert isinstance(source.source_manifest, V1UpgradeProjection)
    assert source.source_manifest.price_snapshot is None
    assert source.source_bytes == source_bytes
    assert source.source_manifest_commitment_sha256 == sha256(source_bytes).hexdigest()
    assert captured.source_manifest_commitment_sha256 == sha256(source_bytes).hexdigest()
    assert captured.resolved_manifest.source_manifest_schema_version == "1"
    assert captured.resolved_manifest.price_snapshot is None
    assert captured.resolved_manifest.case_files == (
        "inputs/cases/000.yaml",
        "inputs/cases/001.yaml",
    )
    assert captured.resolved_manifest.provider.api_key_env is None
    assert captured.resolved_manifest.provider.replay_file is None
    assert captured.resolved_manifest.generation.model_dump(mode="json") == {
        "max_output_tokens": 2048,
        "temperature": 0.0,
        "reasoning_effort": None,
        "text_verbosity": None,
        "reasoning_mode": "omitted",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
        "service_tier": "default",
    }
    assert not any(record.role == "replay" for record in captured.records)
    assert captured.resolved_manifest.capsule.run_purpose == "integration_smoke"
    assert captured.resolved_manifest.capsule.claim_intent == "none"
    assert captured.resolved_manifest.capsule.comparisons[0].model_dump(mode="json") == {
        "comparison_id": "if-vs-concise",
        "left_arm": "if",
        "right_arm": "concise",
        "role": "contextual",
    }
    dataset = captured.resolved_manifest.capsule.datasets[0]
    assert dataset.model_dump(mode="json") | {"dataset_content_sha256": "ignored"} == {
        "dataset_id": "legacy-capture",
        "dataset_version": "unversioned",
        "role": "smoke",
        "case_schema_version": "1",
        "case_file_ordinals": [0, 1],
        "dataset_content_sha256": "ignored",
    }
    case_records = tuple(record for record in captured.records if record.role == "case")
    expected_dataset_digest = stable_digest(
        "laconian-dataset-content-v1",
        {
            "dataset_id": "legacy-capture",
            "dataset_version": "unversioned",
            "members": [
                {
                    "source_ordinal": 0,
                    "capsule_path": "inputs/cases/000.yaml",
                    "byte_length": len(relative_bytes),
                    "sha256": sha256_bytes(relative_bytes),
                },
                {
                    "source_ordinal": 1,
                    "capsule_path": "inputs/cases/001.yaml",
                    "byte_length": len(absolute_bytes),
                    "sha256": sha256_bytes(absolute_bytes),
                },
            ],
        },
    )
    assert dataset.dataset_content_sha256 == expected_dataset_digest
    assert all(record.dataset_id == "legacy-capture" for record in case_records)
    assert (
        upgrade_v1_manifest(
            source.source_manifest,
            dataset_content_sha256=expected_dataset_digest,
        )
        == captured.resolved_manifest
    )


def test_v1_rejects_input_root_as_a_usage_error(tmp_path: Path) -> None:
    invocation_cwd = tmp_path / "cwd"
    invocation_cwd.mkdir()
    _write_manifest(
        invocation_cwd / "manifest.yaml",
        {
            "schema_version": "1",
            "runner_version": __version__,
            "run_name": "legacy-capture",
            "provider": {"kind": "fake", "model": "fixture-v1"},
            "case_files": ["cases.yaml"],
            "arms": ["baseline"],
        },
    )

    with pytest.raises(CaptureError) as error:
        load_source_manifest_capture(
            "manifest.yaml",
            input_root=tmp_path,
            invocation_cwd=invocation_cwd,
        )

    assert error.value.code == "v1_input_root_forbidden"


def test_v1_capture_lexically_accepts_parent_locator_without_path_resolve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation_cwd = tmp_path / "workspace/invocation"
    invocation_cwd.mkdir(parents=True)
    parent_case = tmp_path / "workspace/cases/pair.yaml"
    case_bytes = _write_case(
        parent_case,
        _case("parent-en", "parent", "en", prompt="English"),
        _case("parent-ru", "parent", "ru", prompt="Russian"),
    )
    _write_manifest(
        invocation_cwd / "manifest.yaml",
        {
            "schema_version": "1",
            "runner_version": __version__,
            "run_name": "parent-capture",
            "provider": {"kind": "fake", "model": "fixture-v1"},
            "case_files": ["../cases/pair.yaml"],
            "arms": ["baseline"],
        },
    )

    def forbid_resolve(*_args: object, **_kwargs: object) -> Path:
        raise AssertionError("Path.resolve must not be used for v1 lexical semantics")

    monkeypatch.setattr(Path, "resolve", forbid_resolve)

    source = load_source_manifest_capture(
        "manifest.yaml",
        input_root=None,
        invocation_cwd=invocation_cwd,
    )
    captured = capture_authored_inputs(source, source_root=ROOT)

    case_file = next(item for item in captured.files if item.record.role == "case")
    assert case_file.data == case_bytes
    assert case_file.record.logical_locator == "case_files[0]"
    assert case_file.record.capsule_path == "inputs/cases/000.yaml"


@pytest.mark.parametrize("absolute_replay", [False, True])
def test_v1_replay_resolves_from_invocation_cwd_or_explicit_absolute_path(
    tmp_path: Path,
    absolute_replay: bool,
) -> None:
    invocation_cwd = tmp_path / "invocation"
    invocation_cwd.mkdir()
    _write_case(
        invocation_cwd / "cases.yaml",
        _case("replay-en", "replay", "en", prompt="English"),
        _case("replay-ru", "replay", "ru", prompt="Russian"),
    )
    replay_path = (
        tmp_path / "absolute/replay.yaml"
        if absolute_replay
        else invocation_cwd / "fixtures/replay.yaml"
    )
    replay_path.parent.mkdir(parents=True)
    replay_bytes = b"responses:\r\n  replay: exact\r\n"
    replay_path.write_bytes(replay_bytes)
    replay_locator = str(replay_path) if absolute_replay else "fixtures/replay.yaml"
    _write_manifest(
        invocation_cwd / "manifest.yaml",
        {
            "schema_version": "1",
            "runner_version": __version__,
            "run_name": "legacy-replay",
            "provider": {
                "kind": "replay",
                "model": "replay-v1",
                "api_key_env": "IGNORED_API_KEY",
                "replay_file": replay_locator,
            },
            "case_files": ["cases.yaml"],
            "arms": ["baseline"],
        },
    )

    source = load_source_manifest_capture(
        "manifest.yaml",
        input_root=None,
        invocation_cwd=invocation_cwd,
    )
    captured = capture_authored_inputs(source, source_root=ROOT)

    replay = next(item for item in captured.files if item.record.role == "replay")
    assert replay.data == replay_bytes
    assert replay.record.logical_locator == "provider.replay_file"
    assert replay.record.capsule_path == "inputs/provider/replay.yaml"
    assert captured.resolved_manifest.provider.api_key_env is None
    assert captured.resolved_manifest.provider.replay_file == "inputs/provider/replay.yaml"


def test_v2_capture_rejects_a_symlinked_input_root(tmp_path: Path) -> None:
    real_input = tmp_path / "real-input"
    real_input.mkdir()
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["pair.yaml"],
            datasets=[_dataset("symlink-dataset", [0])],
        ),
    )
    symlink_input = tmp_path / "symlink-input"
    symlink_input.symlink_to(real_input, target_is_directory=True)

    with pytest.raises(CaptureError) as error:
        load_source_manifest_capture(
            manifest_path,
            input_root=symlink_input,
            invocation_cwd=tmp_path,
        )

    assert error.value.code == "invalid_input_root"


@pytest.mark.parametrize("explicit_input_root", [False, True])
def test_v2_capture_is_independent_of_invocation_cwd(
    tmp_path: Path,
    explicit_input_root: bool,
) -> None:
    manifest_directory = tmp_path / "manifests"
    input_directory = tmp_path / "project" if explicit_input_root else manifest_directory
    _write_case(
        input_directory / "cases/en.yaml",
        _case("stable-en", "stable", "en", prompt="same bytes"),
    )
    _write_case(
        input_directory / "cases/ru.yaml",
        _case("stable-ru", "stable", "ru", prompt="those same bytes"),
    )
    manifest_path = manifest_directory / "capture.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["cases/en.yaml", "cases/ru.yaml"],
            datasets=[_dataset("stable-dataset", [0, 1])],
            arms=["baseline", "concise"],
        ),
    )
    cwd_a = tmp_path / "cwd-a"
    cwd_b = tmp_path / "cwd-b"
    cwd_a.mkdir()
    cwd_b.mkdir()
    explicit = input_directory if explicit_input_root else None

    source_a, capture_a = _capture_v2(
        manifest_path,
        invocation_cwd=cwd_a,
        input_root=explicit,
    )
    source_b, capture_b = _capture_v2(
        manifest_path,
        invocation_cwd=cwd_b,
        input_root=explicit,
    )

    assert source_a.source_manifest_commitment_sha256 == source_b.source_manifest_commitment_sha256
    assert capture_a.resolved_manifest == capture_b.resolved_manifest
    assert capture_a.resolved_manifest_bytes == capture_b.resolved_manifest_bytes
    assert capture_a.manifest_sha256 == capture_b.manifest_sha256
    assert capture_a.records == capture_b.records
    assert capture_a.files == capture_b.files


def test_synthetic_arms_do_not_require_or_open_a_source_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.capsule.capture as capture_module

    input_root = tmp_path / "input"
    _write_case(
        input_root / "pair.yaml",
        _case("synthetic-en", "synthetic", "en", prompt="English"),
        _case("synthetic-ru", "synthetic", "ru", prompt="Russian"),
    )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["pair.yaml"],
            datasets=[_dataset("synthetic", [0])],
            arms=["baseline", "concise"],
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )
    original_open = capture_module._open_verified_directory

    def reject_source_root_open(path: Path, *, code: str) -> int:
        assert code != "invalid_source_root"
        return original_open(path, code=code)

    monkeypatch.setattr(capture_module, "_open_verified_directory", reject_source_root_open)

    captured = capture_authored_inputs(source, source_root=None)

    assert [arm.name for arm in captured.arms] == ["baseline", "concise"]


def test_file_backed_arms_fail_closed_without_a_source_root(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    _write_case(
        input_root / "pair.yaml",
        _case("file-arm-en", "file-arm", "en", prompt="English"),
        _case("file-arm-ru", "file-arm", "ru", prompt="Russian"),
    )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["pair.yaml"],
            datasets=[_dataset("file-arm", [0])],
            arms=["if"],
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )

    with pytest.raises(CaptureError) as error:
        capture_authored_inputs(source, source_root=None)

    assert error.value.code == "missing_source_root"


def test_capture_binds_all_authored_bytes_and_emits_only_logical_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.capsule.capture as capture_module

    input_root = tmp_path / "input"
    en_bytes = _write_case(
        input_root / "cases/source.with.untrusted.suffix",
        _case("complete-en", "complete", "en", prompt="English prompt"),
    )
    ru_bytes = _write_case(
        input_root / "cases/no-suffix",
        _case("complete-ru", "complete", "ru", prompt="Русский запрос"),
    )
    replay_bytes = b"responses:\r\n  - exact: true\r\n"
    replay_path = input_root / "provider/local.replay"
    replay_path.parent.mkdir(parents=True)
    replay_path.write_bytes(replay_bytes)
    protocol_bytes = b"\x00protocol\xffbytes"
    protocol_source = input_root / "protocols/evil.name.json"
    protocol_source.parent.mkdir(parents=True)
    protocol_source.write_bytes(protocol_bytes)
    binding_id = "../../untrusted binding/name"
    protocol_binding = {
        "binding_id": binding_id,
        "kind": "https://example.test/untrusted/kind",
        "schema_id": "https://example.test/schema/v1",
        "media_type": 'application/example+json; profile="../unsafe"',
        "path": "protocols/evil.name.json",
        "scope": {"dataset_ids": ["complete-dataset"], "comparison_ids": ["if-vs-concise"]},
        "bound_at_stage": "pre_generation",
        "applies_at": ["scoring", "publication"],
        "declared_requirement": "required_for_declared_claim",
    }
    manifest_path = tmp_path / "manifests/capture.yaml"
    source_bytes = _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["cases/source.with.untrusted.suffix", "cases/no-suffix"],
            datasets=[_dataset("complete-dataset", [0, 1])],
            arms=["baseline", "concise", "caveman", "if"],
            provider={
                "kind": "replay",
                "model": "replay-v1",
                "api_key_env": None,
                "replay_file": "provider/local.replay",
            },
            comparisons=[
                {
                    "comparison_id": "if-vs-concise",
                    "left_arm": "if",
                    "right_arm": "concise",
                    "role": "primary",
                }
            ],
            protocol_bindings=[protocol_binding],
        ),
    )
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=cwd,
    )
    original_read = capture_module.read_regular_file_once
    reads: set[tuple[int, int, str]] = set()

    def read_once(directory_fd: int, path: str, *, limit: int, code: str) -> bytes:
        metadata = os.fstat(directory_fd)
        key = (metadata.st_dev, metadata.st_ino, path)
        assert key not in reads, f"source reopened: {path}"
        reads.add(key)
        return original_read(directory_fd, path, limit=limit, code=code)

    monkeypatch.setattr(capture_module, "read_regular_file_once", read_once)

    captured = capture_authored_inputs(source, source_root=ROOT)

    protocol_prefix = sha256(binding_id.encode("utf-8")).hexdigest()[:16]
    protocol_destination = f"inputs/protocols/000-{protocol_prefix}.bin"
    expected_bytes = {
        "inputs/arms/baseline.txt": b"",
        "inputs/arms/caveman/LICENSE.txt": (ROOT / "LICENSES/CAVEMAN-MIT.txt").read_bytes(),
        "inputs/arms/caveman/SKILL.md": (ROOT / "evals/baselines/caveman/SKILL.md").read_bytes(),
        "inputs/arms/caveman/SOURCE.md": (ROOT / "evals/baselines/caveman/SOURCE.md").read_bytes(),
        "inputs/arms/concise.txt": b"Answer concisely.",
        "inputs/arms/if/SKILL.md": (ROOT / "skills/if/SKILL.md").read_bytes(),
        "inputs/cases/000.yaml": en_bytes,
        "inputs/cases/001.yaml": ru_bytes,
        protocol_destination: protocol_bytes,
        "inputs/provider/replay.yaml": replay_bytes,
    }
    assert {item.record.capsule_path: item.data for item in captured.files} == expected_bytes
    assert tuple(record.capsule_path for record in captured.records) == tuple(
        sorted(expected_bytes, key=lambda value: value.encode("utf-8"))
    )
    assert len(captured.records) == len({record.capsule_path for record in captured.records})
    assert [arm.name for arm in captured.arms] == ["baseline", "concise", "caveman", "if"]
    assert [arm.instruction for arm in captured.arms] == [
        None,
        "Answer concisely.",
        expected_bytes["inputs/arms/caveman/SKILL.md"].decode("utf-8"),
        expected_bytes["inputs/arms/if/SKILL.md"].decode("utf-8"),
    ]
    assert [arm.sha256 for arm in captured.arms] == [
        sha256(b"").hexdigest(),
        sha256(b"Answer concisely.").hexdigest(),
        _CAVEMAN_SKILL_SHA256,
        sha256(expected_bytes["inputs/arms/if/SKILL.md"]).hexdigest(),
    ]
    assert sha256(expected_bytes["inputs/arms/caveman/SOURCE.md"]).hexdigest() == (
        _CAVEMAN_SOURCE_SHA256
    )
    assert captured.source_manifest_commitment_sha256 == sha256(source_bytes).hexdigest()
    assert captured.resolved_manifest_bytes == canonical_json(
        captured.resolved_manifest.model_dump(mode="json")
    )
    assert captured.manifest_sha256 == sha256(captured.resolved_manifest_bytes).hexdigest()
    assert captured.resolved_manifest.provider.replay_file == "inputs/provider/replay.yaml"
    binding = captured.resolved_manifest.capsule.protocol_bindings[0]
    assert binding.path == protocol_destination
    assert binding.byte_length == len(protocol_bytes)
    assert binding.sha256 == sha256(protocol_bytes).hexdigest()
    protocol_record = next(record for record in captured.records if record.role == "protocol")
    assert protocol_record.logical_locator == "capsule.protocol_bindings[0].path"
    assert protocol_record.binding_id == binding_id
    assert protocol_record.capsule_path == protocol_destination
    assert all(
        record.capsule_path
        not in {
            "capsule.json",
            "manifest.json",
            "environment.json",
            "case-index.jsonl",
            "plan.jsonl",
            "events.jsonl",
            "raw.jsonl",
            "inputs/index.json",
            ".laconian.lock",
        }
        for record in captured.records
    )
    dataset = captured.resolved_manifest.capsule.datasets[0]
    assert dataset.dataset_content_sha256 == stable_digest(
        "laconian-dataset-content-v1",
        {
            "dataset_id": "complete-dataset",
            "dataset_version": "fixture-v1",
            "members": [
                {
                    "source_ordinal": 0,
                    "capsule_path": "inputs/cases/000.yaml",
                    "byte_length": len(en_bytes),
                    "sha256": sha256(en_bytes).hexdigest(),
                },
                {
                    "source_ordinal": 1,
                    "capsule_path": "inputs/cases/001.yaml",
                    "byte_length": len(ru_bytes),
                    "sha256": sha256(ru_bytes).hexdigest(),
                },
            ],
        },
    )
    metadata = captured.resolved_manifest_bytes + canonical_json(_record_payloads(captured))
    for host_path in (tmp_path, input_root, manifest_path, ROOT, Path.home()):
        assert str(host_path).encode("utf-8") not in metadata
    assert isinstance(captured.files, tuple)
    assert all(isinstance(item.data, bytes) for item in captured.files)
    with pytest.raises(FrozenInstanceError):
        captured.manifest_sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        captured.files[0].data = b"changed"  # type: ignore[misc]


def test_shared_source_locator_is_read_once_and_reuses_the_captured_buffer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.capsule.capture as capture_module

    input_root = tmp_path / "input"
    _write_case(
        input_root / "pair.yaml",
        _case("shared-en", "shared", "en", prompt="English"),
        _case("shared-ru", "shared", "ru", prompt="Russian"),
    )
    shared_bytes = b"one physical source\x00shared by three logical members"
    (input_root / "shared.bin").write_bytes(shared_bytes)
    bindings = [
        {
            "binding_id": f"shared-binding-{ordinal}",
            "kind": "example.org/protocol",
            "schema_id": "example.org/protocol/v1",
            "media_type": "application/octet-stream",
            "path": "shared.bin",
            "scope": {"dataset_ids": ["shared"], "comparison_ids": []},
            "bound_at_stage": "pre_generation",
            "applies_at": ["scoring"],
            "declared_requirement": "optional",
        }
        for ordinal in range(2)
    ]
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["pair.yaml"],
            datasets=[_dataset("shared", [0])],
            provider={
                "kind": "replay",
                "model": "replay-v1",
                "api_key_env": None,
                "replay_file": "shared.bin",
            },
            protocol_bindings=bindings,
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )
    original_read = capture_module.read_regular_file_once
    reads: dict[str, int] = {}

    def count_reads(directory_fd: int, path: str, *, limit: int, code: str) -> bytes:
        reads[path] = reads.get(path, 0) + 1
        return original_read(directory_fd, path, limit=limit, code=code)

    monkeypatch.setattr(capture_module, "read_regular_file_once", count_reads)

    captured = capture_authored_inputs(source, source_root=None)

    shared_members = tuple(
        item for item in captured.files if item.record.role in {"replay", "protocol"}
    )
    assert reads["shared.bin"] == 1
    assert len(shared_members) == 3
    assert all(item.data is shared_members[0].data for item in shared_members)
    assert all(item.data == shared_bytes for item in shared_members)


@pytest.mark.parametrize(
    ("member", "replacement"),
    [
        ("evals/baselines/caveman/SKILL.md", b"drifted skill"),
        (
            "evals/baselines/caveman/SOURCE.md",
            (
                f"- Commit: `{'0' * 40}`\n- SHA-256: `{_CAVEMAN_SKILL_SHA256}`\n- License: MIT\n"
            ).encode(),
        ),
        (
            "evals/baselines/caveman/SOURCE.md",
            (ROOT / "evals/baselines/caveman/SOURCE.md").read_bytes()
            + b"\n# conflicting provenance\n",
        ),
        ("LICENSES/CAVEMAN-MIT.txt", b"not the bundled license"),
    ],
)
def test_capture_rejects_caveman_pin_or_license_drift(
    tmp_path: Path,
    member: str,
    replacement: bytes,
) -> None:
    input_root = tmp_path / "input"
    _write_case(
        input_root / "en.yaml",
        _case("pin-en", "pin", "en", prompt="English"),
    )
    _write_case(
        input_root / "ru.yaml",
        _case("pin-ru", "pin", "ru", prompt="Russian"),
    )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["en.yaml", "ru.yaml"],
            datasets=[_dataset("pin-dataset", [0, 1])],
            arms=["caveman"],
        ),
    )
    source_root = tmp_path / "source"
    _copy_arm_sources(source_root)
    (source_root / member).write_bytes(replacement)
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )

    with pytest.raises(CaptureError) as error:
        capture_authored_inputs(source, source_root=source_root)

    assert error.value.code == "caveman_pin_mismatch"
    assert _CAVEMAN_COMMIT not in str(error.value)


def test_dataset_locale_ownership_allows_complete_reuse_in_separate_datasets(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    definitions = [
        ("alpha-en", "en", "alpha English"),
        ("alpha-ru", "ru", "alpha Russian"),
        ("beta-en", "en", "beta English"),
        ("beta-ru", "ru", "beta Russian"),
    ]
    paths: list[str] = []
    for ordinal, (case_id, locale, prompt) in enumerate(definitions):
        relative = f"cases/{ordinal}.yaml"
        paths.append(relative)
        _write_case(
            input_root / relative,
            _case(case_id, "shared-scenario", locale, prompt=prompt),
        )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=paths,
            datasets=[_dataset("alpha", [0, 1]), _dataset("beta", [2, 3])],
        ),
    )

    _, captured = _capture_v2(
        manifest_path,
        invocation_cwd=tmp_path,
        input_root=input_root,
    )

    assert [
        (case_file.source_ordinal, case_file.dataset_id) for case_file in captured.case_files
    ] == [
        (0, "alpha"),
        (1, "alpha"),
        (2, "beta"),
        (3, "beta"),
    ]


def test_dataset_digest_sorts_members_by_source_ordinal_but_retains_authored_tuple(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "input"
    source_bytes = [
        _write_case(
            input_root / "zero.yaml",
            _case("ordered-en", "ordered", "en", prompt="ordinal zero"),
        ),
        _write_case(
            input_root / "one.yaml",
            _case("ordered-ru", "ordered", "ru", prompt="ordinal one"),
        ),
    ]
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["zero.yaml", "one.yaml"],
            datasets=[_dataset("ordered", [1, 0])],
        ),
    )

    _, captured = _capture_v2(
        manifest_path,
        invocation_cwd=tmp_path,
        input_root=input_root,
    )

    dataset = captured.resolved_manifest.capsule.datasets[0]
    assert dataset.case_file_ordinals == (1, 0)
    assert dataset.dataset_content_sha256 == stable_digest(
        "laconian-dataset-content-v1",
        {
            "dataset_id": "ordered",
            "dataset_version": "fixture-v1",
            "members": [
                {
                    "source_ordinal": ordinal,
                    "capsule_path": f"inputs/cases/{ordinal:03d}.yaml",
                    "byte_length": len(source_bytes[ordinal]),
                    "sha256": sha256(source_bytes[ordinal]).hexdigest(),
                }
                for ordinal in (0, 1)
            ],
        },
    )


def test_dataset_locale_ownership_rejects_a_pair_split_across_datasets(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    _write_case(
        input_root / "en.yaml",
        _case("split-en", "split", "en", prompt="English"),
    )
    _write_case(
        input_root / "ru.yaml",
        _case("split-ru", "split", "ru", prompt="Russian"),
    )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["en.yaml", "ru.yaml"],
            datasets=[_dataset("alpha", [0]), _dataset("beta", [1])],
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )

    with pytest.raises(CaptureError) as error:
        capture_authored_inputs(source, source_root=ROOT)

    assert error.value.code == "dataset_locale_ownership"
    assert "split" not in str(error.value)


def test_capture_rejects_global_duplicate_case_ids_across_datasets(tmp_path: Path) -> None:
    input_root = tmp_path / "input"
    definitions = [
        ("duplicate-en", "alpha", "en"),
        ("alpha-ru", "alpha", "ru"),
        ("duplicate-en", "beta", "en"),
        ("beta-ru", "beta", "ru"),
    ]
    paths: list[str] = []
    for ordinal, (case_id, scenario_id, locale) in enumerate(definitions):
        relative = f"cases/{ordinal}.yaml"
        paths.append(relative)
        _write_case(
            input_root / relative,
            _case(case_id, scenario_id, locale, prompt=f"prompt {ordinal}"),
        )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=paths,
            datasets=[_dataset("alpha", [0, 1]), _dataset("beta", [2, 3])],
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )

    with pytest.raises(CaptureError) as error:
        capture_authored_inputs(source, source_root=ROOT)

    assert error.value.code == "duplicate_case_id"
    assert "duplicate-en" not in str(error.value)


def test_source_manifest_capture_enforces_the_exact_byte_cap(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.yaml"
    oversized.write_bytes(b"x" * (RESOURCE_LIMITS_V1.source_manifest_bytes + 1))

    with pytest.raises(ResourceLimitError) as error:
        load_source_manifest_capture(
            oversized,
            input_root=None,
            invocation_cwd=tmp_path,
        )

    assert error.value.code == "source_manifest_limit"


@pytest.mark.parametrize(
    ("limit_field", "expected_code"),
    [
        ("all_case_files_bytes", "all_case_files_limit"),
        ("captured_input_total_bytes", "captured_input_total_limit"),
    ],
)
def test_capture_enforces_case_and_total_aggregate_caps_before_a_second_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_field: str,
    expected_code: str,
) -> None:
    import laconian_eval.capsule.capture as capture_module

    input_root = tmp_path / "input"
    en_bytes = _write_case(
        input_root / "en.yaml",
        _case("limit-en", "limit", "en", prompt="English"),
    )
    ru_bytes = _write_case(
        input_root / "ru.yaml",
        _case("limit-ru", "limit", "ru", prompt="Russian"),
    )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["en.yaml", "ru.yaml"],
            datasets=[_dataset("limit", [0, 1])],
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )
    aggregate_limit = len(en_bytes) + len(ru_bytes) - 1
    monkeypatch.setattr(
        capture_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, **{limit_field: aggregate_limit}),
    )

    with pytest.raises(ResourceLimitError) as error:
        capture_authored_inputs(source, source_root=ROOT)

    assert error.value.code == expected_code


def test_capture_enforces_arm_and_protocol_aggregate_caps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.capsule.capture as capture_module

    input_root = tmp_path / "input"
    _write_case(
        input_root / "pair.yaml",
        _case("aggregate-en", "aggregate", "en", prompt="English"),
        _case("aggregate-ru", "aggregate", "ru", prompt="Russian"),
    )
    for ordinal in range(2):
        protocol = input_root / f"protocol-{ordinal}.bin"
        protocol.write_bytes(b"protocol-bytes")
    bindings = [
        {
            "binding_id": f"binding-{ordinal}",
            "kind": "example.org/protocol",
            "schema_id": "example.org/protocol/v1",
            "media_type": "application/octet-stream",
            "path": f"protocol-{ordinal}.bin",
            "scope": {"dataset_ids": ["aggregate"], "comparison_ids": []},
            "bound_at_stage": "pre_generation",
            "applies_at": ["scoring"],
            "declared_requirement": "optional",
        }
        for ordinal in range(2)
    ]
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["pair.yaml"],
            datasets=[_dataset("aggregate", [0])],
            arms=["concise"],
            protocol_bindings=bindings,
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )

    monkeypatch.setattr(
        capture_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, all_arm_members_bytes=16),
    )
    with pytest.raises(ResourceLimitError) as arm_error:
        capture_authored_inputs(source, source_root=ROOT)
    assert arm_error.value.code == "all_arm_members_limit"

    monkeypatch.setattr(
        capture_module,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, all_protocol_files_bytes=27),
    )
    with pytest.raises(ResourceLimitError) as protocol_error:
        capture_authored_inputs(source, source_root=ROOT)
    assert protocol_error.value.code == "all_protocol_files_limit"


def test_protocol_ordinals_prevent_collisions_when_hash_prefixes_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.capsule.capture as capture_module
    import laconian_eval.capsule.manifest_models as manifest_models
    import laconian_eval.capsule.record_models as record_models

    input_root = tmp_path / "input"
    _write_case(
        input_root / "pair.yaml",
        _case("prefix-en", "prefix", "en", prompt="English"),
        _case("prefix-ru", "prefix", "ru", prompt="Russian"),
    )
    bindings: list[dict[str, Any]] = []
    for ordinal in range(2):
        (input_root / f"protocol-{ordinal}.bin").write_bytes(bytes([ordinal]))
        bindings.append(
            {
                "binding_id": f"binding-{ordinal}",
                "kind": "example.org/protocol",
                "schema_id": "example.org/protocol/v1",
                "media_type": "application/octet-stream",
                "path": f"protocol-{ordinal}.bin",
                "scope": {"dataset_ids": ["prefix"], "comparison_ids": []},
                "bound_at_stage": "pre_generation",
                "applies_at": ["scoring"],
                "declared_requirement": "optional",
            }
        )
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        _source_v2(
            case_files=["pair.yaml"],
            datasets=[_dataset("prefix", [0])],
            protocol_bindings=bindings,
        ),
    )
    source = load_source_manifest_capture(
        manifest_path,
        input_root=input_root,
        invocation_cwd=tmp_path,
    )
    monkeypatch.setattr(capture_module, "_binding_sha_prefix", lambda _value: "0" * 16)
    fake_hashlib = SimpleNamespace(
        sha256=lambda _value: SimpleNamespace(hexdigest=lambda: "0" * 64)
    )
    monkeypatch.setattr(record_models, "hashlib", fake_hashlib)
    monkeypatch.setattr(manifest_models, "hashlib", fake_hashlib)

    captured = capture_authored_inputs(source, source_root=ROOT)

    protocol_paths = [
        record.capsule_path for record in captured.records if record.role == "protocol"
    ]
    assert protocol_paths == [
        "inputs/protocols/000-0000000000000000.bin",
        "inputs/protocols/001-0000000000000000.bin",
    ]


def test_project_v1_manifest_preserves_legacy_three_rate_price_privately() -> None:
    import laconian_eval.capsule.manifest_models as manifest_models

    payload = {
        "schema_version": "1",
        "runner_version": __version__,
        "run_name": "legacy-priced",
        "provider": {"kind": "fake", "model": "fixture-v1"},
        "case_files": ["cases/en.yaml"],
        "arms": ["baseline"],
        "price_snapshot": {
            "currency": "USD",
            "effective_date": "2026-08-27",
            "source_url": "HTTP://EXAMPLE.test:80/prices/%7Ecurrent?b=2&a=1",
            "input_per_million": "1",
            "cached_input_per_million": "0.125",
            "output_per_million": "2",
        },
    }
    RunManifest.model_validate(payload)
    legacy = project_v1_manifest(payload)
    assert legacy.price_snapshot is not None
    assert type(legacy.price_snapshot) is manifest_models._V1LegacyPriceSnapshotProjection
    assert legacy.price_snapshot.model_dump(mode="json") == {
        "currency": "USD",
        "effective_date": "2026-08-27",
        "source_url": "HTTP://EXAMPLE.test:80/prices/%7Ecurrent?b=2&a=1",
        "input_per_million": 1.0,
        "cached_input_per_million": 0.125,
        "output_per_million": 2.0,
    }
    assert tuple(type(legacy.price_snapshot).model_fields) == (
        "currency",
        "effective_date",
        "source_url",
        "input_per_million",
        "cached_input_per_million",
        "output_per_million",
    )


def test_priced_v1_upgrade_requires_explicit_native_v2_before_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import laconian_eval.capsule.capture as capture_module

    legacy = project_v1_manifest(
        {
            "schema_version": "1",
            "runner_version": __version__,
            "run_name": "legacy-priced",
            "provider": {"kind": "fake", "model": "fixture-v1"},
            "case_files": ["cases/en.yaml"],
            "arms": ["baseline"],
            "price_snapshot": {
                "currency": "USD",
                "effective_date": "2026-08-27",
                "source_url": "HTTP://EXAMPLE.test:80/prices/%7Ecurrent?b=2&a=1",
                "input_per_million": 1,
                "cached_input_per_million": 0.125,
                "output_per_million": 2,
            },
        }
    )

    expected_message = (
        "v1 price snapshots require explicit migration to a native-v2 five-rate "
        "source-evidence manifest"
    )
    with pytest.raises(CaptureError) as direct_error:
        upgrade_v1_manifest(legacy, dataset_content_sha256="a" * 64)
    assert direct_error.value.code == "v1_price_snapshot_requires_native_v2"
    assert direct_error.value.args == (expected_message,)
    assert direct_error.value.__cause__ is None
    assert direct_error.value.__context__ is None

    manifest_path = tmp_path / "priced-v1.yaml"
    manifest_path.write_text(
        """schema_version: '1'
runner_version: 0.1.0a1
run_name: legacy-priced
provider: {kind: fake, model: fixture-v1}
case_files: [cases/en.yaml]
arms: [baseline]
price_snapshot:
  currency: USD
  effective_date: '2026-08-27'
  source_url: https://example.test/prices
  input_per_million: 1
  cached_input_per_million: 0.125
  output_per_million: 2
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        capture_module,
        "_verify_input_root",
        lambda _root: (_ for _ in ()).throw(AssertionError("input root accessed")),
    )
    with pytest.raises(CaptureError) as load_error:
        load_source_manifest_capture(manifest_path, input_root=None, invocation_cwd=tmp_path)
    assert load_error.value.code == "v1_price_snapshot_requires_native_v2"
    assert load_error.value.args == (expected_message,)
    assert load_error.value.__cause__ is None
    assert load_error.value.__context__ is None

    accesses = {
        "case": 0,
        "arm": 0,
        "replay": 0,
        "protocol": 0,
        "root_resolve": 0,
        "root_open": 0,
        "provider": 0,
        "credential": 0,
        "client": 0,
    }

    def reject_access(name: str) -> Any:
        def rejected(*args: object, **kwargs: object) -> Any:
            accesses[name] += 1
            raise AssertionError(f"priced v1 guard must precede {name} access")

        return rejected

    for attribute, name in (
        ("_capture_cases", "case"),
        ("_capture_arms", "arm"),
        ("_capture_replay", "replay"),
        ("_capture_protocols", "protocol"),
        ("_lexical_absolute", "root_resolve"),
        ("_open_verified_directory", "root_open"),
    ):
        monkeypatch.setattr(capture_module, attribute, reject_access(name))

    from laconian_eval.providers.openai import OpenAIProvider

    monkeypatch.setattr(OpenAIProvider, "__init__", reject_access("client"))
    monkeypatch.setattr(OpenAIProvider, "generate", reject_access("provider"))
    monkeypatch.setattr(type(os.environ), "get", reject_access("credential"))

    source_bytes = b"priced-v1-source"
    captured_source = CapturedSourceManifest(
        source_bytes=source_bytes,
        source_manifest_commitment_sha256=sha256(source_bytes).hexdigest(),
        source_manifest=legacy,
        _input_root=Path("/must-not-resolve-or-open"),
    )
    with pytest.raises(CaptureError) as capture_error:
        capture_authored_inputs(
            captured_source,
            source_root=Path("/must-not-resolve-or-open-source-root"),
        )
    assert capture_error.value.code == "v1_price_snapshot_requires_native_v2"
    assert capture_error.value.args == (expected_message,)
    assert capture_error.value.__cause__ is None
    assert capture_error.value.__context__ is None
    assert accesses == dict.fromkeys(accesses, 0)
