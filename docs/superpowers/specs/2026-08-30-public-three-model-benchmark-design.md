# Public Three-Model Benchmark Pipeline Design

**Date:** 2026-08-30

**Status:** Amendment drafted; pending explicit maintainer reapproval

**Historical maintainer approval:** 2026-08-30 (approval of the pre-amendment design)

**Amendment approval:** Pending. The historical approval does not approve this amendment. A new
approval record may be added only after a maintainer reviews this exact diff.

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

The current public CLI also confers no campaign authority or evidentiary capability, and the
repository has no complete scenario-shard projection, live structured judge, campaign spend
ledger, or reasoning/verbosity request path. Those are prerequisites, not capabilities this
document assumes already exist.

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

- literal request wire field `service_tier: "default"`;
- `reasoning.effort: medium`;
- `text.verbosity: medium`;
- `max_output_tokens: 1024`, including visible and reasoning output tokens;
- no tools;
- no conversation carry-over or prior response;
- `store: false`;
- literal `prompt_cache_options: {"mode": "explicit", "ttl": "30m"}` and no cache
  breakpoint;
- no temperature value sent; and
- the existing `system_suffix` instruction placement.

Explicit reasoning and verbosity prevent provider-default drift from silently changing the
experiment. A setting change creates a new protocol hash and cannot be pooled with the campaign.
The source and resolved manifest schemas, request model, request-config hash, plan rows, provider
kwargs, and capsule verifier must all carry these fields. Preflight fails if the exact wire request
does not contain `service_tier: "default"`, `reasoning: {effort: medium}`, and
`text: {verbosity: medium}`. The service-tier key on the wire is exactly `service_tier`; aliases,
SDK-only configuration, environment defaults, and omission are forbidden. The request serializer,
provider projection, attempt journal, response evidence, ledger, and verifier bind this literal
field end to end as `service_tier="default"`. Returned-tier evidence is the exact
`service_tier` field from the canonical raw Responses API result plus its source digest; a renamed,
derived, or SDK-default assertion is not returned-tier evidence. Reasoning mode is omitted and the
omission is itself part of the captured request configuration.

Every response attempt records returned-tier evidence and exactly one closed service-tier
accounting status:

```text
reported_default | not_applicable_definitely_not_sent |
not_applicable_definitely_rejected | missing | mismatch
```

`reported_default` requires returned provider evidence that the effective service tier was
`default`. `not_applicable_definitely_not_sent` is valid only when independent durable evidence
proves the request was never dispatched and therefore received no response and incurred no usage.
`not_applicable_definitely_rejected` is valid only when independent durable evidence proves a
structured definitely-rejected transport response with no Responses API result and no usage;
the retry-eligible 429 case remains governed by section 8. Neither status may be inferred from a
missing field. If any Responses API result is received, or if delivery is unknown, missing
returned-tier evidence is `missing`; any non-`default` evidence is `mismatch`. Either retains the
full worst-case exposure, durably appends STOP, and permits zero later provider calls.

Cache reads and cache writes are distinct request, evidence, usage, pricing, reservation,
reconciliation, and accounting dimensions. For every generation and judge request, the tagged
wire contract has exactly this cache-control member:

```json
"prompt_cache_options": {"mode": "explicit", "ttl": "30m"}
```

`prompt_cache_key` and deprecated `prompt_cache_retention` are absent. The canonical `instructions`
and recursively every object inside canonical `input` contain no `prompt_cache_breakpoint` key;
the verifier rejects that key at any depth before serialization. No other cache-control member is
allowed. The [Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
defines these GPT-5.6+ fields, and the dated
[prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) states that
explicit mode with no explicit breakpoint neither uses prompt caching nor creates cache writes.
The request bytes, provider kwargs, and captured projection must be byte-equivalent on these
members; SDK defaults or omission cannot satisfy the contract.

The tagged live protocol also binds OpenAI Python SDK version `3.3.1` and the exact C0-derived
`uv.lock` member hash. Preflight imports that pinned distribution, verifies that its typed request
and response models expose every frozen field/path, and rejects a different installed version,
lock member, serializer projection, or response model before credentials.

The canonical raw-response paths are exactly:

```text
response.service_tier
response.prompt_cache_options.mode
response.prompt_cache_options.ttl
response.usage.input_tokens
response.usage.input_tokens_details.cached_tokens
response.usage.input_tokens_details.cache_write_tokens
response.usage.output_tokens
response.usage.output_tokens_details.reasoning_tokens
response.usage.total_tokens
```

No alternate, flattened, inferred, billing-dashboard, or SDK convenience path is response
evidence. A Responses result must echo applied options exactly as
`response.prompt_cache_options.mode == "explicit"` and
`response.prompt_cache_options.ttl == "30m"`; missing or different applied-option evidence is a
request-contract mismatch that retains worst-case exposure, appends STOP, and permits zero later
calls. The separate applied-cache-control status has exactly this closed vocabulary:

```text
reported_exact | not_applicable_definitely_not_sent |
not_applicable_definitely_rejected | missing | mismatch | invalid
```

The exact two strings map to `reported_exact`; a proven no-dispatch or definitely rejected/no-usage
attempt maps to its corresponding `not_applicable_*`; absent/null evidence maps to `missing`; any
different well-formed value maps to `mismatch`; and wrong types or source-digest failure map to
`invalid`. Unknown delivery maps to `missing`. Every attempt stores `cache_read_tokens` only from
`response.usage.input_tokens_details.cached_tokens` and `cache_write_tokens` only from
`response.usage.input_tokens_details.cache_write_tokens`, each with its raw-response source digest.
For a complete response, both must be nonnegative integers, each must not exceed `input_tokens`,
their sum must not exceed `input_tokens`, and
`ordinary_uncached_input_tokens = input_tokens - cache_read_tokens - cache_write_tokens`.

The cache-read status enum and cache-write status enum are separate fields but have the same exact
closed vocabulary:

```text
reported_zero | reported_nonzero | not_applicable_definitely_not_sent |
not_applicable_definitely_rejected | missing | invalid
```

The evidence-to-status mapping is exhaustive. A proven never-dispatched attempt has null tokens and
`not_applicable_definitely_not_sent` for both fields. A structured definitely-rejected attempt
independently proven to have no Responses result and no usage has null tokens and
`not_applicable_definitely_rejected` for both. For a Responses result, an exact integer zero maps
to `reported_zero`, a positive integer maps to `reported_nonzero`, an absent or null path maps to
`missing`, and a wrong type, negative value, bound violation, inconsistent total, or source-digest
failure maps to `invalid`. Unknown delivery without a trustworthy result maps to `missing` for
both. No other transition is valid, and the status of one dimension cannot supply or change the
other.

Only `reported_exact/reported_zero/reported_zero` across applied-control/read/write, or the matching
triple of independently proven `not_applicable_*` statuses, satisfies the no-read/no-write contract.
Any nonzero cache read retains the read charge, appends STOP, and permits zero later calls. Any
nonzero cache write is first reconciled and charged at the frozen cache-write rate, then appends
STOP and permits zero later calls. `missing`, `mismatch`, or `invalid` retains the affected
dimension's full conservative reservation; an applied-control failure retains all three input
components. It appends STOP after a Responses result or unknown delivery and permits zero later
calls. Missing write detail never becomes zero. Here and in section
8, “response” means a Responses API result, not a structured definitely-rejected transport response
independently proven to have no result and no usage.

Every frozen requested model ID has a reviewed, non-null cache-write rate even though writes are
forbidden.
`price_snapshot.service_tier` and `price_attestation.requested_service_tier` are both exactly
`"default"`; a mismatch stops before key access. The price snapshot binds separate
ordinary-uncached-input, cache-read-input, cache-write-input, visible-output, and reasoning-output
prices and their source evidence.

The versioned conservative input-exposure rule is frozen and proves an upper bound of at most
`272_000` input tokens for each request attempt. The price snapshot, batch plan, and ledger reserve
only under the ordinary `default`-tier price schedule at that bound. Long-context pricing is not an
authorized price class and must not be used to authorize, reserve, or reconcile campaign spend;
an attempt that cannot be proven within the bound stops before dispatch.

Provider evidence must capture `output_tokens_details.reasoning_tokens` in addition to total
provider `output_tokens`. The visible-response token count is defined as provider output tokens
minus reasoning tokens. A missing, negative, or inconsistent reasoning-token breakdown makes a
token-based result unavailable rather than silently treating hidden reasoning as visible prose.

The requested model IDs and the public model identifiers returned by the API are both retained.
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

### 6.5 Independent reviewer identity registries

The input tag contains two independent, typed identity registries. `AuditReviewerRegistryV1`
contains exactly two distinct audit reviewers. Each ordered entry binds the reviewer ID, numeric
GitHub account ID, exact GitHub login, signing-verification mode, signing fingerprint (including an
explicit null only when the frozen verification mode permits no fingerprint), and role. Its
canonical bytes and digest are audit-registry-specific and bind every audit commitment, reveal,
adjudication, approval, and collector check.

`ProtocolReviewerRegistryV1` contains exactly three distinct protocol reviewers in this exact role
order:

1. `statistical_method`;
2. `blind_judge_audit_protocol`; and
3. `security_evidence`.

Each ordered protocol entry binds its numeric GitHub account ID, exact GitHub login,
signing-verification mode, and signing fingerprint. The `security_evidence` fingerprint is
non-null regardless of the other roles' allowed modes. The protocol registry has canonical bytes
and a digest distinct from the audit registry.

The verification-mode vocabulary is closed:

- `github_verified_commit` requires a GitHub commit-verification record with `verified: true`,
  matching numeric account ID/login, and a null `signing_fingerprint`;
- `ssh_sha256` requires the same identity match and a non-null OpenSSH fingerprint matching
  `SHA256:<base64>`; and
- `openpgp_fingerprint` requires the same identity match and a non-null uppercase 40- or 64-hex
  primary-key fingerprint.

No other mode or fingerprint form is valid. Because `security_evidence` requires a non-null
fingerprint, that role cannot use `github_verified_commit`. A non-null fingerprint is mandatory for
either keyed mode and forbidden for `github_verified_commit`; a mode/fingerprint mismatch rejects
the registry before any attestation is evaluated.

For `github_verified_commit`, `signature_evidence` contains exactly `commit_oid`, `verified: true`,
`reason: "valid"`, `signer_numeric_account_id`, and `signer_login`. For either keyed mode it contains
those five fields plus `fingerprint`, which must byte-equal the top-level fingerprint and satisfy
that mode's grammar. A missing field, extra field, different commit/signer, non-valid verification
reason, or nested key material is forbidden.

Each `ProtocolAttestationV1` contains exactly these required top-level fields, in schema order:
`schema_version`, `role`, `protocol_registry_sha256`, `reviewer_numeric_account_id`,
`reviewer_login`, `verification_mode`, `signing_fingerprint`, `input_tag_object_sha256`,
`peeled_c0_sha256`, `workflow_root`, `subjects`, `subject_root`, `signed_at`,
`signature_evidence`, and `attestation_sha256`. Extra fields are forbidden. Canonical bytes use
`CanonicalJSONV1`: UTF-8, NFC strings, bytewise-sorted object keys, schema-order arrays, JSON
integers only, no insignificant whitespace, and no terminal newline. `attestation_sha256` is
SHA-256 over the domain-separated canonical object with only that digest field omitted; no other
field may be omitted from signed bytes.

The exact role-to-subject inventories are:

| Role | Ordered `subjects` kinds |
|---|---|
| `statistical_method` | `corpus_case_root`, `estimand_protocol_sha256`, `statistical_protocol_sha256`, `bootstrap_protocol_sha256`, `outcome_classification_protocol_sha256`, `false_fail_sensitivity_protocol_sha256` |
| `blind_judge_audit_protocol` | `hard_score_protocol_sha256`, `judge_prompt_sha256`, `judge_schema_sha256`, `audit_sampling_protocol_sha256`, `audit_commit_reveal_protocol_sha256`, `audit_adjudication_protocol_sha256` |
| `security_evidence` | `provider_request_contract_sha256`, `retry_spend_protocol_sha256`, `campaign_state_schema_sha256`, `workflow_endpoint_policy_sha256`, `artifact_security_protocol_sha256`, `publication_correction_protocol_sha256`, `identity_registry_bundle_sha256` |

Each subject is exactly `{kind, sha256}`. A role's attestation must contain every listed subject once
in that order and may contain no subject assigned to another role, no unlisted subject, and no
duplicate. Common fields such as registry, C0, and workflow roots remain top-level and are forbidden
inside `subjects`. `subject_root` is the SHA-256 of the domain-separated canonical ordered subject
array. The three attestations appear in the registry's exact role order, and their ordered canonical
root is `protocol_attestations_root`.

Cardinality, order, numeric account ID, login, verification mode, fingerprint, canonical bytes,
and digest are all security boundaries. A login rename, numeric-ID mismatch, missing required
fingerprint, reordered role, duplicate identity, or cross-registry lookup fails closed. Neither
registry, its members, signatures, approvals, nor attestations may substitute for the other.

### 6.6 Frozen workflow inventory

The protocol freezes this exact 15-member workflow path inventory, in this literal UTF-8 byte
order:

```text
.github/workflows/audit-pr-validate.yml
.github/workflows/benchmark-analysis.yml
.github/workflows/benchmark-audit.yml
.github/workflows/benchmark-batch.yml
.github/workflows/benchmark-collect-complete.yml
.github/workflows/benchmark-dismiss-hold.yml
.github/workflows/benchmark-docs-validate.yml
.github/workflows/benchmark-evidence.yml
.github/workflows/benchmark-finalize-invalid.yml
.github/workflows/benchmark-hard-score.yml
.github/workflows/benchmark-preflight.yml
.github/workflows/benchmark-publication-state.yml
.github/workflows/benchmark-publish.yml
.github/workflows/benchmark-release.yml
.github/workflows/publication-pr-validate.yml
```

Only these member paths and their order are source constants. C0 is the fully verified peeled
commit of the protected input tag used as the campaign code/input authority. For each path, the
member SHA-256 is derived from the exact bytes read from that verified C0 tree; no member hash is a
source constant.
`WorkflowInventoryV1` is the canonical ordered mapping of each literal path to that derived hash,
and `workflow_root` is the SHA-256 of its domain-separated canonical bytes. The inventory rejects a
missing, extra, renamed, reordered, duplicated, nonregular, or byte-mismatched member. The root is
therefore derived only after C0 and all 15 member bytes have been verified; it is never accepted
from an input field without reconstruction.

All three protocol attestations, the generation-context expectation and final generation context,
every provider projection, and publication verification bind this same reconstructed
`workflow_root`. A different workflow subset, reordered inventory, or independently supplied root
cannot authorize a live stage or publication.

## 7. Execution architecture

### 7.1 Input tag, preflight, and generation-context expectation

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

After the generation layer is final and before hard scoring, the campaign authority constructs an
authority-bound `GenerationContextExpectationV1`. It binds the campaign ID, both reviewer-registry
digests, `protocol_attestations_root`, the exact
predecessor campaign-authority root, the complete generation-layer root, the expected digest of the
canonical generation-context payload, and the common `workflow_root`. The canonical payload
carries the tagged hard-scorer source hash, hard-score protocol hash, judge protocol hash,
statistical protocol hash, audit protocol hash, provider-projection root, and every generation
capsule root. Those bindings are retained unchanged in hard-score attachments, judge projections,
provider-evidence inventory, analysis, and publication evidence.

The `GENERATION_SET_SEALED` event and resulting `GENERATION_COMPLETE` authority record contain the
required fields `generation_context_expectation_sha256` and
`verified_generation_context_root` in addition to the 36 ordered capsule hashes. To avoid a hash
self-cycle, the expected context digest is computed over the canonical context payload without the
expectation-link field; the expectation then binds that expected digest, and the final authority
record binds both the reconstructed context root and the separately computed expectation digest.
Verification requires both values to match their independently reconstructed objects.

This authority is a non-serializable campaign capability. Only campaign-side reconstruction of the
predecessor authority root and final generation-layer roots may construct
`VerifiedGenerationContextExpectationV1`, and it exists only in memory for the authorized stage.
No serialized file, raw hash, identifier, CLI or workflow input, environment value, or nested
provider-index field creates, carries, or confers this capability. A caller that merely supplies
the correct bytes or digest remains unauthorized.

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
environment jobs. Each manual `workflow_dispatch` or resume uses four pairwise
credential-separated roles/jobs:

1. a secret-free batch-prepare job that imports the exact campaign registry, predecessor ledger,
   checkpoint inventory, and immutable ordered plan and deterministically constructs one
   `BatchPlanV1` for a contiguous prefix of remaining work;
2. one protected, repository-read-only `benchmark-live` provider job, whose single controller step
   consumes the won receipt and plan sequentially with provider parallelism exactly one;
3. a key-free receipt/state-writer job whose fixed minimal reusable state-writer boundary invokes
   the broker-held state-writer GitHub App to compare-and-swap the exact reservation receipt and
   authority predecessor;
4. a key-free post/state-writer job that validates and uploads every completed or partial logical
   capsule and append-only attempt journal, then invokes that same broker-held App through the fixed
   minimal reusable boundary to compare-and-swap the successor ledger and authority state.

Dependency edges, a bounded wait before the controller step, and single-use handoff receipts ensure
the provider controller cannot begin until the receipt/state writer's expected-OID compare-and-swap
has won. The repository `GITHUB_TOKEN` is read-only in all four jobs.

`BatchPlanV1` binds campaign ID, phase (`generation` or `judge`), input tag object and peeled commit,
workflow-file hash, predecessor-ledger hash, ordered shard and request identities, maximum request
attempts, worst-case reservation, price-snapshot hash, monotonic-time allowance, soft deadline,
and its own hash. The plan size is a deterministic function of the remaining authorized exposure,
remaining ordered work, and frozen call/time bounds; it cannot be enlarged after approval. The
key-free receipt/state writer finalizes the reservation receipt with the exact `workflow_run_id`,
`run_attempt`, `job_id`, and `batch_attempt_id`; the protected provider job accepts only the
corresponding CAS-winner receipt. Only its single hash-verified provider-controller step may map
`OPENAI_API_KEY`, and only after that receipt is verified.

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

The versioned `CampaignStateSchemaV1` canonical state/event schema is the single source of truth
for state names, event names, allowed parent-state and bundle-kind combinations, required evidence,
and terminality. The table below is a generated human-readable rendering of that schema, and tests
load the same schema rather than maintaining a second transition list. Any table/schema drift,
unknown enum value, or event whose evidence discriminator does not match its parent is rejected.
For `GENERATION_SET_SEALED`, the schema's exact required-evidence set is the ordered 36 capsule
hashes, `generation_context_expectation_sha256`, and `verified_generation_context_root`; neither
root is optional, derivable after the transition, or replaceable by a raw context payload.

The closed `PERMANENT_STOP.reason` enum contains the literal discriminator
`credential_exposure`. It is not encoded as generic `security`, `artifact_failure`, or another
alias. For that reason, `CampaignStateSchemaV1` requires a
`CredentialExposureIncidentEvidenceV1` root. Its exact top-level fields are:

```text
schema_version
campaign_id
incident_id
reason
parent_state
parent_authority_oid
current_state_root
spend_ledger_root
artifact_inventory_root
active_phase_plan_root
unresolved_hold_root
secret_kind
affected_artifacts
scanner_receipt
credential_containment
artifact_quarantine_receipt_sha256
no_further_campaign_download_receipt_sha256
complete_publication_pr_close_receipt_sha256
detected_at
credential_exposure_incident_evidence_sha256
```

`reason` is exactly `credential_exposure`. `secret_kind` is exactly one of
`openai_api_key`, `state_writer_app_private_key`, `publisher_app_private_key`,
`release_finalizer_app_private_key`, `github_app_installation_token`, `github_oidc_id_token`,
`repository_github_token`, or `unclassified_suspected_credential`; a secret value, matching
substring, authorization header, environment dump, or raw provider/GitHub response is forbidden.
`schema_version` is exactly `CredentialExposureIncidentEvidenceV1`; `incident_id` matches
`credexp-[0-9a-f]{32}` and is single-use within the campaign.
`unresolved_hold_root` is the exact current hold root or literal null only when absence is proven.
`affected_artifacts` is a nonempty array in ascending numeric artifact-ID order. Each element has
exactly `artifact_id`, `artifact_sha256`, `upload_service_digest`, `source_workflow_ref`,
`source_workflow_sha`, `upload_run_id`, `upload_run_attempt`, `upload_job_id`,
`upload_check_run_id`, `uploaded_at`, `deletion_status`, and `deletion_receipt_sha256`.
`deletion_status` is exactly `deleted`, `already_expired`, `deletion_not_available`, or
`pending_at_stop`; its receipt binds the exact API request/result or the verified reason deletion
was unavailable or pending. Duplicate artifact IDs are forbidden.

`scanner_receipt` has exactly `scanner_protocol_sha256`, `scanner_tool_sha256`, `scanner_rule_id`,
`scanner_run_id`, `scanner_run_attempt`, `scanner_check_run_id`, `verification_mode`, and
`verification_receipt_sha256`; `verification_mode` is `exact_known_value`, `credential_pattern`, or
`independent_safe_metadata_confirmation`. `credential_containment` has exactly `status` and
`receipt_sha256`, where status is `revoked`, `rotated`, or `cryptographically_expired`.
`cryptographically_expired` is allowed only for a GitHub installation, OIDC, or repository token
whose signed issuance/expiry and current invalidity verify; long-lived key kinds require `revoked`
or `rotated`, and an unclassified pattern requires a receipt for containment of every candidate
credential class identified by the safe scanner rule. The quarantine and no-further-download
receipts bind an authority-installed denylist for every affected artifact; they prove that no later
campaign job may download it, not that a prior public download did not occur.
`complete_publication_pr_close_receipt_sha256` is required only for
`COMPLETE_PUBLICATION_PR_OPEN` and must be literal null for every other parent.

Canonical bytes are RFC 8785 JSON over those exact fields excluding the final digest, UTF-8 with no
terminal newline; timestamps are UTC RFC 3339, IDs are canonical integers, roots are lowercase
64-hex SHA-256, and extra, missing, null-where-forbidden, duplicate, or reordered array members are
rejected. The final digest is domain-separated with
`laconian-credential-exposure-incident-evidence-v1`. The evidence is safe metadata only and cannot
contain the suspected credential bytes.

A secret-free `INVALID_EVENT_DISMISSED` proof may clear a benign hold in every state, including
`RESULT_MERGED` and `RELEASED`. It must establish that the event was either an unauthorized-origin
no-op or a byte-identical replay of an already applied event, and that it changed no state, ledger,
artifact, reservation, credential access, or provider dispatch. A read-only job under human
approval from `benchmark-publish`, by an actor distinct from the rejected event source and workflow
trigger actor, verifies and signs the dismissal; clearing the hold does not create a state
transition.

For a nondismissible verified defect before merge, a valid `PERMANENT_STOP` cites the hold and takes
the enumerated invalid path. The sole no-prior-hold exception is `credential_exposure`, whose
incident evidence must instead prove the exact current hold root or proven absence as specified
above. At `RESULT_MERGED`, the defect uses `RELEASE_PLAN_INVALIDATED`; at `RELEASED`, the state
remains terminal and the defect starts a new correction lineage with an explicit `supersedes` hash.
Correction invalidations have exactly two distinct kinds:
`correction_publication_invalidation` and `correction_release_invalidation`. Their schemas,
allowed parents, and evidence are distinct; a generic correction-invalidation alias is forbidden.

The allowed durable transitions are:

| From | Event and required evidence | To | Authorized next action |
|---|---|---|---|
| none | `PREFLIGHT_SEALED`: valid tag, plans, budget, price snapshot | `PREFLIGHTED` | prepare generation batch |
| `PREFLIGHTED` or `GENERATION_RESUMABLE` | `BATCH_RECEIPT_CONSUMED`: exact unused reservation/job tuple and current-price attestation | `GENERATION_ACTIVE` | execute frozen generation batch |
| `GENERATION_ACTIVE` | `NO_DISPATCH_PROVED`: exact job evidence proves zero provider dispatch and releases only never-started reservations | `GENERATION_RESUMABLE` | prepare a new exact batch attempt |
| `GENERATION_ACTIVE` | `VERIFIED_PARTIAL`: exact successor ledger, no STOP, suffix remains | `GENERATION_RESUMABLE` | prepare exact next suffix |
| `GENERATION_ACTIVE` | `GENERATION_SET_SEALED`: all 36 capsule hashes, `generation_context_expectation_sha256`, and `verified_generation_context_root` | `GENERATION_COMPLETE` | deterministic hard score |
| `GENERATION_COMPLETE` | `HARD_SCORE_SET_SEALED`: all 36 request-set hashes | `HARD_SCORE_COMPLETE` | prepare judge batch |
| `HARD_SCORE_COMPLETE` or `JUDGE_RESUMABLE` | `BATCH_RECEIPT_CONSUMED`: exact unused reservation/job tuple and current-price attestation | `JUDGE_ACTIVE` | execute frozen judge batch |
| `JUDGE_ACTIVE` | `NO_DISPATCH_PROVED`: exact job evidence proves zero provider dispatch and releases only never-started reservations | `JUDGE_RESUMABLE` | prepare a new exact batch attempt |
| `JUDGE_ACTIVE` | `VERIFIED_PARTIAL`: exact successor ledger, no STOP, suffix remains | `JUDGE_RESUMABLE` | prepare exact next suffix |
| `JUDGE_ACTIVE` | `JUDGE_SET_SEALED`: all 36 judge-attachment hashes | `JUDGE_COMPLETE` | provider-evidence integrity validation |
| `JUDGE_COMPLETE` | `EVIDENCE_INVENTORY_SEALED`: exact generation/hard-score/judge coverage | `PROVIDER_EVIDENCE_VERIFIED` | create blind audit packet |
| `PROVIDER_EVIDENCE_VERIFIED` | `AUDIT_SEALED`: both reveal chains and signed adjudication or explicit unresolved records | `AUDIT_COMPLETE` | semantic aggregation/inference |
| `AUDIT_COMPLETE` | `ANALYSIS_SEALED`: deterministic scores, bootstrap, sensitivity, outcomes | `ANALYSIS_COMPLETE` | run complete collector |
| `ANALYSIS_COMPLETE` | `COMPLETE_BUNDLE_SEALED`: exact full allowlist and checksum | `BUNDLE_COLLECTED` | prepare publication plan |
| `BUNDLE_COLLECTED` | `COMPLETE_PUBLICATION_PR_OPENED`: exact `bundle_kind=complete`, sealed complete-bundle root, publication plan, branch, base, head, PR | `COMPLETE_PUBLICATION_PR_OPEN` | review and required CI |
| `BUNDLE_COLLECTED` | `COMPLETE_PUBLICATION_PLAN_INVALIDATED`: base/head moved or plan check failed, bundle digest unchanged | `BUNDLE_COLLECTED` | prepare a new complete publication plan |
| `COMPLETE_PUBLICATION_PR_OPEN` | `RESULT_MERGED`: approved complete-bundle PR, exact matching sealed-root lineage and merge tree | `RESULT_MERGED` | prepare release plan |
| `COMPLETE_PUBLICATION_PR_OPEN` | `COMPLETE_PUBLICATION_PLAN_INVALIDATED`: exact complete-bundle PR closed, sealed complete-bundle root unchanged | `BUNDLE_COLLECTED` | prepare a new complete publication plan |
| `RESULT_MERGED` | `RESULT_RELEASED`: protected result tag and checksum-bound assets | `RELEASED` | documentation/social follow-up |
| `RESULT_MERGED` | `RELEASE_PLAN_INVALIDATED`: verified tree, bundle, security, or provenance defect | `RELEASE_BLOCKED` | start a correction lineage; do not tag/release |
| `RELEASE_BLOCKED` or `RELEASED` | `CORRECTION_INTENT_AUTHORIZED`: exact append-only intent, parent authority OID, plans, object names/roots, prior/new latest pointers, and idempotency keys | same campaign state | execute or recover exact correction publication effect |
| `RELEASE_BLOCKED` or `RELEASED` | `CORRECTION_PUBLICATION_RECORDED`, `CORRECTION_MERGE_RECORDED`, `CORRECTION_TAG_RECORDED`, or `CORRECTION_RELEASE_RECORDED`: exact next correction phase and adopted/created effect receipt | same campaign state | execute or recover exact next phase |
| `RELEASE_BLOCKED` or `RELEASED` | `CORRECTION_INVALIDATED`: exactly one typed correction invalidation with allowed phase parent and terminal evidence | same campaign state | correction lineage terminal; a new correction ID is required |
| `RELEASE_BLOCKED` | `CORRECTION_RESULT_RELEASED`: exact correction lineage and complete corrected publication/merge/release evidence | `RELEASED` | documentation/social follow-up from corrected latest pointer |
| `RELEASED` | `CORRECTION_RESULT_RELEASED`: exact append-only correction lineage and complete corrected publication/merge/release evidence | `RELEASED` | preserve prior terminal history; follow the new latest pointer |
| `PREFLIGHTED`, `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`, `AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED`, or `COMPLETE_PUBLICATION_PR_OPEN` | `PERMANENT_STOP`: exact parent-specific reason and evidence; `credential_exposure` requires `CredentialExposureIncidentEvidenceV1`; an open complete publication PR requires its exact close receipt | `STOPPED_INVALID` | prefix/STOP finalizer only |
| any ready/resumable provider state | `BUDGET_EXHAUSTED`: next minimum batch cannot fit | `BUDGET_INCOMPLETE` | prefix/STOP finalizer only |
| `STOPPED_INVALID` or `BUDGET_INCOMPLETE` | `INVALID_PREFIX_SEALED`: exact completed prefix and missing suffix | `INVALID_FINALIZED` | publish registry/incident only |
| `INVALID_FINALIZED` | `INVALID_PUBLICATION_PLAN_INVALIDATED`: base/head moved or plan check failed, prefix digest unchanged | `INVALID_FINALIZED` | prepare a new invalid publication plan |
| `INVALID_FINALIZED` | `INVALID_PUBLICATION_PR_OPENED`: exact `bundle_kind=invalid_prefix`, sealed prefix root, publication plan, branch, base, head, PR | `INVALID_PUBLICATION_PR_OPEN` | review and required CI, no performance claim |
| `INVALID_PUBLICATION_PR_OPEN` | `INVALID_PREFIX_MERGED`: approved invalid-prefix PR, exact sealed-prefix lineage and merge tree | `INVALID_PREFIX_MERGED` | terminal registry/incident publication only |
| `INVALID_PUBLICATION_PR_OPEN` | `INVALID_PUBLICATION_PLAN_INVALIDATED`: exact invalid-prefix PR closed, sealed prefix root unchanged | `INVALID_FINALIZED` | prepare a new invalid publication plan |

Within that generated transition, `credential_exposure` has exactly these allowed parents:
`GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`,
`JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`,
`AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED`, and
`COMPLETE_PUBLICATION_PR_OPEN`. The event must reproduce every current authority, state, ledger,
artifact-inventory, active-plan, and hold root from its parent. `PREFLIGHTED` is excluded because no
provider-bearing artifact has been uploaded; `RESULT_MERGED` uses `RELEASE_PLAN_INVALIDATED`, and
`RELEASED` uses correction lineage. The reason is also forbidden from `STOPPED_INVALID`,
`BUDGET_INCOMPLETE`, `INVALID_FINALIZED`, `INVALID_PUBLICATION_PR_OPEN`, `INVALID_PREFIX_MERGED`,
`RELEASE_BLOCKED`, correction states, and every terminal state. Neither a generic incident event nor
a reason alias can bypass this parent set. Noncredential artifact corruption, traversal, inventory,
or provenance defects remain under their existing phase-specific reason discriminators and cannot
be mislabeled `credential_exposure`.

An active job that exits at the soft deadline is resumable only through `VERIFIED_PARTIAL`. A lost
job without that event uses `NO_DISPATCH_PROVED` only when durable job and provider evidence proves
that the entire batch made zero dispatches and every released reservation is `never_started`;
otherwise ambiguity emits `PERMANENT_STOP`. Audit nonparticipation or an unrevealed commitment emits
a reason-specific `PERMANENT_STOP`; an explicitly signed unresolved adjudication is instead a valid
`AUDIT_SEALED` event whose affected model outcome is inconclusive. No dispatcher may jump from a
partial, STOP, budget, or release-blocked state into live execution or complete collection. An
unresolved `InvalidEventHoldV1` blocks every otherwise allowed transition.

`RESULT_MERGED` is accepted only from `COMPLETE_PUBLICATION_PR_OPEN`. Its event must reproduce
`bundle_kind=complete`, the exact `COMPLETE_BUNDLE_SEALED` root, `BUNDLE_COLLECTED` root,
`PublicationPlanV1` root, approved head, PR, merge commit, and resulting tree root as one matching
lineage. An invalid-prefix root, mixed root, absent discriminator, or
`INVALID_PUBLICATION_PR_OPEN` parent is an invalid event and creates a hold without mutation.
`INVALID_PREFIX_MERGED` is terminal: it accepts no result-release, correction-release,
documentation, website, release-note, or social-promotion event. Its only public meaning is that the
safe registry/incident prefix was human-reviewed and merged. Closing instead of merging either PR
kind requires its type-specific invalidation event; cross-kind close/merge events and generic
`PUBLICATION_PR_OPEN` are not schema values and are testable rejection cases. An
`INVALID_PUBLICATION_PLAN_INVALIDATED` close receipt is terminal for that exact invalid-prefix plan,
branch, and PR: they cannot be reopened or reused, no release/promotion is authorized, and
`INVALID_FINALIZED` permits only creation of a new plan with a new branch/PR identity over the same
unchanged sealed prefix root.

### 7.5 Correction side-effect protocol

Correction authority is stored only in the append-only tree of
`refs/heads/benchmark-authority/<campaign-id>`. For correction ID `<correction-id>`, the only
authoritative paths are the ordered members under
`corrections/<correction-id>/`: `intent.json`, `publication-receipt.json`, `merge-receipt.json`,
`tag-receipt.json`, `release-receipt.json`, and exactly one of `finalization.json` or
`invalidation.json`. Every record binds the campaign ID, correction ID, exact prior campaign-state
hash, prior authority commit OID, prior correction-phase record hash, monotonically increasing
phase number, `supersedes` root, and its own canonical digest. Files are append-only; an absent
later member means the phase has not been durably recorded.

Before any external correction write, `CORRECTION_INTENT_AUTHORIZED` installs `intent.json` by one
expected-OID, non-force, fast-forward authority compare-and-swap. The intent binds the complete
correction publication and release plans; exact base/head/result-tree and sealed-bundle roots;
branch, PR marker, annotated-tag name/message/target, draft-release name/body, ordered asset names
and digests; prior and proposed latest-result pointers; allowed App actors; and a distinct
idempotency key for publication, tag, draft/assets, publish, and each receipt CAS. Each key is the
domain-separated canonical digest of campaign ID, correction ID, phase, plan root, object name, and
expected target/root. GitHub does not provide one universal idempotency header for these effects,
so exact names, immutable targets, embedded intent markers, actors, and roots are the semantic
idempotency boundary; the design makes no stronger platform claim.

The publisher may create or adopt only the intent-bound branch and PR. A key-free state-writer step
then persists `publication-receipt.json` with `CORRECTION_PUBLICATION_RECORDED` by expected-OID CAS.
After protected human merge, it reconstructs the PR approvals, required checks, merge actor, merge
commit, result tree, and sealed-root lineage and persists `merge-receipt.json` with
`CORRECTION_MERGE_RECORDED`. The release finalizer may then create or adopt only the exact annotated
tag and persists `tag-receipt.json` with `CORRECTION_TAG_RECORDED`. It creates or adopts the exact
draft release, reconciles every asset name and digest, performs at most one publish transition, and
persists `release-receipt.json` with `CORRECTION_RELEASE_RECORDED`. Every receipt CAS has the exact
previous authority OID and phase record as parent; a competing or skipped parent fails without
changing authority.

Recovery is mandatory and idempotent. Before retrying an effect, the fixed tool queries the exact
intent-bound ref, PR marker, tag name, release ID/name, and asset names. If nothing exists, it
performs the effect once. If an object already exists with the exact actor, immutable target,
embedded idempotency marker, and content/root, it adopts the object and records the missing receipt
without duplicating it. A mismatched object is never overwritten, force-updated, deleted, or
silently orphaned. A crash after tag creation, during draft asset upload, after draft completion,
or after publish is recovered by adopting all exact existing objects, uploading only absent
intent-bound assets while the release is still a draft, and performing publish only if it remains
draft. An immutable published release with exact assets is adopted; any conflicting or incomplete
immutable object terminates through correction-release invalidation. All retries, queries,
adoptions, conflicts, and returned object IDs/digests are terminal evidence.

The two invalidation records are closed and phase-specific. A
`correction_publication_invalidation` is allowed only with `intent.json` or
`publication-receipt.json` as parent and before a valid merge receipt; it binds the reason, exact
publisher actor, proof of no PR or the exact PR close receipt, all discovered external objects, and
the unchanged proposed latest pointer. A `correction_release_invalidation` is allowed only after
`merge-receipt.json`, with that receipt or a later tag/release receipt as parent; it binds the
merge/tree roots, every created or adopted tag/release/asset object, failure and reconciliation
receipts, and proof that prior immutable objects and the latest pointer were not changed. Either is
installed as `invalidation.json` with `CORRECTION_INVALIDATED` by one expected-OID CAS, makes that
correction lineage terminal, and leaves the campaign in `RELEASE_BLOCKED` or `RELEASED` as it was.
Cross-phase use, both kinds, a generic alias, or invalidation after finalization is rejected. A new
attempt requires a new correction ID and new external names.

Only after all five phase records verify may finalization run. `CORRECTION_RESULT_RELEASED` is the
sole escape from `RELEASE_BLOCKED`; it binds the correction-lineage root, exact predecessor and
`supersedes` event, prior/new latest pointers, publication/merge/tag/release receipts, corrected
result-tree root, annotated-tag object root, and complete ordered release-asset root. The state
writer installs `finalization.json`, the new latest pointer, the terminal correction evidence root,
and the escape event in one ordered authority commit and publishes it with one expected-OID,
non-force, fast-forward CAS. A correction from already `RELEASED` appends the same evidence while
state remains `RELEASED`; it cannot rewrite prior state, history, pointer events, tags, or releases.

### 7.6 Public replay CLI is offline and non-evidentiary

All seven public `laconian-benchmark` commands are offline replay conveniences and are
non-evidentiary: `hard-score`, `prepare-judge`, `seal-judge`, `sample-audit`, `seal-audit`,
`analyze`, and `verify`. They may reconstruct or inspect ordinary values from supplied local
artifacts, but their outputs cannot create campaign authority, advance `CampaignStateV1`, satisfy a
live prerequisite, mint a verified context, or enter publication evidence merely because the
bytes or hashes match.

Live `hard-score`, `prepare-judge`, and `seal-judge` execute only as Runtime campaign-side stages
that receive the in-memory verified generation-context capability. Their exact internal entrypoints
are `laconian_eval.campaign.runtime.Runtime.hard_score`, `.prepare_judge`, and `.seal_judge`; the
only constructor is the non-public
`laconian_eval.campaign.runtime._reconstruct_verified_runtime`, which requires the in-memory
capability from section 7.1. Live `sample-audit`, `seal-audit`, `analyze`, and `verify` execute only
as `laconian_eval.campaign.publication.Publication.campaign.evaluation_stage` methods with those
exact names; the only constructor is the non-public
`laconian_eval.campaign.publication._reconstruct_verified_publication` from current authority.

The public console entrypoint remains `laconian_eval.cli:main` and may call only modules under
`laconian_eval.replay`; it cannot import either campaign constructor or capability type. Import- and
call-graph tests enumerate these seven public command handlers and seven live methods and fail on
any shared writer entrypoint. No live workflow invokes the public replay CLI. No verified
capability, capability wrapper, or capability-bearing context is serialized to an artifact,
provider index, command line, workflow input, or environment value.

## 8. Provider failures, retries, and spend

The campaign has a fixed **USD 75 maximum authorized request exposure** under the committed price
snapshot. The pilot has a separate USD 5 cap. A preflight calculation above the cap stops before
environment approval. Current-price verification follows the reviewer attestation in section 7.1;
there is no brittle automatic scrape. This is a hard scheduling/authorization bound, not a claim
that an external provider invoice can be controlled perfectly or that every planned request is
guaranteed to fit. If cumulative charged-or-reserved exposure plus the next conservative batch
reservation no longer fits, the campaign stops incomplete and is reported accordingly.

The committed `PriceSnapshotV1` and each reviewer `PriceAttestationV1` are tier-specific.
`price_snapshot.service_tier == price_attestation.requested_service_tier == "default"` is required
for every requested model ID and batch. Each frozen requested model ID has separate non-null
reviewed rates for ordinary
uncached input, cache reads, cache writes, visible output, and reasoning output. In particular, a
null cache-write rate is forbidden even though the request contract disables writes; any numeric
rate, including zero, must itself be explicitly sourced and reviewed rather than inferred. The
snapshot and attestation bind the versioned `<= 272_000` conservative input-exposure proof; no
long-context schedule is in the authorized price vocabulary.

An append-only campaign spend ledger tracks both batch and request-attempt exposure. Before a
provider job can map the key, the secret-free preparation path persists a worst-case reservation
for every initial call and allowed retry in its frozen `BatchPlanV1`, including input bounds and
output-token caps. Each reservation is a typed vector with distinct
`ordinary_uncached_input_tokens`, `cache_read_tokens`, `cache_write_tokens`,
`visible_output_tokens`, and `reasoning_output_tokens` components and their frozen prices; read
evidence cannot satisfy or erase the write component. Its finalized receipt binds the campaign,
phase, ordered plan items, price snapshot, requested `default` service tier, literal
`prompt_cache_options: {"mode": "explicit", "ttl": "30m"}`, the recursive absence of every
`prompt_cache_breakpoint`, predecessor ledger, and exact provider-job identity tuple
`(workflow_run_id, run_attempt, job_id, batch_attempt_id)`.

The conservative reservation envelope is versioned and mechanically reproducible. Let `P_u`,
`P_r`, and `P_w` be the frozen ordinary-input, cache-read, and cache-write USD-per-million rates,
and let `P_v` and `P_h` be visible- and reasoning-output rates. For generation, one attempt reserves:

```text
R_attempt = (272_000 * max(P_u, P_r, P_w) +
             1_024 * max(P_v, P_h)) / 1_000_000
```

The three input components remain separately recorded with the coupling invariant
`ordinary_uncached + cache_read + cache_write <= 272_000`; the maximum-rate envelope prevents
double-counting mutually exclusive input-token partitions while retaining worst-case write
exposure. The judge substitutes `768` for `1_024`. A confirmatory request permits one initial
attempt plus five retries, so its worked worst-case chain is exactly `6 * R_attempt`; a full
40-request shard would be `40 * 6 * R_attempt`. For example, with remaining authorization `B`,
preflight may schedule at most `floor(B / (6 * R_attempt))` generation requests and schedules none
if that value is zero. It does not substitute long-context rates or assume cache reads/writes are
zero to make the USD 75 cap fit.

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

Every terminal attempt stores the exact response paths and separate applied-cache-control,
cache-read, and cache-write status enums from section 6.2, plus total input, ordinary-uncached input,
visible output, reasoning output, billed output, total usage, and a source digest for each.
Cache-control/read/write records are never derived from one another. `cache_write_tokens = 0` is
accepted only from the exact canonical path with `reported_zero`; absent or incomplete detail stays
`missing`, never becomes zero, and retains the full write component. If delivery is unknown or any
Responses API result was received, `missing`, `mismatch`, or `invalid` appends STOP and permits zero
later calls.

Any trusted `reported_nonzero` cache-write usage is reconciled at the frozen non-null cache-write
rate and included in charged exposure before STOP is appended. The record and cost remain evidence;
STOP does not discard or relabel the write. `reported_nonzero` cache-read usage reconciles only the
separate read component and also stops because it violates the explicit/no-breakpoint contract.
The same per-attempt record stores exactly one service-tier accounting status from section 6.2.
`missing` or `mismatch` returned-tier evidence retains all unreconciled worst-case components,
appends STOP, and permits zero later calls.

The automatic retry taxonomy is closed and versioned:

- authentication and permission failures, including both 401 and 403, durably stop the campaign;
- only a structured provider 429 response classified `delivery_certainty=definitely_rejected`,
  independently proven to have no response usage, and recorded as
  `not_applicable_definitely_rejected` for service-tier accounting may be retried automatically;
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

The live stage receives only the in-memory `VerifiedGenerationContextExpectationV1` reconstructed
under section 7.1. Every hard-score set and downstream judge projection repeats and verifies the
tagged hard-scorer source hash, hard-score, judge, statistical, and audit protocol hashes,
`protocol_attestations_root`, both identity-registry digests, and the common `workflow_root`.
Provider-evidence validation rejects any attachment or provider-index projection that omits,
changes, nests as alleged authority, or substitutes one of these bindings.

Only deterministic hard-pass responses enter semantic judging. The judge is `gpt-5.6-sol` with:

- literal wire `service_tier: "default"`, literal
  `prompt_cache_options: {"mode": "explicit", "ttl": "30m"}`, and no
  `prompt_cache_breakpoint` anywhere;
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

Judge requests follow the same service-tier, applied-cache-control, cache-read/cache-write,
input-bound, delivery, retry, budget, journaling, and artifact rules as generation. A semantic-gated report requires 100%
judgment coverage for hard-pass responses. Judge failure does not silently fall back to a
hard-gated performance claim.

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
reasoning output, billed output, total, cache-read-input tokens, cache-write-input tokens,
estimated cost, and latency remain separate descriptive metrics.

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

The input-tag manifest binds the exact two-entry `AuditReviewerRegistryV1` from section 6.5,
including each numeric GitHub account ID, exact login, signing-verification mode, fingerprint
field, canonical bytes, and digest. Independence is preserved through ordinary user-authored pull
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
- `benchmark-publish`, requiring separate approval for each publisher or release-finalizer write.

At specification time the repository API reports default workflow permission `read` and
`can_approve_pull_request_reviews: false`. The read default remains. The repository
`GITHUB_TOKEN` is read-only everywhere, including state, provider, publication, correction, and
release workflows; it never creates or closes a PR, moves an authority ref, creates a tag or
release, uploads release assets, approves, or merges.

Self-review and admin bypass are disabled where GitHub supports those controls. Deployment refs
are restricted to the protected benchmark tags. Approval actors and deployment identities are
retained in provenance.

All automated benchmark-workflow writes use exactly three installed, pairwise-distinct,
repository-scoped GitHub Apps with actor IDs frozen in the security protocol and receipts:

- the **state-writer App** performs only expected-OID, non-force, fast-forward updates on
  `benchmark-authority/*`, for requests admitted from the fixed hash-verified reusable
  state-writer job;
- the **publisher App** creates the exact result branch and PR bound by the current
  `PublicationPlanV1`, or closes that exact PR after its typed publication invalidation; and
- the **release-finalizer App** creates the exact protected annotated result tag, creates the exact
  draft release and checksum-bound assets, verifies their returned roots, and performs exactly one
  transition that publishes that draft.

The Apps' GitHub permission grants are necessarily broader than those semantic operations, so the
design does not claim that unavailable GitHub capability scopes enforce the narrow roles. Narrowing
is enforced jointly by fixed hashed tools, endpoint-policy allow/deny tests, protected branch/tag
rulesets, immutable Releases configuration, expected-object receipts, exact actor restrictions,
environment approvals, and postcondition verification. An endpoint, method, ref, actor, asset, or
state transition outside the frozen policy fails closed and leaves a durable receipt or incident.

The state-writer App private key is held only by an identity-bound external token broker; it is not
stored in repository, organization, environment, or Actions secrets. The broker accepts GitHub OIDC
only under a versioned `StateBrokerCallerPolicyV1`. The policy freezes the audience, exact
`OWNER/REPO`, numeric `repository_id`, exact owner login and numeric `repository_owner_id`, and the
repository's exact OIDC subject-customization/immutable-subject configuration state and digest; it
does not assume one GitHub default `sub` format across repository creation, opt-in, rename, or
transfer boundaries. The broker requires `typ=JWT`, `alg=RS256`, a `kid` that resolves through the
current GitHub OIDC JWKS, issuer `https://token.actions.githubusercontent.com`, the frozen `aud`, a
`sub` derived by the frozen repository configuration, `nbf <= iat <= now < exp`, an accepted age
of at most five minutes, and a durable never-before-seen `jti`, then constructs an exact identity
projection containing `repository`, `repository_id`, `repository_owner`, `repository_owner_id`,
`actor`, `actor_id`, `ref`, `ref_type`, `sha`, `event_name`, `workflow`, `workflow_ref`,
`workflow_sha`, `job_workflow_ref`, `job_workflow_sha`, `run_id`, `run_attempt`,
`check_run_id`, and `runner_environment`. The projection requires every listed field; `actor` and
`actor_id` must be the same plan-authorized human dispatcher in the frozen operator registry, and
the `environment` claim must be absent because the reusable state-writer job does not use a GitHub
environment. Standard JOSE/time claims remain raw token metadata. Any missing, duplicate, unknown
identity field in the signed broker request, or value inconsistent with the JWT, GitHub API run,
campaign plan, or frozen registry is denied; extra raw GitHub claims are retained but never confer
authority.

For a called workflow, GitHub's `workflow`, `ref`, `workflow_ref`, and `workflow_sha` describe the
caller, while `job_workflow_ref` and `job_workflow_sha` describe the called reusable workflow. The
caller reference must therefore be exactly
`OWNER/REPO/.github/workflows/<allowed-caller>.yml@<trigger-ref>` and the called reference exactly
`OWNER/REPO/.github/workflows/benchmark-publication-state.yml@<trigger-ref>`; bare paths and a
synthetic `workflow_ref@C0` comparison are forbidden. `workflow` must equal the exact top-level
workflow name extracted from the verified caller member. The caller uses the same-repository
reusable-workflow form, so the called workflow resolves at the same triggering commit without a
self-referential C0 literal in C0's own YAML. The called workflow has exact job ID `state_writer`.
Because GitHub OIDC has no step-ID claim and `id-token: write` is job-scoped, the entire reusable
job is the credential boundary: it contains only GitHub's OIDC bootstrap and one fixed,
hash-pinned, argument-closed broker client, with no checkout, generated command, caller script, or
caller-controlled action before or after it. `state-cas` is a reviewed YAML step ID, not an OIDC
identity claim. The broker binds `check_run_id` to that reusable job through the GitHub API and
performs the expected-OID CAS itself; no installation token is returned to any Actions step.

`<trigger-ref>` has exactly one of two forms selected by the caller row: the campaign's exact
protected input tag `refs/tags/<campaign-input-tag>`, with `ref_type=tag`, `sha=C0`, and both
workflow SHA claims equal to C0; or exact `refs/heads/main`, with `ref_type=branch`, `sha` and both
workflow SHA claims equal to the single main commit already bound by the applicable audit,
analysis, collection, publication, release, dismissal, or correction plan. For a main run the
broker also reads both workflow members at that commit and requires their bytes to equal the
corresponding C0-derived member hashes in the common workflow root. All caller rows require
`event_name=workflow_dispatch`; a reusable `workflow_call` is the mechanism of the called job, not
the triggering event reported by these OIDC tokens. The closed caller/ref/event mapping is:

| Caller workflow | Required triggering ref | Allowed event types |
|---|---|---|
| `benchmark-preflight.yml` | exact campaign input tag | `PREFLIGHT_SEALED` |
| `benchmark-batch.yml` | exact campaign input tag | `BATCH_RECEIPT_CONSUMED`, `NO_DISPATCH_PROVED`, `VERIFIED_PARTIAL`, `GENERATION_SET_SEALED`, `JUDGE_SET_SEALED`, `PERMANENT_STOP`, `BUDGET_EXHAUSTED` |
| `benchmark-hard-score.yml` | exact campaign input tag | `HARD_SCORE_SET_SEALED`, `PERMANENT_STOP` |
| `benchmark-evidence.yml` | exact campaign input tag | `EVIDENCE_INVENTORY_SEALED`, `PERMANENT_STOP` |
| `benchmark-audit.yml` | exact plan-bound `main` | `AUDIT_SEALED`, `PERMANENT_STOP` |
| `benchmark-analysis.yml` | exact plan-bound `main` | `ANALYSIS_SEALED`, `PERMANENT_STOP` |
| `benchmark-collect-complete.yml` | exact plan-bound `main` | `COMPLETE_BUNDLE_SEALED`, `PERMANENT_STOP` |
| `benchmark-finalize-invalid.yml` | exact campaign input tag | `INVALID_PREFIX_SEALED` |
| `benchmark-dismiss-hold.yml` | exact plan-bound `main` | `INVALID_EVENT_DISMISSED`, `PERMANENT_STOP` |
| `benchmark-publish.yml` | exact plan-bound `main` | `COMPLETE_PUBLICATION_PR_OPENED`, `INVALID_PUBLICATION_PR_OPENED`, `COMPLETE_PUBLICATION_PLAN_INVALIDATED`, `INVALID_PUBLICATION_PLAN_INVALIDATED`, `RESULT_MERGED`, `INVALID_PREFIX_MERGED`, `PERMANENT_STOP`, `CORRECTION_INTENT_AUTHORIZED`, `CORRECTION_PUBLICATION_RECORDED`, `CORRECTION_MERGE_RECORDED`, and `CORRECTION_INVALIDATED(kind=correction_publication_invalidation)` |
| `benchmark-release.yml` | exact plan-bound `main` | `RESULT_RELEASED`, `RELEASE_PLAN_INVALIDATED`, `CORRECTION_TAG_RECORDED`, `CORRECTION_RELEASE_RECORDED`, `CORRECTION_RESULT_RELEASED`, and `CORRECTION_INVALIDATED(kind=correction_release_invalidation)` |

Paths are fully qualified as above; no other member of the 15-path inventory may call the broker.
The broker verifies the run and reusable caller/callee relationship through the GitHub API and
requires `run_id`, `run_attempt`, and `check_run_id` to resolve to the exact reusable job, exact
caller and callee workflow commits, and exact initial-run actor. On a rerun it separately obtains
the REST `triggering_actor` and requires that login/numeric ID to be plan-authorized; no nonexistent
OIDC `triggering_actor` claim is assumed. It also requires the common workflow root, campaign ID,
caller-allowed event type,
`refs/heads/benchmark-authority/<campaign-id>` target, and expected current OID in the signed token
request. `PERMANENT_STOP` is additionally closed by schema parent and reason: batch may emit it only
from `PREFLIGHTED`, `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `HARD_SCORE_COMPLETE`,
`JUDGE_RESUMABLE`, or `JUDGE_ACTIVE` for provider, reservation, delivery, identity, ledger, or
security evidence; hard-score only from `GENERATION_COMPLETE` for generation-context or hard-score
integrity failure; evidence only from `JUDGE_COMPLETE` for coverage or provider-evidence failure;
audit only from `PROVIDER_EVIDENCE_VERIFIED` for identity, nonparticipation, reveal, or adjudication
protocol failure; analysis only from `AUDIT_COMPLETE` for statistical, provenance, or integrity
failure; and complete collection only from `ANALYSIS_COMPLETE` for bundle coverage or lineage
failure. Publish may emit it only from `BUNDLE_COLLECTED` or `COMPLETE_PUBLICATION_PR_OPEN`, and the
latter requires the exact publisher-App close receipt for that open PR. Dismiss-hold may emit it
only from one of those already enumerated predecessor states after proving a cited nondismissible
`InvalidEventHoldV1` whose source evidence matches the same phase-specific reason. No other
predecessor, reason discriminator, caller, or wildcard STOP authority exists.

Those ordinary reason grants do not subsume `credential_exposure`. That discriminator has this
separate exhaustive caller/parent matrix; every cell also requires the exact
`CredentialExposureIncidentEvidenceV1` roots and receipts above:

| Credential-incident caller | Exact allowed current parent states | Additional restriction |
|---|---|---|
| `benchmark-batch.yml` | `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE` | affected artifact was uploaded or consumed by the exact current batch plan/run |
| `benchmark-hard-score.yml` | `GENERATION_COMPLETE` | affected generation artifact is an exact hard-score input or scan output |
| `benchmark-evidence.yml` | `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`, `AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED` | designated cross-phase inventory/scanner; every artifact is already in the current inventory or exact phase plan |
| `benchmark-audit.yml` | `PROVIDER_EVIDENCE_VERIFIED` | affected artifact is an exact audit input or output |
| `benchmark-analysis.yml` | `AUDIT_COMPLETE` | affected artifact is an exact analysis input or output |
| `benchmark-collect-complete.yml` | `ANALYSIS_COMPLETE` | affected artifact is an exact collection input or proposed bundle member |
| `benchmark-publish.yml` | `BUNDLE_COLLECTED`, `COMPLETE_PUBLICATION_PR_OPEN` | affected artifact is publication-plan bound; the open-PR parent additionally requires publisher-App closure of that exact PR and its close receipt |
| `benchmark-dismiss-hold.yml` | every allowed `credential_exposure` parent except `COMPLETE_PUBLICATION_PR_OPEN` | only with the exact current nondismissible hold root and incident evidence independently verified under dismissal approval |

`benchmark-preflight.yml`, `benchmark-finalize-invalid.yml`, `benchmark-release.yml`, both PR
validators, and the docs validator have no credential-incident authority. The matrix grants no
caller a different STOP reason, parent, event, ref, artifact, or App operation. A phase workflow
that merely receives an unbound artifact ID or scanner assertion is denied.

Pull-request refs, branches other than exact `main`, any other tag, a tag/object/commit mismatch,
unlisted callers or called workflows, caller/callee SHA or byte mismatch, an unexpected
`environment`, a different event/job/check-run/actor, and a stale expected OID are denied before
token minting. The broker obtains a single-repository, short-lived installation token for one fixed
state-writer invocation; the token never leaves the broker, expires within five minutes, and is
discarded immediately after the one expected-OID CAS. Its request ID, raw OIDC
subject/claims, canonical identity projection, App actor, expiry, event kind and STOP reason,
authority ref, expected/new OIDs, and broker decision are recorded in the state receipt. Policy
tests prove an unrelated workflow—even on an otherwise allowed ref—cannot obtain the credential.

Publisher and release-finalizer credentials are mapped only in their separately approved
`benchmark-publish` jobs. State-writer App credentials are never mapped into Actions; the broker
uses them only after the fixed reusable job passes the closed policy above. No App credential is
present in provider-controller, model-output parsing, scoring, packaging, or artifact-inspection
scope, and no App ever receives `OPENAI_API_KEY` or a model-output field as an input, environment
value, argument, stdin, or log. A fixed byte-blind transport step may transmit only already sealed
opaque Git objects or release assets whose roots are plan-bound; it cannot decode or select their
contents. Provider jobs have read-only repository permissions. Publication jobs never receive the
provider key. No `pull_request_target`, privileged automatic `workflow_run`, untrusted fork code,
or model-generated command is used.

Human authorities are separate and are not counted among the three automated Apps. The three
protocol reviewers author and sign their exact protocol-attestation commits/PRs; the two audit
reviewers author their commitment and reveal commits/PRs and sign adjudication; and maintainers
perform environment/deployment approvals, exact-head validation authorization, protected PR review,
and protected merges. These acts use the humans' own GitHub identities through normal protected
repository controls; no human token is injected into a workflow. Human authorship or approval
cannot replace an App receipt or authority CAS, and no App may substitute for a required human
reviewer, approve its own PR, or merge.

The live secret is a dedicated project-scoped restricted key created for this benchmark campaign,
not an organization/admin key. The project has no unrelated consumers, exposes only the API
capabilities required by the frozen runner, and uses a provider-side project spend guard where
available. The key is revoked or rotated after the campaign and immediately after any incident.

Each provider batch has the exact four-role/job boundary in section 7.2: secret-free prepare,
protected repository-read-only provider, key-free receipt/state writer, and key-free post/state
writer. The prepare job imports and verifies checkpoints, checks the predecessor ledger/STOP state,
constructs `BatchPlanV1`, creates its worst-case reservation, and emits a digest-bound safe input
artifact. The protected provider job checks out the exact detached preflight commit and re-verifies
the tag object and plan digest, but its controller step remains disabled until the receipt/state
writer wins the single expected-OID authority CAS and the job verifies that won receipt. The
post/state writer validates the output and performs the successor expected-OID CAS; neither state
writer maps the provider key.
`${{ secrets.OPENAI_API_KEY }}` is mapped through step-scoped `env` only for the single
hash-verified provider-controller command, never at workflow or job scope and never during
checkout, dependency setup, artifact download/upload, or packaging. No third-party action or
arbitrary shell runs while the key is in scope; tracing is disabled, SDK retries are zero, and
ambient proxy credentials are not trusted.

All Actions are pinned to full commit SHAs. Every job checks out the preflight-recorded detached
commit SHA, never a tag name after preflight, and checkout does not persist credentials. Workflow
policy tests fail on a floating action ref, widened `GITHUB_TOKEN` permission, wrong App actor or
credential scope, forbidden GitHub endpoint, unapproved trigger, arbitrary live input,
tag/commit/workflow-root mismatch, or any provider/App secret in a PR/fork or wrong-role job.

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

Suspected credential exposure discovered after upload uses only
`PERMANENT_STOP(reason=credential_exposure)`. The discovering phase workflow or designated
`benchmark-evidence` inventory/scanner reconstructs the exact current state/ledger/inventory/plan/
hold roots, verifies the source upload/run/job and scanner receipts, assigns the incident ID, and
builds `CredentialExposureIncidentEvidenceV1` without retaining the suspected bytes. Before the
state CAS, the discovering run fails its ordinary phase action closed and retains the
repository-wide mutation concurrency lease, so no successor phase or live batch can start. The
affected credential is then revoked, rotated, or proven cryptographically expired; every
affected artifact is locally quarantined and placed in the proposed authority denylist, a deletion
request is attempted, and the current deletion result is recorded. The state writer atomically
installs the incident root and
denylist and moves the exact allowed parent to `STOPPED_INVALID` by one expected-OID CAS. Every
entrypoint checks that denylist before artifact download and checks STOP before provider dispatch,
so the CAS authorizes zero later downloads by campaign jobs and zero later provider calls.

If the parent is `COMPLETE_PUBLICATION_PR_OPEN`, the separately approved `benchmark-publish` job
first uses only the publisher App to close that exact PR and includes the close receipt; no other
credential-incident caller can stop from that parent. If deletion is pending or unavailable at the
STOP CAS, the prefix/STOP finalizer cannot emit `INVALID_PREFIX_SEALED` until it binds a terminal
safe containment receipt containing the final deletion result, continued artifact denylist, and
credential-response receipt. No transition out of `STOPPED_INVALID` is added merely to update
containment evidence.

Because retrieval may already have occurred, the event is treated as a disclosure and the campaign
is operationally invalid even if deletion succeeds. Only artifact IDs/digests, safe upload and
scanner metadata, containment/deletion receipts, incident timeline, and the safe invalid-campaign
record are retained; raw affected data is excluded from publication. Discovery at `RESULT_MERGED`
uses `RELEASE_PLAN_INVALIDATED`; discovery at `RELEASED` uses a correction lineage. Release,
correction, invalid-finalization, invalid-publication, and terminal states cannot emit a new
credential-exposure STOP event.

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
- copied native-v2 manifests, tier- and cache-dimensioned dated price snapshot, and per-batch
  reviewer attestations;
- both independent identity registries, all three ordered protocol attestations and their root,
  the 15-member workflow inventory, derived member hashes, and common workflow root;
- exact cases, arm hashes, Caveman provenance, protocol hashes, and runner provenance;
- all terminal and retry attempts, errors, exact applied-cache-control evidence, separate
  cache-read/cache-write usage and accounting, service-tier request/return/accounting evidence,
  returned models, and request metadata allowed by the publication policy;
- generation-context expectation/final roots and the tagged hard-scorer, hard-score, judge,
  statistical, audit, provider-projection, and workflow-root lineage;
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

For `credential_exposure`, the prefix/STOP finalizer additionally requires the canonical incident
root, continued denylist, terminal credential-containment and deletion receipts, and proof that no
affected raw artifact is in the safe publication projection. It publishes no scanner match bytes,
secret material, or affected artifact content.

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

The plan's `bundle_kind` and sealed root are mandatory discriminators in every publisher, PR,
validation, merge, collector, and state event. A complete plan may emit only
`COMPLETE_PUBLICATION_PR_OPENED` and enter `COMPLETE_PUBLICATION_PR_OPEN`; an invalid-prefix plan may
emit only `INVALID_PUBLICATION_PR_OPENED` and enter `INVALID_PUBLICATION_PR_OPEN`. Required CI checks
reconstruct the discriminator and root from the proposed tree rather than trusting PR labels or
event inputs. Human merge of an invalid-prefix PR emits only `INVALID_PREFIX_MERGED`, the terminal
safe registry/incident state. Human merge of a complete PR may emit `RESULT_MERGED` only with the
complete root lineage specified in section 7.4. Neither path can consume the other's event.

A separately approved `benchmark-publish` environment job runs trusted publisher preparation from
the detached input commit with no App credential. It creates a separate worktree rooted at the
exact publication base SHA, verifies the plan, bundle digest, workflow root, and inventory, copies
fixed allowlisted paths byte-for-byte, and verifies the exact expected tree diff and sealed commit
root. Only then does its fixed byte-blind publisher step map the publisher-App credential; that step
accepts only the plan, object roots, ref, and PR metadata and creates only the bound branch and pull
request. For an invalidated publication it may instead close only that exact plan-bound PR and must
record the typed `correction_publication_invalidation` or ordinary publication invalidation receipt
as applicable. It does not parse, score, render, execute, or otherwise interpret untrusted model
output, and it has no provider key or state/release App credential. The read-only repository
`GITHUB_TOKEN` is not a publication authority and cannot approve or merge the PR.

The publication job does not merge directly. Normal CI, branch protection, conversation
resolution, exact-head validation, and human review apply. The publication contract requires a
maintainer with write access to verify the exact PR head SHA and sealed bundle digest and authorize
the secret-free `publication-pr-validate` check required by branch protection. The publisher App
cannot approve or merge its own PR. After human merge, a protected `ResultReleasePlanV1` binds the
campaign, input tag, bundle digest, exact publication PR and approved head, merge commit and
result-tree digest, result tag name, release workflow SHA, common workflow root, and asset digests.
A separately approved `benchmark-publish` release-finalizer job rechecks the plan and prepares the
annotated-tag object and sealed opaque assets before any App credential is mapped. Its fixed
byte-blind finalizer step then maps only the release-finalizer App credential, accepts the bound
tag/release/asset roots, creates the protected annotated `benchmark-result-<campaign-id>` tag at
exactly the merge commit, creates the checksum-bound draft GitHub Release and exact assets, verifies
returned tag/release/asset roots, and performs one publish transition. It never rewrites result
files and records the annotated tag object, release ID, draft and publish receipts, and returned
asset digests. Repository immutable Releases and tag rulesets prohibit rewrite; the read-only
`GITHUB_TOKEN` performs none of these writes.

Actions artifacts are temporary review transport, not the durable public record. The committed
result directory and release assets are the publication surface.

Every started confirmatory input tag gets a registry outcome:

- valid positive, negative, and inconclusive campaigns publish full allowed evidence;
- an operationally invalid campaign publishes the reason and non-sensitive provenance without a
  performance claim; and
- suspected credential exposure follows section 12.2 and publishes only the safe invalid-campaign
  incident record.

Corrections use the durable intent/receipt/adoption/finalization protocol in section 7.5. They create
a new result directory, protected annotated tag, release, and append-only latest-pointer event with
an explicit `supersedes` lineage; existing evidence, states, commits, pointers, tags, and releases
are not rewritten. A `RELEASE_BLOCKED` lineage creates no original result tag or release; its
correction binds and supersedes the blocked merge explicitly. Publication-stage correction failure
records `correction_publication_invalidation`; release-stage correction failure records
`correction_release_invalidation`; no generic correction invalidation is accepted. A successful
correction binds every persisted publication, merge, tag, and release receipt before the final
`CORRECTION_RESULT_RELEASED` CAS.

### 13.3 Documentation and social claims

Only after `CampaignStateV1` reaches `RELEASED` may synchronized result sections be added to the six
localized READMEs, `evals/README.md`, the website, changelog, a new release note, and a dated social
package. `RESULT_MERGED`, `RELEASE_BLOCKED`, and `INVALID_PREFIX_MERGED` explicitly authorize no
documentation, release-note, website, or social promotion. The historical `v0.1.0-alpha.1` release
note and alpha social package remain unchanged.

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
- manifest/request round-trip tests proving literal wire `service_tier: "default"`, exact
  `prompt_cache_options` explicit/`30m`, recursive breakpoint absence, forbidden cache keys,
  returned applied options, canonical read/write paths, all three closed cache-status mappings,
  pinned OpenAI SDK `3.3.1`/lock identity, exact medium reasoning, medium verbosity, and the
  `<= 272_000` versioned input-exposure bound in every request identity and wire payload;
- corpus-neutrality tests proving that only prompt-grounded sentence constraints are gating and
  that critical-warning case IDs are frozen;
- parent/shard-plan tests proving exactly 36 disjoint 40-row generation projections whose ordered
  union is the three 480-row parent plans;
- hard-score/request-set sealing plus judge-schema, prompt-blinding, injection-resistance,
  attachment-binding, zero-call attachment, and exact coverage tests;
- audit sampling, certainty-unit coverage, canonicalization, exact two-entry audit identity
  registry, exact ordered three-entry protocol registry/attestations, closed verification modes,
  role-specific ordered subject inventories and forbidden fields, numeric-ID/login/signature
  binding and non-null security-evidence fingerprint,
  commitment/reveal PR ordering, adjudication, weighting, agreement, model/arm-indexed false-fail
  sensitivity, quality/brevity extrema, exact-search certificates, and deterministic search-cap
  tests, including `M = K = 120` fail-closed exhaustion;
- exact call-count, default-tier price-snapshot attestation, non-null cache-write rates,
  `BatchPlanV1`, single-use job receipt, distinct cache-read/cache-write
  reservation/reconciliation/evidence, duplicate/rerun rejection, STOP propagation, and
  campaign-budget tests, including a definitely-rejected 429-retry-then-success chain whose
  attempts remain separately accounted and every closed service-tier accounting status;
- schema-generated `CampaignStateV1` transition-table/tests, parent-hash, atomic invalid-event hold,
  approved dismissal, complete/invalid publication-state separation, terminal
  `INVALID_PREFIX_MERGED`, cross-kind merge/close rejection,
  post-merge benign-hold dismissal, hold-to-STOP, compare-and-swap race, no-mutation, illegal-jump,
  zero-dispatch recovery, resumable-partial, budget-incomplete, publication-replan,
  release-blocked, correction-intent preauthorization, per-effect receipt CAS, create/adopt retry,
  PR/merge/tag/draft/asset/publish crash-window reconciliation, atomic
  `CORRECTION_RESULT_RELEASED` escape, terminal correction append, distinct phase-bound correction
  invalidations, immutable-orphan evidence, invalid-finalization, and happy-path property tests;
  canonical golden vectors for `GENERATION_SET_SEALED` require the exact ordered 36 capsule hashes,
  `generation_context_expectation_sha256`, and `verified_generation_context_root`, and reject an
  omitted, extra, swapped, malformed, or independently mismatched root while proving the rendered
  transition table is generated from that same required-evidence schema; credential-exposure
  vectors require the exact safe `CredentialExposureIncidentEvidenceV1`, allowed prepublication
  parent, current roots, source upload, scanner and containment receipts, artifact denylist, and
  open-PR close receipt where applicable, and reject every reason alias, secret-bearing field,
  excluded parent, or incomplete receipt;
- closed retry-taxonomy, `Retry-After`, jitter, retry exhaustion, 401/403 stop, ambiguous delivery,
  soft deadline, forced runner loss, and exact-suffix resume tests;
- tar round-trip, hidden-lock, mode, digest, extraction, traversal, link, overwrite, inventory,
  and secret-scan tests, including cross-phase post-upload detection, deletion pending/unavailable,
  terminal containment before prefix finalization, and zero later campaign download/provider-call
  tests;
- exact 15-path C0-derived workflow inventory/root, trigger, read-only `GITHUB_TOKEN`, four-job
  provider boundary, three distinct App actors, endpoint policy, rulesets, immutable Releases,
  human/App authority separation, OIDC state-broker exact identity projection, fully qualified
  caller/callee references, tag/main `ref`/`ref_type`/`sha` and caller/callee SHA semantics,
  `typ`/`alg`/`kid`/issuer/audience/subject/time/single-use-`jti`, absent-environment and exact
  actor/repository/check-run/rerun-initiator restrictions, minimal reusable-job boundary,
  missing/extra/mismatch, unrelated-workflow, and pull-request-ref denial, token expiry, and every
  closed phase-specific `PERMANENT_STOP` caller/parent/reason allow and deny vector, including every
  allowed and forbidden credential-incident caller/state pair, per-batch environment approval,
  campaign concurrency, batch-controller ordering,
  step-scoped-secret, detached-SHA pinning, Markdown neutralization, and exact artifact-provenance
  policy tests;
- read-only provider-evidence verifier, complete-collector ordering, incomplete-prefix finalizer,
  credential-incident schema/canonicalization/quarantine/deletion/revocation/rotation/expiry and
  safe-record publication, `PublicationPlanV1` ancestor/base/head movement and closed-PR replan,
  minimal App publisher, exact-head manual publication-PR validation, `ResultReleasePlanV1`,
  annotated-tag/draft-assets/one-publish release finalizer, and correction-lineage tests;
- authority-bound generation-context expectation reconstruction, no-hash-self-cycle, tagged
  protocol/workflow-root propagation, exact expectation/final-root binding in the schema-canonical
  `GENERATION_SET_SEALED` event and `GENERATION_COMPLETE` record, and rejection of every serialized
  or supplied capability surrogate;
- import- and call-graph tests proving all seven public replay commands are offline and
  non-evidentiary and that every live hard-score, judge, audit, analysis, and verification workflow
  uses the exact Runtime or Publication entrypoint without invoking the public CLI; and
- a full synthetic campaign that reconstructs the report from published-style artifacts without a
  provider secret.

PR and fork CI remains provider-offline and secret-free: it may fetch pinned actions and locked
dependencies, but it has read-only repository permission and cannot make live model calls.

### 14.2 Live pilot

Before preregistering the confirmatory tag, a separately labeled operational pilot runs one shared
scenario in both languages, all four arms, one repetition, and all three generation models. At
most 24 generation and 24 judge attempts are permitted, under the USD 5 cap. The pilot freezes
`max_transient_retries = 0`, so retries cannot raise the actual API-attempt ceiling above 48.

The pilot validates API parameters; literal requested and returned `default` service-tier evidence;
returned explicit/`30m` applied-cache-control evidence; separate zero cache-read/cache-write proof
and STOP behavior; returned-model and usage capture; rate behavior; checkpoint transport; judge
schema; and cost accounting. It is never benchmark evidence. The corpus and decision thresholds
cannot be tuned to make the observed pilot effect favorable. A required protocol fix creates a new
pilot identity; the confirmatory input tag is created only after the implementation is frozen and
reverified.

### 14.3 Confirmatory sequence

This amended design is a governance gate. No implementation slice, pilot, or live workflow rollout
may begin while **Amendment approval** remains pending. A maintainer must review this exact diff and
add a new dated approval record in a later commit; the historical 2026-08-30 approval cannot satisfy
that gate.

After that explicit reapproval and implementation, the release sequence is:

1. full provider-offline synthetic campaign is green;
2. the exact two audit identities and ordered three protocol identities/attestations are frozen,
   and workflow security and statistical review are green against the common workflow root;
3. the live operational pilot is green;
4. code, manifests, methods, settings, seeds, and price snapshot are frozen in the input tag;
5. each required bounded generation batch receives `benchmark-live` approval and runs in order;
6. all generation capsules are sealed, the authority-bound generation-context expectation is
   reconstructed, and `GENERATION_SET_SEALED` atomically binds the exact ordered 36 capsule hashes,
   `generation_context_expectation_sha256`, and `verified_generation_context_root` into
   `GENERATION_COMPLETE`; then the deterministic hard-score/request-set attachments are sealed;
7. each required bounded judge batch receives `benchmark-live` approval and runs in order;
8. generation, hard-score, and judge artifacts pass read-only provider-evidence integrity
   validation and `EvidenceInventoryV1` is sealed;
9. two reviewers complete commit-reveal and adjudication;
10. capsule-bound aggregation classifies every model outcome;
11. the complete read-only collector seals the final bundle from provider evidence, audit, and
    analysis;
12. `benchmark-publish` receives separate approval for the exact `PublicationPlanV1`, maps only the
    publisher App in the fixed step, and opens the result PR from the verified main base;
13. a maintainer approves publication-PR validation for the exact head SHA and the reviewed PR
    merges;
14. `ResultReleasePlanV1` binds the merge commit and asset digests;
15. the separately approved release finalizer maps only the release App, creates the protected
    annotated result tag, draft release, and checksum-bound assets, verifies them, and performs one
    publish transition; and
16. documentation, website, and social result packages are updated from the merged evidence.

From the first provider artifact upload through `COMPLETE_PUBLICATION_PR_OPEN`, every consuming
phase scans its exact inputs and proposed outputs before its success transition; the designated
`benchmark-evidence` scanner may also be dispatched against any exact eligible current-state
inventory. A credential-exposure finding immediately takes the caller/state-specific incident path,
installs the denylist and `STOPPED_INVALID`, completes containment, and then uses only the safe
prefix/incident publication path. It never resumes the numbered success sequence. A finding after
`RESULT_MERGED` or `RELEASED` follows release invalidation or correction instead.

At any authorized prepublication `PERMANENT_STOP`, or any provider-stage `BUDGET_EXHAUSTED`, the
sequence branches immediately to the prefix/STOP finalizer and safe invalid-campaign publication
path defined by `CampaignStateV1`. It does not continue to a later live, audit, aggregate, complete
collection, or complete-publication stage.

## 15. Known limitations

- Twelve independent scenario clusters can produce wide intervals. Inconclusive is an expected and
  acceptable outcome.
- The corpus is a compact response suite, not a universal task distribution.
- OpenAI model IDs and returned snapshot identifiers or service behavior can change. Requested and
  returned identifiers, timestamps, settings, and limitations are disclosed, but a hosted API
  cannot provide perfect future reproducibility.
- Sol judging Sol is not fully independent. The two-person audit measures disagreement but does
  not remove every judge bias.
- A public artifact reveals benchmark responses before final publication to anyone who retrieves
  it; blinding is enforced by the reviewer protocol, not by pretending the repository is private.
- Secret scanning cannot prove that an uploaded artifact contains no credential, and deleting an
  artifact cannot retract prior public downloads. The cross-phase `credential_exposure` path
  revokes or expires the credential, blocks later campaign downloads and calls, and invalidates the
  campaign, but it cannot prove that disclosure did not already occur or that every external copy
  was destroyed.
- A forced runner loss can occur before the post-controller `always()` upload. Per-shard seals limit
  already-uploaded evidence loss, but work produced across multiple shards inside the current batch
  can still be lost; retained reservations and STOP behavior prevent unsafe continuation but cannot
  recover that work.
- GitHub environment approval is job-scoped. A long campaign may require several manual approvals,
  one for each bounded generation or judge batch; there is no campaign-wide approval primitive.
- Publication requires one protected approval to create the exact result PR and another to create
  the post-merge result tag/release; these are separate App-credentialed jobs.
- GitHub App permission grants are broader than the intended state, publisher, and release roles.
  Fixed tools, endpoint tests, rulesets, immutable Releases, receipts, and actor restrictions reduce
  that exposure but do not make it a platform-enforced least-capability boundary.
- The state-writer broker is an additional trusted availability and identity-verification boundary.
  A broker outage stops state progress; a claim mismatch cannot fall back to a stored App key.
- GitHub APIs do not offer one universal idempotency header across refs, PRs, tags, and Releases.
  Exact-name/root adoption closes ordinary crash retries, but a conflicting immutable external
  object terminates that correction lineage and remains disclosed evidence rather than being
  rewritten.
- API price estimates are not invoices. Cache reads, cache writes, and returned service-tier detail
  remain provider evidence: missing detail retains worst-case exposure and can invalidate the run.
  The campaign intentionally authorizes neither long-context pricing nor a service tier other than
  literal `default`.
- The seven public replay commands are useful for offline reproduction but intentionally cannot
  recreate live campaign authority or evidentiary capabilities.
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

- a maintainer has reviewed this exact amendment diff and recorded a fresh explicit approval; the
  historical 2026-08-30 approval is not sufficient;
- every item in the automated verification section is fresh and green;
- all three native-v2 manifests collectively yield exactly 1,440 parent-plan rows, and the 36
  hash-bound shard plans form an exact disjoint 36-by-40 partition;
- Runtime and Publication campaign-side stages bind every live hard-score, judge, audit, analysis,
  verification, and bundle attachment to its exact authority parents through the exact internal
  entrypoints, while all seven public replay commands remain offline and non-evidentiary;
- manifest/request evidence captures literal wire `service_tier: "default"`, returned-tier evidence
  and the exact closed accounting vocabulary; literal `prompt_cache_options` explicit/`30m` with
  forbidden cache keys and no breakpoint; exact returned applied-control/read/write paths and
  separate exhaustive status enums; pinned SDK/lock identity; medium reasoning; medium verbosity;
  and the reasoning-token breakdown required for visible-token scoring;
- every requested model ID has a reviewed non-null cache-write rate, both tier fields equal
  `"default"`, the versioned conservative input bound is at most `272_000`, and neither
  authorization nor reservation can select long-context pricing;
- the corpus-neutrality edit and warning-severity schema are frozen and validated;
- the workflow can reconstruct, verify, and resume an exact tarred checkpoint including
  `.laconian.lock`;
- the `CampaignStateV1` dispatcher rejects every illegal, duplicated, skipped-parent, STOP-to-live,
  and partial-to-complete event without state mutation, atomically blocks on
  `InvalidEventHoldV1` until approved dismissal or the phase-appropriate STOP, release-block, or
  correction path, and permits zero-dispatch recovery only with exact `never_started` reservation
  evidence; every mutation is serialized and compare-and-swapped against the exact state/hold root;
  complete and invalid publication PRs occupy distinct states, only a complete sealed-root lineage
  can reach `RESULT_MERGED`, and `INVALID_PREFIX_MERGED` is terminal and cannot release or promote;
  the sole `RELEASE_BLOCKED` escape is an atomic `CORRECTION_RESULT_RELEASED`, a correction from
  `RELEASED` only appends terminal history, every correction external effect is preauthorized and
  receipt-reconciled/adoptable after crashes, and the two phase-bound correction invalidations
  cannot alias;
- every post-upload `credential_exposure` STOP uses the canonical safe
  `CredentialExposureIncidentEvidenceV1`, reproduces the exact current authority/state/ledger/
  inventory/plan/hold roots and affected upload/run/job, binds the closed secret classification,
  scanner verification, credential containment, quarantine/deletion and no-further-campaign-
  download receipts, closes an open complete PR with the publisher App before STOP, and is accepted
  only from the exact prepublication parents and frozen callers; release, correction,
  invalid-finalization, invalid-publication, and terminal states cannot use that reason;
- the exact two-entry audit registry and exact three-entry ordered protocol registry bind numeric
  IDs, logins, closed verification modes and fingerprints, the security-evidence fingerprint is
  non-null, every role has exactly its ordered required subject inventory and no forbidden field,
  the three ordered attestations/root verify, and neither registry can substitute for the other;
- the exact ordered 15-path workflow inventory derives its member hashes and common root only from
  verified C0 bytes, and protocol attestations, generation context, provider projection, and
  publication all verify that same root;
- the authority-bound generation-context expectation is reconstructed only in campaign memory,
  binds campaign/registries/predecessor/generation layer and expected context digest without a hash
  self-cycle, the schema-canonical `GENERATION_SET_SEALED` evidence and resulting
  `GENERATION_COMPLETE` both require `generation_context_expectation_sha256` and
  `verified_generation_context_root` alongside the ordered 36 capsule hashes, and that lineage
  carries the tagged hard-scorer plus hard-score, judge, statistics, audit protocols and workflow
  root through final provider and publication evidence;
- the repository `GITHUB_TOKEN` is read-only everywhere; the four-job provider boundary is exact;
  the state-writer, publisher, and release-finalizer Apps are pairwise distinct and repository
  scoped; the state token broker admits only the exact repository/actor identity, fully qualified
  caller and reusable-workflow paths at the exact tag or main ref, real
  `workflow_sha`/`job_workflow_sha` caller/callee semantics, event/check-run/OID tuple, minimal
  reusable job, frozen crypto/audience/subject/time/single-use-token policy, REST-verified rerun
  initiator, phase-specific caller/parent/reason STOP authority, and the exact cross-phase
  credential-incident matrix, and denies every unrelated workflow, ref, identity,
  missing/extra/mismatched claim, predecessor, reason alias, artifact, or event; App/provider
  credentials are mapped only in their fixed, separately authorized boundaries with no
  provider-key/model-output overlap;
- protocol/audit reviewer commits and PRs, maintainer validations/approvals, and protected human
  merges remain distinct human authorities and cannot be replaced by any automated App or workflow;
- the batch controller and every later artifact-consuming phase prove predecessor-ledger,
  single-use job receipt where applicable, per-attempt reservation, permanent STOP, soft-deadline,
  exact-suffix resume, and zero-subsequent-download/call behavior for authentication, permission,
  ambiguity, credential exposure, and missing state;
- preflight and the durable ledger enforce the USD 75 authorized-exposure scheduling bound from
  the frozen default-tier, cache-dimensioned price snapshot and reviewer attestation, account
  nonzero writes before STOP, retain worst-case exposure for missing write/tier detail, and stop
  before a batch that cannot fit;
- the operational pilot completes within its USD 5 bound with consistent returned models and
  complete usage;
- judge, statistics, audit, and security protocols are frozen, attested, and hash-bound; every
  critical judge-pass primary record is audited; and the two audit-reviewer identity-bound
  commitment/reveal chains verify;
- model/arm-indexed false-fail sensitivity recomputes semantic quality and brevity, verifies exact
  extrema certificates, and becomes inconclusive on deterministic search-cap exhaustion;
- the read-only collector rejects an incomplete performance bundle, the prefix/STOP finalizer emits
  only safe invalid-campaign provenance, and the minimal publisher copies only an exact sealed
  allowlist;
- `PublicationPlanV1` starts from exact current `main` containing every bound audit merge, the
  publisher App creates or closes only its exact plan-bound branch/PR, `ResultReleasePlanV1` binds
  the reviewed merge tree, and the release App creates only the protected annotated tag, verified
  draft/assets, and one publish transition; base/head movement has an exact closed-PR replan
  transition, and a verified post-merge defect blocks release;
- documentation, website, release-note, and social updates are impossible before `RELEASED` and
  remain forbidden for `RESULT_MERGED`, `RELEASE_BLOCKED`, or `INVALID_PREFIX_MERGED`;
- endpoint-policy tests, actor restrictions, expected-OID receipts, protected rulesets, and
  immutable Releases constrain the technically broader App permissions, and no workflow token can
  approve or merge a PR;
- protected input/result tags, all three App installations, the state-broker OIDC/claim policy,
  actor restrictions, immutable Releases, and both GitHub environments are configured; and
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
- [GitHub OpenID Connect token claims](https://docs.github.com/en/actions/reference/security/oidc#oidc-token-claims)
- [GitHub OIDC with reusable workflows](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows#how-the-token-works-with-reusable-workflows)
- [GitHub calling reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows#calling-a-reusable-workflow)
- [OpenAI project and restricted-key controls](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform)
- [OpenAI Responses create API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [OpenAI prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- [OpenAI GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [OpenAI GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [OpenAI GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
