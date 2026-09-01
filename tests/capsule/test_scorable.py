from __future__ import annotations

import hashlib
import inspect
import random
import traceback
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any
from uuid import UUID

import pytest
from capsule_helpers import raw_attempt_v2_payload
from pydantic import ValidationError

from laconian_eval.capsule.attempts import (
    RawAttemptV2,
    derive_attempt_id,
    raw_attempt_bytes,
)
from laconian_eval.capsule.canonical import sha256_bytes, stable_digest
from laconian_eval.capsule.record_models import PlanRowV1
from laconian_eval.capsule.scorable import (
    HardCheckV2,
    ScorableError,
    ScoredAttemptV2,
    project_scored_attempts,
)
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import CheckResult, HardConstraints, ResponseCase
from laconian_eval.scoring import deterministic_hard_checks

_CANARY = "TOP-SECRET /private/scoring-input"
_ARMS = ("baseline", "concise", "caveman", "if")


def _cases() -> tuple[dict[str, ResponseCase], tuple[str, str]]:
    json_case = ResponseCase(
        id="projection-json-en",
        scenario_id="projection-json",
        locale="en",
        category="structured-output",
        prompt="Return one JSON answer.",
        hard_constraints=HardConstraints(
            required_literals=("Done",),
            forbidden_literals=("Never",),
            required_json_keys=("answer",),
            min_sentences=1,
            max_sentences=1,
        ),
    )
    yaml_case = ResponseCase(
        id="projection-yaml-en",
        scenario_id="projection-yaml",
        locale="en",
        category="structured-output",
        prompt="Return one YAML answer.",
        hard_constraints=HardConstraints(
            required_literals=("Done",),
            forbidden_literals=("Never",),
            required_yaml_keys=("answer",),
            min_sentences=1,
            max_sentences=1,
        ),
    )
    json_uid = sha256_bytes(b"projection-json-case")
    yaml_uid = sha256_bytes(b"projection-yaml-case")
    return {json_uid: json_case, yaml_uid: yaml_case}, (json_uid, yaml_uid)


def _plan(
    cases_by_uid: dict[str, ResponseCase],
    case_uids: tuple[str, str],
) -> tuple[PlanRowV1, ...]:
    rows: list[PlanRowV1] = []
    for ordinal in range(40):
        case_uid = case_uids[ordinal % 2]
        case = cases_by_uid[case_uid]
        arm = _ARMS[ordinal % len(_ARMS)]
        rows.append(
            PlanRowV1(
                ordinal=ordinal,
                plan_item_id=sha256_bytes(f"plan:{ordinal}".encode()),
                pairing_unit_id=sha256_bytes(f"pair:{ordinal // 4}".encode()),
                case_uid=case_uid,
                scenario_uid=sha256_bytes(case.scenario_id.encode()),
                case_id=case.id,
                locale=case.locale,
                repetition=ordinal // 8,
                arm=arm,
                block_id=sha256_bytes(f"block:{ordinal // 4}".encode()),
                arm_position=ordinal % 4,
                prompt_sha256=sha256_bytes(case.prompt.encode()),
                case_definition_sha256=response_case_sha256(case),
                instruction_sha256=sha256_bytes(f"instruction:{arm}".encode()),
                request_config_sha256=sha256_bytes(b"request-config"),
                input_token_bound=65_578,
            )
        )
    return tuple(rows)


def _output_for(case: ResponseCase) -> str:
    return '{"answer":"Done."}' if case.id == "projection-json-en" else "answer: Done."


def _raw(
    plan: PlanRowV1,
    case: ResponseCase,
    *,
    attempt: int = 1,
    call_sequence: int = 0,
    terminal_reason: str | None = "success",
) -> RawAttemptV2:
    return RawAttemptV2.model_validate(
        raw_attempt_v2_payload(
            plan.model_dump(mode="json"),
            attempt=attempt,
            call_sequence=call_sequence,
            terminal_reason=terminal_reason,
            output_text=_output_for(case),
        )
    )


def _ledger(
    plan: tuple[PlanRowV1, ...],
    cases_by_uid: dict[str, ResponseCase],
) -> tuple[RawAttemptV2, ...]:
    rows: list[RawAttemptV2] = []
    for row in plan:
        case = cases_by_uid[row.case_uid]
        if row.ordinal == 7:
            rows.append(
                _raw(
                    row,
                    case,
                    attempt=1,
                    call_sequence=7,
                    terminal_reason=None,
                )
            )
            rows.append(
                _raw(
                    row,
                    case,
                    attempt=2,
                    call_sequence=8,
                    terminal_reason="success",
                )
            )
        else:
            rows.append(_raw(row, case, call_sequence=row.ordinal + 9))
    random.Random(9281).shuffle(rows)
    return tuple(rows)


def _fixture() -> tuple[tuple[PlanRowV1, ...], tuple[RawAttemptV2, ...], dict[str, ResponseCase]]:
    cases_by_uid, case_uids = _cases()
    plan = _plan(cases_by_uid, case_uids)
    return plan, _ledger(plan, cases_by_uid), cases_by_uid


def _scored_payload(
    plan: PlanRowV1,
    raw: RawAttemptV2,
    *,
    checks: tuple[HardCheckV2, ...] | None = None,
    hard_pass: bool = True,
) -> dict[str, object]:
    return {
        "schema_version": "2",
        "ordinal": plan.ordinal,
        "plan_item_id": plan.plan_item_id,
        "attempt_id": raw.attempt_id,
        "raw_attempt_sha256": sha256_bytes(raw_attempt_bytes(raw)),
        "case_uid": plan.case_uid,
        "case_definition_sha256": plan.case_definition_sha256,
        "response_id": raw.response_id,
        "terminal_reason": raw.terminal_reason,
        "raw": raw,
        "checks": (HardCheckV2(name="format.max_sentences", passed=True),)
        if checks is None
        else checks,
        "hard_pass": hard_pass,
    }


def _assert_scorable_error(call: Callable[[], object]) -> str:
    with pytest.raises(ScorableError) as caught:
        call()
    assert caught.value.code in {
        "invalid_input",
        "resource_limit",
        "plan_mismatch",
        "case_mismatch",
        "raw_mismatch",
        "scoring_mismatch",
    }
    assert str(caught.value) == "capsule scoring rejected"
    assert _CANARY not in str(caught.value)
    assert _CANARY not in repr(caught.value)
    return caught.value.code


def _rebind_raw(payload: dict[str, Any]) -> RawAttemptV2:
    run_id = UUID(payload["run_id"])
    payload["attempt_id"] = derive_attempt_id(
        run_id,
        payload["plan_item_id"],
        payload["attempt"],
    )
    output = payload["output_text"]
    if output is not None:
        output_sha256 = hashlib.sha256(output.encode("utf-8")).hexdigest()
        payload["output_sha256"] = output_sha256
        payload["response_id"] = stable_digest(
            "laconian-response-v1",
            {
                "run_id": run_id,
                "plan_item_id": payload["plan_item_id"],
                "attempt_id": payload["attempt_id"],
                "case_uid": payload["case_uid"],
                "instruction_sha256": payload["instruction_sha256"],
                "output_sha256": output_sha256,
            },
        )
    return RawAttemptV2.model_validate(payload)


def _replace_terminal(
    raw_rows: tuple[RawAttemptV2, ...],
    item_id: str,
    replacement: RawAttemptV2,
) -> tuple[RawAttemptV2, ...]:
    return tuple(
        replacement if row.plan_item_id == item_id and row.terminal else row for row in raw_rows
    )


def test_scored_attempt_binds_exact_terminal_identity_and_raw_hash() -> None:
    plan, raw_rows, _cases_by_uid = _fixture()
    raw = next(row for row in raw_rows if row.plan_item_id == plan[0].plan_item_id)
    scored = ScoredAttemptV2.model_validate(_scored_payload(plan[0], raw))

    assert scored.ordinal == plan[0].ordinal
    assert scored.plan_item_id == plan[0].plan_item_id == raw.plan_item_id
    assert scored.attempt_id == raw.attempt_id
    assert scored.raw_attempt_sha256 == sha256_bytes(raw_attempt_bytes(raw))
    assert scored.case_uid == plan[0].case_uid == raw.case_uid
    assert scored.case_definition_sha256 == plan[0].case_definition_sha256
    assert scored.case_definition_sha256 == raw.case_definition_sha256
    assert scored.response_id == raw.response_id
    assert scored.terminal_reason == raw.terminal_reason
    assert scored.hard_pass == (
        raw.terminal_reason == "success" and all(check.passed for check in scored.checks)
    )
    assert list(scored.model_dump(mode="json")) == [
        "schema_version",
        "ordinal",
        "plan_item_id",
        "attempt_id",
        "raw_attempt_sha256",
        "case_uid",
        "case_definition_sha256",
        "response_id",
        "terminal_reason",
        "raw",
        "checks",
        "hard_pass",
    ]


def test_scored_models_are_strict_frozen_extra_forbid_and_hard_only() -> None:
    plan, raw_rows, _cases_by_uid = _fixture()
    raw = next(row for row in raw_rows if row.plan_item_id == plan[0].plan_item_id)
    scored = ScoredAttemptV2.model_validate(_scored_payload(plan[0], raw))

    with pytest.raises(ValidationError):
        scored.ordinal = 1  # type: ignore[misc]
    with pytest.raises(ValidationError):
        HardCheckV2(name="strict", passed=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        HardCheckV2(name="", passed=True)
    with pytest.raises(ValidationError):
        HardCheckV2(name="x" * 1025, passed=True)
    with pytest.raises(ValidationError):
        HardCheckV2.model_validate({"name": "strict", "passed": True, "detail": "forbidden"})

    for field in ("unknown", "detail", "semantic_pass", "judgment_id", "judge_provenance"):
        with pytest.raises(ValidationError):
            ScoredAttemptV2.model_validate(_scored_payload(plan[0], raw) | {field: _CANARY})
    with pytest.raises(ValidationError):
        ScoredAttemptV2.model_validate(_scored_payload(plan[0], raw) | {"ordinal": True})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("plan_item_id", "a" * 64),
        ("attempt_id", "b" * 64),
        ("raw_attempt_sha256", "c" * 64),
        ("case_uid", "d" * 64),
        ("case_definition_sha256", "e" * 64),
        ("response_id", "f" * 64),
        ("terminal_reason", "provider_rejected"),
    ),
)
def test_scored_attempt_rejects_each_forged_duplicate_identity(
    field: str,
    value: object,
) -> None:
    plan, raw_rows, _cases_by_uid = _fixture()
    raw = next(row for row in raw_rows if row.plan_item_id == plan[0].plan_item_id)

    with pytest.raises(ValidationError):
        ScoredAttemptV2.model_validate(_scored_payload(plan[0], raw) | {field: value})


def test_scored_attempt_rejects_nonterminal_and_forbidden_terminal_reasons() -> None:
    plan, _raw_rows, cases_by_uid = _fixture()
    case = cases_by_uid[plan[0].case_uid]
    raw_rows = (
        _raw(plan[0], case, terminal_reason=None),
        _raw(plan[0], case, terminal_reason="authentication_stopped"),
        _raw(plan[0], case, terminal_reason="ambiguous_delivery"),
    )

    for raw in raw_rows:
        with pytest.raises(ValidationError):
            ScoredAttemptV2.model_validate(
                _scored_payload(plan[0], raw, checks=(), hard_pass=False)
            )


def test_scored_attempt_revalidates_raw_and_hard_pass_relations() -> None:
    plan, raw_rows, cases_by_uid = _fixture()
    success = next(row for row in raw_rows if row.plan_item_id == plan[0].plan_item_id)
    values = dict(success.__dict__)
    values.update(output_text=None, output_sha256=None, response_id=None)
    forged_success = RawAttemptV2.model_construct(**values)
    forged_payload = _scored_payload(plan[0], success)
    forged_payload["raw"] = forged_success

    with pytest.raises(ValidationError):
        ScoredAttemptV2.model_validate(forged_payload)

    failure = _raw(plan[0], cases_by_uid[plan[0].case_uid], terminal_reason="provider_rejected")
    with pytest.raises(ValidationError):
        ScoredAttemptV2.model_validate(_scored_payload(plan[0], failure, checks=(), hard_pass=True))
    with pytest.raises(ValidationError):
        ScoredAttemptV2.model_validate(
            _scored_payload(
                plan[0],
                failure,
                checks=(HardCheckV2(name="provider.error", passed=False),),
                hard_pass=False,
            )
        )
    with pytest.raises(ValidationError):
        ScoredAttemptV2.model_validate(
            _scored_payload(
                plan[0],
                success,
                checks=(HardCheckV2(name="format.max_sentences", passed=False),),
                hard_pass=True,
            )
        )


def test_scored_attempt_rejects_nested_model_subclasses_and_constructed_checks() -> None:
    plan, raw_rows, _cases_by_uid = _fixture()
    success = next(row for row in raw_rows if row.plan_item_id == plan[0].plan_item_id)

    class RawSubclass(RawAttemptV2):
        pass

    class CheckSubclass(HardCheckV2):
        pass

    raw_subclass = RawSubclass.model_validate(success.model_dump(mode="python"))
    check_subclass = CheckSubclass(name="format.max_sentences", passed=True)
    forged_check = HardCheckV2.model_construct(name="format.max_sentences", passed=_CANARY)
    base = _scored_payload(plan[0], success)

    for field, value in (
        ("raw", raw_subclass),
        ("checks", (check_subclass,)),
        ("checks", (forged_check,)),
    ):
        with pytest.raises(ValidationError):
            ScoredAttemptV2.model_validate(base | {field: value})


def test_projection_is_terminal_only_deterministic_and_in_plan_order() -> None:
    plan, raw_rows, cases_by_uid = _fixture()

    scored = project_scored_attempts(
        plan=plan,
        raw_attempts=raw_rows,
        cases_by_uid=cases_by_uid,
    )
    rescored = project_scored_attempts(
        plan=plan,
        raw_attempts=tuple(reversed(raw_rows)),
        cases_by_uid=cases_by_uid,
    )

    assert scored == rescored
    assert len(scored) == 40
    assert tuple(row.ordinal for row in scored) == tuple(range(40))
    assert tuple(row.plan_item_id for row in scored) == tuple(row.plan_item_id for row in plan)
    retried = scored[7]
    assert retried.raw.attempt == 2
    assert retried.raw.terminal
    assert retried.terminal_reason == "success"
    assert tuple(check.name for check in scored[0].checks) == (
        "exact.required_literal[0]",
        "exact.forbidden_literal[0]",
        "format.json_object",
        "format.json_key_set",
        "format.required_json_key[answer]",
        "format.min_sentences",
        "format.max_sentences",
    )
    assert tuple(check.name for check in scored[1].checks) == (
        "exact.required_literal[0]",
        "exact.forbidden_literal[0]",
        "format.yaml_mapping",
        "format.yaml_key_set",
        "format.required_yaml_key[answer]",
        "format.min_sentences",
        "format.max_sentences",
    )
    assert all(
        set(check.model_dump()) == {"name", "passed"} for row in scored for check in row.checks
    )
    assert all(row.hard_pass for row in scored)


@pytest.mark.parametrize("reason", ("provider_rejected", "retry_exhausted"))
def test_projection_preserves_terminal_provider_failure_reason_without_checks(reason: str) -> None:
    plan, raw_rows, cases_by_uid = _fixture()
    replacement = _raw(plan[0], cases_by_uid[plan[0].case_uid], terminal_reason=reason)

    scored = project_scored_attempts(
        plan=plan,
        raw_attempts=_replace_terminal(raw_rows, plan[0].plan_item_id, replacement),
        cases_by_uid=cases_by_uid,
    )

    assert scored[0].terminal_reason == reason
    assert scored[0].response_id is None
    assert scored[0].checks == ()
    assert scored[0].hard_pass is False


def _missing_raw(
    plan: tuple[PlanRowV1, ...],
    raw: tuple[RawAttemptV2, ...],
    cases: dict[str, ResponseCase],
) -> tuple[tuple[PlanRowV1, ...], tuple[RawAttemptV2, ...], dict[str, ResponseCase]]:
    del cases
    return plan, tuple(row for row in raw if row.plan_item_id != plan[1].plan_item_id), _cases()[0]


def _duplicate_terminal(
    plan: tuple[PlanRowV1, ...],
    raw: tuple[RawAttemptV2, ...],
    cases: dict[str, ResponseCase],
) -> tuple[tuple[PlanRowV1, ...], tuple[RawAttemptV2, ...], dict[str, ResponseCase]]:
    terminal = next(row for row in raw if row.plan_item_id == plan[1].plan_item_id)
    return plan, (*raw, terminal), cases


def _extra_raw(
    plan: tuple[PlanRowV1, ...],
    raw: tuple[RawAttemptV2, ...],
    cases: dict[str, ResponseCase],
) -> tuple[tuple[PlanRowV1, ...], tuple[RawAttemptV2, ...], dict[str, ResponseCase]]:
    payload = raw[0].model_dump(mode="json")
    payload["plan_item_id"] = sha256_bytes(b"unknown-plan-item")
    return plan, (*raw, _rebind_raw(payload)), cases


def _nonterminal_only(
    plan: tuple[PlanRowV1, ...],
    raw: tuple[RawAttemptV2, ...],
    cases: dict[str, ResponseCase],
) -> tuple[tuple[PlanRowV1, ...], tuple[RawAttemptV2, ...], dict[str, ResponseCase]]:
    replacement = _raw(plan[1], cases[plan[1].case_uid], terminal_reason=None)
    return plan, _replace_terminal(raw, plan[1].plan_item_id, replacement), cases


@pytest.mark.parametrize(
    "mutation",
    (_missing_raw, _duplicate_terminal, _extra_raw, _nonterminal_only),
)
def test_projection_requires_exact_terminal_raw_bijection(
    mutation: Callable[
        [tuple[PlanRowV1, ...], tuple[RawAttemptV2, ...], dict[str, ResponseCase]],
        tuple[tuple[PlanRowV1, ...], tuple[RawAttemptV2, ...], dict[str, ResponseCase]],
    ],
) -> None:
    plan, raw, cases = mutation(*_fixture())

    _assert_scorable_error(
        lambda: project_scored_attempts(plan=plan, raw_attempts=raw, cases_by_uid=cases)
    )


@pytest.mark.parametrize(
    ("field", "wrong"),
    (
        ("scenario_uid", "a" * 64),
        ("case_uid", "b" * 64),
        ("case_definition_sha256", "c" * 64),
        ("prompt_sha256", "d" * 64),
        ("case_id", "other-case-en"),
        ("locale", "ru"),
        ("arm", "if"),
        ("repetition", 99),
        ("instruction_sha256", "e" * 64),
        ("request_config_sha256", "f" * 64),
    ),
)
@pytest.mark.parametrize("target_terminal", (False, True), ids=("retry", "terminal"))
def test_projection_rejects_every_wrong_raw_to_plan_join(
    field: str,
    wrong: object,
    target_terminal: bool,
) -> None:
    plan, raw_rows, cases = _fixture()
    target_plan = plan[7] if not target_terminal else plan[1]
    target = next(
        row
        for row in raw_rows
        if row.plan_item_id == target_plan.plan_item_id and row.terminal is target_terminal
    )
    payload = target.model_dump(mode="json")
    if field == "arm" and payload[field] == wrong:
        wrong = "baseline"
    payload[field] = wrong
    forged = _rebind_raw(payload)
    changed = tuple(forged if row is target else row for row in raw_rows)

    _assert_scorable_error(
        lambda: project_scored_attempts(plan=plan, raw_attempts=changed, cases_by_uid=cases)
    )


def test_projection_requires_exact_case_mapping_and_case_binding() -> None:
    plan, raw_rows, cases = _fixture()
    missing = dict(cases)
    missing.pop(plan[0].case_uid)
    extra = dict(cases) | {sha256_bytes(b"extra-case"): next(iter(cases.values()))}
    wrong = dict(cases)
    wrong[plan[0].case_uid] = next(
        case for case in cases.values() if case != cases[plan[0].case_uid]
    )

    for mapping in (missing, extra, wrong):
        _assert_scorable_error(
            lambda mapping=mapping: project_scored_attempts(
                plan=plan,
                raw_attempts=raw_rows,
                cases_by_uid=mapping,
            )
        )


def test_projection_rejects_one_case_uid_bound_to_conflicting_scenarios() -> None:
    plan, raw_rows, cases = _fixture()
    target = plan[2]
    wrong_scenario = "a" * 64
    changed_plan = tuple(
        row.model_copy(update={"scenario_uid": wrong_scenario}) if row is target else row
        for row in plan
    )
    changed_raw = tuple(
        _rebind_raw(row.model_dump(mode="json") | {"scenario_uid": wrong_scenario})
        if row.plan_item_id == target.plan_item_id
        else row
        for row in raw_rows
    )

    _assert_scorable_error(
        lambda: project_scored_attempts(
            plan=changed_plan,
            raw_attempts=changed_raw,
            cases_by_uid=cases,
        )
    )


def test_projection_rejects_wrong_plan_order_or_duplicate_id() -> None:
    plan, raw_rows, cases = _fixture()
    skipped_ordinal = (plan[0].model_copy(update={"ordinal": 4}), *plan[1:])
    duplicate_id = (
        *plan[:-1],
        plan[-1].model_copy(update={"plan_item_id": plan[0].plan_item_id}),
    )

    for changed in (skipped_ordinal, duplicate_id):
        _assert_scorable_error(
            lambda changed=changed: project_scored_attempts(
                plan=changed,
                raw_attempts=raw_rows,
                cases_by_uid=cases,
            )
        )


def test_projection_class_bound_revalidates_every_input_without_echo() -> None:
    plan, raw_rows, cases = _fixture()
    plan_values = dict(plan[0].__dict__)
    plan_values["ordinal"] = _CANARY
    forged_plan = PlanRowV1.model_construct(**plan_values)
    raw_values = dict(raw_rows[0].__dict__)
    raw_values["request_config_sha256"] = _CANARY
    forged_raw = RawAttemptV2.model_construct(**raw_values)
    case_values = dict(cases[plan[0].case_uid].__dict__)
    case_values["prompt"] = " "
    forged_case = ResponseCase.model_construct(**case_values)

    calls = (
        lambda: project_scored_attempts(
            plan=(forged_plan, *plan[1:]),
            raw_attempts=raw_rows,
            cases_by_uid=cases,
        ),
        lambda: project_scored_attempts(
            plan=plan,
            raw_attempts=(forged_raw, *raw_rows[1:]),
            cases_by_uid=cases,
        ),
        lambda: project_scored_attempts(
            plan=plan,
            raw_attempts=raw_rows,
            cases_by_uid=dict(cases) | {plan[0].case_uid: forged_case},
        ),
    )
    for call in calls:
        _assert_scorable_error(call)


def test_projection_rejects_model_subclasses_at_each_class_bound_boundary() -> None:
    plan, raw_rows, cases = _fixture()

    class PlanSubclass(PlanRowV1):
        pass

    class RawSubclass(RawAttemptV2):
        pass

    class CaseSubclass(ResponseCase):
        pass

    subclass_plan = PlanSubclass.model_validate(plan[0].model_dump(mode="python"))
    subclass_raw = RawSubclass.model_validate(raw_rows[0].model_dump(mode="python"))
    original_case = cases[plan[0].case_uid]
    subclass_case = CaseSubclass.model_validate(original_case.model_dump(mode="python"))

    calls = (
        lambda: project_scored_attempts(
            plan=(subclass_plan, *plan[1:]),
            raw_attempts=raw_rows,
            cases_by_uid=cases,
        ),
        lambda: project_scored_attempts(
            plan=plan,
            raw_attempts=(subclass_raw, *raw_rows[1:]),
            cases_by_uid=cases,
        ),
        lambda: project_scored_attempts(
            plan=plan,
            raw_attempts=raw_rows,
            cases_by_uid=dict(cases) | {plan[0].case_uid: subclass_case},
        ),
    )
    for call in calls:
        _assert_scorable_error(call)


class _LengthMismatchSequence(Sequence[PlanRowV1]):
    def __init__(self, rows: tuple[PlanRowV1, ...]) -> None:
        self._rows = rows

    def __len__(self) -> int:
        return len(self._rows) - 1

    def __getitem__(self, index: int) -> PlanRowV1:
        return self._rows[index]

    def __iter__(self) -> Iterator[PlanRowV1]:
        return iter(self._rows)


class _OversizedSequence(Sequence[PlanRowV1]):
    def __len__(self) -> int:
        return 100_001

    def __getitem__(self, index: int) -> PlanRowV1:
        raise AssertionError(_CANARY)

    def __iter__(self) -> Iterator[PlanRowV1]:
        raise AssertionError(_CANARY)


class _CanaryLengthSequence(Sequence[PlanRowV1]):
    def __len__(self) -> int:
        raise RuntimeError(_CANARY)

    def __getitem__(self, index: int) -> PlanRowV1:
        raise AssertionError(index)


class _CanaryIteratorSequence(Sequence[PlanRowV1]):
    def __len__(self) -> int:
        return 1

    def __getitem__(self, index: int) -> PlanRowV1:
        raise AssertionError(index)

    def __iter__(self) -> Iterator[PlanRowV1]:
        raise RuntimeError(_CANARY)


class _LengthMismatchMapping(Mapping[str, ResponseCase]):
    def __init__(self, values: dict[str, ResponseCase]) -> None:
        self._values = values

    def __len__(self) -> int:
        return len(self._values) - 1

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __getitem__(self, key: str) -> ResponseCase:
        return self._values[key]

    def items(self) -> object:
        return self._values.items()


def test_projection_bounded_materialization_rejects_lying_sequences_and_mappings() -> None:
    plan, raw_rows, cases = _fixture()

    assert (
        _assert_scorable_error(
            lambda: project_scored_attempts(
                plan=_OversizedSequence(),
                raw_attempts=raw_rows,
                cases_by_uid=cases,
            )
        )
        == "resource_limit"
    )
    _assert_scorable_error(
        lambda: project_scored_attempts(
            plan=_LengthMismatchSequence(plan),
            raw_attempts=raw_rows,
            cases_by_uid=cases,
        )
    )
    _assert_scorable_error(
        lambda: project_scored_attempts(
            plan=plan,
            raw_attempts=raw_rows,
            cases_by_uid=_LengthMismatchMapping(cases),
        )
    )


@pytest.mark.parametrize("hostile_plan", (_CanaryLengthSequence(), _CanaryIteratorSequence()))
def test_public_scorable_error_discards_hostile_exception_chains(
    hostile_plan: Sequence[PlanRowV1],
) -> None:
    with pytest.raises(ScorableError) as caught:
        project_scored_attempts(
            plan=hostile_plan,
            raw_attempts=(),
            cases_by_uid={},
        )

    error = caught.value
    assert error.code == "invalid_input"
    assert error.args == ("capsule scoring rejected",)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _CANARY not in "".join(traceback.format_exception(error))


def test_projection_rejects_authored_overlong_check_name_content_free() -> None:
    case_uid = sha256_bytes(b"long-key-case")
    key = _CANARY + "x" * 1025
    case = ResponseCase(
        id="long-key-en",
        scenario_id="long-key",
        locale="en",
        category="structured-output",
        prompt="Return JSON.",
        hard_constraints=HardConstraints(required_json_keys=(key,)),
    )
    plan = _plan({case_uid: case, sha256_bytes(b"unused"): case}, (case_uid, case_uid))[:1]
    raw = (
        RawAttemptV2.model_validate(
            raw_attempt_v2_payload(
                plan[0].model_dump(mode="json"),
                output_text='{"' + key + '":"ok"}',
            )
        ),
    )

    _assert_scorable_error(
        lambda: project_scored_attempts(
            plan=plan,
            raw_attempts=raw,
            cases_by_uid={case_uid: case},
        )
    )


def test_deterministic_hard_checks_is_the_legacy_ordered_pure_projection() -> None:
    cases, case_uids = _cases()
    case = cases[case_uids[0]]

    first = deterministic_hard_checks(case, _output_for(case))
    second = deterministic_hard_checks(case, _output_for(case))

    assert first == second
    assert isinstance(first, tuple)
    assert tuple(check.name for check in first) == (
        "exact.required_literal[0]",
        "exact.forbidden_literal[0]",
        "format.json_object",
        "format.json_key_set",
        "format.required_json_key[answer]",
        "format.min_sentences",
        "format.max_sentences",
    )


def test_public_signatures_are_stable() -> None:
    assert str(inspect.signature(project_scored_attempts)) == (
        "(*, plan: 'Sequence[PlanRowV1]', raw_attempts: 'Sequence[RawAttemptV2]', "
        "cases_by_uid: 'Mapping[str, ResponseCase]') -> 'tuple[ScoredAttemptV2, ...]'"
    )
    hard_checks_signature = inspect.signature(deterministic_hard_checks)
    assert tuple(hard_checks_signature.parameters) == ("case", "output")
    assert hard_checks_signature.parameters["case"].annotation is ResponseCase
    assert hard_checks_signature.parameters["output"].annotation is str
    assert hard_checks_signature.return_annotation == tuple[CheckResult, ...]
