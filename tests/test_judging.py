import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from laconian_eval.judging import (
    JudgeRequest,
    SemanticJudgment,
    attach_judgments,
    build_judge_request,
    load_judgments,
)
from laconian_eval.models import (
    ErrorInfo,
    HardConstraints,
    JudgeProvenance,
    RawAttempt,
    ResponseCase,
    SemanticRubric,
)
from laconian_eval.scoring import score_attempt


def digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def case() -> ResponseCase:
    return ResponseCase(
        id="judge-001-en",
        scenario_id="judge-001",
        locale="en",
        category="direct",
        prompt="Explain the answer.",
        semantic_rubric=SemanticRubric(
            required_facts=("fact one", "fact two"),
            material_warning="state the caveat",
        ),
    )


def raw(
    *,
    output: str | None = "The exact response.",
    arm: str = "if",
    instruction_hash: str | None = None,
    error: ErrorInfo | None = None,
    run_id: str = "run-1",
) -> RawAttempt:
    response_case = case()
    return RawAttempt(
        run_id=run_id,
        manifest_sha256=digest("manifest"),
        case_id=response_case.id,
        arm=arm,
        repetition=0,
        attempt=1,
        terminal=True,
        prompt_sha256=digest(response_case.prompt),
        instruction_sha256=instruction_hash or digest(f"{arm}-instruction"),
        provider="fake",
        model="fixture-v1",
        started_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        elapsed_ms=5,
        output_text=output,
        error=error,
    )


def judgment(response_id: str, *, passed: bool = True) -> SemanticJudgment:
    return SemanticJudgment(
        response_id=response_id,
        passed=passed,
        defect_codes=() if passed else ("missing_fact",),
        evidence="Synthetic evidence.",
        judge_provider="fixture",
        judge_model="fixture-judge-v1",
        judge_prompt_sha256=digest("judge prompt"),
    )


def test_judge_request_is_blind_and_contains_only_the_allowed_fields() -> None:
    response_case = case()

    request = build_judge_request(response_case, raw())

    assert isinstance(request, JudgeRequest)
    assert request.prompt == response_case.prompt
    assert request.locale == response_case.locale
    assert request.semantic_rubric == response_case.semantic_rubric
    assert request.response_text == "The exact response."
    assert len(request.response_id) == 64
    assert set(request.model_dump()) == {
        "response_id",
        "prompt",
        "locale",
        "semantic_rubric",
        "response_text",
    }
    serialized = request.model_dump_json()
    for forbidden in ("arm", "provider", "model", "token", "length"):
        assert forbidden not in serialized


def test_response_id_is_deterministic_opaque_and_distinguishes_arm_instances() -> None:
    response_case = case()
    first = build_judge_request(response_case, raw())
    repeated = build_judge_request(response_case, raw())
    other_arm_same_instruction = build_judge_request(
        response_case,
        raw(arm="concise", instruction_hash=digest("concise-instruction")),
    )
    other_run = build_judge_request(response_case, raw(run_id="run-2"))

    assert first.response_id == repeated.response_id
    assert first.response_id != other_arm_same_instruction.response_id
    assert first.response_id != other_run.response_id
    assert "run-1" not in first.response_id

    first_raw = raw()
    canonical = json.dumps(
        {
            "attempt": first_raw.attempt,
            "case_id": first_raw.case_id,
            "instruction_sha256": first_raw.instruction_sha256,
            "manifest_sha256": first_raw.manifest_sha256,
            "prompt_sha256": first_raw.prompt_sha256,
            "repetition": first_raw.repetition,
            "response_text": first_raw.output_text,
            "run_id": first_raw.run_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert first.response_id == digest(canonical)


def test_build_judge_request_validates_raw_identity_and_rejects_errors() -> None:
    response_case = case()
    error_raw = raw(
        output=None,
        error=ErrorInfo(kind="timeout", message="Timed out.", retryable=True),
    )

    with pytest.raises(ValueError, match="provider error"):
        build_judge_request(response_case, error_raw)
    with pytest.raises(ValueError, match="case_id"):
        build_judge_request(
            response_case.model_copy(update={"id": "judge-002-en"}),
            raw(),
        )
    with pytest.raises(ValueError, match="prompt_sha256"):
        build_judge_request(
            response_case.model_copy(update={"prompt": "Different prompt."}),
            raw(),
        )


def test_judgment_models_are_strict_and_frozen() -> None:
    request = build_judge_request(case(), raw())
    result = judgment(request.response_id)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        JudgeRequest.model_validate({**request.model_dump(), "arm": "if"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SemanticJudgment.model_validate({**result.model_dump(), "score": 1})
    with pytest.raises(ValidationError, match="frozen"):
        result.passed = False


def test_attach_judgments_matches_opaque_ids_and_leaves_missing_as_none() -> None:
    response_case = case()
    if_raw = raw()
    concise_raw = raw(arm="concise")
    scored = (
        score_attempt(response_case, if_raw),
        score_attempt(response_case, concise_raw),
    )
    if_id = build_judge_request(response_case, if_raw).response_id

    attached = attach_judgments(scored, (judgment(if_id, passed=False),))

    assert attached[0].semantic_pass is False
    assert attached[0].judgment_id == if_id
    assert attached[0].judge_provenance == JudgeProvenance(
        provider="fixture",
        model="fixture-judge-v1",
        prompt_sha256=digest("judge prompt"),
    )
    assert attached[1].semantic_pass is None
    assert attached[1].judgment_id is None
    assert attached[1].judge_provenance is None
    assert scored[0].semantic_pass is None


def test_attach_judgments_rejects_a_judgment_for_a_hard_failure() -> None:
    response_case = case().model_copy(
        update={"hard_constraints": HardConstraints(required_literals=("REQUIRED",))}
    )
    raw_response = raw(output="too short")
    hard_failure = score_attempt(response_case, raw_response)
    response_id = build_judge_request(response_case, raw_response).response_id

    assert not hard_failure.hard_pass
    with pytest.raises(ValueError, match="hard-fail"):
        attach_judgments((hard_failure,), (judgment(response_id),))


def test_attach_judgments_rejects_duplicate_unknown_and_duplicate_scored_ids() -> None:
    response_case = case()
    raw_response = raw()
    scored = score_attempt(response_case, raw_response)
    response_id = build_judge_request(response_case, raw_response).response_id
    valid = judgment(response_id)

    with pytest.raises(ValueError, match="duplicate judgment"):
        attach_judgments((scored,), (valid, valid))
    with pytest.raises(ValueError, match="unknown response_id"):
        attach_judgments((scored,), (judgment("f" * 64),))
    with pytest.raises(ValueError, match="duplicate scored response_id"):
        attach_judgments((scored, scored), ())


def test_attach_judgments_revalidates_provider_error_records() -> None:
    error_scored = score_attempt(
        case(),
        raw(
            output=None,
            error=ErrorInfo(kind="timeout", message="Timed out.", retryable=True),
        ),
    )
    tampered = error_scored.model_copy(
        update={
            "semantic_pass": True,
            "judgment_id": digest("response-id"),
            "judge_provenance": JudgeProvenance(
                provider="fixture",
                model="fixture-judge-v1",
                prompt_sha256=digest("judge prompt"),
            ),
        }
    )

    with pytest.raises(ValidationError, match="hard-fail"):
        attach_judgments((tampered,), ())


def test_load_synthetic_judgment_fixture_has_pass_and_failure() -> None:
    path = Path(__file__).parent / "fixtures" / "judge-results.yaml"

    judgments = load_judgments(path)

    assert {item.passed for item in judgments} == {True, False}
    assert "synthetic" in path.read_text(encoding="utf-8").lower()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "schema_version: '1'\ndescription: test\njudgments:\n"
            "  - response_id: &id "
            "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
            "    passed: true\n    defect_codes: []\n    evidence: ok\n"
            "    judge_provider: fixture\n    judge_model: fixture\n"
            "    judge_prompt_sha256: "
            "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'\n"
            "  - response_id: *id\n    passed: false\n    defect_codes: [x]\n"
            "    evidence: 'no'\n    judge_provider: fixture\n    judge_model: fixture\n"
            "    judge_prompt_sha256: "
            "'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'\n",
            "duplicate judgment",
        ),
        (
            "schema_version: '1'\nschema_version: '1'\ndescription: test\njudgments: []\n",
            "duplicate",
        ),
    ],
)
def test_load_judgments_rejects_duplicate_ids_and_yaml_keys(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    path = tmp_path / "judgments.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_judgments(path)
