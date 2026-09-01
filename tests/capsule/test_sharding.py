from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import Any

import pytest
from capsule_helpers import resolved_manifest_v2_payload
from pydantic import ValidationError

import laconian_eval.capsule.sharding as sharding_module
from laconian_eval.arms import Arm, arm_from_captured_bytes
from laconian_eval.capsule.canonical import canonical_json, canonical_jsonl, sha256_bytes
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.planning import (
    case_uid,
    materialize_parent_plan,
    scenario_uid,
)
from laconian_eval.capsule.record_models import CaseIndexRowV1, PlanRowV1
from laconian_eval.capsule.sharding import (
    ShardPlanError,
    ShardPlanV1,
    materialize_shard_projection,
    parse_shard_plan_file_bytes,
    project_shard_plans,
    shard_plan_file_bytes,
    validate_public_generation_partition,
)

_CAMPAIGN_ID = "public-benchmark-2026"
_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
_SHARD_DOMAIN = b"laconian-shard-plan-v1\x00"
_REQUEST_CONFIG_DOMAIN = b"laconian-request-config-v1\x00"


def _independent_shard_digest(payload: dict[str, Any]) -> str:
    preimage = {
        "shard_schema_version": payload["shard_schema_version"],
        "campaign_id": payload["campaign_id"],
        "model_id": payload["model_id"],
        "scenario_uid": payload["scenario_uid"],
        "parent_manifest_sha256": payload["parent_manifest_sha256"],
        "parent_plan_sha256": payload["parent_plan_sha256"],
        "derivation_version": payload["derivation_version"],
        "ordered_plan_item_ids": payload["ordered_plan_item_ids"],
        "row_count": payload["row_count"],
    }
    return hashlib.sha256(_SHARD_DOMAIN + canonical_json(preimage)).hexdigest()


def _independent_request_config_digest(model_id: str) -> str:
    preimage = {
        "provider_kind": "openai",
        "requested_model": model_id,
        "generation": {
            "max_output_tokens": 1024,
            "temperature": None,
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
            "envelope_allowance_tokens": 65_536,
            "standard_tier_max_input_tokens": 272_000,
        },
        "store": False,
        "tools": [],
    }
    return hashlib.sha256(_REQUEST_CONFIG_DOMAIN + canonical_json(preimage)).hexdigest()


def _shard_payload(*, model_id: str = "gpt-5.6-sol") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "shard_schema_version": "1",
        "campaign_id": _CAMPAIGN_ID,
        "model_id": model_id,
        "scenario_uid": sha256_bytes(b"scenario"),
        "parent_manifest_sha256": sha256_bytes(b"manifest"),
        "parent_plan_sha256": sha256_bytes(b"plan"),
        "derivation_version": "laconian-scenario-shards-v1",
        "ordered_plan_item_ids": [
            sha256_bytes(f"plan-item-{ordinal}".encode()) for ordinal in range(40)
        ],
        "row_count": 40,
    }
    payload["shard_plan_sha256"] = _independent_shard_digest(payload)
    return payload


def _reseal(payload: dict[str, Any]) -> dict[str, Any]:
    payload["shard_plan_sha256"] = _independent_shard_digest(payload)
    return payload


def test_shard_plan_round_trips_exact_shape() -> None:
    payload = _shard_payload()
    shard = ShardPlanV1.model_validate(payload)

    assert list(shard.model_dump(mode="json")) == [
        "shard_schema_version",
        "campaign_id",
        "model_id",
        "scenario_uid",
        "parent_manifest_sha256",
        "parent_plan_sha256",
        "derivation_version",
        "ordered_plan_item_ids",
        "row_count",
        "shard_plan_sha256",
    ]
    assert shard.model_dump(mode="json") == payload
    assert shard.shard_plan_sha256 == _independent_shard_digest(payload)
    assert ShardPlanV1.model_validate(shard.model_dump(mode="python")) == shard


def test_sharding_public_signatures_are_exact() -> None:
    assert str(inspect.signature(project_shard_plans)) == (
        "(*, campaign_id: 'str', resolved_manifest: 'ResolvedManifestV2', "
        "parent_manifest_sha256: 'str', parent_plan: 'Sequence[PlanRowV1]', "
        "case_index: 'Sequence[CaseIndexRowV1]', captured_arms: 'Sequence[Arm]') "
        "-> 'tuple[ShardPlanV1, ...]'"
    )
    assert str(inspect.signature(materialize_shard_projection)) == (
        "(shard: 'ShardPlanV1', parent_plan: 'Sequence[PlanRowV1]') -> 'tuple[PlanRowV1, ...]'"
    )
    assert str(inspect.signature(validate_public_generation_partition)) == (
        "(*, campaign_id: 'str', resolved_manifests: 'Sequence[ResolvedManifestV2]', "
        "parent_manifest_sha256s: 'Sequence[str]', "
        "case_indexes: 'Sequence[Sequence[CaseIndexRowV1]]', "
        "captured_arms_by_parent: 'Sequence[Sequence[Arm]]', "
        "parent_plans: 'Sequence[Sequence[PlanRowV1]]', "
        "shard_plans: 'Sequence[ShardPlanV1]') -> 'None'"
    )
    assert str(inspect.signature(shard_plan_file_bytes)) == ("(shard: 'ShardPlanV1') -> 'bytes'")
    assert str(inspect.signature(parse_shard_plan_file_bytes)) == (
        "(data: 'bytes') -> 'ShardPlanV1'"
    )


def _unknown_field(payload: dict[str, Any]) -> None:
    payload["unknown"] = "forbidden"


def _uppercase_digest(payload: dict[str, Any]) -> None:
    payload["scenario_uid"] = str(payload["scenario_uid"]).upper()
    _reseal(payload)


def _short_digest(payload: dict[str, Any]) -> None:
    payload["parent_manifest_sha256"] = "a" * 63
    _reseal(payload)


def _blank_model(payload: dict[str, Any]) -> None:
    payload["model_id"] = ""
    _reseal(payload)


def _missing_model(payload: dict[str, Any]) -> None:
    del payload["model_id"]


def _substitute_model(payload: dict[str, Any]) -> None:
    payload["model_id"] = "gpt-5.6-orbit"
    _reseal(payload)


def _duplicate_plan_item(payload: dict[str, Any]) -> None:
    ids = list(payload["ordered_plan_item_ids"])
    ids[-1] = ids[0]
    payload["ordered_plan_item_ids"] = ids
    _reseal(payload)


def _wrong_row_count(payload: dict[str, Any]) -> None:
    payload["row_count"] = 39
    _reseal(payload)


def _unknown_derivation(payload: dict[str, Any]) -> None:
    payload["derivation_version"] = "laconian-scenario-shards-v2"
    _reseal(payload)


def _forged_self_hash(payload: dict[str, Any]) -> None:
    payload["shard_plan_sha256"] = "0" * 64


def _bool_row_count(payload: dict[str, Any]) -> None:
    payload["row_count"] = True
    _reseal(payload)


@pytest.mark.parametrize(
    "mutation",
    (
        _unknown_field,
        _uppercase_digest,
        _short_digest,
        _blank_model,
        _missing_model,
        _substitute_model,
        _duplicate_plan_item,
        _wrong_row_count,
        _unknown_derivation,
        _forged_self_hash,
        _bool_row_count,
    ),
    ids=lambda mutation: mutation.__name__,
)
def test_shard_plan_rejects_nonexact_shape(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    payload = _shard_payload()
    mutation(payload)
    if mutation not in {_missing_model, _forged_self_hash}:
        assert payload["shard_plan_sha256"] == _independent_shard_digest(payload)
    with pytest.raises(ValidationError):
        ShardPlanV1.model_validate(payload)


def test_shard_plan_accepts_each_and_only_each_public_model() -> None:
    for model_id in _MODELS:
        assert ShardPlanV1.model_validate(_shard_payload(model_id=model_id)).model_id == model_id


def test_shard_plan_file_bytes_are_canonical_json_plus_one_lf() -> None:
    shard = ShardPlanV1.model_validate(_shard_payload())
    encoded = canonical_json(shard.model_dump(mode="json")) + b"\n"

    assert shard_plan_file_bytes(shard) == encoded
    assert parse_shard_plan_file_bytes(encoded) == shard

    raw = shard.model_dump(mode="json")
    alternate_order = json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    alternate_number = encoded.replace(b'"row_count":40', b'"row_count":4e1')
    alternate_escape = encoded.replace(b"public-benchmark-2026", b"public\\u002dbenchmark-2026")
    unknown = canonical_json(raw | {"unknown": "forbidden"}) + b"\n"
    forged = canonical_json(raw | {"shard_plan_sha256": "0" * 64}) + b"\n"
    variants = (
        encoded[:-1],
        encoded + b"\n",
        encoded[:-1] + b"\r\n",
        b" " + encoded,
        encoded[:-1] + b" \n",
        alternate_order,
        alternate_number,
        alternate_escape,
        unknown,
        forged,
    )
    assert len(set(variants)) == len(variants)
    for candidate in variants:
        with pytest.raises(ShardPlanError) as caught:
            parse_shard_plan_file_bytes(candidate)
        assert caught.value.code == "plan_mismatch"


def test_shard_plan_file_rejects_excessive_json_depth_as_plan_mismatch() -> None:
    hostile = b"[" * 2_000 + b"]" * 2_000 + b"\n"

    with pytest.raises(ShardPlanError) as caught:
        parse_shard_plan_file_bytes(hostile)

    assert caught.value.code == "plan_mismatch"


def test_shard_file_helpers_class_bound_revalidate_instances() -> None:
    shard = ShardPlanV1.model_validate(_shard_payload())
    object.__setattr__(shard, "model_dump", lambda **_kwargs: _shard_payload())
    assert parse_shard_plan_file_bytes(shard_plan_file_bytes(shard)) == shard

    object.__setattr__(shard, "shard_plan_sha256", "0" * 64)
    with pytest.raises(ShardPlanError) as caught:
        shard_plan_file_bytes(shard)
    assert caught.value.code == "plan_mismatch"
    assert str(caught.value) == "capsule shard plan rejected"


def _manifest(model_id: str) -> ResolvedManifestV2:
    payload = deepcopy(resolved_manifest_v2_payload())
    payload["run_name"] = "public-benchmark-parent"
    payload["provider"] = {
        "kind": "openai",
        "model": model_id,
        "api_key_env": "OPENAI_API_KEY",
        "replay_file": None,
    }
    payload["arms"] = ["baseline", "concise", "caveman", "if"]
    payload["repetitions"] = 5
    payload["generation"] = {
        "max_output_tokens": 1024,
        "temperature": None,
        "reasoning_effort": "medium",
        "text_verbosity": "medium",
        "reasoning_mode": "omitted",
        "prompt_cache_mode": "explicit",
        "prompt_cache_ttl": "30m",
        "service_tier": "default",
    }
    return ResolvedManifestV2.model_validate(payload)


def _captured_arms() -> tuple[Arm, ...]:
    return (
        arm_from_captured_bytes("baseline", b""),
        arm_from_captured_bytes("concise", b"Answer concisely."),
        arm_from_captured_bytes("caveman", b"Caveman benchmark instruction."),
        arm_from_captured_bytes("if", b"IF benchmark instruction."),
    )


def _case_index(manifest: ResolvedManifestV2, *, salt: str) -> tuple[CaseIndexRowV1, ...]:
    rows: list[CaseIndexRowV1] = []
    for scenario_ordinal in range(12):
        source_ordinal = 0 if scenario_ordinal < 6 else 1
        dataset = manifest.capsule.datasets[source_ordinal]
        scenario_id_value = f"scenario-{scenario_ordinal:02d}"
        scenario_identity = scenario_uid(
            dataset.dataset_id,
            dataset.dataset_version,
            scenario_id_value,
        )
        for locale in ("en", "ru"):
            case_id_value = f"{scenario_id_value}-{locale}"
            definition = sha256_bytes(f"{salt}:definition:{case_id_value}".encode())
            rows.append(
                CaseIndexRowV1(
                    dataset_id=dataset.dataset_id,
                    dataset_version=dataset.dataset_version,
                    dataset_role=dataset.role,
                    source_ordinal=source_ordinal,
                    record_ordinal=(scenario_ordinal % 6) * 2 + (locale == "ru"),
                    case_id=case_id_value,
                    case_uid=case_uid(
                        scenario_identity,
                        case_id_value,
                        locale,
                        definition,
                    ),
                    scenario_id=scenario_id_value,
                    scenario_uid=scenario_identity,
                    locale=locale,
                    category="direct",
                    case_definition_sha256=definition,
                    prompt_sha256=sha256_bytes(f"{salt}:prompt:{case_id_value}".encode()),
                    prompt_utf8_bytes=len(f"{salt}:prompt:{case_id_value}".encode()),
                )
            )
    return tuple(rows)


def _parent_plan_bytes(rows: Sequence[PlanRowV1]) -> bytes:
    return canonical_jsonl(row.model_dump(mode="json") for row in rows)


def _bundle(
    model_id: str,
) -> tuple[
    ResolvedManifestV2,
    str,
    tuple[CaseIndexRowV1, ...],
    tuple[Arm, ...],
    tuple[PlanRowV1, ...],
    tuple[ShardPlanV1, ...],
]:
    manifest = _manifest(model_id)
    manifest_sha256 = sha256_bytes(canonical_json(manifest.model_dump(mode="json")))
    case_index = _case_index(manifest, salt=model_id)
    arms = _captured_arms()
    parent = materialize_parent_plan(
        parent_manifest_sha256=manifest_sha256,
        resolved_manifest=manifest,
        case_index=case_index,
        captured_arms=arms,
    )
    shards = project_shard_plans(
        campaign_id=_CAMPAIGN_ID,
        resolved_manifest=manifest,
        parent_manifest_sha256=manifest_sha256,
        parent_plan=parent,
        case_index=case_index,
        captured_arms=arms,
    )
    return manifest, manifest_sha256, case_index, arms, parent, shards


def test_shard_projection_preserves_every_parent_field_except_local_ordinal() -> None:
    _, _, _, _, parent, shards = _bundle(_MODELS[0])
    expected_scenarios = tuple(dict.fromkeys(row.scenario_uid for row in parent))
    expected_parent_plan_sha256 = sha256_bytes(_parent_plan_bytes(parent))

    assert tuple(shard.scenario_uid for shard in shards) == expected_scenarios
    assert {shard.parent_plan_sha256 for shard in shards} == {expected_parent_plan_sha256}
    assert {shard.row_count for shard in shards} == {40}
    assert len(shards) == 12
    for shard in shards:
        projection = materialize_shard_projection(shard, parent)
        assert tuple(row.ordinal for row in projection) == tuple(range(40))
        assert tuple(row.plan_item_id for row in projection) == shard.ordered_plan_item_ids
        parent_by_id = {row.plan_item_id: row for row in parent}
        for projected in projection:
            projected_payload = projected.model_dump(mode="json")
            parent_payload = parent_by_id[projected.plan_item_id].model_dump(mode="json")
            assert projected_payload.pop("ordinal") in range(40)
            parent_payload.pop("ordinal")
            assert projected_payload == parent_payload


def _assert_shard_error(call: Callable[[], object]) -> None:
    with pytest.raises(ShardPlanError) as caught:
        call()
    assert caught.value.code == "plan_mismatch"


def test_shard_projection_rejects_forged_membership_order_and_parent_commitment() -> None:
    _, _, _, _, parent, shards = _bundle(_MODELS[0])
    shard = shards[0]

    reversed_payload = shard.model_dump(mode="json")
    reversed_payload["ordered_plan_item_ids"] = list(
        reversed(reversed_payload["ordered_plan_item_ids"])
    )
    reversed_shard = ShardPlanV1.model_validate(_reseal(reversed_payload))
    _assert_shard_error(lambda: materialize_shard_projection(reversed_shard, parent))

    missing_payload = shard.model_dump(mode="json")
    missing_payload["ordered_plan_item_ids"] = missing_payload["ordered_plan_item_ids"][:-1]
    missing_payload["row_count"] -= 1
    missing_shard = ShardPlanV1.model_validate(_reseal(missing_payload))
    _assert_shard_error(lambda: materialize_shard_projection(missing_shard, parent))

    wrong_parent_payload = shard.model_dump(mode="json")
    wrong_parent_payload["parent_plan_sha256"] = "0" * 64
    wrong_parent = ShardPlanV1.model_validate(_reseal(wrong_parent_payload))
    _assert_shard_error(lambda: materialize_shard_projection(wrong_parent, parent))

    forged_parent = list(parent)
    object.__setattr__(forged_parent[0], "plan_item_id", "INVALID")
    _assert_shard_error(lambda: materialize_shard_projection(shard, forged_parent))


def test_three_model_public_partition_is_exactly_36_by_40(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundles = tuple(_bundle(model_id) for model_id in _MODELS)
    manifests = tuple(bundle[0] for bundle in bundles)
    manifest_sha256s = tuple(bundle[1] for bundle in bundles)
    case_indexes = tuple(bundle[2] for bundle in bundles)
    captured_arms = tuple(bundle[3] for bundle in bundles)
    parents = tuple(bundle[4] for bundle in bundles)
    shards = tuple(shard for bundle in bundles for shard in bundle[5])

    assert [len(parent) for parent in parents] == [480, 480, 480]
    assert len(shards) == 36
    assert {shard.row_count for shard in shards} == {40}
    assert sum(shard.row_count for shard in shards) == 1440
    assert {shard.model_id for shard in shards} == set(_MODELS)
    assert all(row.input_token_bound <= 272_000 for parent in parents for row in parent)
    assert len({row.plan_item_id for parent in parents for row in parent}) == 1440
    for manifest, parent in zip(manifests, parents, strict=True):
        expected_request_config = _independent_request_config_digest(manifest.provider.model)
        assert {row.request_config_sha256 for row in parent} == {expected_request_config}

    for shard in shards:
        parent = parents[manifest_sha256s.index(shard.parent_manifest_sha256)]
        projection = materialize_shard_projection(shard, parent)
        assert {row.locale for row in projection} == {"en", "ru"}
        assert {row.arm for row in projection} == {"baseline", "concise", "caveman", "if"}
        assert {row.repetition for row in projection} == set(range(5))
        assert {row.scenario_uid for row in projection} == {shard.scenario_uid}
        assert len({(row.case_uid, row.repetition, row.arm) for row in projection}) == 40

    real_validate = sharding_module.validate_parent_plan
    calls: list[tuple[object, ...]] = []

    def spy_validate(
        rows: Sequence[PlanRowV1],
        *,
        parent_manifest_sha256: str,
        resolved_manifest: ResolvedManifestV2,
        case_index: Sequence[CaseIndexRowV1],
        captured_arms: Sequence[Arm],
    ) -> None:
        calls.append((rows, parent_manifest_sha256, resolved_manifest, case_index, captured_arms))
        real_validate(
            rows,
            parent_manifest_sha256=parent_manifest_sha256,
            resolved_manifest=resolved_manifest,
            case_index=case_index,
            captured_arms=captured_arms,
        )

    monkeypatch.setattr(sharding_module, "validate_parent_plan", spy_validate)
    validate_public_generation_partition(
        campaign_id=_CAMPAIGN_ID,
        resolved_manifests=manifests,
        parent_manifest_sha256s=manifest_sha256s,
        case_indexes=case_indexes,
        captured_arms_by_parent=captured_arms,
        parent_plans=parents,
        shard_plans=shards,
    )
    assert calls == [
        (
            parents[index],
            manifest_sha256s[index],
            manifests[index],
            case_indexes[index],
            captured_arms[index],
        )
        for index in range(3)
    ]


def test_public_partition_rejects_each_nonexact_policy_dimension_before_parent_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundles = tuple(_bundle(model_id) for model_id in _MODELS)
    valid: dict[str, Any] = {
        "campaign_id": _CAMPAIGN_ID,
        "resolved_manifests": tuple(bundle[0] for bundle in bundles),
        "parent_manifest_sha256s": tuple(bundle[1] for bundle in bundles),
        "case_indexes": tuple(bundle[2] for bundle in bundles),
        "captured_arms_by_parent": tuple(bundle[3] for bundle in bundles),
        "parent_plans": tuple(bundle[4] for bundle in bundles),
        "shard_plans": tuple(shard for bundle in bundles for shard in bundle[5]),
    }

    def unexpected_parent_validation(*_args: object, **_kwargs: object) -> None:
        pytest.fail("nonexact public policy reached parent validation")

    monkeypatch.setattr(sharding_module, "validate_parent_plan", unexpected_parent_validation)
    mutations = (
        ("manifest", "arms", ("concise", "baseline", "caveman", "if")),
        ("manifest", "repetitions", 4),
        ("generation", "max_output_tokens", 2048),
        ("generation", "temperature", 0.0),
        ("generation", "reasoning_effort", "low"),
        ("generation", "text_verbosity", "low"),
        ("generation", "reasoning_mode", "included"),
        ("generation", "prompt_cache_mode", "implicit"),
        ("generation", "prompt_cache_ttl", "1h"),
        ("generation", "service_tier", "flex"),
    )
    for owner, field, value in mutations:
        manifest = ResolvedManifestV2.model_validate(
            valid["resolved_manifests"][0].model_dump(mode="python", round_trip=True)
        )
        target = manifest if owner == "manifest" else manifest.generation
        object.__setattr__(target, field, value)
        changed = valid | {
            "resolved_manifests": (manifest, *valid["resolved_manifests"][1:]),
        }
        _assert_shard_error(lambda changed=changed: validate_public_generation_partition(**changed))


def test_public_partition_rejects_duplicate_ids_within_and_across_parents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundles = tuple(_bundle(model_id) for model_id in _MODELS)
    parents = tuple(bundle[4] for bundle in bundles)
    valid: dict[str, Any] = {
        "campaign_id": _CAMPAIGN_ID,
        "resolved_manifests": tuple(bundle[0] for bundle in bundles),
        "parent_manifest_sha256s": tuple(bundle[1] for bundle in bundles),
        "case_indexes": tuple(bundle[2] for bundle in bundles),
        "captured_arms_by_parent": tuple(bundle[3] for bundle in bundles),
        "parent_plans": parents,
        "shard_plans": tuple(shard for bundle in bundles for shard in bundle[5]),
    }

    monkeypatch.setattr(sharding_module, "validate_parent_plan", lambda *_args, **_kwargs: None)

    def unexpected_projection(**_kwargs: object) -> tuple[ShardPlanV1, ...]:
        pytest.fail("duplicate plan-item ID reached shard projection")

    monkeypatch.setattr(sharding_module, "_project_validated_parent", unexpected_projection)

    within_first_parent = (
        parents[0][0],
        parents[0][1].model_copy(update={"plan_item_id": parents[0][0].plan_item_id}),
        *parents[0][2:],
    )
    across_second_parent = (
        parents[1][0].model_copy(update={"plan_item_id": parents[0][0].plan_item_id}),
        *parents[1][1:],
    )
    for changed_parents in (
        (within_first_parent, parents[1], parents[2]),
        (parents[0], across_second_parent, parents[2]),
    ):
        changed = valid | {"parent_plans": changed_parents}
        _assert_shard_error(lambda changed=changed: validate_public_generation_partition(**changed))


def test_public_partition_rejects_alignment_campaign_and_order_mutations() -> None:
    bundles = tuple(_bundle(model_id) for model_id in _MODELS)
    valid: dict[str, Any] = {
        "campaign_id": _CAMPAIGN_ID,
        "resolved_manifests": tuple(bundle[0] for bundle in bundles),
        "parent_manifest_sha256s": tuple(bundle[1] for bundle in bundles),
        "case_indexes": tuple(bundle[2] for bundle in bundles),
        "captured_arms_by_parent": tuple(bundle[3] for bundle in bundles),
        "parent_plans": tuple(bundle[4] for bundle in bundles),
        "shard_plans": tuple(shard for bundle in bundles for shard in bundle[5]),
    }

    for field in (
        "resolved_manifests",
        "parent_manifest_sha256s",
        "case_indexes",
        "captured_arms_by_parent",
        "parent_plans",
    ):
        shorter = valid | {field: valid[field][:-1]}
        _assert_shard_error(lambda shorter=shorter: validate_public_generation_partition(**shorter))
        longer = valid | {field: valid[field] + (valid[field][0],)}
        _assert_shard_error(lambda longer=longer: validate_public_generation_partition(**longer))

    for campaign_id in ("", "wrong-campaign"):
        changed = valid | {"campaign_id": campaign_id}
        _assert_shard_error(lambda changed=changed: validate_public_generation_partition(**changed))

    reordered_models = valid | {
        "resolved_manifests": (
            valid["resolved_manifests"][1],
            valid["resolved_manifests"][0],
            valid["resolved_manifests"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**reordered_models))

    duplicate_hash = valid | {
        "parent_manifest_sha256s": (
            valid["parent_manifest_sha256s"][0],
            valid["parent_manifest_sha256s"][0],
            valid["parent_manifest_sha256s"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**duplicate_hash))

    swapped_hashes = valid | {
        "parent_manifest_sha256s": (
            valid["parent_manifest_sha256s"][1],
            valid["parent_manifest_sha256s"][0],
            valid["parent_manifest_sha256s"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**swapped_hashes))

    swapped_indexes = valid | {
        "case_indexes": (
            valid["case_indexes"][1],
            valid["case_indexes"][0],
            valid["case_indexes"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**swapped_indexes))

    reversed_arms = valid | {
        "captured_arms_by_parent": (
            tuple(reversed(valid["captured_arms_by_parent"][0])),
            valid["captured_arms_by_parent"][1],
            valid["captured_arms_by_parent"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**reversed_arms))

    swapped_parents = valid | {
        "parent_plans": (
            valid["parent_plans"][1],
            valid["parent_plans"][0],
            valid["parent_plans"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**swapped_parents))

    forged_first_parent = (
        valid["parent_plans"][0][0].model_copy(update={"plan_item_id": "0" * 64}),
        *valid["parent_plans"][0][1:],
    )
    forged_parent = valid | {
        "parent_plans": (
            forged_first_parent,
            valid["parent_plans"][1],
            valid["parent_plans"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**forged_parent))

    reordered_shards = valid | {
        "shard_plans": (
            valid["shard_plans"][1],
            valid["shard_plans"][0],
            *valid["shard_plans"][2:],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**reordered_shards))

    swapped_shard_segments = valid | {
        "shard_plans": (
            *valid["shard_plans"][12:24],
            *valid["shard_plans"][0:12],
            *valid["shard_plans"][24:36],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**swapped_shard_segments))

    mismatched_shard_payload = valid["shard_plans"][0].model_dump(mode="json")
    mismatched_shard_payload["campaign_id"] = "wrong-campaign"
    mismatched_shard = ShardPlanV1.model_validate(_reseal(mismatched_shard_payload))
    mismatched_shards = valid | {"shard_plans": (mismatched_shard, *valid["shard_plans"][1:])}
    _assert_shard_error(lambda: validate_public_generation_partition(**mismatched_shards))

    wrong_provider_payload = valid["resolved_manifests"][0].model_dump(mode="python")
    wrong_provider_payload["provider"] = {
        "kind": "fake",
        "model": _MODELS[0],
        "api_key_env": None,
        "replay_file": None,
    }
    wrong_provider = ResolvedManifestV2.model_validate(wrong_provider_payload)
    wrong_provider_inputs = valid | {
        "resolved_manifests": (
            wrong_provider,
            valid["resolved_manifests"][1],
            valid["resolved_manifests"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**wrong_provider_inputs))


def test_public_partition_rejects_missing_extra_or_substitute_models() -> None:
    bundles = tuple(_bundle(model_id) for model_id in _MODELS)
    valid: dict[str, Any] = {
        "campaign_id": _CAMPAIGN_ID,
        "resolved_manifests": tuple(bundle[0] for bundle in bundles),
        "parent_manifest_sha256s": tuple(bundle[1] for bundle in bundles),
        "case_indexes": tuple(bundle[2] for bundle in bundles),
        "captured_arms_by_parent": tuple(bundle[3] for bundle in bundles),
        "parent_plans": tuple(bundle[4] for bundle in bundles),
        "shard_plans": tuple(shard for bundle in bundles for shard in bundle[5]),
    }
    for omitted in range(3):
        keep = tuple(index for index in range(3) if index != omitted)
        changed = valid | {
            name: tuple(valid[name][index] for index in keep)
            for name in (
                "resolved_manifests",
                "parent_manifest_sha256s",
                "case_indexes",
                "captured_arms_by_parent",
                "parent_plans",
            )
        }
        _assert_shard_error(lambda changed=changed: validate_public_generation_partition(**changed))

    fourth = _bundle(_MODELS[0])
    extra = valid | {
        "resolved_manifests": valid["resolved_manifests"] + (fourth[0],),
        "parent_manifest_sha256s": valid["parent_manifest_sha256s"] + (fourth[1],),
        "case_indexes": valid["case_indexes"] + (fourth[2],),
        "captured_arms_by_parent": valid["captured_arms_by_parent"] + (fourth[3],),
        "parent_plans": valid["parent_plans"] + (fourth[4],),
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**extra))

    substitute_manifest = _manifest("gpt-5.6-orbit")
    substitute = valid | {
        "resolved_manifests": (
            valid["resolved_manifests"][0],
            substitute_manifest,
            valid["resolved_manifests"][2],
        )
    }
    _assert_shard_error(lambda: validate_public_generation_partition(**substitute))
