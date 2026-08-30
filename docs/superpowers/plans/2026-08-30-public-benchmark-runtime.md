# Public Three-Model Benchmark Campaign Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the fail-closed campaign authority, exact spend accounting, bounded batch planning, closed retry policy, resumable provider controller, and GitHub Actions credential boundary required to run the pilot and three-model campaign.

**Architecture:** Keep a campaign control plane beside, not inside, the generation capsule. `CampaignStateSchemaV1` is the sole source for states, events, evidence discriminators, caller/ref policy, reachability, and terminality; generated Python projections and broker policy are checked against that one schema. GitHub Actions never receives a state-writer App key or installation token. Its fixed reusable state job presents GitHub OIDC plus a canonical mutation request to an external broker, and the broker alone constructs canonical Git SHA-1 objects and advances the protected authority ref through smart-HTTP `receive-pack` with an exact old-OID lease. A secret-free prepare job reserves exact worst-case exposure and seals one contiguous `BatchPlanV1`; the protected read-only provider job reconstructs the winning receipt before its single controller step maps `OPENAI_API_KEY`. Live hard-score and judge sealing are available only through an in-memory authority capability and the three private Runtime methods.

**Tech Stack:** Python 3.11+, Pydantic 2 strict/frozen models, integer micro-USD arithmetic, existing canonical JSON and descriptor-bound capsule primitives, pytest, Hypothesis-free deterministic property loops, Ruff, mypy, GitHub Actions with full-SHA pins, and the OpenAI Responses adapter with SDK retries disabled.

---

## Execution contract

- Approved design: `docs/superpowers/specs/2026-08-30-public-three-model-benchmark-design.md`, especially Sections 7, 8, 12, and 14.
- Normative design commit: `46147ef62b5bb009421d58928e879d92247d84b5`.
- Maintainer approval record: `0e2981e32b5d8982e78c73a5e413b36e2b1495e9`.
- Milestone 0 is approved and complete. These Runtime tasks are unblocked; later implementation,
  pilot, and publication gates remain closed until their named tests and reviews pass.
- Any future normative amendment re-blocks every affected Runtime task until that amendment receives
  separate explicit maintainer approval recorded by commit; implementation or live work may not
  infer approval from this plan sync.
- Master roadmap: `docs/superpowers/plans/2026-08-30-public-benchmark-roadmap.md`.
- Prerequisite slice: `docs/superpowers/plans/2026-08-30-public-benchmark-foundations.md`.
- Evaluation types consumed by judge-phase batches: `docs/superpowers/plans/2026-08-30-public-benchmark-evaluation-audit.md`.
- This slice does not publish repository content, create releases, or implement statistical estimators.
- The provider controller has repository read permission only. The only step that receives `OPENAI_API_KEY` is the repository-owned controller invocation after receipt consumption.
- Every money value is an integer count of USD micro-units. Floats and binary floating-point conversions are forbidden in scheduling, reservation, reconciliation, and cap checks.
- The full campaign cap is exactly `75_000_000` micro-USD. The pilot cap is exactly `5_000_000` micro-USD.
- Confirmatory generation permits at most five 429 retries per request; the pilot permits zero. No other automatic retry class exists.
- The Actions hard timeout is 180 minutes. The controller soft deadline is 165 minutes from its monotonic start and must leave a verified checkpoint before a resumable exit.
- Every state-mutation caller uses literal concurrency group `laconian-public-benchmark-state` and
  `cancel-in-progress: false`; the external broker additionally enforces the exact authority old-OID
  lease, so workflow concurrency is never treated as the CAS.
- Every task uses focused RED, observes the named failure, implements the minimum GREEN behavior, runs the stated regression gate, and commits before the next task.

## File boundary

```text
src/laconian_eval/campaign/__init__.py       public campaign types only
src/laconian_eval/campaign/models.py         shared strict scalars and GitHub identities
src/laconian_eval/campaign/artifact_wire.py  cross-slice inner artifact envelope/authorization
src/laconian_eval/campaign/tag_binding.py    immutable benchmark-input tag verification
src/laconian_eval/campaign/preflight.py      campaign registry and exposure seal
src/laconian_eval/campaign/state_schema.py   sole canonical CampaignStateSchemaV1 source
src/laconian_eval/campaign/state.py          generated state/event models and pure transitions
src/laconian_eval/campaign/state_broker.py   OIDC request/receipt types and closed caller policy
src/laconian_eval/campaign/authority_git.py  canonical SHA-1 objects and receive-pack lease verifier
src/laconian_eval/campaign/authority.py      trusted-chain reconstruction and pure mutation packages
src/laconian_eval/campaign/spend.py          exact reservations and reconciliation ledger
src/laconian_eval/campaign/retry.py          closed retry taxonomy and deterministic backoff
src/laconian_eval/campaign/batch.py          bounded prefix plan and single-use job receipt
src/laconian_eval/campaign/controller.py     sequential generation/judge orchestration
src/laconian_eval/campaign/benchmark_adapter.py neutral context/attempt artifact adapters
src/laconian_eval/campaign/runtime.py        private authority capability and three live methods
src/laconian_eval/providers/base.py          structured status and Retry-After evidence
src/laconian_eval/providers/openai.py        fail-closed OpenAI error classification
src/laconian_eval/capsule/attempts.py        policy-neutral campaign-compatible backoff evidence
src/laconian_eval/capsule/execution.py       one-attempt execution seam used by controller
tools/benchmark_capture_trust_boundary.py    read-only safe repository-settings snapshot
tools/benchmark_preflight_stage.py           fixed secret-free preflight adapter
tools/benchmark_prepare_batch.py             fixed secret-free batch preparer
tools/benchmark_run_batch.py                 sole step-scoped provider-key controller
tools/benchmark_post_batch.py                fixed key-free result/authority adapter
tools/benchmark_hard_score_stage.py          authority-verified hard-score/prepare-judge tool
tools/benchmark_seal_judge_stage.py          authority-verified seal-judge tool
tools/benchmark_state_broker_client.py       fixed OIDC/mutation client; receives no App token
.github/workflows/benchmark-preflight.yml    secret-free tag/preflight dispatch
.github/workflows/benchmark-batch.yml        prepare/provider/state-writer bounded batch
.github/workflows/benchmark-dismiss-hold.yml no-input approved benign-hold recovery
.github/workflows/benchmark-publication-state.yml minimal reusable OIDC state-writer boundary
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
```

The generated `CampaignStateName` projection must contain exactly, and only, the following values;
the tuple is generated from `CampaignStateSchemaV1` rather than copied into production code:

```python
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
    "COMPLETE_PUBLICATION_PR_OPEN",
    "RESULT_MERGED",
    "RELEASED",
    "RELEASE_BLOCKED",
    "STOPPED_INVALID",
    "BUDGET_INCOMPLETE",
    "INVALID_FINALIZED",
    "INVALID_PUBLICATION_PR_OPEN",
    "INVALID_PREFIX_MERGED",
    "INVALID_PREFIX_MERGED_INVALID",
]
```

```text
FULL_CAP_USD_MICROS = 75_000_000
PILOT_CAP_USD_MICROS = 5_000_000
HARD_TIMEOUT_SECONDS = 10_800
SOFT_DEADLINE_SECONDS = 9_900
CHECKPOINT_MARGIN_SECONDS = 900

CampaignSeedV1
CampaignPlanIndexV1
CampaignRegistryV1
CampaignStateSchemaV1
StateWriterGitIdentityV1
StateBrokerCallerPolicyV1
AuthorityMutationRequestV1
AuthorityMutationReceiptV1
VerifiedPhasePlanV1
CredentialScanReceiptV1
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

laconian_eval.campaign.runtime._reconstruct_verified_runtime
laconian_eval.campaign.runtime.Runtime.hard_score
laconian_eval.campaign.runtime.Runtime.prepare_judge
laconian_eval.campaign.runtime.Runtime.seal_judge
```

`_reconstruct_verified_runtime` is the only constructor and requires the authority-only in-memory
verified generation-context capability. The capability and wrappers are never serialized. There is
no public campaign-authority CLI or second console entry point. The existing public console remains
`laconian_eval.cli:main`; its seven offline handlers live only under `laconian_eval.replay` and
cannot import Runtime, its constructor, or its capability type.

Public errors carry a stable code and constant message, never paths, keys, response text, raw provider exception bodies, workflow inputs, or untrusted artifact bytes.

### Task 1: Define canonical campaign and GitHub identity records

**Files:**

- Create: `src/laconian_eval/campaign/__init__.py`
- Create: `src/laconian_eval/campaign/models.py`
- Create: `src/laconian_eval/campaign/artifact_wire.py`
- Create: `tests/campaign/__init__.py`
- Create: `tests/campaign/test_models.py`
- Create: `tests/campaign/test_artifact_wire.py`

#### Step 1: RED-test strict shared records

- [ ] Add payload factories for `InputTagBindingV1`, `ProviderJobIdentityV1`, `PriceAttestationV1`,
  `WorkflowIdentityV1`, `ArtifactIdentityV1`, `GitHubAppInstallationIdentityV1`,
  `StateWriterGitIdentityV1`,
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
  attestation hash, and identity digest. The three roles require three pairwise-distinct App and
  installation IDs; a generic `github-actions[bot]` identity is invalid. The state-writer App
  private key exists only in the external broker. Publisher and release-finalizer credentials are
  broker-minted only for separately approved `benchmark-publish` jobs. No App private key or App
  installation token is an Actions, repository, organization, or environment secret.
- [ ] Define exact `StateWriterGitIdentityV1` fields: `schema_version == "StateWriterGitIdentityV1"`;
  positive
  `state_writer_app_account_id`; case-sensitive `state_writer_app_login`; literal ASCII author and
  committer name `Laconian Benchmark State Writer`; literal ASCII author and committer email
  `laconian-benchmark-state-writer@users.noreply.github.com`; and class-bound digest. Reject any
  extra field, Unicode substitution, Git-profile lookup, different author/committer bytes, login
  outside `[A-Za-z0-9-]+(?:\[bot\])?`, NUL/CR/LF/`<`/`>` or other control character, or digest
  mismatch. Its domain separator is
  `laconian-state-writer-git-identity-v1` and canonical UTF-8 has no terminal newline.
- [ ] Model `security_attestor` as a downscoped read-only capability of the same
  `release_finalizer` installation, never as a fourth App identity: it may receive only
  `administration:read`, `metadata:read`, and `contents:read`; release-writing tokens from that App
  omit Administration permission.
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

#### Step 2: GREEN the strict base layer

- [ ] Implement a private `CampaignModel` with `ConfigDict(strict=True, frozen=True, extra="forbid")`.
- [ ] Use decimal integer validators for GitHub numeric IDs and exact lowercase patterns for SHA-1 and SHA-256.
- [ ] Use the existing `canonical_json` and `stable_digest` functions; do not add a second canonical JSON implementation.
- [ ] Define `campaign_record_sha256(domain, model)` so it class-bound revalidates before hashing and excludes only the record's own digest field.
- [ ] Export only stable public records from `campaign/__init__.py`.
- [ ] Rerun the focused test to GREEN.

#### Step 3: Add hostile-boundary and canonical vectors

- [ ] Add a hard-coded canonical JSON vector for each identity record and independently compute its domain-separated digest in the test.
- [ ] Forge model instances with `model_construct`, hostile string subclasses, and stateful `model_dump`; public hashing must reject them with content-free `CampaignRecordError`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_models.py tests/campaign/test_artifact_wire.py tests/capsule/test_canonical.py -q
```

#### Step 4: Commit

- [ ] Review `git diff --check` and commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/models.py src/laconian_eval/campaign/artifact_wire.py tests/campaign/__init__.py tests/campaign/test_models.py tests/campaign/test_artifact_wire.py
git commit -m "feat: define canonical campaign identities"
```

### Task 2: Bind immutable input tags and seal preflight

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
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-attestations.jsonl`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary-signature.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmark/security/state-writer-git-identity.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmark/security/campaign-state-schema.json`
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

#### Step 1: RED-test tag resolution without credentials

- [ ] Test annotated and lightweight `benchmark-input-YYYYMMDD.N` tags in temporary Git repositories.
- [ ] Reject a branch, raw commit, moving alias, malformed date/sequence, tag outside the detached checkout ancestry, mismatched tag object, mismatched peeled commit, dirty checkout, and unavailable object.
- [ ] Patch `os.environ` with a credential canary and prove tag verification neither reads nor serializes `OPENAI_API_KEY`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_tag_binding.py -q
```

Expected RED: `tag_binding` imports fail.

#### Step 2: GREEN exact tag binding

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

#### Step 3: RED-test the real tagged campaign input package

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
  `reviewers.yaml`, `protocol-reviewers.yaml`, `protocol-attestations.jsonl`, the repository trust-boundary attestation
  and detached signature, all seven protocol
  paths/hashes, corpus/arm/runner/dependency hashes, mode-independent caps, the exact
  `benchmark/security/state-writer-git-identity.json` member and digest, and its own digest.
- [ ] Define `BenchmarkWorkflowInventoryV1`, the exact 15-member
  `BENCHMARK_WORKFLOW_PATHS_V1` tuple named by these plans, and
  `build_benchmark_workflow_inventory(tagged_root)`. The builder iterates those paths from the
  verified `C0` tree in the frozen literal `BENCHMARK_WORKFLOW_PATHS_V1` order and never sorts,
  reorders, or accepts caller-supplied entries. It binds each `(relative_path, sha256)` in that exact
  order plus the workflow-policy
  version/full-SHA action-pin proof, and computes the class-bound inventory root. No workflow hash or
  inventory root is a source-code constant before the live freeze.
  Runtime Task 2 tests build a synthetic temporary `C0` containing all 15 paths; they do not depend on
  future Slice 4 files or the then-partial cumulative `tests/test_ci_contract.py`.
  `campaign.yaml`, all three protocol attestations, and the registry bind the same root.
  Publication Task 13 adds the final cross-slice test proving its completed 15-workflow enumeration
  exactly equals this production constant and verifies the real-byte root. Live `C0` population is
  owned only by the roadmap freeze. Unknown/missing/duplicate workflows or a hash from any commit
  other than exact verified C0, including mutable `main`, fails.

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
- [ ] Require fixture `price-snapshot.yaml` to exercise service tier literal `default`, canonical
  UTC observation time, and five separate non-null integer micro-USD rates for every frozen model:
  ordinary-uncached input, cache-read input, cache-write input, visible output, and reasoning output.
  Each dimension carries its own exact official
  HTTPS source URLs, rounding version, and one independent verification attestation. During
  implementation, synthetic fixture rates/URLs are explicitly non-live. The final freeze task
  re-checks then-current official sources and commits the real exact rates; an unverifiable or
  changed rate blocks that task rather than accepting a blank, estimated, or stale value.
- [ ] Require a nonnull reviewed cache-write rate for every frozen model alias and an attestation
  that literal `prompt_cache_options: {"mode":"explicit","ttl":"30m"}`, recursive absence of
  every `prompt_cache_breakpoint`, and the exact `cache_write_tokens` usage field are supported
  by the tagged API contract. Missing support/rate blocks the tag; preflight may not assume writes are
  free or silently map them to cached reads.
- [ ] The synthetic package exercises `mode: pilot`; after the live pilot gate, the confirmatory
  freeze is a separately reviewed commit/tag whose package declares
  `mode: confirmatory`. Mode comes only from the verified tagged package and is bound into campaign
  identity; no CLI, workflow input, or environment value may override it. A mode edit always creates
  a new tag, registry, plan index, and campaign ID.
- [ ] Require live `reviewers.yaml` to preregister exactly two distinct maintainer-supplied GitHub
  numeric account IDs/logins for the human audit plus their required commit-signing verification
  mode and optional exact key fingerprints. Its canonical digest is the audit-reviewer-registry hash.
  Synthetic identities are permitted only in tests. Do not create the live file or
  input tag until the final freeze receives both real identities; missing, duplicate, fabricated,
  or unverified identities fail preflight. Task 2 fixtures use explicitly synthetic identities.
- [ ] After Slice 2 Task 3 commits its neutral reviewer/context contract, load the benchmark-owned strict
  `ProtocolReviewerRegistryV1` from `protocol-reviewers.yaml`; Runtime must import/class-bound
  revalidate that type and must not define or re-export a second class. It contains exactly three
  role-bound `ProtocolReviewerBindingV1`
  records in order `statistical_method`, `blind_judge_audit_protocol`, `security_evidence`, each with
  a distinct non-bot numeric GitHub account ID/login, closed signing verification mode, and exact
  mode-compatible fingerprint. Keyed modes require a fingerprint; `github_verified_commit`
  requires null; `security_evidence` always requires non-null and therefore cannot use
  `github_verified_commit`. Its canonical digest is independent of the two-person audit registry;
  no identity is inferred from an attestation line. Live freeze requires all three real bindings,
  while fixtures are explicitly synthetic. This is an explicit Task 2 integration edge on Slice 2
  Task 3; tag/Git/pricing work may proceed earlier, but preflight cannot turn GREEN without it.
  Slice 2 Task 8 later extends the already-owned context into the post-judge provider bridge.
- [ ] Require the seven canonical protocol files to be byte-complete projections of the implemented
  hard-score, judge, statistics, audit, retry, checkpoint, and publication contracts. Tests
  independently recompute every protocol hash and reject a file generated from a different source
  revision or containing an unknown/free-form execution field.
- [ ] Import and class-bound revalidate Evaluation-owned `ProtocolAttestationV1`; Runtime must not
  define a substitute. Require exactly these top-level fields in schema order:
  `schema_version`, `role`, `protocol_registry_sha256`, `reviewer_numeric_account_id`,
  `reviewer_login`, `verification_mode`, `signing_fingerprint`, `input_tag_object_sha256`,
  `peeled_c0_sha256`, `workflow_root`, `subjects`, `subject_root`, `signed_at`,
  `signature_evidence`, and `attestation_sha256`. Canonical bytes use strict `CanonicalJSONV1`.
  Require the closed verification modes `github_verified_commit|ssh_sha256|openpgp_fingerprint`
  with their exact fingerprint and signature-evidence rules.
- [ ] Require the exact ordered subject kinds for `statistical_method`:
  `corpus_case_root`, `estimand_protocol_sha256`, `statistical_protocol_sha256`,
  `bootstrap_protocol_sha256`, `outcome_classification_protocol_sha256`, and
  `false_fail_sensitivity_protocol_sha256`; for `blind_judge_audit_protocol`:
  `hard_score_protocol_sha256`, `judge_prompt_sha256`, `judge_schema_sha256`,
  `audit_sampling_protocol_sha256`, `audit_commit_reveal_protocol_sha256`, and
  `audit_adjudication_protocol_sha256`; and for `security_evidence`:
  `provider_request_contract_sha256`, `retry_spend_protocol_sha256`,
  `campaign_state_schema_sha256`, `workflow_endpoint_policy_sha256`,
  `artifact_security_protocol_sha256`, `publication_correction_protocol_sha256`,
  `identity_registry_bundle_sha256`, and `state_writer_git_identity_sha256`.
  Every subject is exactly `{kind, sha256}`. Require one attestation per registry role in registry
  order and recompute `subject_root` plus `protocol_attestations_root`; unknown, duplicate,
  cross-role, reordered, or identity-mismatched subjects fail preflight.
- [ ] Because Task 3 implements the schema after this synthetic package test, commit exact canonical
  `benchmark/security/campaign-state-schema.json` bytes generated directly from approved design
  commit `46147ef62b5bb009421d58928e879d92247d84b5` and freeze those bytes verbatim. Bind its digest as the
  `campaign_state_schema_sha256` subject. Task 3 must generate byte-identical schema bytes and turns
  RED on any mismatch; the live input tag remains owned by the later roadmap freeze after both tasks
  are complete.
- [ ] Add a golden Git-object fixture whose protected input tag resolves to exact C0. Class-bound
  revalidate each attestation and use Evaluation's fixed object/signature verifier against that
  repository object database; do not inject ancestry or signature callbacks. Require
  `input_tag_object_sha256`, `peeled_c0_sha256`, signature-evidence commit OID, reviewer numeric
  identity/login, verification mode/fingerprint, workflow root, and every subject digest to agree.
  Reject a mutable ref, missing object, replacement/graft, different commit, fabricated verification
  record, mode/fingerprint mismatch, self-digest recursion, or callback-supplied truth.
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
  canonical attestation bytes. The `security_evidence` protocol attestation separately binds the
  trust-boundary and identity-registry subject roots through its exact subject inventory; neither
  record may claim or derive its own containing Git object ID.
- [ ] Add exact-settings tests with fake paginated GitHub responses. Secret-free preflight re-fetches
  every endpoint readable by its repository token and canonical-compares it with the captured
  records. Admin-only settings require a separately produced signed observation no older than 24
  hours at dispatch; a changed/unreadable/partial setting, App permission, source-App check binding,
  ruleset, retention value, or signature blocks preflight. Never weaken this to a human checkbox.
- [ ] Implement `tools/benchmark_capture_trust_boundary.py` as a separate read-only maintainer tool,
  never a workflow or public CLI command. It consumes a fixed directory of already captured safe
  canonical GET records plus the detached security-reviewer signature, projects only the schema's
  allowlisted fields, and writes canonical attestation bytes. It accepts no credential, endpoint,
  role subset, secret metadata, arbitrary response body, or mutation capability. Tests prove raw
  header/cookie/credential canaries never reach output, logs, or errors and every omitted page or
  record fails. The later fixed `security_attestor` job obtains fresh Administration-read evidence
  only through its downscoped external-broker capability.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_trust_boundary.py tests/campaign/test_input_package.py -q
```
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_input_package.py -q
```

Expected RED: the strict input-package loader and real frozen files do not exist.

#### Step 4: RED-test the complete secret-free registry and seed-derived order

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
all seven ordered protocol hashes, five-dimension price snapshot/source roots, the exact two audit-reviewer account/signing
bindings and audit-reviewer-registry hash, the exact three role-bound protocol-reviewer bindings and
protocol-reviewer-registry hash,
all three protocol attestation records/hashes and their ordered root,
the exact `StateWriterGitIdentityV1` and `CampaignStateSchemaV1` member hashes,
the repository trust-boundary attestation/signature hashes and ordered settings-record root,
planned initial calls, planned maximum attempts,
requested service-tier root (every generation/judge request exactly `default`), explicit/30m cache-policy root and recursive no-breakpoint proof, projected reserved
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

#### Step 5: GREEN the tagged package and deterministic preflight

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
- [ ] Import and class-bound revalidate Foundations-owned `ResolvedPriceSnapshotV1`; implement only
  the strict integer-micro-USD projection and pure `token_charge_usd_micros` /
  `project_worst_case_exposure` functions in `spend.py`. Preserve the exact five Foundation field
  names and source evidence without redeclaration. Each token component rounds up independently;
  all ledger inputs and outputs are strict nonnegative integers.
- [ ] Calculate worst-case request exposure through those pure functions and enforce exactly `5_000_000` pilot or `75_000_000` confirmatory micro-USD.
- [ ] Emit a canonical `PreflightSummaryV1` that contains counts, price URLs, reservations, and hashes but no prompts, outputs, credentials, arbitrary paths, or environment values.
- [ ] Rerun tag, spend-pricing, and preflight tests to GREEN.

#### Step 6: Commit

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
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-attestations.jsonl \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary-signature.json \
  tests/fixtures/public-benchmark-input-v1/benchmark/security/state-writer-git-identity.json \
  tests/fixtures/public-benchmark-input-v1/benchmark/security/campaign-state-schema.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/hard-score.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/judge.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/statistics.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/audit.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/retry.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/checkpoint.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/protocols/public-three-model-v1/publication.json
git commit -m "feat: seal benchmark campaign preflight"
```

### Task 3: Implement the normative state machine and invalid-event holds

**Files:**

- Create: `src/laconian_eval/campaign/state_schema.py`
- Create: `src/laconian_eval/campaign/state.py`
- Create: `src/laconian_eval/campaign/state_broker.py`
- Create: `src/laconian_eval/campaign/authority_git.py`
- Create: `src/laconian_eval/campaign/authority.py`
- Create: `tools/benchmark_state_broker_client.py`
- Create: `tests/campaign/test_state_schema.py`
- Create: `tests/campaign/test_state.py`
- Create: `tests/campaign/test_state_broker.py`
- Create: `tests/campaign/test_authority_git.py`
- Create: `tests/campaign/test_authority.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

#### Step 1: RED-test the sole canonical state schema

- [ ] Define one versioned canonical `CampaignStateSchemaV1` fixture and generate the state-name,
  event-name, parent/bundle/evidence-discriminator, terminality, caller/ref, and reachability/liveness
  projections from it. Test that production `state.py`, broker policy, and the human-readable design
  table round-trip to the same schema digest. A hand-written second transition list, table-only edge,
  broker-only edge, unknown enum, unreachable event, or nonterminal state without an authorized
  success/invalidation/STOP/correction continuation fails.
- [ ] Canonicalize schema, event, state, hold, request, and receipt records as RFC 8785 JSON, UTF-8
  without terminal newline, UTC RFC 3339 timestamps, canonical JSON integers, lowercase SHA-256
  roots, and 40-lowercase-hex Git SHA-1 OIDs. Reject missing/extra/null-where-forbidden fields,
  duplicate/reordered schema arrays, floats, bool-as-int, or a digest that omits any field except its
  own final digest.
- [ ] Generate canonical schema bytes and require byte equality plus digest equality with Task 2's
  approved synthetic `benchmark/security/campaign-state-schema.json` member and its
  `security_evidence` subject. Any drift requires a new normative amendment and reapproval; a test
  cannot update its expected digest from production output.
- [ ] Assert the generated state tuple is exactly
  `PREFLIGHTED`, `GENERATION_ACTIVE`, `GENERATION_RESUMABLE`, `GENERATION_COMPLETE`,
  `HARD_SCORE_COMPLETE`, `JUDGE_ACTIVE`, `JUDGE_RESUMABLE`, `JUDGE_COMPLETE`,
  `PROVIDER_EVIDENCE_VERIFIED`, `AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, `BUNDLE_COLLECTED`,
  `COMPLETE_PUBLICATION_PR_OPEN`, `RESULT_MERGED`, `RELEASED`, `RELEASE_BLOCKED`,
  `STOPPED_INVALID`, `BUDGET_INCOMPLETE`, `INVALID_FINALIZED`,
  `INVALID_PUBLICATION_PR_OPEN`, `INVALID_PREFIX_MERGED`, and
  `INVALID_PREFIX_MERGED_INVALID`. Reject any untyped publication-open state/event, cross-kind merge/close
  events, or a release/correction/promotion edge from either invalid-prefix terminal state.
- [ ] Generate and parameterize every approved edge in design Section 7.4, including same-state
  publication/correction intent and receipt records, the two typed correction invalidation kinds,
  `RELEASE_BLOCKED + CORRECTION_RESULT_RELEASED -> RELEASED`, and
  `RELEASED + CORRECTION_RESULT_RELEASED -> RELEASED`. Assert invalid-prefix publication uses only
  `INVALID_PUBLICATION_PR_OPEN` and ends only in `INVALID_PREFIX_MERGED` or
  `INVALID_PREFIX_MERGED_INVALID`.

- [ ] Cover every illegal source/event pair, a STOP-to-live jump, partial-to-complete jump, release-blocked continuation, duplicate event, skipped parent, wrong phase-plan, wrong spend hash, wrong inventory root, and unresolved hold.
- [ ] `CORRECTION_RESULT_RELEASED` is the sole release-blocked escape: require the exact next
  correction sequence; predecessor correction record/root; prior pointer digest; new pointer digest;
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
- [ ] For `GENERATION_SET_SEALED`, require exactly the ordered 36 capsule hashes,
  `generation_context_expectation_sha256`, and `verified_generation_context_root`. Neither root may
  be omitted, reconstructed later, or replaced by a serialized raw context.
- [ ] Generate the ordinary `PERMANENT_STOP` caller/parent/reason rows from the schema exactly:
  batch from `PREFLIGHTED|GENERATION_RESUMABLE|GENERATION_ACTIVE|HARD_SCORE_COMPLETE|JUDGE_RESUMABLE|JUDGE_ACTIVE`
  for provider/reservation/delivery/identity/ledger/security evidence; hard-score from
  `GENERATION_COMPLETE` for generation-context/hard-score integrity; evidence from `JUDGE_COMPLETE`
  for coverage/provider-evidence failure; audit from `PROVIDER_EVIDENCE_VERIFIED` for identity/
  nonparticipation/reveal/adjudication protocol failure; analysis from `AUDIT_COMPLETE` for
  statistical/provenance/integrity failure; complete collection from `ANALYSIS_COMPLETE` for bundle
  coverage/lineage failure; publish from `BUNDLE_COLLECTED|COMPLETE_PUBLICATION_PR_OPEN`, with the
  open-PR row requiring its exact publisher close receipt; and dismiss-hold only for one of those
  same parent/reason rows plus its exact nondismissible hold. There is no `any nonterminal` wildcard.
- [ ] Generate the exact `credential_exposure` parent/caller matrix from the schema. Require
  `CredentialExposureIncidentEvidenceV1`, safe metadata only, and the exact current authority,
  state, ledger, artifact-inventory, active-plan, and hold roots. Its rows are: batch from
  `GENERATION_RESUMABLE|GENERATION_ACTIVE|HARD_SCORE_COMPLETE|JUDGE_RESUMABLE|JUDGE_ACTIVE`;
  hard-score from `GENERATION_COMPLETE`; evidence from
  `GENERATION_RESUMABLE|GENERATION_ACTIVE|GENERATION_COMPLETE|HARD_SCORE_COMPLETE|JUDGE_RESUMABLE|JUDGE_ACTIVE|JUDGE_COMPLETE|PROVIDER_EVIDENCE_VERIFIED|AUDIT_COMPLETE|ANALYSIS_COMPLETE|BUNDLE_COLLECTED`;
  audit from `PROVIDER_EVIDENCE_VERIFIED`; analysis from `AUDIT_COMPLETE`; complete collection from
  `ANALYSIS_COMPLETE`; publish from `BUNDLE_COLLECTED|COMPLETE_PUBLICATION_PR_OPEN`; and dismiss-hold
  from every preceding credential parent except `COMPLETE_PUBLICATION_PR_OPEN`. Require the exact
  complete-PR close receipt only at `COMPLETE_PUBLICATION_PR_OPEN`; forbid this reason at
  `PREFLIGHTED`, post-merge, invalid-prefix, release-blocked, correction, and terminal states.
  Exhaustively test the full caller × parent × reason Cartesian product, including every excluded
  preflight/invalid/release/correction/terminal cell.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_state_schema.py tests/campaign/test_state.py -q
```

Expected RED: the canonical schema, generated projection, and transition function are absent.

#### Step 2: GREEN schema-generated pure transition models

- [ ] Implement `CampaignStateSchemaV1` first and generate the discriminated `CampaignEventV1`
  union, `CampaignStateName`, evidence-discriminator checks, transition dispatcher, terminal-state
  checks, and reachability matrix into `state.py`. The generated file carries its source-schema
  digest and fails tests if regenerated bytes differ; no task may edit the generated enum/mapping by
  hand.
- [ ] Define `CampaignStateV1` with exactly schema version, campaign ID, transition number, state,
  previous-state hash, event type/hash, tag object, peeled commit, active phase-plan hash,
  spend-ledger hash, inventory Merkle root, optional STOP/incident ID, exact workflow/job or reviewer
  identities, `state_writer_git_identity_sha256`, and state hash.
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
  roots, unchanged state/spend/inventory/correction/publication roots, numeric trigger and distinct
  `benchmark-publish` approval identities, expected authority-ref OID, and self digest. It is a hold
  mutation, never a `CampaignEventV1`, and cannot change state name/hash.
- [ ] Enforce the schema-generated parent, bundle kind, source workflow/ref, reason, evidence, and
  terminality predicates before constructing the next state. `INVALID_EVENT_DISMISSED` remains a
  hold mutation rather than a state transition and cannot appear in a state event union merely to
  simplify dispatch.
- [ ] Rerun `test_state.py` to GREEN.

#### Step 3: RED-test the external OIDC broker and canonical Git lease

- [ ] Feed shuffled, missing, duplicated, expired, superseded, and forked authority envelopes; accept only one exhaustive parent-linked chain rooted at the exact protected canonical ref
  `refs/heads/benchmark-authority/{campaign_id}`. Operator-supplied artifact subsets and "latest by
  name" discovery are never authority.
- [ ] Build two deterministic mutation requests with the same expected canonical-ref OID and race
  them through one fake external broker. Exactly one receive-pack lease succeeds; the sibling fails atomically, and
  reconstructing from the winning ref yields its exact state, spend, hold, inventory, and artifact
  locator roots.
- [ ] Test `StateBrokerCallerPolicyV1` against signed fake GitHub OIDC tokens. Require current GitHub
  JWKS, `typ=JWT`, `alg=RS256`, matching `kid`, issuer
  `https://token.actions.githubusercontent.com`, frozen audience and the repository's exact OIDC
  subject-customization/immutable-subject configuration state and digest (never an assumed default
  `sub` format),
  `nbf <= iat <= now < exp`, age at most five minutes, and never-before-seen `jti`. Build the exact
  projection fields `repository`, `repository_id`, `repository_owner`, `repository_owner_id`,
  `actor`, `actor_id`, `ref`, `ref_type`, `sha`, `event_name`, `workflow`, `workflow_ref`,
  `workflow_sha`, `job_workflow_ref`, `job_workflow_sha`, `run_id`, `run_attempt`, `check_run_id`,
  and `runner_environment`; the reusable state job has no
  environment claim. Verify API run/job records and reject missing/extra/mismatched claims, reruns
  with an unauthorized triggering actor, unlisted caller/ref/event, PR ref, or reused `jti`.
- [ ] Generate the broker caller/ref/event matrix from `CampaignStateSchemaV1`. Every tag/main event
  requires its prebound caller SHA except exactly these six post-merge events:
  `RESULT_MERGED`, `INVALID_PREFIX_MERGED`, `CORRECTION_MERGE_RECORDED`,
  `RESULT_MERGE_INVALIDATED`, `INVALID_PREFIX_MERGE_INVALIDATED`, and
  `CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
  publication_outcome=merged_invalid)`. Each exception requires exact merge/current-main
  containment, unchanged result subtree, caller/callee C0 workflow bytes, direct `merge_commit`
  plan semantics, and the matching admission evidence/failure root; it grants no other event or
  write authority.
- [ ] Admit exactly these top-level callers through the reusable callee:
  `benchmark-preflight.yml`, `benchmark-batch.yml`, `benchmark-hard-score.yml`,
  `benchmark-evidence.yml`, `benchmark-audit.yml`, `benchmark-analysis.yml`,
  `benchmark-collect-complete.yml`, `benchmark-finalize-invalid.yml`,
  `benchmark-dismiss-hold.yml`, `benchmark-publish.yml`, and `benchmark-release.yml`.
  Preflight, batch, hard-score, evidence, and invalid finalization require the exact protected input
  tag; audit, analysis, collection, dismissal, publication, and release require exact plan-bound
  `main`, subject only to the six typed exceptions above. The two PR validators and docs validator
  never call the broker; `benchmark-publication-state.yml` is the exact callee, never an
  independent event caller.
- [ ] Prove the external broker alone holds the state-writer App private key and minted installation
  token. The Actions client sends only OIDC plus canonical `AuthorityMutationRequestV1`; no token,
  key, JWT signer, arbitrary URL, path, packfile, commit, or App credential returns to Actions.
  Credential canaries must be absent from request/receipt bytes, logs, errors, child environments,
  and generated artifacts.
- [ ] Define exact `AuthorityMutationRequestV1` fields for campaign/transition, event type/root,
  canonical source-record bytes and schema roots, exact authority ref, mutation mode, nullable
  expected current OID, proposed tree root, whole-second commit time,
  `state_writer_git_identity_sha256`, OIDC/run identity root, idempotency key, and request digest.
  Missing/extra fields, caller-supplied packfile/commit/arbitrary path, reused idempotency key with
  different bytes, or mismatch against the signed OIDC identity is denied before App-token minting.
- [ ] Construct canonical Git SHA-1 blobs, trees, and commits independently. Require repository
  object format SHA-1, exact `100644` record blobs and `040000` trees, canonical raw-byte tree order,
  no symlink/executable/submodule, exactly zero parents for bootstrap or one expected parent for a
  successor, the frozen `StateWriterGitIdentityV1` author/committer lines, whole-second UTC epoch,
  and message `laconian benchmark authority <campaign-id> transition <20-digit-number>: <event-type>\n`.
  Author and committer epochs and `+0000` offsets are byte-identical; there is no
  `encoding`, `gpgsig`, `mergetag`, or continuation header. Reject ambient Git config, alternate identity, extra
  header/object/tree member, SHA-256 repository format, or noncanonical bytes. Recompute every OID
  from exact `type SP decimal-size NUL content` bytes rather than trusting Git CLI output.
- [ ] Fake Git smart HTTP and require only discovery
  `GET /OWNER/REPO.git/info/refs?service=git-receive-pack`, upload
  `POST /OWNER/REPO.git/git-receive-pack`, and read-only ref/object reconciliation. Bootstrap sends
  all-zero old SHA-1 OID with `expected_absent`; successors send the exact expected current OID.
  The broker accepts only one-parent fast-forward history and exact missing object closure. REST ref
  creation/update, Git Database writes, Contents writes, force, delete, alternate ref, extra packed
  object, or inferred old OID is rejected.
- [ ] For transition one require `mutation_mode=expected_absent`, null expected OID, transition 1,
  `PREFLIGHT_SEALED`, a parentless commit, and literal old OID
  `0000000000000000000000000000000000000000`. Every successor requires
  `mutation_mode=expected_current_oid`, the exact 40-lowercase-hex predecessor, and one-parent
  fast-forward child. Response-loss reconciliation may retry only the byte-identical request while
  the ref remains absent/unchanged.
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
  ordered candidate package. The broker installs the schema-required records in one deterministic
  authority commit and one expected-old-OID receive-pack lease.
- [ ] Define strict `DurableArtifactSubstitutionV1` and `DurableAuthorityCheckpointV1`. A checkpoint
  binds campaign ID, publication ID, correction sequence, stage literal `merged|released`,
  predecessor authority-envelope root, exact merge commit/result path/bundle digest, and a complete byte-sorted mapping from every
  transient artifact locator/envelope/payload/materialized-root digest needed by the authority DAG to
  one or more byte-identical regular files in that immutable merge tree. The released form extends
  the merged checkpoint with its digest, annotated tag object/target, release ID,
  immutable-Release configuration/observation receipt digest, and both exact asset digests. It has
  no caller-selected omissions and its own
  digest; unmapped private bytes make the checkpoint impossible rather than silently durable.
- [ ] Put the merged checkpoint inside the accepted `RESULT_MERGED` event evidence and the extended
  checkpoint inside `RESULT_RELEASED` or `CORRECTION_RESULT_RELEASED` evidence. Each binds only the
  predecessor authority root, so event/state hashing has no cycle. Test a byte changed at the
  committed result path, incomplete mapping, wrong merge/tree/tag/asset, locator substitution,
  duplicate mapping, and a checkpoint that claims its resulting state hash.
- [ ] Treat correction progress as the schema's same-state `CampaignEventV1` records, not as a
  generic terminal-evidence mutation API. Runtime validates the exact event discriminator,
  predecessor correction member, active correction ID/phase, authority roots, and unchanged
  `RELEASED|RELEASE_BLOCKED` state where required; Publication owns construction and external-effect
  verification. Require the distinct
  `CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
  publication_outcome=unmerged_invalid|merged_invalid)` and
  `CORRECTION_INVALIDATED(kind=correction_release_invalidation)` schemas. Either invalidation makes
  that correction ID terminal; continuation requires a new ID, and `merged_invalid` additionally
  requires explicit supersession of the failed correction and contaminated merge. Reject a generic
  invalidation alias, phase gap, duplicate terminalization, two active corrections, or stale lease.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_state_broker.py tests/campaign/test_authority_git.py tests/campaign/test_authority.py -q
```

Expected RED: broker policy, canonical object builder, receive-pack lease, and authority APIs are absent.

#### Step 4: GREEN authority envelopes

- [ ] Implement `AuthorityEnvelopeV1` as the append-only unit containing exactly one accepted state
  event or hold/dismissal mutation, its trusted artifact
  provenance, predecessor envelope hash, and envelope hash. Same-state publication/correction events
  are ordinary schema-validated events; they are not a separate untyped append channel.
- [ ] Define `AuthorityMutationV1` as a strict frozen candidate package containing campaign ID,
  expected authority-ref OID (nullable only for initial creation), predecessor authority-head/state/
  hold/correction/publication roots, one schema-ordered `AuthorityEnvelopeV1`, all resulting roots,
  trusted artifact provenance, `state_writer_git_identity_sha256`, and mutation digest. The broker replays the
  envelope before constructing one deterministic child commit; candidates are composable only
  through a pure builder, never by concatenating JSON.
- [ ] Implement `apply_campaign_event` so each event adds exactly the schema-required canonical
  `events`, `evidence`, `corrections`, `publication`, `receipts`, or `incidents` members in one
  candidate authority tree. A correction release receipt must already be the exact predecessor of
  `CORRECTION_RESULT_RELEASED`; no concatenated JSON or caller-selected extra record is accepted.
  Implement `dismiss_invalid_event_hold` for exactly one `HoldDismissalMutationV1` envelope.
- [ ] Define each authority Git commit as a canonical tree containing the current head record,
  immutable envelope bytes, and the exact numeric artifact IDs/service/payload digests required to
  reconstruct every ancestor. The commit has the previously observed authority-ref OID as its sole
  parent. Before `RESULT_MERGED`, reject every missing/expired ancestor. At or after
  `RESULT_MERGED`, an expired transient locator may be substituted only through the complete
  accepted `DurableAuthorityCheckpointV1`: fetch the exact protected merge tree by object ID,
  descriptor-safely reverify every mapped byte/digest, and replay the entire chain. At or after
  `RESULT_RELEASED`, additionally verify the annotated tag and exact published release/asset
  identities under the recorded immutable-Release repository setting when the released checkpoint
  claims them. This is recoverability evidence, not a claim that an external object is undeletable.
  A missing mapping, mutable ref lookup, merely same-named file,
  changed durable byte, or incomplete checkpoint remains fatal. The protected authority Git history
  itself stores every envelope/checkpoint byte and is never replaced by Actions-artifact discovery.
- [ ] Implement `AuthorityTreeSchemaV1` with exact root blob `campaign-state.json` and optional root
  trees `events`, `evidence`, `holds`, `receipts`, `corrections`, `publication`, and `incidents`.
  Event paths are `events/<20-digit-transition>-<schema-event-name>.json`; content-addressed evidence
  paths are schema-name plus lowercase SHA-256. A successor retains every prior member byte-for-byte,
  replaces only `campaign-state.json`, and appends exactly the current schema-required members.
  Reject deletion, rewrite, executable/symlink/submodule modes, unsafe/non-NFC names, duplicate
  entries, or any path not admitted by the current event schema.
- [ ] Implement `tools/benchmark_state_broker_client.py` as a fixed, argument-closed OIDC client.
  It accepts only the canonical mutation-request path and fixed broker audience/endpoint compiled
  into the C0-reviewed tool, obtains one GitHub OIDC token, sends both once, and verifies the
  canonical `AuthorityMutationReceiptV1`. It has no checkout, App ID, installation ID, private key,
  installation token, packfile, arbitrary URL, retry mutation, or ref-write code. The external
  broker class-bound revalidates every source record, reconstructs the predecessor, constructs the
  exact Git objects, mints the state-writer installation token, performs one receive-pack lease,
  discards the token within five minutes, and returns only the safe receipt.
- [ ] Implement `StateWriterGitIdentityV1` use end to end. Preflight matches the frozen tag member to
  the installed App account and broker policy; `PREFLIGHT_SEALED`, every later event, every mutation
  request/receipt, and every canonical commit bind the same digest. A changed App identity requires a
  new tag/security attestation/campaign and cannot continue an existing authority ref.
- [ ] Implement `AuthorityMutationReceiptV1` with exact campaign/request/idempotency IDs, event and
  ref, mutation mode, expected old OID, ordered blob/tree OIDs, candidate commit OID, observed
  before/after OIDs, create/update/adopt result, endpoint-policy digest, safe request IDs/statuses,
  App actor, Git-identity digest, OIDC identity root, times, and self digest. On response loss adopt
  only an exact fully reverified candidate; retry only while the ref is unchanged; any third OID or
  byte disagreement is a terminal conflict.
- [ ] Compute `unresolved_hold_root_sha256` from byte-sorted active hold hashes.
- [ ] Implement `require_no_unresolved_hold` in `campaign.authority` with the exact signature
  `require_no_unresolved_hold(authority: ReconstructedAuthorityV1) -> None`; export it from
  `campaign.__init__`. Keep `apply_campaign_event` pure: it constructs a candidate mutation bound
  to expected state, hold, and authority-ref OID. The broker re-verifies all three immediately
  before the receive-pack lease.
- [ ] Run state and authority files together to GREEN.

#### Step 5: Commit

- [ ] Run `git diff --check` and commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/state_schema.py src/laconian_eval/campaign/state.py src/laconian_eval/campaign/state_broker.py src/laconian_eval/campaign/authority_git.py src/laconian_eval/campaign/authority.py tools/benchmark_state_broker_client.py tests/campaign/test_state_schema.py tests/campaign/test_state.py tests/campaign/test_state_broker.py tests/campaign/test_authority_git.py tests/campaign/test_authority.py
git commit -m "feat: add fail-closed campaign authority"
```

### Task 4: Extend exact pricing with reservations and reconciliation

**Files:**

- Modify: `src/laconian_eval/campaign/spend.py`
- Modify: `tests/campaign/test_spend.py`
- Modify: `src/laconian_eval/campaign/preflight.py`
- Modify: `tests/campaign/test_preflight.py`

#### Step 1: RED-test exact ledger pricing

- [ ] Import and class-bound revalidate Foundations-owned `ResolvedPriceSnapshotV1`,
  `PriceDimensionV1`, and `PriceSourceEvidenceV1`; Runtime must not redeclare a price schema or
  rename a dimension. Require these exact five field names verbatim:
  `ordinary_uncached_input_per_million`, `cache_read_input_per_million`,
  `cache_write_input_per_million`, `visible_output_per_million`, and
  `reasoning_output_per_million`. Map their canonical decimal representations to a separate strict
  integer-micro-USD projection without binary floating-point arithmetic, preserving dimension,
  `source_url`, `effective_date`, `usd_per_million`, and `source_sha256` equality.
- [ ] Import Foundations-owned `AppliedCacheControlStatus`, `CacheReadStatus`, `CacheWriteStatus`,
  `ServiceTierStatus`, and `ReasoningTokenAccounting` plus
  `PublicBenchmarkResponseEvidenceV1`/`PublicBenchmarkProviderErrorEvidenceV1`; do not redeclare or
  widen any status type. Preserve and verify exact `applied_cache_control_source_sha256`,
  `cache_read_source_sha256`, `cache_write_source_sha256`, `service_tier_source_sha256`,
  `usage_source_sha256`, `reasoning_tokens_source_sha256`, and `returned_model_source_sha256`
  evidence together with `raw_response_sha256` and provider-error-only `error_source_sha256`. Only
  the exact successful status tuple
  `reported_exact/reported_zero/reported_zero/reported_default`, or the matching independently
  proven `not_applicable_definitely_not_sent`/`not_applicable_definitely_rejected` tuple, may release
  no-cache/default-tier reservation components; missing, mismatch, invalid, or nonzero evidence
  remains charged/reserved and emits STOP as prescribed.
- [ ] Accept usage/tier/cache evidence only from Foundation's exact canonical response paths:
  `response.service_tier`, `response.prompt_cache_options.mode`,
  `response.prompt_cache_options.ttl`, `response.usage.input_tokens`,
  `response.usage.input_tokens_details.cached_tokens`,
  `response.usage.input_tokens_details.cache_write_tokens`, `response.usage.output_tokens`,
  `response.usage.output_tokens_details.reasoning_tokens`, and `response.usage.total_tokens`. An
  alternate/flattened/inferred path or failed source digest never authorizes reconciliation.
- [ ] Define golden vectors for ordinary-uncached input, cache-read input, cache-write input,
  visible output, reasoning output, and zero tokens using:

```python
def token_charge_usd_micros(tokens: int, rate_usd_micros_per_million: int) -> int:
    numerator = tokens * rate_usd_micros_per_million
    return (numerator + 999_999) // 1_000_000
```

- [ ] Assert each of the five components rounds up independently and the sum is overflow-bounded.
  For trusted usage require `ordinary_uncached_input_tokens + cache_read_tokens +
  cache_write_tokens == input_tokens`, `visible_output_tokens + reasoning_output_tokens ==
  output_tokens`, and every exact response-path/source digest/status from Foundations. A missing,
  mismatched, or invalid dimension retains its conservative reservation; neither cache status may
  supply or alter the other.
- [ ] Make the imported `ResolvedPriceSnapshotV1`, integer-micro-USD projection, and
  `PriceAttestationV1` require
  `service_tier == requested_service_tier == "default"` and five separate, reviewed, non-null
  integer micro-USD-per-million rates plus source evidence for ordinary-uncached input, cache reads,
  cache writes, visible output, and reasoning output for every frozen requested model ID. A numeric
  zero is valid only when explicitly sourced and reviewed. Recompute the versioned `<=272_000`
  conservative input proof; no long-context price class, threshold, field, fallback, reservation,
  or reconciliation path exists in the authorized vocabulary.
- [ ] Bind literal `prompt_cache_options: {"mode":"explicit","ttl":"30m"}` and recursive absence
  of every `prompt_cache_breakpoint` into the snapshot, reservation, and receipt. Reject floats,
  decimal exponent strings, negative values, bools, a missing/nullable rate, source-evidence
  mismatch, or unsupported requested/returned model ID.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_spend.py -q
```

Expected RED: pricing primitives exist from Task 2, but reservation, reconciliation, and ledger models are absent.

#### Step 2: RED-test append-only attempt reservations

- [ ] Reserve one row for every initial attempt and every allowed retry in the frozen batch, each
  with plan item, attempt number, input bound, cache policy, worst-case cache-write bound, output cap,
  requested service tier `default`, the five exact price dimensions, price snapshot hash, and exact
  worst-case micro-USD. Conservatively price
  each possible input token at the maximum compatible ordinary-uncached/cache-read/cache-write rate unless the frozen
  policy and request identity prove a narrower mutually exclusive component.
- [ ] Freeze the reproducible envelope with `P_u`, `P_r`, `P_w`, `P_v`, and `P_h` denoting the five
  micro-USD-per-million rates. Generation reserves the integer ceiling of
  `(272_000 * max(P_u, P_r, P_w) + 1_024 * max(P_v, P_h)) / 1_000_000`; judge substitutes `768` for
  `1_024`. Keep the five component counts separate with
  `ordinary_uncached + cache_read + cache_write <= 272_000`. Confirmatory reserves exactly six such
  attempt envelopes per request; pilot reserves one. Test hard-coded generation, judge, six-attempt,
  40-request shard, cap-equality, and next-batch-does-not-fit vectors independently of production.
- [ ] Reconcile independently as `never_started`, `trusted_usage`, `definitely_rejected_zero`, or `retained_worst_case`.
- [ ] Prove missing usage, ambiguous delivery, runner loss, unverified checkpoint, and prior failed retry retain full exposure.
- [ ] Prove a later success never releases an earlier attempt reservation.
- [ ] Prove rerun/replacement reservations are additive and a receipt cannot be reused.
- [ ] Test a 429-retry-success chain with both attempts separately accounted: the definitely rejected
  first attempt may become `definitely_rejected_zero` only under the frozen verified zero-billing
  rule; otherwise it retains its reservation, while the successful attempt uses trusted usage.
- [ ] Assert `charged_or_reserved + next_batch_reservation <= cap` before a plan may be sealed; exact equality is allowed.

#### Step 3: GREEN ledger types and verifier

- [ ] Implement canonical `PriceMicrosProjectionV1`, `RequestReservationV1`, `SpendEventV1`,
  `SpendLedgerV1`, and `SpendSummaryV1`; import `ResolvedPriceSnapshotV1` and the evidence/status
  types from Foundations without defining aliases or duplicate models.
- [ ] Make `append_spend_event` require the exact predecessor ledger hash, strictly increasing row number, single-use reservation identity, and current campaign/price hashes.
- [ ] Implement a streaming verifier that recomputes totals and refuses unknown event kinds or nonterminal reconciliation gaps.
- [ ] Integrate `seal_preflight` with the exact pilot/full cap and projected attempt counts.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_spend.py tests/campaign/test_preflight.py -q
```

#### Step 4: Commit

- [ ] Commit spend and now-GREEN preflight together:

```bash
git add src/laconian_eval/campaign/spend.py src/laconian_eval/campaign/preflight.py tests/campaign/test_spend.py tests/campaign/test_preflight.py
git commit -m "feat: enforce exact campaign spend exposure"
```

### Task 5: Replace broad retries with the closed campaign policy

**Files:**

- Create: `src/laconian_eval/campaign/retry.py`
- Create: `tests/campaign/test_retry.py`
- Modify: `src/laconian_eval/providers/base.py`
- Modify: `src/laconian_eval/providers/openai.py`
- Modify: `src/laconian_eval/capsule/attempts.py`
- Modify: `tests/test_openai_provider.py`
- Modify: `tests/capsule/test_attempts_v2.py`
- Modify: `tests/capsule/test_delivery_certainty.py`

#### Step 1: RED-test provider error evidence

- [ ] Keep legacy `GenerationRequest`, `GenerationResult`, and `ProviderError` bytes unchanged.
  Extend public-benchmark fixtures around Foundations-owned
  `PublicBenchmarkProviderErrorEvidenceV1.structured_status` and add a campaign-owned sanitized
  Retry-After evidence record without exposing response headers or exception bodies.
- [ ] Assert 401/403 are definite rejections with permanent STOP classification; structured 429 is definite rejection; timeout, connection, 408, 409, 5xx, and unknown status have unknown delivery.
- [ ] Assert SDK retries remain exactly zero.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/test_openai_provider.py -q
```

Expected RED: the campaign-owned Retry-After projection and exact public-benchmark 429 evidence
matrix are absent, and current 409/5xx behavior is broader than the campaign contract.

#### Step 2: RED-test `RetryPolicyV1`

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
- [ ] Retry only when `structured_status == 429`, delivery certainty is
  `definitely_rejected`, and the complete Foundation evidence proves that no Responses result and no
  usage exist: response ID and returned model/tier are null; usage is wholly unavailable with no
  counts; applied-cache, cache-read, cache-write, and service-tier statuses are each exactly
  `not_applicable_definitely_rejected`; and every independent source digest validates. Retry count
  must also remain, no STOP/hold may exist, the next attempt reservation must exist, and the
  deadline must cover backoff + timeout + durable work + the 900-second checkpoint margin.
- [ ] Assert pilot maximum retries is exactly zero and confirmatory maximum retries is exactly five,
  derived only from the verified manifest/phase plan. A sixth retry, SDK retry, retry of any other
  status/certainty, workflow override, or unreserved attempt is rejected before sleep or dispatch.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_retry.py tests/capsule/test_delivery_certainty.py -q
```

Expected RED: campaign retry module and evidence schema are absent; legacy fixed exponential expectations fail.

#### Step 3: GREEN closed taxonomy and evidence

- [ ] Implement `RetryEvidenceV1` with status, certainty, raw safe Retry-After, bounded value, exponential bound, seed-derivation digest, chosen delay, source, attempt reservation hash, deadline remainder, and decision.
- [ ] Keep `RawAttemptV2` policy-neutral: validate terminal/backoff structural consistency but stop enforcing `100 * 2 ** n`. Bind exact campaign retry policy through spend/controller evidence instead.
- [ ] Update OpenAI classification and sanitizer boundaries. Header lookup failures become unusable Retry-After, never untrusted text in public errors.
- [ ] Run provider, attempt, delivery, and retry tests to GREEN.

#### Step 4: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/retry.py src/laconian_eval/providers/base.py src/laconian_eval/providers/openai.py src/laconian_eval/capsule/attempts.py tests/campaign/test_retry.py tests/test_openai_provider.py tests/capsule/test_attempts_v2.py tests/capsule/test_delivery_certainty.py
git commit -m "feat: enforce closed live retry policy"
```

### Task 6: Seal bounded batch plans and consume one job receipt

**Files:**

- Create: `src/laconian_eval/campaign/batch.py`
- Create: `tests/campaign/test_batch.py`
- Modify: `src/laconian_eval/campaign/models.py`
- Modify: `src/laconian_eval/campaign/spend.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

#### Step 1: RED-test deterministic contiguous-prefix selection

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
  snapshot hash, all five rate/source roots, literal explicit/30m cache policy, recursive
  no-breakpoint proof, monotonic allowance, soft deadline, and plan hash.
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

#### Step 2: RED-test single-use receipt ordering

- [ ] Prove `ConsumedBatchReceiptV1` binds one exact `ProviderJobIdentityV1`, current-price reviewer
  attestation with all five non-null rate/source dimensions, reservation event/hash, batch plan,
  `state_writer_git_identity_sha256`, and winning `AuthorityMutationReceiptV1`.
- [ ] Reject reused, missing, duplicate, superseded, run-attempt-mismatched, job-mismatched, and batch-attempt-mismatched receipts before provider construction.
- [ ] Instrument the provider factory and environment accessor and assert the consumed receipt and
  winning remote `BATCH_RECEIPT_CONSUMED` authority envelope are durable before the first API-key
  environment lookup. Local fsync or an uploaded candidate is insufficient: re-fetch the protected
  authority ref, reconstruct it from the winning OID, and match the exact workflow run, run attempt,
  numeric provider job ID, UUID4 batch-attempt ID, plan, reservation, and receipt.
- [ ] A rerun identity must append a new reservation and plan; it cannot claim a prior unused receipt.
- [ ] Race two pre-key consumers against the same expected authority-ref OID. Exactly one external
  broker receive-pack lease wins; the loser never evaluates an `OPENAI_API_KEY` expression or constructs a
  provider. Crash the winner after the broker lease but before the key-bearing step and prove no-input recovery
  emits `NO_DISPATCH_PROVED` only when the exact GitHub job-step timeline says the key-bearing step
  never started and no controller-start/attempt evidence exists. Any uncertain or started step
  fails closed to `PERMANENT_STOP`; an `ACTIVE` state is never silently reused.

#### Step 3: GREEN planner and receipt consumer

- [ ] Implement `select_contiguous_batch` as a pure function with stable tie-free order.
- [ ] Implement `prepare_batch` so it appends reservation events and seals `PreparedBatchV1` without reading credentials.
- [ ] Implement `consume_job_receipt` with exact current-price attestation and an exclusive-create
  receipt marker, producing a canonical `BATCH_RECEIPT_CONSUMED` candidate bound to the expected
  remote authority-ref OID. It grants no credential authority by itself.
- [ ] Run receipt consumption in a separate key-free `receipt-writer` job. After `prepare`, start
  both the environment-approved provider job and receipt-writer: the provider's first read-only step
  waits boundedly and makes no provider import/call, while receipt-writer exhaustively lists the
  exact run-attempt jobs, requires one statically named provider job plus its deployment approval,
  binds that numeric job ID, and calls the fixed reusable OIDC state job so the external broker can
  perform the expected-old-OID lease. No App PEM/token material enters either job. The provider wait
  step re-fetches and reconstructs the winning ref;
  only its next step may evaluate/map `OPENAI_API_KEY`. The later key-free `post` job records
  completion/resume/STOP evidence and cannot retroactively authorize a call.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_batch.py tests/campaign/test_spend.py tests/campaign/test_authority.py -q
```

#### Step 4: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/batch.py src/laconian_eval/campaign/models.py src/laconian_eval/campaign/spend.py tests/campaign/test_batch.py
git commit -m "feat: bind one live job to one batch receipt"
```

### Task 7: Run exact generation and judge suffixes

This task may start its generation/context and hard-score/prepare-judge integration after Slice 2
Tasks 3–4. Do not implement or turn GREEN the `Runtime.seal_judge` provider-evidence half, and do
not commit this serialized task, until Slice 2 Task 8 owns/exports
`VerifiedBenchmarkProviderEvidenceV1` and its loader. This preserves task-by-task execution without
duplicating the neutral post-judge bridge.

**Files:**

- Create: `src/laconian_eval/campaign/controller.py`
- Create: `src/laconian_eval/campaign/benchmark_adapter.py`
- Create: `src/laconian_eval/campaign/runtime.py`
- Create: `tools/benchmark_hard_score_stage.py`
- Create: `tools/benchmark_seal_judge_stage.py`
- Create: `tests/campaign/test_controller.py`
- Create: `tests/campaign/test_benchmark_adapter.py`
- Create: `tests/campaign/test_runtime.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `src/laconian_eval/capsule/execution.py`
- Modify: `tests/capsule/test_execution.py`
- Modify: `tests/capsule/test_resume.py`
- Modify: `tests/test_public_contract.py`

#### Step 1: RED-test a one-attempt capsule seam

- [ ] Extract a private-to-capsule/public-to-campaign `execute_next_attempt` seam that executes exactly one already-verified next plan item under the capsule lock and returns canonical attempt/event hashes.
- [ ] Preserve `resume_capsule(path, *, provider_factory)` unchanged for local use.
- [ ] Prove no campaign callback, spend model, GitHub record, or API key enters generic capsule verification.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/capsule/test_execution.py tests/capsule/test_resume.py -q
```

Expected RED: the one-attempt seam is not exported.

#### Step 2: RED-test every controller boundary

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

#### Step 3: RED-test deadline and checkpoint behavior

- [ ] Use a fake monotonic clock. Start a request only when remaining time covers request timeout, maximum possible next backoff, journal allowance, and 900-second checkpoint margin.
- [ ] At every logical shard boundary, finalize the shard, pack the strict uncompressed tar checkpoint, verify its sidecar and restored capsule, and append inventory evidence.
- [ ] On voluntary exit, checkpoint the verified partial shard and emit `VERIFIED_PARTIAL` only after upload provenance is available.
- [ ] A forced loss before verified upload can use `NO_DISPATCH_PROVED` only when every reservation is durably `never_started`; otherwise emit `PERMANENT_STOP`.
- [ ] An `AMBIGUOUS_INFLIGHT` item is never resumed.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_controller.py::test_soft_deadline_checkpoints_before_resumable_exit tests/campaign/test_controller.py::test_forced_loss_requires_zero_dispatch_proof tests/campaign/test_controller.py::test_ambiguous_delivery_stops_without_retry -q
```

#### Step 4: GREEN sequential controller

- [ ] Implement immutable `GenerationPhaseAdapter` and `JudgePhaseAdapter` with a shared `ControllerProtocol`. Neither adapter accepts arbitrary imports or callables from workflow input.
- [ ] After Slice 2 commits its neutral layer/context APIs, implement
  `seal_generation_context(registry, verified_phase_plan, generation_evidence, output_root) ->
  VerifiedGenerationContextIndexV1` in `campaign.benchmark_adapter`. It calls the benchmark-owned
  `write_layer_root_index` for the exact 36 generation capsule/sidecar pairs and
  `write_generation_context_index` for
  `GENERATION/generation-context.json`, copying campaign seed, peeled commit, exact tagged
  hard-scorer source path/hash, hard-score/judge/statistics/audit protocol paths/hashes,
  exact two audit-reviewer and three role-bound protocol-reviewer bindings/signing modes, both
  registry digests, the three ordered protocol attestations/root, exact workflow-inventory
  root, and registry digest from verified `CampaignRegistryV1`. Re-open and
  re-hash the exact tagged source/protocol members and require equality rather than copying an
  unverified scalar. Adapter tests independently substitute the statistics member/hash and require
  rejection before context publication or analysis authority can exist.
  Fresh-reload both outputs and byte-compare all 36 ordered parents. Campaign imports neutral
  benchmark types; benchmark code never imports a campaign type.
- [ ] Bind the resulting generation layer-root digest and
  `generation_context_index_sha256` into the accepted `GENERATION_SET_SEALED` event evidence and its
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
  the broker's receive-pack lease yields the final authority root, which is deliberately absent from the expectation
  preimage and therefore creates no self-cycle.
- [ ] In `campaign.runtime`, implement the only constructor
  `_reconstruct_verified_runtime`. It descriptor-opens the exact retained expectation, verifies
  predecessor and accepted final authority roots, `GENERATION_SET_SEALED` payload, registry/tagged
  hard-scorer/protocol/workflow roots, context and generation-root digests, and constructs the
  authority-only generation-context capability in memory. The capability is non-Pydantic,
  non-serializable, unpickleable, absent from `campaign.__init__`, and cannot be supplied by a path,
  hash, CLI, workflow input, environment value, provider index, or caller callback.
- [ ] Define exactly `Runtime.hard_score`, `Runtime.prepare_judge`, and `Runtime.seal_judge` on the
  object returned by that constructor. Each method keeps the same in-memory capability while calling
  Evaluation-owned neutral builders. Stale predecessor/final roots, another campaign's copied
  expectation, rehashed substitutions, descriptor races, direct `Runtime()` construction, or public
  replay invocation fail before an output root is created.
- [ ] Require `Runtime.hard_score` to seal all 36 ordered hard-score request sets,
  `Runtime.prepare_judge` to bind the same 36 slots and exact ordered hard-pass request IDs, and
  `Runtime.seal_judge` to fresh-load all 36 judge-attempt boundaries plus the external in-memory
  expectation and return `VerifiedBenchmarkProviderEvidenceV1`. The generation transition binds the
  exact 36 capsule hashes, `generation_context_expectation_sha256`, and
  `verified_generation_context_root`; the judge transition binds all 36 judge attachment hashes.
- [ ] Make `tools/benchmark_hard_score_stage.py` accept exactly `--authority-root`,
  `--generation-index`, `--generation-root`, `--hard-score-output-root`, and
  `--judge-request-output-root`; it calls `_reconstruct_verified_runtime` once and then
  `Runtime.hard_score` and `Runtime.prepare_judge`. Make `tools/benchmark_seal_judge_stage.py` accept
  exactly `--authority-root`, `--generation-index`, `--generation-root`, `--hard-score-root`,
  `--judge-request-root`, `--judge-attempt-root`, and `--output-root`; it calls only
  `Runtime.seal_judge`. Both use `allow_abbrev=False`, exclusive outputs, content-free errors, no raw
  identity/digest/mode options, and never serialize the verified capability. After the judge/provider
  root is written, `Runtime.seal_judge` fresh-calls
  `load_verified_benchmark_provider_evidence(
  generation_expectation=runtime_capability.expectation,
  provider_index_path=provider_index_path, generation_root=generation_root,
  hard_score_root=hard_score_root, judge_request_root=judge_request_root,
  judge_attempt_root=judge_attempt_root, judge_root=judge_root)`; the loader must exact-compare that external in-memory wrapper with every serialized
  expectation, predecessor/final authority root, context, workflow, and four-root binding. It never
  reconstructs a verified expectation from provider-index bytes.
- [ ] Implement the exact adapter boundary
  `seal_judge_attempt_root(*, attempt_root: Path, request_root_index: LayerRootIndexV1,
  request_attachments: Sequence[JudgeRequestAttachmentV1],
  batch_results: Sequence[BatchRunResultV1]) -> VerifiedJudgeAttemptRootV1` in
  `campaign.benchmark_adapter`. It maps only class-bound controller/receipt/spend/delivery evidence
  and verified request attachments into benchmark-owned neutral `index` and `boundaries` values,
  calls `write_judge_attempt_root(attempt_root, index=index, boundaries=boundaries)` once at an empty
  owned root, then calls
  `load_verified_judge_attempt_root(attempt_root,
  expected_request_root_index_sha256=request_root_index.layer_root_index_sha256,
  request_attachments=request_attachments)` and byte-compares all 36 boundaries/index before
  returning that verified wrapper.
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

#### Step 5: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/controller.py src/laconian_eval/campaign/benchmark_adapter.py src/laconian_eval/campaign/runtime.py tools/benchmark_hard_score_stage.py tools/benchmark_seal_judge_stage.py src/laconian_eval/capsule/execution.py tests/campaign/test_controller.py tests/campaign/test_benchmark_adapter.py tests/campaign/test_runtime.py tests/capsule/test_execution.py tests/capsule/test_resume.py tests/test_public_contract.py
git commit -m "feat: run bounded resumable benchmark batches"
```

### Task 8: Seal the private Runtime and replay isolation boundary

**Files:**

- Modify: `src/laconian_eval/campaign/runtime.py`
- Modify: `src/laconian_eval/campaign/controller.py`
- Modify: `tools/benchmark_hard_score_stage.py`
- Modify: `tools/benchmark_seal_judge_stage.py`
- Create: `tests/campaign/test_runtime_boundary.py`
- Modify: `tests/test_public_contract.py`

#### Step 1: RED-test the import and call graph

- [ ] Assert Runtime has exactly these live method owners and no public constructor:

```text
laconian_eval.campaign.runtime.Runtime.hard_score
laconian_eval.campaign.runtime.Runtime.prepare_judge
laconian_eval.campaign.runtime.Runtime.seal_judge
laconian_eval.campaign.runtime._reconstruct_verified_runtime
```

- [ ] Prove `Runtime()` raises, `_reconstruct_verified_runtime` is absent from
  `campaign.__init__.__all__`, and neither the Runtime object nor its capability can be Pydantic-
  dumped, JSON encoded, pickled, copied into a provider index, or accepted from a caller-supplied
  callback/path/hash. No shared state-writer or authority-mutation callable is reachable from these
  methods.
- [ ] Inspect the existing `laconian_eval.cli:main` graph. Its exact seven public commands remain
  `hard-score`, `prepare-judge`, `seal-judge`, `sample-audit`, `seal-audit`, `analyze`, and `verify`;
  every handler imports only `laconian_eval.replay`. Prove replay cannot import `campaign.runtime`,
  `campaign.publication`, either private constructor, the capability type, broker client, or
  authority writers. Runtime cannot import replay handlers.
- [ ] Prove there is no `laconian_eval.campaign.cli`, second console script, public campaign
  parser, generic writer entrypoint, or workflow invocation of `laconian_eval.cli:main`. This task
  tests only the three now-existing Runtime methods; Publication Task 7 creates the four future
  `laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.sample_audit`,
  `.seal_audit`, `.analyze`, and `.verify` methods plus
  `laconian_eval.campaign.publication._reconstruct_verified_publication`. Publication Task 15 proves the final seven-live
  tuple without inventing future modules or imports here.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_runtime_boundary.py tests/test_public_contract.py -q
```

Expected RED: Runtime construction/export and replay import boundaries are not yet closed.

#### Step 2: GREEN the private boundary

- [ ] Make Runtime construction token-gated by a module-private sentinel produced only after exact
  authority reconstruction. Keep the capability in private slots and make serialization/copy
  attempts fail with content-free errors.
- [ ] Make both fixed stage tools import only `_reconstruct_verified_runtime` plus the three exact
  methods, use fixed literal paths supplied by their workflows, and expose no reusable parser or
  arbitrary method name.
- [ ] Run the focused boundary tests plus Evaluation's offline CLI tests to GREEN.

#### Step 3: Commit

- [ ] Commit:

```bash
git add src/laconian_eval/campaign/runtime.py src/laconian_eval/campaign/controller.py tools/benchmark_hard_score_stage.py tools/benchmark_seal_judge_stage.py tests/campaign/test_runtime_boundary.py tests/test_public_contract.py
git commit -m "feat: isolate private benchmark runtime methods"
```

### Task 9: Add OIDC-brokered preflight and live-batch workflows

**Files:**

- Create: `.github/workflows/benchmark-preflight.yml`
- Create: `.github/workflows/benchmark-batch.yml`
- Create: `.github/workflows/benchmark-dismiss-hold.yml`
- Create: `.github/workflows/benchmark-publication-state.yml`
- Create: `tools/benchmark_preflight_stage.py`
- Create: `tools/benchmark_prepare_batch.py`
- Create: `tools/benchmark_run_batch.py`
- Create: `tools/benchmark_post_batch.py`
- Create: `tools/benchmark_prepare_hold_dismissal.py`
- Create: `tests/campaign/test_workflow_policy.py`
- Modify: `tests/test_ci_contract.py`

#### Step 1: RED-test workflow policy structurally

- [ ] Parse YAML and reject aliases/merge keys before schema inspection.
- [ ] `benchmark-preflight.yml` must be no-input `workflow_dispatch` only, have top-level
  `permissions: {}`, the literal shared concurrency group, no environment, and no secret expression.
  Require `github.ref_type == "tag"`, exact input-tag grammar, tag-object/peeled-commit verification,
  and prove the actual `GITHUB_WORKFLOW_REF` path plus running workflow bytes/hash equal that exact
  `C0` workflow-inventory member; default-branch/branch dispatch or a mutable workflow copy fails. It
  has a read-only `prepare-preflight` job with exactly `contents: read` and
  `pull-requests: read`, used in part to re-fetch the three exact protocol attestations. Its
  state-mutation job calls only the same-repository reusable
  `benchmark-publication-state.yml` with the canonical `PREFLIGHT_SEALED` request. No App ID,
  installation ID, key, token, state credential, arbitrary pack, or write-capable repository token
  exists in Actions. The external broker creates
  `refs/heads/benchmark-authority/{campaign_id}` only with `expected_absent` and the all-zero old
  SHA-1 OID; an existing divergent ref or simultaneous creator fails atomically.
- [ ] `benchmark-batch.yml` must be no-input `workflow_dispatch` only from the immutable input tag,
  use the literal shared concurrency group, and contain
  exactly four jobs: secret-free `prepare`, key-free narrow `receipt-writer`, environment-gated
  read-only `provider`, and provider-secret-free `post`. Each state mutation crosses the fixed
  `benchmark-publication-state.yml` OIDC boundary; the external broker uses the frozen state-writer
  App and exact expected-old-OID receive-pack lease. No Actions job receives an App token, and no
  job can create its own commit, packfile, endpoint, ref, or mutation event.
- [ ] Under top-level deny, batch `prepare` declares exactly `contents: read, actions: read`;
  `receipt-writer` declares only the reads required to bind jobs/deployments plus `id-token: write`
  inside the reusable boundary; provider uses the exact scopes below; and `post` has only read scopes
  plus the reusable OIDC call. No implicit workflow permission is accepted. The broker-held App
  token, never either repository token, performs each authority mutation.
- [ ] `prepare-preflight`, batch `prepare`, and batch `provider` check out the registry-recorded
  detached commit with `persist-credentials: false` and reverify the input tag object. State-writer
  jobs do not check out candidate code; the reusable state job contains no checkout at all.
- [ ] The provider job has `permissions: {contents: read, actions: read, deployments: read}`,
  `environment: benchmark-live`, `timeout-minutes: 180`, and no repository-write scope.
- [ ] The provider and receipt-writer both depend on `prepare`, not on each other. Provider is
  statically named and first enters the protected environment/read-only wait step. Receipt-writer
  uses the run-attempt jobs/deployment/approval APIs to discover and bind its exact numeric identity,
  constructs the canonical mutation request, and presents GitHub OIDC only through the reusable
  state job. The provider's bounded wait accepts only the canonical broker receipt and winning
  OID/digest for itself. Its next
  key-bearing step maps only `${{ secrets.OPENAI_API_KEY }}` and no App credential or write token.
  Expression-location and job-graph tests enforce this order; a missing/ambiguous provider job or
  approval times out with zero broker mutation and zero key lookup.
- [ ] The literal secret expression `${{ secrets.OPENAI_API_KEY }}` appears exactly once, under
  `env` of the single fixed `tools/benchmark_run_batch.py` step. It is absent from workflow/job env,
  checkout, setup, artifact download/upload, post-controller, state-broker calls, and `always()`
  steps. The four fixed workflow tools accept only closed literal paths and derive every model,
  phase, event, price, retry, ref, and authority ID from verified records; none is a public console
  entry point or reusable arbitrary parser.
- [ ] `benchmark-dismiss-hold.yml` is no-input `workflow_dispatch` only. A read-only inspector
  first requires exact `refs/heads/main` and the dismissal plan's pre-bound current-main SHA; it
  verifies the caller and reusable workflow bytes against the campaign's C0-derived workflow root
  and derives the one campaign/authority-ref identity only from the accepted plan/authority package.
  It accepts no tag/PR/other branch, campaign/ref/hash input, or latest/by-name authority discovery.
  The inspector reconstructs that exact canonical ref and proves there is exactly one dismissible
  benign hold; a separate read-only `authorize-dismissal` job uses `benchmark-publish` only to
  capture a distinct human approval; and a no-environment state job presents only its canonical
  dismissal request and OIDC to the reusable broker boundary. The fixed
  `tools/benchmark_prepare_hold_dismissal.py` binds the hold, source/trigger/approval numeric
  identities, expected ref OID, and `HoldDismissalMutationV1`. That mutation leaves state name/hash,
  spend, inventory, correction, and publication roots unchanged while removing only the exact dismissible
  hold from the unresolved-hold root. It accepts no hold ID, actor,
  reason, ref, campaign, or event input. The broker performs one exact old-OID lease and the
  workflow no-ops only when the exact dismissal is already canonical.
- [ ] `benchmark-publication-state.yml` is a same-repository `workflow_call` reusable workflow with
  exact job ID `state_writer`, no environment, no checkout, no artifact action, no generated shell,
  no caller-controlled action, and no secret. The entire job contains only GitHub's OIDC bootstrap
  and one full-SHA-pinned, argument-closed broker-client invocation. `id-token: write` is job-scoped;
  `state-cas` is only a reviewed step ID, never an asserted OIDC claim. The broker requires the fully
  qualified caller and called `workflow_ref`/`job_workflow_ref`, both workflow SHAs, exact run/job/
  check-run identity, and the same trigger ref; bare paths or synthetic `workflow_ref@C0` checks fail.
- [ ] Pin the exact ordered 15-path workflow tuple from the approved design and recompute its C0
  member hashes/root. Runtime creates only its four owned workflow files; synthetic C0 fixtures
  supply the eleven later-owned members. Reject missing, extra, reordered, mutable-main, or
  independently supplied workflow roots. Publication Task 13 replaces the synthetic boundary with
  the complete real-byte cross-slice proof.
- [ ] Freeze exactly three pairwise-distinct installed App identities:
  `state_writer`, `publisher`, and `release_finalizer`. The first is usable only inside the external
  state broker; the latter two require `benchmark-publish`. Pre-register the one
  `security_attestor` capability as a downscoped token from the existing release-finalizer
  installation with only `administration:read`, `metadata:read`, and `contents:read`; it is not a
  fourth App. Its later fixed `benchmark-publish` job runs with `environment: benchmark-publish`,
  has exact main/ref/plan/OIDC policy, no
  provider key or model/artifact bytes, and release-writing tokens from the same installation omit
  Administration permission.
- [ ] Reject `pull_request_target`, `workflow_run`, cron, arbitrary shell inputs, unpinned actions, third-party actions in the key-bearing job, `set -x`, persisted checkout credentials, and dynamic `uses`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_workflow_policy.py tests/test_ci_contract.py -q
```

Expected RED: workflow files are missing.

#### Step 2: GREEN the four Runtime-owned workflows

- [ ] Pin every action to a full 40-character commit. Use the repository's existing checkout/setup pins and the approved artifact pins.
- [ ] In `prepare-preflight`, seal the verified tagged registry and emit a receipt-bound
  `PREFLIGHT_SEALED` candidate. Its reusable state call gives no repository write permission and
  sends only OIDC plus the canonical request. The external broker re-verifies the tag, registry,
  candidate, Git identity, and expected-absent ref, then constructs and installs the deterministic
  parentless authority commit through the all-zero-old-OID receive-pack command. `benchmark-batch`
  cannot prepare work
  until reconstruction from that canonical ref yields `PREFLIGHTED`.
- [ ] In `prepare`, retrieve authority/checkpoint artifacts by exact numeric ID and exact workflow-run provenance, reconstruct state, create reservations, and upload only the safe prepared batch.
- [ ] Give `prepare` one closed recovery branch for an already canonical `GENERATION_ACTIVE` or
  `JUDGE_ACTIVE` receipt. It loads the prior provider run/job only from that receipt, exhaustively
  re-fetches the exact job-step timeline and controller/artifact inventory, and may emit
  `NO_DISPATCH_PROVED` only when the key-bearing step provably never started and no dispatch marker
  exists. Receipt-writer/provider are skipped; `post` sends the recovery candidate through the same
  reusable broker boundary. A started/uncertain step emits `PERMANENT_STOP`, while verified partial evidence emits
  `VERIFIED_PARTIAL`. No workflow input selects run, job, receipt, event, or recovery mode.
- [ ] In `receipt-writer`, resolve the exact provider job/deployment/approval identity through
  GitHub APIs. Combine the prepared official-source capture with that exact approved job/deployment
  record to construct `PriceAttestationV1`, require its source observation to be no more than 24
  hours before approval, bind the current frozen five price/source roots, default tier,
  explicit/30m cache policy, recursive no-breakpoint proof, and captured approval API digest, then
  consume the receipt and win the Task 6 external-broker receive-pack lease. No workflow input or operator
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
  capability in-process and calls `Runtime.seal_judge`; public replay `seal-judge` is
  forbidden in the live workflow. All paths are fixed workflow literals, never artifact
  interpolation. `ATTEMPTS` is exactly the adapter-written,
  fresh-loaded `JudgeAttemptRootIndexV1` plus its 36 fixed boundary files. Reload all 36
  `JudgeAttachmentV1` records (including zero-call attachments), and create the
  `JUDGE_SET_SEALED` candidate. Generation completion analogously creates
  `GENERATION_SET_SEALED`. Before that generation event, the Slice 3 adapter writes the generation
  `LayerRootIndexV1` and `GENERATION/generation-context.json`, binding the campaign seed, peeled
  commit, tagged hard-scorer source, hard-score/judge/statistics/audit protocols,
  workflow-inventory root, both
  reviewer registries, the three-role `protocol_attestations_root`, and
  the 36 capsule/sidecar pairs. It also writes the exact authority-package
  `GENERATION_COMPLETE/generation-context-expectation.json`; the candidate/event and artifact
  inventory bind the generation root, context, and expectation digests. These generation/judge set projections have null direct
  scan receipts and bind/recompute the complete transitive direct-receipt root; the provider-evidence
  verifier later rejects any missing/substituted receipt or false direct-scan claim. The external
  broker alone commits either event to the
  canonical authority ref;
  `benchmark-evidence.yml` therefore cannot begin until the authoritative state is
  `JUDGE_COMPLETE`.
- [ ] The fixed reusable job and broker reconstruct only same-run receipt-bound candidate evidence
  by numeric artifact identity. The broker attempts one exact old-OID receive-pack command; a stale
  sibling fails without selecting a newer candidate, and response-loss recovery adopts only the
  byte-identical expected commit. Tests reject REST ref writes and any force/delete command.
- [ ] Workflow-policy tests prove no state App ID, installation ID, private-key name/value, JWT,
  installation token, publisher credential, or release-finalizer write credential occurs anywhere
  in Actions YAML, tool inputs, artifacts, logs, or child environments. Every repository
  `GITHUB_TOKEN` remains read-only. Altering the reusable workflow, broker client digest, caller/
  callee identity, mutation request, returned permissions, or Git-identity digest fails before ref
  mutation.
- [ ] Set every authority artifact to `retention-days: 90` and preserve exact API artifact IDs/service digests in successor provenance.
- [ ] Rerun workflow policy tests to GREEN.

#### Step 3: Prove no secret use in PR/fork CI

- [ ] Extend `test_ci_contract.py` to scan every workflow for provider secret references and assert only `benchmark-batch.yml` contains the one approved occurrence.
- [ ] Assert all PR/fork jobs retain read-only repository permissions and cannot dispatch live work.
- [ ] Add crash/race fixtures for pre-key lease loss, post-lease/pre-key crash, `ACTIVE` with a provably
  skipped key step, and `ACTIVE` with an uncertain/started key step. Only the first provable case may
  use `NO_DISPATCH_PROVED`; all others make zero new calls and remain stopped until invalid
  finalization.
- [ ] Run all workflow contract tests.

#### Step 4: Commit

- [ ] Commit:

```bash
git add .github/workflows/benchmark-preflight.yml .github/workflows/benchmark-batch.yml .github/workflows/benchmark-dismiss-hold.yml .github/workflows/benchmark-publication-state.yml tools/benchmark_preflight_stage.py tools/benchmark_prepare_batch.py tools/benchmark_run_batch.py tools/benchmark_post_batch.py tools/benchmark_prepare_hold_dismissal.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py
git commit -m "ci: add protected benchmark batch workflows"
```

### Task 10: Rehearse pilot bounds and the full offline runtime

**Files:**

- Create: `tests/campaign/test_runtime_synthetic.py`
- Create: `benchmarks/runbooks/public-benchmark.md`
- Modify: `tests/campaign/test_preflight.py`
- Modify: `tests/campaign/test_controller.py`

#### Step 1: RED-test the pilot contract end to end

- [ ] Materialize one shared scenario in both locales, four arms, one repetition, and all three models.
- [ ] Assert 24 generation calls, no generation retries, at most 24 judge calls, no judge retries, and total authorized exposure no greater than `5_000_000` micro-USD.
- [ ] Interrupt after a deterministic request, pack/restore the exact partial capsule, generate a new batch receipt, and resume only the exact suffix.
- [ ] Reject any pilot setting or workflow input that permits a 25th generation or judge attempt.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_runtime_synthetic.py::test_pilot_is_bounded_to_48_total_attempts -q
```

Expected RED: the integrated pilot fixture is absent.

#### Step 2: GREEN a provider-offline 1,440-row runtime

- [ ] Use deterministic fake/replay providers to execute all 36 generation shards through multiple batches, including one 429 retry, one ordinary rejection, one partial checkpoint, and exact suffix resume.
- [ ] Drive deterministic hard-score fixture attachments, then run all 36 judge attachments through the same controller contract.
- [ ] Reconstruct the authority-only in-memory capability and invoke exactly
  `Runtime.hard_score`, `Runtime.prepare_judge`, and `Runtime.seal_judge`; prove no public replay
  handler, serialized capability, public campaign CLI, or caller-supplied expected root participates.
- [ ] Assert exact ordered coverage, distinct receipts per provider job, charged/reserved totals below `75_000_000`, no unresolved holds, and zero calls after a synthetic STOP branch.
- [ ] Reconstruct every state/spend/checkpoint artifact from exact IDs and hashes at the end.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_runtime_synthetic.py -q
```

#### Step 3: Write the operator and broker runbook

- [ ] Document exact no-input workflow dispatches for preflight, batch approval, resume,
  no-dispatch proof, STOP, hold dismissal, and invalid-prefix handoff; document external broker
  health, OIDC audience/JWKS/subject checks, receive-pack lease receipts, response-loss
  reconciliation, App-key rotation, provider-key revocation, and the three fixed App identities.
  There is no public campaign-authority command. The seven public replay commands remain offline and
  non-evidentiary.
- [ ] State plainly that GitHub environment approval is per job, every resumed batch needs another approval, artifacts expire after 90 days, and no live call is permitted before all setup gates in the roadmap pass.
- [ ] Include expected safe summaries and escalation actions; never include a secret value or an instruction to print it.
- [ ] State that `security_attestor` is a release-finalizer-App downscope, not a fourth App; its
  Administration-read token is broker-minted only for the future fixed publication job and never
  coexists with a release-write token.

#### Step 4: Run the slice regression gate

- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign tests/capsule tests/test_openai_provider.py tests/test_providers.py tests/test_runner.py tests/test_reporting.py tests/test_cli.py tests/test_ci_contract.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
git diff --check
```

Expected GREEN: every command exits 0. No provider credential or network access is used.

#### Step 5: Commit

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
- [ ] Independent security review confirms the provider job is read-only and the provider secret is
  step-scoped; Actions contains no state App key/token; the reusable OIDC boundary, exact broker
  caller matrix, SHA-1 object construction, and receive-pack old-OID leases match the approved
  design.
- [ ] Independent statistical/evidence review confirms request identities and usage fields match the approved protocol.
- [ ] No live workflow is dispatched by this implementation plan. Live pilot authorization remains a separate maintainer action after the roadmap setup gate.
