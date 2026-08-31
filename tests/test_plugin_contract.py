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
