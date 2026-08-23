from datetime import date
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
