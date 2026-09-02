from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from laconian_eval.benchmark.outcomes import (
    ModelOutcome,
    OutcomeEvidenceV1,
    classify_model_outcome,
)


def _interval(*, lower: float, upper: float):  # type: ignore[no-untyped-def]
    from laconian_eval.benchmark.bootstrap import BootstrapIntervalV1

    return BootstrapIntervalV1(
        point=(lower + upper) / 2,
        lower=lower,
        upper=upper,
        valid_replicates=10_000,
        available=True,
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
                token_sensitivity_min_lower=0.10,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.OPERATIONALLY_INVALID,
        ),
        (
            _evidence(
                semantic_sensitivity_min_lower=-0.04,
                semantic_sensitivity_max_upper=-0.10,
                token_sensitivity_min_lower=0.10,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.NEGATIVE_QUALITY,
        ),
        (
            _evidence(
                token_sensitivity_min_lower=0.10,
                token_sensitivity_max_upper=-0.10,
            ),
            ModelOutcome.NEGATIVE_BREVITY,
        ),
        (_evidence(), ModelOutcome.SUPPORTED),
    )

    for evidence, expected in rows:
        assert classify_model_outcome(evidence).outcome is expected

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
        token_sensitivity_min_lower=0.10,
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
        "token-sensitivity-max-upper-below-zero",
    )


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
