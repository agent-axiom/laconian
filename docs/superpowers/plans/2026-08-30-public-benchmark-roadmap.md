# Public Three-Model Benchmark Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver, secure, rehearse, execute, audit, and publish the approved GPT-5.6 Sol/Terra/Luna benchmark without allowing incomplete evidence, uncontrolled spend, or premature public claims.

**Architecture:** Four executable implementation slices establish the serial Git-native protocol-review DAG `T0 -> C0 -> Rstat -> Rjudge -> Rsecurity -> B0 <- T1` and a separate fail-closed campaign control plane. Evaluation/Audit first bootstraps the sole CanonicalJSONV1 attachment primitives imported by Foundations; Foundations then own the exact OpenAI request/evidence wire and sealed capsules. Evaluation/Audit also owns statements, verified envelopes, bundle/tag binding, raw-object archive, and offline replay. Runtime owns the authority schema, external OIDC broker, shared initial-publication/release wire, state-bound terminal-containment primitives, hold/drift/exposure state, provider controller, and three live evaluation methods. Publication imports those shared/state-bound types by object identity and owns the remaining terminal-containment algorithm/evidence, four live methods, and all operational branch, PR, merge, release, correction, and promotion effects. Live operations begin only after every code, GitHub, broker, provider-key, and pilot gate passes.

**Tech Stack:** Python 3.11+, Pydantic 2, OpenAI Python SDK 3.3.1, NumPy PCG64, pytest/Ruff/mypy, GitHub Actions with full-SHA pins, OpenAI Responses API, strict CanonicalJSONV1, SHA-256 evidence, canonical Git SHA-1 objects, smart-HTTP receive-pack leases, descriptor-safe capsule/tar I/O, and protected Git tags/Releases.

---

## Sources, approval, and fixed scope

- Normative design: `docs/superpowers/specs/2026-08-30-public-three-model-benchmark-design.md`.
  The general approved baseline is `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`; the approved
  Foundations preflight amendment is `e67ad191623316f69523b051fba48ec2e7492493`; and the approved
  shard-checkpoint authority and bounded-directory amendment is
  `36bdcf7467ddd68543a024a1fb9a058f6c865a0d`.
- Approval metadata: governance-only successor `d6b147aefb0bab0e64a41541a67e2c1b8f4d00ad`
  records the exact approval of `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`; governance-only
  successor `6930b6e18b11d50a4df5b5fd18d37207e891a28c` records the exact approval of
  `e67ad191623316f69523b051fba48ec2e7492493`. Both remain historical authority for their approved
  scopes.
- Checkpoint amendment approval metadata: on 2026-09-01 the maintainer/user explicitly approved
  normative commit `36bdcf7467ddd68543a024a1fb9a058f6c865a0d` with exact message
  `Одобряю amendment 36bdcf7467ddd68543a024a1fb9a058f6c865a0d`. This governance-only successor
  records that approval without changing normative behavior. Foundations Tasks 10–12 and affected
  Runtime Tasks 6, 7, 9, and 10 may proceed only from a handoff that records this successor's future
  full SHA as `PLAN_BASE_SHA`; the roadmap does not invent or embed that SHA.
- Pending protocol-signature evidence amendment: receipt-hash-only prefix inputs are replaced by
  exact source-bearing REST/GraphQL/local-verifier evidence and network-free replay of the same
  derivation. Evaluation Task 3's protocol-review acceptance path and all downstream consumers of
  its verified prefix/DAG/archive capabilities remain blocked from commit/merge as complete until
  the exact amendment commit is separately approved and governance-recorded.
- Historical prior approvals: normative commits `55b90582ae461cf7a3dc072d53d8b03e79fb3614` and `46147ef62b5bb009421d58928e879d92247d84b5`, recorded respectively by `983471c1557a58a80065406e3a346e00c80f2aa3` and `0e2981e32b5d8982e78c73a5e413b36e2b1495e9`, remain evidence only for their superseded designs.
- Milestone 0 is complete. Slice implementation starts only after the synchronized roadmap plus four slice plans are committed and that already-created commit is recorded at handoff as `PLAN_BASE_SHA`. Any later normative design amendment re-blocks every affected task until separately and explicitly approved.
- Generation model IDs are exactly `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`; returned provider model IDs are recorded separately and must be consistent per requested-model campaign, not textually equal to the requested ID.
- Primary contrast is `concise - if`, independently per model. The plan is 3 models × 12 scenarios × 2 locales × 4 arms × 5 repetitions = 1,440 responses, projected into exactly 36 ordered 40-row shards.
- Full authorized request exposure is USD 75. Pilot exposure is USD 5 with at most 24 generation and 24 judge attempts and no retry.
- Promotion requires an active, nonwithdrawn latest pointer at `RELEASED`, null `unresolved_hold_root`, null active credential-exposure incident/progress fields, and no open incident or correction. `RESULT_MERGED`, `RELEASE_BLOCKED`, `INVALID_PREFIX_MERGED`, and `INVALID_PREFIX_MERGED_INVALID` never authorize a release claim, documentation, presentation, website, release note, or social post.

## Plan set and dependency graph

```text
Approved design 05e3d7ba/e67ad/36bdcf7 + governance successors d6b147a/6930b6e/this successor
    |
    v
Synchronized five-plan bundle recorded as PLAN_BASE_SHA
    |
    v
Slice 2 Task 1 — canonical attachment bootstrap
    |
    v
Slice 1 Tasks 1–9
    |
    v
Approved checkpoint amendment 36bdcf7 + this successor recorded as PLAN_BASE_SHA
    |
    v
Slice 1 Tasks 10–12 and affected Runtime Tasks 6/7/9/10
    |
    v
Exact protocol-signature evidence amendment approval + governance successor recorded as PLAN_BASE_SHA
    |
    v
Evaluation Task 3 protocol-review prefix/DAG/archive acceptance and downstream consumers
    |
    v
Interleaved Slice 2 Tasks 2–15 and Slice 3 Runtime at their explicit interface gates
    |
    v
Slice 4 — Publication
    |
    v
Offline reconstruction + two independent reviews
    |
    v
External trust setup -> live pilot -> confirmatory campaign -> human audit/merge/release
    |
    v
Post-RELEASED documentation, presentation, and social package
```

Detailed plans:

This roadmap is a non-executable orchestration index. The four slice plans below are the executable
`superpowers:writing-plans` documents and contain the bite-sized RED/GREEN/commit steps.

1. `docs/superpowers/plans/2026-08-30-public-benchmark-foundations.md` — 12 tasks.
2. `docs/superpowers/plans/2026-08-30-public-benchmark-evaluation-audit.md` — 15 tasks.
3. `docs/superpowers/plans/2026-08-30-public-benchmark-runtime.md` — 10 tasks.
4. `docs/superpowers/plans/2026-08-30-public-benchmark-publication.md` — 15 tasks.

## Milestone 0: Approved protocol/security contract — complete

- [x] Amend and independently review the normative design.
- [x] Bind literal `service_tier: "default"`, literal `prompt_cache_options: {"mode":"explicit","ttl":"30m"}`, recursive absence of `prompt_cache_breakpoint`, distinct cache-read/cache-write evidence and pricing, exact returned response paths and status vocabularies, SDK 3.3.1/`uv.lock`, and the `<=272_000` conservative input bound.
- [x] Bind the two-person audit registry, ordered three-person protocol registry, strict `ProtocolReviewStatementV1`, mode-discriminated `VerifiedProtocolAttestationV1`, `ProtocolAttestationBundleV1`, `ProtocolAttestationTagBindingV1`, serial reviewer commits, raw-object archive, authority-only in-memory generation capability, and exact generation seal roots.
- [x] Bind `CampaignStateSchemaV1`, external OIDC state broker, canonical Git object/receive-pack
  lease protocol, `StateWriterGitIdentityV1`, exactly three Apps, protected one-entry merge-queue
  admission, the separate `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` current-main authority row,
  active-containment root and append-only successor merge denylist, terminal guard/dequeue/fence
  barriers, durable initial/correction intents and receipts, the six post-merge success/failure
  exceptions, invalid-event holds/dismissal, protocol drift, two-phase credential-exposure progress,
  preauthorized/attested/executable release planning, closed broker-token finality, invalid-prefix
  terminality, and seven-offline/seven-live entrypoint isolation.
- [x] Receive explicit maintainer approval for normative commit `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`; record it without changing normative behavior at governance successor `d6b147aefb0bab0e64a41541a67e2c1b8f4d00ad`.
- [x] Receive explicit maintainer approval for Foundations normative commit
  `e67ad191623316f69523b051fba48ec2e7492493`; record it without changing normative behavior at
  governance successor `6930b6e18b11d50a4df5b5fd18d37207e891a28c`.

## Plan synchronization gate

- [ ] Receive explicit maintainer approval for the exact proposed source-backed protocol-signature
  evidence amendment commit, record it without changing normative behavior in a governance-only
  successor, and record that successor as `PLAN_BASE_SHA` before Evaluation Task 3's protocol-review
  prefix/DAG/archive path or a downstream consumer is committed or merged as complete.

- [x] Receive explicit maintainer approval for exact shard-checkpoint amendment commit
  `36bdcf7467ddd68543a024a1fb9a058f6c865a0d` with message
  `Одобряю amendment 36bdcf7467ddd68543a024a1fb9a058f6c865a0d` on 2026-09-01.
- [ ] Record this governance-only successor's future full SHA as `PLAN_BASE_SHA` before Foundations
  Tasks 10–12 or affected Runtime Tasks 6/7/9/10 proceed; do not place that future SHA inside this
  successor's own tree.

- [ ] Commit the synchronized roadmap and all four executable slice plans together, then record that
  already-created commit at implementation handoff as `PLAN_BASE_SHA`; do not place a future commit
  SHA inside its own tree.
- [x] Verify no executable plan retains the superseded topology/type/provenance vocabulary:

```bash
rg -n '(^|[^[:alnum:]_])Protocol[A]ttestationV1([^[:alnum:]_]|$)|ProtocolReview[A]ttestationV1|BenchmarkWorkflow[I]nventoryV1|require_no_unresolved_[h]old|at full SHA `46147e[f]|Normative design commit: `46147e[f]' docs/superpowers/plans/2026-08-30-public-benchmark-{foundations,runtime,evaluation-audit,publication}.md
```

Expected: no output; `rg` exits 1 because no stale term matches.

- [x] Verify plan formatting and whitespace before recording `PLAN_BASE_SHA`:

```bash
git diff --check
```

Expected: no output and exit 0.

Cross-slice ownership is fixed:

| Boundary | Sole owner |
|---|---|
| Versioned public benchmark request/policy, OpenAI wire/evidence, price schema, seals, shards, checkpoints | Foundations |
| CanonicalJSONV1 trio and neutral attachment primitives in `benchmark.attachments`; reviewer/workflow registries, protocol-subject Literal/mapping, statements, verified envelopes, serial reviewer DAG, bundle/tag binding, and `ProtocolReviewObjectArchiveV1` in `benchmark.protocol_review`; seven public offline commands | Evaluation/Audit |
| `CampaignStateSchemaV1`, state/authority and shared credential broker wire, `StateWriterGitIdentityV1`, initial-publication receipt/append wire, shared release effect/receipt/append wire, the six state-bound merge-denylist/terminal-containment primitives, hold/dismissal, drift/main fallback, exposure pending/progress/effect/final roots, containment-start event/root transitions, spend/batches, `Runtime.hard_score`, `.prepare_judge`, `.seal_judge`, reusable `benchmark-publication-state.yml` | Runtime |
| `Publication.campaign.evaluation_stage.sample_audit`, `.seal_audit`, `.analyze`, `.verify`, collection, terminal guard/queue/dequeue/fence/barrier/finality algorithms and all remaining Publication evidence types, merge admission, atomic postmerge hold consumers, open-PR exposure closure, executable release graph/finalizer closure, correction, documentation gate | Publication |

The public console entrypoint remains `laconian_eval.cli:main`. Its exact offline tuple is
`hard-score`, `prepare-judge`, `seal-judge`, `sample-audit`, `seal-audit`, `analyze`, `verify`, and
every handler imports only `laconian_eval.replay`. Live authority is available only through the
three Runtime and four Publication methods above; no public campaign-authority console exists.

The frozen workflow tuple is literal, ordered, and derived from verified C0 bytes:

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

## Milestone 1: Bootstrap canonical attachments and implement Foundations

- [ ] Execute Evaluation/Audit Task 1 first and export its sole `benchmark.attachments`
  CanonicalJSONV1 trio; then execute Foundations Tasks 1–12 in order with RED/GREEN/commit and
  two-stage review per task. No interim or second canonical encoder/parser/error type is allowed.
- [ ] Preserve legacy `GenerationRequest` bytes; add a versioned benchmark-only request/policy carrying the exact tier/cache TTL contract.
- [ ] Pin OpenAI SDK 3.3.1 and exact C0 `uv.lock`; verify the exact nine-member request projection,
  canonical request bytes, typed SDK request/response paths, installed/locked distribution, and
  forbidden recursive cache keys before credential access or client construction.
- [ ] Carry the five non-null price dimensions, requested/returned IDs, exact response paths, separate status/source-digest fields, and ordinary-uncached input through manifest, plan, attempt, seal, replay, and verification.
- [ ] Freeze corpus neutrality/severity, three exact parent plans, 36×40 shards, seal/finalize, verified scored sidecars, and safe deterministic checkpoints.
- [ ] Obtain one capsule-integrity review and one hostile-archive/security review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/capsule tests/test_smoke_cases.py tests/test_openai_provider.py tests/test_providers.py -q
uv run ruff check src/laconian_eval/capsule src/laconian_eval/providers tests/capsule
uv run mypy src
```

Expected: all commands exit 0; pytest reports no failed/skipped required Foundations test, Ruff
prints no findings, and mypy prints `Success: no issues found`.

## Milestone 2A: Complete Evaluation/Audit

- [ ] Evaluation Task 1 is already complete as the Milestone 1 bootstrap. After Slice 1 verified
  sealed/scorable evidence is available, execute Evaluation Tasks 2–15 in order.
- [ ] Implement strict CanonicalJSONV1; `TagOperatorRegistryV1`; two-entry stable `TagRulesetPolicyV1`; both reviewer registries; `ProtocolReviewStatementV1`; all three mode-discriminated `VerifiedProtocolAttestationV1` envelopes; `ProtocolAttestationBundleV1`; post-tag `ProtocolAttestationTagBindingV1`; `TagCreationRuleSuiteReceiptV1`; `ProtocolReviewObjectArchiveV1`; and fixed raw Git-object/signature verification.
- [ ] Construct and verify only `T0 -> C0 -> Rstat -> Rjudge -> Rsecurity -> B0 <- T1`: one fixed-path statement per reviewer commit, envelopes created only after their signed commit exists, B0 containing only the three envelopes/bundle delta, and both protected annotated tags created by the same registered operator.
- [ ] Bind every hard-score, judge, audit, analysis, and final evidence attachment to both registries, `protocol_attestations_root`, `ProtocolAttestationTagBindingV1`, the exact T0/T1 object identities and peeled C0/B0 commits, and the 15-member `WorkflowInventoryV1.workflow_root`.
- [ ] Require judge requests to use the same explicit/30m/no-breakpoint, SDK/lock, tier/cache evidence/status contract as generation.
- [ ] Implement fixed-denominator scoring, 10,000-vector PCG64 scenario bootstrap, outcome precedence, 144-record two-person audit, adjudication, weighted metrics, and exact false-fail certificates.
- [ ] Add only the seven offline replay handlers through `laconian_eval.cli:main`; prove the replay import/call graph contains no live capability or campaign constructor.
- [ ] Obtain one statistical-method review and one blind-judge/audit-protocol review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/benchmark -q
uv run ruff check src/laconian_eval/benchmark src/laconian_eval/replay tests/benchmark
uv run mypy src
```

Expected: all commands exit 0; pytest reports no failed/skipped required benchmark test, Ruff prints
no findings, and mypy prints `Success: no issues found`.

## Milestone 2B: Implement Runtime

- [ ] Execute the 10 Runtime tasks in order. Runtime Task 2 waits for Evaluation Task 3 types; Runtime Task 7 waits for Evaluation Tasks 4 and 8 evidence types.
- [ ] Generate state/event enums, transition table, evidence selectors, reachability, liveness, caller/ref/reason matrices, and broker policy from `CampaignStateSchemaV1` only; reject table-only, broker-only, wildcard, unreachable, cross-kind, or wedged edges.
- [ ] Implement `unresolved_hold_root`, strict hold/dismissal plan and caller identity, the four atomic hold consumers, `protocol_authority_drift`, protected-main fallback/freeze, and the universal fresh pair/policy/registry gate.
- [ ] Implement both active credential-exposure fields, provisional/permanent denylist members, `CREDENTIAL_EXPOSURE_PENDING`, ordered effect receipts, calculated predecessor-linked progress roots, terminal chain equality, final STOP/supplement consumption, and exposure-over-drift precedence.
- [ ] Add the campaign-state `active_publication_terminal_containment_root`, the exact
  `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` event and current-main broker row. Runtime Task 3 is the
  sole owner in `campaign.publication_wire` of `PublicationMergeDenylistEntryV1`,
  `PublicationMergeDenylistV1`, `PublicationTerminalContainmentPreflightV1`,
  `PublicationPreContainmentTerminalRouteV1`, `PublicationTerminalContainmentIntentV1`, and
  `PublicationTerminalContainmentFinalityV1`; Publication imports them by object identity. Reject
  shadow schemas, wildcard callers, non-monotone denylist changes, and a terminal transition that
  fails to clear the matching active root while preserving the successor denylist.
- [ ] Store the state-writer App key only in the external broker. Actions has no state key/token secret. The minimal reusable writer job performs only OIDC bootstrap plus the pinned broker client and receives no installation token.
- [ ] Build exact canonical SHA-1 blob/tree/commit objects with frozen identity bytes and publish only through smart-HTTP receive-pack using all-zero expected-absent bootstrap or exact-old-OID successor leases; reconcile absent/exact/divergent response-loss outcomes.
- [ ] Bind five-component default-tier reservations and trusted charges; no long-context price class can authorize, reserve, or reconcile spend.
- [ ] Allow automatic retry only for a proven no-result/no-usage 429 whose tier/applied/read/write statuses are the matching `not_applicable_definitely_rejected` values.
- [ ] Implement the three private Runtime live methods and prove no serialized capability and no dependency on replay handlers.
- [ ] Create `.github/workflows/benchmark-publication-state.yml` in Runtime Task 9. Prove four-job
  provider separation and the exact three-App topology. In the same task, bootstrap the canonical
  `campaign.release` security-attestor records, safe `campaign.release_broker` verifier, secret-free
  OIDC client, and `benchmark-preflight.yml` `preflight_rulesets` job/row. Its external broker reuses
  the release-finalizer installation, returns permissions exactly `administration:write`,
  `contents:read`, and `metadata:read`, closes the token before returning safe evidence, and has a
  GET-only endpoint policy.
- [ ] Obtain one state/accounting review and one OIDC/Actions/authority review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/capsule tests/test_openai_provider.py tests/test_ci_contract.py -q
uv run ruff check src/laconian_eval/campaign tests/campaign .github/workflows
uv run mypy src
```

Expected: all commands exit 0; pytest reports no failed/skipped required campaign test, Ruff prints
no findings, and mypy prints `Success: no issues found`.

## Milestone 3: Implement Publication

- [ ] Execute all 15 Publication tasks after stable Slice 1–3 types exist.
- [ ] Publication Task 7 creates `campaign/publication.py`, the private constructor, and four exact live methods; it modifies the reusable state workflow created by Runtime Task 9. Task 8 modifies those interfaces.
- [ ] Publication Task 10 imports, class-bound revalidates, and does not re-export the six Runtime-owned state-bound
  merge-denylist/containment primitives by object identity; it owns the terminal algorithm and all
  remaining branch/marker/check/queue/guard/dequeue/fence/barrier/finality evidence types. Runtime
  must not import a Publication-owned algorithm/evidence type into its state schema.
- [ ] Publication Task 10 extends the Runtime-created attestor substrate only with the
  `postmerge_rule_suite` caller row; Task 11 adds only `release_preparation` and the
  release-finalizer operation rows. The exact caller jobs are `security_attestor`,
  `publisher_effect`, `publication_terminalizer`, and `release_finalizer`; no later task changes the
  already frozen preflight workflow.
- [ ] Keep complete and invalid-prefix plans/states/events disjoint. Invalid-prefix publication ends at `INVALID_PREFIX_MERGED` or `INVALID_PREFIX_MERGED_INVALID` and can never create a result release, correction, documentation, presentation, or social effect.
- [ ] Persist intent before every initial/correction branch, PR, tag, draft, asset, publish, finalization, or invalidation effect; test create-or-adopt/reconcile at every response-loss and receipt-CAS window.
- [ ] Admit only `merge_commit` with parents `[base, head]` and exact tree. Persist `PostMergeAdmissionEvidenceV1` or `PostMergeAdmissionFailureV1`, including double-read current main, unchanged result subtree for a verified first-parent descendant, approvals/checks/actor, and timely historical passing non-bypass rule-suite evidence.
- [ ] Cover all six post-merge broker exceptions: the three success events `RESULT_MERGED`,
  `INVALID_PREFIX_MERGED`, `CORRECTION_MERGE_RECORDED`, and the three phase-bound failure events
  `RESULT_MERGE_INVALIDATED`, `INVALID_PREFIX_MERGE_INVALIDATED`, and
  `CORRECTION_INVALIDATED(kind="correction_publication_invalidation",
  publication_outcome="merged_invalid")`.
- [ ] Implement the separate terminal-containment algorithm for every active initial/correction
  publication prefix in this order: reconcile ordinary transports and freeze the exact ordinary or
  write-ambiguity source; build preflight/route/intent, append every candidate selector to the
  permanent successor denylist, and seal publisher ledger/vault prefixes with zero outstanding
  requests, dispatches, or live tokens; accept exactly one expected-OID
  `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` CAS (`null -> intent_sha256`) before any guard/dequeue/
  fence action; run at most eight stable global guard rounds; construct the exact two-inventory
  `PublicationTerminalMergeBarrierV1`, including authenticated dequeue/timeline and, only when
  needed and pilot-proven, a fresh failed `merge_group` validator run; double-read protected `main`
  and walk its complete first-parent chain; construct the one source-class-matching premerge or
  merge-won `PublicationTerminalContainmentFinalityV1`; then apply one phase-exact terminal CAS that
  clears only the matching active root and preserves the successor denylist forever. While the root
  is active, deny constructive mint, enqueue/merge admission, release authorization, a new
  publication/correction intent, exposure/hold state changes, and unrelated successors.
- [ ] Every active-prefix `no_pr|closed`, write ambiguity, and reconciliation-unavailable route must
  pass through containment; it cannot use a direct root-null terminal edge. Ordinary premerge and
  merge-won finality carry the exact stable `PublicationNoLaterEffectsEvidenceV1` where required.
  Write-ambiguity and reconciliation-unavailable variants instead bind their strict sealed
  failure-only evidence and never fabricate stable external state, object absence, or a no-later
  root. Any merge observed before terminal CAS switches to the phase-exact failed-admission route.
- [ ] Freeze the exact five `PostMergeAdmissionFailureV1.failure_kind` members:
  `ordinary`, `protocol_authority_drift_race`, `credential_exposure_race`,
  `reconciliation_unavailable`, and `publication_write_ambiguity_merge_race`. Freeze the independent
  19-member schema-ordered `failed_predicates` vocabulary:
  `unexpected_merge_parent`, `unexpected_merge_method`, `pr_identity_mismatch`,
  `base_oid_mismatch`, `head_oid_mismatch`, `result_tree_mismatch`,
  `checks_or_approvals_invalid`, `merge_actor_invalid`, `historical_rules_invalid`,
  `main_containment_invalid`, `workflow_root_mismatch`, `observation_inconsistent`,
  `publication_prefix_not_admitted_before_merge`, `publication_close_lost_to_merge`,
  `publication_reopened_after_close`, `protocol_authority_drift`,
  `credential_exposure_race`, `publication_reconciliation_unavailable`, and
  `publication_write_ambiguity_merge_race`. Tests exhaust every predicate under its allowed failure
  kind and strict source class (`normal_postmerge_admission`, `ordinary_terminal_disposition`, or
  `write_ambiguity`), all current-main descendant/movement branches, attestor pass/failure/not-run
  nullability, and every terminal consumer.
- [ ] Implement both acyclic release graphs. Initial is
  `InitialPreauthorizedResultReleasePlanV1 -> closed passing SecurityAttestorReceiptV1 -> ExecutableResultReleasePlanV1(intent_kind="initial") -> ResultReleaseIntentV1`.
  Correction is original prepublication `CorrectionIntentV1` with nested
  `CorrectionReleaseIntentPlanV1` -> publication receipt -> admitted correction merge -> closed
  passing security-attestor receipt -> `ExecutableResultReleasePlanV1(intent_kind="correction")`;
  there is no second correction intent. A failing attestation feeds only phase-exact invalidation.
  Initial tag target is the admitted initial merge; correction tag target remains the original
  intent's deterministic approved head, while the observed correction merge stays mandatory
  admission/lineage evidence and cannot retarget the tag.
  Follow with phase-exact delivery resolutions and accepted receipt wrappers,
  `ReleaseFinalizerOperationSetV1`, `ReleaseNoLaterEffectsEvidenceV1`, and exactly one initial or
  correction finalization/invalidation. Every publisher, security-attestor, and release-finalizer
  credential subject has a signed request-start before every dispatch, terminal transport receipt,
  append-only phase ledger/vault log, and exactly one terminal disposition; request ordinal `n+1`
  cannot dispatch until `n` is terminal. A mint followed by abort before the first or next request
  closes as a signed minted-and-closed zero-request disposition; delivery unknown requires the
  broker-signed unrecoverability proof and zero operation dispatches. Terminal evidence recomputes
  zero outstanding requests/dispatches/live tokens, denies later mint and same-token post-boundary
  dispatch, and archives only canary-free safe projections.
- [ ] Reconcile releases with fully paginated authenticated draft lookup, exact-ID reads, published-only by-tag recovery, upload-host asset POST, paginated asset listing, and the sole draft-to-published PATCH. Treat timeout/422/502 with relist/adopt; divergent or `starter` assets terminate.
- [ ] Verify the immutable-Releases setting, exact Release fields/assets, pinned tool digest, and `gh release verify` output as `ImmutableReleaseVerificationV1`; make no claim that a Release or Git history is undeletable.
- [ ] Handle credential exposure before publication, with a complete PR open, after merge, and after release; close an open complete PR, withdraw latest after release, preserve immutable history truth, and require a clean corrected lineage before promotion.
- [ ] Admit a nonnull hold only to the four exact atomic consumers: dismissal; premerge typed STOP; held `RESULT_MERGED -> RELEASE_PLAN_INVALIDATED`; and held `RELEASED -> CORRECTION_INTENT_AUTHORIZED`, each binding and clearing the predecessor hold while every other publication/release/correction edge requires null hold and active-progress roots.
- [ ] At `COMPLETE_PUBLICATION_PR_OPEN`, require credential pending CAS, publisher-only closure of that exact PR, ordered close-effect receipt, and final credential STOP; a merge race switches only to the existing postmerge invalidation/correction path.
- [ ] Obtain one supply-chain/publication review and one complete-DAG review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/benchmark tests/test_ci_contract.py tests/test_release_bundle.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
```

Expected: all commands exit 0; pytest reports no failed/skipped required publication test, Ruff
prints no formatting/lint findings, and mypy prints `Success: no issues found`.

## Milestone 4: Full offline synthetic rollout

- [ ] Reconstruct the complete T0/C0/Rstat/Rjudge/Rsecurity/B0/T1 object closure and raw-object archive, then all 36 generation capsules, 36 hard-score sets, 36 judge attachments, audit, analysis, complete bundle, publication intent/plan/receipt prefixes, queue/guard/fence/containment evidence, merge admission, both variants of the preauthorized→attested→executable release graph, accepted release receipt wrappers, operation-set/no-later evidence, terminal finalization, and final active latest pointer without provider or network access.
- [ ] Exercise the full matrix: paired-tag creation-suite replay/recreation and update/delete-bypass rejection; malformed reviewer DAG/signature/archive vectors; 429 exact retry; definitely rejected terminal; zero-call judge attachment; partial resume; every STOP parent/reason/caller allow and deny; all hold/dismissal consumers; moved/deleted/drifted-tag main fallback; budget exhaustion; both invalid-prefix merge outcomes; complete merge success/failure; all six post-merge exceptions; every terminal-containment source/prefix and queue/guard/dequeue/fence/current-main branch; all five failure kinds, all 19 schema-ordered failure predicates, and security-attestor result nullability; both correction invalidation families and all four publication outcomes; correction success from `RELEASE_BLOCKED` and `RELEASED`; every branch/PR/tag/draft/asset/publish effect-response/receipt-CAS loss window; every publisher/security-attestor/release-finalizer request, response-loss, closure, no-mint, minted-abort-before-first/next-request, post-boundary-dispatch denial, and reconciliation-unavailable window; expected-absent and competing receive-pack races; paginated draft and asset reads; timeout/422/502 reconciliation; divergent and `starter` assets; and credential exposure before/during/after drift, with complete PR open, after merge, and after release, including every pending-progress crash point and cross-pending/campaign/incident rejection.
- [ ] Rebuild the human report only from published-style artifacts and compare every checksum.
- [ ] Scan every synthetic artifact for canaries, credential patterns, environment dumps, private paths, unsafe Markdown/HTML, duplicate paths, and unbound files.
- [ ] Run twice from clean temporary roots:

```bash
uv sync --all-extras --dev
uv run pytest -p no:cacheprovider -q
uv run pytest -p no:cacheprovider -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
git diff --check
```

Expected: dependency sync exits 0; both pytest runs pass with identical required test counts and no
live calls; Ruff/mypy exit 0 with no findings; `git diff --check` prints nothing.

- [ ] Record commit/platform/timestamps/exit/test count for both runs and obtain two independent reviews with no unresolved P0/P1 finding.

## Milestone 5: Configure external trust boundaries

This milestone changes external state and needs explicit maintainer authorization at execution time.

- [ ] Confirm by secret-name/presence metadata only that `benchmark-live` contains `OPENAI_API_KEY`; never retrieve or print its value. Independently attest restriction, spend guard, sole consumers, and rotate/revoke procedure.
- [ ] Protect `benchmark-live` and `benchmark-publish` with required reviewers, no self-review/admin bypass, and approved deployment refs. Keep repository `GITHUB_TOKEN` read-only and global Actions PR approval disabled.
- [ ] Register exactly three pairwise-distinct repository-scoped Apps: state writer, publisher, and
  release finalizer. All App private keys and installation tokens exist only in their measured
  external broker vaults; `benchmark-publish` and every other Actions scope contain no App credential
  secret and authenticate to brokers only by exact job-scoped OIDC. The release-finalizer
  installation includes `administration:write`, while the separate `security_attestor` broker role
  mints its token downscoped in canonical order to `administration:write`, `contents:read`, and
  `metadata:read`. Although `administration:write` is GitHub's required permission name for the
  immutable-Releases setting endpoint, the attestor's fixed endpoint/query policy grants no mutation
  path; signed safe receipts may retain the preregistered nonsecret App identity.
- [ ] Protect `benchmark-authority/*` for brokered expected-old-OID receive-pack only; protect result branches and `main` with exact actors/checks and human merge. Configure exactly two disjoint tag-pattern rulesets for T0 and T1: the one registered `User/always` operator may bypass creation only, while update and deletion have zero bypass actors. Both tags are annotated-only and immutable after creation. Enable immutable Releases and record the setting without claiming object undeletability.
- [ ] Register the workflow-backed `laconian/publication-pr-validate` required check with exact
  GitHub Actions source App and C0 workflow hash on both `pull_request` and
  `merge_group:checks_requested`; publish it on the PR head or temporary merge-group SHA
  respectively. The publisher-App terminal guard is evidence consumed by that validator, not a
  base required-check context. Freeze a repository-owned active `PublicationBranchRulesetPolicyV1`
  with one-entry `MERGE`/`ALLGREEN`, minimum/maximum entries `1`, zero minimum wait, build
  concurrency `1`, exactly that one strict required check, no protected-main bypass/direct merge,
  and a positive check-response timeout whose seconds equal exactly `60 *` the observed GitHub
  `check_response_timeout_minutes`; publisher bypass exists only for the deterministic head pattern. Observation uses
  `includes_parents=false` and rejects inherited/unlisted rulesets. Retain historical passing rule
  suites promptly and confirm 90-day artifact retention.
- [ ] Capture and independently sign the safe repository trust record, including exact three-App permissions, OIDC broker policy, returned attestor permissions, stable two-ruleset policy, both unique historical creation rule suites, immutable setting, actors, and timestamps—never tokens, keys, PEMs, or raw privileged responses. A creation receipt requires zero matching earlier creation suites and exactly one matching after-OID suite; replay, deletion/recreation, ambiguous suites, update, or delete operations fail closed.

No live provider workflow may run until this milestone is complete and reviewed.

## Milestone 6: Run the non-evidentiary live pilot

- [ ] Freeze pilot C0, derive the literal 15-member `WorkflowInventoryV1`, activate both pilot tag-pattern rulesets, and have the registered operator create protected annotated pilot T0 peeling exactly to C0 with its unique creation-suite receipt.
- [ ] Add and commit-sign Rstat, Rjudge, and Rsecurity serially in registry order; create envelopes only after each signed commit; create B0 with only the three envelopes and `ProtocolAttestationBundleV1`; have the same operator create protected annotated pilot T1 on B0 with its own unique creation-suite receipt.
- [ ] Run secret-free pilot preflight: double-read both refs/policy, verify the complete raw Git closure/archive, signatures, stable ruleset policy, creation suites, `ProtocolAttestationTagBindingV1`, campaign registry, SDK/lock, price evidence, `StateWriterGitIdentityV1`, and generation-context expectation before approving provider jobs.
- [ ] Verify at most 24 generation and 24 judge attempts, zero retry, USD 5 exposure, exact explicit/30m/default wire, response paths/statuses/digests, returned-model consistency, checkpoints, and broker receipts.
- [ ] Run the disposable live platform pilot for terminal containment: create a one-PR
  `MERGE`/`ALLGREEN` queue; prove complete two-pass global inventory and an observable `LOCKED`
  entry; dequeue exactly, re-enqueue under a new merge group, and authorize a rerun retaining the
  workflow-run ID with `run_attempt == source_run_attempt + 1`; prove the fresh failed required
  validator removes or blocks the entry and the permanent denylist fails every later group. Accept
  an unrelated protected-main descendant only through a complete first-parent walk whose every
  advance is the rollout-proved two-parent queue merge, and reject a synthetic single-parent
  advance. Capture the real artifact API 302, strip Authorization/cookies before following the one
  allowlisted Location, safely extract the unique decision JSON from the bounded ZIP, and probe
  every required App endpoint/permission. Any unsupported queue state, timeline, rerun, redirect,
  same-SHA validator, or permission behavior blocks Milestone 7; it never weakens the contract.
- [ ] Treat pilot output as operational evidence only. Any protocol or implementation change creates a new pilot T0/T1 pair, reviewer commits, envelopes, B0, bundle and tag binding; pair-specific objects are never reused, though identical content-addressed C0 subobjects may recur. Revoke or rotate the key when incident policy requires.

## Milestone 7: Execute the confirmatory campaign

- [ ] After implementation is frozen and reverified, construct the final pair in exact order: activate both final tag rulesets; registered operator creates annotated T0 on frozen C0; Rstat/Rjudge/Rsecurity add one signed statement commit each; verifier creates B0 with only envelopes/bundle delta; the same operator creates annotated T1 on B0; persist both unique creation suites.
- [ ] Preflight double-reads both refs/policy, verifies the complete T0/C0/reviewer/B0/T1 closure, raw-object archive, registries, statements, signatures, envelopes, bundle/root/tag binding, 15-member workflow root, 1,440 rows, 36×40 partition, requested models, first-batch fit, and USD 75 cap before authority bootstrap or credential access.
- [ ] Approve each generation and judge batch separately; before the next approval verify authority OID, state/hold, spend/inventory, receipt, and exact suffix. Seal all 36 generation, hard-score, and judge attachments.
- [ ] On STOP, budget exhaustion, ambiguity, missing authority, or credential incident, make zero later calls/downloads and take only the schema-authorized invalid-prefix/containment route.
- [ ] Rotate or revoke the provider key after the final provider batch and immediately on credential incident.

## Milestone 8: Audit, analyze, collect, publish, and release

- [ ] Seal the provider inventory, complete the two identity-bound commit/reveal chains and adjudication, then seal deterministic analysis and three independent model outcomes.
- [ ] Collect only a complete bundle; otherwise finalize only the safe invalid prefix.
- [ ] Authorize initial publication intent before the exact publisher branch/PR effects. Human review
  and the protected one-entry `MERGE`/`ALLGREEN` merge queue are mandatory; reconstruct queue/guard/fence,
  publication-success finality, post-merge evidence/failure, and the applicable one of six
  post-merge events. If terminalization starts first, persist the separate containment-start event
  before guard/dequeue/fence work and finish only through its exact barrier/current-main/finality
  terminal route, preserving the denylist and clearing the active root.
- [ ] For a valid complete merge, build the immutable preauthorized plan, obtain the purpose-bound
  closed passing security-attestor receipt, derive the executable plan, and authorize the initial
  `ResultReleaseIntentV1` before the
  exact tag/draft/assets/publish effects. Reconcile every crash window, close every attestor/finalizer
  token and ledger, prove no later effects, and transition to `RELEASED` only through the exact
  terminal finalization.
- [ ] A correction is append-only original intent with nested `CorrectionReleaseIntentPlanV1` →
  publication → admitted merge, followed by exactly one disjoint branch: closed passing
  security-attestor receipt → executable plan → tag/release receipts → finalization; or closed
  failure evidence → phase-specific invalidation with no executable plan/effect. There is no second
  correction intent, and the observed merge cannot retarget the preauthorized approved-head tag. A
  new correction after `merged_invalid` explicitly supersedes the failed correction and
  contaminated merge; prior latest remains unchanged until successful finalization.

## Milestone 9: Present the released result

- [ ] Require `RELEASED`, active/nonwithdrawn latest pointer, null `unresolved_hold_root`, null active credential-exposure incident/progress and publication-containment roots, no open incident or correction, and fresh verification of the exact terminal finalization, accepted release receipt chain, immutable external objects, and zero-live-token no-later evidence.
- [ ] Update localized READMEs, `evals/README.md`, website, changelog, dated release note, presentation, and social package only from the committed complete bundle. Keep historical alpha material unchanged.
- [ ] Every number names model, campaign, interval, gate, denominator, confidence interval, and limitations; explain positive `concise - if`; never call visible-token reduction billed-output, total-token, monetary, or universal savings.
- [ ] Invalid-prefix terminal outcomes remain only in their reviewed authority/incident history; they
  trigger no release, documentation, site, presentation, release-note, social, or correction effect
  and never enter this promotion milestone.

## Completion definition

Implementation is complete when all four slice plans, synthetic reconstruction, quality gates, and two independent reviews are green. A result campaign is publishable only when its complete lineage is `RELEASED`, active and nonwithdrawn, public checksums are durable, provider credentials are contained as planned, and every public claim derives from that exact bundle. Positive, negative, and inconclusive model outcomes are acceptable; invalid-prefix outcomes remain incident evidence rather than releases.
