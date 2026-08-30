# Public Three-Model Benchmark Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver, secure, rehearse, execute, audit, and publish the approved GPT-5.6 Sol/Terra/Luna benchmark without allowing incomplete evidence, uncontrolled spend, or premature public claims.

**Architecture:** Four implementation slices establish an immutable evidence DAG and a separate fail-closed campaign control plane. Foundations make generation evidence shardable, sealable, and transportable. Evaluation defines neutral blind-judging, clustered-inference, and human-audit APIs. Runtime binds each provider job to one exact reservation and state transition. Publication authoritatively stages the live audit/analysis outputs, verifies the complete DAG, copies a sealed allowlist through a separately approved writer, and releases only the reviewed merge tree. Live operations begin only after all code, GitHub, provider-key, and pilot gates pass.

**Tech Stack:** Python 3.11+, Pydantic 2, NumPy PCG64 for the frozen statistical protocol, pytest/Ruff/mypy, GitHub Actions with protected environments and full-SHA action pins, OpenAI Responses API, canonical JSON/SHA-256 attachments, descriptor-safe capsule/tar I/O, and immutable Git tags/releases.

---

## Sources and fixed scope

- Approved design: `docs/superpowers/specs/2026-08-30-public-three-model-benchmark-design.md`.
- Design approval: 2026-08-30.
- Generation models: exactly `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`.
- Primary contrast: `concise - if`, reported independently for each model.
- Full generation plan: 3 models × 12 scenarios × 2 locales × 4 arms × 5 repetitions = 1,440 responses.
- Full logical partition: exactly 36 model/scenario capsules × 40 plan rows.
- Potential semantic judgments: at most 1,440; only deterministic hard-pass responses are dispatched.
- Full authorized request-exposure cap: USD 75. Pilot cap: USD 5 with at most 24 generation and 24 judge attempts and no retry.
- Documentation, website, release-note, presentation, and social result claims remain blocked until
  `CampaignStateV1.state == "RELEASED"` and the exact requested initial/correction release receipt is
  the canonical latest released pointer. A blocked or merely merged correction never authorizes
  promotion; a successful correction from `RELEASE_BLOCKED` must first apply the immutable
  `CORRECTION_RESULT_RELEASED -> RELEASED` transition.

## Plan set and dependency graph

```text
Approved design -> Milestone 0 amendment + fresh approval
    |
    v
Slice 1 — Foundations
    |-------------------------|
    v                         v
Slice 2 — Evaluation/Audit   Slice 3 — Campaign Runtime
    |                         |
    |-----------+-------------|
                v
Slice 4 — Evidence Collection, Publication, Release
                |
                v
Offline synthetic rollout + two independent reviews
                |
                v
Protected GitHub/provider setup -> pilot C0/C1 freeze/tag -> live pilot
                |
                v
Confirmatory C0/C1 re-freeze/tag -> batches -> audit -> analysis -> publication -> release
                |
                v
Post-RELEASED documentation, presentation, and social package
```

The detailed plans are:

1. `docs/superpowers/plans/2026-08-30-public-benchmark-foundations.md`
2. `docs/superpowers/plans/2026-08-30-public-benchmark-evaluation-audit.md`
3. `docs/superpowers/plans/2026-08-30-public-benchmark-runtime.md`
4. `docs/superpowers/plans/2026-08-30-public-benchmark-publication.md`

## Milestone 0: Lock names, boundaries, and compatibility

- [ ] Amend the approved design before any slice implementation. In Sections 6.2/8, bind the literal
  Responses `service_tier="default"`, no-write cache mode, distinct cache-read/cache-write accounting
  and rates, returned-tier evidence, conservative exposure, and the delivery-specific fail-closed
  status vocabulary. In Sections 12.1/13.2, replace the two-job/two-writer or write-capable repository
  `GITHUB_TOKEN` assumptions with the four-job provider boundary and three mutually exclusive
  dedicated Apps defined by the Runtime/Publication plans. Add the two independent reviewer
  registries, exact frozen 15-workflow inventory/root used by all protocol attestations, and the
  authority-bound generation-context expectation that fixes tagged hard-scorer source/protocol
  identity before hard scoring. In Section 7.4 add the sole blocked-release escape
  `RELEASE_BLOCKED + CORRECTION_RESULT_RELEASED -> RELEASED`, its exact correction-lineage/
  publication/merge/release evidence bindings, and the rule that a successful correction from an
  already `RELEASED` campaign appends terminal correction evidence without changing state; no
  other correction event may rewrite a terminal state or prior history. Record a
  fresh approval in the design approval block. Keep the experiment estimands, caps, evidence, audit,
  publication, and human-merge invariants unchanged. Until this single protocol/security amendment
  is merged and reapproved, every slice task is blocked; neither the old writer topology nor an
  implicit default/cache policy is an implementation fallback.
- [ ] Read all four slice plans and enforce this already-resolved cross-slice contract:

| Boundary | Owning module | Stable public names |
|---|---|---|
| Generation seal | `laconian_eval.capsule.seal_models` / `finalize` | `SealV1`, `capsule_sha256`, `FinalizeResultV1`, `finalize_capsule` |
| Shard evidence | `laconian_eval.capsule.sharding` / `scorable` / `sidecars` | `ShardPlanV1`, `ScoredAttemptV2`, `VerifiedScoredCapsuleV2`, `load_verified_scored_capsule` |
| Artifact wire | `laconian_eval.campaign.artifact_wire` | `ArtifactEnvelopeV1`, `UploadAuthorizationV1`; Runtime owns these before any provider upload and Slice 4 reuses them |
| Hard score and judge | `laconian_eval.benchmark.hard_score` / `judge` | `HardScoreRequestSetV1`, `JudgeRequestAttachmentV1`, `JudgeAttemptEvidenceV1`, `JudgeAttemptRootIndexV1`, `JudgeAttachmentV1` and their exact writers/loaders/verifiers |
| Neutral context/provider bridge | `laconian_eval.benchmark.context` / `provider_evidence` plus `campaign.benchmark_adapter` / `benchmark_stage` | `ProtocolReviewerRegistryV1`, `LayerRootIndexV1`, `GenerationContextExpectationV1`, `VerifiedGenerationContextExpectationV1`, `GenerationContextIndexV1`, `VerifiedGenerationContextIndexV1` (owned by `context`); `VerifiedBenchmarkProviderEvidenceV1` (owned by `provider_evidence`, constructible only with the external in-memory verified expectation); authority-verified generation-context, hard-score, prepare-judge, and seal-judge stage adapters |
| Audit and analysis | `laconian_eval.benchmark.audit_sampling` / `reporting` plus `laconian_eval.campaign.evaluation_stage` | `VerifiedAuditSampleRootV1`, `write_audit_sample_root`, `load_verified_audit_sample_root`, `VerifiedAuditEvidenceV1`, `VerifiedAnalysisEvidenceV1`, their fixed neutral writers/loaders, and Publication-owned authority-bound sample-audit, seal-audit, and analyze-plus-verify stage adapters |
| Campaign registry | `laconian_eval.campaign.preflight` | `CampaignSeedV1`, `CampaignPlanIndexV1`, `CampaignRegistryV1`, `RepositoryTrustBoundaryAttestationV1`, `BenchmarkWorkflowInventoryV1`, `BENCHMARK_WORKFLOW_PATHS_V1`, `build_benchmark_workflow_inventory`, and sealed preflight; it imports the neutral protocol-reviewer registry |
| Runtime authority | `laconian_eval.campaign.state` / `authority` | `CampaignEventV1`, `CampaignStateV1`, `InvalidEventHoldV1`, `TerminalEvidenceMutationV1`, `HoldDismissalMutationV1`, `AuthorityMutationV1`, `DurableAuthorityCheckpointV1`, `ReconstructedAuthorityV1`, `require_no_unresolved_hold`, `apply_campaign_event`, append/dismiss/composite mutations |
| Spend and batches | `laconian_eval.campaign.spend` / `batch` / `controller` | `SpendLedgerV1`, `VerifiedPhasePlanV1`, `BatchPlanV1`, `ConsumedBatchReceiptV1`, `CredentialScanReceiptV1` |
| Exact artifact/publication/release | `laconian_eval.campaign.github_records` / `artifacts` / `publication` / `release` | `ExactArtifactLocatorV1`, `VerifiedArtifactArchive`, `PublicationPlanV1`, `PublicationMergeReceiptV1`, `BlockedReleaseObjectsV1`, `LatestPublicationPointerV1`, `CorrectionProgressV1`, `CorrectionLineageV1`, `ResultReleasePlanV1`, `ResultReleaseReceiptV1` |
| Local command surfaces | `laconian_eval.benchmark.cli` / `campaign.cli` | `laconian-benchmark` seven fixed offline/non-evidentiary replay commands; all seven live derivations use fixed campaign-side adapters/tools (Runtime owns hard-score, prepare-judge, and seal-judge; Publication owns sample-audit, seal-audit, and combined analyze-plus-verify); `laconian-campaign` sixteen fixed secret-free/runtime commands; state, publisher, and release writers remain separate narrow tools |

- [ ] Grow one cumulative `tests/test_public_contract.py` contract only at serialized owners: Slice 1
  Tasks 1, 3, and 9 respectively pin corpus, provider/tier, and final capsule/scored-sidecar names;
  Slice 2 Task 14 pins methodology/evidence language and Task 15 pins final layer/context/
  judge-attempt/provider/audit/analysis names plus seven commands; Slice 3 Task 7 pins adapter
  handoffs and Task 8 pins runtime
  names/six commands; Slice 4 Tasks 7, 8, 10, 11, and 13 pin their newly exported records/workflow
  owners and the final sixteen campaign commands. Every owning task lists and stages the file; rebase
  before the next owner and never edit it concurrently.
- [ ] Use `src/laconian_eval/campaign/` for campaign authority/runtime/publication control and `src/laconian_eval/benchmark/` for hard score, judge, statistics, audit, and reports.
- [ ] Keep the dependency direction `campaign -> benchmark -> verified capsule`. Generic capsule verification must never import GitHub authority or spend control.
- [ ] Preserve legacy v1 CLI, replay smoke, `RawAttempt`, `ScoredAttempt`, and `RunSummary` behavior.
- [ ] Freeze the cross-slice names in `tests/test_public_contract.py` so later renames fail visibly.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/test_public_contract.py tests/test_package.py -q
```

Expected GREEN after the final interface-owning task in each implemented slice; before a later slice
exists, its rows remain documentation-only and are not imported by an earlier slice.

## Milestone 1: Implement Slice 1 foundations

- [ ] Execute `2026-08-30-public-benchmark-foundations.md` task by task.
- [ ] Remove evaluator-invented sentence limits and freeze material/critical warning severity before observing pilot outputs.
- [ ] Bind explicit medium reasoning, medium verbosity, omitted reasoning mode, and reasoning-token usage into manifests, requests, identities, attempts, and verification.
- [ ] Materialize exactly three 480-row parent plans and 36 disjoint, ordered, hash-bound 40-row shard projections.
- [ ] Add public finalize/seal, scorable projections, sealed verification, and strict uncompressed checkpoint pack/restore.
- [ ] Obtain one capsule-integrity review and one hostile-archive/security review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/capsule tests/test_smoke_cases.py tests/test_openai_provider.py tests/test_providers.py -q
uv run ruff check src/laconian_eval/capsule src/laconian_eval/providers tests/capsule
uv run mypy src
```

## Milestone 2A: Implement Slice 2 evaluation and audit

- [ ] Start only after Slice 1 exposes verified sealed/scorable evidence.
- [ ] Execute `2026-08-30-public-benchmark-evaluation-audit.md` task by task.
- [ ] Seal one `HardScoreRequestSetV1` and one judge attachment for every generation capsule, including zero-request attachments.
- [ ] Prove the judge request is blind to arm, generation model, order, length, usage, latency, and cost.
- [ ] Implement fixed-denominator H/S quality, scenario-cluster bootstrap with 10,000 PCG64 vectors and type-7 quantiles, exact outcome precedence, and all limitation fields.
- [ ] Implement the exact 144-record certainty/stratified human sample, two-person commit-reveal, dual-signoff adjudication, weighted agreement/false-pass intervals, and model/arm-indexed false-fail sensitivity.
- [ ] Fail closed on missing records, fewer than 9,990 valid bootstrap replicates, zero audit denominators, unverifiable certificates, or search-cap exhaustion.
- [ ] Obtain one statistical-method review and one blind-judge/audit-protocol review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/benchmark -q
uv run ruff check src/laconian_eval/benchmark tests/benchmark
uv run mypy src
```

## Milestone 2B: Implement Slice 3 campaign runtime

- [ ] After Slice 1, start Runtime Task 1 campaign models, tag binding, trust/pricing schemas,
  state/hold authority, exact spend, and generation batch planning while Slice 2 proceeds. Pause
  Runtime at Task 2's neutral-context integration checkpoint: Task 2 may not turn GREEN or commit,
  and serialized Runtime Tasks 3–6 may not start, until Slice 2 Task 3 owns/exports the neutral
  reviewer registries, `GenerationContextIndexV1`, and verified context loader. Slice 2 Task 8 only
  extends the post-judge provider bridge. Resume Runtime task order from Task 2 after Task 3 lands.
- [ ] Integrate generation/judge adapters and judge batch planning only after Slice 2 locks its
  request, judge-attempt, layer/context, and attachment contracts.
- [ ] Runtime Task 7's generation/context and hard-score/prepare-judge stage work may use Slice 2
  Tasks 3–4, but its seal-judge/provider-evidence half may not turn GREEN or commit until Slice 2
  Task 8 owns `VerifiedBenchmarkProviderEvidenceV1` and the post-judge bridge.
- [ ] At Runtime Task 7 completion, run the real generation-authority adapter tests. Require the
  retained expectation/predecessor/final-root binding; exact statistics/hard-score/judge/audit and
  workflow roots; direct neutral Task 3/4/8 composition for hard-score, prepare-judge, and
  seal-judge; external expectation passed to the provider loader; and zero Runtime import/invocation
  of `laconian_eval.benchmark.cli`.
- [ ] Execute `2026-08-30-public-benchmark-runtime.md` task by task.
- [ ] Prove every provider attempt has a reservation and every batch has a new single-use job receipt.
- [ ] Price uncached input, cached input, cache writes, and output from the frozen price snapshot for
  the literal requested Responses service tier `default`; require the
  versioned conservative input bound to be `<= 272_000` and mark any larger request
  `definitely_not_sent`. Long-context rates may be attested but are never authorized or reserved.
- [ ] Bind and emit exact Responses `service_tier="default"` in every generation/judge manifest,
  request, identity, reservation, attempt, price snapshot, and approval attestation. Preserve the
  returned tier/accounting status. Only independently definitely-not-sent/rejected attempts with no
  response/usage may use the matching closed `not_applicable_definitely_not_sent` or
  `not_applicable_definitely_rejected` value (so a proven 429 can retry); for response-received or
  unknown delivery, missing/non-default evidence retains worst-case exposure, stops later calls, and
  can never be silently reconciled as standard-tier usage.
- [ ] Require reviewed nonnull cache-write rates and explicit/no-breakpoint cache-mode support for
  all frozen generation/judge aliases; omitted write usage retains worst-case exposure, and any
  nonzero write under the forbidden-write contract stops the campaign after cost is recorded.
- [ ] Prove only structured, definitely rejected 429 responses retry; 401/403 STOP; timeout/connection/408/409/5xx/unknown delivery never retry.
- [ ] Prove a soft-deadline exit is resumable only after a verified partial checkpoint and runner loss never silently recreates uncertain work.
- [ ] Prove `CampaignStateV1` rejects illegal transitions without changing the last valid state and atomically creates `InvalidEventHoldV1`.
- [ ] Prove the protected `benchmark-authority/<campaign-id>` ref is the only authoritative head and
  that a non-force fast-forward remote CAS rejects every stale sibling.
- [ ] Obtain one state-machine/accounting review and one Actions credential-boundary review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/capsule tests/test_openai_provider.py tests/test_ci_contract.py -q
uv run ruff check src/laconian_eval/campaign tests/campaign .github/workflows
uv run mypy src
```

## Milestone 3: Implement Slice 4 collection, publication, and release

- [ ] Start after Slices 1–3 publish stable hashes/types and Slice 2 exposes the fixed neutral
  audit/analysis writers and verified loaders; Slice 4 authoritatively stages and seals their live
  outputs.
- [ ] Execute `2026-08-30-public-benchmark-publication.md` task by task.
- [ ] At Publication Task 7 completion, run the real `campaign.evaluation_stage` and workflow tests.
  Require the exact provider/sample/seal/analyze-plus-verify boundaries, state/event-bound roots,
  external in-memory expectation, authority-bound statistics protocol, deterministic bootstrap,
  private byte-identical sample rematerialization after reviewer-artifact expiry, cross-sample
  rejection, and zero raw `laconian-benchmark` invocation in a live workflow.
- [ ] Verify exact run, run-attempt, job, deployment, approval, artifact ID, service digest, detached commit, workflow hash, and capsule/attachment lineage.
- [ ] Keep the provider-evidence verifier read-only and prohibit it from accepting audit/statistical outputs.
- [ ] Keep complete collection and invalid-prefix finalization separate; the invalid path must contain no performance estimate.
- [ ] Prove the minimal publisher copies only the sealed fixed inventory byte-for-byte and cannot parse or execute model output.
- [ ] Prove publication base/head movement forces replan; post-merge defects force `RELEASE_BLOCKED`; release finalization tags only the verified merge commit.
- [ ] Obtain one supply-chain/publication review and one independent complete-DAG review.
- [ ] Gate:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/benchmark tests/test_ci_contract.py tests/test_release_bundle.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
```

## Milestone 4: Full offline synthetic rollout

- [ ] Run a provider-free campaign that reconstructs all 36 generation capsules, 36 hard-score request sets, 36 judge attachments, audit, analysis, complete bundle, publication plan, and release plan.
- [ ] Include deterministic cases for one 429 retry, ordinary terminal rejection, zero-call judge attachment, partial checkpoint/resume, STOP branch, invalid-prefix bundle, publication replan, and release block.
- [ ] Rebuild the human report exclusively from published-style artifacts and compare every checksum.
- [ ] Scan the complete synthetic artifact inventory for known canaries, credential patterns, environment dumps, private paths, unsafe Markdown/HTML, duplicate paths, and unbound files.
- [ ] Run the entire repository suite twice from clean temporary output roots:

```bash
uv sync --all-extras --dev
uv run pytest -p no:cacheprovider -q
uv run pytest -p no:cacheprovider -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
git diff --check
```

- [ ] Record command, commit SHA, platform, start/end timestamps, exit code, and test count for both runs.
- [ ] Require two independent reviews with no unresolved P0/P1 findings before repository setup.

## Milestone 5: Configure external trust boundaries

This milestone changes external repository/provider state and requires explicit maintainer authorization at execution time.

- [ ] Confirm `benchmark-live` contains `OPENAI_API_KEY` without reading or printing its value.
  Plan-authoring note (2026-08-30): the maintainer reports that the secret is already present; keep
  this gate unchecked until execution-time read-only name/presence confirmation and the independent
  restriction/rotation attestation below. Never retrieve the value.
- [ ] Independently attest that the secret is a dedicated restricted project key, has only required API capability, has no unrelated consumers, has a provider-side spend guard where available, and has a written rotate/revoke procedure.
- [ ] Protect `benchmark-live` with required reviewers, prevent self-review, disable admin bypass, and allow deployments only from `benchmark-input-*` tags.
- [ ] Create equally protected `benchmark-publish` without `OPENAI_API_KEY`.
- [ ] Keep default repository workflow permissions read-only and the combined **Allow GitHub Actions
  to create and approve pull requests** setting disabled. Require full-SHA action pinning.
- [ ] Register three repository-scoped, pairwise-distinct GitHub Apps and attest their numeric App/
  installation IDs, slugs/bot logins, exact permission responses, owners, private-key fingerprints,
  and rotation procedure: state writer (`contents:write` beyond metadata); publisher
  (`actions:read`, `deployments:read`, `contents:write`, `pull_requests:write`); release finalizer
  (`actions/deployments:read`, `contents:write`). Store state-App credentials as repository secrets
  mapped only by fixed writer steps; store publisher/release triples only in `benchmark-publish`.
  Do not create `benchmark-state` or `benchmark-release` environments. Treat every endpoint exposed
  by each broad GitHub permission as technically reachable; fixed hashed tools, endpoint-policy
  tests, rulesets, immutable Releases, and before/after receipts—not capability claims—enforce the
  narrower operational roles.
- [ ] Add immutable input/result tag rules. Enable immutable GitHub Releases. Permit result tag/
  release creation only to the release-finalizer App; it must create a draft, upload/verify both
  assets, then perform one draft-to-published transition and prove the release is immutable.
- [ ] Protect `benchmark-authority/*` against deletion, force-push, and human updates; allow only the
  exact state-writer App to create/non-force-fast-forward with expected-OID CAS.
- [ ] Protect `refs/heads/benchmark-result-pr/*` for publisher-created result refs; the static
  ruleset restricts the namespace/actor while the fixed publisher and validator enforce the exact
  plan-derived branch grammar. Forbid force/delete/reuse/update after the initial push. Protect
  `main` with required human review/checks and restrict merge/update actors to preregistered non-bot
  maintainers, explicitly excluding all benchmark Apps and GitHub Actions. Publisher
  `pull_requests:write` is API-capable of merge, so ruleset exclusion—not a capability claim—is the
  enforcement boundary.
- [ ] Register the always-present `publication-pr-validate`, `audit-pr-validate`, and
  `benchmark-docs-validate` check jobs, then add their exact names to `main` protection. Each workflow
  runs on every pull request (and `merge_group` when merge queue is enabled) and returns a successful
  explicit no-op for irrelevant paths; no required workflow uses top-level path filters.
- [ ] Confirm artifact retention is 90 days and schedule campaign/audit completion inside that window.
- [ ] Preregister each required check's exact name, GitHub Actions source App ID, trusted workflow
  path, and workflow hash; same-name checks from another source do not count.
- [ ] Capture and independently sign `RepositoryTrustBoundaryAttestationV1`: repository, two
  environments, every ruleset, three Apps/permissions, default read token, disabled global PR toggle,
  immutable releases, required-check provenance, 90-day retention, safe API-record root, capture
  actor/time. Re-fetch readable settings and require a fresh signed admin-only observation at
  preflight. Record no secret value, token, PEM, or raw privileged response.

Gate: no live workflow reference to `benchmark-live` is dispatched until every checkbox in this milestone is complete and reviewed.

## Milestone 6: Run the non-evidentiary live pilot

- [ ] Execute the first explicit live-package freeze task (the sole owner deferred by Runtime Task
  2). Create the three live `evals/manifests/public-benchmark-gpt-5.6-*.yaml` files;
  `benchmarks/campaigns/public-three-model-v1/{campaign-seed.json,price-snapshot.yaml,reviewers.yaml,protocol-reviewers.yaml,repository-trust-boundary.json,repository-trust-boundary-signature.json}`;
  and all seven `benchmarks/protocols/public-three-model-v1/*.json` files in reviewed source commit
  `C0-pilot`, together with final code/workflows. Set mode `pilot`, requested service tier `default`,
  and current signed price/trust evidence. Do not yet create `campaign.yaml` or
  `protocol-review-attestations.jsonl`.
- [ ] Obtain the exact three role-bound GitHub approvals of `C0-pilot`, capture their canonical API
  records, then create sole-child freeze commit `C1-pilot` whose only two changed paths are
  `benchmarks/campaigns/public-three-model-v1/campaign.yaml` and
  `benchmarks/campaigns/public-three-model-v1/protocol-review-attestations.jsonl`. The package binds
  `C0-pilot`; tag protected `benchmark-input-YYYYMMDD.N` at `C1-pilot`. Any extra delta, stale/
  dismissed review, expired settings capture, or self-reference restarts the two-commit freeze.
- [ ] Create the separately labeled pilot identity only from that verified tag.
- [ ] Run secret-free preflight and verify exactly 24 generation plus at most 24 judge attempts, zero retries, and reserved exposure no greater than USD 5.
- [ ] Review current official pricing against the committed snapshot and record the reviewer attestation.
- [ ] Approve and run each bounded pilot batch through `benchmark-live`.
- [ ] Verify request parameters, returned-model consistency, reasoning/visible token accounting, checkpoint transport, judge schema, exact artifact provenance, and spend reconciliation.
- [ ] Treat pilot outputs as operational evidence only; never merge them into the confirmatory result or tune thresholds for a favorable effect.
- [ ] If any protocol fix is required, create a new pilot identity and repeat this milestone from preflight.
- [ ] Revoke/rotate the pilot key if incident policy requires it.

Gate: the confirmatory input tag is forbidden until the complete pilot lineage is green and implementation/protocol inputs are frozen again.

## Milestone 7: Freeze and execute the confirmatory campaign

- [ ] Repeat the explicit two-commit freeze after the accepted pilot with new
  `C0-confirmatory -> C1-confirmatory`. `C0-confirmatory` owns the same live manifest/campaign-input/
  seven-protocol paths, final corpus/arm/dependency/runner/workflow bytes, mode `confirmatory`, new
  preregistered seed, `service_tier: default`, current official price snapshot, and fresh signed trust
  attestation. It contains neither final `campaign.yaml` nor review-attestation JSONL.
- [ ] Obtain three new exact role-bound approvals of `C0-confirmatory`; make `C1-confirmatory` its sole
  child and change only `campaign.yaml` plus `protocol-review-attestations.jsonl`. Create the next
  protected `benchmark-input-YYYYMMDD.N` tag at `C1-confirmatory`. Preflight rejects reuse of pilot
  identity/reviews, any third changed path, or a tag at `C0`.
- [ ] Run secret-free preflight; independently verify the 1,440 rows, 36×40 partition, requested models, first-batch fit, and USD 75 cap.
- [ ] Approve each bounded generation batch individually; verify predecessor state/spend/inventory before the next approval.
- [ ] Seal all 36 generation capsules and all 36 hard-score request sets.
- [ ] Approve each bounded judge batch individually; verify exact request coverage and zero-call attachments.
- [ ] On STOP, budget exhaustion, ambiguity, missing authority, or credential incident, cease provider work and take only the invalid-prefix path.
- [ ] Rotate or revoke the provider key after the final provider batch, and immediately after any credential incident.

## Milestone 8: Audit, analyze, collect, publish, and release

- [ ] Seal `EvidenceInventoryV1` before generating the blind audit packet.
- [ ] Complete both identity-bound commitment PRs before either reveal PR; retain original labels and complete dual-signoff adjudication.
- [ ] Seal deterministic analysis and one independent model-specific outcome for Sol, Terra, and Luna.
- [ ] Run the complete collector only with full 36/36/36 evidence, complete audit, and complete analysis; otherwise use the safe invalid-prefix finalizer.
- [ ] Prepare `PublicationPlanV1` from exact current `main` containing every bound audit merge.
- [ ] Approve the minimal `benchmark-publish` job to open the exact result PR.
- [ ] A maintainer verifies the exact PR head and bundle digest, confirms the automatically triggered
  `publication-pr-validate` check succeeds, submits the required human PR review, and merges through
  branch protection. There is no fork/workflow-approval action for the App-authored same-repository PR.
- [ ] The secret-free publication-state workflow re-fetches that exact PR, successful required checks,
  current human review, merge commit/tree, and bundle, then advances canonical authority to
  `RESULT_MERGED` by remote CAS, binding a complete durable checkpoint from every transient artifact
  to byte-identical files in that merge tree. A moved base/head or closed-unmerged PR is closed if still open,
  recorded as plan invalidation, and replanned from the bundle state; no branch is force-updated.
- [ ] Prepare `ResultReleasePlanV1` from the exact merge tree.
- [ ] Approve the separate release finalizer; reproduce the plan-bound annotated-tag object, create
  `benchmark-result-<campaign-id>`, stage the exact checksum-bound assets on a draft release, and
  publish once only after both verify.
- [ ] Verify the durable result directory, annotated tag, release ID, returned asset digests, immutable
  release attestation, and released extension of the durable checkpoint; transition to `RELEASED`.
- [ ] Any later correction adds a new sequence-specific result directory, PR, merge, tag, release,
  and explicit `CorrectionLineageV1` superseding the previous objects; prior paths/tags/releases and
  terminal campaign state are never rewritten.

## Milestone 9: Present the released result

- [ ] Start only after a fresh verifier proves `RELEASED`, no unresolved hold, and the exact requested
  initial/correction receipt as the canonical latest released publication pointer.
- [ ] Require `reconstruct_correction_progress(authority) is None`; an accepted defect or any
  in-flight correction prefix blocks promotion of the prior pointer.
- [ ] Update the six localized READMEs, `evals/README.md`, website, changelog, dated release note, presentation, and dated social package from the committed result bundle.
- [ ] Keep historical alpha release/social files unchanged.
- [ ] Every numeric statement names model, campaign, date interval, gate, pair/scenario denominator, confidence interval, and limitations link.
- [ ] For an `invalid_prefix` release, publish only bundle-derived operational status, incident code,
  completed/missing work, provenance, and limitations. Omit every model/arm performance number,
  comparison, direction, quality pass/fail claim, interval, ranking, or savings statement; no fake
  analysis object may satisfy the docs gate.
- [ ] Explain positive `concise - if` direction beside each value.
- [ ] Never call visible-output-token reduction billed-output, total-token, monetary, or universal-model savings.
- [ ] Publish no context-free numeric hero/social image.
- [ ] Review localized copy and presentation numbers against machine JSON before publication.

## Roadmap completion definition

The work is complete only when the chosen campaign lineage is `RELEASED`, its public evidence and checksums are durable, the provider key is rotated/revoked as planned, and the post-release presentation/social package contains only bundle-derived claims. A positive result is not required; valid negative, inconclusive, and operationally invalid outcomes are all publishable through their specified paths.
