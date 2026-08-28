"""Deterministic case identities and Cartesian generation plans."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TypeVar, cast
from uuid import RFC_4122, UUID

from pydantic import ValidationError

from laconian_eval.arms import Arm, arm_from_captured_bytes
from laconian_eval.capsule.canonical import (
    canonical_json,
    sha256_bytes,
    stable_digest,
    stable_digest_bytes,
)
from laconian_eval.capsule.capture import CapturedInputFile, CapturedInputs
from laconian_eval.capsule.limits import (
    RESOURCE_LIMITS_V1,
    ResourceLimitError,
    bounded_utf8_length,
    check_collection_count,
    check_plan_token_exposure,
)
from laconian_eval.capsule.manifest_models import ResolvedDatasetV2, ResolvedManifestV2
from laconian_eval.capsule.record_models import (
    CaseIndexRowV1,
    InputFileRecordV1,
    PlanRowV1,
)
from laconian_eval.capsule.schema import Arm as ArmName
from laconian_eval.capsule.schema import Locale
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import ResponseCase

_SCHEDULE_VERSION = "laconian-schedule-v1"
_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_RowT = TypeVar("_RowT")


class PlanningError(ValueError):
    """Content-free planning failure with a stable machine-readable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("capsule planning rejected")


def _require_capsule_identity(value: object) -> UUID:
    if not isinstance(value, UUID) or value.version != 4 or value.variant != RFC_4122:
        raise PlanningError("invalid_capsule_identity")
    return value


def _utf8(value: object) -> bytes:
    if type(value) is not str:
        raise PlanningError("invalid_arm_instruction")
    try:
        return value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise PlanningError("invalid_utf8") from None


def _checked_sequence_count(
    values: Sequence[object],
    *,
    limit: int,
    code: str,
) -> int:
    count = len(values)
    check_collection_count(count, limit=limit, code=code)
    return count


def _bounded_sequence_tuple(
    values: Sequence[_RowT],
    *,
    reported_count: int,
    limit: int,
    limit_code: str,
    mismatch_code: str,
) -> tuple[_RowT, ...]:
    materialized: list[_RowT] = []
    for item in values:
        check_collection_count(
            len(materialized) + 1,
            limit=limit,
            code=limit_code,
        )
        materialized.append(item)
    if len(materialized) != reported_count:
        raise PlanningError(mismatch_code)
    return tuple(materialized)


def _exact_sequence_tuple(
    values: Sequence[_RowT],
    *,
    expected_count: int,
    mismatch_code: str,
) -> tuple[_RowT, ...]:
    try:
        reported_count = len(values)
    except Exception:
        raise PlanningError(mismatch_code) from None
    if reported_count != expected_count:
        raise PlanningError(mismatch_code)

    try:
        iterator = iter(values)
    except Exception:
        raise PlanningError(mismatch_code) from None
    materialized: list[_RowT] = []
    for _ in range(expected_count):
        try:
            materialized.append(next(iterator))
        except StopIteration:
            raise PlanningError(mismatch_code) from None
        except Exception:
            raise PlanningError(mismatch_code) from None
    try:
        next(iterator)
    except StopIteration:
        return tuple(materialized)
    except Exception:
        raise PlanningError(mismatch_code) from None
    raise PlanningError(mismatch_code)


def _revalidate_resolved_manifest(value: object) -> ResolvedManifestV2:
    if not isinstance(value, ResolvedManifestV2):
        raise PlanningError("invalid_resolved_manifest")
    if getattr(value, "schedule_algorithm_version", None) != _SCHEDULE_VERSION:
        raise PlanningError("schedule_version_mismatch")
    try:
        payload = value.model_dump(mode="python", round_trip=True, warnings=False)
        return ResolvedManifestV2.model_validate(payload)
    except (TypeError, ValueError):
        raise PlanningError("invalid_resolved_manifest") from None


def _revalidate_response_case(value: object) -> ResponseCase:
    if not isinstance(value, ResponseCase):
        raise PlanningError("invalid_case_record")
    try:
        _bound_case_identifiers(value)
    except ResourceLimitError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise PlanningError("invalid_case_record") from None
    try:
        payload = value.model_dump(mode="python", round_trip=True, warnings=False)
        return ResponseCase.model_validate(payload)
    except ResourceLimitError:
        raise
    except ValidationError as exc:
        if any(error.get("type") == "string_unicode" for error in exc.errors(include_input=False)):
            raise PlanningError("invalid_utf8") from None
        raise PlanningError("invalid_case_record") from None
    except (AttributeError, TypeError, ValueError):
        raise PlanningError("invalid_case_record") from None


def _revalidate_case_index_row(value: object) -> CaseIndexRowV1:
    if not isinstance(value, CaseIndexRowV1):
        raise PlanningError("case_index_mismatch")
    try:
        bounded_utf8_length(
            value.case_id,
            limit=RESOURCE_LIMITS_V1.bounded_string_bytes,
            code="bounded_string_limit",
        )
        bounded_utf8_length(
            value.scenario_id,
            limit=RESOURCE_LIMITS_V1.bounded_string_bytes,
            code="bounded_string_limit",
        )
    except ResourceLimitError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise PlanningError("case_index_mismatch") from None
    try:
        payload = value.model_dump(mode="python", round_trip=True, warnings=False)
        return CaseIndexRowV1.model_validate(payload)
    except ResourceLimitError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise PlanningError("case_index_mismatch") from None


def _bound_case_identifiers(case: ResponseCase) -> None:
    bounded_utf8_length(
        case.id,
        limit=RESOURCE_LIMITS_V1.bounded_string_bytes,
        code="bounded_string_limit",
    )
    bounded_utf8_length(
        case.scenario_id,
        limit=RESOURCE_LIMITS_V1.bounded_string_bytes,
        code="bounded_string_limit",
    )


def recompute_dataset_content_sha256(
    dataset: ResolvedDatasetV2,
    case_records: Sequence[InputFileRecordV1],
) -> str:
    """Recompute one dataset commitment from its captured case-file records."""

    records = _exact_sequence_tuple(
        case_records,
        expected_count=len(dataset.case_file_ordinals),
        mismatch_code="dataset_content_mismatch",
    )
    records_by_ordinal: dict[int, InputFileRecordV1] = {}
    for record in records:
        if (
            record.role != "case"
            or record.dataset_id != dataset.dataset_id
            or record.binding_id is not None
            or record.role_ordinal in records_by_ordinal
        ):
            raise PlanningError("dataset_content_mismatch")
        records_by_ordinal[record.role_ordinal] = record
    expected_ordinals = set(dataset.case_file_ordinals)
    if set(records_by_ordinal) != expected_ordinals:
        raise PlanningError("dataset_content_mismatch")
    members = [
        {
            "source_ordinal": source_ordinal,
            "capsule_path": records_by_ordinal[source_ordinal].capsule_path,
            "byte_length": records_by_ordinal[source_ordinal].byte_length,
            "sha256": records_by_ordinal[source_ordinal].sha256,
        }
        for source_ordinal in sorted(expected_ordinals)
    ]
    return stable_digest(
        "laconian-dataset-content-v1",
        {
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.dataset_version,
            "members": members,
        },
    )


def scenario_uid(dataset_id: str, dataset_version: str, scenario_id: str) -> str:
    """Return the dataset-scoped scenario identity from its exact v1 preimage."""

    return stable_digest(
        "laconian-scenario-v1",
        {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "scenario_id": scenario_id,
        },
    )


def case_uid(
    scenario_identity: str,
    case_id: str,
    locale: Locale,
    case_definition_sha256: str,
) -> str:
    """Return the localized case identity from its exact v1 preimage."""

    return stable_digest(
        "laconian-case-v1",
        {
            "scenario_uid": scenario_identity,
            "case_id": case_id,
            "locale": locale,
            "case_definition_sha256": case_definition_sha256,
        },
    )


def schedule_digest_bytes(
    seed: int,
    case_identity: str,
    repetition: int,
    arm: ArmName,
) -> bytes:
    """Return the raw schedule digest used as the primary arm-sort key."""

    return stable_digest_bytes(
        _SCHEDULE_VERSION,
        {
            "seed": seed,
            "case_uid": case_identity,
            "repetition": repetition,
            "arm": arm,
        },
    )


def block_id(capsule_identity: UUID, case_identity: str, repetition: int) -> str:
    """Return a case/repetition block identity."""

    return stable_digest(
        "laconian-block-v1",
        {
            "run_id": _require_capsule_identity(capsule_identity),
            "case_uid": case_identity,
            "repetition": repetition,
        },
    )


def pairing_unit_id(capsule_identity: UUID, case_identity: str, repetition: int) -> str:
    """Return the independently domain-separated pairing-unit identity."""

    return stable_digest(
        "laconian-pairing-unit-v1",
        {
            "run_id": _require_capsule_identity(capsule_identity),
            "case_uid": case_identity,
            "repetition": repetition,
        },
    )


def request_config_sha256(manifest: ResolvedManifestV2) -> str:
    """Bind every provider-request setting except secrets and environment values."""

    manifest = _revalidate_resolved_manifest(manifest)
    return stable_digest(
        "laconian-request-config-v1",
        {
            "provider_kind": manifest.provider.kind,
            "requested_model": manifest.provider.model,
            "generation": {
                "max_output_tokens": manifest.generation.max_output_tokens,
                "temperature": manifest.generation.temperature,
            },
            "retry": {
                "max_transient_retries": manifest.retry.max_transient_retries,
                "timeout_seconds": manifest.retry.timeout_seconds,
            },
            "instruction_placement": manifest.instruction_placement,
            "store": False,
            "tools": [],
        },
    )


def plan_item_id(
    capsule_identity: UUID,
    case_identity: str,
    repetition: int,
    arm: ArmName,
    instruction_sha256: str,
    request_config_digest: str,
) -> str:
    """Return one immutable provider-call intent identity."""

    return stable_digest(
        "laconian-plan-item-v1",
        {
            "run_id": _require_capsule_identity(capsule_identity),
            "case_uid": case_identity,
            "repetition": repetition,
            "arm": arm,
            "instruction_sha256": instruction_sha256,
            "request_config_sha256": request_config_digest,
        },
    )


def _manifest_datasets_by_source(
    manifest: ResolvedManifestV2,
) -> dict[int, ResolvedDatasetV2]:
    ownership: dict[int, ResolvedDatasetV2] = {}
    for dataset in manifest.capsule.datasets:
        for source_ordinal in dataset.case_file_ordinals:
            if source_ordinal in ownership:
                raise PlanningError("case_capture_mismatch")
            ownership[source_ordinal] = dataset
    if set(ownership) != set(range(len(manifest.case_files))):
        raise PlanningError("case_capture_mismatch")
    return ownership


def _validate_capture_agreement(
    captured_inputs: CapturedInputs,
    manifest: ResolvedManifestV2,
) -> dict[int, ResolvedDatasetV2]:
    captured_manifest = _revalidate_resolved_manifest(captured_inputs.resolved_manifest)
    if captured_manifest != manifest:
        raise PlanningError("manifest_capture_mismatch")
    try:
        manifest_bytes = canonical_json(manifest.model_dump(mode="json"))
    except UnicodeEncodeError:
        raise PlanningError("invalid_utf8") from None
    if (
        captured_inputs.resolved_manifest_bytes != manifest_bytes
        or captured_inputs.manifest_sha256 != sha256_bytes(manifest_bytes)
    ):
        raise PlanningError("manifest_capture_mismatch")
    if manifest.schedule_algorithm_version != _SCHEDULE_VERSION:
        raise PlanningError("schedule_version_mismatch")

    ownership = _manifest_datasets_by_source(manifest)
    case_inputs: dict[int, CapturedInputFile] = {}
    for captured_file in captured_inputs.files:
        record = captured_file.record
        if record.role != "case":
            continue
        if record.role_ordinal in case_inputs:
            raise PlanningError("case_capture_mismatch")
        if record.byte_length != len(captured_file.data) or record.sha256 != sha256_bytes(
            captured_file.data
        ):
            raise PlanningError("case_capture_mismatch")
        case_inputs[record.role_ordinal] = captured_file
    if set(case_inputs) != set(range(len(manifest.case_files))):
        raise PlanningError("case_capture_mismatch")
    if len(captured_inputs.case_files) != len(manifest.case_files):
        raise PlanningError("case_capture_mismatch")

    for source_ordinal, case_file in enumerate(captured_inputs.case_files):
        record = case_file.record
        dataset = ownership[source_ordinal]
        if (
            case_file.source_ordinal != source_ordinal
            or case_file.input_file != case_inputs[source_ordinal]
            or record.role_ordinal != source_ordinal
            or record.capsule_path != manifest.case_files[source_ordinal]
            or case_file.dataset_id != dataset.dataset_id
            or record.dataset_id != dataset.dataset_id
            or not case_file.cases
        ):
            raise PlanningError("case_capture_mismatch")

    for dataset in manifest.capsule.datasets:
        records = tuple(case_inputs[ordinal].record for ordinal in dataset.case_file_ordinals)
        if recompute_dataset_content_sha256(dataset, records) != dataset.dataset_content_sha256:
            raise PlanningError("dataset_content_mismatch")
    return ownership


def _hash_case(case: ResponseCase) -> tuple[str, str]:
    try:
        definition = response_case_sha256(case)
        prompt = case.prompt
        if type(prompt) is not str:
            raise PlanningError("invalid_case_record")
        prompt_digest = hashlib.sha256(prompt.encode("utf-8", errors="strict")).hexdigest()
    except UnicodeEncodeError:
        raise PlanningError("invalid_utf8") from None
    return definition, prompt_digest


def _validate_case_locale(case_id_value: str, locale: Locale) -> None:
    if not case_id_value.endswith(f"-{locale}"):
        raise PlanningError("case_locale_mismatch")


def materialize_case_index(
    captured_inputs: CapturedInputs,
    resolved_manifest: ResolvedManifestV2,
) -> tuple[CaseIndexRowV1, ...]:
    """Materialize the exact source/record-ordered localized case index."""

    resolved_manifest = _revalidate_resolved_manifest(resolved_manifest)
    ownership = _validate_capture_agreement(captured_inputs, resolved_manifest)
    case_count = sum(len(case_file.cases) for case_file in captured_inputs.case_files)
    check_collection_count(
        case_count,
        limit=RESOURCE_LIMITS_V1.case_records,
        code="case_records_limit",
    )
    if case_count == 0:
        raise PlanningError("case_capture_mismatch")

    rows: list[CaseIndexRowV1] = []
    case_ids: set[str] = set()
    case_uids: set[str] = set()
    locales_by_scenario: dict[tuple[str, str], set[str]] = {}
    groups_by_scenario_uid: dict[str, tuple[str, str]] = {}
    for case_file in captured_inputs.case_files:
        dataset = ownership[case_file.source_ordinal]
        for record_ordinal, captured_case in enumerate(case_file.cases):
            case = _revalidate_response_case(captured_case)
            if case.id in case_ids:
                raise PlanningError("duplicate_case_id")
            case_ids.add(case.id)
            _validate_case_locale(case.id, case.locale)
            group = (dataset.dataset_id, case.scenario_id)
            locales = locales_by_scenario.setdefault(group, set())
            if case.locale in locales:
                raise PlanningError("dataset_locale_ownership")
            locales.add(case.locale)
            definition_digest, prompt_digest = _hash_case(case)
            try:
                scenario_identity = scenario_uid(
                    dataset.dataset_id,
                    dataset.dataset_version,
                    case.scenario_id,
                )
                case_identity = case_uid(
                    scenario_identity,
                    case.id,
                    case.locale,
                    definition_digest,
                )
            except UnicodeEncodeError:
                raise PlanningError("invalid_utf8") from None
            prior_group = groups_by_scenario_uid.setdefault(scenario_identity, group)
            if prior_group != group:
                raise PlanningError("duplicate_scenario_uid")
            if case_identity in case_uids:
                raise PlanningError("duplicate_case_uid")
            case_uids.add(case_identity)
            rows.append(
                CaseIndexRowV1(
                    dataset_id=dataset.dataset_id,
                    dataset_version=dataset.dataset_version,
                    dataset_role=dataset.role,
                    source_ordinal=case_file.source_ordinal,
                    record_ordinal=record_ordinal,
                    case_id=case.id,
                    case_uid=case_identity,
                    scenario_id=case.scenario_id,
                    scenario_uid=scenario_identity,
                    locale=case.locale,
                    category=case.category,
                    case_definition_sha256=definition_digest,
                    prompt_sha256=prompt_digest,
                )
            )
    if any(locales != {"en", "ru"} for locales in locales_by_scenario.values()):
        raise PlanningError("dataset_locale_ownership")
    return tuple(rows)


def validate_case_index(
    rows: Sequence[CaseIndexRowV1],
    captured_inputs: CapturedInputs,
    resolved_manifest: ResolvedManifestV2,
) -> None:
    """Recompute and require byte-semantic equality for every case-index row."""

    resolved_manifest = _revalidate_resolved_manifest(resolved_manifest)
    reported_count = _checked_sequence_count(
        rows,
        limit=RESOURCE_LIMITS_V1.case_records,
        code="case_records_limit",
    )
    unvalidated_candidate = _bounded_sequence_tuple(
        rows,
        reported_count=reported_count,
        limit=RESOURCE_LIMITS_V1.case_records,
        limit_code="case_records_limit",
        mismatch_code="case_index_mismatch",
    )
    candidate = tuple(_revalidate_case_index_row(row) for row in unvalidated_candidate)
    expected = materialize_case_index(captured_inputs, resolved_manifest)
    if candidate != expected:
        raise PlanningError("case_index_mismatch")


def _validate_case_index_cross_rows(
    rows: Sequence[CaseIndexRowV1],
    manifest: ResolvedManifestV2,
    *,
    reported_count: int,
) -> tuple[CaseIndexRowV1, ...]:
    unvalidated_rows = _bounded_sequence_tuple(
        rows,
        reported_count=reported_count,
        limit=RESOURCE_LIMITS_V1.case_records,
        limit_code="case_records_limit",
        mismatch_code="case_index_mismatch",
    )
    materialized = tuple(_revalidate_case_index_row(row) for row in unvalidated_rows)
    if not materialized:
        raise PlanningError("case_index_mismatch")
    ownership = _manifest_datasets_by_source(manifest)
    case_ids: set[str] = set()
    case_uids: set[str] = set()
    locales_by_scenario: dict[tuple[str, str], set[str]] = {}
    groups_by_scenario_uid: dict[str, tuple[str, str]] = {}
    expected_record_ordinal: dict[int, int] = {}
    previous_position: tuple[int, int] | None = None
    seen_sources: set[int] = set()
    for row in materialized:
        position = (row.source_ordinal, row.record_ordinal)
        if previous_position is not None and position <= previous_position:
            raise PlanningError("case_index_mismatch")
        previous_position = position
        expected_record = expected_record_ordinal.get(row.source_ordinal, 0)
        if row.record_ordinal != expected_record:
            raise PlanningError("case_index_mismatch")
        expected_record_ordinal[row.source_ordinal] = expected_record + 1
        seen_sources.add(row.source_ordinal)
        dataset = ownership.get(row.source_ordinal)
        if dataset is None or (
            row.dataset_id != dataset.dataset_id
            or row.dataset_version != dataset.dataset_version
            or row.dataset_role != dataset.role
        ):
            raise PlanningError("case_index_mismatch")
        if row.case_id in case_ids or row.case_uid in case_uids:
            raise PlanningError("case_index_mismatch")
        case_ids.add(row.case_id)
        case_uids.add(row.case_uid)
        try:
            _validate_case_locale(row.case_id, row.locale)
            expected_scenario = scenario_uid(
                row.dataset_id,
                row.dataset_version,
                row.scenario_id,
            )
            expected_case = case_uid(
                expected_scenario,
                row.case_id,
                row.locale,
                row.case_definition_sha256,
            )
        except (PlanningError, UnicodeEncodeError):
            raise PlanningError("case_index_mismatch") from None
        if row.scenario_uid != expected_scenario or row.case_uid != expected_case:
            raise PlanningError("case_index_mismatch")
        group = (row.dataset_id, row.scenario_id)
        prior_group = groups_by_scenario_uid.setdefault(row.scenario_uid, group)
        if prior_group != group:
            raise PlanningError("case_index_mismatch")
        locales = locales_by_scenario.setdefault(group, set())
        if row.locale in locales:
            raise PlanningError("case_index_mismatch")
        locales.add(row.locale)
    if seen_sources != set(range(len(manifest.case_files))) or any(
        locales != {"en", "ru"} for locales in locales_by_scenario.values()
    ):
        raise PlanningError("case_index_mismatch")
    return materialized


def _validated_arms(
    manifest: ResolvedManifestV2,
    captured_arms: Sequence[Arm],
) -> tuple[Arm, ...]:
    reported_count = len(captured_arms)
    if reported_count != len(manifest.arms):
        raise PlanningError("arm_manifest_mismatch")
    arms_list: list[Arm] = []
    for arm in captured_arms:
        if len(arms_list) >= reported_count:
            raise PlanningError("arm_manifest_mismatch")
        arms_list.append(arm)
    if len(arms_list) != reported_count:
        raise PlanningError("arm_manifest_mismatch")
    arms = tuple(arms_list)
    names = tuple(arm.name for arm in arms)
    if names != manifest.arms or len(names) != len(set(names)):
        raise PlanningError("arm_manifest_mismatch")
    for arm in arms:
        if arm.name == "baseline":
            if arm.instruction is not None:
                raise PlanningError("invalid_baseline_arm")
            data = b""
        else:
            data = _utf8(arm.instruction)
        if sha256_bytes(data) != arm.sha256:
            raise PlanningError("arm_hash_mismatch")
        if arm.name == "baseline" and arm.sha256 != _EMPTY_SHA256:
            raise PlanningError("arm_hash_mismatch")
        try:
            reconstructed = arm_from_captured_bytes(arm.name, data)
        except (TypeError, ValueError):
            raise PlanningError("invalid_arm_instruction") from None
        if reconstructed != arm:
            raise PlanningError("invalid_arm_instruction")
    return arms


def materialize_plan(
    capsule_identity: UUID,
    resolved_manifest: ResolvedManifestV2,
    case_index: Sequence[CaseIndexRowV1],
    captured_arms: Sequence[Arm],
) -> tuple[PlanRowV1, ...]:
    """Materialize the bounded deterministic case x repetition x arm plan."""

    run_id = _require_capsule_identity(capsule_identity)
    resolved_manifest = _revalidate_resolved_manifest(resolved_manifest)
    case_count = _checked_sequence_count(
        case_index,
        limit=RESOURCE_LIMITS_V1.case_records,
        code="case_records_limit",
    )
    cardinality = case_count * resolved_manifest.repetitions * len(resolved_manifest.arms)
    check_collection_count(
        cardinality,
        limit=RESOURCE_LIMITS_V1.plan_rows,
        code="plan_rows_limit",
    )
    check_plan_token_exposure(
        resolved_manifest.generation.max_output_tokens,
        cardinality,
        limits=RESOURCE_LIMITS_V1,
    )
    cases = _validate_case_index_cross_rows(
        case_index,
        resolved_manifest,
        reported_count=case_count,
    )
    arms = _validated_arms(resolved_manifest, captured_arms)

    config_digest = request_config_sha256(resolved_manifest)
    rows: list[PlanRowV1] = []
    plan_ids: set[str] = set()
    block_ids: set[str] = set()
    pairing_ids: set[str] = set()
    for case in cases:
        for repetition in range(resolved_manifest.repetitions):
            ordered_arms = sorted(
                arms,
                key=lambda arm: (
                    schedule_digest_bytes(
                        resolved_manifest.arm_order_seed,
                        case.case_uid,
                        repetition,
                        cast(ArmName, arm.name),
                    ),
                    arm.name,
                ),
            )
            block_identity = block_id(run_id, case.case_uid, repetition)
            pairing_identity = pairing_unit_id(run_id, case.case_uid, repetition)
            if (
                block_identity == pairing_identity
                or block_identity in block_ids
                or block_identity in pairing_ids
                or pairing_identity in block_ids
                or pairing_identity in pairing_ids
            ):
                raise PlanningError("duplicate_plan_block_id")
            block_ids.add(block_identity)
            pairing_ids.add(pairing_identity)
            for arm_position, arm in enumerate(ordered_arms):
                arm_name = cast(ArmName, arm.name)
                item_identity = plan_item_id(
                    run_id,
                    case.case_uid,
                    repetition,
                    arm_name,
                    arm.sha256,
                    config_digest,
                )
                if item_identity in plan_ids:
                    raise PlanningError("duplicate_plan_item_id")
                plan_ids.add(item_identity)
                rows.append(
                    PlanRowV1(
                        ordinal=len(rows),
                        plan_item_id=item_identity,
                        pairing_unit_id=pairing_identity,
                        case_uid=case.case_uid,
                        scenario_uid=case.scenario_uid,
                        case_id=case.case_id,
                        locale=case.locale,
                        repetition=repetition,
                        arm=arm_name,
                        block_id=block_identity,
                        arm_position=arm_position,
                        prompt_sha256=case.prompt_sha256,
                        case_definition_sha256=case.case_definition_sha256,
                        instruction_sha256=arm.sha256,
                        request_config_sha256=config_digest,
                    )
                )
    if len(rows) != cardinality:
        raise PlanningError("plan_mismatch")
    return tuple(rows)


def validate_plan(
    rows: Sequence[PlanRowV1],
    capsule_identity: UUID,
    resolved_manifest: ResolvedManifestV2,
    case_index: Sequence[CaseIndexRowV1],
    captured_arms: Sequence[Arm],
) -> None:
    """Recompute and require exact Cartesian coverage and row equality."""

    resolved_manifest = _revalidate_resolved_manifest(resolved_manifest)
    reported_count = _checked_sequence_count(
        rows,
        limit=RESOURCE_LIMITS_V1.plan_rows,
        code="plan_rows_limit",
    )
    check_plan_token_exposure(
        resolved_manifest.generation.max_output_tokens,
        reported_count,
        limits=RESOURCE_LIMITS_V1,
    )
    candidate = _bounded_sequence_tuple(
        rows,
        reported_count=reported_count,
        limit=RESOURCE_LIMITS_V1.plan_rows,
        limit_code="plan_rows_limit",
        mismatch_code="plan_mismatch",
    )
    expected = materialize_plan(
        capsule_identity,
        resolved_manifest,
        case_index,
        captured_arms,
    )
    if candidate != expected:
        raise PlanningError("plan_mismatch")
