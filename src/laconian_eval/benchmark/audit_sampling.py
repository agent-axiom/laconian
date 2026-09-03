"""Frozen certainty/Hamilton human-audit sampling and durable sample roots."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Literal, Self, cast
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from laconian_eval.benchmark.attachments import (
    RationalV1,
    canonical_json_v1,
    parse_canonical_json_v1,
)
from laconian_eval.benchmark.context import BenchmarkProtocolBindingsV1
from laconian_eval.benchmark.judge import RubricItemV1
from laconian_eval.benchmark.provider_evidence import (
    _AUDIT_POPULATION_ATTACHMENT_MAX_BYTES,
    _AUDIT_POPULATION_JSONL_MAX_BYTES,
    AuditPopulationAttachmentV1,
    AuditPopulationRecordV1,
    VerifiedAuditPopulationV1,
    VerifiedBenchmarkProviderEvidenceV1,
    _build_audit_population_from_checked,
    _canonical_population_jsonl,
    _load_verified_audit_population_from_bytes,
    _revalidate_verified_audit_population_v1,
    _revalidate_verified_provider_evidence_v1,
)
from laconian_eval.benchmark.seeds import derive_seed128
from laconian_eval.capsule.bounded_io import open_directory_no_follow
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.capsule.filesystem import (
    DestinationCollisionError,
    FilesystemPosixOps,
    cleanup_owned_staging,
    create_owned_staging,
    publish_owned_staging,
)
from laconian_eval.capsule.posix import PosixOps
from laconian_eval.models import WarningSeverity

_MODELS = ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra")
_LOCALES = ("en", "ru")
_ARMS = ("baseline", "caveman", "if", "concise")
_CERTAINTY_CASES = frozenset({"safety-medical-en", "safety-medical-ru"})
_AUDIT_SAMPLE_MEMBER_MAX_BYTES = {
    "population-attachment.json": _AUDIT_POPULATION_ATTACHMENT_MAX_BYTES,
    "population.jsonl": _AUDIT_POPULATION_JSONL_MAX_BYTES,
    "sample-manifest.json": 16 * 1024 * 1024,
    "blind-packet.json": 64 * 1024 * 1024,
}


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def _validate_nested_model_owner(
    value: object,
    expected_owner: type[BaseModel],
    *,
    collection: bool = False,
    json_mode: bool = False,
) -> object:
    """Reject Python-supplied model subclasses before Pydantic can normalize them."""

    values = value if collection and isinstance(value, (list, tuple)) else (value,)
    if any(isinstance(item, BaseModel) and type(item) is not expected_owner for item in values):
        raise ValueError(f"field must contain exact {expected_owner.__name__} owners")
    if collection and json_mode and type(value) is list:
        return tuple(
            expected_owner.model_validate_json(canonical_json_v1(item))
            if type(item) is dict
            else item
            for item in value
        )
    return value


class CellAllocationV1(_StrictFrozenModel):
    cell_id: str
    noncertainty_population: int = Field(ge=0)
    local_minimum: int = Field(ge=0, le=1)
    proportional_numerator: int = Field(ge=0)
    proportional_denominator: int = Field(ge=1)
    floor_seats: int = Field(ge=0)
    fractional_remainder: RationalV1
    residual_rank: int | None = Field(default=None, ge=1)
    global_fill_passes: tuple[int, ...]
    selected_noncertainty: int = Field(ge=0)
    seed: int = Field(ge=0, lt=2**128)
    permutation: tuple[str, ...]
    inclusion_probability: RationalV1

    @field_validator("fractional_remainder", "inclusion_probability", mode="before")
    @classmethod
    def reject_foreign_rational_owners(cls, value: object) -> object:
        return _validate_nested_model_owner(value, RationalV1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            type(self.fractional_remainder) is not RationalV1
            or type(self.inclusion_probability) is not RationalV1
            or len(self.permutation) != self.noncertainty_population
            or len(set(self.permutation)) != len(self.permutation)
            or self.selected_noncertainty > self.noncertainty_population
            or tuple(self.global_fill_passes) != tuple(sorted(set(self.global_fill_passes)))
        ):
            raise ValueError("audit cell allocation count mismatch")
        expected_probability = RationalV1(
            numerator=self.selected_noncertainty,
            denominator=max(1, self.noncertainty_population),
        )
        if self.inclusion_probability != expected_probability:
            raise ValueError("audit cell inclusion probability mismatch")
        return self


class AuditSampleManifestV1(_StrictFrozenModel):
    schema_version: Literal["audit-sample-manifest-v1"]
    campaign_id: str
    protocol_bindings: BenchmarkProtocolBindingsV1
    population_attachment_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    target: int = Field(ge=144)
    total_certainty_count: int = Field(ge=0)
    certainty_record_ids: tuple[str, ...]
    stratum_quotas: Mapping[str, int]
    cells: tuple[CellAllocationV1, ...]
    ordered_selected_record_ids: tuple[str, ...]
    sample_manifest_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @field_validator("protocol_bindings", mode="before")
    @classmethod
    def reject_foreign_protocol_owner(cls, value: object) -> object:
        return _validate_nested_model_owner(value, BenchmarkProtocolBindingsV1)

    @field_validator("cells", mode="before")
    @classmethod
    def reject_foreign_cell_owners(cls, value: object, info: ValidationInfo) -> object:
        return _validate_nested_model_owner(
            value,
            CellAllocationV1,
            collection=True,
            json_mode=info.mode == "json",
        )

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if (
            type(self.protocol_bindings) is not BenchmarkProtocolBindingsV1
            or any(type(row) is not CellAllocationV1 for row in self.cells)
            or self.total_certainty_count != len(self.certainty_record_ids)
            or self.certainty_record_ids
            != tuple(sorted(set(self.certainty_record_ids), key=str.encode))
            or tuple(self.stratum_quotas)
            != tuple(sorted(self.stratum_quotas, key=lambda item: item.encode("utf-8")))
            or tuple(row.cell_id for row in self.cells)
            != tuple(sorted({row.cell_id for row in self.cells}, key=str.encode))
            or self.ordered_selected_record_ids
            != tuple(sorted(set(self.ordered_selected_record_ids), key=str.encode))
            or not set(self.certainty_record_ids) <= set(self.ordered_selected_record_ids)
        ):
            raise ValueError("audit sample manifest ordering/coverage mismatch")
        expected = stable_digest(
            "laconian-audit-sample-manifest-v1",
            self.model_dump(mode="json", exclude={"sample_manifest_sha256"}),
        )
        if self.sample_manifest_sha256 != expected:
            raise ValueError("audit sample manifest self digest mismatch")
        return self


class BlindAuditRecordV1(_StrictFrozenModel):
    audit_record_id: str = Field(pattern="^[0-9a-f]{64}$")
    prompt: str
    rubric: tuple[RubricItemV1, ...]
    material_warning_requirement: str | None
    warning_severity: WarningSeverity | None
    locale: str
    candidate_response: str

    @field_validator("rubric", mode="before")
    @classmethod
    def reject_foreign_rubric_owners(cls, value: object, info: ValidationInfo) -> object:
        return _validate_nested_model_owner(
            value,
            RubricItemV1,
            collection=True,
            json_mode=info.mode == "json",
        )

    @model_validator(mode="after")
    def validate_exact_rubric_owners(self) -> Self:
        if any(type(row) is not RubricItemV1 for row in self.rubric):
            raise ValueError("blind audit record contains a foreign rubric owner")
        return self


class BlindAuditPacketV1(_StrictFrozenModel):
    campaign_registry_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    sample_manifest_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    records: tuple[BlindAuditRecordV1, ...]
    packet_sha256: str = Field(pattern="^[0-9a-f]{64}$")

    @field_validator("records", mode="before")
    @classmethod
    def reject_foreign_record_owners(cls, value: object, info: ValidationInfo) -> object:
        return _validate_nested_model_owner(
            value,
            BlindAuditRecordV1,
            collection=True,
            json_mode=info.mode == "json",
        )

    @model_validator(mode="after")
    def validate_packet(self) -> Self:
        ids = tuple(row.audit_record_id for row in self.records)
        if any(type(row) is not BlindAuditRecordV1 for row in self.records) or ids != tuple(
            sorted(set(ids), key=str.encode)
        ):
            raise ValueError("blind packet IDs must be unique and byte-sorted")
        expected = stable_digest(
            "laconian-blind-audit-packet-v1",
            self.model_dump(mode="json", exclude={"packet_sha256"}),
        )
        if self.packet_sha256 != expected:
            raise ValueError("blind packet self digest mismatch")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedAuditSampleRootV1:
    population: VerifiedAuditPopulationV1
    manifest: AuditSampleManifestV1
    packet: BlindAuditPacketV1
    audit_sample_root_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.population) is not VerifiedAuditPopulationV1
            or type(self.manifest) is not AuditSampleManifestV1
            or type(self.packet) is not BlindAuditPacketV1
            or type(self.audit_sample_root_sha256) is not str
        ):
            raise TypeError("verified audit sample root requires exact owners")


@dataclass(frozen=True, slots=True)
class _SamplingDesign:
    target: int
    certainty_record_ids: tuple[str, ...]
    stratum_quotas: Mapping[str, int]
    cells: tuple[CellAllocationV1, ...]
    ordered_selected_record_ids: tuple[str, ...]


@dataclass(slots=True)
class _MutableCell:
    cell_id: str
    population: tuple[str, ...]
    local_minimum: int
    proportional_numerator: int
    proportional_denominator: int
    floor_seats: int
    fractional_remainder: Fraction
    residual_rank: int | None
    selected: int
    seed: int
    permutation: tuple[str, ...]
    global_passes: list[int]


def _revalidate_model(model_type: type[BaseModel], value: object) -> BaseModel:
    if type(value) is not model_type:
        raise TypeError(f"expected exact {model_type.__name__}")
    return model_type.model_validate(
        model_type.model_dump(value, mode="python", round_trip=True, warnings=False)
    )


def _stratum_id(model: str, locale: str, arm: str) -> str:
    return canonical_json_v1({"generation_model": model, "locale": locale, "arm": arm}).decode(
        "utf-8"
    )


def _cell_id(model: str, locale: str, arm: str, decision: bool) -> str:
    return canonical_json_v1(
        {
            "generation_model": model,
            "locale": locale,
            "arm": arm,
            "blinded_judge_decision": decision,
        }
    ).decode("utf-8")


def _is_certainty(record: AuditPopulationRecordV1) -> bool:
    return (
        record.blinded_judge_decision
        and record.case_id in _CERTAINTY_CASES
        and record.arm in {"if", "concise"}
    )


def _target_for_certainty_count(certainty_count: int) -> int:
    if type(certainty_count) is not int or certainty_count < 0:
        raise ValueError("certainty count must be a nonnegative integer")
    return max(144, certainty_count)


def _permutation(
    record_ids: tuple[str, ...],
    *,
    cell_id: str,
    campaign_seed: str,
    input_tag_commit: str,
    judge_protocol_sha256: str,
) -> tuple[int, tuple[str, ...]]:
    seed = derive_seed128(
        "laconian-human-audit-v1/cell/" + cell_id,
        campaign_seed,
        input_tag_commit,
        judge_protocol_sha256,
    )
    ordered = tuple(sorted(record_ids, key=str.encode))
    indexes = np.random.Generator(np.random.PCG64(seed)).permutation(len(ordered))
    return seed, tuple(ordered[int(index)] for index in indexes)


def _apply_global_fill(
    cells: dict[str, _MutableCell],
    *,
    selected_total: int,
    target: int,
    population_size: int,
) -> int:
    """Fill at most one available record per byte-ordered cell and numbered pass."""

    if (
        type(cells) is not dict
        or any(
            type(identifier) is not str
            or type(cell) is not _MutableCell
            or cell.cell_id != identifier
            or type(cell.population) is not tuple
            or not 0 <= cell.selected <= len(cell.population)
            or type(cell.global_passes) is not list
            or cell.global_passes != sorted(set(cell.global_passes))
            for identifier, cell in cells.items()
        )
        or any(
            type(value) is not int or value < 0
            for value in (selected_total, target, population_size)
        )
        or selected_total < sum(cell.selected for cell in cells.values())
    ):
        raise ValueError("global fill requires one strict allocation state")
    limit = min(target, population_size)
    pass_number = 0
    ordered_cells = tuple(sorted(cells, key=str.encode))
    while selected_total < limit:
        pass_number += 1
        added = 0
        for identifier in ordered_cells:
            cell = cells[identifier]
            if selected_total >= limit:
                break
            if cell.selected >= len(cell.population):
                continue
            cell.selected += 1
            cell.global_passes.append(pass_number)
            selected_total += 1
            added += 1
        if not added:
            break
    return selected_total


def _compute_sampling_design(
    records: Sequence[AuditPopulationRecordV1],
    *,
    campaign_seed: str,
    input_tag_commit: str,
    judge_protocol_sha256: str,
    target: int,
) -> _SamplingDesign:
    """Pure exact design used by both public sampling and defense-in-depth golden tests."""

    if type(records) not in {tuple, list} or any(
        type(row) is not AuditPopulationRecordV1 for row in records
    ):
        raise TypeError("sampling design requires exact audit population records")
    checked = tuple(
        cast(AuditPopulationRecordV1, _revalidate_model(AuditPopulationRecordV1, row))
        for row in records
    )
    ids = tuple(row.canonical_record_id for row in checked)
    if len(set(ids)) != len(ids):
        raise ValueError("sampling population contains duplicate canonical IDs")
    if type(target) is not int or target < 0:
        raise ValueError("sampling target must be a nonnegative integer")
    if any(
        row.generation_model not in _MODELS or row.locale not in _LOCALES or row.arm not in _ARMS
        for row in checked
    ):
        raise ValueError("sampling record is outside the frozen 24 strata")
    certainty = tuple(
        sorted(
            (row.canonical_record_id for row in checked if _is_certainty(row)),
            key=str.encode,
        )
    )
    certainty_set = set(certainty)
    strata = tuple(
        sorted(
            (
                _stratum_id(model, locale, arm)
                for model in _MODELS
                for locale in _LOCALES
                for arm in _ARMS
            ),
            key=str.encode,
        )
    )
    records_by_stratum: dict[str, list[AuditPopulationRecordV1]] = {
        stratum: [] for stratum in strata
    }
    for row in checked:
        records_by_stratum[_stratum_id(row.generation_model, row.locale, row.arm)].append(row)

    quotas: dict[str, int] = {}
    mutable: dict[str, _MutableCell] = {}
    for stratum in strata:
        stratum_rows = records_by_stratum[stratum]
        certainty_count = sum(row.canonical_record_id in certainty_set for row in stratum_rows)
        noncertainty = tuple(
            row for row in stratum_rows if row.canonical_record_id not in certainty_set
        )
        quota = max(0, min(6 - certainty_count, len(noncertainty)))
        quotas[stratum] = quota
        cell_rows: dict[str, list[str]] = {}
        for row in noncertainty:
            identifier = _cell_id(
                row.generation_model,
                row.locale,
                row.arm,
                row.blinded_judge_decision,
            )
            cell_rows.setdefault(identifier, []).append(row.canonical_record_id)
        cell_ids = tuple(sorted(cell_rows, key=str.encode))
        use_minimum = quota >= len(cell_ids)
        minima = {identifier: int(use_minimum) for identifier in cell_ids}
        capacities = {
            identifier: len(cell_rows[identifier]) - minima[identifier] for identifier in cell_ids
        }
        residual_total = quota - sum(minima.values())
        denominator = sum(capacities.values())
        for identifier in cell_ids:
            capacity = capacities[identifier]
            numerator = residual_total * capacity
            recorded_denominator = denominator if denominator else 1
            floor = numerator // recorded_denominator if denominator else 0
            remainder = Fraction(
                numerator % recorded_denominator if denominator else 0,
                recorded_denominator,
            )
            seed, permutation = _permutation(
                tuple(cell_rows[identifier]),
                cell_id=identifier,
                campaign_seed=campaign_seed,
                input_tag_commit=input_tag_commit,
                judge_protocol_sha256=judge_protocol_sha256,
            )
            mutable[identifier] = _MutableCell(
                cell_id=identifier,
                population=tuple(cell_rows[identifier]),
                local_minimum=minima[identifier],
                proportional_numerator=numerator,
                proportional_denominator=recorded_denominator,
                floor_seats=floor,
                fractional_remainder=remainder,
                residual_rank=None,
                selected=minima[identifier] + floor,
                seed=seed,
                permutation=permutation,
                global_passes=[],
            )
        remaining = quota - sum(mutable[identifier].selected for identifier in cell_ids)
        ranked = sorted(
            (mutable[identifier] for identifier in cell_ids),
            key=lambda cell: (-cell.fractional_remainder, cell.cell_id.encode("utf-8")),
        )
        for rank, cell in enumerate(ranked, start=1):
            cell.residual_rank = rank
            if remaining and cell.selected < len(cell.population):
                cell.selected += 1
                remaining -= 1
        if remaining:
            raise ValueError("Hamilton allocation could not place every local seat")

    selected_total = _apply_global_fill(
        mutable,
        selected_total=len(certainty) + sum(cell.selected for cell in mutable.values()),
        target=target,
        population_size=len(checked),
    )

    selected = set(certainty)
    for cell in mutable.values():
        selected.update(cell.permutation[: cell.selected])
    if len(selected) != selected_total:
        raise ValueError("sampling design selected a duplicate population record")
    cells = tuple(
        CellAllocationV1(
            cell_id=cell.cell_id,
            noncertainty_population=len(cell.population),
            local_minimum=cell.local_minimum,
            proportional_numerator=cell.proportional_numerator,
            proportional_denominator=cell.proportional_denominator,
            floor_seats=cell.floor_seats,
            fractional_remainder=RationalV1(
                numerator=cell.fractional_remainder.numerator,
                denominator=cell.fractional_remainder.denominator,
            ),
            residual_rank=cell.residual_rank,
            global_fill_passes=tuple(cell.global_passes),
            selected_noncertainty=cell.selected,
            seed=cell.seed,
            permutation=cell.permutation,
            inclusion_probability=RationalV1(
                numerator=cell.selected,
                denominator=max(1, len(cell.population)),
            ),
        )
        for cell in sorted(mutable.values(), key=lambda item: item.cell_id.encode("utf-8"))
    )
    return _SamplingDesign(
        target=target,
        certainty_record_ids=certainty,
        stratum_quotas={key: quotas[key] for key in sorted(quotas, key=str.encode)},
        cells=cells,
        ordered_selected_record_ids=tuple(sorted(selected, key=str.encode)),
    )


def _population_and_provider(
    population: VerifiedAuditPopulationV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> tuple[VerifiedAuditPopulationV1, VerifiedBenchmarkProviderEvidenceV1]:
    evidence = _revalidate_verified_provider_evidence_v1(provider_evidence)
    checked_population = _revalidate_verified_audit_population_v1(population)
    expected = _build_audit_population_from_checked(evidence)
    if canonical_json_v1(
        checked_population.attachment.model_dump(mode="json")
    ) != canonical_json_v1(
        expected.attachment.model_dump(mode="json")
    ) or _canonical_population_jsonl(checked_population.records) != _canonical_population_jsonl(
        expected.records
    ):
        raise ValueError("audit population is not derived from the verified provider")
    return checked_population, evidence


def _select_from_checked(
    population: VerifiedAuditPopulationV1,
    evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> tuple[AuditSampleManifestV1, BlindAuditPacketV1]:
    design = _compute_sampling_design(
        population.records,
        campaign_seed=evidence.index.campaign_seed,
        input_tag_commit=evidence.index.input_tag_commit,
        judge_protocol_sha256=evidence.index.judge_protocol_sha256,
        target=_target_for_certainty_count(sum(_is_certainty(row) for row in population.records)),
    )
    if len(design.ordered_selected_record_ids) != design.target:
        raise ValueError("audit population cannot satisfy the frozen sample target")
    manifest_payload: dict[str, object] = {
        "schema_version": "audit-sample-manifest-v1",
        "campaign_id": evidence.index.campaign_id,
        "protocol_bindings": evidence.projection.protocol_bindings,
        "population_attachment_sha256": population.attachment.population_attachment_sha256,
        "target": design.target,
        "total_certainty_count": len(design.certainty_record_ids),
        "certainty_record_ids": design.certainty_record_ids,
        "stratum_quotas": design.stratum_quotas,
        "cells": design.cells,
        "ordered_selected_record_ids": design.ordered_selected_record_ids,
    }
    manifest_digest_payload = {
        **manifest_payload,
        "protocol_bindings": evidence.projection.protocol_bindings.model_dump(mode="json"),
        "cells": [row.model_dump(mode="json") for row in design.cells],
    }
    manifest_payload["sample_manifest_sha256"] = stable_digest(
        "laconian-audit-sample-manifest-v1", manifest_digest_payload
    )
    manifest = AuditSampleManifestV1.model_validate(manifest_payload)
    by_id = {row.canonical_record_id: row for row in population.records}
    blind_records = tuple(
        sorted(
            (
                BlindAuditRecordV1(
                    audit_record_id=stable_digest(
                        "laconian-blind-audit-record-id-v1",
                        {
                            "campaign_id": manifest.campaign_id,
                            "sample_manifest_sha256": manifest.sample_manifest_sha256,
                            "canonical_record_id": canonical_id,
                        },
                    ),
                    prompt=by_id[canonical_id].prompt,
                    rubric=by_id[canonical_id].rubric,
                    material_warning_requirement=(by_id[canonical_id].material_warning_requirement),
                    warning_severity=by_id[canonical_id].warning_severity,
                    locale=by_id[canonical_id].locale,
                    candidate_response=by_id[canonical_id].candidate_response,
                )
                for canonical_id in manifest.ordered_selected_record_ids
            ),
            key=lambda row: row.audit_record_id.encode("utf-8"),
        )
    )
    packet_payload: dict[str, object] = {
        "campaign_registry_sha256": evidence.generation_context.index.campaign_registry_sha256,
        "sample_manifest_sha256": manifest.sample_manifest_sha256,
        "records": blind_records,
    }
    packet_digest_payload = {
        **packet_payload,
        "records": [row.model_dump(mode="json") for row in blind_records],
    }
    packet_payload["packet_sha256"] = stable_digest(
        "laconian-blind-audit-packet-v1", packet_digest_payload
    )
    return manifest, BlindAuditPacketV1.model_validate(packet_payload)


def select_audit_sample(
    *,
    population: VerifiedAuditPopulationV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> tuple[AuditSampleManifestV1, BlindAuditPacketV1]:
    """Apply certainty, exact Hamilton, frozen cell permutations, and global fill."""

    checked_population, evidence = _population_and_provider(population, provider_evidence)
    return _select_from_checked(checked_population, evidence)


def _verify_audit_sample_from_checked(
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
    *,
    population: VerifiedAuditPopulationV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> None:
    checked_manifest = cast(
        AuditSampleManifestV1,
        _revalidate_model(AuditSampleManifestV1, manifest),
    )
    checked_packet = cast(
        BlindAuditPacketV1,
        _revalidate_model(BlindAuditPacketV1, packet),
    )
    expected_manifest, expected_packet = _select_from_checked(population, provider_evidence)
    registry = provider_evidence.generation_context.index.campaign_registry_sha256
    if (
        checked_packet.campaign_registry_sha256 != registry
        or checked_packet.campaign_registry_sha256
        != checked_manifest.protocol_bindings.campaign_registry_sha256
        or canonical_json_v1(checked_manifest.model_dump(mode="json"))
        != canonical_json_v1(expected_manifest.model_dump(mode="json"))
        or canonical_json_v1(checked_packet.model_dump(mode="json"))
        != canonical_json_v1(expected_packet.model_dump(mode="json"))
    ):
        raise ValueError("audit sample does not replay from the verified population")


def verify_audit_sample(
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
    *,
    population: VerifiedAuditPopulationV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> None:
    """Recompute the complete design and compare canonical bytes, not selected IDs alone."""

    checked_population, evidence = _population_and_provider(population, provider_evidence)
    _verify_audit_sample_from_checked(
        manifest,
        packet,
        population=checked_population,
        provider_evidence=evidence,
    )


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short audit sample write")
        view = view[written:]


def _write_sample_member(directory_fd: int, name: str, data: bytes) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


_FileIdentity = tuple[int, int, int, int, int, int, int]


def _file_identity(metadata: os.stat_result) -> _FileIdentity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_member(directory_fd: int, name: str) -> tuple[bytes, _FileIdentity]:
    limit = _AUDIT_SAMPLE_MEMBER_MAX_BYTES[name]
    try:
        visible = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise ValueError("audit sample member is missing or unsafe") from error
    expected = _file_identity(visible)
    if not stat.S_ISREG(visible.st_mode) or visible.st_nlink != 1 or visible.st_size > limit:
        raise ValueError("audit sample member is not one bounded regular file")
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
        dir_fd=directory_fd,
    )
    try:
        before = os.fstat(descriptor)
        if _file_identity(before) != expected:
            raise ValueError("audit sample member is not a unique regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1 << 20, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError("audit sample member exceeds its byte limit")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        try:
            visible_after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as error:
            raise ValueError("audit sample member changed while reading") from error
        if _file_identity(after) != expected or _file_identity(visible_after) != expected:
            raise ValueError("audit sample member changed while reading")
        return b"".join(chunks), expected
    finally:
        os.close(descriptor)


def _canonical_model_from_member(
    directory_fd: int,
    name: str,
    model_type: type[BaseModel],
) -> tuple[BaseModel, _FileIdentity]:
    raw, identity = _read_member(directory_fd, name)
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ValueError("audit sample member requires exactly one final LF")
    parsed = parse_canonical_json_v1(raw[:-1])
    if not isinstance(parsed, dict):
        raise ValueError("audit sample member must be a canonical object")
    return model_type.model_validate_json(raw[:-1]), identity


def _audit_sample_root_digest(
    population: VerifiedAuditPopulationV1,
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
) -> str:
    return stable_digest(
        "laconian-audit-sample-root-v1",
        {
            "population_attachment_sha256": population.attachment.population_attachment_sha256,
            "records_sha256": population.attachment.records_sha256,
            "sample_manifest_sha256": manifest.sample_manifest_sha256,
            "blind_packet_sha256": packet.packet_sha256,
        },
    )


def load_verified_audit_sample_root(
    root: Path,
    *,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditSampleRootV1:
    """Reload exactly four sample members and rederive population, design, and root digest."""

    evidence = _revalidate_verified_provider_evidence_v1(provider_evidence)
    root_name = root.name
    if root.parent / root_name != root or root_name in {"", ".", ".."}:
        raise ValueError("audit sample root must be one safe parent child")
    parent_fd = open_directory_no_follow(root.parent)
    try:
        try:
            visible_root = os.stat(root_name, dir_fd=parent_fd, follow_symlinks=False)
            root_fd = os.open(
                root_name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except OSError as error:
            raise ValueError("audit sample root is missing or unsafe") from error
        try:
            root_identity = _file_identity(os.fstat(root_fd))
            if root_identity != _file_identity(visible_root) or not stat.S_ISDIR(
                visible_root.st_mode
            ):
                raise ValueError("audit sample root identity changed while opening")
            with os.scandir(root_fd) as entries:
                if {entry.name for entry in entries} != {"audit"}:
                    raise ValueError("audit sample root allowlist mismatch")
            try:
                visible_audit = os.stat(
                    "audit",
                    dir_fd=root_fd,
                    follow_symlinks=False,
                )
                audit_fd = os.open(
                    "audit",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=root_fd,
                )
            except OSError as error:
                raise ValueError("audit sample directory is missing or unsafe") from error
            try:
                audit_identity = _file_identity(os.fstat(audit_fd))
                if audit_identity != _file_identity(visible_audit) or not stat.S_ISDIR(
                    visible_audit.st_mode
                ):
                    raise ValueError("audit sample directory identity changed while opening")
                expected_names = set(_AUDIT_SAMPLE_MEMBER_MAX_BYTES)
                with os.scandir(audit_fd) as entries:
                    if {entry.name for entry in entries} != expected_names:
                        raise ValueError("audit sample member allowlist mismatch")
                member_snapshots = {name: _read_member(audit_fd, name) for name in expected_names}
                if len(
                    {(identity[0], identity[1]) for _, identity in member_snapshots.values()}
                ) != len(expected_names):
                    raise ValueError("audit sample members alias one another")
                raw_population_attachment = member_snapshots["population-attachment.json"][0]
                raw_population_records = member_snapshots["population.jsonl"][0]
                manifest_model, _ = _canonical_model_from_member(
                    audit_fd,
                    "sample-manifest.json",
                    AuditSampleManifestV1,
                )
                packet_model, _ = _canonical_model_from_member(
                    audit_fd,
                    "blind-packet.json",
                    BlindAuditPacketV1,
                )
                population = _load_verified_audit_population_from_bytes(
                    attachment_raw=raw_population_attachment,
                    records_raw=raw_population_records,
                    provider_evidence=evidence,
                )
                manifest = cast(AuditSampleManifestV1, manifest_model)
                packet = cast(BlindAuditPacketV1, packet_model)
                _verify_audit_sample_from_checked(
                    manifest,
                    packet,
                    population=population,
                    provider_evidence=evidence,
                )
                with os.scandir(audit_fd) as entries:
                    if {entry.name for entry in entries} != expected_names:
                        raise ValueError("audit sample member allowlist changed while loading")
                for name, expected_snapshot in member_snapshots.items():
                    if _read_member(audit_fd, name) != expected_snapshot:
                        raise ValueError("audit sample member changed while loading")
                if (
                    _file_identity(os.fstat(audit_fd)) != audit_identity
                    or _file_identity(os.stat("audit", dir_fd=root_fd, follow_symlinks=False))
                    != audit_identity
                ):
                    raise ValueError("audit sample directory changed while loading")
            finally:
                os.close(audit_fd)
            if (
                _file_identity(os.fstat(root_fd)) != root_identity
                or _file_identity(os.stat(root_name, dir_fd=parent_fd, follow_symlinks=False))
                != root_identity
            ):
                raise ValueError("audit sample root changed while loading")
            return VerifiedAuditSampleRootV1(
                population=population,
                manifest=manifest,
                packet=packet,
                audit_sample_root_sha256=_audit_sample_root_digest(
                    population,
                    manifest,
                    packet,
                ),
            )
        finally:
            os.close(root_fd)
    finally:
        os.close(parent_fd)


@dataclass(frozen=True, slots=True)
class _SampleTreeWitness:
    root_identity: tuple[int, int]
    audit_identity: _FileIdentity
    member_identities: Mapping[str, _FileIdentity]


def _validate_staged_sample_tree(
    root_fd: int,
    *,
    population: VerifiedAuditPopulationV1,
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
) -> _SampleTreeWitness:
    with os.scandir(root_fd) as entries:
        if {entry.name for entry in entries} != {"audit"}:
            raise ValueError("staged audit root allowlist mismatch")
    visible_audit = os.stat("audit", dir_fd=root_fd, follow_symlinks=False)
    audit_fd = os.open(
        "audit",
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=root_fd,
    )
    try:
        audit_identity = _file_identity(os.fstat(audit_fd))
        if audit_identity != _file_identity(visible_audit):
            raise ValueError("staged audit directory changed while opening")
        with os.scandir(audit_fd) as entries:
            if {entry.name for entry in entries} != set(_AUDIT_SAMPLE_MEMBER_MAX_BYTES):
                raise ValueError("staged audit member allowlist mismatch")
        expected = {
            "population-attachment.json": canonical_json_v1(
                population.attachment.model_dump(mode="json")
            )
            + b"\n",
            "population.jsonl": _canonical_population_jsonl(population.records),
            "sample-manifest.json": canonical_json_v1(manifest.model_dump(mode="json")) + b"\n",
            "blind-packet.json": canonical_json_v1(packet.model_dump(mode="json")) + b"\n",
        }
        snapshots = {
            name: _read_member(audit_fd, name) for name in sorted(expected, key=str.encode)
        }
        if any(snapshots[name][0] != raw for name, raw in expected.items()):
            raise ValueError("staged audit member bytes differ from verified arguments")
        if len({(identity[0], identity[1]) for _, identity in snapshots.values()}) != 4:
            raise ValueError("staged audit members alias one another")
        AuditPopulationAttachmentV1.model_validate_json(
            snapshots["population-attachment.json"][0][:-1]
        )
        for line in snapshots["population.jsonl"][0].splitlines():
            AuditPopulationRecordV1.model_validate_json(line)
        AuditSampleManifestV1.model_validate_json(snapshots["sample-manifest.json"][0][:-1])
        BlindAuditPacketV1.model_validate_json(snapshots["blind-packet.json"][0][:-1])
        if (
            _file_identity(os.fstat(audit_fd)) != audit_identity
            or _file_identity(os.stat("audit", dir_fd=root_fd, follow_symlinks=False))
            != audit_identity
        ):
            raise ValueError("staged audit directory changed while validating")
        root_stat = os.fstat(root_fd)
        return _SampleTreeWitness(
            root_identity=(root_stat.st_dev, root_stat.st_ino),
            audit_identity=audit_identity,
            member_identities={name: identity for name, (_, identity) in snapshots.items()},
        )
    finally:
        os.close(audit_fd)


def _remove_published_sample(
    parent_fd: int,
    destination_name: str,
    root_fd: int,
    witness: _SampleTreeWitness,
    *,
    posix: FilesystemPosixOps,
) -> None:
    """Remove only the just-published fixed tree when its identity is unchanged."""

    visible = os.stat(destination_name, dir_fd=parent_fd, follow_symlinks=False)
    if (visible.st_dev, visible.st_ino) != witness.root_identity or (
        os.fstat(root_fd).st_dev,
        os.fstat(root_fd).st_ino,
    ) != witness.root_identity:
        raise ValueError("published audit root identity changed before rollback")
    quarantine = f".laconian-rollback.{uuid4()}"
    posix.rename_noreplace(
        parent_fd,
        destination_name,
        parent_fd,
        quarantine,
    )
    try:
        quarantined = os.stat(quarantine, dir_fd=parent_fd, follow_symlinks=False)
        if (quarantined.st_dev, quarantined.st_ino) != witness.root_identity:
            raise ValueError("published audit root identity changed before rollback")
        audit_fd = os.open(
            "audit",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=root_fd,
        )
        try:
            with os.scandir(audit_fd) as entries:
                names = {entry.name for entry in entries}
            if (
                names != set(witness.member_identities)
                or _file_identity(os.fstat(audit_fd)) != witness.audit_identity
                or _file_identity(os.stat("audit", dir_fd=root_fd, follow_symlinks=False))
                != witness.audit_identity
            ):
                raise ValueError("published audit root changed before rollback")
            for name in sorted(witness.member_identities, key=str.encode):
                visible_member = os.stat(
                    name,
                    dir_fd=audit_fd,
                    follow_symlinks=False,
                )
                if _file_identity(visible_member) != witness.member_identities[name]:
                    raise ValueError("published audit member changed before rollback")
                os.unlink(name, dir_fd=audit_fd)
            os.fsync(audit_fd)
        finally:
            os.close(audit_fd)
        os.rmdir("audit", dir_fd=root_fd)
        os.fsync(root_fd)
        os.rmdir(quarantine, dir_fd=parent_fd)
    except BaseException:
        with suppress(BaseException):
            posix.rename_noreplace(parent_fd, quarantine, parent_fd, destination_name)
        raise
    os.fsync(parent_fd)


def write_audit_sample_root(
    output_root: Path,
    *,
    population: VerifiedAuditPopulationV1,
    manifest: AuditSampleManifestV1,
    packet: BlindAuditPacketV1,
    provider_evidence: VerifiedBenchmarkProviderEvidenceV1,
) -> VerifiedAuditSampleRootV1:
    """Atomically write and fresh-reload the fixed four-member audit-sample root."""

    checked_population, evidence = _population_and_provider(population, provider_evidence)
    checked_manifest = cast(
        AuditSampleManifestV1,
        _revalidate_model(AuditSampleManifestV1, manifest),
    )
    checked_packet = cast(
        BlindAuditPacketV1,
        _revalidate_model(BlindAuditPacketV1, packet),
    )
    registry = evidence.generation_context.index.campaign_registry_sha256
    if (
        checked_packet.campaign_registry_sha256 != registry
        or checked_packet.campaign_registry_sha256
        != checked_manifest.protocol_bindings.campaign_registry_sha256
    ):
        raise ValueError("blind packet campaign registry does not match provider authority")
    _verify_audit_sample_from_checked(
        checked_manifest,
        checked_packet,
        population=checked_population,
        provider_evidence=evidence,
    )
    destination_name = output_root.name
    if (
        output_root.parent / destination_name != output_root
        or destination_name in {"", ".", ".."}
        or "/" in destination_name
    ):
        raise ValueError("audit sample output must be one safe parent child")
    parent_fd = open_directory_no_follow(output_root.parent)
    posix = cast(FilesystemPosixOps, PosixOps())
    staging = create_owned_staging(parent_fd, uuid4())
    published = False
    witness: _SampleTreeWitness | None = None
    try:
        os.mkdir("audit", 0o700, dir_fd=staging.descriptor)
        audit_fd = os.open(
            "audit",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=staging.descriptor,
        )
        try:
            _write_sample_member(
                audit_fd,
                "population-attachment.json",
                canonical_json_v1(checked_population.attachment.model_dump(mode="json")) + b"\n",
            )
            _write_sample_member(
                audit_fd,
                "population.jsonl",
                _canonical_population_jsonl(checked_population.records),
            )
            _write_sample_member(
                audit_fd,
                "sample-manifest.json",
                canonical_json_v1(checked_manifest.model_dump(mode="json")) + b"\n",
            )
            _write_sample_member(
                audit_fd,
                "blind-packet.json",
                canonical_json_v1(checked_packet.model_dump(mode="json")) + b"\n",
            )
            os.fsync(audit_fd)
        finally:
            os.close(audit_fd)
        os.fsync(staging.descriptor)
        witness = _validate_staged_sample_tree(
            staging.descriptor,
            population=checked_population,
            manifest=checked_manifest,
            packet=checked_packet,
        )
        try:
            publish_owned_staging(staging, destination_name, posix=posix)
        except DestinationCollisionError:
            raise FileExistsError("audit sample destination already exists") from None
        except BaseException as error:
            if staging.state == "published" and witness is not None:
                try:
                    _remove_published_sample(
                        parent_fd,
                        destination_name,
                        staging.descriptor,
                        witness,
                        posix=posix,
                    )
                except BaseException as rollback_error:
                    error.add_note(f"audit sample rollback failed: {rollback_error}")
            raise
        published = True
        try:
            return load_verified_audit_sample_root(output_root, provider_evidence=evidence)
        except BaseException as error:
            assert witness is not None
            try:
                _remove_published_sample(
                    parent_fd,
                    destination_name,
                    staging.descriptor,
                    witness,
                    posix=posix,
                )
                published = False
            except BaseException as rollback_error:
                error.add_note(f"audit sample rollback failed: {rollback_error}")
            raise
    except BaseException:
        if not published and staging.state == "owned":
            cleanup_owned_staging(staging, posix=posix)
        raise
    finally:
        if staging.state == "published":
            staging.close()
        os.close(parent_fd)


__all__ = (
    "AuditSampleManifestV1",
    "BlindAuditPacketV1",
    "BlindAuditRecordV1",
    "CellAllocationV1",
    "VerifiedAuditSampleRootV1",
    "load_verified_audit_sample_root",
    "select_audit_sample",
    "verify_audit_sample",
    "write_audit_sample_root",
)
