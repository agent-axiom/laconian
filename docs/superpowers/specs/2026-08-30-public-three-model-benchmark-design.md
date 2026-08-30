# Public Three-Model Benchmark Pipeline Design

**Date:** 2026-08-30

**Status:** Written specification awaiting maintainer review

**Scope:** Publication-grade response benchmark for GPT-5.6 Sol, Terra, and Luna, executed through
GitHub Actions with immutable generation, judging, human-audit, and publication evidence

## 1. Decision

Laconian will run one preregistered response benchmark campaign against three OpenAI models:
`gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`. Each model is an independent experiment. The
project will not pool the three models into a universal family claim.

The selected architecture is a staged capsule pipeline:

```text
immutable input tag
  -> secret-free preflight
  -> sharded generation capsules
  -> blind semantic-judge attachments
  -> two-person commit-reveal audit
  -> capsule-bound scoring and inference
  -> separately approved publication PR
  -> immutable result tag and release
```

The full campaign is confirmatory. It publishes a registry entry and the appropriate evidence
whether its outcome is positive, negative, inconclusive, or operationally invalid. A favorable
result is not a publication condition.

## 2. Context

The repository already has:

- a response corpus with 12 shared scenarios, each localized in English and Russian;
- four byte-pinned response arms: `baseline`, `concise`, `caveman`, and `if`;
- deterministic hard constraints and semantic rubrics;
- an append-only generation capsule with captured inputs, a materialized plan, request journaling,
  delivery-certainty tracking, resume verification, and sealing mechanics;
- a synthetic replay smoke path that validates basic data flow; and
- a methodology that forbids public efficiency claims without denominators, confidence intervals,
  judge provenance, and human audit.

The synthetic replay result is not model evidence. The current capsule path is also not yet
connected end-to-end to capsule-bound judging, scoring, inference, audit, and publication. GitHub
currently has no live-benchmark workflow, benchmark environment, benchmark secret, or protected
benchmark-tag ruleset.

The design therefore completes the evidence path before spending API budget or publishing a
performance statement.

## 3. Goals

- Measure whether `if` produces shorter successful responses than the exact concise instruction
  `Answer concisely.` for each selected model.
- Prevent a failed, incomplete, or semantically inferior answer from winning because it is short.
- Preserve the English/Russian and repeated-generation dependence in statistical inference.
- Make provider requests, retries, judgments, human labels, estimators, and outcome rules
  reproducible and auditable.
- Bound API exposure before credentials become available and during execution.
- Make resume fail closed when request delivery is ambiguous.
- Separate provider-secret execution from repository-write publication authority.
- Publish immutable evidence and honest limitations for every started confirmatory campaign.
- Produce result-specific documentation and social copy only after evidence review and merge.

## 4. Non-goals

- Combining activation accuracy with response brevity or quality.
- Claiming compatibility with a named agent host from stored activation expectations.
- Treating translations or repetitions as independent scenarios.
- Claiming universal Laconian superiority from three model-specific experiments.
- Using `baseline` or Caveman as a substitute for the primary `if` versus `concise` hypothesis.
- Publishing the existing replay fixture as live evidence.
- Creating a continuously running benchmark, leaderboard, scheduled spend, or PR-triggered live
  provider job.
- Posting automatically to social accounts.
- Hiding a valid negative or inconclusive result.

## 5. Approaches considered

### A. One monolithic live workflow

One job would prepare, generate, judge, score, and publish. It is operationally simple but gives a
large failure domain, weak checkpoint behavior, a serious hosted-job timeout risk, and an unsafe
temptation to combine provider secrets with repository-write permissions.

### B. Staged capsule pipeline — selected

Small generation and judge shards produce hash-bound artifacts. Human labels and statistical
attachments reference immutable upstream hashes. A separate environment and job create the
publication PR without the provider secret. This is the smallest architecture that meets the
methodology and failure-safety requirements.

### C. Per-request workflow fan-out

One job per request minimizes lost work but creates thousands of jobs, a much larger Actions
supply-chain surface, more difficult rate coordination, and unwieldy artifact collection. The
selected design instead keeps all matched observations for one model/scenario together.

## 6. Confirmatory experimental contract

### 6.1 Scope and calls

The full response campaign contains:

| Dimension | Value |
|---|---:|
| Generation models | 3 |
| Independent scenarios | 12 |
| Localized cases per scenario | 2 (`en`, `ru`) |
| Arms | 4 |
| Repetitions | 5 |
| Planned generation responses | 1,440 |
| Potential judge decisions | up to 1,440 |

Activation cases remain a separate suite and do not enter response metrics.

Each model has its own native-v2 manifest. Across the four arms for one model, the provider,
requested model, user prompt, generation settings, tool availability, instruction placement, and
repetition remain fixed. Only the captured arm instruction bytes differ.

### 6.2 Generation settings

All three models use the Responses API with explicit, captured settings:

- `reasoning.effort: medium`;
- `text.verbosity: medium`;
- standard reasoning mode;
- `max_output_tokens: 1024`, including visible and reasoning output tokens;
- no tools;
- no conversation carry-over or prior response;
- `store: false`;
- no temperature value sent; and
- the existing `system_suffix` instruction placement.

Explicit reasoning and verbosity prevent provider-default drift from silently changing the
experiment. A setting change creates a new protocol hash and cannot be pooled with the campaign.

The requested aliases and the public model identifiers returned by the API are both retained.
Successful responses for one model campaign must resolve consistently. A mixed returned-model
identifier invalidates that model campaign rather than being silently pooled.

### 6.3 Randomization

The existing seeded arm-order algorithm remains the request-order contract within each localized
case and repetition. A separate predeclared campaign seed determines shard order, bootstrap
resampling, and human-audit sampling through domain-separated derivations. Seeds and algorithm
versions are captured before any live call.

Case text, constraints, rubric, arm bytes, runner source, dependencies, judge protocol, and
statistical protocol are hashed by the immutable input tag. Editing any of them requires a new tag
and campaign ID.

## 7. Execution architecture

### 7.1 Input tag and preflight

The operator creates a protected tag matching `benchmark-input-YYYYMMDD.N` on the exact commit to
execute. The manually dispatched workflow rejects branch refs, moving aliases, malformed tags,
uncommitted manifests, arbitrary model input, and arbitrary shell input.

A secret-free preflight:

1. verifies the tag and commit identity;
2. validates the three static manifests and all captured inputs;
3. materializes the exact request plan;
4. verifies expected model/scenario/locale/arm/repetition coverage;
5. calculates planned call and output-token exposure;
6. binds the dated price snapshot and source URLs;
7. proves that the authorized campaign exposure does not exceed the fixed budget; and
8. publishes only a preflight summary and digest for environment review.

No provider credential is available during preflight.

### 7.2 Generation shards

Generation uses 36 capsules: `3 models x 12 scenarios`. A capsule keeps both languages, all four
arms, and all five repetitions together, for 40 planned responses. This preserves matched data and
keeps the maximum per-job provider-call window below the monolithic design.

The matrix uses:

- `fail-fast: false`;
- `max-parallel: 1` for the first confirmatory campaign;
- one repository-wide concurrency group;
- `cancel-in-progress: false`;
- a three-hour job timeout;
- `contents: read` and only the additional read permission needed to retrieve verified artifacts;
  and
- checkout without persisted credentials.

The matrix ordering is precomputed, but no cross-model pooled estimate depends on job order. Every
provider timestamp remains in the evidence.

### 7.3 Checkpoints and resume

Each shard checkpoint is a tar archive rather than a direct directory upload. The archive retains
`.laconian.lock`, file modes, exact relative paths, and the complete append-only capsule. It has a
SHA-256 sidecar and a unique name containing campaign, model, scenario, and run-attempt identity.

Before credentials become available on resume, the job:

1. validates the artifact origin, workflow, input tag, head SHA, and digest;
2. rejects path traversal, links, devices, duplicate normalized paths, and unexpected members;
3. extracts with restrictive modes;
4. runs full capsule verification; and
5. compares the manifest, plan, protocol, model, and shard hashes with the preflight registry.

Resume never replans. `AMBIGUOUS_INFLIGHT` is not automatically continued. A missing checkpoint
after runner loss also cannot be silently recreated under the same attempt identity. The operator
must preserve the failed attempt and use the documented invalidation or explicit new-attempt flow.

## 8. Provider failures, retries, and spend

The campaign has a fixed **USD 75 maximum authorized exposure** under the captured price snapshot.
The pilot has a separate USD 5 cap. A changed price or a preflight calculation above the cap stops
before environment approval.

Before every provider call, the runner checks recorded spend plus a conservative maximum charge
for the next request. Completed matrix artifacts are included in the campaign total. The runner
does not schedule a request when the remaining authorization cannot cover it. Actual provider
usage remains authoritative, and estimated cost is explicitly distinguished from the invoice.

Retries are allowed only when delivery evidence makes another call safe:

- authentication and permission failures stop the campaign;
- timeout, connection loss, 408, and 5xx with unknown delivery become
  `AMBIGUOUS_INFLIGHT` and are not automatically retried;
- a valid provider `Retry-After` controls a safe 429 retry when it fits the bounded job budget;
- otherwise a safe transient retry uses recorded exponential backoff with full jitter; and
- at most five transient retries are allowed by the frozen manifest.

The existing sub-second fixed backoff is not sufficient for this campaign and must be replaced
before the live pilot. SDK retries remain disabled so the append-only journal is the only retry
authority.

`GENERATION_COMPLETE` alone is not a success gate. Collection verifies all planned keys, terminal
reasons, retry chains, delivery certainty, returned-model consistency, response usage, and missing
records. `retry_exhausted` and provider-rejected records remain evidence and count against success
and coverage.

## 9. Blind semantic judge

Only deterministic hard-pass responses enter semantic judging. The judge is `gpt-5.6-sol` with:

- `reasoning.effort: low`;
- low text verbosity and a strict structured-output schema;
- `max_output_tokens: 768`;
- no tools, persistence, or conversation carry-over; and
- a frozen prompt, schema, settings, and protocol SHA-256.

The judge sees the original user request, semantic rubric, material-warning requirement, locale,
and candidate response as explicitly delimited untrusted data. It does not see arm, provider,
generation model, request order, output length, token counts, latency, or cost. Candidate text can
never issue instructions to the judge or select files.

The structured judgment records every rubric-item decision, the material-warning decision where
applicable, any material contradiction, overall semantic pass, and bounded evidence. The overall
decision must be derivable from the item decisions; inconsistent or malformed judgments fail
closed.

Judge requests follow the same delivery, retry, budget, journaling, and artifact rules as
generation. A semantic-gated report requires 100% judgment coverage for hard-pass responses. Judge
failure does not silently fall back to a hard-gated performance claim.

Using Sol to judge Sol-generated answers is a disclosed limitation. The independent human sample
is the predeclared check against judge disagreement and self-preference; it does not make the judge
infallible.

## 10. Statistical contract

### 10.1 Primary estimand

The confirmatory comparison is `if` versus `concise`, calculated separately for each generation
model. An eligible pair has matching case and repetition, terminal responses for both arms, and a
pass for both arms under the selected semantic gate.

The primary delta is:

```text
output tokens(concise) - output tokens(if)
```

A positive delta means the eligible `if` response is shorter. The point estimator is the existing
median over eligible paired deltas. Characters are secondary and are never presented as tokens.
Input, output, total, cached-input tokens, estimated cost, and latency remain separate descriptive
metrics; output brevity is not described as total-token or invoice savings.

Baseline and Caveman results provide context only. Any pairwise estimates involving them are
exploratory and do not replace the primary hypothesis.

### 10.2 Dependence and intervals

Every confirmatory interval is two-sided 95%. For paired brevity and paired arm pass-rate
differences, a seeded cluster bootstrap resamples the 12 `scenario_id` blocks with replacement and
keeps both locales, all repetitions, and matched arms within each block. Each replicate recomputes
the complete estimator. The implementation uses 10,000 replicates and records algorithm, PRNG,
seed, valid replicate count, and failure handling.

Raw arm pass proportions also receive disclosed Wilson intervals as descriptive binomial
summaries. The confirmatory non-inferiority decision uses the scenario-clustered paired difference,
not a fiction that 120 localized repetitions are independent scenarios.

Intervals, denominators, scenario coverage, eligible pair count, token-pair count, and missingness
are always adjacent to point estimates. `eligible_pairs` and `token_pairs` are separate fields.

### 10.3 Quality and coverage gates

For both hard and semantic pass rates, the lower 95% confidence bound for:

```text
pass_rate(if) - pass_rate(concise)
```

must be greater than `-0.05`. This is the predeclared five-percentage-point quality
non-inferiority margin.

A model result also requires:

- at least 96 of the 120 planned primary pairs to be eligible;
- eligible pairs from at least 10 of 12 scenarios;
- provider-reported output-token usage for every eligible pair;
- complete judge coverage for every hard-pass response; and
- no unresolved identity, delivery, model, or provenance error.

These gates prevent a small successful subset from carrying the brevity claim.

### 10.4 Outcome classification

A model-specific hypothesis is **supported** only when all integrity, coverage, quality, and human
audit gates pass and the lower 95% bound for the primary token delta is above zero.

If quality is demonstrably inferior or the primary interval is entirely below zero, the result is
reported as negative/rejected with the exact reason. If an interval crosses the decision boundary
or a coverage/audit gate is insufficient, the result is inconclusive. Protocol, identity,
security, or ambiguous-delivery failures make the campaign operationally invalid rather than
inconclusive performance evidence.

The three model decisions are published separately. No multiplicity-adjusted family claim is
made. A descriptive statement such as “supported on X of 3 tested models” must still link to all
three independent results and their limitations.

## 11. Human audit

### 11.1 Sampling and blinding

After all judge decisions are sealed, a deterministic sample targets 144 judged records. It uses
24 strata: `3 generation models x 2 locales x 4 arms`, with an initial quota of six per stratum.
If a stratum has fewer than six judged hard-pass records, all are selected and unused quota is
redistributed deterministically. If fewer than 144 judged records exist overall, all are audited.

The sampling seed is derived from the immutable campaign tag and judge-protocol hash with the
domain separator `laconian-human-audit-v1`. The blind packet removes model, arm, order, tokens,
length, latency, judge decision, and provider metadata. It retains only the prompt, rubric,
locale, candidate response, and opaque audit-record ID required for human evaluation.

Two human reviewers label the same packet independently using the frozen rubric. They must not
inspect generation or judge artifacts before committing their labels.

### 11.2 Commit-reveal

Independence is preserved by a public commit-reveal protocol:

1. each reviewer produces canonical label JSONL and a fresh random salt;
2. the reviewer publishes only a domain-separated SHA-256 commitment bound to campaign, reviewer
   ID, salt, and exact label bytes;
3. after both commitments are immutable, both reviewers reveal their label files and salts;
4. CI recomputes both commitments and rejects changed, malformed, or incomplete labels; and
5. disagreements are copied to an append-only adjudication record without editing either original
   label file.

The two reviewers reconcile disagreements after reveal and record a bounded rationale plus both
sign-offs. Any unresolved disagreement makes the semantic performance conclusion inconclusive.

### 11.3 Audit metrics and gate

The publication reports human-human raw agreement, Cohen's kappa with its limitations, judge versus
adjudicated-consensus agreement, design-weighted false-pass rate, denominators, and 95% intervals.
Kappa is descriptive because class imbalance can make it unstable.

The audit gate requires:

- judge-consensus agreement of at least 90%;
- a judge false-pass rate of at most 5%;
- no unresolved reviewer disagreement; and
- no audited false pass that omits a required critical safety warning.

An audit-gate failure does not erase the run. It prevents a supported semantic claim and is
published as an inconclusive or negative limitation.

## 12. GitHub Actions trust boundaries

### 12.1 Environments and permissions

The repository adds two protected environments:

- `benchmark-live`, holding `OPENAI_API_KEY` and requiring approval before generation or judge
  execution; and
- `benchmark-publish`, requiring a separate approval before repository-write publication.

Self-review and admin bypass are disabled where GitHub supports those controls. Deployment refs
are restricted to the protected benchmark tags. Approval actors and deployment identities are
retained in provenance.

Provider jobs have read-only repository permissions and never receive a write-capable token.
Publication jobs never receive the provider key. No `pull_request_target`, privileged automatic
`workflow_run`, untrusted fork code, or model-generated command is used.

All Actions are pinned to full commit SHAs. Checkout does not persist credentials. Workflow policy
tests fail on a floating action ref, widened permission, unapproved trigger, arbitrary live input,
or secret in a PR/fork job.

### 12.2 Public artifacts

Readers of a public repository may be able to retrieve Actions artifacts. This campaign therefore
uses only the allowlisted public corpus and treats every uploaded checkpoint as potentially public.
Before upload, a fail-closed package gate validates the inventory and scans for known credential
values, credential patterns, environment dumps, private paths, and disallowed provider metadata.

Headers, the API key, environment contents, and unrestricted diagnostics never enter an artifact.
If the scan cannot prove the allowlisted package safe, upload and publication stop. The security
event is retained without reproducing the suspected secret.

Model output remains untrusted data. It is never executed, used as a path, interpolated into a
shell command, or rendered unescaped into HTML.

## 13. Publication flow

### 13.1 Publication bundle

The secret-free collector verifies every upstream workflow, tag, head SHA, artifact digest,
capsule seal, attachment hash, audit commitment, and statistical output. It then creates an
allowlisted bundle under:

```text
benchmarks/results/<campaign-id>/
```

The bundle includes:

- campaign registry record and input/result commit identities;
- copied native-v2 manifests and dated price snapshot;
- exact cases, arm hashes, Caveman provenance, protocol hashes, and runner provenance;
- all terminal and retry attempts, errors, usage, returned models, and request metadata allowed by
  the publication policy;
- generation seals and checksums;
- judge protocol, records, and attachment hashes;
- audit sample manifest, commitments, reveals, original labels, adjudication, and agreement
  report;
- scored records, machine summary, bootstrap outputs, human-readable report, and limitations; and
- a complete checksum manifest and reproducibility command.

Raw and derived layers remain separately hash-bound. Recomputing an analysis creates a new
attachment; it never mutates generation evidence.

### 13.2 Review, merge, release, and correction

The `benchmark-publish` workflow creates a branch and pull request. It does not merge directly.
Normal CI, branch protection, conversation resolution, and human review apply. After merge, a
protected `benchmark-result-<campaign-id>` tag points to the result commit. A GitHub Release carries
the immutable bundle archive, checksum, and provenance attestation.

Actions artifacts are temporary review transport, not the durable public record. The committed
result directory and release assets are the publication surface.

Every started confirmatory input tag gets a registry outcome:

- valid positive, negative, and inconclusive campaigns publish full allowed evidence;
- an operationally invalid campaign publishes the reason and non-sensitive provenance without a
  performance claim; and
- suspected credential exposure quarantines the raw artifact and publishes only a safe incident
  record.

Corrections create a new result directory and tag with an explicit `supersedes` link. Existing
evidence, tags, and releases are not rewritten.

### 13.3 Documentation and social claims

After the result PR merges, synchronized result sections may be added to the six localized
READMEs, `evals/README.md`, the website, changelog, a new release note, and a dated social package.
The historical `v0.1.0-alpha.1` release note and alpha social package remain unchanged.

Every numeric claim names the exact model, date interval, campaign, quality gate, eligible-pair
and scenario denominators, interval, and limitation link. Positive `concise - if` direction is
explained next to the number. Output-token brevity is never promoted as total-token or monetary
savings. No numeric claim appears in a context-free hero or social-preview image.

## 14. Verification and staged rollout

### 14.1 Automated verification

Implementation is test-driven and includes:

- unit and property tests for delta direction, eligibility, scenario-cluster bootstrap,
  non-inferiority, outcome classification, sparse/missing records, and deterministic seeds;
- judge-schema, prompt-blinding, injection-resistance, attachment-binding, and coverage tests;
- audit sampling, canonicalization, commitment, reveal, adjudication, weighting, agreement, and
  threshold tests;
- exact call-count, price-snapshot, next-call reserve, and campaign-budget tests;
- `Retry-After`, jitter, retry exhaustion, authentication stop, ambiguous delivery, runner loss,
  and resume tests;
- tar round-trip, hidden-lock, mode, digest, extraction, traversal, link, overwrite, inventory,
  and secret-scan tests;
- workflow trigger, permissions, environment, concurrency, matrix, full-SHA pinning, and artifact
  provenance policy tests; and
- a full synthetic campaign that reconstructs the report from published-style artifacts without a
  provider secret.

PR and fork CI remains entirely offline and read-only.

### 14.2 Live pilot

Before preregistering the confirmatory tag, a separately labeled operational pilot runs one shared
scenario in both languages, all four arms, one repetition, and all three generation models. At
most 24 generation and 24 judge calls are planned, under the USD 5 cap.

The pilot validates API parameters, returned-model and usage capture, rate behavior, checkpoint
transport, judge schema, and cost accounting. It is never benchmark evidence. The corpus and
decision thresholds cannot be tuned to make the observed pilot effect favorable. A required
protocol fix creates a new pilot identity; the confirmatory input tag is created only after the
implementation is frozen and reverified.

### 14.3 Confirmatory sequence

The release sequence is:

1. full offline synthetic campaign is green;
2. workflow security and statistical review are green;
3. the live operational pilot is green;
4. code, manifests, methods, settings, seeds, and price snapshot are frozen in the input tag;
5. the full campaign receives `benchmark-live` approval and runs once;
6. generation and judge artifacts pass integrity collection;
7. two reviewers complete commit-reveal and adjudication;
8. capsule-bound aggregation classifies every model outcome;
9. `benchmark-publish` receives separate approval and opens the result PR;
10. after CI and review, the PR merges and the immutable result release is created; and
11. documentation, website, and social result packages are updated from the merged evidence.

## 15. Known limitations

- Twelve independent scenario clusters can produce wide intervals. Inconclusive is an expected and
  acceptable outcome.
- The corpus is a compact response suite, not a universal task distribution.
- OpenAI aliases and service behavior can change. Requested and returned identifiers, timestamps,
  settings, and limitations are disclosed, but a hosted API cannot provide perfect future
  reproducibility.
- Sol judging Sol is not fully independent. The two-person audit measures disagreement but does
  not remove every judge bias.
- A public artifact reveals benchmark responses before final publication to anyone who retrieves
  it; blinding is enforced by the reviewer protocol, not by pretending the repository is private.
- A forced runner loss can occur before `always()` uploads a checkpoint. Small shards limit the
  failure domain but cannot eliminate that platform risk.
- API price estimates are not invoices, and cache accounting remains provider-specific.
- Human audit requires two available reviewers and timely reveal before temporary Actions
  artifacts expire.

## 16. Acceptance criteria

The system is ready for the full campaign only when:

- every item in the automated verification section is fresh and green;
- all three native-v2 manifests validate and yield exactly 1,440 generation plan rows;
- the workflow can reconstruct, verify, and resume an exact tarred checkpoint including
  `.laconian.lock`;
- provider jobs have no write token and publication jobs have no provider secret;
- preflight proves the USD 75 exposure bound from the frozen price snapshot;
- the operational pilot completes within its USD 5 bound with consistent returned models and
  complete usage;
- judge and audit protocols are frozen and hash-bound;
- protected input/result tags and both GitHub environments are configured; and
- the maintainer explicitly approves the live workflow deployment.

The project is ready to claim a model-specific result only after the full campaign also satisfies
the integrity, coverage, quality, audit, and publication gates in this specification.

## 17. Authoritative references

- [Laconian benchmark methodology](../../../benchmarks/methodology.md)
- [Evaluation data contract](../../../evals/README.md)
- [Generation capsule design](2026-08-24-v0.1-generation-capsule-design.md)
- [GitHub environments and deployment protection](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub Actions artifact storage](https://docs.github.com/en/actions/tutorials/store-and-share-data)
- [Secure use of GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)
- [OpenAI GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [OpenAI GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [OpenAI GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
