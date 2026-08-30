# Alpha Launch Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an honest, installable, reproducible `v0.1.0-alpha.1` skill/plugin release with truthful CI and a ready-to-use social launch package.

**Architecture:** Keep the repository root as the plugin root so `skills/if/SKILL.md` remains the sole workflow copy. Fix interpreter selection and Python 3.14 import-policy compatibility independently from the plugin/release layer. Gate release publication on validators, two real Python versions, a deterministic allowlisted archive, and green GitHub checks.

**Tech Stack:** Python 3.11/3.14, pytest, uv, GitHub Actions, Codex plugin manifests, standard-library `zipfile`, SVG/PNG, GitHub CLI.

---

## File map

- `.github/workflows/ci.yml`: truthful interpreter matrix plus repo-owned skill/plugin contracts.
- `.github/workflows/release.yml`: tag-triggered alpha asset construction and GitHub Release.
- `.codex-plugin/plugin.json`: root plugin identity and install-surface metadata.
- `.agents/plugins/marketplace.json`: repo marketplace exposing the root plugin.
- `src/laconian_eval/capsule/import_policy.py`: Python 3.14 fixed-alias compatibility and warning-free descriptor cleanup.
- `tests/capsule/test_import_guard_subprocess.py`: portable extension probe and bounded slow OpenAI integration timeout.
- `tests/capsule/test_import_policy.py`: portable DESTSHARED module coverage and Python 3.14 alias regression.
- `tests/capsule/test_verify_prepared.py`: Python 3.14-compatible scandir monkeypatch.
- `tests/test_ci_contract.py`: workflow interpreter and release-gate contracts.
- `tests/test_plugin_contract.py`: plugin/marketplace/skill identity contract.
- `tests/test_release_bundle.py`: deterministic release allowlist, byte identity, and checksum contract.
- `tools/build_plugin_release.py`: deterministic plugin zip and checksum builder.
- `pyproject.toml`, `src/laconian_eval/__init__.py`, `uv.lock`, eval manifests and version-pinned fixtures: synchronized alpha version.
- `README*.md`: exact plugin and standalone install/uninstall paths in every edition.
- `CHANGELOG.md`, `docs/releases/v0.1.0-alpha.1.md`: alpha boundary and release notes.
- `NOTICE`: license coverage for manifests, release tooling, and social assets.
- `assets/social/laconian-alpha.svg`, `assets/social/laconian-alpha.png`: deterministic social card source and final bitmap.
- `docs/social/alpha-launch.md`: English/Russian social copy, demo, alt text, and claim boundaries.

### Task 1: Make the CI interpreter matrix truthful

**Files:**
- Create: `tests/test_ci_contract.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the failing workflow contract test**

```python
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def _workflow(name: str) -> dict[str, object]:
    value = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_ci_binds_uv_to_each_declared_python() -> None:
    workflow = _workflow("ci.yml")
    jobs = workflow["jobs"]
    quality = jobs["quality"]
    assert quality["strategy"]["matrix"]["python-version"] == ["3.11", "3.14"]
    assert quality["env"] == {
        "UV_PYTHON": "${{ matrix.python-version }}",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    macos = jobs["macos-capsule"]
    assert macos["env"] == {"UV_PYTHON": "3.14", "UV_PYTHON_DOWNLOADS": "never"}
    for job in (quality, macos):
        commands = [step.get("run", "") for step in job["steps"]]
        assert any("sys.version_info[:2]" in command for command in commands)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/test_ci_contract.py -q`

Expected: FAIL because neither job defines `UV_PYTHON`, `UV_PYTHON_DOWNLOADS`, or a runtime-version assertion.

- [ ] **Step 3: Bind uv and assert the effective interpreter**

Add this job-level environment to `quality`:

```yaml
    env:
      UV_PYTHON: ${{ matrix.python-version }}
      UV_PYTHON_DOWNLOADS: never
```

Add this job-level environment to `macos-capsule`:

```yaml
    env:
      UV_PYTHON: "3.14"
      UV_PYTHON_DOWNLOADS: never
```

Immediately after each `uv sync` step, add:

```yaml
      - name: Verify Python selection
        run: >-
          uv run python -c 'import os, sys; expected = tuple(map(int,
          os.environ["UV_PYTHON"].split("."))); assert sys.version_info[:2] == expected,
          (sys.version, expected)'
```

- [ ] **Step 4: Run the focused contract and lint the workflow diff**

Run: `uv run pytest tests/test_ci_contract.py -q`

Expected: PASS.

Run: `git diff --check`

Expected: exit 0 with no output.

- [ ] **Step 5: Commit the truthful matrix**

```bash
git add .github/workflows/ci.yml tests/test_ci_contract.py
git commit -m "ci: bind quality jobs to declared Python"
```

### Task 2: Remove build-layout assumptions from import tests

**Files:**
- Modify: `tests/capsule/test_import_guard_subprocess.py`
- Modify: `tests/capsule/test_import_policy.py`

- [ ] **Step 1: Add a portable extension-module selector to both test modules**

Import `importlib.machinery` and `sysconfig` in `test_import_guard_subprocess.py`. Use this test helper
in both modules instead of `_sha3` or `_hashlib`:

```python
def _destshared_extension_name(destshared: Path) -> str:
    for path in sorted(destshared.iterdir(), key=lambda item: item.name):
        for suffix in importlib.machinery.EXTENSION_SUFFIXES:
            if path.is_file() and path.name.endswith(suffix):
                name = path.name[: -len(suffix)]
                if name and name not in sys.modules:
                    return name
    raise AssertionError(f"no unloaded DESTSHARED extension under {destshared}")
```

In `test_import_guard_subprocess.py`, resolve the name from
`Path(sysconfig.get_config_var("DESTSHARED"))` in the parent and interpolate it into the child
body. In `test_import_policy.py`, import the selected name with `importlib.import_module` and use
that module in the mapping passed to `revalidate_loaded_modules`.

- [ ] **Step 2: Verify the tests expose the old assumptions before replacement**

Run on the existing environment:

```bash
uv run pytest \
  tests/capsule/test_import_guard_subprocess.py::test_audit_seals_extension_loader_create_and_exec \
  tests/capsule/test_import_guard_subprocess.py::test_guard_positive_lazy_captured_stdlib_source_and_extension_imports \
  tests/capsule/test_import_policy.py::test_loaded_dependency_source_and_destshared_extension_are_allowed -q
```

Expected before editing the assertions: the hard-coded tests still reference `_sha3` and `_hashlib`.
On an Astral standalone build they fail with loader `type` or missing `__file__` as recorded in CI.

- [ ] **Step 3: Replace every hard-coded extension module and expected name**

Replace the guarded child body and assertion with:

```python
extension_probe = _destshared_extension_name(Path(sysconfig.get_config_var("DESTSHARED")))
body = r"""
installation = install_import_guard(policy)
loaded = []
for probe_name in ("annotated_types.test_cases", "colorsys", "__EXTENSION_PROBE__"):
    assert probe_name not in sys.modules
    module = __import__(probe_name, fromlist=("*",))
    loaded.append((probe_name, type(module.__spec__.loader).__name__))
revalidate_import_state(policy)
revalidate_loaded_modules(policy)
os.write(1, (__import__("json").dumps(loaded) + "\n").encode())
"""
result = _run_child(body.replace("__EXTENSION_PROBE__", extension_probe))
assert result.returncode == 0, result.stderr
assert json.loads(result.stdout) == [
    ["annotated_types.test_cases", "_OriginValidatingLoader"],
    ["colorsys", "_OriginValidatingLoader"],
    [extension_probe, "_OriginValidatingLoader"],
]
```

Replace the direct policy test body with:

```python
extension_name = _destshared_extension_name(policy.destshared_root.canonical_path)
extension_module = importlib.import_module(extension_name)
extension_path = Path(extension_module.__file__).resolve()
assert extension_path.is_relative_to(policy.destshared_root.canonical_path)
revalidate_loaded_modules(
    policy,
    modules=MappingProxyType(
        {"packaging.version": packaging.version, extension_name: extension_module}
    ),
)
```

The same build-layout assumption also exists in
`test_audit_seals_extension_loader_create_and_exec`. Resolve `extension_probe` in the parent before
the child call and interpolate its repr into the already formatted child source:

```python
extension_probe = _destshared_extension_name(Path(sysconfig.get_config_var("DESTSHARED")))
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
```

Keep the existing return-code and `guard_callable_drift:0` assertions after this call.

- [ ] **Step 4: Run focused tests on both installed CPython layouts**

Run with project Python 3.11:

```bash
uv run pytest \
  tests/capsule/test_import_guard_subprocess.py::test_audit_seals_extension_loader_create_and_exec \
  tests/capsule/test_import_guard_subprocess.py::test_guard_positive_lazy_captured_stdlib_source_and_extension_imports \
  tests/capsule/test_import_policy.py::test_loaded_dependency_source_and_destshared_extension_are_allowed -q
```

Expected: 6 passed (four parametrized loader-tamper cases plus two import-policy probes).

Run after `UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv sync --all-extras --locked`:

```bash
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv run pytest \
  tests/capsule/test_import_guard_subprocess.py::test_audit_seals_extension_loader_create_and_exec \
  tests/capsule/test_import_guard_subprocess.py::test_guard_positive_lazy_captured_stdlib_source_and_extension_imports \
  tests/capsule/test_import_policy.py::test_loaded_dependency_source_and_destshared_extension_are_allowed -q
```

Expected: all six cases reach policy construction; any remaining failure is the separate fixed-alias
compatibility addressed in Task 3.

- [ ] **Step 5: Commit the portable probes**

```bash
git add tests/capsule/test_import_guard_subprocess.py tests/capsule/test_import_policy.py
git commit -m "test: select real destshared extensions"
```

### Task 3: Support real Python 3.14 import semantics

**Files:**
- Modify: `src/laconian_eval/capsule/import_policy.py`
- Modify: `tests/capsule/test_import_guard_subprocess.py`
- Modify: `tests/capsule/test_import_policy.py`
- Modify: `tests/capsule/test_verify_prepared.py`

- [ ] **Step 1: Write the Python 3.14 fixed-alias regression test**

Add a test guarded only by the runtime fact it exercises:

```python
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
```

- [ ] **Step 2: Verify RED under actual Python 3.14**

Run:

```bash
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv sync --all-extras --locked
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv run pytest \
  tests/capsule/test_import_policy.py::test_collections_abc_identity_alias_is_pinned_when_runtime_uses_it -q
```

Expected: ERROR/FAIL with `builtin_frozen_mismatch` while building `policy`.

- [ ] **Step 3: Add the conditional fixed alias**

Build `_FIXED_MODULE_ALIASES` with this additional entry only when the current interpreter exposes
the identity alias:

```python
_COLLECTIONS_ABC_ALIAS = (
    {"collections.abc": "_collections_abc"}
    if sys.modules.get("collections.abc") is not None
    and sys.modules.get("collections.abc") is sys.modules.get("_collections_abc")
    else {}
)
_FIXED_MODULE_ALIASES = {
    "os.path": "posixpath" if os.name == "posix" else "ntpath",
    "importlib._bootstrap": "_frozen_importlib",
    "importlib._bootstrap_external": "_frozen_importlib_external",
    **_COLLECTIONS_ABC_ALIAS,
}
```

Do not add a version check; object identity is the security-relevant runtime fact.

- [ ] **Step 4: Make the slow OpenAI case explicitly integration-bounded**

Change the helper signature and its one slow caller:

```python
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
```

Add `timeout=90` to the existing `_run_child` call in
`test_guard_allows_lazy_openai_sdk_closure_then_full_revalidation`, alongside
`provider_kind="openai"`.

Keep the default at 30 seconds for all other child tests.

- [ ] **Step 5: Make test-only aliases and scandir interception runtime-aware**

Import `typing` in `tests/capsule/test_import_guard_subprocess.py`, derive the expected result from
the same runtime used by the child, and replace the hard-coded `typing.io` tuple with:

```python
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
```

In `test_tree_walker_sorts_bounded_names_before_stat_and_error_selection`, widen the monkeypatch
input and guard fd-only inspection:

```python
def ordered_scandir(
    descriptor: int | str | bytes | os.PathLike[str],
) -> Any:
    if type(descriptor) is int and _descriptor_path(descriptor) == root.resolve():
        return FakeScandir()
    return real_scandir(descriptor)
```

- [ ] **Step 6: Remove the Python 3.14 SyntaxWarning without changing close semantics**

Rewrite `root_identity_is_current` so cleanup happens after the guarded operation and no return
occurs inside `finally`:

```python
def root_identity_is_current(path: str, device: int, inode: int) -> bool:
    descriptor = -1
    current = False
    close_failed = False
    try:
        try:
            descriptor = os_open("/", directory_flags)
            for component in path.split("/"):
                if component in ("", "."):
                    continue
                next_descriptor = os_open(component, directory_flags, dir_fd=descriptor)
                os_close(descriptor)
                descriptor = next_descriptor
            metadata = os_fstat(descriptor)
            current = (
                metadata.st_mode & 0o170000 == 0o040000
                and metadata.st_dev == device
                and metadata.st_ino == inode
            )
        except handled_os_errors:
            current = False
    finally:
        if descriptor >= 0:
            try:
                os_close(descriptor)
            except handled_os_errors:
                close_failed = True
    return current and not close_failed
```

- [ ] **Step 7: Verify GREEN on real 3.14, including warning-as-error**

Run:

```bash
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv run python \
  -W error::SyntaxWarning -m py_compile src/laconian_eval/capsule/import_policy.py
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv run pytest \
  tests/capsule/test_import_policy.py \
  tests/capsule/test_import_guard_subprocess.py \
  tests/capsule/test_verify_prepared.py -q
```

Expected: all selected tests pass, with only the existing non-UTF-8 filesystem skip where the
filesystem cannot construct that filename.

- [ ] **Step 8: Commit Python 3.14 compatibility**

```bash
git add src/laconian_eval/capsule/import_policy.py \
  tests/capsule/test_import_guard_subprocess.py \
  tests/capsule/test_import_policy.py \
  tests/capsule/test_verify_prepared.py
git commit -m "fix: support Python 3.14 import aliases"
```

### Task 4: Add the root plugin and repo marketplace

**Files:**
- Create: `.codex-plugin/plugin.json`
- Create: `.agents/plugins/marketplace.json`
- Create: `tests/test_plugin_contract.py`

- [ ] **Step 1: Write the failing plugin contract test**

```python
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_root_plugin_packages_the_canonical_if_skill() -> None:
    plugin = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads(
        (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
    )
    assert plugin["name"] == "laconian"
    assert plugin["version"] == "0.1.0-alpha.1"
    assert plugin["skills"] == "./skills/"
    assert plugin["license"] == "Apache-2.0"
    assert not ({"apps", "mcpServers", "hooks"} & plugin.keys())
    assert (ROOT / plugin["skills"] / "if/SKILL.md").is_file()
    assert marketplace == {
        "name": "laconian",
        "interface": {"displayName": "Laconian"},
        "plugins": [
            {
                "name": "laconian",
                "source": {"source": "local", "path": "./"},
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }
    assert all(
        prompt.startswith("$laconian:if ") for prompt in plugin["interface"]["defaultPrompt"]
    )
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/test_plugin_contract.py -q`

Expected: FAIL because both JSON files are absent.

- [ ] **Step 3: Add the exact manifest and marketplace**

Use the strict-semver manifest approved in the design:

```json
{
  "name": "laconian",
  "version": "0.1.0-alpha.1",
  "description": "Produce the shortest complete answer while preserving correctness and required information.",
  "author": {
    "name": "Laconian contributors",
    "url": "https://github.com/agent-axiom"
  },
  "homepage": "https://github.com/agent-axiom/laconian",
  "repository": "https://github.com/agent-axiom/laconian",
  "license": "Apache-2.0",
  "keywords": ["concise", "brevity", "writing", "editing", "agent-skill"],
  "skills": "./skills/",
  "interface": {
    "displayName": "Laconian",
    "shortDescription": "Shortest complete answers without lost substance",
    "longDescription": "Use the if workflow to remove filler, restatement, repetition, and decoration while preserving correctness, safety, required detail, exact values, and material uncertainty.",
    "developerName": "Laconian contributors",
    "category": "Productivity",
    "capabilities": ["Interactive"],
    "websiteURL": "https://github.com/agent-axiom/laconian",
    "defaultPrompt": [
      "$laconian:if Answer this as briefly as possible without losing required detail.",
      "$laconian:if Shorten this draft while preserving every material fact and warning.",
      "$laconian:if Remove filler and repetition from this answer."
    ]
  }
}
```

Use the marketplace object asserted by the test. Do not duplicate `SKILL.md` under `plugins/`.

- [ ] **Step 4: Validate skill, plugin, and contract**

Run:

```bash
uv run python /Users/if/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/if
uv run python /Users/if/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
uv run pytest tests/test_skill_contract.py tests/test_plugin_contract.py -q
```

Expected: validator messages indicate valid skill/plugin and all tests pass.

- [ ] **Step 5: Commit packaging metadata**

```bash
git add .codex-plugin/plugin.json .agents/plugins/marketplace.json tests/test_plugin_contract.py
git commit -m "feat: package laconian as a repo plugin"
```

### Task 5: Version and build the immutable alpha bundle

**Files:**
- Create: `tools/build_plugin_release.py`
- Create: `tests/test_release_bundle.py`
- Modify: `pyproject.toml`
- Modify: `src/laconian_eval/__init__.py`
- Modify: `uv.lock`
- Modify: `evals/manifests/openai-example.yaml`
- Modify: `evals/manifests/replay-smoke.yaml`
- Modify: version-pinned tests returned by `rg -l '0\.1\.0\.dev0' tests`

- [ ] **Step 1: Change the package expectation first and verify RED**

Change only `tests/test_package.py` to expect:

```python
def test_package_exposes_alpha_version() -> None:
    assert __version__ == "0.1.0a1"


def test_cli_reports_alpha_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "laconian 0.1.0a1"
```

Run: `uv run pytest tests/test_package.py -q`

Expected: 2 failures showing the old `0.1.0.dev0` value.

- [ ] **Step 2: Synchronize the PEP 440 version**

Set `pyproject.toml` and `src/laconian_eval/__init__.py` to `0.1.0a1`. Replace the old value in:

```text
evals/manifests/openai-example.yaml
evals/manifests/replay-smoke.yaml
tests/capsule/test_attempts_v2.py
tests/capsule/test_delivery_certainty.py
tests/capsule/test_import_guard_subprocess.py
tests/capsule/test_import_policy.py
tests/capsule/test_provenance.py
tests/capsule/test_resume.py
tests/test_cases.py
tests/test_cli.py
tests/test_package.py
```

Regenerate the lock with `uv lock`, then run `uv sync --all-extras --locked` for the active
interpreter.

- [ ] **Step 3: Write the failing release-bundle test**

The test must execute the builder twice and assert identical bytes, exact inventory, canonical
skill bytes, strict manifest version, and checksum:

```python
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from tools.build_plugin_release import build_release

ROOT = Path(__file__).parents[1]

EXPECTED = {
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "skills/if/SKILL.md",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE",
    "LICENSES/CC-BY-4.0.txt",
}


def test_release_bundle_is_deterministic_and_allowlisted(tmp_path: Path) -> None:
    first = build_release(ROOT, tmp_path / "one")
    second = build_release(ROOT, tmp_path / "two")
    assert first.archive.read_bytes() == second.archive.read_bytes()
    with ZipFile(first.archive) as bundle:
        assert set(bundle.namelist()) == EXPECTED
        assert bundle.read("skills/if/SKILL.md") == (ROOT / "skills/if/SKILL.md").read_bytes()
        manifest = json.loads(bundle.read(".codex-plugin/plugin.json"))
        assert manifest["version"] == "0.1.0-alpha.1"
    digest = hashlib.sha256(first.archive.read_bytes()).hexdigest()
    assert first.checksum.read_text(encoding="ascii") == f"{digest}  {first.archive.name}\n"
```

- [ ] **Step 4: Run and verify RED**

Run: `uv run pytest tests/test_package.py tests/test_release_bundle.py -q`

Expected: package tests pass after version synchronization; release test errors because the builder
does not exist.

- [ ] **Step 5: Implement the deterministic standard-library builder**

Create `tools/build_plugin_release.py` with:

```python
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

RELEASE_FILES = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "skills/if/SKILL.md",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE",
    "LICENSES/CC-BY-4.0.txt",
)


@dataclass(frozen=True)
class ReleaseArtifacts:
    archive: Path
    checksum: Path


def build_release(root: Path, output_dir: Path) -> ReleaseArtifacts:
    manifest = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    if version != "0.1.0-alpha.1":
        raise ValueError(f"unexpected plugin version: {version!r}")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"laconian-plugin-v{version}.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as bundle:
        for relative in RELEASE_FILES:
            data = (root / relative).read_bytes()
            info = ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data, compresslevel=9)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return ReleaseArtifacts(archive=archive, checksum=checksum)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    artifacts = build_release(args.root.resolve(), args.output_dir.resolve())
    print(artifacts.archive)
    print(artifacts.checksum)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify GREEN and build real assets**

Run:

```bash
uv run pytest tests/test_package.py tests/test_release_bundle.py -q
uv run python tools/build_plugin_release.py --output-dir dist
python3 -m zipfile -l dist/laconian-plugin-v0.1.0-alpha.1.zip
```

Expected: tests pass; archive lists exactly eight approved files.

- [ ] **Step 7: Commit version and builder**

```bash
git add pyproject.toml src/laconian_eval/__init__.py uv.lock \
  evals/manifests tests tools/build_plugin_release.py
git commit -m "build: prepare alpha plugin bundle"
```

### Task 6: Replace placeholder installation and prepare launch copy

**Files:**
- Modify: `README.md`
- Modify: `README.ru.md`
- Modify: `README.zh-CN.md`
- Modify: `README.el.md`
- Modify: `README.it.md`
- Modify: `README.grc-x-laconian.md`
- Modify: `tests/test_public_contract.py`
- Modify: `CHANGELOG.md`
- Modify: `NOTICE`
- Create: `docs/releases/v0.1.0-alpha.1.md`
- Create: `docs/social/alpha-launch.md`

- [ ] **Step 1: Write failing public installation and claim-boundary tests**

Add constants and tests:

```python
PLUGIN_ADD = "codex plugin marketplace add agent-axiom/laconian --ref v0.1.0-alpha.1 --json"
PLUGIN_INSTALL = "codex plugin add laconian@laconian --json"
STANDALONE_URL = (
    "https://raw.githubusercontent.com/agent-axiom/laconian/v0.1.0-alpha.1/skills/if/SKILL.md"
)


@pytest.mark.parametrize("filename", README_FILES.values())
def test_every_readme_has_pinned_install_paths(filename: str) -> None:
    text = _read(filename)
    assert PLUGIN_ADD in text
    assert PLUGIN_INSTALL in text
    assert STANDALONE_URL in text
    assert "<agent-skills-directory>" not in text


def test_social_launch_copy_is_explicitly_experimental() -> None:
    text = _read("docs/social/alpha-launch.md")
    assert "Illustrative edit, not benchmark output." in text
    assert "Иллюстративное редактирование, не результат бенчмарка." in text
    assert "No public benchmark result" in text
    assert re.search(r"\b\d+(?:[.,]\d+)?\s*%", text) is None
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/test_public_contract.py -q`

Expected: all new cases fail because the placeholder blocks remain and social copy is absent.

- [ ] **Step 3: Replace every installation section with pinned commands**

Keep translated prose in each README but use the same exact command blocks:

```bash
codex plugin marketplace add agent-axiom/laconian --ref v0.1.0-alpha.1 --json
codex plugin add laconian@laconian --json
```

State that the installed invocation is `$laconian:if` and a new task/restart may be needed. Verify
discovery with:

```bash
codex plugin list --marketplace laconian --json
```

Under a separate uninstall label, provide:

```bash
codex plugin remove laconian@laconian --json
codex plugin marketplace remove laconian --json
```

Provide the standalone path:

```bash
mkdir -p "$HOME/.agents/skills/if"
curl -fsSL "https://raw.githubusercontent.com/agent-axiom/laconian/v0.1.0-alpha.1/skills/if/SKILL.md" \
  -o "$HOME/.agents/skills/if/SKILL.md"
```

State that standalone invocation is `$if`, and verify the copy with:

```bash
test -s "$HOME/.agents/skills/if/SKILL.md"
```

Under a separate uninstall label, remove only the exact copied target:

```bash
rm "$HOME/.agents/skills/if/SKILL.md"
rmdir "$HOME/.agents/skills/if"
```

- [ ] **Step 4: Add alpha release notes and changelog boundary**

Move the current foundation list under `## [0.1.0-alpha.1] - 2026-08-30`, keep a new empty
`## [Unreleased]` heading, and say explicitly that no public benchmark result is included.

`docs/releases/v0.1.0-alpha.1.md` must list the installable one-file skill, repo plugin, supported
Python versions, archive/checksum, known experimental boundary, and the absence of benchmark
claims.

- [ ] **Step 5: Add ready-to-post social copy**

`docs/social/alpha-launch.md` must contain:

- English and Russian X versions under 280 characters;
- English and Russian LinkedIn/Telegram versions;
- one before/after example labeled illustrative in both languages;
- exact card alt text;
- allowed claims (`one-file workflow`, `experimental alpha`, `open benchmark under development`);
- prohibited claims (`proven`, numeric token savings, benchmark winner, universal-directory listing).

- [ ] **Step 6: Extend the license map**

Add these exact classifications to `NOTICE`:

```text
.codex-plugin/, .agents/, and tools/: Apache-2.0.
assets/social/ and docs/social/: CC-BY-4.0.
```

- [ ] **Step 7: Verify docs and commit**

Run:

```bash
uv run pytest tests/test_public_contract.py tests/test_plugin_contract.py -q
rg -n "<agent-skills-directory>|saves [0-9]|better than|benchmark winner" README*.md docs/social
```

Expected: tests pass; `rg` returns no unsupported install placeholder or performance claim.

```bash
git add README*.md CHANGELOG.md NOTICE docs/releases docs/social tests/test_public_contract.py
git commit -m "docs: add pinned alpha install and launch copy"
```

### Task 7: Create and verify the social card

**Files:**
- Create: `assets/social/laconian-alpha.svg`
- Create: `assets/social/laconian-alpha.png`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write the failing asset contract**

```python
import struct


def test_social_card_has_exact_copy_and_dimensions() -> None:
    svg = _read("assets/social/laconian-alpha.svg")
    for text in ("if", "The shortest complete answer.", "Experimental alpha"):
        assert text in svg
    png = (ROOT / "assets/social/laconian-alpha.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (1200, 630)
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/test_public_contract.py::test_social_card_has_exact_copy_and_dimensions -q`

Expected: FAIL because the assets do not exist.

- [ ] **Step 3: Create the deterministic SVG source**

Create `assets/social/laconian-alpha.svg` with this exact source:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title desc">
  <title id="title">Laconian experimental alpha</title>
  <desc id="desc">if — The shortest complete answer. Experimental alpha.</desc>
  <rect width="1200" height="630" fill="#F1E9DB"/>
  <rect width="430" height="630" fill="#171512"/>
  <rect x="430" width="12" height="630" fill="#8A2F2B"/>
  <circle cx="1080" cy="102" r="38" fill="none" stroke="#8A2F2B" stroke-width="10"/>
  <text x="80" y="410" fill="#F1E9DB" font-family="Georgia, serif" font-size="300" font-weight="700">if</text>
  <text x="520" y="250" fill="#171512" font-family="Arial, Helvetica, sans-serif" font-size="58" font-weight="700">The shortest</text>
  <text x="520" y="326" fill="#171512" font-family="Arial, Helvetica, sans-serif" font-size="58" font-weight="700">complete answer.</text>
  <line x1="520" y1="382" x2="1060" y2="382" stroke="#8A2F2B" stroke-width="8"/>
  <text x="520" y="452" fill="#171512" font-family="Arial, Helvetica, sans-serif" font-size="32" font-weight="700" letter-spacing="3">Experimental alpha</text>
</svg>
```

This uses a 1200x630 canvas with warm stone `#F1E9DB`, dark ink `#171512`, muted red `#8A2F2B`,
a large serif `if` on the left, and the exact launch copy on the right. Keep it free of charts,
scores, third-party logos, and unsupported claims.

Because exact text and reproducibility are release invariants, use SVG rather than generative
in-image typography.

- [ ] **Step 4: Render PNG and inspect it visually**

Run:

```bash
magick -background none assets/social/laconian-alpha.svg assets/social/laconian-alpha.png
magick identify assets/social/laconian-alpha.png
```

Expected dimensions: `1200x630`.

Open the PNG with the image viewer and confirm exact text, contrast, safe margins, and small-preview
legibility. If visual corrections are needed, edit only the SVG and rerender.

- [ ] **Step 5: Verify GREEN and commit**

Run: `uv run pytest tests/test_public_contract.py::test_social_card_has_exact_copy_and_dimensions -q`

Expected: PASS.

```bash
git add assets/social tests/test_public_contract.py
git commit -m "docs: add alpha social card"
```

### Task 8: Add release automation and artifact contract gates

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ci_contract.py`

- [ ] **Step 1: Extend workflow tests before editing workflows**

Assert the quality job runs the repository-owned skill/plugin contract tests and that the release
workflow produces a prerelease:

```python
def test_ci_validates_skill_and_plugin() -> None:
    workflow = _workflow("ci.yml")
    runs = [step.get("run", "") for step in workflow["jobs"]["quality"]["steps"]]
    assert any(
        command == "uv run pytest tests/test_skill_contract.py tests/test_plugin_contract.py -q"
        for command in runs
    )


def test_release_workflow_builds_tagged_assets() -> None:
    workflow = _workflow("release.yml")
    release = workflow["jobs"]["release"]
    assert release["permissions"]["contents"] == "write"
    runs = "\n".join(step.get("run", "") for step in release["steps"])
    assert "tools/build_plugin_release.py" in runs
    assert "gh release create" in runs
    assert "--prerelease" in runs
    assert "docs/releases/v0.1.0-alpha.1.md" in runs
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/test_ci_contract.py -q`

Expected: failures for the missing contract command and missing release workflow.

- [ ] **Step 3: Add repo-owned skill/plugin contracts to each quality matrix job**

After type checking and before pytest, add:

```yaml
      - run: uv run pytest tests/test_skill_contract.py tests/test_plugin_contract.py -q
```

This is checkout-owned and independent of any developer-machine path. Run the bundled skill and
plugin validators locally in Task 9; do not embed their absolute paths in GitHub Actions.

- [ ] **Step 4: Create tag-triggered release workflow**

Create `.github/workflows/release.yml` with the same pinned checkout/setup-python actions already
used by CI:

```yaml
name: Release

on:
  push:
    tags: ["v0.1.0-alpha.1"]

permissions:
  contents: read

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.11"
      - name: Build deterministic plugin assets
        run: python tools/build_plugin_release.py --output-dir dist
      - name: Verify checksum
        working-directory: dist
        run: sha256sum -c "laconian-plugin-${GITHUB_REF_NAME}.zip.sha256"
      - name: Publish GitHub prerelease
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "$GITHUB_REF_NAME" \
            "dist/laconian-plugin-${GITHUB_REF_NAME}.zip" \
            "dist/laconian-plugin-${GITHUB_REF_NAME}.zip.sha256" \
            --verify-tag \
            --prerelease \
            --title "Laconian ${GITHUB_REF_NAME}" \
            --notes-file docs/releases/v0.1.0-alpha.1.md
```

The builder names the archive `laconian-plugin-v0.1.0-alpha.1.zip`, so the workflow variable must
match it exactly.

- [ ] **Step 5: Verify workflows and commit**

Run:

```bash
uv run pytest tests/test_ci_contract.py tests/test_release_bundle.py -q
git diff --check
```

Expected: PASS and no whitespace errors.

```bash
git add .github/workflows/ci.yml .github/workflows/release.yml tests/test_ci_contract.py
git commit -m "ci: gate and publish alpha plugin releases"
```

### Task 9: Run complete verification and real local plugin smoke tests

**Files:**
- Modify only if verification exposes a demonstrated defect.

- [ ] **Step 1: Run formatting, lint, types, validators, and focused contracts**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run python /Users/if/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/if
uv run python /Users/if/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
uv run pytest tests/test_ci_contract.py tests/test_plugin_contract.py \
  tests/test_release_bundle.py tests/test_skill_contract.py tests/test_public_contract.py -q
```

Expected: all commands exit 0.

- [ ] **Step 2: Run full Python 3.11 suite**

```bash
UV_PYTHON=3.11 UV_PYTHON_DOWNLOADS=never uv sync --all-extras --locked
UV_PYTHON=3.11 UV_PYTHON_DOWNLOADS=never uv run pytest -q
```

Expected: all tests pass with only the documented non-UTF-8 filesystem skip when applicable.

- [ ] **Step 3: Run full Python 3.14 suite**

```bash
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv sync --all-extras --locked
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv run python \
  -W error::SyntaxWarning -m py_compile src/laconian_eval/capsule/import_policy.py
UV_PYTHON=3.14 UV_PYTHON_DOWNLOADS=never uv run pytest -q
```

Expected: all tests pass with only the documented filesystem skip.

- [ ] **Step 4: Build and smoke-test the clean wheel**

```bash
uv build
uvx --from dist/laconian_eval-0.1.0a1-py3-none-any.whl laconian --version
uvx --from dist/laconian_eval-0.1.0a1-py3-none-any.whl laconian --help
```

Expected version: `laconian 0.1.0a1`; help exits 0.

- [ ] **Step 5: Smoke-test local marketplace discovery with reversible state**

From the worktree root, first run these read-only checks and confirm neither a marketplace named
`laconian` nor an installed `laconian@laconian` entry exists:

```bash
codex plugin marketplace list --json
codex plugin list --available --json
```

If either entry exists, stop and preserve the user's state. Otherwise run the full reversible smoke
sequence:

```bash
codex plugin marketplace add . --json
codex plugin list --marketplace laconian --available --json
codex plugin add laconian@laconian --json
codex plugin list --marketplace laconian --json
codex plugin remove laconian@laconian --json
codex plugin marketplace remove laconian --json
codex plugin marketplace list --json
```

Expected: discovery returns one available `laconian` plugin, installation returns
`laconian@laconian` as installed and enabled, both cleanup commands succeed, and the final listing
contains no `laconian` marketplace. A new Codex task is required to manually invoke `$laconian:if`;
the manifest/discovery smoke test does not mutate this active task. If discovery or installation
fails, do not open the launch PR: diagnose and fix the package path, or remove the unverified plugin
install claim and ship only the standalone path. If either full interpreter suite is red, pause the
release and fix the demonstrated compatibility defect instead of weakening the matrix.

- [ ] **Step 6: Verify the final diff and request independent code review**

```bash
git status --short
git diff origin/main...HEAD --check
git diff --stat origin/main...HEAD
```

Dispatch a reviewer with the approved spec, this plan, `origin/main` as base, and current HEAD.
Resolve every Critical or Important finding, rerun the affected tests, and commit only demonstrated
fixes.

### Task 10: Create PR, merge only on green, and publish the alpha

**Files / external state:**
- GitHub PR and Actions.
- GitHub repository metadata and branch protection.
- Git tag and GitHub Release.
- Repository social preview.

- [ ] **Step 1: Push and create the launch PR**

```bash
git push -u origin codex/launch-readiness-alpha
gh pr create \
  --title "feat: prepare v0.1.0-alpha.1 launch" \
  --body-file docs/releases/v0.1.0-alpha.1.md
```

- [ ] **Step 2: Wait for every PR check**

Run: `gh pr checks --watch`

Expected: `quality (3.11)`, `quality (3.14)`, and `macos-capsule` all pass, with logs proving the
declared interpreter versions. Do not merge a pending or failed run.

- [ ] **Step 3: Merge through the PR and verify main**

After the watched checks pass, merge with the repository's existing merge-commit convention:

```bash
gh pr merge --merge
gh pr view --json number,state,mergedAt,mergeCommit,url
gh run list --workflow ci.yml --branch main --limit 3 \
  --json databaseId,headSha,status,conclusion,url
```

Select the run whose `headSha` equals the PR's `mergeCommit.oid`, then run `gh run watch` with that
actual numeric database ID. Confirm `quality (3.11)`, `quality (3.14)`, and `macos-capsule` are green
before changing release state.

- [ ] **Step 4: Configure repository launch metadata**

```bash
gh repo edit agent-axiom/laconian \
  --description "The shortest complete answer: an experimental agent skill with an open benchmark under development." \
  --homepage "https://github.com/agent-axiom/laconian#readme" \
  --add-topic agent-skills \
  --add-topic codex \
  --add-topic concise-writing \
  --add-topic llm-evaluation \
  --add-topic prompt-engineering
```

Re-read `repos/agent-axiom/laconian/branches/main/protection`; the planning audit returned HTTP 404,
so do not overwrite a newly added policy if that state has changed. If it remains unprotected,
create `/private/tmp/laconian-main-protection.json` with `apply_patch`:

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["quality (3.11)", "quality (3.14)", "macos-capsule"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": true
}
```

Apply and read it back:

```bash
gh api --method PUT repos/agent-axiom/laconian/branches/main/protection \
  --input /private/tmp/laconian-main-protection.json
gh api repos/agent-axiom/laconian/branches/main/protection
```

Verify the exact three contexts, strict mode, admin enforcement, no force pushes/deletions, and
conversation resolution. If GitHub rejects protection because of permissions or plan limits,
leave repository metadata in place and disclose the limitation before tagging.

- [ ] **Step 5: Upload the social preview**

Use the GitHub repository settings UI to upload `assets/social/laconian-alpha.png`. Read the page
back or capture a screenshot proving the preview is present. If permissions or plan limits reject
the change, preserve the asset in the repository and report the limitation.

- [ ] **Step 6: Tag and verify the immutable release**

```bash
git fetch origin main
git ls-remote --exit-code --tags origin refs/tags/v0.1.0-alpha.1
gh release view v0.1.0-alpha.1 --json url,tagName,isDraft,isPrerelease
```

Both existence checks must report that no tag/release exists. Read the merged commit from
`gh pr view --json mergeCommit`, verify it is an ancestor of `origin/main`, and tag that exact SHA:

```bash
release_commit=$(gh pr view --json mergeCommit --jq '.mergeCommit.oid')
git merge-base --is-ancestor "$release_commit" origin/main
git tag -a v0.1.0-alpha.1 "$release_commit" -m "Laconian v0.1.0-alpha.1"
git push origin v0.1.0-alpha.1
gh run list --workflow release.yml --branch v0.1.0-alpha.1 --limit 1 \
  --json databaseId,headSha,status,conclusion,url
```

Run `gh run watch` with the returned numeric database ID, then inspect the release:

```bash
gh release view v0.1.0-alpha.1 --json url,tagName,isDraft,isPrerelease,assets
```

Expected: a non-draft prerelease with the zip and `.sha256` asset. Download both into a fresh
directory created by `mktemp -d /private/tmp/laconian-release.XXXXXX`. From that exact directory,
run `shasum -a 256 -c laconian-plugin-v0.1.0-alpha.1.zip.sha256` and
`python3 -m zipfile -l laconian-plugin-v0.1.0-alpha.1.zip`. Confirm the allowlist and compare the
archived `skills/if/SKILL.md` bytes with `git show v0.1.0-alpha.1:skills/if/SKILL.md` without
rewriting either source.

- [ ] **Step 7: Final evidence report**

Report the PR, merge commit, main CI run, release URL, install commands, validation counts, social
asset paths, ready-to-post English/Russian copy, GitHub metadata/protection state, and any remaining
universal-directory or benchmark work. Do not describe the alpha as benchmark-proven, and do not
post to an external social account without a separately identified account and explicit send action.
