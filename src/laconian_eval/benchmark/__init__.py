"""Public benchmark evidence primitives."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from laconian_eval.benchmark.attachments import (
    CanonicalJSONV1Error,
    RationalV1,
    attachment_digest,
    canonical_json_v1,
    parse_canonical_json_v1,
    write_attachment_json,
)
from laconian_eval.benchmark.protocol_review import (
    BENCHMARK_WORKFLOW_PATHS_V1,
    GITHUB_COMMIT_SIGNER_QUERY_V1,
    GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1,
    PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1,
    ArchivedApiBlobV1,
    ArchivedApiReceiptBindingV1,
    AuditReviewerRegistryV1,
    AuditReviewerSigningKeyV1,
    GitHubCommitVerificationProjectionV1,
    GitHubSignatureObservationReceiptV1,
    GitHubSignatureProjectionV1,
    GitHubVerifiedCommitEvidenceV1,
    GitObjectSHA256V1,
    InputTagMessageV1,
    LocalSignatureVerificationReceiptV1,
    OpenPGPVerifiedCommitEvidenceV1,
    ParsedProtocolGitObjectV1,
    ProtocolAttestationBundleV1,
    ProtocolAttestationTagBindingV1,
    ProtocolAttestationTagMessageV1,
    ProtocolBundleBuilderGitIdentityV1,
    ProtocolReviewerBindingV1,
    ProtocolReviewerRegistryV1,
    ProtocolReviewIdentityRegistryBundleV1,
    ProtocolReviewObjectArchiveV1,
    ProtocolReviewRoleV1,
    ProtocolReviewSigningKeyV1,
    ProtocolReviewStatementV1,
    ProtocolReviewSubjectV1,
    ProtocolSignatureEvidenceSourceV1,
    ProtocolSubjectKindV1,
    ReviewerAccountBindingV1,
    SignatureEvidenceV1,
    SignatureVerificationModeV1,
    SSHVerifiedCommitEvidenceV1,
    TagCreationRuleSuiteReceiptV1,
    TagOperatorProjectionV1,
    TagOperatorRegistryV1,
    TagRulesetObservationReceiptV1,
    TagRulesetPolicyV1,
    VerifiedProtocolAttestationV1,
    VerifiedProtocolReviewDagV1,
    VerifiedProtocolReviewPrefixV1,
    WorkflowInventoryV1,
    build_protocol_attestation_bundle,
    build_protocol_attestation_tag_binding,
    build_protocol_review_object_archive,
    build_workflow_inventory,
    canonical_protocol_reviewer_registry_bytes,
    canonical_reviewer_registry_bytes,
    compute_audit_reviewer_registry_sha256,
    compute_protocol_attestations_root,
    compute_protocol_reviewer_registry_sha256,
    load_verified_protocol_review_object_archive,
    parse_protocol_git_object,
    protocol_review_digest,
    verify_commit_signature_evidence_source,
    verify_protocol_review_dag,
    verify_protocol_review_prefix,
)
from laconian_eval.benchmark.protocol_review import (
    ArchivedProtocolGitObjectV1 as ArchivedProtocolGitObjectV1,
)
from laconian_eval.benchmark.protocol_review import (
    BoundedCanonicalText as BoundedCanonicalText,
)
from laconian_eval.benchmark.protocol_review import (
    CanonicalGitAsciiEmail as CanonicalGitAsciiEmail,
)
from laconian_eval.benchmark.protocol_review import (
    CanonicalGitAsciiName as CanonicalGitAsciiName,
)
from laconian_eval.benchmark.protocol_review import (
    CompanionTagRef as CompanionTagRef,
)
from laconian_eval.benchmark.protocol_review import (
    GitObjectId as GitObjectId,
)
from laconian_eval.benchmark.protocol_review import (
    GitObjectTypeV1 as GitObjectTypeV1,
)
from laconian_eval.benchmark.protocol_review import (
    InputTagRef as InputTagRef,
)
from laconian_eval.benchmark.protocol_review import (
    ProtocolReviewerCommitV1 as ProtocolReviewerCommitV1,
)
from laconian_eval.benchmark.protocol_review import (
    ProtocolReviewVerificationError as ProtocolReviewVerificationError,
)
from laconian_eval.benchmark.protocol_review import (
    StrictCanonicalBase64 as StrictCanonicalBase64,
)
from laconian_eval.benchmark.protocol_review import (
    TagCreationBypassGrantV1 as TagCreationBypassGrantV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagCreationRuleEvaluationV1 as TagCreationRuleEvaluationV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagRulesetBypassActorV1 as TagRulesetBypassActorV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagRulesetDetailProjectionV1 as TagRulesetDetailProjectionV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagRulesetListEntryProjectionV1 as TagRulesetListEntryProjectionV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagRulesetListPageProjectionV1 as TagRulesetListPageProjectionV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagRulesetProjectionV1 as TagRulesetProjectionV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagRulesetRequestTargetV1 as TagRulesetRequestTargetV1,
)
from laconian_eval.benchmark.protocol_review import (
    TagRulesetRuleV1 as TagRulesetRuleV1,
)
from laconian_eval.benchmark.protocol_review import (
    VerifierDependencyInventoryEntryV1 as VerifierDependencyInventoryEntryV1,
)
from laconian_eval.benchmark.protocol_review import (
    WholeSecondTimestamp as WholeSecondTimestamp,
)
from laconian_eval.benchmark.protocol_review import (
    WorkflowInventoryMemberV1 as WorkflowInventoryMemberV1,
)
from laconian_eval.benchmark.protocol_review import (
    compute_verifier_dependency_inventory_root as compute_verifier_dependency_inventory_root,
)
from laconian_eval.benchmark.protocol_review import (
    validate_signature_mode_fingerprint as validate_signature_mode_fingerprint,
)
from laconian_eval.benchmark.seeds import derive_seed128

if TYPE_CHECKING:
    from laconian_eval.benchmark.aggregation import (
        AggregatedModelV1,
        aggregate_verified_evidence,
    )
    from laconian_eval.benchmark.audit_commit_reveal import (
        AuditAdjudicationCoreV1,
        AuditAdjudicationV1,
        AuditGitObjectArchiveV1,
        AuditPullRequestEvidenceSourceV1,
        ExactGitHubPullRequestRecordV1,
        ExactGitHubReviewRecordV1,
        ExactGitHubReviewSignoffV1,
        ExactGitHubReviewSourceV1,
        GitHubAuditApiObservationReceiptV1,
        PullRequestProofV1,
        ReviewerChainV1,
        ReviewerCommitmentV1,
        ReviewerIdentityV1,
        ReviewerRevealV1,
        verify_audit_chain,
        verify_reviewer_chain,
    )
    from laconian_eval.benchmark.audit_metrics import (
        ModelAuditGateV1,
        ModelAuditMetricsV1,
        WeightedConfusionV1,
        WeightedProportionV1,
        compute_model_audit_metrics,
        evaluate_model_audit_gate,
    )
    from laconian_eval.benchmark.audit_sampling import (
        AuditSampleManifestV1,
        BlindAuditPacketV1,
        VerifiedAuditSampleRootV1,
        load_verified_audit_sample_root,
        select_audit_sample,
        verify_audit_sample,
        write_audit_sample_root,
    )
    from laconian_eval.benchmark.bootstrap import (
        BootstrapIntervalV1,
        BootstrapVectorsV1,
        make_cluster_vectors,
    )
    from laconian_eval.benchmark.context import (
        AttachmentLayerRootMemberV1,
        BenchmarkProtocolBindingsV1,
        GenerationContextExpectationV1,
        GenerationContextIndexV1,
        GenerationLayerRootMemberV1,
        LayerKindV1,
        LayerRootIndexV1,
        LayerRootMemberV1,
        VerifiedGenerationContextExpectationV1,
        VerifiedGenerationContextIndexV1,
        load_layer_root_index,
        load_verified_generation_context_index,
        protocol_bindings_from_context,
        write_generation_context_index,
        write_layer_root_index,
    )
    from laconian_eval.benchmark.hard_score import (
        HardReasonCode as HardReasonCode,
    )
    from laconian_eval.benchmark.hard_score import (
        HardScoreError as HardScoreError,
    )
    from laconian_eval.benchmark.hard_score import (
        HardScoreRecordV1 as HardScoreRecordV1,
    )
    from laconian_eval.benchmark.hard_score import (
        HardScoreRequestSetV1,
        build_hard_score_request_set,
        verify_hard_score_request_set,
    )
    from laconian_eval.benchmark.hard_score import (
        derive_judge_request_id as derive_judge_request_id,
    )
    from laconian_eval.benchmark.hard_score import (
        recompute_hard_score_request_set_sha256 as recompute_hard_score_request_set_sha256,
    )
    from laconian_eval.benchmark.judge import (
        JUDGE_REQUESTED_SERVICE_TIER,
        JUDGE_SERVICE_TIER_WIRE_FIELD,
        BlindJudgeRequestV1,
        JudgeAttachmentV1,
        JudgeAttemptBoundaryV1,
        JudgeAttemptEvidenceV1,
        JudgeAttemptRootIndexV1,
        JudgeAttemptRootMemberV1,
        JudgeAttemptUsageV1,
        JudgeProviderRequestV1,
        JudgeRequestAttachmentV1,
        VerifiedJudgeAttemptRootV1,
        build_judge_attachment,
        build_judge_request_attachment,
        load_verified_judge_attempt_root,
        verify_judge_attachment,
        verify_judge_request_attachment,
        write_judge_attempt_root,
    )
    from laconian_eval.benchmark.outcomes import (
        ModelOutcome as ModelOutcome,
    )
    from laconian_eval.benchmark.outcomes import (
        ModelOutcomeV1 as ModelOutcomeV1,
    )
    from laconian_eval.benchmark.outcomes import (
        OutcomeEvidenceV1 as OutcomeEvidenceV1,
    )
    from laconian_eval.benchmark.outcomes import (
        classify_model_outcome as classify_model_outcome,
    )
    from laconian_eval.benchmark.provider_evidence import (
        AuditPopulationAttachmentV1,
        BenchmarkProviderEvidenceProjectionV1,
        ProviderEvidenceIndexV1,
        VerifiedAuditPopulationV1,
        VerifiedBenchmarkProviderEvidenceV1,
        build_audit_population,
        compute_requested_returned_model_source_sha256,
        load_provider_evidence_index,
        load_verified_audit_population,
        load_verified_benchmark_provider_evidence,
        write_audit_population,
        write_provider_evidence_index,
    )
    from laconian_eval.benchmark.reporting import (
        AnalysisEvidenceAttachmentV1,
        AuditEvidenceAttachmentV1,
        BootstrapArtifactV1,
        CampaignAnalysisV1,
        VerifiedAnalysisEvidenceV1,
        VerifiedAuditEvidenceV1,
        build_bootstrap_artifact,
        load_verified_analysis_evidence,
        load_verified_audit_evidence,
        write_analysis_evidence_root,
        write_audit_evidence_root,
    )
    from laconian_eval.benchmark.sensitivity import (
        FalseFailCandidateV1 as FalseFailCandidateV1,
    )
    from laconian_eval.benchmark.sensitivity import (
        FalseFailLimitV1 as FalseFailLimitV1,
    )
    from laconian_eval.benchmark.sensitivity import (
        SensitivityCertificateV1,
        SensitivityResultV1,
        verify_sensitivity_certificate,
    )
    from laconian_eval.benchmark.sensitivity import (
        SensitivityExhaustionReason as SensitivityExhaustionReason,
    )
    from laconian_eval.benchmark.sensitivity import (
        SensitivityExtremumV1 as SensitivityExtremumV1,
    )
    from laconian_eval.benchmark.sensitivity import (
        derive_false_fail_limit as derive_false_fail_limit,
    )
    from laconian_eval.benchmark.sensitivity import (
        enumerate_sensitivity_exact as enumerate_sensitivity_exact,
    )

_CONTEXT_EXPORTS = frozenset(
    {
        "AttachmentLayerRootMemberV1",
        "BenchmarkProtocolBindingsV1",
        "GenerationContextExpectationV1",
        "GenerationContextIndexV1",
        "GenerationLayerRootMemberV1",
        "LayerKindV1",
        "LayerRootIndexV1",
        "LayerRootMemberV1",
        "VerifiedGenerationContextExpectationV1",
        "VerifiedGenerationContextIndexV1",
        "load_layer_root_index",
        "load_verified_generation_context_index",
        "protocol_bindings_from_context",
        "write_generation_context_index",
        "write_layer_root_index",
    }
)
_HARD_SCORE_EXPORTS = frozenset(
    {
        "HardReasonCode",
        "HardScoreError",
        "HardScoreRecordV1",
        "HardScoreRequestSetV1",
        "build_hard_score_request_set",
        "derive_judge_request_id",
        "recompute_hard_score_request_set_sha256",
        "verify_hard_score_request_set",
    }
)
_AGGREGATION_EXPORTS = frozenset({"AggregatedModelV1", "aggregate_verified_evidence"})
_AUDIT_SAMPLING_EXPORTS = frozenset(
    {
        "AuditSampleManifestV1",
        "BlindAuditPacketV1",
        "VerifiedAuditSampleRootV1",
        "load_verified_audit_sample_root",
        "select_audit_sample",
        "verify_audit_sample",
        "write_audit_sample_root",
    }
)
_AUDIT_COMMIT_REVEAL_EXPORTS = frozenset(
    {
        "AuditAdjudicationCoreV1",
        "AuditAdjudicationV1",
        "AuditGitObjectArchiveV1",
        "AuditPullRequestEvidenceSourceV1",
        "ExactGitHubPullRequestRecordV1",
        "ExactGitHubReviewRecordV1",
        "ExactGitHubReviewSignoffV1",
        "ExactGitHubReviewSourceV1",
        "GitHubAuditApiObservationReceiptV1",
        "PullRequestProofV1",
        "ReviewerChainV1",
        "ReviewerCommitmentV1",
        "ReviewerIdentityV1",
        "ReviewerRevealV1",
        "verify_audit_chain",
        "verify_reviewer_chain",
    }
)
_AUDIT_METRICS_EXPORTS = frozenset(
    {
        "ModelAuditGateV1",
        "ModelAuditMetricsV1",
        "WeightedConfusionV1",
        "WeightedProportionV1",
        "compute_model_audit_metrics",
        "evaluate_model_audit_gate",
    }
)
_BOOTSTRAP_EXPORTS = frozenset(
    {"BootstrapIntervalV1", "BootstrapVectorsV1", "make_cluster_vectors"}
)
_SENSITIVITY_EXPORTS = frozenset(
    {
        "FalseFailCandidateV1",
        "FalseFailLimitV1",
        "SensitivityExhaustionReason",
        "SensitivityExtremumV1",
        "SensitivityResultV1",
        "derive_false_fail_limit",
        "enumerate_sensitivity_exact",
        "SensitivityCertificateV1",
        "verify_sensitivity_certificate",
    }
)
_OUTCOME_EXPORTS = frozenset(
    {
        "ModelOutcome",
        "ModelOutcomeV1",
        "OutcomeEvidenceV1",
        "classify_model_outcome",
    }
)
_PROVIDER_EVIDENCE_EXPORTS = frozenset(
    {
        "AuditPopulationAttachmentV1",
        "BenchmarkProviderEvidenceProjectionV1",
        "ProviderEvidenceIndexV1",
        "VerifiedAuditPopulationV1",
        "VerifiedBenchmarkProviderEvidenceV1",
        "build_audit_population",
        "compute_requested_returned_model_source_sha256",
        "load_provider_evidence_index",
        "load_verified_audit_population",
        "load_verified_benchmark_provider_evidence",
        "write_audit_population",
        "write_provider_evidence_index",
    }
)
JUDGE_LAZY_EXPORTS_V1 = (
    "JUDGE_REQUESTED_SERVICE_TIER",
    "JUDGE_SERVICE_TIER_WIRE_FIELD",
    "BlindJudgeRequestV1",
    "JudgeProviderRequestV1",
    "JudgeRequestAttachmentV1",
    "JudgeAttemptUsageV1",
    "JudgeAttemptEvidenceV1",
    "JudgeAttemptBoundaryV1",
    "JudgeAttemptRootMemberV1",
    "JudgeAttemptRootIndexV1",
    "VerifiedJudgeAttemptRootV1",
    "write_judge_attempt_root",
    "load_verified_judge_attempt_root",
    "JudgeAttachmentV1",
    "build_judge_request_attachment",
    "verify_judge_request_attachment",
    "build_judge_attachment",
    "verify_judge_attachment",
)
_JUDGE_EXPORTS = {name: ("laconian_eval.benchmark.judge", name) for name in JUDGE_LAZY_EXPORTS_V1}
_REPORTING_EXPORTS = frozenset(
    {
        "AnalysisEvidenceAttachmentV1",
        "AuditEvidenceAttachmentV1",
        "BootstrapArtifactV1",
        "CampaignAnalysisV1",
        "VerifiedAnalysisEvidenceV1",
        "VerifiedAuditEvidenceV1",
        "build_bootstrap_artifact",
        "load_verified_analysis_evidence",
        "load_verified_audit_evidence",
        "write_analysis_evidence_root",
        "write_audit_evidence_root",
    }
)


def __getattr__(name: str) -> Any:
    """Load sidecar-dependent exports lazily to preserve capsule import acyclicity."""

    if name in _AGGREGATION_EXPORTS:
        module_name = "laconian_eval.benchmark.aggregation"
    elif name in _AUDIT_COMMIT_REVEAL_EXPORTS:
        module_name = "laconian_eval.benchmark.audit_commit_reveal"
    elif name in _AUDIT_METRICS_EXPORTS:
        module_name = "laconian_eval.benchmark.audit_metrics"
    elif name in _AUDIT_SAMPLING_EXPORTS:
        module_name = "laconian_eval.benchmark.audit_sampling"
    elif name in _BOOTSTRAP_EXPORTS:
        module_name = "laconian_eval.benchmark.bootstrap"
    elif name in _SENSITIVITY_EXPORTS:
        module_name = "laconian_eval.benchmark.sensitivity"
    elif name in _CONTEXT_EXPORTS:
        module_name = "laconian_eval.benchmark.context"
    elif name in _HARD_SCORE_EXPORTS:
        module_name = "laconian_eval.benchmark.hard_score"
    elif name in _OUTCOME_EXPORTS:
        module_name = "laconian_eval.benchmark.outcomes"
    elif name in _PROVIDER_EVIDENCE_EXPORTS:
        module_name = "laconian_eval.benchmark.provider_evidence"
    elif name in _REPORTING_EXPORTS:
        module_name = "laconian_eval.benchmark.reporting"
    elif name in _JUDGE_EXPORTS:
        module_name, owner_name = _JUDGE_EXPORTS[name]
        value = getattr(import_module(module_name), owner_name)
        globals()[name] = value
        return value
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose registered lazy owners without importing them."""

    return sorted(set(globals()) | set(__all__))


__all__ = (  # noqa: RUF022 - approved Slice 2 public contract order
    "CanonicalJSONV1Error",
    "canonical_json_v1",
    "parse_canonical_json_v1",
    "RationalV1",
    "attachment_digest",
    "write_attachment_json",
    "derive_seed128",
    "HardScoreRequestSetV1",
    "build_hard_score_request_set",
    "verify_hard_score_request_set",
    "JUDGE_REQUESTED_SERVICE_TIER",
    "JUDGE_SERVICE_TIER_WIRE_FIELD",
    "BlindJudgeRequestV1",
    "JudgeProviderRequestV1",
    "JudgeRequestAttachmentV1",
    "JudgeAttemptUsageV1",
    "JudgeAttemptEvidenceV1",
    "JudgeAttemptBoundaryV1",
    "JudgeAttemptRootMemberV1",
    "JudgeAttemptRootIndexV1",
    "VerifiedJudgeAttemptRootV1",
    "write_judge_attempt_root",
    "load_verified_judge_attempt_root",
    "JudgeAttachmentV1",
    "build_judge_request_attachment",
    "verify_judge_request_attachment",
    "build_judge_attachment",
    "verify_judge_attachment",
    "AggregatedModelV1",
    "aggregate_verified_evidence",
    "BootstrapVectorsV1",
    "BootstrapIntervalV1",
    "make_cluster_vectors",
    "BootstrapArtifactV1",
    "build_bootstrap_artifact",
    "LayerKindV1",
    "GenerationLayerRootMemberV1",
    "AttachmentLayerRootMemberV1",
    "LayerRootMemberV1",
    "LayerRootIndexV1",
    "write_layer_root_index",
    "load_layer_root_index",
    "SignatureVerificationModeV1",
    "GitHubVerifiedCommitEvidenceV1",
    "SSHVerifiedCommitEvidenceV1",
    "OpenPGPVerifiedCommitEvidenceV1",
    "SignatureEvidenceV1",
    "ProtocolSignatureEvidenceSourceV1",
    "AuditReviewerSigningKeyV1",
    "verify_commit_signature_evidence_source",
    "ProtocolReviewRoleV1",
    "ProtocolSubjectKindV1",
    "PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1",
    "ReviewerAccountBindingV1",
    "AuditReviewerRegistryV1",
    "ProtocolReviewerBindingV1",
    "ProtocolReviewerRegistryV1",
    "TagOperatorProjectionV1",
    "TagOperatorRegistryV1",
    "TagRulesetPolicyV1",
    "GITHUB_COMMIT_SIGNER_QUERY_V1",
    "GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1",
    "InputTagMessageV1",
    "ProtocolAttestationTagMessageV1",
    "ProtocolBundleBuilderGitIdentityV1",
    "TagRulesetObservationReceiptV1",
    "TagCreationRuleSuiteReceiptV1",
    "ArchivedApiReceiptBindingV1",
    "WorkflowInventoryV1",
    "BENCHMARK_WORKFLOW_PATHS_V1",
    "build_workflow_inventory",
    "GitObjectSHA256V1",
    "ParsedProtocolGitObjectV1",
    "VerifiedProtocolReviewPrefixV1",
    "VerifiedProtocolReviewDagV1",
    "ArchivedApiBlobV1",
    "parse_protocol_git_object",
    "verify_protocol_review_prefix",
    "verify_protocol_review_dag",
    "build_protocol_attestation_bundle",
    "build_protocol_attestation_tag_binding",
    "build_protocol_review_object_archive",
    "load_verified_protocol_review_object_archive",
    "ProtocolReviewSubjectV1",
    "ProtocolReviewStatementV1",
    "VerifiedProtocolAttestationV1",
    "GitHubCommitVerificationProjectionV1",
    "GitHubSignatureProjectionV1",
    "GitHubSignatureObservationReceiptV1",
    "LocalSignatureVerificationReceiptV1",
    "ProtocolReviewSigningKeyV1",
    "ProtocolReviewIdentityRegistryBundleV1",
    "ProtocolAttestationBundleV1",
    "ProtocolAttestationTagBindingV1",
    "ProtocolReviewObjectArchiveV1",
    "canonical_reviewer_registry_bytes",
    "compute_audit_reviewer_registry_sha256",
    "canonical_protocol_reviewer_registry_bytes",
    "compute_protocol_reviewer_registry_sha256",
    "protocol_review_digest",
    "compute_protocol_attestations_root",
    "BenchmarkProtocolBindingsV1",
    "protocol_bindings_from_context",
    "GenerationContextExpectationV1",
    "VerifiedGenerationContextExpectationV1",
    "GenerationContextIndexV1",
    "VerifiedGenerationContextIndexV1",
    "write_generation_context_index",
    "load_verified_generation_context_index",
    "ProviderEvidenceIndexV1",
    "compute_requested_returned_model_source_sha256",
    "write_provider_evidence_index",
    "load_provider_evidence_index",
    "BenchmarkProviderEvidenceProjectionV1",
    "VerifiedBenchmarkProviderEvidenceV1",
    "load_verified_benchmark_provider_evidence",
    "AuditPopulationAttachmentV1",
    "VerifiedAuditPopulationV1",
    "VerifiedAuditSampleRootV1",
    "build_audit_population",
    "write_audit_population",
    "load_verified_audit_population",
    "AuditSampleManifestV1",
    "BlindAuditPacketV1",
    "select_audit_sample",
    "verify_audit_sample",
    "write_audit_sample_root",
    "load_verified_audit_sample_root",
    "ReviewerIdentityV1",
    "PullRequestProofV1",
    "ReviewerCommitmentV1",
    "ReviewerRevealV1",
    "GitHubAuditApiObservationReceiptV1",
    "ExactGitHubPullRequestRecordV1",
    "AuditPullRequestEvidenceSourceV1",
    "AuditGitObjectArchiveV1",
    "ExactGitHubReviewSourceV1",
    "ReviewerChainV1",
    "verify_reviewer_chain",
    "AuditAdjudicationCoreV1",
    "ExactGitHubReviewRecordV1",
    "ExactGitHubReviewSignoffV1",
    "AuditAdjudicationV1",
    "verify_audit_chain",
    "WeightedConfusionV1",
    "WeightedProportionV1",
    "ModelAuditMetricsV1",
    "ModelAuditGateV1",
    "compute_model_audit_metrics",
    "evaluate_model_audit_gate",
    "SensitivityResultV1",
    "SensitivityCertificateV1",
    "verify_sensitivity_certificate",
    "CampaignAnalysisV1",
    "AuditEvidenceAttachmentV1",
    "AnalysisEvidenceAttachmentV1",
    "VerifiedAuditEvidenceV1",
    "VerifiedAnalysisEvidenceV1",
    "write_audit_evidence_root",
    "load_verified_audit_evidence",
    "load_verified_analysis_evidence",
    "write_analysis_evidence_root",
)
