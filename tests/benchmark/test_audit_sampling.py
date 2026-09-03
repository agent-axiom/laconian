"""Behavioral tests for the frozen human-audit population and sample root."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

import laconian_eval.benchmark as benchmark_package
import laconian_eval.benchmark.audit_sampling as audit_module
import laconian_eval.benchmark.provider_evidence as provider_module
from laconian_eval.benchmark.attachments import RationalV1, canonical_json_v1
from laconian_eval.benchmark.audit_sampling import (
    AuditSampleManifestV1,
    BlindAuditPacketV1,
    BlindAuditRecordV1,
    VerifiedAuditSampleRootV1,
    _compute_sampling_design,
    _target_for_certainty_count,
    load_verified_audit_sample_root,
    select_audit_sample,
    verify_audit_sample,
    write_audit_sample_root,
)
from laconian_eval.benchmark.context import BenchmarkProtocolBindingsV1
from laconian_eval.benchmark.judge import RubricItemV1
from laconian_eval.benchmark.provider_evidence import (
    AuditPopulationAttachmentV1,
    AuditPopulationRecordV1,
    VerifiedAuditPopulationV1,
    build_audit_population,
    load_verified_audit_population,
    write_audit_population,
)
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.capsule.filesystem import PostPublishSyncError
from tests.benchmark.helpers import (
    CompleteProviderEvidenceFixture,
    get_cached_complete_provider_evidence_fixture,
    sha256_marker,
)


@pytest.fixture(scope="module")
def provider_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> CompleteProviderEvidenceFixture:
    return get_cached_complete_provider_evidence_fixture(tmp_path_factory)


def _provider(fixture: CompleteProviderEvidenceFixture) -> Any:
    assert fixture.provider_evidence is not None
    return fixture.provider_evidence


@pytest.fixture(scope="module")
def population(
    provider_fixture: CompleteProviderEvidenceFixture,
) -> VerifiedAuditPopulationV1:
    return build_audit_population(provider_evidence=_provider(provider_fixture))


def _population_jsonl(records: tuple[AuditPopulationRecordV1, ...]) -> bytes:
    rows = sorted(canonical_json_v1(row.model_dump(mode="json")) for row in records)
    return b"".join(row + b"\n" for row in rows)


def _population_attachment_digest(payload: dict[str, Any]) -> str:
    return stable_digest(
        "laconian-audit-population-attachment-v1",
        {key: value for key, value in payload.items() if key != "population_attachment_sha256"},
    )


def _manifest_with_digest(payload: dict[str, Any]) -> AuditSampleManifestV1:
    payload["sample_manifest_sha256"] = stable_digest(
        "laconian-audit-sample-manifest-v1",
        {key: value for key, value in payload.items() if key != "sample_manifest_sha256"},
    )
    return AuditSampleManifestV1.model_validate_json(canonical_json_v1(payload))


def _packet_for_manifest(
    manifest: AuditSampleManifestV1,
    records: tuple[AuditPopulationRecordV1, ...],
) -> BlindAuditPacketV1:
    by_id = {row.canonical_record_id: row for row in records}
    blind: list[dict[str, Any]] = []
    for canonical_id in manifest.ordered_selected_record_ids:
        source = by_id[canonical_id]
        blind.append(
            {
                "audit_record_id": stable_digest(
                    "laconian-blind-audit-record-id-v1",
                    {
                        "campaign_id": manifest.campaign_id,
                        "sample_manifest_sha256": manifest.sample_manifest_sha256,
                        "canonical_record_id": canonical_id,
                    },
                ),
                "prompt": source.prompt,
                "rubric": [item.model_dump(mode="json") for item in source.rubric],
                "material_warning_requirement": source.material_warning_requirement,
                "warning_severity": source.warning_severity,
                "locale": source.locale,
                "candidate_response": source.candidate_response,
            }
        )
    blind.sort(key=lambda row: row["audit_record_id"].encode("utf-8"))
    payload: dict[str, Any] = {
        "campaign_registry_sha256": manifest.protocol_bindings.campaign_registry_sha256,
        "sample_manifest_sha256": manifest.sample_manifest_sha256,
        "records": blind,
    }
    payload["packet_sha256"] = stable_digest("laconian-blind-audit-packet-v1", payload)
    return BlindAuditPacketV1.model_validate_json(canonical_json_v1(payload))


def _synthetic_record(
    ordinal: int,
    *,
    model: str,
    locale: str,
    arm: str,
    decision: bool,
    case_id: str = "direct-answer-en",
) -> AuditPopulationRecordV1:
    marker = sha256_marker(800_000 + ordinal)
    return AuditPopulationRecordV1(
        canonical_record_id=marker,
        generation_capsule_sha256=sha256_marker(810_000 + ordinal),
        hard_score_request_set_sha256=sha256_marker(820_000 + ordinal),
        judge_request_attachment_sha256=sha256_marker(830_000 + ordinal),
        judge_attachment_sha256=sha256_marker(840_000 + ordinal),
        plan_item_id=sha256_marker(850_000 + ordinal),
        response_id=sha256_marker(860_000 + ordinal),
        judge_request_id=sha256_marker(870_000 + ordinal),
        generation_model=model,
        scenario_uid=sha256_marker(880_000 + ordinal),
        locale=locale,
        repetition=ordinal % 5,
        arm=arm,
        blinded_judge_decision=decision,
        case_id=case_id.replace("-en", f"-{locale}"),
        case_category="safety" if case_id.startswith("safety") else "direct",
        warning_severity=None,
        prompt=f"Prompt {ordinal}",
        rubric=(),
        material_warning_requirement=None,
        candidate_response=f"Candidate {ordinal}",
    )


def _golden_records() -> tuple[AuditPopulationRecordV1, ...]:
    rows: list[AuditPopulationRecordV1] = []
    ordinal = 0

    def add(count: int, **kwargs: Any) -> None:
        nonlocal ordinal
        for _ in range(count):
            rows.append(_synthetic_record(ordinal, **kwargs))
            ordinal += 1

    add(30, model="gpt-5.6-luna", locale="en", arm="baseline", decision=False)
    add(30, model="gpt-5.6-luna", locale="en", arm="baseline", decision=True)
    add(
        5,
        model="gpt-5.6-luna",
        locale="en",
        arm="if",
        decision=True,
        case_id="safety-medical-en",
    )
    add(1, model="gpt-5.6-luna", locale="en", arm="if", decision=False)
    add(54, model="gpt-5.6-luna", locale="en", arm="if", decision=True)
    add(
        3,
        model="gpt-5.6-sol",
        locale="ru",
        arm="concise",
        decision=True,
        case_id="safety-medical-en",
    )
    add(2, model="gpt-5.6-sol", locale="ru", arm="concise", decision=False)
    add(2, model="gpt-5.6-sol", locale="ru", arm="concise", decision=True)
    add(1, model="gpt-5.6-terra", locale="ru", arm="baseline", decision=False)
    add(60, model="gpt-5.6-terra", locale="en", arm="caveman", decision=True)
    return tuple(rows)


def test_audit_population_is_a_bijection_over_verified_judged_records(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
) -> None:
    evidence = _provider(provider_fixture)
    expected: set[str] = set()
    for capsule, hard_set, requests, judgments in zip(
        evidence.generation_evidence,
        evidence.hard_score_request_sets,
        evidence.judge_request_attachments,
        evidence.judge_attachments,
        strict=True,
    ):
        plan = {row.plan_item_id: row for row in capsule.plan}
        request_ids = {row.blind_request.judge_request_id for row in requests.requests}
        judgment_ids = {row.judge_request_id for row in judgments.records}
        for hard in hard_set.records:
            if not hard.hard_pass:
                continue
            assert hard.judge_request_id in request_ids & judgment_ids
            expected.add(
                stable_digest(
                    "laconian-audit-population-record-id-v1",
                    {
                        "campaign_id": evidence.index.campaign_id,
                        "generation_capsule_sha256": capsule.capsule_sha256,
                        "hard_score_request_set_sha256": hard_set.hard_score_request_set_sha256,
                        "judge_request_attachment_sha256": requests.judge_request_attachment_sha256,
                        "judge_attachment_sha256": judgments.judge_attachment_sha256,
                        "plan_item_id": plan[hard.plan_item_id].plan_item_id,
                        "response_id": hard.response_id,
                        "judge_request_id": hard.judge_request_id,
                    },
                )
            )
    assert len(population.records) == len(expected) == 1_440
    assert {row.canonical_record_id for row in population.records} == expected
    assert population.records == tuple(
        sorted(population.records, key=lambda row: canonical_json_v1(row.model_dump(mode="json")))
    )


def test_audit_population_attachment_binds_every_provider_evidence_parent(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
) -> None:
    evidence = _provider(provider_fixture)
    attachment = population.attachment
    assert (
        attachment.provider_evidence_index_sha256,
        attachment.benchmark_provider_evidence_sha256,
        attachment.judge_attempt_root_index_sha256,
    ) == (
        evidence.index.provider_evidence_index_sha256,
        evidence.projection.benchmark_provider_evidence_sha256,
        evidence.index.judge_attempt_root_index_sha256,
    )
    assert (
        attachment.ordered_generation_capsule_sha256s
        == evidence.index.ordered_generation_capsule_sha256s
    )
    assert (
        attachment.ordered_hard_score_request_set_sha256s
        == evidence.index.ordered_hard_score_request_set_sha256s
    )
    assert (
        attachment.ordered_judge_request_attachment_sha256s
        == evidence.index.ordered_judge_request_attachment_sha256s
    )
    assert (
        attachment.ordered_judge_attempt_boundary_sha256s
        == evidence.index.ordered_judge_attempt_boundary_sha256s
    )
    assert (
        attachment.ordered_judge_attachment_sha256s
        == evidence.index.ordered_judge_attachment_sha256s
    )
    assert (
        attachment.records_sha256
        == hashlib.sha256(_population_jsonl(population.records)).hexdigest()
    )
    assert attachment.population_attachment_sha256 == _population_attachment_digest(
        attachment.model_dump(mode="json")
    )
    serialized = canonical_json_v1(attachment.model_dump(mode="json"))
    assert b"identity_registry_bundle" not in serialized
    assert b"relative_path" not in serialized

    class ForeignProtocolBindings(BenchmarkProtocolBindingsV1):
        pass

    foreign_bindings = ForeignProtocolBindings.model_validate(
        attachment.protocol_bindings.model_dump(mode="python", round_trip=True)
    )
    attachment_payload = attachment.model_dump(mode="python", round_trip=True)
    attachment_payload["protocol_bindings"] = foreign_bindings
    with pytest.raises((TypeError, ValueError)):
        AuditPopulationAttachmentV1.model_validate(attachment_payload)

    record = next(row for row in population.records if row.rubric)

    class ForeignRubricItem(RubricItemV1):
        pass

    foreign_rubric = ForeignRubricItem.model_validate(
        record.rubric[0].model_dump(mode="python", round_trip=True)
    )
    record_payload = record.model_dump(mode="python", round_trip=True)
    record_payload["rubric"] = (foreign_rubric, *record.rubric[1:])
    with pytest.raises((TypeError, ValueError)):
        AuditPopulationRecordV1.model_validate(record_payload)


def test_audit_population_parents_require_exact_36_unique_index_aligned_chains(
    population: VerifiedAuditPopulationV1,
) -> None:
    base = population.attachment.model_dump(mode="json")
    field = "ordered_judge_attachment_sha256s"
    for vector in (
        base[field][:-1],
        [*base[field], sha256_marker(999_001)],
        [*base[field][:-1], base[field][0]],
    ):
        payload = dict(base)
        payload[field] = vector
        payload["population_attachment_sha256"] = _population_attachment_digest(payload)
        with pytest.raises(ValidationError):
            AuditPopulationAttachmentV1.model_validate_json(canonical_json_v1(payload))
    for vector in (list(reversed(base[field])), [sha256_marker(999_002), *base[field][1:]]):
        payload = dict(base)
        payload[field] = vector
        payload["population_attachment_sha256"] = _population_attachment_digest(payload)
        assert (
            AuditPopulationAttachmentV1.model_validate_json(canonical_json_v1(payload))
            != population.attachment
        )


def test_audit_population_reload_rejects_provider_projection_or_judge_parent_substitution(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
    tmp_path: Path,
) -> None:
    for field in (
        "benchmark_provider_evidence_sha256",
        "judge_attempt_root_index_sha256",
        "ordered_judge_attachment_sha256s",
    ):
        audit_root = tmp_path / field
        write_audit_population(audit_root, population)
        path = audit_root / "population-attachment.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if field.startswith("ordered_"):
            payload[field] = [sha256_marker(999_010), *payload[field][1:]]
        else:
            payload[field] = sha256_marker(999_011)
        payload["population_attachment_sha256"] = _population_attachment_digest(payload)
        path.write_bytes(canonical_json_v1(payload) + b"\n")
        with pytest.raises(ValueError):
            load_verified_audit_population(
                audit_root,
                provider_evidence=_provider(provider_fixture),
            )


def test_audit_population_writer_and_loader_use_the_same_exact_two_member_layout(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _provider(provider_fixture)
    audit_root = tmp_path / "population"
    write_audit_population(audit_root, population)
    assert {path.name for path in audit_root.iterdir()} == {
        "population-attachment.json",
        "population.jsonl",
    }
    assert (audit_root / "population-attachment.json").read_bytes() == (
        canonical_json_v1(population.attachment.model_dump(mode="json")) + b"\n"
    )
    assert (audit_root / "population.jsonl").read_bytes() == _population_jsonl(population.records)
    loaded = load_verified_audit_population(audit_root, provider_evidence=evidence)
    assert loaded is not population
    assert loaded.attachment == population.attachment and loaded.records == population.records
    assert provider_module._population_fingerprint(
        population.attachment, population.records
    ) == stable_digest(
        "laconian-verified-audit-population-full-content-v1",
        {
            "attachment": population.attachment.model_dump(mode="json"),
            "records": [record.model_dump(mode="json") for record in population.records],
        },
    )
    with pytest.raises(FileExistsError):
        write_audit_population(audit_root, population)
    with pytest.raises(TypeError):
        VerifiedAuditPopulationV1(population.attachment, population.records)
    with pytest.raises(TypeError):
        dataclasses.replace(population)
    forged = object.__new__(VerifiedAuditPopulationV1)
    object.__setattr__(forged, "attachment", population.attachment)
    object.__setattr__(forged, "records", population.records)
    with pytest.raises(TypeError):
        write_audit_population(tmp_path / "forged", forged)
    poisoned = load_verified_audit_population(audit_root, provider_evidence=evidence)
    object.__setattr__(poisoned, "records", poisoned.records[:-1])
    with pytest.raises(ValueError):
        write_audit_population(tmp_path / "poisoned", poisoned)

    oversized = tmp_path / "population-oversized"
    shutil.copytree(audit_root, oversized)
    oversized_records = oversized / "population.jsonl"
    oversized_records.unlink()
    with oversized_records.open("xb") as descriptor:
        descriptor.truncate(provider_module._AUDIT_POPULATION_JSONL_MAX_BYTES + 1)
    with pytest.raises(ValueError):
        load_verified_audit_population(oversized, provider_evidence=evidence)

    raced = tmp_path / "population-race"
    shutil.copytree(audit_root, raced)
    real_snapshot = provider_module._stable_regular_file_snapshot
    replaced = False

    def replace_records_after_snapshot(root_fd: int, relative_path: str) -> Any:
        nonlocal replaced
        result = real_snapshot(root_fd, relative_path)
        if relative_path == "population.jsonl" and not replaced:
            replaced = True
            target = raced / "population.jsonl"
            replacement = raced / "replacement.tmp"
            replacement.write_bytes(target.read_bytes())
            os.replace(replacement, target)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(
            provider_module,
            "_stable_regular_file_snapshot",
            replace_records_after_snapshot,
        )
        with pytest.raises(ValueError):
            load_verified_audit_population(raced, provider_evidence=evidence)
    assert replaced


def test_audit_sample_has_144_records_six_per_stratum_and_all_critical_certainty_units(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
) -> None:
    manifest, packet = select_audit_sample(
        population=population,
        provider_evidence=_provider(provider_fixture),
    )
    assert (
        manifest.target == len(manifest.ordered_selected_record_ids) == len(packet.records) == 144
    )
    selected = set(manifest.ordered_selected_record_ids)
    by_id = {row.canonical_record_id: row for row in population.records}
    strata: dict[tuple[str, str, str], int] = {}
    for record_id in selected:
        row = by_id[record_id]
        key = (row.generation_model, row.locale, row.arm)
        strata[key] = strata.get(key, 0) + 1
    assert len(strata) == 24 and set(strata.values()) == {6}
    certainty = {
        row.canonical_record_id
        for row in population.records
        if row.blinded_judge_decision
        and row.case_id in {"safety-medical-en", "safety-medical-ru"}
        and row.arm in {"if", "concise"}
    }
    assert tuple(sorted(certainty, key=str.encode)) == manifest.certainty_record_ids
    assert certainty <= selected
    assert manifest.sample_manifest_sha256 == stable_digest(
        "laconian-audit-sample-manifest-v1",
        manifest.model_dump(mode="json", exclude={"sample_manifest_sha256"}),
    )
    expected_audit_ids = tuple(
        sorted(
            (
                stable_digest(
                    "laconian-blind-audit-record-id-v1",
                    {
                        "campaign_id": manifest.campaign_id,
                        "sample_manifest_sha256": manifest.sample_manifest_sha256,
                        "canonical_record_id": canonical_id,
                    },
                )
                for canonical_id in manifest.ordered_selected_record_ids
            ),
            key=str.encode,
        )
    )
    assert tuple(row.audit_record_id for row in packet.records) == expected_audit_ids
    assert all(
        row.canonical_record_id not in certainty
        for row in population.records
        if row.case_category == "safety"
        and row.case_id not in {"safety-medical-en", "safety-medical-ru"}
    )


def test_hamilton_allocation_and_global_fill_match_golden_manifest() -> None:
    records = _golden_records()
    campaign_seed = sha256_marker(900_001)
    input_tag_commit = "1" * 40
    judge_protocol_sha256 = sha256_marker(900_002)
    design = _compute_sampling_design(
        records,
        campaign_seed=campaign_seed,
        input_tag_commit=input_tag_commit,
        judge_protocol_sha256=judge_protocol_sha256,
        target=144,
    )

    def canonical_id(
        model: str,
        locale: str,
        arm: str,
        decision: bool | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "generation_model": model,
            "locale": locale,
            "arm": arm,
        }
        if decision is not None:
            payload["blinded_judge_decision"] = decision
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    expected_quotas = {
        canonical_id(model, locale, arm): 0
        for model in ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra")
        for locale in ("en", "ru")
        for arm in ("baseline", "caveman", "if", "concise")
    }
    expected_quotas.update(
        {
            canonical_id("gpt-5.6-luna", "en", "baseline"): 6,
            canonical_id("gpt-5.6-luna", "en", "if"): 1,
            canonical_id("gpt-5.6-sol", "ru", "concise"): 3,
            canonical_id("gpt-5.6-terra", "ru", "baseline"): 1,
            canonical_id("gpt-5.6-terra", "en", "caveman"): 6,
        }
    )
    expected_quotas = {key: expected_quotas[key] for key in sorted(expected_quotas, key=str.encode)}
    assert len(expected_quotas) == 24
    assert design.stratum_quotas == expected_quotas

    luna_baseline_false = canonical_id("gpt-5.6-luna", "en", "baseline", False)
    luna_baseline_true = canonical_id("gpt-5.6-luna", "en", "baseline", True)
    luna_if_false = canonical_id("gpt-5.6-luna", "en", "if", False)
    luna_if_true = canonical_id("gpt-5.6-luna", "en", "if", True)
    sol_concise_false = canonical_id("gpt-5.6-sol", "ru", "concise", False)
    sol_concise_true = canonical_id("gpt-5.6-sol", "ru", "concise", True)
    terra_baseline_false = canonical_id("gpt-5.6-terra", "ru", "baseline", False)
    terra_caveman_true = canonical_id("gpt-5.6-terra", "en", "caveman", True)
    expected_allocations = {
        luna_baseline_false: (30, 1, 116, 58, 2, (0, 1), 1, tuple(range(1, 28)), 30, (1, 1)),
        luna_baseline_true: (30, 1, 116, 58, 2, (0, 1), 2, tuple(range(1, 28)), 30, (1, 1)),
        luna_if_false: (1, 0, 1, 55, 0, (1, 55), 2, (1,), 1, (1, 1)),
        luna_if_true: (54, 0, 54, 55, 0, (54, 55), 1, tuple(range(1, 32)), 32, (16, 27)),
        sol_concise_false: (2, 1, 1, 2, 0, (1, 2), 1, (), 2, (1, 1)),
        sol_concise_true: (2, 1, 1, 2, 0, (1, 2), 2, (1,), 2, (1, 1)),
        terra_baseline_false: (1, 1, 0, 1, 0, (0, 1), 1, (), 1, (1, 1)),
        terra_caveman_true: (60, 1, 295, 59, 5, (0, 1), 1, tuple(range(1, 33)), 38, (19, 30)),
    }
    cells = {row.cell_id: row for row in design.cells}
    assert tuple(cells) == tuple(sorted(expected_allocations, key=str.encode))
    for cell_id, expected in expected_allocations.items():
        cell = cells[cell_id]
        actual = (
            cell.noncertainty_population,
            cell.local_minimum,
            cell.proportional_numerator,
            cell.proportional_denominator,
            cell.floor_seats,
            (cell.fractional_remainder.numerator, cell.fractional_remainder.denominator),
            cell.residual_rank,
            cell.global_fill_passes,
            cell.selected_noncertainty,
            (cell.inclusion_probability.numerator, cell.inclusion_probability.denominator),
        )
        assert actual == expected

    certainty = tuple(
        sorted(
            (
                row.canonical_record_id
                for row in records
                if row.blinded_judge_decision
                and row.case_id in {"safety-medical-en", "safety-medical-ru"}
                and row.arm in {"if", "concise"}
            ),
            key=str.encode,
        )
    )
    independent_selected = set(certainty)
    for cell_id, cell in cells.items():
        source_ids = tuple(
            sorted(
                (
                    row.canonical_record_id
                    for row in records
                    if not (
                        row.blinded_judge_decision
                        and row.case_id in {"safety-medical-en", "safety-medical-ru"}
                        and row.arm in {"if", "concise"}
                    )
                    and canonical_id(
                        row.generation_model,
                        row.locale,
                        row.arm,
                        row.blinded_judge_decision,
                    )
                    == cell_id
                ),
                key=str.encode,
            )
        )
        material = b"\0".join(
            value.encode("utf-8")
            for value in (
                "laconian-human-audit-v1/cell/" + cell_id,
                campaign_seed,
                input_tag_commit,
                judge_protocol_sha256,
            )
        )
        expected_seed = int.from_bytes(hashlib.sha256(material).digest()[:16], "big")
        indexes = np.random.Generator(np.random.PCG64(expected_seed)).permutation(len(source_ids))
        expected_permutation = tuple(source_ids[int(index)] for index in indexes)
        assert cell.seed == expected_seed
        assert cell.permutation == expected_permutation
        independent_selected.update(expected_permutation[: cell.selected_noncertainty])
    assert design.target == 144
    assert design.certainty_record_ids == certainty
    assert len(certainty) == 8
    assert design.ordered_selected_record_ids == tuple(sorted(independent_selected, key=str.encode))
    assert len(design.ordered_selected_record_ids) == 144

    # A full higher-ranked cell retains its rank but cannot consume the residual
    # seat; the next available cell must receive it.
    local = {
        "a": audit_module._MutableCell(
            "a", ("a0",), 0, 0, 1, 0, Fraction(2, 3), None, 1, 0, ("a0",), []
        ),
        "b": audit_module._MutableCell(
            "b", ("b0", "b1"), 0, 0, 1, 0, Fraction(1, 3), None, 0, 0, ("b0", "b1"), []
        ),
    }
    audit_module._apply_local_residual_seats(local, ("a", "b"), remaining=1)
    assert local["a"].residual_rank == 1 and local["a"].selected == 1
    assert local["b"].residual_rank == 2 and local["b"].selected == 1

    # Exercise the exact global-fill helper with cells that are already full and one
    # that becomes full in pass 1; byte order and the second pass decide the result.
    synthetic = {
        "c": audit_module._MutableCell(
            "c", ("c0", "c1"), 0, 0, 1, 0, Fraction(0), None, 1, 0, ("c0", "c1"), []
        ),
        "a": audit_module._MutableCell(
            "a", ("a0",), 1, 0, 1, 0, Fraction(0), None, 1, 0, ("a0",), []
        ),
        "b": audit_module._MutableCell(
            "b", ("b0", "b1", "b2"), 0, 0, 1, 0, Fraction(0), None, 0, 0, ("b0", "b1", "b2"), []
        ),
    }
    assert (
        audit_module._apply_global_fill(
            synthetic,
            selected_total=2,
            target=5,
            population_size=6,
        )
        == 5
    )
    assert synthetic["a"].global_passes == []
    assert synthetic["b"].global_passes == [1, 2]
    assert synthetic["c"].global_passes == [1]


def test_certainty_overflow_expands_target_instead_of_subsampling() -> None:
    assert _target_for_certainty_count(0) == 144
    assert _target_for_certainty_count(144) == 144
    assert _target_for_certainty_count(145) == 145
    certainty_records = tuple(
        _synthetic_record(
            ordinal,
            model="gpt-5.6-sol",
            locale="en",
            arm="if",
            decision=True,
            case_id="safety-medical-en",
        )
        for ordinal in range(145)
    )
    design = _compute_sampling_design(
        certainty_records,
        campaign_seed=sha256_marker(900_010),
        input_tag_commit="2" * 40,
        judge_protocol_sha256=sha256_marker(900_011),
        target=_target_for_certainty_count(len(certainty_records)),
    )
    expected_ids = tuple(
        sorted((row.canonical_record_id for row in certainty_records), key=str.encode)
    )
    assert design.target == 145
    assert design.certainty_record_ids == expected_ids
    assert design.ordered_selected_record_ids == expected_ids


def test_blind_packet_omits_model_arm_judge_tokens_and_provider_metadata(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
) -> None:
    manifest, packet = select_audit_sample(
        population=population,
        provider_evidence=_provider(provider_fixture),
    )
    assert set(packet.model_dump(mode="json")) == {
        "campaign_registry_sha256",
        "sample_manifest_sha256",
        "records",
        "packet_sha256",
    }
    assert all(
        set(row.model_dump(mode="json"))
        == {
            "audit_record_id",
            "prompt",
            "rubric",
            "material_warning_requirement",
            "warning_severity",
            "locale",
            "candidate_response",
        }
        for row in packet.records
    )
    forbidden = {
        "ordinal",
        "order",
        "length",
        "generation_model",
        "model",
        "arm",
        "judge_decision",
        "blinded_judge_decision",
        "tokens",
        "latency",
        "cost",
        "provider",
        "provider_metadata",
    }
    assert all(forbidden.isdisjoint(row.model_dump(mode="json")) for row in packet.records)
    assert tuple(row.audit_record_id for row in packet.records) == tuple(
        sorted((row.audit_record_id for row in packet.records), key=str.encode)
    )
    assert packet.campaign_registry_sha256 == manifest.protocol_bindings.campaign_registry_sha256
    assert packet.packet_sha256 == stable_digest(
        "laconian-blind-audit-packet-v1",
        packet.model_dump(mode="json", exclude={"packet_sha256"}),
    )
    payload = packet.records[0].model_dump(mode="json")
    payload["generation_model"] = "gpt-5.6-sol"
    with pytest.raises(ValidationError):
        BlindAuditRecordV1.model_validate_json(canonical_json_v1(payload))

    class ForeignProtocolBindings(BenchmarkProtocolBindingsV1):
        pass

    foreign_bindings = ForeignProtocolBindings.model_validate(
        manifest.protocol_bindings.model_dump(mode="python", round_trip=True)
    )
    manifest_payload = manifest.model_dump(mode="python", round_trip=True)
    manifest_payload["protocol_bindings"] = foreign_bindings
    with pytest.raises((TypeError, ValueError)):
        AuditSampleManifestV1.model_validate(manifest_payload)

    class ForeignRational(RationalV1):
        pass

    for field in ("fractional_remainder", "inclusion_probability"):
        cell_payload = manifest.cells[0].model_dump(mode="python", round_trip=True)
        original = getattr(manifest.cells[0], field)
        cell_payload[field] = ForeignRational(
            numerator=original.numerator,
            denominator=original.denominator,
        )
        with pytest.raises((TypeError, ValueError)):
            audit_module.CellAllocationV1.model_validate(cell_payload)

    class ForeignCell(audit_module.CellAllocationV1):
        pass

    foreign_cell = ForeignCell.model_validate(
        manifest.cells[0].model_dump(mode="python", round_trip=True)
    )
    manifest_payload = manifest.model_dump(mode="python", round_trip=True)
    manifest_payload["cells"] = (foreign_cell, *manifest.cells[1:])
    with pytest.raises((TypeError, ValueError)):
        AuditSampleManifestV1.model_validate(manifest_payload)
    forged_manifest = manifest.model_copy(
        update={"cells": (foreign_cell, *manifest.cells[1:])}
    )
    with pytest.raises((TypeError, ValueError)):
        audit_module._revalidate_model(AuditSampleManifestV1, forged_manifest)

    rational = manifest.cells[0].fractional_remainder
    foreign_rational = ForeignRational(
        numerator=rational.numerator,
        denominator=rational.denominator,
    )
    rational_cell = manifest.cells[0].model_copy(
        update={"fractional_remainder": foreign_rational}
    )
    forged_rational_manifest = manifest.model_copy(
        update={"cells": (rational_cell, *manifest.cells[1:])}
    )
    with pytest.raises((TypeError, ValueError)):
        audit_module._revalidate_model(AuditSampleManifestV1, forged_rational_manifest)

    record = next(row for row in packet.records if row.rubric)

    class ForeignRubricItem(RubricItemV1):
        pass

    foreign_rubric = ForeignRubricItem.model_validate(
        record.rubric[0].model_dump(mode="python", round_trip=True)
    )
    record_payload = record.model_dump(mode="python", round_trip=True)
    record_payload["rubric"] = (foreign_rubric, *record.rubric[1:])
    with pytest.raises((TypeError, ValueError)):
        BlindAuditRecordV1.model_validate(record_payload)

    class ForeignBlindRecord(BlindAuditRecordV1):
        pass

    foreign_record = ForeignBlindRecord.model_validate(
        packet.records[0].model_dump(mode="python", round_trip=True)
    )
    packet_payload = packet.model_dump(mode="python", round_trip=True)
    packet_payload["records"] = (foreign_record, *packet.records[1:])
    with pytest.raises((TypeError, ValueError)):
        BlindAuditPacketV1.model_validate(packet_payload)
    forged_packet = packet.model_copy(
        update={"records": (foreign_record, *packet.records[1:])}
    )
    with pytest.raises((TypeError, ValueError)):
        audit_module._revalidate_model(BlindAuditPacketV1, forged_packet)

    rubric_record = record.model_copy(
        update={"rubric": (foreign_rubric, *record.rubric[1:])}
    )
    rubric_index = packet.records.index(record)
    forged_rubric_packet = packet.model_copy(
        update={
            "records": (
                *packet.records[:rubric_index],
                rubric_record,
                *packet.records[rubric_index + 1 :],
            )
        }
    )
    with pytest.raises((TypeError, ValueError)):
        audit_module._revalidate_model(BlindAuditPacketV1, forged_rubric_packet)


def test_audit_sample_root_writer_loader_round_trip_exact_four_member_layout(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
    tmp_path: Path,
) -> None:
    manifest, packet = select_audit_sample(
        population=population,
        provider_evidence=_provider(provider_fixture),
    )
    root = tmp_path / "sample-root"
    written = write_audit_sample_root(
        root,
        population=population,
        manifest=manifest,
        packet=packet,
        provider_evidence=_provider(provider_fixture),
    )
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    assert files == {
        "audit/population-attachment.json",
        "audit/population.jsonl",
        "audit/sample-manifest.json",
        "audit/blind-packet.json",
    }
    loaded = load_verified_audit_sample_root(root, provider_evidence=_provider(provider_fixture))
    assert loaded is not written
    assert loaded.population.attachment == population.attachment
    assert loaded.manifest == manifest and loaded.packet == packet
    assert loaded.audit_sample_root_sha256 == stable_digest(
        "laconian-audit-sample-root-v1",
        {
            "population_attachment_sha256": population.attachment.population_attachment_sha256,
            "records_sha256": population.attachment.records_sha256,
            "sample_manifest_sha256": manifest.sample_manifest_sha256,
            "blind_packet_sha256": packet.packet_sha256,
        },
    )
    assert benchmark_package.VerifiedAuditSampleRootV1 is VerifiedAuditSampleRootV1
    assert benchmark_package.write_audit_sample_root is write_audit_sample_root
    assert benchmark_package.load_verified_audit_sample_root is load_verified_audit_sample_root


def test_audit_sample_root_writer_is_failure_atomic_no_replace_and_fresh_reloads(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, packet = select_audit_sample(
        population=population,
        provider_evidence=_provider(provider_fixture),
    )
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_audit_sample_root(
            existing,
            population=population,
            manifest=manifest,
            packet=packet,
            provider_evidence=_provider(provider_fixture),
        )
    assert sentinel.read_text(encoding="utf-8") == "keep"

    failing = tmp_path / "failing"
    original_write = audit_module._write_sample_member
    calls = 0

    def fail_third(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected write failure")
        original_write(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "_write_sample_member", fail_third)
        with pytest.raises(OSError, match="injected"):
            write_audit_sample_root(
                failing,
                population=population,
                manifest=manifest,
                packet=packet,
                provider_evidence=_provider(provider_fixture),
            )
    assert not failing.exists()
    assert not any(path.name.startswith(".laconian-stage.") for path in tmp_path.iterdir())

    post_sync = tmp_path / "post-sync"
    real_posix_type = audit_module.PosixOps

    def fail_sync(_descriptor: int) -> None:
        raise OSError("injected parent sync failure")

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "PosixOps", lambda: real_posix_type(fsync_fn=fail_sync))
        with pytest.raises(PostPublishSyncError):
            write_audit_sample_root(
                post_sync,
                population=population,
                manifest=manifest,
                packet=packet,
                provider_evidence=_provider(provider_fixture),
            )
    assert not post_sync.exists()

    reload_failure = tmp_path / "reload-failure"

    def fail_reload(*_args: Any, **_kwargs: Any) -> VerifiedAuditSampleRootV1:
        raise RuntimeError("injected post-publish reload failure")

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "load_verified_audit_sample_root", fail_reload)
        with pytest.raises(RuntimeError, match="post-publish reload"):
            write_audit_sample_root(
                reload_failure,
                population=population,
                manifest=manifest,
                packet=packet,
                provider_evidence=_provider(provider_fixture),
            )
    assert not reload_failure.exists()

    swapped_member = tmp_path / "swapped-member"

    def swap_member_then_fail(
        root: Path,
        **_kwargs: Any,
    ) -> VerifiedAuditSampleRootV1:
        member = root / "audit/blind-packet.json"
        member.unlink()
        member.write_bytes(b"attacker replacement\n")
        raise RuntimeError("injected swapped-member reload failure")

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "load_verified_audit_sample_root", swap_member_then_fail)
        with pytest.raises(RuntimeError, match="swapped-member") as caught:
            write_audit_sample_root(
                swapped_member,
                population=population,
                manifest=manifest,
                packet=packet,
                provider_evidence=_provider(provider_fixture),
            )
    assert (swapped_member / "audit/blind-packet.json").read_bytes() == b"attacker replacement\n"
    assert any("rollback failed" in note for note in getattr(caught.value, "__notes__", ()))

    swapped_audit = tmp_path / "swapped-audit"

    def swap_audit_then_fail(
        root: Path,
        **_kwargs: Any,
    ) -> VerifiedAuditSampleRootV1:
        (root / "audit").rename(root / "owned-audit")
        (root / "audit").mkdir()
        (root / "audit/attacker").write_text("keep", encoding="utf-8")
        raise RuntimeError("injected swapped-audit reload failure")

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "load_verified_audit_sample_root", swap_audit_then_fail)
        with pytest.raises(RuntimeError, match="swapped-audit"):
            write_audit_sample_root(
                swapped_audit,
                population=population,
                manifest=manifest,
                packet=packet,
                provider_evidence=_provider(provider_fixture),
            )
    assert (swapped_audit / "audit/attacker").read_text(encoding="utf-8") == "keep"
    assert (swapped_audit / "owned-audit/blind-packet.json").is_file()

    successful = tmp_path / "successful"
    real_loader = audit_module.load_verified_audit_sample_root
    loads = 0

    def counted_loader(*args: Any, **kwargs: Any) -> VerifiedAuditSampleRootV1:
        nonlocal loads
        loads += 1
        return real_loader(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "load_verified_audit_sample_root", counted_loader)
        result = write_audit_sample_root(
            successful,
            population=population,
            manifest=manifest,
            packet=packet,
            provider_evidence=_provider(provider_fixture),
        )
    assert loads == 1 and result.population is not population


def test_audit_sample_root_loader_rejects_extra_missing_alias_or_parent_substitution(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _provider(provider_fixture)
    manifest, packet = select_audit_sample(
        population=population,
        provider_evidence=evidence,
    )
    baseline = tmp_path / "baseline"
    write_audit_sample_root(
        baseline,
        population=population,
        manifest=manifest,
        packet=packet,
        provider_evidence=evidence,
    )

    extra = tmp_path / "extra"
    shutil.copytree(baseline, extra)
    (extra / "audit/extra.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_verified_audit_sample_root(extra, provider_evidence=evidence)

    missing = tmp_path / "missing"
    shutil.copytree(baseline, missing)
    (missing / "audit/sample-manifest.json").unlink()
    with pytest.raises(ValueError):
        load_verified_audit_sample_root(missing, provider_evidence=evidence)

    alias = tmp_path / "alias"
    shutil.copytree(baseline, alias)
    packet_path = alias / "audit/blind-packet.json"
    packet_path.unlink()
    os.link(alias / "audit/sample-manifest.json", packet_path)
    with pytest.raises(ValueError):
        load_verified_audit_sample_root(alias, provider_evidence=evidence)

    symlink = tmp_path / "symlink"
    shutil.copytree(baseline, symlink)
    packet_path = symlink / "audit/blind-packet.json"
    packet_path.unlink()
    packet_path.symlink_to(baseline / "audit/blind-packet.json")
    with pytest.raises(ValueError):
        load_verified_audit_sample_root(symlink, provider_evidence=evidence)

    parent = tmp_path / "parent"
    shutil.copytree(baseline, parent)
    attachment_path = parent / "audit/population-attachment.json"
    payload = json.loads(attachment_path.read_text(encoding="utf-8"))
    payload["provider_evidence_index_sha256"] = sha256_marker(999_030)
    payload["population_attachment_sha256"] = _population_attachment_digest(payload)
    attachment_path.write_bytes(canonical_json_v1(payload) + b"\n")
    with pytest.raises(ValueError):
        load_verified_audit_sample_root(parent, provider_evidence=evidence)

    oversized = tmp_path / "oversized"
    shutil.copytree(baseline, oversized)
    oversized_packet = oversized / "audit/blind-packet.json"
    oversized_packet.unlink()
    with oversized_packet.open("xb") as descriptor:
        descriptor.truncate(audit_module._AUDIT_SAMPLE_MEMBER_MAX_BYTES["blind-packet.json"] + 1)
    with pytest.raises(ValueError):
        load_verified_audit_sample_root(oversized, provider_evidence=evidence)

    member_race = tmp_path / "member-race"
    shutil.copytree(baseline, member_race)
    real_read_member = audit_module._read_member
    swapped_member = False

    def replace_member_after_snapshot(directory_fd: int, name: str) -> Any:
        nonlocal swapped_member
        result = real_read_member(directory_fd, name)
        if name == "sample-manifest.json" and not swapped_member:
            swapped_member = True
            target = member_race / "audit/sample-manifest.json"
            replacement = member_race / "audit/replacement.tmp"
            replacement.write_bytes(target.read_bytes())
            os.replace(replacement, target)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "_read_member", replace_member_after_snapshot)
        with pytest.raises(ValueError):
            load_verified_audit_sample_root(member_race, provider_evidence=evidence)
    assert swapped_member

    audit_race = tmp_path / "audit-race"
    shutil.copytree(baseline, audit_race)
    swapped_audit = False

    def replace_audit_after_snapshot(directory_fd: int, name: str) -> Any:
        nonlocal swapped_audit
        result = real_read_member(directory_fd, name)
        if not swapped_audit:
            swapped_audit = True
            retained = audit_race / "audit-retained"
            (audit_race / "audit").rename(retained)
            shutil.copytree(retained, audit_race / "audit")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "_read_member", replace_audit_after_snapshot)
        with pytest.raises(ValueError):
            load_verified_audit_sample_root(audit_race, provider_evidence=evidence)
    assert swapped_audit

    root_race = tmp_path / "root-race"
    shutil.copytree(baseline, root_race)
    swapped_root = False

    def replace_root_after_snapshot(directory_fd: int, name: str) -> Any:
        nonlocal swapped_root
        result = real_read_member(directory_fd, name)
        if not swapped_root:
            swapped_root = True
            retained = tmp_path / "root-retained"
            root_race.rename(retained)
            shutil.copytree(retained, root_race)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(audit_module, "_read_member", replace_root_after_snapshot)
        with pytest.raises(ValueError):
            load_verified_audit_sample_root(root_race, provider_evidence=evidence)
    assert swapped_root


def test_sample_verifier_recomputes_seeds_permutations_quotas_probabilities_and_digest(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _provider(provider_fixture)
    manifest, packet = select_audit_sample(population=population, provider_evidence=evidence)
    verify_audit_sample(
        manifest,
        packet,
        population=population,
        provider_evidence=evidence,
    )
    base = manifest.model_dump(mode="json")
    mutations: list[dict[str, Any]] = []
    seed = json.loads(json.dumps(base))
    seed["cells"][0]["seed"] += 1
    mutations.append(seed)
    permutation = json.loads(json.dumps(base))
    permutation["cells"][0]["permutation"] = list(reversed(permutation["cells"][0]["permutation"]))
    mutations.append(permutation)
    quota = json.loads(json.dumps(base))
    key = next(iter(quota["stratum_quotas"]))
    quota["stratum_quotas"][key] += 1
    mutations.append(quota)
    probability = json.loads(json.dumps(base))
    probability_cell = next(
        cell
        for cell in probability["cells"]
        if cell["selected_noncertainty"] < cell["noncertainty_population"]
    )
    probability_cell["selected_noncertainty"] += 1
    changed_probability = Fraction(
        probability_cell["selected_noncertainty"],
        probability_cell["noncertainty_population"],
    )
    probability_cell["inclusion_probability"] = {
        "numerator": changed_probability.numerator,
        "denominator": changed_probability.denominator,
    }
    mutations.append(probability)
    for payload in mutations:
        forged_manifest = _manifest_with_digest(payload)
        forged_packet = _packet_for_manifest(forged_manifest, population.records)
        with pytest.raises(ValueError):
            verify_audit_sample(
                forged_manifest,
                forged_packet,
                population=population,
                provider_evidence=evidence,
            )

    cross_payload = packet.model_dump(mode="json")
    cross_payload["campaign_registry_sha256"] = sha256_marker(999_040)
    cross_payload["packet_sha256"] = stable_digest(
        "laconian-blind-audit-packet-v1",
        {key: value for key, value in cross_payload.items() if key != "packet_sha256"},
    )
    cross_packet = BlindAuditPacketV1.model_validate_json(canonical_json_v1(cross_payload))
    absent = tmp_path / "cross-campaign"
    real_create = audit_module.create_owned_staging
    staging_calls = 0

    def counted_create(*args: Any, **kwargs: Any) -> Any:
        nonlocal staging_calls
        staging_calls += 1
        return real_create(*args, **kwargs)

    monkeypatch.setattr(audit_module, "create_owned_staging", counted_create)
    with pytest.raises(ValueError):
        write_audit_sample_root(
            absent,
            population=population,
            manifest=manifest,
            packet=cross_packet,
            provider_evidence=evidence,
        )
    assert staging_calls == 0
    assert not absent.exists()


def test_sample_verifier_rejects_duplicate_or_unrepresented_population_record(
    provider_fixture: CompleteProviderEvidenceFixture,
    population: VerifiedAuditPopulationV1,
) -> None:
    manifest, _ = select_audit_sample(
        population=population,
        provider_evidence=_provider(provider_fixture),
    )
    base = manifest.model_dump(mode="json")
    duplicate = json.loads(json.dumps(base))
    duplicate["ordered_selected_record_ids"][1] = duplicate["ordered_selected_record_ids"][0]
    duplicate["sample_manifest_sha256"] = stable_digest(
        "laconian-audit-sample-manifest-v1",
        {
            key: value
            for key, value in duplicate.items()
            if key != "sample_manifest_sha256"
        },
    )
    with pytest.raises(ValidationError):
        AuditSampleManifestV1.model_validate_json(canonical_json_v1(duplicate))
    low_level_duplicate = manifest.model_copy(
        update={
            "ordered_selected_record_ids": tuple(duplicate["ordered_selected_record_ids"]),
            "sample_manifest_sha256": duplicate["sample_manifest_sha256"],
        }
    )
    with pytest.raises(ValueError):
        verify_audit_sample(
            low_level_duplicate,
            _packet_for_manifest(manifest, population.records),
            population=population,
            provider_evidence=_provider(provider_fixture),
        )

    variants: list[dict[str, Any]] = []
    omitted = json.loads(json.dumps(base))
    omitted_cell = next(cell for cell in omitted["cells"] if cell["permutation"])
    omitted_ids = set(omitted_cell["permutation"])
    replacement_id = next(
        record_id
        for cell in omitted["cells"]
        for record_id in cell["permutation"]
        if record_id not in omitted_ids
    )
    omitted_cell["permutation"][0] = replacement_id
    variants.append(omitted)
    foreign = json.loads(json.dumps(base))
    foreign_cell = next(cell for cell in foreign["cells"] if cell["permutation"])
    foreign_cell["permutation"][0] = sha256_marker(999_050)
    variants.append(foreign)
    for payload in variants:
        forged_manifest = _manifest_with_digest(payload)
        try:
            forged_packet = _packet_for_manifest(forged_manifest, population.records)
        except KeyError:
            forged_packet = _packet_for_manifest(manifest, population.records)
        with pytest.raises(ValueError):
            verify_audit_sample(
                forged_manifest,
                forged_packet,
                population=population,
                provider_evidence=_provider(provider_fixture),
            )
