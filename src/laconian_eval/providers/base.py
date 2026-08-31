from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias, runtime_checkable

from pydantic import field_validator

from laconian_eval.capsule.schema import (
    CapsuleModel,
    PromptCacheMode,
    PromptCacheTTL,
    PublicBenchmarkModelId,
    ReasoningEffort,
    ReasoningMode,
    ServiceTier,
    TextVerbosity,
)

INPUT_TOKEN_BOUND_VERSION = "openai-utf8-envelope-v1"
OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE = 65_536
OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS = 272_000


def conservative_input_token_bound(*, instruction_utf8_bytes: int, prompt_utf8_bytes: int) -> int:
    """Return one-token-per-byte plus the frozen Responses-envelope allowance."""
    for value in (instruction_utf8_bytes, prompt_utf8_bytes):
        if type(value) is not int or value < 0:
            raise ValueError("input byte counts must be nonnegative integers")
    return instruction_utf8_bytes + prompt_utf8_bytes + OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE


class PublicBenchmarkRequestPolicyV1(CapsuleModel):
    schema_version: Literal["PublicBenchmarkRequestPolicyV1"]
    service_tier: ServiceTier
    prompt_cache_mode: PromptCacheMode
    prompt_cache_ttl: PromptCacheTTL
    reasoning_mode: ReasoningMode
    input_token_bound_version: Literal["openai-utf8-envelope-v1"]
    max_input_tokens: Literal[272000]

    @field_validator("max_input_tokens", mode="before")
    @classmethod
    def validate_exact_token_ceiling(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("max_input_tokens must be an exact integer")
        return value


@dataclass(frozen=True, slots=True)
class PublicBenchmarkRequestV1:
    case_id: str
    arm: str
    repetition: int
    requested_model_id: PublicBenchmarkModelId
    instructions: str | None
    prompt: str
    max_output_tokens: int
    temperature: float | None
    timeout_seconds: float
    policy: PublicBenchmarkRequestPolicyV1
    reasoning_effort: ReasoningEffort | None = None
    text_verbosity: TextVerbosity | None = None


DeliveryCertainty: TypeAlias = Literal[
    "definitely_not_sent",
    "definitely_rejected",
    "response_received",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    case_id: str
    arm: str
    repetition: int
    model: str
    instructions: str | None
    prompt: str
    max_output_tokens: int
    temperature: float | None
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    output_text: str
    usage: TokenUsage | None = None
    request_id: str | None = None
    finish_reason: str | None = None
    response_model: str | None = None
    delivery_certainty: Literal["response_received"] = field(
        default="response_received",
        init=False,
    )


@runtime_checkable
class Provider(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class ProviderError(Exception):
    __slots__ = (
        "_delivery_certainty",
        "_finish_reason",
        "_kind",
        "_message",
        "_request_id",
        "_response_model",
        "_retryable",
        "_usage",
    )

    def __init__(
        self,
        kind: str,
        message: str,
        retryable: bool,
        request_id: str | None = None,
        *,
        delivery_certainty: DeliveryCertainty = "unknown",
        response_model: str | None = None,
        finish_reason: str | None = None,
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self._delivery_certainty = delivery_certainty
        self._finish_reason = finish_reason
        self._kind = kind
        self._message = message
        self._retryable = retryable
        self._request_id = request_id
        self._response_model = response_model
        self._usage = usage

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def message(self) -> str:
        return self._message

    @property
    def retryable(self) -> bool:
        return self._retryable

    @property
    def request_id(self) -> str | None:
        return self._request_id

    @property
    def delivery_certainty(self) -> DeliveryCertainty:
        return self._delivery_certainty

    @property
    def response_model(self) -> str | None:
        return self._response_model

    @property
    def finish_reason(self) -> str | None:
        return self._finish_reason

    @property
    def usage(self) -> TokenUsage | None:
        return self._usage
