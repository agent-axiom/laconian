from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from hashlib import sha256

import pytest
from pydantic import ValidationError

from laconian_eval.benchmark.aggregation import (
    AggregatedModelV1,
    GatePairDenominatorsV1,
    InferenceIntegrityError,
    PairDenominatorsV1,
    PlannedObservationV1,
    _build_aggregated_model_from_rows,
    _retained_worst_case_analytical_cost_usd,
    _sealed_micro_usd_per_million,
    _trusted_analytical_cost_usd,
    arm_pass_rate,
    cache_integrity_limitations,
    pair_denominators_for_gate,
)


def _key(*, scenario: int, locale: str, repetition: int) -> dict[str, object]:
    return {
        "scenario_uid": sha256(f"scenario-{scenario}".encode()).hexdigest(),
        "case_id": f"case-{scenario:02d}-{locale}",
        "locale": locale,
        "repetition": repetition,
    }


def _row(
    *,
    scenario: int,
    locale: str,
    repetition: int,
    arm: str = "baseline",
    generation_model: str = "model-a",
    hard_pass: bool = True,
    semantic_success: bool = True,
    response_id: str | None = "response",
    terminal_zero_reason: str | None = None,
    input_tokens: int | None = 20,
    output_tokens: int | None = 7,
    reasoning_tokens: int | None = 7,
    cache_read_tokens: int | None = 2,
    cache_write_tokens: int | None = 0,
    ordinary_uncached_input_tokens: int | None = 18,
    total_tokens: int | None = 27,
    visible_output_tokens: int | None = 0,
    applied_cache_control_status: str = "reported_exact",
    cache_read_status: str = "reported_nonzero",
    cache_write_status: str = "reported_zero",
    service_tier_status: str = "reported_default",
    cache_policy_status: str = "conformant_zero_write",
    analytical_cost_usd: Decimal = Decimal("0.000012"),
    cost_availability: str = "trusted_usage",
    latency_ms: int | None = 25,
    output_characters: int | None = 12,
) -> PlannedObservationV1:
    return PlannedObservationV1(
        generation_model=generation_model,
        **_key(scenario=scenario, locale=locale, repetition=repetition),
        arm=arm,
        response_id=(
            f"{response_id}-{scenario}-{locale}-{repetition}-{arm}"
            if response_id is not None
            else None
        ),
        hard_pass=hard_pass,
        semantic_success=semantic_success,
        terminal_zero_reason=terminal_zero_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        ordinary_uncached_input_tokens=ordinary_uncached_input_tokens,
        total_tokens=total_tokens,
        visible_output_tokens=visible_output_tokens,
        applied_cache_control_status=applied_cache_control_status,
        cache_read_status=cache_read_status,
        cache_write_status=cache_write_status,
        service_tier_status=service_tier_status,
        cache_policy_status=cache_policy_status,
        analytical_cost_usd=analytical_cost_usd,
        cost_availability=cost_availability,
        latency_ms=latency_ms,
        output_characters=output_characters,
    )


@pytest.fixture
def baseline_rows() -> tuple[PlannedObservationV1, ...]:
    return tuple(
        _row(scenario=scenario, locale=locale, repetition=repetition)
        for scenario in range(12)
        for locale in ("en", "ru")
        for repetition in range(5)
    )


@pytest.fixture
def complete_rows(
    baseline_rows: tuple[PlannedObservationV1, ...],
) -> tuple[PlannedObservationV1, ...]:
    return tuple(
        row.model_copy(
            update={
                "arm": arm,
                "response_id": f"{row.response_id}-{arm}",
            }
        )
        for arm in ("baseline", "caveman", "if", "concise")
        for row in baseline_rows
    )


def _replace_row(
    rows: tuple[PlannedObservationV1, ...],
    index: int,
    **updates: object,
) -> tuple[PlannedObservationV1, ...]:
    changed = PlannedObservationV1.model_validate(
        {**rows[index].model_dump(), **updates}
    )
    return (*rows[:index], changed, *rows[index + 1 :])


def test_h_and_s_use_120_planned_key_denominators(
    baseline_rows: tuple[PlannedObservationV1, ...],
) -> None:
    rows = tuple(
        PlannedObservationV1.model_validate(
            {
                **row.model_dump(),
                "hard_pass": index < 91,
                "semantic_success": index < 73,
                "terminal_zero_reason": "hard_fail" if index >= 91 else None,
            }
        )
        for index, row in enumerate(baseline_rows)
    )

    assert arm_pass_rate(rows, gate="hard") == Fraction(91, 120)
    assert arm_pass_rate(rows, gate="semantic") == Fraction(73, 120)


def test_row_builder_rejects_missing_duplicate_or_cross_arm_key_populations(
    complete_rows: tuple[PlannedObservationV1, ...],
) -> None:
    with pytest.raises(InferenceIntegrityError, match="480"):
        _build_aggregated_model_from_rows(
            generation_model="model-a", rows=complete_rows[:-1]
        )

    duplicate = (*complete_rows[:-1], complete_rows[-2])
    with pytest.raises(InferenceIntegrityError, match=r"duplicate|key"):
        _build_aggregated_model_from_rows(generation_model="model-a", rows=duplicate)

    cross_arm = _replace_row(
        complete_rows,
        120,
        scenario_uid=complete_rows[120].scenario_uid[:-1] + "0",
    )
    with pytest.raises(InferenceIntegrityError, match=r"shared|key"):
        _build_aggregated_model_from_rows(generation_model="model-a", rows=cross_arm)

    inconsistent_locale_case = complete_rows
    for index in (0, 120, 240, 360):
        inconsistent_locale_case = _replace_row(
            inconsistent_locale_case,
            index,
            case_id="case-00-en-alternate",
        )
    with pytest.raises(InferenceIntegrityError, match=r"case|repetition"):
        _build_aggregated_model_from_rows(
            generation_model="model-a", rows=inconsistent_locale_case
        )


@pytest.mark.parametrize("reason", ["provider_rejected", "retry_exhausted"])
def test_planned_observation_provider_failures_require_null_response_and_zero_h_s(
    reason: str,
) -> None:
    status = (
        "not_applicable_definitely_rejected"
        if reason == "provider_rejected"
        else "not_applicable_definitely_not_sent"
    )
    failed = _row(
        scenario=0,
        locale="en",
        repetition=0,
        response_id=None,
        hard_pass=False,
        semantic_success=False,
        terminal_zero_reason=reason,
        input_tokens=None,
        output_tokens=None,
        reasoning_tokens=None,
        cache_read_tokens=None,
        cache_write_tokens=None,
        ordinary_uncached_input_tokens=None,
        total_tokens=None,
        visible_output_tokens=None,
        applied_cache_control_status=status,
        cache_read_status=status,
        cache_write_status=status,
        service_tier_status=status,
        cache_policy_status="terminal_no_usage",
        analytical_cost_usd=Decimal(0),
        cost_availability="definitely_rejected_zero",
        latency_ms=None,
        output_characters=None,
    )
    assert failed.response_id is None

    for updates in (
        {"response_id": "unexpected"},
        {"hard_pass": True},
        {"semantic_success": True},
        {"terminal_zero_reason": None},
        {"input_tokens": 0},
        {"latency_ms": 0},
        {"output_characters": 0},
        {"analytical_cost_usd": Decimal("0.000001")},
        {"cost_availability": "retained_worst_case"},
        {"cache_policy_status": "missing_write_detail"},
        {"cache_read_status": "missing"},
    ):
        with pytest.raises(ValidationError):
            PlannedObservationV1.model_validate(
                {**failed.model_dump(), **updates}
            )


@pytest.mark.parametrize(
    ("reason", "hard_pass", "semantic_success", "valid"),
    [
        (None, True, False, True),
        (None, True, True, True),
        (None, False, False, False),
        ("blank_response", False, False, True),
        ("hard_fail", False, False, True),
        ("blank_response", True, False, False),
        ("hard_fail", False, True, False),
    ],
)
def test_planned_observation_success_requires_response_and_exact_h_s_reason_matrix(
    reason: str | None, hard_pass: bool, semantic_success: bool, valid: bool
) -> None:
    kwargs = dict(
        scenario=0,
        locale="en",
        repetition=0,
        terminal_zero_reason=reason,
        hard_pass=hard_pass,
        semantic_success=semantic_success,
    )
    if valid:
        assert _row(**kwargs).response_id is not None
    else:
        with pytest.raises(ValidationError):
            _row(**kwargs)

    with pytest.raises(ValidationError):
        _row(scenario=0, locale="en", repetition=0, response_id=None)


def test_planned_observation_response_and_output_character_presence_match() -> None:
    with pytest.raises(ValidationError):
        _row(scenario=0, locale="en", repetition=0, output_characters=None)

    assert _row(
        scenario=0, locale="en", repetition=0, output_characters=0
    ).output_characters == 0


def test_cache_write_counts_accounting_and_cost_basis_remain_distinct() -> None:
    row = _row(
        scenario=0,
        locale="en",
        repetition=0,
        input_tokens=20,
        cache_read_tokens=2,
        cache_write_tokens=3,
        cache_write_status="reported_nonzero",
        ordinary_uncached_input_tokens=15,
        cache_policy_status="forbidden_nonzero_write",
        analytical_cost_usd=Decimal("0.000099"),
    )
    assert row.cache_write_tokens == 3
    assert row.ordinary_uncached_input_tokens == 15
    assert row.analytical_cost_usd == Decimal("0.000099")

    with pytest.raises(ValidationError):
        _row(
            scenario=0,
            locale="en",
            repetition=0,
            cache_write_tokens=3,
            cache_write_status="reported_nonzero",
            ordinary_uncached_input_tokens=18,
            cache_policy_status="forbidden_nonzero_write",
        )


def test_missing_cache_write_detail_retains_worst_case_cost_and_integrity_limitation() -> None:
    row = _row(
        scenario=0,
        locale="en",
        repetition=0,
        cache_write_tokens=None,
        ordinary_uncached_input_tokens=None,
        cache_write_status="missing",
        cache_policy_status="missing_write_detail",
        cost_availability="retained_worst_case",
        analytical_cost_usd=Decimal("0.001"),
    )
    assert cache_integrity_limitations((row,)) == ("cache_write_detail_missing",)


def test_cost_availability_is_an_exhaustive_three_state_iff_matrix() -> None:
    with pytest.raises(ValidationError):
        _row(
            scenario=0,
            locale="en",
            repetition=0,
            cost_availability="unavailable",
        )

    with pytest.raises(ValidationError):
        _row(
            scenario=0,
            locale="en",
            repetition=0,
            cost_availability="retained_worst_case",
        )

    with pytest.raises(ValidationError):
        _row(
            scenario=0,
            locale="en",
            repetition=0,
            output_tokens=None,
            total_tokens=None,
            reasoning_tokens=None,
            visible_output_tokens=None,
            cost_availability="trusted_usage",
        )


def test_analytical_cost_uses_independent_integer_micro_usd_component_ceilings() -> None:
    rates = tuple(
        _sealed_micro_usd_per_million(value)
        for value in (
            Decimal("0.001"),
            Decimal("0.001"),
            Decimal("0.001"),
            Decimal("0.001"),
            Decimal("0.001"),
        )
    )
    assert _trusted_analytical_cost_usd((1, 1, 1, 1, 1), rates) == Decimal(
        "0.000005"
    )
    assert _retained_worst_case_analytical_cost_usd(rates) == Decimal("0.000274")

    assert _sealed_micro_usd_per_million(Decimal("0.000001")) == 1
    with pytest.raises(InferenceIntegrityError):
        _sealed_micro_usd_per_million(Decimal("0.0000015"))
    with pytest.raises(InferenceIntegrityError):
        _sealed_micro_usd_per_million(-1)


def test_cache_write_evidence_never_changes_visible_output_or_pair_eligibility(
    complete_rows: tuple[PlannedObservationV1, ...],
) -> None:
    before = pair_denominators_for_gate(complete_rows, gate="hard")
    changed = _replace_row(
        complete_rows,
        240,
        cache_write_tokens=None,
        ordinary_uncached_input_tokens=None,
        cache_write_status="missing",
        cache_policy_status="missing_write_detail",
        cost_availability="retained_worst_case",
    )
    assert changed[240].visible_output_tokens == complete_rows[240].visible_output_tokens
    assert pair_denominators_for_gate(changed, gate="hard") == before


def test_visible_tokens_subtract_reasoning_and_never_fall_back_to_billed_output() -> None:
    assert _row(
        scenario=0,
        locale="en",
        repetition=0,
        output_tokens=7,
        reasoning_tokens=7,
        visible_output_tokens=0,
    ).visible_output_tokens == 0

    with pytest.raises(ValidationError):
        _row(
            scenario=0,
            locale="en",
            repetition=0,
            output_tokens=7,
            reasoning_tokens=2,
            visible_output_tokens=7,
        )

    with pytest.raises(ValidationError):
        _row(
            scenario=0,
            locale="en",
            repetition=0,
            output_tokens=7,
            reasoning_tokens=8,
            visible_output_tokens=0,
        )

    unresolved = _row(
        scenario=0,
        locale="en",
        repetition=0,
        reasoning_tokens=None,
        visible_output_tokens=None,
        cost_availability="retained_worst_case",
    )
    assert unresolved.visible_output_tokens is None

    unicode_characters = len("日本🙂")
    descriptive = _row(
        scenario=0,
        locale="en",
        repetition=0,
        reasoning_tokens=None,
        visible_output_tokens=None,
        output_characters=unicode_characters,
        cost_availability="retained_worst_case",
    )
    assert descriptive.output_characters == 3
    assert descriptive.visible_output_tokens is None


def test_eligible_pairs_and_token_pairs_are_distinct(
    complete_rows: tuple[PlannedObservationV1, ...],
) -> None:
    changed = _replace_row(
        complete_rows,
        240,
        output_tokens=None,
        reasoning_tokens=None,
        total_tokens=None,
        visible_output_tokens=None,
        cost_availability="retained_worst_case",
    )
    denominators = pair_denominators_for_gate(changed, gate="hard")
    assert denominators.eligible_pairs == 120
    assert denominators.token_pairs == 119

    malformed_shared = tuple(
        PlannedObservationV1.model_validate(
            {**row.model_dump(), "locale": "en"}
        )
        if row.arm in {"if", "concise"}
        else row
        for row in complete_rows
    )
    if_keys = {
        (row.scenario_uid, row.case_id, row.locale, row.repetition)
        for row in malformed_shared
        if row.arm == "if"
    }
    concise_keys = {
        (row.scenario_uid, row.case_id, row.locale, row.repetition)
        for row in malformed_shared
        if row.arm == "concise"
    }
    assert len(if_keys) == len(concise_keys) == 120
    assert if_keys == concise_keys
    assert len({key[0] for key in if_keys}) == 12
    with pytest.raises(InferenceIntegrityError, match=r"locale|case"):
        pair_denominators_for_gate(malformed_shared, gate="hard")


@pytest.mark.parametrize(
    ("eligible_pairs", "token_pairs", "scenarios"),
    [(1, 0, 0), (120, 121, 12), (11, 0, 1), (10, 0, 11), (120, 0, 13)],
)
def test_pair_denominators_reject_impossible_scenario_counts(
    eligible_pairs: int, token_pairs: int, scenarios: int
) -> None:
    with pytest.raises(ValidationError):
        PairDenominatorsV1(
            planned_pairs=120,
            eligible_pairs=eligible_pairs,
            token_pairs=token_pairs,
            eligible_scenarios=scenarios,
        )


def test_gate_names_are_runtime_closed(
    baseline_rows: tuple[PlannedObservationV1, ...],
    complete_rows: tuple[PlannedObservationV1, ...],
) -> None:
    with pytest.raises(InferenceIntegrityError):
        arm_pass_rate(baseline_rows, gate="other")  # type: ignore[arg-type]
    with pytest.raises(InferenceIntegrityError):
        pair_denominators_for_gate(
            complete_rows, gate="other"  # type: ignore[arg-type]
        )


def test_aggregated_model_requires_shared_arm_keys_canonical_order_and_immutable_gates(
    complete_rows: tuple[PlannedObservationV1, ...],
) -> None:
    model = _build_aggregated_model_from_rows(
        generation_model="model-a", rows=reversed(complete_rows)
    )
    expected = tuple(
        sorted(
            complete_rows,
            key=lambda row: (
                bytes.fromhex(row.scenario_uid),
                row.case_id.encode(),
                row.locale.encode(),
                row.repetition,
                ("baseline", "caveman", "if", "concise").index(row.arm),
            ),
        )
    )
    assert model.rows == expected
    assert model.denominators_by_gate == GatePairDenominatorsV1(
        hard=pair_denominators_for_gate(expected, gate="hard"),
        semantic=pair_denominators_for_gate(expected, gate="semantic"),
    )
    assert model.integrity_limitations == ()

    with pytest.raises(ValidationError):
        AggregatedModelV1(
            generation_model="model-a",
            rows=tuple(reversed(expected)),
            denominators_by_gate=model.denominators_by_gate,
            integrity_limitations=(),
        )
    with pytest.raises(ValidationError):
        model.denominators_by_gate.hard = PairDenominatorsV1(
            planned_pairs=120,
            eligible_pairs=120,
            token_pairs=120,
            eligible_scenarios=12,
        )
