import pytest
from pydantic import ValidationError

from laconian_eval.models import (
    ActivationCase,
    ActivationCaseFile,
    HardConstraints,
    ProviderConfig,
    ResponseCase,
    ResponseCaseFile,
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


@pytest.mark.parametrize("empty_field", ["case_files", "arms"])
def test_manifest_rejects_empty_plan_collections(empty_field: str) -> None:
    payload: dict[str, object] = {
        "schema_version": "1",
        "run_name": "smoke",
        "provider": {"kind": "fake", "model": "fake-v1"},
        "case_files": ["evals/cases/response-smoke.yaml"],
        "arms": ["baseline"],
    }
    payload[empty_field] = []

    with pytest.raises(ValidationError, match=empty_field):
        RunManifest.model_validate(payload)


def test_response_case_file_rejects_empty_cases() -> None:
    with pytest.raises(ValidationError, match="cases"):
        ResponseCaseFile.model_validate({"schema_version": "1", "kind": "response", "cases": []})


def test_activation_case_file_rejects_empty_cases() -> None:
    with pytest.raises(ValidationError, match="cases"):
        ActivationCaseFile.model_validate(
            {"schema_version": "1", "kind": "activation", "cases": []}
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


def test_hard_constraints_accepts_declared_yaml_keys() -> None:
    constraints = HardConstraints.model_validate(
        {"required_yaml_keys": ["status", "reason", "next_step"]}
    )

    assert constraints.required_yaml_keys == ("status", "reason", "next_step")


def test_hard_constraints_rejects_mixed_structured_formats() -> None:
    with pytest.raises(ValidationError, match="JSON and YAML"):
        HardConstraints.model_validate(
            {
                "required_json_keys": ["answer"],
                "required_yaml_keys": ["answer"],
            }
        )


@pytest.mark.parametrize("field", ["required_json_keys", "required_yaml_keys"])
def test_hard_constraints_rejects_duplicate_structured_keys(field: str) -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        HardConstraints.model_validate({field: ["answer", "answer"]})


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
