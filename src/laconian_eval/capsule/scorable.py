"""Deterministic hard-score projection for terminal capsule attempts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, NoReturn, Self, TypeAlias, TypeVar, cast

from pydantic import StrictBool, field_validator, model_validator

from laconian_eval.capsule.attempts import RawAttemptV2, raw_attempt_bytes
from laconian_eval.capsule.canonical import sha256_bytes
from laconian_eval.capsule.limits import RESOURCE_LIMITS_V1
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.schema import (
    BoundedNonBlankString,
    CapsuleModel,
    Sha256,
    StrictNonNegativeInt,
)
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import ResponseCase
from laconian_eval.scoring import deterministic_hard_checks

ScorableErrorCode: TypeAlias = Literal[
    "invalid_input",
    "resource_limit",
    "plan_mismatch",
    "case_mismatch",
    "raw_mismatch",
    "scoring_mismatch",
]
ScorableTerminalReason: TypeAlias = Literal["success", "retry_exhausted", "provider_rejected"]
_SCORABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "invalid_input",
        "resource_limit",
        "plan_mismatch",
        "case_mismatch",
        "raw_mismatch",
        "scoring_mismatch",
    }
)
_TERMINAL_REASONS = frozenset({"success", "retry_exhausted", "provider_rejected"})
_T = TypeVar("_T")


class HardCheckV2(CapsuleModel):
    name: BoundedNonBlankString
    passed: StrictBool


class ScoredAttemptV2(CapsuleModel):
    schema_version: Literal["2"]
    ordinal: StrictNonNegativeInt
    plan_item_id: Sha256
    attempt_id: Sha256
    raw_attempt_sha256: Sha256
    case_uid: Sha256
    case_definition_sha256: Sha256
    response_id: Sha256 | None
    terminal_reason: ScorableTerminalReason
    raw: RawAttemptV2
    checks: tuple[HardCheckV2, ...]
    hard_pass: StrictBool

    @field_validator("raw", mode="before")
    @classmethod
    def reject_raw_subclasses(cls, value: object) -> object:
        if isinstance(value, RawAttemptV2) and type(value) is not RawAttemptV2:
            raise ValueError("raw attempt subclass rejected")
        return value

    @field_validator("checks", mode="before")
    @classmethod
    def reject_check_subclasses(cls, value: object) -> object:
        if isinstance(value, (list, tuple)) and any(
            isinstance(check, HardCheckV2) and type(check) is not HardCheckV2 for check in value
        ):
            raise ValueError("hard-check subclass rejected")
        return value

    @model_validator(mode="after")
    def bind_terminal_raw_attempt(self) -> Self:
        try:
            if type(self.raw) is not RawAttemptV2:
                raise ValueError
            raw_payload = RawAttemptV2.model_dump(
                self.raw,
                mode="python",
                round_trip=True,
                warnings=False,
            )
            checked_raw = RawAttemptV2.model_validate(raw_payload)
            if checked_raw != self.raw:
                raise ValueError
            for check in self.checks:
                if type(check) is not HardCheckV2:
                    raise ValueError
                check_payload = HardCheckV2.model_dump(
                    check,
                    mode="python",
                    round_trip=True,
                    warnings=False,
                )
                if HardCheckV2.model_validate(check_payload) != check:
                    raise ValueError
            raw_sha256 = sha256_bytes(raw_attempt_bytes(self.raw))
        except Exception:
            raise ValueError("invalid nested raw attempt") from None
        if (
            not self.raw.terminal
            or self.raw.terminal_reason not in _TERMINAL_REASONS
            or self.plan_item_id != self.raw.plan_item_id
            or self.attempt_id != self.raw.attempt_id
            or self.raw_attempt_sha256 != raw_sha256
            or self.case_uid != self.raw.case_uid
            or self.case_definition_sha256 != self.raw.case_definition_sha256
            or self.response_id != self.raw.response_id
            or self.terminal_reason != self.raw.terminal_reason
        ):
            raise ValueError("scored attempt identity mismatch")

        success = self.raw.terminal_reason == "success"
        if success:
            if (
                self.raw.error is not None
                or self.raw.output_text is None
                or self.raw.output_sha256 is None
                or self.raw.response_id is None
            ):
                raise ValueError("scored success evidence mismatch")
        elif (
            self.raw.error is None
            or self.raw.output_text is not None
            or self.raw.output_sha256 is not None
            or self.raw.response_id is not None
            or self.checks
        ):
            raise ValueError("scored provider failure evidence mismatch")

        expected_hard_pass = success and all(check.passed for check in self.checks)
        if self.hard_pass is not expected_hard_pass:
            raise ValueError("hard-pass projection mismatch")
        return self


class ScorableError(ValueError):
    """Content-free scoring failure with a closed machine-readable code."""

    def __init__(self, code: ScorableErrorCode) -> None:
        checked_code = (
            code if type(code) is str and code in _SCORABLE_ERROR_CODES else "invalid_input"
        )
        self.code = cast(ScorableErrorCode, checked_code)
        super().__init__("capsule scoring rejected")


def _fail(code: ScorableErrorCode) -> NoReturn:
    raise ScorableError(code)


def _exact_tuple(
    values: Sequence[_T],
    *,
    maximum_count: int,
) -> tuple[_T, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        _fail("invalid_input")
    try:
        reported_count = len(values)
    except Exception:
        _fail("invalid_input")
    if reported_count > maximum_count:
        _fail("resource_limit")
    try:
        iterator = iter(values)
    except Exception:
        _fail("invalid_input")

    materialized: list[_T] = []
    for _ in range(reported_count):
        try:
            materialized.append(next(iterator))
        except Exception:
            _fail("invalid_input")
    try:
        next(iterator)
    except StopIteration:
        pass
    except Exception:
        _fail("invalid_input")
    else:
        _fail("invalid_input")
    if len(materialized) != reported_count:
        _fail("invalid_input")
    return tuple(materialized)


def _revalidate_plan_row(value: object) -> PlanRowV1:
    if type(value) is not PlanRowV1:
        _fail("plan_mismatch")
    try:
        payload = PlanRowV1.model_dump(
            value,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return PlanRowV1.model_validate(payload)
    except ScorableError:
        raise
    except Exception:
        _fail("plan_mismatch")


def _revalidate_raw_attempt(value: object) -> RawAttemptV2:
    if type(value) is not RawAttemptV2:
        _fail("raw_mismatch")
    try:
        payload = RawAttemptV2.model_dump(
            value,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return RawAttemptV2.model_validate(payload)
    except ScorableError:
        raise
    except Exception:
        _fail("raw_mismatch")


def _revalidate_response_case(value: object) -> ResponseCase:
    if type(value) is not ResponseCase:
        _fail("case_mismatch")
    try:
        payload = ResponseCase.model_dump(
            value,
            mode="python",
            round_trip=True,
            warnings=False,
        )
        return ResponseCase.model_validate(payload)
    except ScorableError:
        raise
    except Exception:
        _fail("case_mismatch")


def _materialize_cases(cases_by_uid: Mapping[str, ResponseCase]) -> dict[str, ResponseCase]:
    if not isinstance(cases_by_uid, Mapping):
        _fail("invalid_input")
    try:
        reported_count = len(cases_by_uid)
    except Exception:
        _fail("invalid_input")
    if reported_count > RESOURCE_LIMITS_V1.case_records:
        _fail("resource_limit")
    try:
        iterator = iter(cases_by_uid.items())
    except Exception:
        _fail("invalid_input")

    checked: dict[str, ResponseCase] = {}
    for _ in range(reported_count):
        try:
            item = next(iterator)
            key, value = item
        except Exception:
            _fail("invalid_input")
        if type(key) is not str or key in checked:
            _fail("case_mismatch")
        checked[key] = _revalidate_response_case(value)
    try:
        next(iterator)
    except StopIteration:
        pass
    except Exception:
        _fail("invalid_input")
    else:
        _fail("invalid_input")
    if len(checked) != reported_count:
        _fail("case_mismatch")
    return checked


def _validate_case_joins(
    plan: tuple[PlanRowV1, ...],
    cases_by_uid: dict[str, ResponseCase],
) -> None:
    expected_case_uids = {row.case_uid for row in plan}
    if set(cases_by_uid) != expected_case_uids:
        _fail("case_mismatch")
    scenario_by_case_uid: dict[str, str] = {}
    for row in plan:
        prior_scenario = scenario_by_case_uid.setdefault(row.case_uid, row.scenario_uid)
        if prior_scenario != row.scenario_uid:
            _fail("case_mismatch")
        case = cases_by_uid[row.case_uid]
        try:
            definition_sha256 = response_case_sha256(case)
            prompt_sha256 = sha256_bytes(case.prompt.encode("utf-8", errors="strict"))
        except Exception:
            _fail("case_mismatch")
        if (
            row.case_id != case.id
            or row.locale != case.locale
            or row.case_definition_sha256 != definition_sha256
            or row.prompt_sha256 != prompt_sha256
        ):
            _fail("case_mismatch")


def _raw_matches_plan(raw: RawAttemptV2, plan: PlanRowV1) -> bool:
    return (
        raw.plan_item_id == plan.plan_item_id
        and raw.scenario_uid == plan.scenario_uid
        and raw.case_uid == plan.case_uid
        and raw.case_id == plan.case_id
        and raw.locale == plan.locale
        and raw.case_definition_sha256 == plan.case_definition_sha256
        and raw.arm == plan.arm
        and raw.repetition == plan.repetition
        and raw.prompt_sha256 == plan.prompt_sha256
        and raw.instruction_sha256 == plan.instruction_sha256
        and raw.request_config_sha256 == plan.request_config_sha256
    )


def _terminal_rows_by_plan_item(
    plan_by_id: dict[str, PlanRowV1],
    raw_attempts: tuple[RawAttemptV2, ...],
) -> dict[str, RawAttemptV2]:
    terminal_by_id: dict[str, RawAttemptV2] = {}
    attempt_ids: set[str] = set()
    call_sequences: set[int] = set()
    for raw in raw_attempts:
        expected = plan_by_id.get(raw.plan_item_id)
        if (
            expected is None
            or not _raw_matches_plan(raw, expected)
            or raw.attempt_id in attempt_ids
            or raw.call_sequence in call_sequences
        ):
            _fail("raw_mismatch")
        attempt_ids.add(raw.attempt_id)
        call_sequences.add(raw.call_sequence)
        if not raw.terminal:
            continue
        if raw.terminal_reason not in _TERMINAL_REASONS or raw.plan_item_id in terminal_by_id:
            _fail("raw_mismatch")
        terminal_by_id[raw.plan_item_id] = raw
    if set(terminal_by_id) != set(plan_by_id):
        _fail("raw_mismatch")
    return terminal_by_id


def _score_terminal(
    plan: PlanRowV1,
    raw: RawAttemptV2,
    case: ResponseCase,
) -> ScoredAttemptV2:
    try:
        if raw.terminal_reason == "success":
            if raw.output_text is None:
                _fail("raw_mismatch")
            checks = tuple(
                HardCheckV2(name=check.name, passed=check.passed)
                for check in deterministic_hard_checks(case, raw.output_text)
            )
            hard_pass = all(check.passed for check in checks)
        else:
            checks = ()
            hard_pass = False
        return ScoredAttemptV2(
            schema_version="2",
            ordinal=plan.ordinal,
            plan_item_id=plan.plan_item_id,
            attempt_id=raw.attempt_id,
            raw_attempt_sha256=sha256_bytes(raw_attempt_bytes(raw)),
            case_uid=plan.case_uid,
            case_definition_sha256=plan.case_definition_sha256,
            response_id=raw.response_id,
            terminal_reason=cast(ScorableTerminalReason, raw.terminal_reason),
            raw=raw,
            checks=checks,
            hard_pass=hard_pass,
        )
    except ScorableError:
        raise
    except Exception:
        _fail("scoring_mismatch")


def _project_scored_attempts_core(
    *,
    plan: Sequence[PlanRowV1],
    raw_attempts: Sequence[RawAttemptV2],
    cases_by_uid: Mapping[str, ResponseCase],
) -> tuple[ScoredAttemptV2, ...]:
    checked_plan = tuple(
        _revalidate_plan_row(row)
        for row in _exact_tuple(plan, maximum_count=RESOURCE_LIMITS_V1.plan_rows)
    )
    checked_raw = tuple(
        _revalidate_raw_attempt(row)
        for row in _exact_tuple(raw_attempts, maximum_count=RESOURCE_LIMITS_V1.raw_rows)
    )
    checked_cases = _materialize_cases(cases_by_uid)
    if not checked_plan or not checked_raw:
        _fail("plan_mismatch")
    if tuple(row.ordinal for row in checked_plan) != tuple(range(len(checked_plan))):
        _fail("plan_mismatch")
    plan_by_id: dict[str, PlanRowV1] = {}
    for row in checked_plan:
        if row.plan_item_id in plan_by_id:
            _fail("plan_mismatch")
        plan_by_id[row.plan_item_id] = row

    _validate_case_joins(checked_plan, checked_cases)
    terminal_by_id = _terminal_rows_by_plan_item(plan_by_id, checked_raw)
    return tuple(
        _score_terminal(row, terminal_by_id[row.plan_item_id], checked_cases[row.case_uid])
        for row in checked_plan
    )


def project_scored_attempts(
    *,
    plan: Sequence[PlanRowV1],
    raw_attempts: Sequence[RawAttemptV2],
    cases_by_uid: Mapping[str, ResponseCase],
) -> tuple[ScoredAttemptV2, ...]:
    """Project exactly one deterministic terminal scored row in plan order."""

    failure_code: ScorableErrorCode | None = None
    try:
        return _project_scored_attempts_core(
            plan=plan,
            raw_attempts=raw_attempts,
            cases_by_uid=cases_by_uid,
        )
    except ScorableError as error:
        failure_code = error.code
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        failure_code = "invalid_input"
    assert failure_code is not None
    raise ScorableError(failure_code) from None
