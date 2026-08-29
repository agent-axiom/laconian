from __future__ import annotations

import re
import struct
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "website"
PAGE = SITE / "index.html"
STYLES = SITE / "styles.css"
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes.append(dict(attrs))


def test_static_directory_does_not_shadow_stdlib_site() -> None:
    assert not (ROOT / "site").exists()


def test_page_has_skill_first_content_and_metadata() -> None:
    html = PAGE.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(html)

    assert '<html lang="en">' in html
    assert "The shortest complete answer." in html
    assert "portable" in html.lower()
    assert "one-file" in html.lower()
    assert "Illustrative edit — not benchmark output." in html
    assert "no public benchmark result is available yet" in html.lower()
    assert {"header", "nav", "main", "section", "footer"} <= set(parser.tags)
    assert {"top", "example", "principles", "install", "source"} <= {
        attrs.get("id") for attrs in parser.attributes
    }
    assert 'href="SKILL.md"' in html
    assert 'href="styles.css"' in html
    assert 'href="https://agent-axiom.github.io/laconian/"' in html
    assert 'content="https://agent-axiom.github.io/laconian/og.png"' in html
    assert "CC BY 4.0 documentation" in html


def test_page_avoids_unfounded_performance_claims() -> None:
    html = PAGE.read_text(encoding="utf-8").lower()
    for claim in ("proven to", "saves tokens", "outperforms", "always better"):
        assert claim not in html


def test_styles_include_accessible_responsive_states() -> None:
    css = STYLES.read_text(encoding="utf-8")
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert re.search(r"@media\s*\([^)]*max-width", css)
    assert "@import" not in css
    assert "http://" not in css
    assert "https://" not in css


def test_dark_focus_and_print_code_remain_visible() -> None:
    css = STYLES.read_text(encoding="utf-8")
    print_rules = css[css.index("@media print") :]

    assert ".install-section a:focus-visible" in css
    assert "outline-color: var(--paper);" in css
    assert ".install-lede code," in print_rules
    assert ".install-path code" in print_rules
    assert "background: #fff;" in print_rules
    assert "color: #000;" in print_rules


def test_social_preview_has_expected_png_dimensions() -> None:
    data = (SITE / "og.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (1200, 630)


def test_pages_workflow_uses_split_least_privilege_jobs() -> None:
    raw = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    package = workflow["jobs"]["package"]
    deploy = workflow["jobs"]["deploy"]

    assert workflow["permissions"] == {}
    assert package["permissions"] == {"contents": "read"}
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert deploy["needs"] == "package"
    assert "skills/if/SKILL.md" in raw
    assert "_site/SKILL.md" in raw
    assert "pull_request_target" not in raw
    assert "write-all" not in raw
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in raw
    assert "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9" in raw
    assert "actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128" in raw
