from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from laconian_eval.benchmark.bootstrap import BootstrapIntervalV1
from laconian_eval.benchmark.outcomes import (
    ModelOutcome,
    ModelOutcomeV1,
    OutcomeEvidenceV1,
    classify_model_outcome,
)


def _interval(*, lower: float, upper: float) -> BootstrapIntervalV1:
    return BootstrapIntervalV1(
        point=(lower + upper) / 2,
        lower=lower,
        upper=upper,
        valid_replicates=10_000,
        available=True,
    )


def _unavailable_interval() -> BootstrapIntervalV1:
    return BootstrapIntervalV1(
        point=None,
        lower=None,
        upper=None,
        valid_replicates=9_989,
        available=False,
    )


def _evidence(**overrides: object) -> OutcomeEvidenceV1:
    fields: dict[str, object] = {
        "integrity_valid": True,
        "integrity_reasons": (),
        "coverage_valid": True,
        "hard_quality": _interval(lower=-0.04, upper=-0.03),
        "semantic_sensitivity_min_lower": -0.04,
        "semantic_sensitivity_max_upper": -0.03,
        "token_sensitivity_min_lower": 0.01,
        "token_sensitivity_max_upper": 0.02,
        "audit_gate_passed": True,
        "sensitivity_complete": True,
    }
    fields.update(overrides)
    return OutcomeEvidenceV1.model_validate(fields)


def test_outcome_precedence_is_operational_invalid_then_negative_quality_then_brevity_then_supported() -> (  # noqa: E501
    None
):
    rows = (
        (
            _evidence(
                integrity_valid=False,
                integrity_reasons=("protocol-failure",),
                hard_quality=_interval(lower=-0.20, upper=-0.10),
                semantic_sensitivity_min_lower=-0.20,
                semantic_sensitivity_max_upper=-0.10,
                token_sensitivity_min_lower=-0.20,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.OPERATIONALLY_INVALID,
        ),
        (
            _evidence(
                hard_quality=_interval(lower=-0.20, upper=-0.10),
                semantic_sensitivity_min_lower=-0.20,
                semantic_sensitivity_max_upper=-0.10,
                token_sensitivity_min_lower=-0.20,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.NEGATIVE_QUALITY,
        ),
        (
            _evidence(
                token_sensitivity_min_lower=-0.20,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.NEGATIVE_BREVITY,
        ),
        (_evidence(), ModelOutcome.SUPPORTED),
    )

    for evidence, expected in rows:
        assert classify_model_outcome(evidence).outcome is expected

    crossing_hard_interval = _evidence(
        hard_quality=_interval(lower=-0.10, upper=0.10),
        token_sensitivity_min_lower=-0.20,
        token_sensitivity_max_upper=-0.10,
    )
    crossing_result = classify_model_outcome(crossing_hard_interval)
    assert crossing_result.outcome is ModelOutcome.INCONCLUSIVE
    assert "token-sensitivity-max-upper-below-zero" not in crossing_result.reasons

    from laconian_eval.benchmark import ModelOutcome as PublicModelOutcome

    assert PublicModelOutcome is ModelOutcome


def test_all_applicable_negative_reasons_are_retained() -> None:
    evidence = _evidence(
        integrity_valid=False,
        integrity_reasons=(
            "protocol-failure",
            "protocol-failure",
            "provenance-failure",
        ),
        hard_quality=_interval(lower=-0.20, upper=-0.10),
        semantic_sensitivity_min_lower=-0.20,
        semantic_sensitivity_max_upper=-0.10,
        token_sensitivity_min_lower=-0.20,
        token_sensitivity_max_upper=-0.10,
    )

    result = classify_model_outcome(evidence)

    assert result.outcome is ModelOutcome.OPERATIONALLY_INVALID
    assert result.reasons == (
        "operational-integrity-invalid",
        "protocol-failure",
        "protocol-failure",
        "provenance-failure",
        "hard-quality-upper-below-minus-0.05",
        "semantic-sensitivity-max-upper-below-minus-0.05",
    )

    isolation_rows = (
        (
            _evidence(
                coverage_valid=False,
                hard_quality=_interval(lower=-0.20, upper=-0.10),
                semantic_sensitivity_min_lower=-0.20,
                semantic_sensitivity_max_upper=-0.10,
                token_sensitivity_min_lower=-0.20,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.INCONCLUSIVE,
            (),
        ),
        (
            _evidence(
                hard_quality=_unavailable_interval(),
                token_sensitivity_min_lower=-0.20,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.INCONCLUSIVE,
            (),
        ),
        (
            _evidence(
                hard_quality=_interval(lower=-0.20, upper=-0.10),
                semantic_sensitivity_min_lower=-0.20,
                semantic_sensitivity_max_upper=-0.10,
                token_sensitivity_min_lower=-0.20,
                token_sensitivity_max_upper=-0.10,
                audit_gate_passed=False,
            ),
            ModelOutcome.NEGATIVE_QUALITY,
            ("hard-quality-upper-below-minus-0.05",),
        ),
        (
            _evidence(
                sensitivity_complete=False,
                token_sensitivity_min_lower=-0.20,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.INCONCLUSIVE,
            (),
        ),
    )
    for isolated, expected_outcome, expected_reasons in isolation_rows:
        isolated_result = classify_model_outcome(isolated)
        assert isolated_result.outcome is expected_outcome
        assert isolated_result.reasons == expected_reasons


def test_boundary_values_are_inconclusive_because_thresholds_are_strict() -> None:
    boundary = _evidence(
        hard_quality=_interval(lower=-0.05, upper=-0.05),
        semantic_sensitivity_min_lower=-0.05,
        semantic_sensitivity_max_upper=-0.05,
        token_sensitivity_min_lower=0.0,
        token_sensitivity_max_upper=0.0,
    )
    result = classify_model_outcome(boundary)
    assert result.outcome is ModelOutcome.INCONCLUSIVE
    assert result.reasons == ()

    incomplete = _evidence(
        sensitivity_complete=False,
        semantic_sensitivity_min_lower=None,
        semantic_sensitivity_max_upper=-0.04,
        token_sensitivity_min_lower=None,
        token_sensitivity_max_upper=0.0,
    )
    assert classify_model_outcome(incomplete).outcome is ModelOutcome.INCONCLUSIVE

    with pytest.raises(ValidationError, match="complete sensitivity"):
        _evidence(sensitivity_complete=True, token_sensitivity_max_upper=None)

    for non_finite in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValidationError, match="finite"):
            _evidence(semantic_sensitivity_max_upper=non_finite)

    for incompatible_extrema in (
        {
            "semantic_sensitivity_min_lower": -0.03,
            "semantic_sensitivity_max_upper": -0.04,
        },
        {
            "token_sensitivity_min_lower": 0.01,
            "token_sensitivity_max_upper": 0.0,
        },
    ):
        with pytest.raises(ValidationError, match="minimum lower exceeds maximum upper"):
            _evidence(**incompatible_extrema)

    raw_evidence = _evidence().model_dump()
    for coercive_fields in (
        {"integrity_valid": 1},
        {"coverage_valid": "yes"},
        {"audit_gate_passed": 1},
        {"sensitivity_complete": "yes"},
        {"semantic_sensitivity_min_lower": True},
        {"token_sensitivity_max_upper": "0.02"},
    ):
        with pytest.raises(ValidationError):
            OutcomeEvidenceV1(**(raw_evidence | coercive_fields))
    with pytest.raises(ValidationError):
        ModelOutcomeV1(outcome="supported", reasons=[])

    class OutcomeEvidenceSubclass(OutcomeEvidenceV1):
        pass

    class BootstrapIntervalSubclass(BootstrapIntervalV1):
        pass

    hostile_outer_values: tuple[object, ...] = (
        {},
        OutcomeEvidenceSubclass.model_validate(raw_evidence),
        _evidence().model_copy(update={"coverage_valid": "yes"}),
        _evidence().model_copy(update={"unexpected": "extra"}),
        _evidence(
            hard_quality=BootstrapIntervalSubclass.model_validate(
                _interval(lower=-0.04, upper=-0.03).model_dump()
            )
        ),
    )
    for hostile in hostile_outer_values:
        with pytest.raises(ValueError, match="strictly valid OutcomeEvidenceV1"):
            classify_model_outcome(hostile)  # type: ignore[arg-type]

    valid_hard = _interval(lower=-0.04, upper=-0.03)
    hostile_hard_updates = (
        {"upper": math.nan},
        {"available": False},
        {"lower": 0.10, "upper": -0.10},
        {"valid_replicates": 10_001},
        {"total_replicates": 9_999},
        {"lower": "-0.04"},
    )
    for hostile_update in hostile_hard_updates:
        forged_hard = valid_hard.model_copy(update=hostile_update)
        forged_outer = _evidence().model_copy(update={"hard_quality": forged_hard})
        with pytest.raises(ValueError, match="strictly valid OutcomeEvidenceV1"):
            classify_model_outcome(forged_outer)
