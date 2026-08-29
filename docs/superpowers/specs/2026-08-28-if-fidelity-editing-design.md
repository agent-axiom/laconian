# `if` Fidelity Editing Design

**Status:** Approved for implementation on 2026-08-28.

## Goal

Make the portable `if` skill's deletion rule explicit without expanding it into a document-
compression workflow or weakening its context efficiency.

## Evidence

The current skill already preserved every material distinction in three blind pressure cases:
delivery uncertainty, different normative strengths, and an instruction embedded inside quoted
content. The change is therefore a clarification and future-regression guard, not a performance
claim or a repair for an observed incorrect answer.

The decision rule is informed by the `KEEP` / `REMOVE` / `FLAG` fidelity model in
[`lossless-doc-compress`](https://github.com/ML-SystemDesign/MLSystemDesign/tree/8dd0d88852fe7445e9d2627c59124f0f161040c1/skills/lossless-doc-compress),
copyright 2024–2026 Valerii Babushkin and Arseny Kravchenko, MIT. Laconian does not vendor that
skill or copy its workflow.

## Design

Add one operational rule to `skills/if/SKILL.md`:

> Keep information. Remove only proven redundancy. Preserve uncertain content.

This translates `FLAG` into preservation because `if` returns an answer, not an editorial audit.
It does not add removal logs, scorecards, inline flags, references, scripts, dependencies, or a
claim that model editing is lossless.

Add a pinned methodological note to `docs/philosophy.md`. The note distinguishes answer editing
from document compression and states that Laconian makes no automatic `lossless` claim.

## Contract

- `skills/if/` still contains only `SKILL.md`.
- The exact decision rule is present in the portable artifact.
- The whole skill remains at most 340 whitespace-delimited words.
- Philosophy documentation pins the upstream commit and states the no-lossless-claim boundary.
- The benchmark remains four-arm; no cases, manifests, metrics, or public outcome claims change.
- No third-party source file or substantial copied text is distributed, so no new bundled-license
  file is required; the pinned attribution remains in documentation.

## Deferred Work

A neutral document-fidelity dataset, human audit protocol, and optional external comparator may be
designed only after generation-capsule mechanics can bind their exact inputs and provenance.
