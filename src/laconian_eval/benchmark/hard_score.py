"""Sealed deterministic hard-score request-set attachments."""

from __future__ import annotations

import re
from typing import Literal, TypeAlias, cast

from pydantic import Field, StrictBool, model_validator

from laconian_eval.benchmark.attachments import canonical_json_v1
from laconian_eval.benchmark.context import (
    BenchmarkProtocolBindingsV1,
    GenerationLayerRootMemberV1,
    VerifiedGenerationContextExpectationV1,
    VerifiedGenerationContextIndexV1,
    protocol_bindings_from_context,
)
from laconian_eval.capsule.attempts import TerminalReason
from laconian_eval.capsule.canonical import stable_digest
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.schema import (
    BoundedNonBlankString,
    CapsuleModel,
    Sha256,
    StrictNonNegativeInt,
)
from laconian_eval.capsule.scorable import ScoredAttemptV2, project_scored_attempts
from laconian_eval.capsule.sidecars import VerifiedScoredCapsuleV2

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

HardReasonCode: TypeAlias = Literal[
    "hard_pass",
    "provider_rejected",
    "retry_exhausted",
    "blank_output",
    "required_literal",
    "forbidden_literal",
    "json_object",
    "json_key_set",
    "yaml_mapping",
    "yaml_key_set",
    "min_sentences",
    "max_sentences",
]

_PROVIDER_FAILURE_REASONS = frozenset({"provider_rejected", "retry_exhausted"})


class HardScoreError(ValueError):
    """Raised when verified parents cannot produce the frozen request-set contract."""

    def __init__(self) -> None:
        super().__init__("hard-score request set rejected")


class HardScoreRecordV1(CapsuleModel):
    ordinal: StrictNonNegativeInt
    plan_item_id: Sha256
    attempt_id: Sha256
    response_id: Sha256 | None
    terminal_reason: TerminalReason
    hard_pass: StrictBool
    reason_codes: tuple[HardReasonCode, ...] = Field(min_length=1)
    judge_request_id: Sha256 | None

    @model_validator(mode="after")
    def validate_closed_result_shape(self) -> HardScoreRecordV1:
        if self.ordinal >= 40:
            raise ValueError("hard-score record ordinal must be in 0..39")
        if self.hard_pass:
            if (
                self.terminal_reason != "success"
                or self.response_id is None
                or self.reason_codes != ("hard_pass",)
                or self.judge_request_id is None
            ):
                raise ValueError("hard-pass record shape mismatch")
            return self

        if self.judge_request_id is not None or self.reason_codes != tuple(
            sorted(set(self.reason_codes), key=lambda item: item.encode("utf-8"))
        ):
            raise ValueError("hard-fail reason codes must be sorted and unique")
        if "hard_pass" in self.reason_codes:
            raise ValueError("hard-fail record cannot carry hard_pass")
        if self.terminal_reason in _PROVIDER_FAILURE_REASONS:
            if self.response_id is not None or self.reason_codes != (self.terminal_reason,):
                raise ValueError("provider-failure record shape mismatch")
        elif self.terminal_reason == "success":
            if self.response_id is None or any(
                reason in _PROVIDER_FAILURE_REASONS for reason in self.reason_codes
            ):
                raise ValueError("deterministic hard-fail record shape mismatch")
        else:
            raise ValueError("unsupported hard-score terminal reason")
        return self


class HardScoreRequestSetV1(CapsuleModel):
    schema_version: Literal["1"]
    campaign_id: BoundedNonBlankString
    generation_model: BoundedNonBlankString
    scenario_uid: Sha256
    generation_capsule_sha256: Sha256
    manifest_sha256: Sha256
    plan_sha256: Sha256
    hard_scorer_source_sha256: Sha256
    hard_score_protocol_sha256: Sha256
    judge_protocol_sha256: Sha256
    protocol_bindings: BenchmarkProtocolBindingsV1
    records: tuple[HardScoreRecordV1, ...] = Field(min_length=1, max_length=40)
    ordered_judge_request_ids: tuple[Sha256, ...]
    hard_score_request_set_sha256: Sha256

    @model_validator(mode="after")
    def validate_closed_request_set(self) -> HardScoreRequestSetV1:
        if len(self.records) != 40 or tuple(record.ordinal for record in self.records) != tuple(
            range(40)
        ):
            raise ValueError("hard-score request set requires exact ordinals 0..39")
        if (
            len({record.plan_item_id for record in self.records}) != 40
            or len({record.attempt_id for record in self.records}) != 40
        ):
            raise ValueError("hard-score records require unique plan and attempt identities")
        expected_request_ids = tuple(
            cast(str, record.judge_request_id) for record in self.records if record.hard_pass
        )
        if self.ordered_judge_request_ids != expected_request_ids or len(
            set(expected_request_ids)
        ) != len(expected_request_ids):
            raise ValueError("ordered judge request IDs do not match hard-pass plan order")
        if (
            self.hard_scorer_source_sha256 != self.protocol_bindings.hard_scorer_source_sha256
            or self.hard_score_protocol_sha256 != self.protocol_bindings.hard_score_protocol_sha256
            or self.judge_protocol_sha256 != self.protocol_bindings.judge_protocol_sha256
        ):
            raise ValueError("hard-score protocol projection mismatch")
        expected = stable_digest(
            "laconian-hard-score-request-set-v1",
            self.model_dump(mode="json", exclude={"hard_score_request_set_sha256"}),
        )
        if self.hard_score_request_set_sha256 != expected:
            raise ValueError("hard-score request-set digest mismatch")
        return self


def derive_judge_request_id(
    *,
    campaign_id: str,
    generation_capsule_sha256: str,
    plan_item_id: str,
    response_id: str,
    judge_protocol_sha256: str,
) -> str:
    """Derive one judge request ID without depending on the enclosing attachment."""

    if type(campaign_id) is not str or not campaign_id.strip():
        raise ValueError("campaign ID must be a nonblank string")
    for value in (
        generation_capsule_sha256,
        plan_item_id,
        response_id,
        judge_protocol_sha256,
    ):
        if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("judge request identity inputs must be lowercase SHA-256")
    return stable_digest(
        "laconian-judge-request-v1",
        {
            "campaign_id": campaign_id,
            "generation_capsule_sha256": generation_capsule_sha256,
            "plan_item_id": plan_item_id,
            "response_id": response_id,
            "judge_protocol_sha256": judge_protocol_sha256,
        },
    )


def _hard_reason_for_check(name: str) -> HardReasonCode:
    if name == "format.nonblank_output":
        return "blank_output"
    if name.startswith("exact.required_literal[") and name.endswith("]"):
        return "required_literal"
    if name.startswith("exact.forbidden_literal[") and name.endswith("]"):
        return "forbidden_literal"
    if name == "format.json_object":
        return "json_object"
    if name == "format.json_key_set" or (
        name.startswith("format.required_json_key[") and name.endswith("]")
    ):
        return "json_key_set"
    if name == "format.yaml_mapping":
        return "yaml_mapping"
    if name == "format.yaml_key_set" or (
        name.startswith("format.required_yaml_key[") and name.endswith("]")
    ):
        return "yaml_key_set"
    if name == "format.min_sentences":
        return "min_sentences"
    if name == "format.max_sentences":
        return "max_sentences"
    raise HardScoreError


def _strict_model_copy(model_type: type[PlanRowV1], value: object) -> PlanRowV1:
    if type(value) is not model_type:
        raise HardScoreError
    try:
        payload = model_type.model_dump(value, mode="python", round_trip=True, warnings=False)
        return model_type.model_validate(payload)
    except Exception:
        raise HardScoreError from None


def _strict_scored_copy(value: object) -> ScoredAttemptV2:
    if type(value) is not ScoredAttemptV2:
        raise HardScoreError
    try:
        payload = ScoredAttemptV2.model_dump(
            value,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return ScoredAttemptV2.model_validate(payload)
    except Exception:
        raise HardScoreError from None


def _checked_authority(
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
) -> tuple[
    VerifiedGenerationContextIndexV1,
    GenerationLayerRootMemberV1,
    VerifiedScoredCapsuleV2,
]:
    if (
        type(context) is not VerifiedGenerationContextIndexV1
        or type(expectation) is not VerifiedGenerationContextExpectationV1
        or type(boundary_ordinal) is not int
        or not 0 <= boundary_ordinal < 36
    ):
        raise HardScoreError
    try:
        checked_context = VerifiedGenerationContextIndexV1(
            expectation=context.expectation,
            index=context.index,
            root_index=context.root_index,
            generation_evidence=context.generation_evidence,
        )
        checked_expectation = VerifiedGenerationContextExpectationV1(
            expectation=expectation.expectation,
            bound_generation_complete_authority_root_sha256=(
                expectation.bound_generation_complete_authority_root_sha256
            ),
        )
    except Exception:
        raise HardScoreError from None
    if checked_context.expectation != checked_expectation:
        raise HardScoreError
    member = checked_context.root_index.members[boundary_ordinal]
    scored = checked_context.generation_evidence[boundary_ordinal]
    if (
        type(member) is not GenerationLayerRootMemberV1
        or type(scored) is not VerifiedScoredCapsuleV2
    ):
        raise HardScoreError
    if (
        member.ordinal != boundary_ordinal
        or scored.capsule_sha256 != member.generation_capsule_sha256
        or checked_context.index.ordered_generation_capsule_sha256s[boundary_ordinal]
        != member.generation_capsule_sha256
    ):
        raise HardScoreError
    return checked_context, member, scored


def _record_from_scored(
    *,
    campaign_id: str,
    generation_capsule_sha256: str,
    judge_protocol_sha256: str,
    plan: PlanRowV1,
    scored: ScoredAttemptV2,
) -> HardScoreRecordV1:
    if (
        plan.ordinal != scored.ordinal
        or plan.plan_item_id != scored.plan_item_id
        or plan.case_uid != scored.case_uid
        or plan.case_definition_sha256 != scored.case_definition_sha256
    ):
        raise HardScoreError
    mapped_checks = tuple(
        (_hard_reason_for_check(check.name), check.passed) for check in scored.checks
    )
    if scored.hard_pass:
        if scored.response_id is None or not all(passed for _, passed in mapped_checks):
            raise HardScoreError
        reasons: tuple[HardReasonCode, ...] = ("hard_pass",)
        judge_request_id = derive_judge_request_id(
            campaign_id=campaign_id,
            generation_capsule_sha256=generation_capsule_sha256,
            plan_item_id=scored.plan_item_id,
            response_id=scored.response_id,
            judge_protocol_sha256=judge_protocol_sha256,
        )
    elif scored.terminal_reason in _PROVIDER_FAILURE_REASONS:
        if scored.response_id is not None or mapped_checks:
            raise HardScoreError
        reasons = (cast(HardReasonCode, scored.terminal_reason),)
        judge_request_id = None
    elif scored.terminal_reason == "success":
        if scored.response_id is None:
            raise HardScoreError
        reasons = tuple(
            sorted(
                {reason for reason, passed in mapped_checks if not passed},
                key=lambda item: item.encode("utf-8"),
            )
        )
        if not reasons:
            raise HardScoreError
        judge_request_id = None
    else:
        raise HardScoreError
    return HardScoreRecordV1(
        ordinal=scored.ordinal,
        plan_item_id=scored.plan_item_id,
        attempt_id=scored.attempt_id,
        response_id=scored.response_id,
        terminal_reason=scored.terminal_reason,
        hard_pass=scored.hard_pass,
        reason_codes=reasons,
        judge_request_id=judge_request_id,
    )


def _build_hard_score_request_set(
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
) -> HardScoreRequestSetV1:
    checked_context, member, evidence = _checked_authority(
        context,
        expectation,
        boundary_ordinal,
    )
    if len(evidence.plan) != 40 or len(evidence.scored_attempts) != 40:
        raise HardScoreError
    checked_plan = tuple(_strict_model_copy(PlanRowV1, row) for row in evidence.plan)
    checked_scored = tuple(_strict_scored_copy(row) for row in evidence.scored_attempts)
    try:
        projected_scored = project_scored_attempts(
            plan=checked_plan,
            raw_attempts=tuple(row.raw for row in checked_scored),
            cases_by_uid=evidence.cases_by_uid,
        )
    except Exception:
        raise HardScoreError from None
    if projected_scored != checked_scored:
        raise HardScoreError
    if tuple(row.ordinal for row in checked_plan) != tuple(range(40)):
        raise HardScoreError
    scenario_uids = {row.scenario_uid for row in checked_plan}
    if (
        scenario_uids != {member.scenario_uid}
        or evidence.manifest.provider.model != member.generation_model
        or evidence.capsule_sha256 != member.generation_capsule_sha256
    ):
        raise HardScoreError
    index = checked_context.index
    records = tuple(
        _record_from_scored(
            campaign_id=index.campaign_id,
            generation_capsule_sha256=member.generation_capsule_sha256,
            judge_protocol_sha256=index.judge_protocol_sha256,
            plan=plan,
            scored=scored,
        )
        for plan, scored in zip(checked_plan, checked_scored, strict=True)
    )
    protocol_bindings = protocol_bindings_from_context(index)
    payload: dict[str, object] = {
        "schema_version": "1",
        "campaign_id": index.campaign_id,
        "generation_model": member.generation_model,
        "scenario_uid": member.scenario_uid,
        "generation_capsule_sha256": member.generation_capsule_sha256,
        "manifest_sha256": evidence.manifest_sha256,
        "plan_sha256": evidence.plan_sha256,
        "hard_scorer_source_sha256": index.hard_scorer_source_sha256,
        "hard_score_protocol_sha256": index.hard_score_protocol_sha256,
        "judge_protocol_sha256": index.judge_protocol_sha256,
        "protocol_bindings": protocol_bindings.model_dump(mode="json"),
        "records": [record.model_dump(mode="json") for record in records],
        "ordered_judge_request_ids": [
            record.judge_request_id for record in records if record.hard_pass
        ],
    }
    payload["hard_score_request_set_sha256"] = stable_digest(
        "laconian-hard-score-request-set-v1",
        payload,
    )
    return HardScoreRequestSetV1.model_validate(payload)


def build_hard_score_request_set(
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
) -> HardScoreRequestSetV1:
    """Derive all identities from one externally authorized verified context member."""

    try:
        return _build_hard_score_request_set(
            context=context,
            expectation=expectation,
            boundary_ordinal=boundary_ordinal,
        )
    except HardScoreError:
        raise
    except Exception:
        raise HardScoreError from None


def recompute_hard_score_request_set_sha256(
    attachment: HardScoreRequestSetV1,
) -> str:
    """Revalidate the attachment and recompute the digest omitting only its self field."""

    if type(attachment) is not HardScoreRequestSetV1:
        raise HardScoreError
    try:
        payload = HardScoreRequestSetV1.model_dump(
            attachment,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        checked = HardScoreRequestSetV1.model_validate(payload)
    except Exception:
        raise HardScoreError from None
    return stable_digest(
        "laconian-hard-score-request-set-v1",
        checked.model_dump(mode="json", exclude={"hard_score_request_set_sha256"}),
    )


def verify_hard_score_request_set(
    attachment: HardScoreRequestSetV1,
    *,
    context: VerifiedGenerationContextIndexV1,
    expectation: VerifiedGenerationContextExpectationV1,
    boundary_ordinal: int,
) -> None:
    """Rebuild from verified parents and require exact canonical attachment equality."""

    if type(attachment) is not HardScoreRequestSetV1:
        raise HardScoreError
    try:
        payload = HardScoreRequestSetV1.model_dump(
            attachment,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        checked = HardScoreRequestSetV1.model_validate(payload)
        expected = _build_hard_score_request_set(
            context=context,
            expectation=expectation,
            boundary_ordinal=boundary_ordinal,
        )
        if canonical_json_v1(checked.model_dump(mode="json")) != canonical_json_v1(
            expected.model_dump(mode="json")
        ):
            raise HardScoreError
    except HardScoreError:
        raise
    except Exception:
        raise HardScoreError from None


__all__ = (
    "HardReasonCode",
    "HardScoreError",
    "HardScoreRecordV1",
    "HardScoreRequestSetV1",
    "build_hard_score_request_set",
    "derive_judge_request_id",
    "recompute_hard_score_request_set_sha256",
    "verify_hard_score_request_set",
)
