from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).parents[1]


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_required_license_files_exist() -> None:
    apache = ROOT / "LICENSE"
    assert "Apache License" in apache.read_text(encoding="utf-8")
    assert file_sha256(apache) == (
        "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
    )

    creative_commons = ROOT / "LICENSES/CC-BY-4.0.txt"
    assert "Attribution 4.0 International" in creative_commons.read_text(encoding="utf-8")
    assert file_sha256(creative_commons) == (
        "9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411"
    )

    caveman_mit = ROOT / "LICENSES/CAVEMAN-MIT.txt"
    assert file_sha256(caveman_mit) == (
        "f0abc56b6f49ab2e285bb6e6723f028abb7ebd4fe0e242bbdc2b4dded0ace8b9"
    )


def test_notice_maps_all_distributed_material() -> None:
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "skills/if/SKILL.md: Apache-2.0" in notice
    assert (
        "README files, docs/, evals/cases/, benchmarks/methodology.md, and published "
        "benchmark results: CC-BY-4.0." in notice
    )
    assert "evals/baselines/caveman/SOURCE.md: CC-BY-4.0." in notice
    assert "Full terms: LICENSES/CAVEMAN-MIT.txt." in notice


def test_caveman_fixture_is_the_reviewed_snapshot() -> None:
    fixture = ROOT / "evals/baselines/caveman/SKILL.md"
    digest = file_sha256(fixture)
    assert digest == "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"
    source = (fixture.parent / "SOURCE.md").read_text(encoding="utf-8")
    assert "Upstream: https://github.com/JuliusBrussee/caveman" in source
    assert "Path: `plugins/caveman/skills/caveman/SKILL.md`" in source
    assert "Commit: `781c384cafc28d7ca392014dbab569f985b5b2fd`" in source
    assert f"SHA-256: `{digest}`" in source
    assert "License: MIT" in source
