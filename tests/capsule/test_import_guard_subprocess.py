from __future__ import annotations

import importlib.machinery
import json
import subprocess
import sys
import sysconfig
import typing
from pathlib import Path

import pytest

from laconian_eval.capsule.import_policy import CONSOLE_LAUNCHER_TEMPLATE

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


_PROVENANCE_SETUP = r"""
import importlib.machinery
import importlib.metadata
import os
import sys
from pathlib import Path

from laconian_eval.capsule.import_policy import (
    ImportPolicyError,
    build_import_policy,
    install_import_guard,
    revalidate_import_state,
    revalidate_loaded_modules,
)
from laconian_eval.capsule.provenance import (
    InstalledProvenance,
    _capture_runner_distribution,
    capture_dependency_closure,
    capture_runner_source,
)
from laconian_eval.capsule.record_models import UvLockV1

provider_kind = "__PROVIDER_KIND__"
runner = capture_runner_source()
provenance = InstalledProvenance(
    runner_source=runner,
    runner_distribution=_capture_runner_distribution(),
    dependencies=capture_dependency_closure(provider_kind=provider_kind),
    package_version="0.1.0a1",
    checkout_binding="unavailable",
    git_commit=None,
    git_state="unavailable",
    uv_lock=UvLockV1.model_validate({"availability": "unavailable", "sha256": None}),
    provider_kind=provider_kind,
    requested_model="fixture-v1",
    adapter_source_sha256="0" * 64,
    transport_policy="openai-direct-v1" if provider_kind == "openai" else "offline",
    sdk_distribution="openai" if provider_kind == "openai" else None,
    sdk_version=importlib.metadata.version("openai") if provider_kind == "openai" else None,
    container_image_digest=None,
    python_implementation="CPython",
    python_version=sys.version,
    os_family="Darwin",
    os_release="test",
    architecture="arm64",
)
sys.modules["__main__"].__file__ = os.fspath(runner.origins["capsule/import_policy.py"].path)
policy = build_import_policy(provenance)
"""


def _run_child(
    body: str,
    *,
    provider_kind: str = "fake",
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    setup = _PROVENANCE_SETUP.replace("__PROVIDER_KIND__", provider_kind)
    return subprocess.run(
        [sys.executable, "-c", setup + body],
        cwd=ROOT,
        env={},
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


_PUBLIC_RESUME_CHILD = r"""
import json
import os
import sys
from pathlib import Path

from laconian_eval.capsule.execution import ProviderFactory, resume_capsule

capsule = Path(sys.argv[1])
action = sys.argv[2]
launcher = Path(sys.executable).with_name("laconian").resolve()

# A ``python -c`` subprocess gives the test a trace hook without changing the owned
# production API.  Present the same verified console-launcher identity and import root
# that the public ``laconian plan`` process captured.
sys.argv[0] = os.fspath(launcher)
sys.modules["__main__"].__file__ = os.fspath(launcher)
sys.modules["__main__"].__spec__ = None
sys.path[0] = os.fspath(launcher.parent)
sys.path_importer_cache.pop(os.fspath(Path.cwd()), None)

observed = {"triggered": 0, "lazy_loaded": None}
cache_key = "/synthetic/laconian-import-guard-drift"
assert cache_key not in sys.path_importer_cache

def at_execution_checkpoint(frame, event, arg):
    del arg
    if (
        event == "call"
        and frame.f_code.co_name == "_complete_execution_checkpoint"
        and frame.f_globals.get("__name__") == "laconian_eval.capsule.execution"
        and observed["triggered"] == 0
    ):
        observed["triggered"] = 1
        if action == "lazy_import":
            lazy = __import__("annotated_types.test_cases", fromlist=("test_cases",))
            observed["lazy_loaded"] = lazy.__name__
        elif action == "sys_path":
            sys.path.append("/synthetic/outside")
        elif action == "meta_path":
            sys.meta_path.append(object())
        elif action == "path_hooks":
            sys.path_hooks.append(lambda _value: None)
        elif action == "importer_cache":
            sys.path_importer_cache[cache_key] = None
        else:
            raise AssertionError(action)
    return at_execution_checkpoint

assert "annotated_types.test_cases" not in sys.modules
sys.settrace(at_execution_checkpoint)
try:
    result = resume_capsule(capsule, provider_factory=ProviderFactory())
finally:
    sys.settrace(None)

# Restore the deliberately drifted surface so the still-installed audit hook permits
# the diagnostic serialization below.  The checkpoint already observed the drift.
if observed["triggered"] and action == "sys_path":
    assert sys.path.pop() == "/synthetic/outside"
elif observed["triggered"] and action == "meta_path":
    sys.meta_path.pop()
elif observed["triggered"] and action == "path_hooks":
    sys.path_hooks.pop()
elif observed["triggered"] and action == "importer_cache":
    del sys.path_importer_cache[cache_key]

events = [json.loads(row)["kind"] for row in (capsule / "events.jsonl").read_bytes().splitlines()]
raw_rows = (capsule / "raw.jsonl").read_bytes().splitlines()
os.write(1, (json.dumps({
    "result": result.model_dump(mode="json"),
    "triggered": observed["triggered"],
    "lazy_loaded": observed["lazy_loaded"],
    "events": events,
    "raw_rows": len(raw_rows),
}) + "\n").encode())
"""


_PUBLIC_PLAN_CHILD = r"""
import json
import os
import sys
from pathlib import Path

from laconian_eval.cli import main

launcher = Path(sys.executable).with_name("laconian").resolve()
sys.argv[0] = os.fspath(launcher)
sys.modules["__main__"].__file__ = os.fspath(launcher)
sys.modules["__main__"].__spec__ = None
sys.path[0] = os.fspath(launcher.parent)
sys.path_importer_cache.pop(os.fspath(Path.cwd()), None)
raise SystemExit(main([
    "plan",
    sys.argv[1],
    "--results-root",
    sys.argv[2],
    "--input-root",
    sys.argv[3],
    "--source-root",
    sys.argv[4],
]))
"""


@pytest.fixture(scope="module")
def public_resume_inputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    workspace = tmp_path_factory.mktemp("public-import-guard-resume")
    input_root = workspace / "inputs"
    cases_root = input_root / "cases"
    cases_root.mkdir(parents=True)
    (cases_root / "response.yaml").write_text(
        """schema_version: "1"
kind: response
cases:
  - id: public-import-guard-en
    scenario_id: public-import-guard
    locale: en
    category: direct
    prompt: Answer briefly.
  - id: public-import-guard-ru
    scenario_id: public-import-guard
    locale: ru
    category: direct
    prompt: Ответьте кратко.
""",
        encoding="utf-8",
    )
    manifest = input_root / "manifest.yaml"
    manifest.write_text(
        """schema_version: "2"
runner_version: 0.1.0a1
run_name: public-import-guard
provider:
  kind: fake
  model: fixture-v1
case_files:
  - cases/response.yaml
arms:
  - baseline
repetitions: 1
arm_order_seed: 17
instruction_placement: system_suffix
generation:
  max_output_tokens: 128
  temperature: null
retry:
  max_transient_retries: 0
  timeout_seconds: 5
price_snapshot: null
capsule:
  run_purpose: integration_smoke
  claim_intent: none
  datasets:
    - dataset_id: public-import-guard
      dataset_version: fixture-v1
      role: smoke
      case_schema_version: "1"
      case_file_ordinals:
        - 0
  comparisons: []
  protocol_bindings: []
""",
        encoding="utf-8",
    )
    return manifest, input_root


def _run_public_resume(
    inputs: tuple[Path, Path],
    tmp_path: Path,
    action: str,
) -> dict[str, object]:
    manifest, input_root = inputs
    results_root = tmp_path / "results"
    results_root.mkdir()
    planned = subprocess.run(
        [
            sys.executable,
            "-c",
            _PUBLIC_PLAN_CHILD,
            str(manifest),
            str(results_root),
            str(input_root),
            str(ROOT),
        ],
        cwd=ROOT,
        env={},
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert planned.returncode == 0, planned.stderr
    capsule = Path(planned.stdout.splitlines()[0])
    assert capsule.is_absolute()
    assert capsule.is_dir()
    completed = subprocess.run(
        [sys.executable, "-c", _PUBLIC_RESUME_CHILD, str(capsule), action],
        cwd=ROOT,
        env={},
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_guard_installation_self_test_proves_audit_observed_and_guard_blocked() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
print(__import__("json").dumps({
    "audit_events": installation.audit_hook.import_events,
    "sentinel_audit_observed": installation.sentinel_audit_observed,
    "sentinel_guard_blocked": installation.sentinel_guard_blocked,
    "guard_first": sys.meta_path[0] is installation.guard,
}))
"""
    )
    payload = _payload(result)
    assert payload["audit_events"] >= 1  # type: ignore[operator]
    assert payload["sentinel_audit_observed"] is True
    assert payload["sentinel_guard_blocked"] is True
    assert payload["guard_first"] is True


@pytest.mark.parametrize(
    "tamper",
    [
        "setattr(guard, 'policy', object())",
        "setattr(guard.policy, 'path_finder', object())",
        "setattr(guard.policy._audit_hook, 'armed', False)",
    ],
)
def test_installed_guard_reachable_security_state_is_sealed(tamper: str) -> None:
    result = _run_child(
        rf"""
installation = install_import_guard(policy)
guard = sys.meta_path[0]
try:
    {tamper}
except (AttributeError, TypeError):
    os.write(1, b"SEALED\n")
else:
    os.write(1, b"MUTABLE\n")
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SEALED"


@pytest.mark.parametrize(
    "corruption",
    [
        'object.__setattr__(guard, "_LaconianImportGuard__installed", False)',
        'object.__setattr__(guard, "_LaconianImportGuard__sentinel_name", "_changed")',
        'object.__setattr__(guard, "_LaconianImportGuard__snapshot", object())',
        (
            'object.__setattr__(guard_snapshot, "path_find_spec", '
            "lambda fullname, path, target: side_effects.append(fullname))"
        ),
    ],
)
def test_independent_audit_snapshot_rejects_force_corrupted_guard(
    corruption: str,
) -> None:
    result = _run_child(
        rf"""
installation = install_import_guard(policy)
guard = sys.meta_path[0]
guard_snapshot = object.__getattribute__(guard, "_LaconianImportGuard__snapshot")
side_effects = []
{corruption}
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_integrity_drift:0"


def test_force_corrupting_build_policy_cannot_weaken_independent_audit_snapshot() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
object.__setattr__(policy, "runtime_state", policy.initial_state)
object.__setattr__(policy, "enforcement_token", object())
sys.path.append("/synthetic/outside")
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sys_path_drift"


def test_registered_audit_hook_does_not_resolve_mutable_validator_global() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
policy_module = sys.modules["laconian_eval.capsule.import_policy"]
policy_module._check_live_fixed_state = lambda *args, **kwargs: None
side_effects = []
class SideEffectFinder:
    @staticmethod
    def find_spec(fullname, path=None, target=None):
        side_effects.append(fullname)
        return None
sys.meta_path.pop(0)
sys.meta_path.insert(0, SideEffectFinder())
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
except ModuleNotFoundError:
    outcome = "module_not_found"
else:
    outcome = "imported"
os.write(1, (outcome + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_order_drift:0"


def test_guard_and_returned_status_expose_no_audit_callback_or_shared_snapshot() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
guard = sys.meta_path[0]
ordinary_backrefs = any(
    hasattr(value, attribute)
    for value in (guard, installation.audit_hook)
    for attribute in ("policy", "audit_hook", "snapshot", "callback", "armed")
)
os.write(1, (("EXPOSED" if ordinary_backrefs else "SEALED") + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "SEALED"


def test_guard_allows_lazy_owned_import_without_growing_frozen_cache() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
before = tuple(sys.path_importer_cache.items())
import annotated_types.test_cases as lazy_owned
after = tuple(sys.path_importer_cache.items())
revalidate_import_state(policy)
revalidate_loaded_modules(policy)
os.write(1, (__import__("json").dumps({
    "loaded": lazy_owned.__name__,
    "cache_same": len(before) == len(after) and all(
        left_key == right_key and left_value is right_value
        for (left_key, left_value), (right_key, right_value) in zip(before, after, strict=True)
    ),
}) + "\n").encode())
"""
    )
    payload = _payload(result)
    assert payload == {"loaded": "annotated_types.test_cases", "cache_same": True}


def test_guard_preserves_normal_module_not_found_for_optional_missing_import() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
probe_name = "_laconian_intentionally_missing_optional_module"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ModuleNotFoundError as error:
    os.write(1, (type(error).__name__ + "\n").encode())
except ImportPolicyError as error:
    os.write(1, ("POLICY:" + error.code + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ModuleNotFoundError"


@pytest.mark.parametrize("path_value", ["outside", "pathlike"])
def test_guard_rejects_unfrozen_package_search_path_before_path_hooks(
    path_value: str,
) -> None:
    result = _run_child(
        rf"""
installation = install_import_guard(policy)
import annotated_types
original_path = annotated_types.__path__
side_effects = []
class EvilPath:
    def __hash__(self):
        return 1
    def __fspath__(self):
        side_effects.append("fspath")
        return "/synthetic/outside"
annotated_types.__path__ = [
    "/synthetic/outside" if {path_value!r} == "outside" else EvilPath()
]
before = tuple(sys.path_importer_cache.items())
probe_name = "annotated_types._laconian_missing_path_probe"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    annotated_types.__path__ = original_path
    after = tuple(sys.path_importer_cache.items())
    unchanged = len(before) == len(after) and all(
        left_key == right_key and left_value is right_value
        for (left_key, left_value), (right_key, right_value) in zip(before, after, strict=True)
    )
    os.write(1, (
        error.code + ":" + str(len(side_effects)) + ":" + str(unchanged) + "\n"
    ).encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "import_path_not_allowed:0:True"


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    [
        ("sys.meta_path.pop(0)", "guard_order_drift"),
        ("sys.meta_path.insert(0, object())", "guard_order_drift"),
        ("sys.path.append('/synthetic/outside')", "sys_path_drift"),
        ("sys.path_hooks.append(lambda value: None)", "path_hooks_drift"),
        ("sys.path_importer_cache['/synthetic/outside'] = None", "importer_cache_drift"),
    ],
)
def test_immutable_audit_hook_blocks_import_after_state_tampering(
    tamper: str,
    expected_code: str,
) -> None:
    result = _run_child(
        rf"""
installation = install_import_guard(policy)
{tamper}
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + "\n").encode())
else:
    os.write(1, b"IMPORT_UNEXPECTEDLY_SUCCEEDED\n")
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected_code


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    [
        (
            """
builtin_index = sys.meta_path.index(importlib.machinery.BuiltinImporter)
frozen_index = sys.meta_path.index(importlib.machinery.FrozenImporter)
sys.meta_path[builtin_index], sys.meta_path[frozen_index] = (
    sys.meta_path[frozen_index],
    sys.meta_path[builtin_index],
)
""",
            "guard_order_drift",
        ),
        (
            """
pathfinder_index = sys.meta_path.index(importlib.machinery.PathFinder)
sys.meta_path[pathfinder_index] = object()
""",
            "guard_order_drift",
        ),
        ("sys.path_hooks.reverse()", "path_hooks_drift"),
        (
            """
cache_key = next(iter(sys.path_importer_cache))
old_cache_value = sys.path_importer_cache[cache_key]
sys.path_importer_cache[cache_key] = None if old_cache_value is not None else object()
""",
            "importer_cache_drift",
        ),
    ],
)
def test_audit_hook_checks_internal_fixed_identities_while_guard_remains_first(
    tamper: str,
    expected_code: str,
) -> None:
    result = _run_child(
        rf"""
installation = install_import_guard(policy)
assert sys.meta_path[0] is installation.guard
{tamper}
assert sys.meta_path[0] is installation.guard
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + "\n").encode())
else:
    os.write(1, b"IMPORT_UNEXPECTEDLY_SUCCEEDED\n")
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected_code


def test_guard_rejects_synthetic_out_of_policy_origin_before_loader_execution() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
executed = False
try:
    __import__(installation.sentinel_name)
except ImportPolicyError as error:
    os.write(1, (__import__("json").dumps({
        "code": error.code,
        "executed": executed,
        "guard_blocks": installation.guard.sentinel_blocks,
    }) + "\n").encode())
"""
    )
    payload = _payload(result)
    assert payload["code"] == "import_origin_not_allowed"
    assert payload["executed"] is False
    assert payload["guard_blocks"] >= 2  # type: ignore[operator]


def test_guard_blocks_mutated_pathfinder_before_loader_side_effect() -> None:
    result = _run_child(
        r"""
side_effects = []
class SideEffectLoader:
    def create_module(self, spec):
        side_effects.append("create")
        return None
    def exec_module(self, module):
        side_effects.append("exec")

probe_name = "_laconian_external_loader_probe"
assert probe_name not in sys.modules
installation = install_import_guard(policy)
original_find_spec = importlib.machinery.PathFinder.find_spec
def synthetic_find_spec(fullname, path=None, target=None):
    if fullname == probe_name:
        return importlib.machinery.ModuleSpec(
            fullname,
            SideEffectLoader(),
            origin="/synthetic/outside.py",
        )
    return original_find_spec(fullname, path, target)
importlib.machinery.PathFinder.find_spec = synthetic_find_spec
try:
    __import__(probe_name)
except ImportPolicyError as error:
    importlib.machinery.PathFinder.find_spec = original_find_spec
    os.write(1, (__import__("json").dumps({
        "code": error.code,
        "side_effects": side_effects,
    }) + "\n").encode())
"""
    )
    payload = _payload(result)
    assert payload == {"code": "meta_path_finder_drift", "side_effects": []}


def test_audit_rejects_pathfinder_callable_drift_before_tampered_finder_runs() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
side_effects = []
probe_name = "_laconian_tampered_pathfinder_probe"
assert probe_name not in sys.modules
original_descriptor = importlib.machinery.PathFinder.__dict__["find_spec"]
def tampered_find_spec(cls, fullname, path=None, target=None):
    side_effects.append(fullname)
    return None
importlib.machinery.PathFinder.find_spec = classmethod(tampered_find_spec)
try:
    __import__(probe_name)
except ImportPolicyError as error:
    importlib.machinery.PathFinder.find_spec = original_descriptor
    os.write(1, ((error.code + ":" + str(len(side_effects))) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "meta_path_finder_drift:0"


def test_audit_rejects_in_place_pathfinder_code_drift_before_execution() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
probe_name = "_laconian_pathfinder_code_drift_probe"
assert probe_name not in sys.modules
finder_function = importlib.machinery.PathFinder.__dict__["find_spec"].__func__
original_code = finder_function.__code__
def tampered_find_spec(cls, fullname, path=None, target=None):
    cls._laconian_probe_side_effect = fullname
    return None
finder_function.__code__ = tampered_find_spec.__code__
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
except ModuleNotFoundError:
    outcome = "module_not_found"
else:
    outcome = "imported"
side_effect = int(
    getattr(importlib.machinery.PathFinder, "_laconian_probe_side_effect", None)
    == probe_name
)
finder_function.__code__ = original_code
os.write(1, (outcome + ":" + str(side_effect) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "meta_path_finder_drift:0"


def test_audit_rejects_guard_find_spec_descriptor_replacement_before_execution() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
guard_type = type(installation.guard)
original = guard_type.__dict__["find_spec"]
side_effects = []
def tampered_find_spec(self, fullname, path=None, target=None):
    side_effects.append(fullname)
    return None
guard_type.find_spec = tampered_find_spec
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
except ModuleNotFoundError:
    outcome = "module_not_found"
else:
    outcome = "imported"
guard_type.find_spec = original
os.write(1, (outcome + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


def test_audit_rejects_in_place_guard_method_code_drift_before_execution() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
guard_type = type(installation.guard)
guard_function = guard_type.__dict__["find_spec"]
original_code = guard_function.__code__
def tampered_find_spec(self, fullname, path=None, target=None):
    type(self)._laconian_guard_method_side_effect = fullname
    return None
guard_function.__code__ = tampered_find_spec.__code__
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
except ModuleNotFoundError:
    outcome = "module_not_found"
else:
    outcome = "imported"
side_effect = int(
    getattr(guard_type, "_laconian_guard_method_side_effect", None) == probe_name
)
guard_function.__code__ = original_code
os.write(1, (outcome + ":" + str(side_effect) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


def test_audit_rejects_guard_module_global_callable_rebinding_before_use() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
policy_module = sys.modules["laconian_eval.capsule.import_policy"]
original = policy_module._validated_origin
side_effects = []
def tampered_validated_origin(*args, **kwargs):
    side_effects.append("validated")
    return original(*args, **kwargs)
policy_module._validated_origin = tampered_validated_origin
probe_name = "annotated_types.test_cases"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
policy_module._validated_origin = original
os.write(1, (outcome + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


@pytest.mark.parametrize("method_name", ["create_module", "exec_module"])
def test_audit_rejects_proxy_loader_descriptor_replacement_before_execution(
    method_name: str,
) -> None:
    replacement = {
        "create_module": """
def tampered_proxy_method(self, spec):
    side_effects.append(spec.name)
    return None
""",
        "exec_module": """
def tampered_proxy_method(self, module):
    side_effects.append(module.__name__)
""",
    }[method_name]
    result = _run_child(
        f"""
installation = install_import_guard(policy)
policy_module = sys.modules["laconian_eval.capsule.import_policy"]
proxy_type = policy_module._OriginValidatingLoader
original = proxy_type.__dict__[{method_name!r}]
side_effects = []
{replacement}
setattr(proxy_type, {method_name!r}, tampered_proxy_method)
probe_name = "annotated_types.test_cases"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
setattr(proxy_type, {method_name!r}, original)
os.write(1, (outcome + ":" + str(len(side_effects)) + "\\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


@pytest.mark.parametrize("method_name", ["create_module", "exec_module"])
def test_audit_rejects_in_place_proxy_loader_method_code_drift(
    method_name: str,
) -> None:
    replacement = {
        "create_module": """
def tampered_proxy_method(self, spec):
    type(self)._laconian_proxy_method_side_effect = spec.name
    return None
""",
        "exec_module": """
def tampered_proxy_method(self, module):
    type(self)._laconian_proxy_method_side_effect = module.__name__
""",
    }[method_name]
    result = _run_child(
        f"""
installation = install_import_guard(policy)
policy_module = sys.modules["laconian_eval.capsule.import_policy"]
proxy_type = policy_module._OriginValidatingLoader
proxy_function = proxy_type.__dict__[{method_name!r}]
original_code = proxy_function.__code__
{replacement}
proxy_function.__code__ = tampered_proxy_method.__code__
probe_name = "annotated_types.test_cases"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
side_effect = int(
    getattr(proxy_type, "_laconian_proxy_method_side_effect", None) == probe_name
)
proxy_function.__code__ = original_code
os.write(1, (outcome + ":" + str(side_effect) + "\\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


def test_audit_rejects_guard_getattribute_replacement_before_dispatch() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
guard_type = type(installation.guard)
side_effects = []
def tampered_getattribute(self, name):
    side_effects.append(name)
    return object.__getattribute__(self, name)
guard_type.__getattribute__ = tampered_getattribute
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
del guard_type.__getattribute__
os.write(1, (outcome + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


@pytest.mark.parametrize("surface", ["guard", "proxy"])
def test_audit_rejects_inert_extra_class_attribute(surface: str) -> None:
    result = _run_child(
        f"""
installation = install_import_guard(policy)
policy_module = sys.modules["laconian_eval.capsule.import_policy"]
surface_type = (
    type(installation.guard)
    if {surface!r} == "guard"
    else policy_module._OriginValidatingLoader
)
surface_type._laconian_inert_extra = object()
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
del surface_type._laconian_inert_extra
os.write(1, (outcome + "\\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift"


def test_audit_probe_state_getattribute_cannot_disable_registered_validation() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
policy_module = sys.modules["laconian_eval.capsule.import_policy"]
state_type = getattr(policy_module, "_AuditProbeState", None)
if state_type is not None:
    def bypass_getattribute(self, name):
        if name == "armed":
            return False
        return object.__getattribute__(self, name)
    state_type.__getattribute__ = bypass_getattribute
side_effects = []
class SideEffectFinder:
    @staticmethod
    def find_spec(fullname, path=None, target=None):
        side_effects.append(fullname)
        return None
sys.meta_path.pop(0)
sys.meta_path.insert(0, SideEffectFinder())
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
except ModuleNotFoundError:
    outcome = "module_not_found"
else:
    outcome = "imported"
os.write(1, (outcome + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_order_drift:0"


def test_reentrant_import_after_hook_registration_fails_installation() -> None:
    result = _run_child(
        r"""
original_addaudithook = sys.addaudithook
probe_name = "_laconian_reentrant_install_probe"
assert probe_name not in sys.modules
def reentrant_addaudithook(hook):
    original_addaudithook(hook)
    __import__(probe_name)
sys.addaudithook = reentrant_addaudithook
try:
    install_import_guard(policy)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "installed"
sys.addaudithook = original_addaudithook
os.write(1, (outcome + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "audit_hook_installation_failed"


def test_registered_audit_hook_blocks_every_later_hook_registration() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
guard_type = type(installation.guard)
original_find_spec = guard_type.find_spec
side_effects = []
def tampered_find_spec(self, fullname, path=None, target=None):
    side_effects.append("guard")
    return original_find_spec(self, fullname, path, target)
def later_hook(event, arguments):
    if event == "import":
        side_effects.append("hook")
        guard_type.find_spec = tampered_find_spec
try:
    sys.addaudithook(later_hook)
except ImportPolicyError as error:
    registration_outcome = error.code
else:
    registration_outcome = "add_call_returned"
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    import_outcome = error.code
else:
    import_outcome = "imported"
os.write(
    1,
    (
        registration_outcome
        + ":"
        + import_outcome
        + ":"
        + str(len(side_effects))
        + "\n"
    ).encode(),
)
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("add_call_returned:import_origin_not_allowed:0")


@pytest.mark.parametrize("mutation", ["replace", "code"])
def test_audit_seals_inherited_source_loader_exec_owner(mutation: str) -> None:
    if mutation == "replace":
        tamper = """
side_effects = []
def tampered_exec(self, module):
    side_effects.append(module.__name__)
    return original(self, module)
owner.exec_module = tampered_exec
"""
        restore = "owner.exec_module = original"
        observed = "len(side_effects)"
    else:
        tamper = """
original_code = original.__code__
def tampered_exec(self, module):
    type(self)._laconian_source_exec_side_effect = module.__name__
original.__code__ = tampered_exec.__code__
"""
        restore = "original.__code__ = original_code"
        observed = (
            "int(getattr(importlib.machinery.SourceFileLoader, "
            "'_laconian_source_exec_side_effect', None) == probe_name)"
        )
    result = _run_child(
        f"""
installation = install_import_guard(policy)
owner = next(
    base for base in importlib.machinery.SourceFileLoader.__mro__
    if "exec_module" in base.__dict__
)
original = owner.__dict__["exec_module"]
{tamper}
probe_name = "colorsys"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
observed = {observed}
{restore}
os.write(1, (outcome + ":" + str(observed) + "\\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


@pytest.mark.parametrize("method_name", ["create_module", "exec_module"])
@pytest.mark.parametrize("mutation", ["replace", "code"])
def test_audit_seals_extension_loader_create_and_exec(
    method_name: str,
    mutation: str,
) -> None:
    extension_probe = _destshared_extension_name(Path(sysconfig.get_config_var("DESTSHARED")))
    argument = "spec" if method_name == "create_module" else "module"
    if mutation == "replace":
        tamper = f"""
side_effects = []
def tampered_method(self, {argument}):
    observed_name = (
        {argument}.name
        if {method_name!r} == "create_module"
        else {argument}.__name__
    )
    side_effects.append(observed_name)
    return original(self, {argument})
owner.{method_name} = tampered_method
"""
        restore = f"owner.{method_name} = original"
        observed = "len(side_effects)"
    else:
        direct_call = (
            "return _imp.create_dynamic(spec)"
            if method_name == "create_module"
            else "return _imp.exec_dynamic(module)"
        )
        tamper = f"""
original_code = original.__code__
def tampered_method(self, {argument}):
    observed_name = (
        {argument}.name
        if {method_name!r} == "create_module"
        else {argument}.__name__
    )
    type(self)._laconian_extension_side_effect = observed_name
    {direct_call}
original.__code__ = tampered_method.__code__
"""
        restore = "original.__code__ = original_code"
        observed = "int(getattr(owner, '_laconian_extension_side_effect', None) == probe_name)"
    result = _run_child(
        f"""
installation = install_import_guard(policy)
owner = importlib.machinery.ExtensionFileLoader
original = owner.__dict__[{method_name!r}]
{tamper}
probe_name = {extension_probe!r}
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
except BaseException as error:
    outcome = type(error).__name__
else:
    outcome = "imported"
observed = {observed}
{restore}
os.write(1, (outcome + ":" + str(observed) + "\\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


@pytest.mark.parametrize("surface", ["loader_base", "module_spec"])
def test_audit_seals_getattribute_on_loader_mro_and_module_spec(surface: str) -> None:
    result = _run_child(
        f"""
installation = install_import_guard(policy)
surface_type = (
    importlib.machinery.SourceFileLoader.__mro__[1]
    if {surface!r} == "loader_base"
    else importlib.machinery.ModuleSpec
)
side_effects = []
def tampered_getattribute(self, name):
    side_effects.append(name)
    return object.__getattribute__(self, name)
surface_type.__getattribute__ = tampered_getattribute
probe_name = "colorsys"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
del surface_type.__getattribute__
os.write(1, (outcome + ":" + str(len(side_effects)) + "\\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift:0"


def test_audit_seals_machinery_loader_class_bindings() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
original = importlib.machinery.SourceFileLoader
class TamperedSourceLoader(original):
    pass
importlib.machinery.SourceFileLoader = TamperedSourceLoader
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
importlib.machinery.SourceFileLoader = original
os.write(1, (outcome + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift"


@pytest.mark.parametrize(
    "suffix_name",
    ["SOURCE_SUFFIXES", "BYTECODE_SUFFIXES", "EXTENSION_SUFFIXES"],
)
def test_audit_seals_mutable_machinery_suffix_collections(suffix_name: str) -> None:
    result = _run_child(
        f"""
installation = install_import_guard(policy)
suffixes = getattr(importlib.machinery, {suffix_name!r})
suffixes.append(".laconian-tampered")
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    outcome = error.code
else:
    outcome = "imported"
suffixes.pop()
os.write(1, (outcome + "\\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guard_callable_drift"


def test_guard_positive_lazy_captured_stdlib_source_and_extension_imports() -> None:
    extension_probe = _destshared_extension_name(Path(sysconfig.get_config_var("DESTSHARED")))
    body = r"""
installation = install_import_guard(policy)
loaded = []
for probe_name in ("annotated_types.test_cases", "colorsys", __EXTENSION_PROBE__):
    assert probe_name not in sys.modules
    module = __import__(probe_name, fromlist=("*",))
    loaded.append((probe_name, type(module.__spec__.loader).__name__))
revalidate_import_state(policy)
revalidate_loaded_modules(policy)
os.write(1, (__import__("json").dumps(loaded) + "\n").encode())
"""
    result = _run_child(body.replace("__EXTENSION_PROBE__", repr(extension_probe)))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        ["annotated_types.test_cases", "_OriginValidatingLoader"],
        ["colorsys", "_OriginValidatingLoader"],
        [extension_probe, "_OriginValidatingLoader"],
    ]


@pytest.mark.parametrize(
    "tamper",
    [
        "finder.path = '/synthetic/outside'",
        "finder._loaders = []",
    ],
)
def test_audit_rejects_internal_file_finder_drift(tamper: str) -> None:
    result = _run_child(
        rf"""
installation = install_import_guard(policy)
finder = next(
    value for value in sys.path_importer_cache.values()
    if type(value) is importlib.machinery.FileFinder
)
{tamper}
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "importer_cache_drift"


def test_audit_rejects_file_finder_instance_method_shadow_before_execution() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
finder = next(
    value for value in sys.path_importer_cache.values()
    if type(value) is importlib.machinery.FileFinder
)
side_effects = []
def tampered_find_spec(fullname, target=None):
    side_effects.append(fullname)
    return None
finder.find_spec = tampered_find_spec
probe_name = "_laconian_file_finder_shadow_probe"
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "importer_cache_drift:0"


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    [
        ("sys.path = EvilList(sys.path)", "sys_path_drift"),
        ("sys.meta_path = EvilList(sys.meta_path)", "guard_order_drift"),
        ("sys.path_hooks = EvilList(sys.path_hooks)", "path_hooks_drift"),
        (
            "sys.path_importer_cache = EvilDict(sys.path_importer_cache)",
            "importer_cache_drift",
        ),
    ],
)
def test_audit_rejects_container_subclasses_before_overridden_iteration(
    tamper: str,
    expected_code: str,
) -> None:
    result = _run_child(
        rf"""
installation = install_import_guard(policy)
side_effects = []
class EvilList(list):
    def __iter__(self):
        side_effects.append("iter")
        return super().__iter__()
class EvilDict(dict):
    def items(self):
        side_effects.append("items")
        return super().items()
{tamper}
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{expected_code}:0"


def test_audit_rejects_str_subclass_path_before_overridden_comparison() -> None:
    result = _run_child(
        r"""
installation = install_import_guard(policy)
side_effects = []
class EvilStr(str):
    def __eq__(self, other):
        side_effects.append("eq")
        return super().__eq__(other)
    __hash__ = str.__hash__
sys.path[0] = EvilStr(sys.path[0])
probe_name = installation.sentinel_name
assert probe_name not in sys.modules
try:
    __import__(probe_name)
except ImportPolicyError as error:
    os.write(1, (error.code + ":" + str(len(side_effects)) + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "sys_path_drift:0"


def test_application_audit_hook_is_added_before_guard_and_seen_by_independent_hook() -> None:
    result = _run_child(
        r"""
observed = []
ambient_first = sys.meta_path[0]
def independent_hook(event, args):
    if event == "sys.addaudithook":
        observed.append((event, sys.meta_path[0] is ambient_first))
    elif event == "import" and args:
        observed.append((event, sys.meta_path[0] is not ambient_first, args[0]))
sys.addaudithook(independent_hook)
installation = install_import_guard(policy)
sentinel_seen = any(
    event == "import" and changed and name == installation.sentinel_name
    for event, changed, *names in observed
    for name in (names[0] if names else None,)
)
os.write(1, (__import__("json").dumps({
    "add_before_guard": observed[0] == ("sys.addaudithook", True),
    "sentinel_seen_after_guard": sentinel_seen,
}) + "\n").encode())
"""
    )
    payload = _payload(result)
    assert payload == {
        "add_before_guard": True,
        "sentinel_seen_after_guard": True,
    }


def test_audit_hook_installation_failure_does_not_mutate_bootstrap_state() -> None:
    result = _run_child(
        r"""
original_addaudithook = sys.addaudithook
before = (
    tuple(sys.path),
    tuple(sys.meta_path),
    tuple(sys.path_hooks),
    tuple(sys.path_importer_cache.items()),
)
sys.addaudithook = lambda hook: None
try:
    install_import_guard(policy)
except ImportPolicyError as error:
    after = (
        tuple(sys.path),
        tuple(sys.meta_path),
        tuple(sys.path_hooks),
        tuple(sys.path_importer_cache.items()),
    )
    sys.addaudithook = original_addaudithook
    payload = {"code": error.code, "unchanged": before == after}
    os.write(1, (__import__("json").dumps(payload) + "\n").encode())
"""
    )
    payload = _payload(result)
    assert payload == {"code": "audit_hook_installation_failed", "unchanged": True}


def test_preinstalled_audit_suppressor_cannot_silently_drop_application_hook() -> None:
    result = _run_child(
        r"""
def suppress_new_hooks(event, args):
    if event == "sys.addaudithook":
        raise RuntimeError("suppressed")
sys.addaudithook(suppress_new_hooks)
before = (
    tuple(sys.path),
    tuple(sys.meta_path),
    tuple(sys.path_hooks),
    tuple(sys.path_importer_cache.items()),
)
try:
    install_import_guard(policy)
except ImportPolicyError as error:
    after = (
        tuple(sys.path),
        tuple(sys.meta_path),
        tuple(sys.path_hooks),
        tuple(sys.path_importer_cache.items()),
    )
    os.write(1, (__import__("json").dumps({
        "code": error.code,
        "unchanged": before == after,
    }) + "\n").encode())
"""
    )
    payload = _payload(result)
    assert payload == {"code": "audit_hook_installation_failed", "unchanged": True}


_TYPING_IO_EXPECTED = (
    "originless_module_changed" if hasattr(typing, "io") else "import_origin_not_allowed"
)


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    [
        ('sys.modules["typing.io"] = object()', _TYPING_IO_EXPECTED),
        (
            'sys.modules["_cython_9_9_9"] = type(sys)("_cython_9_9_9")',
            "import_origin_not_allowed",
        ),
    ],
)
def test_originless_runtime_exceptions_are_pinned_and_never_learned(
    tamper: str,
    expected_code: str,
) -> None:
    result = _run_child(
        rf"""
{tamper}
try:
    revalidate_loaded_modules(policy)
except ImportPolicyError as error:
    os.write(1, (error.code + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected_code


def test_fixed_frozen_alias_is_pinned_to_its_exact_initial_module_object() -> None:
    result = _run_child(
        r"""
original = sys.modules["os.path"]
assert original is sys.modules[original.__spec__.name]
sys.modules["os.path"] = type(sys)("os.path")
try:
    revalidate_loaded_modules(policy)
except ImportPolicyError as error:
    os.write(1, (error.code + "\n").encode())
"""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "fixed_module_alias_changed"


def test_guard_allows_lazy_openai_sdk_closure_then_full_revalidation() -> None:
    result = _run_child(
        r"""
assert "openai" not in sys.modules
installation = install_import_guard(policy)
import openai
import openai.resources.responses
revalidate_import_state(policy)
revalidate_loaded_modules(policy)
os.write(1, (__import__("json").dumps({
    "sdk": openai.__name__,
    "lazy": openai.resources.responses.__name__,
    "guard_first": sys.meta_path[0] is installation.guard,
}) + "\n").encode())
""",
        provider_kind="openai",
        timeout=90,
    )
    payload = _payload(result)
    assert payload == {
        "sdk": "openai",
        "lazy": "openai.resources.responses",
        "guard_first": True,
    }


def test_console_launcher_real_wrapper_runs_under_exact_template() -> None:
    launcher = ROOT / ".venv/bin/laconian"
    raw = launcher.read_bytes()
    _, remainder = raw.split(b"\n", 1)
    normalized = b"#!<CURRENT_INTERPRETER>\n" + remainder
    assert normalized == CONSOLE_LAUNCHER_TEMPLATE


def test_public_resume_checkpoint_allows_owned_lazy_import(
    public_resume_inputs: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    payload = _run_public_resume(public_resume_inputs, tmp_path, "lazy_import")
    result = payload["result"]

    assert payload["triggered"] == 1, json.dumps(payload, sort_keys=True)
    assert payload["lazy_loaded"] == "annotated_types.test_cases"
    assert isinstance(result, dict)
    assert result["status"] == "valid"
    assert result["state"] == "GENERATION_COMPLETE"
    assert payload["events"] == [
        "prepared",
        "execution_started",
        "request_started",
        "request_finished",
        "request_started",
        "request_finished",
        "generation_completed",
    ]
    assert payload["raw_rows"] == 2


@pytest.mark.parametrize(
    "action",
    ["sys_path", "meta_path", "path_hooks", "importer_cache"],
)
def test_public_resume_checkpoint_blocks_import_state_drift_before_provider_call(
    action: str,
    public_resume_inputs: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    payload = _run_public_resume(public_resume_inputs, tmp_path, action)
    result = payload["result"]

    assert payload["triggered"] == 1, json.dumps(payload, sort_keys=True)
    assert payload["lazy_loaded"] is None
    assert isinstance(result, dict)
    assert result["status"] == "valid"
    assert result["state"] == "INTERRUPTED"
    # ``request_started`` is durably appended before every provider call.  Its absence,
    # together with an empty raw journal, proves that the drift checkpoint failed closed
    # without either an adapter call or fabricated provider evidence.
    assert payload["events"] == [
        "prepared",
        "execution_started",
        "execution_interrupted",
    ]
    assert payload["raw_rows"] == 0
