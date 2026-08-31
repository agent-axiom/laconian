# Public Three-Model Benchmark Campaign Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the fail-closed campaign authority, exact spend accounting, bounded batch planning, closed retry policy, resumable provider controller, and GitHub Actions credential boundary required to run the pilot and three-model campaign.

**Architecture:** Keep a campaign control plane beside, not inside, the generation capsule. `CampaignStateSchemaV1` is the sole source for states, events, evidence discriminators, caller/ref policy, reachability, and terminality; generated Python projections and broker policy are checked against that one schema. GitHub Actions never receives a state-writer App key or installation token. Its fixed reusable state job presents GitHub OIDC plus a canonical mutation request to an external broker, and the broker alone constructs canonical Git SHA-1 objects and advances the protected authority ref through smart-HTTP `receive-pack` with an exact old-OID lease. A secret-free prepare job reserves exact worst-case exposure and seals one contiguous `BatchPlanV1`; the protected read-only provider job reconstructs the winning receipt before its single controller step maps `OPENAI_API_KEY`. Live hard-score and judge sealing are available only through an in-memory authority capability and the three private Runtime methods.

**Tech Stack:** Python 3.11+, Pydantic 2 strict/frozen models, integer micro-USD arithmetic, existing canonical JSON and descriptor-bound capsule primitives, pytest, Hypothesis-free deterministic property loops, Ruff, mypy, GitHub Actions with full-SHA pins, and the OpenAI Responses adapter with SDK retries disabled.

---

## Execution contract

- Approved design: `docs/superpowers/specs/2026-08-30-public-three-model-benchmark-design.md`, especially Sections 6.2, 6.5–6.6, 7, 8, 12, 14, and 16.
- Normative design commit: `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`.
- Maintainer approval record: governance-only commit
  `d6b147aefb0bab0e64a41541a67e2c1b8f4d00ad`, recording the exact user message
  `Одобряю amendment 05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126` on 2026-08-31.
- Milestone 0 is approved. Runtime implementation is unblocked only after this synchronized plan is
  reviewed and committed; pilot and publication gates remain closed until their named tests and
  reviews pass.
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
src/laconian_eval/campaign/tag_binding.py    exact paired annotated-tag and raw Git-object verification
src/laconian_eval/campaign/preflight.py      stable campaign registry and exposure seal
src/laconian_eval/campaign/state_schema.py   sole canonical CampaignStateSchemaV1 source
src/laconian_eval/campaign/state.py          generated state/event models and pure transitions
src/laconian_eval/campaign/state_broker.py   OIDC request/receipt types and closed caller policy
src/laconian_eval/campaign/authority_git.py  canonical SHA-1 objects and receive-pack lease verifier
src/laconian_eval/campaign/authority.py      trusted-chain reconstruction and pure mutation packages
src/laconian_eval/campaign/broker_wire.py    shared cycle-free broker policy/signing registry wire
src/laconian_eval/campaign/publication_wire.py Runtime-owned initial-publication receipt/append wire
src/laconian_eval/campaign/release_wire.py   sole shared release effect/receipt/append wire
src/laconian_eval/campaign/release.py        canonical security-attestor substrate, extended by Publication
src/laconian_eval/campaign/release_broker.py safe attestor policy verifier; no token-bearing vault code
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
tools/benchmark_release_broker_client.py     fixed secret-free attestor OIDC client
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
VerifiedCampaignInputPackageV1
CampaignPreflightSealV1
CampaignRegistryPayloadV1
CampaignRegistryV1
CampaignStateSchemaV1
StateWriterGitIdentityV1
StateBrokerCallerPolicyV1
CampaignEventMutationSourceV1
AuthorityMutationRequestV1
AuthorityMutationReceiptV1
AuthorityRefReconciliationReceiptV1
BrokerTokenDeliveryIsolationPolicyV1
BrokerSigningKeyV1
BrokerSigningIdentityV1
BrokerCallerAuthorizationReceiptV1
BrokerTokenRequestDispatchReceiptV1
BrokerTokenRedactedSuccessArchiveV1
BrokerTokenSafeSuccessProjectionV1
BrokerTokenRequestTransportReceiptV1
BrokerResponseZeroizationReceiptV1
BrokerTokenUnrecoverabilityReceiptV1
BrokerTokenClosureDispatchReceiptV1
BrokerTokenDeleteAttemptV1
BrokerTokenDenialProbeV1
BrokerVaultScopeIdentityV1
BrokerVaultAuditEntryV1
BrokerVaultAuditLogV1
BrokerVaultAuditPrefixV1
PublicationBranchReceiptV1
PublicationPRReceiptV1
InitialBranchReceiptAppendV1
InitialPRReceiptAppendV1
InitialPublicationReceiptAppendV1
PublicationMergeDenylistEntryV1
PublicationMergeDenylistV1
PublicationTerminalContainmentPreflightV1
PublicationPreContainmentTerminalRouteV1
PublicationTerminalContainmentIntentV1
PublicationTerminalContainmentFinalityV1
ReleaseEffectAuthorizationV1
ReleaseEffectResultV1
AnnotatedTagEffectResultsV1
InstallationTokenRevocationReceiptV1
FinalReleaseVerificationReceiptV1
TagReceiptV1
DraftReleaseReceiptV1
ReleaseAssetReceiptV1
PublishReceiptV1
InitialTagReceiptAppendV1
InitialDraftReleaseReceiptAppendV1
InitialAssetReceiptsAppendV1
InitialPublishReceiptAppendV1
InitialReleaseReceiptAppendV1
VerifiedPhasePlanV1
CredentialScanReceiptV1
InvalidEventDismissalPlanV1
InvalidEventDismissalEvidenceV1
InvalidEventNondismissibilityEvidenceV1
HeldResultMergedConsumptionV1
ProtocolAuthorityDriftEvidenceV1
CredentialExposurePendingV1
CredentialExposureEffectReceiptV1
CredentialExposureProgressRootV1
CredentialExposureSupplementV1
TerminalCredentialExposureConsumptionV1
AuthorityMutationV1
CheckpointInventoryV1
BatchPreparationRequestV1
BatchRunResultV1
RepositoryTrustBoundaryAttestationV1
MainFallbackLivenessPolicyV1
ArtifactEnvelopeV1
UploadAuthorizationV1

apply_campaign_event(
    ReconstructedAuthorityV1,
    CampaignEventV1,
    expected_state_sha256: str | null,
    expected_unresolved_hold_root: str | null,
    expected_active_credential_exposure_incident_id: str | null,
    expected_active_credential_exposure_pending_root: str | null,
    expected_authority_ref_oid: str | null
) -> AuthorityMutationV1

dismiss_invalid_event_hold(
    ReconstructedAuthorityV1,
    InvalidEventDismissalPlanV1,
    InvalidEventDismissalEvidenceV1,
    expected_authority_ref_oid: str
) -> AuthorityMutationV1

append_initial_publication_receipt(
    ReconstructedAuthorityV1,
    InitialPublicationReceiptAppendV1,
    expected_state_sha256: str,
    expected_authority_ref_oid: str
) -> AuthorityMutationV1

append_initial_release_receipt(
    ReconstructedAuthorityV1,
    InitialReleaseReceiptAppendV1,
    expected_state_sha256: str,
    expected_authority_ref_oid: str
) -> AuthorityMutationV1

build_terminal_credential_exposure_consumption(
    ReconstructedAuthorityV1,
    CredentialExposureIncidentEvidenceV1
) -> TerminalCredentialExposureConsumptionV1

require_ordinary_effect_gate(ReconstructedAuthorityV1) -> None

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

The Runtime stable interface exports `require_ordinary_effect_gate` from `laconian_eval.campaign`.
It first proves the active incident-ID/pending-root pair invariant and reconstructs the monotone
publication merge-denylist root, then gates every ordinary credential, effect, and event on the hold
root, both active-exposure fields, and `active_publication_terminal_containment_root` being null.
Typed exposure/containment consumers and the two closed receipt-append families bypass it only
through generated exact `CampaignStateSchemaV1`/non-event broker rows, never through a caller flag
or alternate helper. Every bypass byte-preserves or performs the one schema-authorized transition
of the denylist/containment roots.

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

- [ ] Add payload factories only for Runtime-owned strict Git transport/ref-observation identities,
  `ProviderJobIdentityV1`, `PriceAttestationV1`,
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
  `administration:write`, `contents:read`, and `metadata:read`; `administration:write` is GitHub's
  required permission name for the immutable-Releases settings read, while the attestor's fixed
  endpoint/query policy contains no mutation. Release-writing tokens from that App omit
  Administration permission.
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

Expected GREEN: PASS; the strict identity/artifact models and every hostile canonical vector pass.

#### Step 4: Commit

- [ ] Review `git diff --check` and commit:

```bash
git add src/laconian_eval/campaign/__init__.py src/laconian_eval/campaign/models.py src/laconian_eval/campaign/artifact_wire.py tests/campaign/__init__.py tests/campaign/test_models.py tests/campaign/test_artifact_wire.py
git commit -m "feat: define canonical campaign identities"
```

### Task 2: Bind immutable input tags and seal preflight

Do not start this task until Evaluation Task 3 has committed
`src/laconian_eval/benchmark/protocol_review.py` and its canonical package exports. The gate imports
the Evaluation-owned protocol-review types/helpers named below, checks defining-module and object
identity, and must be GREEN before any Runtime schema, fixture, or preflight code is added.

**Files:**

- Create: `src/laconian_eval/campaign/tag_binding.py`
- Create: `src/laconian_eval/campaign/preflight.py`
- Create: `src/laconian_eval/campaign/broker_wire.py`
- Create: `src/laconian_eval/campaign/spend.py`
- Create: `tests/campaign/test_tag_binding.py`
- Create: `tests/campaign/test_input_package.py`
- Create: `tests/campaign/test_preflight.py`
- Create: `tests/campaign/test_broker_wire.py`
- Create: `tests/campaign/test_spend.py`
- Create: `tests/campaign/test_trust_boundary.py`
- Create: `tests/campaign/test_state_schema_fixture.py`
- Create: `tools/benchmark_capture_trust_boundary.py`
- Create: `tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.json`
- Create: `tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.sha256`
- Create: `tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-sol.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-terra.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-luna.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign-seed.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/price-snapshot.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/reviewers.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-reviewers.yaml`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary-signature.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmark/security/tag-operator-registry.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmark/security/tag-ruleset-policy.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmark/security/invalid-event-dismissal-policy.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmark/security/main-fallback-liveness-policy.json`
- Create: `tests/fixtures/public-benchmark-input-v1/benchmark/security/protocol-bundle-builder-git-identity.json`
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

This task implements Runtime integration and synthetic tagged-repository fixtures only; neutral
protocol-review schemas remain Evaluation-owned. It must not create the
live `evals/manifests/public-benchmark-*`, `benchmarks/campaigns/public-three-model-v1/*`, or
`benchmarks/protocols/public-three-model-v1/*` records. The roadmap's post-implementation freeze
task owns those paths after all workflows, protocols, tests, and independent reviews exist.

Evaluation owns `src/laconian_eval/benchmark/protocol_review.py` and every neutral protocol-review
schema/helper: operator/ruleset/workflow types, statements, stable REST/GraphQL/local evidence,
`InputTagMessageV1`, `ProtocolAttestationTagMessageV1`, `ProtocolBundleBuilderGitIdentityV1`,
envelopes, bundle, tag binding, `TagRulesetObservationReceiptV1`,
`ArchivedApiReceiptBindingV1`, archive, raw-object grammar, digest preimages, and
network-free importer. Runtime imports those exact classes/functions, checks `__module__` and object
identity, and class-bound revalidates their outputs; it must not define, subclass, copy, or re-export
a second schema. Runtime owns only repository/GitHub observation orchestration in `tag_binding.py`,
stable `CampaignRegistryV1`/preflight, `MainFallbackLivenessPolicyV1`, and campaign state/authority.
In particular, Runtime imports package exports `CanonicalJSONV1Error`, `canonical_json_v1`, and
`parse_canonical_json_v1` by object identity with their sole definitions in
`laconian_eval.benchmark.attachments`, and imports `ProtocolSubjectKindV1` plus immutable
`PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1` by object identity with their sole definitions in
`laconian_eval.benchmark.protocol_review`. It defines no JSON encoder/parser, copied Literal/tuple,
or compatibility export. Runtime's LF-domain helpers call the imported canonical encoder directly;
they never use Evaluation's internal NUL-domain `canonical_json_v1_digest`.

#### Step 1: RED-test tag resolution without credentials

- [ ] Test the deterministically paired annotated-only refs
  `benchmark-input-YYYYMMDD.N` and `benchmark-attestations-YYYYMMDD.N` in temporary Git
  repositories, including the complete serial reviewer/bundle closure.
- [ ] Reject a lightweight or tag-of-tag ref, branch/raw commit, wrong suffix/namespace, moving/deleted
  alias, malformed date/sequence, mismatched tag object or peeled C0/B0, dirty checkout, unavailable
  object, shallow closure, replace/graft, mixed campaign, or any tag/commit/tree/blob byte that does
  not reproduce both expected hashes.
- [ ] Patch `os.environ` with a credential canary and prove tag verification neither reads nor serializes `OPENAI_API_KEY`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_tag_binding.py -q
```

Expected RED: `tag_binding` imports fail.

#### Step 2: GREEN exact paired-tag and object-closure binding

- [ ] Implement `bind_protocol_review_pair(repository, input_tag_ref, companion_tag_ref)` with
  non-shell Git plumbing through a narrow subprocess runner. Permit only the two exact ref regexes
  and the same nonzero suffix; pass exact raw tag/commit/tree/blob bytes to Evaluation's fixed parser/
  verifier rather than trusting porcelain or implementing a Runtime parser.
- [ ] Verify T0/C0/Rstat/Rjudge/Rsecurity/B0/T1, exact fixed paths/deltas/parents/messages/identities,
  all raw-object hashes, bundle/root, operator/ruleset roots, and signatures before returning the
  complete `ProtocolAttestationTagBindingV1`. Record each double-read observation separately; no
  observation time/request ID/ETag enters identity.
- [ ] Run preflight twice for the same immutable pair with different observation times and assert the
  same tag binding, campaign registry/ID, authority ref, seed-derived order, and plans; only separate
  receipts differ.
- [ ] Use a fixed environment allowlist for Git subprocesses and reject replace objects, grafts,
  alternates that escape the verified object database, shallow missing closure, ambient Git identity,
  and any attempt to repair/recreate a ref in place.
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
- [ ] Define `campaign.yaml` as the strict C0-only `CampaignInputPackageV1` index binding the three
  manifest paths and hashes, exact `mode: pilot|confirmatory`, `campaign-seed.json`,
  `price-snapshot.yaml`, `reviewers.yaml`, `protocol-reviewers.yaml`, the repository trust-boundary attestation
  and detached signature, all seven protocol
  paths/hashes, corpus/arm/runner/dependency hashes, mode-independent caps, the exact
  tag-operator, tag-ruleset, publication-branch-ruleset, invalid-event-dismissal,
  main-fallback-liveness, protocol-bundle-builder, state-writer,
  `BrokerTokenDeliveryIsolationPolicyV1`, and ordered exact three `BrokerSigningKeyV1` security
  members/digests plus `broker_signing_keys_root_sha256`, and its own digest. The broker roles are
  exactly `publisher`, `release_finalizer`, `security_attestor` in that order; decoded SPKI bytes,
  validity windows, Ed25519 algorithm, per-key digest, fixed-three-leaf duplicate-last Merkle tree,
  and final wrapper root must all recompute. Reject the entire
  `benchmarks/protocol-reviews/<T0>/` subtree and every statement, envelope, attestation root,
  companion binding, B0/T1 value, or placeholder in C0 and `CampaignInputPackageV1`.
- [ ] Import Evaluation-owned exact three-field `WorkflowInventoryV1`, exact 15-member
  `BENCHMARK_WORKFLOW_PATHS_V1`, and `build_workflow_inventory`. Call the builder over the
  verified `C0` tree in the frozen literal `BENCHMARK_WORKFLOW_PATHS_V1` order and never sorts,
  reorders, or accepts caller-supplied entries. The schema contains exactly `schema_version`,
  `members`, and `workflow_root`; every member contains exactly `path` and `sha256`. It computes
  `SHA256(UTF8("laconian-workflow-inventory-v1\n") || CanonicalJSONV1(inventory without exactly
  workflow_root))`. Action-pin/policy proofs remain separate C0 evidence and are not implicit
  inventory fields. No workflow hash or
  inventory root is a source-code constant before the live freeze.
  Runtime Task 2 tests build a synthetic temporary `C0` containing all 15 paths; they do not depend on
  future Slice 4 files or the then-partial cumulative `tests/test_ci_contract.py`.
  `campaign.yaml`, all three later statements/envelopes, their bundle/tag binding, and the registry
  bind the same reconstructed root.
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
- [ ] Add a dedicated precredential RED test node for the approved SDK 3.3.1 contract. Import the
  exact Foundation-owned `BenchmarkSDKContractError` and
  `require_benchmark_sdk_contract` objects from `laconian_eval.providers`, assert their owner module
  is `laconian_eval.providers.openai`, and call exactly
  `require_benchmark_sdk_contract(c0_uv_lock_bytes=verified_c0.read_regular_file("uv.lock"),
  expected_c0_uv_lock_sha256=verified_input_package.uv_lock_sha256)`. The package member hash is
  independently bound by `VerifiedCampaignInputPackageV1`; no caller/workflow scalar supplies it.
  The internally constructed strict record requires OpenAI Python SDK version exactly `3.3.1`,
  exact C0 lock bytes/hash, the literal typed request-model fields, all canonical response paths,
  and its self digest. Instrument environment access, credential lookup, provider/client construction,
  OIDC/App-token mint, and network mutation; every `BenchmarkSDKContractError`, including the closed
  `serializer-projection` code, has the same fail-closed behavior and must occur before any of them.
  Runtime neither enumerates a smaller error-code subset nor defines a wrapper, copied constant, or
  second validator. The pure `_public_benchmark_responses_kwargs` serializer projection remains
  Foundation-owned: Runtime calls it only through the verified Foundation provider contract and
  does not define, copy, alias, or re-export it. Run
  this RED node explicitly:

  ```bash
  uv run pytest -p no:cacheprovider tests/campaign/test_preflight.py::test_openai_sdk_3_3_1_lock_and_models_verify_before_any_credential -q
  ```

  Expected RED: the Foundation-owned SDK/lock precredential verifier is absent. GREEN imports that
  exact object into secret-free preflight and reruns the same call immediately before every
  provider-key mapping; all credential/client/provider spies remain zero on failure.
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
  mode-compatible fingerprint plus canonical ASCII Git author/committer name and email used in its
  reviewer commit. Keyed modes require a fingerprint; `github_verified_commit`
  requires null; `security_evidence` always requires non-null and therefore cannot use
  `github_verified_commit`. Its canonical digest is independent of the two-person audit registry;
  no identity is inferred from an attestation line. Live freeze requires all three real bindings,
  while fixtures are explicitly synthetic. This is an explicit Task 2 integration edge on Slice 2
  Task 3; tag/Git/pricing work may proceed earlier, but preflight cannot turn GREEN without it.
  Slice 2 Task 8 later extends the already-owned context into the post-judge provider bridge.
- [ ] Import/class-bound revalidate Evaluation-owned one-operator `TagOperatorRegistryV1` from C0 with positive repository/account IDs,
  case-sensitive login, canonical tagger name/email, entry digest, and registry digest. Both digests
  use their exact newline domains and omit only their own self field; T0/T1 and the post-tag binding
  must match the same entry. Apply the normative 1-80-byte tokenized printable-ASCII name grammar,
  3-254-byte single-`@` email grammar, unsigned non-zero-padded bounded epoch, and literal `+0000` to
  registry and tag bytes identically.
- [ ] Load Runtime-owned exact C0 `InvalidEventDismissalPolicyV1` with repository ID, nonempty ascending strict
  `{account_id,login}` eligible list, exact digest, and no role/team/App/deploy-key/ambient-maintainer
  expansion. Load Runtime-owned exact `MainFallbackLivenessPolicyV1` and Evaluation-owned exact
  two-entry `TagRulesetPolicyV1` from their fixed paths and reproduce all three digests before any
  review or preflight value is accepted.
- [ ] Define/import only the Runtime-owned shared cycle-free broker registry wire in
  `campaign.broker_wire`: exact `BrokerTokenDeliveryIsolationPolicyV1`, `BrokerSigningKeyV1`, and
  `BrokerSigningIdentityV1`. The isolation policy has exactly the approved GitHub origin/version/
  token endpoint, ordered roles `publisher,release_finalizer,security_attestor`, one
  `{broker_role,vault_measurement_sha256}` per role in that order, and literal true fields
  `github_tls_terminates_inside_token_vault`,
  `complete_response_validation_precedes_token_commit`,
  `token_commit_precedes_executor_visibility`,
  `failed_token_commit_zeroizes_response_bytes`,
  `executor_accepts_only_committed_token_handles`; literal false fields
  `raw_token_bytes_leave_token_vault`, `raw_token_bytes_enter_actions`, and
  `unknown_delivery_allows_operation_dispatch`; followed by
  `broker_token_delivery_isolation_policy_sha256`; its domain is
  `laconian-broker-token-delivery-isolation-policy-v1\n`, omitting only that digest. A signing key has
  exactly schema/role/key ID/`Ed25519`/base64url SPKI/not-before/not-after/self digest under
  `laconian-broker-signing-key-v1\n`. A signing identity has exactly registry digest, nested key,
  three-key root and self digest under `laconian-broker-signing-identity-v1\n`. Publication imports
  these identical class objects; Runtime preflight rejects a second class/module, preflight-selected
  key, unknown key, wrong role/order/algorithm/window/root, invalid SPKI, or policy/vault measurement
  mismatch before any live authority or broker token request exists.
- [ ] In the same sole-owner `campaign.broker_wire` module, RED-test and implement the complete
  cycle-free broker/vault wire imported by Publication. Every class is strict/frozen/extra-forbid,
  uses the Evaluation-owned canonical encoder, verifies its nested duplicated digests, and has no
  raw token/JWT/header/cookie field. Freeze these exact ordered schemas and domains:

  - `BrokerVaultScopeIdentityV1`: `schema_version,scope_kind,campaign_id,
    campaign_registry_sha256,repository_id,publication_id,publication_attempt,correction_id,
    bundle_kind,sealed_root_sha256,publication_plan_sha256,authorizing_intent_sha256,release_phase,
    preauthorized_release_plan_sha256,release_intent_sha256,security_attestation_purpose,
    security_attestation_subject_sha256,scope_identity_sha256`, with the exact publication/release/
    security nullability matrix and domain `laconian-broker-vault-scope-identity-v1\n`;
  - `BrokerCallerAuthorizationReceiptV1`: campaign/registry/repository and nested scope pair,
    `broker_role,broker_policy_sha256,authorized_policy_row_sha256,caller_workflow_ref,
    caller_workflow_sha256,caller_job,job_workflow_ref,job_workflow_sha256,required_ref_class,
    oidc_issuer,oidc_audience,oidc_subject,oidc_repository,oidc_ref,oidc_sha,oidc_environment,
    run_id,run_attempt,check_run_id,actor,authenticated_at`, nested signing identity/signature and
    final digest. The signature and record domains are
    `laconian-broker-caller-authorization-signature-v1\n` and
    `laconian-broker-caller-authorization-receipt-v1\n`; issuer is exactly GitHub's token issuer,
    while raw JWT/App JWT and caller-supplied claim projections are forbidden;
  - `BrokerTokenRequestDispatchReceiptV1`: exact campaign/registry/repository/scope/role/App,
    broker policy/row and nested caller authorization, isolation-policy/vault-measurement roots,
    operation key, positive credential ordinal, vault transaction/request IDs and dispatch time,
    literal POST installation-token endpoint/API/accept/authentication values, ordered requested
    permissions, exact request body/payload root, nested signing identity/signature and digest under
    `laconian-broker-token-request-dispatch-{signature,receipt}-v1\n`. It is durably signed before
    the first request byte and contains no terminal or response field;
  - `BrokerTokenRedactedSuccessArchiveV1`: exact
    `schema_version,redacted_response_canonical_json_base64,token_replacement_fingerprint_sha256,
    redacted_response_sha256,redacted_success_archive_sha256` under
    `laconian-broker-token-redacted-success-archive-v1\n`; and
    `BrokerTokenSafeSuccessProjectionV1`: exact
    `schema_version,installation_id,repository_selection,repository_ids,permissions,
    token_fingerprint_sha256,expires_at,safe_success_projection_sha256` under
    `laconian-broker-token-safe-success-projection-v1\n`. Decoded archive bytes preserve the full
    201 response with only token text replaced, and the compact projection is a total deterministic
    extraction;
  - `BrokerTokenRequestTransportReceiptV1`: exact campaign/registry/repository/scope/role/App,
    broker policy/row, nested caller authorization, isolation/vault roots, operation key/credential
    ordinal/transaction, nested dispatch receipt, request/dispatch/terminal/nullable completion,
    literal dispatch/method/endpoint/API/accept/authentication, requested permissions/body/payload,
    `outcome=successful_201|definite_denial|delivery_unknown`, nullable status, returned permissions/
    repository IDs, nullable token fingerprint/expiry/vault-commit time, commit count, nullable safe-
    projection kind/root, nullable exact redacted archive and compact projection, nested signing
    identity/signature and digest under
    `laconian-broker-token-request-transport-{signature,receipt}-v1\n`. Success is exact committed
    201/count-one/full match; definite denial is only 401/403/404/422 with no token; every other,
    response-loss, malformed, or failed-commit result is delivery-unknown/count-zero and cannot
    dispatch an operation;
  - `BrokerResponseZeroizationReceiptV1`: exact campaign/registry/repository/scope/role/transaction/
    transport root, `zeroization_outcome`, buffer count, literal zero raw-token/handle counts, vault
    measurement, time, signing identity/signature and digest under the response-zeroization signature/
    receipt domains; and `BrokerTokenUnrecoverabilityReceiptV1`: exact campaign/registry/repository/
    scope/role/App/operation/credential/isolation fields, nested delivery-unknown transport receipt,
    status/transaction/outcome, literal zero commit/handle/dispatch/export/accessible-token counts,
    `uncommitted_response_bytes_zeroized=true`, vault measurement, nested zeroization receipt,
    predecessor audit entry, signing identity/signature/time/digest under
    `laconian-broker-token-unrecoverability-{signature,receipt}-v1\n`. The total outcome mapping is
    response loss -> `no_complete_response_received`, invalid response ->
    `complete_response_validation_failed`, valid 201 plus failed durable commit ->
    `durable_token_commit_failed`;
  - `BrokerTokenClosureDispatchReceiptV1`: exact scope/role/App/policy, operation key/credential,
    request/fingerprint/commit/expiry, `operation=delete|denial_probe`, ordinal/request/time and its
    literal DELETE-or-GET endpoint tuple, signing identity/signature/digest under the closure-dispatch
    signature/receipt domains. `BrokerTokenDeleteAttemptV1` has exact role/App/policy/ordinal/request,
    nested delete dispatch, times, DELETE endpoint tuple, fingerprint,
    `outcome=confirmed_204|response_lost|observed_non_204`, nullable status/safe response and
    `transport_receipt_sha256` under `laconian-broker-token-delete-attempt-v1\n`.
    `BrokerTokenDenialProbeV1` has the analogous exact repository/App/policy/fingerprint/ordinal/
    request, nested probe dispatch, times, GET repository endpoint tuple,
    `outcome=denied_401|response_lost|observed_retryable`, nullable status/safe response and digest
    under `laconian-broker-token-denial-probe-v1\n`;
  - `BrokerVaultAuditEntryV1`: exact nested scope, role/App, gapless ordinal/predecessor, nullable
    transaction/operation/credential, closed event kind, nullable fingerprint, source receipt,
    recomputed request/operation/live counts, time and digest under
    `laconian-broker-vault-audit-entry-v1\n`. `BrokerVaultAuditLogV1` contains the same scope/role/App,
    complete ordered entries, three literal zero final counts, signing identity/signature/seal time
    and root under the audit-log signature/record domains. `BrokerVaultAuditPrefixV1` contains exact
    scope/digest, publisher role/App, `prefix_purpose=containment_start|barrier_complete|
    pre_fence_attachment`, paired broker-ledger prefix, count/entries/last digest, recomputed three
    counts, signing identity/signature/time/root under the vault-prefix signature/record domains.

  Generate independent golden vectors for every field tuple/domain/signature omission, request-
  start/terminal bijection, response-loss branch, delete/probe first-decisive outcome, scope/role/App/
  signing-key join and the vault event table. Crash immediately before/after every durable append,
  network dispatch, vault commit, zeroization, delete and probe; replay must produce either the exact
  terminal record or a closed unrecoverability branch, with zero raw-token export and no operation
  dispatch from unknown delivery. `tests/test_public_contract.py` asserts every listed package export
  is object-identical to `campaign.broker_wire`, and Publication has no copy or alias.
- [ ] Require the seven canonical protocol files to be byte-complete projections of the implemented
  hard-score, judge, statistics, audit, retry, checkpoint, and publication contracts. Tests
  independently recompute every protocol hash and reject a file generated from a different source
  revision or containing an unknown/free-form execution field.
- [ ] Consume, but do not redefine, Evaluation's singular field
  `audit_protocol_sha256: Sha256`. Runtime Task 2 derives it only by descriptor-reading and hashing
  the verified C0 member
  `benchmarks/protocols/public-three-model-v1/audit.json` at the exact peeled input commit. Require
  that same field and value in `CampaignInputPackageV1`, `VerifiedCampaignInputPackageV1`, the
  typed `CampaignPreflightSealV1`/`PREFLIGHT_SEALED` evidence, authority genesis, and each typed
  downstream consumer that needs it. `CampaignRegistryV1` binds it only indirectly through
  `payload.campaign_input_package_sha256`; reject a caller/workflow scalar, a mutable-`main` byte
  source, a second audit digest alias, or disagreement with the audit member of the ordered
  seven-protocol inventory.
  Preserve Evaluation's separate `audit_sampling_protocol_sha256`,
  `audit_commit_reveal_protocol_sha256`, and `audit_adjudication_protocol_sha256` bindings unchanged;
  the singular aggregate field neither replaces nor derives those granular bindings.
- [ ] Import and class-bound revalidate Evaluation-owned `ProtocolReviewStatementV1`, the three
  mode-discriminated signature-evidence variants, `VerifiedProtocolAttestationV1`, and
  `ProtocolAttestationBundleV1`; Runtime must not define a shadow class. A statement contains exactly
  the approved identity/T0/C0/workflow/subjects/time fields and `statement_sha256`, and contains no
  reviewer-commit OID, signature evidence, envelope/bundle/T1 digest, or future placeholder. Its
  digest is `SHA256(UTF8("laconian-protocol-review-statement-v1\n") || CanonicalJSONV1(statement
  without exactly statement_sha256))`; `subject_root` uses the exact ordered subjects array and
  `laconian-protocol-review-subjects-root-v1\n`.
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
  `publication_branch_ruleset_policy_sha256`, `identity_registry_bundle_sha256`,
  `state_writer_git_identity_sha256`, `broker_token_delivery_isolation_policy_sha256`,
  `broker_signing_keys_root_sha256`, `tag_operator_registry_sha256`, `tag_ruleset_policy_root`, and
  `invalid_event_dismissal_policy_sha256`. Every subject is exactly `{kind, sha256}`; unknown,
  duplicate, cross-role, reordered, common-root-as-subject, or identity-mismatched data fails.
- [ ] Import `ProtocolSubjectKindV1` and `PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1` from
  `laconian_eval.benchmark` and assert object identity with
  `laconian_eval.benchmark.protocol_review`; derive statement validation from that immutable mapping,
  not the prose list above or a Runtime tuple. Likewise import `CanonicalJSONV1Error`,
  `canonical_json_v1`, and `parse_canonical_json_v1` from `laconian_eval.benchmark`, assert object
  identity with `laconian_eval.benchmark.attachments`, and route every Runtime wire preimage/parser
  through those exact objects. `tests/test_public_contract.py` rejects a copied Literal/mapping,
  wrapper encoder/parser, local re-export, or use of the internal NUL-domain digest helper.
- [ ] A `VerifiedProtocolAttestationV1` is exactly
  `{schema_version,statement,signature_evidence,attestation_sha256}` and is created only after its
  reviewer commit. Each evidence variant has exactly `schema_version`, `verification_mode`,
  `commit_oid`, `commit_object_sha256`, `parent_commit_oid`, `statement_path`,
  `github_rest_verification`, and `github_graphql_signature`; SSH/OpenPGP additionally and only have
  `fingerprint`, `keyring_sha256`, and `local_signature_verification`. Freeze exact
  `GitHubCommitVerificationProjectionV1` REST fields including repository/commit/API/endpoint,
  `verified=true`, `reason=valid`, payload, signature, `verified_at`, and self digest; freeze exact
  `GitHubSignatureProjectionV1` GraphQL fields including repository/commit/query digest, numeric
  signer/login, `is_valid=true`, `state=VALID`, and self digest. REST payload/signature byte-match the
  raw signed commit; GraphQL signer byte-matches the registry. Keyed modes additionally reconstruct
  and locally verify the embedded signature against only the frozen keyring and exact fingerprint.
- [ ] Keep variable GitHub transport evidence only in strict
  `GitHubSignatureObservationReceiptV1` records with repository/commit/projection roots,
  `observed_at`, request IDs, ETags, raw/canonical response hashes, TLS endpoint identity, and exact
  self digest. Transport receipts are excluded from statements, envelopes, B0, tag binding,
  campaign registry/ID, seed, and plans; two observations with different timestamps/request IDs/
  ETags must reproduce byte-identical stable projections and campaign identity. Tests state the
  trust boundary explicitly: offline replay verifies archived bytes/projections and keyed signatures
  but cannot independently authenticate GitHub as the origin of `github_verified_commit` evidence.
- [ ] Use Evaluation's raw-object/DAG verifier to verify the exact noncyclic Git topology
  `T0 -> C0 -> Rstat -> Rjudge -> Rsecurity -> B0 <- T1`. T0/T1 are unsigned annotated tags with
  deterministic paired refs. Rstat/Rjudge/Rsecurity each have one exact parent and add only their
  role's fixed statement path; B0 has one parent and adds only three fixed envelope paths plus
  `bundle.json`. C0/T0/input package contain no protocol-review subtree or future value; B0 contains
  no B0/T1 self-reference. Verify exact tree deltas and every raw object with both SHA-1 OID and
  `GitObjectSHA256V1 = SHA256(type SP decimal-size NUL content)`.
- [ ] Exercise Evaluation's closed raw tag/commit grammar: exact ordered headers, one blank line, exact canonical
  tag message plus LF, frozen tagger/reviewer/builder identity, whole-second epoch, literal `+0000`,
  and exact messages. T0 message contains exactly `schema_version,input_tag_ref,companion_tag_ref,
  peeled_c0_oid,protocol_reviewer_registry_sha256,tag_operator_registry_sha256,
  tag_ruleset_policy_root,workflow_root`; T1 contains exactly
  `schema_version,input_tag_ref,input_tag_oid,input_tag_object_sha256,companion_tag_ref,
  bundle_commit_oid,bundle_commit_object_sha256,protocol_attestation_bundle_sha256,
  protocol_attestations_root,tag_operator_registry_sha256,tag_ruleset_policy_root`. Reviewer commits
  contain only tree/one parent/frozen author+committer/one mode-compatible `gpgsig` and exact
  `laconian protocol review <T0> <role>: <statement_sha256>\n`; B0 contains only tree/one parent/
  frozen builder author+committer and exact bundle message, with no signature. Reject lightweight or tag-of-tag refs, a fifth/duplicate/unknown header,
  embedded tag signature, multiple commit signatures, `encoding`, `mergetag`, CR/NUL/non-NFC,
  alternate timezone/message/config identity, second parent, executable/symlink/submodule mode, or
  extra/missing/renamed tree entry. Golden fixtures pin the full raw bytes, both hashes, parents,
  paths, and deltas for T0, C0, all R*, B0, and T1.
- [ ] Use Evaluation's exact `ProtocolAttestationBundleV1` builder for the three complete envelopes
  in role order and exact `ProtocolAttestationTagBindingV1` builder only after T1 exists. The binding records T0/C0, three
  reviewer commits, B0/T1, bundle/root, workflow/operator/ruleset roots, and canonical complete
  object-closure inventory; it is first persisted only in preflight/authority and copied downstream
  only through the sealed campaign registry.
- [ ] Use Evaluation-owned exact `TagOperatorRegistryV1`, the two-entry stable-semantic-order
  `TagRulesetPolicyV1`, fresh `TagRulesetObservationReceiptV1`, and one unique historical
  `TagCreationRuleSuiteReceiptV1` for each tag. The creation-authorizer ruleset contains only creation
  plus the sole frozen `User/always` operator bypass; the disjoint immutability ruleset contains
  update then deletion and no bypass actors. Map raw rule-suite `result` to `overall_result`, preserve
  `evaluation_result`, map actor ID/name, and allowlist only rule source type/ID, enforcement, result,
  and rule type. T0/T1 creation must be `overall_result=bypass`, `evaluation_result=fail`, all-zero
  before OID, exact tag-object after OID, and two distinct nonreplayed suite IDs; update/delete bypass,
  delete/recreate, wrong actor, namespace squat, ambiguous suite, or extra applicable ruleset fails.
  The stable policy root uses exactly `laconian-tag-ruleset-policy-v2\n`; observation and creation
  receipts use their exact v1 newline domains and omit only their named self fields. Current policy
  receipts and historical creation receipts remain outside campaign identity.
- [ ] Call Evaluation's exact `ProtocolReviewObjectArchiveV1` builder/importer over Runtime-captured
  safe bytes: ordered raw Git objects; lexicographically ordered
  safe raw/canonical API blobs; and ordered `ArchivedApiReceiptBindingV1` wrappers for GitHub
  signatures, ruleset observations, T0 creation, and T1 creation. Enforce one-to-one indexed
  receipt-hash-to-blob-path linkage, exact receipt discriminator/self digest, no orphan/duplicate/
  aliased/missing blob, and no headers/cookies/authorization/query secret in raw bytes. Its
  network-free importer reconstructs all object headers/hashes/trees/deltas and all receipt/projection
  hashes before accepting the archive. `object_closure_root` hashes only ordered
  `{oid,type,size,git_object_sha256}` projections under
  `laconian-protocol-review-object-closure-v1\n`; the outer archive digest hashes the complete archive
  without exactly its self field under `laconian-protocol-review-object-archive-v1\n`. The already
  computed closure root is an ordinary outer field, so neither preimage is circular.
- [ ] Because the approved prose tables are not an algorithmic extraction format, manually
  transcribe and review the canonical schema fixture at
  `tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.json` in the RED fixture
  commit. After that commit is independently reviewed, compute its digest with the platform
  `shasum` implementation and apply the exact printed 64-hex value to the separate checked-in
  `campaign-state-schema.canonical.sha256` sidecar as exactly
  `<lowercase-64-hex><two spaces>campaign-state-schema.canonical.json<LF>`. The test parses that
  closed grammar and independently hashes the JSON bytes; no Python/production generator writes or
  updates either fixture. Require the synthetic input-package member
  `tests/fixtures/public-benchmark-input-v1/benchmark/security/campaign-state-schema.json` to be a
  byte-identical copy of that owner fixture and bind the same digest as the
  `campaign_state_schema_sha256` subject. Task 3's generator must later equal those literal bytes;
  the live input tag remains owned by the roadmap freeze.

  Freeze/review the literal first, then run this independent command, which imports no production
  module. Only after a reviewer compares the output with the frozen bytes may the exact output line
  be added to the sidecar by `apply_patch` and the fixture test committed:

  ```bash
  git add tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.json
  git commit -m "test: freeze reviewed campaign state schema fixture"
  shasum -a 256 tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.json
  git add tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.sha256 \
    tests/campaign/test_state_schema_fixture.py \
    tests/fixtures/public-benchmark-input-v1/benchmark/security/campaign-state-schema.json
  git commit -m "test: bind reviewed campaign state schema digest"
  uv run pytest -p no:cacheprovider tests/campaign/test_state_schema_fixture.py -q
  ```

  Expected before the sidecar/copy commit: the fixture test fails only because the reviewed digest
  sidecar/copy is absent. Expected after applying exactly the reviewed `shasum` output: PASS, with
  the sidecar digest equal to an independent `hashlib.sha256` calculation and the package member
  byte-equal to the owner literal. No sentinel, unknown hash, self-blessing generator, or
  amend/regeneration of the reviewed fixture commit exists.
- [ ] Depend on Evaluation's table-driven golden preimage tests for operator/ruleset/workflow/
  statements/projections/receipts/local verification/envelopes/bundle/binding/archive, then add
  Runtime integration tests proving only `CampaignRegistryPayloadV1`, `CampaignRegistryV1`,
  dismissal/main-fallback/state records are Runtime-owned. Runtime must call the exact neutral
  newline-domain helpers and reject a circular preimage, wrong domain, omitted ordinary field,
  included self field, ambient transport field, or schema object whose `__module__`/identity differs.
- [ ] Add independent canonical vectors for the delivery-isolation policy, each of the three signing
  keys, every leaf/node/root preimage (including literal `N22=node(L2,L2)`), and each campaign-bound
  signing identity. Build expected bytes and SHA-256 values without production helpers; reject a
  promoted odd leaf, sentinel leaf, reordered role, caller-supplied root, padded base64url, non-
  Ed25519 SPKI, expired/not-yet-valid key, duplicate key ID, wrong campaign registry, or any extra/
  omitted field. Run the focused owner test before preflight:

  ```bash
  uv run pytest -p no:cacheprovider tests/campaign/test_broker_wire.py -q
  ```

  Expected RED: the shared broker-wire module and fixed-three-key root verifier are absent.
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
  record fails. The later fixed `security_attestor` job obtains fresh evidence only through its
  downscoped external-broker capability with ordered permissions `administration:write`,
  `contents:read`, `metadata:read` and a GET-only endpoint policy.
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
- [ ] Build `VerifiedCampaignInputPackageV1`, then bind the complete verified input package into
  `CampaignPreflightSealV1`, the `PREFLIGHT_SEALED` evidence, and authority genesis. Those typed
  records, not `CampaignRegistryV1`, retain and revalidate the operational preflight material:

```text
mode, input tag object and peeled commit,
current preflight workflow path/SHA-256, exact 15-workflow inventory/root, three manifest/parent-plan hashes,
literal `uv.lock` path and `uv_lock_sha256`,
ordered 36 shard hashes, exact tagged `src/laconian_eval/benchmark/hard_score.py` source SHA-256,
hard-score/judge/statistical protocol path/hash fields and the Evaluation-owned singular
`audit_protocol_sha256: Sha256`,
the plaintext `CampaignSeedV1` and its hash, `CampaignPlanIndexV1` hash,
all seven ordered protocol hashes, five-dimension price snapshot/source roots, the exact two audit-reviewer account/signing
bindings and audit-reviewer-registry hash, the exact three role-bound protocol-reviewer bindings and
protocol-reviewer-registry hash,
the complete `ProtocolAttestationTagBindingV1`, all three verified envelopes/root and bundle hash,
tag-operator, stable tag-ruleset, and publication-branch-ruleset roots, invalid-event-dismissal and
main-fallback-liveness roots, exact broker-token-delivery-isolation policy, ordered three broker
signing keys and their recomputed root,
the exact `StateWriterGitIdentityV1` and `CampaignStateSchemaV1` member hashes,
the repository trust-boundary attestation/signature hashes and ordered settings-record root,
planned initial calls, planned maximum attempts,
requested service-tier root (every generation/judge request exactly `default`), explicit/30m cache-policy root and recursive no-breakpoint proof, projected reserved
micro-USD, and cap micro-USD
```

  `VerifiedCampaignInputPackageV1` contains only the C0-derived members of that list and its own
  package digest. `CampaignPreflightSealV1`/`PREFLIGHT_SEALED` evidence adds the post-C0 verified
  envelopes, complete companion binding, exact registry, receipts needed for live admission, and
  the separately typed plan/budget evidence before authority genesis copies the complete seal.

- [ ] Define `CampaignRegistryPayloadV1` with exactly these fields, in canonical schema order, and
  no mode, seed, plan, audit-protocol, price, trust-boundary, state-writer, state-schema, workflow-
  inventory object, receipt, or transport-metadata field:

  ```text
  campaign_input_package_sha256
  audit_reviewer_registry_sha256
  protocol_reviewer_registry_sha256
  workflow_root
  protocol_attestation_tag_binding
  tag_operator_registry_sha256
  tag_ruleset_policy_root
  publication_branch_ruleset_policy_sha256
  invalid_event_dismissal_policy_sha256
  main_fallback_liveness_policy_sha256
  broker_token_delivery_isolation_policy_sha256
  broker_signing_keys
  broker_signing_keys_root_sha256
  protocol_attestations_root
  protocol_attestation_bundle_sha256
  ```

  `protocol_attestation_tag_binding` is the complete strict
  `ProtocolAttestationTagBindingV1`. Define `CampaignRegistryV1` with exactly
  `schema_version`, `campaign_id`, `payload`, and `campaign_registry_sha256`. The registry digest is
  `SHA256(UTF8("laconian-campaign-registry-v1\n") || CanonicalJSONV1(payload))`; `campaign_id` is
  exactly `benchmark-` plus its first 32 lowercase hex characters. Observation/signature/ruleset/
  creation receipts and archive transport metadata are not payload fields. The key array contains
  exactly the three C0 keys in publisher/release-finalizer/security-attestor order and reproduces the
  fixed-three-leaf duplicate-last Merkle/root construction; the delivery-isolation policy and branch
  ruleset policy are byte-copied from their verified C0 members. Full seed, plans, audit
  protocol, workflow inventory, and the rest of the preflight list remain separately typed in the
  verified input package, preflight seal/evidence, authority genesis, and downstream records; their
  registry binding is indirect through `campaign_input_package_sha256` except for the payload fields
  explicitly listed above.

Derive the hard-scorer source hash by descriptor-reading that one path from verified `C0`; derive
the hard-score protocol hash and `audit_protocol_sha256` from their exact members of the seven-file
tagged protocol inventory. Neither is accepted as a manifest/CLI/workflow scalar. Re-hash both
protocol members during verified-input-package load, bind their paths and hashes into the typed
preflight seal and authority genesis, and reject a self-consistent substituted package whose digest
does not equal `CampaignRegistryPayloadV1.campaign_input_package_sha256`.

- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_preflight.py -q
```

Expected RED: registry models and `seal_preflight` are absent.

#### Step 5: Implement the minimal tagged package and deterministic preflight

- [ ] Implement a strict `load_campaign_input_package(tag_root: Path) -> VerifiedCampaignInputPackageV1`
  that opens only the fixed paths above, rejects symlinks/aliases/duplicates/unknown members, and
  proves every path and digest is reachable from the exact peeled input commit. Workflow inputs may
  select only the immutable tag; they may not override seed, reviewer, price, model, or protocol.
- [ ] Construct the exact stable `CampaignRegistryPayloadV1`, compute
  `campaign_registry_sha256 = SHA256(UTF8("laconian-campaign-registry-v1\n") ||
  CanonicalJSONV1(payload))`, and derive `campaign_id = "benchmark-" +
  campaign_registry_sha256[:32]`. Re-run preflight with different observation times/request IDs/
  ETags/API response order and require byte-identical payload, registry digest, campaign ID,
  authority-ref name, seed-derived order, and plans. Mutating any T0/C0/R*/B0/T1 object, stable
  projection, signature, bundle, operator/policy root, or C0 input instead creates a different
  registry; no transport receipt may do so.
- [ ] Materialize and validate every parent plan and `ShardPlanV1` through Slice 1 APIs; never reconstruct plan IDs in campaign code.
- [ ] Construct and revalidate `CampaignPlanIndexV1` from the tagged plaintext seed and verified
  shard plans. Store the full `CampaignSeedV1` in `VerifiedCampaignInputPackageV1`, bind it into the
  typed preflight seal/evidence and authority genesis, and copy it only into separately typed
  downstream consumers that require bootstrap, judge blinding, shard ordering, or audit sampling.
  `CampaignRegistryV1` contains neither the seed nor its direct fields.
- [ ] Bind the one `campaign_registry_sha256` and complete companion-tag binding in
  `PREFLIGHT_SEALED`, authority genesis, every event/mutation/request/receipt, `BatchPlanV1`,
  generation context/expectation, provider/audit/analysis handoff, and collector/publication/release
  interfaces. Reject a component copied from another internally valid tag pair before any plan,
  credential, provider call, artifact read, or mutation.
- [ ] Import and class-bound revalidate Foundations-owned `ResolvedPriceSnapshotV1`; implement only
  the strict integer-micro-USD projection and pure `token_charge_usd_micros` /
  `project_worst_case_exposure` functions in `spend.py`. Preserve the exact five Foundation field
  names and source evidence without redeclaration. Each token component rounds up independently;
  all ledger inputs and outputs are strict nonnegative integers.
- [ ] Calculate worst-case request exposure through those pure functions and enforce exactly `5_000_000` pilot or `75_000_000` confirmatory micro-USD.
- [ ] Emit a canonical `PreflightSummaryV1` that contains counts, price URLs, reservations, and hashes but no prompts, outputs, credentials, arbitrary paths, or environment values.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/benchmark/test_protocol_review.py tests/campaign/test_tag_binding.py tests/campaign/test_input_package.py tests/campaign/test_preflight.py tests/campaign/test_broker_wire.py tests/campaign/test_spend.py tests/campaign/test_trust_boundary.py tests/campaign/test_state_schema_fixture.py tests/test_public_contract.py -q
```

Expected GREEN: PASS; the verified input package, typed preflight seal/evidence, authority genesis,
and separately typed consumers carry the single C0-derived `audit_protocol_sha256` together with
all unchanged granular audit bindings, while the exact four-field registry binds them only through
its exact payload.

#### Step 6: Commit

- [ ] Commit the tag and preflight slice:

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/tag_binding.py \
  src/laconian_eval/campaign/preflight.py \
  src/laconian_eval/campaign/broker_wire.py \
  src/laconian_eval/campaign/spend.py \
  tools/benchmark_capture_trust_boundary.py \
  tests/campaign/test_tag_binding.py \
  tests/campaign/test_input_package.py \
  tests/campaign/test_preflight.py \
  tests/campaign/test_broker_wire.py \
  tests/campaign/test_spend.py \
  tests/campaign/test_trust_boundary.py \
  tests/campaign/test_state_schema_fixture.py \
  tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.json \
  tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.sha256 \
  tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-sol.yaml \
  tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-terra.yaml \
  tests/fixtures/public-benchmark-input-v1/evals/manifests/public-benchmark-gpt-5.6-luna.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/campaign-seed.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/price-snapshot.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/reviewers.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/protocol-reviewers.yaml \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary.json \
  tests/fixtures/public-benchmark-input-v1/benchmarks/campaigns/public-three-model-v1/repository-trust-boundary-signature.json \
  tests/fixtures/public-benchmark-input-v1/benchmark/security/tag-operator-registry.json \
  tests/fixtures/public-benchmark-input-v1/benchmark/security/tag-ruleset-policy.json \
  tests/fixtures/public-benchmark-input-v1/benchmark/security/invalid-event-dismissal-policy.json \
  tests/fixtures/public-benchmark-input-v1/benchmark/security/main-fallback-liveness-policy.json \
  tests/fixtures/public-benchmark-input-v1/benchmark/security/protocol-bundle-builder-git-identity.json \
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
- Create: `src/laconian_eval/campaign/publication_wire.py`
- Create: `src/laconian_eval/campaign/release_wire.py`
- Create: `tools/benchmark_state_broker_client.py`
- Create: `tests/campaign/test_state_schema.py`
- Create: `tests/campaign/test_state.py`
- Create: `tests/campaign/test_state_broker.py`
- Create: `tests/campaign/test_authority_git.py`
- Create: `tests/campaign/test_authority.py`
- Create: `tests/campaign/test_publication_wire.py`
- Create: `tests/campaign/test_release_wire.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

#### Step 1: RED-test the sole canonical state schema

- [ ] Treat
  `tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.json` as the sole
  checked-in literal fixture owned by `tests/campaign/test_state_schema_fixture.py`. It is manually
  transcribed from the exact approved Section 7.4 tables because the prose/table rendering is not an
  algorithmically complete extraction source. After the RED fixture commit is independently
  reviewed, use the separately reviewed
  `tests/fixtures/campaign-state-schema-v1/campaign-state-schema.canonical.sha256` sidecar created in
  Task 2; this plan contains no guessed digest or sentinel. The test independently canonicalizes and
  hashes the literal bytes, requires the closed sidecar line to match, checks every reviewed
  state/event/parent/bundle/evidence/terminality/caller/ref
  row, and byte-compares the synthetic input-package copy without importing `campaign.state_schema`
  or any production generator.
- [ ] Define one versioned canonical `CampaignStateSchemaV1` production projection and generate the state-name,
  event-name, parent/bundle/evidence-discriminator, terminality, caller/ref, and reachability/liveness
  projections from it. Require its canonical bytes to equal the independently reviewed literal
  fixture before using its digest. Test that production `state.py` and broker policy round-trip to
  the same schema digest. A hand-written second production transition list, table-only edge,
  broker-only edge, unknown enum, unreachable event, or nonterminal state without an authorized
  success/invalidation/STOP/correction continuation fails.
- [ ] Canonicalize schema, event, state, hold, request, and receipt records as RFC 8785 JSON, UTF-8
  without terminal newline, UTC RFC 3339 timestamps, canonical JSON integers, lowercase SHA-256
  roots, and 40-lowercase-hex Git SHA-1 OIDs. Reject missing/extra/null-where-forbidden fields,
  duplicate/reordered schema arrays, floats, bool-as-int, or a digest that omits any field except its
  own final digest.
- [ ] RED verification command:

  ```bash
  uv run pytest -p no:cacheprovider tests/campaign/test_state_schema_fixture.py -q
  ```

  Expected RED: until the manually transcribed literal, its independently reviewed post-commit
  SHA-256 sidecar, and the byte-identical synthetic input-package copy are all checked in;
  production output cannot update or bless any expected byte or digest.
- [ ] Generate canonical schema bytes and require byte equality plus digest equality with both the
  literal owner fixture and Task 2's synthetic `benchmark/security/campaign-state-schema.json`
  member and its `security_evidence` subject. Any drift requires a new normative amendment and
  reapproval; a test cannot update its expected digest from production output.
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
  the same-state `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` root transition and every phase-exact
  containment terminal consumer,
  `RELEASE_BLOCKED + CORRECTION_RESULT_RELEASED -> RELEASED`, and
  `RELEASED + CORRECTION_RESULT_RELEASED -> RELEASED`. Assert invalid-prefix publication uses only
  `INVALID_PUBLICATION_PR_OPEN` and ends only in `INVALID_PREFIX_MERGED` or
  `INVALID_PREFIX_MERGED_INVALID`.

- [ ] Cover every illegal source/event pair, a STOP-to-live jump, partial-to-complete jump, release-blocked continuation, duplicate event, skipped parent, wrong phase-plan, wrong spend hash, wrong inventory root, and unresolved hold.
- [ ] `CORRECTION_RESULT_RELEASED` is the sole release-blocked escape: require the exact next
  `correction_attempt`; predecessor correction record/root; prior pointer digest; new pointer digest;
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
  Slice 4 owns the nested exact `ReleaseExternalObjectsInventoryV1` construction/re-fetch and its
  `current_external_objects_root_sha256`. A post-call failure may not use the preflight-empty form,
  and no later event can erase or relabel an observed orphan object.
- [ ] Assert each event is single-use, parent-bound, canonical, and carries an exact source workflow/actor or reviewer identity.
- [ ] Freeze `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` as the only event that may change publication
  containment roots. Its exact event contains the full ordered containment publication identity,
  literal event type, positive parent transition, nested exact
  `PublicationTerminalContainmentIntentV1` plus its digest, predecessor denylist root, nested exact
  successor `PublicationMergeDenylistV1` plus its root, `publisher_broker_phase="terminalizing"`,
  nested signed `PublisherBrokerPhaseLedgerPrefixV1(prefix_purpose="containment_start")` and
  `BrokerVaultAuditPrefixV1(prefix_purpose="containment_start")` plus both roots, all three zero
  outstanding/live counts, `constructive_mint_disabled=true`, source workflow
  `benchmark-publish.yml`, source job `publication_terminalizer`, frozen source-workflow SHA,
  `source_ref_class="protected_current_main"`, `occurred_at`, and event digest. The prefix pair must
  byte-match identity/purpose, paired-ledger root/count/time, recompute zero open request/dispatch/
  token counts, and precede the accepted mutation receipt. Reject a free source job, caller-provided
  zero count, plan-bound-main-only row, start with nonnull hold, start with incomplete active exposure,
  a second active containment, or any ordinary event that changes either publication root.
- [ ] For `GENERATION_SET_SEALED`, require exactly the ordered 36 capsule hashes,
  `generation_context_expectation_sha256`, and `verified_generation_context_root`. Neither root may
  be omitted, reconstructed later, or replaced by a serialized raw context.
- [ ] GREEN verification command:

  ```bash
  uv run pytest -p no:cacheprovider tests/campaign/test_state_schema_fixture.py tests/campaign/test_state_schema.py tests/campaign/test_state.py -q
  ```

  Expected GREEN: PASS; production-generated canonical bytes, both checked-in fixture copies, the
  independently frozen SHA-256 literal, and every exact reviewed schema row agree byte-for-byte.
- [ ] Generate the ordinary `PERMANENT_STOP` caller/parent/reason rows from the schema exactly:
  batch from `PREFLIGHTED|GENERATION_RESUMABLE|GENERATION_ACTIVE|HARD_SCORE_COMPLETE|JUDGE_RESUMABLE|JUDGE_ACTIVE`
  for provider/reservation/delivery/identity/ledger/security evidence; hard-score from
  `GENERATION_COMPLETE` for generation-context/hard-score integrity; evidence from `JUDGE_COMPLETE`
  for coverage/provider-evidence failure; audit from `PROVIDER_EVIDENCE_VERIFIED` for identity/
  nonparticipation/reveal/adjudication protocol failure; analysis from `AUDIT_COMPLETE` for
  statistical/provenance/integrity failure; complete collection from `ANALYSIS_COMPLETE` for bundle
  coverage/lineage failure; publish from `BUNDLE_COLLECTED|COMPLETE_PUBLICATION_PR_OPEN` for exactly
  `publication_lineage_failure|publication_reconciliation_unavailable`, with the unavailable form
  binding its sealed disposition set/receipt and the open-PR row requiring its exact publisher close
  receipt; and dismiss-hold only for one of those
  same parent/reason rows plus its exact nondismissible hold. There is no `any nonterminal` wildcard.
- [ ] Generate the exact `credential_exposure` caller/parent matrix from the schema. Require
  `CredentialExposureIncidentEvidenceV1`, safe metadata only, and the exact current authority,
  state, ledger, artifact-inventory, active-plan, hold, denylist, and containment roots. Freeze these
  rows without category expansion:

  | Caller | Exact allowed current parents | Additional restriction |
  |---|---|---|
  | `benchmark-batch.yml` | `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE` | affected artifact belongs to the exact current batch plan/run |
  | `benchmark-hard-score.yml` | `GENERATION_COMPLETE` | affected generation artifact is an exact hard-score input or scan output |
  | `benchmark-evidence.yml` | `GENERATION_RESUMABLE`, `GENERATION_ACTIVE`, `GENERATION_COMPLETE`, `HARD_SCORE_COMPLETE`, `JUDGE_RESUMABLE`, `JUDGE_ACTIVE`, `JUDGE_COMPLETE`, `PROVIDER_EVIDENCE_VERIFIED`, `AUDIT_COMPLETE`, `ANALYSIS_COMPLETE`, or `BUNDLE_COLLECTED` without an active initial-publication prefix | designated cross-phase inventory/scanner and exact inventoried artifact/phase plan |
  | `benchmark-evidence.yml` | `STOPPED_INVALID`, `BUDGET_INCOMPLETE`, `INVALID_FINALIZED` without an active initial-publication prefix, `INVALID_PREFIX_MERGED`, or `INVALID_PREFIX_MERGED_INVALID` | pending/effects then only strict terminal supplement; state remains invalid and cannot resume |
  | `benchmark-audit.yml` | `PROVIDER_EVIDENCE_VERIFIED` | affected artifact is an exact audit input/output |
  | `benchmark-analysis.yml` | `AUDIT_COMPLETE` | affected artifact is an exact analysis input/output |
  | `benchmark-collect-complete.yml` | `ANALYSIS_COMPLETE` | affected artifact is an exact collection input or proposed bundle member |
  | `benchmark-publish.yml` | `BUNDLE_COLLECTED` with an active complete prefix, `COMPLETE_PUBLICATION_PR_OPEN`, `INVALID_FINALIZED` with an active invalid prefix, `INVALID_PUBLICATION_PR_OPEN`, bare `RELEASE_BLOCKED`, bare `RELEASED`, or an active correction before valid merge | exact publication/correction artifact; no-PR/close-or-merge race, invalid supplement, bare-state correction start, or publication-family invalidation only |
  | `benchmark-release.yml` | `RESULT_MERGED` before or after initial release intent, or an active correction after valid merge | exact release-plan/correction artifact or release object; release-plan or release-family correction invalidation only |
  | `benchmark-dismiss-hold.yml` | every premerge credential-exposure STOP parent except `COMPLETE_PUBLICATION_PR_OPEN` and `BUNDLE_COLLECTED` with an active initial-publication prefix | exact current nondismissible hold and independently verified incident; no postmerge, correction, or supplement row |

  Every row grants exactly `CREDENTIAL_EXPOSURE_PENDING`, zero or more next-ordinal
  `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` events, and its one phase-exact terminal consumer. Premerge
  direct rows end only in `PERMANENT_STOP(reason=credential_exposure)`; invalid terminal rows end in
  the strict supplement; postmerge and correction rows end only in the listed release/correction
  invalidation or correction intent. Complete/invalid publication prefixes require exact
  no-PR/close/merge-race partitioning. Exhaustively test the full caller × parent × event × ref
  Cartesian product, every excluded `PREFLIGHTED`/prefix/terminal cell, and that containment already
  started forbids a new pending/progress CAS.
- [ ] Replace every open-ended STOP or generic security branch with the approved closed 24-value
  `PermanentStopReasonV1` and its strict reason-discriminated evidence union. Generate one exhaustive
  caller × current-parent × trigger-ref × reason × evidence row set from
  `CampaignStateSchemaV1`; no `any nonterminal`, role/team/maintainer wildcard, reason alias, mixed
  variant, broker-only edge, or table-only edge exists. Assert every reachable nonterminal state has
  an allowed success, invalidation, STOP, correction, dismissal, exposure-progress, or safe-invalid
  continuation.

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

  The first 22 values use exact reason-discriminated `OrdinaryStopEvidenceV1`: schema/campaign,
  reason, parent state/authority, current state/ledger/inventory/plan/hold roots,
  `source_records_root`, strict `detail`, time, and self digest under
  `laconian-ordinary-stop-evidence-v1\n`. Freeze the literal reason-to-detail field map from Section
  7.4; fields from another variant, a shared optional bag, empty/duplicate/reordered source records,
  or a supplied root are invalid. `credential_exposure` and `protocol_authority_drift` use only their
  separate exact evidence schemas.
- [ ] Define `InvalidEventNondismissibilityEvidenceV1` with exactly
  `schema_version,campaign_id,campaign_registry_sha256,parent_state,parent_authority_oid,hold_id,
  hold_sha256,rejected_request_sha256,failed_validation,source_records_root,observed_at,
  nondismissibility_evidence_sha256` under
  `laconian-invalid-event-nondismissibility-evidence-v1\n`; its nonempty validation array and source
  root reproduce the accepted current hold. Define `HeldResultMergedConsumptionV1` with exactly
  `schema_version,kind="nondismissible",campaign_id,campaign_registry_sha256,
  parent_state="RESULT_MERGED",parent_authority_oid,hold_id,hold_root_sha256,
  hold_admission_event_sha256,nondismissibility_evidence_sha256,consumption_sha256` under
  `laconian-held-result-merged-consumption-v1\n`. The release-plan invalidation embeds this exact
  consumption, clears the current hold atomically, and cannot name a future event/successor. Golden
  vectors reject a stale/rebound hold, mismatched rejection/validation set, opaque nondismissibility
  root, half-consumption, or use at any other parent.
- [ ] Add exact `ProtocolAuthorityDriftEvidenceV1` and the literal premerge drift STOP matrix for
  moved/deleted/substituted T0/T1, changed raw object, stable policy mismatch, registry mismatch, or
  fresh double-read failure that proves drift. The evidence binds campaign registry, both sealed and
  current ref/object/policy observations, caller/current parent/ref, optional consumed hold, and an
  exact complete-publication-PR close receipt only at that parent. Drift STOP never restores live
  authority; after merge use only release invalidation/correction. Every eligible state remains
  reachable through the protected-main `benchmark-evidence.yml` fallback when T0 is missing or moved.
  Its fields are exactly schema/campaign/registry, parent state/authority/hold, tag-binding root,
  nullable observed T0/T1 OIDs, observed ruleset root, nonempty ordered failed predicates, verification
  receipts root, nullable exact PR-close receipt, time, and self digest under
  `laconian-protocol-authority-drift-evidence-v1\n`. The predicate vocabulary is exactly
  `input_ref_moved|input_ref_deleted|companion_ref_moved|companion_ref_deleted|object_oid_mismatch|
  raw_object_sha256_mismatch|closure_mismatch|ruleset_drift|tag_creator_mismatch|
  creation_authorization_mismatch|signature_identity_mismatch|topology_mismatch|cross_campaign_replay`.
  Freeze the local rows exactly as: batch at `PREFLIGHTED|GENERATION_RESUMABLE|GENERATION_ACTIVE|
  HARD_SCORE_COMPLETE|JUDGE_RESUMABLE|JUDGE_ACTIVE` on T0; hard-score at
  `GENERATION_COMPLETE` on T0; evidence at `JUDGE_COMPLETE` on T0; audit at
  `PROVIDER_EVIDENCE_VERIFIED`, analysis at `AUDIT_COMPLETE`, collection at `ANALYSIS_COMPLETE`, and
  publish at `BUNDLE_COLLECTED|COMPLETE_PUBLICATION_PR_OPEN`, all on exact plan-bound main. Duplicate
  those 13 parents exactly once for protected-current-main `benchmark-evidence.yml` fallback; only the
  open-PR row requires/permits the exact close receipt. No other caller/parent/ref cell exists.
- [ ] Add constructive `CREDENTIAL_EXPOSURE_PENDING` and
  `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` self-loop events. Pending atomically writes the exact
  `CredentialExposurePendingV1` and `denylist/provisional/<incident-id>.json`, advances transition,
  initializes the calculated `CredentialExposureProgressRootV1`, and sets both
  `active_credential_exposure_incident_id` and `active_credential_exposure_pending_root` in the same
  successor. Pending has exactly campaign/
  incident, parent/current state and authority, ledger/inventory/plan/hold roots, nullable concurrent-
  drift root, ascending affected artifacts, scanner/provisional-denylist roots, canonical complete
  pending-effect inventory, time, and self digest under
  `laconian-credential-exposure-pending-v1\n`; no suspected bytes enter it. Effect appends exactly the next
  zero-padded ordinal `CredentialExposureEffectReceiptV1`, advances the predecessor-linked effect
  chain/root, and changes no campaign state. Each receipt has exactly campaign/incident/pending and
  predecessor roots, ordinal/kind/external-object/idempotency key, requested/observed terminal state,
  receipt root, time, and self digest. Every progress self-loop preserves the same nonnull active
  incident ID and active pending root while advancing only the incident's predecessor-linked
  progress/effect root. The six-field progress projection has no self field; its empty,
  link, and outer roots use exactly the three normative newline domains and bind campaign, incident,
  originating pending digest, previous active root, ordinal, and receipt digest. The final
  credential-exposure `PERMANENT_STOP` consumes
  the exact completed progress root, writes the permanent denylist, and atomically clears both
  active exposure fields. `CredentialExposureSupplementV1` is the strict `supplement_kind` union of
  `ProtocolDriftCredentialExposureSupplementV1` and
  `InvalidLineageCredentialExposureSupplementV1`, never one nullable bag. The drift variant has
  exactly schema/kind/campaign/incident/pending/final-evidence/original-drift-STOP/consumed-active-
  root/terminal-effect-root/recorded-at/self-digest fields under
  `laconian-protocol-drift-credential-exposure-supplement-v1\n`. The invalid-lineage variant has
  exactly schema/kind/campaign/incident/parent-state/parent-authority/invalid-origin-event and
  evidence roots/pending/final-evidence/consumed-active-root/terminal-effect-root/nullable exact
  invalid-PR-close receipt/recorded-at/self digest under
  `laconian-invalid-lineage-credential-exposure-supplement-v1\n`; its parent-to-origin mapping is
  exactly `STOPPED_INVALID -> PERMANENT_STOP`, `BUDGET_INCOMPLETE -> BUDGET_EXHAUSTED`,
  `INVALID_FINALIZED|INVALID_PUBLICATION_PR_OPEN -> INVALID_PREFIX_SEALED`,
  `INVALID_PREFIX_MERGED -> INVALID_PREFIX_MERGED`, and
  `INVALID_PREFIX_MERGED_INVALID -> INVALID_PREFIX_MERGE_INVALIDATED`. Both consume the exact active
  progress root, clear both fields in one successor, preserve state, and grant no live resume.
  Pending/effect events require `active_publication_terminal_containment_root=null`. Exposure newly
  detected after containment start performs external credential revocation/rotation and pauses the
  same evidence-preserving containment run, but may not install/advance a campaign exposure root or
  rewrite its immutable pre-containment route.
  Cover exposure-before-drift, drift-during-exposure, exposure-after-drift, open-PR
  close, crash after pending and after every effect, idempotent adoption, complete terminal inventory,
  and denial of every ordinary mutation/effect/credential while pending.
- [ ] Define and export the one Runtime-owned terminal consumer used by post-merge Publication
  events; Publication imports the identical object and may not duplicate or flatten it:

  ```python
  class TerminalCredentialExposureConsumptionV1(CapsuleModel):
      schema_version: Literal["TerminalCredentialExposureConsumptionV1"]
      campaign_id: BoundedNonBlankString
      campaign_registry_sha256: Sha256
      incident_id: BoundedNonBlankString
      credential_exposure_pending_sha256: Sha256
      predecessor_active_pending_root: Sha256
      terminal_effect_receipts_root: Sha256
      credential_exposure_incident_evidence: CredentialExposureIncidentEvidenceV1
      concurrent_protocol_authority_drift_evidence_sha256: Sha256 | None
      consumed_unresolved_hold_id: BoundedNonBlankString | None
      consumed_unresolved_hold_root_sha256: Sha256 | None
      consumption_sha256: Sha256
  ```

  Its digest is exactly
  `SHA256(UTF8("laconian-terminal-credential-exposure-consumption-v1\n") ||
  CanonicalJSONV1(record without exactly consumption_sha256))`.
  `build_terminal_credential_exposure_consumption` accepts only reconstructed authority and the
  final strict incident evidence. It requires the same campaign/registry/incident/pending digest,
  recomputes the predecessor progress root and terminal effect chain from every ordinal receipt,
  requires `terminal_effect_receipts_root` to equal that chain, and copies the concurrent drift
  root from the originating pending record. Both hold fields are null when no hold was current;
  otherwise both identify the one hold copied into the pending/final evidence. It accepts no caller
  root, inventory, ID, Boolean, callback, or mutable lookup. Cross-incident, cross-pending,
  cross-campaign, missing/gapped/reordered effect, terminal-chain, drift-root, half-null/wrong-hold,
  and digest-recomputed substitution vectors all fail before a terminal candidate is built.
- [ ] Extend the generated phase-aware exposure matrix. Besides the approved premerge parents,
  pending/effect self-loops are admitted at `RESULT_MERGED`, bare `RELEASE_BLOCKED|RELEASED`, a
  nonterminal correction prefix, and artifact-bearing `STOPPED_INVALID|BUDGET_INCOMPLETE|
  INVALID_FINALIZED|INVALID_PUBLICATION_PR_OPEN|INVALID_PREFIX_MERGED|
  INVALID_PREFIX_MERGED_INVALID`, only for emergency containment and only while the active
  publication-containment root is null. Their only terminal consumers
  are: exposure-race `RESULT_MERGE_INVALIDATED` for an open complete PR that merged; pre- or
  post-intent `RELEASE_PLAN_INVALIDATED` at `RESULT_MERGED`; `CORRECTION_INTENT_AUTHORIZED` for bare
  `RELEASE_BLOCKED|RELEASED`; the matching publication-family correction invalidation before a
  valid correction merge; or correction-release invalidation after its valid merge. Each requires
  `TerminalCredentialExposureConsumptionV1`, clears both active fields and the matching optional
  hold atomically, and preserves/records the contaminated roots. Invalid-lineage parents use the
  exact supplement before ordinary typed invalid-prefix plan invalidation, except a merge-before-
  close race which consumes through `INVALID_PREFIX_MERGE_INVALIDATED`. Metadata/drift/nondismissible
  variants forbid that consumer and require the active pair null. After invalidating an active
  correction, only a new correction ID that explicitly supersedes the terminalized prefix and
  contaminated exposure root may continue. Exercise every prefix and a crash/replay at every
  pending/effect/final-CAS boundary; no prefix can wedge or resume its ordinary next phase.
- [ ] Define the six state-bound containment wire primitives now in Runtime-owned
  `laconian_eval.campaign.publication_wire`: `PublicationMergeDenylistEntryV1`,
  `PublicationMergeDenylistV1`, `PublicationTerminalContainmentPreflightV1`,
  `PublicationPreContainmentTerminalRouteV1`, `PublicationTerminalContainmentIntentV1`, and
  `PublicationTerminalContainmentFinalityV1`. Freeze their exact approved ordered fields,
  nullability, discriminators, LF domains, nested-root equality, and export identities before the
  state schema consumes them. Runtime owns only these six state/start/finality join records plus the
  initial publication receipt/append wire; Publication Task 10 imports them by object identity and
  owns the guard/dequeue/fence/reconciliation algorithm and every other publication evidence type.
  `tests/test_public_contract.py` and `test_publication_wire.py` reject an owner moved into
  `campaign.publication`, an alias, subclass, flattened dict, forward-schema substitute, or second
  digest helper. This direction removes any Runtime→future-Publication implementation dependency.
- [ ] Freeze Runtime's exact containment join rather than duplicating the Publication schemas. The
  shared phrase “full containment publication identity” is expanded in this fixed order whenever
  Runtime compares an owner object: `campaign_id`, `campaign_registry_sha256`, `publication_id`,
  nullable `publication_attempt`, nullable `correction_id`, `bundle_kind`,
  `publication_plan_sha256`, `authorizing_intent_sha256`, `repository_id`, `parent_state`,
  `source_authority_parent_oid`, `authority_phase`, `branch_name`, `expected_base_oid`,
  `expected_head_oid`, `pull_request_marker`, `publication_head_commit_trailer`. Initial publication
  requires positive attempt/null correction; correction requires null attempt/nonempty correction.
  The state/root integration tests independently freeze the owner classes' ordered field tuples,
  exact LF domains, and these joins:

  - denylist genesis is null-predecessor/zero-count/empty, every successor copies all entries and
    appends exactly one, and no campaign event may remove or rewrite an entry;
  - containment preflight has exactly one ordinary/ambiguity source, exact pre-containment protected-
    main/marker/global-queue observations, ascending candidate PRs with a signed observation
    bijection, and the exact merged subset;
  - the pre-containment route's literal route/failure/event/outcome map is reconstructed, with active
    exposure only for complete/correction and an already accepted strict supplement plus null active
    pair for invalid-prefix;
  - intent joins expected source authority/next transition, preflight main OID, predecessor and exact
    one-entry successor denylists, branch-ruleset/workflow roots and the phase-derived premerge/
    merge-won event pair; it contains no accepted receipt or post-CAS evidence;
  - finality accepts only `ordinary_premerge|write_ambiguity_premerge|ordinary_merge_won|
    write_ambiguity_merge_won`, the exact containment-start mutation receipt, matching intent/
    successor denylist/source, a terminal parent distinct from the immutable source parent, direct
    premerge barrier/fenced pair or nested merge-won evidence, sealed publisher disposition set and
    the intent-derived required terminal event.

  Test missing/extra/reordered fields, wrong owner identity, wrong source/finality cross-product,
  self-cycle, source/terminal-parent confusion, nonmonotone denylist, missing zero-residual barrier,
  unpaired signed prefixes, exposure-route substitution, and any digest omitting an ordinary field.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_publication_wire.py tests/campaign/test_state_schema.py tests/campaign/test_state.py -q
```

Expected RED: the canonical schema, generated projection, and transition function are absent.

#### Step 2: GREEN schema-generated pure transition models

- [ ] Implement `CampaignStateSchemaV1` first and generate the discriminated `CampaignEventV1`
  union, `CampaignStateName`, evidence-discriminator checks, transition dispatcher, terminal-state
  checks, and reachability matrix into `state.py`. The generated file carries its source-schema
  digest and fails tests if regenerated bytes differ; no task may edit the generated enum/mapping by
  hand.
- [ ] Define `CampaignStateV1` with the exact Section 7 field tuple, including
  `campaign_registry_sha256`, both exact tag-object bindings, peeled C0/B0 identities, transition/
  parent/event/state roots, phase plan, spend ledger, artifact inventory, correction/publication
  roots, nullable `unresolved_hold_root`, nullable `active_credential_exposure_incident_id`, nullable
  `active_credential_exposure_pending_root`, STOP/incident fields, source identity, nonnull
  `publication_merge_denylist_root_sha256`, nullable
  `active_publication_terminal_containment_root`,
  `state_writer_git_identity_sha256`, and state digest. Null means proven absence, never unchecked;
  freeze the pair invariant
  `(active_credential_exposure_incident_id is null) ==
  (active_credential_exposure_pending_root is null)`. A nonnull incident ID must equal the incident
  identifier embedded in the active `CredentialExposurePendingV1`; its originating pending digest
  and reconstructed `CredentialExposureProgressRootV1` must both recompute from that same incident
  ID. A digest-valid root for another incident is invalid. Every mutation request and broker replay
  binds predecessor and successor values for the hold root, both active exposure fields, both
  publication-containment roots, and the campaign registry. Genesis installs the exact canonical
  empty `PublicationMergeDenylistV1` record/root and null active containment. Every ordinary event
  byte-preserves both roots; containment start alone appends one denylist entry and changes
  `null -> terminal_containment_intent_sha256`; the matching phase-exact consumer alone preserves
  that denylist and changes the same intent root to null.
- [ ] Define exact broker-owned `InvalidEventHoldV1` and its digest. Create a hold only for one
  authenticated, authorized-source, hold-worthy rejection after pre-auth/transient/benign-sibling
  outcomes have been excluded; invalid input cannot be used as an unbounded storage/DoS primitive.
  It contains exactly `schema_version,campaign_id,hold_id,rejected_request_sha256,
  parent_authority_oid,parent_state,parent_transition_number,current_state_root,spend_ledger_root,
  artifact_inventory_root,active_phase_plan_root,source_workflow,source_actor_id,
  source_actor_login,failed_validation,held_at,invalid_event_hold_sha256`, is written only at
  `holds/<hold-id>/hold.json`, and uses the exact `laconian-invalid-event-hold-v1\n` preimage.
- [ ] Implement exact hold admission: pre-auth garbage, temporary reads, wrong repository/run/
  campaign, duplicate accepted request, benign sibling, and stale CAS produce only broker audit denial
  and no campaign transition/hold. Only a request that already passed repository, OIDC/App,
  caller/callee, transport, and sealed-registry checks but then fails event schema, parent, hash,
  required evidence, or literal edge may cause broker-owned `INVALID_EVENT_HELD` by expected-OID
  CAS. The exact `InvalidEventHoldV1` fields/path/digest are frozen; at most one hold exists and a
  racing request is audit-denied without another state transition. Hold admission is generated from
  the full reconstructed authority configuration, not the state name alone: any active initial-
  publication prefix, `COMPLETE_PUBLICATION_PR_OPEN`, any nonnull terminal-containment root, or `RELEASED` or
  `RELEASE_BLOCKED` with any nonterminal correction prefix forbids `INVALID_EVENT_HELD`, because no
  later correction phase is an approved hold consumer. Only bare `RELEASED` may consume a newly
  admitted hold through `CORRECTION_INTENT_AUTHORIZED`; at `RESULT_MERGED`, including after an
  initial release intent/receipt prefix, the only held exit is `RELEASE_PLAN_INVALIDATED`. Exhaustive
  prefix vectors prove every admitted hold has a reachable atomic consumer and no active publication,
  containment, or correction prefix can be wedged by a new hold.
- [ ] Replace the old free-standing dismissal mutation with C0-frozen
  `InvalidEventDismissalPolicyV1`, strict `InvalidEventDismissalPlanV1`, and
  `InvalidEventDismissalEvidenceV1`. The plan has exactly the approved fields from campaign and
  registry/policy roots through hold/parent, eligible dismisser, proof, dispatcher/ref,
  `expected_no_effects_root`, `planned_at`, and self digest; the evidence has exactly campaign/hold,
  plan root, parent, proof/no-effects, dismisser ID/login/signature root, `dismissed_at`, and self
  digest. Use only proof kinds `authenticated_noop|byte_identical_applied_replay` and the exact
  newline domains. The selected identity is in the C0 policy and distinct from the rejected source.
  `INVALID_EVENT_DISMISSED` is a canonical
  expected-OID self-loop event: transition/state digest advances, state name and every unrelated root
  remain unchanged, and exactly the current hold root becomes null.
- [ ] Enforce the schema-generated parent, bundle kind, source workflow/ref, caller-specific actor,
  reason, strict evidence discriminator, hold root, active-exposure incident-ID/pending-root pair,
  and terminality predicates
  before constructing the next state. A nonnull hold is admitted only by dismissal, the exact
  premerge nondismissible/credential/drift STOP consumer, `RESULT_MERGED` release invalidation, or
  typed held-`RELEASED` correction intent; each binds and clears it. Every other ordinary,
  publication, release, correction, promotion, or safe-finalization edge requires the hold root null,
  both members of the active-exposure pair null, and the active containment root null. The sole
  exceptions are containment start, its post-CAS barrier/finality work and phase-exact terminal
  consumer; terminal-ready exposure already named by the immutable route is consumed atomically by
  that terminal event and cannot advance after containment starts.
- [ ] Rerun `test_state.py` to GREEN.

#### Step 3: RED-test the external OIDC broker and canonical Git lease

- [ ] Feed shuffled, missing, duplicated, expired, superseded, and forked authority commits/records;
  accept only one exhaustive parent-linked chain rooted at the exact protected canonical ref
  `refs/heads/benchmark-authority/{campaign_id}`. Operator-supplied artifact subsets and "latest by
  name" discovery are never authority.
- [ ] Build two deterministic mutation requests with the same expected canonical-ref OID and race
  them through one fake external broker. Exactly one receive-pack lease succeeds; the sibling fails atomically, and
  reconstructing from the winning ref yields its exact state, spend, hold, inventory, and artifact
  locator roots.
- [ ] Mutation and broker replay tests must reject every half-null active-exposure pair, a nonnull ID
  that differs from the pending/progress incident, a pending root copied from another incident, a
  progress event that changes either active field, and a terminal STOP/supplement candidate that
  clears only one. Replay the complete pending -> each progress effect -> terminal STOP and pending
  -> each progress effect -> drift supplement chains; require pending to set both, every progress
  commit to preserve both byte-for-byte, and the terminal commit to clear both atomically. Inject a
  stale expected pair, cross-incident receipt, response-loss adoption, and competing expected-OID
  candidate; only the byte-identical candidate with the exact predecessor pair may be adopted.
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
- [ ] Make `actor`/`actor_id` caller-discriminated. Every normal caller and rerun REST
  `triggering_actor` must equal the one plan-authorized frozen tag operator; only
  `benchmark-dismiss-hold.yml` instead requires the exact current dismissal-plan/C0-policy eligible
  account/login, distinct from the rejected source actor. An initial actor, ambient maintainer,
  environment reviewer, role/team/App, or operator fallback cannot satisfy dismissal authority.
- [ ] Generate the broker caller/ref/event matrix from `CampaignStateSchemaV1`. Every tag/main event
  requires its prebound caller SHA except exactly these six ordinary post-merge admission events:
  `RESULT_MERGED`, `INVALID_PREFIX_MERGED`, `CORRECTION_MERGE_RECORDED`,
  `RESULT_MERGE_INVALIDATED`, `INVALID_PREFIX_MERGE_INVALIDATED`, and
  `CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
  publication_outcome=merged_invalid)`. Each exception requires exact merge/current-main
  containment, unchanged result subtree, caller/callee C0 workflow bytes, direct `merge_commit`
  plan semantics, and the matching admission evidence/failure root; it grants no other event or
  write authority. Keep them distinct from the four protected-current-main classes: drift routes;
  publication terminal-containment start/barrier/finality; exact exposure pending/progress/phase-
  terminal/supplement; and safe-invalid continuation. Each class requires current-main caller and
  reusable workflow bytes equal their frozen C0 members, fresh pair/policy/registry evidence, and
  its one phase-exact row. Publication containment additionally binds the accepted intent/root and,
  when main advanced, exact first-parent `PublicationContainmentMainAdvanceProofV1`; it never
  rewrites the original OIDC run SHA or grants a constructive publication/release effect.
- [ ] Freeze the exhaustive top-level caller/ref/event table below and generate it from the same state
  schema as the transition matrix. A comma-separated cell names literal events, not a category or
  wildcard. Every main exception is limited to the six admission events or four current-main classes
  above; all other main rows require the plan-bound SHA.

  | Caller workflow | Required triggering ref | Exact allowed event types |
  |---|---|---|
  | `benchmark-preflight.yml` | exact campaign input tag | `PREFLIGHT_SEALED` |
  | `benchmark-batch.yml` | exact campaign input tag | `BATCH_RECEIPT_CONSUMED`, `NO_DISPATCH_PROVED`, `VERIFIED_PARTIAL`, `GENERATION_SET_SEALED`, `JUDGE_SET_SEALED`, `PERMANENT_STOP`, `BUDGET_EXHAUSTED`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
  | `benchmark-hard-score.yml` | exact campaign input tag | `HARD_SCORE_SET_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
  | `benchmark-evidence.yml` | exact campaign input tag; protected current `main` only for drift, exact cross-phase exposure, terminal-invalid supplement, or safe-invalid continuation | `EVIDENCE_INVENTORY_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED`, `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`; on current main, only the phase-exact containment/supplement or drift event |
  | `benchmark-audit.yml` | exact plan-bound `main` | `AUDIT_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
  | `benchmark-analysis.yml` | exact plan-bound `main` | `ANALYSIS_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
  | `benchmark-collect-complete.yml` | exact plan-bound `main` | `COMPLETE_BUNDLE_SEALED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
  | `benchmark-finalize-invalid.yml` | exact campaign input tag, or protected current `main` only for safe-invalid continuation | `INVALID_PREFIX_SEALED` |
  | `benchmark-dismiss-hold.yml` | exact plan-bound `main` | `INVALID_EVENT_DISMISSED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` |
  | `benchmark-publish.yml` | exact plan-bound `main`; protected current `main` additionally only for exact postmerge admission, publication containment, exposure, and drift rows | `PUBLICATION_INTENT_AUTHORIZED`, `PUBLICATION_TERMINAL_CONTAINMENT_STARTED`, `COMPLETE_PUBLICATION_PR_OPENED`, `INVALID_PUBLICATION_PR_OPENED`, `COMPLETE_PUBLICATION_PLAN_INVALIDATED`, `INVALID_PUBLICATION_PLAN_INVALIDATED`, `RESULT_MERGED`, `RESULT_MERGE_INVALIDATED`, `INVALID_PREFIX_MERGED`, `INVALID_PREFIX_MERGE_INVALIDATED`, `PERMANENT_STOP`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED`, `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`, `CORRECTION_INTENT_AUTHORIZED`, `CORRECTION_PUBLICATION_RECORDED`, `CORRECTION_MERGE_RECORDED`, and all four publication-family `CORRECTION_INVALIDATED` outcomes `unmerged_invalid|merged_invalid|fenced_write_ambiguity|reconciliation_unavailable`; separately only `initial_publication_receipt_append` |
  | `benchmark-release.yml` | exact plan-bound `main`; protected current `main` additionally only for exact postmerge exposure and drift rows | `RESULT_RELEASE_INTENT_AUTHORIZED`, `RESULT_RELEASED`, `RELEASE_PLAN_INVALIDATED`, `CORRECTION_TAG_RECORDED`, `CORRECTION_RELEASE_RECORDED`, `CORRECTION_RESULT_RELEASED`, release-family `CORRECTION_INVALIDATED`, `CREDENTIAL_EXPOSURE_PENDING`, `CREDENTIAL_EXPOSURE_EFFECT_RECORDED`; separately only `initial_release_receipt_append` |

  `benchmark-publish.yml` is the sole caller for containment start/finality and the publication
  receipt append; `benchmark-release.yml` is the sole release receipt append caller. The two PR
  validators and docs validator never call the broker; `benchmark-publication-state.yml` is the
  exact callee, never an independent event caller. Generate a negative vector for every unlisted
  caller/ref/event/non-event cell and require denial before OIDC exchange or App-token mint.
- [ ] Keep the non-state broker matrix separate from the generated campaign-event matrix. It has
  exactly two rows. `benchmark-publish.yml` on protected plan-bound main may request only
  `initial_publication_receipt_append` at matching `BUNDLE_COLLECTED|INVALID_FINALIZED`, exact active
  intent, null hold/exposure/containment roots, and next `branch -> pull_request` receipt. Separately,
  `benchmark-release.yml` on protected plan-bound main may request only
  `initial_release_receipt_append` at `RESULT_MERGED`, authoritative initial `release-intent.json`,
  null hold/exposure/containment roots, and next `tag -> draft_release -> assets -> publish` receipt.
  Both retain campaign state and every root byte-for-byte. They grant no correction, invalid-prefix,
  event, arbitrary path, generic receipt, or same-state append capability; every other caller/ref/
  state/kind combination is denied before OIDC exchange or App-token mint.
- [ ] Implement `MainFallbackLivenessPolicyV1` from C0 with exact repository, protected
  `refs/heads/main`, required check, workflow root, ordered 15 member paths, and exact newline-domain
  digest. For moved/deleted T0/T1, only the existing protected-main `benchmark-evidence.yml` may
  read frozen closure/authority and request the typed drift STOP or safe-invalid continuation; it
  must prove current-main contains byte-identical C0 workflow members and the required protected-main
  check is passing. This adds no App, workflow, environment, secret, provider/publication/release
  authority, or restored-ref resume path.
- [ ] Apply one universal fresh gate immediately before every provider-key mapping, OIDC exchange,
  App-token mint/use, artifact access/download, or external effect. The responsible workflow/tool/
  broker freshly double-reads T0/T1, verifies exact annotated-tag and peeled object OIDs/raw hashes,
  reconstructs the exact stable two-ruleset projection from fresh receipts, and matches the sealed
  tag binding plus `campaign_registry_sha256`. Temporary read failure yields no token, effect, or
  state; cached preflight, environment approval, intent, prior receipt, idempotent retry, or
  response-loss recovery never bypasses the gate. It then reconstructs hold, exposure, permanent
  publication denylist and active-containment roots. A nonnull containment root denies every
  constructive mint/dispatch/merge admission/release authorization; only its intent-bound barrier,
  merge-won classification, resumption proof and terminal finality row remain. Proven drift admits
  only the exact drift/exposure/close/safe-invalid exceptions generated by the schema.
- [ ] Prove the external broker alone holds the state-writer App private key and minted installation
  token. The Actions client sends only OIDC plus canonical `AuthorityMutationRequestV1`; no token,
  key, JWT signer, arbitrary URL, path, packfile, commit, or App credential returns to Actions.
  Credential canaries must be absent from request/receipt bytes, logs, errors, child environments,
  and generated artifacts.
- [ ] Define `AuthorityMutationRequestV1` as the exact strict three-member `mutation_kind` union.
  `campaign_event` has the sole variant field `campaign_event_source:
  CampaignEventMutationSourceV1`, whose exact fields are
  `schema_version,transition_number,event_type,event_record,event_sha256,required_member_paths,
  required_member_sha256s,recorded_at,source_sha256`; the parallel member arrays are positive,
  equal-length, canonical-order and duplicate-free and hash under
  `laconian-campaign-event-mutation-source-v1\n`. `initial_publication_receipt_append` has only the
  nested exact `InitialPublicationReceiptAppendV1`; `initial_release_receipt_append` has only the
  nested exact `InitialReleaseReceiptAppendV1`. The exact ordered common fields are
  `schema_version,mutation_kind,<one variant source>,campaign_id,campaign_registry_sha256,
  authority_ref,mutation_mode,expected_current_oid,proposed_tree_oid,commit_timestamp,
  state_writer_git_identity_sha256,predecessor_unresolved_hold_root,
  successor_unresolved_hold_root,predecessor_active_credential_exposure_incident_id,
  successor_active_credential_exposure_incident_id,
  predecessor_active_credential_exposure_pending_root,
  successor_active_credential_exposure_pending_root,
  predecessor_publication_merge_denylist_root_sha256,
  successor_publication_merge_denylist_root_sha256,
  predecessor_active_publication_terminal_containment_root,
  successor_active_publication_terminal_containment_root,oidc_run_identity_sha256,request_id,
  idempotency_key,request_sha256` under
  `laconian-authority-mutation-request-v1\n`. Each append's parent/time/idempotency key equals the
  outer expected OID/commit time/key and byte-preserves every state/root field.
  Missing/extra fields, caller-supplied packfile/commit/arbitrary path, reused idempotency key with
  different bytes, or mismatch against the signed OIDC identity is denied before App-token minting.
- [ ] Own the closed, acyclic §7.6 initial-publication and initial-release receipt wires in
  `publication_wire.py` and `release_wire.py`; Publication imports and re-exports these identical
  objects and never defines a second copy. The common release receipts are usable by both initial
  and correction flows, while only the two publication and four release append variants authorize a
  non-state authority commit.

- [ ] Keep OIDC/JWKS/API transport evidence outside the authority identity projection. The exact
  state-broker projection contains only repository, repository_id, repository_owner,
  repository_owner_id, actor, actor_id, ref, ref_type, sha, event_name, workflow, workflow_ref,
  workflow_sha, job_workflow_ref, job_workflow_sha, run_id, run_attempt, check_run_id, and
  runner_environment. The signed broker request carries only its digest. Raw typ/alg/kid/issuer/
  audience/subject/jti/time claims, triggering-actor API evidence and JWKS/run/job receipts remain
  broker audit inputs, not extra projection fields. The reusable state job has no environment claim;
  reject any exported raw-OIDC projection schema, deployment/approval field, job-name field,
  caller-supplied claim projection, or raw-token metadata that could confer authority.
- [ ] Define the two initial-publication effect receipts exactly in publication_wire.py.
  PublicationBranchReceiptV1 contains, in order, schema_version, campaign_id,
  campaign_registry_sha256, publication_id, positive publication_attempt, intent_sha256,
  operation created|adopted, branch_name, base_oid, head_oid,
  branch_create_delivery_resolution_sha256, publisher_credential_disposition_sha256,
  publisher App actor, request_receipts_root, and receipt_sha256. PublicationPRReceiptV1 contains
  schema_version, the same campaign/registry/publication/attempt/intent, branch_receipt_sha256,
  operation created|adopted, positive pull_request_number, pull_request_node_id, exact HTTPS URL,
  base/head OIDs, marker, merge_eligibility_receipt_sha256,
  merge_eligibility_delivery_resolution_sha256, pr_create_delivery_resolution_sha256,
  pr_marker_discovery_sha256, eligibility and PR-create publisher credential disposition roots,
  publisher App actor, request_receipts_root, and receipt_sha256. Their domains are respectively
  laconian-publication-branch-receipt-v1\n and laconian-publication-pr-receipt-v1\n, omitting
  only receipt_sha256.
- [ ] Define InitialPublicationReceiptAppendV1 as the strict receipt_kind union of
  InitialBranchReceiptAppendV1 and InitialPRReceiptAppendV1. Every variant contains exactly, in
  order, schema_version, mutation_kind=initial_publication_receipt_append, literal receipt_kind,
  campaign_id, campaign_registry_sha256, publication_id, positive publication_attempt, bundle_kind,
  authorizing_intent_sha256, publication_plan_sha256, authority_parent_oid,
  campaign_state_sha256_before, campaign_state_sha256_after, nullable predecessor_append_sha256,
  literal receipt_path, class-bound receipt_payload, append_idempotency_key, recorded_at, and
  append_sha256. Branch is kind branch/path branch-receipt.json/null predecessor/
  PublicationBranchReceiptV1/domain laconian-initial-branch-receipt-append-v1\n; PR is kind
  pull_request/path pr-receipt.json/immediate branch predecessor/PublicationPRReceiptV1/domain
  laconian-initial-pr-receipt-append-v1\n. recorded_at is the accepted
  PUBLICATION_INTENT_AUTHORIZED time plus exactly one or two seconds, never a workflow clock.
- [ ] Define the shared release authorization/result wire exactly in release_wire.py.
  ReleaseEffectAuthorizationV1 contains schema_version, intent_kind initial|correction,
  campaign_id, campaign_registry_sha256, publication_id, nullable publication_attempt, nullable
  correction_id, authorizing_intent_sha256, preauthorized_release_plan_sha256,
  executable_release_plan_sha256, security_attestor_receipt_sha256,
  tag_target_kind initial_merge|correction_approved_head, authorized_tag_target_oid, and
  authorization_sha256. Initial requires positive attempt/null correction; correction requires
  null attempt/path-safe correction ID. Its domain is
  laconian-release-effect-authorization-v1\n, omitting only authorization_sha256.
- [ ] ReleaseEffectResultV1 contains exactly schema_version, effect_kind
  tag_object|tag_ref|draft_release|asset|publish|final_verification, nested exact authorization,
  effect_idempotency_key, api_method POST|PATCH|GET, endpoint_template, request_payload_sha256,
  request_receipts_root, positive response_status, raw_response_sha256,
  canonical_response_sha256, operation created|uploaded|published|adopted|verified,
  external_object_observation_sha256, and effect_result_sha256. Its domain is
  laconian-release-effect-result-v1\n. AnnotatedTagEffectResultsV1 contains exactly
  schema_version, tag_effect_idempotency_key, tag-object result, tag-ref result, and
  effect_results_root_sha256 under laconian-annotated-tag-effect-results-v1\n. The tag steps are
  object ordinal 0 then ref ordinal 1 with the exact derived step keys; a one-step effect_kind=tag,
  lightweight tag, reordered pair, or hidden partial result is invalid.
- [ ] InstallationTokenRevocationReceiptV1 contains exactly schema_version, campaign_id,
  campaign_registry_sha256, publication_id, authorization_sha256, effect_kind
  tag|draft_release|asset|publish|final_verification, subject_kind
  complete_effect_result|partial_effect_prefix|failed_delivery_resolution, subject_root_sha256,
  token_closure_projection_sha256, release-finalizer App identity, token_fingerprint_sha256,
  token_vault_committed_at, token_expires_at, endpoint DELETE /installation/token, API version
  2022-11-28, outcome revoked_204|ambiguous_delivery_then_confirmed_unusable|
  expired_then_confirmed_unusable, revoked_or_confirmed_unusable_at, and
  revocation_receipt_sha256. Its domain is
  laconian-installation-token-revocation-receipt-v1\n. It contains no free effect-result root,
  issue-time alias, request-root alias or standalone denial-probe root; those facts reconstruct
  through the exact signed closure projection.
- [ ] FinalReleaseVerificationReceiptV1 contains exactly schema/campaign/registry/publication,
  authorization, final-verification ReleaseEffectResultV1, effect_delivery_resolution_sha256,
  immutable_release_verification_sha256, final_external_objects_root_sha256, release-finalizer
  actor, request_receipts_root, final-verification revocation, and receipt_sha256. Its domain is
  laconian-final-release-verification-receipt-v1\n.
- [ ] Define the four shared outer receipt payloads exactly. TagReceiptV1 has authorization,
  AnnotatedTagEffectResultsV1, separate tag-object and tag-ref delivery-resolution roots, tag
  name/object/target, actor, the ordered object-then-ref request-receipt Merkle root, tag-token
  revocation, and receipt digest. DraftReleaseReceiptV1, ReleaseAssetReceiptV1, and PublishReceiptV1
  each add effect_delivery_resolution_sha256 immediately after their class-bound effect result and
  otherwise retain the approved exact object/operation/actor/request/revocation fields. Their
  domains are laconian-tag-receipt-v1\n, laconian-draft-release-receipt-v1\n,
  laconian-release-asset-receipt-v1\n, and laconian-publish-receipt-v1\n, omitting only each
  receipt_sha256. Every nested authorization and effect result byte-matches; each success receipt
  binds the complete exact-success delivery resolution, and asset payloads are exactly ordinals
  [0,1] with one release ID and distinct names/IDs.
- [ ] Define InitialReleaseReceiptAppendV1 as the strict tag|draft_release|assets|publish union.
  Every variant contains exactly, in order, schema_version, mutation_kind,
  receipt_kind, campaign_id, campaign_registry_sha256, publication_id, positive
  publication_attempt, authorizing_intent_sha256, preauthorized_release_plan_sha256,
  executable_release_plan_sha256, security_attestor_receipt_sha256, authority_parent_oid,
  campaign_state_sha256_before, campaign_state_sha256_after, nullable predecessor_append_sha256,
  literal receipt_path, class-bound receipt_payload, append_idempotency_key, recorded_at, and
  append_sha256. Paths/payloads are tag-receipt.json/TagReceiptV1,
  draft-release-receipt.json/DraftReleaseReceiptV1,
  asset-receipts.json/exact ordered two-member ReleaseAssetReceiptV1 tuple, and
  publish-receipt.json/PublishReceiptV1. Their exact domains are
  `laconian-initial-tag-receipt-append-v1\n`,
  `laconian-initial-draft-release-receipt-append-v1\n`,
  `laconian-initial-asset-receipts-append-v1\n`, and
  `laconian-initial-publish-receipt-append-v1\n`, respectively.
  recorded_at equals the accepted RESULT_RELEASE_INTENT_AUTHORIZED time plus exactly one, two,
  three, or four seconds respectively. No wrapper omits publication_attempt/recorded_at or derives
  time from an effect/retry/workflow clock.
- [ ] Add independent literal canonical vectors for every shared receipt/aggregate/append preimage
  above. Initial release binds the acyclic
  InitialPreauthorizedResultReleasePlanV1 -> passing SecurityAttestorReceiptV1 ->
  ExecutableResultReleasePlanV1(intent_kind=initial) -> ResultReleaseIntentV1 graph: the
  preauthorized and executable digests are distinct and each is recomputed from its nested object.
  Correction binds CorrectionReleaseIntentPlanV1.plan_sha256 as preauthorization and the postmerge
  `ExecutableResultReleasePlanV1.executable_release_plan_sha256` as executable while retaining the
  immutable approved-head tag target and original `CorrectionIntentV1` digest. Reject legacy
  one-plan aliases, equality
  between the two initial plan digests, attestor substitution, merge-commit retargeting, omitted
  delivery roots, wrong tag step, partial-effect success, cross-intent/cross-publication replay,
  wrong append time/attempt/path/predecessor, or an aggregate/checkpoint that drops final
  verification or token closure.

- [ ] Require every shared wire class to be strict/frozen/extra-forbid and hash exactly its
  approved newline domain while omitting only its named self field. Verify release effect chronology
  as authorization -> dispatch/delivery resolution -> exact effect result or partial prefix ->
  signed token closure -> revocation receipt -> outer receipt. Every minted token has one complete,
  partial, or failed-resolution subject and one first-decisive closure; a 204 permits no later delete,
  an ambiguous-loss outcome requires bound same-token denial probes, and expiry requires no earlier
  decisive observation. Count every post-boundary operation-dispatch start, not merely successful
  calls, and require zero.
- [ ] Export only Runtime-owned shared broker, initial-publication receipt/append, release receipt/
  append and containment state/event/request/receipt types plus
  `append_initial_publication_receipt` and `append_initial_release_receipt` from `campaign.__init__`.
  Extend `tests/test_public_contract.py` to prove Publication imports those identical class objects
  from `campaign.broker_wire`, `campaign.publication_wire`, `campaign.release_wire`, state and
  authority owners, never subclasses, aliases or locally flattened copies. The six Runtime-owned
  denylist/containment package exports are owner-identical to `campaign.publication_wire`, present
  exactly once in Runtime's owner manifest, and absent from Publication's owner manifest; Publication
  only class-bound consumes them. Freeze the exact authorization field tuple, the two tag
  delivery roots, each non-tag effect_delivery_resolution_sha256, both append attempt/time fields,
  and both receipt-family unions. The public export set contains no OIDC raw-token projection or
  broker secret/handle type.
- [ ] Construct canonical Git SHA-1 blobs, trees, and commits independently. Require repository
  object format SHA-1, exact `100644` record blobs and `040000` trees, canonical raw-byte tree order,
  no symlink/executable/submodule, exactly zero parents for bootstrap or one expected parent for a
  successor, the frozen `StateWriterGitIdentityV1` author/committer lines, whole-second UTC epoch,
  and message `laconian benchmark authority <campaign-id> transition <20-digit-number>: <event-type>\n`
  for event commits. An initial-publication append instead uses exactly
  `laconian benchmark authority <campaign-id> state <20-digit-current-transition>: initial-publication-<receipt-kind>\n`;
  an initial-release append uses the corresponding exact
  `...: initial-release-<receipt-kind>\n`. Neither invents or increments a campaign transition. The
  author/committer epoch and request commit time equal the nested event/append `recorded_at` exactly;
  there is no fourth message grammar.
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
- [ ] Exhaustively test both initial-publication and all four initial-release append variants: exact direct campaign/registry/
  publication/initial-intent/plan equality; payload self digest; App actor; fixed filename; strict
  predecessor append; aggregate asset ordinals/order; distinct idempotency key; exact old-OID lease;
  positive publication attempt, deterministic recorded time, and byte-identical campaign-state
  blob/hash/transition/hold/pending/denylist/containment roots. Inject loss before and
  after each object upload/ref update and require byte-identical adoption. Reject a missing/skipped/
  duplicate/reordered path, correction authorization, locally fabricated receipt, arbitrary payload,
  state/event change, half-null gate, stale OID, and any generic non-state append. Require branch then
  PR appends before either publication-open event, and all four release appends as authoritative
  files before `RESULT_RELEASED`; `RELEASE_PLAN_INVALIDATED` may terminate a partial
  prefix while preserving every already-recorded external object.
- [ ] Test dismissal only in the exact schema-enumerated states. Require the plan-selected C0-policy
  identity to equal OIDC actor and rerun triggering actor, be distinct from the rejected-event source,
  and produce the exact `INVALID_EVENT_DISMISSED` CAS. `benchmark-publish` environment approval is
  additional provenance, never the identity authority; excluded states and actors fail closed.
- [ ] Exhaustively parameterize pre-auth/transient/benign-sibling denials versus authenticated
  hold-worthy failures. Prove only the latter creates the one hold; dismissal then requires the exact
  frozen eligible actor, strict plan, and no-effects proof. Identity/provenance/spend/delivery/
  credential/STOP/release/security defects use their typed consumer paths and cannot be relabeled as
  a dismissible no-op under any actor or terminal state.
- [ ] Test nondismissible terminal paths: a pre-merge `PERMANENT_STOP` hold, the accepted post-merge
  `RELEASE_PLAN_INVALIDATED -> RELEASE_BLOCKED` state transition, and post-release correction-lineage
  evidence stages appended without rewriting history. A `correction_release` mutation leaves
  `RELEASED` unchanged, but from `RELEASE_BLOCKED` the read-only recorder must derive both the
  correction-release envelope and the separately verified `CORRECTION_RESULT_RELEASED` event in one
  ordered candidate package. The broker installs the schema-required records in one deterministic
  authority commit and one expected-old-OID receive-pack lease.
- [ ] Reject every predecessor-only durable-substitution/checkpoint schema or locator-rebinding
  channel. The approved authority tree retains its exact canonical records and immutable event/
  receipt evidence, while transient Actions artifacts remain required inputs until their approved
  terminal consumer has copied only the normative digests/receipts into authority. A missing or
  expired referenced artifact is fatal; a protected merge tree, result tag, Release, asset, same-name
  file, or caller mapping cannot substitute for it. Postmerge reconstruction instead verifies the
  approved merge/admission, release-effect, final-verification, token-closure, and terminal-
  containment records at their exact authority paths. Test expiration, same-bytes-at-another-path,
  merge-tree/tag/asset substitution, incomplete ancestry, and an invented checkpoint member; each
  fails without changing authority.
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

#### Step 4: GREEN authority mutations

- [ ] Implement no intermediate authority-envelope union. A candidate carries exactly one of the
  three class-bound sources already present in `AuthorityMutationRequestV1`: exact
  `CampaignEventMutationSourceV1`, `InitialPublicationReceiptAppendV1`, or
  `InitialReleaseReceiptAppendV1`. Revalidate the source object, required-member manifest,
  predecessor authority/state/root tuple, provenance and digest directly; a generic unchanged-state
  append, predecessor-envelope hash, or fourth wrapper schema is rejected.
- [ ] Define `AuthorityMutationV1` as a strict frozen candidate package containing campaign ID,
  `campaign_registry_sha256`, expected authority-ref OID (nullable only for initial creation),
  predecessor authority-head/state/hold roots, predecessor active-exposure incident ID and pending
  root, predecessor publication denylist and active-containment roots, predecessor correction/
  publication roots, one schema-ordered three-member mutation source, and all
  resulting roots and active-exposure fields,
  trusted artifact provenance, `state_writer_git_identity_sha256`, and mutation digest. The broker replays the
  source before constructing one deterministic child commit; the initial-receipt variant retains
  every state/root/transition field byte-for-byte. The containment-start candidate alone appends one
  denylist snapshot and sets its intent root; its terminal consumer preserves that denylist and
  clears only the matching active root. Candidates are composable only
  through a pure builder, never by concatenating JSON.
- [ ] Implement `apply_campaign_event` so each event adds exactly the schema-required canonical
  `events`, `evidence`, `corrections`, `publication`, `receipts`, or `incidents` members in one
  candidate authority tree. A correction release receipt must already be the exact predecessor of
  `CORRECTION_RESULT_RELEASED`; no concatenated JSON or caller-selected extra record is accepted.
  Implement `dismiss_invalid_event_hold` only as construction of the exact
  `INVALID_EVENT_DISMISSED` event from one verified `InvalidEventDismissalPlanV1` and matching
  `InvalidEventDismissalEvidenceV1`; no untyped hold-mutation channel remains.
- [ ] Implement `append_initial_publication_receipt` and `append_initial_release_receipt` as the only
  non-event builders. The publication builder reconstructs the exact active complete/invalid initial
  intent at `BUNDLE_COLLECTED|INVALID_FINALIZED`, requires null hold/exposure/containment, verifies
  campaign/registry/publication/positive attempt/bundle/intent/plan/actor and deterministic time,
  and appends only branch then PR. The release builder class-bound
  revalidates the Runtime-owned common receipt and append variant, reconstructs the authoritative
  initial `release-intent.json`, requires `RESULT_MERGED`, null hold/pending/containment roots, exact direct
  campaign/registry/publication/positive attempt/intent, separately recomputed
  `InitialPreauthorizedResultReleasePlanV1` and `ExecutableResultReleasePlanV1` digests, exact
  security-attestor receipt, and the next absent path in the four-row
  order. It returns one mutation whose state blob/hash/transition and every nonreceipt tree member
  are byte-identical. Neither builder can accept a correction receipt, raw bytes, path, callback, Boolean,
  candidate OID, or caller-selected event. Publication supplies only the strict shared object.
- [ ] Define each authority Git commit as a canonical tree containing the current head record,
  immutable envelope bytes, and the exact numeric artifact IDs/service/payload digests required to
  reconstruct every ancestor. The commit has the previously observed authority-ref OID as its sole
  parent. Reject every missing/expired referenced ancestor at every state. At or after
  `RESULT_MERGED`, additionally verify the exact protected merge/admission records; at or after
  `RESULT_RELEASED`, verify the annotated tag, published Release/assets, immutable-Release evidence,
  final verification and token closures named by the accepted authority records. These external
  objects do not replace an absent authority member or transient artifact required by an earlier
  event. A mutable-ref lookup, merely same-named file, caller mapping, or invented durable checkpoint
  is fatal. The protected authority Git history stores every canonical authority record and never
  delegates record identity to Actions-artifact discovery.
- [ ] Implement `AuthorityTreeSchemaV1` with exact root blob `campaign-state.json` and optional root
  trees `events`, `evidence`, `holds`, `receipts`, `corrections`, `publication`, `incidents`, and
  `denylist`. Admit only the exact incident paths `incidents/<incident-id>/pending.json`,
  `incidents/<incident-id>/effects/<8-digit-ordinal>.json`, terminal/supplement evidence paths, and
  `denylist/provisional/<incident-id>.json` or `denylist/permanent/<incident-id>.json`; never a
  generic incident/denylist filename or caller-selected path.
  The publication append family admits only
  `publication/initial/<authoritative-publication-id>/attempts/<20-digit-publication-attempt>/branch-receipt.json`,
  then the same prefix's `pr-receipt.json`. The release append family admits only that exact attempt
  prefix's `tag-receipt.json`, then `draft-release-receipt.json`, then `asset-receipts.json`, then
  `publish-receipt.json`; each file
  is the canonical matching Runtime-owned append variant and nested receipt payload. The prefix,
  publication ID, filename, kind, predecessor append digest, and presence/absence of all earlier
  members are derived from authority and cannot be supplied as a free path. Campaign-event
  envelopes cannot create these six files, and either append family cannot create any other
  tree member.
  Preflight stores the empty publication denylist snapshot at
  `denylist/publication/merge/<empty-root>.json`. Containment start additionally appends exactly its
  successor snapshot, generic event, byte-identical intent-local `containment-start-event.json`,
  `publication/containment/<intent-root>/{intent,broker-prefix,vault-prefix}.json`; terminal finality
  appends only the finality-derived content-addressed barrier, nullable fenced-write-ambiguity,
  nullable merge-won, required finality and ordinary no-later/unavailable evidence members. Require
  a stored zero-residual barrier, exact payload class/root/path derivation and immutable retention of
  every older denylist/containment member.
  Event paths are `events/<20-digit-transition>-<schema-event-name>.json`; content-addressed evidence
  paths are exactly `evidence/<schema-name>/<lowercase-sha256>.json`. Every successor retains every prior member
  byte-for-byte. A campaign-event successor replaces only `campaign-state.json` and appends exactly
  the current schema-required members; an initial-receipt successor retains `campaign-state.json`
  byte-for-byte and appends only its one receipt path.
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
- [ ] Implement `AuthorityMutationReceiptV1` as the same exact strict three-member union. The event
  variant carries exactly `transition_number,event_type,event_sha256,
  event_member_manifest_root_sha256`; each append variant carries only
  `receipt_kind,receipt_path,append_sha256`. Its ordered common fields are
  `schema_version,mutation_kind,<variant fields>,campaign_id,campaign_registry_sha256,request_id,
  idempotency_key,authority_ref,mutation_mode,expected_old_oid,ordered_blob_oids,ordered_tree_oids,
  candidate_commit_oid,observed_before_oid,observed_after_oid,outcome,endpoint_policy_sha256,
  github_request_receipts,final_reconciliation_receipts,app_actor_id,app_actor_login,
  state_writer_git_identity_sha256,oidc_run_identity_sha256`, then the exact predecessor/successor
  hold, exposure incident, exposure pending, publication denylist and active-containment pairs,
  `started_at,completed_at,receipt_sha256` under
  `laconian-authority-mutation-receipt-v1\n`. Every discovery GET and
  possibly delivered receive-pack POST appears once; response loss has null status/safe response,
  and reconciliation observations cannot be omitted. On response loss adopt
  only an exact fully reverified candidate; retry only while the ref is unchanged; any third OID or
  byte disagreement is a terminal conflict.
- [ ] Define `AuthorityRefReconciliationReceiptV1` with exactly
  `schema_version,repository_id,authority_ref,candidate_commit_oid,expected_old_oid,
  observation_round,method,endpoint_template,request_id,request_dispatched_at,
  response_completed_at,response_status,observed_ref_oid,
  verified_candidate_object_closure_root_sha256,resolved_state,reconciliation_receipt_sha256`
  under `laconian-authority-ref-reconciliation-receipt-v1\n`. Method/endpoint are the literal
  authority-ref GET; round is `1|2`; 404 maps only to absent/null observation, 200 requires an OID,
  and only an exact candidate may carry the verified closure root. Every mutation receipt contains
  both ordered rounds with distinct request IDs and equal final resolution; `created|adopted_exact`
  requires two exact-candidate reads after all possibly delivered receive-pack attempts. Test 404,
  divergent/candidate byte mismatch, changed state between rounds, omitted lost write, reordered
  round, and retry-after-third-OID as terminal failures.
- [ ] Compute `unresolved_hold_root` from the exact current active-hold projection and compute
  `active_credential_exposure_pending_root` only through the normative empty/link/progress preimages;
  neither root may be copied from a request. Require each exposure receipt to byte-match campaign,
  incident, originating pending digest, predecessor progress root, and next ordinal before deriving
  its successor root.
- [ ] Implement `require_ordinary_effect_gate` in `campaign.authority` with the exact signature
  `require_ordinary_effect_gate(authority: ReconstructedAuthorityV1) -> None`; export it from
  `campaign.__init__`. It first verifies the active incident-ID/pending-root pair invariant and
  reconstructs the full monotone publication denylist, and admits an ordinary credential/effect/
  event only when `unresolved_hold_root`, `active_credential_exposure_incident_id`,
  `active_credential_exposure_pending_root`, and `active_publication_terminal_containment_root` are all
  proven null; typed atomic
  consumers are admitted only by their generated schema rows. Keep `apply_campaign_event` pure: it
  constructs a candidate bound to expected state, hold root, both active-exposure fields, denylist,
  active containment, and authority-ref OID. The broker re-verifies every field immediately before
  the receive-pack lease.
- [ ] Run state and authority files together to GREEN:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_publication_wire.py tests/campaign/test_release_wire.py tests/campaign/test_state_schema.py tests/campaign/test_state.py tests/campaign/test_state_broker.py tests/campaign/test_authority_git.py tests/campaign/test_authority.py -q
```

Expected GREEN: PASS; the schema-generated state machine, external broker policy, canonical Git
objects, smart-HTTP receive-pack leases, and reconstructed authority all pass.

#### Step 5: Commit

- [ ] Run `git diff --check` and commit:

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/state_schema.py \
  src/laconian_eval/campaign/state.py \
  src/laconian_eval/campaign/state_broker.py \
  src/laconian_eval/campaign/authority_git.py \
  src/laconian_eval/campaign/authority.py \
  src/laconian_eval/campaign/publication_wire.py \
  src/laconian_eval/campaign/release_wire.py \
  tools/benchmark_state_broker_client.py \
  tests/campaign/test_state_schema.py \
  tests/campaign/test_state.py \
  tests/campaign/test_state_broker.py \
  tests/campaign/test_authority_git.py \
  tests/campaign/test_authority.py \
  tests/campaign/test_publication_wire.py \
  tests/campaign/test_release_wire.py \
  tests/test_public_contract.py
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

Expected GREEN: PASS; every reservation and five-component reconciliation is exact.

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
- [ ] Run provider, attempt, delivery, and retry tests to GREEN:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_retry.py tests/test_openai_provider.py tests/capsule/test_attempts_v2.py tests/capsule/test_delivery_certainty.py -q
```

Expected GREEN: PASS; only the exact definitely-rejected 429 evidence receives a bounded retry.

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
- [ ] Reject reordering, gaps, duplicate request IDs, a shard/request outside the remaining suffix,
  an enlarged plan, a stale predecessor, wrong workflow/registry/tag-pair hash, wrong price hash,
  nonnull hold, nonnull active exposure root, nonnull active publication-containment root, a
  nonreconstructing/mismatched publication denylist root, or STOP.
- [ ] Assert `BatchPlanV1` binds campaign, `campaign_registry_sha256`, complete companion-tag binding,
  phase, mode, both tag objects/peeled commits, workflow SHA-256, requested service-tier literal/root,
  predecessor state/spend/inventory/hold/active-exposure/publication-denylist/active-containment
  roots, ordered shard/request
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
  hold/active-exposure/publication-denylist/active-containment/inventory/phase-plan roots, and a
  bounded monotonic allowance. It has no model, retry, price,
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
  winning remote `BATCH_RECEIPT_CONSUMED` authority commit and mutation receipt are durable before
  the first API-key
  environment lookup. Local fsync or an uploaded candidate is insufficient: re-fetch the protected
  authority ref, reconstruct it from the winning OID, and match the exact workflow run, run attempt,
  numeric provider job ID, UUID4 batch-attempt ID, plan, reservation, and receipt.
- [ ] Immediately before the provider step evaluates `OPENAI_API_KEY`, rerun the universal fresh
  pair/policy/registry gate and the exact Foundation-owned
  `require_benchmark_sdk_contract(c0_uv_lock_bytes=verified_c0.read_regular_file("uv.lock"),
  expected_c0_uv_lock_sha256=verified_input_package.uv_lock_sha256)` call over the same verified C0
  member. Inject failure
  at each read/model check and prove the provider secret expression is never evaluated, no provider
  is constructed, no OIDC/App token is minted, no artifact is downloaded, and no state is changed.
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

Expected GREEN: PASS; the contiguous planner and single-use receipt consumer satisfy every test.

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

- [ ] Before provider construction and before every initial call/retry, independently rerun the
  universal fresh pair/policy/registry gate and revalidate registry/tag binding, batch plan, receipt,
  state hash, nullable hold/active-exposure/active-publication-containment roots, reconstructed
  permanent publication-denylist root, spend hash, checkpoint inventory root, STOP
  marker, reservation, SDK `3.3.1`/lock/model projection, and exact next request. Any temporary read
  failure, drift, hold, or pending exposure performs zero key access/call and routes only through its
  exact schema-authorized evidence path.
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
  final archive bytes against the exact key and the frozen credential patterns. A pre-upload match
  emits only content-free local scan-failure evidence, quarantines or deletes the unsafe archive,
  returns no upload locator, and makes zero later provider calls; it must not falsely claim remote
  `credential_exposure`. Any match discovered after an upload or possible download instead enters
  the exact pending → ordered containment-effect receipts → final STOP/supplement protocol, and no
  immediate one-step incident/STOP helper is permitted.
- [ ] Prove a controller crash or exit before a complete `CredentialScanReceiptV1` leaves no
  upload-authorized archive. The receipt binds campaign, batch, payload role, exact payload digest,
  payload byte length, pattern-policy hash, exact-key-scan boolean, scan completion time, and receipt digest;
  it never includes the key, a matched excerpt, an environment value, or a private path.
- [ ] RED-test cross-phase post-upload credential discovery separately from local pre-upload scan
  failure. First CAS exact `CredentialExposurePendingV1` plus provisional denylist; then execute only
  the frozen complete containment inventory, record each external effect as the next
  `CredentialExposureEffectReceiptV1` expected-OID self-loop, and finally consume the exact progress
  root with the schema-selected terminal consumer: direct premerge credential-exposure STOP,
  `ProtocolDriftCredentialExposureSupplementV1`, `InvalidLineageCredentialExposureSupplementV1`, or
  the exact postmerge/correction invalidation or correction-intent record. Inject a crash after
  pending, after
  each effect, after an external success before its receipt, before final CAS, and during an open-PR
  close/merge race; resume by exact idempotent state observation only, never by re-enabling provider
  or downloads. Test exposure-before-drift, drift-during-exposure, and exposure-after-drift ordering.
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
  `seal_generation_context(registry, verified_input_package, preflight_seal, verified_phase_plan,
  generation_evidence, output_root) ->
  VerifiedGenerationContextIndexV1` in `campaign.benchmark_adapter`. It calls the benchmark-owned
  `write_layer_root_index` for the exact 36 generation capsule/sidecar pairs and
  `write_generation_context_index` for
  `GENERATION/generation-context.json`, copying campaign seed, peeled commit, exact tagged
  hard-scorer source path/hash, hard-score/judge/statistics protocol paths/hashes, and the exact
  Evaluation-owned `audit_protocol_sha256: Sha256` already derived by Task 2 from verified C0
  `benchmarks/protocols/public-three-model-v1/audit.json` bytes at the peeled input commit,
  plus the unchanged `audit_sampling_protocol_sha256`,
  `audit_commit_reveal_protocol_sha256`, and `audit_adjudication_protocol_sha256` bindings,
  exact two audit-reviewer and three role-bound protocol-reviewer bindings/signing modes, both
  reviewer-registry digests, the exact workflow inventory/root, seed, protocol members, and other
  C0-derived fields from class-bound `VerifiedCampaignInputPackageV1`; the three ordered verified
  envelopes/root and complete companion-tag binding from class-bound `CampaignPreflightSealV1` and
  the exact payload fields of verified `CampaignRegistryV1`; and the registry digest from that
  registry. Require the input-package digest to equal
  `registry.payload.campaign_input_package_sha256` and the seal to bind the same registry digest.
  Re-open and
  re-hash the exact tagged source/protocol members and require equality rather than copying an
  unverified scalar. Adapter tests independently substitute the statistics member/hash and require
  rejection before context publication or analysis authority can exist.
  Fresh-reload both outputs and byte-compare all 36 ordered parents. Campaign imports neutral
  benchmark types; benchmark code never imports a campaign type.
- [ ] Bind the resulting generation layer-root digest and
  `generation_context_index_sha256` into the accepted `GENERATION_SET_SEALED` event evidence and its
  authority commit. The read-only hard-score preparer reconstructs canonical authority, extracts
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
- [ ] Rerun controller and capsule regression tests to GREEN:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_controller.py tests/campaign/test_benchmark_adapter.py tests/campaign/test_runtime.py tests/capsule/test_execution.py tests/capsule/test_resume.py tests/test_public_contract.py -q
```

Expected GREEN: PASS; the exact generation/judge suffixes, sealed roots, private Runtime methods,
checkpoint recovery, and credential-scan handoff pass together.

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
- [ ] Pin the compatible dispatcher signature exactly as
  `main(argv: Sequence[str] | None = None, *, program: str | None = None) -> int`.
  `program="laconian-benchmark"` selects only the seven offline handlers, `program="laconian"`
  preserves the legacy parser/entrypoint, and omitted `program` derives the installed script name.
  Runtime tools never call `main`, and this plan introduces no eighth command or live CLI hook.
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

Expected RED: FAIL because Runtime construction/export and replay import boundaries are not yet
closed.

#### Step 2: Implement the minimal private boundary and verify GREEN

- [ ] Make Runtime construction token-gated by a module-private sentinel produced only after exact
  authority reconstruction. Keep the capability in private slots and make serialization/copy
  attempts fail with content-free errors.
- [ ] Make both fixed stage tools import only `_reconstruct_verified_runtime` plus the three exact
  methods, use fixed literal paths supplied by their workflows, and expose no reusable parser or
  arbitrary method name.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_runtime_boundary.py tests/test_public_contract.py tests/test_cli.py -q
```

Expected GREEN: PASS; only the private Runtime construction path owns the three live methods and
all seven public replay commands remain offline.

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
- Create: `src/laconian_eval/campaign/release.py`
- Create: `src/laconian_eval/campaign/release_broker.py`
- Create: `tools/benchmark_release_broker_client.py`
- Create: `tools/benchmark_preflight_stage.py`
- Create: `tools/benchmark_prepare_batch.py`
- Create: `tools/benchmark_run_batch.py`
- Create: `tools/benchmark_post_batch.py`
- Create: `tools/benchmark_prepare_hold_dismissal.py`
- Create: `tests/campaign/test_workflow_policy.py`
- Create: `tests/campaign/test_release_broker.py`
- Create: `tests/campaign/test_security_attestor_credential_finality.py`
- Modify: `tests/test_ci_contract.py`

#### Step 1: RED-test workflow policy structurally

- [ ] Parse YAML and reject aliases/merge keys before schema inspection.
- [ ] `benchmark-preflight.yml` must be no-input `workflow_dispatch` only, have top-level
  `permissions: {}`, the literal shared concurrency group, no environment, and no secret expression.
  Require `github.ref_type == "tag"`, exact input-tag grammar, tag-object/peeled-commit verification,
  and prove the actual `GITHUB_WORKFLOW_REF` path plus running workflow bytes/hash equal that exact
  `C0` workflow-inventory member; default-branch/branch dispatch or a mutable workflow copy fails. It
  has a read-only `prepare-preflight` job with exactly `contents: read` and
  `pull-requests: read`, used in part to double-read T0/T1 and re-fetch the exact
  C0/Rstat/Rjudge/Rsecurity/B0 object closure, statements, envelopes, bundle, GitHub projections,
  policy observations, and both historical creation-suite receipts. It emits a cycle-free preflight
  attestation subject. A following job named exactly `security_attestor` has
  only `id-token: write`, no environment or repository token permission, and invokes the hash-bound
  secret-free `benchmark_release_broker_client.py` with exact OIDC audience
  `laconian-security-attestor-broker`. The external measured broker owns the existing
  release-finalizer App key/token, selects only the frozen `preflight_rulesets` caller row, performs
  the exact tag/publication-ruleset GET allowlist, closes the token, and returns only signed safe pass
  or failure evidence. A read-only sealing job accepts only a closed passing receipt before it can
  build the `PREFLIGHT_SEALED` candidate; failure has no authority candidate. Its state-mutation job
  calls only the same-repository reusable `benchmark-publication-state.yml` with the canonical
  `PREFLIGHT_SEALED` request. No App/installation ID is a credential input or secret mapping, and no
  key, token, state credential, arbitrary pack, or write-capable repository token exists in Actions.
  Signed safe receipts may contain only the preregistered nonsecret App/installation identity needed
  for actor verification. The external broker creates
  `refs/heads/benchmark-authority/{campaign_id}` only with `expected_absent` and the all-zero old
  SHA-1 OID; an existing divergent ref or simultaneous creator fails atomically.
- [ ] Preflight verifies the exact two-ruleset model and historical creation evidence before
  registry sealing: fresh current observations reproduce the stable C0 policy; T0 and T1 each have
  one different authenticated creation suite with all-zero before OID, exact after tag-object OID,
  frozen operator, top-level `bypass`/`fail`, and sole active creation-rule `fail`. It persists the
  exact API wrappers/blobs and `ProtocolReviewObjectArchiveV1`, then double-reads both refs again;
  movement/deletion/substitution between reads yields no authority bootstrap.
- [ ] Create the canonical security-attestor records in `campaign.release`, and the policy verifier
  in `campaign.release_broker`; the latter imports those class objects and never redefines,
  subclasses, aliases, or re-exports them. Freeze the common three-row
  `SecurityAttestorCallerPolicyV1`, but implement only the independently callable
  `preflight_rulesets` row here. Its ordered requested/returned permissions are exactly
  `administration:write`, `contents:read`, `metadata:read`; the endpoint policy is GET-only. The
  Actions client contains no App identity/key/token/header/handle, and fake-broker finality tests
  cover no-request, denial, delivery-unknown unrecoverability, permission mismatch, successful
  closure, zero outstanding requests/dispatches/live tokens, and denial of any later mint.
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
- [ ] Immediately before that one secret expression is evaluated, the provider job reruns both the
  universal fresh pair/policy/registry gate and the identical Foundation-owned
  `require_benchmark_sdk_contract` call and requires its literal `None` success return. The
  reusable state job's broker reruns the universal gate immediately before OIDC exchange/App-token
  mint and receive-pack; every later App boundary reruns it before token mint/effect. Static and
  dynamic tests make a temporary read failure produce no credential access, download, mutation, or
  external effect even after environment approval or an earlier winning receipt.
- [ ] `benchmark-dismiss-hold.yml` is no-input `workflow_dispatch` only. A read-only inspector
  first requires exact `refs/heads/main` and the dismissal plan's pre-bound current-main SHA; it
  verifies the caller and reusable workflow bytes against the campaign's C0-derived workflow root
  and derives the one campaign/authority-ref identity only from the accepted plan/authority package.
  It accepts no tag/PR/other branch, campaign/ref/hash input, or latest/by-name authority discovery.
  The inspector reconstructs that exact canonical ref and proves there is exactly one dismissible
  benign hold; a separate read-only `authorize-dismissal` job uses `benchmark-publish` only to
  capture a distinct human approval; and a no-environment state job presents only its canonical
  dismissal request and OIDC to the reusable broker boundary. The fixed
  `tools/benchmark_prepare_hold_dismissal.py` binds the C0 policy, exact hold, source/trigger/eligible
  dismisser numeric identities, expected ref OID, strict plan, and dismissal evidence. The resulting
  `INVALID_EVENT_DISMISSED` self-loop advances transition/state hash while leaving state name, spend,
  inventory, correction, publication, active-exposure, publication-denylist, and active-containment
  roots unchanged and removing only the exact
  hold from the unresolved-hold root. It accepts no hold ID, actor,
  reason, ref, campaign, or event input. The broker performs one exact old-OID lease and the
  workflow no-ops only when the exact dismissal is already canonical.
- [ ] The protected-main required check implements exact `MainFallbackLivenessPolicyV1`: while any
  campaign is nonterminal it verifies all 15 current-main workflow members remain byte-identical to
  C0. The existing `benchmark-evidence.yml` can therefore run without a tag trigger after T0/T1 is
  moved/deleted and request only typed drift STOP, exact open-PR close where required, exposure
  containment, or already-sealed safe-invalid continuation. Tests reject admin-bypassed protection,
  changed current-main bytes, restored-ref live resume, provider/publication/release/correction
  authority, or any new workflow/App/environment/secret.
- [ ] `benchmark-publication-state.yml` is a same-repository `workflow_call` reusable workflow with
  exact job ID `state_writer`, no environment, no checkout, no artifact action, no generated shell,
  no caller-controlled action, and no secret. The entire job contains only GitHub's OIDC bootstrap
  and one full-SHA-pinned, argument-closed broker-client invocation. `id-token: write` is job-scoped;
  `state-cas` is only a reviewed step ID, never an asserted OIDC claim. The broker requires the fully
  qualified caller and called `workflow_ref`/`job_workflow_ref`, both workflow SHAs, exact run/job/
  check-run identity, and the same trigger ref; bare paths or synthetic `workflow_ref@C0` checks fail.
- [ ] Generate workflow caller/ref/actor/event admission from the sole state schema, including the
  exact 24 STOP reasons, strict evidence variants, all literal drift and credential pending/effect/
  final/supplement rows, every publication-containment start/resumption/finality row, protected-main
  fallback rows, hold/exposure/denylist/containment-root gates, and all deny cells. Compare the
  generated rows byte-for-byte with Task 3's exhaustive caller/ref/event table and its separate two-
  row non-event append table; neither test may maintain a permissive hand-written subset.
  Normal callers/reruns require the frozen operator; dismiss-hold requires the plan-selected eligible
  dismisser and matching rerun trigger actor. No wildcard caller, actor, state, reason, ref, or
  environment-reviewer authority is permitted.
- [ ] In `test_workflow_policy.py`, construct one canonical request for each of the three closed
  `AuthorityMutationRequestV1` variants and one request for every admitted event row. Assert the
  reusable job transmits only OIDC plus those canonical bytes, the broker class-bound revalidates the
  matching Runtime-owned source/append object, and predecessor/successor hold, exposure incident,
  exposure progress, publication denylist, and active-containment roots equal the reconstructed
  transition. For containment start, assert the authenticated run SHA becomes the immutable
  `containment_main_oid`; a later current-main resumption requires the exact signed first-parent
  advance proof and cannot rewrite that OIDC identity. For every deny vector, instrument OIDC
  exchange, state-writer mint, publisher/release-finalizer mint, receive-pack, provider secret lookup,
  and network dispatch and require all counters remain zero.
- [ ] Pin the exact ordered 15-path workflow tuple from the approved design and recompute its C0
  member hashes/root. Runtime creates only its four owned workflow files; synthetic C0 fixtures
  supply the eleven later-owned members. Reject missing, extra, reordered, mutable-main, or
  independently supplied workflow roots. Publication Task 13 replaces the synthetic boundary with
  the complete real-byte cross-slice proof.
- [ ] Freeze exactly three pairwise-distinct installed App identities:
  `state_writer`, `publisher`, and `release_finalizer`. The first is usable only inside the external
  state broker; the latter two require `benchmark-publish`. Pre-register the one
  `security_attestor` capability as a downscoped token from the existing release-finalizer
  installation with only `administration:write`, `contents:read`, and `metadata:read`; it is not a
  fourth App. The fixed endpoint/query policy uses the Administration permission only for the
  immutable-Releases settings read and grants no mutation endpoint. Runtime owns the common
  canonical records/client and the `benchmark-preflight.yml` `preflight_rulesets` row; Publication
  Task 10 adds the `benchmark-publish.yml` `postmerge_rule_suite` row, and Publication Task 11 adds
  the `benchmark-release.yml` `release_preparation` row. The later fixed publication job runs with
  `environment: benchmark-publish`, has exact main/ref/plan/OIDC policy, no
  provider key or model/artifact bytes, and release-writing tokens from the same installation omit
  Administration permission.
- [ ] Reject `pull_request_target`, `workflow_run`, cron, arbitrary shell inputs, unpinned actions, third-party actions in the key-bearing job, `set -x`, persisted checkout credentials, and dynamic `uses`.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_workflow_policy.py tests/campaign/test_release_broker.py tests/campaign/test_security_attestor_credential_finality.py tests/test_ci_contract.py -q
```

Expected RED: workflow files are missing.

#### Step 2: Implement the minimal four Runtime-owned workflows

- [ ] Pin every action to a full 40-character commit. Use the repository's existing checkout/setup pins and the approved artifact pins.
- [ ] In `prepare-preflight`, seal the verified tagged registry and emit a receipt-bound
  cycle-free attestation subject, then let only the distinct `security_attestor` job obtain a closed
  safe pass/failure projection through OIDC. A read-only sealing job emits `PREFLIGHT_SEALED` only
  from the passing projection. Its reusable state call gives no repository write permission and
  sends only OIDC plus the canonical request. Before doing so it writes and network-free reloads the
  exact protocol-review archive, stable projections, policy/creation receipts, tag binding, and
  four-field campaign registry, then performs the second exact ref read. The external broker
  independently reruns the universal gate and re-verifies the pair, registry,
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
- [ ] If any post-upload scanner or later phase detects credential material, do not construct an
  ordinary batch STOP. The detector first requests the pending CAS; broker/workflows then admit only
  the frozen complete containment inventory. That CAS sets the active incident ID and pending root
  together; each next expected-OID `CredentialExposureEffectReceiptV1` self-loop preserves both,
  and only the generated phase-exact STOP, strict supplement-union member, release/correction
  invalidation, or bare-state correction intent consumes the final progress root and clears both
  together. A pending/progress CAS is forbidden once publication terminal containment has started;
  later exposure only revokes/rotates externally and resumes that same evidence-preserving
  containment route. Crash recovery re-observes each exact external object/
  idempotency key; it never re-enables provider credentials, artifact downloads, publication, or
  live progression while the pending root is nonnull.
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
  commit, tagged hard-scorer source, hard-score/judge/statistics protocols, and the unchanged
  Evaluation-owned `audit_protocol_sha256: Sha256` from Runtime Task 2's verified peeled-C0 audit
  member, alongside unchanged `audit_sampling_protocol_sha256`,
  `audit_commit_reveal_protocol_sha256`, and `audit_adjudication_protocol_sha256`,
  workflow-inventory root, `campaign_registry_sha256`, complete companion-tag binding, both
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
- [ ] Workflow-policy tests prove no state App/installation ID credential expression or secret
  mapping, private-key name/value, JWT, installation token, publisher credential, or
  release-finalizer write credential occurs anywhere in Actions YAML, tool inputs, artifacts, logs,
  or child environments. Signed safe receipts may retain only preregistered nonsecret identity
  metadata. Every repository
  `GITHUB_TOKEN` remains read-only. Altering the reusable workflow, broker client digest, caller/
  callee identity, mutation request, returned permissions, or Git-identity digest fails before ref
  mutation.
- [ ] Set every authority artifact to `retention-days: 90` and preserve exact API artifact IDs/service digests in successor provenance.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_workflow_policy.py tests/campaign/test_release_broker.py tests/campaign/test_security_attestor_credential_finality.py tests/test_ci_contract.py -q
```

Expected GREEN: PASS; all four Runtime-owned workflows and the external-broker boundary satisfy the
closed policy.

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
git add .github/workflows/benchmark-preflight.yml .github/workflows/benchmark-batch.yml .github/workflows/benchmark-dismiss-hold.yml .github/workflows/benchmark-publication-state.yml src/laconian_eval/campaign/release.py src/laconian_eval/campaign/release_broker.py tools/benchmark_release_broker_client.py tools/benchmark_preflight_stage.py tools/benchmark_prepare_batch.py tools/benchmark_run_batch.py tools/benchmark_post_batch.py tools/benchmark_prepare_hold_dismissal.py tests/campaign/test_release_broker.py tests/campaign/test_security_attestor_credential_finality.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py
git commit -m "ci: add protected benchmark batch workflows"
```

### Task 10: Rehearse pilot bounds and the full offline runtime

**Files:**

- Create: `tests/campaign/test_runtime_synthetic.py`
- Create: `benchmarks/runbooks/public-benchmark.md`
- Modify: `tests/campaign/test_preflight.py`
- Modify: `tests/campaign/test_controller.py`

#### Step 1: RED-test the pilot contract end to end

- [ ] First construct the complete synthetic T0/C0/Rstat/Rjudge/Rsecurity/B0/T1 Git DAG from fixed
  bytes, both active rulesets, the one operator, three reviewer signatures, stable REST/GraphQL/local
  evidence, two unique creation suites, and exact API blobs/wrappers. Pin every raw Git SHA-1 and
  `GitObjectSHA256V1`; network-free import the complete `ProtocolReviewObjectArchiveV1`, run preflight
  twice with different volatile observation metadata, and require the same campaign registry, ID,
  plans, and authority genesis. Delete/move/substitute each tag between the two reads and require zero
  credential, external effect, or authority creation.
- [ ] Import Evaluation Task 14's `tests.benchmark.helpers.build_synthetic_public_campaign` fixture
  and extract its frozen C0 input-package Git blob plus the exact broker-key and delivery-isolation
  subject digests. Parse those bytes only through the Evaluation-owned canonical parser, reconstruct
  the ordered `publisher`, `release_finalizer`, `security_attestor` records from Runtime's sole-owner
  `BrokerSigningKeyV1` and the policy from Runtime's sole-owner
  `BrokerTokenDeliveryIsolationPolicyV1`, and require byte-for-byte equality with the frozen blob.
  Recompute each key leaf/node/root, the policy digest, and the fourteen-member
  `security_evidence` subject root using the object-identical
  `PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1`. Negative vectors delete/reorder/duplicate a key, change
  a policy Boolean, restore the obsolete eleven-member subject tuple, or substitute a copied type or
  canonical encoder; each fails before registry seal, credential lookup, or authority construction.
- [ ] Materialize one shared scenario in both locales, four arms, one repetition, and all three models.
- [ ] Assert 24 generation calls, no generation retries, at most 24 judge calls, no judge retries, and total authorized exposure no greater than `5_000_000` micro-USD.
- [ ] Interrupt after a deterministic request, pack/restore the exact partial capsule, generate a new batch receipt, and resume only the exact suffix.
- [ ] Reject any pilot setting or workflow input that permits a 25th generation or judge attempt.
- [ ] Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_runtime_synthetic.py::test_pilot_is_bounded_to_48_total_attempts -q
```

Expected RED: FAIL because the integrated pilot fixture and its end-to-end runtime wiring are absent.

#### Step 2: Implement the minimal provider-offline runtime wiring and run GREEN

- [ ] Use deterministic fake/replay providers to execute all 36 generation shards through multiple batches, including one 429 retry, one ordinary rejection, one partial checkpoint, and exact suffix resume.
- [ ] Drive every state event from the one generated matrix, including one dismissible hold,
  nondismissible STOP, moved/deleted-tag drift through protected-main fallback, and one post-upload
  credential incident through pending, every inventoried effect, direct final STOP, both strict
  supplement variants, every postmerge/correction consumer class, and complete/invalid publication
  close-versus-merge races. Also rehearse ordinary and write-ambiguity publication terminal
  containment: start commits the monotone denylist and active intent root, crash/restart preserves
  them, premerge and merge-won finality each clear only the matching root, and all constructive
  authority remains denied in between.
  Inject crashes after each exposure CAS/effect and prove exact-root adoption plus zero ordinary work
  while held/pending. Rerun the exact Foundation-owned `require_benchmark_sdk_contract` call and
  universal fresh gates before every synthetic
  credential/effect boundary.
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

Expected GREEN: PASS with the exact 1,440-row runtime, bounded retry, private Runtime capability,
checkpoint-resume, receipt, spend, and STOP assertions above.

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
  broker-minted token has the exact ordered permissions `administration:write`, `contents:read`,
  `metadata:read`, is constrained to the fixed read-only endpoint policy, and never coexists with a
  release-write token.
- [ ] Document the human preflight ceremony in order: configure/record both tag rulesets; registered
  operator creates annotated T0 and its creation receipt; three registry reviewers add/sign only
  their fixed-path statements serially; secret-free verifier builds B0/envelopes/bundle; the same
  operator creates paired annotated T1 and its distinct receipt; archive/import; preflight double
  read; only then pilot dispatch. Document protected-main fallback, exact eligible hold dismissal,
  pending credential-containment recovery, and the rule that a changed object/policy requires a new
  pair and new campaign rather than repair/restored-ref resume.

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
- [ ] The same run first proves exact T0/C0/Rstat/Rjudge/Rsecurity/B0/T1 raw-object vectors,
  stable/API archive reconstruction, two-read policy/receipt binding, stable campaign identity,
  exhaustive hold/drift/exposure root transitions, and SDK/universal precredential gates without
  GitHub/provider network access or secrets.
- [ ] Independent security review confirms the provider job is read-only and the provider secret is
  step-scoped; Actions contains no state App key/token; the reusable OIDC boundary, exact broker
  caller matrix, SHA-1 object construction, and receive-pack old-OID leases match the approved
  design.
- [ ] Independent statistical/evidence review confirms request identities and usage fields match the approved protocol.
- [ ] No live workflow is dispatched by this implementation plan. Live pilot authorization remains a separate maintainer action after the roadmap setup gate.
