# Public Benchmark Publication Slice 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the secret-free, fail-closed publication half of the public three-model benchmark: exact GitHub artifact provenance, provider-evidence inventory sealing, complete and invalid-prefix collection, minimal reviewed publication, checksum-bound result release, and post-`RELEASED` documentation validation.

**Architecture:** Slice 4 consumes immutable campaign authority from Slice 3, sealed generation/hard-score/judge evidence, and the neutral audit/analysis APIs from Slice 2. Fixed campaign-side tools authoritatively stage and seal the live audit and analysis outputs while keeping Runtime-verified expectations in process. Repository-owned Python code retrieves artifacts only by exact numeric identity, verifies every parent hash, projects one of two disjoint public bundle kinds, and creates deterministic publication and release plans. Repository `GITHUB_TOKEN` permissions remain read-only everywhere. Three mutually exclusive GitHub Apps carry the only writes. Their broad GitHub permissions make multiple endpoints technically reachable, but each is protocol-authorized and its fixed hashed tool may act only in one role: state-writer expected-OID-CAS on `benchmark-authority/*`; publisher creation of a bound result branch/PR or closure of that exact invalidated PR; release-finalizer creation of one new protected result tag/release. Rulesets, immutable Releases, endpoint-policy tests, and receipts enforce that separation. Publisher and release-finalizer credentials are mapped only in separately approved jobs in the existing `benchmark-publish` environment; the state-App repository secrets are mapped only to fixed hashed writer steps. None receives the provider key or interprets model output.

**Tech Stack:** Python 3.11+, Pydantic v2 strict models, standard-library `hashlib`, `json`, `tarfile`, `urllib`, `zipfile`, Git plumbing, pytest, deterministic property loops, uv, and GitHub Actions pinned to full commit SHAs.

**Approved design:** [Public Three-Model Benchmark Pipeline Design](../specs/2026-08-30-public-three-model-benchmark-design.md), especially sections 7.4, 12, 13, 14, and 16.

**Protocol/security amendment prerequisite:** Before Task 1, merge and reapprove roadmap Milestone
0, which adds the literal default-tier/cache/accounting/reviewer/workflow-root contract and replaces
the design's two-job/write-capable repository-`GITHUB_TOKEN` topology with the four-job,
three-dedicated-App topology specified here. It also approves the Section 7.4
`RELEASE_BLOCKED + CORRECTION_RESULT_RELEASED -> RELEASED` edge and terminal-evidence-only
correction behavior from `RELEASED`. Until then every Publication task is blocked. The older or
implicit contracts are not fallbacks; all experiment and evidence invariants remain normative.

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
    append_terminal_evidence,
    append_terminal_evidence_then_event,
    apply_campaign_event,
    require_no_unresolved_hold,
)
from laconian_eval.campaign.artifact_wire import ArtifactEnvelopeV1, UploadAuthorizationV1
from laconian_eval.campaign.benchmark_stage import load_authority_verified_generation_context
from laconian_eval.campaign.preflight import CampaignRegistryV1
from laconian_eval.campaign.spend import SpendLedgerV1
from laconian_eval.campaign.state import CampaignEventV1, CampaignStateV1, InvalidEventHoldV1
from laconian_eval.campaign.models import GitHubAppInstallationIdentityV1
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

Slice 2 must also expose the seven offline/non-evidentiary `laconian-benchmark` replay commands with
`allow_abbrev=False`. Production staging never invokes those raw commands: the Slice 4 hard-score
workflow and Slice 3 final judge-batch post step call the Runtime-owned campaign-side tools below,
which keep the authority-verified context wrapper in-process. Slice 4 Task 7 owns analogous fixed
campaign-side sample-audit, seal-audit, and analyze-plus-verify tools for the remaining neutral
Evaluation APIs. Slice 4 consumes the already sealed judge output and does not duplicate judge
execution:

```text
uv run python tools/benchmark_hard_score_stage.py --authority-root AUTHORITY --generation-index GENERATION_INDEX --generation-root GENERATION --hard-score-output-root HARD --judge-request-output-root REQUESTS
uv run python tools/benchmark_seal_judge_stage.py --authority-root AUTHORITY --generation-index GENERATION_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-attempt-root ATTEMPTS --output-root OUT
```

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
from laconian_eval.campaign.evaluation_stage import (
    load_authority_verified_provider_evidence,
    run_analyze_and_verify_stage,
    run_sample_audit_stage,
    run_seal_audit_stage,
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
- `src/laconian_eval/campaign/publication.py`: `PublicationPlanV1`, deterministic Git tree/commit
  construction, byte-copy publisher, and PR validator.
- `src/laconian_eval/campaign/release.py`: `ResultReleasePlanV1`, release assets, idempotent protected
  tag/release finalizer, and receipts.
- `src/laconian_eval/campaign/docs_gate.py`: post-`RELEASED` synchronized documentation/social
  provenance validation.
- `src/laconian_eval/campaign/evaluation_stage.py`: authority-bound, in-process sample-audit,
  seal-audit, and analyze-plus-verify stage composition.
- `tools/benchmark_minimal_publisher.py`: standard-library-only publisher executable used by the
  write-capable job.
- `tools/benchmark_release_finalizer.py`: standard-library-only result-tag/release executable.
- `tools/benchmark_prepare_correction.py`: fixed correction-bundle and correction-plan preparation
  executable.
- `tools/benchmark_sample_audit_stage.py`: fixed authority-bound audit-sample executable.
- `tools/benchmark_seal_audit_stage.py`: fixed authority-bound audit-sealing executable.
- `tools/benchmark_analyze_stage.py`: fixed authority-bound analyze-plus-verify executable.
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
- `tests/campaign/test_evaluation_stage.py`
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
- `.github/workflows/benchmark-publication-state.yml`
- `.github/workflows/benchmark-release.yml`
- `.github/workflows/benchmark-docs-validate.yml`

### Modify

- `src/laconian_eval/campaign/__init__.py`: export only stable Slice 4 record types.
- `src/laconian_eval/campaign/cli.py`: extend the Slice 3 `laconian-campaign` entry point with
  secret-free Slice 4 preparation and validation commands.
- `tests/campaign/test_cli.py`: extend the Slice 3 CLI contract without replacing its six commands.
- `tests/campaign/test_workflow_policy.py`: extend the repository-wide workflow security contract.
- `tests/test_public_contract.py`: extend the cumulative stable export and command-ownership
  contract through Slice 4.
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
fields, a non-`workflow_dispatch` event, a branch ref, a non-SHA action workflow hash, an
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

`input_ref` must match `refs/tags/benchmark-input-[0-9]{8}\.[1-9][0-9]*`. Environment, deployment,
and approval fields are either all null or all populated. Each nonnull environment requires its
exact deployment/approval evidence. `benchmark-live` remains the distinct provider boundary.
`benchmark-publish` hosts separately approved jobs whose credentials identify distinct publisher
and release-finalizer Apps. State-writer jobs have a null environment and a distinct App identity in
their authority envelope; `benchmark-state` and `benchmark-release` environments are forbidden.
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

Preserve `cache_write_tokens`, `cache_write_accounting`, the derived nonoverlapping uncached-input
count, and cache-write charge/reservation evidence distinctly in every generation/judge reference
and `cache_write_usage_root_sha256`. Reject folding writes into cached reads, treating missing write
detail as zero, or publishing a spend total that does not reproduce from the four price components.
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
and `seal-judge` owns the exact `provider-evidence-index.json`. The workflow resolves all six files
and four complete roots from numeric artifact locators. It first calls
`load_authority_verified_generation_context(...)`, which reconstructs the retained predecessor and
final `GENERATION_COMPLETE` authority roots and returns a
`VerifiedGenerationContextIndexV1` whose `.expectation` is the only in-memory
`VerifiedGenerationContextExpectationV1`. It then calls
`load_verified_benchmark_provider_evidence(generation_expectation=verified_context.expectation,
provider_index_path=..., generation_root=..., hard_score_root=...,
judge_request_root=..., judge_root=...)` exactly once and passes the returned immutable object here.
No raw file, nested provider-index field, digest, workflow input, or CLI option may construct that
verified expectation. This function accepts neither root-path tuples nor a provider-index path.

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
substituted context/index or a hash copied from `C1`/mutable `main` fails.

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
tree, checksum, absence-of-performance-layer, and no-follow verification and is the only invalid
claim-evidence object accepted by the docs gate. Export both the type and loader.

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

### Task 7: Add secret-free staged evaluation, evidence, and collector workflows

**Files:**
- Create: `.github/workflows/benchmark-hard-score.yml`
- Create: `.github/workflows/benchmark-evidence.yml`
- Create: `.github/workflows/benchmark-audit.yml`
- Create: `.github/workflows/benchmark-analysis.yml`
- Create: `.github/workflows/benchmark-collect-complete.yml`
- Create: `.github/workflows/benchmark-finalize-invalid.yml`
- Create: `.github/workflows/audit-pr-validate.yml`
- Create: `src/laconian_eval/campaign/evaluation_stage.py`
- Create: `tools/benchmark_sample_audit_stage.py`
- Create: `tools/benchmark_seal_audit_stage.py`
- Create: `tools/benchmark_analyze_stage.py`
- Create: `tools/validate_audit_pr.py`
- Modify: `src/laconian_eval/campaign/cli.py`
- Modify: `tests/campaign/test_cli.py`
- Create: `tests/campaign/test_publication_workflows.py`
- Create: `tests/campaign/test_evaluation_stage.py`
- Create: `tests/campaign/test_audit_pr.py`
- Modify: `tests/campaign/test_workflow_policy.py`
- Modify: `tests/test_ci_contract.py`
- Modify: `tests/test_public_contract.py`

- [ ] **Step 1: Write failing workflow-policy tests**

Require the six staged evidence/collector workflows to have only `workflow_dispatch`, no inputs, top-level
`permissions: {}`, `concurrency.group: laconian-public-benchmark-state`,
`cancel-in-progress: false`, exact
detached-tag verification, `ubuntu-24.04`, `persist-credentials: false`, 90-day artifact retention,
and only full-SHA action refs. Forbid `OPENAI_API_KEY` and every `secrets.` expression except the
three state-App repository secrets mapped only in a fixed hashed state-writer step,
`pull_request_target`, `workflow_run`, `schedule`, `push`, name-based artifact download, and
repository `GITHUB_TOKEN` write permissions. A final narrow `state-writer` job has only
`actions: read` and `contents: read`, executes the Slice 3 hashed state writer with the dedicated
state-App credentials, and can only non-force fast-forward the
exact canonical authority ref from its expected OID. Require every download to resolve an `ExactArtifactLocatorV1` from numeric
repository/run/attempt/job/artifact/deployment identities and then compare the service and payload
digests.

Require the three fixed Slice 4 stage tools to import only
`laconian_eval.campaign.evaluation_stage`, never `laconian_eval.benchmark.cli`. Their campaign-side
module reconstructs authority, obtains the in-memory Runtime-verified generation expectation,
requires the retained judge/provider roots and provider-index digest, and only then calls neutral
Evaluation Task 8–13 loaders/builders directly. Static workflow tests reject every live
`laconian-benchmark` invocation, all raw identity/hash/mode options, and any attempt to serialize the
verified wrapper. The seven public benchmark commands remain offline/non-evidentiary replay only.

Every secret-free compute job declares only `contents: read` and `actions: read`; the audit job also
declares `pull-requests: read`, and jobs that re-fetch environment deployment/approval evidence
additionally declare `deployments: read`. No permission is inherited from workflow scope. The final
state-writer declares exactly `actions: read` and `contents: read`, consumes a same-run candidate
package by numeric identity, and has no deployment, PR, checks, release, or provider capability in
its repository token. Its short-lived App token is permission-attested and accepted by the
authority-ref ruleset only.

As a prerequisite regression, parse Slice 3's `benchmark-preflight.yml` and `benchmark-batch.yml` in
the same policy suite. Require immutable protected-tag preflight, the shared literal concurrency
group, and the literal `${{ secrets.OPENAI_API_KEY }}` exactly once under `env` of the single
repository-owned `laconian-campaign run-batch` step. It must be absent from workflow/job scope,
checkout/setup/download/upload, post-controller, and `always()` steps. Slice 4 does not modify
those workflows.

Require `audit-pr-validate.yml` to run a stable job named `audit-pr-validate` on every
`pull_request` event, `pull_request_review` type `submitted|dismissed`, and `merge_group`, with no
top-level path filter, read-only permissions, no secret, and trusted-base code. Review events must
resolve and validate their exact PR/head rather than trust event text, so both required signoffs
cause a fresh check run. It returns an explicit successful no-op when the diff has no path
under `benchmarks/audits/**`; this keeps the required check present on result, docs, and unrelated
PRs.
Its job declares exactly `contents: read` and `pull-requests: read`.

Pin exactly:

```text
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d
actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_audit_pr.py tests/campaign/test_workflow_policy.py tests/test_ci_contract.py -q`

Expected: FAIL because the seven workflow files, three fixed stage tools, campaign-side stage
module, and audit validator are absent.

- [ ] **Step 3: Add fixed CLI commands**

Extend the existing Slice 3 `laconian-campaign` parser with only the four secret-free Slice 4
subcommands and fixed option names:

```text
fetch-artifact --locator-json --output-zip
seal-provider-evidence --authority-root --artifact-root --output-root
collect-complete --authority-root --artifact-root --output-root
finalize-invalid-prefix --authority-root --artifact-root --output-root
```

Use `argparse.ArgumentParser(allow_abbrev=False)`, exclusive output creation, stable content-free
errors, canonical JSON stdout, and no shell/model/command/model-ID input. Preserve the six Slice 3
commands `preflight`, `reconstruct-authority`, `prepare-batch`, `consume-receipt`, `run-batch`, and
`apply-event`. The two publication/release write-capable operations remain only in the separately hashed
`tools/benchmark_minimal_publisher.py` and `tools/benchmark_release_finalizer.py` executables.
Extend `tests/test_public_contract.py` to pin the ten-command intermediate surface and exact
workflow/module owners. Tasks 8, 10, 11, and 13 add their commands only after each owning handler
exists; Task 13 pins the final sixteen-command surface.

- [ ] **Step 4: Implement hard-score, evidence, audit, and analysis orchestration**

Each workflow checks `github.ref_type == 'tag'`, the input-tag grammar, and `github.sha` against the
Slice 3 campaign authority before retrieving exact artifacts. The live hard-score/prepare-judge
pair uses the Runtime-owned fixed campaign-side tool below so the authority-verified
generation-context capability remains in-process; Runtime's final judge-batch post step has already
used the sibling fixed seal-judge tool before `JUDGE_COMPLETE`. The remaining live evidence stages
use the three Slice 4-owned fixed campaign-side tools below; none invokes the public replay CLI.
No workflow interpolates an artifact field into a shell command:

```text
uv run python tools/benchmark_hard_score_stage.py --authority-root AUTHORITY --generation-index GENERATION_INDEX --generation-root GENERATION --hard-score-output-root HARD --judge-request-output-root REQUESTS
uv run python tools/benchmark_sample_audit_stage.py --authority-root AUTHORITY --generation-index GENERATION_INDEX --provider-index PROVIDER_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-root JUDGES --output-root AUDIT_SAMPLE
uv run python tools/benchmark_seal_audit_stage.py --authority-root AUTHORITY --generation-index GENERATION_INDEX --provider-index PROVIDER_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-root JUDGES --review-root REVIEWS --repository-root REPO --output-root AUDIT
uv run python tools/benchmark_analyze_stage.py --authority-root AUTHORITY --generation-index GENERATION_INDEX --provider-index PROVIDER_INDEX --generation-root GENERATION --hard-score-root HARD --judge-request-root REQUESTS --judge-root JUDGES --audit-root AUDIT --output-root RESULT
```

Every uppercase output above is a distinct freshly absent root. `HARD` and `REQUESTS` are uploaded
and later retrieved as separate exact numeric artifacts; commands never reuse an existing output
root or point an output at one of their inputs.

Every stage tool uses `allow_abbrev=False`, accepts only the exact path options shown, and delegates
immediately to its campaign-side module. The Runtime-owned hard-score tool calls
`campaign.benchmark_stage`; the three Slice 4 tools call `campaign.evaluation_stage`. No tool
accepts an expected digest, authority-root hash, campaign/model/protocol/workflow identity, mode
scalar, arbitrary command, or output filename. `load_authority_verified_provider_evidence`
reconstructs the retained `GENERATION_COMPLETE` predecessor/final roots and current authority,
calls `load_authority_verified_generation_context`, requires the accepted judge/provider-index
digest and all four roots, and passes its in-memory
  `VerifiedGenerationContextExpectationV1` explicitly into
`load_verified_benchmark_provider_evidence`. It exact-compares the provider index's nested
expectation, predecessor/final authority roots, context digest, tagged
`statistics_protocol_sha256`, and workflow root; it never treats those serialized fields as a
capability. `run_sample_audit_stage`, `run_seal_audit_stage`, and
`run_analyze_and_verify_stage` call the neutral Task 8–13 APIs directly and fresh-reload their
outputs with that same verified provider object. The first two require exact state
`PROVIDER_EVIDENCE_VERIFIED` and the retained evidence-inventory/provider-index binding; the
analyze stage requires exact state `AUDIT_COMPLETE`, resolves the audit root only from the accepted
`AUDIT_SEALED` event and numeric artifact locator, and byte-compares the freshly loaded audit
digest with that event before analysis. It calls `aggregate_verified_evidence`,
`analyze_campaign`, `build_bootstrap_artifact`, `write_analysis_evidence_root`, and
`load_verified_analysis_evidence` in one process, requiring
`CampaignAnalysisV1.statistics_protocol_sha256` to equal that authority-derived value before
returning success. Static workflow tests reject raw
`laconian-benchmark` invocations for all seven live stages and reject any import of
`laconian_eval.benchmark.cli` from campaign code or fixed tools.

`run_seal_audit_stage` never selects a prior Actions artifact or accepts a sample-root option. It
deterministically rederives the exact population and sample from the same authority-verified
provider evidence into an operation-owned temporary root, fresh-loads it, and requires its root,
manifest, packet, population, and provider-parent hashes to equal every merged commitment, reveal,
adjudication, and signoff binding. Only then does it pass that private path as
`source_sample_root` to `write_audit_evidence_root`; success or failure removes only the validated
temporary root. Tests repeat sampling under varied filesystem enumeration, prove byte-identical
rederivation after an earlier sample artifact has expired, reject cross-sample reviews, and reject
any caller-selected sample path.

`benchmark-hard-score.yml` alone accepts `GENERATION_COMPLETE`. Its one fixed stage-tool invocation
first seals all 36
`HardScoreRequestSetV1` files, then runs `prepare-judge` from only those sealed sets and the
verified scored capsules plus the exact `GENERATION/generation-context.json` retained from Slice 3.
Its read-only prepare step reconstructs canonical authority and re-fetches the exact
`GENERATION_COMPLETE` evidence binding for the generation layer root and
`GenerationContextIndexV1` digest. It keeps that fixed authority-derived expectation alongside
`GENERATION_INDEX` while calling both neutral builders in-process; no workflow input, event scalar, or operator flag may
choose an expected digest. The loader rejects a context/generation index that is internally
self-consistent but differs from the authority-bound digest.
It applies `HARD_SCORE_SET_SEALED` only after the 36-entry
`JudgeRequestAttachmentV1` index re-verifies, producing `HARD_SCORE_COMPLETE`.
Slice 3 judge-batch preparation consumes that exact index and binds its hash in `BatchPlanV1`.
Runtime's fixed seal-judge stage tool already emitted the exact four-root-bound
`provider-evidence-index.json`; the accepted judge completion and artifact inventory bind that
digest and exact locator. `benchmark-evidence.yml` alone accepts `JUDGE_COMPLETE`, reconstructs
authority, retrieves and re-verifies those sealed JUDGES bytes without resealing, then calls
`laconian-campaign seal-provider-evidence`, and applies
`EVIDENCE_INVENTORY_SEALED`, producing `PROVIDER_EVIDENCE_VERIFIED`.

`benchmark-audit.yml` may create the deterministic blind packet while authority remains
`PROVIDER_EVIDENCE_VERIFIED`; packet creation is explicitly not a state transition. Only after it
verifies the exact commitment PRs, reveal PRs, adjudication PR, actor separation, merge SHAs, and
the output of `tools/benchmark_seal_audit_stage.py` may it apply `AUDIT_SEALED`, producing
`AUDIT_COMPLETE`. `benchmark-analysis.yml` alone accepts `AUDIT_COMPLETE`, runs the exact
analyze-plus-verify stage tool above, reloads the result through
`load_verified_analysis_evidence`, and
applies `ANALYSIS_SEALED`, producing `ANALYSIS_COMPLETE`.

Implement `tools/validate_audit_pr.py` against separately checked-out trusted base and candidate
trees. For commitment PRs it verifies exact preregistered numeric actor/login, required verified
commit signature and configured fingerprint, one new immutable commitment path, schema and sample
bindings, and absence of any reveal. For reveal PRs it proves both commitments are already ancestors
of base, recomputes the actor's commitment byte-for-byte, verifies complete unique labels, and
permits only that reviewer's new reveal paths. For adjudication PRs it proves both reveal merges are
ancestors, verifies `AuditAdjudicationCoreV1`, both independent sign-off proofs, exact actor/review
provenance, and append-only ordering. Changed old paths, premature stages, mixed roles, self-signoff,
missing review/signature bytes, or an unregistered actor fail. The same logic runs before merge in
`audit-pr-validate`; `benchmark-audit.yml` re-verifies the merged chain before sealing it.

`benchmark-collect-complete.yml` accepts only `ANALYSIS_COMPLETE` and applies
`COMPLETE_BUNDLE_SEALED`; `benchmark-finalize-invalid.yml` accepts only `STOPPED_INVALID` or
`BUDGET_INCOMPLETE` and applies `INVALID_PREFIX_SEALED`. Every other source state/event pair must
fail before artifact upload or state mutation. Every accepted event becomes a candidate package;
only the narrow Slice 3 state writer may advance the canonical authority ref, and a stale remote head
fails closed.

- [ ] **Step 5: Run workflow and CLI GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_evaluation_stage.py tests/campaign/test_audit_pr.py tests/campaign/test_workflow_policy.py tests/campaign/test_cli.py tests/test_ci_contract.py tests/test_public_contract.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` enumerates exactly the three Runtime benchmark
workflows plus these seven Slice 4 workflows (ten total); later tasks cumulatively update the same
test to 13, 14, and finally 15 rather than expecting not-yet-created workflows here.

Run: `uv run laconian-campaign --help`

Expected: exit 0 and list the six locked Slice 3 commands plus the four Slice 4 commands above.

- [ ] **Step 6: Commit secret-free evidence and collection workflows**

```bash
git add .github/workflows/benchmark-hard-score.yml \
  .github/workflows/benchmark-evidence.yml \
  .github/workflows/benchmark-audit.yml \
  .github/workflows/benchmark-analysis.yml \
  .github/workflows/benchmark-collect-complete.yml \
  .github/workflows/benchmark-finalize-invalid.yml \
  .github/workflows/audit-pr-validate.yml \
  src/laconian_eval/campaign/evaluation_stage.py \
  tools/benchmark_sample_audit_stage.py \
  tools/benchmark_seal_audit_stage.py \
  tools/benchmark_analyze_stage.py \
  tools/validate_audit_pr.py \
  src/laconian_eval/campaign/cli.py \
  tests/campaign/test_cli.py \
  tests/campaign/test_publication_workflows.py \
  tests/campaign/test_evaluation_stage.py \
  tests/campaign/test_audit_pr.py \
  tests/campaign/test_workflow_policy.py \
  tests/test_ci_contract.py \
  tests/test_public_contract.py
git commit -m "ci: orchestrate secret-free benchmark evidence stages"
```

### Task 8: Define and construct `PublicationPlanV1`

**Files:**
- Create: `src/laconian_eval/campaign/publication.py`
- Create: `tools/benchmark_prepare_correction.py`
- Create: `tests/campaign/test_publication_plan.py`
- Modify: `src/laconian_eval/campaign/collector.py`
- Modify: `src/laconian_eval/campaign/public_projection.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `src/laconian_eval/campaign/cli.py`
- Modify: `tests/campaign/test_cli.py`
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
    defect_class: Literal["publication_metadata", "release_metadata"]
    defect_code: Literal[
        "publication_object_metadata_diverged",
        "release_object_metadata_diverged",
        "release_finalization_interrupted",
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
    immutable_release_attestation_sha256: Sha256 | None
    evidence_sha256: Sha256


class LatestPublicationPointerV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    correction_sequence: StrictNonNegativeInt
    publication_id: BoundedNonBlankString
    release_status: Literal["released", "release_blocked"]
    bundle_kind: Literal["complete", "invalid_prefix"]
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
    stage: Literal[
        "defect_accepted", "publication_invalidated", "publication_open", "merged"
    ]
    publication_invalidation_sha256s: tuple[Sha256, ...]
    current_publication_attempt: StrictPositiveInt
    current_publication_plan_sha256: Sha256 | None
    current_publication_receipt_sha256: Sha256 | None
    current_merge_receipt_sha256: Sha256 | None
    progress_sha256: Sha256


class CorrectionLineageV1(CapsuleModel):
    schema_version: Literal["1"]
    source_campaign_state: Literal["RELEASED", "RELEASE_BLOCKED"]
    correction_sequence: StrictPositiveInt
    defect_record_sha256: Sha256
    supersedes_pointer_sha256: Sha256
    supersedes_release_status: Literal["released", "release_blocked"]
    supersedes_bundle_kind: Literal["complete", "invalid_prefix"]
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
    pull_request_title: BoundedNonBlankString
    pull_request_body_sha256: Sha256
    plan_sha256: Sha256
```

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
receipt, invalidation, close plan/receipt, and every state or terminal-evidence mutation. An accepted
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
Also reject missing/changed bundle-kind fields or a correction that changes bundle kind; an
invalid-prefix lineage cannot acquire complete analysis evidence, and a complete lineage cannot be
downgraded to hide it.

The only accepted defect source is a human-authored and reviewed file at
  `benchmarks/corrections/{campaign_id}/{N}/defect.json`, merged to `main` as a one-file PR and then
  recorded in canonical authority as a `correction_defect` terminal mutation. Its sequence and
  affected pointer are derived, not operator-selected. A defect in generation, scoring, judging,
  audit, statistical methods, source evidence, credential integrity, campaign authority, public
  projection/report rendering, or trusted code/workflow is not correctable under this lineage: fail
  closed and require a new reviewed campaign.
Require `publication_metadata` to pair only with `publication_object_metadata_diverged`; require
`release_metadata` to pair only with `release_object_metadata_diverged` or
`release_finalization_interrupted`. Unknown/free-form codes and a code/class mismatch fail before
correction authority.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_plan.py tests/campaign/test_cli.py tests/test_public_contract.py -q`

Expected: FAIL because `publication.py` does not exist.

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
path and hash into the plan. Reject a missing/duplicate/substituted path, a hash from `C1` or mutable
`main`, and a registry root that differs from the campaign package. CLI and workflow inputs expose no
workflow-identity override.

The builders likewise accept no audit-merge list from a caller. For a complete bundle, derive the
ordered full merge set from the verified audit/adjudication attachment DAG and re-fetch every exact
merge commit through canonical authority before binding `audit_merge_shas`. For an invalid-prefix
bundle, derive exactly the accepted pre-STOP audit-merge prefix (possibly empty), require no
post-STOP merge, and bind the ordered complement in `missing_suffix_sha256`. Reject a
caller/CLI override, a merely open audit PR, a merge absent from current `main`, and any order/hash
that differs from the sealed audit evidence.

The correction builder accepts only canonical authority in `RELEASED` or `RELEASE_BLOCKED` with an
append-only verified defect/correction-evidence envelope and
`CorrectionProgressV1.stage in {"defect_accepted", "publication_invalidated"}`. It re-verifies every superseded object,
requires a new bundle/result path/publication ID, and computes a diff that only adds the new result
directory. It never rewrites prior result bytes, tags, releases, receipts, or documentation markers.
Publication/merge/release workflows reuse the same protected plan and writer boundaries; correction
receipts append authority evidence without changing the terminal campaign state.

`build_corrected_bundle` is the sole correction-bundle producer. For `release_metadata` and
`publication_metadata` it permits exact byte-for-byte reuse only after the prior bundle fully
re-verifies and the defect is an external publication/release-object metadata divergence from the
already-correct sealed plan, not a code/renderer/bundle defect. It preserves bundle kind and cannot
change any bundle member, analysis value, outcome/interval, audit record, provider evidence, or
invalid-prefix claim prohibition. Both bundle kinds permit only this exact-reuse path; every public
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
`CorrectionDefectRecordV1.evidence_sha256`; the accepted `correction_defect` terminal mutation binds
the record's `record_sha256`, and `CorrectionLineageV1.defect_record_sha256` equals that same record
digest. No event hash is compared to the record self hash. It also verifies the ordered Slice 3 terminal-evidence mutation root for each
correction stage. Every security, credential, audit, provider, or unrelated invalid-event hold still
blocks correction; correction evidence never dismisses or mutates one.

`reconstruct_latest_publication_pointer` bootstraps sequence 0 from accepted state-event authority:
`RESULT_RELEASED` supplies the initial publication/merge/tag/release receipts for `RELEASED`, while
`RELEASE_PLAN_INVALIDATED` supplies the initial publication/merge, null successful-release fields,
and exact `BlockedReleaseObjectsV1` for `RELEASE_BLOCKED`. It then folds each terminal correction
group from the terminal-evidence root. A terminal group is exactly: defect; zero or more
publication-open/publication-invalidation attempt pairs; one final publication-open; merge; and
exactly one release-success or `correction_release_invalidation`. Release success creates a released
pointer; release invalidation requires phase-accurate `BlockedReleaseObjectsV1` and creates a
release-blocked pointer. The pointer advances only at one of those two terminal records.

`reconstruct_correction_progress` accepts at most one contiguous in-flight tail for exactly
`latest_pointer.correction_sequence + 1`: defect alone; defect plus completed publication-
invalidation attempt pairs; an exact current publication-open; or an exact merge. It returns the
closed `CorrectionProgressV1` stage and retains the full attempt/invalidation chain. Require
`current_publication_attempt == len(publication_invalidation_sha256s) + 1`.
`defect_accepted|publication_invalidated` require current plan/receipt/merge null;
`publication_open` requires plan/receipt and null merge; `merged` requires all three. Missing,
duplicate, gapped, reordered, two simultaneous tails, a next defect before terminalization, or a
release record before merge fail. Every legitimate persisted prefix is resumable, but never changes
the latest pointer or authorizes docs/social claims. Tests cover every prefix, repeated publication
replans, release success, and release-blocked terminalization for initial state and correction N.
The pointer, not the campaign-state name, determines
whether prior tag/release fields must exist. Publishing, merging, release failure, and release success each append
their candidate through Slice 3 `append_terminal_evidence`; only a successful correction released
from `RELEASE_BLOCKED` additionally constructs `CORRECTION_RESULT_RELEASED`.

Only after these handlers exist, add the eleventh fixed command:

```text
build-publication-plan --authority-root --bundle-root --main-repository --output-root
```

Wire it directly to the initial/correction plan builders selected from canonical authority, reject
abbreviations and operator-supplied identities, and extend CLI/public-contract tests to eleven exact
commands.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_plan.py tests/campaign/test_cli.py tests/test_public_contract.py -q`

Expected: PASS.

- [ ] **Step 6: Commit publication planning**

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/publication.py \
  src/laconian_eval/campaign/collector.py \
  src/laconian_eval/campaign/public_projection.py \
  tools/benchmark_prepare_correction.py \
  src/laconian_eval/campaign/cli.py \
  tests/campaign/test_publication_plan.py \
  tests/campaign/test_cli.py \
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

The receipt is:

```python
class PublicationReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    publication_attempt: StrictPositiveInt
    correction_lineage_sha256: Sha256 | None
    publication_plan_sha256: Sha256
    bundle_sha256: Sha256
    branch_name: BoundedNonBlankString
    base_sha: GitObjectId
    head_sha: GitObjectId
    publication_operation: Literal[
        "created_branch_and_pr", "reused_exact_branch_created_pr", "observed_exact_pr"
    ]
    pull_request_number: StrictPositiveInt
    pull_request_node_id: BoundedNonBlankString
    pull_request_url: ExactAsciiHttpUrl
    repository_id: StrictPositiveInt
    workflow_run_id: StrictPositiveInt
    run_attempt: StrictPositiveInt
    job_id: StrictPositiveInt
    job_name: Literal["publish"]
    environment: Literal["benchmark-publish"]
    deployment_id: StrictPositiveInt
    approval_actor_id: StrictPositiveInt
    approval_actor_login: BoundedNonBlankString
    publisher_app: GitHubAppInstallationIdentityV1
    opened_by: BoundedNonBlankString
    receipt_sha256: Sha256
```

Require `publisher_app.role == "publisher"`, `opened_by == publisher_app.bot_login`, and the exact
pre-registered App/installation/repository IDs and permissions-attestation hash. Reject
`github-actions[bot]`, the state/release App, or a publisher App permission response other than the
closed allowlist `actions:read`, `deployments:read`, `contents:write`,
`pull_requests:write`.

- [ ] **Step 2: Add failing authority and non-interpretation tests**

Reject a changed base, changed package/script/plan/bundle digest, unexpected ZIP/tar member, path
escape, symlink, an existing divergent remote branch, response text containing shell/HTML/Markdown payloads,
extra Git diff, PR API response with wrong head/base/actor, and any token in a child process
environment except the exact `git push` and PR POST operations. Spy on JSON parsing and assert only
the plan, bundle seal, checksums, and GitHub response are parsed. Add crash/race fixtures for loss
after branch push but before PR POST, after PR POST but before receipt write, and two recovery jobs
racing to create the one bound PR.

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
without `extractall`, verifies the plan and bundle, creates a temporary worktree at exact `base_sha`,
copies only `expected_files`, force-adds only `result_path`, verifies index/tree/head identities,
and re-fetches the exact remote branch. If absent it pushes
`proposed_head_sha:refs/heads/{branch_name}` with force disabled; if already present it proceeds only
when the ref equals `proposed_head_sha` and the base/tree/plan/bundle all reverify. It then re-fetches
the exact head/base PR and POSTs the bound PR only when none exists. It
never runs a file from the bundle and never places the token in a remote URL, log, receipt, or Git
configuration.

The only nonsecret runtime identity inputs are the fixed GitHub variables `GITHUB_REPOSITORY_ID`,
`GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_JOB`, and `GITHUB_SHA`. Before pushing, the tool
uses those numeric values to re-fetch the current job, deployment, and `benchmark-publish` approval;
it re-fetches and permission-attests its App installation, records both exact identities in
`PublicationReceiptV1`, and rejects missing/mismatched approval, actor, installation, or permissions.
It deletes the 0600 signer PEM and scrubs App variables/token before returning. Tests prove private
key/token canaries never reach logs, receipts, Git config/URL, bundle, or unrelated child processes.

- [ ] **Step 5: Add idempotent safe recovery**

If the exact branch exists without a PR, reverify every ref/tree/base/plan/bundle byte and create the
one bound PR without pushing or updating the branch. If the exact open PR already exists, perform no
write and accept it only when base, head, title, body digest, author, plan, and bundle are identical.
On a PR-POST conflict, re-fetch and accept only that exact unique PR. Emit a new
`PublicationReceiptV1` for the current recovery job with the corresponding
`publication_operation`; do not claim byte identity with a receipt from a different run/job/
deployment. The recorder/state CAS accepts exactly one fully reverified receipt. If canonical
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
- Create: `.github/workflows/benchmark-publication-state.yml`
- Create: `tools/validate_publication_pr.py`
- Create: `tests/campaign/test_publication_pr.py`
- Modify: `tests/campaign/test_publication_workflows.py`
- Modify: `tools/benchmark_minimal_publisher.py`
- Modify: `tests/campaign/test_minimal_publisher.py`
- Modify: `src/laconian_eval/campaign/publication.py`
- Modify: `src/laconian_eval/campaign/__init__.py`
- Modify: `src/laconian_eval/campaign/cli.py`
- Modify: `tests/campaign/test_cli.py`
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
`pull_request` type `opened`, `synchronize`, `reopened`, and `closed`, plus `merge_group`, without a
top-level path filter, and on `pull_request_review` type `submitted|dismissed`, with read-only
permissions and no secrets. Review events resolve the exact current PR/head before validation. It executes
`tools/validate_publication_pr.py` from the exact base checkout, never candidate code. An unrelated
diff returns a successful explicit no-op so the globally required check is never left Pending.
Its job declares exactly `contents: read` and `pull-requests: read`.

Require `benchmark-publication-state.yml` to use the shared concurrency group and trusted-base code
on the same PR events plus no-input `workflow_dispatch`. It no-ops unrelated PRs. A read-only inspect
job declares exactly `contents: read`, `actions: read`, `pull-requests: read`, and `checks: read` and
reconstructs the exact publication receipt from the canonical authority ref; a narrow
state-writer job may only non-force fast-forward that ref using the dedicated state App while its
repository token declares exactly `contents: read` and `actions: read`. Only that fixed writer step
may map the three state-App repository secrets. When an exact still-open plan is invalidated, this workflow
emits only a safe close-required summary. The same no-input `benchmark-publish.yml` and same
protected `publish` job/tool later enter their receipt-bound `close_exact_pr` mode; there is no third
write-capable close job. No job reviews, approves, merges, force-pushes, edits, or deletes result
content.
Forks, human-authored PRs, and non-result diffs can execute only the read-only no-op path; policy
tests inspect job conditions and exact head repository/actor/receipt bindings before any write token
is available.

For every manual path in both `benchmark-publish.yml` and `benchmark-publication-state.yml`, require
`github.ref_type == "tag"`, exact `benchmark-input-YYYYMMDD.N` grammar, and reverify the selected tag
object/peeled commit/registry to derive the sole campaign and
`refs/heads/benchmark-authority/{campaign_id}`. Reject default-branch dispatch, a branch, mutable ref,
or newest/by-name discovery. On PR/review/merge-group events, derive campaign/authority only from the
exact validated `PublicationReceiptV1` at the bound head; no manual selector is consulted.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_publication_pr.py -q`

Expected: FAIL because the three workflows and PR/state recorders are absent.

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
it with only publisher-App credentials. Open mode emits `PublicationReceiptV1`; close mode may only
close the one exact open PR and emits `PublicationCloseReceiptV1`, never edits branch/content. A
following read-only `record-publication` job re-fetches the PR by number/head and validates the
receipt. Initial publication creates `PUBLICATION_PR_OPENED` or
`INVALID_PUBLICATION_PR_OPENED`; correction publication appends `correction_publication`; initial
close applies the matching publication-plan invalidation only after the close receipt verifies;
correction close appends `correction_publication_invalidation`, which retains the active correction
sequence and advances only its publication attempt. A separate narrow state-writer maps only the
state-App secrets, verifies the expected authority-ref OID, and performs one non-force CAS.
`record-publication` treats a PR opened/closed without a durable receipt as a recoverable exact-plan
lookup, never as permission to create another branch or target another PR.

After the validator/recorders exist, extend `laconian-campaign` with exactly three additional
secret-free commands, bringing its locked total to fourteen:

```text
validate-publication-pr --trusted-root --candidate-root --github-event
record-publication-merge --authority-root --github-event --output-root
invalidate-publication-plan --authority-root --github-event --output-root
```

All three use trusted API records and canonical authority; none accepts a PR number, branch, head,
base, event type, or artifact selector from an operator. The commands only construct candidate
state events or terminal-evidence mutations selected from canonical source state. The Slice 3 state
writer owns the remote CAS.
Update `tests/test_public_contract.py` to require all fourteen exact command names and reject aliases.

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
`append_terminal_evidence` plus the state-App CAS to append `correction_defect`; this is the sole
entry into correction preparation. Unrelated PRs return the explicit `irrelevant` result.

Define strict `RequiredCheckEvidenceV1` for each required check with check-run ID/name,
`status == "completed"`, conclusion, head SHA, check-suite ID/event, source App numeric ID/slug,
workflow run ID/attempt, trusted workflow path/SHA-256, and evidence digest. Re-fetch check run,
suite, and Actions run by exact IDs; require the preregistered GitHub Actions source App and trusted
base workflow bytes. A same-name check from another App/workflow, a rerequested/in-progress suite,
or a run on another SHA fails even if its conclusion says success.

Define `PublicationMergeReceiptV1` binding the exact publication plan/receipt, PR number, base and
approved head, merge mode `direct|merge_queue`, nullable-as-a-set merge-group ref/SHA/base,
byte-sorted exact queue PR membership, ordered `RequiredCheckEvidenceV1` records at the approved head
for direct merge or at the merge-group SHA for queue merge, non-bot human approving review
ID/actor/commit, merge actor numeric ID/login/time/commit, recomputed merge-tree/result-tree/bundle
digests, the complete `DurableAuthorityCheckpointV1` and its digest, and its own digest. Require the
merge actor to equal a preregistered non-bot maintainer account allowed by the `main` ruleset; reject
all three benchmark Apps, the GitHub Actions App, merge bots, and an unregistered human even when the
GitHub API says the PR is merged. Merge-group fields are all required only in queue mode and the recorded queue base/head
must prove this exact PR/head was a member. `record-publication-merge` re-fetches all objects by exact IDs, requires the PR to be
merged (not merely closed), the approved head unchanged, every required check successful, the human
review current, the merge commit reachable from current `main`, and the exact result tree. Only then
does it exhaustively derive the Runtime checkpoint mapping for every transient artifact needed by
the authority DAG, re-open each mapped committed result byte from the exact merge object, and bind
that checkpoint into the initial `RESULT_MERGED` event for application to
`PUBLICATION_PR_OPEN`. An expired artifact before this accepted event is fatal; after it, only the
checkpoint's complete byte-identical mapping is an allowed reconstruction substitute. From
terminal correction authority the same command instead constructs a `correction_merge`
`TerminalEvidenceMutationV1` chained to the accepted `correction_publication` root; state name/hash
remain unchanged and its new correction checkpoint supersedes the prior durable pointer without
removing any mapping. Tests reject using either record family from the other's source state, an
incomplete/different durable mapping, and race a stale terminal-evidence/ref root.

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
`PublicationCloseReceiptV1` must verify before the state writer applies the event. In correction
mode, merge appends `correction_merge`, close/failure appends
`correction_publication_invalidation`, and neither
uses `RESULT_MERGED` or a publication state event from terminal authority. Replanning
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
CAS procedures. It forbids manually supplied PR/head/base IDs and states that release planning is
blocked until `PublicationMergeReceiptV1` has advanced canonical authority to `RESULT_MERGED`.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_publication_pr.py tests/campaign/test_minimal_publisher.py tests/campaign/test_cli.py tests/test_public_contract.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` cumulatively enumerates 13 benchmark workflows: the
three Runtime workflows, seven Task 7 workflows, and the three workflows in this task.

- [ ] **Step 7: Commit protected publication and PR validation**

```bash
git add .github/workflows/benchmark-publish.yml \
  .github/workflows/publication-pr-validate.yml \
  .github/workflows/benchmark-publication-state.yml \
  tools/validate_publication_pr.py \
  tools/benchmark_minimal_publisher.py \
  src/laconian_eval/campaign/publication.py \
  src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/cli.py \
  tests/campaign/test_minimal_publisher.py \
  tests/campaign/test_cli.py \
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
- Modify: `src/laconian_eval/campaign/cli.py`
- Modify: `tests/campaign/test_cli.py`
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
    bundle_kind: Literal["complete", "invalid_prefix"]
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

Add `RELEASED` and `RELEASE_BLOCKED` correction fixtures. Require a new immutable result directory,
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
    publication_receipt: PublicationReceiptV1,
    publication_merge_receipt: PublicationMergeReceiptV1,
    asset_root: Path,
) -> ResultReleasePlanV1:

def build_correction_release_plan(
    *,
    repository: Path,
    authority: ReconstructedAuthorityV1,
    correction_publication_plan: PublicationPlanV1,
    correction_publication_receipt: PublicationReceiptV1,
    correction_merge_receipt: PublicationMergeReceiptV1,
    correction_lineage: CorrectionLineageV1,
    asset_root: Path,
) -> ResultReleasePlanV1:
```

Neither release builder accepts a workflow path/hash scalar. Resolve only the literal
`.github/workflows/benchmark-release.yml` member from the same verified 15-member frozen `C0`
`authority.registry.workflow_inventory`, re-hash its tagged bytes, and bind the path and hash in the
release plan. Reject path/hash substitution, a `C1` or mutable-`main` workflow, inventory-root drift,
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
correction can only create its new sequence-specific tag/release.

- [ ] **Step 5: Implement the standard-library-only release finalizer**

`tools/benchmark_release_finalizer.py` accepts only package ZIP, repository, and receipt path. The
package contains the exact finalizer plus the hash-bound shared `github_app_auth.py`; the tool reads
only fixed step-scoped `RELEASE_APP_ID`, `RELEASE_APP_INSTALLATION_ID`, and
`RELEASE_APP_PRIVATE_KEY`, mints a short-lived installation token, verifies the closed release-App
  permission response, and scrubs all signer/token material. It verifies the package and plan;
  independently rebuilds the exact annotated-tag bytes, requires its object ID to equal
  `expected_tag_object_sha`, creates that one tag object/ref, creates one exact draft/non-prerelease
  GitHub Release, uploads and re-fetches the two assets, compares returned digest/size/name/media
  fields, and only then performs the single plan-bound `draft: true -> false` publication transition.
  It re-fetches the now-published immutable release and its repository immutable-release attestation
  before emitting a receipt. No other release edit exists.

Return:

```python
class ResultReleaseReceiptV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    publication_id: BoundedNonBlankString
    correction_lineage_sha256: Sha256 | None
    release_plan_sha256: Sha256
    bundle_kind: Literal["complete", "invalid_prefix"]
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
    immutable_release_attestation_sha256: Sha256
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
allowlist `actions:read`, `deployments:read`, and `contents:write` (whose reachable surface includes
the required new-tag/release/asset endpoints). Derive
`published_at_utc` only by re-fetching the created/existing GitHub release; reject a naive,
noncanonical, caller-supplied, or workflow-clock timestamp.

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
receipt and all immutable external objects; racing receipts cannot trigger another external update.
On every non-idempotent failure, re-fetch the bounded tag/release/asset set and emit a safe
`BlockedReleaseObjectsV1`; the state transition/terminal mutation binds it before any correction can
be planned. Orphan objects are immutable evidence and are never deleted or reused.

Before the first tag API call it uses the same fixed GitHub runtime identity variables as the
publisher, re-fetches the numeric `release-finalizer` job, deployment, and separate
`benchmark-publish` approval, calls the authority/hold verifier bound by the plan, re-fetches and
attests the release App, re-fetches the immutable-Releases repository setting and exact trust-
boundary record, and records both authorizations in `ResultReleaseReceiptV1`. Repository
`GITHUB_TOKEN` is read-only and is never the release actor.

Only after release handlers exist, add the fifteenth fixed command:

```text
build-release-plan --authority-root --result-root --github-event --output-root
```

It selects initial/correction construction only from verified authority and lineage, accepts no tag,
release, PR, merge, or asset identity override, and is pinned by CLI/public-contract tests.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_result_release.py tests/campaign/test_cli.py tests/test_public_contract.py -q`

Expected: PASS.

- [ ] **Step 7: Commit result release planning and finalization**

```bash
git add src/laconian_eval/campaign/__init__.py \
  src/laconian_eval/campaign/release.py \
  tools/benchmark_release_finalizer.py \
  src/laconian_eval/campaign/cli.py \
  tests/campaign/test_result_release.py \
  tests/campaign/test_cli.py \
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
`release-finalizer`; a read-only `record-release`; and a narrow `state-writer`. The gated job has
exactly `actions: read`, `deployments: read`, and `contents: read` on its repository token, one
repository-owned `run` step, step-scoped release-App ID/installation/private key plus a
`GITHUB_READ_TOKEN` used only for the numeric package GET and unset before finalization, no provider
secret, no checkout/setup/action step, and no generic release edit/delete command; the hash-bound
finalizer alone may issue its one exact draft-to-published PATCH after asset verification. The state writer has
exactly `actions: read` and `contents: read`, maps only the state-App repository secrets in its fixed
step, and can only non-force fast-forward the canonical authority ref. No repository
`GITHUB_TOKEN` can write.

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/campaign/test_publication_workflows.py -q`

Expected: FAIL because `.github/workflows/benchmark-release.yml` is absent.

- [ ] **Step 3: Implement the release workflow**

Trigger only with no-input `workflow_dispatch` from the immutable input tag. Use the shared
`laconian-public-benchmark-state` concurrency group. For an initial release,
`prepare-release` proves exact `RESULT_MERGED`; for a correction, it proves the terminal
`RELEASED|RELEASE_BLOCKED` state plus
`reconstruct_correction_progress(authority).stage == "merged"` and the exact append-only correction
publication/merge lineage. It checks
current PR/merge/tree/security state, builds the release plan/assets/finalizer package, and uploads
it for 90 days. `release-finalizer` downloads by numeric artifact ID, verifies the exact hashed
script and App-auth helper, and executes them with only the release-App credentials.
`record-release` re-fetches all GitHub objects and emits a receipt-bound candidate only after
verification. It derives the released `DurableAuthorityCheckpointV1` by extending the exact merged
checkpoint with the annotated tag object/target, immutable-release attestation, and both verified
asset digests; it re-verifies that every prior transient mapping remains present byte-for-byte. For
the initial release, `state-writer` binds that checkpoint into and applies `RESULT_RELEASED` from
`RESULT_MERGED`. For a correction it calls Slice 3 `append_terminal_evidence` with the expected
terminal-evidence root and authority-ref OID. A correction
from `RELEASED` appends the verified correction-release mutation while state remains `RELEASED`; a
correction from `RELEASE_BLOCKED` packages that mutation followed by
`CORRECTION_RESULT_RELEASED` through Slice 3
`append_terminal_evidence_then_event`, and the state writer installs both ordered envelopes from
that one `AuthorityMutationV1` in one authority commit/remote CAS,
ending at `RELEASED`; the correction-release evidence/event binds the superseding released
checkpoint. A divergent release
emits `RELEASE_PLAN_INVALIDATED`, which the state writer applies as `RELEASE_BLOCKED` only from
`RESULT_MERGED`; terminal correction failures append invalid correction evidence without rewriting
prior state or result objects. That terminal evidence kind is exactly
`correction_release_invalidation`; it is legal only after the active correction's verified merge,
requires `BlockedReleaseObjectsV1`, terminalizes the in-flight correction as a new
`release_blocked` latest pointer, and advances correction sequence. It is distinct from
`correction_publication_invalidation`, which never advances the pointer or sequence.

- [ ] **Step 4: Test failed and replayed finalization**

Add workflow fixture cases for failure before tag creation, tag created before runner loss, draft
created before asset upload, each partial asset state, both assets verified before publication,
publication before receipt upload, and exact rerun. Only byte-identical tags/drafts/assets or an
already published immutable release may recover. A divergent draft/published object, mutable-release
setting, incomplete released checkpoint, or failed immutable attestation emits
`RELEASE_PLAN_INVALIDATED` with exact `BlockedReleaseObjectsV1` and no result rewrite.

- [ ] **Step 5: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_publication_workflows.py tests/campaign/test_result_release.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` cumulatively enumerates 14 benchmark workflows.

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
- Modify: `src/laconian_eval/campaign/cli.py`
- Modify: `tests/campaign/test_cli.py`
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
Run the same matrix for an `invalid_prefix` release: accept only synchronized operational-status and
limitations blocks derived from `VerifiedInvalidPrefixBundleV1`; reject a complete-analysis object,
missing completed/missing/incident evidence, or even a qualitative model/arm comparison. Conversely,
reject invalid-prefix evidence for a `complete` release and reject any bundle-kind/hash disagreement
between plan, receipt, committed tree, marker, and claim evidence.

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
PostReleaseClaimEvidenceV1 = VerifiedAnalysisEvidenceV1 | VerifiedInvalidPrefixBundleV1


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
`CORRECTION_RESULT_RELEASED` transition. Require `release_plan.bundle_kind`, receipt bundle kind/hash,
and the runtime claim-evidence variant to agree. The `complete` variant verifies receipt, committed
bundle, correction lineage where present, tag, immutable release, and analysis parent hashes; parses
only explicit markers/bounded result sections; and compares every numeric or qualitative benchmark
claim with the machine summary. The `invalid_prefix` variant verifies the sealed completed-prefix,
missing-suffix, incident, registry/state/ledger, release, and absence-of-performance-layer proofs; it
forbids every model/arm performance number, comparison, direction, pass/fail quality claim, effect,
interval, ranking, or savings statement and permits only bounded operational status, incident code,
missing-work, provenance, and limitations text. No null/fabricated analysis is accepted. Both variants
require all six localized READMEs plus evaluation docs, site, changelog, release note, presentation
source, and dated social package to name the same campaign/publication/bundle/tag and visible bundle
kind.

- [ ] **Step 5: Implement the PR workflow and runbook**

`benchmark-docs-validate.yml` runs the stable job `benchmark-docs-validate` on every `pull_request`
and `merge_group`, without a top-level path filter; has read-only permissions; checks out base and
candidate separately; and executes trusted-base `tools/validate_result_docs.py`. It returns an
explicit successful no-op when none of the synchronized result, release, social, presentation, or
result-shaped Markdown/HTML paths changed, so the required check is always present.
Its job declares exactly `contents: read` and `pull-requests: read`.
At this final workflow checkpoint, make `tests/test_ci_contract.py` assert that its 15 exact workflow
paths equal Runtime's `BenchmarkWorkflowInventoryV1` production path constant, then build/reverify
the inventory from the trusted tree and require every full-SHA pin/policy hash. This is the deferred
real cross-slice check; Runtime Task 2 used only synthetic files at those fixed paths.

Only after `docs_gate.py` and the trusted wrapper exist, add the sixteenth and final fixed command:

```text
validate-result-docs --trusted-root --candidate-root --github-event
```

Wire it directly to `verify_post_release_docs`, reject abbreviations/identity overrides, and make
CLI/public-contract tests require exactly the final sixteen names.

The runbook must contain the exact repository settings checklist below, operator commands for
complete and invalid publication, exact-head workflow approval, merge verification, release
approval, recovery/invalidation branches, artifact-expiry warning, and key-revocation/incident
steps. It must say that documentation/social work begins only after canonical
`CampaignStateV1.state == "RELEASED"`, the accepted `RESULT_RELEASED` or
`CORRECTION_RESULT_RELEASED` evidence, immutable receipt, and latest-publication pointer all verify.

- [ ] **Step 6: Run focused GREEN checks**

Run: `uv run pytest tests/campaign/test_docs_gate.py tests/campaign/test_publication_workflows.py tests/campaign/test_cli.py tests/test_public_contract.py tests/test_site.py -q`

Expected: PASS.

At this checkpoint `tests/test_ci_contract.py` enumerates all 15 benchmark workflows: three Runtime
and twelve Slice 4 workflows.

- [ ] **Step 7: Commit the post-release gate and operator documentation**

```bash
git add src/laconian_eval/campaign/docs_gate.py \
  tools/validate_result_docs.py \
  .github/workflows/benchmark-docs-validate.yml \
  tests/campaign/test_docs_gate.py \
  tests/campaign/test_publication_workflows.py \
  src/laconian_eval/campaign/cli.py \
  tests/campaign/test_cli.py \
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
the same handlers and fixed campaign-side stage tools as the workflows: Runtime hard-score/
prepare-judge and `HARD_SCORE_SET_SEALED`; Slice 3 judge execution plus the fixed seal-judge stage
through `JUDGE_COMPLETE`; provider-evidence verification and `EVIDENCE_INVENTORY_SEALED`;
Publication `run_sample_audit_stage` with no state jump; both commitment/reveal chains and
adjudication; `run_seal_audit_stage` plus `AUDIT_SEALED`;
`run_analyze_and_verify_stage` through `tools/benchmark_analyze_stage.py`, then
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
merge and release the safe registry/incident bundle, and prove no generation/judge/audit/analysis or
performance claim enters the tree. Run the post-release docs gate with
`VerifiedInvalidPrefixBundleV1`, accept synchronized operational-status/limitations copy, and reject
null/fabricated analysis or any numeric/qualitative model comparison.

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/campaign/test_publication_reconstruction.py -q`

Expected: FAIL until the fixture connects every Slice 4 interface and state event.

- [ ] **Step 4: Complete the deterministic offline fixture**

Use no network, provider key, current time, random UUID, mutable branch lookup, or host-private path.
Freeze repository ID and trust-boundary/settings records; the run, attempt, job, deployment,
approval, and artifact IDs for every hard-score/evidence/audit/analysis/collection/publication/release
stage; canonical timestamps; API JSON; Git author/tagger identity; deterministic USTAR bytes;
draft/upload/publish/immutable-release responses; and result assets in `publication_helpers.py`.
Make `fake_github.py` reject every endpoint outside the exact GET/POST/PATCH set used by the readers,
publisher, and finalizer.

- [ ] **Step 5: Run both reconstructions twice**

Run:

```bash
uv run pytest tests/campaign/test_publication_reconstruction.py -q
uv run pytest tests/campaign/test_publication_reconstruction.py -q
```

Expected: PASS twice with identical asserted bundle, publication-plan, proposed-head, release-plan,
tag-object, merged/released durable-checkpoint, immutable-release-attestation, and receipt hashes.

- [ ] **Step 6: Commit offline publication reconstruction**

```bash
git add tests/campaign/test_publication_reconstruction.py \
  tests/campaign/publication_helpers.py \
  tests/campaign/fake_github.py
git commit -m "test: reconstruct benchmark publication offline"
```

### Task 15: Run the complete Slice 4 and repository verification

**Files:**
- Verify only; fix failures in their owning task and commit those fixes separately.

- [ ] **Step 1: Run Slice 4 tests**

```bash
uv run pytest \
  tests/campaign/test_github_records.py \
  tests/campaign/test_artifacts.py \
  tests/campaign/test_provider_evidence.py \
  tests/campaign/test_public_projection.py \
  tests/campaign/test_complete_collector.py \
  tests/campaign/test_invalid_prefix_finalizer.py \
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

- [ ] **Step 2: Run workflow/public contract tests**

```bash
uv run pytest \
  tests/test_ci_contract.py \
  tests/test_public_contract.py \
  tests/test_site.py \
  tests/test_release_bundle.py -q
```

Expected: PASS.

- [ ] **Step 3: Run all repository quality gates**

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
git diff --check
```

Expected: every command exits 0; `git diff --check` prints nothing.

- [ ] **Step 4: Review the workflow diff manually**

Run:

```bash
git diff -- .github/workflows tools src/laconian_eval/campaign tests/campaign
```

Expected: no floating action ref, no provider secret in Slice 4, no privileged automatic trigger,
no workflow/job-level secret mapping, no name-based artifact retrieval, no repository
`GITHUB_TOKEN` write, and no approval or merge operation. The only secret expressions are the three
state-App names in fixed authority-writer steps and the role-matched three publisher/release-App
names in their respective protected job. App writes match the enumerated state-ref, result-PR, and
new-tag/release roles exactly.

- [ ] **Step 5: Correct failures only in their owning task**

If a verification command fails, return to the task that owns the failing file, make the smallest
correction, rerun that task's exact GREEN command, and use that task's explicit `git add` and commit
step. Do not create a catch-all verification commit and never use `git add .`.

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
  administrator bypass, restrict deployments to `benchmark-input-*` tags, and configure no provider
  secret.
- [ ] Register three distinct GitHub Apps installed only on this repository and record their numeric
  App/installation IDs, exact slugs/bot logins, repository ID, permission response, permissions-
  attestation hash, creation owner, rotation owner, and private-key fingerprint. Require pairwise
  distinct IDs/installations/bot logins/private keys:
  - state writer: metadata read plus `contents: write`; no actions/deployments/PR/checks permission.
    Because `contents:write` also makes Git reference and release endpoints technically reachable,
    its fixed hashed tool may call only expected-OID CAS on `benchmark-authority/*`; result-tag rules,
    immutable Releases, endpoint-policy tests, and before/after inventories detect any other use;
  - publisher: metadata read, `actions: read`, `deployments: read`, `contents: write`, and
    `pull_requests: write`; no checks/administration permission. These permissions technically expose
    review/merge and release endpoints, but the fixed tool never calls them, result-tag rules and
    immutable Releases bound the release surface, the result validator accepts only a preregistered
    non-bot maintainer review, and the `main` ruleset excludes the App from merge;
  - release finalizer: metadata read, `actions: read`, `deployments: read`, and `contents: write` for
    new tag/release/assets; no pull-request/checks/reviews/administration permission.
- [ ] Store `STATE_WRITER_APP_ID`, `STATE_WRITER_APP_INSTALLATION_ID`, and
  `STATE_WRITER_APP_PRIVATE_KEY` as repository Actions secrets referenced only by fixed trusted
  state-writer steps. Store the analogous `PUBLISHER_*` and `RELEASE_*` triples only in
  `benchmark-publish`; expression-location policy tests ensure each protected job maps only its own
  role. Do not create `benchmark-state` or `benchmark-release` environments. Rotate any key that was
  exposed outside its intended scope and update the attestation before dispatch.
- [ ] Create an immutable input-tag ruleset for `benchmark-input-*` that blocks update and deletion
  and restricts creation to authorized maintainers.
- [ ] Create an immutable result-tag ruleset for `benchmark-result-*` that blocks update and deletion
  and grants create bypass only to the exact release-finalizer App installation. The publisher and
  state Apps cannot bypass it.
- [ ] Enable GitHub immutable releases for the repository and capture the safe setting/API digest.
  Require the release-finalizer App to create only a new draft, upload the two plan-bound assets, and
  perform its one draft-to-published transition; after publication, neither that App nor any other
  benchmark identity may edit/delete the release or its assets. Re-fetch and bind the immutable
  release attestation before `RESULT_RELEASED`.
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
  every PR (and merge queue when enabled), have no top-level path filter, and return explicit success
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
  complete durable checkpoint into the immutable merge tree; after that, expiry substitution is
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
