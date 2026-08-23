# Design

Laconian separates a tiny portable response skill from the project that tests it. This document
describes the implemented walking skeleton; the approved foundation specification remains in
`docs/superpowers/specs/` as development history.

## Boundary

The entire user-installable artifact is `skills/if/SKILL.md`. It is a Markdown-only instruction
file with no code, dependency, permission, reference, asset, or network requirement. Examples,
case data, providers, scoring, reports, and historical notes remain outside the skill so they do
not consume its runtime context.

The benchmark package is `laconian_eval`, requires Python 3.11 or newer, and exposes the
`laconian` command. It is provider-neutral at its core. Deterministic fake and replay providers
support offline development; the optional OpenAI adapter implements the first mocked live
contract.

## Components

- `models.py` defines immutable, strict Pydantic schemas for cases, manifests, raw attempts,
  scores, judge provenance, and summaries.
- `yaml_io.py` rejects duplicate mapping keys before schema validation.
- `cases.py` loads activation and response files, rejects duplicate IDs, and enforces one English
  and one Russian record per scenario.
- `arms.py` loads `baseline`, exact `Answer concisely.`, pinned Caveman, and exact `if` bytes and
  calculates instruction hashes.
- `runner.py` builds a seeded arm order, calls a provider, records bounded retry lineage, redacts
  configured secrets, and appends raw JSONL with flush-and-fsync boundaries.
- `scoring.py` rejects blank successes and applies exact-value, complete structured-mapping, and
  sentence constraints to terminal attempts.
- `judging.py` creates an optional blind semantic boundary with opaque response IDs and explicit
  judge provenance.
- `reporting.py` aggregates per-arm metrics and quality-gated `if` versus `concise` pairs without
  a composite rank.
- `cli.py` connects validation, run, score, and report commands and refuses to overwrite outputs.

## Data flow

```text
manifest + cases + arm bytes
  -> strict validation and deterministic run plan
  -> provider or replay response
  -> append-only raw JSONL
  -> deterministic hard checks
  -> optional blind semantic judgments
  -> quality-gated paired aggregation
  -> machine summary and Markdown report
```

The activation path is separate: stored prompts and expected decisions can test a routing proxy,
but they never affect response-quality metrics.

## Reproducibility

A manifest fixes the provider kind, requested model, case paths, arms, repetitions, arm-order
seed, `system_suffix` instruction location, generation settings, timeout, retry budget, and an
optional price snapshot. A raw record carries manifest, prompt, and instruction hashes along with
the provider and requested-model labels, the provider-returned model identifier when available,
attempt lineage, timestamps, text or classified error, and any public usage fields.

The CLI creates a unique UTC-stamped run directory and writes `manifest.json`, `raw.jsonl`, and
`run.log`. Scoring loads the manifest-declared case definitions from the checked-out revision,
requires the explicit `--cases` input to match them, and validates the complete planned key set,
retry chains, prompt and arm hashes, run identity, and consistent returned-model provenance before
creating `scored.jsonl` and `summary.json`. A publishable run pins the exact case files and
repository revision; raw rows do not currently contain a hash of the full rubric definition.
Reporting recomputes and verifies a sibling summary before rendering it.

## Safety and failure semantics

Configuration errors fail before a provider call. Authentication stops a run without retrying;
transient categories use the bounded manifest policy. Partial append-only artifacts remain
inspectable. Secret values are redacted from stored provider messages and request identifiers.

Benchmark prompts and outputs are untrusted data. Generated model text is never executed as code
or a shell command. It cannot change runner configuration, filesystem targets, credentials, or
scoring rules. Output writers use exclusive creation and reject existing targets.

## Scope limits

The walking skeleton has 24 bilingual response records and eight bilingual activation records,
not the deferred public corpus of 100 or more cases. It does not include live semantic judging,
human preference studies, host installation claims, confidence-interval computation, a hosted
leaderboard, or a composite score. Replay fixtures prove deterministic plumbing, not model
performance.

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
