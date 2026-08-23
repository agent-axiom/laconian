from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_required_license_files_exist() -> None:
    assert "Apache License" in (ROOT / "LICENSE").read_text()
    assert "Attribution 4.0 International" in (ROOT / "LICENSES/CC-BY-4.0.txt").read_text()
    notice = (ROOT / "NOTICE").read_text()
    assert "skills/if/SKILL.md: Apache-2.0" in notice
    assert (
        "README files, docs/, evals/cases/, benchmarks/methodology.md, and published "
        "benchmark results: CC-BY-4.0." in notice
    )


def test_caveman_fixture_is_the_reviewed_snapshot() -> None:
    fixture = ROOT / "evals/baselines/caveman/SKILL.md"
    digest = sha256(fixture.read_bytes()).hexdigest()
    assert digest == "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"
    source = (fixture.parent / "SOURCE.md").read_text()
    assert "781c384cafc28d7ca392014dbab569f985b5b2fd" in source
    assert "MIT" in source
