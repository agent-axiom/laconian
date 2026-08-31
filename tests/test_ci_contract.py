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


def test_ci_validates_skill_and_plugin() -> None:
    workflow = _workflow("ci.yml")
    runs = [step.get("run", "") for step in workflow["jobs"]["quality"]["steps"]]
    contract = "uv run pytest tests/test_skill_contract.py tests/test_plugin_contract.py -q"
    assert runs.count(contract) == 1
    assert runs.index("uv run mypy src") < runs.index(contract) < runs.index("uv run pytest -q")


def test_release_workflow_builds_tagged_assets() -> None:
    path = ROOT / ".github/workflows/release.yml"
    assert path.is_file(), "release workflow is missing"
    raw = path.read_text(encoding="utf-8")
    workflow = _workflow("release.yml")
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"push": {"tags": ["v0.1.0-alpha.1"]}}
    assert workflow["permissions"] == {"contents": "read"}

    release = workflow["jobs"]["release"]
    assert release["runs-on"] == "ubuntu-latest"
    assert release["permissions"]["contents"] == "write"
    steps = release["steps"]
    assert steps[0]["uses"] == ("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1")
    assert steps[1]["uses"] == ("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97")
    assert steps[1]["with"]["python-version"] == "3.11"

    runs = "\n".join(step.get("run", "") for step in steps)
    assert "python tools/build_plugin_release.py --output-dir dist" in runs
    assert 'sha256sum -c "laconian-plugin-${GITHUB_REF_NAME}.zip.sha256"' in runs
    assert "gh release create" in runs
    assert '"dist/laconian-plugin-${GITHUB_REF_NAME}.zip"' in runs
    assert '"dist/laconian-plugin-${GITHUB_REF_NAME}.zip.sha256"' in runs
    assert "--verify-tag" in runs
    assert "--prerelease" in runs
    assert '--title "Laconian ${GITHUB_REF_NAME}"' in runs
    assert "--notes-file docs/releases/v0.1.0-alpha.1.md" in runs
    publish = next(step for step in steps if step.get("name") == "Publish GitHub prerelease")
    assert publish["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1" in raw
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0" in raw
