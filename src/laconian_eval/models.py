from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HardConstraints(StrictModel):
    required_literals: tuple[str, ...] = ()
    forbidden_literals: tuple[str, ...] = ()
    required_json_keys: tuple[str, ...] = ()
    min_sentences: int | None = Field(default=None, ge=1)
    max_sentences: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_sentence_bounds(self) -> Self:
        if (
            self.min_sentences is not None
            and self.max_sentences is not None
            and self.min_sentences > self.max_sentences
        ):
            raise ValueError("min_sentences must not exceed max_sentences")
        return self


class SemanticRubric(StrictModel):
    required_facts: tuple[str, ...] = ()
    material_warning: str | None = None


class ResponseCase(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+-(en|ru)$")
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    locale: Literal["en", "ru"]
    category: Literal[
        "direct",
        "coding",
        "preservation",
        "structured-output",
        "uncertainty",
        "safety",
        "user-message",
        "summarization",
    ]
    prompt: str = Field(min_length=1)
    hard_constraints: HardConstraints = HardConstraints()
    semantic_rubric: SemanticRubric = SemanticRubric()

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class ActivationCase(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+-(en|ru)$")
    scenario_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    locale: Literal["en", "ru"]
    prompt: str = Field(min_length=1)
    expected_activation: bool
    rationale: str = Field(min_length=1)

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class ResponseCaseFile(StrictModel):
    schema_version: Literal["1"]
    kind: Literal["response"]
    cases: tuple[ResponseCase, ...]


class ActivationCaseFile(StrictModel):
    schema_version: Literal["1"]
    kind: Literal["activation"]
    cases: tuple[ActivationCase, ...]


class ProviderConfig(StrictModel):
    kind: Literal["fake", "replay", "openai"]
    model: str = Field(min_length=1)
    api_key_env: str | None = None
    replay_file: str | None = None

    @model_validator(mode="after")
    def validate_kind_configuration(self) -> Self:
        if self.kind == "openai" and (self.api_key_env is None or not self.api_key_env.strip()):
            raise ValueError("api_key_env must be nonblank when kind is openai")
        if self.kind == "replay" and (self.replay_file is None or not self.replay_file.strip()):
            raise ValueError("replay_file must be nonblank when kind is replay")
        return self


class GenerationSettings(StrictModel):
    max_output_tokens: int = Field(default=1024, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)


class RetryPolicy(StrictModel):
    max_transient_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: float = Field(default=60, gt=0, le=600)


class PriceSnapshot(StrictModel):
    currency: Literal["USD"] = "USD"
    effective_date: date
    source_url: HttpUrl
    input_per_million: float = Field(ge=0)
    cached_input_per_million: float | None = Field(default=None, ge=0)
    output_per_million: float = Field(ge=0)


class RunManifest(StrictModel):
    schema_version: Literal["1"]
    run_name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    provider: ProviderConfig
    case_files: tuple[str, ...]
    arms: tuple[Literal["baseline", "concise", "caveman", "if"], ...]
    repetitions: int = Field(default=1, ge=1, le=100)
    arm_order_seed: int = 0
    instruction_placement: Literal["system_suffix"] = "system_suffix"
    generation: GenerationSettings = GenerationSettings()
    retry: RetryPolicy = RetryPolicy()
    price_snapshot: PriceSnapshot | None = None

    @field_validator("arms")
    @classmethod
    def reject_duplicate_arms(
        cls,
        value: tuple[Literal["baseline", "concise", "caveman", "if"], ...],
    ) -> tuple[Literal["baseline", "concise", "caveman", "if"], ...]:
        if len(value) != len(set(value)):
            raise ValueError("arms must be unique")
        return value


class ErrorInfo(StrictModel):
    kind: str
    message: str
    retryable: bool
    request_id: str | None = None


class TokenUsageModel(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_cached_input_tokens(self) -> Self:
        if self.cached_input_tokens is not None and self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens must not exceed input_tokens")
        return self


class RawAttempt(StrictModel):
    schema_version: Literal["1"] = "1"
    run_id: str
    manifest_sha256: str
    case_id: str
    arm: Literal["baseline", "concise", "caveman", "if"]
    repetition: int = Field(ge=0)
    attempt: int = Field(ge=1)
    terminal: bool
    retry_of_attempt: int | None = None
    backoff_ms: int | None = Field(default=None, ge=0)
    prompt_sha256: str
    instruction_sha256: str
    provider: str
    model: str
    started_at: datetime
    elapsed_ms: int = Field(ge=0)
    output_text: str | None = None
    usage: TokenUsageModel | None = None
    request_id: str | None = None
    finish_reason: str | None = None
    error: ErrorInfo | None = None

    @model_validator(mode="after")
    def validate_output_or_error(self) -> Self:
        if (self.output_text is None) == (self.error is None):
            raise ValueError("exactly one of output_text and error must be provided")
        return self


class CheckResult(StrictModel):
    name: str
    passed: bool
    detail: str


class ScoredAttempt(StrictModel):
    raw: RawAttempt
    checks: tuple[CheckResult, ...]
    hard_pass: bool
    semantic_pass: bool | None = None
    judgment_id: str | None = None


class PriceEstimate(StrictModel):
    input_usd: float
    cached_input_usd: float
    output_usd: float
    total_usd: float


class ArmMetrics(StrictModel):
    arm: Literal["baseline", "concise", "caveman", "if"]
    total: int
    hard_passed: int
    semantic_passed: int | None
    provider_errors: int
    retry_attempts: int
    exact_violations: int
    format_violations: int
    median_output_tokens: float | None
    median_output_characters: float | None
    price: PriceEstimate | None = None


class PairedMetrics(StrictModel):
    left_arm: Literal["if"] = "if"
    right_arm: Literal["concise"] = "concise"
    eligible_pairs: int
    median_output_token_delta: float | None
    median_output_character_delta: float | None


class RunSummary(StrictModel):
    schema_version: Literal["1"] = "1"
    quality_gate: Literal["hard", "semantic"]
    raw_attempts: int
    terminal_records: int
    arms: tuple[ArmMetrics, ...]
    paired: PairedMetrics
    price_snapshot: PriceSnapshot | None = None
