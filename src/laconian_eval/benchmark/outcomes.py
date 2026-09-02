"""Closed per-model benchmark outcome classification."""

from __future__ import annotations

import math
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from laconian_eval.benchmark.bootstrap import BootstrapIntervalV1

_QUALITY_THRESHOLD = -0.05
_BREVITY_THRESHOLD = 0.0

_OPERATIONAL_INTEGRITY_INVALID = "operational-integrity-invalid"
_HARD_QUALITY_NEGATIVE = "hard-quality-upper-below-minus-0.05"
_SEMANTIC_QUALITY_NEGATIVE = (
    "semantic-sensitivity-max-upper-below-minus-0.05"
)
_TOKEN_BREVITY_NEGATIVE = "token-sensitivity-max-upper-below-zero"


class ModelOutcome(str, Enum):  # noqa: UP042 - frozen contract requires str + Enum.
    OPERATIONALLY_INVALID = "operationally-invalid"
    NEGATIVE_QUALITY = "negative-quality"
    NEGATIVE_BREVITY = "negative-brevity"
    SUPPORTED = "supported"
    INCONCLUSIVE = "inconclusive"


class OutcomeEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    integrity_valid: bool
    integrity_reasons: tuple[str, ...]
    coverage_valid: bool
    hard_quality: BootstrapIntervalV1
    semantic_sensitivity_min_lower: float | None
    semantic_sensitivity_max_upper: float | None
    token_sensitivity_min_lower: float | None
    token_sensitivity_max_upper: float | None
    audit_gate_passed: bool
    sensitivity_complete: bool

    @field_validator(
        "semantic_sensitivity_min_lower",
        "semantic_sensitivity_max_upper",
        "token_sensitivity_min_lower",
        "token_sensitivity_max_upper",
    )
    @classmethod
    def validate_sensitivity_extremum(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("sensitivity extrema must be finite when present")
        return value

    @model_validator(mode="after")
    def validate_complete_sensitivity(self) -> Self:
        extrema = (
            self.semantic_sensitivity_min_lower,
            self.semantic_sensitivity_max_upper,
            self.token_sensitivity_min_lower,
            self.token_sensitivity_max_upper,
        )
        if self.sensitivity_complete and any(value is None for value in extrema):
            raise ValueError("complete sensitivity requires all four extrema")
        return self


class ModelOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: ModelOutcome
    reasons: tuple[str, ...]


def classify_model_outcome(evidence: OutcomeEvidenceV1) -> ModelOutcomeV1:
    """Apply the frozen precedence and retain all applicable negative reasons."""

    operational_invalid = (
        not evidence.integrity_valid or bool(evidence.integrity_reasons)
    )
    hard_negative = (
        evidence.coverage_valid
        and evidence.hard_quality.available
        and evidence.hard_quality.upper is not None
        and evidence.hard_quality.upper < _QUALITY_THRESHOLD
    )
    semantic_negative = (
        evidence.coverage_valid
        and evidence.audit_gate_passed
        and evidence.sensitivity_complete
        and evidence.semantic_sensitivity_max_upper is not None
        and evidence.semantic_sensitivity_max_upper < _QUALITY_THRESHOLD
    )
    token_negative_evidence = (
        evidence.coverage_valid
        and evidence.audit_gate_passed
        and evidence.sensitivity_complete
        and evidence.token_sensitivity_max_upper is not None
        and evidence.token_sensitivity_max_upper < _BREVITY_THRESHOLD
    )

    reasons: list[str] = []
    if operational_invalid:
        reasons.append(_OPERATIONAL_INTEGRITY_INVALID)
        reasons.extend(evidence.integrity_reasons)
    if hard_negative:
        reasons.append(_HARD_QUALITY_NEGATIVE)
    if semantic_negative:
        reasons.append(_SEMANTIC_QUALITY_NEGATIVE)
    if token_negative_evidence:
        reasons.append(_TOKEN_BREVITY_NEGATIVE)

    quality_pass = (
        evidence.integrity_valid
        and not evidence.integrity_reasons
        and evidence.coverage_valid
        and evidence.hard_quality.available
        and evidence.hard_quality.lower is not None
        and evidence.hard_quality.lower > _QUALITY_THRESHOLD
        and evidence.audit_gate_passed
        and evidence.sensitivity_complete
        and evidence.semantic_sensitivity_min_lower is not None
        and evidence.semantic_sensitivity_min_lower > _QUALITY_THRESHOLD
    )

    if operational_invalid:
        outcome = ModelOutcome.OPERATIONALLY_INVALID
    elif hard_negative or semantic_negative:
        outcome = ModelOutcome.NEGATIVE_QUALITY
    elif quality_pass and token_negative_evidence:
        outcome = ModelOutcome.NEGATIVE_BREVITY
    elif (
        quality_pass
        and evidence.token_sensitivity_min_lower is not None
        and evidence.token_sensitivity_min_lower > _BREVITY_THRESHOLD
    ):
        outcome = ModelOutcome.SUPPORTED
    else:
        outcome = ModelOutcome.INCONCLUSIVE

    return ModelOutcomeV1(outcome=outcome, reasons=tuple(reasons))


__all__ = (
    "ModelOutcome",
    "ModelOutcomeV1",
    "OutcomeEvidenceV1",
    "classify_model_outcome",
)
