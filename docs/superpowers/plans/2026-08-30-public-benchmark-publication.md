# Public Benchmark Publication Slice 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the secret-free, fail-closed publication half of the public three-model benchmark: exact GitHub artifact provenance, provider-evidence inventory sealing, complete and invalid-prefix collection, minimal reviewed publication, checksum-bound result release, and post-`RELEASED` documentation validation.

**Architecture:** Slice 4 consumes immutable campaign authority from Slice 3, sealed generation/hard-score/judge evidence, and the neutral audit/analysis APIs from Slice 2. A non-public `Publication` capability reconstructs current authority in memory and owns the four live Evaluation stages; the seven public replay commands remain offline and non-evidentiary. Repository-owned Python retrieves artifacts only by exact numeric identity, verifies every parent hash, projects one of two disjoint public bundle kinds, and creates deterministic publication and release plans. Repository `GITHUB_TOKEN` permissions remain read-only everywhere. Exactly three pairwise-distinct GitHub Apps carry writes: the external OIDC state broker alone holds the state-writer App and performs expected-OID receive-pack CAS on `benchmark-authority/*`; the publisher App creates/adopts one intent-bound result branch/PR or closes that exact invalidated PR; and the release-finalizer App creates/adopts one intent-bound protected annotated result tag, draft Release, assets, and publish transition. A separately downscoped `security_attestor` job authorizes one short-lived broker-vaulted token from the existing release-finalizer App installation, downscoped to `administration:write`, `contents:read`, and `metadata:read`; the job receives only signed safe receipts, is not a fourth App, and has no repository-write endpoint capability. No App/installation ID is an Actions credential input or secret mapping, and no App private key, installation token, App-auth Authorization header, or opaque token handle reaches a runner. Signed safe receipts may carry only the preregistered nonsecret App/installation identity needed to verify the actor. The closed read client may create a repository `GITHUB_TOKEN` header only for its exact allowlisted read request and must strip it before every redirect or broker call. The separately approved `benchmark-publish` jobs authenticate only to measured external publisher, release-finalizer, and security-attestor brokers by OIDC; those brokers keep token bytes inside their vaults, perform the exact operation-row calls, close every token, and return signed safe receipts. No App receives the provider key or interprets model output.

**Tech Stack:** Python 3.11+, Pydantic v2 strict models, standard-library `hashlib`, `json`, `tarfile`, `urllib`, `zipfile`, Git plumbing, pytest, deterministic property loops, uv, and GitHub Actions pinned to full commit SHAs.

**Approved design:** [Public Three-Model Benchmark Pipeline Design](../specs/2026-08-30-public-three-model-benchmark-design.md), normative design commit `05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`, especially sections 6.5–7.7, 12, 13, 14, and 16.

**Approval record:** Amendment approval metadata is committed at
`d6b147aefb0bab0e64a41541a67e2c1b8f4d00ad`, recording the exact 2026-08-31 approval
`Одобряю amendment 05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126`. Milestone 0 is complete and
Publication is unblocked only by this synchronized plan. The older or implicit contracts are not fallbacks; all experiment,
authority, publication, and evidence invariants in the approved design remain normative.
Any future normative amendment re-blocks every affected Publication task until that amendment is
separately reviewed, recorded, and explicitly approved.

---

## Amendment synchronization contract

This section is mandatory and supersedes any older shorthand later in this plan. No compatibility
alias or partially implemented predecessor contract is allowed.

**Task 9 source-backed audit-authority synchronization (separate approval required):** Publication
consumes the Evaluation amendment of the same name and remains blocked on its separately approved
normative commit. It accepts only the exclusive `benchmark-reviewer-registry-v2` bytes and rejects
the superseded keyless v1 wire. The complete bundle carries and checksum-binds exactly one
`audit/git-object-archive.json`, five source records in logical order at
`audit/pull-request-sources/commitment/{reviewer_id}.json`,
`audit/pull-request-sources/reveal/{reviewer_id}.json`, and
`audit/pull-request-sources/adjudication.json`, two reviewer-ID-ordered source records at
`audit/github-review-sources/{review_id}.json`, and the two already-required
`audit/reviewer-chains/{reviewer_id}.json`. Braces name canonical safe values read from sealed
records; there are exactly two commitment, two reveal, two review-source, and two reviewer-chain
instances. Publication copies these exact bytes and invokes Evaluation Task 13's source-backed
loader, which reparses the bounded Git-object archive and reconstructs PR, commit-signature, and
GitHub-review evidence from retained raw bytes. No audit capability, workflow, adapter, writer, or
validator boundary accepts an ambient Git repository path, Git/ancestry/signature callback,
detached review record, trusted source-success Boolean, caller-supplied repository ID/slug scalar,
mutable badge, or copied fingerprint. The low-level read client's repository value is constructed
internally from provider-derived authority. The pre-merge PR
validator checks only the phase-appropriate append-only prefix, exact candidate delta/signature,
and previously sealed sources; it cannot fabricate a future merge record. The post-merge
`seal_audit` verifier applies the complete retained-source and exact-topology rules. A successful
live API observation is archived evidence, never an authority shortcut. This paragraph supersedes
every later `repository-root`, `git_object_database`, detached `github_review_records`, or
direct-success shorthand for audit seal, collection, planning, validation, replay, or publication.

Publication Task 7's `seal_audit` adapter owns the sole live acquisition. After reconstructing the
current Publication capability and provider authority, its read-only `GitHubReadClient` fetches the
five exact PR records, five pairs of commit-signature REST/GraphQL responses, two exact review
records, and the bounded raw Git commit/tree/blob closure. The client preserves exact response
bytes, request ID, ETag, observation time, API version, endpoint, and TLS endpoint identity long
enough to construct the Evaluation-owned sources/receipts; it exposes no caller URL/parser or raw
authorization header. The adapter verifies the complete in-memory source set before the audit
writer persists it and advances state. Replay and later publication consume only those persisted
bytes. Add `get_pull_request_review` to the closed client and endpoint table; the existing paginated
review-list method may discover an ID but never supplies the exact retained review source.

- [ ] Verify `git show 05e3d7ba86fbaa11a7c9e4072dc1f24039bd7126:docs/superpowers/specs/2026-08-30-public-three-model-benchmark-design.md`
  and governance successor `d6b147aefb0bab0e64a41541a67e2c1b8f4d00ad` before Task 1.
- [ ] Import and class-bound revalidate Runtime-owned campaign authority, registry, state, OIDC,
  hold, drift, credential-exposure, progress-root, mutation-request/receipt, main-liveness-policy,
  and dismissal-policy/plan types. Import workflow inventory, ruleset policy/observations,
  operator registry, tag binding, signature projections/receipts, and object archive only from
  Evaluation-owned `laconian_eval.benchmark.protocol_review`. Publication owns no duplicate.
- [ ] Import and class-bound revalidate Evaluation-owned `ProtocolReviewStatementV1`,
  `VerifiedProtocolAttestationV1`, `ProtocolAttestationBundleV1`, strict REST/GraphQL/local-signature
  projections, and canonical digest helpers. No flattened predecessor alias is allowed.
- [ ] Require the exact serial protected annotated-tag closure
  `T0 -> C0 -> Rstat -> Rjudge -> Rsecurity -> B0 <- T1`, its raw-object SHA-1/SHA-256 values,
  post-tag binding, `CampaignRegistryV1`, `ProtocolReviewObjectArchiveV1`, and one-to-one archived
  safe raw/canonical API response bindings before any publication capability is reconstructed.
- [ ] All authority/evidence models are strict, frozen, `extra="forbid"`, and CanonicalJSONV1-
  validated. Integer fields reject booleans, floats, numeric strings and out-of-range values;
  arrays preserve schema order; only the named self-digest field is omitted from each exact
  domain-separated preimage.

The exact imported Runtime and Evaluation surfaces are:

```python
from laconian_eval.benchmark import (
    CanonicalJSONV1Error,
    canonical_json_v1,
    parse_canonical_json_v1,
)
from laconian_eval.campaign.authority import (
    AuthorityMutationReceiptV1,
    AuthorityMutationRequestV1,
    DraftReleaseReceiptV1,
    FinalReleaseVerificationReceiptV1,
    InitialAssetReceiptsAppendV1,
    InitialDraftReleaseReceiptAppendV1,
    InitialPublishReceiptAppendV1,
    InitialReleaseReceiptAppendV1,
    InitialTagReceiptAppendV1,
    GitHubOidcRunIdentityV1,
    InstallationTokenRevocationReceiptV1,
    PublishReceiptV1,
    ReconstructedAuthorityV1,
    ReleaseAssetReceiptV1,
    ReleaseEffectAuthorizationV1,
    ReleaseEffectResultV1,
    TagReceiptV1,
    append_initial_release_receipt,
)
from laconian_eval.campaign.preflight import (
    CampaignRegistryV1,
    MainFallbackLivenessPolicyV1,
)
from laconian_eval.campaign.state import (
    CampaignEventV1,
    CampaignStateV1,
    CredentialExposureEffectReceiptV1,
    CredentialExposureIncidentEvidenceV1,
    CredentialExposurePendingV1,
    CredentialExposureProgressRootV1,
    CredentialExposureSupplementV1,
    InvalidEventDismissalEvidenceV1,
    InvalidEventDismissalPlanV1,
    InvalidEventHoldV1,
    OrdinaryStopEvidenceV1,
    ProtocolAuthorityDriftEvidenceV1,
    TerminalCredentialExposureConsumptionV1,
)
from laconian_eval.benchmark.protocol_review import (
    ArchivedApiReceiptBindingV1,
    GITHUB_COMMIT_SIGNER_QUERY_V1,
    GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
    GitHubCommitVerificationProjectionV1,
    GitHubSignatureObservationReceiptV1,
    GitHubSignatureProjectionV1,
    InputTagMessageV1,
    ProtocolAttestationTagMessageV1,
    ProtocolAttestationBundleV1,
    ProtocolAttestationTagBindingV1,
    ProtocolBundleBuilderGitIdentityV1,
    ProtocolReviewObjectArchiveV1,
    ProtocolReviewStatementV1,
    PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1,
    ProtocolSubjectKindV1,
    TagCreationRuleSuiteReceiptV1,
    TagOperatorRegistryV1,
    TagRulesetObservationReceiptV1,
    TagRulesetPolicyV1,
    VerifiedProtocolAttestationV1,
    WorkflowInventoryV1,
)
```

Publication imports the canonical JSON trio through `laconian_eval.benchmark` and proves each
package export is the identical object owned by `laconian_eval.benchmark.attachments`; it imports
the subject-kind Literal and immutable role mapping directly from
`laconian_eval.benchmark.protocol_review`. It neither shadows nor reconstructs any of the five
objects. The contract test asserts `is` identity for all five, verifies the immutable security-role
tuple has the exact 14 approved subject kinds, and rejects every Publication-local copy or
compatibility alias.

`GitHubReadClient` is Publication-owned, capability-separated, and read-only. It exposes bounded
methods for repository identity; run/attempt/jobs/approvals/deployments/artifacts; raw Git
ref/tag/commit/tree/blob objects; REST commit verification; the one fixed GraphQL signer query;
current repository rulesets; historical rule suites; PR/check/review/merge observations; current
main containment; immutable-Release settings; and Release/assets. Each method fixes API version,
endpoint/query digest, pagination/body bounds and safe response projection. It never accepts an
arbitrary URL, method, GraphQL document, ref namespace, or response parser. Every REST call is
`GET`; the sole exception is one read-only `POST https://api.github.com/graphql` carrying the
checked-in signer query digest, bounded variables, and no mutation. GitHub GraphQL queries are
transported by POST, so “read-only” describes capability and query semantics, not an inaccurate
HTTP-verb restriction.

`PublicationReceiptV1` is not a second effect receipt. It is a Publication-owned strict
discriminated union alias of `PublicationBranchReceiptV1 | PublicationPRReceiptV1`; the two concrete
records retain distinct schema versions, paths, field sets and digest domains. `CorrectionIntentV1`
is Publication-owned in `campaign.publication`; it is the strict, complete pre-effect correction
record defined in Task 8, including the prior state/authority/phase lineage, both correction plans,
base/head/tree/bundle roots, every branch/PR/tag/draft/asset identity, prior/proposed latest
pointers, both allowed App actors, named pairwise-distinct effect/receipt-CAS idempotency keys, and
the conditional post-release exposure withdrawal/incident/contaminated tag/Release/history roots.
No opaque aggregate plan hash or unordered effect-key bag is permitted. A nonnull consumed hold is valid
only for the exact `RELEASED` nondismissible/exposure/invalidation/drift consumer and its successor clears
that hold atomically.

### Exact 05e3d7ba terminal-containment and credential-finality overlay

This overlay is the implementation delta from the superseded `55b90582` contract to the approved
`05e3d7ba` contract. It supersedes every later reference to a generic
`PublicationInvalidationV1`, a one-stage initial `RejectedResultReleasePlanFixture`, a bare
`RejectedSecurityAttestorTokenRequestFixture`, ordinary direct merge, or a six-row-only post-merge/current-main
exception set. Those names and shapes are negative-test fixtures only; production code must not
export or deserialize them.

Task ownership is fixed:

- Task 8 defines the initial/correction intent and phase-exact terminal record unions.
- Task 9 implements ordinary branch/check/PR delivery resolution and the publisher broker ledger.
- Task 10 implements the protected merge-queue policy, terminal containment, terminal guard,
  dequeue/fence barrier, post-merge admission, and orchestration of Runtime's containment-start
  authority event/wire primitives. It extends Runtime Task 9's canonical security-attestor
  substrate with only the `postmerge_rule_suite` caller row and lifecycle.
- Task 11 implements the preauthorized/attested/executable release graph, extends that same
  attestor substrate with only the `release_preparation` caller row/lifecycle, and implements the
  release-finalizer credential lifecycle. Runtime Task 9 alone bootstraps the shared canonical
  attestor records/client and `preflight_rulesets` row.
- Task 14 exercises every crash, response-loss, pagination, queue, rerun, merge, token-closure, and
  reconciliation-unavailable branch offline.

The Runtime-owned imports below must exist before Slice 4 GREEN. The contract test imports every
name, confirms its defining module, and rejects a Publication-local duplicate:

```python
APPROVED_05E_RUNTIME_IMPORTS = (
    "AnnotatedTagEffectResultsV1",
    "AuthorityRefReconciliationReceiptV1",
    "BrokerCallerAuthorizationReceiptV1",
    "BrokerResponseZeroizationReceiptV1",
    "BrokerSigningIdentityV1",
    "BrokerSigningKeyV1",
    "BrokerTokenClosureDispatchReceiptV1",
    "BrokerTokenDeleteAttemptV1",
    "BrokerTokenDeliveryIsolationPolicyV1",
    "BrokerTokenDenialProbeV1",
    "BrokerTokenRedactedSuccessArchiveV1",
    "BrokerTokenRequestDispatchReceiptV1",
    "BrokerTokenRequestTransportReceiptV1",
    "BrokerTokenSafeSuccessProjectionV1",
    "BrokerTokenUnrecoverabilityReceiptV1",
    "BrokerVaultAuditEntryV1",
    "BrokerVaultAuditLogV1",
    "BrokerVaultAuditPrefixV1",
    "BrokerVaultScopeIdentityV1",
    "CampaignEventMutationSourceV1",
    "HeldResultMergedConsumptionV1",
    "InitialBranchReceiptAppendV1",
    "InitialPRReceiptAppendV1",
    "InitialPublicationReceiptAppendV1",
    "InvalidEventNondismissibilityEvidenceV1",
    "InvalidLineageCredentialExposureSupplementV1",
    "ProtocolDriftCredentialExposureSupplementV1",
    "PublicationMergeDenylistEntryV1",
    "PublicationMergeDenylistV1",
    "PublicationPreContainmentTerminalRouteV1",
    "PublicationTerminalContainmentFinalityV1",
    "PublicationTerminalContainmentIntentV1",
    "PublicationTerminalContainmentPreflightV1",
)
```

The six denylist/containment imports at the end of this tuple are defined exactly once by Runtime in
`laconian_eval.campaign.publication_wire`, because `CampaignStateSchemaV1` and the broker consume
them before Slice 4 exists. Publication Task 10 class-bound revalidates and re-exports none of them;
it imports the identical objects and owns only the effect algorithm and the remaining Publication
evidence records. This direction is a build dependency, not a transfer of publication capability to
Runtime.

Publication owns the following exact records in `campaign.publication`; no compatibility alias or
dict-shaped substitute is allowed. `test_amendment_contract.py` compares this tuple to the module's
stable export manifest, and the focused schema tests compare every model's ordered fields,
discriminators, strict scalar behavior, domain-separated digest, and nested-root equality to the
approved golden vectors:

```python
APPROVED_05E_PUBLICATION_TYPES = (
    "ConflictingPublicationObjectsV1",
    "CorrectionInvalidationV1",
    "InitialPublicationFinalizationV1",
    "InitialPublicationInvalidationV1",
    "PublicationBranchCreateDeliveryResolutionV1",
    "PublicationBranchObservationV1",
    "PublicationBranchRulesetObservationReceiptV1",
    "PublicationBranchRulesetPolicyV1",
    "PublicationCanonicalExternalStateV1",
    "PublicationCheckApiArchiveV1",
    "PublicationCheckRunPageReceiptV1",
    "PublicationCheckRunProjectionV1",
    "PublicationCheckRunsObservationV1",
    "PublicationCheckRunsSemanticSnapshotV1",
    "PublicationCheckSuitePageReceiptV1",
    "PublicationCheckSuiteProjectionV1",
    "PublicationCheckSuiteRunEnumerationV1",
    "PublicationClosedObservationV1",
    "PublicationContainmentMainAdvanceProofV1",
    "PublicationContainmentMergeWonEvidenceV1",
    "PublicationContainmentMergedCandidateV1",
    "PublicationEligibilityDeliveryResolutionSetV1",
    "PublicationFencedWriteAmbiguityV1",
    "PublicationFinalCheckRunsObservationSetV1",
    "PublicationGuardCreateAttemptV1",
    "PublicationGuardUpdateAttemptV1",
    "PublicationHeadCommitObservationV1",
    "PublicationLatestPointerObservationV1",
    "PublicationMainAdvanceCompareReceiptV1",
    "PublicationMainCommitObservationV1",
    "PublicationMainComparePageReceiptV1",
    "PublicationMainFirstParentCommitV1",
    "PublicationMergeEligibilityDeliveryResolutionV1",
    "PublicationMergeEligibilityReceiptV1",
    "PublicationMergeFenceArtifactArchiveReceiptV1",
    "PublicationMergeFenceArtifactEntryV1",
    "PublicationMergeFenceArtifactExtractionReceiptV1",
    "PublicationMergeFenceArtifactInventoryV1",
    "PublicationMergeFenceArtifactPageReceiptV1",
    "PublicationMergeFenceArtifactRedirectReceiptV1",
    "PublicationMergeFenceCheckRunDiscoveryV1",
    "PublicationMergeFenceCheckRunObservationV1",
    "PublicationMergeFenceCheckRunPageReceiptV1",
    "PublicationMergeFenceDecisionArtifactV1",
    "PublicationMergeFenceEvidenceSetV1",
    "PublicationMergeFenceRerunAttemptV1",
    "PublicationMergeFenceRerunTargetProofV1",
    "PublicationMergeFenceWorkflowRunObservationV1",
    "PublicationMergeQueueDequeueAttemptV1",
    "PublicationMergeQueueDequeueTargetProofV1",
    "PublicationMergeQueueInventoryEntryV1",
    "PublicationMergeQueueInventoryObservationV1",
    "PublicationMergeQueueInventoryPageReceiptV1",
    "PublicationMergeQueueObservationV1",
    "PublicationMergeQueuePreflightObservationV1",
    "PublicationMergeQueueTimelinePageReceiptV1",
    "PublicationMergeQueueTimelineReceiptV1",
    "PublicationNoLaterEffectsEvidenceV1",
    "PublicationPRCloseDeliveryResolutionV1",
    "PublicationPRCreateDeliveryResolutionV1",
    "PublicationPRMarkerArchiveV1",
    "PublicationPRMarkerDiscoveryV1",
    "PublicationPRMarkerObservationV1",
    "PublicationPRMarkerPageReceiptV1",
    "PublicationPRStateObservationV1",
    "PublicationPRTerminalDispositionV1",
    "PublicationPlanInvalidationDetailV1",
    "PublicationPlanInvalidationEvidenceV1",
    "PublicationPostGuardVerificationReceiptV1",
    "PublicationProtectedMainObservationV1",
    "PublicationReleaseAuthorizationLedgerObservationV1",
    "PublicationReleaseAuthorizationLedgerSnapshotV1",
    "PublicationReleaseInventoryObservationV1",
    "PublicationReleaseInventoryPageReceiptV1",
    "PublicationRequiredMergeFenceRunReceiptV1",
    "PublicationSuccessFinalityEvidenceV1",
    "PublicationTerminalGuardDeliveryResolutionV1",
    "PublicationTerminalGuardReceiptV1",
    "PublicationTerminalGuardRoundV1",
    "PublicationTerminalGuardSetV1",
    "PublicationTerminalMergeBarrierV1",
    "PublicationTerminalMergeSnapshotV1",
    "PublicationTerminalReconciliationObservationV1",
    "PublicationWriteAmbiguitySetV1",
    "PublicationWriteAmbiguitySubjectV1",
    "PublisherBarrierCredentialDispositionSetV1",
    "PublisherBrokerLedgerEntryV1",
    "PublisherBrokerPhaseLedgerPrefixV1",
    "PublisherBrokerPhaseLedgerV1",
    "PublisherCredentialBrokerPolicyRowV1",
    "PublisherCredentialBrokerPolicyV1",
    "PublisherCredentialDispositionSetV1",
    "PublisherCredentialSubjectV1",
    "PublisherNoMintReceiptV1",
    "PublisherOperationAttemptProjectionV1",
    "PublisherOperationCredentialDispositionV1",
    "PublisherOperationFinalObservationProjectionV1",
    "PublisherOperationRequestDispatchReceiptV1",
    "PublisherOperationTransportProjectionV1",
    "PublisherOperationTransportReceiptV1",
    "PublisherPaginationArchivePrefixV1",
    "PublisherPaginationFailureReceiptV1",
    "PublisherPartialContainmentReadV1",
    "PublisherPartialReconciliationRoundV1",
    "PublisherPartialReconciliationSourceV1",
    "PublisherReadAbortReceiptV1",
    "PublisherReconciliationAttachmentReceiptV1",
    "PublisherReconciliationUnavailableReceiptV1",
    "PublisherTokenClosureProjectionV1",
    "PublisherWriteAmbiguityFenceAttachmentV1",
)
```

Release owns the following records in `campaign.release`; the first two replace the initial use of
`RejectedResultReleasePlanFixture`, while `CorrectionReleaseIntentPlanV1` remains the immutable correction
preauthorization. `RejectedResultReleasePlanFixture` may remain only as a rejected predecessor fixture:

```python
APPROVED_05E_RELEASE_TYPES = (
    "ExecutableResultReleasePlanV1",
    "InitialPreauthorizedResultReleasePlanV1",
    "PartialAnnotatedTagEffectV1",
    "PartialAssetEffectsV1",
    "PostMergeAdmissionSubjectV1",
    "ReleaseAuthorizationLedgerEntryV1",
    "ReleaseDiscoveryMatchProjectionV1",
    "ReleaseDiscoveryPageReceiptV1",
    "ReleaseEffectDeliveryResolutionV1",
    "ReleaseExternalObjectObservationV1",
    "ReleaseExternalObjectsInventoryV1",
    "ReleaseFinalizerBrokerLedgerEntryV1",
    "ReleaseFinalizerBrokerLedgerV1",
    "ReleaseFinalizerBrokerPolicyV1",
    "ReleaseFinalizerCallerV1",
    "ReleaseFinalizerCredentialDispositionV1",
    "ReleaseFinalizerCredentialSubjectV1",
    "ReleaseFinalizerNoRequestReceiptV1",
    "ReleaseFinalizerOperationPolicyRowV1",
    "ReleaseFinalizerOperationSetV1",
    "ReleaseFinalizerTokenClosureProjectionV1",
    "ReleaseLatestPointerObservationV1",
    "ReleaseNoLaterEffectsEvidenceV1",
    "ReleaseOperationDispatchReceiptV1",
    "ReleaseOperationTransportProjectionV1",
    "ReleaseOperationTransportReceiptV1",
    "ReleasePlanInvalidationDetailV1",
    "ReleasePlanInvalidationEvidenceV1",
    "ReleasePreparationEvidenceV1",
    "ReleaseReconciliationAttemptSummaryV1",
    "ReleaseReconciliationObservationSetV1",
    "ReleaseReconciliationObservationV1",
    "ReleaseReconciliationTokenClosureReceiptV1",
    "ReleaseReconciliationUnavailableReceiptV1",
    "SecurityAttestorBrokerLedgerEntryV1",
    "SecurityAttestorBrokerLedgerV1",
    "SecurityAttestorCallerPolicyRowV1",
    "SecurityAttestorCallerPolicyV1",
    "SecurityAttestorCredentialDispositionSetV1",
    "SecurityAttestorCredentialDispositionV1",
    "SecurityAttestorCredentialSubjectV1",
    "SecurityAttestorFailureEvidenceV1",
    "SecurityAttestorGetDispatchReceiptV1",
    "SecurityAttestorGetTransportReceiptV1",
    "SecurityAttestorNoRequestReceiptV1",
    "SecurityAttestorTokenClosureReceiptV1",
)
```

The exact terminal algorithm is constructive and serialized:

1. Reconcile every ordinary branch, PR, eligibility-check, and close/create transport. Any
   response-lost write that cannot be ordered before an authenticated server observation becomes a
   `PublicationWriteAmbiguitySubjectV1`; it never becomes a synthetic ordinary success or absence.
2. Build `PublicationTerminalContainmentPreflightV1` from the complete branch/marker/check/queue/
   release-authorization observations. Build `PublicationTerminalContainmentIntentV1`, append every
   candidate selector to `PublicationMergeDenylistV1`, and seal matching signed publisher-ledger
   and vault prefixes with zero outstanding requests, dispatches, and live tokens.
3. Apply exactly one expected-OID `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` same-state event. It
   performs `active_publication_terminal_containment_root: null -> intent_sha256`, monotonically
   advances `publication_merge_denylist_root_sha256`, switches the publisher broker to
   `terminalizing`, and disables constructive mint. While active, no exposure event, hold,
   publication/correction intent, merge admission, release authorization, or unrelated successor
   is legal.
4. Iterate at most eight `PublicationTerminalGuardRoundV1` rounds. Each round performs one global
   pre-discovery and one global post-discovery, guards every sorted distinct discovered head with a
   publisher-App completed-failure check, and finishes only when the candidate set is stable.
5. Build `PublicationTerminalMergeBarrierV1` from two complete global queue inventories, the exact
   PR queue/timeline observations, every dequeue attempt, and—only when supported by the frozen
   pilot proof—one failed Actions validator fence. An authorized rerun targets the authenticated
   prior success, requires accepted HTTP 201 and `run_attempt == source_run_attempt + 1`, then
   discovers the new check run by complete suite pagination and verifies the bounded artifact chain:
   authenticated artifact pages, authenticated 302 with stripped Authorization/Cookie on the one
   allowlisted Location, bounded ZIP archive, exact safe extraction, and decision JSON.
6. Double-read main and walk its complete first-parent chain. Classify every merged candidate and
   either produce the disjoint premerge finality, ordinary merge-won finality, or write-ambiguity
   merge-won finality. A residual barrier excludes only the already preserved selected merge; no
   other queue/head/PR candidate may disappear from evidence.
7. Apply the route's phase-exact terminal event with
   `PublicationTerminalContainmentFinalityV1`. The CAS preserves the denylist forever and performs
   `active_publication_terminal_containment_root: intent_sha256 -> null`. A late or ambiguous merge
   always takes an invalidation/release-block route and cannot authorize a result release or claim.

`PostMergeAdmissionFailureV1` uses the exact ordered field list in approved design section 12 and
has exactly these failure kinds and schema-ordered predicate vocabulary:

```python
POSTMERGE_FAILURE_KINDS = (
    "ordinary",
    "protocol_authority_drift_race",
    "credential_exposure_race",
    "reconciliation_unavailable",
    "publication_write_ambiguity_merge_race",
)

POSTMERGE_FAILED_PREDICATES = (
    "unexpected_merge_parent",
    "unexpected_merge_method",
    "pr_identity_mismatch",
    "base_oid_mismatch",
    "head_oid_mismatch",
    "result_tree_mismatch",
    "checks_or_approvals_invalid",
    "merge_actor_invalid",
    "historical_rules_invalid",
    "main_containment_invalid",
    "workflow_root_mismatch",
    "observation_inconsistent",
    "publication_prefix_not_admitted_before_merge",
    "publication_close_lost_to_merge",
    "publication_reopened_after_close",
    "protocol_authority_drift",
    "credential_exposure_race",
    "publication_reconciliation_unavailable",
    "publication_write_ambiguity_merge_race",
)
```

The strict source discriminator is
`normal_postmerge_admission|ordinary_terminal_disposition|write_ambiguity`. Normal admission has no
containment fields. Ordinary terminal disposition requires an ordinary merge-won finality and the
exact `PublicationPRTerminalDispositionV1(outcome="already_merged")` for a close/absence race.
Write ambiguity requires the write-ambiguity merge-won finality, an empty signed release-
authorization ledger, and no ordinary disposition/no-later root. Drift and exposure carry only
their class-bound evidence. Reconciliation-unavailable carries the sealed
`PublisherCredentialDispositionSetV1`, `PublisherReconciliationUnavailableReceiptV1`, and signed
empty release-authorization ledger; it never fabricates stable external state or no-later evidence.

Initial terminal writes use exactly one member of
`InitialPublicationInvalidationV1 | InitialPublicationFinalizationV1`. Correction terminal writes
use exactly `CorrectionInvalidationV1` with outcome
`unmerged_invalid|merged_invalid|fenced_write_ambiguity|reconciliation_unavailable`. Each record
copies its phase-exact premerge/merge-won containment finality, before/after active-root values,
successor denylist root, terminal disposition or fenced/unavailable evidence, and the exact initial
receipt append or correction event parent. There is no generic invalidation model and no field bag
shared across incompatible phases.

The initial release graph is one-way and acyclic:

```text
InitialPreauthorizedResultReleasePlanV1
  -> SecurityAttestorReceiptV1(result="pass", attestation_purpose="release_preparation")
  -> ExecutableResultReleasePlanV1(intent_kind="initial")
  -> ResultReleaseIntentV1
  -> ReleaseEffectAuthorizationV1 / effect delivery resolutions / receipt appends
```

The receipt-free preauthorized plan binds the admitted merge, exact result tree, protected annotated
tag bytes/OID, draft metadata, two ordered assets, policies, finalizer identity, workflow root, and
all idempotency keys. The external security-attestor broker binds that root and closes its token
before returning a signed pass or failure record. The executable plan copies immutable effect identities from preauthorization and adds only
the attested observed merge facts. Initial intent embeds the whole executable graph. Correction
uses the already frozen `CorrectionReleaseIntentPlanV1` and original `CorrectionIntentV1`; the
observed correction merge cannot retarget its protected tag.

Publisher, security-attestor, and release-finalizer credentials each use a signed broker policy,
cycle-free credential subject, request-start receipt before every network dispatch, terminal
transport receipt, append-only phase ledger, vault audit log, and exactly one terminal disposition.
Successful or permission-mismatched mint closes through `revoked_204`,
`ambiguous_delivery_then_confirmed_unusable`, or `expired_then_confirmed_unusable`; unknown token
delivery uses the broker-signed unrecoverability proof and zero operation dispatches. Every closure
proves zero same-token dispatch starts after its first decisive boundary. `no_request`, definite
denial, permission mismatch, delivery unknown, stable read, write-ambiguity fenced, and
reconciliation-unavailable are explicit closed variants—not nullable shorthand. A failure to obtain
two complete stable reconciliation passes seals the role-specific unavailable receipt and grants
no release authority.

Each owning task below creates its assigned focused RED file before that task's production or
workflow-YAML change; together those assignments cover exactly:

- `tests/campaign/test_publication_delivery_resolution.py`
- `tests/campaign/test_publication_terminal_containment.py`
- `tests/campaign/test_publication_merge_queue.py`
- `tests/campaign/test_publication_merge_fence.py`
- `tests/campaign/test_publication_terminal_records.py`
- `tests/campaign/test_publisher_credential_finality.py`
- `tests/campaign/test_security_attestor_credential_finality.py`
- `tests/campaign/test_release_authorization_graph.py`
- `tests/campaign/test_release_finalizer_credential_finality.py`
- `tests/campaign/test_reconciliation_unavailable.py`

Run the first missing-type RED, implement one ownership group at a time, and require the complete
focused gate to be GREEN:

```bash
uv run pytest -p no:cacheprovider \
  tests/campaign/test_amendment_contract.py \
  tests/campaign/test_publication_delivery_resolution.py \
  tests/campaign/test_publication_terminal_containment.py \
  tests/campaign/test_publication_merge_queue.py \
  tests/campaign/test_publication_merge_fence.py \
  tests/campaign/test_publication_terminal_records.py \
  tests/campaign/test_publisher_credential_finality.py \
  tests/campaign/test_security_attestor_credential_finality.py \
  tests/campaign/test_release_authorization_graph.py \
  tests/campaign/test_release_finalizer_credential_finality.py \
  tests/campaign/test_reconciliation_unavailable.py -q
```

Expected RED: the first not-yet-owned exact schema/event/import fails before any fake transport
dispatch. Expected GREEN: every listed schema golden vector, every legal route, and every negative
cross-phase/unknown-field/response-loss/token-reuse case passes with the fake transport proving no
unauthorized call.

### Mandatory pre-task contract gate (outside Tasks 1–15)

This synchronization gate is deliberately not a sixteenth implementation task; it is the Slice 4
entry contract that is committed after the owning Slice 1–3 imports are GREEN and before Task 1.

**Files:**
- Modify: `docs/superpowers/plans/2026-08-30-public-benchmark-publication.md`
- Create and own in this task: `tests/campaign/test_amendment_contract.py`

- [ ] **Step 1: Write the RED contract test**

Assert the approved/governance SHAs, exact imported type names, 15-member workflow inventory,
serial Git DAG, state events, caller/ref/event matrix, API endpoint/query allowlist, strict scalar
rejection, and absence of flattened compatibility aliases.

Run:

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_amendment_contract.py -q
```

Expected RED: collection fails only for the first missing approved schema import; it must not fail
for fixture syntax, missing dependency installation, network access, or an unrelated test.

- [ ] **Step 2: Run the pinned-SDK precredential RED gate**

```bash
uv run pytest -p no:cacheprovider \
  tests/test_openai_provider.py::test_benchmark_sdk_contract_fails_before_provider_access \
  tests/benchmark/test_judge.py::test_judge_requires_openai_3_3_1_and_tagged_uv_lock_before_credentials -q
```

Expected RED until the owning slices supply the exact `openai==3.3.1` and C0-derived `uv.lock`
contract. Every mismatch leaves the fake provider call count at zero.

- [ ] **Step 3: Run GREEN after owning imports are synchronized**

```bash
uv run pytest -p no:cacheprovider tests/campaign/test_amendment_contract.py -q
uv run pytest -p no:cacheprovider tests/campaign/test_state_schema.py \
  tests/campaign/test_state.py tests/campaign/test_state_broker.py \
  tests/campaign/test_authority_git.py tests/campaign/test_preflight.py -q
```

Expected GREEN: PASS; the generated transition/caller matrices contain no wildcard, unreachable or
table-only edge, and all approved schema roots reproduce independently.

- [ ] **Step 4: Commit the synchronized executable contract once GREEN**

```bash
git add tests/campaign/test_amendment_contract.py
git commit -m "test: lock approved benchmark amendment contract"
```

Never use `git add .`, never create a compatibility shim, and do not combine plan synchronization
with production implementation. This task owns this test and no later task recreates it.

### Closed authority/effect overlay for every task below

The following generated matrix is part of the implementation contract and overrides every later
single-root or phase-only shorthand. Before any authority mutation, credential mint/map/use,
provider call, artifact access/download, publisher or security-attestor effect, release,
correction, documentation, site, release-note, presentation, or social effect, the caller performs
fresh double reads of both protected refs, the stable two-ruleset policy projection, the companion
tag binding and campaign registry, and proves the workflow bytes against the 15-member C0
`WorkflowInventoryV1`. A transient or inconsistent read causes no token, effect, artifact access,
or state change.

Ordinary edges require both `unresolved_hold_root` and
`active_credential_exposure_pending_root` to be null. The only atomic nonnull-hold consumers are
`INVALID_EVENT_DISMISSED`; premerge `PERMANENT_STOP` for `invalid_event_nondismissible`,
`credential_exposure`, or `protocol_authority_drift`; `RESULT_MERGED -> RELEASE_PLAN_INVALIDATED`;
and `RELEASED -> CORRECTION_INTENT_AUTHORIZED` with the exact nondismissible, exposure,
invalidation, or protocol-drift discriminator/evidence. Each binds the predecessor hold and clears it in the same
expected-OID CAS. `INVALID_PREFIX_SEALED` and every other publication, promotion, release,
correction, safe-finalization, documentation, or social edge require both roots null.

`INVALID_EVENT_HELD` is a broker-owned self-loop only in the spec's exact hold-eligible states and
only after authenticated identity/transport succeeds but event schema/parent/hash/edge validation
fails; pre-auth garbage, transient reads, and benign stale siblings are audit denials only. While a
hold exists, only `INVALID_EVENT_DISMISSED`, its exact nondismissible STOP, the typed emergency
credential/drift STOP consumers, or the two postmerge consumers above are reachable. The dismissal
uses the C0-frozen `InvalidEventDismissalPlanV1`, caller-discriminated eligible dismisser OIDC
identity, signed `InvalidEventDismissalEvidenceV1`, and consumes exactly one hold.

Credential exposure is always two phase: an expected-OID `CREDENTIAL_EXPOSURE_PENDING` self-loop
atomically installs `CredentialExposurePendingV1`, the provisional denylist and initial
`CredentialExposureProgressRootV1`; then each inventoried idempotent containment action is adopted
by an ordinal, predecessor-bound `CREDENTIAL_EXPOSURE_EFFECT_RECORDED` self-loop; only a complete
terminal chain permits `PERMANENT_STOP(reason=credential_exposure)` or, from an already stopped
lineage, `CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`. The terminal evidence binds and consumes the
active progress root, clears the active fields, installs the permanent denylist, and includes the
publisher-only exact PR-close receipt when the parent was `COMPLETE_PUBLICATION_PR_OPEN`. A merge
race switches to the approved postmerge invalidation/correction exposure route. Exposure
containment takes precedence over simultaneous protocol drift; drift evidence is bound into the
incident and no intervening drift-only STOP is allowed.

The protected-current-main exceptions are closed to: drift containment; exposure pending,
progress, final STOP/supplement (including `benchmark-publish` only for an open publication PR and
its publisher-only close); and safe-invalid continuation for any sealed STOP/BUDGET lineage. They
require current protected main, fresh authenticated drift/current-rule observations, and
byte-identical C0 caller/reusable workflow members under the frozen
`MainFallbackLivenessPolicyV1`; no other publish event gains this exception. Repository admission
must keep those fallback members unchanged while a campaign is nonterminal. Platform-admin bypass
is a recorded trust limitation, not a recovery mechanism.

### Exact protocol and API evidence overlay

Preflight and every downstream builder consume the serial protected closure
`T0 -> C0 -> Rstat -> Rjudge -> Rsecurity -> B0 <- T1`, the single companion
`ProtocolAttestationTagBindingV1`, `CampaignRegistryV1`, and a
`ProtocolReviewObjectArchiveV1` containing exact raw bytes of every closure object plus strict
one-to-one API receipt/blob bindings. Network-free replay reconstructs all Git objects and every
safe response digest from archived response-body bytes and canonical projection bytes; those API
bytes remain GitHub-origin observations, not independent cryptographic provenance.

The two applicable tag rulesets are exact and disjoint: the creation-authorizer targets T0/T1,
contains only `creation`, and has the sole frozen operator `User` bypass with `always`; the
immutability ruleset targets the same patterns, contains only `update` and `deletion`, and has no
bypass actors. Historical creation-suite evidence maps the raw GitHub suite top-level
`result="bypass"` exactly to stable receipt `overall_result="bypass"`, retains stable
`evaluation_result="fail"`, requires all-zero `before_sha`, exact annotated-tag `after_sha`, the registered
actor, and exactly one per-rule projection whose source is the sealed creation ruleset,
`enforcement=active`, `rule_type=creation`, and `result=fail`. Main merge suites instead map raw
top-level `result="pass"` to their stable `overall_result="pass"`, require every applicable
per-rule `result="pass"`, and permit no bypass. Volatile names/details/request metadata remain only in the
safe archived raw receipt blobs.

All new records and nested variants use strict CanonicalJSONV1 models and their exact approved
domain-separated preimages; no Publication model accepts permissive `int`, `bool`, float, numeric
string, unknown key, reordered semantic array, omitted required field, or self-inclusive digest.

Write the amendment matrix/archive fixtures first and run:

```bash
uv run pytest -p no:cacheprovider \
  tests/campaign/test_amendment_contract.py \
  tests/benchmark/test_protocol_review.py \
  tests/campaign/test_state_broker.py -q
```

Expected RED: the first absent exact schema/event/archive binding fails and the fake transport has
zero unauthorized calls. After the owning prerequisite implementations, the same command is GREEN
with every referenced generated state/caller row reached and two network-free protocol-review
archive imports producing identical roots. Publication crash recovery remains owned by Task 14 and
is not invoked before that test file exists.

---

## Slice boundary and prerequisite contract

Do not begin this slice until the following imports and focused suites are green. Slice 4 does not
reimplement campaign state, provider execution, spend accounting, scoring, inference, sampling, or
statistical estimators; it composes their neutral APIs under campaign authority.

Required Slice 3 interfaces:

```python
from laconian_eval.campaign.authority import (
    DraftReleaseReceiptV1,
    FinalReleaseVerificationReceiptV1,
    InitialAssetReceiptsAppendV1,
    InitialDraftReleaseReceiptAppendV1,
    InitialPublishReceiptAppendV1,
    InitialReleaseReceiptAppendV1,
    InitialTagReceiptAppendV1,
    GitHubOidcRunIdentityV1,
    InstallationTokenRevocationReceiptV1,
    PublishReceiptV1,
    ReconstructedAuthorityV1,
    ReleaseAssetReceiptV1,
    ReleaseEffectAuthorizationV1,
    ReleaseEffectResultV1,
    TagReceiptV1,
    append_initial_release_receipt,
    require_ordinary_effect_gate,
)
from laconian_eval.campaign.artifact_wire import ArtifactEnvelopeV1, UploadAuthorizationV1
from laconian_eval.campaign.runtime import Runtime
from laconian_eval.campaign.preflight import CampaignRegistryV1
from laconian_eval.campaign.spend import SpendLedgerV1
from laconian_eval.campaign.state import (
    CampaignEventV1,
    CampaignStateV1,
    InvalidEventHoldV1,
    TerminalCredentialExposureConsumptionV1,
)
from laconian_eval.campaign.models import GitHubAppInstallationIdentityV1
```

`Publication`, `_reconstruct_verified_publication`, and the live evaluation-stage capability are
Slice 4 outputs created by Task 7 below; they are not Slice 3 prerequisites.

Required sealed-evidence interfaces from the earlier slices:

```python
from laconian_eval.benchmark.aggregation import aggregate_verified_evidence
from laconian_eval.benchmark.hard_score import (
    HardScoreRequestSetV1,
    verify_hard_score_request_set,
)
from laconian_eval.benchmark.judge import (
    JudgeAttachmentV1,
    JudgeRequestAttachmentV1,
    verify_judge_attachment,
    verify_judge_request_attachment,
)
from laconian_eval.benchmark.provider_evidence import (
    VerifiedBenchmarkProviderEvidenceV1,
    build_audit_population,
    load_verified_benchmark_provider_evidence,
)
from laconian_eval.benchmark.audit_sampling import (
    VerifiedAuditSampleRootV1,
    load_verified_audit_sample_root,
    select_audit_sample,
    write_audit_sample_root,
)
from laconian_eval.benchmark.reporting import (
    BootstrapArtifactV1,
    VerifiedAnalysisEvidenceV1,
    VerifiedAuditEvidenceV1,
    analyze_campaign,
    build_bootstrap_artifact,
    load_verified_analysis_evidence,
    load_verified_audit_evidence,
    write_analysis_evidence_root,
    write_audit_evidence_root,
)
from laconian_eval.capsule.seal_models import SealV1, capsule_sha256
from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2, load_verified_scored_capsule
from laconian_eval.capsule.sharding import ShardPlanV1
```

Required command before Task 1:

```bash
uv sync --all-extras --locked
uv run pytest \
  tests/campaign/test_preflight.py \
  tests/campaign/test_artifact_wire.py \
  tests/campaign/test_state.py \
  tests/campaign/test_authority.py \
  tests/campaign/test_spend.py \
  tests/capsule/test_sharding.py \
  tests/capsule/test_seal_models.py \
  tests/capsule/test_sidecars.py \
  tests/capsule/test_verify_sealed.py \
  tests/benchmark -q
```

Expected: PASS. A missing import or failing prerequisite test blocks Slice 4; fix it in its owning
slice rather than adding compatibility aliases here.

Slice 2 exposes exactly seven offline/non-evidentiary `laconian-benchmark` replay commands with
`allow_abbrev=False`: `hard-score`, `prepare-judge`, `seal-judge`, `sample-audit`, `seal-audit`,
`analyze`, and `verify`. No live workflow invokes them. The exact live ownership tuple is:

```text
laconian_eval.campaign.runtime.Runtime.hard_score
laconian_eval.campaign.runtime.Runtime.prepare_judge
laconian_eval.campaign.runtime.Runtime.seal_judge
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.sample_audit
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.seal_audit
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.analyze
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.verify
```

The only constructors are private
`laconian_eval.campaign.runtime._reconstruct_verified_runtime` and
`laconian_eval.campaign.publication._reconstruct_verified_publication`. They accept authority-
derived in-memory capabilities; no capability, wrapper, or alleged expectation is serialized into
an artifact, provider index, command line, workflow input, or environment value.

## Locked Slice 4 interfaces

The following public names and signatures are normative for this plan:

```python
from pathlib import Path
from typing import Annotated

from pydantic import Field

from laconian_eval.campaign.artifacts import (
    VerifiedArtifactArchive,
    VerifiedArtifactRootV1,
    fetch_exact_artifact,
    materialize_verified_artifact_root,
)
from laconian_eval.campaign.collector import (
    collect_complete_bundle,
    finalize_invalid_prefix,
)
from laconian_eval.campaign.github_records import (
    ExactArtifactLocatorV1,
    GitHubReadClient,
)
from laconian_eval.campaign.provider_evidence import (
    EvidenceInventoryV1,
    seal_provider_evidence_inventory,
)
from laconian_eval.campaign.public_projection import (
    BundleSealV1,
    PublicProjectionPolicyV1,
    verify_public_projection,
)
from laconian_eval.campaign.publication import (
    BlockedReleaseObjectsV1,
    CorrectionAssetIdempotencyV1,
    CorrectionCredentialExposureWithdrawalV1,
    CorrectionEffectActorsV1,
    CorrectionFinalizationV1,
    CorrectionIntentV1,
    CorrectionInvalidationV1,
    CorrectionLineageV1,
    CorrectionMergeReceiptV1,
    CorrectionPhaseLineageV1,
    CorrectionPublicationIdempotencyKeysV1,
    CorrectionPublicationIntentPlanV1,
    CorrectionInvalidationIntentParentV1,
    CorrectionInvalidationPublicationReceiptParentV1,
    CorrectionInvalidationParentV1,
    CorrectionPublicationReceiptV1,
    CorrectionReleaseAssetV1,
    CorrectionReleaseIdempotencyKeysV1,
    CorrectionReleaseIntentPlanV1,
    CorrectionReleaseReceiptV1,
    CorrectionTagReceiptV1,
    DriftHeldReleasedConsumptionV1,
    ExposureHeldReleasedConsumptionV1,
    HeldReleasedConsumptionV1,
    GitHubHumanAccountObservationV1,
    InvalidationHeldReleasedConsumptionV1,
    LatestPublicationPointerV1,
    NondismissibleHeldReleasedConsumptionV1,
    InitialPublicationFinalizationV1,
    InitialPublicationInvalidationV1,
    Publication,
    PublicationBranchReceiptV1,
    PublicationClosePlanV1,
    PublicationCloseReceiptV1,
    PublicationIntentV1,
    PublicationPlanV1,
    PublicationMergeReceiptV1,
    PublicationPRReceiptV1,
    PublicationReceiptV1,
    ProposedLatestPointerConstraintV1,
    build_correction_publication_plan,
    build_correction_release_intent_plan,
    build_publication_plan,
    validate_publication_pull_request,
)
from laconian_eval.campaign.release import (
    ExecutableResultReleasePlanV1,
    InitialPreauthorizedResultReleasePlanV1,
    ReleaseEffectDeliveryResolutionV1,
    ReleaseFinalizerCredentialDispositionV1,
    ReleaseFinalizerOperationSetV1,
    ReleasePreparationEvidenceV1,
    ReleaseReconciliationUnavailableReceiptV1,
    ResultReleaseIntentV1,
    SecurityAttestorCallerPolicyV1,
    SecurityAttestorCredentialDispositionSetV1,
    SecurityAttestorFailureEvidenceV1,
    SecurityAttestorReceiptV1,
    build_correction_release_plan,
    build_executable_result_release_plan,
    build_initial_preauthorized_result_release_plan,
    build_result_release_intent,
)
```

Every writer uses exclusive creation under a caller-owned empty staging directory, fsyncs files and
directories, verifies the complete result, and publishes by atomic rename. Every verifier accepts
explicit paths or exact IDs; none searches for a newest artifact, infers a campaign from a branch
name, or follows a mutable ref.

## Locked publication state contract

The generated `CampaignStateSchemaV1` remains the sole transition source; this plan may not define a
parallel enum. Publication tests render and verify these exact disjoint paths:

```text
BUNDLE_COLLECTED
  -- PUBLICATION_INTENT_AUTHORIZED(bundle_kind=complete) --> BUNDLE_COLLECTED
  -- COMPLETE_PUBLICATION_PR_OPENED --> COMPLETE_PUBLICATION_PR_OPEN
COMPLETE_PUBLICATION_PR_OPEN
  -- RESULT_MERGED + PostMergeAdmissionEvidenceV1 --> RESULT_MERGED
  -- RESULT_MERGE_INVALIDATED + PostMergeAdmissionFailureV1 --> RELEASE_BLOCKED
  -- COMPLETE_PUBLICATION_PLAN_INVALIDATED + exact close receipt --> BUNDLE_COLLECTED

INVALID_FINALIZED
  -- PUBLICATION_INTENT_AUTHORIZED(bundle_kind=invalid_prefix) --> INVALID_FINALIZED
  -- INVALID_PUBLICATION_PR_OPENED --> INVALID_PUBLICATION_PR_OPEN
INVALID_PUBLICATION_PR_OPEN
  -- INVALID_PREFIX_MERGED + PostMergeAdmissionEvidenceV1 --> INVALID_PREFIX_MERGED
  -- INVALID_PREFIX_MERGE_INVALIDATED + PostMergeAdmissionFailureV1 --> INVALID_PREFIX_MERGED_INVALID
  -- INVALID_PUBLICATION_PLAN_INVALIDATED + exact close receipt --> INVALID_FINALIZED
```

The generated schema also includes, without a Publication-local enum, the approved self-loop
events `INVALID_EVENT_HELD`, `INVALID_EVENT_DISMISSED`, `CREDENTIAL_EXPOSURE_PENDING`,
`CREDENTIAL_EXPOSURE_EFFECT_RECORDED`, and `PUBLICATION_TERMINAL_CONTAINMENT_STARTED`; the
exhaustive ordinary `PERMANENT_STOP` reason/evidence union; terminal
`CREDENTIAL_EXPOSURE_SUPPLEMENT_RECORDED`; and the exact drift/exposure/hold/containment consumers
described in the authority/effect overlay. Every state contains a nonnull monotone
`publication_merge_denylist_root_sha256` and nullable
`active_publication_terminal_containment_root`. Tests generate this table and the literal
caller/current-parent/ref/reason/evidence matrix from Runtime's schema, exercise every row, and
assert no wildcard, unreachable row, implicit delegation, second unresolved hold, containment-
root overwrite, denylist deletion, or transition that fails to consume its bound predecessor root.
`benchmark-publish` receives pending/progress/final credential grants at
`COMPLETE_PUBLICATION_PR_OPEN`; only its publisher App may perform the close effect. The same frozen
workflow receives the exact protected-current-main containment-start and terminal-consumer rows for
active initial/correction publication prefixes. The other incident-capable workflow callers receive
only their exact state/ref rows.

`COMPLETE_PUBLICATION_PR_OPEN` and `INVALID_PUBLICATION_PR_OPEN` are distinct schema values; an
untyped publication-open alias, cross-kind open/close/merge events, and missing bundle
discriminators are rejected. `INVALID_PREFIX_MERGED` and `INVALID_PREFIX_MERGED_INVALID` are terminal and accept no
release, correction, documentation, website, release-note, or social-promotion event.

## File map

### Create

- `src/laconian_eval/campaign/github_records.py`: strict GitHub repository, workflow-run,
  run-attempt, job, deployment, approval, artifact, and exact-locator records plus the sole
  Publication-owned, capability-separated `GitHubReadClient`; it imports the Runtime-owned
  `ArtifactEnvelopeV1` wire type rather than redefining it.
- `src/laconian_eval/campaign/artifacts.py`: exact-ID REST retrieval, bounded outer-ZIP handling,
  service-digest checking, and internal envelope verification.
- `src/laconian_eval/campaign/provider_evidence.py`: read-only generation/hard-score/judge/spend
  completeness verifier and `EvidenceInventoryV1` seal.
- `src/laconian_eval/campaign/public_projection.py`: public file roles, allowlists, secret scanning,
  Markdown neutralization, checksums, and `BundleSealV1`.
- `src/laconian_eval/campaign/collector.py`: separate complete-bundle and invalid-prefix writers.
- `src/laconian_eval/campaign/publication.py`: created in Task 7 with the non-public
  `_reconstruct_verified_publication` constructor and `Publication.campaign.evaluation_stage`
  capability; Tasks 8–10 modify it with `PublicationPlanV1`, deterministic Git tree/commit
  construction, the one pre-effect correction intent binding both publication and release plans,
  strict held-`RELEASED` consumer union, sole ownership of phase-exact initial/correction terminal
  records, ordinary delivery resolution, terminal guard/containment/barrier/fence evidence,
  byte-copy publication records, and PR/admission validators.
- `src/laconian_eval/campaign/publisher_broker.py`: exact publisher operation-row policy, signed
  safe transport/closure/vault-ledger projections, and verifier; no token-bearing implementation is
  importable by Actions code.
- `src/laconian_eval/campaign/docs_gate.py`: post-`RELEASED` synchronized documentation/social
  provenance validation.
- `tools/benchmark_minimal_publisher.py` and `tools/benchmark_publisher_broker_client.py`:
  secret-free deterministic publisher package builder and OIDC broker client.
- `tools/benchmark_release_finalizer.py`: secret-free deterministic release request builder.
- `tools/benchmark_release_inventory_monitor.py`: externally scheduled, repository-read-only exact
  released-object inventory verifier.
- `ops/benchmark-release-inventory-monitor.toml`: exact external deployment/cadence/egress contract.
- `docs/runbooks/benchmark-release-inventory-monitor.md`: alert triage and reviewed defect-PR runbook.
- `tools/benchmark_prepare_correction.py`: fixed correction-bundle and correction-plan preparation
  executable.
- `tools/benchmark_sample_audit_stage.py`: fixed authority-bound audit-sample executable.
- `tools/benchmark_seal_audit_stage.py`: fixed authority-bound audit-sealing executable.
- `tools/benchmark_analyze_stage.py`: fixed authority-bound analysis executable.
- `tools/benchmark_verify_stage.py`: fixed authority-bound analysis verification executable.
- `tools/validate_publication_pr.py`: trusted-base PR validation entry point.
- `tools/validate_audit_pr.py`: trusted-base commitment/reveal/adjudication PR validation entry point.
- `tools/validate_result_docs.py`: trusted-base post-release documentation validation entry point.
- `tests/campaign/publication_helpers.py`: deterministic complete, invalid-prefix, Git, and GitHub
  fixture builders.
- `tests/campaign/fake_github.py`: bounded in-memory GitHub REST transport with recorded calls.
- `tests/campaign/test_github_records.py`
- `tests/campaign/test_artifacts.py`
- `tests/campaign/test_provider_evidence.py`
- `tests/campaign/test_public_projection.py`
- `tests/campaign/test_complete_collector.py`
- `tests/campaign/test_invalid_prefix_finalizer.py`
- `tests/campaign/test_publication_plan.py`
- `tests/campaign/test_minimal_publisher.py`
- `tests/campaign/test_publication_pr.py`
- `tests/campaign/test_publication_delivery_resolution.py`
- `tests/campaign/test_publication_terminal_containment.py`
- `tests/campaign/test_publication_merge_queue.py`
- `tests/campaign/test_publication_merge_fence.py`
- `tests/campaign/test_publication_terminal_records.py`
- `tests/campaign/test_publisher_credential_finality.py`
- `tests/campaign/test_release_authorization_graph.py`
- `tests/campaign/test_release_finalizer_credential_finality.py`
- `tests/campaign/test_reconciliation_unavailable.py`
- `tests/campaign/test_audit_pr.py`
- `tests/campaign/test_result_release.py`
- `tests/campaign/test_docs_gate.py`
- `tests/campaign/test_publication_capability.py`
- `tests/campaign/test_evaluation_stage.py`
- `tests/campaign/evaluation_stage_contract.py`
- `tests/campaign/test_publication_workflows.py`
- `tests/campaign/test_publication_reconstruction.py`
- `.github/workflows/benchmark-hard-score.yml`
- `.github/workflows/benchmark-evidence.yml`
- `.github/workflows/benchmark-audit.yml`
- `.github/workflows/benchmark-analysis.yml`
- `.github/workflows/benchmark-collect-complete.yml`
- `.github/workflows/benchmark-finalize-invalid.yml`
- `.github/workflows/audit-pr-validate.yml`
- `.github/workflows/benchmark-publish.yml`
- `.github/workflows/publication-pr-validate.yml`
- `.github/workflows/benchmark-release.yml`
- `.github/workflows/benchmark-docs-validate.yml`

### Modify

- `src/laconian_eval/campaign/__init__.py`: export only stable Slice 4 record types.
- `src/laconian_eval/campaign/release.py`: created by Runtime Task 9 with canonical
  security-attestor records; Publication Tasks 10–11 add the postmerge/release-preparation records,
  receipt-free/executable plans, initial intent, release assets, finalizer ledgers/dispositions, and
  reconciliation evidence without redefining Runtime-owned effect/append wires.
- `src/laconian_eval/campaign/release_broker.py`: created by Runtime Task 9 with the
  `preflight_rulesets` verifier; Publication Tasks 10–11 add only the postmerge,
  release-preparation, and release-finalizer policy rows. Raw token-bearing vault code remains
  external.
- `tools/benchmark_release_broker_client.py`: secret-free OIDC client created by Runtime Task 9 and
  extended only for the exact later policy rows.
- `tests/campaign/test_release_broker.py` and
  `tests/campaign/test_security_attestor_credential_finality.py`: created by Runtime Task 9 and
  extended by their exact postmerge/release-preparation owners.
- `.github/workflows/benchmark-publication-state.yml`: created by Runtime Task 9; Publication Task 7
  adds the audit/analysis/collection caller rows and Task 10 adds publication/admission callers.
- `tests/campaign/test_workflow_policy.py`: extend the repository-wide workflow security contract.
- `tests/test_public_contract.py`: extend the stable export and live/offline ownership contract
  without adding a public campaign CLI.
- `tests/test_ci_contract.py`: include Slice 4 workflow names in the repository workflow contract.
- `benchmarks/runbooks/public-benchmark.md`: extend the Slice 3 operator runbook with collection,
  publication approval, merge, release, recovery, and post-release procedures.
- `CONTRIBUTING.md`: document the result-PR and post-release documentation review gates.
- `evals/README.md`: document reconstruction from a committed complete bundle.
- `SECURITY.md`: document public Actions artifacts, credential-incident handling, and output
  non-execution.

Do not modify `.gitignore`: local smoke output remains ignored. The minimal publisher uses
`git add --force -- benchmarks/results/{campaign_id}` only after verifying the sealed fixed-path
inventory.

## Canonical published trees

The complete collector may create only this role-addressed tree under its staging root:

```text
bundle.json
campaign/registry.json
campaign/state.json
campaign/spend-ledger.json
campaign/artifact-inventory.json
campaign/plan-index.json
provenance/input-tag.json
provenance/workflows.jsonl
provenance/reviewer-attestations.jsonl
provenance/repository-trust-boundary.json
provenance/repository-trust-boundary-signature.json
inputs/manifests/gpt-5.6-luna.json
inputs/manifests/gpt-5.6-sol.json
inputs/manifests/gpt-5.6-terra.json
inputs/price-snapshot.json
inputs/campaign-seed.json
inputs/reviewers.yaml
inputs/protocol-reviewers.yaml
inputs/cases/response.yaml
inputs/arms/baseline.txt
inputs/arms/concise.txt
inputs/arms/caveman/SKILL.md
inputs/arms/caveman/SOURCE.md
inputs/arms/caveman/LICENSE.txt
inputs/arms/if/SKILL.md
inputs/protocols/hard-score.json
inputs/protocols/judge.json
inputs/protocols/statistics.json
inputs/protocols/audit.json
inputs/protocols/retry.json
inputs/protocols/checkpoint.json
inputs/protocols/publication.json
generation/{model_id}/{scenario_uid}/capsule.tar
generation/{model_id}/{scenario_uid}/capsule.tar.sha256
hard-score/{model_id}/{scenario_uid}/request-set.json
judge-requests/{model_id}/{scenario_uid}/attachment.json
judge/{model_id}/{scenario_uid}/attachment.json
audit/audit-evidence.json
audit/population-attachment.json
audit/population.jsonl
audit/sample-manifest.json
audit/blind-packet.json
audit/git-object-archive.json
audit/pull-request-sources/commitment/{reviewer_id}.json
audit/pull-request-sources/reveal/{reviewer_id}.json
audit/pull-request-sources/adjudication.json
audit/commitments/{reviewer_id}.json
audit/reveals/{reviewer_id}/reveal.json
audit/reveals/{reviewer_id}/labels.jsonl
audit/reviewer-chains/{reviewer_id}.json
audit/adjudication-core.json
audit/adjudication.json
audit/signoffs/{reviewer_id}.json
audit/github-review-sources/{review_id}.json
audit/github-review-records/{review_id}.json
audit/metrics.json
analysis/analysis-evidence.json
analysis/analysis.json
analysis/bootstrap.json
analysis/report.md
analysis/checksums.json
report.md
limitations.md
REPRODUCE.md
checksums.sha256
```

`{model_id}`, `{scenario_uid}`, and `{reviewer_id}` denote canonical values taken from sealed
records, validated as single safe path components, and sorted by UTF-8 bytes. `{review_id}` is the
canonical base-10 rendering of a strict positive GitHub review ID, without a leading zero. Braces
in this plan denote validated grammar variables, never an implementation instruction to invent a
path.

The invalid-prefix finalizer may create only:

```text
bundle.json
campaign/registry.json
campaign/state.json
campaign/spend-ledger.json
campaign/completed-prefix.json
campaign/missing-suffix.json
campaign/incident.json
provenance/input-tag.json
provenance/safe-workflows.jsonl
provenance/repository-trust-boundary.json
provenance/repository-trust-boundary-signature.json
limitations.md
REPRODUCE.md
checksums.sha256
```

It must reject generation output, hard-score, judge, audit, analysis, report, pairwise comparison,
effect estimate, confidence interval, or model-ranking members.

---

### Task 1: Add strict GitHub execution and artifact records

**Files:**
- Create: `src/laconian_eval/campaign/github_records.py`
- Create: `tests/campaign/test_github_records.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

- [ ] **Step 1: Write the failing exact-record round-trip test**

Add a fixture with repository ID `1343493800`, workflow run ID `41000000001`, run attempt `2`,
job ID `99000000001`, deployment ID `6100000001`, artifact ID `9700000001`, and full 40-character
Git object IDs. Assert canonical field order and rejection of booleans, floats, zero IDs, unknown
fields, a non-`workflow_dispatch` event, a branch ref on a tag-only caller row or unbound main
branch, a non-SHA action workflow hash, an
environment without deployment/approval, and deployment data on a secret-free artifact.

Use this exact model interface:

```python
class ExactArtifactLocatorV1(CapsuleModel):
    schema_version: Literal["1"]
    repository_id: StrictPositiveInt
    workflow_run_id: StrictPositiveInt
    run_attempt: StrictPositiveInt
    job_id: StrictPositiveInt
    job_name: BoundedNonBlankString
    batch_attempt_id: UUID4 | None
    event: Literal["workflow_dispatch"]
    input_ref: BoundedNonBlankString
    input_tag_object_sha: GitObjectId
    input_commit_sha: GitObjectId
    workflow_path: RelativePosixPath
    workflow_sha256: Sha256
    environment: Literal["benchmark-live", "benchmark-publish"] | None
    deployment_id: StrictPositiveInt | None
    approval_actor_id: StrictPositiveInt | None
    approval_actor_login: BoundedNonBlankString | None
    artifact_id: StrictPositiveInt
    artifact_name: BoundedNonBlankString
    artifact_digest: Sha256
    artifact_created_at_utc: CanonicalTimestamp
    inner_archive_byte_length: StrictNonNegativeInt
    inner_archive_sha256: Sha256
    upload_authorization: UploadAuthorizationV1 | None
    envelope_sha256: Sha256
    payload_kind: Literal["canonical_file", "root_ustar"]
    payload_name: RelativePosixPath
    payload_byte_length: StrictNonNegativeInt
    payload_sha256: Sha256
    materialized_root_sha256: Sha256 | None
    credential_scan_receipt_sha256: Sha256 | None
    source_credential_scan_receipt_root_sha256: Sha256 | None
```

`input_ref` must be the exact protected input tag for tag-bound caller rows or literal
`refs/heads/main` for a plan-bound publication caller row; the workflow inventory/policy selects the
form and main additionally binds its exact commit. Environment, deployment,
and approval fields are either all null or all populated. Each nonnull environment requires its
exact deployment/approval evidence. `benchmark-live` remains the distinct provider boundary.
`benchmark-publish` hosts separately approved jobs whose credentials identify distinct publisher
and release-finalizer Apps. Broker mutation receipts have a null environment and the distinct
state-writer App identity; no Actions state-writer job or secret exists, and `benchmark-state` and
`benchmark-release` environments are forbidden.
`UUID4` is the exact strict runtime scalar from `campaign.models`; locator/envelope round-trip tests
use the same `ProviderJobIdentityV1.batch_attempt_id` value and reject SHA-256-shaped substitutes.
Every locator field shared with `ArtifactEnvelopeV1` must byte-equal the class-bound revalidated
envelope. The inner archive digest/length come from the detached producer upload authorization and
are verified after streaming the sole outer member; they are not embedded in the envelope and thus
do not form a self-digest cycle. Direct `generation_batch|judge_attempt_batch` locators require the
full class-bound `UploadAuthorizationV1` nested here and exact equality of its inner/payload/receipt
fields; all secret-free producer locators require null. The safe nested record is read from canonical
authority, never from the ZIP it authorizes. Apply the same `canonical_file`/`root_ustar` nullability
rules to both records.

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/campaign/test_github_records.py -q`

Expected: FAIL during collection with
`ModuleNotFoundError: No module named 'laconian_eval.campaign.github_records'`.

- [ ] **Step 3: Implement the strict records and canonical identities**

Add `GitHubWorkflowRunV1`, `GitHubJobV1`, `GitHubDeploymentV1`, `GitHubApprovalV1`,
`GitHubArtifactV1`, and `ExactArtifactLocatorV1`. Import and class-bound revalidate the Runtime-owned
`ArtifactEnvelopeV1` and `UploadAuthorizationV1`; do not define a second envelope class. Each new record is
`extra="forbid"`, uses exact integer boundaries, and exposes a `sha256` field derived with
`stable_digest("laconian-{record_name}-v1", payload_without_sha256)` where `{record_name}` is the
closed schema name selected by code, not caller input.

`GitHubArtifactV1` and `ExactArtifactLocatorV1` preserve the exact canonical UTC `created_at` from
the numeric artifact API response. Reject missing/naive/fractionally noncanonical timestamps and
require a generation/judge `CredentialScanReceiptV1.scan_completed_at_utc <=
UploadAuthorizationV1.scan_completed_at_utc <= artifact_created_at_utc`; equality is allowed for
either check. This causal check is stored in durable provenance and
tested with before/equal/after fixtures.

The Runtime-owned `ArtifactEnvelopeV1` contains the producer-side values available before upload;
the following repeated shape is a compatibility assertion, not new ownership:

```python
class ArtifactEnvelopeV1(CapsuleModel):
    schema_version: Literal["1"]
    producer: Literal[
        "generation_batch",
        "generation_evidence_set",
        "hard_score",
        "judge_request",
        "judge_attempt_batch",
        "judge_attachment_set",
        "provider_evidence",
        "audit_packet",
        "audit_evidence",
        "analysis_evidence",
        "complete_collector",
        "invalid_prefix_finalizer",
        "publication_package",
        "publication_receipt",
        "release_package",
        "release_receipt",
        "correction_bundle",
    ]
    repository_id: StrictPositiveInt
    workflow_run_id: StrictPositiveInt
    run_attempt: StrictPositiveInt
    job_id: StrictPositiveInt
    batch_attempt_id: UUID4 | None
    input_tag_object_sha: GitObjectId
    input_commit_sha: GitObjectId
    workflow_path: RelativePosixPath
    workflow_sha256: Sha256
    environment: Literal["benchmark-live", "benchmark-publish"] | None
    deployment_id: StrictPositiveInt | None
    approval_actor_id: StrictPositiveInt | None
    approval_actor_login: BoundedNonBlankString | None
    payload_kind: Literal["canonical_file", "root_ustar"]
    payload_name: RelativePosixPath
    payload_byte_length: StrictNonNegativeInt
    payload_sha256: Sha256
    materialized_root_sha256: Sha256 | None
    credential_scan_receipt_sha256: Sha256 | None
    source_credential_scan_receipt_root_sha256: Sha256 | None
    envelope_sha256: Sha256
```

Direct `generation_batch` and `judge_attempt_batch` envelopes require a Slice 3
`CredentialScanReceiptV1` hash and null source-receipt root. The receipt binds the exact inner
payload bytes and proves exact-key plus pattern
scanning completed before the deterministic inner archive was authorized. The detached
`UploadAuthorizationV1`, which is never uploaded, separately binds the final inner
`laconian-artifact.zip`; it does not claim the later GitHub service wrapper was key-scanned. Do not
add artifact ID or service digest to the envelope: GitHub assigns both after upload.

`generation_evidence_set`, `hard_score`, `judge_request`, `judge_attachment_set`, and
`provider_evidence` are deterministic secret-free projections. They require a null direct receipt
and the ordered Merkle root of every directly scanned generation/judge-attempt receipt reachable
through their exact parents. All other producers require both fields null. A post-controller
projection is never falsely described as exact-key scanned; its loader re-verifies every direct
source receipt and recomputes the transitive root. The
consumer pairs the immutable API metadata with this envelope.

`canonical_file` requires null `materialized_root_sha256`. `root_ustar` requires payload name exactly
`root-payload.tar` and a nonnull root digest. Its uncompressed USTAR contains canonical
`root-manifest.json` plus a bounded allowlisted tree; the root digest covers the byte-sorted tuples
`(relative_path, byte_length, sha256, normalized_mode)` for every member except the manifest. The
manifest binds that root and has its own digest; the outer payload digest binds the complete tar, so
there is no self cycle.

- [ ] **Step 4: Add API-response parsers with content-free failures**

Add `parse_workflow_run`, `parse_workflow_jobs`, `parse_deployments`, `parse_approvals`, and
`parse_artifact`. Return only strict records and raise `GitHubRecordError(code)` without echoing
provider-controlled JSON. Prove that deployment status `target_url` and `log_url` end in the exact
`/actions/runs/{run_id}/job/{job_id}` pair and that the approval names the expected environment.

This task also owns the sole `GitHubReadClient` definition in `campaign/github_records.py`; later
tasks extend its closed method table but may not shadow or relocate the class. Freeze this exact
constructor (the API version, base hosts, timeout, headers, query document, and bounds are internal
constants and therefore are not caller arguments):

```python
class GitHubReadClient:
    def __init__(
        self,
        *,
        repository: OwnerRepo,
        token: SecretStr,
        transport: GitHubReadTransport,
    ) -> None: ...
```

`OwnerRepo` is one NFC ASCII `owner/name` pair with neither empty, dot, slash, percent-encoded, nor
control components. `GitHubReadTransport` is injected only for bounded tests; it is private to this
module's client and is never handed to a campaign caller. The client exposes no generic `request`,
URL, method, headers, body, parser, pagination, or GraphQL-document parameter.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_github_records.py -q`

Expected: PASS.

Run: `uv run ruff check src/laconian_eval/campaign/github_records.py tests/campaign/test_github_records.py`

Expected: exit 0.

- [ ] **Step 6: Commit the exact GitHub records**

```bash
git add src/laconian_eval/campaign/github_records.py \
  src/laconian_eval/campaign/__init__.py \
  tests/campaign/test_github_records.py
git commit -m "feat: bind benchmark GitHub artifact provenance"
```

### Task 2: Retrieve and verify artifacts only by exact numeric identity

**Files:**
- Modify: `src/laconian_eval/campaign/github_records.py`
- Create: `src/laconian_eval/campaign/artifacts.py`
- Create: `tests/campaign/fake_github.py`
- Modify: `tests/campaign/test_github_records.py`
- Create: `tests/campaign/test_artifacts.py`

- [ ] **Step 1: Write failing tests for exact lookup and bounded download**

Cover these cases with `FakeGitHubReadTransport`:

- exact run, attempt, job, deployment, approval, artifact ID, service digest, and envelope pass;
- a correct name with the wrong artifact ID fails;
- a correct artifact ID from a different run or attempt fails;
- duplicate artifacts, rerun artifacts, PR/fork origins, expired artifacts, and absent predecessors fail;
- pagination must be exhausted and bounded before selection;
- an outer service ZIP above 1 GiB or not containing exactly one regular member named
  `laconian-artifact.zip` fails; the inner ZIP may have at most 64 members, each at most 512 MiB,
  with aggregate declared and streamed uncompressed bytes at most 1 GiB; either layer rejects
  duplicate names, encryption, links, absolute paths, backslashes, `.`/`..`, non-NFC names, or a
  compression ratio above 100 before extraction;
- the authorization header is never forwarded to the signed redirect host;
- inside `laconian-artifact.zip`, `artifact-envelope.json`, conditional
  `credential-scan-receipt.json`, and the one declared payload are the only accepted members.
  Generation/judge artifacts require all three; secret-free producers require exactly envelope plus
  payload. Add a golden fixture that constructs the producer inner ZIP, wraps it exactly as
  `actions/upload-artifact` does, serves the raw service ZIP, and proves both layers and the unchanged
  inner bytes verify.
- root producers use the exact `root-payload.tar` contract. Test missing/duplicate manifest, root
  digest mismatch, unlisted/duplicate member, non-USTAR format, sparse/device/link member, unsafe
  path, nonnormalized mode/metadata, truncation/trailing bytes, and materialized-root substitution.

The public call is:

```python
archive = fetch_exact_artifact(
    client=GitHubReadClient(
        repository="agent-axiom/laconian",
        token="ghs_test_token",
        transport=fake_transport,
    ),
    expected=locator,
    destination=tmp_path / "downloaded-artifact.zip",
)
assert archive.locator == locator
assert archive.payload_sha256 == locator.payload_sha256
```

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/campaign/test_artifacts.py -q`

Expected: FAIL during collection because `laconian_eval.campaign.artifacts` does not exist.

- [ ] **Step 3: Implement the closed read-only GitHub client**

The artifact methods of `GitHubReadClient` may issue only these requests; the same class's other
capability-separated methods are additionally limited to the amendment synchronization contract's
raw-Git, fixed REST verification, fixed GraphQL signer, current-ruleset, historical-rule-suite,
PR/check/review/merge, current-main, immutable-Release, and Release/assets reads. Tests enumerate the
full public-method/verb/endpoint/query-digest table and reject any unlisted method or caller URL.
The closed public method names are exactly:

```text
get_repository
get_workflow_run
list_workflow_jobs
list_run_approvals
list_deployments
list_deployment_statuses
get_artifact
download_artifact_zip
get_git_ref
get_git_tag
get_git_commit
get_git_tree
get_git_blob
get_commit_verification
query_commit_signer
list_repository_rulesets
get_repository_ruleset
list_rule_suites
get_rule_suite
get_pull_request
get_pull_request_review
list_pull_request_reviews
list_check_runs
get_main_ref
get_main_commit
get_immutable_releases_setting
list_releases
get_release
get_release_by_tag
list_release_assets
download_release_asset
```

Every name has one implementation-owned endpoint template and fixed strict return parser; none
accepts a parser or URL. Ref-taking methods accept only the call-site-selected literal namespace
from the verified campaign plan (`refs/tags/<T0-or-T1>`, its peeled OID, `refs/heads/main`, the exact
result branch, or the exact result tag), never an arbitrary ref string. REST reads use only the
exact table below. `{ref_path}` is the validated ref with only the leading `refs/` removed;
`{object_oid}`, `{commit_oid}`, `{tree_oid}`, and `{blob_oid}` are lowercase 40-hex object IDs, and
all numeric IDs are strict positive integers. Query keys appear in the shown order; RFC 3986
percent-encoding uses UTF-8 and uppercase hex. `P(N)` means `per_page=100&page=N`, `N=1..64`, until
a short/empty final page. All pages are read; a page-64 continuation fails closed.

| Public method | Exact request | Query / redirect policy |
|---|---|---|
| `get_repository` | `GET /repos/{owner}/{repo}` | none |
| `get_workflow_run` | `GET /repos/{owner}/{repo}/actions/runs/{run_id}` | none |
| `list_workflow_jobs` | `GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs` | `P(N)` |
| `list_run_approvals` | `GET /repos/{owner}/{repo}/actions/runs/{run_id}/approvals` | none |
| `list_deployments` | `GET /repos/{owner}/{repo}/deployments` | `sha={input_commit_sha}&ref={input_ref}&task=deploy&environment={environment}&P(N)` |
| `list_deployment_statuses` | `GET /repos/{owner}/{repo}/deployments/{deployment_id}/statuses` | `P(N)` |
| `get_artifact` | `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}` | none |
| `download_artifact_zip` | `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip` | `Accept: application/octet-stream`; exactly one HTTPS redirect under the download rule below |
| `get_git_ref` | `GET /repos/{owner}/{repo}/git/ref/{ref_path}` | none |
| `get_git_tag` | `GET /repos/{owner}/{repo}/git/tags/{object_oid}` | none |
| `get_git_commit` | `GET /repos/{owner}/{repo}/git/commits/{commit_oid}` | none; strict raw-object field parser |
| `get_git_tree` | `GET /repos/{owner}/{repo}/git/trees/{tree_oid}` | no `recursive` query |
| `get_git_blob` | `GET /repos/{owner}/{repo}/git/blobs/{blob_oid}` | none; exact base64 parser and decoded-byte bound |
| `get_commit_verification` | `GET /repos/{owner}/{repo}/git/commits/{commit_oid}` | none; strict verification projection parser |
| `query_commit_signer` | `POST https://api.github.com/graphql` | exact query/body/digest below; no redirect or pagination |
| `list_repository_rulesets` | `GET /repos/{owner}/{repo}/rulesets` | `includes_parents=false&targets=branch%2Ctag&P(N)` |
| `get_repository_ruleset` | `GET /repos/{owner}/{repo}/rulesets/{ruleset_id}` | `includes_parents=false` |
| `list_rule_suites` | `GET /repos/{owner}/{repo}/rulesets/rule-suites` | `ref={exact_ref}&time_period=month&rule_suite_result=all&evaluate_status=all&P(N)` |
| `get_rule_suite` | `GET /repos/{owner}/{repo}/rulesets/rule-suites/{rule_suite_id}` | none |
| `get_pull_request` | `GET /repos/{owner}/{repo}/pulls/{pull_number}` | none; strict merge state/actor/commit projection |
| `get_pull_request_review` | `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}` | none; exact raw review-source bytes and observation metadata |
| `list_pull_request_reviews` | `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` | `P(N)`; parses `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`, and `DISMISSED`, so no invented dismissal-list endpoint exists |
| `list_check_runs` | `GET /repos/{owner}/{repo}/commits/{commit_oid}/check-runs` | `filter=all&P(N)` |
| `get_main_ref` | `GET /repos/{owner}/{repo}/git/ref/heads/main` | none; only literal protected `main` |
| `get_main_commit` | `GET /repos/{owner}/{repo}/commits/{commit_oid}` | none; OID equals the preceding main-ref observation |
| `get_immutable_releases_setting` | `GET /repos/{owner}/{repo}/immutable-releases` | none; only strict `enabled=true` succeeds |
| `list_releases` | `GET /repos/{owner}/{repo}/releases` | `P(N)`; authenticated drafts included |
| `get_release` | `GET /repos/{owner}/{repo}/releases/{release_id}` | none |
| `get_release_by_tag` | `GET /repos/{owner}/{repo}/releases/tags/{tag}` | none; exact plan tag only, never draft discovery |
| `list_release_assets` | `GET /repos/{owner}/{repo}/releases/{release_id}/assets` | `P(N)` |
| `download_release_asset` | `GET /repos/{owner}/{repo}/releases/assets/{asset_id}` | `Accept: application/octet-stream`; exactly one HTTPS redirect under the download rule below |

No other REST route, verb, query key/order/value, media type, host, or redirect is present in the
client. `get_git_commit` and `get_commit_verification` deliberately share one endpoint but have
different closed parsers and tests. Ruleset history, Contents API, archive-by-name/run listing,
audit-log search, review-dismissal writes, GraphQL introspection/mutation, and every write verb are
absent.

`query_commit_signer(commit_oid)` is the only non-REST method. It performs exactly one read-only
`POST https://api.github.com/graphql` with `Content-Type: application/json`, variables exactly
`{owner, name, oid}`, and the Evaluation-owned `GITHUB_COMMIT_SIGNER_QUERY_V1` bytes below. It
imports that constant and `GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1` by object/value identity from
`laconian_eval.benchmark.protocol_review`; `campaign.github_records` owns no copied query. It rejects a
null/wrong repository, wrong OID, aliases, extensions, errors, extra top-level payload, pagination,
or a mutation document. `GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1` is literal
`141ec2ce356c197073e0aeece28a804b56b8c31a615a3d36995c72ce2c9b3d7b`, the lowercase SHA-256 of
these 357 exact UTF-8 bytes (including the final LF). Record tests independently hash the bytes,
assert that golden, and copy it into `GitHubSignatureProjectionV1.query_sha256`:

```graphql
query ProtocolCommitSignature($owner: String!, $name: String!, $oid: GitObjectID!) {
  repository(owner: $owner, name: $name) {
    databaseId
    object(oid: $oid) {
      ... on Commit {
        oid
        signature {
          isValid
          state
          signer {
            databaseId
            login
          }
        }
      }
    }
  }
}
```

Set `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, a fixed user agent,
and a 30-second timeout. Each JSON response is at most 8 MiB; each list is at most 100 entries per
page, 64 pages, and 64 MiB aggregate canonical response bytes, and all pages must be exhausted.
The GraphQL response is one nonpaginated 8-MiB body. Only the two table-marked download methods may
follow a redirect: accept exactly one absolute `https://` `Location` returned by authenticated
`api.github.com`, reject userinfo, fragments, nondefault ports, and loopback/private/link-local IP
literals, strip authorization, cookies, and all GitHub headers, send only the fixed download user
agent plus `Accept: application/octet-stream`, and reject a second redirect. Stream to an exclusively created file while hashing and
enforcing the 1 GiB compressed bound. Before reading a member, sum the central-directory sizes with
checked arithmetic at both layers; while streaming, enforce the 512 MiB member and 1 GiB aggregate
uncompressed counters independently of declared sizes and compression ratios. Never materialize an
unbounded member in memory. Every producer passes exactly one prebuilt
`laconian-artifact.zip` path to `actions/upload-artifact`; directories, globs, or separately uploaded
inner members are workflow-policy failures.

- [ ] **Step 4: Implement exact provenance verification**

`fetch_exact_artifact` must verify API records before download, require GitHub's service field to be
exactly `sha256:` followed by 64 lowercase hexadecimal characters, normalize only by removing that
fixed prefix, and hash the raw outer service ZIP against the remaining digest. Without `extractall`,
it streams the sole outer member `laconian-artifact.zip`, verifies its digest/length, opens that
inner ZIP under the independent bounds, canonical-parses `artifact-envelope.json`, compares every
shared field with `ExactArtifactLocatorV1`, and hashes the
declared payload. For generation/judge artifacts it canonical-parses the fixed receipt member,
recomputes its digest, requires the envelope/locator hash to match, and verifies that the receipt
binds only this payload digest/length and completed pre-upload exact-key/pattern scan. It also
class-bound revalidates the locator's authority-sourced `UploadAuthorizationV1`, requires its
inner/payload/receipt fields to match the streamed bytes, and rejects a missing authorization or one
obtained from the artifact itself. The receipt
never binds the enclosing ZIP, avoiding a digest cycle. It returns:

```python
class RootPayloadMemberV1(CapsuleModel):
    relative_path: RelativePosixPath
    byte_length: StrictNonNegativeInt
    sha256: Sha256
    normalized_mode: Literal["0644", "0755"]


class RootPayloadManifestV1(CapsuleModel):
    schema_version: Literal["1"]
    members: tuple[RootPayloadMemberV1, ...]
    materialized_root_sha256: Sha256
    manifest_sha256: Sha256


@dataclass(frozen=True, slots=True)
class VerifiedArtifactArchive:
    locator: ExactArtifactLocatorV1
    envelope: ArtifactEnvelopeV1
    service_archive_path: Path
    service_archive_byte_length: int
    service_archive_sha256: str
    inner_archive_path: Path
    inner_archive_byte_length: int
    inner_archive_sha256: str
    payload_path: Path
    payload_name: str
    payload_byte_length: int
    payload_sha256: str
    credential_scan_receipt: CredentialScanReceiptV1 | None


@dataclass(frozen=True, slots=True)
class VerifiedArtifactRootV1:
    archive: VerifiedArtifactArchive
    root_path: Path
    manifest: RootPayloadManifestV1
    materialized_root_sha256: str
```

No function accepts an artifact name as a selector. `artifact_name` is checked only after numeric
ID selection.

Implement `materialize_verified_artifact_root(archive, destination) -> VerifiedArtifactRootV1` for
`root_ustar` only. Reuse the descriptor-relative, no-follow, strict uncompressed-USTAR policy from
Slice 1; exclusively create an owned `0700` stage, enforce envelope/manifest count and byte bounds
while streaming, hash every regular member, reject unknown or repeated paths, fsync, atomically
rename, then reopen/reverify every descriptor and the materialized-root digest. It never accepts a
caller allowlist or archive-selected destination. `canonical_file` consumers use the verified
`payload_path` directly. Add golden producer/consumer fixtures for generation, hard-score,
judge-request, judge, audit, analysis, collection, publication, and release roots.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `uv run pytest tests/campaign/test_artifacts.py tests/campaign/test_github_records.py -q`

Expected: PASS.

- [ ] **Step 6: Commit exact artifact retrieval**

```bash
git add src/laconian_eval/campaign/artifacts.py \
  src/laconian_eval/campaign/github_records.py \
  tests/campaign/fake_github.py \
  tests/campaign/test_github_records.py \
  tests/campaign/test_artifacts.py
git commit -m "feat: retrieve benchmark artifacts by exact identity"
```

### Task 3: Seal the read-only provider-evidence inventory

**Files:**
- Create: `src/laconian_eval/campaign/provider_evidence.py`
- Create: `tests/campaign/publication_helpers.py`
- Create: `tests/campaign/test_provider_evidence.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

- [ ] **Step 1: Write the failing happy-path coverage test**

Build a synthetic `CampaignRegistryV1` plus the exact tuple of 36 `ShardPlanV1` records covering
three model IDs and twelve byte-sorted scenario UIDs. Give every generation seal one hard-score
request set, one judge-request attachment, and one judge attachment, including sealed zero-request
and zero-call attachments. Assert exactly 36 members in each ordered collection and one inventory
hash.

Use this record shape:

```python
class EvidenceAttachmentRefV1(CapsuleModel):
    model_id: BoundedNonBlankString
    scenario_uid: Sha256
    artifact: ExactArtifactLocatorV1
    parent_sha256: Sha256
    attachment_sha256: Sha256
    credential_scan_receipt_sha256: Sha256 | None
    source_credential_scan_receipt_root_sha256: Sha256 | None


class EvidenceInventoryV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    input_tag_object_sha: GitObjectId
    input_commit_sha: GitObjectId
    campaign_registry_sha256: Sha256
    audit_protocol_sha256: Sha256
    benchmark_provider_evidence_sha256: Sha256
    shard_plan_root_sha256: Sha256
    spend_ledger_sha256: Sha256
    cache_write_usage_root_sha256: Sha256
    service_tier_evidence_root_sha256: Sha256
    generation: tuple[EvidenceAttachmentRefV1, ...]
    hard_score: tuple[EvidenceAttachmentRefV1, ...]
    judge_request: tuple[EvidenceAttachmentRefV1, ...]
    judge: tuple[EvidenceAttachmentRefV1, ...]
    artifact_provenance_root_sha256: Sha256
    direct_provider_artifact_root_sha256: Sha256
    credential_scan_receipt_root_sha256: Sha256
    inventory_sha256: Sha256
```

- [ ] **Step 2: Add failing integrity and completeness tests**

Parametrize deletion, duplication, reordering, wrong capsule parent, wrong hard-score parent,
missing or changed judge-request attachment, judge request outside the sealed request set, missing
zero-call attachment, nonterminal request,
ambiguous delivery, internally impossible or contradictory token usage, inconsistent returned
model, missing spend receipt,
unreconciled reservation, superseded attempt, unresolved hold, and active credential-exposure
pending root. Also pass an audit or analysis
path to the verifier and assert `unexpected_evidence_layer`.

Delete or alter a direct generation/judge-attempt `CredentialScanReceiptV1`, bind it to different
bytes, mark the exact-key scan incomplete, or supply one created after upload; inventory sealing
must fail. Generation-set, hard-score, judge-request, judge-attachment-set, and provider-evidence
producers are secret-free: their direct receipt field is null and their transitive source-receipt
root must recompute from all exact reachable direct artifacts. Substitute, omit, or add any direct
locator/receipt or claim a post projection was directly scanned and sealing fails. The inventory
root covers all ordered direct provider scan receipts so the collector never needs the key later.

Missing or provider-omitted reasoning-token breakdown is not an evidence-integrity failure. Add
fixtures for `not_reported` and schema-valid `invalid` reasoning usage, preserve those statuses in
the sealed inventory, and prove the later analysis marks that model's token objective unavailable
or inconclusive while the complete evidence bundle remains publishable. Negative counts, component
counts exceeding output usage, or disagreement between duplicate provider fields remain integrity
failures.

Preserve `ordinary_uncached_input_tokens`, `cache_read_tokens`, `cache_write_tokens`, the exact
Foundation-owned `applied_cache_control_status`, `cache_read_status`, and `cache_write_status`, their
independent raw-source digests, and all five charge/reservation components distinctly in every
generation/judge reference and `cache_write_usage_root_sha256`. Reject folding writes into reads or
ordinary uncached input, treating missing write detail as zero, or publishing a spend total that
does not reproduce from ordinary-uncached input, cache-read input, cache-write input, visible
output, and reasoning output.
The report may describe cache-write cost only as provider accounting; it never enters the primary
visible-output-token contrast.

Require requested service tier `default`, the exact wire-field request digest, and returned service
tier in every generation/judge attempt reference and
`service_tier_evidence_root_sha256`. A complete inventory accepts `reported_default` for every
received response and exactly `not_applicable_definitely_not_sent` or
`not_applicable_definitely_rejected` only for the matching independently proven delivery state with
no response/usage (including a prior proven 429 retry). `missing|mismatch` on a
received or unknown-delivery attempt must already have stopped provider execution and can appear only
in the safe invalid-prefix lineage with worst-case exposure retained. Reject an omitted/`auto`
request, forged not-applicable status, or projection that drops the returned tier/accounting status.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_provider_evidence.py -q`

Expected: FAIL during collection because `provider_evidence.py` does not exist.

- [ ] **Step 4: Implement the read-only verifier**

Add this exact entry point:

```python
def seal_provider_evidence_inventory(
    *,
    registry: CampaignRegistryV1,
    shard_plans: tuple[ShardPlanV1, ...],
    authority: ReconstructedAuthorityV1,
    spend_ledger: SpendLedgerV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    artifact_locators: tuple[ExactArtifactLocatorV1, ...],
) -> EvidenceInventoryV1:
```

The Slice 3 adapter owns creation and durable placement of
`GENERATION/generation-context.json` plus the generation `LayerRootIndexV1`; Slice 2 `hard-score`,
`prepare-judge`, and `seal-judge` respectively own the hard-score, judge-request, and judge indexes,
and Runtime's `Runtime.seal_judge` owns the exact `provider-evidence-index.json` plus the separately
verified `ATTEMPTS` root. Runtime Task 7 reconstructs the retained predecessor and final
`GENERATION_COMPLETE` authority roots through `_reconstruct_verified_runtime`, then calls the exact
Evaluation Task 8 `load_verified_benchmark_provider_evidence` boundary with
`provider_index_path`, `generation_root`, `hard_score_root`, `judge_request_root`,
`judge_attempt_root`, `judge_root`, and the constructor's in-memory `generation_expectation`.
This Task 3 function receives only that returned immutable `VerifiedBenchmarkProviderEvidenceV1`;
it accepts neither root-path tuples nor a provider-index path. Publication Task 7 later
reconstructs its own authority-only capability before invoking this same inventory seal in a live
workflow. No raw file, nested provider-index field, digest, workflow input, or CLI option may
construct the verified expectation.

It requires `authority.state.state == "JUDGE_COMPLETE"`, calls
`require_ordinary_effect_gate(authority)`, and exact-compares the verified object's complete
generation expectation, predecessor authority root, bound final authority root, context digest,
provider-index digest, and workflow root with the retained authority events. It reuses only the
verified object's scored capsules and
strict attachments, and joins only on exact parent hashes and planned request IDs,
verifies the ledger and returned-model consistency separately per generation model,
and derives the provenance root from the ordered exact locators. It opens every input read-only and
creates no output itself.

Re-hash the tagged `src/laconian_eval/benchmark/hard_score.py` source plus the exact hard-score,
statistics, and audit protocol members from verified `C0`; require their path/hash pairs, the frozen
workflow-inventory root, and the authority-bound generation-context digest to equal
`CampaignRegistryV1`, the neutral context, every hard-score request set, and
`VerifiedBenchmarkProviderEvidenceV1`. A self-consistent
substituted context/index or a hash copied from any non-C0 or mutable-`main` commit fails.
The audit member is exactly
`benchmarks/protocols/public-three-model-v1/audit.json`; consume Evaluation's singular
`audit_protocol_sha256: Sha256` as verified by Runtime Task 2, store that same field in
`EvidenceInventoryV1`, and reject an alias, caller scalar, omitted consumer binding, or any
redefinition of the Evaluation-owned contract.

No Slice 2 code imports this campaign inventory. Require
`EvidenceInventoryV1.benchmark_provider_evidence_sha256` to equal that projection's digest and every
ordered 36-parent vector to match. Return/store the verified projection alongside the inventory in
the campaign loader so audit/analysis loaders receive their mandatory benchmark-owned argument.
Export `EvidenceInventoryV1` and `seal_provider_evidence_inventory` from `campaign.__init__`; the
next serialized public-contract owner pins their module and signature.

- [ ] **Step 5: Prove the verifier does not mutate or reopen inputs after verification**

Add spies for `open`, `Path.write_bytes`, `Path.write_text`, `os.rename`, and capsule directory
metadata. Assert byte-for-byte and stat identity preservation on success and every failure path.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_provider_evidence.py -q`

Expected: PASS.

Run: `uv run mypy src/laconian_eval/campaign/provider_evidence.py`

Expected: exit 0.

- [ ] **Step 7: Commit provider-evidence inventory sealing**

```bash
git add src/laconian_eval/campaign/provider_evidence.py \
  src/laconian_eval/campaign/__init__.py \
  tests/campaign/publication_helpers.py \
  tests/campaign/test_provider_evidence.py
git commit -m "feat: seal exact provider evidence inventory"
```

### Task 4: Add allowlist-by-construction public projection and secret scanning

**Files:**
- Create: `src/laconian_eval/campaign/public_projection.py`
- Create: `tests/campaign/test_public_projection.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

- [ ] **Step 1: Write failing projection-role and checksum tests**

Define `PublicFileRole` as a closed literal for every fixed member family in the two canonical
trees. Test UTF-8 byte ordering, unique normalized relative paths, regular files only, bounded
member count, 1 GiB aggregate bytes, 128 MiB per file, canonical `checksums.sha256`, and a
domain-separated `BundleSealV1`.

Use these public records:

```python
class PublicFileV1(CapsuleModel):
    role: PublicFileRole
    path: RelativePosixPath
    byte_length: StrictNonNegativeInt
    sha256: Sha256


class BundleSealV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    kind: Literal["complete", "invalid_prefix"]
    audit_protocol_sha256: Sha256
    source_state_sha256: Sha256
    source_artifact_root_sha256: Sha256
    files: tuple[PublicFileV1, ...]
    checksum_manifest_sha256: Sha256
    bundle_sha256: Sha256
```

- [ ] **Step 2: Write failing credential and untrusted-Markdown tests**

Reject exact known secrets, `sk-`/`sess-`/bearer/private-key patterns, authorization/cookie headers,
environment dumps, `OPENAI_API_KEY`, home/private/temp paths, unrestricted exception bodies, and
unknown provider metadata keys. The error exposes only a stable code, role, and file digest.

For approved excerpts, assert that `<`, `>`, `&`, backticks, Markdown links/images, headings,
mentions, autolinks, and bidirectional controls become inert text. Canonical JSONL response files
retain exact model bytes; only human-readable excerpts pass through the encoder.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_public_projection.py -q`

Expected: FAIL because `public_projection.py` does not exist.

- [ ] **Step 4: Implement the projection policy**

Add:

```python
class PublicProjectionPolicyV1(CapsuleModel):
    schema_version: Literal["1"] = "1"
    maximum_member_count: Literal[4096] = 4096
    maximum_file_bytes: Literal[134217728] = 134217728
    maximum_aggregate_bytes: Literal[1073741824] = 1073741824
    markdown_encoder_version: Literal["laconian-text-only-v1"] = "laconian-text-only-v1"
    credential_pattern_version: Literal["laconian-public-secret-scan-v1"] = (
        "laconian-public-secret-scan-v1"
    )


def verify_public_projection(
    root: Path,
    *,
    registry: CampaignRegistryV1,
    kind: Literal["complete", "invalid_prefix"],
    source_state_sha256: str,
    source_artifact_root_sha256: str,
    known_secret_values: tuple[str, ...] = (),
) -> BundleSealV1:
```

Derive `campaign_id` and the Evaluation-owned `audit_protocol_sha256: Sha256` only from the verified
Runtime registry. Re-hash the registry-bound peeled-C0
`benchmarks/protocols/public-three-model-v1/audit.json` projection before returning either bundle
kind; no projection call accepts either value as an independent scalar or defines an audit-hash
alias.

`known_secret_values` is an optional offline defense-in-depth input, not the live exact-key control.
For every generation/judge source, projection first requires the inventory-bound Slice 3
`CredentialScanReceiptV1` over the byte-identical uploaded archive. The later secret-free collector
must not claim it can recover or re-scan the provider key.

Scan through fd-relative no-follow reads. Never place a matched byte sequence in an exception,
test ID, log, or GitHub annotation. Generate checksums as lowercase SHA-256, two spaces, relative
path, newline, sorted by UTF-8 bytes.
Export `PublicProjectionPolicyV1`, `BundleSealV1`, and `verify_public_projection` from
`campaign.__init__`; do not expose internal scanners or text encoders.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_public_projection.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the public projection boundary**

```bash
git add src/laconian_eval/campaign/public_projection.py \
  src/laconian_eval/campaign/__init__.py \
  tests/campaign/test_public_projection.py
git commit -m "feat: project benchmark evidence to a safe public bundle"
```

### Task 5: Build the fail-closed complete collector

**Files:**
- Create: `src/laconian_eval/campaign/collector.py`
- Create: `tools/benchmark_reproduce_public_bundle.py`
- Create: `tests/campaign/test_complete_collector.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

- [ ] **Step 1: Write the failing exact-tree collection test**

Use the canonical complete tree from this plan. Assert byte identity for copied raw and derived
layers, 36 generation tar/sidecar pairs, 36 hard-score attachments, 36 judge-request attachments,
36 judge attachments, both commitments, both reveals, adjudication core/envelope, both standalone
signoffs, their exact canonical GitHub review records, analysis outputs, report, limitations,
reproduction instructions, checksum manifest, and `bundle.json`. Freeze the complete bytes and
SHA-256 of `REPRODUCE.md`; the only variable fragment is the already validated literal
`campaign_id` inserted by the collector's canonical text renderer. The document never embeds its
containing `bundle_sha256`, avoiding a digest cycle.
Require `provenance/reviewer-attestations.jsonl` to be the byte-identical tagged three-line
`VerifiedProtocolAttestationV1` envelope file accepted by preflight, with all three hashes and their ordered
root reproduced from
`CampaignRegistryV1`; it is not synthesized from informal review notes during collection.
Likewise require the byte-identical tagged `RepositoryTrustBoundaryAttestationV1` and detached
signature accepted by preflight. Recompute their digests/settings-record root and verify the
registered security-evidence signer; collection never turns the repository-settings checklist into
a substitute attestation.
Require `provenance/workflows.jsonl` to be the canonical path/hash projection from the registry's
exact 15-member `WorkflowInventoryV1`; recompute its root from committed `C0` bytes and
byte-compare the root bound by every protocol review. Never snapshot mutable default-branch bytes at
collection time.

Call:

```python
seal = collect_complete_bundle(
    registry=registry,
    authority=analysis_complete_authority,
    evidence_inventory=evidence_inventory,
    benchmark_provider_evidence=benchmark_provider_evidence,
    audit=verified_audit,
    analysis=verified_analysis,
    artifact_roots=verified_artifact_roots,
    output_root=tmp_path / "complete-bundle",
    policy=PublicProjectionPolicyV1(),
)
assert seal.kind == "complete"
```

- [ ] **Step 2: Add failing incomplete/superseded/untrusted tests**

Delete each required member family in turn. Add duplicate or superseded attempts, wrong PR merge
SHAs, a fork-origin artifact, a stale audit sign-off, an analysis parent mismatch, a symlink, an
existing output, an output outside the caller root, and a credential pattern. Every case must fail
without publishing a visible bundle.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_complete_collector.py -q`

Expected: FAIL because `collect_complete_bundle` cannot be imported.

- [ ] **Step 4: Implement complete-only collection**

Use this signature exactly:

```python
def collect_complete_bundle(
    *,
    registry: CampaignRegistryV1,
    authority: ReconstructedAuthorityV1,
    evidence_inventory: EvidenceInventoryV1,
    benchmark_provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
    audit: VerifiedAuditEvidenceV1,
    analysis: VerifiedAnalysisEvidenceV1,
    artifact_roots: tuple[Path, ...],
    output_root: Path,
    policy: PublicProjectionPolicyV1,
) -> BundleSealV1:
```

Require `authority.state.state == "ANALYSIS_COMPLETE"`, call
`require_ordinary_effect_gate(authority)`, and require exact
evidence/audit/analysis parent hashes, the full audit merge set, and exact current inventory. Obtain
the aggregate inputs only through `load_verified_audit_evidence` and
`load_verified_analysis_evidence`; copy from already verified descriptors into an
owned `0700` stage, never parse model text while rendering reports, verify the finished projection,
fsync, atomically publish, then reverify through a fresh descriptor.

Require `registry`, `evidence_inventory`, `benchmark_provider_evidence`, `audit`, and `analysis` to
carry the identical Evaluation-owned `audit_protocol_sha256: Sha256`, sourced only from Runtime
Task 2's verified C0
`benchmarks/protocols/public-three-model-v1/audit.json` bytes. Re-hash that public projection member
before sealing; an absent, renamed, independently supplied, or mismatched value blocks collection.

Pass `benchmark_provider_evidence` to both mandatory loader keywords and require its digest to match
`EvidenceInventoryV1`. The four roots used to reconstruct it must be members of the exact artifact
inventory; a caller-synthesized projection or root substitution fails before staging output.
Reload both exact reviewer registries and all three protocol-review attestations; require distinct
role-bound protocol identities, exact peeled commit/workflow/seven-protocol/audit-registry/protocol-
registry bindings and `approved` dispositions, then copy their original
canonical JSONL bytes to the fixed provenance member. Missing/stale reviews block complete
collection.
Export only `collect_complete_bundle` from the collector surface at this checkpoint.

- [ ] **Step 5: Verify deterministic reconstruction**

Collect twice into separate roots from byte-identical inputs and assert identical member bytes,
checksums, `bundle.json`, and `bundle_sha256`. Vary filesystem enumeration order and assert the
same result.

Create the standard-library-only repository tool
`tools/benchmark_reproduce_public_bundle.py`. Its exact CLI is
`main(argv: Sequence[str] | None = None) -> int` with only required
`--bundle-root BUNDLE_ROOT`, `allow_abbrev=False`, no environment-derived inputs, no network/Git
client imports, and no writes. It descriptor-opens only the supplied copied public tree, applies the
same bounds/no-follow rules, and independently recomputes the campaign seed/plan index, all seven
protocol hashes (including hard-score, retry, checkpoint, and publication), the 36-member
generation/hard-score/judge-request/judge vectors and roots, audit population/sample, analysis seal,
checksum manifest, and bundle digest. Its one success line is exactly
`{"bundle_sha256":"<resolved bundle_sha256>","campaign_id":"<resolved campaign_id>","status":"reproduced"}\n`
in canonical key order with exit 0; failure writes no stdout, writes exactly
`{"code":"reproduction-failed","status":"error"}\n` to stderr, and exits 3 without exception or
path text.

The collector renders `REPRODUCE.md` with these exact UTF-8/LF-only bytes, substituting only the
validated campaign ID and ending in one LF:

```text
# Offline structural reproduction

From the approved input-tag checkout, run:

uv run --frozen python tools/benchmark_reproduce_public_bundle.py --bundle-root benchmarks/results/{campaign_id}

Expected stdout:

{"bundle_sha256":"<computed lowercase SHA-256>","campaign_id":"{campaign_id}","status":"reproduced"}
```

The test copies only the public tree to `benchmarks/results/{campaign_id}` in a clean checkout of the
approved input commit, runs that literal command with network and GitHub/provider access trapped,
and asserts stdout uses the recomputed `bundle.json.bundle_sha256` in the exact success schema and
exit 0. It mutates every recomputed family and asserts exit 3,
content-free stderr, no write, and no API attempt. It independently hashes the rendered
`REPRODUCE.md`, requires the digest recorded in `checksums.sha256`/`bundle.json`, and rejects CRLF,
extra whitespace, alternate command/options, unresolved braces, or a different script path.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_complete_collector.py tests/campaign/test_public_projection.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the complete collector**

```bash
git add src/laconian_eval/campaign/collector.py \
  src/laconian_eval/campaign/__init__.py \
  tools/benchmark_reproduce_public_bundle.py \
  tests/campaign/test_complete_collector.py
git commit -m "feat: collect complete publication benchmark evidence"
```

### Task 6: Build the disjoint invalid-prefix finalizer

**Files:**
- Modify: `src/laconian_eval/campaign/collector.py`
- Modify: `tools/benchmark_reproduce_public_bundle.py`
- Create: `tests/campaign/test_invalid_prefix_finalizer.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

- [ ] **Step 1: Write the failing STOP and budget-prefix tests**

Create one `STOPPED_INVALID` state with a safe incident and one `BUDGET_INCOMPLETE` state. Assert
the exact invalid-prefix tree, ordered completed prefix, exact expected missing suffix, last valid
spend ledger, and absence of all performance layers. Require `REPRODUCE.md` to use the exact Task 5
bytes/command with this campaign ID and require its independent checksum in both bundle manifests.

Parameterize generation STOP before the first call, mid-generation inside a 40-row shard, exactly at
a generation shard boundary, mid-judge inside a nonempty judge attachment, between judge
attachments, and across a sealed zero-call judge attachment. For every case, assert the active phase,
phase-plan hash, completed whole units, optional completed partial-unit request prefix, missing
partial-unit suffix, remaining whole units, last verified checkpoint, and scan-receipt identities.

Use:

```python
seal = finalize_invalid_prefix(
    registry=registry,
    campaign_plan_index=campaign_plan_index,
    phase_plan=verified_phase_plan,
    authority=stopped_authority,
    spend_ledger=spend_ledger,
    safe_artifact_locators=safe_locators,
    incident=incident,
    output_root=tmp_path / "invalid-prefix",
    policy=PublicProjectionPolicyV1(),
)
assert seal.kind == "invalid_prefix"
```

- [ ] **Step 2: Add failing cross-path tests**

Assert rejection from `ANALYSIS_COMPLETE`, any unresolved hold or active credential-exposure
pending root, a phase-plan hash different from the
authority's active plan, a non-prefix completed set, a missing item outside the exact suffix, a
generation record in a judge prefix or vice versa, a fabricated zero-call boundary, a ledger not
matching state, raw model output, judge/audit/
analysis records, `report.md`, token deltas, intervals, rankings, credentials, or a suspected
  exposure record containing the suspected bytes.
  The two safe trust-boundary provenance records remain mandatory in the invalid-prefix tree, but a
  secret-bearing settings response, token, PEM, or free-form admin payload is always rejected.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_invalid_prefix_finalizer.py -q`

Expected: FAIL with `ImportError` for `finalize_invalid_prefix`.

- [ ] **Step 4: Implement a separate finalizer, not a mode flag**

Add the exact signature:

```python
def finalize_invalid_prefix(
    *,
    registry: CampaignRegistryV1,
    campaign_plan_index: CampaignPlanIndexV1,
    phase_plan: VerifiedPhasePlanV1,
    authority: ReconstructedAuthorityV1,
    spend_ledger: SpendLedgerV1,
    safe_artifact_locators: tuple[ExactArtifactLocatorV1, ...],
    incident: SafeIncidentV1,
    output_root: Path,
    policy: PublicProjectionPolicyV1,
) -> BundleSealV1:
```

Define `SafeIncidentV1` in `collector.py` with enumerated reason, incident ID, timestamps, affected
artifact IDs/digests, deletion result, and safe narrative code. It contains no free-form provider
exception, credential, response, prompt, or environment field. Define `InvalidPrefixEvidenceV1`
with the closed fields `phase`, `active_phase_plan_sha256`, ordered whole-unit identities, completed
whole-unit prefix, optional partial-unit identity plus its completed-request prefix and missing-request
suffix, remaining whole-unit suffix, last verified checkpoint hash, last spend-ledger hash, ordered
safe scan-receipt hashes, and its own digest.

Define frozen `VerifiedInvalidPrefixBundleV1` as the non-serializable trusted-loader result containing
the class-bound `BundleSealV1`, `InvalidPrefixEvidenceV1`, `SafeIncidentV1`, verified registry/state/
ledger hashes, exact member inventory, and descriptor-owned root. Implement
`load_verified_invalid_prefix_bundle(root) -> VerifiedInvalidPrefixBundleV1`; it repeats the fixed
tree, checksum, absence-of-performance-layer, and no-follow verification. It is accepted only for
invalid publication planning/PR validation; the post-release result-claims gate rejects it because
invalid-prefix states have no release or promotion path. Export both the type and loader.

The function accepts only the safe-invalid states enumerated by the approved state matrix, calls
`require_ordinary_effect_gate(authority)`, verifies
`SpendLedgerV1` against the authority hash, and
requires `phase_plan.plan_sha256 == authority.state.active_phase_plan_sha256`. For generation it
validates the plan against `CampaignPlanIndexV1` and uses its seed-derived 36-shard order. For judge
it validates the sealed `JudgeRequestAttachmentV1` index root, uses that same shard order, retains
all 36 attachment boundaries including zero-call attachments, and uses each attachment's sealed
request order. It derives completion only from verified checkpoints, terminal attempt evidence,
spend events, and scan receipts. Callers cannot supply either prefix or suffix. An ambiguous
in-flight request starts the missing suffix even though its worst-case reservation remains in the
ledger.

For `credential_exposure`, require the canonical `CredentialExposureIncidentEvidenceV1`, exact
affected-artifact denylist, terminal revoked/rotated/cryptographically-expired containment as
permitted for the secret kind, deletion-or-unavailability receipts, no-further-campaign-download
receipt, and the publisher close receipt when the parent was `COMPLETE_PUBLICATION_PR_OPEN`. Exclude
every affected raw artifact and scanner-match byte from the projection. Publish only safe incident
metadata and never claim prior downloads or public Git objects were erased.
Export `VerifiedInvalidPrefixBundleV1`, `load_verified_invalid_prefix_bundle`, and
`finalize_invalid_prefix` from `campaign.__init__`.

Extend the same fixed reproduction tool by strict `bundle.json.kind` dispatch. For
`invalid_prefix`, it recomputes only registry/state/ledger, phase-plan/completed-prefix/missing-
suffix/incident, safe provenance, member inventory, checksums, and bundle digest; it rejects any
performance member. The command, exact stdout/error schemas, exits, no-write/no-network rule, and
`REPRODUCE.md` bytes remain identical to Task 5. Tests run the literal document command from a
copied invalid-prefix tree and mutate every permitted family plus one forbidden performance member.

- [ ] **Step 5: Run both collector suites and verify separation**

Run: `uv run pytest tests/campaign/test_complete_collector.py tests/campaign/test_invalid_prefix_finalizer.py -q`

Expected: PASS.

- [ ] **Step 6: Commit invalid-prefix finalization**

```bash
git add src/laconian_eval/campaign/collector.py \
  src/laconian_eval/campaign/__init__.py \
  tools/benchmark_reproduce_public_bundle.py \
  tests/campaign/test_invalid_prefix_finalizer.py
git commit -m "feat: finalize invalid benchmark prefixes safely"
```

### Task 7: Add the `Publication` capability and secret-free evidence workflows

**Files:**
- Create: `src/laconian_eval/campaign/publication.py`
- Modify: `src/laconian_eval/campaign/github_records.py`
- Create: `tools/benchmark_sample_audit_stage.py`
- Create: `tools/benchmark_seal_audit_stage.py`
- Create: `tools/benchmark_analyze_stage.py`
- Create: `tools/benchmark_verify_stage.py`
- Create: `.github/workflows/benchmark-hard-score.yml`
- Create: `.github/workflows/benchmark-evidence.yml`
- Create: `.github/workflows/benchmark-audit.yml`
- Create: `.github/workflows/benchmark-analysis.yml`
- Create: `.github/workflows/benchmark-collect-complete.yml`
- Create: `.github/workflows/benchmark-finalize-invalid.yml`
- Create: `.github/workflows/audit-pr-validate.yml`
- Modify: `.github/workflows/benchmark-publication-state.yml`
- Create: `tools/validate_audit_pr.py`
- Create: `tests/campaign/test_publication_capability.py`
- Create: `tests/campaign/test_publication_workflows.py`
- Create: `tests/campaign/test_audit_pr.py`
- Modify: `tests/campaign/test_github_records.py`
- Modify: `tests/campaign/test_workflow_policy.py`
- Modify: `tests/test_ci_contract.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write failing capability and ownership tests**

Test that ordinary construction is impossible and the sole constructor is the private
`_reconstruct_verified_publication(*, authority, verified_generation_context,
verified_provider_evidence)`. It re-verifies current canonical authority and returns one in-memory
capability whose exact live methods are:

```python
Publication.campaign.evaluation_stage.sample_audit
Publication.campaign.evaluation_stage.seal_audit
Publication.campaign.evaluation_stage.analyze
Publication.campaign.evaluation_stage.verify
```

Each method is keyword-only and accepts only typed local inputs/operation-owned output roots. Tests
reject pickling, JSON/Pydantic serialization, public export of the constructor, construction from a
digest or provider index, reuse after authority moves, and importing a public replay handler from
campaign code. Call-graph tests pin the three Runtime-owned live methods plus these four Publication-
owned methods and prove none shares a writer entrypoint with the seven handlers under
`laconian_eval.replay`.

- [ ] **Step 2: Run capability tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_capability.py tests/test_public_contract.py -q`

Expected: FAIL because `campaign/publication.py` and the private constructor do not exist.

- [ ] **Step 3: Implement authority-only staged evaluation**

Implement the private constructor and four methods. `sample_audit` and `seal_audit` require exact
state `PROVIDER_EVIDENCE_VERIFIED`; `analyze` and `verify` require the exact accepted
`AUDIT_SEALED` lineage, with `verify` additionally fresh-loading the analysis output produced by
`analyze`. Every call requires the same in-memory verified generation-context capability, both
identity registries, `protocol_attestations_root`, hard-score/judge/statistical protocol hashes,
the Evaluation-owned singular `audit_protocol_sha256: Sha256` derived by Runtime Task 2 from exact
peeled-C0 `benchmarks/protocols/public-three-model-v1/audit.json` bytes, provider-projection root,
the unchanged `audit_sampling_protocol_sha256`, `audit_commit_reveal_protocol_sha256`, and
`audit_adjudication_protocol_sha256` bindings, and common `workflow_root`. The singular aggregate
never replaces or derives those granular bindings. The provider index is evidence only;
it carries the expectation digest and repeated bindings but never a nested alleged expectation or
capability.

`seal_audit` uses only the source-acquisition boundary in the amendment synchronization contract:
it derives repository identity from verified provider attestations, captures the exact five PRs,
five signature-response pairs, two exact reviews, and deterministic bounded Git-object closure,
constructs the Evaluation-owned source/archive models, and passes those plus the verified sample,
reviewer chains, adjudication, and metrics to `write_audit_evidence_root`. It accepts no
`repository_root`, repository scalar, raw-response input, detached review record, prebuilt success
flag, or Git/signature callback. Tests exhaustively compare the client's request log with the exact
closed endpoint/query table and prove any missing, duplicate, reordered, cross-repository, stale,
or post-capture-mutated source blocks `AUDIT_SEALED`.

The four fixed tools import only `laconian_eval.campaign.publication`, reconstruct the capability
from current authority inside one process, call exactly one corresponding method, and exit. They
accept fixed staging paths only, use `allow_abbrev=False`, and accept no campaign ID, expected root,
protocol hash, workflow hash, model ID, mode scalar, arbitrary command, or capability value. The
sample is deterministically rederived from verified provider evidence in an operation-owned root;
no caller may select or reuse an old sample root. No live tool or workflow invokes
`laconian-benchmark` or modules under `laconian_eval.replay`.

- [ ] **Step 4: Write failing workflow and broker-policy tests**

Require the seven new workflows to use only their frozen triggers, top-level `permissions: {}`,
`concurrency.group: laconian-public-benchmark-state`, `cancel-in-progress: false`, trusted detached
code, `ubuntu-24.04`, `persist-credentials: false`, exact numeric artifact locators, 90-day
retention, and full-SHA action refs. The exact workflow inventory now contains eleven paths: the
four Runtime-owned workflows `.github/workflows/benchmark-preflight.yml`,
`.github/workflows/benchmark-batch.yml`, `.github/workflows/benchmark-dismiss-hold.yml`, and
`.github/workflows/benchmark-publication-state.yml`, plus these seven. Missing, extra, renamed, or
reordered members fail.

Every compute job is read-only. Every authority mutation calls Runtime Task 9's existing
`.github/workflows/benchmark-publication-state.yml`; Task 7 only adds the exact audit, analysis,
complete-collection, invalid-finalization, hard-score, and evidence caller/event rows. The reusable
job contains only OIDC bootstrap and the fixed hash-pinned argument-closed broker client. It has no
checkout, generated shell, caller script, App secret, App token, or step before/after that client.
The external broker validates caller/callee/run/check identity and performs the receive-pack CAS;
it never returns the state-writer installation token to Actions.

Repository-wide scans fail on `STATE_WRITER_APP_ID`, `STATE_WRITER_APP_INSTALLATION_ID`,
`STATE_WRITER_APP_PRIVATE_KEY`, a state-writer installation token, or any equivalent state
credential in workflow YAML, repository/environment secrets, arguments, stdin, output, logs, or
artifacts. They also reject write-capable `GITHUB_TOKEN`, `pull_request_target`, privileged
`workflow_run`, untrusted code, and any overlap with `OPENAI_API_KEY`.

Require `audit-pr-validate.yml` to run stable job `audit-pr-validate` on the approved PR/review
events, with trusted-base code, exact head resolution, no secret, and only `contents: read` plus
`pull-requests: read`. Unrelated diffs return an explicit successful no-op.

- [ ] **Step 5: Run workflow tests and verify RED**

Run: `uv run pytest tests/campaign/test_github_records.py tests/campaign/test_publication_workflows.py tests/campaign/test_audit_pr.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py -q`

Expected: FAIL because this checkpoint's frozen 11-workflow inventory, fixed tools, and new reusable-workflow caller rows are
absent.

- [ ] **Step 6: Implement this task's workflows and audit validator within the 11-member checkpoint**

`benchmark-hard-score.yml` calls only `Runtime.hard_score` then `Runtime.prepare_judge` and accepts
only `GENERATION_COMPLETE`; the existing judge runtime calls only `Runtime.seal_judge`.
`benchmark-evidence.yml` accepts only `JUDGE_COMPLETE` and seals the exact provider-evidence
inventory. `benchmark-audit.yml` calls only Publication `sample_audit` and `seal_audit`, then emits
`AUDIT_SEALED`. `benchmark-analysis.yml` calls only Publication `analyze` and `verify`, then emits
`ANALYSIS_SEALED`. `benchmark-collect-complete.yml` accepts only `ANALYSIS_COMPLETE` and emits
`COMPLETE_BUNDLE_SEALED`. `benchmark-finalize-invalid.yml` accepts only `STOPPED_INVALID` or
`BUDGET_INCOMPLETE` and emits `INVALID_PREFIX_SEALED`. Every event is packaged as canonical broker
input against an exact expected authority OID; stale OID, unresolved hold, or active
credential-exposure pending root fails before upload or side effect.

Hard-score, evidence, and invalid-finalization dispatch from the exact protected campaign input tag
and reverify its tag object/C0. Audit, analysis, and complete collection dispatch from exact
plan-bound `main` and reverify the caller/reusable workflow members against the same C0-derived
workflow root. `audit-pr-validate.yml` alone uses its frozen PR/review triggers and has no mutation
authority.

Implement `tools/validate_audit_pr.py` against separate trusted-base and candidate checkouts. Verify
the fixed reviewer registry, Git object ancestry, configured signature-verification mode/fingerprint,
commitment/reveal/adjudication ordering, actor separation, current reviews, and append-only paths.
Reject premature reveal, cross-sample labels, self-signoff, missing signature evidence, changed old
paths, or any unregistered actor.

Pin the four approved action commits already frozen by the design and do not introduce another
action. Static tests prove all seven live methods have exactly the ownership tuple above and every
public replay command remains offline/non-evidentiary.

```text
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d
actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
```

- [ ] **Step 7: Run capability/workflow GREEN checks**

Run: `uv run pytest tests/campaign/test_github_records.py tests/campaign/test_publication_capability.py tests/campaign/test_publication_workflows.py tests/campaign/test_audit_pr.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py tests/test_public_contract.py -q`

Expected: PASS; `tests/test_ci_contract.py` enumerates exactly 11 workflows at this checkpoint. Tasks
10, 12, and 13 advance the real inventory to 13, 14, and finally 15 respectively.

- [ ] **Step 8: Commit the capability and evidence workflows**

```bash
git add src/laconian_eval/campaign/publication.py \
  src/laconian_eval/campaign/github_records.py \
  tools/benchmark_sample_audit_stage.py \
  tools/benchmark_seal_audit_stage.py \
  tools/benchmark_analyze_stage.py \
  tools/benchmark_verify_stage.py \
  tools/validate_audit_pr.py \
  .github/workflows/benchmark-hard-score.yml \
  .github/workflows/benchmark-evidence.yml \
  .github/workflows/benchmark-audit.yml \
  .github/workflows/benchmark-analysis.yml \
  .github/workflows/benchmark-collect-complete.yml \
  .github/workflows/benchmark-finalize-invalid.yml \
  .github/workflows/audit-pr-validate.yml \
  .github/workflows/benchmark-publication-state.yml \
  tests/campaign/test_publication_capability.py \
  tests/campaign/test_publication_workflows.py \
  tests/campaign/test_audit_pr.py \
  tests/campaign/test_github_records.py \
  tests/campaign/test_workflow_policy.py \
  tests/test_ci_contract.py \
  tests/test_public_contract.py
git commit -m "ci: add authority-bound publication evaluation stages"
```

### Task 8: Define and construct `PublicationPlanV1`

**Files:**
- Modify: `src/laconian_eval/campaign/publication.py`
- Create: `tools/benchmark_prepare_correction.py`
- Create: `tests/campaign/test_publication_plan.py`
- Create: `tests/campaign/test_publication_terminal_records.py`
- Modify: `src/laconian_eval/campaign/collector.py`
- Modify: `src/laconian_eval/campaign/public_projection.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write the failing complete and invalid plan round-trip tests**

Use a local bare Git repository with `main`, the input commit, two commitment merges, two reveal
merges, one adjudication merge, and no result path. Build complete and invalid-prefix plans and
assert deterministic proposed tree and commit IDs.

The following historical model block is retained only as a consolidated predecessor-wire rejection
fixture. Do not implement or export any class shape from this block, including a class whose name
still resembles a production name. Focused tests submit these old `schema_version="1"`, aggregate
checkpoint/finalization, split correction-invalidation, and scalar-root shapes and require strict
failure before any credential or effect. Production Task 8 uses only the exact 05e3d7ba overlay
records and fields from normative §§7.5–7.6.

```python
class GitHubHumanAccountObservationV1(CapsuleModel):
    account_id: StrictPositiveInt
    login: BoundedNonBlankString
    account_type: Literal["User"]
    source_api_receipt_sha256: Sha256
    eligible_merge_team_policy_sha256: Sha256
    observation_sha256: Sha256


class CorrectionDefectRecordV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    correction_attempt: StrictPositiveInt
    affected_pointer_sha256: Sha256
    affected_publication_id: BoundedNonBlankString
    defect_class: Literal[
        "publication_metadata",
        "release_metadata",
        "credential_exposure",
        "nondismissible_hold",
        "invalidation_hold",
        "protocol_authority_drift",
    ]
    defect_code: Literal[
        "publication_object_metadata_diverged",
        "release_object_metadata_diverged",
        "release_finalization_interrupted",
        "post_merge_credential_exposure",
        "nondismissible_invalid_event",
        "accepted_release_invalidation",
        "persistent_protocol_authority_drift",
    ]
    evidence_sha256: Sha256
    record_sha256: Sha256


class CorrectionPhaseLineageV1(CapsuleModel):
    schema_version: Literal["1"]
    prior_campaign_state_sha256: Sha256
    prior_authority_oid: GitObjectId
    prior_phase_sha256: Sha256
    phase_number: StrictPositiveInt
    supersedes_root_sha256: Sha256


class CorrectionPublicationIntentPlanV1(CapsuleModel):
    schema_version: Literal["1"]
    publication_plan: "PublicationPlanV1"
    base_oid: GitObjectId
    head_oid: GitObjectId
    result_tree_oid: GitObjectId
    sealed_bundle_sha256: Sha256
    branch_name: BoundedNonBlankString
    pull_request_marker: BoundedNonBlankString
    plan_sha256: Sha256


class CorrectionReleaseAssetV1(CapsuleModel):
    name: BoundedNonBlankString
    byte_length: StrictNonNegativeInt
    sha256: Sha256


class ProposedLatestPointerConstraintV1(CapsuleModel):
    schema_version: Literal["1"]
    correction_attempt: StrictPositiveInt
    supersedes_pointer_sha256: Sha256
    required_publication_id: BoundedNonBlankString
    required_result_path: RelativePosixPath
    required_bundle_sha256: Sha256
    required_release_status: Literal["released"]
    constraint_sha256: Sha256


class CorrectionReleaseIntentPlanV1(CapsuleModel):
    schema_version: Literal["1"]
    annotated_tag_name: BoundedNonBlankString
    annotated_tag_message: BoundedNonBlankString
    annotated_tag_target_oid: GitObjectId
    tagger_name: Literal["Laconian Benchmark Release"]
    tagger_email: Literal["benchmark-release@laconian.invalid"]
    tagger_timestamp: CanonicalTimestamp
    annotated_tag_bytes_sha256: Sha256
    expected_tag_object_oid: GitObjectId
    draft_release_name: BoundedNonBlankString
    draft_release_body: BoundedNonBlankString
    draft_release_marker: BoundedNonBlankString
    require_immutable_release: Literal[True]
    immutable_release_policy_sha256: Sha256
    assets: tuple[CorrectionReleaseAssetV1, CorrectionReleaseAssetV1]
    plan_sha256: Sha256


class CorrectionEffectActorsV1(CapsuleModel):
    schema_version: Literal["1"]
    publisher_app: GitHubAppInstallationIdentityV1
    release_finalizer_app: GitHubAppInstallationIdentityV1


class CorrectionAssetIdempotencyV1(CapsuleModel):
    asset_name: BoundedNonBlankString
    asset_sha256: Sha256
    effect_key: Sha256


class CorrectionPublicationIdempotencyKeysV1(CapsuleModel):
    schema_version: Literal["1"]
    intent_cas_key: Sha256
    publication_effect_key: Sha256
    publication_receipt_cas_key: Sha256
    merge_receipt_cas_key: Sha256
    publication_invalidation_receipt_cas_key: Sha256


class CorrectionReleaseIdempotencyKeysV1(CapsuleModel):
    schema_version: Literal["1"]
    tag_effect_key: Sha256
    draft_release_effect_key: Sha256
    asset_effects: tuple[CorrectionAssetIdempotencyV1, CorrectionAssetIdempotencyV1]
    publish_effect_key: Sha256
    final_verification_effect_key: Sha256
    tag_receipt_cas_key: Sha256
    release_receipt_cas_key: Sha256
    finalization_receipt_cas_key: Sha256
    release_invalidation_receipt_cas_key: Sha256


class CorrectionCredentialExposureWithdrawalV1(CapsuleModel):
    schema_version: Literal["1"]
    latest_status: Literal["withdrawn_due_to_credential_exposure"]
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1
    incident_root_sha256: Sha256
    contaminated_tag_root_sha256: Sha256
    contaminated_release_root_sha256: Sha256
    contaminated_history_root_sha256: Sha256
    withdrawal_sha256: Sha256


class NondismissibleHeldReleasedConsumptionV1(CapsuleModel):
    kind: Literal["nondismissible"]
    hold_id: BoundedNonBlankString
    hold_root_sha256: Sha256
    nondismissible_evidence_sha256: Sha256
    hold_admission_event_sha256: Sha256
    consumption_sha256: Sha256


class ExposureHeldReleasedConsumptionV1(CapsuleModel):
    kind: Literal["exposure"]
    hold_id: BoundedNonBlankString
    hold_root_sha256: Sha256
    credential_exposure_incident_id: BoundedNonBlankString
    incident_root_sha256: Sha256
    terminal_containment_root_sha256: Sha256
    credential_exposure_evidence_sha256: Sha256
    terminal_exposure_progress_and_evidence_root_sha256: Sha256
    consumption_sha256: Sha256


class InvalidationHeldReleasedConsumptionV1(CapsuleModel):
    kind: Literal["invalidation"]
    hold_id: BoundedNonBlankString
    hold_root_sha256: Sha256
    invalidation_evidence_sha256: Sha256
    prior_release_invalidation_event_path: RelativePosixPath
    prior_release_invalidation_event_sha256: Sha256
    consumption_sha256: Sha256


class DriftHeldReleasedConsumptionV1(CapsuleModel):
    kind: Literal["drift"]
    hold_id: BoundedNonBlankString
    hold_root_sha256: Sha256
    protocol_authority_drift_evidence_sha256: Sha256
    prior_drift_observation_event_sha256: Sha256
    consumption_sha256: Sha256


HeldReleasedConsumptionV1 = Annotated[
    NondismissibleHeldReleasedConsumptionV1
    | ExposureHeldReleasedConsumptionV1
    | InvalidationHeldReleasedConsumptionV1
    | DriftHeldReleasedConsumptionV1,
    Field(discriminator="kind"),
]


class CorrectionIntentV1(CapsuleModel):
    schema_version: Literal["CorrectionIntentV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    defect_class: Literal[
        "publication_metadata",
        "release_metadata",
        "credential_exposure",
        "nondismissible_hold",
        "invalidation_hold",
        "protocol_authority_drift",
    ]
    defect_code: Literal[
        "publication_object_metadata_diverged",
        "release_object_metadata_diverged",
        "release_finalization_interrupted",
        "post_merge_credential_exposure",
        "nondismissible_invalid_event",
        "accepted_release_invalidation",
        "persistent_protocol_authority_drift",
    ]
    defect_evidence_sha256: Sha256
    authority_parent_state: Literal["RELEASED", "RELEASE_BLOCKED"]
    phase_lineage: CorrectionPhaseLineageV1
    held_released_consumption: HeldReleasedConsumptionV1 | None
    correction_publication_plan: CorrectionPublicationIntentPlanV1
    correction_release_plan: CorrectionReleaseIntentPlanV1
    prior_latest_pointer: "LatestPublicationPointerV1"
    proposed_latest_pointer_constraint: ProposedLatestPointerConstraintV1
    allowed_effect_actors: CorrectionEffectActorsV1
    publication_idempotency_keys: CorrectionPublicationIdempotencyKeysV1
    release_idempotency_keys: CorrectionReleaseIdempotencyKeysV1
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1 | None
    credential_exposure_withdrawal: CorrectionCredentialExposureWithdrawalV1 | None
    created_at: CanonicalTimestamp
    intent_sha256: Sha256


class BlockedReleaseObjectsV1(CapsuleModel):
    schema_version: Literal["1"]
    failure_phase: Literal[
        "pre_tag",
        "tag_created",
        "draft_created",
        "assets_partial",
        "assets_complete",
        "publish_unverified",
        "published_divergent",
    ]
    planned_tag_name: BoundedNonBlankString
    observed_tag_object_sha: GitObjectId | None
    observed_release_id: StrictPositiveInt | None
    observed_release_is_draft: StrictBool | None
    observed_asset_root_sha256: Sha256 | None
    immutable_release_verification_sha256: Sha256 | None
    evidence_sha256: Sha256


class ResultMergeInvalidatedBlockedOriginV1(CapsuleModel):
    kind: Literal["result_merge_invalidated"]
    postmerge_admission_failure_sha256: Sha256
    contaminated_merge_oid: GitObjectId
    contaminated_result_tree_oid: GitObjectId
    no_release_effects_evidence_sha256: Sha256
    origin_sha256: Sha256


class ReleasePlanInvalidatedBlockedOriginV1(CapsuleModel):
    kind: Literal["release_plan_invalidated"]
    release_defect_evidence_sha256: Sha256
    blocked_release_objects: BlockedReleaseObjectsV1
    origin_sha256: Sha256


ReleaseBlockedOriginV1 = Annotated[
    ResultMergeInvalidatedBlockedOriginV1 | ReleasePlanInvalidatedBlockedOriginV1,
    Field(discriminator="kind"),
]


class LatestPublicationPointerV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    successful_correction_attempt: StrictNonNegativeInt
    publication_id: BoundedNonBlankString
    release_status: Literal["released", "release_blocked"]
    bundle_kind: Literal["complete"]
    result_path: RelativePosixPath
    bundle_sha256: Sha256
    publication_plan_sha256: Sha256
    publication_pr_number: StrictPositiveInt
    merge_commit_sha: GitObjectId
    result_tag_name: BoundedNonBlankString | None
    tag_object_sha: GitObjectId | None
    release_id: StrictPositiveInt | None
    release_receipt_sha256: Sha256 | None
    release_blocked_origin: ReleaseBlockedOriginV1 | None
    pointer_sha256: Sha256


class CorrectionProgressV1(CapsuleModel):
    schema_version: Literal["1"]
    correction_attempt: StrictPositiveInt
    base_pointer_sha256: Sha256
    defect_record_sha256: Sha256
    phase: Literal[
        "intent_authorized",
        "publication_recorded",
        "merge_recorded",
        "tag_recorded",
        "release_recorded",
    ]
    intent_sha256: Sha256
    publication_receipt_sha256: Sha256 | None
    merge_receipt_sha256: Sha256 | None
    tag_receipt_sha256: Sha256 | None
    release_receipt_sha256: Sha256 | None
    progress_sha256: Sha256


class CorrectionLineageV1(CapsuleModel):
    schema_version: Literal["1"]
    source_campaign_state: Literal["RELEASED", "RELEASE_BLOCKED"]
    correction_attempt: StrictPositiveInt
    defect_record_sha256: Sha256
    supersedes_pointer_sha256: Sha256
    supersedes_release_status: Literal["released", "release_blocked"]
    supersedes_bundle_kind: Literal["complete"]
    supersedes_publication_id: BoundedNonBlankString
    supersedes_result_path: RelativePosixPath
    supersedes_bundle_sha256: Sha256
    supersedes_publication_plan_sha256: Sha256
    supersedes_publication_pr_number: StrictPositiveInt
    supersedes_merge_commit_sha: GitObjectId
    supersedes_result_tag_name: BoundedNonBlankString | None
    supersedes_tag_object_sha: GitObjectId | None
    supersedes_release_id: StrictPositiveInt | None
    supersedes_release_receipt_sha256: Sha256 | None
    supersedes_release_blocked_origin: ReleaseBlockedOriginV1 | None
    lineage_sha256: Sha256


class CorrectionPublicationReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    correction_intent_sha256: Sha256
    branch_receipt: "PublicationBranchReceiptV1"
    pull_request_receipt: "PublicationPRReceiptV1"
    receipt_sha256: Sha256


class CorrectionMergeReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    correction_publication_receipt_sha256: Sha256
    publication_merge_receipt: "PublicationMergeReceiptV1"
    correction_intent_sha256: Sha256
    receipt_sha256: Sha256


class CorrectionTagReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    correction_intent_sha256: Sha256
    correction_release_plan_sha256: Sha256
    executable_release_plan: "ExecutableResultReleasePlanV1"
    executable_release_plan_sha256: Sha256
    security_attestor_receipt: "SecurityAttestorReceiptV1"
    security_attestor_receipt_sha256: Sha256
    tag_receipt: "TagReceiptV1"
    receipt_sha256: Sha256


class CorrectionReleaseReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    correction_intent_sha256: Sha256
    correction_release_plan_sha256: Sha256
    executable_release_plan_sha256: Sha256
    security_attestor_receipt_sha256: Sha256
    correction_tag_receipt_sha256: Sha256
    draft_release_receipt: "DraftReleaseReceiptV1"
    asset_receipts: tuple["ReleaseAssetReceiptV1", "ReleaseAssetReceiptV1"]
    publish_receipt: "PublishReceiptV1"
    final_verification_receipt: "FinalReleaseVerificationReceiptV1"
    release_finalizer_operation_set: "ReleaseFinalizerOperationSetV1"
    release_no_later_effects: "ReleaseNoLaterEffectsEvidenceV1"
    receipt_sha256: Sha256


class CorrectionFinalizationV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    correction_intent_sha256: Sha256
    correction_release_plan_sha256: Sha256
    executable_release_plan_sha256: Sha256
    security_attestor_receipt_sha256: Sha256
    correction_release_receipt_sha256: Sha256
    durable_authority_checkpoint: "RejectedDurableAuthorityCheckpointFixture"
    durable_authority_checkpoint_sha256: Sha256
    prior_latest_pointer_sha256: Sha256
    final_latest_pointer: "LatestPublicationPointerV1"
    finalization_sha256: Sha256


class CorrectionInvalidationIntentParentV1(CapsuleModel):
    parent_phase: Literal["intent"]
    correction_intent_sha256: Sha256


class CorrectionInvalidationPublicationReceiptParentV1(CapsuleModel):
    parent_phase: Literal["publication_receipt"]
    correction_intent_sha256: Sha256
    correction_publication_receipt_sha256: Sha256


CorrectionInvalidationParentV1 = Annotated[
    CorrectionInvalidationIntentParentV1 | CorrectionInvalidationPublicationReceiptParentV1,
    Field(discriminator="parent_phase"),
]


# Rejection fixtures only: the approved wire uses the single closed CorrectionInvalidationV1
# record defined by the 05e3d7ba overlay, never these predecessor unions/classes.
class RejectedCorrectionPublicationNoPRInvalidationFixture(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    kind: Literal["correction_publication_invalidation"]
    publication_outcome: Literal["unmerged_invalid"]
    observation_kind: Literal["no_pr"]
    cause: Literal["ordinary", "credential_exposure"]
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1 | None
    reason: Literal["correction_publication_invalid"]
    correction_intent_sha256: Sha256
    publisher_actor: GitHubAppInstallationIdentityV1
    proposed_latest_pointer_constraint_sha256: Sha256
    authenticated_pr_absence_observation_sha256: Sha256
    discovered_branch_receipt: PublicationBranchReceiptV1 | None
    discovered_pull_request_projection_sha256: Sha256 | None
    discovered_branch_and_pr_inventory_root_sha256: Sha256
    no_later_effects_evidence_sha256: Sha256
    invalidation_sha256: Sha256


class RejectedCorrectionPublicationClosedPRInvalidationFixture(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    kind: Literal["correction_publication_invalidation"]
    publication_outcome: Literal["unmerged_invalid"]
    observation_kind: Literal["closed_pr"]
    cause: Literal["ordinary", "credential_exposure"]
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1 | None
    reason: Literal["correction_publication_invalid"]
    parent: CorrectionInvalidationParentV1
    publisher_actor: GitHubAppInstallationIdentityV1
    proposed_latest_pointer_constraint_sha256: Sha256
    close_receipt: "PublicationCloseReceiptV1"
    discovered_branch_and_pr_root_sha256: Sha256
    no_later_effects_evidence_sha256: Sha256
    invalidation_sha256: Sha256


class RejectedCorrectionPublicationMergedInvalidationFixture(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    kind: Literal["correction_publication_invalidation"]
    publication_outcome: Literal["merged_invalid"]
    observation_kind: Literal["merged_pr"]
    cause: Literal["ordinary", "credential_exposure"]
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1 | None
    parent: CorrectionInvalidationParentV1
    proposed_latest_pointer_constraint_sha256: Sha256
    pull_request_number: StrictPositiveInt
    immutable_pull_request_root_sha256: Sha256
    base_oid: GitObjectId
    head_oid: GitObjectId
    observed_merge_oid: GitObjectId
    observed_merge_parents: tuple[GitObjectId, GitObjectId]
    expected_result_tree_oid: GitObjectId
    observed_result_tree_oid: GitObjectId
    merge_actor: GitHubHumanAccountObservationV1
    merge_method: Literal["merge_commit"]
    required_checks_root_sha256: Sha256
    approvals_root_sha256: Sha256
    current_main_oid: GitObjectId
    request_receipts_root_sha256: Sha256
    postmerge_admission_failure_sha256: Sha256
    contaminated_exposure_root_sha256: Sha256
    no_later_effects_evidence_sha256: Sha256
    invalidation_sha256: Sha256


RejectedCorrectionPublicationInvalidationFixture = Annotated[
    RejectedCorrectionPublicationNoPRInvalidationFixture
    | RejectedCorrectionPublicationClosedPRInvalidationFixture
    | RejectedCorrectionPublicationMergedInvalidationFixture,
    Field(discriminator="observation_kind"),
]


class RejectedCorrectionReleaseInvalidationFixture(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    correction_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    phase_lineage: CorrectionPhaseLineageV1
    kind: Literal["correction_release_invalidation"]
    cause: Literal["ordinary", "credential_exposure"]
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1 | None
    correction_intent_sha256: Sha256
    correction_release_plan_sha256: Sha256
    correction_merge_receipt_sha256: Sha256
    merge_commit_oid: GitObjectId
    result_tree_oid: GitObjectId
    blocked_release_objects: BlockedReleaseObjectsV1
    reconciliation_receipts_root_sha256: Sha256
    unchanged_latest_pointer_sha256: Sha256
    no_later_effects_evidence_sha256: Sha256
    invalidation_sha256: Sha256


class PublicationPlanV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    publication_attempt: StrictPositiveInt
    correction_lineage: CorrectionLineageV1 | None
    bundle_kind: Literal["complete", "invalid_prefix"]
    bundle_sha256: Sha256
    audit_protocol_sha256: Sha256
    bundle_artifact: ExactArtifactLocatorV1
    input_tag_object_sha: GitObjectId
    input_commit_sha: GitObjectId
    campaign_registry_sha256: Sha256
    protocol_attestation_tag_binding_sha256: Sha256
    workflow_root: Sha256
    main_fallback_liveness_policy_sha256: Sha256
    authority_state_sha256: Sha256
    unresolved_hold_root_sha256: Sha256 | None
    active_credential_exposure_pending_root_sha256: Sha256 | None
    audit_merge_shas: tuple[GitObjectId, ...]
    stop_state_sha256: Sha256 | None
    missing_suffix_sha256: Sha256 | None
    base_ref: Literal["refs/heads/main"]
    base_sha: GitObjectId
    result_path: RelativePosixPath
    expected_files: tuple[PublicFileV1, ...]
    expected_tree_diff_sha256: Sha256
    publication_workflow_path: Literal[".github/workflows/benchmark-publish.yml"]
    publication_workflow_sha256: Sha256
    branch_name: BoundedNonBlankString
    commit_message: BoundedNonBlankString
    commit_timestamp: CanonicalTimestamp
    proposed_tree_oid: GitObjectId
    proposed_head_sha: GitObjectId
    expected_merge_tree_oid: GitObjectId
    merge_method: Literal["merge_commit"]
    expected_merge_parents: tuple[GitObjectId, GitObjectId]
    required_check_names: tuple[BoundedNonBlankString, ...]
    review_policy_sha256: Sha256
    allowed_merge_actor_ids: tuple[StrictPositiveInt, ...]
    branch_ruleset_sha256: Sha256
    pull_request_title: BoundedNonBlankString
    pull_request_body_sha256: Sha256
    plan_sha256: Sha256
```

After all referenced classes are defined, resolve the quoted forward references once with
`CorrectionPublicationIntentPlanV1.model_rebuild()`, `CorrectionIntentV1.model_rebuild()`, and each
of the six correction wrapper classes; no
shadow dict, permissive mapping, or flattened compatibility model is allowed. Canonicalize every
nested record with `extra="forbid"` and compute `intent_sha256` over the complete
`CorrectionIntentV1` while omitting only `intent_sha256`.

Derive both `CorrectionIntentV1.created_at` and
`CorrectionReleaseIntentPlanV1.tagger_timestamp` from the immutable reviewed defect merge commit's
Git committer timestamp: parse its signed epoch seconds plus numeric offset, normalize to integral
UTC, serialize once as `CanonicalTimestamp`, and require the two fields equal. Wall clock, workflow
clock, caller input, locale, and host timezone never participate. Golden tests run under distinct
`TZ`/locale settings and shifted clocks and require identical timestamp, tag bytes/OID, intent, and
USTAR bytes.

Add field-by-field builder tests and mapping assertions. `build_correction_intent` derives
`phase_lineage.prior_campaign_state_sha256`, `prior_authority_oid`, `prior_phase_sha256`, the exact
next `phase_number`, and `supersedes_root_sha256` from reconstructed authority and the latest durable
correction prefix; none is a caller scalar. It embeds the complete class-bound
`PublicationPlanV1`, maps `base_oid == publication_plan.base_sha`,
`head_oid == publication_plan.proposed_head_sha`,
`result_tree_oid == publication_plan.expected_merge_tree_oid`, and
`sealed_bundle_sha256 == publication_plan.bundle_sha256`, then revalidates the exact branch and PR
marker. It also embeds the complete `CorrectionReleaseIntentPlanV1`: the annotated tag targets
exactly `correction_publication_plan.head_oid`, so canonical tag bytes/object OID, draft identity,
immutable-release policy, and ordered assets are deterministic before publication. The intent
contains no actual merge OID or final latest pointer. A changed nested plan field, marker,
base/head/tree/bundle/tag target/object, or a digest-valid but lineage-substituted plan fails.

The builder reconstructs `prior_latest_pointer` from authority and deterministically constructs
only `ProposedLatestPointerConstraintV1`; neither is accepted from CLI/workflow input, and the
constraint deliberately contains no PR number, merge commit, tag object, release ID, receipt, or
other future observation. It selects only the
frozen publisher and release-finalizer `GitHubAppInstallationIdentityV1` records and requires their
App and installation identities to be pairwise distinct. It derives every named key in
`CorrectionPublicationIdempotencyKeysV1` and `CorrectionReleaseIdempotencyKeysV1` under their phase/
effect-specific domains in the same pre-effect intent. All keys across both records are pairwise
distinct, receipt-CAS keys cannot substitute for effect keys or another phase's CAS, and the two
asset-key records repeat the exact aligned release-asset name and digest. Tests delete, duplicate,
reorder, alias, or swap every key and require
failure; there is no generic effect-key collection.

Freeze idempotency derivation as `sha256(domain || CanonicalJSONV1(ordered_preimage))`. Correction
keys use the ordered base `[campaign_id, campaign_registry_sha256, correction_id, publication_id,
phase_lineage_sha256, correction_publication_plan.plan_sha256,
correction_release_plan.plan_sha256, object_or_target_root]`; initial keys use `[campaign_id,
campaign_registry_sha256, publication_id, release_plan_sha256, tag_target_sha,
object_or_target_root]`. The final element is the exact affected branch/PR/merge/tag/draft/asset/
publish/receipt/finalization/invalidation root, never null or a generic phase bag. The closed domains
are one literal per field:

```text
laconian-correction-intent-cas-key-v1\n
laconian-correction-publication-effect-key-v1\n
laconian-correction-publication-receipt-cas-key-v1\n
laconian-correction-merge-receipt-cas-key-v1\n
laconian-correction-publication-invalidation-cas-key-v1\n
laconian-correction-tag-effect-key-v1\n
laconian-correction-draft-effect-key-v1\n
laconian-correction-asset-0-effect-key-v1\n
laconian-correction-asset-1-effect-key-v1\n
laconian-correction-publish-effect-key-v1\n
laconian-correction-final-verification-effect-key-v1\n
laconian-correction-tag-receipt-cas-key-v1\n
laconian-correction-release-receipt-cas-key-v1\n
laconian-correction-finalization-cas-key-v1\n
laconian-correction-release-invalidation-cas-key-v1\n
laconian-initial-release-intent-cas-key-v1\n
laconian-initial-tag-effect-key-v1\n
laconian-initial-draft-effect-key-v1\n
laconian-initial-asset-0-effect-key-v1\n
laconian-initial-asset-1-effect-key-v1\n
laconian-initial-publish-effect-key-v1\n
laconian-initial-final-verification-effect-key-v1\n
laconian-initial-tag-receipt-append-cas-key-v1\n
laconian-initial-draft-receipt-append-cas-key-v1\n
laconian-initial-asset-0-receipt-key-v1\n
laconian-initial-asset-1-receipt-key-v1\n
laconian-initial-assets-receipt-append-cas-key-v1\n
laconian-initial-publish-receipt-append-cas-key-v1\n
laconian-initial-release-finalization-cas-key-v1\n
laconian-initial-release-invalidation-cas-key-v1\n
```

For each asset row, `object_or_target_root` is CanonicalJSONV1 of `[ordinal, asset_name,
asset_sha256]`; all other rows use their typed target digest. Check in golden preimage bytes and
digests for every line, plus reorder/omission/cross-domain/cross-campaign/cross-plan negatives.
The initial and correction `final_verification_effect_key` values are preauthorized,
pairwise-distinct from publish/finalization/receipt keys, and bind the
`ReleaseEffectResultV1(effect_kind="final_verification")`; no final-verification append key or
authority path exists.

Freeze every Publication-owned authority/evidence self hash as
`SHA256(UTF8(literal_domain) || CanonicalJSONV1(record without exactly sole_self_field))`:

| Record | literal LF-terminated domain | sole self field |
|---|---|---|
| `CorrectionPublicationIntentPlanV1` | `laconian-correction-publication-intent-plan-v1\n` | `plan_sha256` |
| `ProposedLatestPointerConstraintV1` | `laconian-proposed-latest-pointer-constraint-v1\n` | `constraint_sha256` |
| `CorrectionReleaseIntentPlanV1` | `laconian-correction-release-intent-plan-v1\n` | `plan_sha256` |
| `CorrectionCredentialExposureWithdrawalV1` | `laconian-correction-credential-exposure-withdrawal-v1\n` | `withdrawal_sha256` |
| `NondismissibleHeldReleasedConsumptionV1` | `laconian-nondismissible-held-released-consumption-v1\n` | `consumption_sha256` |
| `ExposureHeldReleasedConsumptionV1` | `laconian-exposure-held-released-consumption-v1\n` | `consumption_sha256` |
| `InvalidationHeldReleasedConsumptionV1` | `laconian-invalidation-held-released-consumption-v1\n` | `consumption_sha256` |
| `DriftHeldReleasedConsumptionV1` | `laconian-drift-held-released-consumption-v1\n` | `consumption_sha256` |
| `CorrectionIntentV1` | `laconian-correction-intent-v1\n` | `intent_sha256` |
| `BlockedReleaseObjectsV1` | `laconian-blocked-release-objects-v1\n` | `evidence_sha256` |
| `ResultMergeInvalidatedBlockedOriginV1` | `laconian-result-merge-invalidated-blocked-origin-v1\n` | `origin_sha256` |
| `ReleasePlanInvalidatedBlockedOriginV1` | `laconian-release-plan-invalidated-blocked-origin-v1\n` | `origin_sha256` |
| `LatestPublicationPointerV1` | `laconian-latest-publication-pointer-v1\n` | `pointer_sha256` |
| `CorrectionProgressV1` | `laconian-correction-progress-v1\n` | `progress_sha256` |
| `CorrectionLineageV1` | `laconian-correction-lineage-v1\n` | `lineage_sha256` |
| `CorrectionPublicationReceiptV1` | `laconian-correction-publication-receipt-v1\n` | `receipt_sha256` |
| `CorrectionMergeReceiptV1` | `laconian-correction-merge-receipt-v1\n` | `receipt_sha256` |
| `CorrectionTagReceiptV1` | `laconian-correction-tag-receipt-v1\n` | `receipt_sha256` |
| `CorrectionReleaseReceiptV1` | `laconian-correction-release-receipt-v1\n` | `receipt_sha256` |
| `CorrectionFinalizationV1` | `laconian-correction-finalization-v1\n` | `finalization_sha256` |
| `CorrectionInvalidationV1` | `laconian-correction-invalidation-v1\n` | `correction_invalidation_sha256` |
| `InitialPreauthorizedResultReleasePlanV1` | `laconian-initial-preauthorized-result-release-plan-v1\n` | `preauthorized_release_plan_sha256` |
| `ExecutableResultReleasePlanV1` | `laconian-executable-result-release-plan-v1\n` | `executable_release_plan_sha256` |
| `ResultReleaseIntentV1` | `laconian-result-release-intent-v1\n` | `intent_sha256` |
| `ImmutableReleaseVerificationV1` | `laconian-immutable-release-verification-v1\n` | `verification_sha256` |
| `ReleasePlanInvalidationEvidenceV1` | `laconian-release-plan-invalidation-evidence-v1\n` | `release_plan_invalidation_evidence_sha256` |
| `InitialPublicationInvalidationV1` | `laconian-initial-publication-invalidation-v1\n` | `invalidation_sha256` |
| `InitialPublicationFinalizationV1` | `laconian-initial-publication-finalization-v1\n` | `finalization_sha256` |
| `PublicationReleaseInventoryObservationV1` | `laconian-publication-release-inventory-observation-v1\n` | `release_inventory_observation_sha256` |

Check in independently hand-authored literal canonical-byte fixtures and expected digests for every
row; tests cannot call production serializers/builders to create expected bytes and reject alternate
domains, missing/doubled LF, wrong omitted field, nested self-hash omission, and cross-record replay.

`held_released_consumption` is null if and only if the reconstructed parent has no unresolved hold.
It is forbidden for `RELEASE_BLOCKED`. For a held `RELEASED` parent it is exactly one strict
discriminated nondismissible/exposure/invalidation/drift variant, reproduces the current hold ID/root, and
binds the variant-specific typed evidence and accepted event root. The intent CAS clears exactly
that hold root; wrong kind, evidence, event, hold ID/root, null-with-hold, nonnull-without-hold, or a
successor that preserves/substitutes the hold fails. Ordinary metadata correction paths require the
active exposure incident ID/pending-root pair to be null.
The defect class/code/evidence matrix is closed and one-to-one with the consumer discriminator:
`nondismissible_hold/nondismissible_invalid_event -> nondismissible`,
`credential_exposure/post_merge_credential_exposure -> exposure`,
`invalidation_hold/accepted_release_invalidation -> invalidation`, and
`protocol_authority_drift/persistent_protocol_authority_drift -> drift`. Metadata defects require
no hold consumer. Tests reject every cross-pairing even when the component digests are individually
valid. Consumer records bind only already accepted hold-admission, terminal exposure progress/
evidence, prior invalidation, or prior drift-observation events. They never contain the future
consuming `CORRECTION_INTENT_AUTHORIZED` event hash, intent self hash, or successor authority OID.
Literal preimage goldens prove the hold/evidence -> intent -> event dependency is acyclic.
For the invalidation consumer, `prior_release_invalidation_event_path` is derived from the active
release-blocked pointer's accepted authority member and must resolve under that campaign's exact
`events/` or initial-publication invalidation member selected by `ReleaseBlockedOriginV1`;
descriptor-read canonical bytes must hash to `prior_release_invalidation_event_sha256` and equal the
origin's accepted event/evidence binding. Caller paths, future correction events, and same-digest
bytes outside that exact authority member are rejected.

`terminal_exposure_consumption` is nonnull for either `RELEASED` or `RELEASE_BLOCKED` if and only if
the defect is exactly `credential_exposure/post_merge_credential_exposure`; every ordinary defect
requires it null and requires the active pair already null. The Runtime-owned strict projection binds incident ID,
pending digest/root, predecessor active-progress root, terminal effect-chain/receipt root, final
`CredentialExposureIncidentEvidenceV1`, and optional concurrent-drift root. The intent CAS verifies
the predecessor active pair, atomically clears both active fields, and consumes the matching hold
when one exists. A no-hold exposure has `held_released_consumption=null`; with a current hold the
consumer must be the exposure variant and all incident/evidence/event roots must equal the terminal
projection. A `RELEASED` exposure additionally requires `credential_exposure_withdrawal` and exact
equality to that terminal projection; a `RELEASE_BLOCKED` exposure requires withdrawal null. The
withdrawal contains exactly the status and incident root,
contaminated tag root, contaminated Release root, contaminated history root, and self digest. It is
null for `RELEASE_BLOCKED` and every metadata defect. Tests cover both parent states and reject a missing conditional record,
one on an ineligible parent/defect, a nonwithdrawn status, any substituted contaminated root, or an
unknown nested field. Complete typed nested plans and their own exact digests are the only plan
authority; no opaque aggregate plan hash is accepted.

The correction authority subtree remains exactly six ordered member positions:
`intent.json`, `publication-receipt.json`, `merge-receipt.json`, `tag-receipt.json`,
`release-receipt.json`, and exactly one of `finalization.json|invalidation.json` in the terminal
position. The complete correction release plan remains in immutable `intent.json`; no post-merge
release-intent record or seventh path exists. `INVALID_EVENT_HELD` is forbidden while any
correction ID has a nonterminal intent/publication/merge/tag/release prefix. Only a bare `RELEASED`
campaign may later consume a hold in a new `CORRECTION_INTENT_AUTHORIZED` CAS; no later correction
phase is a hold consumer. Add state-table, mutation, and replay tests for every nonterminal prefix.
`CorrectionMergeReceiptV1` verifies the actual merge
has parents exactly `[correction_publication_plan.base_oid,
correction_publication_plan.head_oid]`, has the exact preauthorized result tree, and retains the
earlier intent digest unchanged. The correction annotated tag targets the deterministic approved
`head_oid`, not unknown `M`, so its raw bytes and object OID are precomputable in the original
intent. Only `CorrectionFinalizationV1` constructs a full `LatestPublicationPointerV1` from verified
receipts. The wrappers map one-to-one to approved correction events:
`CORRECTION_INTENT_AUTHORIZED`, `CORRECTION_PUBLICATION_RECORDED`,
`CORRECTION_MERGE_RECORDED`, `CORRECTION_TAG_RECORDED`, `CORRECTION_RELEASE_RECORDED`, and either
`CORRECTION_RESULT_RELEASED` or the applicable typed `CORRECTION_INVALIDATED`. Every wrapper binds
campaign ID, `campaign_registry_sha256`, correction ID, publication ID, exact prior authority OID,
prior phase hash, next phase number, supersedes root, typed payload, and its own digest. Their exact
digest domains are respectively `laconian-correction-intent-v1\n`,
`laconian-correction-publication-receipt-v1\n`, `laconian-correction-merge-receipt-v1\n`,
`laconian-correction-tag-receipt-v1\n`, `laconian-correction-release-receipt-v1\n`,
`laconian-correction-finalization-v1\n`,
`laconian-correction-publication-invalidation-v1\n`, and
`laconian-correction-release-invalidation-v1\n`; each canonical
preimage omits only its own named self-digest field. Recovery accepts only a contiguous prefix with
the exact expected-OID predecessor and phase lineage. Missing, duplicate, reordered, replayed,
cross-campaign, cross-registry, cross-correction, or alternate-path records fail.

Initial plans and ordinary correction plans require both nullable authority roots null. The sole
exception is the dedicated held-`RELEASED` correction gate above: exactly one current unresolved
hold is consumed through `HeldReleasedConsumptionV1`, the active exposure pair remains null, and the
same intent CAS clears that exact hold. These fields remain explicit so a caller cannot erase a
blocked predecessor while hashing the plan. The registry, companion binding, workflow inventory and
fallback policy fields must exactly equal reconstructed canonical authority; no builder accepts them
as caller scalars.

`expected_merge_parents` is exactly `[base_sha, proposed_head_sha]`. The plan binds the expected
merge tree but never claims to know the eventual merge commit. V1 accepts only literal
`merge_commit`; squash, rebase, any alternate mode, a pre-merge test SHA, or a caller-selected merge mode is
rejected.

For every plan, validate `publication_id` against
`[a-z0-9][a-z0-9-]{0,95}`. Derive `publication_attempt` only from reconstructed canonical authority:
it is `1` when that publication ID has no accepted invalidation and otherwise exactly one greater
than its contiguous, digest-chained accepted invalidation count. Derive `branch_name` exactly as
`benchmark-result-pr/{publication_id}-a{publication_attempt}-{base_sha[:12]}-{bundle_sha256[:12]}`.
It must match
`benchmark-result-pr/[a-z0-9][a-z0-9-]{0,95}-a[1-9][0-9]*-[0-9a-f]{12}-[0-9a-f]{12}`, be new, and may not equal
or prefix-match `main`, `benchmark-authority/`, any tag ref, dot component, lock suffix, or other
protected namespace. No caller supplies it. For an initial publication,
`publication_id == campaign_id`, `correction_lineage is None`, and the result path is
`benchmarks/results/{campaign_id}`. For correction attempt `N`, `publication_id` is exactly
`{campaign_id}-correction-{N}`, the branch/result path/tag/Release use that new publication ID, and
every superseded field is required. `correction_attempt` is derived from the full accepted
`corrections/` directory history as `max(all started and terminal attempt ordinals) + 1`, not from
the latest pointer; every copied supersedes field must equal
that pointer, including `supersedes_bundle_kind` and the strict blocked-origin union.
`supersedes_release_status == "released"` requires all four released tag/release fields and null
`release_blocked_origin`; `"release_blocked"` requires all four released fields null and exactly one
nonnull origin variant. `result_merge_invalidated` binds `PostMergeAdmissionFailureV1`, contaminated
merge/tree, and no-release proof; `release_plan_invalidated` binds the release defect plus
`BlockedReleaseObjectsV1`. Validate its phase-dependent field presence
and preserve every observed orphan tag/draft/asset identity without granting release authority,
independently of `source_campaign_state`. Complete plans require the ordered full audit merge set and
null STOP fields. Complete plans copy the identical Evaluation-owned
`audit_protocol_sha256: Sha256` from the verified bundle/inventory lineage and reverify it against
Runtime Task 2's peeled-C0 audit member; no plan builder accepts that value independently.
Invalid-prefix plans retain the same campaign-registry field even when no audit output exists and
require empty absent-audit suffixes plus exact STOP and
missing-suffix hashes.

Bind `publication_attempt` into the commit message, PR title/body, proposed head, plan digest,
intent, effect receipt, invalidation, close plan/receipt, and every authority mutation. An accepted
invalidation permanently consumes its attempt even if `base_sha` and bundle bytes did not change;
the next plan therefore has a new branch and head without updating, deleting, or force-pushing the
old branch. Reject gaps, replayed attempts, caller-supplied attempts, or an invalidation chain from a
different publication ID.

An initial result directory is byte-for-byte the sealed bundle. A correction result directory adds
exactly one plan-owned canonical `correction-lineage.json` beside the byte-for-byte corrected bundle
projection. `PublicationPlanV1.expected_files`, tree diff, commit, merge receipt, release plan, and
release assets all hash that file. It is forbidden in initial/invalid-prefix publication and cannot
be supplied from model output.

- [ ] **Step 2: Add failing ancestry, movement, and collision tests**

Reject a base other than current `main`, a base that omits the input commit or any present audit
merge, an existing result path, existing branch, wrong bundle digest, extra tree member, symlink,
base movement before publication, proposed-head movement, unclean worktree, noncanonical commit
metadata, and mismatched publication workflow hash.
Reject every branch spelling not equal to the one derivation above, including case changes,
additional slashes, shortened/full caller hashes, ref escapes, an existing ref, or a branch whose
base/bundle prefixes do not match the plan.

Also test a first correction after `RELEASED`, a first correction after `RELEASE_BLOCKED`, and a
second correction. Include both histories: released initial -> correction 1 merged but release
blocked while campaign state remains `RELEASED` -> correction 2 supersedes a `release_blocked`
pointer; and blocked initial -> correction 1 released -> `CORRECTION_RESULT_RELEASED` changes
campaign state to `RELEASED` -> correction 2 supersedes a `released` pointer. Reject a sequence gap/reuse, missing defect record, a superseded digest not found
at the exact prior result path, partial tag/release field sets, editing/removing the old result path,
reusing an old branch/tag/publication ID, or a correction whose lineage does not point to the latest
immutable publication for this campaign.
Exercise every blocked release phase and reject hiding an observed orphan object, treating a draft
as released, or deleting/reusing the planned blocked tag/release during correction.
Also reject missing/changed bundle-kind fields or a correction that changes bundle kind. Correction
lineage requires `bundle_kind=complete`; `INVALID_PREFIX_MERGED` and
`INVALID_PREFIX_MERGED_INVALID` are terminal and cannot acquire analysis, correction, release,
documentation, website, release-note, or social-promotion authority.

The only accepted defect source is a human-authored and reviewed file at
  `benchmarks/corrections/{campaign_id}/{N}/defect.json`, merged to `main` as a one-file PR. There is
  no separate `correction_defect` state event or authority mutation: the single
  `CORRECTION_INTENT_AUTHORIZED` CAS verifies the protected-main merge, embeds the strict defect
  record as intent evidence, and binds its digest. Its sequence and affected pointer are derived,
  not operator-selected. A defect in generation, scoring, judging,
  audit, statistical methods, source evidence other than the exact post-merge credential-exposure
  protocol, campaign authority, public
  projection/report rendering, or trusted code/workflow is not correctable under this lineage: fail
  closed and require a new reviewed campaign.
Require `publication_metadata` to pair only with `publication_object_metadata_diverged`; require
`release_metadata` to pair only with `release_object_metadata_diverged` or
`release_finalization_interrupted`; and require `credential_exposure` to pair only with
`post_merge_credential_exposure` plus canonical incident/containment evidence. Unknown/free-form
codes and a code/class mismatch fail before correction authority.

Write the durable correction-prefix tests against the sole authority subtree
`corrections/<correction-id>/`. It admits the ordered members `intent.json`,
`publication-receipt.json`, `merge-receipt.json`, `tag-receipt.json`, `release-receipt.json`, and
exactly one of `finalization.json` or `invalidation.json`. Before any external correction effect,
`CORRECTION_INTENT_AUTHORIZED` installs `intent.json` by one expected-OID CAS. The intent binds the
prior authority OID/state/latest pointer, explicit `supersedes` root, complete publication plan,
branch and PR marker, expected result tree, deterministic proposed-latest-pointer constraint,
allowed actors, reviewed defect evidence, conditional held-`RELEASED` consumer, and distinct
publication effect/receipt keys. It binds the complete deterministic correction release plan,
including tag target equal to approved `head_oid`, but no unknown actual merge observation. The
accepted merge wrapper verifies actual `M`/parents/tree against that immutable intent and does not
embed or create another intent. Only finalization constructs the complete
`LatestPublicationPointerV1` from verified receipts. No unpersisted local plan authorizes a write.

Test all durable prefixes and both closed invalidation kinds.
`CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=unmerged_invalid)` and
`CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=merged_invalid)` are allowed only with
`intent.json` or
`publication-receipt.json` and exact `publication_outcome` of `unmerged_invalid` or
`merged_invalid`; `merged_invalid` additionally requires `PostMergeAdmissionFailureV1`, contaminated
merge/exposure, and no-tag/no-Release/no-asset/no-latest/no-docs/no-social evidence.
`CORRECTION_INVALIDATED(kind=correction_release_invalidation)` is allowed only after a valid
`merge-receipt.json` and binds every
created or adopted tag/Release/asset object plus reconciliation evidence. Either invalidation is
terminal for that correction ID, leaves the prior latest pointer unchanged, and requires a new
correction ID. After `merged_invalid`, the new intent must supersede both the failed correction root
and contaminated merge/exposure root. Cross-phase use, a generic invalidation alias, both terminal
members, or an invalidation after finalization fails.

Implement the approved single closed `CorrectionInvalidationV1` wire record; the predecessor
publication/release unions above remain parser-rejection fixtures only. All nullable fields are
present and the validator enforces the exact outcome matrix from §7.5: `unmerged_invalid`,
`merged_invalid`, `fenced_write_ambiguity`, and `reconciliation_unavailable` are publication-only;
the release variant has null publication outcome/disposition fields and a nonnull exact
`ReleasePlanInvalidationEvidenceV1` root. No scalar root validates without its required nested exact
object.

For `unmerged_invalid`, require the exact shared `PublicationPRTerminalDispositionV1(outcome=no_pr|
closed)`, all discovered intent-bound branch/PR objects, publication no-later evidence, and
ordinary-premerge containment finality. `merged_invalid` requires the exact
`PostMergeAdmissionFailureV1`: direct normal admission has no containment/disposition/no-later
record, while an active-containment ordinary or ambiguity race carries the approved merge-won
finality and its exact branch-specific fields. `fenced_write_ambiguity` requires
`invalidation_cause=publication_write_ambiguity_fenced`, the nested
`PublicationFencedWriteAmbiguityV1(terminal_route=correction_premerge)`, and write-ambiguity
premerge containment finality. `reconciliation_unavailable` carries the sealed publisher
disposition set/receipt and empty release-authorization-ledger root, makes no stable external-state
claim, and uses ordinary-premerge or merge-won containment finality according to the exact
`no_pr|closed|already_merged` disposition.

Every containment-form publication outcome binds the exact containment finality, successor
merge-denylist root, source/immediate authority parents, and active containment root transition from
the exact `PublicationTerminalContainmentIntentV1.intent_sha256` terminal-containment intent digest
to null; it never substitutes the underlying `CorrectionIntentV1` digest. The terminal CAS
byte-preserves the denylist. Direct normal
`merged_invalid` has no containment/fence fields and does not mutate the denylist. A correction
release invalidation is allowed only after the valid merge receipt, has all containment/fence and
publication fields null, and binds the exact release operation set/reconciliation evidence and
unchanged prior/proposed latest-pointer roots. Its reconciliation-unavailable branch carries the
sealed failure-only operation set/receipt and a null release-no-later root.

Apply the exact closed cause rules: ordinary forbids emergency objects; credential exposure
requires the matching terminal consumption and atomically clears the incident/pending pair;
protocol drift requires current-parent drift evidence; write ambiguity and publisher/release
reconciliation unavailability are legal only in their named rows. `recorded_at` equals the selected
authenticated no-later closure, postmerge failure, or sealed unavailable-ledger time. Tests cover
every outcome × cause × parent phase, branch/PR response loss, merge-before-close races, root
clearance/denylist preservation, mixed/null fields, half-null exposure, hidden holds or objects,
cross-incident roots, pointer advancement, terminal replay, and rejection after finalization.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_plan.py tests/campaign/test_publication_terminal_records.py tests/test_public_contract.py -q`

Expected: FAIL because the Task 7 capability module does not yet define publication plans,
correction intent, or their deterministic builders.

- [ ] **Step 4: Implement deterministic plan construction**

Add:

```python
def build_publication_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    bundle_root: Path,
    bundle_seal: BundleSealV1,
    bundle_artifact: ExactArtifactLocatorV1,
) -> PublicationPlanV1:

def build_correction_publication_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    corrected_bundle_root: Path,
    corrected_bundle_seal: BundleSealV1,
    corrected_bundle_artifact: ExactArtifactLocatorV1,
    correction_lineage: CorrectionLineageV1,
) -> PublicationPlanV1:

def build_correction_intent(
    *,
    authority: ReconstructedAuthorityV1,
    publication_plan: PublicationPlanV1,
    correction_release_plan: CorrectionReleaseIntentPlanV1,
) -> CorrectionIntentV1:

def build_correction_release_intent_plan(
    *,
    authority: ReconstructedAuthorityV1,
    publication_plan: PublicationPlanV1,
    asset_root: Path,
) -> CorrectionReleaseIntentPlanV1:

def require_correction_authority(
    authority: ReconstructedAuthorityV1,
    correction_lineage: CorrectionLineageV1,
) -> None:

def reconstruct_latest_publication_pointer(
    authority: ReconstructedAuthorityV1,
) -> LatestPublicationPointerV1:

def reconstruct_correction_progress(
    authority: ReconstructedAuthorityV1,
) -> CorrectionProgressV1 | None:

def build_corrected_bundle(
    *,
    authority: ReconstructedAuthorityV1,
    prior_bundle_root: Path,
    defect_record: CorrectionDefectRecordV1,
    output_root: Path,
) -> BundleSealV1:
```

Require `authority.state.state` to be exactly `BUNDLE_COLLECTED` for a complete bundle or
`INVALID_FINALIZED` for an invalid-prefix bundle, then call
`require_ordinary_effect_gate(authority)`.
Use `git merge-base --is-ancestor`, `git mktree`, and `git commit-tree` with the neutral fixed author
and committer `Laconian Benchmark Publisher <benchmark-publisher@laconian.invalid>`, UTC
timestamp derived internally from the exact `base_sha` commit's integral committer epoch/offset and
normalized to UTC `+0000`, and locale/timezone-independent environment. Callers and workflow clocks
cannot supply a timestamp. Bind the normalized value in `PublicationPlanV1.commit_timestamp`, run
the builders twice under different clocks/timezones/locales, and require identical tree/head/plan
hashes. Compute the exact file diff
from `BundleSealV1`; do not parse response JSONL or report Markdown.

Neither builder accepts a workflow path/hash scalar. Reconstruct the retained verified C0
`CampaignInputPackageV1` from authority genesis, require its canonical package digest to equal
`authority.registry.payload.campaign_input_package_sha256`, and import/class-bound revalidate only
Evaluation's `WorkflowInventoryV1`. Rebuild that inventory from the exact retained C0 bytes and
require its root to equal `authority.registry.payload.workflow_root`. Resolve only the literal
`.github/workflows/benchmark-publish.yml` member from that verified inventory, descriptor-read and
re-hash its exact C0 bytes, and bind its literal path and hash into the plan. Reject a missing,
duplicate, substituted, non-C0, or mutable-`main` member, package-digest drift, inventory-root drift,
or any CLI/workflow override.

The builders likewise accept no audit-merge list from a caller. For a complete bundle, derive the
ordered full merge set from the verified audit/adjudication attachment DAG and re-fetch every exact
merge commit through canonical authority before binding `audit_merge_shas`. For an invalid-prefix
bundle, derive exactly the accepted pre-STOP audit-merge prefix (possibly empty), require no
post-STOP merge, and bind the ordered complement in `missing_suffix_sha256`. Reject a
caller/CLI override, a merely open audit PR, a merge absent from current `main`, and any order/hash
that differs from the sealed audit evidence.

The correction builder accepts only canonical authority in `RELEASED` or `RELEASE_BLOCKED`, an
exact reviewed defect/incident root, and either no active correction or a new ID after a terminal
prior invalidation. It re-verifies every superseded object, requires a new bundle/result
path/publication ID, and computes a diff that only adds the new result directory. It never rewrites
prior result bytes, tags, Releases, assets, receipts, pointer events, or documentation markers.
Publication/merge/release effects reuse the same protected boundaries. Initial tag, draft, ordered
asset pair, and publish receipts each use the Runtime-owned non-state append CAS. Correction has
only the authoritative tag-wrapper CAS and the aggregate release-wrapper CAS; its inner draft,
ordered assets, and publish receipts are nested in that aggregate and never receive independent
authority CASes. The terminal campaign state remains unchanged until the approved final event.

`build_correction_release_intent_plan` runs before the correction intent CAS. It derives canonical
annotated-tag bytes/name/message/object OID and frozen tagger identity/timestamp with target exactly
the deterministic correction publication approved `head_oid`, plus draft name/body/marker,
immutable-Release policy, and the two
ordered asset name/size/digest records from canonical authority and descriptor-read bytes. It accepts
no identity, target, body, actor, asset, or key override. `build_correction_intent` embeds that plan
and both key records without flattening. After merge, Task 11's `build_correction_release_plan`
requires actual `M` parents exactly `[base_oid, head_oid]` and the expected result tree, then maps the
preauthorized tagger timestamp/bytes/OID, draft, asset fields, and USTAR mtime byte-for-byte into
`ExecutableResultReleasePlanV1`; it cannot replace the earlier intent or plan. Only an initial release derives
its tagger timestamp from the observed merge receipt.

For credential exposure before merge, first persist `CREDENTIAL_EXPOSURE_PENDING` plus the
provisional denylist, then record every inventoried idempotent containment effect through
`CREDENTIAL_EXPOSURE_EFFECT_RECORDED`; only the complete predecessor-bound progress chain permits
the terminal incident, publisher close receipt when the complete PR is open,
`PERMANENT_STOP(reason=credential_exposure)`, and safe invalid-prefix projection. Crash recovery
adopts the exact pending/effect external state by idempotency key and never restores live authority.
Under simultaneous drift this same sequence runs from protected current main and binds drift
evidence; it never emits an intervening drift-only STOP. After a
complete merge but before release, use `RESULT_MERGE_INVALIDATED` or
`RELEASE_PLAN_INVALIDATED` as phase-appropriate, disclose the contaminated merge, and create no
original tag/Release. After `RELEASED`, retain the historical release, immediately append
`latest_status=withdrawn_due_to_credential_exposure`, record containment and affected public object
IDs/tombstone status, and require a new explicit correction. Neither deletion nor withdrawal is
described as historical erasure.

`build_corrected_bundle` is the sole correction-bundle producer. For `release_metadata` and
`publication_metadata` it permits exact byte-for-byte reuse only after the prior bundle fully
re-verifies and the defect is an external publication/release-object metadata divergence from the
already-correct sealed plan, not a code/renderer/bundle defect. It preserves bundle kind and cannot
change any bundle member, analysis value, outcome/interval, audit record, provider evidence, or
invalid-prefix claim prohibition. Only a complete lineage permits this exact-reuse path; every public
projection/report-rendering/trusted-code defect requires a new reviewed campaign. The fixed
`tools/benchmark_prepare_correction.py` selects this closed behavior
from the accepted defect record and authority; it accepts no sequence, class, identity, artifact, or
path override beyond fixed workflow staging roots. Slice 4 uploads that corrected bundle first,
re-fetches its numeric `ExactArtifactLocatorV1`, and only then calls
`build_correction_publication_plan`; no synthetic or missing locator is allowed.
When a correction occurs after transient artifact expiry, this reconstruction may substitute bytes
only through the accepted authority members and their exact protected merge tree, annotated tag,
immutable Release, ordered assets, and accepted append/finalization roots. Every required parent
must be mapped and reverified from canonical bytes; an unmapped private layer or merely same-named
committed file forces a new campaign. Metadata-only reuse still reconstructs the exact prior
committed bundle from those accepted objects rather than trusting a stale local copy or predecessor
checkpoint wrapper.

For ordinary correction, both authority roots are null. Exactly four nonnull-hold consumers exist
repository-wide: `INVALID_EVENT_DISMISSED`; the typed premerge nondismissible/credential/drift STOP
family; `RESULT_MERGED -> RELEASE_PLAN_INVALIDATED`; and `RELEASED ->
CORRECTION_INTENT_AUTHORIZED` with the exact nondismissible, exposure, invalidation, or drift
discriminator/evidence. Only the last is a correction intent: it binds the predecessor hold through
the strict `HeldReleasedConsumptionV1` variant and its expected-OID successor clears that exact root
atomically.
Tests exercise all four discriminators and reject every defect/evidence/consumer cross-pairing.
No unrelated hold authorizes correction, and no correction silently dismisses or preserves a hold.
For `RELEASE_BLOCKED`, the closed `require_correction_authority` verifier requires the terminal
state's accepted `RELEASE_PLAN_INVALIDATED` event hash to equal
`CorrectionDefectRecordV1.evidence_sha256`; `CorrectionLineageV1.defect_record_sha256` equals the
reviewed record digest, and the later intent explicitly binds that event and record as
`supersedes`. For a `RELEASED` credential incident, the intent additionally binds the withdrawn
latest-status event and terminal containment root.

`reconstruct_latest_publication_pointer` bootstraps attempt 0 from accepted state-event authority:
`RESULT_RELEASED` supplies the initial publication/merge/tag/release receipts for `RELEASED`, while
either `RESULT_MERGE_INVALIDATED` or `RELEASE_PLAN_INVALIDATED` supplies the exact corresponding
blocked-origin variant for `RELEASE_BLOCKED`. `require_correction_authority`, the attempt-0 pointer,
and `CorrectionLineageV1` must preserve that exact origin and reject cross-origin synthesis. It then folds each correction directory
only in the ordered durable member sequence. A fully verified `finalization.json` plus
`CORRECTION_RESULT_RELEASED` creates the next released pointer. Either invalidation kind leaves the
prior pointer byte-identical; it never creates a release-blocked pointer for the failed correction,
but its terminal directory remains in the accepted attempt history. A successful correction writes
its attempt ordinal into `LatestPublicationPointerV1.successful_correction_attempt`; gaps caused by
invalidated attempts are valid and never reused. Reconstruction rejects missing/duplicate/
reordered attempt ordinals, reuse after invalidation in any phase, names/paths/tags/Releases whose
N differs from the directory ordinal, and supersedes/progress roots that omit an invalidated attempt.

`reconstruct_correction_progress` accepts at most one contiguous in-flight directory for exactly
the history-derived next `correction_attempt`. It validates `intent_authorized`,
`publication_recorded`, `merge_recorded`, `tag_recorded`, and `release_recorded` prefixes, each with
the exact prior record hash and authority OID. Missing, duplicate, gapped, reordered, two active
directories, an effect receipt without intent, a tag before merge, or release before tag fails.
Every legitimate prefix is idempotently resumable through exact query/adoption, but it never changes
the latest pointer or authorizes docs/social claims. Only a fully receipt-bound
`CORRECTION_RESULT_RELEASED` finalization advances the pointer; from `RELEASE_BLOCKED` it also moves
state to `RELEASED`, while from `RELEASED` state remains `RELEASED` and history is appended.

Do not add a public campaign CLI. The fixed trusted preparation tool calls the initial/correction
plan builder selected from canonical authority and accepts no operator-supplied publication ID,
attempt, branch, base/head, audit merge, workflow identity, correction attempt, defect code, or
result-path override. The public console surface remains the seven offline replay commands.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_plan.py tests/campaign/test_publication_terminal_records.py tests/test_public_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit publication planning**

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/publication.py \
  src/laconian_eval/campaign/collector.py \
  src/laconian_eval/campaign/public_projection.py \
  tools/benchmark_prepare_correction.py \
  tests/campaign/test_publication_plan.py \
  tests/campaign/test_publication_terminal_records.py \
  tests/test_public_contract.py
git commit -m "feat: bind exact benchmark publication plans"
```

### Task 9: Implement the byte-copy-only minimal publisher

**Files:**
- Create: `tools/benchmark_minimal_publisher.py`
- Create: `tools/benchmark_publisher_broker_client.py`
- Create: `src/laconian_eval/campaign/publisher_broker.py`
- Create: `tests/campaign/test_minimal_publisher.py`
- Create: `tests/campaign/test_publisher_broker.py`
- Create: `tests/campaign/test_publication_delivery_resolution.py`
- Create: `tests/campaign/test_publisher_credential_finality.py`
- Modify: `src/laconian_eval/campaign/publication.py`

- [ ] **Step 1: Write the failing local publisher test**

Use a local bare origin and fake GitHub PR endpoint. Supply an exact package ZIP containing only
`publication-plan.json`, `bundle.tar`, `bundle.tar.sha256`,
`tools/benchmark_minimal_publisher.py`, and the hash-bound
`tools/benchmark_publisher_broker_client.py`. The test's fake external publisher broker, not the
Actions-side tool, owns the App private key, terminates GitHub TLS, mints one operation-scoped token,
commits it to the measured vault before executor visibility, performs the exact GitHub reads/write,
closes the token, and returns only signed safe projections/receipts. Assert the created/adopted
branch, proposed head, exact result tree, eligibility check, PR base/title/body, App actor, delivery
resolutions, credential disposition, ledger prefix, and receipt. Assert recursively that no private
key, JWT, installation token, Authorization header, opaque token handle, or raw error body enters
Actions memory, environment, argv, logs, artifacts, exceptions, or receipts.

`publisher_broker.py` imports the canonical Publication-owned
`PublisherCredentialBrokerPolicyV1`, operation rows, subjects, signed
request/transport/closure projections, phase ledger, vault-audit bindings, and safe reconciliation
records from `publication.py`; it defines only the external-broker policy verifier/client boundary
and never redefines, subclasses, aliases, or re-exports those records. The broker phase is monotone
`constructive -> terminalizing -> terminal_reconciling -> sealed`; workflow input cannot lower it.
Constructive rows are exactly: `branch_create` with `contents:write,metadata:read` and ref GET/create;
`merge_eligibility` with `checks:write,metadata:read` and check-suite/run GET/create; and
`pull_request_create` with `metadata:read,pull_requests:write` and PR-list/exact/create. A row cannot
union permissions or endpoints from another operation. Every mint has append-before-send request,
successful/denied/unknown transport, vault commit or zeroization/unrecoverability, operation
dispatch/terminal receipts, final authenticated observations, delete/denial-probe closure, and one
credential disposition. The signed ledger recomputes zero outstanding token requests, zero
outstanding operation dispatches, zero live tokens, and denial of later mint before the next
authority phase.

The following block is a predecessor-wire rejection fixture, not an implementation schema. It
freezes the old aggregate receipt/merge shape so tests can reject it before any broker request. The
initial authority directory and production records use only the exact attempt-qualified paths,
Runtime-owned receipt/append wires, and 05e3d7ba Publication models in the overlay:

```python
class PublicationIntentV1(CapsuleModel):
    schema_version: Literal["PublicationIntentV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    publication_attempt: StrictPositiveInt
    bundle_kind: Literal["complete", "invalid_prefix"]
    publication_plan_sha256: Sha256
    sealed_bundle_root: Sha256
    authority_parent_oid: GitObjectId
    branch_name: BoundedNonBlankString
    base_oid: GitObjectId
    head_oid: GitObjectId
    result_tree_oid: GitObjectId
    pull_request_marker: BoundedNonBlankString
    publisher_app: GitHubAppInstallationIdentityV1
    branch_idempotency_key: Sha256
    pull_request_idempotency_key: Sha256
    branch_receipt_idempotency_key: Sha256
    pull_request_receipt_idempotency_key: Sha256
    merge_observation_idempotency_key: Sha256
    invalidation_idempotency_key: Sha256
    intent_sha256: Sha256


class PublicationBranchReceiptV1(CapsuleModel):
    schema_version: Literal["PublicationBranchReceiptV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    intent_sha256: Sha256
    operation: Literal["created", "adopted"]
    branch_name: BoundedNonBlankString
    base_oid: GitObjectId
    head_oid: GitObjectId
    actor: GitHubAppInstallationIdentityV1
    request_receipts_root: Sha256
    receipt_sha256: Sha256


class PublicationPRReceiptV1(CapsuleModel):
    schema_version: Literal["PublicationPRReceiptV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    intent_sha256: Sha256
    branch_receipt_sha256: Sha256
    operation: Literal["created", "adopted"]
    pull_request_number: StrictPositiveInt
    pull_request_node_id: BoundedNonBlankString
    pull_request_url: ExactAsciiHttpUrl
    base_oid: GitObjectId
    head_oid: GitObjectId
    marker: BoundedNonBlankString
    actor: GitHubAppInstallationIdentityV1
    request_receipts_root: Sha256
    receipt_sha256: Sha256


class PublicationMergeReceiptV1(CapsuleModel):
    schema_version: Literal["PublicationMergeReceiptV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    publication_plan_sha256: Sha256
    pull_request_receipt_sha256: Sha256
    pull_request_number: StrictPositiveInt
    base_oid: GitObjectId
    head_oid: GitObjectId
    merge_commit_oid: GitObjectId
    merge_parents: tuple[GitObjectId, GitObjectId]
    result_tree_oid: GitObjectId
    merge_commit_raw_sha256: Sha256
    merge_committer_epoch_seconds: StrictNonNegativeInt
    merge_committer_utc_offset: BoundedNonBlankString
    merge_committer_timestamp_utc: CanonicalTimestamp
    merge_method: Literal["merge_commit"]
    merge_actor: GitHubHumanAccountObservationV1
    required_checks_root_sha256: Sha256
    approvals_root_sha256: Sha256
    current_main_oid: GitObjectId
    request_receipts_root_sha256: Sha256
    receipt_sha256: Sha256


PublicationReceiptV1 = Annotated[
    PublicationBranchReceiptV1 | PublicationPRReceiptV1,
    Field(discriminator="schema_version"),
]
```

Production publication/release/correction authority records directly carry `campaign_id`,
`campaign_registry_sha256`, and `publication_id`: this includes `PublicationIntentV1`, branch/PR/
merge/close receipts, every publication invalidation, `ResultReleaseIntentV1`, all four release
effect receipts, terminal finalization/invalidation, the single `CorrectionIntentV1` with both
plans, and
all six correction subtree wrappers. Referencing an intent/plan digest is additional and never a
substitute for these three direct fields. Constructors copy the values only from reconstructed
authority, canonical validators require exact equality at every parent/child edge, and every self-
digest includes them. Parametrize one-field substitution, cross-campaign/registry/publication replay,
digest recomputation after substitution, missing field, and old-schema alias for every record; all
must fail before an App credential, external effect, or authority candidate exists.
Both ordinary merge receipts and correction merged-invalid evidence require the strict
`GitHubHumanAccountObservationV1`: numeric account ID/login, literal API `type="User"`, exact source
receipt, and current eligible-merge-team policy root. The account must be the approved non-bot human
merger and distinct from publisher, release-finalizer, state-writer, and GitHub Actions identities.
Tests reject `Bot`/`App`, bot-login aliases, team-policy drift, ID/login mismatch, stale API receipt,
and substitution of any `GitHubAppInstallationIdentityV1`.

`PUBLICATION_INTENT_AUTHORIZED` must persist `intent.json` by external-broker expected-OID CAS
before the external publisher broker may mint its operation-scoped credential. The branch effect emits and persists
`branch-receipt.json` before a PR effect is authorized; the PR effect emits and persists
`pr-receipt.json` before either type-specific opened event. A correction uses its already persisted
`corrections/<correction-id>/intent.json` and persists the analogous
`publication-receipt.json`. An unpersisted, stale, cross-kind, or locally fabricated intent is
rejected before GitHub access.

The initial directory's exact ordered members are `intent.json`, `branch-receipt.json`,
`pr-receipt.json`, `merge-receipt.json`, optional `release-intent.json`, optional
`tag-receipt.json`, optional `draft-release-receipt.json`, optional `asset-receipts.json`, optional
`publish-receipt.json`, and exactly one terminal `finalization.json` or `invalidation.json`.
Invalid-prefix publication forbids every release member. No effect may skip its predecessor receipt,
and every receipt has a distinct intent-bound idempotency key.

The initial tag/draft/assets/publish receipt writes are the closed §7.6 non-state authority append
mechanism, never additional `CampaignStateSchemaV1` events. Each expected-OID broker mutation has
discriminator exactly `initial_release_receipt_append`, appends exactly one next allowlisted path,
retains the byte-identical `CampaignStateV1` and state hash, and carries strict
`InitialReleaseReceiptAppendV1`; no generic unchanged-state append exists. The only path/kind/payload
rows are `tag -> tag-receipt.json -> TagReceiptV1`, `draft_release ->
draft-release-receipt.json -> DraftReleaseReceiptV1`, `assets -> asset-receipts.json -> exactly two
ordered ReleaseAssetReceiptV1`, and `publish -> publish-receipt.json -> PublishReceiptV1`. The broker
replays the predecessor, checks exact intent/registry/publication equality and next path, constructs
one append-only authority commit, and leases the ref. Final `RESULT_RELEASED` binds the accepted
ordered append wrappers, final-verification receipt, operation-set/no-later evidence, and
`InitialPublicationFinalizationV1` while changing state once; failure uses only approved
`RELEASE_PLAN_INVALIDATED` plus `InitialPublicationInvalidationV1`.
Correction receipts use only their separately approved correction phase events and six-member
wrapper sequence.

Require `publisher_app.role == "publisher"`, every observed actor to equal its bot login, and the exact
pre-registered App/installation/repository IDs and permissions-attestation hash. Reject
`github-actions[bot]`, the state/release App, or any request/response whose ordered permissions and
endpoints do not byte-equal its one authorized publisher-broker operation row. A union token across
branch/check/PR or constructive/terminal operations is forbidden.

- [ ] **Step 2: Add failing authority and non-interpretation tests**

Reject a changed base, changed package/script/plan/bundle digest, unexpected ZIP/tar member, path
escape, symlink, an existing divergent remote branch, response text containing shell/HTML/Markdown payloads,
extra Git diff, PR API response with wrong head/base/actor, missing authoritative intent or prior
branch receipt, and any App key/JWT/token/header/handle in any Actions process or environment. Spy
on JSON parsing and assert only
the plan, bundle seal, checksums, and GitHub response are parsed. Add crash/race fixtures for loss
before/after branch creation, branch-receipt CAS, PR creation, and PR-receipt CAS, plus two recovery
jobs racing at each boundary. Also cover eligibility-check create/adopt, every token-request/
operation-dispatch/response-loss/closure boundary, signed broker-ledger and vault-audit equality,
zeroization/unrecoverability, no-mint, later-mint denial, and recursive token-canary absence.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_delivery_resolution.py tests/campaign/test_publisher_credential_finality.py tests/campaign/test_minimal_publisher.py -q`

Expected: FAIL because `tools/benchmark_minimal_publisher.py` is absent.

- [ ] **Step 4: Implement the standard-library-only executable**

The executable accepts only:

```text
--package-zip PATH
--repository OWNER/REPO
--receipt-output PATH
```

It reads no App/installation ID as a credential input and no private key, installation token, token
handle, or GitHub write credential. It accepts only the fixed GitHub OIDC job identity and verified
campaign/package roots, then validates the preregistered nonsecret App identity inside signed safe
broker receipts,
calls the fixed publisher-broker client with one canonical operation request, and receives only
signed safe receipts/projections. The external measured broker selects the exact policy row, owns
all token bytes and Authorization headers, performs at most one broker-authorized GitHub operation
plus its required observations/closure, and seals the ledger before returning. Repository
`GITHUB_TOKEN` is never passed to the executable and has read-only workflow permissions.

It verifies the raw package ZIP digest supplied in `LACONIAN_PACKAGE_SHA256`, extracts fixed members
without `extractall`, verifies the current authority intent, plan, and bundle, creates a temporary worktree at exact `base_sha`,
copies only `expected_files`, force-adds only `result_path`, verifies index/tree/head identities,
and packages the exact proposed commit/object identity for broker validation. The
authority-selected next effect is branch create, merge-eligibility check, or PR create; one
invocation requests at most one policy row. The broker creates/adopts only the exact branch ref,
then on a later authoritative prefix creates/adopts the exact success eligibility check, then on a
later prefix creates/adopts the marker-bound PR. Each operation returns its signed transport,
delivery-resolution, credential-disposition, closure, ledger, and safe observation roots; the
secret-free recorder emits only the matching `PublicationBranchReceiptV1` or
`PublicationPRReceiptV1`/append wrapper after revalidation. The tool never runs a file from the
bundle and cannot represent a token, remote credential URL, Authorization header, or Git credential
configuration.

The only nonsecret runtime identity inputs are the fixed GitHub variables `GITHUB_REPOSITORY_ID`,
`GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_JOB`, and `GITHUB_SHA`. Before pushing, the tool
uses those numeric values only in the signed OIDC caller request. The external broker re-fetches the
current job/deployment/approval, validates the registered App installation and exact operation row,
and binds those identities into safe receipts. It rejects a mismatched approval, actor,
installation, authority parent, intent, predecessor receipt, phase, permission, or endpoint before
mint. Tests prove private-key/token/header canaries never enter Actions at all.

- [ ] **Step 5: Add idempotent safe recovery**

Reconstruct the authoritative next prefix before every broker call. A missing branch selects only
the `branch_create` row; after its exact signed delivery resolution and branch receipt win the
expected-OID authority CAS, a later invocation may select only `merge_eligibility`; only after that
receipt wins may a still later invocation select `pull_request_create`. An exact branch without a PR
therefore cannot skip the eligibility prefix or make a direct Actions-side PR request. If the exact
open PR already exists, the external broker performs no write and adopts it only when base, head,
title, body digest, author, plan, and bundle are identical. A lost/conflicting PR-create response is
resolved solely by the broker's signed authenticated final observations; Actions never retries or
issues the POST itself.

Every invocation selects one exact operation row, uses a fresh closed token lifecycle, and emits a
new effect-specific receipt for the current run/job/deployment with `created` or `adopted`; it never
claims byte identity with a receipt from a different caller. The state broker accepts exactly one
fully reverified receipt before the next effect. If canonical authority already binds one,
re-fetch/reverify it and make the invocation a no-op; a stale expected-OID CAS loser makes no further
publisher-broker call. Entering `terminalizing`, `terminal_reconciling`, or `sealed` forbids every
remaining constructive call. Any object mismatch raises `publication_collision`; no force push,
edit, close, approve, merge, label, or review endpoint is called. Test recovery under a new
run/job/approval identity, response loss at every operation, and every effect/receipt CAS crash
window.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_delivery_resolution.py tests/campaign/test_publisher_credential_finality.py tests/campaign/test_publisher_broker.py tests/campaign/test_minimal_publisher.py tests/campaign/test_publication_plan.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the minimal publisher**

```bash
git add tools/benchmark_minimal_publisher.py \
  tools/benchmark_publisher_broker_client.py \
  src/laconian_eval/campaign/publisher_broker.py \
  src/laconian_eval/campaign/publication.py \
  tests/campaign/test_publication_delivery_resolution.py \
  tests/campaign/test_publisher_credential_finality.py \
  tests/campaign/test_minimal_publisher.py \
  tests/campaign/test_publisher_broker.py
git commit -m "feat: publish sealed benchmark bundles minimally"
```

### Task 10: Add the protected publication workflow and trusted PR validation

**Files:**
- Create: `.github/workflows/benchmark-publish.yml`
- Create: `.github/workflows/publication-pr-validate.yml`
- Modify: `.github/workflows/benchmark-publication-state.yml`
- Modify: `src/laconian_eval/campaign/release.py`
- Modify: `src/laconian_eval/campaign/release_broker.py`
- Modify: `tools/benchmark_release_broker_client.py`
- Modify: `tests/campaign/test_release_broker.py`
- Modify: `tests/campaign/test_security_attestor_credential_finality.py`
- Create: `tests/campaign/test_publication_terminal_containment.py`
- Create: `tests/campaign/test_publication_merge_queue.py`
- Create: `tests/campaign/test_publication_merge_fence.py`
- Create: `tools/validate_publication_pr.py`
- Create: `tests/campaign/test_publication_pr.py`
- Modify: `tests/campaign/test_publication_workflows.py`
- Modify: `tools/benchmark_minimal_publisher.py`
- Modify: `src/laconian_eval/campaign/publisher_broker.py`
- Modify: `tests/campaign/test_minimal_publisher.py`
- Modify: `tests/campaign/test_publisher_broker.py`
- Modify: `src/laconian_eval/campaign/publication.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `benchmarks/runbooks/public-benchmark.md`
- Modify: `tests/test_public_contract.py`
- Modify: `tests/test_ci_contract.py`

- [ ] **Step 1: Write failing workflow-boundary tests**

Import the six Runtime-owned state-bound wire primitives from
`laconian_eval.campaign.publication_wire` and assert package/object identity before defining any
Task 10 evidence schema. Publication must not define, subclass, alias, or re-export
`PublicationMergeDenylistEntryV1`, `PublicationMergeDenylistV1`,
`PublicationTerminalContainmentPreflightV1`, `PublicationPreContainmentTerminalRouteV1`,
`PublicationTerminalContainmentIntentV1`, or `PublicationTerminalContainmentFinalityV1`.

Require `benchmark-publish.yml` to have a read-only `prepare-publication` job and exactly two
mutually exclusive `benchmark-publish` environment effect jobs named `publisher_effect` and
`publication_terminalizer`. Each has exactly
`id-token: write` plus `actions: read`, `deployments: read`, `contents: read`, and
`pull-requests: read`; only the latter four are repository-token scopes. It contains only the fixed
OIDC bootstrap, bounded numeric artifact downloader, and repository-owned publisher-broker client.
It maps no App/installation ID as a credential input and no private key, token, or opaque handle.
`${{ github.token }}` is exposed only as `GITHUB_READ_TOKEN` for the bounded
numeric artifact GET and is unset before the broker request. There is no write-capable
`GITHUB_TOKEN`, checkout/setup/artifact/third-party action, local GitHub write, or secret in the
environment. Forbid `OPENAI_API_KEY`, App secret names, approval/merge commands, `gh pr review`,
`gh pr merge`, force push, mutable refs, and any App-auth Authorization header created by Actions
code. The bounded repository-read client may create only the `GITHUB_READ_TOKEN` header for its
allowlisted numeric API GET and must strip it before the signed redirect fetch and every broker call.
Only `publisher_effect` may select the three constructive policy rows, and only from an exact
plan-bound protected-main prefix. Only `publication_terminalizer` may select containment start,
terminal guard/close/barrier/dequeue/fence/reconciliation rows, and its OIDC job name is repeated
byte-for-byte by `PUBLICATION_TERMINAL_CONTAINMENT_STARTED.source_job`. A workflow mode, package, or
rerun cannot move a row between the two callers; only one effect job is eligible for a reconstructed
authority prefix.

The same `.github/workflows/benchmark-publish.yml` also has the separately protected
`security_attestor` job. It runs only at the exact allowed main/ref/plan in the
`benchmark-publish` environment, declares exactly `id-token: write` and no repository-token scope,
requests OIDC only with audience `laconian-security-attestor-broker` for its closed job identity, and receives from the
external broker only signed safe attestation receipts for one short-lived token scoped to the
existing release-finalizer App installation with returned permissions exactly
`administration:write`, `contents:read`, and `metadata:read`. The external measured broker mints,
vaults, performs the fixed GET allowlist, closes the token, and returns no token/header/handle. The
job contains only OIDC bootstrap and the fixed broker client; no App key, contents/Release write
token, repository-token substitute, publisher/state credential, provider key, model/artifact bytes,
or direct GitHub settings reader enters the job. Release-writer tokens omit Administration
permission.

Runtime Task 9 has already created the canonical security-attestor records in `release.py`, the safe
verifier and `preflight_rulesets` policy row in `release_broker.py`, and the secret-free OIDC client
plus fake-broker tests. Task 10 imports those exact class objects and extends only the same files and
tests with `postmerge_rule_suite`; it must not redefine, subclass, alias, or re-export the records.
Task 11 then adds only `release_preparation` and the release-finalizer operation policy. This ordering
makes every workflow caller independently GREEN without changing a previously frozen C0 workflow.

- [ ] Extend the Task 9 publisher and tests with exactly two package-discriminated modes:
  `open_exact_pr` and `close_exact_pr`. Close mode requires `PublicationClosePlanV1`, re-fetches the
  exact open PR/head/receipt/invalidation, calls only the close endpoint, and emits
  `PublicationCloseReceiptV1`; it cannot open/edit/review/approve/merge/delete a branch. Both modes
  require the same publisher App identity and protected job.

Freeze the external publisher broker's terminal rows exactly as normative §7.4:
`terminal_guard_discovery` (`contents:read,metadata:read,pull_requests:read`), `terminal_guard`
(`checks:write,metadata:read`), `pull_request_close`
(`metadata:read,pull_requests:write`), `terminal_merge_barrier_read`
(`actions:read,checks:read,contents:read,merge_queues:read,metadata:read,pull_requests:read`),
`terminal_merge_barrier_dequeue` (`merge_queues:write,metadata:read`),
`terminal_merge_fence_rerun` (`actions:write,metadata:read`), and the post-write
`terminal_reconciliation_read` (`checks:read,contents:read,metadata:read,pull_requests:read`). Each
row carries only its exact REST/GraphQL documents and endpoint templates, plus token mint/delete/
denial-probe. Entering `terminalizing` disables every constructive mint; entering
`terminal_reconciling` disables every write mint; `sealed` denies all later mint. Tests prove one
fresh token lifecycle per operation, no union/superset scope, complete signed request/transport/
closure evidence, and zero token/header/handle bytes in Actions. The
`terminal_merge_barrier_read` row alone has two closed authorization arms: before
`PUBLICATION_TERMINAL_CONTAINMENT_STARTED`, it may mint only the explicitly source-bound read-only
preflight credential needed to construct the containment intent; after the accepted tombstone CAS,
it may mint only intent/CAS-bound post-action reads. Every other containment credential, including
guard discovery, guard create/update, PR close, dequeue, and rerun, may mint only after that CAS;
no write-capable row has a pre-CAS arm. Tests reject a source substitution in preflight, an
intent/CAS substitution after start, and every pre-CAS guard, close, dequeue, or rerun request.

Require the workflow's top-level concurrency group to be exactly
`laconian-public-benchmark-state` with `cancel-in-progress: false`. The receipt must bind the
numeric publish job, deployment, and approval actor parsed through the Task 1 GitHub records before
the bundle-kind-specific publication-PR-open event is applied.

Require `publication-pr-validate.yml` to run the stable job `publication-pr-validate` on every
`pull_request` type `opened`, `synchronize`, `reopened`, and `closed`, without a
top-level path filter; on `pull_request_review` type `submitted|dismissed`; and on
`merge_group: [checks_requested]`, with read-only permissions and no secrets. Pull-request/review
events resolve the exact current PR/head; merge-group events authenticate the one-entry MERGE queue
inventory and publish the same required context on the event's merge-group SHA. It executes
`tools/validate_publication_pr.py` from the exact protected base checkout, never candidate code. An
unrelated diff returns a successful explicit no-op so the globally required check is never left
Pending. Its job declares exactly `contents: read` and `pull-requests: read`. Tests reject a missing
`merge_group` trigger, a context emitted only on the PR head, a multi-entry/non-MERGE group, or
candidate-code checkout.

Require `benchmark-publication-state.yml` to use the shared concurrency group and trusted-base code
on the same PR events plus no-input `workflow_dispatch`. It no-ops unrelated PRs. A read-only inspect
job declares exactly `contents: read`, `actions: read`, `pull-requests: read`, and `checks: read` and
reconstructs the exact publication receipt from the canonical authority ref; a narrow state mutation
calls the existing OIDC reusable job created by Runtime Task 9. That job contains only OIDC bootstrap
and the fixed broker client; no state-writer credential or installation token is mapped into Actions.
When an exact still-open plan is invalidated, this workflow
emits only a safe close-required summary. The same no-input `benchmark-publish.yml` and same
protected `publication_terminalizer` job/tool later enters its receipt-bound `close_exact_pr` mode;
`publisher_effect` cannot select close or any other terminal row, and there is no third
write-capable publisher job. No job reviews, approves, merges, force-pushes, edits, or deletes result
content.
Forks, human-authored PRs, and non-result diffs can execute only the read-only no-op path; policy
tests inspect job conditions and exact head repository/actor/receipt bindings before any write token
is available.

For every manual publication path, require exact `refs/heads/main` at the plan-bound main SHA,
re-read the caller and reusable workflow blobs at that SHA, and derive the campaign/authority only
from the accepted intent/receipt. Reject an input tag, another branch, mutable selector,
newest/by-name discovery, operator campaign/PR/head/base input, or a main SHA not bound by the plan.
The only exceptions to plan-bound main are the literal generated caller rows: the six existing
post-merge admission/invalidation events; `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` and its
phase-exact terminal consumers; drift containment; credential-exposure pending/progress/final/
supplement; and safe-invalid continuation. All retain OIDC `ref=refs/heads/main`, fresh double
reads, byte-identical C0 workflow members, independently verified Git/GitHub objects, and the exact
active containment/denylist roots. Containment is not a seventh generic post-merge exception: its
start is a same-state expected-OID CAS for an active publication prefix, and only the intent-named
terminal event may clear it.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_terminal_containment.py tests/campaign/test_publication_merge_queue.py tests/campaign/test_publication_merge_fence.py tests/campaign/test_security_attestor_credential_finality.py tests/campaign/test_publication_workflows.py tests/campaign/test_publication_pr.py tests/test_ci_contract.py -q`

Expected: FAIL because the two new workflows, publication/admission recorders, and required caller
rows in the existing reusable workflow are absent.

- [ ] **Step 3: Implement the publication workflow**

`prepare-publication` reconstructs current authority. On the initial path it proves
`BUNDLE_COLLECTED` or `INVALID_FINALIZED`, downloads the exact bundle, and builds
`PublicationPlanV1`. On the correction path it proves terminal `RELEASED|RELEASE_BLOCKED` plus the
reviewed protected-main defect record/merge and a resumable `CorrectionProgressV1` planning stage;
it does not request or expect a `correction_defect` state event. It runs the Task 8 correction-bundle producer, uploads that
bundle, re-fetches its numeric locator, and only then builds the correction plan. When the exact
current publication plan is invalid while its PR remains open, it instead builds a closed
`PublicationClosePlanV1` binding only that receipt/PR/head and the already-derived invalidation.
  It packages the selected plan, bundle when opening, exact publisher script, and secret-free
  publisher-broker client,
uploads with 90-day retention, and exports artifact ID, service digest, payload digest, and plan
digest. No workflow/operator input selects the mode.

The mutually exclusive gated `publisher_effect` and `publication_terminalizer` jobs each use the
same frozen shell block to download the package by numeric artifact ID, hash the raw ZIP, extract and
hash the fixed publisher script and broker client with `unzip -p`, and execute them with only their
verified exact OIDC job identity. The external broker alone owns the publisher App credential and
performs the selected operation. `publisher_effect` open mode emits only the ordered branch,
eligibility, and PR receipts from Task 9; `publication_terminalizer` close mode may only
close the one exact open PR and emits `PublicationCloseReceiptV1`, never edits branch/content. A
following read-only `record-publication` job re-fetches the PR by number/head and validates the
receipt. Initial publication creates `COMPLETE_PUBLICATION_PR_OPENED` or
`INVALID_PUBLICATION_PR_OPENED`; correction publication appends
`CORRECTION_PUBLICATION_RECORDED`; initial
close applies the matching publication-plan invalidation only after the close receipt verifies;
correction close appends
`CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=unmerged_invalid)`, which terminates that correction ID without advancing the
latest pointer. Every receipt/event uses the external OIDC broker against the exact expected
authority OID; no state-writer credential reaches Actions.
`record-publication` treats a PR opened/closed without a durable receipt as a recoverable exact-plan
lookup, never as permission to create another branch or target another PR.

Do not add a public campaign CLI. Fixed trusted-base validator/recorder tools use trusted API records
and canonical authority; none accepts a PR number, branch, head, base, event type, artifact selector,
campaign, correction ID, or effect mode from an operator. They construct only the exact
authority-selected receipt/event and hand it to the reusable OIDC broker job. Public contract tests
keep exactly seven offline replay commands and reject a live/public shared writer.

- [ ] **Step 4: Implement trusted-base PR validation**

Add:

```python
class PublicationClosePlanV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    publication_attempt: StrictPositiveInt
    correction_lineage_sha256: Sha256 | None
    publication_plan_sha256: Sha256
    publication_receipt_sha256: Sha256
    pull_request_number: StrictPositiveInt
    exact_head_sha: GitObjectId
    invalidation_sha256: Sha256
    expected_authority_ref_oid: GitObjectId
    close_plan_sha256: Sha256


class PublicationCloseReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    close_plan_sha256: Sha256
    publication_attempt: StrictPositiveInt
    pull_request_number: StrictPositiveInt
    exact_head_sha: GitObjectId
    closed_at_utc: CanonicalTimestamp
    publisher_app: GitHubAppInstallationIdentityV1
    closed_by: BoundedNonBlankString
    receipt_sha256: Sha256


class PublicationPRValidationV1(CapsuleModel):
    schema_version: Literal["1"]
    kind: Literal["result", "correction_defect", "irrelevant"]
    publication_receipt_sha256: Sha256 | None
    correction_defect_record_sha256: Sha256 | None
    validation_sha256: Sha256


def validate_publication_pull_request(
    *,
    trusted_repository: Path,
    candidate_repository: Path,
    event: Mapping[str, object],
) -> PublicationPRValidationV1:
```

For a result PR, require base `main`, author equal to the exact registered publisher App bot login,
the bound branch, exact base/head SHA, no merge
conflict, current-base equality, plan and bundle digest, exact result-path-only diff, no symlink,
submodule, executable bit, workflow change, or extra file. Recompute the bundle projection and
proposed tree/head using trusted-base code. Emit a canonical safe summary containing only campaign,
plan, bundle, base, and head digests.
Before returning success on either the PR head or its one-entry `merge_group` SHA, reconstruct the
exact active campaign authority from the registry-bound authority ref, never from event-selected
state. Class-bound verify the current publication intent/attempt/branch/head/plan and current
`publication_merge_denylist_root_sha256`, load every referenced
`PublicationMergeDenylistEntryV1`, and require this candidate absent. Also require the exact
intent-bound publisher eligibility receipt/check to be current and passing. A matching terminal-
guard receipt/check, active `PublicationTerminalContainmentIntentV1`, denylist tombstone, missing or
wrong eligibility evidence, stale authority OID, or guard/eligibility source-App/workflow mismatch
forces failure; reopening or re-enqueueing cannot revive it. On `merge_group`, authenticate its sole
queue entry back to the same PR/head and repeat the authority/denylist/guard reads before publishing
the validator context on the temporary group SHA. Tests cover PR-head and merge-group denial for a
denylisted head, active containment, missing/wrong eligibility, matching terminal guard, stale
authority, and a late tombstone between PR success and queue validation. The explicit no-op is legal
only after trusted-base classification proves a truly unrelated diff with no result/correction
branch, marker, path, plan, or authority identity.
For the `publication-pr-validate` required check to succeed, also re-fetch one current APPROVED
review at the exact head from a preregistered non-bot maintainer numeric ID/login, require its exact
review ID/API-record digest, and reject dismissal/staleness. Before that review the result validator
fails closed; its `pull_request_review submitted|dismissed` trigger reruns the same check. Thus a
publisher-App review cannot satisfy the gate even though `pull_requests:write` is technically broad
enough to call review/merge endpoints.

For a correction-defect PR, require a non-bot human author, exactly the next fixed defect path and
no other diff, strict `CorrectionDefectRecordV1`, current latest-pointer binding, a current distinct
human approval, and no result/workflow/docs changes. On its exact merged event,
`benchmark-publication-state.yml` revalidates merge ancestry/tree but does not append authority.
The reviewed defect record and immutable merge evidence are external verified inputs to the single
first authority write, `CORRECTION_INTENT_AUTHORIZED`, whose `intent.json` embeds and binds them.
No pre-intent defect-record path, mutation, event, or authority commit exists; add a negative test
for that absence. Unrelated PRs return the explicit `irrelevant` result.

Define strict `RequiredCheckEvidenceV1` for each required check with check-run ID/name,
`status == "completed"`, conclusion, head SHA, check-suite ID/event, source App numeric ID/slug,
workflow run ID/attempt, trusted workflow path/SHA-256, and evidence digest. Re-fetch check run,
suite, and Actions run by exact IDs; require the preregistered GitHub Actions source App and trusted
base workflow bytes. A same-name check from another App/workflow, a rerequested/in-progress suite,
or a run on another SHA fails even if its conclusion says success.

Define `PublicationMergeReceiptV1` with the exact approved compact wire: `schema_version`, common
campaign/repository identity and initial/correction XOR identity, `authority_parent_oid`,
`publication_plan_sha256`, `publication_receipt_kind`, nullable
`publication_pr_receipt_sha256`, PR number/node ID/URL, observed merge/head/base OIDs, nested exact
`PostMergeAdmissionEvidenceV1` plus its digest, duplicated publication-success-finality root,
`recorded_at`, and `publication_merge_receipt_sha256`. Every duplicate byte-equals the nested
evidence and `recorded_at` equals its latest sealed time. The nested admission subject/evidence,
queue inventory/timeline, and success-finality records prove the authenticated one-entry MERGE
queue, exact `M` parents/tree, human actors, and required merge-group checks. Direct, squash,
rebase, jump/solo, missing-group, multi-entry-group, and queue-identity aliases are rejected;
`merge_method="merge_commit"` describes the protected queue's Git commit shape, not permission for a
direct merge. No checkpoint or aggregate-release object is part of this receipt.

The broker constructs `PostMergeAdmissionEvidenceV1` independently from exact GitHub API responses
and Git object bytes, never from event input. It proves the PR is merged, `M` is the PR's immutable
merge commit, its parents/tree exactly match the plan, all checks and current approvals bind the
approved head, the human actor/method are allowed, and historical protection was enforced. The
downscoped `security_attestor` job presents only its exact OIDC identity and receives signed safe
pass/failure evidence. The external broker alone mints, vaults, uses, and closes a short-lived token
from the existing release-finalizer App installation with `administration:write`, `contents:read`,
and `metadata:read`; it fetches and seals the complete repository rule-suite
record whose `before_sha=base_oid`, `after_sha=M`, `ref=refs/heads/main`, actor equals the merge
actor, overall result is `pass` rather than `bypass`, and every active per-rule evaluation matches
the plan-bound ruleset. Reading only current rules is insufficient.

For a post-merge dispatch, OIDC remains on `refs/heads/main` at current main `H`. Require `H == M` or
a protected first-parent descendant that contains `M`, keeps the plan-bound result subtree
byte-identical, and has no intervening commit touching that subtree. Re-read main before and after
all other observations and re-evaluate containment. The caller and reusable workflow blobs at `H`
must still equal their C0 inventory members. Missing, contradictory, bypassed, late-missing, or
moving evidence fails closed.

Implement `PostMergeAdmissionFailureV1` from the exact ordered 53-field contract and the
`POSTMERGE_FAILURE_KINDS`/`POSTMERGE_FAILED_PREDICATES` tuples in the mandatory overlay. In
addition to the immutable plan/PR/merge/rule/request observations, it carries the strict
`PostMergeAdmissionSubjectV1` plus pass/failure security-attestor evidence, the source-kind-
discriminated containment finality, successor denylist and before/after active roots, selected
merged candidate, complete publisher credential disposition, reconciliation-unavailable receipt,
signed empty release-authorization ledger where applicable, exact PR terminal disposition, class-
bound drift/exposure evidence, no-later root where constructible, and its digest. The five failure
kinds are exhaustive; fields from another kind/source/phase are forbidden.

The six existing post-merge admission/invalidation event shapes are:

```text
RESULT_MERGED
INVALID_PREFIX_MERGED
CORRECTION_MERGE_RECORDED
RESULT_MERGE_INVALIDATED
INVALID_PREFIX_MERGE_INVALIDATED
CORRECTION_INVALIDATED(kind=correction_publication_invalidation, publication_outcome=merged_invalid)
```

The first three require `PostMergeAdmissionEvidenceV1`; the last three require
`PostMergeAdmissionFailureV1`. The sixth additionally requires the exact active correction
`intent.json` or `publication-receipt.json`, no valid merge/later receipt, matching correction
phase/plan/PR roots, and proof of no tag/Release/asset/latest/docs/social effects. It can authorize
only terminal `merged_invalid`; it cannot authorize unmerged invalidation, a merge receipt, or any
release phase. `PUBLICATION_TERMINAL_CONTAINMENT_STARTED` is the additional protected-current-main
same-state row described in the overlay, not a seventh post-merge admission result. All other main
events remain pinned to their pre-bound main SHA.

If exposure begins while a complete publication PR is open or after its merge effect but before the
authority CAS, the only complete-path event is `RESULT_MERGE_INVALIDATED` with
`failure_kind=credential_exposure_race` and the terminal exposure projection. That CAS binds the
observed merge, atomically clears the active incident/pending pair, consumes the matching hold if
present, and enters `RELEASE_BLOCKED`; ordinary admission failures forbid the projection and require
the pair null. Add crash/replay tests for exposure before merge, after merge before CAS, and after
reconstruction, including hidden/mismatched holds.

Only successful complete admission from `COMPLETE_PUBLICATION_PR_OPEN` emits `RESULT_MERGED` and
enters `RESULT_MERGED`. Successful invalid admission from `INVALID_PUBLICATION_PR_OPEN` emits
`INVALID_PREFIX_MERGED` and enters terminal `INVALID_PREFIX_MERGED`. Failed complete admission emits
`RESULT_MERGE_INVALIDATED` and enters `RELEASE_BLOCKED`; failed invalid admission emits
`INVALID_PREFIX_MERGE_INVALIDATED` and enters terminal `INVALID_PREFIX_MERGED_INVALID`. Cross-kind,
generic, absent-discriminator, or wrong-parent events create a hold without state mutation.

Define only the approved terminal unions. `InitialPublicationInvalidationV1` covers initial
complete/invalid premerge failure and release-plan failure; `InitialPublicationFinalizationV1`
covers the corresponding successful terminal records. `CorrectionInvalidationV1` covers exactly
`unmerged_invalid`, `merged_invalid`, `fenced_write_ambiguity`, and
`reconciliation_unavailable`. Every member uses its literal schema version, terminal kind,
publication attempt or correction ID, active authority phase, exact intent/receipt parent, and the
approved field order. Cross-kind optional bags and a generic `PublicationInvalidationV1` are
rejected.

Every active publication prefix first takes `PUBLICATION_TERMINAL_CONTAINMENT_STARTED`; its terminal
record then embeds the matching `PublicationTerminalContainmentFinalityV1`, before/after active
roots, successor denylist, and exactly one of ordinary PR disposition, fenced-write ambiguity,
reconciliation-unavailable, post-merge failure, or release-plan invalidation evidence. Ordinary
premerge `no_pr|closed` carries `PublicationNoLaterEffectsEvidenceV1`; unavailable and fenced forms
must leave that root null. An already merged or reopened PR uses the merge-won form and cannot be
recast as a premerge close.

An exact unchanged branch with no PR remains the recovery case and cannot be invalidated merely to
skip recovery. Tests crash after branch-receipt CAS, move base/branch before PR creation, close then
reopen/merge, lose every write response, and exhaust authenticated pagination. They require the
phase-exact terminal record to be the sole liveness exit for both bundle kinds and corrections;
phase substitution, hidden discovered objects, fabricated absence, a missing terminal guard,
nonmonotone denylist, or an uncleared/mismatched containment root fails before the terminal CAS.

Successful correction admission appends `CORRECTION_MERGE_RECORDED`; an absent/closed unmerged PR
uses `CorrectionInvalidationV1(publication_outcome="unmerged_invalid")`; a merge that wins ordinary
terminalization uses `merged_invalid`; an unorderable publisher write uses
`fenced_write_ambiguity`; and failed stable reconciliation uses `reconciliation_unavailable`.
None advances the latest pointer. Replanning initial publication starts from `BUNDLE_COLLECTED` or
`INVALID_FINALIZED` with the next authority-derived attempt and a new immutable branch/head/plan;
it never updates or force-pushes the invalid branch. End-to-end tests cover both bundle kinds, main
movement before and after opening, unchanged base/bundle after invalidation, every terminal outcome,
and stale-CAS adoption; each accepted terminal record advances the attempt exactly once.

- [ ] **Step 5: Add manual approval evidence to the runbook test**

Assert the workflow and runbook state that the publisher-App-authored same-repository PR triggers
the always-present validators normally; it does not depend on the repository-global Actions
create/approve-PR toggle or a fork-workflow approval. A write-authorized maintainer verifies the
exact head/bundle, supplies the required human PR review, and only after required checks enqueues the
exact PR into the one-entry `MERGE` queue. The resulting merge is accepted only from authenticated
merge-group/queue evidence; direct, squash, and rebase merge are forbidden. Neither the publisher
App nor any workflow approves a review, enqueues, or merges the PR.

The runbook also gives the exact no-input recovery dispatch, merge-recorder, close/replan, and stale
CAS procedures. It forbids manually supplied PR/head/base IDs and states that complete release
planning is blocked until `PublicationMergeReceiptV1` has advanced canonical authority to
`RESULT_MERGED`; invalid-prefix outcomes are terminal and have no release plan.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_terminal_containment.py tests/campaign/test_publication_merge_queue.py tests/campaign/test_publication_merge_fence.py tests/campaign/test_security_attestor_credential_finality.py tests/campaign/test_publication_workflows.py tests/campaign/test_publication_pr.py tests/campaign/test_publisher_broker.py tests/campaign/test_release_broker.py tests/campaign/test_minimal_publisher.py tests/test_ci_contract.py tests/test_public_contract.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` enumerates exactly thirteen workflows: the eleven
present after Task 7 plus the two new workflows in this task; the Runtime-owned reusable workflow is
modified, not counted twice.

- [ ] **Step 7: Commit protected publication and PR validation**

```bash
git add .github/workflows/benchmark-publish.yml \
  .github/workflows/publication-pr-validate.yml \
  .github/workflows/benchmark-publication-state.yml \
  src/laconian_eval/campaign/release.py \
  src/laconian_eval/campaign/release_broker.py \
  tools/validate_publication_pr.py \
  tools/benchmark_minimal_publisher.py \
  tools/benchmark_release_broker_client.py \
  src/laconian_eval/campaign/publication.py \
  src/laconian_eval/campaign/publisher_broker.py \
  src/laconian_eval/campaign/__init__.py \
  tests/campaign/test_minimal_publisher.py \
  tests/campaign/test_publisher_broker.py \
  tests/campaign/test_release_broker.py \
  tests/campaign/test_publication_terminal_containment.py \
  tests/campaign/test_publication_merge_queue.py \
  tests/campaign/test_publication_merge_fence.py \
  tests/campaign/test_security_attestor_credential_finality.py \
  tests/campaign/test_publication_pr.py \
  tests/campaign/test_publication_workflows.py \
  benchmarks/runbooks/public-benchmark.md \
  tests/test_ci_contract.py \
  tests/test_public_contract.py
git commit -m "ci: gate exact benchmark publication pull requests"
```

### Task 11: Build the preauthorized, attested, executable release graph and idempotent finalizer

**Files:**
- Modify: `src/laconian_eval/campaign/release.py`
- Modify: `src/laconian_eval/campaign/release_broker.py`
- Create: `tools/benchmark_release_finalizer.py`
- Modify: `tools/benchmark_release_broker_client.py`
- Create: `tools/benchmark_release_inventory_monitor.py`
- Create: `ops/benchmark-release-inventory-monitor.toml`
- Create: `docs/runbooks/benchmark-release-inventory-monitor.md`
- Create: `tests/campaign/test_result_release.py`
- Modify: `tests/campaign/test_release_broker.py`
- Modify: `tests/campaign/test_security_attestor_credential_finality.py`
- Create: `tests/campaign/test_release_authorization_graph.py`
- Create: `tests/campaign/test_release_finalizer_credential_finality.py`
- Create: `tests/campaign/test_reconciliation_unavailable.py`
- Create: `tests/campaign/test_release_inventory_monitor.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write the failing merged-result plan test**

Create an approved publication PR fixture, merge it, and build two fixed assets:
`benchmark-result-{publication_id}.tar` and `benchmark-result-{publication_id}.tar.sha256`. Assert the
merge tree contains the exact result path and the release plan binds every digest.

The following predecessor sketch is a RED-only rejection fixture. Do not implement or export any
of these shapes; `test_release_authorization_graph.py` parses representative payloads and requires
strict rejection before credentials or external reads:

```python
class ReleaseAssetV1(CapsuleModel):
    name: BoundedNonBlankString
    media_type: Literal["application/x-tar", "text/plain"]
    byte_length: StrictNonNegativeInt
    sha256: Sha256


class RejectedSecurityAttestorTokenRequestFixture(CapsuleModel):
    broker_request_id: BoundedNonBlankString
    oidc_identity: GitHubOidcRunIdentityV1
    app_id: StrictPositiveInt
    installation_id: StrictPositiveInt
    repository_id: StrictPositiveInt
    requested_permissions: tuple[
        Literal["administration:write"], Literal["contents:read"], Literal["metadata:read"]
    ]
    safe_broker_response_sha256: Sha256
    token_expires_at_utc: CanonicalTimestamp
    token_request_sha256: Sha256


class SecurityAttestorRepositoryObservationV1(CapsuleModel):
    repository_id: StrictPositiveInt
    repository_full_name: BoundedNonBlankString
    default_branch: Literal["main"]
    private: StrictBool
    request_sha256: Sha256
    response_status: Literal[200]
    raw_response_sha256: Sha256
    canonical_projection_sha256: Sha256
    observation_sha256: Sha256


class SecurityAttestorResultTagRulesetObservationV1(CapsuleModel):
    creation_ruleset_id: StrictPositiveInt
    immutability_ruleset_id: StrictPositiveInt
    result_tag_patterns: tuple[BoundedNonBlankString, ...]
    creation_ruleset_policy_sha256: Sha256
    immutability_ruleset_policy_sha256: Sha256
    creation_bypass_actor: GitHubAppInstallationIdentityV1
    creation_bypass_actors_root_sha256: Sha256
    immutability_bypass_actors: tuple[()]
    tag_ruleset_policy_root_sha256: Sha256
    request_sha256: Sha256
    response_status: Literal[200]
    raw_response_sha256: Sha256
    canonical_projection_sha256: Sha256
    observation_sha256: Sha256


class SecurityAttestorImmutableReleaseObservationV1(CapsuleModel):
    repository_id: StrictPositiveInt
    immutable_releases_enabled: Literal[True]
    request_sha256: Sha256
    response_status: Literal[200]
    raw_response_sha256: Sha256
    canonical_projection_sha256: Sha256
    observation_sha256: Sha256


class InitialSecurityAttestorLineageV1(CapsuleModel):
    kind: Literal["initial"]
    publication_plan_sha256: Sha256
    publication_merge_receipt_sha256: Sha256
    merge_commit_oid: GitObjectId
    result_tree_oid: GitObjectId
    authorized_tag_target_oid: GitObjectId
    lineage_sha256: Sha256


class CorrectionSecurityAttestorLineageV1(CapsuleModel):
    kind: Literal["correction"]
    correction_id: BoundedNonBlankString
    correction_intent_sha256: Sha256
    correction_merge_receipt_sha256: Sha256
    nested_publication_merge_receipt_sha256: Sha256
    merge_commit_oid: GitObjectId
    result_tree_oid: GitObjectId
    authorized_tag_target_oid: GitObjectId
    lineage_sha256: Sha256


SecurityAttestorLineageV1 = Annotated[
    InitialSecurityAttestorLineageV1 | CorrectionSecurityAttestorLineageV1,
    Field(discriminator="kind"),
]


class SecurityAttestorReceiptV1(CapsuleModel):
    schema_version: Literal["SecurityAttestorReceiptV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    job_id: StrictPositiveInt
    job_name: Literal["security_attestor"]
    check_run_id: StrictPositiveInt
    deployment_id: StrictPositiveInt
    environment: Literal["benchmark-publish"]
    approval_actor_id: StrictPositiveInt
    approval_actor_login: BoundedNonBlankString
    job_api_observation_root_sha256: Sha256
    deployment_api_observation_root_sha256: Sha256
    approval_api_observation_root_sha256: Sha256
    lineage: SecurityAttestorLineageV1
    token_request: RejectedSecurityAttestorTokenRequestFixture
    returned_permissions: tuple[
        Literal["administration:write"], Literal["contents:read"], Literal["metadata:read"]
    ]
    repository_observation: SecurityAttestorRepositoryObservationV1
    result_tag_ruleset_observation: SecurityAttestorResultTagRulesetObservationV1
    immutable_release_setting_observation: SecurityAttestorImmutableReleaseObservationV1
    observed_at_utc: CanonicalTimestamp
    receipt_sha256: Sha256


class RejectedResultReleasePlanFixture(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    correction_lineage_sha256: Sha256 | None
    input_tag_object_sha: GitObjectId
    input_commit_sha: GitObjectId
    campaign_registry_sha256: Sha256
    protocol_attestation_tag_binding_sha256: Sha256
    workflow_root: Sha256
    authority_state_sha256: Sha256
    unresolved_hold_root_sha256: Sha256 | None
    active_credential_exposure_pending_root_sha256: Sha256 | None
    bundle_kind: Literal["complete"]
    bundle_sha256: Sha256
    audit_protocol_sha256: Sha256
    publication_plan_sha256: Sha256
    publication_merge_receipt_sha256: Sha256
    security_attestor_receipt: SecurityAttestorReceiptV1
    publication_pr_number: StrictPositiveInt
    publication_approved_head_sha: GitObjectId
    merge_commit_sha: GitObjectId
    result_tree_sha256: Sha256
    tag_target_kind: Literal["initial_merge", "correction_approved_head"]
    tag_target_sha: GitObjectId
    result_tag_name: BoundedNonBlankString
    tagger_name: Literal["Laconian Benchmark Release"]
    tagger_email: Literal["benchmark-release@laconian.invalid"]
    tagger_timestamp: CanonicalTimestamp
    tag_message: BoundedNonBlankString
    expected_tag_object_sha: GitObjectId
    release_name: BoundedNonBlankString
    release_body_sha256: Sha256
    require_immutable_release: Literal[True]
    release_workflow_path: Literal[".github/workflows/benchmark-release.yml"]
    release_workflow_sha256: Sha256
    assets: tuple[ReleaseAssetV1, ReleaseAssetV1]
    plan_sha256: Sha256
```

The initial tag is exactly `benchmark-result-{campaign_id}`. A correction tag is exactly
`benchmark-result-{campaign_id}-correction-{N}` where N is the monotonic correction attempt, and requires the matching
`CorrectionLineageV1.lineage_sha256`. For an initial plan,
`tag_target_kind="initial_merge"` and `tag_target_sha == merge_commit_sha`. For a correction,
`tag_target_kind="correction_approved_head"` and `tag_target_sha` equals the original correction
intent's preauthorized approved `head_oid`; actual `merge_commit_sha` remains mandatory lineage and
admission evidence and must have exact parents `[base_oid, head_oid]` and the expected tree. No
existing tag or release is updated, deleted, retargeted, or overwritten. Initial tagger timestamp is
derived only from the authenticated raw observed merge commit's committer header frozen in
`PublicationMergeReceiptV1`: parse exact epoch seconds and strict `[+-][0-9]{4}` offset, reject
overflow/nonintegral/duplicate committer headers, normalize to UTC, and require
`tagger_timestamp == merge_committer_timestamp_utc`. It is never derived from `merged_at`, workflow
clock, receipt observation time, caller input, locale, or host timezone. Correction tagger identity/timestamp is copied
byte-for-byte from `CorrectionReleaseIntentPlanV1`, where it was frozen prepublication. Normalize
the timestamp to Git's exact UTC `+0000` representation and construct the annotated-tag bytes with
the fixed name/email, exact `tag_target_sha`/type/tag, and one canonical LF-terminated message. Compute
`expected_tag_object_sha` with `git mktag` in a locale/timezone-independent environment before any
GitHub call. A rerun must reproduce the same object ID; a tagger clock, identity, message, or newline
override is forbidden.
Golden tests run with shifted wall clocks and distinct `TZ`/locale values and require identical
merge receipt, tagger timestamp, raw annotated-tag bytes/OID, asset USTAR mtimes, and release plan;
epoch/offset/raw-commit substitution fails.

Implement the approved overlay instead: initial planning first emits receipt-free
`InitialPreauthorizedResultReleasePlanV1`; the release-preparation attestor then emits either
`SecurityAttestorReceiptV1(result="pass")` or `SecurityAttestorFailureEvidenceV1`; only a pass may
construct `ExecutableResultReleasePlanV1(intent_kind="initial")` and then
`ResultReleaseIntentV1`. Tests exercise both initial/correction target variants and reject
initial-target-as-head, correction-target-as-merge, wrong actual merge parents/tree, or any
disagreement among the preauthorized plan, executable plan, annotated-tag bytes/OID,
`TagReceiptV1.target_commit_sha`, and the authoritative intent.

The preauthorized and executable plans' audit-protocol digest must exactly equal the Publication
plan, complete bundle, evidence inventory, and verified Runtime registry value. The sole source
remains Runtime Task 2's verified peeled-C0
`benchmarks/protocols/public-three-model-v1/audit.json` digest under the Evaluation-owned
`audit_protocol_sha256: Sha256` contract; the finalizer accepts no separate input.

Release planning is forbidden for `invalid_prefix`, `INVALID_PREFIX_MERGED`, and
`INVALID_PREFIX_MERGED_INVALID`; those states are terminal and authorize no tag, Release, asset,
correction, documentation, website, release note, or social promotion.

- [ ] **Step 2: Add failing defect and collision tests**

Reject a nonmerged/closed/unapproved PR, changed approved head, wrong merge tree, absent bundle,
post-merge provenance/security defect, moved `main`, tag name collision, tag pointing elsewhere,
release collision, missing/extra/changed asset, returned asset digest mismatch, and mutable update or
delete attempts. Verify a defect produces `RELEASE_PLAN_INVALIDATED` and `RELEASE_BLOCKED` through
the Slice 3 state interface before any tag API call when detected preflight. For a failure discovered
after an external call, require phase-accurate `BlockedReleaseObjectsV1` containing every observed
tag/draft/asset identity; never claim the objects are absent or released.
Vary source filesystem mtimes, owners, permissions, enumeration order, locale, timezone, and umask;
the asset tar and annotated-tag object must remain byte-identical. Add tag-object collision vectors
for every fixed header/message field.

Add `RELEASED` and `RELEASE_BLOCKED` correction fixtures. Require a new append-only result directory,
merge, tag, release, assets, publication/release plans, and receipts whose lineage supersedes the
exact previous bundle/result/tag/release where present. Reject any attempt to reuse the original
result path/tag/release ID or omit the visible `supersedes` record.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_security_attestor_credential_finality.py tests/campaign/test_release_authorization_graph.py tests/campaign/test_release_finalizer_credential_finality.py tests/campaign/test_reconciliation_unavailable.py tests/campaign/test_result_release.py -q`

Expected: FAIL because the release-plan builders, release-finalizer policy rows, and finalizer are
absent from the Task 10 security-attestor-only foundation.

- [ ] **Step 4: Implement the three-stage release-plan construction**

The following old one-stage signatures are negative fixtures and must not exist in production:

```python
def build_result_release_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    publication_plan: PublicationPlanV1,
    publication_receipt: PublicationPRReceiptV1,
    publication_merge_receipt: PublicationMergeReceiptV1,
    security_attestor_receipt: SecurityAttestorReceiptV1,
    asset_root: Path,
) -> RejectedResultReleasePlanFixture:

def build_result_release_intent(
    *,
    authority: ReconstructedAuthorityV1,
    release_plan: RejectedResultReleasePlanFixture,
) -> ResultReleaseIntentV1:

def build_correction_release_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    correction_intent: CorrectionIntentV1,
    correction_publication_receipt: CorrectionPublicationReceiptV1,
    correction_merge_receipt: CorrectionMergeReceiptV1,
    security_attestor_receipt: SecurityAttestorReceiptV1,
    correction_lineage: CorrectionLineageV1,
    asset_root: Path,
) -> RejectedResultReleasePlanFixture:
```

Implement these exact production boundaries instead:

```python
def build_initial_preauthorized_result_release_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    publication_plan: PublicationPlanV1,
    publication_receipt: PublicationPRReceiptV1,
    publication_merge_receipt: PublicationMergeReceiptV1,
    asset_root: Path,
) -> InitialPreauthorizedResultReleasePlanV1: ...


def build_executable_result_release_plan(
    *,
    authority: ReconstructedAuthorityV1,
    preauthorized_plan: InitialPreauthorizedResultReleasePlanV1 | CorrectionReleaseIntentPlanV1,
    security_attestor_receipt: SecurityAttestorReceiptV1,
    admitted_merge_receipt: PublicationMergeReceiptV1,
) -> ExecutableResultReleasePlanV1: ...


def build_result_release_intent(
    *,
    authority: ReconstructedAuthorityV1,
    executable_release_plan: ExecutableResultReleasePlanV1,
) -> ResultReleaseIntentV1: ...
```

Neither release builder accepts a workflow path/hash scalar. Reconstruct the retained verified C0
`CampaignInputPackageV1` from authority genesis and require its canonical package digest to equal
`authority.registry.payload.campaign_input_package_sha256`. Import/class-bound revalidate only
Evaluation's `WorkflowInventoryV1`, rebuild it from the exact retained C0 bytes, and require its root
to equal `authority.registry.payload.workflow_root`. Resolve only the literal
`.github/workflows/benchmark-release.yml` member, descriptor-read and re-hash its exact C0 bytes,
and bind the path and hash in the release plan. Reject path/hash substitution, a non-C0 or mutable-
`main` workflow, package-digest or inventory-root drift, or any CLI/workflow override.

Require `authority.state.state == "RESULT_MERGED"`, call
`require_ordinary_effect_gate(authority)`, and require the
exact approved head, actual merge commit,
result tree, bundle, and `PublicationMergeReceiptV1` bound by the state transition, and
two asset bytes. Implement a separate release-owned `_write_result_release_ustar` in `release.py`;
do not call the capsule-specific Slice 1 `pack_checkpoint`, whose filename/provenance/mode/mtime
contract is intentionally different. The release writer accepts only the already verified
`PublicFileV1` inventory plus descriptor-owned committed result root and writes:
UTF-8-byte-sorted normalized relative names; regular files only; `uid=gid=0`; empty `uname/gname`;
mtime exactly `tagger_timestamp` converted to integral UTC epoch seconds; modes normalized to `0644`; no PAX, GNU, sparse, link, device, socket, or
extended header; exact USTAR numeric encoding; exactly two zero end blocks; and no trailing bytes.
The checksum sidecar is lowercase SHA-256, two spaces, exact tar filename, LF. Host metadata and
`tarfile` defaults may not influence either asset.

For corrections, a separate `build_correction_release_plan` accepts terminal `RELEASED` or
`RELEASE_BLOCKED`, authoritative `CorrectionIntentV1`, `CorrectionPublicationReceiptV1`,
`CorrectionMergeReceiptV1`, the same `CorrectionLineageV1`, and asset root; it derives and
revalidates every nested publication/release value from those correction-specific records rather
than accepting generic publication-plan/receipt arguments. It requires the new correction result path and does not change campaign state
while planning. Initial and correction release plans share the exact asset construction and finalizer, but a
correction can only create its new attempt-specific tag/release. Every name, marker, asset digest,
actor, exact head target, and idempotency key must equal the already persisted correction intent;
the post-merge builder binds observed `M` only as lineage/admission evidence and cannot invent a new
external effect identity.

Before any initial release effect, `RESULT_RELEASE_INTENT_AUTHORIZED` persists
`publication/initial/<publication-plan-id>/release-intent.json` by expected-OID CAS while state
remains `RESULT_MERGED`. The strict `ResultReleaseIntentV1` binds campaign ID,
`campaign_registry_sha256`, publication ID, deterministic annotated-tag bytes/OID/name/target, exact draft
Release name/body/marker, ordered asset names/sizes/digests, release-finalizer actor, immutable-
Release policy root, and distinct idempotency keys for tag, draft, each asset, publish, every receipt,
finalization, and invalidation. `build_result_release_intent` derives every field from canonical
authority and `ExecutableResultReleasePlanV1(intent_kind="initial")`; no workflow scalar participates. A correction is eligible only
after its valid `merge-receipt.json`, which binds the original authoritative `CorrectionIntentV1`
and release-plan hash without embedding a second intent. Missing intent, wrong parent OID,
cross-lineage names, or a release effect after correction publication invalidation fails before the
external release-finalizer broker may mint its operation-scoped credential.

- [ ] **Step 5: Implement the standard-library-only release finalizer**

`tools/benchmark_release_finalizer.py` accepts only package ZIP, repository, and receipt path. The
package contains the exact finalizer plus the hash-bound secret-free
`tools/benchmark_release_broker_client.py`; it contains no App identity secret, private key, JWT,
installation token, Authorization header, or token handle. It verifies the package/plan,
independently rebuilds the annotated-tag bytes, and requires its object ID to equal
`expected_tag_object_sha`. The authority-selected invocation submits at most one canonical
operation request to the measured external release-finalizer broker: create/adopt tag object/ref,
create/adopt draft, one asset ordinal, publish/adopt, final verification, or terminal reconciliation.
The broker selects the exact `ReleaseFinalizerOperationPolicyRowV1`, owns/vaults the token and
GitHub TLS, performs the row's reads/effect, closes the token, seals its signed ledger/audit prefix,
and returns only safe transport/delivery-resolution/closure receipts. The two assets are separate
ordinals and separate broker calls: ordinal 0 must reconcile and close before ordinal 1. Sharing a
token, fingerprint, effect result, revocation, or operation row across ordinals is forbidden. No
per-asset authority path exists.

`release.py` remains the canonical owner of every release-finalizer and security-attestor record.
`release_broker.py` imports and validates those exact class objects and defines no duplicate schema.
Extend `ReleaseFinalizerBrokerPolicyV1` with the frozen initial/correction callers and only the
literal effect tuples `(tag,tag_object,0)`, `(tag,tag_ref,1)`,
`(draft_release,draft_release,0)`, `(asset,asset,0)`, `(asset,asset,1)`,
`(publish,publish,0)`, `(final_verification,final_verification,0)`, plus the single
`(terminal_reconciliation_read,terminal_reconciliation_read,0)` row. Each write row uses only its
exact applicable `contents:write`, `metadata:read` permission pair and the normative
create/adopt endpoint subset; the reconciliation row uses only `contents:read`, `metadata:read` and
the exact tag/Release/assets/latest-pointer GET inventory. The phase is monotone
`constructive -> terminal_reconciling -> sealed`; entering reconciliation disables every write mint
and `sealed` denies every later mint. Each caller and operation form one indivisible policy row,
each asset ordinal gets a separate row/token lifecycle, and no caller-selected permission or
endpoint union is valid. `ReleaseFinalizerCallerV1` fixes caller job `release_finalizer` and OIDC
audience `laconian-release-finalizer-broker`; every security-attestor row fixes job
`security_attestor` and audience `laconian-security-attestor-broker`. Tests reject either audience,
job, workflow, ref, or environment substituted independently.
  Each successful broker operation returns Runtime's acyclic `ReleaseEffectResultV1`, the exact
  `InstallationTokenRevocationReceiptV1`/closure projection, and then the matching `TagReceiptV1`,
  `DraftReleaseReceiptV1`,
  `ReleaseAssetReceiptV1`, `PublishReceiptV1`, or `FinalReleaseVerificationReceiptV1`. Final
  verification constructs the latter from the exact immutable verification and complete external-
  object root; only then may Publication build `ReleaseNoLaterEffectsEvidenceV1` and the terminal
  `InitialPublicationFinalizationV1`. For an initial release the secret-free recorder wraps the next exact receipt in
  `InitialReleaseReceiptAppendV1` and the broker persists its allowlisted path by expected-OID CAS
  with byte-identical CampaignState hash; this is the closed §7.6 non-state authority append, not an
  invented CampaignState event. The next phase is ineligible until that phase's receipt append wins;
  within aggregate-assets, ordinal 1 is authorized by the same phase and only after ordinal 0 is
  reverified, and both receipts are appended once as `asset-receipts.json`. For a correction, the approved
  `CORRECTION_TAG_RECORDED` wrapper persists the tag receipt, and the later approved
  `CORRECTION_RELEASE_RECORDED` wrapper aggregates the draft, both assets, publish, and final release
  receipts. The fixed serialized finalizer never skips a missing predecessor receipt and never
  performs an untracked retry.

The following entire block is a predecessor-wire rejection fixture. Every shown field layout is
negative, and every `Rejected*` class name is forbidden. If an unprefixed class name remains in the
approved overlay, production implements only that overlay's current exact shape; the predecessor
payload shown here must still fail before token mint or GitHub dispatch:

```python
class RejectedResultReleaseIdempotencyKeysFixture(CapsuleModel):
    schema_version: Literal["1"]
    release_intent_cas_key: Sha256
    tag_effect_key: Sha256
    draft_release_effect_key: Sha256
    first_asset_effect_key: Sha256
    second_asset_effect_key: Sha256
    publish_effect_key: Sha256
    final_verification_effect_key: Sha256
    tag_receipt_append_cas_key: Sha256
    draft_release_receipt_append_cas_key: Sha256
    first_asset_receipt_key: Sha256
    second_asset_receipt_key: Sha256
    asset_receipts_append_cas_key: Sha256
    publish_receipt_append_cas_key: Sha256
    finalization_key: Sha256
    invalidation_key: Sha256


class ResultReleaseIntentV1(CapsuleModel):
    schema_version: Literal["ResultReleaseIntentV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    release_plan_sha256: Sha256
    security_attestor_receipt: SecurityAttestorReceiptV1
    security_attestor_receipt_sha256: Sha256
    authority_parent_oid: GitObjectId
    annotated_tag_bytes_sha256: Sha256
    expected_tag_object_sha: GitObjectId
    result_tag_name: BoundedNonBlankString
    target_commit_sha: GitObjectId
    tag_message: BoundedNonBlankString
    draft_release_name: BoundedNonBlankString
    draft_release_body: BoundedNonBlankString
    draft_release_marker: BoundedNonBlankString
    assets: tuple[ReleaseAssetV1, ReleaseAssetV1]
    release_finalizer_app: GitHubAppInstallationIdentityV1
    immutable_release_policy_sha256: Sha256
    idempotency_keys: RejectedResultReleaseIdempotencyKeysFixture
    intent_sha256: Sha256


# Import, class-bound revalidate, and re-export Runtime-owned GitHubOidcRunIdentityV1,
# ReleaseEffectAuthorizationV1, ReleaseEffectResultV1, TagReceiptV1, DraftReleaseReceiptV1,
# ReleaseAssetReceiptV1, PublishReceiptV1, FinalReleaseVerificationReceiptV1, all four
# Initial*ReceiptAppendV1 variants, InitialReleaseReceiptAppendV1, and
# InstallationTokenRevocationReceiptV1 and append_initial_release_receipt. Publication must not
# redefine any of them.

# Each imported concrete effect receipt contains the same strict
# ReleaseEffectAuthorizationV1. It has exact fields authorizing_intent_sha256,
# preauthorized_release_plan_sha256, executable_release_plan_sha256, and
# security_attestor_receipt_sha256. For intent_kind="initial", authorizing_intent_sha256 equals the
# authoritative ResultReleaseIntentV1 digest and the two plan hashes both equal its exact
# RejectedResultReleasePlanFixture. For intent_kind="correction", authorizing_intent_sha256 equals the
# authoritative CorrectionIntentV1 digest, preauthorized_release_plan_sha256 equals its nested
# CorrectionReleaseIntentPlanV1 digest, and executable_release_plan_sha256 equals the postmerge
# RejectedResultReleasePlanFixture proven to be its deterministic derivation. Runtime's
# initial append API accepts only intent_kind="initial" and enforces closed path/order/expected-OID
# rules while leaving the CampaignState hash byte-identical. The authorization also carries the
# exact plan-bound security_attestor_receipt_sha256; every concrete receipt must repeat it.


class ImmutableReleaseVerificationV1(CapsuleModel):
    schema_version: Literal["ImmutableReleaseVerificationV1"]
    repository_setting_response_sha256: Sha256
    release_fields_sha256: Sha256
    gh_version: BoundedNonBlankString
    gh_binary_sha256: Sha256
    gh_release_verify_output_sha256: Sha256
    verification_sha256: Sha256


class ReleaseInventoryDefectEvidenceV1(CapsuleModel):
    schema_version: Literal["ReleaseInventoryDefectEvidenceV1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    durable_authority_checkpoint_sha256: Sha256
    expected_tag_object_sha: GitObjectId
    expected_tag_target_sha: GitObjectId
    expected_release_id: StrictPositiveInt
    expected_release_fields_sha256: Sha256
    expected_asset_root_sha256: Sha256
    expected_actor_root_sha256: Sha256
    observed_tag_root_sha256: Sha256 | None
    observed_release_root_sha256: Sha256 | None
    observed_asset_root_sha256: Sha256 | None
    observed_actor_root_sha256: Sha256 | None
    defect_kinds: tuple[
        Literal[
            "tag_missing",
            "tag_object_diverged",
            "tag_target_diverged",
            "release_missing",
            "release_fields_diverged",
            "assets_diverged",
            "actors_diverged",
        ],
        ...,
    ]
    safe_request_receipts_root_sha256: Sha256
    observed_at_utc: CanonicalTimestamp
    evidence_sha256: Sha256


class ReleaseInventoryAlertReceiptV1(CapsuleModel):
    schema_version: Literal["ReleaseInventoryAlertReceiptV1"]
    evidence_sha256: Sha256
    cadence_slot_utc: CanonicalTimestamp
    alert_idempotency_key: Sha256
    alert_sink_identity_sha256: Sha256
    operation: Literal["emitted", "adopted"]
    safe_response_receipt_sha256: Sha256
    alerted_at_utc: CanonicalTimestamp
    receipt_sha256: Sha256


class RejectedResultReleaseReceiptFixture(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    effect_authorization: ReleaseEffectAuthorizationV1
    security_attestor_receipt_sha256: Sha256
    tag_receipt: TagReceiptV1
    draft_release_receipt: DraftReleaseReceiptV1
    asset_receipts: tuple[ReleaseAssetReceiptV1, ReleaseAssetReceiptV1]
    publish_receipt: PublishReceiptV1
    final_verification_receipt: FinalReleaseVerificationReceiptV1
    correction_lineage_sha256: Sha256 | None
    release_plan_sha256: Sha256
    bundle_kind: Literal["complete"]
    bundle_sha256: Sha256
    result_tag_name: BoundedNonBlankString
    tag_object_sha: GitObjectId
    target_commit_sha: GitObjectId
    release_operation: Literal[
        "created_tag_and_release",
        "reused_tag_created_release",
        "resumed_exact_draft",
        "observed_exact_published",
    ]
    release_id: StrictPositiveInt
    release_url: ExactAsciiHttpUrl
    published_at_utc: CanonicalTimestamp
    immutable: Literal[True]
    immutable_release_verification: ImmutableReleaseVerificationV1
    assets: tuple[ReleaseAssetV1, ReleaseAssetV1]
    repository_id: StrictPositiveInt
    workflow_run_id: StrictPositiveInt
    run_attempt: StrictPositiveInt
    job_id: StrictPositiveInt
    job_name: Literal["release_finalizer"]
    environment: Literal["benchmark-publish"]
    deployment_id: StrictPositiveInt
    approval_actor_id: StrictPositiveInt
    approval_actor_login: BoundedNonBlankString
    release_app: GitHubAppInstallationIdentityV1
    released_by: BoundedNonBlankString
    receipt_sha256: Sha256


class RejectedResultReleaseFinalizationFixture(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    effect_authorization: ReleaseEffectAuthorizationV1
    security_attestor_receipt_sha256: Sha256
    tag_receipt: TagReceiptV1
    draft_release_receipt: DraftReleaseReceiptV1
    asset_receipts: tuple[ReleaseAssetReceiptV1, ReleaseAssetReceiptV1]
    publish_receipt: PublishReceiptV1
    final_verification_receipt: FinalReleaseVerificationReceiptV1
    result_release_receipt: RejectedResultReleaseReceiptFixture
    durable_authority_checkpoint: "RejectedDurableAuthorityCheckpointFixture"
    durable_authority_checkpoint_sha256: Sha256
    finalization_sha256: Sha256


class RejectedPreIntentResultReleaseInvalidationFixture(CapsuleModel):
    schema_version: Literal["1"]
    phase: Literal["pre_intent"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    cause: Literal["ordinary", "credential_exposure"]
    merge_commit_oid: GitObjectId
    result_tree_oid: GitObjectId
    defect_evidence_sha256: Sha256
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1 | None
    consumed_unresolved_hold_id: BoundedNonBlankString | None
    consumed_unresolved_hold_root_sha256: Sha256 | None
    no_external_effects_evidence_sha256: Sha256
    invalidation_sha256: Sha256


class RejectedPostIntentResultReleaseInvalidationFixture(CapsuleModel):
    schema_version: Literal["1"]
    phase: Literal["post_intent"]
    campaign_id: BoundedNonBlankString
    campaign_registry_sha256: Sha256
    publication_id: BoundedNonBlankString
    cause: Literal["ordinary", "credential_exposure"]
    release_intent_sha256: Sha256
    defect_evidence_sha256: Sha256
    consumed_unresolved_hold_id: BoundedNonBlankString | None
    consumed_unresolved_hold_root_sha256: Sha256 | None
    terminal_exposure_consumption: TerminalCredentialExposureConsumptionV1 | None
    blocked_release_objects: BlockedReleaseObjectsV1
    tag_receipt: TagReceiptV1 | None
    draft_release_receipt: DraftReleaseReceiptV1 | None
    asset_receipts: tuple[ReleaseAssetReceiptV1, ...]
    publish_receipt: PublishReceiptV1 | None
    reconciliation_receipts_root_sha256: Sha256
    invalidation_sha256: Sha256


RejectedResultReleaseInvalidationFixture = Annotated[
    RejectedPreIntentResultReleaseInvalidationFixture
    | RejectedPostIntentResultReleaseInvalidationFixture,
    Field(discriminator="phase"),
]
```

Production instead uses the overlay's exact `ResultReleaseIntentV1`,
`ReleaseEffectDeliveryResolutionV1`, four initial receipt-append wrappers,
`ReleaseFinalizerOperationSetV1`, `ReleasePlanInvalidationEvidenceV1`,
`InitialPublicationInvalidationV1`, and `InitialPublicationFinalizationV1`. The success terminal
record names all four accepted append-wrapper digests, the final verification receipt, and exact
`ReleaseNoLaterEffectsEvidenceV1`; an invalidation names its phase-exact preparation/effect prefix,
operation set, stable no-later proof or sealed reconciliation-unavailable receipt. No aggregate
`RejectedResultReleaseReceiptFixture`, second finalization wrapper, or pre/post-intent generic invalidation is
admitted.

Class-bound revalidate every imported shared receipt. Tests reject initial/correction intent-kind
substitution, an initial receipt naming a correction intent, a correction receipt naming a
`ResultReleaseIntentV1`, any release-plan mismatch, a correction receipt whose authorization does
not equal the original `CorrectionIntentV1` plus its nested release plan, and any correction receipt
passed to `append_initial_release_receipt`. `CorrectionTagReceiptV1` and
`CorrectionReleaseReceiptV1` additionally require all nested shared receipts to carry the identical
correction authorization; their authoritative phase wrappers, not the inner draft/asset/publish
receipts individually, each win one correction CAS.
`tests/test_public_contract.py` asserts that Publication re-exports the identical Runtime class
objects for `GitHubOidcRunIdentityV1`, `ReleaseEffectAuthorizationV1`, `ReleaseEffectResultV1`,
`InstallationTokenRevocationReceiptV1`, `FinalReleaseVerificationReceiptV1`, and all four effect receipts, and freezes the authorization
field names `authorizing_intent_sha256`, `preauthorized_release_plan_sha256`,
`executable_release_plan_sha256`, and `security_attestor_receipt_sha256`.

`RELEASE_PLAN_INVALIDATED` may occur directly from `RESULT_MERGED` before release intent or from one
of the five exact post-intent phases. Every route uses
`ReleasePlanInvalidationEvidenceV1.release_phase=pre_intent|release_intent|tag_receipt|
draft_release_receipt|asset_receipts|publish_receipt` and one strict
`ReleasePlanInvalidationDetailV1`. Pre-intent evidence proves zero authorization/mint/dispatch and
complete external-object absence or preserves a preexisting conflict. Post-intent evidence binds
the executable graph, every accepted append wrapper, every discovered external object, complete
`ReleaseFinalizerOperationSetV1`, and stable `ReleaseNoLaterEffectsEvidenceV1`; the
`release_reconciliation_unavailable` row instead carries its sealed unavailable receipt and null
no-later root. Credential exposure, drift, and nondismissible hold use only their exact class-bound
consumers. The terminal CAS installs `InitialPublicationInvalidationV1`, consumes the matching
active root/hold when required, and never fabricates absence or a success aggregate. Tests cover all
six phases, all closed reasons, partial tag/assets, exposure before/after intent, half-null roots,
hidden objects, cross-intent replay, mixed variants, and reconciliation-unavailable.

`SecurityAttestorReceiptV1` is produced only after an exact receipt-free preauthorized plan and
before its executable plan/initial intent. It binds that plan root, the applicable admitted merge,
purpose-specific repository/ruleset/immutable-setting observations, the complete
`SecurityAttestorCredentialDispositionSetV1`, signed broker ledger, and closed token. Failure emits
`SecurityAttestorFailureEvidenceV1` and can only feed release invalidation. The returned permission
tuple is exactly `administration:write`, `contents:read`, `metadata:read`; the signed policy permits
only the purpose row's authenticated GET endpoints. Observation and closure times come from signed
broker/GitHub receipts, never caller time. Golden fixtures cover every policy row, request/transport
outcome, permission order, initial/correction discriminator, raw/canonical swap, pagination,
omitted/extra field, digest mutation, and same-token post-boundary dispatch.
The Runtime-owned `GitHubOidcRunIdentityV1` is class-bound revalidated in full, including repository
name/ID, owner, actor and triggering actor, ref/SHA/event, caller/callee workflow paths and SHAs,
run/attempt/job/check-run, runner/environment, issuer/audience/subject/JTI/time and JWKS evidence.
Tests reject wrong job/check-run/deployment/environment approval, rerun actor, ref/SHA, caller or
callee SHA, expired response, token material in a safe response, and reused JTI.

The initial success dependency is strictly one-way: publication merge receipt ->
`InitialPreauthorizedResultReleasePlanV1` -> closed passing security-attestor receipt ->
`ExecutableResultReleasePlanV1` -> initial intent -> Runtime `ReleaseEffectAuthorizationV1` ->
delivery resolutions and receipt appends -> final verification -> release no-later evidence ->
`InitialPublicationFinalizationV1`. A closed initial attestor failure instead feeds only the
phase-exact `RELEASE_PLAN_INVALIDATED` evidence and can produce no executable plan, intent, or
effect authorization. The correction success dependency is original prepublication correction
intent with nested `CorrectionReleaseIntentPlanV1` -> publication receipt -> correction merge
receipt -> closed passing attestor receipt -> `ExecutableResultReleasePlanV1` -> effect
authorization/receipts -> aggregate correction release wrapper -> correction finalization. A
closed correction attestor failure feeds only its exact correction release invalidation and can
produce no executable plan or effect. There is no second correction intent and the original intent
cannot hash the future attestor receipt. Each
post-attestation successor repeats the receipt digest and class-bound revalidates the complete
receipt from authority/archive. The four initial append wrappers retain the ordered shared receipt
digests without changing CampaignState; `InitialPublicationFinalizationV1` then binds those wrapper
digests, the exact final-verification receipt, and release no-later evidence. No predecessor hashes a
successor, so self-reference is impossible. Tests independently rebuild every preimage, mutate each lineage/request/response/
permission field, reject correction-future-merge substitution, and prove the graph is acyclic.
For durability, initial `release-intent.json` embeds the complete
`SecurityAttestorReceiptV1` plus its digest. Correction adds no path: the first post-attestation
authoritative `CorrectionTagReceiptV1` wrapper embeds the complete fresh receipt and complete
`ExecutableResultReleasePlanV1` plus both digests before its CAS; later correction aggregate,
operation-set/no-later evidence, and finalization bind those embedded objects. No attestor token is
live after a pass/failure record. If that closed record becomes stale under its plan-bound freshness
policy before the executable plan or tag wrapper, rerun attestation and rebuild the executable plan
before any release credential/effect;
after the tag-wrapper CAS, reconstruction uses its durable canonical bytes and never a transient
artifact. Tests delete/expire every Actions artifact at each prefix and require identical offline
reconstruction, while mismatched full-object/digest pairs and a seventh correction path fail.

Require `release_app.role == "release_finalizer"`, `released_by == release_app.bot_login`, the
pre-registered App/installation/repository IDs, and exact permission attestation. Reject the
publisher/state Apps, `github-actions[bot]`, or any permission response other than the closed
per-operation write-row tuple `contents:write`, `metadata:read` (whose reachable surface includes the
required new-tag/release/asset endpoints); the reconciliation-read row is exactly
`contents:read`, `metadata:read`. No row contains Actions or Deployments permission. The installed App
also has `administration:write`, but that permission is omitted from the write token and appears only
on the separately brokered `security_attestor` token. Derive
`published_at_utc` only by re-fetching the created/existing GitHub release; reject a naive,
noncanonical, caller-supplied, or workflow-clock timestamp.

Freeze the finalizer's write endpoint allowlist to the exact annotated-tag-object/ref creation,
draft-Release creation, asset upload, and one `PATCH /repos/{owner}/{repo}/releases/{release_id}`
whose sole mutation is the plan-bound draft-to-published transition. Concretely, no Contents API,
GraphQL mutation, tag update/delete, Release delete, asset delete/update, or general Release edit is
allowed. Every request binds the intent key, exact numeric repository/release IDs, actor, request ID,
and pre/post observation into its effect receipt.

```text
POST /repos/{owner}/{repo}/git/tags
POST /repos/{owner}/{repo}/git/refs
POST /repos/{owner}/{repo}/releases
POST https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name={asset_name}
PATCH /repos/{owner}/{repo}/releases/{release_id}  # draft true -> false only
DELETE /installation/token  # revoke only the current finalizer authentication token
```

After every create/adopt effect, safe failure, or response-loss reconciliation, the external
release-finalizer broker calls the exact token-revocation endpoint and denial probe before returning
only safe receipts; the runner finalizer merely verifies those signed records. Runtime's strict
`InstallationTokenRevocationReceiptV1` records the effect authorization, nonsecret token
fingerprint, endpoint, request receipt, `204` response or response-loss recovery observation,
post-revocation authentication-denial probe, canonical UTC timestamp, and self digest. Each concrete
effect receipt, `ReleaseFinalizerCredentialDispositionV1`, and final
`ReleaseFinalizerOperationSetV1` binds the matching revocation/closure root; authority cannot append
the receipt or terminalize without it. A lost revocation response is recovered only by proving the
same token unusable, while a token that remains usable is a credential exposure and cannot be
reported as success. Tests cover 204, response loss, expiry, revoke failure, crash before/after
revoke, replay across effects/tokens, zero post-boundary dispatch, and guaranteed scrubbing. This
auth-token DELETE is explicitly distinct from and does not authorize any Git ref, tag object,
Release, asset, branch, or other object deletion.

After receipt-free preauthorization and before executable-plan/intent authorization, the fixed
`security_attestor` job in `.github/workflows/benchmark-release.yml` presents only its exact OIDC
identity and preauthorized-plan subject to the external broker. That broker alone mints, vaults,
uses, and closes the short-lived release-finalizer installation token downscoped to
`administration:write`, `contents:read`, and `metadata:read`, fetches the exact repository, ruleset,
and immutable-setting endpoints, and returns only the strict signed plan-bound
`SecurityAttestorReceiptV1` or failure evidence. False, missing, malformed, permission-expanded, or
unbound responses fail closed. The Actions job and release finalizer receive only the verified safe
receipt and never receive an administration-capable token or call repository/ruleset/immutable-setting admin
endpoints. Draft recovery fully paginates authenticated `GET /repos/{owner}/{repo}/releases`, matches
one unique intent marker/tag/author, and then fetches that exact release ID. The by-tag endpoint is
not used to discover drafts. Published recovery may use
`GET /repos/{owner}/{repo}/releases/tags/{tag}` but still re-fetches by numeric ID. Asset recovery
fully paginates the exact release's assets. After an upload timeout, HTTP 422, or HTTP 502, relist
and adopt only exact name/content-type/size/provider-digest/uploader evidence; when the API digest
is absent, download and hash the bytes. A `starter` asset or divergent same-name object is terminal
failure evidence and is never overwritten or silently retried.

The authenticated read allowlist is concrete and closed:

```text
GET /repos/{owner}/{repo}/immutable-releases
GET /repos/{owner}/{repo}/releases?per_page=100&page={page}
GET /repos/{owner}/{repo}/releases/{release_id}
GET /repos/{owner}/{repo}/releases/tags/{tag}
GET /repos/{owner}/{repo}/releases/{release_id}/assets?per_page=100&page={page}
GET /repos/{owner}/{repo}/releases/assets/{asset_id}  # octet-stream download only when digest is absent
```

Pagination continues through the authenticated response's final page; a truncated page sequence is
not absence evidence. No by-tag lookup participates in draft discovery.

After publish, require returned `immutable == true` and run a pinned/versioned
`gh release verify` for the exact repository/tag/release/assets. Hash the canonical setting
response, Release fields, pinned CLI version/binary digest, and command output into
`ImmutableReleaseVerificationV1`. GitHub REST does not return a separate platform-attestation
digest for this purpose, so no invented field or claim is accepted. Immutable Releases protect the published tag/assets,
but the implementation does not claim Releases cannot be deleted or every metadata field cannot be
changed. Protected tag rules, immediate finalizer-token revocation, actor alerts, scheduled exact
inventory checks, and authority policy expose and constrain that residual platform risk.

Implement the scheduled inventory check as a concrete external read-only monitor, not a sixteenth
Actions workflow and not a new trigger on any frozen workflow. The deployment runs the checked-in,
C0-hash-verified `tools/benchmark_release_inventory_monitor.py` exactly every 3600 seconds at the
UTC hour boundary under the deployment identity/config frozen in
`ops/benchmark-release-inventory-monitor.toml`. It has no GitHub/repository credential and uses only
public read endpoints plus exact Git object fetches; its sole secret is an external operations-alert
sink credential, mapped only after defect evidence exists and never sent to GitHub. From the active
latest pointer, accepted terminal finalization, and authoritative receipt chain it re-fetches and
revalidates the exact annotated tag object/target, Release numeric ID and immutable fields, ordered
asset IDs/names/sizes/digests, and tag/Release/asset actors. It emits canonical safe
`ReleaseInventoryDefectEvidenceV1` plus an alert to the existing operations sink, but never mutates
GitHub, campaign authority, latest pointer, or release objects; correction still begins only through
the reviewed defect-PR protocol. Evidence and alerts use exact domains
`laconian-release-inventory-defect-evidence-v1\n` omitting only `evidence_sha256` and
`laconian-release-inventory-alert-receipt-v1\n` omitting only `receipt_sha256`. Alert idempotency is
SHA-256 over the literal domain plus CanonicalJSONV1 of `[evidence_sha256, cadence_slot_utc,
alert_sink_identity_sha256]`; retries adopt only an exact prior alert. Independent literal goldens
and fixture-backed normal/divergence/deletion/actor/replay, wrong-slot/credential, duplicate-alert,
and no-mutation tests are owned by `tests/campaign/test_release_inventory_monitor.py`.
`docs/runbooks/benchmark-release-inventory-monitor.md` names the operations owner, deployment/health
check, missed-two-slots escalation, alert acknowledgement, evidence preservation, and reviewed
defect-PR creation; it never directs an operator to repair GitHub objects. Adding `schedule:` to
`benchmark-release.yml` would violate the approved workflow caller/trigger contract and therefore
requires a normative amendment; this external monitor does not.

An exact existing published immutable tag/release is idempotent. An exact draft may resume missing
byte-identical asset uploads and the one publication transition; a divergent draft is invalidated
and left untouched for incident handling. A crash after one upload, after both uploads, or after
publication re-fetches exact state and resumes only the missing step. The executable never deletes,
retargets, replaces, overwrites, or edits a published release, and its only release update is the
single exact draft-to-published transition after both assets verify.
Each tag/draft/asset/publish phase success emits only its Runtime-owned typed effect receipt. A
successful final-verification job emits the Runtime-owned
`FinalReleaseVerificationReceiptV1`. Publication then reconstructs the accepted tag, draft,
ordered-assets, publish, and final-verification chain from the four authoritative append wrappers,
verifies the external broker's signed terminal-reconciliation observations and already closed
read-token receipt, then builds the complete `ReleaseFinalizerOperationSetV1` and
`ReleaseNoLaterEffectsEvidenceV1`. Publication never receives or closes that token. The single terminal
`InitialPublicationFinalizationV1` names those four append-wrapper digests, the final-verification
receipt digest, and the nested exact no-later object/root; there is no aggregate release receipt or
second finalization wrapper. If authority already binds a phase wrapper or terminal finalization, a
later verification run is a no-op only after revalidating its canonical bytes and every plan-bound
external object; racing observations cannot trigger another external update or replace any nested
receipt.
On every non-idempotent failure, re-fetch the bounded tag/release/asset set and emit a safe
`BlockedReleaseObjectsV1`; the broker persists it before any correction can be planned. Conflicting
or externally visible objects are retained as exposure evidence under the no-overwrite/no-reuse
protocol; this is not a claim that the platform makes them undeletable.

Before the first tag API call, the external broker uses the same fixed GitHub runtime identity
variables as the publisher, re-fetches the numeric `release_finalizer` job, deployment, and separate
`benchmark-publish` approval, calls the authority/hold verifier bound by the plan, and re-fetches and
attests the release App. It verifies the already closed plan-bound `release_preparation` attestor
receipt and exact trust-boundary record; neither the release-writer token nor the Actions job
re-fetches the immutable-Releases setting or any Administration-gated endpoint. The per-phase
authorization is repeated in its typed effect receipt and closed
delivery resolution, and the terminal operation set proves the complete authorization ledger and
zero live release-finalizer tokens. Repository `GITHUB_TOKEN` is read-only and is never the release
actor.

Do not add a public campaign CLI. The fixed trusted release-preparation tool selects initial or
correction construction only from verified authority/lineage and accepts no tag, Release, PR,
merge, asset, actor, campaign, correction, or effect identity override.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_security_attestor_credential_finality.py tests/campaign/test_release_authorization_graph.py tests/campaign/test_release_finalizer_credential_finality.py tests/campaign/test_reconciliation_unavailable.py tests/campaign/test_result_release.py tests/campaign/test_release_broker.py tests/campaign/test_release_inventory_monitor.py tests/test_public_contract.py -q`

Expected: PASS.

- [ ] **Step 7: Commit result release planning and finalization**

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/release.py \
  src/laconian_eval/campaign/release_broker.py \
  tools/benchmark_release_finalizer.py \
  tools/benchmark_release_broker_client.py \
  tools/benchmark_release_inventory_monitor.py \
  ops/benchmark-release-inventory-monitor.toml \
  docs/runbooks/benchmark-release-inventory-monitor.md \
  tests/campaign/test_result_release.py \
  tests/campaign/test_release_broker.py \
  tests/campaign/test_security_attestor_credential_finality.py \
  tests/campaign/test_release_authorization_graph.py \
  tests/campaign/test_release_finalizer_credential_finality.py \
  tests/campaign/test_reconciliation_unavailable.py \
  tests/campaign/test_release_inventory_monitor.py \
  tests/test_public_contract.py
git commit -m "feat: bind and finalize benchmark result releases"
```

### Task 12: Add the separately approved release workflow

**Files:**
- Create: `.github/workflows/benchmark-release.yml`
- Modify: `tests/campaign/test_publication_workflows.py`
- Modify: `tests/test_ci_contract.py`

- [ ] **Step 1: Extend the failing workflow contract**

Require a read-only `prepare-release` with exactly `contents: read`, `actions: read`,
`pull-requests: read`, and `checks: read`; a `benchmark-publish` environment job named exactly
`security_attestor`; a secret-free
`authorize-release-intent` candidate job; an intervening call to the Runtime-owned OIDC broker
reusable job named `persist-release-intent`; a separately approved `benchmark-publish` environment
job named `release_finalizer`; and a read-only `record-release` followed by the existing broker
recorder. The dependency chain is exactly `prepare-release -> security_attestor ->
authorize-release-intent -> persist-release-intent -> release_finalizer -> record-release` on a
closed pass. The disjoint failure branch is `prepare-release -> security_attestor ->
build-release-invalidation -> persist-release-invalidation`, where the last job invokes only the
Runtime reusable state broker and terminates the run. The finalizer cannot be scheduled from a
prepare artifact or attestor failure. A correction uses its
already persisted pre-effect `CorrectionIntentV1` and approved merge-receipt phase and adds no
second intent CAS or seventh correction path.

The gated finalizer job has exactly `id-token: write` plus `actions: read`, `deployments: read`, and
`contents: read`; only the latter three are repository-token scopes. It has one repository-owned
`run` step, the hash-bound secret-free release-broker client,
and a `GITHUB_READ_TOKEN` used only for the numeric package GET and unset before the broker request.
It has no provider secret, App/installation ID credential input, private key, installation token,
App-auth Authorization header, opaque token handle, checkout/setup/action step, or generic release
edit/delete command. Only the closed numeric-package downloader may create the read-only repository
token header, and it strips that header before the redirect fetch and broker request.
Only the external measured broker may issue the one exact draft-to-published PATCH after asset
verification. The `security_attestor` job in this workflow requests the exact
`release_preparation` policy row by OIDC audience `laconian-security-attestor-broker` and receives
only the signed plan-bound pass receipt or
failure evidence after the external broker has performed and closed the
`administration:write`, `contents:read`, `metadata:read` GET-only lifecycle. It cannot substitute
repository-token reads and declares exactly `id-token: write` with no repository-token scope. The
similarly named Task 10 job in `benchmark-publish.yml` is a distinct
`postmerge_rule_suite` caller row and cannot supply this receipt. The reusable state job likewise
contains only OIDC bootstrap and the fixed broker client. No repository `GITHUB_TOKEN` can write.
The `release_finalizer` job uses only audience `laconian-release-finalizer-broker`; caller job,
audience, workflow/ref/SHA, environment, and event must byte-equal one indivisible policy row.

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/test_ci_contract.py -q`

Expected: FAIL because `.github/workflows/benchmark-release.yml` is absent.

- [ ] **Step 3: Implement the release workflow**

Trigger only with no-input `workflow_dispatch` at the exact plan-bound `main` SHA. Use the shared
`laconian-public-benchmark-state` concurrency group. For an initial release,
`prepare-release` proves exact `RESULT_MERGED`; for a correction, it proves terminal
`RELEASED|RELEASE_BLOCKED`, an authoritative pre-publication `CorrectionIntentV1`, and exact durable
`publication-receipt.json` and `merge-receipt.json` wrappers. It checks
current PR/merge/tree state and builds only the receipt-free
`InitialPreauthorizedResultReleasePlanV1` or reconstructs the correction intent's exact
`CorrectionReleaseIntentPlanV1`, plus deterministic assets/finalizer package, then uploads it for 90
days. Only after that immutable preauthorized root exists does `security_attestor` request the
workflow-bound `release_preparation` row. A closed pass receipt permits
`authorize-release-intent`; closed failure evidence permits only the phase-exact release-plan
invalidation path and no executable plan, intent, finalizer, or external effect.
`build-release-invalidation` accepts only that closed failure evidence and constructs either the
initial pre-intent `RELEASE_PLAN_INVALIDATED` candidate or the exact
`CORRECTION_INVALIDATED(kind=correction_release_invalidation)` candidate. The reusable
`persist-release-invalidation` call may win only that phase-exact expected-OID CAS; it cannot invoke
`authorize-release-intent`, `persist-release-intent`, `release_finalizer`, or any release broker row.

`authorize-release-intent` has read-only permissions, no environment, App/provider secret, or
external write. It consumes the exact passing receipt and builds
`ExecutableResultReleasePlanV1`. For an initial release it then builds the exact
`ResultReleaseIntentV1` and `RESULT_RELEASE_INTENT_AUTHORIZED` candidate. For correction it
revalidates the immutable original intent's complete release plan against actual `M`, requiring
parents exactly `[base_oid, head_oid]`, the expected tree, and tag target exactly the preauthorized
`head_oid`; it creates no new intent or authority candidate. On the initial path,
`persist-release-intent` presents only the canonical candidate plus OIDC to
the Runtime reusable broker, which reconstructs authority, verifies the expected OID and all direct
campaign/registry/publication bindings, and wins one receive-pack CAS. Only its verified mutation
receipt authorizes `release_finalizer`. On correction, the accepted correction intent and merge-
receipt authority roots are the authorization inputs. In both cases the finalizer reconstructs the
authoritative intent and passing attestor/executable-plan graph from the current authority/archive
before requesting an effect. It downloads by numeric artifact ID, verifies the exact hashed
finalizer and secret-free broker client, unsets `GITHUB_READ_TOKEN`, and submits at most one
canonical OIDC-bound operation to the external release-finalizer broker. No App credential or token
reaches the runner.
`record-release` re-fetches all GitHub objects and emits a receipt-bound candidate only after
verification. It reconstructs the exact annotated tag object/target,
`ImmutableReleaseVerificationV1`, both verified asset digests, the authoritative
tag/draft/ordered-assets/publish receipt chain, and
`FinalReleaseVerificationReceiptV1`; it re-verifies that every prior transient mapping remains
present byte-for-byte. The external release-finalizer broker alone performs the exact
terminal-reconciliation row, closes its read token, and returns signed safe observations and
closure. `record-release` verifies those records, then constructs the exact complete
`ReleaseFinalizerOperationSetV1` and `ReleaseNoLaterEffectsEvidenceV1`; it never receives or closes
the token. Initial success has no aggregate release receipt and no durable
checkpoint wrapper: `InitialPublicationFinalizationV1` directly binds the four accepted append
wrapper digests, final-verification receipt, publication-success finality, and nested release
no-later object/root. Correction success instead uses the exact phase wrappers and
`CorrectionFinalizationV1`. Omission, reorder, duplicate inequality, cross-effect
`ReleaseEffectResultV1`, token closure, attestor, append-wrapper, or final-verification substitution
fails before the final authority CAS. Golden tests independently prove the acyclic order effect
receipts -> accepted append wrappers -> final verification -> operation set/no-later evidence ->
terminal finalization. For the initial release, the broker uses only the four exact non-state
receipt append variants in tag, draft, assets, publish order, retaining the same CampaignState hash,
then binds `InitialPublicationFinalizationV1` and `RESULT_RELEASED` from `RESULT_MERGED`.

Initial dispatch is prefix-exact across one-phase runs. With no release intent it persists only
`RESULT_RELEASE_INTENT_AUTHORIZED`. With an existing intent or tag/draft/assets/publish receipt
prefix, it revalidates the authoritative intent, makes `persist-release-intent` an explicit no-op,
and permits exactly the next missing tag/draft/aggregate-assets/publish phase followed by Runtime's corresponding non-state receipt
append CAS. A complete publish prefix permits only final verification and the single
`RESULT_RELEASED` CAS. Add rerun and crash tests before and after every intent/effect/receipt
boundary. Add the partial-assets crash vector: after ordinal 0 upload and response persistence loss,
the next run adopts exact ordinal 0, uploads/adopts ordinal 1, and wins one aggregate-assets append
CAS. Assert two fresh gates, two distinct token fingerprints/results/revocations, exact ordinal
ordering, token canary absence, and denial of shared authorization material. No prefix repeats a completed phase, skips a receipt, invents a per-asset authority member, or
advances two phases in one run.

Correction dispatch is phase-exact and performs at most one missing effect or CAS per run. An
`intent_authorized|publication_recorded` prefix with an admitted exact merge persists
`CORRECTION_MERGE_RECORDED` once; `merge_recorded` performs/adopts only the preauthorized tag-target-
head effect and then persists `CORRECTION_TAG_RECORDED`; `tag_recorded` performs/adopts only the next
missing draft, asset, or publish effect. After publish it performs a distinct post-publish final-
verification subphase using `final_verification_effect_key`, emits `ReleaseEffectResultV1`, revokes
that token, and emits `FinalReleaseVerificationReceiptV1`; only after all five typed receipt groups
verify does it persist their aggregate as `CORRECTION_RELEASE_RECORDED`. `release_recorded` only verifies and installs
`finalization.json`, the receipt-derived next latest pointer, and `CORRECTION_RESULT_RELEASED` in one
expected-OID CAS. Every phase revalidates the immutable prior wrapper and exact authority OID; an
already accepted phase is adopted without a duplicate effect or CAS. A correction from `RELEASED` leaves state `RELEASED`; one from `RELEASE_BLOCKED`
moves state to `RELEASED`. A divergent release emits `RELEASE_PLAN_INVALIDATED`, which the broker
applies as `RELEASE_BLOCKED` only from
`RESULT_MERGED`; terminal correction failures append invalid correction evidence without rewriting
prior state or result objects. That event is exactly
`CORRECTION_INVALIDATED(kind=correction_release_invalidation)`; it is legal only after the active correction's verified
`merge-receipt.json`, requires `BlockedReleaseObjectsV1` and reconciliation receipts, and
terminalizes that correction ID without changing campaign state or advancing the latest pointer.
It is distinct from both
`CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=unmerged_invalid)` and
`CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=merged_invalid)`; none of these invalidations advances the pointer.

- [ ] **Step 4: Test failed and replayed finalization**

Add workflow fixture cases for failure before tag creation, tag created before runner loss, draft
created before asset upload, each partial asset state, both assets verified before publication,
publication before receipt CAS, finalization before event CAS, and exact rerun. Only byte-identical tags/drafts/assets or an
already published immutable release may recover. A divergent draft/published object, mutable-release
setting, incomplete accepted receipt/finalization chain, or failed
`ImmutableReleaseVerificationV1` emits
`RELEASE_PLAN_INVALIDATED` with exact `BlockedReleaseObjectsV1` and no result rewrite.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_result_release.py tests/test_ci_contract.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` enumerates exactly fourteen benchmark workflows.

- [ ] **Step 6: Commit the release workflow**

```bash
git add .github/workflows/benchmark-release.yml \
  tests/campaign/test_publication_workflows.py \
  tests/test_ci_contract.py
git commit -m "ci: gate checksum-bound benchmark releases"
```

### Task 13: Gate documentation and social changes on verified `RELEASED`

**Files:**
- Create: `src/laconian_eval/campaign/docs_gate.py`
- Create: `tools/validate_result_docs.py`
- Create: `.github/workflows/benchmark-docs-validate.yml`
- Create: `tests/campaign/test_docs_gate.py`
- Modify: `tests/campaign/test_publication_workflows.py`
- Modify: `tests/test_public_contract.py`
- Modify: `benchmarks/runbooks/public-benchmark.md`
- Modify: `CONTRIBUTING.md`
- Modify: `evals/README.md`
- Modify: `SECURITY.md`
- Modify: `tests/test_ci_contract.py`

- [ ] **Step 1: Write failing synchronized-surface tests**

Lock the surfaces to:

```python
SYNCHRONIZED_RESULT_PATHS = (
    "README.md",
    "README.ru.md",
    "README.el.md",
    "README.grc-x-laconian.md",
    "README.zh-CN.md",
    "README.it.md",
    "evals/README.md",
    "website/index.html",
    "CHANGELOG.md",
)
IMMUTABLE_ALPHA_PATHS = (
    "docs/releases/v0.1.0-alpha.1.md",
    "docs/social/alpha-launch.md",
    "assets/social/laconian-alpha.svg",
    "assets/social/laconian-alpha.png",
)
```

Require a new `docs/releases/benchmark-result-{publication_id}.md` and
`docs/social/{release_date}-{publication_id}.md`, plus the fixed presentation source
`docs/presentations/benchmark-result-{publication_id}.md`, where `release_date` is canonical
`YYYY-MM-DD` derived only from the accepted `PublishReceiptV1.published_at_utc` after UTC
normalization. On an initial lineage that receipt is reconstructed from the authoritative
`InitialPublishReceiptAppendV1` named by `InitialPublicationFinalizationV1`; on a correction it is
the exact publish receipt in the accepted `release-receipt.json` named by
`CorrectionFinalizationV1`,
and `publication_id` equals the campaign ID for an initial release or its exact
correction publication ID. All three are required changed paths in a post-release result-claims PR.
Every changed result block contains this exact marker grammar:

```html
<!-- laconian-result campaign="{campaign_id}" publication="{publication_id}" bundle="{bundle_sha256}" tag="benchmark-result-{publication_id}" -->
```

The brace-delimited values are reconstructed from the accepted terminal finalization, executable
release plan, and authoritative receipt chain; `bundle_sha256` must be exactly 64 lowercase
hexadecimal characters.

- [ ] **Step 2: Add failing state and claim-consistency tests**

Reject `RESULT_MERGED`, every `RELEASE_BLOCKED` state (even if correction-release evidence exists
without the required state transition), absent/wrong release receipt, missing localized surface,
changed alpha paths, model/date/campaign mismatch, denominator mismatch, interval mismatch, missing
quality gate or limitation link, reversed `concise - if` direction, billed/total/cost wording for
visible-output brevity, and numeric claims in hero/social-preview images.

Reject a benchmark-result marker or result-shaped numeric claim in any changed Markdown/HTML path
outside the enumerated synchronized/dynamic surfaces, and reject a presentation slide whose number,
model, interval, denominator, gate, direction, tag, bundle, or limitation differs from machine JSON.
All benchmark claim blocks, including qualitative/comparative statements with no number (for
example shorter, better, worse, passes, fails, or inconclusive when tied to a benchmark model/arm),
must be inside the exact marker-delimited bounded block. Reject such claims outside a block and add
positive/negative phrase fixtures in every supported surface.
Reject `INVALID_PREFIX_MERGED` and `INVALID_PREFIX_MERGED_INVALID` unconditionally: invalid-prefix
publication is a terminal registry/incident outcome and has no result release, correction, docs,
website, release-note, or social-promotion path. Also reject
`latest_status=withdrawn_due_to_credential_exposure`, an open credential incident, missing
containment/correction evidence, or a latest pointer that is not active, released, and nonwithdrawn.
Safe incident disclosure uses its separate reviewed path and cannot pass this result-claims gate.

The one pre-release carve-out is an exact result PR: changed paths wholly beneath the
`PublicationPlanV1.result_path` and exactly equal to its sealed `expected_files` are revalidated with
the same trusted-base `validate_publication_pull_request` logic. On success the docs validator emits
an explicit successful `sealed_result_bundle_noop`, even though canonical bundle files such as
`analysis/report.md`, `report.md`, or `limitations.md` contain result-shaped text. Any missing/extra/
changed member, path outside that bound result root, unbound result directory, or failed publication
validation is not carved out and fails. This prevents the always-present docs check from deadlocking
the publication PR without weakening arbitrary-path detection.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_docs_gate.py tests/test_ci_contract.py -q`

Expected: FAIL because `docs_gate.py` does not exist.

- [ ] **Step 4: Implement trusted-base documentation validation**

Add:

```python
PostReleaseClaimEvidenceV1 = VerifiedAnalysisEvidenceV1


def verify_post_release_docs(
    *,
    trusted_repository: Path,
    candidate_repository: Path,
    authority: ReconstructedAuthorityV1,
    executable_release_plan: ExecutableResultReleasePlanV1,
    finalization: InitialPublicationFinalizationV1 | CorrectionFinalizationV1,
    claim_evidence: PostReleaseClaimEvidenceV1,
) -> None: ...
```

Derive the changed-path inventory internally by opening the exact trusted and candidate Git trees,
enumerating their raw byte path/mode/object-ID tuples, and computing the canonical UTF-8-byte-sorted
diff. Never accept a changed-path list from a caller, event payload, CLI option, or environment.
Reject invalid UTF-8, aliases after path normalization, duplicate/missing/extra/reordered diff rows,
symlinks, submodules, and a candidate tree that does not equal the event's independently re-fetched
head. Tests prove that omitting a result-shaped path or substituting an event-supplied list cannot
select the no-op or sealed-result carve-out.

Unconditionally require `authority.state.state == "RELEASED"`, both authority roots null, and
`reconstruct_correction_progress(authority) is None`; an accepted defect or any in-flight correction
prefix blocks documentation/social validation even though the prior released pointer remains
reconstructable. For a
correction, also require the exact append-only correction publication, merge, and release receipts,
the canonical latest released pointer, and `require_correction_authority` as specified in Task 8.
A correction originating from `RELEASE_BLOCKED` is acceptable only after the authoritative
`CORRECTION_RESULT_RELEASED` transition. Require
`release_plan.bundle_kind == release_receipt.bundle_kind == "complete"`, an active nonwithdrawn
latest pointer, and exact bundle hashes. Verify receipt, committed bundle, correction lineage where
present, tag, `ImmutableReleaseVerificationV1`, and every analysis parent hash; parse only explicit
marker-bounded result sections; and compare every numeric or qualitative benchmark claim with the
machine summary. No null, fabricated, invalid-prefix, withdrawn, or incident-open analysis is
accepted. Require all six localized READMEs plus evaluation docs, site, changelog, release note,
presentation source, and dated social package to name the same campaign/publication/bundle/tag.

- [ ] **Step 5: Implement the PR workflow and runbook**

`benchmark-docs-validate.yml` runs the stable job `benchmark-docs-validate` on every `pull_request`,
without a top-level path filter; has read-only permissions; checks out base and
candidate separately; and executes trusted-base `tools/validate_result_docs.py`. It returns an
explicit successful no-op when none of the synchronized result, release, social, presentation, or
result-shaped Markdown/HTML paths changed, so the check is always present even though it is not the
base ruleset's required context.
Its job declares exactly `contents: read` and `pull-requests: read`.
At this final workflow checkpoint, make `tests/test_ci_contract.py` assert that its 15 exact workflow
paths equal Runtime's `WorkflowInventoryV1` production path constant, then build/reverify
the inventory from the trusted tree and require every full-SHA pin/policy hash. This is the deferred
real cross-slice check; Runtime Task 2 used only synthetic files at those fixed paths.

Do not add a public campaign CLI. The trusted workflow calls `tools/validate_result_docs.py`
directly with independently derived base/head repositories and event identity. Public-contract
tests retain exactly seven offline replay commands and reject live publication authority from those
handlers.

The runbook must contain the exact repository settings checklist below, operator commands for
complete and invalid publication, exact-head workflow approval, merge verification, release
approval, recovery/invalidation branches, artifact-expiry warning, and key-revocation/incident
steps. It must say that documentation/social work begins only after canonical
`CampaignStateV1.state == "RELEASED"`, the accepted `RESULT_RELEASED` or
`CORRECTION_RESULT_RELEASED` evidence, `ImmutableReleaseVerificationV1`, release receipt, and
latest-publication pointer all verify.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_docs_gate.py tests/campaign/test_publication_workflows.py tests/test_ci_contract.py tests/test_public_contract.py tests/test_site.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` enumerates the exact frozen 15-workflow inventory.

- [ ] **Step 7: Commit the post-release gate and operator documentation**

```bash
git add src/laconian_eval/campaign/docs_gate.py \
  tools/validate_result_docs.py \
  .github/workflows/benchmark-docs-validate.yml \
  tests/campaign/test_docs_gate.py \
  tests/campaign/test_publication_workflows.py \
  tests/test_public_contract.py \
  tests/test_ci_contract.py \
  benchmarks/runbooks/public-benchmark.md \
  CONTRIBUTING.md \
  evals/README.md \
  SECURITY.md
git commit -m "docs: gate benchmark claims on verified release"
```

### Task 14: Reconstruct the entire publication path offline

**Files:**
- Create: `tests/campaign/test_publication_reconstruction.py`
- Modify: `tests/campaign/publication_helpers.py`
- Modify: `tests/campaign/fake_github.py`

- [ ] **Step 1: Write the failing complete-lineage reconstruction**

First construct the exact serial protocol Git DAG, both annotated tags, stable ruleset policy,
operator registry, REST/GraphQL/local verification projections, historical tag-creation suites,
single companion binding, campaign registry, and complete object/API archive. Import it with the
network disabled and assert every Git OID/raw-object SHA-256, receipt digest, response-blob digest,
statement, envelope, bundle, ordered root and campaign identity reproduces. Negative fixtures cover
missing/extra/reordered closure objects, cycles, alternate tag grammar, wrong operator, namespace
squat, missing or differently authorized creation bypass, any update/delete bypass, duplicate rule
suite, response-hash/blob mismatch, omitted GraphQL signer state, and unknown CanonicalJSON fields.

Starting from 36 published-style synthetic generation capsules in `GENERATION_COMPLETE`, execute
the same handlers and fixed campaign-side stage tools as the workflows: `Runtime.hard_score`,
`Runtime.prepare_judge`, and `HARD_SCORE_SET_SEALED`; Slice 3 judge execution plus
`Runtime.seal_judge`
through `JUDGE_COMPLETE`; provider-evidence verification and `EVIDENCE_INVENTORY_SEALED`;
Publication `Publication.campaign.evaluation_stage.sample_audit` with no state jump; both
commitment/reveal chains and adjudication;
`Publication.campaign.evaluation_stage.seal_audit` plus `AUDIT_SEALED`;
`Publication.campaign.evaluation_stage.analyze` followed by exact `.verify`, then
`ANALYSIS_SEALED`; and complete collection. Assert a static trace contains no raw
`laconian-benchmark` execution. Continue through publication
planning, minimal publication into a local bare repository, trusted-base PR validation, a real
local merge, release planning, fake-GitHub tag/release finalization, and the post-release docs gate.
Assert every parent digest and every allowed state transition through `RELEASED`.
Expire every Actions artifact in a second reconstruction after `RESULT_MERGED`; require the merged
publication/release authority members and terminal finalization to replay identical authority solely
from protected Git objects, committed result bytes, annotated tag, immutable Release assets, and
canonical accepted receipts. Before the merge event, the same expiry remains fatal.

- [ ] **Step 2: Write the failing invalid-prefix reconstruction**

Start from `BUDGET_INCOMPLETE`, finalize the exact prefix, create and validate its publication PR,
and exercise both merge outcomes. Successful admission emits `INVALID_PREFIX_MERGED`; failed
admission emits `INVALID_PREFIX_MERGE_INVALIDATED` and
`INVALID_PREFIX_MERGED_INVALID`. Prove both are terminal and reject every release-plan, tag,
Release, asset, correction, docs, website, release-note, social, generation/judge/audit/analysis, or
performance-claim attempt.

- [ ] **Step 3: Add the exhaustive crash, outcome, and exposure matrix**

For initial publication and release, inject response loss immediately before and after intent CAS,
branch creation, branch-receipt CAS, PR creation, PR-receipt CAS, human merge observation,
merge-receipt CAS, release-intent CAS, tag creation and its non-state tag-receipt append CAS, draft
creation and its non-state draft-receipt append CAS, each asset upload followed by the one ordered
two-asset receipt append CAS, publish and its non-state publish-receipt append CAS, finalization, and
final event CAS. Each initial receipt append must use the exact
`initial_release_receipt_append` discriminator/path/schema, expected authority OID, and unchanged
CampaignState hash. Correction injection instead follows only the approved event wrappers:
publication-receipt CAS, merge-receipt CAS, tag effect then `CORRECTION_TAG_RECORDED`, each missing
draft/asset/publish effect, post-publish final-verification result/revocation/receipt, then aggregate
`CORRECTION_RELEASE_RECORDED`, and finalization/event CAS. Inject crashes before/after publish,
verification, token revocation, and wrapper CAS; replay never republishes or reuses a token.
Every retry must query exact names, create or adopt once, and either persist the matching allowed
receipt wrapper or record terminal conflict evidence; no test invents a CampaignState event.

For every initial/correction publication prefix and both ordinary and write-ambiguity source
classes, inject the same before/after loss at containment-start CAS, every queue inventory/timeline
page, guard create/update, exact dequeue, merge-fence run discovery/rerun/artifact redirect/page/
extraction, both main reads, disposition/finality construction, and terminal CAS. Assert the active
containment root blocks every unrelated transition, the selected merged candidate is never dropped,
the successor denylist is byte-preserved when the root clears, and a replay adopts the exact guard,
dequeue, fence, or terminal record without a second effect. For every generated publisher
containment broker read vector, reject ordinal gaps and ordinal reuse; inject an executor abort
before the first request and before every next pagination request, prove zero open/operation
dispatch on each abort, and require ordinal `n+1` to start only after ordinal `n` has a signed
terminal transport record. A later recovery must use a fresh attempt and may never skip, duplicate,
or reorder containment inventory requests.

For publisher, security-attestor, and release-finalizer credentials, inject loss before/after every
caller authorization, request dispatch, broker transport, safe success/failure projection, effect
dispatch, delivery resolution, token delete, unrecoverability/closure, audit-log append, ledger seal,
and reconciliation-only token close. Assert distinct operation keys/fingerprints, exact
request↔transport↔closure bijections, zero outstanding dispatch/live-token counters, denial of a
later mint, and recursive absence of token/PEM/canary bytes in every persisted or logged projection.
For both initial and correction release preparation, exercise a closed passing receipt separately
from every closed failure stage. A pass alone may construct the executable plan and then the
initial intent/effect authorization; a failure produces only its phase-exact invalidation and zero
executable plan, intent, or external effect. Include a minted-and-closed abort before the first GET,
an abort before each next GET, and prove request ordinal `n+1` can start only after ordinal `n` has a
signed terminal transport record; loss cannot skip, duplicate, or reorder the attestor inventory.

Cover all six post-merge broker exceptions, both complete and invalid initial outcomes, correction
success, all four correction publication outcomes (`unmerged_invalid`, `merged_invalid`,
`fenced_write_ambiguity`, `reconciliation_unavailable`), ordinary and
reconciliation-unavailable release invalidation, and successful recovery from every durable
correction prefix. Assert invalidation never advances the latest pointer and a
new correction after `merged_invalid` explicitly supersedes the failed correction and contaminated
merge. Include current main exactly `M`, a protected first-parent descendant with no result touch,
an intervening result touch, missing/bypass per-rule suite, double-read movement, and every
`PostMergeAdmissionFailureV1.failed_predicates` member across all five failure kinds. Exercise
`postmerge_security_result=not_run|pass|failure` with its exact subject/attestor nullability and
reject an attestor call after an earlier structural predicate made it unauthorized.

Exercise credential exposure before merge (pending CAS, every ordinal predecessor-bound effect
receipt, publisher-only close, terminal STOP, safe invalid prefix), after complete
merge before release (release blocked, no original tag/Release), and after `RELEASED` (historical
objects retained, latest withdrawn, containment recorded, superseding correction required). Assert
crashes after the pending CAS and every effect/external-response/receipt CAS adopt exact state,
simultaneous drift continues exposure from protected main without a drift-only STOP, exposure after
a sealed drift STOP uses the supplement flow, and no fixture or message claims historical erasure
or platform undeletability. Generate every hold-eligible state, dismissal, nondismissible STOP, and
postmerge hold consumer; assert each consumes the exact predecessor hold and every other edge is
blocked. Exercise moved/deleted tags, ruleset drift, fallback-member drift, temporary reads, and all
safe-invalid states under the protected-main liveness invariant.

- [ ] **Step 4: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_reconstruction.py -q`

Expected: FAIL until the fixture connects every Slice 4 interface and state event.

- [ ] **Step 5: Implement the minimal deterministic offline fixture**

Use no network, provider key, current time, random UUID, mutable branch lookup, or host-private path.
Freeze the raw bytes of every protocol closure object and safe API response/canonical projection,
repository ID and trust-boundary/settings records; the run, attempt, job, deployment,
approval, and artifact IDs for every hard-score/evidence/audit/analysis/collection/publication/release
stage; canonical timestamps; API JSON; Git author/tagger identity; deterministic USTAR bytes;
draft/upload/publish/immutable-release responses; and result assets in `publication_helpers.py`.
Make `fake_github.py` reject every endpoint outside Task 1's exact artifact/repository read
allowlist; Task 9/10's exact publisher branch/check/PR, terminal guard, queue/timeline GraphQL,
dequeue, rerun, compare/Git-object, check-suite/run, Actions-run/artifact pagination, validated 302,
and credential-free redirect-fetch endpoints; the three brokers' token mint/delete/denial-probe and
signed request/transport/closure lifecycle; and Task 11's enumerated immutable-setting, paginated
Release/asset read, annotated-tag, tag-ref, draft-Release, upload-host asset, and sole
draft-to-published endpoints. The fake external brokers, not the Actions-facing clients, own token
bytes and Authorization headers and expose only safe signed projections. It must model fully
paginated draft and asset listing, by-tag published
lookup, exact release-ID reads, immutable-Releases setting, rule-suite history, upload timeout/422/
502 reconciliation, absent provider digest requiring download/hash, `starter` assets, and pinned
`gh release verify` output.

- [ ] **Step 6: Run both reconstructions twice**

Run:

```bash
uv run pytest tests/campaign/test_publication_reconstruction.py -q
uv run pytest tests/campaign/test_publication_reconstruction.py -q
```

Expected: PASS twice with identical asserted bundle, publication-plan, proposed-head, release-plan,
tag object, merge receipt, accepted release append/phase receipts,
`ImmutableReleaseVerificationV1`, operation-set/no-later roots, terminal-finalization root, and
latest-pointer hash.

- [ ] **Step 7: Commit offline publication reconstruction**

```bash
git add tests/campaign/test_publication_reconstruction.py \
  tests/campaign/publication_helpers.py \
  tests/campaign/fake_github.py
git commit -m "test: reconstruct benchmark publication offline"
```

### Task 15: Lock live/offline stage separation and run repository verification

**Files:**
- Create: `tests/campaign/test_evaluation_stage.py`
- Create: `tests/campaign/evaluation_stage_contract.py`
- Modify: `tests/campaign/test_workflow_policy.py`

- [ ] **Step 1: Write the failing exact stage-ownership tests**

In `test_evaluation_stage.py`, import a test-only `collect_evaluation_stage_contract` helper and
assert the exact offline command tuple is `hard-score`, `prepare-judge`, `seal-judge`,
`sample-audit`, `seal-audit`, `analyze`, `verify`, with every handler owned under
`laconian_eval.replay`. Assert the exact live tuple is:

```text
laconian_eval.campaign.runtime.Runtime.hard_score
laconian_eval.campaign.runtime.Runtime.prepare_judge
laconian_eval.campaign.runtime.Runtime.seal_judge
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.sample_audit
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.seal_audit
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.analyze
laconian_eval.campaign.publication.Publication.campaign.evaluation_stage.verify
```

Pin the only live constructors as private `_reconstruct_verified_runtime` and
`_reconstruct_verified_publication`. AST/import/call-graph assertions reject a replay handler that
imports either campaign constructor/capability, a live method that imports replay code, any shared
writer/mutation entrypoint, any serialized capability, and every live workflow invocation of
`laconian-benchmark`. The public console target remains `laconian_eval.cli:main` and routes only to
`laconian_eval.replay`.

Extend `test_workflow_policy.py` with a whole-workflow zero-state-secret scan. Assert no workflow
contains an App/installation ID credential expression or secret mapping, private-key secret
expression, installation token, App-auth Authorization header, or opaque token handle for the state-writer,
publisher, or release-finalizer roles. Each broker-calling job has `id-token: write` only at the
exact job scope and receives only signed safe receipts; those receipts may include the
preregistered nonsecret App identity. Security-attestor and state-broker jobs contain only their
fixed OIDC bootstrap and secret-free broker client. A publisher or release-finalizer package job
may additionally contain only the exact bounded numeric artifact downloader and its transient
repository `GITHUB_READ_TOKEN` path: the token authenticates only the allowlisted numeric metadata/
archive request and is stripped before a validated redirect fetch or any broker call. No other
repository-read helper, credential propagation, or package discovery is allowed.
Assert exactly
three pairwise-distinct App identities in the sealed registry, all keys/tokens confined to their
external measured brokers, and `security_attestor` reuses only the release-finalizer installation
through a distinct broker role and exact `administration:write`, `contents:read`, `metadata:read`
GET-only policy. Reject a repository-token substitute, local App key/token mapping, release write in
the attestor, or mutation endpoint.

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```bash
uv run pytest tests/campaign/test_evaluation_stage.py tests/campaign/test_workflow_policy.py -q
```

Expected: FAIL during collection because `tests/campaign/evaluation_stage_contract.py` does not yet
exist.

- [ ] **Step 3: Implement the minimal test-owned contract collector**

Create `evaluation_stage_contract.py` with deterministic AST traversal, console-script parsing, and
YAML scalar/path extraction. It accepts an explicit repository root, byte-sorts paths, follows no
symlink, executes/imports no candidate module, and returns only canonical tuples of module/function/
workflow references. It contains no production adapter, compatibility alias, campaign constructor,
or writer. Add the exact zero-secret/path assertions to `test_workflow_policy.py`.

If these new tests expose a production mismatch, return to Task 7, 10, or 12 and fix that owning
implementation before continuing; do not weaken the collector or add a live/public alias.

- [ ] **Step 4: Run focused GREEN and all Slice 4 tests**

```bash
uv run pytest tests/campaign/test_evaluation_stage.py tests/campaign/test_workflow_policy.py -q
uv run pytest \
  tests/campaign/test_github_records.py \
  tests/campaign/test_artifacts.py \
  tests/campaign/test_provider_evidence.py \
  tests/campaign/test_public_projection.py \
  tests/campaign/test_complete_collector.py \
  tests/campaign/test_invalid_prefix_finalizer.py \
  tests/campaign/test_publication_capability.py \
  tests/campaign/test_evaluation_stage.py \
  tests/campaign/test_publication_plan.py \
  tests/campaign/test_publication_delivery_resolution.py \
  tests/campaign/test_publication_terminal_containment.py \
  tests/campaign/test_publication_merge_queue.py \
  tests/campaign/test_publication_merge_fence.py \
  tests/campaign/test_publication_terminal_records.py \
  tests/campaign/test_publisher_credential_finality.py \
  tests/campaign/test_security_attestor_credential_finality.py \
  tests/campaign/test_release_authorization_graph.py \
  tests/campaign/test_release_finalizer_credential_finality.py \
  tests/campaign/test_reconciliation_unavailable.py \
  tests/campaign/test_minimal_publisher.py \
  tests/campaign/test_publication_pr.py \
  tests/campaign/test_audit_pr.py \
  tests/campaign/test_result_release.py \
  tests/campaign/test_docs_gate.py \
  tests/campaign/test_publication_workflows.py \
  tests/campaign/test_workflow_policy.py \
  tests/campaign/test_publication_reconstruction.py -q
```

Expected: PASS.

- [ ] **Step 5: Run workflow/public contracts and repository quality gates**

```bash
uv run pytest tests/test_ci_contract.py tests/test_public_contract.py tests/test_site.py tests/test_release_bundle.py -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
git diff --check
```

Expected: every command exits 0; the workflow inventory is exactly 15 members and `git diff
--check` prints nothing. The test-owned scanner proves no state App credential reaches Actions, no
live workflow invokes a replay command, and every App key/token remains confined to its measured
external broker behind the exact OIDC-only boundary.

- [ ] **Step 6: Commit the cross-slice contract tests**

```bash
git add tests/campaign/test_evaluation_stage.py \
  tests/campaign/evaluation_stage_contract.py \
  tests/campaign/test_workflow_policy.py
git commit -m "test: lock benchmark live stage ownership"
```

Do not create a catch-all verification commit and never use `git add .`; any production correction
must use its owning task's exact files, focused GREEN command, and commit.

---

## Repository settings prerequisite checklist

These are maintainer actions outside the implementation commits. Inspect and record them in the
rollout evidence; do not mutate GitHub while executing this plan.

- [ ] Keep repository default `GITHUB_TOKEN` permission at `read`.
- [ ] Enable repository enforcement that every action is pinned to a full-length commit SHA.
- [ ] Configure `benchmark-live` with required reviewer approval, prevent self-review, disable
  administrator bypass, restrict deployments to `benchmark-input-*` tags, and retain only the
  dedicated restricted `OPENAI_API_KEY` environment secret.
- [ ] Create `benchmark-publish` with required reviewer approval, prevent self-review, disable
  administrator bypass, restrict deployments to protected `main`, and configure no provider
  secret.
- [ ] Register three distinct GitHub Apps installed only on this repository and record their numeric
  App/installation IDs, exact slugs/bot logins, repository ID, permission response, permissions-
  attestation hash, creation owner, rotation owner, and private-key fingerprint. Require pairwise
  distinct IDs/installations/bot logins/private keys:
  - state writer, held only by the external OIDC broker: metadata read plus `contents: write`; no actions/deployments/PR/checks permission.
    Because `contents:write` also makes Git reference and release endpoints technically reachable,
    its fixed hashed tool may call only expected-OID CAS on `benchmark-authority/*`; result-tag rules,
    immutable Releases, endpoint-policy tests, and before/after inventories detect any other use;
  - publisher: the installation grant ceiling is Actions write, Checks write, Contents write, Merge
    queues write, Metadata read, and Pull requests write. This is only the union needed to mint the
    exact per-operation read/write rows; a token containing the union is forbidden. Each external
    broker mint is downscoped to one literal §7.4 row, and its fixed tool never calls review/merge or
    release endpoints outside that row. Result-tag rules and immutable Releases bound the release
    surface, the result validator accepts only a preregistered non-bot maintainer review, and the
    `main` ruleset excludes the App from merge;
  - release finalizer: the installation grant ceiling is Administration write, Contents write, and
    Metadata read; no Actions, Deployments, Pull requests, Checks, or Reviews grant. Every
    release-effect token omits Administration and has only the exact applicable
    `contents:write`, `metadata:read` row; reconciliation has only `contents:read`, `metadata:read`.
    The separately brokered `security_attestor` token has the exact ordered permissions
    `administration:write`, `contents:read`, `metadata:read`. Its fixed policy uses GitHub's
    write-named Administration permission only for GET-only ruleset/immutable-settings observations
    and grants no mutation endpoint.
- [ ] Configure the fixed `security_attestor` jobs in `.github/workflows/benchmark-publish.yml` and
  `.github/workflows/benchmark-release.yml` to request respectively only the
  `postmerge_rule_suite` and `release_preparation` caller rows from the external security-attestor
  broker. That broker reuses the release-finalizer App installation but has its own measured vault
  role/signing key; each job receives only signed safe pass/failure evidence and is not a fourth App.
  No repository-token substitute, App ID/key credential input or secret mapping, installation token,
  contents/release write token, App-auth Authorization header, opaque handle, or mutation endpoint
  may reach either job; the safe receipt may carry only the preregistered nonsecret App identity.
- [ ] Configure the external state, publisher, release-finalizer, and security-attestor brokers'
  exact repository/caller/OIDC policies and keep all three App private keys only in their measured
  broker vaults. Create no App identity/key/token/handle Actions secret at repository, organization,
  or environment scope and return no installation token to a runner. `benchmark-publish` stores no
  `PUBLISHER_*` or `RELEASE_*` triple; its jobs authenticate to brokers only by OIDC. Do not create
  `benchmark-state` or `benchmark-release` environments. Rotate any key exposed outside its intended
  scope and update the attestation before dispatch.
- [ ] Commit and verify the strict one-entry `TagOperatorRegistryV1` at its C0 path, including the
  exact operator numeric ID/login and canonical tagger identity bound by T0, T1, the companion tag
  binding, campaign registry, and ordered security-evidence subjects.
- [ ] Create exactly two active disjoint protocol-tag rulesets over the exact T0/T1 patterns: the
  creation-authorizer contains only `creation` and the frozen operator as its sole `User`/`always`
  bypass actor; the immutability ruleset contains only `update` and `deletion` with an empty bypass
  actor list. Reject every extra applicable/evaluate/disabled ruleset, rule, actor, role, team, App,
  deploy key, exemption, pattern overlap, or ID collision. Capture unique historical creation suites
  for both tags with raw top-level `result="bypass"` mapped to stable
  `overall_result="bypass"`, stable `evaluation_result="fail"`, and per-rule `result="fail"`; archive
  their safe response blobs.
- [ ] Create exactly two active result-tag rulesets over the same exact
  `refs/tags/benchmark-result-*` pattern. The creation-authorizer contains only `creation` and has
  the exact release-finalizer App installation as its sole `App`/`always` bypass actor. The
  immutability ruleset contains only `update` and `deletion` and has an empty bypass list. Their
  numeric IDs are distinct; no rule or bypass actor crosses between them, and no third applicable,
  evaluate, or disabled ruleset exists. The publisher/state Apps, roles, teams, users, deploy keys,
  and repository admins are not policy bypass actors. Tests prove GitHub bypass applies to the
  entire containing ruleset, so combining creation with update/delete is rejected, along with ID,
  pattern, target, enforcement, rule, or actor overlap/substitution.
- [ ] Enable GitHub immutable releases for the repository and capture the safe setting/API digest.
  Require the release-finalizer App to create only a new draft, upload the two plan-bound assets, and
  perform its one draft-to-published transition; after publication, neither that App nor any other
  benchmark workflow identity is authorized to edit/delete the release or its assets. Re-fetch the
  returned Release `immutable` field and bind `ImmutableReleaseVerificationV1` over the setting,
  Release fields, and pinned `gh release verify` output before `RESULT_RELEASED`. Do not claim the
  feature makes deletion or every metadata mutation impossible.
- [ ] Protect `benchmark-authority/*` from deletion, force-push, and human updates; permit only the
  exact state-writer App installation to create or non-force fast-forward a ref after expected-OID
  verification. Publisher/release Apps and Actions tokens cannot bypass it.
- [ ] Keep the repository-global **Allow GitHub Actions to create and approve pull requests** setting
  disabled. Publisher-App authentication creates/closes the exact PR independently. Its
  `pull_requests:write` token is API-capable of requesting a merge, so do not claim capability
  absence: workflow/tool policy forbids that endpoint and the `main` ruleset makes every benchmark
  App/Actions identity ineligible to merge.
- [ ] Create a result-branch ruleset matching `refs/heads/benchmark-result-pr/*`; permit only the
  exact publisher App to create refs in that namespace. The fixed publisher tool and validator—not
  the ruleset's static ref pattern—require the full name to equal the plan derivation
  `benchmark-result-pr/{publication_id}-a{publication_attempt}-{base_sha[:12]}-{bundle_sha256[:12]}`;
  forbid force-push,
  deletion, reuse, and updates after its initial push. State/release Apps, Actions, and humans have no
  bypass. Do not grant the publisher App `main` bypass.
- [ ] Add only the exact `laconian/publication-pr-validate` context to the protected `main` required
  checks after its first recognized run, including `merge_group: checks_requested`. This is the sole
  required check in `PublicationBranchRulesetPolicyV1`; preregister its GitHub Actions source App ID,
  workflow path, and trusted workflow hash. Its one required-check member has exactly
  `context="laconian/publication-pr-validate"`, `source_kind="Integration"`, that positive
  `source_app_id`, `strict=true`, and `do_not_enforce_on_create=true`; reject a same-name context or
  any substituted member field from another source.
  `audit-pr-validate` and `benchmark-docs-validate` still run on every PR without path filters and
  return explicit success when irrelevant, but they are not added to this exact ruleset policy.
- [ ] Enable the merge queue and freeze `PublicationBranchRulesetPolicyV1` with
  `merge_queue_required=true`, method `MERGE`, grouping strategy `ALLGREEN`, minimum entries `1`,
  wait time `0`, maximum entries `1`, and build concurrency `1`, plus positive
  `merge_queue_check_response_timeout_seconds` exactly equal to `60 *` the observed GitHub
  `check_response_timeout_minutes`. Direct/squash/rebase merge is forbidden. Capture the raw settings response and canonical
  policy digest, then prove the `merge_group` check and one-entry queue/timeline evidence reproduce
  those values before any admission receipt.
- [ ] On `main`, require one active repository-owned, non-inherited ruleset with
  `allowed_ruleset_source_type="Repository"` and `enforcement="active"`; keep one required human PR
  approval, `dismiss_stale_reviews=true`, `require_last_push_approval=true`, required conversation
  resolution, enforced administrators, force-push/deletion prohibition, and a
  restrict-updates/merge-actors rule allowing only the preregistered non-bot maintainer team.
  Explicitly exclude all three benchmark Apps, GitHub Actions, and other bots from merge
  eligibility; record the numeric maintainer IDs used by `PublicationMergeReceiptV1`.
- [ ] Set every benchmark Actions artifact to the repository maximum retention of 90 days and finish
  every pre-merge lineage before any required artifact expires. At `RESULT_MERGED`, require the
  accepted merge receipt and exact protected result tree; after that, expiry substitution is allowed
  only through canonical authority mappings and those protected Git bytes and, after release, the
  accepted append/finalization chain plus immutable tag/Release/assets.
- [ ] Verify the OpenAI key is project-scoped and restricted, the provider project has no unrelated
  consumers, the project spend guard is set, and rotation/revocation ownership is recorded.
- [ ] Record environment approval actors through
  `/repos/{owner}/{repo}/actions/runs/{run_id}/approvals`, numeric jobs through the run-attempt jobs
  endpoint, and deployment identity through deployment statuses whose target URL binds the exact
  run/job pair.
- [ ] Before each protected approval, compare the committed price snapshot with its frozen official
  source URLs and record the reviewer attestation; do not approve if the rates cannot be verified.
- [ ] Before approving the publication PR workflow, verify the exact PR head SHA and sealed bundle
  digest before approving the `benchmark-publish` environment deployment. After the App-authored PR
  opens, verify the same head/bundle, submit the required human review, and only after the exact
  required check succeeds enqueue that PR into the one-entry `MERGE` queue. Observe the merge only
  through authenticated merge-group/queue evidence; never direct/squash/rebase merge. There is no
  fork-workflow approval step.
- [ ] Before release approval, verify the exact merged tree,
  `InitialPreauthorizedResultReleasePlanV1 | CorrectionReleaseIntentPlanV1`, derived
  `ExecutableResultReleasePlanV1`, tag name, both asset digests, deterministic tag-object ID,
  draft-to-published plan, immutable-release setting, and accepted publication-merge authority.
- [ ] Produce `RepositoryTrustBoundaryAttestationV1` plus its detached registered-reviewer signature
  from the exact settings above. Bind repository/environment/ruleset IDs and safe API digests, App
  identities/permissions, default read token, disabled global PR toggle, immutable releases,
  required-check source provenance, retention, and capture actor/time. Re-fetch all readable records
  and require a fresh signed admin-only settings observation before each pilot/confirmatory preflight;
  commit only nonsecret projections, never tokens, PEMs, key values, or raw admin payloads.
- [ ] After `RELEASED`, revoke or rotate the benchmark key and record the safe result without storing
  the key or provider dashboard secrets.

## Completion criteria

Slice 4 is complete only when all Task 15 commands are fresh and green, the offline complete and
invalid-prefix lineages reconstruct twice with identical hashes, the network-free importer
reconstructs every raw object in `T0 -> C0 -> Rstat -> Rjudge -> Rsecurity -> B0 <- T1` and every
receipt/blob digest, and a maintainer has reviewed the
repository-settings checklist without changing GitHub as part of implementation. No live provider
call, publication PR, result tag, GitHub Release, README result block, website result, release note,
or social package is created by executing this plan.
Acceptance additionally requires one unchanged Evaluation-owned
`audit_protocol_sha256: Sha256` across the verified Runtime registry, evidence inventory, aggregate
audit and analysis loaders, complete/invalid bundle lineage, `Publication` capability,
`PublicationPlanV1`, both preauthorized release-plan variants, and
`ExecutableResultReleasePlanV1`. Every consumer must prove the value came from
Runtime Task 2's verified peeled-C0
`benchmarks/protocols/public-three-model-v1/audit.json` bytes; no Publication schema owns or aliases
the contract, and the exact `VerifiedProtocolAttestationV1` role-subject inventories remain
unchanged. Acceptance also requires the approved normative SHA and governance successor above,
strict CanonicalJSONV1 rejection vectors, the generated wildcard-free state/caller/effect matrix,
both authority roots null at every ordinary publication/release/correction/docs/social boundary,
and crash/replay tests for pending exposure, effect adoption, hold consumption, drift fallback, and
open-publication-PR close ordering.
