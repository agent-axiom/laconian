from __future__ import annotations

import ast
import importlib.metadata as metadata
import json
import os
import shutil
import socket
import stat
import subprocess
from collections import deque
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capsule_helpers import resolved_manifest_v2_payload

from laconian_eval import __version__
from laconian_eval.capsule.canonical import canonical_json, sha256_bytes, stable_digest
from laconian_eval.capsule.capture import CapturedInputFile, CapturedInputs
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.provenance import (
    ProvenanceError,
    capture_dependency_closure,
    capture_distribution_inventory,
    capture_installed_provenance,
    capture_resume_provenance,
    capture_runner_source,
    parse_container_image_digest,
    project_environment,
    resolve_source_root,
)
from laconian_eval.capsule.record_models import (
    ImportEnvironmentV1,
    InputFileRecordV1,
)

ROOT = Path(__file__).parents[2]
_OPENAI_CLOSURE = (
    "annotated-types",
    "anyio",
    "h11",
    "httpcore2",
    "httpx2",
    "idna",
    "jiter",
    "openai",
    "packaging",
    "pydantic",
    "pydantic-core",
    "pyyaml",
    "sniffio",
    "truststore",
    "typing-extensions",
    "typing-inspection",
)
_OFFLINE_CLOSURE = (
    "annotated-types",
    "packaging",
    "pydantic",
    "pydantic-core",
    "pyyaml",
    "typing-extensions",
    "typing-inspection",
)


def _captured_inputs(
    *,
    provider_kind: str = "fake",
    requested_model: str = "fixture-v1",
    runner_version: str = __version__,
    authored_data: bytes | None = None,
) -> CapturedInputs:
    payload = resolved_manifest_v2_payload()
    payload["runner_version"] = runner_version
    provider = payload["provider"]
    assert isinstance(provider, dict)
    provider.update(
        {
            "kind": provider_kind,
            "model": requested_model,
            "api_key_env": "OPENAI_API_KEY" if provider_kind == "openai" else None,
            "replay_file": "inputs/provider/replay.yaml" if provider_kind == "replay" else None,
        }
    )
    resolved = ResolvedManifestV2.model_validate(payload)
    resolved_bytes = canonical_json(resolved.model_dump(mode="json"))
    files: tuple[CapturedInputFile, ...] = ()
    if authored_data is not None:
        record = InputFileRecordV1.model_validate(
            {
                "role": "case",
                "role_ordinal": 0,
                "logical_locator": "case_files[0]",
                "capsule_path": "inputs/cases/000.yaml",
                "byte_length": len(authored_data),
                "sha256": sha256_bytes(authored_data),
                "dataset_id": "dataset-alpha",
                "binding_id": None,
            }
        )
        files = (CapturedInputFile(record=record, data=authored_data),)
    return CapturedInputs(
        source_manifest_commitment_sha256="0" * 64,
        resolved_manifest=resolved,
        resolved_manifest_bytes=resolved_bytes,
        manifest_sha256=sha256_bytes(resolved_bytes),
        files=files,
        case_files=(),
        arms=(),
    )


def _import_environment() -> ImportEnvironmentV1:
    return ImportEnvironmentV1.model_validate(
        {
            "import_policy_version": "laconian-import-policy-v1",
            "stdlib_origin_policy": "interpreter-layout-v1",
            "stdlib_extension_policy": "destshared-v1",
            "platstdlib_mode": "same_as_stdlib",
            "guard_source_sha256": "1" * 64,
            "audit_hook_source_sha256": "1" * 64,
            "runner_import_mode": "path",
            "launcher_mode": "module",
            "launcher_template_sha256": None,
            "virtualenv_bootstrap_sha256": None,
            "import_roots": [
                {
                    "distribution": "packaging",
                    "module": "packaging",
                    "origin_member": "packaging/__init__.py",
                },
                {
                    "distribution": "pydantic",
                    "module": "pydantic",
                    "origin_member": "pydantic/__init__.py",
                },
                {
                    "distribution": "pydantic-core",
                    "module": "pydantic_core",
                    "origin_member": "pydantic_core/__init__.py",
                },
                {
                    "distribution": "pyyaml",
                    "module": "yaml",
                    "origin_member": "yaml/__init__.py",
                },
            ],
        }
    )


def _make_distribution(
    site: Path,
    name: str,
    version: str = "1.0",
    *,
    requires: tuple[str, ...] = (),
    direct_url: dict[str, object] | None = None,
    list_direct_url: bool = True,
    external_script: str | None = None,
    extra_record_rows: tuple[str, ...] = (),
) -> metadata.Distribution:
    normalized = name.lower().replace("-", "_")
    dist_info = site / f"{normalized}-{version}.dist-info"
    package = site / normalized
    dist_info.mkdir(parents=True)
    package.mkdir(parents=True)
    metadata_text = "\n".join(
        (
            "Metadata-Version: 2.4",
            f"Name: {name}",
            f"Version: {version}",
            *(f"Requires-Dist: {requirement}" for requirement in requires),
            "",
            "",
        )
    )
    (dist_info / "METADATA").write_text(metadata_text, encoding="utf-8")
    (dist_info / "WHEEL").write_text("Wheel-Version: 1.0\n", encoding="utf-8")
    (dist_info / "RECORD").write_text("", encoding="utf-8")
    (dist_info / "INSTALLER").write_text("fixture\n", encoding="utf-8")
    (dist_info / "REQUESTED").write_bytes(b"")
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    rows = [
        f"{dist_info.name}/METADATA,,",
        f"{dist_info.name}/WHEEL,,",
        f"{dist_info.name}/RECORD,,",
        f"{dist_info.name}/INSTALLER,,",
        f"{dist_info.name}/REQUESTED,,",
        f"{package.name}/__init__.py,,",
    ]
    if direct_url is not None:
        (dist_info / "direct_url.json").write_text(json.dumps(direct_url), encoding="utf-8")
        if list_direct_url:
            rows.append(f"{dist_info.name}/direct_url.json,,")
    if external_script is not None:
        entry_point_target = (
            "laconian_eval.cli:entrypoint"
            if name == "laconian-eval" and external_script == "laconian"
            else f"{normalized}:main"
        )
        (dist_info / "entry_points.txt").write_text(
            f"[console_scripts]\n{external_script} = {entry_point_target}\n", encoding="utf-8"
        )
        rows.extend(
            (
                f"{dist_info.name}/entry_points.txt,,",
                f"../../../bin/{external_script},,",
            )
        )
    rows.extend(extra_record_rows)
    (dist_info / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")
    matches = tuple(
        distribution
        for distribution in metadata.distributions(path=[os.fspath(site)])
        if distribution.metadata["Name"] == name
    )
    assert len(matches) == 1
    return matches[0]


def _scripts_root_for_site(site: Path) -> Path:
    return Path(os.path.abspath(os.path.join(site, "../../../bin")))


@pytest.fixture(scope="module")
def offline_provenance():  # type: ignore[no-untyped-def]
    return capture_installed_provenance(
        _captured_inputs(),
        source_root=ROOT,
        container_image_digest=None,
    )


def test_runner_source_inventory_uses_exact_sorted_single_read_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    calls: list[str] = []
    original = provenance.read_regular_file_snapshot

    def counted(directory_fd: int, path: str, *, limit: int, code: str) -> Any:
        calls.append(path)
        return original(directory_fd, path, limit=limit, code=code)

    monkeypatch.setattr(provenance, "read_regular_file_snapshot", counted)
    captured = capture_runner_source()
    paths = tuple(member.path for member in captured.index.files)
    assert paths == tuple(sorted(paths, key=lambda value: value.encode("utf-8")))
    assert len(paths) == len(set(paths)) == len(calls)
    assert calls == list(paths)
    assert all(path.endswith(".py") or path == "py.typed" for path in paths)
    assert captured.index.runner_source_sha256 == stable_digest(
        "laconian-runner-source-v1",
        {
            "package_name": "laconian-eval",
            "files": [member.model_dump(mode="json") for member in captured.index.files],
        },
    )
    assert captured.index_bytes == canonical_json(captured.index.model_dump(mode="json"))
    assert tuple(item.record.role_ordinal for item in captured.files) == tuple(range(len(paths)))
    for path, source_file, copied in zip(paths, captured.index.files, captured.files, strict=True):
        assert copied.data is captured.file_bytes[path]
        assert copied.record.logical_locator == f"package[laconian_eval]/{path}"
        assert copied.record.byte_length == source_file.byte_length == len(copied.data)
        assert copied.record.sha256 == source_file.sha256 == sha256_bytes(copied.data)


def test_private_runner_origins_and_distribution_metadata_support_import_policy(
    offline_provenance: Any,
) -> None:
    runner = offline_provenance.runner_source
    assert runner._package_root.is_absolute()
    assert runner._package_parent == runner._package_root.parent
    assert set(runner.origins) == {item.path for item in runner.index.files}
    for item in runner.index.files:
        origin = runner.origins[item.path]
        assert origin.path == runner._package_root / item.path
        assert origin.path.is_absolute()
        assert origin.identity.size == item.byte_length
        assert stat.S_ISREG(origin.identity.mode)

    distribution = offline_provenance.runner_distribution
    assert distribution._site_packages_root.is_absolute()
    assert b"Name: laconian-eval" in distribution.metadata_bytes
    assert b"laconian = laconian_eval.cli:entrypoint" in distribution.entry_points_bytes
    assert distribution.files == tuple(distribution.files)


@pytest.mark.parametrize("member", ["asset.txt", "nested/py.typed"])
def test_runner_source_rejects_unexpected_regular_members(tmp_path: Path, member: str) -> None:
    package = tmp_path / "laconian_eval"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"")
    target = package / member
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"unexpected")
    with pytest.raises(ProvenanceError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "unexpected_runner_member"
    assert "unexpected" not in str(caught.value)


def test_runner_source_rejects_symlinks(tmp_path: Path) -> None:
    package = tmp_path / "laconian_eval"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"")
    (package / "linked.py").symlink_to(package / "__init__.py")
    with pytest.raises(ProvenanceError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "unsafe_runner_member"


def test_runner_source_rejects_symlinked_directories(tmp_path: Path) -> None:
    package = tmp_path / "laconian_eval"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.py").write_bytes(b"payload")
    (package / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ProvenanceError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "unsafe_runner_member"


def test_runner_source_rejects_intermediate_swap_during_descriptor_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import bounded_io, provenance

    package = tmp_path / "laconian_eval"
    nested = package / "nested"
    nested.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (nested / "payload.py").write_bytes(b"GOOD")
    evil = tmp_path / "evil"
    evil.mkdir()
    (evil / "payload.py").write_bytes(b"EVIL")
    parked = package / "parked"
    original = bounded_io.read_regular_file_snapshot

    def swap_for_snapshot(  # type: ignore[no-untyped-def]
        directory_fd: int, path: str, *, limit: int, code: str
    ):
        if path != "nested/payload.py":
            return original(directory_fd, path, limit=limit, code=code)
        nested.rename(parked)
        evil.rename(nested)
        try:
            return original(directory_fd, path, limit=limit, code=code)
        finally:
            nested.rename(evil)
            parked.rename(nested)

    monkeypatch.setattr(
        provenance,
        "read_regular_file_snapshot",
        swap_for_snapshot,
        raising=False,
    )
    with pytest.raises(ProvenanceError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "unstable_file_snapshot"
    assert b"EVIL" not in str(caught.value).encode()


def test_runner_source_rejects_member_added_after_initial_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    package = tmp_path / "laconian_eval"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"")
    original = provenance.read_regular_file_snapshot
    added = False

    def add_after_inventory(  # type: ignore[no-untyped-def]
        directory_fd: int, path: str, *, limit: int, code: str
    ):
        nonlocal added
        snapshot = original(directory_fd, path, limit=limit, code=code)
        if not added:
            added = True
            (package / "late.py").write_bytes(b"LATE")
        return snapshot

    monkeypatch.setattr(provenance, "read_regular_file_snapshot", add_after_inventory)
    with pytest.raises(ProvenanceError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "unstable_runner_inventory"


def test_runner_source_rejects_persistent_directory_replacement_with_same_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    package = tmp_path / "laconian_eval"
    nested = package / "nested"
    nested.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"")
    (nested / "payload.py").write_bytes(b"SAME")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "payload.py").write_bytes(b"SAME")
    parked = package / "original"
    original = provenance._scan_runner_members
    inventories = 0

    def replace_after_inventory(directory_fd: int):  # type: ignore[no-untyped-def]
        nonlocal inventories
        inventory = original(directory_fd)
        inventories += 1
        if inventories == 1:
            nested.rename(parked)
            replacement.rename(nested)
        return inventory

    monkeypatch.setattr(provenance, "_scan_runner_members", replace_after_inventory)
    with pytest.raises(ProvenanceError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "unstable_runner_inventory"


def test_runner_source_enforces_per_file_aggregate_and_authored_input_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    package = tmp_path / "laconian_eval"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"12345")
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(
            RESOURCE_LIMITS_V1,
            runner_source_file_bytes=4,
            all_runner_source_files_bytes=8,
            captured_input_total_bytes=8,
        ),
    )
    with pytest.raises(ResourceLimitError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "runner_source_file_limit"

    (package / "__init__.py").write_bytes(b"1234")
    with pytest.raises(ResourceLimitError) as caught:
        capture_runner_source(package_root=package, authored_input_bytes=5)
    assert caught.value.code == "captured_input_total_limit"

    (package / "other.py").write_bytes(b"1234")
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(
            RESOURCE_LIMITS_V1,
            runner_source_file_bytes=4,
            all_runner_source_files_bytes=7,
            captured_input_total_bytes=20,
        ),
    )
    with pytest.raises(ResourceLimitError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "all_runner_source_files_limit"


def test_runner_source_member_limit_is_global_across_recursive_siblings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    package = tmp_path / "laconian_eval"
    (package / "a/a").mkdir(parents=True)
    for path in ("a/a/z.py", "a/z.py", "y.py", "z.py"):
        (package / path).write_bytes(b"")
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_files=3),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_runner_source(package_root=package)
    assert caught.value.code == "runner_member_count_limit"


def test_offline_dependency_closure_is_exact_and_binds_every_retained_file(
    offline_provenance: Any,
) -> None:
    assert tuple(item.record.distribution for item in offline_provenance.dependencies) == (
        _OFFLINE_CLOSURE
    )
    for inventory in offline_provenance.dependencies:
        members = [
            {
                "path": item.path,
                "byte_length": item.byte_length,
                "sha256": item.sha256,
            }
            for item in inventory.files
        ]
        assert members == sorted(members, key=lambda item: item["path"].encode("utf-8"))
        assert inventory.record.files_sha256 == stable_digest(
            "laconian-distribution-files-v1",
            {"distribution": inventory.record.distribution, "files": members},
        )
        assert not any(
            item.path.endswith(("/RECORD", "/INSTALLER", "/REQUESTED", "/direct_url.json"))
            or item.path.endswith(".pyc")
            or "/__pycache__/" in f"/{item.path}/"
            for item in inventory.files
        )
        for item in inventory.files:
            assert item._origin == inventory._site_packages_root / item.path
            assert item._origin.is_absolute()
            assert item._identity.size == item.byte_length
            assert stat.S_ISREG(item._identity.mode)


def test_openai_closure_matches_lock_and_excludes_verified_external_scripts() -> None:
    closure = capture_dependency_closure(provider_kind="openai")
    assert tuple(item.record.distribution for item in closure) == _OPENAI_CLOSURE
    assert {item.record.distribution: item.record.version for item in closure} == {
        "annotated-types": "0.8.0",
        "anyio": "4.14.2",
        "h11": "0.16.0",
        "httpcore2": "2.12.0",
        "httpx2": "2.12.0",
        "idna": "3.19",
        "jiter": "0.16.0",
        "openai": "3.3.1",
        "packaging": "26.3",
        "pydantic": "2.13.4",
        "pydantic-core": "2.46.4",
        "pyyaml": "6.0.3",
        "sniffio": "1.3.1",
        "truststore": "0.10.4",
        "typing-extensions": "4.16.0",
        "typing-inspection": "0.4.4",
    }
    assert all("../../../bin/" not in member.path for item in closure for member in item.files)
    assert {item.record.distribution for item in closure} >= {
        "openai",
        "httpx2",
        "idna",
        "pydantic-core",
        "pyyaml",
        "packaging",
    }


def test_distribution_inventory_retains_metadata_wheel_licenses_and_native_members(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "native-demo")
    native = site / "native_demo/native.so"
    native.write_bytes(b"native")
    license_file = site / "native_demo-1.0.dist-info/licenses/LICENSE"
    license_file.parent.mkdir()
    license_file.write_text("license", encoding="utf-8")
    record = site / "native_demo-1.0.dist-info/RECORD"
    record.write_text(
        record.read_text(encoding="utf-8")
        + "native_demo/native.so,,\n"
        + "native_demo-1.0.dist-info/licenses/LICENSE,,\n",
        encoding="utf-8",
    )
    dist = next(metadata.distributions(path=[os.fspath(site)]))
    inventory = capture_distribution_inventory(dist, expected_name="native-demo")
    paths = {item.path for item in inventory.files}
    assert {
        "native_demo/__init__.py",
        "native_demo/native.so",
        "native_demo-1.0.dist-info/METADATA",
        "native_demo-1.0.dist-info/WHEEL",
        "native_demo-1.0.dist-info/licenses/LICENSE",
    } <= paths


def test_live_distribution_inventory_selects_exact_name_in_shared_site_packages() -> None:
    inventory = capture_distribution_inventory(
        metadata.distribution("pydantic"), expected_name="pydantic"
    )
    assert inventory.record.distribution == "pydantic"
    assert inventory.record.version == "2.13.4"


def test_distribution_metadata_and_record_are_each_read_once_and_feed_the_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "single-source")
    calls: list[str] = []
    original = provenance.read_regular_file_snapshot

    def counted(directory_fd: int, path: str, *, limit: int, code: str) -> Any:
        calls.append(path)
        return original(directory_fd, path, limit=limit, code=code)

    monkeypatch.setattr(provenance, "read_regular_file_snapshot", counted)
    inventory = capture_distribution_inventory(dist, expected_name="single-source")
    metadata_path = "single_source-1.0.dist-info/METADATA"
    record_path = "single_source-1.0.dist-info/RECORD"
    assert calls.count(metadata_path) == 1
    assert calls.count(record_path) == 1
    metadata_member = next(item for item in inventory.files if item.path == metadata_path)
    assert metadata_member.data is inventory.metadata_bytes
    assert metadata_member.sha256 == sha256_bytes(inventory.metadata_bytes)
    assert inventory.record.version == "1.0"


@pytest.mark.parametrize(
    ("field", "duplicate_value"),
    (("Name", "foreign-name"), ("Version", "999")),
)
def test_distribution_metadata_rejects_duplicate_identity_headers(
    tmp_path: Path,
    field: str,
    duplicate_value: str,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "duplicate-core")
    metadata_path = site / "duplicate_core-1.0.dist-info/METADATA"
    original = metadata_path.read_text(encoding="utf-8")
    metadata_path.write_text(
        original.replace("\n\n", f"\n{field}: {duplicate_value}\n\n", 1),
        encoding="utf-8",
    )

    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="duplicate-core")
    assert caught.value.code == "invalid_distribution_metadata"


def test_distribution_hash_has_known_exact_member_vector(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "known-vector")
    inventory = capture_distribution_inventory(dist, expected_name="known-vector")
    expected_members = []
    for path in (
        "known_vector-1.0.dist-info/METADATA",
        "known_vector-1.0.dist-info/WHEEL",
        "known_vector/__init__.py",
    ):
        data = (site / path).read_bytes()
        expected_members.append(
            {"path": path, "byte_length": len(data), "sha256": sha256_bytes(data)}
        )
    assert [
        {"path": item.path, "byte_length": item.byte_length, "sha256": item.sha256}
        for item in inventory.files
    ] == expected_members
    assert inventory.record.files_sha256 == stable_digest(
        "laconian-distribution-files-v1",
        {"distribution": "known-vector", "files": expected_members},
    )


def test_distribution_inventory_enforces_aggregate_retained_byte_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "aggregate-limit",
        extra_record_rows=(
            "aggregate_limit/first.bin,,",
            "aggregate_limit/second.bin,,",
        ),
    )
    (site / "aggregate_limit/first.bin").write_bytes(b"a" * 800)
    (site / "aggregate_limit/second.bin").write_bytes(b"b" * 800)
    base_bytes = sum(
        (site / path).stat().st_size
        for path in (
            "aggregate_limit-1.0.dist-info/METADATA",
            "aggregate_limit-1.0.dist-info/RECORD",
            "aggregate_limit-1.0.dist-info/WHEEL",
            "aggregate_limit/__init__.py",
        )
    )
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(
            RESOURCE_LIMITS_V1,
            dependency_file_bytes=900,
            all_dependency_files_bytes=base_bytes + 1_000,
        ),
    )
    reads: list[str] = []
    original = provenance.read_regular_file_snapshot

    def track_reads(directory_fd: int, path: str, *, limit: int, code: str) -> Any:
        reads.append(path)
        return original(directory_fd, path, limit=limit, code=code)

    monkeypatch.setattr(provenance, "read_regular_file_snapshot", track_reads)

    with pytest.raises(ResourceLimitError) as caught:
        capture_distribution_inventory(dist, expected_name="aggregate-limit")
    assert caught.value.code == "distribution_bytes_limit"
    assert "aggregate_limit/first.bin" in reads
    assert "aggregate_limit/second.bin" in reads


def test_distribution_record_rows_are_counted_incrementally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "record-count")
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_files=5),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_distribution_inventory(dist, expected_name="record-count")
    assert caught.value.code == "distribution_member_count_limit"


def test_unlisted_direct_url_is_charged_to_distribution_member_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "unlisted-member",
        direct_url={"url": "https://example.test/member.whl"},
        list_direct_url=False,
    )
    record_rows = len(
        (site / "unlisted_member-1.0.dist-info/RECORD").read_text(encoding="utf-8").splitlines()
    )
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_files=record_rows),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_distribution_inventory(dist, expected_name="unlisted-member")
    assert caught.value.code == "distribution_member_count_limit"


def test_closure_charges_unlisted_direct_urls_to_one_member_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    root = _make_distribution(
        site,
        "unlisted-member-root",
        requires=("unlisted-member-leaf",),
        direct_url={"url": "https://example.test/root.whl"},
        list_direct_url=False,
    )
    leaf = _make_distribution(
        site,
        "unlisted-member-leaf",
        direct_url={"url": "https://example.test/leaf.whl"},
        list_direct_url=False,
    )
    record_rows = sum(
        len((site / path).read_text(encoding="utf-8").splitlines())
        for path in (
            "unlisted_member_root-1.0.dist-info/RECORD",
            "unlisted_member_leaf-1.0.dist-info/RECORD",
        )
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((root, leaf)))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_files=record_rows + 2),
    )
    closure = capture_dependency_closure(root_distributions=("unlisted-member-root",))
    assert {item.record.distribution for item in closure} == {
        "unlisted-member-leaf",
        "unlisted-member-root",
    }

    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_files=record_rows + 1),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("unlisted-member-root",))
    assert caught.value.code == "distribution_member_count_limit"


def test_dependency_single_file_and_distribution_count_limits_are_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    oversized = _make_distribution(
        site,
        "large-member",
        extra_record_rows=("large_member/payload.bin,,",),
    )
    (site / "large_member/payload.bin").write_bytes(b"x" * 500)
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_file_bytes=300),
    )
    with pytest.raises(ResourceLimitError) as caught:
        capture_distribution_inventory(oversized, expected_name="large-member")
    assert caught.value.code == "distribution_bytes_limit"

    root = _make_distribution(site, "distribution-root", requires=("leaf",))
    leaf = _make_distribution(site, "leaf")
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((root, leaf)))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_distributions=1),
    )
    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("distribution-root",))
    assert caught.value.code == "distribution_candidate_count_limit"


def test_dependency_closure_enforces_one_aggregate_evidence_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    root = _make_distribution(
        site,
        "budget-root",
        requires=("budget-leaf",),
        extra_record_rows=("budget_root/payload.bin,,",),
    )
    leaf = _make_distribution(
        site,
        "budget-leaf",
        extra_record_rows=("budget_leaf/payload.bin,,",),
    )
    (site / "budget_root/payload.bin").write_bytes(b"r" * 400)
    (site / "budget_leaf/payload.bin").write_bytes(b"l" * 400)

    def distribution_cost(stem: str, package: str) -> int:
        return sum(
            (site / path).stat().st_size
            for path in (
                f"{stem}-1.0.dist-info/METADATA",
                f"{stem}-1.0.dist-info/RECORD",
                f"{stem}-1.0.dist-info/WHEEL",
                f"{package}/__init__.py",
                f"{package}/payload.bin",
            )
        )

    aggregate_limit = (
        max(
            distribution_cost("budget_root", "budget_root"),
            distribution_cost("budget_leaf", "budget_leaf"),
        )
        + 100
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((root, leaf)))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(
            RESOURCE_LIMITS_V1,
            dependency_file_bytes=1_000,
            all_dependency_files_bytes=aggregate_limit,
        ),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("budget-root",))
    assert caught.value.code == "distribution_bytes_limit"


def test_dependency_closure_counts_listed_and_unlisted_direct_url_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    root = _make_distribution(
        site,
        "url-budget-root",
        requires=("url-budget-leaf",),
        direct_url={"url": "https://example.test/root.whl", "padding": "r" * 400},
    )
    leaf = _make_distribution(
        site,
        "url-budget-leaf",
        direct_url={"url": "https://example.test/leaf.whl", "padding": "l" * 400},
        list_direct_url=False,
    )

    def captured_cost(stem: str, package: str) -> tuple[int, int]:
        direct_url_size = (site / f"{stem}-1.0.dist-info/direct_url.json").stat().st_size
        total = direct_url_size + sum(
            (site / path).stat().st_size
            for path in (
                f"{stem}-1.0.dist-info/METADATA",
                f"{stem}-1.0.dist-info/RECORD",
                f"{stem}-1.0.dist-info/WHEEL",
                f"{package}/__init__.py",
            )
        )
        return total, direct_url_size

    root_cost, root_url_size = captured_cost("url_budget_root", "url_budget_root")
    leaf_cost, leaf_url_size = captured_cost("url_budget_leaf", "url_budget_leaf")
    without_urls = root_cost + leaf_cost - root_url_size - leaf_url_size
    aggregate_limit = without_urls + max(root_url_size, leaf_url_size) + 1
    assert max(root_cost, leaf_cost) < aggregate_limit < root_cost + leaf_cost
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((root, leaf)))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(
            RESOURCE_LIMITS_V1,
            dependency_file_bytes=1_000,
            all_dependency_files_bytes=aggregate_limit,
        ),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("url-budget-root",))
    assert caught.value.code == "distribution_bytes_limit"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "distribution_member_read_failed"),
        ("symlink", "distribution_member_read_failed"),
        ("directory", "distribution_member_read_failed"),
    ],
)
def test_distribution_rejects_missing_symlink_and_nonregular_record_members(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "member-shape",
        extra_record_rows=("member_shape/payload.py,,",),
    )
    target = site / "member_shape/payload.py"
    if mutation == "symlink":
        target.symlink_to(site / "member_shape/__init__.py")
    elif mutation == "directory":
        target.mkdir()
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="member-shape")
    assert caught.value.code == expected_code


def test_distribution_rejects_symlinked_intermediate_directory(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "intermediate-shape",
        extra_record_rows=("linked/payload.py,,",),
    )
    (site / "real").mkdir()
    (site / "real/payload.py").write_bytes(b"payload")
    (site / "linked").symlink_to(site / "real", target_is_directory=True)
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="intermediate-shape")
    assert caught.value.code == "distribution_member_read_failed"


def test_distribution_rejects_duplicate_normalized_record_paths(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "duplicate-member",
        extra_record_rows=("duplicate_member/../duplicate_member/__init__.py,,",),
    )
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="duplicate-member")
    assert caught.value.code == "duplicate_distribution_member"


def test_record_and_metadata_mutation_between_snapshot_and_use_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "mutating-metadata")
    original_snapshot = provenance._snapshot_candidates_in_root

    def mutate_after_snapshot(root: Path, *, expected_name: str | None):  # type: ignore[no-untyped-def]
        candidates = original_snapshot(root, expected_name=expected_name)
        (site / "mutating_metadata-1.0.dist-info/METADATA").write_bytes(
            candidates[0].metadata_bytes + b"X-Mutated: true\n"
        )
        return candidates

    monkeypatch.setattr(provenance, "_snapshot_candidates_in_root", mutate_after_snapshot)
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="mutating-metadata")
    assert caught.value.code == "unstable_file_snapshot"


def test_distribution_rejects_record_mutation_after_initial_identity_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "late-record")
    record = site / "late_record-1.0.dist-info/RECORD"
    original = provenance.read_regular_file_snapshot
    mutated = False

    def mutate_during_member_read(  # type: ignore[no-untyped-def]
        directory_fd: int, path: str, *, limit: int, code: str
    ):
        nonlocal mutated
        snapshot = original(directory_fd, path, limit=limit, code=code)
        if path.endswith("/WHEEL") and not mutated:
            mutated = True
            record.write_bytes(record.read_bytes() + b"late_record/late.py,,\n")
        return snapshot

    monkeypatch.setattr(provenance, "read_regular_file_snapshot", mutate_during_member_read)
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="late-record")
    assert caught.value.code == "unstable_file_snapshot"


def test_distribution_rejects_dist_info_replaced_by_intermediate_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "metadata-link")
    dist_info = site / "metadata_link-1.0.dist-info"
    (dist_info / "RECORD").write_text(
        "metadata_link-1.0.dist-info/METADATA,,\nmetadata_link-1.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    original_snapshot = provenance._snapshot_candidates_in_root

    def replace_after_snapshot(root: Path, *, expected_name: str | None):  # type: ignore[no-untyped-def]
        candidates = original_snapshot(root, expected_name=expected_name)
        parked = site / "parked-metadata"
        dist_info.rename(parked)
        dist_info.symlink_to(parked, target_is_directory=True)
        return candidates

    monkeypatch.setattr(provenance, "_snapshot_candidates_in_root", replace_after_snapshot)
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="metadata-link")
    assert caught.value.code == "unstable_file_snapshot"


def test_payload_files_named_like_volatile_metadata_are_retained(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "volatile-payload",
        extra_record_rows=(
            "volatile_payload/INSTALLER,,",
            "volatile_payload/RECORD,,",
            "volatile_payload/direct_url.json,,",
        ),
    )
    for name in ("INSTALLER", "RECORD", "direct_url.json"):
        (site / f"volatile_payload/{name}").write_bytes(name.encode("ascii"))
    inventory = capture_distribution_inventory(dist, expected_name="volatile-payload")
    assert {
        "volatile_payload/INSTALLER",
        "volatile_payload/RECORD",
        "volatile_payload/direct_url.json",
    } <= {item.path for item in inventory.files}


@pytest.mark.parametrize("name", ["record", "installer", "requested", "DIRECT_URL.JSON"])
def test_volatile_metadata_exclusions_are_exact_case(name: str) -> None:
    from laconian_eval.capsule import provenance

    assert not provenance._is_volatile_metadata(
        f"exact_case-1.0.dist-info/{name}",
        dist_info="exact_case-1.0.dist-info",
    )


def test_nested_dist_info_payload_cannot_authorize_external_console_script(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "nested-auth",
        extra_record_rows=(
            "nested_auth/fake.dist-info/entry_points.txt,,",
            "../../../bin/evil,,",
        ),
    )
    fake = site / "nested_auth/fake.dist-info/entry_points.txt"
    fake.parent.mkdir()
    fake.write_text("[console_scripts]\nevil = nested_auth:main\n", encoding="utf-8")

    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="nested-auth")
    assert caught.value.code == "distribution_member_escape"


def test_nested_dist_info_direct_url_cannot_mask_real_local_origin(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "masked-local",
        direct_url={"url": "file:///private/real-origin", "dir_info": {"editable": False}},
        extra_record_rows=("masked_local/fake.dist-info/direct_url.json,,",),
    )
    fake = site / "masked_local/fake.dist-info/direct_url.json"
    fake.parent.mkdir()
    fake.write_text(
        json.dumps({"url": "https://packages.example.test/masked.whl"}),
        encoding="utf-8",
    )

    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="masked-local")
    assert caught.value.code == "local_dependency"
    assert "real-origin" not in str(caught.value)


def test_nested_dist_info_volatile_lookalike_is_retained_as_payload(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "nested-payload",
        extra_record_rows=("nested_payload/fake.dist-info/direct_url.json,,",),
    )
    fake = site / "nested_payload/fake.dist-info/direct_url.json"
    fake.parent.mkdir()
    fake.write_bytes(b"opaque payload")

    inventory = capture_distribution_inventory(dist, expected_name="nested-payload")
    member = next(
        item
        for item in inventory.files
        if item.path == "nested_payload/fake.dist-info/direct_url.json"
    )
    assert member.data == b"opaque payload"


@pytest.mark.parametrize(
    ("direct_url", "code"),
    [
        ({"url": "file:///private/local", "dir_info": {}}, "local_dependency"),
        ({"url": "git+file:///private/local", "vcs_info": {"vcs": "git"}}, "local_dependency"),
        (
            {"url": "https://example.test/pkg.whl", "dir_info": {"editable": True}},
            "editable_dependency",
        ),
        (
            {"url": "https://example.test/pkg.whl", "dir_info": {"editable": "yes"}},
            "invalid_dependency_direct_url",
        ),
    ],
)
def test_distribution_inventory_rejects_local_or_editable_direct_urls(
    tmp_path: Path, direct_url: dict[str, object], code: str
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "unsafe-demo", direct_url=direct_url)
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="unsafe-demo")
    assert caught.value.code == code
    assert "/private/local" not in str(caught.value)


def test_unlisted_local_direct_url_is_rejected_and_remote_noneditable_is_allowed(
    tmp_path: Path,
) -> None:
    local_site = tmp_path / "local/site-packages"
    local = _make_distribution(
        local_site,
        "unlisted-local",
        direct_url={"url": "file:///private/hidden", "dir_info": {"editable": False}},
        list_direct_url=False,
    )
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(local, expected_name="unlisted-local")
    assert caught.value.code == "local_dependency"
    assert "/private/hidden" not in str(caught.value)

    remote_site = tmp_path / "remote/site-packages"
    remote = _make_distribution(
        remote_site,
        "remote-wheel",
        direct_url={
            "url": "https://packages.example.test/remote.whl",
            "archive_info": {"hash": "sha256=" + "a" * 64},
        },
    )
    assert (
        capture_distribution_inventory(remote, expected_name="remote-wheel").record.distribution
        == "remote-wheel"
    )


def test_negative_unlisted_direct_url_observation_is_stabilized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "late-direct-url")
    original = provenance._optional_unlisted_direct_url

    def create_after_negative(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if result is None:
            (site / "late_direct_url-1.0.dist-info/direct_url.json").write_text(
                json.dumps(
                    {
                        "url": "file:///private/late-origin",
                        "dir_info": {"editable": False},
                    }
                ),
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(provenance, "_optional_unlisted_direct_url", create_after_negative)
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="late-direct-url")
    assert caught.value.code == "unstable_file_snapshot"


def test_malformed_unlisted_direct_url_is_rejected(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "malformed-unlisted")
    (site / "malformed_unlisted-1.0.dist-info/direct_url.json").write_bytes(b"not-json")
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="malformed-unlisted")
    assert caught.value.code == "invalid_dependency_direct_url"


def test_dependency_direct_url_rejects_json_nesting_before_semantic_use(
    tmp_path: Path,
) -> None:
    nested: object = "leaf"
    for _ in range(65):
        nested = {"nested": nested}
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "deep-direct-url",
        direct_url={
            "url": "https://packages.example.test/deep.whl",
            "archive_info": nested,
        },
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_distribution_inventory(dist, expected_name="deep-direct-url")
    assert caught.value.code == "nesting_depth_limit"


@pytest.mark.parametrize(
    "raw_json",
    [
        b'{"url":"file:///private/local","url":"https://example.test/pkg.whl"}',
        b'{"url":"https://example.test/pkg.whl","archive_info":{"size":NaN}}',
    ],
)
def test_dependency_direct_url_requires_strict_unique_finite_json(
    tmp_path: Path,
    raw_json: bytes,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "strict-direct-url",
        direct_url={"url": "https://example.test/pkg.whl"},
    )
    (site / "strict_direct_url-1.0.dist-info/direct_url.json").write_bytes(raw_json)

    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="strict-direct-url")
    assert caught.value.code == "invalid_dependency_direct_url"
    assert "private/local" not in str(caught.value)


def test_distribution_inventory_rejects_unverified_escape(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(
        site,
        "escape-demo",
        extra_record_rows=("../../../private/secret,,",),
    )
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="escape-demo")
    assert caught.value.code == "distribution_member_escape"


def test_distribution_inventory_accepts_only_its_declared_external_console_script(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "console-demo", external_script="console-demo")
    expected_scripts = _scripts_root_for_site(site)
    inventory = capture_distribution_inventory(
        dist,
        expected_name="console-demo",
        scripts_root=expected_scripts,
    )
    assert not any(item.path == "console-demo" for item in inventory.files)
    record = site / "console_demo-1.0.dist-info/RECORD"
    record.write_text(
        record.read_text(encoding="utf-8") + "../../../bin/not-declared,,\n",
        encoding="utf-8",
    )
    dist = next(metadata.distributions(path=[os.fspath(site)]))
    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(
            dist,
            expected_name="console-demo",
            scripts_root=expected_scripts,
        )
    assert caught.value.code == "distribution_member_escape"


def test_entry_point_defaults_cannot_authorize_external_console_script(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "default-authority", external_script="evil")
    (site / "default_authority-1.0.dist-info/entry_points.txt").write_text(
        "[DEFAULT]\nevil = attacker.module:main\n[console_scripts]\n",
        encoding="utf-8",
    )

    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(
            dist,
            expected_name="default-authority",
            scripts_root=_scripts_root_for_site(site),
        )
    assert caught.value.code == "invalid_distribution_entry_points"


def test_dependency_distribution_rejects_duplicate_external_record_member(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "duplicate-external", external_script="evil")
    record = site / "duplicate_external-1.0.dist-info/RECORD"
    record.write_text(
        record.read_text(encoding="utf-8") + "../../../bin/evil,,\n",
        encoding="utf-8",
    )

    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(
            dist,
            expected_name="duplicate-external",
            scripts_root=_scripts_root_for_site(site),
        )
    assert caught.value.code == "duplicate_distribution_member"


def test_external_console_script_requires_verified_installation_scripts_root(
    tmp_path: Path,
) -> None:
    site = tmp_path / "arbitrary/site-packages"
    dist = _make_distribution(site, "wrong-scheme", external_script="wrong-scheme")

    with pytest.raises(ProvenanceError) as caught:
        capture_distribution_inventory(dist, expected_name="wrong-scheme")
    assert caught.value.code == "distribution_member_escape"


@pytest.mark.parametrize(
    ("available", "roots", "code"),
    [
        ((), ("missing",), "missing_dependency"),
        (("duplicate", "duplicate"), ("duplicate",), "duplicate_dependency"),
    ],
)
def test_dependency_closure_rejects_missing_and_duplicate_distributions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    available: tuple[str, ...],
    roots: tuple[str, ...],
    code: str,
) -> None:
    distributions = tuple(
        _make_distribution(tmp_path / f"site-{index}", name) for index, name in enumerate(available)
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))
    with pytest.raises(ProvenanceError) as caught:
        capture_dependency_closure(root_distributions=roots)
    assert caught.value.code == code


def test_dependency_closure_evaluates_markers_and_rejects_unsatisfied_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = tmp_path / "site-packages"
    root = _make_distribution(
        site,
        "root-demo",
        requires=(
            "needed>=2",
            "ignored; python_version < '2'",
        ),
    )
    needed = _make_distribution(site, "needed", version="1")
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((root, needed)))
    with pytest.raises(ProvenanceError) as caught:
        capture_dependency_closure(root_distributions=("root-demo",))
    assert caught.value.code == "unsatisfied_dependency"


def test_dependency_closure_merges_and_propagates_requested_extras(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = tmp_path / "site-packages"
    distributions = (
        _make_distribution(
            site,
            "extra-root",
            requires=("middle[feature]", "middle[second]"),
        ),
        _make_distribution(
            site,
            "middle",
            requires=(
                "feature-leaf; extra == 'feature'",
                "second-leaf; extra == 'second'",
                "nested[deep]; extra == 'feature'",
            ),
        ),
        _make_distribution(site, "feature-leaf"),
        _make_distribution(site, "second-leaf"),
        _make_distribution(
            site,
            "nested",
            requires=("deep-leaf; extra == 'deep'",),
        ),
        _make_distribution(site, "deep-leaf"),
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))

    closure = capture_dependency_closure(root_distributions=("extra-root",))
    assert {item.record.distribution for item in closure} == {
        "deep-leaf",
        "extra-root",
        "feature-leaf",
        "middle",
        "nested",
        "second-leaf",
    }


def test_dependency_marker_context_allocation_and_evaluation_are_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    distributions = (
        _make_distribution(
            site,
            "context-root",
            requires=("middle[one,two,three]",),
        ),
        _make_distribution(
            site,
            "middle",
            requires=("leaf; extra == 'one'",),
        ),
        _make_distribution(site, "leaf"),
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_marker_contexts=2),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("context-root",))
    assert caught.value.code == "distribution_marker_context_limit"


def test_dependency_marker_evaluation_work_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    distributions = (
        _make_distribution(site, "marker-work-root", requires=("middle[one,two,three]",)),
        _make_distribution(
            site,
            "middle",
            requires=(
                "first-never; extra == 'absent'",
                "second-never; extra == 'absent'",
            ),
        ),
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(
            RESOURCE_LIMITS_V1,
            dependency_marker_contexts=10,
            dependency_requirement_evaluations=4,
        ),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("marker-work-root",))
    assert caught.value.code == "distribution_requirement_evaluation_limit"


def test_dependency_unmarked_requirement_reprocessing_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    distributions = (
        _make_distribution(site, "wave-root", requires=("middle[first]",)),
        _make_distribution(site, "middle", requires=("bridge", "leaf")),
        _make_distribution(site, "bridge", requires=("middle[second]",)),
        _make_distribution(site, "leaf"),
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_requirement_evaluations=4),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("wave-root",))
    assert caught.value.code == "distribution_requirement_evaluation_limit"


def test_dependency_requirement_count_is_bounded_before_queue_growth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    distributions = (
        _make_distribution(site, "many-requirements", requires=("leaf",) * 100),
        _make_distribution(site, "leaf"),
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_requirements=20),
    )

    with pytest.raises(ResourceLimitError) as caught:
        capture_dependency_closure(root_distributions=("many-requirements",))
    assert caught.value.code == "distribution_requirement_count_limit"


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_distribution_requirement_preflight_ignores_metadata_body_lookalikes(
    tmp_path: Path,
    newline: bytes,
) -> None:
    site = tmp_path / "site-packages"
    dist = _make_distribution(site, "metadata-body")
    metadata_file = site / "metadata_body-1.0.dist-info/METADATA"
    metadata_file.write_bytes(
        newline.join(
            (
                b"Metadata-Version: 2.4",
                b"Name: metadata-body",
                b"Version: 1.0",
                b"",
                b"Requires-Dist: body-only",
                b"",
            )
        )
    )
    record = site / "metadata_body-1.0.dist-info/RECORD"
    record.write_bytes(record.read_bytes())

    inventory = capture_distribution_inventory(dist, expected_name="metadata-body")
    assert inventory.record.distribution == "metadata-body"


def test_dependency_queue_contains_each_pending_name_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    distributions = (
        _make_distribution(site, "duplicate-edges", requires=("leaf",) * 10),
        _make_distribution(site, "leaf"),
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))
    peak_pending = 0

    class TrackingDeque(deque[str]):
        def append(self, item: str) -> None:
            nonlocal peak_pending
            super().append(item)
            peak_pending = max(peak_pending, len(self))

    monkeypatch.setattr(provenance, "deque", TrackingDeque)
    closure = capture_dependency_closure(root_distributions=("duplicate-edges",))
    assert {item.record.distribution for item in closure} == {"duplicate-edges", "leaf"}
    assert peak_pending == 1


@pytest.mark.parametrize(
    ("versions", "code"),
    [
        ((), "runner_distribution_missing"),
        ((__version__, __version__), "runner_distribution_duplicate"),
        (("99.0",), "runner_version_mismatch"),
    ],
)
def test_runner_distribution_rejects_missing_duplicate_and_version_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    versions: tuple[str, ...],
    code: str,
) -> None:
    from laconian_eval.capsule import provenance

    distributions = tuple(
        _make_distribution(
            tmp_path / f"site-{index}",
            "laconian-eval",
            version=version,
            external_script="laconian",
        )
        for index, version in enumerate(versions)
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter(distributions))
    scripts_root = (
        _scripts_root_for_site(Path(str(distributions[0].locate_file(""))))
        if distributions
        else tmp_path / "unused-bin"
    )
    with pytest.raises(ProvenanceError) as caught:
        provenance._capture_runner_distribution(scripts_root=scripts_root)
    assert caught.value.code == code


def test_runner_distribution_accepts_wheel_and_private_editable_path_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    wheel = _make_distribution(
        tmp_path / "wheel/site-packages",
        "laconian-eval",
        version=__version__,
        external_script="laconian",
    )
    editable = _make_distribution(
        tmp_path / "editable/site-packages",
        "laconian-eval",
        version=__version__,
        external_script="laconian",
        direct_url={
            "url": "file:///private/editable-runner",
            "dir_info": {"editable": True},
        },
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((wheel,)))
    assert (
        provenance._capture_runner_distribution(
            scripts_root=_scripts_root_for_site(tmp_path / "wheel/site-packages")
        ).direct_url_bytes
        is None
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((editable,)))
    captured = provenance._capture_runner_distribution(
        scripts_root=_scripts_root_for_site(tmp_path / "editable/site-packages")
    )
    assert (
        captured.direct_url_bytes
        == (
            tmp_path / "editable/site-packages/laconian_eval-0.1.0a1.dist-info/direct_url.json"
        ).read_bytes()
    )


def test_runner_distribution_rejects_duplicate_external_record_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    runner_dist = _make_distribution(
        site,
        "laconian-eval",
        version=__version__,
        external_script="laconian",
    )
    record = site / f"laconian_eval-{__version__}.dist-info/RECORD"
    record.write_text(
        record.read_text(encoding="utf-8") + "../../../bin/laconian,,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((runner_dist,)))

    with pytest.raises(ProvenanceError) as caught:
        provenance._capture_runner_distribution(scripts_root=_scripts_root_for_site(site))
    assert caught.value.code == "runner_distribution_duplicate_member"


def test_runner_unlisted_direct_url_is_charged_to_member_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    runner_dist = _make_distribution(
        site,
        "laconian-eval",
        version=__version__,
        external_script="laconian",
        direct_url={"url": "file:///private/editable", "dir_info": {"editable": True}},
        list_direct_url=False,
    )
    record_rows = len(
        (site / f"laconian_eval-{__version__}.dist-info/RECORD")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((runner_dist,)))
    monkeypatch.setattr(
        provenance,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, dependency_files=record_rows),
    )

    with pytest.raises(ResourceLimitError) as caught:
        provenance._capture_runner_distribution(scripts_root=_scripts_root_for_site(site))
    assert caught.value.code == "distribution_member_count_limit"


def test_runner_negative_unlisted_direct_url_observation_is_stabilized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    runner_dist = _make_distribution(
        site,
        "laconian-eval",
        version=__version__,
        external_script="laconian",
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((runner_dist,)))
    original = provenance._optional_unlisted_direct_url

    def create_after_negative(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if result is None:
            (site / f"laconian_eval-{__version__}.dist-info/direct_url.json").write_text(
                json.dumps(
                    {
                        "url": "file:///private/late-runner",
                        "dir_info": {"editable": True},
                    }
                ),
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(provenance, "_optional_unlisted_direct_url", create_after_negative)
    with pytest.raises(ProvenanceError) as caught:
        provenance._capture_runner_distribution(scripts_root=_scripts_root_for_site(site))
    assert caught.value.code == "unstable_file_snapshot"


def test_runner_distribution_treats_nested_dist_info_names_as_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    runner_dist = _make_distribution(
        site,
        "laconian-eval",
        version=__version__,
        external_script="laconian",
        extra_record_rows=(
            "laconian_eval/fake.dist-info/METADATA,,",
            "laconian_eval/fake.dist-info/entry_points.txt,,",
            "laconian_eval/fake.dist-info/direct_url.json,,",
        ),
    )
    fake_root = site / "laconian_eval/fake.dist-info"
    fake_root.mkdir()
    (fake_root / "METADATA").write_bytes(b"opaque metadata payload")
    (fake_root / "entry_points.txt").write_bytes(b"opaque entry-point payload")
    (fake_root / "direct_url.json").write_bytes(b"opaque direct-url payload")
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((runner_dist,)))

    captured = provenance._capture_runner_distribution(scripts_root=_scripts_root_for_site(site))
    assert captured.direct_url_bytes is None
    assert {
        "laconian_eval/fake.dist-info/METADATA",
        "laconian_eval/fake.dist-info/entry_points.txt",
        "laconian_eval/fake.dist-info/direct_url.json",
    } <= set(captured.in_root_files)


def test_runner_distribution_rejects_metadata_mutation_after_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    runner_dist = _make_distribution(
        tmp_path / "site-packages",
        "laconian-eval",
        version=__version__,
        external_script="laconian",
    )
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((runner_dist,)))
    original_discover = provenance._discover_distribution_candidates

    def mutate_after_discovery(name: str):  # type: ignore[no-untyped-def]
        candidates = original_discover(name)
        (tmp_path / "site-packages/laconian_eval-0.1.0a1.dist-info/METADATA").write_bytes(
            candidates[0].metadata_bytes + b"X-Mutated: true\n"
        )
        return candidates

    monkeypatch.setattr(provenance, "_discover_distribution_candidates", mutate_after_discovery)
    with pytest.raises(ProvenanceError) as caught:
        provenance._capture_runner_distribution(
            scripts_root=_scripts_root_for_site(tmp_path / "site-packages")
        )
    assert caught.value.code == "unstable_file_snapshot"


def test_runner_distribution_rejects_record_mutation_after_initial_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    site = tmp_path / "site-packages"
    runner_dist = _make_distribution(
        site,
        "laconian-eval",
        version=__version__,
        external_script="laconian",
    )
    record = site / "laconian_eval-0.1.0a1.dist-info/RECORD"
    monkeypatch.setattr(metadata, "distributions", lambda **_context: iter((runner_dist,)))
    original = provenance.read_regular_file_snapshot
    mutated = False

    def mutate_during_member_read(  # type: ignore[no-untyped-def]
        directory_fd: int, path: str, *, limit: int, code: str
    ):
        nonlocal mutated
        snapshot = original(directory_fd, path, limit=limit, code=code)
        if path.endswith("/WHEEL") and not mutated:
            mutated = True
            record.write_bytes(record.read_bytes() + b"laconian_eval/late.py,,\n")
        return snapshot

    monkeypatch.setattr(provenance, "read_regular_file_snapshot", mutate_during_member_read)
    with pytest.raises(ProvenanceError) as caught:
        provenance._capture_runner_distribution(scripts_root=_scripts_root_for_site(site))
    assert caught.value.code == "unstable_file_snapshot"


def test_adapter_digest_uses_only_provider_init_and_selected_adapter(
    offline_provenance: Any,
) -> None:
    members = tuple(
        item.model_dump(mode="json")
        for item in offline_provenance.runner_source.index.files
        if item.path in ("providers/__init__.py", "providers/fake.py")
    )
    assert offline_provenance.adapter_source_sha256 == stable_digest(
        "laconian-adapter-source-v1",
        {"provider_kind": "fake", "files": members},
    )
    assert len(members) == 2


def _copy_source_tree(destination: Path) -> None:
    shutil.copytree(ROOT / "src/laconian_eval", destination / "src/laconian_eval")
    shutil.copyfile(ROOT / "pyproject.toml", destination / "pyproject.toml")
    shutil.copyfile(ROOT / "uv.lock", destination / "uv.lock")


def test_checkout_binding_is_bound_without_git_when_source_bytes_match(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _copy_source_tree(source)
    provenance = capture_installed_provenance(
        _captured_inputs(), source_root=source, container_image_digest=None
    )
    assert provenance.checkout_binding == "bound"
    assert provenance.git_state == "unavailable"
    assert provenance.git_commit is None
    assert provenance.uv_lock.availability == "present"
    assert provenance.uv_lock.sha256 == sha256_bytes((source / "uv.lock").read_bytes())


def test_git_checkout_remains_bound_with_passive_git_attribution(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _copy_source_tree(source)
    subprocess.run(("git", "init", "-q"), cwd=source, check=True)
    subprocess.run(("git", "config", "user.name", "Fixture"), cwd=source, check=True)
    subprocess.run(("git", "config", "user.email", "fixture@example.test"), cwd=source, check=True)
    subprocess.run(("git", "add", "."), cwd=source, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=source, check=True)
    (source / "dirty.txt").write_text("dirty", encoding="utf-8")
    provenance = capture_installed_provenance(
        _captured_inputs(), source_root=source, container_image_digest=None
    )
    assert provenance.checkout_binding == "bound"
    assert provenance.git_state == "unavailable"
    assert provenance.git_commit is None


def test_git_attribution_never_queries_remote_or_diff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    def forbidden_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("passive Git attribution must not start a process")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    assert provenance._git_attribution(tmp_path) == ("unavailable", None)


def test_git_attribution_disables_repository_fsmonitor_hooks(tmp_path: Path) -> None:
    from laconian_eval.capsule import provenance

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
    subprocess.run(("git", "config", "user.name", "Fixture"), cwd=repository, check=True)
    subprocess.run(
        ("git", "config", "user.email", "fixture@example.test"),
        cwd=repository,
        check=True,
    )
    tracked = repository / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    subprocess.run(("git", "add", "tracked.txt"), cwd=repository, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=repository, check=True)

    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor-hook"
    hook.write_text(
        '#!/bin/sh\nhook_dir=${0%/*}\n: > "$hook_dir/fsmonitor-ran"\nexit 0\n',
        encoding="utf-8",
    )
    hook.chmod(0o700)
    subprocess.run(
        ("git", "config", "core.fsmonitor", os.fspath(hook)),
        cwd=repository,
        check=True,
    )

    assert provenance._git_attribution(repository) == ("unavailable", None)
    assert not marker.exists()


def test_git_attribution_does_not_refresh_or_write_the_index(tmp_path: Path) -> None:
    from laconian_eval.capsule import provenance

    subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    subprocess.run(("git", "config", "user.name", "Fixture"), cwd=tmp_path, check=True)
    subprocess.run(
        ("git", "config", "user.email", "fixture@example.test"), cwd=tmp_path, check=True
    )
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    subprocess.run(("git", "add", "tracked.txt"), cwd=tmp_path, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=tmp_path, check=True)
    index = tmp_path / ".git/index"
    before = index.read_bytes()
    current = tracked.stat()
    os.utime(
        tracked,
        ns=(current.st_atime_ns, current.st_mtime_ns + 2_000_000_000),
    )

    assert provenance._git_attribution(tmp_path) == ("unavailable", None)
    assert index.read_bytes() == before


def test_git_attribution_never_executes_repository_clean_filters(tmp_path: Path) -> None:
    from laconian_eval.capsule import provenance

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
    subprocess.run(("git", "config", "user.name", "Fixture"), cwd=repository, check=True)
    subprocess.run(
        ("git", "config", "user.email", "fixture@example.test"),
        cwd=repository,
        check=True,
    )
    tracked = repository / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    (repository / ".gitattributes").write_text("tracked.txt filter=evil\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=repository, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=repository, check=True)

    marker = tmp_path / "clean-filter-ran"
    hook = tmp_path / "clean-filter"
    hook.write_text(
        '#!/bin/sh\nhook_dir=${0%/*}\n: > "$hook_dir/clean-filter-ran"\ncat\n',
        encoding="utf-8",
    )
    hook.chmod(0o700)
    subprocess.run(
        ("git", "config", "filter.evil.clean", os.fspath(hook)),
        cwd=repository,
        check=True,
    )
    current = tracked.stat()
    os.utime(
        tracked,
        ns=(current.st_atime_ns, current.st_mtime_ns + 2_000_000_000),
    )

    provenance._git_attribution(repository)
    assert not marker.exists()


def test_unbound_and_unavailable_sources_carry_no_git_or_lock_attribution(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _copy_source_tree(source)
    target = source / "src/laconian_eval/__init__.py"
    target.write_bytes(target.read_bytes() + b"# drift\n")
    unbound = capture_installed_provenance(
        _captured_inputs(), source_root=source, container_image_digest=None
    )
    unavailable = capture_installed_provenance(
        _captured_inputs(), source_root=None, container_image_digest=None
    )
    for item, binding in ((unbound, "unbound"), (unavailable, "unavailable")):
        assert item.checkout_binding == binding
        assert item.git_state == "unavailable"
        assert item.git_commit is None
        assert item.uv_lock.availability == "unavailable"
        assert item.uv_lock.sha256 is None


def test_bound_checkout_allows_missing_lock_but_rejects_symlink_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    missing_root = tmp_path / "missing"
    _copy_source_tree(missing_root)
    (missing_root / "uv.lock").unlink()
    missing = capture_installed_provenance(
        _captured_inputs(), source_root=missing_root, container_image_digest=None
    )
    assert missing.checkout_binding == "bound"
    assert missing.uv_lock.availability == "unavailable"

    symlink_root = tmp_path / "symlink"
    _copy_source_tree(symlink_root)
    (symlink_root / "uv.lock").unlink()
    secret = tmp_path / "private-index-lock"
    secret.write_text("https://token@private.example/simple\n", encoding="utf-8")
    (symlink_root / "uv.lock").symlink_to(secret)
    with pytest.raises(ProvenanceError) as caught:
        capture_installed_provenance(
            _captured_inputs(), source_root=symlink_root, container_image_digest=None
        )
    assert caught.value.code == "unsafe_uv_lock"
    assert "private.example" not in str(caught.value)

    mutating_root = tmp_path / "mutating"
    _copy_source_tree(mutating_root)
    original = provenance.read_regular_file_snapshot

    def mutate_after_read(directory_fd: int, path: str, *, limit: int, code: str) -> Any:
        snapshot = original(directory_fd, path, limit=limit, code=code)
        if path == "uv.lock":
            (mutating_root / "uv.lock").write_bytes(snapshot.data + b"# changed\n")
        return snapshot

    monkeypatch.setattr(provenance, "read_regular_file_snapshot", mutate_after_read)
    with pytest.raises(ProvenanceError) as caught:
        capture_installed_provenance(
            _captured_inputs(), source_root=mutating_root, container_image_digest=None
        )
    assert caught.value.code == "unsafe_uv_lock"


def test_missing_uv_lock_observation_is_stabilized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    source = tmp_path / "late-lock"
    _copy_source_tree(source)
    (source / "uv.lock").unlink()
    original = provenance._stat_beneath_no_follow

    def create_after_negative(root_fd: int, path: str) -> os.stat_result:
        try:
            return original(root_fd, path)
        except FileNotFoundError:
            if path == "uv.lock":
                (source / "uv.lock").write_text(
                    'source = { registry = "https://private.example/simple" }\n',
                    encoding="utf-8",
                )
            raise

    monkeypatch.setattr(provenance, "_stat_beneath_no_follow", create_after_negative)
    with pytest.raises(ProvenanceError) as caught:
        capture_installed_provenance(
            _captured_inputs(), source_root=source, container_image_digest=None
        )
    assert caught.value.code == "unsafe_uv_lock"
    assert "private.example" not in str(caught.value)


def test_lock_private_urls_are_only_hashed_never_serialized(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _copy_source_tree(source)
    (source / "uv.lock").write_text(
        'source = { registry = "https://token@private.example/simple" }\n',
        encoding="utf-8",
    )
    provenance = capture_installed_provenance(
        _captured_inputs(), source_root=source, container_image_digest=None
    )
    environment = project_environment(
        provenance, import_environment=_import_environment(), filesystem_class="apfs"
    )
    serialized = canonical_json(environment.model_dump(mode="json"))
    assert b"private.example" not in serialized
    assert provenance.uv_lock.sha256 == sha256_bytes((source / "uv.lock").read_bytes())


def test_source_root_defaults_only_for_matching_project(tmp_path: Path) -> None:
    matching = tmp_path / "matching"
    matching.mkdir()
    (matching / "pyproject.toml").write_text(
        '[project]\nname = "laconian-eval"\n', encoding="utf-8"
    )
    other = tmp_path / "other"
    other.mkdir()
    (other / "pyproject.toml").write_text('[project]\nname = "other"\n', encoding="utf-8")
    assert resolve_source_root(None, invocation_cwd=matching) == matching
    assert resolve_source_root(None, invocation_cwd=other) is None
    explicit = resolve_source_root("../matching", invocation_cwd=other)
    assert explicit == matching


@pytest.mark.parametrize(
    "value",
    [
        "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha512:" + "a" * 64,
        " sha256:" + "a" * 64,
        "sha256:" + "a" * 64 + " ",
        "",
    ],
)
def test_container_digest_requires_exact_explicit_grammar(value: str) -> None:
    with pytest.raises(ProvenanceError) as caught:
        parse_container_image_digest(value)
    assert caught.value.code == "invalid_container_image_digest"


def test_container_digest_is_separate_bare_commitment(offline_provenance: Any) -> None:
    digest = "0123456789abcdef" * 4
    assert parse_container_image_digest(f"sha256:{digest}") == digest
    with_container = capture_installed_provenance(
        _captured_inputs(),
        source_root=ROOT,
        container_image_digest=f"sha256:{digest}",
    )
    assert with_container.container_image_digest == digest
    assert with_container.runner_source.index == offline_provenance.runner_source.index


def test_capture_rejects_package_and_manifest_version_disagreement() -> None:
    with pytest.raises(ProvenanceError) as caught:
        capture_installed_provenance(
            _captured_inputs(runner_version="99.0"),
            source_root=ROOT,
            container_image_digest=None,
        )
    assert caught.value.code == "runner_version_mismatch"


def test_capture_rejects_manifest_semantics_mismatching_captured_bytes() -> None:
    captured = _captured_inputs(requested_model="original-model")
    payload = captured.resolved_manifest.model_dump(mode="python")
    provider = payload["provider"]
    assert isinstance(provider, dict)
    provider["model"] = "forged-model"
    forged_manifest = ResolvedManifestV2.model_validate(payload)
    forged_capture = SimpleNamespace(
        resolved_manifest=forged_manifest,
        resolved_manifest_bytes=captured.resolved_manifest_bytes,
        manifest_sha256=captured.manifest_sha256,
        files=captured.files,
    )
    with pytest.raises(ProvenanceError) as caught:
        capture_installed_provenance(
            forged_capture,  # type: ignore[arg-type]
            source_root=None,
            container_image_digest=None,
        )
    assert caught.value.code == "manifest_capture_mismatch"
    assert "forged-model" not in str(caught.value)


def _resume_blocking_provenance_projection(value: Any) -> tuple[object, ...]:
    return (
        value.runner_source,
        value.runner_distribution,
        value.dependencies,
        value.package_version,
        value.provider_kind,
        value.requested_model,
        value.adapter_source_sha256,
        value.transport_policy,
        value.sdk_distribution,
        value.sdk_version,
        value.python_implementation,
        value.python_version,
        value.os_family,
        value.os_release,
        value.architecture,
    )


def test_resume_provenance_matches_preparation_blocking_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import provenance

    captured = _captured_inputs(authored_data=b"authored-case-bytes")
    prepared = capture_installed_provenance(
        captured,
        source_root=None,
        container_image_digest=None,
    )

    def forbidden_source_binding(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("resume provenance must not inspect a source checkout")

    def forbidden_container_parse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("resume provenance must not inspect container inputs")

    monkeypatch.setattr(provenance, "_source_binding", forbidden_source_binding)
    monkeypatch.setattr(provenance, "parse_container_image_digest", forbidden_container_parse)
    resumed = provenance.capture_resume_provenance(
        captured.resolved_manifest,
        authored_input_byte_count=provenance._authored_byte_count(captured),
    )

    assert _resume_blocking_provenance_projection(resumed) == (
        _resume_blocking_provenance_projection(prepared)
    )
    assert resumed.checkout_binding == "unavailable"
    assert resumed.git_commit is None
    assert resumed.git_state == "unavailable"
    assert resumed.uv_lock.availability == "unavailable"
    assert resumed.uv_lock.sha256 is None
    assert resumed.container_image_digest is None


def test_preparation_authored_byte_count_uses_exact_role_filter() -> None:
    from laconian_eval.capsule import provenance

    files = tuple(
        SimpleNamespace(record=SimpleNamespace(role=role), data=data)
        for role, data in (
            ("case", b"case"),
            ("arm", b"instruction"),
            ("replay", b"replay"),
            ("protocol", b"protocol"),
            ("runner_source", b"copied-runner-must-not-count-twice"),
        )
    )
    captured = SimpleNamespace(files=files)

    assert provenance._authored_byte_count(captured) == sum(
        len(item.data) for item in files if item.record.role != "runner_source"
    )


@pytest.mark.parametrize(
    ("authored_input_byte_count", "expected_code"),
    [
        (True, "invalid_count"),
        (-1, "invalid_count"),
        (
            RESOURCE_LIMITS_V1.captured_input_total_bytes + 1,
            "captured_input_total_limit",
        ),
    ],
)
def test_resume_provenance_rejects_invalid_authored_byte_count_before_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    authored_input_byte_count: Any,
    expected_code: str,
) -> None:
    from laconian_eval.capsule import provenance

    monkeypatch.setattr(
        provenance,
        "_capture_runner_distribution",
        lambda: pytest.fail("invalid byte count reached an installed snapshot"),
    )
    with pytest.raises(ResourceLimitError) as caught:
        provenance.capture_resume_provenance(
            _captured_inputs().resolved_manifest,
            authored_input_byte_count=authored_input_byte_count,
        )
    assert caught.value.code == expected_code


def test_provenance_does_not_import_import_policy() -> None:
    from laconian_eval.capsule import provenance

    module = ast.parse(Path(provenance.__file__).read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert "laconian_eval.capsule.import_policy" not in imported_modules


def test_project_environment_computes_exact_runtime_fingerprint_and_provider_identity(
    offline_provenance: Any,
) -> None:
    import_environment = _import_environment()
    environment = project_environment(
        offline_provenance,
        import_environment=import_environment,
        filesystem_class="apfs",
    )
    dependencies = [item.model_dump(mode="json") for item in environment.runtime.dependencies]
    expected = stable_digest(
        "laconian-runtime-v1",
        {
            "package_version": __version__,
            "runner_source_sha256": environment.runner_source_sha256,
            "dependencies": dependencies,
            "import_environment": import_environment.model_dump(mode="json"),
            "adapter_source_sha256": environment.provider.adapter_source_sha256,
        },
    )
    assert environment.runtime.runtime_fingerprint_sha256 == expected
    assert environment.package_version == __version__
    assert environment.provider.kind == "fake"
    assert environment.provider.transport_policy == "offline"
    assert environment.provider.sdk_distribution is None
    assert environment.provider.sdk_version is None


def test_replay_projection_passes_every_captured_provenance_field_exactly() -> None:
    digest = "2" * 64
    provenance = capture_installed_provenance(
        _captured_inputs(provider_kind="replay", requested_model="replay-model"),
        source_root=None,
        container_image_digest=f"sha256:{digest}",
    )
    environment = project_environment(
        provenance,
        import_environment=_import_environment(),
        filesystem_class="apfs",
    )
    assert environment.checkout_binding == provenance.checkout_binding == "unavailable"
    assert environment.git_state == provenance.git_state == "unavailable"
    assert environment.git_commit == provenance.git_commit is None
    assert environment.uv_lock == provenance.uv_lock
    assert environment.package_version == provenance.package_version
    assert environment.runner_source_sha256 == (provenance.runner_source.index.runner_source_sha256)
    assert environment.container_image_digest == provenance.container_image_digest == digest
    assert environment.runtime.python_implementation == provenance.python_implementation
    assert environment.runtime.python_version == provenance.python_version
    assert environment.runtime.os_family == provenance.os_family
    assert environment.runtime.os_release == provenance.os_release
    assert environment.runtime.architecture == provenance.architecture
    assert environment.provider.kind == provenance.provider_kind == "replay"
    assert environment.provider.requested_model == provenance.requested_model == "replay-model"
    assert environment.provider.adapter_source_sha256 == provenance.adapter_source_sha256
    assert environment.provider.transport_policy == provenance.transport_policy == "offline"
    assert environment.provider.sdk_distribution == provenance.sdk_distribution is None
    assert environment.provider.sdk_version == provenance.sdk_version is None


def test_project_environment_revalidates_forged_import_environment_content_free(
    offline_provenance: Any,
) -> None:
    valid = _import_environment()
    payload = {name: getattr(valid, name) for name in type(valid).model_fields}
    payload["import_policy_version"] = "forged-policy"
    forged = ImportEnvironmentV1.model_construct(**payload)
    with pytest.raises(ProvenanceError) as caught:
        project_environment(
            offline_provenance,
            import_environment=forged,
            filesystem_class="apfs",
        )
    assert caught.value.code == "invalid_import_environment"
    assert "forged-policy" not in str(caught.value)


def test_openai_sdk_identity_is_metadata_only(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    imported: list[str] = []
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "openai" or name.startswith("openai."):
            imported.append(name)
            raise AssertionError("provider SDK import is forbidden during provenance capture")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    captured = _captured_inputs(provider_kind="openai", requested_model="gpt-test")
    provenance = capture_installed_provenance(
        captured,
        source_root=ROOT,
        container_image_digest=None,
    )
    resumed = capture_resume_provenance(captured.resolved_manifest, authored_input_byte_count=0)
    assert imported == []
    assert provenance.sdk_distribution == "openai"
    assert provenance.sdk_version == metadata.version("openai")
    assert provenance.transport_policy == "openai-direct-v1"
    assert resumed.sdk_distribution == provenance.sdk_distribution
    assert resumed.sdk_version == provenance.sdk_version
    assert resumed.transport_policy == provenance.transport_policy
    assert resumed.dependencies == provenance.dependencies


def test_generated_environment_omits_host_private_and_unrestricted_metadata(
    offline_provenance: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LACONIAN_TEST_SECRET", "known-secret-value")
    environment = project_environment(
        offline_provenance,
        import_environment=_import_environment(),
        filesystem_class="apfs",
    )
    serialized = canonical_json(environment.model_dump(mode="json")).decode("utf-8")
    forbidden = {
        os.fspath(ROOT),
        os.fspath(tmp_path),
        os.path.expanduser("~"),
        socket.gethostname(),
        os.environ["LACONIAN_TEST_SECRET"],
        "direct_url.json",
        "pip freeze",
        "git diff",
        "remote.origin.url",
    }
    assert all(value not in serialized for value in forbidden if value)
    assert set(environment.model_dump()) == {
        "schema_version",
        "canonical_repository_url",
        "checkout_binding",
        "git_commit",
        "git_state",
        "uv_lock",
        "package_name",
        "package_version",
        "runner_source_sha256",
        "runtime",
        "provider",
        "container_image_digest",
    }


def test_provenance_repr_omits_private_paths_and_exact_byte_buffers(
    offline_provenance: Any,
) -> None:
    rendered = repr(offline_provenance)
    assert os.fspath(offline_provenance.runner_source._package_root) not in rendered
    assert "file_bytes=" not in rendered
    assert "metadata_bytes=" not in rendered
    assert "entry_points_bytes=" not in rendered
    assert "direct_url_bytes=" not in rendered


@pytest.mark.parametrize("code", ["runner_inventory_failed", "dependency_discovery_failed"])
def test_filesystem_sort_keys_reject_non_utf8_names_content_free(code: str) -> None:
    from laconian_eval.capsule import provenance

    invalid_name = "private-name-\udcff"
    with pytest.raises(ProvenanceError) as caught:
        provenance._utf8_sort_key(invalid_name, code=code)
    assert caught.value.code == code
    assert "private-name" not in str(caught.value)


def test_provenance_errors_are_content_free() -> None:
    secret = "secret-model-value"
    with pytest.raises(ProvenanceError) as caught:
        parse_container_image_digest(secret)
    assert secret not in str(caught.value)
