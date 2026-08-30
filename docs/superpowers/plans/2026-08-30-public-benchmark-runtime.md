# Public Three-Model Benchmark Campaign Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the fail-closed campaign authority, exact spend accounting, bounded batch planning, closed retry policy, resumable provider controller, and GitHub Actions credential boundary required to run the pilot and three-model campaign.

**Architecture:** Keep a campaign control plane beside, not inside, the generation capsule. Pure canonical models and transition functions live under `laconian_eval.campaign`; append-only capsule evidence remains under `laconian_eval.capsule`. A secret-free job reconstructs all trusted authority artifacts, reserves exact worst-case exposure, and seals one contiguous `BatchPlanV1`. After the protected provider job has a numeric waiting/running identity and environment approval, a separate key-free receipt-writer uses the dedicated state-writer GitHub App to win the remote authority CAS for its single-use receipt. The provider job has only read permissions: its first step waits for and reconstructs that winning ref, and only its next step maps the provider key to a sequential controller. Every call boundary rechecks campaign state, hold root, spend ledger, STOP state, batch membership, and remaining monotonic time.

**Tech Stack:** Python 3.11+, Pydantic 2 strict/frozen models, integer micro-USD arithmetic, existing canonical JSON and descriptor-bound capsule primitives, pytest, Hypothesis-free deterministic property loops, Ruff, mypy, GitHub Actions with full-SHA pins, and the OpenAI Responses adapter with SDK retries disabled.

---

## Execution contract

- Approved design: `docs/superpowers/specs/2026-08-30-public-three-model-benchmark-design.md`, especially Sections 7, 8, 12, and 14.
- Before Task 1, complete and reapprove the roadmap Milestone 0 protocol/security amendment. It
  adds the literal default-tier/cache/accounting/reviewer/workflow-root contract and replaces the
  design's two-job/write-capable repository-`GITHUB_TOKEN` clauses with this plan's four-job,
  three-dedicated-App topology. It also approves the Section 7.4
  `RELEASE_BLOCKED + CORRECTION_RESULT_RELEASED -> RELEASED` edge and terminal-evidence-only
  correction behavior from `RELEASED`; every experiment, cap, evidence, and publication invariant
  remains unchanged. Until it is merged, all Runtime tasks are blocked and the older/implicit
  contracts are forbidden.
- Master roadmap: `docs/superpowers/plans/2026-08-30-public-benchmark-roadmap.md`.
- Prerequisite slice: `docs/superpowers/plans/2026-08-30-public-benchmark-foundations.md`.
- Evaluation types consumed by judge-phase batches: `docs/superpowers/plans/2026-08-30-public-benchmark-evaluation-audit.md`.
- This slice does not publish repository content, create releases, or implement statistical estimators.
- The provider controller has repository read permission only. The only step that receives `OPENAI_API_KEY` is the repository-owned controller invocation after receipt consumption.
- Every money value is an integer count of USD micro-units. Floats and binary floating-point conversions are forbidden in scheduling, reservation, reconciliation, and cap checks.
- The full campaign cap is exactly `75_000_000` micro-USD. The pilot cap is exactly `5_000_000` micro-USD.
- Confirmatory generation permits at most five 429 retries per request; the pilot permits zero. No other automatic retry class exists.
- The Actions hard timeout is 180 minutes. The controller soft deadline is 165 minutes from its monotonic start and must leave a verified checkpoint before a resumable exit.
- Every state mutation is serialized with literal concurrency group `laconian-public-benchmark-state` and `cancel-in-progress: false`.
- Every task uses focused RED, observes the named failure, implements the minimum GREEN behavior, runs the stated regression gate, and commits before the next task.

## File boundary

```text
src/laconian_eval/campaign/__init__.py       public campaign types only
src/laconian_eval/campaign/models.py         shared strict scalars and GitHub identities
src/laconian_eval/campaign/artifact_wire.py  cross-slice inner artifact envelope/authorization
src/laconian_eval/campaign/tag_binding.py    immutable benchmark-input tag verification
src/laconian_eval/campaign/preflight.py      campaign registry and exposure seal
src/laconian_eval/campaign/state.py          event/state/hold schemas and pure transition table
src/laconian_eval/campaign/authority.py      trusted-chain reconstruction and CAS mutation
src/laconian_eval/campaign/github_app_auth.py bounded dedicated-App token minting
src/laconian_eval/campaign/spend.py          exact reservations and reconciliation ledger
src/laconian_eval/campaign/retry.py          closed retry taxonomy and deterministic backoff
src/laconian_eval/campaign/batch.py          bounded prefix plan and single-use job receipt
src/laconian_eval/campaign/controller.py     sequential generation/judge orchestration
src/laconian_eval/campaign/benchmark_adapter.py neutral context/attempt artifact adapters
src/laconian_eval/campaign/benchmark_stage.py authority-verified live evaluation stages
src/laconian_eval/campaign/cli.py            fixed workflow-facing commands
src/laconian_eval/providers/base.py          structured status and Retry-After evidence
src/laconian_eval/providers/openai.py        fail-closed OpenAI error classification
src/laconian_eval/capsule/attempts.py        policy-neutral campaign-compatible backoff evidence
src/laconian_eval/capsule/execution.py       one-attempt execution seam used by controller
tools/benchmark_state_writer.py              narrow fast-forward-only canonical authority writer
tools/benchmark_capture_trust_boundary.py    read-only safe repository-settings snapshot
tools/benchmark_hard_score_stage.py          authority-verified hard-score/prepare-judge tool
tools/benchmark_seal_judge_stage.py          authority-verified seal-judge tool
pyproject.toml                               laconian-campaign entry point
.github/workflows/benchmark-preflight.yml    secret-free tag/preflight dispatch
.github/workflows/benchmark-batch.yml        prepare/provider/state-writer bounded batch
.github/workflows/benchmark-dismiss-hold.yml no-input approved benign-hold recovery
tools/benchmark_prepare_hold_dismissal.py    fixed read-only dismissal-candidate builder
tests/campaign/                              focused runtime tests
tests/test_openai_provider.py                structured provider-error and Retry-After regressions
tests/capsule/test_attempts_v2.py            campaign backoff-attempt evidence regressions
tests/capsule/test_delivery_certainty.py     delivery-certainty classification regressions
tests/capsule/test_execution.py              one-attempt execution-seam regressions
tests/capsule/test_resume.py                 resumable checkpoint integration regressions
tests/test_public_contract.py                cumulative Slice 3 export and command ownership
tests/test_ci_contract.py                    exact Runtime workflow inventory contract
tests/fixtures/public-benchmark-input-v1/             synthetic schema/workflow fixtures for this slice
evals/manifests/public-benchmark-gpt-5.6-*.yaml       live manifests, owned only by roadmap freeze
benchmarks/campaigns/public-three-model-v1/           live package records, owned only by roadmap freeze
benchmarks/protocols/public-three-model-v1/           live protocol bytes, owned only by roadmap freeze
benchmarks/runbooks/public-benchmark.md               Runtime operator and recovery runbook
```

The campaign package may import capsule canonicalization, verification, finalize, and checkpoint APIs. Capsule modules must not import the campaign package. This one-way dependency prevents generic local capsule verification from acquiring GitHub or spend authority.

## Stable runtime interfaces

The implementation must expose these names:

```text
CampaignPhase = Literal["generation", "judge"]
CampaignMode = Literal["pilot", "confirmatory"]

CampaignStateName = Literal[
    "PREFLIGHTED",
    "GENERATION_ACTIVE",
    "GENERATION_RESUMABLE",
    "GENERATION_COMPLETE",
    "HARD_SCORE_COMPLETE",
    "JUDGE_ACTIVE",
    "JUDGE_RESUMABLE",
    "JUDGE_COMPLETE",
    "PROVIDER_EVIDENCE_VERIFIED",
    "AUDIT_COMPLETE",
    "ANALYSIS_COMPLETE",
    "BUNDLE_COLLECTED",
    "PUBLICATION_PR_OPEN",
    "RESULT_MERGED",
    "RELEASED",
    "RELEASE_BLOCKED",
    "STOPPED_INVALID",
    "BUDGET_INCOMPLETE",
    "INVALID_FINALIZED",
]

FULL_CAP_USD_MICROS = 75_000_000
PILOT_CAP_USD_MICROS = 5_000_000
HARD_TIMEOUT_SECONDS = 10_800
SOFT_DEADLINE_SECONDS = 9_900
CHECKPOINT_MARGIN_SECONDS = 900

CampaignSeedV1
CampaignPlanIndexV1
CampaignRegistryV1
VerifiedPhasePlanV1
CredentialScanReceiptV1
TerminalEvidenceMutationV1
HoldDismissalMutationV1
AuthorityMutationV1
CheckpointInventoryV1
BatchPreparationRequestV1
BatchRunResultV1
RepositoryTrustBoundaryAttestationV1
BenchmarkWorkflowInventoryV1
BENCHMARK_WORKFLOW_PATHS_V1
build_benchmark_workflow_inventory
DurableAuthorityCheckpointV1
ArtifactEnvelopeV1
UploadAuthorizationV1

apply_campaign_event(
    ReconstructedAuthorityV1,
    CampaignEventV1,
    expected_state_sha256: str | null,
    expected_hold_root_sha256: str,
    expected_authority_ref_oid: str | null
) -> AuthorityMutationV1

append_terminal_evidence(
    ReconstructedAuthorityV1,
    TerminalEvidenceMutationV1,
    expected_authority_ref_oid: str
) -> AuthorityMutationV1

append_terminal_evidence_then_event(
    ReconstructedAuthorityV1,
    TerminalEvidenceMutationV1,
    CampaignEventV1,
    expected_authority_ref_oid: str
) -> AuthorityMutationV1

dismiss_invalid_event_hold(
    ReconstructedAuthorityV1,
    HoldDismissalMutationV1,
    expected_authority_ref_oid: str
) -> AuthorityMutationV1

require_no_unresolved_hold(ReconstructedAuthorityV1) -> None

prepare_batch(
    CampaignRegistryV1,
    ReconstructedAuthorityV1,
    SpendLedgerV1,
    CheckpointInventoryV1,
    BatchPreparationRequestV1
) -> PreparedBatchV1

consume_job_receipt(
    PreparedBatchV1,
    ProviderJobIdentityV1,
    PriceAttestationV1
) -> ConsumedBatchReceiptV1

run_batch(
    PreparedBatchV1,
    ConsumedBatchReceiptV1,
    ReconstructedAuthorityV1,
    ProviderFactory,
    monotonic_ns
) -> BatchRunResultV1

load_authority_verified_generation_context(
    ReconstructedAuthorityV1,
    generation_index_path: Path,
    generation_root: Path,
    expectation_path: Path,
) -> VerifiedGenerationContextIndexV1

run_hard_score_stage(
    ReconstructedAuthorityV1, generation_index_path: Path, generation_root: Path,
    output_root: Path
) -> LayerRootIndexV1

run_prepare_judge_stage(
    ReconstructedAuthorityV1, generation_index_path: Path, generation_root: Path,
    hard_score_root: Path, output_root: Path
) -> LayerRootIndexV1

run_seal_judge_stage(
    ReconstructedAuthorityV1, generation_index_path: Path, generation_root: Path,
    hard_score_root: Path, judge_request_root: Path, judge_attempt_root: Path,
    output_root: Path
) -> VerifiedBenchmarkProviderEvidenceV1
```

Public errors carry a stable code and constant message, never paths, keys, response text, raw provider exception bodies, workflow inputs, or untrusted artifact bytes.

## Task 1: Define canonical campaign and GitHub identity records

**Files:**

- Create: `src/laconian_eval/campaign/__init__.py`
- Create: `src/laconian_eval/campaign/models.py`
- Create: `src/laconian_eval/campaign/artifact_wire.py`
- Create: `tests/campaign/__init__.py`
- Create: `tests/campaign/test_models.py`
- Create: `tests/campaign/test_artifact_wire.py`

### Step 1: RED-test strict shared records

- [ ] Add payload factories for `InputTagBindingV1`, `ProviderJobIdentityV1`, `PriceAttestationV1`,
  `WorkflowIdentityV1`, `ArtifactIdentityV1`, `GitHubAppInstallationIdentityV1`,
  `ArtifactEnvelopeV1`, and `UploadAuthorizationV1`.
- [ ] Assert every model is strict, frozen, `extra="forbid"`, canonicalizable, and rejects bool-as-int, noncanonical lowercase SHA-1/SHA-256, zero IDs, blank actors, control characters, duplicate IDs, and timezone-naive timestamps.
- [ ] Assert `ProviderJobIdentityV1` contains exactly `workflow_run_id`, `run_attempt`, `job_id`, and UUID4 `batch_attempt_id`.
- [ ] Define strict frozen `PriceAttestationV1` with price-snapshot hash, exact rate/source-URL
  roots, requested service-tier literal `default`, bounded current-source capture hash and
  observation time, workflow run/attempt, numeric
  provider job/deployment ID, approval actor numeric ID/login, exact approval timestamp, captured
  approval API-record digest, disposition literal `approved`, and self digest. Reviewer identity is
  the approval actor; the job/deployment/run/attempt are the ones in `ProviderJobIdentityV1` and its
  environment record. Require the source observation to precede approval by at most 24 hours and
  receipt consumption to follow approval. A caller-created path, stale capture, mismatched actor/
  job/snapshot/rates, non-approved/dismissed record, or changed API record grants no authority.
- [ ] Require, at model validation and again when consuming authority, the exact equality
  `price_snapshot.service_tier == price_attestation.requested_service_tier == "default"`.
  Reject a missing/non-default tier or any fixture, reservation, batch, receipt, or replay whose
  price-root binding cannot reproduce that equality.
- [ ] Assert `GitHubAppInstallationIdentityV1` binds numeric app and installation IDs, exact app slug
  and bot login, repository ID, closed role `state_writer|publisher|release_finalizer`, permissions
  attestation hash, and identity digest. The three roles require three distinct app/installation IDs;
  a generic `github-actions[bot]` identity is invalid for write authority. The state-writer App uses
  repository Actions secrets mapped only to its fixed hashed step; the distinct publisher and
  release-finalizer App credentials are protected by the one approved `benchmark-publish`
  environment. `benchmark-state` and `benchmark-release` environments do not exist.
- [ ] Assert repr and validation errors never expose a secret/path canary.
- [ ] Own the cross-slice wire contract now, before any provider artifact exists. In
  `artifact_wire.py`, define strict `ArtifactEnvelopeV1` with the closed producer literals
  `generation_batch|generation_evidence_set|hard_score|judge_request|judge_attempt_batch|judge_attachment_set|provider_evidence|audit_packet|audit_evidence|analysis_evidence|complete_collector|invalid_prefix_finalizer|publication_package|publication_receipt|release_package|release_receipt|correction_bundle`;
  repository/run/attempt/job/batch and immutable input/workflow identities; nullable
  environment/deployment/approval tuple; `payload_kind: canonical_file|root_ustar`; safe payload
  name/length/digest; nullable materialized-root digest; mutually exclusive direct credential-scan
  receipt digest vs transitive source-receipt root; and self digest. Direct
  `generation_batch|judge_attempt_batch` require only the direct receipt; deterministic derived
  provider projections require only the transitive root; all other producers require both null.
  `root_ustar` requires `root-payload.tar` and a root digest; `canonical_file` requires a null root.
- [ ] Define detached `UploadAuthorizationV1` with envelope digest, exact inner filename
  `laconian-artifact.zip`, inner byte length/digest, payload length/digest, optional direct-receipt
  digest, pattern-policy digest, exact-key-scan completion literal, canonical scan time, and self
  digest. It is local authorization metadata and is forbidden inside the authorized ZIP. Add golden
  canonical vectors and reject any attempt to embed an inner/service archive digest in the envelope,
  which would create a self cycle. The record itself is nonsecret: after upload, the key-free
  recorder nests it in the exact numeric artifact locator stored by the protected authority Git
  commit. “Detached” means outside the ZIP it authorizes, not ephemeral or omitted from authority.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_models.py tests/campaign/test_artifact_wire.py -q
```

Expected RED: import fails because `laconian_eval.campaign` does not exist.

### Step 2: GREEN the strict base layer

- [ ] Implement a private `CampaignModel` with `ConfigDict(strict=True, frozen=True, extra="forbid")`.
- [ ] Use decimal integer validators for GitHub numeric IDs and exact lowercase patterns for SHA-1 and SHA-256.
- [ ] Use the existing `canonical_json` and `stable_digest` functions; do not add a second canonical JSON implementation.
- [ ] Define `campaign_record_sha256(domain, model)` so it class-bound revalidates before hashing and excludes only the record's own digest field.
- [ ] Export only stable public records from `campaign/__init__.py`.
- [ ] Rerun the focused test to GREEN.

### Step 3: Add hostile-boundary and canonical vectors

- [ ] Add a hard-coded canonical JSON vector for each identity record and independently compute its domain-separated digest in the test.
- [ ] Forge model instances with `model_construct`, hostile string subclasses, and stateful `model_dump`; public hashing must reject them with content-free `CampaignRecordError`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_models.py tests/campaign/test_artifact_wire.py tests/capsule/test_canonical.py -q
```

### Step 4: Commit

- [ ] Review `git diff --check` and commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/models.py src/laconian_eval/campaign/artifact_wire.py tests/campaign/__init__.py tests/campaign/test_models.py tests/campaign/test_artifact_wire.py
git commit -m "feat: define canonical campaign identities"
```

## Task 2: Bind immutable input tags and seal preflight

**Files:**

- Create: `src/laconian_eval/campaign/tag_binding.py`
- Create: `src/laconian_eval/campaign/preflight.py`
- Create: `src/laconian_eval/campaign/spend.py`
- Create: `tests/campaign/test_tag_binding.py`
- Create: `tests/campaign/test_input_package.py`
- Create: `tests/campaign/test_preflight.py`
- Create: `tests/campaign/test_spend.py`
- Create: `tests/campaign/test_trust_boundary.py`
- Create: `tools/benchmark_capture_trust_boundary.py`
- Create: `tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-sol.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-terra.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-luna.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign-seed.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/price-snapshot.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/reviewers.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-reviewers.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-review-attestations.jsonl`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary-signature.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/hard-score.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/judge.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/statistics.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/audit.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/retry.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/checkpoint.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/publication.json`
- Modify: `src/laconian_eval/campaign/__init__.py`

This task implements schemas and synthetic tagged-repository fixtures only. It must not create the
live `evals/manifests/public-benchmark-*`, `benchmarks/campaigns/public-three-model-v1/*`, or
`benchmarks/protocols/public-three-model-v1/*` records. The roadmap's post-implementation freeze
task owns those paths after all workflows, protocols, tests, and independent reviews exist.

### Step 1: RED-test tag resolution without credentials

- [ ] Test annotated and lightweight `benchmark-input-YYYYMMDD.N` tags in temporary Git repositories.
- [ ] Reject a branch, raw commit, moving alias, malformed date/sequence, tag outside the detached checkout ancestry, mismatched tag object, mismatched peeled commit, dirty checkout, and unavailable object.
- [ ] Patch `os.environ` with a credential canary and prove tag verification neither reads nor serializes `OPENAI_API_KEY`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_tag_binding.py -q
```

Expected RED: `tag_binding` imports fail.

### Step 2: GREEN exact tag binding

- [ ] Implement `bind_input_tag(repository: Path, tag: str, detached_head_sha: str) -> InputTagBindingV1` with non-shell Git plumbing through a narrow subprocess runner.
- [ ] Permit exactly `refs/tags/benchmark-input-[0-9]{8}\.[1-9][0-9]*`.
- [ ] Record tag name, object kind, object SHA, peeled commit SHA, and detached checkout SHA in
  `InputTagBindingV1`. Its identity digest covers only those immutable fields. Record observation
  time separately in `TagVerificationReceiptV1`, whose digest may vary and is never an input to
  `campaign_id`, registry identity, authority-ref name, plan order, or provider request identity.
- [ ] Run preflight twice for the same immutable tag with different observation times and assert the
  same input binding, campaign ID, registry identity, authority ref, seed-derived order, and plans;
  only the verification receipt differs.
- [ ] Use a fixed environment allowlist for Git subprocesses and reject replace objects, grafts, and shallow missing ancestry.
- [ ] Rerun the focused test to GREEN.

### Step 3: RED-test the real tagged campaign input package

- [ ] Load the three named manifests above and require exactly the public model IDs
  `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`, native-v2 settings, medium generation
  reasoning, medium verbosity, requested `service_tier: default`, the frozen response
  corpus/arms/runner hashes, 480 rows per
  manifest, and no fourth or missing manifest.
- [ ] Define `CampaignSeedV1` as strict canonical JSON with exactly `schema_version == "1"`,
  `algorithm == "public-hex-seed-v1"`, a preregistered public `campaign_seed` of exactly 64
  lowercase hexadecimal characters, and `seed_sha256 ==
  stable_digest("laconian-campaign-seed-v1", payload_without_digest)`. The plaintext seed is an
  immutable tagged input, not a post-run reveal or caller-supplied workflow value.
- [ ] Define `campaign.yaml` as the strict `CampaignInputPackageV1` index binding the three manifest
  paths and hashes, exact `mode: pilot|confirmatory`, `campaign-seed.json`, `price-snapshot.yaml`,
  `reviewers.yaml`, `protocol-reviewers.yaml`, `protocol-review-attestations.jsonl`, the repository trust-boundary attestation
  and detached signature, all seven protocol
  paths/hashes, corpus/arm/runner/dependency hashes, mode-independent caps, and its own digest.
- [ ] Define `BenchmarkWorkflowInventoryV1`, the exact 15-member
  `BENCHMARK_WORKFLOW_PATHS_V1` tuple named by these plans, and
  `build_benchmark_workflow_inventory(tagged_root)`. The builder opens those paths from the verified
  `C0` tree, sorts `(relative_path, sha256)` by UTF-8 bytes, binds the workflow-policy
  version/full-SHA action-pin proof, and computes the class-bound inventory root. No workflow hash or
  inventory root is a source-code constant before the live freeze.
  Runtime Task 2 tests build a synthetic temporary `C0` containing all 15 paths; they do not depend on
  future Slice 4 files or the then-partial cumulative `tests/test_ci_contract.py`.
  `campaign.yaml`, all three protocol-review attestations, and the registry bind the same root.
  Publication Task 13 adds the final cross-slice test proving its completed 15-workflow enumeration
  exactly equals this production constant and verifies the real-byte root. Live `C0` population is
  owned only by the roadmap freeze. Unknown/missing/duplicate workflows or a hash from `C1`/mutable
  `main` fail.

  The path tuple itself is the following literal UTF-8 byte order; only member hashes/root wait for
  the verified `C0` bytes:

  ```python
  BENCHMARK_WORKFLOW_PATHS_V1 = (
      ".github/workflows/audit-pr-validate.yml",
      ".github/workflows/benchmark-analysis.yml",
      ".github/workflows/benchmark-audit.yml",
      ".github/workflows/benchmark-batch.yml",
      ".github/workflows/benchmark-collect-complete.yml",
      ".github/workflows/benchmark-dismiss-hold.yml",
      ".github/workflows/benchmark-docs-validate.yml",
      ".github/workflows/benchmark-evidence.yml",
      ".github/workflows/benchmark-finalize-invalid.yml",
      ".github/workflows/benchmark-hard-score.yml",
      ".github/workflows/benchmark-preflight.yml",
      ".github/workflows/benchmark-publication-state.yml",
      ".github/workflows/benchmark-publish.yml",
      ".github/workflows/benchmark-release.yml",
      ".github/workflows/publication-pr-validate.yml",
  )
  ```
- [ ] Require fixture `price-snapshot.yaml` to exercise service tier literal `default`, canonical UTC observation time, integer micro-USD
  rates for every input/cached-input/output component used by all four model roles, exact official
  HTTPS source URLs, rounding version, and one independent verification attestation. During
  implementation, synthetic fixture rates/URLs are explicitly non-live. The final freeze task
  re-checks then-current official sources and commits the real exact rates; an unverifiable or
  changed rate blocks that task rather than accepting a blank, estimated, or stale value.
- [ ] Require a nonnull reviewed cache-write rate for every frozen model alias and an attestation
  that the exact explicit/no-breakpoint cache mode and `cache_write_tokens` usage field are supported
  by the tagged API contract. Missing support/rate blocks the tag; preflight may not assume writes are
  free or silently map them to cached reads.
- [ ] The synthetic package exercises `mode: pilot`; after the live pilot gate, the confirmatory
  freeze is a separately reviewed commit/tag whose package declares
  `mode: confirmatory`. `laconian-campaign preflight` has no mode flag: mode comes only from the
  verified tagged package and is bound into campaign identity. A mode edit always creates a new tag,
  registry, plan index, and campaign ID.
- [ ] Require live `reviewers.yaml` to preregister exactly two distinct maintainer-supplied GitHub
  numeric account IDs/logins for the human audit plus their required commit-signing verification
  mode and optional exact key fingerprints. Its canonical digest is the audit-reviewer-registry hash.
  Synthetic identities are permitted only in tests. Do not create the live file or
  input tag until the final freeze receives both real identities; missing, duplicate, placeholder,
  or unverified identities fail preflight. Task 2 fixtures use explicitly synthetic identities.
- [ ] After Slice 2 Task 3 commits its neutral reviewer/context contract, load the benchmark-owned strict
  `ProtocolReviewerRegistryV1` from `protocol-reviewers.yaml`; Runtime must import/class-bound
  revalidate that type and must not define or re-export a second class. It contains exactly three
  role-bound `ProtocolReviewerBindingV1`
  records in order `statistical_method`, `blind_judge_audit_protocol`, `security_evidence`, each with
  a distinct non-bot numeric GitHub account ID/login, signing verification mode, and required exact
  key/certificate fingerprint. Its canonical digest is independent of the two-person audit registry;
  no identity is inferred from an attestation line. Live freeze requires all three real bindings,
  while fixtures are explicitly synthetic. This is an explicit Task 2 integration edge on Slice 2
  Task 3; tag/Git/pricing work may proceed earlier, but preflight cannot turn GREEN without it.
  Slice 2 Task 8 later extends the already-owned context into the post-judge provider bridge.
- [ ] Require the seven canonical protocol files to be byte-complete projections of the implemented
  hard-score, judge, statistics, audit, retry, checkpoint, and publication contracts. Tests
  independently recompute every protocol hash and reject a file generated from a different source
  revision or containing an unknown/free-form execution field.
- [ ] Define strict `ProtocolReviewAttestationV1` with closed role
  `statistical_method|blind_judge_audit_protocol|security_evidence`, numeric GitHub reviewer account
  ID/login, exact prior `reviewed_source_commit_sha`, source PR number/node ID, exact GitHub review
  ID, review commit/head SHA, state literal `APPROVED`, canonical submitted time, fixed review-body
  digest, captured API-record digest, exact `C0` workflow-inventory root, all seven ordered protocol hashes,
  audit-reviewer-registry hash, protocol-reviewer-registry hash, disposition literal `approved`, and
  self digest. The statistical role explicitly
  covers statistics/false-fail/audit estimators; blind-judge/audit covers hard score, blinding,
  commitment/reveal/adjudication, and reviewer registry; security/evidence covers retry,
  checkpoint, credential, authority, artifact, and publication protocols. The JSONL file contains
  exactly one canonical line per role, in that order, with three distinct non-bot reviewers. The
  reviewed source commit contains all final code, workflows, manifests, seed, price, both reviewer
  registries, trust-boundary records, and protocol bytes, excluding only `campaign.yaml` and the
  review-attestation JSONL. The freeze commit
  is its sole child/parented commit and may add exactly those two files; preflight proves every
  attested byte hash against both trees. This avoids an impossible self-reference to the commit
  containing the attestation. Preflight exhaustively re-fetches the exact PR/head and each review ID
  through GitHub's read API, requires the current undismissed `APPROVED` record at C0 and the fixed
  body digest, and canonical-compares the captured API record. A fabricated, dismissed, stale,
  superseded, or source-commit/workflow/protocol/audit-registry/protocol-registry hash mismatch,
  placeholder identity, duplicate reviewer, or non-approved disposition blocks
  preflight. Test fixtures may use synthetic identities; the live tag may not.
- [ ] Add an anti-cycle golden Git fixture: create reviewed source commit `C0`, create freeze commit
  `C1` whose sole parent is `C0` and whose only delta is `campaign.yaml` plus the three captured
  review records/attestations, and verify attestations
  bind `C0` plus exact component hashes while the input tag peels to `C1`. Reject an attestation that
  claims `C1`, a second parent, an extra diff path, changed source bytes, or a package self-digest
  recursion. Fake the exact GitHub review GETs; changing state/actor/head/body/time/API digest or
  removing one response fails.
- [ ] Define strict `RepositoryTrustBoundaryAttestationV1` as a nonsecret, canonical snapshot binding
  the numeric repository ID and owner/name; the two environment IDs, names, deployment policies,
  reviewer rules, prevent-self-review/admin-bypass settings, and safe configuration digests; every
  input/result/authority/result-branch/`main` ruleset ID, enforcement mode, target pattern, bypass or
  allowed-actor set, and canonical API-record digest; the three pairwise-distinct App installation
  identities and permission-attestation hashes; default repository `GITHUB_TOKEN: read`; the global
  Actions create/approve-PR toggle `false`; immutable Releases enabled; artifact retention `90`; and
  the ordered required-check
  names with exact workflow path/hash plus expected source GitHub App ID. It also binds the numeric
  settings-capture actor, canonical capture time, ordered safe settings-API-record root, and its own
  digest. No secret value, PEM, token, environment secret metadata, or free-form response body is
  permitted.
- [ ] Define a detached `RepositoryTrustBoundarySignatureV1` binding the attestation digest, the
  preregistered `security_evidence` reviewer ID/login, signing mode and exact key fingerprint from
  `protocol-reviewers.yaml`, signature algorithm/bytes digest, and self digest. Verify it over domain-separated
  canonical attestation bytes. The reviewed source commit `C0` contains both records; the later
  `ProtocolReviewAttestationV1` for `security_evidence` independently proves that reviewer approved
  the complete `C0`, so neither record refers to its own containing commit.
- [ ] Add exact-settings tests with fake paginated GitHub responses. Secret-free preflight re-fetches
  every endpoint readable by its repository token and canonical-compares it with the captured
  records. Admin-only settings require a separately produced signed observation no older than 24
  hours at dispatch; a changed/unreadable/partial setting, App permission, source-App check binding,
  ruleset, retention value, or signature blocks preflight. Never weaken this to a human checkbox.
- [ ] Implement `tools/benchmark_capture_trust_boundary.py` as a separate read-only maintainer tool,
  not a workflow/CLI command. It accepts only fixed repository and output paths, reads a short-lived
  admin settings-read token from `GITHUB_SETTINGS_READ_TOKEN`, calls an exact GET-only endpoint
  allowlist with bounded pagination/body sizes, projects only the schema's safe fields, exclusively
  writes canonical attestation bytes, and scrubs the token. It cannot mutate settings, inspect secret
  names/values, choose App/ruleset/check subsets, or create a signature. The registered
  `security_evidence` reviewer signs those bytes separately; preflight verifies both. Tests prove raw
  API payload/token canaries never reach output/log/error and every omitted page/record fails.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_trust_boundary.py tests/campaign/test_input_package.py -q
```
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_input_package.py -q
```

Expected RED: the strict input-package loader and real frozen files do not exist.

### Step 4: RED-test the complete secret-free registry and seed-derived order

- [ ] Build fixture manifests for Sol, Terra, and Luna from Slice 1 and assert exactly three 480-row parent plans.
- [ ] Assert `CampaignPlanIndexV1` contains exactly 36 unique 40-row shard plans whose disjoint
  ordered union equals all 1,440 parent rows. Its canonical base order is bytewise
  `(model_id UTF-8, scenario_uid raw SHA-256 bytes)`; its published permutation is the only order
  accepted by generation batches and the only shard order used to flatten later judge requests.
- [ ] Freeze `order_algorithm == "numpy-pcg64-permutation-v1"`, `order_domain ==
  "laconian-shard-order-v1"`, and derive the unsigned 128-bit seed from the first 16 bytes of
  `SHA256(domain || NUL || campaign_seed ASCII || NUL || peeled_input_commit ASCII || NUL ||
  judge_protocol_sha256 ASCII)`. Feed that integer to `numpy.random.Generator(PCG64(seed))` and call
  `permutation(36)` exactly once. Add a hard-coded golden 36-index permutation and derived-seed
  vector, computed independently in the test rather than by the production helper.
- [ ] Require `CampaignPlanIndexV1` to bind the canonical shard hashes, exact permutation,
  seed/domain/algorithm, ordered shard hashes, and its own digest. When hard-score completes, the
  judge-phase `BatchPlanV1` must traverse `JudgeRequestAttachmentV1` records in this same ordered
  shard sequence and each attachment's sealed request order; it binds the resulting ordered request
  IDs and attachment-index root before any judge call.
- [ ] Assert pilot mode selects one shared scenario, both locales, four arms, one repetition, three generation models, no retries, at most 24 generation attempts, and at most 24 judge attempts.
- [ ] Reject arbitrary model names, arbitrary shell values, missing or extra manifests, a non-medium generation protocol, a changed case/arm/runner hash, price snapshot mismatch, projected exposure above cap, or a first batch that cannot fit.
- [ ] Assert `CampaignRegistryV1` binds:

```text
campaign_id, mode, input tag object and peeled commit,
current preflight workflow path/SHA-256, exact 15-workflow inventory/root, three manifest/parent-plan hashes,
ordered 36 shard hashes, exact tagged `src/laconian_eval/benchmark/hard_score.py` source SHA-256,
hard-score/judge/statistical/audit protocol path/hash fields,
the plaintext `CampaignSeedV1` and its hash, `CampaignPlanIndexV1` hash,
all seven ordered protocol hashes, price snapshot, the exact two audit-reviewer account/signing
bindings and audit-reviewer-registry hash, the exact three role-bound protocol-reviewer bindings and
protocol-reviewer-registry hash,
all three protocol-review attestation records/hashes and their ordered root,
the repository trust-boundary attestation/signature hashes and ordered settings-record root,
planned initial calls, planned maximum attempts,
requested service-tier root (every generation/judge request exactly `default`), projected reserved
micro-USD, cap micro-USD, registry hash
```

Derive the hard-scorer source hash by descriptor-reading that one path from verified `C0`; derive
the hard-score protocol hash from its exact member of the seven-file tagged protocol inventory.
Neither is accepted as a manifest/CLI/workflow scalar. Re-hash both during registry load, bind their
paths and hashes into the registry digest, and reject a self-consistent substituted registry whose
expected digest does not equal the input-tag package bound by canonical preflight authority.

- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_preflight.py -q
```

Expected RED: registry models and `seal_preflight` are absent.

### Step 5: GREEN the tagged package and deterministic preflight

- [ ] Implement a strict `load_campaign_input_package(tag_root: Path) -> VerifiedCampaignInputPackageV1`
  that opens only the fixed paths above, rejects symlinks/aliases/duplicates/unknown members, and
  proves every path and digest is reachable from the exact peeled input commit. Workflow inputs may
  select only the immutable tag; they may not override seed, reviewer, price, model, or protocol.
- [ ] Derive `campaign_id` with `stable_digest("laconian-campaign-v1", {"tag_binding_sha256":
  tag_binding_sha256, "protocol_sha256s": list(protocol_sha256s), "mode": mode,
  "campaign_seed_sha256": campaign_seed.seed_sha256, "campaign_plan_index_sha256":
  campaign_plan_index.index_sha256, "audit_reviewer_registry_sha256":
  audit_reviewer_registry_sha256, "protocol_reviewer_registry_sha256":
  protocol_reviewer_registry_sha256})`.
  `protocol_sha256s` is the frozen tuple `(hard-score, judge, statistics, audit, retry, checkpoint,
  publication)` in that order.
- [ ] Materialize and validate every parent plan and `ShardPlanV1` through Slice 1 APIs; never reconstruct plan IDs in campaign code.
- [ ] Construct and revalidate `CampaignPlanIndexV1` from the tagged plaintext seed and verified
  shard plans. Store the full `CampaignSeedV1`, not merely a commitment, in `CampaignRegistryV1` so
  bootstrap, judge blinding, shard ordering, and audit sampling all consume the same verified bytes.
- [ ] Implement `PriceSnapshotV1` and the pure `token_charge_usd_micros` / `project_worst_case_exposure` functions in `spend.py`. Each token component rounds up independently; all inputs and outputs are strict nonnegative integers.
- [ ] Calculate worst-case request exposure through those pure functions and enforce exactly `5_000_000` pilot or `75_000_000` confirmatory micro-USD.
- [ ] Emit a canonical `PreflightSummaryV1` that contains counts, price URLs, reservations, and hashes but no prompts, outputs, credentials, arbitrary paths, or environment values.
- [ ] Rerun tag, spend-pricing, and preflight tests to GREEN.

### Step 6: Commit

- [ ] Commit the tag and preflight slice:

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/tag_binding.py \
  src/laconian_eval/campaign/preflight.py \
  src/laconian_eval/campaign/spend.py \
  tools/benchmark_capture_trust_boundary.py \
  tests/campaign/test_tag_binding.py \
  tests/campaign/test_input_package.py \
  tests/campaign/test_preflight.py \
  tests/campaign/test_spend.py \
  tests/campaign/test_trust_boundary.py \
  tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-sol.yaml \
  tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-terra.yaml \
  tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-luna.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign-seed.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/price-snapshot.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/reviewers.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-reviewers.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-review-attestations.jsonl \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary-signature.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/hard-score.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/judge.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/statistics.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/audit.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/retry.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/checkpoint.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/publication.json
git commit -m "feat: seal benchmark campaign preflight"
```

## Task 3: Implement the normative state machine and invalid-event holds

**Files:**

- Create: `src/laconian_eval/campaign/state.py`
- Create: `src/laconian_eval/campaign/authority.py`
- Create: `src/laconian_eval/campaign/github_app_auth.py`
- Create: `tools/benchmark_state_writer.py`
- Create: `tests/campaign/test_state.py`
- Create: `tests/campaign/test_authority.py`
- Create: `tests/campaign/test_github_app_auth.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

### Step 1: RED-test the exact transition table

- [ ] Parameterize every allowed edge:

```text
none + PREFLIGHT_SEALED -> PREFLIGHTED
PREFLIGHTED|GENERATION_RESUMABLE + BATCH_RECEIPT_CONSUMED -> GENERATION_ACTIVE
GENERATION_ACTIVE + NO_DISPATCH_PROVED|VERIFIED_PARTIAL -> GENERATION_RESUMABLE
GENERATION_ACTIVE + GENERATION_SET_SEALED -> GENERATION_COMPLETE
GENERATION_COMPLETE + HARD_SCORE_SET_SEALED -> HARD_SCORE_COMPLETE
HARD_SCORE_COMPLETE|JUDGE_RESUMABLE + BATCH_RECEIPT_CONSUMED -> JUDGE_ACTIVE
JUDGE_ACTIVE + NO_DISPATCH_PROVED|VERIFIED_PARTIAL -> JUDGE_RESUMABLE
JUDGE_ACTIVE + JUDGE_SET_SEALED -> JUDGE_COMPLETE
JUDGE_COMPLETE + EVIDENCE_INVENTORY_SEALED -> PROVIDER_EVIDENCE_VERIFIED
PROVIDER_EVIDENCE_VERIFIED + AUDIT_SEALED -> AUDIT_COMPLETE
AUDIT_COMPLETE + ANALYSIS_SEALED -> ANALYSIS_COMPLETE
ANALYSIS_COMPLETE + COMPLETE_BUNDLE_SEALED -> BUNDLE_COLLECTED
BUNDLE_COLLECTED + PUBLICATION_PR_OPENED -> PUBLICATION_PR_OPEN
BUNDLE_COLLECTED + COMPLETE_PUBLICATION_PLAN_INVALIDATED -> BUNDLE_COLLECTED
PUBLICATION_PR_OPEN + RESULT_MERGED -> RESULT_MERGED
PUBLICATION_PR_OPEN + COMPLETE_PUBLICATION_PLAN_INVALIDATED -> BUNDLE_COLLECTED
PUBLICATION_PR_OPEN + INVALID_PUBLICATION_PLAN_INVALIDATED -> INVALID_FINALIZED
RESULT_MERGED + RESULT_RELEASED -> RELEASED
RESULT_MERGED + RELEASE_PLAN_INVALIDATED -> RELEASE_BLOCKED
RELEASE_BLOCKED + CORRECTION_RESULT_RELEASED -> RELEASED
any nonterminal pre-publication + PERMANENT_STOP -> STOPPED_INVALID
any ready/resumable provider state + BUDGET_EXHAUSTED -> BUDGET_INCOMPLETE
STOPPED_INVALID|BUDGET_INCOMPLETE + INVALID_PREFIX_SEALED -> INVALID_FINALIZED
INVALID_FINALIZED + INVALID_PUBLICATION_PLAN_INVALIDATED -> INVALID_FINALIZED
INVALID_FINALIZED + INVALID_PUBLICATION_PR_OPENED -> PUBLICATION_PR_OPEN
```

- [ ] Cover every illegal source/event pair, a STOP-to-live jump, partial-to-complete jump, release-blocked continuation, duplicate event, skipped parent, wrong phase-plan, wrong spend hash, wrong inventory root, and unresolved hold.
- [ ] `CORRECTION_RESULT_RELEASED` is the sole release-blocked escape: require the exact next
  correction sequence; predecessor terminal-evidence root; prior pointer digest; new pointer digest;
  correction-lineage digest; publication/merge/release receipt digests; result-tree, annotated-tag,
  and release-asset roots; identical prior/new bundle-kind literals; and prior/new release-status
  literals, while retaining the entire
  blocked-state/event history. Runtime treats these as opaque strict hashes and sequence invariants:
  Slice 4 alone constructs and verifies the richer pointer/lineage records before creating the event.
  Reject every other event from `RELEASE_BLOCKED`; `campaign.state` must never import a Slice 4
  publication type.
- [ ] `RELEASE_PLAN_INVALIDATED` must bind a closed failure phase plus the canonical blocked-external-
  objects digest and observed tag/release/asset roots, including an explicit empty/pre-tag record.
  Runtime validates only the strict opaque phase/hash invariants and retains them in state evidence;
  Slice 4 owns `BlockedReleaseObjectsV1` construction/re-fetch. A post-call failure may not use the
  preflight-empty form, and no later event can erase or relabel an observed orphan object.
- [ ] Assert each event is single-use, parent-bound, canonical, and carries an exact source workflow/actor or reviewer identity.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_state.py -q
```

Expected RED: state types and transition function are absent.

### Step 2: GREEN pure transition models

- [ ] Define a discriminated `CampaignEventV1` union with one payload model per event type and event-specific evidence fields.
- [ ] Define `CampaignStateV1` with exactly schema version, campaign ID, transition number, state, previous-state hash, event type/hash, tag object, peeled commit, active phase-plan hash, spend-ledger hash, inventory Merkle root, optional STOP/incident ID, authority identity, and state hash.
- [ ] Define `InvalidEventHoldV1` binding rejected event bytes/hash, last valid state/spend/inventory/hold roots, source identity, enumerated reason, and hold hash.
- [ ] Close `InvalidEventReasonV1`. Only `duplicate_exact_accepted_event`,
  `stale_expected_root_noop`, and `lost_remote_cas_sibling_noop` can derive
  `HoldDismissibilityV1 == "dismissible_noop"`, and only after reconstruction proves the candidate
  would add no new state, spend, inventory, terminal evidence, or external side effect. Reasons for
  malformed/unknown event, illegal transition, identity/signature, tag/provenance/artifact,
  workflow/permission, price/spend, reservation, ambiguous delivery, credential/secret, policy/
  security, STOP/budget, audit, publication, or release defects always derive `nondismissible`.
  Caller/event bytes never supply the dismissibility field; one total immutable mapping does.
- [ ] Define `HoldDismissalMutationV1` with the exact hold hash, predecessor/result unresolved-hold
  roots, unchanged state/spend/inventory/terminal-evidence roots, numeric trigger and distinct
  `benchmark-publish` approval identities, expected authority-ref OID, and self digest. It is a hold
  mutation, never a `CampaignEventV1`, and cannot change state name/hash.
- [ ] Encode allowed edges as one immutable mapping, then enforce event-specific evidence before constructing the next state.
- [ ] Rerun `test_state.py` to GREEN.

### Step 3: RED-test durable authority reconstruction and CAS

- [ ] Feed shuffled, missing, duplicated, expired, superseded, and forked authority envelopes; accept only one exhaustive parent-linked chain rooted at the exact protected canonical ref
  `refs/heads/benchmark-authority/{campaign_id}`. Operator-supplied artifact subsets and "latest by
  name" discovery are never authority.
- [ ] Build two deterministic authority commits with the same expected canonical-ref OID and simulate
  two non-force writers. Exactly one fast-forward succeeds; the sibling fails atomically, and
  reconstructing from the winning ref yields its exact state, spend, hold, inventory, and artifact
  locator roots.
- [ ] Test GitHub App auth with a local disposable RSA key and fake HTTPS transport: bounded JWT
  `iat/exp/iss`, exact installation endpoint/audience, permission response matching the preregistered
  role, token expiry margin, 0600 PEM lifecycle, fixed `openssl` argv/environment, and content-free
  failures. Inject private-key/token canaries and prove neither enters repr, stdout/stderr, exception,
  receipt, archive, child environment outside the signer, or filesystem after return.
- [ ] Prove an invalid event leaves the last state and every spend/artifact record byte-identical while atomically adding one hold.
- [ ] Test benign hold dismissal in every state, including `RESULT_MERGED` and `RELEASED`. Require an approved `benchmark-publish` identity distinct from both rejected-event source and workflow trigger actor.
- [ ] Exhaustively parameterize every `InvalidEventReasonV1` through the derivation mapping. Prove
  each of the three benign reasons still becomes nondismissible when its byte-level no-op proof is
  absent, and that no identity/provenance/spend/delivery/credential/STOP/release/security hold can be
  dismissed under any actor or terminal state.
- [ ] Test nondismissible terminal paths: a pre-merge `PERMANENT_STOP` hold, the accepted post-merge
  `RELEASE_PLAN_INVALIDATED -> RELEASE_BLOCKED` state transition, and post-release correction-lineage
  evidence stages appended without rewriting history. A `correction_release` mutation leaves
  `RELEASED` unchanged, but from `RELEASE_BLOCKED` the read-only recorder must derive both the
  correction-release envelope and the separately verified `CORRECTION_RESULT_RELEASED` event in one
  ordered candidate package. The state writer installs both envelopes in one deterministic authority
  commit and one expected-ref remote CAS.
- [ ] Define strict `DurableArtifactSubstitutionV1` and `DurableAuthorityCheckpointV1`. A checkpoint
  binds campaign ID, publication ID, correction sequence, stage literal `merged|released`,
  predecessor authority-envelope root, exact merge commit/result path/bundle digest, and a complete byte-sorted mapping from every
  transient artifact locator/envelope/payload/materialized-root digest needed by the authority DAG to
  one or more byte-identical regular files in that immutable merge tree. The released form extends
  the merged checkpoint with its digest, annotated tag object/target, release ID, immutable release
  attestation digest, and both exact asset digests. It has no caller-selected omissions and its own
  digest; unmapped private bytes make the checkpoint impossible rather than silently durable.
- [ ] Put the merged checkpoint inside the accepted `RESULT_MERGED` event evidence and the extended
  checkpoint inside `RESULT_RELEASED` or `CORRECTION_RESULT_RELEASED` evidence. Each binds only the
  predecessor authority root, so event/state hashing has no cycle. Test a byte changed at the
  committed result path, incomplete mapping, wrong merge/tree/tag/asset, locator substitution,
  duplicate mapping, and a checkpoint that claims its resulting state hash.
- [ ] Define and test `TerminalEvidenceMutationV1` for the closed evidence kinds
  `correction_defect`, `correction_publication`, `correction_merge`, `correction_release`, and
  the two distinct kinds `correction_publication_invalidation` and
  `correction_release_invalidation`; the generic `correction_invalidation` alias is invalid. It binds campaign, unchanged terminal `RELEASED|RELEASE_BLOCKED` state
  name/hash, evidence digest, exact source identity/artifact provenance, predecessor terminal-evidence
  root, and mutation digest. Reject it in every nonterminal state, reject unknown kinds/order gaps,
  and prove it cannot dismiss a hold or directly change state/spend/inventory. Require publication
  invalidation only after its publication record and allow a new publication attempt for the same
  correction sequence; require release invalidation only after merge and make it terminal for that
  correction sequence. A new `correction_defect` is illegal until the prior sequence ends in
  `correction_release` or `correction_release_invalidation`. Accept every contiguous persisted prefix
  as resumable and reject gaps, duplicate terminalization, or two active sequences. Add sequence tests for
  append correction-release evidence -> apply `CORRECTION_RESULT_RELEASED` from `RELEASE_BLOCKED` in
  one candidate package; reject reordering, omission, separate commits, or a stale expected ref. No
  docs authority exists until that single remote CAS succeeds.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_authority.py tests/campaign/test_github_app_auth.py -q
```

Expected RED: authority reconstruction/CAS APIs are absent.

### Step 4: GREEN authority envelopes

- [ ] Implement `AuthorityEnvelopeV1` as the append-only unit containing exactly one accepted state
  transition, hold/dismissal mutation, or `TerminalEvidenceMutationV1`, its trusted artifact
  provenance, predecessor envelope hash, and envelope hash. Implement `append_terminal_evidence` as
  a pure expected-root mutation; the same narrow remote state writer performs the CAS.
- [ ] Define `AuthorityMutationV1` as a strict frozen candidate package containing campaign ID,
  expected authority-ref OID (nullable only for initial creation), predecessor authority-head/state/
  hold/terminal-evidence roots, one or more canonically ordered new `AuthorityEnvelopeV1` records,
  all resulting roots, trusted artifact provenance, and mutation digest. The writer replays every
  envelope before constructing one deterministic child commit; candidates are composable only
  through a pure builder, never by concatenating JSON.
- [ ] Implement `append_terminal_evidence_then_event` for the sole two-envelope case required by a
  successful correction release from `RELEASE_BLOCKED`. It applies the terminal mutation to a pure
  intermediate reconstructed authority, validates `CORRECTION_RESULT_RELEASED` against that exact
  intermediate root, and returns one `AuthorityMutationV1` with both envelopes. Reject any other
  event/kind/count, stale OID, reordered envelopes, or two separate writer commits. Implement
  `dismiss_invalid_event_hold` analogously for exactly one `HoldDismissalMutationV1` envelope.
- [ ] Define each authority Git commit as a canonical tree containing the current head record,
  immutable envelope bytes, and the exact numeric artifact IDs/service/payload digests required to
  reconstruct every ancestor. The commit has the previously observed authority-ref OID as its sole
  parent. Before `RESULT_MERGED`, reject every missing/expired ancestor. At or after
  `RESULT_MERGED`, an expired transient locator may be substituted only through the complete
  accepted `DurableAuthorityCheckpointV1`: fetch the exact protected merge tree by object ID,
  descriptor-safely reverify every mapped byte/digest, and replay the entire chain. At or after
  `RESULT_RELEASED`, additionally verify the annotated tag and immutable release assets when the
  released checkpoint claims them. A missing mapping, mutable ref lookup, merely same-named file,
  changed durable byte, or incomplete checkpoint remains fatal. The protected authority Git history
  itself stores every envelope/checkpoint byte and is never replaced by Actions-artifact discovery.
- [ ] Implement `tools/benchmark_state_writer.py` as a provider-secret-free writer. A fixed trusted
  writer step maps only the dedicated state-writer GitHub App ID, installation ID, and private key
  from the three repository Actions secrets; it uses no environment gate and every repository
  `GITHUB_TOKEN` remains read-only. The tool creates a bounded JWT with a 0600 temporary PEM,
  signs through a fixed `openssl` subprocess/environment allowlist, exchanges it for a short-lived
  installation token, deletes the PEM, and never returns or logs either secret/token. It
  verifies a fixed candidate package and current remote ref, reconstructs both roots, creates the
  deterministic child commit, and updates only the exact authority ref with a non-force
  fast-forward. It cannot force, delete, retarget, merge, approve, release, or select artifacts.
  The authority-ref ruleset grants bypass only to this dedicated App installation; repository
  `GITHUB_TOKEN`, publisher App, and release App are not eligible.
- [ ] Compute `unresolved_hold_root_sha256` from byte-sorted active hold hashes.
- [ ] Implement `require_no_unresolved_hold` in `campaign.authority` with the exact signature
  `require_no_unresolved_hold(authority: ReconstructedAuthorityV1) -> None`; export it from
  `campaign.__init__`. Keep `apply_campaign_event` pure: it constructs a candidate mutation bound
  to expected state, hold, and authority-ref OID. The narrow writer re-verifies all three immediately
  before the remote fast-forward.
- [ ] Run state and authority files together to GREEN.

### Step 5: Commit

- [ ] Run `git diff --check` and commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/state.py src/laconian_eval/campaign/authority.py src/laconian_eval/campaign/github_app_auth.py tools/benchmark_state_writer.py tests/campaign/test_state.py tests/campaign/test_authority.py tests/campaign/test_github_app_auth.py
git commit -m "feat: add fail-closed campaign authority"
```

## Task 4: Extend exact pricing with reservations and reconciliation

**Files:**

- Modify: `src/laconian_eval/campaign/spend.py`
- Modify: `tests/campaign/test_spend.py`
- Modify: `src/laconian_eval/campaign/preflight.py`
- Modify: `tests/campaign/test_preflight.py`

### Step 1: RED-test exact ledger pricing

- [ ] Define golden vectors for uncached input, cached input, cache-write input, output, and zero
  tokens using:

```python
def token_charge_usd_micros(tokens: int, rate_usd_micros_per_million: int) -> int:
    numerator = tokens * rate_usd_micros_per_million
    return (numerator + 999_999) // 1_000_000
```

- [ ] Assert each component rounds up independently, the sum is overflow-bounded,
  `cached_input_tokens + cache_write_tokens <= input_tokens`, and reasoning tokens remain part of
  provider output billing. Bind the manifest's exact cache policy and reject provider usage that
  claims cache activity disallowed by that policy.
- [ ] For trusted usage, derive `uncached_input_tokens = input_tokens - cached_input_tokens -
  cache_write_tokens`, then charge the three nonoverlapping input components and output independently.
  If cached/write detail is absent or invalid, retain the full worst-case reservation; never infer
  zero cache writes from omission.
- [ ] Make `PriceSnapshotV1` bind requested provider service tier exactly `default` and carry ordinary and every applicable long-context-tier rate for uncached
  input, cached input, cache writes, and output plus the exact tier threshold for attestation. Preflight
  recomputes Slice 1's versioned secret-free conservative input bound and requires every request to
  remain at or below the frozen 272,000-token standard-tier boundary. Any request above that
  boundary is `definitely_not_sent`; the campaign never authorizes or reserves a long-context tier,
  even when the snapshot records its rate.
- [ ] Reject floats, decimal exponent strings, negative values, bools, unbound rates, and a snapshot without source URL/effective date/hash.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_spend.py -q
```

Expected RED: pricing primitives exist from Task 2, but reservation, reconciliation, and ledger models are absent.

### Step 2: RED-test append-only attempt reservations

- [ ] Reserve one row for every initial attempt and every allowed retry in the frozen batch, each
  with plan item, attempt number, input bound, cache policy, worst-case cache-write bound, output cap,
  requested service tier `default`, applicable context pricing tier, price snapshot hash, and exact
  worst-case micro-USD. Conservatively price
  each possible input token at the maximum compatible uncached/cache-write rate unless the frozen
  policy and request identity prove a narrower mutually exclusive component.
- [ ] Reconcile independently as `never_started`, `trusted_usage`, `definitely_rejected_zero`, or `retained_worst_case`.
- [ ] Prove missing usage, ambiguous delivery, runner loss, unverified checkpoint, and prior failed retry retain full exposure.
- [ ] Prove a later success never releases an earlier attempt reservation.
- [ ] Prove rerun/replacement reservations are additive and a receipt cannot be reused.
- [ ] Test a 429-retry-success chain with both attempts separately accounted: the definitely rejected
  first attempt may become `definitely_rejected_zero` only under the frozen verified zero-billing
  rule; otherwise it retains its reservation, while the successful attempt uses trusted usage.
- [ ] Assert `charged_or_reserved + next_batch_reservation <= cap` before a plan may be sealed; exact equality is allowed.

### Step 3: GREEN ledger types and verifier

- [ ] Implement canonical `PriceSnapshotV1`, `RequestReservationV1`, `SpendEventV1`, `SpendLedgerV1`, and `SpendSummaryV1`.
- [ ] Make `append_spend_event` require the exact predecessor ledger hash, strictly increasing row number, single-use reservation identity, and current campaign/price hashes.
- [ ] Implement a streaming verifier that recomputes totals and refuses unknown event kinds or nonterminal reconciliation gaps.
- [ ] Integrate `seal_preflight` with the exact pilot/full cap and projected attempt counts.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_spend.py tests/campaign/test_preflight.py -q
```

### Step 4: Commit

- [ ] Commit spend and now-GREEN preflight together:

```bash
git add src/laconian_eval/campaign/spend.py src/laconian_eval/campaign/preflight.py tests/campaign/test_spend.py tests/campaign/test_preflight.py
git commit -m "feat: enforce exact campaign spend exposure"
```

## Task 5: Replace broad retries with the closed campaign policy

**Files:**

- Create: `src/laconian_eval/campaign/retry.py`
- Create: `tests/campaign/test_retry.py`
- Modify: `src/laconian_eval/providers/base.py`
- Modify: `src/laconian_eval/providers/openai.py`
- Modify: `src/laconian_eval/capsule/attempts.py`
- Modify: `tests/test_openai_provider.py`
- Modify: `tests/capsule/test_attempts_v2.py`
- Modify: `tests/capsule/test_delivery_certainty.py`

### Step 1: RED-test provider error evidence

- [ ] Extend provider fixtures so `ProviderError` exposes sanitized `http_status: int | None` and `retry_after: str | None` without exposing response headers or exception bodies.
- [ ] Assert 401/403 are definite rejections with permanent STOP classification; structured 429 is definite rejection; timeout, connection, 408, 409, 5xx, and unknown status have unknown delivery.
- [ ] Assert SDK retries remain exactly zero.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/test_openai_provider.py -q
```

Expected RED: `ProviderError` lacks status/Retry-After fields and current 409/5xx behavior is broader than the campaign contract.

### Step 2: RED-test `RetryPolicyV1`

- [ ] Freeze these constants:

```python
RETRY_POLICY_VERSION = "openai-429-full-jitter-v1"
BASE_BACKOFF_MS = 1_000
MAX_EXPONENTIAL_BACKOFF_MS = 60_000
MAX_RETRY_AFTER_MS = 300_000
```

- [ ] Accept `Retry-After` only as ASCII delta-seconds `0..300`; any other value is recorded as unusable and falls back to jitter.
- [ ] Derive `exponential_bound_ms = min(60_000, 1_000 * 2 ** (attempt - 1))`.
- [ ] Derive an inclusive integer jitter in `[0, exponential_bound_ms]` from the campaign seed, `"retry-jitter-v1"` domain, batch hash, plan item ID, and attempt number. Do not use ambient randomness.
- [ ] Retry only when status is 429, delivery certainty is `definitely_rejected`, retry count remains, no STOP/hold exists, reservation exists, and deadline covers backoff + timeout + durable work + 900-second checkpoint margin.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_retry.py tests/capsule/test_delivery_certainty.py -q
```

Expected RED: campaign retry module and evidence schema are absent; legacy fixed exponential expectations fail.

### Step 3: GREEN closed taxonomy and evidence

- [ ] Implement `RetryEvidenceV1` with status, certainty, raw safe Retry-After, bounded value, exponential bound, seed-derivation digest, chosen delay, source, attempt reservation hash, deadline remainder, and decision.
- [ ] Keep `RawAttemptV2` policy-neutral: validate terminal/backoff structural consistency but stop enforcing `100 * 2 ** n`. Bind exact campaign retry policy through spend/controller evidence instead.
- [ ] Update OpenAI classification and sanitizer boundaries. Header lookup failures become unusable Retry-After, never untrusted text in public errors.
- [ ] Run provider, attempt, delivery, and retry tests to GREEN.

### Step 4: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/retry.py src/laconian_eval/providers/base.py src/laconian_eval/providers/openai.py src/laconian_eval/capsule/attempts.py tests/campaign/test_retry.py tests/test_openai_provider.py tests/capsule/test_attempts_v2.py tests/capsule/test_delivery_certainty.py
git commit -m "feat: enforce closed live retry policy"
```

## Task 6: Seal bounded batch plans and consume one job receipt

**Files:**

- Create: `src/laconian_eval/campaign/batch.py`
- Create: `tests/campaign/test_batch.py`
- Modify: `src/laconian_eval/campaign/models.py`
- Modify: `src/laconian_eval/campaign/spend.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

### Step 1: RED-test deterministic contiguous-prefix selection

- [ ] Given registry order, predecessor ledger, checkpoint inventory, remaining time, and cap, assert the selected work is the largest contiguous prefix that fits all frozen call, reservation, and time bounds.
- [ ] Do not begin the judge half of this task until Slice 2's owning hard-score/judge task has
  committed `JudgeRequestAttachmentV1`, its exact verifier, ordered request-ID semantics, and the
  generation-context/index interface used before judge execution. The generation half may proceed
  earlier. This prerequisite is inherited by Task 7 and is an explicit partial-order edge; campaign
  code must not recreate a Slice 2 record.
- [ ] Reject reordering, gaps, duplicate request IDs, a shard/request outside the remaining suffix, an enlarged plan, a stale predecessor, wrong workflow hash, wrong price hash, and an unresolved STOP/hold.
- [ ] Assert `BatchPlanV1` binds campaign, phase, mode, input tag object/commit, workflow SHA-256,
  requested service-tier literal/root, predecessor state/spend/inventory roots, ordered shard/request
  identities, per-attempt reservation hashes, maximum attempts, worst-case reservation, price
  snapshot hash, monotonic allowance, soft deadline, and plan hash.
- [ ] Define `VerifiedPhasePlanV1` as the full immutable campaign-phase index from which contiguous
  batches are sliced. Generation contains the seed-ordered 36 shard units and every ordered plan-row
  ID. Judge contains the same 36 shard slots, each verified `JudgeRequestAttachmentV1` hash, and its
  exact ordered request IDs, including empty tuples for zero-call attachments. Bind its digest in
  every `BatchPlanV1` and `CampaignStateV1.active_phase_plan_sha256`.
- [ ] Assert an empty remaining suffix cannot produce a provider batch.
- [ ] Define strict frozen `CheckpointInventoryEntryV1` with phase, verified phase-plan ordinal,
  exact plan-item/request ID, nullable checkpoint `ArtifactIdentityV1`, capsule/checkpoint/provenance
  hashes, terminal-attempt hash, and next-plan index. Define `CheckpointInventoryV1` with campaign,
  phase, verified phase-plan hash, all entries in ordinal order, predecessor inventory root, and
  class-bound inventory root. Missing work is represented by a null checkpoint in its fixed slot,
  never by deleting/reordering a slot.
- [ ] Define strict frozen `BatchPreparationRequestV1` with campaign ID, phase, mode,
  `WorkflowIdentityV1`, UUID4 batch-attempt ID, expected authority-ref OID, expected state/spend/
  hold/inventory/phase-plan roots, and a bounded monotonic allowance. It has no model, retry, price,
  cap, order, URL, command, or free-form override; those come only from registry/authority.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_batch.py -q
```

Expected RED: batch planner is absent.

### Step 2: RED-test single-use receipt ordering

- [ ] Prove `ConsumedBatchReceiptV1` binds one exact `ProviderJobIdentityV1`, current-price reviewer attestation, reservation event/hash, and batch plan.
- [ ] Reject reused, missing, duplicate, superseded, run-attempt-mismatched, job-mismatched, and batch-attempt-mismatched receipts before provider construction.
- [ ] Instrument the provider factory and environment accessor and assert the consumed receipt and
  winning remote `BATCH_RECEIPT_CONSUMED` authority envelope are durable before the first API-key
  environment lookup. Local fsync or an uploaded candidate is insufficient: re-fetch the protected
  authority ref, reconstruct it from the winning OID, and match the exact workflow run, run attempt,
  numeric provider job ID, UUID4 batch-attempt ID, plan, reservation, and receipt.
- [ ] A rerun identity must append a new reservation and plan; it cannot claim a prior unused receipt.
- [ ] Race two pre-key consumers against the same expected authority-ref OID. Exactly one dedicated
  state-App CAS wins; the loser never evaluates an `OPENAI_API_KEY` expression or constructs a
  provider. Crash the winner after CAS but before the key-bearing step and prove no-input recovery
  emits `NO_DISPATCH_PROVED` only when the exact GitHub job-step timeline says the key-bearing step
  never started and no controller-start/attempt evidence exists. Any uncertain or started step
  fails closed to `PERMANENT_STOP`; an `ACTIVE` state is never silently reused.

### Step 3: GREEN planner and receipt consumer

- [ ] Implement `select_contiguous_batch` as a pure function with stable tie-free order.
- [ ] Implement `prepare_batch` so it appends reservation events and seals `PreparedBatchV1` without reading credentials.
- [ ] Implement `consume_job_receipt` with exact current-price attestation and an exclusive-create
  receipt marker, producing a canonical `BATCH_RECEIPT_CONSUMED` candidate bound to the expected
  remote authority-ref OID. It grants no credential authority by itself.
- [ ] Run receipt consumption in a separate key-free `receipt-writer` job. After `prepare`, start
  both the environment-approved provider job and receipt-writer: the provider's first read-only step
  waits boundedly and makes no provider import/call, while receipt-writer exhaustively lists the
  exact run-attempt jobs, requires one statically named provider job plus its deployment approval,
  binds that numeric job ID, and uses the trusted state-writer package for the expected-OID CAS.
  Delete its PEM/token material. The provider wait step re-fetches and reconstructs the winning ref;
  only its next step may evaluate/map `OPENAI_API_KEY`. A later key-free writer records
  completion/resume/STOP evidence and cannot retroactively authorize a call.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_batch.py tests/campaign/test_spend.py tests/campaign/test_authority.py -q
```

### Step 4: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/batch.py src/laconian_eval/campaign/models.py src/laconian_eval/campaign/spend.py tests/campaign/test_batch.py
git commit -m "feat: bind one live job to one batch receipt"
```

## Task 7: Run exact generation and judge suffixes

This task may start its generation/context and hard-score/prepare-judge integration after Slice 2
Tasks 3–4. Do not implement or turn GREEN the `run_seal_judge_stage`/provider-evidence half, and do
not commit this serialized task, until Slice 2 Task 8 owns/exports
`VerifiedBenchmarkProviderEvidenceV1` and its loader. This preserves task-by-task execution without
duplicating the neutral post-judge bridge.

**Files:**

- Create: `src/laconian_eval/campaign/controller.py`
- Create: `src/laconian_eval/campaign/benchmark_adapter.py`
- Create: `src/laconian_eval/campaign/benchmark_stage.py`
- Create: `tools/benchmark_hard_score_stage.py`
- Create: `tools/benchmark_seal_judge_stage.py`
- Create: `tests/campaign/test_controller.py`
- Create: `tests/campaign/test_benchmark_adapter.py`
- Create: `tests/campaign/test_benchmark_stage.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `src/laconian_eval/capsule/execution.py`
- Modify: `tests/capsule/test_execution.py`
- Modify: `tests/capsule/test_resume.py`
- Modify: `tests/test_public_contract.py`

### Step 1: RED-test a one-attempt capsule seam

- [ ] Extract a private-to-capsule/public-to-campaign `execute_next_attempt` seam that executes exactly one already-verified next plan item under the capsule lock and returns canonical attempt/event hashes.
- [ ] Preserve `resume_capsule(path, *, provider_factory)` unchanged for local use.
- [ ] Prove no campaign callback, spend model, GitHub record, or API key enters generic capsule verification.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/capsule/test_execution.py tests/capsule/test_resume.py -q
```

Expected RED: the one-attempt seam is not exported.

### Step 2: RED-test every controller boundary

- [ ] Before provider construction and before every initial call/retry, independently revalidate batch plan, receipt, state hash, unresolved-hold root, spend hash, checkpoint inventory root, STOP marker, reservation, and exact next request.
- [ ] Define strict frozen `BatchRunResultV1` with campaign/phase, batch-plan and consumed-receipt
  hashes, closed outcome `phase_complete|resumable|stopped`, ordered attempt/retry/spend evidence
  hashes, successor spend and checkpoint-inventory roots, safe inner-archive identities and scan
  receipt hashes, exactly one candidate campaign event, and class-bound result digest. Credential
  values, private paths, provider exception bodies, and detached `UploadAuthorizationV1` bytes are
  forbidden. Export it from `campaign.__init__` and pin its fields in controller/public-contract
  tests.
- [ ] Prove provider parallelism is one and requests never leave frozen order or batch membership.
- [ ] Cover generation and judge phases through a protocol adapter; generation consumes `ShardPlanV1` and judge consumes the verified `JudgeRequestAttachmentV1` index produced after all 36 hard-score request sets are sealed. The judge batch plan binds both the attachment index hash and its exact ordered hard-pass request IDs.
- [ ] RED-test the exact Slice 3→Slice 2 judge-attempt handoff. From controller evidence, construct
  every field of neutral `JudgeAttemptEvidenceV1`, including boundary/request/blind parents, attempt/
  retry/reservation/spend/delivery hashes, requested and returned service tier, safe raw-response hash,
  usage, judgment, terminal evidence, and self digest. Build all 36 `JudgeAttemptBoundaryV1` records
  in frozen request-root order, including empty zero-call boundaries; then the exact
  `JudgeAttemptRootIndexV1`. Reject a missing/extra/reordered request, retry-chain gap, nonterminal
  final attempt, campaign type leakage, or a controller field without a benchmark-owned counterpart.
- [ ] Ordinary terminal definite rejections continue to the next item; 401/403, ambiguity, receipt/spend/provenance mismatch, credential incident, or missing authority append STOP and make zero later calls.
- [ ] After durably recording returned usage/cost, treat nonzero cache writes under the frozen
  explicit/no-breakpoint policy, or actual input usage above the plan row's conservative bound, as a
  permanent policy incident: retain/charge the correct exposure, append STOP, and make zero later
  calls. Never discard billable evidence merely because it violates the request contract.
- [ ] Require both adapters to pass exact `service_tier="default"` at the provider wire and preserve
  the provider-returned service tier plus closed accounting status
  `reported_default|not_applicable_definitely_not_sent|not_applicable_definitely_rejected|missing|mismatch`
  in every generation/judge attempt and spend event. Either exact `not_applicable_*` value is valid
  only for its matching delivery proof when no Responses object or usage exists (including
  a structured retryable 429); it does not block the otherwise-authorized 429 retry. For
  response-received or unknown delivery, missing/non-`default` returned tier never releases a
  reservation: record any trusted billable usage, otherwise retain worst case, append a content-free
  permanent policy incident/STOP, and make zero later calls. Test an ambient project tier configured
  differently and prove omission/`auto` is never emitted on the request wire.
- [ ] A structured 429 followed by success records two attempts, two reservations, one retry evidence row, and no hidden SDK retry.
- [ ] Inject the exact key canary into each possible upload-candidate family in turn: checkpoint tar,
  sidecar, attempt journal, provider metadata, spend/state candidate, safe summary, and controller
  archive. While the key is still in process scope, require the controller to scan the immutable
  final archive bytes against the exact key and the frozen credential patterns. A match emits only a
  content-free `CredentialIncidentV1`, appends `PERMANENT_STOP`, quarantines or deletes the unsafe
  archive, returns no unsafe upload locator, and makes zero later provider calls.
- [ ] Prove a controller crash or exit before a complete `CredentialScanReceiptV1` leaves no
  upload-authorized archive. The receipt binds campaign, batch, payload role, exact payload digest,
  payload byte length, pattern-policy hash, exact-key-scan boolean, scan completion time, and receipt digest;
  it never includes the key, a matched excerpt, an environment value, or a private path.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_controller.py -q
```

Expected RED: controller APIs are absent.

### Step 3: RED-test deadline and checkpoint behavior

- [ ] Use a fake monotonic clock. Start a request only when remaining time covers request timeout, maximum possible next backoff, journal allowance, and 900-second checkpoint margin.
- [ ] At every logical shard boundary, finalize the shard, pack the strict uncompressed tar checkpoint, verify its sidecar and restored capsule, and append inventory evidence.
- [ ] On voluntary exit, checkpoint the verified partial shard and emit `VERIFIED_PARTIAL` only after upload provenance is available.
- [ ] A forced loss before verified upload can use `NO_DISPATCH_PROVED` only when every reservation is durably `never_started`; otherwise emit `PERMANENT_STOP`.
- [ ] An `AMBIGUOUS_INFLIGHT` item is never resumed.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_controller.py::test_soft_deadline_checkpoints_before_resumable_exit tests/campaign/test_controller.py::test_forced_loss_requires_zero_dispatch_proof tests/campaign/test_controller.py::test_ambiguous_delivery_stops_without_retry -q
```

### Step 4: GREEN sequential controller

- [ ] Implement immutable `GenerationPhaseAdapter` and `JudgePhaseAdapter` with a shared `ControllerProtocol`. Neither adapter accepts arbitrary imports or callables from workflow input.
- [ ] After Slice 2 commits its neutral layer/context APIs, implement
  `seal_generation_context(registry, verified_phase_plan, generation_evidence, output_root) ->
  VerifiedGenerationContextIndexV1` in `campaign.benchmark_adapter`. It calls the benchmark-owned
  `write_layer_root_index` for the exact 36 generation capsule/sidecar pairs and
  `write_generation_context_index` for
  `GENERATION/generation-context.json`, copying campaign seed, peeled commit, exact tagged
  hard-scorer source path/hash, hard-score/judge/statistics/audit protocol paths/hashes,
  exact two audit-reviewer and three role-bound protocol-reviewer bindings/signing modes, both
  registry digests, the three ordered protocol-review attestations/root, exact workflow-inventory
  root, and registry digest from verified `CampaignRegistryV1`. Re-open and
  re-hash the exact tagged source/protocol members and require equality rather than copying an
  unverified scalar. Adapter tests independently substitute the statistics member/hash and require
  rejection before context publication or analysis authority can exist.
  Fresh-reload both outputs and byte-compare all 36 ordered parents. Campaign imports neutral
  benchmark types; benchmark code never imports a campaign type.
- [ ] Bind the resulting generation layer-root digest and
  `generation_context_index_sha256` into the accepted `GENERATION_COMPLETE` event evidence and its
  authority envelope. The read-only hard-score preparer reconstructs canonical authority, extracts
  that expected context digest, and passes it to the neutral benchmark loader through a sealed fixed
  package; no operator, workflow input, or `laconian-benchmark` flag supplies it. A context and
  generation index that are internally rehashed but disagree with this authority-bound digest fail
  before hard-score construction.
- [ ] Import neutral `GenerationContextExpectationV1` from `laconian_eval.benchmark.context`.
  Before proposing `GENERATION_SET_SEALED`, construct it from the verified campaign registry,
  predecessor authority root, generation layer-root digest, and context digest; write its canonical
  bytes only at `GENERATION_COMPLETE/generation-context-expectation.json` in the authority candidate.
  The event payload binds the expectation self digest plus the context and generation-root digests;
  the remote CAS yields the final authority root, which is deliberately absent from the expectation
  preimage and therefore creates no self-cycle.
- [ ] In `campaign.benchmark_stage`, implement
  `load_authority_verified_generation_context(authority, generation_index_path, generation_root,
  expectation_path)`. It descriptor-opens the exact retained expectation, verifies the predecessor
  and accepted final authority roots, event kind/payload, registry/tagged hard-scorer/protocol/
  workflow roots, context and generation-root digests, then constructs the neutral
  `VerifiedGenerationContextExpectationV1` in memory and calls the neutral loader. No verified
  capability is serialized, and no expected hash/ID is a function, CLI, workflow, or environment
  input. Add `run_hard_score_stage`, `run_prepare_judge_stage`, and `run_seal_judge_stage`, each of
  which keeps that wrapper in-process while invoking neutral benchmark builders. Stale predecessor/
  final roots, another campaign's copied expectation, rehashed substitutions, descriptor races, or
  raw `laconian-benchmark` production invocation fail.
- [ ] Make `tools/benchmark_hard_score_stage.py` accept exactly `--authority-root`,
  `--generation-index`, `--generation-root`, `--hard-score-output-root`, and
  `--judge-request-output-root`; it reconstructs authority once, loads one in-memory verified
  context, and runs hard-score then prepare-judge. Make `tools/benchmark_seal_judge_stage.py` accept
  exactly `--authority-root`, `--generation-index`, `--generation-root`, `--hard-score-root`,
  `--judge-request-root`, `--judge-attempt-root`, and `--output-root`; it calls only the sealed
  judge stage. Both use `allow_abbrev=False`, exclusive outputs, content-free errors, no raw
  identity/digest/mode options, and never serialize the verified wrapper. After the judge/provider
  root is written, `run_seal_judge_stage` fresh-calls
  `load_verified_benchmark_provider_evidence(generation_expectation=verified_context.expectation,
  ...)`; the loader must exact-compare that external in-memory wrapper with every serialized
  expectation, predecessor/final authority root, context, workflow, and four-root binding. It never
  reconstructs a verified expectation from provider-index bytes.
- [ ] Implement `seal_judge_attempt_root(...) -> VerifiedJudgeAttemptRootV1` in
  `campaign.benchmark_adapter`. It maps only class-bound controller/receipt/spend/delivery evidence
  and verified `JudgeRequestAttachmentV1` records into the benchmark-owned neutral types, calls
  `write_judge_attempt_root(ATTEMPTS, index=..., boundaries=...)` once at an empty owned root, then
  fresh-loads with `load_verified_judge_attempt_root` and byte-compares all 36 boundaries/index.
  The fixed layout is `ATTEMPTS/judge-attempts/index.json` plus `000.json` through `035.json`;
  workflow input cannot supply paths, ordinals, parents, attempts, or digests. Export the adapter and
  pin it in `test_benchmark_adapter.py`/`tests/test_public_contract.py`.
- [ ] Implement `run_batch` as a small loop around boundary validation, one attempt, spend reconciliation, retry decision, journal verification, seal/checkpoint, and state event construction.
- [ ] Ensure `ProviderFactory` is constructed only after receipt consumption and that credential values remain `repr=False` and outside result objects.
- [ ] Before returning from the single key-bearing invocation, build every direct
  `generation_batch` or `judge_attempt_batch` upload candidate
  from exactly three fixed members: canonical envelope, canonical embedded
  `credential-scan-receipt.json`, and the separately scanned payload. The receipt binds only the
  payload, so no digest is self-referential. Scan every uncompressed source/member byte stream before
  packing; checkpoint payloads remain strict uncompressed USTAR and JSON/sidecars are scanned as raw
  canonical bytes. Compression by the later artifact ZIP cannot substitute for this source scan.
  Pack those three members into the deterministic inner file `laconian-artifact.zip`. Scan every
  inner-ZIP byte again with the exact `OPENAI_API_KEY` plus frozen patterns and write a detached local
  `UploadAuthorizationV1` binding that inner ZIP's digest/length and embedded receipt digest. That
  authorization is a closed controller record, never an uploaded member or public artifact. Fsync
  and immediately re-hash all bytes. After scrubbing the key, pass the canonical safe authorization
  record to the key-free artifact recorder; only the resulting exact locator/authority commit may
  make it durable. The secret-free post step may give
  `actions/upload-artifact` exactly that one file and no directory or glob. GitHub's
  service-generated outer ZIP must contain exactly one regular member named
  `laconian-artifact.zip`; its service digest is separate from the detached authorization. Absence,
  mismatch, an extra uploaded path, or incomplete scan means zero upload. Do not claim the service
  wrapper itself was key-scanned and do not defer the inner/member exact-key scan to public
  projection, where the key is intentionally unavailable.
- [ ] After the key-bearing invocation has exited and its environment is scrubbed, secret-free code
  may deterministically build `generation_evidence_set`/generation-context and
  `judge_attachment_set` projections. Their envelopes must have a null direct scan-receipt field and
  the ordered Merkle root of every exact reachable direct receipt. Reload every direct locator,
  receipt, and payload before deriving that root. Never run a projection while the key is mapped and
  never claim its newly packed bytes received an exact-key scan.
- [ ] Rerun controller and capsule regression tests to GREEN.

### Step 5: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/controller.py src/laconian_eval/campaign/benchmark_adapter.py src/laconian_eval/campaign/benchmark_stage.py tools/benchmark_hard_score_stage.py tools/benchmark_seal_judge_stage.py src/laconian_eval/capsule/execution.py tests/campaign/test_controller.py tests/campaign/test_benchmark_adapter.py tests/campaign/test_benchmark_stage.py tests/capsule/test_execution.py tests/capsule/test_resume.py tests/test_public_contract.py
git commit -m "feat: run bounded resumable benchmark batches"
```

## Task 8: Add fixed workflow-facing CLI commands

**Files:**

- Create: `src/laconian_eval/campaign/cli.py`
- Create: `tests/campaign/test_cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_public_contract.py`

### Step 1: RED-test the command surface

- [ ] Add exactly these commands:

```text
laconian-campaign preflight --tag TAG --repository PATH --output PATH
laconian-campaign reconstruct-authority --provenance PATH --output PATH
laconian-campaign prepare-batch --campaign PATH --phase generation|judge --output PATH
laconian-campaign consume-receipt --prepared PATH --job-identity PATH --attestation PATH --output PATH
laconian-campaign run-batch --prepared PATH --receipt PATH --checkpoint-root PATH --output PATH
laconian-campaign apply-event --authority PATH --event PATH --expected-state-sha256 SHA --expected-hold-root-sha256 SHA --output PATH
```

- [ ] Reject extra flags, model overrides, retry overrides, money overrides, shell fragments, URLs, and stdin-sourced executable configuration.
- [ ] Assert stable exit codes: `0` success, `2` invalid evidence/configuration, `3` busy/CAS conflict, `4` STOP/budget terminal path.
- [ ] Assert stdout contains only canonical safe summaries and stderr never contains provider exception bodies or credentials.
- [ ] Start this task only after Slice 2 has committed the `laconian-benchmark` entry point. Add
  `laconian-campaign` without rewriting or reordering the existing script table, and extend
  `tests/test_public_contract.py` to pin both command owners and the six runtime commands. This is the
  serialization point for the only shared `pyproject.toml` edit between Slices 2 and 3.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_cli.py -q
```

Expected RED: entry point and parser do not exist.

### Step 2: GREEN command dispatch

- [ ] Use `argparse` with required subcommands and `allow_abbrev=False`.
- [ ] Keep provider construction inside `run-batch` after receipt revalidation; parsing any other command must not import the OpenAI SDK.
- [ ] Add `laconian-campaign = "laconian_eval.campaign.cli:entrypoint"` to `pyproject.toml`.
- [ ] Run CLI tests plus `tests/test_cli.py` to prove the legacy command remains stable.

### Step 3: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/cli.py tests/campaign/test_cli.py tests/test_public_contract.py pyproject.toml
git commit -m "feat: expose fixed benchmark campaign commands"
```

## Task 9: Add preflight and live-batch workflows

**Files:**

- Create: `.github/workflows/benchmark-preflight.yml`
- Create: `.github/workflows/benchmark-batch.yml`
- Create: `.github/workflows/benchmark-dismiss-hold.yml`
- Create: `tools/benchmark_prepare_hold_dismissal.py`
- Create: `tests/campaign/test_workflow_policy.py`
- Modify: `tests/test_ci_contract.py`

### Step 1: RED-test workflow policy structurally

- [ ] Parse YAML and reject aliases/merge keys before schema inspection.
- [ ] `benchmark-preflight.yml` must be no-input `workflow_dispatch` only, have top-level
  `permissions: {}`, the literal shared concurrency group, no environment, and no secret expression.
  Require `github.ref_type == "tag"`, exact input-tag grammar, tag-object/peeled-commit verification,
  and prove the actual `GITHUB_WORKFLOW_REF` path plus running workflow bytes/hash equal that exact
  `C0` workflow-inventory member; default-branch/branch dispatch or a mutable workflow copy fails. It
  has a read-only `prepare-preflight` job with exactly `contents: read` and
  `pull-requests: read`, used in part to re-fetch the three exact protocol reviews, plus the same narrow `state-writer` pattern as
  batches. The writer has no environment and maps the repository Actions secrets
  `STATE_WRITER_APP_ID`, `STATE_WRITER_APP_INSTALLATION_ID`, and `STATE_WRITER_APP_PRIVATE_KEY`; no
  repository `GITHUB_TOKEN` receives write authority. The writer creates
  `refs/heads/benchmark-authority/{campaign_id}` only when absent and
  commits the initial `PREFLIGHT_SEALED` envelope; an existing divergent ref or simultaneous creator
  fails atomically.
- [ ] `benchmark-batch.yml` must be no-input `workflow_dispatch` only from the immutable input tag,
  use the literal shared concurrency group, and contain
  exactly four jobs: secret-free `prepare`, key-free narrow `receipt-writer`, environment-gated
  read-only `provider`, and provider-secret-free completion `state-writer`. Both writers use the
  dedicated state-App credentials rather than
  write-capable `GITHUB_TOKEN`; it runs the exact hashed
  `tools/benchmark_state_writer.py` and can update only the campaign's canonical authority ref by
  non-force fast-forward.
- [ ] Under top-level deny, batch `prepare` declares exactly `contents: read, actions: read`;
  `receipt-writer` declares exactly `contents: read, actions: read, deployments: read`; provider uses
  the exact scopes below; and completion `state-writer` declares exactly `contents: read, actions:
  read`. No implicit workflow permission is accepted. The App token, not the repository token,
  performs either writer CAS.
- [ ] `prepare-preflight`, batch `prepare`, and batch `provider` check out the registry-recorded
  detached commit with `persist-credentials: false` and reverify the input tag object. State-writer
  jobs do not check out candidate code; they extract and hash only the fixed trusted writer from a
  receipt-bound package and reverify the tag/commit through canonical records.
- [ ] The provider job has `permissions: {contents: read, actions: read, deployments: read}`,
  `environment: benchmark-live`, `timeout-minutes: 180`, and no repository-write scope.
- [ ] The provider and receipt-writer both depend on `prepare`, not on each other. Provider is
  statically named and first enters the protected environment/read-only wait step. Receipt-writer
  uses the run-attempt jobs/deployment/approval APIs to discover and bind its exact numeric identity,
  maps the three state-App repository secrets only in its fixed CAS step, then destroys them. The
  provider's bounded wait accepts only the canonical winning OID/digest for itself. Its next
  key-bearing step maps only `${{ secrets.OPENAI_API_KEY }}` and no App credential or write token.
  Expression-location and job-graph tests enforce this order; a missing/ambiguous provider job or
  approval times out with zero CAS and zero key lookup.
- [ ] The literal secret expression `${{ secrets.OPENAI_API_KEY }}` appears exactly once, under `env` of the single `laconian-campaign run-batch` step. It is absent from workflow/job env, checkout, setup, artifact download/upload, post-controller, and `always()` steps.
- [ ] `benchmark-dismiss-hold.yml` is no-input `workflow_dispatch` only. A read-only inspector
  first requires `github.ref_type == "tag"`, the exact protected input-tag grammar, and independently
  binds/reverifies that tag object/peeled commit to its one registry/campaign/authority-ref name. It
  accepts no default-branch run or latest/by-name authority discovery. The inspector reconstructs
  that exact canonical ref and proves there is exactly one dismissible benign hold; an
  `authorize-dismissal` job uses `benchmark-publish` only to capture a distinct human approval; and
  a no-environment state-writer maps only the state-App repository secrets. The fixed
  `tools/benchmark_prepare_hold_dismissal.py` binds the hold, source/trigger/approval numeric
  identities, expected ref OID, and `HoldDismissalMutationV1`. That mutation leaves state name/hash,
  spend, inventory, and terminal-evidence roots unchanged while removing only the exact dismissible
  hold from the unresolved-hold root. It accepts no hold ID, actor,
  reason, ref, campaign, or event input. The state writer performs one CAS and the workflow no-ops
  only when the exact dismissal is already canonical.
- [ ] Reject `pull_request_target`, `workflow_run`, cron, arbitrary shell inputs, unpinned actions, third-party actions in the key-bearing job, `set -x`, persisted checkout credentials, and dynamic `uses`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_workflow_policy.py tests/test_ci_contract.py -q
```

Expected RED: workflow files are missing.

### Step 2: GREEN the three workflows

- [ ] Pin every action to a full 40-character commit. Use the repository's existing checkout/setup pins and the approved artifact pins.
- [ ] In `prepare-preflight`, seal the verified tagged registry and emit a receipt-bound
  `PREFLIGHT_SEALED` candidate. Its `state-writer` job gives the repository `GITHUB_TOKEN` only
  `actions: read` and `contents: read`; the dedicated state-writer App token performs the sole write.
  It re-verifies the tag/registry/candidate and expected-absent ref, then creates the
  deterministic initial authority commit by non-force push. `benchmark-batch` cannot prepare work
  until reconstruction from that canonical ref yields `PREFLIGHTED`.
- [ ] In `prepare`, retrieve authority/checkpoint artifacts by exact numeric ID and exact workflow-run provenance, reconstruct state, create reservations, and upload only the safe prepared batch.
- [ ] Give `prepare` one closed recovery branch for an already canonical `GENERATION_ACTIVE` or
  `JUDGE_ACTIVE` receipt. It loads the prior provider run/job only from that receipt, exhaustively
  re-fetches the exact job-step timeline and controller/artifact inventory, and may emit
  `NO_DISPATCH_PROVED` only when the key-bearing step provably never started and no dispatch marker
  exists. Receipt-writer/provider are skipped; completion state-writer applies the recovery
  candidate. A started/uncertain step emits `PERMANENT_STOP`, while verified partial evidence emits
  `VERIFIED_PARTIAL`. No workflow input selects run, job, receipt, event, or recovery mode.
- [ ] In `receipt-writer`, resolve the exact provider job/deployment/approval identity through
  GitHub APIs. Combine the prepared official-source capture with that exact approved job/deployment
  record to construct `PriceAttestationV1`, require its source observation to be no more than 24
  hours before approval, bind the current frozen price-snapshot/rate roots and captured approval API
  digest, then consume the receipt and win the Task 6 state-App CAS. No workflow input or operator
  path may supply an attestation, rate, actor, or job identity. In `provider`, re-read and
  reconstruct that winning canonical ref before mapping the secret. Disable shell tracing and
  ambient proxy credentials and run sequentially. The key-bearing step itself constructs and
  exact-key/pattern scans every immutable direct generation/judge-attempt upload archive and emits
  its scan receipt. A later secret-free post step uploads only
  digest-identical `laconian-artifact.zip` files as the sole path of their service artifacts;
  missing receipt/authorization means zero upload.
- [ ] After a judge-phase batch completes the final frozen request suffix, the secret-free post step
  reconstructs the exact authority ref and runs the Runtime-owned fixed
  `tools/benchmark_seal_judge_stage.py --authority-root AUTHORITY --generation-index
  GENERATION_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS
  --judge-attempt-root ATTEMPTS --output-root OUT`. The tool keeps the authority-verified context
  wrapper in-process and calls `campaign.benchmark_stage`; raw `laconian-benchmark seal-judge` is
  forbidden in the live workflow. All paths are fixed workflow literals, never artifact
  interpolation. `ATTEMPTS` is exactly the adapter-written,
  fresh-loaded `JudgeAttemptRootIndexV1` plus its 36 fixed boundary files. Reload all 36
  `JudgeAttachmentV1` records (including zero-call attachments), and create the
  `JUDGE_SET_SEALED` candidate. Generation completion analogously creates
  `GENERATION_SET_SEALED`. Before that generation event, the Slice 3 adapter writes the generation
  `LayerRootIndexV1` and `GENERATION/generation-context.json`, binding the campaign seed, peeled
  commit, tagged hard-scorer source, hard-score/judge/statistics/audit protocols,
  workflow-inventory root, both
  reviewer registries, the three-role protocol-review root, and
  the 36 capsule/sidecar pairs. It also writes the exact authority-package
  `GENERATION_COMPLETE/generation-context-expectation.json`; the candidate/event and artifact
  inventory bind the generation root, context, and expectation digests. These generation/judge set projections have null direct
  scan receipts and bind/recompute the complete transitive direct-receipt root; the provider-evidence
  verifier later rejects any missing/substituted receipt or false direct-scan claim. `state-writer`
  alone commits either event to the
  canonical authority ref;
  `benchmark-evidence.yml` therefore cannot begin until the authoritative state is
  `JUDGE_COMPLETE`.
- [ ] The `state-writer` job downloads only same-run receipt-bound candidate archives by numeric
  artifact identity, reconstructs the current protected authority ref, and attempts the one
  non-force fast-forward. A stale sibling or moved ref fails without retrying or selecting a newer
  candidate.
- [ ] Workflow-policy tests prove the three state-App secret names occur only in fixed hashed
  receipt/state-writer steps, never share
  app/installation IDs with publisher/release roles, and never reach the key-bearing controller,
  setup, checkout, artifact, post, log, receipt, or child-process environments other than the fixed
  `openssl` signer and HTTPS token exchange. Every repository `GITHUB_TOKEN` remains read-only.
- [ ] Package each state-writer invocation with exactly the hash-bound
  `tools/benchmark_state_writer.py` and `src/laconian_eval/campaign/github_app_auth.py`; execute no
  helper from candidate code. Tests alter either helper, add a package member, retain the temporary
  PEM/token, or widen the App's returned permissions and require failure before ref mutation.
- [ ] Set every authority artifact to `retention-days: 90` and preserve exact API artifact IDs/service digests in successor provenance.
- [ ] Rerun workflow policy tests to GREEN.

### Step 3: Prove no secret use in PR/fork CI

- [ ] Extend `test_ci_contract.py` to scan every workflow for provider secret references and assert only `benchmark-batch.yml` contains the one approved occurrence.
- [ ] Assert all PR/fork jobs retain read-only repository permissions and cannot dispatch live work.
- [ ] Add crash/race fixtures for pre-key CAS loss, post-CAS/pre-key crash, `ACTIVE` with a provably
  skipped key step, and `ACTIVE` with an uncertain/started key step. Only the first provable case may
  use `NO_DISPATCH_PROVED`; all others make zero new calls and remain stopped until invalid
  finalization.
- [ ] Run all workflow contract tests.

### Step 4: Commit

- [ ] Commit:

```bash
git add .github/workflows/benchmark-preflight.yml .github/workflows/benchmark-batch.yml .github/workflows/benchmark-dismiss-hold.yml tools/benchmark_prepare_hold_dismissal.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py
git commit -m "ci: add protected benchmark batch workflows"
```

## Task 10: Rehearse pilot bounds and the full offline runtime

**Files:**

- Create: `tests/campaign/test_runtime_synthetic.py`
- Create: `benchmarks/runbooks/public-benchmark.md`
- Modify: `tests/campaign/test_preflight.py`
- Modify: `tests/campaign/test_controller.py`

### Step 1: RED-test the pilot contract end to end

- [ ] Materialize one shared scenario in both locales, four arms, one repetition, and all three models.
- [ ] Assert 24 generation calls, no generation retries, at most 24 judge calls, no judge retries, and total authorized exposure no greater than `5_000_000` micro-USD.
- [ ] Interrupt after a deterministic request, pack/restore the exact partial capsule, generate a new batch receipt, and resume only the exact suffix.
- [ ] Reject any pilot setting or workflow input that permits a 25th generation or judge attempt.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_runtime_synthetic.py::test_pilot_is_bounded_to_48_total_attempts -q
```

Expected RED: the integrated pilot fixture is absent.

### Step 2: GREEN a provider-offline 1,440-row runtime

- [ ] Use deterministic fake/replay providers to execute all 36 generation shards through multiple batches, including one 429 retry, one ordinary rejection, one partial checkpoint, and exact suffix resume.
- [ ] Drive deterministic hard-score fixture attachments, then run all 36 judge attachments through the same controller contract.
- [ ] Assert exact ordered coverage, distinct receipts per provider job, charged/reserved totals below `75_000_000`, no unresolved holds, and zero calls after a synthetic STOP branch.
- [ ] Reconstruct every state/spend/checkpoint artifact from exact IDs and hashes at the end.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_runtime_synthetic.py -q
```

### Step 3: Write the operator runbook

- [ ] Document exact preflight, environment review, price attestation, batch approval, resume, no-dispatch proof, STOP, invalid-prefix, and key-revocation commands.
- [ ] State plainly that GitHub environment approval is per job, every resumed batch needs another approval, artifacts expire after 90 days, and no live call is permitted before all setup gates in the roadmap pass.
- [ ] Include expected safe summaries and escalation actions; never include a secret value or an instruction to print it.

### Step 4: Run the slice regression gate

- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/capsule tests/test_openai_provider.py tests/test_providers.py tests/test_runner.py tests/test_reporting.py tests/test_cli.py tests/test_ci_contract.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
git diff --check
```

Expected GREEN: every command exits 0. No provider credential or network access is used.

### Step 5: Commit

- [ ] Commit:

```bash
git add tests/campaign/test_runtime_synthetic.py benchmarks/runbooks/public-benchmark.md tests/campaign/test_preflight.py tests/campaign/test_controller.py
git commit -m "test: rehearse bounded benchmark runtime"
```

## Slice completion gate

- [ ] Every focused and regression command above is freshly green.
- [ ] `tests/campaign/test_workflow_policy.py` parses every workflow and proves that the literal secret
  expression occurs exactly once in the approved `run-batch` step; a separate credential-canary scan
  over generated test artifacts proves no secret value appears. Do not use a repository-wide raw
  string-count assertion because legitimate sanitizer and policy tests name `OPENAI_API_KEY`.
- [ ] `rg -n "pull_request_target|workflow_run|set -x" .github/workflows/benchmark-*.yml` returns no match.
- [ ] A fresh synthetic run proves exact 1,440-row generation order, bounded retries, per-attempt accounting, checkpoint resume, judge-phase reuse, and STOP-before-next-call.
- [ ] Independent security review confirms the provider job is read-only and the secret is step-scoped.
- [ ] Independent statistical/evidence review confirms request identities and usage fields match the approved protocol.
- [ ] No live workflow is dispatched by this implementation plan. Live pilot authorization remains a separate maintainer action after the roadmap setup gate.
