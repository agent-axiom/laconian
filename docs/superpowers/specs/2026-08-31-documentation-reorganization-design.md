# Documentation Reorganization Design

**Date:** 2026-08-31

## Goal

Make the repository entry point genuinely concise while preserving the current public facts in
focused documents. Move localized README editions out of the repository root and keep every
edition structurally aligned with the English source.

## Current problem

The root `README.md` is 169 lines and combines project status, skill behavior, installation,
benchmark design, commands, repository structure, contribution rules, licensing, and historical
sources. Five similarly long translations duplicate that structure in the repository root.

Much of the detailed material already overlaps `docs/philosophy.md`,
`benchmarks/methodology.md`, `evals/README.md`, `CONTRIBUTING.md`, and `NOTICE`. The translations
also use root-relative links, and `tests/test_public_contract.py` hard-codes their current paths
and the long English section order.

## Chosen approach

Use a small documentation hub and two focused entry guides:

```text
README.md
docs/
  README.md
  using-the-skill.md
  philosophy.md
  design.md
  contributing-cases.md
  i18n/
    README.ru.md
    README.zh-CN.md
    README.el.md
    README.it.md
    README.grc-x-laconian.md
  superpowers/
    plans/
    specs/
benchmarks/
  README.md
  methodology.md
evals/
  README.md
```

`CHANGELOG.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain in the root because those names and
locations are standard repository entry points. The historical `docs/superpowers/` tree remains
where it is; moving development history would add broad link churn without improving the active
documentation path.

## Root README contract

The English README becomes a stable 40–70 line overview with this order:

1. Website and language navigation.
2. Existing banner, title, and the shortest-complete-answer promise.
3. One short project description: a portable Markdown skill plus an open benchmark.
4. A compact status statement that says the project is pre-release, has no public benchmark
   result, and does not treat replay fixtures as performance evidence.
5. A `Start here` section linking to the skill, usage guide, and benchmark guide.
6. A `Documentation` section linking to the documentation index.
7. Compact contribution, private security-reporting, and licensing links.

The root README does not retain full installation instructions, the four-arm table, scoring
details, live-run warnings, the repository map, the historical discussion, or the complete
license map. It links to their authoritative documents instead.

## Focused documents

### `docs/README.md`

Acts as the human-facing documentation index. It groups links under project concepts, usage,
benchmarking, contribution, translations, and development history. It does not repeat the
contents of those documents.

### `docs/using-the-skill.md`

Owns the practical skill documentation currently in the root README:

- what `if` does and does not do;
- the one-file portability boundary;
- installation and removal commands;
- links to `skills/if/SKILL.md` and the project philosophy.

### `benchmarks/README.md`

Owns the operational benchmark overview:

- the purpose of the four comparison arms;
- the quality-before-brevity rule;
- the credential-free replay quickstart;
- the optional live-run command and its cost, availability, and credential warnings;
- links to `methodology.md` for the publication contract and `../evals/README.md` for input data.

Formal methodology remains only in `benchmarks/methodology.md`; the new overview must not copy
its full reproducibility and accounting specification.

### `docs/philosophy.md`

Keeps its current editing philosophy and gains the careful explanation of the name `if`, the
status of Plutarch's later account, the attested word `αἴκα`, the Polybius caveat, and the
existing historical and linguistic source links. The move must not strengthen the anecdote into
a historical claim unsupported by those sources.

## Localizations

All five localized README editions move together to `docs/i18n/` and become concise structural
translations of the new English README. They retain the same status caveats and navigation
destinations, while detailed project documents remain English-only for this change.

The language switcher in `README.md` targets `docs/i18n/README.<locale>.md`. Each localized file
links back to `../../README.md` and uses sibling filenames for the other localized editions.
Links from localized files to repository-root resources use `../../`; command paths remain
repository-root paths because the commands are run from the repository root.

The reconstructed Laconian Doric edition keeps its bilingual experimental-reconstruction warning
and must continue to say that it is not an authentic ancient text.

## Link and contract handling

Active documents must have valid relative Markdown links after the move. Historical plans and
specifications may continue to mention the paths that existed when they were written; they are
development records, not live navigation targets.

`tests/test_public_contract.py` will be updated to:

- use the new localized file paths;
- calculate language-switcher targets relative to each source document;
- assert the new concise English section order;
- verify that benchmark commands and warnings live in `benchmarks/README.md`;
- verify that historical framing and sources live in `docs/philosophy.md`;
- preserve the licensing, status, and reconstruction safeguards;
- check local links in the active README and documentation entry points.

The link check is intentionally scoped to active documentation and excludes historical
`docs/superpowers/` records.

## Validation

The implementation is accepted when:

1. Only `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain as Markdown files
   in the repository root.
2. The English README is between 40 and 70 lines and contains no detailed benchmark table or
   multi-command run procedure.
3. All five localized editions live under `docs/i18n/`, follow the concise structure, and link
   correctly to English and one another.
4. No public performance or cost-savings claim is introduced.
5. The offline and optional live commands remain exact and discoverable in
   `benchmarks/README.md`.
6. All active local Markdown links resolve.
7. The focused public-contract tests and the full repository test suite pass.
8. Package metadata still builds from the root `README.md`.

## Non-goals

- Translating the detailed documentation.
- Moving or rewriting historical `docs/superpowers/` plans and specifications.
- Changing benchmark behavior, schemas, CLI commands, skill instructions, or website content.
- Cleaning unrelated untracked images, `output/`, or `.DS_Store` files.
