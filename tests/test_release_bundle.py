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
