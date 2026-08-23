from collections.abc import Mapping

from laconian_eval.providers.base import GenerationRequest, GenerationResult, ProviderError


class FakeProvider:
    __slots__ = ("_script",)

    def __init__(self, script: Mapping[str, GenerationResult | ProviderError]) -> None:
        self._script = dict(script)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        key = f"{request.case_id}:{request.arm}:{request.repetition}"
        try:
            outcome = self._script[key]
        except KeyError:
            raise ProviderError(
                kind="missing_fake_key",
                message=f"missing fake key: {key}",
                retryable=False,
            ) from None

        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome
