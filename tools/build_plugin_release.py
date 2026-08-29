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
