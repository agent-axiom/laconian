import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

import tools.build_plugin_release as release_builder

ROOT = Path(__file__).parents[1]

EXPECTED = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "skills/if/SKILL.md",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "NOTICE",
    "LICENSES/CC-BY-4.0.txt",
)


def test_release_bundle_is_deterministic_and_allowlisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def non_unix_zip_info(
        filename: str,
        date_time: tuple[int, int, int, int, int, int],
    ) -> ZipInfo:
        info = ZipInfo(filename, date_time=date_time)
        info.create_system = 0
        return info

    monkeypatch.setattr(release_builder, "ZipInfo", non_unix_zip_info)
    assert release_builder.RELEASE_FILES == EXPECTED
    first = release_builder.build_release(ROOT, tmp_path / "one")
    second = release_builder.build_release(ROOT, tmp_path / "two")
    assert first.archive.read_bytes() == second.archive.read_bytes()
    with ZipFile(first.archive) as bundle:
        members = bundle.infolist()
        assert tuple(bundle.namelist()) == EXPECTED
        assert {member.create_system for member in members} == {3}
        assert {member.date_time for member in members} == {(1980, 1, 1, 0, 0, 0)}
        assert {member.external_attr for member in members} == {0o100644 << 16}
        assert {member.compress_type for member in members} == {ZIP_DEFLATED}
        assert bundle.read("skills/if/SKILL.md") == (ROOT / "skills/if/SKILL.md").read_bytes()
        manifest = json.loads(bundle.read(".codex-plugin/plugin.json"))
        assert manifest["version"] == "0.1.0-alpha.1"
    digest = hashlib.sha256(first.archive.read_bytes()).hexdigest()
    assert first.checksum.read_text(encoding="ascii") == f"{digest}  {first.archive.name}\n"
