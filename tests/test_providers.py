import json
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from laconian_eval.cases import load_response_cases
from laconian_eval.providers import (
    FakeProvider,
    GenerationRequest,
    GenerationResult,
    Provider,
    ProviderError,
    ReplayProvider,
    TokenUsage,
)

ROOT = Path(__file__).parents[1]
REPLAY_FIXTURE = ROOT / "tests/fixtures/replay-responses.yaml"
RESPONSE_CASES = ROOT / "evals/cases/response-smoke.yaml"
ARMS = ("baseline", "concise", "caveman", "if")


def request(
    *,
    case_id: str,
    arm: str,
    repetition: int,
) -> GenerationRequest:
    return GenerationRequest(
        case_id=case_id,
        arm=arm,
        repetition=repetition,
        model="fixture-v1",
        instructions="Synthetic instructions.",
        prompt="Synthetic prompt.",
        max_output_tokens=128,
        temperature=None,
        timeout_seconds=5.0,
    )


def write_yaml(path: Path, content: str) -> None:
    path.write_text(dedent(content).strip() + "\n", encoding="utf-8")


def test_provider_records_are_frozen_and_slotted() -> None:
    records: tuple[tuple[object, str], ...] = (
        (request(case_id="case", arm="if", repetition=0), "case_id"),
        (TokenUsage(input_tokens=3, output_tokens=2, total_tokens=5), "input_tokens"),
        (GenerationResult(output_text="Done."), "output_text"),
    )

    for record, field_name in records:
        assert not hasattr(record, "__dict__")
        with pytest.raises(FrozenInstanceError):
            setattr(record, field_name, "changed")


def test_provider_protocol_is_runtime_checkable() -> None:
    assert isinstance(FakeProvider({}), Provider)


def test_provider_error_exposes_stable_fields_and_message() -> None:
    error = ProviderError(
        kind="rate_limit",
        message="Try again later.",
        retryable=True,
        request_id="request-123",
    )

    assert error.kind == "rate_limit"
    assert error.message == "Try again later."
    assert error.retryable is True
    assert error.request_id == "request-123"
    assert str(error) == "Try again later."
    assert error.args == ("Try again later.",)


def test_fake_provider_returns_scripted_result() -> None:
    provider = FakeProvider({"case:if:0": GenerationResult(output_text="Done.")})
    result = provider.generate(request(case_id="case", arm="if", repetition=0))
    assert result.output_text == "Done."


def test_fake_provider_snapshots_the_script() -> None:
    expected = GenerationResult(output_text="Original.")
    script: dict[str, GenerationResult | ProviderError] = {"case:if:0": expected}
    provider = FakeProvider(script)
    script["case:if:0"] = GenerationResult(output_text="Mutated.")

    assert provider.generate(request(case_id="case", arm="if", repetition=0)) is expected


def test_fake_provider_raises_scripted_error() -> None:
    scripted = ProviderError(
        kind="synthetic_failure",
        message="Synthetic failure.",
        retryable=True,
        request_id="fake-error-1",
    )
    provider = FakeProvider({"case:if:0": scripted})

    with pytest.raises(ProviderError) as error:
        provider.generate(request(case_id="case", arm="if", repetition=0))

    assert error.value is scripted


def test_fake_provider_rejects_missing_key_without_retry() -> None:
    provider = FakeProvider({})

    with pytest.raises(ProviderError, match="missing fake key") as error:
        provider.generate(request(case_id="missing", arm="if", repetition=0))

    assert error.value.retryable is False
    assert error.value.request_id is None


def test_fake_missing_key_is_definitely_not_sent() -> None:
    provider = FakeProvider({})

    with pytest.raises(ProviderError, match="missing fake key") as error:
        provider.generate(request(case_id="missing", arm="if", repetition=0))

    assert error.value.delivery_certainty == "definitely_not_sent"


def test_fake_provider_preserves_scripted_delivery_evidence_by_identity() -> None:
    scripted = ProviderError(
        kind="synthetic_failure",
        message="Synthetic failure.",
        retryable=True,
        delivery_certainty="definitely_rejected",
    )
    provider = FakeProvider({"case:if:0": scripted})

    with pytest.raises(ProviderError) as error:
        provider.generate(request(case_id="case", arm="if", repetition=0))

    assert error.value is scripted
    assert error.value.delivery_certainty == "definitely_rejected"


def test_replay_provider_rejects_missing_key(tmp_path) -> None:
    path = tmp_path / "responses.yaml"
    provider = ReplayProvider.from_path(path)
    with pytest.raises(ProviderError, match="missing replay key") as error:
        provider.generate(request(case_id="missing", arm="if", repetition=0))
    assert error.value.retryable is False
    assert str(path) in str(error.value)


def test_replay_missing_key_is_definitely_not_sent(tmp_path: Path) -> None:
    provider = ReplayProvider.from_path(tmp_path / "missing.yaml")

    with pytest.raises(ProviderError, match="missing replay key") as error:
        provider.generate(request(case_id="missing", arm="if", repetition=0))

    assert error.value.delivery_certainty == "definitely_not_sent"


@pytest.mark.parametrize(
    "entry",
    [
        {"output_text": "Done."},
        {"output_text": "Done.", "response_model": None},
        {"output_text": "Done.", "response_model": " \t"},
        {"output_text": "Done.", "response_model": 7},
    ],
)
def test_replay_provider_requires_exact_nonblank_response_model(
    tmp_path: Path,
    entry: dict[str, object],
) -> None:
    path = tmp_path / "invalid-response-model.yaml"
    path.write_text(yaml.safe_dump({"case:if:0": entry}), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="field 'response_model' must be an exact nonblank string",
    ) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


def test_replay_provider_preserves_per_attempt_response_models(tmp_path: Path) -> None:
    path = tmp_path / "responses.yaml"
    write_yaml(
        path,
        """
        case:if:0:
          output_text: First.
          response_model: returned-model-a
        case:if:1:
          output_text: Second.
          response_model: returned-model-b
        """,
    )
    provider = ReplayProvider.from_path(path)

    first = provider.generate(request(case_id="case", arm="if", repetition=0))
    second = provider.generate(request(case_id="case", arm="if", repetition=1))

    assert first.response_model == "returned-model-a"
    assert second.response_model == "returned-model-b"
    assert first.response_model != request(case_id="case", arm="if", repetition=0).model


def test_replay_provider_rejects_one_invalid_row_among_valid_rows(tmp_path: Path) -> None:
    path = tmp_path / "mixed-validity.yaml"
    write_yaml(
        path,
        """
        case:if:0:
          output_text: Valid.
          response_model: returned-model-a
        case:if:1:
          output_text: Missing returned model.
        case:if:2:
          output_text: Also valid.
          response_model: returned-model-b
        """,
    )

    with pytest.raises(ValueError, match=r"case:if:1.*response_model") as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


def test_replay_provider_rejects_duplicate_top_level_key_with_path(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-replay-key.yaml"
    write_yaml(
        path,
        """
        case:if:0:
          output_text: First.
        case:if:0:
          output_text: Second.
        """,
    )

    with pytest.raises(ValueError, match="duplicate") as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


def test_replay_provider_rejects_duplicate_entry_field_with_path(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-entry-field.yaml"
    write_yaml(
        path,
        """
        case:if:0:
          output_text: First.
          output_text: Second.
        """,
    )

    with pytest.raises(ValueError, match="duplicate") as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


def test_replay_provider_rejects_yaml_merge_key_with_path(tmp_path: Path) -> None:
    path = tmp_path / "merge-key.yaml"
    write_yaml(
        path,
        """
        case:if:0:
          <<: &defaults
            output_text: Default.
          output_text: Done.
        """,
    )

    with pytest.raises(ValueError, match="merge") as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


def test_replay_provider_parses_description_usage_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "responses.yaml"
    write_yaml(
        path,
        """
        description: Synthetic data ignored by replay.
        case:if:0:
          output_text: Done.
          response_model: returned-model-a
          input_tokens: 8
          output_tokens: 2
          total_tokens: 10
          cached_input_tokens: 3
          request_id: replay-request-1
          finish_reason: stop
        case:baseline:0:
          output_text: No usage metadata.
          response_model: returned-model-b
          request_id: null
          finish_reason: null
        """,
    )
    provider = ReplayProvider.from_path(path)

    result = provider.generate(request(case_id="case", arm="if", repetition=0))
    no_usage = provider.generate(request(case_id="case", arm="baseline", repetition=0))

    assert result == GenerationResult(
        output_text="Done.",
        usage=TokenUsage(
            input_tokens=8,
            output_tokens=2,
            total_tokens=10,
            cached_input_tokens=3,
        ),
        request_id="replay-request-1",
        finish_reason="stop",
        response_model="returned-model-a",
    )
    assert no_usage == GenerationResult(
        output_text="No usage metadata.",
        response_model="returned-model-b",
    )


def test_replay_provider_snapshots_loaded_entries(tmp_path: Path) -> None:
    path = tmp_path / "responses.yaml"
    write_yaml(
        path,
        "case:if:0:\n  output_text: Original.\n  response_model: returned-model-a",
    )
    provider = ReplayProvider.from_path(path)
    write_yaml(
        path,
        "case:if:0:\n  output_text: Mutated.\n  response_model: returned-model-b",
    )

    result = provider.generate(request(case_id="case", arm="if", repetition=0))

    assert result.output_text == "Original."


@pytest.mark.parametrize("content", ["entries: [", "- first\n- second", ""])
def test_replay_provider_rejects_malformed_or_nonmapping_yaml_with_path(
    tmp_path: Path,
    content: str,
) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "entry",
    [
        None,
        "not a mapping",
        {},
        {"output_text": 7, "response_model": "returned-model"},
    ],
)
def test_replay_provider_rejects_invalid_entries_with_path(
    tmp_path: Path,
    entry: object,
) -> None:
    path = tmp_path / "invalid-entry.yaml"
    path.write_text(yaml.safe_dump({"case:if:0": entry}), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "entry",
    [
        {"output_text": "Done.", "response_model": "returned-model", "input_tokens": 2},
        {
            "output_text": "Done.",
            "response_model": "returned-model",
            "output_tokens": 1,
            "total_tokens": 3,
        },
        {
            "output_text": "Done.",
            "response_model": "returned-model",
            "cached_input_tokens": 1,
        },
    ],
)
def test_replay_provider_rejects_partial_usage_with_path(
    tmp_path: Path,
    entry: dict[str, object],
) -> None:
    path = tmp_path / "partial-usage.yaml"
    path.write_text(yaml.safe_dump({"case:if:0": entry}), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_tokens", -1),
        ("output_tokens", -1),
        ("total_tokens", -1),
        ("cached_input_tokens", -1),
        ("input_tokens", True),
        ("output_tokens", False),
        ("total_tokens", True),
        ("cached_input_tokens", False),
        ("input_tokens", 1.5),
    ],
)
def test_replay_provider_rejects_invalid_token_counts_with_path(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    path = tmp_path / "invalid-count.yaml"
    entry: dict[str, object] = {
        "output_text": "Done.",
        "response_model": "returned-model",
        "input_tokens": 2,
        "output_tokens": 1,
        "total_tokens": 3,
        "cached_input_tokens": 1,
    }
    entry[field] = value
    path.write_text(yaml.safe_dump({"case:if:0": entry}), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "entry",
    [
        {
            "output_text": "Done.",
            "response_model": "returned-model",
            "input_tokens": 2,
            "output_tokens": 2,
            "total_tokens": 3,
        },
        {
            "output_text": "Done.",
            "response_model": "returned-model",
            "input_tokens": 2,
            "output_tokens": 1,
            "total_tokens": 4,
        },
        {
            "output_text": "Done.",
            "response_model": "returned-model",
            "input_tokens": 2,
            "output_tokens": 1,
            "total_tokens": 3,
            "cached_input_tokens": 3,
        },
    ],
)
def test_replay_provider_rejects_inconsistent_token_counts_with_path(
    tmp_path: Path,
    entry: dict[str, object],
) -> None:
    path = tmp_path / "inconsistent-count.yaml"
    path.write_text(yaml.safe_dump({"case:if:0": entry}), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "entry",
    [
        {
            "output_text": "Done.",
            "response_model": "returned-model",
            "unexpected": "field",
        },
        {"output_text": "Done.", "response_model": "returned-model", "request_id": 1},
        {
            "output_text": "Done.",
            "response_model": "returned-model",
            "finish_reason": False,
        },
    ],
)
def test_replay_provider_rejects_extra_or_invalid_metadata_with_path(
    tmp_path: Path,
    entry: dict[str, object],
) -> None:
    path = tmp_path / "invalid-metadata.yaml"
    path.write_text(yaml.safe_dump({"case:if:0": entry}), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "document",
    [
        {
            "description": 3,
            "case:if:0": {
                "output_text": "Done.",
                "response_model": "returned-model",
            },
        },
        {7: {"output_text": "Done.", "response_model": "returned-model"}},
    ],
)
def test_replay_provider_rejects_invalid_top_level_fields_with_path(
    tmp_path: Path,
    document: dict[object, object],
) -> None:
    path = tmp_path / "invalid-top-level.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        ReplayProvider.from_path(path)

    assert str(path) in str(error.value)


def test_complete_replay_fixture_covers_every_case_arm_once_with_metadata() -> None:
    raw = yaml.safe_load(REPLAY_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    description = raw.pop("description").lower()
    assert "synthetic" in description
    assert "not a benchmark result" in description
    cases = load_response_cases([RESPONSE_CASES])
    expected_keys = {f"{case.id}:{arm}:0" for case in cases for arm in ARMS}

    assert len(cases) == 24
    assert len(raw) == 96
    assert set(raw) == expected_keys
    assert (
        sum(
            type(entry) is dict and entry.get("response_model") == "replay-v1"
            for entry in raw.values()
        )
        == 96
    )

    provider = ReplayProvider.from_path(REPLAY_FIXTURE)
    request_ids: set[str] = set()
    for case in cases:
        for arm in ARMS:
            result = provider.generate(request(case_id=case.id, arm=arm, repetition=0))
            assert result.usage is not None
            assert result.usage.input_tokens > 0
            assert result.usage.output_tokens > 0
            assert result.usage.total_tokens > 0
            assert result.usage.total_tokens == (
                result.usage.input_tokens + result.usage.output_tokens
            )
            assert result.response_model == "replay-v1"
            assert result.request_id
            assert result.request_id not in request_ids
            request_ids.add(result.request_id)
            assert result.finish_reason == "stop"


def test_complete_replay_fixture_has_valid_exact_structured_outputs() -> None:
    provider = ReplayProvider.from_path(REPLAY_FIXTURE)

    for locale in ("en", "ru"):
        for arm in ARMS:
            json_result = provider.generate(
                request(case_id=f"structured-json-{locale}", arm=arm, repetition=0)
            )
            json_value = json.loads(json_result.output_text)
            assert json_result.response_model == "replay-v1"
            assert isinstance(json_value, dict)
            assert set(json_value) == {"risk", "mitigation", "confidence"}

            yaml_result = provider.generate(
                request(case_id=f"structured-yaml-{locale}", arm=arm, repetition=0)
            )
            yaml_value = yaml.safe_load(yaml_result.output_text)
            assert yaml_result.response_model == "replay-v1"
            assert isinstance(yaml_value, dict)
            assert set(yaml_value) == {"status", "reason", "next_step"}


def test_complete_replay_fixture_migration_preserves_all_preexisting_bytes() -> None:
    fixture_bytes = REPLAY_FIXTURE.read_bytes()
    inserted = b"  response_model: replay-v1\n"

    assert fixture_bytes.count(inserted) == 96
    assert fixture_bytes.count(inserted + b"  input_tokens:") == 96
    projection = fixture_bytes.replace(inserted, b"")
    assert sha256(projection).hexdigest() == (
        "9331d6ffbf14355a307ace376c6a3a4c93ca7f645a149e543696e334c040afb1"
    )


def test_complete_replay_fixture_contains_explicit_synthetic_hard_failures() -> None:
    provider = ReplayProvider.from_path(REPLAY_FIXTURE)
    cases = load_response_cases([RESPONSE_CASES])
    case = next(case for case in cases if case.id == "preserve-config-en")
    baseline = provider.generate(request(case_id=case.id, arm="baseline", repetition=0)).output_text
    concise = provider.generate(request(case_id=case.id, arm="concise", repetition=0)).output_text
    if_output = provider.generate(request(case_id=case.id, arm="if", repetition=0)).output_text

    assert any(literal not in baseline for literal in case.hard_constraints.required_literals)
    assert all(literal in concise for literal in case.hard_constraints.required_literals)
    assert len(if_output) < len(concise)
    assert any(literal not in if_output for literal in case.hard_constraints.required_literals)
