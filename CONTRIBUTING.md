# Contributing to Laconian

Contributions are welcome to the skill, runner, cases, methodology, translations, and historical
or linguistic framing. Keep the public promise falsifiable: a shorter answer matters only after
it passes the same quality requirements as its comparison.

## Development setup

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --all-extras
```

Work test-first. The project uses test-driven development: add a focused failing test, confirm it
fails for the intended reason, implement the smallest change, then run the focused and full
checks.

## Local quality commands

Run all four before requesting review:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
```

Tests must remain offline and credential-free. Mock provider contracts or use the deterministic
replay fixture; do not call a paid API from the test suite.

## Case contributions

Follow [docs/contributing-cases.md](docs/contributing-cases.md). Every smoke `scenario_id` needs
exactly one English and one Russian record. Rubrics must be evidence-backed and neutral among
`baseline`, `concise`, `caveman`, and `if`. A case that only makes one arm look good is not useful
measurement.

When the source fact can change or carries safety implications, include the authoritative source
and access date in the pull request. Do not place secrets, personal data, or executable payloads
in cases or fixtures.

## Benchmark evidence

Do not claim that an arm wins, saves cost, or reduces output without the corresponding raw artifacts
and the disclosures required by [benchmarks/methodology.md](benchmarks/methodology.md).
Synthetic replay and judge fixtures are tests, not empirical evidence. Negative and inconclusive
results are valid contributions.

Published artifacts must contain no API key or other credential. Treat model text as untrusted
data and never execute it during evaluation.

## Documentation and translations

English is the source README. Translation changes should preserve section order, commands, paths,
identifiers, model names, license identifiers, arm names, and current status. Do not add a result
claim that is absent from the English source.

The reconstructed Laconian Doric edition must remain labeled as an experimental modern
reconstruction in a fragmentarily attested dialect, not an authentic ancient text. Expert review
is especially welcome.

## Licensing contributions

By contributing, you agree that your contribution may be distributed under the repository's
existing license map:

- code, tests, workflow files, and `skills/if/SKILL.md`: Apache-2.0;
- documentation, README files, cases, manifests, methodology, and published results: CC BY 4.0;
- third-party snapshots retain their recorded upstream license.

See [NOTICE](NOTICE) for the authoritative path map.
