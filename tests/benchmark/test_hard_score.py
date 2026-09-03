from __future__ import annotations

import inspect
from collections.abc import Iterator
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from laconian_eval.capsule.canonical import stable_digest

from .helpers import (
    SealedScoredScenario,
    hard_score_record_payload,
    hard_score_request_set_payload,
    sealed_scored_scenario,
    sha256_marker,
)


@pytest.fixture(scope="module")
def scored_scenario(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[SealedScoredScenario]:
    monkeypatch = pytest.MonkeyPatch()
    try:
        yield sealed_scored_scenario(
            tmp_path_factory.mktemp("task3-sealed-mixed"),
            monkeypatch,
        )
    finally:
        monkeypatch.undo()


@pytest.fixture(scope="module")
def zero_pass_scenario(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[SealedScoredScenario]:
    monkeypatch = pytest.MonkeyPatch()
    try:
        yield sealed_scored_scenario(
            tmp_path_factory.mktemp("task3-sealed-zero-pass"),
            monkeypatch,
            all_hard_fail=True,
        )
    finally:
        monkeypatch.undo()


def _unchecked_evidence_copy(evidence: object, **updates: object) -> object:
    from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2

    assert type(evidence) is VerifiedScoredCapsuleV2
    copied = object.__new__(VerifiedScoredCapsuleV2)
    for name in (
        "seal",
        "capsule_sha256",
        "manifest",
        "manifest_sha256",
        "plan_sha256",
        "plan",
        "scored_attempts",
        "cases_by_uid",
    ):
        object.__setattr__(copied, name, updates.get(name, getattr(evidence, name)))
    return copied


def _unchecked_context_copy(
    source: object,
    *,
    index: object | None = None,
    root_index: object | None = None,
    generation_evidence: object | None = None,
) -> object:
    from laconian_eval.benchmark.context import VerifiedGenerationContextIndexV1

    assert type(source) is VerifiedGenerationContextIndexV1
    copied = object.__new__(VerifiedGenerationContextIndexV1)
    object.__setattr__(copied, "expectation", source.expectation)
    object.__setattr__(copied, "index", source.index if index is None else index)
    object.__setattr__(
        copied,
        "root_index",
        source.root_index if root_index is None else root_index,
    )
    object.__setattr__(
        copied,
        "generation_evidence",
        source.generation_evidence if generation_evidence is None else generation_evidence,
    )
    return copied


def _rehashed_context_index(index: object, **updates: object) -> object:
    from laconian_eval.benchmark.context import GenerationContextIndexV1

    assert type(index) is GenerationContextIndexV1
    python_payload = {
        name: getattr(index, name) for name in GenerationContextIndexV1.model_fields
    }
    python_payload.update(updates)
    candidate = GenerationContextIndexV1.model_construct(**python_payload)
    digest = stable_digest(
        "laconian-benchmark-generation-context-index-v1",
        candidate.model_dump(mode="json", exclude={"generation_context_index_sha256"}),
    )
    python_payload["generation_context_index_sha256"] = digest
    return GenerationContextIndexV1.model_construct(**python_payload)


def _rehashed_root_with_member(
    root: object,
    *,
    boundary_ordinal: int,
    member_updates: dict[str, object],
) -> object:
    from laconian_eval.benchmark.context import LayerRootIndexV1

    assert type(root) is LayerRootIndexV1
    members = list(root.members)
    members[boundary_ordinal] = members[boundary_ordinal].model_copy(update=member_updates)
    payload = root.model_dump(mode="json")
    payload["members"] = sorted(
        (member.model_dump(mode="json") for member in members),
        key=lambda member: (
            str(member["generation_model"]).encode("utf-8"),
            bytes.fromhex(str(member["scenario_uid"])),
        ),
    )
    for ordinal, member in enumerate(payload["members"]):
        member["ordinal"] = ordinal
    payload["layer_root_index_sha256"] = stable_digest(
        "laconian-benchmark-layer-root-index-v1",
        {
            key: value
            for key, value in payload.items()
            if key != "layer_root_index_sha256"
        },
    )
    return LayerRootIndexV1.model_validate(payload)


def test_hard_score_record_enforces_closed_pass_and_failure_shapes() -> None:
    from laconian_eval.benchmark.hard_score import HardScoreRecordV1

    passed = HardScoreRecordV1.model_validate(hard_score_record_payload(0))
    failed = HardScoreRecordV1.model_validate(
        hard_score_record_payload(1, hard_pass=False, terminal_reason="success")
    )
    rejected = HardScoreRecordV1.model_validate(
        hard_score_record_payload(2, hard_pass=False, terminal_reason="provider_rejected")
    )
    assert passed.reason_codes == ("hard_pass",)
    assert failed.response_id is not None and failed.judge_request_id is None
    assert rejected.response_id is None and rejected.reason_codes == ("provider_rejected",)

    missing_judge_id = passed.model_dump(mode="json")
    missing_judge_id["judge_request_id"] = None
    duplicate_reasons = failed.model_dump(mode="json")
    duplicate_reasons["reason_codes"] = ["required_literal", "required_literal"]
    provider_response = rejected.model_dump(mode="json")
    provider_response["response_id"] = "a" * 64
    for mutation in (missing_judge_id, duplicate_reasons, provider_response):
        with pytest.raises(ValidationError):
            HardScoreRecordV1.model_validate(mutation)


def test_hard_score_request_set_has_exact_fields_rows_order_and_self_digest() -> None:
    from laconian_eval.benchmark.hard_score import HardScoreRequestSetV1

    attachment = HardScoreRequestSetV1.model_validate(hard_score_request_set_payload())

    assert tuple(HardScoreRequestSetV1.model_fields) == (
        "schema_version",
        "campaign_id",
        "generation_model",
        "scenario_uid",
        "generation_capsule_sha256",
        "manifest_sha256",
        "plan_sha256",
        "hard_scorer_source_sha256",
        "hard_score_protocol_sha256",
        "judge_protocol_sha256",
        "protocol_bindings",
        "records",
        "ordered_judge_request_ids",
        "hard_score_request_set_sha256",
    )
    assert tuple(record.ordinal for record in attachment.records) == tuple(range(40))
    assert attachment.ordered_judge_request_ids == tuple(
        record.judge_request_id for record in attachment.records if record.hard_pass
    )
    assert attachment.hard_score_request_set_sha256 == stable_digest(
        "laconian-hard-score-request-set-v1",
        attachment.model_dump(mode="json", exclude={"hard_score_request_set_sha256"}),
    )


def test_hard_score_request_set_rejects_missing_duplicate_or_reordered_rows() -> None:
    from laconian_eval.benchmark.hard_score import HardScoreRequestSetV1

    for mutation in ("missing", "duplicate", "reordered"):
        payload = hard_score_request_set_payload()
        records = payload["records"]
        assert isinstance(records, list)
        if mutation == "missing":
            records.pop()
        elif mutation == "duplicate":
            records[1] = records[0]
        else:
            records[0], records[1] = records[1], records[0]
        payload["hard_score_request_set_sha256"] = stable_digest(
            "laconian-hard-score-request-set-v1",
            {
                key: value
                for key, value in payload.items()
                if key != "hard_score_request_set_sha256"
            },
        )
        with pytest.raises(ValidationError):
            HardScoreRequestSetV1.model_validate(payload)


def test_judge_request_id_has_exact_noncyclic_domain_payload() -> None:
    from laconian_eval.benchmark.hard_score import derive_judge_request_id

    values = {
        "campaign_id": "campaign-2026-08-31",
        "generation_capsule_sha256": "a" * 64,
        "plan_item_id": "b" * 64,
        "response_id": "c" * 64,
        "judge_protocol_sha256": "d" * 64,
    }
    assert derive_judge_request_id(**values) == stable_digest(
        "laconian-judge-request-v1", values
    )


def test_hard_score_builder_has_no_raw_identity_or_protocol_scalar_parameters() -> None:
    from laconian_eval.benchmark.hard_score import (
        _build_hard_score_request_set_from_checked_authority,
        _verify_hard_score_request_set_from_checked_authority,
        build_hard_score_request_set,
        recompute_hard_score_request_set_sha256,
        verify_hard_score_request_set,
    )

    assert tuple(inspect.signature(build_hard_score_request_set).parameters) == (
        "context",
        "expectation",
        "boundary_ordinal",
    )
    assert tuple(inspect.signature(recompute_hard_score_request_set_sha256).parameters) == (
        "attachment",
    )
    assert tuple(inspect.signature(verify_hard_score_request_set).parameters) == (
        "attachment",
        "context",
        "expectation",
        "boundary_ordinal",
    )
    assert tuple(
        inspect.signature(
            _build_hard_score_request_set_from_checked_authority
        ).parameters
    ) == ("index", "member", "evidence")
    assert tuple(
        inspect.signature(
            _verify_hard_score_request_set_from_checked_authority
        ).parameters
    ) == ("attachment", "index", "member", "evidence")


def test_hard_score_request_set_covers_all_40_plan_rows_and_only_hard_passes(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.hard_score import (
        build_hard_score_request_set,
        recompute_hard_score_request_set_sha256,
        verify_hard_score_request_set,
    )

    attachment = build_hard_score_request_set(
        context=scored_scenario.context,
        expectation=scored_scenario.expectation,
        boundary_ordinal=scored_scenario.boundary_ordinal,
    )

    assert tuple(record.ordinal for record in attachment.records) == tuple(range(40))
    assert tuple(record.plan_item_id for record in attachment.records) == tuple(
        row.plan_item_id for row in scored_scenario.evidence.plan
    )
    assert tuple(record.attempt_id for record in attachment.records) == tuple(
        row.attempt_id for row in scored_scenario.evidence.scored_attempts
    )
    assert len(attachment.ordered_judge_request_ids) == 38
    assert attachment.ordered_judge_request_ids == tuple(
        record.judge_request_id for record in attachment.records if record.hard_pass
    )
    assert all(
        record.judge_request_id is None
        for record in attachment.records
        if not record.hard_pass
    )
    assert sum(record.reason_codes == ("provider_rejected",) for record in attachment.records) == 1
    deterministic_failures = tuple(
        record
        for record in attachment.records
        if record.terminal_reason == "success" and not record.hard_pass
    )
    assert len(deterministic_failures) == 1
    assert deterministic_failures[0].response_id is not None
    assert deterministic_failures[0].reason_codes == ("required_literal",)
    assert attachment.hard_score_request_set_sha256 == (
        recompute_hard_score_request_set_sha256(attachment)
    )
    assert (
        verify_hard_score_request_set(
            attachment,
            context=scored_scenario.context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )
        is None
    )


def test_zero_hard_pass_set_is_still_sealed(
    zero_pass_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.hard_score import (
        build_hard_score_request_set,
        recompute_hard_score_request_set_sha256,
        verify_hard_score_request_set,
    )

    attachment = build_hard_score_request_set(
        context=zero_pass_scenario.context,
        expectation=zero_pass_scenario.expectation,
        boundary_ordinal=zero_pass_scenario.boundary_ordinal,
    )
    assert len(attachment.records) == 40
    assert not any(record.hard_pass for record in attachment.records)
    assert attachment.ordered_judge_request_ids == ()
    assert attachment.hard_score_request_set_sha256 == (
        recompute_hard_score_request_set_sha256(attachment)
    )
    verify_hard_score_request_set(
        attachment,
        context=zero_pass_scenario.context,
        expectation=zero_pass_scenario.expectation,
        boundary_ordinal=zero_pass_scenario.boundary_ordinal,
    )


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "reordered", "wrong_capsule"))
def test_hard_score_request_set_rejects_nonbijective_or_unbound_evidence(
    scored_scenario: SealedScoredScenario,
    mutation: str,
) -> None:
    from laconian_eval.benchmark.hard_score import HardScoreError, build_hard_score_request_set

    evidence = scored_scenario.evidence
    plan = list(evidence.plan)
    scored = list(evidence.scored_attempts)
    evidence_updates: dict[str, object]
    if mutation == "missing":
        evidence_updates = {"plan": tuple(plan[:-1]), "scored_attempts": tuple(scored[:-1])}
    elif mutation == "duplicate":
        plan[1] = plan[0]
        scored[1] = scored[0]
        evidence_updates = {"plan": tuple(plan), "scored_attempts": tuple(scored)}
    elif mutation == "reordered":
        plan[0], plan[1] = plan[1], plan[0]
        scored[0], scored[1] = scored[1], scored[0]
        evidence_updates = {"plan": tuple(plan), "scored_attempts": tuple(scored)}
    else:
        evidence_updates = {"capsule_sha256": sha256_marker(120_000)}
    hostile_evidence = _unchecked_evidence_copy(evidence, **evidence_updates)
    evidence_vector = list(scored_scenario.context.generation_evidence)
    evidence_vector[scored_scenario.boundary_ordinal] = hostile_evidence
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        generation_evidence=tuple(evidence_vector),
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_hard_score_derives_campaign_model_scenario_and_three_code_protocol_hashes_from_context(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import protocol_bindings_from_context
    from laconian_eval.benchmark.hard_score import build_hard_score_request_set

    attachment = build_hard_score_request_set(
        context=scored_scenario.context,
        expectation=scored_scenario.expectation,
        boundary_ordinal=scored_scenario.boundary_ordinal,
    )
    index = scored_scenario.context.index
    member = scored_scenario.context.root_index.members[scored_scenario.boundary_ordinal]

    assert attachment.campaign_id == index.campaign_id
    assert attachment.generation_model == member.generation_model
    assert attachment.scenario_uid == member.scenario_uid
    assert attachment.generation_capsule_sha256 == member.generation_capsule_sha256
    assert attachment.manifest_sha256 == scored_scenario.evidence.manifest_sha256
    assert attachment.plan_sha256 == scored_scenario.evidence.plan_sha256
    assert attachment.hard_scorer_source_sha256 == index.hard_scorer_source_sha256
    assert attachment.hard_score_protocol_sha256 == index.hard_score_protocol_sha256
    assert attachment.judge_protocol_sha256 == index.judge_protocol_sha256
    assert attachment.protocol_bindings == protocol_bindings_from_context(index)
    assert attachment.protocol_bindings.audit_protocol_sha256 == index.audit_protocol_sha256
    assert attachment.protocol_bindings.workflow_root == index.workflow_root


def test_hard_score_builder_and_verifier_require_external_verified_context_expectation(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import VerifiedGenerationContextExpectationV1
    from laconian_eval.benchmark.hard_score import (
        HardScoreError,
        build_hard_score_request_set,
        verify_hard_score_request_set,
    )

    attachment = build_hard_score_request_set(
        context=scored_scenario.context,
        expectation=scored_scenario.expectation,
        boundary_ordinal=scored_scenario.boundary_ordinal,
    )
    wrong_external_expectation = VerifiedGenerationContextExpectationV1(
        expectation=scored_scenario.expectation.expectation,
        bound_generation_complete_authority_root_sha256=sha256_marker(120_001),
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=scored_scenario.context,
            expectation=wrong_external_expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )
    with pytest.raises(HardScoreError):
        verify_hard_score_request_set(
            attachment,
            context=scored_scenario.context,
            expectation=wrong_external_expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_hard_score_verifier_rebuilds_and_rejects_rehashed_attachment_substitution(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.hard_score import (
        HardScoreError,
        HardScoreRequestSetV1,
        _build_hard_score_request_set_from_checked_authority,
        _verify_hard_score_request_set_from_checked_authority,
        build_hard_score_request_set,
        verify_hard_score_request_set,
    )

    attachment = build_hard_score_request_set(
        context=scored_scenario.context,
        expectation=scored_scenario.expectation,
        boundary_ordinal=scored_scenario.boundary_ordinal,
    )
    member = scored_scenario.context.root_index.members[scored_scenario.boundary_ordinal]
    checked_built = _build_hard_score_request_set_from_checked_authority(
        index=scored_scenario.context.index,
        member=member,
        evidence=scored_scenario.evidence,
    )
    assert checked_built == attachment
    _verify_hard_score_request_set_from_checked_authority(
        attachment,
        index=scored_scenario.context.index,
        member=member,
        evidence=scored_scenario.evidence,
    )
    payload = attachment.model_dump(mode="json")
    payload["generation_model"] = "forged-generation-model"
    payload["hard_score_request_set_sha256"] = stable_digest(
        "laconian-hard-score-request-set-v1",
        {
            key: value
            for key, value in payload.items()
            if key != "hard_score_request_set_sha256"
        },
    )
    forged = HardScoreRequestSetV1.model_validate(payload)

    with pytest.raises(HardScoreError):
        verify_hard_score_request_set(
            forged,
            context=scored_scenario.context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )
    with pytest.raises(HardScoreError):
        _verify_hard_score_request_set_from_checked_authority(
            forged,
            index=scored_scenario.context.index,
            member=member,
            evidence=scored_scenario.evidence,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "campaign_id",
        "generation_model",
        "scenario_uid",
        "hard_scorer_source_sha256",
        "hard_score_protocol_sha256",
        "judge_protocol_sha256",
        "audit_protocol_sha256",
        "generation_member",
        "workflow_root",
    ),
)
def test_hard_score_builder_and_verifier_reject_context_member_source_protocol_or_workflow_root_substitution(  # noqa: E501
    scored_scenario: SealedScoredScenario,
    mutation: str,
) -> None:
    from laconian_eval.benchmark.hard_score import (
        HardScoreError,
        build_hard_score_request_set,
        verify_hard_score_request_set,
    )

    attachment = build_hard_score_request_set(
        context=scored_scenario.context,
        expectation=scored_scenario.expectation,
        boundary_ordinal=scored_scenario.boundary_ordinal,
    )
    root = scored_scenario.context.root_index
    index = scored_scenario.context.index
    if mutation in {"generation_model", "scenario_uid", "generation_member"}:
        member_field, replacement = {
            # Keep the rehashed root internally canonical so this regression
            # exercises hard-score context verification rather than the
            # layer-index duplicate/order guard.
            "generation_model": ("generation_model", "gpt-5.6-soa"),
            "scenario_uid": ("scenario_uid", "0" * 64),
            "generation_member": ("generation_capsule_sha256", sha256_marker(120_003)),
        }[mutation]
        forged_root = _rehashed_root_with_member(
            root,
            boundary_ordinal=scored_scenario.boundary_ordinal,
            member_updates={member_field: replacement},
        )
        index_updates: dict[str, object] = {
            "generation_root_index_sha256": forged_root.layer_root_index_sha256,
            "ordered_generation_capsule_sha256s": tuple(
                member.generation_capsule_sha256 for member in forged_root.members
            ),
        }
        forged_index = _rehashed_context_index(index, **index_updates)
    elif mutation == "campaign_id":
        root_payload = root.model_dump(mode="json")
        root_payload["campaign_id"] = "forged-campaign"
        root_payload["layer_root_index_sha256"] = stable_digest(
            "laconian-benchmark-layer-root-index-v1",
            {
                key: value
                for key, value in root_payload.items()
                if key != "layer_root_index_sha256"
            },
        )
        forged_root = type(root).model_validate(root_payload)
        forged_index = _rehashed_context_index(
            index,
            campaign_id="forged-campaign",
            generation_root_index_sha256=forged_root.layer_root_index_sha256,
        )
    else:
        forged_root = root
        forged_index = _rehashed_context_index(index, **{mutation: sha256_marker(120_004)})
    assert forged_index.generation_context_index_sha256 == stable_digest(
        "laconian-benchmark-generation-context-index-v1",
        forged_index.model_dump(mode="json", exclude={"generation_context_index_sha256"}),
    )
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        index=forged_index,
        root_index=forged_root,
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )
    with pytest.raises(HardScoreError):
        verify_hard_score_request_set(
            attachment,
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_hard_score_rejects_forged_rehashed_context_against_external_expected_digest(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import GenerationContextIndexV1
    from laconian_eval.benchmark.hard_score import HardScoreError, build_hard_score_request_set

    payload = scored_scenario.context.index.model_dump(mode="json")
    payload["hard_scorer_source_sha256"] = sha256_marker(120_005)
    payload["generation_context_index_sha256"] = stable_digest(
        "laconian-benchmark-generation-context-index-v1",
        {
            key: value
            for key, value in payload.items()
            if key != "generation_context_index_sha256"
        },
    )
    forged_index = GenerationContextIndexV1.model_validate(payload)
    assert forged_index.generation_context_index_sha256 != (
        scored_scenario.expectation.expectation.expected_context_index_sha256
    )
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        index=forged_index,
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_hard_score_rejects_unknown_check_name_in_verified_parent_projection(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.hard_score import HardScoreError, build_hard_score_request_set
    from laconian_eval.capsule.scorable import ScoredAttemptV2

    scored_rows = list(scored_scenario.evidence.scored_attempts)
    failure_ordinal = next(
        row.ordinal
        for row in scored_rows
        if row.terminal_reason == "success" and not row.hard_pass
    )
    failure_payload = scored_rows[failure_ordinal].model_dump(mode="python", round_trip=True)
    failure_payload["checks"] = ({"name": "future.unapproved_check", "passed": False},)
    scored_rows[failure_ordinal] = ScoredAttemptV2.model_validate(failure_payload)
    hostile_evidence = _unchecked_evidence_copy(
        scored_scenario.evidence,
        scored_attempts=tuple(scored_rows),
    )
    evidence_vector = list(scored_scenario.context.generation_evidence)
    evidence_vector[scored_scenario.boundary_ordinal] = hostile_evidence
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        generation_evidence=tuple(evidence_vector),
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_hard_score_reprojects_verified_parent_from_raw_plan_and_cases(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.hard_score import (
        HardScoreError,
        build_hard_score_request_set,
        verify_hard_score_request_set,
    )
    from laconian_eval.capsule.scorable import ScoredAttemptV2

    genuine_attachment = build_hard_score_request_set(
        context=scored_scenario.context,
        expectation=scored_scenario.expectation,
        boundary_ordinal=scored_scenario.boundary_ordinal,
    )
    scored_rows = list(scored_scenario.evidence.scored_attempts)
    pass_ordinal = next(row.ordinal for row in scored_rows if row.hard_pass)
    pass_payload = scored_rows[pass_ordinal].model_dump(mode="python", round_trip=True)
    pass_payload["checks"] = tuple(
        {"name": check.name, "passed": False}
        for check in scored_rows[pass_ordinal].checks
    )
    pass_payload["hard_pass"] = False
    scored_rows[pass_ordinal] = ScoredAttemptV2.model_validate(pass_payload)
    hostile_evidence = _unchecked_evidence_copy(
        scored_scenario.evidence,
        scored_attempts=tuple(scored_rows),
    )
    evidence_vector = list(scored_scenario.context.generation_evidence)
    evidence_vector[scored_scenario.boundary_ordinal] = hostile_evidence
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        generation_evidence=tuple(evidence_vector),
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )
    with pytest.raises(HardScoreError):
        verify_hard_score_request_set(
            genuine_attachment,
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_hard_score_rejects_exact_type_evidence_with_forged_seal(
    scored_scenario: SealedScoredScenario,
) -> None:
    """An exact runtime type is not evidence unless its sealed sidecar still verifies."""

    from laconian_eval.benchmark.hard_score import HardScoreError, build_hard_score_request_set

    evidence = scored_scenario.evidence
    forged_evidence = _unchecked_evidence_copy(
        evidence,
        seal=evidence.seal.model_copy(
            update={"final_event_sequence": evidence.seal.final_event_sequence + 1}
        ),
    )
    evidence_vector = list(scored_scenario.context.generation_evidence)
    evidence_vector[scored_scenario.boundary_ordinal] = forged_evidence
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        generation_evidence=tuple(evidence_vector),
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_hard_score_rejects_forged_plan_before_iterating_it(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.hard_score import HardScoreError, build_hard_score_request_set

    class PlanIterationReached(BaseException):
        pass

    class FailIfIterated:
        def __iter__(self) -> Iterator[object]:
            raise PlanIterationReached

    hostile_evidence = _unchecked_evidence_copy(
        scored_scenario.evidence,
        plan=FailIfIterated(),
    )
    evidence_vector = list(scored_scenario.context.generation_evidence)
    evidence_vector[scored_scenario.boundary_ordinal] = hostile_evidence
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        generation_evidence=tuple(evidence_vector),
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_sidecar_reconstruction_rejects_oversized_tuple_before_nested_validation(
    scored_scenario: SealedScoredScenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import laconian_eval.benchmark.context as context_module
    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes
    from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
    from laconian_eval.capsule.record_models import PlanRowV1

    class NestedPlanValidationReached(BaseException):
        pass

    original_revalidate = context_module._revalidate_model

    def fail_on_nested_plan(model_type: object, value: object) -> object:
        if model_type is PlanRowV1:
            raise NestedPlanValidationReached
        return original_revalidate(model_type, value)

    oversized_evidence = _unchecked_evidence_copy(
        scored_scenario.evidence,
        plan=(scored_scenario.evidence.plan[0],) * (RESOURCE_LIMITS_V1.plan_rows + 1),
    )
    monkeypatch.setattr(context_module, "_revalidate_model", fail_on_nested_plan)

    with pytest.raises(ValueError):
        _reconstruct_scored_sidecar_bytes(oversized_evidence)


def test_sidecar_reconstruction_rejects_seal_files_before_iterating_them(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes
    from laconian_eval.capsule.seal_models import SealV1

    class SealFilesIterationReached(BaseException):
        pass

    class FailIfIterated:
        def __iter__(self) -> Iterator[object]:
            raise SealFilesIterationReached

    genuine_seal = scored_scenario.evidence.seal
    hostile_seal = SealV1.model_construct(
        **(genuine_seal.model_dump(mode="python", round_trip=True) | {"files": FailIfIterated()})
    )
    hostile_evidence = _unchecked_evidence_copy(
        scored_scenario.evidence,
        seal=hostile_seal,
    )

    with pytest.raises(ValueError):
        _reconstruct_scored_sidecar_bytes(hostile_evidence)


def test_sidecar_reconstruction_rejects_case_mapping_with_extra_items(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes

    class CaseItemsIterationReached(BaseException):
        pass

    class UnderreportingCases(dict[str, object]):
        def __len__(self) -> int:
            return 0

        def items(self) -> Iterator[tuple[str, object]]:
            yield next(iter(super().items()))
            raise CaseItemsIterationReached

    hostile_evidence = _unchecked_evidence_copy(
        scored_scenario.evidence,
        cases_by_uid=MappingProxyType(UnderreportingCases(scored_scenario.evidence.cases_by_uid)),
    )

    with pytest.raises(ValueError):
        _reconstruct_scored_sidecar_bytes(hostile_evidence)


def test_sidecar_reconstruction_rejects_scored_checks_before_iterating_them(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes
    from laconian_eval.capsule.scorable import ScoredAttemptV2

    class ChecksIterationReached(BaseException):
        pass

    class FailIfIterated(tuple[object, ...]):
        def __iter__(self) -> Iterator[object]:
            raise ChecksIterationReached

    genuine_scored = scored_scenario.evidence.scored_attempts[0]
    hostile_scored = ScoredAttemptV2.model_construct(
        **(
            genuine_scored.model_dump(mode="python", round_trip=True)
            | {"checks": FailIfIterated()}
        )
    )
    hostile_evidence = _unchecked_evidence_copy(
        scored_scenario.evidence,
        scored_attempts=(hostile_scored, *scored_scenario.evidence.scored_attempts[1:]),
    )

    with pytest.raises(ValueError):
        _reconstruct_scored_sidecar_bytes(hostile_evidence)


def test_sidecar_reconstruction_rejects_case_constraints_before_iterating_them(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes
    from laconian_eval.models import HardConstraints, ResponseCase

    class ConstraintsIterationReached(BaseException):
        pass

    class FailIfIterated(tuple[object, ...]):
        def __iter__(self) -> Iterator[object]:
            raise ConstraintsIterationReached

    evidence = scored_scenario.evidence
    case_uid, genuine_case = next(iter(evidence.cases_by_uid.items()))
    hostile_constraints = HardConstraints.model_construct(
        **(
            genuine_case.hard_constraints.model_dump(mode="python", round_trip=True)
            | {"required_literals": FailIfIterated()}
        )
    )
    hostile_case = ResponseCase.model_construct(
        **(
            genuine_case.model_dump(mode="python", round_trip=True)
            | {"hard_constraints": hostile_constraints}
        )
    )
    hostile_cases = dict(evidence.cases_by_uid)
    hostile_cases[case_uid] = hostile_case
    hostile_evidence = _unchecked_evidence_copy(
        evidence,
        cases_by_uid=MappingProxyType(hostile_cases),
    )

    with pytest.raises(ValueError):
        _reconstruct_scored_sidecar_bytes(hostile_evidence)


def test_hard_score_rejects_coherent_raw_rescore_without_root_sidecar_binding(
    scored_scenario: SealedScoredScenario,
) -> None:
    """All local score joins can pass while the sealed sidecar bytes still differ."""

    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes
    from laconian_eval.benchmark.hard_score import HardScoreError, build_hard_score_request_set
    from laconian_eval.capsule.attempts import RawAttemptV2
    from laconian_eval.capsule.scorable import project_scored_attempts

    evidence = scored_scenario.evidence
    target = next(row.raw for row in evidence.scored_attempts if row.raw.terminal)
    raw_payload = target.model_dump(mode="python", round_trip=True)
    raw_payload["elapsed_ms"] = target.elapsed_ms + 1
    forged_raw = RawAttemptV2.model_validate(raw_payload)
    forged_scored = project_scored_attempts(
        plan=evidence.plan,
        raw_attempts=tuple(
            forged_raw if row.raw.attempt_id == target.attempt_id else row.raw
            for row in evidence.scored_attempts
        ),
        cases_by_uid=evidence.cases_by_uid,
    )
    assert len(forged_scored) == len(evidence.scored_attempts)
    hostile_evidence = _unchecked_evidence_copy(
        evidence,
        scored_attempts=forged_scored,
    )
    assert (
        _reconstruct_scored_sidecar_bytes(hostile_evidence).sidecar_bytes
        != _reconstruct_scored_sidecar_bytes(evidence).sidecar_bytes
    )
    evidence_vector = list(scored_scenario.context.generation_evidence)
    evidence_vector[scored_scenario.boundary_ordinal] = hostile_evidence
    hostile_context = _unchecked_context_copy(
        scored_scenario.context,
        generation_evidence=tuple(evidence_vector),
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=hostile_context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=scored_scenario.boundary_ordinal,
        )


def test_context_sidecar_reconstruction_matches_real_canonical_sidecar(
    scored_scenario: SealedScoredScenario,
) -> None:
    from laconian_eval.benchmark.context import _reconstruct_scored_sidecar_bytes

    member = scored_scenario.context.root_index.members[scored_scenario.boundary_ordinal]
    assert _reconstruct_scored_sidecar_bytes(scored_scenario.evidence).sidecar_bytes == (
        scored_scenario.sidecar_path.read_bytes()
    )
    assert member.scored_sidecar_sha256


@pytest.mark.parametrize("boundary_ordinal", (True, -1, 36))
def test_hard_score_builder_rejects_boolean_or_out_of_range_boundary(
    scored_scenario: SealedScoredScenario,
    boundary_ordinal: object,
) -> None:
    from laconian_eval.benchmark.hard_score import (
        HardScoreError,
        _build_hard_score_request_set_from_checked_authority,
        build_hard_score_request_set,
    )

    with pytest.raises(HardScoreError):
        build_hard_score_request_set(
            context=scored_scenario.context,
            expectation=scored_scenario.expectation,
            boundary_ordinal=boundary_ordinal,  # type: ignore[arg-type]
        )
    member = scored_scenario.context.root_index.members[scored_scenario.boundary_ordinal]
    hostile_payload = {name: getattr(member, name) for name in type(member).model_fields}
    hostile_payload["ordinal"] = boundary_ordinal
    hostile_member = type(member).model_construct(**hostile_payload)
    with pytest.raises(HardScoreError):
        _build_hard_score_request_set_from_checked_authority(
            index=scored_scenario.context.index,
            member=hostile_member,
            evidence=scored_scenario.evidence,
        )
    if boundary_ordinal is True:
        ordered = list(scored_scenario.context.index.ordered_generation_capsule_sha256s)
        ordered[scored_scenario.boundary_ordinal] = sha256_marker(120_002)
        index_type = type(scored_scenario.context.index)
        hostile_index_payload = {
            name: getattr(scored_scenario.context.index, name)
            for name in index_type.model_fields
        }
        hostile_index_payload["ordered_generation_capsule_sha256s"] = tuple(ordered)
        hostile_index = index_type.model_construct(
            **hostile_index_payload,
        )
        with pytest.raises(HardScoreError):
            _build_hard_score_request_set_from_checked_authority(
                index=hostile_index,
                member=member,
                evidence=scored_scenario.evidence,
            )
