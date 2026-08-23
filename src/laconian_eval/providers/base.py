from dataclasses import dataclass
from typing import Protocol, runtime_checkable


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


@runtime_checkable
class Provider(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class ProviderError(Exception):
    __slots__ = ("_kind", "_message", "_request_id", "_retryable")

    def __init__(
        self,
        kind: str,
        message: str,
        retryable: bool,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self._kind = kind
        self._message = message
        self._retryable = retryable
        self._request_id = request_id

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
