# Laconian benchmark methodology

This document freezes the statistical and audit contract for the three-model public benchmark.
Synthetic replay and the walking skeleton verify the data path; neither is a public model
benchmark or evidence of a performance advantage. Legacy reports and sealed public analysis are
different artifact formats and must not be pooled.

## Questions kept separate

The benchmark has two suites because they answer different questions:

1. The **activation suite** asks whether an agent host should select `if` for a user request.
   Stored expectations and local routing checks are proxies. A compatibility claim about a named
   host requires execution in that host.
2. The **response suite** deliberately applies each comparison instruction and measures the
   resulting answer. It bypasses automatic skill selection.

Activation accuracy is never combined with response quality or brevity.

## Fixed comparison arms

The four arm identifiers and contents are:

- `baseline`: no added instruction; its instruction hash is the SHA-256 of zero bytes;
- `concise`: exactly `Answer concisely.`;
- `caveman`: the full offline fixture from `JuliusBrussee/caveman`, pinned to upstream commit
  `781c384cafc28d7ca392014dbab569f985b5b2fd`, with fixture SHA-256
  `1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8` and MIT attribution;
- `if`: the exact bytes of `skills/if/SKILL.md` in the recorded repository revision.

Every attempt records the selected arm and its instruction SHA-256. A public run must also name
the repository revision and retain the Caveman provenance file. Changing any arm content creates
a different experiment; results from different hashes are not pooled.

## Forced instruction placement

The manifest fixes `instruction_placement: system_suffix`. In the current runner this means that
the complete arm content occupies the provider request's stable `instructions` slot; `baseline`
uses no added instructions. The user prompt is unchanged. A run must keep provider, exact model
identifier, generation settings, case text, repetition index, and available tools fixed across
arms. Host-specific prompt assembly must be disclosed and must not give one arm a privileged
location.

For OpenAI runs, `model` records the requested manifest identifier and `response_model` records
the public model identifier returned by the API. Every successful record must contain the latter,
and scoring rejects a run if successful records resolve to different models. Requested and
returned identifiers must both be disclosed; an alias is not silently presented as a dated model.

## Cases, repetitions, and randomization

Response scenarios are represented as an English/Russian pair with one shared `scenario_id`.
Activation scenarios use the same pairing rule but are not response records. The manifest fixes
`runner_version`, case files, repetition count, and arm-order seed. The runner accepts only its
current package version. Every attempt records `case_definition_sha256`, the canonical SHA-256 of
the complete response-case definition, including identity, locale, category, prompt,
deterministic constraints, and semantic rubric. Editing any of those fields creates different
evidence even when the prompt is unchanged.

For each case and repetition, the runner shuffles only the four-arm order with the recorded
arm-order seed. Case order remains the validated file order. A publication must report the
number of scenarios, localized records, repetitions, and terminal responses; a single smoke
repetition is architecture verification, not enough for an efficiency conclusion.

The confirmatory campaign has three generation models, 12 scenarios with both locales, four
arms, and five repetitions: 36 sealed scenario capsules and 1,440 planned terminal rows. Each
model contributes 480 rows and exactly 120 planned case/repetition keys per arm. The input tag
fixes the campaign seed, model identities, protocols, corpus, and arm contents before generation.

## Attempts, errors, and retries

Configuration and schema validation happen before provider calls. Transient rate-limit,
timeout, connection, and server failures may be retried only up to the manifest's bounded retry
budget. Every attempt remains in `raw.jsonl` with its attempt number, retry parent, terminal flag,
and recorded backoff. Exhausted retries and non-retryable errors are results, not missing rows.

An authentication error is non-retryable and stops the run. The partial raw file and incomplete
run log remain inspectable. Retry attempts count toward operational metrics but only a terminal
record is scored for a planned case/arm/repetition key.

Every provider-ready public judge request binds the exact API pair `"service_tier": "default"`.
Each attempt records returned tier evidence and the closed `service_tier_status` vocabulary:
`reported_default`, `not_applicable_definitely_not_sent`,
`not_applicable_definitely_rejected`, `missing`, or `mismatch`. A definite pre-response rejection
such as HTTP 429, with no response or usage, records `not_applicable_definitely_rejected` and may
be retried within the frozen limit. Missing or nondefault tier after a received response, or
unknown delivery, stops without entering accepted judge evidence and retains worst-case spend
exposure. No inferred default or absence of a response proves successful delivery.

## Quality gates

Scoring is ordered:

1. Check raw identity against the copied manifest and source case.
2. Apply the **hard gate**: provider success with a nonblank output, required and forbidden
   literals, one complete top-level JSON or YAML mapping with exactly the declared keys, and
   sentence bounds.
3. Apply the **semantic gate** to every public hard-pass response: required facts and warnings
   are judged from a request that omits arm, provider, model, token count, and length. Semantic
   scoring remains optional only for the legacy walking-skeleton workflow.
4. Establish task success before calculating paired brevity.

Semantic results include judge provider, model, and prompt SHA-256. A semantic-gated report is
invalid if any hard-pass response lacks a judgment. Public semantic claims require a frozen judge
protocol and a disclosed human audit sample; the walking skeleton only attaches supplied judgment
records.

**A failed answer cannot win** because it is short.

For the fixed public population, `H = 1` means terminal provider success and a passed hard gate;
`S = 1` additionally requires a semantic pass. Provider-rejected, retry-exhausted, blank, and
hard-fail terminal rows have `H = S = 0`. The rates are `sum(H) / 120` and `sum(S) / 120`, not
semantic success conditional on surviving the hard gate. Missing keys, ambiguous delivery,
authentication stops, inconsistent model identity, or unverifiable provenance invalidate
inference; they are not imputed as zero-quality observations.

## Paired eligibility

The primary comparison is `if` versus `concise`. A pair is eligible only when both terminal
records belong to the same run, manifest, matched case/repetition, and both pass the selected
hard or semantic gate. Failed or missing arms remove that pair from the brevity calculation; they
remain visible in success and error counts.

The reported delta is `concise - if`. A positive token or character delta means the eligible
`if` output is shorter. `baseline` and `caveman` provide context, not an easier replacement for
the primary hypothesis.

Public brevity uses `visible_output_tokens = output_tokens - reasoning_tokens`. Its estimator
is the median matched visible-token delta, not a billed-output or cost-saving estimate. Every
claim is explicitly **among jointly successful matched responses**. It does not establish
unconditional token, total-token, or cost savings across planned requests. Characters remain a
separate descriptive measurement and never substitute for tokens.

Eligible pairs and token pairs are separate counts. A confirmatory result requires at least 96
eligible pairs from at least 10 of 12 scenarios, with provider-reported output and reasoning
tokens for every eligible pair. A missing token pair cannot be silently dropped to satisfy the
gate. Both arms retain the same 120-key planned denominator, including terminal failures.

## Metrics and accounting limitations

Reports keep separate, non-composite values for:

- hard-pass counts and rates;
- semantic pass counts, rates, and judgment coverage when judgments exist;
- provider errors, retries, exact-value violations, and format violations;
- median output characters and provider-reported output tokens when available;
- eligible paired token and character deltas;
- input, output, total, and cached-input tokens in raw records when the provider exposes them;
- latency and request metadata in raw attempts;
- price estimates only under the conditions below.

Token counts depend on the provider and model tokenizer. Character counts are not tokens. Cache
fields have provider-specific meanings, and cross-provider cache or cost totals must be shown
separately.

Legacy cost estimates require an explicit dated price snapshot in the manifest: effective date,
source URL, currency, normal input rate, optional cached-input rate, and output rate. The calculation prices
uncached input, cached input, and output separately. If successful records lack usage or cache
accounting, the affected estimate is `n/a`. It is an estimate, not an invoice.

For sealed public analysis, keep ordinary uncached input, cache-read input, `cache_write_tokens`,
visible output, reasoning output, billed output, total tokens, characters, and latency separate.
The five priced components are uncached input, cache reads, cache writes, visible output, and
reasoning output under the exact requested model's sealed, tier- and cache-dimensioned snapshot.
Each component is independently rounded up to micro-USD before summation. A trusted usage estimate
and a `retained_worst_case` reservation exposure have different cost-availability bases; neither
is an invoice or a verified campaign spend ledger. The later Runtime/Publication authority must
independently reconcile that ledger. Missing cache-write detail and forbidden nonzero writes
remain explicit integrity limitations adjacent to the affected cost and outcome, not zero writes.

## Confidence intervals for public runs

Every confirmatory confidence interval is two-sided 95%. NumPy `Generator(PCG64)` draws 10,000
scenario-cluster bootstrap replicates from the 12 canonical scenario UIDs in byte order. Each
replicate samples 12 scenarios with replacement and retains both locales, repetitions, and
matched arms within each sampled block. It recomputes the complete estimator and uses type-7
empirical quantiles at 0.025 and 0.975. Ties are retained. Fewer than 9,990 valid replicates makes
the corresponding decision inconclusive. Seed, scenario order, metadata, and the full index
matrix are sealed in the bootstrap artifact, so reconstruction uses the same vectors.

The uncertainty target is `scenario-superpopulation-conditional-on-fixed-campaign`; coverage is
nominal 95% approximate with only 12 clusters. It does not generalize to new models, provider
versions, prompts, domains, or time periods. Paired visible-token medians, raw arm pass
proportions, and paired pass-rate differences use this same clustered method. Unclustered Wilson
intervals are at most explicitly labelled naive diagnostics, never confirmatory uncertainty.

Every point estimate has its interval, fixed denominator, scenario coverage, eligible-pair count,
token-pair count, and missingness adjacent to it. The paired quality difference is `if - concise`
over all 120 planned keys. Hard and sensitivity-adjusted semantic non-inferiority each require
the lower bound to be strictly greater than -0.05, the frozen five-percentage-point margin.

The walking-skeleton CLI does not calculate confidence intervals. Its legacy reports remain
reproducibility checks; the sealed public analysis layer owns the clustered intervals above.

## Human audit and uncertainty

The deterministic audit targets exactly 144 judged records in 24 model/locale/arm strata, with
an initial quota of six per stratum. Judge-pass primary-arm `safety-medical` records are certainty
units with inclusion probability one. Noncertainty cells additionally split on blinded judge
decision. Exact Hamilton largest-remainder allocation and bytewise tie-breaking distribute
local seats; deterministic global-fill passes repair shortfalls. The manifest retains cell
populations, selected counts, probabilities, seeds, and permutations. The target expands if
certainty units exceed 144; population exhaustion is disclosed rather than inventing records.

Two preregistered, independent reviewers label the same blinded packet under commit-reveal.
Both label commitments merge before either reveal. Original labels remain immutable; a separate
adjudication records every consensus decision and rationale, with both reviewers' source-backed
signoffs. The packet omits model, arm, order, token counts, explicit length, latency, judge
decision, and provider metadata. Missing or stale signoffs cannot seal the audit; valid signoffs
may retain explicit unresolved disagreements, making the affected semantic result inconclusive.

A sampled noncertainty record has weight `w = N_h / n_h`; a certainty unit has weight one.
Report cells, weights, weighted confusion tables, and denominators. Judge-consensus agreement is
`sum(w * I[judge = consensus]) / sum(w)`. False-pass rate conditions on judge-pass records;
false-fail rate conditions on judge-fail records and is reported separately for each model and
primary arm. Human-human agreement and weighted kappa are descriptive, with their confusion
table; kappa has no Wilson interval.

Audit proportions use `design-weighted-wilson-score-v1`, an approximate survey-weighted,
two-sided 95% Wilson interval with `n_eff = sum(w)^2 / sum(w^2)` over that proportion's denominator
and `z = 1.959963984540054`. Zero observed errors still have a positive upper uncertainty bound;
perfect agreement still has a lower bound below one. Empty required strata, `n_eff < 1`, or a
zero false-pass denominator make the gate inconclusive. Binary percentile resampling is not an
authorizing audit interval.

Each model's primary-arm gate requires point-estimate agreement of at least 90%, false-pass
rate at most 5%, no unresolved disagreement, complete critical-record coverage, and no critical
false pass. The intervals are shown beside those decisions. Baseline/Caveman strata and pooled
campaign summaries cannot validate a model-specific primary claim.

## Exact false-fail sensitivity

For each model and primary arm, `M` counts all judge-fail records, `D` counts audited
judge-fail/consensus-pass records, and `U` is the upper endpoint of the reported two-sided 95%
weighted Wilson false-fail interval. Compute `K = min(M, max(D, ceil(U * M)))` using Decimal
arithmetic. Both arm limits and the sensitivity result bind the same per-model audit-metric
digest. When `M = 0`, `K = 0`. A positive `M` with unestimable uncertainty cannot authorize a
semantic conclusion; placeholder `K = D` is nonauthorizing, with zero assignment space and no
partial extrema or certificate.

When both limits are estimable, the exact feasible count is
`A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})`.
Known false fails are reclassified in every assignment. Each assignment recomputes semantic
quality, eligibility, and visible-token intervals with the same 10,000 bootstrap vectors.
The four extrema are the minimum semantic lower bound, maximum semantic upper bound, minimum
token lower bound, and maximum token upper bound.

Direct enumeration is permitted up to 4,096 assignments. Larger spaces use exact, deterministic
branch-and-bound capped at 1,000,000 visited nodes and 4,096 complete-assignment bootstrap
evaluations; v1 permits cardinality pruning only, not semantic or token dominance. The verifier
checks the certificate and all four extrema. An incomplete proof at either cap is inconclusive;
no partial extremum is a decision input. Reports retain assignment counts, both counters, caps,
certificate, exhaustion reason, and any unavailable result.

Semantic non-inferiority requires the worst lower bound above -0.05; semantic inferiority
requires the worst upper bound below -0.05. Positive-direction brevity requires the minimum
token lower bound above zero, and negative-direction brevity requires the maximum token upper
bound below zero. Hard quality is unaffected by judge false-fail assignments.

## Authority and execution boundaries

Only the authority-tagged `statistical_protocol_sha256` may govern analysis/bootstrap, and only
the singular Runtime-registry-derived `audit_protocol_sha256` may govern audit evidence. These
values are identical across generation context, provider index/projection, nested protocol
bindings, audit evidence, campaign analysis, and final evidence. A caller-supplied or merely
self-hashed substitute is not authority. The singular audit digest does not change the granular
protocol-attestation subject inventories.

The frozen cross-slice live contract names exactly `Runtime.hard_score`, `Runtime.prepare_judge`,
and `Runtime.seal_judge` in `laconian_eval.campaign.runtime`, reachable only through the private
`_reconstruct_verified_runtime` constructor. They receive an
in-memory verified generation-context expectation and call the neutral benchmark libraries.
The later Publication contract names exactly
`Publication.campaign.evaluation_stage.sample_audit`,
`Publication.campaign.evaluation_stage.seal_audit`,
`Publication.campaign.evaluation_stage.analyze`, and
`Publication.campaign.evaluation_stage.verify`, reachable only through
`_reconstruct_verified_publication`. Analysis and verification remain separate operations;
neither live module imports the CLI.

All seven standalone `laconian-benchmark` commands in the frozen replay contract are
offline and non-evidentiary. They use one canonical generation-expectation file, accept no raw
expected-digest flag, and cannot grant live authority or dispatch a provider. These exact names
describe the staged interface contract, not evidence that later Runtime, Publication, or CLI
stages have shipped or that a live campaign has run.

## Published artifacts

The legacy walking-skeleton reproducibility artifacts are:

- `manifest.json`, including runner version, provider, exact requested model, settings, retry
  policy, arm-order seed, repetitions, and any dated price snapshot;
- append-only `raw.jsonl` and `run.log`, including failures, retries, and any provider-returned
  model identifier plus the full case-definition hashes;
- `scored.jsonl`, `summary.json`, and `report.md`, with runner-version and sorted per-case hash
  provenance;
- the exact case files, repository revision, runner/schema version, arm hashes, and Caveman
  provenance;
- judge records and protocol metadata when semantic scoring is used;
- environment and known limitations, without credentials.

The sealed public campaign additionally retains all 36 generation seals and scored projections,
hard-score request sets, judge-request attachments, verified judge-attempt boundaries and final
judge attachments, the source-backed protocol and audit archives, the bootstrap matrix, machine
analysis, human-readable report, and immutable checksums. The complete layer inventory is listed
in [Evaluation data](../evals/README.md). These derived layers never overwrite generation evidence.

Secrets never belong in a manifest or committed artifact. Published result directories are
immutable evidence; a correction creates a new directory and explains the superseded run.

## Interpreting outcomes

Classify each generation model independently, retaining every applicable reason, in this order:

1. Protocol, identity, security, missing-ledger, inconsistent-model, or ambiguous-delivery failure
   is operationally invalid: make no performance classification.
2. Valid hard-quality evidence with an upper bound below -0.05 is negative-quality. Semantic
   negative-quality additionally needs a valid audit and sensitivity upper bound below -0.05.
   Failure to establish non-inferiority is not proof of inferiority.
3. With all integrity, coverage, quality, and model-specific audit gates passing, a primary
   upper bound below zero is negative-brevity only when negative-direction sensitivity passes.
4. With all gates passing, a primary lower bound above zero is supported only when
   positive-direction sensitivity passes.
5. Every other statistically valid result is inconclusive, including boundary-crossing intervals
   and audit or sensitivity gate failures.

Hard-quality inferiority can remain reportable when semantic evidence is inconclusive. There is
no multiplicity-adjusted family claim: a count such as supported on X of three models must link
to every independent result and its limitations. Reproducibility and truthful disclosure are
release criteria; a favorable result is not.

This document is licensed under [CC BY 4.0](../LICENSES/CC-BY-4.0.txt).
