# Public Three-Model Benchmark Pipeline Design

**Date:** 2026-08-30

**Status:** Approved for implementation planning

**Maintainer approval:** 2026-08-30

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
  -> frozen resumable batch plans
  -> sharded generation capsules
  -> sealed hard-score/judge-request attachments
  -> blind semantic-judge attachments
  -> two-person commit-reveal audit
  -> capsule-bound semantic aggregation and inference
  -> read-only bundle collection
  -> separately approved minimal publication PR
  -> protected result tag and checksum-bound release
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
  delivery-certainty tracking, resume verification, and seal grammar/reservation foundations;
- a synthetic replay smoke path that validates basic data flow; and
- a methodology that forbids public efficiency claims without denominators, confidence intervals,
  judge provenance, and human audit.

The synthetic replay result is not model evidence. The current capsule path is also not yet
connected end-to-end to capsule-bound judging, scoring, inference, audit, and publication. GitHub
currently has no live-benchmark workflow, benchmark environment, benchmark secret, or protected
benchmark-tag ruleset.

The current public CLI also has no finalize/seal writer, scenario-shard projection, live structured
judge, campaign spend ledger, or reasoning/verbosity request fields. Those are prerequisites, not
capabilities this document assumes already exist.

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
- Produce result-specific documentation and social copy only after evidence review, merge, and the
  verified `RELEASED` transition.

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

Small logical generation and judge shards produce hash-bound artifacts, while bounded resumable
batch-controller jobs amortize GitHub environment approvals across multiple shards. Human labels
and statistical attachments reference immutable upstream hashes. A read-only collector seals the
publication bundle; a separate minimal environment-gated job copies only that exact bundle and
creates the publication PR without the provider secret. This is the smallest architecture that
meets the methodology and failure-safety requirements.

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
- `max_output_tokens: 1024`, including visible and reasoning output tokens;
- no tools;
- no conversation carry-over or prior response;
- `store: false`;
- no temperature value sent; and
- the existing `system_suffix` instruction placement.

Explicit reasoning and verbosity prevent provider-default drift from silently changing the
experiment. A setting change creates a new protocol hash and cannot be pooled with the campaign.
The source and resolved manifest schemas, request model, request-config hash, plan rows, provider
kwargs, and capsule verifier must all carry these fields. Preflight fails if the exact wire request
does not contain `reasoning: {effort: medium}` and `text: {verbosity: medium}`. Reasoning mode is
omitted and the omission is itself part of the captured request configuration.

Provider evidence must capture `output_tokens_details.reasoning_tokens` in addition to total
provider `output_tokens`. The visible-response token count is defined as provider output tokens
minus reasoning tokens. A missing, negative, or inconsistent reasoning-token breakdown makes a
token-based result unavailable rather than silently treating hidden reasoning as visible prose.

The requested aliases and the public model identifiers returned by the API are both retained.
Successful responses for one model campaign must resolve consistently. A mixed returned-model
identifier invalidates that model campaign rather than being silently pooled.

### 6.3 Randomization

The existing seeded arm-order algorithm remains the request-order contract within each localized
case and repetition. A separate predeclared campaign seed determines shard order, bootstrap
resampling, and human-audit sampling. Each derived seed is the first 128 bits of
`SHA256(domain || NUL || campaign_seed || NUL || input_tag_commit || NUL || judge_protocol_sha256)`,
interpreted as an unsigned big-endian integer. Domain strings, canonical encodings, ordering,
PRNG, and algorithm versions are captured before any live call.

Case text, constraints, rubric, arm bytes, runner source, dependencies, judge protocol, and
statistical protocol are hashed by the immutable input tag. Editing any of them requires a new tag
and campaign ID.

### 6.4 Corpus neutrality and warning severity

Hard constraints must be grounded in the user prompt. Before the live pilot, the 14 localized
`max_sentences` constraints that were added by the evaluator but not requested by the prompt are
removed from the confirmatory corpus. Only `user-decline-en` and `user-decline-ru`, whose prompts
explicitly require exactly two sentences, retain sentence-count gates. This prevents an invented
brevity cap from preferentially excluding longer arms.

Every semantic `material_warning` also receives a frozen severity. The two `safety-medical`
localized cases are `critical`; the `preserve-command` and `safety-financial` warnings are
`material`. The audit's zero-tolerance critical-warning rule applies only to the preregistered
`critical` set. The neutrality edit, warning severities, and resulting case hashes are reviewed and
frozen before the pilot; no change is allowed after observing pilot outputs without a new protocol
identity.

## 7. Execution architecture

### 7.1 Input tag and preflight

The operator creates a protected tag matching `benchmark-input-YYYYMMDD.N` on the exact commit to
execute. The manually dispatched workflow rejects branch refs, moving aliases, malformed tags,
uncommitted manifests, arbitrary model input, and arbitrary shell input.

A secret-free preflight:

1. verifies the annotated or lightweight tag object, its peeled commit identity, and the exact
   detached commit SHA that every later job must check out;
2. validates the three static manifests and all captured inputs;
3. materializes one 480-row parent plan for each model and one ordered campaign-plan index;
4. deterministically projects 36 immutable model/scenario shard plans;
5. verifies that the shard plans are disjoint and that their ordered union is exactly the 1,440
   parent rows, with no gap or duplicate;
6. calculates planned call and token exposure;
7. binds the dated price snapshot, calculation rules, and official source URLs;
8. calculates projected campaign and worst-batch reservations and verifies that the first batch
   can start under the fixed budget policy; and
9. publishes only a preflight summary and digest for environment review.

No provider credential is available during preflight. The workflow does not scrape provider
pricing as a security or correctness boundary. Before approving a live batch, the environment
reviewer checks the frozen source URLs against the committed snapshot and records an attestation.
If the current rate cannot be verified or differs, the reviewer does not approve; revised rates
require a new input tag and campaign identity.

### 7.2 Logical shards and bounded batch controller

Generation uses 36 logical capsules: `3 models x 12 scenarios`. A capsule keeps both languages,
all four arms, and all five repetitions together, for 40 planned responses. This preserves matched
data and bounds the loss from a failed checkpoint independently of the number of capsules handled
by one provider job.

`ShardPlanV1` binds campaign ID, model ID, scenario UID, parent-manifest hash, parent-plan hash,
derivation-version, ordered request identities, row count, and its own hash. A capsule is prepared
from this captured projection; selective execution from an unmodified full manifest is forbidden.
Aggregation binds the ordered set of all 36 generation-capsule hashes, and no pair crosses capsule
or run identity.

GitHub applies environment protection to each job, not once to an entire campaign. The workflow
therefore uses a resumable bounded batch controller rather than 36 generation plus 36 judge
environment jobs. Each manual `workflow_dispatch` or resume consists of:

1. a secret-free batch-prepare job that imports the exact campaign registry, predecessor ledger,
   checkpoint inventory, and immutable ordered plan;
2. deterministic construction of one `BatchPlanV1` for a contiguous prefix of remaining work;
3. one `benchmark-live` environment-gated provider job, which consumes that plan sequentially with
   provider parallelism exactly one; and
4. secret-free post-controller validation and upload of every completed or partial logical capsule,
   the append-only attempt journal, and the successor ledger.

`BatchPlanV1` binds campaign ID, phase (`generation` or `judge`), input tag object and peeled commit,
workflow-file hash, predecessor-ledger hash, ordered shard and request identities, maximum request
attempts, worst-case reservation, price-snapshot hash, monotonic-time allowance, soft deadline,
and its own hash. The plan size is a deterministic function of the remaining authorized exposure,
remaining ordered work, and frozen call/time bounds; it cannot be enlarged after approval. The
secret-free first step of the provider job finalizes the reservation receipt with the exact
`workflow_run_id`, `run_attempt`, `job_id`, and `batch_attempt_id` before the key-bearing step can
run.

The controller may cross logical shard boundaries, but it never reorders requests or begins an
item outside the frozen batch. It seals and checkpoints at every logical shard boundary and also
uploads a verified partial checkpoint before a voluntary soft-deadline exit. Ordinary terminal
provider rejections remain evidence and do not stop later items; a campaign STOP condition does.
Every provider-call boundary verifies the exact current ledger and STOP state.

The execution contract also uses:

- one repository-wide state-mutation concurrency group and `cancel-in-progress: false` across live
  batches, state sealing, collection, publication, and release finalization;
- a three-hour hard job timeout plus the runner soft deadline in section 8;
- `contents: read` and only the additional read permission needed to retrieve exact artifacts;
- checkout of the preflight-recorded detached commit SHA without persisted credentials, followed by
  a fresh tag-object-to-commit verification before each key-bearing step; and
- timestamps for every provider attempt.

One environment approval authorizes only that exact bounded batch, not the whole campaign. A resume
is a new batch and requires another approval; the number of approvals is therefore the number of
generation and judge batches actually needed. This limitation is disclosed in the operator runbook
instead of implying that GitHub offers a workflow-wide approval.

### 7.3 Checkpoints and resume

Each shard checkpoint is an uncompressed tar archive rather than a direct directory upload. The
archive retains `.laconian.lock`, file modes, exact relative paths, and the complete append-only
capsule. It has a SHA-256 sidecar and a unique name containing campaign, model, scenario, batch,
and run-attempt identity.

Before credentials become available on resume, the job:

1. selects the exact artifact ID from the exact workflow-run ID, run attempt, input tag object,
   peeled commit SHA, workflow-file hash, environment deployment, batch-attempt ID, and upload
   service digest; latest-by-name lookup is forbidden;
2. enforces archive byte size, member count, per-file, aggregate, path-depth, and time bounds;
3. rejects PAX/GNU sparse records, absolute paths, backslashes, NUL, non-NFC or empty components,
   `.`/`..`, links, devices, FIFOs, duplicate normalized paths, and unexpected members;
4. extracts in one fd-relative pass into a new `0700` directory with no-follow/exclusive-create
   semantics, fsyncs it, and atomically publishes it; generic `tar -xf` and `extractall` are
   forbidden;
5. runs full capsule verification; and
6. compares the manifest, plan, protocol, model, and shard hashes with the preflight registry.

Resume never changes existing plan identities or releases uncertain exposure. It creates a new
bounded `BatchPlanV1` only for the exact remaining suffix. `AMBIGUOUS_INFLIGHT` is not automatically
continued. A missing checkpoint after runner loss also cannot be silently recreated under the same
attempt identity. The operator must preserve the failed attempt and use the documented invalidation
or explicit new-attempt flow.

### 7.4 Normative campaign state machine

`CampaignStateV1` is the only dispatcher authority. Each canonical record contains schema version,
campaign ID, monotonically increasing transition number, current state, previous-state hash,
triggering `CampaignEventV1` type and hash, input tag object and peeled commit, active phase-plan
hash, spend-ledger hash, artifact-inventory Merkle root, optional STOP/incident ID, exact
workflow/job or reviewer identities, and its own hash. Every event is single-use and parent-bound.
Every state or hold mutation runs under the repository-wide concurrency group and performs a
compare-and-swap against the exact last valid state and unresolved-hold root.
An unknown event, skipped parent, duplicate event, or hash mismatch is rejected without mutating the
last valid state and atomically creates a hash-bound `InvalidEventHoldV1`. The hold binds the rejected
event, last valid state and ledger hashes, source workflow/actor, reason, and its own hash. Every
dispatcher, collector, publisher, and release-finalizer entry first proves that no unresolved hold
exists.

A secret-free `INVALID_EVENT_DISMISSED` proof may clear a benign hold in every state, including
`RESULT_MERGED` and `RELEASED`. It must establish that the event was either an unauthorized-origin
no-op or a byte-identical replay of an already applied event, and that it changed no state, ledger,
artifact, reservation, credential access, or provider dispatch. A read-only job under human
approval from `benchmark-publish`, by an actor distinct from the rejected event source and workflow
trigger actor, verifies and signs the dismissal; clearing the hold does not create a state
transition.

For a nondismissible verified defect before merge, a valid `PERMANENT_STOP` cites the hold and takes
the enumerated invalid path. At `RESULT_MERGED`, it instead uses `RELEASE_PLAN_INVALIDATED`; at
`RELEASED`, the state remains terminal and the defect starts a new correction lineage with an
explicit `supersedes` hash.

The allowed durable transitions are:

| From | Event and required evidence | To | Authorized next action |
|---|---|---|---|
| none | `PREFLIGHT_SEALED`: valid tag, plans, budget, price snapshot | `PREFLIGHTED` | prepare generation batch |
| `PREFLIGHTED` or `GENERATION_RESUMABLE` | `BATCH_RECEIPT_CONSUMED`: exact unused reservation/job tuple and current-price attestation | `GENERATION_ACTIVE` | execute frozen generation batch |
| `GENERATION_ACTIVE` | `NO_DISPATCH_PROVED`: exact job evidence proves zero provider dispatch and releases only never-started reservations | `GENERATION_RESUMABLE` | prepare a new exact batch attempt |
| `GENERATION_ACTIVE` | `VERIFIED_PARTIAL`: exact successor ledger, no STOP, suffix remains | `GENERATION_RESUMABLE` | prepare exact next suffix |
| `GENERATION_ACTIVE` | `GENERATION_SET_SEALED`: all 36 capsule hashes | `GENERATION_COMPLETE` | deterministic hard score |
| `GENERATION_COMPLETE` | `HARD_SCORE_SET_SEALED`: all 36 request-set hashes | `HARD_SCORE_COMPLETE` | prepare judge batch |
| `HARD_SCORE_COMPLETE` or `JUDGE_RESUMABLE` | `BATCH_RECEIPT_CONSUMED`: exact unused reservation/job tuple and current-price attestation | `JUDGE_ACTIVE` | execute frozen judge batch |
| `JUDGE_ACTIVE` | `NO_DISPATCH_PROVED`: exact job evidence proves zero provider dispatch and releases only never-started reservations | `JUDGE_RESUMABLE` | prepare a new exact batch attempt |
| `JUDGE_ACTIVE` | `VERIFIED_PARTIAL`: exact successor ledger, no STOP, suffix remains | `JUDGE_RESUMABLE` | prepare exact next suffix |
| `JUDGE_ACTIVE` | `JUDGE_SET_SEALED`: all 36 judge-attachment hashes | `JUDGE_COMPLETE` | provider-evidence integrity validation |
| `JUDGE_COMPLETE` | `EVIDENCE_INVENTORY_SEALED`: exact generation/hard-score/judge coverage | `PROVIDER_EVIDENCE_VERIFIED` | create blind audit packet |
| `PROVIDER_EVIDENCE_VERIFIED` | `AUDIT_SEALED`: both reveal chains and signed adjudication or explicit unresolved records | `AUDIT_COMPLETE` | semantic aggregation/inference |
| `AUDIT_COMPLETE` | `ANALYSIS_SEALED`: deterministic scores, bootstrap, sensitivity, outcomes | `ANALYSIS_COMPLETE` | run complete collector |
| `ANALYSIS_COMPLETE` | `COMPLETE_BUNDLE_SEALED`: exact full allowlist and checksum | `BUNDLE_COLLECTED` | prepare publication plan |
| `BUNDLE_COLLECTED` | `PUBLICATION_PR_OPENED`: exact publication plan, branch, base, head, PR | `PUBLICATION_PR_OPEN` | review and required CI |
| `BUNDLE_COLLECTED` | `COMPLETE_PUBLICATION_PLAN_INVALIDATED`: base/head moved or plan check failed, bundle digest unchanged | `BUNDLE_COLLECTED` | prepare a new complete publication plan |
| `PUBLICATION_PR_OPEN` | `RESULT_MERGED`: approved PR and exact merge tree | `RESULT_MERGED` | prepare release plan |
| `PUBLICATION_PR_OPEN` | `COMPLETE_PUBLICATION_PLAN_INVALIDATED`: complete-bundle PR closed, sealed bundle digest unchanged | `BUNDLE_COLLECTED` | prepare a new complete publication plan |
| `PUBLICATION_PR_OPEN` | `INVALID_PUBLICATION_PLAN_INVALIDATED`: invalid-prefix PR closed, sealed prefix digest unchanged | `INVALID_FINALIZED` | prepare a new invalid publication plan |
| `RESULT_MERGED` | `RESULT_RELEASED`: protected result tag and checksum-bound assets | `RELEASED` | documentation/social follow-up |
| `RESULT_MERGED` | `RELEASE_PLAN_INVALIDATED`: verified tree, bundle, security, or provenance defect | `RELEASE_BLOCKED` | start a correction lineage; do not tag/release |
| any nonterminal pre-publication state | `PERMANENT_STOP`: security, ambiguity, identity, receipt, price-snapshot mismatch, or provenance failure; any open publication PR is closed | `STOPPED_INVALID` | prefix/STOP finalizer only |
| any ready/resumable provider state | `BUDGET_EXHAUSTED`: next minimum batch cannot fit | `BUDGET_INCOMPLETE` | prefix/STOP finalizer only |
| `STOPPED_INVALID` or `BUDGET_INCOMPLETE` | `INVALID_PREFIX_SEALED`: exact completed prefix and missing suffix | `INVALID_FINALIZED` | publish registry/incident only |
| `INVALID_FINALIZED` | `INVALID_PUBLICATION_PLAN_INVALIDATED`: base/head moved or plan check failed, prefix digest unchanged | `INVALID_FINALIZED` | prepare a new invalid publication plan |
| `INVALID_FINALIZED` | `INVALID_PUBLICATION_PR_OPENED`: exact safe-prefix publication plan, branch, base, head, PR | `PUBLICATION_PR_OPEN` | review and required CI, no performance claim |

An active job that exits at the soft deadline is resumable only through `VERIFIED_PARTIAL`. A lost
job without that event uses `NO_DISPATCH_PROVED` only when durable job and provider evidence proves
that the entire batch made zero dispatches and every released reservation is `never_started`;
otherwise ambiguity emits `PERMANENT_STOP`. Audit nonparticipation or an unrevealed commitment emits
a reason-specific `PERMANENT_STOP`; an explicitly signed unresolved adjudication is instead a valid
`AUDIT_SEALED` event whose affected model outcome is inconclusive. No dispatcher may jump from a
partial, STOP, budget, or release-blocked state into live execution or complete collection. An
unresolved `InvalidEventHoldV1` blocks every otherwise allowed transition.

## 8. Provider failures, retries, and spend

The campaign has a fixed **USD 75 maximum authorized request exposure** under the committed price
snapshot. The pilot has a separate USD 5 cap. A preflight calculation above the cap stops before
environment approval. Current-price verification follows the reviewer attestation in section 7.1;
there is no brittle automatic scrape. This is a hard scheduling/authorization bound, not a claim
that an external provider invoice can be controlled perfectly or that every planned request is
guaranteed to fit. If cumulative charged-or-reserved exposure plus the next conservative batch
reservation no longer fits, the campaign stops incomplete and is reported accordingly.

An append-only campaign spend ledger tracks both batch and request-attempt exposure. Before a
provider job can map the key, the secret-free preparation path persists a worst-case reservation
for every initial call and allowed retry in its frozen `BatchPlanV1`, including input bounds and
output-token caps. Its finalized receipt binds the campaign, phase, ordered plan items, price
snapshot, predecessor ledger, and exact provider-job identity tuple
`(workflow_run_id, run_attempt, job_id, batch_attempt_id)`.

That identity must consume exactly one unused reservation before key access. A rerun or replacement
job has a new identity and therefore requires a new additive reservation; it cannot reuse the old
receipt. An unreconciled prior reservation remains fully charged against the cap. Missing,
duplicate, reused, superseded, or identity-mismatched receipts write STOP before credentials. This
makes runner loss conservative rather than an unrecorded opportunity to spend again.

Every request attempt has its own reserved amount and terminal accounting state. A reservation may
be released only with durable evidence that the attempt never began. Once provider dispatch may
have occurred, it reconciles downward only from trusted provider usage or a frozen provider rule
that proves a definitely rejected request has zero billable usage. Missing usage, uncertain
delivery, a crash, or an unverifiable checkpoint retains the full worst-case amount. Earlier failed
attempts in a retry chain and the final successful attempt reconcile independently; success never
erases earlier exposure. The next batch starts only when its predecessor ledger is exact, its new
worst-case reservation fits, and no STOP marker exists.

The automatic retry taxonomy is closed and versioned:

- authentication and permission failures, including both 401 and 403, durably stop the campaign;
- only a structured provider 429 response classified `delivery_certainty=definitely_rejected` may
  be retried automatically;
- its valid bounded `Retry-After` controls the delay; when absent, the frozen domain-seeded
  exponential full-jitter rule controls the delay;
- timeout, connection loss, 408, 409, 5xx, or any other response with uncertain delivery becomes
  `AMBIGUOUS_INFLIGHT` and is never automatically retried;
- other definite provider rejections are terminal and are never automatically retried; and
- at most five 429 retries are allowed by the confirmatory manifest, while the pilot allows zero.

The existing sub-second fixed backoff is not sufficient for this campaign and must be replaced
before the live pilot. The versioned retry-evidence schema records status class, delivery
certainty, provider `Retry-After`, bounded retry-after milliseconds, exponential bound, jitter
derivation, selected backoff, source, attempt reservation, and remaining deadline. The verifier
checks the frozen rule rather than the old exact `100 * 2**n` value. SDK retries remain disabled so
the append-only journal is the only retry authority.

Authentication, permission, ambiguous delivery, reservation inconsistency, or suspected credential
exposure writes a permanent STOP marker into the campaign ledger. The current 403-as-ordinary-
rejection behavior must be changed. Every later secret-free predecessor job and every provider-call
boundary checks the marker, and tests prove that no subsequent call occurs.

The runner stops voluntarily at least 15 minutes before the three-hour job timeout. It begins a
request or retry only if the remaining monotonic time covers the full request timeout, maximum
allowed backoff, durable journal work, and checkpoint margin. `always()` upload is fallback, not a
guarantee after forced runner termination.

`GENERATION_COMPLETE` alone is not a success gate. Collection verifies all planned keys, terminal
reasons, retry chains, delivery certainty, returned-model consistency, response usage, and missing
records. `retry_exhausted` and provider-rejected records remain evidence and count against success
and coverage.

## 9. Blind semantic judge

After all 36 generation capsules are sealed, a secret-free deterministic stage creates one
`HardScoreRequestSetV1` attachment per capsule. It binds the generation-capsule seal, hard-scorer
source and protocol hashes, every planned response ID, deterministic hard-pass decision and reason,
and the exact ordered judge-request IDs for hard-pass responses. The attachment is sealed before
any judge request; changing a hard decision or request set creates a new attachment identity and
cannot be joined to the campaign.

Only deterministic hard-pass responses enter semantic judging. The judge is `gpt-5.6-sol` with:

- `reasoning.effort: low`;
- low text verbosity and a strict structured-output schema;
- `max_output_tokens: 768`;
- no tools, persistence, or conversation carry-over; and
- a frozen prompt, schema, settings, and protocol SHA-256.

The judge sees the original user request, semantic rubric, material-warning requirement, locale,
and candidate response as explicitly delimited untrusted data. It does not see arm, provider,
generation model, request order, output length, token counts, latency, or cost. Candidate text can
never select tools, files, workflow state, or output paths. Delimiting and adversarial tests reduce
prompt-injection risk but cannot prove that an LLM will never be influenced by candidate text; this
remains a disclosed residual limitation.

The structured judgment records every rubric-item decision, the material-warning decision where
applicable, any material contradiction, overall semantic pass, and bounded evidence. The overall
decision must be derivable from the item decisions; inconsistent or malformed judgments fail
closed.

Judge requests follow the same delivery, retry, budget, journaling, and artifact rules as
generation. A semantic-gated report requires 100% judgment coverage for hard-pass responses. Judge
failure does not silently fall back to a hard-gated performance claim.

Judging uses 36 hash-bound attachments keyed by generation model and scenario. Each attachment
references exactly one sealed generation-capsule hash and its sealed `HardScoreRequestSetV1` hash,
and contains judgments for at most its 40 ordered judge requests. A zero-request set still produces
a sealed zero-call judge attachment. Judge batches use the same bounded batch controller,
per-attempt spend ledger, STOP marker, soft deadline, resume contract, and exact-artifact lookup as
generation. Provider-evidence validation verifies that the ordered judge attachments cover each
and only each request in the 36 sealed hard-score request sets.

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
visible output tokens(concise) - visible output tokens(if)
```

A positive delta means the eligible visible `if` response is shorter. For each response,
`visible_output_tokens = output_tokens - reasoning_tokens`; billed output and hidden reasoning
tokens are reported separately. The point estimator is the median over eligible paired visible-token
deltas. Characters are secondary and are never presented as tokens. Input, visible output,
reasoning output, billed output, total, cached-input tokens, estimated cost, and latency remain
separate descriptive metrics.

This is a post-treatment estimand conditional on both matched responses passing the semantic gate.
It does not estimate unconditional token, total-token, or cost savings across all planned requests.
Every public claim therefore says “among jointly successful matched responses.”

Baseline and Caveman results provide context only. Any pairwise estimates involving them are
exploratory and do not replace the primary hypothesis.

### 10.2 Dependence and intervals

Every confirmatory interval is two-sided 95%. The cluster-percentile bootstrap sorts canonical
scenario UIDs bytewise, samples 12 scenario indices with replacement, and retains both locales,
all repetitions, and matched arms for each sampled block. Each replicate recomputes the complete
estimator. The implementation uses NumPy `Generator(PCG64)`, the domain-derived seed from section
6.3, 10,000 replicates, and type-7 empirical quantiles at 0.025 and 0.975. Fewer than 9,990 valid
replicates makes the corresponding decision inconclusive. Ties remain in the empirical sample;
golden vectors freeze ordering, quantiles, and invalid-replicate behavior.

Paired brevity, raw arm pass proportions, and paired arm pass-rate differences all use this same
scenario-clustered interval. Unclustered Wilson intervals may appear only as explicitly labeled
naive diagnostics; they are not publication uncertainty or a decision input. The normative
methodology is updated accordingly before the input tag.

Intervals, denominators, scenario coverage, eligible pair count, token-pair count, and missingness
are always adjacent to point estimates. `eligible_pairs` and `token_pairs` are separate fields.

### 10.3 Quality and coverage gates

For every model and each of its 120 planned case/repetition keys per arm, define:

- `H = 1` only for a terminal provider success that passes the deterministic hard gate;
- `S = 1` only when `H = 1` and the frozen judge passes the semantic rubric; and
- `H = S = 0` for provider-rejected, retry-exhausted, blank, or hard-fail terminal records.

Only hard-pass responses require a judge call. A missing key, unknown delivery, authentication
stop, inconsistent model, or unverifiable provenance invalidates inference instead of being
imputed as failure. Thus `hard_pass_rate = sum(H) / 120` and
`semantic_success_rate = sum(S) / 120`; semantic quality is never conditioned only on rows that
survived the hard gate.

For both `H` and `S`, the paired rate-difference estimator is the mean of `if - concise` over the
120 matched planned keys. The lower 95% cluster-bootstrap bound for:

```text
pass_rate(if) - pass_rate(concise)
```

must be greater than `-0.05`. This is the predeclared five-percentage-point quality
non-inferiority margin. For `S`, this observed-data check is provisional: final semantic
non-inferiority also requires the worst-case false-fail sensitivity bound in section 11.3.

A model result also requires:

- at least 96 of the 120 planned primary pairs to be eligible;
- eligible pairs from at least 10 of 12 scenarios;
- provider-reported billed-output and reasoning-token usage, and therefore visible-output tokens,
  for every eligible pair;
- complete judge coverage for every hard-pass response; and
- no unresolved identity, delivery, model, or provenance error.

These gates prevent a small successful subset from carrying the brevity claim.

### 10.4 Outcome classification

Classification follows this fixed precedence and records every applicable reason:

1. Protocol, identity, security, missing-ledger, inconsistent-model, or ambiguous-delivery failure
   is **operationally invalid**; no performance classification is made.
2. With statistically valid evidence, a hard-quality upper bound below `-0.05` is
   **negative-quality**. Semantic `negative-quality` additionally requires the section 11.3
   worst-case false-fail sensitivity upper bound below `-0.05`. Merely failing to put the lower
   bound above `-0.05` is not evidence of inferiority.
3. When integrity, coverage, quality, and model-specific human-audit gates pass, a primary
   visible-token upper bound below zero is **negative-brevity** only if the section 11.3
   negative-direction false-fail sensitivity gate also passes.
4. When every integrity, coverage, quality, and model-specific human-audit gate passes and the
   primary visible-token lower bound is above zero, the hypothesis is **supported** only if the
   section 11.3 positive-direction false-fail sensitivity gate also passes.
5. Every other statistically valid case, including a boundary-crossing interval or audit-gate
   failure, is **inconclusive**.

If multiple negative conditions hold, all are reported. A semantic-based negative or supported
classification requires a valid audit; hard-gate quality inferiority may still be reported when
the semantic judge is inconclusive.

The three model decisions are published separately. No multiplicity-adjusted family claim is
made. A descriptive statement such as “supported on X of 3 tested models” must still link to all
three independent results and their limitations.

## 11. Human audit

### 11.1 Sampling and blinding

After all judge decisions are sealed, a deterministic sample targets 144 judged records. It uses
24 strata: `3 generation models x 2 locales x 4 arms`, with an initial quota of six per stratum.
Every judge-pass `safety-medical` record from the primary `if` and `concise` arms is first selected
as a certainty unit with inclusion probability one. Under the planned corpus this is at most five
records inside each primary model/locale/arm stratum, so the sixth slot remains available for a
random noncritical record. If certainty units ever exceed the 144-record target, the audit expands
rather than subsampling them.

After certainty selection, base stratum `s = (generation model, locale, arm)` has local capacity
`q_s = max(0, min(6 - c_s, N_s))`, where `c_s` is its certainty count and `N_s` its noncertainty
population. Noncertainty records are split into cells
`h = (generation model, locale, arm, blinded judge decision)`. Within each cell, canonical record
IDs are sorted bytewise and permuted by NumPy `Generator(PCG64)` using the section 6.3 seed derived
with domain `laconian-human-audit-v1/cell/` plus the canonical cell ID.

The integer allocation is exact. If `q_s` is at least the number of nonempty cells, first assign one
seat to every nonempty cell. Allocate the remaining seats by Hamilton largest remainder over each
cell's remaining capacity: take floors of the proportional quotas, then award residual seats by
descending fractional remainder with bytewise cell ID as the tie-break, skipping full cells. If
`q_s` is smaller than the number of nonempty cells, apply the same Hamilton rule without the
one-seat minimum. After all local allocations, set the total target to
`max(144, total_certainty_count)` and fill any shortfall one record per pass over bytewise-sorted
noncertainty cell IDs, skipping full cells, until the target or population exhaustion. A cell's
selected records are always the first `n_h` IDs in its frozen permutation. The sample manifest
records all capacities, floors, remainders, tie-breaks, global-fill passes, `N_h`, `n_h`, certainty
flags, seeds, permutations, and inclusion probabilities.

The blind packet removes model, arm, order, tokens, length, latency, judge decision, and provider
metadata. It retains only the prompt, rubric, warning severity, locale, candidate response, and
opaque audit-record ID required for human evaluation.

Two human reviewers label the same packet independently using the frozen rubric. They must not
inspect generation or judge artifacts before committing their labels.

### 11.2 Commit-reveal

The input-tag manifest preregisters two distinct reviewer GitHub identities and, when used, their
commit-signing key fingerprints. Independence is preserved through ordinary user-authored pull
requests and this public commit-reveal protocol:

1. each reviewer produces canonical label JSONL and a fresh random salt locally;
2. that reviewer opens a PR which only adds
   `benchmarks/audits/<campaign-id>/commitments/<reviewer-id>.json`, containing the
   domain-separated SHA-256 commitment bound to campaign, reviewer ID, salt, sample-manifest hash,
   and exact label bytes;
3. branch-protection CI verifies that the PR actor matches the preregistered reviewer, the head
   commit has the required verified signature status, the path is new, and the commitment schema
   and campaign bindings are exact;
4. only after both commitment PRs merge, each reviewer opens a separate reveal PR adding immutable
   canonical labels and salt under `benchmarks/audits/<campaign-id>/reveals/<reviewer-id>/`;
5. CI recomputes the commitment byte-for-byte and rejects an actor mismatch, modified original
   commitment, malformed or incomplete labels, duplicate record, or premature reveal;
6. after both reveal PRs merge, disagreements are copied by a separate adjudication PR to an
   append-only record without editing either original label file; and
7. both preregistered reviewers independently approve or sign the canonical adjudication digest,
   which binds both reveal hashes and every consensus label and rationale.

The audit collector binds the exact commitment, reveal, and adjudication PR numbers; actors; head
and merge commit SHAs; signature-verification states; merge actors; file hashes; and both reviewer
sign-off records. CI verifies that the signers are the two distinct preregistered identities, checks
their configured signing fingerprints when required, and confirms that the adjudication input did
not include or reveal model-judge labels. A missing or stale sign-off leaves the disagreement
unresolved and the affected model inconclusive. A maintainer cannot substitute a reviewer or
adjudication file without producing a visibly different, invalid provenance chain.

The two reviewers reconcile disagreements after reveal and record a bounded rationale plus both
sign-offs. They and any adjudicator remain blinded to the model-judge decision until the consensus
file is committed and sealed; judge labels are revealed only for agreement calculation. Any
unresolved disagreement makes the affected model's semantic performance conclusion inconclusive.

### 11.3 Audit metrics and gate

For weighting, a noncertainty sampling cell is
`h = (generation model, locale, arm, blinded judge decision)`. Each selected record in that cell
has design weight `w_h = N_h / n_h`, where both `N_h` and `n_h` exclude certainty units; certainty
units have weight one. This finer cell definition is required because judge-pass and judge-fail
records can have different inclusion probabilities.
Agreement is the Hajek
weighted proportion `sum(w * I[judge = consensus]) / sum(w)`. False-pass rate is
`sum(w * I[judge = pass and consensus = fail]) / sum(w * I[judge = pass])`; a zero denominator is
inconclusive. Human-human agreement and kappa use the corresponding design-weighted confusion
table. Weighted kappa is a descriptive point estimate with no Wilson interval; its complete
confusion table is reported. The publication reports all weights, cells, denominators, point
estimates, and the specified intervals for proportions.

Audit uncertainty uses a preregistered design-weighted Wilson score interval. For each reported
proportion, `n_eff = sum(w)^2 / sum(w^2)` over its denominator and the two-sided interval uses
`z = 1.959963984540054`; it therefore retains nonzero uncertainty after zero observed errors or
perfect observed agreement. This is an approximate survey-weighted interval and is labeled as
such. Empty required strata, `n_eff < 1`, or a zero false-pass denominator make the affected gate
inconclusive. Binary percentile resampling is forbidden for audit-gate uncertainty.

The confirmatory audit gate is calculated separately for each generation model and uses only its
`if` and `concise` strata. Baseline and Caveman audit results, plus campaign-wide aggregates, are
exploratory and cannot validate a model-specific primary claim. For each model, the preregistered
point-estimate gate requires:

- judge-consensus agreement of at least 90%;
- judge false-pass rate of at most 5%;
- no unresolved reviewer disagreement;
- 100% audit coverage of judge-pass primary-arm `safety-medical` critical records; and
- no false pass for either preregistered `safety-medical` critical warning.

The 95% intervals are always shown beside those decisions. An audit-gate failure does not erase the
run; it makes that model's semantic conclusion inconclusive rather than allowing other models or
context arms to dilute the failure.

The report also gives the weighted false-fail rate
`P(consensus = pass | judge = fail)` separately for every generation model `m` and primary arm
`a in {if, concise}`. Let `M_{m,a}` be the number of all judge-fail records, `U_{m,a}` its reported
95% upper false-fail bound, and `D_{m,a}` the number of audited judge-fail/consensus-pass records.
Those `D_{m,a}` known records are reclassified in every sensitivity assignment, and at most
`K_{m,a} = min(M_{m,a}, max(D_{m,a}, ceil(U_{m,a} * M_{m,a})))` total records in that model/arm may
be reclassified. If `M_{m,a} = 0`, `K_{m,a} = 0`; if `M_{m,a} > 0` but its false-fail uncertainty is
not estimable, that model's semantic result is inconclusive.

For every feasible arm-specific assignment respecting matched keys, the analysis recomputes `S`,
the semantic pass-rate-difference interval, eligibility, and the primary visible-token interval
with the frozen 10,000-replicate cluster bootstrap. Across assignments it selects the minimum
semantic-quality lower bound, maximum semantic-quality upper bound, minimum primary-token lower
bound, and maximum primary-token upper bound. Exhaustive enumeration or a verifier-checked exact
branch-and-bound certificate is required; a heuristic search is not sufficient.

The exact search is deterministically bounded per model. Let
`A_m = product_a sum_{j=D_{m,a}}^{K_{m,a}} C(M_{m,a} - D_{m,a}, j - D_{m,a})`. Direct enumeration is
allowed only when `A_m <= 4096`. Larger spaces use bytewise record order and exact branch-and-bound
capped at 1,000,000 visited nodes and 4,096 complete-assignment bootstrap evaluations, with all
10,000 bootstrap scenario-index vectors precomputed once. A verifier checks the certificate for
every pruned subtree and all four extrema. The caps count deterministic logical operations, not wall
time. If the proof is incomplete at either cap, all semantic quality and brevity decisions for that
model are `inconclusive`; no partial extremum is used. The caps, counters, certificate, and
`search_exhausted` reason are published.

Semantic non-inferiority passes only when the minimum semantic-quality lower bound is greater than
`-0.05`; semantic `negative-quality` is established only when the maximum semantic-quality upper
bound is below `-0.05`. Otherwise the semantic-quality decision is inconclusive. The
positive-direction brevity sensitivity gate passes only when the minimum token lower bound is
strictly above zero; the negative-direction gate passes only when the maximum token upper bound is
strictly below zero. If the applicable directional gate fails, the semantic brevity result is
inconclusive. Hard-gate `H` quality is unaffected by judge false-fail assignments and retains its
section 10.3 interval.

## 12. GitHub Actions trust boundaries

### 12.1 Environments and permissions

The repository adds two protected environments:

- `benchmark-live`, holding `OPENAI_API_KEY` and requiring approval before generation or judge
  batch execution; and
- `benchmark-publish`, requiring a separate approval before repository-write publication.

At specification time the repository API reports default workflow permission `read` and
`can_approve_pull_request_reviews: false`. The read default remains; rollout enables the repository
Actions PR-creation toggle only for the protected publication path and grants write permissions
explicitly on its two minimal jobs. Neither job contains a PR-approval or merge operation.

Self-review and admin bypass are disabled where GitHub supports those controls. Deployment refs
are restricted to the protected benchmark tags. Approval actors and deployment identities are
retained in provenance.

Provider jobs have read-only repository permissions and never receive a write-capable token.
Publication jobs never receive the provider key. No `pull_request_target`, privileged automatic
`workflow_run`, untrusted fork code, or model-generated command is used.

The live secret is a dedicated project-scoped restricted key created for this benchmark campaign,
not an organization/admin key. The project has no unrelated consumers, exposes only the API
capabilities required by the frozen runner, and uses a provider-side project spend guard where
available. The key is revoked or rotated after the campaign and immediately after any incident.

Each batch has an exact two-job credential boundary. A job outside `benchmark-live` imports and
verifies the checkpoints, checks the predecessor ledger/STOP state, constructs `BatchPlanV1`,
creates its worst-case reservation, and emits a digest-bound safe input artifact. The
environment-gated provider job checks out the exact detached preflight commit, re-verifies the tag
object and plan digest, and finalizes the single-use job receipt before execution.
`${{ secrets.OPENAI_API_KEY }}` is mapped through step-scoped `env` only for the single
hash-verified provider-controller command, never at workflow or job scope and never during
checkout, dependency setup, artifact download/upload, or packaging. No third-party action or
arbitrary shell runs while the key is in scope; tracing is disabled, SDK retries are zero, and
ambient proxy credentials are not trusted.

All Actions are pinned to full commit SHAs. Every job checks out the preflight-recorded detached
commit SHA, never a tag name after preflight, and checkout does not persist credentials. Workflow
policy tests fail on a floating action ref, widened permission, unapproved trigger, arbitrary live
input, tag/commit mismatch, or secret in a PR/fork job.

### 12.2 Public artifacts

Readers of a public repository may be able to retrieve Actions artifacts. This campaign therefore
uses only the allowlisted public corpus and treats every uploaded checkpoint as potentially public.
Typed records and an allowlist-by-construction package projection are the primary boundary. A
fail-closed defense-in-depth scan then checks exact known credential values, credential patterns,
environment dumps, private paths, and disallowed provider metadata.

Headers, the API key, raw SDK exception bodies, environment contents, and unrestricted diagnostics
never enter an artifact. The exact key is scanned only inside its ephemeral provider step and is
never written for scanning. If inventory or scanning fails, upload and publication stop. The
security event is retained without reproducing the suspected secret; pattern matching is defense
in depth, not a claim that regex can prove the absence of every secret.

Suspected credential exposure discovered after upload triggers immediate campaign STOP and key
revocation/rotation. The affected Actions artifact is deleted where GitHub still permits deletion;
only its artifact ID, digest, safe metadata, deletion result, and incident timeline are retained.
Because retrieval may already have occurred, the event is treated as a disclosure and the campaign
is operationally invalid even if deletion succeeds. Raw affected data is excluded from publication.

Model output remains untrusted data. It is never executed, used as a path, interpolated into a
shell command, or rendered as raw GitHub Markdown/HTML. Canonical output stays in JSONL/download
artifacts; any approved excerpt uses a tested text-only encoder that neutralizes HTML, links,
images, headings, fences, and mentions.

## 13. Publication flow

### 13.1 Publication bundle

Immediately after judging, a secret-free read-only provider-evidence verifier checks generation,
hard-score, judge, ledger, and provenance completeness and seals `EvidenceInventoryV1`. It neither
accepts audit/statistical outputs nor creates a publication bundle; its sole purpose is to authorize
the blind audit packet from an exact provider-evidence root.

Only after `AUDIT_COMPLETE` and `ANALYSIS_COMPLETE`, the secret-free, read-only complete collector
accepts the sealed evidence inventory plus allowlisted exact workflow-run IDs, run
attempts, job and batch-attempt IDs, artifact IDs, detached input/workflow SHAs, tag objects and
peeled commits, environment deployments, service digests, capsule seals, attachment hashes, audit
commitments, and statistical outputs. It rejects name-based latest lookup, duplicates, superseded
attempts, PR/fork origins, and a missing predecessor. It binds the ordered set of all 36 generation
capsules, all 36 `HardScoreRequestSetV1` attachments, and all 36 judge attachments, then creates an
allowlisted bundle artifact whose proposed repository destination is:

```text
benchmarks/results/<campaign-id>/
```

The bundle includes:

- campaign registry record and input/result commit identities;
- copied native-v2 manifests, dated price snapshot, and per-batch reviewer attestations;
- exact cases, arm hashes, Caveman provenance, protocol hashes, and runner provenance;
- all terminal and retry attempts, errors, usage, returned models, and request metadata allowed by
  the publication policy;
- generation seals and checksums;
- deterministic hard-score protocol and request-set attachments;
- judge protocol, records, and attachment hashes;
- audit sample manifest, commitments, reveals, original labels, adjudication, and agreement
  report;
- scored records, machine summary, bootstrap outputs, human-readable report, and limitations; and
- a complete checksum manifest and reproducibility command.

Raw and derived layers remain separately hash-bound. Recomputing an analysis creates a new
attachment; it never mutates generation evidence.

The complete collector is fail-closed: any missing generation, hard-score, or judge attachment
prevents a performance bundle. A separate secret-free prefix/STOP finalizer handles budget stops,
security incidents, ambiguity, and other operational invalidity. It binds the immutable full plan,
last valid spend ledger, ordered completed prefix, exact expected missing suffix, STOP/incident
reason, artifact inventory and safe provenance, and emits only a registry/incident artifact with no
performance estimate or model comparison. This lets every started input tag receive an outcome
without weakening the complete collector.

### 13.2 Review, merge, release, and correction

The read-only collector seals a checksum manifest, fixed path inventory, and complete-bundle or
prefix-finalizer digest. A secret-free `PublicationPlanV1` then binds that digest; the exact
bundle kind (`complete` or `invalid_prefix`); the protected `main` base SHA; the input commit SHA;
the ordered set of every present commitment, reveal, and adjudication merge SHA; the expected result
path and tree diff; the publication workflow SHA; and the proposed branch name. A complete plan
requires the full audit merge set. An invalid-prefix plan instead binds its exact STOP state and
missing-stage suffix and cannot invent absent audit merges. The base must be current `main`, must
contain the input commit and every present bound merge SHA as ancestors, and must not already contain
the result path. Any base movement or proposed-head change invalidates the plan and requires a new
plan and approval.

A minimal `benchmark-publish` environment job receives only the repository write and pull-request
permissions needed to publish. Trusted publisher code runs from the detached input commit and
creates a separate worktree rooted at the exact publication base SHA. It verifies the plan, bundle
digest, and inventory, copies fixed allowlisted paths byte-for-byte, verifies the exact expected
tree diff, and opens the bound branch and pull request. It does not parse, score, render, execute, or
otherwise interpret untrusted model output, and it has no provider key. The repository setting that
allows GitHub Actions to create pull requests must be explicitly enabled; the workflow token is not
allowed to approve or merge its own PR.

The publication job does not merge directly. Normal CI, branch protection, conversation
resolution, and human review apply. GitHub places `pull_request` runs created by `GITHUB_TOKEN`
`opened`, `synchronize`, or `reopened` events into an approval-required state. The publication
contract requires a maintainer with write access to verify the exact PR head SHA and sealed bundle
digest, then select **Approve workflows to run**. The resulting secret-free
`publication-pr-validate` check is required by branch protection. After merge, a protected
`ResultReleasePlanV1` binds the campaign, input tag, bundle digest, exact publication PR and approved
head, merge commit and result-tree digest, result tag name, release workflow SHA, and asset digests.
A separate `benchmark-publish` environment-gated release-finalizer job rechecks that plan and
creates `benchmark-result-<campaign-id>` at exactly the merge commit plus the checksum-bound GitHub
Release. It receives only the tag/release permissions needed, never rewrites result files, and
records the tag object, release ID, and returned asset digests.

Actions artifacts are temporary review transport, not the durable public record. The committed
result directory and release assets are the publication surface.

Every started confirmatory input tag gets a registry outcome:

- valid positive, negative, and inconclusive campaigns publish full allowed evidence;
- an operationally invalid campaign publishes the reason and non-sensitive provenance without a
  performance claim; and
- suspected credential exposure follows section 12.2 and publishes only the safe invalid-campaign
  incident record.

Corrections create a new result directory and tag with an explicit `supersedes` link. Existing
evidence, tags, and releases are not rewritten. A `RELEASE_BLOCKED` lineage creates no result tag or
release; its correction lineage binds and supersedes the blocked merge explicitly.

### 13.3 Documentation and social claims

Only after `CampaignStateV1` reaches `RELEASED` may synchronized result sections be added to the six
localized READMEs, `evals/README.md`, the website, changelog, a new release note, and a dated social
package. `RESULT_MERGED` and `RELEASE_BLOCKED` explicitly authorize no documentation, release-note,
website, or social promotion. The historical `v0.1.0-alpha.1` release note and alpha social package
remain unchanged.

Every numeric claim names the exact model, date interval, campaign, quality gate, eligible-pair
and scenario denominators, interval, and limitation link. Positive `concise - if` direction is
explained next to the number. Visible-output-token brevity is never promoted as billed-output,
total-token, or monetary savings. No numeric claim appears in a context-free hero or social-preview
image.

## 14. Verification and staged rollout

### 14.1 Automated verification

Implementation is test-driven and includes:

- unit and property tests for delta direction, eligibility, scenario-cluster bootstrap,
  visible-versus-reasoning tokens, non-inferiority, outcome classification, sparse/missing
  records, and deterministic seeds;
- manifest/request round-trip tests proving exact medium reasoning and medium verbosity in every
  request identity and wire payload;
- corpus-neutrality tests proving that only prompt-grounded sentence constraints are gating and
  that critical-warning case IDs are frozen;
- parent/shard-plan tests proving exactly 36 disjoint 40-row generation projections whose ordered
  union is the three 480-row parent plans;
- hard-score/request-set sealing plus judge-schema, prompt-blinding, injection-resistance,
  attachment-binding, zero-call attachment, and exact coverage tests;
- audit sampling, certainty-unit coverage, canonicalization, reviewer identity/signature binding,
  commitment/reveal PR ordering, adjudication, weighting, agreement, model/arm-indexed false-fail
  sensitivity, quality/brevity extrema, exact-search certificates, and deterministic search-cap
  tests, including `M = K = 120` fail-closed exhaustion;
- exact call-count, price-snapshot attestation, `BatchPlanV1`, single-use job receipt, per-attempt
  reservation/reconciliation, duplicate/rerun rejection, STOP propagation, and campaign-budget
  tests, including a 429-retry-then-success chain whose attempts remain separately accounted;
- `CampaignStateV1` transition-table, parent-hash, atomic invalid-event hold, approved dismissal,
  post-merge benign-hold dismissal, hold-to-STOP, compare-and-swap race, no-mutation, illegal-jump,
  zero-dispatch recovery, resumable-partial, budget-incomplete, publication-replan,
  release-blocked, invalid-finalization, and happy-path property tests;
- closed retry-taxonomy, `Retry-After`, jitter, retry exhaustion, 401/403 stop, ambiguous delivery,
  soft deadline, forced runner loss, and exact-suffix resume tests;
- tar round-trip, hidden-lock, mode, digest, extraction, traversal, link, overwrite, inventory,
  and secret-scan tests;
- workflow trigger, permissions, per-batch environment approval, campaign concurrency,
  batch-controller ordering, step-scoped-secret, detached-SHA pinning, Markdown neutralization, and
  exact artifact-provenance policy tests;
- read-only provider-evidence verifier, complete-collector ordering, incomplete-prefix finalizer,
  credential-incident, `PublicationPlanV1` ancestor/base/head movement and closed-PR replan,
  minimal-publisher, exact-head manual publication-PR validation, `ResultReleasePlanV1`, and
  release-finalizer tests;
- public finalize/seal writer and capsule-bound hard-score/judge/scoring/aggregation attachment
  tests; and
- a full synthetic campaign that reconstructs the report from published-style artifacts without a
  provider secret.

PR and fork CI remains provider-offline and secret-free: it may fetch pinned actions and locked
dependencies, but it has read-only repository permission and cannot make live model calls.

### 14.2 Live pilot

Before preregistering the confirmatory tag, a separately labeled operational pilot runs one shared
scenario in both languages, all four arms, one repetition, and all three generation models. At
most 24 generation and 24 judge attempts are permitted, under the USD 5 cap. The pilot freezes
`max_transient_retries = 0`, so retries cannot raise the actual API-attempt ceiling above 48.

The pilot validates API parameters, returned-model and usage capture, rate behavior, checkpoint
transport, judge schema, and cost accounting. It is never benchmark evidence. The corpus and
decision thresholds cannot be tuned to make the observed pilot effect favorable. A required
protocol fix creates a new pilot identity; the confirmatory input tag is created only after the
implementation is frozen and reverified.

### 14.3 Confirmatory sequence

The release sequence is:

1. full provider-offline synthetic campaign is green;
2. workflow security and statistical review are green;
3. the live operational pilot is green;
4. code, manifests, methods, settings, seeds, and price snapshot are frozen in the input tag;
5. each required bounded generation batch receives `benchmark-live` approval and runs in order;
6. all generation capsules are sealed and the deterministic hard-score/request-set attachments are
   sealed;
7. each required bounded judge batch receives `benchmark-live` approval and runs in order;
8. generation, hard-score, and judge artifacts pass read-only provider-evidence integrity
   validation and `EvidenceInventoryV1` is sealed;
9. two reviewers complete commit-reveal and adjudication;
10. capsule-bound aggregation classifies every model outcome;
11. the complete read-only collector seals the final bundle from provider evidence, audit, and
    analysis;
12. `benchmark-publish` receives separate approval for the exact `PublicationPlanV1` and opens the
    result PR from the verified main base;
13. a maintainer approves publication-PR validation for the exact head SHA and the reviewed PR
    merges;
14. `ResultReleasePlanV1` binds the merge commit and asset digests;
15. the separately approved release finalizer creates the protected result tag and checksum-bound
    release; and
16. documentation, website, and social result packages are updated from the merged evidence.

At any provider-stage `PERMANENT_STOP` or `BUDGET_EXHAUSTED`, the sequence branches immediately to
the prefix/STOP finalizer and safe invalid-campaign publication path defined by `CampaignStateV1`.
It does not continue to judge, audit, aggregate, or complete collection.

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
- A forced runner loss can occur before the post-controller `always()` upload. Per-shard seals limit
  already-uploaded evidence loss, but work produced across multiple shards inside the current batch
  can still be lost; retained reservations and STOP behavior prevent unsafe continuation but cannot
  recover that work.
- GitHub environment approval is job-scoped. A long campaign may require several manual approvals,
  one for each bounded generation or judge batch; there is no campaign-wide approval primitive.
- Publication requires one protected approval to create the exact result PR and another to create
  the post-merge result tag/release; these are separate write-capable jobs.
- API price estimates are not invoices, and cache accounting remains provider-specific.
- Human audit requires two available reviewers and timely reveal before temporary Actions
  artifacts expire.
- Human audit uses only 24 targeted primary-arm records per model under the agreed 144-record
  workload. Model-specific intervals can therefore be wide even when point-estimate gates pass.
- The exact false-fail sensitivity search is deliberately compute-bounded. A large feasible
  assignment space can force a semantic result to inconclusive even when observed-data gates pass.
- Delimiting candidate text and removing authority reduce judge prompt-injection risk but cannot
  prove that model judgment is unaffected by adversarial response content.

## 16. Acceptance criteria

The system is ready for the full campaign only when:

- every item in the automated verification section is fresh and green;
- all three native-v2 manifests collectively yield exactly 1,440 parent-plan rows, and the 36
  hash-bound shard plans form an exact disjoint 36-by-40 partition;
- public finalize/seal, hard-score/request-set, judge, scoring, inference, and bundle writers bind
  every attachment to its exact parent hashes;
- manifest/request evidence captures medium reasoning, medium verbosity, and the reasoning-token
  breakdown required for visible-token scoring;
- the corpus-neutrality edit and warning-severity schema are frozen and validated;
- the workflow can reconstruct, verify, and resume an exact tarred checkpoint including
  `.laconian.lock`;
- the `CampaignStateV1` dispatcher rejects every illegal, duplicated, skipped-parent, STOP-to-live,
  and partial-to-complete event without state mutation, atomically blocks on
  `InvalidEventHoldV1` until approved dismissal or the phase-appropriate STOP, release-block, or
  correction path, and permits zero-dispatch recovery only with exact `never_started` reservation
  evidence; every mutation is serialized and compare-and-swapped against the exact state/hold root;
- provider jobs have no write token, the minimal publisher has no provider secret, and a dedicated
  restricted project key is mapped only to the single provider-controller step;
- the batch controller proves predecessor-ledger, single-use job receipt, per-attempt reservation,
  permanent STOP, soft-deadline, exact-suffix resume, and zero-subsequent-call behavior for
  authentication, permission, ambiguity, credential exposure, and missing state;
- preflight and the durable ledger enforce the USD 75 authorized-exposure scheduling bound from
  the frozen price snapshot and reviewer attestation, and stop before a batch that cannot fit;
- the operational pilot completes within its USD 5 bound with consistent returned models and
  complete usage;
- judge and audit protocols are frozen and hash-bound, every critical judge-pass primary record is
  audited, and the two reviewer identity-bound commitment/reveal chains verify;
- model/arm-indexed false-fail sensitivity recomputes semantic quality and brevity, verifies exact
  extrema certificates, and becomes inconclusive on deterministic search-cap exhaustion;
- the read-only collector rejects an incomplete performance bundle, the prefix/STOP finalizer emits
  only safe invalid-campaign provenance, and the minimal publisher copies only an exact sealed
  allowlist;
- `PublicationPlanV1` starts from exact current `main` containing every bound audit merge,
  `ResultReleasePlanV1` binds the reviewed merge tree, and the release finalizer tags only that
  commit with the sealed asset digests; base/head movement has an exact closed-PR replan transition,
  and a verified post-merge defect blocks release;
- documentation, website, release-note, and social updates are impossible before `RELEASED` and
  remain forbidden for `RESULT_MERGED` or `RELEASE_BLOCKED`;
- the repository explicitly permits GitHub Actions to create pull requests while branch protection
  prevents the workflow token from approving or merging its own PR;
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
- [GitHub `GITHUB_TOKEN` workflow-run behavior](https://docs.github.com/en/actions/concepts/security/github_token)
- [OpenAI project and restricted-key controls](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform)
- [OpenAI GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [OpenAI GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [OpenAI GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
