# Public Three-Model Benchmark Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver, secure, rehearse, execute, audit, and publish the approved GPT-5.6 Sol/Terra/Luna benchmark without allowing incomplete evidence, uncontrolled spend, or premature public claims.

**Architecture:** Four implementation slices establish an immutable evidence DAG and a separate fail-closed campaign control plane. Foundations own the exact OpenAI request/evidence wire and sealed capsules; Evaluation/Audit owns strict protocol attestations and offline replay; Runtime owns the authority schema, external OIDC broker, provider controller, and three live evaluation methods; Publication owns the four remaining live methods and all branch, PR, merge, release, correction, and promotion effects. Live operations begin only after every code, GitHub, broker, provider-key, and pilot gate passes.

**Tech Stack:** Python 3.11+, Pydantic 2, OpenAI Python SDK 3.3.1, NumPy PCG64, pytest/Ruff/mypy, GitHub Actions with full-SHA pins, OpenAI Responses API, strict CanonicalJSONV1, SHA-256 evidence, canonical Git SHA-1 objects, smart-HTTP receive-pack leases, descriptor-safe capsule/tar I/O, and protected Git tags/Releases.

---

## Sources, approval, and fixed scope

- Normative design: `docs/superpowers/specs/2026-08-30-public-three-model-benchmark-design.md` at `46147ef62b5bb009421d58928e879d92247d84b5`.
- Approval metadata: `0e2981e32b5d8982e78c73a5e413b36e2b1495e9`, recording the maintainer's exact approval `Одобряю amendment 46147ef` on 2026-08-30.
- Milestone 0 is complete. Slice implementation is pending and unblocked. Any later normative design amendment re-blocks every affected task until separately and explicitly approved.
- Generation model IDs are exactly `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`; returned provider model IDs are recorded separately and must be consistent per requested-model campaign, not textually equal to the requested ID.
- Primary contrast is `concise - if`, independently per model. The plan is 3 models × 12 scenarios × 2 locales × 4 arms × 5 repetitions = 1,440 responses, projected into exactly 36 ordered 40-row shards.
- Full authorized request exposure is USD 75. Pilot exposure is USD 5 with at most 24 generation and 24 judge attempts and no retry.
- Promotion requires an active, nonwithdrawn latest pointer at `RELEASED`, no unresolved hold, incident, or correction. `RESULT_MERGED`, `RELEASE_BLOCKED`, `INVALID_PREFIX_MERGED`, and `INVALID_PREFIX_MERGED_INVALID` never authorize a release claim, documentation, presentation, website, release note, or social post.

## Plan set and dependency graph

```text
Approved design 46147ef + approval metadata 0e2981e (Milestone 0 complete)
    |
    v
Slice 1 — Foundations
    |--------------------------|
    v                          v
Slice 2 — Evaluation/Audit    Slice 3 — Runtime (pauses at Slice 2-owned interfaces)
    |                          |
    +-------------+------------+
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

1. `docs/superpowers/plans/2026-08-30-public-benchmark-foundations.md` — 12 tasks.
2. `docs/superpowers/plans/2026-08-30-public-benchmark-evaluation-audit.md` — 15 tasks.
3. `docs/superpowers/plans/2026-08-30-public-benchmark-runtime.md` — 10 tasks.
4. `docs/superpowers/plans/2026-08-30-public-benchmark-publication.md` — 15 tasks.

## Milestone 0: Approved protocol/security contract — complete

- [x] Amend and independently review the normative design.
- [x] Bind literal `service_tier: "default"`, literal `prompt_cache_options: {"mode":"explicit","ttl":"30m"}`, recursive absence of `prompt_cache_breakpoint`, distinct cache-read/cache-write evidence and pricing, exact returned response paths and status vocabularies, SDK 3.3.1/`uv.lock`, and the `<=272_000` conservative input bound.
- [x] Bind the two-person audit registry, ordered three-person protocol registry, exact role subject inventories, CanonicalJSONV1 attestations, authority-only in-memory generation capability, and exact generation seal roots.
- [x] Bind `CampaignStateSchemaV1`, external OIDC state broker, canonical Git object/receive-pack lease protocol, `StateWriterGitIdentityV1`, exactly three Apps, direct-merge admission, durable initial/correction intents and receipts, six post-merge exceptions, credential-exposure containment, release recovery, invalid-prefix terminality, and seven-offline/seven-live entrypoint isolation.
- [x] Receive explicit maintainer approval for normative commit `46147ef62b5bb009421d58928e879d92247d84b5`; record it without changing normative content at `0e2981e32b5d8982e78c73a5e413b36e2b1495e9`.

Cross-slice ownership is fixed:

| Boundary | Sole owner |
|---|---|
| Versioned public benchmark request/policy, OpenAI wire/evidence, price schema, seals, shards, checkpoints | Foundations |
| CanonicalJSONV1, reviewer registries, `ProtocolAttestationV1`, protocol subjects, neutral attachments, seven public offline commands | Evaluation/Audit |
| `CampaignStateSchemaV1`, state/authority broker, `StateWriterGitIdentityV1`, spend/batches, `Runtime.hard_score`, `.prepare_judge`, `.seal_judge`, reusable `benchmark-publication-state.yml` | Runtime |
| `Publication.campaign.evaluation_stage.sample_audit`, `.seal_audit`, `.analyze`, `.verify`, collection, publication, merge admission, release, correction, documentation gate | Publication |

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

## Milestone 1: Implement Foundations

- [ ] Execute the 12 Foundations tasks in order with RED/GREEN/commit and two-stage review per task.
- [ ] Preserve legacy `GenerationRequest` bytes; add a versioned benchmark-only request/policy carrying the exact tier/cache TTL contract.
- [ ] Pin OpenAI SDK 3.3.1 and exact C0 `uv.lock`; verify typed request/response fields before credential access.
- [ ] Carry the five non-null price dimensions, requested/returned IDs, exact response paths, separate status/source-digest fields, and ordinary-uncached input through manifest, plan, attempt, seal, replay, and verification.
- [ ] Freeze corpus neutrality/severity, three exact parent plans, 36×40 shards, seal/finalize, verified scored sidecars, and safe deterministic checkpoints.
- [ ] Obtain one capsule-integrity review and one hostile-archive/security review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/capsule tests/test_smoke_cases.py tests/test_openai_provider.py tests/test_providers.py -q
uv run ruff check src/laconian_eval/capsule src/laconian_eval/providers tests/capsule
uv run mypy src
```

## Milestone 2A: Implement Evaluation/Audit

- [ ] Begin after Slice 1 verified sealed/scorable evidence is available; execute all 15 tasks in order.
- [ ] Implement strict CanonicalJSONV1, both reviewer registries, all three mode-discriminated signatures, exact `ProtocolAttestationV1` fields/order/subjects/root, and fixed Git-object/signature verification.
- [ ] Bind every hard-score, judge, audit, analysis, and final evidence attachment to both registries, `protocol_attestations_root`, exact tagged protocols, and `workflow_root`.
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

## Milestone 2B: Implement Runtime

- [ ] Execute the 10 Runtime tasks in order. Runtime Task 2 waits for Evaluation Task 3 types; Runtime Task 7 waits for Evaluation Tasks 4 and 8 evidence types.
- [ ] Generate state/event enums, transition table, evidence selectors, reachability, liveness, caller/ref/reason matrices, and broker policy from `CampaignStateSchemaV1` only; reject table-only, broker-only, wildcard, unreachable, cross-kind, or wedged edges.
- [ ] Store the state-writer App key only in the external broker. Actions has no state key/token secret. The minimal reusable writer job performs only OIDC bootstrap plus the pinned broker client and receives no installation token.
- [ ] Build exact canonical SHA-1 blob/tree/commit objects with frozen identity bytes and publish only through smart-HTTP receive-pack using all-zero expected-absent bootstrap or exact-old-OID successor leases; reconcile absent/exact/divergent response-loss outcomes.
- [ ] Bind five-component default-tier reservations and trusted charges; no long-context price class can authorize, reserve, or reconcile spend.
- [ ] Allow automatic retry only for a proven no-result/no-usage 429 whose tier/applied/read/write statuses are the matching `not_applicable_definitely_rejected` values.
- [ ] Implement the three private Runtime live methods and prove no serialized capability and no dependency on replay handlers.
- [ ] Create `.github/workflows/benchmark-publication-state.yml` in Runtime Task 9. Prove four-job provider separation, the exact three-App topology, and a downscoped read-only security-attestor token from the release-finalizer installation.
- [ ] Obtain one state/accounting review and one OIDC/Actions/authority review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/capsule tests/test_openai_provider.py tests/test_ci_contract.py -q
uv run ruff check src/laconian_eval/campaign tests/campaign .github/workflows
uv run mypy src
```

## Milestone 3: Implement Publication

- [ ] Execute all 15 Publication tasks after stable Slice 1–3 types exist.
- [ ] Publication Task 7 creates `campaign/publication.py`, the private constructor, and four exact live methods; it modifies the reusable state workflow created by Runtime Task 9. Task 8 modifies those interfaces.
- [ ] Keep complete and invalid-prefix plans/states/events disjoint. Invalid-prefix publication ends at `INVALID_PREFIX_MERGED` or `INVALID_PREFIX_MERGED_INVALID` and can never create a result release, correction, documentation, presentation, or social effect.
- [ ] Persist intent before every initial/correction branch, PR, tag, draft, asset, publish, finalization, or invalidation effect; test create-or-adopt/reconcile at every response-loss and receipt-CAS window.
- [ ] Admit only `merge_commit` with parents `[base, head]` and exact tree. Persist `PostMergeAdmissionEvidenceV1` or `PostMergeAdmissionFailureV1`, including double-read current main, unchanged result subtree for a verified first-parent descendant, approvals/checks/actor, and timely historical passing non-bypass rule-suite evidence.
- [ ] Cover all six post-merge broker exceptions: the three success events `RESULT_MERGED`,
  `INVALID_PREFIX_MERGED`, `CORRECTION_MERGE_RECORDED`, and the three phase-bound failure events
  `RESULT_MERGE_INVALIDATED`, `INVALID_PREFIX_MERGE_INVALIDATED`, and
  `CORRECTION_INVALIDATED(kind="correction_publication_invalidation",
  publication_outcome="merged_invalid")`.
- [ ] Reconcile releases with fully paginated authenticated draft lookup, exact-ID reads, published-only by-tag recovery, upload-host asset POST, paginated asset listing, and the sole draft-to-published PATCH. Treat timeout/422/502 with relist/adopt; divergent or `starter` assets terminate.
- [ ] Verify the immutable-Releases setting, exact Release fields/assets, pinned tool digest, and `gh release verify` output as `ImmutableReleaseVerificationV1`; make no claim that a Release or Git history is undeletable.
- [ ] Handle credential exposure before publication, with a complete PR open, after merge, and after release; close an open complete PR, withdraw latest after release, preserve immutable history truth, and require a clean corrected lineage before promotion.
- [ ] Obtain one supply-chain/publication review and one complete-DAG review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/benchmark tests/test_ci_contract.py tests/test_release_bundle.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
```

## Milestone 4: Full offline synthetic rollout

- [ ] Reconstruct all 36 generation capsules, 36 hard-score sets, 36 judge attachments, audit, analysis, complete bundle, publication intent/plan/receipts, merge admission, release intent/plan/receipts, and final active latest pointer without provider or network access.
- [ ] Exercise the full matrix: 429 exact retry; definitely rejected terminal; zero-call judge attachment; partial resume; every STOP parent/reason/caller allow and deny; budget exhaustion; both invalid-prefix merge outcomes; complete merge success/failure; all six post-merge exceptions; both correction invalidations including `merged_invalid`; correction success from `RELEASE_BLOCKED` and `RELEASED`; every branch/PR/tag/draft/asset/publish effect-response/receipt-CAS loss window; expected-absent and competing receive-pack races; paginated draft and asset reads; timeout/422/502 reconciliation; divergent and `starter` assets; and credential exposure prepublication, with complete PR open, after merge, and after release.
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

- [ ] Record commit/platform/timestamps/exit/test count for both runs and obtain two independent reviews with no unresolved P0/P1 finding.

## Milestone 5: Configure external trust boundaries

This milestone changes external state and needs explicit maintainer authorization at execution time.

- [ ] Confirm by secret-name/presence metadata only that `benchmark-live` contains `OPENAI_API_KEY`; never retrieve or print its value. Independently attest restriction, spend guard, sole consumers, and rotate/revoke procedure.
- [ ] Protect `benchmark-live` and `benchmark-publish` with required reviewers, no self-review/admin bypass, and approved deployment refs. Keep repository `GITHUB_TOKEN` read-only and global Actions PR approval disabled.
- [ ] Register exactly three pairwise-distinct repository-scoped Apps: state writer, publisher, release finalizer. The state private key exists only in the external OIDC broker. Publisher/release credentials exist only in `benchmark-publish`; the release-finalizer broker may mint a separate `security_attestor` token downscoped to `administration:read`, `metadata:read`, `contents:read` and no write scope.
- [ ] Protect `benchmark-authority/*` for brokered expected-old-OID receive-pack only; protect result branches, `main`, input tags, and result tags with exact actors/checks and human merge. Enable immutable Releases and record the setting without claiming object undeletability.
- [ ] Register all required checks with exact names/source App/workflow hashes. Retain historical passing rule suites promptly. Confirm 90-day artifact retention.
- [ ] Capture and independently sign the safe repository trust record, including exact three-App permissions, OIDC broker policy, returned attestor permissions, rule suites, immutable setting, actors, and timestamps—never tokens, keys, PEMs, or raw privileged responses.

No live provider workflow may run until this milestone is complete and reviewed.

## Milestone 6: Run the non-evidentiary live pilot

- [ ] Freeze the complete code/input/protocol/workflow package at one protected `benchmark-input-YYYYMMDD.N` tag; verify its annotated/lightweight object and peel exactly to C0. Derive all 15 workflow hashes and `workflow_root` from that C0 tree in literal order.
- [ ] Include both reviewer registries, exact three attestations, price evidence, `StateWriterGitIdentityV1`, trust evidence, and generation-context expectation inputs; no self-referential context capability is serialized.
- [ ] Run secret-free preflight, approve exact bounded provider jobs, verify at most 24 generation and 24 judge attempts, zero retry, USD 5 exposure, exact explicit/30m/default wire, SDK/lock, response paths/statuses/digests, returned-model consistency, checkpoints, and broker receipts.
- [ ] Treat pilot output as operational evidence only. Any protocol change creates a new approved normative version/tag and repeats the pilot. Revoke or rotate the key when incident policy requires.

## Milestone 7: Execute the confirmatory campaign

- [ ] Create a new protected input tag peeling to the frozen confirmatory C0; preflight verifies 1,440 rows, 36×40 partition, registries/attestations/workflow root, requested models, first-batch fit, and USD 75 cap.
- [ ] Approve each generation and judge batch separately; before the next approval verify authority OID, state/hold, spend/inventory, receipt, and exact suffix. Seal all 36 generation, hard-score, and judge attachments.
- [ ] On STOP, budget exhaustion, ambiguity, missing authority, or credential incident, make zero later calls/downloads and take only the schema-authorized invalid-prefix/containment route.
- [ ] Rotate or revoke the provider key after the final provider batch and immediately on credential incident.

## Milestone 8: Audit, analyze, collect, publish, and release

- [ ] Seal the provider inventory, complete the two identity-bound commit/reveal chains and adjudication, then seal deterministic analysis and three independent model outcomes.
- [ ] Collect only a complete bundle; otherwise finalize only the safe invalid prefix.
- [ ] Authorize initial publication intent before the exact publisher branch/PR effects. Human-review and direct-merge through protection; reconstruct post-merge evidence/failure and the applicable one of six post-merge events.
- [ ] For a valid complete merge, authorize release intent before the exact tag/draft/assets/publish effects. Reconcile every crash window and transition to `RELEASED` only after exact verification.
- [ ] A correction is append-only intent→publication→merge→tag→release→finalization or a phase-specific terminal invalidation. A new correction after `merged_invalid` explicitly supersedes the failed correction and contaminated merge; prior latest remains unchanged until successful finalization.

## Milestone 9: Present the released result

- [ ] Require `RELEASED`, active/nonwithdrawn latest pointer, no open incident, hold, or correction, and fresh verification of the exact release receipt.
- [ ] Update localized READMEs, `evals/README.md`, website, changelog, dated release note, presentation, and social package only from the committed complete bundle. Keep historical alpha material unchanged.
- [ ] Every number names model, campaign, interval, gate, denominator, confidence interval, and limitations; explain positive `concise - if`; never call visible-token reduction billed-output, total-token, monetary, or universal savings.
- [ ] Invalid-prefix terminal outcomes remain only in their reviewed authority/incident history; they
  trigger no release, documentation, site, presentation, release-note, social, or correction effect
  and never enter this promotion milestone.

## Completion definition

Implementation is complete when all four slice plans, synthetic reconstruction, quality gates, and two independent reviews are green. A result campaign is publishable only when its complete lineage is `RELEASED`, active and nonwithdrawn, public checksums are durable, provider credentials are contained as planned, and every public claim derives from that exact bundle. Positive, negative, and inconclusive model outcomes are acceptable; invalid-prefix outcomes remain incident evidence rather than releases.
