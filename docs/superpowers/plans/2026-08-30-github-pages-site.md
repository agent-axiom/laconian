# Laconian GitHub Pages Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a dependency-free one-page site that presents `if` as a portable agent skill and makes its canonical Markdown file easy to download.

**Architecture:** Semantic HTML and a single CSS file live in `site/`; there is no client-side JavaScript or framework. A least-privilege GitHub Actions workflow stages the site with the canonical `skills/if/SKILL.md`, uploads one Pages artifact, and deploys it from `main`.

**Tech Stack:** HTML5, CSS, SVG, pytest, PyYAML, GitHub Actions, GitHub Pages

---

### Task 1: Add a failing static-site contract

**Files:**
- Create: `tests/test_site.py`

- [ ] **Step 1: Write the failing tests**

Create tests that read the future page, stylesheet, assets, and workflow directly:

```python
from __future__ import annotations

import re
import struct
from html.parser import HTMLParser
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGE = SITE / "index.html"
STYLES = SITE / "styles.css"
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[dict[str, str | None]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.tags.append(tag)
        self.attributes.append(dict(attrs))


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
```

- [ ] **Step 2: Run the site tests and verify RED**

Run: `uv run pytest tests/test_site.py -q`

Expected: FAIL because `site/index.html` does not exist.

- [ ] **Step 3: Commit the failing contract**

```bash
git add tests/test_site.py
git commit -m "test: define GitHub Pages site contract"
```

### Task 2: Build the dependency-free landing page

**Files:**
- Create: `site/index.html`
- Create: `site/styles.css`
- Create: `site/favicon.svg`
- Create: `site/og.png`
- Create: `site/robots.txt`
- Create: `site/sitemap.xml`

- [ ] **Step 1: Add the semantic page**

Implement one page with this exact hierarchy and copy requirements:

```html
<header>
  <a href="#top" aria-label="Laconian home">Laconian <span>if</span></a>
  <nav aria-label="Primary">
    <a href="#example">Example</a>
    <a href="#principles">Principles</a>
    <a href="#install">Install</a>
    <a href="https://github.com/agent-axiom/laconian">GitHub</a>
  </nav>
</header>
<main id="main">
  <section id="top">
    <p>Portable agent skill · One Markdown file</p>
    <h1>The shortest complete answer.</h1>
    <p><code>if</code> asks an agent to cut redundancy, never what the answer needs to be correct, safe, clear, and complete.</p>
    <a href="SKILL.md" download>Download SKILL.md</a>
    <a href="https://github.com/agent-axiom/laconian/blob/main/skills/if/SKILL.md">Read the source</a>
  </section>
  <section id="example">
    <p>Illustrative edit — not benchmark output.</p>
    <h2>Less, without losing the point.</h2>
    <p>Prompt: How do I delete a local Git branch named <code>demo</code>?</p>
    <article aria-label="Before applying if">
      <p>Sure — to delete the local Git branch named <code>demo</code>, run this command:</p>
      <pre><code>git branch -d demo</code></pre>
      <p>The <code>-d</code> flag protects unmerged work. If Git refuses, you can use
      <code>-D</code>, but only when you intentionally accept losing those commits.</p>
    </article>
    <article aria-label="After applying if">
      <pre><code>git branch -d demo</code></pre>
      <p>Git refuses if <code>demo</code> has unmerged commits; use <code>-D</code> only if you
      intentionally accept losing them.</p>
    </article>
  </section>
  <section id="principles">
    <h2>Complete first.</h2>
    <ol>
      <li>Complete first</li>
      <li>Cut redundancy, not substance</li>
      <li>Keep exact content exact</li>
    </ol>
  </section>
  <section id="install">
    <h2>Install one Markdown file.</h2>
    <code>&lt;agent-skills-directory&gt;/if/SKILL.md</code>
    <a href="SKILL.md" download>Download SKILL.md</a>
  </section>
  <section id="source">
    <h2>Open source, open method.</h2>
    <p>The benchmark is under active development; no public benchmark result is available yet.</p>
  </section>
</main>
<footer>Apache-2.0 code and skill · CC BY 4.0 documentation</footer>
```

Set complete metadata for title, description, canonical URL, Open Graph, X/Twitter, theme color,
favicon, and `og.png`. Use relative asset links so the page works at the `/laconian/` project path.

- [ ] **Step 2: Add the editorial visual system**

Define and use these tokens in `:root`:

```css
:root {
  --paper: #f4efe4;
  --paper-deep: #e8dfcf;
  --ink: #181713;
  --muted: #686257;
  --red: #982d27;
  --rule: #c9c0b1;
  --display: Georgia, "Times New Roman", serif;
  --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}
```

Use a maximum content width of `1180px`, a fluid display scale based on `clamp()`, a desktop
editorial grid, and a single-column layout below `760px`. Include a skip link, visible
`:focus-visible` treatment, touch-sized primary actions, selection colors, print-safe defaults,
and a `prefers-reduced-motion: reduce` override. Do not load remote fonts or imagery.

- [ ] **Step 3: Add metadata assets**

Create a small `if` typographic SVG favicon, copy the reviewed 1200×630 social image to
`site/og.png`, allow all crawlers in `robots.txt`, and put only the canonical home URL in
`sitemap.xml`.

- [ ] **Step 4: Run the page tests and verify the page tests pass while workflow test remains RED**

Run: `uv run pytest tests/test_site.py -q`

Expected: only `test_pages_workflow_uses_split_least_privilege_jobs` fails because the workflow
does not exist yet.

- [ ] **Step 5: Commit the page**

```bash
git add site tests/test_site.py
git commit -m "feat: add Laconian landing page"
```

### Task 3: Deploy through GitHub Pages

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `README.md`

- [ ] **Step 1: Add the least-privilege workflow**

```yaml
name: Deploy Pages

on:
  push:
    branches: [main]
    paths:
      - "site/**"
      - "skills/if/SKILL.md"
      - ".github/workflows/pages.yml"
  workflow_dispatch:

permissions: {}

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  package:
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    steps:
      - name: Checkout
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Stage and validate static site
        shell: bash
        run: |
          test -f site/index.html
          if find site -type l -print -quit | grep -q .; then
            echo "::error::site/ must not contain symbolic links"
            exit 1
          fi
          mkdir _site
          cp -R site/. _site/
          cp skills/if/SKILL.md _site/SKILL.md
      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0
        with:
          path: _site

  deploy:
    needs: package
    runs-on: ubuntu-24.04
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128 # v5.0.0
```

- [ ] **Step 2: Add the website link to the README language bar**

Prepend `[Website](https://agent-axiom.github.io/laconian/) · ` to the first line of `README.md`.

- [ ] **Step 3: Run the focused tests and verify GREEN**

Run: `uv run pytest tests/test_site.py -q`

Expected: `5 passed`.

- [ ] **Step 4: Run repository validation**

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
```

Expected: all commands exit zero; the existing filesystem-specific skip may remain.

- [ ] **Step 5: Commit deployment support**

```bash
git add .github/workflows/pages.yml README.md
git commit -m "ci: deploy site to GitHub Pages"
```

### Task 4: Preview, review, and publish

**Files:**
- Verify only; fix earlier files only if a check finds a concrete defect.

- [ ] **Step 1: Stage the exact deployment artifact locally**

Create a temporary directory, copy `site/` into it, and copy `skills/if/SKILL.md` to its root as
`SKILL.md`. Serve that directory with Python's static HTTP server.

- [ ] **Step 2: Check the local site**

Confirm a successful HTTP response, then inspect the first viewport, before/after comparison,
mobile layout, focus states, social metadata, and `SKILL.md` download. Fix only concrete defects and
rerun focused tests after any edit.

- [ ] **Step 3: Request independent code review**

Give the reviewer the design, plan, base SHA, head SHA, and requirement that the site must be
skill-first, claim-safe, accessible, dependency-free, and deployable at `/laconian/`. Resolve every
Critical or Important finding and rerun validation.

- [ ] **Step 4: Push the branch, open a pull request, and wait for CI**

Push `codex/github-pages-site`, create a PR into `main`, and merge only after required checks and
review pass.

- [ ] **Step 5: Enable Pages and restrict deployment to `main`**

Use the GitHub Pages REST API to set `build_type=workflow`, create or update the `github-pages`
environment, and allow deployments only from `main`.

- [ ] **Step 6: Verify production**

Wait for the Pages workflow, then confirm that
`https://agent-axiom.github.io/laconian/` and its `SKILL.md` return successful responses, the page
metadata uses the production URL, and the repository homepage points to the deployed site.
