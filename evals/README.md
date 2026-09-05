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

The frozen public pipeline keeps original and derived evidence as separate, immutable layers:

- sealed generation evidence: all 36 capsule seals and verified scored projections, fixed
  manifests, cases, arm hashes, and dated tier/cache price snapshots;
- all 36 `HardScoreRequestSetV1` request sets, all 36 judge-request attachments, all 36 final
  `JudgeAttachmentV1` attachments, and the campaign-neutral `JudgeAttemptEvidenceV1` /
  `JudgeAttemptRootIndexV1` verification handoff, including empty boundaries and zero-call seals;
- exact `LayerRootIndexV1` members, `GenerationContextExpectationV1`,
  `GenerationContextIndexV1`, and `ProviderEvidenceIndexV1`, binding all four layers and the
  judge-attempt root to the verified campaign authority;
- distinct `reviewers.yaml` and `protocol-reviewers.yaml` identity registries: the former uses
  `benchmark-reviewer-registry-v2` with exact mode-compatible key bytes and Git identities, while
  the latter is the separate three-role `ProtocolReviewerRegistryV1`;
- three verified protocol-attestation envelopes and their raw Git-object archive, statements,
  bundle, tag binding, source-backed signature projections, and observation/creation receipts;
- `population-attachment.json`, `population.jsonl`, the sample manifest and blind packet,
  round-tripped through the neutral `write_audit_sample_root` boundary;
- the `write_audit_evidence_root` output: `audit-evidence.json`, `git-object-archive.json`, five
  `pull-request-sources/`, two `reviewer-chains/`, commitments, reveals, original labels,
  `adjudication-core.json`, both `signoffs/`, the final adjudication envelope, metrics, and two
  `github-review-sources/` with their independently reconstructed `github-review-records/`;
- the provider-derived `BootstrapArtifactV1` from `build_bootstrap_artifact`, retained as
  `bootstrap.json` with its complete frozen scenario-index matrix; machine analysis,
  human-readable report, `analysis-evidence.json`, and immutable `checksums.json`.

All three verified protocol-attestation envelopes, generation context, provider index, and
benchmark projection carry the same verified `workflow_root`.
`laconian_eval.benchmark.protocol_review` alone owns the exact 15-member `WorkflowInventoryV1`
schema; Runtime verifies and consumes its sealed root instead of defining another inventory.
`statistical_protocol_sha256` and the singular `audit_protocol_sha256` are authority-bound through
context/provider evidence and are the only accepted statistics/audit protocol values. They remain
identical in derived audit and analysis evidence; the singular audit digest does not alter the
approved granular attestation subject inventories.

The frozen live handoff names `Runtime.hard_score`, `Runtime.prepare_judge`, and
`Runtime.seal_judge` in `laconian_eval.campaign.runtime`, reachable only from
`_reconstruct_verified_runtime` with an in-memory verified generation-context expectation.
The later Publication handoff names `Publication.campaign.evaluation_stage.sample_audit`,
`Publication.campaign.evaluation_stage.seal_audit`, `Publication.campaign.evaluation_stage.analyze`,
and `Publication.campaign.evaluation_stage.verify`, reachable only from
`_reconstruct_verified_publication`. The `analyze` and `verify` operations remain separate;
neither live module imports the CLI. All seven standalone `laconian-benchmark` commands are
offline validation only, use the one canonical expectation file, and accept no raw expected-digest
flag. They are offline and non-evidentiary, not live authority entry points. These are staged
cross-slice contracts, not a claim that later live adapters or commands have already shipped.

The synthetic 36-capsule campaign is a test fixture, not benchmark results. It deliberately assigns
negative, inconclusive, and supported outcomes to synthetic observations under the fixed model
identifiers required by the current wire contract. Those identifiers only label fixture slots;
no provider is contacted and no outcome measures the corresponding live model. Deterministic
fixture bytes prove reconstruction, not benchmark superiority or future live model selection.

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
