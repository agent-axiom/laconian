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
