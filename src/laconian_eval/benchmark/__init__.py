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
    ArchivedProtocolGitObjectV1,
    AuditReviewerRegistryV1,
    AuditReviewerSigningKeyV1,
    BoundedCanonicalText,
    CanonicalGitAsciiEmail,
    CanonicalGitAsciiName,
    CompanionTagRef,
    GitHubCommitVerificationProjectionV1,
    GitHubSignatureObservationReceiptV1,
    GitHubSignatureProjectionV1,
    GitHubVerifiedCommitEvidenceV1,
    GitObjectId,
    GitObjectSHA256V1,
    GitObjectTypeV1,
    InputTagMessageV1,
    InputTagRef,
    LocalSignatureVerificationReceiptV1,
    OpenPGPVerifiedCommitEvidenceV1,
    ParsedProtocolGitObjectV1,
    ProtocolAttestationBundleV1,
    ProtocolAttestationTagBindingV1,
    ProtocolAttestationTagMessageV1,
    ProtocolBundleBuilderGitIdentityV1,
    ProtocolReviewerBindingV1,
    ProtocolReviewerCommitV1,
    ProtocolReviewerRegistryV1,
    ProtocolReviewIdentityRegistryBundleV1,
    ProtocolReviewObjectArchiveV1,
    ProtocolReviewRoleV1,
    ProtocolReviewSigningKeyV1,
    ProtocolReviewStatementV1,
    ProtocolReviewSubjectV1,
    ProtocolReviewVerificationError,
    ProtocolSignatureEvidenceSourceV1,
    ProtocolSubjectKindV1,
    ReviewerAccountBindingV1,
    SignatureEvidenceV1,
    SignatureVerificationModeV1,
    SSHVerifiedCommitEvidenceV1,
    StrictCanonicalBase64,
    TagCreationBypassGrantV1,
    TagCreationRuleEvaluationV1,
    TagCreationRuleSuiteReceiptV1,
    TagOperatorProjectionV1,
    TagOperatorRegistryV1,
    TagRulesetBypassActorV1,
    TagRulesetDetailProjectionV1,
    TagRulesetListEntryProjectionV1,
    TagRulesetListPageProjectionV1,
    TagRulesetObservationReceiptV1,
    TagRulesetPolicyV1,
    TagRulesetProjectionV1,
    TagRulesetRequestTargetV1,
    TagRulesetRuleV1,
    VerifiedProtocolAttestationV1,
    VerifiedProtocolReviewDagV1,
    VerifiedProtocolReviewPrefixV1,
    VerifierDependencyInventoryEntryV1,
    WholeSecondTimestamp,
    WorkflowInventoryMemberV1,
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
    compute_verifier_dependency_inventory_root,
    load_verified_protocol_review_object_archive,
    parse_protocol_git_object,
    protocol_review_digest,
    validate_signature_mode_fingerprint,
    verify_commit_signature_evidence_source,
    verify_protocol_review_dag,
    verify_protocol_review_prefix,
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
        HardReasonCode,
        HardScoreError,
        HardScoreRecordV1,
        HardScoreRequestSetV1,
        build_hard_score_request_set,
        derive_judge_request_id,
        recompute_hard_score_request_set_sha256,
        verify_hard_score_request_set,
    )
    from laconian_eval.benchmark.judge import (  # noqa: F401 - PEP 562 typing surface
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
        ModelOutcome,
        ModelOutcomeV1,
        OutcomeEvidenceV1,
        classify_model_outcome,
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
    from laconian_eval.benchmark.sensitivity import (
        FalseFailCandidateV1,
        FalseFailLimitV1,
        SensitivityExhaustionReason,
        SensitivityExtremumV1,
        SensitivityResultV1,
        derive_false_fail_limit,
        enumerate_sensitivity_exact,
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
    {"FalseFailCandidateV1", "FalseFailLimitV1", "SensitivityExhaustionReason",
     "SensitivityExtremumV1", "SensitivityResultV1", "derive_false_fail_limit",
     "enumerate_sensitivity_exact"}
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


__all__ = (
    "FalseFailCandidateV1",
    "FalseFailLimitV1",
    "SensitivityExhaustionReason",
    "SensitivityExtremumV1",
    "SensitivityResultV1",
    "derive_false_fail_limit",
    "enumerate_sensitivity_exact",
    "ModelAuditGateV1",
    "ModelAuditMetricsV1",
    "WeightedConfusionV1",
    "WeightedProportionV1",
    "compute_model_audit_metrics",
    "evaluate_model_audit_gate",
    "BENCHMARK_WORKFLOW_PATHS_V1",
    "GITHUB_COMMIT_SIGNER_QUERY_V1",
    "GRAPHQL_COMMIT_SIGNER_QUERY_SHA256_V1",
    "PROTOCOL_REVIEW_SUBJECT_KINDS_BY_ROLE_V1",
    "AggregatedModelV1",
    "ArchivedApiBlobV1",
    "ArchivedApiReceiptBindingV1",
    "ArchivedProtocolGitObjectV1",
    "AttachmentLayerRootMemberV1",
    "AuditPopulationAttachmentV1",
    "AuditAdjudicationCoreV1",
    "AuditAdjudicationV1",
    "AuditGitObjectArchiveV1",
    "AuditPullRequestEvidenceSourceV1",
    "AuditReviewerRegistryV1",
    "AuditReviewerSigningKeyV1",
    "AuditSampleManifestV1",
    "BenchmarkProtocolBindingsV1",
    "BenchmarkProviderEvidenceProjectionV1",
    "BlindAuditPacketV1",
    "BootstrapIntervalV1",
    "BootstrapVectorsV1",
    "BoundedCanonicalText",
    "CanonicalGitAsciiEmail",
    "CanonicalGitAsciiName",
    "CanonicalJSONV1Error",
    "CompanionTagRef",
    "GenerationContextExpectationV1",
    "GenerationContextIndexV1",
    "GenerationLayerRootMemberV1",
    "GitHubAuditApiObservationReceiptV1",
    "GitHubCommitVerificationProjectionV1",
    "GitHubSignatureObservationReceiptV1",
    "GitHubSignatureProjectionV1",
    "GitHubVerifiedCommitEvidenceV1",
    "GitObjectId",
    "GitObjectSHA256V1",
    "GitObjectTypeV1",
    "HardReasonCode",
    "HardScoreError",
    "HardScoreRecordV1",
    "HardScoreRequestSetV1",
    "InputTagMessageV1",
    "InputTagRef",
    "LayerKindV1",
    "LayerRootIndexV1",
    "LayerRootMemberV1",
    "LocalSignatureVerificationReceiptV1",
    "ModelOutcome",
    "ModelOutcomeV1",
    "ExactGitHubPullRequestRecordV1",
    "ExactGitHubReviewRecordV1",
    "ExactGitHubReviewSignoffV1",
    "ExactGitHubReviewSourceV1",
    "OpenPGPVerifiedCommitEvidenceV1",
    "OutcomeEvidenceV1",
    "ParsedProtocolGitObjectV1",
    "ProtocolAttestationBundleV1",
    "ProtocolAttestationTagBindingV1",
    "ProtocolAttestationTagMessageV1",
    "ProtocolBundleBuilderGitIdentityV1",
    "ProtocolReviewIdentityRegistryBundleV1",
    "ProtocolReviewObjectArchiveV1",
    "ProtocolReviewRoleV1",
    "ProtocolReviewSigningKeyV1",
    "ProtocolReviewStatementV1",
    "ProtocolReviewSubjectV1",
    "ProtocolReviewVerificationError",
    "ProtocolReviewerBindingV1",
    "ProtocolReviewerCommitV1",
    "ProtocolReviewerRegistryV1",
    "ProtocolSignatureEvidenceSourceV1",
    "ProtocolSubjectKindV1",
    "ProviderEvidenceIndexV1",
    "RationalV1",
    "PullRequestProofV1",
    "ReviewerAccountBindingV1",
    "ReviewerChainV1",
    "ReviewerCommitmentV1",
    "ReviewerIdentityV1",
    "ReviewerRevealV1",
    "SSHVerifiedCommitEvidenceV1",
    "SignatureEvidenceV1",
    "SignatureVerificationModeV1",
    "StrictCanonicalBase64",
    "TagCreationBypassGrantV1",
    "TagCreationRuleEvaluationV1",
    "TagCreationRuleSuiteReceiptV1",
    "TagOperatorProjectionV1",
    "TagOperatorRegistryV1",
    "TagRulesetBypassActorV1",
    "TagRulesetDetailProjectionV1",
    "TagRulesetListEntryProjectionV1",
    "TagRulesetListPageProjectionV1",
    "TagRulesetObservationReceiptV1",
    "TagRulesetPolicyV1",
    "TagRulesetProjectionV1",
    "TagRulesetRequestTargetV1",
    "TagRulesetRuleV1",
    "VerifiedGenerationContextExpectationV1",
    "VerifiedGenerationContextIndexV1",
    "VerifiedAuditPopulationV1",
    "VerifiedAuditSampleRootV1",
    "VerifiedBenchmarkProviderEvidenceV1",
    "VerifiedProtocolAttestationV1",
    "VerifiedProtocolReviewDagV1",
    "VerifiedProtocolReviewPrefixV1",
    "VerifierDependencyInventoryEntryV1",
    "WholeSecondTimestamp",
    "WorkflowInventoryMemberV1",
    "WorkflowInventoryV1",
    "attachment_digest",
    "aggregate_verified_evidence",
    "build_audit_population",
    "build_hard_score_request_set",
    "build_protocol_attestation_bundle",
    "build_protocol_attestation_tag_binding",
    "build_protocol_review_object_archive",
    "build_workflow_inventory",
    "canonical_json_v1",
    "canonical_protocol_reviewer_registry_bytes",
    "canonical_reviewer_registry_bytes",
    "compute_audit_reviewer_registry_sha256",
    "compute_requested_returned_model_source_sha256",
    "compute_protocol_attestations_root",
    "compute_protocol_reviewer_registry_sha256",
    "compute_verifier_dependency_inventory_root",
    "classify_model_outcome",
    "derive_judge_request_id",
    "derive_seed128",
    "load_layer_root_index",
    "load_provider_evidence_index",
    "load_verified_audit_population",
    "load_verified_audit_sample_root",
    "load_verified_benchmark_provider_evidence",
    "load_verified_generation_context_index",
    "load_verified_protocol_review_object_archive",
    "make_cluster_vectors",
    "parse_canonical_json_v1",
    "parse_protocol_git_object",
    "protocol_bindings_from_context",
    "protocol_review_digest",
    "recompute_hard_score_request_set_sha256",
    "select_audit_sample",
    "validate_signature_mode_fingerprint",
    "verify_audit_chain",
    "verify_commit_signature_evidence_source",
    "verify_hard_score_request_set",
    "verify_audit_sample",
    "verify_protocol_review_dag",
    "verify_protocol_review_prefix",
    "verify_reviewer_chain",
    "write_attachment_json",
    "write_audit_population",
    "write_audit_sample_root",
    "write_generation_context_index",
    "write_layer_root_index",
    "write_provider_evidence_index",
    *JUDGE_LAZY_EXPORTS_V1,
)
