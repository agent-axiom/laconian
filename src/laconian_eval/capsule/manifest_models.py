"""Strict authored and resolved generation capsule manifest models."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Literal, Self, TypeAlias

from pydantic import Field, field_validator, model_validator

from laconian_eval import __version__
from laconian_eval.capsule.canonical import canonical_json
from laconian_eval.capsule.schema import (
    PROTOCOL_STAGE_ORDER,
    ApiKeyEnvironmentName,
    Arm,
    BoundedNonBlankString,
    BoundedString,
    CapsuleModel,
    ClaimIntent,
    ComparisonRole,
    DatasetRole,
    DeclaredRequirement,
    ExactAsciiHttpUrl,
    ExactDate,
    MediaType,
    NamespacedString,
    NonNegativeFiniteFloat,
    PromptCacheMode,
    PromptCacheTTL,
    ProtocolStage,
    ProviderKind,
    ReasoningEffort,
    ReasoningMode,
    RelativePosixPath,
    RunName,
    RunPurpose,
    ServiceTier,
    Sha256,
    StrictMaxOutputTokens,
    StrictNonNegativeInt,
    StrictRepetitionCount,
    StrictSigned64Int,
    StrictTransientRetries,
    Temperature,
    TextVerbosity,
    TimeoutSeconds,
    require_fixed_order,
    require_unique,
)
from laconian_eval.models import RunManifest


def _validate_provider_configuration(
    *,
    kind: ProviderKind,
    api_key_env: str | None,
    replay_file: str | None,
) -> None:
    if kind == "openai":
        if api_key_env is None:
            raise ValueError("openai requires api_key_env")
        if replay_file is not None:
            raise ValueError("openai forbids replay_file")
    elif kind == "replay":
        if replay_file is None:
            raise ValueError("replay requires replay_file")
        if api_key_env is not None:
            raise ValueError("replay forbids api_key_env")
    elif api_key_env is not None or replay_file is not None:
        raise ValueError("fake forbids api_key_env and replay_file")


class SourceProviderV2(CapsuleModel):
    kind: ProviderKind
    model: BoundedNonBlankString
    api_key_env: ApiKeyEnvironmentName | None = None
    replay_file: RelativePosixPath | None = None

    @model_validator(mode="after")
    def validate_kind_configuration(self) -> Self:
        _validate_provider_configuration(
            kind=self.kind,
            api_key_env=self.api_key_env,
            replay_file=self.replay_file,
        )
        return self


class ResolvedProviderV2(CapsuleModel):
    kind: ProviderKind
    model: BoundedNonBlankString
    api_key_env: ApiKeyEnvironmentName | None
    replay_file: RelativePosixPath | None

    @model_validator(mode="after")
    def validate_kind_configuration(self) -> Self:
        _validate_provider_configuration(
            kind=self.kind,
            api_key_env=self.api_key_env,
            replay_file=self.replay_file,
        )
        return self


class SourceGenerationSettingsV2(CapsuleModel):
    max_output_tokens: StrictMaxOutputTokens = 1024
    temperature: Temperature | None = None
    reasoning_effort: ReasoningEffort | None = None
    text_verbosity: TextVerbosity | None = None
    reasoning_mode: ReasoningMode = "omitted"
    prompt_cache_mode: PromptCacheMode = "explicit"
    prompt_cache_ttl: PromptCacheTTL = "30m"
    service_tier: ServiceTier = "default"


class ResolvedGenerationSettingsV2(CapsuleModel):
    max_output_tokens: StrictMaxOutputTokens
    temperature: Temperature | None
    reasoning_effort: ReasoningEffort | None
    text_verbosity: TextVerbosity | None
    reasoning_mode: ReasoningMode
    prompt_cache_mode: PromptCacheMode
    prompt_cache_ttl: PromptCacheTTL
    service_tier: ServiceTier


class SourceRetryPolicyV2(CapsuleModel):
    max_transient_retries: StrictTransientRetries = 2
    timeout_seconds: TimeoutSeconds = 60.0


class ResolvedRetryPolicyV2(CapsuleModel):
    max_transient_retries: StrictTransientRetries
    timeout_seconds: TimeoutSeconds


PriceDimensionV1: TypeAlias = Literal[
    "ordinary_uncached_input_per_million",
    "cache_read_input_per_million",
    "cache_write_input_per_million",
    "visible_output_per_million",
    "reasoning_output_per_million",
]
_PRICE_DIMENSIONS_V1 = (
    "ordinary_uncached_input_per_million",
    "cache_read_input_per_million",
    "cache_write_input_per_million",
    "visible_output_per_million",
    "reasoning_output_per_million",
)


class PriceSourceEvidenceV1(CapsuleModel):
    dimension: PriceDimensionV1
    source_url: ExactAsciiHttpUrl
    effective_date: ExactDate
    usd_per_million: NonNegativeFiniteFloat
    source_sha256: Sha256


def _validate_price_evidence(
    snapshot: SourcePriceSnapshotV1 | ResolvedPriceSnapshotV1,
) -> None:
    if tuple(item.dimension for item in snapshot.source_evidence) != _PRICE_DIMENSIONS_V1:
        raise ValueError("source_evidence must contain the five dimensions in canonical order")
    for item in snapshot.source_evidence:
        if item.usd_per_million != getattr(snapshot, item.dimension):
            raise ValueError("source evidence rate must equal snapshot rate")
        payload = {
            "dimension": item.dimension,
            "source_url": item.source_url,
            "effective_date": item.effective_date,
            "usd_per_million": item.usd_per_million,
        }
        if item.source_sha256 != hashlib.sha256(canonical_json(payload)).hexdigest():
            raise ValueError("source evidence digest mismatch")


class SourcePriceSnapshotV1(CapsuleModel):
    currency: Literal["USD"] = "USD"
    effective_date: ExactDate
    source_url: ExactAsciiHttpUrl
    service_tier: ServiceTier = "default"
    ordinary_uncached_input_per_million: NonNegativeFiniteFloat
    cache_read_input_per_million: NonNegativeFiniteFloat
    cache_write_input_per_million: NonNegativeFiniteFloat
    visible_output_per_million: NonNegativeFiniteFloat
    reasoning_output_per_million: NonNegativeFiniteFloat
    source_evidence: tuple[PriceSourceEvidenceV1, ...]

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        _validate_price_evidence(self)
        return self


class ResolvedPriceSnapshotV1(CapsuleModel):
    currency: Literal["USD"]
    effective_date: ExactDate
    source_url: ExactAsciiHttpUrl
    service_tier: ServiceTier
    ordinary_uncached_input_per_million: NonNegativeFiniteFloat
    cache_read_input_per_million: NonNegativeFiniteFloat
    cache_write_input_per_million: NonNegativeFiniteFloat
    visible_output_per_million: NonNegativeFiniteFloat
    reasoning_output_per_million: NonNegativeFiniteFloat
    source_evidence: tuple[PriceSourceEvidenceV1, ...]

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        _validate_price_evidence(self)
        return self


class _V1LegacyPriceSnapshotProjection(CapsuleModel):
    currency: Literal["USD"] = "USD"
    effective_date: ExactDate
    source_url: ExactAsciiHttpUrl
    input_per_million: NonNegativeFiniteFloat
    cached_input_per_million: NonNegativeFiniteFloat | None = None
    output_per_million: NonNegativeFiniteFloat


class SourceDatasetV2(CapsuleModel):
    dataset_id: BoundedNonBlankString
    dataset_version: BoundedNonBlankString
    role: DatasetRole
    case_schema_version: Literal["1"]
    case_file_ordinals: tuple[StrictNonNegativeInt, ...] = Field(min_length=1)

    @field_validator("case_file_ordinals")
    @classmethod
    def validate_unique_ordinals(
        cls, value: tuple[StrictNonNegativeInt, ...]
    ) -> tuple[StrictNonNegativeInt, ...]:
        return require_unique(value, label="case_file_ordinals")


class ResolvedDatasetV2(CapsuleModel):
    dataset_id: BoundedNonBlankString
    dataset_version: BoundedNonBlankString
    role: DatasetRole
    case_schema_version: Literal["1"]
    case_file_ordinals: tuple[StrictNonNegativeInt, ...] = Field(min_length=1)
    dataset_content_sha256: Sha256

    @field_validator("case_file_ordinals")
    @classmethod
    def validate_unique_ordinals(
        cls, value: tuple[StrictNonNegativeInt, ...]
    ) -> tuple[StrictNonNegativeInt, ...]:
        return require_unique(value, label="case_file_ordinals")


class ComparisonV2(CapsuleModel):
    comparison_id: BoundedNonBlankString
    left_arm: Arm
    right_arm: Arm
    role: ComparisonRole

    @model_validator(mode="after")
    def validate_distinct_arms(self) -> Self:
        if self.left_arm == self.right_arm:
            raise ValueError("comparison arms must be distinct")
        return self


class ProtocolScopeV2(CapsuleModel):
    dataset_ids: tuple[BoundedNonBlankString, ...]
    comparison_ids: tuple[BoundedNonBlankString, ...]

    @model_validator(mode="after")
    def validate_nonempty_scope(self) -> Self:
        if not self.dataset_ids and not self.comparison_ids:
            raise ValueError("protocol scope must name a dataset or comparison")
        return self


class SourceProtocolBindingV2(CapsuleModel):
    binding_id: BoundedNonBlankString
    kind: NamespacedString
    schema_id: NamespacedString
    media_type: MediaType
    path: RelativePosixPath
    scope: ProtocolScopeV2
    bound_at_stage: Literal["pre_generation"]
    applies_at: tuple[ProtocolStage, ...] = Field(min_length=1)
    declared_requirement: DeclaredRequirement

    @field_validator("applies_at")
    @classmethod
    def validate_applies_order(cls, value: tuple[ProtocolStage, ...]) -> tuple[ProtocolStage, ...]:
        return require_fixed_order(value, order=PROTOCOL_STAGE_ORDER, label="applies_at")


class ResolvedProtocolBindingV2(CapsuleModel):
    binding_id: BoundedNonBlankString
    kind: NamespacedString
    schema_id: NamespacedString
    media_type: MediaType
    path: RelativePosixPath
    byte_length: StrictNonNegativeInt
    sha256: Sha256
    scope: ProtocolScopeV2
    bound_at_stage: Literal["pre_generation"]
    applies_at: tuple[ProtocolStage, ...] = Field(min_length=1)
    declared_requirement: DeclaredRequirement

    @field_validator("applies_at")
    @classmethod
    def validate_applies_order(cls, value: tuple[ProtocolStage, ...]) -> tuple[ProtocolStage, ...]:
        return require_fixed_order(value, order=PROTOCOL_STAGE_ORDER, label="applies_at")


def _validate_capsule_declarations(
    *,
    arms: tuple[Arm, ...],
    case_file_count: int,
    datasets: tuple[SourceDatasetV2 | ResolvedDatasetV2, ...],
    comparisons: tuple[ComparisonV2, ...],
    protocol_bindings: tuple[SourceProtocolBindingV2 | ResolvedProtocolBindingV2, ...],
) -> None:
    dataset_ids = tuple(dataset.dataset_id for dataset in datasets)
    require_unique(dataset_ids, label="dataset IDs")
    comparison_ids = tuple(comparison.comparison_id for comparison in comparisons)
    require_unique(comparison_ids, label="comparison IDs")
    binding_ids = tuple(binding.binding_id for binding in protocol_bindings)
    require_unique(binding_ids, label="binding IDs")

    owned_ordinals = tuple(
        ordinal for dataset in datasets for ordinal in dataset.case_file_ordinals
    )
    if sorted(owned_ordinals) != list(range(case_file_count)):
        raise ValueError("dataset ordinals must partition case_files exactly")

    selected_arms = set(arms)
    unordered_pairs: set[frozenset[str]] = set()
    primary_count = 0
    for comparison in comparisons:
        if comparison.left_arm not in selected_arms or comparison.right_arm not in selected_arms:
            raise ValueError("comparison arms must both be selected")
        unordered_pair = frozenset((comparison.left_arm, comparison.right_arm))
        if unordered_pair in unordered_pairs:
            raise ValueError("unordered comparison pairs must be unique")
        unordered_pairs.add(unordered_pair)
        if comparison.role == "primary":
            primary_count += 1
    if primary_count > 1:
        raise ValueError("at most one comparison may be primary")

    declared_datasets = set(dataset_ids)
    declared_comparisons = set(comparison_ids)
    for binding in protocol_bindings:
        if not set(binding.scope.dataset_ids) <= declared_datasets:
            raise ValueError("protocol scope references an undeclared dataset")
        if not set(binding.scope.comparison_ids) <= declared_comparisons:
            raise ValueError("protocol scope references an undeclared comparison")


class SourceCapsuleDeclarationsV2(CapsuleModel):
    run_purpose: RunPurpose
    claim_intent: ClaimIntent
    datasets: tuple[SourceDatasetV2, ...] = Field(min_length=1)
    comparisons: tuple[ComparisonV2, ...]
    protocol_bindings: tuple[SourceProtocolBindingV2, ...]


class ResolvedCapsuleDeclarationsV2(CapsuleModel):
    run_purpose: RunPurpose
    claim_intent: ClaimIntent
    datasets: tuple[ResolvedDatasetV2, ...] = Field(min_length=1)
    comparisons: tuple[ComparisonV2, ...]
    protocol_bindings: tuple[ResolvedProtocolBindingV2, ...]


class V1ProjectedProvider(CapsuleModel):
    """Provider values after v1 ignored-field normalization but before path capture."""

    kind: ProviderKind
    model: BoundedNonBlankString
    api_key_env: ApiKeyEnvironmentName | None
    replay_file: BoundedNonBlankString | None

    @model_validator(mode="after")
    def validate_kind_configuration(self) -> Self:
        _validate_provider_configuration(
            kind=self.kind,
            api_key_env=self.api_key_env,
            replay_file=self.replay_file,
        )
        return self


class V1UpgradeProjection(CapsuleModel):
    """Path-unresolved exact logical projection of an authored v1 manifest."""

    source_manifest_schema_version: Literal["1"]
    runner_version: BoundedNonBlankString
    run_name: RunName
    provider: V1ProjectedProvider
    case_files: tuple[BoundedString, ...] = Field(min_length=1)
    arms: tuple[Arm, ...] = Field(min_length=1)
    repetitions: StrictRepetitionCount
    arm_order_seed: StrictSigned64Int
    instruction_placement: Literal["system_suffix"]
    generation: SourceGenerationSettingsV2
    retry: SourceRetryPolicyV2
    price_snapshot: _V1LegacyPriceSnapshotProjection | None
    capsule: SourceCapsuleDeclarationsV2

    @field_validator("arms")
    @classmethod
    def validate_unique_arms(cls, value: tuple[Arm, ...]) -> tuple[Arm, ...]:
        return require_unique(value, label="arms")

    @model_validator(mode="after")
    def validate_declarations(self) -> Self:
        _validate_capsule_declarations(
            arms=self.arms,
            case_file_count=len(self.case_files),
            datasets=self.capsule.datasets,
            comparisons=self.capsule.comparisons,
            protocol_bindings=self.capsule.protocol_bindings,
        )
        return self


class _V1ProjectionProviderInput(CapsuleModel):
    kind: ProviderKind
    model: BoundedNonBlankString
    api_key_env: ApiKeyEnvironmentName | None = None
    replay_file: BoundedString | None = None


class _V1ProjectionInput(CapsuleModel):
    schema_version: Literal["1"]
    runner_version: BoundedNonBlankString
    run_name: RunName
    provider: _V1ProjectionProviderInput
    case_files: tuple[BoundedString, ...] = Field(min_length=1)
    arms: tuple[Arm, ...] = Field(min_length=1)
    repetitions: StrictRepetitionCount = 1
    arm_order_seed: StrictSigned64Int = 0
    instruction_placement: Literal["system_suffix"] = "system_suffix"
    generation: SourceGenerationSettingsV2 = Field(default_factory=SourceGenerationSettingsV2)
    retry: SourceRetryPolicyV2 = Field(default_factory=SourceRetryPolicyV2)
    price_snapshot: _V1LegacyPriceSnapshotProjection | None = None

    @field_validator("arms")
    @classmethod
    def validate_unique_arms(cls, value: tuple[Arm, ...]) -> tuple[Arm, ...]:
        return require_unique(value, label="arms")


class SourceManifestV2(CapsuleModel):
    schema_version: Literal["2"]
    runner_version: BoundedNonBlankString
    run_name: RunName
    provider: SourceProviderV2
    case_files: tuple[RelativePosixPath, ...] = Field(min_length=1)
    arms: tuple[Arm, ...] = Field(min_length=1)
    repetitions: StrictRepetitionCount = 1
    arm_order_seed: StrictSigned64Int = 0
    instruction_placement: Literal["system_suffix"] = "system_suffix"
    generation: SourceGenerationSettingsV2 = Field(default_factory=SourceGenerationSettingsV2)
    retry: SourceRetryPolicyV2 = Field(default_factory=SourceRetryPolicyV2)
    price_snapshot: SourcePriceSnapshotV1 | None = None
    capsule: SourceCapsuleDeclarationsV2

    @field_validator("runner_version")
    @classmethod
    def require_current_runner_version(cls, value: str) -> str:
        if value != __version__:
            raise ValueError(f"runner_version must equal current runner version {__version__!r}")
        return value

    @field_validator("arms")
    @classmethod
    def validate_unique_arms(cls, value: tuple[Arm, ...]) -> tuple[Arm, ...]:
        return require_unique(value, label="arms")

    @model_validator(mode="after")
    def validate_declarations(self) -> Self:
        _validate_capsule_declarations(
            arms=self.arms,
            case_file_count=len(self.case_files),
            datasets=self.capsule.datasets,
            comparisons=self.capsule.comparisons,
            protocol_bindings=self.capsule.protocol_bindings,
        )
        return self


class ResolvedManifestV2(CapsuleModel):
    schema_version: Literal["2"]
    source_manifest_schema_version: Literal["1", "2"]
    runner_version: BoundedNonBlankString
    run_name: RunName
    provider: ResolvedProviderV2
    case_files: tuple[RelativePosixPath, ...] = Field(min_length=1)
    arms: tuple[Arm, ...] = Field(min_length=1)
    repetitions: StrictRepetitionCount
    arm_order_seed: StrictSigned64Int
    instruction_placement: Literal["system_suffix"]
    schedule_algorithm_version: Literal["laconian-schedule-v1"]
    generation: ResolvedGenerationSettingsV2
    retry: ResolvedRetryPolicyV2
    price_snapshot: ResolvedPriceSnapshotV1 | None
    capsule: ResolvedCapsuleDeclarationsV2

    @field_validator("arms")
    @classmethod
    def validate_unique_arms(cls, value: tuple[Arm, ...]) -> tuple[Arm, ...]:
        return require_unique(value, label="arms")

    @model_validator(mode="after")
    def validate_declarations(self) -> Self:
        _validate_capsule_declarations(
            arms=self.arms,
            case_file_count=len(self.case_files),
            datasets=self.capsule.datasets,
            comparisons=self.capsule.comparisons,
            protocol_bindings=self.capsule.protocol_bindings,
        )
        if self.source_manifest_schema_version == "1":
            dataset = self.capsule.datasets[0] if len(self.capsule.datasets) == 1 else None
            has_default_comparison = "if" in self.arms and "concise" in self.arms
            comparison = self.capsule.comparisons[0] if len(self.capsule.comparisons) == 1 else None
            exact_dataset = (
                dataset is not None
                and dataset.dataset_id == self.run_name
                and dataset.dataset_version == "unversioned"
                and dataset.role == "smoke"
                and dataset.case_schema_version == "1"
                and dataset.case_file_ordinals == tuple(range(len(self.case_files)))
            )
            exact_comparisons = (
                comparison is not None
                and comparison.comparison_id == "if-vs-concise"
                and comparison.left_arm == "if"
                and comparison.right_arm == "concise"
                and comparison.role == "contextual"
                if has_default_comparison
                else not self.capsule.comparisons
            )
            if (
                self.capsule.run_purpose != "integration_smoke"
                or self.capsule.claim_intent != "none"
                or not exact_dataset
                or not exact_comparisons
                or self.capsule.protocol_bindings
                or self.generation.reasoning_effort is not None
                or self.generation.text_verbosity is not None
                or self.price_snapshot is not None
            ):
                raise ValueError("v1 source marker requires the exact upgrade projection")
        expected_case_paths = tuple(
            f"inputs/cases/{ordinal:03d}.yaml" for ordinal in range(len(self.case_files))
        )
        if self.case_files != expected_case_paths:
            raise ValueError("resolved case paths must use their captured ordinals")
        if self.provider.kind == "replay":
            if self.provider.replay_file != "inputs/provider/replay.yaml":
                raise ValueError("resolved replay path must use the fixed capsule path")
        elif self.provider.replay_file is not None:
            raise ValueError("only replay providers may carry a resolved replay path")
        for ordinal, binding in enumerate(self.capsule.protocol_bindings):
            prefix = hashlib.sha256(binding.binding_id.encode("utf-8")).hexdigest()[:16]
            expected_path = f"inputs/protocols/{ordinal:03d}-{prefix}.bin"
            if binding.path != expected_path:
                raise ValueError("resolved protocol path must match its ordinal and binding")
        return self


def project_v1_manifest(payload: Mapping[str, object]) -> V1UpgradeProjection:
    """Validate raw v1 scalars and project defaults without resolving source locators."""

    validated = RunManifest.model_validate(payload)
    projection_payload = dict(payload)
    if validated.price_snapshot is not None:
        raw_price = payload.get("price_snapshot")
        if not isinstance(raw_price, Mapping):
            raise ValueError("validated price snapshot must retain its authored mapping")
        projection_payload["price_snapshot"] = {
            "currency": validated.price_snapshot.currency,
            "effective_date": validated.price_snapshot.effective_date,
            "source_url": raw_price.get("source_url"),
            "input_per_million": validated.price_snapshot.input_per_million,
            "cached_input_per_million": validated.price_snapshot.cached_input_per_million,
            "output_per_million": validated.price_snapshot.output_per_million,
        }
    manifest = _V1ProjectionInput.model_validate(projection_payload)
    api_key_env = manifest.provider.api_key_env if manifest.provider.kind == "openai" else None
    replay_file = manifest.provider.replay_file if manifest.provider.kind == "replay" else None
    comparisons: list[dict[str, str]] = []
    if "if" in manifest.arms and "concise" in manifest.arms:
        comparisons.append(
            {
                "comparison_id": "if-vs-concise",
                "left_arm": "if",
                "right_arm": "concise",
                "role": "contextual",
            }
        )

    return V1UpgradeProjection.model_validate(
        {
            "source_manifest_schema_version": "1",
            "runner_version": manifest.runner_version,
            "run_name": manifest.run_name,
            "provider": {
                "kind": manifest.provider.kind,
                "model": manifest.provider.model,
                "api_key_env": api_key_env,
                "replay_file": replay_file,
            },
            "case_files": manifest.case_files,
            "arms": list(manifest.arms),
            "repetitions": manifest.repetitions,
            "arm_order_seed": manifest.arm_order_seed,
            "instruction_placement": manifest.instruction_placement,
            "generation": {
                "max_output_tokens": manifest.generation.max_output_tokens,
                "temperature": manifest.generation.temperature,
            },
            "retry": {
                "max_transient_retries": manifest.retry.max_transient_retries,
                "timeout_seconds": manifest.retry.timeout_seconds,
            },
            "price_snapshot": manifest.price_snapshot,
            "capsule": {
                "run_purpose": "integration_smoke",
                "claim_intent": "none",
                "datasets": [
                    {
                        "dataset_id": manifest.run_name,
                        "dataset_version": "unversioned",
                        "role": "smoke",
                        "case_schema_version": "1",
                        "case_file_ordinals": list(range(len(manifest.case_files))),
                    }
                ],
                "comparisons": comparisons,
                "protocol_bindings": [],
            },
        }
    )
