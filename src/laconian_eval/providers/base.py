from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias, runtime_checkable

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
