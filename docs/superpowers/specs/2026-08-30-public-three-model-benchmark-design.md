# Public Three-Model Benchmark Pipeline Design

**Date:** 2026-08-30

**Status:** Constructive-liveness, credential-finality, and exact-wire amendment approved;
implementation may proceed only after the implementation plans are synchronized to this approved
normative commit

**Historical maintainer approval:** 2026-08-30 (approval of the pre-amendment design)

**Prior amendment approval:** On 2026-08-30, the maintainer/user in this Codex task explicitly approved
the normative design at commit `46147ef62b5bb009421d58928e879d92247d84b5` with the exact message
`Одобряю amendment 46147ef`. That approval remains historical evidence for the prior normative
design; it did not approve the later attestation-transport amendment whose separate approval is
recorded below.

**Current amendment approval:** On 2026-08-31, the maintainer/user in this Codex task explicitly
approved the normative design at commit `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126` with the exact
message `Одобряю amendment 05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`. This governance-only
successor records that approval without changing normative behavior. Approval of
`55b90582ae461cf7a3dc072d53d8b03e79fb3614` remains historical evidence for the prior approved
design. Implementation may proceed only after the implementation plans are synchronized to the
newly approved normative commit.

**Approved amendment scope:** This revision closes constructive-liveness, credential-finality, and
exact-wire gaps without changing the benchmark estimand, workload, model set, statistical gates,
public replay surface, workflow inventory, or three-App inventory. It (1) gives every in-flight
publication PR one phase-aware terminal disposition, including every merge-before-close race, (2)
defines exact branch/PR/check/release transport reconciliation and complete terminal check-suite
enumeration, (3) closes every publisher, security-attestor, and release-finalizer token lineage on
both success and failure, (4) separates receipt-free release preauthorization from attestation,
executable intent, effect delivery, and final reconciliation, and (5) admits the two initial-
publication and four initial-release receipt appends through two closed, state-byte-identical
authority mutation families rather than undefined generic write channels. Fixed jobs acquire more
precise caller/endpoint policies, but no workflow file or App role is added.

**Scope:** Publication-grade response benchmark for GPT-5.6 Sol, Terra, and Luna, executed through
GitHub Actions with immutable generation, judging, human-audit, and publication evidence

## 1. Decision

Laconian will run one preregistered response benchmark campaign against three OpenAI models:
`gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`. Each model is an independent experiment. The
project will not pool the three models into a universal family claim.

The selected architecture is a staged capsule pipeline:

```text
protected annotated input tag and serial signed protocol-review chain
  -> protected annotated attestation-bundle companion tag
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
signing-verification mode, signing fingerprint, and canonical ASCII Git author/committer name and
email used by its reviewer commit. The `security_evidence` fingerprint is
non-null regardless of the other roles' allowed modes. The protocol registry has canonical bytes
and a digest distinct from the audit registry.

The verified C0 tree also contains
`benchmark/security/tag-operator-registry.json`, exact `TagOperatorRegistryV1`. It has exactly
`schema_version`, positive numeric `repository_id`, `operators`, and
`tag_operator_registry_sha256`. `operators` contains exactly one `TagOperatorProjectionV1` with
exactly positive numeric `operator_account_id`, case-sensitive `operator_login`, ASCII
`tagger_name`, ASCII `tagger_email`, and `tag_operator_sha256`. `tag_operator_sha256` is SHA-256 of
`UTF8("laconian-tag-operator-v1\n") || CanonicalJSONV1(entry without exactly
tag_operator_sha256)`. `tag_operator_registry_sha256` is SHA-256 of
`UTF8("laconian-tag-operator-registry-v1\n") || CanonicalJSONV1(registry without exactly
tag_operator_registry_sha256)`; the stored entry digest remains inside that registry preimage.
No root is included in its own preimage. Null,
duplicate, role/team/App/deploy-key identity, control character, non-ASCII tagger identity, or a
second operator is forbidden. The C0 input registry, T0/T1 messages,
`ProtocolAttestationTagBindingV1`, and `CampaignRegistryV1` bind this same registry digest.

The verified C0 tree additionally contains `benchmark/security/tag-ruleset-policy.json`, exact
stable `TagRulesetPolicyV1` from section 6.5.3. Its digest is the ordered
`tag_ruleset_policy_root`. These C0 members and digests are required by the input registry and,
together with the token-delivery-isolation policy, broker-key root and dismissal policy below, are
the final five ordered `security_evidence` statement subjects:
`broker_token_delivery_isolation_policy_sha256`, `broker_signing_keys_root_sha256`,
`tag_operator_registry_sha256`, `tag_ruleset_policy_root`, then
`invalid_event_dismissal_policy_sha256`.

C0 also freezes `benchmark/security/invalid-event-dismissal-policy.json`, exact
`InvalidEventDismissalPolicyV1`, with exactly `schema_version`, `repository_id`,
`eligible_dismissers`, and `invalid_event_dismissal_policy_sha256`. `eligible_dismissers` is a
nonempty ascending numeric-account-ID array of strict `{account_id, login}` projections; no role,
team, App, deploy key, repository-role, or ambient maintainer expansion is allowed. Its digest is
SHA-256 of `UTF8("laconian-invalid-event-dismissal-policy-v1\n") || CanonicalJSONV1(policy without
exactly invalid_event_dismissal_policy_sha256)`. The C0 input registry, security statement,
campaign payload, and `CampaignRegistryV1` bind this digest.

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

### 6.5.1 Non-self-referential protocol-review topology

The protocol review uses two protected, annotated-only tags and this serial construction order:

```text
T0 -> C0 -> Rstat -> Rjudge -> Rsecurity -> B0 <- T1
```

Here `T0` is `refs/tags/benchmark-input-YYYYMMDD.N`, an annotated tag whose target peels exactly to
the input commit `C0`. `T1` is the deterministically paired
`refs/tags/benchmark-attestations-YYYYMMDD.N`, an annotated tag whose target peels exactly to the
bundle commit `B0`. A lightweight tag, tag-of-tag target, different suffix, alternate ref namespace,
or ambiguous peel is invalid. Both ref patterns are protected against update and deletion by
rulesets, but authority is conferred only by the verified object identities and raw-object hashes,
never by a mutable ref name or by the ruleset alone.

For the input-tag basename `<T0>`, the exact campaign review paths are:

```text
benchmarks/protocol-reviews/<T0>/statements/01-statistical-method.json
benchmarks/protocol-reviews/<T0>/statements/02-blind-judge-audit-protocol.json
benchmarks/protocol-reviews/<T0>/statements/03-security-evidence.json
benchmarks/protocol-reviews/<T0>/attestations/01-statistical-method.json
benchmarks/protocol-reviews/<T0>/attestations/02-blind-judge-audit-protocol.json
benchmarks/protocol-reviews/<T0>/attestations/03-security-evidence.json
benchmarks/protocol-reviews/<T0>/bundle.json
```

The entire `benchmarks/protocol-reviews/<T0>/` path is absent from `C0`. In particular, `C0` and
`T0` contain no protocol-review statement, verified attestation envelope,
`protocol_attestations_root`, companion-tag binding, or claim about a future reviewer, bundle, or
companion-tag object. `CampaignInputPackageV1`, which is derived only from verified `C0` inputs,
likewise forbids those values. It does contain the ordered exact three cycle-free
`BrokerSigningKeyV1` public-key records and their recomputed `broker_signing_keys_root_sha256`; C0
therefore fixes the receipt signers before any preflight-produced registry or receipt exists. It
also contains the exact `BrokerTokenDeliveryIsolationPolicyV1`, including all three reviewed vault
measurements. This absence and the policy/key-root presence are explicit preflight checks.

`Rstat` has exactly one parent, `C0`, and its tree delta adds only the first statement path as a
regular non-executable blob. `Rjudge` has exactly one parent, `Rstat`, and adds only the second
statement path. `Rsecurity` has exactly one parent, `Rjudge`, and adds only the third statement
path. Each is authored and commit-signed by the registry identity for its role. It retains every
parent tree entry byte-for-byte; a modification, deletion, rename, mode change, second path, second
parent, merge header, or reordered reviewer is invalid. The serial order is normative even if the
reviews were prepared concurrently.

After all three reviewer commits exist and their signatures have been independently verified, a
secret-free verifier creates `B0` with exactly one parent, `Rsecurity`. Its tree retains the parent
unchanged and adds only the three exact attestation-envelope paths and `bundle.json`, all as regular
non-executable blobs. `B0` contains no reference to its own OID or raw-object hash and no reference
to `T1`. Only after `B0` exists may the operator create `T1`. Changing any `C0`, reviewer, statement,
envelope, bundle, tag message, tagger field, or tag object requires a new T0/T1 pair and new
reviewer commits; repair in place is forbidden.

For every Git object in this protocol, `GitObjectSHA256V1` is SHA-256 over the exact bytes:

```text
"<type> <decimal-content-length>\0" || object-content
```

`<type>` is the literal Git object type, the decimal length has no sign or leading zero, and
`object-content` is the exact unmodified content. This raw-object SHA-256 is distinct from the
repository's 40-lowercase-hex SHA-1 object ID. Both values are required wherever an object is
bound. Re-encoding JSON, stripping a signature header, changing a tag message, or hashing only
object content cannot reproduce this digest.

The frozen operator registry supplies one exact `TagOperatorProjectionV1` with positive numeric
GitHub account ID, case-sensitive login, canonical ASCII tagger name/email, and its digest. The
same registered operator creates T0 and T1. The operator may also be one or more of the three
registered reviewers only when that overlap is explicit in the frozen registries; the tag-creation
act never substitutes for any required reviewer statement or commit signature. Creation is possible
only through the exact operator's authorized `User` bypass of the creation-authorizer ruleset; its
historical rule-suite result is therefore exactly `bypass`, not `pass`. A namespace squat,
pre-existing unbound ref, missing or differently authorized creation bypass, wrong/extra/exempt actor,
update/delete bypass, or different operator for T0 and T1 invalidates the pair.

The operator registry and raw tag-object parser share one lexical grammar. Serialized `tagger_name`
is 1–80 bytes total and consists of one or more nonempty non-space ASCII tokens from `0x21..0x7e`
excluding `<` and `>`, joined by exactly one
`0x20`; leading/trailing/repeated whitespace and every tab/control/non-ASCII byte are forbidden.
`tagger_email` is 3–254 printable non-space ASCII bytes, contains exactly one `@`, has nonempty
local/domain sides, neither side starts or ends with `.`, neither contains `..`, and `<`, `>`,
controls, whitespace are forbidden. The epoch is ASCII `0` or `[1-9][0-9]*`, integer range
`0..253402300799`, with no sign or leading zero; timezone is literally
`+0000`. Registry bytes that do not satisfy this grammar are invalid, and T0/T1 reproduce the same
name/email bytes exactly.

Raw Git object grammar is closed. T0 and T1 are unsigned annotated tags whose content contains, in
order, exactly `object <40-lowercase-hex-oid>`, `type commit`, `tag <exact-basename>`, and
`tagger <frozen-name> <frozen-email> <whole-second-epoch> +0000`, followed by one blank line, exact
strict CanonicalJSON message bytes, and one LF. T0 uses `InputTagMessageV1` with exactly
`schema_version`, `input_tag_ref`, `companion_tag_ref`, `peeled_c0_oid`,
`protocol_reviewer_registry_sha256`, `tag_operator_registry_sha256`,
`tag_ruleset_policy_root`, and `workflow_root`; it may name the deterministic future T1
ref but contains no future commit, object, envelope, bundle, root, or receipt. T1 uses
`ProtocolAttestationTagMessageV1` with exactly `schema_version`, `input_tag_ref`, `input_tag_oid`,
`input_tag_object_sha256`, `companion_tag_ref`, `bundle_commit_oid`,
`bundle_commit_object_sha256`, `protocol_attestation_bundle_sha256`,
`protocol_attestations_root`, `tag_operator_registry_sha256`, and `tag_ruleset_policy_root`; it
binds T0 and B0 but contains no T1 OID, T1 raw-object digest, or
self-digest. An embedded tag signature or any fifth header is forbidden.

Each R* commit contains, in order, exactly `tree`, one `parent`, frozen reviewer `author` and
`committer` headers with identical whole-second epoch and `+0000`, and one mode-compatible `gpgsig`
header with Git continuation lines, followed by one blank line and the exact ASCII message
`laconian protocol review <T0> <role>: <statement_sha256>` plus one LF. Each protocol-registry entry
therefore also freezes its canonical ASCII author/committer name and email. B0 contains exactly
`tree`, one `parent`, frozen `ProtocolBundleBuilderGitIdentityV1` author and committer with identical
whole-second epoch and `+0000`, one blank line, and
`laconian protocol attestation bundle <T0>: <protocol_attestation_bundle_sha256>` plus one LF; it
has no signature header. The builder identity has exactly `schema_version`, literal
`name_ascii="Laconian Protocol Bundle Builder"`, literal
`email_ascii="laconian-protocol-bundle-builder@users.noreply.github.com"`, and
`protocol_bundle_builder_git_identity_sha256`. That digest is SHA-256 of
`UTF8("laconian-protocol-bundle-builder-git-identity-v1\n") || CanonicalJSONV1(identity without
exactly protocol_bundle_builder_git_identity_sha256)`. Every identity comes from verified C0 data. `encoding`, `mergetag`, a
second/unknown/duplicate header, multiple signatures, tag signatures, CR, NUL, non-NFC or ambiguous
Unicode, alternate timezone, extra blank line, alternate message, and any system/global/local Git
configuration or author/committer environment influence are rejected. Golden vectors fix the
complete raw bytes, SHA-1 OID, and `GitObjectSHA256V1` of both tags, all three reviewer commits, and
B0; negative vectors cover every forbidden header, identity, timestamp, message, signature, config,
namespace, creator, and bypass variant.

### 6.5.2 Statements, verified envelopes, and bundle

Every object described here uses strict `CanonicalJSONV1`: UTF-8, NFC strings, bytewise-sorted
object keys, schema-order arrays, JSON integers only, no booleans or strings where integers are
required, no floats, no duplicate keys, no insignificant whitespace, and no terminal newline.
Missing, extra, coercible, non-NFC, incorrectly ordered, or digest-mismatched data is invalid.

`ProtocolReviewStatementV1` has exactly these top-level fields:

```text
schema_version
role
protocol_registry_sha256
reviewer_numeric_account_id
reviewer_login
verification_mode
signing_fingerprint
input_tag_ref
input_tag_oid
input_tag_object_sha256
peeled_c0_oid
peeled_c0_sha256
workflow_root
subjects
subject_root
signed_at
statement_sha256
```

`schema_version` is exactly `ProtocolReviewStatementV1`; the role and reviewer fields byte-match
the corresponding ordered protocol-registry entry. `input_tag_ref` is the full T0 ref;
`input_tag_oid` and `peeled_c0_oid` are exact 40-lowercase-hex SHA-1 OIDs; the two SHA-256 fields use
`GitObjectSHA256V1`. `signed_at` is whole-second UTC RFC 3339. `statement_sha256` is the
domain-separated SHA-256 with separator `laconian-protocol-review-statement-v1` over the canonical
object with only `statement_sha256` omitted. The statement contains every substantive reviewer
claim, including the complete T0/C0, registry, workflow, subject, identity, mode, and time binding.
It contains no reviewer-commit OID, signature evidence, attestation-envelope digest, bundle value,
T1 value, or placeholder for a value that becomes known only after the commit is created.

The exact role-to-subject inventories are:

| Role | Ordered `subjects` kinds |
|---|---|
| `statistical_method` | `corpus_case_root`, `estimand_protocol_sha256`, `statistical_protocol_sha256`, `bootstrap_protocol_sha256`, `outcome_classification_protocol_sha256`, `false_fail_sensitivity_protocol_sha256` |
| `blind_judge_audit_protocol` | `hard_score_protocol_sha256`, `judge_prompt_sha256`, `judge_schema_sha256`, `audit_sampling_protocol_sha256`, `audit_commit_reveal_protocol_sha256`, `audit_adjudication_protocol_sha256` |
| `security_evidence` | `provider_request_contract_sha256`, `retry_spend_protocol_sha256`, `campaign_state_schema_sha256`, `workflow_endpoint_policy_sha256`, `artifact_security_protocol_sha256`, `publication_correction_protocol_sha256`, `publication_branch_ruleset_policy_sha256`, `identity_registry_bundle_sha256`, `state_writer_git_identity_sha256`, `broker_token_delivery_isolation_policy_sha256`, `broker_signing_keys_root_sha256`, `tag_operator_registry_sha256`, `tag_ruleset_policy_root`, `invalid_event_dismissal_policy_sha256` |

Each subject is exactly `{kind, sha256}`. A role's statement must contain every listed subject once
in that order and may contain no subject assigned to another role, no unlisted subject, and no
duplicate. Common fields such as registry, C0, and workflow roots remain top-level and are forbidden
inside `subjects`. `subject_root` is exactly
`SHA256(UTF8("laconian-protocol-review-subjects-root-v1\n") || CanonicalJSONV1(the exact ordered
subjects array))`; no statement field or implicit metadata enters that preimage.

`VerifiedProtocolAttestationV1` has exactly `schema_version`, `statement`, `signature_evidence`,
and `attestation_sha256`. `statement` is the complete canonical `ProtocolReviewStatementV1`,
byte-identical to the blob at that role's fixed statement path. `attestation_sha256` uses separator
`laconian-verified-protocol-attestation-v1` over the canonical envelope with only that field omitted.
An envelope is created after its reviewer commit; it is verifier evidence, not reviewer-authored
content, and cannot alter or supplement a substantive statement.

`signature_evidence` is a closed mode-discriminated union. Every variant contains exactly
`schema_version`, `verification_mode`, `commit_oid`, `commit_object_sha256`, `parent_commit_oid`,
`statement_path`, `github_rest_verification`, and `github_graphql_signature`. The schema version is
`GitHubVerifiedCommitEvidenceV1`, `SSHVerifiedCommitEvidenceV1`, or
`OpenPGPVerifiedCommitEvidenceV1` according to the statement's mode. The commit and parent OIDs,
raw-object SHA-256, path, reviewer identity, and mode must reconstruct from the reviewed Git object
and registry rather than from the envelope. The two keyed variants additionally contain exactly
`fingerprint`, `keyring_sha256`, and `local_signature_verification`; those fields are forbidden in
the GitHub-only variant.

`github_rest_verification` is stable allowlisted `GitHubCommitVerificationProjectionV1` and
contains exactly `schema_version`, positive numeric `repository_id`, `commit_oid`, literal
`api_version`, literal `endpoint`, `verified: true`, `reason: "valid"`, `payload`, `signature`,
`verified_at`, and `rest_projection_sha256`. The API version and endpoint are fixed protocol
constants: `X-GitHub-Api-Version: 2022-11-28` and
`GET /repos/{owner}/{repo}/git/commits/{commit_oid}` with no alternate endpoint. The digest uses
separator `laconian-github-commit-verification-projection-v1` over the
canonical projection with only its digest omitted. `payload` byte-equals the signed commit payload
reconstructed from the raw commit object and `signature` byte-equals its embedded signature.

`github_graphql_signature` is stable allowlisted `GitHubSignatureProjectionV1` and contains exactly
`schema_version`, the same numeric `repository_id`, `commit_oid`, fixed `query_sha256`, positive
numeric `signer_database_id`, `signer_login`, `is_valid: true`, `state: "VALID"`, and
`graphql_projection_sha256`. Its digest uses separator
`laconian-github-signature-projection-v1` with only its digest omitted. The signer database ID/login
are exact projections of GraphQL `signer.databaseId`/`signer.login` and byte-match the registry;
the boolean/enum values are exact projections of `isValid`/`state`. Online freeze and preflight obtain both projections over
authenticated TLS from GitHub for the exact repository/commit and compare them to the independently
fetched raw commit. A null signer, mismatched repository/commit/projection, missing or extra field,
or GitHub status accepted without the raw object is invalid.

This composite trust model intentionally omits GraphQL `payload`, `signature`, `verifiedAt`,
`type`, `email`, and `wasSignedByGitHub` from the stable projection: REST plus the raw object binds
payload, signature, and verification time, while GraphQL binds only signer identity and
validity/state. If the fixed query selects an omitted field, it may appear only in the volatile raw
response carried by `GitHubSignatureObservationReceiptV1`; it is non-authoritative and cannot
change the stable projection or any campaign identity.

Variable transport evidence is forbidden from envelopes, B0, `ProtocolAttestationTagBindingV1`,
`CampaignRegistryV1`, campaign ID, seeds, and plans. Instead each online observation writes a
separate `GitHubSignatureObservationReceiptV1` containing exactly `schema_version`,
`repository_id`, `commit_oid`, `rest_projection_sha256`, `graphql_projection_sha256`,
`observed_at`, `request_ids`, `etags`, `raw_response_sha256s`, `canonical_response_sha256s`,
`tls_endpoint_identity`, and `github_signature_observation_receipt_sha256`. These receipts are
preflight/stage evidence only. Fresh observations may have different transport metadata but must
reconstruct byte-identical stable projections. Offline replay verifies the frozen projection/raw
Git-object relation and keyed signatures, but cannot independently authenticate GitHub as the
origin of a `github_verified_commit` projection.
The receipt digest is SHA-256 of
`UTF8("laconian-github-signature-observation-receipt-v1\n") || CanonicalJSONV1(receipt without
exactly github_signature_observation_receipt_sha256)`.

For `ssh_sha256` and `openpgp_fingerprint`, `fingerprint` byte-matches the registry and statement,
and `keyring_sha256` identifies the frozen public-key material included in the
`identity_registry_bundle_sha256` subject. `local_signature_verification` contains exactly
`verified: true`, `signed_payload_sha256`, `signature_sha256`, `verifier_tool_sha256`, and
`verification_receipt_sha256`. An isolated verifier reconstructs the signed payload from the raw
commit, verifies the embedded signature against only that frozen keyring, and requires the verified
primary-key fingerprint to match. REST and GraphQL verification remain mandatory; local
verification is additional and cannot be replaced by GitHub's status. Key material, access tokens,
or a self-asserted verification result are forbidden in the envelope.
`verification_receipt_sha256` is exactly
`SHA256(UTF8("laconian-local-signature-verification-receipt-v1\n") || CanonicalJSONV1(the exact
five-field local_signature_verification record without exactly verification_receipt_sha256))`.

`ProtocolAttestationBundleV1` at `bundle.json` contains exactly `schema_version`,
`protocol_registry_sha256`, `input_tag_ref`, `input_tag_oid`, `input_tag_object_sha256`,
`peeled_c0_oid`, `peeled_c0_sha256`, `workflow_root`, `attestations`,
`protocol_attestations_root`, and `protocol_attestation_bundle_sha256`. `attestations` embeds the
three complete verified envelopes in registry role order and each is byte-identical to its separate
attestation blob. `protocol_attestations_root` uses separator
`laconian-verified-protocol-attestations-root-v1` over that canonical ordered array. The bundle digest uses
separator `laconian-protocol-attestation-bundle-v1` over the canonical bundle with only its final
digest omitted. No B0 or T1 identity appears in the bundle.

### 6.5.3 Post-tag binding and campaign identity

After T1 exists, preflight constructs `ProtocolAttestationTagBindingV1`. It has exactly these
top-level fields:

```text
schema_version
input_tag_ref
input_tag_oid
input_tag_object_sha256
peeled_c0_oid
peeled_c0_sha256
reviewer_commits
bundle_commit_oid
bundle_commit_object_sha256
companion_tag_ref
companion_tag_oid
companion_tag_object_sha256
protocol_registry_sha256
workflow_root
protocol_attestations_root
protocol_attestation_bundle_sha256
object_closure_root
tag_operator_registry_sha256
tag_ruleset_policy_root
protocol_attestation_tag_binding_sha256
```

`reviewer_commits` is the exact three-entry registry-role-ordered array of `{role, commit_oid,
commit_object_sha256}`. `object_closure_root` is the domain-separated digest of the canonical
OID/type/size/raw-object-SHA-256 inventory for T0, C0, all tree and blob objects needed to reconstruct
C0 and the four exact deltas, Rstat, Rjudge, Rsecurity, B0, and T1. C0 parent OIDs are recorded as
boundary links but pre-C0 ancestry is outside this campaign closure.

`TagRulesetPolicyV1` has exactly `schema_version`, positive numeric `repository_id`, `rulesets`, and
`tag_ruleset_policy_root`. `rulesets` has exactly two projections in stable semantic order,
independent of API response order. Each projection has exactly `semantic_role`, distinct positive
`ruleset_id`, `source_type: "Repository"`, `source_id` equal to `repository_id`, `target: "tag"`,
`enforcement: "active"`, `include_patterns`, `exclude_patterns`, `rules`, and `bypass_actors`.
Both use the identical ordered includes `refs/tags/benchmark-input-*` then
`refs/tags/benchmark-attestations-*` and exact empty excludes.

The first projection has `semantic_role: "creation_authorizer"`, only rule
`{type: "creation", parameters: null}`, and exactly one bypass actor
`{actor_id: <frozen-operator-id>, actor_type: "User", bypass_mode: "always"}`. The second has
`semantic_role: "immutability"`, rules exactly `{type: "update", parameters: null}` then
`{type: "deletion", parameters: null}`, and `bypass_actors: []`. The two distinct IDs and their
union are the complete applicable active inventory for both patterns. Any extra applicable,
`evaluate`, or disabled ruleset; overlap; extra/missing/reordered rule; changed include/exclude;
role, team, App, deploy-key, repository-role, organization-admin, or other exempt/bypass actor; or
unknown field is invalid. `tag_ruleset_policy_root` is SHA-256 of
`UTF8("laconian-tag-ruleset-policy-v2\n") || CanonicalJSONV1(policy without exactly
tag_ruleset_policy_root)`. Ruleset projections have no stored entry digest; their identity is their
exact canonical value inside that root. It excludes request IDs,
timestamps, ETags, response/list ordering, headers, pagination, and all transport metadata. The tag
binding digest uses `laconian-protocol-attestation-tag-binding-v1` with only its final digest
omitted.

Current policy reads emit separate `TagRulesetObservationReceiptV1` records containing exactly
`schema_version`, `repository_id`, ordered `ruleset_ids`, `tag_ruleset_policy_root`, `observed_at`,
`request_ids`, `etags`, `raw_response_sha256s`, `canonical_response_sha256s`, `pagination_root`, and
`tag_ruleset_observation_receipt_sha256`. The digest is SHA-256 of
`UTF8("laconian-tag-ruleset-observation-receipt-v1\n") || CanonicalJSONV1(receipt without exactly
tag_ruleset_observation_receipt_sha256)`. They contain no creation actor or historical rule-suite
claim. Each fresh read must prove that exactly the two applicable active rulesets project to the
sealed root.

Each tag creation instead requires a unique historical `TagCreationRuleSuiteReceiptV1` with exactly
`schema_version`, `repository_id`, positive unique `rule_suite_id`, `operation: "create"`, exact
`ref`, Git all-zero SHA-1 `before_sha`, exact annotated-tag-object OID `after_sha`,
`actor_account_id`, `actor_login`, `pushed_at`, `overall_result: "bypass"`, `evaluation_result: "fail"`,
`rule_evaluations`, `creation_authorizer_ruleset_id`, `creation_bypass_grant`,
`tag_ruleset_policy_root`, `request_ids`, `api_version`, `raw_response_sha256`,
`canonical_response_sha256`, `observed_at`, and `tag_creation_rule_suite_receipt_sha256`.
`rule_evaluations` contains exactly one stable element with exactly `rule_source_type: "ruleset"`,
`rule_source_id`, `enforcement: "active"`, `result: "fail"`, and `rule_type: "creation"`.
GitHub raw `rule_source.name` and optional evaluation details remain only in the safe raw response
blob; they are excluded from this stable projection, and an unknown stable field is rejected.
Elements would sort by `(rule_source_type,rule_source_id,rule_type)`, but cardinality is exactly one;
its source ID equals the sealed creation-authorizer ruleset. `creation_bypass_grant` is derived, not
reported per rule, and has exactly `actor_id`, `actor_login`, `source_ruleset_id`, and
`tag_ruleset_policy_root`; it is valid only because top-level actor ID/login and `overall_result=bypass`
match the one `TagOperatorRegistryV1` entry and its sealed `User/always` bypass in
`TagRulesetPolicyV1`. No claim is made that GitHub returns actor type or bypass mode per rule.
The receipt digest is SHA-256 of
`UTF8("laconian-tag-creation-rule-suite-receipt-v1\n") || CanonicalJSONV1(receipt without exactly
tag_creation_rule_suite_receipt_sha256)`. The creation rule's evaluation and grant identify only the frozen operator's exact `User/always`
bypass. Preflight requires one and only one authenticated historical suite for T0 and one different
suite for T1. A reused old suite, delete/recreate, nonzero `before_sha`, different `after_sha`,
wrong/extra/exempt actor, missing/ambiguous/multiple suite, unauthorized creation result, or any
update/deletion bypass is invalid.

Raw-to-canonical mapping is exact: suite `result` maps to `overall_result`, suite
`evaluation_result` maps unchanged, suite `actor_id`/`actor_name` map to
`actor_account_id`/`actor_login`, and each raw evaluation maps only
`rule_source.type`, `rule_source.id`, `enforcement`, `result`, and `rule_type` to the stable element.
Top-level literals must be `bypass` and `fail`; the sole evaluation literals are `ruleset`, the
sealed ID, `active`, `fail`, and `creation`. Missing, duplicate, differently ordered, extra stable,
or contradicting values fail closed.
Receipt `operation: "create"` is a verifier-derived discriminator from the exact new ref, all-zero
`before_sha`, and nonzero annotated-tag-object `after_sha`; it is not claimed to be a GitHub API
response field.

Both receipt types are preflight/stage/archive evidence and are excluded from tag binding,
`CampaignRegistryV1`, campaign ID, seeds, and plans. Rechecking unchanged objects and semantic
policy therefore derives identical identity regardless of observation metadata.

The durable archive is `ProtocolReviewObjectArchiveV1`, containing exactly `schema_version`,
`object_closure_root`, `objects`, `api_blobs`, `api_receipts`, and
`protocol_review_object_archive_sha256`. `objects` uses the same canonical object order with each
entry exactly `{oid, type, size, git_object_sha256, raw_content_base64}`. It
stores exact raw content bytes for every object in the closure, not merely an inventory. A
network-free importer decodes every entry, reconstructs `type SP decimal-size NUL content`, verifies
both hashes, reconstructs all trees/commits/tags and exact deltas, and rejects a missing, extra,
duplicate, reordered, or byte-mismatched object before replay.

`object_closure_root` is SHA-256 of `UTF8("laconian-protocol-review-object-closure-v1\n") ||
CanonicalJSONV1(the ordered entries projected to exactly oid,type,size,git_object_sha256)`; entries
have no stored self digest. `protocol_review_object_archive_sha256` is SHA-256 of
`UTF8("laconian-protocol-review-object-archive-v1\n") || CanonicalJSONV1(the complete archive
without exactly protocol_review_object_archive_sha256)`. The already-computed closure root is an
ordinary field in the outer preimage, so neither digest is circular.

`api_blobs` is ordered lexicographically by `path`; each entry has exactly `path`, `kind`,
`sha256`, and `raw_bytes_base64`. Paths use exactly
`api/<receipt-kind>/<receipt-sha256>/<zero-based-8-digit-page>.response` or the corresponding
`.canonical.json`. `kind` is exactly `safe_raw_response` or
`canonical_projection`. Decoded bytes must hash to `sha256`; canonical projections must parse as
their named strict schema and reproduce every `canonical_response_sha256`, while safe raw response
bytes reproduce every `raw_response_sha256`. `api_receipts` is an ordered array of strict
`ArchivedApiReceiptBindingV1` elements with exactly `receipt_kind`, `receipt_sha256`, `receipt`,
`raw_blob_paths`, and `canonical_blob_paths`. Kind order is `github_signature`,
`tag_ruleset_observation`, `t0_creation_suite`, then `t1_creation_suite`; repeated observations
sort by `(observed_at,receipt_sha256)`. Path arrays have equal cardinality and index `i` maps
one-to-one to receipt raw/canonical hash array index `i`; singular creation fields are normalized
to one-element arrays only by this wrapper. Every path occurs exactly once globally; no blob is
unreferenced, multiply referenced, missing, or keyed by an undefined observation ID. Raw bytes are
exact safe response-body bytes, excluding HTTP headers, authorization, cookies, and query secrets;
a secret-bearing blob is invalid.
`receipt_kind` must match the embedded receipt's schema discriminator and `receipt_sha256` must
equal that receipt's recomputed exact self digest. At every index, the archived raw/canonical blob
entry's `sha256` must equal the corresponding embedded receipt hash. The wrapper has no self field;
its exact canonical value is bound only by `protocol_review_object_archive_sha256`.
Offline replay recomputes every receipt hash from these bytes and the canonical projection, but API
bytes remain platform observation evidence, not independent cryptographic provenance or proof of
GitHub origin.

The post-tag binding is first persisted only in secret-free preflight evidence and the append-only
campaign authority; those are its only live authority sources. Downstream records and the final
offline archive may copy it only through the sealed `CampaignRegistryV1`. It is forbidden from C0,
all statements, all reviewer commits, B0, T0, and T1. This separation is what removes the hash
cycle: the immutable DAG is completed first, and only then is its complete object binding
constructed.

`CampaignInputPackageV1` remains a C0-only package and contains neither attestations nor an
attestation root. Preflight instead builds a `CampaignRegistryPayloadV1` containing the exact
`campaign_input_package_sha256`, both reviewer-registry digests, `workflow_root`, the complete
`ProtocolAttestationTagBindingV1`, `tag_operator_registry_sha256`, `tag_ruleset_policy_root`,
`publication_branch_ruleset_policy_sha256`,
`invalid_event_dismissal_policy_sha256`,
`main_fallback_liveness_policy_sha256`,
`broker_token_delivery_isolation_policy_sha256`,
ordered exact `broker_signing_keys: BrokerSigningKeyV1`,
`broker_signing_keys_root_sha256`,
`protocol_attestations_root`, and
`protocol_attestation_bundle_sha256`. `campaign_registry_sha256` is the SHA-256 with separator
`laconian-campaign-registry-v1` over the canonical payload. `campaign_id` is exactly
`benchmark-` followed by the first 32 lowercase hex characters of that digest.
`CampaignRegistryV1` contains exactly `schema_version`, `campaign_id`, `payload`, and
`campaign_registry_sha256`; it rejects any ID not derived from its payload. Thus T1, B0, all three
review commits, their verified signatures, and the stable tag-ruleset policy bind campaign identity
without requiring any containing Git object to hash itself.
The registry key array byte-equals the reviewed C0 input-package array; its root uses leaves
`SHA256(UTF8("laconian-broker-signing-key-leaf-v1\n") || CanonicalJSONV1(key))`, binary nodes
`SHA256(UTF8("laconian-broker-signing-key-node-v1\n") || left || right)`, and final wrapper
`SHA256(UTF8("laconian-broker-signing-keys-root-v1\n") || CanonicalJSONV1({count:3,merkle_root}))`.
For the fixed three leaves `L0,L1,L2`, odd-node handling is literal duplication:
`N01=node(L0,L1)`, `N22=node(L2,L2)`, and `merkle_root=node(N01,N22)`; promotion or a sentinel leaf
is invalid.
No preflight-selected or merely root-claiming key is admissible.

Cardinality, order, numeric account ID, login, verification mode, fingerprint, canonical bytes,
and digest are all security boundaries. A login rename, numeric-ID mismatch, missing required
fingerprint, reordered role, duplicate identity, or cross-registry lookup fails closed. Neither
registry, its members, signatures, approvals, statements, envelopes, tags, nor roots may substitute
for the other.

### 6.6 Frozen workflow inventory

The C0 workflow endpoint policy includes strict `MainFallbackLivenessPolicyV1` with exactly
`schema_version`, `repository_id`, `protected_ref: "refs/heads/main"`, `required_check_name`,
`workflow_root`, `member_paths`, and `main_fallback_liveness_policy_sha256`; member paths are the
exact ordered 15-member inventory. Its digest is SHA-256 of
`UTF8("laconian-main-fallback-liveness-policy-v1\n") || CanonicalJSONV1(policy without exactly
main_fallback_liveness_policy_sha256)`. The input registry and campaign registry bind it, and
main ruleset/admission receipts bind the exact required check and policy digest.

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
`WorkflowInventoryV1` has exactly `schema_version`, `members`, and `workflow_root`. `members` is
the exact ordered 15-element array above; each member has exactly `path` and `sha256`.
`workflow_root` is exactly
`SHA256(UTF8("laconian-workflow-inventory-v1\n") || CanonicalJSONV1(inventory without exactly
workflow_root))`. The inventory rejects a
missing, extra, renamed, reordered, duplicated, nonregular, or byte-mismatched member. The root is
therefore derived only after C0 and all 15 member bytes have been verified; it is never accepted
from an input field without reconstruction.

All three protocol-review statements, verified envelopes, the bundle, the post-tag binding, the
generation-context expectation and final generation context, every provider projection, and
publication verification bind this same reconstructed
`workflow_root`. A different workflow subset, reordered inventory, or independently supplied root
cannot authorize a live stage or publication.

## 7. Execution architecture

### 7.1 Input tag, preflight, and generation-context expectation

The operator supplies the completed protected pair T0/T1 from section 6.5. Both are annotated-only;
T0 peels to the exact C0 to execute and T1 peels to the exact B0 that closes the serial review DAG.
The manually dispatched workflow rejects branch refs, lightweight or nested tags, moving aliases,
malformed or unpaired names, uncommitted manifests, arbitrary model input, and arbitrary shell
input.

A secret-free preflight:

1. reads both full refs and records their exact object OIDs before accepting any campaign data;
2. downloads the exact section 6.5 campaign object closure, verifies every raw object against both
   its Git SHA-1 OID and `GitObjectSHA256V1`, reconstructs every tree and exact delta, and rejects a
   missing, extra, substituted, malformed, or unreachable object;
3. verifies T0/C0/Rstat/Rjudge/Rsecurity/B0/T1 topology, fixed paths, canonical statements,
   envelopes, bundle, role order, subject roots, REST and GraphQL signature receipts, and required
   local keyed-signature checks;
4. reads both refs again and requires byte-identical ref/OID pairs, reconstructs the closed stable
   `TagRulesetPolicyV1`, verifies fresh current-read receipts and the two unique historical
   `TagCreationRuleSuiteReceiptV1` records with exact authorized creation bypasses, and constructs
   `ProtocolAttestationTagBindingV1`; any movement, deletion/recreation, suite replay/ambiguity,
   creation race, peel change, wrong creator/after-OID, unauthorized creation or update/delete
   bypass, or semantic policy mismatch discards the candidate preflight;
5. validates the three static manifests and all captured C0-only inputs;
6. constructs the canonical `CampaignRegistryV1`, derives `campaign_id` from
   `campaign_registry_sha256`, and uses that digest as the common downstream campaign binding;
7. materializes one 480-row parent plan for each model and one ordered campaign-plan index;
8. deterministically projects 36 immutable model/scenario shard plans;
9. verifies that the shard plans are disjoint and that their ordered union is exactly the 1,440
   parent rows, with no gap or duplicate;
10. calculates planned call and token exposure;
11. binds the dated price snapshot, calculation rules, and official source URLs;
12. calculates projected campaign and worst-batch reservations and verifies that the first batch
   can start under the fixed budget policy; and
13. publishes only a preflight summary, registry digest, and safe verification receipts for
    environment review.

Before `PREFLIGHT_SEALED`, missing or temporarily unavailable refs, Git objects, REST/GraphQL
responses, or ruleset reads produce a safe no-launch result: they create no campaign authority,
state transition, reservation, provider dispatch, or external write, and the unchanged candidate
may be checked again. A proven mismatch, malformed object, or drift also produces no launch; it
cannot be waived or repaired under the same pair. After `PREFLIGHT_SEALED`, a transient read
failure produces no new state and no external effect, while proven deletion, ref movement,
raw-object mismatch, topology substitution, reviewer/signature mismatch, ruleset drift, or
cross-campaign replay emits the phase-authorized `PERMANENT_STOP` and forbids further live work.
A STOPped pair is never resumed by restoring a ref; continuation requires a new pair and campaign
identity.

No provider credential is available during preflight. The workflow does not scrape provider
pricing as a security or correctness boundary. Before approving a live batch, the environment
reviewer checks the frozen source URLs against the committed snapshot and records an attestation.
If the current rate cannot be verified or differs, the reviewer does not approve; revised rates
require a new input tag and campaign identity.

After the generation layer is final and before hard scoring, the campaign authority constructs an
authority-bound `GenerationContextExpectationV1`. It binds the campaign ID,
`campaign_registry_sha256`, both reviewer-registry digests, `protocol_attestations_root`, the exact
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

`BatchPlanV1` binds campaign ID, `campaign_registry_sha256`, phase (`generation` or `judge`), both
tag object OIDs and raw-object SHA-256 values, peeled C0 and B0 object bindings, workflow-file hash,
predecessor-ledger hash, ordered shard and request identities, maximum request attempts, worst-case
reservation, price-snapshot hash, monotonic-time allowance, soft deadline, and its own hash. The
plan size is a deterministic function of the remaining authorized exposure,
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
- checkout of preflight-recorded detached C0 without persisted credentials, followed before each
  credential-bearing step by a fresh double-read of both exact refs and verification of the sealed
  `campaign_registry_sha256`, T0/C0 and T1/B0 object bindings, stable ruleset policy root with fresh
  observation receipts, and no-drift
  condition; and
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

1. selects the exact artifact ID from the exact workflow-run ID, run attempt, both tag-object
   bindings, peeled C0/B0 bindings, `campaign_registry_sha256`, workflow-file hash, environment
   deployment, batch-attempt ID, and upload service digest; latest-by-name lookup is forbidden;
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
triggering `CampaignEventV1` type and hash, `campaign_registry_sha256`, both tag-object bindings,
peeled C0/B0 bindings, active phase-plan hash, spend-ledger hash, artifact-inventory Merkle root,
`unresolved_hold_root`, `active_credential_exposure_incident_id`,
`active_credential_exposure_pending_root`, optional STOP/incident ID, exact workflow/job or reviewer identities,
nonnull `publication_merge_denylist_root_sha256`, nullable
`active_publication_terminal_containment_root`,
`state_writer_git_identity_sha256`, and its own hash. Every event is single-use and parent-bound.
Authority genesis stores the complete `CampaignRegistryV1` and
`ProtocolAttestationTagBindingV1`; every successor event must reproduce their digests unchanged.
Every phase plan, reservation, ledger, capsule, hard-score set, judge projection, audit packet,
analysis attachment, evidence inventory, bundle, publication/correction intent and receipt, merge
evidence, result tag, release asset, and replay registry binds the same
`campaign_registry_sha256`. Supplying component hashes without that common registry digest confers
no authority.
Every state or hold mutation runs under the repository-wide concurrency group and performs a
compare-and-swap against the exact last valid state, unresolved-hold root, and active pending root.
The two active exposure fields are both null or both nonnull. An ordinary successor must reproduce
both null; only the exposure events below may install, advance, consume, or clear them.
Preflight installs the canonical empty `PublicationMergeDenylistV1` root. Every ordinary successor
byte-preserves both publication-containment fields. Only
`PUBLICATION_TERMINAL_CONTAINMENT_STARTED` may advance the denylist root and set a previously null
active containment root; only its exact premerge or merge-won terminal consumer may clear that
active root, and no event ever removes a denylist entry. Containment start requires the exposure
pair either null or already terminal-ready with its exact pending record and every inventoried
effect receipt complete. No exposure pending/progress event and no invalid-event hold may be
installed while the containment root is nonnull. The eventual terminal consumer binds and clears
an already-active terminal-ready exposure pair atomically while preserving the denylist forever.
A newly detected exposure after containment start denies further broker dispatch, leaves the
active containment root and denylist intact, and requires external credential revocation/rotation
before the same evidence-preserving containment run can resume; it cannot mutate the immutable
pre-containment route or silently create a second campaign root.

For every containment schema in this document, **full containment publication identity** expands
in place, in this exact order, to `campaign_id`, `campaign_registry_sha256`, `publication_id`,
nullable `publication_attempt`, nullable `correction_id`, `bundle_kind`,
`publication_plan_sha256`, `authorizing_intent_sha256`, `repository_id`, `parent_state`,
`source_authority_parent_oid`, `authority_phase`, `branch_name`, `expected_base_oid`,
`expected_head_oid`, `pull_request_marker`, and `publication_head_commit_trailer`. Initial
publication has a positive attempt and null correction; correction has a null attempt and a
nonempty correction ID. `source_authority_parent_oid` is the parent reconstructed before the
containment CAS. It is never aliased to the accepted containment successor or to a later terminal
event parent.

`PUBLICATION_TERMINAL_CONTAINMENT_STARTED` is a nonterminal same-state, transition-plus-one
`CampaignEventV1` accepted only by expected-OID CAS. It has exactly `schema_version`, the full
containment publication identity, `event_type="PUBLICATION_TERMINAL_CONTAINMENT_STARTED"`, positive
`parent_transition_number`, nested exact
`terminal_containment_intent: PublicationTerminalContainmentIntentV1`,
`terminal_containment_intent_sha256`, `predecessor_merge_denylist_root_sha256`, nested exact
`successor_merge_denylist: PublicationMergeDenylistV1`,
`successor_merge_denylist_root_sha256`, `publisher_broker_phase="terminalizing"`,
`publisher_broker_phase_ledger_prefix:
PublisherBrokerPhaseLedgerPrefixV1(prefix_purpose="containment_start")`,
`publisher_broker_phase_ledger_prefix_sha256`, nested exact
`publisher_vault_audit_prefix: BrokerVaultAuditPrefixV1(prefix_purpose="containment_start")`,
`publisher_vault_audit_prefix_sha256`,
`outstanding_token_request_count=0`, `outstanding_operation_dispatch_count=0`,
`live_token_count=0`,
`constructive_mint_disabled=true`, `source_workflow="benchmark-publish.yml"`,
`source_job="publication_terminalizer"`,
`source_workflow_sha256`, `source_ref_class="protected_current_main"`, `occurred_at`, and
`campaign_event_sha256`. The accepted mutation atomically appends the intent and successor denylist,
advances authority, preserves the state name, and sets the active root to the intent digest. It is
allowed only for an active initial complete/invalid publication prefix or a correction publication
prefix; write ambiguity remains allowed when preflight already observed one merged candidate so the
unresolved remainder is still tombstoned. The hold root is null at start; the exposure pair may be
null or may be the exact already-active, fully inventoried, terminal-ready pair named by the route
and consumed by the terminal event. No exposure event may advance it after start. The signed
phase-ledger/vault prefixes recompute the monotone terminalizing transition, every closed request and
zero live tokens; the counts are not free assertions. While the active root is nonnull, every
constructive token, enqueue/merge admission, release authorization, new publication/correction
intent and unrelated successor is denied. Only post-CAS barrier work, exact merge-won
classification, or the event-type pair named by the intent may proceed. Crash recovery resumes from
this root. The terminal consumer's immediate parent is the containment authority OID or a preserving
descendant; the original source parent is checked separately through the intent, never incorrectly
required to equal the final event parent.
The two nested containment-start prefixes have byte-identical publication/scope identity and
purpose; the vault prefix's paired-ledger digest equals the nested ledger-prefix digest, every
duplicated root/count/time recomputes, and the event's three zero counts equal both prefixes.
Source workflow SHA is the frozen C0 member and workflow/job/ref fields byte-equal the exact
caller-policy row.

Only a request that has already passed authenticated exact-repository/run/campaign, OIDC/App,
caller/callee, transport, and sealed-registry checks is hold-worthy. If that request then fails
event schema, parent, hash, required evidence, or a literal allowed-edge check, the broker uses the
existing state-writer authority to append internal `INVALID_EVENT_HELD` by expected-OID CAS. Pre-auth
garbage, temporary reads, wrong repository/run/campaign, and a verified benign sibling/stale CAS
request receive only an append-only broker audit denial and cannot create a campaign hold.

`InvalidEventHoldV1` has exactly `schema_version`, `campaign_id`, `hold_id`,
`rejected_request_sha256`, `parent_authority_oid`, `parent_state`, `parent_transition_number`,
`current_state_root`, `spend_ledger_root`, `artifact_inventory_root`, `active_phase_plan_root`,
`source_workflow`, `source_actor_id`, `source_actor_login`, `failed_validation`, `held_at`, and
`invalid_event_hold_sha256`, using `laconian-invalid-event-hold-v1`. The broker appends exact
`holds/<hold-id>/hold.json`; the state name is unchanged, transition number advances, and
`unresolved_hold_root` becomes that hold root. At most one unresolved hold exists. A racing later
request is audit-denied without another state transition. Every entrypoint blocks provider
dispatch, artifact download, and ordinary external effects while the root is nonnull.
The hold digest is SHA-256 of `UTF8("laconian-invalid-event-hold-v1\n") ||
CanonicalJSONV1(hold without exactly invalid_event_hold_sha256)`.
The generated liveness schema permits a broker-owned hold only in states and reconstructed
authority phases with at least one legal hold-consuming edge: every prepublication state listed in
the ordinary STOP table except `COMPLETE_PUBLICATION_PR_OPEN`, `BUNDLE_COLLECTED` only when it has
no active initial-publication prefix, `RESULT_MERGED`, and bare `RELEASED`. Any active initial-
publication prefix, `COMPLETE_PUBLICATION_PR_OPEN`, or `RELEASED`/`RELEASE_BLOCKED` tree with a
nonterminal correction `intent`, publication, merge, tag, or release prefix is ineligible; a state-
name-only check is forbidden. Because every publication intent requires a null hold, no initial PR
can exist while a hold is current. The schema forbids holds in
budget/invalid-finalization/publication and other terminal states. The rejected external request
never becomes an event; only the broker-authored `INVALID_EVENT_HELD` request/event/commit mutates
authority.

The versioned `CampaignStateSchemaV1` canonical state/event schema is the single source of truth
for state names, event names, allowed parent-state and bundle-kind combinations, required evidence,
and terminality. The table below is a generated human-readable rendering of that schema, and tests
load the same schema rather than maintaining a second transition list. Any table/schema drift,
unknown enum value, or event whose evidence discriminator does not match its parent is rejected.
The same source generates a reachability/liveness matrix over every state, event, caller workflow,
trigger-ref rule, reason/evidence discriminator, and terminal/resumption outcome. Broker policy and
tests consume that matrix; every admitted event must be reachable, every nonterminal state must have
an authorized success, invalidation, STOP, or correction continuation, and no table-only or
broker-only edge is permitted.
For `GENERATION_SET_SEALED`, the schema's exact required-evidence set is the ordered 36 capsule
hashes, `generation_context_expectation_sha256`, and `verified_generation_context_root`; neither
root is optional, derivable after the transition, or replaceable by a raw context payload.

The closed `PERMANENT_STOP.reason` enum is exactly, in schema order:

```text
provider_authentication_failure
provider_permission_failure
provider_delivery_ambiguity
provider_contract_mismatch
reservation_ledger_mismatch
batch_identity_mismatch
artifact_integrity_failure
generation_context_integrity_failure
hard_score_integrity_failure
provider_evidence_incomplete
audit_identity_failure
audit_nonparticipation
audit_reveal_failure
audit_adjudication_failure
analysis_statistical_failure
analysis_provenance_failure
analysis_integrity_failure
bundle_coverage_failure
bundle_lineage_failure
publication_lineage_failure
publication_reconciliation_unavailable
invalid_event_nondismissible
credential_exposure
protocol_authority_drift
```

No category name, alias, unknown reason, or wildcard is accepted. `OrdinaryStopEvidenceV1` is a
strict discriminated union for the first 22 reasons. Every variant has exactly `schema_version`,
`campaign_id`, `reason`, `parent_state`, `parent_authority_oid`, `current_state_root`,
`spend_ledger_root`, `artifact_inventory_root`, `active_phase_plan_root`,
`unresolved_hold_root`, `source_records_root`, `detail`, `observed_at`, and
`ordinary_stop_evidence_sha256`. The digest excludes itself and uses
`laconian-ordinary-stop-evidence-v1`. `detail` is itself strict: provider reasons contain
`provider_id`, `attempt_id`, `request_root`, and the applicable authentication, permission,
delivery, or contract receipt root; reservation/batch reasons contain `batch_plan_sha256`,
`reservation_root`, and `ledger_reconciliation_root`; artifact/generation/hard-score/provider-
evidence reasons contain `failed_artifact_root`, `expected_root`, and `verification_root`; audit
reasons contain `audit_packet_root`, `reviewer_or_reveal_root`, and `adjudication_root`; analysis
reasons contain `analysis_plan_root`, `statistical_or_provenance_root`, and `verification_root`;
bundle reasons contain `bundle_root`, `expected_inventory_root`, and `coverage_or_lineage_root`;
`publication_lineage_failure` contains `publication_plan_root`, `branch_pr_root`,
`lineage_verification_root`, and nullable `publication_pr_terminal_disposition_sha256`; and
`publication_reconciliation_unavailable` contains `publication_plan_root`,
`publisher_credential_disposition_set_sha256`, `reconciliation_unavailable_receipt_sha256`, and
nullable `publication_pr_terminal_disposition_sha256`; and
`invalid_event_nondismissible` contains `hold_id`,
`hold_sha256`, and `nondismissibility_evidence_root`. Fields belonging to another variant are
forbidden. `source_records_root` is the ordered Merkle root of the named, already sealed records;
empty, duplicate, reordered, or unbound records fail validation.

The last root above is not opaque. `InvalidEventNondismissibilityEvidenceV1` has exactly
`schema_version`, `campaign_id`, `campaign_registry_sha256`, `parent_state`,
`parent_authority_oid`, `hold_id`, `hold_sha256`, `rejected_request_sha256`, ordered nonempty
`failed_validation`, `source_records_root`, `observed_at`, and
`nondismissibility_evidence_sha256`. It reproduces the accepted `InvalidEventHoldV1` request,
validation set and current hold identity; its domain is
`laconian-invalid-event-nondismissibility-evidence-v1\n`, omitting only its final digest. The
ordinary STOP detail's `nondismissibility_evidence_root` must equal this exact digest.

The reason-to-`detail` mapping is literal: the four provider variants use exactly
`provider_id,attempt_id,request_root,failure_receipt_root`; reservation uses
`batch_plan_sha256,reservation_root,ledger_reconciliation_root`; batch identity uses
`batch_plan_sha256,reservation_root,batch_identity_verification_root`; artifact uses
`failed_artifact_root,expected_root,verification_root`; generation-context uses
`generation_context_expectation_sha256,observed_context_root,verification_root`; hard-score uses
`hard_score_plan_root,observed_hard_score_root,verification_root`; provider-evidence uses
`evidence_inventory_root,expected_inventory_root,verification_root`; all four audit variants use
`audit_packet_root,reviewer_or_reveal_root,adjudication_root`; all three analysis variants use
`analysis_plan_root,statistical_or_provenance_root,verification_root`; both bundle variants use
`bundle_root,expected_inventory_root,coverage_or_lineage_root`; publication uses
`publication_plan_root,branch_pr_root,lineage_verification_root,
publication_pr_terminal_disposition_sha256`; publication reconciliation unavailable uses exactly
`publication_plan_root,publisher_credential_disposition_set_sha256,
reconciliation_unavailable_receipt_sha256,publication_pr_terminal_disposition_sha256`; and
nondismissible hold uses
`hold_id,hold_sha256,nondismissibility_evidence_root`. Each comma-separated list is the complete
field set for that discriminator; no shared optional or alternate detail field exists.

Every absence/close/merge terminalization of an initial or correction publication segment before a
valid admitted merge uses one strict phase-aware terminal-disposition record rather than guessing a
platform-assigned PR number or treating state name as effect phase.
`PublicationPRTerminalDispositionV1` has exactly these ordered fields:

```text
schema_version
campaign_id
campaign_registry_sha256
publication_id
publication_attempt
correction_id
bundle_kind
publication_plan_sha256
authorizing_intent_sha256
parent_state
authority_parent_oid
authority_phase
branch_receipt_sha256
pull_request_receipt_sha256
branch_name
expected_base_oid
expected_head_oid
branch_create_delivery_resolution_sha256
pull_request_marker
pull_request_number
pull_request_node_id
pull_request_url
observed_base_oid
observed_head_oid
observed_merge_oid
pr_marker_discovery_sha256
pr_create_delivery_resolution_sha256
identity_mismatch_predicates
outcome
branch_outcome
close_kind
close_delivery_resolution_sha256
close_receipt_sha256
closed_observation_sha256
terminal_guard_set_sha256
recorded_at
publication_pr_terminal_disposition_sha256
```

The two close-evidence hashes above are class-bound. `PublicationCloseReceiptV1` has exactly
`schema_version="PublicationCloseReceiptV1"`, `campaign_id`, `campaign_registry_sha256`,
`publication_id`, nullable `publication_attempt`, nullable `correction_id`, `bundle_kind`,
`publication_plan_sha256`, `authorizing_intent_sha256`, `pull_request_number`,
`pull_request_node_id`, `pull_request_url`, `base_oid`, `head_oid`,
`close_idempotency_key`, `operation="publisher_closed"|"publisher_close_adopted"`,
`actor: GitHubAppInstallationIdentityV1(role="publisher")`,
`publisher_credential_disposition_sha256`, `request_receipts_root_sha256`, `closed_at`, and
`close_receipt_sha256`. Initial and correction
attempt nullability follows the enclosing disposition. Its domain is
`laconian-publication-close-receipt-v1\n`, omitting only `close_receipt_sha256`.

`PublicationClosedObservationV1` has exactly
`schema_version="PublicationClosedObservationV1"`, the same campaign/registry/publication/
attempt/correction/bundle/plan/intent and PR identity fields, `observed_state="closed"`,
`observed_merged=false`, nullable `observed_merge_oid` fixed to null, `closed_at`,
`first_read_receipt_sha256`, `second_read_receipt_sha256`, `observed_at`, and
`closed_observation_sha256`. Both authenticated reads bind the same exact PR as closed and unmerged
on either side of the close/discovery work immediately before candidate construction; a later
reopen neither rewrites the accepted terminal history nor can escape the permanent denylist: the
fresh Actions validator re-reads that root and fails the PR-head/merge-group required check. The
publisher terminal guard itself remains distinct protocol evidence. Its domain is
`laconian-publication-closed-observation-v1\n`, omitting only `closed_observation_sha256`. Both
records use RFC 8785 JSON, canonical whole-second UTC, exact identity equality, and no raw response
or credential bytes.

`PublicationPRStateObservationV1` has exactly `schema_version`, the same campaign/registry/
publication/attempt/correction/bundle/plan/intent and PR identity, `method="GET"`,
`endpoint_template="/repos/{owner}/{repo}/pulls/{pull_request_number}"`,
`state="open"|"closed"`, `merged`, nullable `merge_oid`, `base_oid`, `head_oid`, nullable
`closed_at`, nullable `merged_at`, `raw_response_sha256`, `canonical_response_sha256`,
`request_receipt_sha256`, `observed_at`, and `pr_state_observation_sha256`. Its state/merged/time
tuple must be GitHub-consistent and actor/base/head/marker identity is revalidated from the same
authenticated projection. Its domain is `laconian-publication-pr-state-observation-v1\n`, omitting
only its final digest.

`PublicationPRCloseDeliveryResolutionV1` has exactly `schema_version`, the same campaign/registry/
publication/attempt/correction/bundle/plan/intent and PR identity, `close_idempotency_key`, nested
exact `pre_dispatch_pr_observation: PublicationPRStateObservationV1`, ordered `attempts`, nested
exact `first_final_pr_observation: PublicationPRStateObservationV1`, nested exact
`second_final_pr_observation: PublicationPRStateObservationV1`,
`resolution=already_closed_no_dispatch|publisher_close_confirmed|publisher_close_adopted|
merge_won`, `final_state="closed"|"merged"`, nullable `final_merge_oid`,
nullable `prior_close_receipt_sha256`,
`publisher_credential_disposition_sha256`, `delivery_ambiguity=false`, `recorded_at`, and
`close_delivery_resolution_sha256`. Each attempt has
exactly positive `ordinal`, `request_id`, `dispatch_state="not_dispatched"|"dispatched"`, `method="PATCH"`,
`endpoint_template="/repos/{owner}/{repo}/pulls/{pull_request_number}"`,
`request_payload_sha256`, `outcome=not_dispatched|definitely_rejected_no_side_effect|closed_200|
non_2xx_resolved_closed|merge_won`, nullable `response_status`,
nullable `safe_response_sha256`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`, and `transport_receipt_sha256`. The
nested receipt is operation `pull_request_close`, attempt kind `pr_close`, has the same ordinal and
recomputed digest, and every duplicated field byte-equals this attempt. Confirmed close requires 200;
definite rejection permits only 400, 401, 403, or 404 plus safe proof; non-2xx resolved close permits
only 409 or 422 plus the final reads; response-loss has null status. Timeout, 5xx, 202, inconsistent
reads, or an unclassified transport leaves ambiguity and cannot be sealed.
Non-dispatch requires only `outcome=not_dispatched` with null response fields; dispatch requires
another outcome. Safe response is nonnull only for definite rejection.

`already_closed_no_dispatch` requires the authenticated pre-read already closed/unmerged and every
attempt non-dispatched. Any possibly delivered publisher close ending closed/unmerged requires
`publisher_close_confirmed|publisher_close_adopted` and a byte-matching nonnull
`PublicationCloseReceiptV1`. `merge_won` preserves the authenticated merge; its prior-close receipt
is nonnull exactly when a close write was confirmed or reconciled before reopen/merge, and otherwise
null. The two final reads have equal stable PR-state projections after excluding request/receipt/
observation time fields; their request IDs are distinct, the first completes before the second
dispatch, and `recorded_at` equals the second authenticated source time.
Its domain is `laconian-publication-pr-close-delivery-resolution-v1\n`, omitting only its final
digest. Thus a lost close response cannot be relabeled as a pre-existing close.

`PublicationPRMarkerPageReceiptV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `publication_id`, nullable `publication_attempt`, nullable
`correction_id`, `repository_id`, `operation_kind="pull_request_create"|
"terminal_guard_discovery"|"pull_request_close"|"terminal_merge_barrier_read"|
"terminal_reconciliation_read"`,
`operation_idempotency_key`, positive
`credential_attempt_ordinal`, positive `operation_request_ordinal`,
`publisher_credential_subject_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`, `observation_round=1|2`,
nullable positive `operation_round_ordinal`, nullable
`observation_stage="pre"|"post"|"final"|"containment_preflight"|
"containment_pre_action"|"containment_first"|"containment_second"`,
positive `page_ordinal`, `query_template`, `request_url`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `transport_terminal_at`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="publisher_app_installation_token_vault"`, `response_status=200`, nullable
`previous_link`, nullable `next_link`, ordered nested exact `pull_requests`,
`raw_response_sha256`, `canonical_response_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `pr_marker_page_receipt_sha256`. Each pull-request member has
exactly positive `number`, nonblank `node_id`, exact ASCII HTTPS `url`, positive `actor_id`,
`actor_login`, `base_oid`, `head_oid`, `state="open"|"closed"`, `merged`, nullable `merge_oid`,
nullable `closed_at`, nullable `merged_at`, `pull_request_marker`, and
`canonical_member_sha256`; fields are total projections of each response-array member in API
order. Raw/canonical/member hashes use the exact same rules as check pages. Identity, App,
credential, operation key, page, request/status and times byte-equal the generic publisher
transport wrapper; page `observation_round`, operation round and stage byte-equal the wrapper and
follow the closed matrix. The wrapper's `source_observation_sha256` equals this page
digest; the page does not
contain that wrapper digest, so the graph is acyclic. The signature and record domains are
`laconian-publication-pr-marker-page-signature-v1\n` and
`laconian-publication-pr-marker-page-receipt-v1\n`. Its signature preimage is
`UTF8(signature domain) || CanonicalJSONV1(record without exactly broker_signature_base64url and
pr_marker_page_receipt_sha256)`; its record digest is `SHA256(UTF8(record domain) ||
CanonicalJSONV1(record without exactly pr_marker_page_receipt_sha256))`, including the verified
signature. The signing-key validity window includes `transport_terminal_at`.

`PublicationPRMarkerArchiveV1` has exactly `schema_version`, the same publication/operation/
credential identity, nullable positive `operation_round_ordinal`, nullable
`observation_stage="pre"|"post"|"final"|"containment_preflight"|
"containment_pre_action"|"containment_first"|"containment_second"`, ordered `blobs`, ordered `page_bindings`, and
`pr_marker_archive_sha256`. Each blob has exactly `path`, `sha256`, and `raw_bytes_base64`; each
binding has exactly `observation_round=1|2`, positive gapless `page_ordinal`,
`page_receipt_sha256`, and `raw_blob_path`. Bindings are all round-one pages followed by all
round-two pages. The blob array has the identical positional order, decoded bytes reproduce the
page raw-body hash, and paths are exactly
`publication-pr-marker/<page-receipt-sha256>.response`; pages, bindings and blobs form a bijection.
Its domain is `laconian-publication-pr-marker-archive-v1\n`, omitting only its final digest.

`PublicationPRMarkerObservationV1` is one complete authenticated round. It has exactly
`schema_version`, the same publication/repository/marker/head/base/expected-OID/query identity,
`operation_kind`, `operation_idempotency_key`, positive `credential_attempt_ordinal`, nullable
positive `operation_round_ordinal`, nullable `observation_stage="pre"|"post"|"final"|
"containment_preflight"|"containment_pre_action"|"containment_first"|"containment_second"`,
`observation_round=1|2`, positive `page_count`, ordered nested exact
`pages: PublicationPRMarkerPageReceiptV1` all with that round, nested exact
`archive: PublicationPRMarkerArchiveV1`, `pr_marker_archive_sha256`,
`pagination_complete=true`, ordered `matching_pull_requests`, `observed_at`, and
`marker_observation_sha256`. Page ordinals are gapless, signed Links are complete, and archive
bindings/blobs contain exactly this round. Matches are the canonical number-ordered exact-marker
projection across all page members. `observed_at` equals the maximum page
`response_completed_at`. Its domain is `laconian-publication-pr-marker-observation-v1\n`, omitting
only its final digest.

`PublicationPRMarkerDiscoveryV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `publication_id`, nullable `publication_attempt`, nullable
`correction_id`, `repository_id`, `pull_request_marker`, `head_owner_login`, `head_branch_name`,
`base_branch_name`, `expected_base_oid`, `expected_head_oid`,
`query_template="GET /repos/{owner}/{repo}/pulls?state=all&head={head_owner_login}:{head_branch_name}&base={base_branch_name}&per_page=100"`,
`first_observation: PublicationPRMarkerObservationV1(observation_round=1)`,
`second_observation: PublicationPRMarkerObservationV1(observation_round=2)`,
ordered `matching_pull_requests`, `observed_at`, and `marker_discovery_sha256`. Each match has
exactly positive `number`, nonblank `node_id`, exact ASCII HTTPS `url`, `actor_id`, `actor_login`,
`base_oid`, `head_oid`, `state=open|closed`, `merged`, nullable `merge_oid`, nullable `closed_at`,
and nullable `merged_at`; the state/merged/nullability tuple must be GitHub-consistent. From a list
response, `merged` is derived exactly as `merged_at != null`, and `merge_oid` equals GitHub's
`merge_commit_sha` exactly when merged and is null otherwise; no nonexistent direct `merged` API
field is assumed. The query
parameters use branch labels, never OIDs; each returned base/head SHA is then compared separately
with the two expected OIDs. Both reads occur only after every PR-create dispatch has terminated and
no further PR-create write dispatch is authorized, fully follow authenticated `Link` pagination,
and produce the
same number-ordered projections; response-loss classifications are derived from those reads rather
than assumed before them. Every round-one wrapper terminal precedes the first round-two dispatch;
the two nested matching projections byte-equal the aggregate array, and `observed_at` equals the
second observation's authenticated time. Every page, generic wrapper and archive binding forms the
exact acyclic bijection above. Its domain is
`laconian-publication-pr-marker-discovery-v1\n`, omitting only its final digest.

`PublicationBranchObservationV1` has exactly `schema_version`, the same campaign/registry/
publication/attempt/correction/bundle/plan/intent identity, `repository_id`, `branch_name`,
`expected_head_oid`, `method="GET"`,
`endpoint_template="/repos/{owner}/{repo}/git/ref/heads/{branch_name}"`,
`status="absent"|"exact"|"conflicting"`, nullable `observed_head_oid`, `response_status`,
`raw_response_sha256`, `canonical_response_sha256`, `request_receipt_sha256`, `observed_at`, and
`branch_observation_sha256`. `absent` requires 404 and null head; `exact` requires 200 and the
expected head; `conflicting` requires 200 and a different head. Its domain is
`laconian-publication-branch-observation-v1\n`, omitting only its final digest.
For this branch record, `PublicationPRStateObservationV1`, and every later publisher non-page GET
observation, `request_receipt_sha256` means exactly the append-before-send
`PublisherOperationRequestDispatchReceiptV1.operation_request_dispatch_receipt_sha256`, never the
terminal wrapper digest. The matching `PublisherOperationTransportReceiptV1` points one-way to the
observation digest in `source_observation_sha256`; identity, operation/global ordinal, coordinates,
request, method/endpoint/payload/status and times form a bijection. No observation points back to
the terminal wrapper, so the graph is acyclic.

`ConflictingPublicationObjectsV1` has exactly `schema_version`, the same identity, ordered
`entries`, and `conflicting_publication_objects_root_sha256`. Each entry has exactly
`object_kind="branch"|"pull_request"|"check_run"`, `object_id`, `expected_head_oid`, nullable
`observed_base_oid`, `observed_head_oid`, `observed_state`, and `source_observation_sha256`.
Entries are sorted by kind order branch, pull request, check run and then canonical object ID; every
stable differing branch, marker PR, or same-App/context check from delivery/guard reconciliation is
included exactly once. Its domain is `laconian-conflicting-publication-objects-v1\n`, omitting only
the final root; the explicit empty record is valid when there is no conflict.

`PublicationBranchCreateDeliveryResolutionV1` has exactly `schema_version`, the same campaign/
registry/publication/attempt/correction/bundle/plan/intent identity, `branch_idempotency_key`,
`branch_name`, `expected_head_oid`, ordered `attempts`, `first_ref_read_receipt_sha256`,
`second_ref_read_receipt_sha256`, `resolved_branch_status=absent|exact|conflicting`, nullable
`observed_head_oid`, `publisher_credential_disposition_sha256`, `delivery_ambiguity=false`,
`recorded_at`, and
`branch_create_delivery_resolution_sha256`. Each attempt has exactly positive `ordinal`, `request_id`,
`dispatch_state=not_dispatched|dispatched`, `method="POST"`,
`endpoint_template="/repos/{owner}/{repo}/git/refs"`, `request_payload_sha256`,
`outcome=not_dispatched|definitely_rejected_no_side_effect|created_exact|
response_lost_resolved_exact|response_lost_resolved_conflict|non_2xx_resolved_exact|
non_2xx_resolved_conflict`, nullable `response_status`, nullable
`safe_response_sha256`, nullable `observed_head_oid`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`, and `transport_receipt_sha256`. The
nested receipt is operation/attempt kind `branch_create`, has the same ordinal and recomputed
digest, and every duplicated field byte-equals this attempt. The two final
authenticated ref reads occur only after every dispatched transport has terminated and byte-equal
one another. `absent` requires every attempt non-dispatched or definitely rejected and both reads
prove 404; `exact` requires both reads resolve the exact planned head; `conflicting` records the one
stable different head. A non-2xx resolution permits only status 409 or 422 and derives exact versus
conflicting solely from the two reads. Timeout, connection loss, 5xx, 202, or any result whose
delivery cannot be settled by the two reads leaves ambiguity and therefore cannot be sealed.
`recorded_at` equals the second authenticated read's source time. Its domain is
`laconian-publication-branch-create-delivery-resolution-v1\n`, omitting only its final digest.

`PublicationPRCreateDeliveryResolutionV1` has exactly `schema_version`, the same campaign/
registry/publication/attempt/correction/bundle/plan/intent identity,
`pull_request_idempotency_key`, ordered `attempts`, nested exact `final_marker_discovery`, nullable
`resolved_pull_request_number`, `resolved_status="none"|"exact"|"conflicting"`,
`publisher_credential_disposition_sha256`, `delivery_ambiguity=false`, `recorded_at`, and
`delivery_resolution_sha256`. Each attempt has exactly positive `ordinal`, `request_id`,
`dispatch_state=not_dispatched|dispatched`, `method="POST"`,
`endpoint_template="/repos/{owner}/{repo}/pulls"`, `request_payload_sha256`,
`outcome=not_dispatched|definitely_rejected_no_side_effect|created_exact|
non_2xx_resolved_exact`, nullable `response_status`, nullable `safe_response_sha256`,
nullable `resolved_pull_request_number`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`, and `transport_receipt_sha256`. The
nested receipt is operation `pull_request_create`, attempt kind `pr_create`, has the same ordinal
and recomputed digest, and every duplicated field byte-equals this attempt. `not_dispatched` has all
response fields null. `definitely_rejected_no_side_effect` requires status `400`, `401`, `403`, or
`404` and a class-bound safe response proving the request could not create an object. `created_exact`
requires `201` and the exact resolved PR. `non_2xx_resolved_exact` permits
only 409 or 422 plus final discovery of that unique exact PR. Timeout, connection loss, 5xx, 202,
or any other ambiguous result cannot be labeled rejected.

`none` requires a null top-level number, every attempt non-dispatched/definitely rejected, and zero
admissible plan-bound matches. `exact` requires a positive number and exactly one admissible
plan-bound match; additional nonadmissible matches remain conflict evidence but do not replace it.
`conflicting` is every stable fully resolved projection that is neither `none` nor `exact`. Its
number is null when no admissible match is merged; when one or more admissible matches are merged it is the
number of the deterministic selected match, sorted first by authenticated `merged_at` and then by
ascending PR number. Every other duplicate, foreign or mismatched match is preserved in
`ConflictingPublicationObjectsV1` and every unmerged candidate head is terminally guarded. An
unresolved attempt forbids terminalization. The resolution domain is
`laconian-publication-pr-create-delivery-resolution-v1\n`, omitting only its final digest; arrays
are ordinal-ordered with no gaps or duplicates. `recorded_at` byte-equals
`final_marker_discovery.observed_at`; retry time or a local clock cannot change it.

Check-run reads are class-bound rather than anonymous page hashes. The ref-level check-run endpoint
is forbidden for completeness because GitHub limits it to runs from the 1,000 most recent check
suites. `PublicationCheckRunProjectionV1` has exactly positive `check_suite_id`, positive
`check_run_id`, `head_oid`, positive `app_id`, `app_slug`, `context`, `status`, nullable
`conclusion`, nullable `external_id`, nullable `started_at`, nullable `completed_at`, and
`canonical_response_sha256`.
Status is exactly `queued|in_progress|completed|waiting|requested|pending`; `completed` requires a
nonnull conclusion from exactly `success|failure|neutral|cancelled|skipped|timed_out|
action_required|stale` and nonnull completion time, while every noncompleted status requires both
null.

`PublicationCheckSuiteProjectionV1` has exactly positive `check_suite_id`, `head_oid`, positive
`app_id`, `app_slug`, and `canonical_response_sha256`.
`PublicationCheckSuitePageReceiptV1` has exactly `schema_version`,
the full campaign/registry/publication/attempt/correction/bundle/plan/intent identity,
`repository_id`, `operation_kind="merge_eligibility"|"terminal_guard"|
"terminal_reconciliation_read"`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, positive `operation_request_ordinal`, `head_oid`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`, positive `publisher_app_id`,
`publisher_app_slug`, `publisher_credential_broker_policy_sha256`,
`authorized_policy_row_sha256`, `publisher_credential_subject_sha256`,
`token_fingerprint_sha256`, `token_vault_committed_at`,
`token_expires_at`,
`method="GET"`, `endpoint_template`, `query_template`, `request_url`, `api_version="2022-11-28"`,
`accept_header="application/vnd.github+json"`,
`authentication_kind="publisher_app_installation_token_vault"`,
nullable positive `operation_round_ordinal`, nullable
`observation_stage="post"|"final"`, `observation_round=1|2`, positive `page_ordinal`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `transport_terminal_at`,
`response_status=200`, nonnegative `total_count`,
ordered `check_suites: PublicationCheckSuiteProjectionV1`, nullable `previous_link`, nullable
`next_link`, `raw_response_sha256`, `canonical_response_sha256`, `authenticated_at`, and
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, `page_receipt_sha256`. `authenticated_at` equals the broker-signed
`response_completed_at`. Every page requires
`token_vault_committed_at <= request_dispatched_at < token_expires_at` and
`request_dispatched_at <= response_completed_at <= transport_terminal_at`; response status/body
and page receipt are terminal at
that time, which is inside the nested signing key's inclusive validity window.
`PublicationCheckRunPageReceiptV1` has the same exact pagination fields plus
positive `check_suite_id`, the fixed `check_context`, and ordered
`check_runs: PublicationCheckRunProjectionV1` instead of suites. Their domains are respectively
`laconian-publication-check-suite-page-receipt-v1\n` and
`laconian-publication-check-run-page-receipt-v1\n`, omitting only the final page digest.
Their signature domains are exactly
`laconian-publication-check-suite-page-signature-v1\n` and
`laconian-publication-check-run-page-signature-v1\n`; each signature preimage is
`UTF8(the matching signature domain) || CanonicalJSONV1(record without exactly
broker_signature_base64url and page_receipt_sha256)`. Each record digest is
`SHA256(UTF8(the matching record domain) || CanonicalJSONV1(record without exactly
page_receipt_sha256))`, including the verified signature, and verifies under the
policy/registry publisher key whose `not_before <= transport_terminal_at <= not_after`.
The suite endpoint template is exactly
`/repos/{owner}/{repo}/commits/{head_oid}/check-suites`; the run endpoint is exactly
`/repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs`; each concrete query template adds
only the class-bound App/context/filter/per-page parameters described below. These literal method/
endpoint fields byte-equal the generic wrapper rather than being inferred from request URL text.
Every suite/run projection's head, App ID/slug and run `context` byte-equal the enclosing
observation and raw GitHub `name`; a mismatch fails closed.
Every page's full identity, operation/key/ordinal, App installation, policy/row, credential-subject
digest, token fingerprint and token times byte-equal its enclosing observation and the exact
same-operation `PublisherCredentialSubjectV1`. The operation projection nests one exact
`PublisherOperationTransportReceiptV1` wrapper whose `source_observation_sha256` equals this page
digest; the broker ledger names the wrapper's distinct transport digest and its start entry names
the wrapper's nested dispatch digest. Those three domain-separated digests are never
interchangeable; cross-campaign, cross-operation or cross-token page reuse is invalid.
The wrapper and page also have byte-equal identity, operation/key/credential subject and ordinal,
request ID, method/endpoint, page, token provenance and dispatch time; wrapper
`observation_round` equals page `observation_round` and operation-round/stage follow the closed
matrix; wrapper outcome is
`read_200`, response status/completion equal the page, and
`attempt_terminal_at = page.transport_terminal_at`. Its nested dispatch receipt reproduces the
page request and operation-request ordinal. Any disagreement is invalid even when both signatures
verify independently.
`publisher_app_id = app_identity.app_id` and `publisher_app_slug = app_identity.app_slug`; both also
byte-equal the selected policy and sealed registry publisher-App member. The concrete suite query's
`app_id` is derived only from that sealed identity. A page that filters on any other App, including
another installed App with a matching context, is invalid.
For either page, `raw_response_sha256` is SHA-256 of the exact archived HTTP response-body bytes and
`canonical_response_sha256` is SHA-256 of RFC 8785 canonical JSON for the complete parsed response
body. Each member projection's `canonical_response_sha256` is instead SHA-256 of RFC 8785 canonical
JSON for that exact unprojected response-array member; its selected fields must equal that parsed
member. The archived page bytes, parsed page object, member order and all projections are therefore
one replayable mapping; a synthetic member hash or unreferenced response member is invalid.

`PublicationCheckApiArchiveV1` has exactly `schema_version`, the same campaign/registry/
publication/attempt/correction/bundle/plan/intent identity, `repository_id`, `operation_kind`,
`operation_idempotency_key`, `credential_attempt_ordinal`, `head_oid`, nullable positive
`operation_round_ordinal`, nullable `observation_stage="post"|"final"`,
`observation_round=1|2`, ordered `blobs`, ordered `page_bindings`, and
`check_api_archive_sha256`. Each blob has exactly `path`, `sha256`, and `raw_bytes_base64`; decoded
bytes reproduce `sha256`, and paths are exactly
`publication-check-api/<page-receipt-sha256>.response`. Each binding has exactly
`page_kind="check_suite"|"check_run"`, nullable positive `check_suite_id`, positive
`page_ordinal`, `page_receipt_sha256`, and `raw_blob_path`. Suite bindings require null suite ID;
run bindings require the enclosing suite ID. Bindings are ordered by all suite pages then ascending
suite ID/run page, and form a bijection over every nested page receipt and blob: receipt raw hash,
blob hash and decoded exact response bytes all match. The `blobs` array uses exactly that same
binding order, with `blobs[i].path = page_bindings[i].raw_blob_path`; no alternate path sort or
permutation is valid. Bytes are response bodies only and exclude
headers, authorization and cookies. Its domain is
`laconian-publication-check-api-archive-v1\n`, omitting only its final digest.

`PublicationCheckSuiteRunEnumerationV1` has exactly `schema_version`, positive `check_suite_id`,
`query_template="GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs?check_name=laconian%2Fpublication-terminal-guard&filter=all&per_page=100"`,
positive `page_count`, ordered nested exact
`page_receipts: PublicationCheckRunPageReceiptV1`, `pagination_complete=true`, ordered
`check_runs: PublicationCheckRunProjectionV1`, and `enumeration_sha256`. Every member repeats that
suite ID and the array is sorted by ascending unique check-run ID. Its domain is
`laconian-publication-check-suite-run-enumeration-v1\n`, omitting only its final digest.

`PublicationCheckRunsSemanticSnapshotV1` has exactly `schema_version`, `head_oid`, positive
`publisher_app_id`, `publisher_app_slug`,
`check_context="laconian/publication-terminal-guard"`, ordered `check_suites`, ordered `check_runs`,
`publisher_context_state="none"|"all_success"|"all_failure"|"mixed_or_nonterminal"`, nullable
`sole_publisher_context_check_run_id`, and `check_runs_semantic_snapshot_sha256`. Each suite member
has exactly `check_suite_id`, `head_oid`, `app_id`, and `app_slug`; each run member has exactly
`check_suite_id`, `check_run_id`, `head_oid`, `app_id`, `app_slug`, `context`, `status`, nullable
`conclusion`, nullable `external_id`, nullable `started_at`, and nullable `completed_at`. Arrays use
the same complete canonical order and status/nullability rules as the source observation. The
snapshot is a total projection: it preserves all external IDs and GitHub lifecycle times but
excludes only operation/credential/policy/token/request, pagination, archive, raw/canonical-response,
signature and observation-time provenance. Its domain is
`laconian-publication-check-runs-semantic-snapshot-v1\n`, omitting only its final digest.

`PublicationCheckRunsObservationV1` has exactly `schema_version`, the same campaign/registry/
publication/attempt/correction/bundle/plan/intent identity, `repository_id`, `branch_name`,
`operation_kind="merge_eligibility"|"terminal_guard"|"terminal_reconciliation_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`,
`publisher_credential_broker_policy_sha256`, `authorized_policy_row_sha256`,
`publisher_credential_subject_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`,
`token_fingerprint_sha256`, `token_vault_committed_at`, `token_expires_at`,
`head_oid`, nullable positive `operation_round_ordinal`, nullable
`observation_stage="post"|"final"`, `observation_round=1|2`,
`check_context="laconian/publication-terminal-guard"`, positive `publisher_app_id`,
`publisher_app_slug`,
`check_suites_query_template="GET /repos/{owner}/{repo}/commits/{head_oid}/check-suites?app_id={publisher_app_id}&check_name=laconian%2Fpublication-terminal-guard&per_page=100"`,
positive `suite_page_count`, `suite_pagination_complete=true`, ordered nested exact
`suite_page_receipts: PublicationCheckSuitePageReceiptV1`, ordered positive unique
`check_suite_ids`, ordered nested exact
`suite_run_enumerations: PublicationCheckSuiteRunEnumerationV1`, nested exact
`check_api_archive: PublicationCheckApiArchiveV1`, ordered
`check_runs: PublicationCheckRunProjectionV1`, `publisher_context_state="none"|"all_success"|
"all_failure"|"mixed_or_nonterminal"`, nullable `sole_publisher_context_check_run_id`,
`semantic_snapshot: PublicationCheckRunsSemanticSnapshotV1`,
`check_runs_semantic_snapshot_sha256`,
`observed_at`, and `check_runs_observation_sha256`. The suite IDs are the complete ascending
publisher-App suite projection for the head; there is exactly one enumeration per suite in that
order. Its App ID/slug and query substitution obey the same four-way App equality as every page.
The nested semantic snapshot is the exact total projection of these suite/run arrays and its
duplicated digest recomputes.
The nested archive identity/round byte-equals the observation and covers exactly all its
suite/run pages. Every nested page repeats the observation's operation/credential provenance. The aggregate contains every run for the fixed context regardless of external ID, sorted by
ascending unique `(check_suite_id,check_run_id)`. `none` requires an empty aggregate;
`all_success|all_failure` require a nonempty aggregate in which every member is completed with that
conclusion; every other projection is mixed/nonterminal. The sole ID is nonnull exactly when the
aggregate cardinality is one. Unsupported pagination, an API cap, a suite/run identity mismatch,
or any incomplete page set fails closed. Its domain is
`laconian-publication-check-runs-observation-v1\n`, omitting only its final digest.

For both page types, receipt count equals `page_count`, ordinals start at one without gaps, page one
has null previous link, every next link byte-equals the next page's signed `request_url` and that
page's previous link byte-equals the prior page's signed `request_url`; only the final page has null
next link. Every page repeats one stable `total_count`; the
deduplicated aggregate cardinality equals it, response objects equal the page projections, and no
ID appears twice. Suite enumeration binds every suite projection's head/App identity; its run
enumeration binds that suite ID and fixed context. Observation `observed_at` is the maximum
broker-signed response-completion time, and every nested page repeats its round. A bare hash or
boolean cannot substitute for these nested receipts.
Every page `query_template` byte-equals its enclosing suite/run literal. `request_url` is the
canonical HTTPS expansion on `api.github.com` with an explicit positive `page` equal to
`page_ordinal`; page one is the literal expansion plus `page=1`, and every later URL equals the
preceding signed `next_link`. Links have the same owner/repository/path and `per_page=100`; only the
positive `page` parameter may change. Suite-page links preserve exactly `app_id` and `check_name` and forbid
`filter`; run-page links preserve exactly `check_name` and `filter=all` and forbid `app_id`. Each
projection's canonical member digest maps to its exact containing response member.
For every page and publisher operation request, concrete URL `{owner}/{repo}` is substituted only
from the sealed campaign-registry repository identity; the page/operation `repository_id`, publisher
App installation repository ID and that registry member are equal. A caller-provided owner/repo or
a signed observation from another repository is invalid even when the head OID happens to match.

`PublicationPostGuardVerificationReceiptV1` has exactly `schema_version`, the same identity,
`branch_name`, `head_oid`, the fixed context, `guard_external_id`, positive `guard_check_run_id`,
`guard_delivery_resolution_sha256`, nested exact
`first_check_runs_observation: PublicationCheckRunsObservationV1`, nested exact
`second_check_runs_observation: PublicationCheckRunsObservationV1`,
`verified_guard_check_run_id`, `all_publisher_context_runs_completed_failure=true`, `verified_at`,
and `post_guard_verification_receipt_sha256`. The two observations have identical identity/query
and byte-equal recomputed `PublicationCheckRunsSemanticSnapshotV1` digests; the
first is round one, the second
round two, every first-round response completes before the first second-round dispatch, and their
request IDs/receipt roots/times are distinct. Both have `publisher_context_state=all_failure`.
The verified ID equals the guard ID and names a member with the exact guard external ID; every
other publisher-App/context member is also completed failure, so platform selection cannot expose
a success or pending run. `verified_at` equals the second observation's authenticated `observed_at`. Its
domain is `laconian-publication-post-guard-verification-receipt-v1\n`, omitting only its final
digest.

`PublicationFinalCheckRunsObservationSetV1` has exactly `schema_version`, the same identity,
`set_kind="guarded"|"guarded_reconciliation"|"no_guard"|"merge_observed"`, nullable
`historical_guard_snapshot_sha256`, nullable `no_guard_reason`, ordered `guarded_head_oids`, ordered
`post_guard_verification_receipts: PublicationPostGuardVerificationReceiptV1`, ordered
`final_check_runs_observations: PublicationCheckRunsObservationV1`, `observed_at`, and
`final_check_runs_observation_set_sha256`. `guarded` requires null reason; all three arrays have
identical positive length and ascending unique head order, and each final observation byte-equals
its receipt's second observation; its historical snapshot root is null. It is the immutable snapshot
named by `PublicationTerminalGuardSetV1`.
`guarded_reconciliation` requires null reason, a nonnull historical snapshot digest equal to that
stable guard set's exact `guarded` object, and the same three ordered positive arrays. The receipt
array and heads byte-equal the historical snapshot, but every final observation is a fresh
`operation_kind="terminal_reconciliation_read"` inventory using the reconciliation-read credential
subject. For each head its recomputed semantic-snapshot digest equals the historical receipt's
second observation's snapshot digest;
both states are `all_failure`, and the fresh response begins only after the historical response is
terminal. The historical verification-receipt array is intentionally shared; no fresh final-
observation page, token, operation-wrapper or dispatch digest is reused.
`no_guard` requires a null historical root and exact reason
`absent_branch_and_zero_marker_matches`, three empty arrays, the class-bound final absent-branch and
zero-match marker reads in the enclosing reconciliation, and no terminal-guard dispatch or live
write token. Closed eligibility dispositions and their inventoried observations may exist.
`merge_observed` requires null historical root and null reason, empty guarded/receipt arrays, exactly one final observation
for the selected merged head, an exact merged-PR marker in the enclosing reconciliation, and no
unmerged candidate head. Successful admission additionally requires that observation to have
`publisher_context_state=all_success` and a nonnull sole ID; failed admission preserves any other
stable complete state. It is constructed before any release authorization.
`observed_at` is the latest fresh member or enclosing authenticated no-guard read time. Its domain is
`laconian-publication-final-check-runs-observation-set-v1\n`, omitting only its final digest.

Every success-check dispatch is likewise closed before a PR effect or terminal guard.
`PublicationMergeEligibilityDeliveryResolutionV1` has exactly `schema_version`, the same identity,
`branch_name`, `head_oid`, `check_context="laconian/publication-terminal-guard"`,
`eligibility_idempotency_key`, `external_id`,
`check_inventory_protocol="complete_check_suite_enumeration_v1"`,
ordered `attempts`, nested exact
`first_check_runs_observation: PublicationCheckRunsObservationV1`, nested exact
`second_check_runs_observation: PublicationCheckRunsObservationV1`, ordered
`lineage_check_run_ids`, nullable `sole_publisher_context_check_run_id`,
nullable `sole_lineage_check_run_id`, `resolved_status="none"|"exact_success"|"conflicting"`,
`publisher_credential_disposition_sha256`, `delivery_ambiguity=false`, `recorded_at`, and
`eligibility_delivery_resolution_sha256`. Each attempt has exactly positive `ordinal`,
`request_id`, `dispatch_state=not_dispatched|dispatched`, `method="POST"`,
`endpoint_template="/repos/{owner}/{repo}/check-runs"`, `request_payload_sha256`,
`outcome=not_dispatched|definitely_rejected_no_side_effect|created_exact`, nullable
`response_status`, nullable `safe_response_sha256`,
nullable `resolved_check_run_id`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`, and `transport_receipt_sha256`. The
nested receipt is operation `merge_eligibility`, attempt kind `check_create`, has the same ordinal
and recomputed digest, and every duplicated field byte-equals this attempt. The lineage-ID array is the exact
ascending subset of the second observation whose external ID equals this intent's `external_id`;
all-publisher/context membership is represented only in the nested observations. `not_dispatched`
has all response/result fields null;
`definitely_rejected_no_side_effect` permits only 400, 401, 403, or 404 plus a class-bound safe
response; `created_exact` requires 201 and its exact check-run ID.
The POST body has exactly `name`, `head_sha`, `external_id`, `status="completed"`, and
`conclusion="success"`; it omits output, actions, URLs and timestamps, and the attempt payload hash
is the RFC 8785 canonical digest of those exact authority-derived fields.
Timeout, connection loss, 5xx, 202, 409, or 422 is never a definite rejection. Both authenticated
reads fully paginate after all dispatches have terminated and no further dispatch is authorized,
use round one then round two, have distinct signed request/receipt roots, complete every round-one
response before the first round-two dispatch, and have byte-equal recomputed semantic-snapshot
digests. `none` requires empty observations and
lineage IDs, null sole IDs, and no possibly delivered attempt. `exact_success` requires the
complete aggregate to contain exactly one publisher-App/context run, every possibly delivered
attempt to resolve to that same one lineage run, equal nonnull sole publisher/lineage IDs, and
`publisher_context_state=all_success`.
Every other stable, fully inventoried projection is `conflicting`; it cannot authorize PR creation
but may be consumed by terminal guarding. The accepted `PublicationMergeEligibilityReceiptV1`
exists only for `exact_success`; its check-run ID equals both sole IDs and its embedded delivery
root byte-equals this record. A later same-App/context run with another external ID therefore blocks
eligibility rather than becoming invisible. `recorded_at` equals the final observation source time. Its domain is
`laconian-publication-merge-eligibility-delivery-resolution-v1\n`, omitting only its final digest.
An unresolved, late, or differently owned success check forbids both PR creation and terminal
authority.

The platform invariant is itself closed evidence. `PublicationBranchRulesetPolicyV1` has exactly
`schema_version`, `repository_id`, `protected_base_ref="refs/heads/main"`,
`publication_head_ref_pattern`, `allowed_ruleset_source_type="Repository"`, `enforcement="active"`,
`pull_request_required=true`, positive `minimum_approvals`, `dismiss_stale_reviews=true`,
`require_last_push_approval=true`, `required_conversation_resolution=true`, ordered
`allowed_merge_methods`,
`merge_queue_required=true`, `merge_queue_merge_method="MERGE"`,
`merge_queue_grouping_strategy="ALLGREEN"`, `merge_queue_minimum_entries_to_merge=1`,
`merge_queue_minimum_entries_to_merge_wait_minutes=0`,
`merge_queue_maximum_entries_to_merge=1`, `merge_queue_build_concurrency=1`, positive
`merge_queue_check_response_timeout_seconds`, `direct_merge_forbidden=true`,
`publication_validator_workflow_path=".github/workflows/publication-pr-validate.yml"`,
`publication_validator_workflow_sha256`, ordered
`publication_validator_triggers=["pull_request","merge_group:checks_requested"]`,
`publication_validator_job="publication-pr-validate"`,
`publication_validator_source_app_id`,
ordered `required_checks`, `main_bypass_actors=[]`,
`main_force_push_allowed=false`, `main_deletion_allowed=false`,
`publication_head_creation_restricted=true`, `publication_head_update_restricted=true`,
`publication_head_bypass_actor_kind="Integration"`, `publication_head_bypass_app_id`,
`publication_head_bypass_mode="always"`, `publication_head_update_allows_fetch_and_merge=false`,
`publication_head_force_push_allowed=false`,
`publication_head_deletion_allowed=false`, ordered `source_ruleset_ids`, and
`publication_branch_ruleset_policy_sha256`. Queue fields are literal REST projections:
`merge_queue_minimum_entries_to_merge_wait_minutes` equals
`merge_queue.parameters.min_entries_to_merge_wait_minutes`, `merge_queue_build_concurrency` equals
`merge_queue.parameters.max_entries_to_build`, and `merge_queue_check_response_timeout_seconds`
equals `60 * merge_queue.parameters.check_response_timeout_minutes`; no rounding or local default is
permitted. Each required-check entry has exactly `context`,
`source_kind="Integration"`, positive `source_app_id`, `strict=true`, and
`do_not_enforce_on_create=true`. The array has exactly one member:
`laconian/publication-pr-validate` from the frozen GitHub Actions App ID. The publisher-App
`laconian/publication-terminal-guard` is protocol evidence consumed by that validator, not a base
required-check context: GitHub evaluates base required checks on the temporary `merge_group` SHA,
where no publisher-App check is created. The publisher bypass App
ID equals the registered publisher App;
the head pattern matches only the deterministic publication/correction branches, and no publisher
grant applies to protected main. The policy domain is
`laconian-publication-branch-ruleset-policy-v1\n`, omitting only its final digest.
Protected-main merges are possible only through that one-entry queue; direct merge, jump/solo
override, auto-merge outside the queue and every human/App/team bypass are absent. The frozen
validator runs on both PR head and `merge_group.checks_requested`, resolves the selected PR/head,
verifies the intent-bound publisher eligibility/terminal-guard evidence and active campaign-state
authority, reads the current benchmark-authority denylist before deciding, and fails any PR or merge
group selected by a terminal tombstone. It publishes its required context on the event SHA: the PR
head for `pull_request` and the temporary merge-group SHA for `merge_group`.

`PublicationBranchRulesetObservationReceiptV1` has exactly `schema_version`, `repository_id`,
`policy_sha256`, ordered `first_read_raw_response_sha256s`, ordered
`first_read_request_receipt_sha256s`, ordered `second_read_raw_response_sha256s`, ordered
`second_read_request_receipt_sha256s`, `first_projection_sha256`, `second_projection_sha256`,
`first_merge_queue_configuration_sha256`, `second_merge_queue_configuration_sha256`,
`validator_workflow_blob_sha256`,
`observed_at`, and `observation_receipt_sha256`. Both fully paginated authenticated reads derive the
same exact policy projection, IDs, enforcement and empty main-bypass set; the projection equals the
sealed registry and `PublicationPlanV1`. Applicable-rule reads for both base and head prove every
source type is `Repository`; any organization/enterprise inherited ruleset makes this protocol
unsupported and fails publication-intent authorization before any branch/check/PR effect. Each repository-owned ruleset detail is fetched with the existing
security-attestor App installation's `Administration: write` permission because GitHub omits
`bypass_actors` without ruleset write access; the fixed job's endpoint policy nevertheless permits
only authenticated GETs and returns no token to general workflow steps. Its domain is
`laconian-publication-branch-ruleset-observation-receipt-v1\n`, omitting only its final digest.
Both reads also reproduce the exact repository merge-queue configuration and the C0-frozen
validator bytes/triggers/job/App. Missing queue requirement, non-`MERGE`, non-`ALLGREEN`, a minimum
or maximum other than one, nonzero minimum-entry wait, build concurrency other than one, any bypass/direct merge, missing
`merge_group:checks_requested`, or wrong workflow/App makes publication unsupported before intent.
Rollout additionally blocks unless the pilot proves that a one-entry MERGE group preserves the
required two-parent/tree admission contract and that a `LOCKED` queue entry remains observable
until an authenticated dequeue, failed required-check removal, or base-ref merge. To enable the
failed-run alternative, the pilot first records a one-PR LOCKED group with a successful frozen
Actions App/context check, installs a tombstone, and proves a post-CAS authority-reading failure on
the same merge-group SHA becomes merge-authoritative, invalidates the old success and removes/blocks
the entry before main advances. If any predicate fails, that alternative is unsupported and only
authenticated dequeue plus causal removal and post-action snapshots can establish the barrier.
The ordered Merkle root of the pre-effect and post-effect observation receipts is the
`publication_branch_ruleset_observation_root_sha256` bound by every eligibility/guard receipt.
Missing source-App binding, stale/disabled rules, an extra main bypass, a mismatched branch pattern,
or a publisher update grant on main fails closed.

Terminal-check delivery is also reconciled exactly. `PublicationTerminalGuardDeliveryResolutionV1`
has exactly `schema_version`, the same identity, `branch_name`, `head_oid`, the fixed context,
`guard_idempotency_key`, `guard_external_id`, ordered `superseded_check_run_ids`, ordered
`attempts`, nested exact `first_check_runs_observation: PublicationCheckRunsObservationV1`, nested
exact `second_check_runs_observation: PublicationCheckRunsObservationV1`, ordered
`lineage_guard_check_run_ids`, positive `designated_guard_check_run_id`,
`all_publisher_context_runs_completed_failure=true`,
`publisher_credential_disposition_sha256`, `delivery_ambiguity=false`, `recorded_at`, and
`guard_delivery_resolution_sha256`. Any registered-
publisher run for the head/context that is pending or not completed failure is terminated by a
`PublicationGuardUpdateAttemptV1`, with exactly
`schema_version`, positive `ordinal`, `operation="updated_to_failure"`, `request_id`,
`dispatch_state="not_dispatched"|"dispatched"`, `method="PATCH"`,
`endpoint_template="/repos/{owner}/{repo}/check-runs/{check_run_id}"`, positive
`target_check_run_id`, `request_payload_sha256`, closed `outcome`, nullable `response_status`,
nullable `safe_response_sha256`, nullable `resolved_check_run_id`, and
`transport_receipt_sha256`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`; its nested receipt is operation
`terminal_guard`, attempt kind `guard_update`, has the same ordinal and recomputed digest, and every
duplicated field byte-equals this attempt. Its PATCH body replaces `external_id` with the exact
`guard_external_id` and has exactly `status="completed"`, `conclusion="failure"`; it omits every
optional output/action/time field. After those updates, a final attempt may be
`PublicationGuardCreateAttemptV1` with the same fields except
`operation="created_failure"`, `method="POST"`,
`endpoint_template="/repos/{owner}/{repo}/check-runs"`, no target ID, and nested transport attempt
kind `guard_create`. Both use outcomes
`not_dispatched`, `definitely_rejected_no_side_effect`, `delivered_exact`,
or `non_2xx_resolved_exact`. Confirmed delivery requires 200 for
PATCH or 201 for POST. Definite rejection permits only 400, 401, 403, or 404 plus class-bound safe
proof; response-loss has null status; non-2xx resolved exact permits only 409 or 422 and exact
post-read adoption. Every possibly delivered attempt must resolve to its one exact check-run ID.
`not_dispatched` requires its namesake outcome and null status/safe-response/resolved ID;
`dispatched` requires another outcome. Safe response is nonnull only for definite rejection, and
resolved ID is nonnull exactly for a delivered/resolved outcome.
The create body has exactly `name`, `head_sha`, `external_id`, `status="completed"`, and
`conclusion="failure"`. PATCH hashes RFC 8785 over exactly its three listed fields; POST hashes it
over exactly its five listed fields.
`superseded_check_run_ids` is the ascending distinct update-target array. The designated guard ID
is the confirmed/adopted create result when present, otherwise the lowest-ordinal confirmed/adopted
update result, otherwise the smallest preexisting member already carrying the guard external ID.

Both nested post-dispatch observations fully paginate all publisher-App check suites and every check
run for this head and fixed context. Their lineage-ID array is the exact external-ID subset. They
use round one then round two, have distinct signed request/receipt roots, complete every first-round
response before the first second-round dispatch, and have byte-equal recomputed semantic-snapshot
digests.
Both have `publisher_context_state=all_failure`, the designated guard
ID is a lineage member and equals the receipt's check-run ID, and no success, pending, queued,
in-progress, neutral, skipped, or cancelled run remains. A nonlineage member may remain only as
completed failure, and at least one designated guard-lineage member exists. Thus `none`,
`exact_success`, and `conflicting` eligibility projections
are all terminalizable; only unresolved delivery is not. `recorded_at` equals the final observation source time. Its domain is
`laconian-publication-terminal-guard-delivery-resolution-v1\n`, omitting only its final digest.

`PublicationTerminalGuardReceiptV1` has exactly `schema_version`, the same campaign/registry/
publication/attempt/correction/bundle/plan/intent identity, `branch_name`, `head_oid`,
`check_context="laconian/publication-terminal-guard"`,
`guard_idempotency_key`, `guard_external_id`,
`actor: GitHubAppInstallationIdentityV1(role="publisher")`, positive `check_run_id`,
`status="completed"`, `conclusion="failure"`, `publication_branch_ruleset_policy_sha256`,
`publication_branch_ruleset_observation_root_sha256`, nullable
`superseded_merge_eligibility_receipt_sha256`, `eligibility_delivery_resolution_sha256`,
`guard_delivery_resolution_sha256`, `operation="updated_to_failure"|"created_failure"|
"adopted_failure"`, `request_receipts_root_sha256`,
`publisher_credential_disposition_sha256`,
`post_guard_check_run_verification_receipt_sha256`, `guarded_at`, and
`terminal_guard_receipt_sha256`. Its domain is
`laconian-publication-terminal-guard-receipt-v1\n`, omitting only its final digest. The ruleset
maps `updated_to_failure` only to a confirmed 200 PATCH, `created_failure` only to a confirmed 201
POST, and `adopted_failure` only to an exact response-loss/non-2xx/preexisting lineage adoption in
the delivery resolution; the receipt check-run ID is its designated guard ID.
Its post-guard hash names the exact `PublicationPostGuardVerificationReceiptV1`; that receipt's
identity, head/context, guard ID/external ID and delivery-resolution digest byte-equal this receipt.
The publisher credential digest byte-equals the delivery resolution's exact
`PublisherOperationCredentialDispositionV1(operation_kind="terminal_guard",
credential_status="minted_then_closed")`; `guarded_at` is the later of the verification time and
the token closure time. A not-minted guard disposition is therefore unconstructible.
The ruleset does not require this App-bound context on protected main. It permits no update to the
intent-bound branch/head except the publisher's preauthorized protocol, and no protocol-authorized
publisher action may restore a terminal guard to success. The guard is durable protocol evidence
read by the validator. The sole platform-enforced anti-merge gate is the GitHub Actions App check
`laconian/publication-pr-validate`, which runs on both PR-head and merge-group SHAs, re-reads the
authority denylist/terminal evidence, and fails every tombstoned selector. Closing a PR alone is not
treated as irreversible.

One terminal decision may have more than one possibly mergeable head. The class-bound
`PublicationTerminalGuardSetV1` has exactly `schema_version`, the same identity,
`branch_create_delivery_resolution_sha256`, `pr_create_delivery_resolution_sha256`, positive
`round_count`, ordered `rounds`, ordered `final_guarded_head_oids`,
`final_branch_observation_sha256`, `final_pr_marker_discovery_sha256`,
`final_check_runs_observation_set_sha256`, `conflicting_publication_objects_root_sha256`,
`publisher_credential_dispositions_root_sha256`, `guarded_at`, and
`terminal_guard_set_sha256`. Each `PublicationTerminalGuardRoundV1` has exactly `schema_version`,
the same identity, positive gapless `round_ordinal`, nested exact
`pre_guard_discovery_disposition: PublisherOperationCredentialDispositionV1(
operation_kind="terminal_guard_discovery")`, `pre_guard_discovery_disposition_sha256`,
`pre_guard_branch_observation_sha256`, nested
exact `pre_guard_pr_marker_discovery`, ordered `candidate_head_oids`, ordered
`eligibility_delivery_resolution_sha256s`, ordered `terminal_guard_delivery_resolutions`, ordered
`terminal_guard_receipts`, ordered `post_guard_check_run_verification_receipt_sha256s`,
nested exact `post_guard_discovery_disposition: PublisherOperationCredentialDispositionV1(
operation_kind="terminal_guard_discovery")`, `post_guard_discovery_disposition_sha256`,
`post_guard_branch_observation_sha256`, nested exact `post_guard_pr_marker_discovery`, ordered
`post_guard_candidate_head_oids`, `round_outcome="expanded"|"stable"`, and `round_sha256`, using
domain `laconian-publication-terminal-guard-round-v1\n` and omitting only its final digest.

Every persisted round has exactly two global read-only discovery dispositions. A pre-read which
already proves an authenticated merge and precedes every guard dispatch routes directly to the
existing merge-won terminal branch and constructs no guard round or guard set. The two operation idempotency keys are
`SHA256(UTF8("laconian-terminal-guard-discovery-key-v1\n") || CanonicalJSONV1({campaign_id,
publication_id,publication_attempt,correction_id,round_ordinal,stage}))`, with `stage` exactly `pre`
or `post`; no per-head guard key may own those reads. Each disposition's final projection contains
exactly its one branch observation followed by its one complete two-round marker discovery, uses
that round ordinal/stage on every wrapper/page/archive, and has terminal status
`discovery_complete`. Each candidate head instead has one distinct `terminal_guard` disposition
whose key is derived from the same identity, round ordinal and lowercase head OID; it owns only that
head's guard writes and post-write check inventories.

Before round one, all branch, PR and eligibility-success transports have terminated and no success-
check, branch-create, or PR-create dispatch remains authorized. Each candidate array is the sorted
unique complete union of the planned head, exact/conflicting branch observations, every possibly
delivered branch head, and every exact-marker PR head. Every candidate has one empty-or-resolved
eligibility resolution, one fully reconciled guard delivery whose transports terminate within that
round before its post-reads, one guard receipt, and one post-guard verification proving every
publisher-App/context run in the complete suite inventory is failure. Post-guard branch
and PR reads then recompute the union. Equality yields `stable`; a strict superset yields `expanded`
and the next round's pre-observations/candidates byte-equal that post projection. A missing head,
shrink, substitution, unresolved write, non-superset change, or more than eight rounds fails closed.
The final round is uniquely stable; its head array and post observations equal the set's three
final branch/PR fields. Its `final_check_runs_observation_set_sha256` names the exact guarded
`PublicationFinalCheckRunsObservationSetV1`: heads equal `final_guarded_head_oids`, verification
receipts equal the final round's post-guard receipt array, and final observations equal those
receipts' second observations. The credential root is the canonical aggregate of every discovery,
eligibility and guard disposition in exact round/stage/head order; the later unique terminal-
reconciliation-read disposition is
added by `PublicationNoLaterEffectsEvidenceV1` after the stable set. `guarded_at` equals its latest
authenticated source time. The set domain is
`laconian-publication-terminal-guard-set-v1\n`, omitting only its final digest. This pre-read,
guard, post-read loop has no hash cycle and cannot seal while a newly discovered head is unguarded.

#### Fenced publication-write ambiguity

The five ordinary publication delivery-resolution classes remain closed and retain
`delivery_ambiguity=false`. A response-lost write that is not ordered before an authoritative
server-side effect observation is never represented by `response_lost_resolved_*`, a
synthetic zero-effect disposition, or a no-later claim. It is represented only by the failure-only
grammar below.

In this subsection, **full publication identity** means the full containment publication identity
defined before the state event above. All ordinary initial/correction/bundle/phase rules continue
to apply. Any nested pre-containment source that still spells its field `authority_parent_oid`
must byte-equal the enclosing `source_authority_parent_oid`; post-CAS records instead use the
distinct `containment_authority_oid` and terminal events use their immediate accepted parent.

`PublicationWriteAmbiguitySubjectV1` has exactly, in order,
`schema_version="PublicationWriteAmbiguitySubjectV1"`, the full publication identity,
`operation_kind`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, positive `operation_request_ordinal`, positive
`source_attempt_ordinal`,
`attempt_kind`, `method`, `endpoint_template`,
`request_payload_sha256`, nullable `target_branch_name`, nullable
`target_head_oid`, nullable positive `target_check_run_id`, nullable positive
`target_pull_request_number`, `effect_class="merge_enabling"|"safety_monotone"`,
nested exact `request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`,
`operation_transport_receipt_sha256`,
`source_credential_disposition_sha256`,
`transport_outcome="response_lost_unresolved"`, nullable `response_status`,
nullable `response_completed_at`, nullable `resolved_object_id`, nullable
`resolved_object_root_sha256`, nullable `source_observation_sha256`,
`request_dispatched_at`, `attempt_terminal_at`, and
`write_ambiguity_subject_sha256`.

The operation is exactly `branch_create`, `merge_eligibility`,
`pull_request_create`, `terminal_guard`, or
`pull_request_close`; the first three map to `merge_enabling` and the last two
to `safety_monotone`. Target nullability is operation-derived: branch create names
branch/head; eligibility names head; PR create names branch/head and has null assigned PR number;
guard names head and names a check-run ID only for update; close names the exact PR number. The
nested receipts and the source disposition have the same full identity, operation/key/ordinals, request,
method/endpoint/payload/target and times; both digests recompute. The terminal receipt is dispatched,
has its exact nonnull start receipt, outcome `response_lost_unresolved`, and all five
response/result/source fields above null. This new outcome is legal only in this subject and in its
exact publisher transport projection; it is forbidden in every ordinary delivery resolution. The
subject domain is `laconian-publication-write-ambiguity-subject-v1\n`, omitting only its
final digest.

The source ordinal byte-equals the selected member of the corresponding write-attempt array and is
gapless within that source operation; the operation-request ordinal is the independently gapless
global dispatch ordinal for the credential attempt. Arbitrarily delayed delivery is part of the
failure model: for any of these five non-idempotent or safety-monotone writes, a lost request may be
delivered before read one, between the two reads, after read two, or after a proposed terminal
event. Therefore no later observation, including two equal observations, may transform
`response_lost_unresolved` into an ordinary exact/absent/closed resolution. Only the persistent
denylist, post-CAS merge barrier and sealed ambiguity-fence graph below can terminalize it. The sole
ordinary response-loss exception is immutable single-assignment branch-ref creation after the
reserved branch name is observed exact or occupied; that exception is not an ambiguity subject.

`PublicationWriteAmbiguitySetV1` has exactly
`schema_version="PublicationWriteAmbiguitySetV1"`, the full publication identity, positive
`subject_count`, ordered nested exact
`subjects: PublicationWriteAmbiguitySubjectV1`, ordered distinct
`merge_enabling_subject_sha256s`, ordered distinct
`safety_monotone_subject_sha256s`, and `write_ambiguity_set_sha256`. The
subject array is nonempty and sorted by
`(operation_rank,operation_idempotency_key,credential_attempt_ordinal,operation_request_ordinal)`,
where rank is branch, eligibility, PR create, guard, close. `subject_count` equals the array length.
The two digest arrays are exact stable
projections of that array, preserve its order, are disjoint, and their union is complete. Its domain
is `laconian-publication-write-ambiguity-set-v1\n`, omitting only its final digest.

`PublicationMergeDenylistEntryV1` has exactly
`schema_version="PublicationMergeDenylistEntryV1"`, the full publication identity,
`source_kind="ordinary_terminal_disposition"|"write_ambiguity"`, nullable
`publication_pr_terminal_disposition_sha256`, nullable `write_ambiguity_set_sha256`,
`reason="publication_terminal_disposition_fenced"|
"publication_write_delivery_ambiguous_fenced"`, ordered distinct `denied_branch_names`, ordered
distinct `denied_head_oids`, ordered distinct `denied_head_commit_trailers`, ordered distinct
`denied_pull_request_node_ids`, ordered distinct `denied_pull_request_markers`,
ordered distinct positive `denied_pull_request_numbers`, ordered distinct
`denied_operation_idempotency_keys`, `created_at`, and
`merge_denylist_entry_sha256`. Names, markers and keys use ascending UTF-8 byte order, OIDs
ascending lowercase hexadecimal and PR numbers ascending numeric order. The arrays are the complete
nonempty union derivable from the plan, ambiguity subjects and already authenticated candidate
observations; a PR number/node may be absent because a late PR has not yet been assigned. The frozen
validator denies iff any constituent PR has a denied node ID/number, same-repository head branch,
head OID, exact canonical marker line, or exact canonical head-commit trailer. Operation keys are
audit-only and never claimed as a GitHub match source. Future intent admission rejects reuse of a
denied branch/head/marker/trailer. The OR predicate and one-entry constituent resolution are C0-
frozen. Exactly one
source digest is nonnull. The ordinary source is only a fully built exact
`PublicationPRTerminalDispositionV1(outcome="no_pr"|"closed")` and derives reason
`publication_terminal_disposition_fenced`; the ambiguity source is only the exact failure set and
derives reason `publication_write_delivery_ambiguous_fenced`. The entry
domain is `laconian-publication-merge-denylist-entry-v1\n`, omitting only its digest.

`PublicationMergeDenylistV1` has exactly
`schema_version="PublicationMergeDenylistV1"`, `campaign_id`,
`campaign_registry_sha256`, `repository_id`, nullable
`predecessor_merge_denylist_root_sha256`, nonnegative `entry_count`, ordered
nested exact `entries: PublicationMergeDenylistEntryV1`, and
`publication_merge_denylist_root_sha256`. Preflight installs the canonical empty record
with null predecessor, count zero and an empty array; every successor reproduces every prior entry
byte-for-byte, sets its predecessor to the prior root, increments the count and appends exactly one
new entry. No entry is removed or rewritten. Its domain is
`laconian-publication-merge-denylist-v1\n`, omitting only its final root.

`PublicationMergeQueuePreflightObservationV1` has exactly
`schema_version="PublicationMergeQueuePreflightObservationV1"`, the full publication
identity, `source_kind="ordinary_terminal_disposition"|"write_ambiguity"`,
`source_sha256`,
`operation_kind="terminal_merge_barrier_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`, positive `pull_request_number`,
`repository_node_id`, positive `repository_database_id`, `pull_request_node_id`,
`pull_request_state="open"|"closed"|"merged"`, `merged`, nullable
`merged_at`, nullable `merge_oid`, `base_oid`, `head_oid`,
`observed_main_oid`, nullable nested exact `merge_queue_entry`,
`graphql_document_sha256`, `graphql_variables_sha256`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `response_status=200`,
`graphql_errors=[]`, `raw_response_sha256`,
`canonical_response_sha256`, nested exact `raw_response_blob`,
`publisher_credential_subject_sha256`, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, `observed_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and
`merge_queue_preflight_observation_sha256`. Its state/merge/nullability, queue-entry
projection, raw archive, query/variables, dispatch bijection, signature omission and canonical
mapping rules are byte-for-byte those of `PublicationMergeQueueObservationV1` below.
`source_sha256` equals the selected terminal disposition or ambiguity set and contains no
preflight/intent/successor-state digest, so the graph is acyclic. Its record/signature domains are
`laconian-publication-merge-queue-preflight-observation-v1\n` and
`laconian-publication-merge-queue-preflight-observation-signature-v1\n`.

`PublicationProtectedMainObservationV1` has exactly
`schema_version="PublicationProtectedMainObservationV1"`, the full publication identity,
`observation_phase="pre_containment"|"post_action_first"|"post_action_second"`, nullable
`source_kind="ordinary_terminal_disposition"|"write_ambiguity"`, nullable
`source_sha256`, nullable `terminal_containment_intent_sha256`, nullable
`containment_authority_oid`, nullable `successor_merge_denylist_root_sha256`,
`operation_kind="terminal_merge_barrier_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`, `method="GET"`,
`endpoint_template="/repos/{owner}/{repo}/git/ref/heads/main"`,
`observed_main_oid`, `response_status=200`, `raw_response_sha256`,
`canonical_response_sha256`, nested exact `raw_response_blob`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `observed_at`,
`publisher_credential_subject_sha256`, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `protected_main_observation_sha256`. Pre-
containment requires source kind/digest nonnull and all three post-CAS fields null; either post phase
requires the reverse. The ref target is a commit and supplies the lowercase OID. Raw archive,
append-before-send bijection, one-way terminal-wrapper link, chronology and exact signature/digest
omissions are identical to other publisher non-page reads. Its domains are
`laconian-publication-protected-main-observation-signature-v1\n` and
`laconian-publication-protected-main-observation-v1\n`.

`PublicationTerminalContainmentPreflightV1` has exactly
`schema_version="PublicationTerminalContainmentPreflightV1"`, the full publication identity,
`containment_kind="ordinary_terminal_disposition"|"write_ambiguity"`, nullable
`publication_pr_terminal_disposition_sha256`, nullable
`write_ambiguity_set_sha256`, nested exact
`protected_main_observation: PublicationProtectedMainObservationV1(
observation_phase="pre_containment")`,
`protected_main_observation_sha256`, nested exact
`marker_discovery: PublicationPRMarkerDiscoveryV1`,
`marker_discovery_sha256`, nested exact
`pre_containment_queue_inventory: PublicationMergeQueueInventoryObservationV1(
observation_scope="pre_containment",observation_stage="pre_containment",snapshot_ordinal=0)`,
`pre_containment_queue_inventory_sha256`, ordered distinct positive `candidate_pull_request_numbers`,
ordered nested exact
`queue_observations: PublicationMergeQueuePreflightObservationV1`, ordered
matching `queue_observation_sha256s`,
ordered distinct positive `merged_candidate_pull_request_numbers`,
`merge_state="all_unmerged"|"merge_observed"`,
`observed_main_oid`, `publication_branch_ruleset_observation_root_sha256`,
`observed_at`, and `containment_preflight_sha256`. Exactly one source digest is
nonnull and equals the selected source. Candidate numbers are the ascending unique union of every
source candidate, fresh complete marker discovery and every denylist-affected global queue entry;
queue observations form a bijection in
that order. The protected-main observation supplies `observed_main_oid`. `all_unmerged` requires an
empty merged array; `merge_observed` requires it to be the exact positive subset of merged queue/
marker observations. An ordinary fully resolved source that observes a merge still installs the
containment CAS before failed admission so every remaining candidate is fenced; it never skips the
persistent denylist. A write-ambiguity source does the same for the whole set, preserves every
immutable merge, and fences every remaining unmerged affected candidate. Its domain is
`laconian-publication-terminal-containment-preflight-v1\n`, omitting only its final digest.

`PublicationPreContainmentTerminalRouteV1` is the cycle-free route discriminator built
before containment. It has exactly `schema_version="PublicationPreContainmentTerminalRouteV1"`,
the full publication identity,
`source_kind="ordinary_terminal_disposition"|"write_ambiguity"`, `source_sha256`,
`route_kind="initial_complete_stop"|"initial_complete_plan_invalidation"|
"initial_invalid_plan_invalidation"|"correction_unmerged_invalidation"`,
`source_failure_code="publication_lineage_failure"|"base_moved"|"head_moved"|"plan_mismatch"|
"closed_unmerged"|"terminal_invalid_lineage"|"protocol_authority_drift"|
"credential_exposure"|"publication_reconciliation_unavailable"|
"publication_write_delivery_ambiguous_fenced"`,
nullable `credential_exposure_route_state="active_pending"|"accepted_supplement"`,
`source_failure_evidence_root_sha256`, `premerge_terminal_event_type="PERMANENT_STOP"|
"COMPLETE_PUBLICATION_PLAN_INVALIDATED"|"INVALID_PUBLICATION_PLAN_INVALIDATED"|
"CORRECTION_INVALIDATED"`, `premerge_terminal_reason_or_outcome`, `created_at`, and
`pre_containment_terminal_route_sha256`. The ordinary source names an exact
`no_pr|closed` disposition. `publication_lineage_failure` names a pre-existing exact
`OrdinaryStopEvidenceV1(reason="publication_lineage_failure")` and maps only to
`initial_complete_stop/PERMANENT_STOP/publication_lineage_failure`. The five plan-failure
codes name respectively the already authenticated base observation, branch observation,
plan-verification receipts, terminal disposition, or lineage-verification receipts and map:
complete bundle to `initial_complete_plan_invalidation/COMPLETE_PUBLICATION_PLAN_INVALIDATED`,
invalid-prefix to
`initial_invalid_plan_invalidation/INVALID_PUBLICATION_PLAN_INVALIDATED`, and correction to
`correction_unmerged_invalidation/CORRECTION_INVALIDATED/unmerged_invalid`.
`publication_write_delivery_ambiguous_fenced` names only the ambiguity set and maps complete
to `initial_complete_stop/PERMANENT_STOP`, invalid-prefix to
`initial_invalid_plan_invalidation/INVALID_PUBLICATION_PLAN_INVALIDATED`, and correction to
`correction_unmerged_invalidation/CORRECTION_INVALIDATED/fenced_write_ambiguity`.
`protocol_authority_drift` names the exact pre-containment `ProtocolAuthorityDriftEvidenceV1` and
maps complete to `initial_complete_stop/PERMANENT_STOP/protocol_authority_drift`, invalid-prefix
to `initial_invalid_plan_invalidation/INVALID_PUBLICATION_PLAN_INVALIDATED/
protocol_authority_drift`, and correction to
`correction_unmerged_invalidation/CORRECTION_INVALIDATED/unmerged_invalid` with
`invalidation_cause=protocol_authority_drift`. `credential_exposure` has two disjoint forms.
Complete initial publication and correction require `credential_exposure_route_state=active_pending`
and name the exact active `CredentialExposurePendingV1` plus completed effect-prefix root; their
terminal events atomically consume that exposure chain. Invalid-prefix publication requires
`credential_exposure_route_state=accepted_supplement`, an exact already-accepted
`CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED` event and `CredentialExposureSupplementV1`, and both
active exposure fields null before containment starts; its later plan-invalidation record copies
the supplement/origin/effect roots but does not consume them a second time. The active form maps
complete to `initial_complete_stop/PERMANENT_STOP/credential_exposure` and correction to
`correction_unmerged_invalidation/CORRECTION_INVALIDATED/unmerged_invalid` with
`invalidation_cause=credential_exposure`; the accepted-supplement form maps only to
`initial_invalid_plan_invalidation/INVALID_PUBLICATION_PLAN_INVALIDATED/credential_exposure`.
Every non-exposure code requires `credential_exposure_route_state=null`.
`publication_reconciliation_unavailable` names the exact
sealed `PublisherReconciliationUnavailableReceiptV1`, its disposition-set root, and empty signed
release-authorization-ledger root; it maps complete to
`initial_complete_stop/PERMANENT_STOP/publication_reconciliation_unavailable`, invalid-prefix to
`initial_invalid_plan_invalidation/INVALID_PUBLICATION_PLAN_INVALIDATED/
publication_reconciliation_unavailable`, and correction to
`correction_unmerged_invalidation/CORRECTION_INVALIDATED/reconciliation_unavailable`. These three
routes still require an independently authenticated exact `no_pr|closed` terminal disposition;
their source evidence root is the canonical Merkle root of the exact named evidence tuple. No source
evidence in this record contains a containment intent, accepted CAS receipt, barrier, no-later root,
terminal event or successor OID. The broker reconstructs the one literal row from the source
identity/bundle/phase/cause; a caller-supplied alternative is invalid. Its domain is
`laconian-publication-pre-containment-terminal-route-v1\n`, omitting only its digest.

`PublicationTerminalContainmentIntentV1` has exactly
`schema_version="PublicationTerminalContainmentIntentV1"`, the full publication identity,
`containment_kind="ordinary_terminal_disposition"|"write_ambiguity"`,
`expected_authority_oid`, positive `expected_transition_number`, nested exact
nullable `publication_pr_terminal_disposition: PublicationPRTerminalDispositionV1`, nullable
`publication_pr_terminal_disposition_sha256`, nullable nested exact
`write_ambiguity_set: PublicationWriteAmbiguitySetV1`, nullable `write_ambiguity_set_sha256`, nested exact
`containment_preflight: PublicationTerminalContainmentPreflightV1`,
`containment_preflight_sha256`, `containment_main_oid`, nested exact
`predecessor_merge_denylist: PublicationMergeDenylistV1`,
`predecessor_merge_denylist_root_sha256`, nested exact
`successor_merge_denylist: PublicationMergeDenylistV1`,
`successor_merge_denylist_root_sha256`,
`publication_branch_ruleset_policy_sha256`, `workflow_root`, nested exact
`premerge_terminal_route: PublicationPreContainmentTerminalRouteV1`,
`premerge_terminal_route_sha256`, `premerge_terminal_event_type`,
`merge_won_terminal_event_type`, `created_at`, and
`terminal_containment_intent_sha256`. The expected OID equals
`source_authority_parent_oid`; the successor denylist is the one legal append containing this
matching containment entry. Exactly one nested source/digest pair is nonnull and byte-equals that
entry. The ordinary pair is an exact `no_pr|closed` disposition and the ambiguity pair is the exact
failure set. The nested route has the same source kind/digest and its duplicated digest and premerge
event recompute. The merge-won event is uniquely phase-derived: initial complete maps to
`RESULT_MERGE_INVALIDATED`, initial invalid-prefix to
`INVALID_PREFIX_MERGE_INVALIDATED`, and correction to
`CORRECTION_INVALIDATED` with `publication_outcome=merged_invalid`. The two event
fields cannot be caller-selected. The preflight repeats the same source pair, identity and ruleset root;
`containment_main_oid` equals its protected-main OID. CAS admission rechecks that ruleset
and denies any later constructive dispatch. The intent contains no accepted mutation receipt, new authority OID, queue
observation, fence run, broker finality, or terminal-event field. Its domain is
`laconian-publication-terminal-containment-intent-v1\n`, omitting only its final digest.

Every field named `containment_authority_mutation_receipt` in this specification is the same exact
join, never a generic campaign-event receipt. It is
`AuthorityMutationReceiptV1(mutation_kind="campaign_event",
event_type="PUBLICATION_TERMINAL_CONTAINMENT_STARTED")`; its event digest names the exact start
event that nests this intent and its signed containment-start prefix pair, and its candidate commit
and observed-after OIDs both equal `containment_authority_oid`. Its predecessor/successor
publication denylist roots equal the intent's predecessor/successor roots, and its predecessor/
successor active containment roots are exactly `null -> terminal_containment_intent_sha256`.
Start-event `occurred_at` equals both signed start-prefix observation times and is no later than the
receipt `started_at <= completed_at`. Every post-CAS read, dequeue, rerun, timeline query, barrier
dispatch, fence attachment and terminal-finality observation occurs at or after receipt completion.
Identity, expected old/source OID, transition number, event member manifest and duplicated receipt
digest all recompute. A receipt for another event, candidate, root transition, intent or time order
is invalid everywhere, including through a nested barrier, fenced record or merge-won object.

`PublicationMergeQueueObservationV1` has exactly
`schema_version="PublicationMergeQueueObservationV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`,
`operation_kind="terminal_merge_barrier_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`,
`observation_phase="after_intent_pre_action"|"after_action_first"|"after_action_second"`,
`observation_stage="containment_pre_action"|"containment_first"|"containment_second"`,
`containment_snapshot_ordinal=0|1|2`,
positive `observation_ordinal`, positive `pull_request_number`,
`repository_node_id`, positive `repository_database_id`, `pull_request_node_id`,
`pull_request_state="open"|"closed"|"merged"`,
`merged`, nullable `merged_at`, nullable `merge_oid`, `base_oid`, `head_oid`,
`observed_main_oid`, nullable nested exact `merge_queue_entry`,
`graphql_document_sha256`, `graphql_variables_sha256`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `response_status=200`,
`graphql_errors=[]`, `raw_response_sha256`,
`canonical_response_sha256`, nested exact `raw_response_blob`,
`publisher_credential_subject_sha256`, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, `observed_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `merge_queue_observation_sha256`. Phase, stage and snapshot are a literal bijection:
`after_intent_pre_action/containment_pre_action/0`,
`after_action_first/containment_first/1`, or
`after_action_second/containment_second/2`; no cross-product is valid. A nonnull
queue entry has exactly `entry_id`, `merge_queue_id`, `enqueued_at`,
`state="AWAITING_CHECKS"|"LOCKED"|"MERGEABLE"|"QUEUED"|"UNMERGEABLE"`,
nullable `base_commit_oid`, nullable `head_commit_oid`, nonnegative `position`,
`jump`, and `solo`; null means that exact PR is not a queue member. The full
`pull_request_state="merged"` iff `merged=true`, `merged_at` and `merge_oid` are nonnull; open or
closed requires `merged=false` and both fields null. `repository_database_id` byte-equals the sealed
numeric `repository_id`; the opaque node ID is preserved separately. `raw_response_blob` has exactly `path`, `sha256`, and `raw_bytes_base64`;
decoded bytes reproduce `raw_response_sha256`, and path is
`publication-merge-queue/<SHA256(UTF8(request_id))>.response`. Identity,
operation/key/ordinals, request, token subject and times byte-equal the nested dispatch receipt. The
separately inventoried terminal wrapper points one-way to this observation digest in
`source_observation_sha256`; the observation does not name the wrapper, so the graph is acyclic.
Signature and record domains are
`laconian-publication-merge-queue-observation-signature-v1\n` and
`laconian-publication-merge-queue-observation-v1\n`; the signature preimage omits exactly
the signature and final digest and the record digest omits exactly the final digest.

The observation is the decoded and signed result of exactly one `POST /graphql` whose
UTF-8 query bytes are C0-frozen as:

~~~graphql
query PublicationMergeQueueState($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){id databaseId ref(qualifiedName:"refs/heads/main"){target{... on Commit{oid}}} pullRequest(number:$number){id number state merged mergedAt mergeCommit{oid} baseRefOid headRefOid mergeQueueEntry{id enqueuedAt state position jump solo baseCommit{oid} headCommit{oid} mergeQueue{id}}}}}
~~~

Variables are exactly `{owner: nonempty ASCII GitHub owner, repo: nonempty ASCII GitHub
repository name, number: integer 1..2^31-1}`; no other variable, field or fragment is legal.
Repository/PR IDs, ref OID, state/merge and queue projections are total mappings from that one
response. A missing PR, null repository/ref, GraphQL error, malformed/partial body or inconsistent
OID fails the read and cannot become an observation.

`PublicationMergeQueueInventoryPageReceiptV1` has exactly
`schema_version="PublicationMergeQueueInventoryPageReceiptV1"`, the full publication
identity, `observation_scope="pre_containment"|"post_containment"`, nullable
`source_kind`, nullable `source_sha256`, nullable
`terminal_containment_intent_sha256`, nullable `containment_authority_oid`, nullable
`successor_merge_denylist_root_sha256`,
`operation_kind="terminal_merge_barrier_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`,
`observation_stage="pre_containment"|"post_containment_pre_action"|
"post_containment_first"|"post_containment_second"`, `snapshot_ordinal=0|1|2`,
`inventory_pass_ordinal=1|2`, positive `page_ordinal`, nullable `after_cursor`,
`graphql_document_sha256`, `graphql_variables_sha256`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `response_status=200`,
`graphql_errors=[]`, `repository_node_id`, positive
`repository_database_id`, `observed_main_oid`, `merge_queue_id`,
nonnegative `total_count`, `has_next_page`, nullable `end_cursor`,
`position_base=0|1`, ordered nested exact
`entries: PublicationMergeQueueInventoryEntryV1`, `raw_response_sha256`,
`canonical_response_sha256`, nested exact `raw_response_blob`,
`publisher_credential_subject_sha256`, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, `observed_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `inventory_page_receipt_sha256`. Each
`PublicationMergeQueueInventoryEntryV1` has exactly
`schema_version="PublicationMergeQueueInventoryEntryV1"`,
`entry_id`, `enqueued_at`, `state`, nonnegative
`position`, `jump`, `solo`, nullable `base_commit_oid`,
nullable `head_commit_oid`, `pull_request_node_id`, positive
`pull_request_number`, `pull_request_state="open"|"closed"|"merged"`,
`merged`, nullable `merged_at`, nullable `merge_oid`,
`base_ref_name`, `base_ref_oid`, `head_ref_name`,
`head_ref_oid`, nullable `head_commit_message_sha256`, nullable
`head_commit_trailer`, `body_sha256`, and `canonical_entry_sha256`.
Pre-containment requires source fields nonnull, all post-CAS fields null, its namesake stage and
`snapshot_ordinal=0`. Post-containment requires the reverse: pre-action maps to zero, first to one
and second to two. Operation key/scope distinguish the two ordinal-zero reads.
The GraphQL `databaseId` field is nullable on the wire. Rollout nevertheless requires it to
be a positive integer equal to the sealed numeric `repository_id`; null is an explicit
unsupported-platform failure, never substituted with the opaque node ID.
Null head commit requires both message fields null and makes that entry affected but ineligible for
a barrier until a later complete page resolves it. A nonnull head commit preserves the exact
message hash and projects the one canonical Laconian trailer or null; the raw page proves parsing.

The fixed UTF-8 query is:

~~~graphql
query PublicationMainMergeQueue($owner:String!,$repo:String!,$after:String){repository(owner:$owner,name:$repo){id databaseId ref(qualifiedName:"refs/heads/main"){target{... on Commit{oid}}} mergeQueue(branch:"main"){id entries(first:100,after:$after){totalCount pageInfo{hasNextPage endCursor} nodes{id enqueuedAt state position jump solo baseCommit{oid} headCommit{oid message} pullRequest{id number state merged mergedAt mergeCommit{oid} baseRefName baseRefOid headRefName headRefOid body}}}}}}
~~~

Variables are exactly `{owner,repo,after}`, with `after=null` on page one and
the prior nonnull end cursor thereafter. Repository/ref/queue/pageInfo and every node/PR are nonnull;
the nullable database ID is subject to the rollout gate above. Page ordinals and cursors are
gapless, total count is constant, the final page has `hasNextPage=false`, and aggregate
cardinality equals total count. Within a pass, entry IDs and PR node IDs/numbers are independently
unique, positions are unique and exactly the contiguous interval
`position_base..position_base+total_count-1` in aggregate queue order, and the base is the
single value frozen by the pilot and policy root. Every raw page is archived;
null/inconsistent pagination fails closed. The page signature preimage is
`UTF8("laconian-publication-merge-queue-inventory-page-signature-v1\n") ||
CanonicalJSONV1(page without exactly broker_signature_base64url and
inventory_page_receipt_sha256)`; the record digest uses
`laconian-publication-merge-queue-inventory-page-v1\n` and omits exactly its final digest.

`PublicationMergeQueueInventoryObservationV1` has exactly
`schema_version="PublicationMergeQueueInventoryObservationV1"`, the same scope/source-or-
intent identity, `observation_stage`, `snapshot_ordinal=0|1|2`,
`inventory_pass_count=2`, positive `pages_per_pass`, positive `page_count`,
`position_base=0|1`, ordered nested exact
`pages: PublicationMergeQueueInventoryPageReceiptV1`, ordered exact
`all_entries: PublicationMergeQueueInventoryEntryV1`, ordered `affected_entry_ids`,
`publication_merge_denylist_root_sha256`, `observed_main_oid`,
`canonical_inventory_state_sha256`, `raw_archive_root_sha256`, `observed_at`, and
`inventory_observation_sha256`. Pages satisfy the complete chain above, are ordered by
`(inventory_pass_ordinal,page_ordinal)`,
`page_count=2*pages_per_pass`, and form two independently complete passes. Their operation
identity, stage, snapshot, key, policy root and position base are byte-equal. The second pass begins
only after every first-pass request terminates. Each pass produces exactly the same ordered
`all_entries` canonical bytes, total count, main OID, queue ID, final cursor semantics and
canonical inventory digest; otherwise no observation exists. The published `all_entries`
array is that common typed aggregate, with a bijection to every page member of either pass and no
extra or omitted entry. Affected IDs are the exact entry subset selected by the denylist's frozen
OR predicate; filtering never removes entries from the archive. A pre-containment observation uses
the already constructed candidate successor denylist root containing the source entry, not the
installed predecessor root. Entry selectors derive only from plan/source evidence that precedes
preflight; newly discovered PR numbers/nodes remain preflight/barrier evidence and do not
retroactively rewrite the entry. `raw_archive_root_sha256` is SHA-256 of
`UTF8("laconian-publication-merge-queue-inventory-raw-archive-v1\n")` followed by the
length-prefixed decoded raw page bytes in canonical page order. The entry domain is
`laconian-publication-merge-queue-inventory-entry-v1\n` and the observation domain is
`laconian-publication-merge-queue-inventory-observation-v1\n`; each omits exactly its
own final digest.

`PublicationMergeQueueTimelinePageReceiptV1` has exactly
`schema_version="PublicationMergeQueueTimelinePageReceiptV1"`, the full publication
identity, `terminal_containment_intent_sha256`, `containment_authority_oid`,
positive `pull_request_number`, `pull_request_node_id`,
`operation_kind="terminal_merge_barrier_read"`, `operation_idempotency_key`,
positive `credential_attempt_ordinal`, positive `operation_request_ordinal`,
positive `page_ordinal`, nullable `after_cursor`,
`graphql_document_sha256`, `graphql_variables_sha256`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `response_status=200`,
`graphql_errors=[]`, nonnegative `total_count`, `has_next_page`,
nullable `end_cursor`, ordered nested exact `events`,
`raw_response_sha256`, `canonical_response_sha256`, nested exact
`raw_response_blob`, `publisher_credential_subject_sha256`, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `timeline_page_receipt_sha256`. Events are
a strict discriminated union. Every member has `event_kind="added_to_merge_queue"|
"removed_from_merge_queue"|"merged"`, `event_node_id`, `occurred_at`,
nullable nested exact `actor` and `canonical_event_sha256`; actor, when present,
has exactly `typename` and nullable `login`, matching the fixed query without an invented node ID.
Added has nonnull
`queue_id` and every remove/merge-only field null. Removed has nullable wire
`queue_id`, nullable `before_commit_oid`, nullable `reason` and all
merge-only fields null. Merged has null queue/before/reason, nullable `commit_oid`, nullable
`merge_ref_name`. A removal selected as causal barrier
evidence additionally requires a nonnull actor login, queue ID, reason and an exact earlier matching
added event with the same queue ID; a
merge selected for failed admission requires nonnull commit OID.

The fixed query is:

~~~graphql
query PublicationPRMergeQueueTimeline($owner:String!,$repo:String!,$number:Int!,$after:String){repository(owner:$owner,name:$repo){databaseId pullRequest(number:$number){id timelineItems(first:100,after:$after,itemTypes:[ADDED_TO_MERGE_QUEUE_EVENT,REMOVED_FROM_MERGE_QUEUE_EVENT,MERGED_EVENT]){totalCount pageInfo{hasNextPage endCursor} nodes{__typename ... on AddedToMergeQueueEvent{id createdAt actor{__typename login} mergeQueue{id}} ... on RemovedFromMergeQueueEvent{id createdAt actor{__typename login} beforeCommit{oid} mergeQueue{id} reason} ... on MergedEvent{id createdAt actor{__typename login} commit{oid} mergeRefName}}}}}}
~~~

Variables/cursor rules and dispatch-wrapper bijection are identical to one complete inventory pass;
page/cardinality mismatch fails closed. The page signature is over
`UTF8("laconian-publication-merge-queue-timeline-page-signature-v1\n") ||
CanonicalJSONV1(page without exactly broker_signature_base64url and
timeline_page_receipt_sha256)`, and the record domain is
`laconian-publication-merge-queue-timeline-page-v1\n` omitting only its final digest.
`PublicationMergeQueueTimelineReceiptV1` has exactly
`schema_version="PublicationMergeQueueTimelineReceiptV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`, positive
`pull_request_number`, `pull_request_node_id`,
`operation_kind="terminal_merge_barrier_read"`, `operation_idempotency_key`,
positive `credential_attempt_ordinal`, positive `page_count`, ordered nested exact
`page_receipts: PublicationMergeQueueTimelinePageReceiptV1`, ordered nested exact
`events`, `pagination_complete=true`, `raw_archive_root_sha256`,
`observed_at`, and `timeline_receipt_sha256`. Pages/cursors are gapless and
every page repeats those exact identity/key/PR fields. The aggregate preserves all three event kinds
in API order and is a bijection to all page members. `raw_archive_root_sha256` is SHA-256 of
`UTF8("laconian-publication-merge-queue-timeline-raw-archive-v1\n")` followed by the
length-prefixed decoded raw page bytes in page order. A delivery-ambiguous dequeue or failed-fence
removal is causally settled only by an exact added→post-action removed pair for that PR/queue,
followed by two global inventories with no affected entry; a merged event routes failed admission.
The selected pair's queue IDs, actor login and removal reason are nonnull and equal where
applicable; no other timeline event may be silently discarded. Its domain is
`laconian-publication-merge-queue-timeline-receipt-v1\n`, omitting exactly its final digest.

`PublicationMergeQueueDequeueTargetProofV1` has exactly
`schema_version="PublicationMergeQueueDequeueTargetProofV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, nested exact
`pre_action_queue_observation: PublicationMergeQueueObservationV1(
observation_phase="after_intent_pre_action")`,
`pre_action_queue_observation_sha256`, positive `target_pull_request_number`,
`target_pull_request_node_id`, `target_merge_queue_entry_id`, positive
`action_ordinal`, `constructed_at`, and `dequeue_target_proof_sha256`. The
observation is unmerged with a nonnull entry; every PR/node/entry/head/intent/CAS field byte-equals
the proof and current active authority/denylist read. It contains no dispatch, action outcome,
barrier or finality root. Its domain is
`laconian-publication-merge-queue-dequeue-target-proof-v1\n`, omitting only its digest.

`PublicationMergeQueueDequeueAttemptV1` has exactly
`schema_version="PublicationMergeQueueDequeueAttemptV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`,
`operation_kind="terminal_merge_barrier_dequeue"`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, positive `operation_request_ordinal`, positive `ordinal`,
`client_mutation_id`, `request_id`,
`dispatch_state="not_dispatched"|"dispatched"`, `method="POST"`,
`endpoint_template="/graphql"`, `graphql_document_sha256`,
`graphql_variables_sha256`, `request_payload_sha256`,
nested exact `target_authorization_proof: PublicationMergeQueueDequeueTargetProofV1`,
`target_authorization_proof_sha256`,
positive `target_pull_request_number`, `target_pull_request_node_id`, nullable
`target_merge_queue_entry_id`,
`outcome="not_dispatched"|"dequeued_exact"|"delivery_ambiguous"|"definite_rejection"`,
nullable `response_status`, nullable `graphql_errors_sha256`, nullable
`returned_client_mutation_id`, nullable `returned_merge_queue_entry_id`, nullable
`returned_pull_request_node_id`, nullable positive `returned_pull_request_number`, nullable
`raw_response_sha256`, nullable `canonical_response_sha256`, nullable nested exact
`raw_response_blob`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1(
operation_kind="terminal_merge_barrier_dequeue")`, `transport_receipt_sha256`, and
`merge_queue_dequeue_attempt_sha256`. `dequeued_exact` requires dispatch,
status 200, the canonical empty-error hash, echoed client mutation ID, exact returned entry/PR
node/number and nonnull archived raw/canonical response hashes. Every dispatched attempt has a
nonnull target entry ID. `delivery_ambiguous` covers response loss with null status/response fields
and any received response not proving exact success or definite pre-mutation rejection; received
bytes and their blob/hash are nonnull. Definite rejection is only a class-bound pre-mutation
401/403/404 and archives its body. HTTP 200 with errors, null/partial data or identity mismatch is
delivery-ambiguous and never definite. The raw blob has exactly `path`, `sha256` and
`raw_bytes_base64`, and all response/status/hash fields byte-equal the generic terminal transport
receipt. The
client mutation ID recomputes solely from this record's intent, PR node and ordinal. Its domain is
`laconian-publication-merge-queue-dequeue-attempt-v1\n`, omitting only its final digest.
The nested target proof digest byte-equals the generic dispatch/terminal wrapper
`target_authorization_proof_sha256` and all duplicated target fields. A not-dispatched attempt still
preserves the proof but has no start receipt.

The dequeue mutation UTF-8 bytes are C0-frozen as:

~~~graphql
mutation PublicationDequeue($id:ID!,$clientMutationId:String!){dequeuePullRequest(input:{id:$id,clientMutationId:$clientMutationId}){clientMutationId mergeQueueEntry{id enqueuedAt state position jump solo baseCommit{oid} headCommit{oid} mergeQueue{id} pullRequest{id number}}}}
~~~

Variables are exactly `{id: target_pull_request_node_id, clientMutationId:
"publication-dequeue/" + lowercase_hex(SHA256(UTF8("publication-dequeue-v1") || BYTE(0x00) ||
HEXDECODE(terminal_containment_intent_sha256) || BYTE(0x00) ||
UTF8(target_pull_request_node_id) || BYTE(0x00) || U64BE(ordinal)))}`. The ID is the PullRequest node ID required by
`DequeuePullRequestInput.id`, never the queue-entry ID. Query and mutation bodies are
canonical RFC 8785 `{query,variables}` JSON with content type
`application/json` and no batching. Every request has append-before-send and one terminal
receipt; malformed/partial bodies are archived and fail closed.

Required-check fence evidence is a closed typed aggregate rather than a bag of response blobs.
`PublicationMergeFenceWorkflowRunObservationV1` has exactly `schema_version`, the full publication
identity, intent/CAS/denylist roots, operation key/credential/request ordinals,
`evidence_kind="rerun_source_success"|"post_containment_fence_failure"`,
`workflow_run_id`, positive `run_attempt`, positive `check_suite_id`, frozen workflow
path/ref/commit/blob/root,
`event="merge_group"`, `action="checks_requested"`, `merge_group_ref`, base/head OIDs, ordered
exact one-member PR identity, `status="completed"`, `conclusion="success"|"failure"`, requested/started/
completed times, actor/triggering-actor identities, method/endpoint/request IDs and times,
`response_status=200`, canonical/raw response hashes and blob, credential subject and dispatch receipt, signing
identity/signature, and `workflow_run_observation_sha256`.
The workflow response is the sole source of `check_suite_id`; a caller-provided suite or run ID is
invalid.

`PublicationMergeFenceCheckRunPageReceiptV1` has exactly `schema_version`, the same full
publication/evidence/authority/operation identity, positive `workflow_run_id`, positive
`run_attempt`, positive `check_suite_id`, `attempt_kind="fence_check_run_page"`, positive gapless
`page_ordinal`, `per_page=100`, nonnegative `total_count`, nullable validated previous/next Link,
ordered nested exact
`check_runs: PublicationCheckRunProjectionV1`, method/endpoint/request/times,
`response_status=200`, canonical/raw response hashes and blob, credential subject, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, signing identity/signature, and
`fence_check_run_page_receipt_sha256`. The endpoint is exactly
`GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs?check_name=laconian%2Fpublication-pr-validate&filter=all&per_page=100&page={page_ordinal}`.

`PublicationMergeFenceCheckRunDiscoveryV1` has exactly `schema_version`, the same full
publication/evidence/authority identity, `workflow_run_id`, `run_attempt`, `check_suite_id`,
`merge_group_head_oid`, Actions App ID/slug, `check_name="laconian/publication-pr-validate"`,
operation key/credential ordinal, positive `page_count`, ordered nested exact
`pages: PublicationMergeFenceCheckRunPageReceiptV1`, ordered distinct positive
`matching_check_run_ids`, positive `selected_check_run_id`, `raw_archive_root_sha256`,
`observed_at`, and `check_run_discovery_sha256`. The suite ID byte-equals the authenticated
workflow-run response. Page one dispatches only after the workflow-run source record and terminal
wrapper exist; every later page dispatches only after its predecessor wrapper. Complete signed Link
pagination archives every returned run in that suite, all page counts equal the final enumerated
length, and the direct selected-run read starts only after discovery completes;
exactly one run may match the merge-group head, Actions App, check name and evidence-kind-derived
terminal conclusion. That unique ID is selected. Zero or multiple matches, capped/repeated pages,
an unarchived run or a cross-origin Link fails closed. Response-derived suite/run IDs may
parameterize only serialized continuation requests under the already authority-derived aggregate
key; they never enter a mint request or operation key.

`PublicationMergeFenceCheckRunObservationV1` has the same authority/operation/evidence coordinates,
nested exact `check_run_discovery: PublicationMergeFenceCheckRunDiscoveryV1`,
`check_run_discovery_sha256`, the selected positive check-suite/check-run IDs, Actions App ID/slug,
`name="laconian/publication-pr-validate"`, the same merge-group head OID,
`status="completed"`, `conclusion="success"|"failure"`, `started_at`, `completed_at`, `external_id`, nullable
`decision_artifact_sha256_from_output`, exact direct-GET pre-dispatch/raw archive/signature fields,
and
`check_run_observation_sha256`. The workflow/check run attempt, group/PR/head and conclusion agree;
suite/run IDs byte-equal the discovery selection, and
`workflow.requested_at <= workflow.started_at <= check.started_at <= check.completed_at <=
workflow.completed_at`.
Source-success requires
both conclusions `success`, the exact source-time predicate below, and a null decision
digest. Fence-failure requires both conclusions `failure`; the check output contains exactly the
lowercase selected decision digest in the frozen field and no alternative digest. A direct
`GET /repos/{owner}/{repo}/check-runs/{check_run_id}` is legal only after complete discovery and
only for its selected ID.

`PublicationMergeFenceArtifactPageReceiptV1` has exactly `schema_version`, the same authority and
operation identity, positive `workflow_run_id`, positive `run_attempt`, positive gapless
`page_ordinal`, `per_page=100`, nullable validated previous/next Link, nonnegative `total_count`, ordered exact
artifact entries, method/endpoint/request/times, `response_status=200`, canonical/raw response hashes and blob,
credential subject/dispatch receipt, signing identity/signature, and
`artifact_page_receipt_sha256`. Each
`PublicationMergeFenceArtifactEntryV1` has exactly
`schema_version="PublicationMergeFenceArtifactEntryV1"`, positive `artifact_id`, `node_id`, `name`,
nonnegative `size_in_bytes`, `expired=true|false`, `created_at`, `expires_at`,
`archive_download_url`, and `artifact_entry_sha256`. Complete signed Link pagination inventories
every artifact for this run; count, IDs, ordering and archive root recompute, and missing/capped/
repeated/cross-origin pages fail closed.

`PublicationMergeFenceArtifactRedirectReceiptV1` has exactly `schema_version`, the full evidence
identity, positive `artifact_id`, `archive_format="zip"`, operation coordinates, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1(
attempt_kind="workflow_artifact_redirect")`, `operation_request_dispatch_receipt_sha256` for authenticated
`GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip`, `response_status=302`,
`authorization_header_present_on_api_request=true`, `location_url_sha256`, parsed
`location_host`, `location_path_sha256`, `location_query_sha256`, `location_expires_at`,
`redirect_count=1`, `raw_location_exported=false`, `response_body_sha256` for the exact empty/bounded body, terminal time, signing
identity/signature, and `artifact_redirect_receipt_sha256`. Location host must match the frozen
GitHub Actions artifact-object-store allowlist, the location digest is computed inside the broker
without persisting the pre-signed query, expiry must exceed the next dispatch plus skew, and
userinfo, fragment, non-HTTPS, IP literals, private/link-local targets and extra redirects are
forbidden. This record contains no terminal transport wrapper/digest or evidence-set digest.

`PublicationMergeFenceArtifactArchiveReceiptV1` has exactly `schema_version`, the same evidence
identity and artifact ID, nested exact redirect receipt/digest, a distinct signed object-store
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1(
attempt_kind="workflow_artifact_archive")`, `operation_request_dispatch_receipt_sha256`,
`method="GET"`, exact validated location digest,
`authentication_kind="none"`, `authorization_header_present=false`, `cookie_header_present=false`,
`redirect_follow_count=0`, positive `maximum_archive_bytes`, observed content length,
`response_status=200`, `content_type="application/zip"`, `zip_sha256`, nested exact bounded raw ZIP
blob, dispatch/completion times, signing identity/signature, and `artifact_archive_receipt_sha256`.
The publisher token is stripped before the cross-origin request; the signed broker operation
projection still inventories this credential-free follow as `workflow_artifact_archive`, while no
vault token is attached to its wire headers. Size overrun, range/chunk mismatch, redirect or host
change fails before extraction. This record contains no terminal transport wrapper/digest; the
token/App fields in its append-before-send receipt are provenance only.

`PublicationMergeFenceArtifactExtractionReceiptV1` has exactly `schema_version`, the same identity,
artifact/archive digests, frozen limits for entry count, total uncompressed bytes, per-entry bytes,
compression ratio, path depth and filename bytes, ordered exact ZIP-member inventory,
`selected_path="publication-merge-fence/decision.json"`, `selected_json_sha256`, nested exact
`decision_artifact: PublicationMergeFenceDecisionArtifactV1`, `decision_artifact_sha256`,
`extracted_at`, signing identity/signature, and `artifact_extraction_receipt_sha256`. Extraction is
one fd-relative no-follow pass into a new private directory; absolute/traversal/backslash/NUL or
non-NFC paths, duplicates after normalization/case-folding, links, devices, encryption, unsupported
methods, bad CRC/size, nested archives and every unexpected selected-path multiplicity fail closed.
The selected canonical JSON bytes reproduce both decision digests.

`PublicationMergeFenceArtifactInventoryV1` has exactly `schema_version`, the same identity/run,
ordered nested exact pages, page/archive roots, ordered distinct `candidate_artifact_ids`,
`expired_candidate_count=0`, ordered nested exact redirect/archive/extraction receipts for every
candidate artifact, positive `selected_artifact_id`,
`selected_decision_artifact_sha256`, `observed_at`, and `artifact_inventory_sha256`. Candidate IDs
are the complete ascending projection of every paginated entry whose exact name is
`laconian-publication-merge-fence-decision`, including expired entries; validity therefore requires
that every such entry is nonexpired. Every candidate is downloaded and safely inspected; exactly
one extracted decision matches the full campaign/intent/CAS/run-attempt/
group/PR/App/context identity and the check-output digest. Zero matches, two matches, a divergent
candidate, an expired candidate, an omitted download or an extra receipt fails closed.

`PublicationMergeFenceEvidenceSetV1` has exactly `schema_version`, the full identity,
`evidence_kind="rerun_source_success"|"post_containment_fence_failure"`,
`containment_authority_mutation_receipt_sha256`, nested exact
`workflow_run_observation: PublicationMergeFenceWorkflowRunObservationV1`,
`workflow_run_observation_sha256`, nested exact
`check_run_observation: PublicationMergeFenceCheckRunObservationV1`,
`check_run_observation_sha256`, nullable nested exact
`artifact_inventory: PublicationMergeFenceArtifactInventoryV1`, nullable
`artifact_inventory_sha256`, nullable nested exact
`decision_artifact: PublicationMergeFenceDecisionArtifactV1`, nullable
`decision_artifact_sha256`, ordered exact `transport_wrapper_sha256s`,
`raw_archive_root_sha256`, `observed_at`, and `fence_evidence_set_sha256`.
The mutation-receipt digest byte-equals the exact accepted containment-start receipt resolved at
`containment_authority_oid` and later nested by the barrier; an evidence set without that join is
invalid. Source-success requires both observations to carry the source-success kind, terminal success and
each source workflow/check `completed_at < containment_authority_mutation_receipt.started_at` for
the exact accepted start receipt; both artifact pairs and the check-output decision digest are
null. Their later GET dispatch/completion and evidence-set `observed_at` may be at or after that
receipt's `completed_at`: those times authenticate immutable old success and are not execution
times. It makes no tombstone-decision claim. Fence-failure requires both observations to carry the
failure kind/conclusion, all four artifact fields nonnull, and the selected extracted decision/
check-output digest to reproduce an authority read at or after the same receipt's `completed_at`.
No mixed arm is valid.

For every signed HTTP source record `R` among the workflow-run observation, fence check-run page,
check-run observation, artifact page, artifact redirect and artifact archive, with respect to
generic operation-lifecycle receipts `R` nests its append-before-send
`PublisherOperationRequestDispatchReceiptV1 D` and no terminal wrapper or evidence set. It may
nest only the class-bound local prerequisites named by its own schema. The unique later
`PublisherOperationTransportReceiptV1 T` nests that same `D`, byte-equals the request/status/times/
raw hash and points one-way with `T.source_observation_sha256` equal to `R`'s recomputed named final
digest. `R` never names `T`.
`transport_wrapper_sha256s` is the exact request-order bijection of those wrappers. Extraction and
inventory are local descendants with no transport wrapper. Thus the only edge order is
`D -> R -> T -> evidence set`; every raw body and ZIP is archived once. `observed_at` is the maximum
authenticated/extraction time. All duplicated run/check/group/PR/authority/decision fields and the
check-output/inventory/decision digests are byte-equal. Its domain is
`laconian-publication-merge-fence-evidence-set-v1\n`, omitting only its digest.

The evidence signature and record domains are literal:

| Type | Signature domain | Record domain |
|---|---|---|
| `PublicationMergeFenceWorkflowRunObservationV1` | `laconian-publication-merge-fence-workflow-run-observation-signature-v1\n` | `laconian-publication-merge-fence-workflow-run-observation-v1\n` |
| `PublicationMergeFenceCheckRunPageReceiptV1` | `laconian-publication-merge-fence-check-run-page-receipt-signature-v1\n` | `laconian-publication-merge-fence-check-run-page-receipt-v1\n` |
| `PublicationMergeFenceCheckRunObservationV1` | `laconian-publication-merge-fence-check-run-observation-signature-v1\n` | `laconian-publication-merge-fence-check-run-observation-v1\n` |
| `PublicationMergeFenceArtifactPageReceiptV1` | `laconian-publication-merge-fence-artifact-page-receipt-signature-v1\n` | `laconian-publication-merge-fence-artifact-page-receipt-v1\n` |
| `PublicationMergeFenceArtifactRedirectReceiptV1` | `laconian-publication-merge-fence-artifact-redirect-receipt-signature-v1\n` | `laconian-publication-merge-fence-artifact-redirect-receipt-v1\n` |
| `PublicationMergeFenceArtifactArchiveReceiptV1` | `laconian-publication-merge-fence-artifact-archive-receipt-signature-v1\n` | `laconian-publication-merge-fence-artifact-archive-receipt-v1\n` |
| `PublicationMergeFenceArtifactExtractionReceiptV1` | `laconian-publication-merge-fence-artifact-extraction-receipt-signature-v1\n` | `laconian-publication-merge-fence-artifact-extraction-receipt-v1\n` |

For every table row, the signature preimage is `UTF8(signature-domain) ||
CanonicalJSONV1(record without exactly broker_signature_base64url and the row's final digest)`; the
record digest is `SHA256(UTF8(record-domain) || CanonicalJSONV1(record without exactly its final
digest))`, including the verified signature. The signing fields are literally
`broker_signing_identity` and `broker_signature_base64url`. Record-only domains are
`PublicationMergeFenceCheckRunDiscoveryV1` ->
`laconian-publication-merge-fence-check-run-discovery-v1\n`,
`PublicationMergeFenceArtifactInventoryV1` ->
`laconian-publication-merge-fence-artifact-inventory-v1\n`,
`PublicationMergeFenceArtifactEntryV1` ->
`laconian-publication-merge-fence-artifact-entry-v1\n`, and the evidence-set domain above. Each
record-only type hashes canonical JSON omitting exactly its named final digest. No inferred
capitalization transform, generic standard omission or domain alias is valid.

`PublicationMergeFenceRerunTargetProofV1` has exactly
`schema_version="PublicationMergeFenceRerunTargetProofV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`,
`workflow_path=".github/workflows/publication-pr-validate.yml"`, `workflow_ref`,
`workflow_commit_oid`, `workflow_blob_sha256`, `workflow_root`, positive
`workflow_run_id`, positive `source_run_attempt`, `event="merge_group"`,
`action="checks_requested"`, `merge_group_ref`, `merge_group_base_oid`,
`merge_group_head_oid`, positive `pull_request_number`, `pull_request_node_id`,
`pull_request_head_oid`, `actions_app_id`, `actions_app_slug`,
`check_name="laconian/publication-pr-validate"`, nested exact
`source_run_evidence_set: PublicationMergeFenceEvidenceSetV1(
evidence_kind="rerun_source_success")`,
`source_run_evidence_set_sha256`,
`observed_at`, and `rerun_target_proof_sha256`. The signed read receipts/blobs
inside the evidence set form a complete bijection to the authenticated run/check-discovery reads
and prove the exact
one-PR merge group, frozen workflow, App/context and prior run. The source run/check IDs, suite,
attempt, group/head/PR/App/context and authenticated workflow-run repository ID byte-equal the
target fields and the full identity's `repository_id`; both source completions are strictly before
the accepted containment mutation receipt's `started_at`, while their later evidence reads may
complete after that receipt. It contains no post-CAS failed-fence artifact, rerun dispatch or
outcome. Its domain is `laconian-publication-merge-fence-rerun-target-proof-v1\n`,
omitting only its digest.

`PublicationMergeFenceRerunAttemptV1` records every authorized rerun attempt, including failures.
It has exactly `schema_version="PublicationMergeFenceRerunAttemptV1"`, the full publication
identity, intent/CAS/denylist roots, `operation_kind="terminal_merge_fence_rerun"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`, nested exact
`target_proof: PublicationMergeFenceRerunTargetProofV1`, `target_proof_sha256`, positive
`workflow_run_id`, positive `source_run_attempt`, positive `expected_run_attempt`,
`dispatch_state="not_dispatched"|"dispatched"`, nullable nested exact
`dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`, nullable
`dispatch_receipt_sha256`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1(
operation_kind="terminal_merge_fence_rerun")`, `transport_receipt_sha256`,
`outcome="not_dispatched"|"rerun_accepted_201"|"delivery_ambiguous"|"definite_rejection"`,
nullable `response_status`, nullable `safe_response_sha256`, `recorded_at`, and
`rerun_attempt_sha256`. Target fields byte-equal the proof, workflow run is the original target,
and `expected_run_attempt=source_run_attempt+1` without overflow. Not-dispatched has null dispatch
pair and response fields; every dispatched member has the exact append-before-send dispatch pair.
Accepted requires status 201 and a closed safe response; ambiguity covers response loss or a
received response that cannot prove rejection/no-effect; definite rejection is only authenticated
pre-effect 401/403/404. A later required-fence receipt may select only an accepted attempt and must
then authenticate that exact expected attempt; attempts before it remain inventoried and none may
dispatch after the selected accepted attempt. Its domain is
`laconian-publication-merge-fence-rerun-attempt-v1\n`, omitting only its digest.

`PublicationRequiredMergeFenceRunReceiptV1` has exactly
`schema_version="PublicationRequiredMergeFenceRunReceiptV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`,
`workflow_path=".github/workflows/publication-pr-validate.yml"`, `workflow_ref`,
`workflow_commit_oid`, `workflow_blob_sha256`, `workflow_root`,
positive `workflow_run_id`, positive `run_attempt`, positive
`check_suite_id`, positive `check_run_id`, `actions_app_id`,
`actions_app_slug`, `check_name="laconian/publication-pr-validate"`,
`event="merge_group"`, `action="checks_requested"`,
`merge_group_ref`, `merge_group_base_oid`, `merge_group_head_oid`,
positive `pull_request_number`, `pull_request_node_id`,
`pull_request_head_oid`, `trigger_kind="new_merge_group"|"authorized_rerun"`,
nullable nested exact
`selected_rerun_attempt: PublicationMergeFenceRerunAttemptV1`, nullable
`selected_rerun_attempt_sha256`,
`requested_at`, `started_at`,
`completed_at`, `status="completed"`, `conclusion="failure"`,
`decision="denied_by_publication_merge_denylist"`, `observed_authority_ref`,
`observed_authority_oid`, positive `observed_transition_number`,
`observed_active_publication_terminal_containment_root`,
`observed_merge_denylist_root_sha256`, `decision_authority_read_at`, nested exact
`fence_evidence_set: PublicationMergeFenceEvidenceSetV1(
evidence_kind="post_containment_fence_failure")`, `fence_evidence_set_sha256`,
`decision_artifact_sha256`, `request_receipts_root_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and
`required_merge_fence_run_receipt_sha256`. The merge group contains exactly this one PR.
`PublicationMergeFenceDecisionArtifactV1` has exactly `schema_version`, the full publication
identity, workflow/run/group/PR identity, every `observed_*` field above,
`decision_authority_read_at`, `decision`, `created_at`, and `decision_artifact_sha256`; its domain is
`laconian-publication-merge-fence-decision-artifact-v1\n`. Its extracted archive path and bytes are
the frozen member named by the evidence set; the set's typed run/check discovery/page/redirect/
archive records and ordered request root form the exact response/wrapper/raw-archive bijection.
The evidence workflow response's repository ID equals the full identity's `repository_id`, its
suite/run IDs equal the complete discovery selection, and `request_receipts_root_sha256` is the
canonical ordered root of `fence_evidence_set.transport_wrapper_sha256s`.
For `new_merge_group`, both selected-rerun-attempt fields are null and
`run_attempt=1`; original request/start may precede the CAS. For
`authorized_rerun`, the exact selected `PublicationMergeFenceRerunAttemptV1(
outcome="rerun_accepted_201")`/digest is nonnull, selects
`POST /repos/{owner}/{repo}/actions/runs/{workflow_run_id}/rerun`, proves a 201 terminal response
under the C0-frozen `actions:write` row, and dispatches after the CAS;
the original `requested_at` may predate the CAS but `started_at` is not before rerun dispatch. The
receipt `workflow_run_id` equals the attempt's original target run and
`run_attempt=selected_rerun_attempt.expected_run_attempt=
selected_rerun_attempt.source_run_attempt+1`; the fresh evidence set independently authenticates
that exact new attempt, check, artifact and decision. Target proof and dispatch/transport fields
recompute for this frozen workflow, event/action, one-PR merge-group SHA, App/context and original
run; caller-selected run IDs or adoption of a later retry are invalid. In both cases
`decision_authority_read_at` is at or after the containment CAS and before
decision/check completion, and the observed authority OID
equals that CAS OID or a descendant preserving the same active-containment and denylist roots. The
evidence set's selected decision artifact reproduces every `observed_*` field. A skipped, neutral,
cancelled, stale, success, unauthorized/pre-CAS rerun, wrong-App/context/workflow or multi-PR check
is invalid. Signature and record domains are
`laconian-publication-required-merge-fence-run-signature-v1\n` and
`laconian-publication-required-merge-fence-run-receipt-v1\n`. Its signature preimage omits exactly
`broker_signature_base64url` and `required_merge_fence_run_receipt_sha256`; its record digest
omits exactly only `required_merge_fence_run_receipt_sha256` and includes the verified signature.

`PublicationTerminalMergeSnapshotV1` has exactly
`schema_version="PublicationTerminalMergeSnapshotV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`,
`barrier_scope="all_candidates"|"residual_unmerged_after_merge_won"`, ordered distinct
`excluded_merged_candidate_pull_request_numbers`, `snapshot_ordinal=1|2`, nested exact
`protected_main_observation: PublicationProtectedMainObservationV1`,
`protected_main_observation_sha256`, nested exact
`marker_discovery: PublicationPRMarkerDiscoveryV1`,
`marker_discovery_sha256`, nested exact
`merge_queue_inventory: PublicationMergeQueueInventoryObservationV1(
observation_scope="post_containment")`, `merge_queue_inventory_sha256`, ordered distinct positive
`candidate_pull_request_numbers`, ordered nested exact
`queue_observations: PublicationMergeQueueObservationV1`, ordered matching
`queue_observation_sha256s`, `all_denied_queue_entries_absent=true`,
`all_candidates_unmerged=true`, `observed_main_oid`,
`canonical_external_snapshot_sha256`, `observed_at`, and
`snapshot_sha256`. For all-candidates scope the excluded array is empty. For residual scope it is
the exact merged-candidate number array from the enclosing merge-won evidence and those candidates
are omitted from every unmerged/queue-absence assertion, but retained in the signed source
archives. Candidates are otherwise the sorted union of preflight, source, prior action
observations, this complete fresh marker discovery and every denylist-affected global inventory
entry; each has exactly one queue observation, and
the array is empty iff that union is empty. Every queue observation has a null entry and an unmerged
PR. The global inventory may retain unrelated entries but has an empty `affected_entry_ids` array.
Snapshot ordinal byte-equals its inventory ordinal and maps protected-main/queue observation phase
to `post_action_first`/`after_action_first` or `post_action_second`/`after_action_second`.
The protected-main observation supplies the OID even when there are no candidates. Snapshot two
begins only after every snapshot-one request terminates. The two canonical external digests exclude
only receipt/request/time fields and byte-equal. `observed_at` is the maximum authenticated source
time of its main observation, marker discovery, complete inventory and every queue observation; it
is not caller-selected. Its domain is
`laconian-publication-terminal-merge-snapshot-v1\n`, omitting only its final digest.

`PublicationMainFirstParentCommitV1` has exactly
`schema_version="PublicationMainFirstParentCommitV1"`, nested exact
`commit_observation: PublicationMainCommitObservationV1`,
`commit_observation_sha256`, `commit_oid`, ordered
`parent_oids`, `committed_at`, `message_sha256`, nullable
`merge_commit_laconian_trailer`, ordered nested exact `associated_pull_requests`,
positive `selected_merged_pull_request_number`, nested exact
`selected_head_commit_observation: PublicationHeadCommitObservationV1`,
`selected_head_commit_observation_sha256`, and `canonical_commit_sha256`. Each PR
member has exactly positive `number`, `node_id`,
`state="open"|"closed"`, `merged`, nullable `merged_at`, nullable
`merge_commit_oid`, `base_ref_name`, `base_oid`, `head_ref_name`,
`head_oid`, nullable `pull_request_marker`, and `canonical_pr_sha256`.
Every commit requires exactly two distinct parent OIDs, as proved by the rollout's one-entry
`MERGE`-queue protection contract, and exactly one selected member with `merged=true`,
nonnull merged time, `merge_commit_oid=commit_oid`, protected main as base and all complete
identity fields; zero or multiple candidates fail closed. The selected head OID binds an already
archived exact head-commit read whose canonical trailer is tested against the successor denylist.
The merge commit trailer is preserved separately and never substituted for the publication
head-commit trailer. A single-parent, octopus, direct-push, squash/rebase or otherwise
nonconforming main-advance member is a protection-bypass failure, never an unrelated safe advance.
Its domain is
`laconian-publication-main-first-parent-commit-v1\n`, omitting exactly its final digest.

`PublicationMainCommitObservationV1` is one signed step in the separately reconstructed main
first-parent walk. It has exactly `schema_version="PublicationMainCommitObservationV1"`, the full
publication identity, `terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, `operation_kind="terminal_merge_barrier_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`, `observation_stage="containment_advance"`, `commit_oid`,
`method="GET"`, `endpoint_template="/repos/{owner}/{repo}/git/commits/{commit_oid}"`,
`request_url`, `request_id`, `request_dispatched_at`, `response_completed_at`,
`response_status=200`, `observed_commit_oid`, ordered `parent_oids`, `tree_oid`, `committed_at`,
`message_sha256`, nullable `merge_commit_laconian_trailer`, `canonical_response_sha256`,
`raw_response_sha256`, nested exact `raw_response_blob`, `publisher_credential_subject_sha256`,
nested exact `request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, `observed_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `main_commit_observation_sha256`. Observed and requested OIDs
are equal and every commit field is the total authenticated Git-object projection. Raw bytes are
archived; dispatch/transport wrappers and signature bind the same identity/key/ordinal/time. Its
signature and record domains are `laconian-publication-main-commit-observation-signature-v1\n` and
`laconian-publication-main-commit-observation-v1\n` with exact signed-record omissions. The
enclosing semantic commit byte-equals this observation's OID/parents/time/message/trailer.

`PublicationHeadCommitObservationV1` is the immutable selected-PR head read. It has exactly
`schema_version="PublicationHeadCommitObservationV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, `classifying_main_commit_oid`, positive
`selected_merged_pull_request_number`, `head_oid`,
`operation_kind="terminal_merge_barrier_read"`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, positive `operation_request_ordinal`,
`observation_stage="containment_advance"`, `method="GET"`,
`endpoint_template="/repos/{owner}/{repo}/git/commits/{head_oid}"`, `request_url`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `response_status=200`,
`observed_commit_oid`, ordered `parent_oids`, `tree_oid`, `message_sha256`, ordered nested exact
`parsed_trailers`, nullable `selected_publication_head_commit_trailer`,
`canonical_response_sha256`, `raw_response_sha256`, nested exact `raw_response_blob`,
`publisher_credential_subject_sha256`, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, `observed_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `head_commit_observation_sha256`. The observed OID equals
`head_oid`; parents/tree/message are total projections of the immutable Git commit response.
Each parsed trailer has exactly `ordinal`, `key`, and `value` and is the complete canonical
`git interpret-trailers --parse` equivalent over the authenticated message bytes. The selected
trailer is null only when neither Laconian publication/correction trailer exists; otherwise it is
the unique exact `Laconian-Publication-Attempt: ...` or `Laconian-Correction-ID: ...` line.
Duplicates, both classes, invalid UTF-8/control bytes or parse disagreement fail closed. Raw bytes
are archived and every request/identity/time field byte-equals the signed dispatch/transport
wrapper. Its signature and record domains are
`laconian-publication-head-commit-observation-signature-v1\n` and
`laconian-publication-head-commit-observation-v1\n` with the exact signed-record omissions.
The enclosing first-parent commit nests this exact object for its selected PR head, and all
commit/PR/head/trailer fields byte-equal; the successor denylist independently tests this selected
trailer rather than the main merge commit message.

`PublicationMainComparePageReceiptV1` has exactly `schema_version`, the full
publication identity, `terminal_containment_intent_sha256`,
`containment_authority_oid`, `operation_kind="terminal_merge_barrier_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`,
`page_kind="compare"|"commit_pull_requests"`, nullable `commit_oid`, positive
`page_ordinal`, `method="GET"`, `endpoint_template`,
`request_url`, `request_id`, `request_dispatched_at`,
`response_completed_at`, `response_status=200`, nullable `previous_link`,
nullable `next_link`, `raw_response_sha256`,
`canonical_response_sha256`, nested exact `raw_response_blob`,
`publisher_credential_subject_sha256`, nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`,
`operation_request_dispatch_receipt_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `main_compare_page_receipt_sha256`. Compare
maps only to `/repos/{owner}/{repo}/compare/{from_oid}...{to_oid}` and has null commit;
PR classification maps only to `/repos/{owner}/{repo}/commits/{commit_oid}/pulls`.
Both use complete signed Link pagination and archive every member/body. Signature and record domains
are `laconian-publication-main-compare-page-signature-v1\n` and
`laconian-publication-main-compare-page-receipt-v1\n`. The signature preimage is its signature
domain plus `CanonicalJSONV1(record without exactly broker_signature_base64url and
main_compare_page_receipt_sha256)`; the record digest is its record domain plus
`CanonicalJSONV1(record without exactly main_compare_page_receipt_sha256)`, including the verified
signature.

`PublicationMainAdvanceCompareReceiptV1` has exactly `schema_version`, the same
identity/intent/CAS/from/to OIDs, `compare_status="ahead"`,
`merge_base_oid`, positive `ahead_by`, `behind_by=0`, positive
`total_commits`, ordered distinct `compare_commit_oids`, ordered nested exact
`pages: PublicationMainComparePageReceiptV1`, ordered nested exact
`first_parent_commits: PublicationMainFirstParentCommitV1`,
`raw_archive_root_sha256`, `observed_at`, and
`main_advance_compare_receipt_sha256`. Compare pages enumerate every commit in GitHub's complete
comparison result, including side-branch commits; their canonical OID projection byte-equals
`compare_commit_oids`. `ahead_by=total_commits=len(compare_commit_oids)` after complete
`per_page=100&page=n` pagination. The distinct first-parent array is reconstructed by authenticated
`PublicationMainCommitObservationV1` GETs walking from `to_main_oid` through parent index zero back
to `from_main_oid`, with a finite bound of `ahead_by`, no cycle and no skipped OID; it is never
claimed equal to the compare list. In forward order, the first member's first parent equals
`from_main_oid`, every later member's first parent equals the prior `commit_oid`, and the last
member equals `to_main_oid`. Every walk member has exactly two parents, one complete commit-PR page
chain and an exact selected head-commit observation; any other parent cardinality or missing
classification fails as a protection bypass. Missing/capped pagination,
non-ahead status, ancestry gaps or an unclassified merge commit fails closed. Its domain is
`laconian-publication-main-advance-compare-receipt-v1\n`.

`PublicationContainmentMainAdvanceProofV1` has exactly
`schema_version="PublicationContainmentMainAdvanceProofV1"`, the full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`from_main_oid`, `to_main_oid`, nested exact
`compare_receipt: PublicationMainAdvanceCompareReceiptV1`,
`compare_receipt_sha256`, ordered nested exact `first_parent_commits`, ordered
`intervening_merge_pull_request_numbers`, ordered
`intervening_merge_commit_oids`, `all_intervening_merges_unaffected=true`,
`no_affected_merged_event=true`, `observed_at`, and
`main_advance_proof_sha256`. The signed compare is exactly
`ahead`; the commit array is the complete first-parent path from the containment baseline
exclusive to the post-action OID inclusive and is byte-for-byte equal, in the same order, to
`compare_receipt.first_parent_commits`; the outer array is not an independently selectable copy.
Every intervening merge is class-bound to a PR and
fails every denylist selector independently across PR node ID, number, same-repository branch, head
OID, canonical marker and the selected head-commit trailer. A missing body/head classification or
zero/multiple selected merge PRs fails closed. Force-push, deletion, unknown ancestry or an affected
merge fails closed.
Its domain is `laconian-publication-containment-main-advance-proof-v1\n`.

`PublisherBarrierCredentialDispositionSetV1` is the acyclic credential prefix consumed by
the barrier. It has exactly `schema_version="PublisherBarrierCredentialDispositionSetV1"`,
the same full publication identity,
`terminal_containment_intent_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, positive `disposition_count`, ordered nested
exact `dispositions: PublisherOperationCredentialDispositionV1`,
nested exact `broker_phase_ledger_prefix:
PublisherBrokerPhaseLedgerPrefixV1(prefix_purpose="barrier_complete")`,
`broker_phase_ledger_prefix_sha256`, nested exact
`vault_audit_log_prefix: BrokerVaultAuditPrefixV1(prefix_purpose="barrier_complete")`,
`vault_audit_log_prefix_sha256`,
`outstanding_token_request_count=0`,
`outstanding_operation_dispatch_count=0`, `live_token_count=0`, `observed_at`,
nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and
`publisher_barrier_credential_dispositions_root_sha256`. Count equals array length. Members
are the complete canonical-rank-ordered set of every
`terminal_merge_barrier_read|terminal_merge_barrier_dequeue|terminal_merge_fence_rerun`
credential attempt from source-bound preflight through barrier completion, including denial,
permission mismatch, unknown mint, read abort and retry. Every request/page/action used by
preflight or barrier maps to exactly one member and there is no extra member. The ledger/vault roots
end at the latest member closure and recompute zero open requests/dispatches/live tokens. This
prefix references no barrier, attachment, final disposition set or sealed ledger. Its signature and
record domains are
`laconian-publisher-barrier-credential-disposition-set-signature-v1\n` and
`laconian-publisher-barrier-credential-disposition-set-v1\n` with the exact signed-record
omission rules.
The nested barrier prefix pair has byte-identical identity and `barrier_complete` purpose; its vault
pair digest equals the ledger-prefix digest, duplicated roots/counts/time recompute, and the outer
zero counters equal both prefixes.

`PublicationTerminalMergeBarrierV1` has exactly
`schema_version="PublicationTerminalMergeBarrierV1"`, the full publication identity,
nested exact `terminal_containment_intent: PublicationTerminalContainmentIntentV1`,
`terminal_containment_intent_sha256`, nested exact
`containment_authority_mutation_receipt: AuthorityMutationReceiptV1(
mutation_kind="campaign_event",event_type="PUBLICATION_TERMINAL_CONTAINMENT_STARTED")`,
`containment_authority_mutation_receipt_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, `containment_main_oid`,
`barrier_scope="all_candidates"|"residual_unmerged_after_merge_won"`, ordered distinct
`excluded_merged_candidate_pull_request_numbers`, nested exact
`pre_action_queue_inventory: PublicationMergeQueueInventoryObservationV1(
observation_scope="post_containment",observation_stage="post_containment_pre_action",
snapshot_ordinal=0)`,
`pre_action_queue_inventory_sha256`, ordered nested exact
`pre_action_queue_observations: PublicationMergeQueueObservationV1(
observation_phase="after_intent_pre_action",containment_snapshot_ordinal=0)`, ordered nested
exact `dequeue_attempts: PublicationMergeQueueDequeueAttemptV1`, ordered nested exact
`fence_rerun_attempts: PublicationMergeFenceRerunAttemptV1`, ordered nested exact
`fence_runs: PublicationRequiredMergeFenceRunReceiptV1`, ordered nested exact
`timeline_receipts: PublicationMergeQueueTimelineReceiptV1`, ordered nested exact
`candidate_actions`, nested exact
`first_post_action_snapshot: PublicationTerminalMergeSnapshotV1(
snapshot_ordinal=1,barrier_scope=barrier_scope)`,
nested exact
`second_post_action_snapshot: PublicationTerminalMergeSnapshotV1(
snapshot_ordinal=2,barrier_scope=barrier_scope)`,
ordered distinct positive `candidate_pull_request_numbers`,
`barrier_method="already_clear"|"dequeue"|"fresh_failed_required_run"|
"dequeue_and_fence"`, `all_pre_action_entries_accounted=true`,
`all_denied_queue_entries_absent=true`, `all_candidates_unmerged=true`,
`main_delta="unchanged"|"unrelated_descendant"`, nullable nested exact
`main_advance_proof: PublicationContainmentMainAdvanceProofV1`, nullable
`main_advance_proof_sha256`, `main_safe=true`,
`future_enqueue_requires_new_merge_group=true`,
`canonical_external_snapshot_sha256`,
nested exact
`publisher_barrier_credential_disposition_set: PublisherBarrierCredentialDispositionSetV1`,
`publisher_barrier_credential_dispositions_root_sha256`, `recorded_at`, and
`terminal_merge_barrier_sha256`.

`all_candidates` is the premerge branch. `residual_unmerged_after_merge_won` is legal only when the
containment preflight recorded `merge_observed`; its candidate arrays exclude exactly the immutable
merged-candidate set named by the enclosing merge-won evidence and include every remaining affected
identity. A zero-residual barrier is still constructed from the two complete global snapshots.
For all-candidates scope the barrier exclusion array and both snapshot exclusion arrays are empty.
For residual scope all three arrays byte-equal the enclosing merge-won evidence's exact merged-PR
array. The barrier candidate array, pre-action inventory affected projection, pre-action queue
observations, both snapshot candidate arrays and candidate actions are byte-identical sorted
complements of that exclusion within the complete affected set. Pre-action queue observations form
an exact PR-order bijection to that projection and every member has stage
`containment_pre_action`, snapshot ordinal zero and `after_intent_pre_action`; no post-action read
can justify `already_absent`.
Each candidate action has exactly `pull_request_number`,
`pre_action_queue_observation_sha256`, ordered `dequeue_attempt_sha256s`, nullable
`selected_dequeue_attempt_sha256`, ordered `fence_rerun_attempt_sha256s`, nullable
`selected_fence_run_receipt_sha256`, nullable `timeline_receipt_sha256`,
nullable `selected_fence_trigger_kind="new_merge_group"|"authorized_rerun"`,
nullable `selected_removal_event_sha256`, nullable `selected_action_resolution_sha256`, and
`action_resolution="already_absent"|"dequeued_exact"|"removed_after_response_loss"|
"removed_after_failed_fence"`. Candidate actions partition the global dequeue-attempt,
fence-rerun-attempt, accepted-fence and timeline arrays by PR; each digest appears exactly once and
no attempt/run/timeline is missing or extra. The union is closed: `already_absent` requires a null
pre-action entry, both attempt arrays empty and every selected/timeline field null. `dequeued_exact`
requires a nonempty dequeue array whose selected member is the unique exact `dequeued_exact`
attempt and has no fence selection. `removed_after_response_loss` requires a selected
`delivery_ambiguous` dequeue plus nonnull timeline/causal removal and no fence selection.
`removed_after_failed_fence` requires exactly one selected fresh post-CAS failed required-validator
receipt, a nonnull trigger kind byte-equal to that receipt's `trigger_kind`, and a nonnull
timeline/selected causal removal pair after that
failure and before both post-action snapshots. Exactly one trigger arm holds. `new_merge_group`
requires `run_attempt=1`, null selected-rerun object/digest in the selected run, and no selected
rerun attempt in this action; its rerun-attempt array may contain only earlier nondecisive attempts
for other old run/group identities and none may target the selected new run. `authorized_rerun`
requires the selected run's exact nonnull
`PublicationMergeFenceRerunAttemptV1(outcome="rerun_accepted_201")` digest to occur exactly once in
this action's nonempty rerun-attempt array and requires `run_attempt=source_run_attempt+1` with full
target/source-evidence equality. Dequeue attempts in either arm are empty or end in a recorded
delivery ambiguity. Every other action has a null trigger. Earlier
no-mint/not-dispatched/rejection/ambiguous attempts remain in order; no action attempt may dispatch
after the first decisive exact dequeue or selected accepted fence. `selected_action_resolution_sha256`
is the domain-separated digest of the selected attempt, trigger, fence, timeline and removal tuple
and is null only for `already_absent`. If no decisive resolution
exists, the barrier is unconstructible and its complete attempt prefix remains failure evidence.
`already_clear` means every action is already
absent; `dequeue` means at least one confirmed/causally settled dequeue and no fence;
`fresh_failed_required_run` the inverse; the combined method has both. Fence presence is determined
by a selected failed-fence receipt in either trigger arm, never merely by an accepted rerun. A delivery-ambiguous action
requires its selected timeline removal before both later global inventories. The two snapshots have equal main OIDs,
marker/candidate semantics and canonical external state. `unchanged` requires that OID equal
`containment_main_oid` and both advance-proof fields null; `unrelated_descendant`
requires a nonnull recomputed proof to the common post-action OID. A zero-candidate barrier is proved by two
signed protected-main observations plus two zero-match marker discoveries, never by a free boolean.
Any newly merged affected candidate not already present in the residual scope's exact exclusion
array, or any unsafe/unknown main change, forbids this schema and routes through
exact merge-won/failed-admission evidence or fails closed. The queue `LOCKED` entry must remain observable until exact dequeue,
failed required-check removal or completed merge; rollout is unsupported unless the pilot
establishes that contract. The barrier domain is
`laconian-publication-terminal-merge-barrier-v1\n`, omitting only its final digest.
`recorded_at` equals the nested barrier-disposition-set `observed_at` and is not before either
snapshot time or any selected dequeue, timeline or fence completion time.

The broker exposes three containment-scoped publisher rows. Their operation names, sorted
permission arrays, endpoint sets and target constraints are byte-for-byte the literal broker matrix
in section 7.6; this local summary cannot narrow or widen them. The barrier-read row is legal for
the source-bound preflight and for intent/CAS-bound post-action reads, the dequeue row only for the
fixed mutation and broker-derived proof, and the rerun row only for the exact authenticated frozen
workflow/run/group/App/context proof. Dequeue and rerun are
legal only after the accepted containment CAS. The pilot must prove those exact GitHub-App installation permissions work; a broader
admin or contents-write grant is invalid. Each credential is minted only after the persistent
tombstone CAS, except the explicitly source-bound read-only preflight credential. Requests are gapless and serialized: ordinal `n+1` cannot dispatch before
ordinal `n` has a terminal receipt. A mint followed by executor abort before the first or
next request still closes as a signed minted-and-closed read-abort disposition with zero open
requests and no synthesized observation; terminalization requires a later fresh attempt that
constructs the barrier or observes `merge_won`.

Containment operation keys are broker-derived, never caller-selected. Here `LP(x)` is
U32BE byte length followed by exact UTF-8 bytes, an absent value is the empty string, and stage ranks
are preflight=1, pre-action=2, action=3, first=4, second=5, advance=6. A barrier-read key is exactly
`"publication-containment-read/" + lowercase_hex(SHA256(
UTF8("laconian-publication-containment-read-key-v1\n") ||
LP(source_or_intent_sha256) || LP(containment_authority_oid_or_empty) || U8(stage_rank) ||
U8(snapshot_ordinal_or_zero) || LP(logical_aggregate_class) || LP(canonical_target)))`. Preflight uses the source
digest and empty authority; every post-CAS read uses the intent digest and containment authority.
`canonical_target` is computed before mint and before the aggregate's first request as
`<logical-aggregate-class>/` plus lowercase hex SHA-256 of
`UTF8("laconian-publication-containment-target-v1\n")`, then the following exact LP fields:

| Aggregate class | Exact authority-known LP field sequence |
|---|---|
| `protected_main` | `repository_id`, literal `refs/heads/main` |
| `marker_discovery` | `pull_request_marker` |
| `queue_pr` | zero-padded 20-digit affected PR number |
| `queue_inventory` | `repository_id`, literal `refs/heads/main`, barrier scope |
| `queue_timeline` | zero-padded 20-digit affected PR number |
| `fence_evidence` | source workflow-run ID, source run attempt, frozen workflow-blob digest, Actions App ID, literal check name, merge-group head OID, affected PR number |
| `main_advance` | containment baseline OID, authenticated current-run OIDC SHA |

Intent/source digest, authority OID, stage/snapshot and class remain in the outer operation-key
preimage. Queue/entry node IDs, check-suite/run IDs, artifact IDs/URLs and archive digests are
response-derived and appear only in signed observations/pages; none enters this target or changes
the aggregate key. A main-advance token is minted only after the current-run SHA is authenticated;
its first protected-main read must equal that SHA or the aggregate aborts.
`logical_aggregate_class` is one of `protected_main`, `marker_discovery`, `queue_pr`,
`queue_inventory`, `queue_timeline`, `fence_evidence`, or `main_advance`; it and target are constant
for the complete logical aggregate. Request attempt kind, observation round, inventory pass and page
are deliberately excluded from the operation key and are bound only by each append-before-send/
terminal wrapper. Thus every page/round of one aggregate shares one key/disposition and different
aggregate/stage/target scopes cannot collide.
The class/source-to-coordinate map is literal: protected-main `pre_containment`,
`post_action_first`, `post_action_second` map to `containment_preflight/0`,
`containment_first/1`, `containment_second/2`; queue-PR `after_intent_pre_action`,
`after_action_first`, `after_action_second` map to `containment_pre_action/0`,
`containment_first/1`, `containment_second/2`; inventory `pre_containment`,
`post_containment_pre_action`, `post_action_first`, `post_action_second` map to
`containment_preflight/0`, `containment_pre_action/0`, `containment_first/1`,
`containment_second/2`. Timeline and fence evidence use `containment_action` with null snapshot;
compare/main/head commit reads use `containment_advance` with null snapshot. No other
class/stage/snapshot triple is valid.
A dequeue key is exactly
`"publication-containment-dequeue/" + lowercase_hex(SHA256(
UTF8("laconian-publication-containment-dequeue-key-v1\n") ||
HEXDECODE(dequeue_target_proof_sha256) || U64BE(action_ordinal)))`. A rerun key is exactly
`"publication-containment-rerun/" + lowercase_hex(SHA256(
UTF8("laconian-publication-containment-rerun-key-v1\n") ||
HEXDECODE(rerun_target_proof_sha256) || U64BE(source_run_attempt + 1)))`. Every credential request,
subject, dispatch/transport receipt, action schema and disposition recomputes the applicable key,
target-proof digest and coordinates. Any different target, free key or cross-stage reuse is denied
before mint or dispatch.

`PublisherWriteAmbiguityFenceAttachmentV1` has exactly
`schema_version="PublisherWriteAmbiguityFenceAttachmentV1"`, the same full publication
identity, `write_ambiguity_set_sha256`,
`terminal_containment_intent_sha256`,
`containment_authority_mutation_receipt_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, `terminal_merge_barrier_sha256`,
`publisher_barrier_credential_dispositions_root_sha256`, positive `subject_count`,
ordered `write_ambiguity_subject_sha256s`, ordered
`source_credential_disposition_sha256s`,
nested exact `pre_attachment_broker_phase_ledger_prefix:
PublisherBrokerPhaseLedgerPrefixV1(prefix_purpose="pre_fence_attachment")`,
`pre_attachment_broker_phase_ledger_root_sha256`, nested exact
`pre_attachment_vault_audit_prefix:
BrokerVaultAuditPrefixV1(prefix_purpose="pre_fence_attachment")`,
`pre_attachment_vault_audit_log_root_sha256`, `observed_authority_oid`, positive
`observed_transition_number`, `observed_active_publication_terminal_containment_root`,
`observed_publication_merge_denylist_root_sha256`, `authority_observed_at`,
`outstanding_token_request_count=0`,
`outstanding_operation_dispatch_count=0`, `live_token_count=0`,
`canonical_external_state_claimed=false`, `admission_authorized=false`,
`release_authorized=false`, `attached_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and
`publisher_write_ambiguity_fence_attachment_sha256`. Count/subject array byte-equal the
ambiguity set. The source-disposition array is aligned one-for-one; duplicates are legal when
several lost requests share one credential disposition, and each subject's source disposition,
operation/key/credential/request/transport tuple recomputes. The authority read follows the barrier
and observes the same active intent and permanent denylist. The pre-attachment broker root is
exactly the just-appended `terminalizing -> terminal_reconciling` transition; the attachment
names no attachment-ledger entry or final set. Its signature and record domains are
`laconian-publisher-write-ambiguity-fence-attachment-signature-v1\n` and
`laconian-publisher-write-ambiguity-fence-attachment-v1\n` with exact signed-record
omissions.
The nested pre-attachment prefix pair has byte-identical identity and
`pre_fence_attachment` purpose; its vault pair digest equals the ledger-prefix digest, duplicated
roots/counts/time recompute, and the attachment zero counters equal both prefixes.

`PublicationFencedWriteAmbiguityV1` has exactly
`schema_version="PublicationFencedWriteAmbiguityV1"`, the full publication identity,
`terminal_route="initial_complete_premerge"|"initial_invalid_premerge"|
"correction_premerge"`, `terminal_event_type`, nested exact
`write_ambiguity_set: PublicationWriteAmbiguitySetV1`,
`write_ambiguity_set_sha256`, nested exact
`terminal_containment_intent: PublicationTerminalContainmentIntentV1(
containment_kind="write_ambiguity")`, `terminal_containment_intent_sha256`, nested exact
`containment_authority_mutation_receipt: AuthorityMutationReceiptV1(
mutation_kind="campaign_event",event_type="PUBLICATION_TERMINAL_CONTAINMENT_STARTED")`,
`containment_authority_mutation_receipt_sha256`, nested exact
`successor_merge_denylist: PublicationMergeDenylistV1`,
`successor_merge_denylist_root_sha256`, nested exact
`terminal_merge_barrier: PublicationTerminalMergeBarrierV1`,
`terminal_merge_barrier_sha256`, nested exact
`publisher_write_ambiguity_fence_attachment:
PublisherWriteAmbiguityFenceAttachmentV1`,
`publisher_write_ambiguity_fence_attachment_sha256`, nested exact
`publisher_credential_disposition_set: PublisherCredentialDispositionSetV1(
finality_status="write_ambiguity_fenced_sealed")`,
`publisher_credential_disposition_set_sha256`, nested exact
`release_authorization_ledger_snapshot:
PublicationReleaseAuthorizationLedgerSnapshotV1`,
`release_authorization_ledger_root_sha256`, nullable `merge_observation_sha256`,
`delivery_ambiguity=true`, `late_external_effects_possible=true`,
`canonical_external_state_claimed=false`, `admission_authorized=false`,
`release_authorized=false`, `outstanding_token_request_count=0`,
`outstanding_operation_dispatch_count=0`, `live_token_count=0`, nullable
`no_later_effects_root_sha256`, `recorded_at`, and
`fenced_write_ambiguity_sha256`.

`terminal_event_type` is exact and route-derived:
`initial_complete_premerge -> PERMANENT_STOP`,
`initial_invalid_premerge -> INVALID_PUBLICATION_PLAN_INVALIDATED`, and
`correction_premerge -> CORRECTION_INVALIDATED`; it byte-equals the intent's nested route and is
not caller-selectable. All three routes require the exact established
`PublicationTerminalMergeBarrierV1`, a null merge
observation and a null no-later root. If preflight or barrier work observes a merge/main change, this
schema is forbidden; the exact ambiguity/containment roots instead extend the phase-specific
`PostMergeAdmissionFailureV1` and route to `RESULT_MERGE_INVALIDATED`,
`INVALID_PREFIX_MERGE_INVALIDATED`, or correction `merged_invalid`. The release-ledger snapshot has identical
scope, an empty entry array and zero authorization/mint/dispatch counts. `recorded_at`
equals the sealed publisher-set time and signed empty release-ledger time and is not before barrier
time. This record is forbidden from every ordinary delivery resolution,
`reconciliation_sourced_zero_effect`, `PublicationNoLaterEffectsEvidenceV1`,
`PublicationSuccessFinalityEvidenceV1`, successful merge admission, release preparation,
documentation and social authority. Its domain is
`laconian-publication-fenced-write-ambiguity-v1\n`, omitting only its final digest.

The normative hash DAG is acyclic through the final disposition set: ambiguity-source dispatch/terminal/
closure receipts → source dispositions → ambiguity subjects/set → preflight read receipts and
closed dispositions → preflight → denylist and intent → accepted containment CAS → post-CAS
receipts/observations/actions → their closed dispositions → complete barrier-disposition subset →
barrier → `terminalizing -> terminal_reconciling` prefix → fence attachment → attachment ledger
entry → sealed ledger/vault → final disposition set. It then has exactly two disjoint suffixes.
Premerge is final set → fenced ambiguity record → premerge finality → terminal authority event.
Merge-won is final set → `PublicationContainmentMergeWonEvidenceV1` → merge-won finality →
`PostMergeAdmissionFailureV1` → phase-exact merge-invalidation event; no fenced ambiguity record is
constructed on that suffix.
A barrier naming a final set, attachment naming its own ledger/final set, subject disposition naming
the subject/set, or any reverse digest is invalid.
Every ambiguity/intent/CAS/denylist/barrier/subset root duplicated by the applicable fenced record
or merge-won evidence, attachment and final set is byte-equal. Attachment subjects are the exact ordered projection of the outer
ambiguity set; aligned source dispositions are exactly the final set's
`write_delivery_ambiguous` members. The barrier prefix is the exact canonical subset of the final
set, with no extra/missing source or containment member.

`PublicationContainmentMergedCandidateV1` has exactly
`schema_version="PublicationContainmentMergedCandidateV1"`, positive
`pull_request_number`, `pull_request_node_id`, `pull_request_marker`,
`pull_request_url`, `observed_base_oid`, `head_oid`, `merge_oid`, `merged_at`,
`observed_main_oid`, ordered
distinct `source_observation_sha256s`, ordered distinct
`conflicting_publication_object_sha256s`, and `merged_candidate_sha256`. Sources
are a nonempty exact subset of preflight, queue, marker, timeline and protected-main observations
whose authenticated fields agree. Conflicting objects are preserved, never selected away. Its
domain is `laconian-publication-containment-merged-candidate-v1\n`, omitting its digest.

`PublicationContainmentMergeWonEvidenceV1` has exactly
`schema_version="PublicationContainmentMergeWonEvidenceV1"`, the full publication identity,
`source_kind="ordinary_terminal_disposition"|"write_ambiguity"`, `source_sha256`,
nested exact
`terminal_containment_intent: PublicationTerminalContainmentIntentV1`,
`terminal_containment_intent_sha256`, nested exact
`containment_authority_mutation_receipt: AuthorityMutationReceiptV1(
mutation_kind="campaign_event",event_type="PUBLICATION_TERMINAL_CONTAINMENT_STARTED")`,
`containment_authority_mutation_receipt_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, positive `merged_candidate_count`, ordered
nested exact `merged_candidates: PublicationContainmentMergedCandidateV1`, nullable
`selected_merge_won_candidate_sha256`, ordered distinct
`merged_candidate_pull_request_numbers`, nonnegative `residual_candidate_count`,
ordered distinct `residual_candidate_pull_request_numbers`, nested exact
`residual_terminal_merge_barrier: PublicationTerminalMergeBarrierV1(
barrier_scope="residual_unmerged_after_merge_won")`,
`residual_terminal_merge_barrier_sha256`, nullable nested exact
`merge_won_terminal_disposition: PublicationPRTerminalDispositionV1(outcome="already_merged")`,
nullable `merge_won_terminal_disposition_sha256`, nullable nested exact
`publisher_write_ambiguity_fence_attachment:
PublisherWriteAmbiguityFenceAttachmentV1`, nullable
`publisher_write_ambiguity_fence_attachment_sha256`, nested exact
`publisher_credential_disposition_set: PublisherCredentialDispositionSetV1`,
`publisher_credential_disposition_set_sha256`,
`canonical_external_state_claimed=false`, `admission_authorized=false`,
`release_authorized=false`, `recorded_at`, and
`containment_merge_won_evidence_sha256`. Counts equal array lengths; the two PR arrays are
disjoint and their union is the complete affected candidate set. The residual barrier is required
even at count zero and fences exactly the residual array. Ordinary source requires its exact
original `no_pr|closed` disposition in the intent, a nonnull independently reconstructed merge-won
disposition, a nonnull selected-candidate digest, null attachment pair and stable-or-unavailable
sealed publisher finality. The selected candidate is the deterministic first tuple by authenticated
`merged_at`, then ascending PR number, then merge OID. Its number/node/URL/marker/observed
base/head/merge OID/merged time byte-project exactly into the
`PublicationPRTerminalDispositionV1(outcome="already_merged")`; that disposition's `recorded_at`
equals the selected merged time. No observation from another candidate may fill any field. Write
ambiguity requires the ambiguity set, null ordinary merge-won disposition, a null selected-
candidate digest, nonnull exact attachment pair and `write_ambiguity_fenced_sealed` finality. It preserves every merged
candidate; no selected merge may erase another candidate/conflict. `recorded_at` equals the sealed
publisher-set `observed_at`, is not before the residual barrier time or any candidate `merged_at`,
and, for write ambiguity, is not before attachment `attached_at`. Its domain is
`laconian-publication-containment-merge-won-evidence-v1\n`, omitting its digest.

`PublicationTerminalContainmentFinalityV1` is the only object that an active-containment
terminal consumer may use. It has exactly
`schema_version="PublicationTerminalContainmentFinalityV1"`, the full publication identity,
`finality_kind="ordinary_premerge"|"write_ambiguity_premerge"|"ordinary_merge_won"|
"write_ambiguity_merge_won"`, `source_kind`, `source_sha256`, nested exact
`terminal_containment_intent: PublicationTerminalContainmentIntentV1`,
`terminal_containment_intent_sha256`, nested exact
`containment_authority_mutation_receipt: AuthorityMutationReceiptV1(
mutation_kind="campaign_event",event_type="PUBLICATION_TERMINAL_CONTAINMENT_STARTED")`,
`containment_authority_mutation_receipt_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, `terminal_authority_parent_oid`, nullable
nested exact `terminal_merge_barrier: PublicationTerminalMergeBarrierV1`, nullable
`terminal_merge_barrier_sha256`, nullable nested exact
`fenced_write_ambiguity: PublicationFencedWriteAmbiguityV1`, nullable
`fenced_write_ambiguity_sha256`, nullable nested exact
`merge_won_evidence: PublicationContainmentMergeWonEvidenceV1`, nullable
`merge_won_evidence_sha256`, nested exact
`publisher_credential_disposition_set: PublisherCredentialDispositionSetV1`,
`publisher_credential_disposition_set_sha256`, `required_terminal_event_type`,
`recorded_at`, and `terminal_containment_finality_sha256`. The source matrix is closed:
`ordinary_premerge|ordinary_merge_won` require
`source_kind=ordinary_terminal_disposition`, while both write-ambiguity kinds require
`source_kind=write_ambiguity`; no cross-pair exists. Premerge ordinary requires the source
disposition, all-candidates barrier and stable/unavailable set, with both
ambiguity/merge pairs null. Premerge ambiguity requires the source set, barrier, exact fenced record
and fenced set, with merge pair null. Either merge-won branch requires only the exact merge-won
pair; direct barrier/fenced pairs are null because they are nested by that evidence. Every
duplicated intent/CAS/denylist/source/finality root recomputes. The terminal parent is the current
containment authority OID or a descendant that byte-preserves active intent and denylist; it is
distinct from `source_authority_parent_oid`. Premerge kinds require
`required_terminal_event_type=terminal_containment_intent.premerge_terminal_event_type`; merge-won
kinds require equality to its `merge_won_terminal_event_type`.
For ordinary premerge, `recorded_at` equals the sealed publisher-set time; for ambiguity premerge it
equals the fenced record time; for either merge-won kind it equals the merge-won evidence time.
Its domain is `laconian-publication-terminal-containment-finality-v1\n`, omitting its digest.

The normal constructive sibling is `PublicationMergeEligibilityReceiptV1`, with exactly
`schema_version`, the same campaign/registry/publication/attempt/correction/bundle/plan/intent,
`branch_name`, `head_oid`, the same literal `check_context`,
`actor: GitHubAppInstallationIdentityV1(role="publisher")`, positive `check_run_id`,
`status="completed"`, `conclusion="success"`, the same policy and observation roots,
`eligibility_delivery_resolution_sha256`, `request_receipts_root_sha256`, `eligible_at`, and
`publisher_credential_disposition_sha256`, `merge_eligibility_receipt_sha256`. Its domain is
`laconian-publication-merge-eligibility-receipt-v1\n`, omitting only its final digest. The
publisher creates/adopts this preauthorized check on the exact head immediately before PR create;
the credential digest byte-equals the embedded delivery resolution's exact
`PublisherOperationCredentialDispositionV1(operation_kind="merge_eligibility")`, whose token is
closed before any PR-create token may be minted;
the PR receipt and opened event bind it, and post-merge admission proves it was the sole complete-
success check for that App-bound context at merge. Repository provisioning, publication authorization, and every
pre-effect observation instead prove that the sole branch-protection required check is
`laconian/publication-pr-validate` from the frozen GitHub Actions App. The publisher eligibility and
terminal-guard context is distinct protocol evidence consumed by that validator. A terminal guard is a later publisher-App check on the same head/context
and names the eligibility receipt it supersedes exactly when delivery resolution is
`exact_success`; the receipt field is null for `none|conflicting`, while the conflicting resolution
and guard-delivery `superseded_check_run_ids` inventory every actual run/effect. After terminal authority no caller may mint a
new success check. Every attempt and correction uses a distinct head commit whose exact commit
message includes respectively `Laconian-Publication-Attempt: <publication-id>/<20-digit-attempt>`
or `Laconian-Correction-ID: <correction-id>`; intent admission proves that head OID is absent from
the ordered root of all prior terminal publication lineages. A same-head retry is rejected, so a
terminal failure check cannot wedge a later legal replan.

`schema_version` is exactly `PublicationPRTerminalDispositionV1`; `bundle_kind` is `complete` or
`invalid_prefix`; `outcome` is exactly `no_pr`, `closed`, or `already_merged`. Initial publication
uses a positive canonical `publication_attempt`, null `correction_id`, and an `authority_phase` of `initial_intent`,
`initial_branch_receipt`, `initial_pr_receipt`, or `initial_opened`. The first three phases require
the corresponding `BUNDLE_COLLECTED` or `INVALID_FINALIZED` parent; `initial_opened` requires the
matching `COMPLETE_PUBLICATION_PR_OPEN` or `INVALID_PUBLICATION_PR_OPEN` parent. Correction
publication uses null `publication_attempt`, a nonempty authoritative correction ID,
`bundle_kind=complete`, a
`RELEASE_BLOCKED` or `RELEASED` parent, and phase `correction_intent` or
`correction_publication_receipt`. Every field is present. `branch_receipt_sha256` is null exactly
at `initial_intent` and in both correction phases; it is nonnull in every later initial phase.
`pull_request_receipt_sha256` is nonnull exactly at `initial_pr_receipt`, `initial_opened`, or
`correction_publication_receipt`; response loss may therefore leave it null while exact-marker
discovery independently observes a PR in an earlier authority phase.
`branch_create_delivery_resolution_sha256`, `pr_marker_discovery_sha256`, and
`pr_create_delivery_resolution_sha256` are always the exact nonnull class-bound resolutions for
this intent. `branch_outcome` is exactly `absent`, `exact`, or `conflicting` and equals the branch
resolution. `terminal_guard_set_sha256` is nonnull for `closed`, for `no_pr` with
`branch_outcome=exact|conflicting` or PR delivery status `conflicting`, and for `already_merged` whenever any guard dispatch may have
delivered. It is null for `no_pr` exactly when branch outcome is absent, PR delivery status is
`none`, marker discovery has zero matches, and no guard dispatch occurred; a check/branch/PR
conflict always requires the complete set. It may be null for
`already_merged` only when pre-guard discovery proved the merge and no guard dispatch occurred.
Every nonnull set is fully reconciled and post-write reverified before terminal candidate
construction. `close_delivery_resolution_sha256` is null exactly for `no_pr` and otherwise names
the exact close/merge resolution.
The PR delivery status is `none|conflicting` with null number for `no_pr`; `closed` requires
`exact` with number equal to the disposition. `already_merged` permits `exact` or `conflicting` and
requires the same positive selected merged number. In the conflicting case the selected discovery
match is the deterministic earliest authenticated merge described by the delivery resolution; all
other matches remain conflict evidence and cannot authorize admission or release.

For `no_pr`, the PR number, node ID, URL, observed base/head, merge OID, close kind, close receipt,
and closed observation are all
null; the phase is `initial_intent`, `initial_branch_receipt`, or `correction_intent`, the create-
delivery resolutions prove no branch or PR request remains ambiguous, and bounded, fully paginated
exact-marker discovery proves zero unique admissible plan PR. Foreign, duplicate, or mismatched
marker matches are not called absent: they are fully inventoried as conflicts and every candidate
head is guarded. A non-absent branch or any conflict additionally requires the complete guard set;
only an absent branch with zero marker matches permits that set null. For `closed`, the PR number is a positive canonical
integer, node ID/URL and observed base/head are nonempty, the merge OID is null, and
`closed_observation_sha256` names the authenticated closed-PR observation.
`close_kind=publisher_closed` additionally requires the exact nonnull publisher-App
`close_receipt_sha256`; `close_kind=observed_already_closed` requires that receipt null and proves
the PR was already closed unmerged before the handler could act. The former requires close
resolution `publisher_close_confirmed|publisher_close_adopted`; the latter requires
`already_closed_no_dispatch`. Both require the exact failed
guard set over every possibly mergeable head; a later reopen cannot pass the required check or
merge because the Actions validator re-reads the persistent denylist, irrespective of the
publisher-App guard context. For
`already_merged`, the same PR identity fields and a lowercase 40-hex observed merge OID are
nonnull, closed observation is null, and close resolution is `merge_won`. If that resolution has a
nonnull prior-close receipt, `close_kind=publisher_closed_then_reopened_merged` and
`close_receipt_sha256` byte-equals it; otherwise both fields are null;
authenticated discovery
proves that this exact PR merged
before close completed. Expected base/head always equal the plan; observed base/head preserve the
authenticated PR even when they differ. `identity_mismatch_predicates` is the canonical schema-
ordered subset of `base_oid_mismatch` and `head_oid_mismatch`, empty exactly when both match, and
must byte-equal the consuming plan-invalidation or failed-admission predicates. The marker and
marker-discovery root are always nonnull and intent-bound. When the guard set is nonnull, the
disposition marker-discovery digest equals its `final_pr_marker_discovery_sha256`, and
`branch_outcome`/observed branch head derive from its exact final branch observation. When the set
is null, they equal the terminal pre-guard observations. For a PR outcome, the discovery match's
number/node/URL/base/head/state/merge tuple byte-equals both final close-resolution observations and
the closed observation or merge-won projection as applicable; no independently valid observation
from another round may be substituted;
`recorded_at` is deterministic canonical whole-second UTC: for `no_pr` it equals the final
`PublicationPRMarkerDiscoveryV1.observed_at`, for `closed` it equals the authenticated current PR
`closed_at` reproduced by the strict closed observation, and for `already_merged` it equals the
authenticated PR `merged_at`. The
class-bound terminal observation in `pr_marker_discovery_sha256` must reproduce that same source
timestamp. Initial complete, initial invalid-prefix, and
correction identities cannot substitute for one another.

Canonical bytes are RFC 8785 JSON in the exact field set above, UTF-8 without a terminal newline.
The digest is
`SHA256(UTF8("laconian-publication-pr-terminal-disposition-v1\n") ||
CanonicalJSONV1(record without exactly publication_pr_terminal_disposition_sha256))`. Missing,
extra, half-null identity groups, mismatched phase/parent/receipt, guessed PR numbers,
uninventoried or unguarded duplicate marker matches, fabricated close effects, and `closed` after a
merge are rejected. `no_pr` or
`closed` may authorize only the
phase-appropriate typed STOP, supplement, plan invalidation, or correction invalidation;
`already_merged` may authorize only the matching typed failed-admission event. The latter event
must embed this exact record and no caller may relabel a merged PR as absent or closed.

`credential_exposure` is not encoded as generic `security`, `artifact_failure`, or another alias.
For that reason, `CampaignStateSchemaV1` requires a
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
credential_exposure_pending_sha256
consumed_active_pending_root
terminal_effect_receipts_root
concurrent_protocol_authority_drift_evidence_sha256
secret_kind
affected_artifacts
scanner_receipt
credential_containment
artifact_quarantine_receipt_sha256
no_further_campaign_download_receipt_sha256
publication_pr_terminal_disposition_sha256
complete_publication_pr_disposition
complete_publication_pr_close_receipt_sha256
invalid_publication_pr_disposition
invalid_publication_pr_close_receipt_sha256
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
`credential_exposure_pending_sha256` must name the unique unresolved pending record consumed by
this final event. `consumed_active_pending_root` equals the predecessor state's active progress root
and `terminal_effect_receipts_root` equals its completed effect chain.
`concurrent_protocol_authority_drift_evidence_sha256` is the exact drift root when
drift coexists and is literal null only when the pending record's fresh check proved no drift.
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
`publication_pr_terminal_disposition_sha256` is nonnull exactly when an initial or correction
publication segment is active before a valid admitted merge and its PR absence/close/merge must be
terminalized. It is null in every other phase, including `RESULT_MERGED`, an initial release prefix,
a correction after valid merge, and a bare post-merge state. When nonnull it names the one exact
`PublicationPRTerminalDispositionV1` built from reconstructed authority and fully paginated marker
discovery. For an initial prefix, the two legacy phase-specific disposition fields below are strict
projections of that record; for a correction prefix they are both `not_applicable` while the shared
root is nonnull and correction-bound. No caller-supplied PR number or status is accepted.
`complete_publication_pr_disposition` is exactly `not_applicable`, `no_pr`,
`closed_before_stop`, `merged_before_close`, or `closed_then_reopened_merged`. It may be applicable only at
`COMPLETE_PUBLICATION_PR_OPEN` or at `BUNDLE_COLLECTED` with an authoritative active initial
complete-publication intent/branch/PR prefix. `no_pr` is allowed only at that pre-open prefix when
bounded exact-marker discovery proves no unique admissible or merged plan PR and every conflict
head is guarded; its close receipt is null. `closed_before_stop`
requires shared outcome `closed` and authorizes only the existing premerge credential STOP. Its
close receipt is nonnull and equal for `publisher_closed`, or null for
`observed_already_closed`, whose nonnull strict closed observation is carried by the shared record.
`merged_before_close` requires a null close receipt, independently proves that the
intent-bound PR became merged before the close effect could complete, and authorizes only typed
`RESULT_MERGE_INVALIDATED`. `closed_then_reopened_merged` instead requires the shared
`publisher_closed_then_reopened_merged` close kind and byte-identical nonnull prior-close receipt,
and authorizes the same failed-admission event. Every other parent or a `BUNDLE_COLLECTED` tree with no active initial
prefix uses `not_applicable` and a null close receipt. A merged PR is never described as closed, and
no disposition can substitute for another. Its projection maps shared outcome
`no_pr|closed` to `no_pr|closed_before_stop`; `already_merged` maps to `merged_before_close` when
the shared close receipt is null and `closed_then_reopened_merged` when it is nonnull, and
its close-receipt field byte-equals the shared record's nullable field.
`invalid_publication_pr_disposition` is independently exactly `not_applicable`,
`no_pr`, `closed_before_supplement`, `merged_before_close`, or
`closed_then_reopened_merged`. It may be applicable only at
`INVALID_PUBLICATION_PR_OPEN` or at `INVALID_FINALIZED` with an authoritative active initial
invalid-prefix intent/branch/PR prefix. `no_pr` is allowed only at that pre-open prefix when bounded
exact-marker discovery proves no unique admissible or merged plan PR and every conflict head is
guarded; its close receipt is null. `closed_before_supplement` requires
shared outcome `closed` and authorizes only the invalid-lineage supplement followed by the ordinary
typed invalid-prefix plan invalidation. Its close receipt is nonnull/equal for `publisher_closed`
or null with the shared nonnull strict observation for `observed_already_closed`;
`merged_before_close` requires a null close
receipt and authorizes only race-form `INVALID_PREFIX_MERGE_INVALIDATED`;
`closed_then_reopened_merged` requires the shared nonnull prior-close receipt and authorizes that
same race event. Every other parent or an
`INVALID_FINALIZED` tree with no active initial prefix uses `not_applicable` and a null close
receipt. Complete and invalid-prefix dispositions cannot both be applicable.
Its projection maps shared outcome `no_pr|closed` to
`no_pr|closed_before_supplement`; `already_merged` maps by null versus nonnull prior-close receipt
to `merged_before_close|closed_then_reopened_merged`, and its close-receipt field
byte-equals the shared record's nullable field. For an active correction, shared `no_pr` or `closed`
authorizes only `CORRECTION_INVALIDATED(... publication_outcome=unmerged_invalid)`, while
`already_merged` authorizes only its `merged_invalid` sibling. Both initial-projection fields remain
`not_applicable` in that correction case.

Canonical bytes are RFC 8785 JSON over those exact fields excluding the final digest, UTF-8 with no
terminal newline; timestamps are UTC RFC 3339, IDs are canonical integers, roots are lowercase
64-hex SHA-256, and extra, missing, null-where-forbidden, duplicate, or reordered array members are
rejected. The final digest is SHA-256 of
`UTF8("laconian-credential-exposure-incident-evidence-v1\n") || CanonicalJSONV1(evidence without
exactly credential_exposure_incident_evidence_sha256)`. The evidence is safe metadata only and cannot
contain the suspected credential bytes.

The same closed reason enum contains `protocol_authority_drift`. It is a STOP reason from every
post-seal prepublication state, including `PREFLIGHTED`, and the same evidence class is also the
non-STOP defect evidence for the exact post-merge and correction routes below. It requires
`ProtocolAuthorityDriftEvidenceV1` with exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `parent_state`, `parent_authority_oid`, `unresolved_hold_root`,
`protocol_attestation_tag_binding_sha256`, `observed_input_ref_oid`,
`observed_companion_ref_oid`, `observed_tag_ruleset_policy_root`, `failed_predicates`,
`verification_receipts_root`, `publication_pr_terminal_disposition_sha256`, `observed_at`, and
`protocol_authority_drift_evidence_sha256`. `parent_state` and `parent_authority_oid` always name
the exact current state/phase, including a reconstructed correction prefix. An observed ref OID is null only when an exact
authenticated absence receipt proves deletion. `failed_predicates` is a nonempty canonical ordered
subset of `input_ref_moved`, `input_ref_deleted`, `companion_ref_moved`,
`companion_ref_deleted`, `object_oid_mismatch`, `raw_object_sha256_mismatch`, `closure_mismatch`,
`ruleset_drift`, `tag_creator_mismatch`, `creation_authorization_mismatch`, `signature_identity_mismatch`, `topology_mismatch`, and
`cross_campaign_replay`. Its digest is SHA-256 of
`UTF8("laconian-protocol-authority-drift-evidence-v1\n") || CanonicalJSONV1(evidence without
exactly protocol_authority_drift_evidence_sha256)`. The event changes no external object, cannot adopt
restored refs, and its prepublication STOP use enters `STOPPED_INVALID`. The terminal-disposition
root is nonnull exactly at a `BUNDLE_COLLECTED` parent with an active initial complete-publication
prefix, at `COMPLETE_PUBLICATION_PR_OPEN`, or during an active correction before a valid merge; it
is null at every other parent. For the initial prefix, `no_pr` or `closed` permits the typed drift
STOP, while `already_merged` permits only
`RESULT_MERGE_INVALIDATED(failure_kind=protocol_authority_drift_race)`. For a correction prefix,
`no_pr` or `closed` permits only publication-family `CORRECTION_INVALIDATED(cause=protocol_authority_drift,
publication_outcome=unmerged_invalid)`, while `already_merged` permits only its `merged_invalid`
sibling with the drift-race failure. After a valid initial or correction merge the exact release-
invalidation route binds this evidence with a null disposition. At bare `RELEASE_BLOCKED` or
`RELEASED`, only the drift-typed correction-intent route applies. No post-merge form emits STOP.
When `unresolved_hold_root` is nonnull, drift evidence binds that consumed root and the STOP
successor sets it null; null means proven absence, never “not checked.”

`InvalidEventDismissalEvidenceV1` has exactly `schema_version`, `campaign_id`, `hold_id`,
`hold_sha256`, `invalid_event_dismissal_plan_sha256`, `parent_authority_oid`, `parent_state`, `proof_kind`, `no_effects_root`,
`dismissal_reviewer_account_id`, `dismissal_reviewer_login`, `dismissal_signature_root`,
`dismissed_at`, and `invalid_event_dismissal_evidence_sha256`, using
`laconian-invalid-event-dismissal-v1`. `proof_kind` is exactly `authenticated_noop` or
`byte_identical_applied_replay`; either proves no state, ledger, artifact, reservation, credential,
provider, or external effect. `benchmark-dismiss-hold.yml`, under approval by an actor distinct
from the rejected source/trigger, appends `holds/<hold-id>/dismissal.json` and
`INVALID_EVENT_DISMISSED` by expected-OID CAS. This is a self-loop: state name is unchanged,
transition advances, and exactly that one current `unresolved_hold_root` becomes null.
The dismissal digest is SHA-256 of `UTF8("laconian-invalid-event-dismissal-v1\n") ||
CanonicalJSONV1(evidence without exactly invalid_event_dismissal_evidence_sha256)`.

Before that workflow requests a mutation it seals `InvalidEventDismissalPlanV1` with exactly
`schema_version`, `campaign_id`, `campaign_registry_sha256`,
`invalid_event_dismissal_policy_sha256`, `hold_id`, `hold_sha256`, `parent_state`,
`parent_authority_oid`, `eligible_dismisser_account_id`, `eligible_dismisser_login`, `proof_kind`,
`authorized_dispatcher_workflow`, `authorized_dispatcher_ref`, `expected_no_effects_root`,
`planned_at`, and `invalid_event_dismissal_plan_sha256`. The dispatcher fields are exactly
`benchmark-dismiss-hold.yml` and the plan-bound protected-main ref. The selected
identity is one frozen eligible projection and is distinct from the rejected request actor. Its
digest is SHA-256 of `UTF8("laconian-invalid-event-dismissal-plan-v1\n") || CanonicalJSONV1(plan
without exactly invalid_event_dismissal_plan_sha256)`. Dismissal evidence binds this plan root and
exact approved actor; an ambient maintainer, changed plan, or plan for another hold is rejected.

For a nondismissible verified defect before merge, a valid `PERMANENT_STOP` cites the hold and takes
the enumerated invalid path and its successor explicitly clears `unresolved_hold_root`; its
ordinary evidence binds the consumed hold root. At `RESULT_MERGED`, `RELEASE_PLAN_INVALIDATED`
binds and consumes the hold and enters `RELEASE_BLOCKED`. At `RELEASED`, the applicable typed
correction nondismissible/exposure/invalidation/drift intent binds and consumes it while preserving
terminal history.
Dismissal is the only other consuming exit. The only two no-prior-hold exceptions are `credential_exposure` and
`protocol_authority_drift`; their typed evidence must prove the exact current hold root or proven
absence as specified above. At `RESULT_MERGED`, the defect uses `RELEASE_PLAN_INVALIDATED`; at `RELEASED`, the state
remains terminal and the defect starts a new correction lineage with an explicit `supersedes` hash.

`HeldReleasedConsumptionV1` is a strict `kind`-discriminated union of exactly four records; no
wrapper, generic evidence hash, or fallback member exists. The consuming `CorrectionIntentV1`
also embeds `CorrectionDefectRecordV1`, which has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `parent_state="RELEASED"`, `parent_authority_oid`, `defect_class`,
`defect_code`, `evidence_sha256`, `hold_root_sha256`, and `correction_defect_record_sha256`, using
domain `laconian-correction-defect-record-v1\n`. Its evidence hash equals the selected union
member's `consumption_sha256`; it is outside that member so neither digest is self-referential.

`NondismissibleHeldReleasedConsumptionV1` has exactly
`schema_version="NondismissibleHeldReleasedConsumptionV1"`, `kind="nondismissible"`,
`campaign_id`, `campaign_registry_sha256`, `parent_state="RELEASED"`, `parent_authority_oid`,
`hold_id`, `hold_root_sha256`, `hold_admission_event_sha256`, nested exact
`nondismissibility_evidence: InvalidEventNondismissibilityEvidenceV1`, and
`consumption_sha256`. The nested evidence names the same released parent/OID and accepted hold; its
rejected-request and failed-validation projection byte-equals the accepted `InvalidEventHoldV1`.
Its domain is `laconian-nondismissible-held-released-consumption-v1\n`, omitting only its final
digest.

`ExposureHeldReleasedConsumptionV1` has exactly
`schema_version="ExposureHeldReleasedConsumptionV1"`, `kind="exposure"`, `campaign_id`,
`campaign_registry_sha256`, `parent_state="RELEASED"`, `parent_authority_oid`, `hold_id`,
`hold_root_sha256`, `hold_admission_event_sha256`, nested exact
`terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1`, and
`consumption_sha256`. The terminal consumer's campaign/registry, incident parent/OID, and consumed
hold identity equal this record. Its domain is
`laconian-exposure-held-released-consumption-v1\n`, omitting only its final digest.

`InvalidationHeldReleasedConsumptionV1` has exactly
`schema_version="InvalidationHeldReleasedConsumptionV1"`, `kind="invalidation"`, `campaign_id`,
`campaign_registry_sha256`, `parent_state="RELEASED"`, `parent_authority_oid`, `hold_id`,
`hold_root_sha256`, `hold_admission_event_sha256`,
`source_kind="initial_release_invalidation"|"correction_release_invalidation"`,
`typed_invalidation_evidence_sha256`, `terminal_invalidation_record_path`,
`terminal_invalidation_record_sha256`, `invalidation_event_path`, `invalidation_event_sha256`, and
`consumption_sha256`. Both paths are canonical authority-derived paths, never caller-selected. The
event path resolves in accepted ancestry to exactly one `RELEASE_PLAN_INVALIDATED` or release-family
`CORRECTION_INVALIDATED` event; that event transitively binds the separate terminal invalidation
record and typed evidence roots, which must equal the two fields here. Its domain is
`laconian-invalidation-held-released-consumption-v1\n`, omitting only its final digest.

`DriftHeldReleasedConsumptionV1` has exactly
`schema_version="DriftHeldReleasedConsumptionV1"`, `kind="drift"`, `campaign_id`,
`campaign_registry_sha256`, `parent_state="RELEASED"`, `parent_authority_oid`, `hold_id`,
`hold_root_sha256`, `hold_admission_event_sha256`, nested exact
`protocol_authority_drift_evidence: ProtocolAuthorityDriftEvidenceV1`, and `consumption_sha256`.
The drift evidence names that same released parent/OID/hold. Its domain is
`laconian-drift-held-released-consumption-v1\n`, omitting only its final digest.

For every member, campaign/registry/parent/hold fields equal reconstructed current authority and
`hold_admission_event_sha256` names the accepted `INVALID_EVENT_HELD` event whose rejected request,
failed validation and installed hold equal the selected evidence. The union is nonnull exactly when
a bare `RELEASED` parent has one unresolved hold and is forbidden at `RELEASE_BLOCKED` or during an
active correction prefix. Kind maps one-to-one to defect class/code
`nondismissible_hold/nondismissible_invalid_event`,
`credential_exposure/post_merge_credential_exposure`,
`invalidation_hold/accepted_release_invalidation`, or
`protocol_authority_drift/persistent_protocol_authority_drift`; the sibling
`CorrectionDefectRecordV1` must reproduce that mapping and consumption digest. The consuming intent
CAS clears exactly the hold. Non-exposure variants require the active exposure pair and terminal
exposure field null; exposure requires and clears the exact nonnull pair. No member may name the
future correction intent/event, successor OID, or successor state root. All four use RFC 8785 JSON
and the stated LF-terminated domain.
Correction invalidations have exactly two distinct kinds:
`correction_publication_invalidation` and `correction_release_invalidation`. Their schemas,
allowed parents, and evidence are distinct; a generic correction-invalidation alias is forbidden.

`CREDENTIAL_EXPOSURE_PENDING` and `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` are constructive closed
events. The pending event requires exactly `CredentialExposurePendingV1`,
`incidents/<incident-id>/pending.json`, and
`denylist/provisional/<incident-id>.json`; it is a self-loop that advances the transition and sets
the two active pending fields. The effect event requires exactly one next ordinal
`CredentialExposureEffectReceiptV1` at
`incidents/<incident-id>/effects/<8-digit-ordinal>.json`; that schema has exactly
`schema_version`, `campaign_id`, `incident_id`, `pending_root`,
`predecessor_active_pending_root`, `effect_ordinal`, `effect_kind`,
`external_object_id`, `idempotency_key`, `requested_state_root`, `observed_terminal_state`,
`request_receipts_root`, `recorded_at`, and `credential_exposure_effect_receipt_sha256`, whose digest
is SHA-256 of `UTF8("laconian-credential-exposure-effect-receipt-v1\n") ||
CanonicalJSONV1(receipt without exactly credential_exposure_effect_receipt_sha256)`. The event
is a self-loop that advances transition and pending-progress root without changing campaign state.
Every receipt's `campaign_id` and `incident_id` byte-equal its unique originating
`CredentialExposurePendingV1`, and `pending_root` equals that record's
`credential_exposure_pending_sha256`; a cross-campaign, cross-incident, or cross-pending value is
invalid even when the predecessor progress root and ordinal otherwise verify.

When an active initial or correction publication prefix may have a PR, its pending inventory has
exactly one `effect_kind="publication_pr_terminal_disposition"` ordinal rather than an unconditional
close item. `observed_terminal_state` is exactly `no_pr`, `closed`, or `already_merged`.
`external_object_id` is the canonical PR number for `closed|already_merged` and the literal
`none` for `no_pr`; `request_receipts_root` binds complete bounded exact-marker discovery,
the strict publisher-close-plus-observation or already-closed observation for `closed`, or exact
PR/merge/current-main observation for `already_merged`. `no_pr` is legal only before an
authoritative PR-open receipt and proves zero unique admissible or merged plan PRs while preserving
and guarding every conflict; `closed` requires one exact close-kind
branch; `already_merged` binds the observed merge and preserves any reconciled prior close instead
of claiming none occurred. All three outcomes complete that one ordinal. For an initial complete
prefix they map to `no_pr`, `closed_before_stop`, and either `merged_before_close` or
`closed_then_reopened_merged`; for an initial invalid prefix, to `no_pr`,
`closed_before_supplement`, and the same receipt-qualified merged pair; for a correction prefix, to unmerged no-PR invalidation, unmerged closed-PR
invalidation, and race-form `merged_invalid`. Outcome/disposition mismatch, a second PR ordinal, or
claiming close after merge is rejected.
For this effect kind, `requested_state_root` is not generic: it equals the recomputed
`publication_pr_terminal_disposition_sha256`. The receipt's terminal state, external PR ID,
request-receipt root, branch/PR/create/check/guard/close roots and observations are the exact
class-bound projection of that record, and the final incident, supplement or failed-admission
consumer embeds those same canonical bytes. Substituting a disposition from another valid effect
chain is rejected.

`CredentialExposureProgressRootV1` is a calculated projection, not a stored self-containing
record. Its exact fields are `schema_version`, `campaign_id`, `incident_id`,
`credential_exposure_pending_sha256`, `last_effect_ordinal`, and `effect_chain_root`.
The initial projection uses `last_effect_ordinal: null` and
`effect_chain_root = SHA256(UTF8("laconian-credential-exposure-effect-chain-empty-v1\n") ||
CanonicalJSONV1({campaign_id,incident_id,credential_exposure_pending_sha256}))`.
`active_credential_exposure_pending_root` is
`SHA256(UTF8("laconian-credential-exposure-progress-root-v1\n") ||
CanonicalJSONV1(the exact six-field projection))`; it has no stored self field. Effect ordinals
start at integer 1, advance by exactly one, and path-format as eight zero-padded decimal digits.
Each successor `effect_chain_root` is
`SHA256(UTF8("laconian-credential-exposure-effect-chain-link-v1\n") ||
CanonicalJSONV1({predecessor_active_pending_root,effect_ordinal,
credential_exposure_effect_receipt_sha256}))`; the next progress root is then computed from that
chain root and ordinal. `terminal_effect_receipts_root` is exactly the final `effect_chain_root`.

`TerminalCredentialExposureConsumptionV1` is the one strict post-merge terminal projection. Its
exact fields are `schema_version`, `campaign_id`, `campaign_registry_sha256`, `incident_id`,
`credential_exposure_pending_sha256`, `predecessor_active_pending_root`,
`terminal_effect_receipts_root`, nested exact `credential_exposure_incident_evidence`,
`concurrent_protocol_authority_drift_evidence_sha256`, nullable
`consumed_unresolved_hold_id`, nullable `consumed_unresolved_hold_root_sha256`, and
`consumption_sha256`. The two hold fields are both null or both identify the one current hold copied
through pending/final evidence. Its digest is
`SHA256(UTF8("laconian-terminal-credential-exposure-consumption-v1\n") ||
CanonicalJSONV1(record without exactly consumption_sha256))`. Construction replays every ordinal,
requires one campaign/registry/incident/pending root, equates the predecessor progress and terminal
effect-chain roots to the final incident evidence, and copies the originating concurrent-drift
root. It contains no consuming-event hash, successor authority OID, or future root; terminal
event construction is therefore acyclic. Cross-incident, gapped, reordered, substituted-drift, or
half-null-hold records fail before a terminal event is built.

The pending and effect events are permitted from exactly the existing premerge parents
`GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`,
`JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`,
`AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED`, and
`COMPLETE_PUBLICATION_PR_OPEN`; from `RESULT_MERGED`; from `RELEASE_BLOCKED` or `RELEASED` with no
active correction or with exactly one valid nonterminal correction prefix; and from the
artifact-bearing invalid states `STOPPED_INVALID`, `BUDGET_INCOMPLETE`, `INVALID_FINALIZED`,
`INVALID_PUBLICATION_PR_OPEN`, `INVALID_PREFIX_MERGED`, and
`INVALID_PREFIX_MERGED_INVALID`. These added rows grant emergency containment only and do not
authorize live resume, release, correction promotion, documentation, or social effects. Pending
requires both active fields null; effect requires both to match the exact incident and current
progress root. `INVALID_EVENT_HELD` is ineligible whenever a `RELEASED` or `RELEASE_BLOCKED`
authority tree contains an active nonterminal correction prefix; the generated guard reconstructs
the correction phase rather than considering the campaign-state name alone.

The terminal consumer is phase-exact. Existing premerge parents use
`PERMANENT_STOP(reason=credential_exposure)`. A complete initial-publication prefix, whether still
at `BUNDLE_COLLECTED` or already `COMPLETE_PUBLICATION_PR_OPEN`, uses that STOP after `no_pr` proof
or `closed_before_stop`; if its PR is externally merged before close, only
`RESULT_MERGE_INVALIDATED` may consume the completed chain and it enters `RELEASE_BLOCKED`.
An invalid-prefix initial-publication prefix, whether still at `INVALID_FINALIZED` or already
`INVALID_PUBLICATION_PR_OPEN`, uses the invalid-lineage supplement after `no_pr` proof or
`closed_before_supplement`, then the ordinary typed plan invalidation; if its PR is externally
merged first, only race-form `INVALID_PREFIX_MERGE_INVALIDATED` consumes the chain and enters
`INVALID_PREFIX_MERGED_INVALID`.
`RESULT_MERGED` uses `RELEASE_PLAN_INVALIDATED`, both before and after an authoritative initial
release intent. Bare `RELEASE_BLOCKED` or `RELEASED` uses `CORRECTION_INTENT_AUTHORIZED`; a held
`RELEASED` parent additionally admits typed `protocol_authority_drift` as the fourth discriminator
beside nondismissible, exposure, and invalidation evidence. An active correction before a valid
correction merge uses its publication-family `CORRECTION_INVALIDATED`; after a valid merge it uses
its release-family `CORRECTION_INVALIDATED`. Each post-merge consumer requires the exact
`TerminalCredentialExposureConsumptionV1`, clears the active incident/root pair and matching
optional hold atomically, preserves every contaminated merge/tag/Release/history root, and blocks
the ordinary next phase. Terminalizing an active correction requires the next correction ID to
supersede both that failed prefix and the exposure root.
Every active initial-publication prefix was created with a null hold and is itself hold-ineligible;
therefore either initial merge-before-close event requires `unresolved_hold_root=null`. An active
correction prefix is likewise hold-ineligible. Optional-hold consumption applies only to the
separately enumerated `RESULT_MERGED` release-invalidation and bare `RELEASED` correction-start
forms, never to an initial or correction PR race.

The artifact-bearing invalid states use `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED` as a self-loop,
except for the invalid-prefix merge-before-close race above. For
`INVALID_PUBLICATION_PR_OPEN`, or `INVALID_FINALIZED` with an active initial invalid prefix, its
inventoried effects include publisher-App closure of that exact invalid-prefix PR before the
supplement when a PR exists; every other such parent forbids a PR-close field.
The supplement records containment and disclosure, consumes the exact progress root, clears both
active fields, requires the hold root null, preserves the terminal/invalid state, and grants no live
authority. A `STOPPED_INVALID` parent is no longer restricted to a prior drift reason.

For every terminal form, final validation requires each `pending_effect_inventory` item and ordinal
exactly once, `consumed_active_pending_root` equal to the predecessor state's current progress root,
and `terminal_effect_receipts_root` equal to its completed chain before both active fields clear.
All ordinary events require the active pair null.

The allowed durable transitions are:

Every phase-qualified terminal row below has two disjoint admission forms. The direct form is legal
only when no active publication/correction effect prefix exists, for a normal postmerge admission
that was not sourced from terminal disposition, or for release-only invalidation after publication
admission; it additionally requires `active_publication_terminal_containment_root=null` and cannot
carry containment fields. A root-null active publication/correction prefix is eligible only to
start containment, never to skip it. Every `no_pr|closed` terminal disposition, every publication
write ambiguity, and every terminal-disposition merge race must first accept containment start and
then use the containment form. The containment form is legal only after the immediately bound
`PUBLICATION_TERMINAL_CONTAINMENT_STARTED` successor (or a descendant that byte-preserves its
active root and denylist), and requires nested exact `PublicationTerminalContainmentFinalityV1`,
`source_authority_parent_oid` equal to the intent's source parent, `authority_parent_oid` equal to
the finality terminal parent, the same permanent successor denylist,
`active_publication_terminal_containment_root_before=terminal_containment_intent_sha256`, and
`active_publication_terminal_containment_root_after=null`. `no_pr|closed` uses exactly
`ordinary_premerge` or `write_ambiguity_premerge`; any authenticated merged candidate uses exactly
`ordinary_merge_won` or `write_ambiguity_merge_won`. A reconciliation-unavailable terminal
disposition therefore takes the premerge form only for `no_pr|closed` and the merge-won form only
for `already_merged`. The terminal CAS preserves the denylist and atomically clears the active
root. No other transition below may consume, clear, replace, or silently preserve a nonnull active
containment root.

| From | Event and required evidence | To | Authorized next action |
|---|---|---|---|
| none | `PREFLIGHT_SEALED`: valid annotated T0/T1 pair, double-read object closure and ruleset receipts, canonical `CampaignRegistryV1` and companion binding, plans, budget, price snapshot, canonical `StateWriterGitIdentityV1`, parentless authority commit, and atomic `expected_absent` ref creation | `PREFLIGHTED` | prepare generation batch |
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
| `BUNDLE_COLLECTED` | `PUBLICATION_INTENT_AUTHORIZED`: exact `bundle_kind=complete`, deterministic branch/PR identities, effect roots, actors, and idempotency keys | `BUNDLE_COLLECTED` | create or adopt exact complete branch/PR |
| `BUNDLE_COLLECTED`, `COMPLETE_PUBLICATION_PR_OPEN`, `INVALID_FINALIZED`, `INVALID_PUBLICATION_PR_OPEN`, `RELEASE_BLOCKED`, or `RELEASED`, each with the exact active publication/correction prefix and null active containment root | `PUBLICATION_TERMINAL_CONTAINMENT_STARTED`: ordinary source requires exact `no_pr|closed`; either source permits preflight `merge_state=all_unmerged|merge_observed`; both require cycle-free preflight, one monotone denylist append, signed terminalizing broker/vault prefixes with zero open requests/dispatches/live tokens, and expected-OID CAS | same state name with active containment root | if preflight was all-unmerged run only the post-CAS all-candidates barrier; if it observed a merge classify merge-won and fence the residual set |
| `BUNDLE_COLLECTED` | `COMPLETE_PUBLICATION_PR_OPENED`: exact prior intent, `bundle_kind=complete`, sealed complete-bundle root, publication plan, and adopted/created branch/PR receipts | `COMPLETE_PUBLICATION_PR_OPEN` | review and required CI |
| `BUNDLE_COLLECTED` | `COMPLETE_PUBLICATION_PLAN_INVALIDATED`: base/head moved or plan check failed, bundle digest unchanged; an active containment prefix requires exact premerge finality and clears its root | `BUNDLE_COLLECTED` | direct form may replan normally; containment form may authorize only a new positive attempt that explicitly supersedes the terminal root and uses fresh branch/head/marker/trailer absent from every denylist selector |
| `BUNDLE_COLLECTED` with active initial complete intent/branch/PR prefix and observed merged PR | `RESULT_MERGE_INVALIDATED`: exact `PostMergeAdmissionFailureV1`, merge-won containment finality when containment is active, `PublicationPRTerminalDispositionV1(outcome=already_merged)` for ordinary source or null for write ambiguity, discovered/adopted prefix objects, immutable merge and no-release proof; reconciliation-unavailable instead binds its sealed failure-only set/receipt and zero release-authorization ledger without claiming stable external state; drift or exposure additionally requires its class-bound nested evidence/consumer | `RELEASE_BLOCKED` | start a correction that supersedes the contaminated pre-open publication prefix, every merged candidate, and any exposure root |
| `COMPLETE_PUBLICATION_PR_OPEN` | `RESULT_MERGED`: approved complete-bundle PR, exact matching sealed-root lineage, merge receipt, and `PostMergeAdmissionEvidenceV1` | `RESULT_MERGED` | prepare release plan |
| `COMPLETE_PUBLICATION_PR_OPEN` | `RESULT_MERGE_INVALIDATED`: intent-bound PR is already merged but exact post-merge admission fails; an active containment prefix requires exact merge-won finality, merge-before-close binds the exact terminal disposition for ordinary source, drift or exposure binds its class-bound nested evidence/consumer, and every form preserves immutable merge/no-release evidence | `RELEASE_BLOCKED` | start a correction that explicitly supersedes every contaminated merge and any exposure root |
| `COMPLETE_PUBLICATION_PR_OPEN` | `COMPLETE_PUBLICATION_PLAN_INVALIDATED`: exact complete-bundle PR closed, sealed complete-bundle root unchanged; an active containment prefix requires exact premerge finality and clears its root | `BUNDLE_COLLECTED` | authorize only a new positive attempt that supersedes any terminal root and uses fresh branch/head/marker/trailer absent from every denylist selector |
| `RESULT_MERGED` | `RESULT_RELEASE_INTENT_AUTHORIZED`: deterministic tag/draft-release/asset/publish identities, roots, actors, and idempotency keys | `RESULT_MERGED` | create or adopt exact initial release effects |
| `RESULT_MERGED` | `RESULT_RELEASED`: exact prior release intent, protected annotated result tag, immutable published release, checksum-bound assets, and create/adopt receipts | `RELEASED` | documentation/social follow-up |
| `RESULT_MERGED` | `RELEASE_PLAN_INVALIDATED`: verified tree, bundle, security, provenance, or credential-exposure defect before or after release intent; if held or exposure is active, evidence binds the exact terminal consumer and successor clears the applicable roots | `RELEASE_BLOCKED` | start a correction lineage; do not tag/release |
| bare `RELEASE_BLOCKED` or `RELEASED` | `CORRECTION_INTENT_AUTHORIZED`: exact append-only intent, parent authority OID, plans, object names/roots, prior/new latest pointers, and idempotency keys; a held `RELEASED` parent is allowed only for exact nondismissible/exposure/invalidation/drift discriminator and evidence, and active exposure requires its terminal projection; the successor clears every consumed root | same campaign state | execute or recover exact correction publication effect |
| `RELEASE_BLOCKED` or `RELEASED` | `CORRECTION_PUBLICATION_RECORDED`, `CORRECTION_MERGE_RECORDED`, `CORRECTION_TAG_RECORDED`, or `CORRECTION_RELEASE_RECORDED`: exact next correction phase and adopted/created effect receipt | same campaign state | execute or recover exact next phase |
| `RELEASE_BLOCKED` or `RELEASED` with active correction `intent.json` or `publication-receipt.json` parent and no valid merge receipt | `CORRECTION_INVALIDATED(kind=correction_publication_invalidation, publication_outcome=unmerged_invalid|fenced_write_ambiguity)`: exact absent/closed PR and publication failure evidence; an active containment prefix requires the source-class-matching premerge finality, preserves its denylist and clears its root; active exposure additionally requires terminal consumption | same campaign state | correction lineage terminal; a new correction ID supersedes the failed prefix and any exposure root |
| `RELEASE_BLOCKED` or `RELEASED` with active correction `intent.json` or `publication-receipt.json` parent, observed merged PR, and no valid merge receipt | `CORRECTION_INVALIDATED(kind=correction_publication_invalidation, publication_outcome=merged_invalid)`: exact `PostMergeAdmissionFailureV1`, source-class-matching merge-won finality when containment is active, every contaminated merge/exposure, typed terminal consumption when active, and ordinary no-later-effects evidence | same campaign state | correction lineage terminal; a new correction ID explicitly supersedes the failed correction, every contaminated merge, and any exposure root |
| `RELEASE_BLOCKED` or `RELEASED` with active correction publication prefix whose required reconciliation exhausts | `CORRECTION_INVALIDATED(kind=correction_publication_invalidation, publication_outcome=reconciliation_unavailable)`: exact sealed unavailable disposition set/receipt, all request/dispatch pairs closed, zero live token and zero release authorization; exact PR terminal disposition is `no_pr|closed|already_merged`; an active prefix uses premerge finality for the first two outcomes and merge-won finality for the third, but no stable external-state/no-later claim is made | same campaign state | correction lineage terminal and release remains blocked; a new correction must supersede it and freshly reconcile before any success |
| `RELEASE_BLOCKED` or `RELEASED` with active correction valid `merge-receipt.json`, `tag-receipt.json`, or `release-receipt.json` parent | `CORRECTION_INVALIDATED(kind=correction_release_invalidation)`: exact release-phase failure and external-object evidence; active exposure additionally requires terminal consumption | same campaign state | correction lineage terminal; a new correction ID supersedes the failed prefix and any exposure root |
| `RELEASE_BLOCKED` | `CORRECTION_RESULT_RELEASED`: exact correction lineage and complete corrected publication/merge/release evidence | `RELEASED` | documentation/social follow-up from corrected latest pointer |
| `RELEASED` | `CORRECTION_RESULT_RELEASED`: exact append-only correction lineage and complete corrected publication/merge/release evidence | `RELEASED` | preserve prior terminal history; follow the new latest pointer |
| `PREFLIGHTED`, `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`, `AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED`, or `COMPLETE_PUBLICATION_PR_OPEN` | `PERMANENT_STOP`: exact parent-specific reason/evidence; nondismissible/credential/drift evidence binds any consumed hold root and successor clears it; credential exposure also consumes completed active progress root; an active initial complete prefix requires exact shared `no_pr` or `closed` disposition, while `already_merged` is excluded to the failed-admission row | `STOPPED_INVALID` | prefix/STOP finalizer only |
| any ready/resumable provider state | `BUDGET_EXHAUSTED`: next minimum batch cannot fit | `BUDGET_INCOMPLETE` | prefix/STOP finalizer only |
| `STOPPED_INVALID` or `BUDGET_INCOMPLETE` | `INVALID_PREFIX_SEALED`: exact completed prefix and missing suffix; unresolved hold and active pending incident are both null | `INVALID_FINALIZED` | publish registry/incident only |
| `INVALID_FINALIZED` | `INVALID_PUBLICATION_PLAN_INVALIDATED`: base/head moved, plan check failed, fenced write ambiguity, credential exposure, protocol drift, or an active invalid publication prefix exhausts exact reconciliation with the sealed unavailable receipt/set; prefix digest unchanged, PR disposition exact when ordinary, and an active containment prefix requires matching premerge finality and clears its root | `INVALID_FINALIZED` | direct form may replan normally; containment form may authorize only a new positive attempt that supersedes the terminal root and uses fresh branch/head/marker/trailer absent from every denylist selector |
| `INVALID_FINALIZED` | `PUBLICATION_INTENT_AUTHORIZED`: exact `bundle_kind=invalid_prefix`, deterministic branch/PR identities, effect roots, actors, and idempotency keys | `INVALID_FINALIZED` | create or adopt exact invalid-prefix branch/PR |
| `INVALID_FINALIZED` | `INVALID_PUBLICATION_PR_OPENED`: exact prior intent, `bundle_kind=invalid_prefix`, sealed prefix root, publication plan, and adopted/created branch/PR receipts | `INVALID_PUBLICATION_PR_OPEN` | review and required CI, no performance claim |
| `INVALID_FINALIZED` with active initial invalid intent/branch/PR prefix and observed merged PR | `INVALID_PREFIX_MERGE_INVALIDATED`: exact `PostMergeAdmissionFailureV1`, matching merge-won finality when containment is active, ordinary `PublicationPRTerminalDispositionV1(outcome=already_merged)` or null for write ambiguity, discovered/adopted prefix objects and every immutable merge; exposure additionally requires its class-bound terminal consumer | `INVALID_PREFIX_MERGED_INVALID` | terminal disclosed invalid-prefix merge; no release, correction, or promotion |
| `INVALID_PUBLICATION_PR_OPEN` | `INVALID_PREFIX_MERGED`: approved invalid-prefix PR, exact sealed-prefix lineage, merge receipt, and `PostMergeAdmissionEvidenceV1` | `INVALID_PREFIX_MERGED` | terminal registry/incident publication only |
| `INVALID_PUBLICATION_PR_OPEN` | `INVALID_PREFIX_MERGE_INVALIDATED`: intent-bound invalid-prefix PR is already merged but exact post-merge admission fails; an active containment prefix requires source-class-matching merge-won finality, merge-before-close binds the exact ordinary terminal disposition, and exposure binds its class-bound terminal consumer | `INVALID_PREFIX_MERGED_INVALID` | terminal disclosed invalid-prefix merge; no release, correction, or promotion |
| `INVALID_PUBLICATION_PR_OPEN` | `INVALID_PUBLICATION_PLAN_INVALIDATED`: exact invalid-prefix PR closed, fenced write ambiguity, or exact sealed reconciliation-unavailable failure with no success authority; sealed prefix root unchanged and an active containment prefix requires matching premerge finality and clears its root | `INVALID_FINALIZED` | authorize only a new positive attempt that supersedes any terminal root and uses fresh branch/head/marker/trailer absent from every denylist selector |
| `PREFLIGHTED`, `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`, `AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED` with no active initial-publication prefix, `RESULT_MERGED`, or bare `RELEASED`, with both roots null and no active correction prefix | `INVALID_EVENT_HELD`: exact broker-owned `InvalidEventHoldV1`, authenticated hold-worthy rejection, expected-OID CAS | same state | exact consumer only |
| the same phase-qualified hold-eligible states with one current hold and active pending null | `INVALID_EVENT_DISMISSED`: exact plan/evidence, expected-OID CAS | same state | clear exactly that hold and resume only unchanged-state authority |
| any exact exposure-eligible state with no active pending incident | `CREDENTIAL_EXPOSURE_PENDING`: exact pending record plus provisional denylist, expected-OID CAS | same state | containment only |
| any exact exposure-eligible state with matching active pending incident | `CREDENTIAL_EXPOSURE_EFFECT_RECORDED`: next inventoried effect receipt, expected-OID CAS | same state | next containment effect or final event only |
| `STOPPED_INVALID`, `BUDGET_INCOMPLETE`, `INVALID_FINALIZED`, `INVALID_PUBLICATION_PR_OPEN`, `INVALID_PREFIX_MERGED`, or `INVALID_PREFIX_MERGED_INVALID` with matching active exposure incident | `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`: terminal `CredentialExposureSupplementV1` after pending record and containment receipts; consumes active root and preserves state | same state | no live resume; only the pre-existing safe invalid-prefix continuation, when any, remains possible |

Within the generated `PERMANENT_STOP` transition, the `credential_exposure` reason has exactly
these allowed parents:
`GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`,
`JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`,
`AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED`, and
`COMPLETE_PUBLICATION_PR_OPEN`. The event must reproduce every current authority, state, ledger,
artifact-inventory, active-plan, and hold root from its parent. `PREFLIGHTED` is excluded because no
provider-bearing artifact has been uploaded; `RESULT_MERGED` uses `RELEASE_PLAN_INVALIDATED`, and
`RELEASED` uses correction lineage. The reason is also forbidden from `STOPPED_INVALID`,
`BUDGET_INCOMPLETE`, `INVALID_FINALIZED`, `INVALID_PUBLICATION_PR_OPEN`, `INVALID_PREFIX_MERGED`,
`INVALID_PREFIX_MERGED_INVALID`,
`RELEASE_BLOCKED`, correction states, and every terminal state. These restrictions apply to the
STOP reason, not to the separately enumerated pending/progress and terminal-consumer rows above.
Neither a generic incident event nor a reason alias can bypass this parent set. Noncredential
artifact corruption, traversal, inventory, or provenance defects remain under their existing
phase-specific reason discriminators and cannot be mislabeled `credential_exposure`.

An active job that exits at the soft deadline is resumable only through `VERIFIED_PARTIAL`. A lost
job without that event uses `NO_DISPATCH_PROVED` only when durable job and provider evidence proves
that the entire batch made zero dispatches and every released reservation is `never_started`;
otherwise ambiguity emits `PERMANENT_STOP`. Audit nonparticipation or an unrevealed commitment emits
a reason-specific `PERMANENT_STOP`; an explicitly signed unresolved adjudication is instead a valid
`AUDIT_SEALED` event whose affected model outcome is inconclusive. No dispatcher may jump from a
partial, STOP, budget, or release-blocked state into live execution or complete collection. An
unresolved `InvalidEventHoldV1` blocks every ordinary transition; only the exact consuming edges
enumerated above or the exposure emergency pending/progress/final flow are admitted.

`RESULT_MERGED` is accepted only from `COMPLETE_PUBLICATION_PR_OPEN`. Its event must reproduce
`bundle_kind=complete`, the exact `COMPLETE_BUNDLE_SEALED` root, `BUNDLE_COLLECTED` root,
`PublicationPlanV1` root, approved head, PR, merge commit, and resulting tree root as one matching
lineage. An invalid-prefix root, mixed root, absent discriminator, or
`INVALID_PUBLICATION_PR_OPEN` parent is an invalid event and creates a hold without mutation.
`INVALID_PREFIX_MERGED` and `INVALID_PREFIX_MERGED_INVALID` are terminal: neither accepts a
result-release, correction-release, documentation, website, release-note, or social-promotion
event. The former means that the safe registry/incident prefix was human-reviewed and validly
merged; the latter additionally discloses that exact merge failed admission and makes no claim that
its lineage was valid. Closing instead of merging either PR
kind requires its type-specific invalidation event; cross-kind close/merge events and generic
`PUBLICATION_PR_OPEN` are not schema values and are testable rejection cases. An
`INVALID_PUBLICATION_PLAN_INVALIDATED` close receipt is terminal for that exact invalid-prefix plan,
branch, and PR: a platform reopen cannot restore protocol authority and the failed required guard
prevents merge; none can be reused, no release/promotion is authorized, and
`INVALID_FINALIZED` permits only creation of a new plan with a new branch/PR identity over the same
unchanged sealed prefix root.

### 7.5 Correction side-effect protocol

Correction authority is stored only in the append-only tree of
`refs/heads/benchmark-authority/<campaign-id>`. Every correction ID is exactly the 37-byte ASCII
string matching `corr-[0-9a-f]{32}`, is single-use within its campaign, and byte-equals every path,
intent, receipt, event and idempotency-key projection; slash, dot, Unicode and normalization aliases
are unrepresentable. For correction ID `<correction-id>`, the only
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

If exposure is active at a bare `RELEASE_BLOCKED` or `RELEASED` parent, the intent additionally
binds the exact `TerminalCredentialExposureConsumptionV1`; its one CAS clears the active pair and
matching optional hold. The `RELEASED` exposure form also contains the withdrawal below, while the
`RELEASE_BLOCKED` form forbids withdrawal because no released latest pointer exists. Ordinary
correction intents forbid terminal exposure consumption and require the active pair null.
For protocol drift at a bare `RELEASE_BLOCKED` or `RELEASED` parent, the intent instead binds the
exact current-parent `ProtocolAuthorityDriftEvidenceV1`, requires both its terminal-disposition root
and the active exposure pair null, and grants no other defect class. A released drift intent appends
`latest_status=withdrawn_due_to_protocol_authority_drift`; the blocked form has no prior released
pointer to withdraw.

When a correction starts from `RELEASED` because of credential exposure, the same intent CAS also
appends `latest_status=withdrawn_due_to_credential_exposure`, incident root, and contaminated
tag/Release/history roots. This status invalidates consumption and promotion without deleting or
rewriting the historical latest-pointer event. Only successful `CORRECTION_RESULT_RELEASED` may
append the next active latest pointer.

The publisher may create or adopt only the intent-bound branch and PR, and immediately before PR
create it installs the same exact successful App-bound merge-eligibility check. The strict
correction `publication-receipt.json` carries the branch-create, eligibility-check, and PR-create
delivery-resolution roots, final marker-discovery root, eligibility receipt root, and exact
branch/PR identities. A
key-free state-writer step then persists it with `CORRECTION_PUBLICATION_RECORDED` by expected-OID CAS.
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
Correction draft discovery, serialized finalization, timeout/422/502 asset reconciliation, and
published-release verification use the same exact endpoint and `starter`-asset rules in section
7.6; a by-tag lookup is never treated as a draft lookup.

The two invalidation variants are one closed wire union. `CorrectionInvalidationV1` has exactly
`schema_version="CorrectionInvalidationV1"`, `campaign_id`, `campaign_registry_sha256`,
`correction_id`, `parent_state="RELEASE_BLOCKED"|"RELEASED"`, nullable
`source_authority_parent_oid`, `authority_parent_oid`,
`correction_intent_sha256`,
`invalidation_kind="correction_publication_invalidation"|"correction_release_invalidation"`,
nullable `publication_outcome="unmerged_invalid"|"merged_invalid"|
"fenced_write_ambiguity"|"reconciliation_unavailable"`,
`invalidation_cause="ordinary"|"credential_exposure"|
"protocol_authority_drift"|"publication_reconciliation_unavailable"|
"publication_write_ambiguity_fenced"|"release_reconciliation_unavailable"`, nullable nested exact
`terminal_containment_finality: PublicationTerminalContainmentFinalityV1`, nullable
`terminal_containment_finality_sha256`, nullable
`successor_merge_denylist_root_sha256`, nullable
`active_publication_terminal_containment_root_before`, nullable
`active_publication_terminal_containment_root_after`, nullable nested exact
`fenced_write_ambiguity: PublicationFencedWriteAmbiguityV1`, nullable
`fenced_write_ambiguity_sha256`, nullable nested exact
`publication_pr_terminal_disposition: PublicationPRTerminalDispositionV1`, nullable
`publication_no_later_effects_root_sha256`, nullable nested exact
`post_merge_admission_failure: PostMergeAdmissionFailureV1`, nullable
`post_merge_admission_failure_sha256`, nullable nested exact
`publisher_credential_disposition_set: PublisherCredentialDispositionSetV1`, nullable
`publisher_credential_disposition_set_sha256`, nullable nested exact
`reconciliation_unavailable_receipt: PublisherReconciliationUnavailableReceiptV1`, nullable
`reconciliation_unavailable_receipt_sha256`, nullable
`release_authorization_ledger_root_sha256`, nullable
`release_plan_invalidation_evidence_sha256`, nullable
`release_finalizer_operation_set: ReleaseFinalizerOperationSetV1`, nullable
`release_finalizer_operation_set_sha256`, nullable
`release_reconciliation_unavailable_receipt: ReleaseReconciliationUnavailableReceiptV1`, nullable
`release_reconciliation_unavailable_receipt_sha256`, nullable
`release_no_later_effects_root_sha256`, nullable
`protocol_authority_drift_evidence_sha256`, nullable
`terminal_exposure_consumption_sha256`, `prior_latest_pointer_root_sha256`,
`proposed_latest_pointer_root_sha256`, `terminal_event_type="CORRECTION_INVALIDATED"`,
`recorded_at`, and `correction_invalidation_sha256`. All nullable fields are present. Both pointer
roots equal the active intent and remain byte-identical across invalidation. The digest domain is
`laconian-correction-invalidation-v1\n`, omitting only its final digest.

The publication variant requires a nonnull outcome and null release evidence/roots. Its exact
outcome matrix is:

| Publication outcome | Required nonnull fields and exact nullability |
|---|---|
| `unmerged_invalid` | exact `no_pr|closed` disposition, publication no-later root, and ordinary-premerge containment finality; publisher-unavailable/fenced/post-merge fields null |
| `merged_invalid` | nested post-merge failure/digest; the direct normal-admission arm has null containment finality, disposition and no-later root, while an active-containment ordinary/ambiguity race has merge-won finality and respectively exact disposition/no-later or both null; publisher-unavailable/fenced-premerge fields null |
| `fenced_write_ambiguity` | cause `publication_write_ambiguity_fenced`, nested exact `PublicationFencedWriteAmbiguityV1(terminal_route=correction_premerge)` and write-ambiguity-premerge containment finality; ordinary disposition/no-later/post-merge/unavailable fields null |
| `reconciliation_unavailable` | nested sealed unavailable disposition set/receipt and exact empty release-ledger root; `no_pr|closed` uses ordinary-premerge finality and null post-merge failure, while `already_merged` requires the exact post-merge failure with merge-won finality; both no-later roots null |

The unavailable row requires `invalidation_cause=publication_reconciliation_unavailable`, the
receipt's `required_terminal_event_type=CORRECTION_INVALIDATED`, and `recorded_at` equal the
receipt/set/publisher-ledger/vault-log/release-ledger sealed time. It makes no stable external-state,
admission, merge-validity or release claim. Ordinary unmerged and containment-race merged outcomes
use the ordinary/exposure/drift/ambiguity cause fields below and set `recorded_at` to their selected
no-later closure time. Direct normal `merged_invalid` instead copies the nested
`PostMergeAdmissionFailureV1.recorded_at`. The release variant requires null publication outcome/disposition and
publisher-unavailable/post-merge fields plus a nonnull exact release-plan-invalidation root. Its
ordinary/exposure/drift form has a nonnull release no-later root, null release-unavailable objects
and its time equals release no-later close. Its `release_reconciliation_unavailable` form instead
nests the exact failure-only release operation set/receipt and duplicated digests from that
evidence, requires the release no-later root null, and records their common sealed time.
A cross-variant field, unavailable cause on a non-unavailable outcome, or free scalar root without
its required nested object is invalid.

Every containment-form publication outcome has a nonnull exact containment finality/digest,
successor denylist, source parent, immediate terminal parent, before root equal to the intent digest
and after root null. The finality terminal parent equals `authority_parent_oid`; its intent source
parent equals `source_authority_parent_oid`. The correction terminal CAS byte-preserves the denylist
and clears the active root. The release-invalidation variant has every containment/fence field null
and its source parent null. The direct normal `merged_invalid` arm likewise has every containment/
fence field null, has `source_authority_parent_oid=authority_parent_oid` as required by its nested
post-merge failure, and does not mutate the denylist. No nullable scalar root is
accepted without its nested exact object.

A `correction_publication_invalidation` is allowed only with `intent.json` or
`publication-receipt.json` as parent and before a valid merge receipt. Its `publication_outcome` is
exactly `unmerged_invalid`, `merged_invalid`, `fenced_write_ambiguity`, or
`reconciliation_unavailable`.
`unmerged_invalid` binds the reason, exact publisher
actor, shared `PublicationPRTerminalDispositionV1(outcome=no_pr|closed)`, every discovered
branch/PR object, and the unchanged proposed latest pointer. Each non-unavailable,
non-ambiguity invalidation has a closed
`cause=ordinary|credential_exposure|protocol_authority_drift`; fenced ambiguity has only
`publication_write_ambiguity_fenced`. The exposure form requires the exact
terminal consumption projection and clears the active pair. The drift form requires exact
current-parent `ProtocolAuthorityDriftEvidenceV1`, whose terminal-disposition root equals the
invalidation's record, and requires the active pair null. The ordinary form forbids both emergency
objects and also requires that pair null. A `closed` record accepts exactly its strict close-kind
branch; no-PR, publisher-closed, and observed-already-closed evidence cannot substitute.

`merged_invalid` is the terminal escape when the intent-bound correction PR is already merged but
`PostMergeAdmissionEvidenceV1` fails, so no valid `merge-receipt.json` can be written. It binds the
immutable PR/base/head, observed merge SHA and parents, merge/current-main trees, merge actor/method,
checks/approvals, current-main containment, all GitHub request receipts, and the exact
`PostMergeAdmissionFailureV1` root. It records the contaminated merge/exposure root and proves no correction
tag, Release, asset, latest-pointer event, documentation, or promotion was authorized. It never
pretends the merge was absent and never manufactures a merge receipt. A merge-before-close
exposure requires the race-form failure whose terminal projection byte-equals the invalidation's
projection.
Protocol-drift `merged_invalid` requires
`PostMergeAdmissionFailureV1(failure_kind=protocol_authority_drift_race)` whose nested drift
evidence and terminal disposition byte-equal the invalidation; its terminal exposure projection is
null. Ordinary merged invalidation uses `failure_kind=ordinary` and forbids both emergency objects.

A `correction_release_invalidation` is allowed only after a valid `merge-receipt.json`, with that
receipt or a later tag/release receipt as parent; it binds the merge/tree roots, every created or
adopted tag/release/asset object, failure and reconciliation receipts, and proof that prior immutable
objects and the latest pointer were not changed. It uses the same three-member closed cause rule:
exposure requires terminal consumption, drift requires exact current-parent drift evidence with a
null terminal disposition, and ordinary invalidation forbids both. Either invalidation kind is installed as
`invalidation.json` with `CORRECTION_INVALIDATED` by one expected-OID CAS, makes that correction
lineage terminal, and leaves the campaign in `RELEASE_BLOCKED` or `RELEASED` as it was. Cross-phase
use, both kinds, a generic alias, or invalidation after finalization is rejected. A new attempt
requires a new correction ID and new external names; after any exposure terminalization, its intent
must explicitly supersede the failed correction root and exposure root, and after `merged_invalid`
also the contaminated merge. The prior
latest pointer remains unchanged until a later correction fully finalizes.

Only after all five phase records verify may finalization run. `CorrectionFinalizationV1` has
exactly `schema_version="CorrectionFinalizationV1"`, `campaign_id`,
`campaign_registry_sha256`, `correction_id`, `parent_state="RELEASE_BLOCKED"|"RELEASED"`,
`authority_parent_oid`, `correction_intent_sha256`, `correction_lineage_root_sha256`,
`supersedes_event_sha256`, `superseded_terminal_root_sha256`,
`prior_latest_pointer_root_sha256`, `new_latest_pointer_root_sha256`,
`publication_receipt_sha256`, `publication_merge_receipt_sha256`, `tag_receipt_sha256`,
`release_receipt_sha256`, `corrected_result_tree_root_sha256`,
`annotated_tag_object_root_sha256`, `ordered_release_asset_root_sha256`, nested exact
`publication_success_finality: PublicationSuccessFinalityEvidenceV1`,
`publication_success_finality_root_sha256`, nested exact
`release_no_later_effects: ReleaseNoLaterEffectsEvidenceV1`,
`release_no_later_effects_root_sha256`, `publisher_broker_phase_ledger_root_sha256`,
`release_finalizer_broker_phase_ledger_root_sha256`, `publisher_live_token_count=0`,
`release_finalizer_live_token_count=0`, `terminal_event_type="CORRECTION_RESULT_RELEASED"`,
`recorded_at`, and `correction_finalization_sha256`. Every receipt is the accepted, immediately
preceding correction-lineage phase member; every duplicated identity, plan, merge, tree, tag,
release, asset, finality and ledger root byte-equals its nested source. The supersedes event/root
and prior pointer equal the intent; the new pointer is a distinct append-only successor whose bytes
name this correction and exact release. `recorded_at` equals the release no-later closure/event time
and is not before publication-success sealing. Its domain is
`laconian-correction-finalization-v1\n`, omitting only its final digest. Extra nullable phase fields,
a missing phase receipt, a scalar-only finality root, or a prior/new pointer rewrite is invalid.

`CORRECTION_RESULT_RELEASED` is the
sole escape from `RELEASE_BLOCKED`; it binds the correction-lineage root, exact predecessor and
`supersedes` event, prior/new latest pointers, publication/merge/tag/release receipts, corrected
result-tree root, annotated-tag object root, and complete ordered release-asset root. Its exact
`finalization.json` also nests the merge-bound `PublicationSuccessFinalityEvidenceV1` and the final
`ReleaseNoLaterEffectsEvidenceV1`, repeats both roots, and requires both broker ledgers sealed with
zero live tokens; the release proof includes the final immutable verification delivery resolution.
The finalization/event time equals the release no-later final closure time. The state
writer installs `finalization.json`, the new latest pointer, the terminal correction evidence root,
and the escape event in one ordered authority commit and publishes it with one expected-OID,
non-force, fast-forward CAS. A correction from already `RELEASED` appends the same evidence while
state remains `RELEASED`; it cannot rewrite prior state, history, pointer events, tags, or releases.

### 7.6 Initial publication and release side-effect protocol

Initial complete and invalid-prefix publication uses the same preauthorize/create-or-adopt/receipt
discipline as correction; “initial” does not mean best-effort. `publication_id` is campaign-stable,
is 1 through 64 ASCII bytes, and matches
`[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?`; `/`, `.`, `..`, controls, non-ASCII, and every Unicode
normalization alias are therefore unrepresentable. Every replan increments `publication_attempt`
in the closed range `1..99999999999999999999`, and its path form is the unique zero-padded
20-digit decimal encoding. Authority records live only under
`publication/initial/<publication-id>/attempts/<20-digit-publication-attempt>/` with exact ordered members `intent.json`,
`branch-receipt.json`, `pr-receipt.json`, `merge-receipt.json`, optional `release-intent.json`,
optional `tag-receipt.json`, optional `draft-release-receipt.json`, optional
`asset-receipts.json`, optional `publish-receipt.json`, and zero terminal members while the attempt
is active but exactly one append-only `finalization.json` or `invalidation.json` when it becomes
terminal. Invalid-prefix publication forbids every release member. Reconstruction derives phase
from the accepted members plus campaign state/event; an active prefix is never inferred from state
name alone.

Unless a record below states another literal explicitly, every named `*V1` wire record introduced
in sections 7.4 through 7.6 has `schema_version` exactly equal to its class name. This rule supplies
no omitted field and permits no generic or versionless alias.

Before a publisher effect, `PUBLICATION_INTENT_AUTHORIZED` installs `intent.json` by authority CAS
while state remains `BUNDLE_COLLECTED` or `INVALID_FINALIZED`. It binds bundle kind, sealed root,
publication ID and attempt, base/head/result tree, deterministic branch name, exact commit bytes/OID,
the required attempt/correction commit-message trailer, the ordered root of prior terminal head
OIDs, PR base/title/body and embedded plan marker, expected publisher actor,
`PublicationBranchRulesetPolicyV1`, checks/approval policy, merge expectations, and separate
domain-separated idempotency keys for branch creation and delivery resolution, eligibility-check
creation and delivery resolution, PR creation and delivery resolution, every receipt, marker
discovery, terminal-guard creation, PR close, merge observation, and invalidation. No branch, check,
PR close-delivery, terminal-reconciliation-read, or PR may exist before that intent is authoritative,
and its head OID must be absent from all prior
terminal publication lineages.

The fixed publisher queries the exact branch and PR marker before each effect. An absent branch is
created once at the intent-bound commit; an exact existing branch is adopted. An absent PR is
created once from that branch to the exact base only after the publisher App creates/adopts the
exact successful `PublicationMergeEligibilityReceiptV1` check on the head; an open or already merged PR is adopted only when
number, actor, base/head, title/body marker, sealed root, and plan all match. Branch and PR receipts
are persisted before `COMPLETE_PUBLICATION_PR_OPENED` or `INVALID_PUBLICATION_PR_OPENED` advances
state. If the human merge succeeds but the merge-event CAS or response is lost, recovery reconstructs
`PostMergeAdmissionEvidenceV1`, adopts that exact merge, persists `merge-receipt.json`, and emits
the same merge event; it never opens a replacement PR.

The shared `GitHubAppInstallationIdentityV1` wire object has exactly `schema_version`, `app_id`,
`installation_id`, `app_slug`, `bot_login`, `repository_id`, `role`,
`permissions_attestation_sha256`, and `identity_sha256`. Its schema literal is
`GitHubAppInstallationIdentityV1`; all three numeric IDs are positive canonical integers; `role` is
exactly `state_writer`, `publisher`, or `release_finalizer`; strings are bounded nonblank safe
metadata. Its digest domain is `laconian-github-app-installation-identity-v1\n` and omits only
`identity_sha256`. The role, IDs, slug/login, repository, and permissions must equal the sealed
registry projection; an ambient Actions/bot identity is not this type.

`BrokerTokenDeliveryIsolationPolicyV1` has exactly `schema_version`,
`api_origin="https://api.github.com"`, `api_version="2022-11-28"`,
`installation_token_endpoint="POST /app/installations/{installation_id}/access_tokens"`, ordered
`broker_roles=["publisher","release_finalizer","security_attestor"]`,
ordered exact `vault_implementation_measurements`,
`github_tls_terminates_inside_token_vault=true`,
`complete_response_validation_precedes_token_commit=true`,
`token_commit_precedes_executor_visibility=true`,
`failed_token_commit_zeroizes_response_bytes=true`,
`executor_accepts_only_committed_token_handles=true`,
`raw_token_bytes_leave_token_vault=false`, `raw_token_bytes_enter_actions=false`,
`unknown_delivery_allows_operation_dispatch=false`, and
`broker_token_delivery_isolation_policy_sha256`. The token vault treats receipt, validation and
durable encrypted commit of the complete GitHub response as one fail-closed transaction. A token
handle becomes usable only after that transaction commits a fingerprint, issued/expiry times and
the exact returned permissions; no partial or uncommitted response bytes are addressable by the
request executor. A crash or transport loss before commit therefore cannot create an accessible
bearer credential even if GitHub created one internally. Its domain is
`laconian-broker-token-delivery-isolation-policy-v1\n`, omitting only its final digest. The exact
policy is a C0 input-package member and security-review subject and is byte-copied into the campaign
registry. An implementation or measurement that cannot enforce every literal fails closed before
token mint; no assumed server-processing deadline, token-expiry estimate, installation suspension,
or later resumption is an admissible substitute.
`vault_implementation_measurements` contains exactly one
`{broker_role,vault_measurement_sha256}` member per ordered role and no duplicate measurement key;
each deployed vault must reproduce its role member before accepting a request.

`BrokerSigningKeyV1` has exactly `schema_version`, `broker_role="publisher"|
"release_finalizer"|"security_attestor"`, `key_id`, `algorithm="Ed25519"`,
`public_key_spki_der_base64url`, `not_before`, `not_after`, and `broker_signing_key_sha256`; it has no
campaign root. Its domain is `laconian-broker-signing-key-v1\n`, omitting only its final digest.
The registry's `broker_signing_keys_root_sha256` is the domain-separated ordered Merkle root of
exactly one key per role in that order, and decoded public SPKI bytes reproduce the key material.
`BrokerSigningIdentityV1` has exactly `schema_version`, `campaign_registry_sha256`, nested exact
`signing_key: BrokerSigningKeyV1`, `broker_signing_keys_root_sha256`, and
`broker_signing_identity_sha256`. Its domain is `laconian-broker-signing-identity-v1\n`, omitting
only its final digest; the key/root byte-equal the cycle-free registry payload. Every broker policy
nests that campaign-bound identity. A ledger signature is unpadded base64url Ed25519 over its exact
domain-separated canonical preimage and verifies under the nested SPKI bytes; an unknown key,
algorithm, validity window or registry root fails closed.

`BrokerCallerAuthorizationReceiptV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `repository_id`,
nested exact `scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`,
`broker_policy_sha256`, `authorized_policy_row_sha256`, `caller_workflow_ref`,
`caller_workflow_sha256`, `caller_job`, `job_workflow_ref`, `job_workflow_sha256`,
`required_ref_class`, `oidc_issuer="https://token.actions.githubusercontent.com"`, `oidc_audience`,
`oidc_subject`, `oidc_repository`, `oidc_ref`, `oidc_sha`, `oidc_environment`, positive
`run_id`, positive `run_attempt`, positive `check_run_id`, `actor`, `authenticated_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1`, `broker_signature_base64url`, and
`caller_authorization_receipt_sha256`. Repository, caller/callee workflow blobs, ref/SHA,
environment, run and check-run identity are freshly resolved through the GitHub OIDC JWKS and API
and byte-equal the one exact role policy row; a caller-supplied claim projection, mutable workflow
ref, union of rows, or stale authorization is invalid. `authorized_policy_row_sha256` is the
recomputed digest of that exact member and `broker_policy_sha256` is its enclosing policy digest.
The receipt contains neither the raw OIDC JWT nor an App JWT. Its signature preimage is
`UTF8("laconian-broker-caller-authorization-signature-v1\n") || CanonicalJSONV1(record without
exactly broker_signature_base64url and caller_authorization_receipt_sha256)` and its record domain
is `laconian-broker-caller-authorization-receipt-v1\n`, omitting only the final digest. The nested
key role equals `broker_role` and is valid at `authenticated_at`.

`BrokerTokenRequestDispatchReceiptV1` is the append-before-send mint record and has exactly
`schema_version`, `campaign_id`, `campaign_registry_sha256`, `repository_id`,
nested exact `scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`,
`app_identity: GitHubAppInstallationIdentityV1`, `broker_policy_sha256`,
`authorized_policy_row_sha256`, nested exact
`caller_authorization: BrokerCallerAuthorizationReceiptV1`,
`caller_authorization_receipt_sha256`, `broker_token_delivery_isolation_policy_sha256`,
`vault_measurement_sha256`, `operation_idempotency_key`, positive `credential_attempt_ordinal`,
`vault_transaction_id`, `request_id`, `request_dispatched_at`, `method="POST"`,
`endpoint_template="/app/installations/{installation_id}/access_tokens"`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="app_jwt"`, ordered `requested_permissions`, nested exact `request_body`,
`request_payload_sha256`, nested exact `broker_signing_identity: BrokerSigningIdentityV1`,
`broker_signature_base64url`, and `token_request_dispatch_receipt_sha256`. It is durably appended
and signed before the first request byte may cross the vault network boundary; its timestamp is the
actual dispatch boundary. Its duplicated identity, policy/row, caller authorization, transaction,
request, permissions and request-body fields byte-equal the terminal transport receipt. The request
body and payload rules are the same exact rules defined below. Its signature preimage uses
`laconian-broker-token-request-dispatch-signature-v1\n`; its record domain is
`laconian-broker-token-request-dispatch-receipt-v1\n`, omitting only its final digest. Neither a
terminal outcome nor any response-derived field occurs in this acyclic pre-dispatch record.

`BrokerTokenRedactedSuccessArchiveV1` has exactly `schema_version`,
`redacted_response_canonical_json_base64`, `token_replacement_fingerprint_sha256`,
`redacted_response_sha256`, and `redacted_success_archive_sha256`. Decoding the base64 yields the
RFC 8785 bytes of the complete parsed GitHub 201 body with exactly the `token` string replaced by
`token_replacement_fingerprint_sha256`; `expires_at`, the permissions object,
`repository_selection`, every full repository object and every other official response member are
otherwise preserved. Parsing and canonicalizing those decoded bytes is idempotent and reproduces
`redacted_response_sha256`; raw token bytes are absent. Its archive domain is
`laconian-broker-token-redacted-success-archive-v1\n`, omitting only the final archive digest.

`BrokerTokenSafeSuccessProjectionV1` is the compact authority projection and has exactly
`schema_version`, positive `installation_id`,
`repository_selection="selected"`, ordered positive `repository_ids`, ordered
`permissions`, `token_fingerprint_sha256`, `expires_at`, and
`safe_success_projection_sha256`. `installation_id` comes from the request path; every other field
is deterministically extracted from the nested redacted archive. Permissions are the complete unique
lexicographically ordered `resource:level` projection of the response `permissions` object and
repositories are the complete ascending ID projection of the response's full repository objects.
Unknown, duplicate or ill-typed response members fail parsing; no raw token bytes are
representable. Its domain is
`laconian-broker-token-safe-success-projection-v1\n`, omitting only its final digest. The canonical
projection is stored in the sealed broker evidence archive, so its digest, repository selection,
permissions and expiry are independently replayable offline.

`BrokerTokenRequestTransportReceiptV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `repository_id`,
nested exact `scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`,
`app_identity: GitHubAppInstallationIdentityV1`,
`broker_policy_sha256`, `authorized_policy_row_sha256`,
`caller_authorization_receipt_sha256`, nested exact
`caller_authorization: BrokerCallerAuthorizationReceiptV1`,
`broker_token_delivery_isolation_policy_sha256`, `vault_measurement_sha256`,
`operation_idempotency_key`, positive
`credential_attempt_ordinal`, `vault_transaction_id`, nested exact
`request_dispatch_receipt: BrokerTokenRequestDispatchReceiptV1`,
`token_request_dispatch_receipt_sha256`, `request_id`, `request_dispatched_at`, `transport_terminal_at`,
nullable `response_completed_at`, `dispatch_state="dispatched"`, `method="POST"`,
`endpoint_template="/app/installations/{installation_id}/access_tokens"`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="app_jwt"`, ordered `requested_permissions`, nested exact
`request_body`, `request_payload_sha256`,
`outcome="successful_201"|"definite_denial"|"delivery_unknown"`, nullable positive
`response_status`, ordered `returned_permissions`, ordered positive `returned_repository_ids`,
nullable `token_fingerprint_sha256`, nullable `token_expires_at`,
nullable `token_vault_committed_at`, `durable_token_commit_count=0|1`, nullable
`safe_response_projection_kind="redacted_success_json"|"response_body_commitment"`, nullable
`safe_response_projection_sha256`, nullable nested exact
`safe_success_archive: BrokerTokenRedactedSuccessArchiveV1`, nullable nested exact
`safe_success_projection: BrokerTokenSafeSuccessProjectionV1`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1`, `broker_signature_base64url`, and
`token_request_transport_receipt_sha256`. `request_body` has exactly
`repository_ids=[repository_id]` and `permissions`; the latter is the lexicographically keyed JSON
object obtained by splitting every unique requested `resource:level` at the colon and assigning
that exact `read|write` level. Its RFC 8785 bytes reproduce `request_payload_sha256`; omitting
`repository_ids`, adding another repository or permission, or using installation-wide defaults is
invalid.

The nested caller-authorization and dispatch receipts are byte-equal projections of the terminal
receipt and their duplicated digests recompute. Caller authentication completes no later than
request dispatch. The dispatch receipt is the unique append-only start record for this
campaign/role/operation/key/credential ordinal and vault transaction; the terminal receipt is its
unique completion. A request without that durable start record is forbidden, and a started request
blocks role phase advance or sealing until exactly one terminal receipt or class-bound
unrecoverability receipt has been appended.
Their nested scope identities and recomputed scope digests are identical and equal the enclosing
role-specific credential subject/disposition scope; operation keys are derived inside that scope
and cannot authorize cross-publication, cross-release or cross-attestation replay.

`request_dispatched_at <= transport_terminal_at`. Success requires status 201,
`request_dispatched_at <= response_completed_at <= token_vault_committed_at =
transport_terminal_at`, commit count one, exact returned
permissions, `returned_repository_ids=[repository_id]`, fingerprint, expiry and a safe projection
of the complete response with only the raw `token` value replaced by its fingerprint. It requires
a nonnull nested redacted archive and safe-success projection whose request installation and
extracted repository/permission/fingerprint/expiry fields byte-equal the receipt, and
`0 < token_expires_at - token_vault_committed_at <= maximum_token_ttl_seconds` from the exact role
policy. Definite
denial permits exactly 401, 403, 404 or 422, requires
`request_dispatched_at <= response_completed_at = transport_terminal_at`, a safe projection, commit
count zero, null vault-commit time, null success archive/projection and empty returned/token fields.
Delivery unknown covers
timeout/connection loss, response loss after possible server commit, malformed payload, every
HTTP status other than documented-denial 401/403/404/422 or a valid committed 201, plus a valid
parsed 201 whose durable vault commit fails; its status and safe
projection kind/hash and response completion are all null for response loss, with dispatch no later
than terminal. For any received unknown response they are all nonnull and
`request_dispatched_at <= response_completed_at <= transport_terminal_at`; commit count and all
returned/token/commit-time fields are zero/null and both success objects are null. The vault transaction
ID is unique across campaign/role and is the same ID used by any enclosing unrecoverability receipt.
The isolation-policy root and vault measurement byte-equal the campaign registry and the exact
`broker_role` measurement member; commit count one is invalid without that join.
Broker-policy/row digests equal the role-specific policy and exact operation/purpose row selected
by identity, phase, caller/ref, operation key, permissions and endpoints; cross-row unions or an
unlisted row digest are invalid.
For success, projection kind is `redacted_success_json` and its hash equals the nested archive's
recomputed `redacted_response_sha256`; the compact projection separately recomputes and is a total
extraction from those archived bytes. For every
received non-success or malformed response, kind is `response_body_commitment` and its hash is
`SHA256(UTF8("laconian-broker-token-response-body-commitment-v1\n") || exact response-body bytes)`;
the bytes themselves are never exported because an unexpected body may contain a bearer secret.
A valid parsed 201 followed by failed durable commit uses the response-body-commitment kind,
retains status 201, but has empty returned repositories/permissions and null fingerprint/expiry/
commit time because no usable token record exists.
The signature preimage is
`UTF8("laconian-broker-token-request-transport-signature-v1\n") || CanonicalJSONV1(record without
exactly broker_signature_base64url and token_request_transport_receipt_sha256)`; key role equals
`broker_role` and is valid at `transport_terminal_at`. The record domain is
`laconian-broker-token-request-transport-receipt-v1\n`, omitting only its final digest.

`BrokerResponseZeroizationReceiptV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `repository_id`,
nested exact `scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`, `vault_transaction_id`,
`token_request_transport_receipt_sha256`,
`zeroization_outcome="no_response_buffer_received"|"uncommitted_buffer_zeroized"`, nonnegative
`uncommitted_buffer_count`, `raw_token_export_count=0`, `executor_token_handle_issue_count=0`,
`vault_measurement_sha256`, `zeroized_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1`, `broker_signature_base64url`, and
`response_zeroization_receipt_sha256`. No-response requires count zero; buffer-zeroized requires a
positive count and complete destruction before executor visibility. It names only the already-
terminal delivery-unknown request and never a later unrecoverability receipt or audit root. Its
signature and record domains are respectively
`laconian-broker-response-zeroization-signature-v1\n` and
`laconian-broker-response-zeroization-receipt-v1\n`. The signature preimage omits exactly
`broker_signature_base64url` and `response_zeroization_receipt_sha256`; the record-digest preimage
omits exactly `response_zeroization_receipt_sha256` and includes the verified signature.

`BrokerTokenUnrecoverabilityReceiptV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `repository_id`,
nested exact `scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`,
`app_identity: GitHubAppInstallationIdentityV1`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, `broker_token_delivery_isolation_policy_sha256`,
`token_request_receipt_sha256`, nested exact
`token_request_transport_receipt: BrokerTokenRequestTransportReceiptV1(outcome="delivery_unknown")`,
`token_request_transport_outcome="delivery_unknown"`, nullable
`response_status`, `vault_transaction_id`,
`vault_transaction_outcome="no_complete_response_received"|"complete_response_validation_failed"|
"durable_token_commit_failed"`, `durable_token_commit_count=0`,
`executor_token_handle_issue_count=0`, `operation_dispatch_count=0`,
`raw_token_export_count=0`, `accessible_token_count=0`,
`uncommitted_response_bytes_zeroized=true`, `vault_measurement_sha256`, nested exact
`response_zeroization_receipt: BrokerResponseZeroizationReceiptV1`,
`response_zeroization_receipt_sha256`,
`vault_audit_predecessor_entry_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1`, `broker_signature_base64url`, `observed_at`, and
`token_unrecoverability_receipt_sha256`. The request receipt and nullable status use the same
class-bound delivery-unknown transport result as the enclosing broker disposition; the duplicated
request digest is the nested receipt's recomputed final digest. The unique vault
transaction is absent from every successful-token commit and handle-issuance ledger and is present
once in the append-only audit log with the selected outcome and zero counters. Validation failure
includes malformed or unexpected 2xx and never permits extracting a token field; commit failure is
recordable only because executor visibility follows durable commit. The measurement byte-equals the
C0-reviewed implementation measurement for the isolation policy. The signature preimage is
`UTF8("laconian-broker-token-unrecoverability-signature-v1\n") || CanonicalJSONV1(record without
exactly broker_signature_base64url and token_unrecoverability_receipt_sha256)` and verifies under
the nested signing key whose `signing_key.broker_role` equals the receipt `broker_role` and whose
validity window includes `observed_at`. The record digest uses
`laconian-broker-token-unrecoverability-receipt-v1\n`, omitting only its final digest. Raw or partial
token bytes are unrepresentable. A receipt proves only that this protocol has no accessible token
or dispatch from the ambiguous request; it does not claim that GitHub failed to create an internal,
cryptographically unreachable token.
Vault outcome mapping is total and exact: transport/response loss selects
`no_complete_response_received`; any complete invalid, malformed or unexpected response selects
`complete_response_validation_failed`; and only a valid parsed 201 followed by failed durable commit
selects `durable_token_commit_failed`. These map to the nested request receipt's delivery-unknown
status/body/transaction fields with no alternative classification.
The nested zeroization receipt has the same role/transaction/request/measurement, its digest
recomputes, and `zeroized_at <= observed_at`; response loss selects `no_response_buffer_received`,
whereas every received invalid response or failed commit selects `uncommitted_buffer_zeroized`.
Its exact audit entry is the predecessor named by the unrecoverability receipt; the next audit entry
names the completed unrecoverability receipt, so neither object hashes its own future log root.
All three nested scope identities and digests byte-equal.
The role mapping is closed: publisher uses the publisher App identity, release finalizer uses the
release-finalizer App identity, and security attestor also uses the release-finalizer App identity
but selects the distinct `security_attestor` vault measurement and broker signing key. The nested
signing key's role and the policy measurement member both equal `broker_role`; App role alone never
selects a key or measurement.

`BrokerVaultScopeIdentityV1` has exactly `schema_version`, `scope_kind="publication"|"release"|
"security_attestation"`, `campaign_id`, `campaign_registry_sha256`, `repository_id`, nullable
`publication_id`, nullable positive `publication_attempt`, nullable `correction_id`, nullable
`bundle_kind="complete"|"invalid_prefix"`, nullable `sealed_root_sha256`, nullable
`publication_plan_sha256`, nullable `authorizing_intent_sha256`, nullable
`release_phase="pre_intent"|"release_intent"|"tag_receipt"|"draft_release_receipt"|
"asset_receipts"|"publish_receipt"`, nullable `preauthorized_release_plan_sha256`, nullable
`release_intent_sha256`, nullable `security_attestation_purpose`, nullable
`security_attestation_subject_sha256`, and `scope_identity_sha256`. Publication scope requires the
full class-bound publication identity and null release/security fields, including null release
phase and preauthorized plan. Release scope requires that same publication identity, one exact
release phase and null security fields. At `pre_intent`, release intent is null and the preauthorized
plan is nullable only for the explicit no-plan preparation failure; at every later release phase
both preauthorized plan and accepted release intent are nonnull and byte-equal reconstructed
authority. Security scope requires one closed purpose and its exact cycle-free subject digest;
publication fields are present iff that purpose is publication-bound. Every security scope has a
null release intent. `release_preparation` alone has `release_phase=pre_intent` and a nonnull exact
preauthorized plan; the other security purposes have both release phase and preauthorized plan
null. Thus neither an attestor scope nor a pre-intent reconciliation hashes a future intent that
transitively contains its own evidence.
Every field byte-equals the enclosing disposition-set identity. Its domain is
`laconian-broker-vault-scope-identity-v1\n`, omitting only its final digest.

`BrokerVaultAuditEntryV1` has exactly `schema_version`, nested exact
`scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`,
`app_identity: GitHubAppInstallationIdentityV1`, positive gapless `entry_ordinal`, nullable
`predecessor_entry_sha256`, nullable `vault_transaction_id`, nullable
`operation_idempotency_key`, nullable positive `credential_attempt_ordinal`,
`event_kind="token_request_started"|"token_request_terminal"|"token_committed"|
"operation_dispatch_started"|"operation_dispatch_terminal"|"token_delete_started"|
"token_delete_terminal"|"denial_probe_started"|"denial_probe_terminal"|
"uncommitted_response_zeroized"|"token_unrecoverable"|"token_closed"`, nullable
`token_fingerprint_sha256`, `source_receipt_sha256`, nonnegative
`outstanding_token_request_count_after`, nonnegative `outstanding_operation_dispatch_count_after`,
nonnegative `live_token_count_after`, `occurred_at`, and `entry_sha256`. Its domain is
`laconian-broker-vault-audit-entry-v1\n`, omitting only its final digest. The first predecessor is
null and each later predecessor is the prior entry digest; times are nondecreasing. Each start
increments its named outstanding count, each unique same-request terminal decrements it, successful
token commit increments live count, and exact token closure decrements live count. All other events
leave those counters unchanged. Counts are recomputed from the prefix and may never be negative.
Every event names the exact corresponding signed request, dispatch, terminal, delete, probe,
unrecoverability or closure receipt; start events name only acyclic pre-dispatch receipts. Unknown
mint paths contain no token-committed event and contain exactly one zeroization then unrecoverability
event for their unique vault transaction. No transaction, request or terminal event may be omitted,
duplicated or reassigned to another scope.

`BrokerVaultAuditLogV1` has exactly `schema_version`, nested exact
`scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`, `broker_role`,
`app_identity`, ordered nested exact `entries`,
`outstanding_token_request_count=0`, `outstanding_operation_dispatch_count=0`,
`live_token_count=0`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1`, `broker_signature_base64url`, `sealed_at`, and
`vault_audit_log_root_sha256`. The final scalar counts equal the last entry's recomputed counts
(or zero for an allowed empty log). The log is a bijection with the same role's signed broker-ledger
request/operation/closure evidence and with every request/closure/unrecoverability receipt in its
enclosing disposition set; its ordering is identical at equal timestamps. The log cannot seal with
an unmatched start or live committed token. Its signature preimage uses
`laconian-broker-vault-audit-log-signature-v1\n`; its record domain is
`laconian-broker-vault-audit-log-v1\n`, omitting only the final root. A bare audit root is valid only
when the enclosing finality object nests this exact recomputable signed log.
The nested signing identity's campaign registry and key root byte-equal the scope registry and
role-policy key; `signing_key.broker_role=broker_role` and
`signing_key.not_before <= sealed_at <= signing_key.not_after`. The App/role mapping is the closed
mapping above. A cross-role, expired, unknown or policy-divergent key invalidates the log.

The event table is closed:

| Event kind | Exact `source_receipt_sha256` type | Exact `occurred_at` | Counter delta `(request,operation,live)` |
|---|---|---|---|
| `token_request_started` | `BrokerTokenRequestDispatchReceiptV1` | request dispatch | `(+1,0,0)` |
| `token_request_terminal` | `BrokerTokenRequestTransportReceiptV1` | transport terminal | `(-1,0,0)` |
| `token_committed` | successful `BrokerTokenRequestTransportReceiptV1` | vault commit | `(0,0,+1)` |
| `operation_dispatch_started` | role-specific acyclic operation dispatch receipt | operation dispatch | `(0,+1,0)` |
| `operation_dispatch_terminal` | role-specific terminal transport receipt | transport terminal | `(0,-1,0)` |
| `token_delete_started` | `BrokerTokenClosureDispatchReceiptV1(operation="delete")` | delete dispatch | `(0,+1,0)` |
| `token_delete_terminal` | `BrokerTokenDeleteAttemptV1` | delete transport terminal | `(0,-1,0)` |
| `denial_probe_started` | `BrokerTokenClosureDispatchReceiptV1(operation="denial_probe")` | probe dispatch | `(0,+1,0)` |
| `denial_probe_terminal` | `BrokerTokenDenialProbeV1` | probe transport terminal | `(0,-1,0)` |
| `uncommitted_response_zeroized` | `BrokerResponseZeroizationReceiptV1` | zeroization completion | `(0,0,0)` |
| `token_unrecoverable` | `BrokerTokenUnrecoverabilityReceiptV1` | `observed_at` | `(0,0,0)` |
| `token_closed` | role-specific exact closure projection | `closed_at` | `(0,0,-1)` |

All fields irrelevant to the selected event's exact source are null; vault transaction, operation
key/ordinal and fingerprint are nonnull exactly when present in that source and byte-equal it. The
predecessor of `token_unrecoverable` or `token_closed` equals the source receipt's
`vault_audit_predecessor_entry_sha256`, avoiding a receipt/log hash cycle.

Throughout this protocol, `live_token_count` and `live_installation_token_count` count complete
bearer-token bytes or committed token handles accessible to any protocol broker, executor, workflow
or other protocol actor. A GitHub-internal token whose bytes never committed in the isolated vault
is not live under this definition because no protocol actor can authenticate with it. Every
delivery-unknown request remains explicitly inventoried by its unrecoverability receipt rather than
being silently treated as a denied mint.
For every committed token, `token_fingerprint_sha256` is exactly
`SHA256(UTF8("laconian-installation-token-fingerprint-v1\n") || exact UTF-8 token bytes)`, computed
only inside the vault; every request, dispatch, closure, probe and broker-ledger join reproduces that
same digest. `token_vault_committed_at` is not a claimed GitHub server issuance time. It equals the
successful authenticated token-request transport receipt's same-named field, which exists only
after the complete 201 response has validated and its token transaction has durably committed;
denial and delivery-unknown receipts retain their ordinary HTTP `response_completed_at` when a
response exists but have null token-vault commit time. `token_expires_at` byte-equals the successful
response's safe projection, and vault commit must precede expiry. Raw token bytes remain
unrepresentable.

Publisher credentials have a closed broker lifecycle; a terminal check is not final while a
success-capable token remains live. `PublisherCredentialBrokerPolicyRowV1` has exactly
`schema_version`, `caller_workflow_ref`, `caller_workflow_sha256`, `caller_job`,
`job_workflow_ref`, `job_workflow_sha256`, `required_oidc_audience`,
`required_environment="benchmark-publish"`, `required_ref_class`, `protocol_phase`,
`credential_mode="installation_token"`, `operation_kind`, ordered `requested_permissions`, ordered
`endpoint_templates`, and `policy_row_sha256`. Its domain is
`laconian-publisher-credential-broker-policy-row-v1\n`, omitting only its final digest. There is
exactly one row per operation in the literal matrix below, in table order; each row's job, ref
class, phase, operation, permissions and endpoints are indivisible. The caller workflow ref/SHA
byte-equal the enclosing policy; the called-job workflow ref/SHA and OIDC audience byte-equal the
sealed registry and immutable reusable workflow blob. No digest of a caller-selected subset,
superset or union is valid.

`PublisherCredentialBrokerPolicyV1` has exactly
`schema_version`, `campaign_registry_sha256`, `repository_id`,
`publisher_app_identity: GitHubAppInstallationIdentityV1(role="publisher")`,
`broker_token_delivery_isolation_policy_sha256`, `caller_workflow_ref`,
`caller_workflow_sha256`, ordered nested exact
`allowed_rows: PublisherCredentialBrokerPolicyRowV1`, ordered
`monotonic_protocol_phases=["constructive","terminalizing","terminal_reconciling","sealed"]`,
`maximum_token_ttl_seconds=3600`, `maximum_reconciliation_attempts=3`,
`reconciliation_retry_schedule_seconds=[0,30,120]`, positive
`clock_and_transport_skew_margin_seconds`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`installation_token_enters_actions=false`, and
`publisher_credential_broker_policy_sha256`. The rows are closed to the frozen
`benchmark-publish.yml`: `publisher_effect` on exact plan-bound protected main may request
constructive `branch_create|merge_eligibility|pull_request_create`;
`publication_terminalizer` on protected current main may request terminalizing
`terminal_guard_discovery|terminal_guard|pull_request_close|terminal_merge_barrier_read|
terminal_merge_barrier_dequeue|terminal_merge_fence_rerun`; and that same fixed job may request
`terminal_reconciliation_read` only after every write-token disposition is closed. Constructive
permissions are the least-privilege applicable subset of `contents:write`, `checks:write`,
`pull_requests:write`, and `metadata:read`; terminalizing uses only `checks:write|
pull_requests:write|contents:read|pull_requests:read|merge_queues:read|merge_queues:write|
actions:read|actions:write|checks:read|metadata:read`; reconciliation uses only `contents:read|checks:read|
pull_requests:read|metadata:read`. A row cannot union permissions from another operation. Its
domain is `laconian-publisher-credential-broker-policy-v1\n`, omitting only its final digest.

The row arrays byte-equal this literal operation matrix; no caller-selected subset or endpoint is
valid. Token mint uses `POST /app/installations/{installation_id}/access_tokens`, closure uses
`DELETE /installation/token`, and the denial probe uses `GET /repos/{owner}/{repo}` in every minted
row in addition to the operation endpoints below.
| Operation | Phase | Exact requested permissions | Exact operation endpoints |
|---|---|---|---|
| `branch_create` | `constructive` | `contents:write`, `metadata:read` | `GET /repos/{owner}/{repo}/git/ref/heads/{branch_name}`; `POST /repos/{owner}/{repo}/git/refs` |
| `merge_eligibility` | `constructive` | `checks:write`, `metadata:read` | `GET /repos/{owner}/{repo}/commits/{head_oid}/check-suites`; `GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs`; `POST /repos/{owner}/{repo}/check-runs` |
| `pull_request_create` | `constructive` | `metadata:read`, `pull_requests:write` | `GET /repos/{owner}/{repo}/pulls`; `GET /repos/{owner}/{repo}/pulls/{pull_request_number}`; `POST /repos/{owner}/{repo}/pulls` |
| `terminal_guard_discovery` | `terminalizing` | `contents:read`, `metadata:read`, `pull_requests:read` | `GET /repos/{owner}/{repo}/git/ref/heads/{branch_name}`; `GET /repos/{owner}/{repo}/pulls` |
| `terminal_guard` | `terminalizing` | `checks:write`, `metadata:read` | `GET /repos/{owner}/{repo}/commits/{head_oid}/check-suites`; `GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs`; `PATCH /repos/{owner}/{repo}/check-runs/{check_run_id}`; `POST /repos/{owner}/{repo}/check-runs` |
| `pull_request_close` | `terminalizing` | `metadata:read`, `pull_requests:write` | `GET /repos/{owner}/{repo}/pulls`; `GET /repos/{owner}/{repo}/pulls/{pull_request_number}`; `PATCH /repos/{owner}/{repo}/pulls/{pull_request_number}` |
| `terminal_merge_barrier_read` | `terminalizing` | `actions:read`, `checks:read`, `contents:read`, `merge_queues:read`, `metadata:read`, `pull_requests:read` | `POST /graphql` restricted to the three C0-frozen queue/timeline documents; `GET /repos/{owner}/{repo}/git/ref/heads/main`; `GET /repos/{owner}/{repo}/pulls`; `GET /repos/{owner}/{repo}/compare/{from_oid}...{to_oid}`; `GET /repos/{owner}/{repo}/git/commits/{commit_oid}`; `GET /repos/{owner}/{repo}/git/commits/{head_oid}`; `GET /repos/{owner}/{repo}/commits/{commit_oid}/pulls`; `GET /repos/{owner}/{repo}/actions/runs/{workflow_run_id}`; `GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs`; `GET /repos/{owner}/{repo}/check-runs/{check_run_id}`; `GET /repos/{owner}/{repo}/actions/runs/{workflow_run_id}/artifacts`; authenticated `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip` only to receive the validated 302; one credential-free `GET` to that exact allowlisted Location with Authorization/cookies stripped |
| `terminal_merge_barrier_dequeue` | `terminalizing` | `merge_queues:write`, `metadata:read` | `POST /graphql` restricted to the C0-frozen dequeue mutation and broker-derived PR node/client-mutation ID |
| `terminal_merge_fence_rerun` | `terminalizing` | `actions:write`, `metadata:read` | `POST /repos/{owner}/{repo}/actions/runs/{workflow_run_id}/rerun`, with the broker-authenticated frozen workflow/event/group/App/context target proof |
| `terminal_reconciliation_read` | `terminal_reconciling` | `checks:read`, `contents:read`, `metadata:read`, `pull_requests:read` | `GET /repos/{owner}/{repo}/git/ref/heads/{branch_name}`; `GET /repos/{owner}/{repo}/pulls`; `GET /repos/{owner}/{repo}/commits/{head_oid}/check-suites`; `GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs`; `GET /repos/{owner}/{repo}/git/ref/tags/{tag_name}`; `GET /repos/{owner}/{repo}/git/tags/{tag_oid}`; `GET /repos/{owner}/{repo}/releases`; `GET /repos/{owner}/{repo}/releases/{release_id}`; `GET /repos/{owner}/{repo}/releases/{release_id}/assets`; `GET /repos/{owner}/{repo}/contents/{latest_pointer_path}` |

`PublisherCredentialSubjectV1` is the cycle-free post-mint/pre-operation authority object. It has
exactly `schema_version`, the full campaign/registry/publication/attempt/correction/bundle/plan/
intent identity, `repository_id`, `operation_kind`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, `publisher_credential_broker_policy_sha256`,
`authorized_policy_row_sha256`, `app_identity: GitHubAppInstallationIdentityV1(role="publisher")`,
`caller_authorization_receipt_sha256`, nested exact
`token_request_transport_receipt: BrokerTokenRequestTransportReceiptV1(outcome="successful_201")`,
`token_request_receipt_sha256`, ordered `requested_permissions`, ordered `returned_permissions`,
`token_fingerprint_sha256`, `token_vault_committed_at`, `token_expires_at`, and
`publisher_credential_subject_sha256`. The request digest recomputes; every identity, role/App,
policy/row, caller, operation/key/ordinal, permission and token field byte-equals the request and
the selected publisher policy row. Requested and returned permissions are equal. Its domain is
`laconian-publisher-credential-subject-v1\n`, omitting only its final digest. Because it contains no
operation attempt, closure, disposition or ledger root, it is constructible before the first
publisher API effect and may be safely named by dispatch/page receipts. A permission mismatch,
denial or unknown mint can never produce this subject.

`PublisherOperationRequestDispatchReceiptV1` is the append-before-send record for every publisher
write or operation-owned GET, including the validated credential-free artifact-object-store follow.
It has exactly `schema_version`, the full campaign/
registry/publication/attempt/correction/bundle/plan/intent identity, `repository_id`,
`operation_kind`, `operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`, nullable positive `source_attempt_ordinal`, `attempt_kind`, nullable
positive `operation_round_ordinal`, nullable `observation_stage="pre"|"post"|"final"|
"containment_preflight"|"containment_pre_action"|"containment_action"|
"containment_first"|"containment_second"|"containment_advance"`, nullable
`containment_snapshot_ordinal=0|1|2`, nullable
`observation_round=1|2`, nullable
`page_ordinal`, `publisher_credential_broker_policy_sha256`, `authorized_policy_row_sha256`,
`publisher_credential_subject_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`, nested exact
`caller_authorization: BrokerCallerAuthorizationReceiptV1(broker_role="publisher")`,
`caller_authorization_receipt_sha256`, `token_request_receipt_sha256`,
`token_fingerprint_sha256`, `token_vault_committed_at`, `token_expires_at`, `request_id`,
`request_dispatched_at`, `method`, `endpoint_template`, `request_payload_sha256`, nullable
`target_object_id`, nullable `target_authorization_proof_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `operation_request_dispatch_receipt_sha256`. It is durably
appended before the first request byte crosses the network boundary. The policy/row, App, caller,
operation/key/ordinal and token provenance byte-equal the exact same-operation
`PublisherCredentialSubjectV1`; method/endpoint/payload/target equal the literal operation matrix and authority-derived
request. `token_vault_committed_at <= request_dispatched_at < token_expires_at`; the caller
authorization precedes or equals dispatch and the signing key is valid then. Its signature and
record domains are respectively `laconian-publisher-operation-request-dispatch-signature-v1\n` and
`laconian-publisher-operation-request-dispatch-receipt-v1\n`. The signature preimage is
`UTF8("laconian-publisher-operation-request-dispatch-signature-v1\n") ||
CanonicalJSONV1(record without exactly broker_signature_base64url and
operation_request_dispatch_receipt_sha256)`; the record digest is SHA-256 of the record domain
followed by canonical JSON omitting exactly its final digest and including the verified signature.
It contains no outcome or
response-derived field.
For `attempt_kind=workflow_artifact_archive`, token/App fields are authorization provenance only:
the request URL is the exact prior redirect digest target and the wire request has neither
Authorization nor Cookie header as proved by `PublicationMergeFenceArtifactArchiveReceiptV1`.

`PublisherOperationTransportReceiptV1` is the unique terminal mate for a publisher operation
attempt and has exactly `schema_version`, the same full identity, `repository_id`, `operation_kind`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`, positive
`operation_request_ordinal`, nullable positive `source_attempt_ordinal`, `attempt_kind`, nullable
positive `operation_round_ordinal`, nullable `observation_stage="pre"|"post"|"final"|
"containment_preflight"|"containment_pre_action"|"containment_action"|
"containment_first"|"containment_second"|"containment_advance"`, nullable
`containment_snapshot_ordinal=0|1|2`, nullable
`observation_round=1|2`, nullable
`page_ordinal`, `publisher_credential_broker_policy_sha256`, `authorized_policy_row_sha256`,
nullable `publisher_credential_subject_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`, `request_id`,
`dispatch_state="not_dispatched"|"dispatched"`, nullable nested exact
`request_dispatch_receipt: PublisherOperationRequestDispatchReceiptV1`, nullable
`operation_request_dispatch_receipt_sha256`, `method`, `endpoint_template`,
`request_payload_sha256`, nullable `target_object_id`, nullable
`target_authorization_proof_sha256`, `outcome`, nullable positive
`response_status`, nullable `response_completed_at`, nullable `safe_response_sha256`, nullable
`resolved_object_id`, nullable `resolved_object_root_sha256`, nullable
`source_observation_sha256`, `attempt_terminal_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `operation_transport_receipt_sha256`. For `dispatched`, the
nested start receipt is nonnull, its digest recomputes, every duplicated field byte-equals, and
`request_dispatched_at <= response_completed_at <= attempt_terminal_at` for a
received response; response loss has null status/completion/safe hash and dispatch no later than
terminal. Token validity is checked at the nested dispatch boundary; a response or reconciliation
may terminate after expiry and remains inventoried rather than becoming an unmatched start. A
delivery later resolved by class-bound reads names their final observation root. For
`not_dispatched`, the credential-subject digest, both nullable start fields, all response fields and every resolved/source field
are null, outcome is exactly `not_dispatched`, and `attempt_terminal_at` is the durable
no-dispatch decision time. Outcome/status/result nullability otherwise equals the one closed source
attempt matrix for its operation and attempt kind; a generic receipt cannot widen that enum.
Every source attempt's `transport_receipt_sha256` is the recomputed digest of this exact same-ordinal
receipt nested in `PublisherOperationTransportProjectionV1`; every reconciliation page or other GET
request hash is likewise in bijection with one such receipt, with its page/observation digest in
`source_observation_sha256`. Its signature preimage uses
`laconian-publisher-operation-transport-signature-v1\n`; it omits exactly
`broker_signature_base64url` and `operation_transport_receipt_sha256`. Its record
digest uses `laconian-publisher-operation-transport-receipt-v1\n`, omits exactly its final
digest and includes the verified signature.

The broker advances a durable per-publication phase monotonically before minting. Entering
`terminalizing` irrevocably disables branch, eligibility-success, and PR-create token requests for
that attempt/head; `terminal_reconciling` disables every publisher write token; `sealed` denies all
requests. Workflow inputs cannot lower the phase. The external broker performs allowed calls and
returns only safe receipt hashes; no installation token or authorization header enters Actions.

`PublisherNoMintReceiptV1` has exactly `schema_version`, the same full publication identity,
`repository_id`, `operation_kind`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, `authorized_policy_row_sha256`,
`reason="phase_forbidden"|"operation_not_required"|"superseded_before_request"`,
`token_request_count=0`, `operation_dispatch_count=0`, `recorded_at`, and
`no_mint_receipt_sha256`. Reason must equal reconstructed authority/phase and cannot replace a
required operation. Its domain is `laconian-publisher-no-mint-receipt-v1\n`, omitting only its final
digest.

`BrokerTokenClosureDispatchReceiptV1` is the acyclic append-before-send record for token deletion
and denial probes. It has exactly `schema_version`, nested exact
`scope_identity: BrokerVaultScopeIdentityV1`, `scope_identity_sha256`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`,
`app_identity: GitHubAppInstallationIdentityV1`, `broker_policy_sha256`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`,
`token_request_receipt_sha256`, `token_fingerprint_sha256`, `token_vault_committed_at`,
`token_expires_at`, `operation="delete"|"denial_probe"`, positive `ordinal`, `request_id`,
`request_dispatched_at`, `method="DELETE"|"GET"`, `endpoint_template`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="isolated_installation_token_handle"`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1`, `broker_signature_base64url`, and
`token_closure_dispatch_receipt_sha256`. Delete maps only to `DELETE /installation/token`; probe
maps only to `GET /repos/{owner}/{repo}`. It is durably appended before the request crosses the
network boundary and contains no terminal outcome. Its full identity/policy/token fields byte-equal
the enclosing closure and disposition. Its signature and record domains are respectively
`laconian-broker-token-closure-dispatch-signature-v1\n` and
`laconian-broker-token-closure-dispatch-receipt-v1\n`. The signature preimage omits exactly
`broker_signature_base64url` and `token_closure_dispatch_receipt_sha256`; the record-digest preimage
omits exactly `token_closure_dispatch_receipt_sha256` and includes the verified signature.

`PublisherTokenClosureProjectionV1` has exactly `schema_version`, the same campaign/registry/
publication/attempt/correction/bundle/plan/intent identity, `repository_id`, `operation_kind`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`,
`publisher_credential_broker_policy_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`,
`token_request_receipt_sha256`, ordered `requested_permissions`, ordered
`returned_permissions`, `token_fingerprint_sha256`, `token_vault_committed_at`, `token_expires_at`,
`outcome="revoked_204"|"ambiguous_delivery_then_confirmed_unusable"|
"expired_then_confirmed_unusable"`, ordered nested exact
`delete_attempts: BrokerTokenDeleteAttemptV1`, `closure_boundary_at`, ordered nested exact
`denial_probe_attempts: BrokerTokenDenialProbeV1`,
`post_boundary_same_token_operation_dispatch_count=0`,
`vault_audit_predecessor_entry_sha256`, `closed_at`, and `token_closure_projection_sha256`.
`BrokerTokenDeleteAttemptV1` has exactly `schema_version`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`,
`app_identity: GitHubAppInstallationIdentityV1`, `broker_policy_sha256`, positive gapless
`ordinal`, `request_id`, nested exact
`dispatch_receipt: BrokerTokenClosureDispatchReceiptV1(operation="delete")`,
`token_closure_dispatch_receipt_sha256`,
`request_dispatched_at`, `transport_terminal_at`, nullable `response_completed_at`,
`dispatch_state="dispatched"`, `method="DELETE"`, `endpoint_template="/installation/token"`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="isolated_installation_token_handle"`, `token_fingerprint_sha256`,
`outcome="confirmed_204"|"response_lost"|"observed_non_204"`, nullable positive
`response_status`, nullable `safe_response_sha256`, and `transport_receipt_sha256`. Confirmed
requires status 204, response completion equal to transport terminal and the SHA-256 of empty
response bytes; response loss requires null status/response fields and dispatch no later than
transport terminal; observed non-204 permits every received positive HTTP status other than 204
and requires both response fields with
`request_dispatched_at <= response_completed_at <= transport_terminal_at`. Every attempt has
`token_vault_committed_at <= request_dispatched_at < token_expires_at`; no delete is dispatched at
or after expiry, including on the expiry-confirmation path. Delete attempts are serialized: each later dispatch is strictly after the prior
`transport_terminal_at`, so the highest ordinal is also temporally last.
Its domain is `laconian-broker-token-delete-attempt-v1\n`, omitting only
`transport_receipt_sha256`.
The nested dispatch digest recomputes and every role/scope/App/policy/operation/key/credential/token/
ordinal/request/method/endpoint/dispatch-time field byte-equals the terminal attempt and enclosing
closure. The audit start names that dispatch digest; its unique next same-request terminal names this
attempt digest.

`BrokerTokenDenialProbeV1` has exactly `schema_version`,
`broker_role="publisher"|"release_finalizer"|"security_attestor"`, the same repository/App/
`broker_policy_sha256` and token fingerprint, positive gapless `ordinal`, `request_id`, nested exact
`dispatch_receipt: BrokerTokenClosureDispatchReceiptV1(operation="denial_probe")`,
`token_closure_dispatch_receipt_sha256`, `request_dispatched_at`,
`transport_terminal_at`, nullable `response_completed_at`,
`method="GET"`, `endpoint_template="/repos/{owner}/{repo}"`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="isolated_installation_token_handle"`,
`outcome="denied_401"|"response_lost"|"observed_retryable"`, nullable positive
`response_status`, nullable `safe_response_sha256`, and
`denial_probe_sha256`. Denied requires status 401 and both response fields; response loss requires
null status/response fields; retryable permits every received positive HTTP status other than 401
and requires both response fields. Every received probe has
`request_dispatched_at <= response_completed_at <= transport_terminal_at`; a lost response has
dispatch no later than terminal. Its domain is
`laconian-broker-token-denial-probe-v1\n`, omitting only its final digest; the request executor
uses the committed handle and never exports token bytes. The enclosing probe array is empty exactly
for `revoked_204` and nonempty for the other two outcomes; when nonempty it is serialized;
the nested dispatch digest and all duplicated identity/token/request/time fields recompute exactly;
the audit start/terminal pair names the dispatch and probe digests respectively.
For both terminal attempt types, audit fields not duplicated directly—scope identity, operation key,
credential ordinal, token-request digest and vault commit/expiry—are extracted only through the
nested exact dispatch receipt and must equal the enclosing closure; the terminal attempt cannot
override them. The three closure outcomes are first-decisive and disjoint. `revoked_204` requires
exactly one first/only observed 204 in a nonempty delete sequence; any earlier members are only
response-lost or observed-non-204, the boundary is that 204 response completion, no later delete or
denial-probe dispatch exists, and `closed_at=closure_boundary_at <= token_expires_at`.
`ambiguous_delivery_then_confirmed_unusable` requires no observed 204 anywhere, at least one lost
delete, and sets the boundary to the final delete transport terminal before expiry. Its nonempty
probe sequence starts strictly after the boundary and before expiry; every earlier probe is
response-lost/retryable, the final is `denied_401`, and `closed_at` equals that final response.
`expired_then_confirmed_unusable` requires no observed 204 whose response completes at or before
expiry and no earlier decisive unusability, and sets the boundary exactly to signed expiry. It
permits only a serialized pre-expiry-dispatched delete prefix; because each later delete dispatch
must follow the prior terminal, that prefix contains at most one 204 whose response completes
strictly after expiry. Every probe dispatch is strictly after both the boundary and the last delete
terminal, its final probe is `denied_401`, and `closed_at` equals that final response. Thus a delete
legally dispatched before expiry but confirmed 204 only after expiry is classified by the expiry
branch and still requires post-expiry denial proof. No path can satisfy another path's predicate.

At the boundary the vault atomically marks this exact `(scope_identity,broker_role,
token_fingerprint_sha256)` handle non-dispatchable for every ordinary operation/effect. The
append-only vault log replays
`post_boundary_same_token_operation_dispatch_count=0` by counting every same-token
`operation_dispatch_started`/role-specific effect-dispatch-start after the boundary regardless of
its eventual success, error or response loss. Only closure delete and denial-probe starts are
excluded; a later fresh token fingerprint is a distinct lifecycle. The probe attempts themselves
are all bound by the closure digest. The closure's requested and returned arrays byte-equal the disposition; equality is
required only for `minted_then_closed`, while the permission-mismatch status requires inequality.
Every common delete/probe member's role, App, policy and fingerprint byte-equal its enclosing
closure. Role-to-App mapping is the same closed mapping as token request and unrecoverability
receipts. `broker_policy_sha256` equals `publisher_credential_broker_policy_sha256`,
`release_finalizer_broker_policy_sha256`, or `security_attestor_caller_policy_sha256` for the
corresponding broker role and no other mapping is valid. The closure's `token_request_receipt_sha256` equals the enclosing
disposition's nested request transport digest.
For every received delete/probe response, `safe_response_sha256` is SHA-256 of the exact response-
body bytes (the 204 body is empty); authorization/request headers and token bytes are never part of
that body or archive. Response loss has a null safe hash.
The closure projection domain is
`laconian-publisher-token-closure-projection-v1\n`, omitting only its final digest.

`PublisherReconciliationAttachmentReceiptV1` has exactly `schema_version`, the same full
publication identity, `repository_id`, `operation_kind`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, positive `source_credential_attempt_ordinal`,
`zero_effect_source_disposition_sha256`, `operation_final_observation_root_sha256`,
`terminal_reconciliation_observation_sha256`,
`reconciliation_read_credential_subject_sha256`, `attached_at`, and
`reconciliation_attachment_receipt_sha256`. The source ordinal is lower, has the same operation/key
and names exactly one earlier no-dispatch disposition. The two observation roots byte-equal the
synthetic disposition's final projection and the second stable terminal-reconciliation observation;
the credential-subject digest is the recomputed exact
`PublisherCredentialSubjectV1(operation_kind="terminal_reconciliation_read")` used by every
attached observation/page, and is independent of the synthetic write operation's key and ordinal.
`attached_at` equals that second observation's authenticated `observed_at`, the enclosing synthetic
disposition's `closed_or_not_minted_at`, and its `reconciliation_attached` ledger entry's
`occurred_at`. Its domain is
`laconian-publisher-reconciliation-attachment-receipt-v1\n`, omitting only its final digest.

Every operation has one class-bound `PublisherOperationCredentialDispositionV1` with exactly
`schema_version`, the same campaign/registry/publication/attempt/correction/bundle/plan/intent
identity, `repository_id`, `operation_kind`, `operation_idempotency_key`, `protocol_phase`, positive
`credential_attempt_ordinal`,
`publisher_credential_broker_policy_sha256`, `authorized_policy_row_sha256`,
`broker_phase_ledger_root_sha256`,
nested exact `operation_transport: PublisherOperationTransportProjectionV1`,
`operation_transport_root_sha256`, nested exact
`operation_final_observation: PublisherOperationFinalObservationProjectionV1`,
`operation_final_observation_root_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`,
`credential_status="not_minted"|"mint_denied_no_dispatch"|"minted_then_closed"|
"minted_permission_mismatch_then_closed_no_dispatch"|
"mint_delivery_unknown_unrecoverable_no_dispatch"|
"reconciliation_sourced_zero_effect"`, ordered
`requested_permissions`, ordered
`returned_permissions`, nullable `token_request_receipt_sha256`, nullable nested exact
`token_request_transport_receipt: BrokerTokenRequestTransportReceiptV1`, nullable
`publisher_credential_subject_sha256`, nullable nested exact
`publisher_credential_subject: PublisherCredentialSubjectV1`, nullable
`no_mint_receipt: PublisherNoMintReceiptV1`, nullable nested exact
`token_unrecoverability_receipt: BrokerTokenUnrecoverabilityReceiptV1`, nullable
`zero_effect_source_disposition_sha256`, nullable nested exact
`reconciliation_attachment_receipt: PublisherReconciliationAttachmentReceiptV1`, nullable
`token_fingerprint_sha256`, nullable `token_vault_committed_at`, nullable `token_expires_at`, nullable
nested exact `token_closure: PublisherTokenClosureProjectionV1`,
`closed_or_not_minted_at`, and
`credential_disposition_sha256`. `operation_kind` is exactly `branch_create`,
`merge_eligibility`, `pull_request_create`, `terminal_guard_discovery`, `terminal_guard`,
`pull_request_close`, `terminal_merge_barrier_read`,
`terminal_merge_barrier_dequeue`, `terminal_merge_fence_rerun`, or
`terminal_reconciliation_read`; phase, endpoint and caller equal the named policy row. Requested
permissions equal that row only when a token request occurred. No-request/synthetic dispositions
use empty arrays but retain the exact authorized row digest. Every nonnull credential subject has a
recomputed duplicated digest and byte-equal disposition identity, policy/row, App, request,
permission and token fields.
`not_minted` requires empty permission arrays, a nonnull exact no-mint receipt proving no token request and
no dispatch, and every request receipt/credential-subject/unrecoverability/source/attachment/token/closure field null.
`mint_denied_no_dispatch` requires a nonnull exact request transport with `definite_denial` and its
byte-equal duplicated digest, expected requested permissions, empty returned permissions, a null no-mint receipt, and null
credential-subject/unrecoverability/source/attachment/token/closure fields with zero dispatch.
`minted_then_closed` requires a nonnull exact `successful_201` request transport and digest, equal
requested and returned least-privilege arrays, a nonnull exact publisher credential subject, all
token/closure fields nonnull, authenticated token vault commit before expiry,
and the nested closure identity/permissions/token/times byte-equal the disposition.
`minted_permission_mismatch_then_closed_no_dispatch` requires the same successful request transport,
unequal returned permissions, a null credential subject, full token/closure fields and zero dispatch; it is terminally
inventoried but authorizes no API effect.
Both minted variants have null unrecoverability/source/attachment fields.
`mint_delivery_unknown_unrecoverable_no_dispatch`
requires a nested dispatched token-request transport with `delivery_unknown` whose outcome is not a class-bound definite denial
or valid captured token response—including timeout, connection loss, 202, 5xx, malformed or
unexpected 2xx, and response loss after possible server commit—exact requested and empty returned
permissions, a nonnull exact role-matching unrecoverability receipt, null no-mint/source/attachment/
credential-subject/token/response-time/closure fields, and zero operation dispatch. Its terminal time equals the receipt's
`observed_at`; a later independent mint is a new credential-attempt ordinal and cannot reuse this
request or transaction. In every request-bearing status, the duplicated request digest is the
nested transport receipt's recomputed digest; disposition, unrecoverability receipt and transport
receipt reproduce the same role/App, broker policy, authorized row, requested permissions,
operation key, ordinal and vault transaction where applicable. Denial, success and unknown
transports all nest the exact caller authorization and dispatch receipt selected by that same row.
`reconciliation_sourced_zero_effect` is the one resolution-selected
zero-effect member after an earlier same-operation no-dispatch disposition. It has empty permission
arrays, null request digest/transport/credential-subject/no-mint/unrecoverability/token fields, a nonnull
`zero_effect_source_disposition_sha256` naming that earlier `not_minted`, denied,
permission-mismatched-and-closed, or unrecoverable member, a byte-matching nonnull exact attachment
receipt, the complete same-ordinal source attempts all represented by strict
`PublisherOperationTransportReceiptV1(dispatch_state="not_dispatched",
publisher_credential_subject_sha256=null)` members, zero dispatched write attempts, and exact final
observations sourced from the separately closed terminal-reconciliation read. It closes at its
final observation time and allows no write. On `stable_read_sealed`, the final read uses a fresh
least-privilege token and closes normally; failed attempts retain new ordinals. A caller may stop
retrying only by selecting the signed `reconciliation_unavailable_sealed` branch, which grants no
stable-state or success authority.
Ambiguous revocation and expiry use the nested class-bound closure proof above. The nested
projections recompute their duplicated roots and bind the
exact enclosing delivery resolution without hashing that resolution's final digest, avoiding a cycle. Its domain is
`laconian-publisher-operation-credential-disposition-v1\n`, omitting only its final digest; raw
token bytes are unrepresentable.

The two disposition roots are exact acyclic projections. `PublisherOperationTransportProjectionV1`
has exactly `schema_version`, the same identity, `operation_kind`, `operation_idempotency_key`,
ordered `attempts`, `transport_terminal=true`, and `operation_transport_root_sha256`. Each strict
`PublisherOperationAttemptProjectionV1` has exactly positive `operation_request_ordinal`, nullable
positive `source_attempt_ordinal`, `attempt_kind`, nullable
positive `operation_round_ordinal`, nullable `observation_stage="pre"|"post"|"final"|
"containment_preflight"|"containment_pre_action"|"containment_action"|
"containment_first"|"containment_second"|"containment_advance"`, nullable
`containment_snapshot_ordinal=0|1|2`, nullable
`observation_round=1|2`, nullable `page_ordinal`, `request_id`,
`dispatch_state="not_dispatched"|"dispatched"`, `method`, `endpoint_template`,
`request_payload_sha256`, nullable `target_object_id`, nullable
`target_authorization_proof_sha256`, `outcome`, nullable `response_status`,
nullable `safe_response_sha256`, nullable `resolved_object_id`, nullable
`resolved_object_root_sha256`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`, and
`transport_receipt_sha256`. Operation-request ordinals are gapless in actual dispatch/decision
order. Source-attempt ordinal is nonnull and gapless only within a source write-attempt array; it is
null for GET/page observations, whose round/stage/page coordinates are independently bound. The nested
terminal receipt's recomputed digest, global/source ordinals, source identity and every duplicated
field byte-equal the projection.
For a dispatched member its nested pre-dispatch receipt is the unique ledger start evidence; for a
non-dispatched member both nested start fields are null. The closed
operation matrix is:

| Operation | Attempt kind and round/page | Literal method/endpoint | Allowed outcome set |
|---|---|---|---|
| `branch_create` | `branch_create`; source ordinal nonnull; all observation coordinates null | `POST /repos/{owner}/{repo}/git/refs` | the exact `PublicationBranchCreateDeliveryResolutionV1` write-attempt enum |
| `branch_create` | `branch_ref`; source/op-round null; stage `final`; observation round `1|2`; page null | `GET /repos/{owner}/{repo}/git/ref/heads/{branch_name}` | publisher read outcome enum |
| `merge_eligibility` | `check_create`; source ordinal nonnull; all observation coordinates null | `POST /repos/{owner}/{repo}/check-runs` | exact eligibility write-attempt enum |
| `merge_eligibility` | `check_suite_page|check_run_page`; source/op-round null; stage `final`; observation round `1|2`; positive page | the matching check suite/run GET endpoint | publisher read outcome enum |
| `pull_request_create` | `pr_create`; source ordinal nonnull; all observation coordinates null | `POST /repos/{owner}/{repo}/pulls` | exact PR-create write-attempt enum |
| `pull_request_create` | `pr_marker_page`; source/op-round null; stage `final`; observation round `1|2`; positive page | `GET /repos/{owner}/{repo}/pulls` | publisher read outcome enum |
| `terminal_guard_discovery` | `branch_ref`; source null; positive operation round; stage `pre|post`; observation round/page null | `GET /repos/{owner}/{repo}/git/ref/heads/{branch_name}` | publisher read outcome enum |
| `terminal_guard_discovery` | `pr_marker_page`; source null; positive operation round; stage `pre|post`; observation round `1|2`; positive page | `GET /repos/{owner}/{repo}/pulls` | publisher read outcome enum |
| `terminal_guard` | `guard_update|guard_create`; source and operation-round ordinals nonnull; observation coordinates null | respectively `PATCH /repos/{owner}/{repo}/check-runs/{check_run_id}` or `POST /repos/{owner}/{repo}/check-runs` | exact guard write-attempt enum |
| `terminal_guard` | `check_suite_page|check_run_page`; source null; positive operation round; stage `post`; observation round `1|2`; positive page | matching check suite/run GET endpoint | publisher read outcome enum |
| `pull_request_close` | `pr_close`; source ordinal nonnull; all observation coordinates null | `PATCH /repos/{owner}/{repo}/pulls/{pull_request_number}` | exact close write-attempt enum |
| `pull_request_close` | `pr_state`; source/op-round null; stage `pre`; observation round/page null, or stage `final`; observation round `1|2`; page null | `GET /repos/{owner}/{repo}/pulls/{pull_request_number}` | publisher read outcome enum |
| `pull_request_close` | `pr_marker_page`; source/op-round null; stage `final`; observation round `1|2`; positive page | `GET /repos/{owner}/{repo}/pulls` | publisher read outcome enum |
| `terminal_merge_barrier_read` | `protected_main_ref`; source/op-round/page/observation-round null; stage/snapshot exactly `containment_preflight/0|containment_first/1|containment_second/2` | `GET /repos/{owner}/{repo}/git/ref/heads/main` | publisher read outcome enum |
| `terminal_merge_barrier_read` | `pr_marker_page`; source/op-round null; stage/snapshot exactly preflight/0, first/1 or second/2; observation round `1|2`; positive page | `GET /repos/{owner}/{repo}/pulls` | publisher read outcome enum |
| `terminal_merge_barrier_read` | `merge_queue_pr_query`; source/op-round/page/observation-round null; stage/snapshot exactly preflight/0, pre-action/0, first/1 or second/2 | `POST /graphql` with the fixed queue-state document | publisher read outcome enum |
| `terminal_merge_barrier_read` | `merge_queue_inventory_page`; source/op-round/observation-round null; the same four stage/snapshot pairs; positive page | `POST /graphql` with the fixed inventory document | publisher read outcome enum |
| `terminal_merge_barrier_read` | `merge_queue_timeline_page`; source/op-round/round/snapshot null; stage `containment_action`; positive page | `POST /graphql` with the fixed timeline document | publisher read outcome enum |
| `terminal_merge_barrier_read` | `workflow_run|check_run|workflow_artifacts_page`; source/op-round/round/snapshot null; stage `containment_action`; page positive only for artifacts page | the exact Actions/direct-check/artifact-list GET endpoint in the policy row | publisher read outcome enum |
| `terminal_merge_barrier_read` | `fence_check_run_page`; source/op-round/round/snapshot null; stage `containment_action`; positive page | `GET /repos/{owner}/{repo}/check-suites/{check_suite_id}/check-runs` | publisher read outcome enum |
| `terminal_merge_barrier_read` | `workflow_artifact_redirect`; source/op-round/round/snapshot/page null; stage `containment_action` | authenticated `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip` | exactly `read_redirect_302` on a validated Location; every other terminal result uses the ordinary failure outcomes |
| `terminal_merge_barrier_read` | `workflow_artifact_archive`; source/op-round/round/snapshot/page null; stage `containment_action` | credential-free GET of the exact validated allowlisted Location | `read_200` only with Authorization/cookies absent and the bounded ZIP receipt; otherwise ordinary failure outcomes |
| `terminal_merge_barrier_read` | `main_compare_page|commit_pull_requests_page`; source/op-round/round/snapshot null; stage `containment_advance`; positive page | exact compare or commit-pulls GET endpoint | publisher read outcome enum |
| `terminal_merge_barrier_read` | `main_commit|head_commit`; source/op-round/round/snapshot/page null; stage `containment_advance` | respectively `GET /repos/{owner}/{repo}/git/commits/{commit_oid}` or `GET /repos/{owner}/{repo}/git/commits/{head_oid}` | publisher read outcome enum |
| `terminal_merge_barrier_dequeue` | `merge_queue_dequeue`; positive source ordinal equals dequeue `ordinal`; stage `containment_action`; all round/snapshot/page coordinates null | `POST /graphql` with the fixed dequeue document | exact dequeue enum |
| `terminal_merge_fence_rerun` | `workflow_rerun`; source/op-round/round/snapshot/page null; stage `containment_action` | `POST /repos/{owner}/{repo}/actions/runs/{workflow_run_id}/rerun` | `not_dispatched|rerun_accepted_201|delivery_ambiguous|definite_rejection` |
| `terminal_reconciliation_read` | `branch_ref|pr_marker_page|check_suite_page|check_run_page|release_inventory_page|latest_pointer`; source/op-round null; stage `final`; observation round `1|2`; page positive only for a page kind | the matching GET endpoint from the broker policy | publisher read outcome enum |

Every ordinary row requires a null containment snapshot and target-authorization proof. Containment
read rows derive a nonnull proof only when selecting a protected target; dequeue requires the exact
pre-action queue-observation proof and rerun the exact target proof below. The publisher read
outcome enum is exactly `read_200|read_404|read_redirect_302|read_definite_denial|
read_response_lost|read_unexpected_status|read_malformed_response`. For every write row,
source-attempt ordinal and fields byte-equal the named write-attempt array while the global request
ordinal records interleaved GET/write protocol order; `attempt_kind` is the table literal, not an
absent source field. Write response/safe/result nullability is exactly the source matrix. Every GET
uses the lowercase SHA-256 of zero bytes as payload. Successful
`read_200|read_404` has that exact status, null safe-response field, and result/root nullability equal
to the class-bound observation. `read_redirect_302` is legal only for
`workflow_artifact_redirect`, requires exact status 302 and the signed validated-Location receipt,
and never forwards credentials to the follow-up. Definite denial permits only 401/403 plus the exact response-body
hash; response loss has null status/completion/body; unexpected status covers every other received
status and hashes its body; malformed response is a received nominally successful status whose
archived bytes fail the exact parser. Each request failure terminally closes its pre-dispatch
start and aborts only that reconciliation attempt—no unmatched request remains.
For GraphQL, status 200 plus nonempty `errors`, null/partial data, missing required nodes or
malformed bytes is `read_malformed_response` with the complete raw body archived; it is
never `read_200`. Dequeue outcomes are exactly
`not_dispatched|dequeued_exact|delivery_ambiguous|definite_rejection` as defined by its
attempt schema. Rerun exact success is only authenticated 201; response loss or any received result
that is neither 201 nor a proven pre-dispatch 401/403/404 is `delivery_ambiguous`.

Pagination failure is an aggregate, never a per-request transport outcome.
`PublisherPaginationFailureReceiptV1` has exactly `schema_version`, the same full publication and
operation identity, `operation_idempotency_key`, positive `credential_attempt_ordinal`,
`publisher_credential_subject_sha256`, `reconciliation_round=1|2`,
`collection_kind="pr_marker"|"check_suite"|"check_run"|"release"|"asset"`,
`collection_key`,
`valid_page_receipt_sha256s`, nullable positive `last_valid_page_ordinal`, nullable
`expected_next_request_url`,
`failure_kind="terminal_request_failure"|"missing_required_next_link"|"invalid_link_chain"|
"cardinality_inconsistent"`, nullable `source_terminal_transport_receipt_sha256`, nullable
`source_terminal_outcome="read_definite_denial"|"read_response_lost"|
"read_unexpected_status"|"read_malformed_response"`, nullable `source_request_id`, nullable
`source_raw_response_sha256`, nullable nested exact `failed_response_blob`, nested exact
`archive_prefix: PublisherPaginationArchivePrefixV1`, `archive_prefix_root_sha256`,
`observed_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `pagination_failure_receipt_sha256`. Valid page roots are a
gapless page-one prefix in request order and are in bijection with the archive prefix; empty prefix
requires null last ordinal and nonempty prefix requires the last ordinal equal its length.
`collection_key` is exactly the publication marker digest for PR-marker pages, lowercase head OID
for check-suite pages, decimal check-suite ID for check-run pages, literal `repository` for the
release list, or decimal release ID for an asset list.
`PublisherPaginationArchivePrefixV1` has exactly `schema_version`, the same publication/operation/
credential identity, `reconciliation_round`, `collection_kind`, `collection_key`, ordered
`entries`, and `archive_prefix_root_sha256`. Each entry has exactly positive gapless
`page_ordinal`, `page_kind="pr_marker"|"check_suite"|"check_run"|"release_inventory"`, nested
exact `page_receipt` as the matching class-bound signed page type, `page_receipt_sha256`, `path`,
`raw_response_sha256`, and `raw_bytes_base64`; path is
`publication-pagination/<collection-kind>/<collection-key>/<two-digit-round>/<page-ordinal>-<page-receipt-sha256>.response`,
decoded bytes reproduce the raw hash, and entry order is ascending page ordinal. The entry array is
a bijection with the failure receipt's valid page roots and the existing class-bound page receipts;
identity, page ordinal and raw hash byte-equal those receipts. Its domain is
`laconian-publisher-pagination-archive-prefix-v1\n`, omitting only its final digest, and the failure
receipt's duplicated root must recompute from this nested object.
`failed_response_blob` has exactly `path`, `sha256`, and `raw_bytes_base64`; decoded bytes reproduce
the source raw hash and path is exactly
`publication-pagination-failures/<SHA256(UTF8(request_id))>.response` using lowercase hex.
`terminal_request_failure` requires the unique
failed generic wrapper digest, its exact terminal outcome and request ID, and `observed_at` equal
that wrapper's `attempt_terminal_at`. Only `read_response_lost` requires the blob and raw-response
digest null; denial, unexpected-status and malformed-response require both nonnull and replayable.
For every received failure, blob `sha256`, `source_raw_response_sha256` and wrapper
`safe_response_sha256` are byte-equal, and source/wrapper request ID, outcome and status are exact.
The other three kinds require null source-terminal wrapper/outcome, the exact last nominally
successful wrapper request ID and raw-response digest plus a nonnull replayable blob,
forbid a terminal-failure wrapper digest, and set `observed_at` to its response completion time;
their expected-next URL and Link/cardinality predicates are recomputed from the archived bytes and
the preceding valid page. The receipt identity, subject and collection equal the enclosing read
disposition, and its `reconciliation_round` equals every source wrapper `observation_round` and
class-bound page round in that failed collection; its signature and record domains are
`laconian-publisher-pagination-failure-receipt-signature-v1\n` and
`laconian-publisher-pagination-failure-receipt-v1\n`. Its signature preimage is
`UTF8(signature domain) || CanonicalJSONV1(record without exactly broker_signature_base64url and
pagination_failure_receipt_sha256)`; its record digest is `SHA256(UTF8(record domain) ||
CanonicalJSONV1(record without exactly pagination_failure_receipt_sha256))`, including the verified
signature. A missing, invalid, repeated or cross-origin
Link therefore closes the aggregate read without inventing an additional request or a valid page.
For `stable_double_read`, the two rounds contain every exact branch, PR, complete check-suite/run,
release-ledger and pointer request receipt from the corresponding nested reconciliation observation
in protocol/page order, with no extra or omitted GET. For incomplete/unstable failure finality, the
projection instead contains the complete attempted prefix for zero to two rounds, with no fabricated
unrequested suffix. Its domain is
`laconian-publisher-operation-transport-projection-v1\n`, omitting only its final digest.

`PublisherPartialContainmentReadV1` is the typed maximal prefix for an aborted barrier
read. It has exactly `schema_version="PublisherPartialContainmentReadV1"`, the same full
publication identity,
`operation_kind="terminal_merge_barrier_read"`, `operation_idempotency_key`,
positive `credential_attempt_ordinal`, `observation_stage`, nullable
`containment_snapshot_ordinal=0|1|2`, `logical_aggregate_class`,
`canonical_target`, positive `next_operation_request_ordinal`, ordered nested exact
`members`, `raw_archive_root_sha256`, `observed_at`, and
`partial_containment_read_sha256`. Each member has exactly
`member_kind="atomic_read"|"page_read"`, positive gapless
`operation_request_ordinal`, `attempt_kind`, nullable `observation_round=1|2`,
nullable positive `page_ordinal`, nested exact
`transport_receipt: PublisherOperationTransportReceiptV1`,
`transport_receipt_sha256`, nullable nested exact class-bound
`source_receipt_or_observation`, nullable `source_receipt_or_observation_sha256`,
and nullable nested exact `raw_response_blob`. Members are exactly ordinals
`1..next-1` in dispatch order; every wrapper is terminal. A decoded success has one exact
class-bound observation/page and received raw bytes; a failed terminal wrapper retains its raw body
when received and has no successful source object. No requested prefix member is omitted or added,
and no unrequested suffix is invented. The raw archive root is the domain-separated length-prefixed
concatenation of all received bodies in member order. Its domain is
`laconian-publisher-partial-containment-read-v1\n`, omitting only its digest.

`PublisherReadAbortReceiptV1` is the signed record for a minted read credential whose
executor stops before the next request without fabricating that request. It has exactly
`schema_version="PublisherReadAbortReceiptV1"`, the same full publisher publication identity,
`operation_kind="terminal_merge_barrier_read"|"terminal_reconciliation_read"`,
`operation_idempotency_key`, `protocol_phase="terminalizing"|"terminal_reconciling"`,
positive `credential_attempt_ordinal`,
`publisher_credential_broker_policy_sha256`, `authorized_policy_row_sha256`,
`publisher_credential_subject_sha256`, `token_fingerprint_sha256`,
`abort_position="before_first_request"|"before_next_request"`, positive
`next_operation_request_ordinal`, ordered positive
`completed_operation_request_ordinals`, ordered
`terminal_transport_receipt_sha256s`, ordered
`completed_source_observation_sha256s`,
nullable nested exact `partial_containment_read: PublisherPartialContainmentReadV1`, nullable
`partial_containment_read_sha256`,
`pre_abort_broker_phase_ledger_root_sha256`,
`outstanding_operation_dispatch_count=0`, `aborted_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `publisher_read_abort_receipt_sha256`. Completed
ordinals are exactly `1..next-1`; terminal receipts are a bijection with them and all are
closed, while observation digests are exactly the successfully decoded subset. Before-first is
equivalent to next=1 and all three arrays empty. The broker durably appends the receipt after the
last terminal request, or after token issue for before-first, and atomically disables every later
dispatch for that credential attempt. It claims no missing observation. For barrier-read abort both
partial-prefix fields are nonnull and recompute; for
reconciliation-read abort both are null and its actual prefix is carried by the typed complete-
source/partial-source round grammar below. `aborted_at` is the receipt/final-projection observation time and is not
before every prefix terminal time. Its signature/record
domains are `laconian-publisher-read-abort-signature-v1\n` and
`laconian-publisher-read-abort-receipt-v1\n` with the exact signed-record omission rules:
the signature omits exactly signature+final digest and the record digest omits exactly its final
digest while including the verified signature.

`PublisherPartialReconciliationSourceV1` is the typed maximal prefix inside the currently
unfinished reconciliation source. It has exactly `schema_version`, the same publication/
operation/credential identity, `reconciliation_round=1|2`,
`source_kind="branch_ref"|"pr_marker"|"check_runs"|
"release_authorization_inventory"|"latest_pointer"`, positive
`first_operation_request_ordinal`, positive `next_operation_request_ordinal`, ordered nested exact
`members`, `raw_archive_root_sha256`, nullable `last_member_terminal_at`, and
`partial_reconciliation_source_sha256`. Each member has exactly
`member_kind="atomic_read"|"page_read"`, its global operation-request ordinal, `attempt_kind`,
nullable positive `page_ordinal`, nested exact terminal
`transport_receipt: PublisherOperationTransportReceiptV1`, `transport_receipt_sha256`, nested exact
class-bound successful `source_receipt_or_observation`,
`source_receipt_or_observation_sha256`, and nested exact `raw_response_blob`. Member ordinals are
the complete contiguous range from first through `next-1`; the array may be empty only when first
equals next, in which case the last time is null and the raw root is canonical empty. Otherwise the
last time equals the last wrapper terminal. Every page is valid but the source remains incomplete
because its authenticated Link requires the unissued next page; a terminal request failure belongs
to the failure grammar instead. The type's domain is
`laconian-publisher-partial-reconciliation-source-v1\n`, omitting only its digest.

`PublisherPartialReconciliationRoundV1` is the replayable prefix when a round cannot complete. It
has exactly `schema_version`, the same publication/operation/credential identity,
`reconciliation_round=1|2`, `termination_kind="request_failure"|"read_abort"`, ordered nested exact
`completed_sources`, nullable nested exact
`partial_source_prefix: PublisherPartialReconciliationSourceV1`, nullable
`partial_source_prefix_sha256`, positive `first_operation_request_ordinal`, positive
`next_operation_request_ordinal`, nullable nested exact
`pagination_failure: PublisherPaginationFailureReceiptV1`, nullable nested exact
`terminal_failure_transport_receipt: PublisherOperationTransportReceiptV1`,
nullable `publisher_read_abort_receipt_sha256`,
`round_status="incomplete"`, `observed_at`, and `partial_round_sha256`. Each completed source has
exactly `source_kind="branch_ref"|"pr_marker"|"check_runs"|
"release_authorization_inventory"|"latest_pointer"`, one matching nested exact class-bound
observation, and its recomputed `source_observation_sha256`. Sources are the complete attempted
protocol prefix in that literal order and nest their signed page/raw archives. Request failure
requires exactly one of pagination failure or terminal failure nonnull and a null abort digest: any
paginated collection, including failure on page one with an empty valid prefix, uses the former;
only a non-page GET uses the latter; both partial-source fields are null. Read abort requires both
failure fields null, the exact nonnull enclosing `PublisherReadAbortReceiptV1` digest, and next
request ordinal equal that receipt. Its completed sources are the maximal fully decoded source
prefix before that unissued request. The partial-source pair is nonnull exactly when the executor
stopped inside the next source, including between valid pages, and is null when it stopped before
the round's first source or exactly between sources. Completed sources plus partial-source members
partition exactly this round's contiguous global-ordinal suffix for read abort. For request failure,
completed-source wrappers plus the selected pagination failure's ordered valid-page/terminal-
failure wrappers, or the selected atomic terminal-failure wrapper, partition that suffix instead.
The suffix is `first_operation_request_ordinal..next_operation_request_ordinal-1`. Round one starts
at ordinal one; round two starts one after the final wrapper of the complete round-one observation.
For read abort, all earlier complete-round records in the enclosing final-observation projection
plus this partial round jointly partition the abort receipt's global arrays `1..next-1` and
byte-equal them. A nonnull partial
source begins exactly one ordinal after the last completed source wrapper, or at the round's first
ordinal when no source completed, and ends at the round's `next` value. The selected failure and every
completed source wrapper are present in the enclosing transport projection with byte-equal
identity/global ordinal/round/request and one-way source digest. `observed_at` is the maximum source
authenticated time and failure terminal time for request failure; for read abort it equals the
enclosing abort receipt's `aborted_at`, including an empty prefix. Its domain is
`laconian-publisher-partial-reconciliation-round-v1\n`, omitting only its final digest.
Each tagged member is a closed union: branch_ref nests only
`PublicationBranchObservationV1`, pr_marker only
`PublicationPRMarkerDiscoveryV1`, check_runs only
`PublicationFinalCheckRunsObservationSetV1`, release authorization only its exact
inventory observation, and latest_pointer only `PublicationLatestPointerObservationV1`;
all other variant fields are absent. Every nested page/observation and generic wrapper has
`observation_round=reconciliation_round`, and the completed array is exactly the maximal
source-order prefix before the selected failure.

`PublisherOperationFinalObservationProjectionV1` has exactly `schema_version`, the same identity,
`operation_kind`, `operation_idempotency_key`, ordered `observations`, `terminal_status`,
ordered nested exact `partial_rounds: PublisherPartialReconciliationRoundV1`, ordered nested exact
`pagination_failures: PublisherPaginationFailureReceiptV1`, nullable
`terminal_failure_transport_receipt_sha256`, nullable nested exact
`partial_containment_read: PublisherPartialContainmentReadV1`, nullable
`partial_containment_read_sha256`, nullable nested exact
`failed_containment_transport_receipt: PublisherOperationTransportReceiptV1`, nullable
`failed_containment_transport_receipt_sha256`, nullable nested exact
`read_abort_receipt: PublisherReadAbortReceiptV1`, nullable
`publisher_read_abort_receipt_sha256`, `observed_at`,
and `operation_final_observation_root_sha256`. Each observation has exactly
`observation_kind="branch_ref"|"pr_marker"|"pr_state"|"check_runs"|
"terminal_reconciliation"|"protected_main"|"merge_queue_preflight_pr"|"merge_queue_pr"|
"merge_queue_inventory"|"merge_queue_timeline"|"required_merge_fence_run"|
"main_commit"|"head_commit"|"main_advance_compare"`, `object_order_key`, and one
class-bound `observation_sha256` naming respectively `PublicationBranchObservationV1`,
`PublicationPRMarkerDiscoveryV1`, `PublicationPRStateObservationV1`, or
`PublicationCheckRunsObservationV1`; `terminal_reconciliation` instead names the exact
`PublicationTerminalReconciliationObservationV1` and appears zero to two times for the read operation.
The nine containment kinds respectively name
`PublicationProtectedMainObservationV1`,
`PublicationMergeQueuePreflightObservationV1`,
`PublicationMergeQueueObservationV1`,
`PublicationMergeQueueInventoryObservationV1`,
`PublicationMergeQueueTimelineReceiptV1`,
`PublicationRequiredMergeFenceRunReceiptV1`, and
`PublicationMainCommitObservationV1`, `PublicationHeadCommitObservationV1`, and
`PublicationMainAdvanceCompareReceiptV1`.
For unselected `not_minted|mint_denied_no_dispatch|
minted_permission_mismatch_then_closed_no_dispatch|
mint_delivery_unknown_unrecoverable_no_dispatch`, both nested projections have empty attempts/
observations and terminal status `no_dispatch`; their time is that disposition's own denial,
no-mint, closure, or unrecoverability boundary. A resolution instead selects either a valid-permission
minted disposition or the later `reconciliation_sourced_zero_effect` member. A stable final read
selects a minted read disposition; unavailable finality may retain minted-and-closed read
dispositions with attempted prefixes and no selected digest. Only those selected or explicitly
unavailable read members carry the operation attempts/final observations below.
Entries use protocol order, then canonical object key. Exact membership/status is: branch has its
two final ref reads and status `absent|exact|conflicting`; eligibility has its two final check
inventories and `none|exact_success|conflicting`; PR create has its final marker discovery and
`none|exact|conflicting`; terminal-guard discovery has exactly one branch observation followed by
one complete two-round marker discovery for its bound round/stage and status
`discovery_complete`; guard has its two complete check inventories and `all_failure`; close has
its pre-read followed by two final PR reads and
`already_closed_no_dispatch|publisher_close_confirmed|publisher_close_adopted|merge_won`; terminal
reconciliation has: exactly round-one then round-two observations with equal recomputed canonical
external-state digests for `stable_double_read`; zero to one complete observations for
`reconciliation_incomplete`; or exactly two observations with unequal canonical-state digests for
`reconciliation_unstable`; its read abort uses `read_aborted`. The latter three statuses are legal
only inside the exact unavailable
finality branch and authorize no synthetic attachment, no-later claim, admission or release.
Barrier-read status is exactly
`barrier_read_complete|read_aborted_before_dispatch|read_aborted_partial|barrier_read_failed`;
dequeue status is its exact attempt outcome; rerun status is
`rerun_accepted|rerun_unresolved`. A barrier selects only complete read evidence; an
aborted/failed attempt remains inventoried and a fresh credential attempt is mandatory. An original
write whose terminal transport is `response_lost_unresolved` has status
`write_delivery_ambiguous`, names no later ordinary observation and can appear only in the
fenced-ambiguity finality branch. Dequeue/rerun dispositions fabricate no causal observations:
timeline removal and required-fence evidence belong to barrier-read members. Its
partial-round/pagination arrays and terminal-failure digest are empty/null for
`no_dispatch|stable_double_read|reconciliation_unstable|write_delivery_ambiguous|
barrier_read_complete|rerun_accepted|rerun_unresolved`. The containment-prefix/failure pairs are
null for all of those statuses. A read-abort status
has the exact nested abort receipt/digest nonnull; before-first has no other failure/prefix field and
before-next contains only actually completed prefixes. A reconciliation-read before-next abort has
exactly one partial round with `termination_kind=read_abort` and byte-equal abort digest/next request;
before-first has no partial round. A barrier-read abort carries its containment prefix only inside
the abort receipt and has no projection-level failed-containment pair. Every other status requires both abort fields
null. `reconciliation_incomplete` has exactly
one partial round for the first failed round; pagination failures contain exactly its failure or are
empty when its nonnull terminal wrapper failed a non-page request, and the duplicated terminal
wrapper digest follows the opposite nullability. All earlier valid sources/pages and wrappers are
nested by the partial round and transport projection. Projection `observed_at` equals the maximum
of every complete observation and the partial-round time; for any read-abort status it instead
equals the signed abort receipt's `aborted_at`. `barrier_read_failed` requires the exact last failed
terminal wrapper nested in both failure fields plus a nonnull maximal typed
`PublisherPartialContainmentReadV1`/digest whose last member is that same wrapper. Abort fields,
reconciliation partial rounds, pagination failures and ordinary terminal-failure digest are null;
every successful prefix member and the failed member are in exact wrapper/source/archive bijection.
Projection time uses that wrapper's terminal time; it
cannot name an unattempted suffix. `object_order_key` is exactly the ASCII tuple
`<stage-rank>/<observation-kind-rank>/<canonical-object-id>`. Ordinary stage rank is `00` for the close
pre-read, `01|02` for a round-one/two source record, and `03` for a two-read aggregate such as
`PublicationPRMarkerDiscoveryV1`. Containment stage ranks are `10` preflight,
`11` pre-action, `12` action, `13` first snapshot, `14` second
snapshot and `15` main advance; no other value is valid. Kind ranks are `01` branch,
`02` PR marker, `03` PR state, `04` check runs, `05` terminal
reconciliation, `06` protected main, `07` queue-preflight PR, `08` queue PR,
`09` queue inventory, `10` queue timeline, `11` required fence run and
`12` main commit, `13` head commit and `14` main-advance compare. Canonical object ID is
exactly the branch name for branch observations, publication marker digest for PR-marker discovery,
zero-padded 20-digit PR number for PR state, lowercase head OID plus `/` plus check-set kind for
checks, or literal `aggregate` for terminal reconciliation. Keys are unique and the array is
ascending bytewise by the complete key.
For containment observations the canonical object ID is respectively `main/<snapshot>`,
`<zero-padded-20-digit-pr>/preflight`, the zero-padded PR number, `inventory/<stage>/<snapshot>`,
`timeline/<zero-padded-pr>`,
`fence/<zero-padded-20-digit-workflow-run>/<zero-padded-10-digit-run-attempt>/<merge-group-head-oid>`,
`main-commit/<commit-oid>`, `head-commit/<head-oid>`,
or `compare/<from-oid>/<to-oid>`. These values are recomputed from the nested object and unique
within the operation. Coverage is transitive rather than a false top-level/page equality: every
successful transport `source_observation_sha256` maps either to one atomic top-level observation or
to exactly one nested page/request of one top-level aggregate; every nested member maps back to one
transport wrapper, with no extra/omitted wrapper or aggregate.
Its domain is
`laconian-publisher-operation-final-observation-projection-v1\n`, omitting only its final
digest. Both projection identities/operation keys byte-equal the disposition and enclosing
resolution, and their times precede or equal `closed_or_not_minted_at`.

`PublisherBrokerLedgerEntryV1` has exactly `schema_version`, positive gapless `entry_ordinal`,
nullable `predecessor_entry_sha256`, nullable `operation_kind`, nullable
`operation_idempotency_key`, nullable positive `credential_attempt_ordinal`,
`entry_kind="phase_transition"|"token_request_started"|
"token_request_terminal"|"token_issued"|"operation_dispatch_started"|
"operation_dispatch_terminal"|"token_closed"|"no_mint"|
"token_unrecoverable"|"reconciliation_attached"|"read_aborted"|
"write_ambiguity_fence_attached"`, `phase_before`, `phase_after`, nullable
`request_terminal_outcome="definite_denial"|"successful_response"|"delivery_unknown"`, nullable
`response_status`, nullable `token_fingerprint_sha256`, nullable
`request_or_transport_receipt_sha256`, `occurred_at`, and `entry_sha256`. The first predecessor is
null and every later predecessor equals the prior entry; phases follow only
`constructive -> terminalizing -> terminal_reconciling -> sealed`, allowing a same-phase event but
never reversal. Entries have nondecreasing `occurred_at`; equal instants retain ordinal order. A
phase transition has null operation/attempt/request fields and an exact strict
phase advance; every other entry except `write_ambiguity_fence_attached` has the full operation key.
Only request-terminal has an outcome/
status: definite denial permits exactly 401, 403, 404 or 422, success requires 201, and every timeout,
connection loss, 202, 5xx, malformed/unexpected 2xx or response loss after possible server commit
is `delivery_unknown` with nullable observed status. Token issue/operation-dispatch/close entries require the
fingerprint; unknown-mint request/terminal/unrecoverability entries have none. Its domain is
`laconian-publisher-broker-ledger-entry-v1\n`,
omitting only its final digest.

Entry nullability and evidence are closed: `phase_transition` has null operation, ordinal, request
outcome/status, fingerprint and receipt; `write_ambiguity_fence_attached` has the separate exact
nullability below; every other kind has the full disposition key and same phase on both sides.
`token_request_started` names the exact
`BrokerTokenRequestDispatchReceiptV1` and `occurred_at` equals its `request_dispatched_at`; it has all other
nullable class fields null. `token_request_terminal` alone has the terminal outcome/status and names
the exact terminal token-request receipt, with `occurred_at=transport_terminal_at`.
`token_issued` names that successful receipt, carries its fingerprint, and occurs exactly at
`token_vault_committed_at`. `operation_dispatch_started` names exactly one
`PublisherOperationRequestDispatchReceiptV1`, carries the issued fingerprint, and occurs exactly at
its `request_dispatched_at`; `operation_dispatch_terminal` names its unique same-request
`PublisherOperationTransportReceiptV1`, carries the same fingerprint, and occurs exactly at
`attempt_terminal_at`. `token_closed` carries the same fingerprint and names the
recomputed full `PublisherTokenClosureProjectionV1` digest. `no_mint` names the disposition's exact
`PublisherNoMintReceiptV1` digest.
Its `occurred_at` equals that no-mint receipt's `recorded_at`. `token_unrecoverable` names its exact
`BrokerTokenUnrecoverabilityReceiptV1` digest and occurs at its `observed_at`.
`reconciliation_attached` names the exact `PublisherReconciliationAttachmentReceiptV1` digest and
has no fingerprint; its time equals `attached_at`. `read_aborted` has the full read
operation/key/credential ordinal, same phase on both sides, nonnull fingerprint, null request
outcome/status, and names the exact `PublisherReadAbortReceiptV1`; it follows that receipt's
pre-abort ledger root, has `occurred_at=aborted_at`, and precedes token closure.
`write_ambiguity_fence_attached` has null
operation/key/credential/fingerprint/outcome/status, phase before=after `terminal_reconciling`, and
names the exact `PublisherWriteAmbiguityFenceAttachmentV1` digest; it follows the attachment's
pre-attachment root and has `occurred_at=attached_at`. Every other nullable-field combination is invalid.
For a token-closed entry, disposition, full closure projection and ledger entry have byte-equal
identity, operation/key/ordinal and fingerprint; the entry receipt is exactly
`token_closure_projection_sha256`, and its `occurred_at` equals both closure `closed_at` and
disposition `closed_or_not_minted_at`.

The disposition-to-entry sequence is exact and forbids extra synthetic members. `not_minted` has
only `no_mint`. `mint_denied_no_dispatch` has exactly `token_request_started` then
`token_request_terminal(definite_denial)`. A non-aborted minted status has exactly request-started,
request-terminal(successful-response), token-issued, then zero or more adjacent
`operation_dispatch_started, operation_dispatch_terminal` pairs bijective with exactly the
dispatched transport attempts, then token-closed; the permission-mismatch status has zero dispatch
pairs and neither branch admits `read_aborted`. Within one credential attempt requests are serialized, so no second start precedes its
predecessor terminal. Not-dispatched attempts create no ledger pair. The delivery-unknown status has exactly request-started,
request-terminal(delivery-unknown), then token-unrecoverable. A
`reconciliation_sourced_zero_effect` member has exactly one `reconciliation_attached` entry, whose
receipt binds its one earlier allowed source and final-observation root; such a member exists
exactly once iff a delivery resolution selects that synthetic disposition. No other entry kind or
ordering validates for a status.
A minted read-abort sequence is request-start, request-terminal(success), token-issued, zero or
more complete operation-dispatch start/terminal pairs, `read_aborted`, then token-closed. Fenced
finality has every barrier member closed, then exactly `terminalizing -> terminal_reconciling`,
`write_ambiguity_fence_attached`, and `terminal_reconciling -> sealed`; no reconciliation-read
token/request exists in that branch.
At every ledger prefix, outstanding request count is starts minus token-request terminals and
outstanding operation-dispatch count is operation starts minus matching operation terminals; both
are nonnegative. A phase transition, token closure, reconciliation attachment, or seal is forbidden
while either applicable count is nonzero. Every operation terminal matches exactly one earlier
unmatched start by full identity/key/credential/request ordinal and nested dispatch digest, and no
start is matched twice. The final signed counts are recomputed from the complete entry array rather
than trusted scalar assertions.

`PublisherBrokerPhaseLedgerV1` has exactly `schema_version`, the same full identity,
`publisher_credential_broker_policy_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`, ordered nested exact `entries`,
`final_phase="sealed"`, `outstanding_token_request_count=0`,
`outstanding_operation_dispatch_count=0`, `live_token_count=0`,
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, `observed_at`, and
`ledger_root_sha256`. The broker signature preimage is
`UTF8("laconian-publisher-broker-ledger-signature-v1\n") || CanonicalJSONV1(record without exactly
broker_signature_base64url and ledger_root_sha256)` and verifies as specified above. The final root
is `SHA256(UTF8("laconian-publisher-broker-phase-ledger-v1\n") || CanonicalJSONV1(record without
exactly ledger_root_sha256))`, including the verified signature. The identity byte-equals the
broker policy and campaign-registry member. There is a bijection between
each disposition key `(operation_kind,operation_idempotency_key,credential_attempt_ordinal)` and
its request/no-mint plus terminal ledger entries. Every issued fingerprint has exactly one closure
entry, every dispatched operation request has one same-disposition start/terminal pair, an unknown mint has one
terminal plus one token-unrecoverable entry and no operation dispatch, and the final phase transition occurs only after
all prior entries close. Thus sealed/zero counts are replayed facts, not free assertions.
Every disposition's `broker_phase_ledger_root_sha256` is the exact hash-chain prefix ending at its
own no-mint, denial, token-unrecoverable, reconciliation-attached, or token-close entry: the field
equals that terminal entry's `entry_sha256`, and `closed_or_not_minted_at` equals its `occurred_at`.
The signed final ledger strictly extends every such prefix before its sealed phase transition.
Its `observed_at` equals that final sealed transition's `occurred_at`.
On stable-read finality, the selected `terminal_reconciliation_read` is the maximum credential-
attempt ordinal for that operation. Every synthetic attachment occurs after its second
reconciliation observation and before that read disposition's token-closed entry. On unavailable
finality there is no synthetic attachment; the maximum read-attempt ordinal is the final inventoried
failure. In either branch, the immediately following and last entry is the exact
`terminal_reconciling -> sealed` phase transition: no request, dispatch or attachment intervenes.
Stable seal time is not before read closure/probe or the second observation; unavailable seal time
is not before the final failed attempt and any partial observation.

`PublisherBrokerPhaseLedgerPrefixV1` is the signed, recomputable nonfinal prefix used by terminal
containment. It has exactly `schema_version="PublisherBrokerPhaseLedgerPrefixV1"`, the same full
publication identity, `publisher_credential_broker_policy_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`,
`prefix_purpose="containment_start"|"barrier_complete"|"pre_fence_attachment"`, ordered nested
exact `entries: PublisherBrokerLedgerEntryV1`, positive `endpoint_entry_ordinal`,
`endpoint_phase="terminalizing"|"terminal_reconciling"`, nonnegative
`outstanding_token_request_count`, nonnegative `outstanding_operation_dispatch_count`, nonnegative
`live_token_count`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, `observed_at`, and `ledger_prefix_root_sha256`. Entries are exactly
gapless ordinals one through the endpoint and replay the three scalar counts; the endpoint digest
is the last entry digest and its time equals `observed_at`. Containment start ends at the accepted
`constructive -> terminalizing` transition with all counts zero. Barrier complete ends at the last
barrier-disposition closure in terminalizing with all counts zero. Pre-fence attachment ends at the
accepted `terminalizing -> terminal_reconciling` transition with all counts zero. Its signature and
record domains are `laconian-publisher-broker-ledger-prefix-signature-v1\n` and
`laconian-publisher-broker-ledger-prefix-v1\n`, omitting exactly signature+final root and final root
respectively.

`BrokerVaultAuditPrefixV1` is the corresponding signed vault prefix. It has exactly
`schema_version="BrokerVaultAuditPrefixV1"`, nested exact
`scope_identity: BrokerVaultScopeIdentityV1(scope_kind="publication")`,
`scope_identity_sha256`, `broker_role="publisher"`,
`app_identity: GitHubAppInstallationIdentityV1(role="publisher")`, the same `prefix_purpose`,
`paired_broker_phase_ledger_prefix_sha256`, nonnegative `entry_count`, ordered nested exact
`entries: BrokerVaultAuditEntryV1`, nullable `last_entry_sha256`, nonnegative
`outstanding_token_request_count`, nonnegative `outstanding_operation_dispatch_count`, nonnegative
`live_token_count`, nested exact `broker_signing_identity:
BrokerSigningIdentityV1(signing_key.broker_role="publisher")`, `broker_signature_base64url`,
`observed_at`, and `vault_audit_prefix_root_sha256`. Its entries are the exact complete vault-log
prefix through every broker-ledger source at the paired ledger endpoint; the pair digest names the
enclosing exact ledger prefix, `entry_count=len(entries)`, and the last digest equals the final
entry or is null iff the count is zero. Its `observed_at` byte-equals the paired ledger prefix time.
The event bijection and all counts replay, and all three counts are zero for every containment purpose. Its signature and
record domains are `laconian-broker-vault-audit-prefix-signature-v1\n` and
`laconian-broker-vault-audit-prefix-v1\n` with the same exact omissions. Every later
`PublisherBrokerPhaseLedgerV1` and `BrokerVaultAuditLogV1` used by terminal finality must
byte-prefix-extend every nested signed prefix of the same scope and cannot reorder, replace, or
omit an entry. A bare ledger or vault prefix digest never proves containment finality.

`PublisherReconciliationUnavailableReceiptV1` is the total failure-only terminal record for a
publication whose required fresh reconciliation cannot complete. It has exactly `schema_version`,
the same full publication identity, `publisher_credential_broker_policy_sha256`,
`authorized_policy_row_sha256`, ordered nested exact `read_attempt_summaries`,
`terminal_reason="persistent_mint_denial"|"persistent_permission_mismatch"|
"persistent_delivery_unknown"|"authenticated_read_unavailable"|
"unstable_external_state"`,
`stable_double_read_count=0`, `outstanding_token_request_count=0`,
`outstanding_operation_dispatch_count=0`, `live_token_count=0`,
`final_broker_phase_ledger_root_sha256`, `vault_audit_log_root_sha256`,
`release_authorization_ledger_snapshot: PublicationReleaseAuthorizationLedgerSnapshotV1`,
`release_authorization_ledger_root_sha256`,
`canonical_external_state_claimed=false`, `admission_authorized=false`,
`release_authorized=false`, `terminal_invalidation_required=true`,
`required_terminal_event_type="PERMANENT_STOP"|"INVALID_PUBLICATION_PLAN_INVALIDATED"|
"RESULT_MERGE_INVALIDATED"|"INVALID_PREFIX_MERGE_INVALIDATED"|"CORRECTION_INVALIDATED"`,
`recorded_at`, and
`reconciliation_unavailable_receipt_sha256`. Each summary has exactly positive
`credential_attempt_ordinal`, `credential_disposition_sha256`,
`operation_transport_root_sha256`, `operation_final_observation_root_sha256`, ordered zero-to-two
`round_observation_sha256s`, and `terminal_status="no_dispatch"|
"reconciliation_incomplete"|"reconciliation_unstable"|"read_aborted"`. The three summaries are a complete
bijection over
all terminal-reconciliation credential attempts and preserve every denial, mismatch, unknown mint,
closed token and authenticated read prefix; their roots/digests recompute from the exact nested
dispositions in the enclosing set. A single observation is evidence only of that one read and
never a stable external-state claim. Exactly the policy's three attempts are terminal, use its
literal retry schedule from the prior terminal time, and freshly reauthorize before each mint; only
earlier stable success avoids exhaustion. “Persistent” means this exact three-attempt exhaustion,
not that the first two attempts share the final class; all three remain inventoried. The terminal
reason is derived from the final summary's exact disposition/status by this total mapping:

| Final disposition and observation status | Exact terminal reason |
|---|---|
| `mint_denied_no_dispatch` / `no_dispatch` | `persistent_mint_denial` |
| `minted_permission_mismatch_then_closed_no_dispatch` / `no_dispatch` | `persistent_permission_mismatch` |
| `mint_delivery_unknown_unrecoverable_no_dispatch` / `no_dispatch` | `persistent_delivery_unknown` |
| `minted_then_closed` / `reconciliation_incomplete` | `authenticated_read_unavailable` |
| `minted_then_closed` / `read_aborted` | `authenticated_read_unavailable` |
| `minted_then_closed` / `reconciliation_unstable` | `unstable_external_state` |

`not_minted`, `reconciliation_sourced_zero_effect`, any other disposition/status pair, or any
stable observation is forbidden in the three summaries. Two complete but unequal rounds select
`unstable_external_state` and retain both roots. An incomplete final summary with no complete
observation has its final-observation time equal the latest failed wrapper or pagination-failure
receipt; with one complete observation it is the maximum of that observation and the failed
wrapper/receipt time. `read_aborted` names the exact abort receipt in the final projection; its summary time is
`aborted_at`, its completed observations are exactly that receipt's prefix, and it consumes one of
the three retry attempts. Before-first has no round observation. The two broker roots equal the
enclosing sealed signed broker ledger and
vault log with recomputed zero counts. The nested release-authorization snapshot has the same
publication scope, an empty entry array, all three authorization/mint/dispatch counts zero, and a
recomputed signed root; `release_authorized=false` is its exact projection rather than a free
assertion. `recorded_at` byte-equals the enclosing disposition-set `observed_at`, broker-ledger
`observed_at`, vault-log `sealed_at`, and signed release-ledger snapshot `observed_at`.
`required_terminal_event_type` is derived only from identity/phase and terminal disposition:
initial complete `no_pr|closed` maps to `PERMANENT_STOP`; initial invalid-prefix `no_pr|closed`
maps to `INVALID_PUBLICATION_PLAN_INVALIDATED`; initial complete `already_merged` maps to
`RESULT_MERGE_INVALIDATED`; initial invalid-prefix `already_merged` maps to
`INVALID_PREFIX_MERGE_INVALIDATED`; and every correction maps to `CORRECTION_INVALIDATED`.
Its domain is
`laconian-publisher-reconciliation-unavailable-receipt-v1\n`, omitting only its final digest. This
record can authorize only the phase-exact initial `PERMANENT_STOP`, invalid-prefix plan
invalidation, correction-publication invalidation, or merge-failure edge enumerated in the state
table; it cannot appear in
`PublicationNoLaterEffectsEvidenceV1`, `PublicationSuccessFinalityEvidenceV1`, merge admission or
release preparation.

`PublisherCredentialDispositionSetV1` has exactly `schema_version`, the same identity,
`publisher_credential_broker_policy_sha256`, ordered nested exact
`dispositions: PublisherOperationCredentialDispositionV1`,
`finality_status="stable_read_sealed"|"reconciliation_unavailable_sealed"|
"write_ambiguity_fenced_sealed"`, nullable
`terminal_reconciliation_read_disposition_sha256`, nullable
`terminal_merge_barrier_sha256`, nullable
`publisher_barrier_credential_dispositions_root_sha256`, nullable nested exact
`write_ambiguity_fence_attachment: PublisherWriteAmbiguityFenceAttachmentV1`, nullable
`publisher_write_ambiguity_fence_attachment_sha256`, nullable nested exact
`reconciliation_unavailable_receipt: PublisherReconciliationUnavailableReceiptV1`,
nullable `reconciliation_unavailable_receipt_sha256`,
`final_broker_phase="sealed"`,
`broker_phase_ledger: PublisherBrokerPhaseLedgerV1`,
`final_broker_phase_ledger_root_sha256`, nested exact
`broker_vault_audit_log: BrokerVaultAuditLogV1(scope_kind="publication",broker_role="publisher")`,
`vault_audit_log_root_sha256`, `outstanding_token_request_count=0`,
`outstanding_operation_dispatch_count=0`, `live_token_count=0`, `observed_at`, and
`credential_dispositions_root_sha256`. Dispositions are complete and sorted by the literal total
key `(operation_rank,bound_round_or_0,bound_head_or_object_key,
operation_idempotency_key,credential_attempt_ordinal)`, where operation rank is branch,
eligibility, PR create, terminal-guard discovery, guard, close, barrier-read, barrier-dequeue,
fence-rerun, reconciliation-read, with numeric ranks `01..10` in that order; round is zero unless the authorized
operation key binds a positive guard/close/reconciliation round; and the bound head/object key is
the lowercase head OID, canonical PR number, or empty string exactly as the policy row defines.
Credential-attempt ordinals are gapless positive integers independently within each operation-
idempotency key. Denied,
unrecoverable or permission-mismatched attempts followed by a valid retry remain distinct members.
For `stable_read_sealed`, both unavailable and attachment pairs are null and the named read disposition is the
unique final selected member and a closed valid read-only token. Its ledger root is
the exact prefix ending at that read's close/attachment entry. The set's separate final broker root
equals the nested signed sealed ledger's recomputed `ledger_root_sha256`, which strictly extends
that prefix. Its vault root equals the nested signed log's recomputed root. The set `observed_at`
equals the ledger `observed_at`, vault-audit `sealed_at`, and final sealed transition time; every
disposition, ledger entry and audit entry obeys the exact source-receipt bijection above. Every
nested closure/unrecoverability predecessor digest names the exact prior audit entry, and the next
terminal audit entry names that closure/unrecoverability receipt. The set domain is
`laconian-publisher-credential-disposition-set-v1\n`, omitting only its final digest.
For `reconciliation_unavailable_sealed`, the named read disposition is null, the exact unavailable
receipt/digest are nonnull, the attachment pair is null, and it is root/count-equal to the two nested signed ledgers, every attempted read
disposition remains inventoried, and no synthetic attachment or stable reconciliation projection is
claimed. Sealing is allowed only after all request/operation pairs and tokens are closed; it grants
no success authority.
The barrier digest/subset pair is both null only outside terminal containment. Within terminal
containment it is always nonnull: premerge finality names the all-candidates barrier, and either
merge-won finality names the exact `residual_unmerged_after_merge_won` barrier nested by
`PublicationContainmentMergeWonEvidenceV1`, including its zero-candidate barrier. The subset is the
exact canonical disposition projection of that same barrier. Stable and unavailable finality both
follow this consuming-route rule; the fact that `PublicationTerminalContainmentFinalityV1` stores
merge-won barrier fields only through its nested evidence does not make the disposition-set fields
nullable. For `write_ambiguity_fenced_sealed` the reconciliation
read and unavailable pairs are null; barrier/subset and attachment pairs are nonnull and recompute.
No reconciliation-read disposition exists. The array inventories every ambiguity-source
disposition plus every barrier-read/dequeue/rerun attempt. The nested barrier subset is an exact
canonical subarray and the final signed ledger/vault byte-prefix-extend its two prefix roots; no
other disposition may intervene before the subset endpoint. The sealed ledger contains the exact
fence-attachment sequence, all three counts are zero, and neither the set nor attachment claims
stable external state, admission or release authority.

Every branch, eligibility, PR-create, guard, and close delivery resolution names exactly one
resolution-selected disposition with matching identity, operation, idempotency key, transport root
and final-observation root: either the valid minted effect member or a later
`reconciliation_sourced_zero_effect` member. Earlier denied, mismatched, unknown-mint or no-request
members remain in the set but are not that resolution link. Its constructive or terminal receipt
repeats the selected disposition digest. A
terminal guard's post-dispatch check observations occur before its write token is closed; the final
guard set additionally names every exact `terminal_guard_discovery` disposition through its round
fields. Discovery members are resolution-selected only by that set, carry `discovery_complete`, and
can never be substituted for a per-head guard or an ordinary write resolution. A
stable guard snapshot is then re-read into a distinct `guarded_reconciliation` object with exactly
one read-only `terminal_reconciliation_read` disposition. The terminal/no-later record inventories every disposition in canonical operation,
round, head and attempt order and proves the broker ledger is in `sealed` with zero live tokens.

The two initial publication effect receipts are exact closed wire records. Their ordered fields
and types are:

```text
PublicationBranchReceiptV1
  schema_version = "PublicationBranchReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  publication_attempt: positive canonical integer
  intent_sha256: lowercase SHA-256
  operation: "created" | "adopted"
  branch_name: bounded nonblank string
  base_oid: lowercase 40-hex Git OID
  head_oid: lowercase 40-hex Git OID
  branch_create_delivery_resolution_sha256: lowercase SHA-256
  publisher_credential_disposition_sha256: lowercase SHA-256
  actor: GitHubAppInstallationIdentityV1(role="publisher")
  request_receipts_root: lowercase SHA-256
  receipt_sha256: lowercase SHA-256

PublicationPRReceiptV1
  schema_version = "PublicationPRReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  publication_attempt: positive canonical integer
  intent_sha256: lowercase SHA-256
  branch_receipt_sha256: lowercase SHA-256
  operation: "created" | "adopted"
  pull_request_number: positive canonical integer
  pull_request_node_id: bounded nonblank string
  pull_request_url: exact ASCII HTTPS URL
  base_oid: lowercase 40-hex Git OID
  head_oid: lowercase 40-hex Git OID
  marker: bounded nonblank string
  merge_eligibility_receipt_sha256: lowercase SHA-256
  merge_eligibility_delivery_resolution_sha256: lowercase SHA-256
  pr_create_delivery_resolution_sha256: lowercase SHA-256
  pr_marker_discovery_sha256: lowercase SHA-256
  eligibility_publisher_credential_disposition_sha256: lowercase SHA-256
  pr_create_publisher_credential_disposition_sha256: lowercase SHA-256
  actor: GitHubAppInstallationIdentityV1(role="publisher")
  request_receipts_root: lowercase SHA-256
  receipt_sha256: lowercase SHA-256
```

Their digest domains are respectively `laconian-publication-branch-receipt-v1\n` and
`laconian-publication-pr-receipt-v1\n`, over RFC 8785 JSON omitting only `receipt_sha256`. Every
identity, plan-bound branch/base/head/marker, actor, merge-eligibility check and its closed delivery,
PR create delivery and marker discovery, and parent receipt must
match reconstructed intent authority. The PR number is learned only from authenticated create/adopt discovery and can
never appear in the intent.

Persisting those two receipts uses a second closed non-event family.
`InitialPublicationReceiptAppendV1` is a strict `receipt_kind`-discriminated union of
`InitialBranchReceiptAppendV1` and `InitialPRReceiptAppendV1`. Every variant has exactly
`schema_version`, `mutation_kind="initial_publication_receipt_append"`, literal `receipt_kind`,
`campaign_id`, `campaign_registry_sha256`, `publication_id`, positive `publication_attempt`, `bundle_kind`,
`authorizing_intent_sha256`, `publication_plan_sha256`, `authority_parent_oid`,
`campaign_state_sha256_before`, `campaign_state_sha256_after`, nullable
`predecessor_append_sha256`, literal `receipt_path`, one class-bound `receipt_payload`,
`append_idempotency_key`, `recorded_at`, and `append_sha256`. Branch uses schema
`InitialBranchReceiptAppendV1`, kind `branch`, path `branch-receipt.json`, null predecessor, payload
`PublicationBranchReceiptV1`, and domain `laconian-initial-branch-receipt-append-v1\n`. PR uses
schema `InitialPRReceiptAppendV1`, kind `pull_request`, path `pr-receipt.json`, predecessor equal to
the accepted branch append digest, payload `PublicationPRReceiptV1`, and domain
`laconian-initial-pr-receipt-append-v1\n`. Each domain hashes canonical JSON omitting only
`append_sha256`.

`recorded_at` is deterministic canonical whole-second UTC and equals the accepted
`PUBLICATION_INTENT_AUTHORIZED` event's timestamp plus exactly one second for branch or two seconds
for PR. Only `benchmark-publish.yml` on the protected plan-bound main ref may request the family,
only while state remains the matching `BUNDLE_COLLECTED` or `INVALID_FINALIZED` with that exact
active intent, and only with null hold and active-exposure roots. Branch then PR is the sole order.
The wrapper parent OID, request expected OID, and reconstructed authority OID are equal; wrapper,
outer-request, and intent-authorized receipt-CAS idempotency keys are equal; both state hashes equal
the current byte-identical `campaign-state.json`. Each append retains the entire prior authority
tree byte-for-byte, appends only its one absent path, changes no state name/transition/root, and
creates no event. `*_PUBLICATION_PR_OPENED` is rejected until both exact appends exist; response
loss is reconciled only by adopting the exact external object and exact candidate authority commit.
This family cannot append a merge, invalidation, release, correction, arbitrary path, or generic
same-state record.

After `RESULT_MERGED`, `RESULT_RELEASE_INTENT_AUTHORIZED` installs `release-intent.json` before any
release effect. It binds the deterministic annotated-tag bytes/OID/name/target, draft Release
name/body/marker, ordered asset names/byte sizes/digests, release-finalizer actor, immutable-Release
policy root, and distinct idempotency keys for tag, draft, each asset, publish, each receipt, and
finalization. The finalizer queries exact names first: it creates or adopts only a byte-identical
annotated tag; creates or adopts only the exact draft; uploads only an absent intent-bound asset
while draft; adopts an existing asset only when name, size, digest, release ID, and actor match; and
publishes only an exact complete draft. If publish succeeded but the response or `RESULT_RELEASED`
CAS was lost, it verifies the immutable published release, tag, every asset, and actor, adopts them,
persists the missing receipts, and emits `RESULT_RELEASED` once.

Those missing initial-release receipts use one closed non-event authority family; they are not
`CampaignEventV1` self-loops. `InitialReleaseReceiptAppendV1` is a strict `receipt_kind`
discriminated union of `InitialTagReceiptAppendV1`, `InitialDraftReleaseReceiptAppendV1`,
`InitialAssetReceiptsAppendV1`, and `InitialPublishReceiptAppendV1`. Every variant has exactly
`schema_version`, `mutation_kind="initial_release_receipt_append"`, its literal `receipt_kind`,
`campaign_id`, `campaign_registry_sha256`, `publication_id`, positive `publication_attempt`,
`authorizing_intent_sha256`,
`preauthorized_release_plan_sha256`, `executable_release_plan_sha256`,
`security_attestor_receipt_sha256`, `authority_parent_oid`,
`campaign_state_sha256_before`, `campaign_state_sha256_after`, nullable
`predecessor_append_sha256`, literal `receipt_path`, one class-bound `receipt_payload`,
`append_idempotency_key`, `recorded_at`, and `append_sha256`. `recorded_at` is deterministic
canonical whole-second UTC: it equals the accepted `RESULT_RELEASE_INTENT_AUTHORIZED` event's
`recorded_at` plus exactly one, two, three, or four seconds for tag, draft, aggregate assets, or
publish respectively. No workflow clock, effect timestamp, or retry time may choose it. The four
variant domains are respectively
`laconian-initial-tag-receipt-append-v1`,
`laconian-initial-draft-release-receipt-append-v1`,
`laconian-initial-asset-receipts-append-v1`, and
`laconian-initial-publish-receipt-append-v1`, each followed by LF and canonical JSON omitting only
`append_sha256`.
The four `receipt_payload` types are respectively strict `TagReceiptV1`,
`DraftReleaseReceiptV1`, the exact ordered tuple of two `ReleaseAssetReceiptV1` values with ordinals
zero and one, and `PublishReceiptV1`; no raw JSON, union fallback, or locally flattened duplicate is
accepted.

| Append variant | Exact `schema_version` | `receipt_kind` | Basename | Exact payload and payload digest domain |
|---|---|---|---|---|
| `InitialTagReceiptAppendV1` | `InitialTagReceiptAppendV1` | `tag` | `tag-receipt.json` | `TagReceiptV1`; `laconian-tag-receipt-v1\n`; omit only `receipt_sha256` |
| `InitialDraftReleaseReceiptAppendV1` | `InitialDraftReleaseReceiptAppendV1` | `draft_release` | `draft-release-receipt.json` | `DraftReleaseReceiptV1`; `laconian-draft-release-receipt-v1\n`; omit only `receipt_sha256` |
| `InitialAssetReceiptsAppendV1` | `InitialAssetReceiptsAppendV1` | `assets` | `asset-receipts.json` | two `ReleaseAssetReceiptV1`; each `laconian-release-asset-receipt-v1\n`; omit only its `receipt_sha256` |
| `InitialPublishReceiptAppendV1` | `InitialPublishReceiptAppendV1` | `publish` | `publish-receipt.json` | `PublishReceiptV1`; `laconian-publish-receipt-v1\n`; omit only `receipt_sha256` |

Release planning uses a one-way, acyclic three-stage graph. The receipt-free initial member is
`InitialPreauthorizedResultReleasePlanV1`, with exactly `schema_version`, `intent_kind="initial"`,
`campaign_id`, `campaign_registry_sha256`, `publication_id`, positive `publication_attempt`, null
`correction_id`, `publication_plan_sha256`, `publication_merge_receipt_sha256`,
`admitted_merge_commit_oid`, `result_tree_oid`, `result_tree_sha256`,
`sealed_bundle_root_sha256`, `provenance_root_sha256`, `tag_target_kind="initial_merge"`,
`authorized_tag_target_oid`, `tag_name`, `tagger_name`, `tagger_email`, `tagger_timestamp`,
`tag_message_sha256`, `annotated_tag_bytes_sha256`, `expected_tag_object_oid`,
`draft_release_name`, `draft_release_body_sha256`, `release_marker`, ordered exact `assets`,
`tag_ruleset_policy_sha256`, `immutable_release_policy_sha256`,
`release_finalizer_app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`release_workflow_sha256`, `common_workflow_root_sha256`, exact `idempotency_keys`, and
`preauthorized_release_plan_sha256`. Each asset has exactly `asset_ordinal=0|1`, `name`,
`byte_length`, and `sha256`; the array is exactly `[0,1]`. `idempotency_keys` has exactly `tag`,
`tag_object`, `tag_ref`, `draft_release`, `asset_0`, `asset_1`, `publish`, `final_verification`,
`tag_receipt_append`, `draft_receipt_append`, `asset_receipts_append`, `publish_receipt_append`, and
`finalization`. The admitted merge and authorized tag target are the same lowercase Git OID. Its
domain is `laconian-initial-preauthorized-result-release-plan-v1\n`, omitting only its final digest;
it contains no attestor, executable-plan, intent, effect, preparation, invalidation or finalization
root.

The correction preauthorization is the immutable nested `CorrectionReleaseIntentPlanV1`. It has
exactly `schema_version`, `intent_kind="correction"`, `campaign_id`,
`campaign_registry_sha256`, `publication_id`, null `publication_attempt`, exact path-safe
`correction_id`, `correction_publication_plan_sha256`,
`approved_head_oid`, `tag_target_kind="correction_approved_head"`,
`authorized_tag_target_oid`, the same tag/tagger/annotated-object, draft/marker/assets, policy,
finalizer/workflow and exact idempotency-key fields as the initial plan, and `plan_sha256`.
`authorized_tag_target_oid` equals the immutable correction publication plan's approved head OID.
Its domain is `laconian-correction-release-intent-plan-v1\n`, omitting only `plan_sha256`; that
digest is the correction `preauthorized_release_plan_sha256`. It contains no observed future merge,
attestor or executable-plan root.

`ExecutableResultReleasePlanV1` has exactly `schema_version`, `intent_kind`, `campaign_id`,
`campaign_registry_sha256`, `publication_id`, nullable `publication_attempt`, nullable
`correction_id`, nullable `correction_intent_sha256`, nested exact `preauthorized_plan` as one of
the two plan types above,
`preauthorized_release_plan_sha256`, nested exact
`security_attestor_receipt: SecurityAttestorReceiptV1(result="pass",
attestation_purpose="release_preparation")`, `security_attestor_receipt_sha256`,
`admitted_merge_receipt_sha256`, `observed_merge_commit_oid`, ordered
`observed_merge_parent_oids`, `observed_result_tree_oid`, `observed_result_tree_sha256`,
`observed_provenance_root_sha256`, `tag_target_kind`, `authorized_tag_target_oid`,
`expected_tag_object_oid`, and `executable_release_plan_sha256`. Initial identity has positive
attempt/null correction; correction has null attempt/path-safe correction ID. The preauthorized
plan digest is recomputed from the exact nested member and equals the attestor's same field; the
attestor digest is recomputed and equals its duplicated root. Observed merge facts equal the
accepted initial or correction merge receipt, while effect names/bytes/assets/idempotency keys are
copied only from the preauthorized member. Initial target equals its observed admitted merge `M`.
Correction target remains the immutable approved head from `CorrectionIntentV1`; the actual
correction merge `M` remains separately bound as admission lineage and never silently retargets the
tag. Its domain is `laconian-executable-result-release-plan-v1\n`, omitting only its final digest.
Neither predecessor points back to this executable root.
`correction_intent_sha256` is null for initial. For correction it equals the one active original
`CorrectionIntentV1.intent_sha256`, the attestor receipt's same field, and every downstream
`ReleaseEffectAuthorizationV1.authorizing_intent_sha256`; cross-intent replay is rejected.

`ResultReleaseIntentV1`, installed only for initial release, has exactly
`schema_version="ResultReleaseIntentV1"`, the
initial identity, `publication_plan_sha256`, `publication_merge_receipt_sha256`, nested exact
`executable_release_plan: ExecutableResultReleasePlanV1(intent_kind="initial")`,
`preauthorized_release_plan_sha256`, `security_attestor_receipt_sha256`,
`executable_release_plan_sha256`, `authority_parent_oid`, `recorded_at`, and
`result_release_intent_sha256`. All three duplicated roots equal the nested executable graph. The
correction authorizing intent is instead the original immutable `CorrectionIntentV1`; no second
postmerge correction intent may rewrite its tag target. Its digest is
`SHA256(UTF8("laconian-result-release-intent-v1\n") || CanonicalJSONV1(record without exactly
result_release_intent_sha256))`.

The shared nested release records have these exact ordered fields and types:

```text
ReleaseEffectAuthorizationV1
  schema_version = "ReleaseEffectAuthorizationV1"
  intent_kind: "initial" | "correction"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  publication_attempt: positive canonical integer | null
  correction_id: path-safe correction ID | null
  authorizing_intent_sha256: lowercase SHA-256
  preauthorized_release_plan_sha256: lowercase SHA-256
  executable_release_plan_sha256: lowercase SHA-256
  security_attestor_receipt_sha256: lowercase SHA-256
  tag_target_kind: "initial_merge" | "correction_approved_head"
  authorized_tag_target_oid: lowercase 40-hex Git OID
  authorization_sha256: lowercase SHA-256

ReleaseEffectResultV1
  schema_version = "ReleaseEffectResultV1"
  effect_kind: "tag_object" | "tag_ref" | "draft_release" | "asset" | "publish" | "final_verification"
  authorization: ReleaseEffectAuthorizationV1
  effect_idempotency_key: lowercase SHA-256
  api_method: "POST" | "PATCH" | "GET"
  endpoint_template: bounded nonblank string
  request_payload_sha256: lowercase SHA-256
  request_receipts_root: lowercase SHA-256
  response_status: positive canonical integer
  raw_response_sha256: lowercase SHA-256
  canonical_response_sha256: lowercase SHA-256
  operation: "created" | "uploaded" | "published" | "adopted" | "verified"
  external_object_observation_sha256: lowercase SHA-256
  effect_result_sha256: lowercase SHA-256

AnnotatedTagEffectResultsV1
  schema_version = "AnnotatedTagEffectResultsV1"
  tag_effect_idempotency_key: lowercase SHA-256
  tag_object_effect_result: ReleaseEffectResultV1(effect_kind="tag_object")
  tag_ref_effect_result: ReleaseEffectResultV1(effect_kind="tag_ref")
  effect_results_root_sha256: lowercase SHA-256

InstallationTokenRevocationReceiptV1
  schema_version = "InstallationTokenRevocationReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  authorization_sha256: lowercase SHA-256
  effect_kind: "tag" | "draft_release" | "asset" | "publish" | "final_verification"
  subject_kind: "complete_effect_result" | "partial_effect_prefix" | "failed_delivery_resolution"
  subject_root_sha256: lowercase SHA-256
  token_closure_projection_sha256: lowercase SHA-256
  app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")
  token_fingerprint_sha256: lowercase SHA-256
  token_vault_committed_at: canonical whole-second UTC
  token_expires_at: canonical whole-second UTC
  endpoint = "DELETE /installation/token"
  api_version = "2022-11-28"
  outcome: "revoked_204" | "ambiguous_delivery_then_confirmed_unusable" | "expired_then_confirmed_unusable"
  revoked_or_confirmed_unusable_at: canonical whole-second UTC
  revocation_receipt_sha256: lowercase SHA-256

FinalReleaseVerificationReceiptV1
  schema_version = "FinalReleaseVerificationReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  authorization: ReleaseEffectAuthorizationV1
  effect_result: ReleaseEffectResultV1(effect_kind="final_verification")
  effect_delivery_resolution_sha256: lowercase SHA-256
  immutable_release_verification_sha256: lowercase SHA-256
  final_external_objects_root_sha256: lowercase SHA-256
  actor: GitHubAppInstallationIdentityV1(role="release_finalizer")
  request_receipts_root: lowercase SHA-256
  installation_token_revocation: InstallationTokenRevocationReceiptV1(effect_kind="final_verification")
  receipt_sha256: lowercase SHA-256
```

Their digest domains are respectively `laconian-release-effect-authorization-v1\n`,
`laconian-release-effect-result-v1\n`, and
`laconian-installation-token-revocation-receipt-v1\n`, omitting only each record's final digest.
`AnnotatedTagEffectResultsV1` uses `laconian-annotated-tag-effect-results-v1\n`, omitting only its
final root.
Every authorization revalidates the exact `ExecutableResultReleasePlanV1`: campaign/registry/
publication and initial/correction XOR identity, preauthorized/executable/attestor roots and tag
target tuple byte-equal it. Initial authorizing intent is the exact `ResultReleaseIntentV1` and
targets admitted initial merge `M`; correction authorizing intent is the original
`CorrectionIntentV1` and targets its approved publication head. Every effect result and external
observation repeats the same authorization; a correction's observed merge `M` cannot replace the
authorized target.

`ReleaseFinalizerTokenClosureProjectionV1` is the acyclic credential sibling. It has exactly
`schema_version`, the same full initial/correction release identity, `repository_id`, `release_phase`,
`effect_kind`, `effect_step_kind`, `effect_step_ordinal`, `effect_idempotency_key`, positive
`credential_attempt_ordinal`, `broker_role="release_finalizer"`,
`app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`release_finalizer_broker_policy_sha256`, `token_request_receipt_sha256`, ordered
`requested_permissions`, ordered `returned_permissions`, `token_fingerprint_sha256`,
`token_vault_committed_at`, `token_expires_at`,
`closure_outcome="revoked_204"|"ambiguous_delivery_then_confirmed_unusable"|
"expired_then_confirmed_unusable"`, ordered nested exact
`delete_attempts: BrokerTokenDeleteAttemptV1`, `closure_boundary_at`, ordered nested exact
`denial_probe_attempts: BrokerTokenDenialProbeV1`,
`post_boundary_same_token_operation_dispatch_count=0`, `vault_audit_predecessor_entry_sha256`, `closed_at`,
and `token_closure_projection_sha256`. It obeys the exact common serialized delete/probe and
outcome/boundary matrix defined above, substituting the release-finalizer role/App/policy; every
member and the successful nested request transport in its disposition byte-equal its identity,
fingerprint, permissions and token times. Its domain is
`laconian-release-finalizer-token-closure-projection-v1\n`, omitting only its final digest. Every
revocation receipt and credential disposition that refer to one token byte-equal this projection;
the revocation's time equals closure `closed_at` and adds the subject link only after the
delivery/prefix digest exists.

Failure/recovery uses a closed result rather than hiding transport state.
`ReleaseEffectDeliveryResolutionV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `publication_id`, nullable `publication_attempt`, nullable
`correction_id`, `release_phase`, `preauthorized_release_plan_sha256`, nullable nested exact
`authorization: ReleaseEffectAuthorizationV1`, `effect_kind`, `effect_step_kind`,
`effect_step_ordinal`, `effect_idempotency_key`, ordered `attempts`, nested exact
`first_external_object_observation: ReleaseExternalObjectObservationV1`, nested exact
`second_external_object_observation: ReleaseExternalObjectObservationV1`,
`resolved_status="not_dispatched"|"rejected_no_side_effect"|"exact_success"|"conflicting"`,
nullable nested exact
`effect_result: ReleaseEffectResultV1`, `release_finalizer_credential_disposition_sha256`,
`delivery_ambiguity=false`, `recorded_at`, and
`effect_delivery_resolution_sha256`. Each attempt has exactly positive `ordinal`, `request_id`,
`dispatch_state="not_dispatched"|"dispatched"`, the step's literal method and endpoint,
`request_payload_sha256`, `outcome=not_dispatched|definitely_rejected_no_side_effect|
delivered_exact|response_lost_resolved_exact|non_2xx_resolved_exact|
resolved_conflicting`, nullable `response_status`, nullable `safe_response_sha256`, and
nullable nested exact `transport_receipt: ReleaseOperationTransportReceiptV1`, and
nullable `transport_receipt_sha256`. Not-dispatched attempts require both transport fields null;
every dispatched attempt requires the exact nested terminal wrapper and recomputed duplicated
digest, whose attempt/effect/request/method/endpoint/payload/status fields byte-equal this attempt.
Status/nullability follows the same conservative matrices below:
non-dispatch has null response fields, definite rejection permits only 400/401/403/404 plus safe
proof, response-loss has null status, and non-2xx exact/conflict permits only 409 or 422 plus two
equal authenticated observations. `exact_success` alone embeds the byte-identical effect result;
`rejected_no_side_effect` requires at least one definite rejection, no possibly delivered attempt,
and two final absence observations; `not_dispatched` requires every attempt not dispatched and the
same stable absence. `conflicting` preserves the stable nonmatching object but cannot produce a
success receipt. The identity, authorization and literal effect tuple in both observations
byte-equal the resolution. The two final observations have identical canonical external state;
for exact success the effect result's observation digest equals the second observation digest.
`recorded_at` byte-equals the second authenticated observation's `observed_at`; retry or local time
cannot select it. Its domain is
`SHA256(UTF8("laconian-release-effect-delivery-resolution-v1\n") || CanonicalJSONV1(record without
exactly effect_delivery_resolution_sha256))`.
Initial identity requires a positive bounded attempt and null correction ID; correction identity
requires null attempt and its exact path-safe correction ID.
At `pre_intent`, authorization is null, every attempt is not dispatched, and only
`not_dispatched|conflicting` can result from authenticated pre-effect reads against the
preauthorized plan. At every later phase authorization is nonnull and byte-equals the executable
plan/intent roots. Exact success is forbidden without it.

The effect tuple is not a cross-product. It is exactly `(tag,tag_object,0)`,
`(tag,tag_ref,1)`, `(draft_release,draft_release,0)`, `(asset,asset,0)`, `(asset,asset,1)`,
`(publish,publish,0)`, or `(final_verification,final_verification,0)`. The nested
`ReleaseEffectResultV1.effect_kind` equals `effect_step_kind`; aggregate `effect_kind=tag` never
appears as a step-result kind.

`PartialAnnotatedTagEffectV1` has exactly `schema_version`, the same identity/authorization,
`tag_object_delivery_resolution: ReleaseEffectDeliveryResolutionV1(effect_kind="tag",
effect_step_kind="tag_object", effect_step_ordinal=0, resolved_status="exact_success")`,
`tag_object_effect_result: ReleaseEffectResultV1(effect_kind="tag_object")`,
`tag_ref_delivery_resolution: ReleaseEffectDeliveryResolutionV1(effect_kind="tag",
effect_step_kind="tag_ref", effect_step_ordinal=1,
resolved_status="rejected_no_side_effect"|"conflicting")`, and `partial_effect_root_sha256`. It uses
`laconian-partial-annotated-tag-effect-v1\n`, omitting only its final digest. The object success
precedes the ref failure; target/name/OID and derived step keys equal intent. The sibling
revocation receipt points to this completed prefix root, but the prefix never hashes that receipt,
avoiding a digest cycle. This is the only typed tag-object-without-ref partial preimage.
`PartialAssetEffectsV1` has exactly `schema_version`, the same identity/authorization,
`failed_asset_ordinal=0|1`, ordered `successful_prefix`,
`failed_asset_delivery_resolution: ReleaseEffectDeliveryResolutionV1(effect_kind="asset",
effect_step_kind="asset", resolved_status="rejected_no_side_effect"|"conflicting")`, and
`partial_effect_root_sha256`. A prefix entry has exactly `asset_ordinal`, an exact-success delivery
resolution and its byte-identical `ReleaseEffectResultV1(effect_kind="asset")`. Ordinal zero failure
requires empty prefix; ordinal one requires exactly successful ordinal zero. The failed resolution
has the named ordinal. Its domain is `laconian-partial-asset-effects-v1\n`, omitting only its final
digest. These two aggregate-prefix types are the only meaning of `partial_effect`; no single-step
delivery resolution has a partial status.
`FinalReleaseVerificationReceiptV1` uses
`laconian-final-release-verification-receipt-v1\n` and omits only `receipt_sha256`.
The effect result embeds the byte-identical authorization, and revocation repeats that
authorization digest, exact effect kind/subject root, and finalizer App identity. For the first two
outcomes revocation time is not before authenticated token-response completion or after token expiry; the ambiguous outcome
requires the exact failed-delivery receipt plus a successful post-revocation denial probe.
`expired_then_confirmed_unusable` instead requires observation at or after response-bound expiry, any DELETE
attempt receipt, a denied post-expiry authenticated probe, and proof of no successful use after
expiry. No token bytes, raw authorization header,
or secret response field is representable.

`PostMergeAdmissionSubjectV1` is the cycle-free input to the postmerge security attestor. It has
exactly `schema_version`, `campaign_id`, `campaign_registry_sha256`, `repository_id`,
`intent_kind="initial"|"correction"`, `publication_id`, nullable `publication_attempt`, nullable
`correction_id`, `authorizing_intent_sha256`, `result_plan_sha256`, positive
`pull_request_number`, `base_branch_name`, `base_oid`, `head_branch_name`, `head_oid`,
`observed_merge_commit_oid`, `observed_merge_tree_oid`, `current_main_oid`,
`current_main_containment_root_sha256`, positive `merge_actor_account_id`,
`merge_actor_login`, `merged_at`, and `postmerge_admission_subject_sha256`. Every field is projected
from the plan-bound PR and two stable authenticated merged observations; the merge commit has exact
parents/base-head relation and expected tree. It contains no security-attestor receipt, final
admission evidence, merge receipt or release plan. Its domain is
`laconian-postmerge-admission-subject-v1\n`, omitting only its final digest.

The broader ruleset-read credential has its own closed caller and token lifecycle.
`SecurityAttestorCallerPolicyRowV1` has exactly `schema_version`, `campaign_registry_sha256`,
`repository_id`, `attestation_purpose="preflight_rulesets"|"postmerge_rule_suite"|
"release_preparation"`, `caller_workflow_path`, `caller_workflow_ref`,
`caller_workflow_sha256`, `callee_workflow_path`, `callee_workflow_ref`,
`callee_workflow_sha256`, `caller_job="security_attestor"`,
`oidc_audience="laconian-security-attestor-broker"`, `protected_environment`,
`allowed_event_name`, `required_ref_class`, `protocol_phase="observing"`, ordered
`requested_permissions=["administration:write","contents:read","metadata:read"]`, ordered
`get_endpoint_templates`, `token_mint_endpoint_template`, `token_delete_endpoint_template`,
`denial_probe_endpoint_template`, and `policy_row_sha256`. Caller/callee path, immutable refs and
blob SHAs equal the common workflow-root inventory; environment/event/ref are the exact
purpose-specific protected trigger. Its domain is
`laconian-security-attestor-policy-row-v1\n`, omitting only its final digest.

`SecurityAttestorCallerPolicyV1` has exactly `schema_version`, `campaign_registry_sha256`,
`repository_id`, `app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`broker_token_delivery_isolation_policy_sha256`, ordered
`requested_permissions=["administration:write","contents:read","metadata:read"]`, ordered
`allowed_rows: SecurityAttestorCallerPolicyRowV1`, ordered
`monotonic_phases=["observing","sealed"]`, `maximum_token_ttl_seconds=3600`, positive
`clock_and_transport_skew_margin_seconds`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="security_attestor")`,
`installation_token_enters_actions=false`, and
`security_attestor_caller_policy_sha256`. The three rows are literal: `preflight_rulesets` is called only by frozen
`benchmark-preflight.yml` on the exact campaign input tag and may GET repository rulesets,
ruleset-by-ID and applicable branch/tag rules; `postmerge_rule_suite` is called only by frozen
`benchmark-publish.yml` on protected current main and may GET repository rulesets, rule-suite lists
and rule-suite-by-ID; `release_preparation` is called only by frozen `benchmark-release.yml` on
protected current main and may GET repository rulesets, rule-suite-by-ID and
`/repos/{owner}/{repo}/immutable-releases`. Every concrete endpoint is substituted only from sealed
repository/ref/ruleset/suite identity. Token mint, revoke and denial-probe endpoints are fixed
broker internals; every other method and all non-GET repository endpoints are denied. Its domain is
`laconian-security-attestor-caller-policy-v1\n`, omitting only its final digest.
Every caller authorization receipt selects one indivisible row and byte-equals its caller/callee
workflow, OIDC audience, environment, event, ref, phase, permissions and endpoints. The policy App,
broker signing key and isolation measurement equal the sealed registry role members. Token TTL and
dispatch-before-expiry checks use the common broker inequality and this policy's exact bound/skew.
The broker serializes exactly one ledger per deterministic operation key below. Entering `sealed`
irrevocably denies every later token request or GET for that key; a retry is another credential
attempt inside the same observing-phase ledger, never a second invocation ledger.

For every purpose, `operation_idempotency_key` is exactly
`SHA256(UTF8("laconian-security-attestor-operation-v1\n") || CanonicalJSONV1({campaign_id,
campaign_registry_sha256,repository_id,attestation_purpose,intent_kind,publication_id,
publication_attempt,correction_id,correction_intent_sha256,preauthorized_release_plan_sha256,
postmerge_admission_subject_sha256,admitted_merge_receipt_sha256}))`, using the purpose matrix's
exact nullability. No workflow run ID,
retry ordinal, observation time or caller-selected nonce enters this preimage.

`SecurityAttestorTokenClosureReceiptV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `repository_id`, `attestation_purpose`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`,
`broker_role="security_attestor"`,
`app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`security_attestor_caller_policy_sha256`, `token_request_receipt_sha256`, ordered
`requested_permissions`, ordered `returned_permissions`, `token_fingerprint_sha256`,
`token_vault_committed_at`, `token_expires_at`,
`outcome="revoked_204"|"ambiguous_delivery_then_confirmed_unusable"|
"expired_then_confirmed_unusable"`, ordered nested exact
`delete_attempts: BrokerTokenDeleteAttemptV1`, `closure_boundary_at`, ordered nested exact
`denial_probe_attempts: BrokerTokenDenialProbeV1`,
`post_boundary_same_token_operation_dispatch_count=0`, `vault_audit_predecessor_entry_sha256`, `closed_at`,
and `closure_receipt_sha256`. It obeys the exact common serialized delete/probe and outcome/boundary
matrix with the security-attestor role, release-finalizer App identity and attestor policy. Identity,
repository, purpose/key/ordinal, policy, permissions, fingerprint, vault-commit and expiry byte-equal
the enclosing attestor disposition; its request digest equals that disposition's nested successful
request transport. Closure time is not after the enclosing pass/failure record's `observed_at`. Its domain is
`laconian-security-attestor-token-closure-receipt-v1\n`, omitting only its final digest.

`SecurityAttestorCredentialSubjectV1` is the cycle-free post-mint/pre-GET authorization object. It
has exactly `schema_version`, nested exact
`scope_identity: BrokerVaultScopeIdentityV1(scope_kind="security_attestation")`,
`scope_identity_sha256`, the same invocation identity, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, `security_attestor_caller_policy_sha256`,
`authorized_policy_row_sha256`, `app_identity: GitHubAppInstallationIdentityV1(
role="release_finalizer")`, `token_request_receipt_sha256`, ordered `requested_permissions`,
identical `returned_permissions`, `token_fingerprint_sha256`, `token_vault_committed_at`,
`token_expires_at`, and `security_attestor_credential_subject_sha256`. Its domain is
`laconian-security-attestor-credential-subject-v1\n`, omitting only its final digest. It contains
no GET dispatch, response, closure, ledger or audit root.

`SecurityAttestorGetDispatchReceiptV1` is appended and signed before any request bytes leave the
vault. It has exactly `schema_version`, the same invocation/operation identity, positive
`credential_attempt_ordinal`, positive gapless `request_ordinal`,
`security_attestor_credential_subject_sha256`, `authorized_policy_row_sha256`,
`method="GET"`, `endpoint_template`, `request_url`, `request_payload_sha256`, `request_id`,
`request_dispatched_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="security_attestor")`,
`broker_signature_base64url`, and `get_dispatch_receipt_sha256`. Policy, subject, method/endpoint,
request and time are immutable before send. Its signature and record domains are
`laconian-security-attestor-get-dispatch-signature-v1\n` and
`laconian-security-attestor-get-dispatch-receipt-v1\n`, omitting the signature/final digest as in
the common signed-receipt rule.

`SecurityAttestorGetTransportReceiptV1` has exactly `schema_version`, the same campaign/purpose and
nullable release identity, `repository_id`, `operation_idempotency_key`, positive
`credential_attempt_ordinal`, positive gapless `request_ordinal`,
`security_attestor_caller_policy_sha256`, `authorized_policy_row_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`token_fingerprint_sha256`, nested exact
`credential_subject: SecurityAttestorCredentialSubjectV1`,
`security_attestor_credential_subject_sha256`, nested exact
`dispatch_receipt: SecurityAttestorGetDispatchReceiptV1`, `get_dispatch_receipt_sha256`,
`method="GET"`, `endpoint_template`, `request_url`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="isolated_installation_token_handle"`, `request_id`,
`request_dispatched_at`, `transport_terminal_at`, nullable `response_completed_at`,
`outcome="read_200"|"read_404"|"response_lost"|"other_response"`, nullable positive
`response_status`, nullable `response_body_commitment_sha256`, nullable
`canonical_response_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="security_attestor")`,
`broker_signature_base64url`, and `get_transport_receipt_sha256`. The endpoint template is one exact
member of the purpose row; concrete owner/repository/ref/ruleset/suite IDs come only from sealed
identity/authority. Received responses have dispatch <= completion <= terminal, status/body
commitment nonnull and response-loss fields null; 200/404 map literally, while every other received
status is `other_response`. Canonical response is nonnull exactly for a parsed JSON response.
Body commitment is
`SHA256(UTF8("laconian-security-attestor-get-response-body-v1\n") || exact response-body bytes)`;
canonical response is SHA-256 of RFC 8785 parsed JSON. Its record domain is
`laconian-security-attestor-get-transport-receipt-v1\n`, omitting only its final digest. Ordered
subject/dispatch/terminal identities, row, request, method/endpoint, payload and dispatch time are
byte-equal. The subject's vault commit is not after dispatch and dispatch is strictly before token
expiry; response/terminal completion may occur after expiry. Terminal signature time lies in the
security-attestor signing-key validity window.
Ordered
receipts contain every request/page needed by the four observation roots; those roots and receipts
form a bijection, including prior/next pagination URLs enforced by their class-bound observation
schemas. Pass permits only the purpose matrix's expected successful statuses; any loss, other status,
missing/extra endpoint or incomplete page is failure evidence.

`SecurityAttestorNoRequestReceiptV1` has exactly `schema_version`, the same invocation identity,
`operation_idempotency_key`, positive `credential_attempt_ordinal`,
`security_attestor_caller_policy_sha256`, `authorized_policy_row_sha256`,
`reason="attestor_identity_mismatch"`, `token_request_count=0`,
`get_dispatch_count=0`, `recorded_at`, and `no_request_receipt_sha256`. Its domain is
`laconian-security-attestor-no-request-receipt-v1\n`, omitting only its final digest.

`SecurityAttestorCredentialDispositionV1` has exactly `schema_version`, the same campaign,
purpose and nullable initial/correction release identity, `repository_id`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`,
`security_attestor_caller_policy_sha256`, `authorized_policy_row_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`credential_status="no_request"|"mint_denied_no_dispatch"|"minted_then_closed"|
"minted_permission_mismatch_then_closed_no_dispatch"|
"mint_delivery_unknown_unrecoverable_no_dispatch"`, ordered `requested_permissions`, ordered
`returned_permissions`, nullable `token_request_receipt_sha256`, nullable nested exact
`token_request_transport_receipt: BrokerTokenRequestTransportReceiptV1`, nullable nested exact
`no_request_receipt: SecurityAttestorNoRequestReceiptV1`, nullable nested exact
`token_unrecoverability_receipt: BrokerTokenUnrecoverabilityReceiptV1`, nullable
`credential_subject: SecurityAttestorCredentialSubjectV1`, nullable
`security_attestor_credential_subject_sha256`, nullable
`token_fingerprint_sha256`, nullable `token_vault_committed_at`, nullable `token_expires_at`, ordered
`get_request_receipts: SecurityAttestorGetTransportReceiptV1`, nullable nested exact
`token_closure: SecurityAttestorTokenClosureReceiptV1`, `recorded_at`, and
`credential_disposition_sha256`. Its five statuses obey the same exact request outcome,
permission, retry-ordinal, unrecoverability and closure nullability matrix as the release-finalizer
disposition. No-request has a nonnull exact no-request receipt and all request/subject/token fields null;
every other status has that receipt null. No-request, denial, mismatch and unknown have null
credential subjects and zero GET dispatches; a valid minted member has the unique nonnull exact
subject/digest, contains the purpose row's complete GET receipt sequence and closes its token after
the last GET. Request digest/transport, role/App/policy, ordinal, fingerprint, vault time and closure are
byte-equal throughout; disposition, token-request transport, subject and every GET/no-request receipt repeat
the one purpose row digest. Its domain is
`laconian-security-attestor-credential-disposition-v1\n`, omitting only its final digest.

`SecurityAttestorBrokerLedgerEntryV1` has exactly `schema_version`, positive gapless
`entry_ordinal`, nullable `predecessor_entry_sha256`, nullable `attestation_purpose`, nullable
`operation_idempotency_key`, nullable positive `credential_attempt_ordinal`,
`entry_kind="phase_transition"|"no_request"|"token_request_started"|
"token_request_terminal"|"token_issued"|"operation_dispatch_started"|
"operation_dispatch_terminal"|"token_closed"|
"token_unrecoverable"`, `phase_before="observing"|"sealed"`,
`phase_after="observing"|"sealed"`, nullable
`request_terminal_outcome="definite_denial"|"successful_response"|"delivery_unknown"`, nullable
`response_status`, nullable `token_fingerprint_sha256`, nullable
`request_or_transport_receipt_sha256`, `occurred_at`, and `entry_sha256`. Entries are hash-chained,
nondecreasing in time and same-phase except the unique final `observing -> sealed` transition.
No-request has one no-request entry naming its exact `SecurityAttestorNoRequestReceiptV1`. Denial
has request-started/terminal; valid or mismatched mint
adds token-issued, adjacent start/terminal pairs in bijection with every GET (zero for mismatch), then token-closed naming
the full closure digest; unknown adds terminal/token-unrecoverable. Request terminal outcome/status
and all other kind nullability are the shared publisher matrix. An operation start names the exact
`SecurityAttestorGetDispatchReceiptV1` and occurs at `request_dispatched_at`; its unique terminal
names the matching `SecurityAttestorGetTransportReceiptV1` and occurs at `transport_terminal_at`.
Both carry the same token fingerprint; no terminal may lack or reuse a start. Its domain is
`laconian-security-attestor-broker-ledger-entry-v1\n`, omitting only its
final digest.

`SecurityAttestorBrokerLedgerV1` has exactly `schema_version`, the same invocation identity,
`security_attestor_caller_policy_sha256`, ordered nested exact `entries`, `final_phase="sealed"`,
`outstanding_token_request_count=0`, `outstanding_dispatch_count=0`, `live_token_count=0`, nested
exact `broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="security_attestor")`,
`broker_signature_base64url`, `observed_at`, and `ledger_root_sha256`. Signature preimage is
`UTF8("laconian-security-attestor-broker-ledger-signature-v1\n") || CanonicalJSONV1(record without
exactly broker_signature_base64url and ledger_root_sha256)`; the record domain is
`laconian-security-attestor-broker-ledger-v1\n`, omitting only its final root. Every disposition
key has exactly its class-bound entry sequence; every issued fingerprint closes once, every GET is
inventoried by one start/terminal pair, and the final transition occurs immediately after the
selected class-terminal entry only when replayed outstanding request/dispatch counts are zero:
no-request, definite-denial terminal, token-closed, or token-unrecoverable.

`SecurityAttestorCredentialDispositionSetV1` has exactly `schema_version`, the same invocation
identity, `security_attestor_caller_policy_sha256`, ordered nested exact
`dispositions: SecurityAttestorCredentialDispositionV1`,
`selected_credential_disposition_sha256`, nested exact
`final_broker_ledger: SecurityAttestorBrokerLedgerV1`,
`final_broker_ledger_root_sha256`, nested exact
`broker_vault_audit_log: BrokerVaultAuditLogV1(scope_kind="security_attestation",
broker_role="security_attestor")`, `vault_audit_log_root_sha256`,
`final_phase="sealed"`, `outstanding_token_request_count=0`,
`outstanding_dispatch_count=0`, `live_token_count=0`, `observed_at`, and
`credential_disposition_set_sha256`. Dispositions contain every gapless credential-attempt ordinal;
denied/mismatched/unknown retries remain present. The selected digest names the unique maximum-
ordinal terminal member whose exact status and evidence feed this pass/failure: valid closed GET
for pass or observational failure, permission-mismatch closure for that post-mint failure, or
no-request/denial/unrecoverability for pre-mint failure. Final roots recompute from the nested signed
ledger and signed vault log. Their scope, App, policy, signing identities, request/dispatch pairs,
closures/unrecoverability events and zero counters form an exact bijection; `observed_at` equals the
ledger seal and audit-log `sealed_at`. Its
domain is `laconian-security-attestor-credential-disposition-set-v1\n`, omitting only its final
digest.
The set is the broker's complete prefix for that deterministic operation key through its unique
sealed transition; a second ledger/root or a later mint for the key is invalid.

`SecurityAttestorReceiptV1` is pass-only and has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `attestation_purpose="preflight_rulesets"|
"postmerge_rule_suite"|"release_preparation"`, nullable `intent_kind`, nullable `publication_id`,
nullable `publication_attempt`, nullable `correction_id`, nullable
`correction_intent_sha256`, nullable `preauthorized_release_plan_sha256`, nullable
`postmerge_admission_subject_sha256`, nullable
`admitted_merge_receipt_sha256`,
`security_policy_sha256`, `security_attestor_caller_policy_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`, ordered exact
`requested_permissions=["administration:write","contents:read","metadata:read"]`, identical
`returned_permissions`, `endpoint_policy_sha256`, `token_request_receipt_sha256`,
`token_request_transport_receipt: BrokerTokenRequestTransportReceiptV1(outcome="successful_201")`,
`token_fingerprint_sha256`, `token_vault_committed_at`, `token_expires_at`, ordered
`get_request_receipt_sha256s`, nullable `tag_ruleset_observation_root_sha256`, nullable
`publication_branch_ruleset_observation_root_sha256`, nullable
`rule_suite_observation_root_sha256`, nullable `immutable_release_setting_observation_sha256`,
`result="pass"`, `failed_predicates=[]`, nested exact
`token_closure: SecurityAttestorTokenClosureReceiptV1`,
`selected_credential_disposition_sha256`, nested exact
`credential_disposition_set: SecurityAttestorCredentialDispositionSetV1`, `observed_at`, and
`security_attestor_receipt_sha256`.

The purpose matrix is exact. `preflight_rulesets` has every publication/release identity and merge/
plan/subject field null, nonnull tag and publication-ruleset roots, and null rule-suite/immutable roots.
`postmerge_rule_suite` has initial/correction XOR identity and a nonnull exact cycle-free postmerge
subject, but null admitted merge receipt and preauthorized plan; it has nonnull publication-ruleset
and rule-suite roots and null tag/immutable roots.
`release_preparation` has the same XOR identity, the byte-equal postmerge subject, nonnull
preauthorized plan and admitted merge receipt,
nonnull tag/publication/rule-suite/immutable roots, and every root equal to reconstructed authority.
`correction_intent_sha256` is null for preflight and initial identity and equals the active immutable
`CorrectionIntentV1` for either correction purpose.
The nested closure repeats the outer token identity exactly and is completed before candidate
construction. The selected disposition is the set's unique selected member; every duplicated
request/token/closure field and digest byte-equals it, and outer `get_request_receipt_sha256s` is
the ordered projection of its nested GET receipts' recomputed digests. Set observation time equals the pass
record's `observed_at`. The external broker, not an Actions step, mints the token, performs only its purpose's
GET allowlist, closes the token, and returns safe receipts; no token/header enters Actions. Its
domain is `laconian-security-attestor-receipt-v1\n`, omitting only its final digest. Every executable
release authorization names a `release_preparation` pass record.

Failure is a different class, so a denied mint needs no fictional token.
`SecurityAttestorFailureEvidenceV1` has exactly `schema_version`, the same common campaign,
purpose and nullable release identity/plan/postmerge-subject/merge fields,
`failure_stage="pre_mint"|"post_mint"`,
`security_policy_sha256`, `security_attestor_caller_policy_sha256`, nullable `observed_app_identity`,
ordered `requested_permissions`, ordered `returned_permissions`, `endpoint_policy_sha256`, nullable
`pre_mint_outcome="no_request"|"definite_denial"|"delivery_unknown_unrecoverable"`, nullable
`token_request_receipt_sha256`, nullable nested exact
`token_request_transport_receipt: BrokerTokenRequestTransportReceiptV1`, nullable nested exact
`token_unrecoverability_receipt: BrokerTokenUnrecoverabilityReceiptV1`, nullable
`token_fingerprint_sha256`, nullable `token_vault_committed_at`,
nullable `token_expires_at`, ordered `get_request_receipt_sha256s`, the same four nullable
observation roots, nonempty ordered `failed_predicates`, nullable nested exact
`token_closure: SecurityAttestorTokenClosureReceiptV1`,
`selected_credential_disposition_sha256`, nested exact
`credential_disposition_set: SecurityAttestorCredentialDispositionSetV1`,
`denial_or_transport_receipts_root_sha256`,
`observed_at`, and `security_attestor_failure_evidence_sha256`. `pre_mint` permits only
`attestor_identity_mismatch|token_request_denied|token_request_delivery_unknown_unrecoverable`, has
empty returned permissions/GET receipts and null token, closure and observation fields. Identity
mismatch selects `no_request`, empty requested permissions and null request/unrecoverability.
Denial selects `definite_denial`, exact requested permissions and exact nested denial request
transport/digest, and null
unrecoverability. Delivery unknown selects `delivery_unknown_unrecoverable`, exact requested
permissions and exact nested unknown transport/digest, plus an exact security-attestor-role unrecoverability receipt with
zero GET/operation dispatch. `post_mint` has null pre-mint outcome/unrecoverability and requires the complete token/closure tuple
and permits the remaining permission/repository/ruleset/suite/immutable/missing-observation
predicates in canonical order. Pre-mint failure selects its maximum-ordinal terminal
no-request/denied/unknown disposition; post-mint failure selects the valid closed GET or
permission-mismatch-and-closed disposition that feeds its predicates. The set/ledger counts and
observation time byte-equal the failure record; its outer GET hash array is the ordered digest
projection of the selected disposition's nested GET receipts (empty for no-GET failure).
Its domain is `laconian-security-attestor-failure-evidence-v1\n`,
omitting only its final digest. It cannot enter an executable plan or effect authorization.

`ReleaseEffectResultV1` admits only this literal effect/method/endpoint/status/operation matrix;
`{owner}`, `{repo}`, IDs, names, and query parameters are substituted only from exact authority:

| `effect_kind` | Semantic branch | `api_method` | Exact `endpoint_template` | `response_status` | `operation` |
|---|---|---|---|---:|---|
| `tag_object` | create | `POST` | `/repos/{owner}/{repo}/git/tags` | `201` | `created` |
| `tag_object` | adopt | `GET` | `/repos/{owner}/{repo}/git/tags/{tag_object_sha}` | `200` | `adopted` |
| `tag_ref` | create | `POST` | `/repos/{owner}/{repo}/git/refs` | `201` | `created` |
| `tag_ref` | adopt | `GET` | `/repos/{owner}/{repo}/git/ref/tags/{tag_name}` | `200` | `adopted` |
| `draft_release` | create | `POST` | `/repos/{owner}/{repo}/releases` | `201` | `created` |
| `draft_release` | adopt | `GET` | `/repos/{owner}/{repo}/releases/{release_id}` | `200` | `adopted` |
| `asset` | upload | `POST` | `/repos/{owner}/{repo}/releases/{release_id}/assets{?name,label}` | `201` | `uploaded` |
| `asset` | adopt | `GET` | `/repos/{owner}/{repo}/releases/assets/{asset_id}` | `200` | `adopted` |
| `publish` | publish | `PATCH` | `/repos/{owner}/{repo}/releases/{release_id}` | `200` | `published` |
| `publish` | adopt published | `GET` | `/repos/{owner}/{repo}/releases/{release_id}` | `200` | `adopted` |
| `final_verification` | verify | `GET` | `/repos/{owner}/{repo}/releases/{release_id}` | `200` | `verified` |

For tag-object, tag-ref, draft-release, and publish POST/PATCH rows,
`request_payload_sha256` hashes the exact RFC 8785 canonical JSON request body authorized by the
intent. For asset upload it instead hashes the exact raw uploaded bytes and equals the intent-bound
asset SHA-256; the observation additionally binds exact `Content-Type`, query `name`, and optional
`label`. For GET it is the lowercase SHA-256 of zero bytes and no request body is sent. The request-
receipt root includes every prerequisite/list/pagination call in protocol order, while the row is
the one terminal create/adopt/verify observation. Raw and canonical response hashes bind that same
status/object. Timeout, 202, 204, 3xx, alternate endpoint, by-tag draft lookup, cross-kind operation,
or an adopted object observed only through a write response is not a valid effect result.

The four receipt payloads have these exact ordered fields and types:

```text
TagReceiptV1
  schema_version = "TagReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  authorization: ReleaseEffectAuthorizationV1
  annotated_tag_effect_results: AnnotatedTagEffectResultsV1
  tag_object_delivery_resolution_sha256: lowercase SHA-256
  tag_ref_delivery_resolution_sha256: lowercase SHA-256
  tag_name: bounded nonblank string
  tag_object_sha: lowercase 40-hex Git OID
  target_commit_sha: lowercase 40-hex Git OID
  actor: GitHubAppInstallationIdentityV1(role="release_finalizer")
  request_receipts_root: lowercase SHA-256
  installation_token_revocation: InstallationTokenRevocationReceiptV1(effect_kind="tag")
  receipt_sha256: lowercase SHA-256

DraftReleaseReceiptV1
  schema_version = "DraftReleaseReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  authorization: ReleaseEffectAuthorizationV1
  effect_result: ReleaseEffectResultV1(effect_kind="draft_release")
  effect_delivery_resolution_sha256: lowercase SHA-256
  operation: "created" | "adopted"
  release_id: positive canonical integer
  release_name: bounded nonblank string
  release_body_sha256: lowercase SHA-256
  marker: bounded nonblank string
  draft = true
  actor: GitHubAppInstallationIdentityV1(role="release_finalizer")
  request_receipts_root: lowercase SHA-256
  installation_token_revocation: InstallationTokenRevocationReceiptV1(effect_kind="draft_release")
  receipt_sha256: lowercase SHA-256

ReleaseAssetReceiptV1
  schema_version = "ReleaseAssetReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  authorization: ReleaseEffectAuthorizationV1
  effect_result: ReleaseEffectResultV1(effect_kind="asset")
  effect_delivery_resolution_sha256: lowercase SHA-256
  asset_ordinal: 0 | 1
  operation: "uploaded" | "adopted"
  release_id: positive canonical integer
  asset_id: positive canonical integer
  name: bounded nonblank string
  byte_length: nonnegative canonical integer
  sha256: lowercase SHA-256
  actor: GitHubAppInstallationIdentityV1(role="release_finalizer")
  request_receipts_root: lowercase SHA-256
  installation_token_revocation: InstallationTokenRevocationReceiptV1(effect_kind="asset")
  receipt_sha256: lowercase SHA-256

PublishReceiptV1
  schema_version = "PublishReceiptV1"
  campaign_id: bounded nonblank string
  campaign_registry_sha256: lowercase SHA-256
  publication_id: bounded nonblank string
  authorization: ReleaseEffectAuthorizationV1
  effect_result: ReleaseEffectResultV1(effect_kind="publish")
  effect_delivery_resolution_sha256: lowercase SHA-256
  operation: "published" | "adopted_published"
  release_id: positive canonical integer
  draft_before = true
  draft_after = false
  actor: GitHubAppInstallationIdentityV1(role="release_finalizer")
  request_receipts_root: lowercase SHA-256
  installation_token_revocation: InstallationTokenRevocationReceiptV1(effect_kind="publish")
  receipt_sha256: lowercase SHA-256
```

Each payload uses the domain in the table above and canonical JSON omitting only
`receipt_sha256`. For a tag, its authorization is byte-identical to both nested effect-result
authorizations; for every other payload it is byte-identical to `effect_result.authorization`.
Every success receipt binds the complete exact-success delivery resolution for its nested effect
result. Tag binds two roots in object/ref order; each resolution's embedded effect result is
byte-identical to the corresponding aggregate result. Draft, each asset, publish and final
verification bind one same-step resolution whose embedded result byte-equals the receipt. A lost
response, retry or adoption path therefore cannot disappear from a success receipt.
Actor, campaign, registry, publication, intent, plan roots, security-attestor root, object identity,
idempotency key, and revocation bindings revalidate against authority. Outer and effect operations
map exactly: draft `created|adopted`, asset `uploaded|adopted`, and publish
`published -> published` or `adopted_published -> adopted`. The two asset payloads are ordered
strictly by ordinal `[0,1]`, share the one release ID and authorization, have distinct asset IDs and
names, and equal the two intent-bound sizes/digests. Extra, omitted, flattened, cross-effect, or
cross-publication fields fail canonical validation.
For draft, either asset, publish, and final verification, the outer `request_receipts_root`
byte-equals the nested effect result's root. For a tag it equals the deterministic ordered Merkle
root of the tag-object then tag-ref effect request-receipt roots, with domain
`laconian-annotated-tag-request-receipts-root-v1\n`. No outer root is independently selectable.

The tag aggregate is always ordered object then ref. Its distinct step keys are
`SHA256(UTF8("laconian-release-tag-effect-step-idempotency-v1\n") ||
CanonicalJSONV1({tag_effect_idempotency_key,step_ordinal,effect_kind}))` for exactly
`(0,"tag_object")` then `(1,"tag_ref")`. The object result binds the exact intent-authorized
annotated-tag bytes, OID, name, tagger, message and target; the ref result binds
`refs/tags/{tag_name}` to exactly that tag-object OID. The four exact operation pairs
`created/created`, `created/adopted`, `adopted/created`, and `adopted/adopted` are valid, always in
that order; a lightweight ref to the target commit is rejected. Receipt-level token revocation
retains `effect_kind="tag"`, uses `subject_kind=complete_effect_result`, and its subject root equals
the aggregate root. Every other success receipt likewise uses `complete_effect_result`; an
aggregate partial uses `partial_effect_prefix`, and a minted token whose step ends rejected or
conflicting uses `failed_delivery_resolution`. The revocation subject never hashes the revocation
receipt, and every minted token maps to exactly one such subject in no-later evidence. If the
object succeeds but the ref cannot be reconciled exactly, no `TagReceiptV1` exists; release
invalidation uses the exact partial-effect detail and inventories the orphan object.

These shared payload types and append wrappers are normative exact wire records. Runtime owns their
single implementation but cannot alter this schema. The sole
`<publication-id>` path component and `<20-digit-publication-attempt>` component byte-equal the
authoritative publication plan, release intent and append wrapper; every nested payload binds the
same attempt through its byte-identical authorizing intent and plan roots. A plan ID, unpadded
attempt, directory alias, or normalized substitute is forbidden.

Only `benchmark-release.yml` on the protected plan-bound main ref may request this family, and only
while canonical authority is `RESULT_MERGED`, its exact initial `release-intent.json` is current,
and both the unresolved-hold and active-exposure roots are null. The only admitted sequence is
`tag-receipt.json` -> `draft-release-receipt.json` -> one ordered two-member
`asset-receipts.json` -> `publish-receipt.json`; tag has null predecessor, every later append names
the immediately prior append digest, and each nested payload revalidates the same campaign,
registry, publication, intent, two release-plan roots, security-attestor receipt, actor, object,
and effect authorization. The append's `authority_parent_oid`, request
`expected_current_oid`, and reconstructed current authority OID are identical; its
`append_idempotency_key`, the outer request idempotency key, and the corresponding intent-authorized
receipt-CAS key are identical; and both state hash fields equal the one current
`campaign-state.json` digest. Each append uses one
expected-old-OID fast-forward CAS, retains
`campaign-state.json`, its digest, state name, transition number, hold root, active-exposure pair,
and every other tree member byte-for-byte, appends exactly the one next absent file, and creates no
event file. Missing, duplicate, reordered, correction, invalid-prefix, arbitrary-path, or generic
same-state appends are forbidden. `RESULT_RELEASED` requires all four accepted appends and their
exact nested receipts; it cannot manufacture or batch an omitted predecessor receipt.

`HeldResultMergedConsumptionV1` has exactly
`schema_version="HeldResultMergedConsumptionV1"`, `kind="nondismissible"`, `campaign_id`,
`campaign_registry_sha256`, `parent_state="RESULT_MERGED"`, `parent_authority_oid`, `hold_id`,
`hold_root_sha256`, `hold_admission_event_sha256`, `nondismissibility_evidence_sha256`, and
`consumption_sha256`. Every hold identity equals the one current accepted hold and the evidence
proves its closed nondismissible defect; no future event or successor OID is present. Its domain is
`laconian-held-result-merged-consumption-v1\n`, omitting only `consumption_sha256`.

`ReleasePreparationEvidenceV1` is the exact pre-intent subject. Its ordered fields are
`schema_version="ReleasePreparationEvidenceV1"`, `campaign_id`, `campaign_registry_sha256`,
`publication_id`, positive `publication_attempt`, `publication_plan_sha256`,
`publication_merge_receipt_sha256`, `sealed_bundle_root_sha256`,
`expected_result_tree_sha256`, `expected_provenance_root_sha256`, nullable
`candidate_preauthorized_release_plan_sha256`, nullable
`candidate_security_attestation_kind="pass"|"failure"`, nullable nested exact
`candidate_security_attestation_evidence`, nullable
`candidate_security_attestation_evidence_sha256`, nullable
`candidate_executable_release_plan_sha256`,
`preparation_receipts_root_sha256`, and `release_preparation_evidence_sha256`. The two candidate
plan fields and attestation union are exact class-bound attempted objects when nonnull; any
attestation requires a nonnull preauthorized plan. `pass` embeds `SecurityAttestorReceiptV1`;
`failure` embeds `SecurityAttestorFailureEvidenceV1`; its duplicated digest is the selected member's
final digest. Campaign, registry, publication, attempt, publication plan, bundle, merge
receipt, expected result tree and provenance roots byte-equal the enclosing invalidation and current
accepted `RESULT_MERGED` authority. At any post-intent phase the candidate preauthorized/executable
plans and `pass` attestor are nonnull and equal the three top-level authority roots. At pre-intent,
security-attestation failure requires a candidate preauthorized plan and exact nonnull `failure`
evidence but null candidate executable plan and null top-level successful-attestor/executable roots;
external-object conflict requires a valid preauthorized plan, `pass` receipt and executable plan;
verified
tree/bundle/provenance failure may have both null or a valid pair according to the recorded
preparation order. The record contains no intent, effect, terminal event, or successor OID. Its domain is
`laconian-release-preparation-evidence-v1\n`, omitting only its final digest.

`ReleasePlanInvalidationEvidenceV1` is the strict class-bound evidence for initial
`RELEASE_PLAN_INVALIDATED`. It has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `publication_id`, positive `publication_attempt`,
`publication_plan_sha256`, `sealed_bundle_root_sha256`, nested exact `release_preparation`, nullable
`preauthorized_release_plan_sha256`, nullable `executable_release_plan_sha256`, nullable
`security_attestor_receipt_sha256`, `authority_parent_oid`, `release_phase`, `reason`, nullable
`release_intent_sha256`, nullable `tag_receipt_append_sha256`, nullable
`draft_release_receipt_append_sha256`, nullable `asset_receipts_append_sha256`, nullable
`publish_receipt_append_sha256`, nullable `current_external_objects_root_sha256`, nested exact
`detail`, nullable nested exact
`release_finalizer_operation_set: ReleaseFinalizerOperationSetV1`, nullable
`release_finalizer_operation_set_sha256`, nullable nested exact
`release_reconciliation_unavailable_receipt: ReleaseReconciliationUnavailableReceiptV1`, nullable
`release_reconciliation_unavailable_receipt_sha256`, nullable `no_later_effects_root_sha256`,
`recorded_at`, and
`release_plan_invalidation_evidence_sha256`.

`ReleasePlanInvalidationDetailV1` is a closed `detail_kind` discriminator union; `detail_kind`
equals top-level `reason`, and each member has exactly the remaining fields listed here:

| `detail_kind` | Exact remaining fields |
|---|---|
| `verified_tree_mismatch` | `expected_tree_oid`, nullable `observed_tree_oid`, `expected_result_tree_sha256`, nullable `observed_result_tree_sha256`, `verification_receipts_root_sha256` |
| `bundle_mismatch` | `expected_bundle_root_sha256`, nullable `observed_bundle_root_sha256`, `expected_inventory_root_sha256`, nullable `observed_inventory_root_sha256`, `verification_receipts_root_sha256` |
| `security_attestation_failure` | `expected_security_policy_sha256`, nullable `observed_security_policy_sha256`, nonempty canonical ordered `failed_predicates`, `security_attestor_failure_evidence_sha256`, `security_observation_receipts_root_sha256` |
| `provenance_failure` | `expected_provenance_root_sha256`, nullable `observed_provenance_root_sha256`, `verification_receipts_root_sha256` |
| `external_object_conflict` | `effect_kind`, `effect_step_kind`, nonnegative `effect_step_ordinal`, `object_kind`, `expected_object_root_sha256`, nullable `observed_object_id`, nullable `observed_object_root_sha256`, `delivery_state`, `effect_delivery_resolution_sha256`, nullable `partial_effect_root_sha256`, `observation_receipts_root_sha256`, nullable `installation_token_revocation_receipt_sha256` |
| `immutable_release_verification_failure` | `publish_receipt_append_sha256`, `final_verification_effect_delivery_resolution_sha256`, `expected_final_external_objects_root_sha256`, `observed_final_external_objects_root_sha256`, nonempty canonical ordered `failed_predicates`, `verification_receipts_root_sha256` |
| `credential_exposure` | nested exact `terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1` |
| `protocol_authority_drift` | nested exact `protocol_authority_drift_evidence: ProtocolAuthorityDriftEvidenceV1` |
| `invalid_event_nondismissible` | nested exact `held_result_merged_consumption: HeldResultMergedConsumptionV1` |
| `release_reconciliation_unavailable` | `release_finalizer_operation_set_sha256`, `release_reconciliation_unavailable_receipt_sha256` |

The security predicate order is exactly `attestor_identity_mismatch`, `token_request_denied`,
`token_request_delivery_unknown_unrecoverable`,
`returned_permissions_mismatch`, `repository_identity_mismatch`,
`result_tag_ruleset_mismatch`, `publication_branch_ruleset_mismatch`, `rule_suite_mismatch`,
`immutable_releases_not_enabled`,
`authenticated_observation_missing_or_invalid`. The immutable-verification order is exactly
`release_not_published`, `release_not_immutable`, `tag_identity_mismatch`, `asset_set_mismatch`,
`asset_digest_mismatch`, `actor_mismatch`, `verification_tool_mismatch`,
`verification_delivery_unresolved`. External-object `effect_kind` is `tag`, `draft_release`,
`asset`, or `publish`; `effect_step_kind` is `tag_object`, `tag_ref`, `draft_release`, `asset`, or
`publish`; `object_kind` is `tag_object`, `tag_ref`, `draft_release`, `asset`, or
`published_release`; and `delivery_state` is `preexisting_conflict`, `write_rejected`,
`pre_dispatch_local_rejection`, `ambiguous_then_conflict`, or `partial_effect`. A nullable observed root/OID is legal only with an
authenticated absence/inconsistency receipt in the member's exact receipt root. Fields from any
other member are forbidden.

The external-conflict tuple is literal, not a cross-product: exactly
`(tag,tag_object,0,tag_object)`, `(tag,tag_ref,1,tag_ref)`,
`(draft_release,draft_release,0,draft_release)`, `(asset,asset,0|1,asset)`, or
`(publish,publish,0,published_release)`. `partial_effect` is legal only for tag-ref after an exact
tag-object result or for an enumerated asset ordinal after the prior ordered release steps; its
object inventory retains every orphan. The token-revocation receipt is null exactly for a
credentialless preexisting conflict or pre-dispatch local rejection whose class-bound ledger proves
no mint and no dispatch. It is nonnull for `write_rejected`, `ambiguous_then_conflict`, or
`partial_effect`, is bound to the exact failed effect authorization/result prefix, and also appears
in the no-later-effects evidence.
The separate immutable-verification observation additionally admits exactly
`(final_verification,final_verification,0,published_release)` with authenticated GET-by-release-ID
semantics; it is not an `external_object_conflict` detail tuple.
Every external-conflict member's delivery-resolution digest names the exact tuple/identity and its
two stable observations; the member's observed ID/root and observation-receipt root derive from the
second observation. `partial_effect_root_sha256` is nonnull exactly for `partial_effect` and names
`PartialAnnotatedTagEffectV1` for tag-ref or `PartialAssetEffectsV1` for asset. In those rows the
revocation uses `subject_kind=partial_effect_prefix`; a minted rejected/conflicting single step uses
`failed_delivery_resolution`. Credentialless preexisting/local rejection uses a not-dispatched
resolution plus exact release-finalizer no-request receipt and null revocation. In every case
invalidation `recorded_at` equals the enclosing `ReleaseNoLaterEffectsEvidenceV1.observed_at`, the
final broker sealed/closure time not before the second reconciliation read; the earlier failed-step observation time remains
bound by its delivery-resolution digest and is not required to equal final reconciliation.
The sole exception is `reason=release_reconciliation_unavailable`: its nested operation set has
`finality_status=reconciliation_unavailable_sealed`, its nested failure receipt/digests byte-equal
that set, `current_external_objects_root_sha256` and `no_later_effects_root_sha256` are null, and
every other reason-specific/emergency field is null. It preserves all completed effect resolutions
but claims no complete external state or release success. `recorded_at` equals the failure receipt,
operation-set, release-ledger and vault-audit sealed time. Every other reason requires a nonnull
current external-object root and stable no-later proof and has both unavailable objects null.

`ReleaseDiscoveryMatchProjectionV1` has exactly `object_id`, `object_root_sha256`, `name`, nullable
`release_id`, nullable `actor_id`, `actor_login`, `source_page_ordinal`,
`raw_response_sha256`, and `canonical_response_sha256`. `ReleaseDiscoveryPageReceiptV1` has exactly
`schema_version`, `query_template`, positive gapless `page_ordinal`, `response_status=200`, ordered
`objects: ReleaseDiscoveryMatchProjectionV1`, nullable `previous_link`, nullable `next_link`,
`raw_response_sha256`, `canonical_response_sha256`, `authenticated_at`, and
`page_receipt_sha256`. Links chain exactly from page one/null previous through final/null next; IDs
are unique and page/API ordered. Its domain is
`laconian-release-discovery-page-receipt-v1\n`, omitting only its final digest.

`ReleaseExternalObjectObservationV1` has exactly
`schema_version="ReleaseExternalObjectObservationV1"`, `campaign_id`,
`campaign_registry_sha256`, `publication_id`, nullable `publication_attempt`, nullable
`correction_id`, `release_phase`, `effect_kind`, `effect_step_kind`, `effect_step_ordinal`,
`object_kind`, `expected_object_root_sha256`, `observation_mode="direct"|
"paginated_name_discovery"`, nullable `direct_endpoint_template`, nullable
`direct_response_status`, nullable `direct_raw_response_sha256`, nullable
`direct_canonical_response_sha256`, nullable `discovery_query_template`, nullable positive
`discovery_page_count`, ordered nested exact
`discovery_pages: ReleaseDiscoveryPageReceiptV1`, ordered
`matching_objects: ReleaseDiscoveryMatchProjectionV1`, nullable `selected_object_read_endpoint`,
nullable `selected_object_read_status`, nullable `selected_object_read_raw_response_sha256`,
nullable `selected_object_read_canonical_response_sha256`, nullable `observed_object_id`, nullable
`observed_object_root_sha256`, `observed_state="absent"|"exact"|"conflicting"`,
`observation_receipts_root_sha256`, `observed_at`, and `observation_sha256`. Initial identity is
positive attempt/null correction; correction is null attempt/path-safe correction.

Direct mode is exact for tag-object by OID, tag ref by name, publish by release ID, and final
verification by release ID. Its discovery/page/match/selected fields are null or empty; absent is an
authenticated 404 with null observed identity, while exact/conflicting is 200 with one nonnull
identity/root equal/different to expected. Paginated mode is exact for draft discovery through
fully paginated `GET /repos/{owner}/{repo}/releases?per_page=100` and asset discovery through
`GET /repos/{owner}/{repo}/releases/{release_id}/assets?per_page=100`; its direct fields are null,
every page is 200, and the complete matching array is sorted by canonical object ID. Zero matches
means absent/null selected identity even though every HTTP status is 200. Exactly one match is then
fetched by `GET /repos/{owner}/{repo}/releases/{release_id}` or
`GET /repos/{owner}/{repo}/releases/assets/{asset_id}` and yields exact/conflicting by root. Two or
more matches are conflicting, preserve all members, and have null selected-read and top-level
identity/root. A missing page, broken Link chain, by-tag draft lookup, duplicate hidden by
selection, or un-fetched unique match fails closed. `observed_at` is the final authenticated page
or selected/direct read time. Its digest is
`SHA256(UTF8("laconian-release-external-object-observation-v1\n") || CanonicalJSONV1(record without
exactly observation_sha256))`.

`ReleaseExternalObjectsInventoryV1` has exactly
`schema_version="ReleaseExternalObjectsInventoryV1"`, the same full identity and `release_phase`,
ordered `observations`, nullable `empty_inventory_receipts_root_sha256`, and
`current_external_objects_root_sha256`. Observations use literal effect tuple order, then asset
ordinal, then object ID with null represented only by the absence sentinel and sorting before any
nonempty ID; duplicates are forbidden. Empty observations require a nonnull authenticated complete
absence-read root; nonempty observations require that field null. A pre-intent same-name conflict is
therefore nonempty even though authorized dispatch count is zero. Its digest is
`SHA256(UTF8("laconian-release-external-objects-inventory-v1\n") || CanonicalJSONV1(record without
exactly current_external_objects_root_sha256))`.

`ReleaseLatestPointerObservationV1` has exactly `schema_version`, the same full identity,
`latest_pointer_path`, `expected_state="absent"|"exact"`, `observed_state="absent"|"exact"`,
nullable `expected_pointer_root_sha256`, nullable `observed_pointer_root_sha256`, `api_method="GET"`,
`endpoint_template`, `response_status`, `request_receipt_sha256`, `observed_at`, and
`latest_pointer_observation_sha256`. Absent/404 uses two null roots; exact/200 uses two equal nonnull
predecessor roots. Its domain is `laconian-release-latest-pointer-observation-v1\n`, omitting only
its final digest.

`ReleaseReconciliationObservationV1` has exactly `schema_version`, the same full identity,
`authority_parent_oid`, `release_phase`, nested exact
`external_objects_inventory: ReleaseExternalObjectsInventoryV1`, nested exact
`latest_pointer_observation: ReleaseLatestPointerObservationV1`,
`canonical_release_external_state_sha256`,
`outstanding_release_write_dispatch_count=0`, `live_release_write_token_count=0`,
`broker_phase="terminal_reconciling"`, `observed_at`, and `reconciliation_observation_sha256`.
`observed_at` is the latest nested authenticated source time. Its domain is
`laconian-release-reconciliation-observation-v1\n`, omitting only its final digest.
`ReleaseReconciliationObservationSetV1` has exactly `schema_version`, the same identity, nested
exact `first_observation`, nested exact `second_observation`, `observed_at`, and
`reconciliation_observation_set_sha256`. The two observations have equal
`canonical_release_external_state_sha256`; their authenticated receipt roots are distinct and the
first time precedes the second. `observed_at` equals the second observation time. Its domain is
`laconian-release-reconciliation-observation-set-v1\n`, omitting only its final digest.

`ReleaseReconciliationTokenClosureReceiptV1` has exactly `schema_version`, the same full identity,
`authority_parent_oid`, `release_phase`, `release_finalizer_broker_policy_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`token_request_receipt_sha256`, ordered exact
`requested_permissions=["contents:read","metadata:read"]`, identical `returned_permissions`,
`token_fingerprint_sha256`, `token_vault_committed_at`, `token_expires_at`,
`reconciliation_observation_set_sha256`, nested exact
`token_closure: ReleaseFinalizerTokenClosureProjectionV1`, `closed_at`, and
`reconciliation_token_closure_receipt_sha256`. The token can call only final inventory/pointer GET
endpoints and has no write permission. Identity/times/fingerprint equal the nested closure, which
occurs after the second read. Its domain is
`laconian-release-reconciliation-token-closure-receipt-v1\n`, omitting only its final digest. It
requires no effect authorization, so pre-intent/no-plan reconciliation is constructible.

`ReleaseFinalizerCallerV1` has exactly `schema_version`, `campaign_registry_sha256`,
`repository_id`, `caller_kind="initial_release"|"correction_release"`,
`caller_workflow_path`, `caller_workflow_ref`, `caller_workflow_sha256`,
`callee_workflow_path`, `callee_workflow_ref`, `callee_workflow_sha256`,
`caller_job="release_finalizer"`, `oidc_audience="laconian-release-finalizer-broker"`,
`protected_environment`, `allowed_event_name`, `required_ref_class="protected_current_main"`, and
`release_finalizer_caller_sha256`. Workflow paths, immutable refs, blob SHAs, environment and event
equal the common workflow-root and sealed registry. Its domain is
`laconian-release-finalizer-caller-v1\n`, omitting only its final digest.

`ReleaseFinalizerOperationPolicyRowV1` has exactly `schema_version`,
`campaign_registry_sha256`, `repository_id`, nested exact
`caller: ReleaseFinalizerCallerV1`, `release_finalizer_caller_sha256`,
`release_phase="pre_intent"|"release_intent"|"tag_receipt"|"draft_release_receipt"|
"asset_receipts"|"publish_receipt"`, `operation_kind="release_effect"|
"terminal_reconciliation_read"`, `effect_kind`, `effect_step_kind`,
`effect_step_ordinal`, `method`, ordered `endpoint_templates`, ordered
`requested_permissions`, `token_mint_endpoint_template`, `token_delete_endpoint_template`,
`denial_probe_endpoint_template`, and `policy_row_sha256`. Effect tuple/nullability, method,
endpoints and permissions are exactly one row of the closed effect/read matrix; the nested caller
makes caller and operation one indivisible authorization rather than a caller×operation product.
Its domain is `laconian-release-finalizer-operation-policy-row-v1\n`, omitting only its final
digest.

`ReleaseFinalizerBrokerPolicyV1` has exactly `schema_version`, `campaign_registry_sha256`,
`repository_id`, `app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`,
`broker_token_delivery_isolation_policy_sha256`, ordered nested exact
`allowed_callers: ReleaseFinalizerCallerV1`, ordered nested exact
`operation_rows: ReleaseFinalizerOperationPolicyRowV1`, ordered
`monotonic_phases=["constructive","terminal_reconciling","sealed"]`,
`maximum_token_ttl_seconds=3600`, `maximum_reconciliation_attempts=3`,
`reconciliation_retry_schedule_seconds=[0,30,120]`, positive
`clock_and_transport_skew_margin_seconds`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="release_finalizer")`,
`installation_token_enters_general_actions_steps=false`, and
`release_finalizer_broker_policy_sha256`. Allowed callers are frozen `benchmark-release.yml` for
initial and its correction-release row on protected current main, with exact workflow/job SHAs from
the common root. Operation rows are exactly the effect tuple/method/endpoint matrix above plus one
read-only terminal-reconciliation row; write rows request only exact applicable
`contents:write|metadata:read`, and the read row requests only `contents:read|metadata:read` and the
exact GET inventory/pointer endpoints: `/git/ref/tags/{tag_name}`,
`/git/tags/{tag_oid}`, `/releases`, `/releases/{release_id}`,
`/releases/{release_id}/assets`, `/releases/assets/{asset_id}`, and
`/contents/{latest_pointer_path}`. Every row also fixes token mint, revoke and denial-probe endpoints.
Entering terminal reconciliation disables all write mints; sealed denies every later mint. Its
domain is `laconian-release-finalizer-broker-policy-v1\n`, omitting only its final digest.
Every `BrokerCallerAuthorizationReceiptV1` selects one exact operation row and its nested caller;
caller/callee workflow, OIDC audience/environment/event/ref, phase, effect tuple, permissions and
endpoints byte-equal that one row. A caller entry not nested by the row grants nothing.

`ReleaseFinalizerCredentialSubjectV1` is the cycle-free post-mint/pre-effect object. It has exactly
`schema_version`, nested exact `scope_identity: BrokerVaultScopeIdentityV1(scope_kind="release")`,
`scope_identity_sha256`, the same full release identity, `release_phase`, `effect_kind`,
`effect_step_kind`, `effect_step_ordinal`, `effect_idempotency_key`, positive
`credential_attempt_ordinal`, `release_finalizer_broker_policy_sha256`,
`authorized_policy_row_sha256`, `app_identity: GitHubAppInstallationIdentityV1(
role="release_finalizer")`, `token_request_receipt_sha256`, ordered `requested_permissions`,
identical `returned_permissions`, `token_fingerprint_sha256`, `token_vault_committed_at`,
`token_expires_at`, and `release_finalizer_credential_subject_sha256`. Its domain is
`laconian-release-finalizer-credential-subject-v1\n`, omitting only its final digest; it contains no
effect, dispatch, response, closure, ledger or audit root.

`ReleaseOperationDispatchReceiptV1` is appended and signed before send. It has exactly
`schema_version`, the same full release/effect/credential identity, positive `attempt_ordinal`,
`attempt_kind="effect_write"|"inventory_page"|"selected_object_read"|
"latest_pointer_read"`, nullable `reconciliation_round=1|2`, nullable positive `page_ordinal`,
`release_finalizer_credential_subject_sha256`, `authorized_policy_row_sha256`, `method`,
`endpoint_template`, `request_url`, `request_payload_sha256`, `request_id`,
`request_dispatched_at`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="release_finalizer")`,
`broker_signature_base64url`, and `operation_dispatch_receipt_sha256`. Its signature and record
domains are `laconian-release-operation-dispatch-signature-v1\n` and
`laconian-release-operation-dispatch-receipt-v1\n`.

`ReleaseOperationTransportReceiptV1` is the unique signed terminal sibling. It has exactly
`schema_version`, the same full release/effect/credential/attempt identity, nested exact
`credential_subject: ReleaseFinalizerCredentialSubjectV1`,
`release_finalizer_credential_subject_sha256`, nested exact
`dispatch_receipt: ReleaseOperationDispatchReceiptV1`, `operation_dispatch_receipt_sha256`,
`method`, `endpoint_template`, `request_url`, `request_payload_sha256`, `request_id`,
`request_dispatched_at`, nullable `response_completed_at`, `transport_terminal_at`,
`outcome="response_observed"|"response_lost"`, nullable `response_status`, nullable
`safe_response_sha256`, nullable `source_observation_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="release_finalizer")`,
`broker_signature_base64url`, and `operation_transport_receipt_sha256`. Response-observed requires
status/completion and the class-bound safe body/observation fields; response-loss requires them
null. Subject, dispatch and terminal duplicated identity/request fields byte-equal; vault commit is
not after dispatch, dispatch is strictly before expiry, and response/terminal completion may occur
later. Signature and record domains are
`laconian-release-operation-transport-signature-v1\n` and
`laconian-release-operation-transport-receipt-v1\n`, with the common signature/final-digest
omissions.

`ReleaseFinalizerNoRequestReceiptV1` has exactly `schema_version`, the same full release identity,
`release_phase`, `effect_kind`, `effect_step_kind`, `effect_step_ordinal`,
`effect_idempotency_key`, positive `credential_attempt_ordinal`,
`release_finalizer_broker_policy_sha256`,
`authorized_policy_row_sha256`,
`reason="pre_intent_no_authorization"|"phase_forbidden"|"effect_not_required"`,
`operation_dispatch_count=0`, `recorded_at`, and `no_request_receipt_sha256`. Its reason must equal
the reconstructed phase/detail and policy row; no-request cannot replace a required authorized
effect. Its domain is `laconian-release-finalizer-no-request-receipt-v1\n`, omitting only its final
digest.

`ReleaseFinalizerCredentialDispositionV1` has exactly `schema_version`, the same full identity,
`release_phase`, `effect_kind`, `effect_step_kind`, `effect_step_ordinal`,
`effect_idempotency_key`, positive `credential_attempt_ordinal`,
`release_finalizer_broker_policy_sha256`,
`authorized_policy_row_sha256`,
`broker_phase_ledger_root_sha256`, nested exact
`operation_transport_projection: ReleaseOperationTransportProjectionV1`,
`operation_transport_projection_sha256`,
`credential_status="no_request"|"mint_denied_no_dispatch"|"minted_then_closed"|
"minted_permission_mismatch_then_closed_no_dispatch"|
"mint_delivery_unknown_unrecoverable_no_dispatch"`, ordered `requested_permissions`, ordered
`returned_permissions`, nullable `token_request_receipt_sha256`, nullable nested exact
`token_request_transport_receipt: BrokerTokenRequestTransportReceiptV1`, nullable
`no_request_receipt: ReleaseFinalizerNoRequestReceiptV1`, nullable nested exact
`token_unrecoverability_receipt: BrokerTokenUnrecoverabilityReceiptV1`, nullable
`credential_subject: ReleaseFinalizerCredentialSubjectV1`, nullable
`release_finalizer_credential_subject_sha256`, nullable
`token_fingerprint_sha256`, nullable `token_vault_committed_at`,
nullable `token_expires_at`, nullable nested exact
`token_closure_projection: ReleaseFinalizerTokenClosureProjectionV1`, `dispatch_count`,
`recorded_at`, and `credential_disposition_sha256`. `no_request` has empty permissions and null
request digest/transport/unrecoverability/subject/token/closure fields, a nonnull exact no-request receipt
and zero dispatch. Every other status has null no-request receipt.
`mint_denied_no_dispatch` has the exact `definite_denial` request transport, its byte-equal digest
expected requested permissions, empty returned
permissions, null unrecoverability/subject/token/closure and zero dispatch. `minted_then_closed` has an
exact `successful_201` request transport and digest, equal requested/returned permissions, null
unrecoverability, one exact nonnull credential subject/digest, full token fields and
class-bound closure projection; dispatch count equals its exact transport projection.
`minted_permission_mismatch_then_closed_no_dispatch` has the same successful request transport,
unequal returned permissions, full token/
closure fields, null unrecoverability and zero dispatch.
`mint_delivery_unknown_unrecoverable_no_dispatch` has the exact `delivery_unknown` request
transport/digest and role-matching
`BrokerTokenUnrecoverabilityReceiptV1`, expected requested permissions, empty returned permissions,
null token/closure fields and zero dispatch. A later retry uses a new credential-attempt
ordinal and vault transaction. Denial, mismatch and unknown have a null subject, empty transport-
attempt array, `dispatch_count=0`, and `terminal_status=no_dispatch`. `no_request` instead has an
empty array and `terminal_status=not_dispatched`, and is the sole credentialless mapping for a
pre-intent resolution with `resolved_status=not_dispatched`; only the valid
minted disposition named by a delivery resolution carries its exact effect attempts. Its domain is
`laconian-release-finalizer-credential-disposition-v1\n`, omitting only its final digest.
The additional tuple `(terminal_reconciliation_read,terminal_reconciliation_read,0)` is legal only
for this credential type, uses the plan-bound reconciliation-read idempotency key and read-only
policy row, and has no `ReleaseEffectDeliveryResolutionV1`. Its transport projection is the two
ordered reconciliation rounds. The unique successful read attempt uses `minted_then_closed` and
its token/closure projection byte-equals the nested projection in
`ReleaseReconciliationTokenClosureReceiptV1`.

`ReleaseOperationTransportProjectionV1` has exactly `schema_version`, the same identity/effect
tuple/key, ordered `attempts`, `dispatch_count`, `transport_terminal=true`,
`terminal_status="no_dispatch"|"not_dispatched"|"rejected_no_side_effect"|"exact_success"|
"conflicting"|"stable_double_read"|"reconciliation_incomplete"|
"reconciliation_unstable"`, and `operation_transport_projection_sha256`. Each strict
attempt has exactly positive `ordinal`, `attempt_kind="effect_write"|"inventory_page"|
"selected_object_read"|"latest_pointer_read"`, nullable `reconciliation_round`, nullable
`page_ordinal`, `request_id`, `dispatch_state="not_dispatched"|"dispatched"`, literal `method`,
`endpoint_template`, `request_payload_sha256`, `outcome`, nullable `response_status`, nullable
`safe_response_sha256`, nullable nested exact
`transport_receipt: ReleaseOperationTransportReceiptV1`, and nullable
`transport_receipt_sha256`. Effect-write attempts have null round/page,
byte-equal same-ordinal fields from the exact `ReleaseEffectDeliveryResolutionV1`, the literal tuple
method/endpoint, and its exact outcome/status/nullability matrix; terminal status equals that
resolution status. The terminal-reconciliation tuple has only dispatched GET attempts, round
`1|2`, page ordinal positive only for a paginated inventory, the zero-byte payload hash,
`outcome=read_200|read_404|read_definite_denial|read_response_lost|
read_unexpected_status|read_malformed_response`, with the same exact status/body nullability as the
publisher read wrapper. Each complete round contains every page,
selected-object, direct-object and latest-pointer request receipt from the matching nested
`ReleaseReconciliationObservationV1`, in literal tuple/page order; no request is omitted or added.
Every dispatched projection member nests the exact subject/dispatch/terminal wrapper and digest;
every duplicated field byte-equals it. A not-dispatched member has both wrapper fields null and
creates no ledger/audit start. The generic start/terminal pairs are therefore a bijection with
dispatched members.
Stable double-read has two complete equal semantic observations. Incomplete contains the exact
attempted prefix through its first terminal wrapper failure and zero or one complete observations;
unstable has two complete observations with unequal canonical release-state digests. Only the
failure-only reconciliation branch below admits the latter two statuses.
Dispatch count equals dispatched members. Its domain is
`laconian-release-operation-transport-projection-v1\n`, omitting only its final digest. Every
delivery resolution's disposition names the byte-exact projection of its attempts without pointing
back to the resolution digest.

`ReleaseFinalizerBrokerLedgerEntryV1` has exactly `schema_version`, positive gapless
`entry_ordinal`, nullable `predecessor_entry_sha256`, nullable `effect_kind`, nullable
`effect_step_kind`, nullable `effect_step_ordinal`, nullable `effect_idempotency_key`, nullable
positive `credential_attempt_ordinal`,
`entry_kind="phase_transition"|"no_request"|"token_request_started"|
"token_request_terminal"|"token_issued"|"operation_dispatch_started"|
"operation_dispatch_terminal"|"token_closed"|
"token_unrecoverable"`, `phase_before`, `phase_after`, nullable
`request_terminal_outcome="definite_denial"|"successful_response"|"delivery_unknown"`, nullable
`response_status`, nullable `token_fingerprint_sha256`, nullable
`request_or_transport_receipt_sha256`, `occurred_at`, and `entry_sha256`. Entries form one
nondecreasing-time hash chain; phases follow only
`constructive -> terminal_reconciling -> sealed`, with same-phase nontransition entries and one
strict advance per transition. Phase transition alone has null effect/key/attempt/evidence fields.
Every other entry has the full disposition key.

Status sequences and evidence are exact. `no_request` has one no-request entry naming its nested
`ReleaseFinalizerNoRequestReceiptV1`. Denial has request-started then request-terminal naming the
exact definite-denial request transport. Either minted status has request-started,
request-terminal(success), token-issued, a bijection over adjacent operation-dispatch start/
terminal pairs
(zero for permission mismatch), then token-closed naming the full
`ReleaseFinalizerTokenClosureProjectionV1`; issue/dispatch/close carry one fingerprint. Unknown has
request-started, request-terminal(delivery-unknown), then token-unrecoverable naming the exact
unrecoverability receipt and no dispatch. Request status is the shared total token-request matrix;
all unmentioned nullable combinations or entry sequences are invalid. Its domain is
`laconian-release-finalizer-broker-ledger-entry-v1\n`, omitting only its final digest.
An operation start names the exact `ReleaseOperationDispatchReceiptV1`, carries the issued
fingerprint and occurs at its `request_dispatched_at`; its unique terminal names the matching
`ReleaseOperationTransportReceiptV1`, carries the same fingerprint and occurs at
`transport_terminal_at`. Every start has one terminal before closure/phase advance, and no terminal
may reuse or precede a start.
`ReleaseFinalizerBrokerLedgerV1` has exactly `schema_version`, the same full identity,
`release_finalizer_broker_policy_sha256`,
`app_identity: GitHubAppInstallationIdentityV1(role="release_finalizer")`, ordered nested exact
`entries`, `final_phase="sealed"`, `outstanding_token_request_count=0`, `outstanding_dispatch_count=0`,
`live_token_count=0`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="release_finalizer")`,
`broker_signature_base64url`, `observed_at`, and `ledger_root_sha256`. Signature/preimage/key
verification uses
`UTF8("laconian-release-finalizer-broker-ledger-signature-v1\n") || CanonicalJSONV1(record without
exactly broker_signature_base64url and ledger_root_sha256)`; the role key is valid at `observed_at`.
Every credential disposition key has a bijective ledger
sequence, every issued fingerprint one close entry, every dispatch one start/terminal pair,
transport attempt and
revocation subject where applicable, and every delivery-unknown request one terminal/
token-unrecoverable pair with no dispatch. Replayed outstanding request and operation-dispatch
counts are nonnegative at every prefix and zero before closure or phase advance. A disposition's
`broker_phase_ledger_root_sha256` equals
its class-terminal entry's `entry_sha256`; its `recorded_at` equals that entry's `occurred_at`, and
the terminal entry's evidence digest names the disposition's no-request receipt, request transport,
full closure or unrecoverability receipt as specified above—it never equals the disposition digest.
The signed final ledger extends every prefix and seals only after either the selected successful
maximum-ordinal read-only reconciliation disposition closes or the exact third failure-only read
attempt reaches its denial, unrecoverability or token-closure terminal. The immediately following
and last entry is the
`terminal_reconciling -> sealed` transition; `observed_at` equals that transition time. Its domain is
`laconian-release-finalizer-broker-ledger-v1\n`, omitting only the final root for the record digest,
which therefore includes the verified signature.

`ReleaseReconciliationUnavailableReceiptV1` is the failure-only sealed read record. It has exactly
`schema_version`, the same full release identity, `release_phase`,
`release_finalizer_broker_policy_sha256`, `authorized_policy_row_sha256`, ordered nested exact
`attempt_summaries`, `terminal_reason="persistent_mint_denial"|
"persistent_permission_mismatch"|"persistent_delivery_unknown"|
"authenticated_read_unavailable"|"unstable_external_state"`,
`stable_double_read_count=0`, `outstanding_token_request_count=0`,
`outstanding_operation_dispatch_count=0`, `live_token_count=0`,
`final_broker_ledger_root_sha256`, `vault_audit_log_root_sha256`,
`canonical_release_state_claimed=false`, `release_success_authorized=false`,
`terminal_invalidation_required=true`, `recorded_at`, and
`release_reconciliation_unavailable_receipt_sha256`. Each
`ReleaseReconciliationAttemptSummaryV1` has exactly positive `credential_attempt_ordinal`,
`credential_disposition_sha256`, `operation_transport_projection_sha256`, ordered zero-to-two
`reconciliation_observation_sha256s`, nullable `terminal_transport_receipt_sha256`, and
`terminal_status="no_dispatch"|"reconciliation_incomplete"|"reconciliation_unstable"`.
The three summaries are a complete bijection over the policy's exact three read attempts and retry
schedule; every disposition/wrapper/partial observation is nested in the enclosing operation set.
Final disposition/status maps to terminal reason exactly as in the publisher unavailable table,
substituting the release types; no-request, a stable read, or any synthetic effect disposition is
forbidden. Incomplete time is the latest exact authenticated observation or failed terminal
wrapper; unstable retains both unequal observation roots. Final ledger/audit roots and zero counts
equal the enclosing signed records, and `recorded_at` equals their common sealed time. Its domain is
`laconian-release-reconciliation-unavailable-receipt-v1\n`, omitting only its final digest. It
authorizes only the phase-exact release or correction-release invalidation failure branch and no
release finalization/success/no-later claim.

`ReleaseFinalizerOperationSetV1` has exactly `schema_version`, the same full identity,
`release_phase`, nullable `preauthorized_release_plan_sha256`, nullable `executable_release_plan_sha256`,
nullable `security_attestor_receipt_sha256`, `release_finalizer_broker_policy_sha256`, ordered
nested exact `delivery_resolutions: ReleaseEffectDeliveryResolutionV1`, ordered nested exact
`credential_dispositions: ReleaseFinalizerCredentialDispositionV1`, ordered nested exact
`token_revocations: InstallationTokenRevocationReceiptV1`, nullable
`partial_effect_kind="annotated_tag"|"assets"`, nullable `partial_effect_root_sha256`, nullable
`failed_delivery_resolution_sha256`, nullable nested exact
`reconciliation_token_closure: ReleaseReconciliationTokenClosureReceiptV1`,
nullable `reconciliation_read_credential_disposition_sha256`,
`finality_status="stable_read_sealed"|"reconciliation_unavailable_sealed"`, nullable nested exact
`reconciliation_unavailable_receipt: ReleaseReconciliationUnavailableReceiptV1`,
`final_broker_phase="sealed"`, nested exact
`final_broker_ledger: ReleaseFinalizerBrokerLedgerV1`, `final_broker_ledger_root_sha256`,
`broker_vault_audit_log: BrokerVaultAuditLogV1(scope_kind="release",
broker_role="release_finalizer")`, `vault_audit_log_root_sha256`,
`outstanding_token_request_count=0`, `outstanding_dispatch_count=0`, `live_token_count=0`,
`closed_at`, and `operation_set_sha256`. Delivery resolutions follow the literal step order and
form the complete phase-derived contiguous successful prefix plus at most the invalidation detail's
one failed/conflicting step. Partial kind/root are both null or name the exact tag/asset prefix;
failed resolution equals that prefix's failed step or the nonpartial detail. Every token mint in the
broker ledger has exactly one ordered credential disposition per gapless credential-attempt
ordinal; no-request, denied, unrecoverable and permission-mismatched attempts followed by retry are retained.
Every issued token has one exact closure projection. Every issued effect token with valid returned
permissions additionally has exactly one unique revocation subject mapping to one complete result,
partial prefix or failed resolution; permission-mismatch dispositions authorize no effect and need
no subject-bearing revocation. The separate reconciliation closure names
the exact read set and closes after the second read. Its fingerprint, token request, permissions,
transport projection and token-closure projection equal the one named successful read disposition,
which is the final credential-attempt member. This is exactly `stable_read_sealed`, with null
unavailable receipt. For `reconciliation_unavailable_sealed`, both successful-read fields are null,
the exact nonnull unavailable receipt inventories all three failed read attempts, and neither a
stable reconciliation set nor a no-later/success claim is permitted.
`final_broker_ledger_root_sha256` and `vault_audit_log_root_sha256` equal the nested signed records'
recomputed roots. Ledger/audit scope, policy/App/key, token requests, operation dispatch pairs,
closures/unrecoverability and zero counters are bijective; `closed_at` equals ledger `observed_at`,
audit `sealed_at` and final sealed transition time. The final records prove completeness and sealed
denial of later mint. Its domain is
`laconian-release-finalizer-operation-set-v1\n`, omitting only its final digest.
At `pre_intent`, the preauthorized root equals the preparation candidate when one exists and may be
null only when preparation failed before plan construction; that no-plan form has empty delivery,
partial/failure and effect-revocation members plus exact no-request/no-mint write ledger evidence
and the one required read-only reconciliation closure. Every later
phase requires all three preauthorized/executable/attestor roots nonnull.

`ReleaseNoLaterEffectsEvidenceV1` has exactly `schema_version`, the same full identity,
`authority_parent_oid`, `release_phase`, nested exact
`release_finalizer_operation_set: ReleaseFinalizerOperationSetV1`, nested exact
`reconciliation_observation_set: ReleaseReconciliationObservationSetV1`,
`outstanding_dispatch_count=0`, `live_installation_token_count=0`, `observed_at`, and
`no_later_effects_root_sha256`. The read set occurs after all write resolutions and closure of all
write tokens; its read-only token is then closed in the operation set's separate reconciliation
closure.
`observed_at` equals the operation set's final `closed_at`, which is not before the second
reconciliation observation. The operation-set inventory is
complete for the release phase and detail, so an omitted attempt, effect or token cannot validate.
This schema requires the nested operation set `finality_status=stable_read_sealed`, a nonnull exact
reconciliation closure/read disposition and null unavailable receipt. Failure-only sealed finality
cannot satisfy or be substituted for this no-later proof.
Its digest is `SHA256(UTF8("laconian-release-no-later-effects-evidence-v1\n") ||
CanonicalJSONV1(record without exactly no_later_effects_root_sha256))`. The enclosing invalidation's
external-object root equals the nested second inventory digest and its recorded time equals this
evidence's observed time.

`release_phase` is exactly `pre_intent`, `release_intent`, `tag_receipt`,
`draft_release_receipt`, `asset_receipts`, or `publish_receipt`. The literal append matrix is:

| Phase | Intent | Tag append | Draft append | Asset append | Publish append |
|---|---|---|---|---|---|
| `pre_intent` | null | null | null | null | null |
| `release_intent` | nonnull | null | null | null | null |
| `tag_receipt` | nonnull | nonnull | null | null | null |
| `draft_release_receipt` | nonnull | nonnull | nonnull | null | null |
| `asset_receipts` | nonnull | nonnull | nonnull | nonnull | null |
| `publish_receipt` | nonnull | nonnull | nonnull | nonnull | nonnull |

At `pre_intent`, both plan roots and the top-level successful-attestor root are null; at every later
phase all three are nonnull and byte-equal current intent/effect authorization. Each append hash is
the accepted `Initial*ReceiptAppendV1.append_sha256`, never a nested payload digest; reconstruction
derives that digest from canonical wrapper bytes. `security_attestation_failure` and
`invalid_event_nondismissible` are legal only at `pre_intent`; the latter is pre-intent because a
hold forbids intent authorization. A pre-intent external conflict requires nonnull candidate plan
and passing attestor/executable fields in `release_preparation`. `immutable_release_verification_failure` is legal only
at `publish_receipt`. Credential exposure and drift are legal at any phase. Ordinary members require
null active exposure and hold; credential, drift and held members bind and consume exactly their
current nested evidence. Every duplicated identity/root inside a nested detail equals the common
parent. The external-object root inventories every observed object, including an annotated tag
object whose ref step failed and a published release whose response was lost. Before any authorized
effect it is empty only when authenticated complete reads prove absence; a preexisting/foreign
pre-intent conflict produces a nonempty inventory while authorization, token-mint and dispatch
counts remain zero. `no_later_effects_root_sha256` binds final reconciliation reads.
The digest is
`SHA256(UTF8("laconian-release-plan-invalidation-evidence-v1\n") || CanonicalJSONV1(record without
exactly release_plan_invalidation_evidence_sha256))`; no terminal event/hash or successor OID is
representable.

Every terminal initial attempt installs exactly one strict terminal record in the same authority
CAS as its terminal campaign event. `InitialPublicationInvalidationV1` has exactly these ordered
fields:

```text
schema_version
terminal_kind
campaign_id
campaign_registry_sha256
publication_id
publication_attempt
bundle_kind
authorizing_intent_sha256
publication_plan_sha256
sealed_bundle_root_sha256
source_authority_parent_oid
authority_parent_oid
authority_phase
terminal_event_type
invalidation_cause
terminal_containment_finality
terminal_containment_finality_sha256
successor_merge_denylist_root_sha256
active_publication_terminal_containment_root_before
active_publication_terminal_containment_root_after
fenced_write_ambiguity
fenced_write_ambiguity_sha256
publication_pr_terminal_disposition
ordinary_stop_evidence_sha256
publication_plan_invalidation_evidence_sha256
protocol_authority_drift_evidence_sha256
credential_exposure_incident_evidence_sha256
terminal_exposure_consumption_sha256
credential_exposure_supplement_sha256
post_merge_admission_failure_sha256
publisher_credential_disposition_set_sha256
reconciliation_unavailable_receipt_sha256
release_authorization_ledger_root_sha256
release_finalizer_operation_set_sha256
release_reconciliation_unavailable_receipt_sha256
release_invalidation_evidence_sha256
no_later_effects_root_sha256
recorded_at
invalidation_sha256
```

The schema literal is `InitialPublicationInvalidationV1`, `terminal_kind=invalidation`, the attempt
is a positive canonical integer, and all direct identity/root/parent fields equal reconstructed
authority. `authority_phase` is exactly `initial_intent`, `initial_branch_receipt`,
`initial_pr_receipt`, `initial_opened`, `post_merge_pre_release_intent`,
`post_merge_release_intent`, `post_merge_tag_receipt`, `post_merge_draft_release_receipt`,
`post_merge_asset_receipts`, or `post_merge_publish_receipt`. The five post-intent phase names map
one-to-one to `ReleasePlanInvalidationEvidenceV1.release_phase=release_intent|tag_receipt|
draft_release_receipt|asset_receipts|publish_receipt`; pre-release-intent maps to `pre_intent`.
`terminal_event_type` is exactly `PERMANENT_STOP`,
`COMPLETE_PUBLICATION_PLAN_INVALIDATED`, `INVALID_PUBLICATION_PLAN_INVALIDATED`,
`RESULT_MERGE_INVALIDATED`, `INVALID_PREFIX_MERGE_INVALIDATED`, or
`RELEASE_PLAN_INVALIDATED`. `invalidation_cause` is exactly `ordinary_plan_or_lineage`,
`protocol_authority_drift`, `credential_exposure`, `post_merge_admission_failure`,
`publication_reconciliation_unavailable`, `publication_write_ambiguity_fenced`, or
`release_invalidation`. Every nullable field is
present.

`PublicationPlanInvalidationEvidenceV1`, used by either typed initial plan-invalidation event, has
exactly `schema_version`, `campaign_id`, `campaign_registry_sha256`, `publication_id`, positive
`publication_attempt`, `bundle_kind`, `authorizing_intent_sha256`, `publication_plan_sha256`,
`sealed_bundle_root_sha256`, `parent_authority_oid`, `authority_phase`, `reason`, nullable
`branch_receipt_sha256`, nullable `pull_request_receipt_sha256`, nullable exact
`publication_pr_terminal_disposition`, `branch_create_delivery_resolution_sha256`,
`pr_create_delivery_resolution_sha256`, `pr_marker_discovery_sha256`, nullable
`terminal_guard_set_sha256`, `conflicting_publication_objects_root_sha256`,
`expected_base_oid`, `expected_head_oid`, `observed_current_base_oid`, nullable
`observed_branch_head_oid`, ordered `plan_mismatch_predicates`, nested exact `detail`,
nullable `publisher_credential_disposition_set_sha256`, nullable
`reconciliation_unavailable_receipt_sha256`, nullable
`release_authorization_ledger_root_sha256`, nullable `no_later_effects_root_sha256`, `recorded_at`, and
`publication_plan_invalidation_evidence_sha256`. Its schema literal is the class name; reason is
exactly `base_moved`, `head_moved`, `plan_mismatch`, `closed_unmerged`,
`terminal_invalid_lineage`, or `reconciliation_unavailable`.
`PublicationPlanInvalidationDetailV1` is a strict reason discriminator
whose remaining fields are exactly:

| Reason | Exact remaining detail fields |
|---|---|
| `base_moved` | `expected_base_oid`, `observed_current_base_oid`, `base_observation_receipts_root_sha256` |
| `head_moved` | `expected_head_oid`, `observed_branch_head_oid`, `branch_observation_sha256` |
| `plan_mismatch` | `expected_publication_plan_sha256`, `observed_plan_inputs_root_sha256`, nonempty ordered `failed_predicates`, `verification_receipts_root_sha256` |
| `closed_unmerged` | nested exact `publication_pr_terminal_disposition` with `outcome=closed` |
| `terminal_invalid_lineage` | `expected_sealed_root_sha256`, `observed_lineage_root_sha256`, nonempty ordered `failed_predicates`, `verification_receipts_root_sha256` |
| `reconciliation_unavailable` | `publisher_credential_disposition_set_sha256`, `reconciliation_unavailable_receipt_sha256`, `release_authorization_ledger_root_sha256`, nested exact `publication_pr_terminal_disposition` with `outcome=no_pr|closed` |

Expected fields equal the intent/plan. Base-moved requires a different nonnull current protected-
base OID; head-moved requires a different nonnull branch head. A null branch head is legal only
with `no_pr`, `branch_outcome=absent`, and authenticated absence in the branch resolution. These
current ref observations are distinct from the nested disposition's observed PR base/head, which
remain null for `no_pr` and are nonnull only for a PR outcome. Once intent exists, the terminal disposition is always nonnull and
is `no_pr|closed`; an observed merge uses the distinct failed-admission event. Its branch/PR
delivery, final marker discovery, guard set, conflict root and expected OIDs byte-equal the
duplicated top-level fields; its PR observed OIDs and identity mismatch predicates are independently
preserved inside the disposition. Top-level `plan_mismatch_predicates` is the nonempty canonical
schema-ordered subset appropriate to the reason. `plan_mismatch` uses
`publication_id_mismatch`, `attempt_mismatch`, `bundle_kind_mismatch`,
`ruleset_policy_mismatch`, `actor_mismatch`, `idempotency_key_mismatch`, or
`prior_terminal_head_reuse`; `terminal_invalid_lineage` uses `sealed_root_mismatch`,
`receipt_parent_mismatch`, `marker_mismatch`, `conflicting_object_uncontained`, or
`terminal_guard_incomplete`; base/head/closed reasons use only their same-named predicate; and
reconciliation unavailable uses only `reconciliation_unavailable`.
Receipt nullability follows reconstructed
phase. For `reconciliation_unavailable`, the three top-level failure roots and disposition
byte-equal its detail and the exact sealed unavailable set/receipt, including that receipt's empty
signed release-authorization ledger; `no_later_effects_root_sha256` is null and `recorded_at` equals
the receipt/set/publisher-ledger/vault-log/release-ledger sealed time. Every other reason requires
the three failure roots null, a nonnull exact no-later root, and `recorded_at` equal its observed
time. Its domain is
`laconian-publication-plan-invalidation-evidence-v1\n`, omitting only its final digest.

The terminal record's event/cause/nullability matrix is exhaustive; every field not named in a row
is null:

| Terminal event | Exact `invalidation_cause` | Required nonnull cause fields |
|---|---|---|
| `PERMANENT_STOP` | `ordinary_plan_or_lineage` | `ordinary_stop_evidence_sha256`; exact `no_pr|closed` disposition |
| `PERMANENT_STOP` | `protocol_authority_drift` | `protocol_authority_drift_evidence_sha256`; exact `no_pr|closed` disposition |
| `PERMANENT_STOP` | `credential_exposure` | `credential_exposure_incident_evidence_sha256`; exact `no_pr|closed` disposition; terminal-consumption and supplement fields null |
| `PERMANENT_STOP` | `publication_reconciliation_unavailable` | `ordinary_stop_evidence_sha256(reason=publication_reconciliation_unavailable)`; exact `publisher_credential_disposition_set_sha256`, `reconciliation_unavailable_receipt_sha256`, empty signed `release_authorization_ledger_root_sha256`, and exact `no_pr|closed` disposition; `no_later_effects_root_sha256=null` |
| `COMPLETE_PUBLICATION_PLAN_INVALIDATED` | `ordinary_plan_or_lineage` | `publication_plan_invalidation_evidence_sha256`; exact `no_pr|closed` disposition once intent exists |
| `INVALID_PUBLICATION_PLAN_INVALIDATED` | `ordinary_plan_or_lineage` | `publication_plan_invalidation_evidence_sha256`; exact `no_pr|closed` disposition once intent exists |
| `INVALID_PUBLICATION_PLAN_INVALIDATED` | `protocol_authority_drift` | plan-invalidation and exact drift-evidence roots; exact `no_pr|closed` disposition; exposure/supplement fields null |
| `INVALID_PUBLICATION_PLAN_INVALIDATED` | `credential_exposure` | plan-invalidation, incident, and supplement roots; exact `no_pr|closed` disposition; terminal-consumption null |
| `INVALID_PUBLICATION_PLAN_INVALIDATED` | `publication_reconciliation_unavailable` | plan-invalidation evidence with `reason=reconciliation_unavailable`; exact unavailable set/receipt and empty signed release-ledger roots copied from it; exact `no_pr|closed` disposition; `no_later_effects_root_sha256=null` |
| `PERMANENT_STOP` | `publication_write_ambiguity_fenced` | nested exact `PublicationFencedWriteAmbiguityV1(terminal_route=initial_complete_premerge)` and digest; ordinary disposition/no-later/unavailable/post-merge fields null |
| `INVALID_PUBLICATION_PLAN_INVALIDATED` | `publication_write_ambiguity_fenced` | nested exact `PublicationFencedWriteAmbiguityV1(terminal_route=initial_invalid_premerge)` and digest; ordinary disposition/no-later/unavailable/post-merge fields null |
| `RESULT_MERGE_INVALIDATED` or `INVALID_PREFIX_MERGE_INVALIDATED` | `post_merge_admission_failure` | `post_merge_admission_failure_sha256` with `failure_kind=ordinary`; its nullable-or-`already_merged` disposition is copied exactly and both emergency objects are null |
| either merge-invalidation event | `post_merge_admission_failure` | post-merge failure with `failure_kind=publication_write_ambiguity_merge_race`, exact write-ambiguity merge-won containment finality and empty signed release ledger; ordinary disposition/no-later fields null |
| `RESULT_MERGE_INVALIDATED` | `protocol_authority_drift` | post-merge failure with `failure_kind=protocol_authority_drift_race` and byte-identical drift root; exact `already_merged` disposition; terminal-consumption null |
| either merge-invalidation event | `credential_exposure` | post-merge failure with `failure_kind=credential_exposure_race`, incident, and byte-identical terminal-consumption roots; exact `already_merged` disposition |
| either merge-invalidation event | `publication_reconciliation_unavailable` | post-merge failure with `failure_kind=reconciliation_unavailable` and ordinary merge-won containment finality; exact unavailable set/receipt and empty signed release-ledger roots copied from it; exact `already_merged` disposition; `no_later_effects_root_sha256=null` |
| `RELEASE_PLAN_INVALIDATED` | `release_invalidation` | release evidence reason is one of the six ordinary reasons or `invalid_event_nondismissible`; all emergency fields null |
| `RELEASE_PLAN_INVALIDATED` | `release_invalidation` | release evidence reason is `release_reconciliation_unavailable`; exact failure-only release operation-set/receipt roots copied from it; `no_later_effects_root_sha256=null` and publisher-unavailable fields null |
| `RELEASE_PLAN_INVALIDATED` | `protocol_authority_drift` | release evidence reason is exactly `protocol_authority_drift` and its nested drift root byte-equals the direct drift root; disposition and terminal-consumption null |
| `RELEASE_PLAN_INVALIDATED` | `credential_exposure` | release evidence reason is exactly `credential_exposure`, and its nested terminal consumer byte-equals the direct incident/consumption roots; disposition null |

For a merge row, every duplicated nested root byte-equals the strict
`PostMergeAdmissionFailureV1`; for a release row it equals the strict release-invalidation evidence.
For every row terminating an active publication-containment root, the nested exact
`PublicationTerminalContainmentFinalityV1` and digest, successor denylist root, before root equal to
its intent digest and after root null are nonnull. Its terminal parent byte-equals
`authority_parent_oid`; its source parent byte-equals the record's distinct
`source_authority_parent_oid`. Ordinary premerge rows also carry the no-later root whose nested
finality is byte-identical; ambiguity rows carry the exact fenced object; merge rows carry the exact
merge-won finality through `PostMergeAdmissionFailureV1`. The terminal CAS preserves the successor
denylist byte-for-byte and clears the active containment root. Release-only invalidation with no
active publication containment has all seven containment/fence fields null and its source parent
equals its immediate authority parent. Direct normal failed admission has the same null
containment/fence fields and immediate source parent, without a denylist transition.
Premerge STOP and invalid-prefix supplement routes consume the active exposure chain directly
through incident/supplement evidence and therefore cannot carry the post-merge-only
`TerminalCredentialExposureConsumptionV1`. A plan invalidation before any
authoritative intent has no initial directory and therefore no terminal record; once `intent.json`
exists, every applicable STOP/plan invalidation/failed admission/release invalidation appends this
record atomically. Premerge STOP/plan invalidation and containment-sourced ordinary failed-admission rows require exact
`PublicationNoLaterEffectsEvidenceV1`; its duplicated identity, phase, disposition and delivery
roots equal the terminal record, except that every
`publication_reconciliation_unavailable` row requires this root null and instead carries the exact
sealed unavailable set/receipt and their empty signed release-authorization-ledger root. A direct
`PostMergeAdmissionFailureV1(source_kind=normal_postmerge_admission)` has a null disposition, null
no-later root and copies that object's deterministic `recorded_at`; it is not a close-race
terminalization. The write-ambiguity merge-race also has a null no-later root and uses its
merge-won/failure sealed time. A
`RELEASE_PLAN_INVALIDATED` row instead requires the exact
`ReleaseNoLaterEffectsEvidenceV1` nested by its `ReleasePlanInvalidationEvidenceV1`, and the generic
terminal `no_later_effects_root_sha256` equals that release root, except that
`reason=release_reconciliation_unavailable` requires the no-later root null and copies the exact
failure-only release operation-set/receipt roots. It never claims zero release
authorization after an intent/effect exists. `recorded_at` byte-equals the selected class's final
authenticated closure/sealed `observed_at` and the terminal event timestamp; for unavailable it
equals the applicable publisher or release failure receipt, disposition/operation set, broker
ledger and vault-log sealed times, plus the signed empty release-authorization ledger for the
publisher branch. Its digest is
`SHA256(UTF8("laconian-initial-publication-invalidation-v1\n") || CanonicalJSONV1(record without
exactly invalidation_sha256))`.

`InitialPublicationFinalizationV1` has exactly `schema_version`,
`terminal_kind="finalization"`, `campaign_id`, `campaign_registry_sha256`, `publication_id`,
`publication_attempt`, `bundle_kind`, `authorizing_intent_sha256`, `publication_plan_sha256`,
`sealed_bundle_root_sha256`, `authority_parent_oid`, `publication_merge_receipt_sha256`, nullable
`publication_success_finality: PublicationSuccessFinalityEvidenceV1`,
`publication_success_finality_root_sha256`, nullable
`release_intent_sha256`, nullable `tag_receipt_append_sha256`, nullable
`draft_release_receipt_append_sha256`, nullable `asset_receipts_append_sha256`, nullable
`publish_receipt_append_sha256`, nullable `final_release_verification_receipt_sha256`, nullable
`release_no_later_effects: ReleaseNoLaterEffectsEvidenceV1`, nullable
`release_no_later_effects_root_sha256`,
`terminal_event_type`, `recorded_at`, and `finalization_sha256`. The schema literal is
`InitialPublicationFinalizationV1`. Invalid-prefix success requires
`terminal_event_type=INVALID_PREFIX_MERGED`, an exact nonnull publication-success-finality object/
root and all release fields null; complete success requires
`terminal_event_type=RESULT_RELEASED` and every release field nonnull and equal to the accepted
append wrapper/final-verification chain, including an exact release no-later object whose nested
operation set is sealed with zero live tokens. Each duplicated finality root recomputes from its
nested exact object. Each append field is specifically its accepted wrapper's
`append_sha256`; nested payload digests are reconstructed from those canonical bytes. The
finalization timestamp equals the terminal event timestamp and, for `RESULT_RELEASED`, the release
no-later final closure time; it cannot precede the publication-success sealed time. Its digest
domain is `laconian-initial-publication-finalization-v1\n`, omitting only
`finalization_sha256`.

`RESULT_MERGED` alone does not terminalize the complete attempt: it appends the exact merge receipt
and leaves zero terminal members while release is pending. `INVALID_PREFIX_MERGED` appends its merge
receipt plus finalization; `RESULT_RELEASED` appends finalization; every typed terminal failure above
appends invalidation. Exactly one terminal member is thereafter immutable. Missing, both, premature,
cause/event mismatch, or a later receipt beneath an invalidated attempt fails reconstruction before
any credential or effect.

The annotated tag's tagger name/email/timestamp are deterministic content needed for its OID, not
proof of the platform actor. Actor authorization comes only from the intent-bound App installation
identity, broker/API request and audit-log receipts, and protected-tag ruleset evidence.

Draft recovery fully paginates authenticated `GET /releases` (the by-tag endpoint is not a draft
lookup), requires one unique tag/marker/author match, then fetches that exact release ID. Published
recovery may use the exact tag endpoint and still re-verifies by ID. Create/update endpoints have no
platform idempotency key or CAS, so one repository-wide serialized finalizer performs exact
pre-read/effect/post-read reconciliation. After an asset timeout, 422, or 502 it relists assets and
adopts only an exact name/content-type/size/provider-digest/uploader match, downloading and hashing
bytes when the API digest is absent. A divergent object or `starter` asset is terminal
`RELEASE_PLAN_INVALIDATED` evidence under the no-delete/no-overwrite policy; it is never blindly
retried.

Every query, create, adoption, response loss, retry, conflict, and returned object ID/root is an
authority receipt. A same-name object with a different actor, target, marker, byte/root, plan, or
lineage is never overwritten, force-updated, reused, or hidden. Before merge, a complete conflict
uses the exact complete-publication invalidation or `PERMANENT_STOP`; an invalid-prefix conflict
uses its exact invalidation. An already-merged complete object that fails admission emits
`RESULT_MERGE_INVALIDATED` and enters `RELEASE_BLOCKED`; an already-merged invalid-prefix object
that fails admission emits `INVALID_PREFIX_MERGE_INVALIDATED` and enters terminal
`INVALID_PREFIX_MERGED_INVALID`. A release/tag/draft/asset/publish conflict emits
`RELEASE_PLAN_INVALIDATED` and enters `RELEASE_BLOCKED`. Immutable or externally visible objects
are recorded as exposure/orphan
evidence. Recovery cannot create a second branch, PR, tag, Release, asset name, or publish
transition. All external effects are therefore either covered by a prior durable intent and exact
receipt/adoption, or are terminal conflicting evidence; no untracked ordinary-publication orphan is
accepted.

Credential exposure at `RESULT_MERGED` uses the same event with a strict pre-intent or post-intent
invalidation form. Both require `TerminalCredentialExposureConsumptionV1` and clear the active
pair plus matching optional hold in the invalidation CAS. The pre-intent form proves no release
object exists; the post-intent form binds the exact intent and every discovered/adopted tag, draft,
asset, or published object plus no-later-effects reconciliation. Ordinary invalidation forbids the
terminal projection and requires the active pair null. No post-intent evidence may be hidden by
selecting the pre-intent form.

### 7.7 Public replay CLI is offline and non-evidentiary

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
`campaign_registry_sha256`, `protocol_attestations_root`, both identity-registry digests, and the
common `workflow_root`.
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
are restricted to the protected input-tag pattern; the paired attestation-tag pattern is separately
protected against update and deletion and is never accepted as a workflow trigger. The exact
stable semantic ruleset policy root enters `ProtocolAttestationTagBindingV1`; variable observations
remain separate receipts. Approval actors and deployment
identities are retained in provenance. A platform administrator may technically bypass or later
change a ruleset, so a ref name or ruleset is not immutable authority: exact Git OIDs,
`GitObjectSHA256V1` values, the double-read receipts, and post-seal drift checks are mandatory.

One universal gate applies immediately before **any** provider/App/OIDC credential mint, mapping,
or use and before any external effect other than the read-only verification calls themselves. The
responsible workflow, broker, or fixed tool freshly double-reads both exact refs, verifies both tag
and peeled-object identities/raw hashes, reconstructs the stable `TagRulesetPolicyV1` projection
from fresh `TagRulesetObservationReceiptV1` evidence, and matches the sealed companion binding and
`campaign_registry_sha256`. A temporary inability to complete any read produces no token, effect,
or state mutation. Proven drift before merge uses exactly the closed drift STOP matrix; after merge
it uses only the existing release-invalidation/correction path. No cached preflight result,
environment approval, durable intent, prior receipt, or idempotent retry bypasses this gate.
Independently, a nonnull `active_credential_exposure_pending_root` blocks every ordinary authority
mutation, credential issuance, provider call, artifact access/download, publication, release,
correction, documentation/social action, and external effect. The only admissions are the next
inventoried containment effect, its typed `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` CAS, the final
phase-exact STOP, supplement, merge/release invalidation, or correction intent/invalidation that
consumes the root, and protected-main reads/CAS needed for those acts. An unresolved invalid-event
hold likewise blocks every ordinary edge;
the only atomic consumers permitted with a nonnull hold are `INVALID_EVENT_DISMISSED`; premerge
`PERMANENT_STOP` with `invalid_event_nondismissible`, typed credential-exposure, or typed drift
evidence; `RESULT_MERGED -> RELEASE_PLAN_INVALIDATED`; and `RELEASED ->
CORRECTION_INTENT_AUTHORIZED` only with the exact nondismissible/exposure/invalidation/drift
discriminator and evidence. Hold admission is forbidden while any correction prefix is active.
It is also forbidden while any initial-publication prefix is active and at
`COMPLETE_PUBLICATION_PR_OPEN`.
Each consumer binds the predecessor hold root and its successor clears it. All require the
active exposure root null except the credential emergency flow's own progress/final consumer.
Every other publication, promotion, release, correction, invalid-prefix, or safe-finalization edge
requires both roots null.
On proven premerge drift the requested ordinary credential/effect remains forbidden. The closed
exceptions are: state-writer for the typed drift STOP CAS and, for an active initial complete-
publication prefix, publisher only for its exact absence/close/merge disposition and corresponding
STOP or failed-admission CAS; the protected-main safe-invalid continuation after an already sealed
STOP/BUDGET lineage; and credential-exposure pending/final CASes plus only their inventoried
containment credentials/effects/receipts, because exposure containment has emergency precedence.
Those exceptions are governed by their exact matrices below and grant no live recovery.

All automated benchmark-workflow writes use exactly three installed, pairwise-distinct,
repository-scoped GitHub Apps with actor IDs frozen in the security protocol and receipts:

- the **state-writer App** performs only expected-OID, non-force, fast-forward updates on
  `benchmark-authority/*`, for requests admitted from the fixed hash-verified reusable
  state-writer job;
- the **publisher App** creates the exact result branch and PR bound by the current
  `PublicationPlanV1`, writes the App-bound eligibility/terminal-guard protocol-evidence context,
  or closes/dequeues/fences only the exact affected PR after typed terminal containment; the App
  context is not the branch-protection required check; and
- the **release-finalizer App** creates the exact protected annotated result tag, creates the exact
  draft release and checksum-bound assets, verifies their returned roots, and performs exactly one
  transition that publishes that draft.

The companion-tag amendment adds no GitHub App, workflow, environment, credential, or secret. The
existing 15-member workflow inventory and three-App topology remain exact; protocol reviewers and
the registered operator respectively create the serial review commits and paired annotated tags
through protected human Git operations before preflight.

The release-finalizer App installation also has `Administration: write`, solely because GitHub
withholds ruleset `bypass_actors` from callers lacking ruleset write access; this does not add a
fourth App, and the security-attestor endpoint policy remains GET-only. A separate fixed `security_attestor` job in
`.github/workflows/benchmark-publish.yml` at the exact allowed main/ref/plan runs only in the
protected `benchmark-publish` environment. After its own closed OIDC job identity verifies, an
external App-token broker mints a permissions-downscoped installation token containing only
`administration:write`, `metadata:read`, and `contents:read`; the App private key never enters
Actions, and the exact token request and returned permissions are receipt-bound. No
contents/Releases write token or publisher/state credential is present in that job. The fixed
client rejects every non-GET method even though the installation token is technically broader.
Conversely, release-writer tokens omit Administration permission. No other workflow, ref, job, or environment
may request the attestor token. The attestor reads exact repository rule-suite and
immutable-Release settings and never receives a provider key or model-output/artifact bytes.

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
`actor_id` are caller-discriminated. Every normal caller requires the same plan-authorized human
dispatcher in the frozen operator registry. Only `benchmark-dismiss-hold.yml` instead requires the
exact `eligible_dismisser_account_id/login` in the current strict dismissal plan and C0 dismissal
policy, distinct from the rejected source actor. Its plan also binds the exact dispatcher workflow
and ref. A rerun's REST `triggering_actor` must satisfy the same caller-specific rule; it cannot
fall back to the initial actor or the tag operator. The `environment` claim must be absent because the reusable state-writer job does not use a GitHub
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
workflow SHA claims equal to the dispatch's current main commit. Except for the six ordinary
post-merge admission events, the emergency exposure rows, the closed initial-release receipt append,
and four current-main containment classes enumerated immediately below, that main commit must be the single SHA already bound by the
applicable audit, analysis, collection, publication, release, dismissal, or correction plan. For
every main run the broker reads both workflow members at that commit and requires their bytes to
equal the corresponding C0-derived member hashes in the common workflow root. All caller rows require
`event_name=workflow_dispatch`; a reusable `workflow_call` is the mechanism of the called job, not
the triggering event reported by these OIDC tokens. The closed caller/ref/event mapping is:

The only plan-SHA exceptions beyond those six are four current-main classes: drift containment;
publication terminal-containment start/barrier/finality;
the exact credential-exposure pending/progress/phase-terminal/supplement rows below; and safe-invalid
continuation for any already sealed STOP or BUDGET lineage. Each uses fresh current `H`,
double-reads refs/policy, authenticates the run, and requires caller and reusable workflow blobs at
`H` to byte-equal their sealed C0 workflow-root members. They authorize no other main-ref event.

For publication containment, the authenticated start run's `sha` is the intent-bound
`containment_main_oid` baseline and its workflow bytes/root are frozen in the accepted event.
Post-CAS work may continue in that run or a fresh protected-current-main resumption run. Every
later mint binds the accepted containment authority OID/root plus that run's authenticated current
main SHA; when it differs from the baseline, the broker first constructs the exact signed
`PublicationContainmentMainAdvanceProofV1` from baseline to current main. Thus OIDC never pretends
the original run SHA moved, while a safe first-parent descendant with byte-identical frozen
workflow members remains live. Force-push, unrelated workflow bytes, an affected intervening merge,
or a failed compare denies mint and leaves the containment root resumable.

Reachability of those classes is conditional on an enforced main-liveness invariant. While any
campaign is nonterminal, the existing protected-main validation check rejects a merge that changes,
deletes, or renames any of the 15 C0-frozen workflow members or changes their ordered root; the
existing state-writer App also refuses authority after such a merge. The check itself runs from
protected current main, compares the proposed tree to the sealed campaign registry/root, and needs
no tag trigger, so this introduces no circular dependency and no new workflow, App, environment, or
secret. Each fallback still verifies current bytes. A platform administrator can bypass/disable
GitHub protection; that is an explicit trust limitation, and “reachable from every state” means
only while this invariant is enforced.

| Caller workflow | Required triggering ref | Allowed event types |
|---|---|---|
| `benchmark-preflight.yml` | exact campaign input tag | `PREFLIGHT_SEALED` |
| `benchmark-batch.yml` | exact campaign input tag | `BATCH_RECEIPT_CONSUMED`, `NO_DISPATCH_PROVED`, `VERIFIED_PARTIAL`, `GENERATION_SET_SEALED`, `JUDGE_SET_SEALED`, `PERMANENT_STOP`, `BUDGET_EXHAUSTED`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
| `benchmark-hard-score.yml` | exact campaign input tag | `HARD_SCORE_SET_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
| `benchmark-evidence.yml` | exact campaign input tag; protected current `main` only for drift containment, the exact cross-phase exposure rows, terminal-invalid supplements, or safe-invalid continuation | `EVIDENCE_INVENTORY_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED`, `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`; on main, only the phase-exact containment/supplement or drift event is allowed |
| `benchmark-audit.yml` | exact plan-bound `main` | `AUDIT_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
| `benchmark-analysis.yml` | exact plan-bound `main` | `ANALYSIS_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
| `benchmark-collect-complete.yml` | exact plan-bound `main` | `COMPLETE_BUNDLE_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
| `benchmark-finalize-invalid.yml` | exact campaign input tag or protected current `main` under the safe-invalid exception | `INVALID_PREFIX_SEALED` |
| `benchmark-dismiss-hold.yml` | exact plan-bound `main` | `INVALID_EVENT_DISMISSED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
| `benchmark-publish.yml` | exact plan-bound `main`; protected current `main` additionally for its exact post-merge admission, publication terminal-containment, exposure, and drift rows | `PUBLICATION_INTENT_AUTHORIZED`, `PUBLICATION_TERMINAL_CONTAINMENT_STARTED`, `COMPLETE_PUBLICATION_PR_OPENED`, `INVALID_PUBLICATION_PR_OPENED`, `COMPLETE_PUBLICATION_PLAN_INVALIDATED`, `INVALID_PUBLICATION_PLAN_INVALIDATED`, `RESULT_MERGED`, `RESULT_MERGE_INVALIDATED`, `INVALID_PREFIX_MERGED`, `INVALID_PREFIX_MERGE_INVALIDATED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED`, `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`, `CORRECTION_INTENT_AUTHORIZED`, `CORRECTION_PUBLICATION_RECORDED`, `CORRECTION_MERGE_RECORDED`, all four typed publication `CORRECTION_INVALIDATED` outcomes (`unmerged_invalid`, `merged_invalid`, `fenced_write_ambiguity`, `reconciliation_unavailable`); credential authority is limited to complete/invalid PR handling, publication containment, bare release-blocked/released correction start, and pre-merge correction prefixes; separately, only the closed `initial_publication_receipt_append` non-event mutation |
| `benchmark-release.yml` | exact plan-bound `main`; protected current `main` additionally for its exact post-merge exposure and drift rows | `RESULT_RELEASE_INTENT_AUTHORIZED`, `RESULT_RELEASED`, `RELEASE_PLAN_INVALIDATED`, `CORRECTION_TAG_RECORDED`, `CORRECTION_RELEASE_RECORDED`, `CORRECTION_RESULT_RELEASED`, `CORRECTION_INVALIDATED(kind=correction_release_invalidation)`, `CREDENTIAL_EXPOSURE_PENDING`, and `CREDENTIAL_EXPOSURE_EFFECT_RECORDED`; separately, only the closed `initial_release_receipt_append` non-event mutation |

`RESULT_MERGED`, `INVALID_PREFIX_MERGED`, and `CORRECTION_MERGE_RECORDED` are the only successful
post-merge admissions. `RESULT_MERGE_INVALIDATED` and `INVALID_PREFIX_MERGE_INVALIDATED` are the
only ordinary-publication failed-admission records. The exact
`CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=merged_invalid)` event is the only correction failed-admission record. Those
six events are the only ordinary admission-specific post-merge main exceptions. Emergency
credential pending/progress and the phase-exact consumers above are separate closed containment
exceptions and cannot authorize successful admission. Their pre-merge plan cannot and
must not claim to know
the eventual merge commit SHA or GitHub-assigned PR number. Instead it binds a deterministic exact
marker, branch/base/head, title/body bytes, protected base ref and base OID, approved head OID,
sealed bundle/result-path roots, deterministic expected merge tree, v1 merge
method `merge_commit`, ordered expected parents `[base_oid, head_oid]`, required-check names and
conclusions, approval/review policy, allowed human merge actor IDs, branch/ruleset digest, and the
permitted current-main containment rule. Only after create-or-adopt discovery does the strict
`PublicationPRReceiptV1` bind the platform-assigned number, node ID, URL, and exact marker/base/head;
post-merge evidence binds that accepted receipt, or the same exact-marker discovery when response
loss prevented its receipt CAS. A caller-supplied, predicted, or pre-intent PR number is forbidden.

After merge, the broker independently constructs `PostMergeAdmissionEvidenceV1` from GitHub and Git
objects, not event input. It proves the PR is merged, its immutable base/head match the plan, the
observed merge commit `M` is the PR's merge commit, `M` has exactly the two ordered parents and
expected tree, all plan-bound checks and approvals applied to the exact head, the merge actor and
method are allowed, and historical protection was enforced. A PR's pre-merge test
`merge_commit_sha` is never accepted as `M`. Historical enforcement requires the
downscoped security-attestor job to fetch the exact repository rule-suite record whose
`before_sha=base_oid`, `after_sha=M`, `ref=refs/heads/main`, actor equals the merge actor, overall
result is `pass` rather than `bypass`, and per-rule active evaluations match the plan-bound ruleset;
reading only current branch rules is insufficient. The attestor persists the complete canonical
suite response immediately because GitHub retains rule-suite history only for a bounded period;
missing late evidence fails closed. The OIDC `ref` remains `refs/heads/main`; its
`sha=workflow_sha=job_workflow_sha=H`, where current main `H` must equal `M` or be a protected
first-parent descendant that contains `M`, leaves the plan-bound result subtree byte-identical to
`M`, and has no intervening commit touching that subtree. The caller and reusable workflow blobs at
`H` must still equal their C0 inventory members. The evidence binds `M`, `H`, PR/base/head, parent
list, tree/result roots, checks, approvals, merge actor/method, branch-protection/ruleset receipts,
exact rule-suite ID/evaluations, GitHub request IDs, and its own digest. Because these GitHub and Git
reads are not a multi-endpoint snapshot, the broker double-reads current main and recomputes
containment after collecting the other evidence; incompatible intervening movement fails closed.
Missing or contradictory
API/Git evidence, absent/bypassed rule-suite evidence, a rebase/squash, changed result subtree, or
noncontained merge is denied.

The aggregates used for publication finality are closed wire records.
`PublicationEligibilityDeliveryResolutionSetV1` has exactly `schema_version`, the same campaign/
registry/publication/attempt/correction/bundle/plan/intent identity, ordered `entries`, and
`eligibility_delivery_resolution_set_sha256`. Each entry has exactly `head_oid` and one class-bound
`eligibility_delivery_resolution_sha256`; entries are complete, sorted by ascending unique head,
and the explicit empty array is allowed only when the credential ledger proves no eligibility token
or dispatch. Its domain is `laconian-publication-eligibility-delivery-resolution-set-v1\n`, omitting
only its final digest.

`ReleaseAuthorizationLedgerEntryV1` has exactly `schema_version`, nested exact
`scope_identity: BrokerVaultScopeIdentityV1(scope_kind="publication")`,
`scope_identity_sha256`, positive gapless `entry_ordinal`, nullable
`predecessor_entry_sha256`, `entry_kind="release_intent_authorized"|"token_request_started"|
"token_request_terminal"|"effect_dispatch_started"|"effect_dispatch_terminal"`, nullable
`release_intent_sha256`, `source_receipt_sha256`, `occurred_at`, and `entry_sha256`. The hash chain,
source-receipt type, start/terminal pairing and time equalities use the exact release-broker
receipts; an intent is nonnull from authorization onward. Its domain is
`laconian-release-authorization-ledger-entry-v1\n`, omitting only its final digest.
`PublicationReleaseAuthorizationLedgerSnapshotV1` has exactly `schema_version`, the same nested
publication scope/digest, ordered nested exact `entries`, nonnegative
`authorized_release_intent_count`, nonnegative `release_write_token_mint_count`, nonnegative
`release_effect_dispatch_count`, `outstanding_request_or_dispatch_count=0`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="release_finalizer")`,
`broker_signature_base64url`, `observed_at`, and `release_authorization_ledger_root_sha256`. Counts
are recomputed from the complete append-only entry array; for publication terminal reconciliation
the exact valid snapshot is an empty entry array and three zeros. The signature/key/validity checks
are the same strict checks as `BrokerVaultAuditLogV1`; its signature and record domains are
`laconian-publication-release-authorization-ledger-snapshot-signature-v1\n` and
`laconian-publication-release-authorization-ledger-snapshot-v1\n`.

`PublicationReleaseInventoryPageReceiptV1` has exactly `schema_version`, the full publication
identity, `repository_id`, `operation_kind="terminal_reconciliation_read"`,
`operation_idempotency_key`, positive `credential_attempt_ordinal`,
positive `operation_request_ordinal`, `publisher_credential_subject_sha256`,
`reconciliation_round=1|2`,
`page_kind="tag_ref"|"annotated_tag_object"|"release_page"|"asset_page"`, nullable positive
`release_id`, positive `page_ordinal`, `query_template`, `request_url`, `request_id`,
`request_dispatched_at`, `response_completed_at`, `transport_terminal_at`,
`api_version="2022-11-28"`, `accept_header="application/vnd.github+json"`,
`authentication_kind="publisher_app_installation_token_vault"`, `response_status=200|404`,
nullable `previous_link`, nullable `next_link`, ordered nested exact `objects`,
`raw_response_sha256`, `canonical_response_sha256`, nested exact
`broker_signing_identity: BrokerSigningIdentityV1(signing_key.broker_role="publisher")`,
`broker_signature_base64url`, and `inventory_page_receipt_sha256`. Each object has exactly
`object_kind="tag_ref"|"annotated_tag_object"|"release"|"asset"`, `object_id`, nullable
`object_type`, nullable `target_oid`, nullable `tag_name`, nullable `release_id`, nullable
`asset_name`, nullable `asset_size`, nullable `asset_digest`, nullable `actor_id`, nullable `draft`,
nullable `prerelease`, nullable `published_at`, and `canonical_member_sha256`; nullability is the
literal GitHub object-kind projection. Page domains and signatures use
`laconian-publication-release-inventory-page-{receipt|signature}-v1\n`.

Tag ref/object reads are single page-one GETs with null Links and exact 200/404 semantics. Release
and asset lists use `per_page=100`, signed GitHub Link chaining, gapless pages and complete stable
cardinality. Every present tag ref is recursively dereferenced through exact `/git/tags/{tag_oid}`
responses until a commit is reached; cycles, missing targets or more than sixteen tag objects fail
closed. The expected result tag must resolve through exactly one annotated tag object when claimed.
Release pages inventory every release; asset pages inventory every asset for every release, not only
a same-name match. Concrete owner/repo and all App/policy/token/request chronology equal the
reconciliation credential subject and generic publisher operation wrapper. Each wrapper has outcome
`read_200|read_404`, source-observation digest equal to this page digest, and exact matching request,
status and times.

`PublicationReleaseInventoryObservationV1` has exactly `schema_version`, the same full identity,
`repository_id`, `operation_idempotency_key`, positive `credential_attempt_ordinal`,
`publisher_credential_subject_sha256`, `reconciliation_round=1|2`, `expected_tag_name`,
`expected_release_name`, ordered nested exact
`page_receipts: PublicationReleaseInventoryPageReceiptV1`, ordered `archive_blobs`, ordered
`tag_ref_and_object_projections`, ordered `release_projections`, ordered `asset_projections`,
`pagination_complete=true`, `archive_complete=true`, ordered `observed_name_conflicts`,
`observed_at`, and `release_inventory_observation_sha256`. Each archive blob has exactly `path`,
`sha256`, and `raw_bytes_base64`; paths are keyed by page digest and decoded bytes reproduce every
page's raw body hash in a bijection. Projections are complete, unique and canonically sorted; each
conflict has exactly `object_kind="tag_object"|"tag_ref"|"release"|"asset"`, `object_id`,
`observed_object_root_sha256`, nullable `actor_id`, and the exact containing page/member digest.
Its domain is `laconian-publication-release-inventory-observation-v1\n`, omitting only its final
digest.

`PublicationReleaseAuthorizationLedgerObservationV1` has exactly `schema_version`, the same
identity, nested exact
`authorization_ledger_snapshot: PublicationReleaseAuthorizationLedgerSnapshotV1`,
`release_authorization_ledger_root_sha256`, nested exact
`release_inventory_observation: PublicationReleaseInventoryObservationV1`,
`authorized_release_intent_count=0`, `release_write_token_mint_count=0`,
`release_effect_dispatch_count=0`, ordered `observed_name_conflicts`,
`observed_at`, and `release_authorization_ledger_observation_sha256`. Each conflict entry has exactly
`object_kind="tag_object"|"tag_ref"|"release"|"asset"`, `object_id`,
`observed_object_root_sha256`, nullable `actor_id`, and `source_observation_sha256`, sorted by kind
then canonical object ID. The three zeros and conflict array are exact projections of the nested
signed ledger snapshot and complete external inventory; every conflict source digest is the nested
inventory's exact page/member digest. Foreign or preexisting same-name objects are retained here;
physical emptiness is neither claimed nor required. Its domain is
`laconian-publication-release-authorization-ledger-observation-v1\n`, omitting only its final
digest.

`PublicationLatestPointerObservationV1` has exactly `schema_version`, the same identity,
`repository_id`, `latest_pointer_path`, `expected_state="absent"|"exact"`,
`observed_state="absent"|"exact"`, nullable `expected_pointer_root_sha256`, nullable
`observed_pointer_root_sha256`, `method="GET"`,
`endpoint_template="/repos/{owner}/{repo}/contents/{latest_pointer_path}"`,
`response_status`, `request_receipt_sha256`, `observed_at`, and
`latest_pointer_observation_sha256`. Expected and observed states byte-equal. `absent` requires two
null roots and authenticated 404; `exact` requires authenticated 200 and two equal nonnull roots
matching the predecessor authority's exact pointer bytes. Its domain is
`laconian-publication-latest-pointer-observation-v1\n`, omitting only its final digest.

`PublicationCanonicalExternalStateV1` has exactly `schema_version`, the same full publication
identity, `authority_parent_oid`, `authority_phase`, nested exact `branch_state`, ordered nested
exact `pull_request_states`, nested exact `check_state`, nested exact
`release_authorization_state`, nested exact `latest_pointer_state`, and
`canonical_publication_external_state_sha256`. `branch_state` has exactly `branch_name`,
`expected_head_oid`, `status="absent"|"exact"|"conflicting"`, and nullable `observed_head_oid`.
Each PR state has exactly the complete marker projection's number/node/url/actor/base/head/state/
merged/merge-OID/closed/merged-time fields in ascending PR-number order. `check_state` has exactly
`set_kind`, nullable `no_guard_reason`, ordered `guarded_head_oids`, and ordered nested exact
`semantic_snapshots: PublicationCheckRunsSemanticSnapshotV1` in head order.
`release_authorization_state` has exactly the three authorization/mint/dispatch counts and the
complete canonically ordered conflict tuples; `latest_pointer_state` has exactly expected/observed
state and pointer roots. Every member is a total deterministic projection of the corresponding five
nested source observations; raw/canonical response hashes, request IDs, credentials, pagination,
signatures and observation/probe times alone are excluded. Its domain is
`laconian-publication-canonical-external-state-v1\n`, omitting only its final digest. A free scalar
digest without this nested recomputable projection is invalid.

`PublicationTerminalReconciliationObservationV1` has exactly `schema_version`, the same identity,
`authority_parent_oid`, `authority_phase`, `reconciliation_round=1|2`, nested exact
`final_branch_observation: PublicationBranchObservationV1`, nested exact
`final_pr_marker_observation: PublicationPRMarkerObservationV1`, nested exact
`final_check_runs_observation_set: PublicationFinalCheckRunsObservationSetV1`, nested exact
`release_authorization_ledger_observation: PublicationReleaseAuthorizationLedgerObservationV1`,
nested exact `latest_pointer_observation: PublicationLatestPointerObservationV1`,
`canonical_external_state: PublicationCanonicalExternalStateV1`,
`canonical_publication_external_state_sha256`,
`outstanding_publisher_write_dispatch_count=0`, `live_publisher_write_token_count=0`,
`broker_phase="terminal_reconciling"`, `observed_at`, and
`reconciliation_observation_sha256`. The no-guard check set derives its absent-branch/zero-marker
proof from these exact nested observations; a `guarded_reconciliation` set names the separate
historical object in `PublicationTerminalGuardSetV1.final_check_runs_observation_set_sha256` and
matches only its stable semantics through fresh reconciliation pages; and a merge-observed set
derives its selected merged head and absence of unmerged candidates from the exact marker/PR reads.
The nested canonical state is the exact projection of all five source components and its duplicated
digest recomputes. This record's `reconciliation_round` equals every generic operation wrapper
`observation_round`, every release-inventory page `reconciliation_round`, and every nested check
observation/page plus marker observation/page `observation_round`; the differently named
fields are literal and never substituted. Only PR-create delivery resolution nests the two-round
`PublicationPRMarkerDiscoveryV1`; terminal reconciliation never nests that aggregate.
`observed_at` is the latest nested authenticated time. Its domain is
`laconian-publication-terminal-reconciliation-observation-v1\n`, omitting only its final digest.

`PublicationNoLaterEffectsEvidenceV1` is the exact no-later root used by initial publication
terminal records and failed admission. It has exactly `schema_version`, the same identity,
`source_authority_parent_oid`, `terminal_authority_parent_oid`, `authority_phase`, nested exact
`terminal_containment_finality: PublicationTerminalContainmentFinalityV1(
finality_kind="ordinary_premerge"|"ordinary_merge_won")`, `terminal_containment_finality_sha256`,
`terminal_containment_intent_sha256`,
`containment_authority_mutation_receipt_sha256`, `containment_authority_oid`,
`successor_merge_denylist_root_sha256`, `terminal_merge_barrier_sha256`, nested exact
`publication_pr_terminal_disposition: PublicationPRTerminalDispositionV1`,
`branch_create_delivery_resolution_sha256`, `pr_create_delivery_resolution_sha256`, nested exact
`eligibility_delivery_resolution_set: PublicationEligibilityDeliveryResolutionSetV1`, nullable
`terminal_guard_set_sha256`, nullable `close_delivery_resolution_sha256`, nested exact
`publisher_credential_disposition_set: PublisherCredentialDispositionSetV1`, nested exact
`first_reconciliation_observation: PublicationTerminalReconciliationObservationV1`, nested exact
`second_reconciliation_observation: PublicationTerminalReconciliationObservationV1`,
`outstanding_dispatch_count=0`, `live_installation_token_count=0`, `observed_at`, and
`no_later_effects_root_sha256`.

For premerge, the nested disposition is the finality's exact `no_pr|closed` source. For merge-won,
the finality source remains its original `no_pr|closed` disposition while the no-later nested
disposition is the independently reconstructed exact `already_merged` member of merge-won
evidence. Every duplicated
intent/CAS/denylist/barrier root recomputes; source parent appears only through the intent, while the
terminal parent equals the current containment authority or a preserving descendant. The barrier
completes before terminal reconciliation begins, and the disposition set's barrier/subset pair
equals it. Both reconciliation observations occur after every possibly delivered branch/PR/check/close write
is classified and after the broker has entered `terminal_reconciling`; their branch, marker, check,
release-ledger and latest-pointer semantic projections hash to the same
`canonical_publication_external_state_sha256`, while their request receipts/times remain distinct
and ordered first before second. The first record and every nested request have round one; the
second have round two. Every round-one request terminal precedes the first round-two dispatch. The unique read-only reconciliation token
is then closed, the broker advances to `sealed`, and the credential set is constructed with zero
live tokens. Its operation and final-observation projections bind both reads. The second observation
supplies the final semantic state and read time; no write-capable token exists during either read
and no token can be minted after sealing. No-later `observed_at` equals the credential disposition
set's authenticated sealed/closure
time, which is not before the second read. All duplicated resolution, disposition, guard, close and identity roots equal the
enclosing record; nullability follows its exact phase/outcome. Foreign release objects may remain
inventoried, but zero protocol authorization, token mint, and dispatch proves no release effect was
caused by this lineage. Its digest is
`SHA256(UTF8("laconian-publication-no-later-effects-evidence-v1\n") || CanonicalJSONV1(record
without exactly no_later_effects_root_sha256))`.
This record requires `publisher_credential_disposition_set.finality_status="stable_read_sealed"`,
a null reconciliation-unavailable receipt and the exact named successful read disposition; the
unavailable branch cannot satisfy its schema.

Successful merge admission closes the same publisher broker before any release authorization.
`PublicationSuccessFinalityEvidenceV1` has exactly `schema_version`, the same full identity,
`authority_parent_oid`, `publication_receipt_kind="initial_pr_receipt"|
"correction_publication_receipt"|"discovery_only"`, nullable `publication_pr_receipt_sha256`,
`pr_create_delivery_resolution_sha256`, `pr_marker_discovery_sha256`, positive
`pull_request_number`, `pull_request_node_id`, `pull_request_url`, `observed_merge_commit_oid`, nested exact
`publisher_credential_disposition_set: PublisherCredentialDispositionSetV1`, nested exact
`first_reconciliation_observation: PublicationTerminalReconciliationObservationV1`, nested exact
`second_reconciliation_observation: PublicationTerminalReconciliationObservationV1`,
`outstanding_dispatch_count=0`, `live_installation_token_count=0`, `observed_at`, and
`success_finality_root_sha256`. Both observations use `set_kind=merge_observed`, name the same exact
merged PR/head/commit, have `publisher_context_state=all_success` with one sole check-run ID, prove
zero release authorization/mint/dispatch, and have equal canonical external state but distinct
ordered authenticated reads. After the second read, the reconciliation token closes and the
complete disposition set advances the broker to `sealed` with zero live tokens; every denied,
permission-mismatched, or retried credential attempt remains inventoried. `observed_at` equals the
set's sealed/closure time and is not before the second read. Its domain is
`laconian-publication-success-finality-evidence-v1\n`, omitting only its final digest.
The disposition set has `finality_status="stable_read_sealed"`, a null unavailable receipt and the
nonnull selected reconciliation-read disposition; unavailable finality cannot satisfy success.
The receipt hash is nonnull exactly for its two receipt kinds and null for `discovery_only`; the
delivery resolution, marker discovery and selected PR identity are always nonnull and byte-equal
the same fields in `PostMergeAdmissionEvidenceV1`, so response/CAS loss cannot make success
finality unconstructible.

`PostMergeAdmissionEvidenceV1` has exactly `schema_version`, `campaign_id`,
`campaign_registry_sha256`, `repository_id`, `intent_kind="initial"|"correction"`,
`publication_id`, nullable `publication_attempt`, nullable `correction_id`, `authority_parent_oid`,
`authority_phase`, `publication_plan_sha256`, `bundle_kind`, `sealed_root_sha256`,
`publication_receipt_kind`, nullable `publication_pr_receipt_sha256`,
`pr_create_delivery_resolution_sha256`, `pr_marker_discovery_sha256`, nested exact
`postmerge_admission_subject: PostMergeAdmissionSubjectV1`,
`postmerge_admission_subject_sha256`, nested exact
`security_attestor_receipt: SecurityAttestorReceiptV1(attestation_purpose="postmerge_rule_suite")`,
`security_attestor_receipt_sha256`, `checks_approvals_root_sha256`,
`github_git_request_receipts_root_sha256`, nested exact
`publication_success_finality: PublicationSuccessFinalityEvidenceV1`,
`publication_success_finality_root_sha256`, `recorded_at`, and
`post_merge_admission_evidence_sha256`. Initial/correction XOR identity follows the publication
plan. Every PR/base/head/M/tree/current-main/actor/time field in the plan, PR discovery, subject,
attestor record and success finality byte-equals; the attestor operation key commits the subject
root and has null admitted-merge receipt. Checks/approval and request roots are exact digest
projections of those nested records. `recorded_at` is the latest nested authenticated/sealed time.
Its domain is `laconian-post-merge-admission-evidence-v1\n`, omitting only its final digest.

`PublicationMergeReceiptV1` has exactly `schema_version`, the same campaign/repository and
initial/correction XOR identity, `authority_parent_oid`, `publication_plan_sha256`,
`publication_receipt_kind`, nullable `publication_pr_receipt_sha256`, positive
`pull_request_number`, `pull_request_node_id`, `pull_request_url`, `observed_merge_commit_oid`,
`observed_head_oid`, `observed_base_oid`, nested exact
`post_merge_admission_evidence: PostMergeAdmissionEvidenceV1`,
`post_merge_admission_evidence_sha256`, `publication_success_finality_root_sha256`, `recorded_at`,
and `publication_merge_receipt_sha256`. Every duplicated field/root byte-equals the nested evidence;
`recorded_at` equals it, and the receipt domain is `laconian-publication-merge-receipt-v1\n`,
omitting only its final digest. Initial `merge-receipt.json` and correction
`corrections/<correction-id>/merge-receipt.json` are exactly this schema; no other merge-receipt
grammar is admissible.

Every successful `PostMergeAdmissionEvidenceV1` and accepted initial or correction merge receipt
contains `publication_success_finality_root_sha256` equal to this exact object. No initial release
preauthorization, correction tag authorization, or successful publication finalization may occur
until that root reconstructs against the admitted `M`; this field is part of the merge evidence,
not a caller-supplied later annotation.

`PostMergeAdmissionFailureV1` is the only failed-admission schema. Its exact ordered fields are:

```text
schema_version
campaign_id
campaign_registry_sha256
publication_id
publication_attempt
correction_id
source_kind
source_authority_parent_oid
authority_parent_oid
authority_phase
publication_plan_sha256
bundle_kind
sealed_root_sha256
publication_receipt_kind
publication_pr_receipt_sha256
pr_create_delivery_resolution_sha256
pr_marker_discovery_sha256
pull_request_number
pull_request_node_id
pull_request_url
pull_request_marker
pull_request_actor
expected_base_oid
expected_head_oid
observed_base_oid
observed_head_oid
observed_merge_oid
current_main_oid
observed_parent_oids
observed_tree_oid
observed_result_root_sha256
merge_actor
merge_method
checks_approvals_root_sha256
rule_suite_observation_root_sha256
github_git_request_receipts_root_sha256
postmerge_security_result
postmerge_admission_subject
postmerge_admission_subject_sha256
security_attestor_receipt
security_attestor_receipt_sha256
security_attestor_failure_evidence
security_attestor_failure_evidence_sha256
failure_kind
terminal_containment_finality
terminal_containment_finality_sha256
successor_merge_denylist_root_sha256
active_publication_terminal_containment_root_before
active_publication_terminal_containment_root_after
selected_merged_candidate_sha256
publisher_credential_disposition_set
publisher_credential_disposition_set_sha256
reconciliation_unavailable_receipt
reconciliation_unavailable_receipt_sha256
release_authorization_ledger_root_sha256
release_authorization_ledger_snapshot
publication_pr_terminal_disposition
protocol_authority_drift_evidence
terminal_exposure_consumption
failed_predicates
no_later_effects_root_sha256
recorded_at
post_merge_admission_failure_sha256
```

`schema_version` is exactly `PostMergeAdmissionFailureV1`. Campaign, registry, publication, plan,
bundle, sealed-root, expected base, and expected head values byte-equal reconstructed authority.
`source_kind` is exactly `normal_postmerge_admission|ordinary_terminal_disposition|write_ambiguity`.
For either containment source the source parent is the intent's pre-containment parent and
`authority_parent_oid` is the current accepted containment parent or a preserving descendant. For
normal postmerge admission the source parent equals the immediate parent and every containment
field is null. `authority_phase` is one of the exact
initial/correction publication phases admitted by the terminal-disposition schema. `correction_id` is
null for either initial bundle, where `publication_attempt` is a positive canonical integer; for a
correction `publication_attempt` is null and `correction_id` is the exact nonempty active ID. A
correction requires `bundle_kind=complete`. `publication_receipt_kind` is exactly
`initial_pr_receipt`, `correction_publication_receipt`, or `discovery_only`.
`publication_pr_receipt_sha256` is nonnull exactly for the first two ordinary kinds and names the
accepted exact authority receipt; it is null for response-loss/pre-receipt discovery and may also
be null for `source_kind=write_ambiguity`. PR create-delivery and marker-discovery roots are
nonnull for ordinary source; ambiguity source may leave either null only when the selected merged
PR is independently authenticated by the containment preflight/inventory/timeline chain. An accepted
receipt embeds the same roots. `pull_request_number` is a positive canonical integer; node ID, URL,
and marker are exact authenticated identities,
and the three merge/current OIDs are lowercase 40-hex Git OIDs. `observed_parent_oids` is the exact
Git-order array of zero through 64 observed OIDs, so an unexpected parent count remains recordable.
`observed_tree_oid` is a Git OID or null; `observed_result_root_sha256` is lowercase SHA-256 or
null. Either nullable observation may be null only with `observation_inconsistent` or
`result_tree_mismatch` as applicable and an authenticated missing/inconsistent observation in the
request-receipt root.
The selected top-level PR is deterministic: ascending `(merged_at,pull_request_number,node_id)`
over the complete nonempty merged-candidate array, and `selected_merged_candidate_sha256` names that
exact first member. The nested containment finality preserves every other merged candidate and
conflicting object; selection never discards one.

`postmerge_security_result` is exactly `not_run|pass|failure`. `not_run` requires all six nullable
subject/attestor fields null and is permitted only when a preceding structural/identity predicate
made an attestor call unauthorized. `pass` requires a nonnull exact
`PostMergeAdmissionSubjectV1`, its duplicated digest, a nonnull exact postmerge
`SecurityAttestorReceiptV1`, its digest, and null failure fields; it is used when a later drift or
containment predicate fails. `failure` requires the same exact subject plus nonnull
`SecurityAttestorFailureEvidenceV1`/digest and null pass fields. Subject M/base/head/tree/actor and
operation key byte-equal the failure observations. No attestor record for another subject, purpose,
repository or publication can enter failed admission.

`pull_request_actor` has exactly `observation_status`, nullable `account_id`, nullable `login`,
nullable `api_type`, and `source_receipt_sha256`. Status is `observed`, `missing`, or `inconsistent`;
the identity triple is nonnull exactly for observed. Expected base/head always equal the plan,
while observed base/head always preserve the authenticated PR and may differ. A bound PR has the
registered publisher actor and equal OIDs; deviations are recordable only with their predicates.

`merge_actor` has exactly `observation_status`, nullable `account_id`, nullable `login`, nullable
`api_type`, and
`source_receipt_sha256`. Status is `observed`, `missing`, or `inconsistent`; the identity triple is
nonnull exactly for `observed`, with a positive account ID and bounded nonblank strings. A
successful admission separately requires the strict human projection; this failure object can
therefore faithfully record a bot, App, unknown API type, or missing actor. `merge_method` is
exactly `merge_commit`, `squash`, `rebase`, or `unknown_or_inconsistent`. The checks/approvals,
rule-suite and GitHub/Git-request fields are nonnull SHA-256 roots of complete canonical
observations, including explicit missing/denied observations rather than omitted keys. For
ordinary/drift/exposure failure sourced from an ordinary disposition, the no-later root is nonnull and exactly
`PublicationNoLaterEffectsEvidenceV1` for this identity/phase; both unavailable objects and their
duplicated digests are null, and `recorded_at` byte-equals no-later `observed_at`. For
reconciliation-unavailable failure, the nested exact `PublisherCredentialDispositionSetV1(
finality_status="reconciliation_unavailable_sealed")` and its exact unavailable receipt plus
duplicated digests are nonnull, the release-authorization root equals the receipt's exact signed
empty ledger, the no-later root is null, and `recorded_at` equals the unavailable receipt/set/
publisher-ledger/vault-log/release-ledger authenticated sealed time. The release-ledger root is null
for every other failure kind. Retry clocks cannot change either form's digest.
For `source_kind=normal_postmerge_admission`, the disposition, no-later and every containment/fence
field are null; `recorded_at` is the deterministic maximum authenticated source time across
`merged_at`, the complete GitHub/Git request-receipt set and the nonnull postmerge security
pass/failure evidence when present. It is never a retry or local-clock time.

`failure_kind` is exactly `ordinary`, `protocol_authority_drift_race`,
`credential_exposure_race`, `reconciliation_unavailable`, or
`publication_write_ambiguity_merge_race`.
`normal_postmerge_admission` forbids the last failure kind and has every containment/fence field
null. `ordinary_terminal_disposition` requires nested exact
`PublicationTerminalContainmentFinalityV1(finality_kind="ordinary_merge_won")`, its digest,
successor denylist, before root equal to the intent digest and after root null; the immediate/source
parents follow that finality, and the terminal CAS preserves the denylist and clears the active
root. `write_ambiguity` is legal only with
`failure_kind=publication_write_ambiguity_merge_race`, nested exact
`PublicationTerminalContainmentFinalityV1(finality_kind="write_ambiguity_merge_won")`, a null
ordinary disposition and null no-later root. Its publisher set is
`write_ambiguity_fenced_sealed`; the nested exact release-authorization snapshot and root have an
empty entry array and zero authorization/mint/dispatch counts. Every ordinary delivery/receipt root
that could not be constructed is null only in this branch, with the selected merged PR instead
authenticated by finality. No branch may clear containment without the finality object.
Reconciliation-unavailable also nests the exact empty snapshot from its receipt. Every other branch
has both release-ledger fields null; a bare root is never accepted.
`publication_pr_terminal_disposition` is either null or the exact
nested `PublicationPRTerminalDispositionV1`; when nonnull its outcome is `already_merged`, its
campaign/registry/publication/attempt/correction/plan, PR identity, expected/observed base/head,
delivery/discovery, mismatch-predicate and merge identities equal this failure, and
`failed_predicates` contains exactly one of `publication_close_lost_to_merge` or
`publication_reopened_after_close`. It is required for every ordinary initial or correction merge
that wins an attempted absence/close terminalization under
`source_kind=ordinary_terminal_disposition`, null for ambiguity, and forbidden for every
`source_kind=normal_postmerge_admission`. A close race can never retain the normal source kind.
`protocol_authority_drift_evidence` is null
except for `protocol_authority_drift_race`, where it is the exact nested
`ProtocolAuthorityDriftEvidenceV1` for the same parent/OID and has the same terminal-disposition
root. `terminal_exposure_consumption` is null except for `credential_exposure_race`, where it is
the exact nested `TerminalCredentialExposureConsumptionV1`; any concurrent drift is represented
only by that consumption's incident evidence and not duplicated in the drift field.

`failed_predicates` is a nonempty deduplicated array in this schema order:
`unexpected_merge_parent`, `unexpected_merge_method`, `pr_identity_mismatch`,
`base_oid_mismatch`, `head_oid_mismatch`, `result_tree_mismatch`,
`checks_or_approvals_invalid`, `merge_actor_invalid`, `historical_rules_invalid`,
`main_containment_invalid`, `workflow_root_mismatch`, `observation_inconsistent`,
`publication_prefix_not_admitted_before_merge`, `publication_close_lost_to_merge`,
`publication_reopened_after_close`, `protocol_authority_drift`, `credential_exposure_race`,
`publication_reconciliation_unavailable`, `publication_write_ambiguity_merge_race`. The
ordinary form forbids the last four predicates and both class-bound
nested emergency objects, requires the active exposure pair null, and may carry an
`already_merged` disposition only with exactly one close-race predicate. Null prior-close receipt
requires `publication_close_lost_to_merge`; nonnull prior-close receipt requires
`publication_reopened_after_close`. Base/head mismatch predicates exactly equal the disposition's
identity-mismatch projection. `publication_prefix_not_admitted_before_merge` is required exactly
for `authority_phase=initial_intent|initial_branch_receipt|initial_pr_receipt|correction_intent` and
proves the missing opened/publication-receipt authority member and event at authenticated merge
time; it is forbidden after admitted initial-opened or correction-publication-receipt authority.
The drift form requires the applicable close-race predicate,
`protocol_authority_drift`, the exact disposition and drift evidence,
and a null active exposure pair. The credential form requires the close-race and credential
predicates, exact disposition and terminal consumption, and atomically consumes the matching
active pair. For an initial complete credential race, the nested incident projects the applicable
`merged_before_close|closed_then_reopened_merged` value and `not_applicable`; for an initial
invalid-prefix race it projects `not_applicable` and the applicable merged value; for a correction both legacy projections are
`not_applicable` while their shared disposition root equals the nested correction-bound record.
Any additional failed predicate must be independently proven.
The reconciliation-unavailable form requires its namesake predicate, the exact sealed unavailable
set/receipt, their exact empty signed release-ledger root, null drift/exposure objects and null
no-later root. It may preserve independently proven
structural predicates, but never claims stable external state, admission or release authority.
The write-ambiguity form requires only its namesake class predicate among the four terminal-class
predicates, exact write-ambiguity merge-won finality, null drift/exposure/disposition/no-later
fields, and the exact empty signed release ledger. Structural predicates remain independently
provable from the selected merge but cannot authorize admission or release.

Canonical bytes are RFC 8785 JSON over exactly those fields, UTF-8 with no terminal newline. The
digest is
`SHA256(UTF8("laconian-post-merge-admission-failure-v1\n") || CanonicalJSONV1(record without
exactly post_merge_admission_failure_sha256))`. Extra, missing, null-where-forbidden, reordered
arrays, mismatched nested identities, success-consistent evidence, or a future event/successor OID
is rejected. Both initial merge-invalidation events and correction `merged_invalid` bind this
exact evidence root for ordinary/drift/exposure admission failure; their reconciliation-unavailable
forms bind its exact failure-only branch and empty signed release ledger. No generic failure record
exists.

For the sixth exception, the broker additionally requires the exact active correction ID and
phase-number lineage; authority parent is exactly that correction's `intent.json` or
`publication-receipt.json`, no valid `merge-receipt.json` or later phase record exists, and the
intent-bound expected plan/PR/base/head/sealed-result-tree roots are preserved separately from the
authenticated observed PR fields. Any mismatch emits its exact predicate rather than overwriting
the expected value. It applies the same
observed `M` and current-main `H` semantics, double-read, caller/callee workflow-root checks, and
request receipts as the other five exceptions, then binds `PostMergeAdmissionFailureV1` and exact
no-tag/no-Release/no-asset/no-latest/no-documentation/no-promotion evidence. Admission authorizes
only the typed `CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=merged_invalid)` authority commit. That commit makes this correction attempt
terminal; only a new correction ID whose intent explicitly supersedes both the failed-correction
root and contaminated `M`/exposure root may continue. The sixth exception cannot authorize a
generic correction invalidation, `unmerged_invalid`, merge receipt, release phase, or any later
effect.

The corresponding merge event and authority receipt record the observed immutable `M` and current
`H`. A failed-admission event records the same immutable observations and exact closed failed
predicates but cannot manufacture `PostMergeAdmissionEvidenceV1`. If exposure starts while the PR
is open and the merge wins the close race, the broker completes the inventoried containment chain
and admits only the race-form failed event; that one CAS consumes the terminal projection and any
matching hold, clears the active pair, records the contaminated merge, and enters the applicable
release-blocked or correction-terminal path. Response-loss recovery may adopt an already merged PR
only by reconstructing the same evidence; it cannot substitute a new merge. Every other main event
retains the strict pre-bound-main-SHA rule.

Paths are fully qualified as above; no other member of the 15-path inventory may call the broker.
The broker verifies the run and reusable caller/callee relationship through the GitHub API and
requires `run_id`, `run_attempt`, and `check_run_id` to resolve to the exact reusable job, exact
caller and callee workflow commits, and exact initial-run actor. On a rerun it separately obtains
the REST `triggering_actor` and requires that login/numeric ID to be plan-authorized; no nonexistent
OIDC `triggering_actor` claim is assumed. It also requires the common workflow root, campaign ID,
caller-allowed event type,
`refs/heads/benchmark-authority/<campaign-id>` target, and expected current OID in the signed token
request. Ordinary STOP authority is the following literal exhaustive table. A comma-separated
reason cell means precisely those literals, each paired with its matching
`OrdinaryStopEvidenceV1` variant; there is no category expansion or wildcard. Every row uses the
listed ref and exact current parent.

| Caller | Parent | Ref | Exact reasons | Evidence |
|---|---|---|---|---|
| `benchmark-batch.yml` | `PREFLIGHTED`, `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, or `JUDGE_ACTIVE` | exact T0 | `provider_authentication_failure`, `provider_permission_failure`, `provider_delivery_ambiguity`, `provider_contract_mismatch`, `reservation_ledger_mismatch`, `batch_identity_mismatch`, `artifact_integrity_failure` | matching strict ordinary variant |
| `benchmark-hard-score.yml` | `GENERATION_COMPLETE` | exact T0 | `generation_context_integrity_failure`, `hard_score_integrity_failure`, `artifact_integrity_failure` | matching strict ordinary variant |
| `benchmark-evidence.yml` | `JUDGE_COMPLETE` | exact T0 | `provider_evidence_incomplete`, `artifact_integrity_failure` | matching strict ordinary variant |
| `benchmark-audit.yml` | `PROVIDER_EVIDENCE_VERIFIED` | exact plan-bound `main` | `audit_identity_failure`, `audit_nonparticipation`, `audit_reveal_failure`, `audit_adjudication_failure` | matching strict ordinary variant |
| `benchmark-analysis.yml` | `AUDIT_COMPLETE` | exact plan-bound `main` | `analysis_statistical_failure`, `analysis_provenance_failure`, `analysis_integrity_failure` | matching strict ordinary variant |
| `benchmark-collect-complete.yml` | `ANALYSIS_COMPLETE` | exact plan-bound `main` | `bundle_coverage_failure`, `bundle_lineage_failure` | matching strict ordinary variant |
| `benchmark-publish.yml` | `BUNDLE_COLLECTED` | exact plan-bound `main` | `publication_lineage_failure`, `publication_reconciliation_unavailable` | matching strict ordinary variant; reconciliation-unavailable requires the exact sealed unavailable receipt/set and active prefix with shared `no_pr` or `closed` disposition; ordinary lineage permits null disposition only when no prefix |
| `benchmark-publish.yml` | `COMPLETE_PUBLICATION_PR_OPEN` | exact plan-bound `main` | `publication_lineage_failure`, `publication_reconciliation_unavailable` | matching strict ordinary variant plus exact shared `closed` disposition; unavailable additionally binds the sealed unavailable receipt/set |
| `benchmark-dismiss-hold.yml` | any prepublication parent allowed above | exact plan-bound `main` | `invalid_event_nondismissible` | matching strict ordinary variant citing the one current hold |

Dismiss-hold has only `invalid_event_nondismissible`; it cannot reclassify a held defect. Every
other ordinary failure named elsewhere maps to one of these literals or is a typed non-STOP
attempt/invalidation outcome. No other predecessor, reason, caller, ref, or evidence union member
exists.

Those ordinary reason grants do not subsume either no-prior-hold exception.
`protocol_authority_drift` has this literal exhaustive caller/current-parent/ref/reason matrix;
every row requires `reason=protocol_authority_drift`, the exact current authority parent, stable
policy projection, fresh double-read/observation receipts, and `ProtocolAuthorityDriftEvidenceV1`:

| Drift caller | Exact current parent | Required triggering ref | Closed reason |
|---|---|---|---|
| `benchmark-batch.yml` | `PREFLIGHTED` | exact T0 | `protocol_authority_drift` |
| `benchmark-batch.yml` | `GENERATION_RESUMABLE` | exact T0 | `protocol_authority_drift` |
| `benchmark-batch.yml` | `GENERATION_ACTIVE` | exact T0 | `protocol_authority_drift` |
| `benchmark-hard-score.yml` | `GENERATION_COMPLETE` | exact T0 | `protocol_authority_drift` |
| `benchmark-batch.yml` | `HARD_SCORE_COMPLETE` | exact T0 | `protocol_authority_drift` |
| `benchmark-batch.yml` | `JUDGE_RESUMABLE` | exact T0 | `protocol_authority_drift` |
| `benchmark-batch.yml` | `JUDGE_ACTIVE` | exact T0 | `protocol_authority_drift` |
| `benchmark-evidence.yml` | `JUDGE_COMPLETE` | exact T0 | `protocol_authority_drift` |
| `benchmark-audit.yml` | `PROVIDER_EVIDENCE_VERIFIED` | exact plan-bound `main` | `protocol_authority_drift` |
| `benchmark-analysis.yml` | `AUDIT_COMPLETE` | exact plan-bound `main` | `protocol_authority_drift` |
| `benchmark-collect-complete.yml` | `ANALYSIS_COMPLETE` | exact plan-bound `main` | `protocol_authority_drift` |
| `benchmark-publish.yml` | `BUNDLE_COLLECTED` | exact plan-bound `main` | `protocol_authority_drift`; null disposition when no prefix, otherwise exact shared `no_pr` or `closed` disposition |
| `benchmark-publish.yml` | `COMPLETE_PUBLICATION_PR_OPEN` | exact plan-bound `main` | `protocol_authority_drift`; exact shared `closed` disposition required |

The table above is the phase-local route when its triggering ref remains runnable. To make moved or
deleted T0/T1 cases reachable, existing `benchmark-evidence.yml` also has a protected-current-main
containment entry for the first 11 parent rows. For every such row its caller is
`benchmark-evidence.yml`, ref is current `refs/heads/main`, reason is only
`protocol_authority_drift`, and evidence is the same parent-specific
`ProtocolAuthorityDriftEvidenceV1`. The two publication rows already run on protected current main
and remain exclusively `benchmark-publish.yml`; they may mint the publisher credential only to
obtain exact `closed`, or use `RESULT_MERGE_INVALIDATED` with
`failure_kind=protocol_authority_drift_race` when discovery yields `already_merged`. The broker
authenticates the actor/run, double-reads current main,
requires the caller and reusable state-CAS workflow bytes at current main to byte-equal their frozen
C0 workflow-root members, independently reconstructs current refs, raw objects, stable policy
projection, sealed binding and registry, and admits only the typed drift STOP CAS for those 11
fallback rows. It cannot emit a success, ordinary STOP, provider or publisher credential,
publication, release, or restored-ref resume. No fallback caller delegates a publication effect.
Thus deletion of the very tag needed by a local row cannot wedge containment.

Post-merge drift has this separate exhaustive protected-current-main matrix; each caller and its
reusable broker job must remain byte-identical to frozen C0 and may perform only the listed terminal
route:

| Drift caller | Exact reconstructed phase | Allowed event only |
|---|---|---|
| `benchmark-release.yml` | `RESULT_MERGED`, before or after initial release intent | `RELEASE_PLAN_INVALIDATED` with exact drift evidence and no exposure consumer |
| `benchmark-publish.yml` | bare `RELEASE_BLOCKED` or bare `RELEASED` | drift-typed `CORRECTION_INTENT_AUTHORIZED` only |
| `benchmark-publish.yml` | active correction `intent.json` or `publication-receipt.json`, before valid merge | publication-family `CORRECTION_INVALIDATED(cause=protocol_authority_drift)` with shared terminal disposition; `already_merged` requires `merged_invalid` |
| `benchmark-release.yml` | active correction at or after valid `merge-receipt.json` | release-family `CORRECTION_INVALIDATED(cause=protocol_authority_drift)` |

Fresh pair reads may prove drift, so these rows do not require the drifted tag ref to trigger. They
require current protected main, exact parent/phase and null active exposure; grant no STOP,
provider call, successful merge/release, correction promotion, documentation, or social effect.
No other caller, phase, or current-main exception exists.

No dismiss-hold caller, alternate scanner, other parent/ref/reason, or wildcard may emit drift
STOP. The generated broker matrix contains each local row and its main fallback exactly once. At
`RESULT_MERGED` or later, the same proof authorizes only the existing release invalidation or
correction path.

After any sealed STOP or `BUDGET_EXHAUSTED`, later pair drift does not wedge safe invalid
publication. Existing `benchmark-finalize-invalid.yml` may run at protected current main, and the
following is the exhaustive continuation matrix:

| Current state | Main-capable caller | Allowed state/effect only |
|---|---|---|
| `STOPPED_INVALID` or `BUDGET_INCOMPLETE` | `benchmark-finalize-invalid.yml` | `INVALID_PREFIX_SEALED` CAS from frozen C0 bytes and archived sealed closure |
| `INVALID_FINALIZED` | `benchmark-publish.yml` | invalid-prefix intent CAS, create/adopt exact invalid branch/PR, record/open CAS, or typed plan invalidation |
| `INVALID_PUBLICATION_PR_OPEN` | `benchmark-publish.yml` | close/invalidate the exact PR or admit the exact protected invalid-prefix merge |

Each invocation still fresh-double-reads both refs and policy. Proven drift selects this narrow
exception: only state-writer CASes and publisher effects necessary for the listed invalid-prefix
lineage may proceed from verified frozen C0 workflow bytes and the archived sealed object closure.
No provider credential, complete-bundle publisher, release, correction promotion, documentation,
social publication, or restored-ref resume is allowed. Temporary inability to read any required
authority produces no token, effect, or state. `benchmark-finalize-invalid.yml` is main-capable only
for the first row, so no new workflow, App, environment, or secret is introduced.

`credential_exposure` has this
separate exhaustive caller/parent matrix; every cell also requires the exact
`CredentialExposureIncidentEvidenceV1` roots and receipts above:

| Credential-incident caller | Exact allowed current parent states | Additional restriction |
|---|---|---|
| `benchmark-batch.yml` | `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE` | affected artifact was uploaded or consumed by the exact current batch plan/run |
| `benchmark-hard-score.yml` | `GENERATION_COMPLETE` | affected generation artifact is an exact hard-score input or scan output |
| `benchmark-evidence.yml` | `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`, `AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, or `BUNDLE_COLLECTED` with no active initial publication prefix | designated cross-phase inventory/scanner; every artifact is already in the current inventory or exact phase plan |
| `benchmark-evidence.yml` | `STOPPED_INVALID`, `BUDGET_INCOMPLETE`, `INVALID_FINALIZED` with no active initial publication prefix, `INVALID_PREFIX_MERGED`, or `INVALID_PREFIX_MERGED_INVALID` | only two-phase pending containment and terminal `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`; preserve the invalid state and permit no live resume |
| `benchmark-audit.yml` | `PROVIDER_EVIDENCE_VERIFIED` | affected artifact is an exact audit input or output |
| `benchmark-analysis.yml` | `AUDIT_COMPLETE` | affected artifact is an exact analysis input or output |
| `benchmark-collect-complete.yml` | `ANALYSIS_COMPLETE` | affected artifact is an exact collection input or proposed bundle member |
| `benchmark-publish.yml` | `BUNDLE_COLLECTED` with an active initial complete prefix, `COMPLETE_PUBLICATION_PR_OPEN`, `INVALID_FINALIZED` with an active initial invalid prefix, `INVALID_PUBLICATION_PR_OPEN`, bare `RELEASE_BLOCKED`, bare `RELEASED`, or an active correction before valid merge | affected artifact is publication-plan/correction bound; prove no PR or close the exact open PR, use merge-race invalidation if merge wins, use terminal supplement for an invalid-prefix lineage, correction intent for bare post-release states, or publication-family invalidation for an active correction |
| `benchmark-release.yml` | `RESULT_MERGED` before or after release intent, or an active correction after valid merge | affected artifact or release object is exact release-plan/correction input; terminalize through `RELEASE_PLAN_INVALIDATED` or release-family correction invalidation |
| `benchmark-dismiss-hold.yml` | every premerge `credential_exposure` STOP parent except `COMPLETE_PUBLICATION_PR_OPEN` and `BUNDLE_COLLECTED` with an active initial-publication prefix | only with the exact current nondismissible hold root and incident evidence independently verified under dismissal approval; no post-merge, correction, or supplement row |

Every matrix row grants its caller exactly `CREDENTIAL_EXPOSURE_PENDING`, zero or more ordered
`CREDENTIAL_EXPOSURE_EFFECT_RECORDED`, and its phase-exact terminal consumer from section 7.4. A
premerge row ends in `PERMANENT_STOP(reason=credential_exposure)`; an invalid terminal row ends in
the supplement; post-merge and correction rows end only through their listed invalidation or
correction intent. For either complete initial-publication prefix, including pre-open
`BUNDLE_COLLECTED`, `benchmark-publish` first seals pending, then proves no PR or attempts the exact
close. No PR or a successful close produces the applicable STOP disposition; a merge that wins
produces `merged_before_close` and race-form `RESULT_MERGE_INVALIDATED`. For either invalid initial-
publication prefix, including pre-open `INVALID_FINALIZED`, the same partition ends in an invalid-
lineage supplement plus typed plan invalidation, or race-form
`INVALID_PREFIX_MERGE_INVALIDATED`.
No cross-workflow delegation or implied event grant exists.

`benchmark-preflight.yml`, `benchmark-finalize-invalid.yml`, both PR validators, and the docs
validator have no credential-incident authority. The matrix grants no
caller a different STOP reason, parent, event, ref, artifact, or App operation. A phase workflow
that merely receives an unbound artifact ID or scanner assertion is denied.

Pull-request refs, branches other than exact `main`, any other tag, a tag/object/commit mismatch,
unlisted callers or called workflows, caller/callee SHA or byte mismatch, an unexpected
`environment`, a different event/job/check-run/actor, and a stale expected OID are denied before
token minting. For every authority mutation, including transition one, the broker itself performs
the universal fresh pair/policy/registry gate immediately before OIDC exchange or App-token mint
and again before receive-pack; a read failure yields no token/ref request/receipt/state, and drift
uses only the exact current-parent matrix. The broker then obtains a single-repository, short-lived
installation token for one fixed state-writer invocation; the token never leaves the broker,
expires within five minutes, and is
discarded immediately after the one expected-OID CAS. Its request ID, raw OIDC
subject/claims, canonical identity projection, App actor, expiry, event kind and STOP reason,
authority ref, expected/new OIDs, and broker decision are recorded in the state receipt. Policy
tests prove an unrelated workflow—even on an otherwise allowed ref—cannot obtain the credential.

#### Authority object and ref protocol

The authority Git identity is the canonical input-tag member
`benchmark/security/state-writer-git-identity.json`, with this exact closed
`StateWriterGitIdentityV1` field set:

```text
schema_version = "StateWriterGitIdentityV1"
state_writer_app_account_id = <positive canonical JSON integer>
state_writer_app_login = <exact case-sensitive installed App bot login>
author_name_ascii = "Laconian Benchmark State Writer"
author_email_ascii = "laconian-benchmark-state-writer@users.noreply.github.com"
committer_name_ascii = "Laconian Benchmark State Writer"
committer_email_ascii = "laconian-benchmark-state-writer@users.noreply.github.com"
state_writer_git_identity_sha256 = <lowercase 64-hex digest>
```

Author and committer name/email bytes are deliberately identical. All four values are the literal
ASCII bytes shown; Unicode normalization, localization, substitution, display-name lookup, or a
GitHub profile email is forbidden. The App account ID is greater than zero and the login is the
exact installed actor login, matching ASCII `[A-Za-z0-9-]+(?:\[bot\])?`; its case is significant.
Every string is valid UTF-8/ASCII and contains no NUL, CR, LF, `<`, `>`, or other control byte.
Canonical bytes are RFC 8785 JSON over exactly the fields above (object input order is immaterial),
UTF-8 with no terminal newline, hashing all fields except the final digest with domain separator
`laconian-state-writer-git-identity-v1`. Missing, extra, null, nonliteral, or digest-mismatched
fields fail closed.

The installed App account ID/login are therefore not obtained from an undefined “App registry.”
Preflight reads this exact member from verified C0, matches its account ID/login against the
repository installation and `StateBrokerCallerPolicyV1`, and requires its digest in the input
registry and as the ordered `security_evidence` protocol-review statement subject. `PREFLIGHT_SEALED`,
every `CampaignEventV1`, publication/correction authority intent, `AuthorityMutationRequestV1`, and
`AuthorityMutationReceiptV1` binds the same digest. A different identity requires a new input tag,
paired companion tag, three new signed statements, bundle, and campaign; no authority ref may mix
identity digests.

Every broker request carries one canonical `AuthorityMutationRequestV1` with a strict three-member
`mutation_kind` union. Its exact ordered common fields are `schema_version`, `mutation_kind`, one
variant source field at that position, `campaign_id`, `campaign_registry_sha256`, `authority_ref`,
`mutation_mode`, `expected_current_oid`, `proposed_tree_oid`, `commit_timestamp`,
`state_writer_git_identity_sha256`, `predecessor_unresolved_hold_root`,
`successor_unresolved_hold_root`, `predecessor_active_credential_exposure_incident_id`,
`successor_active_credential_exposure_incident_id`,
`predecessor_active_credential_exposure_pending_root`,
`successor_active_credential_exposure_pending_root`,
`predecessor_publication_merge_denylist_root_sha256`,
`successor_publication_merge_denylist_root_sha256`,
`predecessor_active_publication_terminal_containment_root`,
`successor_active_publication_terminal_containment_root`, `oidc_run_identity_sha256`, `request_id`,
`idempotency_key`, and `request_sha256`. `schema_version` is exactly
`AuthorityMutationRequestV1`; the ref is the one campaign authority ref; mutation mode is
`expected_absent` or `expected_current_oid`; the expected OID is null only for genesis and otherwise
lowercase 40-hex; proposed tree is a lowercase 40-hex Git tree OID; roots are lowercase SHA-256 or
class-permitted null; timestamps are canonical whole-second UTC; request ID is bounded nonblank and
idempotency key is SHA-256.

For `mutation_kind=campaign_event`, the sole variant field is
`campaign_event_source: CampaignEventMutationSourceV1`, whose exact fields are
`schema_version="CampaignEventMutationSourceV1"`, positive `transition_number`, literal
`event_type`, class-bound nested `event_record: CampaignEventV1`, `event_sha256`, ordered
`required_member_paths`, ordered matching `required_member_sha256s`, `recorded_at`, and
`source_sha256`; its domain is `laconian-campaign-event-mutation-source-v1\n` omitting only
`source_sha256`. Event type/hash/timestamp/transition equal the nested record, and the two member
arrays have identical positive length, canonical path order, and no duplicate.
For `mutation_kind=initial_publication_receipt_append`, the sole variant field is
`initial_publication_receipt_append: InitialPublicationReceiptAppendV1`. For
`mutation_kind=initial_release_receipt_append`, it is
`initial_release_receipt_append: InitialReleaseReceiptAppendV1`. Each variant forbids the other two
source fields and every event/transition alias.

All requests hash exact RFC 8785 JSON with domain `laconian-authority-mutation-request-v1\n`,
omitting only `request_sha256`. Both append variants require `expected_current_oid`, byte-identical
predecessor/successor campaign state, hold, incident-ID, and pending-root values, and their exact
caller/state/path/order gate in section 7.6. The nested append's parent OID, recorded time, and
idempotency key equal the outer expected OID, commit timestamp, and idempotency key respectively.
The broker accepts no caller-supplied packfile, prebuilt commit, arbitrary path, or arbitrary Git
object. It independently canonicalizes every schema record, recomputes its SHA-256 root, fetches and
verifies the exact predecessor tree when one exists, and constructs the candidate Git objects.

The publication roots in every request are transition-authoritative, not advisory. Genesis has a
nonnull successor equal to the canonical empty `PublicationMergeDenylistV1` root, null predecessor
denylist, and both containment roots null. Every ordinary event and both non-event append families
byte-preserve denylist and containment roots. `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` alone may
replace the predecessor denylist by its exact one-entry monotone successor and change containment
`null -> terminal_containment_intent_sha256`. The phase-exact terminal consumer alone may preserve
that successor denylist and change containment `terminal_containment_intent_sha256 -> null` while
nesting matching `PublicationTerminalContainmentFinalityV1`. No request may remove a denylist entry,
install an already-present containment root, clear an unmatched root, or combine either root change
with a non-campaign-event append.

`AuthorityTreeSchemaV1` permits exactly root blob `campaign-state.json` and the optional root trees
`events`, `evidence`, `holds`, `receipts`, `corrections`, `publication`, `incidents`, and
`denylist`. Event files are
`events/<20-digit-transition>-<schema-event-name>.json`; content-addressed evidence is
`evidence/<schema-name>/<lowercase-sha256>.json`; hold, effect-receipt, correction, publication,
and incident
paths are only those required by the current `CampaignStateSchemaV1` event, including the exact
correction members in section 7.5, except for the two separately discriminated section 7.6 non-
event append families. The initial-publication family may append only
`publication/initial/<publication-id>/attempts/<20-digit-publication-attempt>/branch-receipt.json`,
then the same prefix's `pr-receipt.json`. The initial-release family may append only that exact
attempt prefix's `tag-receipt.json`, then
`draft-release-receipt.json`, then `asset-receipts.json`, then `publish-receipt.json`; prefix,
publication ID, attempt, filename, payload class, and predecessor are derived from canonical authority and
cannot be caller-selected. Directories have mode `040000`; every leaf is a regular
non-executable blob with mode `100644`. Symlinks, executables, submodules, duplicate names,
non-UTF-8/NFC names, empty components, and `.` or `..` are forbidden. Entries use Git's canonical
raw-byte tree order. A successor retains every prior numbered/content-addressed entry byte-for-byte.
For `campaign_event`, it replaces only `campaign-state.json` and appends exactly the event-required
new members. Either append kind retains `campaign-state.json` and every prior member byte-for-byte
and appends exactly its one next family-owned receipt path. Deleting or modifying prior evidence is
forbidden; no mutation kind may create a member owned by another, and neither append family may
create an event, terminal member, or state change.

The exposure members are closed: `incidents/<incident-id>/pending.json`, ascending
`incidents/<incident-id>/effects/<8-digit-ordinal>.json`, one
`incidents/<incident-id>/final.json` or `supplement.json`, and
`denylist/provisional/<incident-id>.json` followed by `denylist/permanent/<incident-id>.json`.
Pending appends exactly the pending/provisional pair; progress appends exactly one next effect;
finalization appends exactly final-or-supplement plus permanent denylist and consumes the active
root in `campaign-state.json`. No event may replace/delete these append-only members.

Publication containment members are closed. Preflight appends the canonical empty denylist snapshot
at `denylist/publication/merge/<empty-root>.json`. In addition to replacing
`campaign-state.json` and appending the generic numbered `events/...` member, each
containment-start event appends exactly
`denylist/publication/merge/<successor-root>.json`,
`publication/containment/<intent-root>/intent.json`,
`publication/containment/<intent-root>/containment-start-event.json`,
`publication/containment/<intent-root>/broker-prefix.json`, and
`publication/containment/<intent-root>/vault-prefix.json`; the derived
`containment-start-event.json` intentionally duplicates the generic event blob byte-for-byte so
intent-local recovery does not require a directory scan. The snapshot bytes recompute the
successor root and strictly append the predecessor set. In addition to its state replacement and
generic numbered event member, its exact terminal event then appends exactly
the applicable content-addressed members under that same prefix:
`barriers/<barrier-root>.json`, nullable `write-ambiguity/<fenced-root>.json`, nullable
`merge-won/<merge-won-root>.json`, and required `finality/<finality-root>.json`, plus the ordinary
event-required no-later/unavailable evidence paths. Zero-residual barriers are still stored. Paths,
roots, presence and payload classes are derived from the nested finality union, not supplied by the
caller. Every older denylist snapshot and containment member remains immutable; clearing the active
state field never deletes its evidence.

Blob content is the exact canonical UTF-8 record bytes. Tree content is Git's canonical sequence of
`mode SP name NUL raw-object-id`; commit content is exactly `tree <tree-oid>`, then no parent for the
bootstrap or exactly one `parent <expected-current-oid>` thereafter, then these two exact lines:

```text
author Laconian Benchmark State Writer <laconian-benchmark-state-writer@users.noreply.github.com> <epoch> +0000
committer Laconian Benchmark State Writer <laconian-benchmark-state-writer@users.noreply.github.com> <epoch> +0000
```

`<epoch>` is the identical canonical decimal Unix-seconds conversion of the mutation source
record's whole-second UTC `recorded_at` (`YYYY-MM-DDTHH:MM:SSZ`)—the event for
`campaign_event`, `InitialPublicationReceiptAppendV1` for its append variant, or
`InitialReleaseReceiptAppendV1` for its append variant—with no sign or
leading zero. `AuthorityMutationRequestV1.commit_timestamp` must equal that same source value. The broker clears and
ignores all system/global/local Git config and author/committer environment variables. No
`encoding`, `gpgsig`, `mergetag`, extra identity, continuation, or other commit header is present.
After those identity lines, commit content has one blank line and
`laconian benchmark authority <campaign-id> transition <20-digit-number>: <event-type>` followed by
one newline for a campaign event. An initial-publication append instead uses exactly
`laconian benchmark authority <campaign-id> state <20-digit-current-transition>: initial-publication-<receipt-kind>`
followed by one newline and does not increment the transition. An initial-release append uses exactly
`laconian benchmark authority <campaign-id> state <20-digit-current-transition>: initial-release-<receipt-kind>`
followed by one newline and does not increment the transition.
There is no fourth commit-message grammar. Preflight freezes the repository object format to SHA-1, matching the required
40-lowercase-hex authority OIDs; SHA-256-format repositories are outside v1. It also proves that the
repository already has an ordinary reachable commit, so this protocol never attempts to initialize
an entirely empty GitHub repository. The broker reconstructs every blob, tree, and commit OID from
`type SP decimal-size NUL content` and rejects an extra parent,
extra object, extra tree member, unexpected mode, timestamp, identity, message, or OID.

The broker writes the object closure and ref through Git smart HTTP receive-pack, because GitHub's
REST update-ref body has no expected-old-OID precondition and therefore is not this design's CAS.
The only write transport is discovery
`GET /OWNER/REPO.git/info/refs?service=git-receive-pack` followed by
`POST /OWNER/REPO.git/git-receive-pack`. The broker builds a temporary isolated object database and
an exact pack containing only missing objects reachable from the candidate commit, then sends one
receive command `old-oid new-oid refs/heads/benchmark-authority/<campaign-id>` with report status.
This is the protocol-level equivalent of an explicit full-ref `--force-with-lease`; the old OID is
not inferred from an earlier REST read. For reconciliation the App may use only read-only
`GET /repos/{owner}/{repo}/git/ref/heads/benchmark-authority/{campaign-id}` and exact
commit/tree/blob GETs.

No Git Database REST write, Contents API write, GraphQL mutation, delete command, alternate ref,
tag, ordinary branch, pull request, Release, or other repository endpoint is allowed. The receive
command is rejected unless the candidate is independently verified as a one-parent fast-forward
child after bootstrap; the lease is never used to authorize non-fast-forward history. Pack object
enumeration is exact, thin-pack bases must already be verified predecessor objects, and an
unreachable or extra packed object is forbidden. Content-addressed upload is idempotent: after a
timeout or response loss the broker fetches the expected OID and verifies its bytes before
proceeding; an OID/byte disagreement is a terminal security incident.

For transition one, the request must have `mutation_mode=expected_absent`, null expected OID, event
`PREFLIGHT_SEALED`, transition number one, and a parentless commit. After an absence read, the broker
atomically uploads the exact closure and creates the ref in one receive-pack command whose old OID
is Git's all-zero SHA-1 object ID. A server conflict or lost response is reconciled as exactly one
of: candidate now present and fully reverified, ref still absent and identical request retryable, or
different OID present and terminal bootstrap conflict. No second ref or candidate is created. For
every later transition, the receive command's old OID is
exactly `expected_current_oid`; the candidate is its exact one-parent fast-forward child. A sibling
race fails the server's old-OID comparison. After response loss the broker adopts only if the ref
equals the candidate OID and the candidate has the exact expected parent/tree; if the ref is still
at the expected OID it may retry the identical receive command, and any third OID is a CAS conflict.
No reconciliation path force-moves or rewinds a ref.

Every attempt yields canonical `AuthorityMutationReceiptV1` in the broker's append-only durable
log and as safe workflow evidence. It is the same strict three-member `mutation_kind` union as the
request. Its exact ordered common fields are `schema_version`, `mutation_kind`, the variant fields
at that position, `campaign_id`, `campaign_registry_sha256`, `request_id`, `idempotency_key`,
`authority_ref`, `mutation_mode`, `expected_old_oid`, `ordered_blob_oids`, `ordered_tree_oids`,
`candidate_commit_oid`, `observed_before_oid`, `observed_after_oid`, `outcome`,
`endpoint_policy_sha256`, ordered `github_request_receipts`, ordered nested exact
`final_reconciliation_receipts: AuthorityRefReconciliationReceiptV1`,
`app_actor_id`, `app_actor_login`,
`state_writer_git_identity_sha256`, `oidc_run_identity_sha256`,
`predecessor_unresolved_hold_root`, `successor_unresolved_hold_root`,
`predecessor_active_credential_exposure_incident_id`,
`successor_active_credential_exposure_incident_id`,
`predecessor_active_credential_exposure_pending_root`,
`successor_active_credential_exposure_pending_root`,
`predecessor_publication_merge_denylist_root_sha256`,
`successor_publication_merge_denylist_root_sha256`,
`predecessor_active_publication_terminal_containment_root`,
`successor_active_publication_terminal_containment_root`, `started_at`, `completed_at`, and
`receipt_sha256`. `schema_version` is exactly `AuthorityMutationReceiptV1`; outcome is `created` or
`adopted_exact`; OIDs, roots, IDs, nullability, ref, mode, identity and timestamps match the exact
request and authenticated transport observations.

The `campaign_event` variant has exactly `transition_number`, `event_type`, `event_sha256`, and
`event_member_manifest_root_sha256` as its variant fields. Each append variant instead has exactly
`receipt_kind`, `receipt_path`, and `append_sha256`, with the kind/path/root equal to its nested
initial-publication or initial-release wrapper; it has no event fields. Each
`github_request_receipts` member has exactly positive `ordinal`, `method`, `endpoint_template`,
`request_id`, `dispatch_state="dispatched"`,
`transport_outcome="response_observed"|"response_lost"`, nullable positive `response_status`,
nullable `safe_response_sha256`, and `transport_receipt_sha256`; members are in ascending
gapless ordinal order with no duplicate. `response_observed` requires both response fields nonnull;
`response_lost` requires both null and covers timeout, connection loss or loss after possible
server commit. Every discovery GET and possibly delivered receive-pack POST appears once; no retry
may erase the lost attempt. Blob/tree OID arrays are canonical construction order with no
duplicate. RFC 8785 JSON uses domain `laconian-authority-mutation-receipt-v1\n` and omits only
`receipt_sha256`. It contains no App token, authorization header, raw record payload, or unlisted
transport response.

`AuthorityRefReconciliationReceiptV1` has exactly `schema_version`, `repository_id`,
`authority_ref`, `candidate_commit_oid`, nullable `expected_old_oid`,
`observation_round=1|2`, `method="GET"`,
`endpoint_template="/repos/{owner}/{repo}/git/ref/heads/benchmark-authority/{campaign_id}"`,
`request_id`, `request_dispatched_at`, `response_completed_at`,
`response_status=200|404`, nullable `observed_ref_oid`, nullable
`verified_candidate_object_closure_root_sha256`,
`resolved_state="absent"|"exact_candidate"|"divergent"`, and
`reconciliation_receipt_sha256`. A 404 is only `absent` with both observed fields null. A 200
requires an observed OID; `exact_candidate` additionally requires that OID equal the candidate and
the nonnull closure root reproduce its exact parent/tree/blob bytes, while every other OID is
`divergent` with null closure root. Its domain is
`laconian-authority-ref-reconciliation-receipt-v1\n`, omitting only its final digest. Every mutation
receipt contains exactly rounds one and two with distinct request IDs, every possibly delivered
receive-pack attempt completing before round one dispatch and round one completing before round two
dispatch. The two resolved states/OIDs are equal. `created` requires an observed successful
receive-pack report plus two `exact_candidate` reads; `adopted_exact` requires either a pre-existing
exact candidate or a response-lost/ambiguous write followed by those same exact reads. Absent or
divergent final reads cannot produce an authority mutation receipt.

For either initial append, predecessor/successor state, hold, incident ID, and pending root are
byte-identical. For a campaign event they obey that event's exact transition rules.
For exposure and hold events, the request's nested strict event and
`event_member_manifest_root_sha256` reproduce member paths/digests, incident/hold ID and effect
ordinal; the receipt binds that request/event/manifest and the byte-exact candidate commit rather
than adding undeclared top-level fields.
Crash recovery adopts only the same event or append,
candidate OID, paths, bytes, idempotency key, and external terminal-state observation. A different
ordinal/effect/result is a conflict, never a retry success.
Duplicate request IDs must reproduce the same
candidate and prior OID; conflicting reuse is denied. This protocol provides only exact authority
ref creation/advance, not arbitrary repository write authority.

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
protocol reviewers author and sign, in registry role order, their exact one-statement reviewer
commits; the operator creates the exact annotated T0/T1 tag pair only at its specified point in the
serial construction; the two audit reviewers author their commitment and reveal commits/PRs and
sign adjudication; and maintainers perform environment/deployment approvals, exact-head validation
authorization, protected PR review, and protected merges. These acts use the humans' own GitHub
identities through normal protected repository controls; no human token is injected into a
workflow. Human authorship or approval cannot replace signature verification, an App receipt, or
authority CAS, and no App may substitute for a required human reviewer, approve its own PR, or
merge.

The live secret is a dedicated project-scoped restricted key created for this benchmark campaign,
not an organization/admin key. The project has no unrelated consumers, exposes only the API
capabilities required by the frozen runner, and uses a provider-side project spend guard where
available. The key is revoked or rotated after the campaign and immediately after any incident.

Each provider batch has the exact four-role/job boundary in section 7.2: secret-free prepare,
protected repository-read-only provider, key-free receipt/state writer, and key-free post/state
writer. The prepare job imports and verifies checkpoints, checks the predecessor ledger/STOP state,
constructs `BatchPlanV1`, creates its worst-case reservation, and emits a digest-bound safe input
artifact. The protected provider job checks out exact detached C0 and re-verifies both tag objects,
the sealed `campaign_registry_sha256`, and the plan digest, but its controller step remains disabled
until the receipt/state
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
The universal pending gate applies here in full: a pending incident blocks every ordinary authority
mutation, credential, artifact access/download, publication/release/correction, documentation/social
action, and external effect, not merely provider dispatch and campaign download.

Headers, the API key, raw SDK exception bodies, environment contents, and unrestricted diagnostics
never enter an artifact. The exact key is scanned only inside its ephemeral provider step and is
never written for scanning. If inventory or scanning fails, upload and publication stop. The
security event is retained without reproducing the suspected secret; pattern matching is defense
in depth, not a claim that regex can prove the absence of every secret.

Suspected credential exposure discovered after upload uses only the closed two-phase emergency
lifecycle in section 7.4; its terminal consumer is selected by the exact current authority phase.
The discovering phase workflow or designated
`benchmark-evidence` inventory/scanner reconstructs the exact current state/ledger/inventory/plan/
hold roots, verifies the source upload/run/job and scanner receipts, assigns the incident ID, and
builds safe metadata without retaining suspected bytes. Before **any** revocation/rotation,
quarantine/deletion, artifact-access change, or PR close, the broker uses its existing state-writer
authority and repository-wide lease to append `incidents/<incident-id>/pending.json` plus
`denylist/provisional/<incident-id>.json` by one expected-OID CAS while the campaign state name is
unchanged. `CredentialExposurePendingV1` has exactly `schema_version`, `campaign_id`, `incident_id`,
`parent_state`, `parent_authority_oid`, `current_state_root`, `spend_ledger_root`,
`artifact_inventory_root`, `active_phase_plan_root`, `unresolved_hold_root`,
`concurrent_protocol_authority_drift_evidence_sha256`, `affected_artifacts`,
`scanner_evidence_root`, `provisional_denylist_root`, `pending_effect_inventory`, `created_at`, and
`credential_exposure_pending_sha256`; its domain is
`laconian-credential-exposure-pending-v1`. Its digest is SHA-256 of that ASCII domain plus LF and
CanonicalJSONV1 of the pending record with exactly `credential_exposure_pending_sha256` removed.
There is exactly one incident ID, affected artifacts are
the ascending strict projections defined above, and `pending_effect_inventory` is the canonical
ordered set of credential containment, per-artifact quarantine/deletion/access denial, and exact
publication-PR terminal disposition when an initial or correction prefix may have a PR. That item
uses the closed `no_pr|closed|already_merged` outcome and receipt binding in section 7.4; it is not
an unconditional close. The concurrent drift root is null only when a fresh check proves no
drift. Every entrypoint checks the pending path before provider dispatch or artifact download and
denies both immediately.

Containment then executes each inventoried effect idempotently. After each effect the broker
appends or adopts `incidents/<incident-id>/effects/<ordinal>.json` by expected-OID CAS; response
loss is reconciled against exact external identity and state, never retried ambiguously. Only after
all credentials are terminally contained, artifacts terminally quarantined/deleted or proved
unavailable, access denied, and any required open-PR disposition is terminal does the
phase-exact STOP, supplement, merge/release invalidation, or correction intent/invalidation consume
the pending root and install the final permanent denylist plus
`CredentialExposureIncidentEvidenceV1`. A premerge parent with no merge race uses
`PERMANENT_STOP(reason=credential_exposure)` and enters `STOPPED_INVALID`. Crash injection
after the pending CAS and after every effect or receipt must leave the active pending incident in force; no
restart can restore live authority. If a complete publication PR merges before its close is
observed, the broker records `merged_before_close`, keeps the close receipt null, and uses the
race-form `RESULT_MERGE_INVALIDATED` rather than claiming a premerge close or STOP.

Credential containment has emergency precedence over protocol drift. If drift exists initially or
is discovered during handling, only the pending-incident CAS, typed containment credentials,
inventoried effects, and progress/final receipts remain allowed; the exact
`ProtocolAuthorityDriftEvidenceV1` root is recorded in pending and final evidence and handling does
not switch to a drift-only STOP. Even if T0/T1 moved or disappeared or policy drift prevents the tag
trigger, protected-current-main `benchmark-evidence.yml` may initiate, continue, and finalize this
protocol after authenticating fresh drift receipts and byte-identical sealed C0 caller/reusable
workflow members; it cannot emit an intervening drift STOP or any ordinary effect. Exposure first
discovered in an artifact-bearing invalid lineage creates the same pending incident and denylist,
performs the same idempotent effects, and appends strict `CredentialExposureSupplementV1` via a
`CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED` self-loop. That name is a strict `supplement_kind`
discriminated union, never one record with a nullable opaque drift root.

`ProtocolDriftCredentialExposureSupplementV1` has discriminator
`supplement_kind=protocol_drift_stop` and exactly `schema_version`, `supplement_kind`, `campaign_id`,
`incident_id`, `credential_exposure_pending_sha256`,
`credential_exposure_incident_evidence_sha256`, `original_protocol_authority_drift_stop_root`,
`consumed_active_pending_root`, `terminal_effect_receipts_root`, `recorded_at`, and
`credential_exposure_supplement_sha256`. It is accepted only from `STOPPED_INVALID` whose exact
accepted STOP reason and evidence are protocol drift. Its digest domain is
`laconian-protocol-drift-credential-exposure-supplement-v1` plus LF.

`InvalidLineageCredentialExposureSupplementV1` has discriminator
`supplement_kind=invalid_lineage` and exactly `schema_version`, `supplement_kind`, `campaign_id`,
`incident_id`, `parent_state`, `parent_authority_oid`, `invalid_origin_event_sha256`,
`invalid_origin_evidence_sha256`, `credential_exposure_pending_sha256`,
`credential_exposure_incident_evidence_sha256`, `consumed_active_pending_root`,
`terminal_effect_receipts_root`, nullable `invalid_publication_pr_close_receipt_sha256`,
`recorded_at`, and `credential_exposure_supplement_sha256`. `parent_state` is exactly one of
`STOPPED_INVALID` with a non-drift STOP reason, `BUDGET_INCOMPLETE`, `INVALID_FINALIZED`,
`INVALID_PUBLICATION_PR_OPEN`, `INVALID_PREFIX_MERGED`, or
`INVALID_PREFIX_MERGED_INVALID`. The origin pair maps exactly as follows:
`STOPPED_INVALID -> PERMANENT_STOP`, `BUDGET_INCOMPLETE -> BUDGET_EXHAUSTED`,
`INVALID_FINALIZED|INVALID_PUBLICATION_PR_OPEN -> INVALID_PREFIX_SEALED`,
`INVALID_PREFIX_MERGED -> INVALID_PREFIX_MERGED`, and
`INVALID_PREFIX_MERGED_INVALID -> INVALID_PREFIX_MERGE_INVALIDATED`; the event and its typed
evidence must be accepted ancestors of `parent_authority_oid`. Thus an active initial-publication
prefix binds its underlying invalid-prefix origin plus its exact current parent OID/phase, never a
future supplement. The close receipt is nonnull only for `INVALID_PUBLICATION_PR_OPEN`, or
`INVALID_FINALIZED` with an active initial invalid prefix, when incident disposition is
`closed_before_supplement` and the shared close kind is `publisher_closed`; it byte-equals the
incident-evidence field. For `observed_already_closed` it is null and the incident's shared
terminal-disposition root binds the strict closed observation. It is null otherwise. A
`merged_before_close` invalid-prefix incident
never uses this supplement and terminates through race-form `INVALID_PREFIX_MERGE_INVALIDATED`.
Its digest domain is `laconian-invalid-lineage-credential-exposure-supplement-v1` plus LF.

Both digests use `CanonicalJSONV1(supplement without exactly
credential_exposure_supplement_sha256)`. The pending and final incident roots are ordinary
already-computed inputs, so neither variant is circular. Safe invalid-prefix continuation is
blocked until its applicable supplement resolves. Neither variant permits live resume, provider
access, complete publication, release, correction promotion, documentation, or social effects.
The supplement consumes the exact active progress root, clears the active pair, and requires the
hold root null without creating a second `PERMANENT_STOP` or changing the campaign-state name.

For a complete initial prefix at pre-open `BUNDLE_COLLECTED` or
`COMPLETE_PUBLICATION_PR_OPEN`, the separately approved `benchmark-publish` job exclusively records
the PR terminal-disposition ordinal after pending. `no_pr` is possible only pre-open and ends in
STOP; `closed` records `closed_before_stop` plus either its exact publisher-App receipt or strict
already-closed observation and ends in STOP;
`already_merged` records `merged_before_close`, keeps the close receipt null, and ends in race-form
`RESULT_MERGE_INVALIDATED`. The corresponding invalid initial prefix at pre-open
`INVALID_FINALIZED` or `INVALID_PUBLICATION_PR_OPEN` maps `no_pr|closed|already_merged` to
invalid-lineage supplement plus typed plan invalidation, the same path with
`closed_before_supplement` and its exact close-kind evidence, or race-form
`INVALID_PREFIX_MERGE_INVALIDATED` respectively. No
other credential-incident caller can terminalize these prefixes. If deletion is pending or unavailable at the
STOP CAS, the prefix/STOP finalizer cannot emit `INVALID_PREFIX_SEALED` until it binds a terminal
safe containment receipt containing the final deletion result, continued artifact denylist, and
credential-response receipt. Only the typed progress self-loops and final supplement may update
containment evidence in `STOPPED_INVALID`.

Because retrieval may already have occurred, the event is treated as a disclosure and the campaign
is operationally invalid even if deletion succeeds. Before merge, the safe publication projection
contains only artifact IDs/digests, safe upload and scanner metadata, containment/deletion receipts,
incident timeline, and the safe invalid-campaign record; affected raw bytes are excluded from every
future bundle, PR, and release.

After `RESULT_MERGED`, those bytes may already exist in the protected `main` history, merged PR,
forks, clones, caches, or prior fetches. They cannot be retracted or truthfully described as
“excluded from publication.” The campaign uses `RELEASE_PLAN_INVALIDATED`, rotates/revokes the
credential, preserves branch/tag protections, denies every affected artifact and Git object to
future campaign consumers, publishes an explicit disclosure/incident record naming safe object
IDs but no secret bytes, and authorizes no original tag, release, latest pointer, documentation, or
promotion. A new correction intent must bind the contaminated merge/exposure root and, where safe
removal from the current tree is appropriate, publish a separately reviewed tombstone/removal
commit. That commit changes the current tree only; it does not claim to erase PR transport, Git
history, forks, clones, caches, or prior fetches.

Discovery after `RELEASED` uses the same containment and an append-only correction lineage. The
already published tag/Release/history remains disclosed evidence; the existing latest pointer is
not rewritten. The correction intent immediately appends
`latest_status=withdrawn_due_to_credential_exposure` for consumers while preserving the historical
pointer event; a new pointer appears only when the corrected lineage fully releases. Public messaging
distinguishes the safe replacement projection from the already-exposed transport and history and
links both the incident and superseding correction. Release, correction,
invalid-finalization, invalid-publication, and terminal states cannot emit a new
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
attempts, job and batch-attempt IDs, artifact IDs, detached input/workflow SHAs,
`campaign_registry_sha256`, both tag objects and peeled commits, the exact campaign object closure,
environment deployments, service digests, capsule seals, attachment hashes, audit commitments,
and statistical outputs. It rejects name-based latest lookup, duplicates, superseded attempts,
PR/fork origins, a missing predecessor, or any component that does not reconstruct the sealed
registry. It binds the ordered set of all 36 generation capsules, all 36
`HardScoreRequestSetV1` attachments, and all 36 judge attachments, then creates an
allowlisted bundle artifact whose proposed repository destination is:

```text
benchmarks/results/<campaign-id>/
```

The bundle includes:

- campaign registry record, `ProtocolAttestationTagBindingV1`, and input/result commit identities;
- copied native-v2 manifests, tier- and cache-dimensioned dated price snapshot, and per-batch
  reviewer attestations;
- both independent identity registries; all three canonical protocol-review statements; all three
  ordered verified envelopes; the bundle, attestation root, and bundle digest; frozen REST,
  GraphQL and local-signature projections plus separate signature, double-read, creation-actor, and
  ruleset observation receipts; the 15-member workflow inventory, derived member hashes, and common
  workflow root;
- exact `ProtocolReviewObjectArchiveV1` raw bytes for every T0, C0, tree/blob, Rstat, Rjudge,
  Rsecurity, B0, and T1 closure object plus its deterministic manifest, sufficient for a
  network-free importer to reconstruct every object, tree delta, Git SHA-1 OID, and
  `GitObjectSHA256V1` value offline;
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
- a complete checksum manifest and reproducibility command that verifies the object closure with
  network and credential-access canaries proving that replay performs no API call and reads no
  provider or App secret.

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
bundle kind (`complete` or `invalid_prefix`); `campaign_registry_sha256`; both tag-object and peeled
commit bindings; the protected `main` base SHA; the input commit SHA; the ordered set of every
present commitment, reveal, and adjudication merge SHA; the expected result path and tree diff; the
publication workflow SHA; and the proposed branch name. A complete plan
requires the full audit merge set. An invalid-prefix plan instead binds its exact STOP state and
missing-stage suffix and cannot invent absent audit merges. The base must be current `main`, must
contain the input commit and every present bound merge SHA as ancestors, and must not already contain
the result path. Any base movement or proposed-head change invalidates the plan and requires a new
plan and approval.

The plan's `bundle_kind` and sealed root are mandatory discriminators in every publisher, PR,
validation, merge, collector, and state event. A complete plan may emit only
`PUBLICATION_INTENT_AUTHORIZED` followed by `COMPLETE_PUBLICATION_PR_OPENED` and enter
`COMPLETE_PUBLICATION_PR_OPEN`; an invalid-prefix plan may emit only its typed intent followed by
`INVALID_PUBLICATION_PR_OPENED` and enter `INVALID_PUBLICATION_PR_OPEN`. Required CI checks
reconstruct the discriminator and root from the proposed tree rather than trusting PR labels or
event inputs. Human merge of an invalid-prefix PR emits `INVALID_PREFIX_MERGED` only when admission
succeeds, otherwise `INVALID_PREFIX_MERGE_INVALIDATED`; both outcomes are terminal and safe from
release or promotion, but only the former proves the expected registry lineage. Human merge of a
complete PR may emit `RESULT_MERGED` only with the complete root lineage and post-merge admission
evidence specified in section 7.4; failed admission emits `RESULT_MERGE_INVALIDATED` and enters
`RELEASE_BLOCKED`. Neither path can consume the other's event.

A separately approved `benchmark-publish` environment job runs trusted publisher preparation from
detached C0 with no App credential. It creates a separate worktree rooted at the exact publication
base SHA, rechecks both protected tag refs against the sealed companion binding, verifies the plan,
`campaign_registry_sha256`, bundle digest, workflow root, and inventory, copies
fixed allowlisted paths byte-for-byte, and verifies the exact expected tree diff and sealed commit
root. It first persists the initial publication intent under section 7.6. Only then does its fixed
byte-blind publisher step reruns the universal fresh pair/policy/registry gate and maps the
publisher-App credential; that step accepts only the intent,
object roots, ref, and PR metadata and creates or adopts only the bound branch and pull request.
Every missing receipt is reconciled before state advances. For an invalidated publication it may
instead fail only the exact terminal-guard check on the bound head and close only that exact plan-
bound PR; the sealed publisher permissions attestation permits `checks:write` solely for this one
context and exact terminalization. It must record the typed
`correction_publication_invalidation` or ordinary publication invalidation receipt as applicable.
It does not parse, score, render, execute, or otherwise interpret untrusted model output, and it has
no provider key or state/release App credential. The read-only repository `GITHUB_TOKEN` is not a
publication authority and cannot approve or merge the PR.

The publication job does not merge directly. Normal CI, branch protection, conversation
resolution, exact-head validation, and human review apply. The publication contract requires a
maintainer with write access to verify the exact PR head SHA and sealed bundle digest and authorize
the secret-free `publication-pr-validate` check required by branch protection. The publisher App
cannot approve or merge its own PR. After human merge, the protected acyclic graph
`InitialPreauthorizedResultReleasePlanV1` → passing
`SecurityAttestorReceiptV1(purpose="release_preparation")` →
`ExecutableResultReleasePlanV1(intent_kind="initial")` → `ResultReleaseIntentV1` binds the
campaign, `campaign_registry_sha256`, the single companion binding containing both tag identities,
bundle digest, exact publication PR and approved head, merge commit and result-tree digest, result tag name, release workflow SHA,
common workflow root, and asset digests.
A separately approved `benchmark-publish` release-finalizer job rechecks the plan and prepares the
annotated-tag object and sealed opaque assets before any write token is mapped. The separate
downscoped security-attestor job first passes the universal fresh pair/policy/registry gate before
its OIDC/App-token request, then fetches the supported immutable-Releases setting through
`GET /repos/{owner}/{repo}/immutable-releases`; a false/missing response fails closed. The fixed
byte-blind finalizer step then persists `RESULT_RELEASE_INTENT_AUTHORIZED`, repeats the universal
gate immediately before mapping only the
release-finalizer App write token, accepts the bound intent/tag/release/asset roots, and creates or
adopts the protected annotated `benchmark-result-<campaign-id>` tag at exactly the merge commit,
checksum-bound draft GitHub Release, and exact assets. It reconciles receipts and performs or adopts
one publish transition before `RESULT_RELEASED`.

Post-publish verification uses the returned Release `immutable` field and a pinned, versioned
`gh release verify` invocation over the exact repository/tag/release/assets. The design hashes the
canonical setting response, Release fields, pinned CLI/tool digest and output into
`ImmutableReleaseVerificationV1`; it does not claim GitHub REST returned a raw attestation digest.
The finalizer never rewrites result files and records the annotated tag object, release ID, draft,
asset, publish, and verification receipts. Immutable Releases lock the published tag and assets,
but the design does not claim the feature makes Release deletion or every metadata change
impossible. Tag rules, immediate finalizer-token revocation, scheduled exact release inventory
checks, actor alerts, and state policy forbid those operations and expose residual platform risk;
the read-only `GITHUB_TOKEN` performs none of these writes.

Actions artifacts are temporary review transport, not the durable public record. The committed
result directory and release assets are the publication surface.

Every started confirmatory input tag gets a registry outcome:

- valid positive, negative, and inconclusive campaigns publish full allowed evidence;
- an operationally invalid campaign publishes the reason and non-sensitive provenance without a
  performance claim; and
- credential exposure found before merge publishes only the safe invalid-campaign incident
  projection, while post-merge exposure follows section 12.2 and additionally discloses the
  already-public PR/main/tag/Release object IDs, tombstone/removal status, withdrawn-latest status,
  and superseding correction without claiming historical erasure.

Corrections use the durable intent/receipt/adoption/finalization protocol in section 7.5. They create
a new result directory, protected annotated tag, release, and append-only latest-pointer event with
an explicit `supersedes` lineage; existing evidence, states, commits, pointers, tags, and releases
are not rewritten. A `RELEASE_BLOCKED` lineage creates no original result tag or release; its
correction binds and supersedes the blocked merge explicitly. Publication-stage correction failure
records `correction_publication_invalidation`, including terminal `merged_invalid` when applicable;
release-stage correction failure records
`correction_release_invalidation`; no generic correction invalidation is accepted. A successful
correction binds every persisted publication, merge, tag, and release receipt before the final
`CORRECTION_RESULT_RELEASED` CAS.

### 13.3 Documentation and social claims

Only after `CampaignStateV1` reaches `RELEASED` with an active, nonwithdrawn latest pointer and no
open credential incident may synchronized result sections be added to the six localized READMEs,
`evals/README.md`, the website, changelog, a new release note, and a dated social package.
`RESULT_MERGED`, `RELEASE_BLOCKED`, `INVALID_PREFIX_MERGED`,
`INVALID_PREFIX_MERGED_INVALID`, and
`latest_status=withdrawn_due_to_credential_exposure` explicitly authorize no documentation,
release-note, website, or social promotion. The historical `v0.1.0-alpha.1` release note and alpha
social package remain unchanged.

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
  registry, exact ordered three-entry protocol registry/statements/envelopes, closed verification modes,
  role-specific ordered subject inventories and forbidden fields, numeric-ID/login/signature
  binding and non-null security-evidence fingerprint,
  commitment/reveal PR ordering, adjudication, weighting, agreement, model/arm-indexed false-fail
  sensitivity, quality/brevity extrema, exact-search certificates, and deterministic search-cap
  tests, including `M = K = 120` fail-closed exhaustion;
- exact protocol-review DAG golden vectors fixing every synthetic T0, C0, Rstat, Rjudge,
  Rsecurity, B0, and T1 Git SHA-1 OID and `GitObjectSHA256V1` value; strict
  `ProtocolReviewStatementV1`, mode-discriminated `VerifiedProtocolAttestationV1`,
  `ProtocolAttestationBundleV1`, and post-tag `ProtocolAttestationTagBindingV1` canonical-byte,
  self-digest, new noncolliding ordered-root domain, path, delta, exact raw-header/message grammar,
  `ProtocolReviewObjectArchiveV1` network-free reconstruction, stable ruleset policy, stable
  REST/GraphQL projections, separate observation receipts, signer, and local SSH/OpenPGP
  verification vectors; repeated observations with different times/request IDs/ETags/orderings
  derive identical tag binding/campaign ID/seeds/plans; malformed CanonicalJSON vectors explicitly reject floats, booleans where
  integers are required, numeric strings, non-NFC strings, duplicate keys, reordered arrays, and
  extra or missing fields; negative DAG vectors reject any attestation in C0, any envelope in its
  own reviewer commit, wrong parent, path, role order or companion suffix, extra tree entry/header,
  lightweight/nested/moved/deleted ref, mixed campaign, signature/identity/mode/fingerprint
  mismatch, tag signature, encoding/mergetag/duplicate header, alternate timezone/config/message,
  wrong/changed tag operator, namespace squat, missing or differently authorized creation bypass,
  any update/delete bypass, malformed or
  noncanonical JSON, semantic ruleset drift, missing/archive-inventory-only object,
  raw-object mismatch, or cross-campaign replay;
  exact `TagOperatorRegistryV1` and two-entry `TagRulesetPolicyV1` golden vectors prove stable
  semantic ordering independent of API order and reject zero/duplicate IDs, extra applicable or
  evaluate/disabled rulesets, extra rule, overlap, actor/team/role/App/deploy-key exemption,
  missing/wrong `User/always` creation authorization, or any update/delete bypass;
  `TagCreationRuleSuiteReceiptV1` vectors require one unique historical create suite for each exact
  T0/T1 after OID and reject receipt replay, delete/recreate, zero/nonzero-before mismatch,
  different after OID, wrong/extra actor, ambiguous/multiple suites, or update/delete operation;
  raw-suite mapping vectors require top-level `bypass`/`fail`, matching actor, one active creation
  rule with per-rule `fail`, exclude volatile source name/details, derive rather than invent the
  `User/always` grant, and reject invented per-rule actor/bypass fields;
  digest-preimage vectors remove exactly each named self field and reject circular, wrong-domain,
  or ambient-field hashing; tag lexical vectors reject angle brackets, controls, non-ASCII,
  whitespace ambiguity, signed/zero-padded/out-of-range epochs, alternate timezone, or registry/tag
  disagreement; archived API-blob vectors recompute every raw/canonical response hash including
  both creation suites and reject secret-bearing, missing, reordered, aliased, or mismatched blobs;
  golden vectors fix the exact subjects-array root, five-field local-signature receipt root, and
  three-field 15-member `WorkflowInventoryV1` root; negatives reject implicit fields, wrong order,
  missing/extra member, wrapper/receipt-kind mismatch, embedded self-digest mismatch, or indexed
  blob-hash mismatch;
- exact call-count, default-tier price-snapshot attestation, non-null cache-write rates,
  `BatchPlanV1`, single-use job receipt, distinct cache-read/cache-write
  reservation/reconciliation/evidence, duplicate/rerun rejection, STOP propagation, and
  campaign-budget tests, including a definitely-rejected 429-retry-then-success chain whose
  attempts remain separately accounted and every closed service-tier accounting status;
- schema-generated `CampaignStateV1` transition table and complete state/event/caller/ref/reason/
  evidence/terminal/resumption reachability-liveness matrix, with tests proving every admitted edge
  exists in that one schema, every nonterminal state has a legal continuation, and no broker-only,
  table-only, unreachable, wildcard, or wedged edge exists; parent-hash, atomic invalid-event hold,
  approved dismissal, complete/invalid publication-state separation, terminal
  `INVALID_PREFIX_MERGED`, cross-kind merge/close rejection,
  valid and invalid post-merge admission, `RESULT_MERGE_INVALIDATED` release blocking,
  terminal `INVALID_PREFIX_MERGED_INVALID`, post-merge benign-hold dismissal, hold-to-STOP,
  compare-and-swap race, no-mutation, illegal-jump,
  zero-dispatch recovery, resumable-partial, budget-incomplete, publication-replan,
  release-blocked, correction-intent preauthorization, phase-exact receipt CAS, the four ordered
  state-byte-identical initial-release receipt appends, create/adopt retry,
  PR/merge/tag/draft/asset/publish crash-window reconciliation, atomic
  `CORRECTION_RESULT_RELEASED` escape, terminal correction append, distinct phase-bound correction
  invalidations, the sixth post-merge broker edge for exact typed `merged_invalid` with its
  intent/publication-receipt parent and `PostMergeAdmissionFailureV1`, explicit supersession without
  a wedge, immutable-orphan
  evidence, invalid-finalization, and happy-path property tests;
  canonical golden vectors for `GENERATION_SET_SEALED` require the exact ordered 36 capsule hashes,
  `generation_context_expectation_sha256`, and `verified_generation_context_root`, and reject an
  omitted, extra, swapped, malformed, or independently mismatched root while proving the rendered
  transition table is generated from that same required-evidence schema; credential-exposure
  vectors require the exact safe `CredentialExposureIncidentEvidenceV1`, every allowed premerge,
  post-merge, correction-prefix, and invalid-lineage
  parent, current roots, source upload, scanner and containment receipts, artifact denylist, and
  the exact complete/invalid PR close-or-merge disposition where applicable, and reject every
  cross-kind disposition, reason alias, secret-bearing field, excluded parent, or incomplete receipt;
  protocol-authority-drift vectors cover every literal caller/current-parent/ref/reason matrix row,
  both no-prior-hold exceptions, null-versus-required complete-publication-PR close receipts, and
  prove no wildcard, alternate caller, unreachable edge, restored-ref resume, or post-merge STOP;
  moved/deleted-T0 tests reach every parent through the protected-main `benchmark-evidence`
  fallback using byte-identical C0 workflows, while safe-invalid tests cover
  `STOPPED_INVALID`, `BUDGET_INCOMPLETE`, `INVALID_FINALIZED`, and
  `INVALID_PUBLICATION_PR_OPEN` and reject complete publication, provider, release, correction,
  restored-ref, or temporary-read effects;
  invalid-event tests distinguish pre-auth/transient/benign-sibling audit denial from a single
  hold-worthy authenticated rejection, inject hold-CAS races, verify transition-number/root changes
  without state-name change, exercise exact dismissal, and require
  `invalid_event_nondismissible` as dismiss-hold's sole STOP reason;
  dismissal policy/plan vectors reject unregistered or source-equal actors and prove exact hold
  consumption by dismissal, premerge STOP, result-merge invalidation, or released correction;
  gate vectors admit a nonnull hold only for the four exact atomic consumer classes, require each
  successor to clear the bound predecessor root, restrict held-`RELEASED` correction intent to its
  four typed nondismissible/exposure/invalidation/drift evidence forms, forbid hold admission during
  every nonterminal correction prefix, and require both roots null for every other publication/promotion/release/
  correction/safe-finalization edge;
  the closed 23-value STOP enum and strict reason-specific evidence union have a golden vector for
  every literal caller/parent/ref/reason/evidence row and negative vectors for aliases, mixed
  variant fields, missing source roots, and wildcard grants;
- campaign-binding golden and substitution tests proving `PREFLIGHT_SEALED`, authority genesis,
  every `CampaignEventV1`, `BatchPlanV1`, generation context, provider attachment, collector,
  publication/correction/release plan and receipt accept only the one sealed
  `campaign_registry_sha256`, companion-tag binding, and attestation root, and reject a component
  from any other otherwise-valid pair;
- `StateWriterGitIdentityV1` canonical-byte/digest, input-tag/App-account/security-statement/envelope
  binding, literal ASCII author/committer line, whole-second epoch/timezone, and mixed-digest
  rejection tests; authority-object golden vectors for every permitted tree shape and Git
  blob/tree/commit byte, SHA-1 OID, fixed identity/time/message, parentless bootstrap, exact
  one-parent event successor, and the sole non-event initial-receipt message/state-byte-identical
  successor, proving system/global/local Git config, environment identity, Unicode,
  control bytes, and signature/encoding/mergetag headers cannot change candidate bytes;
  receive-pack policy tests for the all-zero expected-absent creation, expected-current-old-OID
  lease, sibling races, absent/candidate/divergent response-loss reconciliation, duplicate request
  adoption, object-upload interruption, thin-base verification, and rejection of every extra
  object, ref, parent, mode, tree entry, endpoint, method, object format, empty-repository bootstrap,
  malformed status, or conflicting idempotency key; and exact mutation-kind-discriminated
  `AuthorityMutationRequestV1`/`AuthorityMutationReceiptV1` canonicalization tests that reject any
  generic non-state append, event/receipt field mixture, reordered receipt, or active-root change;
- closed retry-taxonomy, `Retry-After`, jitter, retry exhaustion, 401/403 stop, ambiguous delivery,
  soft deadline, forced runner loss, and exact-suffix resume tests;
- tar round-trip, hidden-lock, mode, digest, extraction, traversal, link, overwrite, inventory,
  and secret-scan tests, including cross-phase post-upload detection, deletion pending/unavailable,
  terminal containment before prefix finalization, and zero later campaign download/provider-call
  tests; credential-exposure crash tests inject failure after the pending-incident CAS and after every
  containment effect/receipt, prove immediate provider/download denial and idempotent external-state
  adoption, exercise both complete and invalid-prefix open-PR close/merge races, every pre/post-intent
  release invalidation, bare release-blocked/released correction intent, every correction prefix,
  and every artifact-bearing invalid-lineage supplement; cover exposure-before-drift,
  drift-during-exposure, and exposure-after-drift supplement orderings without restoring live authority; invalid-prefix
  finalization remains blocked until the pending incident/supplement resolves;
  state-schema reachability includes `CREDENTIAL_EXPOSURE_PENDING` and every ordinal
  `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` self-loop for all eligible parents, exact authority paths
  including only provisional/permanent members under the exact `denylist` root tree, and
  predecessor/successor roots, protected-main handling under moved/deleted/drifted tags, final
  pending-root consumption, and denial of every ordinary mutation/effect while pending;
  open-complete-PR drift tests admit current-main `benchmark-publish` only for exposure pending,
  ordered close/effect, and final credential STOP from byte-identical frozen workflows, and reject
  every other publish event under that exception;
  progress-root golden vectors cover empty initialization, ordinal 1, multi-link successors,
  zero-padded paths, predecessor mismatch, pending-root/campaign/incident mismatch and cross-pending
  replay, gap/reorder/replay, terminal chain equality, exact final consumption/clear, and supplement
  construction without a second STOP event; every incident caller row including open-PR close is
  reachable in pending/effect/final order;
- exact 15-path C0-derived workflow inventory/root, trigger, read-only `GITHUB_TOKEN`, four-job
  provider boundary, three distinct App actors, endpoint policy, rulesets, immutable Releases,
  human/App authority separation, OIDC state-broker exact identity projection, fully qualified
  caller/callee references, tag/main `ref`/`ref_type`/`sha` and caller/callee SHA semantics,
  `typ`/`alg`/`kid`/issuer/audience/subject/time/single-use-`jti`, absent-environment and exact
  actor/repository/check-run/rerun-initiator restrictions, minimal reusable-job boundary,
  missing/extra/mismatch, unrelated-workflow, and pull-request-ref denial, token expiry; exact
  downscoped security-attestor token requests proving only Administration/Metadata/Contents read,
  no write scope, and exact rule-suite and immutable-setting endpoints; timely exact authorized-bypass
  rule-suite persistence, pre-merge test-SHA rejection, all six exact post-merge caller/event/phase/
  H/M/evidence allow and deny vectors, including correction `merged_invalid`, and post-merge
  double-read/containment, plus every
  closed phase-specific `PERMANENT_STOP` caller/parent/reason allow and deny vector, including every
  allowed and forbidden credential-incident caller/state pair, per-batch environment approval,
  campaign concurrency, batch-controller ordering,
  universal precredential/preeffect fresh-pair/policy/registry gate for state broker, provider,
  publisher, security attestor, and release finalizer, temporary-read no-token/no-effect/no-state,
  step-scoped-secret, detached-SHA pinning, Markdown neutralization, and exact artifact-provenance
  policy tests;
  main-fallback liveness tests prove the existing protected-main check preserves all 15 frozen
  members for every nonterminal campaign, the validator runs without a tag trigger, fallback bytes
  match C0 at current `H`, and admin-bypassed protection fails closed as the documented limitation;
- schema-generated publication-containment vectors enumerate every exact field once, reject
  duplicate/missing/extra names and noncanonical digest preimages, and cover every source/cause/
  phase/finality/event/nullability row. Failure injection delays each possibly delivered branch,
  eligibility-check, PR-create, terminal-guard and PR-close write until before preflight, between
  the two inventory passes, between CAS and first action, and after terminal-event construction;
  dequeue and rerun receive the same four-boundary schedule. Every lost response remains in the
  subject/disposition/ledger/vault bijection and can end only in stable reconstruction,
  failure-only unavailable sealing, or write-ambiguity fence finality. Generated broker vectors
  also cover ordinal gaps/reuse, executor abort before first/next request, partial-read/failure
  prefix joins including abort between pagination pages, GraphQL
  200-with-errors/null/partial/malformed bodies, all three first-decisive token closure paths, a
  pre-expiry delete whose 204 completes after expiry, response loss after boundary, and zero
  same-token post-boundary dispatch starts;
- queue/denylist containment tests exercise each selector independently (PR node ID, PR number,
  branch, head OID, marker and canonical head trailer), prove the operation-key audit alone grants
  no authority, and reject response-derived queue/check/artifact IDs in pre-mint keys. They inject
  enqueue/dequeue/re-enqueue/close/reopen/merge races, response-lost dequeue, every rerun attempt
  outcome, same-run-ID exact next-attempt fencing, multiple/expired decision artifacts, the
  authenticated-302 plus credential-free ZIP fetch, hostile ZIPs, and zero/duplicate extracted
  decisions. Golden hash-DAG vectors require the one-way dispatch -> signed source -> terminal
  wrapper -> evidence-set order and reject every wrapper/source back-edge. They distinguish the
  old pre-CAS source-success evidence arm from the post-CAS failure/artifact arm, require complete
  workflow-suite-derived check-run pagination and unique selection, and cover both natural new-
  merge-group and authorized-rerun fence removal arms. Two stable global inventory passes, timeline causality, candidate/action-attempt
  partitions, residual-scope exclusions and zero-residual barriers must all recompute;
- containment crash/recovery vectors stop before/after intent construction, signed terminalizing
  prefixes, denylist append/CAS, every queue action, both snapshots, main first-parent walk,
  barrier, fence attachment, sealed set and terminal CAS. They cover benign unrelated main advance,
  side-branch compare members, byte-identical inner/outer first-parent arrays, deterministic
  merge-won-disposition projection from the selected merged candidate, rejection of every
  single-parent/octopus/direct-push advance, affected late merge, exposure already terminal-ready at start,
  exposure detected after start, and fresh protected-main resumption. Every terminal consumer must
  preserve the denylist, clear exactly the matching active root, select the source-class finality
  DAG, and prevent release/documentation/social authority after a late or ambiguous merge;
- read-only provider-evidence verifier, complete-collector ordering, incomplete-prefix finalizer,
  credential-incident schema/canonicalization/quarantine/deletion/revocation/rotation/expiry and
  safe-record publication, `PublicationPlanV1` ancestor/base/head movement and closed-PR replan,
  minimal App publisher, exact-head manual publication-PR validation, the initial
  `InitialPreauthorizedResultReleasePlanV1`/security-attestor/
  `ExecutableResultReleasePlanV1`/`ResultReleaseIntentV1` graph plus
  `CorrectionReleaseIntentPlanV1` coverage, annotated-tag/draft-assets/one-publish release
  finalizer, and correction-lineage tests; exhaustive
  failure injection before and after every initial/correction intent CAS, branch, PR, human-merge
  observation, tag, draft, asset, publish, receipt CAS, authority object upload, and ref update,
  including response loss, already-existing exact adoption, divergent conflict, draft-list
  pagination, 422/502 and `starter` assets, publish-before-final-state recovery, zero duplicate or
  orphan success paths, with response loss around the sixth merged-invalid broker/CAS edge,
  and pinned `gh release verify`/REST-observation parsing;
- post-merge credential-exposure tests proving exact terminal projection construction, active-pair
  and optional-hold consumption, race-form failed admission, pre/post-intent containment,
  correction-prefix terminalization and mandatory supersession, rotation/revocation,
  affected-object denylisting, current-tree tombstone/removal when appropriate, withdrawn-latest and
  correction-lineage behavior, and disclosure of irreversible PR/main/history/fork/fetch exposure
  without an erasure claim or release/promotion continuation;
- authority-bound generation-context expectation reconstruction, no-hash-self-cycle, tagged
  protocol/workflow-root propagation, exact expectation/final-root binding in the schema-canonical
  `GENERATION_SET_SEALED` event and `GENERATION_COMPLETE` record, and rejection of every serialized
  or supplied capability surrogate;
- import- and call-graph tests proving all seven public replay commands are offline and
  non-evidentiary and that every live hard-score, judge, audit, analysis, and verification workflow
  uses the exact Runtime or Publication entrypoint without invoking the public CLI; offline archive
  replay installs network and credential-access canaries and proves it neither reaches GitHub nor
  reads provider/App secrets; and
- a full synthetic campaign that first constructs and verifies the complete
  T0/C0/Rstat/Rjudge/Rsecurity/B0/T1 DAG and then reconstructs the report from published-style
  artifacts without a provider secret.

PR and fork CI remains provider-offline and secret-free: it may fetch pinned actions and locked
dependencies, but it has read-only repository permission and cannot make live model calls.

### 14.2 Live pilot

Before constructing the confirmatory pair, the provider-offline synthetic run first constructs and
replays the complete T0/C0/Rstat/Rjudge/Rsecurity/B0/T1 DAG. The repository then configures and
records the stable policy and active rulesets for both pilot tag patterns. On the frozen pilot C0,
the registered tag operator creates an
annotated pilot T0; the three registry reviewers add and sign their one-statement commits serially;
the verifier creates B0 with only the three envelopes and bundle; and the operator creates the
paired annotated pilot T1. Authenticated actor/rule-suite receipts prove the same registered
operator and exact authorized `User/always` creation bypass for both. Pilot preflight double-reads the two refs, verifies the exact closure and
signatures, seals its own `CampaignRegistryV1`, and only then may a separately labeled operational
pilot run one shared scenario in both languages, all four arms, one repetition, and all three
generation models. At most 24 generation and 24 judge attempts are permitted, under the USD 5 cap.
The pilot freezes `max_transient_retries = 0`, so retries cannot raise the actual API-attempt ceiling
above 48.

The pilot validates API parameters; literal requested and returned `default` service-tier evidence;
returned explicit/`30m` applied-cache-control evidence; separate zero cache-read/cache-write proof
and STOP behavior; returned-model and usage capture; rate behavior; checkpoint transport; judge
schema; and cost accounting. It is never benchmark evidence. The corpus and decision thresholds
cannot be tuned to make the observed pilot effect favorable. A required protocol or implementation
fix creates a new pilot pair, three new reviewer statements and signatures, a new bundle, and a new
pilot campaign identity. Pair-specific statements, reviewer commits, envelopes, B0, T1, and the
post-tag binding from the failed pair are never reused; unchanged content-addressed C0 subobjects
may naturally recur under their identical object IDs. The confirmatory
pair is created only after the implementation is frozen and reverified.

The operational pilot also creates a disposable one-PR merge queue and proves the rollout-specific
containment contract: complete two-pass global queue inventory, observable `LOCKED` entry, exact
dequeue, re-enqueue under a new merge group, and an authorized rerun that retains the workflow-run
ID while producing exactly `source_run_attempt+1`. It verifies that the fresh failed Actions check
removes or blocks the entry, the persistent denylist makes a later merge-group validator fail, and
an unrelated protected-main descendant is accepted only through the separate walk in which every
advance member is the exact rollout-proved two-parent merge-queue commit; a synthetic single-parent
advance blocks rollout.
The pilot captures the real artifact API 302, follows only the allowlisted Location without
Authorization/cookies, safely extracts the unique decision JSON from the bounded ZIP, and verifies
that every required App permission/endpoint works. Any unsupported queue state, missing timeline,
different rerun semantics, artifact redirect contract or same-SHA validator behavior blocks rollout
rather than weakening the protocol.

### 14.3 Confirmatory sequence

The constructive-liveness, credential-finality, and exact-wire gate was satisfied by the 2026-08-31
exact maintainer/user approval of normative commit
`05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`, recorded by this governance-only successor with the
exact message `Одобряю amendment 05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`. Approvals of
`55b90582ae461cf7a3dc072d53d8b03e79fb3614` and
`46147ef62b5bb009421d58928e879d92247d84b5` remain historical evidence for their earlier normative
designs. Implementation may proceed only after plan synchronization; any later normative amendment
repeats the same approval process.

After that exact approval, plan synchronization, and the still-required implementation, the release sequence is:

1. the full provider-offline synthetic campaign, including complete serial tag-pair construction
   and offline object-closure replay, is green;
2. the live operational pilot in section 14.2 is green under its own non-reusable pair;
3. final code, manifests, methods, settings, seeds, price snapshot, both identity registries, exact
   protocol subjects, and `StateWriterGitIdentityV1` are frozen in C0;
4. both final tag-pattern rulesets are active, their stable semantic policy root is frozen, and
   separate trust-boundary observation receipts are recorded;
5. the registered tag operator creates final annotated T0 on C0 and records its authenticated
   exact authorized-bypass creation actor/rule-suite receipt;
6. Rstat, Rjudge, and Rsecurity each add exactly their fixed-path statement and commit-sign it in
   registry order; the verifier requires workflow security, judge/audit, and statistical review to
   be green against the common workflow root;
7. the verifier creates B0 with only the three verified envelopes and bundle delta, and the
   same registered operator creates deterministic paired annotated T1 on B0 and records the second
   authenticated exact authorized-bypass creation receipt;
8. preflight double-reads both refs, verifies the exact object closure, tag rulesets, registry,
   statements, signatures, envelopes, roots, and bundle, constructs
   `ProtocolAttestationTagBindingV1` and `CampaignRegistryV1`, verifies
   `StateWriterGitIdentityV1` against the installed App account ID/login, proves SHA-1 object format
   and a nonempty repository, canonically constructs the literal-identity parentless transition-one
   object closure, and bootstraps the absent authority ref with one all-zero-old-OID receive-pack
   command and an identity-bound `AuthorityMutationReceiptV1`;
9. each required bounded generation batch receives `benchmark-live` approval and runs in order;
10. all generation capsules are sealed, the authority-bound generation-context expectation is
   reconstructed, and `GENERATION_SET_SEALED` atomically binds the exact ordered 36 capsule hashes,
   `generation_context_expectation_sha256`, and `verified_generation_context_root` into
   `GENERATION_COMPLETE`; then the deterministic hard-score/request-set attachments are sealed;
11. each required bounded judge batch receives `benchmark-live` approval and runs in order;
12. generation, hard-score, and judge artifacts pass read-only provider-evidence integrity
   validation and `EvidenceInventoryV1` is sealed;
13. two reviewers complete commit-reveal and adjudication;
14. capsule-bound aggregation classifies every model outcome;
15. the complete read-only collector seals the final bundle from provider evidence, audit, and
    analysis;
16. `benchmark-publish` receives separate approval for the exact `PublicationPlanV1`, first seals
    `PUBLICATION_INTENT_AUTHORIZED`, then maps only the publisher App in the fixed step and creates
    or adopts the exact result branch/PR from the verified main base;
17. a maintainer approves publication-PR validation for the exact head SHA and the reviewed PR
    merges;
18. the read-only attestor promptly persists the exact passing main-merge rule suite and the
    broker double-reads main, reconstructs `PostMergeAdmissionEvidenceV1`, and records the observed
    merge event; failed complete admission enters `RELEASE_BLOCKED`, while failed invalid-prefix
    admission enters its terminal invalid-merge state;
19. `InitialPreauthorizedResultReleasePlanV1`, the passing release-preparation attestor receipt,
    and `ExecutableResultReleasePlanV1(intent_kind="initial")` bind the observed merge commit and
    asset digests; then `ResultReleaseIntentV1` is accepted and
    `RESULT_RELEASE_INTENT_AUTHORIZED` is sealed before any tag/Release effect;
20. the separately approved release finalizer maps only the release App, creates or adopts the
    protected annotated result tag, draft release, and checksum-bound assets, verifies them, and
    performs or adopts one publish transition with every receipt reconciled; and
21. documentation, website, and social result packages are updated from the active, nonwithdrawn
    released lineage.

If a correction PR is observed merged but fails admission, its exact typed `merged_invalid` event
uses the sixth post-merge broker exception, records `PostMergeAdmissionFailureV1` with no later
effects, and terminates that correction attempt. Rollout may continue only through a newly approved
correction ID that explicitly supersedes the failed correction and contaminated merge; it cannot
resume the failed attempt or skip to tag/release/latest/promotion.

From the first provider artifact upload through `COMPLETE_PUBLICATION_PR_OPEN`, every consuming
phase scans its exact inputs and proposed outputs before its success transition; the designated
`benchmark-evidence` scanner may also be dispatched against any exact eligible current-state
inventory. A credential-exposure finding immediately takes the caller/state-specific incident path,
first CAS-installs `CREDENTIAL_EXPOSURE_PENDING` and the provisional denylist, then executes only
the inventoried idempotent effects with one `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` receipt per
effect and advances the deterministic predecessor-linked progress root, and only after the terminal
chain equals the inventory consumes the exact active root through final STOP or supplement.
It then uses only the safe prefix/incident publication path and never resumes the numbered success sequence. A finding after
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
- After a merged PR, tombstone or removal commits can clean the current tree but cannot erase Git
  history, PR transport, forks, clones, caches, or prior fetches. The denylist, withdrawn-latest
  status, incident disclosure, and corrected lineage prevent future campaign use and promotion;
  they are containment and supersession, not retraction.
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
  A broker outage stops state progress; a claim mismatch cannot fall back to a stored App key. Its
  receive-pack implementation, isolated object construction, exact endpoint policy, and durable
  request log are trusted. A failed pack may leave content-addressed unreachable objects in GitHub's
  object store, but never an admitted ref movement; reconciliation records that residual fact.
- GitHub APIs do not offer one universal idempotency header across refs, PRs, tags, and Releases.
  Serialized exact pre-read/effect/post-read adoption closes ordinary and correction crash retries,
  but a conflicting external object terminates through the typed invalidation path and remains
  disclosed evidence rather than being rewritten.
- `github_verified_commit` deliberately trusts the authenticated online GitHub REST/GraphQL
  observations frozen by preflight. Offline replay can prove that the stable projections match the
  archived raw commit and preserved observation receipts, but cannot independently authenticate
  GitHub as their historical origin. SSH/OpenPGP modes additionally retain locally verifiable
  cryptographic evidence and do not have this particular limitation.
- Historical repository rule suites are retained by GitHub for a bounded period, so the read-only
  attestor must persist the exact suite promptly; delayed recovery without that record fails closed.
  GitHub's immutable-Releases feature locks the published tag and assets, but this design does not
  claim the Release object is platform-undeletable or that all metadata is forever immutable.
  Token revocation, tag rules, inventory monitoring, actor alerts, and the public authority record
  mitigate rather than eliminate that platform-administrator risk.
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

- the governance prerequisite is satisfied by this governance-only successor recording the
  2026-08-31 exact approval of normative commit
  `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126` with message
  `Одобряю amendment 05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`; approvals
  `55b90582ae461cf7a3dc072d53d8b03e79fb3614` and
  `46147ef62b5bb009421d58928e879d92247d84b5` remain historical, the implementation plans must be
  synchronized before implementation proceeds, and any later normative amendment requires another
  exact approval;
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
  the schema-generated reachability/liveness matrix has no broker-only, table-only, unreachable, or
  wedged edge; pre-auth/transient/benign-sibling denials cannot create a hold, exactly one
  authenticated hold-worthy rejection can, dismissal clears exactly that hold, and dismiss-hold
  has only the literal `invalid_event_nondismissible` STOP route;
  dismissal uses only the C0-frozen identity policy and strict plan, every nondismissible exit
  consumes its exact hold root, and safe finalization requires no unresolved hold or pending
  credential incident; dismissal OIDC/rerun actors are caller-discriminated from normal operator
  dispatch and bind the exact authorized dispatcher fields; a nonnull hold is admitted only by the
  four exact atomic consumer classes, each clears its bound predecessor root, held `RELEASED`
  correction intent is discriminator-restricted, and every other gated edge requires both roots
  null;
  complete and invalid publication PRs occupy distinct states, only a complete sealed-root lineage
  can reach `RESULT_MERGED`, both invalid-prefix merged outcomes are terminal and cannot release or
  promote, and an already-merged complete PR that fails admission reaches `RELEASE_BLOCKED`;
  the sole `RELEASE_BLOCKED` escape is an atomic `CORRECTION_RESULT_RELEASED`, a correction from
  `RELEASED` only appends terminal history, every correction external effect is preauthorized and
  receipt-reconciled/adoptable after crashes, `merged_invalid` terminates and can be explicitly
  superseded rather than wedging, the exact typed merged-invalid event is reachable only as the
  sixth post-merge main exception from its correction intent/publication-receipt phase with
  `PostMergeAdmissionFailureV1` and no-later-effects evidence, and the two phase-bound correction
  invalidations cannot alias;
- every active publication/correction prefix terminalizes only through
  `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` and its matching
  `PublicationTerminalContainmentFinalityV1`; request/receipt/tree schemas prove the monotone
  denylist append and active-root `null -> intent -> null` CAS sequence. Signed broker/vault
  prefixes, arbitrary-delay write-ambiguity subjects, two-pass global queue inventory, typed
  dequeue/timeline/rerun attempts, Actions-validator fence evidence, the authenticated-302/
  credential-free bounded-ZIP artifact chain, two post-action snapshots and safe main first-parent
  walk are complete and bijective. Premerge and merge-won DAGs are disjoint, residual barriers
  exclude exactly preserved merged candidates, token closure proves zero same-token dispatch starts
  after its first-decisive boundary, all terminal consumers preserve the denylist and clear only the
  matched root, and late/ambiguous merge can never authorize release, docs, website or social output;
- every authority mutation is constructed by the broker from exact schema bytes into the closed
  SHA-1 blob/tree/commit shape, transition one uses a parentless commit and all-zero-old-OID
  expected-absent receive-pack creation, every successor uses the exact expected old OID and
  one-parent fast-forward child, response loss reconciles only absent/exact/divergent outcomes, and
  no extra object, ref, parent, tree member, mode, endpoint, or REST pseudo-CAS is admitted; the
  input-tag `StateWriterGitIdentityV1` fixes the literal ASCII author/committer name/email bytes,
  exact installed App numeric ID/login and digest, appears in the ordered security statement,
  verified envelope, and every event/intent/request/receipt, and candidate construction ignores Git
  config/environment and
  forbids alternate identity, control/Unicode bytes, signature/encoding/mergetag headers, timestamp,
  or timezone;
- every post-upload `credential_exposure` STOP uses the canonical safe
  `CredentialExposureIncidentEvidenceV1`, reproduces the exact current authority/state/ledger/
  inventory/plan/hold roots and affected upload/run/job, binds the closed secret classification,
  scanner verification, credential containment, quarantine/deletion and no-further-campaign-
  download receipts, closes an open complete PR with the publisher App before STOP, and is accepted
  only after its broker-CAS pending incident/provisional denylist and every terminal idempotent
  containment receipt; crash recovery cannot reopen provider/download authority, merge races use
  postmerge invalidation/correction, concurrent drift is recorded while exposure containment wins,
  and exposure after drift STOP uses the two-phase terminal supplement that blocks invalid-prefix
  finalization until resolved; pending/progress are explicit expected-OID self-loop events with
  append-only authority members, deterministic predecessor-linked progress roots, crash-adoptable
  receipts, complete-inventory terminal chain, and final exact-root consumption; every incident
  caller/ref row reaches pending, progress, and final handling, including publisher-only PR close;
- the exact two-entry audit registry and exact three-entry ordered protocol registry bind numeric
  IDs, logins, closed verification modes and fingerprints, the security-evidence fingerprint is
  non-null, every role has exactly its ordered required subject inventory and no forbidden field,
  the three ordered statements/envelopes/root verify, and neither registry can substitute for the
  other;
- C0 and `CampaignInputPackageV1` contain no protocol-review statement, envelope, attestation root,
  or companion binding; T0 and T1 are annotated-only protected deterministic pairs; the exact
  serial C0/Rstat/Rjudge/Rsecurity/B0 topology, one-parent fixed-path reviewer deltas, B0-only
  three-envelope/bundle delta, exact raw tag/commit header and canonical-message grammar, strict
  CanonicalJSON schemas, stable REST/GraphQL projections, separate transport receipts, local
  keyed-signature verification, same frozen tag operator with exact authorized-bypass create receipts, and
  every Git SHA-1/raw-object SHA-256 golden vector verify; the exact one-operator registry and
  exactly two active disjoint rulesets have stable semantic order, each tag has a unique nonreplayed
  historical creation-suite receipt proving the sole frozen `User/always` authorization, and
  preflight double-reads both refs and exact
  closure, verifies the stable policy root with fresh separate receipts, and rejects movement, deletion,
  substitution, mixed campaigns, wrong identity/path/parent/order, malformed bytes, missing objects,
  or repair in place;
  every new registry/policy/receipt/archive digest has an exact noncircular domain-separated
  CanonicalJSONV1 preimage, every archived API response hash recomputes offline from safe bytes,
  and tagger identity/epoch bytes satisfy the one closed lexical grammar; subjects, local signature
  verification, and the exact 15-member workflow inventory reproduce their specified roots;
- `ProtocolAttestationTagBindingV1` originates only in preflight/authority evidence as live
  authority and is copied downstream only through the sealed registry; canonical
  `CampaignRegistryV1` derives campaign ID from its payload and binds T0/C0, all three reviewer
  commits, B0/T1, signatures, bundle/root, workflow and stable ruleset policy; observation metadata
  cannot change identity; `campaign_registry_sha256` is
  unchanged in authority genesis, every event and `BatchPlanV1`, generation context, provider/audit/
  analysis evidence, collector, publication/correction/release records, and exact-byte
  `ProtocolReviewObjectArchiveV1`, whose network-free importer reconstructs every closure object;
- the exact ordered 15-path workflow inventory derives its member hashes and common root only from
  verified C0 bytes, and protocol statements/envelopes, generation context, provider projection, and
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
  credential-incident matrix, all six exact post-merge main exceptions including correction
  `merged_invalid`, and denies every unrelated workflow, ref, identity,
  missing/extra/mismatched claim, predecessor, reason alias, artifact, or event; App/provider
  credentials are mapped only in their fixed, separately authorized boundaries with no
  provider-key/model-output overlap; the same exactly-three-App topology supplies a separately
  downscoped, read-only Administration/Metadata/Contents security-attestor token whose returned
  permissions and exact rule-suite/immutable-setting reads are receipt-bound and contain no write
  scope; every provider/App/OIDC credential and external effect is preceded by the universal fresh
  pair/policy/registry gate, temporary read failure creates no token/effect/state, and every
  premerge drift edge uses the literal exhaustive matrix and typed evidence/close receipt while
  post-merge drift uses only release invalidation or correction; moved/deleted-tag containment is
  reachable from every live prepublication state through the existing main-trigger evidence
  workflow, and only the frozen-closure safe-invalid matrix may continue after any sealed STOP or
  budget invalidity, with no new App, workflow, environment, or secret; reachability assumes the
  existing protected-main check preserves all 15 C0 workflow members while campaigns are live and
  fails closed if platform administration bypasses that invariant;
  at an open complete-publication PR under proven drift, current-main `benchmark-publish` admits
  only exposure pending/effect, publisher-only close, and final credential STOP from byte-identical
  frozen workflow members;
- serial protocol-reviewer statement commits, audit-reviewer commits/PRs, tag-operator acts,
  maintainer validations/approvals, and protected human merges remain distinct human authorities
  and cannot be replaced by any automated App or workflow;
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
- `PublicationPlanV1` starts from exact current `main` containing every bound audit merge; durable
  initial intent precedes each branch/PR and release effect; the publisher App creates, adopts, or
  closes only its exact plan-bound branch/PR; post-merge admission independently proves the exact
  protected merge commit/tree/parents/actor/checks/approvals and timely passing main-merge rule
  suite while permitting only a verified first-parent current-main descendant with unchanged result
  subtree; the exact initial preauthorized/attested/executable release-plan graph binds that
  observed merge tree (and `CorrectionReleaseIntentPlanV1` does so for correction), and the release App creates or
  adopts only the protected annotated tag, verified draft/assets, and one publish transition;
  every response-loss window is receipt-reconciled, base/head movement has an exact closed-PR replan
  transition, and a verified post-merge defect takes its typed terminal or release-block path;
- documentation, website, release-note, and social updates are impossible before `RELEASED` and
  remain forbidden for `RESULT_MERGED`, `RELEASE_BLOCKED`, `INVALID_PREFIX_MERGED`, or
  `INVALID_PREFIX_MERGED_INVALID`; a post-merge credential incident withdraws latest, contains and
  discloses the affected objects, and uses a tombstone/corrected lineage without claiming that Git
  history, PR transport, forks, clones, caches, or prior fetches were erased;
- endpoint-policy tests, actor restrictions, receive-pack expected-old-OID receipts, historical
  exact creation-bypass and passing main-merge rule-suite evidence, protected rulesets, canonical immutable-setting/Release observation,
  and pinned `gh release verify` evidence constrain the technically broader App permissions, and no
  workflow token can approve or merge a PR;
- protected annotated input/companion/result tags, all three App installations, the state-broker OIDC/claim policy,
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
- [Git receive-pack protocol](https://git-scm.com/docs/gitprotocol-pack.html)
- [GitHub Git references API](https://docs.github.com/en/rest/git/refs)
- [GitHub Git commits and verification object](https://docs.github.com/en/rest/git/commits)
- [GitHub GraphQL `GitSignature`](https://docs.github.com/en/graphql/reference/git#gitsignature)
- [GitHub rules available for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub repository rule suites](https://docs.github.com/en/rest/repos/rule-suites)
- [GitHub immutable-Releases setting](https://docs.github.com/en/rest/repos/repos#check-if-immutable-releases-are-enabled-for-a-repository)
- [GitHub list Releases, including authenticated drafts](https://docs.github.com/en/rest/releases/releases#list-releases)
- [GitHub published Release lookup by tag](https://docs.github.com/en/rest/releases/releases#get-a-release-by-tag-name)
- [GitHub upload a Release asset](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset)
- [GitHub immutable Releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
- [OpenAI project and restricted-key controls](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform)
- [OpenAI Responses create API reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [OpenAI prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- [OpenAI GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [OpenAI GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [OpenAI GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
