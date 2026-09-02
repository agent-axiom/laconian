import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, runtime_checkable

from pydantic import ConfigDict, field_validator, model_validator

from laconian_eval.benchmark.attachments import canonical_json_v1, parse_canonical_json_v1
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

if TYPE_CHECKING:
    from laconian_eval.capsule.attempts import PublicBenchmarkProviderOutcomeV1

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


class StructuredOutputProviderRequestV1(CapsuleModel):
    """One sealed, benchmark-neutral Responses structured-output request."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    model: PublicBenchmarkModelId
    rendered_input: str
    reasoning_effort: ReasoningEffort
    text_verbosity: TextVerbosity
    structured_output_name: str
    structured_output_schema_canonical_json: bytes
    max_output_tokens: int
    store: Literal[False]
    tools: tuple[()]
    service_tier: Literal["default"]
    prompt_cache_mode: Literal["explicit"]
    prompt_cache_ttl: Literal["30m"]

    @field_validator("rendered_input", "structured_output_name")
    @classmethod
    def validate_exact_nfc_text(cls, value: str) -> str:
        if type(value) is not str or not value:
            raise ValueError("structured-output text must be a nonblank exact string")
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValueError("structured-output text must be strict UTF-8") from error
        if unicodedata.normalize("NFC", value) != value:
            raise ValueError("structured-output text must already be NFC")
        return value

    @field_validator("max_output_tokens", mode="before")
    @classmethod
    def validate_positive_exact_output_limit(cls, value: object) -> object:
        if type(value) is not int or value < 1:
            raise ValueError("structured-output limit must be a positive exact integer")
        return value

    @field_validator("store", mode="before")
    @classmethod
    def validate_exact_false_store(cls, value: object) -> object:
        if type(value) is not bool or value is not False:
            raise ValueError("structured-output store must be exact false")
        return value

    @model_validator(mode="after")
    def validate_canonical_schema(self) -> "StructuredOutputProviderRequestV1":
        try:
            schema = parse_canonical_json_v1(self.structured_output_schema_canonical_json)
        except Exception as error:
            raise ValueError("structured-output schema must be canonical JSON v1") from error
        if (
            type(schema) is not dict
            or canonical_json_v1(schema) != self.structured_output_schema_canonical_json
        ):
            raise ValueError("structured-output schema must be one canonical JSON object")
        return self


@runtime_checkable
class StructuredOutputProvider(Protocol):
    def generate_structured_output(
        self, request: StructuredOutputProviderRequestV1
    ) -> "PublicBenchmarkProviderOutcomeV1": ...


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
ReasoningTokenAccounting: TypeAlias = Literal["reported", "not_reported", "invalid"]
ServiceTierStatus: TypeAlias = Literal[
    "reported_default",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "mismatch",
]
AppliedCacheControlStatus: TypeAlias = Literal[
    "reported_exact",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "mismatch",
    "invalid",
]
CacheReadStatus: TypeAlias = Literal[
    "reported_zero",
    "reported_nonzero",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "invalid",
]
CacheWriteStatus: TypeAlias = Literal[
    "reported_zero",
    "reported_nonzero",
    "not_applicable_definitely_not_sent",
    "not_applicable_definitely_rejected",
    "missing",
    "invalid",
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


@dataclass(frozen=True, slots=True, init=False)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    reasoning_token_accounting: ReasoningTokenAccounting = "not_reported"

    def __init__(
        self,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cached_input_tokens: int | None = None,
        *,
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        reasoning_token_accounting: ReasoningTokenAccounting = "not_reported",
    ) -> None:
        """Keep the legacy fourth argument while exposing benchmark accounting."""

        if (
            cached_input_tokens is not None
            and cache_read_tokens is not None
            and cached_input_tokens != cache_read_tokens
        ):
            raise ValueError("conflicting cache-read token counts")
        object.__setattr__(self, "input_tokens", input_tokens)
        object.__setattr__(self, "output_tokens", output_tokens)
        object.__setattr__(self, "total_tokens", total_tokens)
        object.__setattr__(
            self,
            "cache_read_tokens",
            cache_read_tokens if cache_read_tokens is not None else cached_input_tokens,
        )
        object.__setattr__(self, "cache_write_tokens", cache_write_tokens)
        object.__setattr__(self, "reasoning_tokens", reasoning_tokens)
        object.__setattr__(
            self,
            "reasoning_token_accounting",
            reasoning_token_accounting,
        )

    @property
    def cached_input_tokens(self) -> int | None:
        """Legacy read-only spelling retained for runner and report compatibility."""

        return self.cache_read_tokens


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
