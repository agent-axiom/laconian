"""Immutable public-benchmark scenario shard plans and projections."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal, NoReturn, Self, TypeVar

from pydantic import Field, TypeAdapter, ValidationError, field_validator, model_validator

from laconian_eval.arms import Arm
from laconian_eval.capsule.canonical import (
    canonical_json,
    canonical_jsonl,
    sha256_bytes,
    stable_digest,
)
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.manifest_models import ResolvedManifestV2
from laconian_eval.capsule.planning import PlanningError, validate_parent_plan
from laconian_eval.capsule.record_models import CaseIndexRowV1, PlanRowV1
from laconian_eval.capsule.schema import (
    CapsuleModel,
    PublicBenchmarkModelId,
    RunName,
    Sha256,
    StrictPositiveInt,
)

_PUBLIC_MODEL_ORDER: tuple[PublicBenchmarkModelId, ...] = (
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
)
_SHARD_DERIVATION_VERSION: Literal["laconian-scenario-shards-v1"] = "laconian-scenario-shards-v1"
_SHARD_DIGEST_DOMAIN = "laconian-shard-plan-v1"
_RUN_NAME_ADAPTER = TypeAdapter(RunName)
_SHA256_ADAPTER = TypeAdapter(Sha256)
_T = TypeVar("_T")


class ShardPlanError(ValueError):
    """Content-free shard-planning failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("capsule shard plan rejected")


def _shard_digest_preimage(
    *,
    shard_schema_version: str,
    campaign_id: str,
    model_id: str,
    scenario_uid: str,
    parent_manifest_sha256: str,
    parent_plan_sha256: str,
    derivation_version: str,
    ordered_plan_item_ids: Sequence[str],
    row_count: int,
) -> dict[str, object]:
    return {
        "shard_schema_version": shard_schema_version,
        "campaign_id": campaign_id,
        "model_id": model_id,
        "scenario_uid": scenario_uid,
        "parent_manifest_sha256": parent_manifest_sha256,
        "parent_plan_sha256": parent_plan_sha256,
        "derivation_version": derivation_version,
        "ordered_plan_item_ids": tuple(ordered_plan_item_ids),
        "row_count": row_count,
    }


class ShardPlanV1(CapsuleModel):
    shard_schema_version: Literal["1"]
    campaign_id: RunName
    model_id: PublicBenchmarkModelId
    scenario_uid: Sha256
    parent_manifest_sha256: Sha256
    parent_plan_sha256: Sha256
    derivation_version: Literal["laconian-scenario-shards-v1"]
    ordered_plan_item_ids: tuple[Sha256, ...] = Field(min_length=1)
    row_count: StrictPositiveInt
    shard_plan_sha256: Sha256

    @field_validator("ordered_plan_item_ids")
    @classmethod
    def require_unique_plan_item_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("ordered plan-item IDs must be unique")
        return value

    @model_validator(mode="after")
    def require_exact_count_and_self_hash(self) -> Self:
        if self.row_count != len(self.ordered_plan_item_ids):
            raise ValueError("row count must equal ordered plan-item count")
        expected = stable_digest(
            _SHARD_DIGEST_DOMAIN,
            _shard_digest_preimage(
                shard_schema_version=self.shard_schema_version,
                campaign_id=self.campaign_id,
                model_id=self.model_id,
                scenario_uid=self.scenario_uid,
                parent_manifest_sha256=self.parent_manifest_sha256,
                parent_plan_sha256=self.parent_plan_sha256,
                derivation_version=self.derivation_version,
                ordered_plan_item_ids=self.ordered_plan_item_ids,
                row_count=self.row_count,
            ),
        )
        if self.shard_plan_sha256 != expected:
            raise ValueError("shard-plan self-hash mismatch")
        return self


def _fail() -> NoReturn:
    raise ShardPlanError("plan_mismatch")


def _exact_tuple(
    values: Sequence[_T],
    *,
    expected_count: int | None = None,
    maximum_count: int | None = None,
) -> tuple[_T, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        _fail()
    try:
        reported_count = len(values)
        if expected_count is not None and reported_count != expected_count:
            _fail()
        if maximum_count is not None and reported_count > maximum_count:
            _fail()
        iterator = iter(values)
    except ShardPlanError:
        raise
    except Exception:
        _fail()
    materialized: list[_T] = []
    for _ in range(reported_count):
        try:
            materialized.append(next(iterator))
        except Exception:
            _fail()
    try:
        next(iterator)
    except StopIteration:
        pass
    except Exception:
        _fail()
    else:
        _fail()
    if len(materialized) != reported_count:
        _fail()
    return tuple(materialized)


def _require_campaign_id(value: object) -> str:
    try:
        return _RUN_NAME_ADAPTER.validate_python(value)
    except (TypeError, ValueError):
        _fail()


def _require_sha256(value: object) -> str:
    try:
        return _SHA256_ADAPTER.validate_python(value)
    except (TypeError, ValueError):
        _fail()


def _revalidate_manifest(value: object) -> ResolvedManifestV2:
    if type(value) is not ResolvedManifestV2:
        _fail()
    checked = value
    try:
        payload = ResolvedManifestV2.model_dump(
            checked,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return ResolvedManifestV2.model_validate(payload)
    except (AttributeError, TypeError, ValueError):
        _fail()


def _revalidate_case_row(value: object) -> CaseIndexRowV1:
    if type(value) is not CaseIndexRowV1:
        _fail()
    checked = value
    try:
        payload = CaseIndexRowV1.model_dump(
            checked,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return CaseIndexRowV1.model_validate(payload)
    except (AttributeError, TypeError, ValueError):
        _fail()


def _revalidate_plan_row(value: object) -> PlanRowV1:
    if type(value) is not PlanRowV1:
        _fail()
    checked = value
    try:
        payload = PlanRowV1.model_dump(
            checked,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return PlanRowV1.model_validate(payload)
    except (AttributeError, TypeError, ValueError):
        _fail()


def _revalidate_arm(value: object) -> Arm:
    if type(value) is not Arm:
        _fail()
    checked = value
    try:
        return Arm(
            name=checked.name,
            instruction=checked.instruction,
            sha256=checked.sha256,
        )
    except (AttributeError, TypeError, ValueError):
        _fail()


def _revalidate_shard(value: object) -> ShardPlanV1:
    if type(value) is not ShardPlanV1:
        _fail()
    checked = value
    try:
        payload = ShardPlanV1.model_dump(
            checked,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return ShardPlanV1.model_validate(payload)
    except (AttributeError, TypeError, ValueError):
        _fail()


def _plan_jsonl(rows: Sequence[PlanRowV1]) -> bytes:
    try:
        return canonical_jsonl(
            PlanRowV1.model_dump(
                row,
                mode="json",
                round_trip=True,
                warnings=False,
            )
            for row in rows
        )
    except (AttributeError, TypeError, ValueError, UnicodeError):
        _fail()


def _make_shard(
    *,
    campaign_id: str,
    model_id: PublicBenchmarkModelId,
    scenario_uid: str,
    parent_manifest_sha256: str,
    parent_plan_sha256: str,
    ordered_plan_item_ids: tuple[str, ...],
) -> ShardPlanV1:
    preimage = _shard_digest_preimage(
        shard_schema_version="1",
        campaign_id=campaign_id,
        model_id=model_id,
        scenario_uid=scenario_uid,
        parent_manifest_sha256=parent_manifest_sha256,
        parent_plan_sha256=parent_plan_sha256,
        derivation_version=_SHARD_DERIVATION_VERSION,
        ordered_plan_item_ids=ordered_plan_item_ids,
        row_count=len(ordered_plan_item_ids),
    )
    try:
        return ShardPlanV1(
            shard_schema_version="1",
            campaign_id=campaign_id,
            model_id=model_id,
            scenario_uid=scenario_uid,
            parent_manifest_sha256=parent_manifest_sha256,
            parent_plan_sha256=parent_plan_sha256,
            derivation_version=_SHARD_DERIVATION_VERSION,
            ordered_plan_item_ids=ordered_plan_item_ids,
            row_count=len(ordered_plan_item_ids),
            shard_plan_sha256=stable_digest(_SHARD_DIGEST_DOMAIN, preimage),
        )
    except (TypeError, ValueError):
        _fail()


def shard_plan_file_bytes(shard: ShardPlanV1) -> bytes:
    """Encode one class-bound shard plan as canonical JSON plus exactly one LF."""

    checked = _revalidate_shard(shard)
    try:
        payload = ShardPlanV1.model_dump(
            checked,
            mode="json",
            round_trip=True,
            warnings=False,
        )
        return canonical_json(payload) + b"\n"
    except (AttributeError, TypeError, ValueError, UnicodeError):
        _fail()


def parse_shard_plan_file_bytes(data: bytes) -> ShardPlanV1:
    """Strictly decode and byte-for-byte revalidate one shard-plan file."""

    if type(data) is not bytes or not data.endswith(b"\n"):
        _fail()
    body = data[:-1]
    try:
        decoded = json.loads(body.decode("utf-8", errors="strict"))
        if type(decoded) is not dict:
            _fail()
        shard = ShardPlanV1.model_validate(decoded)
        checked = _revalidate_shard(shard)
        if shard_plan_file_bytes(checked) != data:
            _fail()
        return checked
    except ShardPlanError:
        raise
    except (
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
    ):
        _fail()


def _project_validated_parent(
    *,
    campaign_id: str,
    model_id: PublicBenchmarkModelId,
    parent_manifest_sha256: str,
    parent_plan: tuple[PlanRowV1, ...],
) -> tuple[ShardPlanV1, ...]:
    parent_plan_sha256 = sha256_bytes(_plan_jsonl(parent_plan))
    groups: dict[str, list[str]] = {}
    plan_item_ids: set[str] = set()
    for row in parent_plan:
        if row.plan_item_id in plan_item_ids:
            _fail()
        plan_item_ids.add(row.plan_item_id)
        groups.setdefault(row.scenario_uid, []).append(row.plan_item_id)
    if not groups:
        _fail()
    return tuple(
        _make_shard(
            campaign_id=campaign_id,
            model_id=model_id,
            scenario_uid=scenario_identity,
            parent_manifest_sha256=parent_manifest_sha256,
            parent_plan_sha256=parent_plan_sha256,
            ordered_plan_item_ids=tuple(ordered_ids),
        )
        for scenario_identity, ordered_ids in groups.items()
    )


def project_shard_plans(
    *,
    campaign_id: str,
    resolved_manifest: ResolvedManifestV2,
    parent_manifest_sha256: str,
    parent_plan: Sequence[PlanRowV1],
    case_index: Sequence[CaseIndexRowV1],
    captured_arms: Sequence[Arm],
) -> tuple[ShardPlanV1, ...]:
    """Return one first-appearance-ordered shard per scenario UID."""

    checked_campaign_id = _require_campaign_id(campaign_id)
    checked_manifest = _revalidate_manifest(resolved_manifest)
    checked_parent_sha256 = _require_sha256(parent_manifest_sha256)
    checked_cases = tuple(
        _revalidate_case_row(row)
        for row in _exact_tuple(
            case_index,
            maximum_count=RESOURCE_LIMITS_V1.case_records,
        )
    )
    checked_arms = tuple(
        _revalidate_arm(arm) for arm in _exact_tuple(captured_arms, maximum_count=4)
    )
    checked_parent = tuple(
        _revalidate_plan_row(row)
        for row in _exact_tuple(
            parent_plan,
            maximum_count=RESOURCE_LIMITS_V1.plan_rows,
        )
    )
    if (
        checked_manifest.provider.kind != "openai"
        or checked_manifest.provider.model not in _PUBLIC_MODEL_ORDER
    ):
        _fail()
    try:
        validate_parent_plan(
            checked_parent,
            parent_manifest_sha256=checked_parent_sha256,
            resolved_manifest=checked_manifest,
            case_index=checked_cases,
            captured_arms=checked_arms,
        )
    except PlanningError:
        _fail()
    return _project_validated_parent(
        campaign_id=checked_campaign_id,
        model_id=checked_manifest.provider.model,
        parent_manifest_sha256=checked_parent_sha256,
        parent_plan=checked_parent,
    )


def materialize_shard_projection(
    shard: ShardPlanV1,
    parent_plan: Sequence[PlanRowV1],
) -> tuple[PlanRowV1, ...]:
    """Return exact selected rows with local ordinals zero through row_count minus one."""

    checked_shard = _revalidate_shard(shard)
    checked_parent = tuple(
        _revalidate_plan_row(row)
        for row in _exact_tuple(
            parent_plan,
            maximum_count=RESOURCE_LIMITS_V1.plan_rows,
        )
    )
    if tuple(row.ordinal for row in checked_parent) != tuple(range(len(checked_parent))):
        _fail()
    if sha256_bytes(_plan_jsonl(checked_parent)) != checked_shard.parent_plan_sha256:
        _fail()
    parent_by_id: dict[str, PlanRowV1] = {}
    for row in checked_parent:
        if row.plan_item_id in parent_by_id:
            _fail()
        parent_by_id[row.plan_item_id] = row
    try:
        selected = tuple(parent_by_id[item_id] for item_id in checked_shard.ordered_plan_item_ids)
    except KeyError:
        _fail()
    expected_ids = tuple(
        row.plan_item_id for row in checked_parent if row.scenario_uid == checked_shard.scenario_uid
    )
    if (
        expected_ids != checked_shard.ordered_plan_item_ids
        or len(selected) != checked_shard.row_count
        or any(row.scenario_uid != checked_shard.scenario_uid for row in selected)
    ):
        _fail()

    projected: list[PlanRowV1] = []
    for local_ordinal, parent_row in enumerate(selected):
        parent_payload = PlanRowV1.model_dump(
            parent_row,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        candidate_payload = dict(parent_payload)
        candidate_payload["ordinal"] = local_ordinal
        try:
            candidate = PlanRowV1.model_validate(candidate_payload)
        except (TypeError, ValueError):
            _fail()
        parent_without_ordinal = dict(parent_payload)
        candidate_without_ordinal = PlanRowV1.model_dump(
            candidate,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        parent_without_ordinal.pop("ordinal")
        candidate_without_ordinal.pop("ordinal")
        if candidate_without_ordinal != parent_without_ordinal:
            _fail()
        projected.append(candidate)
    return tuple(projected)


def _require_public_manifest_contract(
    manifest: ResolvedManifestV2,
    expected_model: PublicBenchmarkModelId,
    case_index: tuple[CaseIndexRowV1, ...],
    captured_arms: tuple[Arm, ...],
    parent_plan: tuple[PlanRowV1, ...],
) -> None:
    generation = manifest.generation
    if (
        manifest.provider.kind != "openai"
        or manifest.provider.model != expected_model
        or manifest.arms != ("baseline", "concise", "caveman", "if")
        or manifest.repetitions != 5
        or generation.max_output_tokens != 1024
        or generation.temperature is not None
        or generation.reasoning_effort != "medium"
        or generation.text_verbosity != "medium"
        or generation.reasoning_mode != "omitted"
        or generation.prompt_cache_mode != "explicit"
        or generation.prompt_cache_ttl != "30m"
        or generation.service_tier != "default"
        or len(case_index) != 24
        or len(captured_arms) != 4
        or tuple(arm.name for arm in captured_arms) != manifest.arms
        or len(parent_plan) != 480
        or len({row.scenario_uid for row in parent_plan}) != 12
    ):
        _fail()


def validate_public_generation_partition(
    *,
    campaign_id: str,
    resolved_manifests: Sequence[ResolvedManifestV2],
    parent_manifest_sha256s: Sequence[str],
    case_indexes: Sequence[Sequence[CaseIndexRowV1]],
    captured_arms_by_parent: Sequence[Sequence[Arm]],
    parent_plans: Sequence[Sequence[PlanRowV1]],
    shard_plans: Sequence[ShardPlanV1],
) -> None:
    """Require the aligned Sol/Terra/Luna parents and exact ordered 36-by-40 union."""

    checked_campaign_id = _require_campaign_id(campaign_id)
    manifests = tuple(
        _revalidate_manifest(value) for value in _exact_tuple(resolved_manifests, expected_count=3)
    )
    parent_hashes = tuple(
        _require_sha256(value) for value in _exact_tuple(parent_manifest_sha256s, expected_count=3)
    )
    raw_case_indexes = _exact_tuple(case_indexes, expected_count=3)
    raw_captured_arms = _exact_tuple(captured_arms_by_parent, expected_count=3)
    raw_parent_plans = _exact_tuple(parent_plans, expected_count=3)
    raw_shards = _exact_tuple(shard_plans, expected_count=36)

    if (
        tuple(manifest.provider.model for manifest in manifests) != _PUBLIC_MODEL_ORDER
        or any(manifest.provider.kind != "openai" for manifest in manifests)
        or len(set(parent_hashes)) != 3
    ):
        _fail()

    indexes = tuple(
        tuple(_revalidate_case_row(row) for row in _exact_tuple(rows, expected_count=24))
        for rows in raw_case_indexes
    )
    arms_by_parent = tuple(
        tuple(_revalidate_arm(arm) for arm in _exact_tuple(arms, expected_count=4))
        for arms in raw_captured_arms
    )
    parents = tuple(
        tuple(_revalidate_plan_row(row) for row in _exact_tuple(rows, expected_count=480))
        for rows in raw_parent_plans
    )
    shards = tuple(_revalidate_shard(shard) for shard in raw_shards)

    for index, expected_model in enumerate(_PUBLIC_MODEL_ORDER):
        _require_public_manifest_contract(
            manifests[index],
            expected_model,
            indexes[index],
            arms_by_parent[index],
            parents[index],
        )

    for index in range(3):
        try:
            validate_parent_plan(
                parents[index],
                parent_manifest_sha256=parent_hashes[index],
                resolved_manifest=manifests[index],
                case_index=indexes[index],
                captured_arms=arms_by_parent[index],
            )
        except PlanningError:
            _fail()

    all_parent_ids = tuple(row.plan_item_id for parent in parents for row in parent)
    if len(all_parent_ids) != 1440 or len(set(all_parent_ids)) != 1440:
        _fail()

    expected_shards = tuple(
        shard
        for index, model_id in enumerate(_PUBLIC_MODEL_ORDER)
        for shard in _project_validated_parent(
            campaign_id=checked_campaign_id,
            model_id=model_id,
            parent_manifest_sha256=parent_hashes[index],
            parent_plan=parents[index],
        )
    )
    if (
        len(expected_shards) != 36
        or any(shard.row_count != 40 for shard in expected_shards)
        or sum(shard.row_count for shard in expected_shards) != 1440
        or shards != expected_shards
        or any(shard.campaign_id != checked_campaign_id for shard in shards)
    ):
        _fail()

    ordered_shard_ids = tuple(item for shard in shards for item in shard.ordered_plan_item_ids)
    if (
        ordered_shard_ids
        != tuple(
            item
            for parent in parents
            for scenario_identity in dict.fromkeys(row.scenario_uid for row in parent)
            for item in (
                row.plan_item_id for row in parent if row.scenario_uid == scenario_identity
            )
        )
        or len(set(ordered_shard_ids)) != 1440
    ):
        _fail()
