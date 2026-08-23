import pytest
from pydantic import ValidationError

from laconian_eval.models import (
    ActivationCase,
    HardConstraints,
    ProviderConfig,
    ResponseCase,
    RunManifest,
)


def test_response_case_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ResponseCase.model_validate(
            {
                "id": "direct-001-en",
                "scenario_id": "direct-001",
                "locale": "en",
                "category": "direct",
                "prompt": "Answer briefly.",
                "unknown": True,
            }
        )


def test_activation_case_requires_a_rationale() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        ActivationCase.model_validate(
            {
                "id": "activation-explicit-en",
                "scenario_id": "activation-explicit",
                "locale": "en",
                "prompt": "/if Explain retries.",
                "expected_activation": True,
            }
        )


def test_manifest_rejects_duplicate_arms() -> None:
    with pytest.raises(ValidationError, match="arms must be unique"):
        RunManifest.model_validate(
            {
                "schema_version": "1",
                "run_name": "smoke",
                "provider": {"kind": "fake", "model": "fake-v1"},
                "case_files": ["evals/cases/response-smoke.yaml"],
                "arms": ["baseline", "baseline"],
            }
        )


def test_response_case_rejects_whitespace_only_prompt() -> None:
    with pytest.raises(ValidationError, match="prompt"):
        ResponseCase.model_validate(
            {
                "id": "direct-001-en",
                "scenario_id": "direct-001",
                "locale": "en",
                "category": "direct",
                "prompt": " \t\n",
            }
        )


def test_activation_case_rejects_whitespace_only_prompt() -> None:
    with pytest.raises(ValidationError, match="prompt"):
        ActivationCase.model_validate(
            {
                "id": "activation-explicit-en",
                "scenario_id": "activation-explicit",
                "locale": "en",
                "prompt": " \t\n",
                "expected_activation": True,
                "rationale": "The explicit trigger should activate the skill.",
            }
        )


def test_activation_case_rejects_whitespace_only_rationale() -> None:
    with pytest.raises(ValidationError, match="rationale"):
        ActivationCase.model_validate(
            {
                "id": "activation-explicit-en",
                "scenario_id": "activation-explicit",
                "locale": "en",
                "prompt": "/if Explain retries.",
                "expected_activation": True,
                "rationale": " \t\n",
            }
        )


def test_hard_constraints_rejects_inverted_sentence_bounds() -> None:
    with pytest.raises(ValidationError, match="min_sentences"):
        HardConstraints.model_validate({"min_sentences": 3, "max_sentences": 2})


@pytest.mark.parametrize("api_key_env", [None, "", "   "])
def test_openai_provider_requires_nonblank_api_key_env(api_key_env: str | None) -> None:
    with pytest.raises(ValidationError, match="api_key_env"):
        ProviderConfig.model_validate(
            {"kind": "openai", "model": "gpt-test", "api_key_env": api_key_env}
        )


@pytest.mark.parametrize("replay_file", [None, "", "   "])
def test_replay_provider_requires_nonblank_replay_file(replay_file: str | None) -> None:
    with pytest.raises(ValidationError, match="replay_file"):
        ProviderConfig.model_validate(
            {"kind": "replay", "model": "fixture-v1", "replay_file": replay_file}
        )
