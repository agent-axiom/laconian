# Public Benchmark Publication Slice 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the secret-free, fail-closed publication half of the public three-model benchmark: exact GitHub artifact provenance, provider-evidence inventory sealing, complete and invalid-prefix collection, minimal reviewed publication, checksum-bound result release, and post-`RELEASED` documentation validation.

**Architecture:** Slice 4 consumes immutable campaign authority from Slice 3, sealed generation/hard-score/judge evidence, and the neutral audit/analysis APIs from Slice 2. A non-public `Publication` capability reconstructs current authority in memory and owns the four live Evaluation stages; the seven public replay commands remain offline and non-evidentiary. Repository-owned Python retrieves artifacts only by exact numeric identity, verifies every parent hash, projects one of two disjoint public bundle kinds, and creates deterministic publication and release plans. Repository `GITHUB_TOKEN` permissions remain read-only everywhere. Exactly three pairwise-distinct GitHub Apps carry writes: the external OIDC state broker alone holds the state-writer App and performs expected-OID receive-pack CAS on `benchmark-authority/*`; the publisher App creates/adopts one intent-bound result branch/PR or closes that exact invalidated PR; and the release-finalizer App creates/adopts one intent-bound protected annotated result tag, draft Release, assets, and publish transition. A separately downscoped `security_attestor` job receives only a short-lived broker-minted token from the existing release-finalizer App installation, downscoped to `administration:read`, `metadata:read`, and `contents:read`; it is not a fourth App, and no App private key or write-scoped token reaches that job. No state-writer App ID, installation ID, private key, or installation token exists in Actions secrets or reaches a runner. Publisher and release-finalizer credentials are mapped only in separately approved jobs in the existing `benchmark-publish` environment. No App receives the provider key or interprets model output.

**Tech Stack:** Python 3.11+, Pydantic v2 strict models, standard-library `hashlib`, `json`, `tarfile`, `urllib`, `zipfile`, Git plumbing, pytest, deterministic property loops, uv, and GitHub Actions pinned to full commit SHAs.

**Approved design:** [Public Three-Model Benchmark Pipeline Design](../specs/2026-08-30-public-three-model-benchmark-design.md), normative design commit `46147ef62b5bb009421d58928e879d92247d84b5`, especially sections 7.4–7.7, 12, 13, 14, and 16.

**Approval record:** Amendment approval metadata is committed at
`0e2981e32b5d8982e78c73a5e413b36e2b1495e9`. Milestone 0 is complete, the amendment is approved,
and Publication is unblocked. The older or implicit contracts are not fallbacks; all experiment,
authority, publication, and evidence invariants in the approved design remain normative.
Any future normative amendment re-blocks every affected Publication task until that amendment is
separately reviewed, recorded, and explicitly approved.

---

## Slice boundary and prerequisite contract

Do not begin this slice until the following imports and focused suites are green. Slice 4 does not
reimplement campaign state, provider execution, spend accounting, scoring, inference, sampling, or
statistical estimators; it composes their neutral APIs under campaign authority.

Required Slice 3 interfaces:

```python
from laconian_eval.campaign.authority import (
    DurableAuthorityCheckpointV1,
    ReconstructedAuthorityV1,
    require_no_unresolved_hold,
)
from laconian_eval.campaign.artifact_wire import ArtifactEnvelopeV1, UploadAuthorizationV1
from laconian_eval.campaign.runtime import Runtime
from laconian_eval.campaign.preflight import CampaignRegistryV1
from laconian_eval.campaign.spend import SpendLedgerV1
from laconian_eval.campaign.state import CampaignEventV1, CampaignStateV1, InvalidEventHoldV1
from laconian_eval.campaign.models import GitHubAppInstallationIdentityV1
from laconian_eval.campaign.publication import Publication
```

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
    CorrectionLineageV1,
    LatestPublicationPointerV1,
    Publication,
    PublicationPlanV1,
    PublicationMergeReceiptV1,
    PublicationReceiptV1,
    build_correction_publication_plan,
    build_publication_plan,
    validate_publication_pull_request,
)
from laconian_eval.campaign.release import (
    ResultReleasePlanV1,
    ResultReleaseReceiptV1,
    build_correction_release_plan,
    build_result_release_plan,
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

`COMPLETE_PUBLICATION_PR_OPEN` and `INVALID_PUBLICATION_PR_OPEN` are distinct schema values; an
untyped publication-open alias, cross-kind open/close/merge events, and missing bundle
discriminators are rejected. `INVALID_PREFIX_MERGED` and `INVALID_PREFIX_MERGED_INVALID` are terminal and accept no
release, correction, documentation, website, release-note, or social-promotion event.

## File map

### Create

- `src/laconian_eval/campaign/github_records.py`: strict GitHub repository, workflow-run,
  run-attempt, job, deployment, approval, artifact, and exact-locator records; it imports the Runtime-
  owned `ArtifactEnvelopeV1` wire type rather than redefining it.
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
  construction, byte-copy publication records, and PR/admission validators.
- `src/laconian_eval/campaign/release.py`: `ResultReleasePlanV1`, release assets, idempotent protected
  tag/release finalizer, and receipts.
- `src/laconian_eval/campaign/docs_gate.py`: post-`RELEASED` synchronized documentation/social
  provenance validation.
- `tools/benchmark_minimal_publisher.py`: standard-library-only publisher executable used by the
  write-capable job.
- `tools/benchmark_release_finalizer.py`: standard-library-only result-tag/release executable.
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
audit/commitments/{reviewer_id}.json
audit/reveals/{reviewer_id}/reveal.json
audit/reveals/{reviewer_id}/labels.jsonl
audit/adjudication-core.json
audit/adjudication.json
audit/signoffs/{reviewer_id}.json
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
records, validated as single safe path components, and sorted by UTF-8 bytes. Braces in this plan
denote validated grammar variables, never an implementation instruction to invent a path.

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
- Create: `src/laconian_eval/campaign/artifacts.py`
- Create: `tests/campaign/fake_github.py`
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

- [ ] **Step 3: Implement a GET-only GitHub client**

`GitHubReadClient` may issue only these requests:

```text
GET /repos/{owner}/{repo}
GET /repos/{owner}/{repo}/actions/runs/{run_id}
GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs
GET /repos/{owner}/{repo}/actions/runs/{run_id}/approvals
GET /repos/{owner}/{repo}/deployments
GET /repos/{owner}/{repo}/deployments/{deployment_id}/statuses
GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}
GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip
```

Set `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, a fixed user agent,
and a 30-second timeout. Limit JSON bodies to 8 MiB, follow at most one HTTPS redirect for the ZIP,
strip authorization on redirect, and stream to an exclusively created file while hashing and
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
  tests/campaign/fake_github.py \
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
unreconciled reservation, superseded attempt, and unresolved hold. Also pass an audit or analysis
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
`require_no_unresolved_hold(authority)`, and exact-compares the verified object's complete
generation expectation, predecessor authority root, bound final authority root, context digest,
provider-index digest, and workflow root with the retained authority events. It reuses only the
verified object's scored capsules and
strict attachments, and joins only on exact parent hashes and planned request IDs,
verifies the ledger and returned-model consistency separately per generation model,
and derives the provenance root from the ordered exact locators. It opens every input read-only and
creates no output itself.

Re-hash the tagged `src/laconian_eval/benchmark/hard_score.py` source plus the exact hard-score and
statistics protocol members from verified `C0`; require their path/hash pairs, the frozen
workflow-inventory root, and the authority-bound generation-context digest to equal
`CampaignRegistryV1`, the neutral context, every hard-score request set, and
`VerifiedBenchmarkProviderEvidenceV1`. A self-consistent
substituted context/index or a hash copied from any non-C0 or mutable-`main` commit fails.

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
    campaign_id: str,
    kind: Literal["complete", "invalid_prefix"],
    source_state_sha256: str,
    source_artifact_root_sha256: str,
    known_secret_values: tuple[str, ...] = (),
) -> BundleSealV1:
```

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
- Create: `tests/campaign/test_complete_collector.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

- [ ] **Step 1: Write the failing exact-tree collection test**

Use the canonical complete tree from this plan. Assert byte identity for copied raw and derived
layers, 36 generation tar/sidecar pairs, 36 hard-score attachments, 36 judge-request attachments,
36 judge attachments, both commitments, both reveals, adjudication core/envelope, both standalone
signoffs, their exact canonical GitHub review records, analysis outputs, report, limitations,
reproduction instructions, checksum manifest, and `bundle.json`.
Require `provenance/reviewer-attestations.jsonl` to be the byte-identical tagged three-line
`ProtocolReviewAttestationV1` file accepted by preflight, with all three hashes and their ordered
root reproduced from
`CampaignRegistryV1`; it is not synthesized from informal review notes during collection.
Likewise require the byte-identical tagged `RepositoryTrustBoundaryAttestationV1` and detached
signature accepted by preflight. Recompute their digests/settings-record root and verify the
registered security-evidence signer; collection never turns the repository-settings checklist into
a substitute attestation.
Require `provenance/workflows.jsonl` to be the canonical path/hash projection from the registry's
exact 15-member `BenchmarkWorkflowInventoryV1`; recompute its root from committed `C0` bytes and
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
`require_no_unresolved_hold(authority)`, and require exact
evidence/audit/analysis parent hashes, the full audit merge set, and exact current inventory. Obtain
the aggregate inputs only through `load_verified_audit_evidence` and
`load_verified_analysis_evidence`; copy from already verified descriptors into an
owned `0700` stage, never parse model text while rendering reports, verify the finished projection,
fsync, atomically publish, then reverify through a fresh descriptor.

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

Run the command documented in `REPRODUCE.md` from only a copied public tree. It must independently
recompute the campaign seed/plan index, all seven protocol hashes (including hard-score, retry,
checkpoint, and publication), 36 generation/hard-score/judge-request/judge roots, audit population
and sample, analysis seal, checksum manifest, and bundle digest without GitHub APIs or private
artifacts.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_complete_collector.py tests/campaign/test_public_projection.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the complete collector**

```bash
git add src/laconian_eval/campaign/collector.py \
  src/laconian_eval/campaign/__init__.py \
  tests/campaign/test_complete_collector.py
git commit -m "feat: collect complete publication benchmark evidence"
```

### Task 6: Build the disjoint invalid-prefix finalizer

**Files:**
- Modify: `src/laconian_eval/campaign/collector.py`
- Create: `tests/campaign/test_invalid_prefix_finalizer.py`
- Modify: `src/laconian_eval/campaign/__init__.py`

- [ ] **Step 1: Write the failing STOP and budget-prefix tests**

Create one `STOPPED_INVALID` state with a safe incident and one `BUDGET_INCOMPLETE` state. Assert
the exact invalid-prefix tree, ordered completed prefix, exact expected missing suffix, last valid
spend ledger, and absence of all performance layers.

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

Assert rejection from `ANALYSIS_COMPLETE`, any unresolved hold, a phase-plan hash different from the
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

The function accepts only `STOPPED_INVALID` or `BUDGET_INCOMPLETE`, calls
`require_no_unresolved_hold(authority)`, verifies `SpendLedgerV1` against the authority hash, and
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

- [ ] **Step 5: Run both collector suites and verify separation**

Run: `uv run pytest tests/campaign/test_complete_collector.py tests/campaign/test_invalid_prefix_finalizer.py -q`

Expected: PASS.

- [ ] **Step 6: Commit invalid-prefix finalization**

```bash
git add src/laconian_eval/campaign/collector.py \
  src/laconian_eval/campaign/__init__.py \
  tests/campaign/test_invalid_prefix_finalizer.py
git commit -m "feat: finalize invalid benchmark prefixes safely"
```

### Task 7: Add the `Publication` capability and secret-free evidence workflows

**Files:**
- Create: `src/laconian_eval/campaign/publication.py`
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
identity registries, `protocol_attestations_root`, hard-score/judge/statistical/audit protocol
hashes, provider-projection root, and common `workflow_root`. The provider index is evidence only;
it carries the expectation digest and repeated bindings but never a nested alleged expectation or
capability.

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

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_audit_pr.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py -q`

Expected: FAIL because the seven workflows, fixed tools, and new reusable-workflow caller rows are
absent.

- [ ] **Step 6: Implement the seven workflows and audit validator**

`benchmark-hard-score.yml` calls only `Runtime.hard_score` then `Runtime.prepare_judge` and accepts
only `GENERATION_COMPLETE`; the existing judge runtime calls only `Runtime.seal_judge`.
`benchmark-evidence.yml` accepts only `JUDGE_COMPLETE` and seals the exact provider-evidence
inventory. `benchmark-audit.yml` calls only Publication `sample_audit` and `seal_audit`, then emits
`AUDIT_SEALED`. `benchmark-analysis.yml` calls only Publication `analyze` and `verify`, then emits
`ANALYSIS_SEALED`. `benchmark-collect-complete.yml` accepts only `ANALYSIS_COMPLETE` and emits
`COMPLETE_BUNDLE_SEALED`. `benchmark-finalize-invalid.yml` accepts only `STOPPED_INVALID` or
`BUDGET_INCOMPLETE` and emits `INVALID_PREFIX_SEALED`. Every event is packaged as canonical broker
input against an exact expected authority OID; stale OID or unresolved hold fails before upload or
side effect.

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

Run: `uv run pytest tests/campaign/test_publication_capability.py tests/campaign/test_publication_workflows.py tests/campaign/test_audit_pr.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py tests/test_public_contract.py -q`

Expected: PASS; `tests/test_ci_contract.py` enumerates exactly eleven frozen workflows.

- [ ] **Step 8: Commit the capability and evidence workflows**

```bash
git add src/laconian_eval/campaign/publication.py \
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
- Modify: `src/laconian_eval/campaign/collector.py`
- Modify: `src/laconian_eval/campaign/public_projection.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write the failing complete and invalid plan round-trip tests**

Use a local bare Git repository with `main`, the input commit, two commitment merges, two reveal
merges, one adjudication merge, and no result path. Build complete and invalid-prefix plans and
assert deterministic proposed tree and commit IDs.

Use this model exactly:

```python
class CorrectionDefectRecordV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    correction_sequence: StrictPositiveInt
    affected_pointer_sha256: Sha256
    affected_publication_id: BoundedNonBlankString
    defect_class: Literal["publication_metadata", "release_metadata", "credential_exposure"]
    defect_code: Literal[
        "publication_object_metadata_diverged",
        "release_object_metadata_diverged",
        "release_finalization_interrupted",
        "post_merge_credential_exposure",
    ]
    evidence_sha256: Sha256
    record_sha256: Sha256


class BlockedReleaseObjectsV1(CapsuleModel):
    schema_version: Literal["1"]
    failure_phase: Literal[
        "pre_tag", "tag_created", "draft_created", "assets_partial", "assets_complete",
        "publish_unverified", "published_divergent"
    ]
    planned_tag_name: BoundedNonBlankString
    observed_tag_object_sha: GitObjectId | None
    observed_release_id: StrictPositiveInt | None
    observed_release_is_draft: bool | None
    observed_asset_root_sha256: Sha256 | None
    immutable_release_verification_sha256: Sha256 | None
    evidence_sha256: Sha256


class LatestPublicationPointerV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    correction_sequence: StrictNonNegativeInt
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
    blocked_release_objects: BlockedReleaseObjectsV1 | None
    pointer_sha256: Sha256


class CorrectionProgressV1(CapsuleModel):
    schema_version: Literal["1"]
    correction_sequence: StrictPositiveInt
    base_pointer_sha256: Sha256
    defect_record_sha256: Sha256
    phase: Literal[
        "intent_authorized", "publication_recorded", "merge_recorded",
        "tag_recorded", "release_recorded",
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
    correction_sequence: StrictPositiveInt
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
    supersedes_blocked_release_objects: BlockedReleaseObjectsV1 | None
    lineage_sha256: Sha256


class PublicationPlanV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    publication_attempt: StrictPositiveInt
    correction_lineage: CorrectionLineageV1 | None
    bundle_kind: Literal["complete", "invalid_prefix"]
    bundle_sha256: Sha256
    bundle_artifact: ExactArtifactLocatorV1
    input_tag_object_sha: GitObjectId
    input_commit_sha: GitObjectId
    authority_state_sha256: Sha256
    unresolved_hold_root_sha256: Sha256
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
`benchmarks/results/{campaign_id}`. For correction sequence `N`, `publication_id` is exactly
`{campaign_id}-correction-{N}`, the branch/result path use that new publication ID, and every
superseded field is required. `correction_sequence` must equal the canonical
`LatestPublicationPointerV1.correction_sequence + 1`, and every copied supersedes field must equal
that pointer, including `supersedes_bundle_kind` and blocked-object evidence.
`supersedes_release_status == "released"` requires all four released tag/release fields and null
`blocked_release_objects`; `"release_blocked"` requires all four released fields null and one
nonnull `BlockedReleaseObjectsV1`, even for `pre_tag`. Validate its phase-dependent field presence
and preserve every observed orphan tag/draft/asset identity without granting release authority,
independently of `source_campaign_state`. Complete plans require the ordered full audit merge set and
null STOP fields. Invalid-prefix plans require empty absent-audit suffixes plus exact STOP and
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
  `benchmarks/corrections/{campaign_id}/{N}/defect.json`, merged to `main` as a one-file PR and then
  recorded in canonical authority as a `correction_defect` terminal mutation. Its sequence and
  affected pointer are derived, not operator-selected. A defect in generation, scoring, judging,
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
branch and PR marker, expected result tree, annotated-tag name/message/target template, draft
Release name/body/marker, ordered asset names/sizes/digests, allowed publisher and release-finalizer
actors, proposed latest pointer, and distinct domain-separated idempotency keys for every effect and
receipt. No unpersisted local plan authorizes a write.

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

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_plan.py tests/test_public_contract.py -q`

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
) -> CorrectionIntentV1:

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
`INVALID_FINALIZED` for an invalid-prefix bundle, then call `require_no_unresolved_hold(authority)`.
Use `git merge-base --is-ancestor`, `git mktree`, and `git commit-tree` with the neutral fixed author
and committer `Laconian Benchmark Publisher <benchmark-publisher@laconian.invalid>`, UTC
timestamp derived internally from the exact `base_sha` commit's integral committer epoch/offset and
normalized to UTC `+0000`, and locale/timezone-independent environment. Callers and workflow clocks
cannot supply a timestamp. Bind the normalized value in `PublicationPlanV1.commit_timestamp`, run
the builders twice under different clocks/timezones/locales, and require identical tree/head/plan
hashes. Compute the exact file diff
from `BundleSealV1`; do not parse response JSONL or report Markdown.

Neither builder accepts a workflow path/hash scalar. Resolve the one exact
`.github/workflows/benchmark-publish.yml` member internally from
`authority.registry.workflow_inventory`, require the verified class-bound inventory to contain all
15 frozen `C0` members exactly once, re-hash that member's tagged bytes, and bind both its literal
path and hash into the plan. Reject a missing/duplicate/substituted path, a hash from a non-C0 or mutable
`main`, and a registry root that differs from the campaign package. CLI and workflow inputs expose no
workflow-identity override.

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
Publication/merge/release effects reuse the same protected boundaries, and every effect receipt is
persisted by its own expected-OID CAS while the terminal campaign state remains unchanged.

For credential exposure before merge, use only the canonical incident containment, affected-
artifact denylist/deletion-or-unavailability receipts, publisher close receipt when the complete PR
is open, `PERMANENT_STOP(reason=credential_exposure)`, and safe invalid-prefix projection. After a
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
only through the latest accepted merged/released `DurableAuthorityCheckpointV1` and exact protected
merge/tag/release objects. Every required parent must be mapped and reverified; an unmapped private
layer or merely same-named committed file forces a new campaign. Metadata-only reuse still reads the
exact prior committed bundle through that checkpoint rather than trusting a stale local copy.

Always require no unresolved invalid-event hold. For `RELEASE_BLOCKED`, the closed
`require_correction_authority` verifier requires the terminal state's accepted
`RELEASE_PLAN_INVALIDATED` event hash—not a hold—to equal
`CorrectionDefectRecordV1.evidence_sha256`; `CorrectionLineageV1.defect_record_sha256` equals the
reviewed record digest, and the later intent explicitly binds that event and record as
`supersedes`. For a `RELEASED` credential incident, the intent additionally binds the withdrawn
latest-status event and containment root. Every unrelated invalid-event hold still blocks
correction; correction records never dismiss or mutate one.

`reconstruct_latest_publication_pointer` bootstraps sequence 0 from accepted state-event authority:
`RESULT_RELEASED` supplies the initial publication/merge/tag/release receipts for `RELEASED`, while
`RELEASE_PLAN_INVALIDATED` supplies the initial publication/merge, null successful-release fields,
and exact `BlockedReleaseObjectsV1` for `RELEASE_BLOCKED`. It then folds each correction directory
only in the ordered durable member sequence. A fully verified `finalization.json` plus
`CORRECTION_RESULT_RELEASED` creates the next released pointer. Either invalidation kind leaves the
prior pointer byte-identical; it never creates a release-blocked pointer for the failed correction.

`reconstruct_correction_progress` accepts at most one contiguous in-flight directory for exactly
`latest_pointer.correction_sequence + 1`. It validates `intent_authorized`,
`publication_recorded`, `merge_recorded`, `tag_recorded`, and `release_recorded` prefixes, each with
the exact prior record hash and authority OID. Missing, duplicate, gapped, reordered, two active
directories, an effect receipt without intent, a tag before merge, or release before tag fails.
Every legitimate prefix is idempotently resumable through exact query/adoption, but it never changes
the latest pointer or authorizes docs/social claims. Only a fully receipt-bound
`CORRECTION_RESULT_RELEASED` finalization advances the pointer; from `RELEASE_BLOCKED` it also moves
state to `RELEASED`, while from `RELEASED` state remains `RELEASED` and history is appended.

Do not add a public campaign CLI. The fixed trusted preparation tool calls the initial/correction
plan builder selected from canonical authority and accepts no operator-supplied publication ID,
attempt, branch, base/head, audit merge, workflow identity, correction sequence, defect code, or
result-path override. The public console surface remains the seven offline replay commands.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_plan.py tests/test_public_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit publication planning**

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/publication.py \
  src/laconian_eval/campaign/collector.py \
  src/laconian_eval/campaign/public_projection.py \
  tools/benchmark_prepare_correction.py \
  tests/campaign/test_publication_plan.py \
  tests/test_public_contract.py
git commit -m "feat: bind exact benchmark publication plans"
```

### Task 9: Implement the byte-copy-only minimal publisher

**Files:**
- Create: `tools/benchmark_minimal_publisher.py`
- Create: `tests/campaign/test_minimal_publisher.py`
- Modify: `src/laconian_eval/campaign/publication.py`

- [ ] **Step 1: Write the failing local publisher test**

Use a local bare origin and fake GitHub PR endpoint. Supply an exact package ZIP containing only
`publication-plan.json`, `bundle.tar`, `bundle.tar.sha256`,
`tools/benchmark_minimal_publisher.py`, and the hash-bound
`laconian_eval/campaign/github_app_auth.py`. Assert the pushed branch, proposed head, exact result
tree, PR base/title/body, App actor, and receipt.

The initial authority directory is
`publication/initial/<publication-plan-id>/` and begins with a durable intent:

```python
class PublicationIntentV1(CapsuleModel):
    schema_version: Literal["PublicationIntentV1"]
    campaign_id: BoundedNonBlankString
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
```

`PUBLICATION_INTENT_AUTHORIZED` must persist `intent.json` by external-broker expected-OID CAS
before the publisher credential is mapped. The branch effect emits and persists
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

Require `publisher_app.role == "publisher"`, every observed actor to equal its bot login, and the exact
pre-registered App/installation/repository IDs and permissions-attestation hash. Reject
`github-actions[bot]`, the state/release App, or a publisher App permission response other than the
closed allowlist `actions:read`, `deployments:read`, `contents:write`,
`pull_requests:write`.

- [ ] **Step 2: Add failing authority and non-interpretation tests**

Reject a changed base, changed package/script/plan/bundle digest, unexpected ZIP/tar member, path
escape, symlink, an existing divergent remote branch, response text containing shell/HTML/Markdown payloads,
extra Git diff, PR API response with wrong head/base/actor, missing authoritative intent or prior
branch receipt, and any token in a child process
environment except the exact `git push` and PR POST operations. Spy on JSON parsing and assert only
the plan, bundle seal, checksums, and GitHub response are parsed. Add crash/race fixtures for loss
before/after branch creation, branch-receipt CAS, PR creation, and PR-receipt CAS, plus two recovery
jobs racing at each boundary.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_minimal_publisher.py -q`

Expected: FAIL because `tools/benchmark_minimal_publisher.py` is absent.

- [ ] **Step 4: Implement the standard-library-only executable**

The executable accepts only:

```text
--package-zip PATH
--repository OWNER/REPO
--receipt-output PATH
```

It reads only the fixed step-scoped `PUBLISHER_APP_ID`, `PUBLISHER_APP_INSTALLATION_ID`, and
`PUBLISHER_APP_PRIVATE_KEY` names, calls the shared bounded GitHub App auth helper, and holds the
short-lived installation token only in memory/one fixed Git transport or HTTPS request. Repository
`GITHUB_TOKEN` is never passed to the executable and has read-only workflow permissions.

It verifies the raw package ZIP digest supplied in `LACONIAN_PACKAGE_SHA256`, extracts fixed members
without `extractall`, verifies the current authority intent, plan, and bundle, creates a temporary worktree at exact `base_sha`,
copies only `expected_files`, force-adds only `result_path`, verifies index/tree/head identities,
and re-fetches the exact remote branch. The authority-selected next effect is branch or PR; one
invocation performs at most one effect. If the branch is absent it pushes
`proposed_head_sha:refs/heads/{branch_name}` with force disabled; if already present it proceeds only
when the ref equals `proposed_head_sha` and the base/tree/plan/bundle all reverify, then emits only
`PublicationBranchReceiptV1`. A later invocation requires that persisted receipt, re-fetches the
exact head/base PR, POSTs the bound PR only when none exists, and emits only
`PublicationPRReceiptV1`. It
never runs a file from the bundle and never places the token in a remote URL, log, receipt, or Git
configuration.

The only nonsecret runtime identity inputs are the fixed GitHub variables `GITHUB_REPOSITORY_ID`,
`GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_JOB`, and `GITHUB_SHA`. Before pushing, the tool
uses those numeric values to re-fetch the current job, deployment, and `benchmark-publish` approval;
it re-fetches and permission-attests its App installation, records both exact identities in
the effect-specific receipt, and rejects missing/mismatched approval, actor, installation,
authority parent, intent, predecessor receipt, or permissions.
It deletes the 0600 signer PEM and scrubs App variables/token before returning. Tests prove private
key/token canaries never reach logs, receipts, Git config/URL, bundle, or unrelated child processes.

- [ ] **Step 5: Add idempotent safe recovery**

If the exact branch exists without a PR, reverify every ref/tree/base/plan/bundle byte and create the
one bound PR without pushing or updating the branch. If the exact open PR already exists, perform no
write and accept it only when base, head, title, body digest, author, plan, and bundle are identical.
On a PR-POST conflict, re-fetch and accept only that exact unique PR. Emit a new effect-specific
receipt for the current recovery job with `created` or `adopted`; do not claim byte identity with a
receipt from a different run/job/deployment. The broker CAS accepts exactly one fully reverified
receipt before the next effect. If canonical
authority already binds one, re-fetch/reverify that accepted receipt and treat the new observation
as a no-op; if two recovery receipts race, the stale CAS loser performs no further external write.
Any object mismatch raises `publication_collision`; no force push, edit, close, approve, merge,
label, or review endpoint is called. Test recovery under a new run/job/approval identity and both
crash windows.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_minimal_publisher.py tests/campaign/test_publication_plan.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the minimal publisher**

```bash
git add tools/benchmark_minimal_publisher.py \
  src/laconian_eval/campaign/publication.py \
  tests/campaign/test_minimal_publisher.py
git commit -m "feat: publish sealed benchmark bundles minimally"
```

### Task 10: Add the protected publication workflow and trusted PR validation

**Files:**
- Create: `.github/workflows/benchmark-publish.yml`
- Create: `.github/workflows/publication-pr-validate.yml`
- Modify: `.github/workflows/benchmark-publication-state.yml`
- Create: `tools/validate_publication_pr.py`
- Create: `tests/campaign/test_publication_pr.py`
- Modify: `tests/campaign/test_publication_workflows.py`
- Modify: `tools/benchmark_minimal_publisher.py`
- Modify: `tests/campaign/test_minimal_publisher.py`
- Modify: `src/laconian_eval/campaign/publication.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `benchmarks/runbooks/public-benchmark.md`
- Modify: `tests/test_public_contract.py`
- Modify: `tests/test_ci_contract.py`

- [ ] **Step 1: Write failing workflow-boundary tests**

Require `benchmark-publish.yml` to have a read-only `prepare-publication` job and one
`benchmark-publish` environment job named `publish`. The latter has exactly
`actions: read`, `deployments: read`, `contents: read`, and `pull-requests: read` on its repository
token; it contains one repository-owned `run` step, maps only
`PUBLISHER_APP_ID`, `PUBLISHER_APP_INSTALLATION_ID`, and `PUBLISHER_APP_PRIVATE_KEY` from the
protected environment plus `${{ github.token }}` as `GITHUB_READ_TOKEN` for the bounded numeric
artifact GET, unsets the read token before executing the publisher, and has no write-capable
`GITHUB_TOKEN`, checkout,
setup, artifact, or third-party action step. Forbid `OPENAI_API_KEY`, approval/merge commands,
`gh pr review`, `gh pr merge`, force push, and mutable refs.

The same `.github/workflows/benchmark-publish.yml` also has the separately protected
`security_attestor` job. It runs only at the exact allowed main/ref/plan in the
`benchmark-publish` environment, requests OIDC for its closed job identity, and receives from the
external App-token broker one short-lived token for the existing release-finalizer App installation
with returned permissions exactly `administration:read`, `metadata:read`, and `contents:read`. The
job contains only OIDC bootstrap, the fixed broker client, and the fixed exact rule-suite/immutable-
Release readers. No App key, contents/Release write token, repository-token substitute, publisher/
state credential, provider key, or model/artifact bytes enter the job. Release-writer tokens omit
Administration permission.

- [ ] Extend the Task 9 publisher and tests with exactly two package-discriminated modes:
  `open_exact_pr` and `close_exact_pr`. Close mode requires `PublicationClosePlanV1`, re-fetches the
  exact open PR/head/receipt/invalidation, calls only the close endpoint, and emits
  `PublicationCloseReceiptV1`; it cannot open/edit/review/approve/merge/delete a branch. Both modes
  require the same publisher App identity and protected job.

Require the workflow's top-level concurrency group to be exactly
`laconian-public-benchmark-state` with `cancel-in-progress: false`. The receipt must bind the
numeric publish job, deployment, and approval actor parsed through the Task 1 GitHub records before
the bundle-kind-specific publication-PR-open event is applied.

Require `publication-pr-validate.yml` to run the stable job `publication-pr-validate` on every
`pull_request` type `opened`, `synchronize`, `reopened`, and `closed`, without a
top-level path filter, and on `pull_request_review` type `submitted|dismissed`, with read-only
permissions and no secrets. Review events resolve the exact current PR/head before validation. It executes
`tools/validate_publication_pr.py` from the exact base checkout, never candidate code. An unrelated
diff returns a successful explicit no-op so the globally required check is never left Pending.
Its job declares exactly `contents: read` and `pull-requests: read`.

Require `benchmark-publication-state.yml` to use the shared concurrency group and trusted-base code
on the same PR events plus no-input `workflow_dispatch`. It no-ops unrelated PRs. A read-only inspect
job declares exactly `contents: read`, `actions: read`, `pull-requests: read`, and `checks: read` and
reconstructs the exact publication receipt from the canonical authority ref; a narrow
  state mutation calls the existing OIDC reusable job created by Runtime Task 9. That job contains
  only OIDC bootstrap and the fixed broker client; no state-writer credential or installation token
  is mapped into Actions. When an exact still-open plan is invalidated, this workflow
emits only a safe close-required summary. The same no-input `benchmark-publish.yml` and same
protected `publish` job/tool later enter their receipt-bound `close_exact_pr` mode; there is no third
write-capable close job. No job reviews, approves, merges, force-pushes, edits, or deletes result
content.
Forks, human-authored PRs, and non-result diffs can execute only the read-only no-op path; policy
tests inspect job conditions and exact head repository/actor/receipt bindings before any write token
is available.

For every manual publication path, require exact `refs/heads/main` at the plan-bound main SHA,
re-read the caller and reusable workflow blobs at that SHA, and derive the campaign/authority only
from the accepted intent/receipt. Reject an input tag, another branch, mutable selector,
newest/by-name discovery, operator campaign/PR/head/base input, or a main SHA not bound by the plan.
The only exceptions to plan-bound main are the six exact post-merge events defined below; even those
retain OIDC `ref=refs/heads/main` and use independently verified Git/GitHub objects.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_publication_pr.py -q`

Expected: FAIL because the two new workflows, publication/admission recorders, and required caller
rows in the existing reusable workflow are absent.

- [ ] **Step 3: Implement the publication workflow**

`prepare-publication` reconstructs current authority. On the initial path it proves
`BUNDLE_COLLECTED` or `INVALID_FINALIZED`, downloads the exact bundle, and builds
`PublicationPlanV1`. On the correction path it proves terminal `RELEASED|RELEASE_BLOCKED` plus the
accepted next `correction_defect` mutation and a resumable `CorrectionProgressV1` planning stage,
runs the Task 8 correction-bundle producer, uploads that
bundle, re-fetches its numeric locator, and only then builds the correction plan. When the exact
current publication plan is invalid while its PR remains open, it instead builds a closed
`PublicationClosePlanV1` binding only that receipt/PR/head and the already-derived invalidation.
It packages the selected plan, bundle when opening, exact publisher script, and App-auth helper,
uploads with 90-day retention, and exports artifact ID, service digest, payload digest, and plan
digest. No workflow/operator input selects the mode.

The gated `publish` job uses one frozen shell block to download the package by numeric artifact ID,
hash the raw ZIP, extract the fixed publisher script with `unzip -p`, hash the script, and execute
it with only publisher-App credentials. Open mode reconciles and emits the separate branch and PR
receipts from Task 9; close mode may only
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
For the `publication-pr-validate` required check to succeed, also re-fetch one current APPROVED
review at the exact head from a preregistered non-bot maintainer numeric ID/login, require its exact
review ID/API-record digest, and reject dismissal/staleness. Before that review the result validator
fails closed; its `pull_request_review submitted|dismissed` trigger reruns the same check. Thus a
publisher-App review cannot satisfy the gate even though `pull_requests:write` is technically broad
enough to call review/merge endpoints.

For a correction-defect PR, require a non-bot human author, exactly the next fixed defect path and
no other diff, strict `CorrectionDefectRecordV1`, current latest-pointer binding, a current distinct
human approval, and no result/workflow/docs changes. On its exact merged event,
`benchmark-publication-state.yml` revalidates merge ancestry/tree and uses
the reusable OIDC broker to append the reviewed defect/incident root to authority; this is the sole
entry into correction preparation. Unrelated PRs return the explicit `irrelevant` result.

Define strict `RequiredCheckEvidenceV1` for each required check with check-run ID/name,
`status == "completed"`, conclusion, head SHA, check-suite ID/event, source App numeric ID/slug,
workflow run ID/attempt, trusted workflow path/SHA-256, and evidence digest. Re-fetch check run,
suite, and Actions run by exact IDs; require the preregistered GitHub Actions source App and trusted
base workflow bytes. A same-name check from another App/workflow, a rerequested/in-progress suite,
or a run on another SHA fails even if its conclusion says success.

Define `PublicationMergeReceiptV1` with literal `merge_method="merge_commit"`, exact plan/intent/
branch/PR receipts, PR number, protected base ref/OID, approved head OID, observed merge commit `M`,
ordered parents exactly `[base_oid, approved_head_oid]`, expected/observed merge tree, result subtree
root, human review and merge actors, required checks, `PostMergeAdmissionEvidenceV1`, complete
`DurableAuthorityCheckpointV1`, and its digest. V1 has no queue/squash/rebase fields or aliases.

The broker constructs `PostMergeAdmissionEvidenceV1` independently from exact GitHub API responses
and Git object bytes, never from event input. It proves the PR is merged, `M` is the PR's immutable
merge commit, its parents/tree exactly match the plan, all checks and current approvals bind the
approved head, the human actor/method are allowed, and historical protection was enforced. The
downscoped `security_attestor` job receives only a short-lived token brokered from the existing
release-finalizer App installation with `administration:read`, `metadata:read`, and `contents:read`;
it immediately fetches and seals the complete repository rule-suite
record whose `before_sha=base_oid`, `after_sha=M`, `ref=refs/heads/main`, actor equals the merge
actor, overall result is `pass` rather than `bypass`, and every active per-rule evaluation matches
the plan-bound ruleset. Reading only current rules is insufficient.

For a post-merge dispatch, OIDC remains on `refs/heads/main` at current main `H`. Require `H == M` or
a protected first-parent descendant that contains `M`, keeps the plan-bound result subtree
byte-identical, and has no intervening commit touching that subtree. Re-read main before and after
all other observations and re-evaluate containment. The caller and reusable workflow blobs at `H`
must still equal their C0 inventory members. Missing, contradictory, bypassed, late-missing, or
moving evidence fails closed.

Define `PostMergeAdmissionFailureV1` with exact campaign/optional correction ID, plan/bundle roots,
PR/base/head/observed-merge/current-main OIDs, observed parents/tree/result roots, actor/method,
checks/approvals root, complete rule-suite observation root, ordered GitHub/Git request-receipt root,
nonempty schema-ordered deduplicated `failed_predicates`, no-later-effects root, and its digest. The
closed predicates are `unexpected_merge_parent`, `unexpected_merge_method`,
`result_tree_mismatch`, `checks_or_approvals_invalid`, `merge_actor_invalid`,
`historical_rules_invalid`, `main_containment_invalid`, `workflow_root_mismatch`, and
`observation_inconsistent`.

The six and only six post-merge broker exceptions are:

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
release phase. All other main events remain pinned to their pre-bound main SHA.

Only successful complete admission from `COMPLETE_PUBLICATION_PR_OPEN` emits `RESULT_MERGED` and
enters `RESULT_MERGED`. Successful invalid admission from `INVALID_PUBLICATION_PR_OPEN` emits
`INVALID_PREFIX_MERGED` and enters terminal `INVALID_PREFIX_MERGED`. Failed complete admission emits
`RESULT_MERGE_INVALIDATED` and enters `RELEASE_BLOCKED`; failed invalid admission emits
`INVALID_PREFIX_MERGE_INVALIDATED` and enters terminal `INVALID_PREFIX_MERGED_INVALID`. Cross-kind,
generic, absent-discriminator, or wrong-parent events create a hold without state mutation.

Define `PublicationInvalidationV1` with a discriminant `phase: pre_open|post_open`, closed reason
`base_moved|head_moved|closed_unmerged|plan_mismatch|stop_after_open`, the old plan hash, exact
invalidated `publication_id` and `publication_attempt`, observed safe Git identities, bundle kind,
prior-invalidation root, and digest. `pre_open` permits only `base_moved|plan_mismatch`, requires the
receipt/PR/close fields null as a set, and binds the independently re-fetched base/branch absence or
exact state. `post_open` requires the old receipt and PR identity; if that PR remains open it also
requires the exact close plan/receipt, while an independently observed already-closed PR binds that
closed record. An exact unchanged branch with no PR is the Step 5 recovery case and cannot be
invalidated merely to skip recovery. On any such condition,
`invalidate-publication-plan` constructs `COMPLETE_PUBLICATION_PLAN_INVALIDATED` or
`INVALID_PUBLICATION_PLAN_INVALIDATED`; if the exact PR is still open, the protected close job first
reconstructs `PublicationClosePlanV1`, the same publisher job closes only that PR, and
`PublicationCloseReceiptV1` must verify before the broker applies the event. In correction
mode, successful admission appends `CORRECTION_MERGE_RECORDED`; an absent/closed unmerged PR appends
`CORRECTION_INVALIDATED(kind=correction_publication_invalidation,
publication_outcome=unmerged_invalid)`, while an already merged
failed-admission PR takes only the sixth broker exception with `merged_invalid`. Neither uses
`RESULT_MERGED` nor advances the latest pointer. Replanning an initial publication
starts from `BUNDLE_COLLECTED` or `INVALID_FINALIZED` with the next authority-derived attempt and a
new branch, head, and plan; the base and bundle may remain byte-identical. It never updates or
force-pushes the invalid branch. Add end-to-end cases for both bundle kinds, `main` moving after plan
construction but before branch/PR creation, base movement after opening, unchanged
base/bundle after `head_moved`, unchanged base/bundle after `closed_unmerged`, merged success, and a
CAS race; prove each accepted invalidation advances the attempt exactly once.

- [ ] **Step 5: Add manual approval evidence to the runbook test**

Assert the workflow and runbook state that the publisher-App-authored same-repository PR triggers
the always-present validators normally; it does not depend on the repository-global Actions
create/approve-PR toggle or a fork-workflow approval. A write-authorized maintainer verifies the
exact head/bundle, supplies the required human PR review, and merges only after required checks.
Neither the publisher App nor any workflow approves a review or merges the PR.

The runbook also gives the exact no-input recovery dispatch, merge-recorder, close/replan, and stale
CAS procedures. It forbids manually supplied PR/head/base IDs and states that complete release
planning is blocked until `PublicationMergeReceiptV1` has advanced canonical authority to
`RESULT_MERGED`; invalid-prefix outcomes are terminal and have no release plan.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_publication_pr.py tests/campaign/test_minimal_publisher.py tests/test_public_contract.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` enumerates exactly thirteen workflows: the eleven
present after Task 7 plus the two new workflows in this task; the Runtime-owned reusable workflow is
modified, not counted twice.

- [ ] **Step 7: Commit protected publication and PR validation**

```bash
git add .github/workflows/benchmark-publish.yml \
  .github/workflows/publication-pr-validate.yml \
  .github/workflows/benchmark-publication-state.yml \
  tools/validate_publication_pr.py \
  tools/benchmark_minimal_publisher.py \
  src/laconian_eval/campaign/publication.py \
  src/laconian_eval/campaign/__init__.py \
  tests/campaign/test_minimal_publisher.py \
  tests/campaign/test_publication_pr.py \
  tests/campaign/test_publication_workflows.py \
  benchmarks/runbooks/public-benchmark.md \
  tests/test_ci_contract.py \
  tests/test_public_contract.py
git commit -m "ci: gate exact benchmark publication pull requests"
```

### Task 11: Build `ResultReleasePlanV1` and the idempotent release finalizer

**Files:**
- Create: `src/laconian_eval/campaign/release.py`
- Create: `tools/benchmark_release_finalizer.py`
- Create: `tests/campaign/test_result_release.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write the failing merged-result plan test**

Create an approved publication PR fixture, merge it, and build two fixed assets:
`benchmark-result-{publication_id}.tar` and `benchmark-result-{publication_id}.tar.sha256`. Assert the
merge tree contains the exact result path and the release plan binds every digest.

Use:

```python
class ReleaseAssetV1(CapsuleModel):
    name: BoundedNonBlankString
    media_type: Literal["application/x-tar", "text/plain"]
    byte_length: StrictNonNegativeInt
    sha256: Sha256


class ResultReleasePlanV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    correction_lineage_sha256: Sha256 | None
    input_tag_object_sha: GitObjectId
    input_commit_sha: GitObjectId
    authority_state_sha256: Sha256
    unresolved_hold_root_sha256: Sha256
    bundle_kind: Literal["complete"]
    bundle_sha256: Sha256
    publication_plan_sha256: Sha256
    publication_merge_receipt_sha256: Sha256
    publication_pr_number: StrictPositiveInt
    publication_approved_head_sha: GitObjectId
    merge_commit_sha: GitObjectId
    result_tree_sha256: Sha256
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
`benchmark-result-{campaign_id}-correction-{N}` and requires the matching
`CorrectionLineageV1.lineage_sha256`. Each points through a new annotated tag object to its exact
merge commit; no existing tag or release is updated, deleted, retargeted, or overwritten.
Derive the tagger timestamp from the canonical publication/merge receipt time selected by the plan,
normalize it to Git's exact UTC `+0000` representation, and construct the annotated-tag bytes with
the fixed name/email, exact target/type/tag, and one canonical LF-terminated message. Compute
`expected_tag_object_sha` with `git mktag` in a locale/timezone-independent environment before any
GitHub call. A rerun must reproduce the same object ID; a tagger clock, identity, message, or newline
override is forbidden.

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

Run: `uv run pytest tests/campaign/test_result_release.py -q`

Expected: FAIL because `release.py` and the finalizer are absent.

- [ ] **Step 4: Implement release-plan construction**

Add:

```python
def build_result_release_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    publication_plan: PublicationPlanV1,
    publication_receipt: PublicationPRReceiptV1,
    publication_merge_receipt: PublicationMergeReceiptV1,
    asset_root: Path,
) -> ResultReleasePlanV1:

def build_correction_release_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    correction_publication_plan: PublicationPlanV1,
    correction_publication_receipt: PublicationPRReceiptV1,
    correction_merge_receipt: PublicationMergeReceiptV1,
    correction_lineage: CorrectionLineageV1,
    asset_root: Path,
) -> ResultReleasePlanV1:
```

Neither release builder accepts a workflow path/hash scalar. Resolve only the literal
`.github/workflows/benchmark-release.yml` member from the same verified 15-member frozen `C0`
`authority.registry.workflow_inventory`, re-hash its tagged bytes, and bind the path and hash in the
release plan. Reject path/hash substitution, a non-C0 or mutable-`main` workflow, inventory-root drift,
or any CLI/workflow override.

Require `authority.state.state == "RESULT_MERGED"`, call
`require_no_unresolved_hold(authority)`, and require the exact approved head, actual merge commit,
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
`RELEASE_BLOCKED`, the verified correction publication/merge receipt, and the same
`CorrectionLineageV1`; it requires the new correction result path and does not change campaign state
while planning. Initial and correction release plans share the exact asset construction and finalizer, but a
correction can only create its new sequence-specific tag/release. Every name, marker, asset digest,
actor, target template, and idempotency key must equal the already persisted correction intent; the
post-merge builder may bind observed `M` but cannot invent a new external effect identity.

Before any initial release effect, `RESULT_RELEASE_INTENT_AUTHORIZED` persists
`publication/initial/<publication-plan-id>/release-intent.json` by expected-OID CAS while state
remains `RESULT_MERGED`. It binds the deterministic annotated-tag bytes/OID/name/target, exact draft
Release name/body/marker, ordered asset names/sizes/digests, release-finalizer actor, immutable-
Release policy root, and distinct idempotency keys for tag, draft, each asset, publish, every receipt,
and finalization. A correction uses the already authoritative `corrections/<correction-id>/intent.json`
and is eligible only after its valid `merge-receipt.json`. Missing intent, wrong parent OID,
cross-lineage names, or a release effect after correction publication invalidation fails before the
release-finalizer credential is mapped.

- [ ] **Step 5: Implement the standard-library-only release finalizer**

`tools/benchmark_release_finalizer.py` accepts only package ZIP, repository, and receipt path. The
package contains the exact finalizer plus the hash-bound shared `github_app_auth.py`; the tool reads
only fixed step-scoped `RELEASE_APP_ID`, `RELEASE_APP_INSTALLATION_ID`, and
`RELEASE_APP_PRIVATE_KEY`, mints a short-lived installation token, verifies the closed release-App
  permission response, and scrubs all signer/token material. It verifies the package and plan;
  independently rebuilds the exact annotated-tag bytes and requires its object ID to equal
  `expected_tag_object_sha`. The authority-selected invocation performs at most one effect:
  create/adopt tag, create/adopt draft, upload/adopt one asset, publish/adopt, or final verification.
  Each effect emits its own `TagReceiptV1`, `DraftReleaseReceiptV1`, `ReleaseAssetReceiptV1`, or
  `PublishReceiptV1`; the broker persists that receipt before the next effect is eligible. The fixed
  serialized finalizer never skips a missing predecessor receipt and never performs an untracked
  retry.

Return:

```python
class ImmutableReleaseVerificationV1(CapsuleModel):
    schema_version: Literal["ImmutableReleaseVerificationV1"]
    repository_setting_response_sha256: Sha256
    release_fields_sha256: Sha256
    gh_version: BoundedNonBlankString
    gh_binary_sha256: Sha256
    gh_release_verify_output_sha256: Sha256
    verification_sha256: Sha256


class ResultReleaseReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    correction_lineage_sha256: Sha256 | None
    release_plan_sha256: Sha256
    bundle_kind: Literal["complete"]
    bundle_sha256: Sha256
    result_tag_name: BoundedNonBlankString
    tag_object_sha: GitObjectId
    target_commit_sha: GitObjectId
    release_operation: Literal[
        "created_tag_and_release", "reused_tag_created_release",
        "resumed_exact_draft", "observed_exact_published"
    ]
    release_id: StrictPositiveInt
    release_url: ExactAsciiHttpUrl
    published_at_utc: CanonicalTimestamp
    immutable: Literal[True]
    immutable_release_verification: ImmutableReleaseVerificationV1
    durable_authority_checkpoint: DurableAuthorityCheckpointV1
    durable_authority_checkpoint_sha256: Sha256
    assets: tuple[ReleaseAssetV1, ReleaseAssetV1]
    repository_id: StrictPositiveInt
    workflow_run_id: StrictPositiveInt
    run_attempt: StrictPositiveInt
    job_id: StrictPositiveInt
    job_name: Literal["release-finalizer"]
    environment: Literal["benchmark-publish"]
    deployment_id: StrictPositiveInt
    approval_actor_id: StrictPositiveInt
    approval_actor_login: BoundedNonBlankString
    release_app: GitHubAppInstallationIdentityV1
    released_by: BoundedNonBlankString
    receipt_sha256: Sha256
```

Require `release_app.role == "release_finalizer"`, `released_by == release_app.bot_login`, the
pre-registered App/installation/repository IDs, and exact permission attestation. Reject the
publisher/state Apps, `github-actions[bot]`, or any permission response other than the closed
write-token allowlist `metadata:read`, `actions:read`, `deployments:read`, and `contents:write`
(whose reachable surface includes the required new-tag/release/asset endpoints). The installed App
also has `administration:read`, but that permission is omitted from the write token and appears only
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
```

Before tag or Release effects, the fixed `security_attestor` job in
`.github/workflows/benchmark-publish.yml` uses only the short-lived token brokered from the existing
release-finalizer App installation and downscoped to `administration:read`, `metadata:read`, and
`contents:read` to fetch
`GET /repos/{owner}/{repo}/immutable-releases`; false, missing, malformed, or unbound responses fail
closed. Draft recovery fully paginates authenticated `GET /repos/{owner}/{repo}/releases`, matches
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

An exact existing published immutable tag/release is idempotent. An exact draft may resume missing
byte-identical asset uploads and the one publication transition; a divergent draft is invalidated
and left untouched for incident handling. A crash after one upload, after both uploads, or after
publication re-fetches exact state and resumes only the missing step. The executable never deletes,
retargets, replaces, overwrites, or edits a published release, and its only release update is the
single exact draft-to-published transition after both assets verify.
Every success emits a `ResultReleaseReceiptV1` for the current job with the matching
`release_operation`; it is not byte-identical to a prior run's receipt because run/job/deployment/
approval identity is retained. The recorder/state CAS accepts one reverified receipt. If authority
already binds an earlier receipt, the current observation becomes a no-op after re-verifying that
receipt and all plan-bound external objects; racing receipts cannot trigger another external update.
On every non-idempotent failure, re-fetch the bounded tag/release/asset set and emit a safe
`BlockedReleaseObjectsV1`; the broker persists it before any correction can be planned. Conflicting
or externally visible objects are retained as exposure evidence under the no-overwrite/no-reuse
protocol; this is not a claim that the platform makes them undeletable.

Before the first tag API call it uses the same fixed GitHub runtime identity variables as the
publisher, re-fetches the numeric `release-finalizer` job, deployment, and separate
`benchmark-publish` approval, calls the authority/hold verifier bound by the plan, re-fetches and
attests the release App, re-fetches the immutable-Releases repository setting and exact trust-
boundary record, and records both authorizations in `ResultReleaseReceiptV1`. Repository
`GITHUB_TOKEN` is read-only and is never the release actor.

Do not add a public campaign CLI. The fixed trusted release-preparation tool selects initial or
correction construction only from verified authority/lineage and accepts no tag, Release, PR,
merge, asset, actor, campaign, correction, or effect identity override.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_result_release.py tests/test_public_contract.py -q`

Expected: PASS.

- [ ] **Step 7: Commit result release planning and finalization**

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/release.py \
  tools/benchmark_release_finalizer.py \
  tests/campaign/test_result_release.py \
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
`pull-requests: read`, and `checks: read`; a separate `benchmark-publish` environment job named
`release-finalizer`; a read-only `record-release`; and a call to the Runtime-owned OIDC broker
reusable job. The gated job has
exactly `actions: read`, `deployments: read`, and `contents: read` on its repository token, one
repository-owned `run` step, step-scoped release-App ID/installation/private key plus a
`GITHUB_READ_TOKEN` used only for the numeric package GET and unset before finalization, no provider
secret, no checkout/setup/action step, and no generic release edit/delete command; the hash-bound
finalizer alone may issue its one exact draft-to-published PATCH after asset verification. The
release preparation must consume the exact plan-bound `security_attestor` receipt produced by the
fixed protected job in `.github/workflows/benchmark-publish.yml`, including its broker token-request
identity and returned `administration:read`/`metadata:read`/`contents:read` permissions. It cannot
substitute repository-token reads or request a new token in this workflow. The reusable state job
contains only OIDC bootstrap and the fixed broker client; no
state-writer App ID, installation ID, private key, or installation token exists in Actions. No repository
`GITHUB_TOKEN` can write.

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/campaign/test_publication_workflows.py -q`

Expected: FAIL because `.github/workflows/benchmark-release.yml` is absent.

- [ ] **Step 3: Implement the release workflow**

Trigger only with no-input `workflow_dispatch` at the exact plan-bound `main` SHA. Use the shared
`laconian-public-benchmark-state` concurrency group. For an initial release,
`prepare-release` proves exact `RESULT_MERGED`; for a correction, it proves the terminal
`RELEASED|RELEASE_BLOCKED` state plus
`reconstruct_correction_progress(authority).phase == "merge_recorded"` and the exact durable correction
publication/merge lineage. It checks
current PR/merge/tree/security state, builds the release plan/assets/finalizer package, and uploads
it for 90 days. `release-finalizer` downloads by numeric artifact ID, verifies the exact hashed
script and App-auth helper, and executes them with only the release-App credentials.
`record-release` re-fetches all GitHub objects and emits a receipt-bound candidate only after
verification. It derives the released `DurableAuthorityCheckpointV1` by extending the exact merged
checkpoint with the annotated tag object/target, `ImmutableReleaseVerificationV1`, and both verified
asset digests; it re-verifies that every prior transient mapping remains present byte-for-byte. For
the initial release, the broker binds every intent/effect receipt, finalization, checkpoint, and
`RESULT_RELEASED` from `RESULT_MERGED`. For a correction it persists `tag-receipt.json` and
`release-receipt.json` after their effects, then installs `finalization.json`, the next latest
pointer, and `CORRECTION_RESULT_RELEASED` in one expected-OID CAS only after all five ordered phase
records verify. A correction from `RELEASED` leaves state `RELEASED`; one from `RELEASE_BLOCKED`
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
setting, incomplete released checkpoint, or failed `ImmutableReleaseVerificationV1` emits
`RELEASE_PLAN_INVALIDATED` with exact `BlockedReleaseObjectsV1` and no result rewrite.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_result_release.py -q`

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
`YYYY-MM-DD` derived only from `ResultReleaseReceiptV1.published_at_utc` after UTC normalization,
and `publication_id` equals the campaign ID for an initial release or its exact
correction publication ID. All three are required changed paths in a post-release result-claims PR.
Every changed result block contains this exact marker grammar:

```html
<!-- laconian-result campaign="{campaign_id}" publication="{publication_id}" bundle="{bundle_sha256}" tag="benchmark-result-{publication_id}" -->
```

The brace-delimited values are validated variables taken from `ResultReleaseReceiptV1`;
`bundle_sha256` must be exactly 64 lowercase hexadecimal characters.

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

Run: `uv run pytest tests/campaign/test_docs_gate.py -q`

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
    release_plan: ResultReleasePlanV1,
    release_receipt: ResultReleaseReceiptV1,
    claim_evidence: PostReleaseClaimEvidenceV1,
) -> None:
```

Derive the changed-path inventory internally by opening the exact trusted and candidate Git trees,
enumerating their raw byte path/mode/object-ID tuples, and computing the canonical UTF-8-byte-sorted
diff. Never accept a changed-path list from a caller, event payload, CLI option, or environment.
Reject invalid UTF-8, aliases after path normalization, duplicate/missing/extra/reordered diff rows,
symlinks, submodules, and a candidate tree that does not equal the event's independently re-fetched
head. Tests prove that omitting a result-shaped path or substituting an event-supplied list cannot
select the no-op or sealed-result carve-out.

Unconditionally require `authority.state.state == "RELEASED"`, no unresolved hold, and
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
result-shaped Markdown/HTML paths changed, so the required check is always present.
Its job declares exactly `contents: read` and `pull-requests: read`.
At this final workflow checkpoint, make `tests/test_ci_contract.py` assert that its 15 exact workflow
paths equal Runtime's `BenchmarkWorkflowInventoryV1` production path constant, then build/reverify
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

Run: `uv run pytest tests/campaign/test_docs_gate.py tests/campaign/test_publication_workflows.py tests/test_public_contract.py tests/test_site.py -q`

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
and released durable checkpoints to replay identical authority solely from protected Git objects,
committed result bytes, annotated tag, and immutable release assets. Before the merge event, the
same expiry remains fatal.

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
merge-receipt CAS, release-intent CAS, tag creation, tag-receipt CAS, draft creation, draft-receipt
CAS, each asset upload/receipt CAS, publish, publish-receipt CAS, finalization, and final event CAS.
Every retry must query exact names, create or adopt once, and either persist the matching receipt or
record terminal conflict evidence.

Cover all six post-merge broker exceptions, both complete and invalid initial outcomes, correction
success, `unmerged_invalid`, `merged_invalid`, release-phase invalidation, and successful recovery
from every durable correction prefix. Assert invalidation never advances the latest pointer and a
new correction after `merged_invalid` explicitly supersedes the failed correction and contaminated
merge. Include current main exactly `M`, a protected first-parent descendant with no result touch,
an intervening result touch, missing/bypass per-rule suite, double-read movement, and every
`PostMergeAdmissionFailureV1.failed_predicates` member.

Exercise credential exposure before merge (contain/close/STOP/safe invalid prefix), after complete
merge before release (release blocked, no original tag/Release), and after `RELEASED` (historical
objects retained, latest withdrawn, containment recorded, superseding correction required). Assert
no fixture or message claims historical erasure or platform undeletability.

- [ ] **Step 4: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_reconstruction.py -q`

Expected: FAIL until the fixture connects every Slice 4 interface and state event.

- [ ] **Step 5: Complete the deterministic offline fixture**

Use no network, provider key, current time, random UUID, mutable branch lookup, or host-private path.
Freeze repository ID and trust-boundary/settings records; the run, attempt, job, deployment,
approval, and artifact IDs for every hard-score/evidence/audit/analysis/collection/publication/release
stage; canonical timestamps; API JSON; Git author/tagger identity; deterministic USTAR bytes;
draft/upload/publish/immutable-release responses; and result assets in `publication_helpers.py`.
Make `fake_github.py` reject every endpoint outside Task 1's exact artifact/repository read
allowlist and Task 11's enumerated immutable-setting, paginated Release/asset read, annotated-tag,
tag-ref, draft-Release, upload-host asset, and sole draft-to-published endpoints. It must model fully
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
tag-object, merged/released durable-checkpoint, `ImmutableReleaseVerificationV1`, and receipt hashes.

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
contains state-writer App ID/installation/private-key secret expressions or a state-writer
installation token; `.github/workflows/benchmark-publication-state.yml` contains only OIDC bootstrap
and the fixed broker client. Assert exactly three pairwise-distinct App identities overall, with only
publisher and release-finalizer private-key secret mappings in their role-matched protected jobs;
`security_attestor` uses only the existing release-finalizer installation's brokered
`administration:read`/`metadata:read`/`contents:read` token and is not a fourth App. Reject a
repository-token substitute, App key, or write scope.

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
live workflow invokes a replay command, and only the approved publisher/release-finalizer secret
boundaries remain.

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
  - publisher: metadata read, `actions: read`, `deployments: read`, `contents: write`, and
    `pull_requests: write`; no checks/administration permission. These permissions technically expose
    review/merge and release endpoints, but the fixed tool never calls them, result-tag rules and
    immutable Releases bound the release surface, the result validator accepts only a preregistered
    non-bot maintainer review, and the `main` ruleset excludes the App from merge;
  - release finalizer: metadata read, `actions: read`, `deployments: read`, `contents: write`, and
    `administration: read`; no pull-request/checks/reviews permission. The finalizer write token
    omits administration, while the separately brokered `security_attestor` token has only
    administration/metadata/contents read and no write scope.
- [ ] Configure `.github/workflows/benchmark-publish.yml` job `security_attestor` to request a
  short-lived brokered token from the existing
  release-finalizer App installation, downscoped exactly to `administration:read`, `metadata:read`,
  and `contents:read`. It fetches exact immutable-Releases and historical rule-suite evidence and is
  not a fourth App. No repository-token substitute, release-finalizer private key, write-scoped
  installation token, or write permission may reach the job.
- [ ] Configure the external state broker's exact repository/caller/OIDC policy and store the
  state-writer App private key only in that broker. Do not create any state-writer repository or
  environment Actions secret, and do not return an installation token to a runner. Store only the
  `PUBLISHER_*` and `RELEASE_*` triples in `benchmark-publish`; expression-location policy tests
  ensure each protected job maps only its own role. Do not create `benchmark-state` or
  `benchmark-release` environments. Rotate any key exposed outside its intended scope and update the
  attestation before dispatch.
- [ ] Create an immutable input-tag ruleset for `benchmark-input-*` that blocks update and deletion
  and restricts creation to authorized maintainers.
- [ ] Create an immutable result-tag ruleset for `benchmark-result-*` that blocks update and deletion
  and grants create bypass only to the exact release-finalizer App installation. The publisher and
  state Apps cannot bypass it.
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
- [ ] Add `publication-pr-validate`, `audit-pr-validate`, and `benchmark-docs-validate` to required
  `main` checks after each has produced its first recognized check run. Confirm all three jobs run on
  every PR, have no top-level path filter, and return explicit success
  when irrelevant. Preregister each exact check name with the expected GitHub Actions source App ID,
  workflow path, and trusted workflow hash; a same-name check from another App/workflow does not
  satisfy merge recording.
- [ ] On `main`, keep one required human PR approval, required conversation resolution, enforced
  administrators, force-push/deletion prohibition, and a restrict-updates/merge-actors rule allowing
  only the preregistered non-bot maintainer team. Explicitly exclude all three benchmark Apps,
  GitHub Actions, and other bots from merge eligibility; record the numeric maintainer IDs used by
  `PublicationMergeReceiptV1`.
- [ ] Set every benchmark Actions artifact to the repository maximum retention of 90 days and finish
  every pre-merge lineage before any required artifact expires. At `RESULT_MERGED`, require the
  complete durable checkpoint into the protected merge tree; after that, expiry substitution is
  allowed only through that verified mapping and, after release, its immutable tag/assets extension.
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
  opens, verify the same head/bundle, submit the required human review, and merge only after all
  always-present checks succeed; there is no fork-workflow approval step.
- [ ] Before release approval, verify the exact merged tree, `ResultReleasePlanV1`, tag name, and both
  asset digests, deterministic tag-object ID, draft-to-published plan, immutable-release setting, and
  merged durable checkpoint.
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
invalid-prefix lineages reconstruct twice with identical hashes, and a maintainer has reviewed the
repository-settings checklist without changing GitHub as part of implementation. No live provider
call, publication PR, result tag, GitHub Release, README result block, website result, release note,
or social package is created by executing this plan.
