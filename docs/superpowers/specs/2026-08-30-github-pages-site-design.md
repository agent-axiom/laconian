# Laconian GitHub Pages Site Design

## Purpose

Create a small public site that explains the `if` skill and makes its one Markdown file easy to
inspect or download. The site presents the skill as the primary product; the benchmark appears
only as supporting, unfinished validation infrastructure.

## Audience and primary action

The audience is people who use agent hosts with Markdown skills and want concise answers without
losing correctness or necessary detail. The primary action is **Download `SKILL.md`**. Reading the
source and opening the GitHub repository are secondary actions.

## Content flow

The site is one English-language page with five compact sections:

1. **Thesis:** “The shortest complete answer.” A short explanation identifies `if` as a portable,
   one-file agent skill that cuts redundancy rather than substance.
2. **Illustrative edit:** A before/after response demonstrates removal of greetings, restatement,
   and repetition while preserving an important safety warning. It is explicitly labelled as an
   illustration, not benchmark output.
3. **Principles:** Complete first; cut redundancy, not substance; keep exact content exact.
4. **Install:** Download `SKILL.md`, save it as `<agent-skills-directory>/if/SKILL.md`, and note
   that the base directory depends on the host.
5. **Source:** Links to the skill, repository, methodology, and contribution guidance. It states
   that no public benchmark result is available yet.

The page must not claim that `if` saves a measured amount, outperforms another instruction, works
with every agent host, or always improves an answer.

## Visual direction

Use an austere editorial treatment: warm bone background, near-black text, one deep red accent,
serif display type, and monospace technical details. The layout uses generous negative space,
thin rules, square corners, and no decorative cards, gradients, stock imagery, ancient-warrior
motifs, or generic SaaS chrome. The social preview follows the same palette and typography.

The desktop layout uses a wide editorial grid; narrow screens collapse to one readable column.
All controls retain visible keyboard focus, text maintains strong contrast, and motion is limited
to small transitions disabled by `prefers-reduced-motion`.

## Architecture

Keep the site dependency-free under `site/`:

- `index.html` owns semantic structure, copy, metadata, and links.
- `styles.css` owns the complete responsive visual system.
- `favicon.svg`, `og.png`, `robots.txt`, and `sitemap.xml` provide browser and sharing metadata.
- `.github/workflows/pages.yml` stages `site/`, copies the canonical
  `skills/if/SKILL.md` into the deployment artifact, and deploys that artifact through the
  official GitHub Pages actions.

No client-side JavaScript, web fonts, cookies, analytics, storage, backend, or build framework is
needed. The canonical public URL is `https://agent-axiom.github.io/laconian/`.

## Verification and deployment

Automated tests check the required content, links, metadata, responsive and accessibility hooks,
social asset, and least-privilege Pages workflow. Existing Python tests, formatting, linting, and
type checks remain unchanged. A local static preview is checked at desktop and mobile widths before
the branch is merged. GitHub Pages is configured to deploy from Actions, and the production URL is
checked after the deployment succeeds.

