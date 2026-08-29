from __future__ import annotations

import importlib.machinery
import importlib.metadata
import importlib.util
import os
import stat
import sys
import sysconfig
import zipimport
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, ModuleType, SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from laconian_eval.capsule.canonical import sha256_bytes, stable_digest
from laconian_eval.capsule.import_policy import (
    CONSOLE_LAUNCHER_TEMPLATE,
    CONSOLE_LAUNCHER_TEMPLATE_SHA256,
    ImportPolicy,
    ImportPolicyError,
    InterpreterLayout,
    RuntimeImportState,
    SiteBootstrap,
    _LaconianImportGuard,
    _OriginValidatingLoader,
    build_import_policy,
    capture_runtime_import_state,
    classify_pth_file,
    derive_import_roots_from_members,
    directory_identity,
    inspect_site_bootstrap,
    revalidate_import_environment,
    revalidate_import_state,
    revalidate_loaded_modules,
    validate_interpreter_layout,
    validate_mapped_import_spec,
    verify_console_launcher,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.provenance import (
    DistributionFile,
    DistributionInventory,
    FileIdentity,
    InstalledProvenance,
    _capture_runner_distribution,
    capture_dependency_closure,
    capture_runner_source,
)
from laconian_eval.capsule.record_models import (
    DependencyRecordV1,
    ImportEnvironmentV1,
    ImportRootV1,
    UvLockV1,
)
from laconian_eval.capsule.schema import CONSOLE_LAUNCHER_TEMPLATE_SHA256 as SCHEMA_DIGEST

ROOT = Path(__file__).parents[2]


def _destshared_extension_name(destshared: Path) -> str:
    for path in sorted(destshared.iterdir(), key=lambda item: item.name):
        for suffix in sorted(
            importlib.machinery.EXTENSION_SUFFIXES,
            key=len,
            reverse=True,
        ):
            if path.is_file() and path.name.endswith(suffix):
                name = path.name[: -len(suffix)]
                if name and name not in sys.modules:
                    return name
                break
    raise AssertionError(f"no unloaded DESTSHARED extension under {destshared}")


def test_destshared_extension_name_prefers_longest_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "_laconian_destshared_probe.abi3.so").touch()
    monkeypatch.setattr(importlib.machinery, "EXTENSION_SUFFIXES", [".so", ".abi3.so"])

    assert _destshared_extension_name(tmp_path) == "_laconian_destshared_probe"


class _NamedLookupOnlyEnvironment:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self.lookups: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.lookups.append(key)
        if key not in {"PYTHONPATH", "PYTHONHOME"}:
            raise AssertionError(f"unexpected environment lookup: {key}")
        return self._values[key]

    def __iter__(self) -> Any:
        raise AssertionError("environment iteration is forbidden")

    def __len__(self) -> int:
        raise AssertionError("environment length inspection is forbidden")

    def copy(self) -> Any:
        raise AssertionError("environment copying is forbidden")

    def get(self, key: str, default: object = None) -> Any:
        raise AssertionError("environment get is forbidden")

    def items(self) -> Any:
        raise AssertionError("environment items are forbidden")

    def keys(self) -> Any:
        raise AssertionError("environment keys are forbidden")

    def values(self) -> Any:
        raise AssertionError("environment values are forbidden")


def _installed_provenance(*, provider_kind: str = "fake") -> InstalledProvenance:
    runner = capture_runner_source()
    dependencies = capture_dependency_closure(provider_kind=provider_kind)  # type: ignore[arg-type]
    return InstalledProvenance(
        runner_source=runner,
        runner_distribution=_capture_runner_distribution(),
        dependencies=dependencies,
        package_version="0.1.0.dev0",
        checkout_binding="unavailable",
        git_commit=None,
        git_state="unavailable",
        uv_lock=UvLockV1.model_validate({"availability": "unavailable", "sha256": None}),
        provider_kind=provider_kind,  # type: ignore[arg-type]
        requested_model="fixture-v1",
        adapter_source_sha256="0" * 64,
        transport_policy="openai-direct-v1" if provider_kind == "openai" else "offline",
        sdk_distribution="openai" if provider_kind == "openai" else None,
        sdk_version="3.3.1" if provider_kind == "openai" else None,
        container_image_digest=None,
        python_implementation="CPython",
        python_version=sys.version,
        os_family="Darwin",
        os_release="test",
        architecture="arm64",
    )


@pytest.fixture(scope="module")
def provenance() -> InstalledProvenance:
    return _installed_provenance()


def _module_runtime(provenance: InstalledProvenance) -> RuntimeImportState:
    import _collections_abc
    import collections.abc

    state = capture_runtime_import_state()
    main_origin = provenance.runner_source.origins["cli.py"].path
    main = SimpleNamespace(
        __file__=os.fspath(main_origin),
        __spec__=SimpleNamespace(
            origin=os.fspath(main_origin),
            loader=importlib.machinery.SourceFileLoader("__main__", os.fspath(main_origin)),
            submodule_search_locations=None,
        ),
    )
    optional_virtualenv = tuple(
        finder
        for finder in state.meta_path
        if (
            getattr(finder, "__module__", None) == "_virtualenv"
            and getattr(finder, "__qualname__", None) == "_Finder"
        )
        or (type(finder).__module__ == "_virtualenv" and type(finder).__qualname__ == "_Finder")
    )
    exact_meta_path = (
        *optional_virtualenv,
        importlib.machinery.BuiltinImporter,
        importlib.machinery.FrozenImporter,
        importlib.machinery.PathFinder,
    )
    stdlib = Path(sysconfig.get_path("stdlib"))
    zip_placeholder = stdlib.parent / (
        f"python{sys.version_info.major}{sys.version_info.minor}.zip"
    )
    destshared = Path(sysconfig.get_config_var("DESTSHARED"))
    site_roots = tuple(
        dict.fromkeys(
            os.fspath(inventory._site_packages_root) for inventory in provenance.dependencies
        )
    )
    exact_sys_path = (
        "",
        os.fspath(zip_placeholder),
        os.fspath(stdlib),
        os.fspath(destshared),
        *site_roots,
        os.fspath(provenance.runner_source._package_parent),
    )
    modules: dict[str, object] = {"__main__": main, "sys": sys}
    if collections.abc is _collections_abc:
        modules["collections.abc"] = _collections_abc
        modules["_collections_abc"] = _collections_abc
    return replace(
        state,
        sys_path=exact_sys_path,
        meta_path=exact_meta_path,
        modules=MappingProxyType(modules),
        importer_cache=MappingProxyType({}),
        environ=MappingProxyType({}),
        argv0=os.fspath(main_origin),
    )


@pytest.fixture(scope="module")
def policy(provenance: InstalledProvenance) -> ImportPolicy:
    return build_import_policy(provenance, runtime_state=_module_runtime(provenance))


def _assert_error(code: str, operation: Any) -> None:
    with pytest.raises(ImportPolicyError) as caught:
        operation()
    assert caught.value.code == code
    assert str(caught.value) == "import policy failed"
    assert code not in str(caught.value)


def _partial_module_map(
    policy: ImportPolicy,
    modules: Mapping[str, object],
) -> Mapping[str, object]:
    selected = dict(modules)
    for alias, module in policy.fixed_alias_modules.items():
        target = getattr(getattr(module, "__spec__", None), "name", None)
        assert type(target) is str
        selected[alias] = module
        selected[target] = module
    return MappingProxyType(selected)


def test_console_template_is_exact_and_schema_bound() -> None:
    assert CONSOLE_LAUNCHER_TEMPLATE == (
        b"#!<CURRENT_INTERPRETER>\n"
        b"# -*- coding: utf-8 -*-\n"
        b"import sys\n"
        b"from laconian_eval.cli import entrypoint\n"
        b'if __name__ == "__main__":\n'
        b'    if sys.argv[0].endswith("-script.pyw"):\n'
        b"        sys.argv[0] = sys.argv[0][:-11]\n"
        b'    elif sys.argv[0].endswith(".exe"):\n'
        b"        sys.argv[0] = sys.argv[0][:-4]\n"
        b"    sys.exit(entrypoint())\n"
    )
    assert sha256_bytes(CONSOLE_LAUNCHER_TEMPLATE) == SCHEMA_DIGEST
    assert CONSOLE_LAUNCHER_TEMPLATE_SHA256 == SCHEMA_DIGEST


def test_policy_projection_is_strict_sorted_content_free_and_uses_captured_guard_bytes(
    provenance: InstalledProvenance,
    policy: ImportPolicy,
) -> None:
    environment = policy.import_environment
    assert isinstance(environment, ImportEnvironmentV1)
    assert environment.import_policy_version == "laconian-import-policy-v1"
    assert environment.stdlib_origin_policy == "interpreter-layout-v1"
    assert environment.stdlib_extension_policy == "destshared-v1"
    assert environment.runner_import_mode == "path"
    assert environment.launcher_mode == "module"
    assert environment.launcher_template_sha256 is None
    captured = provenance.runner_source.file_bytes["capsule/import_policy.py"]
    assert environment.guard_source_sha256 == sha256_bytes(captured)
    assert environment.audit_hook_source_sha256 == sha256_bytes(captured)
    assert tuple(
        (item.distribution, item.module, item.origin_member) for item in environment.import_roots
    ) == tuple(
        sorted(
            {
                ("annotated-types", "annotated_types", "annotated_types/__init__.py"),
                ("packaging", "packaging", "packaging/__init__.py"),
                ("pydantic", "pydantic", "pydantic/__init__.py"),
                ("pydantic-core", "pydantic_core", "pydantic_core/__init__.py"),
                ("pyyaml", "_yaml", "_yaml/__init__.py"),
                ("pyyaml", "yaml", "yaml/__init__.py"),
                ("typing-extensions", "typing_extensions", "typing_extensions.py"),
                (
                    "typing-inspection",
                    "typing_inspection",
                    "typing_inspection/__init__.py",
                ),
            },
            key=lambda item: tuple(part.encode("utf-8") for part in item),
        )
    )
    serialized = environment.model_dump_json()
    assert os.fspath(provenance.runner_source._package_parent) not in serialized
    assert os.fspath(provenance.dependencies[0]._site_packages_root) not in serialized
    assert os.fspath(provenance.runner_source._package_parent) not in repr(policy)


def test_all_policy_runtime_reprs_and_errors_are_content_free(
    policy: ImportPolicy,
    provenance: InstalledProvenance,
) -> None:
    forbidden = {
        os.fspath(ROOT),
        os.fspath(provenance.runner_source._package_parent),
        os.fspath(provenance.runner_distribution._site_packages_root),
        os.fspath(policy.stdlib_root.canonical_path),
    }
    rendered = "\n".join(
        (
            repr(policy),
            repr(policy.runtime_state),
            repr(policy.stdlib_root),
            repr(policy.destshared_root),
            repr(policy.bootstrap),
        )
    )
    assert all(value not in rendered for value in forbidden)
    error = ImportPolicyError("host_path_rejected")
    assert repr(error) == "ImportPolicyError('import policy failed')"
    assert all(value not in repr(error) for value in forbidden)


def test_import_root_discovery_rejects_namespace_and_duplicate_ownership() -> None:
    _assert_error(
        "namespace_import_unsupported",
        lambda: derive_import_roots_from_members(
            {"namespace-dist": ("ns/member.py",)},
            package_owners={"ns": ("namespace-dist",)},
        ),
    )
    _assert_error(
        "duplicate_import_ownership",
        lambda: derive_import_roots_from_members(
            {
                "first": ("shared/__init__.py",),
                "second": ("shared/__init__.py",),
            },
            package_owners={"shared": ("first", "second")},
        ),
    )
    assert (
        derive_import_roots_from_members(
            {"metadata-only": ("metadata_only-1.0.dist-info/METADATA",)},
            package_owners={},
        )
        == ()
    )
    _assert_error(
        "missing_import_root",
        lambda: derive_import_roots_from_members(
            {"orphan-code": ("orphan.py",)},
            package_owners={},
        ),
    )


def test_import_root_discovery_uses_package_mapping_but_not_fresh_origin_paths(
    provenance: InstalledProvenance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    original = importlib.metadata.packages_distributions

    def observed() -> dict[str, list[str]]:
        calls.append("called")
        return original()

    monkeypatch.setattr(importlib.metadata, "packages_distributions", observed)
    built = build_import_policy(provenance, runtime_state=_module_runtime(provenance))
    assert calls == ["called"]
    assert {root.module for root in built.import_environment.import_roots} >= {
        "_yaml",
        "annotated_types",
        "packaging",
        "pydantic",
        "pydantic_core",
        "typing_extensions",
        "typing_inspection",
        "yaml",
    }


def test_mapped_top_level_spec_uses_fixed_pathfinder_and_exact_captured_owner(
    provenance: InstalledProvenance,
) -> None:
    calls: list[str] = []

    def fixed_pathfinder(name: str) -> importlib.machinery.ModuleSpec | None:
        calls.append(name)
        return importlib.machinery.PathFinder.find_spec(name)

    root = validate_mapped_import_spec(
        "packaging",
        "packaging",
        provenance.dependencies,
        find_spec=fixed_pathfinder,
    )
    assert calls == ["packaging"]
    assert root == ImportRootV1.model_validate(
        {
            "distribution": "packaging",
            "module": "packaging",
            "origin_member": "packaging/__init__.py",
        }
    )


def test_mapped_top_level_spec_rejects_missing_namespace_multiple_and_wrong_owner(
    provenance: InstalledProvenance,
) -> None:
    _assert_error(
        "missing_import_spec",
        lambda: validate_mapped_import_spec(
            "packaging",
            "packaging",
            provenance.dependencies,
            find_spec=lambda _: None,
        ),
    )
    namespace = importlib.machinery.ModuleSpec("packaging", loader=None, origin=None)
    namespace.submodule_search_locations = ["/one"]
    _assert_error(
        "namespace_import_unsupported",
        lambda: validate_mapped_import_spec(
            "packaging",
            "packaging",
            provenance.dependencies,
            find_spec=lambda _: namespace,
        ),
    )
    multiple = importlib.machinery.ModuleSpec("packaging", loader=None, origin=None)
    multiple.submodule_search_locations = ["/one", "/two"]
    _assert_error(
        "multiple_import_portions",
        lambda: validate_mapped_import_spec(
            "packaging",
            "packaging",
            provenance.dependencies,
            find_spec=lambda _: multiple,
        ),
    )
    pydantic_spec = importlib.machinery.PathFinder.find_spec("pydantic")
    assert pydantic_spec is not None
    _assert_error(
        "import_origin_wrong_distribution",
        lambda: validate_mapped_import_spec(
            "packaging",
            "packaging",
            provenance.dependencies,
            find_spec=lambda _: pydantic_spec,
        ),
    )


def test_mapped_top_level_spec_rejects_unowned_in_root_out_of_root_and_nonregular(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    pytest_spec = importlib.machinery.PathFinder.find_spec("pytest")
    assert pytest_spec is not None
    _assert_error(
        "unowned_import_origin",
        lambda: validate_mapped_import_spec(
            "pytest",
            "packaging",
            provenance.dependencies,
            find_spec=lambda _: pytest_spec,
        ),
    )
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"")
    outside_spec = importlib.machinery.ModuleSpec(
        "outside",
        importlib.machinery.SourceFileLoader("outside", os.fspath(outside)),
        origin=os.fspath(outside),
    )
    _assert_error(
        "import_origin_not_allowed",
        lambda: validate_mapped_import_spec(
            "outside",
            "packaging",
            provenance.dependencies,
            find_spec=lambda _: outside_spec,
        ),
    )
    directory_spec = importlib.machinery.ModuleSpec(
        "directory",
        importlib.machinery.SourceFileLoader("directory", os.fspath(tmp_path)),
        origin=os.fspath(tmp_path),
    )
    _assert_error(
        "import_origin_not_regular",
        lambda: validate_mapped_import_spec(
            "directory",
            "packaging",
            provenance.dependencies,
            find_spec=lambda _: directory_spec,
        ),
    )


def test_policy_build_is_pure_and_does_not_mutate_live_import_state(
    provenance: InstalledProvenance,
) -> None:
    before = (
        tuple(sys.path),
        tuple(sys.meta_path),
        tuple(sys.path_hooks),
        tuple(sys.path_importer_cache.items()),
    )
    state = _module_runtime(provenance)
    built = build_import_policy(provenance, runtime_state=state)
    after = (
        tuple(sys.path),
        tuple(sys.meta_path),
        tuple(sys.path_hooks),
        tuple(sys.path_importer_cache.items()),
    )
    assert before == after
    assert built.runtime_state.sys_path != state.sys_path
    assert "" not in built.runtime_state.sys_path


def test_homebrew_alias_and_cellar_spelling_compare_by_opened_directory_identity() -> None:
    stdlib = Path(sysconfig.get_path("stdlib"))
    alias_identity = directory_identity(stdlib)
    canonical_identity = directory_identity(Path(os.path.realpath(stdlib)))
    assert (alias_identity.device, alias_identity.inode) == (
        canonical_identity.device,
        canonical_identity.inode,
    )
    assert alias_identity.canonical_path == canonical_identity.canonical_path


def test_policy_canonicalizes_stdlib_destshared_and_zip_placeholder_by_identity(
    policy: ImportPolicy,
) -> None:
    identities = tuple((root.identity.device, root.identity.inode) for root in policy.allowed_roots)
    assert len(identities) == len(set(identities))
    assert policy.stdlib_root.identity == directory_identity(sysconfig.get_path("stdlib"))
    assert policy.destshared_root.identity == directory_identity(
        sysconfig.get_config_var("DESTSHARED")
    )
    zip_name = f"python{sys.version_info.major}{sys.version_info.minor}.zip"
    assert policy.zip_placeholder.name == zip_name
    assert policy.zip_placeholder.parent == policy.stdlib_root.canonical_path.parent
    assert not policy.zip_placeholder.exists()
    assert all(not entry.endswith(".zip") for entry in policy.runtime_state.sys_path)


def test_canonical_output_sys_path_has_exact_physical_policy_order(
    policy: ImportPolicy,
    provenance: InstalledProvenance,
) -> None:
    expected: list[Path] = [policy.stdlib_root.canonical_path]
    if policy.destshared_root.identity != policy.stdlib_root.identity:
        expected.append(policy.destshared_root.canonical_path)
    expected.append(directory_identity(provenance.runner_source._package_parent).canonical_path)
    seen = {
        (root.identity.device, root.identity.inode)
        for root in policy.allowed_roots[: len(expected)]
    }
    for inventory in provenance.dependencies:
        identity = directory_identity(inventory._site_packages_root)
        key = (identity.device, identity.inode)
        if key not in seen:
            expected.append(identity.canonical_path)
            seen.add(key)
    assert tuple(map(Path, policy.runtime_state.sys_path)) == tuple(expected)


def test_interpreter_layout_requires_destshared_beneath_base_and_absent_zip(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    stdlib = base / "lib/python3.11"
    destshared = stdlib / "lib-dynload"
    destshared.mkdir(parents=True)
    layout = validate_interpreter_layout(
        stdlib=stdlib,
        destshared=destshared,
        platstdlib=stdlib,
        base_prefix=base,
        version=(3, 11),
    )
    assert isinstance(layout, InterpreterLayout)
    assert layout.platstdlib_mode == "same_as_stdlib"
    assert layout.zip_placeholder == stdlib.parent / "python311.zip"

    _assert_error(
        "missing_destshared",
        lambda: validate_interpreter_layout(
            stdlib=stdlib,
            destshared=None,
            platstdlib=stdlib,
            base_prefix=base,
            version=(3, 11),
        ),
    )
    outside = tmp_path / "outside-dynload"
    outside.mkdir()
    _assert_error(
        "destshared_outside_base_prefix",
        lambda: validate_interpreter_layout(
            stdlib=stdlib,
            destshared=outside,
            platstdlib=stdlib,
            base_prefix=base,
            version=(3, 11),
        ),
    )
    layout.zip_placeholder.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    _assert_error(
        "existing_stdlib_zip",
        lambda: validate_interpreter_layout(
            stdlib=stdlib,
            destshared=destshared,
            platstdlib=stdlib,
            base_prefix=base,
            version=(3, 11),
        ),
    )


def test_distinct_active_platstdlib_is_rejected(
    provenance: InstalledProvenance,
) -> None:
    state = _module_runtime(provenance)
    platstdlib = Path(sysconfig.get_path("platstdlib"))
    if directory_identity(platstdlib) == directory_identity(sysconfig.get_path("stdlib")):
        pytest.skip("interpreter has no distinct platstdlib")
    changed = replace(state, sys_path=(*state.sys_path, os.fspath(platstdlib)))
    _assert_error(
        "active_distinct_platstdlib",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_runtime_state_capture_projects_only_named_import_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import import_policy

    environment = _NamedLookupOnlyEnvironment(
        {
            "PYTHONPATH": "",
            "PYTHONHOME": "",
            "UNRELATED_CREDENTIAL": "must-not-be-read",
        }
    )
    user_site_calls: list[str] = []

    def observed_getusersitepackages() -> str:
        user_site_calls.append("called")
        return "/computed/from/environment"

    with monkeypatch.context() as patcher:
        patcher.setattr(import_policy.os, "environ", environment)
        patcher.setattr(import_policy.site, "USER_SITE", "/already/initialized/user-site")
        patcher.setattr(
            import_policy.site,
            "getusersitepackages",
            observed_getusersitepackages,
        )
        state = capture_runtime_import_state()

    assert environment.lookups == ["PYTHONPATH", "PYTHONHOME"]
    assert dict(state.environ) == {"PYTHONPATH": "", "PYTHONHOME": ""}
    assert type(state.environ) is type(MappingProxyType({}))
    assert state.user_site == Path("/already/initialized/user-site")
    assert user_site_calls == []
    with pytest.raises(TypeError):
        state.environ["PYTHONPATH"] = "changed"  # type: ignore[index]


def test_runtime_state_capture_rejects_unexpected_initialized_user_site_without_resolving_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import import_policy

    user_site_calls: list[str] = []

    def observed_getusersitepackages() -> str:
        user_site_calls.append("called")
        return "/computed/from/environment"

    with monkeypatch.context() as patcher:
        patcher.setattr(
            import_policy.os,
            "environ",
            {"PYTHONPATH": "", "PYTHONHOME": ""},
        )
        patcher.setattr(import_policy.site, "USER_SITE", object())
        patcher.setattr(
            import_policy.site,
            "getusersitepackages",
            observed_getusersitepackages,
        )
        _assert_error("runtime_state_capture_failed", capture_runtime_import_state)
    assert user_site_calls == []


def test_injected_runtime_environment_uses_exact_named_lookups_and_drops_unrelated_values(
    provenance: InstalledProvenance,
) -> None:
    environment = _NamedLookupOnlyEnvironment(
        {
            "PYTHONPATH": "",
            "PYTHONHOME": "",
            "UNRELATED_CREDENTIAL": "must-not-be-read",
        }
    )
    state = replace(
        _module_runtime(provenance),
        environ=cast(Any, environment),
    )

    built = build_import_policy(provenance, runtime_state=state)

    assert environment.lookups == ["PYTHONPATH", "PYTHONHOME"]
    assert dict(built.initial_state.environ) == {"PYTHONPATH": "", "PYTHONHOME": ""}
    assert built.runtime_state.environ is built.initial_state.environ


@pytest.mark.parametrize("name", ["PYTHONPATH", "PYTHONHOME"])
def test_nonempty_python_path_configuration_is_rejected(
    provenance: InstalledProvenance,
    name: str,
) -> None:
    state = replace(
        _module_runtime(provenance),
        environ=MappingProxyType({name: "/sensitive/host/path"}),
    )
    _assert_error(
        f"nonempty_{name.lower()}",
        lambda: build_import_policy(provenance, runtime_state=state),
    )


def test_enabled_user_site_is_rejected(provenance: InstalledProvenance) -> None:
    state = replace(_module_runtime(provenance), user_site_enabled=True)
    _assert_error(
        "user_site_enabled",
        lambda: build_import_policy(provenance, runtime_state=state),
    )


def test_duplicate_launcher_entry_is_rejected(provenance: InstalledProvenance) -> None:
    state = _module_runtime(provenance)
    changed = replace(state, sys_path=("", *state.sys_path))
    _assert_error(
        "ambiguous_launcher_path",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_unknown_active_root_is_rejected_content_free(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    state = _module_runtime(provenance)
    changed = replace(state, sys_path=(*state.sys_path, os.fspath(tmp_path)))
    _assert_error(
        "unknown_import_root",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_physically_equal_active_root_aliases_deduplicate_at_first_occurrence(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    runner_parent = provenance.runner_source._package_parent
    alias = tmp_path / "runner-parent-alias"
    alias.symlink_to(runner_parent, target_is_directory=True)
    state = _module_runtime(provenance)
    changed = replace(state, sys_path=(*state.sys_path, os.fspath(alias)))
    built = build_import_policy(provenance, runtime_state=changed)
    expected = directory_identity(runner_parent)
    physical_matches = [
        item
        for item in built.runtime_state.sys_path
        if _same_physical_directory_for_test(item, expected)
    ]
    assert physical_matches == [os.fspath(expected.canonical_path)]


def _same_physical_directory_for_test(path: str, expected: object) -> bool:
    actual = directory_identity(path)
    return (actual.device, actual.inode) == (expected.device, expected.inode)  # type: ignore[attr-defined]


def test_existing_active_zip_is_rejected_before_unknown_root(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "host.zip"
    archive.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    state = _module_runtime(provenance)
    changed = replace(state, sys_path=(*state.sys_path, os.fspath(archive)))
    _assert_error(
        "active_zip_import",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


@pytest.mark.parametrize("shadow", ["json.py", "json.pyc", "pydantic.py", "laconian_eval.py"])
def test_cwd_shadowing_is_rejected_even_before_import(
    provenance: InstalledProvenance,
    tmp_path: Path,
    shadow: str,
) -> None:
    (tmp_path / shadow).write_bytes(b"raise AssertionError('must not execute')\n")
    state = _module_runtime(provenance)
    first, *remaining = state.sys_path
    assert first == "" or directory_identity(first) == directory_identity(state.cwd)
    changed = replace(
        state,
        cwd=tmp_path,
        sys_path=(os.fspath(tmp_path), *remaining),
    )
    _assert_error(
        "shadowing_import",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_disabled_user_site_shadowing_is_still_rejected(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    (tmp_path / "packaging").mkdir()
    (tmp_path / "packaging/__init__.py").write_bytes(b"")
    state = replace(
        _module_runtime(provenance),
        user_site_enabled=False,
        user_site=tmp_path,
    )
    _assert_error(
        "shadowing_import",
        lambda: build_import_policy(provenance, runtime_state=state),
    )


def test_disabled_user_site_sourceless_shadowing_is_still_rejected(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    (tmp_path / "packaging.pyc").write_bytes(b"not executed")
    state = replace(
        _module_runtime(provenance),
        user_site_enabled=False,
        user_site=tmp_path,
    )
    _assert_error(
        "shadowing_import",
        lambda: build_import_policy(provenance, runtime_state=state),
    )


def test_unknown_meta_path_finder_is_rejected(provenance: InstalledProvenance) -> None:
    state = _module_runtime(provenance)
    changed = replace(state, meta_path=(*state.meta_path, object()))
    _assert_error(
        "unknown_meta_path_finder",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_live_pytest_assertion_rewriter_is_rejected_not_silently_filtered(
    provenance: InstalledProvenance,
) -> None:
    clean = _module_runtime(provenance)
    live_meta_path = capture_runtime_import_state().meta_path
    assert any(type(finder).__module__.startswith("_pytest") for finder in live_meta_path)
    changed = replace(clean, meta_path=live_meta_path)
    _assert_error(
        "unknown_meta_path_finder",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_unknown_path_hook_is_rejected(provenance: InstalledProvenance) -> None:
    state = _module_runtime(provenance)
    changed = replace(state, path_hooks=(*state.path_hooks, lambda _: None))
    _assert_error(
        "unknown_path_hook",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_unknown_importer_cache_finder_is_rejected(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    state = _module_runtime(provenance)
    changed = replace(
        state,
        importer_cache=MappingProxyType({os.fspath(tmp_path): object()}),
    )
    _assert_error(
        "unknown_importer_cache_finder",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_malicious_cached_finder_is_rejected_before_any_find_spec_side_effect(
    provenance: InstalledProvenance,
) -> None:
    side_effects: list[str] = []

    class MaliciousFinder:
        def find_spec(self, fullname: str, path: object = None) -> None:
            side_effects.append(fullname)

    state = _module_runtime(provenance)
    allowed_key = os.fspath(Path(sysconfig.get_path("stdlib")))
    changed = replace(
        state,
        importer_cache=MappingProxyType({allowed_key: MaliciousFinder()}),
    )
    _assert_error(
        "unknown_importer_cache_finder",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )
    assert side_effects == []


def test_cached_file_finder_must_be_bound_to_its_cache_key(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    state = _module_runtime(provenance)
    allowed_key = os.fspath(Path(sysconfig.get_path("stdlib")))
    mismatched = state.path_hooks[1](os.fspath(tmp_path))  # type: ignore[operator]
    changed = replace(
        state,
        importer_cache=MappingProxyType({allowed_key: mismatched}),
    )
    _assert_error(
        "importer_cache_finder_mismatch",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_cached_file_finder_must_have_exact_standard_loader_table(
    provenance: InstalledProvenance,
) -> None:
    state = _module_runtime(provenance)
    allowed_key = os.fspath(Path(sysconfig.get_path("stdlib")))
    incomplete = importlib.machinery.FileFinder(
        allowed_key,
        (importlib.machinery.SourceFileLoader, importlib.machinery.SOURCE_SUFFIXES),
    )
    changed = replace(
        state,
        importer_cache=MappingProxyType({allowed_key: incomplete}),
    )
    _assert_error(
        "importer_cache_finder_mismatch",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_cache_purges_launcher_and_homebrew_zip_aliases_but_preseeds_nested_allowed_dirs(
    provenance: InstalledProvenance,
) -> None:
    state = _module_runtime(provenance)
    file_hook = state.path_hooks[1]
    cwd_key = os.fspath(state.cwd)
    zip_key = state.sys_path[1]
    canonical_zip_key = os.path.realpath(zip_key)
    nested = Path(os.path.realpath(sysconfig.get_path("stdlib"))) / "encodings"
    initial_cache = MappingProxyType(
        {
            cwd_key: file_hook(cwd_key),
            zip_key: None,
            canonical_zip_key: None,
            os.fspath(nested): file_hook(os.fspath(nested)),
        }
    )
    changed = replace(state, importer_cache=initial_cache)
    built = build_import_policy(provenance, runtime_state=changed)
    keys = tuple(built.runtime_state.importer_cache)
    assert cwd_key not in keys
    assert zip_key not in keys
    assert canonical_zip_key not in keys
    assert os.fspath(nested) in keys
    assert type(built.runtime_state.importer_cache[os.fspath(nested)]) is (
        importlib.machinery.FileFinder
    )


def test_external_null_importer_cache_entry_is_rejected(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    state = replace(
        _module_runtime(provenance),
        importer_cache=MappingProxyType({os.fspath(tmp_path): None}),
    )
    _assert_error(
        "unknown_importer_cache_root",
        lambda: build_import_policy(provenance, runtime_state=state),
    )


def test_virtualenv_pth_is_the_sole_exact_executable_exception(tmp_path: Path) -> None:
    runner_parent = tmp_path / "src"
    runner_parent.mkdir()
    assert (
        classify_pth_file("_virtualenv.pth", b"import _virtualenv", runner_parent=runner_parent)
        == "virtualenv"
    )
    for data in (
        b"import _virtualenv\n",
        b"import _virtualenv; import evil",
        b"import evil",
        b"import _editable_impl_laconian_eval",
    ):
        _assert_error(
            "unknown_executable_pth",
            lambda data=data: classify_pth_file("generated.pth", data, runner_parent=runner_parent),
        )


def test_path_only_pth_uses_target_directory_identity_and_rejects_other_targets(
    tmp_path: Path,
) -> None:
    runner_parent = tmp_path / "src"
    runner_parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(runner_parent, target_is_directory=True)
    assert (
        classify_pth_file(
            "_editable_impl_laconian_eval.pth",
            os.fsencode(alias),
            runner_parent=runner_parent,
        )
        == "runner_path"
    )
    other = tmp_path / "other"
    other.mkdir()
    _assert_error(
        "unknown_pth_target",
        lambda: classify_pth_file(
            "_editable_impl_laconian_eval.pth",
            os.fsencode(other),
            runner_parent=runner_parent,
        ),
    )
    _assert_error(
        "invalid_path_pth",
        lambda: classify_pth_file(
            "_editable_impl_laconian_eval.pth",
            os.fsencode(runner_parent) + b"\n" + os.fsencode(runner_parent),
            runner_parent=runner_parent,
        ),
    )


def test_egg_link_is_always_rejected(tmp_path: Path) -> None:
    runner_parent = tmp_path / "src"
    runner_parent.mkdir()
    _assert_error(
        "egg_link_unsupported",
        lambda: classify_pth_file("laconian.egg-link", b"anything", runner_parent=runner_parent),
    )


def _standard_meta_path(*, include_virtualenv: bool) -> tuple[object, ...]:
    captured = capture_runtime_import_state().meta_path
    virtualenv = tuple(
        finder
        for finder in captured
        if (
            getattr(finder, "__module__", None) == "_virtualenv"
            and getattr(finder, "__qualname__", None) == "_Finder"
        )
        or (type(finder).__module__ == "_virtualenv" and type(finder).__qualname__ == "_Finder")
    )
    return (
        *(virtualenv if include_virtualenv else ()),
        importlib.machinery.BuiltinImporter,
        importlib.machinery.FrozenImporter,
        importlib.machinery.PathFinder,
    )


def test_site_bootstrap_enumerates_all_entries_for_path_and_wheel_modes(
    tmp_path: Path,
) -> None:
    wheel_site = tmp_path / "wheel-site"
    wheel_site.mkdir()
    wheel = inspect_site_bootstrap(
        (wheel_site,),
        runner_parent=wheel_site,
        meta_path=_standard_meta_path(include_virtualenv=False),
    )
    assert isinstance(wheel, SiteBootstrap)
    assert wheel.runner_import_mode == "wheel"
    assert wheel.virtualenv_bootstrap_sha256 is None
    assert wheel.virtualenv_finder is None

    path_site = tmp_path / "path-site"
    path_site.mkdir()
    runner_parent = tmp_path / "src"
    runner_parent.mkdir()
    (path_site / "_editable_impl_laconian_eval.pth").write_bytes(os.fsencode(runner_parent))
    path_mode = inspect_site_bootstrap(
        (path_site,),
        runner_parent=runner_parent,
        meta_path=_standard_meta_path(include_virtualenv=False),
    )
    assert path_mode.runner_import_mode == "path"
    assert path_mode.virtualenv_bootstrap_sha256 is None


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("evil.pth", b"import evil", "unknown_executable_pth"),
        ("generated.pth", b"import _editable_impl_project", "unknown_executable_pth"),
        ("project.egg-link", b"/outside", "egg_link_unsupported"),
    ],
)
def test_site_bootstrap_build_rejects_every_unknown_pth_or_egg_link(
    tmp_path: Path,
    name: str,
    data: bytes,
    code: str,
) -> None:
    site_root = tmp_path / "site"
    site_root.mkdir()
    runner_parent = tmp_path / "src"
    runner_parent.mkdir()
    (site_root / "_editable_impl_laconian_eval.pth").write_bytes(os.fsencode(runner_parent))
    (site_root / name).write_bytes(data)
    _assert_error(
        code,
        lambda: inspect_site_bootstrap(
            (site_root,),
            runner_parent=runner_parent,
            meta_path=_standard_meta_path(include_virtualenv=False),
        ),
    )


def test_site_bootstrap_rejects_wrong_path_target_and_missing_path_projection(
    tmp_path: Path,
) -> None:
    site_root = tmp_path / "site"
    site_root.mkdir()
    runner_parent = tmp_path / "src"
    runner_parent.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    pth = site_root / "_editable_impl_laconian_eval.pth"
    pth.write_bytes(os.fsencode(other))
    _assert_error(
        "unknown_pth_target",
        lambda: inspect_site_bootstrap(
            (site_root,),
            runner_parent=runner_parent,
            meta_path=_standard_meta_path(include_virtualenv=False),
        ),
    )
    pth.unlink()
    _assert_error(
        "missing_runner_path_pth",
        lambda: inspect_site_bootstrap(
            (site_root,),
            runner_parent=runner_parent,
            meta_path=_standard_meta_path(include_virtualenv=False),
        ),
    )


def test_virtualenv_bootstrap_requires_exact_module_origin_and_verified_finder(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    actual_site = provenance.runner_distribution._site_packages_root
    site_root = tmp_path / "site"
    site_root.mkdir()
    (site_root / "_virtualenv.pth").write_bytes(b"import _virtualenv")
    (site_root / "_virtualenv.py").write_bytes((actual_site / "_virtualenv.py").read_bytes())
    _assert_error(
        "virtualenv_module_origin_mismatch",
        lambda: inspect_site_bootstrap(
            (site_root,),
            runner_parent=site_root,
            meta_path=_standard_meta_path(include_virtualenv=True),
        ),
    )
    _assert_error(
        "missing_virtualenv_finder",
        lambda: inspect_site_bootstrap(
            (site_root,),
            runner_parent=site_root,
            meta_path=_standard_meta_path(include_virtualenv=False),
        ),
    )


def test_real_virtualenv_bootstrap_accepts_only_the_active_exact_finder(
    provenance: InstalledProvenance,
) -> None:
    site_root = provenance.runner_distribution._site_packages_root
    bootstrap = inspect_site_bootstrap(
        (site_root,),
        runner_parent=provenance.runner_source._package_parent,
        meta_path=_standard_meta_path(include_virtualenv=True),
    )
    assert bootstrap.virtualenv_bootstrap_sha256 is not None
    assert bootstrap.virtualenv_finder is _standard_meta_path(include_virtualenv=True)[0]


def test_site_bootstrap_rejects_directory_inventory_change_during_enumeration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import import_policy

    site_root = tmp_path / "site"
    site_root.mkdir()
    runner_parent = tmp_path / "src"
    runner_parent.mkdir()
    (site_root / "_editable_impl_laconian_eval.pth").write_bytes(os.fsencode(runner_parent))
    original = import_policy._bootstrap_entry_bytes
    mutated = False

    def mutating_read(root: Path, name: str) -> bytes:
        nonlocal mutated
        data = original(root, name)
        if not mutated:
            mutated = True
            (site_root / "late-added.pth").write_bytes(b"import evil")
        return data

    monkeypatch.setattr(import_policy, "_bootstrap_entry_bytes", mutating_read)
    _assert_error(
        "site_bootstrap_changed",
        lambda: inspect_site_bootstrap(
            (site_root,),
            runner_parent=runner_parent,
            meta_path=_standard_meta_path(include_virtualenv=False),
        ),
    )


@pytest.mark.parametrize("scan_kind", ["tree", "shadow"])
def test_import_directory_scans_bound_streamed_entries_before_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scan_kind: str,
) -> None:
    from laconian_eval.capsule import import_policy

    entry_limit = RESOURCE_LIMITS_V1.dependency_files
    scanners: list[FakeScanner] = []
    stat_calls: list[str] = []

    class FakeEntry:
        def __init__(self, name: str) -> None:
            self.name = name

        def stat(self, *, follow_symlinks: bool) -> SimpleNamespace:
            assert follow_symlinks is False
            stat_calls.append(self.name)
            return SimpleNamespace(st_mode=stat.S_IFREG)

    class FakeScanner:
        def __init__(self) -> None:
            self.emitted = 0

        def __enter__(self) -> FakeScanner:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __iter__(self) -> FakeScanner:
            return self

        def __next__(self) -> FakeEntry:
            if self.emitted == entry_limit + 1:
                raise StopIteration
            self.emitted += 1
            return FakeEntry(f"ordinary-{self.emitted:06d}.txt")

    def fake_scandir(_path: object) -> FakeScanner:
        scanner = FakeScanner()
        scanners.append(scanner)
        return scanner

    monkeypatch.setattr(import_policy.os, "scandir", fake_scandir)
    with pytest.raises(ResourceLimitError) as caught:
        if scan_kind == "tree":
            root = import_policy.VerifiedDirectory(directory_identity(tmp_path), "test")
            import_policy._scan_directory_tree(root)
        else:
            import_policy._scan_shadow_directory(tmp_path, frozenset())
    assert caught.value.code == "import_directory_entry_count_limit"
    assert str(caught.value) == "resource limit rejected"
    assert len(scanners) == 1
    assert scanners[0].emitted == entry_limit + 1
    assert stat_calls == []


def test_build_calls_site_bootstrap_enumerator_for_every_selected_root(
    provenance: InstalledProvenance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import import_policy

    calls: list[tuple[Path, ...]] = []
    original = import_policy.inspect_site_bootstrap

    def observed(
        site_roots: tuple[Path, ...],
        *,
        runner_parent: Path,
        meta_path: tuple[object, ...],
    ) -> SiteBootstrap:
        calls.append(site_roots)
        return original(
            site_roots,
            runner_parent=runner_parent,
            meta_path=meta_path,
        )

    monkeypatch.setattr(import_policy, "inspect_site_bootstrap", observed)
    build_import_policy(provenance, runtime_state=_module_runtime(provenance))
    expected = {
        directory_identity(item._site_packages_root).canonical_path
        for item in (*provenance.dependencies,)
    }
    assert len(calls) == 1
    assert set(calls[0]) == expected


def test_build_wires_every_emitted_root_through_mapped_spec_validator(
    provenance: InstalledProvenance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import import_policy

    calls: list[tuple[str, str]] = []
    original = import_policy.validate_mapped_import_spec

    def observed(
        module: str,
        distribution: str,
        dependencies: tuple[object, ...],
        **kwargs: object,
    ) -> ImportRootV1:
        calls.append((module, distribution))
        return original(module, distribution, dependencies, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(import_policy, "validate_mapped_import_spec", observed)
    built = build_import_policy(provenance, runtime_state=_module_runtime(provenance))
    assert calls == [
        (root.module, root.distribution) for root in built.import_environment.import_roots
    ]


@pytest.mark.parametrize("module_name", ["json", "sys", "_frozen_importlib"])
def test_build_rejects_dependency_root_shadowed_by_earlier_import_winner(
    provenance: InstalledProvenance,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
) -> None:
    site_root = tmp_path / "collision-site"
    site_root.mkdir()
    member = f"{module_name}.py"
    source = site_root / member
    data = b"COLLISION = True\n"
    source.write_bytes(data)
    metadata_record = source.stat()
    identity = FileIdentity(
        device=metadata_record.st_dev,
        inode=metadata_record.st_ino,
        mode=metadata_record.st_mode,
        size=metadata_record.st_size,
        mtime_ns=metadata_record.st_mtime_ns,
        ctime_ns=metadata_record.st_ctime_ns,
    )
    member_payload = {
        "path": member,
        "byte_length": len(data),
        "sha256": sha256_bytes(data),
    }
    distribution = "stdlib-collision"
    record = DependencyRecordV1.model_validate(
        {
            "distribution": distribution,
            "version": "1.0",
            "files_sha256": stable_digest(
                "laconian-distribution-files-v1",
                {"distribution": distribution, "files": [member_payload]},
            ),
        }
    )
    inventory = DistributionInventory(
        record=record,
        files=(
            DistributionFile(
                path=member,
                byte_length=len(data),
                sha256=sha256_bytes(data),
                data=data,
                _origin=source,
                _identity=identity,
            ),
        ),
        metadata_bytes=b"",
        _site_packages_root=site_root,
        _captured_byte_length=len(data),
        _captured_member_count=1,
    )
    colliding = replace(
        provenance,
        dependencies=(*provenance.dependencies, inventory),
    )
    package_owners = {
        module: list(owners)
        for module, owners in importlib.metadata.packages_distributions().items()
    }
    package_owners[module_name] = [distribution]
    monkeypatch.setattr(
        importlib.metadata,
        "packages_distributions",
        lambda: package_owners,
    )
    _assert_error(
        "import_origin_not_allowed",
        lambda: build_import_policy(colliding, runtime_state=_module_runtime(colliding)),
    )


def test_build_fails_when_mapped_pathfinder_returns_unowned_in_root_spec(
    provenance: InstalledProvenance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from laconian_eval.capsule import import_policy

    pytest_spec = importlib.machinery.PathFinder.find_spec("pytest")
    assert pytest_spec is not None
    original = import_policy._find_spec_in_verified_roots

    def poisoned(
        fullname: str,
        roots: tuple[Path, ...],
        file_hook: object,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname == "packaging":
            return pytest_spec
        return original(fullname, roots, file_hook)

    monkeypatch.setattr(import_policy, "_find_spec_in_verified_roots", poisoned)
    _assert_error(
        "unowned_import_origin",
        lambda: build_import_policy(provenance, runtime_state=_module_runtime(provenance)),
    )


def _launcher_bytes(executable: str | os.PathLike[str] = sys.executable) -> bytes:
    _, remainder = CONSOLE_LAUNCHER_TEMPLATE.split(b"\n", 1)
    return b"#!" + os.fsencode(executable) + b"\n" + remainder


def test_console_launcher_verification_normalizes_only_the_absolute_shebang(
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    assert verify_console_launcher(launcher, executable=sys.executable) == SCHEMA_DIGEST


def test_console_shebang_accepts_descriptor_equal_absolute_executable_alias(
    tmp_path: Path,
) -> None:
    executable_alias = tmp_path / "python-alias"
    executable_alias.symlink_to(Path(sys.executable))
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes(executable_alias))
    launcher.chmod(0o755)
    assert launcher.is_file() and not launcher.is_symlink()
    assert verify_console_launcher(launcher, executable=sys.executable) == SCHEMA_DIGEST


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda value: value.replace(b"import sys\n", b"import os\n"),
            "launcher_template_mismatch",
        ),
        (lambda value: value[:-1], "launcher_template_mismatch"),
        (lambda value: value.replace(b"\n", b"\r\n"), "launcher_template_mismatch"),
        (lambda value: b"#!python\n" + value.split(b"\n", 1)[1], "invalid_launcher_shebang"),
    ],
)
def test_console_launcher_rejects_every_nonstandard_byte(
    tmp_path: Path,
    mutation: Any,
    code: str,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(mutation(_launcher_bytes()))
    launcher.chmod(0o755)
    _assert_error(code, lambda: verify_console_launcher(launcher, executable=sys.executable))


def test_console_launcher_rejects_symlink_and_wrong_executable(tmp_path: Path) -> None:
    launcher = tmp_path / "laconian-real"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    alias = tmp_path / "laconian"
    alias.symlink_to(launcher)
    _assert_error(
        "launcher_not_regular",
        lambda: verify_console_launcher(alias, executable=sys.executable),
    )
    _assert_error(
        "launcher_interpreter_mismatch",
        lambda: verify_console_launcher(launcher, executable="/bin/sh"),
    )


def test_console_mode_requires_identical_main_and_argv0_regular_file(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    state = _module_runtime(provenance)
    main = SimpleNamespace(__file__=os.fspath(launcher), __spec__=None)
    launcher_parent = os.fspath(tmp_path)
    changed = replace(
        state,
        modules=MappingProxyType({"__main__": main, "sys": sys}),
        argv0=os.fspath(launcher),
        sys_path=(launcher_parent, *state.sys_path[1:]),
    )
    console = build_import_policy(provenance, runtime_state=changed)
    assert console.import_environment.launcher_mode == "console_script"
    assert console.import_environment.launcher_template_sha256 == SCHEMA_DIGEST
    other = tmp_path / "other"
    other.write_bytes(_launcher_bytes())
    other.chmod(0o755)
    mismatched = replace(changed, argv0=os.fspath(other))
    _assert_error(
        "launcher_identity_mismatch",
        lambda: build_import_policy(provenance, runtime_state=mismatched),
    )


def test_console_mode_accepts_hardlink_identity_but_rejects_symlink_main(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    hardlink = tmp_path / "laconian-hardlink"
    os.link(launcher, hardlink)
    symlink = tmp_path / "laconian-symlink"
    symlink.symlink_to(launcher)
    state = _module_runtime(provenance)
    console_path = (os.fspath(tmp_path), *state.sys_path[1:])
    hardlinked = replace(
        state,
        modules=MappingProxyType(
            {"__main__": SimpleNamespace(__file__=os.fspath(launcher), __spec__=None)}
        ),
        argv0=os.fspath(hardlink),
        sys_path=console_path,
    )
    assert (
        build_import_policy(
            provenance,
            runtime_state=hardlinked,
        ).import_environment.launcher_mode
        == "console_script"
    )
    linked_main = replace(
        hardlinked,
        modules=MappingProxyType(
            {"__main__": SimpleNamespace(__file__=os.fspath(symlink), __spec__=None)}
        ),
    )
    _assert_error(
        "launcher_not_regular",
        lambda: build_import_policy(provenance, runtime_state=linked_main),
    )


def test_actual_uv_console_launcher_builds_and_purges_its_parent_cache(
    provenance: InstalledProvenance,
) -> None:
    launcher = ROOT / ".venv/bin/laconian"
    assert launcher.is_file()
    state = _module_runtime(provenance)
    parent = os.fspath(launcher.parent)
    cached_parent = state.path_hooks[1](parent)
    console = replace(
        state,
        modules=MappingProxyType(
            {"__main__": SimpleNamespace(__file__=os.fspath(launcher), __spec__=None)}
        ),
        argv0=os.fspath(launcher),
        sys_path=(parent, *state.sys_path[1:]),
        importer_cache=MappingProxyType({parent: cached_parent}),
    )
    built = build_import_policy(provenance, runtime_state=console)
    assert built.import_environment.launcher_mode == "console_script"
    assert parent not in built.runtime_state.importer_cache


def test_console_launcher_null_cache_exception_is_exact_and_none_only(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    state = _module_runtime(provenance)
    launcher_key = os.path.realpath(os.path.abspath(launcher))
    console = replace(
        state,
        modules=MappingProxyType(
            {"__main__": SimpleNamespace(__file__=os.fspath(launcher), __spec__=None)}
        ),
        argv0=os.fspath(launcher),
        sys_path=(os.fspath(tmp_path), *state.sys_path[1:]),
        importer_cache=MappingProxyType({launcher_key: None}),
    )

    built = build_import_policy(provenance, runtime_state=console)
    assert built.import_environment.launcher_mode == "console_script"
    assert launcher_key not in built.runtime_state.importer_cache

    nearby = os.fspath(tmp_path / "not-the-launcher")
    _assert_error(
        "unknown_importer_cache_root",
        lambda: build_import_policy(
            provenance,
            runtime_state=replace(
                console,
                importer_cache=MappingProxyType({nearby: None}),
            ),
        ),
    )
    _assert_error(
        "unknown_importer_cache_finder",
        lambda: build_import_policy(
            provenance,
            runtime_state=replace(
                console,
                importer_cache=MappingProxyType({launcher_key: object()}),
            ),
        ),
    )


def test_console_multiprocessing_main_alias_is_identity_bound(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    state = _module_runtime(provenance)
    main = SimpleNamespace(__file__=os.fspath(launcher), __spec__=None)
    console_state = replace(
        state,
        modules=MappingProxyType(
            {
                "__main__": main,
                "__mp_main__": main,
                "sys": sys,
            }
        ),
        argv0=os.fspath(launcher),
        sys_path=(os.fspath(tmp_path), *state.sys_path[1:]),
    )

    policy = build_import_policy(provenance, runtime_state=console_state)
    assert policy.import_environment.launcher_mode == "console_script"

    _assert_error(
        "fixed_module_alias_changed",
        lambda: revalidate_loaded_modules(
            policy,
            modules={"__main__": main, "sys": sys},
        ),
    )
    _assert_error(
        "fixed_module_alias_changed",
        lambda: revalidate_loaded_modules(
            policy,
            modules={
                "__main__": main,
                "__mp_main__": SimpleNamespace(
                    __file__=os.fspath(launcher),
                    __spec__=None,
                ),
                "sys": sys,
            },
        ),
    )


def test_collections_abc_identity_alias_is_pinned_when_runtime_uses_it(
    policy: ImportPolicy,
) -> None:
    import _collections_abc
    import collections.abc

    if collections.abc is not _collections_abc:
        pytest.skip("runtime uses distinct collections.abc and _collections_abc modules")
    assert policy.fixed_alias_modules["collections.abc"] is _collections_abc
    forged = dict(sys.modules)
    forged["collections.abc"] = ModuleType("collections.abc")
    _assert_error(
        "fixed_module_alias_changed",
        lambda: revalidate_loaded_modules(policy, modules=MappingProxyType(forged)),
    )


def test_console_main_revalidation_rechecks_exact_launcher_bytes_in_place(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    initial_identity = launcher.stat()
    state = _module_runtime(provenance)
    main = SimpleNamespace(__file__=os.fspath(launcher), __spec__=None)
    console_state = replace(
        state,
        modules=MappingProxyType({"__main__": main, "sys": sys}),
        argv0=os.fspath(launcher),
        sys_path=(os.fspath(tmp_path), *state.sys_path[1:]),
    )
    console = build_import_policy(provenance, runtime_state=console_state)
    launcher.write_bytes(_launcher_bytes().replace(b"import sys\n", b"import os \n"))
    assert launcher.stat().st_ino == initial_identity.st_ino
    _assert_error(
        "launcher_template_mismatch",
        lambda: revalidate_loaded_modules(console, modules=console_state.modules),
    )


def test_console_main_revalidation_binds_original_launcher_file_identity(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    launcher = tmp_path / "laconian"
    launcher.write_bytes(_launcher_bytes())
    launcher.chmod(0o755)
    state = _module_runtime(provenance)
    main = SimpleNamespace(__file__=os.fspath(launcher), __spec__=None)
    console_state = replace(
        state,
        modules=MappingProxyType({"__main__": main, "sys": sys}),
        argv0=os.fspath(launcher),
        sys_path=(os.fspath(tmp_path), *state.sys_path[1:]),
    )
    console = build_import_policy(provenance, runtime_state=console_state)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(_launcher_bytes())
    replacement.chmod(0o755)
    os.replace(replacement, launcher)
    _assert_error(
        "launcher_identity_mismatch",
        lambda: revalidate_loaded_modules(console, modules=console_state.modules),
    )


def test_runner_console_entry_point_is_revalidated_not_trusted(
    provenance: InstalledProvenance,
) -> None:
    forged_distribution = replace(
        provenance.runner_distribution,
        entry_points_bytes=(
            b"[console_scripts]\n"
            b"laconian = laconian_eval.cli:entrypoint\n"
            b"extra = laconian_eval.cli:entrypoint\n"
        ),
    )
    forged = replace(provenance, runner_distribution=forged_distribution)
    _assert_error(
        "invalid_console_entry_point",
        lambda: build_import_policy(forged, runtime_state=_module_runtime(forged)),
    )


def test_virtualenv_bootstrap_digest_binds_exact_pth_and_module_bytes(
    provenance: InstalledProvenance,
    policy: ImportPolicy,
) -> None:
    site_root = provenance.runner_distribution._site_packages_root
    pth = (site_root / "_virtualenv.pth").read_bytes()
    module = (site_root / "_virtualenv.py").read_bytes()
    assert pth == b"import _virtualenv"
    assert policy.import_environment.virtualenv_bootstrap_sha256 == stable_digest(
        "laconian-import-bootstrap-v1",
        {"pth_sha256": sha256_bytes(pth), "module_sha256": sha256_bytes(module)},
    )


def test_import_environment_revalidation_rejects_forged_nested_models_content_free(
    policy: ImportPolicy,
) -> None:
    valid = policy.import_environment
    payload = {name: getattr(valid, name) for name in type(valid).model_fields}
    payload["import_roots"] = (
        ImportRootV1.model_construct(
            distribution="Packaging",
            module="../../host",
            origin_member="/sensitive/path.py",
        ),
    )
    forged = ImportEnvironmentV1.model_construct(**payload)
    _assert_error(
        "invalid_import_environment",
        lambda: revalidate_import_environment(policy, forged),
    )


def test_import_environment_revalidation_detects_fingerprint_drift(policy: ImportPolicy) -> None:
    payload = policy.import_environment.model_dump(mode="python")
    payload["guard_source_sha256"] = "f" * 64
    drifted = ImportEnvironmentV1.model_validate(payload)
    _assert_error(
        "import_environment_drift",
        lambda: revalidate_import_environment(policy, drifted),
    )


def test_loaded_module_revalidation_allows_owned_stdlib_builtin_and_frozen(
    policy: ImportPolicy,
    provenance: InstalledProvenance,
) -> None:
    import abc
    import json as stdlib_json

    runner_path = provenance.runner_source.origins["cli.py"].path
    runner_name = "laconian_eval.cli"
    runner = SimpleNamespace(
        __file__=os.fspath(runner_path),
        __spec__=importlib.machinery.ModuleSpec(
            runner_name,
            importlib.machinery.SourceFileLoader(runner_name, os.fspath(runner_path)),
            origin=os.fspath(runner_path),
        ),
    )
    revalidate_loaded_modules(
        policy,
        modules=_partial_module_map(
            policy, {"sys": sys, "stdlib_json": stdlib_json, runner_name: runner, "abc": abc}
        ),
    )


@pytest.mark.parametrize(
    ("module_key", "spec_name"),
    [
        ("laconian_eval.cli", None),
        ("laconian_eval.cli", "laconian_eval.not_cli"),
        ("laconian_eval.alias", "laconian_eval.cli"),
    ],
)
def test_loaded_owned_module_requires_exact_spec_name_and_module_key(
    policy: ImportPolicy,
    provenance: InstalledProvenance,
    module_key: str,
    spec_name: str | None,
) -> None:
    runner_path = provenance.runner_source.origins["cli.py"].path
    loader_name = "laconian_eval.cli" if spec_name is None else spec_name
    loader = importlib.machinery.SourceFileLoader(loader_name, os.fspath(runner_path))
    spec: object
    if spec_name is None:
        spec = SimpleNamespace(
            origin=os.fspath(runner_path),
            loader=loader,
            submodule_search_locations=None,
        )
    else:
        spec = importlib.machinery.ModuleSpec(
            spec_name,
            loader,
            origin=os.fspath(runner_path),
        )
    module = SimpleNamespace(__file__=os.fspath(runner_path), __spec__=spec)
    _assert_error(
        "import_origin_wrong_distribution",
        lambda: revalidate_loaded_modules(
            policy,
            modules=_partial_module_map(policy, {module_key: module}),
        ),
    )


def test_loaded_stdlib_origin_revalidates_descriptor_bound_root_identity(
    policy: ImportPolicy,
) -> None:
    import json as stdlib_json

    forged_identity = replace(
        policy.stdlib_root.identity,
        device=policy.stdlib_root.identity.device + 1,
    )
    forged = replace(
        policy,
        stdlib_root=replace(policy.stdlib_root, identity=forged_identity),
    )
    _assert_error(
        "import_root_identity_drift",
        lambda: revalidate_loaded_modules(
            forged,
            modules=_partial_module_map(forged, {"json": stdlib_json}),
        ),
    )


def test_loaded_module_revalidation_rejects_namespace_unowned_and_out_of_root(
    policy: ImportPolicy,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"VALUE = 1\n")
    namespace = SimpleNamespace(
        __file__=None,
        __spec__=SimpleNamespace(
            origin=None,
            loader=None,
            submodule_search_locations=[os.fspath(tmp_path)],
        ),
    )
    _assert_error(
        "namespace_import_unsupported",
        lambda: revalidate_loaded_modules(
            policy, modules=_partial_module_map(policy, {"namespace": namespace})
        ),
    )
    unowned = SimpleNamespace(
        __file__=os.fspath(outside),
        __spec__=SimpleNamespace(
            origin=os.fspath(outside),
            loader=importlib.machinery.SourceFileLoader("unowned", os.fspath(outside)),
            submodule_search_locations=None,
        ),
    )
    _assert_error(
        "import_origin_not_allowed",
        lambda: revalidate_loaded_modules(
            policy,
            modules=_partial_module_map(policy, {"unowned": unowned}),
        ),
    )


def test_unowned_origin_inside_allowed_site_root_is_rejected(policy: ImportPolicy) -> None:
    pytest_origin = Path(pytest.__file__)
    assert any(
        os.path.commonpath((os.fspath(root.canonical_path), os.fspath(pytest_origin)))
        == os.fspath(root.canonical_path)
        for root in policy.site_roots
    )
    _assert_error(
        "unowned_import_origin",
        lambda: revalidate_loaded_modules(
            policy,
            modules=_partial_module_map(policy, {"pytest_inside_allowed_site": pytest}),
        ),
    )


def test_captured_pyc_and_sourceless_loader_are_rejected_even_inside_runner_root(
    policy: ImportPolicy,
    provenance: InstalledProvenance,
) -> None:
    import py_compile

    source = provenance.runner_source.origins["cli.py"].path
    pyc = Path(importlib.util.cache_from_source(os.fspath(source)))
    py_compile.compile(os.fspath(source), doraise=True)
    assert pyc.is_file()
    sourceless = SimpleNamespace(
        __file__=os.fspath(pyc),
        __spec__=SimpleNamespace(
            origin=os.fspath(pyc),
            loader=importlib.machinery.SourcelessFileLoader("poison", os.fspath(pyc)),
            submodule_search_locations=None,
        ),
    )
    _assert_error(
        "captured_bytecode_unsupported",
        lambda: revalidate_loaded_modules(
            policy,
            modules=_partial_module_map(policy, {"poison": sourceless}),
        ),
    )


def test_module_spec_origin_and_file_must_identify_the_same_owned_file(
    policy: ImportPolicy,
    provenance: InstalledProvenance,
) -> None:
    spec_origin = provenance.runner_source.origins["__init__.py"].path
    file_origin = provenance.runner_source.origins["cli.py"].path
    disagreement = SimpleNamespace(
        __file__=os.fspath(file_origin),
        __spec__=SimpleNamespace(
            origin=os.fspath(spec_origin),
            loader=importlib.machinery.SourceFileLoader("laconian_eval", os.fspath(spec_origin)),
            submodule_search_locations=None,
        ),
    )
    _assert_error(
        "module_origin_mismatch",
        lambda: revalidate_loaded_modules(
            policy,
            modules=_partial_module_map(policy, {"laconian_eval": disagreement}),
        ),
    )


def test_loaded_dependency_source_and_destshared_extension_are_allowed(
    policy: ImportPolicy,
) -> None:
    import packaging.version

    extension_name = _destshared_extension_name(policy.destshared_root.canonical_path)
    extension_module = importlib.import_module(extension_name)
    extension_path = Path(extension_module.__file__).resolve()
    assert extension_path.is_relative_to(policy.destshared_root.canonical_path)
    revalidate_loaded_modules(
        policy,
        modules=_partial_module_map(
            policy, {"packaging.version": packaging.version, extension_name: extension_module}
        ),
    )


def test_forged_captured_member_bytes_and_identity_are_rejected(
    provenance: InstalledProvenance,
) -> None:
    runner = provenance.runner_source
    changed_bytes = dict(runner.file_bytes)
    changed_bytes["capsule/import_policy.py"] += b"# forged\n"
    forged_bytes = replace(runner, file_bytes=MappingProxyType(changed_bytes))
    bytes_provenance = replace(provenance, runner_source=forged_bytes)
    _assert_error(
        "runner_capture_mismatch",
        lambda: build_import_policy(
            bytes_provenance,
            runtime_state=_module_runtime(bytes_provenance),
        ),
    )

    changed_origins = dict(runner.origins)
    original = changed_origins["__init__.py"]
    changed_origins["__init__.py"] = replace(
        original,
        identity=replace(original.identity, size=original.identity.size + 1),
    )
    forged_identity = replace(runner, origins=MappingProxyType(changed_origins))
    identity_provenance = replace(provenance, runner_source=forged_identity)
    _assert_error(
        "captured_origin_changed",
        lambda: build_import_policy(
            identity_provenance,
            runtime_state=_module_runtime(identity_provenance),
        ),
    )


def test_loaded_main_is_validated_before_bootstrap_mutation(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    state = _module_runtime(provenance)
    outside = tmp_path / "main.py"
    outside.write_bytes(b"")
    main = SimpleNamespace(__file__=os.fspath(outside), __spec__=None)
    changed = replace(state, modules=MappingProxyType({"__main__": main, "sys": sys}))
    before = tuple(sys.path)
    _assert_error(
        "invalid_module_main",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )
    assert tuple(sys.path) == before


@pytest.mark.parametrize(
    ("origin", "loader"),
    [
        ("built-in", importlib.machinery.FrozenImporter),
        ("frozen", importlib.machinery.BuiltinImporter),
        ("built-in", object()),
        ("frozen", object()),
        (None, importlib.machinery.BuiltinImporter),
        (None, importlib.machinery.FrozenImporter),
    ],
)
def test_loaded_builtin_and_frozen_claims_require_consistent_fixed_pairs(
    policy: ImportPolicy,
    origin: str | None,
    loader: object,
) -> None:
    forged = SimpleNamespace(
        __file__=None,
        __spec__=SimpleNamespace(
            name="forged_runtime_module",
            origin=origin,
            loader=loader,
            submodule_search_locations=None,
        ),
    )
    _assert_error(
        "builtin_frozen_mismatch",
        lambda: revalidate_loaded_modules(
            policy,
            modules=_partial_module_map(policy, {"forged_runtime_module": forged}),
        ),
    )


@pytest.mark.parametrize(
    ("origin", "loader"),
    [
        ("built-in", importlib.machinery.BuiltinImporter),
        ("frozen", importlib.machinery.FrozenImporter),
    ],
)
def test_consistent_looking_fixed_module_spec_must_resolve_through_fixed_finder(
    policy: ImportPolicy,
    origin: str,
    loader: object,
) -> None:
    forged = SimpleNamespace(
        __file__=None,
        __spec__=importlib.machinery.ModuleSpec(
            "forged_runtime_module",
            loader,
            origin=origin,
        ),
    )
    _assert_error(
        "builtin_frozen_mismatch",
        lambda: revalidate_loaded_modules(
            policy,
            modules=_partial_module_map(policy, {"forged_runtime_module": forged}),
        ),
    )


def test_guard_resolves_only_fixed_finders_and_rejects_namespace_specs(
    policy: ImportPolicy,
) -> None:
    def namespace_spec(*_: object, **__: object) -> importlib.machinery.ModuleSpec:
        spec = importlib.machinery.ModuleSpec("synthetic_namespace", loader=None, origin=None)
        spec.submodule_search_locations = []
        return spec

    guard = _LaconianImportGuard(policy, path_find_spec=namespace_spec)
    _assert_error(
        "namespace_import_unsupported",
        lambda: guard.find_spec("synthetic_namespace", None, None),
    )


def test_uninstalled_guard_rejects_injected_outside_spec_before_loader_actions(
    policy: ImportPolicy,
    tmp_path: Path,
) -> None:
    side_effects: list[str] = []

    class SideEffectLoader:
        def create_module(self, spec: object) -> None:
            side_effects.append("create")
            return None

        def exec_module(self, module: object) -> None:
            side_effects.append("exec")

    outside = tmp_path / "outside.py"
    outside.write_bytes(b"SIDE_EFFECT = True\n")
    spec = importlib.machinery.ModuleSpec(
        "synthetic_outside",
        SideEffectLoader(),
        origin=os.fspath(outside),
    )
    guard = _LaconianImportGuard(policy, path_find_spec=lambda *_: spec)
    _assert_error(
        "import_origin_not_allowed",
        lambda: guard.find_spec("synthetic_outside", None, None),
    )
    assert side_effects == []


def test_guard_wraps_independently_returned_owned_spec_before_loader_can_execute(
    policy: ImportPolicy,
    provenance: InstalledProvenance,
) -> None:
    executed: list[str] = []

    class AmbientSpyLoader:
        def create_module(self, spec: object) -> None:
            return None

        def exec_module(self, module: ModuleType) -> None:
            executed.append("ambient")
            module.__dict__["__version__"] = "poison"

    origin = provenance.runner_source.origins["__init__.py"].path
    ambient = AmbientSpyLoader()
    supplied = importlib.machinery.ModuleSpec(
        "laconian_eval",
        ambient,
        origin=os.fspath(origin),
    )

    def supplied_spec(*_: object, **__: object) -> importlib.machinery.ModuleSpec:
        return supplied

    guarded = _LaconianImportGuard(policy, path_find_spec=supplied_spec).find_spec(
        "laconian_eval", None, None
    )
    assert guarded is supplied
    assert isinstance(guarded.loader, _OriginValidatingLoader)
    assert guarded.loader.ambient_loader is ambient
    assert guarded.loader.create_module(guarded) is None
    assert executed == []
    module = ModuleType("laconian_eval")
    module.__spec__ = guarded
    guarded.loader.exec_module(module)
    assert executed == []
    assert module.__version__ == "0.1.0.dev0"  # type: ignore[attr-defined]


def test_guard_rejects_custom_loader_for_owned_native_extension(
    policy: ImportPolicy,
) -> None:
    side_effects: list[str] = []

    class CustomLoader:
        def create_module(self, spec: object) -> None:
            side_effects.append("create")
            return None

        def exec_module(self, module: object) -> None:
            side_effects.append("exec")

    owned = next(
        item
        for item in policy.owned_origins.values()
        if item.captured_source is None
        and any(
            item.canonical_path.name.endswith(suffix)
            for suffix in importlib.machinery.EXTENSION_SUFFIXES
        )
    )
    spec = importlib.machinery.ModuleSpec(
        owned.module_name,
        CustomLoader(),
        origin=os.fspath(owned.canonical_path),
    )
    guard = _LaconianImportGuard(policy, path_find_spec=lambda *_: spec)
    _assert_error(
        "invalid_import_loader",
        lambda: guard.find_spec(owned.module_name, None, None),
    )
    assert side_effects == []


def test_captured_source_loader_executes_captured_bytes_not_poisoned_pyc(tmp_path: Path) -> None:
    import py_compile

    poison_source = tmp_path / "poison.py"
    poison_source.write_bytes(b"VALUE = 'poisoned-pyc'\n")
    pyc = tmp_path / "owned.pyc"
    py_compile.compile(os.fspath(poison_source), cfile=os.fspath(pyc), doraise=True)
    ambient = importlib.machinery.SourcelessFileLoader("owned", os.fspath(pyc))

    checks: list[str] = []

    def validate() -> None:
        checks.append("checked")

    loader = _OriginValidatingLoader(
        ambient,
        validate=validate,
        captured_source=b"VALUE = 'captured'\n",
        display_origin="<captured>",
        post_validate=validate,
    )
    module = ModuleType("owned")
    loader.exec_module(module)
    assert module.VALUE == "captured"  # type: ignore[attr-defined]
    assert checks == ["checked", "checked"]


def test_extension_loader_checks_identity_before_and_after_exec(tmp_path: Path) -> None:
    extension = tmp_path / "owned.so"
    extension.write_bytes(b"stable")
    expected = extension.stat()
    calls: list[str] = []

    class MutatingLoader:
        def create_module(self, spec: object) -> None:
            return None

        def exec_module(self, module: ModuleType) -> None:
            calls.append("exec")
            extension.write_bytes(b"changed")

    def validate() -> None:
        current = extension.stat()
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
            expected.st_dev,
            expected.st_ino,
            expected.st_size,
            expected.st_mtime_ns,
        ):
            raise ImportPolicyError("import_origin_changed")

    loader = _OriginValidatingLoader(
        MutatingLoader(),
        validate=validate,
        captured_source=None,
        display_origin="<extension>",
        post_validate=validate,
    )
    _assert_error("import_origin_changed", lambda: loader.exec_module(ModuleType("owned_ext")))
    assert calls == ["exec"]


def test_full_state_revalidation_detects_every_fixed_component_drift(
    policy: ImportPolicy,
) -> None:
    base = policy.runtime_state
    path_drift = replace(base, sys_path=(*base.sys_path, "/unknown"))
    _assert_error(
        "sys_path_drift",
        lambda: revalidate_import_state(
            policy,
            runtime_state=path_drift,
            require_guard=False,
        ),
    )

    assert len(base.meta_path) >= 3
    reordered_meta = replace(
        base,
        meta_path=(base.meta_path[0], base.meta_path[2], base.meta_path[1], *base.meta_path[3:]),
    )
    _assert_error(
        "meta_path_drift",
        lambda: revalidate_import_state(
            policy,
            runtime_state=reordered_meta,
            require_guard=False,
        ),
    )
    substituted_meta = replace(base, meta_path=(*base.meta_path[:-1], object()))
    _assert_error(
        "meta_path_drift",
        lambda: revalidate_import_state(
            policy,
            runtime_state=substituted_meta,
            require_guard=False,
        ),
    )

    reordered_hooks = replace(base, path_hooks=tuple(reversed(base.path_hooks)))
    _assert_error(
        "path_hooks_drift",
        lambda: revalidate_import_state(
            policy,
            runtime_state=reordered_hooks,
            require_guard=False,
        ),
    )
    substituted_hooks = replace(base, path_hooks=(base.path_hooks[0], lambda _: None))
    _assert_error(
        "path_hooks_drift",
        lambda: revalidate_import_state(
            policy,
            runtime_state=substituted_hooks,
            require_guard=False,
        ),
    )

    cache_items = list(base.importer_cache.items())
    assert cache_items
    key, value = cache_items[0]
    replacement = None if value is not None else object()
    replaced_cache = dict(cache_items)
    replaced_cache[key] = replacement
    cache_drift = replace(base, importer_cache=MappingProxyType(replaced_cache))
    _assert_error(
        "importer_cache_drift",
        lambda: revalidate_import_state(
            policy,
            runtime_state=cache_drift,
            require_guard=False,
        ),
    )


def test_zipimporter_cache_value_is_rejected_even_for_an_allowed_key(
    provenance: InstalledProvenance,
    tmp_path: Path,
) -> None:
    import zipfile

    archive = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("payload.py", "SIDE_EFFECT = True\n")
    importer = zipimport.zipimporter(os.fspath(archive))
    state = _module_runtime(provenance)
    allowed_key = os.fspath(Path(sysconfig.get_path("stdlib")))
    changed = replace(
        state,
        importer_cache=MappingProxyType({allowed_key: importer}),
    )
    _assert_error(
        "zip_importer_unsupported",
        lambda: build_import_policy(provenance, runtime_state=changed),
    )


def test_construction_does_not_import_openai_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []
    original = __import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> Any:
        if name == "openai" or name.startswith("openai."):
            imported.append(name)
            raise AssertionError("OpenAI SDK imported during import-policy construction")
        return original(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    provenance = _installed_provenance(provider_kind="openai")
    build_import_policy(provenance, runtime_state=_module_runtime(provenance))
    assert imported == []


def test_runtime_state_and_policy_models_are_closed_to_mutation(policy: ImportPolicy) -> None:
    with pytest.raises((AttributeError, TypeError)):
        policy.runtime_state.modules["evil"] = ModuleType("evil")  # type: ignore[index]
    with pytest.raises(ValidationError):
        ImportEnvironmentV1.model_validate(
            {**policy.import_environment.model_dump(mode="python"), "unknown": "field"}
        )
