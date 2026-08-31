# Evaluation data

The `evals/` tree stores benchmark inputs and reproducibility metadata. It does not store a
successful result by implication: inputs, test fixtures, and public evidence have different
roles.

## Cases

`evals/cases/` contains versioned YAML inputs:

- `response-smoke.yaml` has 12 scenarios, each represented once in English and once in Russian;
- `activation-smoke.yaml` has four routing scenarios in the same two-language pairing.

The response suite applies each comparison arm deliberately. The activation suite stores the
expected selection decision and maintainer rationale. Activation rationales are not model input,
and proxy routing data cannot establish compatibility with a named agent host.

See [the case contribution guide](../docs/contributing-cases.md) for the exact schemas and
neutrality rules.

### Evaluation neutrality

Deterministic gates must be grounded in the user prompt. Only `user-decline-en` and
`user-decline-ru` are sentence-gated because those prompts explicitly require exactly two
sentences. Warning severities are frozen before evaluation: `material` marks a consequential risk
that must be preserved, while `critical` marks an urgent safety risk whose omission could cause
severe harm. These preregistered labels define evaluation handling; they do not make benchmark
claims.

## Manifests

`evals/manifests/` fixes the exact `runner_version`, provider configuration, case paths, arm
identifiers, repetitions, arm-order seed, instruction placement, generation settings, retry
policy, and an optional dated price snapshot. A manifest for another package version is rejected
instead of being silently reinterpreted.

- `replay-smoke.yaml` is the credential-free offline path used by tests and the quickstart.
- `openai-example.yaml` is an optional live-run example, not a recorded benchmark result. Model
  availability and pricing can change; a public run must retain its actual dated configuration.

Relative paths declared by the current CLI are resolved from the working directory, so run the
documented commands from the repository root.

## Baseline fixture

`evals/baselines/caveman/` contains an offline, byte-pinned Caveman snapshot plus source, commit,
hash, and MIT license metadata. It is a comparison fixture, not a Laconian-distributed skill.

## Test fixtures

`tests/fixtures/` contains synthetic provider responses and synthetic semantic judgments for
deterministic tests. They are not benchmark results and must never be cited as evidence about a
live model or provider.

## Published results

`benchmarks/results/` is reserved for future immutable public evidence. A publishable run includes
the copied manifest, all raw attempts and failures, scored records, machine summary, report,
source-case and arm provenance, and any semantic-judge metadata required by the
[methodology](../benchmarks/methodology.md).

Raw and scored attempts carry `case_definition_sha256`; summaries and reports carry the same
canonical hashes for every complete response-case definition. Changing a deterministic constraint
or semantic rubric therefore invalidates old scoring evidence even when the prompt text is
unchanged. The walking skeleton starts this directory empty except for `.gitkeep`.

## Validation

From the repository root:

```bash
uv run laconian validate evals/cases/response-smoke.yaml
uv run laconian validate evals/cases/activation-smoke.yaml
uv run laconian validate evals/manifests/replay-smoke.yaml
uv run laconian validate evals/manifests/openai-example.yaml
```

Eval cases and manifests are licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt). The Caveman
fixture keeps its upstream MIT license.
