# Changelog

All notable project changes will be recorded here.

## [Unreleased]

## [0.1.0-alpha.1] - 2026-08-30

### Added

- A one-file, Markdown-only `if` skill for the shortest complete answer.
- A provider-neutral Python walking skeleton with strict case, manifest, raw, scored, judgment,
  and summary models.
- Four comparison arms: `baseline`, exact `Answer concisely.`, pinned `caveman`, and `if`.
- Twelve response scenarios paired in English and Russian, plus four paired activation scenarios.
- Deterministic fake/replay providers and an optional OpenAI Responses adapter with mocked
  contract coverage.
- Append-only attempts, bounded retry lineage, secret redaction, deterministic checks, optional
  blind semantic judgment attachment, quality-gated pairing, and non-composite reports.
- Immutable scoring provenance that binds manifests and raw attempts to the runner version and
  every complete response-case definition, with the same hashes disclosed in summaries and
  reports.
- Mixed-license attribution for Apache-2.0 project code and skill, CC BY 4.0 documentation and
  benchmark materials, and the MIT Caveman fixture.
- Public philosophy, methodology, case-contribution, contributor, and security documentation.

No public benchmark result is included in this experimental walking skeleton.
