from __future__ import annotations

import hashlib
import inspect
import json
import random
import typing
from collections.abc import Iterator
from dataclasses import replace
from itertools import product
from uuid import UUID

import pytest

from laconian_eval import __version__
from laconian_eval import runner as legacy_runner
from laconian_eval.arms import Arm, arm_from_captured_bytes
from laconian_eval.capsule import planning
from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_jsonl,
    sha256_bytes,
    stable_digest,
)
from laconian_eval.capsule.capture import (
    CapturedCaseFile,
    CapturedInputFile,
    CapturedInputs,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1, ResourceLimitError
from laconian_eval.capsule.manifest_models import (
    ResolvedDatasetV2,
    ResolvedManifestV2,
)
from laconian_eval.capsule.planning import (
    PlanningError,
    block_id,
    case_uid,
    materialize_case_index,
    materialize_parent_plan,
    pairing_unit_id,
    plan_item_id,
    recompute_dataset_content_sha256,
    request_config_sha256,
    scenario_uid,
    schedule_digest_bytes,
    validate_case_index,
    validate_parent_plan,
)
from laconian_eval.capsule.record_models import CaseIndexRowV1, InputFileRecordV1, PlanRowV1
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import ResponseCase
from laconian_eval.providers.base import PublicBenchmarkRequestV1, conservative_input_token_bound


def test_request_config_hash_binds_reasoning_cache_and_tier_policy() -> None:
    manifest = _resolved_manifest()
    expected = {
        "provider_kind": "fake",
        "requested_model": "fixture-v1",
        "generation": {
            "max_output_tokens": 128,
            "temperature": 0.25,
            "reasoning_effort": "medium",
            "text_verbosity": "medium",
            "reasoning_mode": "omitted",
            "prompt_cache_mode": "explicit",
            "prompt_cache_ttl": "30m",
            "service_tier": "default",
        },
        "retry": {"max_transient_retries": 2, "timeout_seconds": 60.0},
        "instruction_placement": "system_suffix",
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
        "service_tier": "default",
        "input_token_bound": {
            "version": "openai-utf8-envelope-v1",
            "envelope_allowance_tokens": 65536,
            "standard_tier_max_input_tokens": 272000,
        },
        "store": False,
        "tools": [],
    }
    assert request_config_sha256(manifest) == stable_digest("laconian-request-config-v1", expected)
    baseline = request_config_sha256(manifest)
    for field, value in (
        ("reasoning_effort", None),
        ("reasoning_effort", "low"),
        ("text_verbosity", None),
        ("text_verbosity", "low"),
    ):
        payload = manifest.model_dump(mode="json")
        payload["generation"][field] = value
        assert request_config_sha256(ResolvedManifestV2.model_validate(payload)) != baseline
    encoded = canonical_json(expected)
    for forbidden in (b"prompt_cache_key", b"prompt_cache_retention", b"breakpoint"):
        assert forbidden not in encoded


@pytest.mark.parametrize("field", ["instruction_utf8_bytes", "prompt_utf8_bytes"])
@pytest.mark.parametrize("value", [True, -1, 1.0])
def test_conservative_input_token_bound_rejects_invalid_counts(field: str, value: object) -> None:
    kwargs = {"instruction_utf8_bytes": 0, "prompt_utf8_bytes": 0}
    kwargs[field] = value
    with pytest.raises(ValueError):
        conservative_input_token_bound(**kwargs)  # type: ignore[arg-type]


def test_conservative_input_token_bound_contract_is_exact() -> None:
    assert conservative_input_token_bound(instruction_utf8_bytes=0, prompt_utf8_bytes=0) == 65_536
    assert (
        conservative_input_token_bound(instruction_utf8_bytes=100_000, prompt_utf8_bytes=106_464)
        == 272_000
    )
    assert conservative_input_token_bound.__doc__ == (
        "Return one-token-per-byte plus the frozen Responses-envelope allowance."
    )
    assert tuple(inspect.signature(conservative_input_token_bound).parameters) == (
        "instruction_utf8_bytes",
        "prompt_utf8_bytes",
    )
    hints = typing.get_type_hints(PublicBenchmarkRequestV1)
    assert hints["arm"] is str
    assert hints["instructions"] == str | None
    with pytest.raises(ValueError) as caught:
        conservative_input_token_bound(instruction_utf8_bytes=-1, prompt_utf8_bytes=0)
    assert caught.value.args == ("input byte counts must be nonnegative integers",)


RUN_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
PARENT_MANIFEST_SHA256 = "a" * 64
OTHER_PARENT_MANIFEST_SHA256 = "b" * 64
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
CONCISE_SHA256 = "49f0aab807da85db802937558c8afa5617cfc9e05002327157b321b56b139cd1"
ALPHA_SOURCE_SHA256 = "5aacd83f9c94cf03e9d2a7ae560ea572c2f266bba38f4b570f9ccdc95b70d4d3"
ALPHA_DATASET_SHA256 = "a439686247423f7d68e479c0a31d7b5fa2fce852bc7699d2d0d425d8812bda61"
BETA_DATASET_SHA256 = "1f43096a1c4de5037dad733bd4819722105503d3038c2c85f1cd29afcb85175c"


class _MustNotIterate:
    def __init__(self, reported_length: int) -> None:
        self.reported_length = reported_length

    def __len__(self) -> int:
        return self.reported_length

    def __iter__(self) -> object:
        raise RuntimeError("ITERATED_BEFORE_LIMIT")


class _OneExtraThenExplode:
    def __init__(self, first: InputFileRecordV1, extra: InputFileRecordV1) -> None:
        self.first = first
        self.extra = extra

    def __len__(self) -> int:
        return 1

    def __iter__(self) -> Iterator[InputFileRecordV1]:
        yield self.first
        yield self.extra
        raise RuntimeError("ITERATED_PAST_EXPECTED_MEMBERS")


def _case(
    case_id: str,
    *,
    scenario_id: str,
    locale: str,
    category: str,
    prompt: str,
) -> ResponseCase:
    return ResponseCase.model_validate(
        {
            "id": case_id,
            "scenario_id": scenario_id,
            "locale": locale,
            "category": category,
            "prompt": prompt,
        }
    )


def _case_input(
    source_ordinal: int,
    dataset_id: str,
    data: bytes,
    cases: tuple[ResponseCase, ...],
) -> tuple[CapturedInputFile, CapturedCaseFile]:
    record = InputFileRecordV1(
        role="case",
        role_ordinal=source_ordinal,
        logical_locator=f"case_files[{source_ordinal}]",
        capsule_path=f"inputs/cases/{source_ordinal:03d}.yaml",
        byte_length=len(data),
        sha256=sha256_bytes(data),
        dataset_id=dataset_id,
        binding_id=None,
    )
    captured = CapturedInputFile(record=record, data=data)
    return captured, CapturedCaseFile(
        source_ordinal=source_ordinal,
        dataset_id=dataset_id,
        input_file=captured,
        cases=cases,
    )


def _arm_input(
    role_ordinal: int,
    name: str,
    member: str,
    data: bytes,
) -> CapturedInputFile:
    path = (
        f"inputs/arms/{member}"
        if name in ("baseline", "concise")
        else f"inputs/arms/{name}/{member}"
    )
    return CapturedInputFile(
        record=InputFileRecordV1(
            role="arm",
            role_ordinal=role_ordinal,
            logical_locator=f"arm[{name}]/{member}",
            capsule_path=path,
            byte_length=len(data),
            sha256=sha256_bytes(data),
            dataset_id=None,
            binding_id=None,
        ),
        data=data,
    )


def _fixture_cases() -> tuple[tuple[ResponseCase, ...], tuple[ResponseCase, ...]]:
    return (
        (
            _case(
                "alpha-en",
                scenario_id="shared",
                locale="en",
                category="direct",
                prompt="Answer \u03b1.",
            ),
            _case(
                "alpha-ru",
                scenario_id="shared",
                locale="ru",
                category="direct",
                prompt="Ответь \u03b1.",
            ),
        ),
        (
            _case(
                "beta-en",
                scenario_id="shared",
                locale="en",
                category="coding",
                prompt="Write β.",
            ),
            _case(
                "beta-ru",
                scenario_id="shared",
                locale="ru",
                category="coding",
                prompt="Напиши β.",
            ),
        ),
    )


def _resolved_manifest(
    *,
    repetitions: int = 2,
    arm_order_seed: int = -17,
    max_output_tokens: int = 128,
) -> ResolvedManifestV2:
    return ResolvedManifestV2.model_validate(
        {
            "schema_version": "2",
            "source_manifest_schema_version": "2",
            "runner_version": __version__,
            "run_name": "planning-fixture",
            "provider": {
                "kind": "fake",
                "model": "fixture-v1",
                "api_key_env": None,
                "replay_file": None,
            },
            "case_files": ["inputs/cases/000.yaml", "inputs/cases/001.yaml"],
            "arms": ["baseline", "concise", "if"],
            "repetitions": repetitions,
            "arm_order_seed": arm_order_seed,
            "instruction_placement": "system_suffix",
            "schedule_algorithm_version": "laconian-schedule-v1",
            "generation": {
                "max_output_tokens": max_output_tokens,
                "temperature": 0.25,
                "reasoning_effort": "medium",
                "text_verbosity": "medium",
                "reasoning_mode": "omitted",
                "prompt_cache_mode": "explicit",
                "prompt_cache_ttl": "30m",
                "service_tier": "default",
            },
            "retry": {"max_transient_retries": 2, "timeout_seconds": 60.0},
            "price_snapshot": None,
            "capsule": {
                "run_purpose": "integration_smoke",
                "claim_intent": "none",
                "datasets": [
                    {
                        "dataset_id": "dataset-alpha",
                        "dataset_version": "v1",
                        "role": "smoke",
                        "case_schema_version": "1",
                        "case_file_ordinals": [0],
                        "dataset_content_sha256": ALPHA_DATASET_SHA256,
                    },
                    {
                        "dataset_id": "dataset-beta",
                        "dataset_version": "v2",
                        "role": "challenge",
                        "case_schema_version": "1",
                        "case_file_ordinals": [1],
                        "dataset_content_sha256": BETA_DATASET_SHA256,
                    },
                ],
                "comparisons": [],
                "protocol_bindings": [],
            },
        }
    )


def _captured_inputs() -> CapturedInputs:
    alpha_cases, beta_cases = _fixture_cases()
    alpha_input, alpha_file = _case_input(0, "dataset-alpha", b"alpha source\n", alpha_cases)
    beta_input, beta_file = _case_input(1, "dataset-beta", b"beta source\n", beta_cases)

    baseline_bytes = b""
    concise_bytes = b"Answer concisely."
    if_bytes = b"Answer completely, briefly."
    arms = (
        arm_from_captured_bytes("baseline", baseline_bytes),
        arm_from_captured_bytes("concise", concise_bytes),
        arm_from_captured_bytes("if", if_bytes),
    )
    arm_files = (
        _arm_input(0, "baseline", "baseline.txt", baseline_bytes),
        _arm_input(1, "concise", "concise.txt", concise_bytes),
        _arm_input(2, "if", "SKILL.md", if_bytes),
    )
    manifest = _resolved_manifest()
    manifest_bytes = canonical_json(manifest.model_dump(mode="json"))
    files = tuple(
        sorted(
            (*arm_files, alpha_input, beta_input),
            key=lambda item: item.record.capsule_path.encode("utf-8"),
        )
    )
    return CapturedInputs(
        source_manifest_commitment_sha256=sha256_bytes(b"source manifest"),
        resolved_manifest=manifest,
        resolved_manifest_bytes=manifest_bytes,
        manifest_sha256=sha256_bytes(manifest_bytes),
        files=files,
        case_files=(alpha_file, beta_file),
        arms=arms,
    )


def _replace_capture(
    captured: CapturedInputs,
    *,
    manifest: ResolvedManifestV2 | None = None,
    case_files: tuple[CapturedCaseFile, ...] | None = None,
    files: tuple[CapturedInputFile, ...] | None = None,
    arms: tuple[Arm, ...] | None = None,
) -> CapturedInputs:
    replacement_manifest = captured.resolved_manifest if manifest is None else manifest
    manifest_bytes = canonical_json(replacement_manifest.model_dump(mode="json"))
    return CapturedInputs(
        source_manifest_commitment_sha256=captured.source_manifest_commitment_sha256,
        resolved_manifest=replacement_manifest,
        resolved_manifest_bytes=manifest_bytes,
        manifest_sha256=sha256_bytes(manifest_bytes),
        files=captured.files if files is None else files,
        case_files=captured.case_files if case_files is None else case_files,
        arms=captured.arms if arms is None else arms,
    )


def _assert_planning_error(code: str, call: object) -> None:
    assert callable(call)
    with pytest.raises(PlanningError) as caught:
        call()
    assert caught.value.code == code


def _independent_stable_digest(domain: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8", errors="strict")
    return hashlib.sha256(domain.encode("utf-8") + b"\0" + encoded).hexdigest()


def _parent_plan_jsonl(rows: tuple[PlanRowV1, ...]) -> bytes:
    return canonical_jsonl(row.model_dump(mode="json") for row in rows)


def test_parent_plan_ids_are_stable_without_run_identity() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)

    first = planning.materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )
    second = planning.materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    assert first == second
    assert _parent_plan_jsonl(first) == _parent_plan_jsonl(second)
    signature = inspect.signature(planning.materialize_parent_plan)
    assert tuple(signature.parameters) == (
        "parent_manifest_sha256",
        "resolved_manifest",
        "case_index",
        "captured_arms",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in signature.parameters.values()
    )
    validation_signature = inspect.signature(planning.validate_parent_plan)
    assert tuple(validation_signature.parameters) == (
        "rows",
        "parent_manifest_sha256",
        "resolved_manifest",
        "case_index",
        "captured_arms",
    )
    assert validation_signature.parameters["rows"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(
        validation_signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in (
            "parent_manifest_sha256",
            "resolved_manifest",
            "case_index",
            "captured_arms",
        )
    )
    assert not hasattr(planning, "materialize_plan")
    assert not hasattr(planning, "validate_plan")


def test_parent_manifest_digest_changes_only_parent_plan_identities() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    first = planning.materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )
    second = planning.materialize_parent_plan(
        parent_manifest_sha256=OTHER_PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    for left, right in zip(first, second, strict=True):
        assert left.plan_item_id != right.plan_item_id
        assert left.block_id != right.block_id
        assert left.pairing_unit_id != right.pairing_unit_id
        assert left.model_dump(exclude={"plan_item_id", "block_id", "pairing_unit_id"}) == (
            right.model_dump(exclude={"plan_item_id", "block_id", "pairing_unit_id"})
        )
        assert left.request_config_sha256 == right.request_config_sha256
        assert left.input_token_bound == right.input_token_bound


@pytest.mark.parametrize(
    "parent_manifest_sha256",
    ["A" * 64, "a" * 63, "g" * 64, "", None, True],
)
def test_parent_plan_requires_canonical_parent_manifest_digest(
    parent_manifest_sha256: object,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    rows = planning.materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    for call in (
        lambda: planning.materialize_parent_plan(
            parent_manifest_sha256=parent_manifest_sha256,  # type: ignore[arg-type]
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
        lambda: planning.validate_parent_plan(
            rows,
            parent_manifest_sha256=parent_manifest_sha256,  # type: ignore[arg-type]
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
    ):
        _assert_planning_error("invalid_parent_manifest_sha256", call)


def test_parent_identity_preimages_are_exact() -> None:
    case_identity = "c" * 64
    instruction_sha256 = "d" * 64
    request_config_digest = "e" * 64
    repetition = 3
    input_token_bound = 65_579

    block_payload = {
        "parent_manifest_sha256": PARENT_MANIFEST_SHA256,
        "case_uid": case_identity,
        "repetition": repetition,
    }
    item_payload = {
        **block_payload,
        "arm": "if",
        "instruction_sha256": instruction_sha256,
        "request_config_sha256": request_config_digest,
        "input_token_bound": input_token_bound,
    }
    assert block_id(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        case_uid=case_identity,
        repetition=repetition,
    ) == _independent_stable_digest("laconian-parent-block-v1", block_payload)
    assert pairing_unit_id(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        case_uid=case_identity,
        repetition=repetition,
    ) == _independent_stable_digest("laconian-parent-pairing-unit-v1", block_payload)
    assert plan_item_id(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        case_uid=case_identity,
        repetition=repetition,
        arm="if",
        instruction_sha256=instruction_sha256,
        request_config_sha256=request_config_digest,
        input_token_bound=input_token_bound,
    ) == _independent_stable_digest("laconian-parent-plan-item-v1", item_payload)

    expected_parameters = {
        block_id: ("parent_manifest_sha256", "case_uid", "repetition"),
        pairing_unit_id: ("parent_manifest_sha256", "case_uid", "repetition"),
        plan_item_id: (
            "parent_manifest_sha256",
            "case_uid",
            "repetition",
            "arm",
            "instruction_sha256",
            "request_config_sha256",
            "input_token_bound",
        ),
    }
    for helper, names in expected_parameters.items():
        signature = inspect.signature(helper)
        assert tuple(signature.parameters) == names
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for parameter in signature.parameters.values()
        )

    with pytest.raises(TypeError):
        block_id(RUN_ID, case_identity, repetition)  # type: ignore[misc]
    with pytest.raises(TypeError):
        pairing_unit_id(RUN_ID, case_identity, repetition)  # type: ignore[misc]
    with pytest.raises(TypeError):
        plan_item_id(  # type: ignore[misc]
            RUN_ID,
            case_identity,
            repetition,
            "if",
            instruction_sha256,
            request_config_digest,
        )


def test_case_index_and_plan_bind_default_service_tier_and_input_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    prompts = {
        case.id: case.prompt for case_file in captured.case_files for case in case_file.cases
    }
    assert {row.prompt_utf8_bytes for row in case_index} == {
        len(prompt.encode("utf-8", errors="strict")) for prompt in prompts.values()
    }
    assert all(
        row.prompt_utf8_bytes == len(prompts[row.case_id].encode("utf-8", errors="strict"))
        for row in case_index
    )
    assert len("Ответь \u03b1.") != len("Ответь \u03b1.".encode("utf-8", errors="strict"))

    def forbidden_instruction_bytes(_: Arm) -> bytes:
        raise AssertionError("planning must derive bytes from Arm.instruction")

    monkeypatch.setattr(Arm, "instruction_bytes", property(forbidden_instruction_bytes))
    assert "instruction_bytes" not in Arm.__dataclass_fields__
    parent_plan = planning.materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    config_digest = request_config_sha256(captured.resolved_manifest)
    assert all(row.request_config_sha256 == config_digest for row in parent_plan)
    arms = {arm.name: arm for arm in captured.arms}
    first_case = case_index[0]
    for arm_name in ("baseline", "concise", "if"):
        arm = arms[arm_name]
        instruction_bytes = (
            b"" if arm.instruction is None else arm.instruction.encode("utf-8", errors="strict")
        )
        row = next(
            row
            for row in parent_plan
            if row.case_uid == first_case.case_uid and row.repetition == 0 and row.arm == arm_name
        )
        expected_bound = first_case.prompt_utf8_bytes + len(instruction_bytes) + 65_536
        assert row.input_token_bound == expected_bound
        assert row.plan_item_id == plan_item_id(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            case_uid=row.case_uid,
            repetition=row.repetition,
            arm=row.arm,
            instruction_sha256=row.instruction_sha256,
            request_config_sha256=config_digest,
            input_token_bound=expected_bound,
        )

    manifest_payload = captured.resolved_manifest.model_dump(mode="json")
    del manifest_payload["generation"]["service_tier"]
    with pytest.raises(ValueError):
        ResolvedManifestV2.model_validate(manifest_payload)
    manifest_payload = captured.resolved_manifest.model_dump(mode="json")
    manifest_payload["generation"]["service_tier"] = "auto"
    with pytest.raises(ValueError):
        ResolvedManifestV2.model_validate(manifest_payload)

    forged_generation = type(captured.resolved_manifest.generation).model_construct(
        **(captured.resolved_manifest.generation.__dict__ | {"service_tier": "auto"})
    )
    forged_manifest = ResolvedManifestV2.model_construct(
        **(captured.resolved_manifest.__dict__ | {"generation": forged_generation})
    )
    _assert_planning_error(
        "invalid_resolved_manifest",
        lambda: planning.materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=forged_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
    )


def test_complete_input_bound_preflight_precedes_identity_and_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    last_instruction = captured.arms[-1].instruction
    assert last_instruction is not None
    last_instruction_utf8_bytes = len(last_instruction.encode("utf-8", errors="strict"))
    oversized_prompt_bytes = (
        planning.OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS
        - planning.OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE
        - last_instruction_utf8_bytes
        + 1
    )
    assert all(
        conservative_input_token_bound(
            instruction_utf8_bytes=(
                0
                if arm.instruction is None
                else len(arm.instruction.encode("utf-8", errors="strict"))
            ),
            prompt_utf8_bytes=oversized_prompt_bytes,
        )
        <= planning.OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS
        for arm in captured.arms[:-1]
    )
    assert (
        conservative_input_token_bound(
            instruction_utf8_bytes=last_instruction_utf8_bytes,
            prompt_utf8_bytes=oversized_prompt_bytes,
        )
        == planning.OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS + 1
    )
    oversized_index = (
        *case_index[:-1],
        case_index[-1].model_copy(update={"prompt_utf8_bytes": oversized_prompt_bytes}),
    )
    calls = {
        "request_config_sha256": 0,
        "block_id": 0,
        "pairing_unit_id": 0,
        "plan_item_id": 0,
        "PlanRowV1": 0,
    }

    def counted(name: str, target: object) -> object:
        assert callable(target)

        def wrapper(*args: object, **kwargs: object) -> object:
            calls[name] += 1
            return target(*args, **kwargs)

        return wrapper

    for name in calls:
        monkeypatch.setattr(planning, name, counted(name, getattr(planning, name)))

    _assert_planning_error(
        "public_benchmark_input_bound_exceeded",
        lambda: planning.materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=oversized_index,
            captured_arms=captured.arms,
        ),
    )
    assert calls == dict.fromkeys(calls, 0)


def test_parent_plan_input_bound_boundary_and_error_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    baseline_manifest = captured.resolved_manifest.model_copy(update={"arms": ("baseline",)})
    exact_prompt_bytes = (
        planning.OPENAI_STANDARD_TIER_MAX_INPUT_TOKENS
        - planning.OPENAI_RESPONSES_ENVELOPE_TOKEN_ALLOWANCE
    )
    exact_index = tuple(
        row.model_copy(update={"prompt_utf8_bytes": exact_prompt_bytes}) for row in case_index
    )
    exact_plan = planning.materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=baseline_manifest,
        case_index=exact_index,
        captured_arms=(captured.arms[0],),
    )
    assert {row.input_token_bound for row in exact_plan} == {272_000}

    oversized_index = (
        *exact_index[:-1],
        exact_index[-1].model_copy(update={"prompt_utf8_bytes": exact_prompt_bytes + 1}),
    )
    _assert_planning_error(
        "public_benchmark_input_bound_exceeded",
        lambda: planning.materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=baseline_manifest,
            case_index=oversized_index,
            captured_arms=(captured.arms[0],),
        ),
    )
    candidate_revalidations = 0
    original_revalidate_plan_row = planning._revalidate_plan_row

    def counted_revalidate_plan_row(value: object) -> PlanRowV1:
        nonlocal candidate_revalidations
        candidate_revalidations += 1
        return original_revalidate_plan_row(value)

    with monkeypatch.context() as patch:
        patch.setattr(planning, "_revalidate_plan_row", counted_revalidate_plan_row)
        _assert_planning_error(
            "public_benchmark_input_bound_exceeded",
            lambda: planning.validate_parent_plan(
                exact_plan,
                parent_manifest_sha256=PARENT_MANIFEST_SHA256,
                resolved_manifest=baseline_manifest,
                case_index=oversized_index,
                captured_arms=(captured.arms[0],),
            ),
        )
    assert candidate_revalidations == 0

    ordinary_plan = planning.materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=baseline_manifest,
        case_index=case_index,
        captured_arms=(captured.arms[0],),
    )
    forged_index = (
        case_index[0].model_copy(update={"prompt_utf8_bytes": case_index[0].prompt_utf8_bytes + 1}),
        *case_index[1:],
    )
    _assert_planning_error(
        "plan_mismatch",
        lambda: planning.validate_parent_plan(
            ordinary_plan,
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=baseline_manifest,
            case_index=forged_index,
            captured_arms=(captured.arms[0],),
        ),
    )
    forged_plan = (
        ordinary_plan[0].model_copy(
            update={"input_token_bound": ordinary_plan[0].input_token_bound + 1}
        ),
        *ordinary_plan[1:],
    )
    _assert_planning_error(
        "plan_mismatch",
        lambda: planning.validate_parent_plan(
            forged_plan,
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=baseline_manifest,
            case_index=case_index,
            captured_arms=(captured.arms[0],),
        ),
    )


def test_section_9_identity_preimages_and_digests_are_literal_goldens() -> None:
    captured = _captured_inputs()
    dataset = captured.resolved_manifest.capsule.datasets[0]
    case_definition = "c" * 64

    expected_dataset_preimage = (
        b'{"dataset_id":"dataset-alpha","dataset_version":"v1","members":['
        b'{"byte_length":13,"capsule_path":"inputs/cases/000.yaml",'
        b'"sha256":"5aacd83f9c94cf03e9d2a7ae560ea572c2f266bba38f4b570f9ccdc95b70d4d3",'
        b'"source_ordinal":0}]}'
    )
    expected_scenario_preimage = (
        b'{"dataset_id":"dataset-alpha","dataset_version":"v1","scenario_id":"shared"}'
    )
    expected_scenario_uid = "67d5a948d6b023d61109f0657532dbe79d60e675c2b0a0f40606db168075f3bc"
    expected_case_preimage = (
        b'{"case_definition_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
        b'"case_id":"alpha-en","locale":"en",'
        b'"scenario_uid":"67d5a948d6b023d61109f0657532dbe79d60e675c2b0a0f40606db168075f3bc"}'
    )
    expected_case_uid = "70d24b0bc44419392753b3d008c0c7c6f57f34ea05e3715221b826196346d1bf"
    expected_schedule_preimage = (
        b'{"arm":"if","case_uid":"70d24b0bc44419392753b3d008c0c7c6f57f34ea05e3715221b826196346d1bf",'
        b'"repetition":0,"seed":-17}'
    )
    expected_request_preimage = (
        b'{"generation":{"max_output_tokens":128,"prompt_cache_mode":"explicit",'
        b'"prompt_cache_ttl":"30m","reasoning_effort":"medium",'
        b'"reasoning_mode":"omitted","service_tier":"default","temperature":0.25,'
        b'"text_verbosity":"medium"},"input_token_bound":'
        b'{"envelope_allowance_tokens":65536,"standard_tier_max_input_tokens":272000,'
        b'"version":"openai-utf8-envelope-v1"},"instruction_placement":"system_suffix",'
        b'"prompt_cache_options":{"mode":"explicit","ttl":"30m"},"provider_kind":"fake",'
        b'"requested_model":"fixture-v1","retry":{"max_transient_retries":2,'
        b'"timeout_seconds":60.0},"service_tier":"default","store":false,"tools":[]}'
    )
    expected_request_sha256 = "63a99d3945a095b3a1b31e556eebcbde36571ac1d6212d64ef2a0f5543f6d923"

    assert (
        canonical_json(
            {
                "dataset_id": "dataset-alpha",
                "dataset_version": "v1",
                "members": [
                    {
                        "source_ordinal": 0,
                        "capsule_path": "inputs/cases/000.yaml",
                        "byte_length": 13,
                        "sha256": ALPHA_SOURCE_SHA256,
                    }
                ],
            }
        )
        == expected_dataset_preimage
    )
    assert (
        canonical_json(
            {
                "dataset_id": "dataset-alpha",
                "dataset_version": "v1",
                "scenario_id": "shared",
            }
        )
        == expected_scenario_preimage
    )
    assert (
        canonical_json(
            {
                "scenario_uid": expected_scenario_uid,
                "case_id": "alpha-en",
                "locale": "en",
                "case_definition_sha256": case_definition,
            }
        )
        == expected_case_preimage
    )
    assert (
        canonical_json({"seed": -17, "case_uid": expected_case_uid, "repetition": 0, "arm": "if"})
        == expected_schedule_preimage
    )
    assert (
        canonical_json(
            {
                "provider_kind": "fake",
                "requested_model": "fixture-v1",
                "generation": {
                    "max_output_tokens": 128,
                    "temperature": 0.25,
                    "reasoning_effort": "medium",
                    "text_verbosity": "medium",
                    "reasoning_mode": "omitted",
                    "prompt_cache_mode": "explicit",
                    "prompt_cache_ttl": "30m",
                    "service_tier": "default",
                },
                "retry": {"max_transient_retries": 2, "timeout_seconds": 60.0},
                "instruction_placement": "system_suffix",
                "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
                "service_tier": "default",
                "input_token_bound": {
                    "version": "openai-utf8-envelope-v1",
                    "envelope_allowance_tokens": 65536,
                    "standard_tier_max_input_tokens": 272000,
                },
                "store": False,
                "tools": [],
            }
        )
        == expected_request_preimage
    )
    assert recompute_dataset_content_sha256(dataset, (captured.case_files[0].record,)) == (
        "a439686247423f7d68e479c0a31d7b5fa2fce852bc7699d2d0d425d8812bda61"
    )
    assert scenario_uid("dataset-alpha", "v1", "shared") == expected_scenario_uid
    assert case_uid(expected_scenario_uid, "alpha-en", "en", case_definition) == (expected_case_uid)
    assert schedule_digest_bytes(-17, expected_case_uid, 0, "if").hex() == (
        "eea99ed5a8f4f6baf68c90dbbc13dc7f8f5b50cf080b39e058784f0f99f13146"
    )
    assert request_config_sha256(captured.resolved_manifest) == expected_request_sha256


def test_case_index_materializes_exact_source_record_order_and_hashes() -> None:
    captured = _captured_inputs()

    rows = materialize_case_index(captured, captured.resolved_manifest)

    assert all(isinstance(row, CaseIndexRowV1) for row in rows)
    assert [(row.source_ordinal, row.record_ordinal, row.case_id) for row in rows] == [
        (0, 0, "alpha-en"),
        (0, 1, "alpha-ru"),
        (1, 0, "beta-en"),
        (1, 1, "beta-ru"),
    ]
    assert rows[0].model_dump(mode="json") == {
        "dataset_id": "dataset-alpha",
        "dataset_version": "v1",
        "dataset_role": "smoke",
        "source_ordinal": 0,
        "record_ordinal": 0,
        "case_id": "alpha-en",
        "case_uid": "8495358afca41f6b2296a2de2ff24fe40bd7b35b798540f5efddc18c5202db23",
        "scenario_id": "shared",
        "scenario_uid": "67d5a948d6b023d61109f0657532dbe79d60e675c2b0a0f40606db168075f3bc",
        "locale": "en",
        "category": "direct",
        "case_definition_sha256": (
            "04fc29aa501e7506a7867d781a399c41b9c5da2d3dc18d035580b22f4b04705e"
        ),
        "prompt_sha256": "d31758a1bb0af554138c9a0bcf1022df0b203bf0d2845f32d8e3a8830aa821bf",
        "prompt_utf8_bytes": 10,
    }
    assert rows[0].case_definition_sha256 == response_case_sha256(captured.case_files[0].cases[0])
    assert rows[0].prompt_sha256 == hashlib.sha256("Answer \u03b1.".encode()).hexdigest()
    assert rows[0].scenario_uid == rows[1].scenario_uid
    assert rows[2].scenario_uid == rows[3].scenario_uid
    assert rows[0].scenario_uid != rows[2].scenario_uid
    assert len({row.case_id for row in rows}) == len(rows)
    assert len({row.case_uid for row in rows}) == len(rows)
    validate_case_index(rows, captured, captured.resolved_manifest)


def test_dataset_digest_recomputation_sorts_members_by_source_ordinal() -> None:
    captured = _captured_inputs()
    records = tuple(case_file.record for case_file in reversed(captured.case_files))
    dataset = ResolvedDatasetV2.model_validate(
        {
            "dataset_id": "combined",
            "dataset_version": "v3",
            "role": "development",
            "case_schema_version": "1",
            "case_file_ordinals": [1, 0],
            "dataset_content_sha256": "0" * 64,
        }
    )
    adjusted = tuple(record.model_copy(update={"dataset_id": "combined"}) for record in records)
    expected_payload = {
        "dataset_id": "combined",
        "dataset_version": "v3",
        "members": [
            {
                "source_ordinal": record.role_ordinal,
                "capsule_path": record.capsule_path,
                "byte_length": record.byte_length,
                "sha256": record.sha256,
            }
            for record in sorted(adjusted, key=lambda item: item.role_ordinal)
        ],
    }
    expected = hashlib.sha256(
        b"laconian-dataset-content-v1\0" + canonical_json(expected_payload)
    ).hexdigest()

    assert recompute_dataset_content_sha256(dataset, adjusted) == expected


def test_dataset_digest_bounds_sequence_to_exact_declared_members_before_iteration() -> None:
    captured = _captured_inputs()
    dataset = captured.resolved_manifest.capsule.datasets[0]
    first = captured.case_files[0].record
    extra = captured.case_files[1].record.model_copy(update={"dataset_id": dataset.dataset_id})

    for records in (
        _MustNotIterate(2),
        _OneExtraThenExplode(first, extra),
    ):
        with pytest.raises(PlanningError) as caught:
            recompute_dataset_content_sha256(  # type: ignore[arg-type]
                dataset,
                records,
            )
        assert caught.value.code == "dataset_content_mismatch"
        assert "ITERATED_" not in str(caught.value)


def test_case_index_rejects_capture_manifest_and_dataset_content_disagreement() -> None:
    captured = _captured_inputs()
    other_manifest = captured.resolved_manifest.model_copy(update={"arm_order_seed": 99})
    _assert_planning_error(
        "manifest_capture_mismatch",
        lambda: materialize_case_index(captured, other_manifest),
    )

    payload = captured.resolved_manifest.model_dump(mode="python", round_trip=True)
    payload["capsule"]["datasets"][0]["dataset_content_sha256"] = "0" * 64
    tampered_manifest = ResolvedManifestV2.model_validate(payload)
    tampered_capture = _replace_capture(captured, manifest=tampered_manifest)
    _assert_planning_error(
        "dataset_content_mismatch",
        lambda: materialize_case_index(tampered_capture, tampered_manifest),
    )

    wrong_owner = replace(captured.case_files[0], dataset_id="dataset-beta")
    owner_capture = _replace_capture(
        captured,
        case_files=(wrong_owner, captured.case_files[1]),
    )
    _assert_planning_error(
        "case_capture_mismatch",
        lambda: materialize_case_index(owner_capture, owner_capture.resolved_manifest),
    )

    missing_record_files = tuple(
        item
        for item in captured.files
        if item.record.role != "case" or item.record.role_ordinal != 0
    )
    missing_record_capture = _replace_capture(captured, files=missing_record_files)
    _assert_planning_error(
        "case_capture_mismatch",
        lambda: materialize_case_index(
            missing_record_capture, missing_record_capture.resolved_manifest
        ),
    )


def test_case_index_rejects_duplicate_ids_and_incomplete_dataset_locales() -> None:
    captured = _captured_inputs()
    duplicate = captured.case_files[1].cases[0].model_copy(update={"id": "alpha-en"})
    duplicate_file = replace(
        captured.case_files[1],
        cases=(duplicate, captured.case_files[1].cases[1]),
    )
    duplicate_capture = _replace_capture(
        captured,
        case_files=(captured.case_files[0], duplicate_file),
    )
    _assert_planning_error(
        "duplicate_case_id",
        lambda: materialize_case_index(duplicate_capture, duplicate_capture.resolved_manifest),
    )

    incomplete_file = replace(
        captured.case_files[1],
        cases=(captured.case_files[1].cases[0],),
    )
    incomplete_capture = _replace_capture(
        captured,
        case_files=(captured.case_files[0], incomplete_file),
    )
    _assert_planning_error(
        "dataset_locale_ownership",
        lambda: materialize_case_index(incomplete_capture, incomplete_capture.resolved_manifest),
    )


def test_case_index_validation_recomputes_every_row_and_rejects_tampering() -> None:
    captured = _captured_inputs()
    rows = materialize_case_index(captured, captured.resolved_manifest)
    altered = rows[0].model_copy(update={"prompt_sha256": "0" * 64})
    candidates = (
        rows[:-1],
        (*rows, rows[-1]),
        (rows[0], rows[0], *rows[2:]),
        (altered, *rows[1:]),
        tuple(reversed(rows)),
    )

    for candidate in candidates:
        _assert_planning_error(
            "case_index_mismatch",
            lambda candidate=candidate: validate_case_index(
                candidate, captured, captured.resolved_manifest
            ),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "secret-forged-category"),
        ("locale", "fr"),
    ],
)
def test_case_index_revalidates_legacy_response_cases_before_hashing_without_echo(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    captured = _captured_inputs()
    forged_case = captured.case_files[0].cases[0].model_copy(update={field: value})
    forged_file = replace(
        captured.case_files[0],
        cases=(forged_case, captured.case_files[0].cases[1]),
    )
    forged_capture = _replace_capture(
        captured,
        case_files=(forged_file, captured.case_files[1]),
    )

    def forbidden_hash(_: ResponseCase) -> str:
        raise AssertionError("invalid cases must be rejected before hashing")

    monkeypatch.setattr(planning, "response_case_sha256", forbidden_hash)
    with pytest.raises(PlanningError) as caught:
        materialize_case_index(forged_capture, forged_capture.resolved_manifest)
    assert caught.value.code == "invalid_case_record"
    assert value not in str(caught.value)


def test_case_index_rejects_constructed_response_case_missing_required_field() -> None:
    captured = _captured_inputs()
    payload = dict(captured.case_files[0].cases[0].__dict__)
    del payload["id"]
    forged_case = ResponseCase.model_construct(**payload)
    forged_file = replace(
        captured.case_files[0],
        cases=(forged_case, captured.case_files[0].cases[1]),
    )
    forged_capture = _replace_capture(
        captured,
        case_files=(forged_file, captured.case_files[1]),
    )

    with pytest.raises(PlanningError) as caught:
        materialize_case_index(forged_capture, forged_capture.resolved_manifest)
    assert caught.value.code == "invalid_case_record"
    assert str(caught.value) == "capsule planning rejected"


def test_case_index_fails_before_hashing_when_row_bound_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _captured_inputs()
    monkeypatch.setattr(
        planning,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, case_records=3),
    )

    def forbidden_hash(_: ResponseCase) -> str:
        raise AssertionError("case hashing must not start before the row bound passes")

    monkeypatch.setattr(planning, "response_case_sha256", forbidden_hash)
    with pytest.raises(ResourceLimitError) as caught:
        materialize_case_index(captured, captured.resolved_manifest)
    assert caught.value.code == "case_records_limit"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "a" * 1024 + "-en"),
        ("scenario_id", "s" * 1025),
    ],
)
def test_case_index_bounds_generated_ids_before_hashing_without_echoing_content(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    captured = _captured_inputs()
    unsafe_case = captured.case_files[0].cases[0].model_copy(update={field: value})
    unsafe_file = replace(
        captured.case_files[0],
        cases=(unsafe_case, captured.case_files[0].cases[1]),
    )
    unsafe_capture = _replace_capture(
        captured,
        case_files=(unsafe_file, captured.case_files[1]),
    )

    def forbidden_hash(_: ResponseCase) -> str:
        raise AssertionError("case hashing must not start before ID bounds pass")

    monkeypatch.setattr(planning, "response_case_sha256", forbidden_hash)
    with pytest.raises(ResourceLimitError) as caught:
        materialize_case_index(unsafe_capture, unsafe_capture.resolved_manifest)
    assert caught.value.code == "bounded_string_limit"
    assert value[:64] not in str(caught.value)


def test_case_and_arm_lone_surrogates_fail_with_controlled_content_free_errors() -> None:
    captured = _captured_inputs()
    unsafe_case = captured.case_files[0].cases[0].model_copy(update={"prompt": "bad\ud800"})
    unsafe_file = replace(
        captured.case_files[0],
        cases=(unsafe_case, captured.case_files[0].cases[1]),
    )
    unsafe_capture = _replace_capture(
        captured,
        case_files=(unsafe_file, captured.case_files[1]),
    )
    with pytest.raises(PlanningError) as case_error:
        materialize_case_index(unsafe_capture, unsafe_capture.resolved_manifest)
    assert case_error.value.code == "invalid_utf8"
    assert "bad" not in str(case_error.value)

    rows = materialize_case_index(captured, captured.resolved_manifest)
    unsafe_arm = Arm(name="if", instruction="bad\ud800", sha256="0" * 64)
    with pytest.raises(PlanningError) as arm_error:
        materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=rows,
            captured_arms=(*captured.arms[:2], unsafe_arm),
        )
    assert arm_error.value.code == "invalid_utf8"
    assert "bad" not in str(arm_error.value)


def test_plan_materializes_exact_cartesian_order_positions_and_hashes() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)

    rows = materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    assert all(isinstance(row, PlanRowV1) for row in rows)
    assert len(rows) == 4 * 2 * 3
    assert [row.ordinal for row in rows] == list(range(24))
    assert len({row.plan_item_id for row in rows}) == 24
    assert len({row.block_id for row in rows}) == 8
    assert len({row.pairing_unit_id for row in rows}) == 8
    assert {row.block_id for row in rows}.isdisjoint({row.pairing_unit_id for row in rows})
    expected_blocks = [
        ("alpha-en", 0, ["concise", "baseline", "if"]),
        ("alpha-en", 1, ["if", "concise", "baseline"]),
        ("alpha-ru", 0, ["baseline", "if", "concise"]),
        ("alpha-ru", 1, ["if", "baseline", "concise"]),
        ("beta-en", 0, ["baseline", "concise", "if"]),
        ("beta-en", 1, ["if", "baseline", "concise"]),
        ("beta-ru", 0, ["baseline", "if", "concise"]),
        ("beta-ru", 1, ["baseline", "concise", "if"]),
    ]
    assert [
        (rows[start].case_id, rows[start].repetition, [row.arm for row in rows[start : start + 3]])
        for start in range(0, len(rows), 3)
    ] == expected_blocks
    assert [row.arm_position for row in rows] == list(range(3)) * 8
    assert {(row.case_uid, row.repetition, row.arm) for row in rows} == set(
        product((row.case_uid for row in case_index), range(2), captured.resolved_manifest.arms)
    )

    arm_hashes = {arm.name: arm.sha256 for arm in captured.arms}
    request_hash = request_config_sha256(captured.resolved_manifest)
    case_by_uid = {row.case_uid: row for row in case_index}
    for row in rows:
        case = case_by_uid[row.case_uid]
        assert row.scenario_uid == case.scenario_uid
        assert row.case_id == case.case_id
        assert row.locale == case.locale
        assert row.prompt_sha256 == case.prompt_sha256
        assert row.case_definition_sha256 == case.case_definition_sha256
        assert row.instruction_sha256 == arm_hashes[row.arm]
        assert row.request_config_sha256 == request_hash
    assert arm_hashes["baseline"] == EMPTY_SHA256
    assert arm_hashes["concise"] == CONCISE_SHA256
    validate_parent_plan(
        rows,
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )


def test_public_manifest_boundaries_revalidate_constructed_instances_without_echo() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    plan = materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )
    payload = dict(captured.resolved_manifest.__dict__)
    payload["repetitions"] = 0
    forged_manifest = ResolvedManifestV2.model_construct(**payload)
    forged_capture = _replace_capture(captured, manifest=forged_manifest)

    calls = (
        lambda: request_config_sha256(forged_manifest),
        lambda: materialize_case_index(captured, forged_manifest),
        lambda: materialize_case_index(forged_capture, forged_manifest),
        lambda: materialize_case_index(forged_capture, captured.resolved_manifest),
        lambda: validate_case_index(case_index, captured, forged_manifest),
        lambda: materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=forged_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
        lambda: validate_parent_plan(
            plan,
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=forged_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
    )
    for call in calls:
        with pytest.raises(PlanningError) as caught:
            call()
        assert caught.value.code == "invalid_resolved_manifest"
        assert "repetitions" not in str(caught.value)


def test_manifest_identity_boundary_rejects_constructed_missing_required_field() -> None:
    captured = _captured_inputs()
    payload = dict(captured.resolved_manifest.__dict__)
    del payload["provider"]
    forged_manifest = ResolvedManifestV2.model_construct(**payload)

    with pytest.raises(PlanningError) as caught:
        request_config_sha256(forged_manifest)
    assert caught.value.code == "invalid_resolved_manifest"
    assert str(caught.value) == "capsule planning rejected"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", "secret-forged-category"),
        ("locale", "fr"),
    ],
)
def test_plan_revalidates_constructed_case_index_rows_before_cross_row_use(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    payload = dict(case_index[0].__dict__)
    payload[field] = value
    forged_row = CaseIndexRowV1.model_construct(**payload)

    def forbidden_identity(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("invalid rows must be rejected before cross-row identity work")

    monkeypatch.setattr(planning, "scenario_uid", forbidden_identity)
    with pytest.raises(PlanningError) as caught:
        materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=(forged_row, *case_index[1:]),
            captured_arms=captured.arms,
        )
    assert caught.value.code == "case_index_mismatch"
    assert value not in str(caught.value)


def test_plan_rejects_constructed_case_index_row_missing_required_field() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    payload = dict(case_index[0].__dict__)
    del payload["case_id"]
    forged_row = CaseIndexRowV1.model_construct(**payload)

    with pytest.raises(PlanningError) as caught:
        materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=(forged_row, *case_index[1:]),
            captured_arms=captured.arms,
        )
    assert caught.value.code == "case_index_mismatch"
    assert str(caught.value) == "capsule planning rejected"


def test_schedule_tie_breaks_equal_digest_bytes_by_arm_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    monkeypatch.setattr(planning, "stable_digest_bytes", lambda _domain, _payload: b"\0" * 32)

    rows = materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    for start in range(0, len(rows), 3):
        assert [row.arm for row in rows[start : start + 3]] == ["baseline", "concise", "if"]


def test_planning_is_independent_of_global_random_and_legacy_plan_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    expected = materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("capsule planning must not use legacy/random scheduling")

    monkeypatch.setattr(random, "Random", forbidden)
    monkeypatch.setattr(random, "shuffle", forbidden)
    monkeypatch.setattr(legacy_runner, "build_run_plan", forbidden)
    random.seed(999_999)

    assert (
        materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        )
        == expected
    )


def test_parent_plan_rejects_the_old_positional_run_identity_api() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    with pytest.raises(TypeError):
        materialize_parent_plan(  # type: ignore[misc]
            RUN_ID,
            captured.resolved_manifest,
            case_index,
            captured.arms,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[:-1],
        lambda rows: (*rows, rows[-1]),
        lambda rows: (rows[0], rows[0], *rows[2:]),
        lambda rows: (
            rows[0].model_copy(update={"ordinal": 1}),
            *rows[1:],
        ),
        lambda rows: (
            rows[0].model_copy(update={"arm_position": 2}),
            *rows[1:],
        ),
        lambda rows: (
            rows[0].model_copy(update={"instruction_sha256": "0" * 64}),
            *rows[1:],
        ),
        lambda rows: tuple(reversed(rows)),
    ],
)
def test_plan_validation_rejects_missing_extra_duplicate_reordered_or_tampered_rows(
    mutate: object,
) -> None:
    assert callable(mutate)
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    rows = materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )
    candidate = mutate(rows)

    _assert_planning_error(
        "plan_mismatch",
        lambda: validate_parent_plan(
            candidate,
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
    )


def test_plan_validation_rejects_wrong_seed_schedule_version_and_selected_arms() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    rows = materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    changed_seed = captured.resolved_manifest.model_copy(update={"arm_order_seed": -18})
    _assert_planning_error(
        "plan_mismatch",
        lambda: validate_parent_plan(
            rows,
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=changed_seed,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
    )

    wrong_version = ResolvedManifestV2.model_construct(
        **(
            captured.resolved_manifest.__dict__
            | {"schedule_algorithm_version": "laconian-schedule-v2"}
        )
    )
    _assert_planning_error(
        "schedule_version_mismatch",
        lambda: materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=wrong_version,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
    )

    fewer_arms = captured.resolved_manifest.model_copy(update={"arms": ("baseline", "concise")})
    _assert_planning_error(
        "arm_manifest_mismatch",
        lambda: validate_parent_plan(
            rows,
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=fewer_arms,
            case_index=case_index,
            captured_arms=captured.arms,
        ),
    )


@pytest.mark.parametrize(
    ("arms", "code"),
    [
        (
            (
                Arm(name="baseline", instruction="", sha256=EMPTY_SHA256),
                arm_from_captured_bytes("concise", b"Answer concisely."),
                arm_from_captured_bytes("if", b"Answer completely, briefly."),
            ),
            "invalid_baseline_arm",
        ),
        (
            (
                arm_from_captured_bytes("baseline", b""),
                Arm(name="concise", instruction="changed", sha256=sha256_bytes(b"changed")),
                arm_from_captured_bytes("if", b"Answer completely, briefly."),
            ),
            "invalid_arm_instruction",
        ),
        (
            (
                arm_from_captured_bytes("baseline", b""),
                arm_from_captured_bytes("concise", b"Answer concisely."),
                Arm(name="if", instruction="changed", sha256="0" * 64),
            ),
            "arm_hash_mismatch",
        ),
        (
            (
                arm_from_captured_bytes("baseline", b""),
                arm_from_captured_bytes("concise", b"Answer concisely."),
                arm_from_captured_bytes("concise", b"Answer concisely."),
            ),
            "arm_manifest_mismatch",
        ),
    ],
)
def test_plan_revalidates_arm_bytes_hashes_baseline_and_manifest_membership(
    arms: tuple[Arm, ...], code: str
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    _assert_planning_error(
        code,
        lambda: materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=arms,
        ),
    )


@pytest.mark.parametrize(
    ("limit_update", "expected_code"),
    [
        ({"plan_rows": 23}, "plan_rows_limit"),
        ({"output_tokens_plan": 3071}, "output_tokens_plan_limit"),
    ],
)
def test_plan_enforces_row_and_token_exposure_before_schedule_allocation(
    monkeypatch: pytest.MonkeyPatch,
    limit_update: dict[str, int],
    expected_code: str,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    uniterable_case_index = _MustNotIterate(len(case_index))
    monkeypatch.setattr(
        planning,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, **limit_update),
    )

    def forbidden_schedule(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("schedule work must not start before exposure checks")

    monkeypatch.setattr(planning, "schedule_digest_bytes", forbidden_schedule)
    with pytest.raises(ResourceLimitError) as caught:
        materialize_parent_plan(
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=uniterable_case_index,  # type: ignore[arg-type]
            captured_arms=captured.arms,
        )
    assert caught.value.code == expected_code


def test_validation_helpers_reject_oversized_sequences_before_iteration() -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)

    oversized_cases = _MustNotIterate(RESOURCE_LIMITS_V1.case_records + 1)
    with pytest.raises(ResourceLimitError) as case_error:
        validate_case_index(  # type: ignore[arg-type]
            oversized_cases,
            captured,
            captured.resolved_manifest,
        )
    assert case_error.value.code == "case_records_limit"

    oversized_plan = _MustNotIterate(RESOURCE_LIMITS_V1.plan_rows + 1)
    with pytest.raises(ResourceLimitError) as plan_error:
        validate_parent_plan(  # type: ignore[arg-type]
            oversized_plan,
            parent_manifest_sha256=PARENT_MANIFEST_SHA256,
            resolved_manifest=captured.resolved_manifest,
            case_index=case_index,
            captured_arms=captured.arms,
        )
    assert plan_error.value.code == "plan_rows_limit"


def test_plan_accepts_exact_row_and_token_exposure_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _captured_inputs()
    case_index = materialize_case_index(captured, captured.resolved_manifest)
    monkeypatch.setattr(
        planning,
        "RESOURCE_LIMITS_V1",
        replace(RESOURCE_LIMITS_V1, plan_rows=24, output_tokens_plan=3072),
    )

    rows = materialize_parent_plan(
        parent_manifest_sha256=PARENT_MANIFEST_SHA256,
        resolved_manifest=captured.resolved_manifest,
        case_index=case_index,
        captured_arms=captured.arms,
    )

    assert len(rows) == 24
